from numbers import Number
from typing import Any

import attrs
import numpy as np
import pyomo.environ as en

from echo.configuration import Units
from echo.exceptions import ConfigurationError, validate

FloatData = dict[Any, float] | list[float] | set[float] | float | np.ndarray

# ArrayType is a type alias for np.ndarray
# Originally ArrayType was a subclass of np.ndarray with added pydantic type validation
# This is not possible in attrs (type annotation have no runtime effects outside of pydantic
# and so can't "trigger" any validation) hence we replace the ArrayType class with a type alias.
ArrayType = np.ndarray


def is_non_negative(v: FloatData | None, err_msg: str) -> FloatData | None:
    """Tests is a 'v' is non negative

    A value of 0 is considered non-negative (i.e. doesn't raise a ValueError) for the purposes of this test
    """
    if v is None:
        return v

    if isinstance(v, Number):
        values = [v]
    elif isinstance(v, dict):
        values = v.values()
    else:
        values = v  # v is list, set or numpy array

    if any([i < 0 for i in values]):
        raise ValueError(err_msg)

    return v


def is_non_positive(v: FloatData | None, err_msg: str) -> FloatData | None:
    """Tests is a 'v' is non positive

    A value of 0 is considered non-positive (i.e. doesn't raise a ValueError) for the purposes of this test
    """
    if v is None:
        return v

    if isinstance(v, Number):
        values = [v]
    elif isinstance(v, dict):
        values = v.values()
    else:
        values = v  # v is list, set or numpy array

    if any([i > 0 for i in values]):
        raise ValueError(err_msg)

    return v


def import_constraint_validator(instance, attributes, value) -> None:  # noqa ANN001
    is_non_negative(value, "Import constraint should be positive, following positive load convention")


def export_constraint_validator(instance, attributes, value) -> None:  # noqa ANN001
    is_non_positive(value, "Export constraint should be negative following positive load convention.")


def nonnegative_load_validator(instance, attributes, value) -> None:  # noqa ANN001
    is_non_negative(value, "Load array entries should all be non negative.")


def nonpositive_generation_validator(instance, attributes, value) -> None:  # noqa ANN001
    is_non_positive(value, "Generation array entries should all be non positive.")


def update_constraint_values(instance, attributes, value) -> None:  # noqa ANN001
    # Keeps the charging/discharging power limits in sync the import/export constraint limits
    instance.import_constraint_value = instance.charging_power_limit
    instance.export_constraint_value = instance.discharging_power_limit


def depth_of_discharge_validator(instance, attributes, value) -> None:  # noqa ANN001
    """Validator for depth of discharge."""
    # Check which dod representation we have
    dod_lim = instance.depth_of_discharge_limit
    max_cap = instance.max_capacity

    # Check dod representation
    if 0 <= dod_lim <= 1:
        # Assume decimal representation
        min_soc = max_cap * dod_lim
    elif 1 < dod_lim <= 100:
        # Assume percentage representation
        min_soc = max_cap * dod_lim / 100.0
    else:
        raise ValueError("DoD must be entered as decimal fraction or percentage of max capacity")

    instance.min_soc = min_soc


def soc_conserv_validator(instance, attributes, value) -> None:  # noqa ANN001
    """Check there is a converv cost and availability when soc conserv is enabled"""
    soc_conserv = instance.soc_conserv
    soc_conserv_cost = instance.soc_conserv_cost
    available = instance.available
    if soc_conserv is not None:
        validate(soc_conserv_cost is not None, "soc_conserv requires soc_conserv_cost")
        validate(available is not None, "soc_conserve requires available")


def check_initial_state_of_charge_within_bounds(
    initial_state_of_charge: float, min_soc: float, max_capacity: float
) -> None:
    # Check initial soc is within bounds
    if (initial_state_of_charge < min_soc) or (initial_state_of_charge > max_capacity):
        raise ValueError(
            f"Initial state of charge, {initial_state_of_charge}, must be between min soc, {min_soc},"
            f"and max capacity, {max_capacity}"
        )


def bound_order_validator(instance, attributes, value) -> None:  # noqa ANN001
    """Checks that lower bound is smaller than upper bound."""
    lb = instance.lower_bound
    ub = instance.upper_bound
    if (lb is not None) and (ub is not None):
        if hasattr(lb, "__iter__"):
            validate(len(lb) == len(ub), "Lower bound and upper bound are mismatched lengths.")
            for i in range(len(lb)):
                if lb[i] >= ub[i]:
                    raise ValueError("Lower bound should be less than upper bound.")
        else:
            if lb >= ub:
                raise ValueError("Lower bound should be less than upper bound.")


def ports_have_same_units_validator(instance, attributes, value) -> None:  # noqa ANN001
    """Raises a ConfigurationError if the units of the ports are not the same"""
    port_units = set([port.units for port in value.values()])
    validate(len(port_units) <= 1, "Tellegen and Aggregation Node ports must have the same units.")


def ports_match_nominal_units_validator(instance, attributes, value) -> None:  # noqa ANN001
    if hasattr(instance, "nominal_units"):
        if instance.nominal_units is not None:
            for port_name, port in value.items():
                validate(
                    port.units == instance.nominal_units,
                    f"Port '{port_name}' units do not match nominal node units '{instance.nominal_units}'.",
                )


def piecewise_arrays_validator(instance, attributes, value) -> None:  # noqa ANN001
    input_points = instance.input_points if hasattr(instance, "input_points") else None
    output_points = instance.output_points if hasattr(instance, "output_points") else None
    if input_points is not None and output_points is not None:
        validate(len(input_points) == len(output_points), "Mismatched indices for input and output dictionaries.")
        for k, _ in input_points.items():
            validate(
                len(input_points[k]) == len(output_points[k]),
                f"Input and output arrays are not equal lengths for index {k}",
            )


def set_bounds_from_piecewise_points_validator(instance, attributes, value) -> None:  # noqa ANN001
    input_points = instance.input_points
    output_points = instance.output_points
    if input_points is not None:
        instance.max_input = max(max(input_points.values()))
        instance.min_input = min(min(input_points.values()))
    if output_points is not None:
        instance.max_output = max(max(output_points.values()))
        instance.min_output = min(min(output_points.values()))


def set_output_bounds_validator(instance, attributes, values) -> None:  # noqa ANN001
    if instance.min_input is None:
        raise ValueError("'min_input' must be set on GasBoilerFixedCOP.")
    instance.max_output = instance.max_input * instance.cop * -1
    if instance.startup_cop is not None:
        instance.min_output = instance.min_input * instance.startup_cop * -1
    else:
        instance.min_output = instance.min_input * instance.cop * -1


def startup_efficiency_validator(instance, attributes, value) -> None:  # noqa ANN001
    if instance.startup_cop is not None:
        validate(
            instance.cop >= instance.startup_cop,
            "Startup efficiency should be less than coefficient of performance (cop)",
        )


def partial_load_cop_validator(instance, attributes, value) -> None:  # noqa ANN001
    for k, v in value.items():
        validate(
            0 <= k <= 1,
            f"All keys in partial load cop must be float values between 0 and 1, offending key {k}",
        )
        validate(
            0 <= v <= 1,
            f"All values in partial load cop must be float values between 0 and 1, offending value {v}",
        )


def temperature_dependent_cop_validator(instance, attributes, value) -> None:  # noqa ANN001
    for k, v in value.items():
        validate(
            -10 <= k <= 50,
            # TODO: reasonable value range is different between air cooled and water cooled chillers.
            #  Do this validation better
            f"All keys in temperature dependent cop must be float values representing ambient operational "
            f"temperature expecting values between -10 and 50, offending key {k}",
        )
        validate(
            0 < v <= 1,
            f"All values in temperature dependent cop must be float values between 0 and 1, offending value {v}",
        )


def non_negative_cop_validator(instance, attributes, value) -> None:  # noqa ANN001
    is_non_negative(value, "Coefficient of performance for heating and cooling must be given as non_negative value")


def partitions_port_validator(instance, attributes, value) -> None:  # noqa ANN001
    """Validate that set of ports defined across different partitions are unique"""
    partitions = value
    node_name = instance.node_name if hasattr(instance, "node_name") else "unknown-node"
    port_name_list = [_port.port_name for v in partitions.values() for _port in v]
    port_uid_list = [_port.uid for v in partitions.values() for _port in v]
    validate(
        len(port_name_list) == len(set(port_name_list)),
        "All ports defined across partitions of PartitionedMultiCommodityTellegenNode must have unique names."
        f"Offending node '{node_name}'",
    )
    validate(
        len(port_uid_list) == len(set(port_uid_list)),
        "All ports defined across partitions of PartitionedMultiCommodityTellegenNode must have unique uids."
        f"Offending node '{node_name}'",
    )


def thermal_units_validator(instance, attributes, value) -> None:  # noqa ANN001
    allowable_thermal_units = {Units.JPS, Units.KWT}
    if value not in allowable_thermal_units:
        raise ValueError(f"Only allowed units are KW Thermal (KWT) and Joules per second (JPS). Received {value}")


def temperature_range_validator(instance, attributes, value) -> None:  # noqa ANN001
    """Temperature range must be non-zero and positive"""
    if instance.max_temp - instance.min_temp <= 0:
        raise ValueError(
            "Temperature range must be non-zero and positive."
            f"Max temp ('{instance.max_temp}') <= min temp ('{instance.min_temp}')."
        )


def import_or_export_demand_set_validator(instance, attributes, value) -> None:  # noqa ANN001
    if not instance.import_demand and not instance.export_demand:
        raise ConfigurationError(
            "Please use set either DemandCharge.import_demand or Demand.export_demand."
            " Alternatively use instances of ImportDemandCharge or ExportDemandCharge."
        )


def reset_periods_validator(instance, attributes, value) -> None:  # noqa ANN001
    if instance.reset_periods is not None:
        validate(
            sum(instance.reset_periods) == len(instance.window_array),
            (
                f"Sum of reset period lengths ({sum(instance.reset_periods)}) is not equal"
                f" to window array length ({len(instance.window_array)})."
            ),
        )
    else:
        # Prevent attrs from retriggering this validator again when we set 'reset_periods' from within the validator
        with attrs.validators.disabled():
            instance.reset_periods = [len(instance.window_array)]

    instance.num_reset_periods = len(instance.reset_periods)
    instance.reset_index = en.RangeSet(0, instance.num_reset_periods - 1)


def block_rates_validator(instance, attributes, value) -> None:  # noqa ANN001
    validate(
        len(instance.blocks) + 1 == len(instance.rates),
        "Enter one more rate than num blocks",
    )
