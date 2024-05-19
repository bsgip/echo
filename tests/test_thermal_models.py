import numpy as np

from echo.utils import TimeSeriesData, expand_as_dict
from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode, Sink, FixedPort
from echo.models.base import Node, OptimisationGraph, TransformNode

from echo.models.thermal import ThermalStorage, HeatPump
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.objectives.base import ObjectiveSet
from echo.objectives.tariff import ImportTariff, ThroughputCost
from echo.objectives.power import PeakPositivePower
from echo.optimiser import optimise


NUMBER_INTERVALS = 48
INTERVAL_DURATION = 30
NUM_EXPANSION_PERIODS = 1


def default_surface_area_of_cylinder(volume: float, include_bottom: bool = True):
    """Given volume of the cylinder in cubic meters, calculate surface area. Assuming height to diameter ration H/D=3.

    If include_bottom is False, do not include bottom surface.
    """
    radius = np.cbrt(volume / (np.pi * 6))
    height = 6 * radius
    if include_bottom:
        return round(2 * np.pi * radius * height + 2 * np.pi * radius**2, 3)
    else:
        return round(2 * np.pi * radius * height + np.pi * radius**2, 3)


amb_temp_data = TimeSeriesData(
    value=25, num_time_intervals=NUMBER_INTERVALS, num_expansion_intervals=NUM_EXPANSION_PERIODS
)
ambient_temp_dict = expand_as_dict(amb_temp_data)

u_ins = 5  # W/sqm*C (from 0.5 - 11 is reasonable range)
mass = 500
min_temp = 10
max_temp = 80
area = default_surface_area_of_cylinder(mass * 1e-3)
q_max_joules = 4184 * mass * (max_temp - min_temp)  # Max energy storage capacity in joules
q_max_kwh = q_max_joules / 3600000
th_load = [0.1] * 14 + [0.4] * 4 + [0.05] * 16 + [0.4] * 6 + [0.2] * 8
th_load = list((np.array(th_load) * q_max_kwh).round())


def test_thermal_storage():
    th_demand_data = TimeSeriesData(
        value=th_load, num_time_intervals=NUMBER_INTERVALS, num_expansion_intervals=NUM_EXPANSION_PERIODS
    )
    th_demand_dict = expand_as_dict(th_demand_data)

    storage = ThermalStorage(
        max_temp=max_temp,
        min_temp=min_temp,
        ambient_temp=ambient_temp_dict,
        storage_mass=mass,
        specific_heat=4184,
        ins_transmittance=u_ins,
        surface_area=area,
        separate_in_out_ports=False,
    )
    # assert that ports units default to KWT
    assert all([v.units == Units.KWT for v in storage.ports.values()])
    assert storage.initial_temp == storage.min_temp + 0.5 * (storage.max_temp - storage.min_temp)

    thermal_demand = Node(node_name="thermal_load", ports={"demand_kwt": Sink(units=Units.KWT)})

    thermal_demand.ports["demand_kwt"].add_sink_profile(th_demand_dict)

    thermal_mains = Node(node_name="thermal_supply", ports={"supply_kwt": FlexPort(units=Units.KWT)})

    cp = TellegenNode(
        node_name="conn_point",
        ports={
            "to_supply_kwt": FlexPort(units=Units.KWT),
            "to_storage_kwt": FlexPort(units=Units.KWT),
            "to_demand_kwt": FlexPort(units=Units.KWT),
        },
    )
    system = OptimisationGraph()
    system.add_node_obj([storage, thermal_demand, thermal_mains, cp])
    system.connect_ports_and_create_edge(cp.ports["to_supply_kwt"], thermal_mains.ports["supply_kwt"])
    system.connect_ports_and_create_edge(cp.ports["to_storage_kwt"], storage.ports["input_output"])
    system.connect_ports_and_create_edge(cp.ports["to_demand_kwt"], thermal_demand.ports["demand_kwt"])
    objective_set = ObjectiveSet(objective_list=[ThroughputCost(component=storage.ports["input_output"], rate=0.01)])

    optimise_results_no = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=INTERVAL_DURATION,
            number_of_intervals=NUMBER_INTERVALS,
            number_of_expansion_intervals=NUM_EXPANSION_PERIODS,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=objective_set,
    )

    storage_temp = getattr(optimise_results_no.model, storage.internal_temp).get_values()
    loss_gain = getattr(optimise_results_no.model, storage.net_loss_gain).get_values()
    soc_100 = optimise_results_no.df()[storage.soc_value][0] * 1 / q_max_kwh

    cp_flow_df_no = (
        optimise_results_no.df_by_port()[[k for k in cp.ports.keys()]].reset_index(level=[0]).drop(columns="level_0")
    )

    # Check that SOC values (in energy units) make sense
    assert all([0 <= v <= 1 for v in soc_100.values])

    # Check that heat loss/gain to environment is calculated correctly
    assert all(
        [
            round(loss_gain[k]) >= round((storage.ambient_temp[k] - storage_temp[k]) * storage.lump_conductance)
            for k in loss_gain.keys()
        ]
    )

    # # Not expecting storage to do anything when no objective set, throughput cost shall prevent from random actions
    assert round(cp_flow_df_no["to_storage_kwt"].min()) == round(cp_flow_df_no["to_storage_kwt"].max()) == 0

    objective_set = ObjectiveSet(
        objective_list=[
            ThroughputCost(component=storage.ports["input_output"], rate=0.01),
            PeakPositivePower(component=cp.ports["to_supply_kwt"]),
        ]
    )
    optimise_results_pp = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=INTERVAL_DURATION,
            number_of_intervals=NUMBER_INTERVALS,
            number_of_expansion_intervals=NUM_EXPANSION_PERIODS,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=objective_set,
    )

    cp_flow_df_pp = (
        optimise_results_pp.df_by_port()[[k for k in cp.ports.keys()]].reset_index(level=[0]).drop(columns="level_0")
    )

    # Expecting peak power to be less with peak power objective
    assert cp_flow_df_no["to_supply_kwt"].max() >= cp_flow_df_pp["to_supply_kwt"].max()


def test_thermal_storage_2_ports():
    th_demand_data = TimeSeriesData(
        value=th_load, num_time_intervals=NUMBER_INTERVALS, num_expansion_intervals=NUM_EXPANSION_PERIODS
    )
    th_demand_dict = expand_as_dict(th_demand_data)
    thermal_demand = Node(node_name="thermal_load", ports={"demand_kwt": Sink(units=Units.KWT)})

    thermal_demand.ports["demand_kwt"].add_sink_profile(th_demand_dict)

    thermal_mains = Node(node_name="thermal_supply", ports={"supply_kwt": FlexPort(units=Units.KWT)})

    storage_2p = ThermalStorage(
        max_temp=80,
        min_temp=10,
        ambient_temp=ambient_temp_dict,
        storage_mass=mass,
        specific_heat=4184,
        ins_transmittance=u_ins,
        surface_area=area,
        separate_in_out_ports=True,
    )

    # assert number of ports
    assert len(list(storage_2p.ports.values())) == 2

    # When Storage has two ports, we need two connection points as only one edge is allowed between any two nodes
    cp_1 = TellegenNode(
        node_name="conn_point_supply",
        ports={
            "to_supply_kwt": FlexPort(units=Units.KWT),
            "to_demand_cp_kwt": FlexPort(units=Units.KWT),
            f"to_storage_input_kwt": FlexPort(units=Units.KWT),
        },
    )
    cp_2 = TellegenNode(
        node_name="conn_point_demand",
        ports={
            "to_supply_cp_kwt": FlexPort(units=Units.KWT),
            "to_demand_kwt": FlexPort(units=Units.KWT),
            "to_storage_output_kwt": FlexPort(units=Units.KWT),
        },
    )

    system = OptimisationGraph()
    system.add_node_obj([storage_2p, thermal_demand, thermal_mains, cp_1, cp_2])
    system.connect_ports_and_create_edge(cp_1.ports["to_supply_kwt"], thermal_mains.ports["supply_kwt"])
    system.connect_ports_and_create_edge(cp_1.ports["to_storage_input_kwt"], storage_2p.ports["input"])
    system.connect_ports_and_create_edge(cp_1.ports["to_demand_cp_kwt"], cp_2.ports["to_supply_cp_kwt"])
    system.connect_ports_and_create_edge(cp_2.ports["to_storage_output_kwt"], storage_2p.ports["output"])
    system.connect_ports_and_create_edge(cp_2.ports["to_demand_kwt"], thermal_demand.ports["demand_kwt"])

    objective_set = ObjectiveSet(
        objective_list=[
            ThroughputCost(component=storage_2p.ports[_port_name], rate=0.01) for _port_name in storage_2p.ports
        ]
    )
    optimise_results_no = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=INTERVAL_DURATION,
            number_of_intervals=NUMBER_INTERVALS,
            number_of_expansion_intervals=NUM_EXPANSION_PERIODS,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=objective_set,
    )

    storage_temp = getattr(optimise_results_no.model, storage_2p.internal_temp).get_values()
    loss_gain = getattr(optimise_results_no.model, storage_2p.net_loss_gain).get_values()
    soc_100 = optimise_results_no.df()[storage_2p.soc_value][0] * 1 / q_max_kwh

    cp_flow_df_no = (
        optimise_results_no.df_by_port()[[k for k in cp_1.ports.keys()]].reset_index(level=[0]).drop(columns="level_0")
    )
    cp_flow_df_2 = (
        optimise_results_no.df_by_port()[[k for k in cp_2.ports.keys()]].reset_index(level=[0]).drop(columns="level_0")
    )
    cp_flow_df_no = cp_flow_df_no.join(cp_flow_df_2)

    # Check that SOC values (in energy units) make sense
    assert all([0 <= v <= 1 for v in soc_100.values])

    # Check that heat loss/gain to environment is calculated correctly
    assert all(
        [
            round(loss_gain[k]) >= round((storage_2p.ambient_temp[k] - storage_temp[k]) * storage_2p.lump_conductance)
            for k in loss_gain.keys()
        ]
    )

    # # Not expecting storage to do anything when no objective set, throughput cost shall prevent from random actions
    for storage_port in storage_2p.ports:
        assert (
            round(cp_flow_df_no[f"to_storage_{storage_port}_kwt"].min())
            == round(cp_flow_df_no[f"to_storage_{storage_port}_kwt"].max())
            == 0
        )

    obj_list = [ThroughputCost(component=storage_2p.ports[_port_name], rate=0.01) for _port_name in storage_2p.ports]
    obj_list.append(PeakPositivePower(component=cp_1.ports["to_supply_kwt"]))
    objective_set = ObjectiveSet(objective_list=obj_list)

    optimise_results_pp = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=INTERVAL_DURATION,
            number_of_intervals=NUMBER_INTERVALS,
            number_of_expansion_intervals=NUM_EXPANSION_PERIODS,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=objective_set,
    )

    cp_flow_df_pp = (
        optimise_results_no.df_by_port()[[k for k in cp_1.ports.keys()]].reset_index(level=[0]).drop(columns="level_0")
    )
    cp_flow_df_2 = (
        optimise_results_no.df_by_port()[[k for k in cp_2.ports.keys()]].reset_index(level=[0]).drop(columns="level_0")
    )
    cp_flow_df_pp = cp_flow_df_pp.join(cp_flow_df_2)

    # Expecting peak power to be less with peak power objective
    assert cp_flow_df_no["to_supply_kwt"].max() >= cp_flow_df_pp["to_supply_kwt"].max()
