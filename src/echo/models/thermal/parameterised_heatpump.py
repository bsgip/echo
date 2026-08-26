import pandas as pd
import pyomo.environ as en
from pydantic import PositiveFloat
from pyomo.core.expr import EqualityExpression, InequalityExpression
from scipy import interpolate

from echo.configuration import Units
from echo.models.agnostic import FlexPort, FlexSink
from echo.models.base import Node
from echo.models.scenario import EchoConcreteModel
from echo.utils import (
    TimeSeriesData,
    clamp,
    expand_as_dict,
    set_float_var_bounds,
    to_initial_values,
)


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
    def temperature_cop_heating_param(self) -> str:
        return f"temperature_cop_heating_factor_{self.node_name}"

    @property
    def temperature_cop_cooling_param(self) -> str:
        return f"temperature_cop_cooling_factor_{self.node_name}"

    @property
    def power_to_heat(self) -> str:
        return "power_to_heat_" + self.node_name

    @property
    def power_to_cool(self) -> str:
        return "power_to_cool_" + self.node_name

    def __init__(self, **data) -> None:
        super().__init__(**data)
        self.create_ports()

    def update(self, ambient_temperature_dict: dict[float, float]) -> None:
        self.ambient_temperature_dict = ambient_temperature_dict

    def create_ports(self) -> None:
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
        heat_intake_rejection_port: FlexPort | None = None,
    ) -> None:
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

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        """Set up variables and parameters associated with the node"""
        super().add_node_to_model(model, profile)
        self._set_helper_variables(model)
        self._load_temperature_values_from_profile(model, profile)
        self._define_temperature_dependent_cop_coefficient(model)
        self._set_input_points_cooling(model)
        self._set_output_points_cooling(model)
        self._set_input_points_heating(model)
        self._set_output_points_heating(model)
        self._set_var_bounds(model)

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
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

    def _add_heat_intake_rejection_constraint(self, model: EchoConcreteModel) -> None:
        """Get variable representing port flow values for thermal output and
        intake or rejection of heat flow, set the constraint."""
        thermal_output = getattr(model, self.ports[self.thermal_output_port_ref].port_name)
        heat_intake_reject = getattr(model, self.ports[self.heat_intake_rejection_port_ref].port_name)

        def heat_reject_constraint(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
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

    def _set_var_bounds(self, model: EchoConcreteModel) -> None:
        """Set cooling and heating port flow bounds based on the max heating and cooling capacity attribute if given.

        Split output port into non-positive and non-negative components.
        """
        lower_bound = self.max_heating_capacity or model.big_m
        upper_bound = self.max_cooling_capacity or model.big_m
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
        # Split output port into +ve and -ve components. +ve component will be cooling,
        # -ve component will be heating
        self.ports[self.thermal_output_port_ref].constrain_pos_neg(model)

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

    def _define_temperature_dependent_cop_coefficient(self, model: EchoConcreteModel) -> None:
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
        clamped_temp_values_heating = [clamp(v, min_temp_heating, max_temp_heating) for v in temperature_dict.values()]

        cop_scaling_interpolated_heating = interpolate.interp1d(
            temperature_points_heating, cop_points_heating, assume_sorted=False
        )(clamped_temp_values_heating).round(2)
        temperature_cop_dict_heating = {
            k: v for k, v in zip(temperature_dict.keys(), cop_scaling_interpolated_heating, strict=True)
        }

        min_temp_cooling = min(self.temperature_dependent_cop_cooling.keys())
        max_temp_cooling = max(self.temperature_dependent_cop_cooling.keys())
        clamped_temp_values_cooling = [clamp(v, min_temp_cooling, max_temp_cooling) for v in temperature_dict.values()]

        cop_scaling_interpolated_cooling = interpolate.interp1d(
            temperature_points_cooling, cop_points_cooling, assume_sorted=False
        )(clamped_temp_values_cooling).round(2)
        temperature_cop_dict_cooling = {
            k: v for k, v in zip(temperature_dict.keys(), cop_scaling_interpolated_cooling, strict=True)
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
        self,
        model: EchoConcreteModel,
        power_to_cool_var: str,
        cooling_out_var: str,
    ) -> None:
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
        self,
        model: EchoConcreteModel,
        power_to_heat_var: str,
        heating_out_var: str,
    ) -> None:
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

    def _set_input_points_cooling(self, model: EchoConcreteModel) -> None:
        """Input breakpoints are input electrical power values calculated as
        cooling_output/(COP_nominal*partial_load_correction) and scaled by 1/temperature_cop_param value"""

        # get parameter holding temperature dependent COP (coefficient of performance) factor
        temperature_cop_param = getattr(model, self.temperature_cop_cooling_param)

        def input_point(k: float, v: float) -> float:
            if v == 0:
                return 0
            else:
                return k * self.max_cooling_capacity / (v * self.nominal_cooling_cop)

        self.input_points_cooling = {
            (p, t): [input_point(k, v) / temperature_cop_param[p, t] for k, v in self.partial_load_cop_cooling.items()]
            for p in range(len(model.Expansion))
            for t in range(len(model.Time))
        }

    def _set_output_points_cooling(self, model: EchoConcreteModel) -> None:
        """Output breakpoints are partial cooling load values (% of max capacity)"""
        self.output_points_cooling = {
            (p, t): [k * self.max_cooling_capacity for k in self.partial_load_cop_cooling.keys()]
            for p in range(len(model.Expansion))
            for t in range(len(model.Time))
        }

    def _set_input_points_heating(self, model: EchoConcreteModel) -> None:
        """Input breakpoints are input electrical power values calculated as
        heating_output/(COP_nominal*partial_load_correction) and scaled by 1/temperature_cop_param value"""

        # get parameter holding temperature dependent COP (coefficient of performance) factor
        temperature_cop_param = getattr(model, self.temperature_cop_heating_param)

        def input_point(k: float, v: float) -> float:
            if v == 0:
                return 0
            else:
                return k * self.max_heating_capacity / (v * self.nominal_heating_cop)

        self.input_points_heating = {
            (p, t): [input_point(k, v) / temperature_cop_param[p, t] for k, v in self.partial_load_cop_heating.items()]
            for p in range(len(model.Expansion))
            for t in range(len(model.Time))
        }

    def _set_output_points_heating(self, model: EchoConcreteModel) -> None:
        """Output breakpoints are partial heating load values (% of max capacity).

        Need to multiply by -1, heating is negative flow of the thermal port.

        """
        self.output_points_heating = {
            (p, t): [-1 * k * self.max_heating_capacity for k in self.partial_load_cop_heating.keys()]
            for p in range(len(model.Expansion))
            for t in range(len(model.Time))
        }
