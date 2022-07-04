import matplotlib.pyplot as plt

from echo.echo_models import *
from echo.echo_thermal_models import *
from echo.echo_optimiser import *
from echo.objectives import *

expansion_periods = 1
time_periods = 24
interval_duration = 60

system = OptimisationGraph()

source = Node()
source.ports['source'] = GasPort()

boiler = TempControlledBoiler(max_input=100,
                              min_input=15,
                              deg_to_kw=1,
                              cop=1
                              )
# temp_sp = np.linspace(75, 80, time_periods)
# temp_sp_dict = generate_dict_with_pyomo_keys_from_array(temp_sp, time_periods, expansion_periods)
# boiler.exit_temp_setpoint = temp_sp_dict

external_temp = [2] * time_periods
external_temp_dict = generate_array_constraint(external_temp, time_periods, expansion_periods)
temp_lb = [0]*8 + [20]*8 + [0]*8
temp_ub = np.array(temp_lb) + 25

thermal_load = ThermalNode(temp_ub=generate_dict_with_pyomo_keys_from_array(temp_ub, time_periods, expansion_periods),
                           temp_lb=generate_dict_with_pyomo_keys_from_array(temp_lb, time_periods, expansion_periods),
                           external_temp=external_temp_dict,
                           temp_to_energy_coef=1,
                           loss_factor=0.05
                           )
hl = FlexHeatSink()
thermal_load.ports['load'] = hl

system.add_node_obj([source, boiler, thermal_load])
system.connect_ports_and_create_edge(source.ports['source'], boiler.ports['input'])
system.connect_ports_and_create_edge(boiler.ports['output'], hl)

obj = PeakPositivePower(component=boiler.ports['input'])

obj_set = ObjectiveSet(objective_list=[obj])

optimiser = EchoOptimiser(
    interval_duration=interval_duration,
    number_of_intervals=time_periods,
    number_of_expansion_intervals=expansion_periods,
    discount_rate=0,
    ES=system,
    objective_set=obj_set
)

optimiser.optimise(tee=True)

print(optimiser.opt_status)

boiler_input = optimiser.values(boiler.ports['input'].port_name)
boiler_output = optimiser.values(boiler.ports['output'].port_name)

boiler_exit_temp = optimiser.values(boiler.exit_t)
boiler_return_temp = optimiser.values(boiler.return_t)

hl_vals = optimiser.values(hl.port_name)

fig = plt.figure()
plt.plot(boiler_input, label='boiler input (kW)')
# plt.plot(boiler_output, label='boiler output (kW)')
plt.plot(boiler_exit_temp, label='boiler exit temp (degC)')
plt.plot(boiler_return_temp, label='boiler return temp (degC)')
plt.plot(hl_vals, label='heating load (kW)')
plt.plot(optimiser.values(thermal_load.internal_temp), label='load temp')

plt.legend()
plt.show()
