import json
import pandas as pd
import numpy as np
import sgt
import sgt_e_json
import matplotlib.pyplot as plt
from tqdm import tqdm
import pickle
import seaborn as sns
import cmath

## echo and optimisation imports
import echo_models as ecm
from echo_optimiser import EchoOptimiser
import objectives as obj
from pyomo.util.infeasible import log_infeasible_constraints

class EchoScenario:
    def __init__(self, network_file=None, name='default_name', description=None):
        self.name = name
        self.description = description
        self.sites = None
        self.num_sites = None
        self.network = None
        self.connection_point_df = None
        self.interval_duration = None
        self.time_periods = None
        self.aggregate_loads = None
        self.processing_errors = None
        # load network model
        if network_file:
            self.load_network_model(network_file)

    def load_network_model(self, network_file):
        # Load the raw e-JSON data.
        print('Importing network data')
        with open(network_file) as f:
            netw_jsn = json.load(f)

        # Create an empty network.
        netw = sgt.Network()

        # Parse the e-JSON data into the empty network.
        sgt_e_json.parse_e_json(netw, netw_jsn)

        # extract connection point information
        con_point_df = pd.concat([
            pd.DataFrame(
                data=[[zip.id(), zip.n_phases(), zip.bus().v_base(), zip.s_const()], ],
                columns=['id', 'n_phases', 'v_base', 's_const'])
            for zip in netw.zips()], ignore_index=True)
        con_point_df['LV/MV'] = con_point_df['v_base'].apply(lambda x: 'LV' if x <= 1. else 'MV')
        con_point_df['sum_power'] = con_point_df['s_const'].apply(
            lambda x: cmath.polar(np.array(x).sum())[0])  # add to>

        self.network_file = network_file
        self.network = netw
        self.connection_point_df = con_point_df
        self.num_sites = len(con_point_df)
        print('Finished importing network data')

    def get_connection_point_info(self):
        return self.connection_point_df

    def add_site_data(self, sites):
        assert self.network is not None, 'load a network before adding site data'
        assert len(sites) == self.num_sites, 'len(sites) must equal len(self.connection_point_df)'
        # check sites for consistency
        # print('Adding site data and checking that all time series data is the same length as the first sites load profile')
        lp = retrieve_value(sites[0], 'load_profile')
        assert lp is not None, 'site 0 has no load_profile'
        time_periods = len(retrieve_value(sites[0], 'load_profile'))
        for i, site in enumerate(sites):
            lp = retrieve_value(site, 'load_profile')
            assert lp is not None, 'site {} has no load profile'.format(i)
            assert len(lp)==time_periods, 'site {} load_profile should have length {} (same as first site)'.format(i, time_periods)
            pv = retrieve_value(site, 'pv_profile')
            if pv is not None:
                assert len(pv)==time_periods, 'site {} pv profile should have length {}'.format(i, time_periods)
            evs = retrieve_value(site, 'evs')
            if evs is not None:
                for j, ev in enumerate(evs):
                    name = retrieve_value(ev, 'name')
                    assert name is not None, 'site {} ev {} must have name'.format(i, j)
                    usage = retrieve_value(ev, 'usage')
                    assert usage is not None, 'site {} ev {} with name {} must have usage'.format(i, j, name)
                    assert len(usage)==time_periods, 'site {}, ev {} with name {} usage should have length {}'.format(i, j, name, time_periods)
                    available = retrieve_value(ev, 'available')
                    assert available is not None, 'site {} ev {} with name {} must have available'.format(i, name, j)
                    assert len(available)==time_periods, 'site {}, ev {} with name {} available should have length {}'.format(i, j, name, time_periods)

        self.sites = sites
        # print('Finished adding site data')

    def save(self, file_name):
        save_dict = vars(self)
        del save_dict['network']
        with open(file_name, 'wb') as handle:
            pickle.dump(save_dict, handle, protocol=pickle.HIGHEST_PROTOCOL)

    def load(self, file_name):
        with open(file_name, 'rb') as handle:
            load_dict = pickle.load(handle)

        self.load_network_model(load_dict['network_file'])
        for key in load_dict:
            setattr(self, key, load_dict[key])

    def optimise_sites(self, time_periods, interval_duration, log_file=None, reprocess=False):
        self.time_periods = time_periods
        self.interval_duration = interval_duration
        aggregate_loads = []
        processing_errors = []
        # todo: implement the log file
        # todo: implement reprocess=False
        for i in tqdm(range(self.num_sites), desc='Optimising sites', file=log_file):
            try:
                self.sites[i] = process_site(self.sites[i], interval_duration, time_periods)
                self.sites[i]['processed'] = True
                processing_errors.append(False)
            except:
                self.sites[i]['processed'] = False
                processing_errors.append(True)

            # todo: what are some other things we want to have all site summaries of?
            aggregate_loads.append(self.sites[i]['aggregate_load'])

        self.aggregate_loads=aggregate_loads
        self.processing_errors = processing_errors
        return processing_errors

    def results_to_df(self):
        if aggregate_load is not None:
            names = [site['name'] for site in self.sites]
            df = pd.DataFrame.from_dict(dict(zip(names, self.aggregate_loads)))
            return df
        else:
            return None


def retrieve_value(dict, key):
    out = None
    if key in dict.keys():
        out = dict[key]
        if hasattr(out, '__len__'):
            if len(out)==0:
                out = None
    return out

def process_site(site_dict, interval_duration, time_periods, expansion_periods=1, discount_rate=0, optimiser_engine='cplex', opt_display=False):
    """
    Process a site
    :param site_dict:
    :param interval_duration:
    :param time_periods:
    :param expansion_periods:
    :param discount_rate:
    :param optimiser_engine:
    :param opt_display:
    :return:
    """

    evs = site_dict['evs']
    ev_name_check(evs)

    # protecting any outside variables from overwrite
    site_dict['load_profile'] = 1 * site_dict['load_profile']
    load_profile_save = 1 * site_dict['load_profile']

    #################### split evs ####################################
    evs_opt = None
    evs_V0G = None
    if evs is not None:
        if len(evs) > 0:
            evs_opt = [ev for ev in evs if (retrieve_value(ev, 'charge_mode') != 'V0G')]
            evs_V0G = [ev for ev in evs if (retrieve_value(ev, 'charge_mode') == 'V0G')]

    ##### process any convenience charge evs        #######
    if evs_V0G is not None:
        for ev in evs_V0G:
            success, ev_soc, ev_delta = V0G_charging(ev, interval_duration)
            ev['delta'] = ev_delta
            ev['SOC'] = ev_soc
            if retrieve_value(ev, 'tod_charging') is not None:
                if success:
                    ev['charge_status'] = 'success'
                else:   # attempt conv
                    success, ev_soc, ev_delta = V0G_charging(ev, interval_duration, force_conv=True)
                    ev['charge_status'] = 'time of day infeasible, convenience success' if success else 'infeasible'

            else:
                ev['charge_status'] = 'success' if success else 'infeasible'
            ev['charge_infeasibility'] = max(-ev_soc.min(),0)

            site_dict['load_profile'] += ev_delta

    ###### check that any V1G evs have charge discharge limit of 0 ############
    if evs_opt:
        for ev in evs_opt:
            if (retrieve_value(ev, 'charge_mode') == 'V1G') and ev['discharging_power_limit'] != 0.0:
                print('\n ev with name '+ ev['name'] + ' is V1G but discharge limit was not zero, setting to zero \n')
                ev['discharging_power_limit'] = 0.

    ############ check if there are any optimisable assets at site and optimise ###################

    if (retrieve_value(site_dict,'battery')) or (evs_opt):
        # set up echo site optimisation model
        # only keep V1G and V2G evs for echo site optimisation
        site_dict['evs'] = evs_opt

        echo_site, objective_set, node_uid_dict = create_echo_site_from_dict(site_dict)
        # Invoke the optimiser and optimise
        optimiser = EchoOptimiser(interval_duration=interval_duration,
                                  number_of_intervals=time_periods,
                                  number_of_expansion_intervals=expansion_periods,
                                  discount_rate=discount_rate,
                                  ES=echo_site,
                                  objective_set=objective_set, optimiser_engine=optimiser_engine)

        optimiser.optimise(tee=opt_display)
        log_infeasible_constraints(optimiser.model)
        # add results into the site dictionary for returning
        site_dict = append_optim_results_to_dict(optimiser, echo_site, node_uid_dict, site_dict)

        if ('infeasible' in optimiser.opt_status['Termination condition']):      # a feasible solution was found
            for ev in site_dict['evs']:
                ev['charge_status'] = 'infeasible'

        # combine back together the V1G, V2G and V0G evs
        if evs_V0G is not None:
            site_dict['evs'] = site_dict['evs'] + evs_V0G

    else:       ### no optimisable assets  so combine everything to get aggregate
        # load profile already includes loads from V0G evs
        if retrieve_value(site_dict, 'pv_profile') is not None:
            site_dict['aggregate_load'] = site_dict['load_profile'] + site_dict['pv_profile']
        else:
            site_dict['aggregate_load'] = load_profile_save

        site_dict['load_profile'] = load_profile_save
        # todo: fix up constraint violation reporting
        site_dict['status'] = 'OK'
        if retrieve_value(site_dict, 'site_max_import') is not None:
            site_dict['import_violation'] = max((site_dict['aggregate_load'] - site_dict['site_max_import']).max(),0)

        if retrieve_value(site_dict, 'site_max_export') is not None:
            site_dict['export_violation'] = max(-(site_dict['aggregate_load'] - site_dict['site_max_export']).min(),0)


    site_dict['load_profile'] = load_profile_save # restore load profile to just be load and not V0G cars

    return site_dict

def V0G_charging(ev, interval_duration, force_conv=False):
    available = ev['available']                         # bool
    usage = ev['usage']                                 # kW
    charge_limit = ev['charging_power_limit']           # kW
    max_capacity = ev['max_capacity']                   # kWh
    initial_soc = ev['initial_state_of_charge']         # kWh
    charging_efficiency = ev['charging_efficiency']     # ratio
    tod_charging = retrieve_value(ev, 'tod_charging')   # bool flag
    if (tod_charging is not None) and (not force_conv):
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


def create_echo_site_from_dict(site_dict):
    load_profile = site_dict['load_profile']
    export_tariff = site_dict['export_tariff']
    import_tariff = site_dict['import_tariff']

    keys = site_dict.keys()
    pv_profile = None if 'pv_profile' not in keys else site_dict['pv_profile']
    evs = retrieve_value(site_dict, 'evs')
    battery = None if 'battery' not in keys else site_dict['battery']
    site_max_import = retrieve_value(site_dict, 'site_max_import')
    site_max_export = retrieve_value(site_dict, 'site_max_export')

    site, objective_set, node_uid_dict = create_echo_site(load_profile=load_profile, export_tariff=export_tariff,
                                                          import_tariff=import_tariff, pv_profile=pv_profile,
                                                          battery=battery, evs=evs,
                                                          site_max_export=site_max_export, site_max_import=site_max_import)
    return site, objective_set, node_uid_dict

def create_echo_site(load_profile, export_tariff, import_tariff, pv_profile=None, battery=None, evs=None, expansion_periods=1,
                     site_max_export=None, site_max_import=None):

    # check evs have unique names
    ev_name_check(evs)
    # split evs into those we will optimise vs those that used V0G charging
    evs_opt = None
    evs_V0G = None
    if evs is not None:
        if len(evs) > 0:
            evs_opt = [ev for ev in evs if (retrieve_value(ev, 'charge_mode') != 'V0G')]
            evs_V0G = [ev for ev in evs if (retrieve_value(ev, 'charge_mode') == 'V0G')]

    # if we have some V0G evs, then add their load to the load profile
    if evs_V0G:
        raise Warning('Echo site should not be passed any V0G EVS')

    num_time_periods = len(load_profile)

    # Create graph
    site = ecm.OptimisationGraph()

    # Create assets
    grid = ecm.Node()       # connection point to grid
    grid.add_named_electrical_ports(['grid'])


    connection_point = ecm.ElectricalTellegenNode()      # summation node
    connection_point.add_named_electrical_ports(['load', 'inv', 'grid'])
    connection_point.ports['grid'].set_flow_constraints(max_import=site_max_import,max_export=site_max_export)
    connection_point.ports['grid'].slack = True         # todo test this and refactor

    if evs_opt is not None:
        connection_point.add_named_electrical_ports(['ev'+str(i) for i in range(len(evs))])
        for i, ev in enumerate(evs_opt):
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

    if evs_opt:
        ev_cps = []
        vehicles = []
        trips = []
        for ev in evs_opt:
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
            vehicle.ports['ev'].enable_min_soc_slack = True

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
    if evs_opt is not None:
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
        ev['name'] = ev_name
        ev['SOC'] = optimiser.values(site.node_obj[node_uid_dict[ev_name]].ports['ev'].soc_value, 0)
        ev['delta'] = optimiser.values(site.node_obj[node_uid_dict[ev_name]].ports['ev'].port_name, 0)
        ev['charge_infeasibility'] = optimiser.values(site.node_obj[node_uid_dict[ev_name]].ports['ev'].min_soc_slack, 0)
        ev['charge_status'] = 'success' if (ev['charge_infeasibility'] == 0) else 'infeasible'

        evs.append(ev)

    import_violation = -optimiser.values(site.node_obj[node_uid_dict['connection_point']].ports['grid'].import_slack, 0)
    export_violation = -optimiser.values(site.node_obj[node_uid_dict['connection_point']].ports['grid'].export_slack, 0)
    aggregate_load = optimiser.values(site.node_obj[node_uid_dict['connection_point']].ports['grid'].port_name, 0)
    return aggregate_load, battery, evs, import_violation, export_violation

def append_optim_results_to_dict(optimiser, site, node_uid_dict, site_dict):
    aggregate_load, battery, evs, import_violation, export_violation = extract_site_results(optimiser, site, node_uid_dict)
    if battery:
        site_dict['battery']['SOC'] = battery['SOC']
        site_dict['battery']['delta'] = battery['delta']
    if evs:
        for ev in evs:
            name = ev['name']
            for i in range(len(site_dict['evs'])):
                if name==site_dict['evs'][i]['name']:
                    site_dict['evs'][i]['SOC'] = ev['SOC']
                    site_dict['evs'][i]['delta'] = ev['delta']
                    site_dict['evs'][i]['charge_infeasibility'] = ev['charge_infeasibility']
                    site_dict['evs'][i]['charge_status'] = ev['charge_status']

    site_dict['aggregate_load'] = aggregate_load
    site_dict['import_violation'] = import_violation
    site_dict['export_violation'] = export_violation
    site_dict['opt_status'] = optimiser.opt_status
    return site_dict

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
    test_site_1, test_objective_set_1, node_uid_dict_1 = create_echo_site(load_profile=test_load,
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
    test_site_2, test_objective_set_2, node_uid_dict_2 = create_echo_site(load_profile=test_load, expansion_periods=expansion_periods,
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
    test_site_3, test_objective_set_3, node_uid_dict_3 = create_echo_site_from_dict(test_site_3_dict)


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

    ## testing V0G --- convenience and time signal --- charging
    # a third vehicle that will be either convenience of time of use
    # the 'charge_model' flag can take values 'V0G', 'V1G', or 'V2G'

    tod_charging = np.ones(available2.shape)
    tod_charging[20:30] = 0.
    ev1 = {'name':'ev1','available': available1, 'usage': usage1, 'max_capacity': 40., 'depth_of_discharge_limit':0,
           'charging_power_limit':10., 'discharging_power_limit':-10, 'charging_efficiency':1,
           'discharging_efficiency':1,'initial_state_of_charge':0.0, 'charge_mode': 'V2G'}

    ev3 = {'name':'ev3','available': available2, 'usage': usage2, 'max_capacity': 40., 'depth_of_discharge_limit':0,
           'charging_power_limit':10., 'discharging_power_limit':0, 'charging_efficiency':1,
           'discharging_efficiency':1, 'initial_state_of_charge':0.0, 'charge_mode': 'V0G', 'tod_charging':tod_charging}

    # ev3 = {'name':'ev3','available': available2, 'usage': usage2, 'max_capacity': 40., 'depth_of_discharge_limit':0,
    #        'charging_power_limit':10., 'discharging_power_limit':0, 'charging_efficiency':1,
    #        'discharging_efficiency':1, 'initial_state_of_charge':0.0, 'charge_mode': 'V0G', 'tod_charging':None}


    # define test site 4 to have 1 ev and 1 battery and some solar and ev to V0G charge ?
    test_site_4_dict = {'name':'test_site_4', 'load_profile':test_load,
                        'pv_profile':test_pv, 'battery':battery,
                        'evs':[ev1, ev3], 'export_tariff':export_tariff_array,
                         'import_tariff':import_tariff_array}

    # process a site with both V0G and V2G/V1G evs
    test_site_4_dict = process_site(test_site_4_dict, interval_duration, time_periods)

    storage_energy_delta = test_site_4_dict['battery']['delta']
    storage_energy_soc = test_site_4_dict['battery']['SOC']

    vehicle1_storage = test_site_4_dict['evs'][0]['SOC']
    vehicle2_storage = test_site_4_dict['evs'][1]['SOC']

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
    ax1.set_title('test site 4: PV and Battery and 2 EVS (1 V2G, 1 V0G)')

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
    ax5.set_xlabel('hour'), ax5.set_ylabel('vehicle 2 (V0G)')
    ax5.legend([line1, line2], ['SOC', 'available for charge'])

    plt.tight_layout()
    plt.show()


    # define test site 5 to have no optimisable assets
    test_site_5_dict = {'name':'test_site_5', 'load_profile':test_load,
                        'pv_profile':test_pv, 'battery':None,
                        'evs':None, 'export_tariff':export_tariff_array,
                         'import_tariff':import_tariff_array}

    test_site_5_dict = process_site(test_site_5_dict, interval_duration, time_periods)

    plt.plot(test_site_5_dict['load_profile'],label='load')
    plt.plot(test_site_5_dict['pv_profile'], label='pv')
    plt.plot(test_site_5_dict['aggregate_load'], label='aggregate')
    plt.legend()
    plt.title('Test site 5: no optimisable assets')
    plt.show()

