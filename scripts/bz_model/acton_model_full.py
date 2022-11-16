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
from read_datafiles import gas_supply_points_dict, bld_to_model, electrical_feeders, bl_substations, bld_not_included, substations_bl
from bz_model_constants import *
from custom_classes import MultiCommodityTellegenNodeManual, MultiCommodityTellegenNode
from graph_plotting_utils import *
from tariffs_and_costs import *
from collections import defaultdict



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