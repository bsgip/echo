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

        # Initialise node variables/params and add node constraints
        for _, node_obj in self.ES.node_obj.items():
            node_obj.verify_node()
            node_obj.initialise_node(self.model)
            for _, port_obj in node_obj.ports.items():
                port_obj.verify_port()
                port_obj.initialise_port(self.model)

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

            def path_flow_rule(model, p, t):
                a = 0
                for _, path in self.ES.path_obj.items():
                    if path.vertices[0] is current_node:
                        a += getattr(model, path.flow_value)[p, t]
                    if path.vertices[-1] is current_node:
                        a -= getattr(model, path.flow_value)[p, t]
                b = getattr(model, current_port.port_name)[p, t]
                return a == b*-1

            def import_paths_rule_one(model, p, t):
                a = 0
                for _, path in self.ES.path_obj.items():
                    if path.vertices[-1] is current_node:
                        a += getattr(model, path.flow_value)[p, t]
                return a <= getattr(model, current_node.inflow)[p, t] * self.model.bigM

            def import_paths_rule_two(model, p, t):
                a = 0
                for _, path in self.ES.path_obj.items():
                    if path.vertices[-1] is current_node:
                        a += getattr(model, path.flow_value)[p, t]
                return getattr(model, current_node.inflow)[p, t] <= a * self.model.bigM

            def export_paths_rule_one(model, p, t):
                a = 0
                for _, path in self.ES.path_obj.items():
                    if path.vertices[0] is current_node:
                        a += getattr(model, path.flow_value)[p, t]
                return a <= getattr(model, current_node.outflow)[p, t] * self.model.bigM

            def export_paths_rule_two(model, p, t):
                a = 0
                for _, path in self.ES.path_obj.items():
                    if path.vertices[0] is current_node:
                        a += getattr(model, path.flow_value)[p, t]
                return getattr(model, current_node.outflow)[p, t] <= a * self.model.bigM

            def no_flow_through_rule(model, p, t):
                return getattr(model, current_node.inflow)[p, t] + getattr(model, current_node.outflow)[p, t] <= 1

            for current_port, current_node in self.ES.sources_or_sinks.items():
                con_name = 'path_flow_con_' + current_node.node_name
                setattr(self.model, con_name, en.Constraint(self.model.Expansion, self.model.Time, rule=path_flow_rule))

                current_node.inflow = 'inflow_' + current_node.node_name
                setattr(self.model, current_node.inflow, en.Var(self.model.Expansion, self.model.Time, initialize=0,
                                                                domain=en.Binary))

                current_node.outflow = 'outflow_' + current_node.node_name
                setattr(self.model, current_node.outflow, en.Var(self.model.Expansion, self.model.Time, initialize=0,
                                                                domain=en.Binary))

                con_name = 'import_path_con_one_' + current_node.node_name
                setattr(self.model, con_name, en.Constraint(self.model.Expansion, self.model.Time, rule=import_paths_rule_one))

                con_name = 'import_path_con_two_' + current_node.node_name
                setattr(self.model, con_name, en.Constraint(self.model.Expansion, self.model.Time, rule=import_paths_rule_two))

                con_name = 'export_path_con_one_' + current_node.node_name
                setattr(self.model, con_name, en.Constraint(self.model.Expansion, self.model.Time, rule=export_paths_rule_one))

                con_name = 'export_path_con_two_' + current_node.node_name
                setattr(self.model, con_name, en.Constraint(self.model.Expansion, self.model.Time, rule=export_paths_rule_two))

                con_name = 'non_tellegen_node_con_' + current_node.node_name
                setattr(self.model, con_name,
                        en.Constraint(self.model.Expansion, self.model.Time, rule=no_flow_through_rule))

    def build_objective(self):
        self.objective = 0

        for _, node_obj in self.ES.node_obj.items():
            for _, port_obj in node_obj.ports.items():
                self.objective += port_obj.add_objective(self.model)

        for _, edge_obj in self.ES.edge_obj.items():
            self.objective += edge_obj.add_objective(self.model)

        for _, path_obj in self.ES.path_obj.items():
            self.objective += path_obj.add_objective(self.model)

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
