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
