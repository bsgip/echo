import enum

import numpy as np

from echo.echo_models import *

""""

    Below Zero assets

"""


class InputOutputNode(Node):
    """
    An input-output node has one input port and one output port.
    We assume the input port only ever imports, and the output port only ever exports.
    """
    input_port_unit: int
    output_port_unit: int
    # Some optional parameters for controlling input/output port flows
    max_output: Optional[NonPositiveFloat]
    min_output: Optional[NonPositiveFloat]
    max_input: Optional[NonNegativeFloat]
    min_input: Optional[NonNegativeFloat]


class GasBoilerFixedCOP(InputOutputNode):
    """ Gas boiler converts gas to heat at a fixed coefficient of performance (COP) where COP = output/input."""
    cop: NonNegativeFloat
    input_port_unit = Units.JPS
    output_port_unit = Units.KWT

    def __init__(self, **data) -> None:
        super().__init__(**data)
        # Add an input and output node, and create the appropriate transformation object
        self.ports['input'] = OffOrConstrainedPort(upper_bound=self.max_input, lower_bound=self.min_input,
                                                   units=self.input_port_unit)
        self.ports['output'] = OffOrConstrainedPort(upper_bound=self.min_output, lower_bound=self.max_output,
                                                    units=self.output_port_unit)
        self.add_input_output_transformation(input_port=self.ports['input'],
                                             output_port=self.ports['output'],
                                             input_weight=-self.cop)  # minus sign important


class TimeVaryingPiecewiseIONode(InputOutputNode):
    """ Node with an input and output port. it is assumed that the input port is always importing,
    and the output port is always exporting. The relationship between input and output is defined at each time
    interval by an array of input-->output point pairs, which are used to construct a piecewise constraint. """
    node_rule = NodeRule.Custom
    max_input: NonNegativeFloat
    min_input: float = 0.
    max_output: NonPositiveFloat
    min_output: float = 0.
    input_pts: Optional[dict]  # dict where the keys are planning-time period tuple, and value is input pt array
    output_pts: Optional[dict]  # dict where the keys are planning-time period tuple, and value is output pt array

    def __init__(self, **data):
        super().__init__(**data)
        self.ports['input'] = FlexPortImport(units=self.input_port_unit, import_constraint_value=self.max_input)
        self.ports['output'] = FlexPortExport(units=self.output_port_unit, export_constraint_value=self.max_output)

    def verify_node(self):
        assert self.input_pts is not None, 'No input points defined'
        assert self.output_pts is not None, 'No output points defined'

    def initialise_node(self, model):
        super(TimeVaryingPiecewiseIONode, self).initialise_node(model)
        # Need to bound our input and output port variables that we will use for piecewise
        set_float_var_bounds(model=model, var_name=self.ports['input'].port_name, ub=self.max_input, lb=0.)
        set_float_var_bounds(model=model, var_name=self.ports['output'].port_name, ub=0., lb=self.max_output)

    def apply_node_constraints(self, model):
        xvar = getattr(model, self.ports['input'].port_name)  # Get input/output pyomo variables
        yvar = getattr(model, self.ports['output'].port_name)
        xdata = self.input_pts  # Get piecewise points
        ydata = self.output_pts

        self.apply_piecewise_constraint(model, xvar, yvar, xdata, ydata)

    def apply_piecewise_constraint(self, model, xvar, yvar, xdata: dict, ydata: dict):
        con_name = 'piecewise_con_' + self.node_name
        setattr(model, con_name, en.Piecewise(model.Expansion, model.Time,
                                              yvar,
                                              xvar,
                                              pw_pts=xdata, pw_constr_type='EQ', f_rule=ydata, pw_repn='SOS2'))


class SinglePiecewiseIONode(TimeVaryingPiecewiseIONode):
    """ The relationship between input and output for all time intervals
    is given by an array of input-->output point pairs, which are used to construct a piecewise constraint."""

    def add_input_pts(self, array, time_periods, expansion_periods):
        self.input_pts = populate_values_across_time_and_expansion_indices(array, time_periods, expansion_periods)

    def add_output_pts(self, array, time_periods, expansion_periods):
        self.output_pts = populate_values_across_time_and_expansion_indices(array, time_periods, expansion_periods)


class SimpleChiller(SinglePiecewiseIONode):
    input_port_unit = Units.KW
    output_port_unit = Units.KWT


class TemperatureAdjustedChiller(TimeVaryingPiecewiseIONode):
    """
    A chiller converts an electrical input to a thermal cooling output.
    The conversion is defined by a piecewise constraint relating input/output.
    This constraint can be different for different time periods, reflecting that chiller performance depends on
    external air temperature which can be included as a parameter.
    """
    input_port_unit = Units.KW
    output_port_unit = Units.KWT
    external_temp: Optional[ArrayType]  # array of external temperatures
    input_coefficients: Optional[ArrayType]  # coefficients on the input power
    temp_coefficients: Optional[ArrayType]  # coefficients on external temp
    n_pts: Optional[int] = 5  # number of points per piecewise approximation

    def __init__(self, **data):
        super().__init__(**data)
        if self.external_temp is not None:
            assert self.input_coefficients is not None, 'If temp data is provided, temp coefficients are required.'
            assert self.temp_coefficients is not None, 'If temp data is provided, input coefficients are required.'
            self.generate_input_output_pts_from_coefficients()

    def generate_input_output_pts_from_coefficients(self):
        xpts = np.linspace(0, self.max_input, self.n_pts)
        time_periods = len(self.external_temp)
        self.input_pts, self.output_pts = create_input_output_pts_from_coefficients(self.temp_coefficients,
                                                                                    self.input_coefficients,
                                                                                    self.external_temp,
                                                                                    xpts,
                                                                                    time_periods)

    def get_cop(self, optimiser):
        """ Returns the coefficient of performance (output/input)"""
        # todo not set up for expansion planning
        _input = optimiser.values(self.ports['input'].port_name)
        _output = optimiser.values(self.ports['output'].port_name)
        cop = np.zeros(len(_input))
        for i in range(len(_input)):
            cop[i] = _output[i] / _input[i] * -1
        return cop


""" 
Thermal models
"""


class ThermalPort(FlexPort):
    """ Flexible thermal port."""

    def __init__(self):
        super(ThermalPort, self).__init__()
        self.units = Units.KWT


class ThermalLoad(Sink):
    """ Heating or cooling load. Fixed parameter."""

    def __init__(self):
        super(ThermalLoad, self).__init__()
        self.units = Units.KWT


class ControllableHCLoad(Port):
    """
    Heating or cooling load, that is controllable via a temperature setpoint parameter.
    Therefore the load is controllable, and is a variable in the optimisation.
    To write down the appropriate constraints with respect to the desired temperature setpoint, we need to know:
    - external air temp
    - parameter representing the building size/footprint.

    """
    flows = Flows.Import
    import_constraint = FlowConstraint.InRange
    units = Units.KWT
    temp_setpoints: Optional[ArrayType]  # Parameter for the temperature setpoints over time
    # The below parameter is used to create a heating load in kW from the
    # difference between the temp setpoint and outside air temp. It represents the building size/volume.
    factor: Optional[float]


"""
Gas models
"""


class GasPort(FlexPort):

    def __init__(self):
        super(GasPort, self).__init__()
        self.units = Units.JPS


class GasDemand(Sink):

    def __init__(self):
        super(GasDemand, self).__init__()
        self.units = Units.JPS


class GasSource(Source):

    def __init__(self):
        super(GasSource, self).__init__()
        self.units = Units.JPS



class TemperatureControlledHeatingLoad(FlexPortImport):
    """ A thermal port with an additional temperature variable that is influenced by the value of the port
    (i.e. how much heat is being delivered). The temperature variable is also influenced by an external temp parameter and a loss factor."""
    units = Units.KWT
    temp_ub: ArrayType  # Upper bound of acceptable temperature for each time interval
    temp_lb: ArrayType  # Lower bound of acceptable temperature for each time interval
    external_temp: dict  # External temp
    loss_factor: Optional[float]  # Losses via the difference between the internal temp and the external temp

    # Pyomo vars/params
    internal_temp: Optional[str]
    temp_error: Optional[str]

    def __init__(self, **data):
        super().__init__(**data)
        self.internal_temp = 'internal_temp_' + self.port_name
        self.temp_error = 'temp_error_' + self.port_name

    def initialise_port(self, model):
        super(TemperatureControlledHeatingLoad, self).initialise_port(model)
        # Create temperature variable
        setattr(model, self.internal_temp, en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))
        # Bound variable to be within acceptable range
        ub_dict = generate_array_constraint(self.temp_ub, time_periods=len(model.Time),
                                            expansion_periods=len(model.Expansion))
        lb_dict = generate_array_constraint(self.temp_lb, time_periods=len(model.Time),
                                            expansion_periods=len(model.Expansion))
        set_var_bounds_from_dict(var=getattr(model, self.internal_temp), ub=ub_dict, lb=lb_dict)
        # Create an error variable for difference between setpoint and actual temperature
        setattr(model, self.temp_error, en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))

        # def temp_error_rule(model, p, t):
        #     return getattr(model, self.temp_error)[p, t] == self.temp_setpoint - getattr(model, self.internal_temp)[p, t]
        #
        # setattr(model, 'temp_error_con_'+self.port_name, en.Constraint(model.Expansion, model.Time, rule=temp_error_rule))

        # Constraint for internal temp vs external temp vs supplied heat
        def rule1(model, p, t):
            if p == 0 and t == 0:
                return en.Constraint.Skip
            else:
                temp_diff = getattr(model, self.internal_temp)[p, t] - getattr(model, self.internal_temp)[p, t - 1]
                loss_term = (self.external_temp[p, t] - getattr(model, self.internal_temp)[p, t])
                return getattr(model, self.port_name)[p, t] == temp_diff - loss_term

        setattr(model, 'internal_temp_con_' + self.port_name, en.Constraint(model.Expansion, model.Time, rule=rule1))


#
# class ARXPort(FlexPort):
#     """ An ARX port has additional input variables """
#     input_data: pd.DataFrame
#     output_data: pd.DataFrame
#     controllable_input: str  # string of name of input col that is controllable
#
#     control_var: Optional[str]
#
#     def __init__(self, **data):
#         super().__init__(**data)
#         self.ports['input'] = FlexPort()
#         self.ports['output'] = FlexPort()
#         mse_test, mse_trained, model_coef = train_arx_on_data(u=self.input_data,
#                                                               y=self.output_data,
#                                                               na=2, nb=2,
#                                                               training_test_split=80)
#         self.control_var = self.controllable_input + self.node_name
#
#     def initialise_node(self, model):
#         super(ARXInputOutputNode, self).initialise_node(model)
#         setattr(model, self.control_var, en.Var())
#     def apply_node_constraints(self, model):


class InputOutputNode(Node):
    input_unit: int
    output_unit: int

    def __init__(self, **data):
        super().__init__(**data)
        self.add_flex_port('input', unit=self.input_unit)
        self.add_flex_port('output', unit=self.output_unit)


class TempControlledBoiler(InputOutputNode):
    """ A temp controlled boiler has an input and output port. """
    input_unit = Units.JPS
    output_unit = Units.KWT
    max_input: float
    max_output: float
    outlet_temp_setpoint = 80
    node_rule = NodeRule.Custom

    # pyomo vars
    is_on: Optional[str]
    return_temp: Optional[str]
    exit_temp: Optional[str]

    def __init__(self, **data):
        super().__init__(**data)
        self.ports['input'].set_flow_constraints(max_import=self.max_input, max_export=0.)
        self.ports['output'].set_flow_constraints(max_import=0., max_export=self.max_output)
        self.return_temp = 'inlet_temp_' + self.node_name
        self.exit_temp = 'outlet_temp_' + self.node_name

    def initialise_node(self, model):
        super(TempControlledBoiler, self).initialise_node(model)
        # Define extra variables
        setattr(model, self.return_temp, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Reals))
        setattr(model, self.exit_temp, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Reals))

    def apply_node_constraints(self, model):
        def constraint1(model, p, t):
            return getattr(model, self.exit_temp)[p, t] == self.outlet_temp_setpoint

        setattr(model, 'boiler_temp_con1_' + self.node_name,
                en.Constraint(model.Expansion, model.Time, rule=constraint1))

        def constraint2(model, p, t):
            """ return at time t = exiting at time t-1 minus energy removed at t-1"""
            return getattr(model, self.return_temp)[p, t] == getattr(model, self.exit_temp)[p, t] + \
                   getattr(model, self.ports['output'].port_name)[p, t]

        setattr(model, 'boiler_temp_con2_' + self.node_name,
                en.Constraint(model.Expansion, model.Time, rule=constraint2))

        def constraint3(model, p, t):
            """ exiting at time t = return at time t-1 + energy added at time t-1"""
            return getattr(model, self.exit_temp)[p, t] == getattr(model, self.ports['input'].port_name)[p, t] + \
                   getattr(model, self.return_temp)[p, t]

        setattr(model, 'boiler_temp_con3_' + self.node_name,
                en.Constraint(model.Expansion, model.Time, rule=constraint3))


class ThermalStorage(Storage):
    self_discharge: float = 0  # rate at which energy is lost from storage
    units = Units.KWT
    external_temp: ArrayType

    # pyomo vars/params
    internal_temp: Optional[str]

    def __init__(self, **data):
        super().__init__(**data)
        self.internal_temp = 'internal_temp_' + self.port_name

    def initialise_port(self, model):
        super(ThermalStorage, self).initialise_port(model)
        # Create a variable for the internal temperature


class BuildingThermalLoad(Node):
    """
    A building thermal load has two ports, a cooling input and a heating input.
    It has an internal temperature that is determined by the combination of heating and cooling input.
    """
    node_rule = NodeRule.Custom
    external_temp: Optional[dict]
    temp_ub: ArrayType  # Upper bound of acceptable temperature for each time interval
    temp_lb: ArrayType  # Lower bound of acceptable temperature for each time interval
    loss_factor: Optional[float]
    temp_to_energy_coef: float  # coefficient that relates changes in temperature to changes in energy in/out. energy=coef*delta T

    # pyomo vars/params
    internal_temp: Optional[str]

    def __init__(self, **data):
        super().__init__(**data)
        self.internal_temp = 'internal_temp_' + self.node_name
        self.ports['heating'] = FlexPortImport(units=Units.KWT)
        self.ports['cooling'] = FlexPortImport(units=Units.KWT)

    def initialise_node(self, model):
        super(BuildingThermalLoad, self).initialise_node(model)
        # Create temperature variable
        setattr(model, self.internal_temp, en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))
        # Bound variable to be within acceptable range
        ub_dict = generate_array_constraint(self.temp_ub, time_periods=len(model.Time),
                                            expansion_periods=len(model.Expansion))
        lb_dict = generate_array_constraint(self.temp_lb, time_periods=len(model.Time),
                                            expansion_periods=len(model.Expansion))
        set_var_bounds_from_dict(var=getattr(model, self.internal_temp), ub=ub_dict, lb=lb_dict)

    def apply_node_constraints(self, model):

        # Constraint for internal temp vs external temp vs supplied heat
        def rule1(model, p, t):
            cooling_input = getattr(model, self.ports['cooling'].port_name)[p, t]
            heating_input = getattr(model, self.ports['heating'].port_name)[p, t]
            internal_temp = getattr(model, self.internal_temp)
            if self.loss_factor is not None:
                external_temp_diff = (self.external_temp[p, t] - getattr(model, self.internal_temp)[p, t])
                energy_diff = external_temp_diff * self.loss_factor * self.temp_to_energy_coef
            else:
                energy_diff = 0

            if p == 0 and t == 0:
                return heating_input - cooling_input == internal_temp[p, t] * self.temp_to_energy_coef - energy_diff
            else:
                temp_diff = internal_temp[p, t] - internal_temp[p, t - 1]
                return (heating_input - cooling_input) == temp_diff * self.temp_to_energy_coef - energy_diff

        setattr(model, 'internal_temp_con_' + self.node_name, en.Constraint(model.Expansion, model.Time, rule=rule1))


class HeatPump(Node):
    """ A heat pump can produce heating water or cooling water,
    and therefore can serve both heating loads and cooling loads."""
    heating_sp = 80  # 80 deg C hot water
    cooling_sp = 6  # 6 deg C cooled water
    node_rule = NodeRule.Custom
    heating_cop_time_series: dict
    cooling_cop_time_series: dict

    # pyomo vars/params
    heating_cop: Optional[str]
    cooling_cop: Optional[str]
    is_heating: Optional[str]
    heat_in: Optional[str]
    cool_in: Optional[str]

    def __init__(self, **data):
        super().__init__(**data)
        self.ports['input'] = FlexPortImport(units=Units.KW)  # Heat pump has electrical input port
        self.ports['heating_out'] = FlexPortExport(units=Units.KWT) # Heat pump has a thermal port for heating output
        self.ports['cooling_out'] = FlexPortExport(units=Units.KWT)  # Heat pump has a thermal port for cooling output

        # Naming variables
        self.heating_cop = 'heating_cop_' + self.node_name
        self.cooling_cop = 'cooling_cop_' + self.node_name
        self.is_heating = 'is_heating_' + self.node_name
        self.heat_in = 'heat_in_' + self.node_name
        self.cool_in = 'cool_in_' + self.node_name

    def initialise_node(self, model):
        super(HeatPump, self).initialise_node(model)
        # Create extra vars
        setattr(model, self.is_heating, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary))
        setattr(model, self.heat_in, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
        setattr(model, self.cool_in, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))

        # Create params
        setattr(model, self.heating_cop, en.Param(model.Expansion, model.Time, initialize=self.heating_cop_time_series, domain=en.NonNegativeReals))
        setattr(model, self.cooling_cop, en.Param(model.Expansion, model.Time, initialize=self.cooling_cop_time_series, domain=en.NonNegativeReals))

    def apply_node_constraints(self, model):
        p_in = getattr(model, self.ports['input'].port_name)
        heat_out = getattr(model, self.ports['heating_out'].port_name)
        cool_out = getattr(model, self.ports['cooling_out'].port_name)
        heating_cop = getattr(model, self.heating_cop)
        cooling_cop = getattr(model, self.cooling_cop)

        def only_heat_or_cool1(model, p, t):
            return getattr(model, self.heat_in)[p, t] <= getattr(model, self.is_heating)[p, t] * model.bigM

        setattr(model, 'only_heat_or_cool1_' + self.node_name, en.Constraint(model.Expansion, model.Time, rule=only_heat_or_cool1))

        def only_heat_or_cool2(model, p, t):
            return getattr(model, self.cool_in)[p, t] <= (1 - getattr(model, self.is_heating)[p, t]) * model.bigM

        setattr(model, 'only_heat_or_cool2_' + self.node_name, en.Constraint(model.Expansion, model.Time, rule=only_heat_or_cool2))

        def sum_rule(model, p, t):
            return p_in[p, t] == getattr(model, self.heat_in)[p, t] + getattr(model, self.cool_in)[p, t]

        setattr(model, 'sum_heat_cool_'+self.node_name, en.Constraint(model.Expansion, model.Time, rule=sum_rule))

        def heating_output_rule(model, p, t):
            return heat_out[p, t] == getattr(model, self.heat_in)[p, t] * heating_cop[p, t] * -1

        def cooling_output_rule(model, p, t):
            return cool_out[p, t] == getattr(model, self.cool_in)[p, t] * cooling_cop[p, t] * -1

        setattr(model, 'heat_con_'+self.node_name, en.Constraint(model.Expansion, model.Time, rule=heating_output_rule))
        setattr(model, 'cool_con_'+self.node_name, en.Constraint(model.Expansion, model.Time, rule=cooling_output_rule))

    def get_heating_cop(self, optimiser):
        _out = optimiser.values(self.ports['heating_out'].port_name)
        _in = optimiser.values(self.heat_in)
        return _out/_in

    def get_cooling_cop(self, optimiser):
        _out = optimiser.values(self.ports['cooling_out'].port_name)
        _in = optimiser.values(self.cool_in)
        return _out/_in


class HeatPump4Pipe(Node):
    """ a 4 pipe heat pump can produce heating and cooling simultaneously"""
    #todo implement this




""" 
Control system models 
"""


class TimeDelayNode(Node):
    """ An input output node that implements a fixed delay between input and output."""
    time_delay: float
    input_unit: int
    output_unit: int
    node_rule = NodeRule.Custom

    def __init__(self, **data):
        super().__init__(**data)
        self.ports['input'] = FlexPortImport(units=self.input_unit)
        self.ports['output'] = FlexPortExport(units=self.output_unit)

    def apply_node_constraints(self, model):

        def time_delay_rule(model, p, t):  # Modified tellegen node rule
            a = getattr(model, self.ports['input'].port_name)
            b = getattr(model, self.ports['output'].port_name)
            if t < self.time_delay:
                return b[p, t] == 0
            else:
                return b[p, t] == a[p, int(t - self.time_delay)] * -1

        con_name = 'time_delay_con_' + self.node_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=time_delay_rule))

