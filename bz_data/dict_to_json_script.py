import json
from anu_hv_network import feeder_dict

with open('acton_network.json', 'w+') as f:
    json_obj = json.dumps(feeder_dict, indent=2)
    f.write(json_obj)

