import uuid
from typing import Optional, Union

import pandas as pd
import pyomo.environ as en
from pydantic import Field

from echo.models.base import BaseModel as EchoBaseModel
from echo.models.base import Path, Port
from echo.models.scenario import EchoConcreteModel


class Objective(EchoBaseModel):
    component: Union[Port, Path, None]
    uid: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str = ""

    def __init__(self, **data):
        super().__init__(**data)
        if not self.name:
            self.name = "obj_" + str(self.uid)

    def verify_objective(self, model: EchoConcreteModel, df: Optional[pd.DataFrame]):
        pass

    def create_params(self, model: EchoConcreteModel, df: Optional[pd.DataFrame]):
        pass

    def create_vars(self, model: EchoConcreteModel):
        pass

    def objective_expr(self, model: EchoConcreteModel):
        pass

    def apply_constraints(self, model: EchoConcreteModel):
        pass

    def get_objective_total(self, optimiser):
        obj_expr = self.objective_expr(optimiser.model)  # Retrieve the objective expression
        return en.value(obj_expr)  # Return the value of the summed expression


class ObjectiveSet(EchoBaseModel):
    """Objective Set is an object containing a list of defined objectives that can be passed to the echo optimiser"""

    objective_list: list[Objective]

    def initialise_objective(self, model: EchoConcreteModel, df: Optional[pd.DataFrame] = None):
        for obj in self.objective_list:
            obj.verify_objective(model, df)
            obj.create_params(model, df)
            obj.create_vars(model)
            obj.apply_constraints(model)

    def set_objective(self, model: EchoConcreteModel, optimiser):
        def objective_rule(model: EchoConcreteModel):
            return sum(obj.objective_expr(model) for obj in self.objective_list)

        optimiser.objective += objective_rule(model)
