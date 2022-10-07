
import numpy as np
import pandas as pd

from echo.echo_models import *
from echo.echo_thermal_models import *
from echo.echo_optimiser import *
from echo.objectives import *
from echo.bz_utils import *

time_periods = 8760  # number of intervals - 8760 = 1hr intervals for 1 year
interval_duration = 60  # in minutes
expansion_periods = 1  # no planning periods

# Define an example load profile, add some noise
load_profile = np.array([100] * time_periods) + np.random.normal(0, 20, time_periods)
# Define a pv system size
solar_system_size = 40  # in kW
# Make up some daily profile (this is purely illustrative)
solar_daily_profile = [0]*7 + [0.2]*1 +[0.4]*1 + [0.8]*2 + [1]*2 + [0.8]*2 + [0.4]*1 + [0.2]*1 + [0]*7
# Repeat this profile over a year
solar_profile = np.array(solar_daily_profile * 365) * solar_system_size * -1

# Plot some of this data
fig = plt.figure(figsize=(12,8))
plt.plot(load_profile[0:24])
plt.plot(solar_profile[0:24])
plt.legend(['Load', 'Solar Generation'])
plt.xlabel('Hour')
plt.ylabel('kW')
plt.show()

seasonal_gas_averages = {'Autumn': 409/31/24,
                         'Winter': 910/31/24,
                         'Spring': 340/31/24,
                         'Summer': 196/31/24}  # 2019 hourly seasonal averages for SoM

df = pd.read_csv('../bz_data/gas_profile_soad_som.csv')
gas_load = gas_profiler(seasonal_profile_df=df,
                        season_multiplier=seasonal_gas_averages,
                        start_date="2019-01-01",
                        end_date="2020-01-01")
gas_load.set_index('Timestamp', inplace=True)
# Trim gas load (to be fixed)
gas_profile = gas_load['profile'][:8760]


# Plot the data
fig = plt.figure(figsize=(12,8))
plt.plot(gas_load['profile'].loc['2019-01-01 00:00:00':'2019-01-01 23:00:00'].values) # Jan
plt.plot(gas_load['profile'].loc['2019-04-01 00:00:00':'2019-04-01 23:00:00'].values) # April
plt.plot(gas_load['profile'].loc['2019-07-01 00:00:00':'2019-07-01 23:00:00'].values) # July
plt.plot(gas_load['profile'].loc['2019-09-01 00:00:00':'2019-09-01 23:00:00'].values) # September
plt.xlabel('Hrs')
plt.ylabel('GJ consumed')
plt.legend(['Summer', 'Autumn', 'Winter', 'Spring'])
plt.show()

# Print the total consumption for the year
print('Total annual gas consumption (GJ): ', sum(gas_load['profile'].values))

elec_rate_daily = [0.1]*6 + [0.5]*3 + [0.1]*6 + [0.6]*3 + [0.1]*6 # $/kWh
gas_rate_daily = [17] * 24  # $/GJ


bulk_grid_node = Node(node_name='bulk_grid')  # build a node
bulk_grid_node.add_electrical_port('grid') # add an electrical port to connect to

connection_pt_node = TellegenNode(node_name='elec_cp')  # create a 'summing' node to connect all our assets to
connection_pt_node.add_electrical_ports_from_list(['upstream', 'load', 'battery', 'chiller', 'solar'])  # create a port on this node for each asset we will connect

# Load node
load_node = Node(node_name='elec_load')
load_port = ElectricalDemand()
load_port.add_demand_profile_from_array(load_profile)  # add our load data in kW to this port - it will become a fixed parameter
load_node.ports['load'] = load_port  # add the port to the node

# Solar node
solar_node = Node(node_name='solar_gen')
solar_port = ElectricalGeneration()
solar_port.add_generation_profile_from_array(solar_profile)
solar_node.ports['solar'] = solar_port

# Battery
battery_node = Node(node_name='battery')
battery_size = 100 # kWh storage capacity
charge_limit = 10  # kW charge/discharge limit
battery_port = ElectricalStorage(max_capacity=battery_size,
                       depth_of_discharge_limit=0,
                       charging_power_limit=charge_limit,
                       discharging_power_limit=-charge_limit,
                       charging_efficiency=1,
                       discharging_efficiency=1,
                       initial_state_of_charge=0.0)
battery_node.ports['battery'] = battery_port

# Chiller node
chiller_node = SimpleChiller(node_name='chiller',
                             input_ub=250,
                             output_ub=250) # Rating in kW

# Define pairs of points that maps chiller input to output. These points form a piecewise approx. of a nonlinear function.
input_breakpoints = [0, 150, 200, 220, 250]
output_values = [0, 50, 100, 150, 250]

# Add these points to the chiller object
chiller_node.add_input_pts(input_breakpoints, time_periods=time_periods, expansion_periods=expansion_periods)
chiller_node.add_output_pts(output_values, time_periods=time_periods, expansion_periods=expansion_periods)


# Plot
plt.plot(input_breakpoints, np.array(output_values))
plt.xlabel('Input kW')
plt.ylabel('Output kW')
plt.title('Chiller input/output curve')
plt.show()


# Create a cooling load
cooling_node = Node(node_name='cooling_load')
cooling_port = FixedThermalPort()
cooling_port.add_initial_value_from_array([-100]*time_periods)
cooling_node.ports['cooling load'] = cooling_port

### GAS
# Bulk network node, with a port for emissions
bulk_gas_node = Node(node_name='gas_supply')
emission_factor = 60  # 60 kg Co2e/GJ gas
gas_supply_port = FlexPortExport(units=Units.JPS)
emission_port = FlexPortExport(units=Units.CO2)
bulk_gas_node.ports['gas_supply'] = gas_supply_port
bulk_gas_node.ports['emissions'] = emission_port
t = Transform()
t.add_lhs_term(gas_supply_port, TransformRule.Both, 1)
t.add_rhs_term(emission_port, TransformRule.Both, emission_factor)
bulk_gas_node.add_transformation(t)

# Gas CP node
gas_connection_pt_node = TellegenNode(node_name='gas_cp')
gas_connection_pt_node.add_flex_ports_from_list(['upstream', 'boiler'], unit=Units.JPS)

# Create a gas boiler node
gas_boiler = GasBoilerFixedCOP(node_name='gas_boiler',
                               max_input=100,
                               min_input=0,
                               max_output=-100,
                               min_output=0,
                               cop=0.8)

# Create a heating load
heating_node = Node(node_name='heating_load')
heating_port = FixedThermalPort()
heating_port.add_initial_value_from_array(gas_profile.values, expansion_periods)
heating_node.ports['heating_load'] = heating_port

# Node for aggregating carbon emissions
carbon_agg_node = Node(node_name='carbon_agg')
gas_emissions = CarbonSink()
carbon_agg_node.ports['gas_emissions'] = gas_emissions

# Create an optimisation graph and add all our nodes to the graph
system = OptimisationGraph()
system.add_node_obj([bulk_grid_node, connection_pt_node, solar_node, chiller_node, battery_node,
                     load_node, cooling_node, heating_node, carbon_agg_node, bulk_gas_node, gas_connection_pt_node, gas_boiler])

# Electrical
system.connect_ports_and_create_edge(bulk_grid_node.ports['grid'], connection_pt_node.ports['upstream'])
system.connect_ports_and_create_edge(connection_pt_node.ports['load'], load_node.ports['load'])
system.connect_ports_and_create_edge(connection_pt_node.ports['battery'], battery_node.ports['battery'])
system.connect_ports_and_create_edge(connection_pt_node.ports['solar'], solar_node.ports['solar'])
system.connect_ports_and_create_edge(connection_pt_node.ports['chiller'], chiller_node.ports['input'])
system.connect_ports_and_create_edge(chiller_node.ports['output'], cooling_port)

# Gas
system.connect_ports_and_create_edge(bulk_gas_node.ports['gas_supply'], gas_connection_pt_node.ports['upstream'])
system.connect_ports_and_create_edge(gas_connection_pt_node.ports['boiler'], gas_boiler.ports['input'])
system.connect_ports_and_create_edge(gas_boiler.ports['output'], heating_port)

# CO2
system.connect_ports_and_create_edge(emission_port, gas_emissions)


#fig = plt.figure(figsize=(12,8))
nx.draw_spring(system, with_labels=True)

elec_tariff = ImportTariff(component=connection_pt_node.ports['upstream'],
                           tariff_array=elec_rate_daily*365)

gas_tariff = ImportTariff(component=gas_connection_pt_node.ports['upstream'],
                          tariff_array=gas_rate_daily*365)

# Define a set of objectives
objective_set = ObjectiveSet(objective_list=[elec_tariff, gas_tariff])

optimiser = EchoOptimiser(
    interval_duration=interval_duration,
    number_of_intervals=time_periods,
    number_of_expansion_intervals=expansion_periods,
    discount_rate=0,
    ES=system, # this is our model
    objective_set=objective_set,  # these are our objectives
    profile=None
)

optimiser.optimise(tee=True)  # optimise the example

#print(optimiser.opt_status)
print(max(gas_profile), min(gas_profile))

# Calculate the total emissions over the year
total_emissions = sum(optimiser.values(carbon_agg_node.ports['sum'].port_name))
print('total emissions: ', total_emissions)