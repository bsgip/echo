import numpy as np
import pytest

from echo.echo_models import *
from echo.echo_optimiser import EchoOptimiser
from echo.configuration import *
from echo.objectives import *

from hypothesis.extra.numpy import arrays
from hypothesis.strategies import floats
from hypothesis import given, settings


import os

SOLVER = os.environ.get('OPTIMISER_ENGINE','cplex')
SOLVER_EXECUTABLE = None



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
                           initial_state_of_charge=0.0)
    battery1.ports['battery'] = b1

    load1 = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([demand] * time_periods, expansion_periods)
    load1.ports['demand'] = l1

    dc_window = [0] * 24 + [1] * 12 + [0] * 12

    site1 = ElectricalTellegenNode()
    site1.add_named_electrical_ports(['cp', 'load', 'bess'])
    cp1 = site1.ports['cp']

    system.add_node_obj([grid, battery1, load1, site1])

    bess_edge1 = Edge(vertices=[site1.ports['bess'], b1])
    load_edge1 = Edge(vertices=[site1.ports['load'], l1])
    grid_edge = Edge(vertices=[cp1, grid.ports['grid']])

    system.add_edge_obj([bess_edge1, load_edge1, grid_edge])

    demand_tariff = ImportDemandTariffObjective(component=cp1,
                                          demand_charges=[DemandCharge(rate=1.0, window_array=dc_window, min_demand=minimum_demand)])

    throughput_cost = ThroughputCost(component=b1, rate=0.0001)
    objective_set = ObjectiveSet(objective_list=[demand_tariff, throughput_cost])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=objective_set
    )

    optimiser.optimise()

    np.testing.assert_array_almost_equal(optimiser.values(cp1.pos, 0)[24:36],
                                         np.ones(12) * max(demand - battery_capacity / 6, min(minimum_demand, demand)))
    np.testing.assert_array_almost_equal(optimiser.values(b1.neg, 0)[24:36],
                                         np.ones(12) * max(-battery_capacity / 6, min(minimum_demand - demand, 0.0)))


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
                           initial_state_of_charge=0.0)
    battery1.ports['battery'] = b1

    solar = Node()
    pv1 = ElectricalPort()
    pv1.flows = Flows.Export
    pv1.export_constraint = FlowConstraint.Fixed
    pv1.export_constraint_value = 0
    solar.ports['solar'] = pv1

    site1 = ElectricalTellegenNode()
    site1.add_named_electrical_ports(['cp', 'load', 'bess', 'pv'])
    cp1 = site1.ports['cp']

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

    import_tariff = ImportTariff(component=cp1,
                                 tariff_array=[1.0] * 24 + [1.05] * 24,
                                 expansion_periods=expansion_periods)

    demand_tariff = ImportDemandTariffObjective(component=cp1,
                                          demand_charges=[DemandCharge(rate=10.0, window_array=[0] * 24 + [1] * 12 + [0] * 12, min_demand=minimum_demand)])

    throughput_cost = ThroughputCost(component=b1, rate=0.1)

    objective_set = ObjectiveSet(objective_list=[import_tariff, demand_tariff, throughput_cost])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=objective_set
    )

    optimiser.optimise()

    # Check that we reduce minimum demand appropriately during the demand period
    max_gross_demand = max(demand_period_demand)
    max_net_demand = max(0.0, max_gross_demand - battery_power)

    expected_import = np.maximum(np.subtract(demand_period_demand, battery_power), max_net_demand)
    expected_import = np.minimum(expected_import, demand_period_demand)
    expected_discharge = expected_import - demand_period_demand
    np.testing.assert_array_almost_equal(optimiser.values(cp1.pos, 0)[24:36],
                                         expected_import,
                                         3)
    np.testing.assert_array_almost_equal(optimiser.values(b1.neg, 0)[24:36],
                                         expected_discharge,
                                         3
                                         )


def test_system_path_flows_adjust_to_path_tariffs():
    """ Tests whether path flows reroute based on path tariffs"""

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30
    demand = 5.0
    battery_power = 2.0

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
                           initial_state_of_charge=0.0)
    battery1.ports['battery'] = b1

    load1 = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([demand]*time_periods, expansion_periods)
    load1.ports['demand'] = l1

    site1 = ElectricalNode()
    site1.add_named_electrical_ports(['cp', 'load', 'bess'])
    site1.node_rule = NodeRule.Tellegen
    cp1 = site1.ports['cp']

    system.add_node_obj([grid, battery1, load1, site1])

    bess_edge1 = Edge(vertices=[site1.ports['bess'], b1])
    load_edge1 = Edge(vertices=[site1.ports['load'], l1])
    grid_edge = Edge(vertices=[cp1, grid.ports['grid']])

    system.add_edge_obj([bess_edge1, load_edge1, grid_edge])

    system.create_path_objects(sources=[grid, battery1, load1], sinks=[grid, battery1, load1])

    grid_to_load = system.paths[(grid, site1, load1)]

    path_tariff = PathTariff(component=grid_to_load,
                             tariff_array=[0] * 24 + [1] * 24,
                             expansion_periods=expansion_periods)

    objective_set = ObjectiveSet(objective_list=[path_tariff])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=objective_set
    )

    optimiser.optimise()

    # Check that grid to load flow is minimised in period of path tariff > 0
    net_load = demand - battery_power
    grid_to_load_vals = optimiser.values(grid_to_load.flow_value, 0)
    np.testing.assert_array_almost_equal(grid_to_load_vals[24:36], np.ones(12) * net_load)


def test_path_flows_respect_port_constraints():

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30
    battery_power = 2
    demand = [4] * time_periods

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    battery = Node()
    b1 = ElectricalStorage(max_capacity=1000,
                           depth_of_discharge_limit=0,
                           charging_power_limit=battery_power,
                           discharging_power_limit=-battery_power,
                           charging_efficiency=1,
                           discharging_efficiency=1,
                           initial_state_of_charge=0.0)
    battery.ports['battery'] = b1

    solar = Node()
    pv1 = ElectricalPort()
    pv1.flows = Flows.Export
    pv1.export_constraint = FlowConstraint.Fixed
    pv1.export_constraint_value = 0
    solar.ports['solar'] = pv1

    site = ElectricalNode()
    site.add_named_electrical_ports(['cp', 'load', 'bess', 'pv'])
    site.node_rule = NodeRule.Tellegen
    cp1 = site.ports['cp']

    load = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array(demand, expansion_periods)
    load.ports['demand'] = l1

    bess_edge1 = Edge(vertices=[site.ports['bess'], b1])
    load_edge1 = Edge(vertices=[site.ports['load'], l1])
    pv_edge = Edge(vertices=[pv1, site.ports['pv']])
    grid_edge = Edge(vertices=[cp1, grid.ports['grid']])

    system.add_node_obj([grid, battery, site, solar, load])
    system.add_edge_obj([bess_edge1, load_edge1, pv_edge, grid_edge])

    system.create_path_objects(sources=[grid, battery, solar, load], sinks=[grid, battery, solar, load])

    tp_cost = ThroughputCost(component=b1,
                             rate=0.2)

    objective_set = ObjectiveSet(objective_list=[tp_cost])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=objective_set
    )

    optimiser.optimise()

    # Check solar flows are zero
    solar_to_bess = system.paths[(solar, site, battery)]
    solar_to_load = system.paths[(solar, site, load)]
    solar_to_grid = system.paths[(solar, site, grid)]

    bess_to_solar = system.paths[(battery, site, solar)]
    load_to_solar = system.paths[(load, site, solar)]
    grid_to_solar = system.paths[(battery, site, solar)]

    np.testing.assert_array_almost_equal(optimiser.values(solar_to_bess.flow_value, 0), [0] * time_periods, 3)
    np.testing.assert_array_almost_equal(optimiser.values(solar_to_load.flow_value, 0), [0] * time_periods, 3)
    np.testing.assert_array_almost_equal(optimiser.values(solar_to_grid.flow_value, 0), [0] * time_periods, 3)

    np.testing.assert_array_almost_equal(optimiser.values(bess_to_solar.flow_value, 0), [0] * time_periods, 3)
    np.testing.assert_array_almost_equal(optimiser.values(load_to_solar.flow_value, 0), [0] * time_periods, 3)
    np.testing.assert_array_almost_equal(optimiser.values(grid_to_solar.flow_value, 0), [0] * time_periods, 3)

