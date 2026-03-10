# echo (energy and commodity holistic optimiser)


## Installation

This package requires that you have python 3.7+ installed and it is recommended you use a virtual environment.

To install this package you need to:

1. Clone this repo:
```
git clone git@github.com:bsgip/echo.git
```

2. Change to the echo directory:
```
cd echo
```

3. With your virtual environment active install using pip:
```
pip install --group all .
```

NOTE: This package is not on pypi - `pip install echo` will NOT install this package. It will install a different package with the same name.

### [Optional]
If you plan to use echo_scenario to solve power flows then you will need to install sgt and sgt-e-json.

1. Install SmartgridToolbox by following the instructions [here](https://gitlab.com/SmartGridToolbox/SmartGridToolbox).
2. Install the SmartGridToolbox python bindings by following the instructions [here](https://smartgridtoolbox.gitlab.io/SmartGridToolbox/python_bindings.html).
3. Install sgt-e-json and its python bindings following instructions [here](https://gitlab.com/SmartGridToolbox/sgt-e-json).
4. If pip install of the sgt-e-json python bindings failed, then a work around is to run `python setup.py`.

## Solver
The following solvers can be used

Free for academic use only:
- CPLEX (recommended): This has been tested the most. It requires a license but is free for academic users. To install, follow instructions [here](https://www.ibm.com/products/ilog-cplex-optimization-studio). After installing CPLEX you will need to add the binaries to your system path. 
- GUROBI: Minimal testing: It requires a license but is free for academic users. Check their website for installation [instructions](https://www.gurobi.com/documentation/9.5/remoteservices/linux_installation.html).

Open source:
- CBC: This solver can be used provided you only include linear costs (no quadratic costs or regularisation). Information on the solver is available [here](https://github.com/coin-or/Cbc). For installing on ubuntu run `sudo apt-get install -y coinor-cbc`


## Documentation

### Building the documentation

Make sure you have the documentation dependencies installed

```
pip install --group docs .
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



