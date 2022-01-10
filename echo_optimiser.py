from pyomo.opt import SolverFactory
import pyomo.environ as en
import pyomo.network
import os
import numpy as np
from configuration import Units, Flows, FlowConstraint, OptimisationType, HubNodeRule, TransformationRule, ExpansionType
from constants import minutes_per_hour
from echo_models import ConfigurationError
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
        self.apply_expansion_constraints()
        self.build_objective()
        self.optimise()

    def add_port(self, obj):
        # Constraints relevant to particular assets are added here as part of initialising the port
        obj.verify_port()
        obj.initialise_port(self.model)

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

        self.model.dr = 'discount_rates'
        setattr(self.model, self.model.dr,
                en.Param(self.model.Expansion, initialize=self.ES.discount_factors))

        # Add expansion objects
        self.ES.add_expansions(self.ES.expansion_periods)

        # Parameter and Variable Definitions for ports
        for _, obj in self.ES.port_obj.items():
            self.add_port(obj)

        # Verify hubs are set up correctly and initialise hub variables
        for _, hub_obj in self.ES.hub_obj.items():
            hub_obj.verify_hub()
            hub_obj.initialise_hub(self.model)

        # Initialise edges and add edge constraints
        for _, edge in self.ES.edge_obj.items():
            edge.initialise_edge(self.model)

    def apply_constraints(self):
        # Hub constraints
        for _, obj in self.ES.hub_obj.items():
            hub_vars = obj.ports

            def reliability(model, expansion_interval, time_interval):  # Tellegen hub rule
                a = 0
                for _, hv in hub_vars.items():
                    b = getattr(self.model, hv.port_name)
                    a += b[expansion_interval, time_interval]
                return a == 0

            def transform(model, expansion_interval, time_interval):  # Generic transformation hub
                lhs = 0
                rhs = 0
                for _, i in obj.transformation.items():
                    rhs = i.rhs
                    for var, weight in i.lhs.items():
                        tr_rule = i.rule[var]
                        if tr_rule is TransformationRule.Both:
                            lhs += getattr(self.model, var.port_name)[expansion_interval, time_interval] * weight
                        if tr_rule is TransformationRule.NegativeComponent:
                            lhs += getattr(self.model, var.negative_port_component)[
                                       expansion_interval, time_interval] * weight
                        if tr_rule is TransformationRule.PositiveComponent:
                            lhs += getattr(self.model, var.positive_port_component)[
                                       expansion_interval, time_interval] * weight
                return lhs == rhs

            if obj.hub_rule == HubNodeRule.Transform:
                con_name = 'transformation_con_' + obj.hub_name
                setattr(self.model, con_name, en.Constraint(self.model.Expansion, self.model.Time, rule=transform))
            if obj.hub_rule == HubNodeRule.Tellegen:
                con_name = 'reliability_con_' + obj.hub_name
                setattr(self.model, con_name, en.Constraint(self.model.Expansion, self.model.Time, rule=reliability))

    def apply_expansion_constraints(self):

        def storage_exp_rule(model, expansion_interval):
            a = 0
            for _, hub in self.ES.asset_expansion_obj.items():
                if hub.expansion_asset_type == ExpansionType.Storage:
                    a += getattr(model, hub.hub_installed)[expansion_interval]
            if type(a) is int:
                return en.Constraint.Feasible
            else:
                return a <= self.ES.global_storage_exp_con

        def gen_exp_rule(model, expansion_interval):
            a = 0
            for _, hub in self.ES.asset_expansion_obj.items():
                if hub.expansion_asset_type == ExpansionType.Generation:
                    a += getattr(model, hub.hub_installed)[expansion_interval]
            if type(a) is int:
                return en.Constraint.Feasible
            else:
                return a <= self.ES.global_generator_exp_con

        if self.ES.asset_expansion_obj:
            con_name = 'global_storage_exp_con'
            setattr(self.model, con_name, en.Constraint(self.model.Expansion, rule=storage_exp_rule))
            con_name = 'global_gen_exp_con'
            setattr(self.model, con_name, en.Constraint(self.model.Expansion, rule=gen_exp_rule))

    def build_objective(self):
        self.objective = 0
        for _, obj in self.ES.port_obj.items():
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
                return var_obj[expansion].value
            else:
                return var_obj.value

    def hub_values(self, hub_obj, expansion_period):
        """ Returns all values of all ports in a specified hub for a single specified expansion period."""

        outputs = {}
        for name, var_obj in hub_obj.ports.items():
            outputs[name] = self.values(var_obj.port_name, expansion_period)
        return outputs

    def hub_life_cycle(self, hub_obj, total_expansion_periods):
        """ Returns life-cycle variables (installed, retired, replaced, capacity) for all ports in the specified hub,
         for all expansion periods. """

        output = {'expansion period': [], 'installed': [], 'retired': [], 'replaced': [], 'remaining life': []}
        rows = []
        for name, var in hub_obj.ports.items():
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
            for _, hub in self.ES.asset_expansion_obj.items():
                output = {'exp': [], 'installed': [], 'active': [], 'retired': [], 'replaced': [], 'remaining life': []}
                rows = []
                for name, var in hub.ports.items():
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

        output = {'initial_edge_capacity': [], 'current_edge_capacity': [], 'capacity_added': []}
        output['initial_edge_capacity'].append(edge.initial_edge_capacity)
        for j in range(0, total_expansion_periods):
            output['current_edge_capacity'].append(self.values(edge.current_cap, j))
            if edge.expansion_planning is True:
                output['capacity_added'].append(self.values(edge.cap_add, j))
        return output

    def get_expansion_ports(self):
        """ Returns all expansion hub ports in model."""

        output = []
        for _, exp_hub in self.ES.asset_expansion_obj.items():
            for _, exp_port in exp_hub.ports.items():
                output.append(exp_port)
        return output

    def test_value_functions(self, hub, total_expansion_periods):
        """ Tests all value functions for a specified hub."""

        print('Hub values')
        print(self.hub_values(hub, 0))
        print('\nHub life cycle')
        print(self.hub_life_cycle(hub, total_expansion_periods))
        p = list(hub.ports.values())[0]
        p_name = list(hub.ports.keys())[0]
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






