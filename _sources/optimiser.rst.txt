*echo* Optimiser
====================


The echo optimiser converts an echo graph into an optimisation problem. The optimisation problem is built using `Pyomo <https://pyomo.readthedocs.io/en/stable/index.html>`_.

Initialising the optimiser
----------------------------

The optimiser has the following parameters:

* ``interval_duration``: the duration of time intervals in minutes
* ``number_of_intervals``: the number of time intervals
* ``number_of_expansion_intervals``: the number of expansion intervals
* ``discount_rate``: a discount rate in decimal notation
* ``ES``: the echo graph
* ``objective_set``: an echo objective set (see :ref:`Objectives <*echo* Optimisation Objectives>`).
* ``optimiser_engine``: a string indicating which optimiser engine to use (e.g., 'cplex')
* ``profile``: a `pandas dataframe <https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.html>`_. that contains time series data needed to initialise the pyomo model.


After creation, the pyomo model can be accessed using the ``.model`` method on the optimiser object.


TBC - info on how to build the pyomo model, how to optimise, providing time series data here instead of directly into the model, etc.


Building the pyomo model
-------------------------
TBC - how everything gets initialised

Setting the objective
---------------------
TBC - detail about the two places objective terms are defined (objective set + on ports/nodes where relevant)

Optimising
------------
TBC - logfile, viewing output settings

Extracting and viewing optimisation results
-----------------------------------------------
After optimisation, the pyomo model is updated with the optimised values.

