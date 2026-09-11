from __future__ import annotations  # Deprecating in python 3.15 in favour of lazy annotations (PEP 649 and 749)

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
import pyomo.environ as en
import shortuuid
from pydantic import Field, validator
from pyomo.core import RangeSet
from pyomo.core.expr.relational_expr import EqualityExpression, InequalityExpression

from echo.configuration import FlowConstraint, Flows, OptimisationType, Units
from echo.constants import negative_variable_component, positive_variable_component
from echo.exceptions import ConfigurationError
from echo.models.base import BaseModel
from echo.models.base.types import ConstraintValueType, InitialValue, InitialValueInput
from echo.models.scenario import EchoConcreteModel
from echo.utils import (
    TimeSeriesData,
    domain_from_flow,
    expand_as_dict,
    generate_array_constraint,
    set_var_bounds_from_dict,
    to_initial_values,
)
from echo.validators import export_cons_check, import_cons_check


class Port(BaseModel):
    # Pydantic attribute declaration follows this format:
    # attribute_name: type = default_value

    units: Units = Units.NA  # Used to ensure that common units are being optimised over at points of interconnection
    initial_value: dict[tuple[int, int], float] | None = None
    initial_value_ref: str | None = None  # string ref to df column
    initial_value_scaling: int | None = None  # scaling factor for initial values
    flow_type: OptimisationType = OptimisationType.NA
    uid: str | None = Field(default_factory=shortuuid.uuid)
    port_name: str = ""
    flows: Flows = Flows.NA  # What flow directions are possible (import, export, both)
    # Used to define the nature of import / export directions and constraints
    import_constraint: FlowConstraint = FlowConstraint.NA
    import_constraint_value: ConstraintValueType | None = None
    export_constraint: FlowConstraint = FlowConstraint.NA
    export_constraint_value: ConstraintValueType | None = None
    active_periods: dict[tuple[int, int], Any] | None = None
    slack: bool = False
    objective: en.numeric_expr.NumericExpression | float = 0  # this will eventually be a pyomo expression
    allow_dangling_port: bool = False

    # Validators for import/export constraint values
    import_con_sign = validator("import_constraint_value", allow_reuse=True)(import_cons_check)
    export_con_sign = validator("export_constraint_value", allow_reuse=True)(export_cons_check)

    @property
    def pos(self) -> str:
        return positive_variable_component + self.port_name

    @property
    def neg(self) -> str:
        return negative_variable_component + self.port_name

    @property
    def is_pos(self) -> str:
        return f"is_pos_{self.port_name}"

    @property
    def import_con_val(self) -> str:
        return f"import_con_val_{self.port_name}"

    @property
    def export_con_val(self) -> str:
        return f"export_con_val_{self.port_name}"

    @property
    def import_slack(self) -> str:
        return f"import_slack_{self.port_name}"

    @property
    def import_slack_max(self) -> str:
        return f"import_slack_max_{self.port_name}"

    @property
    def export_slack(self) -> str:
        return f"export_slack_{self.port_name}"

    @property
    def export_slack_max(self) -> str:
        return f"export_slack_max_{self.port_name}"

    def __init__(self, **data) -> None:
        super().__init__(**data)
        if not self.port_name:  # if no name is provided, give it a default name using the uid
            self.port_name = "port_" + str(self.uid)

    def set_flow_constraints(
        self,
        max_import: ConstraintValueType | None,
        max_export: ConstraintValueType | None,
        slack: bool | None = False,
    ) -> None:
        """Sets the values of port flow constraints.

        Args:
            max_import: max allowable import into port (float, array, or None)
            max_export: max allowable export out of port (float, array, or None)
            slack: bool, whether we want to allow slack in the constraint
        """
        if max_import is not None:
            self.import_constraint = FlowConstraint.Fixed
            self.import_constraint_value = max_import

        if max_export is not None:
            self.export_constraint = FlowConstraint.Fixed
            self.export_constraint_value = max_export

        if slack is not None:
            self.slack = slack

    def process_initial_value(
        self,
        initial_val: InitialValueInput | str,
        expansion_periods: int = 1,
        time_periods: int | None = None,
    ) -> None:
        if isinstance(initial_val, dict):
            self.set_initial_value(initial_val)

        elif isinstance(initial_val, str):
            self.initial_value_ref = initial_val

        elif isinstance(initial_val, list | np.ndarray):
            self.set_initial_value_from_array(
                array=initial_val,
                expansion_periods=expansion_periods,
                time_periods=time_periods,
            )

    def verify_port(self) -> None:
        """Used to verify that a port has been set up appropriately"""
        if self.flows is Flows.NA:
            raise ConfigurationError("The flows value cannot be set to a value of NA.")

        if (self.flows is Flows.Import) or (self.flows is Flows.Both):
            if self.import_constraint is FlowConstraint.NA:
                raise ConfigurationError("The Import FlowConstraint cannot be set to a value of NA.")
            if self.import_constraint is FlowConstraint.Fixed and self.import_constraint_value is None:
                raise ConfigurationError(
                    "The Import flow constraint value cannot be set to None when an Import constraint exists."
                )

        if (self.flows is Flows.Export) or (self.flows is Flows.Both):
            if self.export_constraint is FlowConstraint.NA:
                raise ConfigurationError("The Export FlowConstraint cannot be set to a value of NA.")
            if self.export_constraint is FlowConstraint.Fixed and self.export_constraint_value is None:
                raise ConfigurationError(
                    "The Export flow constraint value cannot be set to None when an Export constraint exists."
                )

        if self.flow_type is OptimisationType.NA:
            raise ConfigurationError("The Optimisation Type has to be configured before instantiation.")

        if self.units is Units.NA:
            raise ConfigurationError("The Units parameter has to be configured before instantiation.")

    def _add_flow_variable_to_model(
        self,
        model: EchoConcreteModel,
        initial_value: float | Callable | None,
        domain: RangeSet | Callable | None,
    ) -> None:
        """Adds the flow variable to the echo concrete model.

        Args:
            model: The echo concrete model for the flow variable to be added to.
            initial_value: The initial value for the variable, or a rule that returns initial values.
            domain : A Set that defines valid values for the variable (e.g., Reals, NonNegativeReals, Binary), or a
                rule that returns Sets.

        Returns:
            None
        """
        setattr(
            model,
            self.port_name,
            en.Var(model.Expansion, model.Time, initialize=initial_value, domain=domain),
        )

    def _add_active_period_constraints_to_model(self, model: EchoConcreteModel) -> None:
        if self.active_periods is None:
            raise ValueError("self.active_periods cannot be None.")

        port_active_periods = self.active_periods

        def on_off_rule1(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            return getattr(model, self.port_name)[p, t] <= port_active_periods[p, t] * model.big_m

        def on_off_rule2(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            return getattr(model, self.port_name)[p, t] >= -port_active_periods[p, t] * model.big_m

        setattr(
            model,
            f"active_con1_{self.port_name}",
            en.Constraint(model.Expansion, model.Time, rule=on_off_rule1),
        )
        setattr(
            model,
            f"active_con2_{self.port_name}",
            en.Constraint(model.Expansion, model.Time, rule=on_off_rule2),
        )

    def _add_import_constraints_to_model(self, model: EchoConcreteModel) -> None:
        # Add import constraint parameter
        time_periods = len(model.Time)
        exp_periods = len(model.Expansion)
        # Generate an array of constraints (ie indexed by time and expansion period)
        import_constraint_dict = generate_array_constraint(self.import_constraint_value, time_periods, exp_periods)
        setattr(
            model,
            self.import_con_val,
            en.Param(
                model.Expansion,
                model.Time,
                initialize=import_constraint_dict,
                domain=en.NonNegativeReals,
            ),
        )

        if self.slack:
            self._add_slack_import_constraints_to_model(model=model)
        else:
            set_var_bounds_from_dict(model=model, var_name=self.port_name, ub=import_constraint_dict, lb=None)

    def _add_slack_import_constraints_to_model(self, model: EchoConcreteModel) -> None:
        """Adds import capacity constraint with slack rules"""

        # Add export capacity slack constraint
        def import_cap_rule_slack(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            return (
                getattr(model, self.port_name)[p, t] + getattr(model, self.import_slack)[p, t]
                <= getattr(model, self.import_con_val)[p, t]
            )

        con_name = "import_con_" + self.port_name
        setattr(
            model,
            self.import_slack,
            en.Var(
                model.Expansion,
                model.Time,
                initialize=0,
                domain=en.NonPositiveReals,
            ),
        )
        setattr(
            model,
            con_name,
            en.Constraint(model.Expansion, model.Time, rule=import_cap_rule_slack),
        )

        # Add import capacity slack max constraint
        def import_cap_slack_max_rule(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            return getattr(model, self.import_slack)[p, t] >= getattr(model, self.import_slack_max)

        con_name = "import_con_max_" + self.port_name
        setattr(
            model,
            self.import_slack_max,
            en.Var(initialize=0, domain=en.NonPositiveReals),
        )
        setattr(
            model,
            con_name,
            en.Constraint(model.Expansion, model.Time, rule=import_cap_slack_max_rule),
        )

    def _add_export_constraints_to_model(self, model: EchoConcreteModel) -> None:
        """Add export constraints to the model."""

        # Add export constraint parameter
        time_periods = len(model.Time)
        exp_periods = len(model.Expansion)

        # Generate an array of constraints (ie indexed by time and expansion period)
        export_constraint_dict = generate_array_constraint(self.export_constraint_value, time_periods, exp_periods)
        setattr(
            model,
            self.export_con_val,
            en.Param(
                model.Expansion,
                model.Time,
                initialize=export_constraint_dict,
                domain=en.NonPositiveReals,
            ),
        )

        if self.slack:
            self._add_slack_export_constraints_to_model(model=model)
        else:
            set_var_bounds_from_dict(model=model, var_name=self.port_name, ub=None, lb=export_constraint_dict)

    def _add_slack_export_constraints_to_model(self, model: EchoConcreteModel) -> None:
        """Adds import capacity constraint with slack rules"""

        # Add export capacity slack constraint
        def export_cap_rule_slack(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            return (
                getattr(model, self.port_name)[p, t] + getattr(model, self.export_slack)[p, t]
                >= getattr(model, self.export_con_val)[p, t]
            )

        con_name = "export_con_" + self.port_name
        setattr(
            model,
            self.export_slack,
            en.Var(
                model.Expansion,
                model.Time,
                initialize=0,
                domain=en.NonNegativeReals,
            ),
        )
        setattr(
            model,
            con_name,
            en.Constraint(model.Expansion, model.Time, rule=export_cap_rule_slack),
        )

        def export_cap_slack_max_rule(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            """Add export capacity slack max constraint"""
            return getattr(model, self.export_slack)[p, t] <= getattr(model, self.export_slack_max)

        con_name = "export_con_max_" + self.port_name
        setattr(
            model,
            self.export_slack_max,
            en.Var(initialize=0, domain=en.NonNegativeReals),
        )
        setattr(
            model,
            con_name,
            en.Constraint(model.Expansion, model.Time, rule=export_cap_slack_max_rule),
        )

    def _determine_initial_value(
        self,
        time_periods: int,
        expansion_periods: int,
        profile: pd.DataFrame | None,
    ) -> InitialValue:

        initial_value_scaling = self.initial_value_scaling or 1

        if self.initial_value_ref is not None:
            initial_val = to_initial_values(
                profile,
                self.initial_value_ref,
                time_periods,
                expansion_periods,
                scaling=initial_value_scaling,
            )
        else:
            # TODO: add scaling for explicit initial value
            initial_val = self.initial_value

        return initial_val

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame | None) -> None:
        """Creates pyomo vars, params, and constraints for the port."""
        initial_value = self._determine_initial_value(
            time_periods=len(model.Time),
            expansion_periods=len(model.Expansion),
            profile=profile,
        )

        domain = domain_from_flow(self.flows)

        # Flow is always represented with a pyomo variable.
        # This gives us flexibility for converting between a variable and parameter with fix/unfix
        self._add_flow_variable_to_model(model=model, initial_value=initial_value, domain=domain)

        # Convert flow variable to parameter if requested.
        if self.flow_type is OptimisationType.Parameter:
            getattr(model, self.port_name).fix()  # Fix the variable - equivalent to setting it as an 'en.Param'

        if self.import_constraint is FlowConstraint.Fixed:  # only apply import/export constraints to variables
            self._add_import_constraints_to_model(model=model)

        if self.import_constraint in [FlowConstraint.Series, FlowConstraint.InRange]:
            raise NotImplementedError("Series and InRange import flow constraints are not implemented")

        if self.export_constraint is FlowConstraint.Fixed:  # only apply these constraints to variables
            self._add_export_constraints_to_model(model=model)

        if self.export_constraint in [FlowConstraint.Series, FlowConstraint.InRange]:
            raise NotImplementedError("Series and InRange export flow constraints are not implemented")

        if self.active_periods is not None:
            self._add_active_period_constraints_to_model(model=model)

    def constrain_pos_neg(self, model: EchoConcreteModel) -> None:
        """Applies a mixed integer constraint that splits a port var into positive and negative components"""
        if hasattr(model, self.pos) is False:
            setattr(
                model,
                self.pos,
                en.Var(
                    model.Expansion,
                    model.Time,
                    initialize=0,
                    domain=en.NonNegativeReals,
                ),
            )
            setattr(
                model,
                self.neg,
                en.Var(
                    model.Expansion,
                    model.Time,
                    initialize=0,
                    domain=en.NonPositiveReals,
                ),
            )
            setattr(
                model,
                self.is_pos,
                en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary),
            )

            con_rule = self.factory_pos_neg_flows(self.port_name, self.pos, self.neg)
            con_name = positive_variable_component + negative_variable_component + self.port_name
            setattr(
                model,
                con_name,
                en.Constraint(model.Expansion, model.Time, rule=con_rule),
            )

            def only_pos_or_neg_one(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
                return getattr(model, self.pos)[p, t] <= getattr(model, self.is_pos)[p, t] * model.big_m

            setattr(
                model,
                f"pos_neg_con1_{self.port_name}",
                en.Constraint(model.Expansion, model.Time, rule=only_pos_or_neg_one),
            )

            def only_pos_or_neg_two(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
                return getattr(model, self.neg)[p, t] >= (getattr(model, self.is_pos)[p, t] - 1) * model.big_m

            setattr(
                model,
                f"pos_neg_con2_{self.port_name}",
                en.Constraint(model.Expansion, model.Time, rule=only_pos_or_neg_two),
            )

    @staticmethod
    def factory_pos_neg_flows(var_name: str, pos_name: str, neg_name: str) -> Callable:
        def constraint(model: EchoConcreteModel, expansion_interval: int, time_interval: int) -> EqualityExpression:
            return getattr(model, var_name)[expansion_interval, time_interval] == (
                getattr(model, pos_name)[expansion_interval, time_interval]
                + getattr(model, neg_name)[expansion_interval, time_interval]
            )

        return constraint

    def set_initial_value(self, initial_value: dict) -> None:
        """Sets initial port value which will be used to initialise the pyomo var/param

        Args:
            initial_value: dict of initial values

        Returns:
            None
        """

        self.initial_value = initial_value

    def set_initial_value_from_timeseriesdata(self, time_series_data: TimeSeriesData) -> None:
        self.set_initial_value(expand_as_dict(time_series_data))

    def set_initial_value_from_array(
        self,
        array: list[float] | np.ndarray,
        expansion_periods: int = 1,
        time_periods: int | None = None,
    ) -> None:
        """Sets initial port value which is used to initialise the pyomo var/param

        Args:
            array: array, list of initial values. Should have either: length = time_periods,
                or length = time_periods*expansion_periods
            time_periods: int, optional number of time periods. If=None, assume that time_periods = len(array)
            expansion_periods: number of expansion periods
        """
        if time_periods is None:
            time_periods = len(array)

        time_series_data = TimeSeriesData(
            value=array,
            num_time_intervals=time_periods,
            num_expansion_intervals=expansion_periods,
        )
        self.set_initial_value_from_timeseriesdata(time_series_data=time_series_data)

    def set_active_periods_from_array(
        self, array: list[bool] | list[int], expansion_periods: int = 1, time_periods: int | None = None
    ) -> None:
        """Sets port active periods

        Args:
            array: array, list of active periods as bool values
            expansion_periods: number of expansion periods (int)
        """

        if time_periods is None:
            time_periods = len(array)

        # We need an array which only contains 0 or 1 representing inactive (flow fixed to 0)
        # or active (flow can be optimised)
        # Convert bools to ints
        active_periods_as_ints = [int(i) for i in array]
        set_of_active_periods = set(active_periods_as_ints)

        if set_of_active_periods not in [{0}, {1}, {0, 1}]:
            raise ValueError("Active periods must be a list of booleans or a list only containing 0's or 1's")

        time_series_data = TimeSeriesData(
            value=active_periods_as_ints,
            num_time_intervals=time_periods,
            num_expansion_intervals=expansion_periods,
        )
        self.active_periods = expand_as_dict(time_series_data)

    def add_objective(self, model: EchoConcreteModel) -> None:
        """Populates the port attribute 'objectives' with any pyomo expressions that are needed
        Args:
            model: pyomo concrete model
        """
        total = 0
        if self.slack is True:
            if hasattr(model, self.import_slack) is True:
                total += -1 * getattr(model, self.import_slack_max) * model.big_m
                total += (
                    -1
                    * sum(getattr(model, self.import_slack)[p, t] for p in model.Expansion for t in model.Time)
                    * model.big_m
                    * 0.1
                )
            if hasattr(model, self.export_slack) is True:
                total += getattr(model, self.export_slack_max) * model.big_m
                total += (
                    sum(getattr(model, self.export_slack)[p, t] for p in model.Expansion for t in model.Time)
                    * model.big_m
                    * 0.1
                )

        self.objective += total
