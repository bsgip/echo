from __future__ import division

from typing import List, Tuple

import numpy as np
import pytest

from echo.configuration import Units, EVChargeMode
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import EV, ElectricalDemand
from echo.models.prebuilt import FlexElectricalNode
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.optimiser import optimise


def test_v0g():
    # Set up hyper params
    time_periods = 96  # number of time periods to run the optimisation for
    interval_duration = 15  # each time period is 15 mins long
    expansion_periods = 1  # not yet implemented leave as 1
    discount_rate = 0  # not yet implemented leave as 0

    # Create graph
    system = OptimisationGraph()

    # Create assets
    grid = Node()  # create node representing upstream grid
    grid.add_port(
        "grid", FlexPort(units=Units.KW)
    )  # create a port which will be used to connect this with the connection_point

    # create the connection point (where we will sum everything up)
    connection_point = TellegenNode()
    connection_point.add_ports_from_list(["ev", "grid"], FlexPort, units=Units.KW)

    # Create V0G vehicle

    available = np.array([1] * 48 + [0] * 48)  # bool when at charger
    usage = np.array([0.0] * 48 + [5] * 48)  # kw average during use

    ev_cp = EV(
        charge_mode="V0G",
        available=available,
        usage=usage,
        connection_port_name="cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-1e4,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=20,
        soc_conserv=None,
        soc_conserv_cost=0.0,
        interval_duration=15.0,
        tod_charging=False,
        trip_slack=True,
    )

    system.add_node_obj([grid, ev_cp, connection_point])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(connection_point.ports["ev"], ev_cp.ports["cp"])
    system.connect_ports_and_create_edge(grid.ports["grid"], connection_point.ports["grid"])

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
    )


def test_v0g_2():
    """Like test_v0g, just different parameters."""

    # Set up hyper params
    available = [1] * 7 + [0] * 3  # bool when at charger
    usage = [0.0] * 7 + [5] * 3  # kw average during use
    interval_duration = 10
    time_periods = len(available)
    expansion_periods = 1  # not yet implemented leave as 1
    discount_rate = 0  # not yet implemented leave as 0

    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(port_name="grid")

    # Create a connection point
    connection_point = TellegenNode()
    connection_point.add_ports_from_list(["grid", "ev_v0g"], FlexPort, units=Units.KW)

    # Create V0G vehicle
    ev = EV(
        node_name="ev",
        charge_mode="V0G",
        available=available,
        usage=usage,
        connection_port_name="cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-1e4,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=20,
        soc_conserv=None,
        soc_conserv_cost=0.0,
        interval_duration=interval_duration,
        tod_charging=None,
        trip_slack=True,
    )

    # Check that ev has 3 ports
    assert len(ev.ports.keys()) == 3

    # Add nodes to the OptimisationGraph
    system.add_node_obj([grid, ev, connection_point])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["grid"], connection_point.ports["grid"])
    system.connect_ports_and_create_edge(connection_point.ports["ev_v0g"], ev.ports["cp"])

    # Invoke the optimiser and optimise
    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
            discount_rate=discount_rate,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
    )


def test_v0g_3():
    """Like test_v0g_2, just different parameters, but discharge first, then charge."""

    # Set up hyper params
    available = [0] * 3 + [1] * 7  # bool when at charger
    usage = [5] * 3 + [0] * 7  # kw average during use
    interval_duration = 10
    time_periods = len(available)
    expansion_periods = 1  # not yet implemented leave as 1
    discount_rate = 0  # not yet implemented leave as 0

    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(port_name="grid")

    # Create a connection point
    connection_point = TellegenNode()
    connection_point.add_ports_from_list(["grid", "ev_v0g"], FlexPort, units=Units.KW)

    # Create V0G vehicle
    ev = EV(
        node_name="ev",
        charge_mode="V0G",
        available=available,
        usage=usage,
        connection_port_name="cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-1e4,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=20,
        soc_conserv=None,
        soc_conserv_cost=0.0,
        interval_duration=interval_duration,
        tod_charging=None,
        trip_slack=True,
    )

    # Check that ev has 3 ports
    assert len(ev.ports.keys()) == 3

    # Add nodes to the OptimisationGraph
    system.add_node_obj([grid, ev, connection_point])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["grid"], connection_point.ports["grid"])
    system.connect_ports_and_create_edge(connection_point.ports["ev_v0g"], ev.ports["cp"])

    # Invoke the optimiser and optimise
    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
            discount_rate=discount_rate,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
    )


def test_v0g_with_initialise_data():
    # Extends off test_v0g()

    # Set up hyper params
    time_periods = 96  # number of time periods to run the optimisation for
    interval_duration = 15  # each time period is 15 mins long
    expansion_periods = 1  # not yet implemented leave as 1
    discount_rate = 0  # not yet implemented leave as 0

    # Create graph
    system = OptimisationGraph()

    # Create assets
    grid = Node(node_name="grid")  # create node representing upstream grid
    grid.add_port(
        "cp", FlexPort(units=Units.KW)
    )  # create a port which will be used to connect this with the connection_point

    # create the connection point (where we will sum everything up)
    connection_point = TellegenNode(node_name="cp")
    connection_point.add_ports_from_list(["ev", "grid"], FlexPort, units=Units.KW)

    # Create V0G vehicle

    available = np.array([1] * 48 + [0] * 48)  # bool when at charger
    usage = np.array([0.0] * 48 + [5] * 48)  # kw average during use

    ev_cp = EV(
        node_name="ev",
        charge_mode="V0G",
        available=available,
        usage=usage,
        connection_port_name="cp",
        max_capacity=100,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-1e4,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=20,
        soc_conserv=None,
        soc_conserv_cost=0.0,
        interval_duration=15.0,
        tod_charging=False,
        trip_slack=True,
    )

    system.add_node_obj([grid, ev_cp, connection_point])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(connection_point.ports["ev"], ev_cp.ports["cp"])
    system.connect_ports_and_create_edge(grid.ports["cp"], connection_point.ports["grid"])

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
    )

    new_interval_duration = 30
    new_initial_state_of_charge = 50
    new_time_periods = 6

    # Available and usage combinations that work
    good_available_usages: List[Tuple[np.array, np.array]] = [
        (np.array([1, 1, 1, 1, 1, 1]), np.array([0, 0, 0, 0, 0, 0])),
        (np.array([0, 0, 0, 0, 0, 0]), np.array([1, 1, 1, 1, 1, 1])),
        (np.array([0, 0, 0, 0, 0, 0]), np.array([0, 0, 0, 0, 0, 0])),
        (np.array([1, 1, 0, 0, 1, 1]), np.array([0, 0, 1, 1, 0, 0])),
        (np.array([1, 1, 0, 0, 1, 1]), np.array([0, 0, 10, 10, 0, 0])),
    ]

    for available_usage in good_available_usages:
        system.get_node("ev").initialise_data(
            available=available_usage[0],
            usage=available_usage[1],
            initial_state_of_charge=new_initial_state_of_charge,
            interval_duration=new_interval_duration,
            edge_port=system.get_edge(("cp", "ev")).vertices[1],
        )

        # Optimise
        optimise(
            scenario_settings=ScenarioSettings(
                interval_duration=new_interval_duration,
                number_of_intervals=new_time_periods,
                number_of_expansion_intervals=expansion_periods,
                discount_rate=discount_rate,
            ),
            engine_settings=engine_settings_from_environment(),
            graph=system,
        )

    # Available and usage combinations that will throw an error
    bad_available_usages: List[Tuple[list, list]] = [
        ([1, 1, 1, 1, 1, 1], [1, 1, 1, 1, 1, 1]),
        ([0, 0, 1, 1, 0, 0], [0, 0, 1, 1, 0, 0]),
        ([1, 1, 0, 0, 1, 1], [0, 0, 40, 40, 0, 0]),
        ([1, 1, 0, 0, 1, 1], [0, 0, -10, -10, 0, 0]),
        # ([-1, 1, 0, 0, 1, 1], [0, 0, 10, 10, 0, 0]),  # TODO: Case currently not handled
        # ([5, 1, 0, 0, 1, 1], [0, 0, 10, 10, 0, 0]),  # TODO: Case currently not handled
    ]

    for available_usage in bad_available_usages:
        with pytest.raises(Exception):
            system.get_node("ev").initialise_data(
                available=available_usage[0],
                usage=available_usage[1],
                initial_state_of_charge=new_initial_state_of_charge,
                interval_duration=new_interval_duration,
            )

            # Optimise
            optimise(
                scenario_settings=ScenarioSettings(
                    interval_duration=new_interval_duration,
                    number_of_intervals=new_time_periods,
                    number_of_expansion_intervals=expansion_periods,
                    discount_rate=discount_rate,
                ),
                engine_settings=engine_settings_from_environment(),
                graph=system,
            )


def test_v0g_output_matches_expectation():
    """This example if taken from scripts/manual_examples/ev_example.

    The aim of this test is to determine if the output of a v0g ev optimisation matches expectations, ie. does the graph
    look right?
    """

    ##Set up hyper params
    time_periods = 48  # number of time periods to run the optimisation for
    interval_duration = 30  # each time period is 15 mins long
    expansion_periods = 1  # not yet implemented leave as 1
    discount_rate = 0  # not yet implemented leave as 0

    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(node_name="grid", port_name="cp")

    # Create a connection point (zero sum) node with ports for our three EVs
    connection_point = TellegenNode(node_name="cp")
    connection_point.add_ports_from_list(["grid", "ev_v0g"], FlexPort, units=Units.KW)

    # Create V0G vehicle
    available = [1] * 24 + [0] * 24  # bool when at charger
    usage = [0.0] * 24 + [5] * 24  # kw average during use

    ev = EV(
        node_name="ev",
        charge_mode="V0G",
        available=available,
        usage=usage,
        connection_port_name="cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-1e4,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=20,
        soc_conserv=None,
        soc_conserv_cost=0.0,
        interval_duration=interval_duration,
        tod_charging=None,
        trip_slack=True,
    )

    # Add nodes to the OptimisationGraph
    system.add_node_obj([grid, ev, connection_point])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["cp"], connection_point.ports["grid"])
    system.connect_ports_and_create_edge(connection_point.ports["ev_v0g"], ev.ports["cp"])

    # Check that the values of initial_value on the ev node "cp" port is the same as the Edge port "cp" connection cp
    # and ev
    assert system.get_edge(("cp", "ev")).vertices[1].initial_value == system.get_node("ev").ports["cp"].initial_value

    # Check tha that "cp" port on ev node and "cp" on Edge connection cp and ev nodes are equal
    assert system.get_edge(("cp", "ev")).vertices[1] == system.get_node("ev").ports["cp"]

    # Invoke the optimiser and optimise
    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
            discount_rate=discount_rate,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
    )

    # Check that the values of initial_value on the ev node "cp" port is the same as the Edge port "cp" connection cp
    # and ev
    assert system.get_edge(("cp", "ev")).vertices[1].initial_value == system.get_node("ev").ports["cp"].initial_value

    # Check tha that "cp" port on ev node and "cp" on Edge connection cp and ev nodes are equal
    assert system.get_edge(("cp", "ev")).vertices[1] == system.get_node("ev").ports["cp"]

    soc = optimise_results.values(ev.ports["vehicle"].soc_value, 0)

    expected_soc = np.array(
        [
            25,
            30,
            35,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            37.5,
            35,
            32.5,
            30,
            27.5,
            25,
            22.5,
            20,
            17.5,
            15,
            12.5,
            10,
            7.5,
            5,
            2.5,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ]
    )

    # Assert the results (soc) and expected results (expected_soc) are equal
    assert np.array_equal(soc, expected_soc)


def test_v0g_output_matches_expectation_after_initialise_data_with_expanding_dataset():
    """This example builds on test_v0g_output_matches_expectation.

    The aim of this test is to determine if the output of a v0g ev optimisation matches expectations, ie. does the graph
    look right, after initialise_data has been used to decrease the number of time periods

    Uses test_v0g_2 inputs, then test_v0g inputs
    """

    # Set up hyper params
    available = [1] * 7 + [0] * 3  # bool when at charger
    usage = [0.0] * 7 + [2] * 3  # kw average during use
    interval_duration = 10
    time_periods = len(available)
    expansion_periods = 1  # not yet implemented leave as 1
    discount_rate = 0  # not yet implemented leave as 0

    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(node_name="grid", port_name="cp")

    # Create a connection point
    connection_point = TellegenNode(node_name="cp")
    connection_point.add_ports_from_list(["grid", "ev_v0g"], FlexPort, units=Units.KW)

    # Create V0G vehicle
    ev = EV(
        node_name="ev",
        charge_mode="V0G",
        available=available,
        usage=usage,
        connection_port_name="cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-1e4,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=20,
        soc_conserv=None,
        soc_conserv_cost=0.0,
        interval_duration=interval_duration,
        tod_charging=None,
        trip_slack=True,
    )
    # Check that ev has 3 ports
    assert len(ev.ports.keys()) == 3

    # Add nodes to the OptimisationGraph
    system.add_node_obj([grid, ev, connection_point])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["cp"], connection_point.ports["grid"])
    system.connect_ports_and_create_edge(connection_point.ports["ev_v0g"], ev.ports["cp"])

    # Check that the values of initial_value on the ev node "cp" port is the same as the Edge port "cp" connection cp
    # and ev
    assert system.get_edge(("cp", "ev")).vertices[1].initial_value == system.get_node("ev").ports["cp"].initial_value

    # Check tha that "cp" port on ev node and "cp" on Edge connection cp and ev nodes are equal
    assert system.get_edge(("cp", "ev")).vertices[1] == system.get_node("ev").ports["cp"]

    # Invoke the optimiser and optimise
    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
            discount_rate=discount_rate,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
    )

    # Set new values for these parameters
    available = [1] * 24 + [0] * 24  # bool when at charger
    usage = [0.0] * 24 + [5] * 24  # kw average during use
    interval_duration = 30
    time_periods = len(available)

    # Check that the values of initial_value on the ev node "cp" port is the same as the Edge port "cp" connection cp
    # and ev
    assert system.get_edge(("cp", "ev")).vertices[1].initial_value == system.get_node("ev").ports["cp"].initial_value

    # Check tha that "cp" port on ev node and "cp" on Edge connection cp and ev nodes are equal
    assert system.get_edge(("cp", "ev")).vertices[1] == system.get_node("ev").ports["cp"]

    # Inject the new parameters into the EV node
    system.get_node("ev").initialise_data(
        available=available,
        usage=usage,
        initial_state_of_charge=20,
        interval_duration=30,
        edge_port=system.get_edge(("cp", "ev")).vertices[1],
    )

    # Check that the values of initial_value on the ev node "cp" port is the same as the Edge port "cp" connection cp
    # and ev
    assert system.get_edge(("cp", "ev")).vertices[1].initial_value == system.get_node("ev").ports["cp"].initial_value

    # Check tha that "cp" port on ev node and "cp" on Edge connection cp and ev nodes are equal
    assert system.get_edge(("cp", "ev")).vertices[1] == system.get_node("ev").ports["cp"]

    # Check that ev has 3 ports
    assert len(ev.ports.keys()) == 3

    # Invoke the optimiser and optimise
    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
            discount_rate=discount_rate,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
    )

    soc = optimise_results.values(ev.ports["vehicle"].soc_value, 0)

    expected_soc = np.array(
        [
            25,
            30,
            35,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            40,
            37.5,
            35,
            32.5,
            30,
            27.5,
            25,
            22.5,
            20,
            17.5,
            15,
            12.5,
            10,
            7.5,
            5,
            2.5,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ]
    )

    # Assert the results (soc) and expected results (expected_soc) are equal
    assert np.array_equal(soc, expected_soc)


def test_v0g_output_matches_expectation_after_initialise_data_with_contracting_dataset():
    """This example builds on test_v0g_output_matches_expectation_after_initialise_data_with_expanding_dataset

    The aim of this test is to determine if the output of a v0g ev optimisation matches expectations, ie. does the graph
    look right, after initialise_data has been used to decrease the number of time periods

    Uses test_v0g inputs, then test_v0g_2 inputs
    """

    # Set up hyper params
    available = [1] * 24 + [0] * 24  # bool when at charger
    usage = [0.0] * 24 + [5] * 24  # kw average during use
    interval_duration = 30
    initial_state_of_charge = 20
    time_periods = len(available)
    expansion_periods = 1  # not yet implemented leave as 1
    discount_rate = 0  # not yet implemented leave as 0

    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(port_name="grid")

    # Create a connection point
    connection_point = TellegenNode(node_name="cp")
    connection_point.add_ports_from_list(["grid", "ev_v0g"], FlexPort, units=Units.KW)

    # Create V0G vehicle
    ev = EV(
        node_name="ev",
        charge_mode=EVChargeMode.V0G,
        available=available,
        usage=usage,
        connection_port_name="cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-10,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=initial_state_of_charge,
        soc_conserv=None,
        soc_conserv_cost=0.0,
        interval_duration=interval_duration,
        tod_charging=None,
        trip_slack=True,
    )

    # Check that ev has 3 ports
    assert len(ev.ports.keys()) == 3

    # Add nodes to the OptimisationGraph
    system.add_node_obj([grid, ev, connection_point])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["grid"], connection_point.ports["grid"])
    system.connect_ports_and_create_edge(connection_point.ports["ev_v0g"], ev.ports["cp"])

    # Check that the values of initial_value on the ev node "cp" port is the same as the Edge port "cp" connection cp
    # and ev
    assert system.get_edge(("cp", "ev")).vertices[1].initial_value == system.get_node("ev").ports["cp"].initial_value

    # Check tha that "cp" port on ev node and "cp" on Edge connection cp and ev nodes are equal
    assert system.get_edge(("cp", "ev")).vertices[1] == system.get_node("ev").ports["cp"]

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
        verbose=False,
    )
    # Check that the values of initial_value on the ev node "cp" port is the same as the Edge port "cp" connection cp
    # and ev
    assert system.get_edge(("cp", "ev")).vertices[1].initial_value == system.get_node("ev").ports["cp"].initial_value

    # Check tha that "cp" port on ev node and "cp" on Edge connection cp and ev nodes are equal
    assert system.get_edge(("cp", "ev")).vertices[1] == system.get_node("ev").ports["cp"]

    # Set new values for these parameters
    available = [1] * 7 + [0] * 3  # bool when at charger
    usage = [0.0] * 7 + [5] * 3  # kw average during use
    interval_duration = 10
    time_periods = len(available)

    # Check that the values of initial_value on the ev node "cp" port is the same as the Edge port "cp" connection cp
    # and ev
    assert system.get_edge(("cp", "ev")).vertices[1].initial_value == system.get_node("ev").ports["cp"].initial_value

    # Check tha that "cp" port on ev node and "cp" on Edge connection cp and ev nodes are equal
    assert system.get_edge(("cp", "ev")).vertices[1] == system.get_node("ev").ports["cp"]

    # Inject the new parameters into the EV node
    system.get_node("ev").initialise_data(
        available=available,
        usage=usage,
        initial_state_of_charge=initial_state_of_charge,
        interval_duration=interval_duration,
        edge_port=system.get_edge(("cp", "ev")).vertices[1],
    )

    # Check that the values of initial_value on the ev node "cp" port is the same as the Edge port "cp" connection cp
    # and ev
    assert system.get_edge(("cp", "ev")).vertices[1].initial_value == system.get_node("ev").ports["cp"].initial_value

    # Check tha that "cp" port on ev node and "cp" on Edge connection cp and ev nodes are equal
    assert system.get_edge(("cp", "ev")).vertices[1] == system.get_node("ev").ports["cp"]

    # Check that ev has 3 ports
    assert len(ev.ports.keys()) == 3

    # Invoke the optimiser and optimise
    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
            discount_rate=discount_rate,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
    )

    soc = optimise_results.values(ev.ports["vehicle"].soc_value, 0)

    expected_soc = np.array(
        [21.66666667, 23.33333333, 25.0, 26.66666667, 28.33333333, 30.0, 31.66666667, 30.83333333, 30.0, 29.16666667]
    )

    assert np.allclose(soc, expected_soc, rtol=1**-5)


# def test_v2g_soc_conserv():
#     pass
