from typing import Optional

import numpy as np
import pandas as pd
import pyomo.environ as en
from pydantic import NonNegativeFloat, PositiveFloat, root_validator, validator

from echo.configuration import FlowConstraint, Units
from echo.models.agnostic import FlexPort, FlexSink, FlexSource, TimeVaryingPiecewiseIONode
from echo.models.base import Node
from echo.models.scenario import EchoConcreteModel
from echo.utils import (
    TimeSeriesData,
    clamp,
    expand_as_dict,
    set_float_var_bounds,
    set_var_bounds_from_dict,
    to_initial_values,
)
from echo.validators import non_negative_cop_check, validate_partial_load_cop, validate_temperature_dependent_cop


class SimpleChiller(Node):
    """A simple chiller model that uses predefined COP (coefficient of performance) values for cooling.

    Simple Chiller has one input electrical port, and one cooling_output (thermal Sink) thermal port.

    The conversion of input electrical energy to cooling output depends on provided coefficients of
    performance (COP) time series data.
    """

    max_cooling_capacity: PositiveFloat = None  # Max cooling load that can be serviced in KWT
    # (if None, bounded by bigM value)
    cooling_cop_time_series: Optional[dict]  # Formatted dict of cooling COPs (coefficients of performance)
    cooling_cop_time_series_ref: Optional[str]
    cooling_cop_constant: Optional[PositiveFloat] = 1  # Constant COP value to use across all optimisation intervals

    cooling_cop_check = validator("cooling_cop_time_series", allow_reuse=True)(non_negative_cop_check)

    electrical_input_port_ref: str = "input"
    thermal_output_port_ref: str = "output"

    def __init__(self, **data):
        super().__init__(**data)
        # Constraint flow of the thermal port
        if self.max_cooling_capacity:
            thermal_import_constraint = FlowConstraint.Fixed
            thermal_import_constraint_value = self.max_cooling_capacity
        else:
            thermal_import_constraint = FlowConstraint.NA
            thermal_import_constraint_value = None

        # Create input and output ports
        self.ports[self.electrical_input_port_ref] = FlexSink(
            units=Units.KW
        )  # Simple Chiller has electrical input port
        # Simple Chiller has cooling output port (thermal sink)
        self.ports[self.thermal_output_port_ref] = FlexSink(
            units=Units.KWT,
            import_constraint=thermal_import_constraint,
            import_constraint_value=thermal_import_constraint_value,
        )

    def set_ports(self, electrical_input_port: FlexSink, thermal_output_port: FlexPort):
        # Discard existing ports
        self.ports.clear()

        # Add the new ports
        self.electrical_input_port_ref = electrical_input_port.port_name
        self.thermal_output_port_ref = thermal_output_port.port_name
        self.ports[self.electrical_input_port_ref] = electrical_input_port
        self.ports[self.thermal_output_port_ref] = thermal_output_port

    def update(self, cooling_cop_time_series):
        self.cooling_cop_time_series = cooling_cop_time_series

    @property
    def cooling_cop(self):
        return "cooling_cop_" + self.node_name

    def add_node_to_model(self, model: EchoConcreteModel, profile):
        # Load coefficient of performance values from profile (if provided by reference)
        self._load_cop_values_from_profile(model, profile)
        super(SimpleChiller, self).add_node_to_model(model, profile)
        setattr(
            model,
            self.cooling_cop,
            en.Param(model.Expansion, model.Time, initialize=self.cooling_cop_time_series, domain=en.NonNegativeReals),
        )

    def apply_node_constraints(self, model: EchoConcreteModel):
        # Get variable names for heating and cooling output depending on thermal ports configuration
        self._apply_node_transformation_constraints(model)

    def _apply_node_transformation_constraints(self, model: EchoConcreteModel):
        cooling_out = getattr(
            model, self.ports[self.thermal_output_port_ref].port_name
        )  # cooling delivered at thermal port
        cooling_cop = getattr(model, self.cooling_cop)

        def cooling_output_rule(model: EchoConcreteModel, p, t):
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

    def _load_cop_values_from_profile(self, model: EchoConcreteModel, profile_df: pd.DataFrame):
        """When coefficient of performance timeseries is set by str reference, load values from profile."""

        if self.cooling_cop_time_series_ref:
            if self.cooling_cop_time_series_ref not in profile_df.columns:
                raise ValueError(
                    "Could not find reference column name " f"{self.cooling_cop_time_series_ref} in the profile."
                )
            self.cooling_cop_time_series = to_initial_values(
                profile_df,
                key=self.cooling_cop_time_series_ref,
                time_periods=len(model.Time),
                expansion_periods=len(model.Expansion),
            )
        self._set_constant_cop_values(model)

    def _set_constant_cop_values(self, model: EchoConcreteModel):
        """If cooling_cop_time_series dictionary is not defined otherwise, use constant cop value"""
        if not self.cooling_cop_time_series:
            self.cooling_cop_time_series = expand_as_dict(
                TimeSeriesData(
                    value=self.cooling_cop_constant,
                    num_time_intervals=len(model.Time),
                    num_expansion_intervals=len(model.Expansion),
                )
            )


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
    def temperature_cop_param(self):
        return f"temperature_cop_factor_{self.node_name}"

    @property
    def electrical_input_port_ref(self):
        return self.input_port_ref

    @property
    def thermal_output_port_ref(self):
        return self.output_port_ref

    def __init__(self, **data):
        super().__init__(**data)
        # A chiller has one electrical input port and one cooling output (thermal sink) port
        self.ports[self.input_port_ref] = FlexSink(units=self.input_port_unit)
        self.ports[self.output_port_ref] = FlexSink(units=self.output_port_unit)
        if self.heat_rejection_port:
            self.ports[self.heat_rejection_port_ref] = FlexSource(units=self.output_port_unit)

    def update(self, ambient_temperature_dict):
        self.ambient_temperature_dict = ambient_temperature_dict

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame):
        self._load_temperature_values_from_profile(model, profile)
        self._define_temperature_dependent_cop_coefficient(model)
        self._set_input_points(model)
        self._set_output_points(model)
        super(ParameterisedChiller, self).add_node_to_model(model, profile)
        if self.heat_rejection_port_ref in self.ports:
            self._add_heat_rejection_constraint(model)

    def set_ports(
        self,
        electrical_input_port: FlexSink,
        cooling_output_port: FlexPort,
        heat_rejection_port: Optional[FlexPort] = None,
    ):
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

    def _define_temperature_dependent_cop_coefficient(self, model: EchoConcreteModel):
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
        temperature_cop_dict = {
            k: np.interp(clamp(v, min_temp, max_temp), temperature_points, cop_points)
            for k, v in temperature_dict.items()
        }

        # Create a parameter holding ambient/condenser temperature dictionary
        # (defaulting to self.constant_ambient_temperature)
        setattr(
            model,
            self.temperature_cop_param,
            en.Param(model.Expansion, model.Time, initialize=temperature_cop_dict, domain=en.Reals),
        )

    def _set_input_points(self, model: EchoConcreteModel):
        """Input breakpoints are input electrical power values calculated as
        cooling_output/(COP_nominal*partial_load_correction) and scaled by 1/temperature_cop_param value"""

        # get parameter holding temperature dependent COP (coefficient of performance) factor
        temperature_cop_param = getattr(model, self.temperature_cop_param)

        def input_point(k, v):
            if v == 0:
                return 0
            else:
                return k * self.max_cooling_capacity / (v * self.nominal_cop)

        self.input_points = {
            (p, t): [input_point(k, v) / temperature_cop_param[p, t] for k, v in self.partial_load_cop.items()]
            for p in range(len(model.Expansion))
            for t in range(len(model.Time))
        }

    def _set_output_points(self, model: EchoConcreteModel):
        """Output breakpoints are partial cooling load values (% of max capacity)"""
        self.output_points = {
            (p, t): [k * self.max_cooling_capacity for k in self.partial_load_cop.keys()]
            for p in range(len(model.Expansion))
            for t in range(len(model.Time))
        }

    def _add_heat_rejection_constraint(self, model: EchoConcreteModel):
        """Get variables representing port flow values for cooling output (heat in) and
        rejected heat flow, set the constraint."""
        heat_in = getattr(model, self.ports[self.output_port_ref].port_name)
        heat_reject = getattr(model, self.ports[self.heat_rejection_port_ref].port_name)

        def heat_reject_constraint(model: EchoConcreteModel, p, t):
            """Amount of rejected heat at each interval equals amount of cooling delivered (heat in) multiplied by
            heat rejection coefficient
            """
            return heat_reject[p, t] == -heat_in[p, t] * self.heat_rejection_coefficient

        setattr(
            model,
            "heat_rejection_constraint_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=heat_reject_constraint),
        )

    def _load_temperature_values_from_profile(self, model: EchoConcreteModel, profile_df: pd.DataFrame):
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


class ThermalNode(Node):
    """
    A thermal node has an internal temperature variable, which can be bounded.
    It can have any number of ports for heating (importing) or cooling (export).
    All the ports are related to temp by an energy balance constraint.
    """

    temp_ub: dict  # Upper bound of acceptable temperature for each time interval: dict with expansion-time keys
    temp_lb: dict  # Lower bound of acceptable temperature for each time interval: dict with expansion-time keys
    external_temp: dict  # External (ambient) temp, formatted as dict with expansion-time keys
    loss_factor: NonNegativeFloat = 0  # Losses due to ambient temp being lower than internal temp
    gain_factor: NonNegativeFloat = 0  # Free gains due to ambient temp being higher than internal temp
    temp_to_energy_coef: PositiveFloat = 1  # Conversion factor * temp change = added energy
    initial_internal_temp: float = 0  # initial internal temperature

    # Pyomo vars/params
    internal_temp: str
    is_gain: str
    losses: str
    gains: str

    def __init__(self, **data):
        super().__init__(**data)
        self.internal_temp = "internal_temp_" + self.node_name
        self.is_gain = "is_gain_" + self.node_name
        self.losses = "losses_" + self.node_name
        self.gains = "gains_" + self.node_name

    def add_node_to_model(self, model: EchoConcreteModel, profile):
        super(ThermalNode, self).add_node_to_model(model, profile)
        self.create_and_bound_temp_vars(model)
        self.loss_and_gain_constraints_and_variables(model)
        self.apply_energy_balance_constraint(model)

    def create_and_bound_temp_vars(self, model: EchoConcreteModel):
        # Create temperature variable
        setattr(model, self.internal_temp, en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))
        # Bound temp variable to be within range
        set_var_bounds_from_dict(model=model, var_name=self.internal_temp, ub=self.temp_ub, lb=self.temp_lb)

    def loss_and_gain_constraints_and_variables(self, model: EchoConcreteModel):
        # Create variable for losses and gains
        setattr(model, self.losses, en.Var(model.Expansion, model.Time, domain=en.NonPositiveReals))
        setattr(model, self.gains, en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))
        setattr(model, self.is_gain, en.Var(model.Expansion, model.Time, domain=en.Binary))

        # Apply constraints on loss and gain variables
        def loss_gain_sum_constraint(model: EchoConcreteModel, p, t):
            """Losses + gains must equal the temperature difference between ambient and internal"""
            return (
                getattr(model, self.losses)[p, t] + getattr(model, self.gains)[p, t]
                == self.external_temp[p, t] - getattr(model, self.internal_temp)[p, t]
            )

        setattr(
            model,
            "loss_gain_con1_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=loss_gain_sum_constraint),
        )

        def loss_or_gain1(model: EchoConcreteModel, p, t):
            """Gains can only be non-zero if is_gain = 1"""
            return getattr(model, self.gains)[p, t] <= getattr(model, self.is_gain)[p, t] * model.bigM

        setattr(
            model, "loss_gain_con2_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=loss_or_gain1)
        )

        def loss_or_gain2(model: EchoConcreteModel, p, t):
            """Losses can only be non-zero if is_gain = 0"""
            return getattr(model, self.losses)[p, t] >= (getattr(model, self.is_gain)[p, t] - 1) * model.bigM

        setattr(
            model, "loss_gain_con3_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=loss_or_gain2)
        )

    def apply_energy_balance_constraint(self, model: EchoConcreteModel):
        # Constraint relating internal, ambient temp, heat in, heat out, losses, and gains
        def rule1(model: EchoConcreteModel, p, t):
            thermal_kw = 0
            for v in self.ports.values():
                thermal_kw += getattr(model, v.port_name)[p, t]  # sum together our thermal ports

            internal_temp = getattr(model, self.internal_temp)
            loss = getattr(model, self.losses)[p, t] * self.loss_factor
            gain = getattr(model, self.gains)[p, t] * self.gain_factor

            if p == 0 and t == 0:
                return (
                    thermal_kw + loss + gain
                    == (internal_temp[p, t] - self.initial_internal_temp) * self.temp_to_energy_coef
                )
            else:
                temp_diff = internal_temp[p, t] - internal_temp[p, t - 1]
                return thermal_kw + loss + gain == temp_diff * self.temp_to_energy_coef

        setattr(model, "internal_temp_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=rule1))


class ThermalStorage(Node):
    """Model of sensible thermal storage with liquid or solid storage medium.

    Thermal storage keeps track of its internal temperature value base. Assumes homogeneous temperature throughout the
    storage volume.
    """

    max_temp: float  # Maximum operational temperature in degrees  Celsius
    min_temp: float  # Minimum operational temperature in degrees  Celsius
    storage_mass: PositiveFloat  # Mass of storage medium in kg
    specific_heat: PositiveFloat  # Specific heat capacity in Joule/kg*C
    ambient_temp: dict = None  # Ambient temp, formatted as dict with expansion-time keys
    ambient_temp_ref: Optional[str]  # Ambient temp by column name reference in profile dataframe
    ins_transmittance: NonNegativeFloat = (
        0  # Thermal transmittance U-value of Thermal Energy Storage insulation in W/sqm*C
    )
    surface_area: NonNegativeFloat = 0  # Surface area of Thermal Energy Storage in square meters, default value=0
    # means zero heat loss/gain
    initial_temp: float = None  # initial internal temperature in degrees  Celsius
    optimised_capacity: bool = False  # If True, set heat storage capacity (size of storage) to be optimisation variable
    energy_flow_units: Units = Units.KWT  # Thermal energy flow units to use, expecting KW Thermal or JPS
    separate_in_out_ports: bool = False  # Create two thermal ports charge and discharge, else 1 two-way port

    input_port_ref: str = "input"
    output_port_ref: str = "output"
    input_output_port_ref: str = "input_output"

    def __init__(self, **data):
        super().__init__(**data)

        # TODO: Shall both ports be bi-directional?
        if self.separate_in_out_ports:
            self.ports[self.input_port_ref] = FlexSink(units=self.energy_flow_units)
            self.ports[self.output_port_ref] = FlexSource(units=self.energy_flow_units)
        else:
            self.ports[self.input_output_port_ref] = FlexPort(units=self.energy_flow_units)

        # Initial temperature is not defined set to mid-operation range
        if not self.initial_temp:
            self.initial_temp = self.min_temp + 0.5 * (self.max_temp - self.min_temp)

    def update(self, ambient_temp):
        self.ambient_temp = ambient_temp

    def set_ports(self, input_port: FlexSink, output_port: FlexSource):
        """Replaces any existing ports with separate input and output ports"""
        # Discard existing ports
        self.ports.clear()

        # Add the new ports
        self.input_port_ref = input_port.port_name
        self.output_port_ref = output_port.port_name
        self.ports[self.input_port_ref] = input_port
        self.ports[self.output_port_ref] = output_port

    def set_port(self, input_output_port: FlexPort):
        """Replaces any existing ports with a combined input output port"""
        # Discard existing ports
        self.ports.clear()

        # Add new port
        self.input_output_port_ref = input_output_port.port_name
        self.ports[self.input_output_port_ref] = input_output_port

    @root_validator
    def _non_zero_temp_range(cls, values: dict) -> dict:
        """Temperature range must be non-zero and positive for Thermal Energy Storage to be operational"""
        if "max_temp" in values and "min_temp" in values and values["max_temp"] - values["min_temp"] <= 0:
            raise ValueError(
                "Temperature range must be non-zero and positive for Thermal Energy Storage to be operational."
                f"Was given max temperature {values['max_temp']} "
                f"and min temperature {values['min_temp']}, "
                f"resulting in range {values['max_temp'] - values['min_temp']}"
            )
        return values

    @validator("energy_flow_units", allow_reuse=True)
    def _units_are_allowed(cls, v: Units) -> Units:
        if v and v not in {Units.JPS, Units.KWT}:
            raise ValueError(f"Only allowed units are KW Thermal (KWT) and Joules per second (JPS). Received {v}")
        return v

    @property
    def internal_temp(self):
        return "internal_temp_" + self.node_name

    @property
    def net_loss_gain(self):
        return "net_loss_gain_" + self.node_name

    @property
    def soc_value(self):
        return "storage_soc_" + self.node_name

    @property
    def soc_constraint(self):
        return "soc_cons_" + self.node_name

    @property
    def lump_capacitance(self):
        return self.storage_mass * self.specific_heat

    @property
    def lump_conductance(self):
        return self.ins_transmittance * self.surface_area

    @property
    def energy_units_conversion(self):
        if self.energy_flow_units == Units.KWT:
            # If ports flow in KWT calculate energy in KWTh
            return 1 / 3600000
        elif self.energy_flow_units == Units.JPS:
            # If ports flow in JPS calculate energy in Joules
            return 1

    @property
    def max_heat_storage_capacity(self):
        return self.lump_capacitance * (self.max_temp - self.min_temp) * self.energy_units_conversion

    def add_node_to_model(self, model: EchoConcreteModel, profile):
        super(ThermalStorage, self).add_node_to_model(model, profile)
        self._load_values_from_profile(model, profile)
        self._create_and_bound_temp_variable(model)
        self._create_soc_variable(model)
        self._apply_net_loss_and_gain_constraint(model)
        self._apply_energy_balance_constraint(model)
        self._apply_soc_constraint(model)

    def _load_values_from_profile(self, model: EchoConcreteModel, profile_df: pd.DataFrame):
        """For all attributes set by str reference, load values from profile."""
        if self.ambient_temp_ref:
            if self.ambient_temp_ref not in profile_df.columns:
                raise ValueError(
                    f"Could find reference column name {self.ambient_temp_ref} "
                    "for ambient temperature in the profile."
                )
            else:
                self.ambient_temp = to_initial_values(
                    profile_df,
                    key=self.ambient_temp_ref,
                    time_periods=len(model.Time),
                    expansion_periods=len(model.Expansion),
                )

        else:
            pass

    def _create_and_bound_temp_variable(self, model: EchoConcreteModel):
        # Create temperature variable
        setattr(model, self.internal_temp, en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))
        # Bound temp variable to be within range
        set_float_var_bounds(model=model, var_name=self.internal_temp, ub=self.max_temp, lb=self.min_temp)

    def _create_soc_variable(self, model: EchoConcreteModel):
        # Calculate initial state of charge based on the initial internal temperature value
        initial_soc = self.lump_capacitance * (self.initial_temp - self.min_temp) * self.energy_units_conversion
        # Create soc variable and bound it
        setattr(
            model,
            self.soc_value,
            en.Var(model.Expansion, model.Time, initialize=initial_soc, bounds=(0, self.max_heat_storage_capacity)),
        )

    def _apply_net_loss_and_gain_constraint(self, model: EchoConcreteModel):
        # Create variable for net losses and gains
        setattr(model, self.net_loss_gain, en.Var(model.Expansion, model.Time, domain=en.Reals))

        # Apply constraints on loss and gain variables
        def net_loss_gain_constraint(model: EchoConcreteModel, p, t):
            """Losses to /gains from environment equals to the temperature
            difference between ambient and internal multiplied by lump_conductance.

            If not ambient temperature values are provided, set loss to zero.
            """
            if not self.ambient_temp:
                return getattr(model, self.net_loss_gain)[p, t] == 0

            return (
                getattr(model, self.net_loss_gain)[p, t]
                == (self.ambient_temp[p, t] - getattr(model, self.internal_temp)[p, t]) * self.lump_conductance
            )

        # Loss/gain values calculated in Joules per sec!

        setattr(
            model,
            "loss_gain_con1_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=net_loss_gain_constraint),
        )

    def _apply_energy_balance_constraint(self, model: EchoConcreteModel):
        # Constraint relating internal, ambient temp, heat in, heat out, losses, and gains
        dt_sec = model.scenario_settings.interval_duration * 60
        max_t = len(model.Time)
        if self.energy_flow_units == Units.KWT:
            # If ports flow in KWT transform to Joules
            flow_units_scaler = 1000
        elif self.energy_flow_units == Units.JPS:
            # If ports flow in JPS calculate losses in JPS
            flow_units_scaler = 1

        def change_of_internal_temperature_constraint(model: EchoConcreteModel, p, t):
            heat_in_out = 0
            for v in self.ports.values():
                heat_in_out += getattr(model, v.port_name)[p, t]  # sum together our thermal ports

            heat_in_out *= flow_units_scaler
            internal_temp = getattr(model, self.internal_temp)
            loss_gain = getattr(model, self.net_loss_gain)[p, t]

            if p == 0 and t == 0:
                return (heat_in_out + loss_gain) * dt_sec == (
                    internal_temp[p, t] - self.initial_temp
                ) * self.lump_capacitance
            elif t == 0:
                # Constraint enforcing temperature (and thus SOC) at the beginning of each expansion
                # periods be the same as at the end of previous expansion period
                return (heat_in_out + loss_gain) * dt_sec == (
                    internal_temp[p, t] - internal_temp[p - 1, max_t]
                ) * self.lump_capacitance
            else:
                temp_diff = internal_temp[p, t] - internal_temp[p, t - 1]
                return (heat_in_out + loss_gain) * dt_sec == temp_diff * self.lump_capacitance

        setattr(
            model,
            "internal_temp_con_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=change_of_internal_temperature_constraint),
        )

    def _apply_soc_constraint(self, model: EchoConcreteModel):
        # State of charge in Joule or KWTh is a linear function of the internal temperature
        def soc_rule(model: EchoConcreteModel, p, t):
            soc = getattr(model, self.soc_value)
            internal_temperature = getattr(model, self.internal_temp)
            self.lump_capacitance * (self.initial_temp - self.min_temp) * self.energy_units_conversion
            return (
                soc[p, t]
                == self.lump_capacitance * (internal_temperature[p, t] - self.min_temp) * self.energy_units_conversion
            )

        setattr(model, "SOC_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=soc_rule))


class SimpleHeatPump(Node):
    """A simple heat pump model that uses predefined COP (coefficient of performance) values for heating and cooling.

    SimpleHeatPump has one input electrical port, and one bidirectional thermal port. In this configuration the heatpump
    can do heating or cooling, but not both simultaneously.

    The conversion of input electrical energy to heating or cooling output depends on provided coefficients of
    performance (COP) time series data.
    """

    max_cooling_capacity: PositiveFloat = (
        None  # Max cooling load that can be serviced in KWT (if None, bounded by bigM value)
    )
    max_heating_capacity: PositiveFloat = (
        None  # Max heating load that can be serviced in KWT (if None, bounded by bigM value)
    )
    heating_cop_time_series: Optional[dict]  # Formatted dict of heating COPs (coefficients of performance)
    # per time period
    cooling_cop_time_series: Optional[dict]  # Formatted dict of cooling COPs (coefficients of performance)
    # per time period
    heating_cop_time_series_ref: Optional[str]
    cooling_cop_time_series_ref: Optional[str]

    cooling_cop_constant: Optional[PositiveFloat] = 1  # Constant COP value to use across all optimisation intervals
    heating_cop_constant: Optional[PositiveFloat] = 1  # Constant COP value to use across all optimisation intervals

    heating_cop_check = validator("heating_cop_time_series", allow_reuse=True)(non_negative_cop_check)
    cooling_cop_check = validator("cooling_cop_time_series", allow_reuse=True)(non_negative_cop_check)

    electrical_input_port_ref: str = "input"
    thermal_output_port_ref: str = "output"

    def __init__(self, **data):
        super().__init__(**data)
        self.create_ports()

    def update(self, heating_cop_time_series, cooling_cop_time_series):
        self.heating_cop_time_series = heating_cop_time_series
        self.cooling_cop_time_series = cooling_cop_time_series

    # Naming variables
    @property
    def heating_cop(self):
        return "heating_cop_" + self.node_name

    @property
    def cooling_cop(self):
        return "cooling_cop_" + self.node_name

    @property
    def power_to_heat(self):
        return "power_to_heat_" + self.node_name

    @property
    def power_to_cool(self):
        return "power_to_cool_" + self.node_name

    def create_ports(self):
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

    def set_ports(self, electrical_input_port: FlexSink, thermal_output_port: FlexPort):
        # Discard existing ports
        self.ports.clear()

        # Add the new ports
        self.electrical_input_port_ref = electrical_input_port.port_name
        self.thermal_output_port_ref = thermal_output_port.port_name
        self.ports[self.electrical_input_port_ref] = electrical_input_port
        self.ports[self.thermal_output_port_ref] = thermal_output_port

    def _set_ports_var_bounds(self, model: EchoConcreteModel):
        """Set cooling and heating port flow bounds based on the max heating and cooling capacity attribute if given.

        Split output port into non-positive and non-negative components.
        """
        # Split output port into +ve and -ve components. +ve component will be cooling,
        # -ve component will be heating
        self.ports[self.thermal_output_port_ref].constrain_pos_neg(model)
        lower_bound = self.max_heating_capacity or model.bigM
        upper_bound = self.max_cooling_capacity or model.bigM
        set_float_var_bounds(
            model,
            self.ports[self.thermal_output_port_ref].port_name,
            ub=upper_bound,
            lb=-lower_bound,
        )

    def _set_helper_variables(self, model: EchoConcreteModel):
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

    def add_node_to_model(self, model: EchoConcreteModel, profile):
        # Load coefficient of performance values from profile (if be set ref)
        self._load_cop_values_from_profile(model, profile)
        super(SimpleHeatPump, self).add_node_to_model(model, profile)
        self._set_ports_var_bounds(model)
        self._set_helper_variables(model)

    def apply_node_constraints(self, model: EchoConcreteModel):
        # Get variable names for heating and cooling output depending on thermal ports configuration
        heating_out_var = self.ports[self.thermal_output_port_ref].neg
        cooling_out_var = self.ports[self.thermal_output_port_ref].pos
        is_cooling_var = self.ports[self.thermal_output_port_ref].is_pos
        # Apply heating_cooling constraints and transformation constraint
        self._apply_only_heat_or_cool_constraints(model, binary_var_name=is_cooling_var)
        self._apply_node_transformation_constraints(
            model, heating_out_var=heating_out_var, cooling_out_var=cooling_out_var
        )

    def _load_cop_values_from_profile(self, model: EchoConcreteModel, profile_df: pd.DataFrame):
        """When coefficient of performance timeseries is set by str reference, load values from profile."""
        if self.cooling_cop_time_series_ref:
            if self.cooling_cop_time_series_ref not in profile_df.columns:
                raise ValueError(
                    "Could not find reference column name " f"{self.cooling_cop_time_series_ref} in the profile."
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
                    "Could not find reference column name " f"{self.heating_cop_time_series_ref} in the profile."
                )
            else:
                self.heating_cop_time_series = to_initial_values(
                    profile_df,
                    key=self.heating_cop_time_series_ref,
                    time_periods=len(model.Time),
                    expansion_periods=len(model.Expansion),
                )

        self._set_constant_cop_values(model)

    def _set_constant_cop_values(self, model: EchoConcreteModel):
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

    def _apply_only_heat_or_cool_constraints(self, model: EchoConcreteModel, binary_var_name: str):
        is_cooling = getattr(model, binary_var_name)  # binary var for whether we are cooling
        power_in = getattr(model, self.ports[self.electrical_input_port_ref].port_name)  # input electrical power

        def only_heat_or_cool1(model: EchoConcreteModel, p, t):
            """Constraint power_to_heat variable.
            power_to_heat=0 when is_cooling=1. power_to_heat is positive real =< bigM value when is_cooling=0"""
            return getattr(model, self.power_to_heat)[p, t] <= (1 - is_cooling[p, t]) * model.bigM

        setattr(
            model,
            "only_heat_or_cool1_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=only_heat_or_cool1),
        )

        def only_heat_or_cool2(model: EchoConcreteModel, p, t):
            """Constraint power_to_cool variable.
            power_to_cool=0 when is_cooling=0. power_to_cool is positive real =< bigM value when is_cooling=1"""
            return getattr(model, self.power_to_cool)[p, t] <= is_cooling[p, t] * model.bigM

        setattr(
            model,
            "only_heat_or_cool2_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=only_heat_or_cool2),
        )

        def sum_rule(model: EchoConcreteModel, p, t):
            """Electrical power input used for heating and for cooling must sum to total electrical power input"""
            return power_in[p, t] == getattr(model, self.power_to_heat)[p, t] + getattr(model, self.power_to_cool)[p, t]

        setattr(model, "sum_heat_cool_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=sum_rule))

    def _apply_node_transformation_constraints(
        self, model: EchoConcreteModel, heating_out_var: str, cooling_out_var: str
    ):
        heating_out = getattr(model, heating_out_var)  # heating delivered at thermal port (heat exported)
        cooling_out = getattr(model, cooling_out_var)  # cooling delivered at thermal port (heat absorbed)
        heating_cop = getattr(model, self.heating_cop)
        cooling_cop = getattr(model, self.cooling_cop)

        def heating_output_rule(model: EchoConcreteModel, p, t):
            """When heatpump used for heating, thermal port is exporting energy, thus -1 scaling.

            Thermal port flow values are negative in heating mode.
            heating_out = power_to_heat * heating cop * -1.
            """
            return heating_out[p, t] == getattr(model, self.power_to_heat)[p, t] * heating_cop[p, t] * -1

        def cooling_output_rule(model: EchoConcreteModel, p, t):
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


class SimpleHeatPumpDualOutput(SimpleHeatPump):
    """A simple dual output (four-pipe) heatpump model that uses predefined COP values for heating and cooling.

    SimpleHeatPumpDualOutput has one input electrical port and two thermal ports: cooling_output (thermal Sink)
    and heating_output (thermal Source).
    In dual output configuration the heatpump can do heating and cooling simultaneously and independently.
    When heating and cooling simultaneously, the waste heat from cooling loop can be used in the heating loop.

    The conversion of input electrical energy to heating or cooling output depends on provided coefficients of
    performance (COP) time series data.
    """

    waste_heat_recovery_coeff: NonNegativeFloat = 1  # Waste heat recovery coefficient from cooling to heating loop
    electrical_input_port_ref: str = "input"
    cooling_output_port_ref: str = "cooling_output"
    heating_output_port_ref: str = "heating_output"

    def __init__(self, **data):
        super().__init__(**data)
        # Create input and output ports: electrical input port, cooling output port and heating output port
        self.create_ports()

    @property
    def heating_out_adjusted(self):
        """heating_out_adjusted variable represents amount of heat that is produced running the primary heating loop."""
        return "heating_out_adjusted_" + self.node_name

    @property
    def delta_heat_flow(self):
        return f"delta_heat_flow_{self.node_name}"

    @property
    def recovered_waste_heat(self):
        return f"recovered_waste_heat_{self.node_name}"

    def create_ports(self):
        # Create input and output ports
        self.ports[self.electrical_input_port_ref] = FlexSink(units=Units.KW)  # Heat pump has electrical input port
        self.ports[self.cooling_output_port_ref] = FlexSink(units=Units.KWT)  # Heat pump has one cooling output port
        self.ports[self.heating_output_port_ref] = FlexSource(units=Units.KWT)  # Heat pump has one heating output port

    def set_ports(
        self, electrical_input_port: FlexSink, cooling_output_port: FlexSink, heating_output_port: FlexSource
    ):
        # Discard existing ports
        self.ports.clear()

        # Add the new ports
        self.electrical_input_port_ref = electrical_input_port.port_name
        self.cooling_output_port_ref = cooling_output_port.port_name
        self.heating_output_port_ref = heating_output_port.port_name
        self.ports[self.electrical_input_port_ref] = electrical_input_port
        self.ports[self.cooling_output_port_ref] = cooling_output_port.port_name
        self.ports[self.heating_output_port_ref] = heating_output_port.port_name

    def _set_ports_var_bounds(self, model: EchoConcreteModel):
        """Set cooling and heating port flow bounds based on the max heating and cooling capacity attribute if given."""
        lower_bound = self.max_heating_capacity or model.bigM
        upper_bound = self.max_cooling_capacity or model.bigM
        set_float_var_bounds(model, self.ports[self.cooling_output_port_ref].port_name, ub=upper_bound, lb=0)
        set_float_var_bounds(model, self.ports[self.heating_output_port_ref].port_name, ub=0, lb=-1 * lower_bound)

    def _create_heat_recovery_vars(self, model: EchoConcreteModel):
        """Create variable for adjusted heat_output supplied by the heating loop"""
        setattr(model, self.heating_out_adjusted, en.Var(model.Expansion, model.Time, domain=en.NonPositiveReals))
        setattr(model, self.recovered_waste_heat, en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))

    def add_node_to_model(self, model: EchoConcreteModel, profile):
        # Use parent class method
        super(SimpleHeatPumpDualOutput, self).add_node_to_model(model, profile)
        self._create_heat_recovery_vars(model)
        self._create_delta_heat_flow_vars(model)

    def apply_node_constraints(self, model: EchoConcreteModel):
        # Get variable names for heating and cooling output depending on thermal ports configuration
        h_out_adjusted_var = self.heating_out_adjusted
        c_out_var = self.ports[self.cooling_output_port_ref].port_name
        # Apply heating_cooling constraints and transformation constraint
        self._apply_heat_recovery_constraints(model)
        self._apply_node_transformation_constraints(
            model, heating_out_var=h_out_adjusted_var, cooling_out_var=c_out_var
        )

    def _create_delta_heat_flow_vars(self, model: EchoConcreteModel):
        """Create a delta heat flow variable, split in pos and negative components"""
        setattr(model, self.delta_heat_flow, en.Var(model.Expansion, model.Time, domain=en.Reals))
        setattr(model, f"{self.delta_heat_flow}_pos", en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))
        setattr(model, f"{self.delta_heat_flow}_neg", en.Var(model.Expansion, model.Time, domain=en.NonPositiveReals))
        setattr(model, f"{self.delta_heat_flow}_is_pos", en.Var(model.Expansion, model.Time, domain=en.Binary))

        def total_sum_rule(model: EchoConcreteModel, p, t):
            """positive and negative component sum"""
            return (
                getattr(model, f"delta_heat_flow_{self.node_name}")[p, t]
                == getattr(model, f"delta_heat_flow_{self.node_name}_pos")[p, t]
                + getattr(model, f"delta_heat_flow_{self.node_name}_neg")[p, t]
            )

        setattr(
            model,
            "sum_pos_neg_delta_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=total_sum_rule),
        )

        def is_pos_rule(model: EchoConcreteModel, p, t):
            """Positive value constraint"""
            return (
                getattr(model, f"delta_heat_flow_{self.node_name}_pos")[p, t]
                <= getattr(model, f"delta_heat_flow_{self.node_name}_is_pos")[p, t] * model.bigM
            )

        setattr(
            model, "is_pos_delta_rule_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=is_pos_rule)
        )

        def is_neg_rule(model: EchoConcreteModel, p, t):
            """positive and negative component sum"""
            return (
                getattr(model, f"delta_heat_flow_{self.node_name}_neg")[p, t]
                >= (getattr(model, f"delta_heat_flow_{self.node_name}_is_pos")[p, t] - 1) * model.bigM
            )

        setattr(
            model, "is_neg_delta_rule_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=is_neg_rule)
        )

    def _apply_heat_recovery_constraints(self, model: EchoConcreteModel):
        power_in = getattr(model, self.ports[self.electrical_input_port_ref].port_name)  # input electrical power
        h_out_var = getattr(model, self.ports[self.heating_output_port_ref].port_name)
        c_out_var = getattr(model, self.ports[self.cooling_output_port_ref].port_name)
        h_out_adjusted_var = getattr(model, self.heating_out_adjusted)
        delta_heat_flow = getattr(model, self.delta_heat_flow)
        delta_heat_flow_neg = getattr(model, f"{self.delta_heat_flow}_neg")
        waste_heat_var = getattr(model, self.recovered_waste_heat)

        def delta_heat_flow_rule(model: EchoConcreteModel, p, t):
            """Delta heat flow between cooling and heating circuits"""
            return delta_heat_flow[p, t] == h_out_var[p, t] + self.waste_heat_recovery_coeff * c_out_var[p, t]

        setattr(
            model,
            "delta_heat_flow_rule_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=delta_heat_flow_rule),
        )

        def adjusted_heat_value_rule(model: EchoConcreteModel, p, t):
            """heating_out_adjusted variable represents amount of heat that is produced in the primary heating loop.

            It is calculated as heating_out_adjusted = heating_delivered_to_load - heating_recovered_from_waste.

            Using negative component of the  delta_heat_flow variable ensures that if more waste heat is available than
            we need to service the load, then primary loop produces 0 heat.
            """
            return h_out_adjusted_var[p, t] == delta_heat_flow_neg[p, t]

        setattr(
            model,
            "adjusted_heat_value_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=adjusted_heat_value_rule),
        )

        def recovered_heat_value_rule(model: EchoConcreteModel, p, t):
            """Track amount of recovered waste heat"""
            return waste_heat_var[p, t] == -1 * h_out_var[p, t] + delta_heat_flow_neg[p, t]

        setattr(
            model,
            "recovered_heat_value_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=recovered_heat_value_rule),
        )

        def sum_rule(model: EchoConcreteModel, p, t):
            """Electrical power input used for heating and for cooling must sum to total electrical power input"""
            return power_in[p, t] == getattr(model, self.power_to_heat)[p, t] + getattr(model, self.power_to_cool)[p, t]

        setattr(model, "sum_heat_cool_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=sum_rule))


class ParameterisedHeatPump(Node):
    """A Parameterised heat pump model.

    This model is different to simple heatpump model in that it uses piecewise linear partial load COP factor
    (coefficient of performance) and piecewise linear temperature COP factor to calculate actual values for heating
    and cooling at each step.

    HeatPumpTwoPipe has one input electrical port and one bidirectional thermal port.
    The heat pump can do heating or cooling, but not both simultaneously.

    The conversion of input electrical energy to heating or cooling output depends on calculated coefficients of
    performance (COP) at each time step.
    """

    nominal_heating_cop: PositiveFloat  # Nominal coefficient of performance in heating mode COP = output/input
    nominal_cooling_cop: PositiveFloat  # Nominal coefficient of performance in cooling mode COP = output/input
    max_heating_capacity: PositiveFloat  # Maximum cooling output in KWT (1RT ~ 3.5KWT)
    max_cooling_capacity: PositiveFloat  # Maximum cooling output in KWT (1RT ~ 3.5KWT)
    partial_load_cop_heating: dict = {
        0: 0,
        0.25: 0.8,
        0.5: 0.9,
        0.75: 1,
        1: 0.85,
    }  # Scaling factor for the nominal COP (coefficient of performance) depending on the partial load value
    partial_load_cop_cooling: dict = {
        0: 0,
        0.25: 0.8,
        0.5: 0.9,
        0.75: 1,
        1: 0.85,
    }  # Scaling factor for the nominal COP (coefficient of performance) depending on the partial load value
    temperature_dependent_cop_heating: dict = {
        -10: 0.4,
        0: 0.6,
        10: 0.7,
        20: 0.9,
        30: 1,
        45: 1,
    }  # Scaling factor for the nominal heating COP depending on
    # the ambient/condenser temperature value
    temperature_dependent_cop_cooling: dict = {
        0: 0.7,
        10: 1,
        20: 0.5,
        30: 0.35,
        45: 0.2,
    }  # Scaling factor for the nominal cooling COP depending on
    # the ambient/condenser temperature value
    ambient_temperature_dict: dict = (
        None  # Condenser side temperature ambient air temperature or condenser
        # water temperature for water cooled chiller
    )
    ambient_temperature_ref: str = None  # Ambient temperature array passed by string reference
    constant_ambient_temperature: float = 10  # Constant value for ambient temperature in degrees C,
    # when no array data is provided
    heat_intake_rejection_port: bool = False  # If True, add heat intake_rejection port
    heat_intake_rejection_coefficient: PositiveFloat = 1
    # Heat intake coefficient  = heating_delivered_to_load/heat_intake_from_source
    # Heat rejection coefficient = cooling_delivered_to_load/heat_rejected_to_source (environment)

    # TODO: We do not want user to ever provide these. Rewrite to be pyomo parameter
    input_points_cooling: dict = None
    output_points_cooling: dict = None
    input_points_heating: dict = None
    output_points_heating: dict = None

    electrical_input_port_ref: str = "input"
    thermal_output_port_ref: str = "output"
    heat_intake_rejection_port_ref: str = "heat_intake_rejection"

    # partial_load_cop_check = root_validator(allow_reuse=True)(validate_partial_load_cop)
    # temperature_cop_check = root_validator(allow_reuse=True)(validate_temperature_dependent_cop)

    @property
    def temperature_cop_heating_param(self):
        return f"temperature_cop_heating_factor_{self.node_name}"

    @property
    def temperature_cop_cooling_param(self):
        return f"temperature_cop_cooling_factor_{self.node_name}"

    @property
    def power_to_heat(self):
        return "power_to_heat_" + self.node_name

    @property
    def power_to_cool(self):
        return "power_to_cool_" + self.node_name

    def __init__(self, **data):
        super().__init__(**data)
        self.create_ports()

    def update(self, ambient_temperature_dict):
        self.ambient_temperature_dict = ambient_temperature_dict

    def create_ports(self):
        # Create input and output ports
        # Heat pump has electrical input port
        self.ports[self.electrical_input_port_ref] = FlexSink(units=Units.KW)
        # Heat pump has one thermal output port
        # Thermal 'output' port is a two-way port: heating output = thermal source, cooling output = thermal sink
        self.ports[self.thermal_output_port_ref] = FlexPort(units=Units.KWT)
        if self.heat_intake_rejection_port:
            self.ports[self.heat_intake_rejection_port_ref] = FlexPort(units=Units.KWT)

    def set_ports(
        self,
        electrical_input_port: FlexSink,
        thermal_output_port: FlexPort,
        heat_intake_rejection_port: Optional[FlexPort] = None,
    ):
        # Discard existing ports
        self.ports.clear()

        # Update port references
        self.electrical_input_port_ref = electrical_input_port.port_name
        self.thermal_output_port_ref = thermal_output_port.port_name

        # Add the new ports
        self.ports[self.electrical_input_port_ref] = electrical_input_port
        self.ports[self.thermal_output_port_ref] = thermal_output_port

        # Handle heat intake rejection
        self.heat_intake_rejection_port = False  # clear if already set
        if heat_intake_rejection_port:
            self.heat_intake_rejection_port = True
            self.heat_intake_rejection_port_ref = heat_intake_rejection_port.port_name
            self.ports[self.heat_intake_rejection_port_ref] = heat_intake_rejection_port

    def add_node_to_model(self, model: EchoConcreteModel, profile):
        """Set up variables and parameters associated with the node"""
        super(ParameterisedHeatPump, self).add_node_to_model(model, profile)
        self._set_helper_variables(model)
        self._load_temperature_values_from_profile(model, profile)
        self._define_temperature_dependent_cop_coefficient(model)
        self._set_input_points_cooling(model)
        self._set_output_points_cooling(model)
        self._set_input_points_heating(model)
        self._set_output_points_heating(model)
        self._set_var_bounds(model)

    def apply_node_constraints(self, model: EchoConcreteModel):
        """Set up constraints associated with the node"""
        # Get variable names for heating and cooling output depending on thermal ports configuration
        heat_out_var = self.ports[self.thermal_output_port_ref].neg
        cool_out_var = self.ports[self.thermal_output_port_ref].pos
        is_cooling_var = self.ports[self.thermal_output_port_ref].is_pos
        # Apply only heating or cooling constraint
        self._apply_only_heat_or_cool_constraints(model, binary_var_name=is_cooling_var)
        # set piecewise linear constraint for heating output
        self._set_piecewise_linear_heating_cop_constraint(
            model, power_to_heat_var=self.power_to_heat, heating_out_var=heat_out_var
        )
        # set piecewise linear constraint for cooling output
        self._set_piecewise_linear_cooling_cop_constraint(
            model, power_to_cool_var=self.power_to_cool, cooling_out_var=cool_out_var
        )
        if self.heat_intake_rejection_port_ref in self.ports:
            self._add_heat_intake_rejection_constraint(model)

    def _add_heat_intake_rejection_constraint(self, model: EchoConcreteModel):
        """Get variable representing port flow values for thermal output and
        intake or rejection of heat flow, set the constraint."""
        thermal_output = getattr(model, self.ports[self.thermal_output_port_ref].port_name)
        heat_intake_reject = getattr(model, self.ports[self.heat_intake_rejection_port_ref].port_name)

        def heat_reject_constraint(model: EchoConcreteModel, p, t):
            """Amount of rejected heat to the environment at each interval equals amount of cooling delivered (heat in)
            multiplied by heat rejection coefficient.
            Amount of heat intake from source/ environment at each interval equals amount of heating delivered
            (heat out) multiplied by heat rejection coefficient.
            """
            return heat_intake_reject[p, t] == -thermal_output[p, t] * self.heat_intake_rejection_coefficient

        setattr(
            model,
            "heat_intake_rejection_constraint_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=heat_reject_constraint),
        )

    def _set_var_bounds(self, model: EchoConcreteModel):
        """Set cooling and heating port flow bounds based on the max heating and cooling capacity attribute if given.

        Split output port into non-positive and non-negative components.
        """
        lower_bound = self.max_heating_capacity or model.bigM
        upper_bound = self.max_cooling_capacity or model.bigM
        set_float_var_bounds(
            model,
            self.ports[self.thermal_output_port_ref].port_name,
            ub=upper_bound,
            lb=-1 * lower_bound,
        )
        max_input_cooling = max(max(self.input_points_cooling.values()))
        min_input_cooling = min(min(self.input_points_cooling.values()))
        max_output_cooling = max(max(self.output_points_cooling.values()))
        min_output_cooling = min(min(self.output_points_cooling.values()))
        set_float_var_bounds(
            model,
            self.power_to_cool,
            ub=max_input_cooling,
            lb=min_input_cooling,
        )
        set_float_var_bounds(
            model,
            self.ports[self.thermal_output_port_ref].pos,
            ub=max_output_cooling,
            lb=min_output_cooling,
        )
        max_input_heating = max(max(self.input_points_heating.values()))
        min_input_heating = min(min(self.input_points_heating.values()))
        max_output_heating = max(max(self.output_points_heating.values()))
        min_output_heating = min(min(self.output_points_heating.values()))
        set_float_var_bounds(
            model,
            self.power_to_heat,
            ub=max_input_heating,
            lb=min_input_heating,
        )
        set_float_var_bounds(
            model,
            self.ports[self.thermal_output_port_ref].neg,
            ub=max_output_heating,
            lb=min_output_heating,
        )

    def _set_helper_variables(self, model: EchoConcreteModel):
        """Create internal variables representing amount of electrical power used to produce heating or cooling
        at each interval. Both variables are non-negative, this is not the same as thermal port flow value.
        Intermediate helper variables."""
        setattr(
            model, self.power_to_heat, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals)
        )
        setattr(
            model, self.power_to_cool, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals)
        )
        # Split output port into +ve and -ve components. +ve component will be cooling,
        # -ve component will be heating
        self.ports[self.thermal_output_port_ref].constrain_pos_neg(model)

    def _load_temperature_values_from_profile(self, model: EchoConcreteModel, profile_df: pd.DataFrame):
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

    def _apply_only_heat_or_cool_constraints(self, model: EchoConcreteModel, binary_var_name: str):
        is_cooling = getattr(model, binary_var_name)  # binary var for whether we are cooling
        power_in = getattr(model, self.ports[self.electrical_input_port_ref].port_name)  # input electrical power

        def only_heat_or_cool1(model: EchoConcreteModel, p, t):
            """Constraint power_to_heat variable.
            power_to_heat=0 when is_cooling=1. power_to_heat is positive real =< bigM value when is_cooling=0"""
            return getattr(model, self.power_to_heat)[p, t] <= (1 - is_cooling[p, t]) * model.bigM

        setattr(
            model,
            "only_heat_or_cool1_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=only_heat_or_cool1),
        )

        def only_heat_or_cool2(model: EchoConcreteModel, p, t):
            """Constraint power_to_cool variable.
            power_to_cool=0 when is_cooling=0. power_to_cool is positive real =< bigM value when is_cooling=1"""
            return getattr(model, self.power_to_cool)[p, t] <= is_cooling[p, t] * model.bigM

        setattr(
            model,
            "only_heat_or_cool2_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=only_heat_or_cool2),
        )

        def sum_rule(model: EchoConcreteModel, p, t):
            """Electrical power input used for heating and for cooling must sum to total electrical power input"""
            return power_in[p, t] == getattr(model, self.power_to_heat)[p, t] + getattr(model, self.power_to_cool)[p, t]

        setattr(model, "sum_heat_cool_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=sum_rule))

    def _define_temperature_dependent_cop_coefficient(self, model: EchoConcreteModel):
        """Get heating and cooling COP (coefficient of performance) scaling factor for each interval.

        Calculate value of the temperature_cop_factor parameter using numpy linear interpolation function.
        """

        temperature_points_heating = list(self.temperature_dependent_cop_heating.keys())
        cop_points_heating = list(self.temperature_dependent_cop_heating.values())
        temperature_points_cooling = list(self.temperature_dependent_cop_cooling.keys())
        cop_points_cooling = list(self.temperature_dependent_cop_cooling.values())

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
        min_temp_heating = min(self.temperature_dependent_cop_heating.keys())
        max_temp_heating = max(self.temperature_dependent_cop_heating.keys())
        temperature_cop_dict_heating = {
            k: np.interp(clamp(v, min_temp_heating, max_temp_heating), temperature_points_heating, cop_points_heating)
            for k, v in temperature_dict.items()
        }

        min_temp_cooling = min(self.temperature_dependent_cop_cooling.keys())
        max_temp_cooling = max(self.temperature_dependent_cop_cooling.keys())
        temperature_cop_dict_cooling = {
            k: np.interp(clamp(v, min_temp_cooling, max_temp_cooling), temperature_points_cooling, cop_points_cooling)
            for k, v in temperature_dict.items()
        }

        # Create a parameter holding ambient/condenser temperature dictionary
        # (defaulting to self.constant_ambient_temperature)
        setattr(
            model,
            self.temperature_cop_heating_param,
            en.Param(model.Expansion, model.Time, initialize=temperature_cop_dict_heating, domain=en.Reals),
        )
        setattr(
            model,
            self.temperature_cop_cooling_param,
            en.Param(model.Expansion, model.Time, initialize=temperature_cop_dict_cooling, domain=en.Reals),
        )

    def _set_piecewise_linear_cooling_cop_constraint(
        self, model: EchoConcreteModel, power_to_cool_var: str, cooling_out_var: str
    ):
        xvar = getattr(model, power_to_cool_var)
        yvar = getattr(model, cooling_out_var)
        xdata = self.input_points_cooling
        ydata = self.output_points_cooling
        con_name = "piecewise_con_cooling_" + self.node_name
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

    def _set_piecewise_linear_heating_cop_constraint(
        self, model: EchoConcreteModel, power_to_heat_var: str, heating_out_var: str
    ):
        xvar = getattr(model, power_to_heat_var)
        yvar = getattr(model, heating_out_var)
        xdata = self.input_points_heating
        ydata = self.output_points_heating
        con_name = "piecewise_con_heating_" + self.node_name
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

    def _set_input_points_cooling(self, model: EchoConcreteModel):
        """Input breakpoints are input electrical power values calculated as
        cooling_output/(COP_nominal*partial_load_correction) and scaled by 1/temperature_cop_param value"""

        # get parameter holding temperature dependent COP (coefficient of performance) factor
        temperature_cop_param = getattr(model, self.temperature_cop_cooling_param)

        def input_point(k, v):
            if v == 0:
                return 0
            else:
                return k * self.max_cooling_capacity / (v * self.nominal_cooling_cop)

        self.input_points_cooling = {
            (p, t): [input_point(k, v) / temperature_cop_param[p, t] for k, v in self.partial_load_cop_cooling.items()]
            for p in range(len(model.Expansion))
            for t in range(len(model.Time))
        }

    def _set_output_points_cooling(self, model: EchoConcreteModel):
        """Output breakpoints are partial cooling load values (% of max capacity)"""
        self.output_points_cooling = {
            (p, t): [k * self.max_cooling_capacity for k in self.partial_load_cop_cooling.keys()]
            for p in range(len(model.Expansion))
            for t in range(len(model.Time))
        }

    def _set_input_points_heating(self, model: EchoConcreteModel):
        """Input breakpoints are input electrical power values calculated as
        heating_output/(COP_nominal*partial_load_correction) and scaled by 1/temperature_cop_param value"""

        # get parameter holding temperature dependent COP (coefficient of performance) factor
        temperature_cop_param = getattr(model, self.temperature_cop_heating_param)

        def input_point(k, v):
            if v == 0:
                return 0
            else:
                return k * self.max_heating_capacity / (v * self.nominal_heating_cop)

        self.input_points_heating = {
            (p, t): [input_point(k, v) / temperature_cop_param[p, t] for k, v in self.partial_load_cop_heating.items()]
            for p in range(len(model.Expansion))
            for t in range(len(model.Time))
        }

    def _set_output_points_heating(self, model: EchoConcreteModel):
        """Output breakpoints are partial heating load values (% of max capacity).

        Need to multiply by -1, heating is negative flow of the thermal port.

        """
        self.output_points_heating = {
            (p, t): [-1 * k * self.max_heating_capacity for k in self.partial_load_cop_heating.keys()]
            for p in range(len(model.Expansion))
            for t in range(len(model.Time))
        }
