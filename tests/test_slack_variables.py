import numpy as np

from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import ElectricalGeneration
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.objectives.base import ObjectiveSet, TotalFlow
from echo.optimiser import optimise

N_INTERVALS = 48


def test_export_slack_var_is_minimised():
    """Connect curtailable solar to a connection pt with a flow constraint and slack vars enabled.
    The optimiser should curtail the solar rather than allowing the slack to be nonzero."""
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min
    N_INTERVALS = time_periods

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-float(i) for i in range(N_INTERVALS)], expansion_periods)
    pv1.curtailable = True
    solar.ports["solar"] = pv1

    inverter = TellegenNode()
    inverter.add_ports_from_list(["cp", "pv"], FlexPort, units=Units.KW)
    inverter.ports["cp"].set_flow_constraints(max_export=-5.0, max_import=[5.0] * time_periods, slack=True)

    system.add_node_obj([grid, solar, inverter])

    system.connect_ports_and_create_edge(inverter.ports["pv"], pv1)
    system.connect_ports_and_create_edge(inverter.ports["cp"], grid.ports["grid"])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=ObjectiveSet(objective_list=[TotalFlow(component=grid.ports["grid"], minimise=False)]),
    )

    inv_export_slack = optimise_results.values(inverter.ports["cp"].export_slack, 0)

    np.testing.assert_almost_equal(inv_export_slack, 0)


def test_import_slack_var_is_minimised():
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min
    N_INTERVALS = time_periods

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)
    grid.ports["grid"].set_flow_constraints(max_export=-5.0, max_import=5.0, slack=True)

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-float(i) for i in range(N_INTERVALS)], expansion_periods)
    pv1.curtailable = True
    solar.ports["solar"] = pv1

    inverter = TellegenNode()
    inverter.add_ports_from_list(["cp", "pv"], FlexPort, units=Units.KW)

    system.add_node_obj([grid, solar, inverter])

    system.connect_ports_and_create_edge(inverter.ports["pv"], pv1)
    system.connect_ports_and_create_edge(inverter.ports["cp"], grid.ports["grid"])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=ObjectiveSet(objective_list=[TotalFlow(component=pv1, minimise=False)]),
    )

    g_import_slack = optimise_results.values(grid.ports["grid"].import_slack, 0)
    g = optimise_results.values(grid.ports["grid"].port_name, 0)

    np.testing.assert_almost_equal(g_import_slack, 0)


def test_slack_vars_take_up_slack_when_forced_to():
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min
    N_INTERVALS = time_periods

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-float(i) for i in range(N_INTERVALS)], expansion_periods)
    pv1.curtailable = True
    solar.ports["solar"] = pv1

    inverter = TellegenNode()
    inverter.add_ports_from_list(["cp", "pv"], FlexPort, units=Units.KW)
    inverter.ports["cp"].set_flow_constraints(max_export=-5.0, max_import=5.0, slack=True)

    system.add_node_obj([grid, solar, inverter])

    system.connect_ports_and_create_edge(inverter.ports["pv"], pv1)
    system.connect_ports_and_create_edge(inverter.ports["cp"], grid.ports["grid"])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
    )

    inv_export_slack = optimise_results.values(inverter.ports["cp"].export_slack, 0)
    sol_p = optimise_results.values(pv1.port_name, 0)

    for i in range(N_INTERVALS):
        np.testing.assert_almost_equal(inv_export_slack, max(0, -1 * sol_p[i] - 5))
