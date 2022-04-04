from __future__ import division
import matplotlib.pyplot as plt
import seaborn as sns
from pyomo.util.infeasible import log_infeasible_constraints
import networkx as nx


from echo.echo_models import *
from echo.echo_optimiser import EchoOptimiser
from echo.objectives import *

# set up seaborn the way you like
sns.set_style({'axes.linewidth': 1, 'axes.edgecolor': 'black', 'xtick.direction': \
    'out', 'xtick.major.size': 4.0, 'ytick.direction': 'out', 'ytick.major.size': 4.0, \
               'axes.facecolor': 'white', 'grid.color': '.8', 'grid.linestyle': u'-', 'grid.linewidth': 0.5})



system = OptimisationGraph()

# Whole system
bulk_grid = BulkGrid()
bulk_gas = BulkGas()

connection_point = ElectricalTellegenNode()
connection_point.add_named_electrical_ports(['grid', 'soad', 'som'])

gas_cp = GasTellegenNode()
gas_cp.ports['bulk'] = GasPort()
gas_cp.ports['soad'] = GasPort()
gas_cp.ports['som'] = GasPort()

### School of Art and Design (SoAD)

# Electrical assets
elec_conn_pt_soad = ElectricalTellegenNode()
elec_conn_pt_soad.add_named_electrical_ports(['cp', 'heat_pump', 'pv', 'kiln'])

elec_kiln = Node()
ek = ElectricalDemand()
elec_kiln.ports['kiln'] = ek

heat_pump_soad = Node()
hp_soad = ElectricalDemand()
heat_pump_soad.ports['heat_pump'] = hp_soad

solar = Node()
pv = ElectricalGeneration()
solar.ports['pv'] = pv

# Gas assets
gas_cp_soad = Node()
gas_cp_soad.ports['cp'] = GasPort()
gas_cp_soad.ports['b1'] = GasPort()
gas_cp_soad.ports['b2'] = GasPort()
gas_cp_soad.ports['kiln'] = GasPort()

boiler1_soad = Node()
b1_soad = GasPort()
b1_soad.set_flow_constraints(max_import=None, max_export=None)
boiler1_soad.ports['b1'] = b1_soad

boiler2_soad = Node()
b2_soad = GasPort()
b2_soad.set_flow_constraints(max_import=None, max_export=None)
boiler2_soad.ports['b2'] = b2_soad

gas_kiln = Node()
gk = GasPort()
gas_kiln.ports['kiln'] = gk


# Add assets and do connections
system.add_node_obj([bulk_grid,
                     bulk_gas,
                     connection_point,
                     elec_conn_pt_soad,
                     gas_cp,
                     gas_cp_soad,
                     elec_kiln,
                     heat_pump_soad,
                     solar,
                     boiler2_soad,
                     boiler1_soad,
                     gas_kiln])

# Electrical connections
system.connect_ports_and_create_edge(bulk_grid.ports['grid'], connection_point.ports['grid'])
system.connect_ports_and_create_edge(connection_point.ports['soad'], elec_conn_pt_soad.ports['cp'])
system.connect_ports_and_create_edge(elec_conn_pt_soad.ports['pv'], solar.ports['pv'])
system.connect_ports_and_create_edge(elec_conn_pt_soad.ports['heat_pump'], heat_pump_soad.ports['heat_pump'])
system.connect_ports_and_create_edge(elec_conn_pt_soad.ports['kiln'], elec_kiln.ports['kiln'])

# Gas connections
system.connect_ports_and_create_edge(bulk_gas.ports['gas'], gas_cp.ports['bulk'])
system.connect_ports_and_create_edge(gas_cp.ports['soad'], gas_cp_soad.ports['cp'])
system.connect_ports_and_create_edge(gas_cp_soad.ports['b1'], boiler1_soad.ports['b1'])
system.connect_ports_and_create_edge(gas_cp_soad.ports['b2'], boiler2_soad.ports['b2'])
system.connect_ports_and_create_edge(gas_cp_soad.ports['kiln'], gas_kiln.ports['kiln'])


### School of Music (SoM)

# Electrical assets
elec_conn_pt_som = ElectricalTellegenNode()
elec_conn_pt_som.add_named_electrical_ports(['cp', 'chiller', 'other'])

chiller = Node()
ch = ElectricalDemand()
chiller.ports['chiller'] = ch

other = Node()
ot = ElectricalDemand()
other.ports['other'] = ot

# Gas assets
gas_cp_som = Node()
gas_cp_som.ports['cp'] = GasPort()
gas_cp_som.ports['som'] = GasPort()
gas_cp_som.ports['pk'] = GasPort()

som_boiler = Node()
som_b = GasPort()
som_b.set_flow_constraints(max_import=None, max_export=None)
som_boiler.ports['som'] = som_b

pk_boiler = Node()
pk_b = GasPort()
pk_b.set_flow_constraints(max_import=None, max_export=None)
pk_boiler.ports['pk'] = pk_b

# Add assets and do connections
system.add_node_obj([elec_conn_pt_som,
                     gas_cp_som,
                     chiller,
                     som_boiler,
                     pk_boiler,
                     other])

# Electrical connections

system.connect_ports_and_create_edge(connection_point.ports['som'], elec_conn_pt_som.ports['cp'])
system.connect_ports_and_create_edge(elec_conn_pt_som.ports['chiller'], chiller.ports['chiller'])
system.connect_ports_and_create_edge(elec_conn_pt_som.ports['other'], other.ports['other'])

# Gas connections
system.connect_ports_and_create_edge(gas_cp.ports['som'], gas_cp_som.ports['cp'])
system.connect_ports_and_create_edge(gas_cp_som.ports['som'], som_boiler.ports['som'])
system.connect_ports_and_create_edge(gas_cp_som.ports['pk'], pk_boiler.ports['pk'])

nx.draw(system)






