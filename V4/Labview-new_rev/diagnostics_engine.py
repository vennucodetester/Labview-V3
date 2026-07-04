"""
diagnostics_engine.py — HVAC Lab Viewer Diagnostic Engine
==========================================================

ARCHITECTURE: Scenario Registry Pattern
Each diagnostic scenario is a self-contained class inheriting DiagnosticScenario.

HOW TO ADD A NEW SCENARIO:
  1. Write a class inheriting DiagnosticScenario (copy any existing class as template).
  2. Set SCENARIO_ID, COMPONENT, LABEL, DEFAULT_THRESHOLDS.
  3. Implement run(df, ctx, thresholds) -> list[Finding].
  4. Append YourNewScenario() to SCENARIO_REGISTRY at the very bottom of this file.
  5. Done — the UI picks it up automatically.

HOW TO DISABLE A FAULTY SCENARIO:
  Find the class, set ENABLED = False, add a comment with the date and reason.

HOW TO ADJUST DETECTION LOGIC:
  Edit the relevant class's run() method and add a line to its UPDATE LOG in the docstring.

HOW TO ADJUST THRESHOLDS WITHOUT EDITING CODE:
  Use the ⚙ Thresholds button in the Diagnostics tab UI.

FILE STRUCTURE:
  1. Imports & constants
  2. DiagnosticContext, Finding, DiagnosticScenario  (base types)
  3. Helper functions
  4. Scenario classes  (grouped by component — RF, CP, CD, EV, TX, DI, HG, SI)
  5. SCENARIO_REGISTRY  (add new scenarios here)
  6. run_all_diagnostics()  (entry point called by DiagnosticsWidget)
"""

from __future__ import annotations

import logging
import numpy as np
import re
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ─── CONSTANTS ────────────────────────────────────────────────────────────────

SEVERITY_ORDER = {'CRITICAL': 0, 'WARNING': 1, 'WATCH': 2, 'OK': 3, 'INFO': 4}

# ─── COLUMN DESCRIPTIONS ──────────────────────────────────────────────────────
# Used by ColumnManagerDialog. Tuple of (description, unit).

COLUMN_DESCRIPTIONS: dict = {
    'S.H_total':       ('Total superheat at compressor inlet (T_2b − T_sat.comp.in)', '°F'),
    'S.H_lh coil':     ('Left coil outlet superheat (T_2a-LH − T_sat.lh)', '°F'),
    'S.H_rh coil':     ('Right coil outlet superheat (T_2a-RH − T_sat.rh)', '°F'),
    'S.H_ctr coil':    ('Center coil outlet superheat (T_2a-CTR − T_sat.ctr)', '°F'),
    'S.C':             ('Condenser subcooling (T_sat.cond − T_4a)', '°F'),
    'S.C-txv.lh':      ('Subcooling at LH TXV inlet', '°F'),
    'S.C-txv.rh':      ('Subcooling at RH TXV inlet', '°F'),
    'S.C-txv.ctr':     ('Subcooling at CTR TXV inlet', '°F'),
    'T_2b':            ('Compressor suction line temperature', '°F'),
    'T_3a':            ('Compressor discharge temperature', '°F'),
    'T_3b':            ('Condenser inlet temperature', '°F'),
    'T_4a':            ('Condenser outlet / liquid line temperature', '°F'),
    'T_waterin':       ('Condenser water inlet temperature', '°F'),
    'T_waterout':      ('Condenser water outlet temperature', '°F'),
    'T_sat.comp.in':   ('Saturation temperature at suction pressure', '°F'),
    'T_sat.cond':      ('Saturation temperature at discharge pressure', '°F'),
    'P_suction':       ('Suction pressure', 'PSIG'),
    'P_disch':         ('Discharge pressure', 'PSIG'),
    'H_comp.in':       ('Enthalpy at compressor inlet', 'kJ/kg'),
    'H_txv.lh':        ('Enthalpy at LH TXV inlet', 'kJ/kg'),
    'H_txv.rh':        ('Enthalpy at RH TXV inlet', 'kJ/kg'),
    'H_txv.ctr':       ('Enthalpy at CTR TXV inlet', 'kJ/kg'),
    'qc':              ('Total cooling capacity', 'BTU/hr'),
    'm_dot':           ('Refrigerant mass flow rate', 'lb/hr'),
    'rpm':             ('Compressor speed', 'RPM'),
    'T_1a-lh':         ('LH TXV outlet / distributor inlet temp', '°F'),
    'T_1b-lh':         ('LH coil inlet / post-distributor temp', '°F'),
    'T_2a-LH':         ('LH coil outlet temperature', '°F'),
    'T_1a-rh':         ('RH TXV outlet / distributor inlet temp', '°F'),
    'T_1b-rh':         ('RH coil inlet / post-distributor temp', '°F'),
    'T_2a-RH':         ('RH coil outlet temperature', '°F'),
    'T_1a-ctr':        ('CTR TXV outlet / distributor inlet temp', '°F'),
    'T_1b-ctr':        ('CTR coil inlet / post-distributor temp', '°F'),
    'T_2a-CTR':        ('CTR coil outlet temperature', '°F'),
}

COLUMN_DESCRIPTIONS = {
    'S.H_total': ('Total superheat at compressor inlet (T_2b - T_sat.comp.in)', '°F'),
    'S.H_lh coil': ('Left coil outlet superheat (T_2a-LH - T_sat.lh)', '°F'),
    'S.H_rh coil': ('Right coil outlet superheat (T_2a-RH - T_sat.rh)', '°F'),
    'S.H_ctr coil': ('Center coil outlet superheat (T_2a-CTR - T_sat.ctr)', '°F'),
    'S.C': ('Condenser subcooling (T_sat.cond - T_4a)', '°F'),
    'S.C-txv.lh': ('Subcooling at LH TXV inlet', '°F'),
    'S.C-txv.rh': ('Subcooling at RH TXV inlet', '°F'),
    'S.C-txv.ctr': ('Subcooling at CTR TXV inlet', '°F'),
    'T_2b': ('Compressor suction line temperature', '°F'),
    'T_3a': ('Compressor discharge temperature', '°F'),
    'T_3b': ('Condenser inlet temperature', '°F'),
    'T_4a': ('Condenser outlet / liquid line temperature', '°F'),
    'T_waterin': ('Condenser water inlet temperature', '°F'),
    'T_waterout': ('Condenser water outlet temperature', '°F'),
    'T_sat.comp.in': ('Saturation temperature at suction pressure', '°F'),
    'T_sat.cond': ('Saturation temperature at discharge pressure', '°F'),
    'P_suction': ('Suction pressure', 'PSIG'),
    'P_disch': ('Discharge pressure', 'PSIG'),
    'H_comp.in': ('Enthalpy at compressor inlet', 'kJ/kg'),
    'H_txv.lh': ('Enthalpy at LH TXV inlet', 'kJ/kg'),
    'H_txv.rh': ('Enthalpy at RH TXV inlet', 'kJ/kg'),
    'qc': ('Total cooling capacity', 'BTU/hr'),
    'm_dot': ('Refrigerant mass flow rate', 'lb/hr'),
    'rpm': ('Compressor speed', 'RPM'),
    'T_1a-lh': ('LH TXV outlet / distributor inlet temp', '°F'),
    'T_1b-lh': ('LH coil inlet / post-distributor temp', '°F'),
    'T_2a-LH': ('LH coil outlet temperature', '°F'),
    'T_2a-RH': ('RH coil outlet temperature', '°F'),
    'T_1a-rh': ('RH TXV outlet / distributor inlet temp', '°F'),
    'T_1b-rh': ('RH coil inlet / post-distributor temp', '°F'),
}

# ─── BASE TYPES ───────────────────────────────────────────────────────────────

@dataclass
class DiagnosticContext:
    """Passed to every scenario's run() method. Read-only context about the system."""
    system_type:   str   # 'shared' | 'cassette'
    module_labels: list  # e.g. ['Left', 'Right']  — use these, never hardcode
    rated_inputs:  dict  # from data_manager.rated_inputs (may be empty dict)
    # Optional: cycle solver prediction (set when solver has run)
    cycle_prediction: object = None   # CycleSolution | None
    # Optional: diagram model (for inline solver fallback in PV-1)
    diagram_model: dict = field(default_factory=dict)


@dataclass
class Finding:
    """A single diagnostic result returned by a scenario's run() method."""
    scenario_id:    str
    label:          str
    component:      str
    severity:       str          # 'CRITICAL' | 'WARNING' | 'WATCH' | 'OK' | 'INFO'
    summary:        str          # one-liner shown on card header
    evidence:       str          # multi-line: values, row counts, slopes
    recommendation: str          # plain-English action steps
    affected_rows:  list = field(default_factory=list)
    uses_trend:     bool = False  # True = all rows used; False = point / window check


# ─── BASE SCENARIO CLASS ──────────────────────────────────────────────────────

class DiagnosticScenario:
    SCENARIO_ID        = ''
    COMPONENT          = ''
    LABEL              = ''
    ENABLED            = True
    DESCRIPTION        = ''   # What is this fault and why does it matter? (2-4 sentences)
    APPLIES_TO: list = ['cassette', 'modular', 'non-modular']  # configs this rule runs on
    LOGIC: str = ''           # template string; {threshold_key} filled at display time
    THRESHOLD_LABELS: dict = {}  # key → human-readable label for threshold spinboxes
    DEFAULT_THRESHOLDS = {}   # key → default value; include units in key name

    def run(self, df, ctx: DiagnosticContext, thresholds: dict) -> list[Finding]:
        """Override in each subclass. Must return a list (empty = nothing fired)."""
        raise NotImplementedError

    # ── Convenience helpers available to all subclasses ──────────────────────

    def t(self, thresholds: dict, key: str):
        """Threshold lookup: user override takes precedence over class default."""
        return thresholds.get(key, self.DEFAULT_THRESHOLDS.get(key))

    def _ok(self, suffix: str = '') -> Finding:
        lbl = f'{self.LABEL} — {suffix}' if suffix else self.LABEL
        return Finding(
            scenario_id=self.SCENARIO_ID, label=lbl,
            component=self.COMPONENT, severity='OK',
            summary='Normal — no issues detected.',
            evidence='', recommendation='',
        )


# ─── HELPER FUNCTIONS ─────────────────────────────────────────────────────────

def _ab(label: str) -> str:
    """'Left'→'lh', 'Center'→'ctr', 'Right'→'rh'"""
    from circuit_semantics import module_abbrev
    return module_abbrev(label)


def _AB(label: str) -> str:
    from circuit_semantics import module_abbrev
    return module_abbrev(label, upper=True)


def _has(df, col: str) -> bool:
    return col in df.columns


def _col(df, col: str):
    """Return Series if column exists, else None."""
    return df[col] if col in df.columns else None


def _window(df, n: int):
    """Last n rows of df (or all rows if df is shorter)."""
    return df.iloc[-n:] if len(df) >= n else df


def _mean(df, col: str, window_n: Optional[int] = None) -> Optional[float]:
    """Mean of column, optionally over last window_n rows. None if missing."""
    s = _col(df if window_n is None else _window(df, window_n), col)
    if s is None:
        return None
    v = float(s.mean(skipna=True))
    return None if v != v else v  # NaN → None


def _slope(df, col: str) -> Optional[float]:
    """Linear regression slope (units/row) over all rows. None if column missing or <3 rows."""
    s = _col(df, col)
    if s is None:
        return None
    y = s.dropna().values
    if len(y) < 3:
        return None
    x = np.arange(len(y), dtype=float)
    try:
        return float(np.polyfit(x, y, 1)[0])
    except Exception:
        return None


def _std(df, col: str) -> Optional[float]:
    """Std dev of column over all rows. None if missing."""
    s = _col(df, col)
    if s is None:
        return None
    v = float(s.std(skipna=True))
    return None if v != v else v


def _pct_below(df, col: str, threshold: float) -> tuple[float, list]:
    """Fraction of non-NaN rows where col < threshold. Also returns row indices."""
    s = _col(df, col)
    if s is None:
        return 0.0, []
    mask = s < threshold
    idx = list(df.index[mask])
    total = s.notna().sum()
    return (len(idx) / max(total, 1)), idx


def _pct_above(df, col: str, threshold: float) -> tuple[float, list]:
    s = _col(df, col)
    if s is None:
        return 0.0, []
    mask = s > threshold
    idx = list(df.index[mask])
    total = s.notna().sum()
    return (len(idx) / max(total, 1)), idx


def _suc_col(ctx: DiagnosticContext, label: str) -> str:
    """Suction pressure column name for a given module label."""
    return f'P_suc-{_ab(label)}' if ctx.system_type == 'cassette' else 'P_suction'


def _disc_col(ctx: DiagnosticContext, label: str) -> str:
    return f'P_disch-{_ab(label)}' if ctx.system_type == 'cassette' else 'P_disch'


def _sh_total_col(ctx: DiagnosticContext, label: str) -> str:
    return f'S.H_total-{_ab(label)}' if ctx.system_type == 'cassette' else 'S.H_total'


def _sc_cond_col(ctx: DiagnosticContext, label: str) -> str:
    """Subcooling at condenser outlet."""
    return f'S.C-{_ab(label)}' if ctx.system_type == 'cassette' else 'S.C'


def _t3a_col(ctx: DiagnosticContext, label: str) -> str:
    return f'T_3a-{_ab(label)}' if ctx.system_type == 'cassette' else 'T_3a'


def _t4a_col(ctx: DiagnosticContext, label: str) -> str:
    return f'T_4a-{_ab(label)}' if ctx.system_type == 'cassette' else 'T_4a'


def _tsat_cond_col(ctx: DiagnosticContext, label: str) -> str:
    return f'T_sat.cond-{_ab(label)}' if ctx.system_type == 'cassette' else 'T_sat.cond'


def _qc_col(ctx: DiagnosticContext, label: str) -> str:
    return f'qc-{_ab(label)}' if ctx.system_type == 'cassette' else 'qc'


def _mdot_col(ctx: DiagnosticContext, label: str) -> str:
    return f'm_dot-{_ab(label)}' if ctx.system_type == 'cassette' else 'm_dot'


def _h_comp_in_col(ctx: DiagnosticContext, label: str) -> str:
    return f'H_comp.in-{_ab(label)}' if ctx.system_type == 'cassette' else 'H_comp.in'


def _t_sat_comp_col(ctx: DiagnosticContext, label: str) -> str:
    return f'T_sat.comp.in-{_ab(label)}' if ctx.system_type == 'cassette' else 'T_sat.comp.in'


def _waterin_col(ctx: DiagnosticContext, label: str) -> str:
    return f'T_waterin-{_ab(label)}' if ctx.system_type == 'cassette' else 'T_waterin'


def _waterout_col(ctx: DiagnosticContext, label: str) -> str:
    return f'T_waterout-{_ab(label)}' if ctx.system_type == 'cassette' else 'T_waterout'


def _t2b_col(ctx: DiagnosticContext, label: str) -> str:
    return f'T_2b-{_ab(label)}' if ctx.system_type == 'cassette' else 'T_2b'


def _t3b_col(ctx: DiagnosticContext, label: str) -> str:
    return f'T_3b-{_ab(label)}' if ctx.system_type == 'cassette' else 'T_3b'


def _t_waterout_col(ctx: DiagnosticContext, label: str) -> str:
    """T_waterout column — cassette: per-unit suffix, shared: global."""
    ab = _ab(label)
    return f'T_waterout-{ab}' if ctx.system_type == 'cassette' else 'T_waterout'


def _t1a_col(label: str) -> str:
    """T_1a-{ab} — TXV outlet / distributor inlet (same naming shared & cassette)."""
    return f'T_1a-{_ab(label)}'


def _t1b_col(label: str) -> str:
    """T_1b-{ab} — coil inlet / post-distributor (same naming shared & cassette)."""
    return f'T_1b-{_ab(label)}'


def _t2a_col(label: str) -> str:
    """T_2a-{AB} — coil outlet (uppercase AB, same naming shared & cassette)."""
    return f'T_2a-{_ab(label).upper()}'


def system_note(ctx: DiagnosticContext) -> str:
    """Returns a human-readable description of the system configuration."""
    n = len(ctx.module_labels)
    if ctx.system_type == 'cassette':
        return f"cassette ({n}-unit, independent circuits)"
    elif n == 1:
        return "non-modular (single-module, shared circuit)"
    else:
        return f"{n}-module shared circuit"


def _sanitize_colname(name: str) -> str:
    """Sanitize a DataFrame column name to a valid Python identifier.

    Examples:
        'S.H_lh coil'  → 'S_H_lh_coil'
        'P_suction'    → 'P_suction'
        'T_sat.comp.in'→ 'T_sat_comp_in'
        'S.H_total-lh' → 'S_H_total_lh'
    """
    return re.sub(r'[^a-zA-Z0-9]+', '_', name).strip('_')


# ─── RF: REFRIGERANT SYSTEM ───────────────────────────────────────────────────

class RF1_RefrigerantLeakTrend(DiagnosticScenario):
    """
    RF-1 · Refrigerant Leak (Trend)
    ================================
    APPROACH:
      Linear regression on SH_total, S.C, P_suction, and qc across ALL rows.
      A refrigerant leak produces a characteristic multi-signal trend:
        - Superheat rising  (less refrigerant → more superheat)
        - Subcooling falling (liquid level in condenser dropping)
        - Suction pressure falling (lower refrigerant density)
        - Capacity falling (less refrigerant mass flow)
      Requires rf1_min_matching_signals of the 4 to trend in the leak direction.

    POINT vs TREND: TREND (all rows — short tests may false-flag, increase min_signals)

    COLUMNS (shared):   S.H_total, S.C, P_suction, qc
    COLUMNS (cassette): S.H_total-{ab}, S.C-{ab}, P_suc-{ab}, qc-{ab} per unit

    THRESHOLDS:
      rf1_sh_slope_f_per_row:    0.10  Min positive SH slope to count
      rf1_sc_slope_f_per_row:    0.05  Min negative SC slope magnitude to count
      rf1_pres_slope_psig_row:   0.02  Min negative pressure slope magnitude
      rf1_qc_slope_btu_row:      1.0   Min negative capacity slope magnitude
      rf1_min_matching_signals:  3     Of 4, how many must trend leak-direction

    FALSE POSITIVES:
      - Short runs with natural transient warm-up can mimic leak trends.
        Increase rf1_min_matching_signals to 4 for stricter detection.
      - Ensure test has reached steady-state before interpreting.

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'RF-1'
    COMPONENT   = 'Refrigerant'
    LABEL       = 'Refrigerant Leak (Trend)'
    DESCRIPTION = (
        "A refrigerant leak causes the system charge mass to fall progressively over time. "
        "As refrigerant escapes, suction pressure drops, superheat rises (gas fills more of the circuit), "
        "subcooling falls (less liquid remaining in the condenser), and cooling capacity declines. "
        "This scenario detects the characteristic multi-signal leak trend using linear regression across all data rows."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • S.H_total — superheat at compressor inlet (°F)\n"
        "  • S.C — subcooling at condenser outlet (°F)\n"
        "  • P_suction / P_suc-{{ab}} — suction pressure (PSIG)\n"
        "  • qc — cooling capacity (BTU/hr)\n"
        "  (cassette: per-unit columns with -{{ab}} suffix)\n"
        "\n"
        "DECISION (linear regression slope over ALL rows):\n"
        "  Count signals trending in leak direction:\n"
        "    SH slope  > +{rf1_sh_slope_f_per_row} °F/row        → rising  ✓\n"
        "    SC slope  < -{rf1_sc_slope_f_per_row} °F/row        → falling ✓\n"
        "    P_suc slope < -{rf1_pres_slope_psig_row} PSIG/row   → falling ✓\n"
        "    qc slope  < -{rf1_qc_slope_btu_row} BTU/hr/row      → falling ✓\n"
        "\n"
        "  CRITICAL  if  all 4 signals match (signals == 4)\n"
        "  WARNING   if  signals >= {rf1_min_matching_signals} (and < 4)\n"
        "  OK        otherwise"
    )
    THRESHOLD_LABELS = {
        'rf1_sh_slope_f_per_row':   'Min SH slope to count as rising (°F/row)',
        'rf1_sc_slope_f_per_row':   'Min SC slope magnitude to count as falling (°F/row)',
        'rf1_pres_slope_psig_row':  'Min P_suc slope magnitude to count as falling (PSIG/row)',
        'rf1_qc_slope_btu_row':     'Min qc slope magnitude to count as falling (BTU/hr/row)',
        'rf1_min_matching_signals': 'Min matching signals required to flag (of 4)',
    }
    DEFAULT_THRESHOLDS = {
        'rf1_sh_slope_f_per_row':   0.10,
        'rf1_sc_slope_f_per_row':   0.05,
        'rf1_pres_slope_psig_row':  0.02,
        'rf1_qc_slope_btu_row':     1.0,
        'rf1_min_matching_signals': 3,
    }
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'at_least', 'min_count': 4, 'conditions': [
            {'column': 'S.H_total',  'function': 'slope', 'operator': '>',  'value': 0.10},
            {'column': 'S.C',        'function': 'slope', 'operator': '<',  'value': -0.05},
            {'column': 'P_suction',  'function': 'slope', 'operator': '<',  'value': -0.02},
            {'column': 'qc',         'function': 'slope', 'operator': '<',  'value': -1.0},
        ]},
        'WARNING': {'join': 'at_least', 'min_count': 3, 'conditions': [
            {'column': 'S.H_total',  'function': 'slope', 'operator': '>',  'value': 0.10},
            {'column': 'S.C',        'function': 'slope', 'operator': '<',  'value': -0.05},
            {'column': 'P_suction',  'function': 'slope', 'operator': '<',  'value': -0.02},
            {'column': 'qc',         'function': 'slope', 'operator': '<',  'value': -1.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        for label in ctx.module_labels:
            ab = _ab(label)
            sh_s  = _slope(df, _sh_total_col(ctx, label))
            sc_s  = _slope(df, _sc_cond_col(ctx, label))
            pr_s  = _slope(df, _suc_col(ctx, label))
            qc_s  = _slope(df, _qc_col(ctx, label))

            if all(v is None for v in [sh_s, sc_s, pr_s, qc_s]):
                continue

            signals = 0
            lines = []
            if sh_s is not None:
                ok = sh_s > self.t(thresholds, 'rf1_sh_slope_f_per_row')
                lines.append(f"  SH slope:  {sh_s:+.3f} °F/row  {'✓ rising' if ok else '—'}")
                if ok: signals += 1
            if sc_s is not None:
                ok = sc_s < -self.t(thresholds, 'rf1_sc_slope_f_per_row')
                lines.append(f"  SC slope:  {sc_s:+.3f} °F/row  {'✓ falling' if ok else '—'}")
                if ok: signals += 1
            if pr_s is not None:
                ok = pr_s < -self.t(thresholds, 'rf1_pres_slope_psig_row')
                lines.append(f"  P_suc slope: {pr_s:+.4f} PSIG/row  {'✓ falling' if ok else '—'}")
                if ok: signals += 1
            if qc_s is not None:
                ok = qc_s < -self.t(thresholds, 'rf1_qc_slope_btu_row')
                lines.append(f"  qc slope:  {qc_s:+.1f} BTU/hr/row  {'✓ falling' if ok else '—'}")
                if ok: signals += 1

            min_sig = self.t(thresholds, 'rf1_min_matching_signals')
            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl = f'{self.LABEL}{" — " + suffix if suffix else ""}'

            if signals >= min_sig:
                sev = 'CRITICAL' if signals == 4 else 'WARNING'
                findings.append(Finding(
                    scenario_id=self.SCENARIO_ID, label=lbl,
                    component=self.COMPONENT, severity=sev, uses_trend=True,
                    summary=f'{signals}/4 leak indicators trending in leak direction over {len(df)} rows.',
                    evidence='\n'.join(lines) + f'\n  Rows analysed: {len(df)}',
                    recommendation=(
                        'LEAK INVESTIGATION STEPS:\n'
                        '1. VISUAL INSPECTION: Inspect all fittings, solder joints, flare connections, '
                        'and service valves for oil residue (oil stain = leak location).\n'
                        '2. ELECTRONIC LEAK DETECTION: Use an electronic refrigerant leak detector '
                        'to sweep all joints, valve stems, and Schrader cores.\n'
                        '3. UV DYE: If UV dye was added at commissioning, use UV light to locate leak.\n'
                        '4. WEIGH CHARGE: Recover refrigerant, weigh, and compare to nameplate.\n'
                        '5. PRESSURE TEST: Perform standing nitrogen pressure test (400 PSIG, 24 hr hold).\n'
                        '6. COMPRESSOR SEAL: Check compressor shaft seal (semi-hermetic) or terminal seal.\n'
                        '7. FALSE POSITIVE: Verify sensor drift is not mimicking a leak trend — '
                        'if only 3/4 signals, re-examine the missing signal for sensor issues.'
                    ),
                ))
            else:
                findings.append(Finding(
                    scenario_id=self.SCENARIO_ID, label=lbl,
                    component=self.COMPONENT, severity='OK', uses_trend=True,
                    summary=f'No significant leak trend detected ({signals}/4 signals).',
                    evidence='\n'.join(lines), recommendation='',
                ))

            if ctx.system_type == 'shared':
                break  # one shared system — only one check needed
        return findings


class RF2_Undercharge(DiagnosticScenario):
    """
    RF-2 · Refrigerant Undercharge (Point)
    ========================================
    APPROACH:
      Point check on latest trend_window_rows. Undercharge signature:
        - SH significantly above target (refrigerant gas filling more of circuit)
        - SC very low (liquid column in condenser depleted)
      Distinct from RF-1: values are persistently out of range, not just trending.

    COLUMNS (shared):   S.H_total, S.C
    COLUMNS (cassette): S.H_total-{ab}, S.C-{ab}

    THRESHOLDS:
      rf2_sh_high_warning_f:  25.0
      rf2_sh_high_critical_f: 40.0
      rf2_sc_low_f:            3.0
      trend_window_rows:       10

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'RF-2'
    COMPONENT   = 'Refrigerant'
    LABEL       = 'Refrigerant Undercharge'
    DESCRIPTION = (
        "Undercharge means the system contains less refrigerant than its design charge. "
        "With insufficient refrigerant mass, the compressor must work with a dilute vapour mixture: "
        "superheat rises as gas fills the evaporator with little heat pickup, and subcooling drops "
        "as the liquid column in the condenser is depleted. This is a point check (persistent high SH + low SC), "
        "distinct from RF-1 (which detects a worsening trend)."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • S.H_total — superheat at compressor inlet (°F)\n"
        "  • S.C — subcooling at condenser outlet (°F)\n"
        "  (cassette: S.H_total-{{ab}}, S.C-{{ab}} per unit)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows):\n"
        "  CRITICAL  if  SH > {rf2_sh_high_critical_f}°F  AND  SC < {rf2_sc_low_f}°F\n"
        "  WARNING   if  SH > {rf2_sh_high_warning_f}°F   AND  SC < {rf2_sc_low_f}°F\n"
        "  WARNING   if  SH > {rf2_sh_high_warning_f}°F   (SC not low — SH alone)\n"
        "  WATCH     if  SH > {rf2_sh_elevated_watch_f}°F AND  SC < {rf2_sc_low_f}°F\n"
        "  OK        otherwise"
    )
    THRESHOLD_LABELS = {
        'rf2_sh_high_warning_f':   'SH WARNING threshold (°F)',
        'rf2_sh_high_critical_f':  'SH CRITICAL threshold (°F)',
        'rf2_sc_low_f':            'SC low limit — corroboration (°F)',
        'rf2_sh_elevated_watch_f': 'SH WATCH threshold (°F)',
        'trend_window_rows':       'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'rf2_sh_high_warning_f':    25.0,
        'rf2_sh_high_critical_f':   40.0,
        'rf2_sc_low_f':              3.0,
        'rf2_sh_elevated_watch_f':  15.0,
        'trend_window_rows':         20,
    }
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'and', 'conditions': [
            {'column': 'S.H_total', 'function': 'mean', 'operator': '>', 'value': 40.0},
            {'column': 'S.C', 'function': 'mean', 'operator': '<', 'value': 3.0},
        ]},
        'WARNING': {'join': 'and', 'conditions': [
            {'column': 'S.H_total', 'function': 'mean', 'operator': '>', 'value': 25.0},
            {'column': 'S.C', 'function': 'mean', 'operator': '<', 'value': 3.0},
        ]},
        'WATCH': {'join': 'and', 'conditions': [
            {'column': 'S.H_total', 'function': 'mean', 'operator': '>', 'value': 15.0},
            {'column': 'S.C', 'function': 'mean', 'operator': '<', 'value': 3.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            ab = _ab(label)
            sh = _mean(df, _sh_total_col(ctx, label), win)
            sc = _mean(df, _sc_cond_col(ctx, label), win)
            if sh is None and sc is None:
                continue

            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl = f'{self.LABEL}{" — " + suffix if suffix else ""}'
            lines = []
            if sh is not None: lines.append(f'  SH_total (avg last {win} rows): {sh:.1f} °F')
            if sc is not None: lines.append(f'  S.C (avg last {win} rows):      {sc:.1f} °F')
            evidence = '\n'.join(lines)

            sh_crit = sh is not None and sh > self.t(thresholds, 'rf2_sh_high_critical_f')
            sh_warn = sh is not None and sh > self.t(thresholds, 'rf2_sh_high_warning_f')
            sc_low  = sc is not None and sc < self.t(thresholds, 'rf2_sc_low_f')

            if sh_crit and sc_low:
                sev, summ = 'CRITICAL', f'SH={sh:.1f}°F (very high) + SC={sc:.1f}°F (very low) — likely undercharged.'
                rec = ('POSSIBLE CAUSES:\n'
                       '1. UNDERCHARGE: Recover and weigh refrigerant — recharge to nameplate weight.\n'
                       '2. PRIOR LEAK: Check leak history. Pressure-test before recharging to avoid repeat.\n'
                       '3. LIQUID LINE RESTRICTION: A partially blocked filter dryer (DI-2) or solenoid '
                       'valve can mimic undercharge symptoms — check SC at TXV inlet.\n'
                       '4. TXV RESTRICTION: A stuck or iced-up TXV starves the evaporator (TX-1).\n'
                       '5. SIGHT GLASS: If equipped, check for bubbles — confirms low liquid level.')
            elif sh_warn and sc_low:
                sev, summ = 'WARNING', f'SH={sh:.1f}°F (elevated) + SC={sc:.1f}°F (low) — possible undercharge.'
                rec = ('Verify refrigerant charge weight — compare to nameplate specification.\n'
                       'Compare SH/SC to commissioning baseline values.\n'
                       'ALSO CHECK: Filter dryer restriction (DI-2), TXV restriction (TX-1), '
                       'or liquid line solenoid valve not fully opening — all can mimic undercharge.')
            elif sh_warn:
                sev, summ = 'WATCH', f'SH={sh:.1f}°F elevated — monitor for further increase.'
                rec = ('Check refrigerant charge and TXV adjustment.\n'
                       'Also check: filter dryer condition (DI-2) and liquid line for restrictions.')
            elif sh is not None and sh > self.t(thresholds, 'rf2_sh_elevated_watch_f') and sc is not None and sc < self.t(thresholds, 'rf2_sc_low_f'):
                sev  = 'WATCH'
                summ = f'SH={sh:.1f}°F elevated + SC={sc:.1f}°F low — possible mild undercharge.'
                rec  = ('Monitor system for worsening SH trend.\n'
                        'Consider adding refrigerant in 0.1 lb steps if qc is below target.\n'
                        'Allow 15 min stabilisation after each addition before re-evaluating.')
                findings.append(Finding(
                    scenario_id=self.SCENARIO_ID, label=lbl, component=self.COMPONENT,
                    severity=sev, summary=summ, evidence=evidence, recommendation=rec,
                ))
                if ctx.system_type == 'shared':
                    break
                continue
            else:
                findings.append(Finding(
                    scenario_id=self.SCENARIO_ID, label=lbl,
                    component=self.COMPONENT, severity='OK',
                    summary='SH and SC within normal range.', evidence=evidence, recommendation='',
                ))
                if ctx.system_type == 'shared': break
                continue

            findings.append(Finding(
                scenario_id=self.SCENARIO_ID, label=lbl,
                component=self.COMPONENT, severity=sev,
                summary=summ, evidence=evidence, recommendation=rec,
            ))
            if ctx.system_type == 'shared':
                break
        return findings


class RF3_Overcharge(DiagnosticScenario):
    """
    RF-3 · Refrigerant Overcharge (Point)
    =======================================
    APPROACH:
      Point check. Overcharge signature:
        - SC very high (excess liquid backed up in condenser)
        - High condensing pressure / discharge pressure
        - Possible low SH alongside high SC (liquid flood-back to suction)

    COLUMNS (shared):   S.C, P_disch, S.H_total
    COLUMNS (cassette): S.C-{ab}, P_disch-{ab}, S.H_total-{ab}

    THRESHOLDS:
      rf3_sc_high_warning_f:  20.0
      rf3_sc_high_critical_f: 30.0
      trend_window_rows:       10

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'RF-3'
    COMPONENT   = 'Refrigerant'
    LABEL       = 'Refrigerant Overcharge'
    DESCRIPTION = (
        "Overcharge means the system contains more refrigerant than its design charge. "
        "Excess liquid floods the condenser, raising subcooling far above normal. "
        "In severe cases, liquid can reach the compressor (flood-back). "
        "High SC alone can also result from an oversized condenser, so this check requires a "
        "corroborating signal (elevated discharge pressure or low superheat) before escalating beyond WATCH."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • S.C — subcooling at condenser outlet (°F)\n"
        "  • S.H_total — superheat at compressor inlet (°F) [corroboration]\n"
        "  • P_disch — discharge pressure (PSIG) [corroboration]\n"
        "  (cassette: per-unit columns with -{{ab}} suffix)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows):\n"
        "  Corroborating signal = SH < {rf3_sh_low_corroborate_f}°F  OR  P_disch > {rf3_p_disch_elevated_psig} PSIG\n"
        "\n"
        "  CRITICAL  if  SC > {rf3_sc_high_critical_f}°F  AND  corroborating signal present\n"
        "  WARNING   if  SC > {rf3_sc_high_warning_f}°F   AND  corroborating signal present\n"
        "  WATCH     if  SC > {rf3_sc_high_warning_f}°F   (no corroborating signal — possible oversized condenser)\n"
        "  OK        otherwise"
    )
    THRESHOLD_LABELS = {
        'rf3_sc_high_warning_f':     'SC WARNING threshold (°F)',
        'rf3_sc_high_critical_f':    'SC CRITICAL threshold (°F)',
        'rf3_sh_low_corroborate_f':  'SH corroboration limit — low SH confirms overcharge (°F)',
        'rf3_p_disch_elevated_psig': 'P_disch corroboration limit — elevated discharge (PSIG)',
        'trend_window_rows':         'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'rf3_sc_high_warning_f':     20.0,
        'rf3_sc_high_critical_f':    30.0,
        'rf3_sh_low_corroborate_f':  15.0,
        'rf3_p_disch_elevated_psig': 260.0,
        'trend_window_rows':          20,
    }
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'and', 'conditions': [
            {'column': 'S.C',       'function': 'mean', 'operator': '>',  'value': 30.0},
            {'column': 'S.H_total', 'function': 'mean', 'operator': '<',  'value': 15.0},
        ]},
        'WARNING': {'join': 'and', 'conditions': [
            {'column': 'S.C',       'function': 'mean', 'operator': '>',  'value': 20.0},
            {'column': 'S.H_total', 'function': 'mean', 'operator': '<',  'value': 15.0},
        ]},
        'WATCH': {'join': 'and', 'conditions': [
            {'column': 'S.C', 'function': 'mean', 'operator': '>', 'value': 20.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            sc      = _mean(df, _sc_cond_col(ctx, label), win)
            sh      = _mean(df, _sh_total_col(ctx, label), win)
            p_disch = _mean(df, _disc_col(ctx, label), win)
            if sc is None:
                continue
            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl = f'{self.LABEL}{" — " + suffix if suffix else ""}'
            lines = [
                'Why: Elevated SC with corroborating pressure or SH signal confirms excess refrigerant charge.',
                f'  S.C (avg last {win} rows): {sc:.1f} °F',
            ]
            if sh is not None:      lines.append(f'  S.H_total (avg):           {sh:.1f} °F')
            if p_disch is not None: lines.append(f'  P_disch (avg):             {p_disch:.1f} PSIG')

            # High SC alone can mean oversized condenser — require corroboration
            corroborating = (
                (sh is not None and sh < self.t(thresholds, 'rf3_sh_low_corroborate_f')) or
                (p_disch is not None and p_disch > self.t(thresholds, 'rf3_p_disch_elevated_psig'))
            )

            if sc > self.t(thresholds, 'rf3_sc_high_critical_f') and corroborating:
                sev = 'CRITICAL'
                summ = f'SC={sc:.1f}°F — severely overcharged. Risk of liquid flood-back.'
                rec = ('POSSIBLE CAUSES:\n'
                       '1. OVERCHARGE: Recover excess refrigerant and reweigh. Do NOT run until corrected.\n'
                       '2. WRONG REFRIGERANT TYPE: Verify the correct refrigerant (R290) was charged — '
                       'a different refrigerant with different saturation properties could explain high SC.\n'
                       '3. LIQUID RECEIVER FLOODING: If system has a receiver, it may be overfull, '
                       'flooding liquid into the condenser tubes.\n'
                       '4. VERY COLD WATER: Unusually low T_waterin (cold water supply) can cause '
                       'high SC without overcharge — check CD-1 approach temp.')
            elif sc > self.t(thresholds, 'rf3_sc_high_warning_f') and corroborating:
                sev = 'WARNING'
                summ = f'SC={sc:.1f}°F — possibly overcharged.'
                rec = ('Recover and reweigh refrigerant charge — compare to nameplate specification.\n'
                       'Also check: oversized condenser can show high SC without actual overcharge.\n'
                       'Verify water inlet temperature is at design conditions.')
            elif sc > self.t(thresholds, 'rf3_sc_high_warning_f') and not corroborating:
                sev = 'WATCH'
                summ = f'SC={sc:.1f}°F elevated but no corroborating pressure/SH signal — possible oversized condenser.'
                rec = 'Check condenser approach temperature. If approach is very low, condenser may be oversized rather than overcharged.'
            else:
                findings.append(self._ok(suffix))
                if ctx.system_type == 'shared': break
                continue

            findings.append(Finding(
                scenario_id=self.SCENARIO_ID, label=lbl,
                component=self.COMPONENT, severity=sev,
                summary=summ, evidence='\n'.join(lines), recommendation=rec,
            ))
            if ctx.system_type == 'shared':
                break
        return findings


class RF4_NonCondensables(DiagnosticScenario):
    """
    RF-4 · Non-Condensables in System (Point)
    ===========================================
    APPROACH:
      Non-condensable gases (air, nitrogen) raise discharge pressure above what
      the condensing temperature alone would predict. CoolProp is used to compute
      the saturation pressure at T_3b (condenser inlet gas temperature). If the
      actual P_disch exceeds P_sat(T_3b) significantly, non-condensables are
      suspected — they add partial pressure on top of the refrigerant saturation
      pressure.
      Note: This replaces the earlier approach-temp duplicate of CD-1 with a
      physically distinct CoolProp-based check.

    COLUMNS (shared):   T_3b, P_disch
    COLUMNS (cassette): T_3b-{ab}, P_disch-{ab}

    THRESHOLDS:
      rf4_excess_pressure_warning_psig:  15.0
      rf4_excess_pressure_critical_psig: 30.0
      trend_window_rows:                 20

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
      - 2026-03-05: Replaced approach-temp duplicate with CoolProp P_sat check.
    """
    SCENARIO_ID = 'RF-4'
    COMPONENT   = 'Refrigerant'
    LABEL       = 'Non-Condensables Suspected'
    DESCRIPTION = (
        "Non-condensable gases (air, nitrogen from pressure testing) occupy volume in the condenser "
        "but cannot condense, so they raise discharge pressure above the saturation pressure corresponding "
        "to the condenser inlet temperature. This check uses CoolProp to compute the expected saturation "
        "pressure at T_3b (condenser inlet gas temp) and compares it to actual P_disch — excess pressure "
        "indicates non-condensables."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • T_3b — condenser inlet gas temperature (°F)\n"
        "  • P_disch — discharge pressure (PSIG)\n"
        "  (cassette: T_3b-{{ab}}, P_disch-{{ab}} per unit)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows):\n"
        "  P_sat = CoolProp saturation pressure at T_3b (R290), converted to PSIG\n"
        "  Excess = P_disch - P_sat\n"
        "\n"
        "  CRITICAL  if  Excess > {rf4_excess_pressure_critical_psig} PSIG\n"
        "  WARNING   if  Excess > {rf4_excess_pressure_warning_psig} PSIG\n"
        "  OK        otherwise"
    )
    THRESHOLD_LABELS = {
        'rf4_excess_pressure_warning_psig':  'Excess pressure WARNING threshold (PSIG)',
        'rf4_excess_pressure_critical_psig': 'Excess pressure CRITICAL threshold (PSIG)',
        'trend_window_rows':                 'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'rf4_excess_pressure_warning_psig':  15.0,
        'rf4_excess_pressure_critical_psig': 30.0,
        'trend_window_rows':                 20,
    }
    # RF-4 requires CoolProp to compute P_sat(T_3b) — cannot be expressed as a
    # simple column comparison in the expression sandbox. Falls back to Python run().
    DEFAULT_EXPRESSIONS = {}

    def run(self, df, ctx, thresholds):
        try:
            from CoolProp.CoolProp import PropsSI
        except ImportError:
            return []
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            t3b    = _mean(df, _t3b_col(ctx, label), win)
            p_disch = _mean(df, _disc_col(ctx, label), win)
            if t3b is None or p_disch is None:
                continue
            # Compute saturation pressure at T_3b (condenser inlet gas temperature)
            t3b_k = (t3b - 32.0) * 5.0 / 9.0 + 273.15
            try:
                p_sat_pa   = PropsSI('P', 'T', t3b_k, 'Q', 1, 'R290')
                p_sat_psig = p_sat_pa / 6894.757 - 14.696
            except Exception:
                continue
            excess = p_disch - p_sat_psig
            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl    = f'{self.LABEL}{" — " + suffix if suffix else ""}'
            lines  = [
                'Why: P_disch exceeding P_sat(T_3b) proves non-condensable gas is occupying condenser volume.',
                f'  T_3b (condenser inlet gas): {t3b:.1f} °F',
                f'  P_sat at T_3b:              {p_sat_psig:.1f} PSIG',
                f'  P_disch actual:             {p_disch:.1f} PSIG',
                f'  Excess pressure:            {excess:.1f} PSIG',
            ]
            if excess > self.t(thresholds, 'rf4_excess_pressure_critical_psig'):
                sev  = 'CRITICAL'
                summ = f'P_disch exceeds P_sat(T_3b) by {excess:.1f} PSIG — significant non-condensables.'
                rec  = ('POSSIBLE CAUSES:\n'
                        '1. AIR INGRESS: Air entered during servicing — recover, evacuate to 500 microns, '
                        'and recharge.\n'
                        '2. MOISTURE CONTAMINATION: Moisture decomposes oil and creates acids. Replace '
                        'filter dryer. Pull deep vacuum (below 500 microns for 30+ min) before recharging.\n'
                        '3. WRONG REFRIGERANT: Mixed refrigerant types produce unexpected P-T behavior. '
                        'Recover and verify refrigerant purity with analyzer.\n'
                        '4. OIL LOGGING: Excessive oil in condenser tubes raises effective condensing pressure. '
                        'Check oil return to compressor.\n'
                        '5. Perform standing nitrogen pressure test (400 PSIG, 24 hr) after repair.')
            elif excess > self.t(thresholds, 'rf4_excess_pressure_warning_psig'):
                sev  = 'WARNING'
                summ = f'P_disch exceeds P_sat(T_3b) by {excess:.1f} PSIG — possible non-condensables.'
                rec  = ('POSSIBLE CAUSES:\n'
                        '1. AIR INGRESS: Check system for air or nitrogen ingress through '
                        'service valve packing or loose Schrader cores.\n'
                        '2. RECENT SERVICE: If recently serviced, verify deep vacuum was achieved '
                        'before charging. Inadequate evacuation leaves air in the system.\n'
                        '3. MIXED REFRIGERANTS: Small amount of wrong refrigerant mixed in can '
                        'raise pressure above expected T_sat. Verify purity.\n'
                        '4. SENSOR ERROR: P_disch transducer may read high — compare to manifold gauge.')
            else:
                findings.append(self._ok(suffix))
                if ctx.system_type == 'shared':
                    break
                continue
            findings.append(Finding(
                scenario_id=self.SCENARIO_ID, label=lbl, component=self.COMPONENT,
                severity=sev, summary=summ, evidence='\n'.join(lines), recommendation=rec,
            ))
            if ctx.system_type == 'shared':
                break
        return findings


# ─── CP: COMPRESSOR ───────────────────────────────────────────────────────────

class CP1_LiquidSluggingRisk(DiagnosticScenario):
    """
    CP-1 · Liquid Slugging Risk (Point)
    =====================================
    APPROACH:
      SH at compressor inlet below danger threshold means liquid refrigerant
      may be entering the compressor — mechanical damage risk.

    COLUMNS (shared):   S.H_total
    COLUMNS (cassette): S.H_total-{ab}

    THRESHOLDS:
      cp1_sh_critical_f: 0.0   At or below → CRITICAL (liquid at inlet)
      cp1_sh_warning_f:  5.0   Below → WARNING (dangerously low)
      trend_window_rows: 10

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'CP-1'
    COMPONENT   = 'Compressor'
    LABEL       = 'Liquid Slugging Risk'
    DESCRIPTION = (
        "Liquid slugging occurs when liquid refrigerant (not vapour) enters the compressor. "
        "Compressors are designed to compress gas only — liquid is incompressible and will destroy "
        "valve reeds, pistons, or scroll tips within seconds. "
        "Superheat at the compressor inlet is the critical guard: SH > 0°F means all refrigerant "
        "has evaporated. When SH approaches 0°F, liquid carry-over is imminent."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • S.H_total — superheat at compressor inlet (°F)\n"
        "  (cassette: S.H_total-{{ab}} per unit)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows):\n"
        "  CRITICAL  if  SH <= {cp1_sh_critical_f}°F  (liquid at inlet — immediate risk)\n"
        "  WARNING   if  SH <  {cp1_sh_warning_f}°F   (dangerously low)\n"
        "  OK        otherwise"
    )
    THRESHOLD_LABELS = {
        'cp1_sh_critical_f': 'SH CRITICAL threshold — liquid carry-over (°F)',
        'cp1_sh_warning_f':  'SH WARNING threshold — dangerously low (°F)',
        'trend_window_rows': 'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'cp1_sh_critical_f': 0.0,
        'cp1_sh_warning_f':  5.0,
        'trend_window_rows': 20,
    }
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'and', 'conditions': [
            {'column': 'S.H_total', 'function': 'mean', 'operator': '<=', 'value': 0.0},
        ]},
        'WARNING': {'join': 'and', 'conditions': [
            {'column': 'S.H_total', 'function': 'mean', 'operator': '<', 'value': 5.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            sh = _mean(df, _sh_total_col(ctx, label), win)
            if sh is None:
                continue
            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl = f'{self.LABEL}{" — " + suffix if suffix else ""}'
            evidence = f'  SH_total (avg last {win} rows): {sh:.1f} °F'

            if sh <= self.t(thresholds, 'cp1_sh_critical_f'):
                sev = 'CRITICAL'
                summ = f'SH={sh:.1f}°F — liquid refrigerant at compressor inlet. Immediate risk.'
                rec = ('STOP THE TEST — liquid refrigerant entering the compressor will destroy it within minutes.\n'
                       '1. Shut down the compressor immediately.\n'
                       '2. Check TXV superheat setting — increase by 3-5°F.\n'
                       '3. Verify TXV bulb is not damaged or detached (TX-2).\n'
                       '4. Check refrigerant charge level — overcharge causes flooding (RF-3).\n'
                       '5. REFRIGERANT MIGRATION: After extended off-cycle, liquid refrigerant migrates '
                       'to the compressor crankcase. Verify crankcase heater operation (if applicable).\n'
                       '6. SUCTION ACCUMULATOR: If fitted, check it is not saturated or bypassed.\n'
                       '7. Do not restart until SH is confirmed above 10°F at steady state.')
            elif sh < self.t(thresholds, 'cp1_sh_warning_f'):
                sev = 'WARNING'
                summ = f'SH={sh:.1f}°F — dangerously low, liquid carry-over risk.'
                rec = ('Adjust TXV to increase superheat target.\n'
                       'Check refrigerant charge and TXV bulb placement/condition.\n'
                       'Monitor closely — if SH continues to drop, stop test.')
            else:
                findings.append(self._ok(suffix))
                if ctx.system_type == 'shared': break
                continue

            findings.append(Finding(
                scenario_id=self.SCENARIO_ID, label=lbl, component=self.COMPONENT,
                severity=sev, summary=summ, evidence=evidence, recommendation=rec,
            ))
            if ctx.system_type == 'shared':
                break
        return findings


class CP2_CompressorOverheating(DiagnosticScenario):
    """
    CP-2 · Compressor Overheating (Point)
    =======================================
    APPROACH:
      High discharge temperature (T_3a) indicates compressor overheating.
      For R290, max recommended discharge temp is ~250°F. High PR compounds severity.

    COLUMNS (shared):   T_3a, P_disch, P_suction
    COLUMNS (cassette): T_3a-{ab}, P_disch-{ab}, P_suc-{ab}

    THRESHOLDS:
      cp2_discharge_temp_warning_f:  220.0
      cp2_discharge_temp_critical_f: 260.0
      trend_window_rows:              10

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'CP-2'
    COMPONENT   = 'Compressor'
    LABEL       = 'Compressor Overheating'
    DESCRIPTION = (
        "High discharge temperature (T_3a) indicates the compressor is working harder than designed: "
        "the hot compressed gas leaving the compressor is excessively hot. "
        "For R290, the recommended discharge temperature limit is approximately 250–260°F. "
        "Causes include very high superheat at suction (hot gas in = hotter gas out), "
        "high compression ratio, or poor compressor cooling. Sustained overheating degrades oil and "
        "accelerates bearing wear."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • T_3a — discharge temperature at compressor outlet (°F)\n"
        "  (cassette: T_3a-{{ab}} per unit)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows):\n"
        "  CRITICAL  if  T_3a > {cp2_discharge_temp_critical_f}°F\n"
        "  WARNING   if  T_3a > {cp2_discharge_temp_warning_f}°F\n"
        "  OK        otherwise"
    )
    THRESHOLD_LABELS = {
        'cp2_discharge_temp_warning_f':  'Discharge temp WARNING threshold (°F)',
        'cp2_discharge_temp_critical_f': 'Discharge temp CRITICAL threshold (°F)',
        'trend_window_rows':             'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'cp2_discharge_temp_warning_f':  220.0,
        'cp2_discharge_temp_critical_f': 260.0,
        'trend_window_rows':              20,
    }
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'and', 'conditions': [
            {'column': 'T_3a', 'function': 'mean', 'operator': '>', 'value': 260.0},
        ]},
        'WARNING': {'join': 'and', 'conditions': [
            {'column': 'T_3a', 'function': 'mean', 'operator': '>', 'value': 220.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            t3a = _mean(df, _t3a_col(ctx, label), win)
            if t3a is None:
                continue
            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl = f'{self.LABEL}{" — " + suffix if suffix else ""}'
            evidence = f'  T_3a (discharge temp, avg last {win} rows): {t3a:.1f} °F'

            if t3a > self.t(thresholds, 'cp2_discharge_temp_critical_f'):
                sev = 'CRITICAL'
                summ = f'T_3a={t3a:.1f}°F — compressor critically overheating (R290 limit ~260°F).'
                rec = ('STOP TEST. POSSIBLE CAUSES:\n'
                       '1. REFRIGERANT UNDERCHARGE: Low charge causes high superheat, which directly '
                       'raises discharge temp — check RF-2 and weigh charge.\n'
                       '2. HIGH COMPRESSION RATIO: Excessive head pressure from condenser fouling (CD-1) '
                       'or low suction from restriction. Check CP-6.\n'
                       '3. SUCTION LINE HEAT GAIN: Poor insulation on the suction line raises return gas '
                       'temperature — check SL-1.\n'
                       '4. COMPRESSOR MOTOR ISSUE: Check for phase imbalance, low voltage, or missing '
                       'phase — electrical problems cause motor overheating.\n'
                       '5. MOTOR COOLING FAN: If the compressor has an external cooling fan, verify it is '
                       'running and airflow is not obstructed.\n'
                       '6. OIL ISSUES: Low oil level or wrong oil type reduces lubrication and increases '
                       'friction heat. Check oil sight glass if accessible.\n'
                       '7. HIGH AMBIENT: If compressor is in an uncooled space, ambient heat adds to discharge temp.\n'
                       '8. NON-CONDENSABLES: Air/nitrogen in circuit raises head pressure and discharge temp (RF-4).')
            elif t3a > self.t(thresholds, 'cp2_discharge_temp_warning_f'):
                sev = 'WARNING'
                summ = f'T_3a={t3a:.1f}°F — elevated discharge temperature.'
                rec = ('POSSIBLE CAUSES:\n'
                       '1. ELEVATED SUPERHEAT: Check SH at compressor inlet (CP-1) — if high, adjust TXV.\n'
                       '2. REFRIGERANT CHARGE: Verify charge against nameplate (RF-2).\n'
                       '3. HIGH CONDENSING PRESSURE: Check condenser performance (CD-1) and water flow (CD-2).\n'
                       '4. SUCTION LINE INSULATION: Check for degraded insulation adding heat (SL-1).\n'
                       '5. ELECTRICAL: Check voltage and phase balance at compressor terminals.')
            else:
                findings.append(self._ok(suffix))
                if ctx.system_type == 'shared': break
                continue

            findings.append(Finding(
                scenario_id=self.SCENARIO_ID, label=lbl, component=self.COMPONENT,
                severity=sev, summary=summ, evidence=evidence, recommendation=rec,
            ))
            if ctx.system_type == 'shared':
                break
        return findings


class CP3_NotCompressing(DiagnosticScenario):
    """
    CP-3 · Compressor Not Compressing (Point)
    ===========================================
    APPROACH:
      If pressure ratio (P_disch_abs / P_suc_abs) < minimum threshold,
      the compressor is not doing meaningful work. Catastrophic failure indicator.
      Pressures converted from PSIG to absolute (add 14.696).

    COLUMNS (shared):   P_disch, P_suction
    COLUMNS (cassette): P_disch-{ab}, P_suc-{ab}

    THRESHOLDS:
      cp3_pr_critical: 1.5   Below → compressor not compressing

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'CP-3'
    COMPONENT   = 'Compressor'
    LABEL       = 'Compressor Not Compressing'
    DESCRIPTION = (
        "If suction and discharge pressure are nearly equal, the compressor is not creating a pressure "
        "differential — it is not compressing. This can indicate a failed compressor (mechanical fault, "
        "broken valves), a stuck or open bypass valve, or a catastrophic refrigerant short-circuit. "
        "This is a critical safety finding: running in this state wastes energy and may damage the compressor further."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • P_disch — discharge pressure (PSIG)\n"
        "  • P_suction / P_suc-{{ab}} — suction pressure (PSIG)\n"
        "  (cassette: per-unit columns with -{{ab}} suffix)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows):\n"
        "  Pressure Ratio (PR) = (P_disch + 14.696) / (P_suction + 14.696)  [absolute pressures]\n"
        "\n"
        "  CRITICAL  if  PR < {cp3_pr_critical}  (compressor not compressing)\n"
        "  OK        otherwise"
    )
    THRESHOLD_LABELS = {
        'cp3_pr_critical': 'Pressure ratio CRITICAL threshold (minimum normal ratio)',
        'trend_window_rows': 'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {'cp3_pr_critical': 1.5, 'trend_window_rows': 20}
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'and', 'conditions': [
            {'column': 'P_disch', 'column2': 'P_suction', 'function': 'pressure_ratio', 'operator': '<', 'value': 1.5},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            pd_ = _mean(df, _disc_col(ctx, label), win)
            ps  = _mean(df, _suc_col(ctx, label), win)
            if pd_ is None or ps is None:
                continue
            pr = (pd_ + 14.696) / max(ps + 14.696, 0.1)
            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl = f'{self.LABEL}{" — " + suffix if suffix else ""}'
            evidence = (f'  P_disch: {pd_:.1f} PSIG | P_suction: {ps:.1f} PSIG\n'
                        f'  Pressure ratio (abs): {pr:.2f}')

            if pr < self.t(thresholds, 'cp3_pr_critical'):
                findings.append(Finding(
                    scenario_id=self.SCENARIO_ID, label=lbl, component=self.COMPONENT,
                    severity='CRITICAL',
                    summary=f'Pressure ratio = {pr:.2f} — compressor not compressing.',
                    evidence=evidence,
                    recommendation=('STOP TEST. POSSIBLE CAUSES:\n'
                                    '1. MECHANICAL FAILURE: Broken reed valves (reciprocating), worn piston rings, '
                                    'or scroll set separation (scroll compressor) — listen for unusual noise.\n'
                                    '2. INTERNAL BYPASS STUCK OPEN: Some compressors have an internal capacity '
                                    'control or relief valve that may be stuck open.\n'
                                    '3. ELECTRICAL FAILURE: Check power supply, control board, and contactor. '
                                    'Verify compressor motor is actually running (check amp draw).\n'
                                    '4. LIQUID SLUGGING DAMAGE: Prior liquid slugging (CP-1) may have damaged '
                                    'internal components. Check operating history.\n'
                                    '5. SENSOR ERROR: Verify both pressure transducer connections are correct — '
                                    'suction and discharge sensors may be swapped or disconnected.\n'
                                    '6. CHECK AMP DRAW: Compare actual compressor amp draw to rated amps. '
                                    'Low amps with motor running confirms mechanical failure.'),
                ))
            else:
                findings.append(self._ok(suffix))
            if ctx.system_type == 'shared':
                break
        return findings


class CP4_PressureRatioExtreme(DiagnosticScenario):
    """
    CP-4 · Extreme Pressure Ratio — Sensor Error Suspected (Point)
    ================================================================
    APPROACH:
      Pressure ratio above a physically plausible maximum for R290 commercial
      refrigeration indicates a sensor error (suction reading too low, or
      discharge reading too high).

    THRESHOLDS:
      cp4_pr_high: 10.0

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'CP-4'
    COMPONENT   = 'Compressor'
    LABEL       = 'Extreme Pressure Ratio — Sensor Error?'
    DESCRIPTION = (
        "Compression ratio (P_disch_abs / P_suc_abs) above 10:1 is physically implausible for "
        "R290 under normal lab conditions and almost certainly indicates a sensor error: a bad "
        "pressure transducer, wrong port mapping in the Diagram tab, or a disconnected sensor "
        "reading near zero. This check guards against downstream calculations producing nonsense results."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • P_disch — discharge pressure (PSIG)\n"
        "  • P_suction / P_suc-{{ab}} — suction pressure (PSIG)\n"
        "  (cassette: per-unit columns with -{{ab}} suffix)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows):\n"
        "  Pressure Ratio (PR) = (P_disch + 14.696) / (P_suction + 14.696)  [absolute pressures]\n"
        "\n"
        "  WARNING   if  PR > {cp4_pr_high}  (physically implausible — likely sensor fault)\n"
        "  OK        otherwise"
    )
    THRESHOLD_LABELS = {
        'cp4_pr_high':     'Pressure ratio WARNING threshold (max plausible ratio)',
        'trend_window_rows': 'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {'cp4_pr_high': 10.0, 'trend_window_rows': 20}
    DEFAULT_EXPRESSIONS = {
        'WARNING': {'join': 'and', 'conditions': [
            {'column': 'P_disch', 'column2': 'P_suction', 'function': 'pressure_ratio', 'operator': '>', 'value': 10.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            pd_ = _mean(df, _disc_col(ctx, label), win)
            ps  = _mean(df, _suc_col(ctx, label), win)
            if pd_ is None or ps is None:
                continue
            pr = (pd_ + 14.696) / max(ps + 14.696, 0.1)
            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl = f'{self.LABEL}{" — " + suffix if suffix else ""}'
            if pr > self.t(thresholds, 'cp4_pr_high'):
                findings.append(Finding(
                    scenario_id=self.SCENARIO_ID, label=lbl, component=self.COMPONENT,
                    severity='WARNING',
                    summary=f'Pressure ratio = {pr:.1f} — physically implausible, check sensors.',
                    evidence=f'  P_disch: {pd_:.1f} PSIG | P_suction: {ps:.1f} PSIG\n  PR(abs): {pr:.2f}',
                    recommendation=('POSSIBLE CAUSES:\n'
                                    '1. SENSOR SWAP: Suction and discharge pressure sensors may be connected '
                                    'to the wrong ports — verify wiring.\n'
                                    '2. TRANSDUCER CALIBRATION: One or both sensors may have drifted. Compare '
                                    'to known-good gauge readings.\n'
                                    '3. WRONG TRANSDUCER RANGE: A suction sensor rated 0-100 PSIG on a 0-500 '
                                    'channel (or vice versa) will produce scaled-up or scaled-down readings.\n'
                                    '4. ZERO OFFSET: Pressure transducer zero drift can make one reading '
                                    'artificially high/low. Re-zero both sensors.'),
                ))
            else:
                findings.append(self._ok(suffix))
            if ctx.system_type == 'shared':
                break
        return findings


class CP5_DischargeTempTrend(DiagnosticScenario):
    """
    CP-5 · Compressor Discharge Temp Trending Up (Trend)
    ======================================================
    APPROACH:
      Positive slope of T_3a across all rows indicates gradual degradation:
      refrigerant loss, poor lubrication, or increasing suction restriction.

    COLUMNS (shared):   T_3a
    COLUMNS (cassette): T_3a-{ab}

    THRESHOLDS:
      cp5_discharge_slope_f_row: 0.2   Min positive slope to flag

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'CP-5'
    COMPONENT   = 'Compressor'
    LABEL       = 'Discharge Temp Trending Up'
    DESCRIPTION = (
        "A rising discharge temperature trend over time (even if not yet above the absolute limit) "
        "indicates the compressor is progressively working harder. "
        "This can be caused by a developing refrigerant leak (rising suction SH), condenser fouling "
        "(rising compression ratio), or oil breakdown reducing lubrication. "
        "Catching the trend early allows intervention before the compressor reaches a critical temperature."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • T_3a — discharge temperature at compressor outlet (°F)\n"
        "  (cassette: T_3a-{{ab}} per unit)\n"
        "\n"
        "DECISION (linear regression slope over ALL rows):\n"
        "  WATCH  if  T_3a slope > +{cp5_discharge_slope_f_row} °F/row  (rising trend)\n"
        "  OK     otherwise"
    )
    THRESHOLD_LABELS = {
        'cp5_discharge_slope_f_row': 'Discharge temp slope WATCH threshold (°F/row)',
    }
    DEFAULT_THRESHOLDS = {'cp5_discharge_slope_f_row': 0.2}
    DEFAULT_EXPRESSIONS = {
        'WATCH': {'join': 'and', 'conditions': [
            {'column': 'T_3a', 'function': 'slope', 'operator': '>', 'value': 0.2},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        for label in ctx.module_labels:
            s = _slope(df, _t3a_col(ctx, label))
            if s is None:
                continue
            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl = f'{self.LABEL}{" — " + suffix if suffix else ""}'
            if s > self.t(thresholds, 'cp5_discharge_slope_f_row'):
                findings.append(Finding(
                    scenario_id=self.SCENARIO_ID, label=lbl, component=self.COMPONENT,
                    severity='WATCH', uses_trend=True,
                    summary=f'T_3a rising at {s:.2f} °F/row over {len(df)} rows.',
                    evidence=f'  T_3a slope: {s:+.3f} °F/row | rows: {len(df)}',
                    recommendation=('Monitor for further increase — may indicate developing problem.\n'
                                    'POSSIBLE CAUSES:\n'
                                    '1. DEVELOPING LEAK: Gradual charge loss raises superheat → raises discharge temp. '
                                    'Check RF-1/RF-2.\n'
                                    '2. CONDENSER DEGRADATION: Gradual fouling raises head pressure. Check CD-1.\n'
                                    '3. SUCTION RESTRICTION: Filter dryer or TXV may be partially blocking flow (DI-2, TX-1).\n'
                                    '4. OIL LEVEL: Low oil increases friction heat. Check oil sight glass if accessible.\n'
                                    '5. ELECTRICAL: Check for voltage drop or phase imbalance at compressor terminals.'),
                ))
            else:
                findings.append(self._ok(suffix))
            if ctx.system_type == 'shared':
                break
        return findings


class CP6_HighCompressionRatio(DiagnosticScenario):
    """
    CP-6 · High Compression Ratio (Point)
    =======================================
    APPROACH:
      Compression ratio CR = (P_disch + 14.696) / (P_suction + 14.696).
      R290 scroll compressors typically rated for CR 3–5.5. High CR reduces
      volumetric efficiency, raises discharge temperature, and increases
      mechanical stress. CP-4 catches impossible ratios (>10); this catches
      the operational warning range (5.5–10).

    COLUMNS (shared):   P_suction, P_disch
    COLUMNS (cassette): P_suc-{ab}, P_disch-{ab}

    THRESHOLDS:
      cp6_cr_watch:      5.5
      cp6_cr_warning:    8.0
      trend_window_rows: 20

    UPDATE LOG:
      - 2026-03-05: Initial implementation. Fills the gap between normal operations
                    and CP-4's extreme ratio check.
    """
    SCENARIO_ID = 'CP-6'
    COMPONENT   = 'Compressor'
    LABEL       = 'High Compression Ratio'
    DESCRIPTION = (
        "Compression ratio (CR) is the ratio of absolute discharge pressure to absolute suction pressure. "
        "R290 scroll compressors are typically rated for CR 3–5.5. High CR reduces volumetric efficiency, "
        "raises discharge temperature, and increases mechanical stress on valves and bearings. "
        "This check covers the operational warning range (5.5–10:1); CR > 10 is caught by CP-4 as a "
        "likely sensor error."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • P_suction / P_suc-{{ab}} — suction pressure (PSIG)\n"
        "  • P_disch / P_disch-{{ab}} — discharge pressure (PSIG)\n"
        "  (cassette: per-unit columns with -{{ab}} suffix)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows):\n"
        "  CR = (P_disch + 14.696) / (P_suction + 14.696)  [absolute pressures]\n"
        "\n"
        "  WARNING  if  CR > {cp6_cr_warning}:1  (high mechanical stress)\n"
        "  WATCH    if  CR > {cp6_cr_watch}:1    (elevated — normal range 3–5.5:1)\n"
        "  OK       otherwise"
    )
    THRESHOLD_LABELS = {
        'cp6_cr_watch':      'Compression ratio WATCH threshold',
        'cp6_cr_warning':    'Compression ratio WARNING threshold',
        'trend_window_rows': 'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'cp6_cr_watch':      5.5,
        'cp6_cr_warning':    8.0,
        'trend_window_rows': 20,
    }
    DEFAULT_EXPRESSIONS = {
        'WARNING': {'join': 'and', 'conditions': [
            {'column': 'P_disch', 'column2': 'P_suction', 'function': 'pressure_ratio', 'operator': '>', 'value': 8.0},
        ]},
        'WATCH': {'join': 'and', 'conditions': [
            {'column': 'P_disch', 'column2': 'P_suction', 'function': 'pressure_ratio', 'operator': '>', 'value': 5.5},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            p_suc   = _mean(df, _suc_col(ctx, label), win)
            p_disch = _mean(df, _disc_col(ctx, label), win)
            if p_suc is None or p_disch is None:
                continue
            cr = (p_disch + 14.696) / max(p_suc + 14.696, 0.1)  # avoid div/0
            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl    = f'{self.LABEL}{" — " + suffix if suffix else ""}'
            evidence = (f'  P_suction (avg last {win} rows): {p_suc:.1f} PSIG\n'
                        f'  P_disch   (avg last {win} rows): {p_disch:.1f} PSIG\n'
                        f'  Compression Ratio:               {cr:.2f}:1')

            if cr > self.t(thresholds, 'cp6_cr_warning'):
                sev  = 'WARNING'
                summ = f'CR = {cr:.2f}:1 — high compression ratio, elevated thermal and mechanical stress.'
                rec  = ('POSSIBLE CAUSES:\n'
                        '1. LOW SUCTION PRESSURE: Refrigerant undercharge (RF-2), suction line restriction (SL-1), '
                        'or evaporator starvation (EV-1).\n'
                        '2. HIGH DISCHARGE PRESSURE: Condenser fouling (CD-1), low water flow (CD-2), '
                        'overcharge (RF-3), or high water inlet temperature.\n'
                        '3. NON-CONDENSABLES: Air/nitrogen raises head pressure (RF-4).\n'
                        '4. Monitor discharge temp (CP-2) — high CR elevates T_3a and accelerates wear.')
            elif cr > self.t(thresholds, 'cp6_cr_watch'):
                sev  = 'WATCH'
                summ = f'CR = {cr:.2f}:1 — elevated. Normal range for R290 is 3–5.5:1.'
                rec  = ('Monitor operating conditions.\n'
                        'Check condenser approach temp and subcooling for early warning signs.')
            else:
                findings.append(self._ok(suffix))
                if ctx.system_type == 'shared':
                    break
                continue

            findings.append(Finding(
                scenario_id=self.SCENARIO_ID, label=lbl, component=self.COMPONENT,
                severity=sev, summary=summ, evidence=evidence, recommendation=rec,
            ))
            if ctx.system_type == 'shared':
                break
        return findings


class CP7_MassFlowCrossCheck(DiagnosticScenario):
    """
    CP-7 · Mass Flow Cross-Check (water-side vs displacement)
    ==========================================================
    APPROACH:
      The app computes mass flow two independent ways:
        m_dot       — condenser water-side energy balance (measurement-driven)
        m_dot_disp  — compressor displacement × ρ_2b × rpm × η_vol (geometry-driven)
      When the system AND its inputs are healthy, the two agree within ~10-15%.
      A persistent disagreement is itself a diagnostic — its DIRECTION points
      at the root cause:
        m_dot_disp >> m_dot  → compressor moving less than its geometry should
                               (worn valves/rings, vol-eff degradation) or the
                               entered GPM/η_vol inputs are off in that direction
        m_dot >> m_dot_disp  → water side claims more flow than the compressor
                               can pump (GPM input too high, water ΔT sensor
                               error, or η_vol input pessimistic)
      Inactive (silent) when m_dot_disp is unavailable — requires compressor
      displacement + speed properties and rated inputs for η_vol.

    COLUMNS (shared):   m_dot, m_dot_disp
    COLUMNS (cassette): m_dot-{ab}, m_dot_disp-{ab}

    UPDATE LOG:
      - 2026-06-10: Initial implementation (Session 11 calc engine additions).
    """
    SCENARIO_ID = 'CP-7'
    COMPONENT   = 'Compressor'
    LABEL       = 'Mass Flow Cross-Check'
    DESCRIPTION = (
        "Compares the two independent mass-flow estimates the app computes: the condenser "
        "water-side energy balance (m_dot) and the compressor displacement method (m_dot_disp). "
        "Agreement validates both the sensors and the compressor; persistent disagreement "
        "points at compressor wear, wrong rated inputs, or water-side sensor error — the "
        "direction of the disagreement narrows the cause."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • m_dot — water-side mass flow (lb/hr)\n"
        "  • m_dot_disp — displacement-based mass flow (lb/hr)\n"
        "  (cassette: m_dot-{{ab}}, m_dot_disp-{{ab}} per unit)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows):\n"
        "  Deviation % = (m_dot_disp - m_dot) / m_dot × 100\n"
        "\n"
        "  WARNING  if  |Deviation| > {cp7_disagree_critical_pct} %\n"
        "  WATCH    if  |Deviation| > {cp7_disagree_warning_pct} %\n"
        "  OK       otherwise\n"
        "  (silent when m_dot_disp unavailable — set compressor displacement/speed "
        "properties and rated inputs to activate)"
    )
    THRESHOLD_LABELS = {
        'cp7_disagree_warning_pct':  'Deviation WATCH threshold (%)',
        'cp7_disagree_critical_pct': 'Deviation WARNING threshold (%)',
        'trend_window_rows':         'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'cp7_disagree_warning_pct':  15.0,
        'cp7_disagree_critical_pct': 30.0,
        'trend_window_rows':         20,
    }
    # Needs a ratio of two derived columns — Python-only.
    DEFAULT_EXPRESSIONS = {}

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            mdot_w = _mean(df, _mdot_col(ctx, label), win)
            disp_col = (f'm_dot_disp-{_ab(label)}'
                        if ctx.system_type == 'cassette' else 'm_dot_disp')
            mdot_d = _mean(df, disp_col, win)
            if mdot_w is None or mdot_d is None or mdot_w <= 0:
                # Cross-check inactive — no compressor specs or no water balance
                if ctx.system_type == 'shared':
                    break
                continue
            dev_pct = (mdot_d - mdot_w) / mdot_w * 100.0
            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl    = f'{self.LABEL}{" — " + suffix if suffix else ""}'
            lines  = [
                'Why: two independent flow estimates should agree when sensors, inputs and compressor are healthy.',
                f'  m_dot (water-side balance):     {mdot_w:.1f} lb/hr',
                f'  m_dot_disp (displacement):      {mdot_d:.1f} lb/hr',
                f'  Deviation:                      {dev_pct:+.1f} %',
            ]
            warn = self.t(thresholds, 'cp7_disagree_warning_pct')
            crit = self.t(thresholds, 'cp7_disagree_critical_pct')
            if abs(dev_pct) > crit:
                sev = 'WARNING'
            elif abs(dev_pct) > warn:
                sev = 'WATCH'
            else:
                findings.append(self._ok(suffix))
                if ctx.system_type == 'shared':
                    break
                continue
            if dev_pct > 0:
                summ = (f'Displacement method predicts {dev_pct:.0f}% more flow than the water '
                        f'balance measures — compressor may be pumping below its geometry.')
                rec  = ('POSSIBLE CAUSES (m_dot_disp >> m_dot):\n'
                        '1. COMPRESSOR WEAR: Leaking discharge/suction valves or worn rings reduce real '
                        'pumping below the displacement prediction. Check compression ratio trend and eta_is.\n'
                        '2. VOLUMETRIC EFFICIENCY INPUT TOO HIGH: Rated inputs produce an optimistic η_vol — '
                        're-check rated mass flow / speed / displacement entries.\n'
                        '3. WATER GPM INPUT TOO LOW: If the entered GPM is below the true flow, the water '
                        'balance under-reports. Verify against the balancing valve / flow meter.\n'
                        '4. WATER ΔT UNDER-READ: Water in/out sensors too close together or poorly coupled.\n'
                        '5. SUCTION DENSITY ERROR: T_2b or P_suction sensor error skews ρ_2b.')
            else:
                summ = (f'Displacement method predicts {abs(dev_pct):.0f}% less flow than the water '
                        f'balance measures — check water-side inputs or compressor specs.')
                rec  = ('POSSIBLE CAUSES (m_dot >> m_dot_disp):\n'
                        '1. WATER GPM INPUT TOO HIGH: Entered GPM above true flow inflates the water '
                        'balance. Verify against the balancing valve / flow meter.\n'
                        '2. WATER ΔT OVER-READ: Water outlet sensor picking up extra heat (e.g. mounted '
                        'too close to compressor discharge) inflates Q_water.\n'
                        '3. VOLUMETRIC EFFICIENCY INPUT TOO LOW: Pessimistic η_vol under-predicts pumping — '
                        're-check rated inputs.\n'
                        '4. SPEED/DISPLACEMENT WRONG: Verify compressor displacement (cm³) and actual RPM.\n'
                        '5. CONDENSER FOULING ON WATER SIDE is NOT a cause — it changes temperatures, '
                        'not the energy balance itself.')
            findings.append(Finding(
                scenario_id=self.SCENARIO_ID, label=lbl, component=self.COMPONENT,
                severity=sev, summary=summ, evidence='\n'.join(lines), recommendation=rec,
            ))
            if ctx.system_type == 'shared':
                break
        return findings


# ─── CD: CONDENSER ────────────────────────────────────────────────────────────

class CD1_CondenserBlockage(DiagnosticScenario):
    """
    CD-1 · Condenser Blockage / Fouling (Point)
    =============================================
    APPROACH:
      Approach temperature = T_sat.cond − T_4a (condenser outlet liquid temp).
      High approach means the condenser is struggling to transfer heat:
      fouling, scaling on water side, or reduced water flow.
      Also used by RF-4 (non-condensables can cause same symptom).

    COLUMNS (shared):   T_sat.cond, T_4a
    COLUMNS (cassette): T_sat.cond-{ab}, T_4a-{ab}

    THRESHOLDS:
      cd1_approach_warning_f:  8.0
      cd1_approach_critical_f: 15.0
      trend_window_rows:        10

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'CD-1'
    COMPONENT   = 'Condenser'
    LABEL       = 'Condenser Blockage / Fouling'
    DESCRIPTION = (
        "Condenser approach temperature is T_sat.cond minus T_waterout — how closely the refrigerant "
        "saturation temperature approaches the leaving water temperature. "
        "A clean, properly sized condenser should achieve an approach of 3–8°F. "
        "High approach temperature means the condenser is struggling to reject heat: the refrigerant "
        "stays hotter relative to the water, indicating fouling, scale buildup, reduced water flow, "
        "or air in the water circuit."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • T_sat.cond — saturation temperature at condensing pressure (°F)\n"
        "  • T_waterout — condenser leaving water temperature (°F)\n"
        "  (cassette: T_sat.cond-{{ab}}, T_waterout-{{ab}} per unit)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows):\n"
        "  Approach temp = T_sat.cond - T_waterout\n"
        "\n"
        "  CRITICAL  if  Approach > {cd1_approach_critical_f}°F\n"
        "  WARNING   if  Approach > {cd1_approach_warning_f}°F\n"
        "  OK        otherwise  (normal approach: 3–8°F)"
    )
    THRESHOLD_LABELS = {
        'cd1_approach_warning_f':  'Approach temp WARNING threshold (°F)',
        'cd1_approach_critical_f': 'Approach temp CRITICAL threshold (°F)',
        'trend_window_rows':       'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'cd1_approach_warning_f':  8.0,
        'cd1_approach_critical_f': 15.0,
        'trend_window_rows':        20,
    }
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'and', 'conditions': [
            {'column': 'T_sat.cond', 'column2': 'T_waterout', 'function': 'diff_mean', 'operator': '>', 'value': 15.0},
        ]},
        'WARNING': {'join': 'and', 'conditions': [
            {'column': 'T_sat.cond', 'column2': 'T_waterout', 'function': 'diff_mean', 'operator': '>', 'value': 8.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            tsat   = _mean(df, _tsat_cond_col(ctx, label), win)
            t_wout = _mean(df, _t_waterout_col(ctx, label), win)
            if tsat is None or t_wout is None:
                continue
            approach = tsat - t_wout
            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl = f'{self.LABEL}{" — " + suffix if suffix else ""}'
            lines = [
                'Why: T_sat.cond - T_waterout = condenser approach temp. High approach means refrigerant cannot cool to near water temperature.',
                f'  T_sat.cond: {tsat:.1f} °F',
                f'  T_waterout: {t_wout:.1f} °F',
                f'  Approach temp: {approach:.1f} °F',
            ]

            if approach > self.t(thresholds, 'cd1_approach_critical_f'):
                sev = 'CRITICAL'
                summ = f'Approach temp = {approach:.1f}°F — severe condenser heat transfer problem.'
                rec = ('POSSIBLE CAUSES (check in order):\n'
                       '1. WATER FLOW TOO LOW: Verify GPM against design spec (CD-2). Check pump '
                       'operation, valve positions, strainer/filter for blockage.\n'
                       '2. WATER INLET TEMP TOO HIGH: If T_waterin exceeds design, approach will '
                       'always be large. Check cooling tower or chilled water supply.\n'
                       '3. CONDENSER FOULING: Inspect heat exchange surfaces for scale, biofilm, '
                       'or debris. Clean with descaling chemical if scale is present.\n'
                       '4. AIR IN WATER CIRCUIT: Air pockets reduce effective heat transfer area. '
                       'Bleed air vents on the water loop.\n'
                       '5. GLYCOL CONCENTRATION: If glycol has been added or concentration changed, '
                       'higher viscosity reduces heat transfer coefficient.\n'
                       '6. NON-CONDENSABLES IN REFRIGERANT: If water side is clean, suspect air '
                       'or nitrogen in refrigerant circuit (RF-4).\n'
                       '7. WATER VALVE PARTIALLY CLOSED: Check all isolation and control valves '
                       'in the water circuit are fully open.\n'
                       '8. PLATE HX / TUBE ISSUE: Verify all plates or tubes are intact — a '
                       'maintenance error may have reduced the effective heat transfer area.')
            elif approach > self.t(thresholds, 'cd1_approach_warning_f'):
                sev = 'WARNING'
                summ = f'Approach temp = {approach:.1f}°F — elevated, condenser performance degraded.'
                rec = ('Check condenser water flow rate and inlet temperature (CD-2).\n'
                       'Inspect heat transfer surfaces for early fouling. Consider preventive cleaning.\n'
                       'Verify all water-side valves are fully open and strainer is clean.\n'
                       'If glycol is used, check concentration has not changed since commissioning.')
            else:
                findings.append(self._ok(suffix))
                if ctx.system_type == 'shared': break
                continue

            findings.append(Finding(
                scenario_id=self.SCENARIO_ID, label=lbl, component=self.COMPONENT,
                severity=sev, summary=summ, evidence='\n'.join(lines), recommendation=rec,
            ))
            if ctx.system_type == 'shared':
                break
        return findings


class CD2_WaterFlowIssue(DiagnosticScenario):
    """
    CD-2 · Water Flow Issue (Point)
    =================================
    APPROACH:
      ΔT_water = T_waterout − T_waterin.
      High ΔT = low water flow (water gaining too much heat).
      Very low ΔT = no heat rejection or sensor error.

    COLUMNS (shared):   T_waterin, T_waterout
    COLUMNS (cassette): T_waterin-{ab}, T_waterout-{ab}

    THRESHOLDS:
      cd2_water_dt_high_warning_f:  12.0
      cd2_water_dt_high_critical_f: 20.0
      cd2_water_dt_low_f:            1.0   (suspiciously small)
      trend_window_rows:             10

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'CD-2'
    COMPONENT   = 'Condenser'
    LABEL       = 'Water Side Flow Issue'
    DESCRIPTION = (
        "Water-side ΔT (T_waterout − T_waterin) reflects how much heat the condenser water is absorbing. "
        "If ΔT is too large, water flow rate is too low — the water is being heated too much per pass, "
        "reducing condenser effectiveness. If ΔT is too small, flow may be excessive (wasted pump energy) "
        "or the condenser is not rejecting heat properly. "
        "For lab units with known GPM, this check validates actual heat exchange against expected performance."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • T_waterin — condenser entering water temperature (°F)\n"
        "  • T_waterout — condenser leaving water temperature (°F)\n"
        "  (cassette: T_waterin-{{ab}}, T_waterout-{{ab}} per unit)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows):\n"
        "  ΔT_water = T_waterout - T_waterin\n"
        "\n"
        "  CRITICAL  if  ΔT > {cd2_water_dt_high_critical_f}°F  (flow severely restricted)\n"
        "  WARNING   if  ΔT > {cd2_water_dt_high_warning_f}°F   (flow lower than expected)\n"
        "  WATCH     if  ΔT < {cd2_water_dt_low_f}°F            (suspiciously small — check sensors)\n"
        "  OK        otherwise"
    )
    THRESHOLD_LABELS = {
        'cd2_water_dt_high_warning_f':  'Water ΔT WARNING threshold — low flow (°F)',
        'cd2_water_dt_high_critical_f': 'Water ΔT CRITICAL threshold — low flow (°F)',
        'cd2_water_dt_low_f':           'Water ΔT WATCH threshold — suspiciously small (°F)',
        'trend_window_rows':            'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'cd2_water_dt_high_warning_f':  12.0,
        'cd2_water_dt_high_critical_f': 20.0,
        'cd2_water_dt_low_f':            1.0,
        'trend_window_rows':             20,
    }
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'and', 'conditions': [
            {'column': 'T_waterout', 'column2': 'T_waterin', 'function': 'diff_mean', 'operator': '>', 'value': 20.0},
        ]},
        'WARNING': {'join': 'and', 'conditions': [
            {'column': 'T_waterout', 'column2': 'T_waterin', 'function': 'diff_mean', 'operator': '>', 'value': 12.0},
        ]},
        'WATCH': {'join': 'and', 'conditions': [
            {'column': 'T_waterout', 'column2': 'T_waterin', 'function': 'diff_mean', 'operator': '<', 'value': 1.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            tw_in  = _mean(df, _waterin_col(ctx, label), win)
            tw_out = _mean(df, _waterout_col(ctx, label), win)
            if tw_in is None or tw_out is None:
                continue
            dt = tw_out - tw_in
            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl = f'{self.LABEL}{" — " + suffix if suffix else ""}'
            evidence = (f'  T_waterin: {tw_in:.1f} °F | T_waterout: {tw_out:.1f} °F\n'
                        f'  ΔT water: {dt:.1f} °F')

            if dt > self.t(thresholds, 'cd2_water_dt_high_critical_f'):
                sev = 'CRITICAL'
                summ = f'ΔT_water = {dt:.1f}°F — water flow severely restricted.'
                rec = ('POSSIBLE CAUSES (check in order):\n'
                       '1. WATER PUMP FAILURE: Check pump is running, impeller is not eroded, '
                       'and pump speed/setting matches design GPM.\n'
                       '2. VALVE POSITIONS: Verify ALL isolation and control valves in the water '
                       'circuit are fully open. A partially closed valve is the most common cause.\n'
                       '3. STRAINER / FILTER CLOGGED: Check water-side strainer or filter for debris. '
                       'Clean or replace if restricted.\n'
                       '4. AIR LOCK: Air trapped in the water circuit reduces effective flow. '
                       'Bleed air vents at high points in the piping.\n'
                       '5. PIPE SCALE / BUILDUP: Internal pipe scaling reduces effective diameter. '
                       'Check pressure differential across condenser — high ΔP confirms restriction.\n'
                       '6. GLYCOL VISCOSITY: If glycol concentration was increased, higher viscosity '
                       'reduces flow rate at the same pump setting. Verify glycol % vs design.\n'
                       '7. FLOW METER ERROR: If a flow meter is installed, verify its reading matches '
                       'actual flow. A faulty meter can lead to incorrect test conditions.\n'
                       '8. WATER LEAK: Check for leaks in the water circuit that reduce total flow.\n'
                       'Verify GPM setting in rated inputs matches actual measured flow.')
            elif dt > self.t(thresholds, 'cd2_water_dt_high_warning_f'):
                sev = 'WARNING'
                summ = f'ΔT_water = {dt:.1f}°F — water flow lower than expected.'
                rec = ('POSSIBLE CAUSES:\n'
                       '1. LOW WATER GPM: Verify water flow rate — check pump operation, valve positions, '
                       'and strainer/filter for partial blockage.\n'
                       '2. CONTROL VALVE HUNTING: Check if a modulating water valve is oscillating '
                       'or not opening fully.\n'
                       '3. AIR IN WATER CIRCUIT: Small air pockets can reduce flow — bleed air vents.\n'
                       '4. INCREASED GLYCOL %: Higher glycol concentration reduces heat transfer.\n'
                       '5. PIPE SCALE: Early scaling reduces flow — check ΔP across condenser.\n'
                       '6. FLOW METER INACCURACY: If GPM reading looks normal but ΔT is high, '
                       'suspect the flow meter is reading high. Verify with bucket test or ultrasonic.')
            elif dt < self.t(thresholds, 'cd2_water_dt_low_f'):
                sev = 'WATCH'
                summ = f'ΔT_water = {dt:.1f}°F — very small. Check sensor placement or heat rejection.'
                rec = ('POSSIBLE CAUSES:\n'
                       '1. SENSOR SWAP: T_waterin and T_waterout sensors may be installed backwards.\n'
                       '2. SENSORS ON SAME PIPE: Both sensors may be on the same pipe (inlet or outlet) '
                       'by mistake — verify physical placement.\n'
                       '3. EXCESSIVE WATER FLOW: If GPM is much higher than design, ΔT will be small. '
                       'This wastes pump energy but is not harmful to the unit.\n'
                       '4. LOW HEAT LOAD: If the unit is running at very low capacity, ΔT will be '
                       'naturally small — check qc to confirm.')
            else:
                findings.append(self._ok(suffix))
                if ctx.system_type == 'shared': break
                continue

            findings.append(Finding(
                scenario_id=self.SCENARIO_ID, label=lbl, component=self.COMPONENT,
                severity=sev, summary=summ, evidence=evidence, recommendation=rec,
            ))
            if ctx.system_type == 'shared':
                break
        return findings


class CD3_WaterFlowInstability(DiagnosticScenario):
    """
    CD-3 · Water Flow Instability — Averages Unreliable
    ====================================================
    APPROACH:
      When condenser water GPM wanders during a test, instantaneous subcooling
      swings negative-to-positive and capacity goes off the charts — yet the
      MEANS of those same columns look perfectly normal, because symmetric
      swings average out.  This scenario detects the masking:
        1. Subcooling (S.C) flipping sign repeatedly within the window
           (physically impossible for a stable system)
        2. Capacity (qc) coefficient of variation far above steady-state noise
        3. Measured water GPM (gpm column, when the water_flow_gpm sensor is
           mapped) varying well beyond steady-flow tolerance
      Two or more signals → WARNING ("don't trust averaged m_dot/qc/S.C from
      this window").  One signal → WATCH.
      NOTE: the engine now uses the measured per-row GPM when mapped, which
      removes most of the skew at the source — this scenario remains the
      guard for unmapped-GPM tests and for genuinely unstable flow.

    COLUMNS (shared):   S.C, qc, gpm
    COLUMNS (cassette): S.C-{ab}, qc-{ab}, gpm-{ab}

    UPDATE LOG:
      - 2026-06-10: Initial implementation (user-reported averaging-masking problem).
    """
    SCENARIO_ID = 'CD-3'
    COMPONENT   = 'Condenser'
    LABEL       = 'Water Flow Instability — Averages Unreliable'
    DESCRIPTION = (
        "Varying condenser water flow makes instantaneous subcooling and capacity swing wildly "
        "while their averages still look normal — symmetric swings cancel out in the mean. "
        "Mass flow and capacity computed from such windows are unreliable. This check looks at "
        "the VARIATION of subcooling, capacity and measured GPM, not their averages, and warns "
        "when the averages are masking instability."
    )
    LOGIC = (
        "INPUTS (last {trend_window_rows} rows):\n"
        "  • S.C — condenser subcooling series (°F)\n"
        "  • qc — cooling capacity series (BTU/hr)\n"
        "  • gpm — measured water flow series (when water_flow_gpm sensor mapped)\n"
        "\n"
        "SIGNALS:\n"
        "  1. S.C crosses zero ≥ {cd3_sc_sign_flips} times in the window\n"
        "  2. qc coefficient of variation > {cd3_qc_cv_pct} %\n"
        "  3. measured GPM coefficient of variation > {cd3_gpm_cv_pct} %\n"
        "\n"
        "  WARNING  if 2+ signals fire\n"
        "  WATCH    if 1 signal fires\n"
        "  OK       otherwise"
    )
    THRESHOLD_LABELS = {
        'cd3_sc_sign_flips': 'Subcooling zero-crossings to flag (count)',
        'cd3_qc_cv_pct':     'Capacity variation threshold (CV %)',
        'cd3_gpm_cv_pct':    'Measured GPM variation threshold (CV %)',
        'trend_window_rows': 'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'cd3_sc_sign_flips': 3,
        'cd3_qc_cv_pct':     25.0,
        'cd3_gpm_cv_pct':    10.0,
        'trend_window_rows': 60,
    }
    # Needs sign-flip counting on a series — Python-only.
    DEFAULT_EXPRESSIONS = {}

    def run(self, df, ctx, thresholds):
        findings = []
        win = int(self.t(thresholds, 'trend_window_rows') or 60)
        for label in ctx.module_labels:
            w = _window(df, win)
            sc_s  = _col(w, _sc_cond_col(ctx, label))
            qc_s  = _col(w, _qc_col(ctx, label))
            gpm_s = _col(w, f'gpm-{_ab(label)}'
                         if ctx.system_type == 'cassette' else 'gpm')

            signals = []

            # 1. Subcooling sign flips — the smoking gun
            if sc_s is not None:
                sv = sc_s.dropna()
                if len(sv) >= 5:
                    signs = np.sign(sv.values)
                    signs = signs[signs != 0]
                    flips = int(np.sum(signs[1:] * signs[:-1] < 0))
                    if flips >= int(self.t(thresholds, 'cd3_sc_sign_flips')):
                        signals.append(
                            f'Subcooling flips sign {flips}× — mean {sv.mean():.1f} °F '
                            f'looks normal but range is {sv.min():.1f} … {sv.max():.1f} °F')

            # 2. Capacity coefficient of variation
            if qc_s is not None:
                qv = qc_s.dropna()
                if len(qv) >= 5 and abs(qv.mean()) > 1e-6:
                    cv = float(qv.std() / abs(qv.mean()) * 100.0)
                    if cv > self.t(thresholds, 'cd3_qc_cv_pct'):
                        signals.append(
                            f'Capacity CV {cv:.0f}% — mean {qv.mean():,.0f} BTU/hr '
                            f'but range {qv.min():,.0f} … {qv.max():,.0f} BTU/hr')

            # 3. Measured GPM variation (only when the sensor is mapped)
            if gpm_s is not None:
                gv = gpm_s.dropna()
                if len(gv) >= 5 and gv.mean() > 0:
                    cv = float(gv.std() / gv.mean() * 100.0)
                    if cv > self.t(thresholds, 'cd3_gpm_cv_pct'):
                        signals.append(
                            f'Measured water GPM CV {cv:.0f}% — mean {gv.mean():.2f} GPM, '
                            f'range {gv.min():.2f} … {gv.max():.2f} GPM')

            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl    = f'{self.LABEL}{" — " + suffix if suffix else ""}'

            if len(signals) >= 2:
                sev  = 'WARNING'
                summ = ('Water flow is unstable — averaged m_dot/qc/S.C from this window '
                        'are unreliable even though they look normal.')
            elif len(signals) == 1:
                sev  = 'WATCH'
                summ = ('Possible water flow instability — one variability signal fired; '
                        'inspect the time series before trusting averages.')
            else:
                findings.append(self._ok(suffix))
                if ctx.system_type == 'shared':
                    break
                continue

            lines = ['Why: symmetric swings cancel in the mean — variation, not the average, '
                     'reveals the problem.'] + [f'  • {s}' for s in signals]
            rec = ('POSSIBLE CAUSES / ACTIONS:\n'
                   '1. WATER FLOW VARYING: Balancing valve hunting, building water pressure '
                   'swings, or other loads on the loop. Stabilize flow or add a flow regulator.\n'
                   '2. MAP THE GPM SENSOR: If the data contains a measured GPM column, map it '
                   'to the Condenser water_flow_gpm port — the engine then uses per-row GPM and '
                   'the capacity numbers self-correct.\n'
                   '3. SEGMENT THE DATA: Use the time-range filter to analyze only stable spans; '
                   'discard windows where subcooling flips sign.\n'
                   '4. DO NOT REPORT averaged capacity/mass-flow from this window — recompute '
                   'after stabilizing or mapping measured GPM.')
            findings.append(Finding(
                scenario_id=self.SCENARIO_ID, label=lbl, component=self.COMPONENT,
                severity=sev, summary=summ, evidence='\n'.join(lines), recommendation=rec,
            ))
            if ctx.system_type == 'shared':
                break
        return findings


# ─── EV: EVAPORATOR / COILS ───────────────────────────────────────────────────

class EV1_CoilRestrictionOrIcing(DiagnosticScenario):
    """
    EV-1 · Coil Restriction / Possible Icing (Point — per module)
    ==============================================================
    APPROACH:
      Coil outlet SH very HIGH → restricted airflow (iced solid or blocked).
        Refrigerant evaporates quickly with little heat pickup.
      Coil outlet SH very LOW → possible frost starting to form or liquid flooding.
        Less superheat before coil outlet means limited heat transfer.

    COLUMNS: S.H_{ab} coil  (e.g. 'S.H_lh coil')  — same name for shared & cassette

    THRESHOLDS:
      ev1_coil_sh_high_warning_f:  25.0
      ev1_coil_sh_high_critical_f: 40.0
      ev1_coil_sh_low_warning_f:    3.0
      ev1_coil_sh_low_critical_f:   0.0
      trend_window_rows:            10

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'EV-1'
    COMPONENT   = 'Evaporator Coil'
    LABEL       = 'Coil Starved / TXV Over-open'
    DESCRIPTION = (
        "Coil superheat (SH at the coil outlet) shows how much the refrigerant is superheated "
        "above its saturation temperature by the time it leaves the evaporator coil. "
        "High coil SH means the refrigerant evaporated too quickly or too little refrigerant reached "
        "the coil — this is starvation, not icing. Low coil SH means refrigerant is still partly liquid "
        "at the coil exit, risking liquid carry-over to the compressor. "
        "Note: icing causes SH to FALL over time (detected by EV-3), not to be persistently high."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • S.H_{{ab}} coil — coil outlet superheat per module (°F)\n"
        "    e.g. 'S.H_lh coil', 'S.H_rh coil'\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows, per module):\n"
        "  CRITICAL  if  coil SH > {ev1_coil_sh_high_critical_f}°F  (coil severely starved)\n"
        "  WARNING   if  coil SH > {ev1_coil_sh_high_warning_f}°F   (coil starved — check TXV/charge)\n"
        "  CRITICAL  if  coil SH <= {ev1_coil_sh_low_critical_f}°F  (liquid at coil outlet)\n"
        "  WARNING   if  coil SH <  {ev1_coil_sh_low_warning_f}°F   (very low — TXV overfeeding)\n"
        "  OK        otherwise"
    )
    THRESHOLD_LABELS = {
        'ev1_coil_sh_high_warning_f':  'Coil SH high — WARNING threshold (°F)',
        'ev1_coil_sh_high_critical_f': 'Coil SH high — CRITICAL threshold (°F)',
        'ev1_coil_sh_low_warning_f':   'Coil SH low — WARNING threshold (°F)',
        'ev1_coil_sh_low_critical_f':  'Coil SH low — CRITICAL threshold (°F)',
        'trend_window_rows':           'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'ev1_coil_sh_high_warning_f':  25.0,
        'ev1_coil_sh_high_critical_f': 40.0,
        'ev1_coil_sh_low_warning_f':    3.0,
        'ev1_coil_sh_low_critical_f':   0.0,
        'trend_window_rows':            20,
    }
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'or', 'conditions': [
            {'column': 'S.H_lh coil', 'function': 'mean', 'operator': '>',  'value': 40.0},
            {'column': 'S.H_lh coil', 'function': 'mean', 'operator': '<=', 'value': 0.0},
        ]},
        'WARNING': {'join': 'or', 'conditions': [
            {'column': 'S.H_lh coil', 'function': 'mean', 'operator': '>',  'value': 25.0},
            {'column': 'S.H_lh coil', 'function': 'mean', 'operator': '<',  'value': 3.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            ab  = _ab(label)
            col = f'S.H_{ab} coil'
            sh  = _mean(df, col, win)
            if sh is None:
                continue
            lbl = f'{self.LABEL} — {label}'
            evidence = f'  S.H_{ab} coil (avg last {win} rows): {sh:.1f} °F'

            if sh > self.t(thresholds, 'ev1_coil_sh_high_critical_f'):
                sev = 'CRITICAL'
                summ = f'S.H_{ab} coil = {sh:.1f}°F — coil severely starved — insufficient refrigerant flow to this module.'
                rec = ('POSSIBLE CAUSES:\n'
                       '1. TXV RESTRICTION: TXV may be blocked, iced up, or undersized (TX-1).\n'
                       '2. FLASH GAS IN LIQUID LINE: Check S.C-txv — if low, liquid is flashing '
                       'before the TXV, reducing capacity (DI-2).\n'
                       '3. REFRIGERANT UNDERCHARGE: Insufficient charge starves the evaporator (RF-2).\n'
                       '4. DISTRIBUTOR BLOCKAGE: Check distributor for partial blockage (DI-1, DI-3).\n'
                       '5. AIR-SIDE FOULING: If air-cooled, check coil face for dirt, dust, or ice '
                       'blocking airflow. Clean coil if needed.\n'
                       '6. LOW AIRFLOW: Check blower belt tension, motor speed, and ductwork. '
                       'Low air = reduced evaporator load = high SH.\n'
                       'Note: high coil SH indicates starvation, NOT icing — icing causes SH to FALL.')
            elif sh > self.t(thresholds, 'ev1_coil_sh_high_warning_f'):
                sev = 'WARNING'
                summ = f'S.H_{ab} coil = {sh:.1f}°F — elevated — coil may be starved. Check TXV and charge.'
                rec = ('POSSIBLE CAUSES:\n'
                       '1. TXV SUPERHEAT SETTING: May need adjustment (TX-1).\n'
                       '2. REFRIGERANT CHARGE: Verify charge is adequate (RF-2).\n'
                       '3. FLASH GAS: If S.C-txv is also low, suspect liquid line flash gas (DI-2).\n'
                       '4. AIRFLOW: Check air-side coil cleanliness and blower operation.')
            elif sh <= self.t(thresholds, 'ev1_coil_sh_low_critical_f'):
                sev = 'CRITICAL'
                summ = f'S.H_{ab} coil = {sh:.1f}°F — liquid at coil outlet, compressor flood risk.'
                rec = ('POSSIBLE CAUSES:\n'
                       '1. TXV STUCK OPEN: TXV power element may have failed (TX-2). Adjust or replace.\n'
                       '2. REFRIGERANT OVERCHARGE: Excess charge floods the evaporator (RF-3).\n'
                       '3. TXV EXTERNAL EQUALIZER: Broken equalizer line reads atmospheric pressure, '
                       'causing TXV to open too far.\n'
                       '4. COMPRESSOR CYCLING: Multiple compressor start/stops cause suction pressure '
                       'swings that can drive TXV to over-open temporarily.')
            elif sh < self.t(thresholds, 'ev1_coil_sh_low_warning_f'):
                sev = 'WARNING'
                summ = f'S.H_{ab} coil = {sh:.1f}°F — very low SH at coil outlet.'
                rec = ('Monitor TXV operation. Check for TXV flooding (TX-2).\n'
                       'Verify refrigerant charge is not excessive (RF-3).\n'
                       'Check TXV external equalizer line is intact.')
            else:
                findings.append(self._ok(label))
                continue

            findings.append(Finding(
                scenario_id=self.SCENARIO_ID, label=lbl, component=f'Evaporator — {label}',
                severity=sev, summary=summ, evidence=evidence, recommendation=rec,
            ))
        return findings


class EV2_ModuleImbalance(DiagnosticScenario):
    """
    EV-2 · Module SH Imbalance — Shared Systems Only (Point)
    ==========================================================
    APPROACH:
      Compare coil SH across all modules. Large difference means refrigerant
      distribution is uneven. Possible causes: distributor blockage, one TXV
      stuck, or one coil iced.
      Only fires for shared systems with ≥ 2 modules.

    COLUMNS: S.H_{ab} coil for all module labels

    THRESHOLDS:
      ev2_sh_imbalance_warning_f:  8.0
      ev2_sh_imbalance_critical_f: 15.0
      trend_window_rows:            10

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'EV-2'
    COMPONENT   = 'Evaporator Coil'
    LABEL       = 'Module SH Imbalance'
    APPLIES_TO  = ['cassette', 'modular']  # needs at least 2 modules to compare
    DESCRIPTION = (
        "In a multi-module system, all evaporator coils share the same refrigerant supply. "
        "If one module has significantly higher superheat than others, it is receiving less "
        "refrigerant flow — a sign of TXV mismatch, distributor restriction on that branch, "
        "or a partially blocked coil. The coil with highest SH is the starved/restricted one. "
        "This scenario only runs on shared systems with 2 or more modules."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • S.H_{{ab}} coil — coil outlet superheat per module (°F)\n"
        "    e.g. 'S.H_lh coil', 'S.H_rh coil' for all modules\n"
        "  (shared systems with 2+ modules only)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows):\n"
        "  SH spread = max(coil SH across all modules) - min(coil SH across all modules)\n"
        "\n"
        "  CRITICAL  if  SH spread > {ev2_sh_imbalance_critical_f}°F\n"
        "  WARNING   if  SH spread > {ev2_sh_imbalance_warning_f}°F\n"
        "  OK        otherwise"
    )
    THRESHOLD_LABELS = {
        'ev2_sh_imbalance_warning_f':  'SH spread WARNING threshold (°F)',
        'ev2_sh_imbalance_critical_f': 'SH spread CRITICAL threshold (°F)',
        'trend_window_rows':           'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'ev2_sh_imbalance_warning_f':  8.0,
        'ev2_sh_imbalance_critical_f': 15.0,
        'trend_window_rows':            20,
    }
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'and', 'conditions': [
            {'column': 'S.H_lh coil', 'column2': 'S.H_rh coil', 'function': 'abs_diff_mean', 'operator': '>', 'value': 15.0},
        ]},
        'WARNING': {'join': 'and', 'conditions': [
            {'column': 'S.H_lh coil', 'column2': 'S.H_rh coil', 'function': 'abs_diff_mean', 'operator': '>', 'value': 8.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        if ctx.system_type != 'shared' or len(ctx.module_labels) < 2:
            return []
        win = self.t(thresholds, 'trend_window_rows')
        sh_vals = {}
        for label in ctx.module_labels:
            v = _mean(df, f'S.H_{_ab(label)} coil', win)
            if v is not None:
                sh_vals[label] = v
        if len(sh_vals) < 2:
            return []

        max_label = max(sh_vals, key=sh_vals.get)
        min_label = min(sh_vals, key=sh_vals.get)
        delta = sh_vals[max_label] - sh_vals[min_label]
        lines = [f'  {lbl}: SH={v:.1f}°F' for lbl, v in sh_vals.items()]
        lines.append(f'  Max spread: {delta:.1f}°F  ({max_label} vs {min_label})')
        evidence = '\n'.join(lines)

        if delta > self.t(thresholds, 'ev2_sh_imbalance_critical_f'):
            sev = 'CRITICAL'
            summ = f'SH spread = {delta:.1f}°F — severe module imbalance ({max_label} hot, {min_label} cold).'
            rec = (f'POSSIBLE CAUSES:\n'
                   f'1. DISTRIBUTOR BLOCKAGE: Check refrigerant distributor on {max_label} branch (DI-1).\n'
                   f'2. TXV ISSUE: Inspect TXV on {max_label} module — may be restricted (TX-1).\n'
                   f'3. COIL ICING: Check {min_label} coil for ice buildup (EV-3) — icing causes SH to drop.\n'
                   f'4. UNEQUAL AIRFLOW: If modules have different airflow (blocked filters, damper position, '
                   f'duct routing), heat load imbalance causes SH imbalance.\n'
                   f'5. UNEQUAL LOADING: One coil in direct sun, wind, or radiant heat source gets more '
                   f'heat load — check environmental conditions around each module.\n'
                   f'6. PIPING LENGTH: Different suction line lengths between modules cause different '
                   f'pressure drops — verify piping is per design specification.')
        elif delta > self.t(thresholds, 'ev2_sh_imbalance_warning_f'):
            sev = 'WARNING'
            summ = f'SH spread = {delta:.1f}°F — uneven refrigerant distribution.'
            rec = ('POSSIBLE CAUSES:\n'
                   '1. DISTRIBUTOR ORIFICE: Compare orifice sizes across branches (DI-1).\n'
                   '2. TXV SETTINGS: Compare TXV superheat settings across modules.\n'
                   '3. PARTIAL COIL BLOCKAGE: Inspect for blocked coil circuits.\n'
                   '4. AIRFLOW IMBALANCE: Check air filters and damper positions for each module.')
        else:
            return [self._ok()]

        return [Finding(
            scenario_id=self.SCENARIO_ID, label=self.LABEL, component=self.COMPONENT,
            severity=sev, summary=summ, evidence=evidence, recommendation=rec,
        )]


class EV3_CoilIcingTrend(DiagnosticScenario):
    """
    EV-3 · Coil Icing Trend (Time-Series — per module)
    =====================================================
    APPROACH:
      Icing is a progressive phenomenon. Frost accumulates on the coil surface,
      blocking airflow. Signature (all trending simultaneously):
        - T_sat.comp.in < 32°F (necessary condition for frost formation)
        - P_suction declining  (less evaporation as airflow blocked by frost)
        - qc declining         (capacity loss as frost thickens)
        - S.H_{ab} coil declining (less heat input to coil)
      Key distinction: icing causes SH to FALL (opposite of starvation).

    COLUMNS (shared):   T_sat.comp.in, P_suction, qc, S.H_{ab} coil (per module)
    COLUMNS (cassette): T_sat.comp.in-{ab}, P_suc-{ab}, qc-{ab}, S.H_{ab} coil

    THRESHOLDS:
      ev3_tsat_freeze_f:      32.0   # T_sat.comp.in must be below this for icing
      ev3_p_slope_threshold:   0.05  # PSIG/row — P_suc must be falling faster than this
      ev3_qc_slope_threshold:  5.0   # BTU/hr/row — qc must be falling faster than this
      ev3_sh_slope_threshold:  0.05  # °F/row — coil SH must be falling faster than this
      ev3_min_signals:         3     # all 3 slopes must be declining
      trend_window_rows:      20

    UPDATE LOG:
      - 2026-03-05: Initial implementation. Distinguishes from EV-1 (starvation) by
                    requiring FALLING SH (icing) vs high SH (starvation).
    """
    SCENARIO_ID = 'EV-3'
    COMPONENT   = 'Evaporator Coil'
    LABEL       = 'Coil Icing Trend'
    DESCRIPTION = (
        "Coil icing occurs when the evaporating surface temperature drops below 32°F and moisture "
        "from the air or product freezes onto the coil fins. As frost accumulates, it insulates the "
        "coil and blocks airflow — progressively reducing heat transfer, cooling capacity, and "
        "suction pressure, while coil superheat falls (opposite of starvation). "
        "This trend check requires T_sat.comp.in below 32°F plus all three signals declining together "
        "to distinguish genuine icing from other causes of low suction pressure."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • T_sat.comp.in — saturation temp at compressor inlet (°F) [necessary condition]\n"
        "  • P_suction / P_suc-{{ab}} — suction pressure (PSIG)\n"
        "  • qc — cooling capacity (BTU/hr)\n"
        "  • S.H_{{ab}} coil — coil outlet superheat per module (°F)\n"
        "\n"
        "PRECONDITION: T_sat.comp.in must be < {ev3_tsat_freeze_f}°F (below freezing)\n"
        "  If not met, fires OK immediately (icing not possible above 32°F)\n"
        "\n"
        "DECISION (linear regression over last {trend_window_rows} rows, per module):\n"
        "  Count signals declining:\n"
        "    P_suc slope    < -{ev3_p_slope_threshold} PSIG/row  → falling ✓\n"
        "    qc slope       < -{ev3_qc_slope_threshold} BTU/hr/row → falling ✓\n"
        "    Coil SH slope  < -{ev3_sh_slope_threshold} °F/row   → falling ✓\n"
        "\n"
        "  CRITICAL  if  all 3 signals declining (signals == 3)\n"
        "  WARNING   if  signals >= {ev3_min_signals}\n"
        "  WATCH     if  signals < {ev3_min_signals}  (T_sat below freezing but not all trends active)"
    )
    THRESHOLD_LABELS = {
        'ev3_tsat_freeze_f':     'Freezing precondition — T_sat.comp.in must be below (°F)',
        'ev3_p_slope_threshold': 'Min P_suc falling slope magnitude (PSIG/row)',
        'ev3_qc_slope_threshold':'Min qc falling slope magnitude (BTU/hr/row)',
        'ev3_sh_slope_threshold':'Min coil SH falling slope magnitude (°F/row)',
        'ev3_min_signals':       'Min declining signals required to flag',
        'trend_window_rows':     'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'ev3_tsat_freeze_f':      32.0,
        'ev3_p_slope_threshold':   0.05,
        'ev3_qc_slope_threshold':  5.0,
        'ev3_sh_slope_threshold':  0.05,
        'ev3_min_signals':         3,
        'trend_window_rows':      20,
    }
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'and', 'conditions': [
            {'column': 'T_sat.comp.in', 'function': 'mean',  'operator': '<', 'value': 32.0},
            {'column': 'P_suction',     'function': 'slope', 'operator': '<', 'value': -0.05},
            {'column': 'qc',            'function': 'slope', 'operator': '<', 'value': -5.0},
            {'column': 'S.H_lh coil',  'function': 'slope', 'operator': '<', 'value': -0.05},
        ]},
        'WATCH': {'join': 'and', 'conditions': [
            {'column': 'T_sat.comp.in', 'function': 'mean', 'operator': '<', 'value': 32.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        if len(df) < win:
            return findings

        # Check T_sat.comp.in < 32°F (necessary condition — no frost above freezing)
        first_label = ctx.module_labels[0]
        if ctx.system_type == 'cassette':
            tsat_col = f'T_sat.comp.in-{_ab(first_label)}'
        else:
            tsat_col = 'T_sat.comp.in'
        tsat_val = _mean(df, tsat_col, win)

        freeze_thresh = self.t(thresholds, 'ev3_tsat_freeze_f')
        if tsat_val is None or tsat_val >= freeze_thresh:
            msg = (f'T_sat.comp.in = {tsat_val:.1f}°F — above 32°F, icing not possible.'
                   if tsat_val is not None else 'T_sat.comp.in data not available.')
            return [Finding(
                scenario_id=self.SCENARIO_ID, label=self.LABEL,
                component=self.COMPONENT, severity='OK', uses_trend=True,
                summary=msg, evidence='', recommendation='',
            )]

        for label in ctx.module_labels:
            ab     = _ab(label)
            p_col  = _suc_col(ctx, label)
            qc_col = f'qc-{ab}' if ctx.system_type == 'cassette' else 'qc'
            sh_col = f'S.H_{ab} coil'
            dfw    = df.tail(win)

            signals = 0
            lines   = [
                'Why: All 3 signals declining simultaneously with T_sat < 32°F is the definitive icing signature.',
                f'  T_sat.comp.in: {tsat_val:.1f}°F (below 32°F — frost possible)',
            ]

            p_s  = _slope(dfw, p_col)
            qc_s = _slope(dfw, qc_col)
            sh_s = _slope(dfw, sh_col)

            if p_s  is not None:
                ok = p_s < -self.t(thresholds, 'ev3_p_slope_threshold')
                lines.append(f'  P_suction slope:    {p_s:+.3f} PSIG/row  {"✓ falling" if ok else "—"}')
                if ok: signals += 1
            if qc_s is not None:
                ok = qc_s < -self.t(thresholds, 'ev3_qc_slope_threshold')
                lines.append(f'  qc slope:           {qc_s:+.1f} BTU/hr/row  {"✓ falling" if ok else "—"}')
                if ok: signals += 1
            if sh_s is not None:
                ok = sh_s < -self.t(thresholds, 'ev3_sh_slope_threshold')
                lines.append(f'  S.H_{ab} coil slope: {sh_s:+.3f} °F/row  {"✓ falling" if ok else "—"}')
                if ok: signals += 1

            lbl     = f'{self.LABEL} — {label}'
            min_sig = int(self.t(thresholds, 'ev3_min_signals'))
            if signals >= min_sig:
                sev = 'CRITICAL' if signals == 3 else 'WARNING'
                findings.append(Finding(
                    scenario_id=self.SCENARIO_ID, label=lbl,
                    component=f'Evaporator — {label}', severity=sev, uses_trend=True,
                    summary=f'{signals}/3 icing indicators declining on {label} coil.',
                    evidence='\n'.join(lines),
                    recommendation=(
                        '1. Initiate defrost on this module immediately — further operation worsens ice accumulation.\n'
                        '2. Inspect coil surface visually after defrost for residual ice or blockage.\n'
                        '3. Check defrost cycle duration and effectiveness (HG-1).\n'
                        '4. Verify T_sat.comp.in is above 32°F after defrost before restarting refrigeration.\n'
                        '5. Long-term: review defrost schedule frequency vs actual frost accumulation rate.'
                    ),
                ))
            else:
                findings.append(Finding(
                    scenario_id=self.SCENARIO_ID, label=lbl,
                    component=f'Evaporator — {label}', severity='WATCH', uses_trend=True,
                    summary=f'T_sat below freezing but only {signals}/3 icing trends active. Monitor.',
                    evidence='\n'.join(lines),
                    recommendation='Monitor for developing icing. If all 3 signals align, defrost.',
                ))
        return findings


# ─── TX: TXV ─────────────────────────────────────────────────────────────────

class TX1_TXVStarvedOrBlocked(DiagnosticScenario):
    """
    TX-1 · TXV Starved / Blocked (Point — per module)
    ===================================================
    APPROACH:
      Very high coil outlet SH means insufficient refrigerant through the TXV.
      The TXV may be partially or fully blocked, undersized, or malfunctioning.
      Cross-reference with DI-1: if S.C-txv.{ab} is normal, the restriction is
      in the TXV itself (not the upstream distributor).

    COLUMNS: S.H_{ab} coil, S.C-txv.{ab}

    THRESHOLDS:
      tx1_sh_warning_f:  25.0
      tx1_sh_critical_f: 40.0
      trend_window_rows: 10

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'TX-1'
    COMPONENT   = 'TXV'
    LABEL       = 'TXV Starved / Blocked'
    DESCRIPTION = (
        "The thermostatic expansion valve (TXV) meters refrigerant into the evaporator by sensing "
        "suction line superheat at its bulb. If the TXV is blocked, undersized, or its sensing bulb "
        "is poorly clamped, it restricts flow too much — the coil becomes starved, superheat rises "
        "sharply, and cooling capacity falls. This is a point check on coil superheat; if the TXV "
        "appears starved but the distributor SC-txv is also low, suspect flash gas upstream (DI-2)."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • S.H_{{ab}} coil — coil outlet superheat per module (°F)\n"
        "  • S.C-txv.{{ab}} — subcooling at TXV inlet per module (°F) [cross-check]\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows, per module):\n"
        "  CRITICAL  if  coil SH > {tx1_sh_critical_f}°F  (TXV severely starving coil)\n"
        "  WARNING   if  coil SH > {tx1_sh_warning_f}°F   (TXV possibly starving coil)\n"
        "  OK        otherwise\n"
        "  Note: if S.C-txv is also low, suspect flash gas upstream (DI-2) not TXV"
    )
    THRESHOLD_LABELS = {
        'tx1_sh_warning_f':  'Coil SH WARNING threshold — TXV possibly starved (°F)',
        'tx1_sh_critical_f': 'Coil SH CRITICAL threshold — TXV severely starved (°F)',
        'trend_window_rows': 'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'tx1_sh_warning_f':  25.0,
        'tx1_sh_critical_f': 40.0,
        'trend_window_rows': 20,
    }
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'and', 'conditions': [
            {'column': 'S.H_lh coil', 'function': 'mean', 'operator': '>', 'value': 40.0},
        ]},
        'WARNING': {'join': 'and', 'conditions': [
            {'column': 'S.H_lh coil', 'function': 'mean', 'operator': '>', 'value': 25.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            ab  = _ab(label)
            sh  = _mean(df, f'S.H_{ab} coil', win)
            sc_txv = _mean(df, f'S.C-txv.{ab}', win)
            if sh is None:
                continue
            lbl = f'{self.LABEL} — {label}'
            lines = [f'  S.H_{ab} coil (avg last {win}): {sh:.1f} °F']
            if sc_txv is not None:
                lines.append(f'  S.C-txv.{ab} (TXV inlet SC): {sc_txv:.1f} °F')

            if sh > self.t(thresholds, 'tx1_sh_critical_f'):
                sev = 'CRITICAL'
                summ = f'S.H_{ab} coil = {sh:.1f}°F — TXV severely starving coil.'
                rec = ('POSSIBLE CAUSES:\n'
                       '1. TXV INLET SCREEN BLOCKAGE: Inspect for debris, solder particles, or '
                       'ice formation at the TXV inlet screen.\n'
                       '2. MOISTURE FREEZE-UP: Moisture in the system can form ice at the TXV orifice '
                       '(intermittent blockage). Replace filter dryer and evacuate.\n'
                       '3. TXV BULB ISSUE: Check bulb placement and thermal contact — a loose bulb '
                       'reads ambient and under-opens the valve.\n'
                       '4. EXTERNAL EQUALIZER BLOCKED: If the external equalizer line is crimped or '
                       'blocked, the TXV will not respond to evaporator pressure changes.\n'
                       '5. WRONG TXV ORIFICE SIZE: Verify orifice matches the design capacity for R290.\n'
                       '6. UPSTREAM RESTRICTION: If S.C-txv is also low, suspect DI-1/DI-2 (distributor '
                       'or filter dryer) rather than the TXV itself.')
            elif sh > self.t(thresholds, 'tx1_sh_warning_f'):
                sev = 'WARNING'
                summ = f'S.H_{ab} coil = {sh:.1f}°F — TXV possibly starving coil.'
                rec = ('POSSIBLE CAUSES:\n'
                       '1. TXV SUPERHEAT SETTING: Check and adjust superheat setpoint.\n'
                       '2. TXV INLET SCREEN: Inspect for early debris accumulation.\n'
                       '3. REFRIGERANT CHARGE: Verify charge is adequate (RF-2).\n'
                       '4. MOISTURE: If blockage is intermittent, suspect moisture freeze-up at orifice.')
            else:
                findings.append(self._ok(label))
                continue

            findings.append(Finding(
                scenario_id=self.SCENARIO_ID, label=lbl, component=f'TXV — {label}',
                severity=sev, summary=summ, evidence='\n'.join(lines), recommendation=rec,
            ))
        return findings


class TX2_TXVFlooding(DiagnosticScenario):
    """
    TX-2 · TXV Flooding / Stuck Open (Point — per module)
    =======================================================
    APPROACH:
      Very low or negative coil outlet SH means too much refrigerant through
      the TXV — liquid carry-over into the suction line.

    COLUMNS: S.H_{ab} coil

    THRESHOLDS:
      tx2_sh_warning_f:  3.0
      tx2_sh_critical_f: 0.0
      trend_window_rows: 10

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'TX-2'
    COMPONENT   = 'TXV'
    LABEL       = 'TXV Flooding / Stuck Open'
    DESCRIPTION = (
        "A flooding TXV passes too much refrigerant: the coil is overfed, liquid reaches the coil "
        "outlet, and wet vapour (low or zero superheat) approaches the compressor. "
        "Causes include an oversized TXV, a TXV set to too low a superheat target, a failed sensing "
        "bulb, or a stuck-open valve. Flooding is dangerous because it can lead directly to liquid "
        "slugging (CP-1). This check watches for persistently low coil SH per module."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • S.H_{{ab}} coil — coil outlet superheat per module (°F)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows, per module):\n"
        "  CRITICAL  if  coil SH <= {tx2_sh_critical_f}°F  (liquid leaving coil — flood-back risk)\n"
        "  WARNING   if  coil SH <  {tx2_sh_warning_f}°F   (very low SH — TXV possibly overfeeding)\n"
        "  OK        otherwise"
    )
    THRESHOLD_LABELS = {
        'tx2_sh_warning_f':  'Coil SH WARNING threshold — TXV overfeeding (°F)',
        'tx2_sh_critical_f': 'Coil SH CRITICAL threshold — liquid at coil outlet (°F)',
        'trend_window_rows': 'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'tx2_sh_warning_f':  3.0,
        'tx2_sh_critical_f': 0.0,
        'trend_window_rows': 20,
    }
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'and', 'conditions': [
            {'column': 'S.H_lh coil', 'function': 'mean', 'operator': '<=', 'value': 0.0},
        ]},
        'WARNING': {'join': 'and', 'conditions': [
            {'column': 'S.H_lh coil', 'function': 'mean', 'operator': '<', 'value': 3.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            ab = _ab(label)
            sh = _mean(df, f'S.H_{ab} coil', win)
            if sh is None:
                continue
            lbl = f'{self.LABEL} — {label}'
            evidence = f'  S.H_{ab} coil (avg last {win}): {sh:.1f} °F'

            if sh <= self.t(thresholds, 'tx2_sh_critical_f'):
                sev = 'CRITICAL'
                summ = f'S.H_{ab} coil = {sh:.1f}°F — liquid leaving coil, flood-back risk.'
                rec = ('POSSIBLE CAUSES:\n'
                       '1. TXV POWER ELEMENT FAILED: The thermostatic charge in the TXV bulb may have '
                       'leaked, causing the valve to open fully. Replace TXV if confirmed.\n'
                       '2. TXV BULB DETACHED: Bulb may have lost thermal contact with suction line — '
                       'if reading ambient (warm), valve opens too far. Re-clamp and insulate.\n'
                       '3. EXTERNAL EQUALIZER BROKEN: If the equalizer tube is broken or disconnected, '
                       'the TXV reads atmospheric pressure and opens wide.\n'
                       '4. REFRIGERANT OVERCHARGE: Excess charge floods the evaporator (RF-3).\n'
                       '5. WRONG SUPERHEAT SETTING: TXV may be set too low from factory — adjust stem.\n'
                       '6. COMPRESSOR CYCLING: Rapid on/off cycles cause suction pressure swings that '
                       'drive TXV to over-open during low-pressure periods.')
            elif sh < self.t(thresholds, 'tx2_sh_warning_f'):
                sev = 'WARNING'
                summ = f'S.H_{ab} coil = {sh:.1f}°F — very low, TXV possibly overfeeding.'
                rec = ('Adjust TXV superheat setting — increase by 2-3°F increments.\n'
                       'Monitor S.H_total at compressor inlet (CP-1) — liquid carry-over risk.\n'
                       'Check TXV bulb contact and external equalizer line integrity.')
            else:
                findings.append(self._ok(label))
                continue

            findings.append(Finding(
                scenario_id=self.SCENARIO_ID, label=lbl, component=f'TXV — {label}',
                severity=sev, summary=summ, evidence=evidence, recommendation=rec,
            ))
        return findings


class TX3_TXVHunting(DiagnosticScenario):
    """
    TX-3 · TXV Hunting / Instability (Trend — per module)
    =======================================================
    APPROACH:
      High standard deviation of coil outlet SH over all rows indicates the TXV
      is oscillating between starved and flooded states. Causes: oversized TXV,
      loose bulb, or low load condition.

    COLUMNS: S.H_{ab} coil

    THRESHOLDS:
      tx3_sh_std_warning_f:  5.0
      tx3_sh_std_critical_f: 10.0

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'TX-3'
    COMPONENT   = 'TXV'
    LABEL       = 'TXV Hunting / Instability'
    DESCRIPTION = (
        "TXV hunting occurs when the valve oscillates between open and closed positions instead of "
        "settling at a stable flow rate. The sensing bulb detects low superheat → valve closes → "
        "superheat rises → valve opens → overshoots → repeats. This cycling causes suction pressure "
        "and coil superheat to oscillate rhythmically. Causes: loose or poorly insulated bulb, "
        "oversized valve, or bulb charge degradation. Detected by high standard deviation of coil SH "
        "over time — the values cycle rather than hold steady."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • S.H_{{ab}} coil — coil outlet superheat per module (°F)\n"
        "\n"
        "DECISION (standard deviation over ALL rows, per module):\n"
        "  CRITICAL  if  coil SH std dev > {tx3_sh_std_critical_f}°F  (severe TXV instability)\n"
        "  WARNING   if  coil SH std dev > {tx3_sh_std_warning_f}°F   (TXV oscillating)\n"
        "  OK        otherwise\n"
        "  Note: std dev measures oscillation magnitude — high std dev = hunting"
    )
    THRESHOLD_LABELS = {
        'tx3_sh_std_warning_f':  'Coil SH std dev WARNING threshold — TXV oscillating (°F)',
        'tx3_sh_std_critical_f': 'Coil SH std dev CRITICAL threshold — severe instability (°F)',
    }
    DEFAULT_THRESHOLDS = {
        'tx3_sh_std_warning_f':  5.0,
        'tx3_sh_std_critical_f': 10.0,
    }
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'and', 'conditions': [
            {'column': 'S.H_lh coil', 'function': 'std', 'operator': '>', 'value': 10.0},
        ]},
        'WARNING': {'join': 'and', 'conditions': [
            {'column': 'S.H_lh coil', 'function': 'std', 'operator': '>', 'value': 5.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        for label in ctx.module_labels:
            ab  = _ab(label)
            std = _std(df, f'S.H_{ab} coil')
            if std is None:
                continue
            lbl = f'{self.LABEL} — {label}'
            evidence = (
                f'Why: SH std dev > {self.t(thresholds, "tx3_sh_std_warning_f"):.1f}°F means valve is oscillating, not holding steady.\n'
                f'  S.H_{ab} coil std dev over {len(df)} rows: {std:.1f} °F'
            )

            if std > self.t(thresholds, 'tx3_sh_std_critical_f'):
                sev = 'CRITICAL'
                summ = f'S.H_{ab} coil std={std:.1f}°F — severe TXV instability.'
                rec = ('1. Check TXV sensing bulb is firmly clamped to the suction line — a loose bulb reads ambient, not line temp.\n'
                       '2. Insulate the bulb from ambient air with armaflex or similar — bulb must only sense suction line temperature.\n'
                       "3. Verify the bulb is positioned at the 4 or 8 o'clock position on the suction line, not at 6 o'clock (oil pooling).\n"
                       '4. If bulb placement is correct, the TXV may be oversized — compare to manufacturer sizing chart for R290.\n'
                       '5. Temporarily restrict the TXV manual stem slightly to add damping resistance if hunting is severe.')
            elif std > self.t(thresholds, 'tx3_sh_std_warning_f'):
                sev = 'WARNING'
                summ = f'S.H_{ab} coil std={std:.1f}°F — TXV oscillating.'
                rec = ('1. Check TXV sensing bulb is firmly clamped to the suction line — a loose bulb reads ambient, not line temp.\n'
                       '2. Insulate the bulb from ambient air with armaflex or similar — bulb must only sense suction line temperature.\n'
                       "3. Verify the bulb is positioned at the 4 or 8 o'clock position on the suction line, not at 6 o'clock (oil pooling).\n"
                       '4. If bulb placement is correct, the TXV may be oversized — compare to manufacturer sizing chart for R290.\n'
                       '5. Temporarily restrict the TXV manual stem slightly to add damping resistance if hunting is severe.')
            else:
                findings.append(self._ok(label))
                continue

            findings.append(Finding(
                scenario_id=self.SCENARIO_ID, label=lbl, component=f'TXV — {label}',
                severity=sev, summary=summ, evidence=evidence, recommendation=rec, uses_trend=True,
            ))
        return findings


# ─── DI: DISTRIBUTOR & FILTER DRYER ──────────────────────────────────────────

class DI1_DistributorImbalance(DiagnosticScenario):
    """
    DI-1 · Refrigerant Distributor Imbalance (Point — shared systems ≥ 2 modules)
    ================================================================================
    APPROACH:
      The distributor splits liquid refrigerant from the condenser to each module's TXV.
      A blocked or undersized distributor port causes that module to be starved.
      Key distinguishing feature vs TX-1 (TXV blockage):
        - DI-1: S.C-txv.{ab} is LOWER than S.C at condenser outlet on the affected branch
          (restriction is BEFORE the TXV — less subcooled liquid arriving)
        - TX-1: S.C-txv.{ab} is normal (good liquid arriving), but SH is still high
          (restriction is AT the TXV)
      Also triggers on coil SH imbalance (see EV-2), but adds the distributor-specific
      subcooling cross-check to help isolate the component.

    COLUMNS: S.H_{ab} coil, S.C-txv.{ab}, S.C (condenser outlet SC)

    THRESHOLDS:
      di1_sh_imbalance_warning_f:  8.0
      di1_sc_drop_warning_f:       4.0   (S.C − S.C-txv.{ab} gap)
      trend_window_rows:           10

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'DI-1'
    COMPONENT   = 'Distributor'
    LABEL       = 'Refrigerant Distributor Imbalance'
    APPLIES_TO  = ['cassette', 'modular']  # needs at least 2 modules to compare
    DESCRIPTION = (
        "The splitter distributor divides refrigerant flow between 2 or 3 module branches (Left, Center, Right). "
        "A restriction in one branch orifice reduces flow to that module: its coil SH rises while "
        "the others remain normal. The corroborating sign is a drop in SC from the condenser outlet "
        "to the TXV inlet on the affected branch (flash gas forming in the restricted orifice). "
        "This check only runs on shared systems with 2 or more modules — a single module has no "
        "inter-branch comparison."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • S.H_{{ab}} coil — coil outlet superheat per module (°F)\n"
        "  • S.C — subcooling at shared condenser outlet (°F)\n"
        "  • S.C-txv.{{ab}} — subcooling at TXV inlet per module (°F)\n"
        "  (shared systems with 2+ modules only)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows):\n"
        "  SH spread = max coil SH - min coil SH across all modules\n"
        "  SC drop on affected branch = S.C (condenser) - S.C-txv.{{ab}} (TXV inlet, highest-SH module)\n"
        "\n"
        "  WARNING  if  SH spread > {di1_sh_imbalance_warning_f}°F  AND  SC drop > {di1_sc_drop_warning_f}°F\n"
        "           (both signals confirm distributor restriction, not TXV)\n"
        "  WATCH    if  SH spread > {di1_sh_imbalance_warning_f}°F  (no SC drop corroboration)\n"
        "  OK       otherwise"
    )
    THRESHOLD_LABELS = {
        'di1_sh_imbalance_warning_f': 'SH imbalance WARNING threshold — spread across modules (°F)',
        'di1_sc_drop_warning_f':      'SC drop corroboration threshold — condenser to TXV inlet (°F)',
        'trend_window_rows':          'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'di1_sh_imbalance_warning_f': 8.0,
        'di1_sc_drop_warning_f':      4.0,
        'trend_window_rows':          20,
    }
    DEFAULT_EXPRESSIONS = {
        'WARNING': {'join': 'and', 'conditions': [
            {'column': 'S.H_lh coil', 'column2': 'S.H_rh coil', 'function': 'abs_diff_mean', 'operator': '>', 'value': 8.0},
            {'column': 'S.C', 'column2': 'S.C-txv.lh', 'function': 'diff_mean', 'operator': '>', 'value': 4.0},
        ]},
        'WATCH': {'join': 'and', 'conditions': [
            {'column': 'S.H_lh coil', 'column2': 'S.H_rh coil', 'function': 'abs_diff_mean', 'operator': '>', 'value': 8.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        if ctx.system_type != 'shared' or len(ctx.module_labels) < 2:
            return []
        win = self.t(thresholds, 'trend_window_rows')
        sc_cond = _mean(df, 'S.C', win)  # shared condenser outlet SC
        sh_vals, sc_txv_vals = {}, {}
        for label in ctx.module_labels:
            ab = _ab(label)
            v = _mean(df, f'S.H_{ab} coil', win)
            if v is not None: sh_vals[label] = v
            v2 = _mean(df, f'S.C-txv.{ab}', win)
            if v2 is not None: sc_txv_vals[label] = v2

        if len(sh_vals) < 2:
            return []

        max_lbl = max(sh_vals, key=sh_vals.get)
        min_lbl = min(sh_vals, key=sh_vals.get)
        delta_sh = sh_vals[max_lbl] - sh_vals[min_lbl]
        lines = [
            'Why: High SH on one branch + SC drop on that same branch = flow restriction, not TXV issue.',
            f'  SH imbalance: {delta_sh:.1f}°F ({max_lbl}={sh_vals[max_lbl]:.1f}°F, {min_lbl}={sh_vals[min_lbl]:.1f}°F)',
        ]
        if sc_cond is not None:
            lines.append(f'  S.C at condenser outlet: {sc_cond:.1f}°F')
        for lbl_, v in sc_txv_vals.items():
            drop = (sc_cond - v) if sc_cond is not None else None
            lines.append(f'  S.C-txv.{_ab(lbl_)}: {v:.1f}°F' + (f'  (drop from cond: {drop:.1f}°F)' if drop else ''))

        # Distributor signature: affected branch has both high SH AND lower SC-txv
        affected_ab = _ab(max_lbl)
        sc_drop = None
        if sc_cond is not None and max_lbl in sc_txv_vals:
            sc_drop = sc_cond - sc_txv_vals[max_lbl]

        has_sh_imb = delta_sh > self.t(thresholds, 'di1_sh_imbalance_warning_f')
        has_sc_drop = sc_drop is not None and sc_drop > self.t(thresholds, 'di1_sc_drop_warning_f')

        if has_sh_imb and has_sc_drop:
            sev = 'WARNING'
            summ = (f'SH imbalance {delta_sh:.1f}°F + SC drop of {sc_drop:.1f}°F on {max_lbl} branch '
                    f'— distributor restriction suspected.')
            rec = (f'POSSIBLE CAUSES:\n'
                   f'1. DISTRIBUTOR ORIFICE BLOCKAGE: Inspect orifice on {max_lbl} branch for debris, '
                   f'solder particles, or partial blockage.\n'
                   f'2. ORIFICE SIZING: Compare orifice sizes across all branches — may need re-sizing.\n'
                   f'3. OIL LOGGING: Oil may be trapped in the {max_lbl} circuit, reducing refrigerant flow.\n'
                   f'4. PIPING LENGTH DIFFERENCE: If circuit piping lengths differ significantly, '
                   f'pressure drop differences cause unequal flow.\n'
                   f'5. ELEVATION: If distributor outlets are at different heights, gravity affects '
                   f'refrigerant distribution.\n'
                   f'Note: if S.C-txv is normal but SH is still high, suspect TX-1 (TXV) instead.')
        elif has_sh_imb:
            sev = 'WATCH'
            summ = (f'SH imbalance of {delta_sh:.1f}°F — possible distributor or TXV issue on {max_lbl}.')
            rec = ('Check S.C-txv across modules to isolate distributor (DI-1) vs TXV (TX-1).\n'
                   'If S.C-txv is low on the starved branch, suspect upstream restriction (DI-2).\n'
                   'If S.C-txv is normal, suspect TXV issue on that module.')
        else:
            return [self._ok()]

        return [Finding(
            scenario_id=self.SCENARIO_ID, label=self.LABEL, component=self.COMPONENT,
            severity=sev, summary=summ, evidence='\n'.join(lines), recommendation=rec,
        )]


class DI2_FilterDryerBlockage(DiagnosticScenario):
    """
    DI-2 · Filter Dryer Blockage (Point + Trend)
    ==============================================
    APPROACH:
      A blocked filter dryer causes a pressure drop in the liquid line, which
      partially flashes refrigerant into vapor before it reaches the TXV(s).
      Key signature:
        - S.C at condenser outlet (S.C) is still positive (liquid leaving condenser OK)
        - S.C-txv.{ab} at TXV inlet(s) is significantly LOWER than S.C
        - The gap (S.C − S.C-txv.{ab}) is the fingerprint of the restriction
      Trend version: if this gap is growing larger over time, the filter is
      progressively blocking.

    COLUMNS (shared):   S.C, S.C-txv.{ab} for all modules
    COLUMNS (cassette): S.C-{ab}, S.C-txv.{ab} for all modules in that unit

    THRESHOLDS:
      di2_sc_drop_warning_f:  3.0   (S.C − mean(S.C-txv) > this → WARNING)
      di2_sc_drop_critical_f: 8.0
      di2_gap_slope_per_row:  0.02  (growing gap → progressive blockage)
      trend_window_rows:      10

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'DI-2'
    COMPONENT   = 'Filter Dryer'
    LABEL       = 'Filter Dryer Blockage'
    DESCRIPTION = (
        "The filter dryer removes moisture and particulates from the liquid line. Over time it can "
        "become saturated with contaminants, creating a pressure drop across it. A significant "
        "pressure drop causes partial evaporation (flash gas) at the TXV inlet, reducing the TXV's "
        "effective capacity and starving the evaporator. "
        "Detected by comparing subcooling at the condenser outlet (S.C) versus subcooling at the "
        "TXV inlet (S.C-txv): a large SC drop across the liquid line indicates filter dryer restriction."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • S.C / S.C-{{ab}} — subcooling at condenser outlet (°F)\n"
        "  • S.C-txv.{{ab}} — subcooling at TXV inlet per module (°F)\n"
        "  (cassette: S.C-{{ab}} per unit)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows, per module):\n"
        "  SC drop (gap) = S.C (condenser outlet) - S.C-txv.{{ab}} (TXV inlet)\n"
        "  Gap slope = linear regression on (S.C - S.C-txv) over all rows\n"
        "\n"
        "  CRITICAL  if  SC drop > {di2_sc_drop_critical_f}°F  (filter severely blocked)\n"
        "  WARNING   if  SC drop > {di2_sc_drop_warning_f}°F   (filter restriction)\n"
        "            (adds 'gap growing' note if gap slope > {di2_gap_slope_per_row} °F/row)\n"
        "  OK        otherwise"
    )
    THRESHOLD_LABELS = {
        'di2_sc_drop_warning_f':  'SC drop WARNING threshold — condenser to TXV inlet (°F)',
        'di2_sc_drop_critical_f': 'SC drop CRITICAL threshold — condenser to TXV inlet (°F)',
        'di2_gap_slope_per_row':  'Growing gap slope threshold — progressive blockage (°F/row)',
        'trend_window_rows':      'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'di2_sc_drop_warning_f':  3.0,
        'di2_sc_drop_critical_f': 8.0,
        'di2_gap_slope_per_row':  0.02,
        'trend_window_rows':      20,
    }
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'and', 'conditions': [
            {'column': 'S.C', 'column2': 'S.C-txv.lh', 'function': 'diff_mean', 'operator': '>', 'value': 8.0},
        ]},
        'WARNING': {'join': 'and', 'conditions': [
            {'column': 'S.C', 'column2': 'S.C-txv.lh', 'function': 'diff_mean', 'operator': '>', 'value': 3.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            ab = _ab(label)
            sc_cond = _mean(df, _sc_cond_col(ctx, label), win)
            sc_txv  = _mean(df, f'S.C-txv.{ab}', win)
            if sc_cond is None or sc_txv is None:
                continue

            gap = sc_cond - sc_txv
            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl = f'{self.LABEL}{" — " + suffix if suffix else ""}'

            # Trend: is the gap growing?
            # Compute gap series if both columns exist
            gap_slope = None
            if _has(df, _sc_cond_col(ctx, label)) and _has(df, f'S.C-txv.{ab}'):
                gap_series = df[_sc_cond_col(ctx, label)] - df[f'S.C-txv.{ab}']
                gap_slope = _slope(gap_series.to_frame('gap'), 'gap') if len(gap_series.dropna()) >= 3 else None

            lines = [
                f'  S.C at cond outlet: {sc_cond:.1f}°F',
                f'  S.C-txv.{ab} (TXV inlet): {sc_txv:.1f}°F',
                f'  SC drop across liquid line: {gap:.1f}°F',
            ]
            if gap_slope is not None:
                lines.append(f'  Gap trend: {gap_slope:+.3f} °F/row ({"growing ↑" if gap_slope > 0 else "stable"})')

            growing = gap_slope is not None and gap_slope > self.t(thresholds, 'di2_gap_slope_per_row')

            if gap > self.t(thresholds, 'di2_sc_drop_critical_f'):
                sev = 'CRITICAL'
                summ = f'SC drops {gap:.1f}°F between condenser and TXV — filter dryer severely blocked.'
                rec = ('Replace filter dryer immediately.\n'
                       'POSSIBLE CAUSES OF BLOCKAGE:\n'
                       '1. MOISTURE CONTAMINATION: Moisture reacts with refrigerant oil to form acids '
                       'that clog the dryer core. Replace dryer and check for moisture entry points.\n'
                       '2. SOLDER/BRAZE DEBRIS: Particles from installation can block the screen.\n'
                       '3. ACID FORMATION: Compressor motor burnout produces acids that saturate the dryer.\n'
                       '4. UNDERSIZED DRYER: Verify filter dryer capacity matches system requirements.\n'
                       'After replacement: pull deep vacuum (below 500 microns) and recharge.')
            elif gap > self.t(thresholds, 'di2_sc_drop_warning_f'):
                sev = 'WARNING' if not growing else 'WARNING'
                summ = (f'SC drops {gap:.1f}°F in liquid line — filter dryer restriction.'
                        + (' Gap is growing (progressive blockage).' if growing else ''))
                rec = ('Plan to replace filter dryer. Monitor gap — if growing, replace urgently.\n'
                       'Inspect for moisture entry points (recent system opening, service history).\n'
                       'Check for solder/braze debris from recent installation or repair work.\n'
                       'Verify filter dryer is correctly sized for the system capacity.')
            else:
                findings.append(self._ok(suffix))
                if ctx.system_type == 'shared': break
                continue

            findings.append(Finding(
                scenario_id=self.SCENARIO_ID, label=lbl, component=self.COMPONENT,
                severity=sev, summary=summ, evidence='\n'.join(lines),
                recommendation=rec, uses_trend=growing,
            ))
            if ctx.system_type == 'shared':
                break
        return findings


class DI3_EvaporatorDistributorRestriction(DiagnosticScenario):
    """
    DI-3 · Evaporator Distributor Restriction (Point — per module)
    ================================================================
    APPROACH:
      The evaporator distributor splits refrigerant from the TXV into multiple
      circuits within a single coil. A restriction or undersizing creates a
      pressure drop across the distributor, causing partial flash evaporation:
        T_1a-{ab}: TXV outlet / distributor inlet  (should be subcooled liquid)
        T_1b-{ab}: Coil inlet / post-distributor   (temp entering coil circuits)
      Normal: T_1b ≈ T_1a (liquid passes cleanly, minimal ΔP).
      Restriction: ΔP → partial flash → T_1b > T_1a (gas is warmer than subcooled liquid).
      Large positive ΔT = (T_1b − T_1a) → evaporator distributor restriction or undersizing.

    COLUMNS: T_1a-{ab}, T_1b-{ab}  (same naming convention for both system types)

    THRESHOLDS:
      di3_delta_watch_f:   3.0    # °F above which to WATCH
      di3_delta_warning_f: 6.0    # °F above which WARNING
      trend_window_rows:   20

    UPDATE LOG:
      - 2026-03-05: Initial implementation. Distinct from DI-1 (splitter distributor
                    between modules). This checks within-coil circuit distribution.
    """
    SCENARIO_ID = 'DI-3'
    COMPONENT   = 'Evaporator Distributor'
    LABEL       = 'Evaporator Distributor Restriction'
    DESCRIPTION = (
        "The evaporator distributor splits refrigerant from the TXV into multiple circuits within "
        "a single coil (typically 4–8 circuits). A restriction or undersizing in the distributor "
        "creates a pressure drop that causes partial flash evaporation inside the distributor body. "
        "This is detected by comparing T_1a (TXV outlet / distributor inlet, subcooled liquid) "
        "to T_1b (coil inlet, post-distribution): if T_1b > T_1a, refrigerant has flashed inside "
        "the distributor, confirming restriction."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • T_1a-{{ab}} — TXV outlet / evaporator distributor inlet temperature (°F)\n"
        "  • T_1b-{{ab}} — coil inlet / post-distributor temperature (°F)\n"
        "  (same column naming for shared and cassette systems)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows, per module):\n"
        "  ΔT = T_1b - T_1a  (positive = refrigerant flashed inside distributor)\n"
        "\n"
        "  WARNING  if  ΔT > {di3_delta_warning_f}°F  (flash gas confirmed in distributor)\n"
        "  WATCH    if  ΔT > {di3_delta_watch_f}°F    (slight flash gas possible)\n"
        "  OK       otherwise  (T_1b ≈ T_1a = clean liquid passing through)"
    )
    THRESHOLD_LABELS = {
        'di3_delta_watch_f':   'ΔT WATCH threshold — T_1b minus T_1a (°F)',
        'di3_delta_warning_f': 'ΔT WARNING threshold — T_1b minus T_1a (°F)',
        'trend_window_rows':   'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'di3_delta_watch_f':   3.0,
        'di3_delta_warning_f': 6.0,
        'trend_window_rows':   20,
    }
    DEFAULT_EXPRESSIONS = {
        'WARNING': {'join': 'and', 'conditions': [
            {'column': 'T_1b-lh', 'column2': 'T_1a-lh', 'function': 'diff_mean', 'operator': '>', 'value': 6.0},
        ]},
        'WATCH': {'join': 'and', 'conditions': [
            {'column': 'T_1b-lh', 'column2': 'T_1a-lh', 'function': 'diff_mean', 'operator': '>', 'value': 3.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            t1a = _mean(df, _t1a_col(label), win)
            t1b = _mean(df, _t1b_col(label), win)
            if t1a is None or t1b is None:
                continue
            delta = t1b - t1a   # positive = T_1b warmer → flash gas in distributor
            ab    = _ab(label)
            lbl   = f'{self.LABEL} — {label}'
            evidence = (
                f'  T_1a-{ab} (distributor inlet): {t1a:.1f} °F\n'
                f'  T_1b-{ab} (coil inlet):        {t1b:.1f} °F\n'
                f'  ΔT = T_1b − T_1a:              {delta:+.1f} °F'
            )

            if delta > self.t(thresholds, 'di3_delta_warning_f'):
                sev  = 'WARNING'
                summ = f'ΔT = T_1b − T_1a = {delta:+.1f}°F on {label} — flash gas in evap distributor.'
                rec  = ('POSSIBLE CAUSES (A positive T_1b − T_1a means refrigerant is flashing inside the distributor):\n'
                        '1. DISTRIBUTOR BLOCKAGE: Inspect for debris, solder intrusion from brazing, or '
                        'foreign material blocking flow.\n'
                        '2. UNDERSIZED ORIFICE/NOZZLE: Verify distributor nozzle size matches design capacity.\n'
                        '3. IMPROPER BRAZING: Solder may have intruded into the distributor body during '
                        'installation — requires replacement if confirmed.\n'
                        '4. LOW SUBCOOLING AT TXV INLET: If S.C-txv is low, refrigerant is already flashing '
                        'before it enters the distributor. Check filter dryer (DI-2) and charge (RF-2).')
            elif delta > self.t(thresholds, 'di3_delta_watch_f'):
                sev  = 'WATCH'
                summ = f'ΔT = T_1b − T_1a = {delta:+.1f}°F on {label} — slight flash gas possible.'
                rec  = ('Monitor S.C-txv to verify adequate subcooling reaching the TXV.\n'
                        'Check for partial blockage in distributor if this worsens over time.')
            else:
                findings.append(self._ok(label))
                continue

            findings.append(Finding(
                scenario_id=self.SCENARIO_ID, label=lbl,
                component=f'Evaporator Distributor — {label}',
                severity=sev, summary=summ, evidence=evidence, recommendation=rec,
            ))
        return findings


class SL1_SuctionLineRestriction(DiagnosticScenario):
    """
    SL-1 · Suction Line Restriction / Excessive Heat Gain (Point)
    ==============================================================
    APPROACH:
      Only applicable to shared systems with ≥2 modules.
      Suction line SH gain = S.H_total (at compressor) − max(S.H_{ab} coil across modules).
      This quantity represents heat accumulated between the coil outlets and the compressor
      suction port. Normal = 5–10°F (ambient gain through insulation).
      High gain = poor insulation or partial restriction causing pressure drop and
      additional superheat accumulation in the suction line.

    COLUMNS: S.H_total, S.H_{ab} coil (all modules), P_suction
    SYSTEM:  shared only (cassette units have short, independent suction lines)

    THRESHOLDS:
      sl1_sh_gain_watch_f:   10.0
      sl1_sh_gain_warning_f: 25.0
      trend_window_rows:     20

    UPDATE LOG:
      - 2026-03-05: Initial implementation. Cassette excluded — per-unit lines are short.
    """
    SCENARIO_ID = 'SL-1'
    COMPONENT   = 'Suction Line'
    LABEL       = 'Suction Line Heat Gain / Restriction'
    DESCRIPTION = (
        "The suction line carries low-pressure refrigerant vapour from the evaporator coil outlets "
        "to the compressor inlet. Heat gained through the suction line insulation adds superheat "
        "without adding any cooling capacity — it just makes the compressor work harder. "
        "In multi-module shared systems, suction line SH gain = S.H_total (at compressor) minus "
        "the highest coil SH (at the furthest coil outlet). Normal gain is 5–10°F through good insulation; "
        "higher values indicate insulation damage, missing insulation, or a partial restriction."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • S.H_total — superheat at compressor inlet (°F)\n"
        "  • S.H_{{ab}} coil — coil outlet superheat per module (°F)\n"
        "  (shared systems with 2+ modules only; cassette excluded — short independent lines)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows):\n"
        "  SH gain = S.H_total - max(S.H_{{ab}} coil across all modules)\n"
        "  (represents heat accumulated between furthest coil outlet and compressor inlet)\n"
        "\n"
        "  WARNING  if  SH gain > {sl1_sh_gain_warning_f}°F  (significant insulation loss or restriction)\n"
        "  WATCH    if  SH gain > {sl1_sh_gain_watch_f}°F    (elevated — check insulation)\n"
        "  OK       otherwise  (normal: 5–10°F gain through good insulation)"
    )
    THRESHOLD_LABELS = {
        'sl1_sh_gain_watch_f':   'SH gain WATCH threshold — suction line heat pickup (°F)',
        'sl1_sh_gain_warning_f': 'SH gain WARNING threshold — suction line heat pickup (°F)',
        'trend_window_rows':     'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'sl1_sh_gain_watch_f':   10.0,
        'sl1_sh_gain_warning_f': 25.0,
        'trend_window_rows':     20,
    }
    DEFAULT_EXPRESSIONS = {
        'WARNING': {'join': 'and', 'conditions': [
            {'column': 'S.H_total', 'column2': 'S.H_lh coil', 'function': 'diff_mean', 'operator': '>', 'value': 25.0},
        ]},
        'WATCH': {'join': 'and', 'conditions': [
            {'column': 'S.H_total', 'column2': 'S.H_lh coil', 'function': 'diff_mean', 'operator': '>', 'value': 10.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        # Only applicable to shared systems with ≥2 modules
        if ctx.system_type != 'shared' or len(ctx.module_labels) < 2:
            return []
        win = self.t(thresholds, 'trend_window_rows')

        sh_total = _mean(df, 'S.H_total', win)
        if sh_total is None:
            return []

        coil_shs = {}
        for label in ctx.module_labels:
            ab = _ab(label)
            v  = _mean(df, f'S.H_{ab} coil', win)
            if v is not None:
                coil_shs[label] = v
        if not coil_shs:
            return []

        max_coil_sh  = max(coil_shs.values())
        max_coil_lbl = max(coil_shs, key=coil_shs.get)
        sh_gain      = sh_total - max_coil_sh

        lines = [
            f'  S.H_total (at compressor inlet):           {sh_total:.1f} °F',
            f'  Max coil SH (at {max_coil_lbl} coil exit): {max_coil_sh:.1f} °F',
            f'  Suction line SH gain:                       {sh_gain:.1f} °F',
        ]

        if sh_gain > self.t(thresholds, 'sl1_sh_gain_warning_f'):
            sev  = 'WARNING'
            summ = f'Suction line heat gain = {sh_gain:.1f}°F — significant insulation loss or restriction.'
            rec  = ('POSSIBLE CAUSES:\n'
                    '1. INSULATION DAMAGE: Inspect suction line insulation for gaps, tears, '
                    'compression, or missing sections. Check for condensation (wet insulation).\n'
                    '2. HOT PIPE ROUTING: Suction line may run near heat sources (steam pipes, '
                    'hot water lines, electrical equipment). Re-route or add shielding.\n'
                    '3. UNCONDITIONED SPACE: Suction line passes through unconditioned (hot) area. '
                    'Add or upgrade insulation in those sections.\n'
                    '4. VALVE RESTRICTION: Check for partially closed valves between coil outlets and '
                    'compressor — restriction causes pressure drop → superheat rise.\n'
                    '5. VAPOR BARRIER: Insulation vapor barrier may be compromised, allowing moisture '
                    'absorption that reduces R-value over time.\n'
                    '6. KINK/OBSTRUCTION: Verify no kinks or obstructions in suction line routing.\n'
                    'Impact: High gain raises discharge temp (CP-2) without adding cooling capacity.')
        elif sh_gain > self.t(thresholds, 'sl1_sh_gain_watch_f'):
            sev  = 'WATCH'
            summ = f'Suction line heat gain = {sh_gain:.1f}°F — elevated, check insulation.'
            rec  = ('Inspect suction line insulation. Typical gain is 5–10°F.\n'
                    'Values above 10°F indicate insulation degradation.')
        else:
            return [Finding(
                scenario_id=self.SCENARIO_ID, label=self.LABEL, component=self.COMPONENT,
                severity='OK',
                summary=f'Suction line heat gain = {sh_gain:.1f}°F — within normal range (≤10°F).',
                evidence='\n'.join(lines), recommendation='',
            )]

        return [Finding(
            scenario_id=self.SCENARIO_ID, label=self.LABEL, component=self.COMPONENT,
            severity=sev, summary=summ, evidence='\n'.join(lines), recommendation=rec,
        )]


# ─── HG: HOT GAS DEFROST ─────────────────────────────────────────────────────

class HG1_DefrostIneffective(DiagnosticScenario):
    """
    HG-1 · Defrost Ineffective / Blocked Hot Gas Line (Indirect)
    =============================================================
    APPROACH:
      No dedicated defrost sensors — detection is indirect.
      Uses defrost_detection.detect_defrost_periods() to find defrost periods
      (identified by P_disch − P_suction differential collapsing to near zero).
      During a valid defrost period, coil inlet temperature (T_1b-{ab}) should
      rise as hot gas warms the coil. If it does NOT rise by the expected amount,
      the hot gas path may be blocked.
      Also: if no defrost periods are detected across a long test run, flags
      that defrost may not be initiating.

    COLUMNS: T_1b-{ab} per module, P_disch / P_suction (for defrost detection)
    REQUIRES: 'Timestamp' column in df for defrost_detection.

    THRESHOLDS:
      hg1_defrost_temp_rise_min_f:     10.0   Expected min coil temp rise during defrost
      hg1_max_rows_without_defrost:   240     Flag if no defrost in this many rows
      trend_window_rows:               10

    FALSE POSITIVES:
      - Defrost detection may miss very short defrosts or defrosts with atypical
        pressure signatures. Increase threshold if flagging incorrectly.

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'HG-1'
    COMPONENT   = 'Hot Gas Defrost'
    LABEL       = 'Defrost Ineffective / Hot Gas Blocked'
    DESCRIPTION = (
        "Hot gas defrost uses high-pressure discharge gas to melt frost from the evaporator coil. "
        "An effective defrost cycle should raise coil temperature above 32°F within a predictable "
        "time window, shedding all accumulated frost. If the defrost cycle completes but frost "
        "remains (detected by coil temperature not reaching 35°F), the hot gas flow is insufficient: "
        "a check valve may be failing, the hot gas solenoid may be partially open, or defrost "
        "duration may be too short for the frost load."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • P_disch, P_suction — used by defrost_detection to identify defrost periods\n"
        "    (defrost detected when P_disch - P_suction differential collapses near zero)\n"
        "  • T_1b-{{ab}} — coil inlet temperature per module (°F)\n"
        "  • Timestamp — required for defrost period time windowing\n"
        "\n"
        "DECISION:\n"
        "  WATCH    if  no defrost periods detected in > {hg1_max_rows_without_defrost} rows\n"
        "  WARNING  if  during a detected defrost period, T_1b-{{ab}} rise < {hg1_defrost_temp_rise_min_f}°F\n"
        "           (coil did not warm sufficiently — hot gas path may be blocked)\n"
        "  (no finding if all detected defrost periods show adequate temperature rise)"
    )
    THRESHOLD_LABELS = {
        'hg1_defrost_temp_rise_min_f':   'Min coil temp rise during defrost period (°F)',
        'hg1_max_rows_without_defrost':  'Max rows before flagging no-defrost detected',
    }
    DEFAULT_THRESHOLDS = {
        'hg1_defrost_temp_rise_min_f':   10.0,
        'hg1_max_rows_without_defrost':  240,
    }
    # HG-1 requires the defrost_detection algorithm (pressure differential analysis)
    # which cannot be expressed as a column comparison. Falls back to Python run().
    DEFAULT_EXPRESSIONS = {}

    def run(self, df, ctx, thresholds):
        if 'Timestamp' not in df.columns:
            return [Finding(
                scenario_id=self.SCENARIO_ID, label=self.LABEL,
                component=self.COMPONENT, severity='INFO',
                summary='Cannot run — no Timestamp column in data.',
                evidence='Defrost detection requires a Timestamp column.',
                recommendation='Ensure Timestamp is included in the dataset.',
            )]

        try:
            from defrost_detection import detect_defrost_periods
        except ImportError:
            return []

        label0 = ctx.module_labels[0]
        d_col = _disc_col(ctx, label0)
        s_col = _suc_col(ctx, label0)

        if not _has(df, d_col) or not _has(df, s_col):
            return []

        try:
            periods = detect_defrost_periods(df, d_col, s_col)
        except Exception as e:
            logging.warning(f'[HG-1] defrost detection failed: {e}')
            return []

        max_rows = self.t(thresholds, 'hg1_max_rows_without_defrost')
        if not periods and len(df) > max_rows:
            return [Finding(
                scenario_id=self.SCENARIO_ID, label=self.LABEL,
                component=self.COMPONENT, severity='WATCH',
                summary=f'No defrost periods detected in {len(df)} rows of data.',
                evidence=f'  Rows: {len(df)} (threshold: {max_rows})\n  No pressure equalisation events found.',
                recommendation=('POSSIBLE CAUSES:\n'
                                '1. DEFROST TIMER/SCHEDULE: Verify defrost is configured and timer is '
                                'triggering at the expected interval.\n'
                                '2. HOT GAS SOLENOID: Check solenoid valve operation — coil may be '
                                'de-energized, stuck closed, or wiring disconnected.\n'
                                '3. CONTROLLER BOARD: Defrost controller may have failed. Check for '
                                'error codes or indicator lights.\n'
                                '4. Manual defrost cycle may be needed to clear existing ice buildup.'),
            )]

        # Check temperature rise during detected defrost periods
        issues = []
        min_rise = self.t(thresholds, 'hg1_defrost_temp_rise_min_f')
        for label in ctx.module_labels:
            ab   = _ab(label)
            t1b  = f'T_1b-{ab}'
            if not _has(df, t1b):
                continue
            for (start_ts, end_ts, dur, _) in periods:
                try:
                    mask = (df['Timestamp'] >= start_ts) & (df['Timestamp'] <= end_ts)
                    seg  = df.loc[mask, t1b].dropna()
                    if len(seg) < 2:
                        continue
                    rise = float(seg.max() - seg.min())
                    if rise < min_rise:
                        issues.append(f'  {label}: temp rise={rise:.1f}°F during defrost at {start_ts} (expected ≥{min_rise}°F)')
                except Exception:
                    continue

        if issues:
            return [Finding(
                scenario_id=self.SCENARIO_ID, label=self.LABEL,
                component=self.COMPONENT, severity='WARNING',
                summary=f'Coil temperature did not rise sufficiently during {len(issues)} defrost period(s).',
                evidence='\n'.join(issues),
                recommendation=('POSSIBLE CAUSES:\n'
                                 '1. HOT GAS LINE BLOCKAGE: Inspect for blockage in solenoid valve, check valve, '
                                 'or kinked tube in the hot gas line.\n'
                                 '2. VALVE NOT FULLY OPENING: Verify hot gas valve opens fully during defrost — '
                                 'low coil voltage or weak solenoid spring can cause partial opening.\n'
                                 '3. TERMINATION THERMOSTAT: Check defrost termination thermostat is not cutting '
                                 'defrost short before ice is fully melted.\n'
                                 '4. LOW DISCHARGE PRESSURE: If discharge pressure is low during defrost, '
                                 'insufficient hot gas energy reaches the coil.\n'
                                 '5. CHECK VALVE: Check valve in the hot gas line may not be seating properly.\n'
                                 '6. DRAIN PAN BLOCKED: Ice in the drain pan can refreeze and block drainage, '
                                 'causing ice to re-accumulate on the coil.'),
            )]
        return []


class HG2_DefrostBackwards(DiagnosticScenario):
    """
    HG-2 · Hot Gas Defrost Possibly Installed Backwards (Indirect)
    ================================================================
    APPROACH:
      If the hot gas defrost line is installed backwards, hot gas enters from the
      wrong end of the coil. Indirect signature during detected defrost periods:
        - Suction pressure spikes sharply at defrost START (hot gas entering
          low-pressure side → pressure equalises from suction end)
        - Coil temperature at the expected hot-gas-inlet end does NOT rise quickly

    THRESHOLDS:
      hg2_suction_spike_psig: 5.0   Suction pressure rise at defrost start

    NOTE: Low-confidence check. Always marked WARNING, not CRITICAL.
          Confirm by visual inspection of the defrost piping.

    FALSE POSITIVES:
      Pressure spikes at defrost termination/start are sometimes normal.
      Only flag if spike is at START and not at termination.

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'HG-2'
    COMPONENT   = 'Hot Gas Defrost'
    LABEL       = 'Defrost Possibly Installed Backwards'
    ENABLED     = True
    DESCRIPTION = (
        "A hot gas defrost system that activates when conditions do not call for it, or that "
        "causes suction pressure to rise unexpectedly during what should be normal refrigeration, "
        "may have a mis-wired or stuck-open hot gas solenoid. "
        "This check detects anomalous suction pressure rises coinciding with discharge pressure "
        "drops — the signature of hot gas being inadvertently routed to the suction side, "
        "effectively creating a refrigerant short-circuit."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • P_disch, P_suction — used by defrost_detection to identify defrost periods\n"
        "  • P_suction / P_suc-{{ab}} — suction pressure during defrost (PSIG)\n"
        "  • Timestamp — required for defrost period time windowing\n"
        "\n"
        "DECISION (during detected defrost periods only):\n"
        "  Spike = suction pressure max - first value, measured in first 20% of defrost period\n"
        "\n"
        "  WARNING  if  suction pressure spike > {hg2_suction_spike_psig} PSIG at defrost START\n"
        "           (hot gas entering suction side — backwards installation suspected)\n"
        "  (low-confidence check — confirm by visual inspection of hot gas piping)"
    )
    THRESHOLD_LABELS = {
        'hg2_suction_spike_psig': 'Suction pressure spike WARNING threshold at defrost start (PSIG)',
    }
    DEFAULT_THRESHOLDS = {'hg2_suction_spike_psig': 5.0}
    # HG-2 requires the defrost_detection algorithm — falls back to Python run().
    DEFAULT_EXPRESSIONS = {}

    def run(self, df, ctx, thresholds):
        if 'Timestamp' not in df.columns:
            return []
        try:
            from defrost_detection import detect_defrost_periods
        except ImportError:
            return []

        label0 = ctx.module_labels[0]
        d_col = _disc_col(ctx, label0)
        s_col = _suc_col(ctx, label0)
        if not _has(df, d_col) or not _has(df, s_col):
            return []

        try:
            periods = detect_defrost_periods(df, d_col, s_col)
        except Exception:
            return []

        if not periods:
            return []

        spike_thr = self.t(thresholds, 'hg2_suction_spike_psig')
        issues = []
        for (start_ts, end_ts, dur, _) in periods:
            try:
                mask = (df['Timestamp'] >= start_ts) & (df['Timestamp'] <= end_ts)
                seg  = df.loc[mask, s_col].dropna()
                if len(seg) < 3:
                    continue
                # Check spike in first 20% of defrost period
                first_slice = seg.iloc[:max(2, len(seg)//5)]
                spike = float(first_slice.max() - first_slice.iloc[0])
                if spike > spike_thr:
                    issues.append(f'  Suction pressure spike={spike:.1f}°F at defrost start ({start_ts})')
            except Exception:
                continue

        if issues:
            return [Finding(
                scenario_id=self.SCENARIO_ID, label=self.LABEL,
                component=self.COMPONENT, severity='WARNING',
                summary=f'Suction pressure spikes at defrost start in {len(issues)} period(s) — backwards installation suspected.',
                evidence='\n'.join(issues),
                recommendation=('LOW CONFIDENCE — confirm by visual inspection of hot gas piping.\n'
                                 'Check that hot gas enters from the intended end of the coil (top or outlet end).\n'
                                 'Refer to manufacturer installation diagram for correct piping direction.'),
            )]
        return []


# ─── SI: SENSOR / THERMODYNAMIC IMPOSSIBILITIES ──────────────────────────────

class SI1_NegativeSubcooling(DiagnosticScenario):
    """
    SI-1 · Negative Subcooling — Vapor in Liquid Line (Point)
    ===========================================================
    APPROACH:
      Subcooling below zero means saturated liquid/vapor mixture in the liquid
      line. This causes flash gas at the TXV inlet, reducing capacity and
      causing erratic TXV operation.

    COLUMNS (shared):   S.C
    COLUMNS (cassette): S.C-{ab}

    THRESHOLDS:
      si1_sc_mild_f:    0.0    (< 0 → WARNING)
      si1_sc_moderate_f: -5.0  (< -5 → CRITICAL)
      si1_sc_severe_f:  -15.0  (< -15 → possible sensor error)
      trend_window_rows: 10

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'SI-1'
    COMPONENT   = 'Refrigerant'
    LABEL       = 'Negative Subcooling'
    DESCRIPTION = (
        "Subcooling is the temperature difference between the saturated condensing temperature "
        "and the actual liquid temperature leaving the condenser. It must always be positive: "
        "a negative value means the measured liquid temperature is above saturation, which is "
        "thermodynamically impossible for a pure liquid. This indicates a sensor error, wrong "
        "sensor port assignment, or a calculation error in the refrigerant property lookup."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • S.C — subcooling at condenser outlet (°F)\n"
        "  (cassette: S.C-{{ab}} per unit)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows):\n"
        "  CRITICAL  if  SC < {si1_sc_severe_f}°F   (severe — possible sensor error or massive undercharge)\n"
        "  CRITICAL  if  SC < {si1_sc_moderate_f}°F (moderate — vapour in liquid line)\n"
        "  WARNING   if  SC < {si1_sc_mild_f}°F     (mild negative subcooling)\n"
        "  OK        otherwise  (SC >= 0 is thermodynamically required)"
    )
    THRESHOLD_LABELS = {
        'si1_sc_mild_f':     'SC WARNING threshold — mild negative subcooling (°F)',
        'si1_sc_moderate_f': 'SC CRITICAL threshold — moderate vapour in liquid line (°F)',
        'si1_sc_severe_f':   'SC CRITICAL threshold — severe / possible sensor error (°F)',
        'trend_window_rows': 'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'si1_sc_mild_f':    0.0,
        'si1_sc_moderate_f': -5.0,
        'si1_sc_severe_f':  -15.0,
        'trend_window_rows': 20,
    }
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'and', 'conditions': [
            {'column': 'S.C', 'function': 'mean', 'operator': '<', 'value': -5.0},
        ]},
        'WARNING': {'join': 'and', 'conditions': [
            {'column': 'S.C', 'function': 'mean', 'operator': '<', 'value': 0.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            sc = _mean(df, _sc_cond_col(ctx, label), win)
            if sc is None:
                continue
            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl = f'{self.LABEL}{" — " + suffix if suffix else ""}'
            evidence = f'  S.C (avg last {win} rows): {sc:.1f} °F'

            if sc < self.t(thresholds, 'si1_sc_severe_f'):
                sev = 'CRITICAL'
                summ = f'S.C = {sc:.1f}°F — severe. Possible sensor error or massive undercharge.'
                rec = ('POSSIBLE CAUSES (check in order):\n'
                       '1. SENSOR ERROR: Verify T_4a (condenser outlet) sensor calibration and placement — '
                       'ensure it is on the liquid line, not on the condenser shell or ambient.\n'
                       '2. PRESSURE SENSOR: Check P_disch transducer — if it reads low, T_sat.cond will be '
                       'wrong, producing false negative SC. Verify calibration.\n'
                       '3. WRONG REFRIGERANT: Confirm R290 was charged. A different refrigerant (R134a, R404A) '
                       'will give wrong T_sat from the pressure reading.\n'
                       '4. MASSIVE UNDERCHARGE: Refrigerant may be so low that condenser outlet is two-phase — '
                       'check RF-2 and weigh charge against nameplate.\n'
                       '5. NON-CONDENSABLES: Air/nitrogen in circuit raises P_disch above true condensing pressure — '
                       'check RF-4.\n'
                       '6. WATER GPM TOO LOW: Insufficient water flow prevents full condensation — check CD-2. '
                       'Verify water pump operation, valve positions, and flow meter reading.\n'
                       '7. WATER INLET TEMP TOO HIGH: If T_waterin is above design, condenser cannot reject '
                       'enough heat — check CD-1 approach temperature.')
            elif sc < self.t(thresholds, 'si1_sc_moderate_f'):
                sev = 'CRITICAL'
                summ = f'S.C = {sc:.1f}°F — vapor in liquid line (moderate).'
                rec = ('POSSIBLE CAUSES:\n'
                       '1. INSUFFICIENT CONDENSER CAPACITY: Check water flow rate (CD-2) — low GPM is the '
                       'most common cause of incomplete condensation.\n'
                       '2. CONDENSER FOULING: Scale, biofilm, or debris on heat exchange surfaces reduces '
                       'heat rejection — check CD-1 approach temperature.\n'
                       '3. REFRIGERANT UNDERCHARGE: Weigh charge and compare to nameplate (RF-2).\n'
                       '4. WATER CIRCUIT AIR LOCK: Air in the water loop reduces effective flow — bleed air vents.\n'
                       '5. HIGH WATER INLET TEMPERATURE: Check T_waterin against design spec.\n'
                       '6. SENSOR DRIFT: Verify T_4a sensor has not drifted — compare to handheld thermometer.')
            elif sc < self.t(thresholds, 'si1_sc_mild_f'):
                sev = 'WARNING'
                summ = f'S.C = {sc:.1f}°F — mild negative subcooling.'
                rec = ('Monitor closely — may worsen as operating conditions change.\n'
                       'Check condenser water flow rate and inlet temperature (CD-2).\n'
                       'Verify refrigerant charge is at nameplate weight (RF-2).\n'
                       'Check T_4a sensor calibration — mild drift could cause false reading.\n'
                       'If water GPM meter is installed, verify reading matches actual flow.')
            else:
                findings.append(self._ok(suffix))
                if ctx.system_type == 'shared': break
                continue

            findings.append(Finding(
                scenario_id=self.SCENARIO_ID, label=lbl, component=self.COMPONENT,
                severity=sev, summary=summ, evidence=evidence, recommendation=rec,
            ))
            if ctx.system_type == 'shared':
                break
        return findings


class SI2_EnthalpyReversal(DiagnosticScenario):
    """
    SI-2 · Enthalpy Reversal — Thermodynamic Impossibility (Point)
    ===============================================================
    APPROACH:
      H_comp.in should be greater than H_txv.{ab} (refrigerant gains enthalpy
      through the evaporator). If H_comp.in < H_txv.{ab}, the cycle is running
      backwards thermodynamically — impossible at steady state. Indicates sensor
      errors or calculation issue.

    COLUMNS (shared):   H_comp.in, H_txv.{ab} per module
    COLUMNS (cassette): H_comp.in-{ab}, H_txv.{ab} per module

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'SI-2'
    COMPONENT   = 'Sensors / Calculations'
    LABEL       = 'Enthalpy Reversal (Thermodynamic Impossibility)'
    DESCRIPTION = (
        "In a correctly operating refrigeration circuit, enthalpy increases through the evaporator "
        "(refrigerant absorbs heat) and decreases through the condenser (refrigerant rejects heat). "
        "An enthalpy reversal — where the evaporator outlet enthalpy is lower than its inlet, or "
        "the condenser outlet is higher than its inlet — is thermodynamically impossible and indicates "
        "sensor errors, wrong port mapping, or incorrect refrigerant property calculation."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • H_comp.in — enthalpy at compressor inlet / evaporator outlet (kJ/kg)\n"
        "  • H_txv.{{ab}} — enthalpy at TXV inlet / evaporator inlet per module (kJ/kg)\n"
        "  (cassette: H_comp.in-{{ab}} per unit)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows, per module):\n"
        "  CRITICAL  if  H_comp.in < H_txv.{{ab}}\n"
        "           (evaporator outlet enthalpy lower than inlet — thermodynamically impossible)\n"
        "  OK        otherwise  (evaporator must add enthalpy: H_comp.in > H_txv)"
    )
    THRESHOLD_LABELS = {
        'trend_window_rows': 'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {'trend_window_rows': 20}
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'and', 'conditions': [
            {'column': 'H_comp.in', 'column2': 'H_txv.lh', 'function': 'diff_mean', 'operator': '<', 'value': 0.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            ab = _ab(label)
            h_comp = _mean(df, _h_comp_in_col(ctx, label), win)
            h_txv  = _mean(df, f'H_txv.{ab}', win)
            if h_comp is None or h_txv is None:
                continue
            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl = f'{self.LABEL}{" — " + suffix if suffix else ""}'
            if h_comp < h_txv:
                findings.append(Finding(
                    scenario_id=self.SCENARIO_ID, label=lbl, component=self.COMPONENT,
                    severity='CRITICAL',
                    summary=f'H_comp.in ({h_comp:.2f}) < H_txv.{ab} ({h_txv:.2f}) — evaporator has negative enthalpy gain.',
                    evidence=(f'  H_comp.in: {h_comp:.3f} kJ/kg\n'
                              f'  H_txv.{ab}: {h_txv:.3f} kJ/kg\n'
                              f'  Difference: {h_comp - h_txv:.3f} kJ/kg'),
                    recommendation=('POSSIBLE CAUSES:\n'
                                    '1. SENSOR SWAP: Temperature sensors at coil inlet and outlet may be wired '
                                    'to the wrong data acquisition channels — verify against Diagram tab.\n'
                                    '2. PRESSURE SENSOR ERROR: If P_suction is reading wrong, the enthalpy '
                                    'calculation (which uses pressure + temperature) will be incorrect. '
                                    'Check transducer calibration and zero offset.\n'
                                    '3. POOR THERMAL CONTACT: Sensor not in good contact with pipe — reading '
                                    'ambient instead of refrigerant temperature. Check sensor clamping.\n'
                                    '4. WRONG REFRIGERANT IN SOFTWARE: If CoolProp is set to R290 but actual '
                                    'charge is different, all enthalpy lookups will be wrong.\n'
                                    '5. REFRIGERANT SHORT-CYCLING: Inspect for bypass path around evaporator.'),
                ))
            else:
                findings.append(self._ok(suffix))
            if ctx.system_type == 'shared':
                break
        return findings


class SI3_SubAtmosphericPressure(DiagnosticScenario):
    """
    SI-3 · Sub-Atmospheric Suction Pressure (Point)
    =================================================
    APPROACH:
      Suction pressure below -14.696 PSIG means below absolute zero pressure —
      physically impossible. Indicates a sensor error.

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'SI-3'
    COMPONENT   = 'Sensors / Calculations'
    LABEL       = 'Sub-Atmospheric Pressure — Sensor Error'
    DESCRIPTION = (
        "R290 (propane) has a boiling point of -43.7°F at atmospheric pressure. Under normal "
        "refrigeration operating conditions, suction pressure must always be above atmospheric "
        "(0 PSIG) or the system would be drawing air inward through any leak. "
        "A negative PSIG reading indicates either a sensor calibration error, a disconnected "
        "transducer reading near zero, or (rarely) actual vacuum in the circuit after a severe leak."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • P_suction / P_suc-{{ab}} — suction pressure (PSIG)\n"
        "  (cassette: P_suc-{{ab}} per unit)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows):\n"
        "  CRITICAL  if  P_suction < {si3_min_psig} PSIG\n"
        "           (below vacuum — absolute zero pressure is -14.696 PSIG; physically impossible)\n"
        "  OK        otherwise"
    )
    THRESHOLD_LABELS = {
        'si3_min_psig':      'Sub-atmospheric CRITICAL threshold (PSIG) — below this is impossible',
        'trend_window_rows': 'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {'si3_min_psig': -14.0, 'trend_window_rows': 20}
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'and', 'conditions': [
            {'column': 'P_suction', 'function': 'mean', 'operator': '<', 'value': -14.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            ps = _mean(df, _suc_col(ctx, label), win)
            if ps is None:
                continue
            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl = f'{self.LABEL}{" — " + suffix if suffix else ""}'
            if ps < self.t(thresholds, 'si3_min_psig'):
                findings.append(Finding(
                    scenario_id=self.SCENARIO_ID, label=lbl, component=self.COMPONENT,
                    severity='CRITICAL',
                    summary=f'Suction pressure = {ps:.1f} PSIG — below atmospheric vacuum. Sensor error.',
                    evidence=f'  P_suction (avg last {win}): {ps:.1f} PSIG',
                    recommendation=('POSSIBLE CAUSES:\n'
                                    '1. TRANSDUCER DISCONNECTED: Check wiring — a disconnected transducer '
                                    'often reads near zero or negative. Verify power supply to sensor.\n'
                                    '2. ZERO OFFSET DRIFT: Pressure transducer may need re-zeroing. Compare '
                                    'reading to a known-good gauge at same port.\n'
                                    '3. DAMAGED DIAPHRAGM: Internal transducer diaphragm may be punctured — '
                                    'replace transducer if recalibration does not help.\n'
                                    '4. WRONG SENSOR RANGE: Verify transducer range matches system pressures '
                                    '(e.g., 0–200 PSIG, not 0–500 PSIG).\n'
                                    '5. DAQ CHANNEL CONFIGURATION: Verify the data acquisition channel is set '
                                    'to the correct excitation voltage and scaling for this transducer model.'),
                ))
            else:
                findings.append(self._ok(suffix))
            if ctx.system_type == 'shared':
                break
        return findings


class SI4_TemperatureOrderViolation(DiagnosticScenario):
    """
    SI-4 · Temperature Order Violation (Point)
    ============================================
    APPROACH:
      Cross-checks expected temperature ordering in the refrigerant circuit:
        - T_3a (comp outlet) must be > T_2b (comp inlet)  — compression adds heat
        - T_3b (cond inlet) ≈ T_3a (same refrigerant line)
        - T_4a (cond outlet) must be < T_3b (cond inlet)  — condenser rejects heat
        - T_waterout must be > T_waterin                   — water absorbs heat
      Violations suggest sensor swap, wrong port connection, or data mapping error.

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'SI-4'
    COMPONENT   = 'Sensors / Calculations'
    LABEL       = 'Temperature Order Violation'
    DESCRIPTION = (
        "The refrigerant circuit has a defined temperature order: liquid entering the TXV "
        "must be cooler than the condensing temperature, and vapour leaving the compressor "
        "must be hotter than the condensing temperature. "
        "A temperature order violation — such as T_3b (condenser inlet gas) being cooler than "
        "T_4a (condenser outlet liquid) — is thermodynamically impossible and indicates sensor "
        "swap, wrong port assignment, or a sensor that has drifted significantly."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • T_2b — compressor inlet temperature (°F)\n"
        "  • T_3a — compressor outlet / discharge temperature (°F)\n"
        "  • T_3b — condenser inlet temperature (°F)\n"
        "  • T_4a — condenser outlet liquid temperature (°F)\n"
        "  • T_waterin, T_waterout — entering/leaving water temperatures (°F)\n"
        "  (cassette: all with -{{ab}} suffix per unit)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows, per unit):\n"
        "  Margin = {si4_margin_f}°F  (tolerance for sensor noise)\n"
        "  Checks:\n"
        "    T_3a < T_2b - margin  → compression not adding heat (impossible)\n"
        "    T_4a > T_3b + margin  → condenser outlet hotter than inlet (impossible)\n"
        "    T_waterout < T_waterin - margin → water cooling instead of heating (impossible)\n"
        "\n"
        "  CRITICAL  if  any of the above violations detected\n"
        "  OK        otherwise"
    )
    THRESHOLD_LABELS = {
        'si4_margin_f':      'Tolerance margin for sensor noise before flagging violation (°F)',
        'trend_window_rows': 'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {'si4_margin_f': 2.0, 'trend_window_rows': 20}
    DEFAULT_EXPRESSIONS = {
        'CRITICAL': {'join': 'or', 'conditions': [
            {'column': 'T_3a',       'column2': 'T_2b',      'function': 'diff_mean', 'operator': '<', 'value': -2.0},
            {'column': 'T_4a',       'column2': 'T_3b',      'function': 'diff_mean', 'operator': '>',  'value': 2.0},
            {'column': 'T_waterout', 'column2': 'T_waterin', 'function': 'diff_mean', 'operator': '<', 'value': -2.0},
        ]},
    }

    def run(self, df, ctx, thresholds):
        findings = []
        win  = self.t(thresholds, 'trend_window_rows')
        marg = self.t(thresholds, 'si4_margin_f')
        for label in ctx.module_labels:
            issues = []
            t2b = _mean(df, _t2b_col(ctx, label), win)
            t3a = _mean(df, _t3a_col(ctx, label), win)
            t3b = _mean(df, _t3b_col(ctx, label), win)
            t4a = _mean(df, _t4a_col(ctx, label), win)
            twi = _mean(df, _waterin_col(ctx, label), win)
            two = _mean(df, _waterout_col(ctx, label), win)

            if t2b is not None and t3a is not None and t3a < t2b - marg:
                issues.append(f'  T_3a ({t3a:.1f}°F) < T_2b ({t2b:.1f}°F) — comp outlet cooler than inlet (impossible)')
            if t3b is not None and t4a is not None and t4a > t3b + marg:
                issues.append(f'  T_4a ({t4a:.1f}°F) > T_3b ({t3b:.1f}°F) — cond outlet hotter than inlet (impossible)')
            if twi is not None and two is not None and two < twi - marg:
                issues.append(f'  T_waterout ({two:.1f}°F) < T_waterin ({twi:.1f}°F) — water cooling instead of heating')

            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl = f'{self.LABEL}{" — " + suffix if suffix else ""}'
            if issues:
                findings.append(Finding(
                    scenario_id=self.SCENARIO_ID, label=lbl, component=self.COMPONENT,
                    severity='CRITICAL',
                    summary=f'{len(issues)} temperature order violation(s) detected — likely sensor wiring error.',
                    evidence='\n'.join(issues),
                    recommendation=('POSSIBLE CAUSES:\n'
                                    '1. SWAPPED SENSOR WIRING: Most common cause — check that each thermocouple '
                                    'is connected to the correct data acquisition channel. Refer to Diagram tab.\n'
                                    '2. DAMAGED / CUT WIRE: A broken thermocouple wire may read ambient temperature '
                                    'instead of pipe temperature. Inspect for damaged leads.\n'
                                    '3. LOOSE TERMINAL: Intermittent connection at the terminal block can cause '
                                    'erratic or wrong readings. Tighten all connections.\n'
                                    '4. WRONG TC TYPE: Verify all thermocouples are the same type (T, J, K) and '
                                    'the DAQ is configured for that type. Mismatched types produce offset errors.\n'
                                    '5. SENSOR NOT ON PIPE: Sensor may have come loose and is reading ambient air '
                                    'instead of refrigerant/water temperature. Re-clamp and insulate.\n'
                                    '6. WATER FLOW REVERSED: If T_waterout < T_waterin, check that water piping '
                                    'is not installed backwards through the condenser.'),
                ))
            else:
                findings.append(self._ok(suffix))
            if ctx.system_type == 'shared':
                break
        return findings


class SI5_PressureSaturationConflict(DiagnosticScenario):
    """
    SI-5 · Pressure–Saturation Temperature Conflict (Point)
    =========================================================
    APPROACH:
      T_sat.comp.in is derived from P_suction via refrigerant property tables.
      It should equal approximately T_2b − S.H_total.
      A large discrepancy (> threshold) suggests the pressure sensor is reading
      incorrectly, or the suction temperature sensor is misplaced.

    COLUMNS (shared):   T_sat.comp.in, T_2b, S.H_total
    COLUMNS (cassette): T_sat.comp.in-{ab}, T_2b-{ab}, S.H_total-{ab}

    THRESHOLDS:
      si5_conflict_warning_f:  5.0
      si5_conflict_critical_f: 15.0
      trend_window_rows:        10

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    SCENARIO_ID = 'SI-5'
    COMPONENT   = 'Sensors / Calculations'
    LABEL       = 'Pressure–Saturation Conflict'
    DESCRIPTION = (
        "For a known refrigerant (R290), the saturation temperature at any given pressure is "
        "precisely defined by thermodynamic tables. If the measured suction pressure implies a "
        "saturation temperature that is significantly different from what is derived from the "
        "superheat calculation (T_2b − S.H_total), there is a conflict between the pressure "
        "transducer and the temperature sensors. This indicates sensor calibration drift, a "
        "wrong sensor assignment, or measurement of a different part of the circuit."
    )
    LOGIC = (
        "INPUTS:\n"
        "  • T_sat.comp.in — saturation temperature derived from P_suction via CoolProp (°F)\n"
        "  • T_2b — compressor inlet temperature (°F)\n"
        "  • S.H_total — superheat at compressor inlet (°F)\n"
        "  (cassette: T_sat.comp.in-{{ab}}, T_2b-{{ab}}, S.H_total-{{ab}} per unit)\n"
        "\n"
        "DECISION (mean over last {trend_window_rows} rows, per unit):\n"
        "  Expected T_sat = T_2b - S.H_total\n"
        "  Conflict = |T_sat.comp.in - (T_2b - S.H_total)|\n"
        "\n"
        "  CRITICAL  if  Conflict > {si5_conflict_critical_f}°F  (sensor error likely)\n"
        "  WARNING   if  Conflict > {si5_conflict_warning_f}°F   (monitor sensor readings)\n"
        "  OK        otherwise"
    )
    THRESHOLD_LABELS = {
        'si5_conflict_warning_f':  'P-sat conflict WARNING threshold (°F)',
        'si5_conflict_critical_f': 'P-sat conflict CRITICAL threshold (°F)',
        'trend_window_rows':       'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'si5_conflict_warning_f':  5.0,
        'si5_conflict_critical_f': 15.0,
        'trend_window_rows':        20,
    }
    DEFAULT_EXPRESSIONS = {}   # Python-only: 3-column arithmetic requires run() method

    def run(self, df, ctx, thresholds):
        findings = []
        win = self.t(thresholds, 'trend_window_rows')
        for label in ctx.module_labels:
            t_sat = _mean(df, _t_sat_comp_col(ctx, label), win)
            t2b   = _mean(df, _t2b_col(ctx, label), win)
            sh    = _mean(df, _sh_total_col(ctx, label), win)
            if t_sat is None or t2b is None or sh is None:
                continue
            expected_tsat = t2b - sh
            conflict = abs(t_sat - expected_tsat)
            suffix = f'Unit {_AB(label)}' if ctx.system_type == 'cassette' else ''
            lbl = f'{self.LABEL}{" — " + suffix if suffix else ""}'
            lines = [
                f'  T_sat.comp.in (from P_suction): {t_sat:.1f} °F',
                f'  T_2b − S.H_total (expected):    {expected_tsat:.1f} °F',
                f'  Discrepancy: {conflict:.1f} °F',
            ]

            if conflict > self.t(thresholds, 'si5_conflict_critical_f'):
                sev = 'CRITICAL'
                summ = f'Pressure–saturation conflict = {conflict:.1f}°F — sensor error likely.'
                rec = ('POSSIBLE CAUSES:\n'
                       '1. PRESSURE TRANSDUCER DRIFT: Suction pressure sensor may have drifted — '
                       'compare to a known-good gauge. Recalibrate or replace.\n'
                       '2. T_2b SENSOR MISPLACED: Verify T_2b is at compressor inlet, not further '
                       'up the suction line. Distance from compressor changes reading.\n'
                       '3. WRONG REFRIGERANT IN SOFTWARE: If the software uses R290 tables but a '
                       'different refrigerant is charged, T_sat from pressure will be wrong.\n'
                       '4. PRESSURE UNITS MISMATCH: Verify sensor outputs in PSIG. A sensor configured '
                       'for Bar or kPa with PSIG scaling will give large errors.\n'
                       '5. THERMOCOUPLE COLD JUNCTION ERROR: RTD/TC cold junction compensation error '
                       'can offset all temperature readings by a fixed amount.\n'
                       '6. PORT MAPPING ERROR: Check the Diagram tab — sensor may be assigned to the '
                       'wrong physical location.')
            elif conflict > self.t(thresholds, 'si5_conflict_warning_f'):
                sev = 'WARNING'
                summ = f'Pressure–saturation conflict = {conflict:.1f}°F — monitor sensor readings.'
                rec = ('Monitor — may indicate early sensor drift.\n'
                       'Verify suction pressure sensor accuracy with a reference gauge.\n'
                       'Confirm T_2b sensor is clamped directly at compressor inlet.\n'
                       'Check that the correct refrigerant type is selected in the software.')
            else:
                findings.append(self._ok(suffix))
                if ctx.system_type == 'shared': break
                continue

            findings.append(Finding(
                scenario_id=self.SCENARIO_ID, label=lbl, component=self.COMPONENT,
                severity=sev, summary=summ, evidence='\n'.join(lines), recommendation=rec,
            ))
            if ctx.system_type == 'shared':
                break
        return findings


# ─── CUSTOM SCENARIOS ─────────────────────────────────────────────────────────

class CustomScenario(DiagnosticScenario):
    """
    Custom Scenario — Expression-Based (loaded from custom_diagnostics.json)
    =========================================================================
    APPROACH:
      Each custom scenario defines one or more boolean expressions (one per severity
      level: CRITICAL, WARNING, WATCH). Expressions are evaluated against the mean
      value of each DataFrame column over the last trend_window_rows rows.
      Column names are sanitized to valid Python identifiers (dots/spaces/hyphens → _).
      First expression that evaluates True determines the fired severity.

    EXPRESSION EXAMPLES:
      'S_H_lh_coil < 0.5 * S_H_rh_coil'          (ratio check)
      'P_suction < 50 and S_C < 2'                 (compound condition)
      '(T_waterin + T_waterout) / 2 > 85'          (average of two sensors)
      'abs(S_H_lh_coil - S_H_rh_coil) > 15'       (absolute difference)

    JSON FORMAT:
      {
        "id": "CUSTOM-1",
        "label": "My Check",
        "component": "Custom",
        "description": "What this checks.",
        "window_rows": 20,
        "levels": [
          {"severity": "CRITICAL", "expression": "...", "summary": "..."},
          {"severity": "WARNING",  "expression": "...", "summary": "..."}
        ],
        "recommendation": "Step 1: ...\nStep 2: ..."
      }

    UPDATE LOG:
      - 2026-03-05: Initial implementation.
    """
    COMPONENT   = 'Custom'

    def __init__(self, cfg: dict):
        self.SCENARIO_ID        = cfg.get('id', 'CUSTOM-?')
        self.LABEL              = cfg.get('label', 'Custom Check')
        self.COMPONENT          = cfg.get('component', 'Custom')
        self.DESCRIPTION        = cfg.get('description', '')
        self.ENABLED            = cfg.get('enabled', True)
        self._cfg               = cfg
        self.DEFAULT_THRESHOLDS = {
            'trend_window_rows': cfg.get('window_rows', 20),
        }

    def run(self, df, ctx: DiagnosticContext, thresholds: dict) -> list[Finding]:
        win = int(self.t(thresholds, 'trend_window_rows'))
        dfw = df.tail(win)

        # Build variable namespace: sanitized_col_name → mean value over window
        ns: dict = {}
        for col in dfw.columns:
            try:
                val = float(dfw[col].mean())
                if not (val != val):  # skip NaN
                    ns[_sanitize_colname(col)] = val
            except (TypeError, ValueError):
                pass  # skip non-numeric columns

        # Add safe math helpers
        ns.update({
            'abs': abs, 'min': min, 'max': max,
            'round': round, 'sqrt': math.sqrt, 'log': math.log,
        })

        safe_builtins: dict = {"__builtins__": {}}

        for level in self._cfg.get('levels', []):
            expr = level.get('expression', '').strip()
            sev  = level.get('severity', 'WARNING')
            if not expr:
                continue
            try:
                result = eval(expr, safe_builtins, ns)  # noqa: S307
            except Exception as exc:
                logging.warning(
                    'CustomScenario %s: expression eval failed: %s — %s',
                    self.SCENARIO_ID, expr, exc,
                )
                continue

            if result:
                # Build evidence showing which variables were used
                # Try to extract variable names from the expression
                used_vars = []
                for var, val in sorted(ns.items()):
                    if var in expr and var not in ('abs', 'min', 'max', 'round', 'sqrt', 'log'):
                        used_vars.append(f'  {var} = {val:.3f}')

                evidence_lines = [
                    f'Why: Expression "{expr}" evaluated True.',
                    f'Window: last {win} rows',
                ]
                if used_vars:
                    evidence_lines.append('Values used:')
                    evidence_lines.extend(used_vars[:10])  # limit to 10 vars

                return [Finding(
                    scenario_id=self.SCENARIO_ID,
                    label=self.LABEL,
                    component=self.COMPONENT,
                    severity=sev,
                    summary=level.get('summary', f'{self.LABEL} condition met.'),
                    evidence='\n'.join(evidence_lines),
                    recommendation=self._cfg.get('recommendation', ''),
                )]

        # No level fired → OK
        return [Finding(
            scenario_id=self.SCENARIO_ID,
            label=self.LABEL,
            component=self.COMPONENT,
            severity='OK',
            summary=f'No condition matched over last {win} rows.',
            evidence=f'  Window: {win} rows  |  {len(self._cfg.get("levels", []))} levels checked.',
            recommendation='',
        )]


# ─── PV-1: PREDICTED VS ACTUAL ────────────────────────────────────────────────

class SQ1_SensorQuality(DiagnosticScenario):
    """
    SQ-1 · Sensor Data Quality Pre-Flight
    ======================================
    APPROACH:
      Every calculation and every other scenario assumes the mapped sensors
      are alive.  A stuck (flatlined), dropped-out, or spiking sensor silently
      corrupts every downstream number, and physics-based checks (SI-1..SI-5)
      only catch values that become physically impossible — a sensor frozen
      at a PLAUSIBLE value sails through everything.

      Per mapped sensor column (over the analysis window):
        • DROPOUT — more than {sq1_nan_pct}% of rows are NaN/missing
        • STUCK   — zero variance across ≥20 valid rows (flatlined; real
                    sensors always show noise)
        • SPIKES  — values beyond {sq1_spike_z}σ from the column mean

    COLUMNS: all echoed raw sensor columns (pressures, temps, water, gpm),
             per-module/per-unit aware.

    UPDATE LOG:
      - 2026-06-10: Initial implementation (sensor pre-flight).
    """
    SCENARIO_ID = 'SQ-1'
    COMPONENT   = 'Sensors'
    LABEL       = 'Sensor Data Quality'
    DESCRIPTION = (
        "Pre-flight check on the mapped sensors themselves: a sensor stuck at a plausible value, "
        "dropping out, or spiking corrupts every calculated column and can fool every other "
        "diagnostic. Physics checks only catch impossible values — this catches dead-but-plausible "
        "sensors by their statistics: real sensors always show noise; flatlines, gaps and spikes "
        "are instrumentation problems, not refrigeration problems."
    )
    LOGIC = (
        "INPUTS: every mapped sensor column echoed into the results "
        "(P_suction, P_disch, T_2b, T_3a, T_3b, T_4a, water temps, coil temps, gpm)\n"
        "\n"
        "PER COLUMN (last {trend_window_rows} rows):\n"
        "  DROPOUT  if  > {sq1_nan_pct} % of rows are missing\n"
        "  STUCK    if  zero variance across ≥ 20 valid rows\n"
        "  SPIKES   if  any value beyond {sq1_spike_z} σ from the mean\n"
        "\n"
        "  WARNING  if any DROPOUT or STUCK sensor found\n"
        "  WATCH    if only spikes found\n"
        "  OK       otherwise"
    )
    THRESHOLD_LABELS = {
        'sq1_nan_pct':  'Missing-data threshold (%)',
        'sq1_spike_z':  'Spike threshold (σ from mean)',
        'trend_window_rows': 'Analysis window (rows)',
    }
    DEFAULT_THRESHOLDS = {
        'sq1_nan_pct':  30.0,
        'sq1_spike_z':  6.0,
        'trend_window_rows': 120,
    }
    # Needs per-column statistics over many columns — Python-only.
    DEFAULT_EXPRESSIONS = {}

    def _columns_to_check(self, df, ctx):
        """Raw-value columns worth checking, for shared or cassette layouts."""
        base_shared = ['P_suction', 'P_disch', 'T_2b', 'T_3a', 'T_3b', 'T_4a',
                       'T_waterin', 'T_waterout', 'gpm']
        cols = []
        if ctx.system_type == 'cassette':
            for label in ctx.module_labels:
                ab = _ab(label)
                cols += [f'P_suc-{ab}', f'P_disch-{ab}', f'T_2b-{ab}',
                         f'T_3a-{ab}', f'T_3b-{ab}', f'T_4a-{ab}',
                         f'T_waterin-{ab}', f'T_waterout-{ab}', f'gpm-{ab}']
        else:
            cols += base_shared
        for label in ctx.module_labels:
            ab = _ab(label)
            cols += [f'T_1b-{ab}', f'T_4b-{ab}', _t2a_col(label)]
        return [c for c in cols if c in df.columns]

    def run(self, df, ctx, thresholds):
        win = int(self.t(thresholds, 'trend_window_rows') or 120)
        w = _window(df, win)
        nan_pct_max = float(self.t(thresholds, 'sq1_nan_pct'))
        spike_z     = float(self.t(thresholds, 'sq1_spike_z'))

        dropouts, stuck, spiky = [], [], []
        for col in self._columns_to_check(df, ctx):
            s = w[col]
            n = len(s)
            if n == 0:
                continue
            nan_pct = float(s.isna().mean() * 100.0)
            if nan_pct > nan_pct_max:
                dropouts.append(f'{col}: {nan_pct:.0f}% missing')
                continue
            v = s.dropna()
            if len(v) >= 20 and float(v.std()) == 0.0:
                stuck.append(f'{col}: flatlined at {v.iloc[0]:.2f} for {len(v)} rows')
                continue
            if len(v) >= 20:
                sd = float(v.std())
                if sd > 0:
                    z_max = float(((v - v.mean()).abs() / sd).max())
                    if z_max > spike_z:
                        spiky.append(f'{col}: spike at {z_max:.1f} sigma from mean')

        if dropouts or stuck:
            sev  = 'WARNING'
            summ = (f'{len(dropouts) + len(stuck)} sensor(s) unreliable — '
                    f'calculated results and other findings may be corrupted.')
        elif spiky:
            sev  = 'WATCH'
            summ = f'{len(spiky)} sensor(s) show spikes — inspect before trusting transients.'
        else:
            return [self._ok()]

        lines = ['Why: a dead-but-plausible sensor corrupts every downstream calculation '
                 'and can fool every physics-based check.']
        for tag, group in (('DROPOUT', dropouts), ('STUCK', stuck), ('SPIKES', spiky)):
            for item in group:
                lines.append(f'  • [{tag}] {item}')
        rec = ('POSSIBLE CAUSES / ACTIONS:\n'
               '1. STUCK SENSOR: Failed thermocouple/RTD or DAQ channel holding last value. '
               'Verify at the DAQ; real sensors always show noise.\n'
               '2. DROPOUT: Loose wiring, DAQ channel fault, or the CSV column is sparse — '
               'check the raw export.\n'
               '3. SPIKES: Electrical noise (compressor contactor EMI), loose connection, or '
               'sensor failing intermittently.\n'
               '4. FIX BEFORE DIAGNOSING: re-run calculations after repairing/excluding the '
               'sensor — other findings from this run are suspect.')
        return [Finding(
            scenario_id=self.SCENARIO_ID, label=self.LABEL, component=self.COMPONENT,
            severity=sev, summary=summ, evidence='\n'.join(lines), recommendation=rec,
        )]


class PV1_PredictedVsActual(DiagnosticScenario):
    """
    Compares the steady-state cycle solver prediction against actual sensor data.

    The cycle solver (cycle_solver.py) predicts the operating point the system
    SHOULD be at given its component specifications (compressor displacement,
    condenser UA, evaporator UA, TXV Cv).  By comparing predicted vs actual,
    we can identify which component is deviating from spec and infer root cause
    from the pattern of deviations.

    This scenario requires:
      - cycle_prediction in the diagnostics context (set by run_all_diagnostics)
      - Component specs set on diagram components (UA, Cv, isentropic_eff)
    """
    SCENARIO_ID = 'PV-1'
    COMPONENT   = 'System'
    LABEL       = 'Predicted vs Actual Operating Point'
    ENABLED     = True
    DESCRIPTION = (
        'Compares the steady-state cycle solver prediction against actual sensor '
        'readings.  Deviations pinpoint root causes with higher precision than '
        'threshold rules — the pattern of which parameters deviate identifies '
        'whether the fault is undercharge, condenser fouling, evaporator icing, '
        'TXV mismatch, or compressor degradation.'
    )
    LOGIC = (
        'Runs the 2-unknown steady-state solver (T_evap, T_cond) using component '
        'specs from the diagram model.  Compares predicted vs actual for: '
        'P_suction, P_disch, SH, SC, T_disch, Q_evap.  Pattern-matches deviations '
        'to root cause signatures.'
    )
    APPLIES_TO = ['cassette', 'modular', 'non-modular']
    DEFAULT_EXPRESSIONS = {}   # Python-only scenario

    DEFAULT_THRESHOLDS = {
        'P_suction_tol_psi':  5.0,
        'P_disch_tol_psi':    8.0,
        'SH_tol_F':           5.0,
        'SC_tol_F':           3.0,
        'T_disch_tol_F':      15.0,
        'capacity_tol_pct':   15.0,
    }
    THRESHOLD_LABELS = {
        'P_suction_tol_psi':  'Suction pressure tolerance (PSIG)',
        'P_disch_tol_psi':    'Discharge pressure tolerance (PSIG)',
        'SH_tol_F':           'Superheat tolerance (°F)',
        'SC_tol_F':           'Subcooling tolerance (°F)',
        'T_disch_tol_F':      'Discharge temp tolerance (°F)',
        'capacity_tol_pct':   'Capacity tolerance (%)',
    }

    def run(self, df, ctx: DiagnosticContext, thresholds: dict) -> list[Finding]:
        # ── 1. Get cycle prediction from context ──────────────────────────────
        prediction = getattr(ctx, 'cycle_prediction', None)

        # If not in context, try to run the solver inline
        if prediction is None:
            diagram_model = getattr(ctx, 'diagram_model', None)
            if diagram_model is None:
                return [Finding(
                    scenario_id=self.SCENARIO_ID, label=self.LABEL,
                    component=self.COMPONENT, severity='INFO',
                    summary='Cycle solver not configured — set component specs in diagram.',
                    evidence=(
                        'The cycle solver requires component specifications:\n'
                        '  • Compressor: displacement_cm3, speed_rpm, isentropic_eff\n'
                        '  • Condenser:  ua_condenser (W/K)\n'
                        '  • Evaporator: ua_evaporator (W/K)\n'
                        '  • TXV:        cv_txv, superheat_setting\n\n'
                        'Edit each component\'s properties in the Diagram tab to enable PV-1.'
                    ),
                    recommendation=(
                        'To activate PV-1: open the Diagram tab, double-click each '
                        'component, and enter its sizing specs. Default values are '
                        'pre-filled — adjust to match your actual equipment.'
                    ),
                )]
            try:
                from cycle_solver import (
                    extract_specs_from_model, extract_conditions_from_df, solve_cycle
                )
                specs      = extract_specs_from_model(diagram_model)
                conditions = extract_conditions_from_df(
                    df, getattr(ctx, 'rated_inputs', {}))
                prediction = solve_cycle(specs, conditions)
            except Exception as exc:
                return [Finding(
                    scenario_id=self.SCENARIO_ID, label=self.LABEL,
                    component=self.COMPONENT, severity='INFO',
                    summary='Cycle solver error — see evidence for details.',
                    evidence=f'Solver error: {exc}',
                    recommendation='Check that CoolProp and scipy are installed.',
                )]

        # ── 2. Solver failed to converge ──────────────────────────────────────
        if not prediction.converged:
            return [Finding(
                scenario_id=self.SCENARIO_ID, label=self.LABEL,
                component=self.COMPONENT, severity='INFO',
                summary=f'Cycle solver did not converge: {prediction.error_msg}',
                evidence=(
                    f'Solver error: {prediction.error_msg}\n\n'
                    'This may indicate:\n'
                    '  • Component specs are far from realistic (check UA values)\n'
                    '  • External conditions are extreme\n'
                    '  • Refrigerant not supported'
                ),
                recommendation=(
                    'Check component specifications in the Diagram tab. '
                    'Typical values: UA_condenser=800 W/K, UA_evaporator=600 W/K, '
                    'Cv_TXV=0.5, isentropic_eff=0.72.'
                ),
            )]

        # ── 3. Build actual values from most recent data ──────────────────────
        recent = df.tail(10)

        def _act(col: str):
            if col in recent.columns:
                v = recent[col].dropna()
                return float(v.mean()) if len(v) > 0 else None
            return None

        actual = {
            'P_suction': _act('P_suction'),
            'P_disch':   _act('P_disch'),
            'S.H_total': _act('S.H_total'),
            'S.C':       _act('S.C'),
            'T_3a':      _act('T_3a'),
            'qc':        _act('qc'),
        }

        # Check that we have at least some actual data
        available = [k for k, v in actual.items() if v is not None]
        if len(available) < 2:
            return [Finding(
                scenario_id=self.SCENARIO_ID, label=self.LABEL,
                component=self.COMPONENT, severity='INFO',
                summary='Insufficient sensor data for comparison (need ≥2 calculated columns).',
                evidence=(
                    'Available columns: ' + ', '.join(available) + '\n'
                    'Needed: P_suction, P_disch, S.H_total, S.C, T_3a, qc\n\n'
                    'Ensure sensors are mapped and calculations have run.'
                ),
                recommendation='Map required sensors in the Diagram tab and run calculations.',
            )]

        # ── 4. Compute deviations ─────────────────────────────────────────────
        try:
            from cycle_solver import compute_deviations, infer_root_cause
        except ImportError:
            return []

        deviations = compute_deviations(prediction, actual, thresholds)
        if not deviations:
            return []

        # ── 5. Build evidence table ───────────────────────────────────────────
        ev_lines = [
            'PREDICTED vs ACTUAL (cycle solver comparison):',
            f'  Solver: T_evap={prediction.T_evap_F:.1f}°F  T_cond={prediction.T_cond_F:.1f}°F  '
            f'PR={prediction.PR:.2f}  η_vol={prediction.eta_vol:.3f}',
            '',
            f"  {'Parameter':<18} {'Predicted':>12} {'Actual':>12} {'Δ':>10}  Flag",
            '  ' + '─' * 60,
        ]
        for d in deviations:
            pred_str = f'{d.predicted:,.1f} {d.unit}'
            act_str  = f'{d.actual:,.1f} {d.unit}'
            dlt_str  = (f'+{d.delta:.1f}' if d.delta >= 0 else f'{d.delta:.1f}')
            ev_lines.append(
                f'  {d.name:<18} {pred_str:>12} {act_str:>12} {dlt_str:>10}  {d.flag}'
            )

        ev_lines.extend([
            '',
            f'  Predicted Q_evap : {prediction.Q_evap_btu_hr/1000:.2f} kBTU/hr  '
            f'({prediction.Q_evap_btu_hr/12000:.2f} tons)',
            f'  Predicted COP    : {prediction.COP:.2f}',
            f'  Predicted T_disch: {prediction.T_disch_F:.1f}°F',
            f'  Predicted SC     : {prediction.SC_F:.1f}°F',
            f'  Predicted T_water_out: {prediction.T_water_out_F:.1f}°F',
        ])

        # ── 6. Pattern-match to root cause ────────────────────────────────────
        cause_label, recommendation = infer_root_cause(deviations)

        # ── 7. Determine overall severity ─────────────────────────────────────
        _sev_rank = {'OK': 0, 'WATCH': 1, 'WARNING': 2, 'CRITICAL': 3}
        max_sev = max(deviations, key=lambda d: _sev_rank.get(d.severity, 0)).severity

        if max_sev == 'OK':
            return [Finding(
                scenario_id=self.SCENARIO_ID, label=self.LABEL,
                component=self.COMPONENT, severity='OK',
                summary='System matches predicted baseline — operating as designed.',
                evidence='\n'.join(ev_lines),
                recommendation='All parameters within tolerance of cycle solver prediction.',
            )]

        # Count high-severity deviations to determine overall severity
        n_critical = sum(1 for d in deviations if d.severity == 'CRITICAL')
        n_warning  = sum(1 for d in deviations if d.severity in ('WARNING', 'CRITICAL'))

        if n_critical >= 2 or (n_critical >= 1 and n_warning >= 3):
            overall_sev = 'CRITICAL'
        elif n_warning >= 2 or n_critical >= 1:
            overall_sev = 'WARNING'
        else:
            overall_sev = 'WATCH'

        summary = f'Root cause: {cause_label}'

        return [Finding(
            scenario_id=self.SCENARIO_ID, label=self.LABEL,
            component=self.COMPONENT,
            severity=overall_sev,
            summary=summary,
            evidence='\n'.join(ev_lines),
            recommendation=recommendation,
        )]


# ─── SCENARIO REGISTRY ────────────────────────────────────────────────────────
# One entry per scenario class.  ORDER = display order within each severity tier.
# To add a new scenario: append YourNewScenario() to this list.
# ─────────────────────────────────────────────────────────────────────────────

SCENARIO_REGISTRY: list[DiagnosticScenario] = [
    # ── Refrigerant ───────────────────────────────────────────────────────────
    RF1_RefrigerantLeakTrend(),
    RF2_Undercharge(),
    RF3_Overcharge(),
    RF4_NonCondensables(),

    # ── Compressor ────────────────────────────────────────────────────────────
    CP1_LiquidSluggingRisk(),
    CP2_CompressorOverheating(),
    CP3_NotCompressing(),
    CP4_PressureRatioExtreme(),
    CP5_DischargeTempTrend(),
    CP6_HighCompressionRatio(),       # NEW
    CP7_MassFlowCrossCheck(),         # NEW — water-side vs displacement m_dot

    # ── Condenser ─────────────────────────────────────────────────────────────
    CD1_CondenserBlockage(),
    CD2_WaterFlowIssue(),
    CD3_WaterFlowInstability(),       # NEW — averaging-masking detector

    # ── Evaporator / Coils ────────────────────────────────────────────────────
    EV1_CoilRestrictionOrIcing(),
    EV2_ModuleImbalance(),
    EV3_CoilIcingTrend(),             # NEW

    # ── TXV ───────────────────────────────────────────────────────────────────
    TX1_TXVStarvedOrBlocked(),
    TX2_TXVFlooding(),
    TX3_TXVHunting(),

    # ── Distributor & Filter Dryer ────────────────────────────────────────────
    DI1_DistributorImbalance(),
    DI2_FilterDryerBlockage(),
    DI3_EvaporatorDistributorRestriction(),   # NEW

    # ── Suction Line ──────────────────────────────────────────────────────────
    SL1_SuctionLineRestriction(),     # NEW

    # ── Hot Gas Defrost ───────────────────────────────────────────────────────
    HG1_DefrostIneffective(),
    HG2_DefrostBackwards(),

    # ── Sensor / Thermodynamic Impossibilities ────────────────────────────────
    SI1_NegativeSubcooling(),
    SI2_EnthalpyReversal(),
    SI3_SubAtmosphericPressure(),
    SI4_TemperatureOrderViolation(),
    SI5_PressureSaturationConflict(),
    SQ1_SensorQuality(),              # NEW — stuck/dropout/spike pre-flight

    # ── Predicted vs Actual (Cycle Solver) ────────────────────────────────────
    PV1_PredictedVsActual(),
]


# ─── SCENARIO LOOKUP ──────────────────────────────────────────────────────────
# Maps scenario_id → scenario instance for widget use (e.g. reading DESCRIPTION).
_SCENARIO_BY_ID: dict[str, 'DiagnosticScenario'] = {
    s.SCENARIO_ID: s for s in SCENARIO_REGISTRY
}

# ─── CUSTOM SCENARIO PERSISTENCE ──────────────────────────────────────────────

def load_custom_scenarios(path: str = None) -> list[CustomScenario]:
    """Load custom_diagnostics.json and return a list of CustomScenario instances.

    Returns an empty list if the file does not exist or cannot be parsed.
    """
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'custom_diagnostics.json')
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        scenarios = [CustomScenario(cfg) for cfg in data.get('scenarios', [])]
        logging.info('Loaded %d custom diagnostic scenario(s) from %s', len(scenarios), path)
        return scenarios
    except Exception as exc:
        logging.warning('load_custom_scenarios: failed to load %s — %s', path, exc)
        return []


def save_custom_scenarios(scenarios_cfg: list[dict], path: str = None) -> bool:
    """Save a list of scenario config dicts to custom_diagnostics.json.

    Returns True on success, False on failure.
    """
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'custom_diagnostics.json')
    try:
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'version': '1.0', 'scenarios': scenarios_cfg}, fh, indent=2)
        return True
    except Exception as exc:
        logging.warning('save_custom_scenarios: failed — %s', exc)
        return False


# ─── Rules Config (built-in scenario overrides) ──────────────────────────────

_RULES_CONFIG_PATH = Path(__file__).parent / 'rules_config.json'


def load_rules_config(path: str = None) -> dict:
    """Load per-scenario overrides from rules_config.json.

    Returns a dict with shape:
        {"version": "2.0", "rules": { "RF-1": {"enabled": True, ...}, ... },
         "scenario_overrides": { ... }}
    Auto-populates default expressions if missing or old format.
    """
    p = Path(path or _RULES_CONFIG_PATH)
    config = None
    if p.exists():
        try:
            with open(p, 'r', encoding='utf-8') as fh:
                config = json.load(fh)
        except Exception as exc:
            logging.warning('load_rules_config: %s', exc)

    # Auto-populate with defaults if missing or old format
    if config is None or 'rules' not in config or not config.get('rules'):
        config = init_rules_config_defaults()
        save_rules_config(config, p)

    return config


def save_rules_config(config: dict, path: str = None) -> bool:
    """Persist rules_config to disk."""
    p = Path(path or _RULES_CONFIG_PATH)
    try:
        with open(p, 'w', encoding='utf-8') as fh:
            json.dump(config, fh, indent=2)
        return True
    except Exception as exc:
        logging.warning('save_rules_config: %s', exc)
        return False


def init_rules_config_defaults() -> dict:
    """Generate default rules_config from all scenario DEFAULT_EXPRESSIONS + metadata."""
    config = {'version': '2.0', 'computed_columns': {}, 'rules': {}}
    for scenario in SCENARIO_REGISTRY:
        default_expr = getattr(scenario, 'DEFAULT_EXPRESSIONS', {})
        if not default_expr:
            continue
        config['rules'][scenario.SCENARIO_ID] = {
            'enabled': scenario.ENABLED,
            'applies_to': getattr(scenario, 'APPLIES_TO', ['cassette', 'modular', 'non-modular']),
            'window_rows': scenario.DEFAULT_THRESHOLDS.get('trend_window_rows', 20),
            'expressions': default_expr,
        }
    return config


# ─── EXPRESSION-BASED RULE EVALUATION ─────────────────────────────────────────

def _make_expression_namespace(dfw: pd.DataFrame) -> dict:
    """Build eval namespace with helper functions for expression-based rule evaluation.

    Provides callable functions: mean(), slope(), std(), last(), pct_above(), pct_below()
    Also adds plain {sanitized_col: mean_value} for backward compat with custom scenarios.
    """
    # Build reverse map: sanitized_name → raw column name
    _col_map = {}
    for c in dfw.columns:
        _col_map[c] = c                        # raw → raw
        _col_map[_sanitize_colname(c)] = c      # sanitized → raw

    def _resolve(col_ref):
        """Resolve a column reference (raw or sanitized) to actual DataFrame column name."""
        if isinstance(col_ref, str):
            return _col_map.get(col_ref, col_ref)
        return str(col_ref)

    def mean(col):
        c = _resolve(col)
        if c not in dfw.columns: return float('nan')
        vals = dfw[c].dropna()
        return float(vals.mean()) if len(vals) > 0 else float('nan')

    def slope(col):
        c = _resolve(col)
        if c not in dfw.columns: return 0.0
        vals = dfw[c].dropna()
        if len(vals) < 2: return 0.0
        x = np.arange(len(vals), dtype=float)
        coeffs = np.polyfit(x, vals.values.astype(float), 1)
        return float(coeffs[0])

    def std(col):
        c = _resolve(col)
        if c not in dfw.columns: return float('nan')
        vals = dfw[c].dropna()
        return float(vals.std()) if len(vals) > 1 else 0.0

    def last(col):
        c = _resolve(col)
        if c not in dfw.columns: return float('nan')
        vals = dfw[c].dropna()
        return float(vals.iloc[-1]) if len(vals) > 0 else float('nan')

    def pct_above(col, threshold):
        c = _resolve(col)
        if c not in dfw.columns: return 0.0
        vals = dfw[c].dropna()
        if len(vals) == 0: return 0.0
        return float((vals > threshold).sum() / len(vals) * 100)

    def pct_below(col, threshold):
        c = _resolve(col)
        if c not in dfw.columns: return 0.0
        vals = dfw[c].dropna()
        if len(vals) == 0: return 0.0
        return float((vals < threshold).sum() / len(vals) * 100)

    def diff_mean(col1, col2):
        """Signed difference of means: mean(col1) - mean(col2)."""
        return mean(col1) - mean(col2)

    def abs_diff_mean(col1, col2):
        """Absolute difference of means: abs(mean(col1) - mean(col2))."""
        return abs(mean(col1) - mean(col2))

    def pressure_ratio(col1, col2):
        """PSIA pressure ratio: (mean(col1)+14.696) / max(mean(col2)+14.696, 0.1)."""
        return (mean(col1) + 14.696) / max(mean(col2) + 14.696, 0.1)

    ns = {
        'mean': mean, 'slope': slope, 'std': std, 'last': last,
        'pct_above': pct_above, 'pct_below': pct_below,
        'diff_mean': diff_mean, 'abs_diff_mean': abs_diff_mean,
        'pressure_ratio': pressure_ratio,
        'abs': abs, 'min': min, 'max': max, 'round': round,
    }

    # Backward compat: plain {sanitized_col: mean_value} for existing custom scenarios
    for col in dfw.columns:
        try:
            val = float(dfw[col].mean())
            if val == val:  # not NaN
                ns[_sanitize_colname(col)] = val
        except (TypeError, ValueError):
            pass

    return ns


def _conditions_to_expr(severity_cfg: dict) -> str:
    """Convert structured conditions -> eval-able expression string.

    Supports join modes: 'and', 'or', 'at_least' (with min_count).
    Supports single-column and two-column functions (column2 field).
    """
    join = severity_cfg.get('join', 'and')
    parts = []
    for cond in severity_cfg.get('conditions', []):
        col  = cond.get('column', '')
        col2 = cond.get('column2', '')
        func = cond.get('function', 'mean')
        op   = cond.get('operator', '>')
        val  = cond.get('value', 0)
        if col2:
            parts.append(f"{func}('{col}', '{col2}') {op} {val}")
        else:
            parts.append(f"{func}('{col}') {op} {val}")

    if not parts:
        return ''

    if join == 'at_least':
        min_count = severity_cfg.get('min_count', 1)
        wrapped = ' + '.join(f'({p})' for p in parts)
        return f'({wrapped} >= {min_count})'
    else:
        return f' {join} '.join(parts)


def _evaluate_rule(dfw: pd.DataFrame, expressions_cfg: dict,
                   namespace: dict, scenario) -> list:
    """Evaluate structured expressions for a single rule.

    Returns list of Finding objects (at most one -- the highest severity that fires).
    Tries CRITICAL -> WARNING -> WATCH in order; first True wins.
    """
    win_rows = len(dfw)

    for sev in ('CRITICAL', 'WARNING', 'WATCH'):
        sev_cfg = expressions_cfg.get(sev)
        if not sev_cfg:
            continue

        expr_str = _conditions_to_expr(sev_cfg)
        if not expr_str:
            continue

        try:
            result = eval(expr_str, {"__builtins__": {}}, namespace)  # noqa: S307
        except Exception as exc:
            logging.warning('[RULES] %s/%s eval failed: %s -- %s',
                          scenario.SCENARIO_ID, sev, expr_str, exc)
            continue

        if result:
            # Build evidence showing which columns were referenced
            evidence_lines = [
                f'Expression: {expr_str}',
                f'Window: last {win_rows} rows',
                'Values:',
            ]
            # Extract column references from conditions
            for cond in sev_cfg.get('conditions', []):
                col  = cond.get('column', '')
                col2 = cond.get('column2', '')
                func = cond.get('function', 'mean')
                try:
                    fn = namespace.get(func)
                    if fn and callable(fn):
                        if col2:
                            val = fn(col, col2)
                            evidence_lines.append(f'  {func}({col}, {col2}) = {val:.3f}')
                        else:
                            val = fn(col)
                            evidence_lines.append(f'  {func}({col}) = {val:.3f}')
                except Exception:
                    pass

            return [Finding(
                scenario_id=scenario.SCENARIO_ID,
                label=scenario.LABEL,
                component=scenario.COMPONENT,
                severity=sev,
                summary=f'{scenario.LABEL} -- {sev}',
                evidence='\n'.join(evidence_lines),
                recommendation=getattr(scenario, 'DESCRIPTION', '') or 'Review system operation.',
            )]

    # No severity fired -> OK
    return [Finding(
        scenario_id=scenario.SCENARIO_ID,
        label=scenario.LABEL,
        component=scenario.COMPONENT,
        severity='OK',
        summary=f'{scenario.LABEL} -- OK',
        evidence=f'All conditions passed (window: {win_rows} rows).',
        recommendation='',
    )]


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

def _apply_computed_columns(df, rules_config: dict):
    """Add user-defined computed columns to the dataframe before rule evaluation.

    Computed columns are defined in rules_config['computed_columns'] with:
      type:    'average' | 'max' | 'min' | 'spread' | 'difference' | 'sum'
      sources: list of source column names present in df
    """
    import pandas as _pd
    for name, cfg in (rules_config or {}).get('computed_columns', {}).items():
        sources = [c for c in cfg.get('sources', []) if c in df.columns]
        if not sources:
            continue
        ctype = cfg.get('type', 'average')
        try:
            src_df = df[sources]
            if ctype == 'average':
                df[name] = src_df.mean(axis=1)
            elif ctype == 'max':
                df[name] = src_df.max(axis=1)
            elif ctype == 'min':
                df[name] = src_df.min(axis=1)
            elif ctype == 'spread':
                df[name] = src_df.max(axis=1) - src_df.min(axis=1)
            elif ctype == 'difference' and len(sources) >= 2:
                df[name] = df[sources[0]] - df[sources[1]]
            elif ctype == 'sum':
                df[name] = src_df.sum(axis=1)
        except Exception as e:
            logging.warning('[RULES] computed column %s failed: %s', name, e)
    return df


def get_all_thresholds(user_overrides: dict = None, custom_scenarios: list = None) -> dict:
    """Merge DEFAULT_THRESHOLDS from all scenarios + custom scenarios + user overrides."""
    merged = {}
    for scenario in SCENARIO_REGISTRY:
        merged.update(scenario.DEFAULT_THRESHOLDS)
    for scenario in (custom_scenarios or []):
        merged.update(scenario.DEFAULT_THRESHOLDS)
    if user_overrides:
        merged.update(user_overrides)
    return merged


def run_all_diagnostics(df, system_type: str, module_labels: list,
                        rated_inputs: dict = None,
                        user_thresholds: dict = None,
                        custom_scenarios: list = None,
                        rules_config: dict = None,
                        diagram_model: dict = None,
                        cycle_prediction=None) -> list[Finding]:
    """
    Main entry point called by DiagnosticsWidget.

    Parameters
    ----------
    df               : processed_df from CalculationsWidget (pandas DataFrame)
    system_type      : 'shared' | 'cassette'
    module_labels    : list of module labels e.g. ['Left', 'Right']
    rated_inputs     : dict from data_manager.rated_inputs (may be None)
    user_thresholds  : dict of user-overridden threshold values (may be None)
    custom_scenarios : list of CustomScenario instances (may be None)
    rules_config     : dict of per-scenario overrides from rules_config.json (may be None)
    diagram_model    : diagram model dict (passed to PV-1 for inline solver fallback)
    cycle_prediction : CycleSolution from cycle_solver.solve_cycle() (may be None)

    Returns
    -------
    List of Finding objects, sorted by severity (CRITICAL first).
    """
    if df is None or df.empty:
        return []

    # Apply user-defined computed columns before rule evaluation
    df = _apply_computed_columns(df.copy(), rules_config)

    # Run cycle solver if not pre-computed but diagram_model is available
    if cycle_prediction is None and diagram_model is not None:
        try:
            from cycle_solver import (
                extract_specs_from_model, extract_conditions_from_df, solve_cycle
            )
            _specs = extract_specs_from_model(diagram_model)
            _cond  = extract_conditions_from_df(df, rated_inputs or {})
            cycle_prediction = solve_cycle(_specs, _cond)
            if cycle_prediction.converged:
                logging.info('[DIAGNOSTICS] Cycle solver converged: '
                             'T_evap=%.1f°F T_cond=%.1f°F COP=%.2f',
                             cycle_prediction.T_evap_F,
                             cycle_prediction.T_cond_F,
                             cycle_prediction.COP)
            else:
                logging.info('[DIAGNOSTICS] Cycle solver did not converge: %s',
                             cycle_prediction.error_msg)
        except Exception as _e:
            logging.debug('[DIAGNOSTICS] Cycle solver skipped: %s', _e)

    ctx = DiagnosticContext(
        system_type=system_type,
        module_labels=module_labels or ['Left'],
        rated_inputs=rated_inputs or {},
        cycle_prediction=cycle_prediction,
        diagram_model=diagram_model or {},
    )
    thresholds = get_all_thresholds(user_thresholds, custom_scenarios)

    # Determine config type for applies_to filtering
    if system_type == 'cassette':
        _config_type = 'cassette'
    elif len(module_labels or ['Left']) > 1:
        _config_type = 'modular'
    else:
        _config_type = 'non-modular'

    _overrides = (rules_config or {}).get('scenario_overrides', {})
    _rules     = (rules_config or {}).get('rules', {})

    registry = list(SCENARIO_REGISTRY) + list(custom_scenarios or [])
    all_findings: list[Finding] = []
    for scenario in registry:
        # Per-rule config from 'rules' key (set by Rules dialog) takes precedence
        # over the legacy 'scenario_overrides' key for enabled / applies_to / window.
        _rule_cfg = _rules.get(scenario.SCENARIO_ID, {})
        _ovr      = _overrides.get(scenario.SCENARIO_ID, {})

        # enabled: rules > scenario_overrides > scenario default
        _enabled = _rule_cfg.get('enabled', _ovr.get('enabled', scenario.ENABLED))
        if not _enabled:
            continue

        # applies_to: rules > scenario_overrides > scenario default
        _default_applies = getattr(scenario, 'APPLIES_TO', ['cassette', 'modular', 'non-modular'])
        _applies_to = _rule_cfg.get('applies_to', _ovr.get('applies_to', _default_applies))
        if _config_type not in _applies_to:
            continue

        # Per-rule window override (set by the window spinbox in the Rules dialog).
        # When present, it overrides the global trend_window_rows threshold for
        # BOTH expression-based evaluation AND Python run() methods.
        _rule_window = _rule_cfg.get('window_rows')  # None if not set

        _expressions = _rule_cfg.get('expressions', {})

        if _expressions:
            # Expression-based evaluation
            _win = int(_rule_window if _rule_window is not None else 20)
            _dfw = df.tail(_win)
            _ns = _make_expression_namespace(_dfw)
            try:
                results = _evaluate_rule(_dfw, _expressions, _ns, scenario)
                # --- Patch recommendations from run() method ---
                # _evaluate_rule() uses DESCRIPTION as recommendation fallback,
                # but each scenario's run() method has detailed, per-severity
                # "POSSIBLE CAUSES" recommendations.  Call run() for non-OK
                # findings and patch the recommendation text.
                _fired = [f for f in results
                          if f.severity not in ('OK', 'INFO')]
                if _fired:
                    try:
                        _scenario_thresh_ovr = _ovr.get('thresholds', {})
                        _eff_thresh = {**thresholds, **_scenario_thresh_ovr}
                        if _rule_window is not None:
                            _eff_thresh['trend_window_rows'] = int(_rule_window)
                        _run_results = scenario.run(df, ctx, _eff_thresh)
                        _rec_by_sev = {}
                        for _rf in _run_results:
                            if (_rf.severity not in ('OK', 'INFO')
                                    and _rf.recommendation):
                                _rec_by_sev.setdefault(
                                    _rf.severity, _rf.recommendation)
                        for _f in _fired:
                            _new_rec = _rec_by_sev.get(_f.severity)
                            if not _new_rec and _rec_by_sev:
                                # No exact severity match — use the highest
                                # available recommendation (dict is insertion-
                                # ordered; run() checks CRITICAL first).
                                _new_rec = next(iter(_rec_by_sev.values()))
                            if _new_rec:
                                _f.recommendation = _new_rec
                    except Exception:
                        pass  # keep DESCRIPTION fallback from _evaluate_rule
            except Exception as e:
                logging.warning('[RULES] Expression eval failed for %s: %s', scenario.SCENARIO_ID, e)
                results = []
        else:
            # Fallback: Python run() method
            _scenario_thresh_ovr = _ovr.get('thresholds', {})
            _effective_thresholds = {**thresholds, **_scenario_thresh_ovr}
            # Forward the per-rule window into the thresholds so scenario.run()
            # uses the user-configured window rather than the global default.
            if _rule_window is not None:
                _effective_thresholds['trend_window_rows'] = int(_rule_window)
            try:
                results = scenario.run(df, ctx, _effective_thresholds)
            except Exception as e:
                logging.warning('[DIAGNOSTICS] %s run() failed: %s', scenario.SCENARIO_ID, e)
                results = []

        all_findings.extend(results)

    # Sort: CRITICAL → WARNING → WATCH → OK → INFO
    all_findings.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 99))
    return all_findings
