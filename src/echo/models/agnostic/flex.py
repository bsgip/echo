import pandas as pd
import pyomo.environ as en
from pydantic import root_validator
from pyomo.core.expr import InequalityExpression

from echo.configuration import FlowConstraint, Flows, OptimisationType
from echo.models.base import Port
from echo.models.scenario import EchoConcreteModel
from echo.validators import (
    check_bound_order,
)


class FlexPort(Port):
    """Flexible variable port, which can import and export without constraints."""

    flows = Flows.Both
    import_constraint = FlowConstraint.NoConstraint
    export_constraint = FlowConstraint.NoConstraint
    flow_type = OptimisationType.Variable


class FlexSink(FlexPort):
    """Flexible port, imports only"""

    flows = Flows.Import


class FlexSource(FlexPort):
    """Flexible ports, exports only"""

    flows = Flows.Export


class OffOrConstrainedPort(FlexPort):
    """A port that is either off (0) or on, and when it is on it is constrained between a min and max value."""

    lower_bound: float
    upper_bound: float

    bounds_check = root_validator(allow_reuse=True)(check_bound_order)  # checks that lower bound < upper bound

    @property
    def active(self) -> str:
        return "active_" + self.port_name

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_port_to_model(model, profile)
        setattr(model, self.active, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary))

        # Apply constraints such that if active=1, the port is bounded, and if active=0, the port is 0.
        def on_off_constraint1(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            return getattr(model, self.port_name)[p, t] >= getattr(model, self.active)[p, t] * self.lower_bound

        def on_off_constraint2(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            return getattr(model, self.port_name)[p, t] <= getattr(model, self.active)[p, t] * self.upper_bound

        setattr(model, "on_off1_" + self.port_name, en.Constraint(model.Expansion, model.Time, rule=on_off_constraint1))
        setattr(model, "on_off2_" + self.port_name, en.Constraint(model.Expansion, model.Time, rule=on_off_constraint2))
