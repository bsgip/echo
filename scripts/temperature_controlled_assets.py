from echo.echo_models import *
from echo.echo_thermal_models import *
from echo.echo_optimiser import *
import matplotlib.pyplot as plt
from echo.utils import *
import seaborn as sns

expansion_periods = 1
time_periods = 48
interval_duration = 30

system = OptimisationGraph()

gas_mains = Node()
gas_mains.ports['mains'] = GasSource()

boiler = BoilerWithTemps()

lb = [i for i in range(0, 16)] + [16]*16 + [j for j in range(15,-1,-1)]
ub = [20]*time_periods
external_temp = generate_array_constraint([0]*time_periods, time_periods, expansion_periods)
heating_load = Node()
hlp = TemperatureControlledHeatingLoad(temp_ub=ub,
                                       temp_lb=lb,
                                       minimise_temp_error=False,
                                       external_temp=external_temp)  # Add a HCLoad input port
heating_load.ports['input'] = hlp

system.add_node_obj([gas_mains, boiler, heating_load])
system.connect_ports_and_create_edge(gas_mains.ports['mains'], boiler.ports['input'])
system.connect_ports_and_create_edge(boiler.ports['output'], heating_load.ports['input'])

optimiser = EchoOptimiser(
    interval_duration=interval_duration,
    number_of_intervals=time_periods,
    number_of_expansion_intervals=expansion_periods,
    discount_rate=0,
    ES=system,
    objective_set=None
)

# optimiser.objective += sum(getattr(optimiser.model, hlp.internal_temp)[p, t] \
#                            for p in optimiser.model.Expansion for t in optimiser.model.Time)
optimiser.optimise(tee=True)

boiler_input = optimiser.values(boiler.ports['input'].port_name, 0)
boiler_output = optimiser.values(boiler.ports['output'].port_name, 0)
hl = optimiser.values(heating_load.ports['input'].port_name)
load_temp = optimiser.values(hlp.internal_temp, 0)
temp_error = optimiser.values(hlp.temp_error)
loss_to_external = np.array(list(external_temp.values())) - np.array(load_temp)

# # Plot some results
# c = sns.color_palette()
# hrs = np.arange(0, time_periods) / 4
# ax1 = plt.subplot()
# line1, = ax1.plot(hrs, hl, color=c[0])
# ax2 = ax1.twinx()
# line2, = ax2.plot(hrs, ub, color=c[1])
# line3, = ax2.plot(hrs, lb, color=c[2])
# line4, = ax2.plot(hrs, load_temp, color=c[3])
# ax1.set_xlabel('hour')
# ax1.set_ylabel('kW')
# ax2.set_ylabel('deg C')
# plt.legend([line1, line2, line3, line4], ['heating load (kW)',
#                                           'temp upper bound (degC)',
#                                           'temp lower bound (degC)',
#                                           'load internal temp (degC)'])
# ax1.set_xlim([0, time_periods/4])
# ax2.set_xlim([0, time_periods/4])
# # ax1.set_ylim([0, 30])
# # ax2.set_ylim([0, 20])
#
#
# plt.show()

fig = plt.Figure()
plt.plot(hl)
plt.plot(ub)
plt.plot(lb)
plt.plot(load_temp)
plt.legend(['heating load (kW)', 'temp upper bound (degC)', 'temp lower bound (degC)','load internal temp (degC)'])
plt.show()
