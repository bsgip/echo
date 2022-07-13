============
*echo* Nodes
============
Nodes represent physical or logical connection between edges of the network. Nodes are composed of a collection of ports, with a well-defined relationship between ports. Ports represent flows into and out of nodes. In general, the relationship between ports will be defined by a system of constraints, which we call the *node transformation*. Nodes may also include other variables and parameters and constraints necessary to model:

* *Assets*: A node can represent a physical asset that is a source, sink, storage or generic transformation between commodities.
* *Interconnection / Hub*: A node can represent a physical or logical interconnection between edges in the network: such as busbar, electrical connection point, gas junction.

Some of the nodes described below come with pre-built ports of a certain type. In these cases, please refer to :ref:`*echo* Port object` which contains descriptions of port models.

Commodity Agnostic Nodes
-------------------------
Commodity agnostic nodes refer to nodes without a specific commodity. To use these nodes, they must be instantiated with a unit that indicates the commodity type.

Flexible Source
^^^^^^^^^^^^^^^

A flexible source is a node with one port that exports some commodity.

Flexible Sink
^^^^^^^^^^^^^^^
A flexible sink is a node with one port that imports some commodity.

Fixed Source
^^^^^^^^^^^^^^^
A fixed source is a node with one port that exports a fixed quantity of a given commodity.

Fixed Sink
^^^^^^^^^^^^^^^
A fixed sink is a node with one port that imports a fixed quantity of a given commodity.

Tellegen
^^^^^^^^^^^^^
A tellegen node is an energy conserving node. The sum of all flows through the node must equal 0. It is used to represent interconnections, either physical or logical, between different flows in a network.

Multi Commodity Tellegen
^^^^^^^^^^^^^
A multi commodity tellegen node is an energy conserving node. The sum of all flows of the same commodity through the node must equal 0. This node does not necessarily represent a physical interconnection, but it is useful for representing logical connections (e.g., a building that has both gas and electricity supply).

Input Output Node
^^^^^^^^^^^^^^^^^
An input output node has one input port, and one output port. The input port always imports a commodity, but the output port can either import or export a commodity.

Single Piecewise Input Output Node
^^^^^^^^^^^^^^^^^^^^^^^^^^^
This node has one input port and one output port. The transformation between input and output is defined by a piecewise function that approximates a nonlinear relationship using straight line segments. This node is useful for approximating generic nonlinear transformations where the transformation is known or can be precalculated.

This node should only be used when capturing a nonlinear transformation precisely is important in achieving the overall modelling aim, because it is computationally expensive to use a piecewise approximation compared to a linear input/output transformation.

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

If the piecewise function is denote :math:`f`, and the input port is :math:`p^\text{in}` and the output port is :math:`p^\text{out}`, then: 

:math:`p^\text{out} = f(p^\text{in})`


Controlled Load
^^^^^^^^^^^^^^^^^
A controlled load must be operated within a minimum and maximum utilisation, and between a minimum and maximum power/flow rate.

Min utilisation is the ratio between the minimum energy consumed, and the maxinimum energy that would be consumed if the load operated at max power.

Max utilisation is the ratio between the maximum energy consumed, and the maximum energy that would be consumed if the load operated at max power.

**Variables**

:math:`p`, the power consumed by the load, indexed by planning and time interval

:math:`p^\text{max}`, the maximum power consumed by the load

:math:`p^\text{min}`, the minimum power consumed by the load

:math:`util^\text{min}`, the minimum utilisation

:math:`util^\text{max}`, the maximum utilisation

**Parameters**

:math:`d^\text{interval}`, the time interval in minutes

:math:`d^\text{total}`, the total number of time intervals

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

The constraints are the same as defined for :ref:`Controlled Load`


Electrical Nodes
----------------------

Battery
^^^^^^^^^^^^^^^^^
The battery node can be used to model electrical storage. A battery holds some energy, or charge. The battery node can import energy and increase its state of charge, or export energy, which decreases its state of charge.
This node can only ever import, or export, it cannot simultaneously import and export.

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

* ``max_capacity`` (:math:`E^\text{max}`): Maximum battery capacity in kWh

* ``depth_of_discharge_limit`` (:math:`dod`): Percentage to which the battery can discharge to, written as a decimal.

* ``charging_power_limit`` (:math:`lim^\text{charge}`): Limit on charging power in kW

* ``discharging_power_limit`` (:math:`lim^\text{discharge}`): Limit on discharging power in kW

* ``charging_efficiency`` (:math:`\eta^\text{charge}`): Efficiency that applies when converting energy imported to a change in stored energy.

* ``discharging_efficiency`` (:math:`\eta^\text{discharge}`): Efficiency that applies when converting energy exported to a change in stored energy.

* ``initial_state_of_charge``: Initial state of charge of the battery in kWh



* ``fixed_storage_capacity``: If ``True`` storage capacity is optimised between 0 and ``max capacity``. Default is ``False``

* ``storage_capacity_cost``: Cost on storage capacity in $ per kWh. Needs to be set to some value if ``fixed_storage_capacity`` is ``True``. Default is ``None``.

* ``regularise``: Optional regularisation term on the battery. Default is ``False``.

**Variables**

:math:`p`, power at battery

:math:`p^+`, power imported by the battery

:math:`p^-`, power exported by the battery

:math:`E`, energy stored in the battery


**Constraints**

Charging/discharging constraint:

:math:`lim^\text{discharge} \leq p \leq lim^\text{charge}`

State of charge constraint:

:math:`E_{x, t} = E_{x, t-1} + p^+_{x, t} \cdot \eta^\text{charge} + p^-_{x, t} \cdot \eta^\text{discharge}`


Depth of discharge constraint:

:math:`E^\text{max} \cdot dod \leq E \leq E^\text{max}`



Solar
^^^^^^^^^^^^^^^^^
A solar node has one port, which exports electrical energy. The amount of energy exported at each time is fixed according to a generation profile, which the user specifies.

An example of initialising a solar node is

.. code-block::

    solar_profile = np.array([0]*7 + [0.2]*1 +[0.4]*1 + [0.8]*2 +
                             [1]*2 + [0.8]*2 + [0.4]*1 + [0.2]*1 + [0]*7)*100

    battery = Solar(port_name='pv',
                    curtailable=True,
                    profile =solar_profile)


**Parameters**

*``port_name``: The name of the port on the solar node.
* ``profile``: The generation profile for the solar node, given in kW average per time interval. This can be specified using a numpy array, a list of values, or a dictionary, where the dictionary keys are ``(planning_period, time_period)``.
* ``curtailable``: Set to ``True`` if solar generation can be curtailed (i.e., reduced for some number of time periods). Default is ``False``.


**Constraints**

If ``curtailable`` is ``True``, and our profile is given by the parameter :math:`p^\text{max}`, and actual solar generation is given by :math:`p`:

:math:`p \leq p^\text{max}`


EV
^^^^^^^^^^^^^
The EV node can be used to model the charging (and discharging) while ensuring that the EV has
enough available charge to meet its trip requirements. The EV node requires the following data:

* ``available`` (:math:`t^\text{available}`): An array representing the periods which the EV is plugged in and available for charging. 1=available to charge, 0=not available.
* ``usage`` (:math:`p^\text{usage}`): An array representing the average power (kW) consumption from driving of the EV during a time period.

Both usage and available should have the same length and importantly available should be zero whenever usage has a value
greater than zero (i.e. if the car is in use driving it is not available to charge).

The EV can be specified to charge in 3 different modes. This is controlled by setting ``charge_mode`` to one of 'V0G', 'V1G' or 'V2G'
which are defined as:

* V0G: non-optimised convenience or time of day charging. Whenever the car is available it will charge at its maximum charging power until full. Alternative, a time-of-day array can be supplied specifying certain time periods during which charging is allowed.
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
and a trip usage port (i.e., a load port). Each of these ports has the associated set of parameters/variables previously defined (see :ref:`*echo* Port object`).
Only EV specific additional parameters/variables are defined below.

**Parameters**

* ``SOC_conserv`` (:math:`L^\text{\text{conserv}}`): conservative state of charge limit below which the EV should not discharge to the grid. This reflects that an EV owner would want to ensure a certain amount of charge is available impromptu trips. This lower bound only applies while the EV is available to charge (i.e., soc lower bound while p^\text{available}=1).
* ``SOC_conserv_cost (``:math:`C^\text{conserv}`): The cost placed on going below the conservative state of charge limit ($/kWh). That is, the conservative state of charge lower limit will be ignored if it would result in saving (or gaining) more money than this cost. Warning, this cost will be incorrectly over represented in the objective cost as it will be applied whenever the car was plugged back in below :math:`C^\text{conserv}`.
* ``trip_slack``: A boolean enabling or disabling slack trips (recommended=True). If enabled, then any trips that require more than the available energy will be assumed to have charged at a public charger and the optimisation will still succeed and be considered feasible. The cost on this public charging is by default very high and so will be treated as a last resort by the optimisation solver. It is recommended that this is True in case the data contains any infeasible trips.
* ``tod_charging``: Time of day charging. An array or list if enabled, otherwise false. Time of day charging allows the EV to charge only during certain time windows (1=allowed, 0=not allowed). This is because customers might not want to charge during peak windows and would most commonly be used with V0G charging.

**Variables**

* :math:`p^\text{cp}`: connection point port power (kW).
* :math:`p^\text{battery}`: battery port power (kW).
* :math:`p^\text{trip}`: trip usage port power (kW).
* :math:`S^\text{trip}`: value of the trip slack variable (kWh). That is, the amount of energy that was required to be charged at a public charger in order to make a trip feasible.
* :math:`S^\text{conserv}`: Value of a slack variable required for the implementation of the conservative lower limit.

**Constraints**

Balance of power across ports:

:math:`p^\text{battery}_{x, t} = p^\text{cp}_{x, t} - p^\text{trip}_{x, t}`

The modified battery state of charge equations accounting for the trip slack variable (if ``trip_slack`` is ``True``):

:math:`E_{x, t} = E_{x,t-1} + \eta^\text{charge} p^\text{battery,+}_{x,t} d^\text{interval} + p^\text{battery, -}_{x,t} \frac{d^\text{interval}}{\eta^\text{discharge}} + S^\text{trip}_{x,t}`

Conservative state of charge lower limit (if ``SOC_conserv is not None``):

:math:`\text{if} \quad t^\text{available}_{x,t} \quad \text{then} \quad E_{p,t} + S^\text{conserv}_{x,t} - L^\text{conserv} >=0`



Inverter
^^^^^^^^^^^^^
An inverter node converts alternating current (AC) to direct current (DC). It has one AC port, and at least one DC port.

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
A boiler converts gas to heat at a fixed coefficient of performance (COP). The COP is a unitless ratio between output energy and input energy. The boiler is either on, and must operate between a min and max input, or off. It has one input port (units of Joules per second) and one output port (units of KW thermal).

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

* ``startup_cop`` (:math:`C^\text{init}`): coefficient of performance, output/input energy.

**Variables**

:math:`p^\text{in}`, input (J/s)

:math:`p^\text{out}`, output (kW thermal)

:math:`p^\text{on}`, binary variable for when the boiler is on


**Constraints**:

Off or constrained constraints:

:math:`p^\text{in} \geq p^\text{on} \cdot p^\text{min}`

:math:`p^\text{in} \leq p^\text{on} \cdot p^\text{max}`

We use a weighted sum of past inputs approach to applying the COP. This constraint enforces that when the boiler turns on, in the first period it will operate at ``startup_cop`` and for subsequent periods it will operate at ``cop``. When the boiler turns off, it will operate at a lower efficiency, and then reach zero in the next time step.


:math:`p^\text{out}_{x, t} = p^\text{in}_{x, t} \cdot C^\text{init} + p^\text{in}_{x, t-1} \cdot (C - C^\text{init})`

For example, if a 10 kW boiler has a ``cop = 1``, and ``startup_cop = 0.7``, in the time period when the boiler turns on, its output is :math:`p^\text{out} = (0.7)(10) + (0.3)(0) = 7`, and in the next time step, its output is :math:`p^\text{out} = (0.7)(10) + (0.3)(10)= 10`. Assume it operates at :math:`p^\text{out}=10` for some time, before turning off. In the time period it turns off, :math:`p^\text{out}=(0.7)(0) + (0.3)(10) = 3`. In the next period :math:`p^\text{out}=(0.7)(0) + (0.3)(0) = 0`.


Temperature Controlled Gas Boiler
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
This node has a gas input port and a heating output port. It has additional variables representing its exit and return temperatures of its working fluid.
These temperature can be optimised within a range.

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

* ``deg_to_kW`` (:math:`\alpha`: conversion factor between a temperature difference :math:`\Delta T` and kW of heating/cooling. Has units of kW/deg C.

* ``cop`` (:math:`C`): see :ref:`Gas Boiler Fixed COP`

* ``startup_cop`` (:math:`C^\text{init}`): see :ref:`Gas Boiler Fixed COP`

* ``exit_temp_bounds`` (:math:`ET^\text{min}`, :math:`ET^\text{max}`): tuple of lower and upper bounds on the exit temperature

* ``return_temp_bounds`` (:math:`RT^\text{min}`, :math:`RT^\text{max}`): tuple of lower and upper bounds on the exit temperature


**Variables**

:math:`p^\text{in}`, gas in

:math:`p^\text{out}`, power out

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

TODO - add startup cop


Thermal Nodes
----------------------

Controllable Thermal Load
^^^^^^^^^^^^^
A controllable thermal load represents a heating and/or cooling load. For example, this node can be used to represent a building's overall thermal load, or specific loads for things like space heating, hot water heating, or other industrial processes. This node supports an arbitrary number of ports, so that the node can be connected to various heating/cooling sources.

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
        thermal_load.add_thermal_port('heating_load')
        thermal_load.add_thermal_port('cooling_load')


**Parameters**:

* ``temp_ub`` (:math:`T^\text{ub}`): temperature upper bound entered as a dictionary of values

* ``temp_lb`` (:math:`T^\text{lb}`): temperature lower bound entered as a dictionary of values

* ``external_temp`` (:math:`T^\text{ambient}`): ambient temperature entered as a dictionary of values

:math:`\alpha`, a factor that equals :math:`\frac{\Delta T}{kW}, used for converting a temperature difference to kW heating or cooling.

:math:`\eta^\text{loss}`, a loss factor/efficiency

:math:`\eta^\text{gain}`, a gain factor/efficiency

**Variables**:

:math:`P`, total heating and cooling kW at the node

:math:`T^\text{internal}`, the internal temperature of the thermal load

:math:`E^\text{loss}`, energy loss due to internal temperature being > ambient temperature

:math:`E^\text{gain}`, energy gain due to internal temperature being < ambient temperature

:math:`E^*`, binary variable for splitting losses and gains


**Constraints**:

Loss and gain sum constraint:

:math:`E^\text{loss} + E^\text{gain} = (T^\text{ambient} - T^\text{internal}) \cdot \alpha`

Loss and gain big M constraints, so we split the variables correctly:

:math:`E^\text{loss} \geq (E^* - 1) \cdot M`

:math:`E^\text{gain} \leq E^* \cdot M`


Constraint relating the heating/cooling delivered to the node to the internal temperature and the losses/gains.

:math:`P_{x, t} + \eta^\text{loss} \cdot E^\text{loss}_{x, t}+ \eta^\text{gain} \cdot E^\text{gain}_{x, t} = (T^\text{internal}_{x, t} - T^\text{internal}_{x, t-1}) \cdot \alpha`


Heat Pump Single Output
^^^^^^^^^^^^^
A heat pump converts electrical input to either heating output, or cooling output.
A single output heat pump has one input electrical port :math:`p^\text{in}`, and one output thermal port :math:`p^\text{out}` that can either be positive (behaving as a heat sink, or cooling source), or negative (behaving as a heat source).
An example of initialising a single output heat pump is

.. code-block::

    time_periods = 24
    heating_cop = np.array([0.8] * time_periods)
    cooling_cop = np.array([2] * time_periods)
    heat_cop_dict = generate_dict_with_pyomo_keys_from_array(heating_cop, time_periods)
    cool_cop_dict = generate_dict_with_pyomo_keys_from_array(cooling_cop, time_periods)

    heat_pump = HeatPumpSingleOutput(heating_cop_time_series=heat_cop_dict,
                                     cooling_cop_time_series=cool_cop_dict)


The coefficients of performance are provided as parameters because in theory they can be calculated prior to optimisation, based on ambient temperature data.

**Parameters**

* ``heating_cop_time_series`` (:math:`COP^\text{heat}`): a dict of time series coefficients of performance for heating.

* ``cool_cop_time_series`` (:math:`COP^\text{cool}`): a dict time series of coefficients of performance for cooling.

Both dicts should be entered as a dict where the keys are ``(planning_period, time_period)``.

**Variables**

:math:`H^\text{in}`, electrical input used for heating

:math:`C^\text{in}`, electrical input used for cooling

:math:`b^*`, binary variable that indicates whether the output port is cooling (:math:`b^*=1`) or heating (:math:`b^*=0`)

:math:`p^\text{in}`, electrical power in

:math:`p^\text{out-}`, heating out

:math:`p^\text{out+}`, cooling out


**Constraints**

Summing constraint on the division of electrical input for heating and cooling purposes:

:math:`H^\text{in} + C^\text{in} = p^\text{in}`

Big M constraints for enforcing that when the cooling indicator variable, :math:`b^*`, is 1, :math:`H^\text{in}=0`, and vice versa.

:math:`H^\text{in} \leq (1 - b^*) \cdot M`

:math:`C^\text{in} \leq b^* \cdot M`


Heating output constraint:

:math:`p^\text{out-}_{x, t} = H^\text{in}_{x, t} \cdot COP^\text{heat}_{x, t}`

Cooling output constraint:

:math:`p^\text{out+}_{x, t} = C^\text{in}_{x, t} \cdot COP^\text{cool}_{x, t}`


Heat Pump Dual Output
^^^^^^^^^^^^^^^
A heat pump with dual outputs has separate ports for heating and cooling, and can be used to serve separate heating and cooling loads.
It has one input electrical port :math:`p^\text{in}`, one output thermal port for heating (export only) :math:`p^\text{heat out}`, and one output port for cooling (import only) :math:`p^\text{cool out}`.

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
The only difference is that instead of splitting port :math:`p^\text{out}` into negative component :math:`p^\text{out-}` representing the heating output, and positive component :math:`p^\text{out+}` representing the cooling output, we have separate ports :math:`p^\text{heat out}` and :math:`p^\text{cool out}`. Therefore, the final pair of constraints are:

Heating output constraint:

:math:`p^\text{heat out}_{x, t} = H^\text{in}_{x, t} \cdot COP^\text{heat}_{x, t}`

Cooling output constraint:

:math:`p^\text{cool out}_{x, t} = C^\text{in}_{x, t} \cdot COP^\text{cool}_{x, t}`



Chiller
^^^^^^^^^^^^^
This node has two ports, an input electrical port, and an output cooling port.



Other Nodes
------------------------

Emitting Node
^^^^^^^^^^^^^^^^^
An emitting node has a port :math:`p^\text{emit}` that generates emissions when it exports, and another port that generates carbon :math:`p^\text{carbon}`.


Time Delay Node
^^^^^^^^^^^^^^^^
A time delay node has two ports, one input :math:`p^\text{in}`, and one output :math:`p^\text{out}`. The input port always imports, and the output port always exports. The throughput from input to output is delayed by some number of time intervals.

This node can be used to represent delays in a system, and is particularly appropriate for discrete/process based systems. The time delay can also be set to 0 to model feedback loops.

**Parameters**

:math:`d`, time delay in number of time intervals

**Constraints**

:math:`p^\text{out}_{x, t} = -p^\text{in}_{x, t-d}`


Input Output ARX Node
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
This node has one input port :math:`p^\text{in}` and one output port :math:`p^\text{out}`. The output at each interval depends on current inputs, previous inputs, and previous outputs. The dependence of the current output on on previous outputs is defined by coefficient array :math:`a`, and the dependence on current and previous inputs is defined by coefficient array :math:`b`


**Constraints**

TBC


Template Node
^^^^^^^^^^^^^^^^^
**Description**

**Variables**

**Parameters**

**Constraints**
