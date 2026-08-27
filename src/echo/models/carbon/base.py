from echo.configuration import Flows, Units
from echo.models.agnostic import FlexPort


class CarbonPort(FlexPort):
    """A flexible carbon port"""

    units = Units.CO2


class CarbonSource(CarbonPort):
    """A variable source of CO2"""

    flows = Flows.Export


class CarbonSink(CarbonPort):
    """A variable sink of CO2"""

    flows = Flows.Import
