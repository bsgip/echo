# echo (energy and commodity holistic optimiser)


## Installation

This package requires that you have python 3.7+ installed and it is recommended you use a virtual environment.

To install this package you need to:

1. clone this repo
```
git clone git@github.com:bsgip/echo.git
```

2. Change to the echo directory
```
cd echo
```

3. With your virtual environment active install using pip
```
pip install .[dev,test,docs]
```

NOTE: This package is not on pypi. Doing `pip install echo` will NOT install this package. It will install a different package.

### [Optional]
If you plan to use echo_scenario to solve power flows then you will need to install sgt and sgt-e-json.

1. Install SmartgridToolbox by following the instructions here https://gitlab.com/SmartGridToolbox/SmartGridToolbox
2. Install the SmartGridToolbox python bindings by following the instructions here https://smartgridtoolbox.gitlab.io/SmartGridToolbox/python_bindings.html
3. Install sgt-e-json and its python bindings following instructions here https://gitlab.com/SmartGridToolbox/sgt-e-json
4. If pip install of the sgt-e-json python bindings failed, then a work around is to run `python setup.py`

## Solver
The following solvers can be used

Free for academic use only:
- CPLEX (recommended): This has been tested the most. It requires a license but is free for academic users. To install, follow instructions [here](https://www.ibm.com/products/ilog-cplex-optimization-studio). After installing CPLEX you will need to add the binaries to your system path.
- GUROBI: Minimal testing: It requires a license but is free for academic users. Check their website for instructions on installing https://www.gurobi.com/documentation/9.5/remoteservices/linux_installation.html

Open source:
- CBC: This solver can be used provided you only include linear costs (no quadratic costs or regularisation). Information on the solver is available here https://github.com/coin-or/Cbc . For installing on ubuntu run `sudo apt-get install -y coinor-cbc1


## Testing

### Running Tests

The test suite can be run with,

```sh
$ pytest
```

This will run the tests using the default optimiser engine (currently set to `cbc`). We default to `cbc` since this is the only solver available to the Github action.

Some of the tests require a solver capable of performing non-linear optimisations. The `cbc` solver is not able to do this. To run the complete set of tests, you will need to have a solver capable of non-linear optimizations (for example `cplex`) installed on your system. You can run pytest and override the default solver using the environment variable `TESTING_OPTIMISER_ENGINE`. For example:

```sh
$ TESTING_OPTIMISER_ENGINE=cplex pytest
```

See the section below 'Writing tests', for instructions on how to mark a test as requiring a non-linear solver.

### Writing tests

Most tests will require an `engine_settings` object. A fixture `engine_settings` has been provided, which should be used by any tests that require engine settings. It is strongly recommended **not** to use `scenario.engine_settings_from_environment()` in order to obtain an engine settings object, since this can result in the your newly-written tests running on a different solver to the rest of the test suite.

A small number of tests might need to be run with a solver capable of non-linear optimizations. These tests should be marked with a special pytest mark decorator:

```py
import pytest

@pytest.mark.nonlinear
def test_that_requires_nonlinear_solver():
    ...
```

### Tox

Tox makes it easy to test echo on multiple versions of python. The configuration file for tox is called `tox.ini`, which
is located in the project root. Looking in `tox.ini`, the `env_list` parameter lists all the environments we will test against.

To prevent echo developers having to install all the different versions of python on their system, tox has been setup
to run in a docker container.

To test with tox, the first step is to build the docker image,

```sh
docker build -f Dockerfile-tox -t echo-tox:latest .
```

This should only need doing once. Re-run the docker build command if you modify the Dockerfile, `Dockerfile-tox`.

The test suite can be run across the different environments (python versions) with,

```sh
docker run -t --volume .:/opt/tox/echo echo-tox:latest -- -W ignore::DeprecationWarning
```

- The command that gets run is `tox`, which you can see by looking at the `ENTRYPOINT` in the Dockerfile, `Dockerfile-tox`.
- The `-t` gives us colored output in the terminal.
- The `--volume` switch mounts echo project inside the container
- Arguments/options before the `--` are passed to `tox`. Anything after `--` is passed to the command `tox` runs i.e. `pytest`. In this case we are using `-W ignore::DeprecationWarning` to suppress an error raised because of deprecated datetime code in pandas (or one of its dependencies)

## Documentation

### Building the documentation

Make sure you have the documentation dependencies installed

```
pip install .[docs]
```

1. Generate the documentation for the echo package (from docstrings)

```
sphinx-apidoc --force --implicit-namespaces --module-first --no-toc --separate -o docs/source/_reference src/echo
```

The auto-generated documentation can be found in `docs/source/_reference`

2. Build the documentation (as html)

```
sphinx-build -b html docs/source docs/_build
```

The built documentation can be found in `docs/_build`. Warnings about duplicated labels can be safely ignored.

### Design (under creation)
Please see the design file [here](https://github.com/bsgip/echo/blob/V1/design.md).

## Issues
Please log any issues in the [issue tracker](https://github.com/bsgip/echo/issues).



