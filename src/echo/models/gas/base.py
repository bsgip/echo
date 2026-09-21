from echo.configuration import Units
from echo.models.agnostic import FixedPort, FlexPort
from attrs import define, field


@define
class FlexGasPort(FlexPort):
    """A flexible port with flow units of Joules/second"""

    units = field(default=Units.JPS)


@define
class FixedGasPort(FixedPort):
    """A Fixed port with flow units of Joules/second"""

    units = field(default=Units.JPS)
