from echo.configuration import Units
from echo.models.agnostic.flex import FlexPort
from echo.models.agnostic.tellegen.three_way_valve import ThreeWayValveNode


def test_threeway_tellegen_node(empty_model):
    """Test asset creation and pyomo constraints"""

    node = ThreeWayValveNode(
        node_name="three_way_valve",
        units=Units.KW,
        input_port_name="port_1",
        output_port_name_1="port_2",
        output_port_name_2="port_3",
    )
    model = empty_model()
    node.add_node_to_model(model, profile=None)
    node.apply_node_constraints(model)
    assert getattr(model, node.constraint_neg_flow_mutually_exclusive_port_1) is not None
    assert getattr(model, node.constraint_neg_flow_mutually_exclusive_port_2) is not None
    assert getattr(model, node.constraint_pos_flow_mutually_exclusive_port_1) is not None
    assert getattr(model, node.constraint_pos_flow_mutually_exclusive_port_2) is not None


def test_threeway_tellegen_node_add_port(empty_model):
    """Test asset creation, add ports and pyomo constraints"""

    node = ThreeWayValveNode(
        node_name="three_way_valve",
        units=Units.KW,
        input_port_name="port_1",
        output_port_name_1="port_2",
        output_port_name_2="port_3",
    )
    node.add_port(name="port_4", port=FlexPort(units=Units.KW))
    node.add_port(name="port_5", port=FlexPort(units=Units.KW))
    model = empty_model()
    node.add_node_to_model(model, profile=None)
    node.apply_node_constraints(model)
    assert getattr(model, node.constraint_neg_flow_mutually_exclusive_port_1) is not None
    assert getattr(model, node.constraint_neg_flow_mutually_exclusive_port_2) is not None
    assert getattr(model, node.constraint_pos_flow_mutually_exclusive_port_1) is not None
    assert getattr(model, node.constraint_pos_flow_mutually_exclusive_port_2) is not None
