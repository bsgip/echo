from echo.configuration import (
    EVChargeMode,
)
from echo.models.electrical.ev.base import EVBase
from echo.validators import ArrayType, check_initial_state_of_charge_within_bounds


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
