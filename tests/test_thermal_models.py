import numpy as np

from echo.utils import TimeSeriesData, expand_as_dict
from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode, Sink, FixedPort
from echo.models.base import Node, OptimisationGraph, TransformNode

from echo.models.thermal import ThermalStorage, HeatPump
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.objectives.base import ObjectiveSet
from echo.objectives.tariff import ImportTariff
from echo.objectives.power import PeakPositivePower
from echo.optimiser import optimise



NUMBER_INTERVALS = 48
INTERVAL_DURATION = 30
NUM_EXPANSION_PERIODS = 1

amb_temp_data = TimeSeriesData(value=25, num_time_intervals=NUMBER_INTERVALS,
                               num_expansion_intervals=NUM_EXPANSION_PERIODS)
ambient_temp_dict = expand_as_dict(amb_temp_data)


def default_surface_area_of_cylinder(volume: float, include_bottom: bool = True):
    """Given volume of the cylinder in cubic meters, calculate surface area. Assuming height to diameter ration H/D=3.

    If include_bottom is False, do not include bottom surface.
    """
    radius = np.cbrt(volume/(np.pi*6))
    height = 6*radius
    if include_bottom:
        return round(2*np.pi*radius*height + 2*np.pi*radius**2,3)
    else:
        return round(2 * np.pi * radius * height + np.pi * radius ** 2,3)


def test_thermal_storage():
    u_ins = 5  # W/sqm*C (from 0.5 - 11 is reasonable range)
    mass = 500
    min_temp = 10
    max_temp = 80
    area = default_surface_area_of_cylinder(mass*1e-3)
    q_max_joules = 4184 * mass * (max_temp-min_temp)  # Max energy storage capacity in joules
    q_max_kwh = q_max_joules / 3600000
    th_load = [0.1] * 14 + [0.4] * 4 + [0.05] * 16 + [0.4] * 6 + [0.2] * 8
    th_load = list((np.array(th_load) * q_max_kwh).round())
    th_demand_data = TimeSeriesData(value=th_load,
                                    num_time_intervals=NUMBER_INTERVALS,
                                    num_expansion_intervals=NUM_EXPANSION_PERIODS)
    th_demand_dict = expand_as_dict(th_demand_data)

    storage = ThermalStorage(max_temp=max_temp,
                             min_temp=min_temp,
                             ambient_temp=ambient_temp_dict,
                             storage_mass=mass,
                             specific_heat=4184,
                             ins_transmittance=u_ins,
                             surface_area=area,
                             separate_in_out_ports=False)
    # assert that ports units default to KWT
    assert all([v.units == Units.KWT for v in storage.ports.values()])
    assert storage.initial_temp == storage.min_temp + 0.5*(storage.max_temp-storage.min_temp)

    # storage_1p = ThermalStorage(max_temp=max_temp,
    #                          min_temp=min_temp,
    #                          ambient_temp=ambient_temp_dict,
    #                          storage_mass=mass,
    #                          specific_heat=4184,
    #                          ins_transmittance=u_ins,
    #                          surface_area=area,
    #                          separate_in_out_ports=False)
    #
    # # assert number of ports
    # assert len(list(storage_1p.ports.values())) == 1

    thermal_demand = Node(node_name="thermal_load",
                          ports={"demand_kwt": Sink(units=Units.KWT)})

    thermal_demand.ports["demand_kwt"].add_sink_profile(th_demand_dict)

    thermal_mains = Node(node_name="thermal_supply",
                         ports={"supply_kwt": FlexPort(units=Units.KWT)})

    cp = TellegenNode(node_name="conn_point",
                      ports={"to_supply_kwt": FlexPort(units=Units.KWT),
                             "to_storage_kwt": FlexPort(units=Units.KWT),
                             "to_demand_kwt": FlexPort(units=Units.KWT)})
    system = OptimisationGraph()
    system.add_node_obj([storage, thermal_demand, thermal_mains, cp])
    system.connect_ports_and_create_edge(cp.ports["to_supply_kwt"], thermal_mains.ports["supply_kwt"])
    system.connect_ports_and_create_edge(cp.ports["to_storage_kwt"], storage.ports["input_output"])
    system.connect_ports_and_create_edge(cp.ports["to_demand_kwt"], thermal_demand.ports["demand_kwt"])
    objective_set = ObjectiveSet(objective_list=[PeakPositivePower(component=cp.ports["to_supply_kwt"])])

    optimise_results_no = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=INTERVAL_DURATION,
            number_of_intervals=NUMBER_INTERVALS,
            number_of_expansion_intervals=NUM_EXPANSION_PERIODS),
        engine_settings=engine_settings_from_environment(),
        graph=system)

    q_max_joules = 4184 * mass * (max_temp-min_temp)  # Max energy storage capacity in joules
    q_max_kwh = q_max_joules / 3600000
    storage_temp = getattr(optimise_results_no.model, storage.internal_temp).get_values()
    loss_gain = getattr(optimise_results_no.model, storage.net_loss_gain).get_values()
    soc_100 = optimise_results_no.df()[storage.soc_value][0] * 1 / q_max_kwh

    # Check that SOC values (in energy units) make sense
    assert all([0 <= v <= 1 for v in soc_100.values])

    cp_flow_df_no = optimise_results_no.df_by_port()[[k for k in cp.ports.keys()]].reset_index(level=[0]).drop(columns='level_0')

    # Check that SOC values (in energy units) make sense
    assert all([0 <= v <= 1 for v in soc_100.values])

    # Check that heat loss/gain to environment is calculated correctly
    assert all([round(loss_gain[k]) >= round((storage.ambient_temp[k]-storage_temp[k])*storage.lump_conductance)
                for k in loss_gain.keys()])

    # # Not expecting storage to do anything when no objective set
    # assert cp_flow_df_no["to_storage_kwt"].min() == cp_flow_df_no["to_storage_kwt"].max()==0

    optimise_results_pp = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=INTERVAL_DURATION,
            number_of_intervals=NUMBER_INTERVALS,
            number_of_expansion_intervals=NUM_EXPANSION_PERIODS),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=objective_set)

    cp_flow_df_pp = optimise_results_pp.df_by_port()[[k for k in cp.ports.keys()]].reset_index(level=[0]).drop(
        columns='level_0')

    # Expecting peak power to be less with peak power objective
    assert cp_flow_df_no["to_supply_kwt"].max() >= cp_flow_df_pp["to_supply_kwt"].max()



