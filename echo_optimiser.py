from pyomo.opt import SolverFactory
import pyomo.environ as en
import pyomo.network
import os
import numpy as np
from configuration import Units, Flows, FlowConstraint, OptimisationType, HubNodeRule, TransformationRule
from constants import minutes_per_hour
from echo_models import FlexibleAsset, ElectricalStorage, ConfigurationError


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

        self.model.discount_factors = 'discount_rates'
        setattr(self.model, self.model.discount_factors,
                en.Param(self.model.Expansion, self.model.Time, initialize=self.ES.discount_factors))

        # Parameters and Variable Definitions for Assets
        for _, obj in self.ES.asset_obj.items():
            self.add_asset(obj)

        # Verify hubs are set up correctly
        for _, hub_obj in self.ES.hub_obj.items():
            hub_obj.verify_hub()

        # Initialise edges and add edge constraints
        for _, edge in self.ES.edge_obj.items():
            edge.initialise_edge(self.model)


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

            # Apply correct hub constraint based on hub rule
            if obj.hub_rule == HubNodeRule.Tellegen:
                con_name = 'reliability_con_' + obj.hub_name
                setattr(self.model, con_name, en.Constraint(self.model.Expansion, self.model.Time, rule=reliability))

            # Generic transformation hub
            def transform(model, expansion_interval, time_interval):
                lhs = 0
                rhs = 0
                for _, i in obj.transformation.items():
                    rhs = i.rhs
                    for var, weight in i.lhs.items():
                        tr_rule = i.rule[var]
                        if tr_rule is TransformationRule.Both:
                            lhs += getattr(self.model, var.node_name)[expansion_interval, time_interval] * weight
                        if tr_rule is TransformationRule.NegativeComponent:
                            lhs += getattr(self.model, var.negative_node_component)[
                                       expansion_interval, time_interval] * weight
                        if tr_rule is TransformationRule.PositiveComponent:
                            lhs += getattr(self.model, var.positive_node_component)[
                                       expansion_interval, time_interval] * weight
                return lhs == rhs

            if obj.hub_rule == HubNodeRule.Transform:
                if not obj.transformation:
                    raise ConfigurationError("Transformation object has not been added to Node.")
                con_name = 'transformation_con_' + obj.hub_name
                setattr(self.model, con_name, en.Constraint(self.model.Expansion, self.model.Time, rule=transform))

    def apply_expansion_constraints(self):
        # ToDo - include other asset types in expansion problem
        # ToDo - include option for constraining number of expansion type decisions (e.g., network expansion vs asset expansion)
        def storage_exp_rule(model, expansion_interval):
            a = 0
            for _, storage_hub in self.ES.expansion_obj.items():
                for _, storage_port in storage_hub.nodes.items():
                    a += getattr(model, storage_port.installed)[expansion_interval]
            return a <= self.ES.global_storage_exp_con

        if self.ES.expansion_obj:
            con_name = 'storage_exp_con'
            setattr(self.model, con_name, en.Constraint(self.model.Expansion, rule=storage_exp_rule))

    def build_objective(self):
        self.objective = 0
        for _, obj in self.ES.asset_obj.items():
            self.objective += obj.add_objective(self.model)

        for _, obj in self.ES.edge_obj.items():
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

    def hub_values(self, hub_obj, expansion):
        outputs = {}
        for name, var_obj in hub_obj.nodes.items():
            outputs[name] = self.values(var_obj.node_name, expansion)
        return outputs

    def hub_installations(self, hub_obj, expansion):
        outputs = {}
        for name, var_obj in hub_obj.nodes.items():
            outputs[name] = self.values(var_obj.installed, expansion)
        return outputs

    def print_life_cycle(self, var, expansion_periods):
        for j in range(0, expansion_periods):
            print('expansion period: ' + str(j))
            print('installed:' + str(self.values(var.installed, j)))
            print('retired:' + str(self.values(var.retire, j)))
            print('replaced:' + str(self.values(var.replace, j)))
            print('life remaining:' + str(self.values(var.lifetime_remaining, j)))
            print('\n')

    def print_expansion_life_cycle(self, expansion_periods):
        if not self.ES.expansion_obj:
            return print('No expansion objects')
        else:
            for _, i in self.ES.expansion_obj.items():
                for _, m in i.nodes.items():
                    print(m.node_name)
                    output = {'installed': [], 'active': [], 'retired': [], 'replaced': [],
                              'life remaining': []}
                    for j in range(0, expansion_periods):
                        output['installed'].append(self.values(m.installed, j))
                        output['active'].append(self.values(m.state_value, j))
                        output['retired'].append(self.values(m.retire, j))
                        output['replaced'].append(self.values(m.replace, j))
                        output['life remaining'].append((self.values(m.lifetime_remaining, j)))

                    print(output)
                    print('\n')
