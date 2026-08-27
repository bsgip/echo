from pydantic import PositiveFloat

from echo.models.base.node import Node
from echo.models.electrical import ElectricalStorage


class Battery(Node):
    def __init__(
        self,
        port_name: str,
        max_capacity: float,
        initial_state_of_charge: float,
        charging_power_limit: float,
        discharging_power_limit: float,
        storage_capacity_cost: PositiveFloat | None = None,
        charging_efficiency: float = 1,
        discharging_efficiency: float = 1,
        depth_of_discharge_limit: float = 0,
        fixed_storage_capacity: bool = True,
        regularise: bool = False,
        **data,
    ) -> None:
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
