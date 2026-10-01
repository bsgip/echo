from collections.abc import Generator
from numbers import Number
from typing import Any

import numpy as np
from pydantic import Field

from echo.exceptions import validate

FloatData = dict[Any, float] | list[float] | set[float] | float | np.ndarray


class ArrayType(np.ndarray):
    numpy_array: np.ndarray = Field(default_factory=lambda: np.zeros(10))

    @classmethod
    def __get_validators__(cls) -> Generator:
        yield cls.validate

    # todo actually validate this type
    @classmethod
    def validate(cls, v: np.ndarray) -> np.ndarray:
        if type(v) is str:
            raise ValueError("Array Type cannot be a string.")
        return v

    class Config:
        arbitrary_types_allowed = True


def var_in_range(var1: float, range_min: float, range_max: float) -> ValueError | None:
    if var1 < range_min or var1 > range_max:
        return ValueError()


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


def import_cons_check(v: FloatData) -> FloatData:
    v = is_non_negative(v, "Import constraint should be positive, following positive load convention")
    return v


def export_cons_check(v: FloatData) -> FloatData:
    v = is_non_positive(v, "Export constraint should be negative following positive load convention.")
    return v


def nonnegative_load(v: FloatData) -> FloatData:
    v = is_non_negative(v, "Load array entries should all be non negative.")
    return v


def nonpositive_generation(v: FloatData) -> FloatData:
    v = is_non_positive(v, "Generation array entries should all be non positive.")
    return v


def nonnegative_costs(v: FloatData) -> FloatData:
    v = is_non_negative(v, "Costs should be positive")
    return v


def dod_checks(cls, values: dict) -> dict:  # noqa ANN001
    """Validator for depth of discharge."""
    # Check which dod representation we have
    dod_lim = values.get("depth_of_discharge_limit")
    max_cap = values.get("max_capacity")
    init_soc = values.get("initial_state_of_charge")
    set_stateful_attrs_at_init = values.get("set_stateful_attrs_at_init")

    # Check dod representation
    if 0 <= dod_lim <= 1:
        # Assume decimal representation
        min_soc = max_cap * dod_lim
    elif 1 < dod_lim <= 100:
        # Assume percentage representation
        min_soc = max_cap * dod_lim / 100.0
    else:
        raise ValueError("DoD must be entered as decimal fraction or percentage of max capacity")

    values["min_soc"] = min_soc

    # Check initial soc is within bounds
    if set_stateful_attrs_at_init:
        check_initial_state_of_charge_within_bounds(
            initial_state_of_charge=init_soc, min_soc=min_soc, max_capacity=max_cap
        )

    return values


def check_initial_state_of_charge_within_bounds(
    initial_state_of_charge: float, min_soc: float, max_capacity: float
) -> None:
    # Check initial soc is within bounds
    if (initial_state_of_charge < min_soc) or (initial_state_of_charge > max_capacity):
        raise ValueError(
            f"Initial state of charge, {initial_state_of_charge}, must be between min soc, {min_soc},"
            f"and max capacity, {max_capacity}"
        )


def check_bound_order(cls, values: dict) -> dict:  # noqa ANN001
    """Checks that lower bound is smaller than upper bound."""
    lb = values.get("lower_bound")
    ub = values.get("upper_bound")
    if (lb is not None) and (ub is not None):
        if hasattr(lb, "__iter__"):
            validate(len(lb) == len(ub), "Lower bound and upper bound are mismatched lengths.")
            for i in range(len(lb)):
                if lb[i] >= ub[i]:
                    raise ValueError("Lower bound should be less than upper bound.")
        else:
            if lb >= ub:
                raise ValueError("Lower bound should be less than upper bound.")
    return values


def ports_have_same_units_validator(obj, attributes, value) -> None:  # noqa ANN001
    """Raises a ConfigurationError if the units of the ports are not the same"""
    port_units = set([port.units for port in value.values()])
    validate(len(port_units) <= 1, "Tellegen and Aggregation Node ports must have the same units.")


def ports_match_nominal_units_validator(obj, attributes, value) -> None:  # noqa ANN001
    if hasattr(obj, "nominal_units"):
        if obj.nominal_units is not None:
            for port_name, port in value.items():
                validate(
                    port.units == obj.nominal_units,
                    f"Port '{port_name}' units do not match nominal node units '{obj.nominal_units}'.",
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
    if input_points is not None and output_points is not None:
        instance.max_input = max(max(input_points.values()))
        instance.min_input = min(min(input_points.values()))
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


def set_output_bounds_from_input_bounds_and_cop_and_startup_cop(cls, values: dict) -> dict:  # noqa ANN001
    cop = values.get("cop")
    eta = values.get("startup_cop")
    max_in = values.get("max_input")
    min_in = values.get("min_input")
    values["max_output"] = max_in * cop * -1
    if eta is not None:
        values["min_output"] = min_in * eta * -1
    else:
        values["min_output"] = min_in * cop * -1
    return values


def startup_efficiency_validator(instance, attributes, value) -> None:  # noqa ANN001
    if instance.startup_cop is not None:
        validate(
            instance.cop >= instance.startup_cop,
            "Startup efficiency should be less than coefficient of performance (cop)",
        )


def validate_startup_efficiency(cls, values: dict) -> dict:  # noqa ANN001
    cop = values.get("cop")
    eta = values.get("startup_cop")
    if eta is not None:
        validate(cop >= eta, "Startup efficiency should be less than coefficient of performance (cop)")
    return values


def validate_partial_load_cop(cls, values: dict) -> dict:  # noqa ANN001
    partial_load_cop = values.get("partial_load_cop")
    for k, v in partial_load_cop.items():
        validate(
            0 <= k <= 1,
            f"All keys in partial load cop must be float values between 0 and 1, offending key {k}",
        )
        validate(
            0 <= v <= 1,
            f"All values in partial load cop must be float values between 0 and 1, offending value {v}",
        )
    return values


def validate_temperature_dependent_cop(cls, values: dict) -> dict:  # noqa ANN001
    """Validate temperature dependent cop dictionary"""
    temperature_cop_coeff = values.get("temperature_dependent_cop")
    for k, v in temperature_cop_coeff.items():
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
    return values


def non_negative_cop_check(v: FloatData) -> FloatData:
    v = is_non_negative(v, "Coefficient of performance for heating and cooling must be given as non_negative value")
    return v


def partitions_port_validator(obj, attributes, value) -> None:  # noqa ANN001
    """Validate that set of ports defined across different partitions are unique"""
    partitions = value
    node_name = obj.node_name if hasattr(obj, "node_name") else "unknown-node"
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
