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
    OptimisationGraph, Tariff, Node, Port, Edge, Transform, ElectricalPort, DemandTariff
from echo_optimiser import EchoOptimiser
from configuration import NodeRule, TransformRule, FlowConstraint, Flows, PathRule

from hypothesis.extra.numpy import arrays
from hypothesis.strategies import floats
from hypothesis import given, settings


import os

SOLVER = os.environ.get('OPTIMISER_ENGINE', 'cplex')
SOLVER_EXECUTABLE = None


import pytest

def test_hybrid_inverter_limits_battery_discharge_rate():

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    battery = Node()
    b1 = ElectricalStorage(max_capacity=48,
                           depth_of_discharge_limit=0,
                           charging_power_limit=5.0,
                           discharging_power_limit=-5.0,
                           charging_efficiency=1,
                           discharging_efficiency=1,
                           throughput_cost=0.0,
                           initial_state_of_charge=48.0)
    battery.ports['battery_asset'] = b1

    solar = Node()
    pv1 = ElectricalPort()
    pv1.flows = Flows.Export
    pv1.export_constraint = FlowConstraint.Fixed
    pv1.export_constraint_value = -4
    solar.ports['solar'] = pv1

    inverter = Node()
    inverter.add_named_electrical_ports(['cp', 'bess', 'pv'])
    inverter.ports['cp'].import_constraint = FlowConstraint.Fixed
    inverter.ports['cp'].import_constraint_value = 5
    inverter.ports['cp'].export_constraint = FlowConstraint.Fixed
    inverter.ports['cp'].export_constraint_value = -5
    inverter.node_rule = NodeRule.Tellegen

    cp = Node()
    cp.add_named_electrical_ports(['load', 'inv', 'grid'])
    cp.node_rule = NodeRule.Tellegen

    load = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([6]*time_periods, expansion_periods)
    load.ports['load'] = l1

    # Create edge objects
    bess_edge = Edge(vertices=[inverter.ports['bess'], b1])
    pv_edge = Edge(vertices=[inverter.ports['pv'], pv1])
    load_edge = Edge(vertices=[cp.ports['load'], l1])
    inv_edge = Edge(vertices=[inverter.ports['cp'], cp.ports['inv']])
    grid_edge = Edge(vertices=[cp.ports['grid'], grid.ports['grid']])

    system.add_node_obj([grid, cp, load, battery, solar, inverter])
    system.add_edge_obj([bess_edge, load_edge, pv_edge, grid_edge, inv_edge])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system
    )

    optimiser.objective = sum(getattr(optimiser.model, grid.ports['grid'].port_name)[p, t]
                              for p in optimiser.model.Expansion for t in optimiser.model.Time) * -1

    optimiser.optimise()

    for i in range(time_periods):
        np.testing.assert_almost_equal(optimiser.values(cp.ports['grid'].port_name, 0)[i], 1.0)



def test_hybrid_inverter_limits_path_flows():

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    battery = Node()
    b1 = ElectricalStorage(max_capacity=48,
                           depth_of_discharge_limit=0,
                           charging_power_limit=5.0,
                           discharging_power_limit=-5.0,
                           charging_efficiency=1,
                           discharging_efficiency=1,
                           throughput_cost=0.0,
                           initial_state_of_charge=48.0)
    battery.ports['battery_asset'] = b1

    solar = Node()
    pv1 = ElectricalPort()
    pv1.flows = Flows.Export
    pv1.export_constraint = FlowConstraint.Fixed
    pv1.export_constraint_value = -4
    solar.ports['solar'] = pv1

    inverter = Node()
    inverter.add_named_electrical_ports(['cp', 'bess', 'pv'])
    inverter.ports['cp'].import_constraint = FlowConstraint.Fixed
    inverter.ports['cp'].import_constraint_value = 5
    inverter.ports['cp'].export_constraint = FlowConstraint.Fixed
    inverter.ports['cp'].export_constraint_value = -5
    inverter.node_rule = NodeRule.Tellegen

    cp = Node()
    cp.add_named_electrical_ports(['load', 'inv', 'grid'])
    cp.node_rule = NodeRule.Tellegen

    load = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([6]*time_periods, expansion_periods)
    load.ports['load'] = l1

    # Create edge objects
    bess_edge = Edge(vertices=[inverter.ports['bess'], b1])
    pv_edge = Edge(vertices=[inverter.ports['pv'], pv1])
    load_edge = Edge(vertices=[cp.ports['load'], l1])
    inv_edge = Edge(vertices=[inverter.ports['cp'], cp.ports['inv']])
    grid_edge = Edge(vertices=[cp.ports['grid'], grid.ports['grid']])

    system.add_node_obj([grid, cp, load, battery, solar, inverter])
    system.add_edge_obj([bess_edge, load_edge, pv_edge, grid_edge, inv_edge])

    grid.ports['grid'].path_rule = PathRule.SourceOrSink
    b1.path_rule = PathRule.SourceOrSink
    pv1.path_rule = PathRule.SourceOrSink
    l1.path_rule = PathRule.SourceOrSink
    system.generate_all_paths()

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system
    )

    optimiser.objective = sum(getattr(optimiser.model, grid.ports['grid'].port_name)[p, t]
                              for p in optimiser.model.Expansion for t in optimiser.model.Time) * -1

    optimiser.optimise()

    bess_to_load = optimiser.values(system.path_obj[(battery, inverter, cp, load)].flow_value, 0)
    bess_to_grid = optimiser.values(system.path_obj[(battery, inverter, cp, grid)].flow_value, 0)
    solar_to_load = optimiser.values(system.path_obj[(solar, inverter, cp, load)].flow_value, 0)
    solar_to_grid = optimiser.values(system.path_obj[(solar, inverter, cp, grid)].flow_value, 0)

    # Check all flows through inverter respect inverter limits
    for i in range(time_periods):
        np.testing.assert_almost_equal(bess_to_load[i] + bess_to_grid[i] + solar_to_load[i] + solar_to_grid[i],
                inverter.ports['cp'].export_constraint_value*-1)
