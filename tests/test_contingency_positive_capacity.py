import os

import numpy as np

from echo.configuration import *
from echo.echo_models import *
from echo.echo_optimiser import EchoOptimiser
from echo.objectives import *

SOLVER = os.environ.get("OPTIMISER_ENGINE", "cplex")
SOLVER_EXECUTABLE = None


def test_positive_contingency_unaffected_by_uncurtailable_solar_capacity():
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    battery = Node()
    b1 = ElectricalStorage(
        max_capacity=48,
        depth_of_discharge_limit=0,
        charging_power_limit=5.0,
        discharging_power_limit=-5.0,
        charging_efficiency=0.9,
        discharging_efficiency=1,
        initial_state_of_charge=0.0,
    )
    battery.ports["battery_asset"] = b1

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-4] * 24 + [0] * 24, expansion_periods)
    solar.ports["solar"] = pv1

    inverter = TellegenNode()
    inverter.add_ports_from_list(["cp", "bess", "pv"], FlexPort, units=Units.KW)
    inverter.ports["cp"].set_flow_constraints(max_export=-5.0, max_import=5.0)

    system.add_node_obj([grid, battery, solar, inverter])

    system.connect_ports_and_create_edge(inverter.ports["bess"], b1)
    system.connect_ports_and_create_edge(inverter.ports["pv"], pv1)
    system.connect_ports_and_create_edge(inverter.ports["cp"], grid.ports["grid"])

    system.create_path_objects(sources=[grid, battery, solar], sinks=[grid, battery, solar])

    bess_to_g = system.get_path([battery, inverter, grid])

    contingency_obj = ContingencyPositive(component=bess_to_g, duration=10.0)

    objective_set = ObjectiveSet(objective_list=[contingency_obj])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=objective_set,
    )

    optimiser.optimise()

    cont_pos_p = optimiser.values(contingency_obj.contingency_pos, 0)

    for i in range(time_periods):
        assert cont_pos_p[i] == 5.0


def test_storage_discharge_and_solar_curtailment_to_maximise_positive_contingency_():
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min
    N_INTERVALS = time_periods

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    battery = Node()
    b1 = ElectricalStorage(
        max_capacity=48,
        depth_of_discharge_limit=0,
        charging_power_limit=2.0,
        discharging_power_limit=-2.0,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=48.0,
    )
    battery.ports["battery_asset"] = b1

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-5] * 24 + [0] * 24, expansion_periods)
    pv1.curtailable = True
    solar.ports["solar"] = pv1

    inverter = TellegenNode()
    inverter.add_ports_from_list(["cp", "bess", "pv"], FlexPort, units=Units.KW)
    inverter.ports["cp"].set_flow_constraints(max_export=-5.0, max_import=5.0)

    system.add_node_obj([grid, battery, solar, inverter])

    system.connect_ports_and_create_edge(inverter.ports["bess"], b1)
    system.connect_ports_and_create_edge(inverter.ports["pv"], pv1)
    system.connect_ports_and_create_edge(inverter.ports["cp"], grid.ports["grid"])

    system.create_path_objects(sources=[grid, battery, solar], sinks=[grid, battery, solar])

    bess_to_g = system.get_path([battery, inverter, grid])
    contingency_obj = ContingencyPositive(component=bess_to_g, duration=10.0)

    objective_set = ObjectiveSet(objective_list=[contingency_obj])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=objective_set,
    )

    optimiser.optimise()

    cont_pos_p = optimiser.values(contingency_obj.contingency_pos, 0)
    sol_p = optimiser.values(pv1.port_name, 0)

    # for i in range(0, 1):
    #     assert cont_pos_p[i] == pytest.approx(2.0, rel=utils.RELATIVE_TOLERANCE,
    #                                           abs=utils.ABSOLUTE_TOLERANCE), "value is not greater than or equal to within {tolerance}"
    #
    # for i in range(1, N_INTERVALS // 2):
    #     assert cont_pos_p[i] == 4.0
    #     assert sol_p[i] >= -3.0  # Solar at least partially curtailed
    # for i in range(N_INTERVALS // 2, N_INTERVALS):
    #     assert cont_pos_p[i] == 4.0
    #     assert sol_p[i] == 0.0

    #
    #
    # battery = Storage(name='sto', min_power=-2.0, max_power=2.0, max_capacity=48.0)
    # system = Junction(
    #     name='root',
    #     connections=[
    #         Inverter(name='inv', connections=[
    #             Solar(name='sol', curtailable=True),
    #             battery
    #         ], max_power=5.0, min_power=-5.0)
    #     ]
    # )
    #
    # model = ConcreteModel()
    #
    # model.time = en.RangeSet(0, N_INTERVALS - 1)
    # model.interval_duration = [30.0] * N_INTERVALS
    # model.big_m = 1000000
    #
    # df = pd.DataFrame({'sol_p_max': [-5.0] * (N_INTERVALS // 2) + [0.0] * (N_INTERVALS // 2)})
    #
    # system_initial_state = {"sto_soc": 48.0}
    # options = Options()
    #
    # system.initialise_model(model, df.to_dict(), system_initial_state, options)
    # system.apply_constraints(model, system)
    #
    # objective = ObjectiveSet(objectives=[
    #     ContingencyPositive(component=battery.name)
    # ])
    # objective.initialise_objective(model, system)
    # objective.set_objective(model)
    #
    # solver = SolverFactory(SOLVER, executable=SOLVER_EXECUTABLE)
    # result = solver.solve(model, tee=True)
    #
    # cont_pos_p = model.sto_p_contingency_pos.extract_values()
    # sol_p = model.sol_p.extract_values()
    #
    # for i in range(0, 1):
    #     assert cont_pos_p[i] == pytest.approx(2.0, rel=utils.RELATIVE_TOLERANCE,
    #                                           abs=utils.ABSOLUTE_TOLERANCE), "value is not greater than or equal to within {tolerance}"
    # for i in range(1, N_INTERVALS // 2):
    #     assert cont_pos_p[i] == 4.0
    #     assert sol_p[i] >= -3.0  # Solar at least partially curtailed
    # for i in range(N_INTERVALS // 2, N_INTERVALS):
    #     assert cont_pos_p[i] == 4.0
    #     assert sol_p[i] == 0.0


def test_positive_contingency_calculation_with_storage_full():
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min
    N_INTERVALS = time_periods

    system = OptimisationGraph()

    grid = Node()
    grid.add_ports_from_list(["grid"], FlexPort, units=Units.KW)

    battery = Node()
    b1 = ElectricalStorage(
        max_capacity=48,
        depth_of_discharge_limit=0,
        charging_power_limit=5.0,
        discharging_power_limit=-0.0,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=48.0,
    )
    battery.ports["battery_asset"] = b1

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-4] * time_periods, expansion_periods)
    solar.ports["solar"] = pv1

    inverter = Inverter(max_import=5, max_export=-5, dc_ac_efficiency=1, ac_dc_efficiency=1)
    inverter.add_ac_port("cp")
    inverter.add_dc_port("bess")
    inverter.add_dc_port("pv")

    cp = Node()
    cp.add_ports_from_list(["load", "inv", "grid"], FlexPort, units=Units.KW)
    cp.node_rule = NodeRule.Tellegen

    load = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([6.0] * time_periods, expansion_periods)
    load.ports["load"] = l1

    system.add_node_obj([grid, cp, load, battery, solar, inverter])

    system.connect_ports_and_create_edge(inverter.ports["bess"], b1)
    system.connect_ports_and_create_edge(inverter.ports["pv"], pv1)
    system.connect_ports_and_create_edge(cp.ports["load"], l1)
    system.connect_ports_and_create_edge(inverter.ports["cp"], cp.ports["inv"])
    system.connect_ports_and_create_edge(cp.ports["grid"], grid.ports["grid"])

    system.create_path_objects(sources=[grid, battery, load, solar], sinks=[grid, battery, load, solar])

    bess_to_g = system.get_path([battery, inverter, cp, grid])
    contingency_obj = ContingencyPositive(component=bess_to_g, duration=10.0)

    objective_set = ObjectiveSet(objective_list=[contingency_obj])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=objective_set,
    )

    optimiser.optimise()

    cont_pos_p = optimiser.values(contingency_obj.contingency_pos, 0)

    for i in range(N_INTERVALS):
        np.testing.assert_almost_equal(cont_pos_p[i], 0.0, 5)  # Had to update to 5dp
