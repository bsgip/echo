from typing import cast

import numpy as np
import pandas as pd
from deprecated import deprecated

from echo.configuration import (
    EVChargeMode,
    EVChargeStatus,
    TransformRule,
)
from echo.exceptions import validate
from echo.models.base import Transform, TransformNode, TransformTerm
from echo.models.electrical.base import ElectricalDemand, ElectricalPort
from echo.models.electrical.ev.base import MobileElectricalStorage
from echo.models.scenario import EchoConcreteModel
from echo.utils import TimeExpandableType, fix_port_variable
from echo.validators import ArrayType


@deprecated(
    version="2.1.14",
    reason="Supeseded by EVV0G, EVV1G, EVV2G, EVWithProfile and EVBase classes",
)
class EV(TransformNode):
    charge_mode: EVChargeMode | None = None
    available: ArrayType | list | str
    usage: ArrayType | list
    connection_port_name: str = "cp"
    tod_charging: ArrayType | list | str | None = None
    interval_duration: int
    # Battery attributes
    max_capacity: float
    depth_of_discharge_limit: float = 0
    charging_power_limit: float
    discharging_power_limit: float
    charging_efficiency: float = 1
    discharging_efficiency: float = 1
    initial_state_of_charge: float

    # next variable is for allowing soc to go below min so as to avoid optimisation failing if there infeasible ev trips
    trip_slack: bool = False  # todo call this 'enable_trip_slack' so we can give it straight to port
    # next three variables are for having a 'conservative' ev user lower bound on the soc while it is plugged in
    soc_conserv: TimeExpandableType | None = None
    soc_conserv_cost: float | None = None

    V0G_delta: ArrayType | list | None
    V0G_SOC: ArrayType | list | None
    V0G_trip_infeasibility: ArrayType | list | None
    charge_status: EVChargeStatus | None

    port_dict_name_to_port_uid_map: dict[str, str] | None = None
    port_dict_name_to_port_name_map: dict[str, str] | None = None

    def __init__(self, **data) -> None:
        super().__init__(**data)

        # Check that usage is always <= max discharge of battery, otherwise the problem will be infeasible.
        for i in self.usage:
            if i > self.discharging_power_limit * -1:
                raise ValueError(
                    f"Usage requirement of {i} exceeds battery discharge limit of {self.discharging_power_limit}."
                )

        # Initialise port_name_to_port_uid_map
        if self.port_dict_name_to_port_uid_map is None:
            self.port_dict_name_to_port_uid_map = {}

        # Initialise port_name_to_port_uid_map
        if self.port_dict_name_to_port_name_map is None:
            self.port_dict_name_to_port_name_map = {}

        # Preserve uid and port_name if present on port
        if "vehicle" in self.port_dict_name_to_port_uid_map.keys():
            vehicle = MobileElectricalStorage(
                uid=self.port_dict_name_to_port_uid_map["vehicle"],
                port_name=self.port_dict_name_to_port_name_map["vehicle"],
                **{k: v for k, v in data.items() if k not in ["uid", "port_name"]},
            )
        else:
            vehicle = MobileElectricalStorage(**data)

        vehicle.enable_trip_slack = self.trip_slack  # Apply trip slack
        self.ports["vehicle"] = vehicle  # EV always has a storage port

        # Preserve uid if present on port
        if "usage" in self.port_dict_name_to_port_uid_map.keys():
            usage_port = ElectricalDemand(
                uid=self.port_dict_name_to_port_uid_map["usage"],
                port_name=self.port_dict_name_to_port_name_map["usage"],
                **{k: v for k, v in data.items() if k not in ["uid", "port_name"]},
            )
        else:
            usage_port = ElectricalDemand()

        usage_port.add_demand_profile_from_array(self.usage, expansion_periods=1)
        self.ports["usage"] = usage_port  # EV always has a fixed trip port

        # Customise connection point port type based on the charge mode
        if self.charge_mode == EVChargeMode.V0G:
            self.trip_slack = True  # Set slack to true
            vehicle.enable_trip_slack = self.trip_slack
            if self.connection_port_name in self.port_dict_name_to_port_uid_map.keys():
                electrical_demand = ElectricalDemand(
                    uid=self.port_dict_name_to_port_uid_map[self.connection_port_name],
                    port_name=self.port_dict_name_to_port_name_map[self.connection_port_name],
                    **{k: v for k, v in data.items() if k not in ["uid", "port_name"]},
                )

            else:
                electrical_demand = ElectricalDemand()
            self.ports[self.connection_port_name] = electrical_demand
            self.process_v0g_charging(self.interval_duration)
            electrical_demand.add_demand_profile_from_array(self.V0G_delta, expansion_periods=1)
        else:
            if self.connection_port_name in self.port_dict_name_to_port_uid_map.keys():
                electrical_port = ElectricalPort(
                    uid=self.port_dict_name_to_port_uid_map[self.connection_port_name],
                    port_name=self.port_dict_name_to_port_name_map[self.connection_port_name],
                )
            else:
                electrical_port = ElectricalPort()
            electrical_port.set_active_periods_from_array(self.available, expansion_periods=1)
            self.ports[self.connection_port_name] = electrical_port
            if self.charge_mode == EVChargeMode.V1G:
                electrical_port.set_flow_constraints(max_import=self.charging_power_limit, max_export=0.0)

        # EV needs a custom transformation because of the positive load convention
        self.add_transformation(self.create_ev_transformation())

        # Set port_dict_name_to_port_uid_map
        if len(self.port_dict_name_to_port_uid_map.keys()) == 0:
            self.port_dict_name_to_port_uid_map = {port_name: port.uid for port_name, port in self.ports.items()}

        # Set port_dict_name_to_port_name_map
        if len(self.port_dict_name_to_port_name_map.keys()) == 0:
            self.port_dict_name_to_port_name_map = {port_name: port.port_name for port_name, port in self.ports.items()}

    def update(
        self,
        available: ArrayType | list | str | None = None,
        usage: ArrayType | list | str | None = None,
        initial_state_of_charge: float | None = None,
        interval_duration: int | None = None,
    ) -> None:
        self.__init__(
            node_name=self.node_name,
            uid=self.uid,
            charge_mode=self.charge_mode,
            available=available if available is not None else self.available,
            usage=usage if usage is not None else self.usage,
            connection_port_name=self.connection_port_name,
            tod_charging=self.tod_charging,
            interval_duration=interval_duration if interval_duration is not None else self.interval_duration,
            max_capacity=self.max_capacity,
            depth_of_discharge_limit=self.depth_of_discharge_limit,
            charging_power_limit=self.charging_power_limit,
            discharging_power_limit=self.discharging_power_limit,
            charging_efficiency=self.charging_efficiency,
            discharging_efficiency=self.discharging_efficiency,
            initial_state_of_charge=(
                initial_state_of_charge if initial_state_of_charge is not None else self.initial_state_of_charge
            ),
            trip_slack=self.trip_slack,
            soc_conserv=self.soc_conserv,
            soc_conserv_cost=self.soc_conserv_cost,
            port_dict_name_to_port_uid_map=self.port_dict_name_to_port_uid_map,
            port_dict_name_to_port_name_map=self.port_dict_name_to_port_name_map,
        )

    def create_ev_transformation(self) -> Transform:
        # Create appropriate transformation: vehicle = cp - usage
        lhs_terms = [
            TransformTerm(var=self.ports["vehicle"], rule=TransformRule.Both, weight=1),
            TransformTerm(var=self.ports["usage"], rule=TransformRule.Both, weight=1),
            TransformTerm(
                var=self.ports[self.connection_port_name],
                rule=TransformRule.Both,
                weight=-1,
            ),
        ]
        return Transform(lhs_terms=lhs_terms)

    def process_v0g_charging(self, interval_duration: float) -> None:
        success, ev_soc, ev_delta, trip_infeasibility = self.v0g_charging(interval_duration)

        self.V0G_delta = ev_delta
        self.V0G_SOC = ev_soc
        if self.tod_charging is not None:
            if success:
                self.charge_status = EVChargeStatus.Feasible
            else:  # force convenience charging
                success, ev_soc, ev_delta, trip_infeasibility = self.v0g_charging(interval_duration, force_conv=True)
                self.charge_status = (
                    EVChargeStatus.TimeOfDayInfeasibleConvenienceFeasible if success else EVChargeStatus.Infeasible
                )
                self.V0G_delta = ev_delta
                self.V0G_SOC = ev_soc

        else:
            self.charge_status = EVChargeStatus.Feasible if success else EVChargeStatus.Infeasible
        self.V0G_trip_infeasibility = trip_infeasibility

    def v0g_charging(
        self,
        interval_duration: float,
        force_conv: bool = False,
    ) -> tuple[bool, list[float], float, float]:
        """Convert V0G vehicle (convenience charging) to a soc profile and a power profile if possible."""

        if (self.tod_charging is not None) and (not force_conv):
            self.available = self.available * self.tod_charging
        available_len = len(self.available)
        soc = np.zeros((available_len + 1,))
        vehicle = cast(MobileElectricalStorage, self.ports["vehicle"])
        soc[0] = vehicle.initial_state_of_charge
        trip_infeasibility = np.zeros((available_len,))
        delta = np.zeros((available_len,))
        max_capacity = vehicle.max_capacity
        charge_limit = vehicle.charging_power_limit
        charging_efficiency = vehicle.charging_efficiency

        for t in range(available_len):
            if self.available[t] and (soc[t] < max_capacity):  # available to charge and not at max capacity
                delta[t] = min(
                    charge_limit,
                    (max_capacity - soc[t]) / charging_efficiency / (interval_duration / 60),
                )
                soc[t + 1] = soc[t] + delta[t] * (interval_duration / 60) * charging_efficiency
            else:  # if not available then it might be on a trip and using power
                soc[t + 1] = soc[t] - self.usage[t] * (interval_duration / 60)
            trip_infeasibility[t] = -min(soc[t + 1], 0)
            soc[t + 1] = max(soc[t + 1], 0)

        success = True if (trip_infeasibility.max() == 0) else False

        return success, soc[1:], delta, trip_infeasibility

    def verify_node(self) -> None:
        super().verify_node()
        if self.charge_mode == EVChargeMode.V0G:
            validate(
                self.ports[self.connection_port_name].initial_value != 0,
                "V0G connection pt port needs demand profile added.",
            )
        else:
            validate(
                self.ports[self.connection_port_name].active_periods is not None,
                "Add available periods to EV connection pt port",
            )
        validate(
            self.ports["usage"].initial_value != 0,
            "EV usage port needs usage profile added.",
        )

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_node_to_model(model, profile)
        if self.charge_mode == EVChargeMode.V0G:
            # Fix the battery state of charge, the slack variable, and battery charging/discharging
            vehicle = cast(MobileElectricalStorage, self.ports["vehicle"])
            fix_port_variable(model, vehicle.soc_value, self.V0G_SOC, expansion_periods=1)
            fix_port_variable(
                model,
                vehicle.trip_slack,
                self.V0G_trip_infeasibility,
                expansion_periods=1,
            )
            power_profile = np.array(self.V0G_delta) + np.array(self.usage) * -1
            fix_port_variable(model, vehicle.port_name, power_profile, expansion_periods=1)
