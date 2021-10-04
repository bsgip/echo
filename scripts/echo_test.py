from __future__ import division

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pyomo.core import Var
from pyomo.util.infeasible import log_infeasible_constraints


# Since using the data-driven data for the testing, use their battery class
import sys
sys.path.append("../")
from old_models import EnergyStorage, EnergySystem, Demand, Generation, Tariff, DispatchRequest, LocalTariff
from echo_models import ElectricalDemand, ElectricalGeneration, ElectricalStorage, ElectricalHub, BulkElectricalGrid, OptimisationGraph, FlexibleAsset
from old_optimiser import EnergyOptimiser, OptimiserObjectiveSet, BTMEnergyOptimiser, LocalEnergyOptimiser
from echo_optimiser import EchoOptimiser
from networkx import Graph

# set up seaborn the way you like
sns.set_style({'axes.linewidth': 1, 'axes.edgecolor': 'black', 'xtick.direction': \
    'out', 'xtick.major.size': 4.0, 'ytick.direction': 'out', 'ytick.major.size': 4.0, \
               'axes.facecolor': 'white', 'grid.color': '.8', 'grid.linestyle': u'-', 'grid.linewidth': 0.5})

############################ Define an Example Optimisation Problem ########################################

battery = ElectricalStorage(max_capacity=15.0,
                        depth_of_discharge_limit=0,
                        charging_power_limit=5.0,
                        discharging_power_limit=-5.0,
                        charging_efficiency=1,
                        discharging_efficiency=1,
                        throughput_cost=0.018,
                        initial_state_of_charge=0.0)

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

net_load = test_load + test_pv
# split load into import and export
connection_point_import = np.copy(net_load)
connection_point_export = np.copy(net_load)
for j, e in enumerate(net_load):
    if e >= 0:
        connection_point_export[j] = 0
    else:
        connection_point_import[j] = 0

import_load_dct = dict(enumerate(connection_point_import))
export_load_dct = dict(enumerate(connection_point_export))

# Tariffs are in $ / kwh
import_tariff = np.array(([0.1] * 28 + [0.3] * 8 + [0.2] * 32 + [0.3] * 16 + [0.1] * 12))
export_tariff = np.array(([0.0] * 96))
export_tariff_dct = dict(enumerate(export_tariff))
import_tariff_dct = dict(enumerate(import_tariff))



colors = sns.color_palette()
hrs = np.arange(0, len(test_load)) / 4
fig = plt.figure(figsize=(14, 4))
ax1 = fig.add_subplot(2, 1, 1)
l1, = ax1.plot(hrs, 4 * test_load, color=colors[0])
l2, = ax1.plot(hrs, 4 * test_pv, color=colors[1])
l3, = ax1.plot(hrs, 4 * net_load, color=colors[2])
ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
ax1.legend([l1, l2, l3], ['Load', 'PV', 'Connection Point'], ncol=2)
ax1.set_xlim([0, len(test_load) / 4])
ax2 = fig.add_subplot(2, 1, 2)
l1, = ax2.plot(hrs, import_tariff, color=colors[3])
l2, = ax2.plot(hrs, export_tariff, color=colors[4])
ax2.set_xlabel('hour'), ax2.set_ylabel('price ($/kWh)')
ax2.legend([l1, l2], ['buy price', 'sell price'], ncol=2)
ax2.set_xlim([0, len(test_load) / 4])
fig.tight_layout()

fig.show()

############################ Optimise this Example ########################################

energy_system = EnergySystem()
energy_system.add_energy_storage(battery)
load = ElectricalDemand()
load.add_demand_profile(dict(enumerate(connection_point_import)))
pv = ElectricalGeneration()
pv.add_generation_profile(dict(enumerate(connection_point_export)))
tariff = Tariff()
tariff.add_tariff_profile_export(export_tariff_dct)
tariff.add_tariff_profile_import(import_tariff_dct)
energy_system.add_demand(load)
energy_system.add_generation(pv)
energy_system.add_tariff(tariff)

grid = BulkElectricalGrid()

connection_point = FlexibleAsset()
connection_point.has_tariff = True
connection_point.tariff = tariff

dyn1 = FlexibleAsset()
dyn2 = FlexibleAsset()
dyn3 = FlexibleAsset()

ES = OptimisationGraph()
elec_hub = ElectricalHub()
elec_hub.named_nodes.append('connection_point')
elec_hub.nodes['connection_point'] = connection_point

elec_hub.nodes['dyn1'] = dyn1
elec_hub.nodes['dyn2'] = dyn2
elec_hub.nodes['dyn3'] = dyn3

ES.add_asset(connection_point)
ES.add_asset(dyn1)
ES.add_asset(dyn2)
ES.add_asset(dyn3)
ES.add_asset(load)
ES.add_asset(pv)
ES.add_asset(battery)
ES.add_asset(grid)
ES.add_hub(elec_hub)
ES.connect_asset_to_hub(connection_point, grid)  #, e_h_g)
ES.connect_asset_to_hub(dyn1, battery)  #, e_h_b)
ES.connect_asset_to_hub(dyn2, pv)  #, e_h_s)
ES.connect_asset_to_hub(dyn3, load)  #, e_h_d)


# Dispatch capabilities will be added in a future version
'''dispatch = DispatchRequest()
req = [[4, 7, 12], [(0, 5000), (0, 15000), (0, 28000)]]
req = [[4], [(0, 15000)]]
dispatch.add_dispatch_request_linear_ramp(req)
energy_system.add_dispatch(dispatch)'''

# Invoke the optimiser and optimise
optimiser = EchoOptimiser(15, 96, energy_system, OptimiserObjectiveSet.EnergyOptimisation, ES)

log_infeasible_constraints(optimiser.model)


############################ Analyse the Optimisation ########################################
# storage_energy_delta = optimiser.values('storage_charge_grid') +\
#                        optimiser.values('storage_charge_generation') +\
#                        optimiser.values('storage_discharge_demand') +\
#                        optimiser.values('storage_discharge_grid')

storage_energy_delta = optimiser.values(battery.node_name)

optimised_connection_point_load = optimiser.values('negative_' + optimiser.c.node_name) + optimiser.values('positive_' + optimiser.c.node_name)

aa = optimiser.values(battery.node_name)
bb = optimiser.value_test()

cc = optimiser.values('negative_' + optimiser.c.node_name)
dd = optimiser.values('positive_' + optimiser.c.node_name)
ee = 1
# a = optimiser.values('cgen')
# b = optimiser.system_generation_dct.values()
# c = zip(list(a), list(b))
#
# print(list(c))


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
l1, = ax3.plot(hrs, storage_energy_delta * 4, color=colors[5])
l2, = ax3.plot(hrs, optimiser.values('storage_soc_' + battery.node_name), color=colors[4])

l3, = ax3.plot(hrs, storage_energy_delta * 4, color=colors[5])
l4, = ax3.plot(hrs, optimiser.values('storage_soc_' + battery.node_name), color=colors[4])

ax3.set_xlabel('hour'), ax3.set_ylabel('action')
ax3.legend([l1, l2, l3, l4], ['battery action (kW)', 'SOC (kWh)', 'B2 kw', 'b2 soc'], ncol=2)
ax3.set_xlim([0, len(test_load) / 4])
fig.tight_layout()
plt.show()