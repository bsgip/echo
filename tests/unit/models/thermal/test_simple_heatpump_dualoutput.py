import pytest
from pydantic import ValidationError

from echo.configuration import Units
from echo.models.thermal import SimpleHeatPumpDualOutput


def test_simple_heatpump_dual_output(cooling_cop_dict, heating_cop_dict):
    """Test creation and assert default ports."""
    hp_dual_output = SimpleHeatPumpDualOutput(
        cooling_cop_time_series=cooling_cop_dict,
        heating_cop_time_series=heating_cop_dict,
        dual_output=True,
    )
    assert len(hp_dual_output.ports) == 3
    assert len([p for p in hp_dual_output.ports.values() if p.units == Units.KWT]) == 2


@pytest.mark.parametrize("waste_heat_recovery_coeff, expected_error", [(1, None), (0, None), (-1, ValidationError)])
def test_simpleheatpump_dual_output_validation(waste_heat_recovery_coeff, expected_error):
    if expected_error:
        with pytest.raises(expected_error):
            SimpleHeatPumpDualOutput(waste_heat_recovery_coeff=waste_heat_recovery_coeff)
    else:
        SimpleHeatPumpDualOutput(waste_heat_recovery_coeff=waste_heat_recovery_coeff)
