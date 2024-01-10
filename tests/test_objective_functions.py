from __future__ import division

from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import ElectricalDemand, ElectricalGeneration, ElectricalStorage, Inverter
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.objectives.base import ObjectiveSet
from echo.objectives.tariff import DemandTariffObjective, ExportTariff, ImportDemandCharge, ImportTariff, ThroughputCost
from echo.optimiser import optimise


def test_objectives_sum_correctly():
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

    inverter = Inverter(max_import=5, max_export=-5, dc_ac_efficiency=0.9, ac_dc_efficiency=1)
    inverter.add_ac_port("cp")
    inverter.add_dc_port("bess")
    inverter.add_dc_port("pv")

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

    # Define a set of objectives
    tp_cost = ThroughputCost(component=b1, rate=0.1)

    import_t = ImportTariff(component=cp.ports["grid"], tariff_array=[0.1] * 24 + [0.4] * 24)

    export_t = ExportTariff(component=cp.ports["grid"], tariff_array=[0.0] * 24 + [0.1] * 24)
    # peak usage
    peak_charge = ImportDemandCharge(
        rate=2.0,
        window_array=[0] * 14 + [1] * 4 + [0] * 16 + [1] * 6 + [0] * 8,
        min_demand=0.0,
        reset_periods=[time_periods],
    )

    # shoulder usage
    shoulder_charge = ImportDemandCharge(
        rate=1.6,
        window_array=[0] * 18 + [1] * 16 + [0] * 6 + [1] * 4 + [0] * 4,
        min_demand=0.0,
        reset_periods=[time_periods],
    )

    demand_tariff = DemandTariffObjective(component=cp.ports["grid"], demand_charges=[peak_charge, shoulder_charge])

    obj_set = ObjectiveSet(objective_list=[tp_cost, import_t, export_t, demand_tariff])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=obj_set,
    )

    # get back each tariff component
    sc = optimise_results.get_single_objective_total_value(shoulder_charge)
    tp = optimise_results.get_single_objective_total_value(tp_cost)
    it = optimise_results.get_single_objective_total_value(import_t)
    et = optimise_results.get_single_objective_total_value(export_t)
    dt = optimise_results.get_single_objective_total_value(demand_tariff)
    total = optimise_results.get_total_objective_value()

    assert tp + it + et + dt == total
