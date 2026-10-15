from attrs import define, field

from echo.configuration import Units
from echo.models.agnostic.flex import FlexPort
from echo.models.base.node import Node


@define
class InputOutputNode(Node):
    """
    An input-output node has one input port and one output port.
    A custom transformation can be defined between input and output.
    """

    # TODO: This Node does not do anything, unnecessary inheritance

    input_port_unit: Units = field(kw_only=True)
    output_port_unit: Units = field(kw_only=True)
    # Optional parameters for controlling input/output port flows
    max_output: float | None = None  # output might be neg or pos, leave it open
    min_output: float | None = None
    max_input: float | None = None
    min_input: float | None = None
    input_port_ref: str = "input"
    output_port_ref: str = "output"

    def __attrs_post_init__(self) -> None:
        # Create an input port and an output port with the correct units
        self.ports[self.input_port_ref] = FlexPort(units=self.input_port_unit)
        self.ports[self.output_port_ref] = FlexPort(units=self.output_port_unit)
