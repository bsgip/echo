from echo.configuration import Units
from echo.models.agnostic import Demand
from echo.models.base.node import Node
from echo.validators import ArrayType


class Load(Node):
    def __init__(self, port_name: str, port_unit: Units, profile: dict | ArrayType | list, **data) -> None:
        super().__init__(**data)
        self.ports[port_name] = Demand(units=port_unit)
        if type(profile) is dict:
            self.ports[port_name].set_initial_value(profile)
        else:
            self.ports[port_name].set_initial_value_from_array(profile)
