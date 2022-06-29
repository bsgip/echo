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

    boiler = GasBoilerFixedCOP(max_input=10,
                               min_input=5,
                               max_output=-10,
                               min_output=-5,
                               cop=0.8)

    heating_load = Node()
    hl = ThermalLoad()
    hl.add_sink_profile_from_array([0] * 24 + [5] * 24, expansion_periods)
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

    nonlin_array = [-0.0068, 5.5052, 0]
    input_breakpoints = [0, 2, 3, 8]
    output_values = [0, -3, -4, -8]
    chiller = Chiller(max_output=-8,
                      max_input=8)
    chiller.set_input_output_breakpoints(input_array=input_breakpoints, output_array=output_values,
                                         time_periods=time_periods)

    cooling_load = Node()
    cl = HeatingOrCoolingLoad()
    cl.add_sink_profile_from_array([4] * time_periods, expansion_periods)
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

    optimiser.optimise()

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


def test_temp_controlled_load():
    expansion_periods = 1
    time_periods = 24
    interval_duration = 60

    system = OptimisationGraph()

    source = Node()
    source.ports['source'] = ThermalPort()

    hl_node = Node()
    external_temp = np.array([2] * time_periods)
    external_temp = generate_array_constraint(external_temp, time_periods, expansion_periods)
    temp_lb = np.array(
        [0] * 7 + [0.2] * 1 + [0.4] * 1 + [0.8] * 2 + [1] * 2 + [0.8] * 2 + [0.4] * 1 + [0.2] * 1 + [0] * 7) * 10
    temp_ub = np.array(temp_lb) + 5
    heating_load = TemperatureControlledHeatingLoad(temp_ub=temp_ub,
                                                    temp_lb=temp_lb,
                                                    external_temp=external_temp,
                                                    loss_factor=1
                                                    )
    hl_node.ports['load'] = heating_load

    system.add_node_obj([source, hl_node])
    system.connect_ports_and_create_edge(source.ports['source'], heating_load)

    throughput_cost = ThroughputCost(component=source.ports['source'],
                                     rate=0.00001)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=ObjectiveSet(objective_list=[throughput_cost])
    )

    optimiser.optimise(tee=True)

    internal_temp = optimiser.values(heating_load.internal_temp)
    power_drawn = optimiser.values(heating_load.port_name)
    plt.plot(internal_temp)
    plt.plot(power_drawn)
    plt.plot(temp_ub)
    plt.plot(temp_lb)

    plt.legend(['Internal temp', 'Power drawn', 'Temp upper bound', 'Temp lower bound'])
    plt.show()


def test_temp_controlled_boiler():
    expansion_periods = 1
    time_periods = 24
    interval_duration = 60

    system = OptimisationGraph()

    source = Node()
    source.ports['source'] = GasPort()

    boiler = TempControlledBoiler()

    heating_load = Node()
    hl = ThermalLoad()
    hl.add_sink_profile_from_array([0] * 24 + [5] * 24, expansion_periods)
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


def test_building_thermal_load():
    expansion_periods = 1
    time_periods = 24
    interval_duration = 60

    system = OptimisationGraph()

    heatsource = Node()
    heatsource.ports['source'] = ThermalPort()

    coolingsource = Node()
    coolingsource.ports['source'] = ThermalPort()

    external_temp = np.array([2] * time_periods)
    external_temp_dict = generate_array_constraint(external_temp, time_periods, expansion_periods)
    temp_lb = np.array(
        [0] * 7 + [0.2] * 1 + [0.4] * 1 + [0.8] * 2 + [1] * 2 + [0.8] * 2 + [0.4] * 1 + [0.2] * 1 + [0] * 7) * 10
    temp_ub = np.array(temp_lb) + 5
    building_node = BuildingThermalLoad(temp_ub=temp_ub,
                                        temp_lb=temp_lb,
                                        external_temp=external_temp_dict,
                                        loss_factor=0,
                                        temp_to_energy_coef=2.5
                                        )

    system.add_node_obj([heatsource, coolingsource, building_node])
    system.connect_ports_and_create_edge(heatsource.ports['source'], building_node.ports['heating'])
    system.connect_ports_and_create_edge(coolingsource.ports['source'], building_node.ports['cooling'])

    throughput_cost1 = ThroughputCost(component=heatsource.ports['source'],
                                      rate=0.00001)
    throughput_cost2 = ThroughputCost(component=coolingsource.ports['source'],
                                      rate=0.00001)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=ObjectiveSet(objective_list=[throughput_cost1, throughput_cost2])
    )

    optimiser.optimise(tee=True)

    internal_temp = optimiser.values(building_node.internal_temp)
    heating_draw = optimiser.values(building_node.ports['heating'].port_name)
    cooling_draw = optimiser.values(building_node.ports['cooling'].port_name)


def test_heat_pump():

    expansion_periods = 1
    time_periods = 24
    interval_duration = 60

    system = OptimisationGraph()

    grid = Node()
    grid.ports['grid'] = ElectricalPort()


    heating_cop = np.linspace(1.6, 4.45, num=time_periods)
    heat_cop_dict = generate_dict_with_pyomo_keys_from_array(heating_cop, time_periods)
    cooling_cop = np.linspace(4.5, 2.15, num=time_periods)
    cool_cop_dict = generate_dict_with_pyomo_keys_from_array(cooling_cop, time_periods, expansion_periods)

    heat_pump = HeatPump(heating_cop_time_series=heat_cop_dict,
                         cooling_cop_time_series=cool_cop_dict)

    heating_load = Node()
    hl = ThermalLoad()
    hl.add_sink_profile_from_array([5]*12 + [0]*12)
    heating_load.ports['load'] = hl

    cooling_load = Node()
    cl = ThermalLoad()
    cl.add_sink_profile_from_array([0]*12 + [5]*12)
    cooling_load.ports['load'] = cl

    system.add_node_obj([grid, heat_pump, heating_load, cooling_load])
    system.connect_ports_and_create_edge(grid.ports['grid'], heat_pump.ports['input'])
    system.connect_ports_and_create_edge(heat_pump.ports['heating_out'], hl)
    system.connect_ports_and_create_edge(heat_pump.ports['cooling_out'], cl)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    optimiser.optimise(tee=True)

    hp_cop = heat_pump.get_heating_cop(optimiser)
    print(optimiser.node_values(heat_pump))

