import numpy as np
import pytest

from echo.echo_models import *
from echo.echo_thermal_models import *
from echo.echo_optimiser import EchoOptimiser
from echo.configuration import *
from echo.objectives import *

import os

SOLVER = os.environ.get('OPTIMISER_ENGINE', 'cplex')
SOLVER_EXECUTABLE = None

N_INTERVALS = 48


def test_gas_boiler_fixed_cop():
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    gas_mains = Node()
    gas_mains.ports['mains'] = GasPort()

    boiler = GasBoilerFixedCOP(max_input=1000,
                               min_input=4,
                               cop=0.8,
                               startup_eta=0.5)

    heating_load = Node()
    hl = FixedThermalPort()
    hl.add_initial_value_from_array([0] * 24 + [20] * 24, expansion_periods)
    heating_load.ports['load'] = hl

    system.add_node_obj([gas_mains, boiler, heating_load])
    system.connect_ports_and_create_edge(gas_mains.ports['mains'], boiler.ports['input'])
    system.connect_ports_and_create_edge(boiler.ports['output'], hl)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    optimiser.optimise(tee=True)

    print('mains gas: ', optimiser.values(gas_mains.ports['mains'].port_name, 0))
    print('boiler input (gas): ', optimiser.values(boiler.ports['input'].port_name, 0))
    print('boiler output (heat): ', optimiser.values(boiler.ports['output'].port_name, 0))
    print('heating load: ', hl.initial_value.values())

    gas_mains = optimiser.values(gas_mains.ports['mains'].port_name, 0)
    boiler_input = optimiser.values(boiler.ports['input'].port_name)
    boiler_output = optimiser.values(boiler.ports['output'].port_name)

    hl_p = hl.initial_value

    for i in range(time_periods):
        assert gas_mains[i] * boiler.cop == hl_p[(0, i)] * -1


def test_chiller_operation():
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.ports['grid'] = ElectricalPort()

    # nonlin_array = [-0.0068, 5.5052, 0]
    input_breakpoints = [0, 2, 3, 8]
    output_values = [0, 3, 4, 8]
    chiller = SimpleChiller(output_ub=8,
                            input_ub=8)
    chiller.add_input_pts(array=input_breakpoints, time_periods=time_periods)
    chiller.add_output_pts(array=output_values, time_periods=time_periods)

    cooling_load = Node()
    cl = FixedThermalPort()
    cl.add_initial_value_from_array([-4] * time_periods, expansion_periods)
    cooling_load.ports['load'] = cl

    system.add_node_obj([grid, chiller, cooling_load])
    system.connect_ports_and_create_edge(grid.ports['grid'], chiller.ports['input'])
    system.connect_ports_and_create_edge(chiller.ports['output'], cl)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    optimiser.optimise(tee=True)

    print('mains gas: ', optimiser.values(grid.ports['grid'].port_name, 0))
    print('chiller input (elec): ', optimiser.values(chiller.ports['input'].port_name, 0))
    print('chiller output (cooling): ', optimiser.values(chiller.ports['output'].port_name, 0))
    print('cooling load: ', cl.initial_value.values())
    print('cop: ', np.divide(optimiser.values(chiller.ports['output'].port_name, 0),
                             optimiser.values(chiller.ports['input'].port_name, 0)))

    chiller_input = optimiser.values(chiller.ports['input'].port_name, 0)
    # chiller_output = optimiser.values(chiller.ports['output'].port_name, 0)
    # grid_import = optimiser.values(grid.ports['grid'].port_name, 0)
    # cl_p = cl.initial_value
    # cop = np.divide(optimiser.values(chiller.ports['output'].port_name, 0), optimiser.values(chiller.ports['input'].port_name, 0))

    for i in range(time_periods):
        assert chiller_input[i] == 3


def test_carbon_aggregation():
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.ports['grid'] = ElectricalPort()
    grid.ports['CO2'] = CarbonSource()
    grid.add_emission_transformation(grid.ports['grid'], grid.ports['CO2'], 0.5)

    battery1 = Node()
    b1 = ElectricalStorage(max_capacity=15,
                           depth_of_discharge_limit=0,
                           charging_power_limit=2.0,
                           discharging_power_limit=-2.0,
                           charging_efficiency=1,
                           discharging_efficiency=1,
                           initial_state_of_charge=0.0)
    battery1.ports['battery'] = b1
    battery1.ports['CO2'] = CarbonSource()
    battery1.add_emission_transformation(b1, battery1.ports['CO2'], 0.2)

    load1 = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array(np.array([6] * time_periods), expansion_periods)
    load1.ports['demand'] = l1

    site1 = TellegenNode()
    site1.add_electrical_ports_from_list(['cp', 'load', 'bess'])

    carbon_aggr = CarbonAggregation()
    carbon_aggr.ports['grid'] = CarbonSink()
    carbon_aggr.ports['bess'] = CarbonSink()

    system.add_node_obj([grid, battery1, load1, site1, carbon_aggr])
    system.connect_ports_and_create_edge(grid.ports['grid'], site1.ports['cp'])
    system.connect_ports_and_create_edge(grid.ports['CO2'], carbon_aggr.ports['grid'])
    system.connect_ports_and_create_edge(site1.ports['bess'], b1)
    system.connect_ports_and_create_edge(battery1.ports['CO2'], carbon_aggr.ports['bess'])
    system.connect_ports_and_create_edge(site1.ports['load'], l1)

    import_tariff = ImportTariff(component=site1.ports['cp'],
                                 tariff_array=np.array(([0.1] * 24 + [0.3] * 24)),
                                 expansion_periods=expansion_periods)
    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=ObjectiveSet(objective_list=[import_tariff])
    )

    optimiser.optimise()

    grid_emissions = optimiser.values(grid.ports['CO2'].port_name, 0)
    bess_emissions = optimiser.values(battery1.ports['CO2'].port_name, 0)
    aggr = optimiser.values(carbon_aggr.ports['sum'].port_name, 0)

    for i in range(time_periods):
        assert aggr[i] * -1 == grid_emissions[i] + bess_emissions[i]


def test_temp_controlled_boiler():
    expansion_periods = 1
    time_periods = 24
    interval_duration = 60

    system = OptimisationGraph()

    source = Node()
    source.ports['source'] = GasPort()

    boiler = TempControlledBoiler(max_input=100,
                                  min_input=0,
                                  max_output=-100,
                                  min_output=0
                                  )

    heating_load = Node()
    hl = FixedThermalPort()
    hl.add_initial_value_from_array([0] * 12 + [5] * 12, expansion_periods)
    heating_load.ports['load'] = hl

    system.add_node_obj([source, boiler, heating_load])
    system.connect_ports_and_create_edge(source.ports['source'], boiler.ports['input'])
    system.connect_ports_and_create_edge(boiler.ports['output'], hl)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    optimiser.optimise(True)

    print()


def test_controllable_thermal_load():
    expansion_periods = 1
    time_periods = 24
    interval_duration = 60

    system = OptimisationGraph()

    source = Node()
    source.ports['source'] = ThermalPort()

    external_temp = np.array([2] * time_periods)
    external_temp_dict = generate_array_constraint(external_temp, time_periods, expansion_periods)
    temp_lb = np.array(
        [0] * 7 + [0.2] * 1 + [0.4] * 1 + [0.8] * 2 + [1] * 2 + [0.8] * 2 + [0.4] * 1 + [0.2] * 1 + [0] * 7) * 10
    temp_ub = np.array(temp_lb) + 5

    heating_load = ThermalNode(temp_ub=temp_ub,
                               temp_lb=temp_lb,
                               external_temp=external_temp_dict,
                               temp_to_energy_coef=1
                               )
    hl = FlexHeatSink()
    heating_load.ports['load'] = hl

    system.add_node_obj([source, heating_load])
    system.connect_ports_and_create_edge(source.ports['source'], hl)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    optimiser.optimise(True)

    print()


def test_new_heat_pump():
    expansion_periods = 1
    time_periods = 24
    interval_duration = 60

    system = OptimisationGraph()

    source = Node()
    source.ports['source'] = ElectricalPort()

    heating_cop = np.array([2] * time_periods)
    heat_cop_dict = generate_dict_with_pyomo_keys_from_array(heating_cop, time_periods)

    heat_pump = HeatPumpSingleOutput(heating_cop_time_series=heat_cop_dict,
                                     cooling_cop_time_series=heat_cop_dict)

    external_temp = np.array([2] * time_periods)
    external_temp_dict = generate_array_constraint(external_temp, time_periods, expansion_periods)
    temp_lb = np.array(
        [0] * 7 + [0.2] * 1 + [0.4] * 1 + [0.8] * 2 + [1] * 2 + [0.8] * 2 + [0.4] * 1 + [0.2] * 1 + [0] * 7) * 10
    temp_ub = np.array(temp_lb) + 5
    ub_dict = generate_dict_with_pyomo_keys_from_array(temp_ub, time_periods)
    lb_dict = generate_dict_with_pyomo_keys_from_array(temp_lb, time_periods)
    thermal_load = ThermalNode(temp_ub=ub_dict,
                               temp_lb=lb_dict,
                               external_temp=external_temp_dict,
                               temp_to_energy_coef=1
                               )
    hl = FlexHeatSink()
    thermal_load.ports['load'] = hl

    system.add_node_obj([source, heat_pump, thermal_load])
    system.connect_ports_and_create_edge(source.ports['source'], heat_pump.ports['input'])
    system.connect_ports_and_create_edge(heat_pump.ports['output'], hl)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    optimiser.optimise(True)

    print()


def test_simple_piecewise_node():
    expansion_periods = 1
    time_periods = 24
    interval_duration = 60

    system = OptimisationGraph()

    source = Node()
    source.ports['source'] = ElectricalPort()

    inputs = [0, 1, 2, 3]
    outputs = [0, -1, -2, -3]
    input_dict = populate_values_across_time_and_expansion_indices(inputs, time_periods, expansion_periods)
    output_dict = populate_values_across_time_and_expansion_indices(outputs, time_periods, expansion_periods)
    io_node = TimeVaryingPiecewiseIONode(input_port_unit=Units.KW, output_port_unit=Units.KW)
    io_node.input_pts = input_dict
    io_node.output_pts = output_dict

    sink_node = Node()
    sp = FixedElectricalPort()
    rand_load = np.random.uniform(0, 3, time_periods)
    sp.add_initial_value_from_array(rand_load)
    sink_node.ports['sink'] = sp

    system.add_node_obj([source, io_node, sink_node])
    system.connect_ports_and_create_edge(source.ports['source'], io_node.ports['input'])
    system.connect_ports_and_create_edge(io_node.ports['output'], sp)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    optimiser.optimise(True)

    load = rand_load
    io_output = optimiser.values(io_node.ports['output'].port_name)
    io_input = optimiser.values(io_node.ports['input'].port_name)

    plt.plot(load, label='load')
    plt.plot(io_input, label='io input')
    plt.plot(io_output, label='io output')
    plt.legend()
    plt.show()

    print()


def test_off_or_constrained_port():
    expansion_periods = 1
    time_periods = 24
    interval_duration = 60

    system = OptimisationGraph()

    source = Node()
    source.ports['source'] = ElectricalPort()

    node = TellegenNode()
    p = OffOrConstrainedPort(units=Units.KW, upper_bound=-4, lower_bound=-10)
    p2 = ElectricalPort()
    node.ports['in'] = p2
    node.ports['out'] = p

    load = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([0] * 12 + [5] * 12)
    load.ports['load'] = l1

    system.add_node_obj([source, node, load])
    system.connect_ports_and_create_edge(source.ports['source'], node.ports['in'])
    system.connect_ports_and_create_edge(node.ports['out'], l1)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    optimiser.optimise(True)

    print()


def test_thermal_node():
    expansion_periods = 1
    time_periods = 24
    interval_duration = 60

    system = OptimisationGraph()

    heating_source = Node()
    heating_source.ports['heating_source'] = ThermalPort(flows=Flows.Export)

    cooling_source = Node()
    cooling_source.ports['cooling_source'] = ThermalPort(flows=Flows.Import)

    external_temp = np.array([2] * time_periods)
    external_temp_dict = generate_array_constraint(external_temp, time_periods, expansion_periods)
    temp_lb = np.array(
        [0] * 7 + [0.2] * 1 + [0.4] * 1 + [0.8] * 2 + [1] * 2 + [0.8] * 2 + [0.4] * 1 + [0.2] * 1 + [0] * 7) * 10
    temp_ub = np.array(temp_lb) + 5

    ub_dict = generate_dict_with_pyomo_keys_from_array(temp_ub, time_periods, expansion_periods)
    lb_dict = generate_dict_with_pyomo_keys_from_array(temp_lb, time_periods, expansion_periods)
    thermal_load = ThermalNode(temp_ub=ub_dict,
                               temp_lb=lb_dict,
                               external_temp=external_temp_dict,
                               temp_to_energy_coef=1,
                               )
    thermal_load.ports['heating'] = ThermalPort(flows=Flows.Import)
    thermal_load.ports['cooling'] = ThermalPort(flows=Flows.Export)

    system.add_node_obj([cooling_source, heating_source, thermal_load])
    system.connect_ports_and_create_edge(heating_source.ports['heating_source'], thermal_load.ports['heating'])
    system.connect_ports_and_create_edge(cooling_source.ports['cooling_source'], thermal_load.ports['cooling'])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    optimiser.optimise(True)

    # check that our energy balance constraint is workin
    e_in = optimiser.values(thermal_load.ports['heating'].port_name)
    e_out = optimiser.values(thermal_load.ports['cooling'].port_name)
    losses = optimiser.values(thermal_load.losses)
    gains = optimiser.values(thermal_load.gains)

    # for i in range(time_periods):
    #     assert e_in[i] + e_out[i] ==

    print()
