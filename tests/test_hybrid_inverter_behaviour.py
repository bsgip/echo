import numpy as np

from echo.configuration import NodeRule, Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import ElectricalDemand, ElectricalGeneration, ElectricalStorage, Inverter
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.objectives.base import ObjectiveSet, TotalFlow
from echo.optimiser import optimise


def test_hybrid_inverter_limits_battery_discharge_rate():
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    battery = Node()
    b1 = ElectricalStorage(
        max_capacity=48,
        depth_of_discharge_limit=0,
        charging_power_limit=5.0,
        discharging_power_limit=-5.0,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=48.0,
    )
    battery.ports["battery_asset"] = b1

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-4] * time_periods, expansion_periods)
    pv1.curtailable = True
    solar.ports["solar"] = pv1

    inverter = Inverter(
        max_import=5,
        max_export=-5,
        dc_ac_efficiency=0.9,
        ac_dc_efficiency=1,
        ac_port_name="cp",
        dc_port_names=["bess", "pv"],
    )

    cp = TellegenNode()
    cp.add_ports_from_list(["load", "inv", "grid"], FlexPort, units=Units.KW)

    load = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([6] * time_periods, expansion_periods)
    load.ports["load"] = l1

    system.add_node_obj([grid, cp, load, battery, solar, inverter])

    system.connect_ports_and_create_edge(inverter.ports["bess"], b1)
    system.connect_ports_and_create_edge(inverter.ports["pv"], pv1)
    system.connect_ports_and_create_edge(cp.ports["load"], l1)
    system.connect_ports_and_create_edge(inverter.ports["cp"], cp.ports["inv"])
    system.connect_ports_and_create_edge(cp.ports["grid"], grid.ports["grid"])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=ObjectiveSet(objective_list=[TotalFlow(component=grid.ports["grid"])]),
    )

    for i in range(time_periods):
        np.testing.assert_almost_equal(optimise_results.values(cp.ports["grid"].port_name, 0)[i], 1.0)


def test_hybrid_inverter_limits_path_flows():
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    battery = Node()
    b1 = ElectricalStorage(
        max_capacity=48,
        depth_of_discharge_limit=0,
        charging_power_limit=5.0,
        discharging_power_limit=-5.0,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=48.0,
    )
    battery.ports["battery_asset"] = b1

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-4] * time_periods, expansion_periods)
    pv1.curtailable = True
    solar.ports["solar"] = pv1

    inverter = Inverter(
        max_import=5,
        max_export=-5,
        dc_ac_efficiency=1,
        ac_dc_efficiency=1,
        ac_port_name="cp",
        dc_port_names=["bess", "pv"],
    )

    cp = TellegenNode()
    cp.add_ports_from_list(["load", "inv", "grid"], FlexPort, units=Units.KW)

    load = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([6] * time_periods, expansion_periods)
    load.ports["load"] = l1

    system.add_node_obj([grid, cp, load, battery, solar, inverter])

    system.connect_ports_and_create_edge(inverter.ports["bess"], b1)
    system.connect_ports_and_create_edge(inverter.ports["pv"], pv1)
    system.connect_ports_and_create_edge(cp.ports["load"], l1)
    system.connect_ports_and_create_edge(inverter.ports["cp"], cp.ports["inv"])
    system.connect_ports_and_create_edge(cp.ports["grid"], grid.ports["grid"])

    system.create_path_objects(sources=[grid, solar, battery], sinks=[grid, battery, load])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=ObjectiveSet(objective_list=[TotalFlow(component=grid.ports["grid"])]),
    )

    bess_to_load = optimise_results.values(system.get_path([battery, inverter, cp, load]).flow_value, 0)
    bess_to_grid = optimise_results.values(system.get_path([battery, inverter, cp, grid]).flow_value, 0)
    solar_to_load = optimise_results.values(system.get_path([solar, inverter, cp, load]).flow_value, 0)
    solar_to_grid = optimise_results.values(system.get_path([solar, inverter, cp, grid]).flow_value, 0)

    # Check all flows through inverter respect inverter limits
    for i in range(time_periods):
        np.testing.assert_almost_equal(
            bess_to_load[i] + bess_to_grid[i] + solar_to_load[i] + solar_to_grid[i],
            inverter.ports["cp"].export_constraint_value * -1,
        )
