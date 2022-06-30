import matplotlib.pyplot as plt

from echo.echo_models import *
from echo.echo_thermal_models import *
from echo.echo_optimiser import *


expansion_periods = 1
time_periods = 24
interval_duration = 60

system = OptimisationGraph()

source = Node()
source.ports['source'] = GasPort()

boiler = TempControlledBoiler(max_input=100,
                              min_input=0,
                              max_output=-100,
                              min_output=0,
                              conversion_factor = 0.5,
                              cop=0.6
                              )

heating_load = Node()
hl = FixedThermalPort()
hl.add_initial_value_from_array([0] * 6 + [2] * 6 + [4] * 12, expansion_periods)
heating_load.ports['load'] = hl

system.add_node_obj([source, boiler, heating_load])
system.connect_ports_and_create_edge(source.ports['source'], boiler.ports['input'])
system.connect_ports_and_create_edge(boiler.ports['output'], hl)

optimiser = EchoOptimiser(
    interval_duration=interval_duration,
    number_of_intervals=time_periods,
    number_of_expansion_intervals=expansion_periods,
    discount_rate=0,
    ES=system,
    objective_set=None
)

optimiser.optimise(tee=True)

print(optimiser.opt_status)


boiler_input = optimiser.values(boiler.ports['input'].port_name)
boiler_output = optimiser.values(boiler.ports['output'].port_name)

boiler_exit_temp = optimiser.values(boiler.exit_temp)
boiler_return_temp = optimiser.values(boiler.return_temp)

hl_vals = optimiser.values(hl.port_name)

fig = plt.figure()
plt.plot(boiler_input, label='boiler input (kW)')
plt.plot(boiler_output, label='boiler output (kW)')
plt.plot(boiler_exit_temp, label='boiler exit temp (degC)')
plt.plot(boiler_return_temp, label='boiler return temp (degC)')
plt.plot(hl_vals, label='heating load (kW)')
plt.legend()
plt.show()
