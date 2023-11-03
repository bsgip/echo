# echo (energy and commodity holistic optimiser) Design

We will model a multi-commodity energy system as a network consisting of nodes and edges.

## Edges
Edges represent a physical flow of a single commodity. An edge is terminated on each end by connection to a port. Edges must begin and end on ports that have the same commodity type.

## Ports
Ports terminate a network edge and represent the connection of an edge to a node. Ports are associated with an individual commodity and represent the flow of the that commodity into or out of a node.

## Nodes
Nodes represent physical or logical connection between edges of the network. Nodes are composed of a collection of ports, with a well-defined relationship between ports. In general, the relationship between ports will be defined by a system of (non)linear constraints . A node can be thought of as defining a transformation between the ports on the node, where ports are used to represent flows of different commodities. Nodes may also include other variables and parameters and constraints necessary to model: <br>
- Assets: A node that represents a physical asset that is a source, sink, storage or transformation between commodities.
- Interconnection / Hub: A node that represents a physical or logical interconnection between edges in the network.

### Node models

Nodes allow the creation of models for assets, transformations, or interconnections. Nodes contain all of the relevant modelling parameters and constraints on asset behaviours. Nodes could include: <br>
- Electric Vehicles
- Distributed Energy Resources
- Energy Storage (PHES and BES)
- Electrolysers
- Power to X

### Network models
Within echo, arbitrary networks can be modelled. These network models contain all of the relevant attributes and constraints on behaviour. Currently, these network models only include the electric power systems (both distribution and transmission) but further work is being undertaken to model additional networks including:
- Transportation networks 
- Gas networks (including hydrogen)	
- Water Networks

### Tariff and Market Pricing
Within echo, it is possible to model arbitrary network and retail tariffs, including recent tariff models like the Local Use of Service (LUOS) network tariff. In addition, it is possible to model energy, ancillary and network services markets.

# Current Capabilities

## Constraint only problems
Echo can solve problems without needing an objective. This simply resolves all of the constraints that are defined, allowing pre-optimisation network flows to be calculated. 

## Optimisation against tariffs/costs
Tariffs can be added either at ports or along specified paths in the network (e.g., on a path from a neighbourhood battery to a local load).   

### Path flows/tracing
Echo can calculate path flows within the network. A path is simply a sequence of distinct edges. Usually a path begins at a node that is a source of some commodity, and terminates at a node that is a sink for the same commodity. Currently, path tracing is only supported for networks with a single commodity type.

# Future capabilities

## Expansion Planning
Expansion planning involves a set of decisions regarding:
- asset expansion --> whether to add new assets to the system (e.g., whether or not to install an energy storage asset somewhere in a network)
- capacity expansion of existing assets --> (e.g., whether or not to upgrade the capacity of a 'line' or a connection point).
- network expansions --> whether to add completely new edges and/or nodes

Expansion planning is implemented by introducing two time intervals. The first is an operational time interval (e.g., 1 hr increments) over which operational decisions have to be made. The second is an expansion planning interval (e.g., 1 year increments) over which investment/expansion decisions are made. Expansion decision variables, which are effectively a binary variable (to make the expansion or not) are indexed by the expansion planning interval. 

The user defines a set of expansion parameters that define the scope of the expansion planning. These parameters include the asset types under consideration for expansion, and any global constraints on the number of expansions per asset type per expansion period. The optimiser will populate the network with empty assets that can be installed in the appropriate expansion planning time period.  

### Retirement Planning
Retirement planning is effectively the opposite of expansion planning. 
Retirement can be directly linked to a lifetime, which can be defined in units of years. 
Assets must be retired when they reach the end of their lifetime. 
Assets can also be prematurely retired - cost? Argument for no cost of premature retirement is that there would be no real salvage/residual value from most assets 

Retirement is only relevant for existing assets (i.e., existing at the start of the optimisation). 
We may assume that new assets will not need to retire within the planning period (which is the entire analysis period).

## Capacity Optimisation
For nodes with a defined capacity (e.g., max kWh for a storage node, or max kW for a connection point node), the node's capacity is introduced as a decision variable. Per unit costs can be introduced to explicitly penalise oversizing capacity. 


## Tariff optimisation
TBC