from typing import cast

import numpy as np
import pandas as pd

from echo.configuration import (
    EVChargeMode,
    EVChargeStatus,
)
from echo.exceptions import validate
from echo.models.electrical.base import ElectricalDemand
from echo.models.electrical.ev.base import EVBase, MobileElectricalStorage
from echo.models.scenario import EchoConcreteModel
from echo.utils import fix_port_variable
from echo.validators import ArrayType, check_initial_state_of_charge_within_bounds


class EVV0G(EVBase):
    """This EV object takes an available and usage dataset to precalculate a demand profile.

    Once plugged in for charging, it assumes charging at the maximum rate until the battery is full.

    """

    # Initialise attributes
    V0G_delta: ArrayType | list | None
    V0G_SOC: ArrayType | list | None
    V0G_trip_infeasibility: ArrayType | list | None
    charge_status: EVChargeStatus | None

    def __init__(self, **data) -> None:
        super().__init__(**data)

        # Set the charge_mode
        self.charge_mode = EVChargeMode.V0G

        # Create ports
        self._create_usage_port()
        self._create_vehicle_port()
        self._create_connection_point_port()

        # If setting attributes with state at instantiation, set them now.
        if self.set_stateful_attrs_at_init:
            self.set_stateful_attrs(
                available=self.available,
                usage=self.usage,
                initial_state_of_charge=self.initial_state_of_charge,
                interval_duration=self.interval_duration,
                tod_charging=self.tod_charging,
            )

        # EV needs a custom transformation because of the positive load convention
        self.add_transformation(self._create_ev_transformation())

        # Set port_dict_name_to_port_uid_map and port_dict_name_to_port_name_map
        self.set_port_uid_maps()

    def _create_connection_point_port(self) -> None:
        """Creates a connection point port for the EV.min_soc

        Overwrites EVBase._create_connection_point_port as V0G uses an ElectricalDemand port instead of a
        ElectricalPort.

        Args:
            None

        Returns:
            None

        """

        self.ports[self.connection_port_name] = ElectricalDemand()

    def set_stateful_attrs(
        self,
        available: ArrayType | list,
        usage: ArrayType | list,
        initial_state_of_charge: float,
        interval_duration: int,
        tod_charging: ArrayType | list | str | None = None,
    ) -> None:
        """Injects attributes with state into EV node and ports.

        Args:
            available: A List or ArrayType of bools representing the ability for the EV to charge. The bools can have
                values of [False, True] or [0, 1]. 0 and False indicate the EV is not available for charging, 1 and
                True indicate the EV is available for charging.
            usage: An array representing the average power consumption from driving of the EV during a time interval.
                Units of power.
            initial_state_of_charge: The initial charge present in the EV's battery. Positive float of energy units,
                not percentage. Positive float with units of energy.
            interval_duration: The duration between timestamps. Units of minutes.
            tod_charging: Time of day charging allows the EV to charge only during certain time windows (1=allowed,
                0=not allowed). Most commonly used with V0G charging. Defaults to None.

        Returns:
            None
        """

        # Update the node attributes.
        self.available = available
        self.usage = usage
        self.initial_state_of_charge = initial_state_of_charge
        self.interval_duration = interval_duration
        self.tod_charging = tod_charging

        # Set the initial_state_of_charge on the vehicle port
        self.ports["vehicle"].initial_state_of_charge = self.initial_state_of_charge

        # Check that the initial_state_of_charge is between the min_soc and max_capacity
        check_initial_state_of_charge_within_bounds(
            initial_state_of_charge=self.ports["vehicle"].initial_state_of_charge,
            min_soc=self.ports["vehicle"].min_soc,
            max_capacity=self.ports["vehicle"].max_capacity,
        )

        # Set stateful attributes for usage port
        self._check_usage_less_than_max_usage()
        self.ports["usage"].add_demand_profile_from_array(self.usage, expansion_periods=1)

        # Calculate demand
        self._process_v0g_charging(self.interval_duration)

        # Set stateful attrs for the connection point port
        self.ports[self.connection_port_name].add_demand_profile_from_array(self.V0G_delta, expansion_periods=1)

    def _process_v0g_charging(self, interval_duration: float) -> None:
        """Calculate the convenience charging profile for the EV.

        Args:
            interval_duration: The timestep of the timeseries in minutes.

        Returns:
            None

        """
        success, ev_soc, ev_delta, trip_infeasibility = self._v0g_charging(interval_duration)

        # Set node attributes
        self.V0G_delta = ev_delta
        self.V0G_SOC = ev_soc

        # Check for time of day charging
        if self.tod_charging is not None:
            if success:
                self.charge_status = EVChargeStatus.Feasible
            else:
                # If there are any infeasibilities, force convenience charging
                success, ev_soc, ev_delta, trip_infeasibility = self._v0g_charging(interval_duration, force_conv=True)
                self.charge_status = (
                    EVChargeStatus.TimeOfDayInfeasibleConvenienceFeasible if success else EVChargeStatus.Infeasible
                )
                self.V0G_delta = ev_delta
                self.V0G_SOC = ev_soc
        else:
            self.charge_status = EVChargeStatus.Feasible if success else EVChargeStatus.Infeasible

        # Set nodes V0G_trip_infeasibility
        self.V0G_trip_infeasibility = trip_infeasibility

    def _v0g_charging(
        self,
        interval_duration: float,
        force_conv: bool = False,
    ) -> tuple[bool, list[float], float, float]:
        """Convert V0G vehicle (convenience charging) to a soc profile and a power profile if possible.

        Args:
            interval_duration: The timestep of the timeseries in minutes.
            force_conv: Force convenience charging if time of day (tod) charging is specified

        Returns:
            success: A bool describing if entire timeseries is feasible (True) or infeasible (False)
            ev_soc: The timeseries profile of the state of charge of the EV
            ev_delta: The timeseries profile of the energy added to the EV
            trip_infeasibility: The timeseries profile of the feasibility of each timestep.
        """

        # Determine the availability of the EV to charge accounting for the time of day charging preferences
        if (self.tod_charging is not None) and (not force_conv):
            self.available = list(np.array(self.available) * np.array(self.tod_charging))

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

        success: bool = True if (trip_infeasibility.max() == 0) else False

        return success, soc[1:], delta, trip_infeasibility

    def _verify_ports(self) -> None:
        """Checks data with state has been set for each port.

        Overwrites parent function.

        Args:
            None

        Returns:
            None

        """
        validate(
            self.ports[self.connection_port_name].initial_value != 0,
            f"{self.node_name} connection point port does not have a demand profile set.",
        )
        validate(
            self.ports["usage"].initial_value != 0,
            f"{self.node_name} usage port needs does not have a usage profile set.",
        )
        validate(
            (isinstance(self.ports["vehicle"], MobileElectricalStorage))
            and (self.ports["vehicle"].initial_state_of_charge) is not None,
            f"{self.node_name} vehicle port does not have a initial_state_of_charge set.",
        )

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame | None = None) -> None:
        """Fix the battery state of charge, the slack variable, and battery charging/discharging for EV.

        Args:
            model: The concrete model to add the EV to
            profile:

        Returns:
            None

        """

        super().add_node_to_model(model, profile)

        vehicle = cast(MobileElectricalStorage, self.ports["vehicle"])
        fix_port_variable(model, vehicle.soc_value, self.V0G_SOC, expansion_periods=1)

        # If there is a trip slack, add the port variable to the model
        if self.enable_trip_slack:
            fix_port_variable(
                model,
                vehicle.trip_slack,
                self.V0G_trip_infeasibility,
                expansion_periods=1,
            )

        power_profile = np.array(self.V0G_delta) + np.array(self.usage) * -1
        fix_port_variable(model, vehicle.port_name, power_profile, expansion_periods=1)
