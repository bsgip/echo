from echo.configuration import OptimisationType, Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import ElectricalDemand, ElectricalPort, ElectricalStorage
from echo.models.scenario import ScenarioSettings
from echo.objectives.base import ObjectiveSet
from echo.objectives.power import PeakNegativePower, PeakPositivePower
from echo.optimiser import optimise

N_INTERVALS = 48


def test_peak_positive_power_objective(engine_settings):
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    battery1 = Node()
    b1 = ElectricalStorage(
        max_capacity=10,
        depth_of_discharge_limit=0,
        charging_power_limit=2.0,
        discharging_power_limit=-2.0,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=0.0,
    )
    battery1.ports["battery"] = b1

    load1 = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([0.0] * 6 + [2.0] * (N_INTERVALS - 6), expansion_periods)
    load1.ports["demand"] = l1

    site1 = TellegenNode()
    site1.add_ports_from_list(["cp", "load", "bess"], FlexPort, units=Units.KW)
    cp1 = site1.ports["cp"]

    system.add_node_obj([grid, battery1, load1, site1])
    system.connect_ports_and_create_edge(site1.ports["bess"], b1)
    system.connect_ports_and_create_edge(site1.ports["load"], l1)
    system.connect_ports_and_create_edge(cp1, grid.ports["grid"])

    peak_pos_power = PeakPositivePower(component=cp1)
    objective_set = ObjectiveSet(objective_list=[peak_pos_power])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings,
        graph=system,
        objective_set=objective_set,
    )

    sto_p = optimise_results.values(b1.port_name, 0)

    # Check that battery minimises peak pos power (import) by discharging when load is > 0
    for i in range(6, N_INTERVALS):
        assert sto_p[i] == -0.25


def test_peak_negative_power_objective(engine_settings):
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    battery1 = Node()
    b1 = ElectricalStorage(
        max_capacity=10,
        depth_of_discharge_limit=0,
        charging_power_limit=2.0,
        discharging_power_limit=-2.0,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=0.0,
    )
    battery1.ports["battery"] = b1

    load1 = Node()
    l1 = ElectricalPort()
    l1.flow_type = OptimisationType.Parameter
    l1.set_initial_value_from_array([-2.0] * 6 + [2.0] * (N_INTERVALS - 6), expansion_periods)
    load1.ports["demand"] = l1

    site1 = TellegenNode()
    site1.add_ports_from_list(["cp", "load", "bess"], FlexPort, units=Units.KW)
    cp1 = site1.ports["cp"]

    system.add_node_obj([grid, battery1, load1, site1])
    system.connect_ports_and_create_edge(site1.ports["bess"], b1)
    system.connect_ports_and_create_edge(site1.ports["load"], l1)
    system.connect_ports_and_create_edge(cp1, grid.ports["grid"])

    peak_neg_power = PeakNegativePower(component=cp1)
    objective_set = ObjectiveSet(objective_list=[peak_neg_power])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings,
        graph=system,
        objective_set=objective_set,
    )

    sto_p = optimise_results.values(b1.port_name, 0)

    # Check that battery absorbs negative load to minimise peak negative power
    assert sum(sto_p[0:6]) == 2 * 6
