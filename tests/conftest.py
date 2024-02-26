import os

import pytest
from rich.console import Console

from echo.models import scenario


def default_testing_optimiser_engine():
    """The default test optimiser engine

    If this is changed, make sure that the replacement optimiser engine
    is installed in the github action.

    This is deliberately not a fixture so it can be accessed in the `pytest_terminal_summary` hook
    """
    return "cbc"


def testing_optimiser_engine():
    """Gets the optimiser engine for testing.

    Defaults to default_testing_optimiser_engine() but can be overriden by the
    `TESTING_OPTIMISER_ENGINE` environment variable.

    This is deliberately not a fixture so it can be accessed in the `pytest_terminal_summary` hook
    """
    return os.environ.get("TESTING_OPTIMISER_ENGINE", default_testing_optimiser_engine())


@pytest.fixture
def engine_settings() -> scenario.EngineSettings:
    """Fixture returning engine settings for tests

    This fixture should be used by all tests that required engine settings.
    It is strongly recommended not to use `scenario.engine_settings_from_environment()` which is
    intended for running echo and not testing echo.
    """
    return scenario.engine_settings_from_environment(optimiser_engine=testing_optimiser_engine())


# Based off this stackoverflow answer: https://stackoverflow.com/a/28198398
@pytest.fixture(autouse=True)
def skip_by_optimiser_engine_not_do_non_linear(request, engine_settings):
    optimiser = engine_settings.engine

    # If test marked as nonlinear...
    if request.node.get_closest_marker("nonlinear"):
        # and optimiser can't do non-linear optimisations...
        if not scenario.can_optimiser_do_non_linear_optimisation(optimiser=optimiser):
            # ...then skip
            pytest.skip(f"Optimiser '{optimiser}' cannot do non-linear optimisation")


def pytest_terminal_summary(terminalreporter, exitstatus, config):

    DEFAULT_SOLVER = default_testing_optimiser_engine()

    if testing_optimiser_engine() != DEFAULT_SOLVER:
        return

    with Console() as console:
        console.print(
            "\n==============================  Echo Solver Info  ==============================", style="magenta"
        )
        console.print(
            f"This pytest run used the default solver '{DEFAULT_SOLVER}' (like the Github Action).", end="\n\n"
        )
        console.print(
            "It is important to be aware that certain solvers (e.g. 'cbc') cannot perform all tests.", end="\n\n"
        )
        console.print("To run pytest with a different optimiser, set the 'TESTING_OPTIMISER_ENGINE'")
        console.print("environment variable. For example, to use cplex:", end="\n\n")
        console.print("$ TESTING_OPTIMISER_ENGINE=cplex pytest")
        console.print(
            "================================================================================", style="magenta"
        )
