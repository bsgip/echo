import pyomo.environ as en
from attrs import define, field, validators
from pyomo.core.expr import EqualityExpression

from echo.configuration import Units
from echo.models.agnostic import FlexPort, InputOutputNode, OffOrConstrainedPort
from echo.models.scenario import EchoConcreteModel
from echo.validators import (
    set_output_bounds_validator,
    startup_efficiency_validator,
)


@define
class GasBoilerFixedCOP(InputOutputNode):
    """
    A gas boiler converts gas to heat at a fixed coefficient of performance (COP) where COP = output/input."""

    input_port_unit: Units = Units.JPS
    output_port_unit: Units = Units.KWT

    min_input: float | None = field(default=None, validator=set_output_bounds_validator)

    cop: float = field(
        default=1, validator=[validators.ge(0), startup_efficiency_validator, set_output_bounds_validator]
    )

    startup_cop: float = field(
        default=1, validator=[validators.ge(0), startup_efficiency_validator, set_output_bounds_validator]
    )  # efficiency in startup period

    def __attrs_post_init__(self) -> None:
        super().__attrs_post_init__()

        # Add an input and output node, and create the appropriate transformation object
        self.ports[self.input_port_ref] = OffOrConstrainedPort(
            upper_bound=self.max_input, lower_bound=self.min_input, units=self.input_port_unit
        )
        self.ports[self.output_port_ref] = FlexPort(units=self.output_port_unit)

    def set_ports(self, gas_input_port: OffOrConstrainedPort, thermal_output_port: FlexPort) -> None:
        # Discard existing ports
        self.ports.clear()
        # Add the new ports
        self.input_port_ref = gas_input_port.port_name
        self.output_port_ref = thermal_output_port.port_name
        self.ports[self.input_port_ref] = gas_input_port
        self.ports[self.output_port_ref] = thermal_output_port

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        super().apply_node_constraints(model)

        def node_constraint(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
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
