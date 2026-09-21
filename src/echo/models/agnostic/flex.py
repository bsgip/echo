import attr
import pandas as pd
import pyomo.environ as en
from attrs import define, field
from pyomo.core.expr import InequalityExpression

from echo.configuration import FlowConstraint, Flows, OptimisationType
from echo.models.base import Port
from echo.models.scenario import EchoConcreteModel
from echo.validators import (
    check_bound_order,
)


@define
class FlexPort(Port):
    """Flexible variable port, which can import and export without constraints."""

    flows = field(default=Flows.Both)
    import_constraint = field(default=FlowConstraint.NoConstraint)
    export_constraint = field(default=FlowConstraint.NoConstraint)
    flow_type = field(default=OptimisationType.Variable)


@define
class FlexSink(FlexPort):
    """Flexible port, imports only"""

    flows = field(default=Flows.Import)


@define
class FlexSource(FlexPort):
    """Flexible ports, exports only"""

    flows = field(default=Flows.Export)


@define
class OffOrConstrainedPort(FlexPort):
    """A port that is either off (0) or on, and when it is on it is constrained between a min and max value."""

    lower_bound: float = field(kw_only=True)
    upper_bound: float = field(kw_only=True)

    def __attrs_post_init__(self) -> None:
        # check lower bound < upper bound
        check_bound_order(self, attr.asdict(self))

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
