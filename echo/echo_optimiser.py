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

    def __init__(self, interval_duration, number_of_intervals, number_of_expansion_intervals, discount_rate, ES,
                 objective_set, optimiser_engine=None):
        self.interval_duration = interval_duration  # The duration (in minutes) of each of the intervals being optimised over
        self.number_of_intervals = number_of_intervals
        self.number_of_expansion_intervals = number_of_expansion_intervals
        self.ES = ES
        self.objective_set = objective_set

        # Configure the optimiser through setting appropriate environmental variables.
        if optimiser_engine:
            self.optimiser_engine = optimiser_engine
        else:
            self.optimiser_engine = 'cplex' if not os.environ.get('OPTIMISER_ENGINE') else os.environ.get(
                'OPTIMISER_ENGINE')  # Default to cplex, as we seem to want quadratic costs
        self.optimiser_engine_executable = os.environ.get('OPTIMISER_ENGINE_EXECUTABLE')

        # These values have been arbitrarily chosen
        # A better understanding of the sensitivity of these values may be advantageous
        self.bigM = 5000000
        self.smallM = 0.0001
        self.discount_rate = discount_rate

        self.build_model()
        self.apply_constraints()
        self.build_objective()

    def _validate_network_graph(self):
        """
        Validates that a pyomo model can be built from the provided network graph. Checks for:
        - name consistency between objects (eg node.node_name) and graph nodes
        - others...
        """
        for node_name, node_obj in self.ES.node_obj.items():
            assert node_obj.node_name == node_name, \
                'Node {} name has been updated after being added to the network graph.'.format(node_name)

    def build_model(self):
        # Set up the Pyomo model
        self.model = en.ConcreteModel()
        self.model.interval_duration = self.interval_duration
        self.model.number_of_intervals = self.number_of_intervals
        self.model.paths = self.ES.paths  # Todo better way of making all path variables available for constructing objectives

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
        self._apply_node_constraints()
        self._apply_path_constraints()

    def _apply_node_constraints(self):
        for _, obj in self.ES.node_obj.items():
            obj.apply_node_constraints(self.model)

    def _apply_path_constraints(self):

        if self.ES.paths:

            def path_flow_rule(model, p, t):
                a = 0
                # Iterate through all paths in the model
                for _, path in self.ES.paths.items():
                    # If the path starts at the current node
                    if path.vertices[0] is current_node_name:
                        # Add the flow value
                        a += getattr(model, path.flow_value)[p, t]
                    # If the path ends at the current node
                    if path.vertices[-1] is current_node_name:
                        # Subtract the flow value
                        a -= getattr(model, path.flow_value)[p, t]
                # Enforce that flows out minus flows in = -1 * port
                return a == getattr(model, current_port.port_name)[p, t] * -1

            def only_inflow_or_outflow_one(model, p, t):
                a = 0
                for _, path in self.ES.paths.items():
                    if path.vertices[-1] is current_node_name:
                        a += getattr(model, path.flow_value)[p, t]
                return a <= getattr(model, current_node_obj.inflow)[p, t] * self.model.bigM

            def only_inflow_or_outflow_two(model, p, t):
                a = 0
                for _, path in self.ES.paths.items():
                    if path.vertices[0] is current_node_name:
                        a += getattr(model, path.flow_value)[p, t]
                return a <= (1 - getattr(model, current_node_obj.inflow)[p, t]) * self.model.bigM

            sources_and_sinks = self.ES.get_sources_and_sinks()  # returns concatenated list of all source/sink nodes
            for current_node_name in sources_and_sinks:  # Iterate through the source/sink nodes
                # get the node obj
                current_node_obj = self.ES.node_obj[current_node_name]
                for path_vertices, path_obj in self.ES.paths.items():  # Iterate through all paths
                    if current_node_name is path_vertices[
                        0]:  # If we find a path where the current node is the first node on that path
                        current_port = path_obj.edge_ports[0][0]  # Pick up the first port on the path
                    elif current_node_name is path_vertices[
                        -1]:  # If we find a path where the current node is the last node on that path
                        current_port = path_obj.edge_ports[-1][-1]  # Pick up the last port on the path

                setattr(self.model, f"path_flow_con1_{current_node_name}",
                        en.Constraint(self.model.Expansion, self.model.Time, rule=path_flow_rule))

                # Create an indicator var for when there are flows into a node
                current_node_obj.inflow = f"inflow_{current_node_name}"
                setattr(self.model, current_node_obj.inflow, en.Var(self.model.Expansion, self.model.Time, initialize=0,
                                                                    domain=en.Binary))

                setattr(self.model, f"path_flow_con2_{current_node_name}",
                        en.Constraint(self.model.Expansion, self.model.Time, rule=only_inflow_or_outflow_one))

                setattr(self.model, f"path_flow_con3_{current_node_name}",
                        en.Constraint(self.model.Expansion, self.model.Time, rule=only_inflow_or_outflow_two))

    def build_objective(self):
        self.objective = 0
        # Add objectives defined in the objective set
        if hasattr(self, 'objective_set'):
            if self.objective_set is not None:
                self.objective_set.initialise_objective(self.model)
                self.objective_set.set_objective(self.model, self)

        # Add any other costs that are defined on graph nodes/ports/paths
        for _, node_obj in self.ES.node_obj.items():
            for _, port_obj in node_obj.ports.items():
                self.objective += port_obj.add_objective(self.model)

        for _, path_obj in self.ES.paths.items():
            self.objective += path_obj.add_objective(self.model)

    def optimise(self, tee=False):
        def objective_function(model):
            return self.objective

        self.model.total_cost = en.Objective(rule=objective_function, sense=en.minimize)

        # Set the path to the solver
        if self.optimiser_engine_executable:
            opt = SolverFactory(self.optimiser_engine, executable=self.optimiser_engine_executable)
        else:
            opt = SolverFactory(self.optimiser_engine)

        # Solve the optimisation
        results = opt.solve(self.model, tee=tee, symbolic_solver_labels=True)
        self.opt_status = results['Solver'][0]

    def df(self):
        """
        Extract all vars from the solution as a dataframe
        """
        # todo extend this to do other nice things
        dct = {}

        for var_obj in self.model.component_objects(en.Var):
            if 'soc' in var_obj.name:
                dct[var_obj.name] = var_obj.extract_values()
            if 'port' in var_obj.name:
                dct[var_obj.name] = var_obj.extract_values()

        # Handle multiple indexes
        df = pd.DataFrame(dct)

        return df

    def values(self, variable_name, expansion=0):
        """ Returns the value of a single specified variable during a single specified expansion period."""

        var_obj = getattr(self.model, variable_name)
        if var_obj.dim() == 2:
            # the variable/param has two indices - we assume these are expansion and time
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
            # the variable/param doesn't have two indices
            if var_obj.is_indexed():
                # if it has one, then work out what that one is:
                output = np.zeros(len(var_obj))
                for i in var_obj:
                    output[i] = var_obj[i].value
                return output
            else:
                # if it has no index, we can directly return value
                return var_obj.value


    def node_values(self, node_obj, expansion_period=0):
        """ Returns all values of all ports in a specified node for a single specified expansion period."""

        outputs = {}
        for name, var_obj in node_obj.ports.items():
            outputs[name] = self.values(var_obj.port_name, expansion_period)
        return outputs

    def get_single_objective_total_value(self, objective_obj):
        assert self.objective_set is not None, 'No objectives defined for this optimiser.'
        return objective_obj.get_objective_total(optimiser=self)

    def get_total_objective_value(self):
        assert self.objective_set is not None, 'No objectives defined for this optimiser.'
        return en.value(self.objective)
