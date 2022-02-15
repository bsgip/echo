import numpy as np
import pandas as pd
from datetime import time, datetime

# from c3x.neon.objectives.tariffs.demand import DemandTariff, DemandTariffVersion, DemandCharge, DemandTariffObjective, \
#     Window, TimePeriod, Day
# from c3x.neon.objectives.throughput import ThroughputCost
# from c3x.neon.objectives.tariffs import ImportTariff
# from c3x.neon.models import Junction, Storage, Load, Gen
# from c3x.neon.objectives import Objective, ObjectiveSet
# from c3x.neon.optimiser import Optimiser

from echo_models import ElectricalDemand, ElectricalGeneration, ElectricalStorage, ElectricalNode, \
    OptimisationGraph, Tariff, Node, Port, Edge, Transform, ElectricalPort, DemandTariff, ElectricalTellegenNode
from echo_optimiser import EchoOptimiser
from configuration import NodeRule, TransformRule, FlowConstraint, Flows, PathRule

from hypothesis.extra.numpy import arrays
from hypothesis.strategies import floats
from hypothesis import given, settings


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
                           throughput_cost=0.0,
                           initial_state_of_charge=48.0)
    battery.ports['battery_asset'] = b1

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-4] * 24 + [0] * 24, expansion_periods)
    solar.ports['solar'] = pv1

    inverter = ElectricalTellegenNode()
    inverter.add_named_electrical_ports(['cp', 'bess', 'pv'])
    inverter.ports['cp'].set_flow_constraints(max_export=-5.0, max_import=5.0)

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

    grid.ports['grid'].path_rule = PathRule.SourceOrSink
    b1.path_rule = PathRule.SourceOrSink
    pv1.path_rule = PathRule.SourceOrSink
    l1.path_rule = PathRule.SourceOrSink
    system.generate_all_paths()

    bess_to_g = system.path_obj[(battery, inverter, cp, grid)]
    bess_to_g.fcas_raise = True

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system
    )

    optimiser.objective = sum(getattr(optimiser.model, bess_to_g.contingency_raise)[p, t]
                              for p in optimiser.model.Expansion for t in optimiser.model.Time) * -1

    optimiser.optimise()

    cont_neg_p = optimiser.values(bess_to_g.contingency_raise, 0)*-1

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
                           throughput_cost=0.0,
                           initial_state_of_charge=48.0)
    battery.ports['battery_asset'] = b1

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-4] * time_periods, expansion_periods)
    pv1.curtailable = True
    solar.ports['solar'] = pv1

    inverter = ElectricalTellegenNode()
    inverter.add_named_electrical_ports(['cp', 'bess', 'pv'])
    inverter.ports['cp'].set_flow_constraints(max_export=-5.0, max_import=5.0)

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

    grid.ports['grid'].path_rule = PathRule.SourceOrSink
    b1.path_rule = PathRule.SourceOrSink
    pv1.path_rule = PathRule.SourceOrSink
    l1.path_rule = PathRule.SourceOrSink
    system.generate_all_paths()

    bess_to_g = system.path_obj[(battery, inverter, cp, grid)]
    bess_to_g.fcas_raise = True

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system
    )

    optimiser.objective = sum(getattr(optimiser.model, bess_to_g.contingency_raise)[p, t]
                              for p in optimiser.model.Expansion for t in optimiser.model.Time) * -1

    optimiser.optimise()

    cont_neg_p = optimiser.values(bess_to_g.contingency_raise, 0)*-1
    sol_p = optimiser.values(pv1.port_name,0)

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
                           throughput_cost=0.0,
                           initial_state_of_charge=0.0)
    battery.ports['battery_asset'] = b1

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-4] * time_periods, expansion_periods)
    solar.ports['solar'] = pv1

    inverter = ElectricalTellegenNode()
    inverter.add_named_electrical_ports(['cp', 'bess', 'pv'])
    inverter.ports['cp'].set_flow_constraints(max_export=-5.0, max_import=5.0)

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

    grid.ports['grid'].path_rule = PathRule.SourceOrSink
    b1.path_rule = PathRule.SourceOrSink
    pv1.path_rule = PathRule.SourceOrSink
    l1.path_rule = PathRule.SourceOrSink
    system.generate_all_paths()

    bess_to_g = system.path_obj[(battery, inverter, cp, grid)]
    bess_to_g.fcas_raise = True

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system
    )

    optimiser.objective = sum(getattr(optimiser.model, bess_to_g.contingency_raise)[p, t]
                              for p in optimiser.model.Expansion for t in optimiser.model.Time) * -1

    optimiser.optimise()

    cont_neg_p = optimiser.values(bess_to_g.contingency_raise, 0)*-1

    for i in range(time_periods):
        np.testing.assert_almost_equal(cont_neg_p[i], 0.0, 6)
