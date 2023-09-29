from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
from typing import Collection, Optional, Union

import numpy as np
import pandas as pd
import pyomo.environ as en
from pyomo.opt import SolverFactory, SolverResults, SolverStatus, TerminationCondition

from echo.exceptions import ConfigurationError, OptimiserResultError, validate
from echo.models.base import Node, OptimisationGraph, Port
from echo.models.scenario import EchoConcreteModel, EngineSettings, ScenarioSettings
from echo.objectives.base import Objective, ObjectiveSet

# The default set of termination conditions that pyomo can return and echo will report as a success
DEFAULT_ACCEPTABLE_TERMINATION_CONDITIONS: Collection[TerminationCondition] = set(
    [
        TerminationCondition.feasible,
        TerminationCondition.globallyOptimal,
        TerminationCondition.locallyOptimal,
        TerminationCondition.optimal,
    ]
)


@contextmanager
def logged_stdout(logfile: Optional[str], mode: str = "w"):
    """Context manager that while held open will redirect all stdout to logfile. If the logfile is None then
    no redirection will occur"""
    if logfile is None:
        yield None
    else:
        with open(logfile, mode) as f:
            with redirect_stdout(f):
                yield


@dataclass
class OptimisationResult:
    """Describes the set of results from a successful optimisation run. It will provide a set of utilities
    for accessing result data for the scenario that created this result"""

    scenario_settings: ScenarioSettings
    objective: en.numeric_expr.NumericExpression
    model: EchoConcreteModel
    objective_set: Optional[ObjectiveSet]
    graph: OptimisationGraph
    opt_status: str

    def df(self):
        """
        Extract all vars from the solution as a dataframe
        """
        # todo extend this to do other nice things
        dct = {}

        for var_obj in self.model.component_objects(en.Var):
            if "soc" in var_obj.name:
                dct[var_obj.name] = var_obj.extract_values()
            if "port" in var_obj.name:
                dct[var_obj.name] = var_obj.extract_values()

        # Handle multiple indexes
        df = pd.DataFrame(dct)

        return df

    def df_by_node(self):
        """Returns a df of results by node, using the port names given in each node's 'ports' dict"""
        dct = {}
        for node_name, node in self.graph.node_obj.items():
            for port_name, p in node.ports.items():
                dct[node_name + "-" + port_name] = getattr(self.model, p.port_name).extract_values()

        df = pd.DataFrame(dct)
        return df

    def df_by_port(self):
        """Returns a df of results by port, using port names given in each node's 'ports' dict"""
        dct = {}
        for node_name, node in self.graph.node_obj.items():
            for port_name, p in node.ports.items():
                if dct.get(port_name) is not None:
                    # We have an existing key - make a new name using the node name
                    dct[port_name + "_node_" + node_name] = getattr(self.model, p.port_name).extract_values()
                else:
                    dct[port_name] = getattr(self.model, p.port_name).extract_values()

        df = pd.DataFrame(dct)
        return df

    def values(self, variable_name, expansion=0):
        """Returns the value of a single specified variable during a single specified expansion period."""

        var_obj = getattr(self.model, variable_name)
        if var_obj.dim() == 2:
            # the variable/param has two indices - we assume these are expansion and time
            output = np.zeros(self.scenario_settings.number_of_intervals)
            max_planning_period = 0
            for index in var_obj:
                if index[0] == expansion:
                    try:
                        output[index[1]] = var_obj[index].value
                    except AttributeError:
                        output[index[1]] = var_obj[index]
                max_planning_period = max(max_planning_period, index[0])
            if expansion > max_planning_period:
                raise ConfigurationError("Expansion period is not in range.")
            return output
        else:
            # the variable/param doesn't have two indices
            if var_obj.is_indexed():
                # if it has one, then work out what that one is:
                output = np.zeros(len(var_obj))
                for i in var_obj:
                    output[i] = var_obj[i].value
                return output
            else:
                # if it has no index, we can directly return value
                return var_obj.value

    def node_values(self, node_obj: Node, expansion_period=0):
        """Returns all values of all ports in a specified node for a single specified expansion period."""
        outputs = {}
        for name, var_obj in node_obj.ports.items():
            outputs[name] = self.values(var_obj.port_name, expansion_period)
        return outputs

    def get_single_objective_total_value(self, objective_obj: Objective):
        """Returns the value of a single objective."""
        return objective_obj.get_objective_total(model=self.model)

    def get_total_objective_value(self):
        """Returns the value of the objective function."""
        return en.value(self.objective)

    def get_total_objective_at_port(self, port_obj: Port):
        """Sums all objectives that take the defined port as their component."""
        total = 0
        if self.objective_set:
            for obj in self.objective_set.objective_list:
                if obj.component == port_obj:
                    total += obj.get_objective_total(model=self.model)
        return total


def validate_network_graph(graph: OptimisationGraph):
    """
    Validates that a pyomo model can be built from the provided network graph. Checks for:
    - name consistency between objects (e.g. node.node_name) and graph nodes
    - floating nodes that have no edge connecting them to another node
    """
    for node_name, node_obj in graph.node_obj.items():
        validate(
            node_obj.node_name == node_name,
            "Node {} name has been updated after being added to the network graph.".format(node_name),
        )

    graph.verify_graph()


def build_model_and_objective(
    graph: OptimisationGraph,
    scenario_settings: ScenarioSettings,
    engine_settings: EngineSettings,
    profile: Optional[pd.DataFrame],
    objective_set: Optional[ObjectiveSet],
) -> tuple[EchoConcreteModel, en.numeric_expr.NumericExpression]:
    """Builds an EchoConcreteModel for a particular Echo Scenario definition and a related objective to optimise
    against the model"""
    # Set up the Pyomo model
    model = EchoConcreteModel()
    model.scenario_settings = scenario_settings

    # Bias Values

    # A small fudge factor for reducing the size of the solution set and
    # achieving a unique optimisation solution
    model.smallM = en.Param(initialize=engine_settings.smallM)
    # A bigM value for integer optimisation
    model.bigM = en.Param(initialize=engine_settings.bigM)

    # We use RangeSet to create an index for each of the time
    # periods that we will optimise within.
    model.Time = en.RangeSet(0, scenario_settings.number_of_intervals - 1)
    # Create index for expansion periods
    if scenario_settings.number_of_expansion_intervals == 0:
        model.Expansion = en.RangeSet(0, 0)
    else:
        model.Expansion = en.RangeSet(0, scenario_settings.number_of_expansion_intervals - 1)

    # Setup discounting
    dr = {}
    for ep in range(0, scenario_settings.number_of_expansion_intervals):
        dr[ep] = 1 / ((1 + scenario_settings.discount_rate) ** ep)

    model.discount_rates = en.Param(model.Expansion, initialize=dr)

    # Initialise node variables/params and add node constraints
    for _, node_obj in graph.node_obj.items():
        node_obj.verify_node()
        node_obj.initialise_node(model, profile)

    # Initialise edge variables/params and add edge constraints
    for _, edge_obj in graph.edge_obj.items():
        edge_obj.verify_edge()
        edge_obj.initialise_edge(model)

    # Initialise paths
    for _, path in graph.paths.items():
        path.initialise_path(model)

    # Apply constraints
    for _, obj in graph.node_obj.items():
        obj.apply_node_constraints(model)
    if graph.paths:
        graph.apply_path_constraints(model)

    # Build objective
    objective: Union[float, en.numeric_expr.NumericExpression] = 0

    # Add objectives defined in the objective set
    if objective_set is not None:
        objective_set.initialise_objective(model, profile)
        objective += objective_set.get_objective_total(model)

    # Add any other costs that are defined on graph nodes/ports/paths
    for _, node_obj in graph.node_obj.items():
        node_obj.add_objective(model)
        objective += node_obj.objective
        for _, port_obj in node_obj.ports.items():
            port_obj.add_objective(model)  # populate the .objective attribute for each port
            objective += port_obj.objective  # add the newly populated attribute to our total

    for _, path_obj in graph.paths.items():
        path_obj.add_objective(model)
        objective += path_obj.objective

    return model, objective


def optimise(
    scenario_settings: ScenarioSettings,
    engine_settings: EngineSettings,
    graph: OptimisationGraph,
    objective_set: Optional[ObjectiveSet] = None,
    profile: Optional[pd.DataFrame] = None,
    verbose: bool = False,
    logfile: Optional[str] = None,
    acceptable_conditions: Collection[TerminationCondition] = DEFAULT_ACCEPTABLE_TERMINATION_CONDITIONS,
) -> OptimisationResult:
    """Runs the optimiser with the specified settings. Returns an OptimisationResult that can be queried
    using the supplied graph.

    Will attempt to validate the graph and will raise exceptions if it appears invalid / unsolvable

    verbose: If set to True the solver will operate in verbose mode and print additional output to stdout
    logfile: If set to a file path - the stdout will be redirected to this file (for the duration of this run)
    acceptable_conditions: OptimiserResultError will be raised if the pyomo termination condition is not in this set"""

    validate_network_graph(graph)

    (model, objective) = build_model_and_objective(graph, scenario_settings, engine_settings, profile, objective_set)

    def objective_function(model: EchoConcreteModel):
        return objective

    model.total_cost = en.Objective(rule=objective_function, sense=en.minimize)

    # Set the path to the solver
    if engine_settings.engine_executable:
        opt = SolverFactory(engine_settings.engine, executable=engine_settings.engine_executable)
    else:
        opt = SolverFactory(engine_settings.engine)

    # Run the optimisation, logging everything to the specified file
    with logged_stdout(logfile):
        if verbose:
            model.pprint(verbose=True)
        results: SolverResults = opt.solve(model, tee=True, symbolic_solver_labels=True)

    # Extract the optimisation result
    termination_condition: TerminationCondition = results.solver.termination_condition
    solver_status: SolverStatus = results.solver.status

    if solver_status != SolverStatus.ok:
        raise OptimiserResultError(f"Solver status returned as {solver_status}")

    if termination_condition not in acceptable_conditions:
        raise OptimiserResultError(
            f"Termination condition '{termination_condition}' is not in acceptable set  of {acceptable_conditions}"
        )
    opt_status = results["Solver"][0]

    return OptimisationResult(
        scenario_settings=scenario_settings,
        objective=objective,
        model=model,
        objective_set=objective_set,
        graph=graph,
        opt_status=opt_status,
    )
