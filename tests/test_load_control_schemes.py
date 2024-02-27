import pytest

from echo.configuration import TransformRule, Units
from echo.models.agnostic import FlexPort, TellegenNode, TimeDelayNode
from echo.models.base import Node, OptimisationGraph, Transform, TransformNode, TransformTerm
from echo.models.electrical import BoundedElectricalLoad, ElectricalDemand, ElectricalPort
from echo.models.scenario import ScenarioSettings
from echo.objectives.base import ObjectiveSet, TotalFlow
from echo.optimiser import optimise


def test_simple_bounded_load(engine_settings):
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    load = Node()
    ub = [4] * 24 + [3] * 24
    lb = [0] * 24 + [2] * 24
    l1 = BoundedElectricalLoad(upper_bound=ub, lower_bound=lb)
    load.ports["load"] = l1

    system.add_node_obj([grid, load])
    system.connect_ports_and_create_edge(grid.ports["grid"], l1)

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings,
        graph=system,
        objective_set=ObjectiveSet(objective_list=[TotalFlow(component=grid.ports["grid"])]),
    )

    print(optimise_results.opt_status)
    load_import = optimise_results.values(l1.port_name, 0)

    for i in range(time_periods):
        assert load_import[i] == min(ub[i], lb[i])


@pytest.mark.parametrize("time_delay", [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
def test_time_delay_node(engine_settings, time_delay):
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    td = TimeDelayNode(time_delay=time_delay, input_port_unit=Units.KW, output_port_unit=Units.KW)
    td.ports["input"].set_flow_constraints(max_import=5, max_export=0.0)

    load = Node()
    l1 = ElectricalDemand()
    demand = [0] * 24 + [5] * 24
    l1.add_demand_profile_from_array(demand)
    load.ports["load"] = l1

    system.add_node_obj([grid, td, load])
    system.connect_ports_and_create_edge(grid.ports["grid"], td.ports["input"])
    system.connect_ports_and_create_edge(td.ports["output"], l1)

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings,
        graph=system,
    )

    print(optimise_results.opt_status)
    grid = optimise_results.values(grid.ports["grid"].port_name)
    load_import = optimise_results.values(l1.port_name, 0)

    for i in range(time_periods):
        if i < td.time_delay:
            assert load_import[i] == 0
        else:
            assert load_import[i] == -1 * grid[int(i - td.time_delay)]


def test_feedback_loop(engine_settings):
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    supply = Node()
    s = ElectricalPort()
    s.set_flow_constraints(max_export=-10, max_import=0.0)
    supply.ports["grid"] = s

    cp = TellegenNode()
    cp.add_ports_from_list(["upstream", "supply", "feedback"], FlexPort, units=Units.KW)

    td = TimeDelayNode(input_port_unit=Units.KW, output_port_unit=Units.KW, time_delay=0)

    load = TransformNode()
    l1 = ElectricalDemand()
    demand = [0] * 24 + [5] * 24
    l1.add_demand_profile_from_array(demand)
    excess = ElectricalPort()
    # excess = ElectricalGeneration()
    # excess.add_generation_profile_from_array([-1]*24)
    load.ports["load"] = l1
    load.ports["excess"] = excess
    lhs_terms = [
        TransformTerm(var=l1, rule=TransformRule.Both, weight=1),
        TransformTerm(var=excess, rule=TransformRule.Both, weight=1),
    ]
    t = Transform(lhs_terms=lhs_terms)
    load.add_transformation(t)

    system.add_node_obj([supply, cp, td, load])

    # system.connect_ports_and_create_edge(cp.ports['upstream'], s, edge_name='upstream_to_cp')
    # system.connect_ports_and_create_edge(cp.ports['supply'], l1, edge_name='cp_to_load')
    # system.connect_ports_and_create_edge(excess, td.ports['input'], edge_name='excess_to_td')
    # system.connect_ports_and_create_edge(td.ports['output'], cp.ports['feedback'], edge_name='td_to_feedback')

    system.connect_ports_and_create_edge(cp.ports["upstream"], supply.ports["grid"])
    system.connect_ports_and_create_edge(cp.ports["supply"], load.ports["load"])
    system.connect_ports_and_create_edge(excess, td.ports["input"])
    system.connect_ports_and_create_edge(td.ports["output"], cp.ports["feedback"])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings,
        graph=system,
    )

    # optimiser.objective = sum(getattr(optimiser.model, cp.ports['supply'].port_name)[p, i]
    #                for p in optimiser.model.Expansion for i in optimiser.model.Time)

    print(optimise_results.opt_status)
    cp = optimise_results.values(cp.ports["supply"].port_name)
    load_import = optimise_results.values(l1.port_name, 0)

    for i in range(time_periods):
        if i < td.time_delay:
            assert load_import[i] == 0
        else:
            assert load_import[i] == -1 * cp[int(i - td.time_delay)]
