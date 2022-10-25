import pandas as pd
import numpy as np
from echo import objectives
import echo.echo_models as models
import echo.echo_builder as builder
import echo.configuration as config
import echo.echo_optimiser as optimiser
import pyomo.environ as en
import networkx as nx
import matplotlib.pyplot as plt



df = pd.DataFrame({'bl1_gas_demand': [0.4, 0.5, 0.6, 1.1, 0.8],
                   'bl2_gas_demand': [0.7, 0.8, 1.1, 1.3, 0.9],
                   'bl1_el_demand_net': [7, 8, 10, 8, 11],
                   'bl2_el_demand_power': [5, 5, 6, 9, 7],
                   'bl2_el_demand_chiller': [73, 66, 71, 78, 60],
                   'ambient_temp': [18, 19, 19, 21, 21],
                   'bl1_heating_demand': [283, 255, 264, 263, 276],
                   'bl1_cooling_demand': [387.4, 437.5, 481.0, 549.1, 569.3],
                   'bl2_heating_demand': [283, 255, 264, 263, 276],
                   'bl2_cooling demand': [387.4, 437.5, 481.0, 549.1, 569.3]})

feeder_rating_kva = 3.18*1e3
tx_rating_kva = 1000
time_periods = 5
interval_duration = 60 ## in minutes
expansion_periods = 1
discount_rate = 0



class MultiCommodityTellegenNodeManual(models.MultiCommodityTellegenNode):
    """ Specify subgroups of Ports to which Tellegen constraint appies"""
    tellegen_ports_dict: dict = None
    if tellegen_ports_dict:
        def apply_node_constraints(self, model):
            def reliability(model, p, t):
                a = 0
                for port in tellegen_ports:
                    b = getattr(model, port.port_name)
                    a += b[p, t]
                    return a == 0
            for k, v in self.tellegen_ports_dict.items():
                tellegen_ports = [self.ports.get(i) for i in v]
                setattr(model, 'node_con_' + str(k) + self.node_name, en.Constraint(model.Expansion, model.Time, rule=reliability))


def nx_graph_with_colors(echo_system) -> nx.graph:
    g = nx.Graph()
    for _n in echo_system.node_obj.values():
        g.add_node(_n.node_name, commodity=node_commodity(_n))
    for _e in echo_system.edge_obj:
        g.add_edge(*_e, commodity=system.edge_obj[_e].vertices[0].units.name)
    return g

def node_commodity(echo_node)-> str:
    port_commodities = [p.units.name for p in echo_node.ports.values()]
    if len(set(port_commodities))==1:
        return port_commodities[0]
    else:
        return 'NA'
def plot_echo_graph_with_colors(echo_system, with_labels: bool=True, labels: bool=None, commodity_colors: dict=None):
    graph = nx_graph_with_colors(echo_system)
    edge_colors = None
    node_colors = None
    if commodity_colors:
        edge_colors = [commodity_colors.get(graph.edges[_edge].get('commodity', 'NA'), 'grey') for _edge in graph.edges]
        node_colors = [commodity_colors.get(graph.nodes[_node].get('commodity', 'NA'), 'grey') for _node in graph.nodes]
    nx.draw(graph, edgelist=graph.edges(), nodelist=graph.nodes(), edge_color=edge_colors, node_color=node_colors, with_labels=with_labels, labels=labels)
    plt.show()



system = models.OptimisationGraph()

## Create Electrical Grid and Gas Grid nodes
gas_grid = models.FlexNodeWithEmissions(node_name='GasGrid',
                                        emitting_port='gas_grid',
                                        emitting_port_units=config.Units.JPS,
                                        carbon_port='bulk_gas_emissions',
                                        emissions_factor=50, ## Assuming 1 GJ of natural gas will produce 50 kg of CO2
                                        )


gas_distribution = models.TellegenNode(node_name='GasGridTellegen',
                                       ports={'gas_grid': models.FlexSink(port_name='grid', units=config.Units.JPS),
                                              'gas_sp01': models.FlexSource(port_name='gas_sp01', units=config.Units.JPS),
                                              'gas_sp02': models.FlexSource(port_name='gas_sp02', units=config.Units.JPS)}
                                       )

gas_sp01 = models.TellegenNode(node_name='GasSupply01',
                               ports={'gas_grid': models.FlexSink(port_name='gas_sp01', units=config.Units.JPS),
                                      'bl1_gas_supply': models.FlexSource(port_name='bl1_gas_supply', units=config.Units.JPS)}
                               )

gas_sp02 = models.TellegenNode(node_name='GasSupply02',
                               ports={'gas_grid': models.FlexSink(port_name='gas_sp02', units=config.Units.JPS),
                                      'bl2_gas_supply': models.FlexSource(port_name='bl2_gas_supply', units=config.Units.JPS)}
                               )


carbon_aggregation = models.CarbonAggregation(node_name = 'BulkEmissions', ports={'bulk_gas_emissions': models.CarbonPort()})


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

electrical_grid = models.FlexElectricalNode(node_name = 'ElectricGrid', port_name='to_avenue')


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


# for k,v in system.node_obj.items():
#     print(f'{k}: {v.ports.keys()}')


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


bl2_cp = MultiCommodityTellegenNodeManual(node_name='Bld2',
                                                 ports={'bl2_gas_supply': models.FlexPort(port_name='bl2_gas_supply', units=config.Units.JPS),
                                                        'bl2_gas_demand': models.FlexPort(port_name='bl2_gas_demand',units=config.Units.JPS),
                                                        'bl2_el_supply': models.FlexPort(port_name='bl2_el_supply', units=config.Units.KW),
                                                        'bl2_el_supply_chiller': models.FlexPort(port_name='bl2_el_supply_chiller', units=config.Units.KW),
                                                        'bl2_el_demand_power': models.FlexPort(port_name='bl2_el_demand_power', units=config.Units.KW),
                                                        'bl2_el_demand_chiller': models.FlexPort(port_name='bl2_el_supply_chiller', units=config.Units.KW)},
                                                 tellegen_ports_dict = {'gas_flow':['bl2_gas_supply', 'bl2_gas_demand'],
                                                                        'el_power':['bl2_el_supply', 'bl2_el_demand_power'],
                                                                        'chiller_power':['bl2_el_supply_chiller', 'bl2_el_demand_chiller']})




## Add electrical Nodes to Optimisation graph
system.add_nodes_from([electrical_grid, avenue_feeder, s001, s002, bl1_load_net, bl2_load_power, bl2_load_chiller, bl1_cp, bl2_cp])

### Connections
edges = {('GasGrid', 'gas_grid') : ('GasGridTellegen', 'gas_grid'),
         ('GasGrid', 'bulk_gas_emissions'): ('BulkEmissions', 'bulk_gas_emissions'),
         ('GasGridTellegen','gas_sp01'): ('GasSupply01', 'gas_grid'),
         ('GasGridTellegen','gas_sp02'): ('GasSupply02', 'gas_grid'),
         ('GasSupply01', 'bl1_gas_supply'): ('Bld1', 'bl1_gas_supply'),
         ('Bld1', 'bl1_gas_demand'): ('B1GasLoad', 'bl1_gas_demand'),
         ('GasSupply02', 'bl2_gas_supply'): ('Bld2', 'bl2_gas_supply'),
         ('Bld2', 'bl2_gas_demand'): ('B2GasLoad', 'bl2_gas_demand'),
         ('ElectricGrid', 'to_avenue'): ('AvenueFeeder', 'grid'),
         ('AvenueFeeder', 's001'): ('Substation001', 'feeder'),
         ('AvenueFeeder', 's002'): ('Substation002', 'feeder'),
         ('Substation001', 'bl1_el_supply'): ('Bld1', 'bl1_el_supply'),
         ('Substation001', 'bl2_el_supply'): ('Bld2', 'bl2_el_supply'),
         ('Substation002', 'bl2_el_supply_chiller'): ('Bld2', 'bl2_el_supply_chiller'),
         ('Bld1', 'bl1_el_demand_net'): ('B1Load', 'bl1_el_demand_net'),
         ('Bld2', 'bl2_el_demand_power'): ('B2LoadPower', 'bl2_el_demand_power'),
         ('Bld2', 'bl2_el_demand_chiller'): ('B2LoadChiller', 'bl2_el_demand_chiller')}



for (node1_id, port1_id), (node2_id, port2_id) in edges.items():
    from_node = system.node_obj.get(node1_id, None)
    to_node = system.node_obj.get(node2_id, None)
    if not from_node or not to_node:
        print(f'Cant find connection Nodes {node1_id} is {type(from_node)},'
              f'{node2_id} is {type(to_node)}')
    from_port = from_node.get_port(port1_id)
    to_port = to_node.get_port(port2_id)
    print(f'Connecting Nodes {from_node.node_name}, {to_node.node_name} on Ports {from_port.port_name}, {to_port.port_name}')
    system.connect_ports_and_create_edge(from_port, to_port, edge_name=f'{node1_id}_{node2_id}')




## Plot system Graph colored by commodity

# commodity_colors = {'KW': 'green',
#                    'CO2':'orange',
#                    'KWT':'yellow',
#                    'JPS': 'blue',
#                    'KWh': 'green',
#                    'kVA': 'green',
#                    'kVAR': 'green',
#                    'LPS': 'green',
#                    'NA': 'grey'}
# plot_echo_graph_with_colors(system, commodity_colors=commodity_colors)



# Invoke the optimiser and optimise
optimiser_object = optimiser.EchoOptimiser(interval_duration=interval_duration,
                          number_of_intervals=time_periods,
                          number_of_expansion_intervals=expansion_periods,
                          discount_rate=discount_rate,
                          ES=system,
                          objective_set=None,
                          profile=df)

optimiser_object.optimise(tee=True)




