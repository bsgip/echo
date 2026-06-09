import uuid

import pandas as pd
import pyomo.environ as en
from pydantic import Field

from echo.models.base import BaseModel as EchoBaseModel
from echo.models.base import Path, Port
from echo.models.scenario import EchoConcreteModel


class Objective(EchoBaseModel):
    component: Port | Path | None
    uid: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str = ""
    weight: float = 1

    def __init__(self, **data):
        super().__init__(**data)
        if not self.name:
            self.name = "obj_" + str(self.uid)

    def verify_objective(self, model: EchoConcreteModel, df: pd.DataFrame | None):
        pass

    def create_params(self, model: EchoConcreteModel, df: pd.DataFrame | None):
        pass

    def create_vars(self, model: EchoConcreteModel):
        pass

    def objective_expr(self, model: EchoConcreteModel):
        pass

    def apply_constraints(self, model: EchoConcreteModel):
        pass

    def get_objective_total(self, model: EchoConcreteModel):
        obj_expr = self.objective_expr(model)  # Retrieve the objective expression
        return en.value(obj_expr)  # Return the value of the summed expression


class ObjectiveSet(EchoBaseModel):
    """Objective Set is an object containing a list of defined objectives that can be passed to the echo optimiser"""

    objective_list: list[Objective]

    def add_objectives_to_model(self, model: EchoConcreteModel, df: pd.DataFrame | None = None):
        for obj in self.objective_list:
            obj.verify_objective(model, df)
            obj.create_params(model, df)
            obj.create_vars(model)
            obj.apply_constraints(model)

    def get_objective_total(self, model: EchoConcreteModel):
        return sum([obj.objective_expr(model) * obj.weight for obj in self.objective_list])


class TotalFlow(Objective):
    """Minimises flow at a specified port across all time periods/expansions."""

    component: Port
    minimise: bool = True

    def objective_expr(self, model: EchoConcreteModel):
        sign = -1 if self.minimise else 1
        return sign * sum(getattr(model, self.component.port_name)[p, t] for p in model.Expansion for t in model.Time)


class TotalImportFlow(Objective):
    """Minimises import at a specified port across all time periods/expansions."""

    component: Port
    minimise: bool = True

    def apply_constraints(self, model: EchoConcreteModel):
        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

    def objective_expr(self, model: EchoConcreteModel):
        sign = 1 if self.minimise else -1
        return sign * sum(getattr(model, self.component.pos)[p, t] for p in model.Expansion for t in model.Time)


class TotalExportFlow(Objective):
    """Minimises export at a specified port across all time periods/expansions."""

    component: Port
    minimise: bool = True

    def apply_constraints(self, model: EchoConcreteModel):
        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

    def objective_expr(self, model: EchoConcreteModel):
        sign = -1 if self.minimise else 1
        return sign * sum(getattr(model, self.component.neg)[p, t] for p in model.Expansion for t in model.Time)
