import pytest

from echo.configuration import Units
from echo.models.agnostic import InputOutputNode
from echo.models.agnostic.flex import FlexPort


@pytest.mark.parametrize(
    "params",
    [
        {
            "input_port_ref": "in",
            "output_port_ref": "out",
            "input_port_unit": Units.KW,
            "output_port_unit": Units.JPS,
        },  # both input and output port refs defined
        {
            "output_port_ref": "out",
            "input_port_unit": Units.KW,
            "output_port_unit": Units.JPS,
        },  # no input_port_ref defined
        {
            "input_port_ref": "in",
            "input_port_unit": Units.KW,
            "output_port_unit": Units.JPS,
        },  # no output_port_ref defined
    ],
)
def test_inputoutputnode_initialisation(params):
    node = InputOutputNode(**params)
    input_name = params["input_port_ref"] if "input_port_ref" in params else "input"
    assert input_name in node.ports
    assert isinstance(node.ports[input_name], FlexPort)
    assert node.ports[input_name].units == params["input_port_unit"]

    output_name = params["output_port_ref"] if "output_port_ref" in params else "output"
    assert output_name in node.ports
    assert isinstance(node.ports[output_name], FlexPort)
    assert node.ports[output_name].units == params["output_port_unit"]
