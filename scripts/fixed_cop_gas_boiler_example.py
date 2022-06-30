import matplotlib.pyplot as plt

from echo.echo_models import *
from echo.echo_thermal_models import *
from echo.echo_optimiser import *
from echo.objectives import *

expansion_periods = 1
time_periods = 24
interval_duration = 30

system = OptimisationGraph()

gas_mains = Node()
gas_mains.ports['mains'] = GasPort()

boiler = GasBoilerFixedCOP(max_input=10,
                           min_input=10,
                           max_output=-100,
                           min_output=-0,
                           cop=1)


lb = [0]*6 + [5]*6 + [10]*6 + [12]*6
ub = [1000] * time_periods  # constant upper bound
external_temp = np.array([i for i in range(0, 12)] + [j for j in range(12, 0, -1)]) + 10
external_temp = [3]*time_periods
external_temp_dict = generate_array_constraint(external_temp, time_periods, expansion_periods)
heating_node = Node()
heating_port = ControllableThermalLoad(temp_ub=ub,
                                       temp_lb=lb,
                                       external_temp=external_temp_dict,
                                       temp_to_energy_coef=5,
                                       loss_factor=0.2,
                                       gain_factor=0
                                       )
heating_node.ports['heating_load'] = heating_port

system.add_node_obj([gas_mains, boiler, heating_node])
system.connect_ports_and_create_edge(gas_mains.ports['mains'], boiler.ports['input'])
system.connect_ports_and_create_edge(boiler.ports['output'], heating_port)

tp_cost = ThroughputCost(component=gas_mains.ports['mains'],
                         rate=0.0001)

optimiser = EchoOptimiser(
    interval_duration=interval_duration,
    number_of_intervals=time_periods,
    number_of_expansion_intervals=expansion_periods,
    discount_rate=0,
    ES=system,
    objective_set=ObjectiveSet(objective_list=[tp_cost])
)


optimiser.optimise(tee=True)

gas_mains = optimiser.values(gas_mains.ports['mains'].port_name, 0)
boiler_input = optimiser.values(boiler.ports['input'].port_name)
boiler_output = optimiser.values(boiler.ports['output'].port_name)
load_temp = optimiser.values(heating_port.internal_temp)
thermal_load = optimiser.values(heating_port.port_name)
loss = optimiser.values(heating_port.losses)
gain = optimiser.values(heating_port.gains)
print('loss: ', loss)
print('gain: ', gain)

plt.plot(boiler_input, label='boiler in')
plt.plot(boiler_output, label='boiler out')
plt.plot(lb, label='temp lower bound')
plt.plot(load_temp, label='load temp')
plt.plot(external_temp, label='ambient temp')
#plt.plot(loss, label='loss to ambient')
#plt.plot(gain, label='gain from ambient')
plt.legend()
plt.show()
