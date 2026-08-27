import pandas as pd
import pyomo.environ as en
from pyomo.core.expr import InequalityExpression

from echo.configuration import Units
from echo.models.agnostic.flex import FlexSink, FlexSource
from echo.models.agnostic.tellegen.base import TellegenNode
from echo.models.scenario import EchoConcreteModel


class ThreeWayValveNode(TellegenNode):
    """A node that implements a Tellegen constraint requiring that port values sum to zero.

    ThreeWayValveNode node implements additional constraints between ports,
    there is one input (import) port and two output (export) ports.
    At each time the flow is allowed through only one output port.
    """

    units: Units
    input_port_name: str = "input_port"
    output_port_name_1: str = "output_port_1"
    output_port_name_2: str = "output_port_2"

    # Tuple of two port names on the Node, non-zero flow through only one of the port allowed at any time
    mutually_exclusive_port_flows: tuple[str, str] = None

    @property
    def binary_variable_flow_through_mutually_exclusive_port_1(self) -> str:
        return f"binary_variable_flow_through_mutually_exclusive_{self.output_port_name_1}_{self.node_name}"

    @property
    def constraint_neg_flow_mutually_exclusive_port_1(self) -> str:
        return f"constraint_neg_flow_mutually_exclusive_{self.output_port_name_1}_{self.node_name}"

    @property
    def constraint_pos_flow_mutually_exclusive_port_1(self) -> str:
        return f"constraint_pos_flow_mutually_exclusive_{self.output_port_name_1}_{self.node_name}"

    @property
    def constraint_neg_flow_mutually_exclusive_port_2(self) -> str:
        return f"constraint_neg_flow_mutually_exclusive_{self.output_port_name_2}_{self.node_name}"

    @property
    def constraint_pos_flow_mutually_exclusive_port_2(self) -> str:
        return f"constraint_pos_flow_mutually_exclusive_port_{self.output_port_name_2}_{self.node_name}"

    def __init__(self, **data) -> None:
        super().__init__(**data)
        self.create_ports()

    def create_ports(self) -> None:
        # Create input and output ports
        self.ports[self.input_port_name] = FlexSink(units=self.units)
        self.ports[self.output_port_name_1] = FlexSource(units=self.units)
        self.ports[self.output_port_name_2] = FlexSource(units=self.units)

    def set_ports(
        self,
        input_port: FlexSink,
        output_port_1: FlexSource,
        output_port_2: FlexSource,
    ) -> None:
        # Discard existing ports
        self.ports.clear()

        # Update port references
        self.input_port_name = input_port.port_name
        self.output_port_name_1 = output_port_1.port_name
        self.output_port_name_2 = output_port_2.port_name

        # Add the new ports
        self.ports[self.input_port_name] = input_port
        self.ports[self.output_port_name_1] = output_port_1
        self.ports[self.output_port_name_2] = output_port_2

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        # Load coefficient of performance values from profile (if provided by reference)
        setattr(
            model,
            self.binary_variable_flow_through_mutually_exclusive_port_1,
            en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary),
        )
        super().add_node_to_model(model, profile)

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        super().apply_node_constraints(model)
        self._apply_mutually_exclusive_port_flow_constraint(model)

    def _apply_mutually_exclusive_port_flow_constraint(self, model: EchoConcreteModel) -> None:

        _port_name_1 = self.ports.get(self.output_port_name_1).port_name
        _port_name_2 = self.ports.get(self.output_port_name_2).port_name
        _binary_var = getattr(model, self.binary_variable_flow_through_mutually_exclusive_port_1)

        def mutual_exclusivity_rule_11(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            """When _binary_var is 0, flow through output port 1 is constrained to be zero"""
            return _binary_var[p, t] * -1 * model.big_m <= getattr(model, _port_name_1)[p, t]

        con_name = self.constraint_neg_flow_mutually_exclusive_port_1
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=mutual_exclusivity_rule_11))

        def mutual_exclusivity_rule_12(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            """When _binary_var is 0, flow through output port 1 is constrained to be zero"""
            return getattr(model, _port_name_1)[p, t] <= _binary_var[p, t] * model.big_m

        con_name = self.constraint_pos_flow_mutually_exclusive_port_1
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=mutual_exclusivity_rule_12))

        def mutual_exclusivity_rule_21(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            """When _binary_var is 1, flow through output port 2 is constrained to be zero"""
            return (1 - _binary_var[p, t]) * -1 * model.big_m <= getattr(model, _port_name_2)[p, t]

        con_name = self.constraint_neg_flow_mutually_exclusive_port_2
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=mutual_exclusivity_rule_21))

        def mutual_exclusivity_rule_22(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            """When _binary_var is 1, flow through output port 2 is constrained to be zero"""
            return getattr(model, _port_name_2)[p, t] <= (1 - _binary_var[p, t]) * model.big_m

        con_name = self.constraint_pos_flow_mutually_exclusive_port_2
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=mutual_exclusivity_rule_22))
