from pyomo.core.expr import InequalityExpression
import pyomo.environ as en
from pydantic import PositiveFloat

from echo.models.agnostic import Storage
from echo.models.base import Port
from echo.models.scenario import EchoConcreteModel
from echo.objectives.base import Objective


class PeakPositivePower(Objective):
    """The PeakPositivePower objective minimises the peak positive (imported) power at the specified port."""

    component: Port

    @property
    def max_pos(self) -> str:
        return "max_pos_" + self.name

    def create_vars(self, model: EchoConcreteModel) -> None:
        setattr(model, self.max_pos, en.Var(initialize=0, domain=en.NonNegativeReals))

    def apply_constraints(self, model: EchoConcreteModel) -> None:
        def max_value_rule(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            return getattr(model, self.max_pos) >= getattr(model, self.component.pos)[p, t]

        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

        setattr(
            model,
            f"max_pos_con_{self.component.port_name}",
            en.Constraint(model.Expansion, model.Time, rule=max_value_rule),
        )

    def objective_expr(self, model: EchoConcreteModel) -> float:
        return getattr(model, self.max_pos)


class PeakNegativePower(Objective):
    """The PeakNegativePower objective minimises the peak negative (exported) power at the specified port."""

    component: Port

    @property
    def max_neg(self) -> str:
        return "max_neg_" + self.name

    def create_vars(self, model: EchoConcreteModel) -> None:
        setattr(model, self.max_neg, en.Var(initialize=0, domain=en.NonPositiveReals))

    def apply_constraints(self, model: EchoConcreteModel) -> None:
        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

        def max_value_rule(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            return getattr(model, self.max_neg) <= getattr(model, self.component.neg)[p, t]

        setattr(
            model,
            f"max_neg_con_{self.component.port_name}",
            en.Constraint(model.Expansion, model.Time, rule=max_value_rule),
        )

    def objective_expr(self, model: EchoConcreteModel) -> float:
        return getattr(model, self.max_neg) * -1


class FinalChargeObjective(Objective):
    """A cost on the final state of charge of a storage asset being below full."""

    component: Storage
    rate: PositiveFloat

    def apply_constraints(self, model: EchoConcreteModel) -> None:
        pass
        # if hasattr(model, self.component.pos) is False:
        #     self.component.constrain_pos_neg(model)

    def objective_expr(self, model: EchoConcreteModel) -> float:
        obj = sum(
            (self.component.max_capacity - getattr(model, self.component.soc_value)[p, model.Time.at(-1)]) * self.rate
            for p in model.Expansion
        )
        return obj


class NotFullyChargedPenalty(Objective):
    """A penalty objective for penalising a storage asset for not being fulling charged."""

    component: Storage
    rate: PositiveFloat | None
    rate_array: list

    def apply_constraints(self, model: EchoConcreteModel) -> None:
        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

    def objective_expr(self, model: EchoConcreteModel) -> None:
        if self.rate_array is None:
            self.rate_array = [self.rate] * len(model.Time)
        obj = sum(
            (self.component.max_capacity - getattr(model, self.component.soc_value)[p, t])
            * self.rate_array[t]
            * model.discount_rates[p]
            for p in model.Expansion
            for t in model.Time
        )
        return obj


class QuadraticPower(Objective):
    """The QuadraticPower objective minimises flow^2 at a specified port."""

    component: Port

    def apply_constraints(self, model: EchoConcreteModel) -> None:
        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

    def objective_expr(self, model: EchoConcreteModel) -> float:
        return sum(
            (getattr(model, self.component.port_name)[p, t] * getattr(model, self.component.port_name)[p, t])
            * model.discount_rates[p]
            for p in model.Expansion
            for t in model.Time
        )
