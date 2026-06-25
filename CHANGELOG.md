# Changelog

## Releases

### v2.2.2 (2026-06-xx)

#### Changes

- `echo.objectives.tariff.DemandTariffObjective.add_constraints()` uses a closure construction. These constructions don't work in python. Has been reimplemented using `functools.partial`.
- `echo.models.agnostic.PartitionedMultiCommodityTellegenNode.apply_node_constraints()` gets around the above closure issue using a confusing implicit passing of looping variables. This has been reimplemented using `functools.partial`.

### v2.2.1 (2026-06-05)

#### Adds

- MIT licence

### v2.2.0 (2026-04-30)

#### Adds

- New pattern for insert data with state into for `EVBase` and child classes:
  - Adds `set_stateful_attrs_at_init` attribute, which propagates to relevant ports. If set to `True`, the object will require stateful attributes to be defined upon instantiation. If set to `False`, defining the stateful attributes is delayed until `set_stateful_attrs()` is run.
  - Adds new function `set_stateful_attrs()` which inserts stateful data and run re-initialisation where required.
  - Adds `OptimisationGraph.rebuild_all_edges()` which is designed to be used when all stateful data has been injected into all objects. This is to remedy issues with pydantic object modification and the de-syncing of ports on edges and nodes.
- Adds new tests for the new implementation of EV objects in `tests/test_evs.pyproject`.

#### Changes

- Splits the `EV` object into a new `EVBase` parent object a four child objects:
  - `EVV0G` - convenience charging based on EV availability
  - `EVV1G` - demand managed charging based on EV availability
  - `EVV2G` - demand and generation managed charging based on EV availability
  - `EVWithProfile` - EV charging based on a demand and/or generation profile. The profile can have positive (demand) and negative (generation) values). For use with collected EV data.
  - Replaces `**data` input variable with explicit input variables for functions in `EVBase`, `EVV0G`, `EVV1G`, `EVV2G` and `EVWithDemandProfilee` objects.

#### Deprecates

- Deprecates the `EV` object.

### v2.1.0 (2024-01-29)

#### Adds

- Adds method `to_cytoscape_json` to `OptimisationGraph` class.
- Added a new jupyter notebook (`visualise_network.ipynb`) demonstrating how to visualise networks with matplotlib and cytoscape.
- Sets isort's line length to the same as used by black (`pyproject.toml`).
- Adds an example folder to the echo package, containing a single example btm network (`echo/examples/networks/simple_btm_network.py`).
- Adds class `TimeSeriesData` for representing time series data in a minimalistic way. This class is a replacement for the `ArrayWrap` class, which has been removed.

#### Changes

- `Transform` constructor requires the lhs-terms to be passed in. The `add_lhs_term` method removed from the `Transform` class.
- `Inverter` contructor requires ac/dc port names to be passed in. `add_dc_port` and `add_ac_port` methods removed from the `Inverter` class.
- The following methods/functions on the `Port` class have been renamed:
  - `add_initial_value` → `set_initial_value`
  - `add_initial_value_from_array` → `set_initial_value_from_array`
  - `add_initial_value_from_timeseriesdata` → `set_initial_value_from_timeseriesdata`
  - `initialise_X` methods renamed to `add_X_to_model` (Various classes). An incomplete list includes:
  - `initialise_node` → `add_node_to_model` (`Node` and classes derived from `Node`)
  - `initialise_port` → `add_port_to_model` (`Port` and classes derived from `Port`)
  - `initialise_edge` → `add_edge_to_model` (`Edge` class)
  - `initialise_path` → `add_path_to_model` (`Path` class)
  - `initialise_objective` → `add_objective_to_model` (`Objective` class)
- `initialise_transform` renamed to `_add_transform_to_model` and made private to the `Transform` class.
- `GasPort` renamed to `FlexGasPort` for better naming consistency.
- The utility function `set_var_bounds_from_dict` now takes different parameters. Instead of the variable and bounds, it receives the echo model, the variable name (not the variable itself) along with the bounds.
- `opt_type` rename to `flow_type` since it determines whether the port flow is a variable or parameter in the optimization (`Port` and it subclasses).
- `draw_echo_graph` renamed to `draw_on_axes` (`Optimisation Graph`). `draw_on_axes` now takes different parameters to `draw_echo_graph` to facilitate a switch from an implicit to an explicit drawing approach. See [here](https://matplotlib.org/stable/tutorials/lifecycle.html) for more on the difference between these two approaches.
- Attempts to fix the tests in `test_evs.py` to be more deterministic and not fail periodically due to a different path taken by the optimiser.
- The manual examples and jupyter notebooks in the `/scripts` folder have been completely reworked to be easier to understand.

#### Removes

- The `add_lhs_term` method has been removed from the `Transform` class. Pass lhs-terms to the `__init__` method instead.
- The `add_dc_port` and `add_ac_port` methods have been removed from the `Inverter` class. Pass the ac/dc port names to the `__init__` method instead.
- `NodeRule` has been completely removed. It was used to select between different node constraint behaviours. When defining new node types, a similar effect can be achieved by either subclassing `Node` and overriding `apply_node_constraints` or by subclassing TransformNode instead.
- The `ArrayWrap` class has be removed and replaced with `TimeSeriesData`.
