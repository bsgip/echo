from typing import Optional, Union

import pyomo.environ as en
from pydantic import NonNegativeFloat, PositiveFloat

from echo.configuration import Units
from echo.models.agnostic import (Demand, FlexPort, FlexSink, InputOutputNode,
                                  OffOrConstrainedPort)
from echo.models.base import Node, TransformNode
from echo.models.carbon import CarbonSource
from echo.models.electrical import ElectricalGeneration, ElectricalStorage
from echo.models.scenario import EchoConcreteModel
from echo.validators import ArrayType


class Battery(Node):
    def __init__(
        self,
        port_name,
        max_capacity: float,
        initial_state_of_charge: float,
        charging_power_limit: float,
        discharging_power_limit: float,
        storage_capacity_cost: Optional[PositiveFloat] = None,
        charging_efficiency: float = 1,
        discharging_efficiency: float = 1,
        depth_of_discharge_limit: float = 0,
        fixed_storage_capacity: bool = True,
        regularise: bool = False,
        **data,
    ):
        super().__init__(**data)
        self.ports[port_name] = ElectricalStorage(
            max_capacity=max_capacity,
            depth_of_discharge_limit=depth_of_discharge_limit,
            charging_power_limit=charging_power_limit,
            discharging_power_limit=discharging_power_limit,
            charging_efficiency=charging_efficiency,
            discharging_efficiency=discharging_efficiency,
            initial_state_of_charge=initial_state_of_charge,
            fixed_storage_capacity=fixed_storage_capacity,
            storage_capacity_cost=storage_capacity_cost,
            regularise=regularise,
        )


class Solar(Node):
    def __init__(self, port_name: str, profile: Union[ArrayType, dict], curtailable: bool = False, **data):
        super().__init__(**data)
        self.ports[port_name] = ElectricalGeneration(curtailable=curtailable)
        if type(profile) is dict:
            self.ports[port_name].set_initial_value(profile)
        else:
            self.ports[port_name].set_initial_value_from_array(profile)


class NewSolar(Node):
    """New Solar Node using Solar size for scaling of initial value ref"""

    def __init__(self, port_name: str, solar_size: float, initial_value_ref: str, curtailable: bool = False, **data):
        super().__init__(**data)
        self.ports[port_name] = ElectricalGeneration(
            curtailable=curtailable, initial_value_ref=initial_value_ref, initial_value_scaling=solar_size
        )


class Load(Node):
    def __init__(self, port_name: str, port_unit: Units, profile: Union[dict, ArrayType, list], **data):
        super().__init__(**data)
        self.ports[port_name] = Demand(units=port_unit)
        if type(profile) is dict:
            self.ports[port_name].set_initial_value(profile)
        else:
            self.ports[port_name].set_initial_value_from_array(profile)


class FlexNode(Node):
    def __init__(self, port_name: str, port_unit: Units, **data):
        super().__init__(**data)
        self.ports[port_name] = FlexPort(port_name=port_name, units=port_unit)


class FlexElectricalNode(Node):
    def __init__(self, port_name: str, **data):
        super().__init__(**data)
        self.ports[port_name] = FlexPort(port_name=port_name, units=Units.KW)


class FlexNodeWithEmissions(TransformNode):
    def __init__(
        self,
        emitting_port: str,
        emitting_port_units: Units,
        carbon_port: str,
        emissions_factor: Union[float, ArrayType],
        **data,
    ):
        super().__init__(**data)
        self.ports[emitting_port] = FlexPort(port_name=emitting_port, units=emitting_port_units)
        self.ports[carbon_port] = CarbonSource()
        self.add_emission_transformation(
            emitting_port=self.ports[emitting_port],
            carbon_port=self.ports[carbon_port],
            emission_factor=emissions_factor,
        )


class DieselGenerator(InputOutputNode):
    """
    A diesel generator node. Converts diesel into electricity at a fixed rate of cop which is in units of
    kW/liters per second
    """

    input_port_unit = Units.LPS
    output_port_unit = Units.KW
    cop: NonNegativeFloat = 0.4 * 3600  # kW / litres per second
    startup_efficiency: NonNegativeFloat = (
        0.5  # ratio of efficiency in startup and shutdown period, # todo: ensure between 0-1 (confloat??)
    )
    C02Intensity: NonNegativeFloat = 2.7  # emissions intensity kg per sec / litre per sec = kg/litre

    def __init__(self, **data) -> None:
        super().__init__(**data)
        # add an input and output node, and create appropriate transformations
        self.ports["output"] = OffOrConstrainedPort(
            upper_bound=self.min_output, lower_bound=self.max_output, units=self.output_port_unit
        )

        self.ports["input"] = FlexSink(units=self.input_port_unit)  # the node is importing through this port
        self.ports["co2"] = CarbonSource()
        # todo: add some validators :-)

    def apply_node_constraints(self, model: EchoConcreteModel):
        super(DieselGenerator, self).apply_node_constraints(model)

        def node_constraint(model: EchoConcreteModel, p, t):
            p_in = getattr(model, self.ports["input"].port_name)
            p_out = getattr(model, self.ports["output"].port_name)

            if (p == 0) and (t == 0):
                out = p_in[p, t] * self.startup_efficiency * self.cop
            else:
                out = (p_in[p, t] * self.startup_efficiency + p_in[p, t - 1] * (1 - self.startup_efficiency)) * self.cop
            return p_out[p, t] == -out

        def carbon_rule(model: EchoConcreteModel, p, t):
            p_in = getattr(model, self.ports["input"].port_name)
            c_out = getattr(model, self.ports["co2"].port_name)
            return c_out[p, t] == -p_in[p, t]

        setattr(model, "node_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=node_constraint))
        setattr(model, "node_con_co2_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=carbon_rule))
