from echo.configuration import (
    Units,
)
from echo.models.agnostic import BoundedLoad, Demand, FixedPort, FlexPort, Storage
from attrs import define, field


@define
class ElectricalDemand(Demand):
    """Fixed electrical demand."""

    units = field(default=Units.KW)


@define
class ElectricalPort(FlexPort):
    """Flexible electrical port"""

    units = field(default=Units.KW)


@define
class FixedElectricalPort(FixedPort):
    """An electrical port with fixed values (parameters). No constraints on whether the port is importing/exporting."""

    units = field(default=Units.KW)


@define
class ElectricalStorage(Storage):
    units = field(default=Units.KW)


@define
class BoundedElectricalLoad(BoundedLoad):
    units = field(default=Units.KW)
