from typing import Dict, Optional, Union, cast

import numpy as np
import pandas as pd
import pyomo.environ as en
from pydantic import Field

from echo.configuration import EVChargeMode, NodeRule, TransformRule, Units
from echo.exceptions import ConfigurationError, validate
from echo.models.agnostic import BoundedLoad, Demand, FixedPort, FlexPort, MobileStorage, Source, Storage
from echo.models.base import Node, Transform, TransformTerm
from echo.models.scenario import EchoConcreteModel
from echo.utils import ArrayWrap, fix_port_variable, set_var_bounds_from_dict
from echo.validators import ArrayType


class ElectricalDemand(Demand):
    """Fixed electrical demand."""

    units = Units.KW


class ElectricalGeneration(Source):
    """Electrical generation which can be fixed (non-curtailable) or variable (curtailable)"""

    units = Units.KW
    curtailable: bool = False

    def add_generation_profile(self, generation: dict):
        self.add_initial_value(generation)

    def add_generation_profile_from_array(
        self, generation: ArrayType, expansion_periods=1, time_periods: Optional[int] = None
    ):
        self.add_initial_value_from_array(generation, expansion_periods=expansion_periods, time_periods=time_periods)

    def initialise_port(self, model: EchoConcreteModel, profile: pd.DataFrame):
        super(ElectricalGeneration, self).initialise_port(model, profile)
        if self.curtailable is False:
            getattr(model, self.port_name).fix()  # Equivalent to setting a variable to be a parameter after creation
        else:
            # Constrain solar gen to be within initial value (max value)
            getattr(model, self.port_name).unfix()
            set_var_bounds_from_dict(getattr(model, self.port_name), lb=self.initial_value, ub=None)


class ElectricalStorage(Storage):
    units = Units.KW


class MobileElectricalStorage(MobileStorage):
    units = Units.KW


class EV(Node):
    charge_mode: Optional[EVChargeMode] = None
    available: Union[ArrayType, list, str]
    usage: Union[ArrayType, list]
    connection_port_name: str = "cp"
    tod_charging: Union[ArrayType, list, str, None] = None
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
    soc_conserv: Union[ArrayWrap, None] = None
    soc_conserv_cost: Union[float, None] = None

    V0G_delta: Optional[Union[ArrayType, list]]
    V0G_SOC: Optional[Union[ArrayType, list]]
    V0G_trip_infeasibility: Optional[Union[ArrayType, list]]
    charge_status: Optional[str]

    port_dict_name_to_port_uid_map: Optional[Dict[str, str]] = None
    port_dict_name_to_port_name_map: Optional[Dict[str, str]] = None

    def __init__(self, **data) -> None:
        super().__init__(**data)
        # Check that usage is always <= max discharge of battery, otherwise the problem will be infeasible.
        for i in self.usage:
            if i > self.discharging_power_limit * -1:
                raise ValueError(
                    "Usage requirement of {} exceeds battery discharge limit of {}.".format(
                        i, self.discharging_power_limit
                    )
                )

        # Initialise port_name_to_port_uid_map
        if self.port_dict_name_to_port_uid_map is None:
            self.port_dict_name_to_port_uid_map = dict()

        # Initialise port_name_to_port_uid_map
        if self.port_dict_name_to_port_name_map is None:
            self.port_dict_name_to_port_name_map = dict()

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
            self.process_V0G_charging(self.interval_duration)
            electrical_demand.add_demand_profile_from_array(self.V0G_delta, expansion_periods=1)
        else:
            if self.connection_port_name in self.port_dict_name_to_port_uid_map.keys():
                electrical_port = ElectricalPort(
                    uid=self.port_dict_name_to_port_uid_map[self.connection_port_name],
                    port_name=self.port_dict_name_to_port_name_map[self.connection_port_name],
                )
            else:
                electrical_port = ElectricalPort()
            electrical_port.add_active_periods_from_array(self.available, expansion_periods=1)
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
        available: Optional[Union[ArrayType, list, str]] = None,
        usage: Optional[Union[ArrayType, list, str]] = None,
        initial_state_of_charge: Optional[float] = None,
        interval_duration: Optional[int] = None,
    ):
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
            initial_state_of_charge=initial_state_of_charge
            if initial_state_of_charge is not None
            else self.initial_state_of_charge,
            trip_slack=self.trip_slack,
            soc_conserv=self.soc_conserv,
            soc_conserv_cost=self.soc_conserv_cost,
            port_dict_name_to_port_uid_map=self.port_dict_name_to_port_uid_map,
            port_dict_name_to_port_name_map=self.port_dict_name_to_port_name_map,
        )

    def create_ev_transformation(self):
        # Create appropriate transformation: vehicle = cp - usage
        lhs_terms = [
            TransformTerm(self.ports["vehicle"], TransformRule.Both, ArrayWrap(1)),
            TransformTerm(self.ports["usage"], TransformRule.Both, ArrayWrap(1)),
            TransformTerm(self.ports[self.connection_port_name], TransformRule.Both, ArrayWrap(-1)),
        ]
        return Transform(lhs_terms=lhs_terms)

    def process_V0G_charging(self, interval_duration: float):
        success, ev_soc, ev_delta, trip_infeasibility = self.V0G_charging(interval_duration)

        self.V0G_delta = ev_delta
        self.V0G_SOC = ev_soc
        if self.tod_charging is not None:
            if success:
                self.charge_status = "success"
            else:  # force convenience charging
                success, ev_soc, ev_delta, trip_infeasibility = self.V0G_charging(interval_duration, force_conv=True)
                self.charge_status = "time of day infeasible, convenience success" if success else "infeasible"
                self.V0G_delta = ev_delta
                self.V0G_SOC = ev_soc

        else:
            self.charge_status = "success" if success else "infeasible"
        self.V0G_trip_infeasibility = trip_infeasibility

    def V0G_charging(self, interval_duration: float, force_conv=False):
        """Convert V0G vehicle (convenience charging) to a soc profile and a power profile if possible."""
        if (self.tod_charging is not None) and (not force_conv):
            self.available = self.available * self.tod_charging
        T = len(self.available)
        soc = np.zeros((T + 1,))
        vehicle = cast(MobileElectricalStorage, self.ports["vehicle"])
        soc[0] = vehicle.initial_state_of_charge
        trip_infeasibility = np.zeros((T,))
        delta = np.zeros((T,))
        max_capacity = vehicle.max_capacity
        charge_limit = vehicle.charging_power_limit
        charging_efficiency = vehicle.charging_efficiency

        for t in range(T):
            if self.available[t] and (soc[t] < max_capacity):  # available to charge and not at max capacity
                delta[t] = min(charge_limit, (max_capacity - soc[t]) / charging_efficiency / (interval_duration / 60))
                soc[t + 1] = soc[t] + delta[t] * (interval_duration / 60) * charging_efficiency
            else:  # if not available then it might be on a trip and using power
                soc[t + 1] = soc[t] - self.usage[t] * (interval_duration / 60)
            trip_infeasibility[t] = -min(soc[t + 1], 0)
            soc[t + 1] = max(soc[t + 1], 0)

        success = True if (trip_infeasibility.max() == 0) else False

        return success, soc[1:], delta, trip_infeasibility

    def verify_node(self):
        super(EV, self).verify_node()
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
        validate(self.ports["usage"].initial_value != 0, "EV usage port needs usage profile added.")

    def initialise_node(self, model: EchoConcreteModel, profile):
        super(EV, self).initialise_node(model, profile)
        if self.charge_mode == EVChargeMode.V0G:
            # Fix the battery state of charge, the slack variable, and battery charging/discharging
            vehicle = cast(MobileElectricalStorage, self.ports["vehicle"])
            fix_port_variable(model, vehicle.soc_value, self.V0G_SOC, expansion_periods=1)
            fix_port_variable(model, vehicle.trip_slack, self.V0G_trip_infeasibility, expansion_periods=1)
            power_profile = np.array(self.V0G_delta) + np.array(self.usage) * -1
            fix_port_variable(model, vehicle.port_name, power_profile, expansion_periods=1)


class ElectricalPort(FlexPort):
    """Flexible electrical port"""

    units = Units.KW


class FixedElectricalPort(FixedPort):
    """An electrical port with fixed values (parameters). No constraints on whether the port is importing/exporting."""

    units = Units.KW


class Inverter(Node):
    """An inverter is a node with one AC port and at least one DC port.
    Flows from AC to DC, and DC to AC, are subject to conversion efficiencies."""

    max_import: Union[float, None]
    max_export: Union[float, None]
    dc_ac_efficiency: float = Field(default=1.0, ge=0, le=1)
    ac_dc_efficiency: float = Field(default=1.0, ge=0, le=1)
    dc_port_names: Optional[list] = []
    ac_port_name: Optional[str] = None  # There should generally only be one ac port
    node_rule = NodeRule.Custom

    def add_dc_port(self, port_name: str, uid: Union[str, None] = None):
        p = ElectricalPort(port_name=port_name, uid=uid)
        self.dc_port_names.append(port_name)
        self.ports[port_name] = p

    def add_ac_port(self, port_name: str, uid: Union[str, None] = None):
        if self.ac_port_name is not None:
            raise ConfigurationError("AC port already specified for this inverter.")
        else:
            p = ElectricalPort(port_name=port_name, uid=uid)
            p.set_flow_constraints(max_export=self.max_export, max_import=self.max_import)
            self.ac_port_name = port_name
            self.ports[port_name] = p

    def verify_node(self):
        # Check that we have at least one ac and one dc port
        validate(self.ac_port_name is not None, "Define at least one ac port on inverter.")
        validate(self.dc_port_names is not None, "Define at least one dc port on inverter.")
        # Check that all ports are either ac or dc
        all_port_names = [x for x in self.ports.keys()]
        named_ports = [self.ac_port_name] + self.dc_port_names
        validate(set(all_port_names) == set(named_ports), "All ports on inverter must be ac or dc.")

    def initialise_node(self, model: EchoConcreteModel, profile):
        super(Inverter, self).initialise_node(model, profile)

        ac_port = self.ports[self.ac_port_name]
        # Split ac port into pos/neg, so we can apply the correct efficiencies
        ac_port.constrain_pos_neg(model)

        def inverter_ac_output_must_track_efficiency(model: EchoConcreteModel, p, t):  # Apply efficiency constraints
            dc_total = 0
            for dc_port_name in self.dc_port_names:
                dc_port = self.ports[dc_port_name]
                dc_total += getattr(model, dc_port.port_name)[p, t]

            return (
                getattr(model, ac_port.pos)[p, t] * self.ac_dc_efficiency
                + getattr(model, ac_port.neg)[p, t] / self.dc_ac_efficiency
                == dc_total * -1
            )

        setattr(
            model,
            f"con_inverter_{self.node_name}",
            en.Constraint(model.Expansion, model.Time, rule=inverter_ac_output_must_track_efficiency),
        )


class BoundedElectricalLoad(BoundedLoad):
    units = Units.KW
