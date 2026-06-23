"""
diagram_from_request.py

Phase 3 of TEST_REQUEST_PLAN.md: generate the process diagram from a test
request's topology — one click, nothing re-typed.

Strategy (per the user's verdict that algorithmic layout "doesn't understand
refrigeration positioning"): the templates ARE the user's own hand-built
diagrams, ingested from Lab viewer/2.0/Config into templates/tmpl_*.json
(see templates/index.json).  Generation = nearest-match template → patch
circuits / condenser type → hand back.  The output is their layout by
construction.  Module-count surgery on the 3-module reference happens only
when no template with the right module count exists; the procedural builders
are a last-resort fallback for system types with no template at all.

The returned model carries a transient '_generated_from' key naming the
template file actually used — callers pop it for display/logging before
loading the model into the session.
"""

from __future__ import annotations

import copy
import json
import os
from typing import Dict, List

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# Which circuit labels survive for a given module count (house convention:
# 2-module = Left + Right, per CLAUDE.md column configs)
_LABELS_FOR_COUNT = {1: ['Left'], 2: ['Left', 'Right'],
                     3: ['Left', 'Center', 'Right']}


def _load_template(name: str) -> dict:
    path = os.path.join(TEMPLATES_DIR, name)
    with open(path, encoding='utf-8') as f:
        return json.load(f)


_LABEL_NORMALIZE = {'lh': 'Left', 'left': 'Left',
                    'ctr': 'Center', 'center': 'Center',
                    'rh': 'Right', 'right': 'Right'}


def _comp_label(comp: dict):
    """Normalized circuit label — the hand-built diagrams mix conventions
    ('LH' on some components, 'Left' on others)."""
    lbl = (comp.get('properties') or {}).get('circuit_label')
    if lbl in (None, '', 'None'):
        return None
    return _LABEL_NORMALIZE.get(str(lbl).strip().lower(), lbl)


def _assign_unlabeled_to_modules(model: dict) -> Dict[str, str]:
    """Per-module items without a circuit_label (e.g. AirSensorArray) are
    assigned to the nearest evaporator by x distance.  Only types that occur
    once per module are assigned; shared items (Compressor, main Junction,
    shared Sensors) are left alone."""
    evap_x = {}
    for cid, c in model['components'].items():
        if c.get('type') == 'Evaporator' and _comp_label(c):
            evap_x[_comp_label(c)] = (c.get('position') or [0, 0])[0]
    if not evap_x:
        return {}

    # Count occurrences per type among unlabeled components
    by_type: Dict[str, List[str]] = {}
    for cid, c in model['components'].items():
        if _comp_label(c) is None:
            by_type.setdefault(c.get('type'), []).append(cid)

    n_modules = len(evap_x)
    assigned = {}
    for ctype, ids in by_type.items():
        if len(ids) != n_modules or ctype in ('Compressor', 'Condenser',
                                              'Junction', 'Sensor'):
            continue  # not a per-module pattern
        for cid in ids:
            cx = (model['components'][cid].get('position') or [0, 0])[0]
            label = min(evap_x, key=lambda lb: abs(evap_x[lb] - cx))
            assigned[cid] = label
    return assigned


def _best_shared_3module_file() -> str:
    """The richest 3-module shared template in the library — the reduction
    source.  (User verdict: the 2.0/Config diagrams are the good ones.)"""
    best, best_n = None, -1
    for meta in _template_index().values():
        if meta.get('system_type') == 'shared' and meta.get('modules') == 3 \
                and meta.get('components', 0) > best_n:
            best, best_n = meta['file'], meta.get('components', 0)
    return best or 'tmpl_ID5SL12.json'


def build_shared_from_template(topology: dict) -> dict:
    """Generate a shared-compressor diagram from the user's reference layout."""
    src_file = _best_shared_3module_file()
    model = copy.deepcopy(_load_template(src_file))
    modules = max(1, min(3, int(topology.get('modules', 3) or 3)))
    keep = set(_LABELS_FOR_COUNT[modules])

    extra_labels = _assign_unlabeled_to_modules(model)

    # ── 1. Remove components of dropped modules ─────────────────────────────
    drop_ids = set()
    for cid, c in model['components'].items():
        lbl = _comp_label(c) or extra_labels.get(cid)
        if lbl and lbl not in keep:
            drop_ids.add(cid)
    for cid in drop_ids:
        model['components'].pop(cid, None)

    # ── 2. Remove pipes touching dropped components ─────────────────────────
    model['pipes'] = {pid: p for pid, p in model['pipes'].items()
                      if p.get('start_component_id') not in drop_ids
                      and p.get('end_component_id') not in drop_ids}

    # ── 3. Close the layout gap left by removed modules ────────────────────
    # Shift everything right of the removed band leftward so the diagram
    # stays compact (only needed when 'Center' was removed but 'Right' kept).
    if modules == 2:
        tmpl = _load_template(src_file)
        ev = {_comp_label(c): c['position'][0]
              for c in tmpl['components'].values()
              if c.get('type') == 'Evaporator' and _comp_label(c)}
        if 'Center' in ev and 'Right' in ev and 'Left' in ev:
            dx = ev['Right'] - ev['Center']
            boundary = (ev['Center'] + ev['Left']) / 2 + (ev['Center'] - ev['Left']) / 2
            shifted = set()
            for cid, c in model['components'].items():
                pos = c.get('position') or [0, 0]
                if pos[0] > boundary:
                    c['position'] = [pos[0] - dx, pos[1]]
                    shifted.add(cid)
            for pid, p in model['pipes'].items():
                s_in = p.get('start_component_id') in shifted
                e_in = p.get('end_component_id') in shifted
                route = p.get('route') or []
                if s_in and e_in:
                    p['route'] = [[v[0] - dx, v[1]] for v in route]
                elif s_in or e_in:
                    p.pop('route', None)      # re-auto-route across the seam
                    p.pop('waypoints', None)

    # ── 4. Patch per-request parameters ─────────────────────────────────────
    circuits = int(topology.get('circuits_per_coil', 6) or 6)
    for c in model['components'].values():
        props = c.setdefault('properties', {})
        if c.get('type') == 'Evaporator':
            props['circuits'] = circuits
            props['fan_sensor_count'] = max(1, min(circuits,
                                                   props.get('fan_sensor_count', circuits)))
        if c.get('type') == 'Condenser':
            props['condenser_type'] = ('Water Cooled'
                                       if str(topology.get('condenser_cooling',
                                                           'Water')).lower().startswith('w')
                                       else 'Air Cooled')

    # ── 5. Fresh start for mappings ─────────────────────────────────────────
    model['sensor_roles'] = {}
    model['custom_sensors'] = {}
    model['role_dot_labels'] = {}
    model['_generated_from'] = f"{src_file} (reduced to {modules} module(s))"
    return model


def _template_index() -> dict:
    path = os.path.join(TEMPLATES_DIR, 'index.json')
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _pick_template(topo: dict):
    """Nearest-match over the library of the user's hand-built diagrams.
    Scoring: same system type is mandatory; then closest module count;
    then closest circuits-per-coil; then richer template wins."""
    system = (topo.get('system_type') or 'shared').lower()
    want_mod = int(topo.get('modules', 1) or 1)
    want_circ = int(topo.get('circuits_per_coil', 6) or 6)
    best, best_key = None, None
    for name, meta in _template_index().items():
        if meta.get('system_type') != system:
            continue
        key = (abs(meta.get('modules', 0) - want_mod),
               abs(meta.get('circuits_per_coil', 6) - want_circ),
               -meta.get('components', 0))
        if best_key is None or key < best_key:
            best, best_key = meta, key
    return best


def _patch_params(model: dict, topo: dict) -> None:
    """Apply the request's per-coil circuits and condenser cooling type."""
    circuits = int(topo.get('circuits_per_coil', 6) or 6)
    for c in model['components'].values():
        props = c.setdefault('properties', {})
        if c.get('type') == 'Evaporator':
            props['circuits'] = circuits
        if c.get('type') == 'Condenser':
            props['condenser_type'] = ('Water Cooled'
                                       if str(topo.get('condenser_cooling', 'Water'))
                                       .lower().startswith('w')
                                       else 'Air Cooled')
    model['sensor_roles'] = {}
    model['custom_sensors'] = {}
    model['role_dot_labels'] = {}
    


def build_diagram_for_request(request: dict) -> dict:
    """Entry point: nearest hand-built template, patched to the request.

    The layouts are the user's own finished diagrams (ingested from
    Lab viewer/2.0/Config + the ID6SU12WE session), so generated output is
    'their layout' by construction.  Module-count surgery is used only when
    no template with the right module count exists.
    """
    topo = request.get('topology', {}) or {}
    want_mod = max(1, int(topo.get('modules', 1) or 1))

    meta = _pick_template(topo)
    if meta is None:
        # No template for this system type at all — old procedural fallback
        from diagram_templates import build_diagram_from_config
        print("[DIAGRAM GEN] No template for system type "
              f"{topo.get('system_type')!r} — procedural fallback")
        model = build_diagram_from_config({
            'case_type': 'modular_self_contained', 'case_size': '12 ft',
            'circuits_per_module': int(topo.get('circuits_per_coil', 6) or 6),
            'condenser_type': 'Water Cooled', 'expansion_type': 'TXV',
            'include_filter_dryer': False, 'include_hot_gas_bypass': False,
            'air_curtain_type': 'single', 'shelf_rows': 4,
        })
        model['_generated_from'] = 'procedural fallback (no template)'
        return model

    if meta.get('modules') == want_mod or meta.get('system_type') == 'cassette':
        model = copy.deepcopy(_load_template(meta['file']))
        _patch_params(model, topo)
        _ensure_canonical_sensor_boxes(model, topo)
        model['_generated_from'] = (f"{meta['file']} "
                                    f"(source {meta.get('source')})")
        print(f"[DIAGRAM GEN] Used template {meta['file']} "
              f"(exact module match, source {meta.get('source')})")
        return model

    # Module-count mismatch on a shared system: surgical reduction of the
    # 3-module reference (only path that needs surgery)
    print(f"[DIAGRAM GEN] No exact template for {want_mod} module(s) — "
          f"reducing the 3-module reference")
    model = build_shared_from_template(topo)
    _ensure_canonical_sensor_boxes(model, topo)
    return model


def _ensure_canonical_sensor_boxes(model: dict, topo: dict, anchor_y: float | None = None,
                                   anchor_x: float | None = None) -> None:
    """Auto-add two canonical sensor boxes (Ambient & Walls, Electrical & System)
    so off-diagram instruments have a home on every generated diagram.

    The sensors are added with canonical IDs as their sensor ids — no UUIDs —
    so role_keys are deterministic and the alias DB lights up immediately.

    Safe to call repeatedly: if a box with the same id already exists, leaves
    it alone.
    """
    from sensor_canonical import AMBIENT_WALLS_SLOTS, _unit_tag_from_number

    boxes = model.setdefault('sensor_boxes', {})

    n_compressors = sum(1 for c in (model.get('components') or {}).values()
                        if c.get('type') == 'Compressor')

    if anchor_y is None:
        try:
            bottoms = [
                (c.get('position') or [0, 0])[1] + (c.get('size') or {}).get('height', 0)
                for c in (model.get('components') or {}).values()
            ]
            anchor_y = (max(bottoms) if bottoms else 100) + 70
        except Exception:
            anchor_y = 100
    if anchor_x is None:
        try:
            anchor_x = min((c.get('position') or [0, 0])[0]
                           for c in (model.get('components') or {}).values()) - 20
        except Exception:
            anchor_x = 0

    box_gap = 390
    if 'box_ambient_walls' not in boxes:
        boxes['box_ambient_walls'] = {
            'position': [anchor_x, anchor_y],
            'title': 'Ambient & Walls',
            'sensors': [{'id': cid, 'label': human}
                        for cid, human in AMBIENT_WALLS_SLOTS],
        }

    case_slots = [
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
        ('T_liq.main',   'Main Liquid Line Temp'),
    ]

    if 'box_electrical_system' not in boxes:
        boxes['box_electrical_system'] = {
            'position': [anchor_x + box_gap, anchor_y],
            'title': 'Case Electrical & System',
            'sensors': [{'id': cid, 'label': human} for cid, human in case_slots],
        }
    if n_compressors <= 1:
        if 'box_unit_1_aux' not in boxes:
            boxes['box_unit_1_aux'] = {
                'position': [anchor_x + box_gap * 2, anchor_y],
                'title': 'Compressor Aux',
                'sensors': [
                    {'id': 'W_comp', 'label': 'Compressor Watts'},
                    {'id': 'A_comp', 'label': 'Compressor Amps'},
                    {'id': 'V_comp', 'label': 'Compressor Voltage'},
                ],
            }
    else:
        for u in range(1, n_compressors + 1):
            tag = _unit_tag_from_number(str(u))
            bid = f'box_unit_{u}_aux'
            if bid in boxes:
                continue
            boxes[bid] = {
                'position': [anchor_x + box_gap * (u + 1), anchor_y],
                'title': f'Unit {u} Electrical & Aux',
                'sensors': [
                    {'id': f'W_comp.u{u}', 'label': f'Unit {u} Watts'},
                    {'id': f'A_comp.u{u}', 'label': f'Unit {u} Amps'},
                    {'id': f'V_comp.u{u}', 'label': f'Unit {u} Voltage'},
                    {'id': f'T_lls.out.{tag}', 'label': 'Liquid Line Solenoid Outlet'},
                    {'id': f'T_hgs.out.{tag}', 'label': 'Hot Gas Defrost Solenoid Outlet'},
                    {'id': f'T_defrost.term.{tag}', 'label': 'Defrost Termination Sensor'},
                ],
            }

def build_bare_minimum_diagram(request: dict) -> dict:
    """Build a clean process diagram matching test_loop.py exactly.

    Supports: modular (1-3 modules), door (1-5 doors),
              cassette_mt (independent loop per cassette),
              cassette_lt (independent loop with HGBV/HGS/LLS per cassette).
    """
    topo = request.get('topology', {}) or {}
    mode       = topo.get('mode', 'modular')
    num_doors  = max(1, min(5, int(topo.get('num_doors', 3) or 3)))
    num_raw    = max(1, min(5, int(topo.get('num_cassettes', 1) or 1)))  # raw 1-5 count
    case_type  = topo.get('case_type', 'Doored')
    shelf_rows = max(3, min(8, int(topo.get('shelf_rows', 6) or 6)))
    num_circuits = max(1, int(topo.get('circuits_per_coil', 6) or 6))
    condenser_type = ('Water Cooled'
                      if str(topo.get('condenser_cooling', 'Water')).lower().startswith('w')
                      else 'Air Cooled')
    is_cassette = mode.startswith('cassette')
    if is_cassette:
        case_type = 'Doored'

    CENTER_X    = 600
    MOD_SPACING = 300
    COMP_W, COMP_H = 120, 60
    COND_W, COND_H = 120, 60
    TXV_W, TXV_H   = 120, 60
    EVAP_W  = 240
    EVAP_H  = 80
    DIST_H  = 40
    HEAD_H  = 40

    Y_COMP     = 100
    Y_COND     = 190
    Y_TXV      = 350
    Y_EVAP     = 495
    BRANCH_Y   = Y_COND + COND_H + 30    # 280
    DIST_Y     = Y_EVAP - DIST_H - 15    # 440
    HEAD_Y     = Y_EVAP + EVAP_H         # 575
    HEAD_OUT_Y = HEAD_Y + HEAD_H          # 615
    MERGE_Y    = Y_EVAP + EVAP_H + 85    # 660

    # ── Module layout (modular mode) ─────────────────────────────────────
    num_modules = max(1, min(3, int(topo.get('modules', 1) or 1)))
    if mode == 'modular':
        if num_modules == 1:
            mod_xs  = [CENTER_X];  mod_lbs = ['Left']
        elif num_modules == 2:
            mod_xs  = [CENTER_X - MOD_SPACING // 2, CENTER_X + MOD_SPACING // 2]
            mod_lbs = ['Left', 'Right']
        else:
            mod_xs  = [CENTER_X - MOD_SPACING, CENTER_X, CENTER_X + MOD_SPACING]
            mod_lbs = ['Left', 'Center', 'Right']
    else:
        mod_xs = [CENTER_X]; mod_lbs = ['Left']

    # ── Case-width geometry (matching test_loop.py) ───────────────────────
    if mode == 'modular':
        total_w    = num_modules * EVAP_W + (num_modules - 1) * (MOD_SPACING - EVAP_W)
        left_edge  = mod_xs[0] - EVAP_W / 2
        right_edge = mod_xs[-1] + EVAP_W / 2
        combined_w = total_w
        count = num_modules
    else:  # door or cassette
        count = num_doors
        cassette_process_w = (520 * num_raw) if is_cassette else 0
        total_w    = max(240 * count, cassette_process_w)
        left_edge  = CENTER_X - total_w / 2
        right_edge = CENTER_X + total_w / 2
        combined_w = total_w

    process_x = left_edge - 200
    process_w = combined_w + 300
    LEFTMOST  = left_edge - 100

    components: dict = {}
    pipes:      dict = {}

    # ══════════════════════════════════════════════════════════════════════
    #  NON-CASSETTE: Modular / Door — one shared compressor + condenser
    # ══════════════════════════════════════════════════════════════════════
    if not is_cassette:
        # Non-modular doored: the evap coil is one continuous coil spanning
        # the full door section.  Modular: each module has its own EVAP_W.
        mod_evap_w = combined_w if mode == 'door' else EVAP_W
        ckt_spacing = (mod_evap_w / (num_circuits - 1)) if num_circuits > 1 else mod_evap_w

        # Shared compressor
        components['comp'] = {
            'type': 'Compressor',
            'position': [CENTER_X - COMP_W // 2, Y_COMP],
            'size': {'width': COMP_W, 'height': COMP_H},
            'properties': {'circuit_label': 'None'},
        }
        # Shared condenser
        components['cond'] = {
            'type': 'Condenser',
            'position': [CENTER_X - COND_W // 2, Y_COND],
            'size': {'width': COND_W, 'height': COND_H},
            'properties': {'circuit_label': 'None', 'condenser_type': condenser_type},
        }
        pipes['p_comp_cond'] = {
            'start_component_id': 'comp', 'start_port': 'outlet',
            'end_component_id':   'cond', 'end_port':   'inlet',
            'route': [[CENTER_X, Y_COMP + COMP_H], [CENTER_X, Y_COND]],
        }
        cond_out_y = Y_COND + COND_H

        # Multi-module suction junction
        if num_modules > 1:
            multi_w    = (num_modules - 1) * MOD_SPACING + EVAP_W
            multi_left = CENTER_X - multi_w // 2
            components['multi_suct'] = {
                'type': 'Junction',
                'position': [multi_left, MERGE_Y],
                'size': {'width': multi_w, 'height': 1},
                'properties': {
                    'inlet_count': 1, 'outlet_count': 1,
                    'port_spacing': 20, 'snapped_mode': 'Yes',
                    'circuit_label': 'None',
                },
            }

        for mod_x, lb in zip(mod_xs, mod_lbs):
            cl    = lb if lb else 'None'
            pfx   = lb.lower().replace(' ', '_') + '_' if lb else ''
            el    = mod_x - mod_evap_w // 2
            txv_id  = f'{pfx}txv';  dist_id = f'{pfx}dist'
            evap_id = f'{pfx}evap'; head_id  = f'{pfx}head'

            components[txv_id] = {
                'type': 'TXV',
                'position': [mod_x - TXV_W // 2, Y_TXV],
                'size': {'width': TXV_W, 'height': TXV_H},
                'properties': {'circuit_label': cl},
            }
            components[dist_id] = {
                'type': 'SplitterManifold',
                'position': [el, DIST_Y],
                'size': {'width': mod_evap_w, 'height': DIST_H},
                'properties': {'circuits': num_circuits, 'circuit_label': cl},
            }
            components[evap_id] = {
                'type': 'Evaporator',
                'position': [el, Y_EVAP],
                'size': {'width': mod_evap_w, 'height': EVAP_H},
                'properties': {
                    'circuits': num_circuits,
                    'port_spacing': ckt_spacing,
                    'circuit_label': cl,
                },
            }
            components[head_id] = {
                'type': 'CombinerManifold',
                'position': [el, HEAD_Y],
                'size': {'width': mod_evap_w, 'height': HEAD_H},
                'properties': {'circuits': num_circuits, 'circuit_label': cl},
            }
            # cond → TXV
            pipes[f'p_cond_{txv_id}'] = {
                'start_component_id': 'cond', 'start_port': 'outlet',
                'end_component_id':   txv_id, 'end_port':   'inlet',
                'route': [[CENTER_X, cond_out_y],
                          [CENTER_X, BRANCH_Y], [mod_x, BRANCH_Y], [mod_x, Y_TXV]],
            }
            # TXV → distributor
            txv_out_y = Y_TXV + TXV_H
            if txv_out_y < DIST_Y:
                pipes[f'p_{txv_id}_{dist_id}'] = {
                    'start_component_id': txv_id,  'start_port': 'outlet',
                    'end_component_id':   dist_id, 'end_port':   'inlet',
                    'route': [[mod_x, txv_out_y], [mod_x, DIST_Y]],
                }
            # header → suction collector
            if num_modules == 1:
                pipes['p_loopback'] = {
                    'start_component_id': head_id, 'start_port': 'outlet',
                    'end_component_id':   'comp',  'end_port':   'inlet',
                    'route': [[mod_x,    HEAD_OUT_Y],
                              [mod_x,    MERGE_Y],
                              [LEFTMOST, MERGE_Y],
                              [LEFTMOST, Y_COMP - 30],
                              [CENTER_X, Y_COMP - 30],
                              [CENTER_X, Y_COMP]],
                }
            else:
                pipes[f'p_{head_id}_multi'] = {
                    'start_component_id': head_id,       'start_port': 'outlet',
                    'end_component_id':   'multi_suct',  'end_port':   'inlet_1',
                    'route': [[mod_x, HEAD_OUT_Y], [mod_x, MERGE_Y], [CENTER_X, MERGE_Y]],
                }

        if num_modules > 1:
            pipes['p_loopback'] = {
                'start_component_id': 'multi_suct', 'start_port': 'outlet_1',
                'end_component_id':   'comp',        'end_port':   'inlet',
                'route': [[CENTER_X, MERGE_Y],
                          [CENTER_X, MERGE_Y + 30],
                          [LEFTMOST, MERGE_Y + 30],
                          [LEFTMOST, Y_COMP - 30],
                          [CENTER_X, Y_COMP - 30],
                          [CENTER_X, Y_COMP]],
            }

        # Overall boundary
        proc_y = Y_COMP - 50
        components['bnd_process'] = {
            'type': 'Boundary',
            'position': [process_x, proc_y],
            'size': {'width': process_w, 'height': MERGE_Y - proc_y + 80},
            'properties': {'label': 'Refrigeration Process', 'stroke_color': '#AAAAAA'},
        }

    # ══════════════════════════════════════════════════════════════════════
    #  CASSETTE MODES — independent refrigerant loop per cassette
    # ══════════════════════════════════════════════════════════════════════
    else:
        num_cass = num_raw
        if num_cass == 1:
            cas_lbs = ['']
        elif num_cass == 2:
            cas_lbs = ['LH', 'RH']
        elif num_cass == 3:
            cas_lbs = ['LH', 'CTR', 'RH']
        else:
            cas_lbs = [f'U{i + 1}' for i in range(num_cass)]

        cas_slice_w = combined_w / num_cass
        cas_evap_w  = max(220, min(300, cas_slice_w * 0.55))
        cas_ckt_spacing = (cas_evap_w / (num_circuits - 1)
                           if num_circuits > 1 else cas_evap_w)
        cas_xs = [left_edge + cas_slice_w / 2 + i * cas_slice_w for i in range(num_cass)]
        global_merge_y = MERGE_Y

        for ci, (cx, lb) in enumerate(zip(cas_xs, cas_lbs)):
            cl  = lb if lb else 'None'
            pfx = f'c{ci}_'
            LEFTMOST_CAS = cx - max(cas_evap_w / 2 + 40,
                                    100 if mode == 'cassette_mt' else 180)

            # Compressor (per cassette)
            components[f'{pfx}comp'] = {
                'type': 'Compressor',
                'position': [cx - COMP_W // 2, Y_COMP],
                'size': {'width': COMP_W, 'height': COMP_H},
                'properties': {'circuit_label': cl},
            }

            if mode == 'cassette_mt':
                # ── Cassette MT: simple independent loop ────────────────
                components[f'{pfx}cond'] = {
                    'type': 'Condenser',
                    'position': [cx - COND_W // 2, Y_COND],
                    'size': {'width': COND_W, 'height': COND_H},
                    'properties': {'circuit_label': cl, 'condenser_type': condenser_type},
                }
                components[f'{pfx}txv'] = {
                    'type': 'TXV',
                    'position': [cx - TXV_W // 2, Y_TXV],
                    'size': {'width': TXV_W, 'height': TXV_H},
                    'properties': {'circuit_label': cl},
                }
                components[f'{pfx}dist'] = {
                    'type': 'SplitterManifold',
                    'position': [cx - cas_evap_w // 2, DIST_Y],
                    'size': {'width': cas_evap_w, 'height': DIST_H},
                    'properties': {'circuits': num_circuits, 'circuit_label': cl},
                }
                components[f'{pfx}evap'] = {
                    'type': 'Evaporator',
                    'position': [cx - cas_evap_w // 2, Y_EVAP],
                    'size': {'width': cas_evap_w, 'height': EVAP_H},
                    'properties': {
                        'circuits': num_circuits,
                        'port_spacing': cas_ckt_spacing,
                        'circuit_label': cl,
                    },
                }
                components[f'{pfx}head'] = {
                    'type': 'CombinerManifold',
                    'position': [cx - cas_evap_w // 2, HEAD_Y],
                    'size': {'width': cas_evap_w, 'height': HEAD_H},
                    'properties': {'circuits': num_circuits, 'circuit_label': cl},
                }
                # comp → cond → txv → dist (all vertical through center cx)
                pipes[f'{pfx}p_comp_cond'] = {
                    'start_component_id': f'{pfx}comp', 'start_port': 'outlet',
                    'end_component_id':   f'{pfx}cond', 'end_port':   'inlet',
                    'route': [[cx, Y_COMP + COMP_H], [cx, Y_COND]],
                }
                pipes[f'{pfx}p_cond_txv'] = {
                    'start_component_id': f'{pfx}cond', 'start_port': 'outlet',
                    'end_component_id':   f'{pfx}txv',  'end_port':   'inlet',
                    'route': [[cx, Y_COND + COND_H], [cx, Y_TXV]],
                }
                pipes[f'{pfx}p_txv_dist'] = {
                    'start_component_id': f'{pfx}txv',  'start_port': 'outlet',
                    'end_component_id':   f'{pfx}dist', 'end_port':   'inlet',
                    'route': [[cx, Y_TXV + TXV_H], [cx, DIST_Y]],
                }
                for circuit_idx in range(1, num_circuits + 1):
                    px = (cx if num_circuits == 1 else
                          (cx - cas_evap_w / 2)
                          + (circuit_idx - 1) * cas_ckt_spacing)
                    pipes[f'{pfx}p_dist_evap_{circuit_idx}'] = {
                        'start_component_id': f'{pfx}dist',
                        'start_port': f'outlet_{circuit_idx}',
                        'end_component_id': f'{pfx}evap',
                        'end_port': f'inlet_circuit_{circuit_idx}',
                        'route': [[px, DIST_Y + DIST_H], [px, Y_EVAP]],
                    }
                    pipes[f'{pfx}p_evap_head_{circuit_idx}'] = {
                        'start_component_id': f'{pfx}evap',
                        'start_port': f'outlet_circuit_{circuit_idx}',
                        'end_component_id': f'{pfx}head',
                        'end_port': f'inlet_{circuit_idx}',
                        'route': [[px, Y_EVAP + EVAP_H], [px, HEAD_Y]],
                    }
                # loopback: head → merge_y → LEFTMOST_CAS → comp inlet
                pipes[f'{pfx}p_loopback'] = {
                    'start_component_id': f'{pfx}head', 'start_port': 'outlet',
                    'end_component_id':   f'{pfx}comp', 'end_port':   'inlet',
                    'route': [[cx, HEAD_OUT_Y],
                              [cx, global_merge_y],
                              [LEFTMOST_CAS, global_merge_y],
                              [LEFTMOST_CAS, Y_COMP - 20],
                              [cx, Y_COMP - 20],
                              [cx, Y_COMP]],
                }
                bound_left  = cx - cas_evap_w / 2 - 60
                bound_width = (cx + cas_evap_w / 2 + 60) - bound_left

            else:  # cassette_lt
                # ── Cassette LT: hot gas bypass / solenoid / liquid solenoid
                sol_y    = Y_COND + COND_H + 36
                main_x   = cx + min(70, cas_slice_w * 0.16)
                hot_x    = cx - min(160, cas_slice_w * 0.36)
                hgb_w    = 100
                hgb_h    = 50
                hot_cx   = hot_x + hgb_w / 2

                # HGBV — Hot Gas Bypass Valve
                components[f'{pfx}hgbv'] = {
                    'type': 'LabeledBox',
                    'position': [hot_x, Y_COND],
                    'size': {'width': hgb_w, 'height': hgb_h},
                    'properties': {'label': 'Hot Gas\nBypass', 'circuit_label': cl},
                }
                # HGS — Hot Gas Solenoid
                components[f'{pfx}hgs'] = {
                    'type': 'LabeledBox',
                    'position': [hot_x, sol_y],
                    'size': {'width': hgb_w, 'height': hgb_h},
                    'properties': {'label': 'Hot Gas\nSolenoid', 'circuit_label': cl},
                }
                # Condenser
                components[f'{pfx}cond'] = {
                    'type': 'Condenser',
                    'position': [main_x - COND_W // 2, Y_COND],
                    'size': {'width': COND_W, 'height': COND_H},
                    'properties': {'circuit_label': cl, 'condenser_type': condenser_type},
                }
                # LLS — Liquid Line Solenoid
                components[f'{pfx}lls'] = {
                    'type': 'LabeledBox',
                    'position': [main_x - COND_W // 2, sol_y],
                    'size': {'width': COND_W, 'height': 40},
                    'properties': {'label': 'Liquid Line\nSolenoid', 'circuit_label': cl},
                }
                # TXV
                components[f'{pfx}txv'] = {
                    'type': 'TXV',
                    'position': [main_x - TXV_W // 2, Y_TXV],
                    'size': {'width': TXV_W, 'height': TXV_H},
                    'properties': {'circuit_label': cl},
                }
                # Distributor / evap / header use the requested circuit count.
                components[f'{pfx}dist'] = {
                    'type': 'SplitterManifold',
                    'position': [main_x - cas_evap_w // 2, DIST_Y],
                    'size': {'width': cas_evap_w, 'height': DIST_H},
                    'properties': {'circuits': num_circuits, 'circuit_label': cl},
                }
                components[f'{pfx}evap'] = {
                    'type': 'Evaporator',
                    'position': [main_x - cas_evap_w // 2, Y_EVAP],
                    'size': {'width': cas_evap_w, 'height': EVAP_H},
                    'properties': {
                        'circuits': num_circuits,
                        'port_spacing': cas_ckt_spacing,
                        'circuit_label': cl,
                    },
                }
                components[f'{pfx}head'] = {
                    'type': 'CombinerManifold',
                    'position': [main_x - cas_evap_w // 2, HEAD_Y],
                    'size': {'width': cas_evap_w, 'height': HEAD_H},
                    'properties': {'circuits': num_circuits, 'circuit_label': cl},
                }

                split_y    = Y_COMP + COMP_H + 22
                hgbv_out_y = Y_COND + hgb_h
                hgs_in_y   = sol_y
                hgs_out_y  = sol_y + hgb_h
                asc_y      = DIST_Y - 34

                # comp → split junction via straight vertical
                # (two branches from same comp outlet)
                pipes[f'{pfx}p_comp_hgbv'] = {
                    'start_component_id': f'{pfx}comp', 'start_port': 'outlet',
                    'end_component_id':   f'{pfx}hgbv', 'end_port':   'inlet',
                    'route': [[cx, Y_COMP + COMP_H],
                              [cx, split_y],
                              [hot_cx, split_y],
                              [hot_cx, Y_COND]],
                }
                pipes[f'{pfx}p_comp_cond'] = {
                    'start_component_id': f'{pfx}comp', 'start_port': 'outlet',
                    'end_component_id':   f'{pfx}cond', 'end_port':   'inlet',
                    'route': [[cx, Y_COMP + COMP_H],
                              [cx, split_y],
                              [main_x, split_y],
                              [main_x, Y_COND]],
                }
                pipes[f'{pfx}p_hgbv_hgs'] = {
                    'start_component_id': f'{pfx}hgbv', 'start_port': 'outlet',
                    'end_component_id':   f'{pfx}hgs',  'end_port':   'inlet',
                    'route': [[hot_cx, hgbv_out_y], [hot_cx, hgs_in_y]],
                }
                pipes[f'{pfx}p_cond_lls'] = {
                    'start_component_id': f'{pfx}cond', 'start_port': 'outlet',
                    'end_component_id':   f'{pfx}lls',  'end_port':   'inlet',
                    'route': [[main_x, Y_COND + COND_H], [main_x, sol_y]],
                }
                pipes[f'{pfx}p_lls_txv'] = {
                    'start_component_id': f'{pfx}lls', 'start_port': 'outlet',
                    'end_component_id':   f'{pfx}txv', 'end_port':   'inlet',
                    'route': [[main_x, sol_y + 40], [main_x, Y_TXV]],
                }
                pipes[f'{pfx}p_txv_dist'] = {
                    'start_component_id': f'{pfx}txv',  'start_port': 'outlet',
                    'end_component_id':   f'{pfx}dist', 'end_port':   'inlet',
                    'route': [[main_x, Y_TXV + TXV_H], [main_x, DIST_Y]],
                }
                # HGS → ASC merge point (into suction/liquid header)
                pipes[f'{pfx}p_hgs_asc'] = {
                    'start_component_id': f'{pfx}hgs',  'start_port': 'outlet',
                    'end_component_id':   f'{pfx}dist', 'end_port':   'inlet',
                    'route': [[hot_cx, hgs_out_y],
                              [hot_cx, asc_y],
                              [main_x, asc_y],
                              [main_x, DIST_Y]],
                }
                for circuit_idx in range(1, num_circuits + 1):
                    px = (main_x if num_circuits == 1 else
                          (main_x - cas_evap_w / 2)
                          + (circuit_idx - 1) * cas_ckt_spacing)
                    pipes[f'{pfx}p_dist_evap_{circuit_idx}'] = {
                        'start_component_id': f'{pfx}dist',
                        'start_port': f'outlet_{circuit_idx}',
                        'end_component_id': f'{pfx}evap',
                        'end_port': f'inlet_circuit_{circuit_idx}',
                        'route': [[px, DIST_Y + DIST_H], [px, Y_EVAP]],
                    }
                    pipes[f'{pfx}p_evap_head_{circuit_idx}'] = {
                        'start_component_id': f'{pfx}evap',
                        'start_port': f'outlet_circuit_{circuit_idx}',
                        'end_component_id': f'{pfx}head',
                        'end_port': f'inlet_{circuit_idx}',
                        'route': [[px, Y_EVAP + EVAP_H], [px, HEAD_Y]],
                    }
                # loopback
                pipes[f'{pfx}p_loopback'] = {
                    'start_component_id': f'{pfx}head', 'start_port': 'outlet',
                    'end_component_id':   f'{pfx}comp', 'end_port':   'inlet',
                    'route': [[main_x, HEAD_OUT_Y],
                              [main_x, global_merge_y],
                              [LEFTMOST_CAS, global_merge_y],
                              [LEFTMOST_CAS, Y_COMP - 20],
                              [cx, Y_COMP - 20],
                              [cx, Y_COMP]],
                }
                bound_left  = min(hot_x - 40, main_x - cas_evap_w / 2 - 60)
                bound_right = max(main_x + cas_evap_w / 2 + 60, cx + COMP_W / 2 + 40)
                bound_width = bound_right - bound_left

            # Per-cassette boundary
            components[f'{pfx}bnd_proc'] = {
                'type': 'Boundary',
                'position': [bound_left, Y_COMP - 40],
                'size': {'width': bound_width, 'height': global_merge_y - Y_COMP + 40},
                'properties': {
                    'label': (f'Refrigeration Process [{lb} Cassette]'
                              if lb else 'Refrigeration Process'),
                    'stroke_color': '#AAAAAA',
                },
            }

    # ══════════════════════════════════════════════════════════════════════
    #  AIRFLOW DIAGRAM  (matching test_loop.py ordering)
    # ══════════════════════════════════════════════════════════════════════
    base_y   = MERGE_Y + 100
    fan_size = 60
    # Vertical clearance between an airflow band and the fan box.  Fan
    # inlet/outlet sensor dots sit 14px outside the fan rectangle, so we
    # need at least ~30px so those dots don't land inside the colored band.
    fan_gap  = 35
    band_h   = 30

    if is_cassette:
        # Reversed: Return Air → fans → Primary Discharge Air
        ret_air_y = base_y
        fan_y     = ret_air_y + band_h + fan_gap
        pri_air_y = fan_y + fan_size + fan_gap
        air_bottom_y = pri_air_y
        arr_dir_above = 'down'; arr_dir_below = 'down'
        components['deco_ret_air'] = {
            'type': 'DecorativeRect',
            'position': [left_edge, ret_air_y],
            'size': {'width': combined_w, 'height': 30},
            'properties': {'bg_color': '#FFCDD2', 'label': 'Return Air'},
        }
        components['deco_pri_air'] = {
            'type': 'DecorativeRect',
            'position': [left_edge, pri_air_y],
            'size': {'width': combined_w, 'height': 30},
            'properties': {'bg_color': '#B3E5FC', 'label': 'Primary Discharge Air'},
        }
    else:
        # Normal: Primary → (Secondary modular-only) → fans → Return Air
        pri_air_y = base_y
        components['deco_pri_air'] = {
            'type': 'DecorativeRect',
            'position': [left_edge, pri_air_y],
            'size': {'width': combined_w, 'height': 30},
            'properties': {'bg_color': '#B3E5FC', 'label': 'Primary Discharge Air'},
        }
        if mode == 'modular':
            sec_air_y = pri_air_y + band_h + 10
            components['deco_sec_air'] = {
                'type': 'DecorativeRect',
                'position': [left_edge, sec_air_y],
                'size': {'width': combined_w, 'height': band_h},
                'properties': {'bg_color': '#FFF9C4', 'label': 'Secondary Discharge Air'},
            }
            fan_y = sec_air_y + band_h + fan_gap
        else:
            fan_y = pri_air_y + band_h + fan_gap

        ret_air_y = fan_y + fan_size + fan_gap
        air_bottom_y = ret_air_y
        arr_dir_above = 'up'; arr_dir_below = 'up'
        components['deco_ret_air'] = {
            'type': 'DecorativeRect',
            'position': [left_edge, ret_air_y],
            'size': {'width': combined_w, 'height': 30},
            'properties': {'bg_color': '#FFCDD2', 'label': 'Return Air'},
        }

    # Fans + AirArrow markers
    if mode == 'modular':
        for mi, (mx, lb) in enumerate(zip(mod_xs, mod_lbs)):
            fname = f'Fan {lb}'.strip() if lb else 'Fan'
            fkey  = lb.lower().replace(' ', '_') if lb else f'm{mi}'
            components[f'deco_fan_{fkey}'] = {
                'type': 'DecorativeRect',
                'position': [mx - fan_size / 2, fan_y],
                'size': {'width': fan_size, 'height': fan_size},
                'properties': {'bg_color': '#E0E0E0', 'label': fname},
            }
            # Arrow below fan (pointing up into fan)
            components[f'deco_arr_{fkey}_bot'] = {
                'type': 'AirArrow',
                'position': [mx - 5, fan_y + fan_size],
                'size': {'width': 10, 'height': 10},
                'properties': {'direction': arr_dir_below},
            }
            # Arrow above fan (pointing up out of fan)
            components[f'deco_arr_{fkey}_top'] = {
                'type': 'AirArrow',
                'position': [mx - 5, fan_y - 10],
                'size': {'width': 10, 'height': 10},
                'properties': {'direction': arr_dir_above},
            }
    elif is_cassette:
        for ci, cx in enumerate(cas_xs):
            lb = cas_lbs[ci] if ci < len(cas_lbs) else f'U{ci + 1}'
            tag = lb if lb else f'U{ci + 1}'
            fan_span = min(cas_slice_w * 0.38, 150)
            for fan_idx, fx in enumerate((cx - fan_span / 2, cx + fan_span / 2), 1):
                fkey = f'cass_{ci + 1}_{fan_idx}'
                components[f'deco_fan_{fkey}'] = {
                    'type': 'DecorativeRect',
                    'position': [fx - fan_size / 2, fan_y],
                    'size': {'width': fan_size, 'height': fan_size},
                    'properties': {'bg_color': '#E0E0E0',
                                   'label': f'Evap Fan {tag}-{fan_idx}'},
                }
                components[f'deco_arr_{fkey}_top'] = {
                    'type': 'AirArrow',
                    'position': [fx - 5, fan_y - 10],
                    'size': {'width': 10, 'height': 10},
                    'properties': {'direction': 'down'},
                }
                components[f'deco_arr_{fkey}_bot'] = {
                    'type': 'AirArrow',
                    'position': [fx - 5, fan_y + fan_size],
                    'size': {'width': 10, 'height': 10},
                    'properties': {'direction': 'down'},
                }
    else:
        slice_w = combined_w / count
        for i in range(count):
            fx   = left_edge + slice_w / 2 + i * slice_w
            fkey = f'dr{i+1}'
            components[f'deco_fan_{fkey}'] = {
                'type': 'DecorativeRect',
                'position': [fx - fan_size / 2, fan_y],
                'size': {'width': fan_size, 'height': fan_size},
                'properties': {'bg_color': '#E0E0E0', 'label': f'Evap Fan Dr {i+1}'},
            }
            components[f'deco_arr_{fkey}_bot'] = {
                'type': 'AirArrow',
                'position': [fx - 5, fan_y + fan_size],
                'size': {'width': 10, 'height': 10},
                'properties': {'direction': 'up'},
            }
            components[f'deco_arr_{fkey}_top'] = {
                'type': 'AirArrow',
                'position': [fx - 5, fan_y - 10],
                'size': {'width': 10, 'height': 10},
                'properties': {'direction': 'up'},
            }

    # Airflow boundary
    air_bnd_y = base_y - 40
    air_bnd_h = (air_bottom_y + 30 + 40) - air_bnd_y
    components['bnd_air'] = {
        'type': 'Boundary',
        'position': [process_x, air_bnd_y],
        'size': {'width': process_w, 'height': air_bnd_h},
        'properties': {'label': 'Airflow Diagram', 'stroke_color': '#AAAAAA'},
    }

    # ── Shelving Diagram ─────────────────────────────────────────────────
    shelf_base_y  = air_bottom_y + 30 + 100
    shelf_height  = 30
    shelf_gap     = 20
    shelf_pitch   = shelf_height + shelf_gap
    shelf_total_h = shelf_rows * shelf_pitch - shelf_gap

    # All modes: shelves are drawn as one CONTIGUOUS shelving block spanning
    # the full case width.  `count` columns of shelf (modules / doors /
    # cassettes) share their column boundaries.  Each shelf row is one
    # wide rectangle subdivided by `count` columns — this is the "joined"
    # appearance the user expects.
    col_w  = combined_w / count
    col_xs = [left_edge + i * col_w for i in range(count)]

    for ci, csx in enumerate(col_xs):
        for r in range(shelf_rows):
            sy = shelf_base_y + r * shelf_pitch
            components[f'deco_shelf_{ci}_{r}'] = {
                'type': 'DecorativeRect',
                'position': [csx, sy],
                'size': {'width': col_w, 'height': shelf_height},
                'properties': {'bg_color': '#F0F0F0', 'label': f'Shelf {r+1}'},
            }

    components['bnd_shelf'] = {
        'type': 'Boundary',
        'position': [process_x, shelf_base_y - 40],
        'size': {'width': process_w, 'height': shelf_total_h + 60},
        'properties': {'label': 'Shelving Diagram', 'stroke_color': '#AAAAAA'},
    }

    # Add free-position sensor dots using canonical naming so the alias DB can
    # auto-map CSV columns without the user clicking.  This mirrors
    # test_loop.py: airflow dots live on airflow bands, product dots live at
    # one physical shelf-grid corner, and doors/mullions/fans get their own
    # visible anchors.
    from sensor_canonical import shelf_row_name, shelf_column_name
    sensor_dots = {}
    total_cols = count + 1   # one vertical edge per shelf column boundary

    def add_sensor_dot(canon, x, y, label, sensor_type='temperature', **extra):
        sensor_dots[canon] = {
            'type': sensor_type,
            'position': [x, y],
            'label': label,
            **extra,
        }

    # Calculated refrigeration callouts. These are not required raw probes;
    # they are diagram locations where Analysis mode can display computed
    # superheat/subcooling, while legacy lab-provided SH/SC columns may still
    # be mapped to the same callout if present.
    def add_calc_callouts():
        if is_cassette:
            label_to_tag = {'LH': 'lh', 'CTR': 'ctr', 'RH': 'rh'}
            for i, cx in enumerate(cas_xs):
                lb = cas_lbs[i] if i < len(cas_lbs) else f'U{i + 1}'
                tag = label_to_tag.get(str(lb).upper(), str(lb).lower() if lb else f'u{i + 1}')
                add_sensor_dot(
                    f'calc.SH.{tag}', cx + cas_evap_w / 2 + 26, Y_EVAP + EVAP_H + 18,
                    f'{tag.upper()} Coil Superheat', 'calculation',
                    calc_key=f'S.H_{tag} coil', display_side='right')
                add_sensor_dot(
                    f'calc.SH_total.{tag}', cx - COMP_W / 2 - 26, Y_COMP + 12,
                    f'{tag.upper()} Compressor Superheat', 'calculation',
                    calc_key=f'S.H_total-{tag}', display_side='left')
                add_sensor_dot(
                    f'calc.SC_txv.{tag}', cx + TXV_W / 2 + 26, Y_TXV + 12,
                    f'{tag.upper()} TXV Subcooling', 'calculation',
                    calc_key=f'S.C-txv.{tag}', display_side='right')
                add_sensor_dot(
                    f'calc.SC_cond.{tag}', cx + COND_W / 2 + 26, Y_COND + COND_H - 12,
                    f'{tag.upper()} Condenser Subcooling', 'calculation',
                    calc_key=f'S.C-{tag}', display_side='right')
            return

        tag_map = {'Left': 'lh', 'Center': 'ctr', 'Right': 'rh'}
        for mx, lb in zip(mod_xs, mod_lbs):
            tag = tag_map.get(lb, lb.lower() if lb else 'lh')
            add_sensor_dot(
                f'calc.SH.{tag}', mx + EVAP_W / 2 + 26, Y_EVAP + EVAP_H + 18,
                f'{lb} Coil Superheat', 'calculation',
                calc_key=f'S.H_{tag} coil', display_side='right')
            add_sensor_dot(
                f'calc.SC_txv.{tag}', mx + TXV_W / 2 + 26, Y_TXV + 12,
                f'{lb} TXV Subcooling', 'calculation',
                calc_key=f'S.C-txv.{tag}', display_side='right')
        add_sensor_dot(
            'calc.SH_total', CENTER_X - COMP_W / 2 - 26, Y_COMP + 12,
            'Compressor Total Superheat', 'calculation',
            calc_key='S.H_total', display_side='left')
        add_sensor_dot(
            'calc.SC_cond', CENTER_X + COND_W / 2 + 26, Y_COND + COND_H - 12,
            'Condenser Outlet Subcooling', 'calculation',
            calc_key='S.C', display_side='right')

    add_calc_callouts()

    def edge_x_for(v):
        if mode == 'modular':
            if v < count:
                return col_xs[v]
            return col_xs[-1] + col_w
        return left_edge + v * col_w

    # Air-curtain CSVs commonly use a denser left-to-right sensor pattern than
    # the physical shelf-column boundaries.  Generate the historical superset
    # (s1..s11) so existing data can map; unused dots simply stay grey.
    air_samples = [
        (1, '2in LE'), (2, '12in LE'), (3, '24in LE'),
        (4, '42in LE'), (5, '54in LE'), (6, 'Center'),
        (7, '54in RE'), (8, '42in RE'), (9, '24in RE'),
        (10, '12in RE'), (11, '2in RE'),
    ]

    def air_x_for(idx):
        if len(air_samples) <= 1:
            return left_edge + combined_w / 2
        return left_edge + combined_w * ((idx - 1) / (len(air_samples) - 1))

    for idx, air_h in air_samples:
        edge_x = air_x_for(idx)
        side = 'right' if idx == 1 else 'left' if idx == 11 else ('above' if idx % 2 else 'below')
        add_sensor_dot(f'T_air.disc.s{idx}', edge_x, pri_air_y + 15,
                       f'Primary Discharge Air - {air_h}',
                       display_side=side)
        if mode == 'modular':
            add_sensor_dot(f'T_air.sec.s{idx}', edge_x, base_y + 40 + 15,
                           f'Secondary Discharge Air - {air_h}',
                           display_side=side)
        add_sensor_dot(f'T_air.ret.s{idx}', edge_x, ret_air_y + 15,
                       f'Return Air - {air_h}',
                       display_side=side)

    # Core rule (user-defined):
    #   - 1 column of shelf per module / door / cassette (= `count`).
    #   - Shelves are JOINED across stacks (one contiguous shelving block).
    #   - Sharing happens at the COLUMN boundaries between stacks:
    #     `count + 1` boundary dot-columns total.  3 modules → 4 dot-cols.
    #     5 doors → 6 dot-cols.  The shared boundary is naturally ONE dot
    #     because adjacent stacks share that vertical line.
    #   - Each shelf keeps its OWN rear dot (top edge) and front dot
    #     (bottom edge) — those are NOT collapsed, since rear-of-upper
    #     and front-of-lower are physically different points on the case
    #     (the shelf has depth).
    shelf_width_in = 48 if mode == 'modular' else 30
    total_shelf_in = count * shelf_width_in
    product_cols = {}

    def add_product_col(col_id: str, inches_from_left: float):
        if inches_from_left < 0 or inches_from_left > total_shelf_in:
            return
        frac = inches_from_left / total_shelf_in if total_shelf_in else 0
        product_cols[col_id] = (
            left_edge + combined_w * frac,
            shelf_column_name(0, 1, [col_id])[1],
        )

    # Product-sim CSV labels are physical distances from the left or right
    # end of the case.  Non-modular/cassette shelves are 30 in wide; modular
    # shelves are 48 in wide.  Therefore LE30 is a shelf border on cassette
    # and door cases, while LE48 is a module border on modular cases.
    add_product_col('LE', 0)
    add_product_col('RE', total_shelf_in)
    add_product_col('Ctr', total_shelf_in / 2)
    for boundary in range(1, count):
        inches = boundary * shelf_width_in
        if inches <= total_shelf_in / 2:
            add_product_col(f'LE{int(inches)}', inches)
        else:
            add_product_col(f'RE{int(total_shelf_in - inches)}', inches)

    for col_id, (edge_x, col_h) in product_cols.items():
        side_rear = 'left' if col_id == 'RE' else 'right' if col_id == 'LE' else 'above'
        side_front = 'left' if col_id == 'RE' else 'right' if col_id == 'LE' else 'below'
        for r in range(shelf_rows):
            row_id, row_h = shelf_row_name(r, shelf_rows)
            top_y    = shelf_base_y + r * shelf_pitch          # rear edge of this shelf
            bottom_y = top_y + shelf_height                    # front edge of this shelf
            add_sensor_dot(f"T_prod.{row_id}.{col_id}.r",
                           edge_x, top_y,
                           f"Product Sim - {row_h} Shelf - {col_h} - Rear",
                           display_side=side_rear)
            add_sensor_dot(f"T_prod.{row_id}.{col_id}.f",
                           edge_x, bottom_y,
                           f"Product Sim - {row_h} Shelf - {col_h} - Front",
                           display_side=side_front)

    # Fan air thermocouples, anchored to the fan boxes.
    if mode == 'modular':
        fan_specs = []
        tag_map = {'Left': 'lh', 'Center': 'ctr', 'Right': 'rh'}
        for mi, (mx, lb) in enumerate(zip(mod_xs, mod_lbs)):
            tag = tag_map.get(lb, lb.lower() if lb else 'lh')
            fan_specs.append((tag, mx - fan_size / 2, fan_y, fan_size, fan_size))
    elif is_cassette:
        fan_specs = []
        for i, cx in enumerate(cas_xs):
            lb = cas_lbs[i] if i < len(cas_lbs) else ''
            tag = lb.lower() if lb else f'u{i+1}'
            fan_span = min(cas_slice_w * 0.38, 150)
            fan_specs.append((tag, cx - fan_span / 2, cx + fan_span / 2, fan_y))
    else:
        fan_specs = []
        slice_w = combined_w / count
        for i in range(count):
            fx = left_edge + slice_w / 2 + i * slice_w
            fan_specs.append((f'd{i+1}', fx - fan_size / 2, fan_y, fan_size, fan_size))

    for spec in fan_specs:
        if is_cassette:
            tag, left_x, right_x, fy = spec
            fh = fan_size
        else:
            tag, fx, fy, fw, fh = spec
            left_x = fx + fw * 0.18
            right_x = fx + fw * 0.82
        if is_cassette:
            inlet_y = fy - 14
            outlet_y = fy + fh + 14
        else:
            inlet_y = fy + fh + 14
            outlet_y = fy - 14
        add_sensor_dot(f'T_air.fan_in.{tag}.LE', left_x, inlet_y,
                       f'Fan {tag.upper()} Air In - LE', display_side='left')
        add_sensor_dot(f'T_air.fan_in.{tag}.RE', right_x, inlet_y,
                       f'Fan {tag.upper()} Air In - RE', display_side='right')
        add_sensor_dot(f'T_air.fan_off.{tag}.LE', left_x, outlet_y,
                       f'Fan {tag.upper()} Air Off - LE', display_side='left')
        add_sensor_dot(f'T_air.fan_off.{tag}.RE', right_x, outlet_y,
                       f'Fan {tag.upper()} Air Off - RE', display_side='right')
        if is_cassette:
            add_sensor_dot(f'T_air.fan_off.{tag}.avg', (left_x + right_x) / 2, outlet_y + 18,
                           f'Discharge Air Sensor ({tag.upper()})', display_side='below')

    # Air-cooled cassette condenser air probes. Historical RLN/RMN files use
    # left/right condenser air-in and air-out labels per unit.
    if is_cassette and condenser_type == 'Air Cooled':
        for i, cx in enumerate(cas_xs):
            lb = cas_lbs[i] if i < len(cas_lbs) else ''
            tag = lb.lower() if lb else f'u{i+1}'
            fan_w = min(110, max(76, cas_slice_w * 0.20))
            fan_h = 40
            fan_x = cx + COND_W / 2 + 92
            fan_y_cond = Y_COND + (COND_H - fan_h) / 2
            components[f'deco_condfan_{tag}'] = {
                'type': 'DecorativeRect',
                'position': [fan_x, fan_y_cond],
                'size': {'width': fan_w, 'height': fan_h},
                'properties': {'bg_color': '#E0E0E0',
                               'label': f'Cond. Fan {tag.upper()}'},
            }
            components[f'deco_condfan_{tag}_arr_in'] = {
                'type': 'AirArrow',
                'position': [fan_x + fan_w / 2 - 5, fan_y_cond - 12],
                'size': {'width': 10, 'height': 10},
                'properties': {'direction': 'down'},
            }
            components[f'deco_condfan_{tag}_arr_out'] = {
                'type': 'AirArrow',
                'position': [fan_x + fan_w / 2 - 5, fan_y_cond + fan_h + 2],
                'size': {'width': 10, 'height': 10},
                'properties': {'direction': 'down'},
            }
            left_x = fan_x + fan_w * 0.25
            right_x = fan_x + fan_w * 0.75
            in_y = fan_y_cond - 10
            out_y = fan_y_cond + fan_h + 10
            add_sensor_dot(f'T_air.cond_in.{tag}.LE', left_x, in_y,
                           f'Condenser Air In ({tag.upper()} LE)', display_side='left')
            add_sensor_dot(f'T_air.cond_in.{tag}.RE', right_x, in_y,
                           f'Condenser Air In ({tag.upper()} RE)', display_side='right')
            add_sensor_dot(f'T_air.cond_out.{tag}.LE', left_x, out_y,
                           f'Condenser Air Out ({tag.upper()} LE)', display_side='left')
            add_sensor_dot(f'T_air.cond_out.{tag}.RE', right_x, out_y,
                           f'Condenser Air Out ({tag.upper()} RE)', display_side='right')
    
    # ── Doors Diagram ────────────────────────────────────────────────────
    door_style = topo.get('door_style', '')
    if case_type == 'Doored':
        door_base_y = shelf_base_y + shelf_total_h + 80
        door_height = 240
        mullion_w   = 16
        door_rects = []
        mullion_rects = []

        if mode == 'modular':
            # French-door pattern (user rule):
            #   E [D D C] × (N-1) [D D] E
            # N modules → 2N doors + (N+1) mullions
            #   (2 end mullions + N-1 center mullions).
            # Each module is one pair of French doors.
            N_mod      = len(mod_xs)
            n_doors    = 2 * N_mod
            n_mullions = N_mod + 1
            gap = 4
            total_mull_w = n_mullions * mullion_w
            total_gap_w  = (n_doors + n_mullions - 1) * gap
            door_w = (combined_w - total_mull_w - total_gap_w) / n_doors

            # Build the item sequence: [(kind, id), ...] then place left-to-right
            sequence: list[tuple[str, str]] = [('M', 'LH')]
            ctr_idx = 0
            door_idx = 0
            for m in range(N_mod):
                # Pair of French doors for this module
                tag = ['lh', 'ctr', 'rh'][m] if N_mod == 3 else \
                      ['lh', 'rh'][m]        if N_mod == 2 else 'lh'
                door_idx += 1; sequence.append(('D', f'{door_idx}.{tag}.L'))
                door_idx += 1; sequence.append(('D', f'{door_idx}.{tag}.R'))
                if m < N_mod - 1:
                    ctr_idx += 1
                    sequence.append(('M', f'ctr{ctr_idx}'))
            sequence.append(('M', 'RH'))

            dcx = left_edge
            for kind, ident in sequence:
                if kind == 'M':
                    components[f'deco_mull_{ident.lower()}'] = {
                        'type': 'DecorativeRect',
                        'position': [dcx, door_base_y],
                        'size': {'width': mullion_w, 'height': door_height},
                        'properties': {'bg_color': '#B0BEC5', 'label': ''},
                    }
                    mullion_rects.append((ident, dcx, door_base_y, mullion_w, door_height))
                    dcx += mullion_w + gap
                else:
                    # ident = "{door_num}.{module_tag}.{L|R}"
                    door_num = int(ident.split('.')[0])
                    components[f'deco_door_{door_num}'] = {
                        'type': 'DecorativeRect',
                        'position': [dcx, door_base_y],
                        'size': {'width': door_w, 'height': door_height},
                        'properties': {'bg_color': '#E1F5FE',
                                       'label': f'Door {door_num}'},
                    }
                    door_rects.append((door_num, dcx, door_base_y, door_w, door_height))
                    dcx += door_w + gap
        else:
            N   = count
            gap = 4
            total_mull_w = (N + 1) * mullion_w
            total_gap_w  = (2 * N) * gap
            door_w = (combined_w - total_mull_w - total_gap_w) / N
            dcx = left_edge
            components['deco_mull_lh'] = {
                'type': 'DecorativeRect',
                'position': [dcx, door_base_y],
                'size': {'width': mullion_w, 'height': door_height},
                'properties': {'bg_color': '#B0BEC5', 'label': ''},
            }
            mullion_rects.append(('LH', dcx, door_base_y, mullion_w, door_height))
            dcx += mullion_w + gap
            for i in range(N):
                components[f'deco_door_{i+1}'] = {
                    'type': 'DecorativeRect',
                    'position': [dcx, door_base_y],
                    'size': {'width': door_w, 'height': door_height},
                    'properties': {'bg_color': '#E1F5FE', 'label': f'Door {i+1}'},
                }
                door_rects.append((i + 1, dcx, door_base_y, door_w, door_height))
                dcx += door_w + gap
                if i < N - 1:
                    components[f'deco_mull_ctr_{i}'] = {
                        'type': 'DecorativeRect',
                        'position': [dcx, door_base_y],
                        'size': {'width': mullion_w, 'height': door_height},
                        'properties': {'bg_color': '#B0BEC5', 'label': ''},
                    }
                    mullion_rects.append((f'ctr{i+1}', dcx, door_base_y, mullion_w, door_height))
                    dcx += mullion_w + gap
            components['deco_mull_rh'] = {
                'type': 'DecorativeRect',
                'position': [dcx, door_base_y],
                'size': {'width': mullion_w, 'height': door_height},
                'properties': {'bg_color': '#B0BEC5', 'label': ''},
            }
            mullion_rects.append(('RH', dcx, door_base_y, mullion_w, door_height))
        components['bnd_doors'] = {
            'type': 'Boundary',
            'position': [process_x, door_base_y - 40],
            'size': {'width': process_w, 'height': door_height + 60},
            'properties': {'label': 'Doors Diagram', 'stroke_color': '#AAAAAA'},
        }

        door_points = [
            ('top.L', 0.22, 0.08, 'above'),
            ('top.R', 0.78, 0.08, 'above'),
            ('ctr',   0.50, 0.50, 'right'),
            ('btm.L', 0.22, 0.92, 'below'),
            ('btm.R', 0.78, 0.92, 'below'),
        ]
        for door_num, x, y, w, h in door_rects:
            for suffix, fx, fy, side in door_points:
                add_sensor_dot(f'T_door.d{door_num}.{suffix}',
                               x + w * fx, y + h * fy,
                               f'Door {door_num} Thermocouple {suffix}',
                               display_side=side)

        mullion_points = [
            ('top',   0.10, 'right'),
            ('upper', 0.30, 'right'),
            ('ctr',   0.50, 'right'),
            ('lower', 0.70, 'right'),
            ('btm',   0.90, 'right'),
        ]
        for mullion_id, x, y, w, h in mullion_rects:
            for suffix, fy, side in mullion_points:
                add_sensor_dot(f'T_mull.{mullion_id}.{suffix}',
                               x + w / 2, y + h * fy,
                               f'Mullion {mullion_id} Thermocouple {suffix}',
                               display_side=side)

    # ── Tag all components and pipes ──────────────────────────────────────
    for p in pipes.values():
        p['_simple_mode'] = True
        p['route_locked'] = True
        p['_raw_route']   = True
    for c in components.values():
        c['_simple_mode'] = True

    model = {
        'components': components,
        'pipes':      pipes,
        'sensor_roles':    {},
        'custom_sensors':  sensor_dots,
        'role_dot_labels': {},
        'sensor_boxes':    {},
        '_simple_mode': True,
        '_topology': topo,
        '_generated_from': (f'bare_minimum ({mode}, count={count}, '
                            f'{num_circuits} circuits/coil)'),
    }
    # Add canonical sensor boxes so off-diagram instruments (ambient temps,
    # wall temps, compressor electrical) always have a home.
    _ensure_canonical_sensor_boxes(model, topo)
    return model
