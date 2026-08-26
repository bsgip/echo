from echo.models.base.node import Node
from echo.models.electrical import ElectricalGeneration


class ScaledSolar(Node):
    """Solar Node using size of solar system for scaling of initial value ref"""

    def __init__(
        self,
        port_name: str,
        solar_size: float,
        initial_value_ref: str,
        curtailable: bool = False,
        **data,
    ) -> None:
        super().__init__(**data)
        self.ports[port_name] = ElectricalGeneration(
            curtailable=curtailable, initial_value_ref=initial_value_ref, initial_value_scaling=solar_size
        )
