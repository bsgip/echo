from echo.configuration import Units
from echo.models.agnostic import FixedPort, FlexPort


class FlexGasPort(FlexPort):
    """A flexible port with flow units of Joules/second"""

    units = Units.JPS


class FixedGasPort(FixedPort):
    """A Fixed port with flow units of Joules/second"""

    units = Units.JPS
