import pandas as pd
import pyomo.environ as en
from pydantic import NonNegativeFloat
from pyomo.core.expr import EqualityExpression, InequalityExpression

from echo.configuration import Units
from echo.models.agnostic import FlexSink, FlexSource
from echo.models.scenario import EchoConcreteModel
from echo.models.thermal.simple_heatpump import SimpleHeatPump
from echo.utils import (
    set_float_var_bounds,
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

    def __init__(self, **data) -> None:
        super().__init__(**data)
        # Create input and output ports: electrical input port, cooling output port and heating output port
        self.create_ports()

    @property
    def heating_out_adjusted(self) -> str:
        """heating_out_adjusted variable represents amount of heat that is produced running the primary heating loop."""
        return "heating_out_adjusted_" + self.node_name

    @property
    def delta_heat_flow(self) -> str:
        return f"delta_heat_flow_{self.node_name}"

    @property
    def recovered_waste_heat(self) -> str:
        return f"recovered_waste_heat_{self.node_name}"

    def create_ports(self) -> None:
        # Create input and output ports
        self.ports[self.electrical_input_port_ref] = FlexSink(units=Units.KW)  # Heat pump has electrical input port
        self.ports[self.cooling_output_port_ref] = FlexSink(units=Units.KWT)  # Heat pump has one cooling output port
        self.ports[self.heating_output_port_ref] = FlexSource(units=Units.KWT)  # Heat pump has one heating output port

    def set_ports(
        self, electrical_input_port: FlexSink, cooling_output_port: FlexSink, heating_output_port: FlexSource
    ) -> None:
        # Discard existing ports
        self.ports.clear()

        # Add the new ports
        self.electrical_input_port_ref = electrical_input_port.port_name
        self.cooling_output_port_ref = cooling_output_port.port_name
        self.heating_output_port_ref = heating_output_port.port_name
        self.ports[self.electrical_input_port_ref] = electrical_input_port
        self.ports[self.cooling_output_port_ref] = cooling_output_port.port_name
        self.ports[self.heating_output_port_ref] = heating_output_port.port_name

    def _set_ports_var_bounds(self, model: EchoConcreteModel) -> None:
        """Set cooling and heating port flow bounds based on the max heating and cooling capacity attribute if given."""

        lower_bound = self.max_heating_capacity or model.big_m
        upper_bound = self.max_cooling_capacity or model.big_m
        set_float_var_bounds(model, self.ports[self.cooling_output_port_ref].port_name, ub=upper_bound, lb=0)
        set_float_var_bounds(model, self.ports[self.heating_output_port_ref].port_name, ub=0, lb=-1 * lower_bound)

    def _create_heat_recovery_vars(self, model: EchoConcreteModel) -> None:
        """Create variable for adjusted heat_output supplied by the heating loop"""

        setattr(model, self.heating_out_adjusted, en.Var(model.Expansion, model.Time, domain=en.NonPositiveReals))
        setattr(model, self.recovered_waste_heat, en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        # Use parent class method
        super().add_node_to_model(model, profile)
        self._create_heat_recovery_vars(model)
        self._create_delta_heat_flow_vars(model)

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        # Get variable names for heating and cooling output depending on thermal ports configuration
        h_out_adjusted_var = self.heating_out_adjusted
        c_out_var = self.ports[self.cooling_output_port_ref].port_name
        # Apply heating_cooling constraints and transformation constraint
        self._apply_heat_recovery_constraints(model)
        self._apply_node_transformation_constraints(
            model, heating_out_var=h_out_adjusted_var, cooling_out_var=c_out_var
        )

    def _create_delta_heat_flow_vars(self, model: EchoConcreteModel) -> None:
        """Create a delta heat flow variable, split in pos and negative components"""
        setattr(model, self.delta_heat_flow, en.Var(model.Expansion, model.Time, domain=en.Reals))
        setattr(model, f"{self.delta_heat_flow}_pos", en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))
        setattr(model, f"{self.delta_heat_flow}_neg", en.Var(model.Expansion, model.Time, domain=en.NonPositiveReals))
        setattr(model, f"{self.delta_heat_flow}_is_pos", en.Var(model.Expansion, model.Time, domain=en.Binary))

        def total_sum_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
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

        def is_pos_rule(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            """Positive value constraint"""
            return (
                getattr(model, f"delta_heat_flow_{self.node_name}_pos")[p, t]
                <= getattr(model, f"delta_heat_flow_{self.node_name}_is_pos")[p, t] * model.big_m
            )

        setattr(
            model, "is_pos_delta_rule_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=is_pos_rule)
        )

        def is_neg_rule(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            """positive and negative component sum"""
            return (
                getattr(model, f"delta_heat_flow_{self.node_name}_neg")[p, t]
                >= (getattr(model, f"delta_heat_flow_{self.node_name}_is_pos")[p, t] - 1) * model.big_m
            )

        setattr(
            model, "is_neg_delta_rule_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=is_neg_rule)
        )

    def _apply_heat_recovery_constraints(self, model: EchoConcreteModel) -> None:
        power_in = getattr(model, self.ports[self.electrical_input_port_ref].port_name)  # input electrical power
        h_out_var = getattr(model, self.ports[self.heating_output_port_ref].port_name)
        c_out_var = getattr(model, self.ports[self.cooling_output_port_ref].port_name)
        h_out_adjusted_var = getattr(model, self.heating_out_adjusted)
        delta_heat_flow = getattr(model, self.delta_heat_flow)
        delta_heat_flow_neg = getattr(model, f"{self.delta_heat_flow}_neg")
        waste_heat_var = getattr(model, self.recovered_waste_heat)

        def delta_heat_flow_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            """Delta heat flow between cooling and heating circuits"""
            return delta_heat_flow[p, t] == h_out_var[p, t] + self.waste_heat_recovery_coeff * c_out_var[p, t]

        setattr(
            model,
            "delta_heat_flow_rule_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=delta_heat_flow_rule),
        )

        def adjusted_heat_value_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
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

        def recovered_heat_value_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            """Track amount of recovered waste heat"""
            return waste_heat_var[p, t] == -1 * h_out_var[p, t] + delta_heat_flow_neg[p, t]

        setattr(
            model,
            "recovered_heat_value_" + self.node_name,
            en.Constraint(model.Expansion, model.Time, rule=recovered_heat_value_rule),
        )

        def sum_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            """Electrical power input used for heating and for cooling must sum to total electrical power input"""
            return power_in[p, t] == getattr(model, self.power_to_heat)[p, t] + getattr(model, self.power_to_cool)[p, t]

        setattr(model, "sum_heat_cool_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=sum_rule))
