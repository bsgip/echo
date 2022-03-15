import random
import time as time_

import numpy as np
import pandas as pd
from echo_models import *
from echo_optimiser import EchoOptimiser
from objectives import *
import networkx as nx
import matplotlib.pyplot as plt

import os

SOLVER = os.environ.get('OPTIMISER_ENGINE', 'cplex')
SOLVER_EXECUTABLE = None

N_INTERVALS = 48

def many_node_system_no_objective(num_gen, num_loads, num_storage, num_tellegen_nodes, objective):

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

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=objective
    )

    optimiser.optimise()
    return optimiser


incr = np.logspace(0, 3, 4)
df = pd.DataFrame(columns=['Num load','Num gen','Num bess','Num TN', 'User time', 'Time', 'Nvar', 'Ncon'], index=[])
index = 0
for num_gen in incr:
    for num_load in incr:
        for num_bess in incr:
            num_tn = 5
            t = many_node_system_no_objective(int(num_gen), int(num_load), int(num_bess), num_tn, None)
            df.loc[index] = pd.Series({'Num load': num_load,'Num gen': num_gen,'Num bess': num_bess,'Num TN': num_tn,
                                       'User time': t.opt_status['User time'], 'Time': t.opt_status['Time'],
                                       'Nvar': t.model.nvariables(), 'Ncon': t.model.nconstraints()})
            index += 1
