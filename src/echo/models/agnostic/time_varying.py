import pandas as pd
import pyomo.environ as en
from pydantic import root_validator

from echo.exceptions import validate
from echo.models.agnostic.input_output import InputOutputNode
from echo.models.scenario import EchoConcreteModel
from echo.utils import (
    populate_values_across_time_and_expansion_indices,
    set_float_var_bounds,
)
from echo.validators import (
    set_bounds_from_piecewise_points,
    validate_piecewise_arrays,
)


class TimeVaryingPiecewiseIONode(InputOutputNode):
    """A Node with an input and output and time varying piecewise relationship between input and output.

    The relationship between input and output is defined at each time interval by an array
    of input-->output point pairs, which are used to construct a piecewise constraint.
    Attributes input_port_unit and output_port_unit define node's commodity.
    """

    input_points: dict | None  # dict where the keys are planning-time period tuple, and value is input pt array
    output_points: dict | None  # dict where the keys are planning-time period tuple, and value is output pt array
    input_points_ref: str | None  # Ref to profile dataframe column with input points array to be used across all times
    output_points_ref: str | None  # Ref to profile dataframe column with input points array to be used across all times

    piecewise_check = root_validator(allow_reuse=True)(validate_piecewise_arrays)  # validate input/output points
    populate_bounds = root_validator(allow_reuse=True)(
        set_bounds_from_piecewise_points
    )  # set attributes max_output,  min_output, max_input, min_input from input points/output points

    def verify_points_values(self) -> None:
        validate(self.input_points is not None, "No input points defined")
        validate(self.output_points is not None, "No output points defined")
        # Validate that dictionary keys match and length of each value array are the same
        for k in self.input_points.keys():
            validate(k in self.output_points.keys(), f"Key {k} not found in output_points dictionary")
            validate(
                len(self.input_points[k]) == len(self.output_points[k]),
                "Number of break points in "
                "input_points output_points must match."
                f"Different length value arrays for key {k}",
            )

    def load_input_output_values_from_profile(self, model: EchoConcreteModel, profile_df: pd.DataFrame) -> None:
        """If input/output point string references are provided, load values from profile.

        input_points_ref/output_points_ref will override input_points/output_points values provided
        in the instance's attributes (if any) with values from profile dataframe.
        """
        if self.input_points_ref:
            """Load input points array from profile dataframe and set the same array across all time points"""
            if self.input_points_ref not in profile_df.columns:
                raise ValueError(f"Could not find reference column name {self.input_points_ref} in the profile.")
            input_points_array = profile_df[self.input_points_ref].to_list()
            self.add_constant_input_points(input_points_array, len(model.Time), len(model.Expansion))

        if self.output_points_ref:
            """Load input points array from profile dataframe and set the same array across all time points"""
            if self.output_points_ref and self.output_points_ref not in profile_df.columns:
                raise ValueError(f"Could not find reference column name {self.output_points_ref} in the profile.")
            output_points_array = profile_df[self.output_points_ref].to_list()
            self.add_constant_output_points(output_points_array, len(model.Time), len(model.Expansion))

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        self.load_input_output_values_from_profile(model, profile)
        super().add_node_to_model(model, profile)
        # Bound input and output port variables, otherwise piecewise constraint will fail
        self.verify_points_values()
        set_float_var_bounds(
            model=model, var_name=self.ports[self.output_port_ref].port_name, ub=self.max_output, lb=self.min_output
        )
        set_float_var_bounds(
            model=model, var_name=self.ports[self.input_port_ref].port_name, ub=self.max_input, lb=self.min_input
        )

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        xvar = getattr(model, self.ports[self.input_port_ref].port_name)
        yvar = getattr(model, self.ports[self.output_port_ref].port_name)
        xdata = self.input_points
        ydata = self.output_points
        con_name = "piecewise_con_" + self.node_name
        setattr(
            model,
            con_name,
            en.Piecewise(
                model.Expansion,
                model.Time,
                yvar,
                xvar,
                pw_pts=xdata,
                pw_constr_type="EQ",
                f_rule=ydata,
                pw_repn="SOS2",
                warn_domain_coverage=False,
            ),
        )

    def add_constant_input_points(
        self,
        input_points: float | int | list,
        time_periods: int,
        expansion_periods: int = 1,
    ) -> None:
        """Tiles constant input points array across time and expansion periods"""
        self.input_points = populate_values_across_time_and_expansion_indices(
            input_points, time_periods, expansion_periods
        )

    def add_constant_output_points(
        self,
        output_points: float | int | list,
        time_periods: int,
        expansion_periods: int = 1,
    ) -> None:
        """Tiles constant output points array across time and expansion periods."""
        self.output_points = populate_values_across_time_and_expansion_indices(
            output_points, time_periods, expansion_periods
        )
