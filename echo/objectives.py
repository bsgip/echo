import uuid
from typing import List, Union

import abc
from datetime import datetime, date, time, timedelta
from typing import Literal, Union, List, Optional
from pydantic import BaseModel, validator
from enum import Enum
import pyomo.environ as en
import pandas as pd
import numpy as np


from .echo_models import Port, ConfigurationError


class Objective(object):

    def __init__(self,
                 component):
        self.component = component


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

    def objective_val(self, optimiser, expansion_period):
        return optimiser.values(self.component.max_pos, expansion_period)


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

    def objective_val(self, optimiser, expansion_period):
        return optimiser.values(self.component.max_neg, expansion_period)*-1


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

    def objective_val(self, optimiser, expansion_period):
        return optimiser.values(self.component.pos, expansion_period) * \
               optimiser.values(self.component.import_tariff, expansion_period)


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
        self.component.export_tariff = 'export_tariff_' + self.component.port_name
        setattr(model, self.component.export_tariff, en.Param(model.Expansion, model.Time, initialize=self.export_tariff))
        pass

    def create_vars(self, model):
        pass

    def apply_constraints(self, model):
        if not hasattr(self.component, 'pos'):
            self.component.constrain_pos_neg(model)

    def objective_expr(self, model):
        return sum(getattr(model, self.component.neg)[p, t] * getattr(model, self.component.export_tariff)[p, t] *
                   getattr(model, model.dr)[p] for p in model.Expansion for t in model.Time)

    def objective_val(self, optimiser, expansion_period):
        return optimiser.values(self.component.neg, expansion_period) * \
               optimiser.values(self.component.export_tariff, expansion_period)


class PathTariff(Objective):

    def __init__(self,
                 component,
                 tariff_array,
                 expansion_periods: int=1
                 ):
        super(PathTariff, self).__init__(component)
        self.path_tariff = {}
        self.create_tariff_dict(tariff_array, expansion_periods)
        self.uid = uuid.uuid4()

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
        self.component.path_tariff = 'path_tariff_' + str(self.uid)
        setattr(model, self.component.path_tariff, en.Param(model.Expansion, model.Time, initialize=self.path_tariff))

    def create_vars(self, model):
        pass

    def apply_constraints(self, model):
        pass

    def objective_expr(self, model):
        return sum(getattr(model, self.component.flow_value)[p, t] * getattr(model, self.component.path_tariff)[p, t] *
                   getattr(model, model.dr)[p] for p in model.Expansion for t in model.Time)

    def objective_val(self, optimiser, expansion_period):
        return optimiser.values(self.component.flow_value, expansion_period) * \
               optimiser.values(self.component.path_tariff, expansion_period)


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

    def objective_val(self, optimiser, expansion_period):
        return (optimiser.values(self.component.pos, expansion_period) -
                optimiser.values(self.component.neg, expansion_period)) * self.rate


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

    def objective_val(self, optimiser, expansion_period):
        return optimiser.values(self.component.port_name, expansion_period) * \
               optimiser.values(self.component.port_name, expansion_period)


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

    def objective_val(self, optimiser, expansion_period):
        return optimiser.values(self.component.contingency_neg, expansion_period)


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

    def objective_val(self, optimiser, expansion_period):
        return optimiser.values(self.component.contingency_pos, expansion_period) * -1


# From neon



class ResetPeriod(Enum):
    # TODO How can we model rolling reset windows in the optimisation?
    month = 'month'
    quarter = 'quarter'
    year = 'year'


class Day(Enum):
    weekday = 'weekday'
    weekend = 'weekend'
    holiday = 'holiday'


class TimePeriod(object):

    def __init__(self,
                 start_time: time,
                 end_time: time,
                 day_type: List[Day]):
        self.start_time = start_time
        self.end_time = end_time
        self.day_type = day_type

    def to_bool(self, df: pd.DataFrame) -> np.ndarray:
        """
        Convert time period to an array based on whether a row is in the time period
        Args:
            df: input DataFrame

        Returns:

        """
        allowed_days_of_week_start = 7
        allowed_days_of_week_end = 0
        if Day.weekday in self.day_type:
            # Weekdays are 0...4
            allowed_days_of_week_start = 0
            allowed_days_of_week_end = 4
        else:
            allowed_days_of_week_start = 5
        if Day.weekend in self.day_type:
            # Weekends are 5, 6
            allowed_days_of_week_end = 6
        if Day.holiday in self.day_type:
            raise NotImplementedError('Public holidays not currently supported in optimisation')
        return (
                   (df.index.isin(df.between_time(self.start_time, self.end_time, include_start=True, include_end=False).index))
                   & (df.index.weekday <= allowed_days_of_week_end)
                   & (df.index.weekday >= allowed_days_of_week_start)
        ).astype(int)

    def overlaps(self, other: 'TimePeriod'):
        """
        Determine whether two `TimePeriod`s are overlapping. Used for validating `Window`s.
        Args:
            other:

        Returns:

        """
        if set(self.day_type).intersection(set(other.day_type)):
            end_time = self.end_time
            if end_time == time(0, 0):
                end_time = time(23, 59, 59)
            if self.start_time > self.end_time:
                self_ranges = [(time(0, 0), end_time), (self.start_time, time(23, 59, 59))]
            else:
                self_ranges = [(self.start_time, end_time)]
            end_time = other.end_time
            if end_time == time(0, 0):
                end_time = time(23, 59, 59)
            if other.start_time > other.end_time:
                other_ranges = [(time(0, 0), end_time), (other.start_time, time(23, 59, 59))]
            else:
                other_ranges = [(other.start_time, end_time)]

            for self_range in self_ranges:
                for other_range in other_ranges:
                    if self_range[0] < other_range[1] and other_range[0] < self_range[1]:
                        return True
        return False


class Window(object):

    def  __init__(self, time_periods: List[TimePeriod]):
        self.time_periods = time_periods

    @validator('time_periods')
    def non_overlapping_periods(cls, v):
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                if v[i].overlaps(v[j]):
                    raise ValueError(f"TimePeriod {v[i]} overlaps with TimePeriod {v[j]}")
        return v

    def to_bool_periods(self, df: pd.DataFrame) -> np.ndarray:
        if isinstance(df, dict):
            df = pd.DataFrame(df)
            df.index = pd.to_datetime(df.index)
        time_period_stack = np.column_stack([period.to_bool(df) for period in self.time_periods])
        return time_period_stack.any(axis=1).astype(int)


class DemandTariffObjective(Objective):

    def __init__(self,
                 component,
                 demand_charges,
                 excess_demand_charge,
                 off_peak_demand_charge,
                 df=None,
                 expansion_periods=1
                 ):
        super(DemandTariffObjective, self).__init__(component)
        self.demand_charges = demand_charges
        self.excess_demand_charge = excess_demand_charge
        self.off_peak_demand_charge = off_peak_demand_charge
        self.df = df  # pandas dataframe for carrying date info so we can define weekday/weekend rates etc
        self.expansion_periods = expansion_periods

    def verify_objective(self):
        """ Check objectives all reference an object of the correct type"""
        if not hasattr(self.component, 'port_name'):
            raise ConfigurationError('Demand Tariff objective must be applied to port component.')

        if type(self.demand_charges) is not list:
            raise ConfigurationError('Enter list of demand charges.')

        # Check that windows are not overlapping if there are multiple demand charges defined
        v = []
        for dc in self.demand_charges:
            if dc.window is not None:
                v.append(dc.window.time_periods[0])
                for i in range(len(v)):
                    for j in range(i + 1, len(v)):
                        if v[i].overlaps(v[j]):
                            raise ValueError(f"TimePeriod {v[i]} overlaps with TimePeriod {v[j]}")

    def create_params(self, model):
        # Create window bool param for each demand charge
        for dc in self.demand_charges:
            if dc.window:
                # Check that there is a dataframe reference
                if self.df is None:
                    raise ConfigurationError('Enter pandas date_range in demandtariffobjective if using time periods to define tariffs.')
                dc.window_obj_to_bool(self.df, self.expansion_periods)
                dc.create_params(model)
            elif dc.window_array is not None:
                dc.window_array_to_bool(self.expansion_periods)
                dc.create_params(model)
            else:
                raise ConfigurationError('Window not defined for demand charge.')

    def create_vars(self, model):
        for dc in self.demand_charges:
            dc.max_demand_val = 'max_demand_' + str(dc.uid)
            setattr(model, dc.max_demand_val, en.Var(initialize=0, domain=en.NonNegativeReals))

        # Todo finish implementing this
        if self.excess_demand_charge:
            setattr(model, f"demand_{dc.uid}_excess_demand_charge_amount", en.Var(within=en.NonNegativeReals, initialize=0))

        if self.off_peak_demand_charge:
            setattr(model, f"demand_{dc.uid}_off_peak_demand_amount", en.Var(within=en.NonNegativeReals, initialize=0))

    def apply_constraints(self, model):
        if not hasattr(self.component, 'pos'):
            self.component.constrain_pos_neg(model)

        for dc in self.demand_charges:
            def max_demand_rule(model, p, t):
                return getattr(model, dc.max_demand_val) >= \
                       (getattr(model, self.component.pos)[p, t] - dc.min_demand) * getattr(model, dc.window_active)[p, t]

            setattr(model, f"cons_{dc.max_demand_val}_max_demand", en.Constraint(model.Expansion, model.Time,
                                                                              rule=max_demand_rule))

    def objective_expr(self, model):
        objective = 0
        for dc in self.demand_charges:
            objective += getattr(model, dc.max_demand_val) * dc.rate
        if self.excess_demand_charge:
            pass
        if self.off_peak_demand_charge:
            pass
        return objective


class DemandCharge(object):
    """ A demand charge is a rate that applies to the maximum demand over a specified time window."""

    def __init__(self,
                 rate,
                 min_demand,
                 window=None,
                 window_array=None,
                 ):
        self.rate = rate
        self.min_demand = min_demand
        self.uid = uuid.uuid4()
        self.window_bool = None
        self.window = window
        self.window_array = window_array

    def window_array_to_bool(self, expansion_periods):
        w = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(self.window_array)):
                w[(ep, i)] = self.window_array[i]
        self.window_bool = w

    def window_obj_to_bool(self, df, expansion_periods):
        array = self.window.to_bool_periods(df)
        w = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(array)):
                w[(ep, i)] = array[i]
        self.window_bool = w

    def create_params(self, model):
        self.window_active = 'window_active_' + str(self.uid)
        setattr(model, self.window_active, en.Param(model.Expansion, model.Time, initialize=self.window_bool, domain=en.Binary))


