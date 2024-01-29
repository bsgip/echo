import numpy as np

from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import ElectricalDemand, ElectricalGeneration, ElectricalStorage, Inverter
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.objectives.base import ObjectiveSet, TotalExportFlow, TotalImportFlow
from echo.optimiser import optimise

N_INTERVALS = 48


def test_hybrid_inverter_dc_ac_efficiency():
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

    # Minimise import
    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=ObjectiveSet(objective_list=[TotalImportFlow(component=cp.ports["grid"])]),
    )

    root_p = optimise_results.values(grid.ports["grid"].port_name, 0)
    inv_p = optimise_results.values(inverter.ports["cp"].port_name, 0)
    cp_p = optimise_results.values(cp.ports["grid"].port_name, 0)
    sol_p = optimise_results.values(pv1.port_name, 0)
    sto_p = optimise_results.values(b1.port_name, 0)
    sto_soc = optimise_results.values(b1.soc_value, 0)
    # With the chosen objective, it doesn't matter if the energy is sourced from solar or battery,
    # but each interval should be importing at 1.0
    # TODO Test for preferencing solar gen vs storage
    for i in range(N_INTERVALS):
        np.testing.assert_almost_equal(cp_p[i], 1.0)
        # Check that the efficiency matches the DC input
        np.testing.assert_almost_equal(sol_p[i] + sto_p[i], inv_p[i] / 0.9, 6)


def test_hybrid_inverter_dc_dc_efficiency():
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
        initial_state_of_charge=0.0,
    )
    battery.ports["battery_asset"] = b1

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array(
        [-2.0 / 0.9] * (N_INTERVALS // 2) + [0.0] * (N_INTERVALS // 2), expansion_periods
    )
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
    l1.add_demand_profile_from_array([0.0] * (N_INTERVALS // 2) + [2.0] * (N_INTERVALS // 2), expansion_periods)
    load.ports["load"] = l1

    system.add_node_obj([grid, cp, load, battery, solar, inverter])

    system.connect_ports_and_create_edge(inverter.ports["bess"], b1)
    system.connect_ports_and_create_edge(inverter.ports["pv"], pv1)
    system.connect_ports_and_create_edge(cp.ports["load"], l1)
    system.connect_ports_and_create_edge(inverter.ports["cp"], cp.ports["inv"])
    system.connect_ports_and_create_edge(cp.ports["grid"], grid.ports["grid"])

    # Minimise import
    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=ObjectiveSet(objective_list=[TotalImportFlow(component=cp.ports["grid"])]),
    )

    root_p = optimise_results.values(grid.ports["grid"].port_name, 0)
    cp_p = optimise_results.values(cp.ports["grid"].pos, 0)
    sol_p = optimise_results.values(pv1.port_name, 0)
    sto_p = optimise_results.values(b1.port_name, 0)
    load_p = optimise_results.values(load.ports["load"].port_name, 0)

    for i in range(N_INTERVALS // 2):
        np.testing.assert_almost_equal(cp_p[i], 0.0, 5)  # Had to add 5dp
        np.testing.assert_almost_equal(sol_p[i], -sto_p[i], 5)
        np.testing.assert_almost_equal(sol_p[i], -2.0 / 0.9, 5)
    for i in range(N_INTERVALS // 2, N_INTERVALS):
        np.testing.assert_almost_equal(cp_p[i], 0.0, 5)
        assert sto_p[i]
