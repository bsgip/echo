from echo.configuration import Units, FlowConstraint
from echo.models.agnostic import FlexPort, TellegenNode, Source, InputOutputNode, Demand, Storage
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import Inverter, ElectricalGeneration
from echo.models.carbon import CarbonAggregation, CarbonPort

from echo.models.prebuilt import Battery, FlexNodeWithEmissions, Electrolyser
from echo.objectives.tariff import ImportTariff, ExportTariff
from echo.objectives.base import ObjectiveSet
from echo.optimiser import optimise
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment

import pandas as pd
source_df = pd.read_csv("scripts/manual_examples/Dataframe.csv")
source_df["Hydrogen load"] = 5*60*60  # 5kg per second
source_df["Wind"] = -100000
source_df["Solar"] *= -1
grid_emission_factor = source_df["Carbon intensity"]
test_battery_size = 100e3  # kWh
electrolyser_cop = 1/39.4  # kWh of electricity to 1 kg of Hydrogen
electrolyser_max_input = 1750162  # kW max input
h2_storage_capacity = 10003211 # kg

# Instantiate echo Optimisation Graph
system = OptimisationGraph()

# Node representing connection to Electrical Grid, per each kW of electricity flowing through 'grid' port
# carbon port emits CO2_tonne = N_kW_ti*emissions_factor_ti
electrical_grid = FlexNodeWithEmissions(node_name='ElectricalGrid',
                                       emitting_port='grid',
                                       emitting_port_units=Units.KW,
                                       carbon_port='grid_emissions',
                                       emissions_factor=grid_emission_factor)
#
# electrical_grid.add_emission_offset(emitting_port='grid',
#                                     carbon_port='grid_emissions',
#                                     emission_factor= grid_emission_factor)

# Carbon aggregation Node stores all emissions produced over simulation period
carbon_aggregation = CarbonAggregation(node_name='BulkEmissions',
                                       ports={'bulk_grid_emissions': CarbonPort()})

# Define all port for electrical connection point, omitting DC/AC Inverter model for now
electrical_cp_ports = {'CP_grid': FlexPort(units=Units.KW,
                                           export_constraint=FlowConstraint.Fixed,
                                           export_constraint_value= -100000),
                       'CP_solar': FlexPort(units=Units.KW),
                        'CP_wind': FlexPort(units=Units.KW),
                       'CP_battery': FlexPort(units=Units.KW),
                       'CP_electrolyser': FlexPort(units=Units.KW)}


# Electrical connection point, all flows sum to zero, no additional constraints defined
connection_point = TellegenNode(node_name='ConnectionPoint', ports=electrical_cp_ports)

# Create Solar generation node, initial_value_ref here set to the name of DataFrame column with PV output
solar = Node(node_name='BulkSolar',
             ports={'solar': ElectricalGeneration(units=Units.KW,
                                                  initial_value_ref='Solar',
                                                  curtailable=False)})

wind = Node(node_name='BulkWind',
            ports={'wind': ElectricalGeneration(units=Units.KW,
                                                 initial_value_ref='Wind',
                                                 curtailable=False)})

# Create electric battery Node
battery = Battery(node_name='Battery',
                  port_name='battery',
                  max_capacity=test_battery_size,
                  initial_state_of_charge=0,
                  charging_power_limit=0.5 *test_battery_size,
                  discharging_power_limit=-0.5 * test_battery_size,
                  storage_capacity_cost=None,
                  charging_efficiency=1,
                  discharging_efficiency=1,
                  depth_of_discharge_limit=0,
                  fixed_storage_capacity=True)


# Electrolyser model
electrolyser = Electrolyser(node_name='Electrolyser',
                               input_port_unit=Units.KW,
                               output_port_unit=Units.H2Kg,
                               max_input=electrolyser_max_input)

hydrogen_load = Node(node_name='H2Demand',
                     ports={f'h2_demand': Demand(units=Units.H2Kg,
                                                 initial_value_ref='Hydrogen load')})


hydrogen_cp_ports = {'CP_electrolyser': FlexPort(units=Units.H2Kg),
                    'CP_load': FlexPort(units=Units.H2Kg),
                    'CP_storage': FlexPort(units=Units.H2Kg)}


# Hydrogen connection point, all flows sum to zero, no additional constraints defined
hydrogen_connection_point = TellegenNode(node_name='H2ConnectionPoint', ports=hydrogen_cp_ports)


hydrogen_storage = Node(node_name ="H2Storage",
                        ports = {'h2_storage_port': Storage( units = Units.H2Kg,
                                                             max_capacity =h2_storage_capacity,
                                                             charging_power_limit = h2_storage_capacity,
                                                             discharging_power_limit = -1*h2_storage_capacity,
                                                             initial_state_of_charge =0)})


## Add all the Nodes to the Optimisation GRaph
system.add_nodes_from([electrical_grid, carbon_aggregation, connection_point,
                       solar, wind, battery, electrolyser, hydrogen_load, hydrogen_connection_point, hydrogen_storage])

system.connect_ports_and_create_edge(electrical_grid.ports['grid_emissions'],
                                     carbon_aggregation.ports['bulk_grid_emissions'],
                                     edge_name=f'{electrical_grid.node_name}_{carbon_aggregation.node_name}')
system.connect_ports_and_create_edge(electrical_grid.ports['grid'],
                                     connection_point.ports['CP_grid'],
                                     edge_name=f'{electrical_grid.node_name}_{connection_point.node_name}')
system.connect_ports_and_create_edge(solar.ports['solar'],
                                     connection_point.ports['CP_solar'],
                                     edge_name=f'{solar.node_name}_{connection_point.node_name}')
system.connect_ports_and_create_edge(wind.ports['wind'],
                                     connection_point.ports['CP_wind'],
                                     edge_name=f'{wind.node_name}_{connection_point.node_name}')
system.connect_ports_and_create_edge(battery.ports['battery'],
                                     connection_point.ports['CP_battery'],
                                     edge_name=f'{battery.node_name}_{connection_point.node_name}')
system.connect_ports_and_create_edge(electrolyser.ports['input'],
                                     connection_point.ports['CP_electrolyser'],
                                     edge_name=f'{electrolyser.node_name}_{connection_point.node_name}')
system.connect_ports_and_create_edge(electrolyser.ports['output'],
                                     hydrogen_connection_point.ports['CP_electrolyser'],
                                     edge_name=f'{electrolyser.node_name}_{hydrogen_connection_point.node_name}')
system.connect_ports_and_create_edge(hydrogen_storage.ports['h2_storage_port'],
                                     hydrogen_connection_point.ports['CP_storage'],
                                     edge_name=f'{hydrogen_storage.node_name}_{hydrogen_connection_point.node_name}')
system.connect_ports_and_create_edge(hydrogen_load.ports['h2_demand'],
                                     hydrogen_connection_point.ports['CP_load'],
                                     edge_name=f'{hydrogen_load.node_name}_{hydrogen_connection_point.node_name}')


system.draw_echo_graph(with_labels=True)



import_cost = ImportTariff(component=connection_point.ports['CP_grid'],
                               tariff_array=source_df['Prices']*1e-3,
                               expansion_periods=1)  # create the import objective cost
export_cost = ExportTariff(component=connection_point.ports['CP_grid'],
                               tariff_array=source_df['Prices']*1e-3,
                               expansion_periods=1)  # create the export objective cost
objective_set = ObjectiveSet(objective_list=[import_cost, export_cost])

optimise_results = optimise(
    scenario_settings=ScenarioSettings(
        interval_duration=60,
        number_of_intervals=len(source_df.index),
        number_of_expansion_intervals=1,
        discount_rate=0
    ),
    engine_settings=engine_settings_from_environment(),
    graph=system,
    objective_set=objective_set,
    profile=source_df
)

result_df = optimise_results.df_by_port()
result_df_raw = optimise_results.df()

solar_port = solar.ports['solar']
wind_port = solar.ports['solar']


(source_df.Solar.values - result_df.solar.values).sum()
(source_df.Wind.values - result_df.wind.values).sum()


