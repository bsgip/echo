import numpy as np

from echo.utils import TimeSeriesData, expand_as_dict
from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode, Sink
from echo.models.base import Node, OptimisationGraph

from echo.models.thermal import ThermalStorage
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.objectives.base import ObjectiveSet
from echo.objectives.power import PeakPositivePower
from echo.objectives.tariff import ThroughputCost
from echo.optimiser import optimise
import pandas as pd

pd.options.plotting.backend = "plotly"


""" A simple thermal network

    A heating load, thermal storage and heating mains are connected resulting in this graph:
                       +--------+
                    +--+ th load
+------+     +------+  |  +--------+
|th mains +--+ C.P. +--+
+------+     +------+  |  +----------+
                    +--+ th storage
                       +----------+
"""

# ----------------------------------------------------------------------------------------------------------------------
#   1. Define constants
# ----------------------------------------------------------------------------------------------------------------------

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


# Thermal transmittance of storage insulation in W/sqm*C (from 0.5 - 11 is reasonable range)
u_ins = 5
# mass of thermal storage in kg
mass = 500
# Specific heat capacity of storage medium (here is water) in J/kg*C
c_p = 4184
# Total surface area of thermal storage from volume (for water 1 kg=1 litre)
area = default_surface_area_of_cylinder(mass * 1e-3)

# ----------------------------------------------------------------------------------------------------------------------
#   2. Define thermal demand profile and ambient temperature profile
# ----------------------------------------------------------------------------------------------------------------------

q_max_joules = c_p * mass * 70  # Max energy storage capacity in joules
q_max_kwh = q_max_joules / 3600000
th_load = [0.1] * 14 + [0.4] * 4 + [0.05] * 16 + [0.4] * 6 + [0.2] * 8
th_load = list((np.array(th_load) * q_max_kwh).round())

th_demand_data = TimeSeriesData(
    value=th_load, num_time_intervals=NUMBER_INTERVALS, num_expansion_intervals=NUM_EXPANSION_PERIODS
)

th_demand_dict = expand_as_dict(th_demand_data)

amb_temp_data = TimeSeriesData(
    value=25, num_time_intervals=NUMBER_INTERVALS, num_expansion_intervals=NUM_EXPANSION_PERIODS
)
ambient_temp_dict = expand_as_dict(amb_temp_data)

# ----------------------------------------------------------------------------------------------------------------------
#   3. Define nodes
# ----------------------------------------------------------------------------------------------------------------------

thermal_demand = Node(node_name="thermal_load", ports={"demand_kwt": Sink(units=Units.KWT)})

thermal_demand.ports["demand_kwt"].add_sink_profile(th_demand_dict)

thermal_mains = Node(node_name="thermal_supply", ports={"supply_kwt": FlexPort(units=Units.KWT)})

storage = ThermalStorage(
    max_temp=80,
    min_temp=10,
    ambient_temp=ambient_temp_dict,
    storage_mass=mass,
    specific_heat=4184,
    ins_transmittance=u_ins,
    surface_area=area,
    separate_in_out_ports=False,
)

cp = TellegenNode(
    node_name="conn_point",
    ports={
        "to_supply_kwt": FlexPort(units=Units.KWT),
        "to_storage_kwt": FlexPort(units=Units.KWT),
        "to_demand_kwt": FlexPort(units=Units.KWT),
    },
)

# ----------------------------------------------------------------------------------------------------------------------
#   4. Build the optimisation graph
# ----------------------------------------------------------------------------------------------------------------------

system = OptimisationGraph()
system.add_node_obj([storage, thermal_demand, thermal_mains, cp])
system.connect_ports_and_create_edge(cp.ports["to_supply_kwt"], thermal_mains.ports["supply_kwt"])
system.connect_ports_and_create_edge(cp.ports["to_storage_kwt"], storage.ports["input_output"])
system.connect_ports_and_create_edge(cp.ports["to_demand_kwt"], thermal_demand.ports["demand_kwt"])

objective_set = ObjectiveSet(
    objective_list=[
        ThroughputCost(component=storage.ports["input_output"], rate=0.01),
        PeakPositivePower(component=cp.ports["to_supply_kwt"]),
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


""" When Storage has two ports, we need two connection points as only one edge is allowed between any two nodes
"""

# ----------------------------------------------------------------------------------------------------------------------
#   5. Create thermal storage with 2 ports and two separate connection points
# ----------------------------------------------------------------------------------------------------------------------


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

cp_1 = TellegenNode(
    node_name="conn_point_supply",
    ports={
        "to_supply_kwt": FlexPort(units=Units.KWT),
        "to_demand_cp_kwt": FlexPort(units=Units.KWT),
        "to_storage_input_kwt": FlexPort(units=Units.KWT),
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

# ----------------------------------------------------------------------------------------------------------------------
#   6. Build new optimisation graph
# ----------------------------------------------------------------------------------------------------------------------


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
obj_list = [ThroughputCost(component=storage_2p.ports[_port_name], rate=0.01) for _port_name in storage_2p.ports]
obj_list.append(PeakPositivePower(component=cp_1.ports["to_supply_kwt"]))
objective_set = ObjectiveSet(objective_list=obj_list)

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

storage_temp = getattr(optimise_results.model, storage_2p.internal_temp).get_values()
loss_gain = getattr(optimise_results.model, storage_2p.net_loss_gain).get_values()
soc_kwth = optimise_results.df()[storage_2p.soc_value]
soc_100 = optimise_results.df()[storage_2p.soc_value][0] * 1 / q_max_kwh

cp_flow_df = (
    optimise_results.df_by_port()[[k for k in cp_1.ports.keys()]].reset_index(level=[0]).drop(columns="level_0")
)
cp_flow_df_2 = (
    optimise_results.df_by_port()[[k for k in cp_2.ports.keys()]].reset_index(level=[0]).drop(columns="level_0")
)
cp_flow_df = cp_flow_df.join(cp_flow_df_2)

fig = cp_flow_df.plot(
    title="Connection Point flows in KWTh",
    labels=dict(index="Time", value="KWTh"),
)
fig.show()

fig = pd.DataFrame(soc_100).plot(
    title="Thermal Storage SOC in KWTh",
    labels=dict(index="Time", value="KWTh", variable="SOC"),
)
fig.show()
