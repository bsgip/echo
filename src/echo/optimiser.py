from dataclasses import dataclass

from echo.models.scenario import EchoConcreteModel


@dataclass
class OptimisationResult:
    model: EchoConcreteModel
