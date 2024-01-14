import os

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis.extra.numpy import arrays
from hypothesis.strategies import floats

from echo.configuration import FlowConstraint, Flows, Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import ElectricalDemand, ElectricalPort, ElectricalStorage
from echo.models.prebuilt import FlexNode, Load
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.objectives.base import ObjectiveSet
from echo.objectives.tariff import (
    BlockImportTariff,
    DemandTariffObjective,
    ImportDemandCharge,
    ImportTariff,
    PathTariff,
    ThroughputCost,
)
from echo.optimiser import optimise


@pytest.mark.parametrize(
    "minimum_demand,demand", [(0.0, 1.0), (1.0, 1.0), (2.0, 1.0), (0.0, 2.0), (1.0, 2.0), (2.0, 2.0)]
)
@pytest.mark.parametrize("battery_capacity", [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
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
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    battery1 = Node()
    b1 = ElectricalStorage(
        max_capacity=battery_capacity,
        depth_of_discharge_limit=0,
        charging_power_limit=2.0,
        discharging_power_limit=-2.0,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=0.0,
    )
    battery1.ports["battery"] = b1

    load1 = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([demand] * time_periods, expansion_periods)
    load1.ports["demand"] = l1

    dc_window = [0] * 24 + [1] * 12 + [0] * 12

    site1 = TellegenNode()
    site1.add_ports_from_list(["cp", "load", "bess"], FlexPort, units=Units.KW)
    cp1 = site1.ports["cp"]

    system.add_node_obj([grid, battery1, load1, site1])
    system.connect_ports_and_create_edge(site1.ports["bess"], b1)
    system.connect_ports_and_create_edge(site1.ports["load"], l1)
    system.connect_ports_and_create_edge(cp1, grid.ports["grid"])

    demand_tariff = DemandTariffObjective(
        component=cp1,
        demand_charges=[
            ImportDemandCharge(
                rate=1.0, window_array=dc_window, min_demand=minimum_demand, reset_periods=[time_periods]
            )
        ],
    )

    throughput_cost = ThroughputCost(component=b1, rate=0.0001)
    objective_set = ObjectiveSet(objective_list=[demand_tariff, throughput_cost])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=objective_set,
    )

    np.testing.assert_array_almost_equal(
        optimise_results.values(cp1.pos, 0)[24:36],
        np.ones(12) * max(demand - battery_capacity / 6, min(minimum_demand, demand)),
    )
    np.testing.assert_array_almost_equal(
        optimise_results.values(b1.neg, 0)[24:36],
        np.ones(12) * max(-battery_capacity / 6, min(minimum_demand - demand, 0.0)),
    )


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
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    battery1 = Node()
    b1 = ElectricalStorage(
        max_capacity=1000,
        depth_of_discharge_limit=0,
        charging_power_limit=battery_power,
        discharging_power_limit=-battery_power,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=0.0,
    )
    battery1.ports["battery"] = b1

    solar = Node()
    pv1 = ElectricalPort()
    pv1.flows = Flows.Export
    pv1.export_constraint = FlowConstraint.Fixed
    pv1.export_constraint_value = 0
    solar.ports["solar"] = pv1

    site1 = TellegenNode()
    site1.add_ports_from_list(["cp", "load", "bess", "pv"], FlexPort, units=Units.KW)
    cp1 = site1.ports["cp"]

    load1 = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array(demand, expansion_periods)
    load1.ports["demand"] = l1

    system.add_node_obj([grid, battery1, site1, solar, load1])
    system.connect_ports_and_create_edge(site1.ports["bess"], b1)
    system.connect_ports_and_create_edge(site1.ports["load"], l1)
    system.connect_ports_and_create_edge(pv1, site1.ports["pv"])
    system.connect_ports_and_create_edge(cp1, grid.ports["grid"])

    import_tariff = ImportTariff(
        component=cp1, tariff_array=[1.0] * 24 + [1.05] * 24, expansion_periods=expansion_periods
    )

    demand_tariff = DemandTariffObjective(
        component=cp1,
        demand_charges=[
            ImportDemandCharge(
                rate=10.0,
                window_array=[0] * 24 + [1] * 12 + [0] * 12,
                min_demand=minimum_demand,
                reset_periods=[time_periods],
            )
        ],
    )

    throughput_cost = ThroughputCost(component=b1, rate=0.1)

    objective_set = ObjectiveSet(objective_list=[import_tariff, demand_tariff, throughput_cost])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=objective_set,
    )

    # Check that we reduce minimum demand appropriately during the demand period
    max_gross_demand = max(demand_period_demand)
    max_net_demand = max(0.0, max_gross_demand - battery_power)

    expected_import = np.maximum(np.subtract(demand_period_demand, battery_power), max_net_demand)
    expected_import = np.minimum(expected_import, demand_period_demand)
    expected_discharge = expected_import - demand_period_demand
    np.testing.assert_array_almost_equal(optimise_results.values(cp1.pos, 0)[24:36], expected_import, 3)
    np.testing.assert_array_almost_equal(optimise_results.values(b1.neg, 0)[24:36], expected_discharge, 3)


def test_system_path_flows_adjust_to_path_tariffs():
    """Tests whether path flows reroute based on path tariffs"""

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30
    demand = 5.0
    battery_power = 2.0

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    battery1 = Node()
    b1 = ElectricalStorage(
        max_capacity=1000,
        depth_of_discharge_limit=0,
        charging_power_limit=battery_power,
        discharging_power_limit=-battery_power,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=0.0,
    )
    battery1.ports["battery"] = b1

    load1 = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([demand] * time_periods, expansion_periods)
    load1.ports["demand"] = l1

    site1 = TellegenNode()
    site1.add_ports_from_list(["cp", "load", "bess"], FlexPort, units=Units.KW)
    cp1 = site1.ports["cp"]

    system.add_node_obj([grid, battery1, load1, site1])

    system.connect_ports_and_create_edge(site1.ports["bess"], b1)
    system.connect_ports_and_create_edge(site1.ports["load"], l1)
    system.connect_ports_and_create_edge(cp1, grid.ports["grid"])

    system.create_path_objects(sources=[grid, battery1, load1], sinks=[grid, battery1, load1])

    grid_to_load = system.get_path([grid, site1, load1])

    path_tariff = PathTariff(
        component=grid_to_load, tariff_array=[0] * 24 + [1] * 24, expansion_periods=expansion_periods
    )

    objective_set = ObjectiveSet(objective_list=[path_tariff])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=objective_set,
    )

    # Check that grid to load flow is minimised in period of path tariff > 0
    net_load = demand - battery_power
    grid_to_load_vals = optimise_results.values(grid_to_load.flow_value, 0)
    np.testing.assert_array_almost_equal(grid_to_load_vals[24:36], np.ones(12) * net_load)


def test_path_flows_respect_port_constraints():
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30
    battery_power = 2
    demand = [4] * time_periods

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    battery = Node()
    b1 = ElectricalStorage(
        max_capacity=1000,
        depth_of_discharge_limit=0,
        charging_power_limit=battery_power,
        discharging_power_limit=-battery_power,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=0.0,
    )
    battery.ports["battery"] = b1

    solar = Node()
    pv1 = ElectricalPort()
    pv1.flows = Flows.Export
    pv1.export_constraint = FlowConstraint.Fixed
    pv1.export_constraint_value = 0
    solar.ports["solar"] = pv1

    site = TellegenNode()
    site.add_ports_from_list(["cp", "load", "bess", "pv"], FlexPort, units=Units.KW)
    cp1 = site.ports["cp"]

    load = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array(demand, expansion_periods)
    load.ports["demand"] = l1

    system.add_node_obj([grid, battery, site, solar, load])
    system.connect_ports_and_create_edge(site.ports["bess"], b1)
    system.connect_ports_and_create_edge(site.ports["load"], l1)
    system.connect_ports_and_create_edge(pv1, site.ports["pv"])
    system.connect_ports_and_create_edge(cp1, grid.ports["grid"])

    system.create_path_objects(sources=[grid, battery, solar, load], sinks=[grid, battery, solar, load])

    tp_cost = ThroughputCost(component=b1, rate=0.2)

    objective_set = ObjectiveSet(objective_list=[tp_cost])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=objective_set,
    )

    # Check solar flows are zero
    solar_to_bess = system.paths[(solar.node_name, site.node_name, battery.node_name)]
    solar_to_load = system.paths[(solar.node_name, site.node_name, load.node_name)]
    solar_to_grid = system.paths[(solar.node_name, site.node_name, grid.node_name)]

    bess_to_solar = system.paths[(battery.node_name, site.node_name, solar.node_name)]
    load_to_solar = system.paths[(load.node_name, site.node_name, solar.node_name)]
    grid_to_solar = system.paths[(battery.node_name, site.node_name, solar.node_name)]

    np.testing.assert_array_almost_equal(optimise_results.values(solar_to_bess.flow_value, 0), [0] * time_periods, 3)
    np.testing.assert_array_almost_equal(optimise_results.values(solar_to_load.flow_value, 0), [0] * time_periods, 3)
    np.testing.assert_array_almost_equal(optimise_results.values(solar_to_grid.flow_value, 0), [0] * time_periods, 3)

    np.testing.assert_array_almost_equal(optimise_results.values(bess_to_solar.flow_value, 0), [0] * time_periods, 3)
    np.testing.assert_array_almost_equal(optimise_results.values(load_to_solar.flow_value, 0), [0] * time_periods, 3)
    np.testing.assert_array_almost_equal(optimise_results.values(grid_to_solar.flow_value, 0), [0] * time_periods, 3)


# This test sometimes fails due to the non-deterministic nature of optimizations.
# We don't want this test to block a merging a pull request due to a failing run of the Github Action
@pytest.mark.skipif(os.getenv("CI") == "true", reason="don't perform non-deterministic test in Github action")
def test_demand_tariff_reset_periods():
    expansion_periods = 1
    expansion_periods = 1
    day_periods = 48
    num_days = 2
    time_periods = day_periods * num_days
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["load"], FlexPort, units=Units.KW)

    load = Node()
    l1 = ElectricalDemand()
    demand = np.random.randint(0, 100, time_periods)
    l1.add_demand_profile_from_array(demand, expansion_periods)
    load.ports["demand"] = l1

    system.add_node_obj([grid, load])
    system.connect_ports_and_create_edge(grid.ports["load"], l1)

    tariff_array_day = [0] * 12 + [1] * 12 + [0] * 12 + [1] * 12

    reset_periods = [day_periods] * num_days
    import_charge = ImportDemandCharge(rate=1.0, reset_periods=reset_periods, window_array=tariff_array_day * num_days)

    dt = DemandTariffObjective(component=l1, demand_charges=[import_charge])

    objective_set = ObjectiveSet(objective_list=[dt])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=objective_set,
    )

    max_demand = optimise_results.values(import_charge.max_demand_val)
    demand_filtered = demand * np.array(tariff_array_day * num_days)
    reset_periods.insert(0, 0)
    val = np.cumsum(reset_periods)
    for i in range(num_days):
        max_opt = max_demand[i]
        max_calc = max(demand_filtered[val[i] : val[i + 1]])
        np.testing.assert_almost_equal(max_opt, max_calc, 5)


def test_block_tariff():
    time_periods = 24
    interval_duration = 60
    expansion_periods = 1

    system = OptimisationGraph()

    grid = FlexNode(node_name="grid", port_name="grid", port_unit=Units.KW)
    load = Load(node_name="load", port_name="load", profile=[10] * time_periods, port_unit=Units.KW)

    system.add_nodes_from([grid, load])
    system.connect_ports_and_create_edge(load.ports["load"], grid.ports["grid"], nodes=("grid", "load"))

    block_tariff = BlockImportTariff(
        component=load.ports["load"], blocks=[50, 100], rates=[1, 2, 3], reset_periods=[5, 19]
    )

    objective_set = ObjectiveSet(objective_list=[block_tariff])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=objective_set,
    )

    print()
