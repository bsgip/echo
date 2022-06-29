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

# Define an electricity supply node
grid = Node()
grid.ports['grid'] = ElectricalPort()

# Define a heat pump
#heating_cop = np.concatenate([np.linspace(1.6, 4.45, num=12), np.linspace(4.45, 1.6, num=12)])
heating_cop = np.array([0]*time_periods)
heat_cop_dict = generate_dict_with_pyomo_keys_from_array(heating_cop, time_periods)
#cooling_cop = np.concatenate([np.linspace(4.5, 2.15, num=12), np.linspace(2.15, 4.5, num=12)])
cooling_cop = np.array([2]*time_periods)
cool_cop_dict = generate_dict_with_pyomo_keys_from_array(cooling_cop, time_periods, expansion_periods)

heat_pump = HeatPump(heating_cop_time_series=heat_cop_dict,
                     cooling_cop_time_series=cool_cop_dict)

heat_pump.ports['input'] = FlexPortImport(units=Units.KW)  # Heat pump has electrical input port
heat_pump.ports['heating_out'] = FlexPortExport(units=Units.KWT)  # Heat pump has a thermal port for heating output
heat_pump.ports['cooling_out'] = FlexPortExport(units=Units.KWT)  # Heat pump has a thermal port for cooling output

# Define a building thermal load

external_temp = np.array([2] * time_periods)
external_temp_dict = generate_array_constraint(external_temp, time_periods, expansion_periods)
temp_lb = np.array([0] * 7 + [0.2] * 1 + [0.4] * 1 + [0.8] * 2 + [1] * 2 + [0.8] * 2 + [0.4] * 1 + [0.2] * 1 + [0] * 7) * 10
temp_ub = np.array(temp_lb) + 5
building_node = BuildingThermalLoad(temp_ub=temp_ub,
                                    temp_lb=temp_lb,
                                    external_temp=external_temp_dict,
                                    loss_factor=0,
                                    temp_to_energy_coef=1
                                    )
building_node.ports['heating'] = FlexPortImport(units=Units.KWT)
building_node.ports['cooling'] = FlexPortImport(units=Units.KWT)

system.add_node_obj([grid, heat_pump, building_node])
system.connect_ports_and_create_edge(grid.ports['grid'], heat_pump.ports['input'])
system.connect_ports_and_create_edge(heat_pump.ports['heating_out'], building_node.ports['heating'])
system.connect_ports_and_create_edge(heat_pump.ports['cooling_out'], building_node.ports['cooling'])

optimiser = EchoOptimiser(
    interval_duration=interval_duration,
    number_of_intervals=time_periods,
    number_of_expansion_intervals=expansion_periods,
    discount_rate=0,
    ES=system,
    objective_set=None
)

optimiser.optimise(tee=True)

print(optimiser.values(heat_pump.ports['heating_out'].port_name))
print(optimiser.values(building_node.ports['heating'].port_name))
print(optimiser.values(heat_pump.ports['cooling_out'].port_name))
print(optimiser.values(building_node.ports['cooling'].port_name))


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
