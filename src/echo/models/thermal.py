from typing import Optional

import pandas as pd
from pydantic import root_validator, validator, PositiveFloat, NonNegativeFloat

import numpy as np
import pyomo.environ as en

from echo.configuration import Units
from echo.models.agnostic import (
    FlexPort,
    FlexSink,
    FlexSource,
    TimeVaryingPiecewiseIONode,
)
from echo.models.base import Node
from echo.models.scenario import EchoConcreteModel
from echo.utils import (
    set_var_bounds_from_dict,
    set_float_var_bounds,
    to_initial_values,
    TimeSeriesData,
    expand_as_dict,
    clamp,
)
from echo.validators import validate_partial_load_cop, validate_temperature_dependent_cop, non_negative_cop_check


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

    cooling_cop_check = validator("cooling_cop_time_series", allow_reuse=True)(non_negative_cop_check)

    def __init__(self, **data):
        super().__init__(**data)
        # Create input and output ports
        self.ports["input"] = FlexSink(units=Units.KW)  # Simple Chiller has electrical input port
        self.ports["output"] = FlexSink(units=Units.KWT)  # Simple Chiller has one cooling output port

    @property
    def cooling_cop(self):
        return "cooling_cop_" + self.node_name

    @property
    def power_to_cool(self):
        return "power_to_cool_" + self.node_name

    def add_node_to_model(self, model: EchoConcreteModel, profile):
        # Load coefficient of performance values from profile (if provided by reference)
        self.load_cop_values_from_profile(model, profile)
        super(SimpleChiller, self).add_node_to_model(model, profile)
        # Create internal variable representing amount of electrical power used to produce cooling
        # at each interval. This is not the same as thermal port flow value.
        # Intermediate helper variable.
        setattr(
            model, self.power_to_cool, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals)
        )

        setattr(
            model,
            self.cooling_cop,
            en.Param(model.Expansion, model.Time, initialize=self.cooling_cop_time_series, domain=en.NonNegativeReals),
        )

    def apply_node_constraints(self, model: EchoConcreteModel):
        # Get variable names for heating and cooling output depending on thermal ports configuration
        self.apply_node_transformation_constraints(model)

    def apply_node_transformation_constraints(self, model: EchoConcreteModel):
        cooling_out = getattr(model, self.ports["output"].port_name)  # cooling delivered at thermal port
        cooling_cop = getattr(model, self.cooling_cop)

        def cooling_output_rule(model: EchoConcreteModel, p, t):
            """Thermal port flow values are positive in cooling mode.
            cooling_out = power_input * cooling cop
            """

            return cooling_out[p, t] == getattr(model, self.ports["input"].port_name)[p, t] * cooling_cop[p, t]

        setattr(
            model, "cool_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=cooling_output_rule)
        )

    def load_cop_values_from_profile(self, model: EchoConcreteModel, profile_df: pd.DataFrame):
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


class ParametrisedChiller(TimeVaryingPiecewiseIONode):
    """A chiller has one electrical input port and one cooling output (thermal sink) port.

    ParametrisedChiller is an input/output piecewise node, with a single set of input/output breakpoints representing
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

    @property
    def temperature_cop_param(self):
        return f"temperature_cop_factor_{self.node_name}"

    def __init__(self, **data):
        super().__init__(**data)
        # A chiller has one electrical input port and one cooling output (thermal sink) port
        self.ports["input"] = FlexSink(units=self.input_port_unit)
        self.ports["output"] = FlexSink(units=self.output_port_unit)
        if self.heat_rejection_port:
            self.ports["heat_rejection"] = FlexSource(units=self.output_port_unit)

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame):
        self.load_temperature_values_from_profile(model, profile)
        self.define_temperature_dependent_cop_coefficient(model)
        self.set_input_points(model)
        self.set_output_points(model)
        super(ParametrisedChiller, self).add_node_to_model(model, profile)
        if "heat_rejection" in self.ports:
            self.add_heat_rejection_constraint(model)

    def define_temperature_dependent_cop_coefficient(self, model: EchoConcreteModel):
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

    def set_input_points(self, model: EchoConcreteModel):
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

    def set_output_points(self, model: EchoConcreteModel):
        """Outputs breakpoints are partial cooling load values (% of max capacity)"""
        self.output_points = {
            (p, t): [k * self.max_cooling_capacity for k in self.partial_load_cop.keys()]
            for p in range(len(model.Expansion))
            for t in range(len(model.Time))
        }

    def add_heat_rejection_constraint(self, model: EchoConcreteModel):
        """Get vari    set_input_pointsables representing port flow values for cooling output (heat in) and
        rejected heat flow, set the constraint."""
        heat_in = getattr(model, self.ports["output"].port_name)
        heat_reject = getattr(model, self.ports["heat_rejection"].port_name)

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

    def load_temperature_values_from_profile(self, model: EchoConcreteModel, profile_df: pd.DataFrame):
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

    def __init__(self, **data):
        super().__init__(**data)

        # TODO: Shall both ports be bi-directional?
        if self.separate_in_out_ports:
            self.ports["input"] = FlexSink(units=self.energy_flow_units)
            self.ports["output"] = FlexSource(units=self.energy_flow_units)
        else:
            self.ports["input_output"] = FlexPort(units=self.energy_flow_units)

        # Initial temperature is not defined set to mid-operation range
        if not self.initial_temp:
            self.initial_temp = self.min_temp + 0.5 * (self.max_temp - self.min_temp)

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
        self.load_values_from_profile(model, profile)
        self.create_and_bound_temp_variable(model)
        self.create_soc_variable(model)
        self.apply_net_loss_and_gain_constraint(model)
        self.apply_energy_balance_constraint(model)
        self.apply_soc_constraint(model)

    def load_values_from_profile(self, model: EchoConcreteModel, profile_df: pd.DataFrame):
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

    def create_and_bound_temp_variable(self, model: EchoConcreteModel):
        # Create temperature variable
        setattr(model, self.internal_temp, en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))
        # Bound temp variable to be within range
        set_float_var_bounds(model=model, var_name=self.internal_temp, ub=self.max_temp, lb=self.min_temp)

    def create_soc_variable(self, model: EchoConcreteModel):
        # Calculate initial state of charge based on the initial internal temperature value
        initial_soc = self.lump_capacitance * (self.initial_temp - self.min_temp) * self.energy_units_conversion
        # Create soc variable and bound it
        setattr(
            model,
            self.soc_value,
            en.Var(model.Expansion, model.Time, initialize=initial_soc, bounds=(0, self.max_heat_storage_capacity)),
        )

    def apply_net_loss_and_gain_constraint(self, model: EchoConcreteModel):
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

    def apply_energy_balance_constraint(self, model: EchoConcreteModel):
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

    def apply_soc_constraint(self, model: EchoConcreteModel):
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


class ThermalPort(FlexPort):
    """Flexible thermal port, +ve if importing heat, -ve if exporting heat."""

    units = Units.KWT


class ParametrisedHeatPump(TimeVaryingPiecewiseIONode):
    """A parametrised heat pump model.


     This model is different to simple heatpump model in that it uses piecewise linear partial load COP factor
     (coefficient of performance) and piecewise linear temperature COP factor to calculate actual values for heating
     and cooling at each step.

     HeatPumpTwoPipe has one input electrical port, and one or two thermal ports.
     If dual_output attribute set to False, only one thermal bidirectional port is created. When one thermal port is
     created the heat pump can do heating or cooling, but not both simultaneously.
     If dual_output attribute set to True, two thermal ports are created cooling_output (thermal Sink) and
     heating_output (thermal Source). When two thermal ports are created the heat pump can do simultaneous heating
     and cooling (4 pipe system) with waste heat recovery from the cooling circuit (when running simultaneously).

     The conversion of input electrical energy to heating or cooling output depends on calculated coefficients of
     performance (COP) at each time step.
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

    dual_output: bool = False
    pass


class SimpleHeatPumpTwoPipe(Node):
    """A simple heat pump model that uses predefined COP (coefficient of performance) values for heating and cooling.

    HeatPumpTwoPipe has one input electrical port, and one or two thermal ports.
    If dual_output attribute set to False, only one thermal bidirectional port is created.
    If dual_output attribute set to True, two thermal ports are created cooling_output (thermal Sink) and heating_output
    (thermal Source).
    It can do heating or cooling, but not both simultaneously.
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

    dual_output: bool = False

    heating_cop_check = validator("heating_cop_time_series", allow_reuse=True)(non_negative_cop_check)
    cooling_cop_check = validator("cooling_cop_time_series", allow_reuse=True)(non_negative_cop_check)

    def __init__(self, **data):
        super().__init__(**data)
        # Create input and output ports
        self.ports["electrical_input"] = FlexSink(units=Units.KW)  # Heat pump has electrical input port
        if self.dual_output:
            self.ports["cooling_output"] = FlexSink(units=Units.KWT)  # Heat pump has one cooling output port
            self.ports["heating_output"] = FlexSource(units=Units.KWT)  # Heat pump has one heating output port
        else:
            self.ports["thermal_output"] = FlexPort(units=Units.KWT)  # Heat pump has one thermal output port

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

    def add_node_to_model(self, model: EchoConcreteModel, profile):
        # Load coefficient of performance values from profile (if be set ref)
        self.load_cop_values_from_profile(model, profile)
        super(SimpleHeatPumpTwoPipe, self).add_node_to_model(model, profile)
        # Set up Ports
        if self.dual_output:
            # Split cooling output port into +ve and -ve components. +ve component will be cooling,
            # -ve component will be heating
            self.ports["cooling_output"].constrain_pos_neg(model)
            set_float_var_bounds(model, self.ports["cooling_output"].port_name, lb=self.max_cooling_capacity)
            set_float_var_bounds(model, self.ports["heating_output"].port_name, ub=self.max_heating_capacity)
        else:
            # Split output port into +ve and -ve components. +ve component will be cooling,
            # -ve component will be heating
            self.ports["thermal_input_output"].constrain_pos_neg(model)
            set_float_var_bounds(
                model,
                self.ports["thermal_input_output"].port_name,
                ub=self.max_heating_capacity,
                lb=self.max_cooling_capacity,
            )

        # Create internal variables representing amount of electrical power used to produce heating or cooling
        # at each interval. Both variables are non-negative, this is not the same as thermal port flow value.
        # Intermediate helper variables.
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

    def apply_node_constraints(self, model: EchoConcreteModel):
        # Get variable names for heating and cooling output depending on thermal ports configuration
        if self.dual_output:
            h_out_var = self.ports["heating_output"].port_name
            c_out_var = self.ports["cooling_output"].port_name
        else:
            h_out_var = self.ports["thermal_output"].is_neg
            c_out_var = self.ports["thermal_output"].is_pos
        # Apply heating_cooling constrains and transformation constraint
        self.apply_only_heat_or_cool_constraints(model, binary_var_name=c_out_var)
        self.apply_node_transformation_constraints(model, heating_out_var=h_out_var, cooling_out_var=c_out_var)

    def load_cop_values_from_profile(self, model: EchoConcreteModel, profile_df: pd.DataFrame):
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

    def apply_only_heat_or_cool_constraints(self, model: EchoConcreteModel, binary_var_name: str):
        is_cooling = getattr(model, binary_var_name)  # binary var for whether we are cooling
        power_in = getattr(model, self.ports["electrical_input"].port_name)  # input electrical power

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

    def apply_node_transformation_constraints(
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

    def get_heating_cop(self, optimiser):
        """Returns the heating cop (coefficient of performance)"""
        _out = optimiser.values(self.ports["thermal_input_output"].pos)
        _in = optimiser.values(self.power_to_heat)
        return _out / _in

    def get_cooling_cop(self, optimiser):
        """Returns the cooling cop (coefficient of performance)"""
        _out = optimiser.values(self.ports["thermal_input_output"].neg)
        _in = optimiser.values(self.power_to_cool)
        return _out / _in


class SimpleHeatPumpFourPipe(SimpleHeatPumpTwoPipe):
    """Four pipe heat pump can do simultaneous heating and cooling."""

    dual_output: bool = True
    waste_heat_recovery_coefficient: float = 1  # Coefficient of the waste heat recovery from the cooling loop in [0, 1]
