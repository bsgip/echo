import enum

import numpy as np

from echo.echo_models import *

""""

    Below Zero assets

"""


class InputOutputNode(Node):
    """
    An input-output node has one input port and one output port.
    A custom transformation can be defined between input and output.
    """
    input_port_unit: int
    output_port_unit: int
    # Optional parameters for controlling input/output port flows
    max_output: Optional[float]  # output might be neg or pos, leave it open
    min_output: Optional[float]
    max_input: Optional[NonNegativeFloat]  # input should generally be non negative
    min_input: Optional[NonNegativeFloat]
    node_rule = NodeRule.Custom


class TimeVaryingPiecewiseIONode(InputOutputNode):
    """
    Node with an input and output port. The relationship between input and output is defined at each time
    interval by an array of input-->output point pairs, which are used to construct a piecewise constraint.
    """
    input_pts: Optional[dict]  # dict where the keys are expansion_planning-time period tuple, and value is input pt array
    output_pts: Optional[dict]  # dict where the keys are expansion_planning-time period tuple, and value is output pt array

    # These values are automatically calculated by the 'set_bounds_from_piecewise_pts' validator
    input_ub: float = None
    input_lb: float = None
    output_ub: float = None
    output_lb: float = None

    piecewise_check = root_validator(allow_reuse=True)(validate_piecewise_arrays)  # validate input/output pts
    populate_bounds = root_validator(allow_reuse=True)(
        set_bounds_from_piecewise_pts)  # set attributes input_ub, input_lb, output_ub, output_lb from input pts/output pts

    def __init__(self, **data):
        super().__init__(**data)
        # Create an input port and an outport port with the correct units
        self.ports['input'] = FlexPort(units=self.input_port_unit)
        self.ports['output'] = FlexPort(units=self.output_port_unit)

    def verify_node(self):
        assert self.input_pts is not None, 'No input points defined'
        assert self.output_pts is not None, 'No output points defined'

    def initialise_node(self, model):
        super(TimeVaryingPiecewiseIONode, self).initialise_node(model)
        # Bound input and output port variables, otherwise piecewise constraint will fail
        set_float_var_bounds(model=model, var_name=self.ports['input'].port_name, ub=self.input_ub, lb=self.input_lb)
        set_float_var_bounds(model=model, var_name=self.ports['output'].port_name, ub=self.output_ub, lb=self.output_lb)

    def apply_node_constraints(self, model):
        xvar = getattr(model, self.ports['input'].port_name)
        yvar = getattr(model, self.ports['output'].port_name)
        xdata = self.input_pts
        ydata = self.output_pts

        con_name = 'piecewise_con_' + self.node_name
        setattr(model, con_name, en.Piecewise(model.Expansion, model.Time,
                                              yvar,
                                              xvar,
                                              pw_pts=xdata, pw_constr_type='EQ', f_rule=ydata, pw_repn='SOS2'))


class SinglePiecewiseIONode(TimeVaryingPiecewiseIONode):
    """
    The relationship between input and output for all time intervals
    is given by an array of input-->output point pairs, which are used to construct a piecewise constraint.
    """

    def add_input_pts(self, array, time_periods, expansion_periods=1):
        """ Tiles input points across time and expansion periods."""
        self.input_pts = populate_values_across_time_and_expansion_indices(array, time_periods, expansion_periods)

    def add_output_pts(self, array, time_periods, expansion_periods=1):
        """ Tiles output points across time and expansion periods."""
        self.output_pts = populate_values_across_time_and_expansion_indices(array, time_periods, expansion_periods)


class SimpleChiller(SinglePiecewiseIONode):
    """
    A chiller converts an electrical input (+ve because it is an electrical sink) to a thermal cooling output (+ve because it is a heat sink).
    A simple chiller is an input/output piecewise node, with a single set of input/output breakpoints used for all time periods.
    """
    input_port_unit = Units.KW
    output_port_unit = Units.KWT


class ParametrisedChiller(TimeVaryingPiecewiseIONode):
    """
    A chiller converts an electrical input (+ve because it is an electrical sink) to a thermal cooling output (+ve because it is a heat sink).
    A temperature
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
        # todo not set up for expansion expansion_planning
        _input = optimiser.values(self.ports['input'].port_name)
        _output = optimiser.values(self.ports['output'].port_name)
        cop = np.zeros(len(_input))
        for i in range(len(_input)):
            cop[i] = _output[i] / _input[i] * -1
        return cop


""" 
Thermal models
"""


class ThermalNode(Node):
    """
    A thermal node has an internal temperature variable, which can be bounded.
    It can have any number of ports for heating (importing) or cooling (export).
    All the ports are related to temp by an energy balance constraint.
    """
    node_rule = NodeRule.Custom
    temp_ub: dict  # Upper bound of acceptable temperature for each time interval, formatted as dict with expansion-time keys
    temp_lb: dict  # Lower bound of acceptable temperature for each time interval, formatted as dict with expansion-time keys
    external_temp: dict  # External (ambient) temp, formatted as dict with expansion-time keys
    loss_factor: Optional[float] = 0  # Losses due to ambient temp being lower than internal temp
    gain_factor: Optional[float] = 0  # Free gains due to ambient temp being higher than internal temp
    temp_to_energy_coef: float = 1  # Conversion factor * temp change = added energy
    initial_internal_temp: float = 0  # initial internal temperature

    # Pyomo vars/params
    internal_temp: Optional[str]
    is_gain: Optional[str]
    losses: Optional[str]
    gains: Optional[str]

    def __init__(self, **data):
        super().__init__(**data)
        self.internal_temp = 'internal_temp_' + self.node_name
        self.is_gain = 'is_gain_' + self.node_name
        self.losses = 'losses_' + self.node_name
        self.gains = 'gains_' + self.node_name

    def initialise_node(self, model):
        super(ThermalNode, self).initialise_node(model)
        self.create_and_bound_temp_vars(model)
        self.loss_and_gain_constraints_and_variables(model)
        self.apply_energy_balance_constraint(model)

    def create_and_bound_temp_vars(self, model):
        # Create temperature variable
        setattr(model, self.internal_temp, en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))
        # Bound temp variable to be within range
        set_var_bounds_from_dict(var=getattr(model, self.internal_temp), ub=self.temp_ub, lb=self.temp_lb)

    def loss_and_gain_constraints_and_variables(self, model):
        # Create variable for losses and gains
        setattr(model, self.losses, en.Var(model.Expansion, model.Time, domain=en.NonPositiveReals))
        setattr(model, self.gains, en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))
        setattr(model, self.is_gain, en.Var(model.Expansion, model.Time, domain=en.Binary))

        # Apply constraints on loss and gain variables
        def loss_gain_sum_constraint(model, p, t):
            """ Losses + gains must equal the temperature difference between ambient and internal"""
            return getattr(model, self.losses)[p, t] + getattr(model, self.gains)[p, t] == \
                   self.external_temp[p, t] - getattr(model, self.internal_temp)[p, t]

        setattr(model, 'loss_gain_con1_' + self.node_name,
                en.Constraint(model.Expansion, model.Time, rule=loss_gain_sum_constraint))

        def loss_or_gain1(model, p, t):
            """ Gains can only be non-zero if is_gain = 1"""
            return getattr(model, self.gains)[p, t] <= getattr(model, self.is_gain)[p, t] * model.bigM

        setattr(model, 'loss_gain_con2_' + self.node_name,
                en.Constraint(model.Expansion, model.Time, rule=loss_or_gain1))

        def loss_or_gain2(model, p, t):
            """ Losses can only be non-zero if is_gain = 0 """
            return getattr(model, self.losses)[p, t] >= (getattr(model, self.is_gain)[p, t] - 1) * model.bigM

        setattr(model, 'loss_gain_con3_' + self.node_name,
                en.Constraint(model.Expansion, model.Time, rule=loss_or_gain2))

    def apply_energy_balance_constraint(self, model):
        # Constraint relating internal, ambient temp, heat in, heat out, losses, and gains
        def rule1(model, p, t):
            thermal_kw = 0
            for v in self.ports.values():
                thermal_kw += getattr(model, v.port_name)[p, t]  # sum together our thermal ports

            internal_temp = getattr(model, self.internal_temp)
            loss = getattr(model, self.losses)[p, t] * self.loss_factor
            gain = getattr(model, self.gains)[p, t] * self.gain_factor

            if p == 0 and t == 0:
                return thermal_kw + loss + gain == (
                        internal_temp[p, t] - self.initial_internal_temp) * self.temp_to_energy_coef
            else:
                temp_diff = internal_temp[p, t] - internal_temp[p, t - 1]
                return thermal_kw + loss + gain == temp_diff * self.temp_to_energy_coef

        setattr(model, 'internal_temp_con_' + self.node_name, en.Constraint(model.Expansion, model.Time, rule=rule1))


class ThermalPort(FlexPort):
    """ Flexible thermal port, +ve if importing heat, -ve if exporting heat."""
    units = Units.KWT


class FlexHeatSource(ThermalPort):
    flows = Flows.Export


class FlexHeatSink(ThermalPort):
    flows = Flows.Import


class FlexCoolingSource(ThermalPort):
    flows = Flows.Import


class FlexCoolingSink(ThermalPort):
    flows = Flows.Export


class FixedThermalPort(FixedPort):
    """ Fixed thermal port, +ve if importing heat, -ve if exporting heat."""
    units = Units.KWT


class ThermalStorage(Storage):
    # todo finish implementing
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



class HeatPump(Node):
    """
    A heat pump is input output node, where input is an electrical port, and either one or two output thermal ports.
    It can only do heating or cooling, it cannot do both simultaneously.
    The conversion of input electrical energy to heating or cooling output depends on provided coefficients of performance (cop) time series data.
    """
    node_rule = NodeRule.Custom
    heating_cop_time_series: dict  # Formatted dict of heating COPs per time period
    cooling_cop_time_series: dict  # Formatted dict of cooling COPs per time period

    # pyomo vars/params
    heating_cop: Optional[str]
    cooling_cop: Optional[str]
    heat_in: Optional[str]
    cool_in: Optional[str]

    def __init__(self, **data):
        super().__init__(**data)
        # Create input and output ports
        self.ports['input'] = FlexPortImport(units=Units.KW)  # Heat pump has electrical input port

        # Naming variables
        self.heating_cop = 'heating_cop_' + self.node_name
        self.cooling_cop = 'cooling_cop_' + self.node_name
        self.heat_in = 'heat_in_' + self.node_name
        self.cool_in = 'cool_in_' + self.node_name

    def initialise_node(self, model):
        super(HeatPump, self).initialise_node(model)

        # Create variables for attributing the input to either heating or cooling
        setattr(model, self.heat_in, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
        setattr(model, self.cool_in, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))

        # Create params for heating and cooling coefficients of performance
        setattr(model, self.heating_cop, en.Param(model.Expansion, model.Time, initialize=self.heating_cop_time_series,
                                                  domain=en.NonNegativeReals))
        setattr(model, self.cooling_cop, en.Param(model.Expansion, model.Time, initialize=self.cooling_cop_time_series,
                                                  domain=en.NonNegativeReals))

    def apply_only_heat_or_cool_constraints(self, model, binary_var):
        is_cooling = getattr(model, binary_var)  # binary var for whether we are cooling
        p_in = getattr(model, self.ports['input'].port_name)  # input electrical power

        def only_heat_or_cool1(model, p, t):
            """ Can only have input used for heating if is_cooling = 0"""
            return getattr(model, self.heat_in)[p, t] <= (1 - is_cooling[p, t]) * model.bigM

        setattr(model, 'only_heat_or_cool1_' + self.node_name,
                en.Constraint(model.Expansion, model.Time, rule=only_heat_or_cool1))

        def only_heat_or_cool2(model, p, t):
            """ Can only have input used for cooling if is_cooling = 1"""
            return getattr(model, self.cool_in)[p, t] <= is_cooling[p, t] * model.bigM

        setattr(model, 'only_heat_or_cool2_' + self.node_name,
                en.Constraint(model.Expansion, model.Time, rule=only_heat_or_cool2))

        def sum_rule(model, p, t):
            """ Input used for heating and input used for cooling must sum to total input"""
            return p_in[p, t] == getattr(model, self.heat_in)[p, t] + getattr(model, self.cool_in)[p, t]

        setattr(model, 'sum_heat_cool_' + self.node_name, en.Constraint(model.Expansion, model.Time, rule=sum_rule))

    def apply_node_transformation_constraints(self, model, heating_out_var, cooling_out_var):
        heat_out = getattr(model, heating_out_var)  # heating delivered
        cool_out = getattr(model, cooling_out_var)  # cooling delivered
        heating_cop = getattr(model, self.heating_cop)
        cooling_cop = getattr(model, self.cooling_cop)

        def heating_output_rule(model, p, t):
            """ Heat out = heat_in * heating cop * -1"""
            return heat_out[p, t] == getattr(model, self.heat_in)[p, t] * heating_cop[p, t] * -1

        def cooling_output_rule(model, p, t):
            """ Cool out = cool_in * cooling cop"""
            return cool_out[p, t] == getattr(model, self.cool_in)[p, t] * cooling_cop[p, t]

        setattr(model, 'heat_con_' + self.node_name,
                en.Constraint(model.Expansion, model.Time, rule=heating_output_rule))
        setattr(model, 'cool_con_' + self.node_name,
                en.Constraint(model.Expansion, model.Time, rule=cooling_output_rule))

    def get_heating_cop(self, optimiser):
        """ Returns the heating cop"""
        _out = optimiser.values(self.ports['output'].pos)
        _in = optimiser.values(self.heat_in)
        return _out / _in

    def get_cooling_cop(self, optimiser):
        """ Returns the cooling cop"""
        _out = optimiser.values(self.ports['output'].neg)
        _in = optimiser.values(self.cool_in)
        return _out / _in


class HeatPumpSingleOutput(HeatPump):
    """
    Heat pump with a single output port for bidirectional heating/cooling.
    Can be used to connect to a thermal load that has heating and cooling.
    """

    def __init__(self, **data):
        super().__init__(**data)
        # Create output port
        self.ports['output'] = FlexPort(units=Units.KWT)

    def initialise_node(self, model):
        super(HeatPumpSingleOutput, self).initialise_node(model)
        # Split output port into +ve and -ve components. +ve component will be cooling, -ve component will be heating
        self.ports['output'].constrain_pos_neg(model)

    def apply_node_constraints(self, model):
        p_out = self.ports['output']
        self.apply_only_heat_or_cool_constraints(model, binary_var=p_out.is_pos)
        self.apply_node_transformation_constraints(model, heating_out_var=p_out.neg, cooling_out_var=p_out.pos)


class HeatPumpDualOutput(HeatPump):
    """
    Heat pump with separate output ports for heating and cooling.
    Can be used to connect to separate heating and cooling nodes.
    """
    def __init__(self, **data):
        super().__init__(**data)
        # Create output port
        self.ports['heating'] = FlexPortExport(units=Units.KWT)
        self.ports['cooling'] = FlexPortImport(units=Units.KWT)

    def initialise_node(self, model):
        super(HeatPumpDualOutput, self).initialise_node(model)
        self.ports['cooling'].constrain_pos_neg(model)  # need to do this so we have a binary variable for the constraints

    def apply_node_constraints(self, model):
        h_out = self.ports['heating']
        c_out = self.ports['cooling']
        self.apply_only_heat_or_cool_constraints(model, binary_var=c_out.is_pos)
        self.apply_node_transformation_constraints(model, heating_out_var=h_out.port_name, cooling_out_var=c_out.port_name)


class HeatPump4Pipe(Node):
    """ a 4 pipe heat pump can produce heating and cooling simultaneously"""
    # todo implement this


"""
Gas models
"""


class GasPort(FlexPort):
    """ A flexible port with flow units of Joules/second"""

    def __init__(self):
        super(GasPort, self).__init__()
        self.units = Units.JPS


class FixedGasPort(GasPort):
    """ Same as gas port, but fixed value. """

    def __init__(self):
        super(FixedGasPort, self).__init__()
        self.opt_type = OptimisationType.Parameter


class GasBoilerFixedCOP(InputOutputNode):
    """
    A gas boiler converts gas to heat at a fixed coefficient of performance (COP) where COP = output/input."""
    cop: NonNegativeFloat
    input_port_unit = Units.JPS
    output_port_unit = Units.KWT
    startup_eta: NonNegativeFloat  # efficiency in startup period

    check_eta = root_validator(allow_reuse=True)(validate_startup_efficiency)
    set_bounds = root_validator(allow_reuse=True)(set_output_bounds_from_input_bounds_and_cop_and_startup_eta)

    def __init__(self, **data) -> None:
        super().__init__(**data)
        # Add an input and output node, and create the appropriate transformation object
        self.ports['input'] = OffOrConstrainedPort(upper_bound=self.max_input, lower_bound=self.min_input,
                                                   units=self.input_port_unit)
        self.ports['output'] = FlexPort(units=self.output_port_unit)

    def apply_node_constraints(self, model):
        super(GasBoilerFixedCOP, self).apply_node_constraints(model)

        def node_constraint(model, p, t):
            p_in = getattr(model, self.ports['input'].port_name)
            p_out = getattr(model, self.ports['output'].port_name)
            if p == 0 and t == 0:
                weighted_inputs = p_in[p, t] * self.startup_eta
                weighted_outputs = 0
            else:
                weighted_inputs = (p_in[p, t] * self.startup_eta + p_in[p, t - 1] * (1 - self.startup_eta)) * self.cop
                # todo decide whether to include past outputs in rule
                weighted_outputs = p_out[p, t - 1] * -0.0
            return p_out[p, t] == (weighted_inputs + weighted_outputs) * -1

        setattr(model, 'node_con_' + self.node_name, en.Constraint(model.Expansion, model.Time, rule=node_constraint))


class ModulatingBoiler(InputOutputNode):
    # todo finish implementing this - this should be like the chiller
    part_load_efficiencies: ArrayType


class TempControlledBoiler(InputOutputNode):
    """
    A temp controlled boiler has an input and output port.
    It has two internal temperature variables, one for exiting water temp and one for returning water temp.
    """
    input_port_unit = Units.JPS
    output_port_unit = Units.KWT
    max_input: float
    min_input: float
    exit_temp_bounds: tuple = (75, 80)
    return_temp_bounds: tuple = (50, 80)
    deg_to_kw: float  # factor for converting a temperature difference to kW required to achieve that delta T
    cop: float  # coefficient of performance, which determines how much of the input energy is delivered as heating energy
    startup_eta: Optional[float]

    # pyomo vars
    is_on: Optional[str]
    return_t: Optional[str]
    exit_t: Optional[str]

    check_eta = root_validator(allow_reuse=True)(validate_startup_efficiency)
    set_output_bounds = root_validator(allow_reuse=True)(set_output_bounds_from_input_bounds_and_cop_and_startup_eta)

    def __init__(self, **data):
        super().__init__(**data)
        self.ports['input'] = OffOrConstrainedPort(units=self.input_port_unit, lower_bound=self.min_input,
                                                   upper_bound=self.max_input)
        self.ports['output'] = OffOrConstrainedPort(units=self.output_port_unit, lower_bound=self.max_output,
                                                    upper_bound=self.min_output)

        self.return_t = 'inlet_temp_' + self.node_name
        self.exit_t = 'outlet_temp_' + self.node_name

    def initialise_node(self, model):
        super(TempControlledBoiler, self).initialise_node(model)
        # Define exit and return temperature variables and bound these appropriately
        setattr(model, self.return_t,
                en.Var(model.Expansion, model.Time, initialize=0, bounds=self.return_temp_bounds, domain=en.Reals))
        setattr(model, self.exit_t,
                en.Var(model.Expansion, model.Time, initialize=0, bounds=self.exit_temp_bounds, domain=en.Reals))

    def apply_node_constraints(self, model):
        # Retrieve some variables
        input_kw = getattr(model, self.ports['input'].port_name)
        output_kw = getattr(model, self.ports['output'].port_name)

        def constraint2(model, p, t):
            """ return temp at time t - exiting temp at time t == energy removed at t"""
            return (getattr(model, self.return_t)[p, t] - getattr(model, self.exit_t)[
                p, t]) * self.deg_to_kw * self.cop == output_kw[p, t]

        setattr(model, 'boiler_temp_con2_' + self.node_name,
                en.Constraint(model.Expansion, model.Time, rule=constraint2))

        def constraint3(model, p, t):
            """ exiting temp at time t = return temp at time t + energy added at time t"""
            return input_kw[p, t] == (
                    getattr(model, self.exit_t)[p, t] - getattr(model, self.return_t)[p, t]) * self.deg_to_kw

        setattr(model, 'boiler_temp_con3_' + self.node_name,
                en.Constraint(model.Expansion, model.Time, rule=constraint3))


""" 
Control system models 
"""


class TimeDelayNode(InputOutputNode):
    """ A time delay node is an input-output node that implements a fixed delay between input and output."""
    time_delay: int  # number of time intervals delay between input and output
    node_rule = NodeRule.Custom

    def __init__(self, **data):
        super().__init__(**data)
        self.ports['input'] = FlexPortImport(units=self.input_port_unit)
        self.ports['output'] = FlexPortExport(units=self.output_port_unit)

    def apply_node_constraints(self, model):

        def time_delay_rule(model, p, t):
            """ This is a modified tellegen rule,
            where the sum=0 applies over staggered time periods according to the time delay """
            a = getattr(model, self.ports['input'].port_name)
            b = getattr(model, self.ports['output'].port_name)
            if t < self.time_delay:
                return b[p, t] == 0
            else:
                return b[p, t] == a[p, int(t - self.time_delay)] * -1

        con_name = 'time_delay_con_' + self.node_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=time_delay_rule))
