import pandas as pd
import pyomo.environ as en
from pydantic import PositiveFloat, validator
from pyomo.core.expr import EqualityExpression

from echo.configuration import FlowConstraint, Units
from echo.models.agnostic import FlexPort, FlexSink
from echo.models.base import Node
from echo.models.scenario import EchoConcreteModel
from echo.utils import (
    TimeSeriesData,
    expand_as_dict,
    to_initial_values,
)
from echo.validators import non_negative_cop_check


class SimpleChiller(Node):
    """A simple chiller model that uses predefined COP (coefficient of performance) values for cooling.

    Simple Chiller has one input electrical port, and one cooling_output (thermal Sink) thermal port.

    The conversion of input electrical energy to cooling output depends on provided coefficients of
    performance (COP) time series data.
    """

    max_cooling_capacity: PositiveFloat | None = None  # Max cooling load that can be serviced in KWT
    # (if None, bounded by big_m value)
    cooling_cop_time_series: dict | None  # Formatted dict of cooling COPs (coefficients of performance)
    cooling_cop_time_series_ref: str | None
    cooling_cop_constant: PositiveFloat | None = 1  # Constant COP value to use across all optimisation intervals

    cooling_cop_check = validator("cooling_cop_time_series", allow_reuse=True)(non_negative_cop_check)

    electrical_input_port_ref: str = "input"
    thermal_output_port_ref: str = "output"

    def __init__(self, **data) -> None:
        super().__init__(**data)
        # Constraint flow of the thermal port
        if self.max_cooling_capacity:
            thermal_import_constraint = FlowConstraint.Fixed
            thermal_import_constraint_value = self.max_cooling_capacity
        else:
            thermal_import_constraint = FlowConstraint.NA
            thermal_import_constraint_value = None

        # Create input and output ports
        # Simple Chiller has electrical input port
        self.ports[self.electrical_input_port_ref] = FlexSink(units=Units.KW)

        # Simple Chiller has cooling output port (thermal sink)
        self.ports[self.thermal_output_port_ref] = FlexSink(
            units=Units.KWT,
            import_constraint=thermal_import_constraint,
            import_constraint_value=thermal_import_constraint_value,
        )

    def set_ports(self, electrical_input_port: FlexSink, thermal_output_port: FlexPort) -> None:
        # Discard existing ports
        self.ports.clear()

        # Add the new ports
        self.electrical_input_port_ref = electrical_input_port.port_name
        self.thermal_output_port_ref = thermal_output_port.port_name
        self.ports[self.electrical_input_port_ref] = electrical_input_port
        self.ports[self.thermal_output_port_ref] = thermal_output_port

    def update(self, cooling_cop_time_series: dict[float, float]) -> None:
        self.cooling_cop_time_series = cooling_cop_time_series

    @property
    def cooling_cop(self) -> str:
        return "cooling_cop_" + self.node_name

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        # Load coefficient of performance values from profile (if provided by reference)
        self._load_cop_values_from_profile(model, profile)
        super().add_node_to_model(model, profile)
        setattr(
            model,
            self.cooling_cop,
            en.Param(model.Expansion, model.Time, initialize=self.cooling_cop_time_series, domain=en.NonNegativeReals),
        )

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        # Get variable names for heating and cooling output depending on thermal ports configuration
        self._apply_node_transformation_constraints(model)

    def _apply_node_transformation_constraints(self, model: EchoConcreteModel) -> None:
        cooling_out = getattr(
            model, self.ports[self.thermal_output_port_ref].port_name
        )  # cooling delivered at thermal port
        cooling_cop = getattr(model, self.cooling_cop)

        def cooling_output_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            """Thermal port flow values are positive in cooling mode.
            cooling_out = power_input * cooling cop
            """

            return (
                cooling_out[p, t]
                == getattr(model, self.ports[self.electrical_input_port_ref].port_name)[p, t] * cooling_cop[p, t]
            )

        setattr(
            model, "cool_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=cooling_output_rule)
        )

    def _load_cop_values_from_profile(self, model: EchoConcreteModel, profile_df: pd.DataFrame) -> None:
        """When coefficient of performance timeseries is set by str reference, load values from profile."""

        if self.cooling_cop_time_series_ref:
            if self.cooling_cop_time_series_ref not in profile_df.columns:
                raise ValueError(
                    f"Could not find reference column name {self.cooling_cop_time_series_ref} in the profile."
                )
            self.cooling_cop_time_series = to_initial_values(
                profile_df,
                key=self.cooling_cop_time_series_ref,
                time_periods=len(model.Time),
                expansion_periods=len(model.Expansion),
            )
        self._set_constant_cop_values(model)

    def _set_constant_cop_values(self, model: EchoConcreteModel) -> None:
        """If cooling_cop_time_series dictionary is not defined otherwise, use constant cop value"""
        if not self.cooling_cop_time_series:
            self.cooling_cop_time_series = expand_as_dict(
                TimeSeriesData(
                    value=self.cooling_cop_constant,
                    num_time_intervals=len(model.Time),
                    num_expansion_intervals=len(model.Expansion),
                )
            )
