import pandas as pd
from pydantic import root_validator, validator

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
    nonnegative_costs,
)


class BoundedPort(FlexPort):
    """A flex port with an upper and lower bound"""

    upper_bound: ArrayType | float
    lower_bound: ArrayType | float

    bound_check = root_validator(allow_reuse=True)(check_bound_order)  # check lower bound < upper bound

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_port_to_model(model, profile)
        # Set bounds on our port variable
        ub_dict = generate_array_constraint(self.upper_bound, time_periods=len(model.Time), expansion_periods=1)
        lb_dict = generate_array_constraint(self.lower_bound, time_periods=len(model.Time), expansion_periods=1)
        set_var_bounds_from_dict(model=model, var_name=self.port_name, ub=ub_dict, lb=lb_dict)


class BoundedLoad(BoundedPort):
    """A port where the load has to be within a max and min value which is specified at each timestep."""

    import_constraint = FlowConstraint.NoConstraint

    # Do additional validation to make sure both bounds are >= 0
    upper_bound_check = validator("upper_bound", allow_reuse=True)(nonnegative_costs)
    lower_bound_check = validator("lower_bound", allow_reuse=True)(nonnegative_costs)

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_port_to_model(model, profile)
