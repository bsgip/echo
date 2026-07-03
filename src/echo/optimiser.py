import warnings
from collections.abc import Collection, Generator
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pyomo.environ as en
from pyomo.opt import SolverFactory, SolverResults, SolverStatus, TerminationCondition

from echo.exceptions import ConfigurationError, OptimiserResultError, validate
from echo.models.base import Node, OptimisationGraph, Port
from echo.models.scenario import EchoConcreteModel, EngineSettings, ScenarioSettings
from echo.objectives.base import Objective, ObjectiveSet
from echo.tracker import AttributeTracker

# The default set of termination conditions that pyomo can return and echo will report as a success
DEFAULT_ACCEPTABLE_TERMINATION_CONDITIONS: Collection[TerminationCondition] = set(
    [
        TerminationCondition.feasible,
        TerminationCondition.globallyOptimal,
        TerminationCondition.locallyOptimal,
        TerminationCondition.optimal,
        TerminationCondition.maxIterations,
        TerminationCondition.maxTimeLimit,
    ]
)


@contextmanager
def logged_stdout(logfile: str | None, mode: str = "w") -> Generator[None]:
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
    for accessing result data for the scenario that created this result
    """

    scenario_settings: ScenarioSettings
    objective: en.numeric_expr.NumericExpression | None
    model: EchoConcreteModel
    objective_set: ObjectiveSet | None
    graph: OptimisationGraph
    opt_status: SolverStatus
    termination_condition: TerminationCondition
    model_attribute_tracker: AttributeTracker | None = None

    def df(self) -> pd.DataFrame:
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

    def df_by_node(self) -> pd.DataFrame:
        """Returns a df of results by node, using the port names given in each node's 'ports' dict"""
        dct = {}
        for node_name, node in self.graph.node_obj.items():
            for port_name, p in node.ports.items():
                dct[node_name + "-" + port_name] = getattr(self.model, p.port_name).extract_values()

        df = pd.DataFrame(dct)
        return df

    def df_by_port(self) -> pd.DataFrame:
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

    def df_objective_by_port(self, index: set | None = None) -> pd.DataFrame:
        """Return the value of each objective assigned to each port."""

        # If the index is None, set it to {1}
        if index is None:
            index = {1}

        dct = {}
        for obj in self.objective_set.objective_list:
            dct[obj.component.port_name + "-" + obj.name] = self.get_single_objective_total_value(obj)

        return pd.DataFrame(dct, index=index)

    def values(self, variable_name: str, expansion: int = 0) -> np.ndarray:
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

    def node_values(self, node_obj: Node, expansion_period: int = 0) -> dict[str, np.ndarray]:
        """Returns all values of all ports in a specified node for a single specified expansion period."""
        outputs = {}
        for name, var_obj in node_obj.ports.items():
            outputs[name] = self.values(var_obj.port_name, expansion_period)
        return outputs

    def get_single_objective_total_value(self, objective_obj: Objective) -> float:
        """Returns the value of a single objective."""
        return objective_obj.get_objective_total(model=self.model)

    def get_total_objective_value(self) -> float:
        """Returns the value of the objective function."""
        return en.value(self.objective)

    def get_total_objective_at_port(self, port_obj: Port) -> float:
        """Sums all objectives that take the defined port as their component."""
        total = 0
        if self.objective_set:
            for obj in self.objective_set.objective_list:
                if obj.component == port_obj:
                    total += obj.get_objective_total(model=self.model)
        return total


def validate_network_graph(graph: OptimisationGraph) -> None:
    """
    Validates that a pyomo model can be built from the provided network graph. Checks for:
    - name consistency between objects (e.g. node.node_name) and graph nodes
    - floating nodes that have no edge connecting them to another node
    """
    for node_name, node_obj in graph.node_obj.items():
        validate(
            node_obj.node_name == node_name,
            f"Node {node_name} name has been updated after being added to the network graph.",
        )

    graph.verify_graph()


def build_model_and_objective(
    graph: OptimisationGraph,
    scenario_settings: ScenarioSettings,
    small_m: float,
    big_m: int,
    profile: pd.DataFrame | None,
    objective_set: ObjectiveSet | None,
) -> tuple[EchoConcreteModel, en.numeric_expr.NumericExpression | None, AttributeTracker]:
    """Builds an EchoConcreteModel for a particular Echo Scenario definition and a related objective to optimise
    against the model"""
    model = EchoConcreteModel()
    tracker = AttributeTracker(model)

    _build_model(
        model=model,
        graph=graph,
        scenario_settings=scenario_settings,
        small_m=small_m,
        big_m=big_m,
        profile=profile,
        tracker=tracker,
    )
    objective = _build_objective(
        model=model, graph=graph, objective_set=objective_set, profile=profile, tracker=tracker
    )

    return model, objective, tracker


def _build_model(
    graph: OptimisationGraph,
    scenario_settings: ScenarioSettings,
    small_m: float,
    big_m: int,
    profile: pd.DataFrame | None,
    tracker: AttributeTracker,
    model: EchoConcreteModel | None = None,
) -> EchoConcreteModel:
    if model is None:
        model = EchoConcreteModel()
    model.small_m = en.Param(initialize=small_m)
    model.big_m = en.Param(initialize=big_m)

    tracker.mark("model-init")

    model.scenario_settings = scenario_settings

    # We use RangeSet to create an index for each of the time
    # periods that we will optimise within.
    model.Time = en.RangeSet(0, scenario_settings.number_of_intervals - 1)

    # Create index for expansion periods
    if scenario_settings.number_of_expansion_intervals == 0:
        model.Expansion = en.RangeSet(0, 0)
    else:
        model.Expansion = en.RangeSet(0, scenario_settings.number_of_expansion_intervals - 1)

    # Setup discounting
    discount_rates = {}
    for ep in range(0, scenario_settings.number_of_expansion_intervals):
        discount_rates[ep] = 1 / ((1 + scenario_settings.discount_rate) ** ep)
    model.discount_rates = en.Param(model.Expansion, initialize=discount_rates)

    tracker.mark("model-setup")

    # Initialise node variables/params and add node constraints
    for node_obj in graph.node_obj.values():
        node_obj.verify_node()
        node_obj.add_node_to_model(model, profile)
        node_obj.apply_node_constraints(model)
        tracker.mark(f"{node_obj.node_name}:node-constraints")

    # Initialise edge variables/params and add edge constraints
    for edge_obj in graph.edge_obj.values():
        edge_obj.verify_edge()
        edge_obj.add_edge_to_model(model)
        tracker.mark(edge_obj.edge_name)

    # Initialise paths
    for path in graph.paths.values():
        path.add_path_to_model(model)
        tracker.mark(path.path_name)

    if graph.paths:
        graph.apply_path_constraints(model)
        tracker.mark("model-adding-path-constraints")

    return model


def _build_objective(
    model: EchoConcreteModel,
    graph: OptimisationGraph,
    profile: pd.DataFrame | None,
    objective_set: ObjectiveSet | None,
    tracker: AttributeTracker,
    objective: en.numeric_expr.NumericExpression | int = 0,
) -> en.numeric_expr.NumericExpression | None:

    # Add objectives defined in the objective set
    if objective_set is not None:
        objective_set.add_objectives_to_model(model, profile)
        objective += objective_set.get_objective_total(model)
        tracker.mark("model-adding-objective-set")

    # Add any other costs that are defined on graph nodes/ports/paths
    for node_obj in graph.node_obj.values():
        node_obj.add_objective(model)
        objective += node_obj.objective
        for port_obj in node_obj.ports.values():
            port_obj.add_objective(model)  # populate the .objective attribute for each port
            objective += port_obj.objective  # add the newly populated attribute to our total
        tracker.mark(f"{node_obj.node_name}:objectives")

    for path_obj in graph.paths.values():
        path_obj.add_objective(model)
        objective += path_obj.objective

        tracker.mark(path_obj.path_name if path_obj.path_name is not None else "model-adding-path-objectives")

    # Determine if we failed to build an objective
    if isinstance(objective, int):
        return None
    return objective


def optimise(
    scenario_settings: ScenarioSettings,
    engine_settings: EngineSettings,
    graph: OptimisationGraph,
    objective_set: ObjectiveSet | None = None,
    profile: pd.DataFrame | None = None,
    verbose: bool = False,
    show_solver_output: bool = False,
    logfile: str | None = None,
    time_limit: int | None = None,
    acceptable_conditions: Collection[TerminationCondition] = DEFAULT_ACCEPTABLE_TERMINATION_CONDITIONS,
) -> OptimisationResult:
    """Runs the optimiser with the specified settings. Returns an OptimisationResult that can be queried
    using the supplied graph.

    Will attempt to validate the graph and will raise exceptions if it appears invalid / unsolvable

    verbose: If set to True the solver will operate in verbose mode and print additional output to stdout
    logfile: If set to a file path - the stdout will be redirected to this file (for the duration of this run)
    acceptable_conditions: OptimiserResultError will be raised if the pyomo termination condition is not in this set
    time_limit: optional time_limit in seconds after which the solver should return a solution if
     other termination conditions have not already been reached."""

    validate_network_graph(graph)

    model, objective, tracker = build_model_and_objective(
        graph=graph,
        scenario_settings=scenario_settings,
        small_m=engine_settings.small_m,
        big_m=engine_settings.big_m,
        profile=profile,
        objective_set=objective_set,
    )

    if objective is not None:

        def cost_function(model: EchoConcreteModel) -> en.numeric_expr.NumericExpression:
            return objective

        model.total_cost = en.Objective(rule=cost_function, sense=en.minimize)

    # Set the path to the solver
    if engine_settings.engine_executable:
        opt = SolverFactory(engine_settings.engine, executable=engine_settings.engine_executable)
    else:
        opt = SolverFactory(engine_settings.engine)

    if time_limit is not None:
        solver_name = engine_settings.engine
        if "cplex" in solver_name:
            opt.options["timelimit"] = time_limit
        elif "glpk" in solver_name:
            opt.options["tmlim"] = time_limit
        elif "gurobi" in solver_name:
            opt.options["TimeLimit"] = time_limit
        elif "xpress" in solver_name:
            # Use the below instead for XPRESS versions before 9.0
            # self.solver.options['maxtime'] = TIME_LIMIT
            opt.options["soltimelimit"] = time_limit

    # Run the optimisation, logging everything to the specified file
    with logged_stdout(logfile):
        if verbose:
            model.pprint(verbose=True)
        results: SolverResults = opt.solve(model, tee=show_solver_output, symbolic_solver_labels=True)

    # Extract the optimisation result
    termination_condition: TerminationCondition = results.solver.termination_condition
    solver_status: SolverStatus = results.solver.status

    if solver_status != SolverStatus.ok:
        if solver_status == SolverStatus.aborted:
            warnings.warn(f"Solver status returned as {solver_status}", stacklevel=1)
        else:
            raise OptimiserResultError(f"Solver status returned as {solver_status}")

    if termination_condition not in acceptable_conditions:
        raise OptimiserResultError(
            f"Termination condition '{termination_condition}' is not in acceptable set  of {acceptable_conditions}"
        )

    return OptimisationResult(
        scenario_settings=scenario_settings,
        objective=objective,
        model=model,
        objective_set=objective_set,
        graph=graph,
        opt_status=solver_status,
        termination_condition=termination_condition,
        model_attribute_tracker=tracker,
    )
