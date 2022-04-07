from pyomo.opt import SolverFactory
import pyomo.environ as en
import pyomo.network
import os
import numpy as np
from echo.configuration import Units, Flows, FlowConstraint, OptimisationType, NodeRule, TransformRule, ExpansionType
from echo.constants import minutes_per_hour
from echo.echo_models import ConfigurationError, Path
import pandas as pd


class EchoOptimiser(object):

    def __init__(self, interval_duration, number_of_intervals, number_of_expansion_intervals, discount_rate, ES, objective_set, optimiser_engine=None):
        self.interval_duration = interval_duration  # The duration (in minutes) of each of the intervals being optimised over
        self.number_of_intervals = number_of_intervals
        self.number_of_expansion_intervals = number_of_expansion_intervals
        self.ES = ES
        self.objective_set = objective_set

        # Configure the optimiser through setting appropriate environmental variables.
        if optimiser_engine:
            self.optimiser_engine = optimiser_engine
        else:
            self.optimiser_engine = 'cplex' if not os.environ.get('OPTIMISER_ENGINE') else os.environ.get('OPTIMISER_ENGINE') # Default to cplex, as we seem to want quadratic costs
        self.optimiser_engine_executable = os.environ.get('OPTIMISER_ENGINE_EXECUTABLE')

        # These values have been arbitrarily chosen
        # A better understanding of the sensitivity of these values may be advantageous
        self.bigM = 5000000
        self.smallM = 0.0001
        self.discount_rate = discount_rate

        self.build_model()
        self.apply_constraints()
        self.build_objective()

    def build_model(self):
        # Set up the Pyomo model
        self.model = en.ConcreteModel()
        self.model.interval_duration = self.interval_duration
        self.model.number_of_intervals = self.number_of_intervals
        self.model.paths = self.ES.paths #Todo better way of making all path variables available for constructing objectives

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

        # Setup discounting
        dr = {}
        for ep in range(0, self.number_of_expansion_intervals):
            dr[ep] = 1 / ((1 + self.discount_rate) ** ep)

        self.model.dr = 'discount_rates'
        setattr(self.model, self.model.dr, en.Param(self.model.Expansion, initialize=dr))

        # Initialise node variables/params and add node constraints
        for _, node_obj in self.ES.node_obj.items():
            for _, port_obj in node_obj.ports.items():
                port_obj.verify_port()
                port_obj.initialise_port(self.model)
            node_obj.verify_node()
            node_obj.initialise_node(self.model)

        # Initialise edge variables/params and add edge constraints
        for _, edge_obj in self.ES.edge_obj.items():
            edge_obj.verify_edge()
            edge_obj.initialise_edge(self.model)

        # Initialise paths
        for _, path in self.ES.paths.items():
            path.initialise_path(self.model)

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
            def unpack_transform(x):
                expr = 0
                for term in x:
                    transform_rule = term['rule']
                    weight = term['weight']
                    var = term['var']
                    if transform_rule is TransformRule.Both:
                        expr += getattr(self.model, var.port_name)[p, t] * weight
                    if transform_rule is TransformRule.NegativeComponent:
                        expr += getattr(self.model, var.neg)[p, t] * weight
                    if transform_rule is TransformRule.PositiveComponent:
                        expr += getattr(self.model, var.pos)[p, t] * weight
                return expr
            rhs = unpack_transform(current_transform.rhs)
            lhs = unpack_transform(current_transform.lhs)
            return lhs == rhs

        for _, obj in self.ES.node_obj.items():
            if obj.node_rule == NodeRule.Transform:
                for _, current_transform in obj.transformations.items():
                    current_transform.initialise_transform(self.model)
                    con_name = 'transformation_con_' + current_transform.transform_name
                    setattr(self.model, con_name, en.Constraint(self.model.Expansion, self.model.Time, rule=transform))
            if obj.node_rule == NodeRule.Tellegen:
                node_ports = obj.ports
                con_name = 'reliability_con_' + obj.node_name
                setattr(self.model, con_name, en.Constraint(self.model.Expansion, self.model.Time, rule=reliability))

    def apply_path_constraints(self):

        if self.ES.paths:

            def path_flow_rule(model, p, t):
                a = 0
                # Iterate through all paths in the model
                for _, path in self.ES.paths.items():
                    # If the path starts at the current node
                    if path.vertices[0] is current_node:
                        # Add the flow value
                        a += getattr(model, path.flow_value)[p, t]
                    # If the path ends at the current node
                    if path.vertices[-1] is current_node:
                        # Subtract the flow value
                        a -= getattr(model, path.flow_value)[p, t]
                # Enforce that flows out minus flows in = -1 * port
                return a == getattr(model, current_port.port_name)[p, t] * -1

            def only_inflow_or_outflow_one(model, p, t):
                a = 0
                for _, path in self.ES.paths.items():
                    if path.vertices[-1] is current_node:
                        a += getattr(model, path.flow_value)[p, t]
                return a <= getattr(model, current_node.inflow)[p, t] * self.model.bigM

            def only_inflow_or_outflow_two(model, p, t):
                a = 0
                for _, path in self.ES.paths.items():
                    if path.vertices[0] is current_node:
                        a += getattr(model, path.flow_value)[p, t]
                return a <= (1 - getattr(model, current_node.inflow)[p, t]) * self.model.bigM

            sources_and_sinks = self.ES.get_sources_and_sinks()  # returns concatenated list of all source/sink nodes
            for current_node in sources_and_sinks:  # Iterate through the source/sink nodes
                for k, v in self.ES.paths.items():  # Iterate through all paths
                    if current_node is k[0]:  # If we find a path where the current node is the first node on that path
                        current_port = v.edge_ports[0][0]  # Pick up the first port on the path
                    elif current_node is k[-1]:  # If we find a path where the current node is the last node on that path
                        current_port = v.edge_ports[-1][-1]  # Pick up the last port on the path
                assert current_port in current_node.ports.values()

                setattr(self.model, f"path_flow_con1_{current_node.node_name}",
                        en.Constraint(self.model.Expansion, self.model.Time, rule=path_flow_rule))

                # Create an indicator var for when there are flows into a node
                current_node.inflow = 'inflow_' + current_node.node_name
                setattr(self.model, current_node.inflow, en.Var(self.model.Expansion, self.model.Time, initialize=0,
                                                                domain=en.Binary))

                setattr(self.model, f"path_flow_con2_{current_node.node_name}",
                        en.Constraint(self.model.Expansion, self.model.Time, rule=only_inflow_or_outflow_one))

                setattr(self.model, f"path_flow_con3_{current_node.node_name}",
                        en.Constraint(self.model.Expansion, self.model.Time, rule=only_inflow_or_outflow_two))

    def build_objective(self):
        self.objective = 0
        # Add objectives defined in the objective set
        if hasattr(self, 'objective_set'):
            if self.objective_set is not None:
                self.objective_set.initialise_objective(self.model)
                self.objective_set.set_objective(self.model, self)

        # Add any other costs that are defined on graph nodes/ports
        for _, node_obj in self.ES.node_obj.items():
            for _, port_obj in node_obj.ports.items():
                self.objective += port_obj.add_objective(self.model)

    def optimise(self, tee=False):
        def objective_function(model):
            return self.objective

        self.model.total_cost = en.Objective(rule=objective_function, sense=en.minimize)

        # Set the path to the solver
        if (self.optimiser_engine == 'cplex') and self.optimiser_engine_executable:
            opt = SolverFactory(self.optimiser_engine, executable=self.optimiser_engine_executable)
        else:
            opt = SolverFactory(self.optimiser_engine)

        # Solve the optimisation
        results = opt.solve(self.model, tee=False, symbolic_solver_labels=True)
        self.opt_status = results['Solver'][0]

    def values(self, variable_name, expansion):
        """ Returns the value of a single specified variable during a single specified expansion period."""

        var_obj = getattr(self.model, variable_name)
        if var_obj.dim() == 2:
            output = np.zeros(self.number_of_intervals)
            max_planning_period = 0
            for index in var_obj:
                if index[0] == expansion:
                    try:
                        output[index[1]] = var_obj[index].value
                    except AttributeError:
                        output[index[1]] = var_obj[index]
                max_planning_period = max(max_planning_period, index[0])
            if expansion > max_planning_period:
                raise ConfigurationError('Expansion period is not in range.')
            return output
        else:
            if var_obj.is_indexed():
                if type(var_obj[expansion]) is int or type(var_obj[expansion]) is float:  # Param
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

    def get_objective_value(self, objective_obj, expansion_period: int):
        return objective_obj.objective_val(optimiser=self, expansion_period=expansion_period)
