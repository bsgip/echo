import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm
import pickle
import seaborn as sns
import cmath
import lzma

## echo and optimisation imports
import echo.echo_models as ecm
from echo.echo_optimiser import EchoOptimiser
import echo.objectives as obj
from pyomo.util.infeasible import log_infeasible_constraints

class EchoScenario:
    def __init__(self, network_file=None, name='default_name', description=None, energy_only=False, load_file=None, byte_string=False):
        self.name = name
        self.description = description
        self.energy_only = energy_only
        self.sites = None
        self.num_sites = None
        self.network = None
        self.connection_point_df = None
        self.interval_duration = None
        self.time_periods = None
        self.aggregate_loads = None
        self.processing_errors = None
        # load network model
        if network_file and not energy_only:
            self.load_network_model(network_file)

        if (network_file is None) and load_file is not None:
            self.load(load_file, byte_string=byte_string)

    def load_network_model(self, network_file):
        # Load the raw e-JSON data.
        # import sgt and sgt-e-json for power flows
        import sgt
        import sgt_e_json
        sgt.set_message_log_level(sgt.LogLevel.NONE)
        sgt.set_warning_log_level(sgt.LogLevel.NONE)

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
        if not self.energy_only:
            assert self.network is not None, 'load a network before adding site data'
            assert len(sites) == self.num_sites, 'len(sites) must equal len(self.connection_point_df)'
        else:
            self.num_sites = len(sites)

        sites = sites.copy()            # prevent overwriting of input
        # check sites for consistency
        # print('Adding site data and checking that all time series data is the same length as the first sites load profile')
        lp = retrieve_value(sites[0], 'load_profile')
        assert lp is not None, 'site 0 has no load_profile'
        time_periods = len(retrieve_value(sites[0], 'load_profile'))
        # todo: add more checks!!
        for i, site in enumerate(sites):
            # load checks
            lp = retrieve_value(site, 'load_profile')
            assert lp is not None, 'site {} has no load profile'.format(i)
            assert len(lp)==time_periods, 'site {} load_profile should have length {} (same as first site)'.format(i, time_periods)

            # site import/export constraint checks
            array_length_check(retrieve_value(site,'site_max_import'), time_periods,
                               'site {} max import constraint should have length {} or be scalar (same as first site)'.format(i, time_periods), scalar_ok=True)
            array_length_check(retrieve_value(site, 'site_max_export'), time_periods,
                               'site {} max exoirt constraint should have length {} or be scalar (same as first site)'.format(i, time_periods), scalar_ok=True)

            # tariff checks
            array_length_check(retrieve_value(site,'import_tariff'), time_periods,
                               'site {} import_tariff should have length {} (same as first site)'.format(i, time_periods))
            array_length_check(retrieve_value(site,'export_tariff'), time_periods,
                               'site {} export_tariff should have length {} (same as first site)'.format(i, time_periods))
            variable = retrieve_value(site, 'import_demand_charges')
            if variable is not None:
                if not isinstance(variable, list):
                    variable = [variable]
                for j, v in enumerate(variable):
                    assert isinstance(v, dict), 'site {} import demand charge {} must be a dictionary'.format(i,j)
                    assert retrieve_value(v, 'rate') is not None, 'site {} import demand charge {} must have rate'.format(i, j)
                    assert retrieve_value(v, 'window') is not None, 'site {} import demand charge {} must have window'.format(i, j)
                    array_length_check(v['window'], time_periods, 'site {} import demand charge {} window must have length {}'.format(i,j,time_periods))
                variable = retrieve_value(site, 'export_demand_charges')
            if variable is not None:
                if not isinstance(variable, list):
                    variable = [variable]
                for j, v in enumerate(variable):
                    assert isinstance(v, dict), 'site {} export demand charge {} must be a dictionary'.format(i,j)
                    assert retrieve_value(v, 'rate') is not None, 'site {} export demand charge {} must have rate'.format(i, j)
                    assert retrieve_value(v, 'window') is not None, 'site {} export demand charge {} must have window'.format(i, j)
                    array_length_check(v['window'], time_periods, 'site {} export demand charge {} window must have length {}'.format(i,j,time_periods))


            # pv checks
            pv = retrieve_value(site, 'pv_profile')
            if pv is not None:
                assert len(pv)==time_periods, 'site {} pv profile should have length {}'.format(i, time_periods)

            # ev checks
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
                    array_length_check(retrieve_value(ev, 'tod_charging'), time_periods, 'site {}, ev {} with name {} tod_charging should have length {}'.format(i, j, name, time_periods))

        self.sites = sites
        # print('Finished adding site data')


    def save(self, file=None):
        save_dict = vars(self).copy()
        del save_dict['network']

        if file:
            with open(file, 'wb') as handle:
                pickle.dump(save_dict, handle, protocol=pickle.HIGHEST_PROTOCOL)
            return None
        else:
            return pickle.dumps(save_dict, protocol=pickle.HIGHEST_PROTOCOL)


    def load(self, file, byte_string=False):
        if not byte_string:
            with open(file, 'rb') as handle:
                load_dict = pickle.load(handle)
        else:
            load_dict = pickle.loads(file)
        if not load_dict['energy_only']:
            self.load_network_model(load_dict['network_file'])
        for key in load_dict:
            setattr(self, key, load_dict[key])


    # def optimise_sites_batched(self, time_periods, interval_duration, log_file=None):
    #     # create copy of site
    #     # reduce the timeseries data in the copy down to the batch we are interested in
    #     # optimise
    #     # amalgamate results

    def optimise_sites(self, time_periods, interval_duration, log_file=None):
        self.time_periods = time_periods
        self.interval_duration = interval_duration
        aggregate_loads = []
        processing_errors = []
        if log_file is not None:
            prog_file = open(log_file, 'w')
        else:
            prog_file = None
        for i in tqdm(range(self.num_sites), desc='Optimising sites', file=prog_file):
            try:
                self.sites[i] = process_site(self.sites[i], interval_duration, time_periods)
                self.sites[i]['processed'] = True
                processing_errors.append(False)
                aggregate_loads.append(self.sites[i]['aggregate_load'])
            except:
                self.sites[i]['processed'] = False
                processing_errors.append(True)
                aggregate_loads.append(np.array([]))
        if log_file is not None:
            prog_file.close()

        self.aggregate_loads=aggregate_loads
        self.processing_errors = processing_errors
        return processing_errors

    def aggregate_load_df(self):
        if self.aggregate_loads is not None:
            names = [site['name'] for site in self.sites]
            df = pd.DataFrame.from_dict(dict(zip(names, self.aggregate_loads)))
            return df
        else:
            return None

    def run_power_flows(self, power_factor=0.93, save_pickle_file=None, log_file=None, auto_taps=True):
        assert not self.energy_only, 'create a scenario with energy_only=False to run power flows'

        # import sgt and sgt-e-json for power flows
        import sgt
        import sgt_e_json
        sgt.set_message_log_level(sgt.LogLevel.NONE)
        sgt.set_warning_log_level(sgt.LogLevel.NONE)

        assert self.aggregate_loads is not None, "Aggregate loads need to be calculated first"
        zips = {z.id(): z for z in self.network.zips()}
        agg_loads_df = self.aggregate_load_df()

        # get bus names
        bus_name = []
        for bus in self.network.buses():
            bus_name += [bus.id() + '.' + str(phase) for phase in bus.phases()]

        # get branch names
        branch_name_0 = []
        branch_name_1 = []
        transformer_names = []
        for branch in self.network.branches():
            branch_name_0 += [branch.id() + '.' + str(phase) for phase in branch.phases_0()]
            branch_name_1 += [branch.id() + '.' + str(phase) for phase in branch.phases_1()]
            if branch.component_type() == 'transformer':
                transformer_names.append(branch.id())

        # get a list of transformers
        transformers = [sgt.Transformer.from_branch(br) for br in self.network.branches() if
                        br.component_type() == 'transformer']

        status = []
        v_pu_list = []
        br_power_0_list = []
        br_power_1_list = []
        br_current_0_list = []
        br_current_1_list = []
        p_inbalance_list = []
        gen_total_list = []
        zip_total_list = []
        loss_total_list = []

        if log_file is not None:
            prog_file = open(log_file, 'w')
        else:
            prog_file = None

        for t in tqdm(agg_loads_df.index, desc='Running power flows', file=prog_file):
            # set the loads
            for zid in agg_loads_df.columns:
                # divide by 1000 to go from kW to MW
                set_zip_total_power(zips[zid], agg_loads_df.at[t, zid] / 1000, pf=power_factor)

            # run the power flow
            if auto_taps:
                tap_changed = auto_taps     # enable or disable automatic tap changing
                while tap_changed:
                    ss = self.network.solve_power_flow()
                    ss = self.network.solve_power_flow()
                    tap_changed = False     # set to false and then see if at least one reg had tap changed
                    for transformer in transformers:
                        tap_changed = transformer.run_tap_changers_once() or tap_changed
            else:
                ss = self.network.solve_power_flow()
            status.append(ss)

            # get the bus voltages
            v_pu = []
            for bus in self.network.buses():
                v_base = bus.v_base()
                v_pu += [abs(x) / v_base for x in bus.v()]
            v_pu_list.append(v_pu)

            # get branch
            br_power_0 = []
            br_power_1 = []
            br_current_0 = []
            br_current_1 = []
            p_loss_tot = 0.0  # Total losses.
            for branch in self.network.branches():
                br_power = branch.s_term()
                br_power_0 += br_power[0]
                br_power_1 += br_power[1]
                br_current = branch.i_term()
                br_current_0 += br_current[0]
                br_current_1 += br_current[1]
                p_loss_tot += np.real(np.sum(br_power[0]) + np.sum(br_power[1]))
            br_power_0_list.append(br_power_0)
            br_power_1_list.append(br_power_1)
            br_current_1_list.append(br_current_1)
            br_current_0_list.append(br_current_0)

            p_gen_tot = 0.0  # Total generation.
            for g in self.network.gens():
                # Add up the total real power generation of each generator.
                p_gen_tot += np.sum(np.real(np.array(g.s())))

            p_zip_tot = 0.0  # Total load power
            for z in self.network.zips():
                # Add up the total real power consumption of each zip.
                p_zip_tot += np.sum(np.real(np.array(z.s())))

            p_inbalance = p_gen_tot - p_zip_tot - p_loss_tot  # Should add to zero: generation = load + losses.
            p_inbalance_list.append(p_inbalance)
            gen_total_list.append(p_gen_tot)
            loss_total_list.append(p_loss_tot)
            zip_total_list.append(p_zip_tot)

        if log_file is not None:
            prog_file.close()

        bus_voltage_df = pd.DataFrame(data=v_pu_list, columns=bus_name)
        branch_power_0_df = pd.DataFrame(data=br_power_0_list, columns=branch_name_0)
        branch_power_1_df = pd.DataFrame(data=br_power_1_list, columns=branch_name_1)
        branch_current_0_df = pd.DataFrame(data=br_current_0_list, columns=branch_name_0)
        branch_current_1_df = pd.DataFrame(data=br_current_1_list, columns=branch_name_1)

        power_flow_results = {'status':status, 'bus_voltage':bus_voltage_df,'branch_power_0':branch_power_0_df,
                                'branch_power_1':branch_power_1_df, 'branch_current_0':branch_current_0_df,
                                'branch_current_1':branch_current_1_df, 'transformer_names':transformer_names,
                              'power_inbalance':p_inbalance_list, 'total_generation':gen_total_list,
                              'total_loss':loss_total_list, 'total_zip':zip_total_list}

        if save_pickle_file is not None:
            with lzma.open(save_pickle_file + '.lzma', 'wb') as handle:
                pickle.dump(power_flow_results, handle, protocol=4)

        return power_flow_results

def array_length_check(array, length, message, scalar_ok=False):
    if array is not None:
        if hasattr(array, '__len__') or (not scalar_ok):
            assert len(array) == length, message


def get_s(p, pf=0.93):
    '''
    Get complex power s

    Args:
        p: the power (numpy array or scalar)
        pf: the power factor

    Returns:
        the complex power
    '''

    q = np.sqrt(pow(p, 2) * (1.0 / pow(pf, 2) - 1.0)) # q = abs(p) * q_fact
    return p + 1j * q

def set_zip_total_power(zip_, p, pf=0.93):
    '''
    Set the total power of a zip (load).

    Args:
        zip_: the zip object
        p: the total power
        pf: the power factor
    '''

    # n_ph = zip_.n_phases()        # for some reason this isn't always working out
    n_ph = zip_.n_comps()
    s_per_ph = get_s(p / n_ph, pf)
    s = [s_per_ph] * n_ph
    zip_.set_s_const(s)


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
            success, ev_soc, ev_delta, trip_infeasibility = V0G_charging(ev, interval_duration)
            ev['delta'] = ev_delta
            ev['SOC'] = ev_soc
            if retrieve_value(ev, 'tod_charging') is not None:
                if success:
                    ev['charge_status'] = 'success'
                else:   # attempt conv
                    success, ev_soc, ev_delta, trip_infeasibility = V0G_charging(ev, interval_duration, force_conv=True)
                    ev['charge_status'] = 'time of day infeasible, convenience success' if success else 'infeasible'

            else:
                ev['charge_status'] = 'success' if success else 'infeasible'
            ev['trip_infeasibility'] = trip_infeasibility

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

        site_dict['status'] = 'OK'
        if retrieve_value(site_dict, 'site_max_import') is not None:
            site_dict['import_violation'] = np.maximum((site_dict['aggregate_load'] - site_dict['site_max_import']),0)
        else:
            site_dict['import_violation'] = 0 * site_dict['aggregate_load']

        if retrieve_value(site_dict, 'site_max_export') is not None:
            site_dict['export_violation'] = np.minimum((site_dict['aggregate_load'] - site_dict['site_max_export']),0)
        else:
            site_dict['export_violation'] = 0 * site_dict['aggregate_load']


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
    trip_infeasibility = np.zeros((T+1,))
    delta = np.zeros((T,))

    for t in range(T):
        if available[t] and (soc[t] < max_capacity):        # available to charge and not at max capacity
            delta[t] = min(charge_limit, (max_capacity - soc[t])/charging_efficiency/(interval_duration/60))
            soc[t+1] = soc[t] + delta[t] * (interval_duration/60) * charging_efficiency
        else:   # if not available then it might be on a trip and using power
            soc[t+1] = soc[t] - usage[t] * (interval_duration/60)
        trip_infeasibility[t+1] = - min(soc[t+1], 0)
        soc[t+1] = max(soc[t+1], 0)


    success = True if (trip_infeasibility.max() == 0) else False

    return success, soc[:-1], delta, trip_infeasibility[:-1]

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
    import_demand_charges = retrieve_value(site_dict, 'import_demand_charges')
    export_demand_charges = retrieve_value(site_dict, 'export_demand_charges')

    site, objective_set, node_uid_dict = create_echo_site(load_profile=load_profile, export_tariff=export_tariff,
                                                          import_tariff=import_tariff, pv_profile=pv_profile,
                                                          battery=battery, evs=evs, import_demand_charges=import_demand_charges,
                                                          site_max_export=site_max_export, site_max_import=site_max_import,
                                                          export_demand_charges=export_demand_charges)
    return site, objective_set, node_uid_dict

def create_echo_site(load_profile, export_tariff, import_tariff, pv_profile=None, battery=None, evs=None, expansion_periods=1,
                     site_max_export=None, site_max_import=None, import_demand_charges=None, export_demand_charges=None):

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
    if (site_max_import is not None) or (site_max_export is not None):
        connection_point.ports['grid'].set_flow_constraints(max_import=site_max_import,max_export=site_max_export, slack=True)

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
            soc_conserv = retrieve_value(ev, 'soc_conserv')
            soc_conserv_cost = retrieve_value(ev, 'soc_conserv_cost')

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
            vehicle.ports['ev'].enable_trip_slack = True
            if soc_conserv is not None:
                assert soc_conserv_cost is not None, 'soc_conserv requires soc_conserve_cost'
                vehicle.ports['ev'].soc_conserv = soc_conserv  # kWh
                vehicle.ports['ev'].soc_conserv_cost = soc_conserv_cost # dollars per kwh
                vehicle.ports['ev'].available = available

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

    objective_list=[]
    if import_tariff is not None:
        import_cost = obj.ImportTariff(connection_point.ports['grid'], import_tariff, expansion_periods)
        objective_list.append(import_cost)
    if export_tariff is not None:
        export_cost = obj.ExportTariff(connection_point.ports['grid'], export_tariff, expansion_periods)
        objective_list.append(export_cost)
    if import_demand_charges is not None:
        if not isinstance(import_demand_charges, list):
            import_demand_charges = [import_demand_charges]
        tmp_list = []
        for charge in import_demand_charges:
            tmp_list.append(obj.DemandCharge(rate=charge['rate'], min_demand=0, window_array=charge['window']))
        import_demand_tariff = obj.ImportDemandTariffObjective(component=connection_point.ports['grid'],
                                                           demand_charges=tmp_list)
        objective_list.append(import_demand_tariff)
    if export_demand_charges is not None:
        if not isinstance(export_demand_charges, list):
            export_demand_charges = [export_demand_charges]
        for charge in export_demand_charges:
            tmp_list.append(obj.DemandCharge(rate=charge['rate'], min_demand=0, window_array=charge['window']))
        tmp_list = []
        export_demand_tariff = obj.ExportDemandTariffObjective(component=connection_point.ports['grid'],
                                                               demand_charges=tmp_list)
        objective_list.append(export_demand_tariff)

    assert len(objective_list) > 0, 'At least one tariff needs to be specified'

    objective_set = obj.ObjectiveSet(objective_list=objective_list)

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
        ev['trip_infeasibility'] = optimiser.values(site.node_obj[node_uid_dict[ev_name]].ports['ev'].trip_slack, 0)
        ev['charge_status'] = 'success' if all(ev['trip_infeasibility'] == 0) else 'infeasible'

        evs.append(ev)

    aggregate_load = optimiser.values(site.node_obj[node_uid_dict['connection_point']].ports['grid'].port_name, 0)

    if hasattr(site.node_obj[node_uid_dict['connection_point']].ports['grid'], 'import_slack'):
        import_violation = -optimiser.values(site.node_obj[node_uid_dict['connection_point']].ports['grid'].import_slack, 0)
    else:
        import_violation = 0. * aggregate_load

    if hasattr(site.node_obj[node_uid_dict['connection_point']].ports['grid'], 'export_slack'):
        export_violation = -optimiser.values(site.node_obj[node_uid_dict['connection_point']].ports['grid'].export_slack, 0)
    else:
        export_violation = 0. * aggregate_load


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
                    site_dict['evs'][i]['trip_infeasibility'] = ev['trip_infeasibility']
                    site_dict['evs'][i]['charge_status'] = ev['charge_status']

    site_dict['aggregate_load'] = aggregate_load
    site_dict['import_violation'] = import_violation
    site_dict['export_violation'] = export_violation
    site_dict['opt_status'] = optimiser.opt_status
    return site_dict
