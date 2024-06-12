"""Integration testing for thermal models with optimisation scenarios"""

import numpy as np
import pandas as pd

from echo.utils import TimeSeriesData, expand_as_dict
from echo.configuration import FlowConstraint, Flows, OptimisationType, Units
from echo.models.agnostic import FlexPort, TellegenNode, Sink, Source, AggregationNode
from echo.models.base import Node, OptimisationGraph, Port

from echo.models.thermal import (
    ThermalStorage,
    ParametrisedChiller,
    SimpleChiller,
    SimpleHeatPump,
    SimpleHeatPumpDualOutput,
)
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.objectives.base import ObjectiveSet
from echo.objectives.tariff import ThroughputCost
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
profile_df = pd.DataFrame({"thermal_load": th_load, "ambient_temp": [25] * NUMBER_INTERVALS})

# Pre-defined arrays of heating and cooling coefficients of performance for simple chiller and HP models
NUMBER_INTERVALS_SHORT = 6
# Cooling demand is a heat source
cooling_load_data = TimeSeriesData(
    value=[0, 0, -2.5, -5, -7.5, -10], num_time_intervals=NUMBER_INTERVALS_SHORT, num_expansion_intervals=1
)
cooling_demand_dict = expand_as_dict(cooling_load_data)

cooling_demand_dict_non_zero = expand_as_dict(
    TimeSeriesData(
        value=[-1, -1, -2.5, -5, -7.5, -10], num_time_intervals=NUMBER_INTERVALS_SHORT, num_expansion_intervals=1
    )
)

heating_load_data = TimeSeriesData(
    value=[5, 5, 3, 3, 0, 0], num_time_intervals=NUMBER_INTERVALS_SHORT, num_expansion_intervals=1
)
heating_load_dict = expand_as_dict(heating_load_data)

combined_thermal_load_data = TimeSeriesData(
    value=[5, 3, -5, -3, 0, 10], num_time_intervals=NUMBER_INTERVALS_SHORT, num_expansion_intervals=1
)
combined_thermal_load_dict = expand_as_dict(combined_thermal_load_data)


cooling_cop_data = TimeSeriesData(
    value=[4, 4, 2.5, 2, 1.5, 2.5],
    num_time_intervals=NUMBER_INTERVALS_SHORT,
    num_expansion_intervals=NUM_EXPANSION_PERIODS,
)
cooling_cop_dict = expand_as_dict(cooling_cop_data)

heating_cop_data = TimeSeriesData(
    value=[1.5, 1.5, 3.5, 3, 3.5, 2.5],
    num_time_intervals=NUMBER_INTERVALS_SHORT,
    num_expansion_intervals=NUM_EXPANSION_PERIODS,
)
heating_cop_dict = expand_as_dict(heating_cop_data)


profile_short = pd.DataFrame(
    {
        "cooling_load": cooling_load_data.value,
        "heating_load": heating_load_data.value,
        "cooling_cop": cooling_cop_data.value,
        "heating_cop": heating_cop_data.value,
    }
)


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

    # Not expecting storage to do anything when no objective set, throughput cost shall prevent from random actions
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


def test_thermal_storage_with_profile():
    storage = ThermalStorage(
        max_temp=max_temp,
        min_temp=min_temp,
        ambient_temp_ref="ambient_temp",
        storage_mass=mass,
        specific_heat=4184,
        ins_transmittance=u_ins,
        surface_area=area,
        separate_in_out_ports=False,
    )

    thermal_demand = Node(
        node_name="thermal_load", ports={"demand_kwt": Sink(units=Units.KWT, initial_value_ref="thermal_load")}
    )

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
        profile=profile_df,
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

    # Not expecting storage to do anything when no objective set, throughput cost shall prevent from random actions
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
        profile=profile_df,
    )

    cp_flow_df_pp = (
        optimise_results_pp.df_by_port()[[k for k in cp.ports.keys()]].reset_index(level=[0]).drop(columns="level_0")
    )

    # Expecting peak power to be less with peak power objective
    assert cp_flow_df_no["to_supply_kwt"].max() >= cp_flow_df_pp["to_supply_kwt"].max()


def test_thermal_storage_no_ambient_temp():
    storage = ThermalStorage(
        max_temp=max_temp,
        min_temp=min_temp,
        storage_mass=mass,
        specific_heat=4184,
        ins_transmittance=u_ins,
        surface_area=area,
        separate_in_out_ports=False,
    )

    thermal_demand = Node(
        node_name="thermal_load", ports={"demand_kwt": Sink(units=Units.KWT, initial_value_ref="thermal_load")}
    )
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
        profile=profile_df,
    )

    storage_temp = getattr(optimise_results_no.model, storage.internal_temp).get_values()
    loss_gain = getattr(optimise_results_no.model, storage.net_loss_gain).get_values()
    soc_100 = optimise_results_no.df()[storage.soc_value][0] * 1 / q_max_kwh

    cp_flow_df_no = (
        optimise_results_no.df_by_port()[[k for k in cp.ports.keys()]].reset_index(level=[0]).drop(columns="level_0")
    )

    # Check that SOC values (in energy units) make sense
    assert all([0 <= v <= 1 for v in soc_100.values])

    # Check that heat loss/gain equals to zero when no ambient temperature reference is supplied
    assert all([round(loss_gain[k]) == 0 for k in loss_gain.keys()])

    # Expecting no change in storage temperature with zero flows and zero gain/loss
    assert all([round(storage_temp[k]) == storage.initial_temp for k in storage_temp.keys()])

    # Not expecting storage to do anything when no objective set, throughput cost shall prevent from random actions
    assert round(cp_flow_df_no["to_storage_kwt"].min()) == round(cp_flow_df_no["to_storage_kwt"].max()) == 0


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

    # Not expecting storage to do anything when no objective set, throughput cost shall prevent from random actions
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
        optimise_results_pp.df_by_port()[[k for k in cp_1.ports.keys()]].reset_index(level=[0]).drop(columns="level_0")
    )
    cp_flow_df_2 = (
        optimise_results_pp.df_by_port()[[k for k in cp_2.ports.keys()]].reset_index(level=[0]).drop(columns="level_0")
    )
    cp_flow_df_pp = cp_flow_df_pp.join(cp_flow_df_2)

    # Expecting peak power to be less with peak power objective
    assert cp_flow_df_no["to_supply_kwt"].max() >= cp_flow_df_pp["to_supply_kwt"].max()


def test_chiller_operation():
    """Test Chiller operation with piecewise linear COP dependent on partial load value"""

    system = OptimisationGraph()
    grid = Node(node_name="grid", ports={"supply_kw": FlexPort(units=Units.KW)})
    chiller = ParametrisedChiller(max_cooling_capacity=10, nominal_cop=2.5)
    cooling_load = Node(node_name="cooling_load", ports={"cooling_demand_kwt": Source(units=Units.KWT)})
    cooling_load.ports["cooling_demand_kwt"].add_source_profile(cooling_demand_dict)
    system.add_node_obj([grid, chiller, cooling_load])
    system.connect_ports_and_create_edge(grid.ports["supply_kw"], chiller.ports["input"])
    system.connect_ports_and_create_edge(chiller.ports["output"], cooling_load.ports["cooling_demand_kwt"])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=INTERVAL_DURATION,
            number_of_intervals=NUMBER_INTERVALS_SHORT,
            number_of_expansion_intervals=1,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
    )

    chiller_actual_cop = list()
    for _output, _input in zip(
        optimise_results.values(chiller.ports["output"].port_name, 0),
        optimise_results.values(chiller.ports["input"].port_name, 0),
    ):
        if _input == 0:
            assert _output == 0
        else:
            assert _output != 0
            chiller_actual_cop.append(round(_output / _input, 3))

    # Check that we observe variation in COP
    assert min(chiller_actual_cop) != max(chiller_actual_cop)

    # Check that observed COP values are within expected range
    min_cop = min([v for v in chiller.partial_load_cop.values() if v != 0]) * chiller.nominal_cop
    for cop_v in chiller_actual_cop:
        assert cop_v >= min_cop
        assert cop_v <= chiller.nominal_cop


def test_chiller_with_heat_rejection():
    """Test Chiller operation with heat rejection port"""

    system = OptimisationGraph()
    grid = Node(node_name="grid", ports={"supply_kw": FlexPort(units=Units.KW)})
    chiller = ParametrisedChiller(
        max_cooling_capacity=10, nominal_cop=2.5, heat_rejection_port=True, heat_rejection_coefficient=0.8
    )
    assert "heat_rejection" in chiller.ports
    cooling_load = Node(node_name="cooling_load", ports={"cooling_demand_kwt": Source(units=Units.KWT)})
    cooling_load.ports["cooling_demand_kwt"].add_source_profile(cooling_demand_dict)
    waste_heat_agg = AggregationNode(port_units=Units.KWT)
    waste_heat_agg.add_port("chiller_waste_heat")

    system.add_node_obj([grid, chiller, cooling_load, waste_heat_agg])
    system.connect_ports_and_create_edge(grid.ports["supply_kw"], chiller.ports["input"])
    system.connect_ports_and_create_edge(chiller.ports["output"], cooling_load.ports["cooling_demand_kwt"])
    system.connect_ports_and_create_edge(chiller.ports["heat_rejection"], waste_heat_agg.ports["chiller_waste_heat"])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=INTERVAL_DURATION,
            number_of_intervals=NUMBER_INTERVALS_SHORT,
            number_of_expansion_intervals=1,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
    )

    chiller_actual_cop = list()
    for _output, _input in zip(
        optimise_results.values(chiller.ports["output"].port_name, 0),
        optimise_results.values(chiller.ports["input"].port_name, 0),
    ):
        if _input == 0:
            assert _output == 0
        else:
            assert _output != 0
            chiller_actual_cop.append(round(_output / _input, 3))

    # Check that we observe variation in COP
    assert min(chiller_actual_cop) != max(chiller_actual_cop)

    total_waste_heat = round(optimise_results.values(waste_heat_agg.total, 0).sum(), 2)
    total_cooling_load = round(optimise_results.df_by_port()["cooling_demand_kwt"].sum(), 2)
    assert total_waste_heat == -chiller.heat_rejection_coefficient * total_cooling_load

    # Check that observed COP values are within expected range
    min_cop = min([v for v in chiller.partial_load_cop.values() if v != 0]) * chiller.nominal_cop
    for cop_v in chiller_actual_cop:
        assert cop_v >= min_cop
        assert cop_v <= chiller.nominal_cop


def test_chiller_with_temperature_cop():
    """Test Chiller operation with piecewise linear COP dependent on partial load value and ambient temperature"""

    ambient_temperature_data = TimeSeriesData(
        value=[10, 0, 7, 20, 5, 15], num_time_intervals=6, num_expansion_intervals=1
    )
    ambient_temperature_dict = expand_as_dict(ambient_temperature_data)
    system = OptimisationGraph()
    grid = Node(node_name="grid", ports={"supply_kw": FlexPort(units=Units.KW)})
    chiller = ParametrisedChiller(
        max_cooling_capacity=10,
        nominal_cop=2.5,
        partial_load_cop={0: 1, 0.25: 1, 0.5: 1, 0.75: 1, 1: 1},
        ambient_temperature_dict=ambient_temperature_dict,
    )
    cooling_load = Node(node_name="cooling_load", ports={"cooling_demand_kwt": Source(units=Units.KWT)})
    # Need non zero
    cooling_load.ports["cooling_demand_kwt"].add_source_profile(cooling_demand_dict_non_zero)

    system.add_node_obj([grid, chiller, cooling_load])
    system.connect_ports_and_create_edge(grid.ports["supply_kw"], chiller.ports["input"])
    system.connect_ports_and_create_edge(chiller.ports["output"], cooling_load.ports["cooling_demand_kwt"])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=INTERVAL_DURATION,
            number_of_intervals=NUMBER_INTERVALS_SHORT,
            number_of_expansion_intervals=1,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
    )

    chiller_actual_cop = list()
    for _output, _input in zip(
        optimise_results.values(chiller.ports["output"].port_name, 0),
        optimise_results.values(chiller.ports["input"].port_name, 0),
    ):
        if _input == 0:
            assert _output == 0
        else:
            assert _output != 0
            chiller_actual_cop.append(round(_output / _input, 3))

    temperature_cop_factor = optimise_results.values(chiller.temperature_cop_param).tolist()

    # Check that we observe variation in COP
    assert min(chiller_actual_cop) != max(chiller_actual_cop)

    # Check that observed COP values are within expected range
    min_cop = min([v for v in temperature_cop_factor]) * chiller.nominal_cop
    for cop_v in chiller_actual_cop:
        i = chiller_actual_cop.index(cop_v)
        assert cop_v >= min_cop
        assert cop_v <= chiller.nominal_cop
        assert round(cop_v, 3) == round(temperature_cop_factor[i] * chiller.nominal_cop, 3)


def test_simple_chiller():
    """Test simple chiller operation with predefined coefficient of performance array"""
    system = OptimisationGraph()
    grid = Node(node_name="grid", ports={"supply_kw": FlexPort(units=Units.KW)})
    chiller = SimpleChiller(max_cooling_capacity=10, cooling_cop_time_series_ref="cooling_cop")
    # Cooling demand is a heat source
    cooling_load = Node(node_name="cooling_load", ports={"cooling_demand_kwt": Source(units=Units.KWT)})
    cooling_load.ports["cooling_demand_kwt"].add_source_profile(cooling_demand_dict)

    system.add_node_obj([grid, chiller, cooling_load])
    system.connect_ports_and_create_edge(grid.ports["supply_kw"], chiller.ports["input"])
    system.connect_ports_and_create_edge(chiller.ports["output"], cooling_load.ports["cooling_demand_kwt"])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=30,
            number_of_intervals=6,
            number_of_expansion_intervals=1,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        profile=profile_short,
    )

    # Coefficient of performance provided at initialisation
    cooling_cop_array = optimise_results.values(chiller.cooling_cop)
    # Actual observed Coefficient of performance (output/input)
    assert max(optimise_results.values(chiller.ports["output"].port_name)) <= chiller.max_cooling_capacity
    chiller_actual_cop = list()
    for _output, _input in zip(
        optimise_results.values(chiller.ports["output"].port_name),
        optimise_results.values(chiller.ports["input"].port_name),
    ):
        if _input == 0:
            assert _output == 0
            chiller_actual_cop.append(0)
        else:
            assert _output != 0
            chiller_actual_cop.append(round(_output / _input, 3))
    # Assert that when output is non-zero, the actual COP equals provided COP
    for _set_cop, _actual_cop in zip(cooling_cop_array, chiller_actual_cop):
        if not _actual_cop == 0:
            assert _set_cop == _actual_cop


def test_simple_heatpump_single_output():
    """Test simple heat pump operation with predefined coefficient of performance array"""
    system = OptimisationGraph()
    grid = Node(node_name="grid", ports={"supply_kw": FlexPort(units=Units.KW)})
    heatpump = SimpleHeatPump(
        max_cooling_capacity=10,
        max_heating_capacity=10,
        cooling_cop_time_series_ref="cooling_cop",
        heating_cop_time_series_ref="heating_cop",
    )
    # Cooling demand is a heat source
    thermal_load = Node(
        node_name="thermal_load",
        ports={
            "thermal_demand_kwt": Port(
                units=Units.KWT,
                flows=Flows.Both,
                import_constraint=FlowConstraint.NoConstraint,
                export_constraint=FlowConstraint.NoConstraint,
                flow_type=OptimisationType.Parameter,
            )
        },
    )
    thermal_load.ports["thermal_demand_kwt"].set_initial_value(combined_thermal_load_dict)

    system.add_node_obj([grid, heatpump, thermal_load])
    system.connect_ports_and_create_edge(grid.ports["supply_kw"], heatpump.ports["electrical_input"])
    system.connect_ports_and_create_edge(heatpump.ports["thermal_output"], thermal_load.ports["thermal_demand_kwt"])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=30,
            number_of_intervals=6,
            number_of_expansion_intervals=1,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        profile=profile_short,
    )

    # Coefficient of performance provided at initialisation
    cooling_cop_array = optimise_results.values(heatpump.cooling_cop)
    heating_cop_array = optimise_results.values(heatpump.heating_cop)

    # Actual observed Coefficient of performance (output/input)
    heating_cop_actual = list()
    for _output, _input in zip(
        optimise_results.values(heatpump.ports["thermal_output"].neg),
        optimise_results.values(heatpump.ports["electrical_input"].port_name),
    ):
        if _input == 0:
            assert _output == 0
            heating_cop_actual.append(0)
        else:
            heating_cop_actual.append(-1 * round(_output / _input, 3))

    # Assert that when output is non-zero, the actual COP equals provided COP
    for _set_cop, _actual_cop in zip(heating_cop_array, heating_cop_actual):
        if not _actual_cop == 0:
            assert _set_cop == _actual_cop

    cooling_cop_actual = list()
    for _output, _input in zip(
        optimise_results.values(heatpump.ports["thermal_output"].pos),
        optimise_results.values(heatpump.ports["electrical_input"].port_name),
    ):
        if _input == 0:
            assert _output == 0
            cooling_cop_actual.append(0)
        else:
            cooling_cop_actual.append(round(_output / _input, 3))

    # Assert that when output is non-zero, the actual COP equals provided COP
    for _set_cop, _actual_cop in zip(cooling_cop_array, cooling_cop_actual):
        if not _actual_cop == 0:
            assert _set_cop == _actual_cop
    # Assert that all electrical power consumed is equal to the power used for heating + power used for cooling
    power_to_heat_and_cool = optimise_results.values(heatpump.power_to_cool) + optimise_results.values(
        heatpump.power_to_heat
    )
    total_power_consumed = optimise_results.values(heatpump.ports["electrical_input"].port_name)

    assert all(power_to_heat_and_cool == total_power_consumed)


def test_simple_heatpump_dual_output():
    """Test simple dual output heat pump operation with predefined coefficient of performance array"""
    system = OptimisationGraph()
    grid = Node(node_name="grid", ports={"supply_kw": FlexPort(units=Units.KW)})
    heatpump = SimpleHeatPumpDualOutput(
        max_cooling_capacity=10,
        max_heating_capacity=10,
        cooling_cop_time_series_ref="cooling_cop",
        heating_cop_time_series_ref="heating_cop",
    )
    # Cooling demand is a heat source
    cooling_load = Node(node_name="cooling_load", ports={"cooling_demand_kwt": Source(units=Units.KWT)})
    cooling_load.ports["cooling_demand_kwt"].add_source_profile(cooling_demand_dict)
    # Heating demand is a heat sink
    heating_load = Node(node_name="heating_load", ports={"heating_demand_kwt": Sink(units=Units.KWT)})
    heating_load.ports["heating_demand_kwt"].add_sink_profile(heating_load_dict)

    system.add_node_obj([grid, heatpump, cooling_load, heating_load])
    system.connect_ports_and_create_edge(grid.ports["supply_kw"], heatpump.ports["electrical_input"])
    system.connect_ports_and_create_edge(heatpump.ports["cooling_output"], cooling_load.ports["cooling_demand_kwt"])
    system.connect_ports_and_create_edge(heatpump.ports["heating_output"], heating_load.ports["heating_demand_kwt"])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=30,
            number_of_intervals=6,
            number_of_expansion_intervals=1,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        profile=profile_short,
    )

    # Coefficient of performance provided at initialisation
    cooling_cop_array = optimise_results.values(heatpump.cooling_cop)
    heating_cop_array = optimise_results.values(heatpump.heating_cop)

    # Actual observed Coefficient of performance (output/input)
    heating_cop_actual = list()
    for _output, _input in zip(
        optimise_results.values(heatpump.heating_out_adjusted),
        optimise_results.values(heatpump.power_to_heat),
    ):
        if _input == 0:
            assert _output == 0
            heating_cop_actual.append(0)
        else:
            heating_cop_actual.append(-1 * round(_output / _input, 3))

    # Assert that when output is non-zero, the actual COP equals provided COP
    for _set_cop, _actual_cop in zip(heating_cop_array, heating_cop_actual):
        if not _actual_cop == 0:
            assert _set_cop == _actual_cop

    cooling_cop_actual = list()
    for _output, _input in zip(
        optimise_results.values(heatpump.ports["cooling_output"].port_name),
        optimise_results.values(heatpump.power_to_cool),
    ):
        if _input == 0:
            assert _output == 0
            cooling_cop_actual.append(0)
        else:
            cooling_cop_actual.append(round(_output / _input, 3))

    # Assert that when output is non-zero, the actual COP equals provided COP
    for _set_cop, _actual_cop in zip(cooling_cop_array, cooling_cop_actual):
        if not _actual_cop == 0:
            assert _set_cop == _actual_cop
    # Assert that all electrical power consumed is equal to the power used for heating + power used for cooling
    power_to_heat_and_cool = optimise_results.values(heatpump.power_to_cool) + optimise_results.values(
        heatpump.power_to_heat
    )
    total_power_consumed = optimise_results.values(heatpump.ports["electrical_input"].port_name)

    assert all(power_to_heat_and_cool == total_power_consumed)

    total_heat_delivered = optimise_results.values(heatpump.ports["heating_output"].port_name).sum()
    total_adjusted_heat_from_source = optimise_results.values(heatpump.heating_out_adjusted).sum()
    total_waste_heat_recovered = optimise_results.values(heatpump.recovered_waste_heat).sum()
    assert round(total_heat_delivered - total_adjusted_heat_from_source, 2) == -1 * round(total_waste_heat_recovered, 2)
