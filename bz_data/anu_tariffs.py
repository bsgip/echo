from echo.configuration import *
# Elec tariffs - 2022 bill
elec_tariffs = {}
# Retail energy tariffs ($/kWh)
elec_tariffs['retail_energy_offpeak'] = {'rate': 0.053320,
                                         'type': TariffType.import_tariff}
elec_tariffs['retail_energy_shoulder'] = {'rate': 0.090416,
                                          'type': TariffType.import_tariff}
elec_tariffs['retail_energy_business'] = {'rate': 0.090416,
                                          'type': TariffType.import_tariff}
# Network energy tariffs ($/kWh)
elec_tariffs['network_offpeak'] = {'rate': 0.032460,
                                   'type': TariffType.import_tariff}
elec_tariffs['network_business'] = {'rate': 0.091300,
                                    'type': TariffType.import_tariff}
elec_tariffs['network_shoulder'] = {'rate': 0.054,
                                    'type': TariffType.import_tariff}
# supply charge ($/days)
elec_tariffs['supply_charge'] = {'rate': 21.864,
                                 'type': TariffType.time}
# HV demand charges ($/kVA/day) #todo we don't have kVA data - could assume a constant pf
elec_tariffs['HV_capacity_charge'] = {'rate': 0.17420}
elec_tariffs['HV_demand_charge'] = {'rate': 0.17420}
# Metering charges ($/day)
elec_tariffs['metering_charge'] = {'rate': 2.19180,
                                   'type': TariffType.time,
                                   'reset': Resets.daily}
# Market charges ($/kWh)
elec_tariffs['ancillary_services_charges'] = {'rate': 0.000414}
elec_tariffs['pool_fees'] = {'rate': 0.000767}
# RET ($/kWh)
elec_tariffs['LRET'] = {'rate': 0.003078,
                        'type': TariffType.import_tariff}
elec_tariffs['SRES'] = {'rate': 0.011232,
                        'type': TariffType.import_tariff}
# Other
elec_tariffs['energy_efficiency_scheme'] = {'rate': 0.003860,
                                            'type': TariffType.import_tariff}

# Gas tariffs
# STTM = short term trading market
gas_tariffs = {}
# Gas ($/GJ)
gas_tariffs['gas_charge'] = {'rate': 12.0}
# Network charges ($/day
gas_tariffs['demand_capacity_charge'] = {'rate': 828.11}
gas_tariffs['standing_charge'] = {'rate': 447.29}

gas_tariffs['epg_charge'] = {'rate': 3100.40} #?
# Market charges
gas_tariffs['sttm_activity_fee'] = {'rate': 0.03762}

# Elec market prices?




