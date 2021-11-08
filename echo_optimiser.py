from pyomo.opt import SolverFactory
import pyomo.environ as en
import pyomo.network
import os
import numpy as np
from configuration import Units, Flows, FlowConstraint, OptimisationType, HubNodeRule
from constants import minutes_per_hour
from echo_models import FlexibleAsset

class EchoOptimiser(object):

    def __init__(self, interval_duration, number_of_intervals, ES):
        self.interval_duration = interval_duration  # The duration (in minutes) of each of the intervals being optimised over
        self.number_of_intervals = number_of_intervals
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


    def factory_constraint_edge_builder(self, hub_edge_par, asset_edge_par):

        def constraint(model, time_interval):
            return getattr(model, hub_edge_par)[time_interval] + getattr(model, asset_edge_par)[time_interval] == 0

        return constraint

    def add_asset(self, obj):
        # Constraints relevant to particular assets are added here as part of initialising the node
        obj.verify_node()
        obj.initialise_node(self.model)

    def build_model(self):
        # Set up the Pyomo model
        self.model = en.ConcreteModel()

        # We use RangeSet to create a index for each of the time
        # periods that we will optimise within.
        self.model.Time = en.RangeSet(0, self.number_of_intervals - 1)

        # Parameters and Variable Definitions for Assets
        for _, obj in self.ES.asset_obj.items():
            self.add_asset(obj)

        # Add Edges
        for _, edge_obj in self.ES.edge_obj.items():
            #obj = edge_obj[2]

            #hub_port = FlexibleAsset()
            #hub_port.verify_node()
            #hub_port.initialise_node(self.model)

            hub_port = edge_obj[0]
            asset_port = edge_obj[1]
            # if asset_port.has_tariff:
            #     hub_port.has_tariff = True

            con_rule1 = self.factory_constraint_edge_builder(hub_port.node_name, asset_port.node_name)
            con_name = 'edge_con_' + hub_port.node_name + '_' + asset_port.node_name
            setattr(self.model, con_name, en.Constraint(self.model.Time, rule=con_rule1))


        #### Bias Values ####

        # A small fudge factor for reducing the size of the solution set and
        # achieving a unique optimisation solution
        self.model.scale_func = en.Param(initialize=self.smallM)
        # A bigM value for integer optimisation
        self.model.bigM = en.Param(initialize=self.bigM)


    def apply_constraints(self):

        for _, obj in self.ES.hub_obj.items():
            hub_vars = obj.nodes

            # Kirchoff flow constraint at each aggregation Hub
            def reliability(model, time_interval):
                a = 0
                for _, hv in hub_vars.items():
                    b = getattr(self.model, hv.node_name)
                    a += b[time_interval]
                return a == 0

            # Transformation constraint at each transformation Hub
            def loss(model, time_interval):
                a = 0
                b = 0
                for _, hv in hub_vars.items():
                    p = getattr(self.model, hv.positive_node_component)
                    n = getattr(self.model, hv.negative_node_component)
                    a += p[time_interval]
                    b += n[time_interval]
                c = a + b
                return c == 0.95*a  # e.g., 5% bi-directional loss

        # Apply the correct constraint based on the hub rule
        if obj.hub_rule == HubNodeRule.Tellegen:
            self.model.reliability_con = en.Constraint(self.model.Time, rule=reliability)
        if obj.hub_rule == HubNodeRule.Custom:
            self.model.loss_con = en.Constraint(self.model.Time, rule=loss)





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

    def values(self, variable_name):
        output = np.zeros(self.number_of_intervals)
        var_obj = getattr(self.model, variable_name)
        for index in var_obj:
            output[index] = var_obj[index].value
        return output

    def value_test(self):
        outputs = []
        for var in self.var_names:
            outputs.append(self.values(var))
        return outputs