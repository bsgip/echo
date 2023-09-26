class ConfigurationError(Exception):
    pass


class OptimiserResultError(Exception):
    """Raised when a particular termination condition is not met when running an optimisation"""

    pass


def validate(statement: bool, message: str):
    """Similar to assert but will NOT be optimised out by bytecode conversions (see bandit warning B101)"""
    if statement:
        return

    raise ConfigurationError(message)
