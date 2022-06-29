from echo.echo_models import *
from echo.echo_thermal_models import *
from echo.echo_thermal_models import *
from echo.echo_optimiser import *
from echo.objectives import *


expansion_periods = 1
time_periods = 24
interval_duration = 60

system = OptimisationGraph()

heatsource = Node()
heatsource.ports['source'] = ThermalPort()

coolingsource = Node()
coolingsource.ports['source'] = ThermalPort()

external_temp = np.array([2] * time_periods)
external_temp_dict = generate_array_constraint(external_temp, time_periods, expansion_periods)
temp_lb = np.array([0] * 7 + [0.2] * 1 + [0.4] * 1 + [0.8] * 2 + [1] * 2 + [0.8] * 2 + [0.4] * 1 + [0.2] * 1 + [0] * 7) * 10
temp_ub = np.array(temp_lb) + 5
building_node = BuildingThermalLoad(temp_ub=temp_ub,
                                    temp_lb=temp_lb,
                                    external_temp=external_temp_dict,
                                    loss_factor=0,
                                    temp_to_energy_coef=2.5
                                    )

system.add_node_obj([heatsource, coolingsource, building_node])
system.connect_ports_and_create_edge(heatsource.ports['source'], building_node.ports['heating'])
system.connect_ports_and_create_edge(coolingsource.ports['source'], building_node.ports['cooling'])

throughput_cost1 = ThroughputCost(component=heatsource.ports['source'],
                                  rate=0.00001)
throughput_cost2 = ThroughputCost(component=coolingsource.ports['source'],
                                  rate=0.00001)

optimiser = EchoOptimiser(
    interval_duration=interval_duration,
    number_of_intervals=time_periods,
    number_of_expansion_intervals=expansion_periods,
    discount_rate=0,
    ES=system,
    objective_set=ObjectiveSet(objective_list=[throughput_cost1, throughput_cost2])
)

optimiser.optimise(tee=True)

internal_temp = optimiser.values(building_node.internal_temp)
heating_draw = optimiser.values(building_node.ports['heating'].port_name)
cooling_draw = optimiser.values(building_node.ports['cooling'].port_name)

fig, ax = plt.subplots()
hrs = np.array([i for i in range(time_periods)])
t_ub = np.array(temp_ub)
t_lb = np.array(temp_lb)
ax.fill_between(hrs, t_lb, t_ub, color='none', hatch='/', edgecolor='grey', label='Temperature bound (degC)')
ax.plot(internal_temp, label='Internal temp(degC)')
#plt.plot(external_temp)
ax.plot(heating_draw, label='Heat added (kW)')
ax.plot(cooling_draw, label='Cooling added (kW)')
ax.legend()
plt.xlabel('Hrs')
plt.show()
