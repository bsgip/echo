import numpy as np
import pytest

from echo.echo_models import *
from echo.echo_optimiser import EchoOptimiser
from echo.configuration import *
from echo.objectives import *

import os

SOLVER = os.environ.get('OPTIMISER_ENGINE','cplex')
SOLVER_EXECUTABLE = None



N_INTERVALS = 48


def test_export_slack_var_is_minimised():
    """ Connect curtailable solar to a connection pt with a flow constraint and slack vars enabled.
    The optimiser should curtail the solar rather than allowing the slack to be nonzero."""
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
    inverter.ports['cp'].set_flow_constraints(max_export=-5.0, max_import=5.0, slack=True)

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

    optimiser.objective += sum(getattr(optimiser.model, pv1.port_name)[p, t]
                              for p in optimiser.model.Expansion for t in optimiser.model.Time)

    optimiser.optimise()

    inv_export_slack = optimiser.values(inverter.ports['cp'].export_slack, 0)

    np.testing.assert_almost_equal(inv_export_slack, 0)


def test_import_slack_var_is_minimised():

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min
    N_INTERVALS = time_periods

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])
    grid.ports['grid'].set_flow_constraints(max_export=-5.0, max_import=5.0, slack=True)

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-float(i) for i in range(N_INTERVALS)], expansion_periods)
    pv1.curtailable = True
    solar.ports['solar'] = pv1

    inverter = ElectricalTellegenNode()
    inverter.add_named_electrical_ports(['cp', 'pv'])

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

    optimiser.objective += sum(getattr(optimiser.model, pv1.port_name)[p, t]
                              for p in optimiser.model.Expansion for t in optimiser.model.Time)

    optimiser.optimise()

    g_import_slack = optimiser.values(grid.ports['grid'].import_slack, 0)
    g = optimiser.values(grid.ports['grid'].port_name, 0)

    np.testing.assert_almost_equal(g_import_slack, 0)


def test_slack_vars_take_up_slack_when_forced_to():

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
    inverter.ports['cp'].set_flow_constraints(max_export=-5.0, max_import=5.0, slack=True)


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

    optimiser.optimise()

    inv_export_slack = optimiser.values(inverter.ports['cp'].export_slack,0)
    sol_p = optimiser.values(pv1.port_name, 0)

    for i in range(N_INTERVALS):
        np.testing.assert_almost_equal(inv_export_slack, max(0, -1*sol_p[i]-5))