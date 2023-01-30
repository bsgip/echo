"""

Configuration classes

"""
from enum import Enum


class Units(Enum):
    """ The units in which the optimisation is undertaken. """

    NA = 0  # Used for initialisation but optimisation will fail if units not set prior to execution.
    KW = 1  # Instantaneous electrical power
    CO2 = 2  # Instantaneous CO2e emissions (in kg)
    KWT = 3  # Instantaneous thermal power
    JPS = 4  # Joules per second
    KWh = 5  # kWh
    kVA = 6  # kVA - apparent power
    kVAR = 7  # reactive power
    LPS = 8  # diesel/petrol in Litres/second


class Flows(Enum):
    """ Can the asset support two way flows. """

    NA = 0
    Import = 1  # the port can only import
    Export = 2  # the port can only export
    Both = 3  # the port can import and export


class FlowConstraint(Enum):
    NA = 0
    NoConstraint = 1  # No constraint on flow at this port
    Fixed = 2  # A fixed constraint exists
    Series = 3  # A time series (time varying) constraint exists
    InRange = 4  # a lower bound constraint and upper bound constraint exist at this port


class OptimisationType(Enum):
    NA = 0
    Parameter = 1  # The port variable is fixed
    Variable = 2  # The port variable is variable/optimisable


class NodeRule(Enum):
    NA = 0
    Tellegen = 1  # The node sums all ports to 0.
    Custom = 2  # The node has some custom transformation
    Transform = 3  # The node has a transformation defined with a Transform object
    Aggregation = 4


class TransformRule(Enum):
    NA = 0
    Both = 1  # the transformation applies to both pos and neg components of the port variable
    Pos = 2  # " " applies to only the positive component of the port variable
    Neg = 3  # "" applies to only the negative component of the port variable


class ExpansionType(Enum):
    NA = 0
    Storage = 1
    Generation = 2
    Edge = 3


class NodeType(object):
    ElectricalFlex = 'electrical_flex'
    ElectricalTellegen = 'elec_tellegen'
    MultiCommodityTellegen = 'multi_commodity_tellegen'
    Battery = 'battery'
    ElectricalLoad = 'load'
    ElectricalGeneration = 'elec_gen'
    Solar = 'solar'
    EV = 'ev'
    V0GEV = 'v0g_ev'
    V1GEV = 'v1g_ev'
    V2GEV = 'v2g_ev'
    Inverter = 'inverter'
    Chiller = 'chiller'
    GasBoiler = 'gas_boiler'
    ControlledElectricalLoad = 'cload_elec'
    ControlledElectricalGen = 'cgen_elec'
    FixedElectrical = 'fixed_elec'
    FixedGas = 'fixed_gas'
    CarbonAggregation = 'carbon_agg'
    HeatPump = 'heatpump'
    FlexWithEmissions = 'flex_with_emissions'


class Resource:
    """ Resources/commodities """
    Electricity = 0
    Gas = 1
    Thermal = 2
    CO2 = 3


class TariffType:
    """ Tariff types"""
    ImportTariff = 'import tariff'
    ExportTariff = 'export tariff'
    ImportDemandTariff = 'import demand tariff'
    ExportDemandTariff = 'export demand tariff'
    ThroughputCost = 'throughput cost'
    PeakPosPower = 'peak positive power'
    PeakNegPower = 'peak negative power'
    QuadraticPower = 'quadratic power'
    ContingencyPositive = 'contingency positive'
    ContingencyNegative = 'contingency negative'


class Resets:
    """ How often something resets """
    minute = 'minute'
    hourly = 'hourly'
    daily = 'daily'
    weekly = 'weekly'
    yearly = 'annually'


class EVChargeMode:
    V0G = 'V0G'
    V1G = 'V1G'
    V2G = 'V2G'
