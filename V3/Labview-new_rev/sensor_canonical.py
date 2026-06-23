"""
sensor_canonical.py — canonical sensor naming.

Every physical sensor location on a generated diagram gets a stable canonical
ID (e.g. T_suc.in, T_prod.top.LE48.r) and a human-readable label
(e.g. "Compressor Suction Inlet Temp", "Top Shelf - 48in LE - Rear").

The canonical ID is what gets stored in the diagram model and what the alias
DB indexes against.  The human label is for hover tooltips and dropdown lists.

Naming scheme is documented in CLAUDE.md Section 15 (added with this module).
"""

from __future__ import annotations
from typing import Optional, Tuple, Dict, Any


# ── Circuit label normalization ─────────────────────────────────────────────
# Historical data has BOTH conventions ('LH' on Fans, 'Left' on TXVs).
_CIRCUIT_NORMALIZE = {'lh': 'Left', 'left': 'Left',
                      'ctr': 'Center', 'center': 'Center',
                      'rh': 'Right', 'right': 'Right'}
_CIRCUIT_TAG = {'Left': 'lh', 'Center': 'ctr', 'Right': 'rh'}


def _unit_tag_from_number(unit_num: str) -> str:
    """Historical cassette files use U1/U2 even when the diagram uses LH/RH."""
    return {'1': 'lh', '2': 'rh', '3': 'ctr'}.get(str(unit_num), f'u{unit_num}')


def _normalize_circuit(circuit_label: Optional[str]) -> str:
    if not circuit_label or circuit_label == 'None':
        return ''
    return _CIRCUIT_NORMALIZE.get(str(circuit_label).strip().lower(), str(circuit_label))


def _circuit_tag(circuit_label: Optional[str]) -> str:
    """Convert 'Left' → 'lh', 'LH' → 'lh', else empty."""
    norm = _normalize_circuit(circuit_label)
    return _CIRCUIT_TAG.get(norm, norm.lower() if norm else '')


def _circuit_human(circuit_label: Optional[str]) -> str:
    return _normalize_circuit(circuit_label)


# ── Shelf row names ─────────────────────────────────────────────────────────
def shelf_row_name(row_idx: int, total_rows: int) -> Tuple[str, str]:
    """(canonical, human) for a shelf row.

    row_idx is 0-based from TOP. Last row is always 'btm' / 'Bottom'.
    """
    if row_idx == 0:
        return ('top', 'Top')
    if row_idx == total_rows - 1:
        return ('btm', 'Bottom')
    if total_rows == 3:
        return ('mid', 'Middle')
    # 4+ rows: r2..r{N-1}
    rid = f'r{row_idx + 1}'
    ordinal = {2: '2nd', 3: '3rd', 4: '4th', 5: '5th',
               6: '6th', 7: '7th', 8: '8th', 9: '9th'}
    human = ordinal.get(row_idx + 1, f'{row_idx + 1}th')
    return (rid, human)


# ── Shelf column names ──────────────────────────────────────────────────────
def shelf_column_name(col_idx: int, total_cols: int,
                      col_distances: Optional[list] = None) -> Tuple[str, str]:
    """(canonical, human) for a shelf column.

    col_idx is 0-based from LEFT END. col=0 is always LE, col=last is always RE.
    Middle columns:
      - if col_distances provided (per case template), use them verbatim
      - else use 'Ctr' for 3-col, 'LE48'/'RE48' for 4-col, 'c{n}' otherwise.
    """
    # Endpoint cases
    if col_idx == 0:
        return ('LE', 'LE')
    if col_idx == total_cols - 1:
        return ('RE', 'RE')

    # Template-provided distance labels (e.g. ["LE", "LE48", "RE48", "RE"])
    if col_distances and 0 <= col_idx < len(col_distances):
        name = col_distances[col_idx]
        return (name, _humanize_distance(name))

    # Defaults
    if total_cols == 3:
        return ('Ctr', 'Center')
    if total_cols == 4:
        return ('LE48', '48in LE') if col_idx == 1 else ('RE48', '48in RE')
    return (f'c{col_idx + 1}', f'Col {col_idx + 1}')


def _humanize_distance(name: str) -> str:
    """LE48 → '48in LE', RE20 → '20in RE', Ctr → 'Center', LE → 'LE'."""
    if name in ('LE', 'RE'):
        return name
    if name == 'Ctr':
        return 'Center'
    import re
    m = re.match(r'^(LE|RE)(\d+)$', name)
    if m:
        return f'{m.group(2)}in {m.group(1)}'
    m = re.match(r'^(\d+)(LE|RE)$', name)
    if m:
        return f'{m.group(1)}in {m.group(2)}'
    return name


# ── Per-component canonical mapping ─────────────────────────────────────────

def canonical_for_compressor(props: Dict, port: str, unit_tag: str = '') -> Optional[Tuple[str, str]]:
    tag = unit_tag or _circuit_tag(props.get('circuit_label') or '')
    suf = f'.{tag}' if tag else ''
    suf_h = f' ({tag.upper()})' if tag else ''
    table = {
        'inlet':  (f'T_suc.in{suf}',  f'Compressor Suction Inlet Temp{suf_h}'),
        'outlet': (f'T_disc.out{suf}', f'Compressor Discharge Outlet Temp{suf_h}'),
        'SP':     (f'P_suc{suf}',     f'Suction Pressure{suf_h}'),
        'DP':     (f'P_disc{suf}',    f'Discharge Pressure{suf_h}'),
        'RPM':    (f'rpm{suf}',       f'Compressor RPM{suf_h}'),
    }
    return table.get(port)


def canonical_for_condenser(props: Dict, port: str, unit_tag: str = '') -> Optional[Tuple[str, str]]:
    tag = unit_tag or _circuit_tag(props.get('circuit_label') or '')
    suf = f'.{tag}' if tag else ''
    suf_h = f' ({tag.upper()})' if tag else ''
    table = {
        'inlet':           (f'T_cond.in{suf}',   f'Condenser Refrigerant Inlet Temp{suf_h}'),
        'outlet':          (f'T_cond.out{suf}',  f'Condenser Refrigerant Outlet Temp{suf_h}'),
        'water_in_temp':   (f'T_w.in{suf}',      f'Condenser Water Inlet Temp{suf_h}'),
        'water_out_temp':  (f'T_w.out{suf}',     f'Condenser Water Outlet Temp{suf_h}'),
        'water_inlet':     (f'T_w.in{suf}',      f'Condenser Water Inlet Temp{suf_h}'),
        'water_outlet':    (f'T_w.out{suf}',     f'Condenser Water Outlet Temp{suf_h}'),
        'water_flow_gpm':  (f'gpm_w{suf}',       f'Condenser Water Flow GPM{suf_h}'),
    }
    return table.get(port)


def canonical_for_txv(props: Dict, port: str, unit_tag: str = '') -> Optional[Tuple[str, str]]:
    label = props.get('circuit_label') or ''
    tag = unit_tag or _circuit_tag(label)
    human_pref = _circuit_human(label) or (unit_tag.upper() if unit_tag else '')
    pref = f'{human_pref} ' if human_pref else ''
    if not tag:
        return None
    table = {
        'inlet':  (f'T_txv.{tag}.in',   f'{pref}TXV Inlet Temp'),
        'outlet': (f'T_txv.{tag}.out',  f'{pref}TXV Outlet Temp'),
        'bulb':   (f'T_txv.{tag}.bulb', f'{pref}TXV Bulb Temp'),
    }
    return table.get(port)


def canonical_for_sensorbulb(props: Dict, port: str, unit_tag: str = '') -> Optional[Tuple[str, str]]:
    if port != 'measurement':
        return None
    label = props.get('circuit_label') or ''
    tag = unit_tag or _circuit_tag(label)
    human_pref = _circuit_human(label) or (unit_tag.upper() if unit_tag else '')
    if not tag:
        return None
    pref = f'{human_pref} ' if human_pref else ''
    return (f'T_txv.{tag}.bulb', f'{pref}TXV Bulb Temp')


def canonical_for_distributor(props: Dict, port: str, unit_tag: str = '') -> Optional[Tuple[str, str]]:
    label = props.get('circuit_label') or ''
    tag = unit_tag or _circuit_tag(label)
    human_pref = _circuit_human(label) or (unit_tag.upper() if unit_tag else '')
    if not tag:
        return None
    pref = f'{human_pref} ' if human_pref else ''
    if port == 'inlet':
        return (f'T_dist.{tag}.in', f'{pref}Distributor Inlet Temp')
    if port.startswith('outlet_'):
        idx = port.split('_')[-1]
        return (f'T_dist.{tag}.out.{idx}', f'{pref}Distributor Outlet {idx} Temp')
    return None


def canonical_for_evaporator(props: Dict, port: str, unit_tag: str = '') -> Optional[Tuple[str, str]]:
    label = props.get('circuit_label') or ''
    tag = unit_tag or _circuit_tag(label)
    human_pref = _circuit_human(label) or (unit_tag.upper() if unit_tag else '')
    if not tag:
        return None
    pref = f'{human_pref} ' if human_pref else ''
    if port.startswith('inlet_circuit_'):
        idx = port.split('_')[-1]
        return (f'T_coil.{tag}.in.{idx}', f'{pref}Coil Inlet {idx} Temp')
    if port.startswith('outlet_circuit_'):
        idx = port.split('_')[-1]
        return (f'T_coil.{tag}.out.{idx}', f'{pref}Coil Outlet {idx} Temp')
    if port == 'dist_inlet':
        return (f'T_coil.{tag}.dist.in', f'{pref}Coil Dist Inlet Temp')
    if port == 'dist_outlet':
        return (f'T_coil.{tag}.dist.out', f'{pref}Coil Dist Outlet Temp')
    return None


def canonical_for_air_array(props: Dict, port: str, unit_tag: str = '') -> Optional[Tuple[str, str]]:
    curtain = (props.get('curtain_type') or 'Primary').lower()
    curtain_short = {'primary': 'disc', 'secondary': 'sec', 'return': 'ret'}.get(curtain, curtain)
    curtain_human = {'primary': 'Primary Discharge Air',
                     'secondary': 'Secondary Air',
                     'return': 'Return Air'}.get(curtain, curtain.title() + ' Air')

    suf = f'.{unit_tag}' if unit_tag else ''
    suf_h = f' ({unit_tag.upper()})' if unit_tag else ''
    # port may be "1".."N" (legacy) or "sensor_1".."sensor_N"
    idx = port.split('_')[-1]
    return (f'T_air.{curtain_short}{suf}.s{idx}',
            f'{curtain_human}{suf_h} - Sensor {idx}')


def canonical_for_shelving(props: Dict, port: str, unit_tag: str = '') -> Optional[Tuple[str, str]]:
    """ShelvingGrid port names: 'sensor_r{row}_top_c{col}' or '_bottom_'."""
    import re
    m = re.match(r'^sensor_r(\d+)_(top|bottom)_c(\d+)$', port)
    if not m:
        return None
    row = int(m.group(1))
    pos = m.group(2)
    col = int(m.group(3))

    shelf_rows = int(props.get('shelf_rows', 6) or 6)
    shelving_type = props.get('shelving_type', 'Modular')
    if shelving_type == 'Modular':
        cols_total = int(props.get('module_count', 3) or 3) + 1
    else:
        cols_total = int(props.get('door_count', 3) or 3) + 1
    col_distances = props.get('col_distances')  # optional per-template override

    # Skip stale role_keys that reference ports beyond the shelving's actual size
    if row < 0 or row >= shelf_rows or col < 0 or col >= cols_total:
        return None

    row_id, row_h = shelf_row_name(row, shelf_rows)
    col_id, col_h = shelf_column_name(col, cols_total, col_distances)
    pos_id = 'r' if pos == 'top' else 'f'      # top edge = Rear, bottom = Front
    pos_h = 'Rear' if pos == 'top' else 'Front'

    suf = f'.{unit_tag}' if unit_tag else ''
    suf_h = f' ({unit_tag.upper()})' if unit_tag else ''
    return (f'T_prod{suf}.{row_id}.{col_id}.{pos_id}',
            f'Product Sim{suf_h} - {row_h} Shelf - {col_h} - {pos_h}')


def canonical_for_junction(props: Dict, port: str, unit_tag: str = '') -> Optional[Tuple[str, str]]:
    if port != 'sensor':
        return None
    label = props.get('circuit_label') or ''
    tag = unit_tag or _circuit_tag(label)
    if not tag:
        return None
    return (f'T_jct.{tag}', f'{_circuit_human(label)} Junction Temp'.strip())


def canonical_for_fan(props: Dict, port: str, unit_tag: str = '') -> Optional[Tuple[str, str]]:
    """Fan air-on / air-off sensors.

    Ports look like 'sensor_0', 'sensor_1', ... (0-indexed).  The Fan's
    air_flow_type ('Air Inlet' = air-in, 'Air Outlet' = air-off) and
    circuit_label drive the canonical role.
    """
    label = props.get('circuit_label') or ''
    tag = unit_tag or _circuit_tag(label)
    if not tag:
        return None
    flow = (props.get('air_flow_type') or 'Air Inlet').lower()
    side = 'in' if 'inlet' in flow else 'off'
    side_h = 'In' if side == 'in' else 'Off'
    # port "sensor_0" → idx 0
    try:
        idx = int(port.rsplit('_', 1)[-1])
    except ValueError:
        return None
    # Conventionally 0=LE, 1=RE for 2-sensor fans
    sensor_count = int(props.get('sensor_count', 2) or 2)
    if sensor_count == 2:
        slot = 'LE' if idx == 0 else 'RE'
        slot_h = slot
    else:
        slot = f's{idx + 1}'
        slot_h = f'Sensor {idx + 1}'
    return (f'T_air.fan_{side}.{tag}.{slot}',
            f'{_circuit_human(label)} Evap Fan Air {side_h} - {slot_h}'.strip())


# ── Master dispatch ─────────────────────────────────────────────────────────

_DISPATCH = {
    'Compressor':      canonical_for_compressor,
    'Condenser':       canonical_for_condenser,
    'TXV':             canonical_for_txv,
    'SensorBulb':      canonical_for_sensorbulb,
    'Distributor':     canonical_for_distributor,
    'SplitterManifold': canonical_for_distributor,
    'Evaporator':      canonical_for_evaporator,
    'AirSensorArray':  canonical_for_air_array,
    'PrimaryAir':      canonical_for_air_array,   # role_key alias
    'SecondaryAir':    canonical_for_air_array,   # role_key alias
    'ReturnAir':       canonical_for_air_array,   # role_key alias
    'ShelvingGrid':    canonical_for_shelving,
    'Junction':        canonical_for_junction,
    'Fan':             canonical_for_fan,
}


def canonical_for_port(comp_type: str, comp_props: Dict,
                       port: str, unit_tag: str = '') -> Optional[Tuple[str, str]]:
    """Master entry point: (canonical_id, human_label) or None if no mapping.

    unit_tag: optional cassette unit tag like 'u1', 'u2' — used when circuit_label
              isn't enough to disambiguate (e.g. multi-compressor cassette systems).
    """
    fn = _DISPATCH.get(comp_type)
    if fn is None:
        return None
    return fn(comp_props or {}, port, unit_tag)


def resolve_canonical_from_role_key(diagram_model: Dict, role_key: str,
                                    unit_tag: str = '') -> Optional[Tuple[str, str]]:
    """Take any role_key found in sensor_roles and produce its canonical pair.

    Handles all historical role_key shapes:
      - "Type.comp_id.port"     (current canonical shape)
      - "comp_id.port"          (legacy fallback shape)
      - "CurtainType.cid.idx"   (PrimaryAir / SecondaryAir / ReturnAir)
      - "sensorbox.sensor_xxx"  (off-diagram box sensors — uses box.sensors[].label)
      - "custom_xxx"            (computed sensors — skipped, returns None)
    """
    if not role_key:
        return None
    comps = diagram_model.get('components', {}) or {}
    boxes = diagram_model.get('sensor_boxes', {}) or {}

    # Custom / computed (no canonical equivalent — they're outputs not raw sensors)
    if role_key.startswith('custom_'):
        return None

    if role_key.startswith('calc.'):
        custom = (diagram_model.get('custom_sensors') or {}).get(role_key) or {}
        return (role_key, custom.get('label') or role_key)

    # Already a canonical ID (e.g. shelf dots generated by
    # build_bare_minimum_diagram use 'T_prod...' / 'T_air...' directly).  Look
    # up the human label from custom_sensors if available, else fall back to
    # the canonical itself.
    if _looks_like_canonical(role_key):
        custom = (diagram_model.get('custom_sensors') or {}).get(role_key) or {}
        return (role_key, custom.get('label') or role_key)

    parts = role_key.split('.')

    # Sensor-box sensor: "sensorbox.sensor_xxx" OR "boxid.sensor_xxx"
    if len(parts) == 2:
        head, tail = parts
        if tail.startswith('sensor_') or head == 'sensorbox':
            # Walk all boxes looking for this sensor id
            for box in boxes.values():
                for s in box.get('sensors', []) or []:
                    if s.get('id') == tail or s.get('id') == role_key:
                        label = s.get('label') or ''
                        return _canonical_from_box_label(label)
            return None
        # Legacy 2-part: "comp_id.port" — look up comp_type from comp_id
        comp = comps.get(head)
        if comp:
            ctype = comp.get('type')
            props = comp.get('properties', {}) or {}
            return canonical_for_port(ctype, props, tail, unit_tag)
        return None

    if len(parts) >= 3:
        ctype, cid = parts[0], parts[1]
        port = '.'.join(parts[2:])
        # Sensor-box 3-part: "sensorbox.{box_id}.{sensor_id}"
        if ctype.lower() == 'sensorbox':
            box = boxes.get(cid)
            if box:
                for s in box.get('sensors', []) or []:
                    if s.get('id') == port:
                        # New-style boxes use the canonical as the sensor id directly
                        if _looks_like_canonical(port):
                            return (port, s.get('label') or port)
                        return _canonical_from_box_label(s.get('label') or '')
            return None
        comp = comps.get(cid, {})
        props = comp.get('properties', {}) or {}
        return canonical_for_port(ctype, props, port, unit_tag)

    return None


# ── Sensor box: derive canonical from the user-set label ────────────────────

# Pattern-based mapping for off-diagram sensors (Ambient/Walls/Electrical).
# The "label" is what the engineer typed in for that slot — we normalize it
# to a canonical and human pair.
_BOX_LABEL_PATTERNS = [
    # (regex_normalized_substring, canonical, human)
    ('ambientdrybulbta',    'T_amb.dry.a',   'Ambient Dry Bulb A'),
    ('ambientdrybulba',     'T_amb.dry.a',   'Ambient Dry Bulb A'),
    ('ambientdrybulbtb',    'T_amb.dry.b',   'Ambient Dry Bulb B'),
    ('ambientdrybulbb',     'T_amb.dry.b',   'Ambient Dry Bulb B'),
    ('ambientwetbulb',      'T_amb.wet',     'Ambient Wet Bulb'),
    ('ambient',             'T_amb.dry.a',   'Ambient'),
    ('frontwall',           'T_wall.front',  'Front Wall Temp'),
    ('rearwall',            'T_wall.rear',   'Rear Wall Temp'),
    ('leftwall',            'T_wall.left',   'Left Wall Temp'),
    ('rightwall',           'T_wall.right',  'Right Wall Temp'),
    ('ceilingtemp',         'T_ceil',        'Ceiling Temp'),
    ('ceiling',             'T_ceil',        'Ceiling Temp'),
    ('totalcompressorwatts','W_comp.total',  'Total Compressor Watts'),
    ('totalcasewatts',      'W_case.total',  'Total Case Watts'),
    ('totalcaseamps',       'A_case.total',  'Total Case Amps'),
    ('totalcasevolts',      'V_case.total',  'Total Case Volts'),
    ('totalcompwatts',      'W_comp.total',  'Total Compressor Watts'),
    ('compressorwatts',     'W_comp',        'Compressor Watts'),
    ('compressoramps',      'A_comp',        'Compressor Amps'),
    ('compressorvolts',     'V_comp',        'Compressor Voltage'),
    ('compressorvoltage',   'V_comp',        'Compressor Voltage'),
    ('casewatts',           'W_case',        'Case Watts'),
    ('caseamps',            'A_case',        'Case Amps'),
    ('casevolts',           'V_case',        'Case Voltage'),
    ('casevoltage',         'V_case',        'Case Voltage'),
    ('totalevapfanwatts',   'W_fan.total',   'Total Evap Fan Watts'),
    ('evapfansamps',        'A_fan',         'Evap Fan Amps'),
    ('evapfanswatts',       'W_fan',         'Evap Fan Watts'),
    ('totalaswatts',        'W_aswt.total',  'Total Anti-Sweat Watts'),
    ('antisweatheatersamps','A_aswt',        'Anti-Sweat Heater Amps'),
    ('antisweatheaterswatts','W_aswt',       'Anti-Sweat Heater Watts'),
    ('frameheateramps',     'A_frame',       'Frame Heater Amps'),
    ('frameheaterwatts',    'W_frame',       'Frame Heater Watts'),
    ('totalframeheatwatts', 'W_frame.total', 'Total Frame Heater Watts'),
    ('runtime',             't_run',         'Run Time'),
    ('flowmeter',           'm_dot_meas',    'Flowmeter (Mass Flow)'),
    ('dischargepressure',   'P_disc',        'Discharge Pressure'),
    ('suctionpressure',     'P_suc',         'Suction Pressure'),
    ('defrost',             'f_defrost',     'Defrost Flag'),
    ('alwaysoff',           'f_alwaysoff',   'Always Off Flag'),
    ('evap',                'T_evap_misc',   'Misc Evap Temp'),
]


def _looks_like_canonical(s: str) -> bool:
    """A canonical ID starts with one of the known prefixes (T_, P_, W_, A_,
    V_, t_, f_, m_, gpm, rpm) and contains only safe characters."""
    if not s:
        return False
    import re
    return bool(re.match(r'^(T_|P_|W_|A_|V_|t_|f_|m_|gpm|rpm)[A-Za-z0-9._]*$', s))


def _canonical_from_box_label(label: str) -> Optional[Tuple[str, str]]:
    """Match a user-entered sensor box label to a canonical slot."""
    if not label:
        return None
    norm = normalize_for_match(label)
    import re

    if norm.startswith('ps'):
        row = None
        for pat, rid in [
            ('topshelf', 'top'), ('top', 'top'),
            ('secondshelf', 'r2'), ('2ndshelf', 'r2'),
            ('thirdshelf', 'r3'), ('3rdshelf', 'r3'),
            ('fourthshelf', 'r4'), ('4thshelf', 'r4'),
            ('fifthshelf', 'r5'), ('5thshelf', 'r5'),
            ('bcshelf', 'btm'), ('bcs', 'btm'), ('bc', 'btm'),
            ('btmshelf', 'btm'), ('bottomshelf', 'btm'),
        ]:
            if pat in norm:
                row = rid
                break
        pos = 'r' if norm.endswith('rear') else 'f' if norm.endswith('front') else None
        base_norm = re.sub(r'(rear|front)$', '', norm)
        col = None
        m = re.search(r'(\d+)(?:in)?(le|re)', base_norm)
        if m:
            col = f"{m.group(2).upper()}{m.group(1)}"
        elif 'center' in norm or 'centre' in norm:
            col = 'Ctr'
        elif base_norm.endswith('le'):
            col = 'LE'
        elif base_norm.endswith('re'):
            col = 'RE'
        if row and col and pos:
            return (f'T_prod.{row}.{col}.{pos}',
                    f'Product Sim - {row} - {col} - {"Rear" if pos == "r" else "Front"}')

    sh_aliases = {
        'leftsh': ('calc.SH.lh', 'Left Coil Superheat'),
        'lhsh': ('calc.SH.lh', 'Left Coil Superheat'),
        'ctrsh': ('calc.SH.ctr', 'Center Coil Superheat'),
        'centersh': ('calc.SH.ctr', 'Center Coil Superheat'),
        'rightsh': ('calc.SH.rh', 'Right Coil Superheat'),
        'rhsh': ('calc.SH.rh', 'Right Coil Superheat'),
    }
    compact = norm.replace('superheat', 'sh')
    compact = compact.replace('suctionheat', 'sh')
    if compact in sh_aliases:
        return sh_aliases[compact]
    if norm in {'liqcond', 'liquidcond', 'liquidcondenser', 'subcooling', 'subcool'}:
        return ('calc.SC_cond', 'Condenser Outlet Subcooling')

    m = re.match(r'^(?:u|unit)(\d+)txvbulb', norm) or re.match(r'^txvbulbtemp(?:u|unit)(\d+)$', norm)
    if m:
        tag = _unit_tag_from_number(m.group(1))
        return (f'T_txv.{tag}.bulb', f'{tag.upper()} TXV Bulb Temp')
    m = (
        re.match(r'^(?:u|unit)(\d+)txvinlet', norm)
        or re.match(r'^(?:tempinto|intotemp|temperatureinto)?txv(?:u|unit)(\d+)$', norm)
    )
    if m:
        tag = _unit_tag_from_number(m.group(1))
        return (f'T_txv.{tag}.in', f'{tag.upper()} TXV Inlet Temp')

    m = re.match(r'^suctiontempintocomp(?:u|unit)(\d+)$', norm)
    if m:
        tag = _unit_tag_from_number(m.group(1))
        return (f'T_suc.in.{tag}', f'Compressor Suction Inlet Temp ({tag.upper()})')
    m = re.match(r'^disch(?:arge)?tempoutofcomp(?:u|unit)(\d+)$', norm)
    if m:
        tag = _unit_tag_from_number(m.group(1))
        return (f'T_disc.out.{tag}', f'Compressor Discharge Outlet Temp ({tag.upper()})')
    m = re.match(r'^compdome(?:u|unit)(\d+)$', norm)
    if m:
        tag = _unit_tag_from_number(m.group(1))
        return (f'P_disc.{tag}', f'Discharge Pressure ({tag.upper()})')
    m = re.match(r'^compsump(?:u|unit)(\d+)$', norm)
    if m:
        tag = _unit_tag_from_number(m.group(1))
        return (f'P_suc.{tag}', f'Suction Pressure ({tag.upper()})')
    m = re.match(r'^condinlettemp(?:u|unit)(\d+)$', norm)
    if m:
        tag = _unit_tag_from_number(m.group(1))
        return (f'T_cond.in.{tag}', f'Condenser Refrigerant Inlet Temp ({tag.upper()})')
    m = re.match(r'^condoutlettemp(?:u|unit)(\d+)$', norm)
    if m:
        tag = _unit_tag_from_number(m.group(1))
        return (f'T_cond.out.{tag}', f'Condenser Refrigerant Outlet Temp ({tag.upper()})')

    m = re.match(r'^evapcoilinlet(\d+)temp(?:u|unit)(\d+)$', norm)
    if m:
        circuit, unit = m.groups()
        tag = _unit_tag_from_number(unit)
        return (f'T_coil.{tag}.in.{circuit}', f'{tag.upper()} Coil Inlet {circuit} Temp')
    m = re.match(r'^evapoutlet(\d+)temp(?:u|unit)(\d+)$', norm)
    if m:
        circuit, unit = m.groups()
        tag = _unit_tag_from_number(unit)
        return (f'T_coil.{tag}.out.{circuit}', f'{tag.upper()} Coil Outlet {circuit} Temp')

    m = re.match(r'^airinto(?:evap|evaporator)(left|right)(?:u|unit)(\d+)$', norm)
    if m:
        side, unit = m.groups()
        tag = _unit_tag_from_number(unit)
        slot = 'LE' if side == 'left' else 'RE'
        return (f'T_air.fan_in.{tag}.{slot}', f'Fan {tag.upper()} Air In - {slot}')
    m = re.match(r'^airoutof(?:evap|evaporator)(left|right)(?:u|unit)(\d+)$', norm)
    if m:
        side, unit = m.groups()
        tag = _unit_tag_from_number(unit)
        slot = 'LE' if side == 'left' else 'RE'
        return (f'T_air.fan_off.{tag}.{slot}', f'Fan {tag.upper()} Air Off - {slot}')
    m = re.match(r'^dischargeairsensor(?:u|unit)(\d+)$', norm)
    if m:
        tag = _unit_tag_from_number(m.group(1))
        return (f'T_air.fan_off.{tag}.avg', f'Discharge Air Sensor ({tag.upper()})')

    m = re.match(r'^airintocond(left|right)(?:u|unit)(\d+)$', norm)
    if m:
        side, unit = m.groups()
        tag = _unit_tag_from_number(unit)
        slot = 'LE' if side == 'left' else 'RE'
        return (f'T_air.cond_in.{tag}.{slot}', f'Condenser Air In ({tag.upper()} {slot})')
    m = re.match(r'^airoutofcond(left|right)(?:u|unit)(\d+)$', norm)
    if m:
        side, unit = m.groups()
        tag = _unit_tag_from_number(unit)
        slot = 'LE' if side == 'left' else 'RE'
        return (f'T_air.cond_out.{tag}.{slot}', f'Condenser Air Out ({tag.upper()} {slot})')
    m = re.match(r'^liquidlinesolenoidoutlet(?:u|unit)(\d+)$', norm)
    if m:
        tag = _unit_tag_from_number(m.group(1))
        return (f'T_lls.out.{tag}', f'Liquid Line Solenoid Outlet ({tag.upper()})')
    m = re.match(r'^hotgasdefrostsolenoidoutlet(?:u|unit)(\d+)$', norm)
    if m:
        tag = _unit_tag_from_number(m.group(1))
        return (f'T_hgs.out.{tag}', f'Hot Gas Defrost Solenoid Outlet ({tag.upper()})')
    m = re.match(r'^defrostterminationsensor(?:u|unit)(\d+)$', norm)
    if m:
        tag = _unit_tag_from_number(m.group(1))
        return (f'T_defrost.term.{tag}', f'Defrost Termination Sensor ({tag.upper()})')

    m = re.match(r'^(volts|amps|watts)(?:unit|u)(\d+)$', norm)
    if m:
        metric, unit = m.groups()
        prefix = {'volts': 'V', 'amps': 'A', 'watts': 'W'}[metric]
        return (f'{prefix}_comp.u{unit}', f'Compressor {unit} {metric.title()}')
    m = re.match(r'^totalunit(\d+)watts$', norm)
    if m:
        unit = m.group(1)
        return (f'W_comp.u{unit}', f'Compressor {unit} Watts')
    for pat, cid, human in _BOX_LABEL_PATTERNS:
        if pat in norm:
            return (cid, human)
    return None


# ── Sensor box canonical slots (off-diagram instruments) ────────────────────

AMBIENT_WALLS_SLOTS = [
    ('T_amb.dry.a',  'Ambient Dry Bulb A'),
    ('T_amb.dry.b',  'Ambient Dry Bulb B'),
    ('T_amb.wet',    'Ambient Wet Bulb'),
    ('T_wall.front', 'Front Wall Temp'),
    ('T_wall.rear',  'Rear Wall Temp'),
    ('T_wall.left',  'Left Wall Temp'),
    ('T_wall.right', 'Right Wall Temp'),
    ('T_ceil',       'Ceiling Temp'),
    ('T_evap_misc',  'Misc Evap Temp'),
]


def electrical_system_slots(n_compressors: int = 1) -> list:
    """Return canonical slots for the Electrical & System box.

    For cassette systems with multiple compressors, per-compressor electrical
    slots are emitted (W_comp.u1, W_comp.u2, ...).
    """
    base = [
        ('W_case.total', 'Total Case Watts'),
        ('A_case.total', 'Total Case Amps'),
        ('V_case.total', 'Total Case Volts'),
        ('W_fan.total',  'Total Evap Fan Watts'),
        ('W_aswt.total', 'Total Anti-Sweat Watts'),
        ('W_frame.total','Total Frame Heater Watts'),
        ('W_comp.total', 'Total Compressor Watts'),
        ('W_case',       'Case Total Watts'),
        ('A_case',       'Case Total Amps'),
        ('V_case',       'Case Voltage'),
        ('W_fan',        'Evap Fan Watts'),
        ('A_fan',        'Evap Fan Amps'),
        ('W_aswt',       'Anti-Sweat Heater Watts'),
        ('A_aswt',       'Anti-Sweat Heater Amps'),
        ('W_frame',      'Frame Heater Watts'),
        ('A_frame',      'Frame Heater Amps'),
        ('t_run',        'Run Time'),
        ('f_defrost',    'Defrost Flag'),
        ('f_alwaysoff',  'Always Off Flag'),
        ('m_dot_meas',   'Flowmeter (Mass Flow)'),
        ('T_liq.main',   'Main Liquid Line Temp (into main distributor)'),
    ]
    if n_compressors <= 1:
        base += [
            ('W_comp',   'Compressor Watts'),
            ('A_comp',   'Compressor Amps'),
            ('V_comp',   'Compressor Voltage'),
        ]
    else:
        for u in range(1, n_compressors + 1):
            tag = _unit_tag_from_number(str(u))
            base += [
                (f'W_comp.u{u}', f'Compressor {u} Watts'),
                (f'A_comp.u{u}', f'Compressor {u} Amps'),
                (f'V_comp.u{u}', f'Compressor {u} Voltage'),
                (f'T_lls.out.{tag}', f'Liquid Line Solenoid Outlet ({tag.upper()})'),
                (f'T_hgs.out.{tag}', f'Hot Gas Defrost Solenoid Outlet ({tag.upper()})'),
                (f'T_defrost.term.{tag}', f'Defrost Termination Sensor ({tag.upper()})'),
            ]
    return base


# ── Normalize a string for fuzzy alias matching ─────────────────────────────

def normalize_for_match(s: str) -> str:
    """Lowercase, strip whitespace, drop punctuation — used by alias DB lookup."""
    import re
    if s is None:
        return ''
    s = str(s).lower()
    # Pandas appends ".1", ".2", ... to duplicate headers. Treat those as
    # the same sensor label for alias matching; true sensor indices usually
    # appear before words like door/unit/circuit rather than as a final suffix.
    s = re.sub(r'\.\d+$', '', s)
    s = re.sub(r'\bdisch\b', 'discharge', s)
    s = re.sub(r'\bait\b', 'air', s)
    s = re.sub(r'\bpresure\b', 'pressure', s)
    s = re.sub(r'\bcondesner\b', 'condenser', s)
    s = re.sub(r'\bintlet\b', 'inlet', s)
    s = re.sub(r'\bback\s+wall\b', 'rear wall', s)
    s = re.sub(r'[\s_\-.()/,]+', '', s)
    return s.strip()
