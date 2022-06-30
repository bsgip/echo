*echo* OptimisationGraph
=========================

Adding Nodes and Edges
--------------------------

Path tracing
--------------
Echo can calculate path flows within the network. A path is simply a sequence of distinct edges.
Usually a path begins at a node that is a source of some commodity, and terminates at a node that is a sink for the same commodity.
Currently, path tracing is only supported for networks with a single commodity type.