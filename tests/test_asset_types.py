import numpy as np

from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode, Sink, FixedPort, Source
from echo.models.base import Node, OptimisationGraph, TransformNode
from echo.models.carbon import CarbonAggregation, CarbonSink, CarbonSource
from echo.models.electrical import ElectricalDemand, ElectricalPort, ElectricalStorage
from echo.models.gas import FlexGasPort, GasBoilerFixedCOP
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.models.thermal import SimpleChiller
from echo.objectives.base import ObjectiveSet
from echo.objectives.tariff import ImportTariff
from echo.optimiser import optimise
from echo.utils import TimeSeriesData, expand_as_dict

N_INTERVALS = 48


def test_gas_boiler_fixed_cop():
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    gas_mains = Node()
    gas_mains.ports["mains"] = FlexGasPort()

    boiler = GasBoilerFixedCOP(max_input=10, min_input=2, max_output=-10, min_output=-2, cop=0.5, startup_cop=0.5)

    heating_load = Node()
    hl = Sink(units=Units.KWT)
    hl.add_sink_profile_from_array([5] * time_periods, expansion_periods)
    heating_load.ports["load"] = hl

    system.add_node_obj([gas_mains, boiler, heating_load])
    system.connect_ports_and_create_edge(gas_mains.ports["mains"], boiler.ports["input"])
    system.connect_ports_and_create_edge(boiler.ports["output"], hl)

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
    )

    print("mains gas: ", optimise_results.values(gas_mains.ports["mains"].port_name, 0))
    print("boiler input (gas): ", optimise_results.values(boiler.ports["input"].port_name, 0))
    print("boiler output (heat): ", optimise_results.values(boiler.ports["output"].port_name, 0))
    print("heating load: ", hl.initial_value.values())

    gas_mains = optimise_results.values(gas_mains.ports["mains"].port_name, 0)
    hl_p = hl.initial_value

    for i in range(time_periods):
        assert gas_mains[i] * boiler.cop == hl_p[(0, i)] * -1


def test_modulating_gas_boiler():
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    gas_mains = Node()
    gas_mains.ports["mains"] = FlexGasPort()

    boiler = GasBoilerFixedCOP(max_input=100, min_input=0, cop=0.8, startup_cop=0.8)

    heating_load = Node()
    hl = Sink(units=Units.KWT)
    hl.add_sink_profile_from_array([5] * time_periods, expansion_periods)
    heating_load.ports["load"] = hl

    system.add_node_obj([gas_mains, boiler, heating_load])
    system.connect_ports_and_create_edge(gas_mains.ports["mains"], boiler.ports["input"])
    system.connect_ports_and_create_edge(boiler.ports["output"], hl)

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
    )

    boiler_input = optimise_results.values(boiler.ports["input"].port_name, 0)
    boiler_output = optimise_results.values(boiler.ports["output"].port_name, 0)

    for i in range(time_periods):
        assert boiler_input[i] * boiler.cop == -1 * boiler_output[i]


def test_chiller_operation():
    """Test SimpleChiller operation with piecewise linear COP dependent on partial load value"""

    system = OptimisationGraph()
    grid = Node(node_name="grid", ports={"supply_kw": FlexPort(units=Units.KW)})
    chiller = SimpleChiller(max_cooling_capacity=10, nominal_cop=2.5)
    # Cooling demand is a heat source
    cooling_load_data = TimeSeriesData(
        value=[-5, -1, -6, -2.5, -7.5, -10], num_time_intervals=6, num_expansion_intervals=1
    )
    cooling_demand_dict = expand_as_dict(cooling_load_data)
    cooling_load = Node(node_name="cooling_load", ports={"cooling_demand_kwt": Source(units=Units.KWT)})
    cooling_load.ports["cooling_demand_kwt"].add_source_profile(cooling_demand_dict)

    system.add_node_obj([grid, chiller, cooling_load])
    system.connect_ports_and_create_edge(grid.ports["supply_kw"], chiller.ports["input"])
    system.connect_ports_and_create_edge(chiller.ports["output"], cooling_load.ports["cooling_demand_kwt"])

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=30,
            number_of_intervals=6,
            number_of_expansion_intervals=1,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
    )

    chiller_actual_cop = np.divide(
        optimise_results.values(chiller.ports["output"].port_name, 0),
        optimise_results.values(chiller.ports["input"].port_name, 0),
    )

    # Check that we observe variation in COP
    assert min(chiller_actual_cop) != max(chiller_actual_cop)

    # Check that observed COP values are within expected range
    min_cop = min([v for v in chiller.partial_load_cop.values() if v != 0]) * chiller.nominal_cop
    for cop_v in chiller_actual_cop:
        assert cop_v >= min_cop
        assert cop_v <= chiller.nominal_cop


def test_carbon_aggregation():
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = TransformNode()
    grid.ports["grid"] = ElectricalPort()
    grid.ports["CO2"] = CarbonSource()
    grid.add_emission_transformation(grid.ports["grid"], grid.ports["CO2"], 0.5)

    battery1 = TransformNode()
    b1 = ElectricalStorage(
        max_capacity=15,
        depth_of_discharge_limit=0,
        charging_power_limit=2.0,
        discharging_power_limit=-2.0,
        charging_efficiency=1,
        discharging_efficiency=1,
        initial_state_of_charge=0.0,
    )
    battery1.ports["battery"] = b1
    battery1.ports["CO2"] = CarbonSource()
    battery1.add_emission_transformation(b1, battery1.ports["CO2"], 0.2)

    load1 = Node()
    l1 = ElectricalDemand()
    l1.add_demand_profile_from_array(np.array([6] * time_periods), expansion_periods)
    load1.ports["demand"] = l1

    site1 = TellegenNode()
    site1.add_ports_from_list(["cp", "load", "bess"], FlexPort, units=Units.KW)

    carbon_aggr = CarbonAggregation()
    carbon_aggr.ports["grid"] = CarbonSink()
    carbon_aggr.ports["bess"] = CarbonSink()

    system.add_node_obj([grid, battery1, load1, site1, carbon_aggr])
    system.connect_ports_and_create_edge(grid.ports["grid"], site1.ports["cp"])
    system.connect_ports_and_create_edge(grid.ports["CO2"], carbon_aggr.ports["grid"])
    system.connect_ports_and_create_edge(site1.ports["bess"], b1)
    system.connect_ports_and_create_edge(battery1.ports["CO2"], carbon_aggr.ports["bess"])
    system.connect_ports_and_create_edge(site1.ports["load"], l1)

    import_tariff = ImportTariff(
        component=site1.ports["cp"],
        tariff_array=np.array(([0.1] * 24 + [0.3] * 24)),
        expansion_periods=expansion_periods,
    )

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
        objective_set=ObjectiveSet(objective_list=[import_tariff]),
    )

    grid_emissions = optimise_results.values(grid.ports["CO2"].port_name, 0)
    bess_emissions = optimise_results.values(battery1.ports["CO2"].port_name, 0)
    aggr = optimise_results.values(carbon_aggr.total, 0)

    for i in range(time_periods):
        assert aggr[i] * -1 == grid_emissions[i] + bess_emissions[i]
