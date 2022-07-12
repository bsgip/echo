============
*echo* Nodes
============
Nodes represent physical or logical connection between edges of the network. Nodes are composed of a collection of ports, with a well-defined relationship between ports. Ports represent flows into and out of nodes. In general, the relationship between ports will be defined by a system of constraints, which we call the *node transformation*. Nodes may also include other variables and parameters and constraints necessary to model:

* *Assets*: A node can represent a physical asset that is a source, sink, storage or generic transformation between commodities.
* *Interconnection / Hub*: A node can represent a physical or logical interconnection between edges in the network: such as busbar, electrical connection point, gas junction.

Flow tracing
-----------------
What is meant to go here?

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
A tellegen node is an energy conserving node. The sum of all flows through the node must equal 0. It is used to represent interconnections, either physical or logical, between different flows in a network.

Multi Commodity Tellegen (ie Building)
^^^^^^^^^^^^^
A multi commodity tellegen node is an energy conserving node. The sum of all flows of the same commodity through the node must equal 0. This node does not necessarily represent a physical interconnection, but it is useful for representing logical connections (e.g., a building that has both gas and electricity supply).


Input Output Node
^^^^^^^^^^^^^^^^^
An input output node has one input port, and one output port. The input port always imports a commodity, but the output port can either import or export a commodity.


Piecewise Input Output Node
^^^^^^^^^^^^^^^^^^^^^^^^^^^
This node has one input port and one output port. The transformation between input and output is defined by a piecewise function that approximates a nonlinear relationship. This node is useful for approximating generic nonlinear transformations where the transformation is known or can be precalculated.

**Constraints**

TBC

Controlled Load
^^^^^^^^^^^^^^^^^
This node must be operated within a minimum and maximum utilisation, and between a minimum and maximum power/flow rate.

Min utilisation is the ratio between the minimum energy consumed, and the maxinimum energy that would be consumed if the load operated at max power.

Max utilisation is the ratio between the maximum energy consumed, and the maximum energy that would be consumed if the load operated at max power.

**Constraints**

TBC

Controlled Generation
^^^^^^^^^^^^^^^^^^^^^
This node must be operated within a minimum and maximum utilisation, and between a minimum and maximum power/flow rate.

Min utilisation is the ratio between the minimum energy generated, and the maxinimum energy that would be generated if the node was operated at max power.

Max utilisation is the ratio between the maximum energy generated, and the maximum energy that would be generated if the node was operated at max power.

**Constraints**


Electrical Nodes
----------------------


Battery
^^^^^^^^^^^^^^^^^


Solar
^^^^^^^^^^^^^^^^^


EV
^^^^^^^^^^^^^
The EV node can be used to model the charging (and discharging) while ensuring that the EV has
enough available charge to meet its trip requirements. The EV node requires the following data:

* ``available`` (:math:`t^{available}`): An array representing the periods which the EV is plugged in and available for charging. 1=available to charge, 0=not available.
* ``usage`` (:math:`p^{usage}`): An array representing the average power (kW) consumption from driving of the EV during a time period.

Both usage and available should have the same length and importantly available should be zero whenever usage has a value
greater than zero (i.e. if the car is in use driving it is not available to charge).

The EV can be specified to charge in 3 different modes. This is controlled by setting ``charge_mode`` to one of 'V0G', 'V1G' or 'V2G'
which are defined as:

* V0G: non-optimised convenience or time of day charging. Whenever the car is available it will charge at it's maximum charging power until full. Alternative, a time-of-day array can be supplied specifying certain time periods during which charging is allowed.
* V1G: optimised uni-directional charging (grid to vehicle only). The car is charged from the upstream grid in a way that optimises the objectives of the model.
* V2G: optimised bi-directional charging (grid to vehicle and vehicle to grid). The car charges and discharges from and to the upstream grid in a way that optimises the model objectives.

An example of initialising an EV node is

.. code-block::

    available = np.array([1] * 24 + [0] * 24)    # bool when at charger
    usage = np.array([0.0]*24 + [5]*24)        # kw average during use

    ev_cp = EV(charge_mode='V2G',
                   available=available,
                   usage=usage,
                   connection_port_name='cp',
                   max_capacity=40,
                   depth_of_discharge_limit=0,
                   charging_power_limit=10,
                   discharging_power_limit=-10,
                   charging_efficiency=1,
                   discharging_efficiency=1,
                   initial_state_of_charge=0,
                   soc_conserv=None,
                   soc_conserv_cost=0.,
                   interval_duration=30.,
                   tod_charging=False,
                   trip_slack=True)


The EV node operates similar to a battery with a built in load (usage) and only certain times during which it can charge (the available).
Hence, the EV node has three ports: one to connect to the grid, one representing the battery (i.e., a storage port),
and a trip usage port (i.e., a load port). Each of these ports has the associated set of parameters/variables previously defined.
Only EV specific additional parameters/variables are defined below.

**Parameters**

* ``SOC_conserv`` (:math:`L^{\text{conserv}}`): conservative state of charge limit below which the EV should not discharge to the grid. This reflects that an EV owner would want to ensure a certain amount of charge is available impromptu trips. This lower bound only applies while the EV is available to charge (i.e., soc lower bound while p^{available}=1).
* ``SOC_conserv_cost (``:math:`C^\text{conserv}`): The cost placed on going below the conservative state of charge limit ($/kWh). That is, the conservative state of charge lower limit will be ignored if it would result in saving (or gaining) more money than this cost. Warning, this cost will be incorrectly over represented in the objective cost as it will be applied whenever the car was plugged back in below :math:`C^\text{conserv}`.
* ``trip_slack``: A boolean enabling or disabling slack trips (recommended=True). If enabled, then any trips that require more than the available energy will be assumed to have charged at a public charger and the optimisation will still succeed and be considered feasible. The cost on this public charging is by default very high and so will be treated as a last resort by the optimisation solver. It is recommended that this is True in case the data contains any infeasible trips.
* ``tod_charging``: Time of day charging. An array or list if enabled, otherwise false. Time of day charging allows the EV to charge only during certain time windows (1=allowed, 0=not allowed). This is because customers might not want to charge during peak windows and would most commonly be used with V0G charging.

**Variables**

* :math:`p^\text{cp}`: connection point port power (kW).
* :math:`p^\text{battery}`: battery port port (kW).
* :math:`p^\text{trip}`: trip usage port power (kW).
* :math:`S^\text{trip}`: value of the trip slack variable (kWH). That is, the amount of energy that was required to be charged at a public charger in order to make a trip feasible.
* :math:`S^\text{conserv}`: Value of a slack variable required for the implementation of the conservative lower limit.

**Constraints**

Balance of power across ports:

:math:`p^\text{battery}_{x, t} = p^\text{cp}_{x, t} - p^\text{trip}_{x, t}`

The modified battery state of charge equations accounting for the trip slack variable (if ``trip_slack=True``):

:math:`E_{x, t} = E_{x,t-1} + \eta^\text{charge} p^{battery,+}_{x,t} d^{interval} + p^{battery, -}_{x,t} \frac{d^\text{interval}}{\eta^\text{discharge}} + S^\text{trip}_{x,t}`

Conservative state of charge lower limit (if ``SOC_conserv is not None``):

:math:`\text{if} \quad t^{available}_{x,t} \quad \text{then} \quad E_{p,t} + S^\text{conserv}_{x,t} - L^\text{conserv} >=0`




Inverter
^^^^^^^^^^^^^
An inverter node has one AC port, and some number of DC ports


**Variables**

:math:`p^{dc}_{z, x, t}`, dc ports where :math:`z \in Z = \{0,1,2...\}`

:math:`p^{ac}_{x, t}`, ac port

**Parameters**

:math:`\eta^{dc-ac}`, dc to ac efficiency

:math:`\eta^{ac-dc}`, ac to dc efficiency

**Constraints**

The below constraint asserts that ac imports (:math:`p^{ac+}`) are subject to the :math:`\eta^{ac-dc}` efficiency, and ac exports (:math:`p^{ac-}`) are subject to the :math:`\eta^{dc-ac}` efficiency.

:math:`p^{ac+} \cdot \eta^{ac-dc} + p^{ac-} \cdot \eta^{dc-ac} = \sum_{i=1}^{z}p^{dc}_{i, x, t}`



Gas Nodes
-----------------

Gas Boiler Fixed COP
^^^^^^^^^^^^^^^^^^^^
**Description**:
A boiler converts gas to heat at a fixed coefficient of performance (COP). The COP is a unitless ratio between output energy and input energy. The boiler is either on, and must operate between a min and max input, or off. It has one input port (gas) and one output port (heat).

A weighted average of past inputs approach is used to introduce a ramp up/ramp down effect. For example, if a 10 kW boiler has a COP of 1, but a startup COP of 0.5, in the time period when it turns on, its output is :math:`0.5\cdot 10 + 0.5\cdot 0 = 5`, and in the next time step, its output is :math:`0.5\cdot 10 + 0.5\cdot 10 = 10`.


**Variables**:

:math:`p^{in}`, input port var 

:math:`p^{out}`, output port var 

:math:`p^{on}`, binary variable for when the boiler is on 

**Parameters**:

:math:`p^{max input}`, max input 

:math:`p^{min input}`, min input 

:math:`cop`, coefficient of performance = output/input 

:math:`cop^{init}`, initial cop in the time interval when the boiler starts. This acts as a ramp up (and ramp down) rate.

**Constraints**:

Off or constrained big M constraints:

:math:`p^{in} \geq p^{on} \cdot p^{min}`

:math:`p^{in} \leq p^{on} \cdot p^{max}`


Node transformation constraint:

:math:`p^{out}_{x, t} = p^{in}_{x, t} \cdot cop^{init} + p^{in}_{x, t-1} \cdot (cop - cop^{init})`


Temperature Controlled Gas Boiler
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
This node has a gas input port and a heating output port. It has additional variables representing its exit and return temperatures, which can be optimised.

**Variables**

:math:`p^{in}`, power in

:math:`p^{out}`, power out

:math:`temp^{exit}`, exit water temperature

:math:`temp^{return}`, return water temperature

**Parameters**

:math:`temp^{max-exit}`, max exit temperature

:math:`temp^{min-exit}`, min exit temperature

:math:`temp^{max-return}`, max return temperature

:math:`temp^{min-return}`, min return temperature

:math:`c`, a factor for converting degrees to kW (kW/deg)

:math:`cop`, coefficient of performance

**Constraints**

Temp bound constraints:

:math:`temp^{min-exit} \leq temp^{exit} \leq temp^{max-exit}`

:math:`temp^{min-return} \leq temp^{return} \leq temp^{max-return}`

Return temp constraint:

:math:`p^{out} = (temp^{return} - temp^{exit})\cdot c \cdot cop `

Exit temp constraint: 

:math:`p^{in} = (temp^{exit} - temp^{return})\cdot c `







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
See :ref:`Controllable Thermal Load`


Heat Pump
^^^^^^^^^^^^^
A heat pump converts electrical input to either heating output, or cooling output.

Dual Heat Pump
^^^^^^^^^^^^^^^
A dual heat pump is the same as a heat pump except it can convert electrical input to heating and cooling output simultaneously.

Chiller
^^^^^^^^^^^^^
This node has two ports, an input electrical port, and an output cooling port.



Other Nodes
------------------------

Carbon Source
^^^^^^^^^^^^^^^^^^^
A carbon source node is a source of carbon flows.


Carbon Sink
^^^^^^^^^^^^^^^^^^^
A carbon sink node is a sink of carbon flows.

Emitting Node
^^^^^^^^^^^^^^^^^
Node that generates emissions when it exports

Time Delay Node
^^^^^^^^^^^^^^^^
**Description**
A time delay node has two ports, one input, and one output. The throughput from input to output is delayed by some number of time intervals. It can be used to represent delays in a system, and is particularly appropriate for discrete/process based systems.

**Variables**

:math:`p^{in}`, flow in

:math:`p^{out}`, flow out

**Parameters**

:math:`td`, time delay in num. intervals

**Constraints**

Node transformation constraint:

:math:`p^{out}_{x, t} = -p^{in}_{x, t-td}`


Input Output ARX Node
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
This node has one input port and one output port. The output at each interval depends on current inputs, previous inputs, and previous outputs. The node transformation is defined by a coefficient array, which can be obtained by training an autoregressive (ARX) model on some data.


Template Node
^^^^^^^^^^^^^^^^^
**Description**

**Variables**

**Parameters**

**Constraints**
