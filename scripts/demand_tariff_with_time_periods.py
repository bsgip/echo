import os

import matplotlib.pyplot as plt
import seaborn as sns

from echo.echo_optimiser import EchoOptimiser
from echo.objectives import *
from echo.echo_models import *

SOLVER = os.environ.get('OPTIMISER_ENGINE', 'cplex')
SOLVER_EXECUTABLE = None

expansion_periods = 1
profile = pd.DataFrame(
    index=pd.date_range(start=datetime(2021, 1, 4), end=datetime(2021, 1, 11), freq='30min', closed='left'))

time_periods = len(profile)
interval_duration = 30

system = OptimisationGraph()

grid = Node()
grid.add_electrical_ports_from_list(['grid'])

battery1 = Node()
b1 = ElectricalStorage(max_capacity=15.0,
                       depth_of_discharge_limit=0,
                       charging_power_limit=2.0,
                       discharging_power_limit=-2.0,
                       charging_efficiency=1,
                       discharging_efficiency=1,
                       initial_state_of_charge=0.0)
battery1.ports['battery'] = b1

load1 = Node()
l1 = ElectricalDemand()

l1.add_demand_profile_from_array([10]*time_periods, expansion_periods)
load1.ports['demand'] = l1

site1 = TellegenNode()
site1.add_electrical_ports_from_list(['cp', 'load', 'bess'])
cp1 = site1.ports['cp']

system.add_node_obj([grid, battery1, load1, site1])

bess_edge1 = Edge(vertices=[site1.ports['bess'], b1])
load_edge1 = Edge(vertices=[site1.ports['load'], l1])
grid_edge = Edge(vertices=[cp1, grid.ports['grid']])

system.add_edge_obj([bess_edge1, load_edge1, grid_edge])

# peak usage
peak_window_new = Window(
    time_periods=[
        TimePeriod(start_time=time(18, 0),
                   end_time=time(21, 0),
                   day_type=[Day.weekday, Day.weekend]
                   )],
    reset_periods=ResetPeriod.day
)

peak_charge = ImportDemandCharge(name='peak',
                                 rate=10.0,
                                 window_object=peak_window_new,
                                 min_demand=0.0)

demand_tariff = DemandTariffObjective(component=cp1,
                                      demand_charges=[peak_charge])

throughput_cost = ThroughputCost(component=b1, rate=0.0001)
objective_set = ObjectiveSet(objective_list=[demand_tariff, throughput_cost])


optimiser = EchoOptimiser(
    interval_duration=interval_duration,
    number_of_intervals=time_periods,
    number_of_expansion_intervals=expansion_periods,
    discount_rate=0,
    ES=system,
    objective_set=objective_set,
    profile=profile
)

optimiser.optimise()
print(optimiser.opt_status)

print(optimiser.values(peak_charge.max_demand_val))

print(optimiser.values(b1.port_name))

plt.plot(optimiser.values(cp1.port_name))
plt.plot(peak_charge.window_array+10)
plt.show()
plt.legend(['demand', 'active demand periods'])