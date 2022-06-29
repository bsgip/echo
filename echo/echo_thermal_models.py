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

    def add_input_pts(self, array, time_periods, expansion_periods=1):
        self.input_pts = populate_values_across_time_and_expansion_indices(array, time_periods, expansion_periods)

    def add_output_pts(self, array, time_periods, expansion_periods=1):
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

# class InputOutputNode(Node):
#     input_unit: int
#     output_unit: int
#
#     def __init__(self, **data):
#         super().__init__(**data)
#         self.add_flex_port('input', unit=self.input_unit)
#         self.add_flex_port('output', unit=self.output_unit)
""" 
Thermal models
"""


class ThermalPort(FlexPort):
    """ Flexible thermal port. Pos indicates that the port is importing heat, neg indicates the port is exporting heat."""
    units = Units.KWT


class FixedThermalPort(FixedPort):
    units = Units.KWT


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
        #todo finish this


class ControllableThermalLoad(ThermalPort):
    """  Port where +ve indicates heating load (ie adding heat) and -ve indicates cooling load (ie removing heat). """
    temp_ub: ArrayType  # Upper bound of acceptable temperature for each time interval
    temp_lb: ArrayType  # Lower bound of acceptable temperature for each time interval
    external_temp: dict  # External temp
    loss_factor: Optional[float]  # Losses via the difference between the internal temp and the external temp
    temp_to_energy_coef: float = 1

    # Pyomo vars/params
    internal_temp: Optional[str]

    def __init__(self, **data):
        super().__init__(**data)
        self.internal_temp = 'internal_temp_' + self.port_name

    def initialise_port(self, model):
        super(ControllableThermalLoad, self).initialise_port(model)
        self.constrain_pos_neg(model)
        # Create temperature variable
        setattr(model, self.internal_temp, en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))
        # Bound temp variable to be within range
        ub_dict = generate_array_constraint(self.temp_ub, time_periods=len(model.Time),
                                            expansion_periods=len(model.Expansion))
        lb_dict = generate_array_constraint(self.temp_lb, time_periods=len(model.Time),
                                            expansion_periods=len(model.Expansion))
        set_var_bounds_from_dict(var=getattr(model, self.internal_temp), ub=ub_dict, lb=lb_dict)

        # Constraint for internal temp vs external temp vs supplied heat (heating) vs removed heat (cooling)
        def rule1(model, p, t):
            cooling = getattr(model, self.neg)[p, t]
            heating = getattr(model, self.pos)[p, t]
            internal_temp = getattr(model, self.internal_temp)
            if self.loss_factor is not None:
                external_temp_diff = (self.external_temp[p, t] - getattr(model, self.internal_temp)[p, t])
                energy_diff = external_temp_diff * self.loss_factor * self.temp_to_energy_coef
            else:
                energy_diff = 0

            if p == 0 and t == 0:
                return heating + cooling == internal_temp[p, t] * self.temp_to_energy_coef - energy_diff
            else:
                temp_diff = internal_temp[p, t] - internal_temp[p, t - 1]
                return heating + cooling == temp_diff * self.temp_to_energy_coef - energy_diff

        setattr(model, 'internal_temp_con_' + self.port_name, en.Constraint(model.Expansion, model.Time, rule=rule1))


class HeatPump(Node):
    """ HP is input output where output can be pos for heating, neg for cooling."""
    node_rule = NodeRule.Custom
    heating_cop_time_series: dict
    cooling_cop_time_series: dict

    # pyomo vars/params
    heating_cop: Optional[str]
    cooling_cop: Optional[str]
    heat_in: Optional[str]
    cool_in: Optional[str]

    def __init__(self, **data):
        super().__init__(**data)
        self.ports['input'] = FlexPortImport(units=Units.KW)  # Heat pump has electrical input port
        self.ports['output'] = FlexPort(units=Units.KWT)

        # Naming variables
        self.heating_cop = 'heating_cop_' + self.node_name
        self.cooling_cop = 'cooling_cop_' + self.node_name
        self.heat_in = 'heat_in_' + self.node_name
        self.cool_in = 'cool_in_' + self.node_name

    def initialise_node(self, model):
        super(HeatPump, self).initialise_node(model)
        # Need to split pos/neg on output. Pos will become cooling ('importing' heat), and neg will become heating
        self.ports['output'].constrain_pos_neg(model)

        # Variables for assigning the input electrical energy to either heating or cooling operation
        setattr(model, self.heat_in, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
        setattr(model, self.cool_in, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))

        # Create params
        setattr(model, self.heating_cop, en.Param(model.Expansion, model.Time, initialize=self.heating_cop_time_series,
                                                  domain=en.NonNegativeReals))
        setattr(model, self.cooling_cop, en.Param(model.Expansion, model.Time, initialize=self.cooling_cop_time_series,
                                                  domain=en.NonNegativeReals))

    def apply_node_constraints(self, model):
        is_cooling = getattr(model, self.ports['output'].is_pos)  # binary var for whether we are cooling
        p_in = getattr(model, self.ports['input'].port_name)  # input electrical power
        heat_out = getattr(model, self.ports['output'].neg)  # heating delivered
        cool_out = getattr(model, self.ports['output'].pos)  # cooling delivered
        heating_cop = getattr(model, self.heating_cop)
        cooling_cop = getattr(model, self.cooling_cop)

        def only_heat_or_cool1(model, p, t):
            return getattr(model, self.heat_in)[p, t] <= (1 - is_cooling[p, t]) * model.bigM

        setattr(model, 'only_heat_or_cool1_' + self.node_name,
                en.Constraint(model.Expansion, model.Time, rule=only_heat_or_cool1))

        def only_heat_or_cool2(model, p, t):
            return getattr(model, self.cool_in)[p, t] <= is_cooling[p, t] * model.bigM

        setattr(model, 'only_heat_or_cool2_' + self.node_name,
                en.Constraint(model.Expansion, model.Time, rule=only_heat_or_cool2))

        def sum_rule(model, p, t):
            return p_in[p, t] == getattr(model, self.heat_in)[p, t] + getattr(model, self.cool_in)[p, t]

        setattr(model, 'sum_heat_cool_' + self.node_name, en.Constraint(model.Expansion, model.Time, rule=sum_rule))

        def heating_output_rule(model, p, t):
            return heat_out[p, t] == getattr(model, self.heat_in)[p, t] * heating_cop[p, t] * -1

        def cooling_output_rule(model, p, t):
            return cool_out[p, t] == getattr(model, self.cool_in)[p, t] * cooling_cop[p, t]

        setattr(model, 'heat_con_' + self.node_name,
                en.Constraint(model.Expansion, model.Time, rule=heating_output_rule))
        setattr(model, 'cool_con_' + self.node_name,
                en.Constraint(model.Expansion, model.Time, rule=cooling_output_rule))

    def get_heating_cop(self, optimiser):
        _out = optimiser.values(self.ports['output'].pos)
        _in = optimiser.values(self.heat_in)
        return _out / _in

    def get_cooling_cop(self, optimiser):
        _out = optimiser.values(self.ports['output'].neg)
        _in = optimiser.values(self.cool_in)
        return _out / _in


class HeatPump4Pipe(Node):
    """ a 4 pipe heat pump can produce heating and cooling simultaneously"""
    # todo implement this


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
