# Modelling Concepts

## Commodities

Echo supports 9 commodities.

## Energy System Networks
 
Echo describes the energy systems as a network comprised of three fundamental building blocks, [edges](#edges), [ports](#ports) and [nodes](#nodes).

### Edges

Edges represent physical flows of a *single* [commodity](#commodities).

### Ports

Ports are connected by edges. Each port *cannot* be connected to more than one edge at a time.

Like [edges](#edges), each port only supports *one* [commodity](#commodities) at a time.

Ports are attached to nodes, allowing the commodity to flow into or out of a node.

Ports restrict the direction of the flow of the commodity. The permitted flows are import (into the node only), export (out of the node only) or both (in and out the node).

### Nodes

Nodes represent physical or logical connection between edges of the network.

Nodes are composed of a collection of ports, with a well-defined relationship between ports.

In general, the relationship between ports will be defined by a system of (non)linear constraints . A node can be thought of as defining a transformation between the ports on the node, where ports are used to represent flows of different commodities. 

Nodes may also include other variables and parameters and constraints necessary to model:

- Assets: A node that represents a physical asset that is a source, sink, storage or transformation between commodities.
- Interconnection / Hub: A node that represents a physical or logical interconnection between edges in the network.


