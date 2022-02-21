import random
import time
import timeit
import numpy as np
from matplotlib.pyplot import figure

from echo_models import *
from echo_optimiser import EchoOptimiser
from objectives import *
import networkx as nx

import os

SOLVER = os.environ.get('OPTIMISER_ENGINE', 'cplex')
SOLVER_EXECUTABLE = None

N_INTERVALS = 48

def test_many_node_system_no_objective():

    ## Set params
    num_gen = 40
    num_loads = 30
    num_storage = 100
    num_tellegen_nodes = 200

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min

    max_demand = 6
    min_demand = 0

    max_gen = -10
    min_gen = 0

    tellegen_node_set = set(range(num_tellegen_nodes))

    ###### Create graph
    system = OptimisationGraph()

    # Generate a random tree using all the tellegen nodes
    rand_tree = nx.random_tree(num_tellegen_nodes)

    node_name_map = {}  #

    # Create echo nodes and edges for tellegen nodes
    for node in rand_tree.nodes:
        n = ElectricalTellegenNode()
        node_name_map[str(node)] = n
        system.add_node(n)

    for edge in rand_tree.edges:
        n1 = edge[0]
        n2 = edge[1]
        node1 = node_name_map[str(n1)]
        node2 = node_name_map[str(n2)]
        system.connect_two_nodes_create_edges_create_ports(node1, node2)

    # Connect loads to random nodes
    for i in range(num_loads):
        # Pick a random node to connect the load to
        x = random.sample(tellegen_node_set, 1)
        sel_node = node_name_map[str(x[0])]

        # Create load node with random demand profile
        load = ElectricalNode()
        lp = ElectricalDemand()
        lp.add_demand_profile_from_array(np.random.randint(min_demand, max_demand, time_periods), expansion_periods)
        name = 'load_' + str(i)
        node_name_map[name] = load
        load.ports[name] = lp
        system.add_node_obj(load)
        system.connect_port_to_node_create_edges_create_port(lp, sel_node)

    # Connect generators to random nodes
    for i in range(num_gen):
        # Pick a random node to connect the generator to
        x = random.sample(tellegen_node_set, 1)
        sel_node = node_name_map[str(x[0])]

        # Create generation node with random generation profile
        gen = ElectricalNode()
        gp = ElectricalGeneration()
        gp.curtailable = False
        gp.add_generation_profile_from_array(np.random.randint(max_gen, min_gen, time_periods), expansion_periods)
        name = 'gen_' + str(i)
        node_name_map[name] = gen
        gen.ports[name] = gp
        system.add_node_obj(gen)
        system.connect_port_to_node_create_edges_create_port(gp, sel_node)

    # Connect storage to random nodes
    for i in range(num_storage):
        # Pick a random node to connect the storage to
        x = random.sample(tellegen_node_set, 1)
        sel_node = node_name_map[str(x[0])]

        # Create storage node
        bess = ElectricalNode()
        b1 = ElectricalStorage(max_capacity=48,
                               depth_of_discharge_limit=0,
                               charging_power_limit=5.0,
                               discharging_power_limit=-5.0,
                               charging_efficiency=1,
                               discharging_efficiency=1,
                               initial_state_of_charge=48.0)
        name = 'bess_' + str(i)
        node_name_map[name] = bess
        bess.ports[name] = b1
        system.add_node_obj(bess)
        system.connect_port_to_node_create_edges_create_port(b1, sel_node)

    # To ensure we can always meet reliability, add a grid node, connect it to a random tellegen node
    x = random.sample(tellegen_node_set, 1)
    sel_node = node_name_map[str(x[0])]

    grid = ElectricalNode()
    g = ElectricalPort()
    grid.ports['grid'] = g
    node_name_map['grid'] = grid
    system.add_node_obj(grid)
    system.connect_port_to_node_create_edges_create_port(g, sel_node)

    nx.draw(system, with_labels=True)

    start = time.time()
    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    optimiser.optimise()

    end = time.time()
    print('Total nodes: ', system.number_of_nodes())
    print('Time taken to construct echo optimiser and optimise: ', end-start)



def test_many_node_system_with_objectives():

    ## Set params

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min

    max_demand = 6
    min_demand = 0

    max_gen = -10
    min_gen = 0

    ###### Create graph

    num_gen = 40
    num_loads = 30
    num_storage = 20
    num_tellegen_nodes = 100

    tellegen_node_set = set(range(num_tellegen_nodes))

    ###### Create graph
    system = OptimisationGraph()

    # Generate a random tree using all the tellegen nodes
    rand_tree = nx.random_tree(num_tellegen_nodes)

    node_name_map = {}  #

    # Create echo nodes and edges for tellegen nodes
    for node in rand_tree.nodes:
        n = ElectricalTellegenNode()
        node_name_map[str(node)] = n
        system.add_node(n)

    for edge in rand_tree.edges:
        n1 = edge[0]
        n2 = edge[1]
        node1 = node_name_map[str(n1)]
        node2 = node_name_map[str(n2)]
        system.connect_two_nodes_create_edges_create_ports(node1, node2)

    # Connect loads to random nodes
    for i in range(num_loads):
        # Pick a random node to connect the load to
        x = random.sample(tellegen_node_set, 1)
        sel_node = node_name_map[str(x[0])]

        # Create load node with random demand profile
        load = ElectricalNode()
        lp = ElectricalDemand()
        lp.add_demand_profile_from_array(np.random.randint(min_demand, max_demand, time_periods), expansion_periods)
        name = 'load_' + str(i)
        node_name_map[name] = load
        load.ports[name] = lp
        system.add_node_obj(load)
        system.connect_port_to_node_create_edges_create_port(lp, sel_node)

    # Connect generators to random nodes
    for i in range(num_gen):
        # Pick a random node to connect the generator to
        x = random.sample(tellegen_node_set, 1)
        sel_node = node_name_map[str(x[0])]

        # Create generation node with random generation profile
        gen = ElectricalNode()
        gp = ElectricalGeneration()
        gp.curtailable = False
        gp.add_generation_profile_from_array(np.random.randint(max_gen, min_gen, time_periods), expansion_periods)
        name = 'gen_' + str(i)
        node_name_map[name] = gen
        gen.ports[name] = gp
        system.add_node_obj(gen)
        system.connect_port_to_node_create_edges_create_port(gp, sel_node)

    # Connect storage to random nodes
    for i in range(num_storage):
        # Pick a random node to connect the storage to
        x = random.sample(tellegen_node_set, 1)
        sel_node = node_name_map[str(x[0])]

        # Create storage node
        bess = ElectricalNode()
        b1 = ElectricalStorage(max_capacity=48,
                               depth_of_discharge_limit=0,
                               charging_power_limit=5.0,
                               discharging_power_limit=-5.0,
                               charging_efficiency=1,
                               discharging_efficiency=1,
                               initial_state_of_charge=48.0)
        name = 'bess_' + str(i)
        node_name_map[name] = bess
        bess.ports[name] = b1
        system.add_node_obj(bess)
        system.connect_port_to_node_create_edges_create_port(b1, sel_node)

    # To ensure we can always meet reliability, add a grid node, connect it to a random tellegen node
    x = random.sample(tellegen_node_set, 1)
    sel_node = node_name_map[str(x[0])]

    grid = ElectricalNode()
    g = ElectricalPort()
    grid.ports['grid'] = g
    node_name_map['grid'] = grid
    system.add_node_obj(grid)
    system.connect_port_to_node_create_edges_create_port(g, sel_node)

    nx.draw(system, with_labels=True)

    objective_set = ObjectiveSet(objective_list=[
        PeakNegativePower(component=g),
        ImportTariff(component=g, tariff_array=[0.1] * 24 + [0.2] * 24, expansion_periods=expansion_periods)
    ])

    start = time.time()

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=objective_set
    )

    optimiser.optimise()

    end = time.time()
    print('Total nodes: ', system.number_of_nodes())
    print('Time taken to construct echo optimiser and optimise: ', end-start)


def test_many_node_system_with_path_tracing():

    ## Set params

    expansion_periods = 1
    time_periods = 48
    interval_duration = 30  # min

    max_demand = 6
    min_demand = 0

    max_gen = -10
    min_gen = 0

    ###### Create graph

    num_gen = 4
    num_loads = 4
    num_storage = 30
    num_tellegen_nodes = 10
    tellegen_node_set = set(range(num_tellegen_nodes))

    system = OptimisationGraph()

    ###### Create graph
    system = OptimisationGraph()

    # Generate a random tree using all the tellegen nodes
    rand_tree = nx.random_tree(num_tellegen_nodes)

    node_name_map = {}  #

    # Create echo nodes and edges for tellegen nodes
    for node in rand_tree.nodes:
        n = ElectricalTellegenNode()
        node_name_map[str(node)] = n
        system.add_node(n)

    for edge in rand_tree.edges:
        n1 = edge[0]
        n2 = edge[1]
        node1 = node_name_map[str(n1)]
        node2 = node_name_map[str(n2)]
        system.connect_two_nodes_create_edges_create_ports(node1, node2)

    # Connect loads to random nodes
    for i in range(num_loads):
        # Pick a random node to connect the load to
        x = random.sample(tellegen_node_set, 1)
        sel_node = node_name_map[str(x[0])]

        # Create load node with random demand profile
        load = ElectricalNode()
        lp = ElectricalDemand()
        lp.add_demand_profile_from_array(np.random.randint(min_demand, max_demand, time_periods), expansion_periods)
        name = 'load_' + str(i)
        node_name_map[name] = load
        load.ports[name] = lp
        system.add_node_obj(load)
        system.connect_port_to_node_create_edges_create_port(lp, sel_node)

    # Connect generators to random nodes
    for i in range(num_gen):
        # Pick a random node to connect the generator to
        x = random.sample(tellegen_node_set, 1)
        sel_node = node_name_map[str(x[0])]

        # Create generation node with random generation profile
        gen = ElectricalNode()
        gp = ElectricalGeneration()
        gp.curtailable = False
        gp.add_generation_profile_from_array(np.random.randint(max_gen, min_gen, time_periods), expansion_periods)
        name = 'gen_' + str(i)
        node_name_map[name] = gen
        gen.ports[name] = gp
        system.add_node_obj(gen)
        system.connect_port_to_node_create_edges_create_port(gp, sel_node)

    # Connect storage to random nodes
    for i in range(num_storage):
        # Pick a random node to connect the storage to
        x = random.sample(tellegen_node_set, 1)
        sel_node = node_name_map[str(x[0])]

        # Create storage node
        bess = ElectricalNode()
        b1 = ElectricalStorage(max_capacity=48,
                               depth_of_discharge_limit=0,
                               charging_power_limit=5.0,
                               discharging_power_limit=-5.0,
                               charging_efficiency=1,
                               discharging_efficiency=1,
                               initial_state_of_charge=48.0)
        name = 'bess_' + str(i)
        node_name_map[name] = bess
        bess.ports[name] = b1
        system.add_node_obj(bess)
        system.connect_port_to_node_create_edges_create_port(b1, sel_node)

    # To ensure we can always meet reliability, add a grid node, connect it to a random tellegen node
    x = random.sample(tellegen_node_set, 1)
    sel_node = node_name_map[str(x[0])]

    grid = ElectricalNode()
    g = ElectricalPort()
    grid.ports['grid'] = g
    node_name_map['grid'] = grid
    system.add_node_obj(grid)
    system.connect_port_to_node_create_edges_create_port(g, sel_node)

    nx.draw(system, with_labels=True)

    #Generate list of source/sink nodes

    sources = []
    sinks = []
    for k, v in node_name_map.items():
        if ('load' in k) or ('sto' in k) or ('grid' in k):
            sinks.append(v)
        if ('gen' in k) or ('sto' in k) or ('grid' in k):
            sources.append(v)

    system.create_path_objects(sources=sources, sinks=sinks)

    start = time.time()

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=None
    )

    optimiser.optimise()

    end = time.time()
    print('Total nodes: ', system.number_of_nodes())
    print('Total paths: ', len(system.paths))
    print('Time taken to construct echo optimiser and optimise: ', end-start)

