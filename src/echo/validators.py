import numpy as np
from pydantic import Field

from echo.exceptions import validate


class ArrayType(np.ndarray):
    numpyArray: np.ndarray = Field(default_factory=lambda: np.zeros(10))

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    # todo actually validate this type
    @classmethod
    def validate(cls, v):
        if type(v) is str:
            raise ValueError("Array Type cannot be a string.")
        return v

    class Config:
        arbitrary_types_allowed = True


def var_in_range(var1, range_min, range_max):
    if var1 < range_min or var1 > range_max:
        return ValueError()


def is_non_negative(v, err_msg):
    if v is not None:
        if hasattr(v, "__iter__"):
            if isinstance(v, dict):
                for i in v.values():
                    if i < 0:
                        raise ValueError(err_msg)
            else:
                for i in v:
                    if i < 0:
                        raise ValueError(err_msg)
        else:
            if v < 0:
                raise ValueError(err_msg)
    return v


def is_non_positive(v, err_msg):
    if v is not None:
        if hasattr(v, "__iter__"):
            if type(v) is dict:
                for i in v.values():
                    if i > 0:
                        raise ValueError(err_msg)
            else:
                for i in v:
                    if i > 0:
                        raise ValueError(err_msg)
        else:
            if v > 0:
                raise ValueError(err_msg)
    return v


def import_cons_check(v):
    v = is_non_negative(v, "Import constraint should be positive, following positive load convention")
    return v


def export_cons_check(v):
    v = is_non_positive(v, "Export constraint should be negative following positive load convention.")
    return v


def nonnegative_load(v):
    v = is_non_negative(v, "Load array entries should all be non negative.")
    return v


def nonpositive_generation(v):
    v = is_non_positive(v, "Generation array entries should all be non positive.")
    return v


def nonnegative_costs(v):
    v = is_non_negative(v, "Costs should be positive")
    return v


def dod_checks(cls, values):
    """Validator for depth of discharge."""
    # Check which dod representation we have
    dod_lim = values.get("depth_of_discharge_limit")
    max_cap = values.get("max_capacity")
    init_soc = values.get("initial_state_of_charge")
    # Check dod representation
    if 0 <= dod_lim <= 1:
        # Assume decimal representation
        min_soc = max_cap * dod_lim
    elif 1 < dod_lim <= 100:
        # Assume percentage representation
        min_soc = max_cap * dod_lim / 100.0
    else:
        raise ValueError("DoD must be entered as decimal fraction or percentage of max capacity")
    # Check initial soc is within bounds
    if (init_soc < min_soc) or (init_soc > max_cap):
        raise ValueError(
            "Initial state of charge, {}, must be between min soc, {}, and max capacity, {}".format(
                init_soc, min_soc, max_cap
            )
        )
    values["min_soc"] = min_soc
    return values


def check_bound_order(cls, values):
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


def node_unit_validator(cls, values):
    """Checks that a tellegen and aggregation nodes' ports all have the same units."""
    ports = values.get("ports")
    u = None
    nominal_units = values.get("port_units")
    if ports is not None:
        for port_key, p in ports.items():
            if u is not None:
                validate(p.units == u, "Tellegen and Aggregation Node ports must have the same units.")
            else:
                u = p.units
            if nominal_units is not None:
                validate(
                    p.units == nominal_units, f"Port {port_key} units do not match nominal node units {nominal_units}."
                )

    return values


def validate_piecewise_arrays(cls, values):
    input_points = values.get("input_points")
    output_points = values.get("output_points")
    if input_points is not None and output_points is not None:
        validate(len(input_points) == len(output_points), "Mismatched indices for input and output dictionaries.")
        for k, _ in input_points.items():
            validate(
                len(input_points[k]) == len(output_points[k]),
                "Input and output arrays are not equal lengths for index {}".format(k),
            )

    return values


def set_bounds_from_piecewise_points(cls, values):
    input_points = values.get("input_points")
    output_points = values.get("output_points")
    if input_points is not None and output_points is not None:
        values["max_input"] = max(max(input_points.values()))
        values["min_input"] = min(min(input_points.values()))
        values["max_output"] = max(max(output_points.values()))
        values["min_output"] = min(min(output_points.values()))
    return values


def set_output_bounds_from_input_bounds_and_cop_and_startup_cop(cls, values):
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


def validate_startup_efficiency(cls, values):
    cop = values.get("cop")
    eta = values.get("startup_cop")
    if eta is not None:
        validate(cop >= eta, "Startup efficiency should be less than coefficient of performance (cop)")
    return values


def validate_partial_load_cop(cls, values):
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


def validate_temperature_dependent_cop(cls, values):
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


def non_negative_cop_check(v):
    v = is_non_negative(v, "Coefficient of performance for heating and cooling must be given as non_negative value")
    return v


def validate_partition_ports(cls, values):
    """Validate that set of ports defined across different partitions are unique"""
    partitions = values.get("partitions")
    port_name_list = [_port.port_name for v in partitions.values() for _port in v]
    port_uid_list = [_port.uid for v in partitions.values() for _port in v]
    validate(
        len(port_name_list) == len(set(port_name_list)),
        "All ports defined across partitions of PartitionedMultiCommodityTellegenNode must have unique names."
        f"Offending node {values.get('node_name')}",
    )
    validate(
        len(port_uid_list) == len(set(port_uid_list)),
        "All ports defined across partitions of PartitionedMultiCommodityTellegenNode must have unique uids."
        f"Offending node {values.get('node_name')}",
    )
    return values
