import numpy as np

from echo.echo_models import *
from echo.echo_optimiser import EchoOptimiser
from echo.configuration import *
from echo.objectives import *

from hypothesis.extra.numpy import arrays
from hypothesis.strategies import floats
from hypothesis import given, settings


import os

SOLVER = os.environ.get('OPTIMISER_ENGINE','cplex')
SOLVER_EXECUTABLE = None


def test_partitioning_regions_for_path_flow():

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min

    system = OptimisationGraph()

    grid = Node()
    grid.add_named_electrical_ports(['grid'])

    battery = Node()
    b1 = ElectricalStorage(max_capacity=48,
                           depth_of_discharge_limit=0,
                           charging_power_limit=5.0,
                           discharging_power_limit=-5.0,
                           charging_efficiency=1,
                           discharging_efficiency=1,
                           initial_state_of_charge=48.0)
    battery.ports['battery_asset'] = b1

    solar = Node()
    pv1 = ElectricalGeneration()
    pv1.add_generation_profile_from_array([-4] * time_periods, expansion_periods)
    pv1.curtailable = False
    solar.ports['solar'] = pv1

    inverter = Inverter(max_import=5, max_export=-5, dc_ac_efficiency=1, ac_dc_efficiency=1)
    inverter.add_ac_port('cp')
    inverter.add_dc_port('bess')
    inverter.add_dc_port('pv')

    cp = ElectricalTellegenNode()
    cp.add_named_electrical_ports(['load', 'inv', 'grid'])

    load = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([6]*time_periods, expansion_periods)
    load.ports['load'] = l1

    system.add_node_obj([grid, cp, load, battery, solar, inverter])

    system.connect_ports_and_create_edge(inverter.ports['bess'], b1)
    system.connect_ports_and_create_edge(inverter.ports['pv'], pv1)
    system.connect_ports_and_create_edge(cp.ports['load'], l1)
    system.connect_ports_and_create_edge(inverter.ports['cp'], cp.ports['inv'])
    system.connect_ports_and_create_edge(cp.ports['grid'], grid.ports['grid'])

    system.create_path_objects(sources=[grid, inverter], sinks=[grid, inverter, load])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    optimiser.optimise(tee=True)

    grid_to_inverter = system.paths[(grid, cp, inverter)]
    grid_to_load = system.paths[(grid, cp, load)]
    inverter_to_grid = system.paths[(inverter, cp, grid)]
    inverter_to_load = system.paths[(inverter, cp, load)]

    for i in range(time_periods):
        np.testing.assert_almost_equal(optimiser.values(grid_to_load.flow_value, 0)[i] +
                                       optimiser.values(grid_to_inverter.flow_value, 0)[i],
                                       optimiser.values(grid.ports['grid'].port_name, 0)[i]*-1)

        np.testing.assert_almost_equal(optimiser.values(inverter_to_grid.flow_value, 0)[i] +
                                       optimiser.values(inverter_to_load.flow_value, 0)[i],
                                       optimiser.values(inverter.ports['cp'].port_name, 0)[i]*-1)


def test_regularisation_of_path_flows():

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min

    system = OptimisationGraph()

    source1 = Node()
    s1 = ElectricalGeneration()
    s1.add_generation_profile_from_array([-1]*time_periods, expansion_periods)
    source1.ports['s1'] = s1

    source2 = Node()
    s2 = ElectricalGeneration()
    s2.add_generation_profile_from_array([-3]*time_periods, expansion_periods)
    source2.ports['s2'] = s2

    cp = ElectricalTellegenNode()
    cp.add_named_electrical_ports(['s1', 's2', 'l1', 'l2'])

    load1 = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array([2]*time_periods, expansion_periods)
    load1.ports['l1'] = l1

    load2 = Node()
    l2 = ElectricalDemand()
    l2.add_demand_profile_from_array([2]*time_periods, expansion_periods)
    load2.ports['l2'] = l2

    system.add_node_obj([source1, source2, load1, load2, cp])
    system.connect_ports_and_create_edge(s1, cp.ports['s1'])
    system.connect_ports_and_create_edge(s2, cp.ports['s2'])
    system.connect_ports_and_create_edge(l1, cp.ports['l1'])
    system.connect_ports_and_create_edge(l2, cp.ports['l2'])

    system.create_path_objects(sources=[source1, source2], sinks=[load1, load2], regularise=True)

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    optimiser.optimise(tee=True)
    print(optimiser.opt_status)

    s1_to_l1 = optimiser.values(system.paths[(source1, cp, load1)].flow_value, 0)*-1
    s1_to_l2 = optimiser.values(system.paths[(source1, cp, load2)].flow_value, 0)*-1
    s2_to_l1 = optimiser.values(system.paths[(source2, cp, load1)].flow_value, 0)*-1
    s2_to_l2 = optimiser.values(system.paths[(source2, cp, load2)].flow_value, 0)*-1

    for i in range(time_periods):
        np.testing.assert_almost_equal(s1_to_l1[i], optimiser.values(s1.port_name, 0)[i]/2)
        np.testing.assert_almost_equal(s1_to_l2[i], optimiser.values(s1.port_name, 0)[i]/2)
        np.testing.assert_almost_equal(s2_to_l1[i], optimiser.values(s2.port_name, 0)[i]/2)
        np.testing.assert_almost_equal(s2_to_l2[i], optimiser.values(s2.port_name, 0)[i]/2)









