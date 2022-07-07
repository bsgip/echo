============
*echo* Nodes
============
Nodes are the
Nodes represent physical or logical connection between edges of the network. Nodes are composed of a collection of ports,
with a well-defined relationship between ports. In general, the relationship between ports will be defined by a system of (non)linear constraints .
A node can be thought of as defining a transformation between the ports on the node, where ports are used to represent flows of different commodities.
Nodes may also include other variables and parameters and constraints necessary to model:

* *Assets*: A node that represents a physical asset that is a source, sink, storage or transformation between commodities.
* *Interconnection / Hub*: A node that represents a physical or logical interconnection between edges in the network: such as busbar, electrical connection point, gas junction.

Flow tracing
-----------------


Commodity Agnostic Nodes
-------------------------

Flexible Source
^^^^^^^^^^^^^^^

Flexible Sink
^^^^^^^^^^^^^^^

Fixed Source
^^^^^^^^^^^^^^^

Fixed Sink
^^^^^^^^^^^^^^^

Tellegen
^^^^^^^^^^^^^

Multi Commodity Tellegen (ie Building)
^^^^^^^^^^^^^

Input Output Node
^^^^^^^^^^^^^^^^^

Piecewise Input Output Node
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Controlled Load
^^^^^^^^^^^^^^^^^

Controlled Generation
^^^^^^^^^^^^^^^^^^^^^



Electrical Nodes
----------------------


Battery
^^^^^^^^^^^^^^^^^

Solar
^^^^^^^^^^^^^^^^^


EV
^^^^^^^^^^^^^

Inverter
^^^^^^^^^^^^^




Gas Nodes
-----------------

Gas Boiler Fixed COP
^^^^^^^^^^^^^^^^^^^^

Temperature Controlled Gas Boiler
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^


Thermal Nodes
----------------------

Controllable Thermal Load
^^^^^^^^^^^^^
A controllable thermal load represents a heating and/or cooling load, in units of Joules. For example, this can be used to represent a building's overall thermal load, or specific loads for things like space heating, hot water heating, or other industrial processes.

Heating is denoted by positive values (indicating that heat is imported), and cooling is denoted by negative values (indicating that heat is exported, i.e. removed).

This node supports an arbitrary number of connections to heating/cooling sources.

Variables:

Parameters:

Constraints: :math:x=2

..math::

    x=2



Heating Load
^^^^^^^^^^^^^

Cooling Load
^^^^^^^^^^^^^

Heat Pump
^^^^^^^^^^^^^

Chiller
^^^^^^^^^^^^^


Other Nodes
------------------------

Carbon Aggregation
^^^^^^^^^^^^^^^^^^^


Emitting Node
^^^^^^^^^^^^^^^^^


Time Delay Node
^^^^^^^^^^^^^^^^



Input Output ARX Node
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
