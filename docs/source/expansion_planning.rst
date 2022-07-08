====================
Expansion planning
====================
Expansion planning refers to decisions about *asset expansions* (whether to build new assets), *capacity expansions* (the size of new assets, or the increased capacity of existing assets), and *retirement planning* (whether to retire assets). Costs can be applied to these decisions that reflect the cost of building new assets, increasing capacity of existing assets, and retiring assets.

Expansion periods
---------------------

In echo, expansion planning is implemented using a planning interval, which is distinct from the time intervals over which operational decisions are made. For example, time intervals might be in 1 hr increments, while planning intervals might be in increments of years.

How it works
--------------
The user add must any potential future assets and installation costs to the network before optimisation. They therefore specify where in the network these assets might be located. They then must specify parameters such as:

* Maximum number of new assets per planning period, or over the entire optimisation window
* Maximum number of assets retired per planning period, or over the entire optimisation window
* Whether the assets have fixed parameters (e.g., fixed storage capacity for a battery), or whether these attributes are able to be optimised against some cost per unit capacity.


Asset Expansions
------------------


Capacity Expansion
--------------------


Asset Retirement
-----------------
Assets have a lifetime that is defined in planning period intervals (e.g., years). At the end of their lifetime, assets must either be replaced or retired. Replacement resets the lifetime of the asset to its nominal lifetime, allowing the asset to continue to be operated. Retirement means that the asset ceases to operate for all subsequent expansion periods. Appropriate costs can be applied to retirement/replacement decisions.



