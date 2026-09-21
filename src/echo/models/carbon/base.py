from echo.configuration import Flows, Units
from echo.models.agnostic import FlexPort
from attrs import define, field


@define
class CarbonPort(FlexPort):
    """A flexible carbon port"""

    units = field(default=Units.CO2)


@define
class CarbonSource(CarbonPort):
    """A variable source of CO2"""

    flows = field(default=Flows.Export)


@define
class CarbonSink(CarbonPort):
    """A variable sink of CO2"""

    flows = field(default=Flows.Import)
