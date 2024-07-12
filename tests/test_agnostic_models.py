"""Unit testing for thermal models individual classes"""

import numpy as np
import pandas as pd
import pytest

from echo.utils import TimeSeriesData, expand_as_dict
from echo.configuration import Units

from echo.models.agnostic import (
    TellegenNode,
    MultiCommodityTellegenNode,
    PartitionedMultiCommodityTellegenNode,
    FlexPort,
)


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
    """Test only ports or partiotions validation error"""
    with pytest.raises(Exception):
        node = PartitionedMultiCommodityTellegenNode(
            partitions={
                "partition_1": [FlexPort(units=Units.KW), FlexPort(units=Units.KW)],
                "partition_2": [FlexPort(units=Units.KW), FlexPort(units=Units.KW)],
            },
            ports={"port_1": FlexPort(units=Units.KW)},
        )
