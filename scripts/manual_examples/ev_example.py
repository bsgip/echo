"""

Example of electric vehicle optimisation, using evs with V0G, V1G, and V2G charge modes.

"""

from __future__ import division

import pprint

from pyomo.util.infeasible import log_infeasible_constraints

from echo.echo_optimiser import EchoOptimiser
from echo.echo_models import *

## Set up hyper params
time_periods = 48  # number of time periods to run the optimisation for
interval_duration = 30  # each time period is 15 mins long
expansion_periods = 1  # not yet implemented leave as 1
discount_rate = 0  # not yet implemented leave as 0

# Create graph
system = OptimisationGraph()

# Create an infinite grid node with one downstream port
grid = FlexElectricalNode(port_name='grid')  

# Create a connection point (zero sum) node with ports for our three EVs
connection_point = TellegenNode()
connection_point.add_electrical_ports_from_list(['grid', 'ev_v0g', 'ev_v1g', 'ev_v2g'])  

# Create V0G vehicle

available = [1] * 24 + [0] * 24  # bool when at charger
usage = [0.0] * 24 + [5] * 24  # kw average during use

ev_v0g = EV(charge_mode='V0G',
            available=available,
            usage=usage,
            connection_port_name='cp',
            max_capacity=40,
            depth_of_discharge_limit=0,
            charging_power_limit=10,
            discharging_power_limit=-1e4,
            charging_efficiency=1,
            discharging_efficiency=1,
            initial_state_of_charge=20,
            soc_conserv=None,
            soc_conserv_cost=0.,
            interval_duration=interval_duration,
            tod_charging=None,
            trip_slack=True)

# Create V1G vehicle

available = np.array([1] * 24 + [0] * 24)  # bool when at charger
usage = np.array([0.0] * 24 + [5] * 24)  # kw average during use

ev_v1g = EV(charge_mode='V1G',
            available=available,
            usage=usage,
            connection_port_name='cp',
            max_capacity=40,
            depth_of_discharge_limit=0,
            charging_power_limit=10,
            discharging_power_limit=-1e4,
            charging_efficiency=1,
            discharging_efficiency=1,
            initial_state_of_charge=0,
            soc_conserv=None,
            soc_conserv_cost=0.,
            interval_duration=interval_duration,
            tod_charging=False,
            trip_slack=True)

# Create a V2G vehicle

available = np.array([1] * 24 + [0] * 24)  # bool when at charger
usage = np.array([0.0] * 24 + [2] * 24)  # kw average during use

ev_v2g = NewEV(charge_mode='V2G',
            available=available,
            usage=usage,
            connection_port_name='cp',
            max_capacity=40,
            depth_of_discharge_limit=0,
            charging_power_limit=10,
            discharging_power_limit=-1e4,
            charging_efficiency=1,
            discharging_efficiency=1,
            initial_state_of_charge=20,
            soc_conserv=[30]*20 + [10]*28,
            soc_conserv_cost=1.,
            interval_duration=interval_duration,
            tod_charging=False,
            trip_slack=True)

system.add_node_obj([grid, ev_v0g, ev_v1g, ev_v2g, connection_point])

# Create edge objects and add to graph
system.connect_ports_and_create_edge(grid.ports['grid'], connection_point.ports['grid'])
system.connect_ports_and_create_edge(connection_point.ports['ev_v0g'], ev_v0g.ports['cp'])
system.connect_ports_and_create_edge(connection_point.ports['ev_v1g'], ev_v1g.ports['cp'])
system.connect_ports_and_create_edge(connection_point.ports['ev_v2g'], ev_v2g.ports['cp'])

############################ ----------------------- ########################################

# Invoke the optimiser and optimise
optimiser = EchoOptimiser(interval_duration=interval_duration,
                          number_of_intervals=time_periods,
                          number_of_expansion_intervals=expansion_periods,
                          discount_rate=discount_rate,
                          ES=system,
                          objective_set=None)

optimiser.optimise(tee=True)

log_infeasible_constraints(optimiser.model)

############################ Analyse the Optimisation ########################################
ev_cp = ev_v0g

print('EV V0G NODE ATTRIBUTES:')
pprint.pprint(vars(ev_cp))
print('\n OPTIMISATION RESULTS: ')
print(optimiser.node_values(ev_cp, 0))
print('EV soc: ', optimiser.values(ev_cp.ports['vehicle'].soc_value, 0))
print('Infeasibility: ', optimiser.values(ev_cp.ports['vehicle'].trip_slack, 0))

plt.plot(usage)
plt.plot(optimiser.values(ev_cp.ports['vehicle'].soc_value, 0))
plt.plot(optimiser.values(ev_cp.ports['vehicle'].trip_slack, 0))
plt.legend(['Usage', 'EV soc', 'infeasibility'])
plt.xlim([0, 47])
plt.show()

ev_cp = ev_v1g

print('EV V1G NODE ATTRIBUTES:')
pprint.pprint(vars(ev_cp))
print('\n OPTIMISATION RESULTS: ')
print(optimiser.node_values(ev_cp, 0))
print('EV soc: ', optimiser.values(ev_cp.ports['vehicle'].soc_value, 0))
print('Infeasibility: ', optimiser.values(ev_cp.ports['vehicle'].trip_slack, 0))

plt.plot(usage)
plt.plot(optimiser.values(ev_cp.ports['vehicle'].soc_value, 0))
plt.plot(optimiser.values(ev_cp.ports['vehicle'].trip_slack, 0))
plt.legend(['Usage', 'EV soc', 'infeasibility'])
plt.xlim([0, 47])
plt.show()

ev_cp = ev_v2g

print('EV V2G NODE ATTRIBUTES:')
pprint.pprint(vars(ev_cp))
print('\n OPTIMISATION RESULTS: ')
print(optimiser.node_values(ev_cp, 0))
print('EV soc: ', optimiser.values(ev_cp.ports['vehicle'].soc_value, 0))
print('Infeasibility: ', optimiser.values(ev_cp.ports['vehicle'].trip_slack, 0))

plt.plot(usage)
plt.plot(optimiser.values(ev_cp.ports['vehicle'].soc_value, 0))
plt.plot(optimiser.values(ev_cp.ports['vehicle'].trip_slack, 0))
plt.legend(['Usage', 'EV soc', 'infeasibility'])
plt.xlim([0, 47])
plt.show()
