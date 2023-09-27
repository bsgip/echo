import os


def can_optimiser_do_non_linear_optimisation() -> bool:
    # This test contains non-linear optimisation, so cbc won't be able to run it. Check the environment and skip this
    # test if cbc is the optimiser engine
    optimiser_engine = os.environ.get("OPTIMISER_ENGINE")

    if optimiser_engine == "cbc":
        return False

    return True
