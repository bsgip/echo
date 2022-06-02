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


def import_cons_check(cls, v):
    if v is not None:
        if v < 0:
            raise ValueError('Import constraint should be positive')


def export_cons_check(cls, v):
    if v is not None:
        if v > 0:
            raise ValueError('Export constraint should be negative')


def nonnegative_load(cls, v):
    """ Validate array field that should have non negative entries"""
    if v is not None:
        array = np.array([x for x in v.values()])
        if not (array >= 0).all():
            raise ValueError('Load array entries should all be non negative.')
    return v


def nonpositive_generation(cls, v):
    """ Validate array field that should have non positive entries"""
    if v is not None:
        array = np.array([x for x in v.values()])
        if not (array <= 0).all():
            raise ValueError('Generation array entries should all be non positive.')
    return v


