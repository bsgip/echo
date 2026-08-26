from __future__ import annotations  # Deprecating in python 3.15 in favour of lazy annotations (PEP 649 and 749)

from dataclasses import dataclass

import pyomo.environ as en
import shortuuid
from pydantic import Field
from pyomo.core.expr.relational_expr import EqualityExpression

from echo.configuration import TransformRule
from echo.exceptions import ConfigurationError
from echo.models.base import BaseModel
from echo.models.base.node import Node
from echo.models.base.port import Port
from echo.models.scenario import EchoConcreteModel
from echo.utils import (
    TimeExpandableType,
    TimeSeriesData,
    expand_as_array,
)


@dataclass
class TransformTerm:
    var: Port
    rule: TransformRule
    weight: TimeExpandableType


class Transform(BaseModel):
    """An object for carrying a generic linear node transformation."""

    uid: str = Field(default_factory=shortuuid.uuid)
    lhs: list[TransformTerm] = []
    rhs = 0

    def __init__(self, lhs_terms: list[TransformTerm], **data) -> None:
        super().__init__(**data)
        if lhs_terms:
            self.lhs = lhs_terms

    @property
    def transform_name(self) -> str:
        return "transform_" + str(self.uid)

    def _add_transform_to_model(self, model: EchoConcreteModel) -> None:
        # Check if we need to create pos/neg components
        for term in self.lhs:
            if term.rule is not TransformRule.Both:
                var = term.var
                var.constrain_pos_neg(model)


class TransformNode(Node):
    """Implements node constraints using Transforms"""

    transformations: dict[str, Transform] = {}

    def add_transformation(self, transformation_obj: Transform) -> None:
        """Adds a transformation object to a node.

        Args:
            transformation_obj: The Transform to be added to the node.

        Returns:
            None
        """

        self.transformations[transformation_obj.uid] = transformation_obj

    def add_input_output_transformation(self, input_port: Port, output_port: Port, input_weight: float) -> None:
        """Adds an input/output transformation to this node.

        Args:
            input_port: The input port for the transformation
            output_port: The output port for the transformation
            input_weight: The weighting for the TransformTerm of the input port.

        Returns:
            None

        """

        lhs_terms = [
            TransformTerm(var=output_port, rule=TransformRule.Both, weight=1),
            TransformTerm(var=input_port, rule=TransformRule.Both, weight=-input_weight),
        ]

        t = Transform(lhs_terms=lhs_terms)

        self.add_transformation(t)

    def add_emission_transformation(self, emitting_port: Port, carbon_port: Port, emission_factor: float) -> None:
        """Creates an emission transformation and adds to the node.

        Args:
            emitting_port: port object that generates emissions when exporting (when negative)
            carbon_port: port object that represents carbon flows out of the node
            emission_factor: a ratio = emissions generated/emitting unit generated (float), or an array of values

        Returns:
            None
        """

        lhs_terms = [
            TransformTerm(var=carbon_port, rule=TransformRule.Neg, weight=1),
            TransformTerm(var=emitting_port, rule=TransformRule.Neg, weight=-emission_factor),
        ]

        t = Transform(lhs_terms=lhs_terms)

        self.add_transformation(t)

    def verify_node(self) -> None:
        """Checks if the node has ports (super), and if the node has transformations.

        Returns:
            None

        Raises:
            ConfigurationError: If no transformations are associated with this node.
        """

        super().verify_node()

        if not self.transformations:
            raise ConfigurationError("Node has Transform rule but Transformation object(s) has not been added to node.")

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        """Add the constraints assoicated with this node to a concrete model.

        Args:
            model: The concrete model the constraints associated with this node will be added to.

        """

        def transform(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            """Generate a transform rule for a generic transformation node.

            Args:
                model: The concrete model from which to draw data.
                p: Index representing capacity expansion
                t: Index representing time.

            Returns:
                EqualityExpression: The transform rule.

            Raises:
                Exception: If an improper TransformRule is used.
            """

            lhs = 0

            for term in current_transform.lhs:
                weight = expand_as_array(
                    TimeSeriesData(
                        value=term.weight,
                        num_expansion_intervals=len(model.Expansion),
                        num_time_intervals=len(model.Time),
                    )
                )

                rule = term.rule

                if rule is TransformRule.Both:
                    var_name = term.var.port_name
                elif rule is TransformRule.Pos:
                    var_name = term.var.pos
                elif rule is TransformRule.Neg:
                    var_name = term.var.neg
                else:
                    raise Exception(f"Unsupported transform rule {rule} for term {term}")

                lhs += getattr(model, var_name)[p, t] * weight[p, t]

            return lhs == current_transform.rhs

        for current_transform in self.transformations.values():
            current_transform._add_transform_to_model(model)  # make sure that all variables have been initialised
            con_name = "transformation_con_" + self.node_name
            setattr(
                model,
                con_name,
                en.Constraint(model.Expansion, model.Time, rule=transform),
            )
