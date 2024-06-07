"""Unit testing for thermal models individual classes"""

import numpy as np
import pandas as pd
import pytest

from echo.utils import TimeSeriesData, expand_as_dict
from echo.configuration import Units


from echo.models.thermal import ThermalStorage, ParametrisedChiller, SimpleHeatPumpTwoPipe, SimpleChiller


NUMBER_INTERVALS = 5
INTERVAL_DURATION = 30
NUM_EXPANSION_PERIODS = 1


cooling_cop_data = TimeSeriesData(
    value=[2, 3, 1, 2, 2.5], num_time_intervals=NUMBER_INTERVALS, num_expansion_intervals=NUM_EXPANSION_PERIODS
)
cooling_cop_dict = expand_as_dict(cooling_cop_data)

heating_cop_data = TimeSeriesData(
    value=[4, 3, 5, 2, 2.5], num_time_intervals=NUMBER_INTERVALS, num_expansion_intervals=NUM_EXPANSION_PERIODS
)
heating_cop_dict = expand_as_dict(heating_cop_data)


def test_simple_chiller():
    """Test asset creation"""
    chiller = SimpleChiller(max_cooling_capacity=20, cooling_cop_time_series=cooling_cop_dict)


def test_simple_chiller_cop_error():
    """Test non negative cop validation error"""
    with pytest.raises(Exception):
        cooling_cop_dict_neg = cooling_cop_dict.copy()
        cooling_cop_dict_neg[(0, 0)] *= -1
        chiller = SimpleChiller(max_cooling_capacity=20, cooling_cop_time_series=cooling_cop_dict_neg)


def test_simple_heatpump():
    """Test asset creation and default ports."""
    hp = SimpleHeatPumpTwoPipe(cooling_cop_time_series=cooling_cop_dict, heating_cop_time_series=heating_cop_dict)
    assert len(hp.ports) == 2

    hp_dual_output = SimpleHeatPumpTwoPipe(
        cooling_cop_time_series=cooling_cop_dict, heating_cop_time_series=heating_cop_dict, dual_output=True
    )
    assert len(hp_dual_output.ports) == 3
    assert len([p for p in hp_dual_output.ports.values() if p.units == Units.KWT]) == 2


def test_simple_heatpump_cop_error():
    """Test non negative cop validation error"""
    with pytest.raises(Exception):
        cooling_cop_dict_neg = cooling_cop_dict.copy()
        cooling_cop_dict_neg[(0, 0)] *= -1
        hp = SimpleHeatPumpTwoPipe(
            cooling_cop_time_series=cooling_cop_dict_neg, heating_cop_time_series=heating_cop_dict
        )
    with pytest.raises(Exception):
        heating_cop_dict_neg = heating_cop_dict.copy()
        heating_cop_dict_neg[(0, 0)] *= -1
        hp = SimpleHeatPumpTwoPipe(
            cooling_cop_time_series=cooling_cop_dict, heating_cop_time_series=heating_cop_dict_neg
        )
