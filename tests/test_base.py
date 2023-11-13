from __future__ import division

from typing import List, Tuple

import numpy as np
import pytest

from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.prebuilt import FlexElectricalNode


def test_port_reference_is_made_in_edge():
    """This test whether a port on a node and on an edge are references or copies.

    Ideally they should be references but they are currently copies. This is a pydantic feature to make copies of
    objects when imbedding them in new objects eg. take a port and referencing it in an edge. Trying to work
    around this breaks pydantic philosophy. This indicates that echo needs a redesign.

    This test should currently fail. When trying to fix this issue, remove the asserts from within the with block.

    """

    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(node_name="grid", port_name="grid_to_cp")

    # Create a connection point
    connection_point = TellegenNode(node_name="cp")
    connection_point.add_ports_from_list(["cp_to_grid"], FlexPort, units=Units.KW)

    # Add nodes to the OptimisationGraph
    system.add_node_obj([grid, connection_point])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["grid_to_cp"], connection_point.ports["cp_to_grid"])

    with pytest.raises(Exception):
        assert id(grid.ports["grid_to_cp"]) == id(system.get_edge(("grid", "cp")).vertices[0])
        assert id(connection_point.ports["cp_to_grid"]) == id(system.get_edge(("grid", "cp")).vertices[1])
