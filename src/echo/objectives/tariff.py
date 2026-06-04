from datetime import time
from enum import Enum
from typing import List, Optional, Union

import numpy as np
import pandas as pd
import pyomo.environ as en
import shortuuid
from pydantic import (
    Field,
    NonNegativeFloat,
    NonPositiveFloat,
    PositiveFloat,
    PositiveInt,
    root_validator,
    validator,
)

from echo.exceptions import validate
from echo.models.base import BaseModel as EchoBaseModel
from echo.models.base import Path, Port
from echo.models.scenario import EchoConcreteModel
from echo.objectives.base import Objective
from echo.validators import ArrayType


class Tariff(Objective):
    tariff_array: Union[ArrayType, list]  # tariff array prices should always be positive
    expansion_periods: Optional[PositiveInt] = 1

    @staticmethod
    def return_tariff_dict(array, expansion_periods):
        # todo update this to work for multiple expansion periods
        keys = [(x, i) for x in range(expansion_periods) for i in range(len(array))]
        vals = dict(zip(keys, array))
        return vals


class ImportTariff(Tariff):
    """The ImportTariff objective applies a price per kWh of energy imported at a defined port."""

    component: Port
    import_tariff_dict: Optional[dict]

    @property
    def import_tariff(self):
        return "import_tariff_" + self.name

    def __init__(self, **data):
        super().__init__(**data)
        self.import_tariff_dict = self.return_tariff_dict(self.tariff_array, self.expansion_periods)

    def create_params(self, model: EchoConcreteModel, df):
        setattr(
            model,
            self.import_tariff,
            en.Param(model.Expansion, model.Time, initialize=self.import_tariff_dict),
        )

    def apply_constraints(self, model: EchoConcreteModel):
        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

    def objective_expr(self, model: EchoConcreteModel):
        return sum(
            getattr(model, self.component.pos)[p, t]
            * getattr(model, self.import_tariff)[p, t]
            * model.scenario_settings.interval_duration
            / 60
            * model.discount_rates[p]
            for p in model.Expansion
            for t in model.Time
        )


class ExportTariff(Tariff):
    """The ExportTariff objective applies a tariff, defined as an array of prices,
    to the negative (exporting) component of the specified port."""

    component: Port
    export_tariff_dict: Optional[dict]

    @property
    def export_tariff(self):
        return "export_tariff_" + self.name

    def __init__(self, **data) -> None:
        super().__init__(**data)
        self.export_tariff_dict = self.return_tariff_dict(self.tariff_array, self.expansion_periods)

    def create_params(self, model: EchoConcreteModel, df):
        setattr(
            model,
            self.export_tariff,
            en.Param(model.Expansion, model.Time, initialize=self.export_tariff_dict),
        )

    def apply_constraints(self, model: EchoConcreteModel):
        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

    def objective_expr(self, model: EchoConcreteModel):
        return sum(
            getattr(model, self.component.neg)[p, t]
            * getattr(model, self.export_tariff)[p, t]
            * model.scenario_settings.interval_duration
            / 60
            * model.discount_rates[p]
            for p in model.Expansion
            for t in model.Time
        )


class BlockTariff(Objective):
    """A block tariff, or step tariff, divides consumption over a time period into different blocks, and each block
    has a different price."""

    component: Port
    blocks: list  # list of consumption blocks/steps (cumulative) as tuple ranges
    rates: list  # list of rates per tuple
    reset_periods: list = []
    reset_index: en.RangeSet

    @property
    def num_price_bands(self):
        return len(self.rates)

    @root_validator
    def check_block_rates(cls, values):
        validate(
            len(values.get("blocks")) + 1 == len(values.get("rates")),
            "Enter one more rate than num blocks",
        )
        return values

    @root_validator(pre=True)
    def set_reset_index(cls, values):
        rp = values.get("reset_periods")
        if rp is not None:
            values["reset_index"] = en.RangeSet(0, len(rp) - 1)
        else:
            values["reset_index"] = en.RangeSet(0, 0)
        return values

    def get_block_var_name(self, i):
        return "block_" + str(i)

    def _get_active_periods(
        self, time_periods: int
    ) -> dict[tuple[int, int, int], np.ndarray]:  # todo only works for single expansion period
        """
        Creates a dict for initialising the window_active pyomo var
        Args:
            window_bool: array of when charge applies, over entire optimisation period
            reset_periods: list of how many intervals per period in which a tariff is calculated.
        Returns:
            initial_window_val: triple indexed dict (expansion, reset index, time) for initialising demand charge var
        """
        initial_window_val: dict[tuple[int, int, int], np.ndarray] = {}
        if self.reset_periods is None:
            self.reset_periods = [time_periods]
        else:
            validate(
                sum(self.reset_periods) == time_periods,
                "Total reset intervals doesn't match time periods.",
            )
        window_bool = np.ones(time_periods)
        num_resets = len(self.reset_periods)
        blank = np.zeros([num_resets, time_periods])  # Create template blank array that we will populate with 1s
        index = 0  # for indexing each reset period
        for i in range(num_resets):
            blank[i, index : index + self.reset_periods[i]] = 1.0  # put the right number of 1s in # noqa E203
            index += self.reset_periods[i]
            new_window = np.array(window_bool) * blank[i]  # use the blank array as a filter on the window bool array
            for t in range(time_periods):
                initial_window_val[(0, i, t)] = new_window[t]  # get the array into a dict with the right keys
        return initial_window_val


class BlockImportTariff(BlockTariff):
    @property
    def window_active(self):
        return "window_active_" + self.name

    def create_vars(self, model: EchoConcreteModel):
        self.component.constrain_pos_neg(model)
        for i in range(self.num_price_bands):
            # Create a variable for each price band, and bound it
            var_name = self.get_block_var_name(i)
            setattr(model, var_name, en.Var(self.reset_index, domain=en.NonNegativeReals))
            if i == 0:
                getattr(model, var_name).setub(self.blocks[i])
            elif i != self.num_price_bands - 1:
                getattr(model, var_name).setub(self.blocks[i] - self.blocks[i - 1])

        initial_val = self._get_active_periods(time_periods=len(model.Time))
        setattr(
            model,
            self.window_active,
            en.Param(model.Expansion, self.reset_index, model.Time, initialize=initial_val),
        )

    def apply_constraints(self, model: EchoConcreteModel):
        def total_rule(model: EchoConcreteModel, r):
            all_blocks = 0
            for i in range(self.num_price_bands):
                var = self.get_block_var_name(i)
                all_blocks += getattr(model, var)[r]
            total_energy = sum(
                getattr(model, self.component.pos)[p, t] * getattr(model, self.window_active)[p, r, t]
                for p in model.Expansion
                for t in model.Time
            )

            return all_blocks >= total_energy

        con_name = "total_energy_con_" + self.name
        setattr(model, con_name, en.Constraint(self.reset_index, rule=total_rule))

    def objective_expr(self, model: EchoConcreteModel):
        total = 0
        for i in range(self.num_price_bands):
            total += self.rates[i] * sum(getattr(model, self.get_block_var_name(i))[r] for r in self.reset_index)
        return total


class PathTariff(Tariff):
    """The PathTariff objective applies a cost per kW of power flow on a specified path."""

    component: Path
    path_tariff_dict: Optional[dict]

    @property
    def path_tariff(self):
        return "path_tariff_" + self.name

    def __init__(self, **data) -> None:
        super().__init__(**data)
        self.path_tariff_dict = self.return_tariff_dict(self.tariff_array, self.expansion_periods)

    def create_params(self, model: EchoConcreteModel, df):
        setattr(
            model,
            self.path_tariff,
            en.Param(model.Expansion, model.Time, initialize=self.path_tariff_dict),
        )

    def apply_constraints(self, model: EchoConcreteModel):
        pass

    def objective_expr(self, model: EchoConcreteModel):
        return sum(
            getattr(model, self.component.flow_value)[p, t]
            * getattr(model, self.path_tariff)[p, t]
            * model.discount_rates[p]
            for p in model.Expansion
            for t in model.Time
        )


class ThroughputCost(Objective):
    """A ThroughputCost objective applies a fixed rate to total throughput (i.e. import minus export) at a port."""

    component: Port
    rate: PositiveFloat

    def apply_constraints(self, model: EchoConcreteModel):
        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

    def objective_expr(self, model: EchoConcreteModel):
        obj = (
            sum(
                (getattr(model, self.component.pos)[p, t] - getattr(model, self.component.neg)[p, t])
                * model.discount_rates[p]
                for p in model.Expansion
                for t in model.Time
            )
            * self.rate
        )
        return obj


class ResetPeriod(Enum):
    day = "day"
    week = "week"
    month = "month"
    quarter = "quarter"
    year = "year"


class Day(Enum):
    weekday = "weekday"
    weekend = "weekend"
    holiday = "holiday"


class TimePeriod(EchoBaseModel):
    start_time: time
    end_time: time
    day_type: list[Day]

    def to_bool(self, df: pd.DataFrame) -> np.ndarray:
        """
        Convert time period to an array based on whether a row is in the time period
        Args:
            df: input DataFrame

        Returns:

        """
        allowed_days_of_week_start = 7
        allowed_days_of_week_end = 0
        if Day.weekday in self.day_type:
            # Weekdays are 0...4
            allowed_days_of_week_start = 0
            allowed_days_of_week_end = 4
        else:
            allowed_days_of_week_start = 5
        if Day.weekend in self.day_type:
            # Weekends are 5, 6
            allowed_days_of_week_end = 6
        if Day.holiday in self.day_type:
            raise NotImplementedError("Public holidays not currently supported in optimisation")
        return (
            (df.index.isin(df.between_time(self.start_time, self.end_time, inclusive="left").index))
            & (df.index.weekday <= allowed_days_of_week_end)
            & (df.index.weekday >= allowed_days_of_week_start)
        ).astype(int)

    def overlaps(self, other: "TimePeriod"):
        """Determines whether two :obj:`TimePeriod` objects are overlapping.

        Intended use if for validating :obj:`Window` objects.

        Args:
            other: The other TimePeriod to compare to

        Returns:
            bool: True if both :obj:`TimePeriod` objects overlap, False otherwise.

        """
        if set(self.day_type).intersection(set(other.day_type)):
            end_time = self.end_time
            if end_time == time(0, 0):
                end_time = time(23, 59, 59)
            if self.start_time > self.end_time:
                self_ranges = [
                    (time(0, 0), end_time),
                    (self.start_time, time(23, 59, 59)),
                ]
            else:
                self_ranges = [(self.start_time, end_time)]
            end_time = other.end_time
            if end_time == time(0, 0):
                end_time = time(23, 59, 59)
            if other.start_time > other.end_time:
                other_ranges = [
                    (time(0, 0), end_time),
                    (other.start_time, time(23, 59, 59)),
                ]
            else:
                other_ranges = [(other.start_time, end_time)]
        for self_range in self_ranges:
            for other_range in other_ranges:
                if self_range[0] < other_range[1] and other_range[0] < self_range[1]:
                    return True
        return False


class Window(EchoBaseModel):
    """Class for specifying window over which a tariff is calculated using datetimes"""

    time_periods: list[TimePeriod]
    reset_periods: Optional[ResetPeriod] = None

    @validator("time_periods")
    def non_overlapping_periods(cls, v):
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                if v[i].overlaps(v[j]):
                    raise ValueError(f"TimePeriod {v[i]} overlaps with TimePeriod {v[j]}")
        return v

    def to_bool_periods(self, df: pd.DataFrame) -> np.ndarray:
        """To convert a window to a bool array"""
        if isinstance(df, dict):
            df = pd.DataFrame(df)
            df.index = pd.to_datetime(df.index)
        time_period_stack = np.column_stack([period.to_bool(df) for period in self.time_periods])
        return time_period_stack.any(axis=1).astype(int)

    def get_reset_period_array(self, df: pd.DataFrame) -> list:
        """Returns an array where each value is the number of time intervals within which the demand charge is
        calculated."""
        interval_duration = (df.index[1] - df.index[0]).seconds // 60  # get the interval duration in minutes
        total_intervals = len(df)

        def _find_rollover(df, interval_duration):
            """Finds when there is a rollover for a specified time period (year, month), and calculates the number
            of intervals in each rollover period"""

            def perform_rollover_calc(diff_array):
                _reset_periods = []
                # initialise a total to count how many intervals per reset period.
                # =1 because the diff array has length n-1
                total = 1

                for i in diff_array:
                    if i != 0:  # this indicates we have rolled over - add our total # intervals
                        _reset_periods.append(total)
                        # reset the total
                        total = 1
                    else:
                        total += 1
                remaining_intervals = len(df) - sum(
                    _reset_periods
                )  # need to calculate the remaining intervals and add these to the end
                _reset_periods.append(remaining_intervals)
                return _reset_periods

            reset_periods = []
            if self.reset_periods is None:
                reset_periods = [total_intervals]
            elif self.reset_periods == ResetPeriod.day:
                validate(
                    interval_duration <= 60 * 24,
                    "Reset period cannot be a day if interval duration is greater than a day.",
                )
                reset_periods = perform_rollover_calc(np.diff(df.index.day))
            elif self.reset_periods == ResetPeriod.week:
                validate(
                    interval_duration <= 60 * 24 * 7,
                    "Reset period cannot be a week if interval duration is greater than a week.",
                )
                reset_periods = perform_rollover_calc(np.diff(df.index.week))
            elif self.reset_periods == ResetPeriod.month:
                validate(
                    interval_duration <= 60 * 8760 // 12,
                    "Reset period cannot be a month if interval duration is greater than a month.",
                )
                reset_periods = perform_rollover_calc(np.diff(df.index.month))
            elif self.reset_periods == ResetPeriod.year:
                validate(
                    interval_duration <= 60 * 8760,
                    "Reset period cannot be a year if interval duration is greater than a year.",
                )
                reset_periods = perform_rollover_calc(np.diff(df.index.year))
            return reset_periods

        return _find_rollover(df, interval_duration)


class DemandCharge(EchoBaseModel):
    """A demand charge is a rate that applies to the maximum demand over one or many specified time windows."""

    uid: str = Field(default_factory=shortuuid.uuid)
    name: str
    rate: NonNegativeFloat
    min_demand: float = 0.0
    window_array: Union[ArrayType, List]
    reset_periods: Union[ArrayType, List]
    import_demand: bool = False
    export_demand: bool = False

    num_reset_periods: int = 0
    reset_index: en.RangeSet  # index for separating different reset periods

    @property
    def max_demand_val(self):
        return "max_demand_" + self.name

    @property
    def window_active(self):
        return "window_active_" + self.name

    @root_validator(pre=True)
    def check_reset_periods(cls, values):
        rp = values.get("reset_periods")
        window_array = values.get("window_array")
        if rp is not None:
            validate(
                sum(rp) == len(window_array),
                "Sum of reset period lengths ({}) is not equal to window array length ({}).".format(
                    sum(rp), len(window_array)
                ),
            )
            values["num_reset_periods"] = len(rp)
        else:
            values["reset_periods"] = [len(window_array)]
            values["num_reset_periods"] = 1
        values["reset_index"] = en.RangeSet(0, values.get("num_reset_periods") - 1)
        return values

    @root_validator
    def check_import_or_export(cls, values):
        validate(
            values.get("import_demand") is True or values.get("export_demand") is True,
            str(
                "Please use ImportDemandCharge or ExportDemandCharge classes, or alternatively,"
                " set DemandCharge.import_demand or DemandCharge.export_demand as True before adding "
                "the demand charge to the demand tariff objective."
            ),
        )
        return values

    @root_validator(pre=True)
    def check_name(cls, values):
        if not values.get("uid"):
            values["uid"] = shortuuid.uuid()

        if not values.get("name"):
            values["name"] = "dc_" + str(values["uid"])
        return values

    @staticmethod
    def _get_active_periods(window_bool, reset_periods):  # todo only works for single expansion period
        """
        Creates a dict for initialising the window_active pyomo var
        Args:
            window_bool: array of when charge applies, over entire optimisation period
            reset_periods: list of how many intervals per period in which a tariff is calculated.
        Returns:
            initial_window_val: triple indexed dict (expansion, reset index, time) for initialising demand charge var
        """
        initial_window_val = {}
        n_intervals = len(window_bool)
        num_resets = len(reset_periods)
        blank = np.zeros([num_resets, n_intervals])  # Create template blank array that we will populate with 1s
        index = 0  # for indexing each reset period
        for i in range(num_resets):
            blank[i, index : index + reset_periods[i] - 1] = 1.0  # put the right number of 1s in # noqa E203
            index += reset_periods[i] - 1
            new_window = np.array(window_bool) * blank[i]  # use the blank array as a filter on the window bool array
            for t in range(n_intervals):
                initial_window_val[(0, i, t)] = new_window[t]  # get the array into a dict with the right keys
        return initial_window_val

    def create_params(self, model: EchoConcreteModel, df):
        initial_val = self._get_active_periods(self.window_array, self.reset_periods)
        # Initialise binary parameter for when the demand charge applies, indexed by Expansion, reset period, Time
        setattr(
            model,
            self.window_active,
            en.Param(
                model.Expansion,
                self.reset_index,
                model.Time,
                initialize=initial_val,
                domain=en.Binary,
            ),
        )

    def create_vars(self, model: EchoConcreteModel):
        if self.import_demand is True:
            setattr(
                model,
                self.max_demand_val,
                en.Var(self.reset_index, initialize=0, domain=en.NonNegativeReals),
            )
        elif self.export_demand is True:
            setattr(
                model,
                self.max_demand_val,
                en.Var(self.reset_index, initialize=0, domain=en.NonPositiveReals),
            )

    def objective_expr(self, model: EchoConcreteModel):
        objective = 0
        if self.import_demand:
            objective += sum(getattr(model, self.max_demand_val)[r] * self.rate for r in self.reset_index)
        elif self.export_demand:
            objective += sum(getattr(model, self.max_demand_val)[r] * self.rate * -1 for r in self.reset_index)
        return objective

    def get_objective_total(self, model: EchoConcreteModel):
        expr = en.value(self.objective_expr(model))
        return expr


class DemandTariffObjective(Objective):
    """A demand tariff objective contains a set of one or more demand charges."""

    component: Port
    demand_charges: List[DemandCharge]
    expansion_periods: Optional[PositiveInt] = 1

    def verify_objective(self, model: EchoConcreteModel, df):
        def verify_non_overlapping():
            """Check that windows are not overlapping if multiple demand charges defined"""
            prev_window = np.array([])
            prev_dc = None
            for dc in self.demand_charges:
                if prev_window.size > 0:
                    comparison = np.array(prev_window) * np.array(dc.window_array)
                    if sum(comparison) > 0:
                        raise ValueError(f"Overlapping time periods between {prev_dc} and {dc}")
                    prev_window = np.array(prev_window) + np.array(dc.window_array)
                else:
                    prev_dc = dc
                    prev_window = np.array(dc.window_array)

        def verify_same_length_windows():
            """Check that all windows have the same length, and that this length matches the number of model
            time intervals"""

            prev_length = None
            for dc in self.demand_charges:
                if prev_length is not None:
                    validate(
                        len(dc.window_array) == prev_length,
                        "Demand charge windows are not all the same length",
                    )
                    prev_length = len(dc.window_array)
                else:
                    prev_length = len(dc.window_array)
                validate(
                    prev_length == model.scenario_settings.number_of_intervals,
                    f"Demand charge {dc} windows do not match optimiser time periods.",
                )

        verify_non_overlapping()
        verify_same_length_windows()

    def create_params(self, model: EchoConcreteModel, df):
        for dc in self.demand_charges:
            dc.create_params(model, df)

    def create_vars(self, model: EchoConcreteModel):
        for dc in self.demand_charges:
            dc.create_vars(model)

    def apply_constraints(self, model: EchoConcreteModel):
        if hasattr(model, self.component.pos) is False:
            self.component.constrain_pos_neg(model)

        for dc in self.demand_charges:
            if dc.import_demand is True:

                def max_import_demand_rule(model: EchoConcreteModel, p, t, r):
                    return (
                        getattr(model, dc.max_demand_val)[r]
                        >= (getattr(model, self.component.pos)[p, t] - dc.min_demand)
                        * getattr(model, dc.window_active)[p, r, t]
                    )

                setattr(
                    model,
                    f"cons_{dc.max_demand_val}_max_demand",
                    en.Constraint(
                        model.Expansion,
                        model.Time,
                        dc.reset_index,
                        rule=max_import_demand_rule,
                    ),
                )
            elif dc.export_demand is True:

                def max_export_demand_rule(model: EchoConcreteModel, p, t, r):
                    return (
                        getattr(model, dc.max_demand_val)[r]
                        <= (getattr(model, self.component.neg)[p, t] - dc.min_demand)
                        * getattr(model, dc.window_active)[p, r, t]
                    )

                setattr(
                    model,
                    f"cons_{dc.max_demand_val}_max_export_demand",
                    en.Constraint(
                        model.Expansion,
                        model.Time,
                        dc.reset_index,
                        rule=max_export_demand_rule,
                    ),
                )

    def objective_expr(self, model: EchoConcreteModel):
        objective = 0
        for dc in self.demand_charges:
            objective += dc.objective_expr(model)
        return objective


class ImportDemandCharge(DemandCharge):
    import_demand = True
    export_demand = False
    min_demand: NonNegativeFloat = 0.0


class ExportDemandCharge(DemandCharge):
    import_demand = False
    export_demand = True
    min_demand: NonPositiveFloat = 0.0
