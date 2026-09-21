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
    nonnegative_load,
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

    import_constraint = field(default=FlowConstraint.NoConstraint)

    upper_bound: ArrayType | float = field(kw_only=True)
    lower_bound: ArrayType | float = field(kw_only=True)

    # Do additional validation to make sure both bounds are >= 0
    @upper_bound.validator
    def _validate_upper_bound(self, attribute, value):  # noqa: ANN001, ANN202
        nonnegative_load(value)

    @lower_bound.validator
    def _validate_lower_bound(self, attribute, value):  # noqa: ANN001, ANN202
        nonnegative_load(value)

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_port_to_model(model, profile)
