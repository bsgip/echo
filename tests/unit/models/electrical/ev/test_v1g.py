from echo.configuration import EVChargeMode
from echo.models.electrical.ev.v1g import EVV1G


def test_evv1g_initialisation():
    required_params = {
        "charging_power_limit": 1,
        "discharging_power_limit": -1,
        "max_capacity": 1,
        "set_stateful_attrs_at_init": False,
    }

    ev = EVV1G(**required_params)

    assert ev.charge_mode == EVChargeMode.V1G
    assert len(ev.ports) == 3
    assert len(ev.transformations) == 1
    assert ev.connection_port_name in ev.ports
    port = ev.ports[ev.connection_port_name]
    assert port.export_constraint_value == 0


def test_evv1g_initialisation_stateful_attrs():
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

    ev = EVV1G(**required_params, **stateful_attrs)

    assert ev.charge_mode == EVChargeMode.V1G
    assert len(ev.ports) == 3
    assert len(ev.transformations) == 1

    assert ev.available == stateful_attrs["available"]
    assert ev.usage == stateful_attrs["usage"]
    assert ev.initial_state_of_charge == stateful_attrs["initial_state_of_charge"]
    assert ev.interval_duration == stateful_attrs["interval_duration"]
    assert ev.connection_port_name in ev.ports
    port = ev.ports[ev.connection_port_name]
    assert port.export_constraint_value == 0
