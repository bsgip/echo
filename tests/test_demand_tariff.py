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
    OptimisationGraph, Tariff, Node, Port, Edge, Transform, ElectricalPort, CarbonPort, FlexiblePort, DemandTariff
from echo_optimiser import EchoOptimiser
from configuration import NodeRule, TransformRule, FlowConstraint, Flows, PathRule

from hypothesis.extra.numpy import arrays
from hypothesis.strategies import floats
from hypothesis import given, settings


import os

SOLVER = os.environ.get('OPTIMISER_ENGINE')
SOLVER_EXECUTABLE = os.environ.get('OPTIMISER_ENGINE_EXECUTABLE')


import pytest

@pytest.mark.solver('milp')
@pytest.mark.parametrize(
    "minimum_demand,demand",
    [
        (0.0, 1.0),
        (1.0, 1.0),
        (2.0, 1.0),
        (0.0, 2.0),
        (1.0, 2.0),
        (2.0, 2.0),
    ]
)
@pytest.mark.parametrize(
    "battery_capacity",
    [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]

)
def test_system_precharges_for_demand_tariff(demand, minimum_demand, battery_capacity):
    """
    Test that we appropriately minimise the demand charge associated with the demand period.
    The tests use the minimal objective function that gives a well-defined result,
    which in this case is the combination of DemandCharges and ThroughputCost.
    ThroughputCost is required to prevent unnecessary battery cycling.
    """

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    dc_window = [0] * 24 + [1] * 12 + [0] * 12

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    battery1 = Node()
    b1 = ElectricalStorage(max_capacity=battery_capacity,
                           depth_of_discharge_limit=0,
                           charging_power_limit=2.0,
                           discharging_power_limit=-2.0,
                           charging_efficiency=1,
                           discharging_efficiency=1,
                           throughput_cost=0.0,
                           initial_state_of_charge=0.0)
    battery1.ports['battery'] = b1

    load1 = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([demand] * time_periods, expansion_periods)
    load1.ports['demand'] = l1

    tariff = DemandTariff(
        window=dc_window,
        demand_charge=1.0,
        min_demand=minimum_demand,
        expansion_periods=expansion_periods
    )

    site1 = ElectricalNode()
    site1.add_named_electrical_ports(['cp', 'load', 'bess'])
    site1.node_rule = NodeRule.Tellegen
    cp1 = site1.ports['cp']

    cp1.has_tariff = True
    cp1.tariff = tariff

    system.add_node_obj([grid, battery1, load1, site1])

    bess_edge1 = Edge(vertices=[site1.ports['bess'], b1])
    load_edge1 = Edge(vertices=[site1.ports['load'], l1])
    grid_edge = Edge(vertices=[cp1, grid.ports['grid']])

    system.add_edge_obj([bess_edge1, load_edge1, grid_edge])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system
    )

    optimiser.optimise()

    np.testing.assert_array_almost_equal(optimiser.values(cp1.positive_port_component, 0)[24:36],
                                         np.ones(12) * max(demand - battery_capacity / 12, min(minimum_demand, demand)))
    np.testing.assert_array_almost_equal(optimiser.values(b1.negative_port_component, 0)[24:36],
                                         np.ones(12) * max(-battery_capacity / 12, min(minimum_demand - demand, 0.0)))


@pytest.mark.solver('milp')
@pytest.mark.slow
@settings(deadline=3000)
@given(arrays(float, 12, elements=floats(1, 100)))
def test_demand_charge_minimised_given_random_demand_in_period(demand_period_demand):
    minimum_demand = 0.0
    demand = np.concatenate([np.zeros(24), demand_period_demand, np.ones(12)])

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30
    battery_power = 2

    import_tariff = [1.0] * 24 + [1.05] * 24
    dc_window = [0] * 24 + [1] * 12 + [0] * 12

    it = Tariff()
    it.add_import_tariff_profile_from_array(import_tariff, expansion_periods)
    it.add_export_tariff_profile_from_array([0]*time_periods, expansion_periods)

    dc = DemandTariff(
        window=dc_window,
        demand_charge=10.0,
        min_demand=minimum_demand,
        expansion_periods=expansion_periods
    )

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    battery1 = Node()
    b1 = ElectricalStorage(max_capacity=1000,
                           depth_of_discharge_limit=0,
                           charging_power_limit=battery_power,
                           discharging_power_limit=-battery_power,
                           charging_efficiency=1,
                           discharging_efficiency=1,
                           throughput_cost=0.2,
                           initial_state_of_charge=0.0)
    battery1.ports['battery'] = b1

    solar = Node()
    pv1 = ElectricalPort()
    pv1.flows = Flows.Export
    pv1.export_constraint = FlowConstraint.Fixed
    pv1.export_constraint_value = 0
    solar.ports['solar'] = pv1

    site1 = ElectricalNode()
    site1.add_named_electrical_ports(['cp', 'load', 'bess', 'pv'])
    site1.node_rule = NodeRule.Tellegen
    cp1 = site1.ports['cp']

    cp1.has_tariff = True
    cp1.tariff = it
    cp1.demand_tariff = dc

    load1 = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array(demand, expansion_periods)
    load1.ports['demand'] = l1

    bess_edge1 = Edge(vertices=[site1.ports['bess'], b1])
    load_edge1 = Edge(vertices=[site1.ports['load'], l1])
    pv_edge = Edge(vertices=[pv1, site1.ports['pv']])
    grid_edge = Edge(vertices=[cp1, grid.ports['grid']])

    system.add_node_obj([grid, battery1, site1, solar, load1])
    system.add_edge_obj([bess_edge1, load_edge1, pv_edge, grid_edge])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system
    )

    optimiser.optimise()


    # Check that we reduce minimum demand appropriately during the demand period
    max_gross_demand = max(demand_period_demand)
    max_net_demand = max(0.0, max_gross_demand - battery_power)

    expected_import = np.maximum(np.subtract(demand_period_demand, battery_power), max_net_demand)
    expected_import = np.minimum(expected_import, demand_period_demand)
    expected_discharge = expected_import - demand_period_demand
    np.testing.assert_array_almost_equal(optimiser.values(cp1.positive_port_component,0)[24:36],
                                         expected_import,
                                         3)
    np.testing.assert_array_almost_equal(optimiser.values(b1.negative_port_component,0)[24:36],
                                         expected_discharge,
                                         3
                                         )
