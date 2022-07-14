*echo* OptimisationGraph
=========================
The optimisation graph holds all the nodes and edges in the model.
It is both a representation of a physical network, as well as an object on which we can perform optimisation and analysis.

Mathematically, the optimisation graph is a graph :math:`G=(N,E)`, where :math:`N` is the set of nodes in the graph, and :math:`E`
is the set of edges. Each node contains a list of ports that belong to the node:

:math:`n=(p_0, p_1, ..., p_m)` where there are :math:`m` ports in a node.

Each edge is a node pair, and since nodes are a set of ports, edges are also a corresponding pair of ports.

Creating and Modifying the Graph
-----------------------------------

The optimisation graph is instantiated as shown below:

.. code-block::

    system = OptimisationGraph()

Once the graph has been created, we can create some nodes and add them to the graph, as shown below:

.. code-block::

    grid = FlexNode(node_name='grid', port_name='grid', port_unit=Units.KW)

    load = Load(node_name='load',
                 port_name='load',
                 port_unit=Units.KW,
                 profile=[2]*24)

    system.add_node_obj([grid, battery])


We can connect nodes together using the ``.connect_nodes_by_name`` method, as shown below:

.. code-block::

    system.connect_nodes_by_name(ports=('grid', 'load'), nodes=('grid', 'load'))

.. note::
    Any nodes that are part of an edge must be added to the graph first, before edges can be created.


Path tracing
-----------------------
.. warning::

    Path tracing is an experimental feature. There is often no unique solution to the path tracing problem, although a regularisation term can be added to produce a unique solution. If path tracing is being used in order to use path tariffs, it is recommended to convert the tariffs to port tariffs where possible. This is because echo may alter the path flows to minimise cost in a way that is not physically meaningful or representative of how flows behave in real networks.


Echo can calculate path flows within the network. A path is a sequence of distinct nodes. Usually a path begins at a node that is a source of some commodity, and terminates at a node that is a sink for the same commodity.

Path tracing currently ignores different commodities. Echo will calculate paths in a network based on user-specified source and sink nodes.
Source nodes are nodes that can be the start of a path (i.e., they can generate a commodity), and sink nodes are nodes
nodes that can be the end of a path (i.e., they can sink a commodity).
If it is not known whether nodes are sources or sinks, they can be entered as both.

.. note::
    Any Tellegen nodes, or interconnecting should NOT be included as either a source or sink. This will raise an error.
    Echo will assume that any node that isn't a source or sink is a tellegen node.

    Source/sink nodes should have only one port.


Enabling Path Tracing
^^^^^^^^^^^^^^^^^^^^^^^

To use path tracing, the full network model should be built first. Then, paths can be generated using the ``.create_path_objects()`` method as shown below.

.. code-block::

    system.create_path_objects(sources=[grid], sinks=[load])

This will create all paths in the network, according to the sources and sinks provided. These path objects can be accessed using
the ``.get_path()`` method, which takes as an input the list of node objects that form the vertices of the desired path.
You should only access path objects if you want to apply a path tariff.

.. note::
    Paths only represent flow in one direction. Therefore, there will be separate path objects for path A->B->C and C->B->A.


Path Flow Constraints
^^^^^^^^^^^^^^^^^^^^^^

Each path object has a variable, :math:`f`. This is a non-negative variable that represents the flow along the path.

Let :math:`f_N^{start}` and :math:`f_N^{end}` represent the sum of path flow variables that start at node N and end at node N respectively.
Then, for each source or sink node :math:`N`, with associated port :math:`p_N`, the constraint is:

:math:`f_N^{end} - f_N^{start} = p_N`

This constraint enforces that if :math:`f_N^{end} > f_N^{start}`, :math:`p_N` will be positive and importing, which is correct since there are more flows in than out. Conversely, if :math:`f_N^{end} < f_N^{start}`, :math:`p_N` will be negative and exporting, which is correct since there are more flows out than in.

Because sources and sinks either import or export at a given time, it does not make sense for there to be simultaneous flows in and out.
Therefore, we add the following pair of big M constraints to enforce that when there are flows in, the sum of flows out must equal zero, and vice versa.
To achieve this we introduce a binary node variable, :math:`N^{inflow}`. For each source or sink node :math:`N`, with associated port :math:`p_N`, the constraints are:

:math:`f_N^{end} <= N^{inflow} \cdot M`

:math:`f_N^{start} <= (1 - N^{inflow}) \cdot M`

.. note::
    A similar constraint could be achieved by splitting each port variable :math:`p_N` into positive and negative components, and instead of the two constraints above, using:

    :math:`f_N^{end} = p_N^+`

    :math:`f_N^{start} = p_N^-`

    However, both formulations require introducing a binary variable and two big M constraints, so it is unlikely there would be a significant difference in performance.







