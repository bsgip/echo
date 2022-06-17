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
    demand = [5]*24 + [0]*24
    l1.add_demand_profile_from_array(demand)
    l1.can_be_shed = True
    l1.shed_cost = 0.2
    l1.max_shed_duration = 2
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
    optimiser.objective += sum(getattr(optimiser.model, l1.port_name)[p, i]
                   for p in optimiser.model.Expansion for i in optimiser.model.Time)

    optimiser.optimise(tee=True)
    print(optimiser.opt_status)
    grid_export = optimiser.values(grid.ports['grid'].neg, 0)
    load_import = optimiser.values(l1.port_name, 0)
    load_shed = optimiser.values(l1.is_shed)

    for i in range(time_periods):
        assert load_import[i] == demand[i] * (1 - load_shed[i])

    assert sum(load_shed) <= l1.max_shed_duration
