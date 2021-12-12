import uuid
import warnings

from networkx import Graph
import pyomo.environ as en
from configuration import Units, Flows, FlowConstraint, OptimisationType, HubNodeRule, TransformationRule
from constants import minutes_per_hour, positive_variable_component, negative_variable_component


class OptimisationGraph(Graph):

    def __init__(self):
        super(OptimisationGraph, self).__init__()
        self.asset_obj = dict()
        self.hub_obj = dict()
        self.edge_obj = dict()
        self.expansion_obj = dict()

    def add_asset(self, asset_obj):
        if type(asset_obj) == list:
            for asset in asset_obj:
                self.add_node(asset.uid)
                self.asset_obj[asset.uid] = asset
        else:
            self.add_node(asset_obj.uid)
            self.asset_obj[asset_obj.uid] = asset_obj

    def add_hub(self, hub_obj):
        # Add Hub
        self.add_node(hub_obj.uid)
        self.hub_obj[hub_obj.uid] = hub_obj
        # Add any nodes within the hub
        for _, node in hub_obj.nodes.items():
            self.add_node(node.uid)
            self.asset_obj[node.uid] = node

    def add_edge_obj(self, edge):
        obj1 = edge.edge_objs[0]
        obj2 = edge.edge_objs[1]
        self.add_edge(obj1.uid, obj2.uid)
        edge_name = uuid.uuid4()
        self.edge_obj[edge_name] = edge

    def connect_asset_to_hub(self, hub, port_name, asset_obj):
        hub_obj = hub.nodes[port_name]
        self.add_edge(hub_obj.uid, asset_obj.uid)
        self.edge_obj[uuid.uuid4()] = (hub_obj, asset_obj)


    def add_expansions(self, expansion_periods):
        hubs_to_add = []
        for _, hub in self.hub_obj.items():
            if hub.expansion_planning:  # Check if the hub has expansion planning
                # TODO - specify which asset types we want to include in the expansion problem, for now just storage
                for i in range(0, expansion_periods):
                    # Create new asset
                    h = Hub()
                    h.expansion = True  # Designate new asset as an expansion asset
                    s = ElectricalStorage(max_capacity=15.0,
                                          depth_of_discharge_limit=0,
                                          charging_power_limit=5.0,
                                          discharging_power_limit=-5.0,
                                          charging_efficiency=1,
                                          discharging_efficiency=1,
                                          throughput_cost=0.018,
                                          initial_state_of_charge=0.0)
                    h.nodes['exp_' + str(i)] = s
                    s.existing_port = False
                    s.lifetime = 2
                    # Add port to existing hub
                    p = Port()
                    p.units = Units.KW
                    port_name = 'exp_' + str(i) + '_' + hub.hub_name
                    hub.nodes[port_name] = p
                    # Create edge object and add it to ES
                    expansionlink = Edge()
                    expansionlink.add_vertices(p, s)
                    self.add_edge_obj(expansionlink)
                    # Add ports to graph
                    self.add_asset([s, p])
                    hubs_to_add.append(h)  # Keep track of the new hubs so we can add them to graph outside this loop
                    self.expansion_obj[h.uid] = h
        for i in hubs_to_add:
            self.add_hub(i)


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
        # ToDo - decide whether costs on flows through nodes should be differentiated from tariffs
        # Details about any tariffs and incentives
        self.has_tariff = False
        self.tariff = None
        self.initial_state = 1  # 1 = on, 0 = off
        self.lifetime = 10
        self.existing_port = False  # To force an asset to be installed in first period

    def verify_node(self):
        """ Used to verify that a port has been setup appropriately"""
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
            raise ConfigurationError(
                "The Units parameter has to be configured before instantiation.")

        if self.export_constraint_value is not None:
            if self.export_constraint_value > 0:
                raise ConfigurationError('Enter export constraint using positive load convention.')

        if self.import_constraint_value is not None:
            if self.import_constraint_value < 0:
                raise ConfigurationError('Enter import constraint using positive load convention.')

    def initialise_node(self, model):
        domain = en.Reals
        if self.flows is Flows.Export:
            domain = en.NonPositiveReals
        elif self.flows is Flows.Import:
            domain = en.NonNegativeReals

        if self.opt_type is OptimisationType.Parameter:
            setattr(model, self.node_name,
                    en.Param(model.Expansion, model.Time, initialize=self.initial_value, domain=domain))

        if self.opt_type is OptimisationType.Variable:

            # Define decision variable for the node value and divide into a positive and negative flow
            setattr(model, self.node_name,
                    en.Var(model.Expansion, model.Time, initialize=self.initial_value, domain=domain))

            self.positive_node_component = positive_variable_component + self.node_name
            self.negative_node_component = negative_variable_component + self.node_name
            setattr(model, self.positive_node_component,
                    en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
            setattr(model, self.negative_node_component,
                    en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonPositiveReals))
            con_rule = self.factory_pos_neg_flows(self.node_name, self.positive_node_component,
                                                  self.negative_node_component)
            con_name = positive_variable_component + negative_variable_component + self.node_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=con_rule))

        # Constraints on import/export
        def import_cap_rule(model, p, t):
            return getattr(model, self.node_name)[p, t] <= getattr(model, self.import_capacity)[p]

        def export_cap_rule(model, p, t):
            return getattr(model, self.node_name)[p, t] >= getattr(model, self.export_capacity)[p]

        if self.import_constraint is FlowConstraint.Fixed:
            self.import_capacity = 'import_cap_' + self.node_name
            setattr(model, self.import_capacity,
                    en.Param(model.Expansion, initialize=self.import_constraint_value, domain=en.NonNegativeReals))
            con_name = 'import_cap_con_' + self.node_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=import_cap_rule))

        if self.export_constraint is FlowConstraint.Fixed:
            self.export_capacity = 'export_cap_' + self.node_name
            setattr(model, self.export_capacity,
                    en.Param(model.Expansion, initialize=self.export_constraint_value, domain=en.NonPositiveReals))
            con_name = 'export_cap_con_' + self.node_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=export_cap_rule))

        # Define a decision variable that turns a port on/off
        self.state_value = 'active_' + self.node_name
        setattr(model, self.state_value, en.Var(model.Expansion, initialize=self.initial_state, domain=en.Binary))

        # Big M Constraint linking on/off variable to node value variable
        def on_off_rule(model, p, t):
            return getattr(model, self.node_name)[p, t] <= \
                   getattr(model, self.state_value)[p] * model.bigM

        con_name2 = 'on_off_con_' + self.node_name
        setattr(model, con_name2, en.Constraint(model.Expansion, model.Time, rule=on_off_rule))

        # Define a decision variable for installing a port
        self.installed = 'installed_' + self.node_name
        setattr(model, self.installed, en.Var(model.Expansion, initialize=0, domain=en.Binary))

        # Ports can only be installed at most once
        def install_once_rule(model):
            return sum(getattr(model, self.installed)[p] for p in model.Expansion) <= 1

        con_name = 'install_once_' + self.node_name
        setattr(model, con_name, en.Constraint(rule=install_once_rule))

        # Constraint for 'existing ports' - forced to be installed in first period
        def existing_port_rule(model, p):
            if p == 0:
                return getattr(model, self.installed)[p] == 1
            else:
                return getattr(model, self.installed)[p] == 0

        if self.existing_port:
            con_name = 'existing_port_' + self.node_name
            setattr(model, con_name, en.Constraint(model.Expansion, rule=existing_port_rule))

        # Can't be on before being installed
        def install_before_run_rule(model, p):
            if p == 0:
                return getattr(model, self.state_value)[p] <= getattr(model, self.installed)[p]
            else:
                return getattr(model, self.state_value)[p] <= \
                       (getattr(model, self.installed)[p] + getattr(model, self.state_value)[p - 1])

        con_name = 'install_before_run_' + self.node_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=install_before_run_rule))

        # Retirement variable
        self.retire = 'retire_' + self.node_name
        setattr(model, self.retire, en.Var(model.Expansion, initialize=0, domain=en.Binary))

        # Replacement variable
        self.replace = 'replace_' + self.node_name
        setattr(model, self.replace, en.Var(model.Expansion, initialize=0, domain=en.Binary))

        # Lifetime remaining variable
        self.lifetime_remaining = 'lifetime_remaining_' + self.node_name
        setattr(model, self.lifetime_remaining, en.Var(model.Expansion, initialize=self.lifetime, domain=en.NonNegativeReals))

        # Define remaining life in terms of state value and replacement variable
        def remaining_life_rule(model, p):
            if p == 0:
                return getattr(model, self.lifetime_remaining)[p] == self.lifetime
            else:
                return getattr(model, self.lifetime_remaining)[p] == \
                       getattr(model, self.lifetime_remaining)[p - 1] - \
                       getattr(model, self.state_value)[p - 1] + \
                       getattr(model, self.replace)[p - 1] * (self.lifetime + 1)

        con_name = 'remaining_life_' + self.node_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=remaining_life_rule))

        # Big M Constraint to force either retirement or replacement at end of lifetime
        def eol_rule1(model, p):
            return getattr(model, self.lifetime_remaining)[p] <= \
                   (1 - (getattr(model, self.replace)[p] + getattr(model, self.retire)[p])) * model.bigM

        def eol_rule2(model, p):
            return (1 - (getattr(model, self.replace)[p] + getattr(model, self.retire)[p])) <= \
                   getattr(model, self.lifetime_remaining)[p] * model.bigM

        con_name = 'eol_1_' + self.node_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=eol_rule1))
        con_name = 'eol_2_' + self.node_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=eol_rule2))

    def factory_pos_neg_flows(self, var_name, pos_name, neg_name):
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
            import_tariff_name = 'import_tariff_' + self.node_name
            setattr(model, import_tariff_name,
                    en.Param(model.Expansion, model.Time, initialize=self.tariff.import_tariff))

            export_tariff_name = 'export_tariff_' + self.node_name
            setattr(model, export_tariff_name,
                    en.Param(model.Expansion, model.Time, initialize=self.tariff.export_tariff))

            objective += sum(
                getattr(model, import_tariff_name)[p, i] * getattr(model, 'positive_' + self.node_name)[p, i] +
                getattr(model, export_tariff_name)[p, i] * getattr(model, 'negative_' + self.node_name)[p, i]
                for p in model.Expansion for i in model.Time)

        # To ensure either positive or negative component = 0
        if self.opt_type is OptimisationType.Variable:
            objective += sum(
                (getattr(model, 'positive_' + self.node_name)[p, i] + getattr(model, 'negative_' + self.node_name)[
                    p, i]) for p in model.Expansion for i in model.Time) * 0.00000001

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
        self.dynamic_nodes = []
        self.hub_name = 'hub_' + str(self.uid)
        self.expansion_planning = False  # For identifying hubs which we can connect new expansion assets to
        self.transformation = {}
        self.expansion = False  # For identifying hubs (assets) that ARE potential expansions
        self.lifetime = 10  # ToDo - link to expansion period timescale

    def add_dynamic_node(self, node_name):
        if self.allow_dynamic_nodes is False:
            raise ConfigurationError("Hub does not permit dynamic nodes")

        # Creates and adds node to the hub, as well as adding it to the list of dynamic nodes
        dn = FlexibleAsset()
        self.nodes[str(node_name)] = dn
        self.dynamic_nodes.append([str(node_name)])

    def add_named_node(self, node_name):
        # Creates and adds node to the hub, as well as adding it to the list of named nodes
        nn = FlexibleAsset()
        self.nodes[str(node_name)] = nn
        self.named_nodes.append([str(node_name)])

    def add_transformation(self, tr_obj):
        self.transformation[uuid.uuid4()] = tr_obj

    def verify_hub(self):
        """ Used to verify that a hub has been setup appropriately"""

        if self.expansion_planning is True and self.hub_rule is not (HubNodeRule.Tellegen or HubNodeRule.Sum):
            raise ConfigurationError('Expansion planning can only be applied to Tellegen hubs.')

        if self.hub_rule is HubNodeRule.NA and len(self.nodes) > 1:
            raise ConfigurationError('HubNodeRule cannot be NA if hub has more than one port.')

        if self.expansion_planning is True and self.expansion is True:
            raise ConfigurationError(
                'A hub either supports expansion planning, or is an expansion asset, it cannot be both.')


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
        self.capex = 0  # in $/unit capacity
        self.fixed_capacity = True

    def initialise_node(self, model):
        super(Storage, self).initialise_node(model)  # Creates pos and neg flow variables for node

        if self.capex and self.fixed_capacity is True:
            warnings.warn('Storage has nonzero capex but fixed capacity')

        SOC_name = 'storage_soc_' + self.node_name
        self.storage_soc_value = SOC_name

        setattr(model, SOC_name,
                en.Var(model.Expansion, model.Time, initialize=0, bounds=(0, self.max_capacity)))  # Actual SOC

        optimised_capacity = 'optimised_capacity_' + self.node_name  # Define max battery capacity as variable
        self.optimised_capacity = optimised_capacity
        if self.fixed_capacity is False:
            setattr(model, optimised_capacity, en.Var(initialize=0, domain=en.NonNegativeReals))
        else:
            setattr(model, optimised_capacity, en.Param(initialize=self.max_capacity, domain=en.NonNegativeReals))

        def cap_limit(model, expansion_interval, time_interval):  # Ensure SOC is within max capacity
            return getattr(model, SOC_name)[expansion_interval, time_interval] <= getattr(model, optimised_capacity)

        cap_limit_con_name = 'cap_limit_cons_' + self.node_name
        setattr(model, cap_limit_con_name, en.Constraint(model.Expansion, model.Time, rule=cap_limit))

        # ToDo - take account of battery charging efficiency
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
        def storage_charge_rate_limit(model, expansion_interval, time_interval):
            return getattr(model, self.node_name)[expansion_interval, time_interval] <= charging_limit

        # Enforce the discharge rate limit
        def storage_discharge_rate_limit(model, expansion_interval, time_interval):
            return getattr(model, self.node_name)[expansion_interval, time_interval] >= discharging_limit

        con_name = 'charge_limit_' + self.node_name
        con_name2 = 'discharge_limit_' + self.node_name

        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=storage_charge_rate_limit))
        setattr(model, con_name2, en.Constraint(model.Expansion, model.Time, rule=storage_discharge_rate_limit))

        initial_state_of_charge = self.initial_state_of_charge

        def SOC_rule(model, expansion_interval, time_interval):
            if time_interval == 0:
                return getattr(model, SOC_name)[expansion_interval, time_interval] \
                       == initial_state_of_charge + getattr(model, self.node_name)[expansion_interval, time_interval]
            else:
                return getattr(model, SOC_name)[expansion_interval, time_interval] \
                       == getattr(model, SOC_name)[expansion_interval, time_interval - 1] + \
                       getattr(model, self.node_name)[expansion_interval, time_interval]

        soc_con = 'soc_limit_' + self.node_name
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
            getattr(model, 'positive_' + self.node_name)[p, i] - getattr(model, 'negative_' + self.node_name)[p, i]
            for p in model.Expansion for i in model.Time) * self.throughput_cost / 2.0

        objective += sum(
            getattr(model, 'positive_' + self.node_name)[p, i] * getattr(model, 'positive_' + self.node_name)[p, i] + \
            getattr(model, 'negative_' + self.node_name)[p, i] * getattr(model, 'negative_' + self.node_name)[p, i]
            for p in model.Expansion for i in model.Time) * 0.0000001

        # Capex - cost of storage in $/kWh, associated with installation variable
        objective += getattr(model, self.optimised_capacity) * self.capex

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
    """A hub that implements a Kirchoff / Tellegen constraint requiring that electrical power is conserved"""

    def __init__(self):
        super(ElectricalHub, self).__init__()
        self.units = Units.KW


class BulkElectricalGrid(FlexibleAsset):

    def __init__(self):
        super(BulkElectricalGrid, self).__init__()
        self.units = Units.KW


class Tariff(object):

    def __init__(self):
        pass

    def add_tariff_profile_import(self, tariff):
        self.import_tariff = tariff

    def add_tariff_profile_export(self, tariff):
        self.export_tariff = tariff


class Port(Node):

    def __init__(self):
        super(Port, self).__init__()
        self.flows = Flows.Both
        self.import_constraint = FlowConstraint.NoConstraint
        self.export_constraint = FlowConstraint.NoConstraint
        self.opt_type = OptimisationType.Variable
        self.units = Units.KW


class Edge(object):

    def __init__(self):
        self.flows = Flows.Both
        self.uid = uuid.uuid4()
        self.edge_name = 'edge_' + str(self.uid)
        self.units = Units.NA  # Used to ensure that common units are being optimised over at points of interconnection
        self.opt_type = OptimisationType.NA  # Is this a decision variable or a fixed parameter
        self.initial_value = 0
        self.has_tariff = False
        self.tariff = None
        self.initial_state = 1  # 1 = on, 0 = off
        self.initial_edge_capacity = 5000000
        self.expansion_planning = False
        self.capex = 0

    def add_vertices(self,  obj1, obj2):
        self.edge_objs = (obj1, obj2)

    def initialise_edge(self, model):

        hub_port = self.edge_objs[0]
        asset_port = self.edge_objs[1]

        # Apply edge constraint
        con_rule1 = self.factory_constraint_edge_builder(hub_port.node_name, asset_port.node_name)
        con_name = 'edge_con_' + hub_port.node_name + '_' + asset_port.node_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=con_rule1))

        # Apply edge capacity constraint to one of the edge vertices
        if hub_port.opt_type is OptimisationType.Parameter:  # Choose edge vertex that is not a parameter
            selected_port = asset_port
        else:
            selected_port = hub_port

        # Check whether selected port has existing flow constraints
        if (hub_port.import_constraint is FlowConstraint.Fixed) or (asset_port.import_constraint is FlowConstraint.Fixed):
            warnings.warn('Applying an edge flow constraint but an import constraint exists at a vertex.')
        if (hub_port.export_constraint is FlowConstraint.Fixed) or (asset_port.export_constraint is FlowConstraint.Fixed):
            warnings.warn('Applying an edge flow constraint but an export constraint exists at a vertex.')

        # Define variable for added capacity per expansion period
        self.cap_add = 'cap_add_' + self.edge_name
        if self.expansion_planning is False:
            setattr(model, self.cap_add, en.Param(model.Expansion, initialize=0, domain=en.NonNegativeReals))
        else:
            setattr(model, self.cap_add, en.Var(model.Expansion, initialize=0, domain=en.NonNegativeReals))

        # Define variable for current edge capacity
        self.current_cap = 'current_cap_' + self.edge_name
        setattr(model, self.current_cap, en.Var(model.Expansion, initialize=0, domain=en.NonNegativeReals))

        def current_cap(model, p):
            if p == 0:
                return getattr(model, self.current_cap)[p] == self.initial_edge_capacity + getattr(model, self.cap_add)[p]
            else:
                return getattr(model, self.current_cap)[p] == \
                       getattr(model, self.current_cap)[p-1] + getattr(model, self.cap_add)[p]

        con_name = 'current_cap_con_' + self.edge_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=current_cap))

        # Enforce that port value is within current edge capacity
        def cap_rule_1(model, p, t):
            return getattr(model, selected_port.node_name)[p, t] <= getattr(model, self.current_cap)[p]

        def cap_rule_2(model, p, t):
            return getattr(model, selected_port.node_name)[p, t] >= - getattr(model, self.current_cap)[p]

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
        # Only cost is cost of edge expansions
        return sum(getattr(model, self.cap_add)[p] for p in model.Expansion)*self.capex

    def add_initial_edge_capacity(self, cap):
        self.initial_edge_capacity = cap

class Transform(object):

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
