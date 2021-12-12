from __future__ import division

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pyomo.core import Var
from pyomo.util.infeasible import log_infeasible_constraints

import sys

sys.path.append("../")
from echo_models import ElectricalDemand, ElectricalGeneration, ElectricalStorage, ElectricalHub, BulkElectricalGrid, \
    OptimisationGraph, FlexibleAsset, Tariff, Hub, Port, Edge, Transform
from echo_optimiser import EchoOptimiser
from configuration import HubNodeRule, TransformationRule, FlowConstraint
from networkx import Graph, draw

# set up seaborn the way you like
sns.set_style({'axes.linewidth': 1, 'axes.edgecolor': 'black', 'xtick.direction': \
    'out', 'xtick.major.size': 4.0, 'ytick.direction': 'out', 'ytick.major.size': 4.0, \
               'axes.facecolor': 'white', 'grid.color': '.8', 'grid.linestyle': u'-', 'grid.linewidth': 0.5})

############################ Define an Example Optimisation Problem ########################################

# Example problem - 2 separate hubs (loads/sites) supplied from a single supply point that is connected to the grid.
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

# Site 2
net_load2 = test_load + test_pv
# split load into import and export
connection_point_import2 = np.copy(net_load2)
connection_point_export2 = np.copy(net_load2)
for j, e in enumerate(net_load2):
    if e >= 0:
        connection_point_export2[j] = 0
    else:
        connection_point_import2[j] = 0

# Tariffs are in $ / kwh
import_tariff = np.array(([0.1] * 28 + [0.3] * 8 + [0.2] * 32 + [0.3] * 16 + [0.1] * 12))
export_tariff = np.array(([0.0] * 96))

############################ Optimise this Example ########################################

np.set_printoptions(suppress=True)

#### Modelling parameters ####
expansion_periods = 1  # Number of expansion time periods
storage_expansions_per_period = 0  # limit on storage expansions per time period

# Setup load, pv, and tariffs as dictionaries
# For now, each expansion period has identical load, pv, tariffs
d1 = {}
gen1 = {}
d2 = {}
gen2 = {}
it = {}
et = {}

for ep in range(0,expansion_periods):
    for i, x in enumerate(connection_point_import):
        d1[(ep, i)] = x
    for i, x in enumerate(connection_point_export):
        gen1[(ep, i)] = x
    for i, x in enumerate(connection_point_import2):
        d2[(ep, i)] = x
    for i, x in enumerate(connection_point_export2):
        gen2[(ep, i)] = x
    for i, x in enumerate(import_tariff):
        it[(ep, i)] = x
    for i, x in enumerate(export_tariff):
        et[(ep, i)] = x


# Setup graph
ES = OptimisationGraph()
ES.global_storage_exp_con = storage_expansions_per_period  #ToDo - better way to carry these parameters
ES.expansion_periods = expansion_periods

tariff = Tariff()
tariff.add_tariff_profile_export(et)
tariff.add_tariff_profile_import(it)

grid = Hub()
emissions = Port()
grid.nodes['grid'] = Port()
grid.nodes['CO2'] = emissions
gt = Transform()
gt.add_rhs(0)
gt.add_lhs(grid.nodes['CO2'], 1, TransformationRule.Both)
gt.add_lhs(grid.nodes['grid'], 0.5, TransformationRule.NegativeComponent)
grid.add_transformation(gt)
grid.hub_rule = HubNodeRule.Transform
ES.add_hub(grid)


#### Site 1
battery1 = Hub()
b1 = ElectricalStorage(max_capacity=15.0,
                       depth_of_discharge_limit=0,
                       charging_power_limit=5.0,
                       discharging_power_limit=-5.0,
                       charging_efficiency=1,
                       discharging_efficiency=1,
                       throughput_cost=0.018,
                       initial_state_of_charge=0.0)
b1.existing_port = True
battery1.nodes['battery_asset'] = b1

load1 = Hub()
l1 = ElectricalDemand()
l1.add_demand_profile(d1)
load1.nodes['demand'] = l1

solar1 = Hub()
pv1 = ElectricalGeneration()
pv1.add_generation_profile(gen1)
solar1.nodes['solar'] = pv1

site1 = ElectricalHub()
cp1 = Port()
cp1.has_tariff = True
cp1.tariff = tariff

site1.nodes['CP'] = cp1
site1.nodes['loadCP'] = Port()
site1.nodes['bessCP'] = Port()
site1.nodes['pvCP'] = Port()
site1.hub_rule = HubNodeRule.Tellegen

ES.add_hub(battery1)
ES.add_hub(load1)
ES.add_hub(site1)
ES.add_hub(solar1)

# Create edge objects
bess_edge1 = Edge()
bess_edge1.add_vertices(site1.nodes['bessCP'], b1)
load_edge1 = Edge()
load_edge1.add_vertices(site1.nodes['loadCP'], l1)
pv_edge1 = Edge()
pv_edge1.add_vertices(site1.nodes['pvCP'], pv1)

ES.add_edge_obj(bess_edge1)
ES.add_edge_obj(load_edge1)
ES.add_edge_obj(pv_edge1)

#### Site 2
battery2 = Hub()
b2 = ElectricalStorage(max_capacity=15.0,
                       depth_of_discharge_limit=0,
                       charging_power_limit=5.0,
                       discharging_power_limit=-5.0,
                       charging_efficiency=1,
                       discharging_efficiency=1,
                       throughput_cost=0.018,
                       initial_state_of_charge=0.0)
b2.existing_port = True
battery2.nodes['battery_asset'] = b2

load2 = Hub()
l2 = ElectricalDemand()
l2.add_demand_profile(d2)
load2.nodes['demand'] = l2

solar2 = Hub()
pv2 = ElectricalGeneration()
pv2.add_generation_profile(gen2)
solar2.nodes['solar'] = pv2

site2 = ElectricalHub()
cp2 = Port()
cp2.has_tariff = True
cp2.tariff = tariff

site2.nodes['CP'] = cp2
site2.nodes['loadCP'] = Port()
site2.nodes['bessCP'] = Port()
site2.nodes['pvCP'] = Port()
site2.hub_rule = HubNodeRule.Tellegen

ES.add_hub(load2)
ES.add_hub(battery2)
ES.add_hub(site2)
ES.add_hub(solar2)

# Create edge objects
bess_edge2 = Edge()
bess_edge2.add_vertices(site2.nodes['bessCP'], b2)
load_edge2 = Edge()
load_edge2.add_vertices(site2.nodes['loadCP'], l2)
pv_edge2 = Edge()
pv_edge2.add_vertices(site2.nodes['pvCP'], pv2)


# Add edge objects to ES - this creates an actual networkx edge
ES.add_edge_obj(bess_edge2)
ES.add_edge_obj(load_edge2)
ES.add_edge_obj(pv_edge2)

# Create intermediate hub
pcc = Hub()
pcc.nodes['site1'] = Port()
pcc.nodes['site2'] = Port()
pcc.nodes['grid'] = Port()
pcc.hub_rule = HubNodeRule.Tellegen
ES.add_hub(pcc)

site1_edge = Edge()
site1_edge.add_vertices(site1.nodes['CP'], pcc.nodes['site1'])
site2_edge = Edge()
site2_edge.add_vertices(site2.nodes['CP'], pcc.nodes['site2'])
grid_edge = Edge()
grid_edge.add_vertices(pcc.nodes['grid'], grid.nodes['grid'])



# Add edge objects to ES - this creates an actual networkx edge
ES.add_edge_obj(site1_edge)
ES.add_edge_obj(site2_edge)
ES.add_edge_obj(grid_edge)


ES.add_expansions(expansion_periods)

############## Testing settings ##################

# emissions.has_tariff = True
# emissions.tariff = tariff
# b1.max_capacity = 100
# b1.fixed_capacity = False
# b2.max_capacity = 100
# b2.fixed_capacity = False
#site1_edge.initial_edge_capacity = 2
#site1_edge.expansion_planning = True
#site1.expansion_planning = True
#site2.expansion_planning = True
#bess_edge1.initial_edge_capacity = 3
# bess_edge1.initial_edge_capacity = 1
# bess_edge1.expansion_planning = False



############################ ----------------------- ########################################

# Dispatch capabilities will be added in a future version
'''dispatch = DispatchRequest()
req = [[4, 7, 12], [(0, 5000), (0, 15000), (0, 28000)]]
req = [[4], [(0, 15000)]]
dispatch.add_dispatch_request_linear_ramp(req)
energy_system.add_dispatch(dispatch)'''

# Invoke the optimiser and optimise
optimiser = EchoOptimiser(15, 96, expansion_periods, ES)

log_infeasible_constraints(optimiser.model)

############################ Analyse the Optimisation ########################################

storage_energy_delta = optimiser.values(b1.node_name, 0)
storage_energy_delta2 = optimiser.values(b2.node_name, 0)
optimised_connection_point_load = optimiser.values(cp1.node_name, 0)
#
# colors = sns.color_palette()
# hrs = np.arange(0, len(test_load)) / 4
# fig = plt.figure(figsize=(14, 7))
# ax1 = fig.add_subplot(2, 1, 1)
# line1, = ax1.plot(hrs, 4 * test_load, color=colors[0])
# line2, = ax1.plot(hrs, 4 * test_pv, color=colors[1])
# line3, = ax1.plot(hrs, 4 * optimised_connection_point_load, color=colors[2])
# line4, = ax1.plot(hrs, 4 * storage_energy_delta, color=colors[3])
# ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
# ax1.legend([line1, line2, line3, line4], ['Load', 'PV', 'Connection Point', 'Storage'], ncol=3)
# ax1.set_xlim([0, len(test_load) / 4])
#
# ax2 = fig.add_subplot(2, 1, 2)
# line1, = ax2.plot(hrs, import_tariff, color=colors[3])
# line2, = ax2.plot(hrs, export_tariff, color=colors[4])
# ax2.set_xlabel('hour'), ax2.set_ylabel('price')
# ax2.legend([line1, line2], ['buy price', 'sell price'], ncol=2)
# ax2.set_xlim([0, len(test_load) / 4])
#
# i = 0
# fig = plt.figure(figsize=(14, 7))
# ax3 = fig.add_subplot(4, 1, 1)
# line1, = ax3.plot(hrs, optimiser.values(b1.node_name, i) * 4, color=colors[1])
# line2, = ax3.plot(hrs, optimiser.values('storage_soc_' + b1.node_name, i), color=colors[2])
# ax3.set_xlim([0, len(test_load) / 4])
# ax3.set_xlabel('hour'), ax3.set_ylabel('B1 action')
# ax3.legend([line1, line2], ['Charging action (kW)', 'SOC (kWh)'])
#
# ax4 = fig.add_subplot(4, 1, 2)
# line3, = ax4.plot(hrs, optimiser.values(b2.node_name, i) * 4, color=colors[3])
# line4, = ax4.plot(hrs, optimiser.values('storage_soc_' + b2.node_name, i), color=colors[4])
# ax4.set_xlim([0, len(test_load) / 4])
# ax4.set_xlabel('hour'), ax4.set_ylabel('B2 action')
# ax4.legend([line3, line4], ['Charging action (kW)', 'SOC (kWh)'])
#
#
#
