Optimisation objectives
===================================

Objective Set
--------------


Power/Flow Objectives
----------------------


Peak Positive Power
^^^^^^^^^^^^^^^^^^^^
Cost = peak positive power at port.
The optimiser will try to minimise the peak power imported.

**Variables**

:math:`p^+`, port positive component

:math:`p^\text{max+}`, maximum port positive component

**Constraints**

:math:`p^\text{max+} >= p^+`

**Objective expression**

:math:`o = p^\text{max+}`



Peak Negative Power
^^^^^^^^^^^^^^^^^^^^
cost = peak negative power at port.
the optimiser will try to minimise the peak power exported.

**Variables**

:math:`p^-`, port negative component

:math:`p^\text{max-}`, maximum port negative component

**Constraints**

:math:`p^\text{max-} <= p^-`

**Objective expression**

:math:`o = p^\text{max-}`


Quadratic Power
^^^^^^^^^^^^^^^^^^^^
The optimiser will try to minimise power squared, which has a regularising effect.

**Variables**

:math:`p`, port value

**Objective expression**

:math:`o = p^2`


Throughput Cost
^^^^^^^^^^^^^^^^
The optimiser will try to minimise the total throughput through a port.

**Variables**

:math:`p^+`, port positive component

:math:`p^-`, port negative component

**Parameters**

:math:`r`, rate in $ per flow unit (e.g., $/kW throughput).

**Objective expression**

:math:`o = (p^+ - p^-) \cdot r`


Contingency Negative
^^^^^^^^^^^^^^^^^^^^
FCAS Raise
How much energy could your asset export (generate) to the upstream grid?
The optimiser will try to maximise the available capacity for contingency bids.

Contingency Positive
^^^^^^^^^^^^^^^^^^^^
FCAS Lower
How much energy could your asset import (consume) from the upstream grid?
The optimiser will try to maximise the available capacity for contingency bids.

Economic Objectives
--------------------


Energy Tariffs
---------------
Tariffs apply an array of prices to the energy imported or exported at a given port.

Import Energy Tariff
^^^^^^^^^^^^^
Prices should be given in $/kWh, or $/equivalent energy unit for a different commodity.
The optimiser will try to minimise the cost of importing energy to the port.

**Variables**

:math:`p^+`, port positive component

**Parameters**

:math:`c_{x, t}`, prices

:math:`d^\text{interval}`, the time interval in minutes

**Objective expression**

:math:`o = p^+ \cdot c \cdot \frac{d^\text{interval}}{60}`


Export Energy Tariff
^^^^^^^^^^^^^
Prices should be given in $/kWh, or $/equivalent energy unit for a different commodity.

The optimiser will try to maximise the returns from exporting energy from the port.

**Variables**

:math:`p^-`, port negative component

**Parameters**

:math:`c_{x, t}`, prices

:math:`d^\text{interval}`, the time interval in minutes

**Objective expression**

:math:`o = p^- \cdot c \cdot \frac{d^\text{interval}}{60}`

Time of Use Energy Tariffs
^^^^^^^^^^^^^^^^^^^^^^^^^^^
Prices should be given in $/kWh, or $/equivalent energy unit for a different commodity.


Path Tariff
^^^^^^^^^^^^^
Prices should be given in $/kWh, or $/equivalent energy unit for a different commodity.


Demand Tariffs
-----------------
Demand tariffs are composed of a set of demand charges. They are typically used on loads/energy consuming ports. Each demand charge specifies a time window over which it applies, a rate (in $/kW or equivalent for a different commodity), and a reset period.

For example, a demand tariff could include a charge that applies at evening peak time (5pm - 8pm), at a rate of $0.5/kW, and resets every month. Using this tariff, the demand would be calculated every day between 5pm and 8pm, and the maximum value over that period would be multiplied by the rate of $0.5/kW.

The optimiser will try to minimise the maximum demand in the appropriate time window during each reset period.

Other Objectives
-----------------


Not Fully Charged Penalty
^^^^^^^^^^^^^^^^^^^^^^^^^^^
The optimiser will penalise a storage asset for not being fully charged.




Template Objective
^^^^^^^^^^^^^^^^^^^^
**Variables**

**Parameters**

**Constraints**

**Objective expression**