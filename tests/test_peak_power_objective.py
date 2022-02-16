import numpy as np

from echo_models import *
from echo_optimiser import EchoOptimiser
from objectives import *

import os

SOLVER = os.environ.get('OPTIMISER_ENGINE', 'cplex')
SOLVER_EXECUTABLE = None

N_INTERVALS = 48

def test_controlled_load_with_peak_power_objective():

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    controlled_load = Node()
    cl = ControlledLoad(max_power=5.0, min_power=0.0, max_utilisation=None, min_utilisation=5.0/60.0)
    controlled_load.ports['cload'] = cl

    system.add_node_obj([grid, controlled_load])
    system.connect_ports_and_create_edge(grid.ports['grid'], cl)

    quad_power = QuadraticPower(component=grid.ports['grid'])
    objective_set = ObjectiveSet(objective_list=[quad_power])

    system.objective_set = objective_set

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system
    )

    optimiser.optimise()

    root_p = optimiser.values(grid.ports['grid'].port_name, 0)*-1
    cl_p = optimiser.values(cl.port_name, 0)

    np.testing.assert_array_almost_equal(list(cl_p), [2 * 10.0 / N_INTERVALS] * 48)

    for i in range(N_INTERVALS):
        assert root_p[i] == cl_p[i]
