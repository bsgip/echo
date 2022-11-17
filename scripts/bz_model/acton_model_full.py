import pandas as pd
import numpy as np
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

## Initialise system
system = models.OptimisationGraph()


## Add Bulk Gas grid , Gas distribution Node and carbon aggregation nodes
gas_grid = models.FlexNodeWithEmissions(node_name='GasGrid',
                                        emitting_port='gas_grid',
                                        emitting_port_units=config.Units.JPS,
                                        carbon_port='bulk_gas_emissions',
                                        emissions_factor=emission_factor)

carbon_aggregation = models.CarbonAggregation(node_name='BulkEmissions',
                                              ports={'bulk_gas_emissions': models.CarbonPort()})


## Create a Gas distribution tellegen node with ports for each supply point (metering point) and gas grid port
gas_distribution_ports = {f'supply_point_{sp_id}': models.FlexSource(units=config.Units.JPS)
                          for sp_id in gas_supply_points_dict.keys() if sp_id!='no_gas'}

gas_distribution_ports['gas_grid'] = models.FlexSink(units=config.Units.JPS)
gas_distribution = models.TellegenNode(node_name='GasDistribution', ports=gas_distribution_ports)

## Connect Gas Grid to Carbon aggregation and Gas distribution
system.add_nodes_from([gas_grid, gas_distribution, carbon_aggregation])

system.connect_ports_and_create_edge(gas_grid.ports['gas_grid'], gas_distribution.ports['gas_grid'],
                                     edge_name=f'{gas_grid.node_name}_{gas_distribution.node_name}')

system.connect_ports_and_create_edge(gas_grid.ports['bulk_gas_emissions'], carbon_aggregation.ports['bulk_gas_emissions'],
                                     edge_name=f'{gas_grid.node_name}_{carbon_aggregation.node_name}')

start_system_size = len(system.node_obj)
## Add gas supply points nodes with ports for all buildings downstream, connect all gas supply points to Gas distribution
for sp_id, bl_list in gas_supply_points_dict.items():
    if sp_id=='no_gas':
        continue
    ports = {f'{bl_id}_gas_supply': models.FlexSource(units=config.Units.JPS) for bl_id in bl_list}
    ports['gas_distribution'] = models.FlexSink(units=config.Units.JPS)
    system.add_node(models.TellegenNode(node_name=f'SP_{sp_id}', ports=ports))
    new_node = system.node_obj.get(f'SP_{sp_id}', None)
    system.connect_ports_and_create_edge(gas_distribution.ports[f'supply_point_{sp_id}'], new_node.ports['gas_distribution'],
                                         edge_name=f'{gas_distribution.node_name}_{new_node.node_name}')

## Varify that system size increased by exactly the number of keys in gas_supply_points_dict
try:
    assert (len(system.node_obj)-len([i for i in gas_supply_points_dict if i!='no_gas']))==start_system_size
except AssertionError as msg:
    print(f'{len([i for i in gas_supply_points_dict if i!="no_gas"])} gas supply point, '
          f'but only {len(system.node_obj)-start_system_size} nodes added to the system' )



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
    if len(bl_gas_sp[bl_id])!=1:
        print(f'Building {bl_id} has {len(bl_gas_sp[bl_id])} gas supply points')
    sp_id = bl_gas_sp[bl_id][0]
    gas_ports = {}
    if sp_id!='no_gas':
        ## Create gas Ports for the building if it has gas supply
        gas_ports = {f'{sp_id}_gas_supply': models.FlexPort(units=config.Units.JPS),
                     f'{bl_id}_gas_demand': models.FlexPort(units=config.Units.JPS)}
        ports.update(gas_ports)
        ## Create and add GasBoiler node for each building that has gas supply
        system.add_node(thermal_models.GasBoilerFixedCOP(node_name=f'Boiler_{bl_id}', cop=boiler_cop,
                                                         startup_cop=boiler_startup_cop,
                                                         min_input=boiler_min_input, max_input=boiler_max_input))
        ## Create and add thermal demand Node for each bld with gas supply
        system.add_node(models.Node(node_name=f'HeatingDemand_{bl_id}',
                                    ports={f'{bl_id}_heating_demand': models.Demand(units=config.Units.KWT,
                                                                                    initial_value_ref=th_reference)}))
        ## Connect Boiler output to Heating demand
        boiler_node = system.node_obj.get(f'Boiler_{bl_id}', None)
        demand_node = system.node_obj.get(f'HeatingDemand_{bl_id}', None)
        system.connect_ports_and_create_edge(boiler_node.ports['output'],
                                             demand_node.ports[f'{bl_id}_heating_demand'],
                                             edge_name=f'{boiler_node.node_name}_{demand_node.node_name}')
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
    for sub_id in sub_list:
        sub_node = system.node_obj.get(f'Substation_{sub_id}', None)
        system.connect_ports_and_create_edge(sub_node.ports[f'to_{bl_id}'],
                                             new_node.ports[f'{sub_id}_electrical_supply'],
                                             edge_name=f'{sub_node.node_name}_{new_node.node_name}')
    if gas_ports:
        gas_node = system.node_obj.get(f'SP_{sp_id}', None)
        system.connect_ports_and_create_edge(gas_node.ports[f'{bl_id}_gas_supply'],
                                             new_node.ports[f'{sp_id}_gas_supply'],
                                             edge_name=f'{gas_node.node_name}_{new_node.node_name}')
        system.connect_ports_and_create_edge(new_node.ports[f'{bl_id}_gas_demand'],
                                             boiler_node.ports['input'],
                                             edge_name=f'{new_node.node_name}_{boiler_node.node_name}')





# Plot system Graph colored by commodity

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

ports = ports_dict(system)
optimiser_object = optimiser.EchoOptimiser(interval_duration=interval_duration,
                          number_of_intervals=time_periods,
                          number_of_expansion_intervals=expansion_periods,
                          discount_rate=discount_rate,
                          ES=system,
                          objective_set=None,
                          profile=source_df)


optimiser_object.optimise(tee=True)

results_df = optimiser_object.df()

######################
#############Name format for campus model

## Gas supply point
## f'supply_point_{sp_id}'
## f'SP_{sp_id}'

## f'{bl_id}_gas_supply'


### Electrical supply
## f'feeder_{f_id}'
## f'{sub_id}_substation'
