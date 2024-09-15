from typing import Optional

import pyomo.environ as en
from pydantic import NonNegativeFloat, root_validator

from echo.configuration import Units
from echo.models.agnostic import FixedPort, FlexPort, InputOutputNode, OffOrConstrainedPort
from echo.models.scenario import EchoConcreteModel
from echo.validators import (
    ArrayType,
    set_output_bounds_from_input_bounds_and_cop_and_startup_cop,
    validate_startup_efficiency,
)


class FlexGasPort(FlexPort):
    """A flexible port with flow units of Joules/second"""

    units = Units.JPS


class FixedGasPort(FixedPort):
    """A Fixed port with flow units of Joules/second"""

    units = Units.JPS


class GasBoilerFixedCOP(InputOutputNode):
    """
    A gas boiler converts gas to heat at a fixed coefficient of performance (COP) where COP = output/input."""

    cop: NonNegativeFloat
    input_port_unit = Units.JPS
    output_port_unit = Units.KWT
    startup_cop: NonNegativeFloat  # efficiency in startup period

    check_cop = root_validator(allow_reuse=True)(validate_startup_efficiency)
    set_bounds = root_validator(allow_reuse=True)(set_output_bounds_from_input_bounds_and_cop_and_startup_cop)

    def __init__(self, **data) -> None:
        super().__init__(**data)
        # Add an input and output node, and create the appropriate transformation object
        self.ports[self.input_port_ref] = OffOrConstrainedPort(
            upper_bound=self.max_input, lower_bound=self.min_input, units=self.input_port_unit
        )
        self.ports[self.output_port_ref] = FlexPort(units=self.output_port_unit)

    def set_ports(self, gas_input_port: OffOrConstrainedPort, thermal_output_port: FlexPort):
        # Discard existing ports
        self.ports.clear()
        # Add the new ports
        self.input_port_ref = gas_input_port.port_name
        self.output_port_ref = thermal_output_port.port_name
        self.ports[self.input_port_ref] = gas_input_port
        self.ports[self.output_port_ref] = thermal_output_port

    def apply_node_constraints(self, model: EchoConcreteModel):
        super(GasBoilerFixedCOP, self).apply_node_constraints(model)

        def node_constraint(model: EchoConcreteModel, p, t):
            p_in = getattr(model, self.ports[self.input_port_ref].port_name)
            p_out = getattr(model, self.ports[self.output_port_ref].port_name)
            if p == 0 and t == 0:
                weighted_inputs = p_in[p, t] * self.startup_cop
                weighted_outputs = 0
            else:
                weighted_inputs = p_in[p, t] * self.startup_cop + p_in[p, t - 1] * (self.cop - self.startup_cop)
                # todo decide whether to include past outputs in rule
                weighted_outputs = p_out[p, t - 1] * -0.0
            return p_out[p, t] == (weighted_inputs + weighted_outputs) * -1

        setattr(model, "node_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=node_constraint))


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
    cop: float  # coefficient of performance - determines how much of the input energy is delivered as heating energy
    startup_cop: Optional[float]

    # pyomo vars
    is_on: Optional[str]
    return_t: str = ""
    exit_t: str = ""

    check_eta = root_validator(allow_reuse=True)(validate_startup_efficiency)
    set_output_bounds = root_validator(allow_reuse=True)(set_output_bounds_from_input_bounds_and_cop_and_startup_cop)

    def __init__(self, **data):
        super().__init__(**data)
        self.ports[self.input_port_ref] = OffOrConstrainedPort(
            units=self.input_port_unit, lower_bound=self.min_input, upper_bound=self.max_input
        )
        self.ports[self.output_port_ref] = OffOrConstrainedPort(
            units=self.output_port_unit, lower_bound=self.max_output, upper_bound=self.min_output
        )

        self.return_t = "inlet_temp_" + self.node_name
        self.exit_t = "outlet_temp_" + self.node_name

    def add_node_to_model(self, model: EchoConcreteModel, profile):
        super(TempControlledBoiler, self).add_node_to_model(model, profile)
        # Define exit and return temperature variables and bound these appropriately
        setattr(
            model,
            self.return_t,
            en.Var(model.Expansion, model.Time, initialize=0, bounds=self.return_temp_bounds, domain=en.Reals),
        )
        setattr(
            model,
            self.exit_t,
            en.Var(model.Expansion, model.Time, initialize=0, bounds=self.exit_temp_bounds, domain=en.Reals),
        )

    def apply_node_constraints(self, model: EchoConcreteModel):
        # Retrieve some variables
        input_kw = getattr(model, self.ports[self.input_port_ref].port_name)
        output_kw = getattr(model, self.ports[self.output_port_ref].port_name)

        def constraint2(model: EchoConcreteModel, p, t):
            """return temp at time t - exiting temp at time t == energy removed at t"""
            return (
                getattr(model, self.return_t)[p, t] - getattr(model, self.exit_t)[p, t]
            ) * self.deg_to_kw * self.cop == output_kw[p, t]

        setattr(
            model, "boiler_temp_con2_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=constraint2)
        )

        def constraint3(model: EchoConcreteModel, p, t):
            """exiting temp at time t = return temp at time t + energy added at time t"""
            return (
                input_kw[p, t]
                == (getattr(model, self.exit_t)[p, t] - getattr(model, self.return_t)[p, t]) * self.deg_to_kw
            )

        setattr(
            model, "boiler_temp_con3_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=constraint3)
        )
