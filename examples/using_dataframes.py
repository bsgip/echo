from __future__ import division

import pandas as pd

from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import ElectricalGeneration, FixedElectricalPort
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.optimiser import optimise

time_periods = 48

df = pd.DataFrame({"load": [5] * time_periods, "solar": [-2] * time_periods})

# Set up hyper params

interval_duration = 30
expansion_periods = 1
discount_rate = 0

# Create graph
system = OptimisationGraph()

# Create assets
grid = Node(node_name="grid")
grid.add_port("grid", FlexPort(units=Units.KW))

connection_point = TellegenNode(node_name="cp")
connection_point.add_ports_from_list(["load", "pv", "grid"], FlexPort, units=Units.KW)

load = Node(node_name="load")
l1 = FixedElectricalPort()
l1.initial_value_ref = "load"
load.add_port("load", l1)

solar = Node(node_name="pv")
pv = ElectricalGeneration()
pv.initial_value_ref = "solar"
solar.add_port("pv", pv)


# Populate graph with assets (nodes)
system.add_nodes_from([grid, load, connection_point, solar])

system.connect_ports_and_create_edge(grid.get_port("grid"), connection_point.get_port("grid"))
system.connect_ports_and_create_edge(pv, connection_point.get_port("pv"))
system.connect_ports_and_create_edge(l1, connection_point.get_port("load"))

# Invoke the optimiser and optimise
optimise_results = optimise(
    scenario_settings=ScenarioSettings(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=discount_rate,
    ),
    engine_settings=engine_settings_from_environment(),
    profile=df,
    graph=system,
    verbose=True,
)
