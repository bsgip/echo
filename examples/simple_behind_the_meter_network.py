from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import (ElectricalDemand, ElectricalGeneration,
                                    ElectricalStorage, Inverter)

""" A behind-the-meter battery network

    A load and pv are also connected resulting in this graph:

                       +------+
                    +--+ load |
+------+  +------+  |  +------+         +---------+
| grid +--+ C.P. +--+                +--+ battery |
+------+  +------+  |  +----------+  |  +---------+
                    +--+ inverter +--+
                       +----------+  |  +------+
                                     +--+ P.V. |
                                        +------+
"""

# ----------------------------------------------------------------------------------------------------------------------
#   1. Define the nodes and edges
# ----------------------------------------------------------------------------------------------------------------------

# Create a node representing upstream grid
grid = Node(node_name="grid")
grid.add_port(
    "grid", FlexPort(units=Units.KW)
)  # create a port which will be used to connect this with the connection_point

# Create a connection point
connection_point = TellegenNode(node_name="CP")
connection_point.add_ports_from_list(
    ["load", "inv", "grid"], FlexPort, units=Units.KW
)  # create ports to connect to the grid, the load, and the inverter

# Create a load
load = Node(node_name="load")
l1 = ElectricalDemand()  # create an electrical demand to attach to this node
load.ports["load"] = l1  # add the electrical demand to a port of the load node

# Create an inverter node with some properties,
# if the constraints are not none then they should be max_export <= 0 <= max_import
# can also set efficiency on the dc and the ac side in the range 0-1
inverter = Inverter(
    node_name="inverter",
    max_import=None,
    max_export=None,
    dc_ac_efficiency=1,
    ac_dc_efficiency=1,
    ac_port_name="inv",
    dc_port_names=["bess", "pv"],
)

# Create a node for the battery
battery = Node(node_name="battery")
b = ElectricalStorage(
    max_capacity=15.0,  # max capacity of battery in kwh
    depth_of_discharge_limit=0,  # allowable depth of discharge in range [0,100] (i.e. percent)
    charging_power_limit=1.25,  # max charging rate in kW
    discharging_power_limit=-1.25,  # max discharging rate in kW
    charging_efficiency=1,  # charging efficiency in range [0,1]
    discharging_efficiency=1,  # discharging efficiency in range [0,1]
    initial_state_of_charge=0.0,
)  # initial state of charge in kWh
# connect the electrical storage to a port on the battery node
battery.ports["bess"] = b

# create a node for the solar panel
solar = Node(node_name="solar")
pv = ElectricalGeneration()  # create an electrical generation object
pv.curtailable = False  # set whether this can be curtailed or not
solar.ports["pv"] = pv  # add the electrical generation to a port on the solar node


# ----------------------------------------------------------------------------------------------------------------------
#   4. Build the optimisation graph
# ----------------------------------------------------------------------------------------------------------------------

network = OptimisationGraph()

# Populate graph with assets (nodes)
network.add_node_obj([grid, battery, load, solar, connection_point, inverter])

# Add edges to graph (i.e. connect up the graph structure how we want it)
network.connect_ports_and_create_edge(grid.ports["grid"], connection_point.ports["grid"])
network.connect_ports_and_create_edge(connection_point.ports["load"], load.ports["load"])
network.connect_ports_and_create_edge(connection_point.ports["inv"], inverter.ports["inv"])
network.connect_ports_and_create_edge(inverter.ports["bess"], battery.ports["bess"])
network.connect_ports_and_create_edge(inverter.ports["pv"], solar.ports["pv"])
