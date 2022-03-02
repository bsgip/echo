import numpy as np

from echo_models import *
from echo_optimiser import EchoOptimiser
from configuration import *
from objectives import *

import os

SOLVER = os.environ.get('OPTIMISER_ENGINE', 'cplex')
SOLVER_EXECUTABLE = None

def test_negative_contingency_respects_hybrid_inverter_constraints():

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    battery = Node()
    b1 = ElectricalStorage(max_capacity=48,
                           depth_of_discharge_limit=0,
                           charging_power_limit=0.0,
                           discharging_power_limit=-5.0,
                           charging_efficiency=1,
                           discharging_efficiency=1,
                           initial_state_of_charge=1.0)
    battery.ports['battery_asset'] = b1

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-4] * 24 + [0] * 24, expansion_periods)
    solar.ports['solar'] = pv1

    inverter = Inverter(max_import=5, max_export=-5, dc_ac_efficiency=1, ac_dc_efficiency=1)
    inverter.add_ac_port('cp')
    inverter.add_dc_port('bess')
    inverter.add_dc_port('pv')

    cp = ElectricalTellegenNode()
    cp.add_named_electrical_ports(['load', 'inv', 'grid'])

    load = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([6] * time_periods, expansion_periods)
    load.ports['load'] = l1

    system.add_node_obj([grid, cp, load, battery, solar, inverter])

    system.connect_ports_and_create_edge(inverter.ports['bess'], b1)
    system.connect_ports_and_create_edge(inverter.ports['pv'], pv1)
    system.connect_ports_and_create_edge(cp.ports['load'], l1)
    system.connect_ports_and_create_edge(inverter.ports['cp'], cp.ports['inv'])
    system.connect_ports_and_create_edge(cp.ports['grid'], grid.ports['grid'])

    system.create_path_objects(sources=[grid, battery, solar, load], sinks=[grid, battery, solar, load])
    bess_to_g = system.paths[(battery, inverter, cp, grid)]
    contingency_neg = ContingencyNegative(component=bess_to_g, duration=10.0)

    objective_set = ObjectiveSet(objective_list=[contingency_neg])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=objective_set
    )

    optimiser.optimise()

    cont_neg_p = optimiser.values(bess_to_g.contingency_neg, 0)

    for i in range(time_periods // 2):
        np.testing.assert_almost_equal(cont_neg_p[i], -1.0)
    for i in range(time_periods // 2, time_periods):
        np.testing.assert_almost_equal(cont_neg_p[i], -5.0)


def test_negative_contingency_maximisation_curtails_solar():
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    battery = Node()
    b1 = ElectricalStorage(max_capacity=48,
                           depth_of_discharge_limit=0,
                           charging_power_limit=0.0,
                           discharging_power_limit=-5.0,
                           charging_efficiency=1,
                           discharging_efficiency=1,
                           initial_state_of_charge=1.0)
    battery.ports['battery_asset'] = b1

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-4] * time_periods, expansion_periods)
    pv1.curtailable = True
    solar.ports['solar'] = pv1

    inverter = Inverter(max_import=5, max_export=-5, dc_ac_efficiency=1, ac_dc_efficiency=1)
    inverter.add_ac_port('cp')
    inverter.add_dc_port('bess')
    inverter.add_dc_port('pv')

    cp = ElectricalTellegenNode()
    cp.add_named_electrical_ports(['load', 'inv', 'grid'])

    load = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([6] * time_periods, expansion_periods)
    load.ports['load'] = l1

    system.add_node_obj([grid, cp, load, battery, solar, inverter])

    system.connect_ports_and_create_edge(inverter.ports['bess'], b1)
    system.connect_ports_and_create_edge(inverter.ports['pv'], pv1)
    system.connect_ports_and_create_edge(cp.ports['load'], l1)
    system.connect_ports_and_create_edge(inverter.ports['cp'], cp.ports['inv'])
    system.connect_ports_and_create_edge(cp.ports['grid'], grid.ports['grid'])

    system.create_path_objects(sources=[grid, battery, solar, load], sinks=[grid, battery, solar, load])

    bess_to_g = system.paths[(battery, inverter, cp, grid)]
    contingency_neg = ContingencyNegative(component=bess_to_g, duration=10.0)

    objective_set = ObjectiveSet(objective_list=[
        contingency_neg
    ]
    )

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=objective_set
    )

    optimiser.optimise()

    cont_neg_p = optimiser.values(bess_to_g.contingency_neg, 0)
    sol_p = optimiser.values(pv1.p, 0)

    for i in range(time_periods // 2):
        np.testing.assert_almost_equal(cont_neg_p[i], -5.0)
        np.testing.assert_almost_equal(sol_p[i], 0.0)

    for i in range(time_periods // 2, time_periods):
        np.testing.assert_almost_equal(cont_neg_p[i], -5.0)
        np.testing.assert_almost_equal(sol_p[i], 0.0)


def test_negative_contingency_calculation_with_no_available_energy():

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    battery = Node()
    b1 = ElectricalStorage(max_capacity=48,
                           depth_of_discharge_limit=0,
                           charging_power_limit=0.0,
                           discharging_power_limit=-5.0,
                           charging_efficiency=1,
                           discharging_efficiency=1,
                           initial_state_of_charge=0.0)
    battery.ports['battery_asset'] = b1

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-4] * time_periods, expansion_periods)
    solar.ports['solar'] = pv1

    inverter = Inverter(max_import=5, max_export=-5, dc_ac_efficiency=1, ac_dc_efficiency=1)
    inverter.add_ac_port('cp')
    inverter.add_dc_port('bess')
    inverter.add_dc_port('pv')

    cp = Node()
    cp.add_named_electrical_ports(['load', 'inv', 'grid'])
    cp.node_rule = NodeRule.Tellegen

    load = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([6.0] * time_periods, expansion_periods)
    load.ports['load'] = l1

    system.add_node_obj([grid, cp, load, battery, solar, inverter])

    system.connect_ports_and_create_edge(inverter.ports['bess'], b1)
    system.connect_ports_and_create_edge(inverter.ports['pv'], pv1)
    system.connect_ports_and_create_edge(cp.ports['load'], l1)
    system.connect_ports_and_create_edge(inverter.ports['cp'], cp.ports['inv'])
    system.connect_ports_and_create_edge(cp.ports['grid'], grid.ports['grid'])

    system.create_path_objects(sources=[grid, battery, solar, load], sinks=[grid, battery, solar, load])

    bess_to_g = system.paths[(battery, inverter, cp, grid)]
    contingency_neg = ContingencyNegative(component=bess_to_g, duration=10.0)

    objective_set = ObjectiveSet(objective_list=[
        contingency_neg
    ]
    )

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set = objective_set
    )

    optimiser.optimise()

    cont_neg_p = optimiser.values(bess_to_g.contingency_neg, 0)

    for i in range(time_periods):
        np.testing.assert_almost_equal(cont_neg_p[i], 0.0, 5)  #Had to update to 5dp
