import echo.objectives as obj


def convert_objective_to_echo_objective(em, node_name_dict: dict, objective_dict: dict, verbose: bool = True):
    """ Converts all the objectives defined in an objective set to echo objectives,
    and returns an echo objective set. """

    if verbose:
        print('Converting objectives to echo objectives')
    objective_list = []
    for obj_name, obj_dict in objective_dict.items():
        if obj_dict['type'] == 'import_tariff':
            new_obj = create_import_tariff(obj_dict, node_name_dict, em)
            objective_list.append(new_obj)
        elif (obj_dict['type'] == 'import_demand_tariff') or (obj_dict['type'] == 'export_demand_tariff'):
            new_obj = create_demand_tariff(obj_dict, node_name_dict, em)
            objective_list.append(new_obj)
        elif obj_dict['type'] == 'throughput':
            new_obj = create_throughput_tariff(obj_dict, node_name_dict, em)
            objective_list.append(new_obj)
        elif (obj_dict['type'] == 'peak_pos_power') or (obj_dict['type'] == 'peak_neg_power'):
            new_obj = create_peak_power_objective(obj_dict, node_name_dict, em)
            objective_list.append(new_obj)
        elif obj_dict['type'] == 'quadratic':
            new_obj = create_quadratic_objective(obj_dict, node_name_dict, em)
            objective_list.append(new_obj)
        else:
            ValueError('Objective not recognised')

    output = obj.ObjectiveSet(objective_list=objective_list)
    return output


def create_import_tariff(tariff_dict, node_name_dict, em):
    """ Creates an echo import tariff from a tariff dictionary"""
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em)
    t = obj.ImportTariff(component=component_obj, tariff_array=tariff_dict['prices'])
    return t


def create_export_tariff(tariff_dict, node_name_dict, em):
    """ Creates an echo export tariff from a tariff dictionary"""
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em)
    t = obj.ExportTariff(component=component_obj, tariff_array=tariff_dict['prices'])
    return t


def create_demand_tariff(tariff_dict, node_name_dict, em):
    """ Creates an echo demand tariff from a tariff dictionary"""
    echo_charge_list = []
    charges = tariff_dict['charges']  # list of charge dicts
    for c in charges:
        rate = c['rate']
        window = c['window']
        if 'min_demand' in c:
            min_demand = c['min_demand']
        else:
            min_demand = 0
        # todo allow demand tariffs to be specific with start/end times
        c = obj.DemandCharge(rate=rate, min_demand=min_demand, window_array=window)  # Create demand charge
        echo_charge_list.append(c)

    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em)
    import_demand = True if 'import' in tariff_dict['type'] else False
    export_demand = False if 'import' in tariff_dict['type'] else True
    demand_tariff = obj.DemandTariffObjective(component=component_obj,
                                              demand_charges=echo_charge_list,
                                              export_demand=export_demand,
                                              import_demand=import_demand)
    return demand_tariff


def create_throughput_tariff(tariff_dict, node_name_dict, em):
    """ Creates an echo throughput tariff from a tariff dictionary"""
    # todo test this
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em)
    t = obj.ThroughputCost(component=component_obj, rate=tariff_dict['rate'])
    return t


def create_peak_power_objective(tariff_dict, node_name_dict, em):
    """ Creates an echo peak power objective from an objective dictionary"""
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em)
    if 'pos' in tariff_dict['type']:
        t = obj.PeakPositivePower(component=component_obj)
    else:
        t = obj.PeakNegativePower(component=component_obj)
    return t


def create_quadratic_objective(tariff_dict, node_name_dict, em):
    """ Creates an echo quadratic objective from an objective dictionary"""
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em)
    t = obj.QuadraticPower(component=component_obj)
    return t


def get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em):
    """ Retrieves an objective component defined in an objective dict from an echo model and returns it."""
    target_node = tariff_dict['component']['node']
    target_port = tariff_dict['component']['port']
    assert target_node in node_name_dict.keys(), f"tariff component {tariff_dict['component']} does not correspond to a defined node/port."
    node_obj = em.node_obj[node_name_dict[target_node]]
    component_obj = node_obj.ports[target_port]
    return component_obj
