from __future__ import division

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pyomo.util.infeasible import log_infeasible_constraints
import pprint


from echo.echo_models import *
from echo.echo_optimiser import EchoOptimiser
from echo.configuration import *
from echo.objectives import *
from networkx import Graph, draw

## Set up hyper params
time_periods = 48  # number of time periods to run the optimisation for
interval_duration = 30          # each time period is 15 mins long
expansion_periods = 1           # not yet implemented leave as 1
discount_rate = 0               # not yet implemented leave as 0

# Create graph
system = OptimisationGraph()

# Create assets
grid = Node()                                   # create node representing upstream grid
grid.add_electrical_ports_from_list(
    ['grid'])  # create a port which will be used to connect this with the connection_point

# create the connection point (where we will sum everything up)
connection_point = TellegenNode()
connection_point.add_electrical_ports_from_list(
    ['ev', 'grid', 'load'])  # create ports to connect to the grid, the load, and the inverter

# Create load

load = Node()
load.ports['load'] = ElectricalDemand()
demand = [5]*48
load.ports['load'].add_demand_profile_from_array(demand, expansion_periods=1)

# Create V0G vehicle

available = np.array([1] * 24 + [0] * 24)    # bool when at charger
usage = np.array([0.0]*24 + [2]*24)        # kw average during use

ev_cp = EV(charge_mode='V2G',
               available=available,
               usage=usage,
               connection_port_name='cp',
               max_capacity=40,
               depth_of_discharge_limit=0,
               charging_power_limit=10,
               discharging_power_limit=-1e4,
               charging_efficiency=1,
               discharging_efficiency=1,
               initial_state_of_charge=40,
               soc_conserv=None,
               soc_conserv_cost=0.,
               interval_duration=30.,
               tod_charging=False,
               trip_slack=True)


system.add_node_obj([grid, ev_cp, connection_point, load])

# Create edge objects and add to graph
system.connect_ports_and_create_edge(connection_point.ports['ev'], ev_cp.ports['cp'])
system.connect_ports_and_create_edge(connection_point.ports['load'], load.ports['load'])
system.connect_ports_and_create_edge(grid.ports['grid'], connection_point.ports['grid'])

tariff_array = [20]*12 + [15]*36
import_tariff = ImportTariff(component=connection_point.ports['grid'],
                          tariff_array=tariff_array)

obj = ObjectiveSet(objective_list=[import_tariff])

############################ ----------------------- ########################################

# Invoke the optimiser and optimise
optimiser = EchoOptimiser(interval_duration=interval_duration,
                          number_of_intervals=time_periods,
                          number_of_expansion_intervals=expansion_periods,
                          discount_rate=discount_rate,
                          ES=system,
                          objective_set=obj)

optimiser.optimise(tee=True)

log_infeasible_constraints(optimiser.model)


############################ Analyse the Optimisation ########################################

print('EV NODE ATTRIBUTES:')
pprint.pprint(vars(ev_cp))
print('\n OPTIMISATION RESULTS: ')
pprint.pprint(optimiser.node_values(ev_cp, 0))
print('EV soc: ', optimiser.values(ev_cp.ports['vehicle'].soc_value,0))
print('Infeasibility: ', optimiser.values(ev_cp.ports['vehicle'].trip_slack, 0))

plt.plot(demand)
plt.plot(usage)
plt.plot(optimiser.values(ev_cp.ports['vehicle'].soc_value,0))
plt.plot(optimiser.values(connection_point.ports['grid'].pos, 0))
plt.plot(tariff_array)
plt.legend(['Load', 'EV trip usage', 'EV soc', 'grid cp (+ve importing)', 'import_tariff'])
plt.xlim([0, 47])

