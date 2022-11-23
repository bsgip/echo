import pandas as pd
from acton_model_bau import *

gas_grid_port = gas_grid.ports['gas_grid'].port_name
co2_aggregation_port = carbon_aggregation.ports['bulk_gas_emissions'].port_name
gas_sp_nodes = [n for n in system.node_obj.values() if 'SP_' in n.node_name]
boiler_nodes = [n for n in system.node_obj.values() if isinstance(n, thermal_models.GasBoilerFixedCOP)]
boiler_nodes = [n for n in system.node_obj.values() if 'Boiler' in n.node_name]
all_boiler_gas_ports = [boiler.ports['input'].port_name for boiler in boiler_nodes]

all_building_nodes = [n for n in system.node_obj.values() if isinstance(n, MultiCommodityTellegenNode)]
all_heating_demand = [n for n in system.node_obj.values() if 'HeatingDemand' in n.node_name]
bl_with_gas = [n for n in all_building_nodes if any(['gas_supply' in port_key for port_key in n.ports])]

el_grid_port = electrical_grid.ports['electrical_grid'].port_name
all_el_demand = [n for n in system.node_obj.values() if 'ElectricalLoad' in n.node_name]
all_el_demand_ports = [p.port_name for n in all_el_demand for p in n.ports.values()]


## Gas flow out of gas grid must equal to inflow of gas distribution
-results_df[gas_grid_port].sum() == results_df[gas_distribution.ports['gas_grid'].port_name].sum()

## Inflow==Outflow for gas distribution
round(sum([results_df[_p.port_name].sum() for _p in gas_distribution.ports.values()]), 5)==0

for sp_node in gas_sp_nodes:
      if round(sum([results_df[_p.port_name].sum() for _p in sp_node.ports.values()]), 5) != 0:
            print(f'{sp_node.node_name} port values dont sum up to zero')


## Verify that Individual gas boiler consumptions sum up to total gas supplied from Gas mai

print(f'Individual gas boiler consumptions sum up to total gas supplied from Gas main: '
      f'{round(results_df[gas_grid_port ].sum()+sum([results_df[boiler_port].sum() for boiler_port in all_boiler_gas_ports]), 5) ==0}')

print(f'Total CO2 emissions calculated matches total gas consumed: '
      f'{round(results_df[carbon_aggregation.ports["bulk_gas_emissions"].port_name].sum()+results_df[gas_grid.ports["gas_grid"].port_name].sum()*emission_factor, 5)==0}')



## Verify boiler output/input == cop
round(- sum([results_df[n.ports['output'].port_name].sum() for n in boiler_nodes])/sum([results_df[n.ports['input'].port_name].sum() for n in boiler_nodes]), 3) == 0.85

## Gas outflow from all building Nodes == input to all boilers
sum([results_df[n.ports['input'].port_name].sum() for n in boiler_nodes]) == \
-sum([results_df[n.ports[f'{n.node_name[1:]}_gas_demand'].port_name].sum() for n in bl_with_gas])

## Gas POrt flows for each building sum up to zero
for n in bl_with_gas:
      gas_ports = [v.port_name for k,v in n.ports.items() if 'gas' in k]
      if round(sum([results_df[_p].sum() for _p in gas_ports]), 5) != 0:
            print(f'{n.node_name} gas port values dont sum up to zero')



for sp_id, bl_list in gas_supply_points_dict.items():
    if sp_id == 'no_gas':
        continue
    sp_node = system.node_obj.get(f'SP_{sp_id}', None)
    total_gas_supplied = sum([results_df[sp_node.ports[f'{bl_id}_gas_supply'].port_name].sum() for bl_id in bl_list])
    bl_nodes = [system.node_obj.get(f'B{bl_id}') for bl_id in bl_list]
    bl_gas_ports = [n.ports[f'{sp_id}_gas_supply'].port_name for n in bl_nodes]
    if len(bl_nodes)!=len(bl_gas_ports):
          print(f'Not all bld have gas ports: {bl_list} for sp {sp_id}')
    total_gas_received = sum([results_df[_p].sum() for _p in bl_gas_ports])
    if round(total_gas_supplied+total_gas_received,5)!=0:
          print(f'sp {sp_id} total supplied {total_gas_supplied}, total received {total_gas_received}')




print(f'Individual electrical demand sum up to total electricity supplied from ELectrical Grid: '
      f'{round(results_df[el_grid_port].sum()+sum([results_df[el_port].sum() for el_port in all_el_demand_ports]), 5) ==0}')
