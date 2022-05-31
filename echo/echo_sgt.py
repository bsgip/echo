import json
import pandas as pd
import cmath
import numpy as np
from tqdm import tqdm
import pickle
import cmath
import lzma

from echo.echo_builder import NetworkSet
import ejson.util as eju
import sgt
import sgt_e_json
sgt.set_message_log_level(sgt.LogLevel.NONE)
sgt.set_warning_log_level(sgt.LogLevel.NONE)

inf = float('inf')
neg_inf = float('-inf')

class SGT_interface():
    def __init__(self, network_file):
        with open(network_file) as f:
            netw_jsn = json.load(f)

        print('Loading network model.')
        # Create an empty network.
        netw = sgt.Network()

        # Parse the e-JSON data into the empty network.
        sgt_e_json.parse_e_json(netw, netw_jsn)

        con_point_df = pd.concat([pd.DataFrame(data=[[zip.id(), zip.n_phases(), zip.bus().v_base(), zip.s_const()], ],columns=['id', 'n_phases', 'v_base', 's_const']) for zip in netw.zips()], ignore_index=True)

        con_point_df['LV/MV'] = con_point_df['v_base'].apply(lambda x: 'LV' if x <= 1. else 'MV')
        con_point_df['sum_power'] = con_point_df['s_const'].apply(lambda x: cmath.polar(np.array(x).sum())[0])  # add to

        self.network_file = network_file
        self.network = netw
        self.network_json = netw_jsn
        self.connection_point_df = con_point_df
        self.num_connections = len(con_point_df)
        self.load_series = None
        print('Finished loading model.')

    def get_connection_info(self):
        return self.connection_point_df

    def save_ejson(self, filename):
        with open(filename, 'w') as f:
            json.dump(self.network_json, f)

    def power_flows(self, power_factor=0.93, save_pickle_file=None, log_file=None, auto_taps=True):

        assert self.load_series is not None, "Needs timeseries of loads"

        zips = {z.id(): z for z in self.network.zips()}
        load_series_df = self.load_series

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

        for t in tqdm(load_series_df.index, desc='Running power flows', file=prog_file):
            # set the loads
            for zid in load_series_df.columns:
                # divide by 1000 to go from kW to MW
                SGT_interface._set_zip_total_power(zips[zid], load_series_df.at[t, zid], pf=power_factor)

            # run the power flow
            if auto_taps:
                tap_changed = auto_taps     # enable or disable automatic tap changing
                while tap_changed:
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

    @staticmethod
    def _set_zip_total_power(zip_, p, pf=0.93):
        '''
        Set the total power of a zip (load).

        Args:
            zip_: the zip object
            p: the total power
            pf: the power factor
        '''

        # n_ph = zip_.n_phases()        # for some reason this isn't always working out
        n_ph = zip_.n_comps()
        s_per_ph = SGT_interface._get_s(p / n_ph, pf)
        s = [s_per_ph] * n_ph
        zip_.set_s_const(s)

    @staticmethod
    def _get_s(p, pf=0.93):
        '''
        Get complex power s

        Args:
            p: the power (numpy array or scalar)
            pf: the power factor

        Returns:
            the complex power
        '''

        q = np.sqrt(pow(p, 2) * (1.0 / pow(pf, 2) - 1.0))  # q = abs(p) * q_fact
        return p + 1j * q

    def load_series_from_df(self, df, mapping=None):
        """
        get load series from a dataframe,
        if mapping is None then first col of dataframe is demand info for first load and so on

        otherwise mapping must be a dict such that specifing how each column of the provided dataframe
         maps to a connection point id {'df_col_name_1':'connection_point_id', ...}

        """

        assert len(df.columns)==self.num_connections, 'dataframe must have one timeseries (column) per connection point'
        load_series = df.copy()

        if mapping is None:
            load_series.columns=self.connection_point_df['id']
        else:
            load_series.rename(columns=mapping)

        self.load_series = load_series / 1000   # convert from kW to MW

    def optimise_taps(self, v0=1.0, num_passes=2):
        # print('Optimising transformer tap settings')
        assert len(self.load_series) <= 30, 'load series cannot have more than 30 timesteps'

        self.v0 = v0
        self.num_passes = num_passes

        self.buses = {b.id(): b for b in self.network.buses()}
        self.zips = {z.id(): z for z in self.network.zips()}
        self.txs = (x.downcast(sgt.Transformer) for x in self.network.branches())
        self.txs = [x for x in self.txs if x is not None]

        # Make a map of buses below each transformer.
        g = eju.make_graph(self.network_json)
        infeeders = [cid for cid, ctype, cd in eju.graph_components(g) if ctype == 'Infeeder']
        assert len(infeeders) == 1
        infeeder = infeeders[0]
        g = eju.reorder(g, start=infeeder)  # Make sure network is oriented.

        self.tx_buses = {}

        for tx in self.txs:
            bus1 = tx.bus1().id()
            accum = self.tx_buses.setdefault(tx.id(), [])

            def pre_cb(g, cur, accum):
                if cur == tx.id():
                    return (True, accum)

                ctp, cd = g.nodes[cur]['comp']
                if ctp == 'Node':
                    accum.append((cur, self.buses[cur]))

                return (False, accum)

            visited, accum = eju.dfs(g, bus1, pre_cb=pre_cb, accum=accum)

        # Set all taps to zero.
        for tx in self.txs:
            tx.set_equal_taps(0)

        # Do the loops
        with tqdm(total=self.num_passes * len(self.txs), desc='Optimising transformer taps') as pbar:
            for pass_ in range(self.num_passes):
                # tqdm.write('pass {} of {}'.format(pass_, self.num_passes))
                for tx in self.txs:
                    # tqdm.write(f'    Transformer {tx.id()}')
                    start_tap = tx.taps()[0];
                    best_dev = inf
                    best_tap = 0;

                    for dir_ in (-1, 1):
                        i0 = start_tap if dir_ == -1 else start_tap + 1
                        i1 = tx.min_tap() if dir_ == -1 else tx.max_tap();
                        # print(f'        [{i0}, {i1}]')
                        tap = i0
                        while (dir_ == -1 and tap >= i1) or (dir_ == 1 and tap <= i1):
                            # print(f'            Trying tap {tap}')
                            tx.set_equal_taps(tap);

                            # Loop over data points
                            lowest = inf
                            highest = neg_inf

                            for t in self.load_series.index:
                                # for t in tqdm(self.df_load_series.index, desc='Iterating through load series'):
                                for zid in self.load_series.columns:
                                    # divide by 1000 to go from kW to MW
                                    z = self.zips[zid]
                                    v = self.load_series.at[t, zid]
                                    nc = z.n_comps()
                                    s_vec = [v / nc] * nc
                                    z.set_s_const(s_vec)

                                ok = self.network.solve_power_flow()
                                if not ok:
                                    # print("            Couldn't solve power flow, ignoring data point")
                                    continue

                                v_env = self._voltage_envelope(self.tx_buses[tx.id()])

                                if (v_env[0] < lowest):
                                    lowest = v_env[0];

                                if (v_env[1] > highest):
                                    highest = v_env[1];

                            dev = abs(self.v0 - 0.5 * (lowest + highest));
                            # print(f'                dev = {dev}')
                            if (dev < best_dev):
                                # print(f'                Deviation is best')
                                best_dev = dev
                                best_tap = tap
                            else:
                                # print(f'                Deviation is not best')
                                break

                            tap += dir_

                        if (best_tap != start_tap):
                            # No point in trying the other direction if we improved in this direction.
                            break

                    pbar.update(1)
                    # print(f'        Best tap = {best_tap}')
                tx.set_equal_taps(best_tap)
                self.network_json['components'][tx.id()]['Transformer']['taps'] = tx.taps()

        print('Finished optimising transformer tap settings')

    def _voltage_envelope(self, buses):
        ve_min = 1e6
        ve_max = -1e6
        for bid, b in buses:
            v = np.abs(b.v()) / b.v_base()
            ve_min = min(np.min(v), ve_min)
            ve_max = max(np.max(v), ve_max)

        return (ve_min, ve_max)

    def loads_from_netset(self, netset, node, port):
        """
            TODO: function to get loads directly from an echo netset
            Remember, if not using the load_series from df, then we need to convert to MW somewhere else
        """
        return None

    def loads_from_network(self, network, mapping):
        """
            TODO: function to get loads directly from an echo network
            Remember, if not using the load_series from df, then we need to convert to MW somewhere else
        """
        return None





if __name__=="__main__":
    network_file = '../data/ausnet_a.json'

    sgt_interface = SGT_interface(network_file)

    df = pd.read_csv('../data/dummy_netset_loads.csv', index_col=[0])

    sgt_interface.load_series_from_df(df[0:15], mapping=None)

    sgt_interface.optimise_taps()

    pf_results = sgt_interface.power_flows()