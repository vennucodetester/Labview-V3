"""
component_schemas.py

Defines the "DNA" for each component type in the refrigeration system.
Each schema includes:
- properties: Editable attributes (integer, string, enum)
- ports: Fixed connection points with type (in/out) and fluid state
- dynamic_ports: Ports generated based on property values (e.g., circuit count)
- zones: Interactive regions (for sensor drops, etc.)
"""

SCHEMAS = {
    "Compressor": {
        "properties": {
            "capacity": {"type": "integer", "default": 1000},
            "displacement_cm3": {"type": "float", "default": 10.5, "min": 0.1, "max": 100.0},
            "speed_rpm": {"type": "float", "default": 3500.0, "min": 100.0, "max": 10000.0},
            "vol_eff": {"type": "float", "default": 0.85, "min": 0.1, "max": 1.0},
            "isentropic_eff": {"type": "float", "default": 0.72, "min": 0.4, "max": 0.95},
            "circuit_label": {"type": "enum", "default": "None", "options": ["None", "Left", "Center", "Right"]}
        },
        "ports": [
            {"name": "inlet",  "type": "in",     "fluid_state": "gas", "pressure_side": "low",  "position": [0.5, 0]},
            {"name": "outlet", "type": "out",    "fluid_state": "gas", "pressure_side": "high", "position": [0.5, 1]},
            {"name": "SP",     "type": "sensor", "fluid_state": "any", "pressure_side": "low",  "position": [0.1, 0.1]},
            {"name": "DP",     "type": "sensor", "fluid_state": "any", "pressure_side": "high", "position": [0.9, 0.1]},
            {"name": "RPM",    "type": "sensor", "fluid_state": "any", "pressure_side": "any",  "position": [0.1, 0.9]}
        ],
        "zones": [
            {"name": "motor", "rect": [0.3, 0.3, 0.4, 0.4]}
        ]
    },
    
    "Condenser": {
        "properties": {
            "capacity": {"type": "integer", "default": 5000},
            "ua_condenser": {"type": "float", "default": 800.0, "min": 50.0, "max": 10000.0},
            "circuit_label": {"type": "enum", "default": "None", "options": ["None", "Left", "Center", "Right"]},
            "condenser_type": {"type": "enum", "default": "Air Cooled", "options": ["Air Cooled", "Water Cooled"]},
            "flip": {"type": "enum", "default": "No", "options": ["No", "Yes"]},
            "fan_cfm": {"type": "float", "default": 0.0, "min": 0.0, "max": 50000.0},
            "fan_rpm": {"type": "float", "default": 0.0, "min": 0.0, "max": 5000.0}
        },
        "ports": [
            {"name": "inlet", "type": "in", "fluid_state": "gas", "pressure_side": "high", "position": [0.5, 0]},
            {"name": "outlet", "type": "out", "fluid_state": "liquid", "pressure_side": "high", "position": [0.5, 1]}
        ],
        "conditional_ports": {
            "Air Cooled": [],
            "Water Cooled": [
                {"name": "water_in_temp", "type": "sensor", "fluid_state": "any", "pressure_side": "any", "position": [0, 0.7]},
                {"name": "water_out_temp", "type": "sensor", "fluid_state": "any", "pressure_side": "any", "position": [0, 0.3]},
                {"name": "water_flow_gpm", "type": "sensor", "fluid_state": "any", "pressure_side": "any", "position": [1, 0.5]}
            ]
        },
        "zones": [
            {"name": "coil_surface", "rect": [0.2, 0.2, 0.6, 0.6]}
        ]
    },
    
    "Evaporator": {
        "properties": {
            "circuits": {"type": "integer", "default": 1, "min": 1, "max": 12},
            "ua_evaporator": {"type": "float", "default": 600.0, "min": 50.0, "max": 10000.0},
            "port_spacing": {"type": "integer", "default": 20, "min": 10, "max": 50},
            "circuit_label": {"type": "enum", "default": "None", "options": ["None", "Left", "Center", "Right"]},
            "inlet_distributor": {"type": "enum", "default": "No", "options": ["No", "Yes"]},
            "outlet_distributor": {"type": "enum", "default": "No", "options": ["No", "Yes"]},
            "fan_sensor_count": {"type": "integer", "default": 6, "min": 1, "max": 12},
            "air_flow_direction": {
                "type": "enum",
                "default": "Bottom to Top",
                "options": ["Bottom to Top", "Top to Bottom"]
            }
        },
        "ports": [],
        "dynamic_ports": {
            "prefix": "inlet_circuit_",
            "count_property": "circuits",
            "port_details": {"type": "in", "fluid_state": "two-phase", "pressure_side": "low"},
            "position_side": "top"
        },
        "dynamic_ports_2": {
            "prefix": "outlet_circuit_",
            "count_property": "circuits",
            "port_details": {"type": "out", "fluid_state": "gas", "pressure_side": "low"},
            "position_side": "bottom"
        },
        "dynamic_ports_3": {
            "prefix": "sensor_bottom_",
            "count_property": "fan_sensor_count",
            "port_details": {"type": "sensor", "fluid_state": "any", "pressure_side": "any"},
            "position_side": "bottom"
        },
        "zones": [
            {"name": "coil_surface", "rect": [0.2, 0.2, 0.6, 0.6]}
        ]
    },
    
    "TXV": {
        "properties": {
            "capacity": {"type": "integer", "default": 100},
            "superheat_setting": {"type": "integer", "default": 10},
            "cv_txv": {"type": "float", "default": 0.5, "min": 0.01, "max": 5.0},
            "circuit_label": {"type": "enum", "default": "None", "options": ["None", "Left", "Center", "Right"]},
            "expansion_device_type": {"type": "enum", "default": "TXV", "options": ["TXV", "Cap Tube"]}
        },
        "ports": [
            {"name": "inlet", "type": "in", "fluid_state": "liquid", "pressure_side": "high", "position": [0.5, 0]},
            {"name": "outlet", "type": "out", "fluid_state": "two-phase", "pressure_side": "low", "position": [0.5, 1]},
            {"name": "bulb", "type": "sensor", "fluid_state": "any", "pressure_side": "low", "position": [0.5, 0.5]}
        ],
        "zones": []
    },

    "RemoteLineEndpoint": {
        "properties": {
            "label": {"type": "string", "default": "Remote Connection"}
        },
        "ports": [
            {"name": "connection", "type": "in", "fluid_state": "any", "pressure_side": "any", "position": [0.5, 0.5]}
        ],
        "zones": []
    },
    
    "FilterDrier": {
        "properties": {
            "size": {"type": "string", "default": "3/8\""},
            "circuit_label": {"type": "enum", "default": "None", "options": ["None", "Left", "Center", "Right"]}
        },
        "ports": [
            {"name": "inlet", "type": "in", "fluid_state": "any", "pressure_side": "high", "position": [0, 0.5]},
            {"name": "outlet", "type": "out", "fluid_state": "any", "pressure_side": "high", "position": [1, 0.5]}
        ],
        "zones": []
    },
    
    
    "Header": {
        "properties": {
            "circuits": {"type": "integer", "default": 1, "min": 1, "max": 12},
            "port_spacing": {"type": "integer", "default": 20, "min": 10, "max": 50},
            "circuit_label": {"type": "enum", "default": "None", "options": ["None", "Left", "Center", "Right"]}
        },
        "ports": [
            {"name": "outlet", "type": "out", "fluid_state": "two-phase", "pressure_side": "low", "position": [1, 0.5]},
            {"name": "sensor_attach", "type": "sensor_attach", "fluid_state": "any", "pressure_side": "any", "position": [1, 0]}
        ],
        "dynamic_ports": {
            "prefix": "in_",
            "count_property": "circuits",
            "port_details": {"type": "in", "fluid_state": "two-phase", "pressure_side": "low"},
            "position_side": "left"
        },
        "zones": []
    },
    "Distributor": {
        "properties": {
            "circuit_count": {"type": "integer", "default": 1, "min": 1, "max": 12},
            "port_spacing": {"type": "integer", "default": 20, "min": 10, "max": 50},
            "circuit_label": {"type": "enum", "default": "None", "options": ["None", "Left", "Center", "Right"]}
        },
        "ports": [
            {"name": "inlet", "type": "in", "fluid_state": "two-phase", "pressure_side": "low", "position": [0, 0.5]}
        ],
        "dynamic_ports": {
            "prefix": "outlet_",
            "count_property": "circuit_count",
            "port_details": {"type": "out", "fluid_state": "two-phase", "pressure_side": "low"},
            "position_side": "right"
        },
        "zones": []
    },
    
    "Junction": {
        "properties": {
            "inlet_count": {"type": "integer", "default": 2, "min": 1, "max": 12},
            "outlet_count": {"type": "integer", "default": 1, "min": 1, "max": 12},
            "port_spacing": {"type": "integer", "default": 20, "min": 5, "max": 1000},
            "snapped_mode": {"type": "enum", "default": "No", "options": ["No", "Yes"]},
            "circuit_label": {"type": "enum", "default": "None", "options": ["None", "Left", "Center", "Right"]}
        },
        "ports": [],
        "dynamic_ports": {
            "prefix": "inlet_",
            "count_property": "inlet_count",
            "port_details": {"type": "in", "fluid_state": "any", "pressure_side": "any"},
            "position_side": "left"
        },
        "dynamic_ports_2": {
            "prefix": "outlet_",
            "count_property": "outlet_count",
            "port_details": {"type": "out", "fluid_state": "any", "pressure_side": "any"},
            "position_side": "right"
        },
        "zones": []
    },
    
    "TeeJunction": {
        "properties": {},
        "ports": [
            {"name": "inlet_1", "type": "in", "fluid_state": "any", "pressure_side": "any", "position": [0, 0.5]},
            {"name": "inlet_2", "type": "in", "fluid_state": "any", "pressure_side": "any", "position": [0.5, 0]},
            {"name": "outlet", "type": "out", "fluid_state": "any", "pressure_side": "any", "position": [1, 0.5]}
        ],
        "zones": []
    },
    
    "YJunction": {
        "properties": {},
        "ports": [
            {"name": "inlet_1", "type": "in", "fluid_state": "any", "pressure_side": "any", "position": [0, 0.3]},
            {"name": "inlet_2", "type": "in", "fluid_state": "any", "pressure_side": "any", "position": [0, 0.7]},
            {"name": "outlet", "type": "out", "fluid_state": "any", "pressure_side": "any", "position": [1, 0.5]}
        ],
        "zones": []
    },
    
    "Splitter": {
        "properties": {},
        "ports": [
            {"name": "inlet", "type": "in", "fluid_state": "any", "pressure_side": "any", "position": [0, 0.5]},
            {"name": "outlet_1", "type": "out", "fluid_state": "any", "pressure_side": "any", "position": [1, 0.3]},
            {"name": "outlet_2", "type": "out", "fluid_state": "any", "pressure_side": "any", "position": [1, 0.7]}
        ],
        "zones": []
    },
    
    "CrossJunction": {
        "properties": {},
        "ports": [
            {"name": "inlet_1", "type": "in", "fluid_state": "any", "position": [0, 0.5]},
            {"name": "inlet_2", "type": "in", "fluid_state": "any", "position": [0.5, 0]},
            {"name": "outlet_1", "type": "out", "fluid_state": "any", "position": [1, 0.5]},
            {"name": "outlet_2", "type": "out", "fluid_state": "any", "position": [0.5, 1]}
        ],
        "zones": []
    },
    
    "Reducer": {
        "properties": {
            "inlet_size": {"type": "string", "default": "5/8\""},
            "outlet_size": {"type": "string", "default": "3/8\""}
        },
        "ports": [
            {"name": "inlet", "type": "in", "fluid_state": "any", "position": [0, 0.5]},
            {"name": "outlet", "type": "out", "fluid_state": "any", "position": [1, 0.5]}
        ],
        "zones": []
    },
    
    "SensorBulb": {
        "properties": {
            "label": {"type": "string", "default": ""},
            "circuit_label": {"type": "enum", "default": "None", "options": ["None", "Left", "Center", "Right"]}
        },
        "ports": [
            {"name": "measurement", "type": "sensor", "fluid_state": "any", "pressure_side": "any", "position": [0.5, 0.5]}
        ],
        "zones": []
    },
    
    "Fan": {
        "properties": {
            "rpm": {"type": "integer", "default": 1200, "min": 0, "max": 5000},
            "air_flow_type": {"type": "enum", "default": "Air Inlet", "options": ["Air Inlet", "Air Outlet"]},
            "sensor_count": {"type": "integer", "default": 6, "min": 1, "max": 12},
            "circuit_label": {"type": "enum", "default": "None", "options": ["None", "LH", "RH", "CTR"]}
        },
        "ports": [],
        "dynamic_ports": {
            "prefix": "sensor_",
            "count_property": "sensor_count",
            "port_details": {"type": "sensor", "fluid_state": "any", "pressure_side": "any"},
            "position_side": "right"
        },
        "zones": []
    },
    
    "AirSensorArray": {
        "properties": {
            "curtain_type": {"type": "enum", "default": "Primary", "options": ["Primary", "Secondary", "Return"]},
            "sensor_count": {"type": "integer", "default": 11, "min": 3, "max": 40},
            "block_width": {"type": "integer", "default": 400, "min": 150, "max": 2000},
            "block_height": {"type": "integer", "default": 25, "min": 15, "max": 50}
        },
        "ports": [],
        "zones": []
    },
    
    "ShelvingGrid": {
        "properties": {
            "shelving_type": {"type": "enum", "default": "Modular", "options": ["Modular", "Non-Modular"]},
            "module_count": {"type": "integer", "default": 3, "min": 1, "max": 3},
            "door_count": {"type": "integer", "default": 3, "min": 1, "max": 5},
            "shelf_rows": {"type": "integer", "default": 6, "min": 1, "max": 10},
            "shelf_width": {"type": "integer", "default": 100, "min": 50, "max": 300},
            "shelf_height": {"type": "integer", "default": 60, "min": 30, "max": 150},
            "row_gap": {"type": "integer", "default": 20, "min": 0, "max": 100}
        },
        "ports": [],
        "zones": []
    },
    


    "HotGasBypassValve": {
        "properties": {
            "capacity": {"type": "integer", "default": 500, "min": 0, "max": 5000},
            "pressure_drop": {"type": "integer", "default": 0, "min": 0, "max": 50},
            "circuit_label": {"type": "enum", "default": "None", "options": ["None", "Left", "Center", "Right"]}
        },
        "ports": [
            {"name": "inlet", "type": "in", "fluid_state": "gas", "pressure_side": "high", "position": [0.5, 0]},
            {"name": "outlet", "type": "out", "fluid_state": "two-phase", "pressure_side": "low", "position": [1, 0.5]}
        ],
        "zones": []
    },

    "HotGasLoop": {
        "properties": {
            "capacity": {"type": "integer", "default": 1000},
            "circuit_label": {"type": "enum", "default": "None", "options": ["None", "Left", "Center", "Right"]}
        },
        "ports": [
            {"name": "inlet", "type": "in", "fluid_state": "two-phase", "pressure_side": "low", "position": [0, 0.5]},
            {"name": "outlet", "type": "out", "fluid_state": "gas", "pressure_side": "low", "position": [1, 0.5]}
        ],
        "zones": []
    },

    "Sensor": {
        "properties": {
            "measurement_type": {
                "type": "enum",
                "default": "Custom Measurement",
                "options": [
                    "Superheat",
                    "Subcooling",
                    "Sensor Bulb",
                    "Ambient Dry Bulb",
                    "Ambient Wet Bulb",
                    "Discharge Pressure",
                    "Suction Pressure",
                    "Electrical Current",
                    "Electrical Voltage",
                    "Custom Measurement"
                ]
            },
            "label": {"type": "string", "default": "Sensor"},
            "circuit_label": {"type": "enum", "default": "None", "options": ["None", "Left", "Center", "Right"]}
        },
        "ports": [
            {"name": "inlet", "type": "in", "fluid_state": "any", "pressure_side": "any", "position": [0, 0.5]},
            {"name": "outlet", "type": "out", "fluid_state": "any", "pressure_side": "any", "position": [1, 0.5]},
            {"name": "measurement", "type": "sensor", "fluid_state": "any", "pressure_side": "any", "position": [0.5, 0]}
        ],
        "size": {"width": 30, "height": 30},
        "zones": []
    },

    "SplitterManifold": {
        "properties": {
            "circuits": {"type": "integer", "default": 3, "min": 1, "max": 12},
            "circuit_label": {"type": "enum", "default": "None", "options": ["None", "Left", "Center", "Right"]}
        },
        "ports": [
            {"name": "inlet", "type": "in", "fluid_state": "any", "pressure_side": "any", "position": [0.5, 0]}
        ],
        "zones": []
    },

    "CombinerManifold": {
        "properties": {
            "circuits": {"type": "integer", "default": 3, "min": 1, "max": 12},
            "circuit_label": {"type": "enum", "default": "None", "options": ["None", "Left", "Center", "Right"]}
        },
        "ports": [
            {"name": "outlet", "type": "out", "fluid_state": "any", "pressure_side": "any", "position": [0.5, 1]}
        ],
        "zones": []
    },

    "LabeledBox": {
        "properties": {
            "label": {"type": "string", "default": ""},
            "circuit_label": {"type": "enum", "default": "None",
                              "options": ["None", "Left", "Center", "Right"]}
        },
        "ports": [
            {"name": "inlet",  "type": "in",  "fluid_state": "any", "pressure_side": "any", "position": [0.5, 0]},
            {"name": "outlet", "type": "out", "fluid_state": "any", "pressure_side": "any", "position": [0.5, 1]}
        ],
        "zones": []
    },

    "AirArrow": {
        "properties": {
            "direction": {"type": "string", "default": "up"},
            "circuit_label": {"type": "enum", "default": "None", "options": ["None"]}
        },
        "ports": [],
        "zones": []
    },

    "DecorativeRect": {
        "properties": {
            "bg_color":   {"type": "string", "default": "#E0E0E0"},
            "label":      {"type": "string", "default": ""},
            "text_color": {"type": "string", "default": "#000000"},
            "circuit_label": {"type": "enum", "default": "None", "options": ["None"]}
        },
        "ports": [],
        "zones": []
    },

    "Boundary": {
        "properties": {
            "label":        {"type": "string", "default": ""},
            "stroke_color": {"type": "string", "default": "#AAAAAA"},
            "circuit_label": {"type": "enum", "default": "None", "options": ["None"]}
        },
        "ports": [],
        "zones": []
    }
}
