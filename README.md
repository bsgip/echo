<p align="center">
  <a href="https://github.com/bsgip/echo"><img width="400" height="120" src="https://github.com/bsgip/echo/blob/c56b6362f2143468cd0524087f5a3ea9c2078cfb/docs/source/images/echo.png" alt='echo'></a>
</p>

<p align="center"><strong>echo</strong> <em>- An energy and commodity holistic optimiser.</em></p>

<p align="center">
<a href="https://github.com/bsgip/echo/actions/">
    <img src="https://github.com/bsgip/echo/actions/workflows/linttest.yml/badge.svg" alt="Test Suite">
</a>
<a href="https://pypi.org/project/eris-echo">
    <img src="https://badge.fury.io/py/eris-echo.svg" alt="PyPI version">
</a>
</p>

echo is a python-based multi-commodity energy system optimisation tool designed for answering grid integration questions.

echo is part of the [Eris](https://bsgip.github.io/eris/) collection of energy modelling tools. echo and Eris are developed and maintained by the [ANU Centre for Energy Systems (ACES)](https://energysystems.anu.edu.au/) at the Australian National University.

---

Install echo with pip:

```sh
pip install eris-echo
```

Install a solver.

echo requires a third party solver to optimise energy modelling scenarios. [cplex](https://www.ibm.com/products/ilog-cplex-optimization-studio) is our preferred solver. See the [documentation](https://bsgip.github.io/echo/getting_started.html#solver-executable) for details of compatible solvers and how to interface them with echo.

## Tutorial

Point to documentation

Concepts

Examples

- [Simple behind the meter network](https://github.com/bsgip/echo/blob/8e05610958ad12f4d653a542a9f7b35e7f985381/examples/simple_behind_the_meter_network.py)
- [Neighbourhood battery with aggregate load](https://github.com/bsgip/echo/blob/8e05610958ad12f4d653a542a9f7b35e7f985381/examples/neighbourhood_battery_with_aggregate_load.py)

More examples can be found in the [examples directory](https://github.com/bsgip/echo/tree/8e05610958ad12f4d653a542a9f7b35e7f985381/examples).

## Contributing

The echo project welcomes [contributions](https://github.com/bsgip/echo/blob/8e05610958ad12f4d653a542a9f7b35e7f985381/CONTRIBUTING.md).



## Issues

Please log any issues in the [issue tracker](https://github.com/bsgip/echo/issues).

## Roadmap

echo is being actively developed...

| Item                               | Status      | Reference                                  | Completion Date |
| ---------------------------------- | ----------- | ------------------------------------------ | --------------- |
| Add ruff and uv                    | Complete    |                                            | Jun 2026        |
| Add ty                             | Planning    |                                            | Aug 2026        |
| Documentation update               | Underway    |                                            | Sep 2026        |
| Examples update                    | Underway    |                                            | Sep 2026        |
| Standardise data injection process | Planning    | <https://github.com/bsgip/echo/issues/103> | Sep 2026        |
| Migrate from Pydantic to Attrs     | Complete    | <https://github.com/bsgip/echo/issues/101> | Oct 2026        |
| Add linopy as parser option        | Planning    | <https://github.com/bsgip/echo/issues/102> | Dec 2026        |
