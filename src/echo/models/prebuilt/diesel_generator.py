import pyomo.environ as en
from pydantic import NonNegativeFloat
from pyomo.core.expr import EqualityExpression

from echo.configuration import Units
from echo.models.agnostic import FlexSink, InputOutputNode, OffOrConstrainedPort
from echo.models.carbon import CarbonSource
from echo.models.scenario import EchoConcreteModel


class DieselGenerator(InputOutputNode):
    """
    A diesel generator node. Converts diesel into electricity at a fixed rate of cop which is in units of
    kW/liters per second
    """

    input_port_unit = Units.LPS
    output_port_unit = Units.KW
    cop: NonNegativeFloat = 0.4 * 3600  # kW / litres per second
    startup_efficiency: NonNegativeFloat = (
        0.5  # ratio of efficiency in startup and shutdown period, # todo: ensure between 0-1 (confloat??)
    )
    C02Intensity: NonNegativeFloat = 2.7  # emissions intensity kg per sec / litre per sec = kg/litre

    def __init__(self, **data) -> None:
        super().__init__(**data)
        # add an input and output node, and create appropriate transformations
        self.ports["output"] = OffOrConstrainedPort(
            upper_bound=self.min_output, lower_bound=self.max_output, units=self.output_port_unit
        )

        self.ports["input"] = FlexSink(units=self.input_port_unit)  # the node is importing through this port
        self.ports["co2"] = CarbonSource()
        # todo: add some validators :-)

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        super().apply_node_constraints(model)

        def node_constraint(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            p_in = getattr(model, self.ports["input"].port_name)
            p_out = getattr(model, self.ports["output"].port_name)

            if (p == 0) and (t == 0):
                out = p_in[p, t] * self.startup_efficiency * self.cop
            else:
                out = (p_in[p, t] * self.startup_efficiency + p_in[p, t - 1] * (1 - self.startup_efficiency)) * self.cop
            return p_out[p, t] == -out

        def carbon_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            p_in = getattr(model, self.ports["input"].port_name)
            c_out = getattr(model, self.ports["co2"].port_name)
            return c_out[p, t] == -p_in[p, t]

        setattr(model, "node_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=node_constraint))
        setattr(model, "node_con_co2_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=carbon_rule))
