import numpy as np

from echo_models import *
from echo_optimiser import EchoOptimiser
from objectives import *

import os

SOLVER = os.environ.get('OPTIMISER_ENGINE', 'cplex')
SOLVER_EXECUTABLE = None

N_INTERVALS = 48

def test_solar_generation_limited_by_inverter_size():
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min
    N_INTERVALS = time_periods

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-float(i) for i in range(N_INTERVALS)], expansion_periods)
    pv1.curtailable = True
    solar.ports['solar'] = pv1

    inverter = ElectricalTellegenNode()
    inverter.add_named_electrical_ports(['cp', 'pv'])
    inverter.ports['cp'].set_flow_constraints(max_export=-5.0, max_import=5.0)

    system.add_node_obj([grid, solar, inverter])

    system.connect_ports_and_create_edge(inverter.ports['pv'], pv1)
    system.connect_ports_and_create_edge(inverter.ports['cp'], grid.ports['grid'])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    optimiser.objective = sum(getattr(optimiser.model, pv1.p)[p, t]
                              for p in optimiser.model.Expansion for t in optimiser.model.Time)

    optimiser.optimise()

    sol_p = optimiser.values(pv1.p, 0)
    inv_p = optimiser.values(inverter.ports['cp'].p,0)

    for i in range(N_INTERVALS):
        np.testing.assert_almost_equal(sol_p[i], max(-i, -5.0))
        np.testing.assert_almost_equal(inv_p[i], max(-i, -5.0))


def test_non_curtailable_system_not_curtailed():
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min
    N_INTERVALS = time_periods

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-5.0] * N_INTERVALS, expansion_periods)
    pv1.curtailable = False
    solar.ports['solar'] = pv1

    inverter = ElectricalTellegenNode()
    inverter.add_named_electrical_ports(['cp', 'pv'])
    inverter.ports['cp'].set_flow_constraints(max_export=-5.0, max_import=5.0)

    system.add_node_obj([grid, solar, inverter])

    system.connect_ports_and_create_edge(inverter.ports['pv'], pv1)
    system.connect_ports_and_create_edge(inverter.ports['cp'], grid.ports['grid'])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    grid.ports['grid'].constrain_pos_neg(optimiser.model)
    optimiser.objective = -sum(getattr(optimiser.model, grid.ports['grid'].neg)[p, t]
                              for p in optimiser.model.Expansion for t in optimiser.model.Time)

    optimiser.optimise()

    inv_p = optimiser.values(inverter.ports['cp'].p, 0)
    sol_p = optimiser.values(pv1.p, 0)
    root_p = optimiser.values(grid.ports['grid'].p, 0)

    for i in range(N_INTERVALS):
        np.testing.assert_almost_equal(sol_p[i], -5.0)
        np.testing.assert_almost_equal(inv_p[i], -5.0)
        np.testing.assert_almost_equal(root_p[i], 5.0)


def test_curtailable_system_curtailed():
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min
    N_INTERVALS = time_periods

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-5.0] * N_INTERVALS, expansion_periods)
    pv1.curtailable = True
    solar.ports['solar'] = pv1

    inverter = ElectricalTellegenNode()
    inverter.add_named_electrical_ports(['cp', 'pv'])
    inverter.ports['cp'].set_flow_constraints(max_export=-5.0, max_import=5.0)

    system.add_node_obj([grid, solar, inverter])

    system.connect_ports_and_create_edge(inverter.ports['pv'], pv1)
    system.connect_ports_and_create_edge(inverter.ports['cp'], grid.ports['grid'])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    grid.ports['grid'].constrain_pos_neg(optimiser.model)
    optimiser.objective = -sum(getattr(optimiser.model, grid.ports['grid'].neg)[p, t]
                              for p in optimiser.model.Expansion for t in optimiser.model.Time)

    optimiser.optimise()

    inv_p = optimiser.values(inverter.ports['cp'].p, 0)
    sol_p = optimiser.values(pv1.p, 0)
    root_p = optimiser.values(grid.ports['grid'].neg, 0)

    for i in range(N_INTERVALS):
        np.testing.assert_almost_equal(sol_p[i], 0.0)
        np.testing.assert_almost_equal(inv_p[i], 0.0)
        np.testing.assert_almost_equal(root_p[i], 0.0)
