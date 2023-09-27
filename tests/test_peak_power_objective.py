import os

import numpy as np

from echo.configuration import Units
from echo.models.agnostic import ControlledLoad, FlexPort
from echo.models.base import Node, OptimisationGraph
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.objectives.base import ObjectiveSet
from echo.objectives.power import QuadraticPower
from echo.optimiser import optimise

N_INTERVALS = 48


def test_controlled_load_with_peak_power_objective():
    # This test contains non-linear optimisation, so cbc won't be able to run it. Check the environment and skip this
    # test if cbc is the optimiser engine
    optimiser_engine = os.environ.get("OPTIMISER_ENGINE", None)

    if optimiser_engine is None:
        raise ValueError("Environment variable optimiser_engine has not been set.")

    if optimiser_engine == "cbc":
        pass

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    controlled_load = Node()
    cl = ControlledLoad(max_power=5.0, min_power=0.0, max_utilisation=None, min_utilisation=5.0 / 60.0)
    controlled_load.ports["cload"] = cl

    system.add_node_obj([grid, controlled_load])
    system.connect_ports_and_create_edge(grid.ports["grid"], cl)

    quad_power = QuadraticPower(component=grid.ports["grid"])
    objective_set = ObjectiveSet(objective_list=[quad_power])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=objective_set,
    )

    root_p = optimise_results.values(grid.ports["grid"].port_name, 0) * -1
    cl_p = optimise_results.values(cl.port_name, 0)

    np.testing.assert_array_almost_equal(list(cl_p), [2 * 10.0 / N_INTERVALS] * 48)

    for i in range(N_INTERVALS):
        assert root_p[i] == cl_p[i]
