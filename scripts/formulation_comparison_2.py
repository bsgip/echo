
"""
Compares mixed integer formulation and the LP formulation

Considers a behind the meter optimisation where the import and export tariffs are different

Also considers battery charge and discharge efficiency. This means that battery power as well as grid power
have a piecewise linear function acting on them

Both formulatiosn should give the same result for the optimised cost, or very very close to (otherwise something is
going wrong)

Change num_days to get an idea of how the different approaches scale with increasing data length. For very small
problems they will be similar

The difference in time to solve is even more noticeable now that there are two variables that need to be split
for the Mixed integer approach.

"""

# some imports
import pandas as pd
import pyomo.environ as pyo
import numpy as np
import matplotlib.pyplot as plt
from pyomo.opt import SolverFactory
import time

# some options
num_days = 20

# setting up the problem
# problem is set up considering 15 minute time intervals and then all units are given in kWh

battery_cap = 10            # max battery capacity kWh
battery_discharge = -5/4    # 5 kW converted to kWh per interval
battery_charge = 5/4        # 5 Kw converted to  kWh per interval
battery_init_soc = 0.0      # ratio from 0 to 1
eta_charge = 0.9            # charging efficiency
eta_discharge = 0.85        # discharging efficiency

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
load_profile *= (0.8+0.2*np.random.random(import_tariff_array.size))


"""
This is the 'standard' mixed integer formulation where the positive and negative power flows are 
split using the big M constraint approach

both the grid power and the battery power are split since now there is the piecewise cost function and also 
the piecewise function for amount of charge done
"""


num_times = len(import_tariff_array)
model = pyo.ConcreteModel()
model.T = range(num_times)
model.pos_agg = pyo.Var(model.T, domain=pyo.Reals, bounds=(0, None))
model.neg_agg = pyo.Var(model.T, domain=pyo.Reals, bounds=(None, 0))
model.pos = pyo.Var(model.T, domain=pyo.Reals, bounds=(0, battery_charge))                # positive kwh to battery
model.neg = pyo.Var(model.T, domain=pyo.Reals, bounds=(battery_discharge, 0))                # negative kwh from battery
model.b = pyo.Var(model.T, domain=pyo.Binary)
model.b_agg = pyo.Var(model.T, domain=pyo.Binary)

model.obj = pyo.Objective(expr=sum(import_tariff_array[t]*model.pos_agg[t]+export_tariff_array[t]*model.neg_agg[t] for t in model.T),
                          sense=pyo.minimize)

# the positive negative breakdown constraint
model.pos_con = pyo.ConstraintList()
model.neg_con = pyo.ConstraintList()
model.pos_agg_con = pyo.ConstraintList()
model.neg_agg_con = pyo.ConstraintList()
model.agg_con = pyo.ConstraintList()
for t in model.T:
    model.pos_con.add(model.pos[t] <= model.b[t] * 1000)
    model.neg_con.add(model.neg[t] >= (model.b[t]-1)*1000)
    model.pos_agg_con.add(model.pos_agg[t] <= model.b_agg[t] * 1000)
    model.neg_agg_con.add(model.neg_agg[t] >= (model.b_agg[t]-1)*1000)
    model.agg_con.add(model.pos_agg[t] + model.neg_agg[t] == load_profile[t] + model.pos[t]+model.neg[t])

# battery max and min capacity constraints
model.soc_min = pyo.ConstraintList()
model.soc_max = pyo.ConstraintList()
for t in range(1, num_times+1):
    model.soc_min.add(battery_cap*battery_init_soc + sum(eta_charge*model.pos[i]+model.neg[i]/eta_discharge for i in range(t)) >= 0.)
    model.soc_max.add(battery_cap*battery_init_soc + sum(eta_charge*model.pos[i]+model.neg[i]/eta_discharge for i in range(t)) <= battery_cap)

opt = SolverFactory('cplex')
t1 = time.time()
results = opt.solve(model)
t2 = time.time()
r = results['Problem'][0]
print('time to solve with first formulation was ', t2-t1, 's')
print('Achieved cost was ', r['Lower bound'])

pos_array = np.zeros((num_times,))
neg_array = np.zeros((num_times,))
pos_agg_array = np.zeros((num_times,))
neg_agg_array = np.zeros((num_times,))
for t in model.T:
    pos_array[t] = model.pos[t].value
    neg_array[t] = model.neg[t].value
    pos_agg_array[t] = model.pos_agg[t].value
    neg_agg_array[t] = model.neg_agg[t].value

assert any((pos_array>0) + (neg_array<0)), 'positive and negative was not split correctly'

# plt.plot(neg_array[:100])
# plt.plot(pos_array[:100])
# plt.show()

""" 
Now the LP reformulation where an auxilliary variable is introduced as the cost and 
constrained below by the original cost function.

A second auxilliary variable is introduced to represent the change in battery charge. 
This is then upper bounded by the piecewise function made up of applying the charge and discharge efficiency 
to the battery power
"""
assert all(import_tariff_array >= export_tariff_array), 'Import tariff must always be greater or equal to export tariff for second formulation'
assert 1/eta_discharge >= eta_charge, '1/eta_discharge must be greater than eta_charge'

model2 = pyo.ConcreteModel()
model2.T = range(num_times)
model2.x = pyo.Var(model2.T, domain=pyo.Reals, bounds=(battery_discharge, battery_charge))    # battery charge/discharge
model2.a = pyo.Var(model2.T, domain=pyo.Reals, initialize=100)    # battery charge/discharge from grid
model2.v  = pyo.Var(model2.T, domain=pyo.Reals, initialize=-100)    # how much the battery actually chargers or dischargers


model2.obj = pyo.Objective(expr=sum(model2.a[t] for t in model2.T),
                          sense=pyo.minimize)

# model2.obj = pyo.Objective(expr=sum(-1e-6*model2.v[t] for t in model2.T),
#                           sense=pyo.minimize)


model2.a_imp_con = pyo.ConstraintList()
model2.a_exp_con = pyo.ConstraintList()
model2.v_discharge_con = pyo.ConstraintList()
model2.v_charge_con = pyo.ConstraintList()
for t in model2.T:
    model2.a_imp_con.add(model2.a[t] >= import_tariff_array[t] * (load_profile[t] + model2.x[t]))
    model2.a_exp_con.add(model2.a[t] >= export_tariff_array[t] * (load_profile[t] + model2.x[t]))
    model2.v_charge_con.add(model2.v[t] <= eta_charge * model2.x[t])
    model2.v_discharge_con.add(model2.v[t] <= model2.x[t]/eta_discharge)

model2.soc_min = pyo.ConstraintList()
model2.soc_max = pyo.ConstraintList()
for t in range(1, num_times+1):
    model2.soc_min.add(battery_cap*battery_init_soc + sum(model2.v[i] for i in range(t)) >= 0.)
    model2.soc_max.add(battery_cap*battery_init_soc + sum(model2.v[i] for i in range(t)) <= battery_cap)

opt = SolverFactory('cplex')
t1 = time.time()
results = opt.solve(model2)
t2 = time.time()
r = results['Problem'][0]
print('time to solve with second formulation was ', t2-t1, 's')
print('Achieved cost was ', r['Lower bound'])

# some checks, we want to check that v_t actually dose represent x_t multiplied by the charge or discharge efficiency
v_array = np.zeros((num_times,))
x_array = np.zeros((num_times,))
for t in model.T:
    v_array[t] = model2.v[t].value
    x_array[t] = model2.x[t].value

inds = x_array <=0
charge = np.zeros(x_array.shape)
charge[inds] = x_array[inds]/eta_discharge
inds = x_array >0
charge[inds] = eta_charge * x_array[inds]

plt.plot(charge[:100])
plt.plot(v_array[:100])
plt.show()
diff = v_array-charge