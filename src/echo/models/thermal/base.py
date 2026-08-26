import pandas as pd
import pyomo.environ as en
from pydantic import NonNegativeFloat, PositiveFloat
from pyomo.core.expr import EqualityExpression, InequalityExpression

from echo.models.base import Node
from echo.models.scenario import EchoConcreteModel
from echo.utils import set_var_bounds_from_dict


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

    def __init__(self, **data) -> None:
        super().__init__(**data)
        self.internal_temp = "internal_temp_" + self.node_name
        self.is_gain = "is_gain_" + self.node_name
        self.losses = "losses_" + self.node_name
        self.gains = "gains_" + self.node_name

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_node_to_model(model, profile)
        self.create_and_bound_temp_vars(model)
        self.loss_and_gain_constraints_and_variables(model)
        self.apply_energy_balance_constraint(model)

    def create_and_bound_temp_vars(self, model: EchoConcreteModel) -> None:
        # Create temperature variable
        setattr(model, self.internal_temp, en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))
        # Bound temp variable to be within range
        set_var_bounds_from_dict(model=model, var_name=self.internal_temp, ub=self.temp_ub, lb=self.temp_lb)

    def loss_and_gain_constraints_and_variables(self, model: EchoConcreteModel) -> None:
        # Create variable for losses and gains
        setattr(model, self.losses, en.Var(model.Expansion, model.Time, domain=en.NonPositiveReals))
        setattr(model, self.gains, en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))
        setattr(model, self.is_gain, en.Var(model.Expansion, model.Time, domain=en.Binary))

        # Apply constraints on loss and gain variables
        def loss_gain_sum_constraint(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
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

        def loss_or_gain1(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            """Gains can only be non-zero if is_gain = 1"""
            return getattr(model, self.gains)[p, t] <= getattr(model, self.is_gain)[p, t] * model.big_m

        setattr(
            model, "loss_gain_con2_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=loss_or_gain1)
        )

        def loss_or_gain2(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            """Losses can only be non-zero if is_gain = 0"""
            return getattr(model, self.losses)[p, t] >= (getattr(model, self.is_gain)[p, t] - 1) * model.big_m

        setattr(
            model, "loss_gain_con3_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=loss_or_gain2)
        )

    def apply_energy_balance_constraint(self, model: EchoConcreteModel) -> None:
        # Constraint relating internal, ambient temp, heat in, heat out, losses, and gains
        def rule1(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
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
