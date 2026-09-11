from dataclasses import dataclass

import numpy as np
import pandas as pd
import pyomo as pyo
import pytest
from pydantic import ValidationError
from pyomo.core.base.var import IndexedVar

from echo import constants
from echo.configuration import FlowConstraint, Flows, OptimisationType, Units
from echo.exceptions import ConfigurationError
from echo.models.base.port import Port
from echo.models.base.types import InitialValue, InitialValueInput
from echo.utils import TimeSeriesData


@pytest.mark.parametrize(
    "port_params",
    [
        {
            "flows": Flows.Import,
            "import_constraint": FlowConstraint.NoConstraint,
            "flow_type": OptimisationType.Variable,
            "units": Units.KW,
        },
        {
            "flows": Flows.Export,
            "export_constraint": FlowConstraint.NoConstraint,
            "flow_type": OptimisationType.Variable,
            "units": Units.KW,
        },
        {
            "flows": Flows.Both,
            "import_constraint": FlowConstraint.NoConstraint,
            "export_constraint": FlowConstraint.NoConstraint,
            "flow_type": OptimisationType.Variable,
            "units": Units.KW,
        },
    ],
)
def test_port_verify(port_params):
    port = Port(**port_params)
    port.verify_port()


@pytest.mark.parametrize(
    "port_params",
    [
        {},  # Missing flows, flow_type, input/export constraints, units
        {
            # Missing flows
            "import_constraint": FlowConstraint.NoConstraint,
            "flow_type": OptimisationType.Variable,
            "units": Units.KW,
        },
        {
            "flows": Flows.Import,
            # Missing import constraint
            "flow_type": OptimisationType.Variable,
            "units": Units.KW,
        },
        {
            "flows": Flows.Import,
            "import_constraint": FlowConstraint.NoConstraint,
            # Missing flow_type
            "units": Units.KW,
        },
        {
            "flows": Flows.Import,
            "import_constraint": FlowConstraint.NoConstraint,
            "flow_type": OptimisationType.Variable,
            # Missing units
        },
        {
            "flows": Flows.Import,
            "import_constraint": FlowConstraint.Fixed,
            "flow_type": OptimisationType.Variable,
            "units": Units.KW,
            # Missing input_constraint_value (since flow constraint is fixed)
        },
        {
            "flows": Flows.Both,
            "import_constraint": FlowConstraint.Fixed,
            "import_constraint_value": 1.0,
            "export_constraint": FlowConstraint.Fixed,
            "flow_type": OptimisationType.Variable,
            "units": Units.KW,
            # Missing output_constraint_value (since flow constraint is fixed and flows is both)
        },
    ],
)
def test_port_raises_configuration_error(port_params: dict):
    port = Port(**port_params)
    with pytest.raises(ConfigurationError):
        port.verify_port()


@pytest.mark.parametrize(
    "raw_initial_val, expected_initial_val",
    [
        ([1, 2, 3], {(0, 0): 1, (0, 1): 2, (0, 2): 3}),  # ints
        ([1.0, 2.0, 3.0], {(0, 0): 1.0, (0, 1): 2.0, (0, 2): 3.0}),  # floats
        ({(0, 0): 1, (0, 1): 2, (0, 2): 3}, {(0, 0): 1, (0, 1): 2, (0, 2): 3}),  # dict of ints
        ({(0, 0): 1.0, (0, 1): 2.0, (0, 2): 3.0}, {(0, 0): 1.0, (0, 1): 2.0, (0, 2): 3.0}),  # dict of floats
        (np.array([1, 2, 3]), {(0, 0): 1, (0, 1): 2, (0, 2): 3}),  # np array of ints
        (np.array([1.0, 2.0, 3.0]), {(0, 0): 1.0, (0, 1): 2.0, (0, 2): 3.0}),  # np array of floats
    ],
)
def test_port_proccess_initial_value(raw_initial_val: list, expected_initial_val: dict):
    port = Port(port_name="port_name")

    assert port.initial_value is None
    port.process_initial_value(initial_val=raw_initial_val)
    assert port.initial_value == expected_initial_val


@pytest.mark.parametrize(
    "import_constraint_value,export_constraint_value",
    [
        ("NOT VALID", 1.0),  # value must be float or array-like
        (1.0, "NOT VALID"),  # value must be float or array-like
        (-1.0, -1.0),  # import value cannot be negative
        (1.0, 1.0),  # Export value can't be
    ],
)
def test_validation(import_constraint_value, export_constraint_value):
    with pytest.raises(ValidationError):
        Port(
            flows=Flows.Both,
            import_constraint=FlowConstraint.Fixed,
            import_constraint_value=import_constraint_value,
            export_constraint=FlowConstraint.Fixed,
            export_constraint_value=export_constraint_value,
            flow_type=OptimisationType.Variable,
            units=Units.KW,
        )


@dataclass
class Method:
    name: str
    initial_value: InitialValueInput | TimeSeriesData | str
    number_of_intervals: int = 3
    profile: pd.DataFrame | None = None


@pytest.mark.parametrize(
    "method, expected_values",
    [
        (Method(name="from_dict", initial_value={(0, 0): 1, (0, 1): 2, (0, 2): 3}), {(0, 0): 1, (0, 1): 2, (0, 2): 3}),
        (
            Method(name="from_dict_via_process_function", initial_value={(0, 0): 1, (0, 1): 2, (0, 2): 3}),
            {(0, 0): 1, (0, 1): 2, (0, 2): 3},
        ),
        (
            Method(
                name="from_timeseriesdata",
                initial_value=TimeSeriesData(value=[1.0, 2.0, 3.0], num_time_intervals=3, num_expansion_intervals=1),
            ),
            {(0, 0): 1, (0, 1): 2, (0, 2): 3},
        ),
        (
            Method(name="from_list", initial_value=[1, 2, 3]),
            {(0, 0): 1, (0, 1): 2, (0, 2): 3},
        ),
        (
            Method(name="from_np_array", initial_value=np.array([1.0, 2.0, 3.0])),
            {(0, 0): 1, (0, 1): 2, (0, 2): 3},
        ),
        (
            Method(name="from_list_via_process_function", initial_value=[1, 2, 3]),
            {(0, 0): 1, (0, 1): 2, (0, 2): 3},
        ),
        (
            Method(name="from_np_array_via_process_function", initial_value=np.array([1.0, 2.0, 3.0])),
            {(0, 0): 1, (0, 1): 2, (0, 2): 3},
        ),
        (
            Method(
                name="with_ref",
                initial_value="initial_values_col",
                profile=pd.DataFrame(pd.DataFrame({"initial_values_col": [1, 2, 3]})),
            ),
            {(0, 0): 1, (0, 1): 2, (0, 2): 3},
        ),
    ],
)
def test_setting_initial_values(empty_model, method: Method, expected_values: InitialValue):
    port_params = {
        "flows": Flows.Both,
        "import_constraint": FlowConstraint.Fixed,
        "import_constraint_value": 1.0,
        "export_constraint_value": -1.0,
        "flow_type": OptimisationType.Variable,
        "units": Units.KW,
    }

    port = Port(**port_params, port_name="port")

    match method.name:
        case "from_dict":
            assert isinstance(method.initial_value, dict)
            port.set_initial_value(initial_value=method.initial_value)
        case "from_dict_via_process_function":
            assert isinstance(method.initial_value, dict)
            port.process_initial_value(initial_val=method.initial_value)
        case "from_timeseriesdata":
            assert isinstance(method.initial_value, TimeSeriesData)
            port.set_initial_value_from_timeseriesdata(time_series_data=method.initial_value)
        case "from_list" | "from_np_array":
            assert isinstance(method.initial_value, list) or isinstance(method.initial_value, np.ndarray)
            port.set_initial_value_from_array(array=method.initial_value, time_periods=method.number_of_intervals)
        case "from_list_via_process_function" | "from_np_array_via_process_function":
            assert isinstance(method.initial_value, list) or isinstance(method.initial_value, np.ndarray)
            port.process_initial_value(initial_val=method.initial_value, time_periods=method.number_of_intervals)
        case "with_ref":
            assert isinstance(method.initial_value, str)
            initial_val_ref = method.initial_value
            port.process_initial_value(initial_val=initial_val_ref)

    model = empty_model(number_of_intervals=method.number_of_intervals)
    port.add_port_to_model(model, profile=method.profile)
    assert hasattr(model, port.port_name)
    assert getattr(model, port.port_name).get_values() == expected_values


@pytest.mark.parametrize("active_periods", [[False, True, True], [0, 1, 1]])
def test_setting_active_periods(empty_model, active_periods):
    port_params = {
        "flows": Flows.Both,
        "import_constraint": FlowConstraint.Fixed,
        "import_constraint_value": 1.0,
        "export_constraint_value": -1.0,
        "flow_type": OptimisationType.Variable,
        "units": Units.KW,
    }

    port = Port(**port_params, port_name="port")

    number_of_intervals = len(active_periods)
    port.set_active_periods_from_array(array=active_periods, time_periods=number_of_intervals)

    model = empty_model(number_of_intervals=number_of_intervals)
    port.add_port_to_model(model, profile=None)
    assert hasattr(model, f"active_con1_{port.port_name}")
    assert hasattr(model, f"active_con2_{port.port_name}")
    # It's difficult to test the active periods are set correctly on the model because they are closed over by
    # the constraint rules `on_off_rule1` and `on_off_rule2`


@pytest.mark.parametrize(
    "import_constraint_value, export_constraint_value, expected_upper_bounds, expected_lower_bounds",
    [
        (1.0, -1.0, [1.0] * 6, [-1.0] * 6),  # same constrain value across all time periods
        (
            [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],  # varying constaint value (across time periods)
            [-1.0, -2.0, -3.0, -4.0, -5.0, -6.0],
            [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            [-1.0, -2.0, -3.0, -4.0, -5.0, -6.0],
        ),
    ],
)
def test_setting_flow_bounds(
    empty_model, import_constraint_value, export_constraint_value, expected_upper_bounds, expected_lower_bounds
):
    number_of_intervals = len(expected_upper_bounds)
    assert number_of_intervals == len(expected_lower_bounds)
    port_params = {
        "flows": Flows.Both,
        "import_constraint": FlowConstraint.Fixed,
        "import_constraint_value": import_constraint_value,
        "export_constraint": FlowConstraint.Fixed,
        "export_constraint_value": export_constraint_value,
        "flow_type": OptimisationType.Variable,
        "units": Units.KW,
        "slack": False,
    }

    port = Port(**port_params, port_name="port")

    model = empty_model(number_of_intervals=number_of_intervals)
    port.add_port_to_model(model, profile=None)

    assert hasattr(model, port.port_name)
    flow = getattr(model, port.port_name)
    lower_bounds = [v.lower for v in flow.values()]
    upper_bounds = [v.upper for v in flow.values()]
    assert upper_bounds == expected_upper_bounds
    assert lower_bounds == expected_lower_bounds

    # Port flow bounds aren't compatible with slack
    # Verify no slack variables present on the model
    assert not hasattr(model, port.import_slack)
    assert not hasattr(model, port.import_slack_max)
    assert not hasattr(model, port.export_slack)
    assert not hasattr(model, port.export_slack_max)

    # Verify objective lacks contributions (which only happen when slack is enabled)
    port.add_objective(model)
    assert port.objective == 0


@pytest.mark.parametrize(
    "import_constraint_value, export_constraint_value, expected_upper_bounds, expected_lower_bounds",
    [
        (1.0, -1.0, [1.0] * 6, [-1.0] * 6),  # same constrain value across all time periods
        (
            [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],  # varying constaint value (across time periods)
            [-1.0, -2.0, -3.0, -4.0, -5.0, -6.0],
            [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            [-1.0, -2.0, -3.0, -4.0, -5.0, -6.0],
        ),
    ],
)
def test_enabling_slack(
    empty_model, import_constraint_value, export_constraint_value, expected_upper_bounds, expected_lower_bounds
):
    number_of_intervals = len(expected_upper_bounds)
    assert number_of_intervals == len(expected_lower_bounds)
    port_params = {
        "flows": Flows.Both,
        "import_constraint": FlowConstraint.Fixed,
        "import_constraint_value": import_constraint_value,
        "export_constraint": FlowConstraint.Fixed,
        "export_constraint_value": export_constraint_value,
        "flow_type": OptimisationType.Variable,
        "units": Units.KW,
        "slack": True,
    }

    port = Port(**port_params, port_name="port")

    model = empty_model(number_of_intervals=number_of_intervals)
    port.add_port_to_model(model, profile=None)

    assert hasattr(model, port.port_name)
    assert hasattr(model, port.import_slack)
    assert hasattr(model, port.import_slack_max)
    assert hasattr(model, port.export_slack)
    assert hasattr(model, port.export_slack_max)

    assert port.objective == 0
    port.add_objective(model)
    assert isinstance(port.objective, pyo.core.expr.numeric_expr.SumExpression)
    assert port.objective.nargs() == 4  # The objective expressions should have 4 terms

    # Slack is not compatible with port flow bounds
    # Verify all bounds on flow variable are None
    flow = getattr(model, port.port_name)
    lower_bounds = [v.lower for v in flow.values()]
    upper_bounds = [v.upper for v in flow.values()]
    assert upper_bounds == [None] * number_of_intervals
    assert lower_bounds == [None] * number_of_intervals


@pytest.mark.parametrize(
    "flow_type, is_fixed", [(OptimisationType.Variable, False), (OptimisationType.Parameter, True)]
)
def test_port_flow_type(flow_type: OptimisationType, is_fixed: bool, empty_model):
    """A port flow can be variable or a "parameter"

    Parameters are still indexed variables but have been fixed using calling `.fix()`
    """
    number_of_intervals = 6
    port_params = {
        "flows": Flows.Both,
        "import_constraint": FlowConstraint.NoConstraint,
        "export_constraint": FlowConstraint.NoConstraint,
        "flow_type": flow_type,
        "units": Units.KW,
        "slack": True,
    }

    port = Port(**port_params, port_name="port")

    model = empty_model(number_of_intervals=number_of_intervals)
    port.add_port_to_model(model, profile=None)
    assert hasattr(model, port.port_name)
    flow = getattr(model, port.port_name)
    assert isinstance(flow, IndexedVar)

    def indexed_var_is_fixed(var: IndexedVar) -> bool:
        return all([v.fixed for v in var.values()])

    assert indexed_var_is_fixed(flow) == is_fixed


def test_splitting_flow_variable(empty_model):
    number_of_intervals = 6
    port_params = {
        "flows": Flows.Both,
        "import_constraint": FlowConstraint.NoConstraint,
        "export_constraint": FlowConstraint.NoConstraint,
        "flow_type": OptimisationType.Variable,
        "units": Units.KW,
        "slack": True,
    }

    port = Port(**port_params, port_name="port")

    model = empty_model(number_of_intervals=number_of_intervals)
    port.add_port_to_model(model, profile=None)

    # Check variables before splitting
    assert hasattr(model, port.port_name)
    assert not hasattr(model, port.pos)
    assert not hasattr(model, port.neg)
    assert not hasattr(model, port.is_pos)

    port.constrain_pos_neg(model)

    # Check variables
    assert hasattr(model, port.port_name)
    assert hasattr(model, port.pos)
    assert hasattr(model, port.neg)
    assert hasattr(model, port.is_pos)

    # Check constraints
    assert hasattr(
        model, f"{constants.positive_variable_component}{constants.negative_variable_component}{port.port_name}"
    )
    assert hasattr(model, f"pos_neg_con1_{port.port_name}")
    assert hasattr(model, f"pos_neg_con2_{port.port_name}")
