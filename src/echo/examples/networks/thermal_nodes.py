import numpy as np

from echo.utils import TimeSeriesData, expand_as_dict
from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode, Sink, FixedPort
from echo.models.base import Node, OptimisationGraph, TransformNode

from echo.models.thermal import ThermalStorage, HeatPump, HotWaterTank, HeatPumpSingleOutput
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.objectives.base import ObjectiveSet
from echo.objectives.power import PeakPositivePower
from echo.objectives.tariff import ThroughputCost
from echo.optimiser import optimise
import pandas as pd

pd.options.plotting.backend = "plotly"


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


NUMBER_INTERVALS = 48
INTERVAL_DURATION = 30
NUM_EXPANSION_PERIODS = 1

amb_temp_data = TimeSeriesData(
    value=25, num_time_intervals=NUMBER_INTERVALS, num_expansion_intervals=NUM_EXPANSION_PERIODS
)
ambient_temp_dict = expand_as_dict(amb_temp_data)
# Use simply COP = 1 for testing
cop_data = TimeSeriesData(
    value=1, num_time_intervals=NUMBER_INTERVALS, num_expansion_intervals=NUM_EXPANSION_PERIODS
)
cop_dict = expand_as_dict(cop_data)
# Thermal transmittance of storage insulation in W/sqm*C (from 0.5 - 11 is reasonable range)
u_ins = 5
# mass of thermal storage in kg
tank_volume = 350
# Specific heat capacity of storage medium (here is water) in J/kg*C
c_p = 4184
area = default_surface_area_of_cylinder(tank_volume)
max_temp_dhw = 65
min_temp_dhw = 45
temp_mains_dhw = 10

# DHW demand profile
dhw_load_normalised = [0] * 8 + [0.2] * 4 + [0.3] * 4 + [0.05] * 16 + [0.1] * 4 + [0.2] * 4 + [0.05] * 8
dhw_total_daily_ltr = 200
dhw_load_litres = list((np.array(dhw_load_normalised) * dhw_total_daily_ltr / sum(dhw_load_normalised)).round())


dhw_load_data = TimeSeriesData(
    value=dhw_load_litres, num_time_intervals=NUMBER_INTERVALS, num_expansion_intervals=NUM_EXPANSION_PERIODS
)

dhw_load_data_dict = expand_as_dict(dhw_load_data)


###########################

dhw_demand = Node(node_name="dhw_load", ports={"demand_lps": Sink(units=Units.LPS)})
dhw_demand.ports["demand_lps"].add_sink_profile(dhw_load_data_dict)
grid = Node(node_name="grid", ports={"supply_kw": FlexPort(units=Units.KW)})
heat_pump = HeatPumpSingleOutput(node_name='heat_pump',
                                 heating_cop_time_series=cop_dict,
                                 cooling_cop_time_series=cop_dict)

hwt = HotWaterTank(
    max_outlet_temp=max_temp_dhw,
    min_outlet_temp=min_temp_dhw,
    inlet_temp=temp_mains_dhw,
    ambient_temp=ambient_temp_dict,
    tank_volume=tank_volume,
    max_flow_rate=9,
    ins_transmittance=u_ins,
    surface_area=area,
    energy_flow_units=Units.KWT
)

system = OptimisationGraph()
system.add_node_obj([grid, heat_pump, hwt, dhw_demand])
system.connect_ports_and_create_edge(grid.ports["supply_kw"], heat_pump.ports["input"])
system.connect_ports_and_create_edge(heat_pump.ports["output"], hwt.ports["thermal_input"])
system.connect_ports_and_create_edge(hwt.ports["water_output"], dhw_demand.ports["demand_lps"])

objective_set = ObjectiveSet(
    objective_list=[
        PeakPositivePower(component=heat_pump.ports["input"])
    ]
)


optimise_results = optimise(
    scenario_settings=ScenarioSettings(
        interval_duration=INTERVAL_DURATION,
        number_of_intervals=NUMBER_INTERVALS,
        number_of_expansion_intervals=NUM_EXPANSION_PERIODS,
    ),
    engine_settings=engine_settings_from_environment(),
    graph=system,
    objective_set=objective_set,
)
