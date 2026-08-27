import os

import pyomo.environ as en
import pytest

from echo.models.scenario import EchoConcreteModel, ScenarioSettings, engine_settings_from_environment


@pytest.fixture
def can_optimiser_do_non_linear_optimisation() -> bool:
    # This test contains non-linear optimisation, so cbc won't be able to run it. Check the environment and skip this
    # test if cbc is the optimiser engine
    optimiser_engine = os.environ.get("OPTIMISER_ENGINE")

    if optimiser_engine == "cbc":
        return False

    return True


@pytest.fixture
def empty_model():
    DEFAULT_NUMBER_OF_INTERVALS = 6

    def _empty_model(number_of_intervals: int = DEFAULT_NUMBER_OF_INTERVALS) -> EchoConcreteModel:
        model = EchoConcreteModel()
        engine_settings = engine_settings_from_environment()
        scenario_settings = ScenarioSettings(
            interval_duration=30,
            number_of_intervals=number_of_intervals,
            number_of_expansion_intervals=1,
        )
        model.small_m = en.Param(initialize=engine_settings.small_m)
        model.big_m = en.Param(initialize=engine_settings.big_m)
        model.scenario_settings = scenario_settings
        model.Time = en.RangeSet(0, scenario_settings.number_of_intervals - 1)
        if scenario_settings.number_of_expansion_intervals == 0:
            model.Expansion = en.RangeSet(0, 0)
        else:
            model.Expansion = en.RangeSet(0, scenario_settings.number_of_expansion_intervals - 1)
        discount_rates = {}
        for ep in range(0, scenario_settings.number_of_expansion_intervals):
            discount_rates[ep] = 1 / ((1 + scenario_settings.discount_rate) ** ep)
        model.discount_rates = en.Param(model.Expansion, initialize=discount_rates)
        return model

    return _empty_model
