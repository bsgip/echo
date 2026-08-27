import pandas as pd
import pyomo.environ as en
from pydantic import root_validator
from pyomo.core.expr import EqualityExpression

from echo.configuration import Units
from echo.models.agnostic import InputOutputNode, OffOrConstrainedPort
from echo.models.scenario import EchoConcreteModel
from echo.validators import (
    set_output_bounds_from_input_bounds_and_cop_and_startup_cop,
    validate_startup_efficiency,
)


class TempControlledBoiler(InputOutputNode):
    """
    A temp controlled boiler has an input and output port.
    It has two internal temperature variables, one for exiting water temp and one for returning water temp.
    """

    input_port_unit = Units.JPS
    output_port_unit = Units.KWT
    max_input: float
    min_input: float
    exit_temp_bounds: tuple = (75, 80)
    return_temp_bounds: tuple = (50, 80)
    deg_to_kw: float  # factor for converting a temperature difference to kW required to achieve that delta T
    cop: float  # coefficient of performance - determines how much of the input energy is delivered as heating energy
    startup_cop: float | None

    # pyomo vars
    is_on: str | None
    return_t: str = ""
    exit_t: str = ""

    check_eta = root_validator(allow_reuse=True)(validate_startup_efficiency)
    set_output_bounds = root_validator(allow_reuse=True)(set_output_bounds_from_input_bounds_and_cop_and_startup_cop)

    def __init__(self, **data) -> None:
        super().__init__(**data)
        self.ports[self.input_port_ref] = OffOrConstrainedPort(
            units=self.input_port_unit, lower_bound=self.min_input, upper_bound=self.max_input
        )
        self.ports[self.output_port_ref] = OffOrConstrainedPort(
            units=self.output_port_unit, lower_bound=self.max_output, upper_bound=self.min_output
        )

        self.return_t = "inlet_temp_" + self.node_name
        self.exit_t = "outlet_temp_" + self.node_name

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_node_to_model(model, profile)
        # Define exit and return temperature variables and bound these appropriately
        setattr(
            model,
            self.return_t,
            en.Var(model.Expansion, model.Time, initialize=0, bounds=self.return_temp_bounds, domain=en.Reals),
        )
        setattr(
            model,
            self.exit_t,
            en.Var(model.Expansion, model.Time, initialize=0, bounds=self.exit_temp_bounds, domain=en.Reals),
        )

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        # Retrieve some variables
        input_kw = getattr(model, self.ports[self.input_port_ref].port_name)
        output_kw = getattr(model, self.ports[self.output_port_ref].port_name)

        def constraint2(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            """return temp at time t - exiting temp at time t == energy removed at t"""
            return (
                getattr(model, self.return_t)[p, t] - getattr(model, self.exit_t)[p, t]
            ) * self.deg_to_kw * self.cop == output_kw[p, t]

        setattr(
            model, "boiler_temp_con2_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=constraint2)
        )

        def constraint3(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            """exiting temp at time t = return temp at time t + energy added at time t"""
            return (
                input_kw[p, t]
                == (getattr(model, self.exit_t)[p, t] - getattr(model, self.return_t)[p, t]) * self.deg_to_kw
            )

        setattr(
            model, "boiler_temp_con3_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=constraint3)
        )
