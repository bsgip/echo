# echo (energy and commodity holistic optimiser) Design

## Nodes
A node is a fundamental and general modelling component that corresponds to a single decision variable or a parameter. It is designed to flexibily represent energy and commodity flows.

### Assets
An asset can be modelled directly based on a Node.

## Hubs
A hub is a collection of nodes that can include non-trival relationships between those nodes.

### Tellegen
An aggregation hub implements a kirchoff / tellegen constraint, such that the nodes in the hub sum to zero.

### Transformation
A transformation hub implements a fixed transformation between nodes in the hub. The transformation can be one-directional (e.g., a transformation of diesel fuel into electricity) or bi-directional (e.g., losses).

### Accumulation
An accumulation hub sums over the nodes that are part of the hub (e.g., summing carbon emission flows from multiple nodes).

# Optimisation
Optimisation can be applied to any values of the nodes.



# Capabilities

Local Flows
Flow Tracing
LUOS
Tariff Optimisation
Distflow?
