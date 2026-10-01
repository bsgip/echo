from attrs import define

from echo.configuration import Flows, Units
from echo.models.agnostic import FlexPort


@define
class CarbonPort(FlexPort):
    """A flexible carbon port"""

    units: Units = Units.CO2


@define
class CarbonSource(CarbonPort):
    """A variable source of CO2"""

    flows: Flows = Flows.Export


@define
class CarbonSink(CarbonPort):
    """A variable sink of CO2"""

    flows: Flows = Flows.Import
