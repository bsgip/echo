import matplotlib.pyplot as plt

from echo.echo_models import *
from echo.echo_thermal_models import *
from echo.echo_optimiser import *


expansion_periods = 1
time_periods = 24
interval_duration = 30

system = OptimisationGraph()

grid = Node()
grid.ports['grid'] = ElectricalPort()

# nonlin_array = [-0.0068, 5.5052, 0]
input_breakpoints = [0, 2, 3, 8]
output_values = [0, 3, 4, 8]
chiller = SimpleChiller(output_ub=20,
                        input_ub=20)
chiller.add_input_pts(array=input_breakpoints, time_periods=time_periods)
chiller.add_output_pts(array=output_values, time_periods=time_periods)

ub = [12]*6 + [10]*6 + [5]*6 + [0]*6
lb = [5]*10 + [0]*14
#external_temp = np.array([i for i in range(0, 12)] + [j for j in range(12, 0, -1)]) + 10
external_temp = [3]*time_periods
external_temp_dict = generate_array_constraint(external_temp, time_periods, expansion_periods)
cooling_node = Node()
cooling_port = ControllableThermalLoad(temp_ub=ub,
                                       temp_lb=lb,
                                       external_temp=external_temp_dict,
                                       temp_to_energy_coef=1,
                                       loss_factor=0,
                                       gain_factor=0,
                                       initial_internal_temp=8,
                                       )
cooling_node.ports['load'] = cooling_port

system.add_node_obj([grid, chiller, cooling_node])
system.connect_ports_and_create_edge(grid.ports['grid'], chiller.ports['input'])
system.connect_ports_and_create_edge(chiller.ports['output'], cooling_port)

optimiser = EchoOptimiser(
    interval_duration=interval_duration,
    number_of_intervals=time_periods,
    number_of_expansion_intervals=expansion_periods,
    discount_rate=0,
    ES=system,
    objective_set=None
)

optimiser.optimise(tee=True)

gas_mains = optimiser.values(grid.ports['grid'].port_name, 0)
boiler_input = optimiser.values(chiller.ports['input'].port_name)
boiler_output = optimiser.values(chiller.ports['output'].port_name)
load_temp = optimiser.values(cooling_port.internal_temp)
thermal_load = optimiser.values(cooling_port.port_name)
loss = optimiser.values(cooling_port.losses)
gain = optimiser.values(cooling_port.gains)
print('loss: ', loss)
print('gain: ', gain)


fig = plt.figure()
hrs = np.array([i for i in range(time_periods)])
plt.fill_between(hrs, lb, ub, color='none', edgecolor='grey', hatch='/', label='load temp bounds')
plt.plot(boiler_input, label='chiller in')
plt.plot(boiler_output, label='chiller out')
plt.plot(lb, label='temp lower bound')
plt.plot(load_temp, label='load temp')
plt.plot(external_temp, label='ambient temp')
#plt.plot(loss, label='loss to ambient')
#plt.plot(gain, label='gain from ambient')
plt.legend()
plt.show()
