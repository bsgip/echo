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
.. math::
    x = \frac{2}{3}

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

**Variables**:

:math:`temp^{internal}_{x, t}`, the internal temperature of the thermal load

:math:`en^{loss}_{x, t}`, energy loss due to internal temperature being > ambient temperature

:math:`en^{gain}_{x, t}`, energy gain due to internal temperature being < ambient temperature

:math:`en^*_{x, t}`, binary variable for splitting losses and gains

**Parameters**:

:math:`temp^{ub}_{x, t}`, temperature upper bound

:math:`temp^{lb}_{x, t}`, temperature lower bound

:math:`temp^{ambient}_{x, t}`, ambient temperature

:math:`c`, a factor for converting from a temperature difference to kW (heat capacity?)

:math:`\eta^{loss}`, a loss factor/efficiency

:math:`\eta^{gain}`, a gain factor/efficiency 


**Constraints**:

Loss and gain sum constraint:

.. math::
    en^{loss} + en^{gain} = (temp^{ambient} - temp^{internal}) \cdot c

Loss and gain Big M constraints:

.. math::
    en^{loss} \geq (en^* - 1) \cdot M

    en^{gain} \leq en^* \cdot M


Node transformation constraint

.. math::
    \sum_{i=1}^{m} p_{i, x, t} + \alpha \cdot en^{loss}_{x, t}+ \beta \cdot en^{gain}_{x, t} = (temp^{internal}_{x, t} - temp^{internal}_{x, t-1}) \cdot c



Heating Load
^^^^^^^^^^^^^
See :ref:`Controllable Thermal Load`


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
