import numpy as np

from echo.echo_models import *
from echo.echo_optimiser import EchoOptimiser
from echo.configuration import *
from echo.objectives import *

import os

SOLVER = os.environ.get('OPTIMISER_ENGINE', 'cplex')
SOLVER_EXECUTABLE = None


def test_simple_load_shedding():

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_electrical_ports_from_list(['grid'])

    load = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([5]*time_periods)
    l1.can_be_shed = True
    l1.shed_cost = 0.
    load.ports['load'] = l1

    system.add_node_obj([grid, load])
    system.connect_ports_and_create_edge(grid.ports['grid'], l1)

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
    optimiser.objective = sum(getattr(optimiser.model, l1.port_name)[p, i]
                   for p in optimiser.model.Expansion for i in optimiser.model.Time)

    optimiser.optimise()
    grid_export = optimiser.values(grid.ports['grid'].neg, 0)
    load_import = optimiser.values(l1.port_name, 0)

    np.testing.assert_almost_equal(sum(grid_export)*-1 * 30.0 / 60.0, 10.0)
    #assert sum(optimiser.values(grid.ports['grid'].neg, 0))*-1 * 30.0 / 60.0 == 10.0
