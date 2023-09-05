import os

import numpy as np

from echo.configuration import NodeRule, Units
from echo.echo_optimiser import EchoOptimiser
from echo.models.agnostic import FlexPort
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import ElectricalDemand, ElectricalGeneration, ElectricalStorage, Inverter
from echo.objectives import DemandTariffObjective, ExportDemandCharge, ImportDemandCharge, ObjectiveSet


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

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=objective_set,
    )

    optimiser.optimise()

    max_demand = optimiser.values(demand_tariff.demand_charges[0].max_demand_val, 0)
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

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=objective_set,
    )

    optimiser.optimise()

    max_demand = optimiser.values(demand_tariff.demand_charges[0].max_demand_val, 0)
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

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=objective_set,
    )

    optimiser.optimise()

    max_demand = optimiser.values(demand_tariff.demand_charges[0].max_demand_val, 0)

    np.testing.assert_array_almost_equal(max_demand[0], 10 - minimum_demand)
    np.testing.assert_array_almost_equal(max_demand[1], 20 - minimum_demand)
