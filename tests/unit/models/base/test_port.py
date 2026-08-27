import numpy as np

from echo.models.base.port import Port


def test_port_proccess_initial_value_types():
    port = Port(port_name="port_name")

    # Assert the initial value is None before it's set
    assert port.initial_value is None

    # Assert list of ints is processed
    port.process_initial_value(initial_val=[1, 2, 3])
    assert port.initial_value == {(0, 0): 1, (0, 1): 2, (0, 2): 3}

    # Assert list of floats is processed
    port.process_initial_value(initial_val=[1.0, 2.0, 3.0])
    assert port.initial_value == {(0, 0): 1.0, (0, 1): 2.0, (0, 2): 3.0}

    # Assert a dict of ints is processed
    port.process_initial_value(initial_val={(0, 0): 1, (0, 1): 2, (0, 2): 3})
    assert port.initial_value == {(0, 0): 1, (0, 1): 2, (0, 2): 3}

    # Assert a dict of ints is processed
    port.process_initial_value(initial_val={(0, 0): 1.0, (0, 1): 2.0, (0, 2): 3.0})
    assert port.initial_value == {(0, 0): 1.0, (0, 1): 2.0, (0, 2): 3.0}

    # Assert a numpy array of ints is processed
    port.process_initial_value(initial_val=np.array([1, 2, 3]))
    assert port.initial_value == {(0, 0): 1, (0, 1): 2, (0, 2): 3}

    # Assert a numpy array of floats is processed
    port.process_initial_value(initial_val=np.array([1.0, 2.0, 3.0]))
    assert port.initial_value == {(0, 0): 1.0, (0, 1): 2.0, (0, 2): 3.0}
