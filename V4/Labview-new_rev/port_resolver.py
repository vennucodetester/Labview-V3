"""
port_resolver.py

Utilities to enumerate component ports and resolve their mapped sensors and
current values, using diagram model as the single source of truth.

Role key resolution order:
1) "{TypeName}.{componentId}.{portName}"
2) "{componentId}.{portName}"
"""

from typing import Dict, List, Optional, Tuple, Any
from component_schemas import SCHEMAS


def enumerate_ports_for_component(component_type: str, component_props: Dict[str, Any]) -> List[str]:
    ports: List[str] = []
    schema = SCHEMAS.get(component_type, {})

    # Static ports
    for p in schema.get('ports', []) or []:
        name = p.get('name')
        if name:
            ports.append(name)

    # Dynamic ports (support _2/_3 keys in schema)
    for dyn_key in ('dynamic_ports', 'dynamic_ports_2', 'dynamic_ports_3'):
        dyn = schema.get(dyn_key)
        if not dyn:
            continue
        prefix = dyn.get('prefix')
        count_prop = dyn.get('count_property')
        if not prefix or not count_prop:
            continue
        count = int((component_props.get(count_prop) or 0))
        for i in range(1, count + 1):
            ports.append(f"{prefix}{i}")

    # Evaporator distributor ports
    if component_type == 'Evaporator':
        if component_props.get('inlet_distributor') == 'Yes':
            ports.append('dist_inlet')
        if component_props.get('outlet_distributor') == 'Yes':
            ports.append('dist_outlet')

    # Condenser conditional ports (Water Cooled only; Air Cooled gets none)
    if component_type == 'Condenser':
        condenser_type = component_props.get('condenser_type', 'Air Cooled')
        cond_ports = schema.get('conditional_ports', {}) or {}
        for p in cond_ports.get(condenser_type, []):
            name = p.get('name')
            if name:
                ports.append(name)

    return ports


def resolve_mapped_sensor(diagram_model: Dict[str, Any], component_type: str, component_id: str, port_name: str) -> Optional[str]:
    roles: Dict[str, str] = diagram_model.get('sensor_roles', {}) or {}
    primary = f"{component_type}.{component_id}.{port_name}"
    fallback = f"{component_id}.{port_name}"
    return roles.get(primary) or roles.get(fallback)


def find_sensor_by_measurement_type(diagram_model: Dict[str, Any], measurement_type: str, circuit_label: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Find inline Sensor component by its measurement_type property.

    Returns (comp_id, sensor_csv_column) or (None, None) if not found.
    Searches sensor_roles for the Sensor component's measurement port mapping.
    """
    components = diagram_model.get('components', {}) or {}
    for comp_id, comp in components.items():
        if comp.get('type') != 'Sensor':
            continue
        props = comp.get('properties', {}) or {}
        if props.get('measurement_type') == measurement_type:
            if circuit_label and props.get('circuit_label', 'None') != circuit_label:
                continue
            # Check if this sensor's measurement port is mapped to a CSV column
            sensor_col = resolve_mapped_sensor(diagram_model, 'Sensor', comp_id, 'measurement')
            if sensor_col:
                return comp_id, sensor_col
    return None, None


def find_suction_pressure_sensor(diagram_model: Dict[str, Any]) -> Optional[str]:
    """Find suction pressure CSV column — inline Sensor first, then legacy Compressor.SP."""
    _, col = find_sensor_by_measurement_type(diagram_model, 'Suction Pressure')
    if col:
        return col
    # Legacy fallback: Compressor SP port
    for comp_id, comp in (diagram_model.get('components', {}) or {}).items():
        if comp.get('type') == 'Compressor':
            return resolve_mapped_sensor(diagram_model, 'Compressor', comp_id, 'SP')
    return None


def find_discharge_pressure_sensor(diagram_model: Dict[str, Any]) -> Optional[str]:
    """Find discharge pressure CSV column — inline Sensor first, then legacy Compressor.DP."""
    _, col = find_sensor_by_measurement_type(diagram_model, 'Discharge Pressure')
    if col:
        return col
    # Legacy fallback: Compressor DP port
    for comp_id, comp in (diagram_model.get('components', {}) or {}).items():
        if comp.get('type') == 'Compressor':
            return resolve_mapped_sensor(diagram_model, 'Compressor', comp_id, 'DP')
    return None


def get_sensor_number(dm, sensor_name: Optional[str]) -> Optional[int]:
    if not sensor_name:
        return None
    try:
        return dm.get_sensor_number(sensor_name)
    except Exception:
        return None


def get_sensor_value(dm, sensor_name: Optional[str]) -> Optional[float]:
    if not sensor_name:
        return None
    try:
        return dm.get_sensor_value(sensor_name)
    except Exception:
        return None


def format_port_label(component_type: str, component_props: Dict[str, Any], port_name: str) -> str:
    label = component_props.get('circuit_label')
    side = f"{label} " if label else ""
    if component_type == 'Evaporator':
        airflow = component_props.get('air_flow_direction') or 'Bottom to Top'
        if port_name == 'dist_inlet':
            return f"{side}Evap Dist Inlet".strip()
        if port_name == 'dist_outlet':
            return f"{side}Evap Dist Outlet".strip()
        if port_name.startswith('inlet_circuit_'):
            idx = port_name.split('_')[-1]
            return f"{side}Evap Inlet {idx}".strip()
        if port_name.startswith('outlet_circuit_'):
            idx = port_name.split('_')[-1]
            return f"{side}Evap Outlet {idx}".strip()
        if port_name.startswith('sensor_bottom_'):
            idx = port_name.split('_')[-1]
            role = "Air In" if airflow == "Bottom to Top" else "Air Out"
            return f"{side}Evap {role} Sensor {idx}".strip()
        if port_name.startswith('sensor_top_'):
            idx = port_name.split('_')[-1]
            role = "Air Out" if airflow == "Bottom to Top" else "Air In"
            return f"{side}Evap {role} Sensor {idx}".strip()
    if component_type == 'Distributor':
        if port_name == 'inlet':
            return f"{side}Distributor Inlet".strip()
        if port_name.startswith('outlet_'):
            idx = port_name.split('_')[-1]
            return f"{side}Distributor Outlet {idx}".strip()
    if component_type == 'TXV':
        if port_name == 'inlet':
            return f"TXV {side}Inlet".replace('  ', ' ').strip()
        if port_name == 'outlet':
            return f"TXV {side}Outlet".replace('  ', ' ').strip()
        if port_name == 'bulb':
            return f"TXV {side}Bulb".replace('  ', ' ').strip()
    if component_type == 'Compressor':
        if port_name == 'inlet':
            return "Compressor Inlet"
        if port_name == 'outlet':
            return "Compressor Outlet"
        if port_name == 'SP':
            return "Suction Pressure"
        if port_name == 'DP':
            return "Discharge Pressure"
        if port_name == 'RPM':
            return "Compressor RPM"
    if component_type == 'Condenser':
        if port_name == 'inlet':
            return "Condenser Inlet"
        if port_name == 'outlet':
            return "Condenser Outlet"
        if port_name == 'water_in_temp':
            return "Condenser Water Inlet Temp"
        if port_name == 'water_out_temp':
            return "Condenser Water Outlet Temp"
        if port_name == 'water_flow_gpm':
            return "Condenser Water Flow GPM"
    if component_type == 'Junction':
        if port_name.startswith('inlet_'):
            idx = port_name.split('_')[-1]
            return f"{side}Junction Inlet {idx}".strip()
        if port_name.startswith('outlet_'):
            idx = port_name.split('_')[-1]
            return f"{side}Junction Outlet {idx}".strip()
        if port_name == 'sensor':
            return f"{side}Junction Sensor".strip()
    if component_type == 'SensorBulb' and port_name == 'measurement':
        return f"Sensor Bulb {side}Measurement".replace('  ', ' ').strip()
    if component_type == 'Sensor':
        measure = component_props.get('measurement_type', 'Custom Measurement')
        lbl = component_props.get('label', '')
        display = lbl or measure
        if port_name == 'measurement':
            return f"{display}".strip()
        if port_name == 'inlet':
            return f"{display} Inlet".strip()
        if port_name == 'outlet':
            return f"{display} Outlet".strip()
        return f"{display}".strip()
    return f"{side}{port_name}".strip()


def list_all_ports(dm) -> List[Dict[str, Any]]:
    """Return a list of port dicts with resolved sensor and value.

    Each dict: { componentId, type, properties, port, label, roleKeyPrimary,
                 roleKeyFallback, sensor, sensorNumber, value }
    """
    out: List[Dict[str, Any]] = []
    model = dm.diagram_model
    components: Dict[str, Dict] = model.get('components', {}) or {}

    for comp_id, comp in components.items():
        ctype = comp.get('type')
        props = comp.get('properties', {}) or {}
        for port in enumerate_ports_for_component(ctype, props):
            sensor = resolve_mapped_sensor(model, ctype, comp_id, port)
            out.append({
                'componentId': comp_id,
                'type': ctype,
                'properties': props,
                'port': port,
                'label': format_port_label(ctype, props, port),
                'roleKeyPrimary': f"{ctype}.{comp_id}.{port}",
                'roleKeyFallback': f"{comp_id}.{port}",
                'sensor': sensor,
                'sensorNumber': get_sensor_number(dm, sensor),
                'value': get_sensor_value(dm, sensor),
            })
    return out


def get_pressures_from_compressor(dm) -> Dict[str, Optional[float]]:
    """Return suction and discharge pressures based on compressor ports (if mapped)."""
    model = dm.diagram_model
    components: Dict[str, Dict] = model.get('components', {}) or {}
    suction_val: Optional[float] = None
    discharge_val: Optional[float] = None
    for comp_id, comp in components.items():
        if comp.get('type') != 'Compressor':
            continue
        for port in ('inlet', 'outlet'):
            sensor = resolve_mapped_sensor(model, 'Compressor', comp_id, port)
            val = get_sensor_value(dm, sensor)
            if port == 'inlet' and val is not None:
                suction_val = val
            if port == 'outlet' and val is not None:
                discharge_val = val
    return {'suction': suction_val, 'discharge': discharge_val}


def get_evaporator_outlet_temps(dm) -> Dict[str, List[float]]:
    """Return outlet temps grouped by evaporator circuit_label (Left/Center/Right)."""
    model = dm.diagram_model
    components: Dict[str, Dict] = model.get('components', {}) or {}
    groups: Dict[str, List[float]] = {'Left': [], 'Center': [], 'Right': []}
    for comp_id, comp in components.items():
        if comp.get('type') != 'Evaporator':
            continue
        props = comp.get('properties', {}) or {}
        label = props.get('circuit_label') or ''
        for port in enumerate_ports_for_component('Evaporator', props):
            if not port.startswith('outlet_circuit_'):
                continue
            sensor = resolve_mapped_sensor(model, 'Evaporator', comp_id, port)
            val = get_sensor_value(dm, sensor)
            if val is not None and label in groups:
                groups[label].append(val)
    return groups


