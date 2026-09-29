import pytest

from echo.objectives.base import Objective

SHORTUUID_LENGTH = 22


@pytest.mark.parametrize("name", [None, "objective-name"])
def test_objective(name):
    if name:
        objective = Objective(name=name)
        assert objective.name == name
    else:
        objective = Objective()
        assert objective.name.endswith(objective.uid)

    assert len(objective.uid) == SHORTUUID_LENGTH
