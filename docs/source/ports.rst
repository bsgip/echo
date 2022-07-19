.. _Ports_ref:
*echo* Ports
=======================
Ports terminate a network edge and represent the connection of an edge to a node.
Ports are associated with an individual commodity and represent the flow of the that commodity into or out of a node.

Base Port Models
-----------------------------------------------

.. note::
    Where variables are indexed by :math:`{x, t}` :math:`x` refers to the planning interval, and :math:`t` refers to the time interval. Sometimes these indices are left out of the constraint equations, and in this case, please refer to the variable definition to see whether it is an indexed variable or not.

Port
^^^^^^
This is the base port class. The main port variable is :math:`p_{x, t}`, which represents the port flow value.

If :math:`p` needs to be split into a positive and negative component, the following variables are introduced:

:math:`p^+_{x, t}`,  the positive component of the port flow

:math:`p^-_{x, t}`,  the negative component of the port flow

:math:`p_{x, t}^\text{*}`, a binary variable for indicating whether :math:`p^+` is non-zero.

The following constraints are used to split the variable.

:math:`p = p^+ + p^-`

:math:`p^+ \leq p^* \cdot M`

:math:`p^- \geq (p^* - 1) \cdot M`

**Parameters**

* ``flows``: A parameter for defining what flows are possible. Options are ``Flows.Both``, ``Flows.Import``, ``Flows.Export``. This parameter controls the domain of :math:`p`.
* ``import_constraint_value`` (:math:`p^\text{import constraint}`): A constraint on imports. Can be None, a non-negative float, or an array of non-negative floats .
* ``export_constraint_value`` (:math:`p^\text{export constraint}`): A constraint on exports. Can be None, a non-positive float, or an array of non-positive floats.
* ``active_periods`` (:math:`p^\text{active}`): An array of periods when the port is active (on). 1=on, 0=off.
* ``slack``: A bool parameter for enabling a slack variable on the port. A slack variable is useful when there are import or export constraints that may not be feasible. They ensure that the solver returns a solution even if the constraints cannot be satisfied, and we can interrogate by how much the import/export constraint was violated.

.. note::
    If ``slack=True``, a large cost is automatically added to the objective, so that the optimiser will only use the slack if it has no alternative. The costs are added in such a way that the maximum violation is penalised more heavily than the total violations.

If ``import constraint is not None``: :math:`p \leq p^\text{import constraint}`

If ``export constraint is not None``: :math:`p \geq p^\text{export constraint}`

If ``slack`` is ``True`` and ``import constraint is not None``, the following variables and constraints are used instead:

:math:`p^\text{import slack}`, the slack at each time interval

:math:`p^\text{max import slack}`, the max import slack over all time intervals

:math:`p + p^\text{import slack} \leq p^\text{import constraint}`

:math:`p^\text{max import slack} \geq p^\text{import slack}`


If ``slack`` is ``True``, and if ``export constraint is not None``, the following variables and constraints are used instead:

:math:`p^\text{export slack}`, the slack at each time interval

:math:`p^\text{max export slack}`, the max export slack over all time intervals

:math:`p + p^\text{export slack} \geq p^\text{export constraint}`

:math:`p^\text{max export slack} \geq p^\text{export slack}`


If ``active_periods is not None``, the following constraints are added:

:math:`p \leq p^\text{active} \cdot M`

:math:`p \geq - p^\text{active} \cdot M`


Storage
^^^^^^^^
A storage port is a child of the :ref:`Port` class. It has the following additional parameters, variables, and constraints:

* ``max_capacity`` (:math:`E^\text{max}`): Maximum battery capacity in kWh

* ``depth_of_discharge_limit`` (:math:`dod`): Percentage to which the battery can discharge to, written as a decimal.

* ``charging_power_limit`` (:math:`lim^\text{charge}`): Limit on charging power in kW

* ``discharging_power_limit`` (:math:`lim^\text{discharge}`): Limit on discharging power in kW

* ``charging_efficiency`` (:math:`\eta^\text{charge}`): Efficiency that applies when converting energy imported to a change in stored energy.

* ``discharging_efficiency`` (:math:`\eta^\text{discharge}`): Efficiency that applies when converting energy exported to a change in stored energy.

* ``initial_state_of_charge``: Initial state of charge of the battery in kWh

* ``fixed_storage_capacity``: If ``True`` storage capacity is optimised between 0 and ``max capacity``. Default is ``False``

* ``storage_capacity_cost``: Cost on storage capacity in $ per kWh.

* ``regularise``: Optional regularisation term on the battery. Default is ``False``.

.. note::
    ``storage_capacity_cost`` must be set to some value if ``fixed_storage_capacity`` is ``True``. Default is ``None``.


**Variables**

These are inherited from the :ref:`Port` class, and are repeated here for clarity:

:math:`p_{x, t}`, battery power

:math:`p^+_{x, t}`, power imported by the battery

:math:`p^-_{x, t}`, power exported by the battery

:math:`E_{x, t}`, energy stored in the battery


**Constraints**

Charging/discharging constraint:

:math:`lim^\text{discharge} \leq p \leq lim^\text{charge}`

State of charge constraint:

:math:`E_{x, t} = E_{x, t-1} + p^+_{x, t} \cdot \eta^\text{charge} + p^-_{x, t} \cdot \eta^\text{discharge}`


Depth of discharge constraint:

:math:`E^\text{max} \cdot dod \leq E \leq E^\text{max}`



Mobile Storage
^^^^^^^^^^^^^^^^^^
Could potentially create a new port model, for EV battery. It would be a child of the :ref:`Storage` class.
It could have the EV-specific parameters:


* ``trip_slack``

* ``soc_conserv``

* ``soc_conserv_cost``

* ``available``

If ``trip_slack`` is ``True``, the modified battery state of charge equation accounting for the trip slack variable is:

:math:`E_{x, t} = E_{x,t-1} + \eta^\text{charge} p^\text{battery,+}_{x,t} d^\text{interval} + p^\text{battery, -}_{x,t} \frac{d^\text{interval}}{\eta^\text{discharge}} + S^\text{trip}_{x,t}`

If ``SOC_conserv is not None``, conservative state of charge lower limit:

:math:`\text{if} \quad t^\text{available}_{x,t} \quad \text{then} \quad E_{p,t} + S^\text{conserv}_{x,t} - L^\text{conserv} \geq 0`


Bounded
^^^^^^^^
A bounded port is a child of the :ref:`Port` class. It must have a value between a lower and upper bound, which may be specified as time varying values.

**Parameters**

* ``upper_bound`` (:math:`p^\text{ub}_{x, t}`): port upper bound

* ``lower_bound`` (:math:`p^\text{lb}_{x, t}`): port lower bound

**Constraints**

:math:`p \geq p^\text{lb}`

:math:`p \leq p^\text{ub}`


Off or Constrained
^^^^^^^^^^^^^^^^^^^
An off or constrained port is a child of the :ref:`Port` class. It must have a value between a lower and upper bound, which may be specified as time varying values. If it is off, it has a value of zero.

**Parameters**

* ``upper_bound`` (:math:`p^\text{ub}_{x, t}`): port upper bound

* ``lower_bound`` (:math:`p^\text{lb}_{x, t}`): port lower bound

**Variables**

* ``on`` (:math:`p^\text{on}_{x, t}`): on/off binary variable


:math:`p \geq p^\text{on} \cdot p^\text{lb}`

:math:`p \leq p^\text{on} \cdot p^\text{ub}`


Controlled Load or Generation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
A controlled load or generation port is a child of the :ref:`Port` class.
It can have a min and/or max utilisation.
Min utilisation is the ratio between the minimum energy consumed, and the maxinimum energy that would be consumed if the load operated at max power.
Max utilisation is the ratio between the maximum energy consumed, and the maximum energy that would be consumed if the load operated at max power.

**Parameters**

* :math:`p^\text{max}`, the maximum port power

* :math:`p^\text{min}`, the minimum port power

* :math:`util^\text{min}`, the minimum utilisation

* :math:`util^\text{max}`, the maximum utilisation

* :math:`d^\text{interval}`, the time interval in minutes

* :math:`d^\text{total}`, the total number of time intervals

**Constraints**

If there is a minimum utilisation specified:

:math:`\sum_{i=0}^x \sum_{j=0}^t p_{i, j} \cdot \frac{d^\text{interval}}{60} \geq util^\text{min} \cdot p^\text{max} \cdot \frac{d^\text{interval}}{60} \cdot d^\text{total}`

If there is a maximum utilisation specified:

:math:`\sum_{i=0}^x \sum_{j=0}^t p_{i, j} \cdot \frac{d^\text{interval}}{60} \leq util^\text{max} \cdot p^\text{max} \cdot \frac{d^\text{interval}}{60} \cdot d^\text{total}`
