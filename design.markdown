# echo (energy and commodity holistic optimiser) Design

## Nodes
A node is a fundamental and general modelling component that corresponds to a single decision variable or a parameter. It is designed to flexibly represent energy and commodity flows.

### Assets
An asset can be modelled directly based on a Node. For example, a Node can represent an Energy Storage asset (e.g., a battery), a Generation asset (e.g., solar PV).  

## Hubs
A hub is a collection of nodes that can include non-trival relationships between those nodes. Specifically, hubs contain a set of intermediate nodes called 'ports'. A port is effectively a node that can accommodate a connection to another node. This allows assets (which are typically nodes) to be 'plugged in' to ports in a hub. It also allows two ports in two separate hubs to be directly connected.

A Hub is required for modelling assets with multiple energy/commodity flows (e.g., an electrolyser or a diesel generator). 

### Tellegen
An aggregation hub implements a kirchoff / tellegen constraint, such that the nodes in the hub sum to zero. 

### Transformation
A transformation hub implements a fixed transformation between nodes in the hub. The transformation can be one-directional (e.g., a transformation of diesel fuel into electricity) or bi-directional (e.g., losses).

### Accumulation
An accumulation hub sums over the nodes that are part of the hub (e.g., summing carbon emission flows from multiple nodes).

## Edges
Lossless edges are used to connect nodes and hubs. 

# Optimisation
Optimisation can be applied to any values of the nodes.


# Capabilities

## Expansion Planning
Expansion planning involves a set of decisions regarding whether to add new assets to the system (e.g., whether or not to install an energy storage asset somewhere in a network), as well as decisions about expanding the capacity of existing assets (e.g., whether or not to upgrade the capacity of a 'line' or a connection point).

Expansion planning is implemented by introducing two time intervals. The first is an operational time interval (e.g., 1 hr increments) over which operational decisions have to be made. The second is an expansion planning interval (e.g., 1 year increments) over which investment/expansion decisions are made. Expansion decision variables, which are effectively a binary variable (to make the expansion or not) are indexed by the expansion planning interval. 

The user defines a set of expansion parameters that define the scope of the expansion planning. These parameters include the asset types under consideration for expansion, and any global constraints on the number of expansions per asset type per expansion period. The optimiser will populate the network with empty assets that can be installed in the appropriate expansion planning time period.  

### Retirement Planning
Retirement planning is effectively the opposite of expansion planning. 
Retirement can be directly linked to a lifetime, which can be defined in units of years. 
Assets must be retired when they reach the end of their lifetime. 
Assets can also be prematurely retired - cost? Argument for no cost of premature retirement is that there would be no real salvage/residual value from most assets 

Retirement is only relevant for existing assets (i.e., existing at the start of the optimisation). 
In [1], the authors assume that new assets will not need to retire within the planning period (which is the entire analysis period).

## Capacity Optimisation
For nodes with a defined capacity (e.g., max kWh for a storage node, or max kW for a connection point node), the node's capacity is introduced as a decision variable. Per unit costs can be introduced to explicitly penalise oversizing capacity. 

## Tariff optimisation

## Local flow tracing

## Other 
Local Flows
Flow Tracing
LUOS
Tariff Optimisation
Distflow?

# Use cases
## Adding storage in a network

## Retirement of coal generators

## ANU BZ - retirement of gas assets

## Balancing problem - hydrogen exports to Japan


# References

[1] Li, Can, Conejo, Antonio J., Liu, Peng, Omell, Benjamin P., Siirola, John D., and Grossmann, Ignacio E. 2022. "Mixed-integer linear programming models and algorithms for generation and transmission expansion planning of power systems". Netherlands. https://doi.org/10.1016/j.ejor.2021.06.024.