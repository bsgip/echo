import uuid
import pickle
import uuid
import warnings
from typing import Optional, Union, List, Any, Tuple

import matplotlib.pyplot as plt
import networkx as nx

from pydantic import BaseModel as PydanticBaseModel, PositiveFloat, NonNegativeFloat
from pydantic import validator, root_validator, confloat

from echo.configuration import *
from echo.constants import *
from echo.utils import *

DataFrame = TypeVar('pandas.core.frame.DataFrame')

"""

    Base models

"""


class BaseModel(PydanticBaseModel):
    """ Create a modified basemodel with the config we want."""

    class Config:
        validate_assignment = True  # Set to true so that we re-validate when we update a model field
        extra = 'ignore'  # If 'allow', extra attributes can be added after instantiation, if 'ignore', extra attributes are ignored, if 'forbid', extra attributes are not allowed.


class PortChecker(BaseModel):
    " input checker for port class"
    units: Units = Units.NA  # Used to ensure that common units are being optimised over at points of interconnection
    initial_value: dict = 0.
    initial_value_ref: Optional[str]  # string ref to df column
    opt_type: OptimisationType = OptimisationType.NA
    uid: uuid.UUID = Field(default_factory=uuid.uuid4)  # this dynamically sets a unique ID?
    port_name: Optional[str] = None
    flows: Flows = Flows.NA  # What flow directions are possible (import, export, both)
    # Used to define the nature of import / export directions and constraints
    import_constraint: FlowConstraint = FlowConstraint.NA
    import_constraint_value: Union[ArrayType, float, None] = None
    export_constraint: FlowConstraint = FlowConstraint.NA
    export_constraint_value: Union[ArrayType, float, None] = None
    active_periods: Optional[dict]
    slack: bool = False
    objective: Optional[Any] = 0  # this will eventually be a pyomo expression

    # Validators for import/export constraint values
    import_con_sign = validator("import_constraint_value", allow_reuse=True)(import_cons_check)
    export_con_sign = validator("export_constraint_value", allow_reuse=True)(export_cons_check)

class TransformChecker(BaseModel):
    """ Input checker for transform class """
    uid: uuid.UUID = Field(default_factory=uuid.uuid4)  # this dynamically sets a unique ID
    transform_name: Optional[str] = None
    lhs: list = []
    rhs = 0

class NodeChecker(BaseModel):
    """
    Input checker for node class
    """
    node_name: Optional[str]
    uid: uuid.UUID = Field(default_factory=uuid.uuid4)  # this dynamically sets a unique ID
    ports: dict = {}
    node_rule: NodeRule = NodeRule.NA
    transformations: dict = {}
    objective: Optional[Any] = 0  # For adding any node objectives


class EdgeChecker(BaseModel):
    """
    Input checker for edge class
    """
    uid: uuid.UUID = Field(default_factory=uuid.uuid4)  # this dynamically sets a unique ID
    edge_name: Optional[str] = None
    vertices: Tuple[object, object]
    nodes: Optional[Tuple[str, str]]  # tuple of node names - todo make this required
    tariff: Optional[Union[list, None]]

class OptimisationGraphChecker(BaseModel):
    "Input checker for the optimisation graph class"
    node_obj: dict = {}
    edge_obj: dict = {}
    paths: dict = {}

class PathChecker(BaseModel):
    """ Input checker for the path class """
    edge_ports: List[tuple] = []  # list of edge name tuples
    vertices: list  # list of node names
    uid: uuid.UUID = Field(default_factory=uuid.uuid4)  # this dynamically sets a unique ID?
    path_name: Optional[str] = None
    units = Units.KW
    regularise: bool = False
    objective: Optional[Any] = 0

    contingency_neg: Optional[str]
    contingency_pos: Optional[str]
    path_tariff: Optional[str]
    slack: Optional[str]


class ControlledLoadOrGenChecker(BaseModel):
    """
    Input checker for controlled load or generation
    """
    min_utilisation: Union[float, None] = None
    max_utilisation: float = None
    max_power: float = None
    min_power: float = None
    units: Units = Units.KW

class OffOrConstrainedPortChecker(BaseModel):
    """ input validor for on or off constrained power"""
    lower_bound: float
    upper_bound: float

    bounds_check = root_validator(allow_reuse=True)(check_bound_order)  # checks that lower bound < upper bound


class BoundedPortChecker(BaseModel):
    """ A flex port with an upper and lower bound"""
    upper_bound: Union[ArrayType, float]
    lower_bound: Union[ArrayType, float]

    bound_check = root_validator(allow_reuse=True)(check_bound_order)  # check lower bound < upper bound


class StorageChecker(BaseModel):
    """ Input checker for storage class"""
    max_capacity: float
    depth_of_discharge_limit: float = 0  # DoD limit is the percent soc to which you can discharge the storage
    min_soc: float = 0
    charging_power_limit: float
    discharging_power_limit: float
    charging_efficiency: float = 1
    discharging_efficiency: float = 1
    initial_state_of_charge: float
    fixed_storage_capacity: bool = True
    storage_capacity_cost: Optional[PositiveFloat]
    regularise: bool = False

    dod_check = root_validator(allow_reuse=True)(dod_checks)