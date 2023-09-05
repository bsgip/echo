from __future__ import division

import numpy as np

from echo.configuration import Units
from echo.echo_optimiser import EchoOptimiser
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import EV


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
    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=discount_rate,
        ES=system,
        objective_set=None,
    )

    optimiser.optimise(tee=True)


def test_v2g_soc_conserv():
    pass
