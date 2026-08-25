import numpy as np
import shortuuid
from pydantic import Field, NonNegativeFloat

from echo.configuration import (
    EVChargeMode,
)
from echo.exceptions import ConfigurationError, validate
from echo.models.base import Node
from echo.models.electrical.base import ElectricalDemand
from echo.validators import ArrayType


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
