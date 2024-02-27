import numpy as np
import pytest

from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import ElectricalDemand, ElectricalGeneration, ElectricalStorage, Inverter
from echo.models.scenario import ScenarioSettings
from echo.optimiser import optimise


def test_partitioning_regions_for_path_flow(engine_settings):
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
    pv1.curtailable = False
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

    system.create_path_objects(sources=[grid, inverter], sinks=[grid, inverter, load])
    # example_path = system.get_path([grid, cp, load])
    # system.paths = {}
    # system.paths[(grid.node_name, cp.node_name, load.node_name)] = example_path

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings,
        graph=system,
    )

    grid_to_inverter = system.get_path([grid, cp, inverter])
    grid_to_load = system.get_path([grid, cp, load])
    inverter_to_grid = system.get_path([inverter, cp, grid])
    inverter_to_load = system.get_path([inverter, cp, load])

    for i in range(time_periods):
        np.testing.assert_almost_equal(
            optimise_results.values(grid_to_load.flow_value, 0)[i]
            + optimise_results.values(grid_to_inverter.flow_value, 0)[i],
            optimise_results.values(grid.ports["grid"].port_name, 0)[i] * -1,
        )

        np.testing.assert_almost_equal(
            optimise_results.values(inverter_to_grid.flow_value, 0)[i]
            + optimise_results.values(inverter_to_load.flow_value, 0)[i],
            optimise_results.values(inverter.ports["cp"].port_name, 0)[i] * -1,
        )


@pytest.mark.nonlinear
def test_regularisation_of_path_flows(engine_settings):

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min

    system = OptimisationGraph()

    source1 = Node()
    s1 = ElectricalGeneration()
    s1.add_generation_profile_from_array([-1] * time_periods, expansion_periods)
    source1.ports["s1"] = s1

    source2 = Node()
    s2 = ElectricalGeneration()
    s2.add_generation_profile_from_array([-3] * time_periods, expansion_periods)
    source2.ports["s2"] = s2

    cp = TellegenNode()
    cp.add_ports_from_list(["s1", "s2", "l1", "l2"], FlexPort, units=Units.KW)

    load1 = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([2] * time_periods, expansion_periods)
    load1.ports["l1"] = l1

    load2 = Node()
    l2 = ElectricalDemand()
    l2.add_demand_profile_from_array([2] * time_periods, expansion_periods)
    load2.ports["l2"] = l2

    system.add_node_obj([source1, source2, load1, load2, cp])
    system.connect_ports_and_create_edge(s1, cp.ports["s1"])
    system.connect_ports_and_create_edge(s2, cp.ports["s2"])
    system.connect_ports_and_create_edge(l1, cp.ports["l1"])
    system.connect_ports_and_create_edge(l2, cp.ports["l2"])

    system.create_path_objects(sources=[source1, source2], sinks=[load1, load2], regularise=True)

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings,
        graph=system,
    )

    print(optimise_results.opt_status)

    s1_to_l1 = optimise_results.values(system.get_path([source1, cp, load1]).flow_value, 0) * -1
    s1_to_l2 = optimise_results.values(system.get_path([source1, cp, load2]).flow_value, 0) * -1
    s2_to_l1 = optimise_results.values(system.get_path([source2, cp, load1]).flow_value, 0) * -1
    s2_to_l2 = optimise_results.values(system.get_path([source2, cp, load2]).flow_value, 0) * -1

    for i in range(time_periods):
        np.testing.assert_almost_equal(s1_to_l1[i], optimise_results.values(s1.port_name, 0)[i] / 2)
        np.testing.assert_almost_equal(s1_to_l2[i], optimise_results.values(s1.port_name, 0)[i] / 2)
        np.testing.assert_almost_equal(s2_to_l1[i], optimise_results.values(s2.port_name, 0)[i] / 2)
        np.testing.assert_almost_equal(s2_to_l2[i], optimise_results.values(s2.port_name, 0)[i] / 2)
