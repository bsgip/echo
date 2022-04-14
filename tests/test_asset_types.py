import numpy as np
import pytest

from echo.echo_models import *
from echo.echo_optimiser import EchoOptimiser
from echo.configuration import *
from echo.objectives import *

import os

SOLVER = os.environ.get('OPTIMISER_ENGINE','cplex')
SOLVER_EXECUTABLE = None



N_INTERVALS = 48


def test_gas_boiler_operation():

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    gas_mains = Node()
    gas_mains.ports['mains'] = GasPort()

    boiler = GasBoiler(0.5)

    heating_load = Node()
    hl = ThermalLoad()
    hl.add_sink_profile_from_array([5]*time_periods, expansion_periods)
    heating_load.ports['load'] = hl

    system.add_node_obj([gas_mains, boiler, heating_load])
    system.connect_ports_and_create_edge(gas_mains.ports['mains'], boiler.ports['gas'])
    system.connect_ports_and_create_edge(boiler.ports['heat'], hl)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    optimiser.optimise()

    print('mains gas: ', optimiser.values(gas_mains.ports['mains'].port_name, 0))
    print('boiler input (gas): ', optimiser.values(boiler.ports['gas'].port_name, 0))
    print('boiler output (heat): ', optimiser.values(boiler.ports['heat'].port_name, 0))
    print('heating load: ', hl.initial_value.values())

    gas_mains = optimiser.values(gas_mains.ports['mains'].port_name, 0)
    hl_p = hl.initial_value

    for i in range(time_periods):
        assert gas_mains[i] * boiler.gas_to_heat_efficiency == hl_p[(0, i)]*-1


def test_chiller_operation():

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.ports['grid'] = ElectricalPort()

    nonlin_array = [-0.0068, 5.5052, 0]
    chiller = Chiller(pw_input=[0, 2, 4, 8],
                      pw_output=[0, 3, 4, 8],
                      max_output=-8,
                      max_input=8,
                      coeff_array=nonlin_array)

    cooling_load = Node()
    cl = ThermalLoad()
    cl.add_sink_profile_from_array([4]*time_periods, expansion_periods)
    cooling_load.ports['load'] = cl

    system.add_node_obj([grid, chiller, cooling_load])
    system.connect_ports_and_create_edge(grid.ports['grid'], chiller.input)
    system.connect_ports_and_create_edge(chiller.output, cl)

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
    print('chiller input (elec): ', optimiser.values(chiller.input.port_name, 0))
    print('chiller output (cooling): ', optimiser.values(chiller.output.port_name, 0))
    print('cooling load: ', cl.initial_value.values())
    print('cop: ', np.divide(optimiser.values(chiller.output.port_name, 0), optimiser.values(chiller.input.port_name, 0)))

    chiller_input = optimiser.values(chiller.input.port_name, 0)
    chiller_output = optimiser.values(chiller.output.port_name, 0)
    grid_import = optimiser.values(grid.ports['grid'].port_name, 0)
    cl_p = cl.initial_value
    cop = np.divide(optimiser.values(chiller.output.port_name, 0), optimiser.values(chiller.input.port_name, 0))

    for i in range(time_periods):
        np.testing.assert_almost_equal(chiller_output[i]*-1,
                                       chiller_input[i]**2*nonlin_array[0] + chiller_input[i]*nonlin_array[1] + nonlin_array[2], 2)


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

    site1 = ElectricalTellegenNode()
    site1.add_named_electrical_ports(['cp', 'load', 'bess'])

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
        assert aggr[i]*-1 == grid_emissions[i] + bess_emissions[i]
