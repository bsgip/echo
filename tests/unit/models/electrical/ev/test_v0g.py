
from echo.configuration import EVChargeMode
from echo.models.electrical.ev.v0g import EVV0G


def test_evv0g_initialisation():
    required_params = {
        "charging_power_limit": 1,
        "discharging_power_limit": -1,
        "max_capacity": 1,
        "set_stateful_attrs_at_init": False,
    }

    ev = EVV0G(**required_params)

    assert ev.charge_mode == EVChargeMode.V0G
    assert len(ev.ports) == 3
    assert len(ev.transformations) == 1


def test_evv0g_initialisation_stateful_attrs():
    required_params = {
        "charging_power_limit": 1,
        "discharging_power_limit": -1,
        "max_capacity": 1,
        "set_stateful_attrs_at_init": True,
    }
    stateful_attrs = {
        "available": [1],
        "usage": [1],
        "initial_state_of_charge": 1,
        "interval_duration": 1,
    }

    ev = EVV0G(**required_params, **stateful_attrs)

    assert ev.charge_mode == EVChargeMode.V0G
    assert len(ev.ports) == 3
    assert len(ev.transformations) == 1

    assert ev.available == stateful_attrs["available"]
    assert ev.usage == stateful_attrs["usage"]
    assert ev.initial_state_of_charge == stateful_attrs["initial_state_of_charge"]
    assert ev.interval_duration == stateful_attrs["interval_duration"]
