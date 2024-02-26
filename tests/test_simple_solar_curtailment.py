import numpy as np

from echo.configuration import Units
from echo.models.agnostic import FlexPort, FlexSink, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import ElectricalGeneration
from echo.models.scenario import ScenarioSettings
from echo.objectives.base import ObjectiveSet, TotalFlow, TotalImportFlow
from echo.optimiser import optimise

N_INTERVALS = 48


def test_solar_generation_limited_by_inverter_size(engine_settings):
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min
    N_INTERVALS = time_periods

    system = OptimisationGraph()

    # Receives the power via inverter
    cp = Node()
    cp.add_ports_from_list(["inverter"], FlexPort, units=Units.KW)

    # Fixed generation ramping up over time
    solar = Node()
    pv1 = ElectricalGeneration(port_name="electrical_generation_port")
    pv1.add_generation_profile_from_array([-float(i) for i in range(N_INTERVALS)], expansion_periods)
    pv1.curtailable = False
    solar.ports["solar"] = pv1

    # This just receives the curtailed power
    ground = Node()
    ground.add_ports_from_list(["inverter"], FlexSink, units=Units.KW)

    inverter = TellegenNode()
    inverter.add_ports_from_list(["cp", "pv", "ground"], FlexPort, units=Units.KW)
    inverter.ports["cp"].set_flow_constraints(max_export=-5.0, max_import=5.0)

    system.add_node_obj([cp, solar, inverter, ground])

    system.connect_ports_and_create_edge(inverter.ports["pv"], pv1)
    system.connect_ports_and_create_edge(inverter.ports["cp"], cp.ports["inverter"])
    system.connect_ports_and_create_edge(inverter.ports["ground"], ground.ports["inverter"])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings,
        graph=system,
        objective_set=ObjectiveSet(objective_list=[TotalFlow(component=inverter.ports["cp"], minimise=False)]),
    )

    sol_p = optimise_results.values(pv1.port_name, 0)
    inv_p = optimise_results.values(inverter.ports["cp"].port_name, 0)
    cp_p = optimise_results.values(cp.ports["inverter"].port_name, 0)
    ground_p = optimise_results.values(inverter.ports["ground"].port_name, 0)

    for i in range(N_INTERVALS):
        np.testing.assert_almost_equal(inv_p[i], max(-i, -5.0))  # Our outgoing power should ramp up and then curtail
        np.testing.assert_almost_equal(inv_p[i] + ground_p[i], sol_p[i])  # The curtailed power goes to ground
        np.testing.assert_almost_equal(cp_p[i], min(i, 5.0))


def test_non_curtailable_system_not_curtailed(engine_settings):
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min
    N_INTERVALS = time_periods

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-5.0] * N_INTERVALS, expansion_periods)
    pv1.curtailable = False
    solar.ports["solar"] = pv1

    inverter = TellegenNode()
    inverter.add_ports_from_list(["cp", "pv"], FlexPort, units=Units.KW)
    inverter.ports["cp"].set_flow_constraints(max_export=-5.0, max_import=5.0)

    system.add_node_obj([grid, solar, inverter])

    system.connect_ports_and_create_edge(inverter.ports["pv"], pv1)
    system.connect_ports_and_create_edge(inverter.ports["cp"], grid.ports["grid"])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings,
        graph=system,
        objective_set=ObjectiveSet(objective_list=[TotalImportFlow(component=grid.ports["grid"])]),
    )

    inv_p = optimise_results.values(inverter.ports["cp"].port_name, 0)
    sol_p = optimise_results.values(pv1.port_name, 0)
    root_p = optimise_results.values(grid.ports["grid"].port_name, 0)

    for i in range(N_INTERVALS):
        np.testing.assert_almost_equal(sol_p[i], -5.0)
        np.testing.assert_almost_equal(inv_p[i], -5.0)
        np.testing.assert_almost_equal(root_p[i], 5.0)


def test_curtailable_system_curtailed(engine_settings):
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min
    N_INTERVALS = time_periods

    system = OptimisationGraph()

    grid = Node()
    grid.add_port("grid", FlexPort(units=Units.KW))

    # Solar will generate 16 but we expect the inverter to cause it to curtail to 5
    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-16.0] * N_INTERVALS, expansion_periods)
    pv1.curtailable = True
    solar.ports["solar"] = pv1

    # Inverter has a flow constraint that should trigger the solar to curtail
    inverter = TellegenNode()
    inverter.add_ports_from_list(["cp", "pv"], FlexPort, units=Units.KW)
    inverter.ports["cp"].set_flow_constraints(max_export=-5.0, max_import=5.0)

    system.add_node_obj([grid, solar, inverter])

    system.connect_ports_and_create_edge(inverter.ports["pv"], pv1)
    system.connect_ports_and_create_edge(inverter.ports["cp"], grid.ports["grid"])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings,
        graph=system,
        objective_set=ObjectiveSet(objective_list=[TotalFlow(component=grid.ports["grid"])]),
    )

    inv_p = optimise_results.values(inverter.ports["cp"].port_name, 0)
    sol_p = optimise_results.values(pv1.port_name, 0)
    root_p = optimise_results.values(grid.ports["grid"].port_name, 0)

    for i in range(N_INTERVALS):
        np.testing.assert_almost_equal(sol_p[i], -5.0)  # Solar should be curtailed
        np.testing.assert_almost_equal(inv_p[i], -5.0)  # To meet the inverter limit
        np.testing.assert_almost_equal(root_p[i], 5.0)  # And the grid will receive that power
