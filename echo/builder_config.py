from pydantic import BaseModel
from typing import Optional, Any, Union, List

from echo.echo_validators import ArrayType


class InverterConfig(BaseModel):
    max_import: Optional[float]
    max_export: Optional[float]
    ac_port_name: str
    dc_port_names: list
    # Defaults
    ac_dc_efficiency = 1
    dc_ac_efficiency = 1

class BatteryConfig(BaseModel):
    max_capacity: float
    depth_of_discharge_limit: float = 0
    charging_power_limit: float
    discharging_power_limit: float
    initial_state_of_charge: float
    # Defaults
    charging_efficiency: float = 1
    discharging_efficiency: float = 1


class SolarConfig(BaseModel):
    curtailable: bool = False


class EVChargeMode:
    V0G = 'v0g'
    V1G = 'v1g'
    V2G = 'v2g'

class EVConfig(BaseModel):
    available: Any
    usage: Any
    max_capacity: float
    depth_of_discharge_limit: float
    charging_power_limit: float
    discharging_power_limit: float
    charge_mode: str
    interval_duration: int

    # Defaults
    charging_efficiency: float = 1
    discharging_efficiency: float = 1
    initial_state_of_charge: float = 0.0
    tod_charging: ArrayType = None
    trip_slack: bool = False
    soc_conserv: float = None
    soc_conserv_cost: float = None


class EmittingNodeConfig(BaseModel):
    emitting_port: str
    carbon_port: str
    emissions_factor: Union[ArrayType, float]


class DemandChargeConfig(BaseModel):
    name: str
    rate: float
    window: ArrayType

class DemandTariffConfig(BaseModel):
    charges: list


class HeatingLoadConfig(BaseModel):
    name: str

