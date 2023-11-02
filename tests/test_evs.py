from __future__ import division

from typing import List, Tuple
import pytest

import numpy as np

from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import EV
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


def test_v2g_soc_conserv():
    pass
