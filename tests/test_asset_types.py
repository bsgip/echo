import numpy as np

from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph, TransformNode
from echo.models.carbon import CarbonAggregation, CarbonSink, CarbonSource
from echo.models.electrical import ElectricalDemand, ElectricalPort, ElectricalStorage
from echo.models.gas import FlexGasPort, GasBoilerFixedCOP
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.models.thermal import FixedThermalPort, HeatSink, SimpleChiller
from echo.objectives.base import ObjectiveSet
from echo.objectives.tariff import ImportTariff
from echo.optimiser import optimise

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
    hl = HeatSink()
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
    hl = HeatSink()
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
    expansion_periods = 1
    time_periods = 48
    interval_duration = 30

    system = OptimisationGraph()

    grid = Node()
    grid.ports["grid"] = ElectricalPort()

    input_breakpoints = [0, 2, 3, 8]
    output_values = [0, -3, -4, -8]
    chiller = SimpleChiller()
    chiller.add_input_pts(input_breakpoints, time_periods=time_periods)
    chiller.add_output_pts(output_values, time_periods=time_periods)

    cooling_load = Node()
    cl = FixedThermalPort()
    cl.set_initial_value_from_array([4] * time_periods, expansion_periods=expansion_periods)
    cooling_load.ports["load"] = cl

    system.add_node_obj([grid, chiller, cooling_load])
    system.connect_ports_and_create_edge(grid.ports["grid"], chiller.ports["input"])
    system.connect_ports_and_create_edge(chiller.ports["output"], cl)

    optimise_results = optimise(
        scenario_settings=ScenarioSettings(
            interval_duration=interval_duration,
            number_of_intervals=time_periods,
            number_of_expansion_intervals=expansion_periods,
        ),
        engine_settings=engine_settings_from_environment(),
        graph=system,
    )

    print("mains gas: ", optimise_results.values(grid.ports["grid"].port_name, 0))
    print("chiller input (elec): ", optimise_results.values(chiller.ports["input"].port_name, 0))
    print("chiller output (cooling): ", optimise_results.values(chiller.ports["output"].port_name, 0))
    print("cooling load: ", cl.initial_value.values())
    print(
        "cop: ",
        np.divide(
            optimise_results.values(chiller.ports["output"].port_name, 0),
            optimise_results.values(chiller.ports["input"].port_name, 0),
        ),
    )

    chiller_input = optimise_results.values(chiller.ports["input"].port_name, 0)
    # chiller_output = optimise_results.values(chiller.ports['output'].port_name, 0)
    # grid_import = optimise_results.values(grid.ports['grid'].port_name, 0)
    # cl_p = cl.initial_value
    # cop = np.divide(optimise_results.values(chiller.ports['output'].port_name, 0), optimise_results.values(chiller.ports['input'].port_name, 0))

    for i in range(time_periods):
        assert chiller_input[i] == 3


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
