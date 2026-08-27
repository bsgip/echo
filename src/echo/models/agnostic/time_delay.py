import pyomo.environ as en
from pyomo.core.expr import InequalityExpression

from echo.models.agnostic.flex import FlexSink, FlexSource
from echo.models.agnostic.input_output import InputOutputNode
from echo.models.scenario import EchoConcreteModel


class TimeDelayNode(InputOutputNode):
    """A time delay node is an input-output node that implements a fixed delay between input and output."""

    time_delay: int  # number of time intervals delay between input and output

    def __init__(self, **data) -> None:
        super().__init__(**data)
        self.ports["input"] = FlexSink(units=self.input_port_unit)
        self.ports["output"] = FlexSource(units=self.output_port_unit)

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        def time_delay_rule(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            """This is a modified tellegen rule, where the sum=0 applies over staggered time periods according to the
            time delay.
            """
            a = getattr(model, self.ports["input"].port_name)
            b = getattr(model, self.ports["output"].port_name)
            if t < self.time_delay:
                return b[p, t] == 0
            else:
                return b[p, t] == a[p, int(t - self.time_delay)] * -1

        con_name = "time_delay_con_" + self.node_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=time_delay_rule))
