import uuid
from datetime import datetime, date, time, timedelta
from typing import Literal, Union, List, Optional, Any, Type
from echo.echo_models import *  #imports our defined basemodel with its config settings
import pyomo.environ as en
import pandas as pd
import numpy as np
from echo.echo_validators import *  # need this to get our array type
from pydantic import Field, validator, root_validator, NegativeFloat, PositiveFloat, confloat, PositiveInt

from echo.echo_models import Port, ConfigurationError


class Objective(BaseModel):

    component: Union[Port, Path]
    uid: uuid.UUID = Field(default_factory=uuid.uuid4)
    obj_name: Optional[str] = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.obj_name is None:
            self.obj_name = 'obj_' + str(self.uid)

    def verify_objective(self, model):
        pass

    def create_params(self, model):
        pass

    def create_vars(self, model):
        pass

    def objective_expr(self, model):
        pass

    def get_objective_total(self, optimiser):
        obj_expr = self.objective_expr(optimiser.model) # Retrieve the objective expression
        return en.value(obj_expr) # Return the value of the summed expression

class ObjectiveSet(BaseModel):
    """ Objective Set is an object containing a list of defined objectives that can be passed to the echo optimiser"""
    objective_list: list

    def initialise_objective(self, model):
        for obj in self.objective_list:
            obj.verify_objective(model)
            obj.create_params(model)
            obj.create_vars(model)
            obj.apply_constraints(model)

    def set_objective(self, model, optimiser):
        def objective_rule(model):
            return sum(obj.objective_expr(model) for obj in self.objective_list)
#        model.objective = en.Objective(rule=objective, sense=en.minimize)
        optimiser.objective += objective_rule(model)

class PeakPositivePower(Objective):
    """ The PeakPositivePower objective minimises the peak positive (imported) power at the specified port. """
    component: Port
    max_pos: Optional[str]

    def __init__(self, **data):
        super().__init__(**data)
        self.max_pos = 'max_pos_' + self.obj_name

    def create_vars(self, model):
        setattr(model, self.max_pos, en.Var(initialize=0, domain=en.NonNegativeReals))

    def apply_constraints(self, model):
        def max_value_rule(model, p, t):
            return getattr(model, self.max_pos) >= getattr(model, self.component.pos)[p, t]

        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

        setattr(model, f"max_pos_con_{self.component.port_name}", en.Constraint(model.Expansion, model.Time, rule=max_value_rule))

    def objective_expr(self, model):
        return getattr(model, self.max_pos)

class PeakNegativePower(Objective):
    """ The PeakNegativePower objective minimises the peak negative (exported) power at the specified port. """
    max_neg: Optional[str]

    def __init__(self, **data):
        super().__init__(**data)
        self.max_neg = 'max_neg_' + self.obj_name

    def create_vars(self, model):
        setattr(model, self.max_neg, en.Var(initialize=0, domain=en.NonPositiveReals))

    def apply_constraints(self, model):
        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

        def max_value_rule(model, p, t):
            return getattr(model, self.max_neg) <= getattr(model, self.component.neg)[p, t]

        setattr(model, f"max_neg_con_{self.component.port_name}", en.Constraint(model.Expansion, model.Time, rule=max_value_rule))

    def objective_expr(self, model):
        return getattr(model, self.max_neg)*-1

class Tariff(Objective):
    tariff_array: Union[ArrayType, list]  #tariff array prices should always be positive
    expansion_periods: Optional[PositiveInt] = 1

    @staticmethod
    def return_tariff_dict(array, expansion_periods):
        keys = [(x, i) for x in range(expansion_periods) for i in range(len(array))]
        vals = dict(zip(keys, array))
        return vals

class ImportTariff(Tariff):
    """ The ImportTariff objective applies a price per kWh of energy imported at a defined port."""
    component: Port
    import_tariff: Optional[str]
    import_tariff_dict: Optional[dict]

    def __init__(self, **data):
        super().__init__(**data)
        self.import_tariff = 'import_tariff_' + self.obj_name
        self.import_tariff_dict = self.return_tariff_dict(self.tariff_array, self.expansion_periods)

    def create_params(self, model):

        setattr(model, self.import_tariff, en.Param(model.Expansion, model.Time, initialize=self.import_tariff_dict))

    def apply_constraints(self, model):
        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

    def objective_expr(self, model):
        return sum(getattr(model, self.component.pos)[p, t] * getattr(model, self.import_tariff)[p, t] *
                   model.interval_duration/60 * getattr(model, model.dr)[p] for p in model.Expansion for t in model.Time)

class ExportTariff(Tariff):
    """ The ExportTariff objective applies a tariff, defined as an array of prices,
     to the negative (exporting) component of the specified port."""
    component: Port
    export_tariff: Optional[str]
    export_tariff_dict: Optional[dict]

    def __init__(self, **data) -> None:
        super().__init__(**data)
        self.export_tariff = 'export_tariff_' + self.obj_name
        self.export_tariff_dict = self.return_tariff_dict(self.tariff_array, self.expansion_periods)

    def create_params(self, model):
        setattr(model, self.export_tariff, en.Param(model.Expansion, model.Time, initialize=self.export_tariff_dict))

    def apply_constraints(self, model):
        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

    def objective_expr(self, model):
        return sum(getattr(model, self.component.neg)[p, t] * getattr(model, self.export_tariff)[p, t] *
                   model.interval_duration / 60 * getattr(model, model.dr)[p] for p in model.Expansion for t in model.Time)

class PathTariff(Tariff):
    """ The PathTariff objective applies a cost per kW of power flow on a specified path."""
    component: Path
    path_tariff: Optional[str]
    path_tariff_dict: Optional[dict]

    def __init__(self, **data) -> None:
        super().__init__(**data)
        self.path_tariff = 'path_tariff_' + self.obj_name
        self.path_tariff_dict = self.return_tariff_dict(self.tariff_array, self.expansion_periods)

    def create_params(self, model):
        setattr(model, self.path_tariff, en.Param(model.Expansion, model.Time, initialize=self.path_tariff_dict))

    def apply_constraints(self, model):
        pass

    def objective_expr(self, model):
        return sum(getattr(model, self.component.flow_value)[p, t] * getattr(model, self.path_tariff)[p, t] *
                   getattr(model, model.dr)[p] for p in model.Expansion for t in model.Time)

class ThroughputCost(Objective):
    """ A ThroughputCost objective applies a fixed rate to total throughput (i.e. import minus export) at a port. """
    component: Port
    rate: PositiveFloat

    def apply_constraints(self, model):
        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

    def objective_expr(self, model):
        obj = sum(
            (getattr(model, self.component.pos)[p, t] - getattr(model, self.component.neg)[p, t]) *
            getattr(model, model.dr)[p] for p in model.Expansion for t in model.Time) * self.rate
        return obj

class QuadraticPower(Objective):
    """ The QuadraticPower objective minimises flow^2 at a specified port."""
    component: Port

    def apply_constraints(self, model):
        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

    def objective_expr(self, model):
        return sum(
            (getattr(model, self.component.port_name)[p, t] * getattr(model, self.component.port_name)[p, t]) *
            getattr(model, model.dr)[p] for p in model.Expansion for t in model.Time)

class Contingency(Objective):
    component: Path

class ContingencyNegative(Objective):
    """ FCAS Raise """
    duration: PositiveFloat
    contingency_neg: Optional[str]

    def __init__(self, **data):
        super().__init__(**data)
        self.contingency_neg = 'cont_neg_' + self.obj_name

    def create_vars(self, model):
        setattr(model, self.contingency_neg, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonPositiveReals))

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
                                                                         self.contingency_neg,
                                                                         exporting_port.export_constraint_value * -1)
                setattr(model, f"cont_neg_con_one_{exporting_port.port_name}",
                        en.Constraint(model.Expansion, model.Time, rule=con_rule))
            if importing_port.import_constraint_value is not None:
                con_rule = contingency_power_limited_by_flow_constraints(model, node1, node2,
                                                                         self.contingency_neg,
                                                                         importing_port.import_constraint_value)
                setattr(model, f"cont_neg_con_two_{importing_port.port_name}",
                        en.Constraint(model.Expansion, model.Time, rule=con_rule))

        # Meet SOC constraint on contingency providing asset, if applicable
        if hasattr(self.component.edge_ports[0][0], 'soc_value'):
            def contingency_energy_limited_soc(model, p, t):
                return getattr(model, self.contingency_neg)[p, t] * self.duration / 60 >= \
                       getattr(model, self.component.edge_ports[0][0].soc_value)[p, t]*-1

            setattr(model, f"cont_neg_soc_lim_{self.component.path_name}",
                    en.Constraint(model.Expansion, model.Time, rule=contingency_energy_limited_soc))

    def objective_expr(self, model):
        return sum(getattr(model, self.contingency_neg)[p, t] * getattr(model, model.dr)[p]
                   for p in model.Expansion for t in model.Time)

class ContingencyPositive(Objective):
    """ FCAS Lower """
    duration: PositiveFloat
    contingency_pos: Optional[str]

    def __init__(self, **data):
        super().__init__(**data)
        self.contingency_pos = 'cont_pos_' + self.obj_name

    def create_vars(self, model):
        setattr(model, self.contingency_pos, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))

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
                                                                         self.contingency_pos,
                                                                         exporting_port.export_constraint_value * -1)
                setattr(model, f"cont_pos_con_one_{exporting_port.port_name}",
                        en.Constraint(model.Expansion, model.Time, rule=con_rule))
            if importing_port.import_constraint_value is not None:
                con_rule = contingency_power_limited_by_flow_constraints(model, node1, node2,
                                                                         self.contingency_pos,
                                                                         importing_port.import_constraint_value)
                setattr(model, f"cont_pos_con_two_{importing_port.port_name}",
                        en.Constraint(model.Expansion, model.Time, rule=con_rule))

        # Meet SOC constraint on contingency providing asset, if applicable
        if hasattr(self.component.edge_ports[0][0], 'soc_value'):
            def contingency_energy_limited_soc(model, p, t):
                return getattr(model, self.contingency_pos)[p, t] * self.duration / 60 <= \
                       self.component.edge_ports[0][0].max_capacity - getattr(model, self.component.edge_ports[0][0].soc_value)[p, t]

            setattr(model, f"cont_pos_soc_lim_{self.component.path_name}",
                    en.Constraint(model.Expansion, model.Time, rule=contingency_energy_limited_soc))

    def objective_expr(self, model):
        return sum(getattr(model, self.contingency_pos)[p, t] * getattr(model, model.dr)[p]
                   for p in model.Expansion for t in model.Time)*-1

class DemandTariffObjective(Objective):
    """ A demand tariff objective contains a set of one or more demand charges."""
    component: Port
    demand_charges: list
    import_demand: bool
    export_demand: bool
    expansion_periods: Optional[PositiveInt] = 1

    def verify_objective(self, model):
        def verify_non_overlapping():
            # Check that windows are not overlapping if there are multiple demand charges defined
            prev_window = np.array([])
            prev_dc = None
            for dc in self.demand_charges:
                if prev_window.size > 0:
                   comparison = np.array(prev_window)*np.array(dc.window_array)
                   if sum(comparison) > 0:
                       raise ValueError(f"Overlapping time periods between {prev_dc} and {dc}")
                   prev_window = np.array(prev_window) + np.array(dc.window_array)
                else:
                   prev_dc = dc
                   prev_window = np.array(dc.window_array)

        def verify_same_length_windows():
            prev_length = None
            for dc in self.demand_charges:
                if prev_length is not None:
                    assert len(dc.window_array) == prev_length, f"Demand charge windows are not all the same length"
                    prev_length = len(dc.window_array)
                else:
                    prev_length = len(dc.window_array)

                assert prev_length == model.number_of_intervals, f"Demand charge {dc} windows do not match optimiser time periods."

        def verify_min_demand():
            if self.import_demand:
                for dc in self.demand_charges:
                    if dc.min_demand < 0:
                        raise ConfigurationError('Enter min demand using positive load convention (ie positive number)')
            elif self.export_demand:
                for dc in self.demand_charges:
                    if dc.min_demand > 0:
                        raise ConfigurationError('Enter min demand using positive load convention (ie negative number)')
            else:
                raise ConfigurationError('Demand tariff must be either import or export.')

        verify_non_overlapping()
        verify_same_length_windows()
        verify_min_demand()

    def create_params(self, model):
        for dc in self.demand_charges:
            dc.create_params(model)

    def create_vars(self, model):
        for dc in self.demand_charges:
            if self.import_demand is True:
                setattr(model, dc.max_demand_val, en.Var(dc.reset_index, initialize=0, domain=en.NonNegativeReals))
            elif self.export_demand is True:
                setattr(model, dc.max_demand_val, en.Var(dc.reset_index, initialize=0, domain=en.NonPositiveReals))

    def apply_constraints(self, model):
        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

        for dc in self.demand_charges:
            if self.import_demand is True:
                def max_import_demand_rule(model, p, t, r):
                    return getattr(model, dc.max_demand_val)[r] >= \
                           (getattr(model, self.component.pos)[p, t] - dc.min_demand) * getattr(model, dc.window_active)[p, r, t]

                setattr(model, f"cons_{dc.max_demand_val}_max_demand",
                        en.Constraint(model.Expansion, model.Time, dc.reset_index, rule=max_import_demand_rule))
            elif self.export_demand is True:
                def max_export_demand_rule(model, p, t, r):
                    return getattr(model, dc.max_demand_val)[r] <= \
                           (getattr(model, self.component.neg)[p, t] - dc.min_demand) * getattr(model, dc.window_active)[p, r, t]

                setattr(model, f"cons_{dc.max_demand_val}_max_export_demand",
                        en.Constraint(model.Expansion, model.Time, dc.reset_index, rule=max_export_demand_rule))

    def objective_expr(self, model):
        objective = 0
        for dc in self.demand_charges:
            if self.import_demand:
                objective += sum(getattr(model, dc.max_demand_val)[r] * dc.rate for r in dc.reset_index)
            elif self.export_demand:
                objective += sum(getattr(model, dc.max_demand_val)[r] * dc.rate * -1 for r in dc.reset_index)

        return objective

class DemandCharge(BaseModel):
    """ A demand charge is a rate that applies to the maximum demand over one or many specified time windows."""
    uid: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: Optional[str] = None
    rate: PositiveFloat
    min_demand: float = 0.0
    window_array: Union[ArrayType, List]
    reset_period_length: int = None

    window_active: Optional[str]
    num_reset_periods: Optional[int]
    reset_index: Optional[Any]
    max_demand_val: Optional[str]

    @root_validator()
    def assign_var_names(cls, values):
        name = values.get('name')
        window_array = values.get('window_array')
        reset_period_length = values.get('reset_period_length')
        if reset_period_length is None:
            temp_reset_period_len = len(window_array)
        else:
            temp_reset_period_len = reset_period_length
        if len(window_array) % temp_reset_period_len != 0:
            raise ValueError(f"Demand charge reset period length should be a multiple of the window array length.")
        values['num_reset_periods'] = len(window_array)//temp_reset_period_len
        values['reset_index'] = en.RangeSet(0, values.get('num_reset_periods')-1)
        values['reset_period_length'] = temp_reset_period_len
        return values

    def __init__(self, **data):
        super().__init__(**data)
        if self.name is None:
            self.name = 'dc_' + str(self.uid)
        self.max_demand_val = 'max_demand_' + self.name
        self.window_active = 'window_active_' + self.name

    def create_params(self, model):
        #todo make this work for multiple planning intervals, make it less hacky:)
        initial_window_val = {}
        x = np.identity(self.num_reset_periods)
        i = 0
        for row in x:
            period_window = row.repeat(self.reset_period_length)
            new_window = np.array(self.window_array)*np.array(period_window)
            for j in range(len(new_window)):
                initial_window_val[(0, i, j)] = new_window[j]
            i += 1

        setattr(model, self.window_active, en.Param(model.Expansion, self.reset_index, model.Time,
                                                    initialize=initial_window_val, domain=en.Binary))

    def get_objective_total(self, optimiser):
        expr = optimiser.values(self.max_demand_val)*self.rate
        return sum(expr)

class ImportDemandTariffObjective(DemandTariffObjective):
    import_demand = True
    export_demand = False

class ExportDemandTariffObjective(DemandTariffObjective):
    import_demand = False
    export_demand = True
