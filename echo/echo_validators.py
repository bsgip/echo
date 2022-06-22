from pydantic import BaseModel, Field
import numpy as np


class ArrayType(np.ndarray):
    numpyArray: np.ndarray = Field(default_factory=lambda: np.zeros(10))

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    #todo actually validate this type
    @classmethod
    def validate(cls, v):
        return v

    class Config:
        arbitrary_types_allowed = True

def var_in_range(var1, range_min, range_max):
    if var1 < range_min or var1 > range_max:
        return ValueError()


def is_non_negative(v, err_msg):
    if v is not None:
        if hasattr(v, '__iter__'):
            if type(v) is dict:
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
        if hasattr(v, '__iter__'):
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
    v = is_non_negative(v, 'Import constraint should be positive, following positive load convention')
    return v

def export_cons_check(v):
    v = is_non_positive(v, 'Export constraint should be negative following positive load convention.')
    return v

def nonnegative_load(v):
    v = is_non_negative(v, 'Load array entries should all be non negative.')
    return v

def nonpositive_generation(v):
    v = is_non_positive(v, 'Generation array entries should all be non positive.')
    return v

def nonnegative_costs(v):
    v = is_non_negative(v, 'Costs should be positive')
    return v

def dod_checks(cls, values):
    """ Validator for depth of discharge."""
    # Check which dod representation we have
    dod_lim = values.get('depth_of_discharge_limit')
    max_cap = values.get('max_capacity')
    init_soc = values.get('initial_state_of_charge')
    # Check dod representation
    if 0 <= dod_lim <= 1:
        # Assume decimal representation
        min_soc = max_cap * dod_lim
    elif 1 < dod_lim <= 100:
        # Assume percentage representation
        min_soc = max_cap * dod_lim / 100.0
    else:
        raise ValueError('DoD must be entered as decimal fraction or percentage of max capacity')
    # Check initial soc is within bounds
    if (init_soc < min_soc) or (init_soc > max_cap):
        raise ValueError(
            'Initial state of charge, {}, must be between min soc, {}, and max capacity, {}'.format(init_soc,
                                                                                                    min_soc,
                                                                                                    max_cap))
    values['min_soc'] = min_soc
    return values


