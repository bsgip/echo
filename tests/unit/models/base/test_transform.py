from echo.models.base.port import Port
from echo.models.base.transform import Transform, TransformNode, TransformRule, TransformTerm


def test_transform_initialisation():
    port = Port()
    term1 = TransformTerm(var=port, rule=TransformRule.Both, weight=1)
    term2 = TransformTerm(var=port, rule=TransformRule.Both, weight=1)

    transform_terms = [term1, term2]
    transform = Transform(lhs_terms=transform_terms)

    assert transform.lhs == transform_terms


def test_transform_initialisation_mutable_default():
    t1 = Transform(lhs_terms=[])
    t2 = Transform(lhs_terms=[])

    assert t1.lhs is not t2.lhs


def test_transformnode_initialisation_mutable_default():
    tn1 = TransformNode()
    tn2 = TransformNode()

    assert tn1.transformations is not tn2.transformations
