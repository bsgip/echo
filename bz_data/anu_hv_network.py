""" Manually defined HV network for Acton campus"""

feeder_list = ['Avenue', 'Central', 'South', 'North', 'Science', 'West', 'Garran']

feeder_dict = {'Avenue':
                   {'AVE00739': ['B31', 'B32'],
                    'AVE00776': ['B15 ', 'B16', 'B17'],
                    'AVE01853': ['B20', 'B22', 'B26'],
                    'AVE02972': ['B18', 'B19'],
                    'AVE05842': ['B108', 'B19A', 'B90'],
                    'AVE11250': ['B145']
                    },
               'Central':
                   {'CEN00755': ['B32', 'B3H'],
                    'CEN01241': ['B10T1', 'B10', 'B3K', 'B3L', 'B5', 'B6', 'B7', 'B8', 'B92'],
                    'CEN01744': ['B46F', 'B46'],
                    'CEN02497': ['B76'],
                    'CEN03488': ['B40', 'B49A', 'B49C'],
                    'CEN04115': ['B28', 'B73', 'B75A', 'B75D', 'B75E', 'B75E', 'B75F', 'B75G', 'B75T1', 'B75T2'],
                    'CEN04737': ['B128', 'B1B', 'B64A', 'B64B', 'B64', 'B65', 'B67A', 'B67B', 'B67C', 'B67', 'B68',
                                 'B69', 'B70', 'B71T', 'B72', 'B78', 'B80', 'B81', 'B93'],
                    'CEN06163': ['B015D'],
                    'CEN08007': ['B120', 'B126', 'B77A', 'B77'],
                    'CEN08500': ['B46C', 'B46H', 'B46J', 'B46N', 'B46Q', 'B46R', 'B46S', 'B46'],
                    'CEN09496': ['B132A', 'B132', 'B37'],
                    'CEN09634': ['B134'],
                    'CEN09635': ['B134'],
                    'CEN09655': ['B122', 'B135', 'B43', 'B45'],
                    'CEN09746': ['B136', 'B137', 'B138', 'B42', 'B44'],
                    'CEN09747': ['B42A'],
                    'CEN09826': ['B188'],
                    'CEN11132': ['B162'],
                    'CEN11134': ['B163']
                    },
               'South': [],
               'North': [],
               'Science': [],
               'West': [],
               'Garran':
                   {'GAR01348': ['B125', 'B142', 'B61', 'B62', 'B63T1', 'B63']
                    }
               }

network_dict = {
    'components': {
        'BSP1': {
            'id': 'bulk_grid',
            'type': 'flex',
            'units': 'kW',
            'ports': feeder_list
        },
        'Avenue': {
            'id': 'bulk_grid',
            'type': 'feeder',
            'units': 'kW',
            'ports': ['B32', 'B31', ...]
        },
        'Central': {
            'id': 'bulk_grid',
            'type': 'feeder',
            'units': 'kW',
            'ports': []
        },
        'North': {
            'id': 'bulk_grid',
            'type': 'feeder',
            'units': 'kW',
            'ports': []
        },
        'South': {
            'id': 'bulk_grid',
            'type': 'feeder',
            'units': 'kW',
            'ports': []
        },
        'Science': {
            'id': 'bulk_grid',
            'type': 'feeder',
            'units': 'kW',
            'ports': []
        },
        'Garran': {
            'id': 'bulk_grid',
            'type': 'feeder',
            'units': 'kW',
            'ports': []
        },
        'West': {
            'id': 'bulk_grid',
            'type': 'feeder',
            'units': 'kW',
            'ports': []
        },
    },
    'edges': {
        'edge_1': {'nodes': ('bulk_grid', 'elec_cp'),
                   'ports': ('downstream', 'upstream'),
                   'res': 'elec'},
    }
}
