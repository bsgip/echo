import pytest

from echo.models.base.path import Path

SHORTUUID_LENGTH = 22


def test_path_initialisation_missing_required_params():
    # required parameters: vertices
    with pytest.raises(TypeError):
        Path()


@pytest.mark.parametrize("path_name", [None, "path-name"])
def test_path_initialisation(path_name):
    required_params = {"vertices": []}
    params = {"path_name": path_name} if path_name else {}

    path = Path(**params, **required_params)

    assert len(path.uid) == SHORTUUID_LENGTH

    assert path.path_name is not None
    if path_name:
        assert path.path_name == path_name
    else:
        assert path.path_name.endswith(path.uid)

    assert path.flow_value == "flow_value_" + path.path_name
