import numpy as np

from echo.configuration import Units
from echo.models.agnostic import FlexPort
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import ElectricalDemand, ElectricalGeneration
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.objectives.base import ObjectiveSet
from echo.objectives.tariff import DemandTariffObjective, ExportDemandCharge, ImportDemandCharge
from echo.optimiser import optimise


def test_system_import_demand_tariff():
    """Test that we correctly calculate the max import demand"""

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    load1 = Node()
    l1 = ElectricalDemand()
    demand = np.random.randint(0, 10, time_periods)
    l1.add_demand_profile_from_array(demand, expansion_periods)
    load1.ports["demand"] = l1

    system.add_node_obj([grid, load1])
    system.connect_ports_and_create_edge(l1, grid.ports["grid"])

    dc_window = [1] * 24 + [0] * 24
    minimum_demand = 1.0
    demand_tariff = DemandTariffObjective(
        component=l1,
        demand_charges=[
            ImportDemandCharge(
                rate=1.0, window_array=dc_window, min_demand=minimum_demand, reset_periods=[time_periods]
            )
        ],
    )

    objective_set = ObjectiveSet(objective_list=[demand_tariff])

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

    max_demand = optimise_results.values(demand_tariff.demand_charges[0].max_demand_val, 0)
    max_in_window = max(np.multiply(demand, dc_window))
    np.testing.assert_array_almost_equal(max_demand, max_in_window - minimum_demand)


def test_system_export_demand_tariff():
    """Test that we correctly calculate the max export demand"""

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    gen = Node()
    g1 = ElectricalGeneration()
    gen_array = np.random.randint(-10, 0, time_periods)
    g1.add_generation_profile_from_array(gen_array, expansion_periods)
    gen.ports["gen"] = g1

    system.add_node_obj([grid, gen])
    system.connect_ports_and_create_edge(g1, grid.ports["grid"])

    dc_window = [1] * 24 + [0] * 24
    minimum_demand = 0.0
    demand_tariff = DemandTariffObjective(
        component=g1,
        demand_charges=[
            ExportDemandCharge(
                rate=1.0, window_array=dc_window, min_demand=minimum_demand, reset_periods=[time_periods]
            )
        ],
    )

    objective_set = ObjectiveSet(objective_list=[demand_tariff])

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

    max_demand = optimise_results.values(demand_tariff.demand_charges[0].max_demand_val, 0)
    max_in_window = min(np.multiply(gen_array, dc_window))
    np.testing.assert_array_almost_equal(max_demand, max_in_window - minimum_demand)


def test_system_import_demand_tariff_two_resets():
    """Test that we correctly calculate the max import demand when we use a reset period"""

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    load1 = Node()
    l1 = ElectricalDemand()
    demand = [10] * 24 + [20] * 24
    l1.add_demand_profile_from_array(demand, expansion_periods)
    load1.ports["demand"] = l1

    system.add_node_obj([grid, load1])
    system.connect_ports_and_create_edge(grid.ports["grid"], l1)

    dc_window = [1] * 6 + [0] * 6 + [0] * 24 + [1] * 6 + [0] * 6
    minimum_demand = 1.0
    demand_tariff = DemandTariffObjective(
        component=l1,
        demand_charges=[
            ImportDemandCharge(
                rate=1.0, import_demand=True, window_array=dc_window, min_demand=minimum_demand, reset_periods=[23, 25]
            )
        ],
    )

    objective_set = ObjectiveSet(objective_list=[demand_tariff])

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

    max_demand = optimise_results.values(demand_tariff.demand_charges[0].max_demand_val, 0)

    np.testing.assert_array_almost_equal(max_demand[0], 10 - minimum_demand)
    np.testing.assert_array_almost_equal(max_demand[1], 20 - minimum_demand)


def test_demand_tariff_read_and_implemented_correctly():
    """Test that the solution to fixing the closure construction has been implemented correctly."""

    demand = np.array([25, 2014, 1, 2015, 9, 23, 1, 11, 999])

    expansion_periods = 1
    time_periods = len(demand)
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    load1 = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array(demand, expansion_periods)
    load1.ports["demand"] = l1

    system.add_node_obj([grid, load1])
    system.connect_ports_and_create_edge(l1, grid.ports["grid"])

    demand_charge_window_1 = [1] * 3 + [0] * 6
    demand_charge_window_2 = [0] * 3 + [1] * 3 + [0] * 3
    demand_charge_window_3 = [0] * 6 + [1] * 3

    minimum_demand = 0.0
    demand_tariff = DemandTariffObjective(
        component=l1,
        demand_charges=[
            ImportDemandCharge(
                rate=1.0,
                window_array=demand_charge_window_1,
                min_demand=minimum_demand,
                reset_periods=[len(demand)],
            ),
            ImportDemandCharge(
                rate=1.0,
                window_array=demand_charge_window_2,
                min_demand=minimum_demand,
                reset_periods=[len(demand)],
            ),
            ImportDemandCharge(
                rate=1.0,
                window_array=demand_charge_window_3,
                min_demand=minimum_demand,
                reset_periods=[len(demand)],
            ),
        ],
    )

    objective_set = ObjectiveSet(objective_list=[demand_tariff])

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

    max_demand_1 = optimise_results.values(demand_tariff.demand_charges[0].max_demand_val, 0)
    max_demand_2 = optimise_results.values(demand_tariff.demand_charges[1].max_demand_val, 0)
    max_demand_3 = optimise_results.values(demand_tariff.demand_charges[2].max_demand_val, 0)
    max_in_window_1 = max(np.multiply(demand, demand_charge_window_1))
    max_in_window_2 = max(np.multiply(demand, demand_charge_window_2))
    max_in_window_3 = max(np.multiply(demand, demand_charge_window_3))

    print(max_demand_1)
    print(max_demand_2)
    print(max_demand_3)
    print(max_in_window_1)
    print(max_in_window_2)
    print(max_in_window_3)
    print(optimise_results.objective.args[0].value)
    print(optimise_results.objective.args[1].value)
    print(optimise_results.objective.args[2].value)

    assert round(max_demand_1[0]) == max_in_window_1 == round(optimise_results.objective.args[0].value)
    assert round(max_demand_2[0]) == max_in_window_2 == round(optimise_results.objective.args[1].value)
    assert round(max_demand_3[0]) == max_in_window_3 == round(optimise_results.objective.args[2].value)
