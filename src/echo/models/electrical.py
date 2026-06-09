from typing import cast
from warnings import warn

import numpy as np
import pandas as pd
import pyomo.environ as en
import shortuuid
from deprecated import deprecated
from pydantic import Field, NonNegativeFloat

from echo.configuration import (
    EVChargeMode,
    EVChargeStatus,
    FlowConstraint,
    Flows,
    OptimisationType,
    TransformRule,
    Units,
)
from echo.exceptions import ConfigurationError, validate
from echo.models.agnostic import BoundedLoad, Demand, FixedPort, FlexPort, MobileStorage, Source, Storage
from echo.models.base import Node, Transform, TransformNode, TransformTerm
from echo.models.scenario import EchoConcreteModel
from echo.utils import TimeExpandableType, fix_port_variable, set_var_bounds_from_dict
from echo.validators import ArrayType, check_initial_state_of_charge_within_bounds


class ElectricalDemand(Demand):
    """Fixed electrical demand."""

    units = Units.KW


class ElectricalGeneration(Source):
    """Electrical generation which can be fixed (non-curtailable) or variable (curtailable)"""

    units = Units.KW
    curtailable: bool = False

    def add_generation_profile(self, generation: dict) -> None:
        self.set_initial_value(generation)

    def add_generation_profile_from_array(
        self,
        generation: ArrayType,
        expansion_periods: int = 1,
        time_periods: int | None = None,
    ) -> None:

        self.set_initial_value_from_array(
            array=generation, expansion_periods=expansion_periods, time_periods=time_periods
        )

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        # Whether curtailable is set or not affect whether the flow is represented as a parameter or variable
        # Handle that here before calling `add_port_to_model`
        self.flow_type = OptimisationType.Variable if self.curtailable else OptimisationType.Parameter

        super().add_port_to_model(model, profile)

        if self.curtailable:
            # Constrain solar gen to be within initial value (max value)
            set_var_bounds_from_dict(model=model, var_name=self.port_name, lb=self.initial_value, ub=None)


class ElectricalStorage(Storage):
    units = Units.KW


class MobileElectricalStorage(MobileStorage):
    units = Units.KW


class EVBase(TransformNode):
    """Base class for EVV0G, EVV1G and EVV2G.

    Args:
        available (ArrayType | list | str | None): A List or ArrayType of bools representing the ability for the
            EV to charge. The bools can have values of [False, True] or [0, 1]. 0 and False indicate the EV is not
            available for charging, 1 and True indicate the EV is available for charging. If
            set_state_attrs_at_init is True, this must be supplied. If set_stateful_attrs_at_init is False, this must
            be provided later using set_stateful_attrs(). ArrayType | list represents data, while a str represents the
            column name in a pandas dataframe.
        charge_mode (EVChargeMode | None): Charge mode of the EV. This is set upon instantiation of EV child classes.
            Defaults to None.
        charging_efficiency (float | None): The efficiency of the battery charging process for the EV. Float as
            a fraction between 0.0 and 1.0 inclusive. Unitless. Defaults to 1.0.
        charging_power_limit (float): The maximum charging rate of the EV's battery. Positive float in power units.
        connection_point_name (str | None): Name of connection point port. Defaults to "cp".
        depth_of_discharge_limit (float, optional): The minimum value of the state of ElectricalStorage of the EV. Same
            as min_soc but expressed as percentage, not energy. Float as a percentage (of max_capacity) between 0.0
            and 100.0. Unitless. Defaults to 0.0.
        discharging_efficiency (float | None): The efficiency of the battery discharging process for the EV. Float as
            a fraction between 0.0 and 1.0 inclusive. Unitless. Defaults to 1.0.
        discharging_power_limit (float): The maximum discharging rate of the EV's battery. This includes
            discharging for travelling and V2G actions. If usage_power_limit is set then
            discharging_power_limit represents maximum V2G generation power only. Negative float in power units.
        enable_trip_slack (bool | None): Enabling trip slack allows the EV to meet usage requirements even if
            other constraints/requirements are breached. That is, it allows the state of charge of the EV's battery
            to go below min to avoid the optimisation failing due to infeasible EV trips. For example, an EV can
            complete a journey requiring 20 kWh of energy if though there is only 15 kWh of energy in the EV
            battery. Setting enable_trip_slack to True will introduce additional energy into the system, though
            there is a cost to do so. This can cause issues when conducting analysis on systems with
            enable_trip_slack=True, so use with caution. Defaults to False.
        initial_state_of_charge (float | None): The initial charge present in the EV's battery. If
            set_state_attrs_at_init is True, this must be supplied. If set_stateful_attrs_at_init is False, it must be
            provided later using set_stateful_attrs(). Positive float with units of energy (not percentage).
        interval_duration(int): Length of time interval between time series data points. Used mostly for conversion
            between power and energy. If set_stateful_attrs_at_init is False, this can be set after EV object
            instantiation using self.set_state_attrs(). Units of minutes.
        max_capacity (float): The storage capacity of the EV's battery. Positive float in energy units.
        port_dict_name_to_port_name_map (dict[str, str] | None): Defines port name to port object map. It is recommended
            not to use this unless you know what you are doing. If None, it will defined once ports are built. Defaults
            to None.
        port_dict_name_to_port_uid_map (dict[str, str] | None): Defines port uid to port object map. It is recommended
            not to use this unless you know what you are doing. If None, it will defined once ports are built. Defaults
            to None.
        set_stateful_attrs_at_init (bool | None): Set attributes with state at object instantiation (True) or
            defer to later (False). If deferring to later, self.set_stateful_attrs() must be used to set these
            attributes. Attributes with state are available and initial_state_of_charge. Defaults to True.
        soc_conserv (TimeExpandableType | None): Conservative state of charge limit below which the EV should not
            discharge to the grid. This reflects that an EV owner would want to ensure a certain amount of charge is
            available impromptu trips. This lower bound only applies while the EV is available to charge. Defaults to
            None.
        soc_conserv_cost (float | None): The cost placed on going below the conservative state of charge limit. That
            is, the conservative state of charge lower limit will be ignored if it would result in saving (or gaining)
            more money than this cost. Units of $/kWh. Defaults to None.
        tod_charging (ArrayType | list | str | None): Time of day charging allows the EV to charge only during certain
            time windows (1=allowed, 0=not allowed). Most commonly used with V0G charging. Defaults to None.
        usage (ArrayType | list | None): An array representing the average power consumption from driving of the EV
            during a time interval. Units of power.
        usage_power_limit (float | None): The maximum power that can be used during an EV trip. If not None, it allows
            discharging_power_limit to represent only the maximum power flow from an EVV2G back into an electrical
            network, and not the maximum power output during a trip. Negative float in power units. Defaults to None,
            however if None, it will be set to discharging_power_limit.
    """

    charge_mode: EVChargeMode | None = None
    connection_port_name: str = "cp"

    # Battery attributes
    charging_efficiency: float = 1
    charging_power_limit: float
    depth_of_discharge_limit: float = 0
    discharging_efficiency: float = 1
    discharging_power_limit: float
    enable_trip_slack: bool = False
    max_capacity: float
    soc_conserv: TimeExpandableType | None = None
    soc_conserv_cost: float | None = None
    usage_power_limit: float | None = None

    # Stateful attributes
    available: ArrayType | list | str | None
    initial_state_of_charge: float | None
    interval_duration: int | None
    set_stateful_attrs_at_init: bool = True
    tod_charging: ArrayType | list | str | None
    usage: ArrayType | list | None = None

    # Helpful mappings for port names and uids
    port_dict_name_to_port_name_map: dict[str, str] | None = None
    port_dict_name_to_port_uid_map: dict[str, str] | None = None

    def __init__(self, **data) -> None:
        super().__init__(**data)

        # If usage_power_limit isn't specified, set it to discharging_power_limit. This is for backwards compatability
        if self.usage_power_limit is None:
            self.usage_power_limit = self.discharging_power_limit

    def _check_stateful_attrs_are_not_none(self) -> None:
        """Checks that the stateful attributes for EVBase and children are not None.

        To be used node verifification before building a network.

        Checks: self.available, self.usage, self.initial_state_of_charge, self.interval_duration.

        Args:
            None

        Returns:
            None

        Raises:
            ConfigurationError: if self.available is None.
            ConfigurationError: if self.usage is None.
            ConfigurationError: if self.initial_state_of_charge is None.
            ConfigurationError: if self.interval_duration is None.
        """

        if self.available is None:
            raise ConfigurationError(
                f"The available attribute for {self.node_name} has not been set. Please use set_stateful_attrs()."
            )

        if self.usage is None:
            raise ConfigurationError(
                f"The usage attribute for {self.node_name} has not been set. Please use set_stateful_attrs()."
            )

        if self.initial_state_of_charge is None:
            raise ConfigurationError(
                f"The initial_state_of_charge attribute for {self.node_name} has not been set. "
                f"Please use set_stateful_attrs()."
            )

        if self.interval_duration is None:
            raise ConfigurationError(
                f"The interval_duration attribute for {self.node_name} has not been set. "
                f"Please use set_stateful_attrs()."
            )

    def _check_usage_less_than_max_usage(self) -> None:
        """Check that the maximum value in usage is not larger than the maximum usage rate.

        If a value of usage is larger than max_usage_rate for an ev, this will result in an infeasible solution.

        Args:
            None

        Returns:
            None

        Raises:
            ValueError: if the maximum power usage is greater than max_discharge_rate.
        """

        # Get the maximum power usage
        max_usage = np.max(np.array(self.usage))

        # If the maximum power usage is larger than the usage power limit, raise an error.
        if max_usage > self.usage_power_limit * -1:
            raise ValueError(
                f"Usage requirement of {max_usage} exceeds battery discharge limit of {self.usage_power_limit}."
            )

    def _create_usage_port(self) -> None:
        """Create a usage port and add it to the EV's ports list.

        Args:
            None

        Returns:
            None
        """

        # Create the usage port and assign it to the EV object
        self.ports["usage"] = ElectricalDemand()

        # TODO: Set demand here if set_stateful_attrs_at_init is True

    def _create_vehicle_port(self) -> None:
        """Create a vehicle port and add it to the EV's ports list.

        Args:
            None

        Returns:
            None
        """

        # Check that attributes with state are not None if set_state_attrs_at_init is True
        if self.set_stateful_attrs_at_init:
            self._check_stateful_attrs_are_not_none()

        # Create the usage port and assign it to the EV object
        self.ports["vehicle"] = MobileElectricalStorage(
            charging_power_limit=self.charging_power_limit,
            discharging_power_limit=self.discharging_power_limit,
            initial_state_of_charge=self.initial_state_of_charge,
            max_capacity=self.max_capacity,
            available=self.available,
            charging_efficiency=self.charging_efficiency,
            depth_of_discharge_limit=self.depth_of_discharge_limit,
            discharging_efficiency=self.discharging_efficiency,
            enable_trip_slack=self.enable_trip_slack,
            soc_conserv=self.soc_conserv,
            soc_conserv_cost=self.soc_conserv_cost,
        )

    def _create_connection_point_port(self) -> None:
        """Create a connection point port and add it to the EV's ports list.

        Args:
            None

        Returns:
            None
        """

        self.ports[self.connection_port_name] = ElectricalPort(
            flows=Flows.Both,
            import_constraint=FlowConstraint.NoConstraint,
            flow_type=OptimisationType.Variable,
            units=Units.KW,
            export_constraint=FlowConstraint.Fixed,
            export_constraint_value=self.discharging_power_limit,
        )

    def _create_ev_transformation(self) -> Transform:
        """Creates the appropriate transformation for EV objects: vehicle = connection_point - usage.

        Args:
            None

        Returns:
            The left hand side of the equation of the linear node transformation. The right hand side is 0.
        """

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

    def verify_node(self) -> None:
        """Checks data with state has been set for the node and each port.

        Args:
            None

        Returns:
            None
        """

        super().verify_node()

        # Check node properties
        self._check_stateful_attrs_are_not_none()
        self._verify_ports()

    def _verify_ports(self) -> None:
        """Checks data with state has been set for each port.

        Args:
            None

        Returns:
            None
        """

        validate(
            self.ports["usage"].initial_value != 0,
            f"{self.node_name} usage port needs does not have a usage profile set.",
        )
        validate(
            self.ports[self.connection_port_name].active_periods is not None,
            f"{self.node_name} connection_point port does not have available set.",
        )
        validate(
            self.ports["vehicle"].initial_state_of_charge is not None,
            f"{self.node_name} vehicle port does not have a initial_state_of_charge set.",
        )

    def set_port_uid_maps(self) -> None:
        """Sets the two maps for port names and port uids, if they aren't already set.

        Args:
            None

        Returns:
            None
        """

        # Set port_dict_name_to_port_uid_map
        if self.port_dict_name_to_port_uid_map is None:
            self.port_dict_name_to_port_uid_map = {port_name: port.uid for port_name, port in self.ports.items()}

        # Set port_dict_name_to_port_name_map
        if self.port_dict_name_to_port_name_map is None:
            self.port_dict_name_to_port_name_map = {port_name: port.port_name for port_name, port in self.ports.items()}


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
        available: ArrayType | list | str,
        usage: ArrayType | list | str,
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

    def _v0g_charging(self, interval_duration: float, force_conv: bool = False) -> tuple[bool, float, float, float]:
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
            self.ports["vehicle"].initial_state_of_charge is not None,
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


class EVV1G(EVBase):
    """An EV with demand managed charging."""

    def __init__(self, **data) -> None:
        super().__init__(**data)

        # Set the charge_mode
        self.charge_mode = EVChargeMode.V1G

        # Create the ports
        self._create_usage_port()
        self._create_vehicle_port()
        self._create_connection_point_port()

        if self.set_stateful_attrs_at_init:
            self.set_stateful_attrs(
                available=self.available,
                usage=self.usage,
                initial_state_of_charge=self.initial_state_of_charge,
                interval_duration=self.interval_duration,
            )

        # EV needs a custom transformation because of the positive load convention
        self.add_transformation(self._create_ev_transformation())

        # Set port_dict_name_to_port_uid_map and port_dict_name_to_port_name_map
        self.set_port_uid_maps()

        # For V1G EVs, need to set max_export constraint to 0.
        self.ports[self.connection_port_name].set_flow_constraints(max_import=self.charging_power_limit, max_export=0.0)

    def set_stateful_attrs(
        self,
        available: ArrayType | list | str,
        usage: ArrayType | list | str,
        initial_state_of_charge: float,
        interval_duration: int,
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

        Returns:
            None
        """

        self.available = available
        self.usage = usage
        self.initial_state_of_charge = initial_state_of_charge
        self.interval_duration = interval_duration

        # Set stateful attributes for usage port
        self._check_usage_less_than_max_usage()
        self.ports["usage"].add_demand_profile_from_array(self.usage, expansion_periods=1)

        # Set stateful data for the connection point port
        self.ports[self.connection_port_name].set_active_periods_from_array(self.available, expansion_periods=1)

        # Set the initial_state_of_charge on the vehicle port
        self.ports["vehicle"].initial_state_of_charge = self.initial_state_of_charge

        # Check that the initial_state_of_charge is between the min_soc and max_capacity
        check_initial_state_of_charge_within_bounds(
            initial_state_of_charge=self.ports["vehicle"].initial_state_of_charge,
            min_soc=self.ports["vehicle"].min_soc,
            max_capacity=self.ports["vehicle"].max_capacity,
        )


class EVV2G(EVBase):
    """An EV with demand managed charging and generation managed discharging for purposes of providing energy to an
    electrical network.
    """

    def __init__(self, **data) -> None:
        super().__init__(**data)

        # Set the charge_mode
        self.charge_mode = EVChargeMode.V2G

        # Create the ports
        self._create_usage_port()
        self._create_vehicle_port()
        self._create_connection_point_port()

        if self.set_stateful_attrs_at_init:
            self.set_stateful_attrs(
                available=self.available,
                usage=self.usage,
                initial_state_of_charge=self.initial_state_of_charge,
                interval_duration=self.interval_duration,
            )

        # EV needs a custom transformation because of the positive load convention
        self.add_transformation(self._create_ev_transformation())

        # Set port_dict_name_to_port_uid_map and port_dict_name_to_port_name_map
        self.set_port_uid_maps()

    def set_stateful_attrs(
        self,
        available: ArrayType | list | str,
        usage: ArrayType | list | str,
        initial_state_of_charge: float,
        interval_duration: int,
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

        Returns:
            None
        """

        self.available = available
        self.usage = usage
        self.initial_state_of_charge = initial_state_of_charge
        self.interval_duration = interval_duration

        # Set stateful attributes for usage port
        self._check_usage_less_than_max_usage()
        self.ports["usage"].add_demand_profile_from_array(self.usage, expansion_periods=1)

        # Set stateful data for the connection point port
        self.ports[self.connection_port_name].set_active_periods_from_array(self.available, expansion_periods=1)

        # Set the initial_state_of_charge on the vehicle port
        self.ports["vehicle"].initial_state_of_charge = self.initial_state_of_charge

        # Check that the initial_state_of_charge is between the min_soc and max_capacity
        check_initial_state_of_charge_within_bounds(
            initial_state_of_charge=self.ports["vehicle"].initial_state_of_charge,
            min_soc=self.ports["vehicle"].min_soc,
            max_capacity=self.ports["vehicle"].max_capacity,
        )


class EVWithProfile(Node):
    """An EV defined through a timeseries profile of demand.

    This EV object is to be used when real world (or modelled) charging data is available; essentially acting as a
    pure load.

    charging_power_limit (float | None): The maximum charging power of the vehicle. Used for data sanity checks only.
        Positive float in units of power.
    demand (dict[str, float] | ArrayType | list[float] | None): The demand data for the EV. Values must be positive
        floats. Values in units of power.
    set_stateful_attrs_at_init (bool | None): Set attributes with state at object instantiation (True) or
        defer to later (False). If deferring to later, self.set_stateful_attrs() must be used to set these
        attributes. Attributes with state are available and initial_state_of_charge. Defaults to True.
    """

    charge_mode: EVChargeMode = EVChargeMode.DemandProfile
    port_name: str | None = "demand"
    port_uid: str | None = Field(default_factory=shortuuid.uuid)
    charging_power_limit: NonNegativeFloat | None

    # Stateful attributes
    set_stateful_attrs_at_init: bool = True
    demand: dict | ArrayType | list | None

    def __init__(self, **data) -> None:
        super().__init__(**data)

        # Set the EV charge mode
        self.charge_mode: EVChargeMode = EVChargeMode.DemandProfile

        # Create the demand port
        self.ports[self.port_name] = ElectricalDemand(
            port_name=self.port_name,
            uid=self.port_uid,
        )

        # Set stateful attributes if required
        if self.set_stateful_attrs_at_init:
            self.set_stateful_attrs(demand=self.demand)

    def set_stateful_attrs(self, demand: dict | ArrayType | list) -> None:
        """Injects attributes with state into EV node and ports.

        Args:
            demand: Timeseries data specifying if the load from the EV charging.

        Returns:
            None
        """

        self.demand = demand

        # Set profile values of the demand port
        if type(self.demand) is dict:
            self.ports[self.port_name].set_initial_value(self.demand)
        else:
            self.ports[self.port_name].set_initial_value_from_array(self.demand)

    def verify_node(self) -> None:
        """Checks data with state has been set for the node and each port.

        Args:
            None

        Returns:
            None
        """

        super().verify_node()

        # Check node properties
        self._check_stateful_attrs_are_not_none()
        self._check_demand_is_not_more_than_max_import()

        # Check ports
        self._verify_ports()

    def _check_stateful_attrs_are_not_none(self) -> None:
        """Check that node attributes with state have been set.

        Args:
            None

        Returns:
            None
        """

        if self.demand is None:
            raise ConfigurationError(
                f"The demand attribute for {self.node_name} has not been set. Please use set_stateful_attrs()."
            )

    def _check_demand_is_not_more_than_max_import(self) -> None:
        """Check that the demand does not breach the maximum import limit of the EV.

        Args:
            None

        Returns:
            None
        """

        if self.charging_power_limit is not None:
            max_demand = np.max(np.array(self.demand))
            if max_demand > self.charging_power_limit:
                raise ValueError(
                    f"Demand requirement of {max_demand} exceeds maximum charging rate of {self.charging_power_limit}."
                )

    def _verify_ports(self) -> None:
        """Check that port attributes with state have been set.

        Args:
            None

        Returns:
            None
        """

        validate(
            self.ports[self.port_name].initial_value != 0,
            f"{self.node_name} demand port '{self.port_name}' does not have a demand profile set. "
            f"Please use set_stateful_attrs() to set it.",
        )


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

        # Display deprecation warning
        warn("Class EV will be deprecated in future versions. Please use EVV0G, EVV1G, EVV2G or EVDemandProfile.")

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
            initial_state_of_charge=(
                initial_state_of_charge if initial_state_of_charge is not None else self.initial_state_of_charge
            ),
            trip_slack=self.trip_slack,
            soc_conserv=self.soc_conserv,
            soc_conserv_cost=self.soc_conserv_cost,
            port_dict_name_to_port_uid_map=self.port_dict_name_to_port_uid_map,
            port_dict_name_to_port_name_map=self.port_dict_name_to_port_name_map,
        )

    def create_ev_transformation(self):
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

    def process_V0G_charging(self, interval_duration: float):
        success, ev_soc, ev_delta, trip_infeasibility = self.V0G_charging(interval_duration)

        self.V0G_delta = ev_delta
        self.V0G_SOC = ev_soc
        if self.tod_charging is not None:
            if success:
                self.charge_status = EVChargeStatus.Feasible
            else:  # force convenience charging
                success, ev_soc, ev_delta, trip_infeasibility = self.V0G_charging(interval_duration, force_conv=True)
                self.charge_status = (
                    EVChargeStatus.TimeOfDayInfeasibleConvenienceFeasible if success else EVChargeStatus.Infeasible
                )
                self.V0G_delta = ev_delta
                self.V0G_SOC = ev_soc

        else:
            self.charge_status = EVChargeStatus.Feasible if success else EVChargeStatus.Infeasible
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

    def verify_node(self):
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

    def add_node_to_model(self, model: EchoConcreteModel, profile):
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


class ElectricalPort(FlexPort):
    """Flexible electrical port"""

    units = Units.KW


class FixedElectricalPort(FixedPort):
    """An electrical port with fixed values (parameters). No constraints on whether the port is importing/exporting."""

    units = Units.KW


class Inverter(Node):
    """An inverter is a node with one AC port and at least one DC port.
    Flows from AC to DC, and DC to AC, are subject to conversion efficiencies.

    Ports can be specified at construction time using the `ac_port_name` and `dc_ports_names` or the ports can be
    added later by making one call to `add_ac_port` and as many calls to `add_dc_port` as required. It is best not
    to mix these two approaches.

    When creating ports through the constructor, the ports will be assigned default uids. If you need to flexibility
    of specifying uids for the ports then use the `add_ac_port` and `add_dc_ports` remembering to supply `uid` values.
    """

    max_import: float | None
    max_export: float | None
    dc_ac_efficiency: float = Field(default=1.0, ge=0, le=1)
    ac_dc_efficiency: float = Field(default=1.0, ge=0, le=1)
    ac_port_name: str | None = None
    dc_port_names: list[str] = Field(default_factory=list)

    def __init__(
        self,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if self.ac_port_name:
            self._add_ac_port(port_name=self.ac_port_name)
        for port_name in self.dc_port_names:
            self._add_port(port_name=port_name)

    def _add_port(self, port_name: str, uid: str | None = None) -> None:
        p = ElectricalPort(port_name=port_name, uid=uid)
        self.ports[port_name] = p

    def _add_ac_port(self, port_name: str, uid: str | None = None) -> None:
        p = ElectricalPort(port_name=port_name, uid=uid)
        p.set_flow_constraints(max_export=self.max_export, max_import=self.max_import)
        self.ports[port_name] = p

    def add_dc_port(self, port_name: str, uid: str | None = None) -> None:
        self.dc_port_names.append(port_name)
        self._add_port(port_name=port_name, uid=uid)

    def add_ac_port(self, port_name: str, uid: str | None = None) -> None:
        self.ac_port_name = port_name
        self._add_ac_port(port_name=self.ac_port_name, uid=uid)

    def verify_node(self) -> None:
        # Check that we have at least one ac and one dc port
        validate(self.ac_port_name is not None, "Define at least one ac port on inverter.")
        validate(self.dc_port_names is not None, "Define at least one dc port on inverter.")
        # Check that all ports are either ac or dc
        all_port_names = [x for x in self.ports.keys()]
        named_ports = [self.ac_port_name] + self.dc_port_names
        validate(
            set(all_port_names) == set(named_ports),
            "All ports on inverter must be ac or dc.",
        )

    def add_node_to_model(self, model: EchoConcreteModel, profile) -> None:
        super().add_node_to_model(model, profile)

        ac_port = self.ports[self.ac_port_name]
        # Split ac port into pos/neg, so we can apply the correct efficiencies
        ac_port.constrain_pos_neg(model)

        def inverter_ac_output_must_track_efficiency(
            model: EchoConcreteModel, p, t
        ) -> None:  # Apply efficiency constraints
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
            en.Constraint(
                model.Expansion,
                model.Time,
                rule=inverter_ac_output_must_track_efficiency,
            ),
        )


class BoundedElectricalLoad(BoundedLoad):
    units = Units.KW
