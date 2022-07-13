d = {
    "name": "my network",
    "components": {
        "grid": {
            "id": "grid",
            "type": "flex_with_emissions",
            "ports": [
                "downstream",
                "co2"
            ],
            "parameters": {
                "emitting_port": "downstream",
                "carbon_port": "co2",
                "emissions_factor": 60
            }
        },
        "emissions": {
            "id": "emissions",
            "type": "carbon_agg",
            "ports": [
                "grid"
            ]
        },
        "cp": {
            "id": "cp",
            "type": "elec_tellegen",
            "ports": [
                "upstream",
                "load",
                "inv",
                "ev"
            ]
        },
        "inverter": {
            "id": "inverter",
            "type": "inverter",
            "ports": [
                "cp",
                "bess",
                "pv"
            ],
            "parameters": {
                "ac_port_name": "cp",
                "dc_port_names": [
                    "bess",
                    "pv"
                ]
            }
        },
        "battery": {
            "id": "battery",
            "type": "battery",
            "ports": [
                "bess"
            ],
            "parameters": {
                "max_capacity": 15.0,
                "depth_of_discharge_limit": 0,
                "charging_power_limit": 1.25,
                "discharging_power_limit": -1.25,
                "charging_efficiency": 1.0,
                "discharging_efficiency": 1.0,
                "initial_state_of_charge": 0
            }
        },
        "solar": {
            "id": "solar",
            "type": "solar",
            "ports": [
                "pv"
            ],
            "parameters": {
                "curtailable": True
            },
            "data": "solar"
        },
        "load": {
            "id": "load",
            "type": "load",
            "ports": [
                "load"
            ],
            "data": "load"
        },
        "ev": {
            "id": "ev",
            "type": "ev",
            "ports": [
                "ev_cp"
            ],
            "parameters": {
                "available": "ev_available",
                "usage": [
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.5,
                    0.5,
                    0.5,
                    0.5,
                    0.5,
                    0.5,
                    0.5,
                    0.5,
                    0.5,
                    0.5,
                    0.5,
                    0.5,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0
                ],
                "max_capacity": 40.0,
                "depth_of_discharge_limit": 0,
                "charging_power_limit": 10.0,
                "discharging_power_limit": -10,
                "charging_efficiency": 1,
                "discharging_efficiency": 1,
                "initial_state_of_charge": 0.0,
                "charge_mode": "V2G",
                "interval_duration": 60,
                "tod_charging": False
            }
        }
    },
    "edges": {
        "grid_cp": {
            "nodes": [
                "grid",
                "cp"
            ],
            "ports": [
                "downstream",
                "upstream"
            ],
            "resource": 1
        },
        "cp_load": {
            "nodes": [
                "cp",
                "load"
            ],
            "ports": [
                "load",
                "load"
            ],
            "resource": 1
        },
        "cp_inverter": {
            "nodes": [
                "cp",
                "inverter"
            ],
            "ports": [
                "inv",
                "cp"
            ],
            "resource": 1
        },
        "inverter_battery": {
            "nodes": [
                "inverter",
                "battery"
            ],
            "ports": [
                "bess",
                "bess"
            ],
            "resource": 1
        },
        "inverter_solar": {
            "nodes": [
                "inverter",
                "solar"
            ],
            "ports": [
                "pv",
                "pv"
            ],
            "resource": 1
        },
        "cp_ev": {
            "nodes": [
                "cp",
                "ev"
            ],
            "ports": [
                "ev",
                "ev_cp"
            ],
            "resource": 1
        },
        "grid_emissions": {
            "nodes": [
                "grid",
                "emissions"
            ],
            "ports": [
                "co2",
                "grid"
            ],
            "resource": 2
        }
    },
    "objectives": {
        "import_cost": {
            "type": "import tariff",
            "name": "import_cost",
            "component": {
                "node": "cp",
                "port": "upstream"
            },
            "prices": [
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                2,
                2,
                2,
                2,
                2,
                2,
                2,
                2,
                2,
                2,
                2,
                2,
                2,
                2,
                2,
                2,
                2,
                2,
                2,
                2,
                2,
                2,
                2,
                2
            ]
        },
        "carbon_cost": {
            "type": "import tariff",
            "name": "carbon_cost",
            "component": {
                "node": "emissions",
                "port": "grid"
            },
            "prices": [
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0
            ]
        },
        "export_cost": {
            "type": "export tariff",
            "name": "export_cost",
            "component": {
                "node": "cp",
                "port": "upstream"
            },
            "prices": [
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                0.1,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3
            ]
        },
        "import_demand_tariff": {
            "type": "import demand tariff",
            "name": "import_demand_tariff",
            "component": {
                "node": "cp",
                "port": "upstream"
            },
            "charges": [
                {
                    "name": "shoulder",
                    "rate": 0.0,
                    "window": [
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1
                    ]
                },
                {
                    "name": "peak",
                    "rate": 0.0,
                    "window": [
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0
                    ]
                }
            ]
        }
    }
}

from echo.echo_builder import Network

n = Network(**d)

