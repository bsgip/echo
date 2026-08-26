from echo.configuration import Units
from echo.models.agnostic import FlexPort
from echo.models.base import Node, TransformNode
from echo.models.carbon import CarbonSource
from echo.validators import ArrayType


class FlexNode(Node):
    def __init__(self, port_name: str, port_unit: Units, **data) -> None:
        super().__init__(**data)
        self.ports[port_name] = FlexPort(port_name=port_name, units=port_unit)


class FlexElectricalNode(Node):
    def __init__(self, port_name: str, **data) -> None:
        super().__init__(**data)
        self.ports[port_name] = FlexPort(port_name=port_name, units=Units.KW)


class FlexNodeWithEmissions(TransformNode):
    def __init__(
        self,
        emitting_port: str,
        emitting_port_units: Units,
        carbon_port: str,
        emissions_factor: float | ArrayType,
        **data,
    ) -> None:
        super().__init__(**data)
        self.ports[emitting_port] = FlexPort(port_name=emitting_port, units=emitting_port_units)
        self.ports[carbon_port] = CarbonSource()
        self.add_emission_transformation(
            emitting_port=self.ports[emitting_port],
            carbon_port=self.ports[carbon_port],
            emission_factor=emissions_factor,
        )
