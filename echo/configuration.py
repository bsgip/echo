class Units(object):
    """ The units in which the optimisation is undertaken. """

    NA = 0  # Used for initialisation but optimisation will fail if units not set prior to execution.
    KW = 1  # Instantaneous electrical power
    CO2 = 2  # Instantaneous CO2e emissions (in kg)
    KWT = 3  # Instantaneous thermal power
    JPS = 4  # Joules per second
    KWh = 5  # kWh
    kVA = 6  # kVA - apparent power
    kVAR = 7  # reactive power


class Flows(object):
    """ Can the asset support two way flows. """

    NA = 0
    Import = 1  # the port can only import
    Export = 2  # the port can only export
    Both = 3  # the port can import and export


class FlowConstraint(object):
    NA = 0
    NoConstraint = 1  # No constraint on flow at this port
    Fixed = 2  # A fixed constraint exists
    Series = 3  # A time series (time varying) constraint exists


class OptimisationType(object):
    NA = 0
    Parameter = 1  # The port variable is fixed
    Variable = 2  # The port variable is variable/optimisable


class NodeRule(object):
    NA = 0
    Tellegen = 1  # The node sums all ports to 0.
    Custom = 2  # The node has some custom transformation
    Transform = 3  # The node has a transformation defined with a Transform object


class TransformRule(object):
    NA = 0
    Both = 1  # the transformation applies to both pos and neg components of the port variable
    PositiveComponent = 2  # " " applies to only the positive component of the port variable
    NegativeComponent = 3  # "" applies to only the negative component of the port variable


class ExpansionType(object):
    NA = 0
    Storage = 1
    Generation = 2
    Edge = 3

class NodeType(object):
    Flex = 'flex'
    Tellegen = 'tellegen'
    Battery = 'battery'
    Load = 'load'
    Generation = 'gen'
    Solar = 'solar'
    EV = 'ev'
    Inverter = 'inverter'
    Chiller = 'chiller'
    Boiler = 'boiler'
    ControlledLoad = 'cload'
    ControlledGen = 'cgen'
    FixedPort = 'fixed_port'
    CarbonAggregation = 'carbon_agg'
    HeatPump = 'heatpump'

class Resource:
    """ Resources/commodities """
    Electricity = 0
    Gas = 1
    Thermal = 2
    CO2 = 3

class TariffType:
    """ Tariff types"""
    import_tariff = 0
    export_tariff = 1
    import_demand_tariff = 2
    export_demand_tariff = 3
    time = 4  # a tariff that applies per time period (eg daily supply charge)

class Resets:
    """ How often something resets """
    minute = 0
    hourly = 1
    daily = 2
    weekly = 3
    yearly = 4


