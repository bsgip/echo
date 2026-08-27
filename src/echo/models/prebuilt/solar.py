from echo.models.base import Node
from echo.models.electrical import ElectricalGeneration
from echo.validators import ArrayType


class Solar(Node):
    def __init__(self, port_name: str, profile: ArrayType | dict, curtailable: bool = False, **data) -> None:
        super().__init__(**data)
        self.ports[port_name] = ElectricalGeneration(curtailable=curtailable)
        if type(profile) is dict:
            self.ports[port_name].set_initial_value(profile)
        else:
            self.ports[port_name].set_initial_value_from_array(profile)
