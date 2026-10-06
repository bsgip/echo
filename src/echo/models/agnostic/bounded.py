import attr
import pandas as pd
from attrs import define, field

from echo.configuration import FlowConstraint
from echo.models.agnostic.flex import FlexPort
from echo.models.scenario import EchoConcreteModel
from echo.utils import (
    generate_array_constraint,
    set_var_bounds_from_dict,
)
from echo.validators import (
    ArrayType,
    check_bound_order,
    nonnegative_load_validator,
)


@define
class BoundedPort(FlexPort):
    """A flex port with an upper and lower bound"""

    upper_bound: ArrayType | float = field(kw_only=True)
    lower_bound: ArrayType | float = field(kw_only=True)

    def __attrs_post_init__(self) -> None:
        # check lower bound < upper bound
        check_bound_order(self, attr.asdict(self))

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_port_to_model(model, profile)
        # Set bounds on our port variable
        ub_dict = generate_array_constraint(self.upper_bound, time_periods=len(model.Time), expansion_periods=1)
        lb_dict = generate_array_constraint(self.lower_bound, time_periods=len(model.Time), expansion_periods=1)
        set_var_bounds_from_dict(model=model, var_name=self.port_name, ub=ub_dict, lb=lb_dict)


@define
class BoundedLoad(BoundedPort):
    """A port where the load has to be within a max and min value which is specified at each timestep."""

    import_constraint: FlowConstraint = FlowConstraint.NoConstraint

    upper_bound: ArrayType | float = field(kw_only=True, validator=nonnegative_load_validator)
    lower_bound: ArrayType | float = field(kw_only=True, validator=nonnegative_load_validator)

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_port_to_model(model, profile)
