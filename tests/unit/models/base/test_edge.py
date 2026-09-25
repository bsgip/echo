import pytest
from pydantic import ValidationError

from echo.models.base.edge import Edge
from echo.models.base.port import Port

SHORT_UID_LENGTH = 22


def test_edge_initialisation_missing_required_params():
    # required parameters: vertices
    with pytest.raises(ValidationError):
        Edge()


@pytest.mark.parametrize("edge_name", [None, "edge-name"])
def test_edge_initialisation(edge_name):
    port_1 = Port()
    required_params = {"vertices": (port_1, port_1)}

    edge = Edge(edge_name=edge_name, **required_params)

    assert len(edge.uid) == SHORT_UID_LENGTH

    assert edge.edge_name is not None
    if edge_name:
        assert edge.edge_name == edge_name
    else:
        assert edge.edge_name.endswith(edge.uid)
