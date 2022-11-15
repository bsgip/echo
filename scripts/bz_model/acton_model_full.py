import pandas as pd
import numpy as np
from echo import objectives
import echo.echo_models as models
import echo.echo_thermal_models as thermal_models
import echo.echo_builder as builder
import echo.configuration as config
import echo.echo_optimiser as optimiser
import echo.utils as utils
import pyomo.environ as en


########### local imports ###############
from read_datafiles import bl_with_meters, kambri_central, central_plant, source_df, extra_gas_supply
from bz_model_constants import *
from custom_classes import MultiCommodityTellegenNodeManual, MultiCommodityTellegenNode
from graph_plotting_utils import *
from tariffs_and_costs import *
from collections import defaultdict


bl_to_model = set(bl_with_meters[bl_with_meters.include_in_model.isin(['Y'])].ID)

gas_supply_points_dict= dict()
for gas_meter, group in bl_with_meters[~bl_with_meters.gas_meter.isnull()&bl_with_meters.include_in_model.isin(['Y'])].groupby('gas_meter'):
    gas_supply_points_dict[gas_meter]=list(group.ID)


electrical_feeders= defaultdict()

for _f, group in bl_with_meters[~bl_with_meters.Feeder.isnull()].groupby('Feeder'):
    feeder_subs = []
    unique_subs = [_s for _s in group[~group.substation.isnull()].substation.unique() if _s!='1225,1744']
    for _s in unique_subs:
        feeder_subs.extend(str(_s).split(','))
    electrical_feeders[_f]=[sub_id for sub_id in unique_subs]


electrical_substations=defaultdict()

for _bl, group in bl_with_meters[bl_with_meters.include_in_model.isin(['Y'])].groupby('ID'):
    bl_subs = []
    feeder_id = list(group.Feeder.unique())[0]
    unique_subs = list(group[~group.substation.isnull()].substation.unique())
    if len(unique_subs)==0:
        continue
    for _s in unique_subs:
        bl_subs.extend(str(_s).split(','))
    print(f'bl {_bl} fed from subs {bl_subs}')












## Initialise system
system = models.OptimisationGraph()


## Add Bulk Gas grid , Gas distribution Node and carbon aggregation nodes
gas_grid = models.FlexNodeWithEmissions(node_name='GasGrid',
                                        emitting_port='gas_grid',
                                        emitting_port_units=config.Units.JPS,
                                        carbon_port='bulk_gas_emissions',
                                        emissions_factor= emission_factor)

carbon_aggregation = models.CarbonAggregation(node_name='BulkEmissions',
                                              ports={'from_bulk_gas_grid': models.CarbonPort()})

## Connect emitting port of Gas grid to Carbon aggregation


electrical_grid = models.FlexElectricalNode(node_name = 'ElectricGrid', port_name='to_avenue')