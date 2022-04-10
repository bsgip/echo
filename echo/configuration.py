class Units(object):
    """ The units in which the optimisation is undertaken. """

    NA = 0  # Used for initialisation but optimisation will fail if units not set prior to execution.
    KW = 1  # Instantaneous electrical power
    CO2 = 2  # Instantaneous CO2e emissions (in kg)
    KWT = 3  # Instantaneous thermal power
    Jps = 4  # Joules per second


class Flows(object):
    """ Can the asset support two way flows. """

    NA = 0
    Import = 1
    Export = 2
    Both = 3


class FlowConstraint(object):
    NA = 0
    NoConstraint = 1
    Fixed = 2
    Series = 3


class OptimisationType(object):
    NA = 0
    Parameter = 1
    Variable = 2


class NodeRule(object):
    NA = 0
    Tellegen = 1
    Sum = 2
    Custom = 3
    Transform = 4


class TransformRule(object):

    NA = 0
    Both = 1
    PositiveComponent = 2
    NegativeComponent = 3


class ExpansionType(object):
    NA = 0
    Storage = 1
    Generation = 2
    Edge = 3

# Define some useful container objects to define the optimisation objectives

class OptimiserObjective(object):
    ConnectionPointCost = 1
    ConnectionPointEnergy = 2
    ThroughputCost = 3
    Throughput = 4
    GreedyGenerationCharging = 5
    GreedyDemandDischarging = 6
    EqualStorageActions = 7
    ConnectionPointPeakPower = 8
    ConnectionPointQuantisedPeak = 9
    PiecewiseLinear = 10
    LocalModelsCost = 11
    LocalGridMinimiser = 12
    LocalThirdParty = 13
    LocalGridPeakPower = 14


class OptimiserObjectiveSet(object):
    FinancialOptimisation = [OptimiserObjective.ConnectionPointCost,
                             # OptimiserObjective.GreedyGenerationCharging,
                             OptimiserObjective.ThroughputCost,
                             OptimiserObjective.EqualStorageActions]

    EnergyOptimisation = [OptimiserObjective.ConnectionPointEnergy,
                          OptimiserObjective.GreedyGenerationCharging,
                          OptimiserObjective.GreedyDemandDischarging,
                          OptimiserObjective.Throughput,
                          OptimiserObjective.EqualStorageActions]

    PeakOptimisation = [OptimiserObjective.ConnectionPointPeakPower]

    QuantisedPeakOptimisation = [OptimiserObjective.ConnectionPointQuantisedPeak]

    DispatchOptimisation = [OptimiserObjective.PiecewiseLinear] + FinancialOptimisation

    LocalModels = [OptimiserObjective.LocalModelsCost,
                   OptimiserObjective.ThroughputCost,
                   OptimiserObjective.EqualStorageActions]

    LocalModelsThirdParty = [OptimiserObjective.LocalThirdParty,
                             OptimiserObjective.ThroughputCost,
                             OptimiserObjective.EqualStorageActions]

    LocalPeakOptimisation = [OptimiserObjective.LocalGridPeakPower]
