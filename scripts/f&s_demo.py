import numpy as np
import pandas as pd

from echo.echo_models import *
from echo.echo_optimiser import *
from echo.objectives import *
from echo.bz_utils import *

time_periods = 8760  # number of intervals
interval_duration = 60  # in minutes
expansion_periods = 1  # no planning periods

load_profile = [100] * time_periods
solar_system_size = 40  # system size in kW
solar_daily_profile = [0]*7 + [0.2]*1 +[0.4]*1 + [0.8]*2 + [1]*2 + [0.8]*2 + [0.4]*1 + [0.2]*1 + [0]*7
solar_profile = np.array(solar_daily_profile * 365) * solar_system_size * -1
plt.plot(solar_profile[0:24])

seasonal_gas_averages = {'Autumn': 409/31/24,
                         'Winter': 910/31/24,
                         'Spring': 340/31/24,
                         'Summer': 196/31/24}  # 2019 hourly seasonal averages for SoM

df = pd.read_csv('../bz_data/gas_profile_soad_som.csv')
gas_load = gas_profiler(seasonal_profile_df=df,
                        season_multiplier=seasonal_gas_averages,
                        start_date="2019-01-01",
                        end_date="2020-01-01")

# Trim gas load (to be fixed)
gas_profile = gas_load['profile'][:8760]

# Retail energy tariffs ($/kWh)
elec_tariff_array_day = [0.3]*8 + [0.5]*2 + [0.3]*8 + [0.7]*3 + [0.3]*3

# Gas tariff
gas_tariff_array_day = [17] * 24  # in $/GJ

emission_factor = 60  # 60 kg Co2e/GJ gas

bulk_grid_node = Node()  # build a node
bulk_grid_node.add_electrical_port('grid') # add an electrical port to connect to

connection_pt_node = TellegenNode()  # create a 'summing' node to connect all our assets to
connection_pt_node.add_electrical_ports_from_list(['upstream', 'load', 'battery', 'chiller', 'solar'])  # create a port on this node for each asset we will connect

# Load node
load_node = Node()
load_port = ElectricalDemand()
load_port.add_demand_profile_from_array(load_profile)  # add our load data in kW to this port - it will become a fixed parameter
load_node.ports['load'] = load_port  # add the port to the node

# Chiller node
chiller_node = Node()
temp_port = ElectricalDemand()
temp_port.add_demand_profile_from_array([0]*time_periods)
chiller_node.ports['input'] = temp_port
# chiller_node = Chiller(max_output=-250,
#                        max_input=250) # Rating in kW
#
# # Define points on our piecewise function that maps chiller input to output.
# input_breakpoints = [0, 150, 200, 220, 250]
# output_values = [0, -50, -100, -150, -250]
#
# chiller_node.set_input_output_breakpoints(input_array=input_breakpoints,
#                                           output_array=output_values,
#                                           time_periods=time_periods,
#                                           expansion_periods=expansion_periods)

# Solar node
solar_node = Node()
solar_port = ElectricalGeneration()
solar_port.add_generation_profile_from_array(solar_profile)
solar_node.ports['solar'] = solar_port

# Battery
battery_node = Node()
battery_size = 100 # kWh storage capacity
charge_limit = 10  # kW
battery_port = ElectricalStorage(max_capacity=battery_size,
                       depth_of_discharge_limit=0,
                       charging_power_limit=charge_limit,
                       discharging_power_limit=-charge_limit,
                       charging_efficiency=1,
                       discharging_efficiency=1,
                       initial_state_of_charge=0.0)
battery_node.ports['battery'] = battery_port


### GAS

# Bulk network node, with a port for emissions

bulk_gas_node = Node()
bulk_gas_node.add_flex_port('gas_supply', unit=Units.JPS)
# bulk_gas_node.add_flex_port('emissions', unit=Units.CO2)
# bulk_gas_node.add_emission_transformation(emitting_port=bulk_gas_node.ports['gas_supply'],
#                                           carbon_port=bulk_gas_node.ports['emissions'],
#                                           emission_factor=emission_factor)

# Gas CP node
gas_connection_pt_node = TellegenNode()
gas_connection_pt_node.add_flex_ports_from_list(['upstream', 'load'], unit=Units.JPS)

gas_load_node = Node()
gas_load_port = GasDemand()
gas_load_port.add_sink_profile_from_array(gas_profile)
gas_load_node.ports['load'] = gas_load_port

# # Node for aggregating carbon emissions
# carbon_agg_node = CarbonAggregation()
# carbon_agg_node.add_flex_port('gas_emissions', unit=Units.CO2)
# carbon_agg_node.add_aggregation_transformation()

# Create an optimisation graph and add all our nodes to the graph
system = OptimisationGraph()
system.add_node_obj([bulk_grid_node, gas_connection_pt_node, connection_pt_node, solar_node, chiller_node, battery_node, load_node, gas_load_node, bulk_gas_node])


# Electrical
system.connect_ports_and_create_edge(bulk_grid_node.ports['grid'], connection_pt_node.ports['upstream'])
system.connect_ports_and_create_edge(connection_pt_node.ports['load'], load_node.ports['load'])
system.connect_ports_and_create_edge(connection_pt_node.ports['battery'], battery_node.ports['battery'])
system.connect_ports_and_create_edge(connection_pt_node.ports['solar'], solar_node.ports['solar'])
system.connect_ports_and_create_edge(connection_pt_node.ports['chiller'], chiller_node.ports['input'])

# Gas
system.connect_ports_and_create_edge(bulk_gas_node.ports['gas_supply'], gas_connection_pt_node.ports['upstream'])
system.connect_ports_and_create_edge(gas_connection_pt_node.ports['load'], gas_load_node.ports['load'])

# CO2
#system.connect_ports_and_create_edge(bulk_gas_node.ports['emissions'], carbon_agg_node.ports['gas_emissions'])


elec_tariff = ImportTariff(component=connection_pt_node.ports['upstream'],
                           tariff_array=np.array(elec_tariff_array_day * 365))

gas_tariff = ImportTariff(component=gas_connection_pt_node.ports['upstream'],
                          tariff_array=np.array(gas_tariff_array_day * 365))


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

print(optimiser.opt_status)

## Plot the optimised connection point
opt_cp = optimiser.values(connection_pt_node.ports['upstream'].port_name)
plt.plot(opt_cp)
plt.show()