from __future__ import division

from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import ElectricalGeneration, Inverter
from echo.models.prebuilt import FlexElectricalNode
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.objectives.base import ObjectiveSet
from echo.objectives.tariff import ImportTariff
from echo.optimiser import optimise


def test_efficiency():
    """Ensure that efficiency attributes on nodes functional """

    # Define parameters
    solar_data = [-1, -1, -1, -1]  # kw load
    import_tariff = [1, 1, 1, 1]  # $/kw
    interval_duration = 60
    time_periods = len(solar_data)
    expansion_periods = 1  # not yet implemented leave as 1
    discount_rate = 0  # not yet implemented leave as 0

    # --- System 1: efficiency of 1 ---
    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(node_name="grid", port_name="grid_to_cp")

    # Create a connection point
    connection_point = TellegenNode(node_name="connection_point")
    connection_point.add_ports_from_list(["cp_to_grid", "cp_to_inverter"], FlexPort, units=Units.KW)

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

    # Add nodes to the OptimisationGraph
    system.add_node_obj([grid, connection_point, inverter, solar])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["grid_to_cp"], connection_point.ports["cp_to_grid"])
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
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=objective_set,
    )

    ac_flow_1 = optimise_results.values(inverter.ports["inverter_to_cp"].port_name, 0)

    # --- System 2: efficiency of 1 for verification ---
    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(node_name="grid", port_name="grid_to_cp")

    # Create a connection point
    connection_point = TellegenNode(node_name="connection_point")
    connection_point.add_ports_from_list(["cp_to_grid", "cp_to_inverter"], FlexPort, units=Units.KW)

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

    # Add nodes to the OptimisationGraph
    system.add_node_obj([grid, connection_point, inverter, solar])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["grid_to_cp"], connection_point.ports["cp_to_grid"])
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
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=objective_set,
    )

    ac_flow_2 = optimise_results.values(inverter.ports["inverter_to_cp"].port_name, 0)


    # --- System 3: efficiency of 0.5 ---
    # Create graph
    system = OptimisationGraph()

    # Create an infinite grid node with one downstream port
    grid = FlexElectricalNode(node_name="grid", port_name="grid_to_cp")

    # Create a connection point
    connection_point = TellegenNode(node_name="connection_point")
    connection_point.add_ports_from_list(["cp_to_grid", "cp_to_inverter"], FlexPort, units=Units.KW)

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
        dc_ac_efficiency=0.5,
        ac_dc_efficiency=1,
        ac_port_name="inverter_to_cp",
        dc_port_names=["inverter_to_solar"],
    )

    # Add nodes to the OptimisationGraph
    system.add_node_obj([grid, connection_point, inverter, solar])

    # Create edge objects and add to graph
    system.connect_ports_and_create_edge(grid.ports["grid_to_cp"], connection_point.ports["cp_to_grid"])
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
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=objective_set,
    )

    ac_flow_3 = optimise_results.values(inverter.ports["inverter_to_cp"].port_name, 0)

    assert len(set(ac_flow_1)) == 1
    assert len(set(ac_flow_2)) == 1
    assert len(set(ac_flow_3)) == 1

    assert round(list(set(ac_flow_1))[0], 1) == -1.0
    assert round(list(set(ac_flow_2))[0], 1) == -1.0
    assert round(list(set(ac_flow_3))[0], 1) == -0.5
