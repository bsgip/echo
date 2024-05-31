from typing import Optional

import pandas as pd
from pydantic import root_validator, validator

import numpy as np
import pyomo.environ as en

from echo.configuration import Units
from echo.exceptions import validate
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
)
from echo.validators import ArrayType, validate_partial_load_cop, validate_temp_dependent_cop


class Chiller(TimeVaryingPiecewiseIONode):
    """A chiller has one electrical input port and one cooling output (thermal sink) port.

    A simple chiller is an input/output piecewise node, with a single set of input/output breakpoints representing
    chiller COP used for all time periods.
    """

    nominal_cop: float  # Nominal coefficient of performance COP = output/input
    max_cooling_capacity: float  # Maximum cooling output in KWT (1RT ~ 3.5KWT)
    partial_load_cop: dict = {0: 0, 0.25: 0.8, 0.5: 0.9, 0.75: 1, 1: 0.85}
    temp_dependent_cop: dict = {0: 0.7, 10: 1, 20: 0.5, 30: 0.35, 45: 0.2}
    ambient_temp_dict: dict = (
        None  # Condenser side temperature, ambient air temp or condenser water temp for water cooled chiller
    )
    ambient_temp_ref: str = None
    input_port_unit: Units = Units.KW
    output_port_unit: Units = Units.KWT
    heat_rejection_port: bool = False
    heat_rejection_coeff: float = 1

    pl_cop_check = root_validator(allow_reuse=True)(validate_partial_load_cop)
    temp_cop_check = root_validator(allow_reuse=True)(validate_temp_dependent_cop)

    @property
    def temp_cop_param(self):
        return f"temperature_cop_factor_{self.node_name}"

    def __init__(self, **data):
        super().__init__(**data)
        # A chiller has one electrical input port and one cooling output (thermal sink) port
        self.ports["input"] = FlexSink(units=self.input_port_unit)
        self.ports["output"] = FlexSink(units=self.output_port_unit)
        if self.heat_rejection_port:
            self.ports["heat_rejection"] = FlexSource(units=self.output_port_unit)

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame):
        self.load_tem_values_from_profile(model, profile)
        self.define_temp_dependent_cop_coefficient(model)
        self.set_input_output_pts(model)
        super(Chiller, self).add_node_to_model(model, profile)
        if "heat_rejection" in self.ports:
            self.add_heat_rejection_constraint(model)

    def define_temp_dependent_cop_coefficient(self, model: EchoConcreteModel):
        """Get COP scaler for each interval.

        Calculate value of the temp_cop_factor parameter using numpy linear interpolation function.
        """

        temp_points = list(self.temp_dependent_cop.keys())
        cop_points = list(self.temp_dependent_cop.values())

        if self.ambient_temp_dict:
            temp_dict = self.ambient_temp_dict
        else:
            # Set default amb temp value to 10 >> no change to nominal COP
            temp_dict = expand_as_dict(
                TimeSeriesData(value=10, num_time_intervals=len(model.Time), num_expansion_intervals=1)
            )

        def value_or_bound(temp_val):
            if temp_val >= max(self.temp_dependent_cop.keys()):
                return max(self.temp_dependent_cop.keys())
            elif temp_val <= min(self.temp_dependent_cop.keys()):
                return min(self.temp_dependent_cop.keys())
            else:
                return temp_val

        # Use numpy linear interpolation function to get temp cop factor from temp dictionary
        temp_cop_dict = {k: np.interp(value_or_bound(v), temp_points, cop_points) for k, v in temp_dict.items()}

        # Create a parameter holding ambient/condenser temperature dictionary (defaulting to 10 degrees)
        setattr(
            model,
            self.temp_cop_param,
            en.Param(model.Expansion, model.Time, initialize=temp_cop_dict, domain=en.Reals),
        )

    def set_input_output_pts(self, model: EchoConcreteModel):
        # get parameter holding temperature dependent COP factor
        temp_cop_param = getattr(model, self.temp_cop_param)

        # Input breakpoints are input electrical power values calculated as cooling_output/(COP*partial_load_correction)
        # and scaled by 1/temp_cop_param value
        def input_point(k, v):
            if v == 0:
                return 0
            else:
                return k * self.max_cooling_capacity / (v * self.nominal_cop)

        self.input_pts = {
            (p, t): [input_point(k, v) / temp_cop_param[p, t] for k, v in self.partial_load_cop.items()]
            for p in range(len(model.Expansion))
            for t in range(len(model.Time))
        }

        # Outputs breakpoints are partial cooling load values (% of max capacity)
        self.output_pts = {
            (p, t): [k * self.max_cooling_capacity for k in self.partial_load_cop.keys()]
            for p in range(len(model.Expansion))
            for t in range(len(model.Time))
        }

    def add_heat_rejection_constraint(self, model: EchoConcreteModel):
        """Get variables representing port flow values for cooling output (heat in) and
        rejected heat flow, set the constraint."""
        heat_in = getattr(model, self.ports["output"].port_name)
        heat_reject = getattr(model, self.ports["heat_rejection"].port_name)

        def heat_reject_constraint(model: EchoConcreteModel, p, t):
            """Amount of rejected heat at each interval equals amount of cooling delivered (heat in) multiplied by
            heat rejection coefficient
            """
            return heat_reject[p, t] == -heat_in[p, t] * self.heat_rejection_coeff

        setattr(
            model,
            "heat_rejection_constraint_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=heat_reject_constraint),
        )

    def load_tem_values_from_profile(self, model: EchoConcreteModel, profile_df: pd.DataFrame):
        """For all attributes set by str reference, load values from profile."""
        if self.ambient_temp_ref and self.ambient_temp_ref in profile_df.columns:
            self.ambient_temp_dict = to_initial_values(
                profile_df,
                key=self.ambient_temp_ref,
                time_periods=len(model.Time),
                expansion_periods=len(model.Expansion),
            )
        elif self.ambient_temp_ref and self.ambient_temp_ref not in profile_df.columns:
            raise ValueError(f"Could find reference column name {self.ambient_temp_ref} in the profile.")
        else:
            pass


class ThermalNode(Node):
    """
    A thermal node has an internal temperature variable, which can be bounded.
    It can have any number of ports for heating (importing) or cooling (export).
    All the ports are related to temp by an energy balance constraint.
    """

    temp_ub: dict  # Upper bound of acceptable temperature for each time interval: dict with expansion-time keys
    temp_lb: dict  # Lower bound of acceptable temperature for each time interval: dict with expansion-time keys
    external_temp: dict  # External (ambient) temp, formatted as dict with expansion-time keys
    loss_factor: float = 0  # Losses due to ambient temp being lower than internal temp
    gain_factor: float = 0  # Free gains due to ambient temp being higher than internal temp
    temp_to_energy_coef: float = 1  # Conversion factor * temp change = added energy
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
    TES volume.
    """

    max_temp: float  # Maximum operational temperature in degrees  Celsius
    min_temp: float  # Minimum operational temperature in degrees  Celsius
    storage_mass: float  # Mass of storage medium in kg
    specific_heat: float  # Specific heat capacity in Joule/kg*C
    ambient_temp: dict = None  # Ambient temp, formatted as dict with expansion-time keys
    ambient_temp_ref: Optional[str]  # Ambient temp by column name reference in profile dataframe
    ins_transmittance: float = 0  # Thermal transmittance U-value of TES insulation in W/sqm*C
    surface_area: float = 0  # Surface area of TES in square meters, default value=0 means zero heat loss/gain
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
        """Temperature range must be non-zero and positive for TES to be operational"""
        if "max_temp" in values and "min_temp" in values and values["max_temp"] - values["min_temp"] <= 0:
            raise ValueError(
                "Temperature range must be non-zero and positive for TES to be operational."
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
        if self.ambient_temp_ref and self.ambient_temp_ref in profile_df.columns:
            self.ambient_temp = to_initial_values(
                profile_df,
                key=self.ambient_temp_ref,
                time_periods=len(model.Time),
                expansion_periods=len(model.Expansion),
            )
        elif self.ambient_temp_ref and self.ambient_temp_ref not in profile_df.columns:
            raise ValueError(
                f"Could find reference column name {self.ambient_temp_ref} " "for ambient temperature in the profile."
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


class HeatPump(Node):
    """
    A heat pump is input output node, where input is an electrical port, and either one or two output thermal ports.
    It can only do heating or cooling, it cannot do both simultaneously.
    The conversion of input electrical energy to heating or cooling output depends on provided coefficients of
    performance (cop) time series data.
    """

    heating_cop_time_series: dict  # Formatted dict of heating COPs per time period
    cooling_cop_time_series: dict  # Formatted dict of cooling COPs per time period

    def __init__(self, **data):
        super().__init__(**data)
        # Create input and output ports
        self.ports["input"] = FlexSink(units=Units.KW)  # Heat pump has electrical input port

        # Naming variables

    @property
    def heating_cop(self):
        return "heating_cop_" + self.node_name

    @property
    def cooling_cop(self):
        return "cooling_cop_" + self.node_name

    @property
    def heat_in(self):
        return "heat_in_" + self.node_name

    @property
    def cool_in(self):
        return "cool_in_" + self.node_name

    def add_node_to_model(self, model: EchoConcreteModel, profile):
        super(HeatPump, self).add_node_to_model(model, profile)

        # Create variables for attributing the input to either heating or cooling
        setattr(model, self.heat_in, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
        setattr(model, self.cool_in, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))

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

    def apply_only_heat_or_cool_constraints(self, model: EchoConcreteModel, binary_var):
        is_cooling = getattr(model, binary_var)  # binary var for whether we are cooling
        p_in = getattr(model, self.ports["input"].port_name)  # input electrical power

        def only_heat_or_cool1(model: EchoConcreteModel, p, t):
            """Can only have input used for heating if is_cooling = 0"""
            return getattr(model, self.heat_in)[p, t] <= (1 - is_cooling[p, t]) * model.bigM

        setattr(
            model,
            "only_heat_or_cool1_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=only_heat_or_cool1),
        )

        def only_heat_or_cool2(model: EchoConcreteModel, p, t):
            """Can only have input used for cooling if is_cooling = 1"""
            return getattr(model, self.cool_in)[p, t] <= is_cooling[p, t] * model.bigM

        setattr(
            model,
            "only_heat_or_cool2_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=only_heat_or_cool2),
        )

        def sum_rule(model: EchoConcreteModel, p, t):
            """Input used for heating and input used for cooling must sum to total input"""
            return p_in[p, t] == getattr(model, self.heat_in)[p, t] + getattr(model, self.cool_in)[p, t]

        setattr(model, "sum_heat_cool_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=sum_rule))

    def apply_node_transformation_constraints(self, model: EchoConcreteModel, heating_out_var, cooling_out_var):
        heat_out = getattr(model, heating_out_var)  # heating delivered
        cool_out = getattr(model, cooling_out_var)  # cooling delivered
        heating_cop = getattr(model, self.heating_cop)
        cooling_cop = getattr(model, self.cooling_cop)

        def heating_output_rule(model: EchoConcreteModel, p, t):
            """Heat out = heat_in * heating cop * -1"""
            return heat_out[p, t] == getattr(model, self.heat_in)[p, t] * heating_cop[p, t] * -1

        def cooling_output_rule(model: EchoConcreteModel, p, t):
            """Cool out = cool_in * cooling cop"""
            return cool_out[p, t] == getattr(model, self.cool_in)[p, t] * cooling_cop[p, t]

        setattr(
            model, "heat_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=heating_output_rule)
        )
        setattr(
            model, "cool_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=cooling_output_rule)
        )

    def get_heating_cop(self, optimiser):
        """Returns the heating cop"""
        _out = optimiser.values(self.ports["output"].pos)
        _in = optimiser.values(self.heat_in)
        return _out / _in

    def get_cooling_cop(self, optimiser):
        """Returns the cooling cop"""
        _out = optimiser.values(self.ports["output"].neg)
        _in = optimiser.values(self.cool_in)
        return _out / _in


class HeatPumpSingleOutput(HeatPump):
    """
    Heat pump with a single output port for bidirectional heating/cooling.
    Can be used to connect to a thermal load that has heating and cooling.
    """

    def __init__(self, **data):
        super().__init__(**data)
        # Create output port
        self.ports["output"] = FlexPort(units=Units.KWT)

    def add_node_to_model(self, model: EchoConcreteModel, profile):
        super(HeatPumpSingleOutput, self).add_node_to_model(model, profile)
        # Split output port into +ve and -ve components. +ve component will be cooling, -ve component will be heating
        self.ports["output"].constrain_pos_neg(model)

    def apply_node_constraints(self, model: EchoConcreteModel):
        p_out = self.ports["output"]
        self.apply_only_heat_or_cool_constraints(model, binary_var=p_out.is_pos)
        self.apply_node_transformation_constraints(model, heating_out_var=p_out.neg, cooling_out_var=p_out.pos)


class HeatPumpDualOutput(HeatPump):
    """
    Heat pump with separate output ports for heating and cooling.
    Can be used to connect to separate heating and cooling nodes.
    """

    def __init__(self, **data):
        super().__init__(**data)
        # Create output port
        self.ports["heating"] = FlexSource(units=Units.KWT)
        self.ports["cooling"] = FlexSink(units=Units.KWT)

    def add_node_to_model(self, model: EchoConcreteModel, profile):
        super(HeatPumpDualOutput, self).add_node_to_model(model, profile)
        self.ports["cooling"].constrain_pos_neg(
            model
        )  # need to do this so we have a binary variable for the constraints

    def apply_node_constraints(self, model: EchoConcreteModel):
        h_out = self.ports["heating"]
        c_out = self.ports["cooling"]
        self.apply_only_heat_or_cool_constraints(model, binary_var=c_out.is_pos)
        self.apply_node_transformation_constraints(
            model, heating_out_var=h_out.port_name, cooling_out_var=c_out.port_name
        )
