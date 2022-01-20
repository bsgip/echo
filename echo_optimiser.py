from pyomo.opt import SolverFactory
import pyomo.environ as en
import pyomo.network
import os
import numpy as np
from configuration import Units, Flows, FlowConstraint, OptimisationType, NodeRule, TransformRule, ExpansionType
from constants import minutes_per_hour
from echo_models import ConfigurationError, Path
import pandas as pd


class EchoOptimiser(object):

    def __init__(self, interval_duration, number_of_intervals, number_of_expansion_intervals, ES):
        self.interval_duration = interval_duration  # The duration (in minutes) of each of the intervals being optimised over
        self.number_of_intervals = number_of_intervals
        self.number_of_expansion_intervals = number_of_expansion_intervals
        self.ES = ES

        # Configure the optimiser through setting appropriate environmental variables.
        self.optimiser_engine = os.environ.get('OPTIMISER_ENGINE')  # Default to ipopt since that is easiest to install
        self.optimiser_engine_executable = os.environ.get('OPTIMISER_ENGINE_EXECUTABLE')

        self.use_bool_vars = True

        # These values have been arbitrarily chosen
        # A better understanding of the sensitivity of these values may be advantageous
        self.bigM = 5000000
        self.smallM = 0.0001
        self.tariff_edge_pos = None
        self.tariff_edge_neg = None
        self.storage_var_value = None
        self.storage_soc_value = None
        self.var_names = list()

        self.build_model()
        self.apply_constraints()
        self.build_objective()
        self.optimise()

    def build_model(self):
        # Set up the Pyomo model
        self.model = en.ConcreteModel()

        #### Bias Values ####

        # A small fudge factor for reducing the size of the solution set and
        # achieving a unique optimisation solution
        self.model.smallM = en.Param(initialize=self.smallM)
        # A bigM value for integer optimisation
        self.model.bigM = en.Param(initialize=self.bigM)

        # We use RangeSet to create a index for each of the time
        # periods that we will optimise within.
        self.model.Time = en.RangeSet(0, self.number_of_intervals - 1)
        # Create index for expansion periods
        if self.number_of_expansion_intervals == 0:
            self.model.Expansion = en.RangeSet(0, 0)
        else:
            self.model.Expansion = en.RangeSet(0, self.number_of_expansion_intervals - 1)

        self.model.dr = 'discount_rates'
        setattr(self.model, self.model.dr,
                en.Param(self.model.Expansion, initialize=self.ES.discount_factors))

        # Add expansion objects
        self.ES.add_asset_expansions(self.ES.expansion_periods)
        self.ES.add_capacity_expansions()

        # Initialise port variables/params and add port constraints
        for _, port_obj in self.ES.port_obj.items():
            port_obj.verify_port()
            port_obj.initialise_port(self.model)

        # Initialise node variables/params and add node constraints
        for _, node_obj in self.ES.node_obj.items():
            node_obj.verify_node()
            node_obj.initialise_node(self.model)

        # Initialise edge variables/params and add edge constraints
        for _, edge_obj in self.ES.edge_obj.items():
            edge_obj.verify_edge()
            edge_obj.initialise_edge(self.model)

        # Initialise path variables/params
        for _, path_obj in self.ES.path_obj.items():
            path_obj.verify_path()
            path_obj.initialise_path(self.model)

    def apply_constraints(self):
        self.apply_node_constraints()
        self.apply_path_constraints()
        self.apply_expansion_constraints()

    def apply_node_constraints(self):

        def reliability(model, p, t):  # Tellegen node rule
            a = 0
            for _, port in node_ports.items():
                b = getattr(self.model, port.port_name)
                a += b[p, t]
            return a == 0

        def transform(model, p, t):  # Generic transformation node
            lhs = 0
            rhs = current_transform.rhs
            num_terms = len(current_transform.weight)
            for i in range(0, num_terms):
                transform_rule = current_transform.rule[i]
                weight = current_transform.weight[i]
                var = current_transform.lhs[i]
                if transform_rule is TransformRule.Both:
                    lhs += getattr(self.model, var.port_name)[p, t] * weight
                if transform_rule is TransformRule.NegativeComponent:
                    lhs += getattr(self.model, var.negative_port_component)[p, t] * weight
                if transform_rule is TransformRule.PositiveComponent:
                    lhs += getattr(self.model, var.positive_port_component)[p, t] * weight
            return lhs == rhs

        for _, obj in self.ES.node_obj.items():
            if obj.node_rule == NodeRule.Transform:
                for _, current_transform in obj.transformations.items():
                    con_name = 'transformation_con_' + current_transform.transform_name
                    setattr(self.model, con_name, en.Constraint(self.model.Expansion, self.model.Time, rule=transform))
            if obj.node_rule == NodeRule.Tellegen:
                node_ports = obj.ports
                con_name = 'reliability_con_' + obj.node_name
                setattr(self.model, con_name, en.Constraint(self.model.Expansion, self.model.Time, rule=reliability))

    def apply_path_constraints(self):

        if self.ES.path_obj:
            def sum_sources_to_sink(model, p, t):  # Sum of paths to sink from all sources must equal sink
                a = 0
                for path in paths_to_sink:
                    a += getattr(model, path.flow_value)[p, t]
                b = getattr(model, path.end_port.positive_port_component)[p, t]
                return a == b

            for _, sink in self.ES.sinks.items():
                paths_to_sink = []
                for l in self.ES.all_paths:
                    if l[-1] is sink:
                        # Get path object
                        p = self.ES.path_obj[tuple(l)]
                        paths_to_sink.append(p)
                con_name = 'sum_paths_to_sink_con_' + sink.node_name
                setattr(self.model, con_name, en.Constraint(self.model.Expansion, self.model.Time, rule=sum_sources_to_sink))

            def sum_paths_from_source(model, p, t):  # Sum of paths from source must equal source
                a = 0
                for path in paths_from_source:
                    a += getattr(model, path.flow_value)[p, t]
                b = getattr(model, path.start_port.negative_port_component)[p, t]
                return a*-1 == b

            for _, source in self.ES.sources.items():
                paths_from_source = []
                for l in self.ES.all_paths:
                    if l[0] is source:
                        p = self.ES.path_obj[tuple(l)]
                        paths_from_source.append(p)
                con_name = 'sum_paths_from_source_con_' + source.node_name
                setattr(self.model, con_name, en.Constraint(self.model.Expansion, self.model.Time, rule=sum_paths_from_source))

    def apply_expansion_constraints(self):

        def storage_exp_rule(model, expansion_interval):
            a = 0
            for _, node in self.ES.storage_expansion_obj.items():
                a += getattr(model, node.installed)[expansion_interval]
            return a <= self.ES.global_storage_exp_con

        def gen_exp_rule(model, expansion_interval):
            a = 0
            for _, node in self.ES.gen_expansion_obj.items():
                a += getattr(model, node.installed)[expansion_interval]
            return a <= self.ES.global_generator_exp_con

        def capacity_exp_rule(model, expansion_interval):
            a = 0
            for _, obj in self.ES.capacity_exp_obj.items():
                a += getattr(model, obj.capacity_added)[expansion_interval]
            return a <= self.ES.global_capacity_exp_con

        def combined_exp_rule(model, expansion_interval):
            a = 0
            for _, obj in self.ES.capacity_exp_obj.items():
                a += getattr(model, obj.capacity_added)[expansion_interval]
            for _, node in self.ES.storage_expansion_obj.items():
                a += getattr(model, node.installed)[expansion_interval]
            for _, node in self.ES.gen_expansion_obj.items():
                a += getattr(model, node.installed)[expansion_interval]
            return a <= self.ES.global_combined_asset_capacity_expansion_con

        if self.ES.storage_expansion_obj:
            con_name = 'global_storage_exp_con'
            setattr(self.model, con_name, en.Constraint(self.model.Expansion, rule=storage_exp_rule))
        if self.ES.gen_expansion_obj:
            con_name = 'global_gen_exp_con'
            setattr(self.model, con_name, en.Constraint(self.model.Expansion, rule=gen_exp_rule))
        if self.ES.capacity_exp_obj:
            con_name = 'global_cap_exp_con'
            setattr(self.model, con_name, en.Constraint(self.model.Expansion, rule=capacity_exp_rule))
        if (self.ES.storage_expansion_obj or self.ES.gen_expansion_obj) and self.ES.capacity_exp_obj:
            con_name = 'global_combined_asset_capacity_expansion_con'
            setattr(self.model, con_name, en.Constraint(self.model.Expansion, rule=combined_exp_rule))

    def build_objective(self):
        self.objective = 0
        for _, obj in self.ES.port_obj.items():
            self.objective += obj.add_objective(self.model)

        for _, obj in self.ES.edge_obj.items():
            self.objective += obj.add_objective(self.model)

        for _, obj in self.ES.path_obj.items():
            self.objective += obj.add_objective(self.model)

    def optimise(self):
        def objective_function(model):
            return self.objective

        self.model.total_cost = en.Objective(rule=objective_function, sense=en.minimize)

        # Set the path to the solver
        if self.optimiser_engine == 'cplex':
            opt = SolverFactory(self.optimiser_engine, executable=self.optimiser_engine_executable)
        else:
            opt = SolverFactory(self.optimiser_engine)

        # Solve the optimisation
        opt.solve(self.model, tee=True, symbolic_solver_labels=True)

    def values(self, variable_name, expansion):
        """ Returns the value of a single specified variable during a single specified expansion period."""

        var_obj = getattr(self.model, variable_name)
        if var_obj.dim() == 2:
            output = np.zeros(self.number_of_intervals)
            max_planning_period = 0
            for index in var_obj:
                if index[0] == expansion:
                    output[index[1]] = var_obj[index].value
                max_planning_period = max(max_planning_period, index[0])
            if expansion > max_planning_period:
                raise ConfigurationError('Expansion period is not in range.')
            return output
        else:
            if var_obj.is_indexed():
                if type(var_obj[expansion]) is int:  # Param
                    return var_obj[expansion]
                else:  # Var
                    return var_obj[expansion].value
            else:
                return var_obj.value

    def node_values(self, node_obj, expansion_period):
        """ Returns all values of all ports in a specified node for a single specified expansion period."""

        outputs = {}
        for name, var_obj in node_obj.ports.items():
            outputs[name] = self.values(var_obj.port_name, expansion_period)
        return outputs

    def node_life_cycle(self, node_obj, total_expansion_periods):
        """ Returns life-cycle variables (installed, retired, replaced, capacity) for all ports in the specified node,
         for all expansion periods. """

        output = {'expansion period': [], 'installed': [], 'retired': [], 'replaced': [], 'remaining life': []}
        rows = []
        for name, var in node_obj.ports.items():
            for j in range(0, total_expansion_periods):
                rows.append(name[0:len(name) - (len(name) - 13)])
                output['expansion period'].append(j)
                output['installed'].append(self.values(var.installed, j))
                output['retired'].append(self.values(var.retire, j))
                output['replaced'].append(self.values(var.replace, j))
                output['remaining life'].append(self.values(var.lifetime_remaining, j))
        df = pd.DataFrame(output, index=rows)
        return df

    def port_life_cycle(self, var, total_expansion_periods):
        """ Returns life-cycle variables (installed, retired, replaced, remaining lifetime) for a specified port
        over all expansion periods."""

        output = {'expansion period': [], 'installed': [], 'retired': [], 'replaced': [], 'remaining life': []}
        for j in range(0, total_expansion_periods):
            output['expansion period'].append(j)
            output['installed'].append(self.values(var.installed, j))
            output['retired'].append(self.values(var.retire, j))
            output['replaced'].append(self.values(var.replace, j))
            output['remaining life'].append(self.values(var.lifetime_remaining, j))
        df = pd.DataFrame(output)
        return df

    def expansion_life_cycle(self, total_expansion_periods):
        """ Returns life-cycle variables (installed, capacity, active, retired, replaced, lifetime remaining) for
         all expansion objects in the model, over all expansion periods. """

        if not self.ES.asset_expansion_obj:
            return print('No asset expansion objects.')
        else:
            output = {'exp': [], 'installed': [], 'active': [], 'retired': [], 'replaced': [], 'remaining life': []}
            rows = []
            for _, node in self.ES.asset_expansion_obj.items():
                for name, var in node.ports.items():
                    for j in range(0, total_expansion_periods):
                        rows.append(name[0:len(name) - (len(name) - 13)])
                        output['exp'].append(j)
                        output['installed'].append(self.values(var.installed, j))
                        output['active'].append(self.values(var.active, j))
                        output['retired'].append(self.values(var.retire, j))
                        output['replaced'].append(self.values(var.replace, j))
                        output['remaining life'].append(self.values(var.lifetime_remaining, j))
            df = pd.DataFrame(output, index=rows)
            return df

    def edge_life_cycle(self, edge, total_expansion_periods):
        """ Returns life-cycle variables (initial capacity, current capacity, added capacity) for a specified edge object
        over all expansion periods. """
        if total_expansion_periods == 0:
            raise ConfigurationError('Enter total expansion periods not a single expansion period.')
        output = {'initial_edge_capacity': [], 'current_edge_capacity': [], 'capacity_added_value': []}
        output['initial_edge_capacity'].append(edge.initial_edge_capacity)
        for j in range(0, total_expansion_periods):
            output['current_edge_capacity'].append(self.values(edge.current_cap, j))
            if edge.expansion_planning is True:
                output['capacity_added_value'].append(self.values(edge.cap_add_value, j))
        return output

    def get_expansion_ports(self):
        """ Returns all expansion node ports in model."""

        output = []
        for _, exp_node in self.ES.storage_expansion_obj.items():
            for _, exp_port in exp_node.ports.items():
                output.append(exp_port)
        for _, exp_node in self.ES.gen_expansion_obj.items():
            for _, exp_port in exp_node.ports.items():
                output.append(exp_port)
        return output

    def test_value_functions(self, node, total_expansion_periods):
        """ Tests all value functions for a specified node."""

        print('Node values')
        print(self.node_values(node, 0))
        print('\nNode life cycle')
        print(self.node_life_cycle(node, total_expansion_periods))
        p = list(node.ports.values())[0]
        p_name = list(node.ports.keys())[0]
        print('\nPort (', p_name, ') values')
        print(self.values(p.port_name, 0))
        print('\nPort (', p_name, ') life cycle')
        print(self.port_life_cycle(p, total_expansion_periods))
        print('\nGet expansion ports')
        print(self.get_expansion_ports())
        print('\nExpansion life cycle')
        print(self.expansion_life_cycle(total_expansion_periods))

    def total_import(self, var, expansion_period):
        return sum(self.values(var.positive_port_component, expansion_period))

    def total_export(self, var, expansion_period):
        return sum(self.values(var.negative_port_component, expansion_period))

    def get_expansions_off_node(self, node):
        """ Returns ports that are parts of expansion nodes connected to specified node."""

        output = []
        for exp_p_name in node.exp_port_names:
            exp_p = node.ports[exp_p_name]
            # Find edge
            e = self.ES.lookup_edge_from_port(exp_p)
            p1 = e.vertices[0]
            p2 = e.vertices[1]
            if exp_p == p1:
                output.append(p2)
            else:
                output.append(p1)

        return output

    def check_pos_neg_port(self, port, expansion_period):
        return self.values(port.positive_port_component, expansion_period) * \
               self.values(port.negative_port_component, expansion_period)




