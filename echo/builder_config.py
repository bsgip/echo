from pydantic import BaseModel
from typing import Optional

class InverterConfig(BaseModel):
    max_import: Optional[float]
    max_export: Optional[float]
    ac_dc_efficiency = 1
    dc_ac_efficiency = 1
    ac_port: str
    dc_ports: list

class BatteryConfig(BaseModel):
    max_capacity: float
    depth_of_discharge_limit: float = 0
    charging_power_limit: float
    discharging_power_limit: float
    charging_efficiency: float = 1
    discharging_efficiency: float = 1
    initial_state_of_charge: float


class SolarConfig(BaseModel):
    curtailable: bool = False