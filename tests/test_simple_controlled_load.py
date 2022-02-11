import numpy as np
import pandas as pd
import pyomo.environ as en
from datetime import time, datetime

# from c3x.neon.objectives.tariffs.demand import DemandTariff, DemandTariffVersion, DemandCharge, DemandTariffObjective, \
#     Window, TimePeriod, Day
# from c3x.neon.objectives.throughput import ThroughputCost
# from c3x.neon.objectives.tariffs import ImportTariff
# from c3x.neon.models import Junction, Storage, Load, Gen
# from c3x.neon.objectives import Objective, ObjectiveSet
# from c3x.neon.optimiser import Optimiser

from echo_models import ElectricalDemand, ElectricalGeneration, ElectricalStorage, ElectricalNode, \
    OptimisationGraph, Tariff, Node, Port, Edge, Transform, ElectricalPort, DemandTariff, \
    ControlledLoad
from echo_optimiser import EchoOptimiser
from configuration import NodeRule, TransformRule, FlowConstraint, Flows, PathRule

from hypothesis.extra.numpy import arrays
from hypothesis.strategies import floats
from hypothesis import given, settings


import os

SOLVER = os.environ.get('OPTIMISER_ENGINE', 'cplex')
SOLVER_EXECUTABLE = None #os.environ.get('OPTIMISER_ENGINE_EXECUTABLE')



def test_simple_controlled_load_does_minimum_energy_action():

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    controlled_load = Node()
    cl = ControlledLoad()
    cl.max_power = 5.0
    cl.min_power = 0.0
    cl.min_utilisation = 5.0/60.0
    controlled_load.ports['cload'] = cl

    edge = Edge(vertices=[grid.ports['grid'], cl])
    system.add_node_obj([grid, controlled_load])
    system.add_edge_obj(edge)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system
    )

    # minimise imports
    optimiser.objective = sum(getattr(optimiser.model, cl.port_name)[p, i]
                   for p in optimiser.model.Expansion for i in optimiser.model.Time)

    optimiser.optimise()
    grid_export = optimiser.values(grid.ports['grid'].neg, 0)
    load_import = optimiser.values(cl.port_name, 0)

    np.testing.assert_almost_equal(sum(grid_export)*-1 * 30.0 / 60.0, 10.0)
    #assert sum(optimiser.values(grid.ports['grid'].neg, 0))*-1 * 30.0 / 60.0 == 10.0

    for i in range(time_periods):
        np.testing.assert_almost_equal(grid_export[i], load_import[i]*-1)
        #assert optimiser.values(grid.ports['grid'].port_name, 0)[i] == optimiser.values(cl.port_name, 0)[i]*-1



def test_simple_controlled_load_does_minimum_power_action():

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    controlled_load = Node()
    cl = ControlledLoad()
    cl.max_power = 5.0
    cl.min_power = 2.0
    cl.min_utilisation = 5.0/60.0
    controlled_load.ports['cload'] = cl

    edge = Edge(vertices=[grid.ports['grid'], cl])
    system.add_node_obj([grid, controlled_load])
    system.add_edge_obj(edge)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system
    )

    # minimise imports
    optimiser.objective = sum(getattr(optimiser.model, cl.port_name)[p, i]
                   for p in optimiser.model.Expansion for i in optimiser.model.Time)

    optimiser.optimise()

    grid_export = optimiser.values(grid.ports['grid'].neg, 0) * -1
    load_import = optimiser.values(cl.port_name, 0)

    for i in range(time_periods):
        np.testing.assert_almost_equal(load_import[i], 2.0)
        np.testing.assert_almost_equal(grid_export[i], load_import[i])


def test_simple_controlled_load_limited_to_max_energy():

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    controlled_load = Node()
    cl = ControlledLoad()
    cl.max_power = 5.0
    cl.min_power = 0.0
    cl.min_utilisation = 5.0/60.0
    cl.max_utilisation = 5.0/30.0
    controlled_load.ports['cload'] = cl

    edge = Edge(vertices=[grid.ports['grid'], cl])
    system.add_node_obj([grid, controlled_load])
    system.add_edge_obj(edge)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system
    )

    # maximise imports
    optimiser.objective = sum(getattr(optimiser.model, cl.port_name)[p, i]
                   for p in optimiser.model.Expansion for i in optimiser.model.Time)*-1

    optimiser.optimise()

    grid_export = optimiser.values(grid.ports['grid'].neg, 0) * -1
    load_import = optimiser.values(cl.port_name, 0)

    #assert sum(load_import) * 30.0 / 60.0 == 20.0
    np.testing.assert_almost_equal(sum(load_import) * 30.0 / 60.0, 20.0)

    for i in range(time_periods):
        np.testing.assert_almost_equal(grid_export[i],load_import[i])
        #assert grid_export[i] == load_import[i]



def test_simple_controlled_load_limited_to_max_power():


    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    controlled_load = Node()
    cl = ControlledLoad()
    cl.max_power = 5.0
    cl.min_power = 0.0
    cl.min_utilisation = 5.0/60.0
    cl.max_utilisation = None
    controlled_load.ports['cload'] = cl

    edge = Edge(vertices=[grid.ports['grid'], cl])
    system.add_node_obj([grid, controlled_load])
    system.add_edge_obj(edge)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system
    )

    # maximise imports
    optimiser.objective = sum(getattr(optimiser.model, cl.port_name)[p, i]
                   for p in optimiser.model.Expansion for i in optimiser.model.Time)*-1

    optimiser.optimise()

    grid_export = optimiser.values(grid.ports['grid'].neg, 0) * -1
    load_import = optimiser.values(cl.port_name, 0)

    for i in range(time_periods):
        np.testing.assert_almost_equal(load_import[i], 5.0)
        #assert load_import[i] == 5.0
        assert grid_export[i] == load_import[i]
