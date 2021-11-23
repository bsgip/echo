from pyomo.opt import SolverFactory
import pyomo.environ as en
import pyomo.network
import os
import numpy as np
from configuration import Units, Flows, FlowConstraint, OptimisationType, HubNodeRule
from constants import minutes_per_hour
from echo_models import FlexibleAsset, ElectricalStorage


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
        self.apply_expansion_constraints()
        self.build_objective()
        self.optimise()

    def factory_constraint_edge_builder(self, hub_edge_par, asset_edge_par):

        def constraint(model, expansion_interval, time_interval):
            return getattr(model, hub_edge_par)[expansion_interval, time_interval] + \
                   getattr(model, asset_edge_par)[expansion_interval, time_interval] == 0

        return constraint

    def add_asset(self, obj):
        # Constraints relevant to particular assets are added here as part of initialising the node
        obj.verify_node()
        obj.initialise_node(self.model)

    def build_model(self):
        # Set up the Pyomo model
        self.model = en.ConcreteModel()

        #### Bias Values ####

        # A small fudge factor for reducing the size of the solution set and
        # achieving a unique optimisation solution
        self.model.scale_func = en.Param(initialize=self.smallM)
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

        # Parameters and Variable Definitions for Assets
        for _, obj in self.ES.asset_obj.items():
            self.add_asset(obj)

        # Add Edges
        for _, edge_obj in self.ES.edge_obj.items():
            hub_port = edge_obj[0]
            asset_port = edge_obj[1]

            con_rule1 = self.factory_constraint_edge_builder(hub_port.node_name, asset_port.node_name)
            con_name = 'edge_con_' + hub_port.node_name + '_' + asset_port.node_name
            setattr(self.model, con_name, en.Constraint(self.model.Expansion, self.model.Time, rule=con_rule1))

    def apply_constraints(self):

        # Apply hub constraints
        for _, obj in self.ES.hub_obj.items():
            hub_vars = obj.nodes

            # Kirchoff flow constraint at each aggregation Hub
            def reliability(model, expansion_interval, time_interval):
                a = 0
                for _, hv in hub_vars.items():
                    b = getattr(self.model, hv.node_name)
                    a += b[expansion_interval, time_interval]
                return a == 0

            # Transformation constraint at each transformation Hu
            def loss(model, expansion_interval, time_interval):
                a = 0
                b = 0
                for _, hv in hub_vars.items():
                    p = getattr(self.model, hv.positive_node_component)
                    n = getattr(self.model, hv.negative_node_component)
                    a += p[expansion_interval, time_interval]
                    b += n[expansion_interval, time_interval]
                c = a + b
                return c == 0.95 * a  # e.g., 5% bi-directional loss

            # Apply correct hub constraint based on hub rule
            if obj.hub_rule == HubNodeRule.Tellegen:
                con_name = 'reliability_con_' + obj.hub_name
                setattr(self.model, con_name, en.Constraint(self.model.Expansion, self.model.Time, rule=reliability))
            if obj.hub_rule == HubNodeRule.Custom:
                con_name = 'loss_con_' + obj.hub_name
                setattr(self.model, con_name, en.Constraint(self.model.Expansion, self.model.Time, rule=loss))

    def apply_expansion_constraints(self):
        # Retrieve info on potential storage expansions
        storage_expansions = {}
        for _, obj in self.ES.asset_obj.items():
            if type(obj) == ElectricalStorage and obj.expansion_node is True:
                storage_expansions[obj.node_name] = obj

        def storage_exp_rule(model, expansion_interval):
            a = 0
            for _, storage_obj in storage_expansions.items():
                a += getattr(model, storage_obj.installed)[expansion_interval]
            return a <= 1

        con_name = 'storage_exp_con'
        setattr(self.model, con_name, en.Constraint(self.model.Expansion, rule=storage_exp_rule))

    def build_objective(self):
        self.objective = 0
        for _, obj in self.ES.asset_obj.items():
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
        opt.solve(self.model, tee=True)

    def values(self, variable_name, expansion):
        var_obj = getattr(self.model, variable_name)
        if var_obj.dim() == 2:
            output = np.zeros(self.number_of_intervals)
            for index in var_obj:
                if index[0] == expansion:
                    output[index[1]] = var_obj[index].value
            return output
        else:
            if var_obj.is_indexed():
                return var_obj[expansion].value
            else:
                return var_obj.value

    def value_test(self):
        outputs = []
        for var in self.var_names:
            outputs.append(self.values(var))
        return outputs
