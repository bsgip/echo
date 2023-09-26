from typing import Optional

import numpy as np
import pyomo.environ as en

from echo.configuration import Flows, NodeRule, Units
from echo.echo_validators import ArrayType
from echo.models.agnostic import (
    FixedPort,
    FlexPort,
    FlexSink,
    FlexSource,
    SinglePiecewiseIONode,
    Sink,
    Source,
    TimeVaryingPiecewiseIONode,
)
from echo.models.base import Node
from echo.models.scenario import EchoConcreteModel
from echo.utils import (
    create_input_output_pts_from_coefficients,
    set_var_bounds_from_dict,
)


class SimpleChiller(SinglePiecewiseIONode):
    """
    A chiller converts an electrical input (+ve because it is an electrical sink) to a thermal cooling output
    (+ve because it is a heat sink).

    A simple chiller is an input/output piecewise node, with a single set of input/output breakpoints used for
    all time periods.
    """

    input_port_unit = Units.KW
    output_port_unit = Units.KWT


class ParameterisedChiller(TimeVaryingPiecewiseIONode):
    """
    A chiller converts an electrical input (+ve because it is an electrical sink) to a thermal cooling output
    (+ve because it is a heat sink).
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
            assert self.input_coefficients is not None, "If temp data is provided, temp coefficients are required."
            assert self.temp_coefficients is not None, "If temp data is provided, input coefficients are required."
            self.generate_input_output_pts_from_coefficients()

    def generate_input_output_pts_from_coefficients(self):
        xpts = np.linspace(0, self.max_input, self.n_pts)
        time_periods = len(self.external_temp)
        self.input_pts, self.output_pts = create_input_output_pts_from_coefficients(
            self.temp_coefficients, self.input_coefficients, self.external_temp, xpts, time_periods
        )

    def get_cop(self, optimiser):
        """Returns the coefficient of performance (output/input)"""
        # todo not set up for expansion planning
        _input = optimiser.values(self.ports["input"].port_name)
        _output = optimiser.values(self.ports["output"].port_name)
        cop = np.zeros(len(_input))
        for i in range(len(_input)):
            cop[i] = _output[i] / _input[i] * -1
        return cop


class ThermalNode(Node):
    """
    A thermal node has an internal temperature variable, which can be bounded.
    It can have any number of ports for heating (importing) or cooling (export).
    All the ports are related to temp by an energy balance constraint.
    """

    node_rule = NodeRule.Custom
    temp_ub: dict  # Upper bound of acceptable temperature for each time interval: dict with expansion-time keys
    temp_lb: dict  # Lower bound of acceptable temperature for each time interval: dict with expansion-time keys
    external_temp: dict  # External (ambient) temp, formatted as dict with expansion-time keys
    loss_factor: float = 0  # Losses due to ambient temp being lower than internal temp
    gain_factor: float = 0  # Free gains due to ambient temp being higher than internal temp
    temp_to_energy_coef: float = 1  # Conversion factor * temp change = added energy
    initial_internal_temp: float = 0  # initial internal temperature

    # Pyomo vars/params
    internal_temp: str
    is_gain: str
    losses: str
    gains: str

    def __init__(self, **data):
        super().__init__(**data)
        self.internal_temp = "internal_temp_" + self.node_name
        self.is_gain = "is_gain_" + self.node_name
        self.losses = "losses_" + self.node_name
        self.gains = "gains_" + self.node_name

    def initialise_node(self, model: EchoConcreteModel, profile):
        super(ThermalNode, self).initialise_node(model, profile)
        self.create_and_bound_temp_vars(model)
        self.loss_and_gain_constraints_and_variables(model)
        self.apply_energy_balance_constraint(model)

    def create_and_bound_temp_vars(self, model: EchoConcreteModel):
        # Create temperature variable
        setattr(model, self.internal_temp, en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))
        # Bound temp variable to be within range
        set_var_bounds_from_dict(var=getattr(model, self.internal_temp), ub=self.temp_ub, lb=self.temp_lb)

    def loss_and_gain_constraints_and_variables(self, model: EchoConcreteModel):
        # Create variable for losses and gains
        setattr(model, self.losses, en.Var(model.Expansion, model.Time, domain=en.NonPositiveReals))
        setattr(model, self.gains, en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))
        setattr(model, self.is_gain, en.Var(model.Expansion, model.Time, domain=en.Binary))

        # Apply constraints on loss and gain variables
        def loss_gain_sum_constraint(model: EchoConcreteModel, p, t):
            """Losses + gains must equal the temperature difference between ambient and internal"""
            return (
                getattr(model, self.losses)[p, t] + getattr(model, self.gains)[p, t]
                == self.external_temp[p, t] - getattr(model, self.internal_temp)[p, t]
            )

        setattr(
            model,
            "loss_gain_con1_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=loss_gain_sum_constraint),
        )

        def loss_or_gain1(model: EchoConcreteModel, p, t):
            """Gains can only be non-zero if is_gain = 1"""
            return getattr(model, self.gains)[p, t] <= getattr(model, self.is_gain)[p, t] * model.bigM

        setattr(
            model, "loss_gain_con2_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=loss_or_gain1)
        )

        def loss_or_gain2(model: EchoConcreteModel, p, t):
            """Losses can only be non-zero if is_gain = 0"""
            return getattr(model, self.losses)[p, t] >= (getattr(model, self.is_gain)[p, t] - 1) * model.bigM

        setattr(
            model, "loss_gain_con3_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=loss_or_gain2)
        )

    def apply_energy_balance_constraint(self, model: EchoConcreteModel):
        # Constraint relating internal, ambient temp, heat in, heat out, losses, and gains
        def rule1(model: EchoConcreteModel, p, t):
            thermal_kw = 0
            for v in self.ports.values():
                thermal_kw += getattr(model, v.port_name)[p, t]  # sum together our thermal ports

            internal_temp = getattr(model, self.internal_temp)
            loss = getattr(model, self.losses)[p, t] * self.loss_factor
            gain = getattr(model, self.gains)[p, t] * self.gain_factor

            if p == 0 and t == 0:
                return (
                    thermal_kw + loss + gain
                    == (internal_temp[p, t] - self.initial_internal_temp) * self.temp_to_energy_coef
                )
            else:
                temp_diff = internal_temp[p, t] - internal_temp[p, t - 1]
                return thermal_kw + loss + gain == temp_diff * self.temp_to_energy_coef

        setattr(model, "internal_temp_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=rule1))


class ThermalPort(FlexPort):
    """Flexible thermal port, +ve if importing heat, -ve if exporting heat."""

    units = Units.KWT


class FlexHeatSource(ThermalPort):
    flows = Flows.Export


class FlexCoolingSource(ThermalPort):
    flows = Flows.Import


class FlexHeatSink(ThermalPort):
    flows = Flows.Import


class FlexCoolingSink(ThermalPort):
    flows = Flows.Export


class HeatSource(Source):
    units = Units.KWT


class HeatSink(Sink):
    units = Units.KWT


class FixedThermalPort(FixedPort):
    """Fixed thermal port, +ve if importing heat, -ve if exporting heat."""

    units = Units.KWT


class HeatPump(Node):
    """
    A heat pump is input output node, where input is an electrical port, and either one or two output thermal ports.
    It can only do heating or cooling, it cannot do both simultaneously.
    The conversion of input electrical energy to heating or cooling output depends on provided coefficients of
    performance (cop) time series data.
    """

    node_rule = NodeRule.Custom
    heating_cop_time_series: dict  # Formatted dict of heating COPs per time period
    cooling_cop_time_series: dict  # Formatted dict of cooling COPs per time period

    # pyomo vars/params
    heating_cop: str
    cooling_cop: str
    heat_in: str
    cool_in: str

    def __init__(self, **data):
        super().__init__(**data)
        # Create input and output ports
        self.ports["input"] = FlexSink(units=Units.KW)  # Heat pump has electrical input port

        # Naming variables
        self.heating_cop = "heating_cop_" + self.node_name
        self.cooling_cop = "cooling_cop_" + self.node_name
        self.heat_in = "heat_in_" + self.node_name
        self.cool_in = "cool_in_" + self.node_name

    def initialise_node(self, model: EchoConcreteModel, profile):
        super(HeatPump, self).initialise_node(model, profile)

        # Create variables for attributing the input to either heating or cooling
        setattr(model, self.heat_in, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
        setattr(model, self.cool_in, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))

        # Create params for heating and cooling coefficients of performance
        setattr(
            model,
            self.heating_cop,
            en.Param(model.Expansion, model.Time, initialize=self.heating_cop_time_series, domain=en.NonNegativeReals),
        )
        setattr(
            model,
            self.cooling_cop,
            en.Param(model.Expansion, model.Time, initialize=self.cooling_cop_time_series, domain=en.NonNegativeReals),
        )

    def apply_only_heat_or_cool_constraints(self, model: EchoConcreteModel, binary_var):
        is_cooling = getattr(model, binary_var)  # binary var for whether we are cooling
        p_in = getattr(model, self.ports["input"].port_name)  # input electrical power

        def only_heat_or_cool1(model: EchoConcreteModel, p, t):
            """Can only have input used for heating if is_cooling = 0"""
            return getattr(model, self.heat_in)[p, t] <= (1 - is_cooling[p, t]) * model.bigM

        setattr(
            model,
            "only_heat_or_cool1_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=only_heat_or_cool1),
        )

        def only_heat_or_cool2(model: EchoConcreteModel, p, t):
            """Can only have input used for cooling if is_cooling = 1"""
            return getattr(model, self.cool_in)[p, t] <= is_cooling[p, t] * model.bigM

        setattr(
            model,
            "only_heat_or_cool2_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=only_heat_or_cool2),
        )

        def sum_rule(model: EchoConcreteModel, p, t):
            """Input used for heating and input used for cooling must sum to total input"""
            return p_in[p, t] == getattr(model, self.heat_in)[p, t] + getattr(model, self.cool_in)[p, t]

        setattr(model, "sum_heat_cool_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=sum_rule))

    def apply_node_transformation_constraints(self, model: EchoConcreteModel, heating_out_var, cooling_out_var):
        heat_out = getattr(model, heating_out_var)  # heating delivered
        cool_out = getattr(model, cooling_out_var)  # cooling delivered
        heating_cop = getattr(model, self.heating_cop)
        cooling_cop = getattr(model, self.cooling_cop)

        def heating_output_rule(model: EchoConcreteModel, p, t):
            """Heat out = heat_in * heating cop * -1"""
            return heat_out[p, t] == getattr(model, self.heat_in)[p, t] * heating_cop[p, t] * -1

        def cooling_output_rule(model: EchoConcreteModel, p, t):
            """Cool out = cool_in * cooling cop"""
            return cool_out[p, t] == getattr(model, self.cool_in)[p, t] * cooling_cop[p, t]

        setattr(
            model, "heat_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=heating_output_rule)
        )
        setattr(
            model, "cool_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=cooling_output_rule)
        )

    def get_heating_cop(self, optimiser):
        """Returns the heating cop"""
        _out = optimiser.values(self.ports["output"].pos)
        _in = optimiser.values(self.heat_in)
        return _out / _in

    def get_cooling_cop(self, optimiser):
        """Returns the cooling cop"""
        _out = optimiser.values(self.ports["output"].neg)
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
        self.ports["output"] = FlexPort(units=Units.KWT)

    def initialise_node(self, model: EchoConcreteModel, profile):
        super(HeatPumpSingleOutput, self).initialise_node(model, profile)
        # Split output port into +ve and -ve components. +ve component will be cooling, -ve component will be heating
        self.ports["output"].constrain_pos_neg(model)

    def apply_node_constraints(self, model: EchoConcreteModel):
        p_out = self.ports["output"]
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
        self.ports["heating"] = FlexSource(units=Units.KWT)
        self.ports["cooling"] = FlexSink(units=Units.KWT)

    def initialise_node(self, model: EchoConcreteModel, profile):
        super(HeatPumpDualOutput, self).initialise_node(model, profile)
        self.ports["cooling"].constrain_pos_neg(
            model
        )  # need to do this so we have a binary variable for the constraints

    def apply_node_constraints(self, model: EchoConcreteModel):
        h_out = self.ports["heating"]
        c_out = self.ports["cooling"]
        self.apply_only_heat_or_cool_constraints(model, binary_var=c_out.is_pos)
        self.apply_node_transformation_constraints(
            model, heating_out_var=h_out.port_name, cooling_out_var=c_out.port_name
        )


class HeatPump4Pipe(Node):
    """a 4 pipe heat pump can produce heating and cooling simultaneously"""

    # todo implement this
