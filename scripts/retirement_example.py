from __future__ import division

import seaborn as sns
from pyomo.util.infeasible import log_infeasible_constraints

from echo.echo_optimiser import EchoOptimiser
from echo.objectives import *
from echo.echo_models import *

""" 
            Example of optimising a behind the meter battery where there is also a load and pv at the location

             our graph is going to look like

                   grid----connection_point----|----load
                                               |----inverter----|----battery
                                                                |----pv

"""

# set up seaborn the way you like
sns.set_style({'axes.linewidth': 1, 'axes.edgecolor': 'black', 'xtick.direction': \
    'out', 'xtick.major.size': 4.0, 'ytick.direction': 'out', 'ytick.major.size': 4.0, \
               'axes.facecolor': 'white', 'grid.color': '.8', 'grid.linestyle': u'-', 'grid.linewidth': 0.5})

############################ Define an Example Optimisation Problem ########################################

############################ Optimise this Example ########################################

np.set_printoptions(suppress=True)

## Set up hyper params
time_periods = 24  # number of time periods to run the optimisation for
interval_duration = 60
expansion_periods = 14
discount_rate = 0  # not yet implemented leave as 0

# Create graph in echo
system = OptimisationGraph()

# Create assets
grid = Node()  # create node representing upstream grid
grid.add_electrical_ports_from_list(['grid'])

connection_point = TellegenNode()  # create the connection point
connection_point.add_electrical_ports_from_list(['load', 'inv', 'grid'])

load = Node()  # create a node to represent the load
l1 = ElectricalDemand()  # create an electrical demand to attach to this node

# Create an array of increasing load each expansion period
init_demand = 10
inc = 10
demand = []
for i in range(expansion_periods):
    demand += [init_demand + inc*i] * time_periods

l1.add_initial_value_from_array(array=demand, expansion_periods=expansion_periods, time_periods=time_periods)
load.ports['load'] = l1  # add the electrical demand to a port of the load node

inverter = Inverter()
inverter.add_ac_port('inv')  # add a port that is used to connect back to the connection_point
inverter.add_dc_port('bess')  # add a port to connect to the battery

# create a retirement node for the battery - retirement parameters are specified at node level
battery = RetirementNode(node_name='battery',
                         initial_life_left=2,
                         nominal_lifetime=3,
                         replace_cost=10.)

b = ElectricalStorage(max_capacity=10.0,  # max capacity of battery in kwh
                                           depth_of_discharge_limit=0, # allowable depth of discharge in range [0,100] (i.e. percent)
                                           charging_power_limit=2,  # max charging rate in kW
                                           discharging_power_limit=-2,  # max discharging rate in kW
                                           charging_efficiency=1,  # charging efficiency in range [0,1]
                                           discharging_efficiency=1,  # discharging efficiency in range [0,1]
                                           initial_state_of_charge=0.0) # initial state of charge in kWh
battery.add_port('bess', b)

# Populate graph with assets (nodes)
system.add_node_obj([grid, battery, load, connection_point, inverter])

# Add edges to graph (i.e. connect up the graph structure how we want it)
system.connect_ports_and_create_edge(grid.ports['grid'], connection_point.ports['grid'])
system.connect_ports_and_create_edge(connection_point.ports['load'], load.ports['load'])
system.connect_ports_and_create_edge(connection_point.ports['inv'], inverter.ports['inv'])
system.connect_ports_and_create_edge(inverter.ports['bess'], battery.ports['bess'])

# Create objectives/tariffs
import_cost = ImportTariff(name='import_cost',
                           component=connection_point.ports['grid'],
                           tariff_array=[2] * (time_periods//2) + [1] * (time_periods//2),
                           expansion_periods=expansion_periods)  # create the import objective cost

objective_set = ObjectiveSet(objective_list=[import_cost])

############################ ----------------------- ########################################

# Invoke the optimiser and optimise
opt = EchoOptimiser(interval_duration=interval_duration,
                    number_of_intervals=time_periods,
                    number_of_expansion_intervals=expansion_periods,
                    discount_rate=discount_rate,
                    ES=system,
                    objective_set=objective_set,
                    optimiser_engine='cplex')

opt.optimise(tee=True)

log_infeasible_constraints(opt.model)


print('Battery1 life remaining: ', opt.values(battery.lifetime_remaining, 0))
print('Battery1 retired: ', opt.values(battery.retire, 0))
print('Battery1 replaced: ', opt.values(battery.replace, 0))
print('Total cost: ', opt.get_total_objective_value())

############################ Analyse the Optimisation ########################################

print()
