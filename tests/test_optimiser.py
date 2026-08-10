from echo.objectives.tariff import ImportTariff
from echo.objectives.base import ObjectiveSet
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.optimiser import optimise
from echo.configuration import Units
from echo.models.electrical import EVV2G
from echo.models.agnostic import TellegenNode, FlexPort
from echo.models.prebuilt import FlexElectricalNode
from echo.models.base import OptimisationGraph


def test_relative_mip_gap_cplex():
    """Check that the relative MIP gap keyword for Optimiser, mip_gap_relative, works for cplex."""

    # Define parameters
    available = [1] * 7 + [0] * 3  # bool when at charger
    usage = [0.0] * 7 + [5] * 3  # kw average during use
    interval_duration = 10
    time_periods = len(available)
    expansion_periods = 1  # not yet implemented leave as 1
    discount_rate = 0  # not yet implemented leave as 0

    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(port_name="grid_to_cp")

    # Create a connection point
    connection_point = TellegenNode()
    connection_point.add_ports_from_list(["cp_to_grid", "cp_to_ev"], FlexPort, units=Units.KW)

    # Create V0G vehicle
    ev = EVV2G(
        node_name="ev",
        available=available,
        usage=usage,
        connection_port_name="ev_to_cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-2.4,
        usage_power_limit=-20,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=20,
        soc_conserv=None,
        soc_conserv_cost=0.0,
        interval_duration=interval_duration,
        tod_charging=None,
        enable_trip_slack=True,
    )

    # Add nodes to the OptimisationGraph
    system.add_node_obj([grid, ev, connection_point])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["grid_to_cp"], connection_point.ports["cp_to_grid"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_ev"], ev.ports["ev_to_cp"])

    # Create objectives/tariffs
    import_tariff = [9, 10, 11, 1, 2, 3, 8, 9, 10, 11]  # $/kw
    import_cost = ImportTariff(
        component=connection_point.ports["cp_to_grid"],
        tariff_array=import_tariff,
        expansion_periods=expansion_periods,
    )
    objective_set = ObjectiveSet(objective_list=[import_cost])

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
        mip_gap_relative=0.01,
    )


def test_absolut_mip_gap_cplex():
    """Check that the absolute MIP gap keyword for Optimiser, mip_gap_absolute, works for cplex."""

    # Define parameters
    available = [1] * 7 + [0] * 3  # bool when at charger
    usage = [0.0] * 7 + [5] * 3  # kw average during use
    interval_duration = 10
    time_periods = len(available)
    expansion_periods = 1  # not yet implemented leave as 1
    discount_rate = 0  # not yet implemented leave as 0

    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(port_name="grid_to_cp")

    # Create a connection point
    connection_point = TellegenNode()
    connection_point.add_ports_from_list(["cp_to_grid", "cp_to_ev"], FlexPort, units=Units.KW)

    # Create V0G vehicle
    ev = EVV2G(
        node_name="ev",
        available=available,
        usage=usage,
        connection_port_name="ev_to_cp",
        max_capacity=40,
        depth_of_discharge_limit=0,
        charging_power_limit=10,
        discharging_power_limit=-2.4,
        usage_power_limit=-20,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=20,
        soc_conserv=None,
        soc_conserv_cost=0.0,
        interval_duration=interval_duration,
        tod_charging=None,
        enable_trip_slack=True,
    )

    # Add nodes to the OptimisationGraph
    system.add_node_obj([grid, ev, connection_point])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["grid_to_cp"], connection_point.ports["cp_to_grid"])
    system.connect_ports_and_create_edge(connection_point.ports["cp_to_ev"], ev.ports["ev_to_cp"])

    # Create objectives/tariffs
    import_tariff = [9, 10, 11, 1, 2, 3, 8, 9, 10, 11]  # $/kw
    import_cost = ImportTariff(
        component=connection_point.ports["cp_to_grid"],
        tariff_array=import_tariff,
        expansion_periods=expansion_periods,
    )
    objective_set = ObjectiveSet(objective_list=[import_cost])

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
        mip_gap_absolute=0.01,
        show_solver_output=True,
    )
