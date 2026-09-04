from unittest.mock import MagicMock

import pytest
import shortuuid

from echo.exceptions import ConfigurationError
from echo.models.base.node import Node
from echo.models.base.port import Port


def test_node_name():
    name = "my-node-name"
    node = Node(node_name=name)
    assert node.node_name == name

    node = Node()
    basename = "node_"
    assert node.node_name.startswith(basename)
    assert len(node.node_name) == len(shortuuid.uuid()) + len(basename)


def test_add_port():
    num_ports = 9
    ports = [Port(port_name=f"port_{i}") for i in range(num_ports)]

    node = Node()
    for p in ports:
        node.add_port(p.port_name, p)

    assert len(node.ports) == len(ports)
    assert node.num_ports() == len(ports)
    for p in ports:
        assert node.get_port(p.port_name) == p


def test_add_ports_from_list():
    num_ports = 9
    port_names = [f"port_{i}" for i in range(num_ports)]

    node = Node()
    node.add_ports_from_list(names=port_names, port_type=Port)

    assert len(node.ports) == len(port_names)
    assert node.num_ports() == len(port_names)


def test_verify_ports_raises_configurationerror():
    node = Node()
    with pytest.raises(ConfigurationError):
        node.verify_node()


def test_add_node_to_model(empty_model):
    node = Node(node_name="node_1")
    port_instance = MagicMock()
    port_instance.verify_port.return_value = None
    port_instance.add_port_to_model.return_value = None

    node.add_port("port_1", port_instance)
    model = empty_model()
    node.add_node_to_model(model, profile=None)

    port_instance.verify_port.assert_called_once()
    port_instance.add_port_to_model.assert_called_once_with(model, None)
