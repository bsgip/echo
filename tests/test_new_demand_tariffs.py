import numpy as np
import pytest

from echo_models import *
from echo_optimiser import EchoOptimiser
from configuration import *
from objectives import *

from hypothesis.extra.numpy import arrays
from hypothesis.strategies import floats
from hypothesis import given, settings


import os

SOLVER = os.environ.get('OPTIMISER_ENGINE','cplex')
SOLVER_EXECUTABLE = None



def test_system_import_demand_tariff():
    """ Test that we correctly calculate the max import demand """

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    load1 = Node()
    l1 = ElectricalDemand()
    demand = np.random.randint(0, 10, time_periods)
    l1.add_demand_profile_from_array(demand, expansion_periods)
    load1.ports['demand'] = l1

    system.add_node_obj([grid, load1])
    grid_edge = Edge(vertices=[l1, grid.ports['grid']])
    system.add_edge_obj([grid_edge])

    dc_window = [1] * 24 + [0] * 24
    minimum_demand = 1.0
    demand_tariff = ImportDemandTariffObjective(component=l1,
                                                demand_charges=[DemandCharge(
                                                  rate=1.0,
                                                  window_array=dc_window,
                                                  min_demand=minimum_demand)])

    objective_set = ObjectiveSet(objective_list=[demand_tariff])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=objective_set
    )

    optimiser.optimise()

    max_demand = optimiser.values(demand_tariff.demand_charges[0].max_demand_val, 0)
    max_in_window = max(np.multiply(demand, dc_window))
    np.testing.assert_array_almost_equal(max_demand, max_in_window-minimum_demand)


def test_system_export_demand_tariff():
    """ Test that we correctly calculate the max export demand """

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    gen = Node()
    g1 = ElectricalGeneration()
    gen_array = np.random.randint(-10, 0, time_periods)
    g1.add_generation_profile_from_array(gen_array, expansion_periods)
    gen.ports['gen'] = g1

    system.add_node_obj([grid, gen])
    grid_edge = Edge(vertices=[g1, grid.ports['grid']])
    system.add_edge_obj([grid_edge])

    dc_window = [1] * 24 + [0] * 24
    minimum_demand = 0.0
    demand_tariff = ExportDemandTariffObjective(component=g1,
                                                demand_charges=[DemandCharge(
                                                  rate=1.0,
                                                  window_array=dc_window,
                                                  min_demand=minimum_demand)])

    objective_set = ObjectiveSet(objective_list=[demand_tariff])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=objective_set
    )

    optimiser.optimise()

    max_demand = optimiser.values(demand_tariff.demand_charges[0].max_demand_val, 0)
    max_in_window = min(np.multiply(gen_array, dc_window))
    np.testing.assert_array_almost_equal(max_demand, max_in_window-minimum_demand)

