import pandas as pd
import numpy as np
import networkx as nx
from echo import objectives
import echo.echo_models as models
import echo.echo_thermal_models as thermal_models
import echo.echo_builder as builder
import echo.configuration as config
import echo.echo_optimiser as optimiser
import echo.utils as utils
import pyomo.environ as en


########### local imports ###############
from read_datafiles import bl_with_meters, kambri_central, central_plant, source_df, extra_gas_supply
from read_datafiles import gas_supply_points_dict, bld_to_model, electrical_feeders, \
    bl_substations, bld_not_included, substations_bl, substations_feeders, bl_gas_sp
from read_datafiles import time_periods, interval_duration, expansion_periods, discount_rate
from bz_model_constants import *
from custom_classes import MultiCommodityTellegenNodeManual, MultiCommodityTellegenNode
from graph_plotting_utils import *
from tariffs_and_costs import *
from collections import defaultdict


from model_validation import check_port_names_unique, ports_dict



### Use 'flat' model for Kambri and Central Plants (can attach thermal and electrical demand to account for losses)

kambri_id = '151'
central_id = '135'
zero_demand = {kambri_id, central_id}


heating_cop_dict = utils.generate_dict_with_pyomo_keys_from_array(source_df.heating_cop, time_periods)
cooling_cop_dict = utils.generate_dict_with_pyomo_keys_from_array(source_df.cooling_cop, time_periods)

## Initialise system
system = models.OptimisationGraph()


########## Add Electrical grid
electrical_grid = models.FlexElectricalNode(node_name = 'ElectricGrid', port_name='electrical_grid')

electrical_distribution_ports = {f'feeder_{f_id}': models.FlexPort(units=config.Units.KW)
                                 for f_id in electrical_feeders.keys()}

electrical_distribution_ports['electrical_grid'] = models.FlexPort(units=config.Units.KW)
electrical_distribution = models.TellegenNode(node_name='ElectricDistribution', ports=electrical_distribution_ports)

## Connect Gas Grid to Carbon aggregation and Gas distribution
system.add_nodes_from([electrical_grid, electrical_distribution])
system.connect_ports_and_create_edge(electrical_grid.ports['electrical_grid'], electrical_distribution.ports['electrical_grid'],
                                     edge_name=f'{electrical_grid.node_name}_{electrical_distribution.node_name}')

start_system_size = len(system.node_obj)
for f_id, sub_list in electrical_feeders.items():
    ports = {f'{sub_id}_substation': models.FlexPort(units=config.Units.KW) for sub_id in sub_list}
    ports['electrical_distribution'] = models.FlexPort(units=config.Units.KW)
    system.add_node(models.TellegenNode(node_name=f'Feeder_{f_id}', ports=ports))
    new_node = system.node_obj.get(f'Feeder_{f_id}', None)
    system.connect_ports_and_create_edge(electrical_distribution.ports[f'feeder_{f_id}'],
                                         new_node.ports['electrical_distribution'],
                                         edge_name=f'{electrical_distribution.node_name}_{new_node.node_name}')

## Varify that system size increased by exactly the number of keys in electrical_feeders
try:
    assert (len(system.node_obj)-len(electrical_feeders))==start_system_size
except AssertionError as msg:
    print(f'{len(electrical_feeders)} electrical Feeders, '
          f'but only {len(system.node_obj)-start_system_size} nodes added to the system' )


start_system_size = len(system.node_obj)

for sub_id, bl_list in substations_bl.items():
    ports = {f'to_{bl_id}': models.FlexPort(units=config.Units.KW) for bl_id in bl_list}
    ports_to_feeders= {f'feeder_{f_id}': models.FlexPort(units=config.Units.KW) for f_id in substations_feeders[sub_id]}
    ports.update(ports_to_feeders)
    system.add_node(models.TellegenNode(node_name=f'Substation_{sub_id}', ports=ports))
    new_node = system.node_obj.get(f'Substation_{sub_id}', None)
    for f_id in substations_feeders[sub_id]:
        feeder_node = system.node_obj.get(f'Feeder_{f_id}', None)
        system.connect_ports_and_create_edge(feeder_node.ports[f'{sub_id}_substation'],
                                         new_node.ports[f'feeder_{f_id}'],
                                         edge_name=f'{feeder_node.node_name}_{new_node.node_name}')


## Varify that system size increased by exactly the number of keys in substations_bl
try:
    assert (len(system.node_obj)-len(substations_bl))==start_system_size
except AssertionError as msg:
    print(f'{len(substations_bl)} electrical Substations, '
          f'but only {len(system.node_obj)-start_system_size} nodes added to the system' )



### Create MultiCommodityTellegen Node for each building, add electrical and gas loads

for bl_id, sub_list in bl_substations.items():
    if bl_id in zero_demand:
        el_reference = 'zero_demand'
        th_reference = 'zero_demand'
    else:
        el_reference = 'bl_el_demand_net'
        th_reference = 'bl_heating_demand'
    ports = {f'{sub_id}_electrical_supply': models.FlexPort(units=config.Units.KW) for sub_id in sub_list}
    ports[f'{bl_id}_electrical_demand']= models.FlexPort(units=config.Units.KW)
    if bl_id in gas_supply_points_dict['no_gas']:
        electrical_heating_port = {}
    else:
        ## Create an additional electrical port for HeatPump connection
        electrical_heating_port = {'to_heatpump': models.FlexPort(units=config.Units.KW)}
        ports.update(electrical_heating_port)
        ## Create and add HeatPump node for each building that has gas supply in BAU model
        system.add_node(thermal_models.HeatPumpSingleOutput(node_name=f'HeatPump_{bl_id}',
                                                            heating_cop_time_series=heating_cop_dict,
                                                            cooling_cop_time_series=cooling_cop_dict))
        ## Create and add thermal demand Node for each bld with gas supply
        system.add_node(models.Node(node_name=f'HeatingDemand_{bl_id}',
                                    ports={f'{bl_id}_heating_demand': models.Demand(units=config.Units.KWT,
                                                                                    initial_value_ref=th_reference)}))
        ## Connect HeatPump output to Heating demand
        heatpump_node = system.node_obj.get(f'HeatPump_{bl_id}', None)
        demand_node = system.node_obj.get(f'HeatingDemand_{bl_id}', None)
        system.connect_ports_and_create_edge(heatpump_node.ports['output'],
                                             demand_node.ports[f'{bl_id}_heating_demand'],
                                             edge_name=f'{heatpump_node.node_name}_{demand_node.node_name}')
    ## add MultiCommodityTellegen Node to represent the building
    system.add_node(MultiCommodityTellegenNode(node_name=f'B{bl_id}', node_rule = config.NodeRule.Custom, ports = ports))
    ## Create an Electrical demand Node for each building
    system.add_node(models.Node(node_name=f'ElectricalLoad_{bl_id}',
                                ports={f'{bl_id}_electrical_demand':
                                           models.FixedElectricalPort(initial_value_ref=el_reference)}))
    ## Connect building to electrical demand
    el_demand = system.node_obj.get(f'ElectricalLoad_{bl_id}', None)
    new_node = system.node_obj.get(f'B{bl_id}', None)
    system.connect_ports_and_create_edge(new_node.ports[f'{bl_id}_electrical_demand'],
                                         el_demand.ports[f'{bl_id}_electrical_demand'],
                                         edge_name=f'{new_node.node_name}_{el_demand.node_name}')
    if len(electrical_heating_port):
        system.connect_ports_and_create_edge(new_node.ports['to_heatpump'],
                                             heatpump_node.ports['input'],
                                             edge_name=f'{new_node.node_name}_{heatpump_node.node_name}')
    for sub_id in sub_list:
        sub_node = system.node_obj.get(f'Substation_{sub_id}', None)
        system.connect_ports_and_create_edge(sub_node.ports[f'to_{bl_id}'],
                                             new_node.ports[f'{sub_id}_electrical_supply'],
                                             edge_name=f'{sub_node.node_name}_{new_node.node_name}')


# Plot system Graph colored by commodity
g = nx_graph_with_colors(system)
nx.is_connected(g)

commodity_colors = {'KW': 'green',
                   'CO2':'orange',
                   'KWT':'yellow',
                   'JPS': 'blue',
                   'KWh': 'green',
                   'kVA': 'green',
                   'kVAR': 'green',
                   'LPS': 'green',
                   'NA': 'grey'}
## plot_echo_graph_with_colors(system, commodity_colors=commodity_colors)

check_port_names_unique(system)
ports = ports_dict(system)

optimiser_object = optimiser.EchoOptimiser(interval_duration=interval_duration,
                          number_of_intervals=time_periods,
                          number_of_expansion_intervals=expansion_periods,
                          discount_rate=discount_rate,
                          ES=system,
                          objective_set=None,
                          profile=source_df)


optimiser_object.optimise(tee=True)

results_hp_df = optimiser_object.df()

