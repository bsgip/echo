"""Commodity agnostic ports and nodes"""

from collections.abc import Iterable
from functools import partial

import numpy as np
import pandas as pd
import pyomo.environ as en
from pydantic import Field, PositiveFloat, root_validator, validator
from pyomo.core.expr import EqualityExpression, InequalityExpression

from echo.configuration import FlowConstraint, Flows, OptimisationType, Units
from echo.exceptions import ConfigurationError, validate
from echo.models.base import Node, Port
from echo.models.scenario import EchoConcreteModel
from echo.utils import (
    TimeExpandableType,
    TimeSeriesData,
    expand_as_array,
    generate_array_constraint,
    populate_values_across_time_and_expansion_indices,
    set_float_var_bounds,
    set_var_bounds_from_dict,
)
from echo.validators import (
    ArrayType,
    check_bound_order,
    dod_checks,
    node_unit_validator,
    nonnegative_costs,
    nonnegative_load,
    nonpositive_generation,
    set_bounds_from_piecewise_points,
    validate_partition_ports,
    validate_piecewise_arrays,
)


class FlexPort(Port):
    """Flexible variable port, which can import and export without constraints."""

    flows = Flows.Both
    import_constraint = FlowConstraint.NoConstraint
    export_constraint = FlowConstraint.NoConstraint
    flow_type = OptimisationType.Variable


class FlexSink(FlexPort):
    """Flexible port, imports only"""

    flows = Flows.Import


class FlexSource(FlexPort):
    """Flexible ports, exports only"""

    flows = Flows.Export


class FixedPort(Port):
    """Fixed port (parameter), can either import or export."""

    flows = Flows.Both
    import_constraint = FlowConstraint.NoConstraint
    export_constraint = FlowConstraint.NoConstraint
    flow_type = OptimisationType.Parameter


class Source(Port):
    """A fixed source of a commodity."""

    flows = Flows.Export
    export_constraint = FlowConstraint.NoConstraint
    flow_type = OptimisationType.Parameter

    # Source should have non positive initial values
    non_pos_check = validator("initial_value", allow_reuse=True)(nonpositive_generation)

    def add_source_profile(self, source_values: dict) -> None:
        self.set_initial_value(source_values)

    def add_source_profile_from_array(
        self,
        source_values: list[float] | np.ndarray,
        expansion_periods: int = 1,
        time_periods: int | None = None,
    ) -> None:
        self.set_initial_value_from_array(
            array=source_values, expansion_periods=expansion_periods, time_periods=time_periods
        )


class Sink(Port):
    """A fixed sink for a commodity."""

    flows = Flows.Import
    import_constraint = FlowConstraint.NoConstraint
    flow_type = OptimisationType.Parameter

    non_neg_check = validator("initial_value", allow_reuse=True)(
        nonnegative_load
    )  # Sink should have non negative initial values

    def add_sink_profile(self, sink_values: dict[tuple[int, int], float]) -> None:
        self.set_initial_value(sink_values)

    def add_sink_profile_from_array(
        self,
        sink_values: list[float] | np.ndarray,
        expansion_periods: int = 1,
        time_periods: int | None = None,
    ) -> None:

        self.set_initial_value_from_array(
            array=sink_values, expansion_periods=expansion_periods, time_periods=time_periods
        )


class Demand(Sink):
    def add_demand_profile(self, demand: dict) -> None:
        self.set_initial_value(demand)

    def add_demand_profile_from_array(
        self,
        demand: TimeExpandableType,
        expansion_periods: int = 1,
        time_periods: int | None = None,
    ) -> None:
        self.set_initial_value_from_array(array=demand, expansion_periods=expansion_periods, time_periods=time_periods)


class TellegenNode(Node):
    """A node that implements a Tellegen constraint requiring that port values sum to zero."""

    tellegen_unit_check = root_validator(allow_reuse=True)(node_unit_validator)

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        def tellegen_node_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            a = 0
            for port in node_ports.values():
                a += getattr(model, port.port_name)[p, t]
            return a == 0

        node_ports = self.ports
        con_name = "reliability_con_" + self.node_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=tellegen_node_rule))

    def verify_node(self) -> None:
        super().verify_node()

        validate(
            len(self.ports) >= 2,
            f"A tellegen node must have at least two ports. Offending node has the name: {self.node_name}",
        )


class ThreeWayValveNode(TellegenNode):
    """A node that implements a Tellegen constraint requiring that port values sum to zero.

    ThreeWayValveNode node implements additional constraints between ports,
    there is one input (import) port and two output (export) ports.
    At each time the flow is allowed through only one output port.
    """

    units: Units
    input_port_name: str = "input_port"
    output_port_name_1: str = "output_port_1"
    output_port_name_2: str = "output_port_2"

    # Tuple of two port names on the Node, non-zero flow through only one of the port allowed at any time
    mutually_exclusive_port_flows: tuple[str, str] = None

    @property
    def binary_variable_flow_through_mutually_exclusive_port_1(self) -> str:
        return f"binary_variable_flow_through_mutually_exclusive_{self.output_port_name_1}_{self.node_name}"

    @property
    def constraint_neg_flow_mutually_exclusive_port_1(self) -> str:
        return f"constraint_neg_flow_mutually_exclusive_{self.output_port_name_1}_{self.node_name}"

    @property
    def constraint_pos_flow_mutually_exclusive_port_1(self) -> str:
        return f"constraint_pos_flow_mutually_exclusive_{self.output_port_name_1}_{self.node_name}"

    @property
    def constraint_neg_flow_mutually_exclusive_port_2(self) -> str:
        return f"constraint_neg_flow_mutually_exclusive_{self.output_port_name_2}_{self.node_name}"

    @property
    def constraint_pos_flow_mutually_exclusive_port_2(self) -> str:
        return f"constraint_pos_flow_mutually_exclusive_port_{self.output_port_name_2}_{self.node_name}"

    def __init__(self, **data) -> None:
        super().__init__(**data)
        self.create_ports()

    def create_ports(self) -> None:
        # Create input and output ports
        self.ports[self.input_port_name] = FlexSink(units=self.units)
        self.ports[self.output_port_name_1] = FlexSource(units=self.units)
        self.ports[self.output_port_name_2] = FlexSource(units=self.units)

    def set_ports(
        self,
        input_port: FlexSink,
        output_port_1: FlexSource,
        output_port_2: FlexSource,
    ) -> None:
        # Discard existing ports
        self.ports.clear()

        # Update port references
        self.input_port_name = input_port.port_name
        self.output_port_name_1 = output_port_1.port_name
        self.output_port_name_2 = output_port_2.port_name

        # Add the new ports
        self.ports[self.input_port_name] = input_port
        self.ports[self.output_port_name_1] = output_port_1
        self.ports[self.output_port_name_2] = output_port_2

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        # Load coefficient of performance values from profile (if provided by reference)
        setattr(
            model,
            self.binary_variable_flow_through_mutually_exclusive_port_1,
            en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary),
        )
        super().add_node_to_model(model, profile)

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        super().apply_node_constraints(model)
        self._apply_mutually_exclusive_port_flow_constraint(model)

    def _apply_mutually_exclusive_port_flow_constraint(self, model: EchoConcreteModel) -> None:

        _port_name_1 = self.ports.get(self.output_port_name_1).port_name
        _port_name_2 = self.ports.get(self.output_port_name_2).port_name
        _binary_var = getattr(model, self.binary_variable_flow_through_mutually_exclusive_port_1)

        def mutual_exclusivity_rule_11(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            """When _binary_var is 0, flow through output port 1 is constrained to be zero"""
            return _binary_var[p, t] * -1 * model.big_m <= getattr(model, _port_name_1)[p, t]

        con_name = self.constraint_neg_flow_mutually_exclusive_port_1
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=mutual_exclusivity_rule_11))

        def mutual_exclusivity_rule_12(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            """When _binary_var is 0, flow through output port 1 is constrained to be zero"""
            return getattr(model, _port_name_1)[p, t] <= _binary_var[p, t] * model.big_m

        con_name = self.constraint_pos_flow_mutually_exclusive_port_1
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=mutual_exclusivity_rule_12))

        def mutual_exclusivity_rule_21(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            """When _binary_var is 1, flow through output port 2 is constrained to be zero"""
            return (1 - _binary_var[p, t]) * -1 * model.big_m <= getattr(model, _port_name_2)[p, t]

        con_name = self.constraint_neg_flow_mutually_exclusive_port_2
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=mutual_exclusivity_rule_21))

        def mutual_exclusivity_rule_22(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            """When _binary_var is 1, flow through output port 2 is constrained to be zero"""
            return getattr(model, _port_name_2)[p, t] <= (1 - _binary_var[p, t]) * model.big_m

        con_name = self.constraint_pos_flow_mutually_exclusive_port_2
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=mutual_exclusivity_rule_22))


class MultiCommodityTellegenNode(Node):
    """
    A node with ports that have multiple commodities.
    A tellegen constraint is applied per commodity.
    """

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        """Apply Tellegen constraint for same commodity ports."""

        def tellegen_node_rule(
            commodity_ports: Iterable[Port],
            model: EchoConcreteModel,
            p: int,
            t: int,
        ) -> EqualityExpression:
            net_flow = 0
            for port in commodity_ports:
                port_flow = getattr(model, port.port_name)
                net_flow += port_flow[p, t]
            return net_flow == 0

        commodities = dict()
        for p in self.ports.values():
            if commodities.get(p.units) is None:
                commodities[p.units] = [p]
            else:
                commodities[p.units].append(p)

        for commodity_type, commodity_ports in commodities.items():
            setattr(
                model,
                "node_con_" + str(commodity_type) + self.node_name,
                en.Constraint(
                    model.Expansion,
                    model.Time,
                    rule=partial(tellegen_node_rule, commodity_ports),
                ),
            )


class PartitionedMultiCommodityTellegenNode(Node):
    """
    A node with partitions of ports, ports in each partition may have multiple commodities.
    A tellegen constraint is applied per partition per commodity.
    """

    partitions: dict[str, list[Port]] = Field(default_factory=dict)
    default_partition: str = "default_partition"

    partition_port_uniqueness_check = root_validator(allow_reuse=True)(validate_partition_ports)

    def __init__(self, **data) -> None:
        super().__init__(**data)
        if len(self.ports):
            if len(self.partitions):
                raise ValueError(
                    "Expect user to define either ports dictionary or partitions dictionary, "
                    "but not both on an instance of PartitionedMultiCommodityTellegenNode."
                    f"Offending instance {self.node_name}"
                )
            else:
                # If user defined ports but not partitions, assign all ports to a default partition
                self.partitions = {self.default_partition: list(self.ports.values())}
        else:
            self.ports = {_p.port_name: _p for port_set in self.partitions.values() for _p in port_set}

    def add_port(self, name: str, port: Port, partition: str | None = None) -> None:
        """Override base add_port method, add addition argument which is partition name to which add the port.

        If partition is not specified, adds to the default partition.
        """
        if partition is None:
            partition = self.default_partition
        if self.ports.get(name) is None:
            self.ports[name] = port
            if not self.partitions.get(partition):
                """If partition with this name does not exist in the partition dictionary, add new item."""
                self.partitions[partition] = [port]
            else:
                self.partitions[partition].append(port)
        else:
            raise ConfigurationError(f"Port with name {name} is already defined on node {self.node_name}")

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        """Apply Tellegen constraint for same commodity ports within each partition."""

        def tellegen_node_rule(
            partition_ports: Iterable[Port],
            model: EchoConcreteModel,
            p: int,
            t: int,
        ) -> EqualityExpression:
            net_flow = 0
            for port in partition_ports:
                port_flow = getattr(model, port.port_name)
                net_flow += port_flow[p, t]
            return net_flow == 0

        partition_commodities = dict()
        for _partition, _ports in self.partitions.items():
            for p in _ports:
                _key = (_partition, p.units)
                if partition_commodities.get(_key) is None:
                    partition_commodities[_key] = [p]
                else:
                    partition_commodities[_key].append(p)

        for partition_commodity_type, partition_ports in partition_commodities.items():
            setattr(
                model,
                "node_con_" + str(partition_commodity_type) + self.node_name,
                en.Constraint(
                    model.Expansion,
                    model.Time,
                    rule=partial(tellegen_node_rule, partition_ports),
                ),
            )


class ControlledLoadOrGen(FlexPort):
    """
    A controlled load or generation has a max/min power, as well as a max/min utilisation.
    Min utilisation is the ratio between the minimum energy consumed/generated,
    and the maximum energy that could be consumed/generated if the load operated at max power.
    Max utilisation is the ratio between the maximum energy consumed/generated,
    and the maximum energy that could be consumed/generated if the load operated at max power.
    """

    min_utilisation: float | None = None
    max_utilisation: float | None = None
    max_power: float | None = None
    min_power: float | None = None
    units: Units = Units.KW

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_port_to_model(model, profile)

        # Set bounds using min and max power
        set_float_var_bounds(model=model, var_name=self.port_name, ub=self.max_power, lb=self.min_power)

        if self.min_utilisation is not None and self.max_power is not None:
            min_utilisation: float = self.min_utilisation
            max_power: float = self.max_power

            def sum_of_energy_must_be_greater_than_min(model: EchoConcreteModel) -> InequalityExpression:
                return (
                    sum(
                        getattr(model, self.port_name)[p, i] * model.scenario_settings.interval_duration / 60.0
                        for p in model.Expansion
                        for i in model.Time
                    )
                    >= min_utilisation
                    * max_power
                    * model.scenario_settings.interval_duration
                    * model.scenario_settings.number_of_intervals
                    / 60.0
                )

            setattr(
                model,
                f"cons_{self.port_name}_min_utilisation_req",
                en.Constraint(rule=sum_of_energy_must_be_greater_than_min),
            )

        if self.max_utilisation is not None and self.max_power is not None:
            max_utilisation: float = self.max_utilisation
            max_power = self.max_power

            def sum_of_energy_must_be_less_than_max(model: EchoConcreteModel) -> InequalityExpression:
                return (
                    sum(
                        getattr(model, self.port_name)[p, i] * model.scenario_settings.interval_duration / 60.0
                        for p in model.Expansion
                        for i in model.Time
                    )
                    <= max_utilisation
                    * max_power
                    * model.scenario_settings.interval_duration
                    * model.scenario_settings.number_of_intervals
                    / 60.0
                )

            setattr(
                model,
                f"cons_{self.port_name}_max_utilisation_req",
                en.Constraint(rule=sum_of_energy_must_be_less_than_max),
            )


class ControlledLoad(ControlledLoadOrGen):
    max_power: float = Field(ge=0)
    min_power: float = Field(ge=0)
    flows = Flows.Import


class ControlledGen(ControlledLoadOrGen):
    max_power: float = Field(le=0)
    min_power: float = Field(le=0)
    flows = Flows.Export


class OffOrConstrainedPort(FlexPort):
    """A port that is either off (0) or on, and when it is on it is constrained between a min and max value."""

    lower_bound: float
    upper_bound: float

    bounds_check = root_validator(allow_reuse=True)(check_bound_order)  # checks that lower bound < upper bound

    @property
    def active(self) -> str:
        return "active_" + self.port_name

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_port_to_model(model, profile)
        setattr(model, self.active, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary))

        # Apply constraints such that if active=1, the port is bounded, and if active=0, the port is 0.
        def on_off_constraint1(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            return getattr(model, self.port_name)[p, t] >= getattr(model, self.active)[p, t] * self.lower_bound

        def on_off_constraint2(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            return getattr(model, self.port_name)[p, t] <= getattr(model, self.active)[p, t] * self.upper_bound

        setattr(model, "on_off1_" + self.port_name, en.Constraint(model.Expansion, model.Time, rule=on_off_constraint1))
        setattr(model, "on_off2_" + self.port_name, en.Constraint(model.Expansion, model.Time, rule=on_off_constraint2))


class BoundedPort(FlexPort):
    """A flex port with an upper and lower bound"""

    upper_bound: ArrayType | float
    lower_bound: ArrayType | float

    bound_check = root_validator(allow_reuse=True)(check_bound_order)  # check lower bound < upper bound

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_port_to_model(model, profile)
        # Set bounds on our port variable
        ub_dict = generate_array_constraint(self.upper_bound, time_periods=len(model.Time), expansion_periods=1)
        lb_dict = generate_array_constraint(self.lower_bound, time_periods=len(model.Time), expansion_periods=1)
        set_var_bounds_from_dict(model=model, var_name=self.port_name, ub=ub_dict, lb=lb_dict)


class BoundedLoad(BoundedPort):
    """A port where the load has to be within a max and min value which is specified at each timestep."""

    import_constraint = FlowConstraint.NoConstraint

    # Do additional validation to make sure both bounds are >= 0
    upper_bound_check = validator("upper_bound", allow_reuse=True)(nonnegative_costs)
    lower_bound_check = validator("lower_bound", allow_reuse=True)(nonnegative_costs)

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_port_to_model(model, profile)


class Storage(Port):
    """Same as old storage but without all the EV attributes"""

    flows = Flows.Both
    flow_type = OptimisationType.Variable
    import_constraint = FlowConstraint.Fixed
    export_constraint = FlowConstraint.Fixed
    max_capacity: float
    depth_of_discharge_limit: float = 0  # DoD limit is the percent soc to which you can discharge the storage
    min_soc: float = 0
    charging_power_limit: float
    discharging_power_limit: float
    charging_efficiency: float = 1
    discharging_efficiency: float = 1
    fixed_storage_capacity: bool = True
    storage_capacity_cost: PositiveFloat | None = None
    regularise: bool = False
    initial_state_of_charge: float | None

    dod_check = root_validator(allow_reuse=True)(dod_checks)

    @property
    def soc_value(self) -> str:
        return "storage_soc_" + self.port_name

    @property
    def optimised_capacity(self) -> str:
        return "optimised_storage_capacity_" + self.port_name

    @property
    def soc_constraint(self) -> str:
        return "soc_cons_" + self.port_name

    def __init__(self, **data) -> None:
        super().__init__(**data)
        self.import_constraint_value = self.charging_power_limit
        self.export_constraint_value = self.discharging_power_limit

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_port_to_model(model, profile)
        self.create_storage_variables(model)
        self.apply_soc_constraints(model)

    def create_storage_variables(self, model: EchoConcreteModel) -> None:
        # Create soc variable and bound it
        setattr(
            model,
            self.soc_value,
            en.Var(
                model.Expansion,
                model.Time,
                initialize=self.initial_state_of_charge,
                bounds=(self.min_soc, self.max_capacity),
            ),
        )
        # Apply charging constraints as bounds on port_name variable
        set_float_var_bounds(model, self.port_name, ub=self.charging_power_limit, lb=self.discharging_power_limit)

        if self.fixed_storage_capacity is False:
            setattr(model, self.optimised_capacity, en.Var(initialize=0, domain=en.NonNegativeReals))

            def cap_limit(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
                # Ensure SOC is within max capacity
                return getattr(model, self.soc_value)[p, t] <= getattr(model, self.optimised_capacity)

            setattr(model, f"cap_lim_{self.port_name}", en.Constraint(model.Expansion, model.Time, rule=cap_limit))
        else:
            setattr(model, self.optimised_capacity, en.Param(initialize=self.max_capacity, domain=en.NonNegativeReals))

    def apply_soc_constraints(self, model: EchoConcreteModel) -> None:
        """Extract some variables to make constraints easier to write"""
        max_t = len(model.Time)  # maximum time interval t
        kw_to_kwh = model.scenario_settings.interval_duration / 60  # conversion from kW to kWh
        soc = getattr(model, self.soc_value)
        power = getattr(model, self.port_name)

        def soc_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            if p == 0 and t == 0:
                return (
                    soc[p, t]
                    == self.initial_state_of_charge
                    + pos[p, t] * kw_to_kwh * self.charging_efficiency
                    + neg[p, t] * kw_to_kwh / self.discharging_efficiency
                )
            elif t == 0:
                return (
                    soc[p, t]
                    == soc[p - 1, max_t]
                    + pos[p, t] * kw_to_kwh * self.charging_efficiency
                    + neg[p, t] * kw_to_kwh / self.discharging_efficiency
                )
            else:
                return (
                    soc[p, t]
                    == soc[p, t - 1]
                    + pos[p, t] * kw_to_kwh * self.charging_efficiency
                    + neg[p, t] * kw_to_kwh / self.discharging_efficiency
                )

        def soc_rule_perfect_efficiency(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            if p == 0 and t == 0:
                return soc[p, t] == self.initial_state_of_charge + power[p, t] * kw_to_kwh
            elif t == 0:
                return soc[p, t] == soc[p - 1, max_t] + power[p, t] * kw_to_kwh
            else:
                return soc[p, t] == soc[p, t - 1] + power[p, t] * kw_to_kwh

        if (self.charging_efficiency == 1) and (self.discharging_efficiency == 1):
            setattr(
                model, self.soc_constraint, en.Constraint(model.Expansion, model.Time, rule=soc_rule_perfect_efficiency)
            )
        else:
            self.constrain_pos_neg(model)
            pos = getattr(model, self.pos)  # get pos variable for writing constraints
            neg = getattr(model, self.neg)  # get neg variable for writing constraints
            setattr(model, self.soc_constraint, en.Constraint(model.Expansion, model.Time, rule=soc_rule))

    def add_objective(self, model: EchoConcreteModel) -> None:
        super().add_objective(model)
        total = 0

        # To get unique solution
        if self.regularise is True:
            total += (
                sum(
                    getattr(model, self.pos)[p, t] * getattr(model, self.pos)[p, t]
                    + getattr(model, self.neg)[p, t] * getattr(model, self.neg)[p, t]
                    for p in model.Expansion
                    for t in model.Time
                )
                * 0.0000001
            )

        if self.storage_capacity_cost is not None:
            total += getattr(model, self.optimised_capacity) * self.storage_capacity_cost

        self.objective += total


class MobileStorage(Storage):
    """New Storage + EV attributes"""

    # next variable is for allowing soc to go below min so as to avoid optimisation failing if there infeasible ev trips
    enable_trip_slack: bool = False
    # next three variables are for having a 'conservative' ev user lower bound on the soc while it is plugged in
    # soc_conserv: Union[ArrayType,list,float, None, dict] = None
    soc_conserv: TimeExpandableType | None = None
    soc_conserv_cost: float | None = None
    # soc_conserve: scalarOrArray
    available: ArrayType | list | None = None

    @property
    def cons_slack(self) -> str:
        return "con_slack" + self.port_name

    @property
    def trip_slack(self) -> str:
        return "trip_slack_" + self.port_name

    @root_validator
    def check_soc_conserv_has_cost(cls, values: dict) -> dict:
        soc_conserv = values.get("soc_conserv")
        soc_conserv_cost = values.get("soc_conserv_cost")
        available = values.get("available")
        if soc_conserv is not None:
            validate(soc_conserv_cost is not None, "soc_conserv requires soc_conserv_cost")
            validate(available is not None, "soc_conserve requires available")
        return values

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super(Storage, self).add_port_to_model(model, profile)
        self.create_storage_variables(model)
        if self.enable_trip_slack:
            self.apply_modified_soc_constraints(model)
        else:
            self.apply_soc_constraints(model)
        self.apply_conserv_soc_constraints(model)

    def apply_conserv_soc_constraints(self, model: EchoConcreteModel) -> None:
        def soc_conservative_rule(
            model: EchoConcreteModel,
            p: int,
            t: int,
        ) -> InequalityExpression | type[en.Constraint.Skip]:
            """A rule for enforcing conservativeness while plugged in"""
            if expanded_soc_conserv and self.available is not None and self.available[t]:
                return (
                    getattr(model, self.soc_value)[p, t]
                    + getattr(model, self.cons_slack)[p, t]
                    - expanded_soc_conserv[p, t]
                    >= 0
                )
            else:
                return en.Constraint.Skip

        if self.soc_conserv is not None:
            expanded_soc_conserv = expand_as_array(
                TimeSeriesData(
                    value=self.soc_conserv,
                    num_expansion_intervals=len(model.Expansion),
                    num_time_intervals=len(model.Time),
                )
            )
            setattr(
                model, self.cons_slack, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals)
            )
            setattr(
                model,
                f"cons_soc_{self.port_name}",
                en.Constraint(model.Expansion, model.Time, rule=soc_conservative_rule),
            )

    def apply_modified_soc_constraints(self, model: EchoConcreteModel) -> None:
        """Get some variables to make constraints easier to write"""
        max_t = len(model.Time)  # maximum time interval t
        kw_to_kwh = model.scenario_settings.interval_duration / 60  # conversion from kW to kWh
        soc = getattr(model, self.soc_value)
        power = getattr(model, self.port_name)

        def soc_rule_slack(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            if p == 0 and t == 0:
                return (
                    soc[p, t]
                    == self.initial_state_of_charge
                    + pos[p, t] * kw_to_kwh * self.charging_efficiency
                    + neg[p, t] * kw_to_kwh / self.discharging_efficiency
                    + slack[p, t]
                )
            elif t == 0:
                return (
                    soc[p, t]
                    == soc[p - 1, max_t]
                    + pos[p, t] * kw_to_kwh * self.charging_efficiency
                    + neg[p, t] * kw_to_kwh / self.discharging_efficiency
                    + slack[p, t]
                )
            else:
                return (
                    soc[p, t]
                    == soc[p, t - 1]
                    + pos[p, t] * kw_to_kwh * self.charging_efficiency
                    + neg[p, t] * kw_to_kwh / self.discharging_efficiency
                    + slack[p, t]
                )

        def soc_rule_perfect_efficiency_slack(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            if p == 0 and t == 0:
                return soc[p, t] == self.initial_state_of_charge + power[p, t] * kw_to_kwh + slack[p, t]
            elif t == 0:
                return soc[p, t] == soc[p, t - 1] + power[p - 1, max_t] * kw_to_kwh + slack[p, t]
            else:
                return soc[p, t] == soc[p, t - 1] + power[p, t] * kw_to_kwh + slack[p, t]

        if self.enable_trip_slack is True:
            """Create a slack variable"""
            setattr(
                model, self.trip_slack, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals)
            )

            # get slack variable for writing constraints
            slack = getattr(model, self.trip_slack)

            # Apply the modified soc constraint, which will overwrite the previously created one
            if (self.charging_efficiency == 1) and (self.discharging_efficiency == 1):
                setattr(
                    model,
                    self.soc_constraint,
                    en.Constraint(model.Expansion, model.Time, rule=soc_rule_perfect_efficiency_slack),
                )
            else:
                self.constrain_pos_neg(model)
                pos = getattr(model, self.pos)  # get pos variable for writing constraints
                neg = getattr(model, self.neg)  # get neg variable for writing constraints
                setattr(model, self.soc_constraint, en.Constraint(model.Expansion, model.Time, rule=soc_rule_slack))

    def add_objective(self, model: EchoConcreteModel) -> None:
        super().add_objective(model)
        total = 0

        if self.enable_trip_slack:
            total += (
                sum(getattr(model, self.trip_slack)[p, t] for p in model.Expansion for t in model.Time)
                * model.big_m
                * 20
            )  # we want this to be more important than import/export constraints

        if self.soc_conserv is not None:
            total += (
                sum(getattr(model, self.cons_slack)[p, t] for p in model.Expansion for t in model.Time)
                * self.soc_conserv_cost
            )

        self.objective += total


class InputOutputNode(Node):
    """
    An input-output node has one input port and one output port.
    A custom transformation can be defined between input and output.
    """

    # TODO: This Node does not do anything, unnecessary inheritance

    input_port_unit: Units
    output_port_unit: Units
    # Optional parameters for controlling input/output port flows
    max_output: float | None  # output might be neg or pos, leave it open
    min_output: float | None
    max_input: float | None
    min_input: float | None
    input_port_ref: str = "input"
    output_port_ref: str = "output"

    def __init__(self, **data) -> None:
        super().__init__(**data)
        # Create an input port and an output port with the correct units
        self.ports[self.input_port_ref] = FlexPort(units=self.input_port_unit)
        self.ports[self.output_port_ref] = FlexPort(units=self.output_port_unit)


class TimeVaryingPiecewiseIONode(InputOutputNode):
    """A Node with an input and output and time varying piecewise relationship between input and output.

    The relationship between input and output is defined at each time interval by an array
    of input-->output point pairs, which are used to construct a piecewise constraint.
    Attributes input_port_unit and output_port_unit define node's commodity.
    """

    input_points: dict | None  # dict where the keys are planning-time period tuple, and value is input pt array
    output_points: dict | None  # dict where the keys are planning-time period tuple, and value is output pt array
    input_points_ref: str | None  # Ref to profile dataframe column with input points array to be used across all times
    output_points_ref: str | None  # Ref to profile dataframe column with input points array to be used across all times

    piecewise_check = root_validator(allow_reuse=True)(validate_piecewise_arrays)  # validate input/output points
    populate_bounds = root_validator(allow_reuse=True)(
        set_bounds_from_piecewise_points
    )  # set attributes max_output,  min_output, max_input, min_input from input points/output points

    def verify_points_values(self) -> None:
        validate(self.input_points is not None, "No input points defined")
        validate(self.output_points is not None, "No output points defined")
        # Validate that dictionary keys match and length of each value array are the same
        for k in self.input_points.keys():
            validate(k in self.output_points.keys(), f"Key {k} not found in output_points dictionary")
            validate(
                len(self.input_points[k]) == len(self.output_points[k]),
                "Number of break points in "
                "input_points output_points must match."
                f"Different length value arrays for key {k}",
            )

    def load_input_output_values_from_profile(self, model: EchoConcreteModel, profile_df: pd.DataFrame) -> None:
        """If input/output point string references are provided, load values from profile.

        input_points_ref/output_points_ref will override input_points/output_points values provided
        in the instance's attributes (if any) with values from profile dataframe.
        """
        if self.input_points_ref:
            """Load input points array from profile dataframe and set the same array across all time points"""
            if self.input_points_ref not in profile_df.columns:
                raise ValueError(f"Could not find reference column name {self.input_points_ref} in the profile.")
            input_points_array = profile_df[self.input_points_ref].to_list()
            self.add_constant_input_points(input_points_array, len(model.Time), len(model.Expansion))

        if self.output_points_ref:
            """Load input points array from profile dataframe and set the same array across all time points"""
            if self.output_points_ref and self.output_points_ref not in profile_df.columns:
                raise ValueError(f"Could not find reference column name {self.output_points_ref} in the profile.")
            output_points_array = profile_df[self.output_points_ref].to_list()
            self.add_constant_output_points(output_points_array, len(model.Time), len(model.Expansion))

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        self.load_input_output_values_from_profile(model, profile)
        super().add_node_to_model(model, profile)
        # Bound input and output port variables, otherwise piecewise constraint will fail
        self.verify_points_values()
        set_float_var_bounds(
            model=model, var_name=self.ports[self.output_port_ref].port_name, ub=self.max_output, lb=self.min_output
        )
        set_float_var_bounds(
            model=model, var_name=self.ports[self.input_port_ref].port_name, ub=self.max_input, lb=self.min_input
        )

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        xvar = getattr(model, self.ports[self.input_port_ref].port_name)
        yvar = getattr(model, self.ports[self.output_port_ref].port_name)
        xdata = self.input_points
        ydata = self.output_points
        con_name = "piecewise_con_" + self.node_name
        setattr(
            model,
            con_name,
            en.Piecewise(
                model.Expansion,
                model.Time,
                yvar,
                xvar,
                pw_pts=xdata,
                pw_constr_type="EQ",
                f_rule=ydata,
                pw_repn="SOS2",
                warn_domain_coverage=False,
            ),
        )

    def add_constant_input_points(
        self,
        input_points: float | int | list,
        time_periods: int,
        expansion_periods: int = 1,
    ) -> None:
        """Tiles constant input points array across time and expansion periods"""
        self.input_points = populate_values_across_time_and_expansion_indices(
            input_points, time_periods, expansion_periods
        )

    def add_constant_output_points(
        self,
        output_points: float | int | list,
        time_periods: int,
        expansion_periods: int = 1,
    ) -> None:
        """Tiles constant output points array across time and expansion periods."""
        self.output_points = populate_values_across_time_and_expansion_indices(
            output_points, time_periods, expansion_periods
        )


class TimeDelayNode(InputOutputNode):
    """A time delay node is an input-output node that implements a fixed delay between input and output."""

    time_delay: int  # number of time intervals delay between input and output

    def __init__(self, **data) -> None:
        super().__init__(**data)
        self.ports["input"] = FlexSink(units=self.input_port_unit)
        self.ports["output"] = FlexSource(units=self.output_port_unit)

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        def time_delay_rule(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            """This is a modified tellegen rule, where the sum=0 applies over staggered time periods according to the
            time delay.
            """
            a = getattr(model, self.ports["input"].port_name)
            b = getattr(model, self.ports["output"].port_name)
            if t < self.time_delay:
                return b[p, t] == 0
            else:
                return b[p, t] == a[p, int(t - self.time_delay)] * -1

        con_name = "time_delay_con_" + self.node_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=time_delay_rule))


class AggregationNode(Node):
    """Arbitrary commodity aggregation node.

    This node has an additional variable, 'total', which equals the sum of all ports defined on the node.
    port_units attribute is used for validation, all ports must be the same commodity.
    """

    port_units: Units

    aggregator_unit_check = root_validator(allow_reuse=True)(node_unit_validator)

    @property
    def total(self) -> None:
        return "total_value_" + self.node_name

    def verify_node(self) -> None:
        super().verify_node()

    def add_port(self, name: str, port: FlexSink | None = None) -> None:
        if port is None:
            port = FlexSink()

        if self.ports.get(name) is None:
            if port.units == Units.NA:
                port.units = self.port_units
            if port.units != self.port_units:
                raise ValueError(
                    f"All ports on Aggregation node must match the node units {self.port_units}."
                    f"Received new port with units {port.units} for node {self.node_name}"
                )
            self.ports[name] = port
        else:
            raise ConfigurationError(f"Port with name {name} is already defined on node {self.node_name}")

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_node_to_model(model, profile)
        # Create a variable for the total value
        setattr(model, self.total, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Reals))

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        def sum_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            a = 0
            for port in self.ports.values():
                a += getattr(model, port.port_name)[p, t]
            return getattr(model, self.total)[p, t] == a

        setattr(model, "total_sum_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=sum_rule))
