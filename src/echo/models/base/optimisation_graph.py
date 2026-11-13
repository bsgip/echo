from __future__ import annotations  # Deprecating in python 3.15 in favour of lazy annotations (PEP 649 and 749)

from collections.abc import Iterable
import os
import warnings
from typing import cast

import matplotlib
import networkx as nx
import pyomo.environ as en
from attrs import define, field
from pyomo.core.expr.relational_expr import EqualityExpression, InequalityExpression
from deprecated import deprecated

from echo.configuration import Units
from echo.exceptions import ConfigurationError, validate
from echo.models.base.edge import Edge
from echo.models.base.node import Node
from echo.models.base.path import Path
from echo.models.base.port import Port
from echo.models.scenario import EchoConcreteModel
from echo.validators import ArrayType


@define
class OptimisationGraph:
    nodes: dict[str, Node] = field(factory=dict)  # Nodes keyed by their node_name
    edges: dict[tuple[str, str], Edge] = field(factory=dict)
    paths: dict[tuple, Path] = field(factory=dict)

    @property
    # @deprecated
    def node_obj(self) -> dict[str, Node]:
        return self.nodes

    @property
    # @deprecated
    def edge_obj(self) -> dict[tuple[str, str], Edge]:
        return self.edges

    def node_name_list(self) -> list[str]:
        return list(self.nodes.keys())

    def edge_list(self) -> list[str]:
        return [e.edge_name for e in self.edges.values()]

    def convert_to_nx(self) -> nx.Graph:
        """Converts the OptimisationGraph to a networkx graph, where nx nodes are echo node names and nx edges are
        nx node pairs"""
        g = nx.Graph()
        g.add_nodes_from(self.nodes.keys())
        g.add_edges_from(self.edges.keys())
        return g

    # This method should be made private and the public method deprecated
    def add_node(self, node: Node) -> None:
        self.nodes[node.node_name] = node

    def add_nodes(self, nodes: Node | Iterable[Node]) -> None:
        if isinstance(nodes, Node):
            self.add_node(nodes)
            return

        for node in nodes:
            self.add_node(node)

    @deprecated(version="2.3.0")
    def delete_node(self, node_name: str) -> None:
        if self.get_node(node_name) is not None:
            del self.nodes[node_name]
        else:
            print(f"Node {node_name} not found.")

    @deprecated(version="2.3.0")
    def delete_edge(self, edge_nodes: tuple[str, str]) -> None:
        if self.get_edge(edge_nodes) is not None:
            del self.edges[edge_nodes]
        else:
            print(f"Edge {edge_nodes} not found.")

    # @deprecated
    def add_node_obj(self, node: list | Node) -> None:
        """Adds either a single node or list of nodes to graph"""
        # todo phase out this method
        if isinstance(node, list):
            for n in node:
                self.add_node(n)
        else:
            self.add_node(node)

    # @deprecated
    def add_nodes_from(self, nodes: list[Node]) -> None:
        """Adds a list of nodes to the graph."""
        for n in nodes:
            self.add_node(n)

    # @deprecated
    def get_node(self, node_name: str) -> Node | None:
        """Returns node object given node name"""
        return self.nodes.get(node_name)

    def get_edge(self, nodes: tuple[str, str]) -> Edge | None:
        """Retrieves the edge that connects a tuple of nodes, if an edge exists."""
        if nodes in self.edges:
            return self.edges.get(nodes)

        reversed_nodes = (nodes[1], nodes[0])
        if reversed_nodes in self.edges:
            return self.edges.get(reversed_nodes)

        return None

    def add_edge(self, edge: Edge, nodes: tuple[str, str] | None = None) -> None:
        port1 = edge.vertices[0]
        port2 = edge.vertices[1]
        validate(
            port1.units == port2.units,
            f"Ports on edge must have matching units. {port1.units} != {port2.units}",
        )
        if nodes is None:
            # Want to avoid doing this lookup - very slow
            node1_name = self.lookup_node_names_from_port(port1)
            node2_name = self.lookup_node_names_from_port(port2)
        else:
            node1_name = nodes[0]
            node2_name = nodes[1]
        # Need to check whether an edge already exists between these two nodes
        if self.get_edge(nodes=(node1_name, node2_name)) is not None:
            raise ValueError("An edge between these nodes already exists")

        self.edges[(node1_name, node2_name)] = edge

    # @deprecated
    def add_edge_obj(self, edge: list[Edge] | Edge) -> None:
        # todo phase out this method
        if isinstance(edge, list):
            for e in edge:
                self.add_edge(e)
        else:
            self.add_edge(edge)

    # @deprecated
    def add_edges_from(self, edge: list[Edge]) -> None:
        for e in edge:
            self.add_edge(e)

    # @deprecated
    def connect_ports_and_create_edge(
        self,
        port1: Port,
        port2: Port,
        edge_name: str | None = None,
    ) -> None:
        """Creates an edge between port1 and port2 and adds it to the graph"""
        edge = Edge(vertices=(port1, port2), edge_name=edge_name) if edge_name else Edge(vertices=(port1, port2))
        self.add_edge(edge)

    @deprecated(
        version="2.3.0",
        reason="No longer needed after migration to attrs",
    )
    def rebuild_all_edges(self) -> None:
        """Deletes and rebuilds all edges. Deprecated and replaced with a `pass` (i.e. no operation)

        To be used after stateful data has been injected into ports. Injecting stateful data into ports alters the
        port. The new altered port correctly remains associated with the node, but does not remain associated with
        any edges this port may be associated with. This method builds new edges for each old edge based on the port
        name associated with each end of the edge. The original edge is deleted.

        Returns:
            None
        """
        pass

    def lookup_node_names_from_port(self, port: Port) -> str:
        """Returns node name of the node that a specified port belongs to, if the port belongs to a node."""
        for node_name, node in self.nodes.items():
            for p in node.ports.values():
                if port == p:
                    return node_name
        raise ConfigurationError(f"Port {port.port_name} is not part of any node, or node has not been added to graph.")

    def get_ports_on_edge_from_nodes(self, node1: str, node2: str) -> tuple[Port, Port] | None:
        """Returns the ports that are on the edge from node1 to node2."""
        connecting_edge = self.edges.get((node1, node2))
        if connecting_edge:
            node1_port = connecting_edge.vertices[0]
            node2_port = connecting_edge.vertices[1]
            return node1_port, node2_port
        else:
            connecting_edge = self.edges.get((node2, node1))
            if connecting_edge:
                node1_port = connecting_edge.vertices[1]
                node2_port = connecting_edge.vertices[0]
                return node1_port, node2_port

        return None

    def get_sources_and_sinks(self) -> set[Node]:
        """Returns a set that contains all source and sink nodes."""
        validate(
            bool(self.paths) is True,
            "Create paths before retrieving sources and sinks.",
        )
        sources_or_sinks = set()
        for path in self.paths.values():
            sources_or_sinks.add(path.vertices[0])
            sources_or_sinks.add(path.vertices[-1])
        return sources_or_sinks

    def get_path(self, path_vertices: list[Node] | list[str]) -> Path:
        """Looks up a path using a list of path vertices (nodes, or node names)."""
        if isinstance(path_vertices[0], Node):
            name_key = [cast(Node, node).node_name for node in path_vertices]
            return self.paths[tuple(name_key)]
        else:
            if self.paths.get(tuple(path_vertices)) is not None:
                return self.paths[tuple(path_vertices)]
            else:
                raise ValueError(f"No path with vertices {path_vertices} is defined.")

    def verify_paths(self) -> None:
        """Verifies that our paths meet the assumptions required to correctly do flow tracing."""
        all_nodes = self.get_sources_and_sinks()
        for node in all_nodes:
            for path in self.paths.values():
                if node in path.vertices[1:-1]:
                    # if the source/sink node appears in the middle of another path, the optimiser will fail
                    # A node can't be both a tellegen node and a source/sink node
                    raise ConfigurationError("Source/sink node is being treated as a tellegen node.")

    def create_path_objects(
        self,
        sources: list[Node] | list[str],
        sinks: list[Node] | list[str],
        path_unit: Units = Units.KW,
        regularise: bool = False,
    ) -> None:
        """Creates path objects according to source/sink lists provided."""

        if os.environ["ECHO_DISABLE_EXPERIMENTAL_PATH_WARNING"] != "1":
            warnings.warn(
                "Path tracing is still experimental. If you are generating paths to use path tariffs, please consider "
                + "whether you can convert these tariffs to point/port tariffs.",
                stacklevel=1,
            )

        all_paths = {}
        graph = self.convert_to_nx()

        if isinstance(sources[0], Node):
            sources = [cast(Node, i).node_name for i in sources]

        if isinstance(sinks[0], Node):
            sinks = [cast(Node, i).node_name for i in sinks]

        tellegen_node_set = set()  # create a set to store list of nodes that are treated as tellegen nodes
        source_sink_set = set(sources + sinks)  # create a set of nodes that are treated as sinks/sources

        for source_node in sources:
            for sink_node in sinks:
                if source_node is not sink_node:
                    # Find all the paths, just using the node names
                    simple_paths = nx.all_simple_paths(graph, source_node, sink_node)
                    simple_edges = nx.all_simple_edge_paths(graph, source_node, sink_node)
                    for vertex_list, edge_list in zip(simple_paths, simple_edges, strict=True):
                        tellegen_node_set.update(vertex_list[1:-1])  # update set of tellegen nodes
                        p = self._create_path_object(vertex_list, edge_list, regularise, path_unit)  # create path
                        all_paths[tuple(vertex_list)] = p

        intersection = source_sink_set.intersection(tellegen_node_set)  # check overlap of tellegen and src/sink nodes

        validate(
            len(intersection) == 0,
            f"Nodes '{intersection}' are being treated as both tellegen and source/sink.",
        )

        self.paths = all_paths

    def _create_path_object(self, vertex_list: list, edge_list: list, regularise: bool, path_unit: Units) -> Path:
        """Creates a path object"""
        p = Path(vertices=vertex_list, regularise=regularise, units=path_unit)  # Create path object
        for edge in edge_list:
            edge_ports = self.get_ports_on_edge_from_nodes(edge[0], edge[1])
            validate(
                edge_ports is not None,
                f"get_ports_on_edge_from_nodes return None for edges {edge[0]}, {edge[1]}",
            )
            p.edge_ports.append(edge_ports)
        return p

    def apply_path_constraints(self, model: EchoConcreteModel) -> None:
        """Applies path tracing constraints to model"""

        def path_flow_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            a = 0
            for path in self.paths.values():  # Iterate through all paths in the model
                if path.vertices[0] is current_node_name:  # If the path starts at the current node
                    a += getattr(model, path.flow_value)[p, t]  # Add the flow value
                if path.vertices[-1] is current_node_name:  # If the path ends at the current node
                    a -= getattr(model, path.flow_value)[p, t]  # Subtract the flow value
            return a == getattr(model, current_port.port_name)[p, t] * -1  # Flows out - flows in = -1 * port

        def only_inflow_or_outflow1(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            a = 0
            for path in self.paths.values():
                if path.vertices[-1] is current_node_name:  # If the path ends at the current node
                    a += getattr(model, path.flow_value)[p, t]  # Add the flow value
            return (
                a <= getattr(model, current_node.inflow)[p, t] * model.big_m
            )  # Incoming paths can only be non-zero if inflow=1

        def only_inflow_or_outflow2(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            a = 0
            for path in self.paths.values():
                if path.vertices[0] is current_node_name:  # If the path starts at the node
                    a += getattr(model, path.flow_value)[p, t]  # Add the flow value
            return (
                a <= (1 - getattr(model, current_node.inflow)[p, t]) * model.big_m
            )  # Outgoing paths can only be non-zero if inflow=0

        sources_and_sinks = self.get_sources_and_sinks()  # returns concatenated list of all source/sink nodes
        for current_node_name in sources_and_sinks:  # Iterate through the source/sink nodes
            current_node = self.nodes[current_node_name]  # get the node obj
            for (
                path_vertices,
                path_obj,
            ) in self.paths.items():  # Iterate through all paths
                if current_node_name is path_vertices[0]:  # If the path starts at the current node
                    current_port = path_obj.edge_ports[0][0]  # Pick up the first port on the path
                elif current_node_name is path_vertices[-1]:  # If the path ends at the current node
                    current_port = path_obj.edge_ports[-1][-1]  # Pick up the last port on the path

            setattr(
                model,
                f"path_flow_con1_{current_node_name}",
                en.Constraint(model.Expansion, model.Time, rule=path_flow_rule),
            )

            # Create an indicator var for when there are flows into a node
            setattr(
                model,
                current_node.inflow,
                en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary),
            )

            setattr(
                model,
                f"path_flow_con2_{current_node_name}",
                en.Constraint(model.Expansion, model.Time, rule=only_inflow_or_outflow1),
            )

            setattr(
                model,
                f"path_flow_con3_{current_node_name}",
                en.Constraint(model.Expansion, model.Time, rule=only_inflow_or_outflow2),
            )

    def draw_on_axes(
        self,
        axes: matplotlib.axes.Axes,
        with_labels: bool = False,
        labels: dict[str, str] = None,
        **kwargs,
    ) -> None:
        """Draws the network on a matplotlib plot

        Args:
            axes (matplotlib.axes.Axes): The (sub-)plot on which to draw the network
            with_labels (bool): Set to True to draw labels on the nodes. Defaults to False.
                Uses the node's names as the label.
            labels (dict): Optional way of supplying node labels as a dictionary of labels (strings) keyed by node.
                Default = None.
            **kwargs: Optional keyword arguments for customising the drawing of the network. See
                networkx.drawing.nx_pylab.draw_networkx documentation for more information.

        Examples:
            The following example shows how to draw an already created OptimisationGraph with the name `network`

            >>> import matplotlib.pyplot as plt
            >>> network_figure = plt.figure()
            >>> network_axes = network_figure.add_subplot()
            >>> network.draw_on_axes(axes=network_axes, with_labels=True)
            >>> plt.show()
        """
        nx.draw_networkx(
            self.convert_to_nx(),
            ax=axes,
            with_labels=with_labels,
            labels=labels,
            **kwargs,
        )

    def to_cytoscape_json(self) -> str:
        """Converts the optimisation graph to json that can be read by cytoscape (https://js.cytoscape.org/)"""
        import json

        graph = self.convert_to_nx()
        nodes = []
        for node in graph.nodes():
            nodes.append({"data": {"id": node}})
        for n1, n2 in graph.edges():
            nodes.append({"data": {"id": f"{n1}_{n2}", "source": n1, "target": n2}})

        return json.dumps(nodes)

    @deprecated
    def print_port_names(self) -> None:
        """Prints port name-uid pairs, useful for debugging infeasible optimisation"""
        for n in self.nodes.values():
            for pn, p in n.ports.items():
                print(pn, ", ", p.port_name)

    def _get_port_names_from_nodes(self, skip_dangling_ports: bool = False) -> set[str]:
        output = set()
        for n in self.nodes.values():
            for p in n.ports.values():
                if skip_dangling_ports and not p.allow_dangling_port:
                    output.add(p.port_name)
        return output

    @deprecated
    def get_port_names_from_nodes(self, skip_dangling_ports: bool = False) -> set[str]:
        return self._get_port_names_from_nodes(skip_dangling_ports=skip_dangling_ports)

    def _get_port_names_from_edges(self) -> set[str]:
        output = set()
        for e in self.edges.values():
            output.add(e.vertices[0].port_name)
            output.add(e.vertices[1].port_name)
        return output

    @deprecated
    def get_port_names_from_edges(self) -> set[str]:
        return self._get_port_names_from_edges()

    def verify_graph(self) -> None:
        """Checks that the graph is connected (all nodes have at least one edge), and warns if there
        are unconnected ports"""
        validate(nx.is_connected(self.convert_to_nx()) is True, "Graph is not connected.")
        # Check graph for ports that are not connected
        ports_on_edges = self._get_port_names_from_nodes(skip_dangling_ports=True)
        ports_on_nodes = self._get_port_names_from_edges()
        diff = ports_on_edges - ports_on_nodes  # check overlap
        if len(diff) != 0:
            warnings.warn(
                f"Ports {diff} are defined on nodes but are not part of an edge. "
                "This may cause erroneous optimisation results.",
                stacklevel=1,
            )

    def split_graph_on_edge(self, node1: str, node2: str) -> tuple[OptimisationGraph, OptimisationGraph]:
        """Splits a graph between node1 and node 2, and returns two echo optimisation graphs.
        The ports on the split edge are kept in the two new graphs."""
        system = self.convert_to_nx()
        # Find the edge that connects these nodes
        if system.has_edge(node1, node2):
            system.remove_edge(node1, node2)
        else:
            raise ValueError(f'No edge exists between nodes "{node1}" and "{node2}"')

        # Get a list of the two sets of nodes
        y = nx.connected_components(system)
        g1_nodes = next(y)
        g2_nodes = next(y)

        g1_subgraph = system.subgraph(g1_nodes)
        g2_subgraph = system.subgraph(g2_nodes)

        def create_new_graph(nodes: list, edges: list) -> OptimisationGraph:
            """Creates a new graph from a list of node names and edge names"""
            new_graph = OptimisationGraph()
            for n in nodes:
                new_graph.add_node_obj(self.nodes[n])
            for ed in edges:
                if self.edges.get(ed) is not None:
                    new_graph.add_edge_obj(self.edges[ed])
                else:
                    new_graph.add_edge_obj(self.edges[(ed[1], ed[0])])

            return new_graph

        graph1 = create_new_graph(g1_subgraph.nodes, g1_subgraph.edges)
        graph2 = create_new_graph(g2_subgraph.nodes, g2_subgraph.edges)

        return graph1, graph2

    @deprecated(
        version="2.3.0",
        reason="No longer needed after migration to attrs. Modify nodes directly.",
    )
    def update_node(self, node_name: str, **kwargs) -> None:
        # Originally this method was necessary because pydantic created clones of objects upon mutation
        # and the edges that made up the optimisation graph

        # The user should no longer need this function since they can either modifify nodes directly.

        # Inject stateful data
        # If the node has a set_stateful_attrs() function, use that function.
        # If it is not, use node.update()
        if hasattr(self.get_node(node_name), "set_stateful_attrs"):
            self.get_node(node_name).set_stateful_attrs(**kwargs)
        else:
            self.get_node(node_name).update(**kwargs)

    @deprecated(
        version="2.3.0",
        reason="No longer needed after migration to attrs. Modify EV nodes directly.",
    )
    def inject_data_into_ev(
        self,
        node_name: str,
        available: ArrayType | list | str | None = None,
        usage: ArrayType | list | str | None = None,
        initial_state_of_charge: float | None = None,
        interval_duration: int | None = None,
    ) -> None:
        """Injects stateful data into an EV node in an OptimisationGraph.

        This is a convenience method to be used for networks constructed by MESNetwork.to_echo(). It will update
        all data in the relevant node and edges through re-initialisation of nodes, and delete and recreated of
        the edge.

        Args:
            node_name: The node_name of the EV to have stateful data injected.
            available: The avability data of the EV to be injected.
            usage: The usage data of the EV to be injected.
            initial_state_of_charge: The initial state of charge of the EV to be injected.
            interval_duration: The interval duration of the EV to be injected.

        Returns:
            None

        """

        node_attributes = {
            "available": available,
            "usage": usage,
            "initial_state_of_charge": initial_state_of_charge,
            "interval_duration": interval_duration,
        }

        self.update_node(node_name=node_name, **node_attributes)
