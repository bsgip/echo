from __future__ import division

import networkx as nx
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pyomo.core import Var
from pyomo.util.infeasible import log_infeasible_constraints

import sys

sys.path.append("../")
from echo_models import ElectricalDemand, ElectricalGeneration, ElectricalStorage, ElectricalNode, \
    OptimisationGraph, Tariff, Node, Port, Edge, Transform, ElectricalPort, CarbonPort
from echo_optimiser import EchoOptimiser
from configuration import NodeRule, TransformRule, FlowConstraint, Flows
from networkx import Graph, draw

# set up seaborn the way you like
sns.set_style({'axes.linewidth': 1, 'axes.edgecolor': 'black', 'xtick.direction': \
    'out', 'xtick.major.size': 4.0, 'ytick.direction': 'out', 'ytick.major.size': 4.0, \
               'axes.facecolor': 'white', 'grid.color': '.8', 'grid.linestyle': u'-', 'grid.linewidth': 0.5})

############################ Define an Example Optimisation Problem ########################################

# Example problem - 2 separate nodes (loads/sites) supplied from a single supply point that is connected to the grid.
# Site 1 has a load + pv
# Site 2 has the same load + pv

# The load and pv arrays below are in kwh consumed per 15 minutes
test_load = np.array(
    [2.13, 2.09, 2.3, 2.11, 2.2, 2.23, 2.2, 2.15, 2.02, 2.19, 2.19, 2.19, 2.12, 2.15, 2.25, 2.12, 2.21, 2.16,
     2.26, 2.13, 2.08, 2.15, 2.42, 2.02, 2.3, 2.26, 2.35, 2.55, 3.23, 2.98, 3.49, 3.5, 3.12, 3.52, 3.94, 3.55,
     3.99, 3.71, 3.38, 3.76, 3.71, 3.78, 3.29, 3.65, 3.61, 3.75, 3.38, 3.66, 3.56, 3.69, 3.3, 3.61, 3.71, 3.82,
     3.17, 3.69, 3.74, 3.86, 3.57, 3.55, 3.75, 3.6, 3.67, 3.48, 3.51, 3.46, 3.19, 3.38, 3.19, 3.38, 3.04, 3.12,
     2.91, 3.11, 3.13, 2.77, 2.24, 2.54, 2.24, 2.24, 2.09, 2.33, 2.17, 2.16, 1.97, 2.16, 2.21, 2.18, 2.01, 2.16,
     2.19, 2.11, 2.17, 2.13, 2.05, 2.19])

test_pv = 2 * np.array(
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.23, 0.52,
     0.74, 0.71, 0.63, 0.68, 0.97, 0.01, 0.52, 0.83, 0.83, 0.79, 1.22, 1.36, 1.27, 1.42, 1.97, 2.56, 2.91, 3.24,
     3.8, 4.3, 4.62, 4.84, 4.6, 4.17, 3.77, 3.76, 3.38, 2.64, 1.96, 1.76, 1.85, 2.4, 3.82, 5.13, 4.97, 5.02, 5.43,
     5.32, 3.56, 1.75, 1.43, 1.65, 1.69, 2.3, 2.71, 2.41, 2.63, 2.6, 1.9, 0.78, 0.13, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
     0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
test_pv *= -1  # convert solar generation to negative to match convention.

# Site 1
net_load = test_load + test_pv
# split load into import and export
connection_point_import = np.copy(net_load)
connection_point_export = np.copy(net_load)

for j, e in enumerate(net_load):
    if e >= 0:
        connection_point_export[j] = 0

    else:
        connection_point_import[j] = 0

# Tariffs are in $ / kwh
import_tariff = np.array(([0.1] * 28 + [0.3] * 8 + [0.2] * 32 + [0.3] * 16 + [0.1] * 12))
export_tariff = np.array(([0.0] * 96))

############################ Optimise this Example ########################################

np.set_printoptions(suppress=True)

# Parameters
expansion_periods = 2
storage_expansions_per_period = 1
generator_expansions_per_period = 0
capacity_expansions_per_period = 0
combined_asset_capacity_expansions_per_period = 0

# Discounting
discount_rate = 0
dr = {}
for ep in range(0, expansion_periods):
    dr[ep] = 1 / ((1 + discount_rate) ** ep)

# Setup load, pv, and tariffs as dictionaries
d1 = {}
d2 = {}
gen1 = {}
gen2 = {}
it = {}
et = {}

site2_load_scale = 1.5
site2_pv_scale = 0.5
for ep in range(0, expansion_periods):
    for i, _ in enumerate(connection_point_import):
        d1[(ep, i)] = connection_point_import[i]
        d2[(ep, i)] = connection_point_import[i]*site2_load_scale
        gen1[(ep, i)] = connection_point_export[i]
        gen2[(ep, i)] = connection_point_export[i]*site2_pv_scale
        it[(ep, i)] = import_tariff[i]
        et[(ep, i)] = export_tariff[i]

# Setup graph
ES = OptimisationGraph()
ES.global_storage_exp_con = storage_expansions_per_period  # ToDo - better way to carry these parameters
ES.global_generator_exp_con = generator_expansions_per_period  # ToDo - better way to carry these parameters
ES.global_combined_asset_capacity_expansion_con = combined_asset_capacity_expansions_per_period
ES.expansion_periods = expansion_periods
ES.discount_factors = dr

# Setup model components

tariff = Tariff()
tariff.add_tariff_profile_export(et)
tariff.add_tariff_profile_import(it)

grid = Node()
emissions = CarbonPort()
emissions.flows = Flows.Export
grid.ports['grid'] = ElectricalPort()
grid.ports['CO2'] = emissions
gt = Transform()
gt.add_rhs(0)
gt.add_lhs(emissions, TransformRule.Both, 0.7*4)
gt.add_lhs(grid.ports['grid'], TransformRule.NegativeComponent, -1)
grid.add_transformation(gt)
grid.node_rule = NodeRule.Transform
ES.add_node_obj(grid)

# Site 1

load1 = Node()
l1 = ElectricalDemand()
l1.add_demand_profile(d1)
load1.ports['demand'] = l1

solar1 = Node()
pv1 = ElectricalGeneration()
pv1.add_generation_profile(gen1)
solar1.ports['solar'] = pv1

site1 = ElectricalNode()
cp1 = ElectricalPort()
cp1.has_tariff = True
cp1.tariff = tariff

site1.ports['CP'] = cp1
site1.ports['loadCP'] = ElectricalPort()
site1.ports['pvCP'] = ElectricalPort()
site1.node_rule = NodeRule.Tellegen

ES.add_node_obj(load1)
ES.add_node_obj(site1)
ES.add_node_obj(solar1)

load_edge1 = Edge()
load_edge1.add_vertices(site1.ports['loadCP'], l1)
pv_edge1 = Edge()
pv_edge1.add_vertices(site1.ports['pvCP'], pv1)

ES.add_edge_obj(load_edge1)
ES.add_edge_obj(pv_edge1)

# Site 2

load2 = Node()
l2 = ElectricalDemand()
l2.add_demand_profile(d2)
load2.ports['demand'] = l2

solar2 = Node()
pv2 = ElectricalGeneration()
pv2.add_generation_profile(gen2)
solar2.ports['solar'] = pv2

site2 = ElectricalNode()
cp2 = ElectricalPort()
cp2.has_tariff = True
cp2.tariff = tariff

site2.ports['CP'] = cp2
site2.ports['loadCP'] = ElectricalPort()
site2.ports['pvCP'] = ElectricalPort()
site2.node_rule = NodeRule.Tellegen

ES.add_node_obj(load2)
ES.add_node_obj(site2)
ES.add_node_obj(solar2)

load_edge2 = Edge()
load_edge2.add_vertices(site2.ports['loadCP'], l2)
pv_edge2 = Edge()
pv_edge2.add_vertices(site2.ports['pvCP'], pv2)

# Add edge objects to ES - this creates an actual networkx edge
ES.add_edge_obj(load_edge2)
ES.add_edge_obj(pv_edge2)

# Create intermediate node for connecting the two sites to the grid
pcc = Node()
pcc.ports['site1'] = ElectricalPort()
pcc.ports['site2'] = ElectricalPort()
pcc.ports['grid'] = ElectricalPort()
pcc.node_rule = NodeRule.Tellegen
pcc.expansion_planning = True
pcc.storage_planning = True
site1.storage_planning_capex = 0

ES.add_node_obj(pcc)

site1_edge = Edge()
site1_edge.add_vertices(site1.ports['CP'], pcc.ports['site1'])
site2_edge = Edge()
site2_edge.add_vertices(site2.ports['CP'], pcc.ports['site2'])
grid_edge = Edge()
grid_edge.add_vertices(pcc.ports['grid'], grid.ports['grid'])

# Add edge objects to ES - this creates an actual networkx edge
ES.add_edge_obj(site1_edge)
ES.add_edge_obj(site2_edge)
ES.add_edge_obj(grid_edge)


# Expansion planning settings
site1.expansion_planning = True
site1.storage_planning = True
site1.storage_planning_capex = 0

site2.expansion_planning = True
site2.storage_planning = True
site1.storage_planning_capex = 0


############################ ----------------------- ########################################

# Invoke the optimiser and optimise
optimiser = EchoOptimiser(15, 96, expansion_periods, ES)

log_infeasible_constraints(optimiser.model)

############################ Analyse the Optimisation ########################################

# Print capacities of expansion planning assets
expansion_ports = optimiser.get_expansion_ports()
print('\nExpansion storage capacities (kWh): ')
for x in expansion_ports:
    print(optimiser.values(x.optimised_storage_capacity,expansion_periods))

colors = sns.color_palette()
hrs = np.arange(0, len(test_load)) / 4

############################ ----------------------- ########################################

# Site 1
fig = plt.figure(figsize=(14, 9))
ax1 = fig.add_subplot(2, 2, 1)
plt.title('Site1 load and pv - planning period 0')
line1, = ax1.plot(hrs, test_load, color=colors[0])
line2, = ax1.plot(hrs, test_pv, color=colors[1])
line3, = ax1.plot(hrs, optimiser.values(cp1.port_name, 0), color=colors[2])
ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
ax1.legend([line1, line2, line3], ['Load', 'PV', 'Connection Point'], ncol=3)

ax2 = fig.add_subplot(2, 2, 2)
plt.title('Site1 expansion decisions - planning period 0')
o = optimiser.get_expansions_off_node(site1)
line1, = ax2.plot(hrs, optimiser.values(o[0].port_name, 0), color=colors[0])
line2, = ax2.plot(hrs, optimiser.values(o[0].storage_soc_value, 0), color=colors[1])
ax2.set_xlim([0, len(test_load) / 4])
ax2.set_xlabel('hour')
ax2.legend([line1, line2], ['EXP 0 action (kW)', 'EXP 0 SOC (kWh)'])

ax1 = fig.add_subplot(2, 2, 3)
plt.title('Site1 load and pv - planning period 1')
line1, = ax1.plot(hrs, test_load, color=colors[0])
line2, = ax1.plot(hrs, test_pv, color=colors[1])
line3, = ax1.plot(hrs, optimiser.values(cp1.port_name, 1), color=colors[2])
ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
ax1.legend([line1, line2, line3], ['Load', 'PV', 'Connection Point'], ncol=3)

ax2 = fig.add_subplot(2, 2, 4)
plt.title('Site1 expansion decisions - planning period 0')
line1, = ax2.plot(hrs, optimiser.values(o[0].port_name, 1), color=colors[0])
line2, = ax2.plot(hrs, optimiser.values(o[0].storage_soc_value, 1), color=colors[1])
ax2.set_xlim([0, len(test_load) / 4])
ax2.set_xlabel('hour')
ax2.legend([line1, line2], ['EXP 0 action (kW)', 'EXP 0 SOC (kWh)'])

############################ ----------------------- ########################################

# Site 2
fig = plt.figure(figsize=(14, 7))
ax1 = fig.add_subplot(2, 2, 1)
plt.title('Site2 load and pv - planning period 0')
line1, = ax1.plot(hrs, test_load*site2_load_scale, color=colors[0])
line2, = ax1.plot(hrs, test_pv*site2_pv_scale, color=colors[1])
line3, = ax1.plot(hrs, optimiser.values(cp2.port_name, 0), color=colors[2])
ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
ax1.legend([line1, line2, line3], ['Load', 'PV', 'Connection Point'], ncol=3)

ax2 = fig.add_subplot(2, 2, 2)
plt.title('Site2 expansion decisions - planning period 0')
o = optimiser.get_expansions_off_node(site2)
line1, = ax2.plot(hrs, optimiser.values(o[0].port_name, 0), color=colors[0])
line2, = ax2.plot(hrs, optimiser.values(o[0].storage_soc_value, 0), color=colors[1])
ax2.set_xlim([0, len(test_load) / 4])
ax2.set_xlabel('hour')
ax2.legend([line1, line2], ['EXP 0 action (kW)', 'EXP 0 SOC (kWh)'])

ax1 = fig.add_subplot(2, 2, 3)
plt.title('Site2 load and pv - planning period 1')
line1, = ax1.plot(hrs, test_load*site2_load_scale, color=colors[0])
line2, = ax1.plot(hrs, test_pv*site2_pv_scale, color=colors[1])
line3, = ax1.plot(hrs, optimiser.values(cp2.port_name, 1), color=colors[2])
ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
ax1.legend([line1, line2, line3], ['Load', 'PV', 'Connection Point'], ncol=3)

ax2 = fig.add_subplot(2, 2, 4)
plt.title('Site2 expansion decisions - planning period 1')
line1, = ax2.plot(hrs, optimiser.values(o[0].port_name, 1), color=colors[0])
line2, = ax2.plot(hrs, optimiser.values(o[0].storage_soc_value, 1), color=colors[1])
ax2.set_xlim([0, len(test_load) / 4])
ax2.set_xlabel('hour')
ax2.legend([line1, line2], ['EXP 0 action (kW)', 'EXP 0 SOC (kWh)'])

############################ ----------------------- ########################################

# PCC

fig = plt.figure(figsize=(14, 7))
ax1 = fig.add_subplot(2, 2, 1)
plt.title('PCC load - planning period 0')
line1, = ax1.plot(hrs, optimiser.values(pcc.ports['grid'].port_name, 0), color=colors[0])
ax1.set_xlabel('hour'), ax1.set_ylabel('kW')

ax2 = fig.add_subplot(2, 2, 2)
plt.title('PCC expansion decisions - planning period 0')
o = optimiser.get_expansions_off_node(pcc)
line1, = ax2.plot(hrs, optimiser.values(o[0].port_name, 0), color=colors[0])
line2, = ax2.plot(hrs, optimiser.values(o[0].storage_soc_value, 0), color=colors[1])
ax2.set_xlim([0, len(test_load) / 4])
ax2.set_xlabel('hour')
ax2.legend([line1, line2], ['EXP 0 action (kW)', 'EXP 0 SOC (kWh)'])

ax1 = fig.add_subplot(2, 2, 3)
plt.title('PCC load - planning period 1')
line1, = ax1.plot(hrs, optimiser.values(pcc.ports['grid'].port_name, 1), color=colors[0])
ax1.set_xlabel('hour'), ax1.set_ylabel('kW')

ax2 = fig.add_subplot(2, 2, 4)
plt.title('PCC expansion decisions - planning period 1')
o = optimiser.get_expansions_off_node(pcc)
line1, = ax2.plot(hrs, optimiser.values(o[0].port_name, 1), color=colors[0])
line2, = ax2.plot(hrs, optimiser.values(o[0].storage_soc_value, 1), color=colors[1])
ax2.set_xlim([0, len(test_load) / 4])
ax2.set_xlabel('hour')
ax2.legend([line1, line2], ['EXP 0 action (kW)', 'EXP 0 SOC (kWh)'])

plt.figure()
options = {"edgecolors": "tab:gray", "node_size": 800, "alpha": 0.9}
pos = nx.spring_layout(ES)
nx.draw_networkx_nodes(ES, pos)
nx.draw_networkx_nodes(ES, pos, nodelist=list(ES.storage_expansion_obj.values()), node_color="tab:red", **options)
nx.draw_networkx_nodes(ES, pos, nodelist=list(ES.gen_expansion_obj.values()), node_color="tab:orange", **options)
nx.draw_networkx_edges(ES, pos)
plt.title('Network layout')
