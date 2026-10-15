import pandas as pd
import pyomo.environ as en
import shortuuid
from attrs import define, field

from echo.models.base import Path, Port
from echo.models.scenario import EchoConcreteModel


@define
class Objective:
    component: Port | Path | None = None
    weight: float = 1
    uid: str = field(factory=shortuuid.uuid)
    name: str = field()

    @name.default
    def _set_name_default(self) -> str:
        return "obj_" + str(self.uid)

    def verify_objective(self, model: EchoConcreteModel, df: pd.DataFrame | None) -> None:
        pass

    def create_params(self, model: EchoConcreteModel, df: pd.DataFrame | None) -> None:
        pass

    def create_vars(self, model: EchoConcreteModel) -> None:
        pass

    def objective_expr(self, model: EchoConcreteModel) -> None:
        pass

    def apply_constraints(self, model: EchoConcreteModel) -> None:
        pass

    def get_objective_total(self, model: EchoConcreteModel) -> float:
        obj_expr = self.objective_expr(model)  # Retrieve the objective expression
        return en.value(obj_expr)  # Return the value of the summed expression


@define
class ObjectiveSet:
    """Objective Set is an object containing a list of defined objectives that can be passed to the echo optimiser"""

    objective_list: list[Objective] = field(factory=list)

    def add_objectives_to_model(self, model: EchoConcreteModel, df: pd.DataFrame | None = None) -> None:
        for obj in self.objective_list:
            obj.verify_objective(model, df)
            obj.create_params(model, df)
            obj.create_vars(model)
            obj.apply_constraints(model)

    def get_objective_total(self, model: EchoConcreteModel) -> float:
        return sum([obj.objective_expr(model) * obj.weight for obj in self.objective_list])


@define
class TotalFlow(Objective):
    """Minimises flow at a specified port across all time periods/expansions."""

    component: Port = field(kw_only=True)
    minimise: bool = True

    def objective_expr(self, model: EchoConcreteModel) -> float:
        sign = -1 if self.minimise else 1
        return sign * sum(getattr(model, self.component.port_name)[p, t] for p in model.Expansion for t in model.Time)


@define
class TotalImportFlow(Objective):
    """Minimises import at a specified port across all time periods/expansions."""

    component: Port = field(kw_only=True)
    minimise: bool = True

    def apply_constraints(self, model: EchoConcreteModel) -> None:
        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

    def objective_expr(self, model: EchoConcreteModel) -> float:
        sign = 1 if self.minimise else -1
        return sign * sum(getattr(model, self.component.pos)[p, t] for p in model.Expansion for t in model.Time)


@define
class TotalExportFlow(Objective):
    """Minimises export at a specified port across all time periods/expansions."""

    component: Port = field(kw_only=True)
    minimise: bool = True

    def apply_constraints(self, model: EchoConcreteModel) -> None:
        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

    def objective_expr(self, model: EchoConcreteModel) -> float:
        sign = -1 if self.minimise else 1
        return sign * sum(getattr(model, self.component.neg)[p, t] for p in model.Expansion for t in model.Time)
