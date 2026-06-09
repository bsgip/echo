"""Unit testing for thermal models individual classes"""

import pyomo.environ as en
import pytest

from echo.configuration import Units
from echo.models.agnostic import (FlexPort,
                                  PartitionedMultiCommodityTellegenNode,
                                  ThreeWayValveNode)
from echo.models.scenario import (EchoConcreteModel, ScenarioSettings,
                                  engine_settings_from_environment)


def empty_model():
    model = EchoConcreteModel()
    engine_settings = engine_settings_from_environment()
    scenario_settings = ScenarioSettings(
        interval_duration=30,
        number_of_intervals=6,
        number_of_expansion_intervals=1,
    )
    model.smallM = en.Param(initialize=engine_settings.smallM)
    model.bigM = en.Param(initialize=engine_settings.bigM)
    model.scenario_settings = scenario_settings
    model.Time = en.RangeSet(0, scenario_settings.number_of_intervals - 1)
    if scenario_settings.number_of_expansion_intervals == 0:
        model.Expansion = en.RangeSet(0, 0)
    else:
        model.Expansion = en.RangeSet(0, scenario_settings.number_of_expansion_intervals - 1)
    discount_rates = {}
    for ep in range(0, scenario_settings.number_of_expansion_intervals):
        discount_rates[ep] = 1 / ((1 + scenario_settings.discount_rate) ** ep)
    model.discount_rates = en.Param(model.Expansion, initialize=discount_rates)
    return model


def test_partitioned_muticommodity_tellegen_node_default_partition():
    """Test asset creation with default partition"""
    node = PartitionedMultiCommodityTellegenNode(ports={"port_1": FlexPort(units=Units.KW)})
    assert node.ports["port_1"] in node.partitions[node.default_partition]


def test_partitioned_muticommodity_tellegen_node():
    """Test asset creation with two partitions"""
    node = PartitionedMultiCommodityTellegenNode(
        partitions={
            "partition_1": [FlexPort(units=Units.KW), FlexPort(units=Units.KW)],
            "partition_2": [FlexPort(units=Units.KW), FlexPort(units=Units.KW)],
        }
    )
    all_partition_ports = [_port.uid for v in node.partitions.values() for _port in v]
    all_ports = [_port.uid for _port in node.ports.values()]
    assert all_partition_ports == all_ports


def test_partitioned_node_add_port():
    """Test asset creation"""

    node = PartitionedMultiCommodityTellegenNode(
        partitions={
            "partition_1": [FlexPort(units=Units.KW), FlexPort(units=Units.KW)],
            "partition_2": [FlexPort(units=Units.KW), FlexPort(units=Units.KW)],
        }
    )
    start_number_ports = len(node.ports)
    node.add_port(name="test_port", port=FlexPort(units=Units.KWT))
    assert node.ports["test_port"]
    assert node.ports["test_port"] in node.partitions[node.default_partition]
    assert len(node.ports) == start_number_ports + 1


def test_partitioned_node_error():
    """Test only ports or partitions validation error"""
    with pytest.raises(Exception):
        PartitionedMultiCommodityTellegenNode(
            partitions={
                "partition_1": [FlexPort(units=Units.KW), FlexPort(units=Units.KW)],
                "partition_2": [FlexPort(units=Units.KW), FlexPort(units=Units.KW)],
            },
            ports={"port_1": FlexPort(units=Units.KW)},
        )


def test_threeway_tellegen_node():
    """Test asset creation and pyomo constraints"""

    node = ThreeWayValveNode(
        node_name="three_way_valve",
        units=Units.KW,
        input_port_name="port_1",
        output_port_name_1="port_2",
        output_port_name_2="port_3",
    )
    model = empty_model()
    node.add_node_to_model(model, profile=None)
    node.apply_node_constraints(model)
    assert getattr(model, node.constraint_neg_flow_mutually_exclusive_port_1) is not None
    assert getattr(model, node.constraint_neg_flow_mutually_exclusive_port_2) is not None
    assert getattr(model, node.constraint_pos_flow_mutually_exclusive_port_1) is not None
    assert getattr(model, node.constraint_pos_flow_mutually_exclusive_port_2) is not None


def test_threeway_tellegen_node_add_port():
    """Test asset creation, add ports and pyomo constraints"""

    node = ThreeWayValveNode(
        node_name="three_way_valve",
        units=Units.KW,
        input_port_name="port_1",
        output_port_name_1="port_2",
        output_port_name_2="port_3",
    )
    node.add_port(name="port_4", port=FlexPort(units=Units.KW))
    node.add_port(name="port_5", port=FlexPort(units=Units.KW))
    model = empty_model()
    node.add_node_to_model(model, profile=None)
    node.apply_node_constraints(model)
    assert getattr(model, node.constraint_neg_flow_mutually_exclusive_port_1) is not None
    assert getattr(model, node.constraint_neg_flow_mutually_exclusive_port_2) is not None
    assert getattr(model, node.constraint_pos_flow_mutually_exclusive_port_1) is not None
    assert getattr(model, node.constraint_pos_flow_mutually_exclusive_port_2) is not None
