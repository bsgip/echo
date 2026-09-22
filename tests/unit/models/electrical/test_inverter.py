from echo.models.electrical import ElectricalPort
import pytest
from pydantic import ValidationError

from echo.models.electrical.inverter import Inverter


@pytest.mark.parametrize(
    "dc_ac_efficiency, ac_dc_efficiency, expected_error",
    [
        (0.0, 0.0, None),
        (1.0, 1.0, None),
        (0.4, 0.7, None),
        (-0.4, 0.7, ValidationError),  # dc_ac_efficiency -ve
        (0.4, -0.7, ValidationError),  # ac_dc_efficiency -ve
    ],
)
def test_inverter_validation(dc_ac_efficiency, ac_dc_efficiency, expected_error):
    if expected_error:
        with pytest.raises(expected_error):
            Inverter(dc_ac_efficiency=dc_ac_efficiency, ac_dc_efficiency=ac_dc_efficiency)
    else:
        Inverter(dc_ac_efficiency=dc_ac_efficiency, ac_dc_efficiency=ac_dc_efficiency)


@pytest.mark.parametrize(
    "ac_port_name, dc_port_names", [(None, []), ("ac", []), (None, ["dc1"]), ("ac", ["dc1", "dc2", "dc3"])]
)
def test_inverter_initialisation(ac_port_name, dc_port_names):
    inverter = Inverter(ac_port_name=ac_port_name, dc_port_names=dc_port_names)

    num_ports = len(dc_port_names) + (ac_port_name is not None)
    assert len(inverter.ports) == num_ports

    if ac_port_name:
        assert ac_port_name in inverter.ports
        assert isinstance(inverter.ports[ac_port_name], ElectricalPort)
    if dc_port_names:
        assert all([name in inverter.ports for name in dc_port_names])
        assert all([isinstance(inverter.ports[name], ElectricalPort) for name in dc_port_names])
