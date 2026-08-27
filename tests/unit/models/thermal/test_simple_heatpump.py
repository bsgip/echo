import pytest

from echo.models.thermal import SimpleHeatPump


def test_simple_heatpump(cooling_cop_dict, heating_cop_dict):
    """Test creation and assert default ports."""
    hp = SimpleHeatPump(
        cooling_cop_time_series=cooling_cop_dict,
        heating_cop_time_series=heating_cop_dict,
    )
    assert len(hp.ports) == 2


def test_simple_heatpump_cop_error(cooling_cop_dict, heating_cop_dict):
    """Test non negative cop validation error"""
    with pytest.raises(Exception):
        cooling_cop_dict_neg = cooling_cop_dict.copy()
        cooling_cop_dict_neg[(0, 0)] *= -1
        SimpleHeatPump(
            cooling_cop_time_series=cooling_cop_dict_neg,
            heating_cop_time_series=heating_cop_dict,
        )
    with pytest.raises(Exception):
        heating_cop_dict_neg = heating_cop_dict.copy()
        heating_cop_dict_neg[(0, 0)] *= -1
        SimpleHeatPump(
            cooling_cop_time_series=cooling_cop_dict,
            heating_cop_time_series=heating_cop_dict_neg,
        )
