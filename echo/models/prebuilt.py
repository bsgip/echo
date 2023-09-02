from typing import Optional, Union

from pydantic import PositiveFloat

from echo.configuration import Units
from echo.echo_validators import ArrayType
from echo.models.agnostic import Demand, FlexPort
from echo.models.base import Node


class Battery(Node):
    def __init__(
        self,
        port_name,
        max_capacity: float,
        initial_state_of_charge: float,
        charging_power_limit: float,
        discharging_power_limit: float,
        storage_capacity_cost: Optional[PositiveFloat] = None,
        charging_efficiency: float = 1,
        discharging_efficiency: float = 1,
        depth_of_discharge_limit: float = 0,
        fixed_storage_capacity: bool = True,
        regularise: bool = False,
        **data,
    ):
        super().__init__(**data)
        self.ports[port_name] = ElectricalStorage(
            max_capacity=max_capacity,
            depth_of_discharge_limit=depth_of_discharge_limit,
            charging_power_limit=charging_power_limit,
            discharging_power_limit=discharging_power_limit,
            charging_efficiency=charging_efficiency,
            discharging_efficiency=discharging_efficiency,
            initial_state_of_charge=initial_state_of_charge,
            fixed_storage_capacity=fixed_storage_capacity,
            storage_capacity_cost=storage_capacity_cost,
            regularise=regularise,
        )


class Solar(Node):
    def __init__(self, port_name: str, profile: Union[ArrayType, dict], curtailable: bool = False, **data):
        super().__init__(**data)
        self.ports[port_name] = ElectricalGeneration(curtailable=curtailable)
        if type(profile) is dict:
            self.ports[port_name].add_initial_value(profile)
        else:
            self.ports[port_name].add_initial_value_from_array(profile)


class NewSolar(Node):
    """New Solar Node using Solar size for scaling of initial value ref"""

    def __init__(self, port_name: str, solar_size: float, initial_value_ref: str, curtailable: bool = False, **data):
        super().__init__(**data)
        self.ports[port_name] = ElectricalGeneration(
            curtailable=curtailable, initial_value_ref=initial_value_ref, initial_value_scaling=solar_size
        )


class Load(Node):
    def __init__(self, port_name: str, port_unit: int, profile: Union[dict, ArrayType, list], **data):
        super().__init__(**data)
        self.ports[port_name] = Demand(units=port_unit)
        if type(profile) is dict:
            self.ports[port_name].add_initial_value(profile)
        else:
            self.ports[port_name].add_initial_value_from_array(profile)


class FlexNode(Node):
    def __init__(self, port_name: str, port_unit: int, **data):
        super().__init__(**data)
        self.ports[port_name] = FlexPort(port_name=port_name, units=port_unit)


class FlexElectricalNode(Node):
    def __init__(self, port_name: str, **data):
        super().__init__(**data)
        self.ports[port_name] = FlexPort(port_name=port_name, units=Units.KW)


class NewInverter(Inverter):
    def __init__(self, ac_port_name: str, dc_port_names: list, **data):
        super().__init__(**data)
        self.add_ac_port(ac_port_name)
        for i in dc_port_names:
            self.add_dc_port(i)


class FlexNodeWithEmissions(Node):
    def __init__(
        self,
        emitting_port: str,
        emitting_port_units: int,
        carbon_port: str,
        emissions_factor: Union[float, ArrayType],
        **data,
    ):
        super().__init__(**data)
        self.ports[emitting_port] = FlexPort(port_name=emitting_port, units=emitting_port_units)
        self.ports[carbon_port] = CarbonSource()
        self.add_emission_transformation(
            emitting_port=self.ports[emitting_port],
            carbon_port=self.ports[carbon_port],
            emission_factor=emissions_factor,
        )
