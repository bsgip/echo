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
from read_datafiles import gas_supply_points_dict, bld_to_model, electrical_feeders, bl_substations, bld_not_included, substations_bl
from bz_model_constants import *
from custom_classes import MultiCommodityTellegenNodeManual, MultiCommodityTellegenNode
from graph_plotting_utils import *
from tariffs_and_costs import *
from collections import defaultdict



## Initialise system
system = models.OptimisationGraph()


## Add Bulk Gas grid , Gas distribution Node and carbon aggregation nodes
gas_grid = models.FlexNodeWithEmissions(node_name='GasGrid',
                                        emitting_port='gas_grid',
                                        emitting_port_units=config.Units.JPS,
                                        carbon_port='bulk_gas_emissions',
                                        emissions_factor= emission_factor)

carbon_aggregation = models.CarbonAggregation(node_name='BulkEmissions',
                                              ports={'bulk_gas_emissions': models.CarbonPort()})


## Create a Gas distribution tellegen node with ports for each supply point (metering point) and gas grid port
gas_distribution_ports = {f'supply_point_{sp_id}': models.FlexSink(units=config.Units.JPS)
                          for sp_id in gas_supply_points_dict.keys() if sp_id!='no_gas'}
gas_distribution_ports['gas_grid'] = models.FlexSink(units=config.Units.JPS)
gas_distribution = models.TellegenNode(node_name='GasGridTellegen',
                                       ports=gas_distribution_ports)

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
    system.add_node(models.TellegenNode(node_name=f'supply_point_{sp_id}', ports=ports))
    new_node = system.node_obj.get(f'supply_point_{sp_id}', None)
    system.connect_ports_and_create_edge(gas_distribution.ports[f'supply_point_{sp_id}'], new_node.ports['gas_distribution'],
                                         edge_name=f'{gas_distribution.node_name}_{new_node.node_name}')

## Varify that system size increased by exactly the number of keys in gas_supply_points_dict
try:
    assert (len(system.node_obj)-len(gas_supply_points_dict))==start_system_size
except AssertionError as msg:
    print(f'{len(gas_supply_points_dict)} gas supply point, '
          f'but only {len(system.node_obj)-len(gas_supply_points_dict)} nodes added to the system' )


electrical_grid = models.FlexElectricalNode(node_name = 'ElectricGrid', port_name='to_avenue')





######################
#############Name format for campus model

## Gas supply point
## f'supply_point_{sp_id}'

## f'{bl_id}_gas_supply'
