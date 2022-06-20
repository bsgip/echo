import numpy as np

from echo.echo_models import *
from echo.echo_optimiser import EchoOptimiser
from echo.configuration import *
from echo.objectives import *
import pytest
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
    grid.ports['grid'].set_flow_constraints(max_export=-100, max_import=100)

    load = Node()
    l1 = ElectricalDemand()
    demand = [5]*24 + [0]*24
    l1.add_demand_profile_from_array(demand)
    l1.can_be_shed = True
    l1.shed_cost = [0]*48
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
    load_shed = optimiser.values(l1.is_off)
    for i in range(time_periods):
        assert load_import[i] == demand[i] * (1 - load_shed[i])



def test_simple_bounded_load():

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_electrical_ports_from_list(['grid'])

    load = Node()
    ub = [4]*24 + [3]*24
    lb = [0]*24 + [2]*24
    l1 = BoundedElectricalLoad(upper_bound=ub, lower_bound=lb)
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
    optimiser.objective = sum(getattr(optimiser.model, l1.port_name)[p, i]
                   for p in optimiser.model.Expansion for i in optimiser.model.Time)

    optimiser.optimise(tee=True)
    print(optimiser.opt_status)
    load_import = optimiser.values(l1.port_name, 0)

    for i in range(time_periods):
        assert load_import[i] == min(ub[i], lb[i])

@pytest.mark.solver('milp')
@pytest.mark.parametrize(
    "time_delay",
    [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]

)
def test_time_delay_node(time_delay):

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_electrical_ports_from_list(['grid'])

    td = TimeDelayNode(time_delay=time_delay)
    td.add_input_port(Units.KW)
    td.ports['input'].set_flow_constraints(max_import=5, max_export=0.)
    td.add_output_port(Units.KW)

    load = Node()
    l1 = ElectricalDemand()
    demand = [0]*24 + [5]*24
    l1.add_demand_profile_from_array(demand)
    load.ports['load'] = l1

    system.add_node_obj([grid, td, load])
    system.connect_ports_and_create_edge(grid.ports['grid'], td.ports['input'])
    system.connect_ports_and_create_edge(td.ports['output'], l1)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    # optimiser.objective = sum(getattr(optimiser.model, l1.port_name)[p, i]
    #                for p in optimiser.model.Expansion for i in optimiser.model.Time)

    optimiser.optimise(tee=True)
    print(optimiser.opt_status)
    grid = optimiser.values(grid.ports['grid'].port_name)
    td_input = optimiser.values(td.ports['input'].port_name)
    td_output = optimiser.values(td.ports['output'].port_name)
    load_import = optimiser.values(l1.port_name, 0)

    for i in range(time_periods):
        if i < td.time_delay:
            assert load_import[i] == 0
        else:
            assert load_import[i] == -1*grid[int(i - td.time_delay)]

