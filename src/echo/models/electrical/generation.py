import pandas as pd

from echo.configuration import (
    OptimisationType,
    Units,
)
from echo.models.agnostic import Source
from echo.models.scenario import EchoConcreteModel
from echo.utils import set_var_bounds_from_dict
from echo.validators import ArrayType


class ElectricalGeneration(Source):
    """Electrical generation which can be fixed (non-curtailable) or variable (curtailable)"""

    units = Units.KW
    curtailable: bool = False

    def add_generation_profile(self, generation: dict) -> None:
        self.set_initial_value(generation)

    def add_generation_profile_from_array(
        self,
        generation: ArrayType,
        expansion_periods: int = 1,
        time_periods: int | None = None,
    ) -> None:

        self.set_initial_value_from_array(
            array=generation, expansion_periods=expansion_periods, time_periods=time_periods
        )

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        # Whether curtailable is set or not affect whether the flow is represented as a parameter or variable
        # Handle that here before calling `add_port_to_model`
        self.flow_type = OptimisationType.Variable if self.curtailable else OptimisationType.Parameter

        super().add_port_to_model(model, profile)

        if self.curtailable:
            # Constrain solar gen to be within initial value (max value)
            set_var_bounds_from_dict(
                model=model,
                var_name=self.port_name,
                lb=self.initial_value,
                ub=None,
            )
