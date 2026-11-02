*echo* Optimisation Objectives
===================================
Objectives can be applied to an echo model in order to optimise the behaviour of controllable variables (decision variables) to achieve a certain outcome.

Objective Set
--------------
The objective set contains a list of objectives as defined in the sections below. Each objective in the list will be added to a total objective term. Multi-objective optimisation problems are not supported.

Power/Flow Objectives
----------------------
Power/flow objectives are applied to a port value directly.

Peak Positive Power
^^^^^^^^^^^^^^^^^^^^

This objective penalises the peak positive (imported) power at a port.

Assuming ``cp1`` is a port object, an example of defining this objective is
.. code-block::

    ppp = PeakPositivePower(component=cp1)

**Variables**

:math:`p^+`, port positive component

:math:`p^\text{max+}`, maximum port positive component

**Constraints**

:math:`p^\text{max+} \geq p^+`

**Objective expression**

:math:`O = p^\text{max+}`


Peak Negative Power
^^^^^^^^^^^^^^^^^^^^
This objective penalises the peak negative (exported) power at a port.

Assuming ``cp1`` is a port object, an example of defining this objective is

.. code-block::

    pnp = PeakNegativePower(component=cp1)

**Variables**

:math:`p^-`, port negative component

:math:`p^\text{max-}`, maximum port negative component

**Constraints**

:math:`p^\text{max-} \leq p^-`

**Objective expression**

:math:`O = p^\text{max-} \cdot -1`


Quadratic Power
^^^^^^^^^^^^^^^^^^^^
This objective penalises the port power squared. This objective acts as a regularization term. This makes the optimal solution, if there is one, unique.


Assuming ``cp1`` is a port object, an example of defining a quadratic power cost is

.. code-block::

    quad_cost = QuadraticPower(component=cp1)

**Variables**

:math:`p`, port value

**Objective expression**

:math:`O = p^2`


Contingency Negative
^^^^^^^^^^^^^^^^^^^^
This objective maximises the available capacity for an FCAS raise bid. An FCAS raise bid is the power that an asset could export (generate) and deliver upstream.

**Parameters**

* ``path``, the path that the flow would theoretically take from the bidder to the upstream grid.
* ``duration`` (:math:`d`): duration in seconds that the asset must sustain their bid power.

**Variables**

:math:`C^\text{neg}`


**Constraints**

The specific constraints will depend on the network. If there are any flow constraints between the bidding port and the upstream port, these need to be accounted for.


**Objective expression**

Contingency Positive
^^^^^^^^^^^^^^^^^^^^
This objective maximises the available capacity an FCAS lower bid. An FCAS lower bid is a quantity of energy that an asset could import from upstream.


**Constraints**

The specific constraints will depend on the network. If there are any flow constraints between the bidding port and the upstream port, these need to be accounted for.

**Objective expression**


Throughput Cost
^^^^^^^^^^^^^^^^
This objective applies a given rate to the total throughput (import plus export) at a port. If the rate is positive, then throughput will be penalised, and if the rate is negative, throughput will be rewarded.

Assuming ``cp1`` is a port object, an example of defining a throughput cost is

.. code-block::

    throughput_cost = ThroughputCost(component=cp1, rate=0.000001)



**Variables**

:math:`p^+`, port positive component

:math:`p^-`, port negative component

**Parameters**

:math:`r`, rate in $ per flow unit (e.g., $/kW throughput).

**Objective expression**

:math:`O = (p^+ - p^-) \cdot r`


Energy Tariffs
---------------
Tariffs apply an array of prices to the energy imported or exported at a given port.
Prices should be given in $/kWh, or $/equivalent energy unit for a different commodity.

Import Energy Tariff
^^^^^^^^^^^^^^^^^^^^^
This objective applies positive prices to energy imported at a port. Therefore, this objective penalises energy imported at a port.

Assuming ``cp1`` is a port object, an example of defining an import tariff is

.. code-block::

    import_tariff_array = [0.1] * 28 + [0.3] * 8 + [0.2] * 32 + [0.3] * 16 + [0.1] * 12
    import_cost = ImportTariff(component=cp1,
                               tariff_array=import_tariff_array)

**Variables**

:math:`p^+`, port positive component

**Parameters**

:math:`c_{x, t}`, prices

:math:`d^\text{interval}`, the time interval in minutes

**Objective expression**

:math:`O = p^+ \cdot c \cdot \frac{d^\text{interval}}{60}`


Export Energy Tariff
^^^^^^^^^^^^^^^^^^^^^
This objective applies positive prices to energy exported from a port. This objective maximises the returns (negative costs) from exporting energy from the port.

Assuming ``cp1`` is a port object, an example of defining an export tariff is

.. code-block::

    export_tariff_array = [0.1] * 28 + [0.3] * 8 + [0.2] * 32 + [0.3] * 16 + [0.1] * 12
    export_cost = ExportTariff(component=cp1,
                               tariff_array=export_tariff_array)


**Variables**

:math:`p^-`, port negative component

**Parameters**

:math:`c_{x, t}`, prices

:math:`d^\text{interval}`, the time interval in minutes

**Objective expression**

:math:`O = p^- \cdot c \cdot \frac{d^\text{interval}}{60}`

Time of Use Energy Tariffs
^^^^^^^^^^^^^^^^^^^^^^^^^^^
Time of use energy tariffs can be formulated as import/export tariffs, by setting the price to zero during the times when the tariff is inactive.


Path Tariff
^^^^^^^^^^^^^
TBC

Power Tariffs
----------------

Demand Tariff
^^^^^^^^^^^^^^
Demand tariffs are composed of a set of demand charges.

A demand charge is a price applied to the maximum power (either import or export) within certain time periods. The demand charge is reset after a certain number of time periods.

For example, consider an import demand charge that applies every evening from 5pm - 8pm, with a rate of $0.5/kW, and resets every month. Each night between 5pm and 8pm, the maximum power imported would be calculated. Then, the maximum of these values would be multiplied by $0.5/kW to obtain the total cost for that month. Then the max value would reset, and the same process would occur for the next month.

Assuming ``cp1`` is a port object, an example of defining a demand tariff and a demand charge is

.. code-block::

    shoulder_rate = 1.0
    shoulder_window = [0] * 18 + [1] * 16 + [0] * 6 + [1] * 4 + [0] * 4

    shoulder_charge = DemandCharge(rate=shoulder_rate,
                                   window_array=shoulder_window,
                                   min_demand=0.0,
                                   reset_period=ResetPeriod.Day,
                                   import_demand=True)

    demand_tariff = ImportDemandTariffObjective(component=cp1,
                                                demand_charges=[shoulder_charge])


**Parameters**

Each demand charge has the following parameters:

* ``window_array`` (:math:`w`): the time window when the charge applies
* ``rate`` (:math:`r`): the rate (in $/kW or equivalent for a different commodity)
* ``min_demand`` (:math:`d^\text{min}`): the minimum demand
* ``reset_period`` (:math:`f`): the reset period frequency (how often the calculation resets)
* ``import_demand``: parameter for controlling whether the charge applies to imports or exports


The objective penalises the maximum demand (either import or export) in the corresponding time window during each reset period.

**Variables**

:math:`p^+`, positive port component (imports)

:math:`p^-`, negative port component (exports)

Each demand charge has the following variables, which are indexed by the reset period :math:`f`

:math:`d_f`, max demand value


**Constraints**

For each demand charge and each reset period:

If ``import_demand`` is ``True``:

:math:`d_f \geq (p^+ - d^\text{min}) \cdot w`

If ``import_demand`` is ``False``:

:math:`d_f \leq (p^- - d^\text{min}) \cdot w`

**Objective expression**

If the demand tariff has :math:`n` demand charges, then the total objective is:

:math:`O = \sum_{i=0}^n x_i`

Where :math:`x` is the total cost of each demand charge, and for each demand charge, if ``import_demand`` is ``True``:

:math:`x = \sum_{j=0}^{f} d_j \cdot r`

else if ``import_demand`` is ``False``:

:math:`x = \sum_{j=0}^{f} d_j \cdot r \cdot -1`



Other Objectives
-----------------


Not Fully Charged Penalty
^^^^^^^^^^^^^^^^^^^^^^^^^^^
The optimiser will penalise a storage asset for not being fully charged.




Advanced Use
----------------

Defining Custom Objectives
^^^^^^^^^^^^^^^^^^^^^^^^^^^
If custom objectives are required, they should be added to the optimiser **after** the optimiser has been initialised. Initialising the optimiser will automatically set the objectives, if any are defined, and so any additional objectives should be added after this initialisation.

.. code-block::

        optimiser = EchoOptimiser(
                                interval_duration=interval_duration,
                                number_of_intervals=time_periods,
                                number_of_expansion_intervals=expansion_periods,
                                discount_rate=0,
                                ES=system,
                                objective_set=objective_set)

        optimiser.objective += sum(getattr(optimiser.model, pv1.port_name)[p, t]
                          for p in optimiser.model.Expansion for t in optimiser.model.Time)


Note the use of ``+=``.

Template Objective
^^^^^^^^^^^^^^^^^^^^
**Variables**

**Parameters**

**Constraints**

**Objective expression**