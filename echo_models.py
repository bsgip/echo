import uuid
from networkx import Graph
import pyomo.environ as en
from configuration import Units, Flows, FlowConstraint, OptimisationType, HubNodeRule
from constants import minutes_per_hour, positive_variable_component, negative_variable_component


class OptimisationGraph(Graph):

    def __init__(self):
        super(OptimisationGraph, self).__init__()
        self.asset_obj = dict()
        self.hub_obj = dict()
        self.edge_obj = dict()

    def add_asset(self, asset_obj):
        self.add_node(asset_obj.uid)
        self.asset_obj[asset_obj.uid] = asset_obj

    def add_hub(self, hub_obj):
        self.add_node(hub_obj.uid)
        self.hub_obj[hub_obj.uid] = hub_obj

    def connect_asset_to_hub(self, hub_obj, asset_obj):
        self.add_edge(hub_obj.uid, asset_obj.uid)
        self.edge_obj[uuid.uuid4()] = (hub_obj, asset_obj)


class ConfigurationError(Exception):
    pass

class Node(object):
    def __init__(self):
        self.uid = uuid.uuid4()
        self.units = Units.NA  # Used to ensure that common units are being optimised over at points of interconnection
        self.opt_type = OptimisationType.NA  # Is this a decision variable or a fixed parameter
        self.initial_value = 0
        self.node_name = 'node_' + str(self.uid)

        # Used to define the nature of import / export directions and constraints
        self.flows = Flows.NA  # What flow directions are possible (import, export, both)
        self.import_constraint = FlowConstraint.NA
        self.import_constraint_value = None
        self.export_constraint = FlowConstraint.NA
        self.export_constraint_value = None

        # Details about any tariffs and incentives
        self.has_tariff = False
        self.tariff = None

    def verify_node(self):
        """ Used to verify that a port has been setup appropriately"""
        if self.flows is Flows.NA:
            raise ConfigurationError("The flows value cannot be set to a value of NA.")

        if self.flows is (Flows.Import or Flows.Both):
            if self.import_constraint is FlowConstraint.NA:
                raise ConfigurationError("The Import FlowConstraint cannot be set to a value of NA.")
            if self.import_constraint is not FlowConstraint.NoConstraint and self.import_constraint_value is None:
                raise ConfigurationError("The Import flow constraint value cannot be set to None when an Import constraint exists.")

        if self.flows is (Flows.Export or Flows.Both):
            if self.export_constraint is FlowConstraint.NA:
                raise ConfigurationError("The Export FlowConstraint cannot be set to a value of NA.")
            if self.export_constraint is not FlowConstraint.NoConstraint and self.export_constraint_value is None:
                raise ConfigurationError("The Export flow constraint value cannot be set to None when an Export constraint exists.")

        if self.opt_type is OptimisationType.NA:
            raise ConfigurationError(
                "The Optimisation Type has to be configured before instantiation.")

        if self.units is Units.NA:
            raise ConfigurationError(
                "The Units parameter has to be configured before instantiation.")

    def initialise_node(self, model):
        domain = en.Reals
        if self.flows is Flows.Export:
            domain = en.NonPositiveReals
        elif self.flows is Flows.Import:
            domain = en.NonNegativeReals

        if self.opt_type is OptimisationType.Parameter:
            setattr(model, self.node_name, en.Param(model.Time, initialize=self.initial_value, domain=domain))

        if self.opt_type is OptimisationType.Variable:
            setattr(model, self.node_name, en.Var(model.Time, initialize=self.initial_value, domain=domain))

            # Divide the variable into a positive and negative flow.
            # This is only applicable for variables, not for parameters which are fixed.
            # By splitting the variables, we are able to use either the positive
            # or negative component.
            # This is only calculated for decision variables because it cannot be calculated for parameters.
            self.positive_node_component = positive_variable_component + self.node_name
            self.negative_node_component = negative_variable_component + self.node_name
            setattr(model, self.positive_node_component, en.Var(model.Time, initialize=0, domain=en.NonNegativeReals))
            setattr(model, self.negative_node_component, en.Var(model.Time, initialize=0, domain=en.NonPositiveReals))
            con_rule = self.factory_pos_neg_flows(self.node_name, self.positive_node_component, self.negative_node_component)
            con_name = positive_variable_component + negative_variable_component + self.node_name
            setattr(model, con_name, en.Constraint(model.Time, rule=con_rule))

    def factory_pos_neg_flows(self, var_name, pos_name, neg_name):
        def constraint(model, time_interval):
            return getattr(model, var_name)[time_interval] == getattr(model, pos_name)[time_interval] + \
                   getattr(model, neg_name)[time_interval]

        return constraint

    def add_initial_value(self, initial_value):
        self.initial_value = initial_value

    def add_objective(self, model):
        objective = 0
        if self.has_tariff:
            model.import_tariff = en.Param(model.Time, initialize=self.tariff.import_tariff)
            model.export_tariff = en.Param(model.Time, initialize=self.tariff.export_tariff)
            objective += sum(
                model.import_tariff[i] * getattr(model, 'positive_' + self.node_name)[i] +
                model.export_tariff[i] * getattr(model, 'negative_' + self.node_name)[i]
                for i in model.Time)
        return objective


class Hub(object):
    """Hubs are collections of one or more ports that can include non-trivial relationships between the ports,
    this allows transformations to be implemented"""

    def __init__(self):
        self.uid = uuid.uuid4()
        self.hub_rule = HubNodeRule.NA
        self.nodes = {}  # 'port_name: port'
        self.named_nodes = []  # A list of nodes that are expected to be attached
        # Included to ensure that nodes can be dynamically populated or can have 'fixed' ports used to implement
        # particular assets like transformations.
        self.allow_dynamic_nodes = False

    def add_dynamic_node(self):
        pass

    def add_named_node(self):
        pass

# High Level definitions of asset types
class Source(Node):
    """ A source of a commodity. """
    def __init__(self):
        super(Source, self).__init__()
        self.flows = Flows.Export
        self.opt_type = OptimisationType.Parameter


class Sink(Node):
    """ The sink for a commodity. """
    def __init__(self):
        super(Sink, self).__init__()
        self.flows = Flows.Import
        self.opt_type = OptimisationType.Parameter


class Storage(Node):
    """ Storage for a commodity. """
    def __init__(self,
                 max_capacity,
                 depth_of_discharge_limit,
                 charging_power_limit,
                 discharging_power_limit,
                 charging_efficiency,
                 discharging_efficiency,
                 throughput_cost,
                 initial_state_of_charge=0
                 ):
        super(Storage, self).__init__()
        self.storage = True
        self.flows = Flows.Both
        self.opt_type = OptimisationType.Variable
        self.import_constraint = FlowConstraint.Fixed
        self.import_constraint_value = charging_power_limit
        self.export_constraint = FlowConstraint.Fixed
        self.export_constraint_value = discharging_power_limit
        # Energy Storage Characteristics
        self.max_capacity = max_capacity
        self.depth_of_discharge_limit = depth_of_discharge_limit
        # DC Power Characteristics
        self.charging_power_limit = charging_power_limit
        self.discharging_power_limit = discharging_power_limit
        self.charging_efficiency = charging_efficiency
        self.discharging_efficiency = discharging_efficiency
        # Derived Values
        self.capacity = self.calc_capacity()
        # Throughput Cost
        # ToDo - Should this be related to the Levelised cost of energy (LCOE)
        self.throughput_cost = throughput_cost
        # Initial state of charge
        self.initial_state_of_charge = initial_state_of_charge
        self.interval_duration = 15

    def initialise_node(self, model):
        super(Storage, self).initialise_node(model)
        SOC_name = 'storage_soc_' + self.node_name
        self.storage_soc_value = SOC_name
        setattr(model, SOC_name,
                en.Var(model.Time, initialize=0, bounds=(0, self.capacity)))

        # # The battery charging efficiency
        eta_chg = self.charging_efficiency
        # # The battery discharging efficiency
        eta_dischg = self.discharging_efficiency
        # # The battery charge power limit
        charging_limit = self.charging_power_limit * (self.interval_duration / minutes_per_hour)
        # # The battery discharge power limit
        discharging_limit = self.discharging_power_limit * (self.interval_duration / minutes_per_hour)
        # # The throughput cost for the energy storage
        throughput_cost = self.throughput_cost

        # Enforce the charging rate limit
        def storage_charge_rate_limit(model, time_interval):
            return getattr(model, self.node_name)[time_interval] <= charging_limit

        # Enforce the discharge rate limit
        def storage_discharge_rate_limit(model, time_interval):
            return getattr(model, self.node_name)[time_interval] >= discharging_limit

        con_name = 'charge_limit_' + self.node_name
        con_name2 = 'discharge_limit_' + self.node_name

        setattr(model, con_name, en.Constraint(model.Time, rule=storage_charge_rate_limit))
        setattr(model, con_name2, en.Constraint(model.Time, rule=storage_discharge_rate_limit))

        initial_state_of_charge = self.initial_state_of_charge

        def SOC_rule(model, time_interval):
            if time_interval == 0:
                return getattr(model, SOC_name)[time_interval] \
                       == initial_state_of_charge + getattr(model, self.node_name)[time_interval]
            else:
                return getattr(model, SOC_name)[time_interval] \
                       == getattr(model, SOC_name)[time_interval - 1] + getattr(model, self.node_name)[
                           time_interval]

        soc_con = 'soc_limit_' + self.node_name
        setattr(model, soc_con, en.Constraint(model.Time, rule=SOC_rule))


    def calc_capacity(self):
        capacity = self.max_capacity
        if 0 <= self.depth_of_discharge_limit <= 1:
            # Assume we have a decimal representation of the dod limit
            capacity *= (1 - self.depth_of_discharge_limit)
        elif 1 < self.depth_of_discharge_limit <= 100:
            # Assume we have a percentage representation of the dod limit
            capacity *= (1 - self.depth_of_discharge_limit / 100.0)
        else:
            raise ConfigurationError('The DoD limit should be between 0 - 100')

        return capacity

    def add_objective(self, model):
        super(Storage, self).add_objective(model)

        objective = 0
        objective += sum(getattr(model, 'positive_' + self.node_name)[i] - getattr(model, 'negative_' + self.node_name)[i]
                        for i in model.Time) * self.throughput_cost / 2.0

        objective += sum(getattr(model, 'positive_' + self.node_name)[i] * getattr(model, 'positive_' + self.node_name)[i] + \
                         getattr(model, 'negative_' + self.node_name)[i] * getattr(model, 'negative_' + self.node_name)[i]
                        for i in model.Time) * 0.0000001
        return objective

class FlexibleAsset(Node):

    def __init__(self):
        super(FlexibleAsset, self).__init__()
        self.flows = Flows.Both
        self.opt_type = OptimisationType.Variable
        self.units = Units.KW


class ElectricalDemand(Sink):

    def __init__(self):
        super(ElectricalDemand, self).__init__()
        self.units = Units.KW
        self.import_constraint = FlowConstraint.NoConstraint

    def add_demand_profile(self, electrical_demand):
        self.add_initial_value(electrical_demand)

class ElectricalGeneration(Source):

    def __init__(self):
        super(ElectricalGeneration, self).__init__()
        self.units = Units.KW
        self.export_constraint = FlowConstraint.NoConstraint

    def add_generation_profile(self, generation):
        self.add_initial_value(generation)
        

class ElectricalStorage(Storage):
    def __init__(self,
                 max_capacity,
                 depth_of_discharge_limit,
                 charging_power_limit,
                 discharging_power_limit,
                 charging_efficiency,
                 discharging_efficiency,
                 throughput_cost,
                 initial_state_of_charge=0
                 ):
         super(ElectricalStorage, self).__init__(max_capacity,
                 depth_of_discharge_limit,
                 charging_power_limit,
                 discharging_power_limit,
                 charging_efficiency,
                 discharging_efficiency,
                 throughput_cost,
                 initial_state_of_charge=0)
         self.units = Units.KW


class ElectricalHub(Hub):
    """A hub that implements a kirchoff / tellegen constraint requiring that electrical power is conserved"""
    def __init__(self):
        super(ElectricalHub, self).__init__()
        self.units = Units.KW

class BulkElectricalGrid(FlexibleAsset):

    def __init__(self):
        super(BulkElectricalGrid, self).__init__()
        self.units = Units.KW