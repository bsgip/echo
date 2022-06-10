from echo.echo_models import *
from echo.echo_optimiser import *

expansion_periods = 1
time_periods = 4
interval_duration = 60

system = OptimisationGraph()

grid = Node()
grid.ports['grid'] = ElectricalPort()

# create an indexed coefficient array
# temperature_array = np.array([i for i in range(time_periods)])*0.5
# temp_coef = [-1,0]
# input_coef = [1,0]

# chiller = NewChiller(max_output=-1000,
#                      max_input=1000,
#                      temp_coef=temp_coef,
#                      input_coef=input_coef,
#                      temperature_array=temperature_array)
#

input_pts = [0,1,2,3,4]
output_pts = [0,-2,-3,-10, -20]

chiller = Chiller(max_output=-1000,
                     max_input=1000)
chiller.set_input_output_breakpoints(input_pts, output_pts, time_periods)

cooling_load = Node()
cl = HeatingOrCoolingLoad()
cl.add_sink_profile_from_array([20] * time_periods, expansion_periods)
cooling_load.ports['load'] = cl

system.add_node_obj([grid, chiller, cooling_load])
system.connect_ports_and_create_edge(grid.ports['grid'], chiller.ports['input'])
system.connect_ports_and_create_edge(chiller.ports['output'], cl)

optimiser = EchoOptimiser(
    interval_duration=interval_duration,
    number_of_intervals=time_periods,
    number_of_expansion_intervals=expansion_periods,
    discount_rate=0,
    ES=system,
    objective_set=None
)

optimiser.objective = sum(getattr(optimiser.model, grid.ports['grid'].port_name)[p, t]
                          for p in optimiser.model.Expansion for t in optimiser.model.Time) * -1

optimiser.optimise(tee=True)

print(optimiser.opt_status)

print('mains: ', optimiser.values(grid.ports['grid'].port_name, 0))
print('chiller input (elec): ', optimiser.values(chiller.ports['input'].port_name, 0))
print('chiller output (cooling): ', optimiser.values(chiller.ports['output'].port_name, 0))
print('cooling load: ', cl.initial_value.values())

print(chiller.get_cop(optimiser))