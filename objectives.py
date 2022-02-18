from typing import List, Union

import pyomo.environ as en

from echo_models import Port, ConfigurationError


class Objective(object):

    def __init__(self,
                 component):
        self.component = component


class PeakPositivePower(Objective):

    def __init__(self,
                 component):
        super(PeakPositivePower, self).__init__(component)

    def verify_objective(self):
        """ Check objectives all reference an object of the correct type"""
        if not hasattr(self.component, 'port_name'):
            raise ConfigurationError('Peak Power objective must be applied to port component.')

    def create_params(self, model):
        pass

    def create_vars(self, model):
        self.component.max_pos = 'max_pos_' + self.component.port_name
        setattr(model, self.component.max_pos, en.Var(initialize=0, domain=en.NonNegativeReals))

    def apply_constraints(self, model):
        def max_value_rule(model, p, t):
            return getattr(model, self.component.max_pos) >= getattr(model, self.component.port_name)[p, t]

        setattr(model, f"max_pos_con_{self.component.port_name}", en.Constraint(model.Expansion, model.Time, rule=max_value_rule))

    def objective_expr(self, model):
        return getattr(model, self.component.max_pos)


class PeakNegativePower(Objective):

    def __init__(self,
                 component):
        super(PeakNegativePower, self).__init__(component)

    def verify_objective(self):
        """ Check objectives all reference an object of the correct type"""
        if not hasattr(self.component, 'port_name'):
            raise ConfigurationError('Peak Power objective must be applied to port component.')

    def create_params(self, model):
        pass

    def create_vars(self, model):
        self.component.max_neg = 'max_neg' + self.component.port_name
        setattr(model, self.component.max_neg, en.Var(initialize=0, domain=en.NonPositiveReals))

    def apply_constraints(self, model):
        def max_value_rule(model, p, t):
            return getattr(model, self.component.max_neg) <= getattr(model, self.component.port_name)[p, t]

        setattr(model, f"max_neg_con_{self.component.port_name}", en.Constraint(model.Expansion, model.Time, rule=max_value_rule))

    def objective_expr(self, model):
        return getattr(model, self.component.max_neg)*-1


class ImportTariff(Objective):

    def __init__(self,
                 component,
                 tariff_array,
                 expansion_periods
                 ):
        super(ImportTariff, self).__init__(component)
        self.import_tariff = {}
        self.create_tariff_dict(tariff_array, expansion_periods)

    def create_tariff_dict(self, array, expansion_periods):
        t = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(array)):
                t[(ep, i)] = array[i]
        self.import_tariff = t

    def verify_objective(self):
        """ Check objectives all reference an object of the correct type"""
        if not hasattr(self.component, 'port_name'):
            raise ConfigurationError('Import Tariff objective must be applied to port component.')

    def create_params(self, model):
        self.component.import_tariff = 'import_tariff_' + self.component.port_name
        setattr(model, self.component.import_tariff, en.Param(model.Expansion, model.Time, initialize=self.import_tariff))

    def create_vars(self, model):
        pass

    def apply_constraints(self, model):
        if not hasattr(self.component, 'pos'):
            self.component.constrain_pos_neg(model)

    def objective_expr(self, model):
        return sum(getattr(model, self.component.pos)[p, t] * getattr(model, self.component.import_tariff)[p, t] *
                   getattr(model, model.dr)[p] for p in model.Expansion for t in model.Time)


class ExportTariff(Objective):

    def __init__(self,
                 component,
                 tariff_array,
                 expansion_periods
                 ):
        super(ExportTariff, self).__init__(component)
        self.export_tariff = {}
        self.create_tariff_dict(tariff_array, expansion_periods)

    def create_tariff_dict(self, array, expansion_periods):
        t = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(array)):
                t[(ep, i)] = array[i]
        self.export_tariff = t

    def verify_objective(self):
        """ Check objectives all reference an object of the correct type"""
        if not hasattr(self.component, 'port_name'):
            raise ConfigurationError('Export Tariff objective must be applied to port component.')

    def create_params(self, model):
        pass

    def create_vars(self, model):
        pass

    def apply_constraints(self, model):
        if not hasattr(self.component, 'pos'):
            self.component.constrain_pos_neg(model)

    def objective_expr(self, model):
        return sum(getattr(model, self.component.neg)[p, t] * self.export_tariff[p, t] * model.dr[p]
                   for p in model.Expansion for t in model.Time)


class PathTariff(Objective):

    def __init__(self,
                 component,
                 tariff_array,
                 expansion_periods
                 ):
        super(PathTariff, self).__init__(component)
        self.path_tariff = {}
        self.create_tariff_dict(tariff_array, expansion_periods)

    def create_tariff_dict(self, array, expansion_periods):
        t = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(array)):
                t[(ep, i)] = array[i]
        self.path_tariff = t

    def verify_objective(self):
        """ Check objectives all reference an object of the correct type"""
        if not hasattr(self.component, 'flow_value'):
            raise ConfigurationError('Path Tariff objective must be applied to path component.')

    def create_params(self, model):
        self.component.path_tariff = 'path_tariff_' + self.component.path_name
        setattr(model, self.component.path_tariff, en.Param(model.Expansion, model.Time, initialize=self.path_tariff))

    def create_vars(self, model):
        pass

    def apply_constraints(self, model):
        pass

    def objective_expr(self, model):
        return sum(getattr(model, self.component.flow_value)[p, t] * getattr(model, self.component.path_tariff)[p, t] *
                   getattr(model, model.dr)[p] for p in model.Expansion for t in model.Time)


class DemandTariffObjective(Objective):

    def __init__(self,
                 component,
                 window,
                 expansion_periods,
                 demand_charge,
                 min_demand
                 ):
        super(DemandTariffObjective, self).__init__(component)
        self.window = None
        self.add_window(window, expansion_periods)
        self.demand_charge = demand_charge
        self.min_demand = min_demand

    def add_window(self, array, expansion_periods):
        window = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(array)):
                window[(ep, i)] = array[i]
        self.window = window

    def verify_objective(self):
        """ Check objectives all reference an object of the correct type"""
        if not hasattr(self.component, 'port_name'):
            raise ConfigurationError('Demand Tariff objective must be applied to port component.')

    def create_params(self, model):
        pass

    def create_vars(self, model):
        self.component.max_demand = 'max_demand_' + self.component.port_name
        setattr(model, self.component.max_demand, en.Var(initialize=0, domain=en.NonNegativeReals))

    def apply_constraints(self, model):
        if not hasattr(self.component, 'pos'):
            self.component.constrain_pos_neg(model)

        def max_demand_rule(model, p, t):
            return getattr(model, self.component.max_demand) >= \
                   (getattr(model, self.component.pos)[p, t] - self.min_demand) * self.window[p, t]

        setattr(model, f"cons_{self.component.port_name}_max_demand", en.Constraint(model.Expansion, model.Time,
                                                                          rule=max_demand_rule))

    def objective_expr(self, model):
        return getattr(model, self.component.max_demand) * self.demand_charge


class ThroughputCost(Objective):

    def __init__(self,
                 component,
                 rate):
        super(ThroughputCost, self).__init__(component)
        self.rate = rate

    def verify_objective(self):
        """ Check objectives all reference an object of the correct type"""
        if not hasattr(self.component, 'port_name'):
            raise ConfigurationError('Throughput Cost objective must be applied to port component.')

    def create_params(self, model):
        pass

    def create_vars(self, model):
        pass

    def apply_constraints(self, model):
        if not hasattr(self.component, 'pos'):
            self.component.constrain_pos_neg(model)

    def objective_expr(self, model):
        return sum(
            (getattr(model, self.component.pos)[p, t] - getattr(model, self.component.neg)[p, t]) *
            getattr(model, model.dr)[p] for p in model.Expansion for t in model.Time) * self.rate


class QuadraticPower(Objective):

    def __init__(self,
                 component):
        super(QuadraticPower, self).__init__(component)

    def verify_objective(self):
        """ Check objectives all reference an object of the correct type"""
        if not hasattr(self.component, 'port_name'):
            raise ConfigurationError('Quadratic Power objective must be applied to port component.')

    def create_params(self, model):
        pass

    def create_vars(self, model):
        pass

    def apply_constraints(self, model):
        if not hasattr(self.component, 'pos'):
            self.component.constrain_pos_neg(model)

    def objective_expr(self, model):
        return sum(
            (getattr(model, self.component.port_name)[p, t] * getattr(model, self.component.port_name)[p, t]) *
            getattr(model, model.dr)[p] for p in model.Expansion for t in model.Time)


class ContingencyNegative(Objective):

    """ FCAS Raise """

    def __init__(self,
                 component,
                 duration):
        super(ContingencyNegative, self).__init__(component)
        self.duration = duration

    def verify_objective(self):
        """ Check objectives all reference an object of the correct type"""
        if not hasattr(self.component, 'flow_value'):
            raise ConfigurationError('Contingency objective must be applied to path component.')

    def create_params(self, model):
        pass

    def create_vars(self, model):
        self.component.contingency_neg = 'cont_neg_' + self.component.path_name
        setattr(model, self.component.contingency_neg,
                en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonPositiveReals))

    def apply_constraints(self, model):

        def contingency_power_limited_by_flow_constraints(model, node1, node2, var, flow_constraint):
            def constraint(model, p, t):
                a = 0
                for _, other_path in model.paths.items():  # Check if the path includes [...node1, node2...]
                    if (node1 in other_path.vertices) and (node2 in other_path.vertices):
                        b = other_path.vertices.index(node1)
                        c = other_path.vertices.index(node2)
                        if b + 1 == c:
                            a += getattr(model, other_path.flow_value)[p, t]
                return getattr(model, var)[p, t] >= (flow_constraint - a)*-1
            return constraint

        # Iterate through vertices on path to pick up any port constraints along path
        for i in range(0, len(self.component.vertices) - 1):
            node1 = self.component.vertices[i]
            node2 = self.component.vertices[i + 1]
            exporting_port = self.component.edge_ports[i][0]
            importing_port = self.component.edge_ports[i][1]

            if exporting_port.export_constraint_value is not None:
                con_rule = contingency_power_limited_by_flow_constraints(model, node1, node2,
                                                                         self.component.contingency_neg,
                                                                         exporting_port.export_constraint_value * -1)
                setattr(model, f"cont_neg_con_one_{exporting_port.port_name}",
                        en.Constraint(model.Expansion, model.Time, rule=con_rule))
            if importing_port.import_constraint_value is not None:
                con_rule = contingency_power_limited_by_flow_constraints(model, node1, node2,
                                                                         self.component.contingency_neg,
                                                                         importing_port.import_constraint_value)
                setattr(model, f"cont_neg_con_two_{importing_port.port_name}",
                        en.Constraint(model.Expansion, model.Time, rule=con_rule))

        # Meet SOC constraint on contingency providing asset, if applicable
        if hasattr(self.component.start_port, 'soc_value'):
            def contingency_energy_limited_soc(model, p, t):
                return getattr(model, self.component.contingency_neg)[p, t] * self.duration / 60 >= \
                       getattr(model, self.component.start_port.soc_value)[p, t]*-1

            setattr(model, f"cont_neg_soc_lim_{self.component.path_name}",
                    en.Constraint(model.Expansion, model.Time, rule=contingency_energy_limited_soc))

    def objective_expr(self, model):
        return sum(getattr(model, self.component.contingency_neg)[p, t] * getattr(model, model.dr)[p]
                   for p in model.Expansion for t in model.Time)


class ContingencyPositive(Objective):
    """ FCAS lower """

    def __init__(self,
                 component,
                 duration):
        super(ContingencyPositive, self).__init__(component)
        self.duration = duration

    def verify_objective(self):
        """ Check objectives all reference an object of the correct type"""
        if not hasattr(self.component, 'flow_value'):
            raise ConfigurationError('Contingency objective must be applied to path component.')

    def create_params(self, model):
        pass

    def create_vars(self, model):
        self.component.contingency_pos = 'cont_pos_' + self.component.path_name
        setattr(model, self.component.contingency_pos,
                en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))

    def apply_constraints(self, model):

        def contingency_power_limited_by_flow_constraints(model, node1, node2, var, flow_constraint):
            def constraint(model, p, t):
                a = 0
                for _, other_path in model.paths.items():  # Check if the path includes [...node1, node2...]
                    if (node1 in other_path.vertices) and (node2 in other_path.vertices):
                        b = other_path.vertices.index(node1)
                        c = other_path.vertices.index(node2)
                        if b - 1 == c:
                            a += getattr(model, other_path.flow_value)[p, t]
                return getattr(model, var)[p, t] <= (flow_constraint - a)
            return constraint

        # Iterate through vertices on path to pick up any port constraints along path
        for i in range(0, len(self.component.vertices) - 1):
            node1 = self.component.vertices[i]
            node2 = self.component.vertices[i + 1]
            exporting_port = self.component.edge_ports[i][0]
            importing_port = self.component.edge_ports[i][1]

            if exporting_port.export_constraint_value is not None:
                con_rule = contingency_power_limited_by_flow_constraints(model, node1, node2,
                                                                         self.component.contingency_pos,
                                                                         exporting_port.export_constraint_value * -1)
                setattr(model, f"cont_pos_con_one_{exporting_port.port_name}",
                        en.Constraint(model.Expansion, model.Time, rule=con_rule))
            if importing_port.import_constraint_value is not None:
                con_rule = contingency_power_limited_by_flow_constraints(model, node1, node2,
                                                                         self.component.contingency_pos,
                                                                         importing_port.import_constraint_value)
                setattr(model, f"cont_pos_con_two_{importing_port.port_name}",
                        en.Constraint(model.Expansion, model.Time, rule=con_rule))

        # Meet SOC constraint on contingency providing asset, if applicable
        if hasattr(self.component.start_port, 'soc_value'):
            def contingency_energy_limited_soc(model, p, t):
                return getattr(model, self.component.contingency_pos)[p, t] * self.duration / 60 <= \
                       self.component.start_port.max_capacity - getattr(model, self.component.start_port.soc_value)[p, t]

            setattr(model, f"cont_pos_soc_lim_{self.component.path_name}",
                    en.Constraint(model.Expansion, model.Time, rule=contingency_energy_limited_soc))

    def objective_expr(self, model):
        return sum(getattr(model, self.component.contingency_pos)[p, t] * getattr(model, model.dr)[p]
                   for p in model.Expansion for t in model.Time)*-1


class ObjectiveSet(object):

    def __init__(self,
                 objective_list):
        self.objectives = objective_list

    def initialise_objective(self, model):
        for obj in self.objectives:
            obj.verify_objective()
            obj.create_params(model)
            obj.create_vars(model)
            obj.apply_constraints(model)

    def set_objective(self, model, optimiser):
        def objective_rule(model):
            return sum(obj.objective_expr(model) for obj in self.objectives)
#        model.objective = en.Objective(rule=objective, sense=en.minimize)
        optimiser.objective += objective_rule(model)






