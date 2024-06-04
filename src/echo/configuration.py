""" Enumerations of possible configurations for echo model components.

"""

from enum import Enum


class Units(Enum):
    """Enumeration object containing units in which the optimisation is undertaken."""

    NA = 0
    """Used for initialisation but optimisation will fail if units not set prior to execution."""
    KW = 1
    """Instantaneous electrical real power kW"""
    CO2 = 2
    """Instantaneous CO2e emissions (in kg)"""
    KWT = 3
    """Instantaneous thermal power"""
    JPS = 4
    """Joules per second"""
    KWh = 5
    """Electrical energy kWh"""
    kVA = 6
    """Instantaneous electrical apparent power kVA """
    kVAR = 7
    """Instantaneous electrical reactive power kVAR """
    LPS = 8
    """Kilogram of Hydrogen """
    H2Kg = 9


class Flows(Enum):
    """Enumeration object defining the direction of commodity flow supported by the Port."""

    NA = 0
    """flow direction for the port is not defined"""
    Import = 1
    """the port supports only import"""
    Export = 2
    """the port supports only export"""
    Both = 3
    """the port supports two-way flow (import and export)"""


class FlowConstraint(Enum):
    """Enumeration object defining the type (format) of constraint at the Port."""

    NA = 0
    """Constraint type is not specified for this port"""
    NoConstraint = 1
    """No constraint on flow at this port"""
    Fixed = 2
    """A fixed constraint exists"""
    Series = 3
    """A time series (time varying) constraint exists"""
    InRange = 4
    """A lower bound constraint and upper bound constraint exist at this port"""


class OptimisationType(Enum):
    """Enumeration object defining the type Port value variable in optimisation context."""

    NA = 0
    """Value type is not specified for this port"""
    Parameter = 1
    """The port value variable is fixed"""
    Variable = 2
    """The port variable is variable/optimisable"""


class TransformRule(Enum):
    """Enumeration object defining to which component of the Port value the Transformation Rule applies"""

    NA = 0
    """Not specified for this Port"""
    Both = 1
    """The transformation applies to both pos and neg components of the port variable"""
    Pos = 2
    """The transformation applies to only the positive component of the port variable"""
    Neg = 3
    """The transformation applies to only the negative component of the port variable"""


class ExpansionType(Enum):
    """Enumeration object defining the type of Expansion"""

    NA = 0
    """Not specified"""
    Storage = 1
    """Energy storage expansion"""
    Generation = 2
    """Energy generation expansion"""
    Edge = 3
    """Energy throughput (Edge capacity) expansion"""


class NodeType(Enum):
    """Enumeration of Node types"""

    ElectricalFlex = "electrical_flex"
    ElectricalTellegen = "elec_tellegen"
    MultiCommodityTellegen = "multi_commodity_tellegen"
    Battery = "battery"
    ElectricalLoad = "load"
    ElectricalGeneration = "elec_gen"
    Solar = "solar"
    """Solar generator (PV) Node"""
    EV = "ev"
    V0GEV = "v0g_ev"
    V1GEV = "v1g_ev"
    V2GEV = "v2g_ev"
    Inverter = "inverter"
    """DC/AC inverter Node"""
    Chiller = "chiller"
    GasBoiler = "gas_boiler"
    ControlledElectricalLoad = "cload_elec"
    ControlledElectricalGen = "cgen_elec"
    FixedElectrical = "fixed_elec"
    FixedGas = "fixed_gas"
    CarbonAggregation = "carbon_agg"
    """CO2 aggregation Node"""
    HeatPump = "heatpump"
    """Heat water pump Node"""
    FlexWithEmissions = "flex_with_emissions"


class Resource(Enum):
    """Enumeration object defining the types of Energy Resources (Commodities)"""

    Electricity = 0
    """Electricity"""
    Gas = 1
    """Gas"""
    Thermal = 2
    """Thermal"""
    CO2 = 3
    """CO2 (emissions)"""


class TariffType(Enum):
    """Tariff types"""

    ImportTariff = "import tariff"
    ExportTariff = "export tariff"
    ImportDemandTariff = "import demand tariff"
    ExportDemandTariff = "export demand tariff"
    ThroughputCost = "throughput cost"
    PeakPosPower = "peak positive power"
    PeakNegPower = "peak negative power"
    QuadraticPower = "quadratic power"
    ContingencyPositive = "contingency positive"
    ContingencyNegative = "contingency negative"


class Resets(Enum):
    """How often something resets"""

    minute = "minute"
    hourly = "hourly"
    daily = "daily"
    weekly = "weekly"
    yearly = "annually"


class EVChargeMode(Enum):
    """Enumeration of EV class charging modes"""

    V0G = "V0G"
    V1G = "V1G"
    V2G = "V2G"
