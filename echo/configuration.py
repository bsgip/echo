""" Enumerations of possible configurations for echo model components.

"""

class Units(object):
    """ Enumeration object containing units in which the optimisation is undertaken.
    """

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


class Flows(object):
    """ Enumeration object defining the direction of commodity flow supported by the Port.
    """

    NA = 0
    """flow direction for the port is not defined"""
    Import = 1
    """the port supports only import"""
    Export = 2
    """the port supports only export"""
    Both = 3
    """the port supports two-way flow (import and export)"""


class FlowConstraint(object):
    """ Enumeration object defining the type (format) of constraint at the Port.
    """

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


class OptimisationType(object):
    """ Enumeration object defining the type Port value variable in optimisation context.
    """
    NA = 0
    """Value type is not specified for this port"""
    Parameter = 1
    """The port value variable is fixed"""
    Variable = 2
    """The port variable is variable/optimisable"""


class NodeRule(object):
    """ Enumeration object defining the type Transformation for the Node object.
    """
    NA = 0
    """Transformation type is not specified for this Node"""
    Tellegen = 1
    """The Node sums all port values to 0"""
    Custom = 2
    """The Node has a custom defined transformation rule"""
    Transform = 3
    """The Node has a transformation rule defined with a Transform object"""


class TransformRule(object):
    """ Enumeration object defining to which component of the Port value the Transformation Rule applies
    """
    NA = 0
    """Not specified for this Port"""
    Both = 1
    """The transformation applies to both pos and neg components of the port variable"""
    PositiveComponent = 2
    """The transformation applies to only the positive component of the port variable"""
    NegativeComponent = 3
    """The transformation applies to only the negative component of the port variable"""


class ExpansionType(object):
    """ Enumeration object defining the type of Expansion
    """
    NA = 0
    """Not specified"""
    Storage = 1
    """Energy storage expansion"""
    Generation = 2
    """Energy generation expansion"""
    Edge = 3
    """Energy throughput (Edge capacity) expansion"""

class NodeType(object):
    """ Enumeration object defining the types of Assets a Node can represent
    """
    Flex = 'flex'
    """Flexible Node"""
    Tellegen = 'tellegen'
    """Tellegen Node"""
    Battery = 'battery'
    """Battery Node"""
    Load = 'load'
    """Load (Energy consumer) Node"""
    Generation = 'gen'
    """Generator (Energy source) Node"""
    Solar = 'solar'
    """Solar generator (PV) Node"""
    EV = 'ev'
    """Electric Vehicle Node"""
    Inverter = 'inverter'
    """DC/AC inverter Node"""
    Chiller = 'chiller'
    """Water Chiller Node"""
    Boiler = 'boiler'
    """Water Boiler Node"""
    ControlledLoad = 'cload'
    """Controlled Energy consumer Node"""
    ControlledGen = 'cgen'
    """Controlled Energy generation Node"""
    FixedPort = 'fixed_port'
    """Fixed port Node"""
    CarbonAggregation = 'carbon_agg'
    """CO2 aggregation Node"""
    HeatPump = 'heatpump'
    """Heat water pump Node"""

class Resource:
    """ Enumeration object defining the types of Energy Resources (Commodities)
    """
    Electricity = 0
    """Electricity"""
    Gas = 1
    """Gas"""
    Thermal = 2
    """Thermal"""
    CO2 = 3
    """CO2 (emissions)"""

class TariffType:
    """ Enumeration object defining the types of Tariff
    """
    import_tariff = 0
    """Triff applies to import only"""
    export_tariff = 1
    """Triff applies to export only"""
    import_demand_tariff = 2
    """Triff applies to peak demand import only"""
    export_demand_tariff = 3
    """Triff applies to peak export import only"""
    time = 4
    """A tariff that applies per time period (e.g. daily supply charge)"""

class Resets:
    """ numeration object defining the frequency of resets
    """
    minute = 0
    """Reset every minute"""
    hourly = 1
    """Reset every hour"""
    daily = 2
    """Reset every day"""
    weekly = 3
    """Reset every week"""
    yearly = 4
    """Reset every year"""


