import numpy as np

from echo.configuration import (
    EVChargeMode,
    FlowConstraint,
    Flows,
    OptimisationType,
    TransformRule,
    Units,
)
from echo.exceptions import ConfigurationError, validate
from echo.models.agnostic import MobileStorage
from echo.models.base import Transform, TransformNode, TransformTerm
from echo.models.electrical.base import ElectricalDemand, ElectricalPort
from echo.utils import TimeExpandableType
from echo.validators import ArrayType


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
    ports: dict[str, ElectricalDemand | ElectricalPort | MobileElectricalStorage] = {}

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
    available: ArrayType | list | None
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
            TypeError: if self.usage is None
            ValueError: if the maximum power usage is greater than max_discharge_rate.
        """

        if self.usage is None:
            raise TypeError("self.usage has not been set, it is still None.")

        # Get the maximum power usage
        max_usage = np.max(np.array(self.usage))

        # Check that self.usage_power_limit is not None
        if self.usage_power_limit is None:
            raise ValueError("A value has not been assigned for self.usage_power_limit.")

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
        # Usage ports are not connected to other ports via edges so we set `allow_dangling_port` to True
        self.ports["usage"] = ElectricalDemand(allow_dangling_port=True)

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
            discharging_power_limit=self.usage_power_limit,
            initial_state_of_charge=self.initial_state_of_charge,
            max_capacity=self.max_capacity,
            available=self.available,
            charging_efficiency=self.charging_efficiency,
            depth_of_discharge_limit=self.depth_of_discharge_limit,
            discharging_efficiency=self.discharging_efficiency,
            enable_trip_slack=self.enable_trip_slack,
            soc_conserv=self.soc_conserv,
            soc_conserv_cost=self.soc_conserv_cost,
            allow_dangling_port=True,  # vehicle port is not connect to another port
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
            (isinstance(self.ports["vehicle"], MobileElectricalStorage))
            and (self.ports["vehicle"].initial_state_of_charge) is not None,
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
