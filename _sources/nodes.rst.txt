.. _Nodes_ref:

============
*echo* Nodes
============
Nodes represent physical or logical connection between edges of the network. Nodes are composed of a collection of ports, with a well-defined relationship between ports. Ports represent flows into and out of nodes. In general, the relationship between ports will be defined by a system of constraints, which define the *node transformation*. Nodes may also include other variables and parameters and constraints necessary to model:

* *Assets*: A node can represent a physical asset that is a source, sink, storage or generic transformation between commodities.
* *Interconnection / Hub*: A node can represent a physical or logical interconnection between edges in the network: such as busbar, electrical connection point, gas junction.

Some of the nodes described below come with pre-built ports of a certain type. In these cases, please refer to :ref:`echo Port object <Ports_ref>` which contains descriptions of port models.

.. note::
    Under the heading for each node, **parameters**, **variables**, and **constraints** may be defined. **Parameters** are typically defined when the node is created, and can be controlled by the user. **Variables** are pyomo variables, and **constraints** are also pyomo constraints, and these are created when *echo* model is into *pyomo* for optimisation.

    Some variables and constraints are always created, while others are conditionally created depending on user specified parameters. Please check whether variables and constraints of interest apply always or need to be turned on via a Node parameter.

Commodity Agnostic Nodes
-------------------------
Commodity agnostic nodes refer to the nodes that can be used across different commodities. To use these nodes, they must be instantiated with a unit that indicates the commodity type for the instance.

Flexible Source
^^^^^^^^^^^^^^^

A Flexible Source is a Node with one Port that can export a commodity.

Flexible Sink
^^^^^^^^^^^^^^^
A Flexible Sink is a Node with one Port that that can import a commodity.

Fixed Source
^^^^^^^^^^^^^^^
A Fixed Source is a Node with one Port that exports a fixed quantity of a given commodity.

Fixed Sink
^^^^^^^^^^^^^^^
A Fixed Sink is a Node with one Port that imports a fixed quantity of a given commodity.

Tellegen Node
^^^^^^^^^^^^^
A Tellegen Node is an energy conserving node that must have at least two ports. The sum of all flows through the Node's Ports must equal zero. It is used to represent interconnections, either physical or logical, between different flows in a network.

**Tellegen Node Constraints**

If the node has :math:`N` ports, each with a value of :math:`p^i_{x, t}` for :math:`i \in N`, then:

:math:`\sum_{i=0}^N p^i_{x, t} = 0`


Multi Commodity Tellegen
^^^^^^^^^^^^^^^^^^^^^^^^
A multi commodity Tellegen Node is an energy conserving node. The sum of all flows of the same commodity through the node must equal zero. This node does not necessarily represent a physical interconnection, but it is useful for representing logical connections (e.g., a building that has both gas and electricity supply).

Like the Tellegen node, the Multi Commodity Tellegen node requires at least two ports per commodity.

The node constraint is the same as :ref:`Tellegen <Tellegen Node>`, but a separate constraint is applied per commodity type.

Linear Input Output Node
^^^^^^^^^^^^^^^^^^^^^^^^^
An input output node has one input port :math:`p^\text{in}`, and one output port, :math:`p^\text{out}`. The input port always imports a commodity, but the output port can either import or export a commodity. The transformation between input and output is linear.


**Parameters**

* ``weight`` (:math:`w`): a weight used to transform the input into the output. The weight can be a single value, or an array of factors.


**Linear Input Output Constraints**

:math:`p^\text{out} = p^\text{in} \cdot w`


Single Piecewise Input Output Node
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
This node has one input port and one output port. The transformation between input and output is defined by a piecewise linear function that approximates a nonlinear relationship using straight line segments. This node is useful for approximating generic nonlinear transformations where the transformation is known or can be precalculated.

This node should only be used when capturing a nonlinear transformation as accurate is possible is important in achieving the overall modelling goal, because it is computationally expensive to use a piecewise approximation compared to a linear input/output transformation.

An example of defining a piecewise input output node is

.. code-block::

    input_pts = [0, 5, 12, 20]
    output_pts = [-3, -7, -30, -50]

    node = SinglePiecewiseIONode()
    node.add_input_pts(input_pts, time_periods, expansion_periods)
    node.add_output_pts(input_pts, time_periods, expansion_periods)


**Parameters**

* ``input_pts``: array of points corresponding to possible values of the input port
* ``output_pts``: array of points corresponding to possible values of the output port

``input_pts`` and ``output_pts`` must be the same length, and should be defined over the range of values that the input and output ports can take, because the bounds on each port will be calculated based on ``input_pts`` and ``output_pts``.

**Constraints**

If the piecewise function is denoted :math:`f`, and the input port is :math:`p^\text{in}_{x, t}` and the output port is :math:`p^\text{out}_{x, t}`, then:

:math:`p^\text{out} = f(p^\text{in})`


Controlled Load
^^^^^^^^^^^^^^^^^
A controlled load must be operated within a minimum and maximum utilisation, and between a minimum and maximum power/flow rate.

Min utilisation is the ratio between the minimum energy consumed, and the maxinimum energy that would be consumed if the load operated at max power.

Max utilisation is the ratio between the maximum energy consumed, and the maximum energy that would be consumed if the load operated at max power.

An example of initialising a controlled load is

.. code-block:: python

    controlled_load = ControlledLoad(max_power=10,
                                     min_power=0,
                                     min_utilisation = 0.5,
                                     max_utilisation = None)

**Variables**

:math:`p_{x, t}`, the power consumed by the load, indexed by planning and time interval

**Parameters**

* :math:`p^\text{max}`, the maximum power consumed by the load

* :math:`p^\text{min}`, the minimum power consumed by the load

* :math:`util^\text{min}`, the minimum utilisation

* :math:`util^\text{max}`, the maximum utilisation

* :math:`d^\text{interval}`, the time interval in minutes

* :math:`d^\text{total}`, the total number of time intervals

**Constraints**

If there is a minimum utilisation specified:

:math:`\sum_{i=0}^x \sum_{j=0}^t p_{i, j} \cdot \frac{d^\text{interval}}{60} \geq util^\text{min} \cdot p^\text{max} \cdot \frac{d^\text{interval}}{60} \cdot d^\text{total}`

If there is a maximum utilisation specified:

:math:`\sum_{i=0}^x \sum_{j=0}^t p_{i, j} \cdot \frac{d^\text{interval}}{60} \leq util^\text{max} \cdot p^\text{max} \cdot \frac{d^\text{interval}}{60} \cdot d^\text{total}`


Controlled Generation
^^^^^^^^^^^^^^^^^^^^^
This node must be operated within a minimum and maximum utilisation, and between a minimum and maximum power/flow rate.

Min utilisation is the ratio between the minimum energy generated, and the maxinimum energy that would be generated if the generation was operated at max power.

Max utilisation is the ratio between the maximum energy generated, and the maximum energy that would be generated if the generation was operated at max power.

**Constraints**

The constraints are the same as for :ref:`Controlled Load`


Electrical Nodes
----------------------

Battery
^^^^^^^^^^^^^^^^^
The battery node can be used to model electrical storage. This node can only ever import, or export, it cannot simultaneously import and export. It has one storage port, which holds most of the parameters.

An example of initialising a battery node is

.. code-block::

    battery = Battery(port_name='battery',
                      max_capacity=15.0,
                      depth_of_discharge_limit=0,
                      charging_power_limit=1.25,
                      discharging_power_limit=-1.25,
                      charging_efficiency=1,
                      discharging_efficiency=1,
                      initial_state_of_charge=0.0)


**Parameters**

* ``port_name``: The name of the port on the battery node

* For the remaining parameters, see :ref:`Storage` in :ref:`*echo* Ports`.

**Variables**

See :ref:`Storage` in :ref:`*echo* Ports`.

**Constraints**

See :ref:`Storage` in :ref:`*echo* Ports`.

Solar
^^^^^^^^^^^^^^^^^
A solar node has one port, which exports electrical energy. The amount of energy exported at each time is fixed according to a generation profile, which the user specifies.

An example of initialising a solar node is

.. code-block::

    solar_profile = np.array([0]*7 + [0.2]*1 +[0.4]*1 + [0.8]*2 +
                             [1]*2 + [0.8]*2 + [0.4]*1 + [0.2]*1 + [0]*7)*100

    solar = Solar(port_name='pv',
                    curtailable=True,
                    profile=solar_profile)


**Parameters**

* ``port_name``: The name of the port on the solar node.

* ``profile``: The generation profile for the solar node, given in kW average per time interval. This can be specified using a numpy array, a list of values, or a dictionary, where the dictionary keys are ``(planning_period, time_period)``.

* ``curtailable``: Set to ``True`` if solar generation can be curtailed (i.e., reduced for some number of time intervals). Default is ``False``.


**Constraints**

If ``curtailable`` is ``True``, and the profile is given by the parameter :math:`p^\text{max}`, and actual solar generation is given by :math:`p`:

:math:`p \leq p^\text{max}`


EV
^^^^^^^^^^^^^
The EV node can be used to model the charging (and discharging) while ensuring that the EV has
enough available charge to meet its trip requirements. The EV node requires the following data:

* ``available`` (:math:`t^\text{available}`): An array representing the periods which the EV is plugged in and available for charging. 1=available to charge, 0=not available.
* ``usage`` (:math:`p^\text{usage}`): An array representing the average power (kW) consumption from driving of the EV during a time interval.

Both usage and available should have the same length and importantly available should be zero whenever usage has a value
greater than zero (i.e. if the car is in use driving it is not available to charge).

The EV can be specified to charge in 3 different modes. This is controlled by setting ``charge_mode`` to one of 'V0G', 'V1G' or 'V2G'
which are defined as:

* V0G: non-optimised convenience or time of day charging. Whenever the car is available it will charge at its maximum charging power until full. Alternative, a time-of-day array can be supplied specifying certain time intervals during which charging is allowed.
* V1G: optimised uni-directional charging (grid to vehicle only). The car is charged from the upstream grid in a way that optimises the model objectives.
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
and a trip usage port (i.e., a load port). Each of these ports has the associated set of parameters/variables previously defined (see :ref:`*echo* Ports`).
Only EV specific additional parameters/variables are defined below.

**Parameters**

* ``SOC_conserv`` (:math:`L^\text{conserv}`): conservative state of charge limit below which the EV should not discharge to the grid. This reflects that an EV owner would want to ensure a certain amount of charge is available impromptu trips. This lower bound only applies while the EV is available to charge (i.e., soc lower bound while :math:`p^\text{available}=1`).
* ``SOC_conserv_cost`` (:math:`C^\text{conserv}`): The cost placed on going below the conservative state of charge limit ($/kWh). That is, the conservative state of charge lower limit will be ignored if it would result in saving (or gaining) more money than this cost.

.. warning::
    ``SOC_conserv_cost`` will be incorrectly over represented in the objective cost as it will be applied whenever the car was plugged back in below :math:`C^\text{conserv}`.

* ``trip_slack``: A boolean enabling or disabling slack trips (recommended=True). If enabled, then any trips that require more than the available energy will be assumed to have charged at a public charger and the optimisation will still succeed and be considered feasible. The cost on this public charging is by default very high and so will be treated as a last resort by the optimisation solver. It is recommended that ``trip_slack`` is ``True`` in case the data contains any infeasible trips.
* ``tod_charging``: Time of day charging. An array or list if enabled, otherwise false. Time of day charging allows the EV to charge only during certain time windows (1=allowed, 0=not allowed). This is because customers might not want to charge during peak windows and would most commonly be used with V0G charging.

**Variables**

* :math:`p^\text{cp}_{x, t}`, connection point port power (kW).
* :math:`p^\text{battery}_{x, t}`, battery port power (kW).
* :math:`p^\text{trip}_{x, t}`, trip usage port power (kW).
* :math:`S^\text{trip}_{x, t}`, value of the trip slack variable (kWh). That is, the amount of energy that was required to be charged at a public charger in order to make a trip feasible.
* :math:`S^\text{conserv}`, value of a slack variable required for the implementation of the conservative lower limit.

**Constraints**

Balance of power across ports:

:math:`p^\text{battery}_{x, t} = p^\text{cp}_{x, t} - p^\text{trip}_{x, t}`

If ``trip_slack`` is ``True``, the modified battery state of charge equation accounting for the trip slack variable is:

:math:`E_{x, t} = E_{x,t-1} + \eta^\text{charge} p^\text{battery,+}_{x,t} d^\text{interval} + p^\text{battery, -}_{x,t} \frac{d^\text{interval}}{\eta^\text{discharge}} + S^\text{trip}_{x,t}`

If ``SOC_conserv is not None``, conservative state of charge lower limit:

:math:`\text{if} \quad t^\text{available}_{x,t} \quad \text{then} \quad E_{p,t} + S^\text{conserv}_{x,t} - L^\text{conserv} \geq 0`



Inverter
^^^^^^^^^^^^^
An inverter node represents AC/DC inverter, that converts alternating current (AC) to direct current (DC) and visa versa. It has one AC port, and at least one DC port.

An example of initialising an inverter is:

.. code-block::

    inverter = Inverter(max_import=20,
                        max_export=-20,
                        dc_ac_efficiency=0.9,
                        ac_dc_efficiency=0.8,
                        ac_port='ac',
                        dc_ports = ['battery', 'solar'])

**Parameters**

* ``max_import``: maximum power the inverter can import through its AC port
* ``max_export``: maximum power the inverter can export through its AC port
* ``dc_ac_efficiency`` (:math:`\eta^\text{export}`): conversion efficiency when converting DC to AC (exporting)
* ``ac_dc_efficiency`` (:math:`\eta^\text{import}`): conversion efficiency when converting AC to DC (importing)


**Variables**

:math:`P^\text{dc}_{x, t}`, total power at DC ports

:math:`P^\text{ac}_{x, t}`, power at AC port

:math:`P^\text{ac+}_{x, t}`, positive power at AC port (i.e., power imported)

:math:`P^\text{ac-}_{x, t}`, negative power at AC port (i.e., power exported)


**Constraints**

The below constraint enforces that the appropriate efficiencies are applied to the appropriate flows into and out of the inverter:

:math:`P^\text{ac+} \cdot \eta^\text{import} + p^\text{ac-} \cdot \eta^\text{export} = -1 \cdot P^\text{dc}_{x, t}`



Gas Nodes
-----------------

Gas Boiler Fixed COP
^^^^^^^^^^^^^^^^^^^^
This Node models a boiler that converts gas to heat at a fixed coefficient of performance (COP).
The COP is a unitless ratio between output energy and input energy.
The boiler is either on, and must operate between a min and max input, or off.
It has one gas input port (units of Joules per second) and one thermal output port (units of KW thermal).

An example of initialising a fixed COP gas boiler is

.. code-block::

    gas_boiler = GasBoilerFixedCOP(max_input=10,
                                   min_input=5,
                                   cop=0.8,
                                   startup_cop=0.6)



**Parameters**

* ``max_input`` (:math:`p^\text{max}`): maximum input

* ``min_input`` (:math:`p^\text{min}`): minimum input

* ``cop`` (:math:`C`): coefficient of performance, output/input energy.

* ``startup_cop`` (:math:`C^\text{init}`): coefficient of performance at the startup, output/input energy.

**Variables**

:math:`p^\text{in}_{x, t}`, input (J/s)

:math:`p^\text{out}_{x, t}`, output (kW thermal)

:math:`p^\text{on}_{x, t}`, binary variable for when the boiler is on


**Constraints**:

When boiler is on (:math:`p^\text{on}_{x, t} = 1`) the following constraints apply:

:math:`p^\text{in} \geq p^\text{on} \cdot p^\text{min}`

:math:`p^\text{in} \leq p^\text{on} \cdot p^\text{max}`

We use a weighted sum of past inputs approach to calculate the COP at a given time interval.
This constraint enforces that when the boiler turns on, in the first optimisation period after the boiler goes from *Off* to *On* state it will operate at ``startup_cop`` and for subsequent periods it will operate at ``cop``. When the boiler turns off, it will operate at a lower efficiency, and then reach zero in the next time step.


:math:`p^\text{out}_{x, t} = p^\text{in}_{x, t} \cdot C^\text{init} + p^\text{in}_{x, t-1} \cdot (C - C^\text{init})`

For example, if a 10 kW boiler has a ``cop = 1`` and ``startup_cop = 0.7``. In the time interval when the boiler turns on, its output is :math:`p^\text{out} = 7`,
and in the next time step, :math:`p^\text{out} = 10`. Assume it operates at :math:`p^\text{out}=10` for some time, before turning off. In the time interval it turns off, :math:`p^\text{out}= 3`. In the next period :math:`p^\text{out}= 0`.


Temperature Controlled Gas Boiler
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
This Node has a gas input port and a thermal output port.
This Node models a boiler that converts gas to heat at a fixed coefficient of performance (COP),in addition it has variables representing the exit and return temperatures of its working fluid.
These temperature variables can be optimised within a range.

An example of initialising a temperature controlled gas boiler is

.. code-block::

    boiler = TempControlledBoiler(max_input=100,
                                  min_input=15,
                                  deg_to_kw=1,
                                  cop=1,
                                  startup_cop=1,
                                  )

**Parameters**

* ``max_input``: see :ref:`Gas Boiler Fixed COP`

* ``min_input``: see :ref:`Gas Boiler Fixed COP`

* ``deg_to_kW`` (:math:`\alpha`):  a factor that equals :math:`\frac{\Delta T}{kW}`, used for converting a temperature difference to kW heating or cooling.

* ``cop`` (:math:`C`): see :ref:`Gas Boiler Fixed COP`

* ``startup_cop`` (:math:`C^\text{init}`): see :ref:`Gas Boiler Fixed COP`

* ``exit_temp_bounds`` (:math:`ET^\text{min}`, :math:`ET^\text{max}`): tuple of lower and upper bounds on the exit temperature

* ``return_temp_bounds`` (:math:`RT^\text{min}`, :math:`RT^\text{max}`): tuple of lower and upper bounds on the exit temperature


**Variables**

:math:`p^\text{in}_{x, t}`, gas in

:math:`p^\text{out}_{x, t}`, power out

:math:`ET`, exit water temperature

:math:`RT`, return water temperature


**Constraints**

Constraints on the exit and return temperatures.

:math:`ET^\text{min} \leq ET \leq ET^\text{max}`

:math:`RT^\text{min} \leq RT \leq RT^\text{max}`

Return temp constraint:

:math:`p^\text{out} = (RT - ET)\cdot \alpha \cdot C`

Exit temp constraint: 

:math:`p^\text{in} = (ET - RT)\cdot \alpha`

TBC - add startup cop


Thermal Nodes
---------------------

Controllable Thermal Load
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
A Controllable Thermal Load node represents a heating and/or cooling load. For example, this node can be used to represent a building's overall thermal load, or specific loads for things like space heating, hot water heating, or other industrial processes. This node supports an arbitrary number of ports, so that the node can be connected to various heating/cooling sources.

Heating is denoted by positive values (indicating that heat is imported).
Cooling is denoted by negative values (indicating that heat is exported, i.e. removed).

An example of initialising a controllable thermal load that is supplied by a single source that can provide heating and cooling is

.. code-block::

        time_periods = 24
        expansion_periods = 1
        external_temp = [2] * time_periods
        external_temp_dict = generate_dict_with_pyomo_keys_from_array(external_temp, time_periods, expansion_periods)
        temp_lb = [0] * 8 + [18] * 8 + [0] * 8
        temp_ub = [10] * 8 + [25] * 8 + [10] * 8
        temp_lb_dict = generate_dict_with_pyomo_keys_from_array(temp_lb, time_periods, expansion_periods)
        temp_ub_dict = generate_dict_with_pyomo_keys_from_array(temp_ub, time_periods, expansion_periods)

        thermal_load = ThermalNode(temp_ub=temp_ub_dict,
                                   temp_lb=temp_ub_dict,
                                   external_temp=external_temp_dict,
                                   temp_to_energy_coef=1,
                                   loss_factor=0.0,
                                   gain_factor=0.0,
                                   initial_internal_temp=0
                                   )
        thermal_load.add_thermal_port('load')

An example of initialising a controllable thermal load that is supplied by separate heating and cooling sources is

.. code-block::


        thermal_load = ThermalNode(temp_ub=temp_ub_dict,
                                   temp_lb=temp_ub_dict,
                                   external_temp=external_temp_dict,
                                   temp_to_energy_coef=1,
                                   loss_factor=0.0,
                                   gain_factor=0.0,
                                   initial_internal_temp=0
                                   )
        thermal_load.add_heating_port('heating_load')
        thermal_load.add_cooling_port('cooling_load')


**Parameters**:

* ``temp_ub`` (:math:`T^\text{ub}`): temperature upper bound entered as a dictionary of values

* ``temp_lb`` (:math:`T^\text{lb}`): temperature lower bound entered as a dictionary of values

* ``external_temp`` (:math:`T^\text{ambient}`): ambient temperature entered as a dictionary of values

* ``temp_to_energy_coef`` (:math:`\alpha`): a factor that equals :math:`\frac{\Delta T}{kW}`, used for converting a temperature difference to kW heating or cooling.

* ``loss_factor`` (:math:`\eta^\text{loss}`): a loss factor/efficiency

* ``gain_factor`` (:math:`\eta^\text{gain}`): a gain factor/efficiency

**Variables**:

:math:`P_{x, t}`, total heating and cooling kW at the node

:math:`T^\text{internal}_{x, t}`, the internal temperature of the thermal load

:math:`E^\text{loss}_{x, t}`, energy loss due to internal temperature being > ambient temperature

:math:`E^\text{gain}_{x, t}`, energy gain due to internal temperature being < ambient temperature

:math:`E^*_{x, t}`, binary variable for splitting losses and gains


**Constraints**:

Loss and gain sum constraint:

:math:`E^\text{loss} + E^\text{gain} = (T^\text{ambient} - T^\text{internal}) \cdot \alpha`

Loss and gain big M constraints, to make sure that the variables are split correctly:

:math:`E^\text{loss} \geq (E^* - 1) \cdot M`

:math:`E^\text{gain} \leq E^* \cdot M`


Constraint relating the heating/cooling delivered to the node to the internal temperature and the losses/gains.

:math:`P_{x, t} + \eta^\text{loss} \cdot E^\text{loss}_{x, t}+ \eta^\text{gain} \cdot E^\text{gain}_{x, t} = (T^\text{internal}_{x, t} - T^\text{internal}_{x, t-1}) \cdot \alpha`


Heat Pump Single Output
^^^^^^^^^^^^^^^^^^^^^^^
This Node models a heat pump that converts electrical energy into either heating or cooling output.
A single output heat pump has one input electrical port :math:`p^\text{in}_{x, t}`, and one output thermal port :math:`p^\text{out}_{x, t}` that can either be positive (behaving as a heat sink, or cooling source), or negative (behaving as a heat source).
An example of initialising a single output heat pump is

.. code-block::

    time_periods = 24
    heating_cop = np.array([0.8] * time_periods)
    cooling_cop = np.array([2] * time_periods)
    heat_cop_dict = generate_dict_with_pyomo_keys_from_array(heating_cop, time_periods)
    cool_cop_dict = generate_dict_with_pyomo_keys_from_array(cooling_cop, time_periods)

    heat_pump = HeatPumpSingleOutput(heating_cop_time_series=heat_cop_dict,
                                     cooling_cop_time_series=cool_cop_dict)


The coefficients of performance are provided as parameters because they can be calculated prior to optimisation, based on the forecasted or historical ambient temperature data.

**Parameters**

* ``heating_cop_time_series`` (:math:`COP^\text{heat}`): a dict of time series coefficients of performance for heating.

* ``cool_cop_time_series`` (:math:`COP^\text{cool}`): a dict time series of coefficients of performance for cooling.

Both dicts should have keys ``(planning_period, time_period)``.

**Variables**

:math:`H^\text{in}_{x, t}`, electrical input used for heating

:math:`C^\text{in}_{x, t}`, electrical input used for cooling

:math:`b^*_{x, t}`, binary variable that indicates whether the output port is cooling (:math:`b^*=1`) or heating (:math:`b^*=0`)

:math:`p^\text{in}_{x, t}`, electrical power in

:math:`p^\text{out-}_{x, t}`, heating out

:math:`p^\text{out+}_{x, t}`, cooling out


**Constraints**

Summing constraint, enforcing that the electrical input used for heating and the electrical input used for cooling equals the total electrical input:

:math:`H^\text{in} + C^\text{in} = p^\text{in}`

Big M constraint pair for enforcing that when the cooling indicator variable, :math:`b^*`, is 1, :math:`H^\text{in}=0`, and vice versa.

:math:`H^\text{in} \leq (1 - b^*) \cdot M`

:math:`C^\text{in} \leq b^* \cdot M`


Heating output constraint:

:math:`p^\text{out-}_{x, t} = H^\text{in}_{x, t} \cdot COP^\text{heat}_{x, t}`

Cooling output constraint:

:math:`p^\text{out+}_{x, t} = C^\text{in}_{x, t} \cdot COP^\text{cool}_{x, t}`


Heat Pump Dual Output
^^^^^^^^^^^^^^^^^^^^^
A heat pump with dual outputs has separate ports for heating and cooling, and can be used to serve separate heating and cooling loads.
It has one input electrical port :math:`p^\text{in}_{x, t}`, one output thermal port for heating (export only) :math:`p^\text{heat out}_{x, t}`, and one output port for cooling (import only) :math:`p^\text{cool out}_{x, t}`.

An example of initialising a dual output heat pump is

.. code-block::

    time_periods = 24
    heating_cop = np.array([0.8] * time_periods)
    cooling_cop = np.array([2] * time_periods)
    heat_cop_dict = generate_dict_with_pyomo_keys_from_array(heating_cop, time_periods)
    cool_cop_dict = generate_dict_with_pyomo_keys_from_array(cooling_cop, time_periods)

    heat_pump = HeatPumpDualOutput(heating_cop_time_series=heat_cop_dict,
                                   cooling_cop_time_series=cool_cop_dict)


The parameters, constraints, and variables are otherwise the same as :ref:`Heat Pump Single Output`. 
The only difference is that instead of splitting port :math:`p^\text{out}` into negative component :math:`p^\text{out-}` representing the heating output, and positive component :math:`p^\text{out+}` representing the cooling output, separate ports :math:`p^\text{heat out}` and :math:`p^\text{cool out}` are used. Therefore, the final pair of constraints are:

Heating output constraint:

:math:`p^\text{heat out}_{x, t} = H^\text{in}_{x, t} \cdot COP^\text{heat}_{x, t}`

Cooling output constraint:

:math:`p^\text{cool out}_{x, t} = C^\text{in}_{x, t} \cdot COP^\text{cool}_{x, t}`



Chiller
^^^^^^^^^^^^^
A Chiller node has two ports, an input electrical port :math:`p^\text{in}_{x, t}`, and an output cooling port :math:`p^\text{out}_{x, t}`. It converts electrical input to cooling according to a coefficient of performance (COP), which depends on ambient temperature, as well as loading (current input/nominal rating).



**Parameters**

* ``input_pts``, an array of input pts. Can either provide the same input points for every time interval, or provide one per time interval, in order to accommodate any temperature effects.

* ``output_pts``, an array of corresponding output pts. Can either provide the same input points for every time interval, or provide one per time interval, in order to accommodate any temperature effects.

.. note::
    ``input_pts`` and ``output_pts`` should cover the operational range of the chiller. Max input and output will be calculated based on these arrays.

**Constraints**

If the piecewise function is denoted :math:`f`, and the input port is :math:`p^\text{in}` and the output port is :math:`p^\text{out}`, then:

:math:`p^\text{out} = f(p^\text{in})`

TBC do this better






Other Nodes
------------------------

Emitting Node
^^^^^^^^^^^^^^^^^
An emitting node has a port :math:`p^\text{emit}_{x, t}` that generates emissions when it exports, and another port that generates carbon :math:`p^\text{carbon}_{x, t}`.


**Parameters**

* :math:`EF_{x, t}`, emissions factor in units of kgCO2 per flow unit of the emitting port. For example, if the emitting commodity is electricity, the emissions factor would have units kgCO2 per kW. This can be a single factor or an array of factors.

.. note::
    Emission factors are usually specified in units of kgCO2 per energy unit (e.g., kgCO2/kWh). The factors should be converted using the appropriate time interval so that they are in the units described above.

**Constraints**

Note that the constraint below uses the negative (exporting) component of :math:`p^\text{emit}`:

:math:`p^\text{carbon} = p^\text{emit-} \cdot EF`


Carbon Aggregation
^^^^^^^^^^^^^^^^^^^
A carbon aggregation node can have an arbitrary number of carbon ports. These ports will usually be a sink of carbon (importing). It has an additional variable called :math:`total_{x, t}` which tracks the total carbon at the node. This can be useful for aggregation all the carbon emissions in a model in one place.

**Variables**

:math:`total_{x, t}`, the sum of all port variables on the node

**Constraints**

If the node has N ports, each with a value of :math:`p_i` for :math:`i \in N`, then:

:math:`total = \sum_{i=0}^N p_i`


Time Delay Node
^^^^^^^^^^^^^^^^
A time delay node has two ports, one input :math:`p^\text{in}_{x, t}`, and one output :math:`p^\text{out}_{x, t}`. The input port always imports, and the output port always exports. The throughput from input to output is delayed by some number of time intervals.

This node can be used to represent delays in a system, and is particularly appropriate for discrete/process based systems. The time delay can also be set to 0 to model feedback loops.

**Parameters**

* :math:`d`, time delay in number of time intervals

**Constraints**

:math:`p^\text{out}_{x, t} = -p^\text{in}_{x, t-d}`


Input Output ARX Node
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
This node has one input port :math:`p^\text{in}_{x, t}` and one output port :math:`p^\text{out}_{x, t}`. The output at each interval depends on current inputs, previous inputs, and previous outputs. The dependence of the current output on on previous outputs is defined by coefficient array :math:`a`, and the dependence on current and previous inputs is defined by coefficient array :math:`b`


**Constraints**

TBC


Template Node
^^^^^^^^^^^^^^^^^


**Variables**

**Parameters**

**Constraints**


Custom Nodes
^^^^^^^^^^^^^^^^
Write something here about how to built generic linear transformations for nodes
