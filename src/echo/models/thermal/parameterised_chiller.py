import pandas as pd
import pyomo.environ as en
from pydantic import PositiveFloat, root_validator
from pyomo.core.expr import EqualityExpression
from scipy import interpolate

from echo.configuration import Units
from echo.models.agnostic import FlexPort, FlexSink, FlexSource, TimeVaryingPiecewiseIONode
from echo.models.scenario import EchoConcreteModel
from echo.utils import (
    TimeSeriesData,
    clamp,
    expand_as_dict,
    to_initial_values,
)
from echo.validators import validate_partial_load_cop, validate_temperature_dependent_cop


class ParameterisedChiller(TimeVaryingPiecewiseIONode):
    """A chiller has one electrical input port and one cooling output (thermal sink) port.

    ParameterisedChiller is an input/output piecewise node, with a single set of input/output breakpoints representing
    chiller COP (Coefficient Of Performance = Output/Input=Cooling_delivered/Electricity_consumed) used
    for all time periods.
    """

    nominal_cop: PositiveFloat  # Nominal coefficient of performance COP = output/input
    max_cooling_capacity: PositiveFloat  # Maximum cooling output in KWT (1RT ~ 3.5KWT)
    partial_load_cop: dict = {
        0: 0,
        0.25: 0.8,
        0.5: 0.9,
        0.75: 1,
        1: 0.85,
    }  # Scaling factor for the nominal COP (coefficient of performance) depending on the partial load value
    temperature_dependent_cop: dict = {
        0: 0.7,
        10: 1,
        20: 0.5,
        30: 0.35,
        45: 0.2,
    }  # Scaling factor for the nominal COP (coefficient of performance) depending on
    # the ambient/condenser temperature value
    ambient_temperature_dict: dict = (
        None  # Condenser side temperature ambient air temperature or condenser
        # water temperature for water cooled chiller
    )
    ambient_temperature_ref: str = None  # Ambient temperature array passed by string reference
    constant_ambient_temperature: float = 10  # Constant value for ambient temperature in degrees C,
    # when no array data is provided
    input_port_unit: Units = Units.KW  # Input port units
    output_port_unit: Units = Units.KWT  # Output port units TODO: implementation for output units JPS
    heat_rejection_port: bool = False  # If True, add heat rejection port
    heat_rejection_coefficient: PositiveFloat = 1  # Heat rejection coefficient cooling_delivered/heat_rejected

    partial_load_cop_check = root_validator(allow_reuse=True)(validate_partial_load_cop)
    temperature_cop_check = root_validator(allow_reuse=True)(validate_temperature_dependent_cop)

    # The input_port_ref and output_port_ref are defined on the parent class (TimeVaryingPiecewiseIONode)
    heat_rejection_port_ref: str = "heat_rejection"

    @property
    def temperature_cop_param(self) -> str:
        return f"temperature_cop_factor_{self.node_name}"

    @property
    def electrical_input_port_ref(self) -> str:
        return self.input_port_ref

    @property
    def thermal_output_port_ref(self) -> str:
        return self.output_port_ref

    def __init__(self, **data) -> None:
        super().__init__(**data)
        # A chiller has one electrical input port and one cooling output (thermal sink) port
        self.ports[self.input_port_ref] = FlexSink(units=self.input_port_unit)
        self.ports[self.output_port_ref] = FlexSink(units=self.output_port_unit)
        if self.heat_rejection_port:
            self.ports[self.heat_rejection_port_ref] = FlexSource(units=self.output_port_unit)

    def update(self, ambient_temperature_dict: dict[float, float]) -> None:
        self.ambient_temperature_dict = ambient_temperature_dict

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        self._load_temperature_values_from_profile(model, profile)
        self._define_temperature_dependent_cop_coefficient(model)
        self._set_input_points(model)
        self._set_output_points(model)
        super().add_node_to_model(model, profile)
        if self.heat_rejection_port_ref in self.ports:
            self._add_heat_rejection_constraint(model)

    def set_ports(
        self,
        electrical_input_port: FlexSink,
        cooling_output_port: FlexPort,
        heat_rejection_port: FlexPort | None = None,
    ) -> None:
        # Discard existing ports
        self.ports.clear()

        # Update port references
        self.input_port_ref = electrical_input_port.port_name
        self.output_port_ref = cooling_output_port.port_name

        # Add the new ports
        self.ports[self.input_port_ref] = electrical_input_port
        self.ports[self.output_port_ref] = cooling_output_port

        # Handle heat intake rejection
        self.heat_rejection_port = False  # clear if already set
        if heat_rejection_port:
            self.heat_rejection_port = True
            self.heat_rejection_port_ref = heat_rejection_port.port_name
            self.ports[self.heat_rejection_port_ref] = heat_rejection_port

    def _define_temperature_dependent_cop_coefficient(self, model: EchoConcreteModel) -> None:
        """Get COP (coefficient of performance) scaling factor for each interval.

        Calculate value of the temperature_cop_factor parameter using numpy linear interpolation function.
        """

        temperature_points = list(self.temperature_dependent_cop.keys())
        cop_points = list(self.temperature_dependent_cop.values())

        if self.ambient_temperature_dict:
            temperature_dict = self.ambient_temperature_dict
        else:
            # Set default amb temp value to 10 >> no change to nominal COP
            temperature_dict = expand_as_dict(
                TimeSeriesData(
                    value=self.constant_ambient_temperature,
                    num_time_intervals=len(model.Time),
                    num_expansion_intervals=len(model.Expansion),
                )
            )

        # Use numpy linear interpolation function to get temperature related cop (coefficient of performance)
        # scaling factor based on the temperature values in the temperature dictionary
        min_temp = min(self.temperature_dependent_cop.keys())
        max_temp = max(self.temperature_dependent_cop.keys())
        clamped_temp_values = [clamp(v, min_temp, max_temp) for v in temperature_dict.values()]

        cop_scaling_interpolated = interpolate.interp1d(temperature_points, cop_points, assume_sorted=False)(
            list(clamped_temp_values)
        ).round(2)
        temperature_cop_dict = {k: v for k, v in zip(temperature_dict.keys(), cop_scaling_interpolated, strict=True)}
        # Create a parameter holding ambient/condenser temperature dictionary
        # (defaulting to self.constant_ambient_temperature)
        setattr(
            model,
            self.temperature_cop_param,
            en.Param(model.Expansion, model.Time, initialize=temperature_cop_dict, domain=en.Reals),
        )

    def _set_input_points(self, model: EchoConcreteModel) -> None:
        """Input breakpoints are input electrical power values calculated as
        cooling_output/(COP_nominal*partial_load_correction) and scaled by 1/temperature_cop_param value"""

        # get parameter holding temperature dependent COP (coefficient of performance) factor
        temperature_cop_param = getattr(model, self.temperature_cop_param)

        def input_point(k: float, v: float) -> float:
            if v == 0:
                return 0
            else:
                return k * self.max_cooling_capacity / (v * self.nominal_cop)

        self.input_points = {
            (p, t): [input_point(k, v) / temperature_cop_param[p, t] for k, v in self.partial_load_cop.items()]
            for p in range(len(model.Expansion))
            for t in range(len(model.Time))
        }

    def _set_output_points(self, model: EchoConcreteModel) -> None:
        """Output breakpoints are partial cooling load values (% of max capacity)"""
        self.output_points = {
            (p, t): [k * self.max_cooling_capacity for k in self.partial_load_cop.keys()]
            for p in range(len(model.Expansion))
            for t in range(len(model.Time))
        }

    def _add_heat_rejection_constraint(self, model: EchoConcreteModel) -> None:
        """Get variables representing port flow values for cooling output (heat in) and
        rejected heat flow, set the constraint."""
        heat_in = getattr(model, self.ports[self.output_port_ref].port_name)
        heat_reject = getattr(model, self.ports[self.heat_rejection_port_ref].port_name)

        def heat_reject_constraint(model: EchoConcreteModel, p: None, t: None) -> EqualityExpression:
            """Amount of rejected heat at each interval equals amount of cooling delivered (heat in) multiplied by
            heat rejection coefficient
            """
            return heat_reject[p, t] == -heat_in[p, t] * self.heat_rejection_coefficient

        setattr(
            model,
            "heat_rejection_constraint_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=heat_reject_constraint),
        )

    def _load_temperature_values_from_profile(self, model: EchoConcreteModel, profile_df: pd.DataFrame) -> None:
        """When ambient temperature is set by str reference, load values from profile."""
        if self.ambient_temperature_ref:
            if self.ambient_temperature_ref and self.ambient_temperature_ref not in profile_df.columns:
                raise ValueError(f"Could not find reference column name {self.ambient_temperature_ref} in the profile.")
            else:
                self.ambient_temperature_dict = to_initial_values(
                    profile_df,
                    key=self.ambient_temperature_ref,
                    time_periods=len(model.Time),
                    expansion_periods=len(model.Expansion),
                )
