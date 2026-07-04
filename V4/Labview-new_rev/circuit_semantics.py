"""
circuit_semantics.py

The semantic layer that makes the code understand the refrigeration circuit.

Key functions
-------------
assign_port_semantics(model)
    Walk every component in model['components'] and write a
    model['port_semantics'] dict that maps each role_key
    (e.g. "TXV.txv_abc123.inlet") to a descriptor dict containing:
        state_name        — thermodynamic identity string
        state_point       — cycle point ('2b', '3a', '4a', etc.) or None
        module            — 'Left' | 'Center' | 'Right' | None
        circuit           — integer circuit number or None
        fluid_state       — 'gas' | 'liquid' | 'two-phase' | 'any'
        pressure_side     — 'high' | 'low' | 'any'
        measurement_type  — 'temperature' | 'pressure' | 'flow' | 'speed' | None
        calc_key          — matching key used in calculation_engine (or None)

resolve_sensor_by_state(model, state_name, module, circuit)
    Find the CSV column mapped to a thermodynamic state.

get_all_module_labels(model)
    Return sorted unique circuit_label values from the diagram.

validate_thermodynamic_consistency(model, csv_data, refrigerant)
    Physics-based sanity checks on the current sensor readings.

suggest_sensor_mappings(model, csv_columns)
    Fuzzy-match CSV column names to unmapped ports using keyword library.

compute_diagram_derived_values(model, csv_data, refrigerant)
    Compute derived thermodynamic values (superheat, subcooling, quality)
    at key ports for display in Analysis mode.
"""

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  State-name vocabulary — see plan for full description
# ---------------------------------------------------------------------------

# Mapping:  (component_type, port_name) → (state_name, state_point,
#            fluid_state, pressure_side, measurement_type, calc_key_template)
#
# calc_key_template uses '{mod}' as a placeholder for 'lh', 'ctr', 'rh'
# (the lowercase abbreviation used internally by calculation_engine).
# None means no module suffix — system-level quantity.
# 'CIRCUIT' means the circuit number must be appended.

_MODULE_ABBREV = {'Left': 'lh', 'Center': 'ctr', 'Right': 'rh', 'None': 'lh', None: 'lh'}

_PORT_SEMANTICS_TABLE = {
    # (comp_type, port_name): (state_name, state_point, fluid_state, pressure_side, meas_type, calc_key_tmpl, module_aware)
    ('Compressor', 'inlet'):   ('comp_suction',      '2b',   'gas',       'low',  'temperature', 'T_2b',       False),
    ('Compressor', 'outlet'):  ('comp_discharge',    '3a',   'gas',       'high', 'temperature', 'T_3a',       False),
    ('Compressor', 'RPM'):     ('comp_rpm',           None,  'any',       'any',  'speed',        'RPM',        False),
    ('Compressor', 'SP'):      ('suction_pressure',   'suc', 'any',       'low',  'pressure',    'P_suc',      False),
    ('Compressor', 'DP'):      ('discharge_pressure', 'disch','any',      'high', 'pressure',    'P_disch',    False),

    ('Condenser',  'inlet'):   ('cond_inlet',         '3b',  'gas',       'high', 'temperature', 'T_3b',       False),
    ('Condenser',  'outlet'):  ('cond_outlet',        '4a',  'liquid',    'high', 'temperature', 'T_4a',       False),
    ('Condenser',  'water_in_temp'):  ('cond_water_in',  None,'any','any','temperature','T_waterin', False),
    ('Condenser',  'water_out_temp'): ('cond_water_out', None,'any','any','temperature','T_waterout',False),
    ('Condenser',  'water_flow_gpm'): ('cond_water_flow',None,'any','any','flow',       'GPM_water', False),

    ('FilterDrier','inlet'):   ('filter_drier_inlet', None,  'liquid',    'high', 'temperature', None,         False),
    ('FilterDrier','outlet'):  ('filter_drier_outlet',None,  'liquid',    'high', 'temperature', None,         False),

    # TXV — module-aware
    ('TXV',        'inlet'):   ('txv_inlet',          '4b',  'liquid',    'high', 'temperature', 'T_4b-{mod}', True),
    ('TXV',        'outlet'):  ('txv_outlet',         '1',   'two-phase', 'low',  'temperature', 'T_1a-{mod}', True),
    ('TXV',        'bulb'):    ('txv_bulb',            None, 'any',       'low',  'temperature', None,         True),

    # Evaporator — module-aware; circuit-level ports handled separately
    ('Evaporator', 'dist_inlet'):      ('evap_inlet',   '1',  'two-phase','low',  'temperature', 'T_1b-{mod}', True),
    ('Evaporator', 'inlet_circuit_*'): ('evap_inlet',   '1',  'two-phase','low',  'temperature', None,         True),
    ('Evaporator', 'outlet_circuit_*'):('evap_outlet',  '2a', 'gas',      'low',  'temperature', 'T_2a-{MOD}', True),
    # ('T_2a-{MOD}' uses uppercase module abbreviation: 'LH', 'CTR', 'RH'  — all consistent)

    # HotGasBypassValve — module-aware
    ('HotGasBypassValve','inlet'):  ('hot_gas_bypass_inlet',  None,'gas',     'high','temperature',None, True),
    ('HotGasBypassValve','outlet'): ('hot_gas_bypass_outlet', None,'two-phase','low','temperature',None, True),

    # HotGasLoop — module-aware
    ('HotGasLoop','inlet'):  ('hot_gas_loop_inlet',  None,'two-phase','low','temperature',None,True),
    ('HotGasLoop','outlet'): ('hot_gas_loop_outlet', None,'gas',      'low','temperature',None,True),

    # Junction / Splitter / Merger — no semantics needed (flow-through only)

    # Sensor (inline measurement component)
    ('Sensor', 'inlet'):       ('sensor_flow_in',    None, 'any','any',None,None,False),
    ('Sensor', 'outlet'):      ('sensor_flow_out',   None, 'any','any',None,None,False),
    ('Sensor', 'measurement'): ('custom_measurement',None, 'any','any','temperature',None,False),

    # SensorBulb
    ('SensorBulb','measurement'):('sensor_bulb',     None, 'any','any','temperature',None,True),

    # AirSensorArray — generic; individual sensor_N ports resolved dynamically
    # ShelvingGrid   — shelf_temp; port names resolved dynamically

    # RemoteLineEndpoint
    ('RemoteLineEndpoint','connection'):('remote_connection',None,'any','any',None,None,False),
}


def _get_port_entry(comp_type: str, port_name: str):
    """Look up the semantics table; wildcard '*' entries match numbered ports."""
    key = (comp_type, port_name)
    if key in _PORT_SEMANTICS_TABLE:
        return _PORT_SEMANTICS_TABLE[key]
    # Try wildcard: 'outlet_circuit_*', 'inlet_circuit_*', 'sensor_*'
    for (ct, pn), entry in _PORT_SEMANTICS_TABLE.items():
        if ct == comp_type and pn.endswith('*'):
            prefix = pn[:-1]
            if port_name.startswith(prefix):
                return entry
    return None


def _module_label_to_abbrev(label: str, upper: bool = False) -> str:
    d = {'Left': 'lh', 'Center': 'ctr', 'Right': 'rh', 'None': 'lh', None: 'lh'}
    abbrev = d.get(label, 'lh')
    return abbrev.upper() if upper else abbrev


# ---------------------------------------------------------------------------
#  Public helper functions — single source of truth for label→key mappings.
#  All other modules import from here; no other file should define these.
# ---------------------------------------------------------------------------

def module_abbrev(label: str, upper: bool = False) -> str:
    """Convert a circuit_label string to the key suffix used in calculation columns.

    'Left'   → 'lh'  (or 'LH'  if upper=True)
    'Center' → 'ctr' (or 'CTR' if upper=True)
    'Right'  → 'rh'  (or 'RH'  if upper=True)
    None / 'None' → 'lh' (single-module fallback)
    """
    return _module_label_to_abbrev(label, upper=upper)


def txv_outlet_key(label: str) -> str:
    """Return the sensor role key for the coil inlet (TXV outlet / evap dist_inlet).

    Naming: T_1b-{abbrev} for all modules.
    Left → 'T_1b-lh', Center → 'T_1b-ctr', Right → 'T_1b-rh'

    Note: An earlier version used 'T_1c-rh' for the Right module — that was a
    dataset-specific anomaly that has now been corrected. Session files carrying
    the old key are migrated automatically on load by data_manager._migrate_sensor_role_keys().
    """
    return f'T_1b-{_module_label_to_abbrev(label)}'


def coil_outlet_key(label: str) -> str:
    """Return the sensor role key for the evap coil outlet (T_2a).

    Naming: T_2a-{ABBREV} (uppercase abbreviation for all modules).
    Left → 'T_2a-LH', Center → 'T_2a-CTR', Right → 'T_2a-RH'

    Note: An earlier version used 'T_2a-ctr' (lowercase) for Center — corrected here.
    Session files carrying the old key are migrated automatically on load.
    """
    return f'T_2a-{_module_label_to_abbrev(label, upper=True)}'


def _circuit_number_from_port(port_name: str) -> int | None:
    """Extract trailing integer from port names like 'outlet_circuit_3' → 3."""
    import re
    m = re.search(r'(\d+)$', port_name)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
#  assign_port_semantics
# ---------------------------------------------------------------------------

def assign_port_semantics(model: dict) -> dict:
    """Populate model['port_semantics'] by walking all components.

    Returns model (mutated in-place).
    """
    if 'port_semantics' not in model:
        model['port_semantics'] = {}
    ps = model['port_semantics']

    components = model.get('components', {})
    for comp_id, comp_data in components.items():
        comp_type = comp_data.get('type', '')
        props     = comp_data.get('properties', {})
        circuit_label = props.get('circuit_label', 'None')
        if circuit_label in ('', None):
            circuit_label = 'None'

        # Collect port names from the component's stored data
        # (We use the port_names that would be on the item; since this is
        #  pure-Python we read the schema to determine them.)
        port_names = _infer_port_names(comp_type, props)

        for port_name in port_names:
            role_key = f"{comp_type}.{comp_id}.{port_name}"
            entry = _get_port_entry(comp_type, port_name)
            if entry is None:
                continue

            (state_name, state_point, fluid_state, pressure_side,
             meas_type, calc_key_tmpl, module_aware) = entry

            module  = circuit_label if module_aware else None
            circuit = _circuit_number_from_port(port_name)

            # Resolve calc_key template
            calc_key = None
            if calc_key_tmpl:
                abbrev_lo = _module_label_to_abbrev(module, upper=False)
                abbrev_hi = _module_label_to_abbrev(module, upper=True)
                calc_key = (calc_key_tmpl
                            .replace('{mod}', abbrev_lo)
                            .replace('{MOD}', abbrev_hi))

            ps[role_key] = {
                'state_name':       state_name,
                'state_point':      state_point,
                'module':           module,
                'circuit':          circuit,
                'fluid_state':      fluid_state,
                'pressure_side':    pressure_side,
                'measurement_type': meas_type,
                'calc_key':         calc_key,
            }

    return model


def _infer_port_names(comp_type: str, props: dict) -> list:
    """Return expected port names for a component based on its type and props.

    Uses component_schemas.SCHEMAS to enumerate static ports and
    computes dynamic port names from property values.
    """
    try:
        from component_schemas import SCHEMAS
    except ImportError:
        return []

    schema = SCHEMAS.get(comp_type, {})
    names  = []

    # Static ports
    for port_def in schema.get('ports', []):
        names.append(port_def['name'])

    # Conditional ports (Condenser water-cooled)
    cond_ports = schema.get('conditional_ports', {})
    if cond_ports and comp_type == 'Condenser':
        ctype = props.get('condenser_type', 'Air Cooled')
        for port_def in cond_ports.get(ctype, []):
            names.append(port_def['name'])

    # Dynamic ports (numbered: outlet_circuit_1 … outlet_circuit_N)
    for key in ('dynamic_ports', 'dynamic_ports_2', 'dynamic_ports_3'):
        dp = schema.get(key)
        if not dp:
            continue
        prefix = dp.get('prefix', '')
        count_prop = dp.get('count_property', '')
        count = int(props.get(count_prop, 1))
        for i in range(1, count + 1):
            names.append(f"{prefix}{i}")

    # Evaporator distributor ports
    if comp_type == 'Evaporator':
        if props.get('inlet_distributor') == 'Yes':
            names.append('dist_inlet')
        if props.get('outlet_distributor') == 'Yes':
            names.append('dist_outlet')

    return names


# ---------------------------------------------------------------------------
#  resolve_sensor_by_state
# ---------------------------------------------------------------------------

def resolve_sensor_by_state(model: dict, state_name: str,
                             module: str = None,
                             circuit: int = None) -> str | None:
    """Find the CSV column name mapped to a given thermodynamic state.

    Args:
        model:      diagram_model dict
        state_name: e.g. 'txv_inlet', 'evap_outlet', 'comp_suction'
        module:     'Left' | 'Center' | 'Right' | None (for system-level)
        circuit:    integer circuit number, or None

    Returns:
        CSV column name string, or None if not mapped / not present.
    """
    ps            = model.get('port_semantics', {})
    sensor_roles  = model.get('sensor_roles', {})

    for role_key, descriptor in ps.items():
        if descriptor.get('state_name') != state_name:
            continue
        if module is not None and descriptor.get('module') != module:
            continue
        if circuit is not None and descriptor.get('circuit') != circuit:
            continue
        # Found a matching port — is it mapped?
        csv_col = sensor_roles.get(role_key)
        if csv_col:
            return csv_col
    return None


# ---------------------------------------------------------------------------
#  get_all_module_labels
# ---------------------------------------------------------------------------

def get_all_module_labels(model: dict) -> list:
    """Return sorted list of unique circuit_label values in the diagram
    (excluding 'None' / None).

    E.g. ['Left', 'Right'] for an 8ft modular case.
    """
    labels = set()
    for comp_data in model.get('components', {}).values():
        lbl = comp_data.get('properties', {}).get('circuit_label')
        if lbl and lbl not in ('None', None):
            labels.add(lbl)
    order = ['Left', 'Center', 'Right']
    return [l for l in order if l in labels]


# ---------------------------------------------------------------------------
#  validate_thermodynamic_consistency
# ---------------------------------------------------------------------------

def validate_thermodynamic_consistency(model: dict, csv_data,
                                        refrigerant: str = 'R290') -> list:
    """Check current sensor readings against refrigeration physics rules.

    Args:
        model:       diagram_model dict with port_semantics populated
        csv_data:    dict-like {csv_column: value} for the current row
        refrigerant: CoolProp refrigerant string (default R290 = Propane)

    Returns:
        List of violation dicts:
        {role_key, state_name, rule, expected, actual, severity}
        severity: 'warning' | 'error'
    """
    violations = []

    def _get(state_name, module=None):
        col = resolve_sensor_by_state(model, state_name, module=module)
        if col and col in csv_data:
            try:
                return float(csv_data[col])
            except (TypeError, ValueError):
                pass
        return None

    def _violation(rule, expected, actual, severity='warning',
                   state_name=None, role_key=None):
        violations.append({
            'role_key':   role_key,
            'state_name': state_name,
            'rule':        rule,
            'expected':   expected,
            'actual':     actual,
            'severity':   severity,
        })

    # Collect system-level values
    T_2b    = _get('comp_suction')
    T_3a    = _get('comp_discharge')
    T_3b    = _get('cond_inlet')
    T_4a    = _get('cond_outlet')
    P_suc   = _get('suction_pressure')
    P_disch = _get('discharge_pressure')

    # Rule 1: Discharge temp > suction temp
    if T_2b is not None and T_3a is not None:
        if T_3a <= T_2b:
            _violation('Discharge temperature must be > suction temperature',
                       f'T_3a > T_2b ({T_2b:.1f}°F)', f'T_3a = {T_3a:.1f}°F',
                       severity='error', state_name='comp_discharge')

    # Rule 2: High pressure > low pressure
    if P_suc is not None and P_disch is not None:
        if P_disch <= P_suc:
            _violation('Discharge pressure must be > suction pressure',
                       f'P_disch > P_suc ({P_suc:.1f} PSIG)', f'P_disch = {P_disch:.1f} PSIG',
                       severity='error', state_name='discharge_pressure')

    # Rule 3: Suction pressure > 0
    if P_suc is not None and P_suc <= 0:
        _violation('Suction pressure should be > 0 PSIG (vacuum or offline?)',
                   '>0 PSIG', f'{P_suc:.1f} PSIG',
                   severity='error', state_name='suction_pressure')

    # Per-module rules
    labels = get_all_module_labels(model) or [None]  # None = non-modular fallback
    for mod in labels:
        T_4b = _get('txv_inlet',   module=mod)
        T_2a = _get('evap_outlet', module=mod)

        if P_suc is not None and T_2a is not None:
            try:
                import CoolProp.CoolProp as CP
                T_sat_suc_C = CP.PropsSI('T', 'P', (P_suc + 14.696) * 6894.76, 'Q', 1, refrigerant) - 273.15
                T_sat_suc_F = T_sat_suc_C * 9 / 5 + 32
                SH_coil = T_2a - T_sat_suc_F
                # Rule 4: Evap outlet superheated
                if SH_coil < 0:
                    _violation(f'Evap outlet should be superheated (module={mod})',
                               'SH > 0°F', f'SH = {SH_coil:.1f}°F (flooded!)',
                               severity='error', state_name='evap_outlet')
            except Exception:
                pass  # CoolProp not available or data missing — skip

        if P_disch is not None and T_4b is not None:
            try:
                import CoolProp.CoolProp as CP
                T_sat_disch_C = CP.PropsSI('T', 'P', (P_disch + 14.696) * 6894.76, 'Q', 0, refrigerant) - 273.15
                T_sat_disch_F = T_sat_disch_C * 9 / 5 + 32
                SC_txv = T_sat_disch_F - T_4b
                # Rule 5: TXV inlet subcooled
                if SC_txv < 0:
                    _violation(f'TXV inlet should be subcooled (module={mod})',
                               'SC > 0°F', f'SC = {SC_txv:.1f}°F',
                               severity='warning', state_name='txv_inlet')
            except Exception:
                pass

    return violations


# ---------------------------------------------------------------------------
#  suggest_sensor_mappings
# ---------------------------------------------------------------------------

#  Keyword library for fuzzy matching CSV column names to state names
_KEYWORDS: dict[str, list[str]] = {
    'comp_suction':          ['suction', 'comp in', 'comp inlet', 'return gas', 'T_2b', 'suc temp', 'suction temp'],
    'comp_discharge':        ['discharge', 'comp out', 'comp outlet', 'T_3a', 'disch temp', 'discharge temp'],
    'cond_inlet':            ['cond in', 'cond inlet', 'T_3b', 'condenser inlet'],
    'cond_outlet':           ['cond out', 'cond outlet', 'liquid line', 'T_4a', 'condenser out'],
    'txv_inlet':             ['txv in', 'txv inlet', 'liquid', 'T_4b', 'liquid temp'],
    'txv_outlet':            ['txv out', 'evap in', 'after txv'],
    'txv_bulb':              ['bulb', 'sensing', 'txv bulb', 'sense bulb'],
    'evap_inlet':            ['evap in', 'dist in', 'distributor', 'after txv'],
    'evap_outlet':           ['evap out', 'coil out', 'coil outlet', 'T_2a', 'evap outlet', 'suction coil'],
    'suction_pressure':      ['suction press', 'P_suc', 'low side press', 'low pressure', 'suc press'],
    'discharge_pressure':    ['discharge press', 'P_disch', 'high side press', 'head press', 'high pressure'],
    'comp_rpm':              ['rpm', 'speed', 'hz', 'frequency', 'comp speed'],
    'cond_water_in':         ['water in', 'entering water', 'CW in', 'water inlet', 'chilled water in'],
    'cond_water_out':        ['water out', 'leaving water', 'CW out', 'water outlet', 'chilled water out'],
    'cond_water_flow':       ['gpm', 'flow', 'water flow', 'gallons'],
    'ambient_drybulb':       ['ambient', 'dry bulb', 'DB', 'room temp', 'ambient temp', 'outdoor'],
    'ambient_wetbulb':       ['wet bulb', 'WB', 'dew point', 'ambient wet'],
    'defrost_status':        ['defrost', 'defrost signal', 'DFR', 'defrost status'],
    'filter_drier_inlet':    ['filter in', 'drier in', 'FD in', 'filter drier inlet'],
    'filter_drier_outlet':   ['filter out', 'drier out', 'FD out', 'filter drier outlet'],
    'hot_gas_bypass_inlet':  ['hot gas in', 'HGB in', 'bypass in'],
    'hot_gas_bypass_outlet': ['hot gas out', 'HGB out', 'bypass out'],
    'shelf_temp':            ['shelf', 'product', 'product temp', 'shelf temp'],
    'discharge_air':         ['discharge air', 'air temp', 'curtain', 'air out'],
    'return_air':            ['return air', 'return', 'air in', 'return temp'],
}

# Module-location keywords appended when a module context is known
_MODULE_LOCATION_WORDS = {
    'Left':   ['left', 'LH', 'lh', 'l-side'],
    'Center': ['center', 'CTR', 'ctr', 'mid', 'centre'],
    'Right':  ['right', 'RH', 'rh', 'r-side'],
}


def _score_column(csv_col: str, keywords: list[str]) -> int:
    """Return a relevance score for a CSV column name against a keyword list."""
    col_lower = csv_col.lower()
    score = 0
    for kw in keywords:
        if kw.lower() in col_lower:
            score += 2 if len(kw) > 4 else 1
    return score


def suggest_sensor_mappings(model: dict, csv_columns: list) -> dict:
    """For each unmapped port with a known state_name, return ranked CSV
    column candidates.

    Returns:
        {role_key: [best_col, second_col, ...]}  (ranked by keyword score)
        Only includes ports that are currently unmapped.
    """
    ps           = model.get('port_semantics', {})
    sensor_roles = model.get('sensor_roles', {})
    suggestions  = {}

    for role_key, descriptor in ps.items():
        if role_key in sensor_roles:
            continue   # Already mapped
        state_name = descriptor.get('state_name')
        if not state_name:
            continue

        base_kws = list(_KEYWORDS.get(state_name, []))

        # Add module-location words if applicable
        mod = descriptor.get('module')
        if mod and mod in _MODULE_LOCATION_WORDS:
            base_kws = _MODULE_LOCATION_WORDS[mod] + base_kws

        if not base_kws:
            continue

        scored = [(col, _score_column(col, base_kws)) for col in csv_columns]
        scored = [(col, s) for col, s in scored if s > 0]
        scored.sort(key=lambda x: x[1], reverse=True)

        if scored:
            suggestions[role_key] = [col for col, _ in scored[:5]]

    return suggestions


# ---------------------------------------------------------------------------
#  compute_diagram_derived_values
# ---------------------------------------------------------------------------

def compute_diagram_derived_values(model: dict, csv_data,
                                    refrigerant: str = 'R290') -> dict:
    """Compute derived thermodynamic values at key ports for Analysis mode display.

    Args:
        model:       diagram_model dict with port_semantics populated
        csv_data:    dict-like {csv_column: value} for the current row
        refrigerant: CoolProp refrigerant string

    Returns:
        {role_key: display_string}
        e.g. {'TXV.abc.bulb': 'SH: 12.3°F', 'Condenser.xyz.outlet': 'SC: 15.2°F'}
    """
    derived = {}

    def _get_mapped_val(role_key):
        sensor_roles = model.get('sensor_roles', {})
        col = sensor_roles.get(role_key)
        if col and col in csv_data:
            try:
                return float(csv_data[col])
            except (TypeError, ValueError):
                pass
        return None

    def _get_state(state_name, module=None, circuit=None):
        col = resolve_sensor_by_state(model, state_name, module=module, circuit=circuit)
        if col and col in csv_data:
            try:
                return float(csv_data[col])
            except (TypeError, ValueError):
                pass
        return None

    # Try to get pressure values (system-level)
    P_suc   = _get_state('suction_pressure')
    P_disch = _get_state('discharge_pressure')

    try:
        import CoolProp.CoolProp as CP

        def _T_sat_F(P_psig, quality=1):
            """Saturation temperature in °F from PSIG."""
            P_Pa   = (P_psig + 14.696) * 6894.76
            T_C    = CP.PropsSI('T', 'P', P_Pa, 'Q', quality, refrigerant) - 273.15
            return T_C * 9 / 5 + 32

        T_sat_suc   = _T_sat_F(P_suc)   if P_suc   is not None else None
        T_sat_disch = _T_sat_F(P_disch) if P_disch is not None else None

    except Exception:
        T_sat_suc   = None
        T_sat_disch = None

    ps = model.get('port_semantics', {})

    for role_key, descriptor in ps.items():
        sn    = descriptor.get('state_name')
        mod   = descriptor.get('module')
        circ  = descriptor.get('circuit')

        val = _get_mapped_val(role_key)
        if val is None:
            continue

        # Superheat at evap coil outlet
        if sn == 'evap_outlet' and T_sat_suc is not None:
            sh = val - T_sat_suc
            derived[role_key] = f"SH: {sh:.1f}°F"

        # Superheat at TXV bulb (= sensing bulb measures suction SH)
        elif sn == 'txv_bulb' and T_sat_suc is not None:
            sh = val - T_sat_suc
            derived[role_key] = f"SH: {sh:.1f}°F"

        # Superheat at compressor suction (total SH)
        elif sn == 'comp_suction' and T_sat_suc is not None:
            sh = val - T_sat_suc
            derived[role_key] = f"Total SH: {sh:.1f}°F"

        # Subcooling at condenser outlet
        elif sn == 'cond_outlet' and T_sat_disch is not None:
            sc = T_sat_disch - val
            derived[role_key] = f"SC: {sc:.1f}°F"

        # Subcooling at TXV inlet (per module)
        elif sn == 'txv_inlet' and T_sat_disch is not None:
            sc = T_sat_disch - val
            derived[role_key] = f"SC: {sc:.1f}°F"

        # Vapour quality after TXV (at evap inlet / dist_inlet)
        elif sn == 'evap_inlet' and P_suc is not None and T_sat_disch is not None:
            # Get the corresponding TXV inlet enthalpy for this module
            T_4b = _get_state('txv_inlet', module=mod)
            if T_4b is not None:
                try:
                    import CoolProp.CoolProp as CP
                    P_disch_Pa = (P_disch + 14.696) * 6894.76 if P_disch else None
                    P_suc_Pa   = (P_suc   + 14.696) * 6894.76
                    T_4b_C     = (T_4b - 32) * 5 / 9 + 273.15
                    if P_disch_Pa:
                        h_4b = CP.PropsSI('H', 'T', T_4b_C, 'P', P_disch_Pa, refrigerant)
                        quality = CP.PropsSI('Q', 'H', h_4b, 'P', P_suc_Pa, refrigerant)
                        derived[role_key] = f"x: {quality:.2f}"
                except Exception:
                    pass

    return derived
