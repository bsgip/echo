from collections import defaultdict

def check_port_names_unique(echo_system):
    all_ports = [_p for _node in echo_system.node_obj.values() for _p in _node.ports.values()]
    port_names = [_p.port_name for _p in all_ports]
    port_ids = [_p.uid for _p in all_ports]
    if any([port_names.count(_name)!=1 for _name in port_names]):
        print(f'Port names are not unique')
        print([_name for _name in port_names if port_names.count(_name)!=1])
    if any([port_ids.count(_id)!=1 for _id in port_ids]):
        print(f'Port ids are not unique')
        print([_id for _id in port_ids if port_ids.count(_id)!=1])


def check_all_ports_connected(echo_system):
    pass


def ports_dict(echo_system):
    ports_dict = defaultdict(dict)
    ports_dict_uid = defaultdict(dict)
    for n in echo_system.node_obj.values():
        for k, v in n.ports.items():
            ports_dict[v.port_name]['node'] = n.node_name
            ports_dict[v.port_name]['port_key'] = k
            ports_dict[v.uid]['node'] = n.node_name
            ports_dict[v.uid]['port_key'] = k
    return ports_dict

