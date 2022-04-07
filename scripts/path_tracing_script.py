import numpy as np
from echo.echo_models import *
from echo.echo_optimiser import EchoOptimiser
from echo.configuration import *
from echo.objectives import *

import os

SOLVER = os.environ.get('OPTIMISER_ENGINE', 'cplex')
SOLVER_EXECUTABLE = None


# expansion_periods = 1
# time_periods = 48
# interval_duration = 30  # min
#
# system = OptimisationGraph()
#
# grid = Node()
# grid.add_named_electrical_ports(['grid'])
#
# battery = Node()
# b1 = ElectricalStorage(max_capacity=48,
#                        depth_of_discharge_limit=0,
#                        charging_power_limit=5.0,
#                        discharging_power_limit=-5.0,
#                        charging_efficiency=1,
#                        discharging_efficiency=1,
#                        initial_state_of_charge=48.0)
# battery.ports['battery_asset'] = b1
#
# solar = Node()
# pv1 = ElectricalGeneration()
# pv1.add_generation_profile_from_array([-4] * time_periods, expansion_periods)
# pv1.curtailable = False
# solar.ports['solar'] = pv1
#
# inverter = Inverter(max_import=5, max_export=-5, dc_ac_efficiency=1, ac_dc_efficiency=1)
# inverter.add_ac_port('cp')
# inverter.add_dc_port('bess')
# inverter.add_dc_port('pv')
#
# cp = ElectricalTellegenNode()
# cp.add_named_electrical_ports(['load', 'inv', 'grid'])
#
# load = Node()
# l1 = ElectricalDemand()
# l1.add_demand_profile_from_array([6]*time_periods, expansion_periods)
# load.ports['load'] = l1
#
# system.add_node_obj([grid, cp, load, battery, solar, inverter])
#
# system.connect_ports_and_create_edge(inverter.ports['bess'], b1)
# system.connect_ports_and_create_edge(inverter.ports['pv'], pv1)
# system.connect_ports_and_create_edge(cp.ports['load'], l1)
# system.connect_ports_and_create_edge(inverter.ports['cp'], cp.ports['inv'])
# system.connect_ports_and_create_edge(cp.ports['grid'], grid.ports['grid'])
#
# system.create_path_objects(sources=[grid, inverter], sinks=[grid, inverter, load])
#
# optimiser = EchoOptimiser(
#     interval_duration=interval_duration,
#     number_of_intervals=time_periods,
#     number_of_expansion_intervals=expansion_periods,
#     discount_rate=0,
#     ES=system,
#     objective_set=None
# )
#
# optimiser.optimise(tee=True)
#
#
# for v, p in system.paths.items():
#     print(v)
#     print(optimiser.values(p.flow_value, 0))


expansion_periods = 1
time_periods = 48
interval_duration = 30
battery_power = 2
demand = [4] * time_periods

system = OptimisationGraph()

grid = Node()
grid.add_named_electrical_ports(['grid'])

battery = Node()
b1 = ElectricalStorage(max_capacity=1000,
                       depth_of_discharge_limit=0,
                       charging_power_limit=battery_power,
                       discharging_power_limit=-battery_power,
                       charging_efficiency=1,
                       discharging_efficiency=1,
                       initial_state_of_charge=0.0)
battery.ports['battery'] = b1

solar = Node()
pv1 = ElectricalGeneration()
pv1.add_generation_profile_from_array([-4] * time_periods, expansion_periods)
pv1.curtailable = False
solar.ports['solar'] = pv1

site = ElectricalNode()
site.add_named_electrical_ports(['cp', 'load', 'bess', 'pv'])
site.node_rule = NodeRule.Tellegen
cp1 = site.ports['cp']

load = Node()
l1 = ElectricalDemand()
l1.add_demand_profile_from_array([6] * time_periods, expansion_periods)
load.ports['demand'] = l1

bess_edge1 = Edge(vertices=[site.ports['bess'], b1])
load_edge1 = Edge(vertices=[site.ports['load'], l1])
pv_edge = Edge(vertices=[pv1, site.ports['pv']])
grid_edge = Edge(vertices=[cp1, grid.ports['grid']])

system.add_node_obj([grid, battery, site, solar, load])
system.add_edge_obj([bess_edge1, load_edge1, pv_edge, grid_edge])

system.create_path_objects(sources=[grid, site], sinks=[grid, site])

optimiser = EchoOptimiser(
    interval_duration=interval_duration,
    number_of_intervals=time_periods,
    number_of_expansion_intervals=expansion_periods,
    discount_rate=0,
    ES=system,
    objective_set=None
)

optimiser.optimise()
print(optimiser.opt_status)

for v, p in system.paths.items():
    print(v)
    print(optimiser.values(p.flow_value, 0))