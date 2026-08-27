import pandas as pd
import pyomo.environ as en
from pydantic import NegativeFloat, NonNegativeFloat, PositiveFloat, root_validator, validator
from pyomo.core.expr import EqualityExpression

from echo.configuration import FlowConstraint, Units
from echo.models.agnostic import FlexPort, FlexSink, FlexSource
from echo.models.base import Node
from echo.models.scenario import EchoConcreteModel
from echo.utils import (
    set_float_var_bounds,
    to_initial_values,
)


class ThermalStorage(Node):
    """Model of sensible thermal storage with liquid or solid storage medium.

    Thermal storage keeps track of its internal temperature value base. Assumes homogeneous temperature throughout the
    storage volume.
    """

    max_temp: float  # Maximum operational temperature in degrees  Celsius
    min_temp: float  # Minimum operational temperature in degrees  Celsius
    storage_mass: PositiveFloat  # Mass of storage medium in kg
    specific_heat: PositiveFloat  # Specific heat capacity in Joule/kg*C
    charging_power_limit: PositiveFloat = (
        None  # Maximum energy flow into the storage at each interval, in energy_flow_units
    )
    discharging_power_limit: NegativeFloat = (
        None  # Maximum energy flow out of the storage at each interval, in energy_flow_units
    )
    ambient_temp: dict | None = None  # Ambient temp, formatted as dict with expansion-time keys
    ambient_temp_ref: str | None  # Ambient temp by column name reference in profile dataframe
    ins_transmittance: NonNegativeFloat = (
        0  # Thermal transmittance U-value of Thermal Energy Storage insulation in W/sqm*C
    )
    surface_area: NonNegativeFloat = 0  # Surface area of Thermal Energy Storage in square meters, default value=0
    # means zero heat loss/gain
    initial_temp: float = None  # initial internal temperature in degrees  Celsius
    optimised_capacity: bool = False  # If True, set heat storage capacity (size of storage) to be optimisation variable
    enforce_end_temperature_value: bool = True  # If True, the internal temperature value at the end of the
    # last optimisation interval is required to be equal initial value
    energy_flow_units: Units = Units.KWT  # Thermal energy flow units to use, expecting KW Thermal or JPS
    separate_in_out_ports: bool = False  # Create two thermal ports charge and discharge, else 1 two-way port

    input_port_ref: str = "input"
    output_port_ref: str = "output"
    input_output_port_ref: str = "input_output"

    def __init__(self, **data) -> None:
        super().__init__(**data)

        if self.separate_in_out_ports:
            self.ports[self.input_port_ref] = FlexSink(units=self.energy_flow_units)
            self.ports[self.output_port_ref] = FlexSource(units=self.energy_flow_units)
            # Set flow constraints if defined
            self.set_flow_constraints_separate_ports()
        else:
            self.ports[self.input_output_port_ref] = FlexPort(units=self.energy_flow_units)
            # Set flow constraints if defined
            self.set_flow_constraints_one_port()

        # Initial temperature is not defined set to mid-operation range
        if not self.initial_temp:
            self.initial_temp = self.min_temp + 0.5 * (self.max_temp - self.min_temp)

    def set_flow_constraints_separate_ports(self) -> None:
        if self.charging_power_limit:
            self.ports[self.input_port_ref].import_constraint = FlowConstraint.Fixed
            self.ports[self.input_port_ref].import_constraint_value = self.charging_power_limit
        if self.discharging_power_limit:
            self.ports[self.input_port_ref].export_constraint = FlowConstraint.Fixed
            self.ports[self.input_port_ref].export_constraint_value = self.discharging_power_limit

    def set_flow_constraints_one_port(self) -> None:
        if self.charging_power_limit:
            self.ports[self.input_output_port_ref].import_constraint = FlowConstraint.Fixed
            self.ports[self.input_output_port_ref].import_constraint_value = self.charging_power_limit
        if self.discharging_power_limit:
            self.ports[self.input_output_port_ref].export_constraint = FlowConstraint.Fixed
            self.ports[self.input_output_port_ref].export_constraint_value = self.discharging_power_limit

    def update(self, ambient_temp: dict[tuple[int, int], float]) -> None:
        self.ambient_temp = ambient_temp

    def set_ports(self, input_port: FlexSink, output_port: FlexSource) -> None:
        """Replaces any existing ports with separate input and output ports"""
        # Discard existing ports
        self.ports.clear()

        # Add the new ports
        self.input_port_ref = input_port.port_name
        self.output_port_ref = output_port.port_name
        self.ports[self.input_port_ref] = input_port
        self.ports[self.output_port_ref] = output_port
        if self.charging_power_limit:
            self.ports[self.input_port_ref].import_constraint = FlowConstraint.Fixed
            self.ports[self.input_port_ref].import_constraint_value = self.charging_power_limit
        if self.discharging_power_limit:
            self.ports[self.input_port_ref].export_constraint = FlowConstraint.Fixed
            self.ports[self.input_port_ref].export_constraint_value = self.discharging_power_limit

    def set_port(self, input_output_port: FlexPort) -> None:
        """Replaces any existing ports with a combined input output port"""
        # Discard existing ports
        self.ports.clear()

        # Add new port
        self.input_output_port_ref = input_output_port.port_name
        self.ports[self.input_output_port_ref] = input_output_port
        if self.charging_power_limit:
            self.ports[self.input_output_port_ref].import_constraint = FlowConstraint.Fixed
            self.ports[self.input_output_port_ref].import_constraint_value = self.charging_power_limit
        if self.discharging_power_limit:
            self.ports[self.input_output_port_ref].export_constraint = FlowConstraint.Fixed
            self.ports[self.input_output_port_ref].export_constraint_value = self.discharging_power_limit

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
    def internal_temp(self) -> str:
        return "internal_temp_" + self.node_name

    @property
    def net_loss_gain(self) -> str:
        return "net_loss_gain_" + self.node_name

    @property
    def soc_value(self) -> str:
        return "storage_soc_" + self.node_name

    @property
    def soc_constraint(self) -> str:
        return "soc_cons_" + self.node_name

    @property
    def lump_capacitance(self) -> float:
        return self.storage_mass * self.specific_heat

    @property
    def lump_conductance(self) -> float:
        return self.ins_transmittance * self.surface_area

    @property
    def energy_units_conversion(self) -> float:
        if self.energy_flow_units == Units.KWT:
            # If ports flow in KWT calculate energy in KWTh
            return 1 / 3600000
        else:
            # If ports flow in JPS calculate energy in Joules
            return 1

    @property
    def max_heat_storage_capacity(self) -> float:
        return self.lump_capacitance * (self.max_temp - self.min_temp) * self.energy_units_conversion

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_node_to_model(model, profile)
        self._load_values_from_profile(model, profile)
        self._create_and_bound_temp_variable(model)
        self._create_soc_variable(model)
        self._apply_net_loss_and_gain_constraint(model)
        self._apply_energy_balance_constraint(model)
        self._apply_soc_constraint(model)
        if self.enforce_end_temperature_value:
            self._apply_final_temperature_constraint(model)

    def _load_values_from_profile(self, model: EchoConcreteModel, profile_df: pd.DataFrame) -> None:
        """For all attributes set by str reference, load values from profile."""
        if self.ambient_temp_ref:
            if self.ambient_temp_ref not in profile_df.columns:
                raise ValueError(
                    f"Could find reference column name {self.ambient_temp_ref} for ambient temperature in the profile."
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

    def _create_and_bound_temp_variable(self, model: EchoConcreteModel) -> None:
        # Create temperature variable
        setattr(
            model,
            self.internal_temp,
            en.Var(model.Expansion, model.Time, initialize=self.initial_temp, domain=en.NonNegativeReals),
        )
        # Bound temp variable to be within range
        set_float_var_bounds(model=model, var_name=self.internal_temp, ub=self.max_temp, lb=self.min_temp)

    def _create_soc_variable(self, model: EchoConcreteModel) -> None:
        # Calculate initial state of charge based on the initial internal temperature value
        initial_soc = self.lump_capacitance * (self.initial_temp - self.min_temp) * self.energy_units_conversion
        # Create soc variable and bound it
        setattr(
            model,
            self.soc_value,
            en.Var(model.Expansion, model.Time, initialize=initial_soc, bounds=(0, self.max_heat_storage_capacity)),
        )

    def _apply_net_loss_and_gain_constraint(self, model: EchoConcreteModel) -> None:
        # Create variable for net losses and gains
        setattr(model, self.net_loss_gain, en.Var(model.Expansion, model.Time, domain=en.Reals))

        # Apply constraints on loss and gain variables
        def net_loss_gain_constraint(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
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

    def _apply_energy_balance_constraint(self, model: EchoConcreteModel) -> None:
        # Constraint relating internal, ambient temp, heat in, heat out, losses, and gains
        dt_sec = model.scenario_settings.interval_duration * 60
        max_t = len(model.Time) - 1
        if self.energy_flow_units == Units.KWT:
            # If ports flow in KWT transform to Joules
            flow_units_scaler = 1000
        elif self.energy_flow_units == Units.JPS:
            # If ports flow in JPS calculate losses in JPS
            flow_units_scaler = 1

        def change_of_internal_temperature_constraint(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
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

    def _apply_final_temperature_constraint(self, model: EchoConcreteModel) -> None:
        # Storage internal temperature at the last optimisation interval must equal initial temperature
        max_t = len(model.Time) - 1
        internal_temperature = getattr(model, self.internal_temp)

        def final_temperature_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            if t == max_t:
                return internal_temperature[p, t] == self.initial_temp
            else:
                return internal_temperature[p, t] >= self.min_temp

        setattr(
            model,
            "final_temp_con_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=final_temperature_rule),
        )

    def _apply_soc_constraint(self, model: EchoConcreteModel) -> None:
        # State of charge in Joule or KWTh is a linear function of the internal temperature
        soc = getattr(model, self.soc_value)
        internal_temperature = getattr(model, self.internal_temp)

        def soc_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            return (
                soc[p, t]
                == self.lump_capacitance * (internal_temperature[p, t] - self.min_temp) * self.energy_units_conversion
            )

        setattr(model, "SOC_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=soc_rule))
