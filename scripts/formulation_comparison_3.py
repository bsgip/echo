# some imports
import pandas as pd
import pyomo.environ as pyo
import numpy as np
import matplotlib.pyplot as plt
from pyomo.opt import SolverFactory
import time
from tqdm import tqdm

# some options
list_num_days = np.arange(1,47,5).tolist()
solve_times_1 = []
solve_times_2 = []

for num_days in tqdm(list_num_days):

    # setting up the problem
    # problem is set up considering 15 minute time intervals and then all units are given in kWh

    battery_cap = 10            # max battery capacity kWh
    battery_discharge = -5/4    # 5 kW converted to kWh per interval
    battery_charge = 5/4        # 5 Kw converted to  kWh per interval
    battery_init_soc = 0.0      # ratio from 0 to 1

    # definign one day worth of stuff at 15 minute intervals

    # tariffs in dollars per kwh
    import_tariff_array = np.array(([0.1] * 28 + [0.3] * 8 + [0.2] * 32 + [0.3] * 16 + [0.1] * 12))
    export_tariff_array = np.array(([0.1] * 96))

    # laod profile in kWh per time period
    load_profile = np.array(
        [2.13, 2.09, 2.3, 2.11, 2.2, 2.23, 2.2, 2.15, 2.02, 2.19, 2.19, 2.19, 2.12, 2.15, 2.25, 2.12, 2.21, 2.16,
         2.26, 2.13, 2.08, 2.15, 2.42, 2.02, 2.3, 2.26, 2.35, 2.55, 3.23, 2.98, 3.49, 3.5, 3.12, 3.52, 3.94, 3.55,
         3.99, 3.71, 3.38, 3.76, 3.71, 3.78, 3.29, 3.65, 3.61, 3.75, 3.38, 3.66, 3.56, 3.69, 3.3, 3.61, 3.71, 3.82,
         3.17, 3.69, 3.74, 3.86, 3.57, 3.55, 3.75, 3.6, 3.67, 3.48, 3.51, 3.46, 3.19, 3.38, 3.19, 3.38, 3.04, 3.12,
         2.91, 3.11, 3.13, 2.77, 2.24, 2.54, 2.24, 2.24, 2.09, 2.33, 2.17, 2.16, 1.97, 2.16, 2.21, 2.18, 2.01, 2.16,
         2.19, 2.11, 2.17, 2.13, 2.05, 2.19])/4



    # extending to get the required number of days
    import_tariff_array = np.hstack([import_tariff_array]*num_days)
    export_tariff_array = np.hstack([export_tariff_array]*num_days)
    load_profile = np.hstack([load_profile]*num_days)

    # adding a little randomness to the load
    np.random.seed(seed=15)
    load_profile *= (0.8+0.2*np.random.random(import_tariff_array.size))

    ## standard formulation splitting charging into postiive and negative
    num_times = len(load_profile)
    model = pyo.ConcreteModel()
    model.T = range(num_times)
    model.x = pyo.Var(model.T, domain=pyo.Reals, bounds=(battery_discharge, battery_charge))    # battery charge/discharge
    model.pos = pyo.Var(model.T, domain=pyo.Reals, bounds=(0, None))                # positive aggregate load
    model.neg = pyo.Var(model.T, domain=pyo.Reals, bounds=(None, 0))                # negative aggregate load
    model.b = pyo.Var(model.T, domain=pyo.Binary)

    model.obj = pyo.Objective(expr=sum(import_tariff_array[t]*model.pos[t]+export_tariff_array[t]*model.neg[t] for t in model.T),
                              sense=pyo.minimize)

    # the positive negative breakdown constraint
    model.pos_con = pyo.ConstraintList()
    model.neg_con = pyo.ConstraintList()
    model.agg_con = pyo.ConstraintList()
    for t in model.T:
        model.pos_con.add(model.pos[t] <= model.b[t] * 1000)
        model.neg_con.add(model.neg[t] >= (model.b[t]-1)*1000)
        model.agg_con.add(model.pos[t] + model.neg[t] == load_profile[t] + model.x[t])

    # battery max and min capacity constraints
    model.soc_min = pyo.ConstraintList()
    model.soc_max = pyo.ConstraintList()
    for t in range(1, num_times+1):
        model.soc_min.add(battery_cap*battery_init_soc + sum(model.x[i] for i in range(t)) >= 0.)
        model.soc_max.add(battery_cap*battery_init_soc + sum(model.x[i] for i in range(t)) <= battery_cap)

    opt = SolverFactory('cplex')
    t1 = time.time()
    results = opt.solve(model)
    t2 = time.time()
    solve_times_1.append(t2-t1)
    # r = results['Problem'][0]
    # print('time to solve with first formulation was ', t2-t1, 's')
    # print('Achieved cost was ', r['Lower bound'])


    ## solving with second formulation
    assert all(import_tariff_array >= export_tariff_array), 'Import tariff must always be greater or equal to export tariff for second formulation'

    model2 = pyo.ConcreteModel()
    model2.T = range(num_times)
    model2.x = pyo.Var(model2.T, domain=pyo.Reals, bounds=(battery_discharge, battery_charge))    # battery charge/discharge
    model2.a = pyo.Var(model2.T, domain=pyo.Reals, initialize=100)    # battery charge/discharge

    model2.obj = pyo.Objective(expr=sum(model2.a[t] for t in model2.T),
                              sense=pyo.minimize)

    model2.a_imp_con = pyo.ConstraintList()
    model2.a_exp_con = pyo.ConstraintList()
    for t in model2.T:
        model2.a_imp_con.add(model2.a[t] >= import_tariff_array[t] * (load_profile[t] + model2.x[t]))
        model2.a_exp_con.add(model2.a[t] >= export_tariff_array[t] * (load_profile[t] + model2.x[t]))

    model2.soc_min = pyo.ConstraintList()
    model2.soc_max = pyo.ConstraintList()
    for t in range(1, num_times+1):
        model2.soc_min.add(battery_cap*battery_init_soc + sum(model2.x[i] for i in range(t)) >= 0.)
        model2.soc_max.add(battery_cap*battery_init_soc + sum(model2.x[i] for i in range(t)) <= battery_cap)

    opt = SolverFactory('cplex')
    t1 = time.time()
    results = opt.solve(model2)
    t2 = time.time()

    solve_times_2.append(t2-t1)
    # r = results['Problem'][0]
    # print('time to solve with second formulation was ', t2-t1, 's')
    # print('Achieved cost was ', r['Lower bound'])


plt.plot(np.array(list_num_days) * 4*24, solve_times_1, label="MILP")
plt.plot(np.array(list_num_days) * 4*24, solve_times_2, label="LP")
plt.xlabel("Data length")
plt.ylabel("Solve time (s)")
plt.title("Formulation comparison")
plt.legend()
plt.show()