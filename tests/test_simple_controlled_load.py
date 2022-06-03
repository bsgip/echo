import numpy as np

from echo.echo_models import *
from echo.echo_optimiser import EchoOptimiser
from echo.configuration import *
from echo.objectives import *

import os

SOLVER = os.environ.get('OPTIMISER_ENGINE', 'cplex')
SOLVER_EXECUTABLE = None


def test_simple_controlled_load_does_minimum_energy_action():

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_electrical_ports_from_list(['grid'])

    controlled_load = Node()
    cl = ControlledLoad(max_power=5.0, min_power=0.0, max_utilisation=None, min_utilisation=5.0/60.0)
    controlled_load.ports['cload'] = cl

    system.add_node_obj([grid, controlled_load])
    system.connect_ports_and_create_edge(grid.ports['grid'], cl)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    # minimise imports
    grid.ports['grid'].constrain_pos_neg(optimiser.model)
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
    grid.add_electrical_ports_from_list(['grid'])

    controlled_load = Node()
    cl = ControlledLoad(max_power=5.0, min_power=2.0, min_utilisation=5.0/60.0, max_utilisation=None)
    controlled_load.ports['cload'] = cl

    system.add_node_obj([grid, controlled_load])
    system.connect_ports_and_create_edge(grid.ports['grid'], cl)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    # minimise imports
    grid.ports['grid'].constrain_pos_neg(optimiser.model)
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
    grid.add_electrical_ports_from_list(['grid'])

    controlled_load = Node()
    cl = ControlledLoad(max_power=5.0, min_power=0.0, min_utilisation=5.0/60.0, max_utilisation=5.0/30.0)
    controlled_load.ports['cload'] = cl

    edge = Edge(vertices=[grid.ports['grid'], cl])
    system.add_node_obj([grid, controlled_load])
    system.add_edge_obj(edge)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    # maximise imports
    grid.ports['grid'].constrain_pos_neg(optimiser.model)
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
    grid.add_electrical_ports_from_list(['grid'])

    controlled_load = Node()
    cl = ControlledLoad(max_power=5.0, min_power=0.0, min_utilisation=5.0/60.0, max_utilisation=None)
    controlled_load.ports['cload'] = cl

    edge = Edge(vertices=[grid.ports['grid'], cl])
    system.add_node_obj([grid, controlled_load])
    system.add_edge_obj(edge)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    # maximise imports
    grid.ports['grid'].constrain_pos_neg(optimiser.model)
    optimiser.objective = sum(getattr(optimiser.model, cl.port_name)[p, i]
                   for p in optimiser.model.Expansion for i in optimiser.model.Time)*-1

    optimiser.optimise()

    grid_export = optimiser.values(grid.ports['grid'].neg, 0) * -1
    load_import = optimiser.values(cl.port_name, 0)

    for i in range(time_periods):
        np.testing.assert_almost_equal(load_import[i], 5.0)
        #assert load_import[i] == 5.0
        assert grid_export[i] == load_import[i]
