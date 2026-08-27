import numpy as np

from echo.validators import ArrayType

ConstraintValueType = ArrayType | float
InitialValue = dict[tuple[int, int], int | float]
InitialValueInput = InitialValue | list[int | float] | np.ndarray
