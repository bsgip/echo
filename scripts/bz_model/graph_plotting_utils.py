import networkx as nx
import matplotlib.pyplot as plt



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

