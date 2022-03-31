class ConfigurationError(Exception):

    def __init__(self):
        super(self.__init__(), ConfigurationError)


class EnergyStorage(object):

    def __init__(self,
                 max_capacity,
                 depth_of_discharge_limit,
                 charging_power_limit,
                 discharging_power_limit,
                 charging_efficiency,
                 discharging_efficiency,
                 throughput_cost,
                 initial_state_of_charge=0
                 ):
        # Energy Storage Characteristics
        self.max_capacity = max_capacity
        self.depth_of_discharge_limit = depth_of_discharge_limit
        # DC Power Characteristics
        self.charging_power_limit = charging_power_limit
        self.discharging_power_limit = discharging_power_limit
        self.charging_efficiency = charging_efficiency
        self.discharging_efficiency = discharging_efficiency
        # Derived Values
        self.capacity = self.calc_capacity()
        # Throughput Cost
        # ToDo - Should this be related to the Levelised cost of energy (LCOE)
        self.throughput_cost = throughput_cost
        # Initial state of charge
        self.initial_state_of_charge = initial_state_of_charge

    def calc_capacity(self):
        capacity = self.max_capacity
        if 0 <= self.depth_of_discharge_limit <= 1:
            # Assume we have a decimal representation of the dod limit
            capacity *= (1 - self.depth_of_discharge_limit)
        elif 1 < self.depth_of_discharge_limit <= 100:
            # Assume we have a percentage representation of the dod limit
            capacity *= (1 - self.depth_of_discharge_limit / 100.0)
        else:
            raise ConfigurationError('The DoD limit should be between 0 - 100')

        return capacity



class Inverter(object):

    def __init__(self,
                 charging_power_limit,
                 discharging_power_limit,
                 charging_efficiency,
                 discharging_efficiency,
                 charging_reactive_power_limit,
                 discharging_reactive_power_limit,
                 reactive_charging_efficiency,
                 reactive_discharging_efficiency
                 ):
        # AC Real Power Characteristics
        self.charging_power_limit = charging_power_limit
        self.discharging_power_limit = discharging_power_limit
        self.charging_efficiency = charging_efficiency
        self.discharging_efficiency = discharging_efficiency
        # AC Reactive Power Characteristics
        self.charging_reactive_power_limit = charging_reactive_power_limit
        self.discharging_reactive_power_limit = discharging_reactive_power_limit
        self.reactive_charging_efficiency = reactive_charging_efficiency
        self.reactive_discharging_efficiency = reactive_discharging_efficiency


class Generation(object):
    #ToDo Fix the default value here
    def __init__(self, peak_rating=0):
        # DC Power Characteristics
        self.peak_rating = peak_rating

    def add_generation_profile(self, generation):
        self.generation = generation

class Demand(object):

    def __init__(self):
        pass

    def add_demand_profile(self, demand):
        self.demand = demand


class Tariff(object):

    def __init__(self):
        pass

    def add_tariff_profile_import(self, tariff):
        self.import_tariff = tariff

    def add_tariff_profile_export(self, tariff):
        self.export_tariff = tariff

class LocalTariff(object):

    def __init__(self):
        pass

    def add_local_energy_tariff_profile_import(self, tariff):
        self.le_import_tariff = tariff

    def add_local_energy_tariff_profile_export(self, tariff):
        self.le_export_tariff = tariff

    def add_local_transport_tariff_profile_import(self, tariff):
        self.lt_import_tariff = tariff

    def add_local_transport_tariff_profile_export(self, tariff):
        self.lt_export_tariff = tariff

    def add_remote_energy_tariff_profile_import(self, tariff):
        self.re_import_tariff = tariff

    def add_remote_energy_tariff_profile_export(self, tariff):
        self.re_export_tariff = tariff

    def add_remote_transport_tariff_profile_import(self, tariff):
        self.rt_import_tariff = tariff

    def add_remote_transport_tariff_profile_export(self, tariff):
        self.rt_export_tariff = tariff


class DispatchRequest(object):

    def __init__(self):
        pass

    def add_dispatch_request_linear_ramp(self, request):
        self.linear_ramp = request

    def add_dispatch_request_step(self, request):
        self.step = request

    def add_dispatch_request_hold(self, request):
        self.hold = request


class EnergySystem(object):
    
    def __init__(self, is_hybrid=False):
        self.energy_storage = None
        self.inverter = None
        self.generation = None
        self.is_hybrid = is_hybrid
        
    def add_energy_storage(self, energy_storage):
        self.energy_storage = energy_storage
        
    def add_inverter(self, inverter):
        self.inverter = inverter

    def add_generation(self, generation):
        self.generation = generation

    def add_demand(self, demand):
        self.demand = demand

    def add_tariff(self, tariff):
        self.tariff = tariff

    def add_local_tariff(self, tariff):
        self.local_tariff = tariff

    def add_dispatch(self, dispatch):
        self.dispatch = dispatch