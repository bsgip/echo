from __future__ import division

from typing import List, Tuple

import numpy as np
import pytest

from echo.configuration import EVChargeMode, Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import EV, ElectricalDemand, ElectricalGeneration, Inverter
from echo.models.prebuilt import FlexElectricalNode
from echo.models.scenario import ScenarioSettings
from echo.objectives.base import ObjectiveSet
from echo.objectives.power import PeakNegativePower
from echo.objectives.tariff import ImportTariff, ThroughputCost
from echo.optimiser import optimise


def test_v0g(engine_settings):
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
        charge_mode=EVChargeMode.V0G,
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
        engine_settings=engine_settings,
        graph=system,
    )


def test_v0g_2(engine_settings):
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
        charge_mode=EVChargeMode.V0G,
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
        engine_settings=engine_settings,
        graph=system,
    )


def test_v0g_3(engine_settings):
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
        charge_mode=EVChargeMode.V0G,
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
        engine_settings=engine_settings,
        graph=system,
    )


def test_v0g_with_stateful_data_injection(engine_settings):
    # Extends off test_v0g()

    # Available and usage combinations that work
    good_available_usages: List[Tuple[np.array, np.array]] = [
        (np.array([1, 1, 1, 1, 1, 1]), np.array([0, 0, 0, 0, 0, 0])),
        (np.array([0, 0, 0, 0, 0, 0]), np.array([1, 1, 1, 1, 1, 1])),
        (np.array([0, 0, 0, 0, 0, 0]), np.array([0, 0, 0, 0, 0, 0])),
        (np.array([1, 1, 0, 0, 1, 1]), np.array([0, 0, 1, 1, 0, 0])),
        (np.array([1, 1, 0, 0, 1, 1]), np.array([0, 0, 10, 10, 0, 0])),
    ]

    for available_usages in good_available_usages:
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
            charge_mode=EVChargeMode.V0G,
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

        # Define new stateful parameters
        new_interval_duration = 30
        new_initial_state_of_charge = 50
        new_time_periods = 6

        # Inject stateful data
        system.node_obj["ev"].update(
            available=available_usages[0],
            usage=available_usages[1],
            initial_state_of_charge=new_initial_state_of_charge,
            interval_duration=new_interval_duration,
        )

        # Update the edge
        system.delete_edge(("cp", "ev"))
        system.connect_ports_and_create_edge(connection_point.ports["ev"], ev_cp.ports["cp"])

        # Optimise
        optimise(
            scenario_settings=ScenarioSettings(
                interval_duration=new_interval_duration,
                number_of_intervals=new_time_periods,
                number_of_expansion_intervals=expansion_periods,
                discount_rate=discount_rate,
            ),
            engine_settings=engine_settings,
            graph=system,
        )


def test_v0g_output_matches_expectation(engine_settings):
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
        charge_mode=EVChargeMode.V0G,
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
        engine_settings=engine_settings,
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


def test_v0g_output_matches_expectation_after_initialise_data_with_expanding_dataset(engine_settings):
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
        charge_mode=EVChargeMode.V0G,
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

    # Set new values for these parameters
    available = [1] * 24 + [0] * 24  # bool when at charger
    usage = [0.0] * 24 + [5] * 24  # kw average during use
    interval_duration = 30
    time_periods = len(available)

    # Inject stateful data
    system.node_obj["ev"].update(available=available, usage=usage, interval_duration=interval_duration)

    # Update the edge
    system.delete_edge(("cp", "ev"))
    system.connect_ports_and_create_edge(connection_point.ports["ev_v0g"], ev.ports["cp"])

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
        engine_settings=engine_settings,
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


def test_v0g_output_matches_expectation_after_initialise_data_with_contracting_dataset(engine_settings):
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

    # Set new values for these parameters
    available = [1] * 7 + [0] * 3  # bool when at charger
    usage = [0.0] * 7 + [5] * 3  # kw average during use
    interval_duration = 10
    time_periods = len(available)

    system.node_obj["ev"].update(
        available=available,
        usage=usage,
        initial_state_of_charge=initial_state_of_charge,
        interval_duration=interval_duration,
    )

    # Update the edge
    system.delete_edge(("cp", "ev"))
    system.connect_ports_and_create_edge(connection_point.ports["ev_v0g"], ev.ports["cp"])

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
        engine_settings=engine_settings,
        graph=system,
    )

    soc = optimise_results.values(ev.ports["vehicle"].soc_value, 0)

    expected_soc = np.array(
        [21.66666667, 23.33333333, 25.0, 26.66666667, 28.33333333, 30.0, 31.66666667, 30.83333333, 30.0, 29.16666667]
    )

    assert np.allclose(soc, expected_soc, rtol=10**-5)


# def test_v2g_soc_conserv():
#     pass


def test_v1g_no_objective(engine_settings):
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
        charge_mode=EVChargeMode.V1G,
        available=available,
        usage=usage,
        connection_port_name="cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-10,
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
        engine_settings=engine_settings,
        graph=system,
    )


def test_v1g_no_objective_2(engine_settings):
    """Like test_v1g, just different parameters."""

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
        charge_mode=EVChargeMode.V1G,
        available=available,
        usage=usage,
        connection_port_name="cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-10,
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
        engine_settings=engine_settings,
        graph=system,
    )


def test_v1g_no_objective_3(engine_settings):
    """Like test_v1g_2, just different parameters, but discharge first, then charge."""

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
        charge_mode=EVChargeMode.V1G,
        available=available,
        usage=usage,
        connection_port_name="cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-10,
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
        engine_settings=engine_settings,
        graph=system,
    )


def test_v2g_no_objective(engine_settings):
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
        charge_mode=EVChargeMode.V2G,
        available=available,
        usage=usage,
        connection_port_name="cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-10,
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
        engine_settings=engine_settings,
        graph=system,
    )


def test_v2g_no_objective_2(engine_settings):
    """Like test_v1g, just different parameters."""

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
        charge_mode=EVChargeMode.V2G,
        available=available,
        usage=usage,
        connection_port_name="cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-10,
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
        engine_settings=engine_settings,
        graph=system,
    )


def test_v2g_no_objective_3(engine_settings):
    """Like test_v1g_2, just different parameters, but discharge first, then charge."""

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
        charge_mode=EVChargeMode.V2G,
        available=available,
        usage=usage,
        connection_port_name="cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-10,
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
        engine_settings=engine_settings,
        graph=system,
    )


def test_simple_v1g_with_stateful_data_injection(engine_settings):
    """Get V1G to behave properly"""
    good_available_usage = (np.array([1, 1, 0, 0, 1, 1]), np.array([0, 0, 10, 10, 0, 0]))
    good_soc = np.array([50, 50, 40, 30, 30, 30])

    # Set up hyper params
    time_periods = 2  # number of time periods to run the optimisation for
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

    # Create V1G vehicle
    available = np.array([0] * 2)
    usage = np.array([5] * 2)
    ev_cp = EV(
        node_name="ev",
        charge_mode=EVChargeMode.V1G,
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
        interval_duration=1,
        tod_charging=False,
        trip_slack=True,
    )

    system.add_node_obj([grid, ev_cp, connection_point])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(connection_point.ports["ev"], ev_cp.ports["cp"])
    system.connect_ports_and_create_edge(grid.ports["cp"], connection_point.ports["grid"])

    # Set new stateful parameters for ev
    new_interval_duration = 60
    new_initial_state_of_charge = 50
    new_time_periods = 6

    # Update ev with stateful parameters
    system.node_obj["ev"].update(
        available=good_available_usage[0],
        usage=good_available_usage[1],
        initial_state_of_charge=new_initial_state_of_charge,
        interval_duration=new_interval_duration,
    )

    # Update the edge
    system.delete_edge(("cp", "ev"))
    system.connect_ports_and_create_edge(connection_point.ports["ev"], ev_cp.ports["cp"])

    # Check that the values of initial_value on the ev node "cp" port is the same as the Edge port "cp" connection
    # cp and ev
    assert system.get_edge(("cp", "ev")).vertices[1].active_periods == system.get_node("ev").ports["cp"].active_periods

    # Check tha that "cp" port on ev node and "cp" on Edge connection cp and ev nodes are equal
    assert system.get_edge(("cp", "ev")).vertices[1] == system.get_node("ev").ports["cp"]

    # Optimise
    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=new_interval_duration,
            number_of_intervals=new_time_periods,
            number_of_expansion_intervals=expansion_periods,
            discount_rate=discount_rate,
        ),
        engine_settings=engine_settings,
        graph=system,
        verbose=False,
    )

    # Get state of charge
    soc = optimise_results.values(ev_cp.ports["vehicle"].soc_value, 0)

    # Assert soc will be what we think it will be
    assert np.allclose(soc, good_soc, rtol=10**-5)


def test_simple_v2g_with_stateful_data_injection_2(engine_settings):
    """Get V1G to behave properly"""
    good_available_usage = (np.array([1, 1, 0, 0, 1, 1]), np.array([0, 0, 10, 10, 0, 0]))

    # Set up hyper params
    interval_duration = 1  # each time period is 15 mins long
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

    # Create V1G vehicle
    available = np.array([0] * 2)
    usage = np.array([5] * 2)
    ev_cp = EV(
        node_name="ev",
        charge_mode=EVChargeMode.V2G,
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
        interval_duration=interval_duration,
        tod_charging=False,
        trip_slack=True,
    )

    system.add_node_obj([grid, ev_cp, connection_point])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(connection_point.ports["ev"], ev_cp.ports["cp"])
    system.connect_ports_and_create_edge(grid.ports["cp"], connection_point.ports["grid"])

    # Set new stateful parameters for ev
    new_interval_duration = 60
    new_initial_state_of_charge = 50
    new_time_periods = 6

    # Update ev with stateful parameters
    system.node_obj["ev"].update(
        available=good_available_usage[0],
        usage=good_available_usage[1],
        initial_state_of_charge=new_initial_state_of_charge,
        interval_duration=new_interval_duration,
    )

    # Update the edge
    system.delete_edge(("cp", "ev"))
    system.connect_ports_and_create_edge(connection_point.ports["ev"], ev_cp.ports["cp"])

    # Check that the values of initial_value on the ev node "cp" port is the same as the Edge port "cp" connection
    # cp and ev
    assert system.get_edge(("cp", "ev")).vertices[1].active_periods == system.get_node("ev").ports["cp"].active_periods

    # Check tha that "cp" port on ev node and "cp" on Edge connection cp and ev nodes are equal
    assert system.get_edge(("cp", "ev")).vertices[1] == system.get_node("ev").ports["cp"]

    # Optimise
    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=new_interval_duration,
            number_of_intervals=new_time_periods,
            number_of_expansion_intervals=expansion_periods,
            discount_rate=discount_rate,
        ),
        engine_settings=engine_settings,
        graph=system,
        verbose=False,
    )

    # Get state of charge
    soc = optimise_results.values(ev_cp.ports["vehicle"].soc_value, 0)

    # Assert soc will be what we think it will be
    assert len(soc) == 6
    assert any(np.not_equal(soc, np.array([50] * 6)))
    assert any(np.not_equal(soc, np.array([20] * 6)))
    assert any(np.not_equal(soc, np.array([0] * 6)))


def test_simple_v1g_with_stateful_data_injection_2(engine_settings):
    """Get V1G to behave properly"""

    # Available and usage combinations that work
    good_available_usages: List[Tuple[np.array, np.array]] = [
        (np.array([1, 1, 1, 1, 1, 1]), np.array([0, 0, 0, 0, 0, 0])),
        (np.array([0, 0, 0, 0, 0, 0]), np.array([1, 1, 1, 1, 1, 1])),
        (np.array([0, 0, 0, 0, 0, 0]), np.array([0, 0, 0, 0, 0, 0])),
        (np.array([1, 1, 0, 0, 1, 1]), np.array([0, 0, 1, 1, 0, 0])),
        (np.array([1, 1, 0, 0, 1, 0]), np.array([0, 0, 25, 20, 0, 10])),
    ]

    good_socs: List[np.array] = [
        np.array([50, 50, 50, 50, 50, 50]),
        np.array([49, 48, 47, 46, 45, 44]),
        np.array([50, 50, 50, 50, 50, 50]),
        np.array([50, 50, 49, 48, 48, 48]),
        np.array([50, 50, 25, 5, 10, 0]),
    ]

    i = 0

    for available_usage in good_available_usages:
        # Set up hyper params
        interval_duration = 1  # each time period is 15 mins long
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

        # Create V1G vehicle
        available = np.array([0] * 2)
        usage = np.array([5] * 2)
        ev_cp = EV(
            node_name="ev",
            charge_mode=EVChargeMode.V1G,
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
            interval_duration=1,
            tod_charging=False,
            trip_slack=True,
        )

        system.add_node_obj([grid, ev_cp, connection_point])

        # Create edge objects and add to graph
        system.connect_ports_and_create_edge(connection_point.ports["ev"], ev_cp.ports["cp"])
        system.connect_ports_and_create_edge(grid.ports["cp"], connection_point.ports["grid"])

        # Set new stateful parameters for ev
        new_interval_duration = 60
        new_initial_state_of_charge = 50
        new_time_periods = 6

        # Update ev with stateful parameters
        system.node_obj["ev"].update(
            available=available_usage[0],
            usage=available_usage[1],
            initial_state_of_charge=new_initial_state_of_charge,
            interval_duration=new_interval_duration,
        )

        # Update the edge
        system.delete_edge(("cp", "ev"))
        system.connect_ports_and_create_edge(connection_point.ports["ev"], ev_cp.ports["cp"])

        # Check that the values of initial_value on the ev node "cp" port is the same as the Edge port "cp" connection
        # cp and ev
        assert (
            system.get_edge(("cp", "ev")).vertices[1].active_periods == system.get_node("ev").ports["cp"].active_periods
        )

        # Check tha that "cp" port on ev node and "cp" on Edge connection cp and ev nodes are equal
        assert system.get_edge(("cp", "ev")).vertices[1] == system.get_node("ev").ports["cp"]

        # Optimise
        optimise_results = optimise(
            scenario_settings=ScenarioSettings(
                interval_duration=new_interval_duration,
                number_of_intervals=new_time_periods,
                number_of_expansion_intervals=expansion_periods,
                discount_rate=discount_rate,
            ),
            engine_settings=engine_settings,
            graph=system,
            verbose=False,
        )

        # Get state of charge
        soc = optimise_results.values(ev_cp.ports["vehicle"].soc_value, 0)

        # Assert soc will be what we think it will be
        assert np.allclose(soc, good_socs[i], rtol=10**-5)

        i += 1

    # Check the last iteration has flow through the grid and is not just relying on the trip_slack
    grid_to_cp_flow = optimise_results.values(grid.ports["cp"].port_name, 0)
    cp_to_grid_flow = optimise_results.values(connection_point.ports["grid"].port_name, 0)
    cp_to_ev_flow = optimise_results.values(connection_point.ports["ev"].port_name, 0)
    ev_to_cp_flow = optimise_results.values(ev_cp.ports["cp"].port_name, 0)

    assert np.allclose(grid_to_cp_flow, np.array([0, 0, 0, 0, -5, 0]), rtol=10**-5)
    assert np.allclose(cp_to_grid_flow, np.array([0, 0, 0, 0, 5, 0]), rtol=10**-5)
    assert np.allclose(cp_to_ev_flow, np.array([0, 0, 0, 0, -5, 0]), rtol=10**-5)
    assert np.allclose(ev_to_cp_flow, np.array([0, 0, 0, 0, 5, 0]), rtol=10**-5)


def test_simple_v0g_with_stateful_data_injection_for_invalid_input_detection(engine_settings):
    """Get V1G to behave properly"""

    bad_available_usages: List[Tuple[list, list]] = [
        ([1, 1, 1, 1, 1, 1], [1, 1, 1, 1, 1, 1]),
        ([0, 0, 1, 1, 0, 0], [0, 0, 1, 1, 0, 0]),
        ([1, 1, 0, 0, 1, 1], [0, 0, 40, 40, 0, 0]),
        ([1, 1, 0, 0, 1, 1], [0, 0, -10, -10, 0, 0]),
        # ([-1, 1, 0, 0, 1, 1], [0, 0, 10, 10, 0, 0]),  # TODO: Case currently not handled
        # ([5, 1, 0, 0, 1, 1], [0, 0, 10, 10, 0, 0]),  # TODO: Case currently not handled
    ]

    for available_usage in bad_available_usages:
        # Set up hyper params
        interval_duration = 1  # each time period is 15 mins long
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

        # Create V1G vehicle
        available = np.array([0] * 2)
        usage = np.array([5] * 2)
        ev_cp = EV(
            node_name="ev",
            charge_mode=EVChargeMode.V0G,
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
            interval_duration=1,
            tod_charging=False,
            trip_slack=True,
        )

        system.add_node_obj([grid, ev_cp, connection_point])

        # Create edge objects and add to graph
        system.connect_ports_and_create_edge(connection_point.ports["ev"], ev_cp.ports["cp"])
        system.connect_ports_and_create_edge(grid.ports["cp"], connection_point.ports["grid"])

        # Set new stateful parameters for ev
        new_interval_duration = 60
        new_initial_state_of_charge = 50
        new_time_periods = 6

        with pytest.raises(Exception):
            # Update ev with stateful parameters
            system.node_obj["ev"].update(
                available=available_usage[0],
                usage=available_usage[1],
                initial_state_of_charge=new_initial_state_of_charge,
                interval_duration=new_interval_duration,
            )

            # Update the edge
            system.delete_edge(("cp", "ev"))
            system.connect_ports_and_create_edge(connection_point.ports["ev"], ev_cp.ports["cp"])

            # Check that the values of initial_value on the ev node "cp" port is the same as the Edge port "cp" connection
            # cp and ev
            assert (
                system.get_edge(("cp", "ev")).vertices[1].active_periods
                == system.get_node("ev").ports["cp"].active_periods
            )

            # Check tha that "cp" port on ev node and "cp" on Edge connection cp and ev nodes are equal
            assert system.get_edge(("cp", "ev")).vertices[1] == system.get_node("ev").ports["cp"]

            # Optimise
            optimise_results = optimise(
                scenario_settings=ScenarioSettings(
                    interval_duration=new_interval_duration,
                    number_of_intervals=new_time_periods,
                    number_of_expansion_intervals=expansion_periods,
                    discount_rate=discount_rate,
                ),
                engine_settings=engine_settings,
                graph=system,
                verbose=False,
            )


def test_v1g_with_objective(engine_settings):
    """Like test_v1g_no_objective_2, but with objective"""

    # Set up hyper params
    available = [1] * 8 + [0] * 2  # bool when at charger
    usage = [0.0] * 8 + [20] * 2  # kw average during use
    solar_data = [-5, -5, 0, 0, 0, 0, 0, -5, -5, -5]  # kw load
    import_tariff = [9, 10, 11, 1, 2, 3, 8, 9, 10, 11]  # $/kw
    interval_duration = 60
    time_periods = len(available)
    expansion_periods = 1  # not yet implemented leave as 1
    discount_rate = 0  # not yet implemented leave as 0

    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(node_name="grid", port_name="grid_to_cp")

    # Create a connection point
    connection_point = TellegenNode(node_name="connection_point")
    connection_point.add_ports_from_list(["cp_to_grid", "cp_to_ev", "cp_to_inverter"], FlexPort, units=Units.KW)

    # create a node for the solar
    solar = Node(node_name="solar")
    pv = ElectricalGeneration()  # create an electrical generation object
    pv.curtailable = False  # set whether this can be curtailed or not
    pv.add_generation_profile_from_array(solar_data, expansion_periods)
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

    # Create V1G vehicle
    ev = EV(
        node_name="ev",
        charge_mode=EVChargeMode.V1G,
        available=available,
        usage=usage,
        connection_port_name="ev_to_cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-20,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=0,
        soc_conserv=None,
        soc_conserv_cost=0.0,
        interval_duration=interval_duration,
        tod_charging=None,
        trip_slack=True,
    )

    # Check that ev has 3 ports
    assert len(ev.ports.keys()) == 3

    # Add nodes to the OptimisationGraph
    system.add_node_obj([grid, ev, connection_point, inverter, solar])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["grid_to_cp"], connection_point.ports["cp_to_grid"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_ev"], ev.ports["ev_to_cp"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_inverter"], inverter.ports["inverter_to_cp"])
    system.connect_ports_and_create_edge(inverter.ports["inverter_to_solar"], solar.ports["solar_to_inverter"])

    # Create objectives/tariffs
    import_cost = ImportTariff(
        component=connection_point.ports["cp_to_grid"], tariff_array=import_tariff, expansion_periods=expansion_periods
    )
    objective_set = ObjectiveSet(objective_list=[import_cost])

    # Invoke the optimiser and optimise
    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
            discount_rate=discount_rate,
        ),
        engine_settings=engine_settings,
        graph=system,
        objective_set=objective_set,
    )

    soc = optimise_results.values(ev.ports["vehicle"].soc_value, 0)

    expected_soc = np.array([5, 10, 10, 20, 30, 35, 35, 40, 20, 0])

    assert np.allclose(soc, expected_soc, rtol=10**-5)


def test_v1g_with_load_with_objective(engine_settings):
    """Like test_v1g_with_objective, but with a load.

    Expect delayed charging behaviour.
    """

    # Set up hyper params
    available = [1] * 8 + [0] * 2  # bool when at charger
    usage = [0.0] * 8 + [20] * 2  # kw average during use
    solar_data = [-5, -5, 0, 0, 0, 0, 0, -5, -5, -5]  # kw generated
    load_data = [10, 10, 5, 5, 10, 10, 5, 5, 10, 10]  # kw load
    import_tariff = [10, 10, 10, 1, 1, 1, 10, 10, 10, 10]  # $/kw
    interval_duration = 60
    time_periods = len(available)
    expansion_periods = 1  # not yet implemented leave as 1
    discount_rate = 0  # not yet implemented leave as 0

    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(node_name="grid", port_name="grid_to_cp")

    # Create a connection point
    connection_point = TellegenNode(node_name="connection_point")
    connection_point.add_ports_from_list(
        names=["cp_to_grid", "cp_to_load", "cp_to_ev", "cp_to_inverter"], port_type=FlexPort, units=Units.KW
    )

    # Create a load object
    load = Node(node_name="load")
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array(load_data, expansion_periods)
    load.ports["load_to_cp"] = l1

    # create a node for the solar
    solar = Node(node_name="solar")
    pv = ElectricalGeneration()
    pv.curtailable = False
    pv.add_generation_profile_from_array(solar_data, expansion_periods)
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

    # Create V1G vehicle
    ev = EV(
        node_name="ev",
        charge_mode=EVChargeMode.V1G,
        available=available,
        usage=usage,
        connection_port_name="ev_to_cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-20,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=0,
        soc_conserv=None,
        soc_conserv_cost=0.0,
        interval_duration=interval_duration,
        tod_charging=None,
        trip_slack=True,
    )

    # Check that ev has 3 ports
    assert len(ev.ports.keys()) == 3

    # Add nodes to the OptimisationGraph
    system.add_node_obj([grid, ev, connection_point, load, inverter, solar])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["grid_to_cp"], connection_point.ports["cp_to_grid"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_ev"], ev.ports["ev_to_cp"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_inverter"], inverter.ports["inverter_to_cp"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_load"], load.ports["load_to_cp"])
    system.connect_ports_and_create_edge(inverter.ports["inverter_to_solar"], solar.ports["solar_to_inverter"])

    # Create objectives/tariffs
    import_cost = ImportTariff(
        component=connection_point.ports["cp_to_grid"], tariff_array=import_tariff, expansion_periods=expansion_periods
    )
    objective_set = ObjectiveSet(objective_list=[import_cost])

    # Invoke the optimiser and optimise
    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
            discount_rate=discount_rate,
        ),
        engine_settings=engine_settings,
        graph=system,
        objective_set=objective_set,
    )

    soc = optimise_results.values(ev.ports["vehicle"].soc_value, 0)

    expected_soc = np.array([0, 0, 10, 20, 30, 40, 40, 40, 20, 0])

    assert np.allclose(soc, expected_soc, rtol=10**-5)


def test_v2g_with_load_with_objective(engine_settings):
    """Like test_v1g_with_load_with_objective, but with a load.

    Expect delayed charging behaviour.
    """

    # Set up hyper params
    available = [1] * 8 + [0] * 2  # bool when at charger
    usage = [0.0] * 8 + [20] * 2  # kw average during use
    solar_data = [-5, -5, 0, 0, 0, 0, 0, -5, -5, -5]  # kw generated
    load_data = [10, 10, 5, 5, 10, 10, 5, 5, 10, 10]  # kw load
    import_tariff = [10, 10, 10, 1, 1, 1, 10, 1, 10, 10]  # $/kw
    interval_duration = 60
    time_periods = len(available)
    expansion_periods = 1  # not yet implemented leave as 1
    discount_rate = 0  # not yet implemented leave as 0

    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(node_name="grid", port_name="grid_to_cp")

    # Create a connection point
    connection_point = TellegenNode(node_name="connection_point")
    connection_point.add_ports_from_list(
        names=["cp_to_grid", "cp_to_load", "cp_to_ev", "cp_to_inverter"], port_type=FlexPort, units=Units.KW
    )

    # Create a load object
    load = Node(node_name="load")
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array(load_data, expansion_periods)
    load.ports["load_to_cp"] = l1

    # create a node for the solar
    solar = Node(node_name="solar")
    pv = ElectricalGeneration()
    pv.curtailable = False
    pv.add_generation_profile_from_array(solar_data, expansion_periods)
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

    # Create V1G vehicle
    ev = EV(
        node_name="ev",
        charge_mode=EVChargeMode.V2G,
        available=available,
        usage=usage,
        connection_port_name="ev_to_cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-20,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=0,
        soc_conserv=None,
        soc_conserv_cost=0.0,
        interval_duration=interval_duration,
        tod_charging=None,
        trip_slack=True,
    )

    # Check that ev has 3 ports
    assert len(ev.ports.keys()) == 3

    # Add nodes to the OptimisationGraph
    system.add_node_obj([grid, ev, connection_point, load, inverter, solar])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["grid_to_cp"], connection_point.ports["cp_to_grid"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_ev"], ev.ports["ev_to_cp"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_inverter"], inverter.ports["inverter_to_cp"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_load"], load.ports["load_to_cp"])
    system.connect_ports_and_create_edge(inverter.ports["inverter_to_solar"], solar.ports["solar_to_inverter"])

    # Create objectives/tariffs
    import_cost = ImportTariff(
        component=connection_point.ports["cp_to_grid"], tariff_array=import_tariff, expansion_periods=expansion_periods
    )

    # assign a throughput cost to the battery
    throughput_cost = ThroughputCost(component=ev.ports["ev_to_cp"], rate=0.000001)

    objective_set = ObjectiveSet(objective_list=[import_cost, throughput_cost])

    # Invoke the optimiser and optimise
    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
            discount_rate=discount_rate,
        ),
        engine_settings=engine_settings,
        graph=system,
        objective_set=objective_set,
    )

    soc = optimise_results.values(ev.ports["vehicle"].soc_value, 0)

    expected_soc = np.array([0, 0, 0, 10, 20, 30, 30, 40, 20, 0])

    assert np.allclose(soc, expected_soc, rtol=10**-5)


def test_v2g_with_load_with_objective_v2g_behaviour(engine_settings):
    """Like test_v1g_with_load_with_objective, but with a load.

    Expect delayed EV to supply some power to load behaviour.
    """

    # Set up hyper params
    available = [1] * 8 + [0] * 2  # bool when at charger
    usage = [0.0] * 8 + [20] * 2  # kw average during use
    solar_data = [-5, -5, -15, -15, 0, 0, -15, -15, -5, -5]  # kw generated
    load_data = [10, 10, 5, 5, 10, 10, 5, 5, 10, 10]  # kw load
    import_tariff = [10, 10, 10, 1, 1, 1, 10, 10, 10, 10]  # $/kw
    interval_duration = 60
    time_periods = len(available)
    expansion_periods = 1  # not yet implemented leave as 1
    discount_rate = 0  # not yet implemented leave as 0

    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(node_name="grid", port_name="grid_to_cp")

    # Create a connection point
    connection_point = TellegenNode(node_name="connection_point")
    connection_point.add_ports_from_list(
        names=["cp_to_grid", "cp_to_load", "cp_to_ev", "cp_to_inverter"], port_type=FlexPort, units=Units.KW
    )

    # Create a load object
    load = Node(node_name="load")
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array(load_data, expansion_periods)
    load.ports["load_to_cp"] = l1

    # create a node for the solar
    solar = Node(node_name="solar")
    pv = ElectricalGeneration()
    pv.curtailable = False
    pv.add_generation_profile_from_array(solar_data, expansion_periods)
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

    # Create V1G vehicle
    ev = EV(
        node_name="ev",
        charge_mode=EVChargeMode.V2G,
        available=available,
        usage=usage,
        connection_port_name="ev_to_cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-20,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=40,
        soc_conserv=None,
        soc_conserv_cost=0.0,
        interval_duration=interval_duration,
        tod_charging=None,
        trip_slack=True,
    )

    # Check that ev has 3 ports
    assert len(ev.ports.keys()) == 3

    # Add nodes to the OptimisationGraph
    system.add_node_obj([grid, ev, connection_point, load, inverter, solar])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["grid_to_cp"], connection_point.ports["cp_to_grid"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_ev"], ev.ports["ev_to_cp"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_inverter"], inverter.ports["inverter_to_cp"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_load"], load.ports["load_to_cp"])
    system.connect_ports_and_create_edge(inverter.ports["inverter_to_solar"], solar.ports["solar_to_inverter"])

    # Create objectives/tariffs
    import_cost = ImportTariff(
        component=connection_point.ports["cp_to_grid"], tariff_array=import_tariff, expansion_periods=expansion_periods
    )

    # assign a throughput cost to the ev's battery
    throughput_cost = ThroughputCost(component=ev.ports["ev_to_cp"], rate=0.000001)

    objective_set = ObjectiveSet(objective_list=[import_cost, throughput_cost])

    # Invoke the optimiser and optimise
    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
            discount_rate=discount_rate,
        ),
        engine_settings=engine_settings,
        graph=system,
        objective_set=objective_set,
    )

    soc = optimise_results.values(ev.ports["vehicle"].soc_value, 0)

    expected_soc = np.array([35, 30, 40, 40, 30, 20, 30, 40, 20, 0])

    assert np.allclose(soc, expected_soc, rtol=10**-5)


def test_v1g_with_load_with_objective_with_stateful_data_injection(engine_settings):
    """Like test_v1g_with_load_with_objective, now using the initialise data function.

    This test is a bit different to the V0G tests with initialise data in that this will just replicate the procedure
    used to build a network in MES: build the echo network, then inject data into the network, then optimise.
    """

    # Set up hyper params
    available = [1] * 8 + [0] * 2  # bool when at charger
    usage = [0.0] * 8 + [5] * 2  # kw average during use
    initial_state_of_charge = 0
    solar_data = [-5, -5, -5, -5, 0, 0, 0, -5, -5, -5]  # kw generated
    load_data = [1] * 10  # [10, 10, 5, 5, 10, 10, 5, 5, 10, 10] # kw load
    import_tariff = [10, 10, 10, 1, 1, 1, 10, 10, 10, 10]  # $/kw
    interval_duration = 60
    time_periods = len(available)
    expansion_periods = 1  # not yet implemented leave as 1
    discount_rate = 0  # not yet implemented leave as 0

    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(node_name="grid", port_name="grid_to_cp")

    # Create a connection point
    connection_point = TellegenNode(node_name="connection_point")
    connection_point.add_ports_from_list(
        names=["cp_to_grid", "cp_to_load", "cp_to_ev", "cp_to_inverter"], port_type=FlexPort, units=Units.KW
    )

    # Create a load object
    load = Node(node_name="load")
    load.ports["load_to_cp"] = ElectricalDemand()

    # create a node for the solar
    solar = Node(node_name="solar")
    solar.ports["solar_to_inverter"] = ElectricalGeneration()
    solar.ports["solar_to_inverter"].curtailable = False

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

    # Create V1G vehicle
    ev = EV(
        node_name="ev",
        charge_mode=EVChargeMode.V1G,
        available=available,
        usage=usage,
        connection_port_name="ev_to_cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-20,
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
    system.add_node_obj([grid, ev, connection_point, load, inverter, solar])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["grid_to_cp"], connection_point.ports["cp_to_grid"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_ev"], ev.ports["ev_to_cp"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_inverter"], inverter.ports["inverter_to_cp"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_load"], load.ports["load_to_cp"])
    system.connect_ports_and_create_edge(inverter.ports["inverter_to_solar"], solar.ports["solar_to_inverter"])

    # Inject data into load
    system.get_node("load").ports["load_to_cp"].add_demand_profile_from_array(load_data, expansion_periods)

    # Inject data into solar
    system.get_node("solar").ports["solar_to_inverter"].add_generation_profile_from_array(solar_data, expansion_periods)
    # Update ev with stateful parameters
    available = [1] * 8 + [0] * 2  # bool when at charger
    usage = [0.0] * 8 + [20] * 2  # kw average during use
    initial_state_of_charge = 0
    interval_duration = 60

    system.node_obj["ev"].update(
        available=available,
        usage=usage,
        initial_state_of_charge=initial_state_of_charge,
        interval_duration=interval_duration,
    )

    # Update the edge
    system.delete_edge(("connection_point", "ev"))
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_ev"], ev.ports["ev_to_cp"])

    # Create objectives/tariffs
    import_cost = ImportTariff(
        component=connection_point.ports["cp_to_grid"], tariff_array=import_tariff, expansion_periods=expansion_periods
    )
    objective_set = ObjectiveSet(objective_list=[import_cost])

    # Invoke the optimiser and optimise
    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
            discount_rate=discount_rate,
        ),
        engine_settings=engine_settings,
        graph=system,
        objective_set=objective_set,
    )

    soc = optimise_results.values(ev.ports["vehicle"].soc_value, 0)

    expected_soc = np.array([4, 8, 12, 16, 26, 36, 36, 40, 20, 0])

    assert np.allclose(soc, expected_soc, rtol=10**-5)


def test_v2g_with_load_with_objective_with_stateful_data_injection(engine_settings):
    """Like test_v2g_with_load_with_objective, now using the initialise data function.

    This test is a bit different to the V0G tests with initialise data in that this will just replicate the procedure
    used to build a network in MES: build the echo network, then inject data into the network, then optimise.
    """

    # Set up hyper params
    available = [1] * 8 + [0] * 2  # bool when at charger
    usage = [0.0] * 8 + [5] * 2  # kw average during use
    initial_state_of_charge = 0
    solar_data = [-5, -5, -5, -5, 0, 0, 0, -5, -5, -5]  # kw generated
    load_data = [1] * 10  # [10, 10, 5, 5, 10, 10, 5, 5, 10, 10] # kw load
    import_tariff = [11, 10, 19, 1, 2, 3, 11, 10, 9, 8]  # $/kw
    interval_duration = 60
    time_periods = len(available)
    expansion_periods = 1  # not yet implemented leave as 1
    discount_rate = 0  # not yet implemented leave as 0

    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(node_name="grid", port_name="grid_to_cp")

    # Create a connection point
    connection_point = TellegenNode(node_name="connection_point")
    connection_point.add_ports_from_list(
        names=["cp_to_grid", "cp_to_load", "cp_to_ev", "cp_to_inverter"], port_type=FlexPort, units=Units.KW
    )

    # Create a load object
    load = Node(node_name="load")
    load.ports["load_to_cp"] = ElectricalDemand()

    # create a node for the solar
    solar = Node(node_name="solar")
    solar.ports["solar_to_inverter"] = ElectricalGeneration()
    solar.ports["solar_to_inverter"].curtailable = False

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

    # Create V1G vehicle
    ev = EV(
        node_name="ev",
        charge_mode=EVChargeMode.V2G,
        available=available,
        usage=usage,
        connection_port_name="ev_to_cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-20,
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
    system.add_node_obj([grid, ev, connection_point, load, inverter, solar])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["grid_to_cp"], connection_point.ports["cp_to_grid"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_ev"], ev.ports["ev_to_cp"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_inverter"], inverter.ports["inverter_to_cp"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_load"], load.ports["load_to_cp"])
    system.connect_ports_and_create_edge(inverter.ports["inverter_to_solar"], solar.ports["solar_to_inverter"])

    # Inject data into load
    system.get_node("load").ports["load_to_cp"].add_demand_profile_from_array(load_data, expansion_periods)

    # Inject data into solar
    system.get_node("solar").ports["solar_to_inverter"].add_generation_profile_from_array(solar_data, expansion_periods)
    # Update ev with stateful parameters
    available = [1] * 8 + [0] * 2  # bool when at charger
    usage = [0.0] * 8 + [15] * 2  # kw average during use
    initial_state_of_charge = 0
    interval_duration = 60

    system.node_obj["ev"].update(
        available=available,
        usage=usage,
        initial_state_of_charge=initial_state_of_charge,
        interval_duration=interval_duration,
    )

    # Update the edge
    system.delete_edge(("connection_point", "ev"))
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_ev"], ev.ports["ev_to_cp"])

    # Create objectives/tariffs
    import_cost = ImportTariff(
        component=connection_point.ports["cp_to_grid"], tariff_array=import_tariff, expansion_periods=expansion_periods
    )

    # assign a throughput cost to the ev's battery
    throughput_cost = ThroughputCost(component=ev.ports["ev_to_cp"], rate=0.000001)

    objective_set = ObjectiveSet(objective_list=[import_cost, throughput_cost])

    # Invoke the optimiser and optimise
    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
            discount_rate=discount_rate,
        ),
        engine_settings=engine_settings,
        graph=system,
        objective_set=objective_set,
    )

    soc = optimise_results.values(ev.ports["vehicle"].soc_value, 0)

    expected_soc_1 = np.array([4, 8, 12, 22, 28, 27, 26, 30, 15, 0])

    assert np.allclose(soc, expected_soc_1, rtol=10**-5)


def test_node_and_port_uids_on_ev_are_set_properly_when_injecting_stateful_data():
    """Check that node uid and port uids are preserved when injecting stateful data into an ev"""

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
        charge_mode=EVChargeMode.V0G,
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

    # Define new stateful parameters
    new_interval_duration = 30
    new_initial_state_of_charge = 50
    new_time_periods = 6

    # Get node uid
    old_node_uid = system.get_node("ev").uid

    # Get port names and uids sets
    old_port_names = {port_name for port_name in system.get_node("ev").ports.keys()}
    old_port_uids = {port.uid for port in system.get_node("ev").ports.values()}

    # Inject stateful data
    system.node_obj["ev"].update(
        available=np.array([1, 1, 0, 0, 1, 1]),
        usage=np.array([0, 0, 10, 10, 0, 0]),
        initial_state_of_charge=new_initial_state_of_charge,
        interval_duration=new_interval_duration,
    )

    # Update the edge
    system.delete_edge(("cp", "ev"))
    system.connect_ports_and_create_edge(connection_point.ports["ev"], ev_cp.ports["cp"])

    # Get node uid
    new_node_uid = system.get_node("ev").uid

    # Get port names and uids sets
    new_port_names = {port_name for port_name in system.get_node("ev").ports.keys()}
    new_port_uids = {port.uid for port in system.get_node("ev").ports.values()}

    # Check they all equal each other
    assert old_node_uid == new_node_uid
    assert old_port_names == new_port_names
    assert old_port_uids == new_port_uids


def test_v1g_with_load_with_objective_with_stateful_data_injection_with_mes_defaults(engine_settings):
    """Like test_v1g_with_load_with_objective_with_stateful_data_injection but with mes defaults for initial ev
    attributes.

    This test is a bit different to the V0G tests with initialise data in that this will just replicate the procedure
    used to build a network in MES: build the echo network, then inject data into the network, then optimise.
    """

    # Set up hyper params
    available = [1, 1]
    usage = [0, 0]
    interval_duration = 1
    initial_state_of_charge = 40
    time_periods = len(available)
    expansion_periods = 1  # not yet implemented leave as 1
    discount_rate = 0  # not yet implemented leave as 0

    # Set up data to inject
    solar_data = [-5, -5, -5, -5, 0, 0, 0, -5, -5, -5]  # kw generated
    load_data = [1] * 10  # kw load
    import_tariff = [10, 10, 10, 1, 1, 1, 10, 10, 10, 10]  # $/kw

    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(node_name="grid", port_name="grid_to_cp")

    # Create a connection point
    connection_point = TellegenNode(node_name="connection_point")
    connection_point.add_ports_from_list(
        names=["cp_to_grid", "cp_to_load", "cp_to_ev", "cp_to_inverter"], port_type=FlexPort, units=Units.KW
    )

    # Create a load object
    load = Node(node_name="load")
    load.ports["load_to_cp"] = ElectricalDemand()

    # create a node for the solar
    solar = Node(node_name="solar")
    solar.ports["solar_to_inverter"] = ElectricalGeneration()
    solar.ports["solar_to_inverter"].curtailable = False

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

    # Create V1G vehicle
    ev = EV(
        node_name="ev",
        charge_mode=EVChargeMode.V1G,
        available=available,
        usage=usage,
        connection_port_name="ev_to_cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-20,
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
    system.add_node_obj([grid, ev, connection_point, load, inverter, solar])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["grid_to_cp"], connection_point.ports["cp_to_grid"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_ev"], ev.ports["ev_to_cp"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_inverter"], inverter.ports["inverter_to_cp"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_load"], load.ports["load_to_cp"])
    system.connect_ports_and_create_edge(inverter.ports["inverter_to_solar"], solar.ports["solar_to_inverter"])

    # Inject data into load
    system.get_node("load").ports["load_to_cp"].add_demand_profile_from_array(load_data, expansion_periods)

    # Inject data into solar
    system.get_node("solar").ports["solar_to_inverter"].add_generation_profile_from_array(solar_data, expansion_periods)
    # Update ev with stateful parameters
    available = [1] * 8 + [0] * 2  # bool when at charger
    usage = [0.0] * 8 + [20] * 2  # kw average during use
    initial_state_of_charge = 0
    interval_duration = 60
    time_periods = len(available)

    # Inject data into the EV
    system.inject_data_into_ev(
        node_name="ev",
        available=available,
        usage=usage,
        initial_state_of_charge=initial_state_of_charge,
        interval_duration=interval_duration,
    )

    # Create objectives/tariffs
    import_cost = ImportTariff(
        component=connection_point.ports["cp_to_grid"], tariff_array=import_tariff, expansion_periods=expansion_periods
    )
    objective_set = ObjectiveSet(objective_list=[import_cost])

    # Invoke the optimiser and optimise
    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
            discount_rate=discount_rate,
        ),
        engine_settings=engine_settings,
        graph=system,
        objective_set=objective_set,
    )

    soc = optimise_results.values(ev.ports["vehicle"].soc_value, 0)

    expected_soc = np.array([4, 8, 12, 16, 26, 36, 36, 40, 20, 0])

    assert np.allclose(soc, expected_soc, rtol=10**-5)
