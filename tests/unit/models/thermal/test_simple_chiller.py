import pytest

from echo.models.thermal import SimpleChiller


def test_simple_chiller(cooling_cop_dict):
    """Test asset creation"""
    SimpleChiller(max_cooling_capacity=20, cooling_cop_time_series=cooling_cop_dict)


def test_simple_chiller_cop_error(cooling_cop_dict):
    """Test non negative cop validation error"""
    with pytest.raises(Exception):
        cooling_cop_dict_neg = cooling_cop_dict.copy()
        cooling_cop_dict_neg[(0, 0)] *= -1
        SimpleChiller(max_cooling_capacity=20, cooling_cop_time_series=cooling_cop_dict_neg)
