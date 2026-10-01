from attrs import define

from echo.configuration import (
    Units,
)
from echo.models.agnostic import BoundedLoad, Demand, FixedPort, FlexPort, Storage


@define
class ElectricalDemand(Demand):
    """Fixed electrical demand."""

    units: Units = Units.KW


@define
class ElectricalPort(FlexPort):
    """Flexible electrical port"""

    units: Units = Units.KW


@define
class FixedElectricalPort(FixedPort):
    """An electrical port with fixed values (parameters). No constraints on whether the port is importing/exporting."""

    units: Units = Units.KW


@define
class ElectricalStorage(Storage):
    units: Units = Units.KW


@define
class BoundedElectricalLoad(BoundedLoad):
    units: Units = Units.KW
