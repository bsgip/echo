"""Integration testing for thermal models individual classes"""

import pandas as pd

from echo.configuration import Units
from echo.models.agnostic import FlexPort, PartitionedMultiCommodityTellegenNode, Sink
from echo.models.base import Node, OptimisationGraph
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.optimiser import optimise

NUMBER_INTERVALS = 10
INTERVAL_DURATION = 30
NUM_EXPANSION_PERIODS = 1

load_1 = [1] * NUMBER_INTERVALS
load_2 = [2] * NUMBER_INTERVALS
load_3 = [2] * NUMBER_INTERVALS
profile_df = pd.DataFrame(
    {
        "thermal_load_1": load_1,
        "thermal_load_2": load_2,
        "thermal_load_3": load_2,
        "electrical_load_1": load_1,
        "electrical_load_2": load_2,
    }
)


def test_partitioned_bus_flows():
    """Test that tellegen rule holds per partition per commodity when using PartitionedMultiCommodityTellegenNode"""
    thermal_mains_1 = Node(node_name="thermal_supply_1", ports={"supply_kwt": FlexPort(units=Units.KWT)})
    thermal_mains_2 = Node(node_name="thermal_supply_2", ports={"supply_kwt": FlexPort(units=Units.KWT)})
    electrical_mains_1 = Node(node_name="electrical_supply_1", ports={"supply_kw": FlexPort(units=Units.KW)})
    electrical_mains_2 = Node(node_name="electrical_supply_2", ports={"supply_kw": FlexPort(units=Units.KW)})

    thermal_load_1 = Node(
        node_name="thermal_load_1",
        ports={"demand_kwt": Sink(units=Units.KWT, initial_value_ref="thermal_load_1")},
    )
    thermal_load_2 = Node(
        node_name="thermal_load_2",
        ports={"demand_kwt": Sink(units=Units.KWT, initial_value_ref="thermal_load_2")},
    )
    thermal_load_3 = Node(
        node_name="thermal_load_3",
        ports={"demand_kwt": Sink(units=Units.KWT, initial_value_ref="thermal_load_3")},
    )
    electrical_load_1 = Node(
        node_name="electrical_load_1",
        ports={"demand_kw": Sink(units=Units.KW, initial_value_ref="electrical_load_1")},
    )
    electrical_load_2 = Node(
        node_name="electrical_load_2",
        ports={"demand_kw": Sink(units=Units.KW, initial_value_ref="electrical_load_2")},
    )

    partitioned_bus = PartitionedMultiCommodityTellegenNode(
        node_name="partitioned_bus",
        partitions={
            "supply_1": [
                FlexPort(port_name="to_thermal_supply_1", units=Units.KWT),
                FlexPort(port_name="to_thermal_demand_1", units=Units.KWT),
                FlexPort(port_name="to_thermal_demand_2", units=Units.KWT),
                FlexPort(port_name="to_electrical_supply_1", units=Units.KW),
                FlexPort(port_name="to_electrical_demand_1", units=Units.KW),
            ],
            "supply_2": [
                FlexPort(port_name="to_thermal_supply_2", units=Units.KWT),
                FlexPort(port_name="to_thermal_demand_3", units=Units.KWT),
                FlexPort(port_name="to_electrical_supply_2", units=Units.KW),
                FlexPort(port_name="to_electrical_demand_2", units=Units.KW),
            ],
        },
    )
    system = OptimisationGraph()
    system.add_node_obj(
        [
            thermal_mains_1,
            thermal_mains_2,
            electrical_mains_1,
            electrical_mains_2,
            thermal_load_1,
            thermal_load_2,
            thermal_load_3,
            electrical_load_1,
            electrical_load_2,
            partitioned_bus,
        ]
    )
    system.connect_ports_and_create_edge(
        partitioned_bus.ports["to_thermal_supply_1"],
        thermal_mains_1.ports["supply_kwt"],
    )
    system.connect_ports_and_create_edge(
        partitioned_bus.ports["to_thermal_demand_1"], thermal_load_1.ports["demand_kwt"]
    )
    system.connect_ports_and_create_edge(
        partitioned_bus.ports["to_thermal_demand_2"], thermal_load_2.ports["demand_kwt"]
    )
    system.connect_ports_and_create_edge(
        partitioned_bus.ports["to_electrical_supply_1"],
        electrical_mains_1.ports["supply_kw"],
    )
    system.connect_ports_and_create_edge(
        partitioned_bus.ports["to_electrical_demand_1"],
        electrical_load_1.ports["demand_kw"],
    )
    system.connect_ports_and_create_edge(
        partitioned_bus.ports["to_thermal_supply_2"],
        thermal_mains_2.ports["supply_kwt"],
    )
    system.connect_ports_and_create_edge(
        partitioned_bus.ports["to_thermal_demand_3"], thermal_load_3.ports["demand_kwt"]
    )
    system.connect_ports_and_create_edge(
        partitioned_bus.ports["to_electrical_supply_2"],
        electrical_mains_2.ports["supply_kw"],
    )
    system.connect_ports_and_create_edge(
        partitioned_bus.ports["to_electrical_demand_2"],
        electrical_load_2.ports["demand_kw"],
    )

    optimise_results_no = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=INTERVAL_DURATION,
            number_of_intervals=NUMBER_INTERVALS,
            number_of_expansion_intervals=NUM_EXPANSION_PERIODS,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        profile=profile_df,
    )

    partition_commodity_ports = dict()
    for _partition, _ports in partitioned_bus.partitions.items():
        for _p in _ports:
            _commodity = _p.units
            if not partition_commodity_ports.get((_partition, _commodity)):
                partition_commodity_ports[(_partition, _commodity)] = [_p.port_name]
            else:
                partition_commodity_ports[(_partition, _commodity)].append(_p.port_name)

    for port_list in partition_commodity_ports.values():
        net_flow_per_period = optimise_results_no.df_by_port()[port_list].sum(axis=1).values
        assert all([v == 0 for v in net_flow_per_period])
