from __future__ import division

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pyomo.util.infeasible import log_infeasible_constraints


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
grid.add_named_electrical_ports(['grid'])       # create a port which will be used to connect this with the connection_point

# create the connection point (where we will sum everything up)
connection_point = ElectricalTellegenNode()
connection_point.add_named_electrical_ports(['ev', 'grid'])  # create ports to connect to the grid, the load, and the inverter

# Create V0G vehicle

available = np.array([1] * 24 + [0] * 24)    # bool when at charger
usage = np.array([0.0]*24 + [5]*24)        # kw average during use

ev_cp = EV(charge_mode='V0G',
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
               interval_duration=30.,
               tod_charging=None,
               trip_slack=True)


system.add_node_obj([grid, ev_cp, connection_point])

# Create edge objects and add to graph
system.connect_ports_and_create_edge(connection_point.ports['ev'], ev_cp.ports['cp'])
system.connect_ports_and_create_edge(grid.ports['grid'], connection_point.ports['grid'])

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

print(optimiser.node_values(ev_cp, 0))
print('Trip usage:', usage)
print('EV soc: ', optimiser.values(ev_cp.ports['vehicle'].soc_value,0))
print('Infeasibility: ', ev_cp.trip_infeasibility)

plt.plot(usage)
plt.plot(optimiser.values(ev_cp.ports['vehicle'].soc_value,0))
plt.plot(ev_cp.trip_infeasibility)
plt.plot(optimiser.values(ev_cp.ports['vehicle'].trip_slack,0))
plt.legend(['Usage', 'EV soc', 'infeasibility', 'slack_var'])

print('Slack sum: ', optimiser.values(ev_cp.ports['vehicle'].trip_slack,0).sum())
print('infeasibility sum: ', ev_cp.trip_infeasibility.sum())

