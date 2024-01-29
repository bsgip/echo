# Changelog

## Releases

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