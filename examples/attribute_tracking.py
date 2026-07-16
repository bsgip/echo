import numpy as np
import pandas as pd
from typing import Any
import networkx as nx

from echo.configuration import Units
from echo.models.agnostic import FlexPort, Sink, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.models.thermal import ThermalStorage
from echo.objectives.base import ObjectiveSet
from echo.objectives.power import PeakPositivePower
from echo.objectives.tariff import ThroughputCost
from echo.optimiser import optimise
from echo.utils import TimeSeriesData, expand_as_dict
from echo import visualization as viz

pd.options.plotting.backend = "plotly"


""" A simple thermal network.
    A heating load, thermal storage and heating mains are connected via a connection point (TellegenNode).
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
INSULATION_TRANSMITTANCE = 5
# mass of thermal storage in kg
MASS = 500
# Specific heat capacity of storage medium (here is water) in J/kg*C
SPECIFIC_HEAT_CAPACITY_WATER = 4184
# Total surface area of thermal storage from volume (for water 1 kg=1 litre)
SURFACE_AREA = default_surface_area_of_cylinder(MASS * 1e-3)

# ----------------------------------------------------------------------------------------------------------------------
#   2. Define thermal demand profile and ambient temperature profile
# ----------------------------------------------------------------------------------------------------------------------

q_max_joules = SPECIFIC_HEAT_CAPACITY_WATER * MASS * 70  # Max energy storage capacity in joules
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
    node_name="thermal_storage",
    max_temp=80,
    min_temp=10,
    ambient_temp=ambient_temp_dict,
    storage_mass=MASS,
    specific_heat=SPECIFIC_HEAT_CAPACITY_WATER,
    ins_transmittance=INSULATION_TRANSMITTANCE,
    surface_area=SURFACE_AREA,
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
#
#     thermal_mains---cp---thermal_demand
#                     |
#                  storage
#
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

optimise_results.model.pprint()
# optimise_results.model.display()


graph = system.convert_to_nx()
positions = nx.spring_layout(graph)

tracker = optimise_results.model_attribute_tracker
print(tracker)


def to_html_string(attrs: dict[str, list[Any]]):
    attr_text = ""
    for attr_class in sorted(attrs.keys()):
        attr_text += "<br>"
        attr_descriptions = [f" <i>{attr_class}</i> '{attr_name}'<br>" for attr_name in sorted(attrs[attr_class])]
        attr_text += "".join(attr_descriptions)

    return attr_text


def node_hover_text(node: Any, *_) -> str:
    node_object = optimise_results.graph.node_obj[node]
    node_type = type(node_object).__name__

    tracker = optimise_results.model_attribute_tracker
    if tracker is not None:
        attrs = tracker.filtered_pairwise_attributes(include=lambda _, checkpoint: checkpoint.startswith(node))
        title = f"<b>{node_type}</b> '{node}'<br>"
        return title + to_html_string(attrs)

    return ""


def edge_hover_text(edge: Any, *_) -> str:
    edge_reversed = edge[::-1]  # reverse the edge tuple (not sure why edges are defined in the opposite sense)
    edge_object = optimise_results.graph.edge_obj[edge_reversed]

    tracker = optimise_results.model_attribute_tracker
    if tracker is not None:
        # Get the attributes that were added when `edge` was added to the pyomo model
        attrs = tracker.filtered_pairwise_attributes(include=lambda _, checkpoint: checkpoint == edge_object.edge_name)
        title = f"<b>{edge}</b><br>"
        return title + to_html_string(attrs)
    return ""

def node_size(*_) -> int:
    return 40

# Use the new visualization function to plot the network/graph
# This function takes callbacks for setting the node (colors, text/labels, hover text etc).
fig = viz.PlotlyGraph.plot(
    graph=graph,
    positions=positions,
    show_node_names=True,
    node_color=viz.echo_node_color,
    node_size=node_size,
    node_text=viz.echo_node_text,
    node_hover_text=node_hover_text,
    edge_hover_text=edge_hover_text,
)
fig.show()
