import json

import ejson.util as eju
import numpy as np
import pandas as pd
import sgt
import sgt_e_json

sgt.set_message_log_level(sgt.LogLevel.NONE)
sgt.set_warning_log_level(sgt.LogLevel.NONE)

inf = float('inf')
neg_inf = float('-inf')


class TapOptimiser:
    '''
    Class for performing tap optimisations.

    Attributes:
        ej_netw: the e-json network dict.
        sgt_netw: the SGT network.
        v0: target central per-unit voltage.
        num_passes: number of optimisation passes to perform.
    '''

    def __init__(self, ejson_network, df_load_series, sgt_network=None, v0=1.0, num_passes=2):
        '''
        Constructor.

        Args:
            ejson_network: the input e-json network
            df_load_series: a dataframe where each col is the series of complex powers for a load on the network
            num_passes: Taps are optimised individually. For the most part, they
                should be mutually independent. But to deal with any residual
                mutual dependence, several passes of the optimisation can be
                carried out.
        '''

        ''' The e-json network.'''

        self.ej_netw = ejson_network
        self.v0 = v0
        self.num_passes = num_passes

        if sgt_network is None:
            self.sgt_netw = sgt.Network()
            sgt_e_json.parse_e_json(self.sgt_netw, self.ej_netw)
        else:
            self.sgt_netw = sgt_network

        self.buses = {b.id(): b for b in self.sgt_netw.buses()}
        self.zips = {z.id(): z for z in self.sgt_netw.zips()}
        self.txs = (x.downcast(sgt.Transformer) for x in self.sgt_netw.branches())
        self.txs = [x for x in self.txs if x is not None]

        self.df_load_series = df_load_series

        # Make a map of buses below each transformer.
        g = eju.make_graph(self.ej_netw)
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

    def optimise(self):
        '''
        Run the tap optimisation. After it completes, self.ej_netw and
        self.sgt_netw will have taps set to the optimal values.
        '''
        # Set all taps to zero.
        for tx in self.txs:
            tx.set_equal_taps(0)

        # Do the loops
        for pass_ in range(self.num_passes):
            print(f'Pass {pass_}')
            for tx in self.txs:
                print(f'    Transformer {tx.id()}')
                start_tap = tx.taps()[0];
                best_dev = inf
                best_tap = 0;

                for dir_ in (-1, 1):
                    i0 = start_tap if dir_ == -1 else start_tap + 1
                    i1 = tx.min_tap() if dir_ == -1 else tx.max_tap();
                    print(f'        [{i0}, {i1}]')
                    tap = i0
                    while (dir_ == -1 and tap >= i1) or (dir_ == 1 and tap <= i1):
                        print(f'            Trying tap {tap}')
                        tx.set_equal_taps(tap);

                        # Loop over data points
                        lowest = inf
                        highest = neg_inf

                        for t in self.df_load_series.index:
                            # for t in tqdm(self.df_load_series.index, desc='Iterating through load series'):
                            for zid in self.df_load_series.columns:
                                # divide by 1000 to go from kW to MW
                                z = self.zips[zid]
                                v = self.df_load_series.at[t, zid]
                                nc = z.n_comps()
                                s_vec = [v / nc] * nc
                                z.set_s_const(s_vec)

                            ok = self.sgt_netw.solve_power_flow()
                            if not ok:
                                print("            Couldn't solve power flow, ignoring data point")
                                continue

                            v_env = self.voltage_envelope(self.tx_buses[tx.id()])

                            if (v_env[0] < lowest):
                                lowest = v_env[0];

                            if (v_env[1] > highest):
                                highest = v_env[1];

                        dev = abs(self.v0 - 0.5 * (lowest + highest));
                        print(f'                dev = {dev}')
                        if (dev < best_dev):
                            print(f'                Deviation is best')
                            best_dev = dev
                            best_tap = tap
                        else:
                            print(f'                Deviation is not best')
                            break

                        tap += dir_

                    if (best_tap != start_tap):
                        # No point in trying the other direction if we improved in this direction.
                        break
                print(f'        Best tap = {best_tap}')
                tx.set_equal_taps(best_tap)
                self.ej_netw['components'][tx.id()]['Transformer']['taps'] = tx.taps()

    def voltage_envelope(self, buses):
        ve_min = 1e6
        ve_max = -1e6
        for bid, b in buses:
            v = np.abs(b.v()) / b.v_base()
            ve_min = min(np.min(v), ve_min)
            ve_max = max(np.max(v), ve_max)

        return (ve_min, ve_max)


def dummy_loads(ej_netw):
    lds = {}
    ld_ids = [k for k, v in ej_netw['components'].items() if next(iter(v.keys())) == 'Load']
    for ld_id in ld_ids:
        p = np.random.normal(loc=1e-3, scale=1e-3, size=10)
        q = 0.2 * abs(p)
        s = p + 1j * q
        lds[ld_id] = s

    return lds


def echo_to_sgt_loads(loads_df, power_factor=0.93):
    powers = loads_df.to_numpy()

    complex_power = get_s(powers / 1000, pf=power_factor)  # convert from KW to MW and make complex
    df_new = pd.DataFrame(data=complex_power, columns=loads_df.columns)
    return df_new


def optimise_taps(json_network, loads_df, subset=None, save_file=None, power_factor=0.93):

    if subset is None:
        complex_loads_df = echo_to_sgt_loads(loads_df, power_factor=power_factor)
    else:
        complex_loads_df = echo_to_sgt_loads(loads_df.iloc[subset], power_factor=power_factor)

    assert len(complex_loads_df) <=30, "load series are too long, use 30 or less representative points"


    opt = TapOptimiser(json_network, complex_loads_df)
    opt.optimise()

    if save_file is not None:
        with open(save_file, 'w+') as f:
            json.dump(opt.ej_netw, f, indent=2)

    return opt.ej_netw, opt.sgt_netw


def get_s(p, pf=0.93):
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


if __name__ == '__main__':
    infile = '../data/ausnet_a.json'
    outfile = '../data/ausnet_a_2.json'

    # Parse in the e-json network.
    with open(infile) as f:
        ej_netw = json.load(f)

    import echo.echo_scenario as ecs

    file_name = '../data/test_scenario.pickle'
    scenario = ecs.EchoScenario(load_file=file_name)

    loads_df = scenario.aggregate_load_df()

    subset = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
    json_network, sgt_network = optimise_taps(scenario.json_network, loads_df, subset=subset, save_file=None,
                                              power_factor=0.93)

    # scenario.optimise_transformer_taps(subset=[10,11,12,13,14,15,16,17,18,19,20])

    # complex_loads_df = echo_to_sgt_loads(loads_df[10:20], power_factor=0.93)
    complex_loads_df = echo_to_sgt_loads(loads_df.iloc[subset], power_factor=0.93)


    # Create a TapOptimiser and run it.
    opt = TapOptimiser(scenario.json_network, complex_loads_df)
    opt.optimise()

    # opt.ej_netw is the now modified ej_netw.
    # opt.sgt_netw is a SGT network object.
    # Both have optimal tap settings now.

    # Write out the modified e-JSON.
    with open(outfile, 'w+') as f:
        json.dump(opt.ej_netw, f, indent=2)
