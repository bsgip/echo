from attrs import define

from echo.configuration import Units
from echo.models.agnostic import FixedPort, FlexPort


@define
class FlexGasPort(FlexPort):
    """A flexible port with flow units of Joules/second"""

    units: Units = Units.JPS


@define
class FixedGasPort(FixedPort):
    """A Fixed port with flow units of Joules/second"""

    units: Units = Units.JPS
