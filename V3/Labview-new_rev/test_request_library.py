"""
test_request_library.py

Data layer for the Test Request system (TEST_REQUEST_PLAN.md, Phase 1).

Design rules (per plan §3 — user explicitly rejected one lumped file):
- A `library/` folder of SMALL, SINGLE-PURPOSE JSON files:
    library/catalogs/txv.json, compressors.json, coils.json, ...
    library/criteria/...        (pass/fail targets per standard / case family)
    library/elp_codes.json      (test-type registry)
    library/projects/<project_id>/project.json
    library/projects/<project_id>/requests/<request_id>.json
- Every record carries a stable unique id + created_by + created_at  → merge-ready
  when multiple engineers' libraries are later compiled into one source of truth.
- A test request stores each part's catalog id PLUS a frozen snapshot of the
  part's values at the time of use, so later catalog edits never silently
  rewrite history.
"""

from __future__ import annotations

import getpass
import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional

LIBRARY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'library')

# Part schemas.  RULE: a field exists only if something downstream consumes it
# (calculation engine, diagram, scorecard) or identifies the part.
# 'model' is always the SUPPLIER part number (primary identifier, user decision
# 2026-06-11); company_pn is the optional internal number.
# kind: 'float' | 'text' | ('choice', [options])
PART_FIELD_DEFS: Dict[str, List[tuple]] = {
    'compressor': [
        ('company_pn',              'Company part number (optional)', 'text'),
        # The five numbers below ARE the "Rated Inputs" the engine needs —
        # entered once per compressor model, auto-filled forever after.
        ('displacement_in3',        'Displacement (in³)',             'float'),
        ('rated_speed_rpm',         'Rated speed (RPM)',              'float'),
        ('rated_mdot_lbhr',         'Rated mass flow (lb/hr)',        'float'),
        ('rated_evap_temp_f',       'Rated evap temp (°F)',           'float'),
        ('rated_return_gas_temp_f', 'Rated return gas temp (°F)',     'float'),
        ('notes',                   'Notes',                          'text'),
    ],
    'condenser': [
        ('company_pn',   'Company part number (optional)', 'text'),
        ('cooling_type', 'Cooling type',                   ('choice', ['Water', 'Air'])),
        ('design_gpm',   'Design water flow (GPM)',        'float'),
        ('design_cfm',   'Design air flow (CFM)',          'float'),
        ('notes',        'Notes',                          'text'),
    ],
    'txv': [
        ('company_pn',        'Company part number (optional)', 'text'),
        ('nominal_tons',      'Nominal capacity (tons)',        'float'),
        ('rated_refrigerant', 'Rated refrigerant',              'text'),
        ('notes',             'Notes',                          'text'),
    ],
    'coil': [
        ('company_pn', 'Company part number (optional)', 'text'),
        ('circuits',   'Number of circuits',             'float'),
        ('fpi',        'Fins per inch',                  'float'),
        ('rows',       'Rows',                           'float'),
        ('notes',      'Notes',                          'text'),
    ],
    'distributor': [
        ('company_pn',  'Company part number (optional)', 'text'),
        ('outlets',     'Number of outlets',              'float'),
        ('nozzle_size', 'Nozzle size',                    'text'),
        ('notes',       'Notes',                          'text'),
    ],
    'fan': [
        ('company_pn',  'Company part number (optional)', 'text'),
        ('diameter_in', 'Diameter (in)',                  'float'),
        ('cfm',         'Air flow (CFM)',                 'float'),
        ('speed_rpm',   'Speed (RPM)',                    'float'),
        ('notes',       'Notes',                          'text'),
    ],
}

# Backward-compatible view: part type → list of field keys
PART_TYPES: Dict[str, List[str]] = {
    ptype: [f[0] for f in fields] for ptype, fields in PART_FIELD_DEFS.items()
}

# Unit conversions for feeding the calculation engine
IN3_TO_CM3 = 16.387064
IN3_TO_FT3 = 1.0 / 1728.0


def part_display(record: dict) -> str:
    """How a part shows in dropdowns: 'SUPPLIER-PN · company-pn'."""
    base = record.get('model', '?')
    comp = record.get('company_pn')
    return f'{base} · {comp}' if comp else base


def compressor_to_rated_inputs(snapshot: dict, water_gpm=None) -> dict:
    """Convert a compressor catalog snapshot (user units: in³, RPM) into the
    engine's rated_inputs dict (ft³, Hz).  This is the wire that makes
    'pick the compressor' auto-fill the Rated Inputs dialog."""
    out = {}
    disp_in3 = snapshot.get('displacement_in3')
    if disp_in3:
        out['disp_ft3'] = float(disp_in3) * IN3_TO_FT3
    rpm = snapshot.get('rated_speed_rpm')
    if rpm:
        out['hz_rated'] = float(rpm) / 60.0
    if snapshot.get('rated_mdot_lbhr'):
        out['m_dot_rated_lbhr'] = float(snapshot['rated_mdot_lbhr'])
    if snapshot.get('rated_evap_temp_f') is not None:
        out['rated_evap_temp_f'] = float(snapshot['rated_evap_temp_f'])
    if snapshot.get('rated_return_gas_temp_f') is not None:
        out['rated_return_gas_temp_f'] = float(snapshot['rated_return_gas_temp_f'])
    if water_gpm:
        out['gpm_water'] = float(water_gpm)
    return out

# Seeded test types — fully editable/extensible by the user.
DEFAULT_ELP_CODES = [
    {'code': 'PERF',    'name': 'Performance (incl. NSF / DOE)'},
    {'code': 'UL',      'name': 'UL Safety'},
    {'code': 'ELP0071', 'name': 'Transit Test'},
    {'code': 'LOAD',    'name': 'Load Test'},
    {'code': 'VIB',     'name': 'Vibration'},
    {'code': 'SOUND',   'name': 'Sound'},
]

# Default target rows offered in a new request (name, min, max, unit).
DEFAULT_TARGETS = [
    {'name': 'Product temp',        'min': None, 'max': 38.0, 'unit': '°F'},
    {'name': 'Coil superheat',      'min': 6.0,  'max': 9.0,  'unit': '°F'},
    {'name': 'Subcooling',          'min': 5.0,  'max': 15.0, 'unit': '°F'},
    {'name': 'Capacity',            'min': None, 'max': None, 'unit': 'BTU/hr'},
    {'name': 'DOE energy',          'min': None, 'max': None, 'unit': 'kWh/day'},
]


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _new_id(prefix: str) -> str:
    return f'{prefix}_{uuid.uuid4().hex[:8]}'


def _user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return 'unknown'


class TestRequestLibrary:
    """All reads/writes for the library folder. One instance per app."""

    def __init__(self, base_dir: str = LIBRARY_DIR):
        self.base = base_dir
        self.catalogs_dir = os.path.join(self.base, 'catalogs')
        self.criteria_dir = os.path.join(self.base, 'criteria')
        self.projects_dir = os.path.join(self.base, 'projects')
        for d in (self.base, self.catalogs_dir, self.criteria_dir, self.projects_dir):
            os.makedirs(d, exist_ok=True)

    # ── low-level json helpers ───────────────────────────────────────────────
    @staticmethod
    def _read(path: str, default):
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except Exception as e:
            print(f'[LIBRARY] Failed reading {path}: {e}')
            return default

    @staticmethod
    def _write(path: str, data) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

    # ── parts catalogs (one file per part type) ──────────────────────────────
    def _catalog_path(self, part_type: str) -> str:
        return os.path.join(self.catalogs_dir, f'{part_type}s.json')

    def catalog(self, part_type: str) -> List[dict]:
        return self._read(self._catalog_path(part_type), [])

    def catalog_models(self, part_type: str) -> List[str]:
        return [part_display(p) for p in self.catalog(part_type)]

    def find_part(self, part_type: str, model: str) -> Optional[dict]:
        # Tolerate the dropdown display form 'SUPPLIER-PN · company-pn'
        model_l = (model or '').split('·')[0].strip().lower()
        for p in self.catalog(part_type):
            if p.get('model', '').strip().lower() == model_l:
                return p
        return None

    def add_part(self, part_type: str, model: str, specs: dict) -> dict:
        """Add a part if its supplier PN is new; return the catalog record."""
        existing = self.find_part(part_type, model)
        if existing:
            return existing
        record = {
            'id': _new_id(part_type[:4]),
            'model': model.split('·')[0].strip(),   # supplier part number
            **{k: v for k, v in (specs or {}).items() if v not in (None, '')},
            'created_by': _user(),
            'created_at': _now(),
        }
        cat = self.catalog(part_type)
        cat.append(record)
        self._write(self._catalog_path(part_type), cat)
        print(f'[LIBRARY] New {part_type} added to catalog: {model}')
        return record

    # ── ELP test-type registry ───────────────────────────────────────────────
    def elp_codes(self) -> List[dict]:
        path = os.path.join(self.base, 'elp_codes.json')
        codes = self._read(path, None)
        if codes is None:
            codes = list(DEFAULT_ELP_CODES)
            self._write(path, codes)
        return codes

    def add_elp_code(self, code: str, name: str) -> None:
        path = os.path.join(self.base, 'elp_codes.json')
        codes = self.elp_codes()
        if not any(c['code'].lower() == code.lower() for c in codes):
            codes.append({'code': code, 'name': name})
            self._write(path, codes)

    # ── criteria (per case model target sets) ────────────────────────────────
    def case_targets_path(self, case_model: str) -> str:
        safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in case_model)
        return os.path.join(self.criteria_dir, 'case_targets', f'{safe}.json')

    def load_case_targets(self, case_model: str) -> Optional[List[dict]]:
        return self._read(self.case_targets_path(case_model), None)

    def save_case_targets(self, case_model: str, targets: List[dict]) -> None:
        self._write(self.case_targets_path(case_model), targets)

    def known_case_models(self) -> List[str]:
        d = os.path.join(self.criteria_dir, 'case_targets')
        if not os.path.isdir(d):
            return []
        return [os.path.splitext(f)[0] for f in sorted(os.listdir(d))
                if f.endswith('.json')]

    # ── projects & requests ──────────────────────────────────────────────────
    def projects(self) -> List[dict]:
        out = []
        if not os.path.isdir(self.projects_dir):
            return out
        for pid in sorted(os.listdir(self.projects_dir)):
            pj = self._read(os.path.join(self.projects_dir, pid, 'project.json'), None)
            if pj:
                out.append(pj)
        return out

    def add_project(self, name: str) -> dict:
        for p in self.projects():
            if p.get('name', '').strip().lower() == name.strip().lower():
                return p
        record = {'id': _new_id('proj'), 'name': name.strip(),
                  'created_by': _user(), 'created_at': _now()}
        self._write(os.path.join(self.projects_dir, record['id'], 'project.json'),
                    record)
        return record

    def requests_for(self, project_id: str) -> List[dict]:
        d = os.path.join(self.projects_dir, project_id, 'requests')
        if not os.path.isdir(d):
            return []
        return [self._read(os.path.join(d, f), None)
                for f in sorted(os.listdir(d)) if f.endswith('.json')]

    def all_requests(self) -> List[dict]:
        out = []
        for p in self.projects():
            out.extend(r for r in self.requests_for(p['id']) if r)
        return out

    def save_request(self, request: dict) -> None:
        path = os.path.join(self.projects_dir, request['project_id'],
                            'requests', f"{request['id']}.json")
        self._write(path, request)
        print(f"[LIBRARY] Saved test request {request.get('request_no')} "
              f"({request['id']})")

    def new_request(self, project_id: str) -> dict:
        """Skeleton request — Rev A, empty fields, sequential request number."""
        n = sum(len(self.requests_for(p['id'])) for p in self.projects()) + 1
        return {
            'id': _new_id('tr'),
            'request_no': f'TR-{datetime.now().year}-{n:03d}',
            'project_id': project_id,
            'elp_code': '',
            'title': '',
            'objective': '',
            'case_model': '',
            'topology': {           # later drives Phase 3 auto-diagram
                'case_family': 'Reach-in (non-modular)',
                'system_type': 'shared',
                'modules': 1,
                'circuits_per_coil': 6,
                'condenser_cooling': 'Water',
                'doored': True,
            },
            'parts': {},            # part_type -> {'catalog_id', 'model', 'snapshot'}
            'settings': {
                'refrigerant': 'R290',
                'charge_oz': None,
                'water_gpm': None,
                'fan_cfm': None,
                'defrost': '',
                'setpoints': '',
            },
            'targets': [dict(t) for t in DEFAULT_TARGETS],
            'revisions': [{
                'rev': 'A', 'at': _now(), 'by': _user(),
                'note': 'Initial release',
            }],
            'created_by': _user(),
            'created_at': _now(),
        }

    # ── part snapshotting (history must never silently change) ───────────────
    def attach_part(self, request: dict, part_type: str, model: str,
                    specs: dict = None) -> None:
        """Reference a catalog part from a request, freezing its values."""
        if not model or not model.strip():
            request['parts'].pop(part_type, None)
            return
        record = self.find_part(part_type, model) or \
            self.add_part(part_type, model, specs or {})
        request['parts'][part_type] = {
            'catalog_id': record['id'],
            'model': record['model'],
            'snapshot': {k: v for k, v in record.items()
                         if k not in ('id', 'created_by', 'created_at')},
        }


# ── printable test request (HTML) ────────────────────────────────────────────

def request_to_html(request: dict, project_name: str = '') -> str:
    """Render a test request as a clean printable HTML document."""
    def esc(s):
        return (str(s) if s is not None else '—').replace('&', '&amp;') \
            .replace('<', '&lt;').replace('>', '&gt;')

    topo = request.get('topology', {})
    settings = request.get('settings', {})
    rev = request.get('revisions', [{}])[-1]

    rows_parts = ''
    for ptype in PART_TYPES:
        p = request.get('parts', {}).get(ptype)
        if not p:
            continue
        snap = p.get('snapshot', {})
        spec_txt = ', '.join(f'{k}: {v}' for k, v in snap.items()
                             if k not in ('model',) and v not in (None, ''))
        rows_parts += (f'<tr><td>{esc(ptype.title())}</td>'
                       f'<td><b>{esc(p.get("model"))}</b></td>'
                       f'<td>{esc(spec_txt)}</td></tr>')

    rows_targets = ''
    for t in request.get('targets', []):
        lo = t.get('min'); hi = t.get('max')
        if lo is None and hi is None:
            band = '—'
        elif lo is None:
            band = f'≤ {hi}'
        elif hi is None:
            band = f'≥ {lo}'
        else:
            band = f'{lo} – {hi}'
        rows_targets += (f'<tr><td>{esc(t.get("name"))}</td>'
                         f'<td>{esc(band)}</td><td>{esc(t.get("unit"))}</td></tr>')

    rows_revs = ''
    for r in request.get('revisions', []):
        rows_revs += (f'<tr><td>Rev {esc(r.get("rev"))}</td>'
                      f'<td>{esc(r.get("at"))}</td><td>{esc(r.get("by"))}</td>'
                      f'<td>{esc(r.get("note"))}</td></tr>')

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
 body {{ font-family: Arial, sans-serif; font-size: 11pt; margin: 32px; }}
 h1 {{ font-size: 16pt; border-bottom: 3px solid #007bff; padding-bottom: 6px; }}
 h2 {{ font-size: 12pt; color: #007bff; margin-top: 22px; }}
 table {{ border-collapse: collapse; width: 100%; margin-top: 6px; }}
 td, th {{ border: 1px solid #ccc; padding: 5px 8px; text-align: left; }}
 th {{ background: #f0f4ff; }}
 .meta td {{ border: none; padding: 2px 12px 2px 0; }}
</style></head><body>
<h1>Test Request {esc(request.get('request_no'))} — Rev {esc(rev.get('rev'))}</h1>
<table class="meta">
 <tr><td><b>Project:</b> {esc(project_name)}</td>
     <td><b>Test type:</b> {esc(request.get('elp_code'))}</td>
     <td><b>Engineer:</b> {esc(request.get('created_by'))}</td>
     <td><b>Date:</b> {esc(request.get('created_at'))}</td></tr>
</table>
<h2>Title & Objective</h2>
<p><b>{esc(request.get('title'))}</b></p>
<p>{esc(request.get('objective'))}</p>
<h2>Case</h2>
<table>
 <tr><th>Case model</th><th>Family</th><th>System</th><th>Modules</th>
     <th>Circuits/coil</th><th>Condenser</th><th>Doored</th></tr>
 <tr><td>{esc(request.get('case_model'))}</td><td>{esc(topo.get('case_family'))}</td>
     <td>{esc(topo.get('system_type'))}</td><td>{esc(topo.get('modules'))}</td>
     <td>{esc(topo.get('circuits_per_coil'))}</td>
     <td>{esc(topo.get('condenser_cooling'))}</td>
     <td>{'Yes' if topo.get('doored') else 'No'}</td></tr>
</table>
<h2>Parts</h2>
<table><tr><th>Component</th><th>Model</th><th>Specs (frozen at time of use)</th></tr>
{rows_parts or '<tr><td colspan="3">No parts recorded</td></tr>'}</table>
<h2>Settings</h2>
<table class="meta">
 <tr><td><b>Refrigerant:</b> {esc(settings.get('refrigerant'))}</td>
     <td><b>Charge (oz):</b> {esc(settings.get('charge_oz'))}</td>
     <td><b>Water GPM:</b> {esc(settings.get('water_gpm'))}</td>
     <td><b>Fan CFM:</b> {esc(settings.get('fan_cfm'))}</td></tr>
 <tr><td colspan="2"><b>Defrost:</b> {esc(settings.get('defrost'))}</td>
     <td colspan="2"><b>Setpoints:</b> {esc(settings.get('setpoints'))}</td></tr>
</table>
<h2>Targets (pass/fail criteria)</h2>
<table><tr><th>Target</th><th>Acceptance band</th><th>Unit</th></tr>{rows_targets}</table>
<h2>Revision history</h2>
<table><tr><th>Rev</th><th>When</th><th>By</th><th>Change</th></tr>{rows_revs}</table>
</body></html>"""
