from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import EVV0G, EVV1G, EVV2G, ElectricalGeneration, Inverter
from echo.models.prebuilt import FlexElectricalNode
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.objectives.base import ObjectiveSet
from echo.objectives.tariff import ImportTariff
from echo.optimiser import optimise


def test_port_reference_is_made_in_edge():
    """This test whether a port on a node and on an edge are references"""

    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(node_name="grid", port_name="grid_to_cp")

    # Create a connection point
    connection_point = TellegenNode(node_name="cp")
    connection_point.add_ports_from_list(["cp_to_grid"], FlexPort, units=Units.KW)

    # Add nodes to the OptimisationGraph
    system.add_nodes([grid, connection_point])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["grid_to_cp"], connection_point.ports["cp_to_grid"])

    assert grid.ports["grid_to_cp"] is system.get_edge(("grid", "cp")).vertices[0]
    assert connection_point.ports["cp_to_grid"] is system.get_edge(("grid", "cp")).vertices[1]

