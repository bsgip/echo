from __future__ import division

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pyomo.core import Var
from pyomo.util.infeasible import log_infeasible_constraints


import sys
sys.path.append("../")
from echo_models import ElectricalDemand, ElectricalGeneration, ElectricalStorage, ElectricalHub, BulkElectricalGrid, OptimisationGraph, FlexibleAsset, Tariff
from echo_optimiser import EchoOptimiser
from configuration import HubNodeRule
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
test_load = np.array([2.13, 2.09, 2.3, 2.11, 2.2, 2.23, 2.2, 2.15, 2.02, 2.19, 2.19, 2.19, 2.12, 2.15, 2.25, 2.12, 2.21, 2.16,
                      2.26, 2.13, 2.08, 2.15, 2.42, 2.02, 2.3, 2.26, 2.35, 2.55, 3.23, 2.98, 3.49, 3.5, 3.12, 3.52, 3.94, 3.55,
                      3.99, 3.71, 3.38, 3.76, 3.71, 3.78, 3.29, 3.65, 3.61, 3.75, 3.38, 3.66, 3.56, 3.69, 3.3, 3.61, 3.71, 3.82,
                      3.17, 3.69, 3.74, 3.86, 3.57, 3.55, 3.75, 3.6, 3.67, 3.48, 3.51, 3.46, 3.19, 3.38, 3.19, 3.38, 3.04, 3.12,
                      2.91, 3.11, 3.13, 2.77, 2.24, 2.54, 2.24, 2.24, 2.09, 2.33, 2.17, 2.16, 1.97, 2.16, 2.21, 2.18, 2.01, 2.16,
                      2.19, 2.11, 2.17, 2.13, 2.05, 2.19])

test_pv = 2*np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.23, 0.52,
                    0.74, 0.71, 0.63, 0.68, 0.97, 0.01, 0.52, 0.83, 0.83, 0.79, 1.22, 1.36, 1.27, 1.42, 1.97, 2.56, 2.91, 3.24,
                    3.8, 4.3, 4.62, 4.84, 4.6, 4.17, 3.77, 3.76, 3.38, 2.64, 1.96, 1.76, 1.85, 2.4, 3.82, 5.13, 4.97, 5.02, 5.43,
                    5.32, 3.56, 1.75, 1.43, 1.65, 1.69, 2.3, 2.71, 2.41, 2.63, 2.6, 1.9, 0.78, 0.13, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
test_pv *= -1 #convert solar generation to negative to match convention.

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

import_load1_dct = dict(enumerate(connection_point_import))
export_load1_dct = dict(enumerate(connection_point_export))

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
export_tariff_dct = dict(enumerate(export_tariff))
import_tariff_dct = dict(enumerate(import_tariff))

# # Plot data
# colors = sns.color_palette()
# hrs = np.arange(0, len(test_load)) / 4
# fig = plt.figure(figsize=(14, 4))
# ax1 = fig.add_subplot(2, 1, 1)
# l1, = ax1.plot(hrs, 4 * net_load, color=colors[0])
# l2, = ax1.plot(hrs, 4 * net_load2, color=colors[1])
# ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
# ax1.legend([l1, l2], ['Connection Point 1', 'Connection Point 2'], ncol=2)
# ax1.set_xlim([0, len(net_load) / 4])
# ax2 = fig.add_subplot(2, 1, 2)
# l1, = ax2.plot(hrs, import_tariff, color=colors[3])
# l2, = ax2.plot(hrs, export_tariff, color=colors[4])
# ax2.set_xlabel('hour'), ax2.set_ylabel('price ($/kWh)')
# ax2.legend([l1, l2], ['buy price', 'sell price'], ncol=2)
# ax2.set_xlim([0, len(test_load) / 4])
# fig.tight_layout()
#
# fig.show()

############################ Optimise this Example ########################################

# Setup graph
ES = OptimisationGraph()

# Setup general elements
grid = BulkElectricalGrid()
ES.add_asset(grid)
tariff = Tariff()
tariff.add_tariff_profile_export(export_tariff_dct)
tariff.add_tariff_profile_import(import_tariff_dct)

# Setup Site 1
battery = ElectricalStorage(max_capacity=15.0,
                            depth_of_discharge_limit=0,
                            charging_power_limit=5.0,
                            discharging_power_limit=-5.0,
                            charging_efficiency=1,
                            discharging_efficiency=1,
                            throughput_cost=0.018,
                            initial_state_of_charge=0.0)

load = ElectricalDemand()
load.add_demand_profile(dict(enumerate(connection_point_import)))
pv = ElectricalGeneration()
pv.add_generation_profile(dict(enumerate(connection_point_export)))

connection_point = FlexibleAsset()
connection_point.has_tariff = True
connection_point.tariff = tariff

elec_hub1 = ElectricalHub()
elec_hub1.hub_rule = HubNodeRule.Tellegen
elec_hub1.add_named_node('dyn1')
elec_hub1.add_named_node('dyn2')
elec_hub1.add_named_node('dyn3')
elec_hub1.nodes['connection_point'] = connection_point

ES.add_asset([load, battery, pv])
ES.add_hub(elec_hub1)

# Setup supply point hub
supply_hub = ElectricalHub()
supply_hub.hub_rule = HubNodeRule.Tellegen
supply_hub.add_named_node('dyn4')
supply_hub.add_named_node('dyn5')
supply_hub.add_named_node('dyn6')

ES.add_hub(supply_hub)

# Setup site 2
battery2 = ElectricalStorage(max_capacity=15.0,
                            depth_of_discharge_limit=0,
                            charging_power_limit=5.0,
                            discharging_power_limit=-5.0,
                            charging_efficiency=1,
                            discharging_efficiency=1,
                            throughput_cost=0.018,
                            initial_state_of_charge=0.0)


connection_point2 = FlexibleAsset()
connection_point2.has_tariff = True
connection_point2.tariff = tariff
pv2 = ElectricalGeneration()
pv2.add_generation_profile(dict(enumerate(connection_point_export2)))

elec_hub2 = ElectricalHub()
elec_hub2.hub_rule = HubNodeRule.Tellegen
elec_hub2.add_named_node('dyn7')
elec_hub2.add_named_node('dyn8')
elec_hub2.add_named_node('dyn9')
elec_hub2.nodes['connection_point2'] = connection_point2

load2 = ElectricalDemand()
load2.add_demand_profile(dict(enumerate(connection_point_import2)))

ES.add_asset([connection_point2, load2, pv2, battery2])
ES.add_hub(elec_hub2)

# Do hub-asset connections
ES.connect_asset_to_hub(elec_hub1, 'dyn1', battery)  # Site 1: hub, port name, asset
ES.connect_asset_to_hub(elec_hub1, 'dyn2', load)  # Site 1
ES.connect_asset_to_hub(elec_hub1, 'dyn3', pv)  # Site 1
ES.connect_asset_to_hub(elec_hub1, 'connection_point', supply_hub.nodes['dyn4'])  # Site 1 to supply hub
ES.connect_asset_to_hub(supply_hub, 'dyn5', grid)  # Supply hub to grid
ES.connect_asset_to_hub(elec_hub2, 'dyn7', battery2)  # Site 2
ES.connect_asset_to_hub(elec_hub2, 'dyn8', load2)  # Site 2
ES.connect_asset_to_hub(elec_hub2, 'dyn9', pv2)  # Site 2
ES.connect_asset_to_hub(elec_hub2, 'connection_point2', supply_hub.nodes['dyn6'])  # Site 2 to supply hub

# Do connections of 0 capacity battery assets
blank1 = ElectricalStorage(max_capacity=100.0,
                            depth_of_discharge_limit=0,
                            charging_power_limit=5.0,
                            discharging_power_limit=-5.0,
                            charging_efficiency=1,
                            discharging_efficiency=1,
                            throughput_cost=0.018,
                            initial_state_of_charge=0.0)

blank2 = ElectricalStorage(max_capacity=0.0,
                            depth_of_discharge_limit=0,
                            charging_power_limit=5.0,
                            discharging_power_limit=-5.0,
                            charging_efficiency=1,
                            discharging_efficiency=1,
                            throughput_cost=0.018,
                            initial_state_of_charge=0.0)


# To connect blank assets to hubs
b1 = FlexibleAsset()
b2 = FlexibleAsset()

ES.add_asset(blank1)
ES.add_asset(blank2)
ES.add_asset(b1)
ES.add_asset(b2)

elec_hub1.nodes['b1'] = b1
elec_hub2.nodes['b2'] = b2

# # Do connections
ES.connect_asset_to_hub(elec_hub1, 'b1', blank1)
ES.connect_asset_to_hub(elec_hub2, 'b2', blank2)

#Other settings

battery.capex = 0.05
battery2.capex = 0.05
blank1.capex = 0.01
blank2.capex = 0



# Dispatch capabilities will be added in a future version
'''dispatch = DispatchRequest()
req = [[4, 7, 12], [(0, 5000), (0, 15000), (0, 28000)]]
req = [[4], [(0, 15000)]]
dispatch.add_dispatch_request_linear_ramp(req)
energy_system.add_dispatch(dispatch)'''

# Invoke the optimiser and optimise
optimiser = EchoOptimiser(15, 96, ES)

log_infeasible_constraints(optimiser.model)

############################ Analyse the Optimisation ########################################

print('B1 capacity =', optimiser.values(battery.max_cap_value))
print('B2 capacity =', optimiser.values(battery2.max_cap_value))
print('blank1 capacity =', optimiser.values(blank1.max_cap_value))


storage_energy_delta = optimiser.values(battery.node_name)
storage_energy_delta2 = optimiser.values(battery2.node_name)
optimised_connection_point_load = optimiser.values(connection_point.node_name)



colors = sns.color_palette()
hrs = np.arange(0, len(test_load)) / 4
fig = plt.figure(figsize=(14, 7))
ax1 = fig.add_subplot(3, 1, 1)
l1, = ax1.plot(hrs, 4 * test_load, color=colors[0])
l2, = ax1.plot(hrs, 4 * test_pv, color=colors[1])
l3, = ax1.plot(hrs, 4 * optimised_connection_point_load, color=colors[2])
l4, = ax1.plot(hrs, 4 * storage_energy_delta, color=colors[3])
ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
ax1.legend([l1, l2, l3, l4], ['Load', 'PV', 'Connection Point', 'Storage'], ncol=3)
ax1.set_xlim([0, len(test_load) / 4])

ax2 = fig.add_subplot(3, 1, 2)
l1, = ax2.plot(hrs, import_tariff, color=colors[3])
l2, = ax2.plot(hrs, export_tariff, color=colors[4])
ax2.set_xlabel('hour'), ax2.set_ylabel('price')
ax2.legend([l1, l2], ['buy price', 'sell price'], ncol=2)
ax2.set_xlim([0, len(test_load) / 4])

ax3 = fig.add_subplot(3, 1, 3)
l1, = ax3.plot(hrs, storage_energy_delta * 4, color=colors[1])
l2, = ax3.plot(hrs, optimiser.values('storage_soc_' + battery.node_name), color=colors[2])
l3, = ax3.plot(hrs, storage_energy_delta2 * 4, color=colors[3])
l4, = ax3.plot(hrs, optimiser.values('storage_soc_' + battery2.node_name), color=colors[4])
l5, = ax3.plot(hrs, optimiser.values(blank1.node_name) * 4, color=colors[5])
l6, = ax3.plot(hrs, optimiser.values('storage_soc_' + blank1.node_name), color=colors[6])
l7, = ax3.plot(hrs, optimiser.values(blank2.node_name) * 4, color=colors[7])
l8, = ax3.plot(hrs, optimiser.values('storage_soc_' + blank2.node_name), color=colors[8])

ax3.set_xlabel('hour'), ax3.set_ylabel('action')
ax3.legend([l1, l2, l3, l4, l5, l6, l7, l8], ['B1 kW', 'B1 SOC', 'B2 kW', 'B2 SOC', 'Blank1 kW', 'Blank1 SOC', 'Blank2 kW', 'Blank2 SOC'], ncol=2)
ax3.set_xlim([0, len(test_load) / 4])

#fig2 = plt.figure(figsize=(14, 7))


fig.tight_layout()

plt.show()

