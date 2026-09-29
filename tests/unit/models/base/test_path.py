import pytest
from pydantic import ValidationError

from echo.models.base.path import Path

SHORTUUID_LENGTH = 22


def test_path_initialisation_missing_required_params():
    # required parameters: vertices
    with pytest.raises(ValidationError):
        Path()


@pytest.mark.parametrize("path_name", [None, "path-name"])
def test_path_initialisation(path_name):
    required_params = {"vertices": []}

    path = Path(path_name=path_name, **required_params)

    assert len(path.uid) == SHORTUUID_LENGTH

    assert path.path_name is not None
    if path_name:
        assert path.path_name == path_name
    else:
        assert path.path_name.endswith(path.uid)
