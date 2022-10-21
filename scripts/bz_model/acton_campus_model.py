import pandas as pd
import numpy as np
from echo import objectives
import echo.echo_models as models
import echo.echo_builder as builder
import echo.configuration as config
import echo.echo_optimiser as optimiser

df = pd.DataFrame({'bl1_gas_demand': [0.4, 0.5, 0.6, 1.1, 0.8],
                   'bl2_gas_demand': [0.7, 0.8, 1.1, 1.3, 0.9],
                   'bl1_el_demand_net': [7, 8, 10, 8, 11],
                   'bl2_el_demand_power': [5, 5, 6, 9, 7],
                   'bl2_el_demand_chiller': [73, 66, 71, 78, 60]})

feeder_rating_kva = 3.18*1e3
tx_rating_kva = 1000
time_periods = 10


system = models.OptimisationGraph()

## Create Electrical Grid and Gas Grid nodes
gas_grid = models.FlexNodeWithEmissions(node_name='GasGrid',
                                        emitting_port='bulk_gas_source',
                                        emitting_port_units=config.Units.JPS,
                                        carbon_port='bulk_gas_emissions',
                                        emissions_factor=50, ## Assuming 1 GJ of natural gas will produce 50 kg of CO2
                                        )


gas_distribution = models.TellegenNode(node_name='GasGridTellegen',
                                       ports={'gas_grid': models.FlexSink(port_name='grid', units=config.Units.JPS),
                                              'gas_sp01': models.FlexSource(port_name='gas_sp01', units=config.Units.JPS),
                                              'gas_sp02': models.FlexSource(port_name='gas_sp01', units=config.Units.JPS)}
                                       )

gas_sp01 = models.TellegenNode(node_name='GasSupply01',
                               ports={'gas_grid': models.FlexSink(port_name='gas_grid', units=config.Units.JPS),
                                      'bl1_gas_supply': models.FlexSource(port_name='bl1_gas_supply', units=config.Units.JPS)}
                               )

gas_sp02 = models.TellegenNode(node_name='GasSupply02',
                               ports={'gas_grid': models.FlexSink(port_name='gas_grid', units=config.Units.JPS),
                                      'bl2_gas_supply': models.FlexSource(port_name='bl2_gas_supply', units=config.Units.JPS)}
                               )


carbon_aggregation = models.CarbonAggregation(ports={'bulk_gas_emissions': models.CarbonPort()})


bl1_gas_load = models.Node(node_name='B1GasLoad',
                           ports={'bl1_gas_demand': models.Demand(port_name='bl1_gas_demand',
                                                                  units=config.Units.JPS,
                                                                  initial_value_ref='bl1_gas_demand')})

bl2_gas_load = models.Node(node_name='B2GasLoad',
                           ports={'bl2_gas_demand': models.Demand(port_name='bl2_gas_demand',
                                                                  units=config.Units.JPS,
                                                                  initial_value_ref='bl2_gas_demand')})


## Add gas Nodes to Optimisation graph
system.add_nodes_from([gas_grid, gas_distribution, gas_sp01, gas_sp02, carbon_aggregation, bl1_gas_load, bl2_gas_load])


## Gas grid should only export ?
# gas_grid.ports['bulk_gas_source'].flows = config.Flows.Export

electrical_grid = models.FlexElectricalNode(port_name='AvenueFeeder')


## MV Feeder Node
## Set grid port to slack=True
avenue_feeder = models.TellegenNode(node_name='AvenueFeeder',
                                    ports={'grid': models.FlexPort(port_name='grid', units=config.Units.KW,
                                                                   import_constraint=config.FlowConstraint.Fixed,
                                                                   export_constraint=config.FlowConstraint.Fixed,
                                                                   import_constraint_value=feeder_rating_kva,
                                                                   export_constraint_value=-feeder_rating_kva),
                                           's001': models.FlexPort(port_name='s001', units=config.Units.KW),
                                           's002': models.FlexPort(port_name='s002', units=config.Units.KW)})

## Substation (distribution transformer Node)
## Substation has import/export constraints on grid port that equlas its KVA rating
s001 = models.TellegenNode(node_name='Substation001',
                           ports={'feeder': models.FlexPort(port_name='feeder', units=config.Units.KW,
                                                            import_constraint=config.FlowConstraint.Fixed,
                                                            import_constraint_value=tx_rating_kva,
                                                            export_constraint=config.FlowConstraint.Fixed,
                                                            export_constraint_value=-tx_rating_kva),
                                  'bl1_el_supply': models.FlexPort(port_name='bl1_el_supply', units=config.Units.KW),
                                  'bl2_el_supply': models.FlexPort(port_name='bl2_el_supply', units=config.Units.KW)}
                           )


s002 = models.TellegenNode(node_name='Substation002',
                           ports={'feeder': models.FlexPort(port_name='feeder', units=config.Units.KW,
                                                            import_constraint=config.FlowConstraint.Fixed,
                                                            import_constraint_value=tx_rating_kva,
                                                            export_constraint=config.FlowConstraint.Fixed,
                                                            export_constraint_value=-tx_rating_kva),
                                  'bl2_el_supply_chiller': models.FlexPort(port_name='bl2_el_supply_chiller',
                                                                           units=config.Units.KW)}
                           )

bl1_load_net = models.Node(node_name='B1Load',
                       ports={'bl1_el_demand_net': models.FixedElectricalPort(port_name='bl1_el_demand_net',
                                                                               initial_value_ref='bl1_el_demand_net')})


bl2_load_power = models.Node(node_name='B2LoadPower',
                             ports={'bl2_el_demand_power': models.FixedElectricalPort(port_name='bl2_el_demand_power',
                                                                                     initial_value_ref='bl2_el_demand_power')})

bl2_load_chiller = models.Node(node_name='B2LoadChiller',
                               ports={'bl2_el_demand_chiller': models.FixedElectricalPort(port_name='bl2_el_demand_chiller',
                                                                                       initial_value_ref='bl2_el_demand_chiller')})


## Add electrical Nodes to Optimisation graph
system.add_nodes_from([electrical_grid, avenue_feeder, s001, s002, bl1_load_net, bl2_load_power, bl2_load_chiller])



## Multicommodity connection points to represent buildings
bl1_cp = models.Node(node_name='Bld1', node_rule = config.NodeRule.Custom,
                                           ports={'bl1_gas_supply': models.FlexPort(port_name='bl1_gas_supply',
                                                                                    units=config.Units.JPS),
                                                  'bl1_gas_demand': models.FlexPort(port_name='bl1_gas_demand',
                                                                                    units=config.Units.JPS),
                                                  'bl1_el_supply': models.FlexPort(port_name='bl1_el_supply',
                                                                                   units=config.Units.KW),
                                                  'bl1_el_demand_net': models.FlexPort(port_name='bl1_el_demand_net',
                                                                                       units=config.Units.KW)})


bl2_cp = models.MultiCommodityTellegenNode(node_name='Bld2',)








