import matplotlib.pyplot as plt
import numpy as np

from echo.echo_models import *
from echo.echo_thermal_models import *
from echo.echo_thermal_models import *
from echo.echo_optimiser import *
from echo.objectives import *

""" 
Example with a heat pump serving both heating and cooling loads.
"""
np.set_printoptions(suppress=True)

expansion_periods = 1
time_periods = 24
interval_duration = 60

system = OptimisationGraph()

source = Node()
source.ports['source'] = ElectricalPort()

heating_cop = np.array([2] * time_periods)
heat_cop_dict = generate_dict_with_pyomo_keys_from_array(heating_cop, time_periods)

heat_pump = HeatPumpSingleOutput(heating_cop_time_series=heat_cop_dict,
                                 cooling_cop_time_series=heat_cop_dict)

external_temp = np.array([2] * time_periods)
external_temp_dict = generate_array_constraint(external_temp, time_periods, expansion_periods)
temp_lb = np.array(
    [0] * 7 + [0.2] * 1 + [0.4] * 1 + [0.8] * 2 + [1] * 2 + [0.8] * 2 + [0.4] * 1 + [0.2] * 1 + [0] * 7) * 10
temp_ub = np.array(temp_lb) + 5
temp_lb_dict = generate_dict_with_pyomo_keys_from_array(temp_lb, time_periods, expansion_periods)
temp_ub_dict = generate_dict_with_pyomo_keys_from_array(temp_ub, time_periods, expansion_periods)

thermal_load = ThermalNode(temp_ub=temp_ub_dict,
                             temp_lb=temp_ub_dict,
                             external_temp=external_temp_dict,
                             temp_to_energy_coef=1,
                             loss_factor=0.0,
                             gain_factor=0.0,
                             initial_internal_temp=0
                             )
hl = ThermalPort()
thermal_load.ports['load'] = hl

system.add_node_obj([source, heat_pump, thermal_load])
system.connect_ports_and_create_edge(source.ports['source'], heat_pump.ports['input'])
system.connect_ports_and_create_edge(heat_pump.ports['output'], hl)

tp_cost = ThroughputCost(rate=0.00001,
                         component=source.ports['source'])

optimiser = EchoOptimiser(
    interval_duration=interval_duration,
    number_of_intervals=time_periods,
    number_of_expansion_intervals=expansion_periods,
    discount_rate=0,
    ES=system,
    objective_set=ObjectiveSet(objective_list=[tp_cost])
)

optimiser.optimise(True)

# HP
elec_in = optimiser.values(heat_pump.ports['input'].port_name)
heat_out = optimiser.values(heat_pump.ports['output'].neg)
cool_out = optimiser.values(heat_pump.ports['output'].pos)

# thermal load
hload = optimiser.values(hl.port_name)*[optimiser.values(hl.port_name)>=0]
cload = optimiser.values(hl.port_name)*[optimiser.values(hl.port_name)<=0]
temp = optimiser.values(thermal_load.internal_temp)

print(elec_in, heat_out, cool_out, hload, cload)

fig = plt.figure()
hrs = np.array([i for i in range(time_periods)])
#plt.fill_between(hrs, temp_lb, temp_ub, color='none', edgecolor='grey', hatch='/', label='load temp bounds')
plt.plot(temp_ub, color='yellow', label='temp setpoint')
plt.plot(elec_in, color='blue', label='HP elec_in (kW)')
plt.plot(heat_out, color='orange', label='HP heating out (kW)')
plt.plot(cool_out, color='green', label='HP cooling out (kW)')
# plt.plot(hload, label='heat load')
# plt.plot(cload, label='cool load')
plt.plot(temp, '--', color='red', label='load internal temp (degC)')
plt.legend()
plt.show()
