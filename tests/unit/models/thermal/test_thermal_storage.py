import pytest
from pydantic import ValidationError

from echo.configuration import Units
from echo.models.thermal.storage import ThermalStorage

positivefloat_values = [(1, None), (0, ValidationError), (-1, ValidationError)]
positivefloat_attributes = [
    "storage_mass",
    "specific_heat",
    "charging_power_limit",
]
positivefloat_data = [
    ({attribute: value}, error) for attribute in positivefloat_attributes for value, error in positivefloat_values
]

negativefloat_values = [(-1, None), (0, ValidationError), (1, ValidationError)]
negativefloat_attributes = [
    "discharging_power_limit",
]
negativefloat_data = [
    ({attribute: value}, error) for attribute in negativefloat_attributes for value, error in negativefloat_values
]

nonnegativefloat_values = [(1, None), (0, None), (-1, ValidationError)]
nonnegativefloat_attributes = [
    "ins_transmittance",
    "surface_area",
]
nonnegativefloat_data = [
    ({attribute: value}, error) for attribute in nonnegativefloat_attributes for value, error in nonnegativefloat_values
]


@pytest.mark.parametrize(
    "param_to_override, expected_error", [*positivefloat_data, *negativefloat_data, *nonnegativefloat_data]
)
def test_thermalstorage_validation_floats(param_to_override, expected_error):
    required_params = {
        "min_temp": 0,
        "max_temp": 1,
        "storage_mass": 1,
        "specific_heat": 1,
    }
    params = {**required_params, **param_to_override}
    if expected_error:
        with pytest.raises(expected_error):
            ThermalStorage(**params)
    else:
        ThermalStorage(**params)


@pytest.mark.parametrize(
    "units, expected_error",
    [
        (Units.NA, ValidationError),
        (Units.KW, ValidationError),
        (Units.CO2, ValidationError),
        (Units.KWT, None),  # thermal unit
        (Units.JPS, None),  # thermal unit
        (Units.KWh, ValidationError),
        (Units.KVA, ValidationError),
        (Units.KVAR, ValidationError),
        (Units.LPS, ValidationError),
        (Units.CMS, ValidationError),
    ],
)
def test_thermalstorage_validation_units(units, expected_error):
    params = {
        "min_temp": 0,
        "max_temp": 1,
        "storage_mass": 1,
        "specific_heat": 1,
    }
    if expected_error:
        with pytest.raises(expected_error):
            ThermalStorage(energy_flow_units=units, **params)
    else:
        ThermalStorage(energy_flow_units=units, **params)


@pytest.mark.parametrize(
    "min_temp,max_temp,expected_error",
    [
        (0, 1, None),
        (-1, 0, None),
        (0, 0, ValidationError),  # min_temp == max_temp
        (1, 1, ValidationError),  # min_temp == max_temp
        (1, 0, ValidationError),  # min_temp > max_temp
    ],
)
def test_thermalstorage_validation_temp_range(min_temp, max_temp, expected_error):
    required_params = {
        "min_temp": min_temp,
        "max_temp": max_temp,
        "storage_mass": 1,
        "specific_heat": 1,
    }

    if expected_error:
        with pytest.raises(expected_error):
            ThermalStorage(**required_params)
    else:
        ThermalStorage(**required_params)
