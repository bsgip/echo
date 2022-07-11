from echo.echo_builder import *
from echo.echo_models import OptimisationGraph, Node, FlexPort
from echo.configuration import *

system = OptimisationGraph()

def create_electrical_flex_node(n: NodeType.ElectricalFlex):
    node = Node(node_name=n.name)
    port = FlexPort()



n = NodeType.ElectricalFlex
n.ports = {}
n.parameters = {}



# def create_electrical_node(node_dict: dict, df: pd.DataFrame):
#     """ Creates a node with a demand (import only) port."""
#     # Check node has only one port
#
#     node = ecm.Node(node_name=node_dict['id'])
#     (port_name, port_attr), = port_dict.items()
#     p = ecm.Demand(units=port_attr['units'])
#     load_profile = process_field(port_attr['data'], df)
#     p.add_initial_value_from_array(load_profile)
#     node.ports[port_name] = p
#     return node
#
# load_node_dict = NodeDict(id='load',
#                           type=NodeType.ElectricalLoad,
#                           units=Units.KW,
#                           ports=PortDict(id='load', data=[3]*10))
#
# load = create_load_node(node_dict=load_node_dict,
#                         port_dict=load_node_dict['ports'],
#                         df=None
#                         )
