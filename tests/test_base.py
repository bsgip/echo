from __future__ import division

import pytest

from echo.configuration import EVChargeMode, Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import EVV0G, EVV1G, EVV2G, ElectricalGeneration, Inverter
from echo.models.prebuilt import FlexElectricalNode
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.objectives.base import ObjectiveSet
from echo.objectives.tariff import ImportTariff
from echo.optimiser import optimise


def test_port_reference_is_made_in_edge():
    """This test whether a port on a node and on an edge are references or copies.

    Ideally they should be references but they are currently copies. This is a pydantic feature to make copies of
    objects when embedding them in new objects eg. take a port and referencing it in an edge. Trying to work
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


def test_rebuild_all_edges():
    """Tests the rebuild_all_edges function usage after stateful data has been injected."""

    def assert_node_edge_port_values(
        v0g_node_port_value: float,
        v0g_edge_port_value: float,
        v12g_node_value: float | None,
        v12g_edge_value: float | None,
    ):
        # Assert that stateful attrs are blank
        if isinstance(ev, EVV0G):
            # Assert ev port on node is blank
            assert ev.ports["ev_to_cp"].initial_value == v0g_node_port_value

            # Assert ev port on the edge is blank
            for edge_name in system.edge_list():
                print(edge_name)
                if "ev" in edge_name:
                    assert ev.ports["ev_to_cp"].initial_value == v0g_edge_port_value
        else:
            # Assert ev port on node is blank
            assert ev.ports["ev_to_cp"].active_periods == v12g_node_value

            # Assert ev port on the edge is blank
            for edge_name in system.edge_list():
                print(edge_name)
                if "ev" in edge_name:
                    assert ev.ports["ev_to_cp"].active_periods == v12g_edge_value

    # Define parameters
    import_tariff = [1, 1, 1, 1, 1, 1]  # $/kw
    interval_duration = 60
    time_periods = len(import_tariff)
    expansion_periods = 1  # not yet implemented leave as 1
    discount_rate = 0  # not yet implemented leave as 0

    # Define stateful attrs
    solar_data = [-1, -1, -1, -1, -1, -1]  # kw load
    available = [1, 1, 0, 0, 1, 0]
    usage = [0, 0, 5, 5, 0, 5]
    initial_state_of_charge = 0

    for EV in [EVV0G, EVV1G, EVV2G]:
        # Create graph
        system = OptimisationGraph()

        # Create an infinite grid node with one downstream port
        grid = FlexElectricalNode(node_name="grid", port_name="grid_to_cp")

        # Create a connection point
        connection_point = TellegenNode(node_name="connection_point")
        connection_point.add_ports_from_list(["cp_to_grid", "cp_to_inverter", "cp_to_ev"], FlexPort, units=Units.KW)

        # create a node for the solar
        solar = Node(node_name="solar")
        pv = ElectricalGeneration()  # create an electrical generation object
        pv.curtailable = False  # set whether this can be curtailed or not
        solar.ports["solar_to_inverter"] = pv  # add the electrical generation to a port on the solar node

        # Create an inverter to attach the solar to
        inverter = Inverter(
            node_name="inverter",
            max_import=None,
            max_export=None,
            dc_ac_efficiency=1,
            ac_dc_efficiency=1,
            ac_port_name="inverter_to_cp",
            dc_port_names=["inverter_to_solar"],
        )

        ev = EV(
            node_name="ev",
            connection_port_name="ev_to_cp",
            max_capacity=20,
            charging_power_limit=5,
            discharging_power_limit=-5,
            set_stateful_attrs_at_init=False,
        )

        # Add nodes to the OptimisationGraph
        system.add_node_obj([grid, connection_point, inverter, solar, ev])

        # Create edge objects and add to graph
        system.connect_ports_and_create_edge(grid.ports["grid_to_cp"], connection_point.ports["cp_to_grid"])
        system.connect_ports_and_create_edge(connection_point.ports["cp_to_inverter"], inverter.ports["inverter_to_cp"])
        system.connect_ports_and_create_edge(inverter.ports["inverter_to_solar"], solar.ports["solar_to_inverter"])
        system.connect_ports_and_create_edge(connection_point.ports["cp_to_ev"], ev.ports["ev_to_cp"])

        # Create objectives/tariffs
        import_cost = ImportTariff(
            component=connection_point.ports["cp_to_grid"],
            tariff_array=import_tariff,
            expansion_periods=expansion_periods,
        )
        objective_set = ObjectiveSet(objective_list=[import_cost])

        # Set solar stateful attrs
        pv.add_generation_profile_from_array(solar_data, expansion_periods)

        assert_node_edge_port_values(
            v0g_node_port_value=0,
            v0g_edge_port_value=0,
            v12g_node_value=None,
            v12g_edge_value=None,
        )

        # Set ev stateful attrs
        ev.set_stateful_attrs(
            available=available,
            usage=usage,
            initial_state_of_charge=initial_state_of_charge,
            interval_duration=interval_duration,
        )

        assert_node_edge_port_values(
            v0g_node_port_value={(0, 0): 5.0, (0, 1): 5.0, (0, 2): 0.0, (0, 3): 0.0, (0, 4): 5.0, (0, 5): 0.0},
            v0g_edge_port_value={(0, 0): 5.0, (0, 1): 5.0, (0, 2): 0.0, (0, 3): 0.0, (0, 4): 5.0, (0, 5): 0.0},
            v12g_node_value={(0, 0): 1, (0, 1): 1, (0, 2): 0, (0, 3): 0, (0, 4): 1, (0, 5): 0},
            v12g_edge_value={(0, 0): 1, (0, 1): 1, (0, 2): 0, (0, 3): 0, (0, 4): 1, (0, 5): 0},
        )

        # Rebuild all the edges before optimisation
        system.rebuild_all_edges()

        assert_node_edge_port_values(
            v0g_node_port_value={(0, 0): 5.0, (0, 1): 5.0, (0, 2): 0.0, (0, 3): 0.0, (0, 4): 5.0, (0, 5): 0.0},
            v0g_edge_port_value={(0, 0): 5.0, (0, 1): 5.0, (0, 2): 0.0, (0, 3): 0.0, (0, 4): 5.0, (0, 5): 0.0},
            v12g_node_value={(0, 0): 1, (0, 1): 1, (0, 2): 0, (0, 3): 0, (0, 4): 1, (0, 5): 0},
            v12g_edge_value={(0, 0): 1, (0, 1): 1, (0, 2): 0, (0, 3): 0, (0, 4): 1, (0, 5): 0},
        )

        # Invoke the optimiser and optimise
        optimise(
            scenario_settings=ScenarioSettings(
                interval_duration=interval_duration,
                number_of_intervals=time_periods,
                number_of_expansion_intervals=expansion_periods,
                discount_rate=discount_rate,
            ),
            engine_settings=engine_settings_from_environment(),
            graph=system,
            objective_set=objective_set,
        )
