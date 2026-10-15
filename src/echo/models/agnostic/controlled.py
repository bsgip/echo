import attrs
import pandas as pd
import pyomo.environ as en
from attrs import define, field
from pyomo.core.expr import InequalityExpression

from echo.configuration import Flows, Units
from echo.models.agnostic.flex import FlexPort
from echo.models.scenario import EchoConcreteModel
from echo.utils import (
    set_float_var_bounds,
)


@define
class ControlledLoadOrGen(FlexPort):
    """
    A controlled load or generation has a max/min power, as well as a max/min utilisation.
    Min utilisation is the ratio between the minimum energy consumed/generated,
    and the maximum energy that could be consumed/generated if the load operated at max power.
    Max utilisation is the ratio between the maximum energy consumed/generated,
    and the maximum energy that could be consumed/generated if the load operated at max power.
    """

    min_utilisation: float | None = field(default=None)
    max_utilisation: float | None = field(default=None)
    max_power: float | None = field(default=None)
    min_power: float | None = field(default=None)
    units: Units = field(default=Units.KW)

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_port_to_model(model, profile)

        # Set bounds using min and max power
        set_float_var_bounds(model=model, var_name=self.port_name, ub=self.max_power, lb=self.min_power)

        if self.min_utilisation is not None and self.max_power is not None:
            min_utilisation: float = self.min_utilisation
            max_power: float = self.max_power

            def sum_of_energy_must_be_greater_than_min(model: EchoConcreteModel) -> InequalityExpression:
                return (
                    sum(
                        getattr(model, self.port_name)[p, i] * model.scenario_settings.interval_duration / 60.0
                        for p in model.Expansion
                        for i in model.Time
                    )
                    >= min_utilisation
                    * max_power
                    * model.scenario_settings.interval_duration
                    * model.scenario_settings.number_of_intervals
                    / 60.0
                )

            setattr(
                model,
                f"cons_{self.port_name}_min_utilisation_req",
                en.Constraint(rule=sum_of_energy_must_be_greater_than_min),
            )

        if self.max_utilisation is not None and self.max_power is not None:
            max_utilisation: float = self.max_utilisation
            max_power = self.max_power

            def sum_of_energy_must_be_less_than_max(model: EchoConcreteModel) -> InequalityExpression:
                return (
                    sum(
                        getattr(model, self.port_name)[p, i] * model.scenario_settings.interval_duration / 60.0
                        for p in model.Expansion
                        for i in model.Time
                    )
                    <= max_utilisation
                    * max_power
                    * model.scenario_settings.interval_duration
                    * model.scenario_settings.number_of_intervals
                    / 60.0
                )

            setattr(
                model,
                f"cons_{self.port_name}_max_utilisation_req",
                en.Constraint(rule=sum_of_energy_must_be_less_than_max),
            )


@define
class ControlledLoad(ControlledLoadOrGen):
    max_power: float = field(kw_only=True, validator=attrs.validators.ge(0))
    min_power: float = field(kw_only=True, validator=attrs.validators.ge(0))
    flows = Flows.Import


@define
class ControlledGen(ControlledLoadOrGen):
    max_power: float = field(kw_only=True, validator=attrs.validators.le(0))
    min_power: float = field(kw_only=True, validator=attrs.validators.le(0))
    flows = Flows.Export
