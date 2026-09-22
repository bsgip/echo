from echo.configuration import EVChargeMode
from echo.models.electrical.ev import EVWithProfile
import pytest
from pydantic import ValidationError
from echo.models.electrical.base import ElectricalDemand


@pytest.mark.parametrize(
    "charging_power_limit,expected_error",
    [
        (0, None),
        (1, None),
        (100, None),
        (-85, ValidationError),  # -ve
        (-1, ValidationError),  # -ve
    ],
)
def test_ev_with_profile_validation_charging_power_limit(charging_power_limit, expected_error):
    common_params = {"set_stateful_attrs_at_init": False}
    if expected_error:
        with pytest.raises(expected_error):
            EVWithProfile(charging_power_limit=charging_power_limit, **common_params)
    else:
        EVWithProfile(charging_power_limit=charging_power_limit, **common_params)


def test_ev_with_profile_initialisation():
    common_params = {"set_stateful_attrs_at_init": False}

    ev = EVWithProfile(**common_params)
    assert ev.charge_mode == EVChargeMode.DemandProfile

    assert len(ev.ports) == 1
    assert "demand" in ev.ports
    demand_port = ev.ports["demand"]
    assert isinstance(demand_port, ElectricalDemand)
    assert demand_port.port_name == "demand"
    assert demand_port.uid == ev.port_uid


def test_ev_with_profile_initialisation_set_stateful():
    demand_profile = {(0, i): i for i in [0, 1, 2, 3, 4, 5]}

    ev = EVWithProfile(demand=demand_profile)
    assert ev.charge_mode == EVChargeMode.DemandProfile

    assert len(ev.ports) == 1
    assert "demand" in ev.ports
    demand_port = ev.ports["demand"]
    assert isinstance(demand_port, ElectricalDemand)
    assert demand_port.port_name == "demand"
    assert demand_port.uid == ev.port_uid

    assert ev.demand == demand_profile
    assert demand_port.initial_value == demand_profile
