import json
import sys
import pandas as pd
import numpy as np
import sgt
import sgt_e_json
import matplotlib.pyplot as plt
## echo and optimisation imports
import echo_models as ecm
from echo_optimiser import EchoOptimiser
import objectives as obj
from pyomo.util.infeasible import log_infeasible_constraints
import seaborn as sns
import cmath


def retrieve_value(dict, key):
    out = None
    if key in dict.keys():
        out = dict[key]
        if hasattr(out, '__len__'):
            if len(out)==0:
                out = None
    return out


# ev3 = {'name':'ev3','available': available2, 'usage': usage2, 'max_capacity': 40., 'depth_of_discharge_limit':0,
#            'charging_power_limit':10., 'discharging_power_limit':0, 'charging_efficiency':1,
#            'discharging_efficiency':1, 'initial_state_of_charge':0.0, 'charge_model': 'V0G'}

def preprocess_evs(evs, interval_duration):
    """
    Does an initial pass of all evs and checks their charging mode. If V1G or V2G then makes sure that their constraints
    are consistent. If V0G then performs this charging a
    :param evs: list of ev dicts
    :param interval duration: time span for each interval
    :return:
    """
    ev_name_check(evs)
    return True

def V0G_charging(ev, interval_duration):
    available = ev['available']                         # bool
    usage = ev['usage']                                 # kW
    charge_limit = ev['charging_power_limit']           # kW
    max_capacity = ev['max_capacity']                   # kWh
    initial_soc = ev['initial_state_of_charge']         # kWh
    charging_efficiency = ev['charging_efficiency']     # ratio
    tod_charging = retrieve_value(ev, 'tod_charging')   # bool flag
    if tod_charging is not None:
        available = available * tod_charging
    T = len(available)
    soc = np.zeros((T+1,))
    soc[0] = initial_soc
    delta = np.zeros((T,))

    for t in range(T):
        if available[t] and (soc[t] < max_capacity):        # available to charge and not at max capacity
            delta[t] = min(charge_limit, (max_capacity - soc[t])/charging_efficiency/(interval_duration/60))
            soc[t+1] = soc[t] + delta[t] * (interval_duration/60) * charging_efficiency
        else:   # if not available then it might be on a trip and using power
            soc[t+1] = soc[t] - usage[t] * (interval_duration/60)

    success = True if (soc.min() >= 0) else False

    return success, soc[:-1], delta

def ev_name_check(evs):
    """
    Checks if all evs have unique names and raises and error if they do not
    :param evs: list of ev dicts
    """
    names = []
    if evs:
        for ev in evs:
            names.append(ev['name'])
        if len(set(names)) != len(names):
            raise Exception('Not all evs have unique names')



def get_connection_point_info(network_file):
    # Load the raw e-JSON data.
    with open(network_file) as f:
        netw_jsn = json.load(f)

    # Create an empty network.
    netw = sgt.Network()

    # Parse the e-JSON data into the empty network.
    sgt_e_json.parse_e_json(netw, netw_jsn)

    # extract connection point information
    con_point_df = pd.concat([
        pd.DataFrame(
            data=[[zip.id(), zip.n_phases(), zip.bus().v_base(), zip.s_const()],],
            columns=['id','n_phases','v_base','s_const'])
        for zip in netw.zips()], ignore_index=True)
    con_point_df ['LV/MV'] = con_point_df['v_base'].apply(lambda x: 'LV' if x <= 1. else 'MV')
    con_point_df['sum_power'] = con_point_df['s_const'].apply(lambda x: cmath.polar(np.array(x).sum())[0])  # add to>

    return con_point_df

def create_site_from_dict(site_dict):
    load_profile = site_dict['load_profile']
    export_tariff = site_dict['export_tariff']
    import_tariff = site_dict['import_tariff']

    keys = site_dict.keys()
    pv_profile = None if 'pv_profile' not in keys else site_dict['pv_profile']
    evs = retrieve_value(site_dict, 'evs')
    battery = None if 'battery' not in keys else site_dict['battery']
    site_max_import = retrieve_value(site_dict, 'site_max_import')
    site_max_export = retrieve_value(site_dict, 'site_max_export')

    site, objective_set, node_uid_dict = create_site(load_profile=load_profile, export_tariff=export_tariff,
                                                     import_tariff=import_tariff, pv_profile=pv_profile,
                                                     battery=battery, evs=evs,
                                                     site_max_export=site_max_export, site_max_import=site_max_import)
    return site, objective_set, node_uid_dict

def create_site(load_profile, export_tariff, import_tariff, pv_profile=None, battery=None, evs=None, expansion_periods=1,
                site_max_export=None, site_max_import=None):
    # todo: add inverter params as inputs
    # todo: constraint on grid connection
    # todo: deal with convenience and time of day charging

    # check evs have unique names
    ev_name_check(evs)

    # First we need to deal with any evs that are V0G charged and merge them with the load
    if evs:
        for ev in evs:
            charge_model = retrieve_value(ev, 'charge_model')
            if charge_model=='V0G':
                # do something
                t = 1

    num_time_periods = len(load_profile)

    # Create graph
    site = ecm.OptimisationGraph()

    # Create assets
    grid = ecm.Node()       # connection point to grid
    grid.add_named_electrical_ports(['grid'])


    connection_point = ecm.ElectricalTellegenNode()      # summation node
    connection_point.add_named_electrical_ports(['load', 'inv', 'grid'])
    connection_point.ports['grid'].set_flow_constraints(max_import=site_max_import,max_export=site_max_export)
    if evs is not None:
        connection_point.add_named_electrical_ports(['ev'+str(i) for i in range(len(evs))])
        for i, ev in enumerate(evs):
            connection_point.ports['ev'+str(i)].set_flow_constraints(max_import=-ev['discharging_power_limit'],
                                                                     max_export=-ev['charging_power_limit'])

    load = ecm.Node()           # site load
    l1 = ecm.ElectricalDemand()
    l1.add_demand_profile_from_array(load_profile, expansion_periods)
    load.ports['load'] = l1

    nodes_list = [grid, connection_point, load]
    node_uid_dict = {'grid':grid.uid, 'connection_point':connection_point.uid, 'load':load.uid}

    if (battery is not None) or (pv_profile is not None):       # if neither then we don't need an inverter
        inverter = ecm.Inverter(max_import=None, max_export=None, dc_ac_efficiency=1, ac_dc_efficiency=1)
        inverter.add_ac_port('inv')
        if battery is not None:
            inverter.add_dc_port('bess')
        if pv_profile is not None:
            inverter.add_dc_port('pv')
        nodes_list.append(inverter)
        node_uid_dict['inverter'] = inverter.uid

    if battery is not None:
        battery_node = ecm.Node()
        b = ecm.ElectricalStorage(max_capacity=battery['max_capacity'],
                              depth_of_discharge_limit=battery['depth_of_discharge_limit'],
                              charging_power_limit=battery['charging_power_limit'],
                              discharging_power_limit=battery['discharging_power_limit'],
                              charging_efficiency=battery['charging_efficiency'],
                              discharging_efficiency=battery['discharging_efficiency'],
                              initial_state_of_charge=battery['initial_state_of_charge'])
        battery_node.ports['bess'] = b
        nodes_list.append(battery_node)
        node_uid_dict['battery'] = battery_node.uid

    if pv_profile is not None:
        if len(pv_profile) != num_time_periods:
            raise Exception('pv_profile must have same length as load_profile')

        solar = ecm.Node()
        pv = ecm.ElectricalGeneration()
        pv.curtailable = False
        pv.add_generation_profile_from_array(pv_profile, expansion_periods)
        solar.ports['pv'] = pv
        nodes_list.append(solar)
        node_uid_dict['solar'] = solar.uid

    if evs:
        ev_cps = []
        vehicles = []
        trips = []
        for ev in evs:
            available = ev['available']
            usage = ev['usage']
            if len(available) != num_time_periods:
                    raise Exception(ev['name']+' available must have same length as load_profile')
            if len(usage) != num_time_periods:
                    raise Exception(ev['name']+' usage must have same length as load_profile')
            ev_cp = ecm.ElectricalTellegenNode()
            ev_cp.add_named_electrical_ports(['cp', 'ev', 'usage'])
            ev_cp.ports['cp'].add_active_periods_from_array(available, expansion_periods)

            ev_storage = ecm.ElectricalStorage(max_capacity=ev['max_capacity'],
                                    depth_of_discharge_limit=ev['depth_of_discharge_limit'],
                                    charging_power_limit=ev['charging_power_limit'],
                                    discharging_power_limit=-1e4,
                                    charging_efficiency=ev['charging_efficiency'],
                                    discharging_efficiency=ev['discharging_efficiency'],
                                    initial_state_of_charge=ev['initial_state_of_charge'])

            vehicle = ecm.Node()
            vehicle.ports['ev'] = ev_storage

            trip = ecm.Node()
            us_port = ecm.ElectricalDemand()
            us_port.add_demand_profile_from_array(usage, expansion_periods=expansion_periods)
            trip.ports['usage'] = us_port

            ev_cps.append(ev_cp)
            vehicles.append(vehicle)
            trips.append(trip)

            node_uid_dict[ev['name']] = vehicle.uid

        nodes_list = nodes_list + ev_cps + vehicles + trips


    # Populate graph with assets (nodes)
    site.add_node_obj(nodes_list)

    # Add edges to graph
    site.connect_ports_and_create_edge(grid.ports['grid'], connection_point.ports['grid'])
    site.connect_ports_and_create_edge(connection_point.ports['load'], load.ports['load'])
    if (battery is not None) or (pv_profile is not None):
        site.connect_ports_and_create_edge(connection_point.ports['inv'], inverter.ports['inv'])
    if battery is not None:
        site.connect_ports_and_create_edge(inverter.ports['bess'], battery_node.ports['bess'])
    if pv_profile is not None:
        site.connect_ports_and_create_edge(inverter.ports['pv'], solar.ports['pv'])
    if evs is not None:
        for i, ev_cp, vehicle, trip in zip(range(len(evs)),ev_cps, vehicles, trips):
            site.connect_ports_and_create_edge(connection_point.ports['ev'+str(i)], ev_cp.ports['cp'])
            site.connect_ports_and_create_edge(ev_cp.ports['ev'], vehicle.ports['ev'])
            site.connect_ports_and_create_edge(ev_cp.ports['usage'], trip.ports['usage'])

    import_cost = obj.ImportTariff(connection_point.ports['grid'], import_tariff, expansion_periods)
    export_cost = obj.ExportTariff(connection_point.ports['grid'], export_tariff, expansion_periods)

    objective_set = obj.ObjectiveSet(objective_list=[export_cost, import_cost])

    return site, objective_set, node_uid_dict

def extract_site_results(optimiser, site, node_uid_dict):
    keys = node_uid_dict.keys()
    battery = None
    if 'battery' in keys:
        battery = dict()
        battery['SOC'] = optimiser.values(site.node_obj[node_uid_dict['battery']].ports['bess'].soc_value, 0)
        battery['delta'] = optimiser.values(site.node_obj[node_uid_dict['battery']].ports['bess'].port_name, 0)
    ev_names = [name for name in keys if 'ev' in name]
    evs = []
    for ev_name in ev_names:
        ev = dict()
        ev['SOC'] = optimiser.values(site.node_obj[node_uid_dict[ev_name]].ports['ev'].soc_value, 0)
        ev['delta'] = optimiser.values(site.node_obj[node_uid_dict[ev_name]].ports['ev'].port_name, 0)
        evs.append(ev)

    aggregate_load = optimiser.values(site.node_obj[node_uid_dict['connection_point']].ports['grid'].port_name, 0)
    return aggregate_load, battery, evs


if __name__=="__main__":
    # define some tariffs
    # Tariffs are in $ / kwh
    import_tariff_array = np.array(([0.1] * 28 + [0.3] * 8 + [0.2] * 32 + [0.3] * 16 + [0.1] * 12))
    export_tariff_array = np.array(([0.1] * 96))

    ## define load to be used in testing
    test_load = np.array(
        [2.13, 2.09, 2.3, 2.11, 2.2, 2.23, 2.2, 2.15, 2.02, 2.19, 2.19, 2.19, 2.12, 2.15, 2.25, 2.12, 2.21, 2.16,
         2.26, 2.13, 2.08, 2.15, 2.42, 2.02, 2.3, 2.26, 2.35, 2.55, 3.23, 2.98, 3.49, 3.5, 3.12, 3.52, 3.94, 3.55,
         3.99, 3.71, 3.38, 3.76, 3.71, 3.78, 3.29, 3.65, 3.61, 3.75, 3.38, 3.66, 3.56, 3.69, 3.3, 3.61, 3.71, 3.82,
         3.17, 3.69, 3.74, 3.86, 3.57, 3.55, 3.75, 3.6, 3.67, 3.48, 3.51, 3.46, 3.19, 3.38, 3.19, 3.38, 3.04, 3.12,
         2.91, 3.11, 3.13, 2.77, 2.24, 2.54, 2.24, 2.24, 2.09, 2.33, 2.17, 2.16, 1.97, 2.16, 2.21, 2.18, 2.01, 2.16,
         2.19, 2.11, 2.17, 2.13, 2.05, 2.19])

    # test pv generation values
    test_pv = np.array(
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.23, 0.52,
         0.74, 0.71, 0.63, 0.68, 0.97, 0.01, 0.52, 0.83, 0.83, 0.79, 1.22, 1.36, 1.27, 1.42, 1.97, 2.56, 2.91, 3.24,
         3.8, 4.3, 4.62, 4.84, 4.6, 4.17, 3.77, 3.76, 3.38, 2.64, 1.96, 1.76, 1.85, 2.4, 3.82, 5.13, 4.97, 5.02, 5.43,
         5.32, 3.56, 1.75, 1.43, 1.65, 1.69, 2.3, 2.71, 2.41, 2.63, 2.6, 1.9, 0.78, 0.13, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    test_pv *= -1  # convert solar generation to negative to match convention.

    # define battery
    battery = {'max_capacity': 15., 'depth_of_discharge_limit':0,
                'charging_power_limit':1.25, 'discharging_power_limit':-1.25,
               'charging_efficiency':1., 'discharging_efficiency':1.,
               'initial_state_of_charge':0}


    # define some electric vehicles
    # Create vehicle 1

    available1 = np.array([1] * 24 + [0] * 24 + [1] * 24 + [0] * 24)        # binary for when its available to charge
    usage1 = np.array([0.0] * 24 + [0.5] * 24 + [0.0] * 24 + [1.0] * 24)    # energy usage on trip at each time period
    # first vehicle is V2G
    ev1 = {'name':'ev1','available': available1, 'usage': usage1, 'max_capacity': 40., 'depth_of_discharge_limit':0,
           'charging_power_limit':10., 'discharging_power_limit':-10, 'charging_efficiency':1,
           'discharging_efficiency':1,'initial_state_of_charge':0.0}


    # Create vehicle 2
    available2 = np.array([1] * 10 + [0] * 10 + [1] * 28 + [0] * 48)
    usage2 = np.array([0.0] * 10 + [0.4] * 10 + [0.0] * 28 + [0.5] * 48)

    # second vehicle is V1G
    ev2 = {'name':'ev2','available': available2, 'usage': usage2, 'max_capacity': 40., 'depth_of_discharge_limit':0,
           'charging_power_limit':10., 'discharging_power_limit':0, 'charging_efficiency':1,
           'discharging_efficiency':1, 'initial_state_of_charge':0.0}

    # store these so as arrays of size (num_evs, time_periods)
    evs = [ev1, ev2]

    ## Set up hyper params
    time_periods = len(test_load)
    interval_duration = 15
    expansion_periods = 1
    discount_rate = 0

    #   Create a test site with PV and battery
    test_site_1, test_objective_set_1, node_uid_dict_1 = create_site(load_profile=test_load,
                                           export_tariff=export_tariff_array, import_tariff=import_tariff_array,
                                           pv_profile=test_pv, battery=battery)

    # Invoke the optimiser and optimise
    optimiser = EchoOptimiser(interval_duration=interval_duration,
                              number_of_intervals=time_periods,
                              number_of_expansion_intervals=expansion_periods,
                              discount_rate=discount_rate,
                              ES=test_site_1,
                              objective_set=test_objective_set_1, optimiser_engine='cplex')

    optimiser.optimise()

    log_infeasible_constraints(optimiser.model)

    ############################ Analyse the Optimisation ########################################
    sns.set_style({'axes.linewidth': 1, 'axes.edgecolor': 'black', 'xtick.direction': \
        'out', 'xtick.major.size': 4.0, 'ytick.direction': 'out', 'ytick.major.size': 4.0, \
                   'axes.facecolor': 'white', 'grid.color': '.8', 'grid.linestyle': u'-', 'grid.linewidth': 0.5})


    aggregate_load, battery_res, _ = extract_site_results(optimiser, test_site_1, node_uid_dict_1)



    storage_energy_delta = battery_res['delta']
    storage_energy_soc = battery_res['SOC']
    optimised_connection_point_load = aggregate_load

    colors = sns.color_palette()
    hrs = np.arange(0, len(test_load)) / 4
    fig = plt.figure(figsize=(14, 7))
    ax1 = fig.add_subplot(3, 1, 1)
    line1, = ax1.plot(hrs, test_load, color=colors[0])
    line2, = ax1.plot(hrs, test_pv, color=colors[1])
    # line3, = ax1.plot(hrs, optimised_connection_point_load, color=colors[2])
    ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
    ax1.legend([line1, line2], ['Load', 'PV'], ncol=2)
    ax1.set_xlim([0, len(test_load) / 4])
    ax1.set_title('test site 1: PV and Battery')

    ax2 = fig.add_subplot(3, 1, 2)
    line1, = ax2.plot(hrs, import_tariff_array, color=colors[3])
    line2, = ax2.plot(hrs, export_tariff_array, color=colors[4])
    ax2.set_xlabel('hour'), ax2.set_ylabel('price')
    ax2.legend([line1, line2], ['buy price', 'sell price'], ncol=2)
    ax2.set_xlim([0, len(test_load) / 4])

    ax3 = fig.add_subplot(3, 1, 3)
    line1, = ax3.plot(hrs, storage_energy_delta, color=colors[1])
    line2, = ax3.plot(hrs, storage_energy_soc, color=colors[2])
    ax3.set_xlim([0, len(test_load) / 4])
    ax3.set_xlabel('hour'), ax3.set_ylabel('Battery action')
    ax3.legend([line1, line2], ['Charging action (kW)', 'SOC (kWh)'])
    plt.show()

    ## Set up hyper params
    time_periods = len(test_load)
    interval_duration = 15
    expansion_periods = 1
    discount_rate = 0

    #   Create a test site with battery and no PV
    test_site_2, test_objective_set_2, node_uid_dict_2 = create_site(load_profile=test_load, expansion_periods=expansion_periods,
                                           export_tariff=export_tariff_array, import_tariff=import_tariff_array,
                                           pv_profile=None, battery=battery)

    # Invoke the optimiser and optimise
    optimiser_2 = EchoOptimiser(interval_duration=interval_duration,
                              number_of_intervals=time_periods,
                              number_of_expansion_intervals=expansion_periods,
                              discount_rate=discount_rate,
                              ES=test_site_2,
                              objective_set=test_objective_set_2, optimiser_engine='cplex')

    optimiser_2.optimise()

    log_infeasible_constraints(optimiser.model)

    aggregate_load_2, battery_res_2, _ = extract_site_results(optimiser_2, test_site_2, node_uid_dict_2)

    storage_energy_delta_2 = battery_res_2['delta']
    storage_energy_soc_2 = battery_res_2['SOC']
    optimised_connection_point_load_2 = aggregate_load_2


    colors = sns.color_palette()
    hrs = np.arange(0, len(test_load)) / 4
    fig = plt.figure(figsize=(14, 7))
    ax1 = fig.add_subplot(3, 1, 1)
    line1, = ax1.plot(hrs, test_load, color=colors[0])
    ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
    ax1.legend([line1], ['Load'], ncol=2)
    ax1.set_xlim([0, len(test_load) / 4])
    ax1.set_title('test site 2: Battery and no PV')

    ax2 = fig.add_subplot(3, 1, 2)
    line1, = ax2.plot(hrs, import_tariff_array, color=colors[3])
    line2, = ax2.plot(hrs, export_tariff_array, color=colors[4])
    ax2.set_xlabel('hour'), ax2.set_ylabel('price')
    ax2.legend([line1, line2], ['buy price', 'sell price'], ncol=2)
    ax2.set_xlim([0, len(test_load) / 4])

    ax3 = fig.add_subplot(3, 1, 3)
    line1, = ax3.plot(hrs, storage_energy_delta_2, color=colors[1])
    line2, = ax3.plot(hrs, storage_energy_soc_2, color=colors[2])
    ax3.set_xlim([0, len(test_load) / 4])
    ax3.set_xlabel('hour'), ax3.set_ylabel('Battery action')
    ax3.legend([line1, line2], ['Charging action (kW)', 'SOC (kWh)'])
    plt.show()

    connection_import_constraint=15
    # so a single site could be defined as a dictionary
    # storing data as a dict and saving and loading ??
    site_max_import_array = 15*np.ones(test_load.shape)
    site_max_import_array[:5] =5
    test_site_3_dict = {'name':'test_site_3', 'load_profile':test_load,
                        'pv_profile':test_pv, 'battery':battery,
                        'evs':evs, 'export_tariff':export_tariff_array,
                         'import_tariff':import_tariff_array,
                        'site_max_import':site_max_import_array, 'site_max_export':-5}
    ### create a test site with 1 battery, pv, and 2 evs
    test_site_3, test_objective_set_3, node_uid_dict_3 = create_site_from_dict(test_site_3_dict)


    # Invoke the optimiser and optimise
    optimiser_3 = EchoOptimiser(interval_duration=interval_duration,
                              number_of_intervals=time_periods,
                              number_of_expansion_intervals=expansion_periods,
                              discount_rate=discount_rate,
                              ES=test_site_3,
                              objective_set=test_objective_set_3, optimiser_engine='cplex')

    optimiser_3.optimise()

    log_infeasible_constraints(optimiser.model)

    aggregate_load_3, battery_res_3, evs_res = extract_site_results(optimiser_3, test_site_3, node_uid_dict_3)

    storage_energy_delta_3 = battery_res_3['delta']
    storage_energy_soc_3 = battery_res_3['SOC']
    optimised_connection_point_load_3 = aggregate_load_3

    vehicle1_storage = evs_res[0]['SOC']
    vehicle2_storage = evs_res[1]['SOC']

    colors = sns.color_palette()
    hrs = np.arange(0, len(test_load)) / 4
    fig = plt.figure(figsize=(14, 7))
    ax1 = fig.add_subplot(5, 1, 1)
    line1, = ax1.plot(hrs, test_load, color=colors[0])
    line2, = ax1.plot(hrs, test_pv, color=colors[1])
    # line3, = ax1.plot(hrs, optimised_connection_point_load, color=colors[2])
    ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
    ax1.legend([line1, line2], ['Load', 'PV'], ncol=2)
    ax1.set_xlim([0, len(test_load) / 4])
    ax1.set_title('test site 3: PV and Battery and 2 EVS')

    ax2 = fig.add_subplot(5, 1, 2)
    line1, = ax2.plot(hrs, import_tariff_array, color=colors[3])
    line2, = ax2.plot(hrs, export_tariff_array, color=colors[4])
    ax2.set_xlabel('hour'), ax2.set_ylabel('price')
    ax2.legend([line1, line2], ['buy price', 'sell price'], ncol=2)
    ax2.set_xlim([0, len(test_load) / 4])

    ax3 = fig.add_subplot(5, 1, 3)
    line1, = ax3.plot(hrs, storage_energy_delta, color=colors[1])
    line2, = ax3.plot(hrs, storage_energy_soc, color=colors[2])
    ax3.set_xlim([0, len(test_load) / 4])
    ax3.set_xlabel('hour'), ax3.set_ylabel('Battery action')
    ax3.legend([line1, line2], ['Charging action (kW)', 'SOC (kWh)'])

    ax4 = fig.add_subplot(5, 1, 4)
    line1, = ax4.plot(hrs, vehicle1_storage, color=colors[1])
    line2, = ax4.plot(hrs, available1, color=colors[2])
    ax4.set_xlim([0, len(test_load) / 4])
    ax4.set_xlabel('hour'), ax4.set_ylabel('vehicle 1 (V2G)')
    ax4.legend([line1, line2], ['SOC', 'available for charge'])

    ax5 = fig.add_subplot(5, 1, 5)
    line1, = ax5.plot(hrs, vehicle2_storage, color=colors[1])
    line2, = ax5.plot(hrs, available2, color=colors[2])
    ax5.set_xlim([0, len(test_load) / 4])
    ax5.set_xlabel('hour'), ax5.set_ylabel('vehicle 2 (V1G)')
    ax5.legend([line1, line2], ['SOC', 'available for charge'])

    plt.tight_layout()
    plt.show()

    plt.plot(aggregate_load_3)
    plt.show()

    ## testing V0G --- convenience and time signal --- charging
    # a third vehicle that will be either convenience of time of use
    # the 'charge_model' flag can take values 'V0G', 'V1G', or 'V2G'

    tod_charging = np.ones(available2.shape)
    tod_charging[20:30] = 0.
    ev3 = {'name':'ev3','available': available2, 'usage': usage2, 'max_capacity': 40., 'depth_of_discharge_limit':0,
           'charging_power_limit':10., 'discharging_power_limit':0, 'charging_efficiency':1,
           'discharging_efficiency':1, 'initial_state_of_charge':0.0, 'charge_model': 'V0G', 'tod_charging':tod_charging}

    # define test site 4 to have 1 ev and 1 battery and some solar and ev to V0G charge ?

    test_site_4_dict = {'name':'test_site_3', 'load_profile':test_load,
                        'pv_profile':test_pv, 'battery':battery,
                        'evs':[ev3], 'export_tariff':export_tariff_array,
                         'import_tariff':import_tariff_array}

    success, ev_soc, ev_delta = V0G_charging(ev3, interval_duration)

    test_site_4, test_objective_set_4, node_uid_dict_4 = create_site_from_dict(test_site_4_dict)

