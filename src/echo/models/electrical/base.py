from echo.configuration import (
    Units,
)
from echo.models.agnostic import BoundedLoad, Demand, FixedPort, FlexPort, Storage


class ElectricalDemand(Demand):
    """Fixed electrical demand."""

    units = Units.KW


class ElectricalPort(FlexPort):
    """Flexible electrical port"""

    units = Units.KW


class FixedElectricalPort(FixedPort):
    """An electrical port with fixed values (parameters). No constraints on whether the port is importing/exporting."""

    units = Units.KW


class ElectricalStorage(Storage):
    units = Units.KW


class BoundedElectricalLoad(BoundedLoad):
    units = Units.KW
