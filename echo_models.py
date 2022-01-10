import uuid
import warnings

import networkx as nx
from networkx import Graph
import pyomo.environ as en
from configuration import Units, Flows, FlowConstraint, OptimisationType, HubNodeRule, TransformationRule, ExpansionType
from constants import minutes_per_hour, positive_variable_component, negative_variable_component
import numpy as np


class OptimisationGraph(Graph):

    def __init__(self):
        super(OptimisationGraph, self).__init__()
        self.port_obj = dict()
        self.hub_obj = dict()
        self.edge_obj = dict()
        self.asset_expansion_obj = dict()
        self.capacity_exp_obj = dict()
        self.hub_edges = dict()

    def add_port(self, port_obj):
        self.add_node(port_obj.uid)
        self.port_obj[port_obj.uid] = port_obj
        if port_obj.capacity_expansion is True:
            self.capacity_exp_obj[port_obj.uid] = port_obj

    def add_hub(self, hub_obj):
        # self.add_node(hub_obj.uid)
        self.hub_obj[hub_obj.uid] = hub_obj
        for _, port in hub_obj.ports.items():  # Add any ports within the hub
            self.add_port(port)

    def add_edge_obj(self, edge):
        obj1 = edge.vertices[0]
        obj2 = edge.vertices[1]
        self.add_edge(obj1.uid, obj2.uid)
        edge_name = uuid.uuid4()
        self.edge_obj[edge_name] = edge

    def add_expansions(self, expansion_periods):
        hubs_to_add = []
        for _, hub in self.hub_obj.items():
            if hub.expansion_planning:  # Check if the hub has expansion planning
                for i in range(0, self.global_storage_exp_con):  # Todo decide if this is the right approach
                    h = Hub()
                    h.expansion_asset = True  # Designate new asset as an expansion asset
                    if hub.storage_planning is True:  # Check if hub has storage expansion planning
                        s = ElectricalStorage(max_capacity=150.0,
                                              depth_of_discharge_limit=0,
                                              charging_power_limit=5.0,
                                              discharging_power_limit=-5.0,
                                              charging_efficiency=1,
                                              discharging_efficiency=1,
                                              throughput_cost=0.018,
                                              initial_state_of_charge=0)
                        h.expansion_asset_type = ExpansionType.Storage
                        s.fixed_storage_capacity = False
                        s.existing_port = False
                    elif hub.generator_planning is True:
                        # ToDo
                        s = ElectricalGeneration()
                        constant_gen = np.array(([1.0] * 96)) * -1
                        gen1 = {}
                        for ep in range(0, expansion_periods):
                            for j, _ in enumerate(constant_gen):
                                gen1[(ep, j)] = constant_gen[i]
                        s.add_generation_profile(gen1)
                        h.expansion_asset_type = ExpansionType.Generation
                        s.fixed_capacity = True
                        s.existing_port = False
                    else:
                        raise ConfigurationError('Expansion planning is on but no expansion type is set to True.')
                    # Connect new port to new hub
                    h.ports['exp_' + str(i)] = s
                    s.lifetime = 2
                    s.capex = hub.storage_planning_capex
                    # Make a new port on the expansion hub
                    p = ElectricalPort()
                    port_name = 'exp_' + str(i) + '_' + hub.hub_name
                    hub.ports[port_name] = p
                    hub.exp_port_names.append(port_name)
                    # Create edge object
                    expansion_link = Edge()
                    expansion_link.add_vertices(p, s)
                    self.add_edge_obj(expansion_link)
                    self.add_port(s)
                    self.add_port(p)
                    self.asset_expansion_obj[h.uid] = h
                    hubs_to_add.append(h)  # Keep track of the new hubs so we can add them to graph outside this loop
        for i in hubs_to_add:
            self.add_hub(i)

    def lookup_hub_from_port(self, port):
        """ Returns hub that a specified port belongs to, raises error if port has no corresponding hub."""
        for _, h in self.hub_obj.items():
            for _, p in h.ports.items():
                if port == p:
                    return h
        raise ConfigurationError('Port is not connected to any hub.')

    def lookup_edges_from_port(self, port):
        """ Returns edge containing the specified port, raises an error if no edge exists."""
        for _, e in self.edge_obj.items():
            p1 = e.vertices[0]
            p2 = e.vertices[1]
            if (port == p1) or (port == p2):
                return e
        raise ConfigurationError('Port is not part of any edge object.')


class ConfigurationError(Exception):
    pass


class Port(object):
    def __init__(self):
        self.uid = uuid.uuid4()
        self.units = Units.NA  # Used to ensure that common units are being optimised over at points of interconnection
        self.opt_type = OptimisationType.NA  # Is this a decision variable or a fixed parameter
        self.initial_value = 0
        self.port_name = 'port_' + str(self.uid)
        # Used to define the nature of import / export directions and constraints
        self.flows = Flows.NA  # What flow directions are possible (import, export, both)
        self.import_constraint = FlowConstraint.NA
        self.import_constraint_value = None
        self.export_constraint = FlowConstraint.NA
        self.export_constraint_value = None
        # Details about any tariffs and incentives
        self.has_tariff = False
        self.tariff = None
        self.initial_state = 1  # 1 = on, 0 = off
        self.lifetime = 100  # in planning period units
        self.existing_port = True  # Existing assets are forced to be installed in the first planning period
        self.capex = 0
        self.fixed_opex = 0
        self.var_opex = 0
        self.replacement_capex = 0
        self.capacity_expansion = False

    def verify_port(self):
        """ Used to verify that a port has been set up appropriately"""
        if self.flows is Flows.NA:
            raise ConfigurationError("The flows value cannot be set to a value of NA.")

        if (self.flows is Flows.Import) or (self.flows is Flows.Both):
            if self.import_constraint is FlowConstraint.NA:
                raise ConfigurationError("The Import FlowConstraint cannot be set to a value of NA.")
            if self.import_constraint is FlowConstraint.Fixed and self.import_constraint_value is None:
                raise ConfigurationError(
                    "The Import flow constraint value cannot be set to None when an Import constraint exists.")

        if (self.flows is Flows.Export) or (self.flows is Flows.Both):
            if self.export_constraint is FlowConstraint.NA:
                raise ConfigurationError("The Export FlowConstraint cannot be set to a value of NA.")
            if self.export_constraint is FlowConstraint.Fixed and self.export_constraint_value is None:
                raise ConfigurationError(
                    "The Export flow constraint value cannot be set to None when an Export constraint exists.")

        if self.opt_type is OptimisationType.NA:
            raise ConfigurationError(
                "The Optimisation Type has to be configured before instantiation.")

        if self.units is Units.NA:
            raise ConfigurationError("The Units parameter has to be configured before instantiation.")

        if self.export_constraint_value is not None:
            if self.export_constraint_value > 0:
                raise ConfigurationError('Enter export constraint using positive load convention.')

        if self.import_constraint_value is not None:
            if self.import_constraint_value < 0:
                raise ConfigurationError('Enter import constraint using positive load convention.')

        if self.capacity_expansion is True and self.existing_port is False:
            raise ConfigurationError('Import/export capacity expansion can only be applied to an existing port.')

        if self.capacity_expansion is True and (-self.export_constraint_value != self.import_constraint_value):
            raise ConfigurationError('Capacity expansion can only be applied if import cap = export cap.')

        if self.capacity_expansion is True:
            if (self.export_constraint_value is None) or (self.import_constraint_value is None):
                raise ConfigurationError('Import/export cap cannot be None if capacity expansion is on.')

    def initialise_port(self, model):
        domain = en.Reals
        if self.flows is Flows.Export:
            domain = en.NonPositiveReals
        elif self.flows is Flows.Import:
            domain = en.NonNegativeReals

        if self.opt_type is OptimisationType.Parameter:
            if self.existing_port is True:
                setattr(model, self.port_name,
                        en.Param(model.Expansion, model.Time, initialize=self.initial_value, domain=domain))
            else:
                setattr(model, self.port_name,
                        en.Var(model.Expansion, model.Time, initialize=self.initial_value, domain=domain))

        if self.opt_type is OptimisationType.Variable:
            # Define decision variable for the port value and divide into a positive and negative flow
            setattr(model, self.port_name,
                    en.Var(model.Expansion, model.Time, initialize=self.initial_value, domain=domain))

            self.positive_port_component = positive_variable_component + self.port_name
            self.negative_port_component = negative_variable_component + self.port_name
            setattr(model, self.positive_port_component,
                    en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
            setattr(model, self.negative_port_component,
                    en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonPositiveReals))
            con_rule = self.factory_pos_neg_flows(self.port_name, self.positive_port_component,
                                                  self.negative_port_component)
            con_name = positive_variable_component + negative_variable_component + self.port_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=con_rule))

        # Import/export capacity variables and constraints
        self.cap_add = 'cap_added_' + self.port_name
        if self.capacity_expansion is True:
            setattr(model, self.cap_add, en.Var(model.Expansion, initialize=0, domain=en.NonNegativeReals))
        else:
            setattr(model, self.cap_add, en.Param(model.Expansion, initialize=0))

        self.current_cap = 'current_cap_' + self.port_name
        setattr(model, self.current_cap, en.Var(model.Expansion, initialize=0, domain=en.NonNegativeReals))

        def current_cap_rule(model, p):  # Rule for updating current capacity based on added capacity
            if p == 0:
                return getattr(model, self.current_cap)[p] == self.initial_cap + \
                       getattr(model, self.cap_add)[p]
            else:
                return getattr(model, self.current_cap)[p] == \
                       getattr(model, self.current_cap)[p - 1] + getattr(model, self.cap_add)[p]

        con_name = 'current_cap_con_' + self.port_name
        self.initial_cap = self.import_constraint_value
        if self.import_constraint_value is None:  # ToDo improve this method of setting the initial capacity
            self.initial_cap = model.bigM
        setattr(model, con_name, en.Constraint(model.Expansion, rule=current_cap_rule))

        def cap_rule_1(model, p, t):  # Enforce current capacity on port value
            return getattr(model, self.port_name)[p, t] <= getattr(model, self.current_cap)[p]

        def cap_rule_2(model, p, t):
            return getattr(model, self.port_name)[p, t] >= - getattr(model, self.current_cap)[p]

        con_name = 'flow_con_1_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=cap_rule_1))
        con_name = 'flow_con_2_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=cap_rule_2))

        # On/off decision variable and constraints
        self.active = 'active_' + self.port_name
        setattr(model, self.active, en.Var(model.Expansion, initialize=self.initial_state, domain=en.Binary))

        def on_off_rule1(model, p, t):
            return getattr(model, self.port_name)[p, t] <= getattr(model, self.active)[p] * model.bigM

        def on_off_rule2(model, p, t):
            return getattr(model, self.port_name)[p, t] >= - getattr(model, self.active)[p] * model.bigM

        def on_off_rule_param(model, p, t):
            return getattr(model, self.port_name)[p, t] == self.initial_value[p, t] * getattr(model, self.active)[p]

        if self.opt_type is OptimisationType.Variable:
            con_name = 'on_off_con1_' + self.port_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=on_off_rule1))
            con_name = 'on_off_con2_' + self.port_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=on_off_rule2))
        elif self.opt_type is OptimisationType.Parameter and self.existing_port is False:  # ToDo better way of identifying objects like this
            con_name = 'on_off_con_param_' + self.port_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=on_off_rule_param))

        # Installation decision variable
        self.installed = 'installed_' + self.port_name
        setattr(model, self.installed, en.Var(model.Expansion, initialize=0, domain=en.Binary))

        def install_once_rule(model):  # Constraint: ports can only be installed at most once
            return sum(getattr(model, self.installed)[p] for p in model.Expansion) <= 1

        con_name = 'install_once_' + self.port_name
        setattr(model, con_name, en.Constraint(rule=install_once_rule))

        def existing_port_rule(model, p):  # Existing port constraint: must be installed in first planning period
            if p == 0:
                return getattr(model, self.installed)[p] == 1
            else:
                return getattr(model, self.installed)[p] == 0

        if self.existing_port:
            con_name = 'existing_port_' + self.port_name
            setattr(model, con_name, en.Constraint(model.Expansion, rule=existing_port_rule))

        def install_before_run_rule(model, p):  # Constraint: port can't be active before being installed
            if p == 0:
                return getattr(model, self.active)[p] <= getattr(model, self.installed)[p]
            else:
                return getattr(model, self.active)[p] <= \
                       (getattr(model, self.installed)[p] + getattr(model, self.active)[p - 1])

        con_name = 'install_before_run_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=install_before_run_rule))

        # Define retirement, replacement, and lifetime remaining variables
        self.retire = 'retire_' + self.port_name
        setattr(model, self.retire, en.Var(model.Expansion, initialize=0, domain=en.Binary))

        self.replace = 'replace_' + self.port_name
        setattr(model, self.replace, en.Var(model.Expansion, initialize=0, domain=en.Binary))

        self.lifetime_remaining = 'lifetime_remaining_' + self.port_name
        setattr(model, self.lifetime_remaining,
                en.Var(model.Expansion, initialize=self.lifetime, domain=en.NonNegativeReals))

        # Define remaining life in terms of active variable and replacement variable
        def remaining_life_rule(model, p):
            if p == 0:
                return getattr(model, self.lifetime_remaining)[p] == self.lifetime
            else:
                return getattr(model, self.lifetime_remaining)[p] == \
                       getattr(model, self.lifetime_remaining)[p - 1] - \
                       getattr(model, self.active)[p - 1] + \
                       getattr(model, self.replace)[p - 1] * (self.lifetime + 1)

        con_name = 'remaining_life_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=remaining_life_rule))

        def eol_rule1(model, p):  # Big M Constraint: force either retirement or replacement at end of lifetime
            return getattr(model, self.lifetime_remaining)[p] <= \
                   (1 - (getattr(model, self.replace)[p] + getattr(model, self.retire)[p])) * model.bigM

        def eol_rule2(model, p):
            return (1 - (getattr(model, self.replace)[p] + getattr(model, self.retire)[p])) <= \
                   getattr(model, self.lifetime_remaining)[p] * model.bigM

        con_name = 'eol_1_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=eol_rule1))
        con_name = 'eol_2_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=eol_rule2))

    def factory_pos_neg_flows(self, var_name, pos_name, neg_name):
        """ Applies constraint: val = pos + neg """

        def constraint(model, expansion_interval, time_interval):
            return getattr(model, var_name)[expansion_interval, time_interval] == \
                   (getattr(model, pos_name)[expansion_interval, time_interval] +
                    getattr(model, neg_name)[expansion_interval, time_interval])

        return constraint

    def add_initial_value(self, initial_value):
        self.initial_value = initial_value

    def add_objective(self, model):

        objective = 0
        if self.has_tariff:
            import_tariff_name = 'import_tariff_' + self.port_name
            setattr(model, import_tariff_name,
                    en.Param(model.Expansion, model.Time, initialize=self.tariff.import_tariff))

            export_tariff_name = 'export_tariff_' + self.port_name
            setattr(model, export_tariff_name,
                    en.Param(model.Expansion, model.Time, initialize=self.tariff.export_tariff))

            objective += sum(
                getattr(model, import_tariff_name)[p, i] * getattr(model, self.positive_port_component)[p, i] *
                getattr(model, model.dr)[p] +
                getattr(model, export_tariff_name)[p, i] * getattr(model, self.negative_port_component)[p, i] *
                getattr(model, model.dr)[p]
                for p in model.Expansion for i in model.Time)

        if self.opt_type is OptimisationType.Variable:  # To ensure either positive or negative component = 0
            objective += sum(
                (getattr(model, self.positive_port_component)[p, i] - getattr(model, self.negative_port_component)[
                    p, i]) for p in model.Expansion for i in model.Time) * 0.00000001

        # Installation capex
        objective += sum(getattr(model, self.installed)[p] * getattr(model, model.dr)[p]
                         for p in model.Expansion) * self.capex

        # Replacement capex
        objective += sum(getattr(model, self.replace)[p] * getattr(model, model.dr)[p]
                         for p in model.Expansion) * self.replacement_capex

        # Fixed opex
        objective += sum(getattr(model, self.active)[p] * getattr(model, model.dr)[p]
                         for p in model.Expansion) * self.fixed_opex

        # Variable opex
        if self.opt_type is OptimisationType.Variable:  # ToDo improve way of identifying ports with variable opex
            objective += sum(
                (getattr(model, self.positive_port_component)[p, t] - getattr(model, self.negative_port_component)[
                    p, t]) *
                getattr(model, model.dr)[p] for p in model.Expansion for t in model.Time) * self.var_opex

        return objective


class Hub(object):
    """Hubs are collections of one or more ports that can include non-trivial relationships between the ports,
    this allows transformations to be implemented"""

    def __init__(self):
        self.uid = uuid.uuid4()
        self.hub_rule = HubNodeRule.NA
        self.ports = {}  # 'port_name: port'
        self.named_ports = []  # A list of ports that are expected to be attached
        # Included to ensure that ports can be dynamically populated or can have 'fixed' ports used to implement
        # particular assets like transformations.
        self.allow_dynamic_ports = False
        self.dynamic_ports = []
        self.hub_name = 'hub_' + str(self.uid)
        self.transformation = {}
        # Expansion planning attributes
        self.expansion_planning = False  # For identifying hubs which we can connect new expansion assets to
        self.storage_planning = False
        self.generator_planning = False
        self.storage_planning_capex = 0
        # Keep list of ports that connect to expansion assets, to more easily retrieve info after optimisation
        # Only applicable for hubs that have expansion planning
        self.exp_port_names = []
        # For identifying hubs (assets) that ARE potential expansions
        self.expansion_asset = False
        self.expansion_asset_type = ExpansionType.NA
        self.lifetime = 10  # ToDo - link to expansion period timescale

    def add_dynamic_port(self, port_name):
        if self.allow_dynamic_ports is False:
            raise ConfigurationError("Hub does not permit dynamic ports.")

        # Creates and adds port to the hub, as well as adding it to the list of dynamic ports
        dn = Port()
        self.ports[str(port_name)] = dn
        self.dynamic_ports.append([str(port_name)])

    def add_named_port(self, port_name):
        # Creates and adds port to the hub, as well as adding it to the list of named ports
        nn = Port()
        self.ports[str(port_name)] = nn
        self.named_ports.append([str(port_name)])

    def add_transformation(self, tr_obj):
        self.transformation[uuid.uuid4()] = tr_obj

    def verify_hub(self):
        """ Used to verify that a hub has been setup appropriately"""

        if self.expansion_planning is True and self.hub_rule is not (HubNodeRule.Tellegen or HubNodeRule.Sum):
            raise ConfigurationError('Expansion planning can only be applied to Tellegen hubs.')

        if self.hub_rule is HubNodeRule.NA and len(self.ports) > 1:
            raise ConfigurationError('HubNodeRule cannot be NA if hub has more than one port.')

        if self.expansion_planning is True and self.expansion_asset is True:
            raise ConfigurationError(
                'A hub cannot both support expansion planning and be an expansion asset.')

        if self.hub_rule == HubNodeRule.Transform:
            if not self.transformation:
                raise ConfigurationError("Hub has Transform rule but Transformation object has not been added to hub.")

        if self.expansion_planning is True and (self.storage_planning is False and self.generator_planning is False):
            raise ConfigurationError('Expansion planning is on but no expansion type is set to True.')

        if self.expansion_asset is True and self.expansion_asset_type is ExpansionType.NA:
            raise ConfigurationError("Expansion asset type cannot be NA.")

    def initialise_hub(self, model):
        var_name = 'installed_hub_' + self.hub_name
        self.hub_installed = var_name
        setattr(model, self.hub_installed,
                en.Var(model.Expansion, initialize=0, domain=en.Binary))

        def installed_hub_rule1(model, p):  # BigM constraints: hub is installed if  all ports in hub are installed
            num_ports = 0
            a = 0
            for _, port in self.ports.items():
                a += getattr(model, port.installed)[p]
                num_ports += 1
            return (num_ports - a) <= (1 - getattr(model, self.hub_installed)[p]) * model.bigM

        def installed_hub_rule2(model, p):
            num_ports = 0
            a = 0
            for _, port in self.ports.items():
                a += getattr(model, port.installed)[p]
                num_ports += 1
            return (num_ports - a) * model.bigM >= (1 - getattr(model, self.hub_installed)[p])

        con_name = 'installed_hub_con1_' + self.hub_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=installed_hub_rule1))
        con_name = 'installed_hub_con2_' + self.hub_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=installed_hub_rule2))


# High Level definitions of asset types
class Source(Port):
    """ A source of a commodity. """

    def __init__(self):
        super(Source, self).__init__()
        self.flows = Flows.Export
        self.opt_type = OptimisationType.Parameter


class Sink(Port):
    """ The sink for a commodity. """

    def __init__(self):
        super(Sink, self).__init__()
        self.flows = Flows.Import
        self.opt_type = OptimisationType.Parameter


class Storage(Port):
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
        self.interval_duration = 15  # ToDo update so this relates to time periods
        self.capex = 0  # in $/unit capacity
        self.fixed_storage_capacity = True

    def initialise_port(self, model):
        super(Storage, self).initialise_port(model)

        self.storage_soc_value = 'storage_soc_' + self.port_name
        setattr(model, self.storage_soc_value,
                en.Var(model.Expansion, model.Time, initialize=0, bounds=(0, self.max_capacity)))  # Actual SOC

        self.optimised_storage_capacity = 'optimised_storage_capacity_' + self.port_name
        if self.fixed_storage_capacity is False:
            setattr(model, self.optimised_storage_capacity, en.Var(initialize=0, domain=en.NonNegativeReals))
        else:
            setattr(model, self.optimised_storage_capacity,
                    en.Param(initialize=self.max_capacity, domain=en.NonNegativeReals))

        def cap_limit(model, expansion_interval, time_interval):  # Ensure SOC is within max capacity
            return getattr(model, self.storage_soc_value)[expansion_interval, time_interval] <= \
                   getattr(model, self.optimised_storage_capacity)

        cap_limit_con_name = 'cap_limit_cons_' + self.port_name
        setattr(model, cap_limit_con_name, en.Constraint(model.Expansion, model.Time, rule=cap_limit))

        # # The battery charging efficiency
        eta_chg = self.charging_efficiency
        # # The battery discharging efficiency
        eta_dischg = self.discharging_efficiency
        charging_limit = self.charging_power_limit * (self.interval_duration / minutes_per_hour)
        discharging_limit = self.discharging_power_limit * (self.interval_duration / minutes_per_hour)

        # Enforce the charging rate limit
        def storage_charge_rate_limit(model, expansion_interval, time_interval):
            return getattr(model, self.port_name)[expansion_interval, time_interval] <= charging_limit

        # Enforce the discharge rate limit
        def storage_discharge_rate_limit(model, expansion_interval, time_interval):
            return getattr(model, self.port_name)[expansion_interval, time_interval] >= discharging_limit

        con_name = 'charge_limit_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=storage_charge_rate_limit))
        con_name = 'discharge_limit_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=storage_discharge_rate_limit))

        # Apply SOC constraint
        def SOC_rule(model, p, t):
            if t == 0:
                return getattr(model, self.storage_soc_value)[p, t] \
                       == self.initial_state_of_charge + getattr(model, self.port_name)[p, t]
            else:
                return getattr(model, self.storage_soc_value)[p, t] \
                       == getattr(model, self.storage_soc_value)[p, t - 1] + getattr(model, self.port_name)[p, t]

        soc_con = 'soc_limit_' + self.port_name
        setattr(model, soc_con, en.Constraint(model.Expansion, model.Time, rule=SOC_rule))

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

        objective += sum(
            (getattr(model, self.positive_port_component)[p, t] - getattr(model, self.negative_port_component)[p, t]) *
            getattr(model, model.dr)[p] for p in model.Expansion for t in model.Time) * self.throughput_cost / 2.0

        objective += sum(
            getattr(model, self.positive_port_component)[p, t] * getattr(model, self.positive_port_component)[p, t] + \
            getattr(model, self.negative_port_component)[p, t] * getattr(model, self.negative_port_component)[p, t]
            for p in model.Expansion for t in model.Time) * 0.0000001

        # Storage capex
        objective += getattr(model, self.optimised_storage_capacity) * self.capex

        return objective


class FlexiblePort(Port):

    def __init__(self):
        super(FlexiblePort, self).__init__()
        self.flows = Flows.Both
        self.import_constraint = FlowConstraint.NoConstraint
        self.export_constraint = FlowConstraint.NoConstraint
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
    """A hub that implements a Kirchoff / Tellegen constraint requiring that electrical power is conserved"""

    def __init__(self):
        super(ElectricalHub, self).__init__()
        self.units = Units.KW


class Tariff(object):

    def __init__(self):
        self.import_tariff = None
        self.export_tariff = None

    def add_tariff_profile_import(self, tariff):
        self.import_tariff = tariff

    def add_tariff_profile_export(self, tariff):
        self.export_tariff = tariff


class ElectricalPort(Port):

    def __init__(self):
        super(ElectricalPort, self).__init__()
        self.flows = Flows.Both
        self.import_constraint = FlowConstraint.NoConstraint
        self.export_constraint = FlowConstraint.NoConstraint
        self.opt_type = OptimisationType.Variable
        self.units = Units.KW


class CarbonPort(Port):

    def __init__(self):
        super(CarbonPort, self).__init__()
        self.flows = Flows.Export
        self.import_constraint = FlowConstraint.NoConstraint
        self.export_constraint = FlowConstraint.NoConstraint
        self.opt_type = OptimisationType.Variable
        self.units = Units.CO


class Edge(object):

    def __init__(self):
        self.uid = uuid.uuid4()
        self.edge_name = 'edge_' + str(self.uid)
        self.units = Units.NA  # Used to ensure that common units are being optimised over at points of interconnection
        self.opt_type = OptimisationType.NA  # Is this a decision variable or a fixed parameter
        self.has_tariff = False
        self.tariff = None
        self.initial_state = 1  # 1 = on, 0 = off
        self.initial_edge_capacity = 5000000
        self.expansion_planning = False
        self.expansion_asset = False
        self.expansion_asset_type = ExpansionType.Edge
        self.capex = 0
        self.vertices = None

    def add_vertices(self, obj1, obj2):
        self.vertices = (obj1, obj2)

    def verify_edge(self, model):
        pass

    def initialise_edge(self, model):
        port1 = self.vertices[0]
        port2 = self.vertices[1]
        con_rule1 = self.factory_constraint_edge_builder(port1.port_name, port2.port_name)
        con_name = 'edge_con_' + port1.port_name + '_' + port2.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=con_rule1))

        # Apply edge capacity constraint on one of the edge vertices
        if port1.opt_type is OptimisationType.Parameter:  # Choose edge vertex that is not a parameter
            selected_port = port2
        else:
            selected_port = port1

        self.cap_add = 'cap_add_' + self.edge_name
        if self.expansion_planning is False:
            setattr(model, self.cap_add, en.Param(model.Expansion, initialize=0, domain=en.NonNegativeReals))
        else:
            setattr(model, self.cap_add, en.Var(model.Expansion, initialize=0, domain=en.NonNegativeReals))

        self.current_cap = 'current_cap_' + self.edge_name
        setattr(model, self.current_cap, en.Var(model.Expansion, initialize=0, domain=en.NonNegativeReals))

        def current_cap_rule(model, p):
            if p == 0:
                return getattr(model, self.current_cap)[p] == self.initial_edge_capacity + getattr(model, self.cap_add)[
                    p]
            else:
                return getattr(model, self.current_cap)[p] == \
                       getattr(model, self.current_cap)[p - 1] + getattr(model, self.cap_add)[p]

        con_name = 'current_cap_con_' + self.edge_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=current_cap_rule))

        def cap_rule_1(model, p, t):
            return getattr(model, selected_port.port_name)[p, t] <= getattr(model, self.current_cap)[p]

        def cap_rule_2(model, p, t):
            return getattr(model, selected_port.port_name)[p, t] >= - getattr(model, self.current_cap)[p]

        con_name = 'flow_con_1_' + self.edge_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=cap_rule_1))
        con_name = 'flow_con_2_' + self.edge_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=cap_rule_2))

    def factory_constraint_edge_builder(self, obj1, obj2):

        def constraint(model, expansion_interval, time_interval):
            return getattr(model, obj1)[expansion_interval, time_interval] + \
                   getattr(model, obj2)[expansion_interval, time_interval] == 0

        return constraint

    def add_objective(self, model):
        objective = 0

        # Edge expansion capex
        objective += sum(
            getattr(model, self.cap_add)[p] * getattr(model, model.dr)[p] for p in model.Expansion) * self.capex

        return objective

    def add_initial_edge_capacity(self, initial_capacity):
        self.initial_edge_capacity = initial_capacity


class Transform(object):
    """ A transform carries a generic linear hub transformation."""

    def __init__(self):
        self.rhs = 0
        self.lhs = {}
        self.rule = {}
        pass

    def add_rhs(self, val):
        self.rhs = val

    def add_lhs(self, var, weight, rule=TransformationRule.Both):
        self.lhs[var] = weight
        self.rule[var] = rule  # For applying transformation to pos/neg part of a variable
