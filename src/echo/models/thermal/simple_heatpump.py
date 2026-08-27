import pandas as pd
import pyomo.environ as en
from pydantic import PositiveFloat, validator
from pyomo.core.expr import EqualityExpression, InequalityExpression

from echo.configuration import FlowConstraint, Units
from echo.models.agnostic import FlexPort, FlexSink
from echo.models.base import Node
from echo.models.scenario import EchoConcreteModel
from echo.utils import (
    TimeSeriesData,
    expand_as_dict,
    set_float_var_bounds,
    to_initial_values,
)
from echo.validators import non_negative_cop_check


class SimpleHeatPump(Node):
    """A simple heat pump model that uses predefined COP (coefficient of performance) values for heating and cooling.

    SimpleHeatPump has one input electrical port, and one bidirectional thermal port. In this configuration the heatpump
    can do heating or cooling, but not both simultaneously.

    The conversion of input electrical energy to heating or cooling output depends on provided coefficients of
    performance (COP) time series data.
    """

    max_cooling_capacity: PositiveFloat = (
        None  # Max cooling load that can be serviced in KWT (if None, bounded by big_m value)
    )
    max_heating_capacity: PositiveFloat = (
        None  # Max heating load that can be serviced in KWT (if None, bounded by big_m value)
    )
    heating_cop_time_series: dict | None  # Formatted dict of heating COPs (coefficients of performance)
    # per time period
    cooling_cop_time_series: dict | None  # Formatted dict of cooling COPs (coefficients of performance)
    # per time period
    heating_cop_time_series_ref: str | None
    cooling_cop_time_series_ref: str | None

    cooling_cop_constant: PositiveFloat | None = 1  # Constant COP value to use across all optimisation intervals
    heating_cop_constant: PositiveFloat | None = 1  # Constant COP value to use across all optimisation intervals

    heating_cop_check = validator("heating_cop_time_series", allow_reuse=True)(non_negative_cop_check)
    cooling_cop_check = validator("cooling_cop_time_series", allow_reuse=True)(non_negative_cop_check)

    electrical_input_port_ref: str = "input"
    thermal_output_port_ref: str = "output"

    def __init__(self, **data) -> None:
        super().__init__(**data)
        self.create_ports()

    def update(self, heating_cop_time_series: dict[float, float], cooling_cop_time_series: dict[float, float]) -> None:
        self.heating_cop_time_series = heating_cop_time_series
        self.cooling_cop_time_series = cooling_cop_time_series

    # Naming variables
    @property
    def heating_cop(self) -> str:
        return "heating_cop_" + self.node_name

    @property
    def cooling_cop(self) -> str:
        return "cooling_cop_" + self.node_name

    @property
    def power_to_heat(self) -> str:
        return "power_to_heat_" + self.node_name

    @property
    def power_to_cool(self) -> str:
        return "power_to_cool_" + self.node_name

    def create_ports(self) -> None:
        # Constraint import flow of the thermal port
        if self.max_cooling_capacity:
            thermal_import_constraint = FlowConstraint.Fixed
            thermal_import_constraint_value = self.max_cooling_capacity
        else:
            thermal_import_constraint = FlowConstraint.NA
            thermal_import_constraint_value = None
        # Constraint export flow of the thermal port
        if self.max_heating_capacity:
            thermal_export_constraint = FlowConstraint.Fixed
            thermal_export_constraint_value = -self.max_heating_capacity
        else:
            thermal_export_constraint = FlowConstraint.NA
            thermal_export_constraint_value = None

        # Create input and output ports
        # Heat pump has electrical input port
        self.ports[self.electrical_input_port_ref] = FlexSink(units=Units.KW)
        # Heat pump has one thermal output port
        # Thermal 'output' port is a two-way port: heating output = thermal source, cooling output = thermal sink"
        self.ports[self.thermal_output_port_ref] = FlexPort(
            units=Units.KWT,
            import_constraint=thermal_import_constraint,
            import_constraint_value=thermal_import_constraint_value,
            export_constraint=thermal_export_constraint,
            export_constraint_value=thermal_export_constraint_value,
        )

    def set_ports(self, electrical_input_port: FlexSink, thermal_output_port: FlexPort) -> None:
        # Discard existing ports
        self.ports.clear()

        # Add the new ports
        self.electrical_input_port_ref = electrical_input_port.port_name
        self.thermal_output_port_ref = thermal_output_port.port_name
        self.ports[self.electrical_input_port_ref] = electrical_input_port
        self.ports[self.thermal_output_port_ref] = thermal_output_port

    def _set_ports_var_bounds(self, model: EchoConcreteModel) -> None:
        """Set cooling and heating port flow bounds based on the max heating and cooling capacity attribute if given.

        Split output port into non-positive and non-negative components.
        """
        # Split output port into +ve and -ve components. +ve component will be cooling,
        # -ve component will be heating
        self.ports[self.thermal_output_port_ref].constrain_pos_neg(model)
        lower_bound = self.max_heating_capacity or model.big_m
        upper_bound = self.max_cooling_capacity or model.big_m
        set_float_var_bounds(
            model,
            self.ports[self.thermal_output_port_ref].port_name,
            ub=upper_bound,
            lb=-lower_bound,
        )

    def _set_helper_variables(self, model: EchoConcreteModel) -> None:
        """Create internal variables representing amount of electrical power used to produce heating or cooling
        at each interval. Both variables are non-negative, this is not the same as thermal port flow value.
        Intermediate helper variables."""
        setattr(
            model, self.power_to_heat, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals)
        )
        setattr(
            model, self.power_to_cool, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals)
        )

        # Create params for heating and cooling coefficients of performance
        setattr(
            model,
            self.heating_cop,
            en.Param(model.Expansion, model.Time, initialize=self.heating_cop_time_series, domain=en.NonNegativeReals),
        )
        setattr(
            model,
            self.cooling_cop,
            en.Param(model.Expansion, model.Time, initialize=self.cooling_cop_time_series, domain=en.NonNegativeReals),
        )

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        # Load coefficient of performance values from profile (if be set ref)
        self._load_cop_values_from_profile(model, profile)
        super().add_node_to_model(model, profile)
        self._set_ports_var_bounds(model)
        self._set_helper_variables(model)

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        # Get variable names for heating and cooling output depending on thermal ports configuration
        heating_out_var = self.ports[self.thermal_output_port_ref].neg
        cooling_out_var = self.ports[self.thermal_output_port_ref].pos
        is_cooling_var = self.ports[self.thermal_output_port_ref].is_pos
        # Apply heating_cooling constraints and transformation constraint
        self._apply_only_heat_or_cool_constraints(model, binary_var_name=is_cooling_var)
        self._apply_node_transformation_constraints(
            model, heating_out_var=heating_out_var, cooling_out_var=cooling_out_var
        )

    def _load_cop_values_from_profile(self, model: EchoConcreteModel, profile_df: pd.DataFrame) -> None:
        """When coefficient of performance timeseries is set by str reference, load values from profile."""
        if self.cooling_cop_time_series_ref:
            if self.cooling_cop_time_series_ref not in profile_df.columns:
                raise ValueError(
                    f"Could not find reference column name {self.cooling_cop_time_series_ref} in the profile."
                )
            else:
                self.cooling_cop_time_series = to_initial_values(
                    profile_df,
                    key=self.cooling_cop_time_series_ref,
                    time_periods=len(model.Time),
                    expansion_periods=len(model.Expansion),
                )

        if self.heating_cop_time_series_ref:
            if self.heating_cop_time_series_ref not in profile_df.columns:
                raise ValueError(
                    f"Could not find reference column name {self.heating_cop_time_series_ref} in the profile."
                )
            else:
                self.heating_cop_time_series = to_initial_values(
                    profile_df,
                    key=self.heating_cop_time_series_ref,
                    time_periods=len(model.Time),
                    expansion_periods=len(model.Expansion),
                )

        self._set_constant_cop_values(model)

    def _set_constant_cop_values(self, model: EchoConcreteModel) -> None:
        """If heating_cop_time_series and cooling_cop_time_series dictionary is not defined otherwise,
        use constant cop values.
        """
        if not self.heating_cop_time_series:
            self.heating_cop_time_series = expand_as_dict(
                TimeSeriesData(
                    value=self.heating_cop_constant,
                    num_time_intervals=len(model.Time),
                    num_expansion_intervals=len(model.Expansion),
                )
            )
        if not self.cooling_cop_time_series:
            self.cooling_cop_time_series = expand_as_dict(
                TimeSeriesData(
                    value=self.cooling_cop_constant,
                    num_time_intervals=len(model.Time),
                    num_expansion_intervals=len(model.Expansion),
                )
            )

    def _apply_only_heat_or_cool_constraints(self, model: EchoConcreteModel, binary_var_name: str) -> None:
        is_cooling = getattr(model, binary_var_name)  # binary var for whether we are cooling
        power_in = getattr(model, self.ports[self.electrical_input_port_ref].port_name)  # input electrical power

        def only_heat_or_cool1(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            """Constraint power_to_heat variable.
            power_to_heat=0 when is_cooling=1. power_to_heat is positive real =< big_m value when is_cooling=0"""
            return getattr(model, self.power_to_heat)[p, t] <= (1 - is_cooling[p, t]) * model.big_m

        setattr(
            model,
            "only_heat_or_cool1_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=only_heat_or_cool1),
        )

        def only_heat_or_cool2(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            """Constraint power_to_cool variable.
            power_to_cool=0 when is_cooling=0. power_to_cool is positive real =< big_m value when is_cooling=1"""
            return getattr(model, self.power_to_cool)[p, t] <= is_cooling[p, t] * model.big_m

        setattr(
            model,
            "only_heat_or_cool2_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=only_heat_or_cool2),
        )

        def sum_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            """Electrical power input used for heating and for cooling must sum to total electrical power input"""
            return power_in[p, t] == getattr(model, self.power_to_heat)[p, t] + getattr(model, self.power_to_cool)[p, t]

        setattr(model, "sum_heat_cool_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=sum_rule))

    def _apply_node_transformation_constraints(
        self, model: EchoConcreteModel, heating_out_var: str, cooling_out_var: str
    ) -> None:
        heating_out = getattr(model, heating_out_var)  # heating delivered at thermal port (heat exported)
        cooling_out = getattr(model, cooling_out_var)  # cooling delivered at thermal port (heat absorbed)
        heating_cop = getattr(model, self.heating_cop)
        cooling_cop = getattr(model, self.cooling_cop)

        def heating_output_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            """When heatpump used for heating, thermal port is exporting energy, thus -1 scaling.

            Thermal port flow values are negative in heating mode.
            heating_out = power_to_heat * heating cop * -1.
            """
            return heating_out[p, t] == getattr(model, self.power_to_heat)[p, t] * heating_cop[p, t] * -1

        def cooling_output_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            """When heatpump used for cooling, thermal port is importing/absorbing.

            Thermal port flow values are positive in cooling mode.
            cooling_out = power_to_cool * cooling cop
            """

            return cooling_out[p, t] == getattr(model, self.power_to_cool)[p, t] * cooling_cop[p, t]

        setattr(
            model, "heat_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=heating_output_rule)
        )
        setattr(
            model, "cool_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=cooling_output_rule)
        )
