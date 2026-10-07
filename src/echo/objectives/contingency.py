import pyomo.environ as en
from attrs import define, field, validators
from pyomo.core.expr import InequalityExpression

from echo.models.agnostic import Storage
from echo.models.base import Path
from echo.models.scenario import EchoConcreteModel
from echo.objectives.base import Objective


@define
class Contingency(Objective):
    component: Path = field(kw_only=True)


@define
class ContingencyNegative(Contingency):
    """FCAS Raise"""

    duration: float = field(
        kw_only=True, validator=validators.gt(0)
    )  # todo this should just be the interval duration ?

    @property
    def contingency_neg(self) -> str:
        return "cont_neg_" + self.name

    def create_vars(self, model: EchoConcreteModel) -> None:
        setattr(
            model, self.contingency_neg, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonPositiveReals)
        )

    def apply_constraints(self, model: EchoConcreteModel) -> None:
        def export_flow_con(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            return getattr(model, self.contingency_neg)[p, t] >= (
                port.export_constraint_value - getattr(model, port.port_name)[p, t]
            )

        def import_flow_con(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            return (
                getattr(model, self.contingency_neg)[p, t]
                >= (port.import_constraint_value - getattr(model, port.port_name)[p, t]) * -1
            )

        # Iterate through vertices on path to pick up any port constraints along path
        for i in range(0, len(self.component.vertices) - 1):
            port = self.component.edge_ports[i][0]  # exporting port
            if port.export_constraint_value is not None:
                setattr(
                    model,
                    f"cont_neg_con_{port.port_name}",
                    en.Constraint(model.Expansion, model.Time, rule=export_flow_con),
                )

            port = self.component.edge_ports[i][1]  # importing port
            if port.import_constraint_value is not None:
                setattr(
                    model,
                    f"cont_neg_con_{port.port_name}",
                    en.Constraint(model.Expansion, model.Time, rule=import_flow_con),
                )

        # Meet SOC constraint on contingency providing asset, if applicable
        initial_port = self.component.edge_ports[0][0]
        if hasattr(initial_port, "soc_value"):

            def contingency_energy_limited_soc(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
                return (
                    getattr(model, self.contingency_neg)[p, t] * self.duration / 60
                    >= getattr(model, initial_port.soc_value)[p, t] * -1
                )

            setattr(
                model,
                f"cont_neg_soc_lim_{self.component.path_name}",
                en.Constraint(model.Expansion, model.Time, rule=contingency_energy_limited_soc),
            )

    def objective_expr(self, model: EchoConcreteModel) -> None:
        return sum(
            getattr(model, self.contingency_neg)[p, t] * model.discount_rates[p]
            for p in model.Expansion
            for t in model.Time
        )


@define
class ContingencyPositive(Contingency):
    """FCAS Lower"""

    duration: float = field(
        kw_only=True, validator=validators.gt(0)
    )  # todo this should just be the interval duration ?

    @property
    def contingency_pos(self) -> None:
        return "cont_pos_" + self.name

    def create_vars(self, model: EchoConcreteModel) -> None:
        setattr(
            model, self.contingency_pos, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals)
        )

    def apply_constraints(self, model: EchoConcreteModel) -> None:
        def export_flow_con(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            return (
                getattr(model, self.contingency_pos)[p, t]
                <= (port.export_constraint_value - getattr(model, port.port_name)[p, t]) * -1
            )

        def import_flow_con(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            return getattr(model, self.contingency_pos)[p, t] <= (
                port.import_constraint_value - getattr(model, port.port_name)[p, t]
            )

        # Iterate through vertices on path to pick up any port constraints along path
        for i in range(0, len(self.component.vertices) - 1):
            port = self.component.edge_ports[i][1]  # exporting port
            if port.export_constraint_value is not None:
                setattr(
                    model,
                    f"cont_pos_con_{port.port_name}",
                    en.Constraint(model.Expansion, model.Time, rule=export_flow_con),
                )

            port = self.component.edge_ports[i][0]  # importing port
            if port.import_constraint_value is not None:
                setattr(
                    model,
                    f"cont_pos_con_{port.port_name}",
                    en.Constraint(model.Expansion, model.Time, rule=import_flow_con),
                )

        # Meet SOC constraint on contingency providing asset, if applicable
        initial_port = self.component.edge_ports[0][0]
        if isinstance(initial_port, Storage):

            def contingency_energy_limited_soc(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
                return (
                    getattr(model, self.contingency_pos)[p, t] * self.duration / 60
                    <= initial_port.max_capacity - getattr(model, initial_port.soc_value)[p, t]
                )

            setattr(
                model,
                f"cont_pos_soc_lim_{self.component.path_name}",
                en.Constraint(model.Expansion, model.Time, rule=contingency_energy_limited_soc),
            )

    def objective_expr(self, model: EchoConcreteModel) -> None:
        return (
            sum(
                getattr(model, self.contingency_pos)[p, t] * model.discount_rates[p]
                for p in model.Expansion
                for t in model.Time
            )
            * -1
        )
