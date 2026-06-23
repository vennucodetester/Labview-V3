# Diagnostics Tab — Implementation Plan (Revised)
> For review before any code is written. Last updated: 2026-03-05

---

## 1. Core Design Goal: "Living Code"

The diagnostics system is designed to be **easily extended and corrected** as you discover new failure modes in the field. The architecture enforces this through a **Scenario Registry Pattern**:

- Every diagnostic scenario is an **independent, self-contained class**
- Adding a new scenario = write one class + append one line to the registry list
- Disabling a faulty scenario = set `ENABLED = False` in the class (one line)
- Adjusting detection logic = edit only that class, nothing else changes
- Every class has a standardised docstring telling you exactly what it checks and why

You should never have to understand the full codebase to add or fix a single diagnostic check.

---

## 2. New Files

| File | Responsibility |
|------|---------------|
| `diagnostics_engine.py` | All detection logic. `Finding` dataclass, `DiagnosticScenario` base class, all scenario classes, `SCENARIO_REGISTRY`, `run_all_diagnostics()` entry point |
| `diagnostics_widget.py` | PyQt6 UI. Expandable cards, summary bar, thresholds editor dialog |

**Only `app.py` is modified** (3 lines: import + connect signal + addTab).

---

## 3. Architecture Overview

```
CalculationsWidget.filtered_data_ready  ──signal──►  DiagnosticsWidget.on_data_ready(df)
                                                              │
                                                    diagnostics_engine.run_all_diagnostics(
                                                        df, system_type, module_labels,
                                                        rated_inputs, thresholds_override
                                                    )
                                                              │
                                                    for scenario in SCENARIO_REGISTRY:
                                                        if scenario.ENABLED:
                                                            findings += scenario.run(df, ctx, thresholds)
                                                              │
                                                    List[Finding]  →  sorted by severity
                                                              │
                                                    DiagnosticsWidget renders expandable cards
```

### DiagnosticScenario Base Class

```python
class DiagnosticScenario:
    SCENARIO_ID = ''          # e.g. 'RF-1'
    COMPONENT   = ''          # e.g. 'Refrigerant', 'TXV — Left'
    LABEL       = ''          # e.g. 'Refrigerant Leak (Trend)'
    ENABLED     = True        # Set False to silence this check without deleting it
    DEFAULT_THRESHOLDS = {}   # dict of param_name → default_value, with units in key name

    def run(self, df, ctx, thresholds) -> list[Finding]:
        """Override in each subclass. ctx = DiagnosticContext (see below)."""
        raise NotImplementedError
```

### DiagnosticContext (passed to every scenario's run())

```python
@dataclass
class DiagnosticContext:
    system_type   : str        # 'shared' | 'cassette'
    module_labels : list       # e.g. ['Left', 'Right']
    rated_inputs  : dict       # from data_manager (rated_capacity_btu_hr, gpm_water, etc.)
```

### Finding (returned by every scenario)

```python
@dataclass
class Finding:
    scenario_id   : str        # e.g. 'RF-1'
    label         : str        # e.g. 'Refrigerant Leak (Trend)'
    component     : str        # e.g. 'Refrigerant'
    severity      : str        # 'CRITICAL' | 'WARNING' | 'WATCH' | 'OK' | 'INFO'
    summary       : str        # one-liner shown on the card
    evidence      : str        # multi-line: specific values, row counts, trend data
    recommendation: str        # plain-English action
    affected_rows : list       # row indices that triggered this finding (empty = all-data check)
    uses_trend    : bool       # True = looked at all rows; False = point-in-time
```

### SCENARIO_REGISTRY (in diagnostics_engine.py)

```python
# ─── ADD NEW SCENARIOS HERE ─────────────────────────────────────────────────
# One entry per scenario class. Order = order shown in UI within each severity.
SCENARIO_REGISTRY = [
    RF1_RefrigerantLeakTrend(),
    RF2_Undercharge(),
    RF3_Overcharge(),
    RF4_NonCondensables(),
    CP1_LiquidSluggingRisk(),
    # ... etc.
    # To add a new scenario: append MyNewScenario() here.
]
```

### Default Thresholds (merged dict from all scenarios)

All `DEFAULT_THRESHOLDS` dicts are merged at startup. The thresholds dialog shows them all grouped by scenario, with units visible in the parameter name. User edits are stored in memory for the session.

---

## 4. Case Type Matrix

| Case Type | System Type | Modules/Units | Thermodynamic Circuits |
|-----------|------------|---------------|----------------------|
| Non-modular, 1–5 doors | shared | 1 (Left) | 1 shared circuit |
| Modular, 2-module | shared | Left + Right | 1 shared circuit, 2 evap branches |
| Modular, 3-module | shared | Left + Center + Right | 1 shared circuit, 3 evap branches |
| Cassette, 1-unit | cassette | 1 | 1 independent circuit |
| Cassette, 2-unit | cassette | 2 | 2 independent circuits |
| Cassette, 3-unit | cassette | 3 | 3 independent circuits |

> Non-modular multi-door: all doors share one evaporator coil. Door count does not affect column naming or diagnostics — treated as 1-module shared.

---

## 5. All Diagnostic Scenarios

Each scenario class will contain a full docstring covering: approach, columns used, known false-positive conditions, update log. This is the contract you can modify.

---

### 🔴 REFRIGERANT SYSTEM

#### RF-1 · RefrigerantLeakTrend
```
APPROACH:  Linear regression (numpy polyfit) on SH_total, S.C, P_suction, qc
           over ALL rows. Leak signature = SH rising + SC falling + P_suc falling
           + qc falling simultaneously. Requires min_matching_signals of 4 to fire.
POINT vs TREND: TREND (all rows)
COLUMNS (shared):   S.H_total, S.C, P_suction, qc
COLUMNS (cassette): S.H_total-{ab}, S.C-{ab}, P_suc-{ab}, qc-{ab}  (per unit)
THRESHOLDS:
  - rf1_sh_slope_f_per_row: 0.3   (min SH slope to count as rising)
  - rf1_sc_slope_f_per_row: 0.3   (min SC slope magnitude to count as falling)
  - rf1_pres_slope_psig_per_row: 0.02
  - rf1_min_matching_signals: 3   (of 4 must match; set to 4 for stricter)
FALSE POSITIVES: Short test runs may show drift that looks like a leak. Increase
                 rf1_min_matching_signals or run longer tests to reduce false flags.
```

#### RF-2 · Undercharge
```
APPROACH:  Point check on latest N rows. SH very high AND SC very low AND
           P_suction below typical range.
POINT vs TREND: POINT (last trend_window_rows)
COLUMNS (shared):   S.H_total, S.C, P_suction
COLUMNS (cassette): S.H_total-{ab}, S.C-{ab}, P_suc-{ab}
THRESHOLDS:
  - rf2_sh_high_warning_f: 25.0
  - rf2_sh_high_critical_f: 40.0
  - rf2_sc_low_f: 3.0
  - trend_window_rows: 10
DISTINGUISH FROM RF-1: Values persistently out of range (no trend), vs RF-1 which
                        requires a time trend of getting worse.
```

#### RF-3 · Overcharge
```
APPROACH:  Point check. SC very high AND high condensing pressure.
           Possible flooding back to suction (low SH alongside high SC).
COLUMNS (shared):   S.C, P_disch, T_sat.cond, S.H_total
COLUMNS (cassette): S.C-{ab}, P_disch-{ab}, T_sat.cond-{ab}, S.H_total-{ab}
THRESHOLDS:
  - rf3_sc_high_warning_f: 20.0
  - rf3_sc_high_critical_f: 30.0
```

#### RF-4 · NonCondensables
```
APPROACH:  Cross-check discharge pressure vs what T_sat.cond predicts. Non-condensables
           raise discharge pressure higher than the condensing temperature alone explains.
           Approach temp also higher than expected for water temp.
COLUMNS (shared):   P_disch, T_sat.cond, T_waterout, T_4a
COLUMNS (cassette): P_disch-{ab}, T_sat.cond-{ab}, T_waterout-{ab}, T_4a-{ab}
THRESHOLDS:
  - rf4_approach_temp_warning_f: 8.0
  - rf4_approach_temp_critical_f: 15.0
NOTE: Hard to distinguish from CD-1 (condenser blockage) without additional info.
      If both RF-4 and CD-1 fire, recommendation will note both possibilities.
```

---

### ⚙️ COMPRESSOR

#### CP-1 · LiquidSluggingRisk
```
APPROACH:  Point check. SH at compressor inlet below danger threshold.
COLUMNS (shared):   S.H_total
COLUMNS (cassette): S.H_total-{ab}
THRESHOLDS:
  - cp1_sh_critical_f: 0.0    (at or below → CRITICAL)
  - cp1_sh_warning_f:  5.0    (below → WARNING)
  - trend_window_rows: 10
```

#### CP-2 · CompressorOverheating
```
APPROACH:  Point check on T_3a (discharge temp). Also considers pressure ratio —
           high PR + high T_3a compounds severity.
COLUMNS (shared):   T_3a, P_disch, P_suction
COLUMNS (cassette): T_3a-{ab}, P_disch-{ab}, P_suc-{ab}
THRESHOLDS:
  - cp2_discharge_temp_warning_f:  220.0
  - cp2_discharge_temp_critical_f: 260.0
NOTE: R290 max recommended discharge temp is ~250°F. Adjust if using different refrigerant.
```

#### CP-3 · CompressorNotCompressing
```
APPROACH:  Point check. Pressure ratio (P_disch / P_suction in absolute) below
           minimum expected for any operating condition.
COLUMNS (shared):   P_disch, P_suction
COLUMNS (cassette): P_disch-{ab}, P_suc-{ab}
THRESHOLDS:
  - cp3_pr_critical: 1.5    (below this → compressor not working)
SEVERITY:  Always CRITICAL.
```

#### CP-4 · PressureRatioExtreme
```
APPROACH:  Point check. Pressure ratio above maximum physically plausible for R290.
           Indicates sensor error (suction too low or discharge too high reading).
COLUMNS:   Same as CP-3
THRESHOLDS:
  - cp4_pr_high: 10.0
```

#### CP-5 · CompressorOverheatingTrend
```
APPROACH:  Trend check. T_3a trending upward across all data (positive slope).
           Indicates gradual degradation: refrigerant loss, poor lubrication, restricted suction.
COLUMNS (shared):   T_3a
COLUMNS (cassette): T_3a-{ab}
THRESHOLDS:
  - cp5_discharge_slope_f_per_row: 0.2   (min slope to flag)
```

#### CP-6 · CompressorOversized / CP-7 · CompressorUndersized
```
APPROACH:  Compare actual mass flow (m_dot) vs what rated_inputs would expect
           for the number of circuits. If m_dot >> rated → oversized.
           If m_dot << rated → undersized or worn.
COLUMNS:   m_dot (shared), m_dot-{ab} (cassette)
NOTE:      Only fires if rated_capacity_btu_hr is available in rated_inputs.
           Without rated specs, this check is skipped and marked INFO.
```

---

### 🌡️ CONDENSER

#### CD-1 · CondenserBlockageFouling
```
APPROACH:  Point check. Approach temp = T_sat.cond − T_4a. High approach = condenser
           struggling to reject heat → blockage, fouling, or insufficient water flow.
COLUMNS (shared):   T_sat.cond, T_4a, P_disch
COLUMNS (cassette): T_sat.cond-{ab}, T_4a-{ab}, P_disch-{ab}
THRESHOLDS:
  - cd1_approach_warning_f:  8.0
  - cd1_approach_critical_f: 15.0
```

#### CD-2 · WaterFlowIssue
```
APPROACH:  Point check. (T_waterout − T_waterin) very high = low water flow rate.
           Very small ΔT = no heat rejection or no flow (sensor error).
COLUMNS (shared):   T_waterin, T_waterout
COLUMNS (cassette): T_waterin-{ab}, T_waterout-{ab}
THRESHOLDS:
  - cd2_water_dt_high_warning_f:  12.0
  - cd2_water_dt_high_critical_f: 20.0
  - cd2_water_dt_low_f:           1.0    (suspiciously small ΔT)
```

#### CD-3 · CondenserOversized
```
APPROACH:  WATCH only. Approach temp very small (< 2°F). Not a problem, but
           informational — condenser may be oversized for this condition.
COLUMNS:   Same as CD-1
THRESHOLDS:
  - cd3_approach_oversized_f: 2.0
SEVERITY:  INFO / WATCH only. Never WARNING or CRITICAL.
```

#### CD-4 · CondenserUndersized
```
APPROACH:  Point + trend. High condensing pressure relative to water inlet temp,
           approach temp persistently high, discharge temp trending up.
THRESHOLDS: Uses cd1 + cp2 thresholds combined.
```

---

### ❄️ EVAPORATOR / COILS (always per module)

#### EV-1 · CoilRestrictionOrIcing
```
APPROACH:  Point check per module. Coil outlet SH very high (no heat pickup —
           airflow blocked by frost/debris) OR very low (liquid flooding — frost
           just starting to melt / reduced superheat). Both extremes are flags.
COLUMNS:   S.H_{ab} coil  (all system types, per module)
           e.g. 'S.H_lh coil', 'S.H_ctr coil', 'S.H_rh coil'
THRESHOLDS:
  - ev1_coil_sh_high_warning_f:  25.0   (high SH → restricted airflow)
  - ev1_coil_sh_high_critical_f: 40.0
  - ev1_coil_sh_low_warning_f:    3.0   (low SH → possible icing/flooding)
  - ev1_coil_sh_low_critical_f:   0.0
```

#### EV-2 · ModuleImbalance (shared systems, ≥ 2 modules only)
```
APPROACH:  Point check. Compare coil SH across all modules. If max − min > threshold,
           refrigerant distribution is uneven. Could be distributor, TXV, or one coil iced.
COLUMNS:   S.H_{ab} coil for all module labels
THRESHOLDS:
  - ev2_sh_imbalance_warning_f:  8.0
  - ev2_sh_imbalance_critical_f: 15.0
SYSTEM:    shared only. Cassette units are independent — compare separately if needed.
```

#### EV-3 · EvaporatorOversized / EV-4 · EvaporatorUndersized
```
APPROACH:  Compare actual capacity (qc) per module vs rated_capacity_btu_hr /
           n_modules. Large persistent gap → sizing issue.
NOTE:      Only fires if rated_capacity_btu_hr available.
```

---

### 🔧 TXV (per module)

#### TX-1 · TXVStarvedOrBlocked
```
APPROACH:  Point check per module. Coil SH very high → TXV not letting enough
           refrigerant through. Combined with low T_1b (low refrigerant flow
           entering coil) strengthens confidence.
COLUMNS:   S.H_{ab} coil, T_1b-{ab}
THRESHOLDS:
  - tx1_sh_warning_f:  25.0
  - tx1_sh_critical_f: 40.0
```

#### TX-2 · TXVFloodingStuckOpen
```
APPROACH:  Point check per module. Coil SH very low or negative.
           Too much refrigerant through TXV → liquid carry-over risk.
COLUMNS:   S.H_{ab} coil
THRESHOLDS:
  - tx2_sh_warning_f:  3.0
  - tx2_sh_critical_f: 0.0
```

#### TX-3 · TXVHuntingInstability
```
APPROACH:  Trend check per module. Standard deviation of S.H_{ab} coil over
           all rows. High std dev = TXV oscillating between starved and flooded.
COLUMNS:   S.H_{ab} coil
THRESHOLDS:
  - tx3_sh_std_warning_f:  5.0
  - tx3_sh_std_critical_f: 10.0
```

#### TX-4 · TXVOversized / TX-5 · TXVUndersized
```
APPROACH:  Oversized: hunting (TX-3) + mean coil SH low → TXV overshoots often.
           Undersized: coil SH persistently high even at rated operating conditions.
NOTE:      These fire as WATCH/INFO if TX-3 already fires, to give context.
```

---

### 🔩 DISTRIBUTOR & FILTER DRYER

#### DI-1 · DistributorBlockageOrImbalance (shared systems, ≥ 2 modules)
```
APPROACH:  The distributor splits liquid refrigerant from the condenser to each
           module's TXV. Blockage or imbalance causes:
           - One module with very high coil SH (starved)
           - Other modules normal or slightly low SH
           Key columns: S.H_{ab} coil imbalance PLUS T_1b-{ab} (TXV inlet temp)
           being significantly lower on the starved branch.
           Cross-check: S.C at condenser outlet (S.C) is still OK, but
           S.C-txv.{ab} on affected branch is lower → pressure drop across distributor.
COLUMNS:   S.H_{ab} coil, T_1b-{ab}, S.C, S.C-txv.{ab} per module
DISTINGUISH FROM TX-1 (TXV blocked): If TXV is blocked, S.C-txv.{ab} on that
           branch is normal (SC OK, liquid arrives fine). If distributor is blocked,
           S.C-txv.{ab} is lower on the affected branch (liquid is restricted BEFORE TXV).
THRESHOLDS:
  - di1_sh_imbalance_warning_f:  8.0
  - di1_sc_drop_warning_f:       4.0   (drop between S.C and S.C-txv.{ab})
```

#### DI-2 · FilterDryerBlockage
```
APPROACH:  A blocked filter dryer causes a liquid line pressure drop, which
           partially flashes the refrigerant before the TXV(s).
           Key signature:
           - S.C at condenser outlet (S.C or S.C-{ab}) is normal / positive
           - S.C-txv.{ab} at TXV inlet(s) is significantly LOWER than S.C
           - The gap between S.C and S.C-txv.{ab} grows as blockage worsens (trend)
           - Accompanied by reduced capacity (qc) and high SH
COLUMNS (shared):   S.C, S.C-txv.{ab} for all modules
COLUMNS (cassette): S.C-{ab}, S.C-txv.{ab} for all modules in that unit
THRESHOLDS:
  - di2_sc_drop_warning_f:  3.0   (S.C − mean(S.C-txv.{ab}) > this → WARNING)
  - di2_sc_drop_critical_f: 8.0
TREND VERSION (DI-2T): The SC gap trending larger over time → progressive blockage.
```

#### DI-3 · DistributorOversized / DI-4 · DistributorUndersized
```
APPROACH:  Informational only (WATCH). Persistent low pressure drop across
           distributor = oversized (minimal distribution resistance).
           Persistent high SC drop without blockage signature = undersized orifice.
NOTE:      Hard to detect without dedicated pressure sensors. Flagged as WATCH
           based on SC-gap pattern combined with no other blockage indicators.
```

---

### 🔥 HOT GAS DEFROST (indirect detection only)

> No dedicated defrost sensors available. All checks use indirect inference from existing data.
> Integration point: `defrost_detection.py` already identifies defrost periods.

#### HG-1 · DefrostBlockedOrIneffective
```
APPROACH:  During detected defrost periods (from defrost_detection.py), coil inlet
           temp (T_1b-{ab}) should rise quickly as hot gas enters. If the coil
           temperature does NOT rise during a defrost period, hot gas is not reaching
           the coil → possible blockage in the hot gas line.
           Also check: if defrost periods are completely absent for a long test run
           (e.g. > 4 hours of data with no defrost), warn about potential issue.
COLUMNS:   T_1b-{ab} during rows flagged as defrost by defrost_detection.py
THRESHOLDS:
  - hg1_defrost_temp_rise_min_f: 10.0   (expected coil temp rise during defrost)
  - hg1_max_run_without_defrost_rows: 240  (e.g. 4 hrs if 1-min intervals)
```

#### HG-2 · DefrostInstalledBackwards
```
APPROACH:  If hot gas defrost is installed backwards, hot gas flows the wrong way
           through the coil. Signature: during defrost, suction pressure RISES sharply
           (hot gas entering low-pressure side) AND coil temp does NOT rise at the
           expected end (outlet end). This is an unusual pressure spike on the suction side
           during defrost.
COLUMNS:   P_suction (shared) or P_suc-{ab} (cassette) + T_1b-{ab} during defrost periods
THRESHOLDS:
  - hg2_suction_pressure_spike_psig: 5.0   (suction rise during defrost → suspect)
NOTE:      Low confidence check. Will be marked WARNING with note that further
           investigation (visual inspection) is needed to confirm.
FALSE POSITIVES: Pressure spikes during defrost termination are normal. Only flag
                 if spike occurs at defrost START and persists.
```

---

### 🔌 SENSOR / THERMODYNAMIC IMPOSSIBILITIES

#### SI-1 · NegativeSubcooling
```
COLUMNS (shared):   S.C
COLUMNS (cassette): S.C-{ab} per unit
THRESHOLDS:
  - si1_sc_mild_f:    0.0    (< 0 → WARNING)
  - si1_sc_moderate_f: -5.0  (< -5 → CRITICAL)
  - si1_sc_severe_f:  -15.0  (< -15 → CRITICAL + sensor error suspected)
```

#### SI-2 · EnthalpyReversal
```
APPROACH:  H_comp.in < average(H_txv.{ab}) → net evaporation is negative.
           Physically impossible at steady state.
COLUMNS:   H_comp.in, H_txv.{ab} per module
```

#### SI-3 · ZeroNegativeSuperheat
```
APPROACH:  S.H_total ≤ 0 (shared) or S.H_total-{ab} ≤ 0 (cassette).
           Covered by CP-1 but repeated here as an impossibility flag.
```

#### SI-4 · SubAtmosphericPressure
```
APPROACH:  P_suction < -14.7 PSIG → below absolute vacuum. Sensor error.
```

#### SI-5 · TemperatureOrderViolation
```
APPROACH:  Cross-checks expected temperature ordering around the refrigerant circuit:
           - T_3a (comp outlet) must be > T_2b (comp inlet)
           - T_4a (cond outlet) must be < T_3b (cond inlet)
           - T_waterin typically < T_waterout (heat rejection to water)
COLUMNS (shared):   T_3a, T_2b, T_4a, T_3b, T_waterin, T_waterout
COLUMNS (cassette): All above with -{ab} suffix
```

#### SI-6 · PressureSaturationConflict
```
APPROACH:  T_sat.comp.in (derived from P_suction) should roughly equal T_2b − S.H_total.
           Large discrepancy suggests pressure sensor reading incorrectly.
THRESHOLDS:
  - si6_conflict_warning_f:  5.0
  - si6_conflict_critical_f: 15.0
```

---

## 6. UI Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  🩺 DIAGNOSTICS   System: Cassette 2-unit (LH + RH)  │  145 rows  │ ⚙ Edit │
│                                                                              │
│  ● 2 CRITICAL   ● 4 WARNING   ● 2 WATCH   ✓ 11 OK   [ Filter: All ▾ ]     │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─ 🔴 CRITICAL ──────────────────────── CP-1 · Liquid Slugging Risk (LH) ─┐│
│  │  SH at comp inlet = 1.2°F avg (last 10 rows). Below 5°F threshold.      ││
│  │  [▼ Evidence]                              [▼ Recommendation]            ││
│  └──────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─ 🔴 CRITICAL ──────────────────────────── SI-1 · Negative Subcooling ───┐│
│  │  S.C (LH) = -8.3°F (moderate). Vapor present in liquid line.            ││
│  │  [▼ Evidence]                              [▼ Recommendation]            ││
│  └──────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─ 🟡 WARNING ─────────────────── RF-1 · Possible Refrigerant Leak (LH) ──┐│
│  │  TREND: SH +12°F, SC -8°F, P_suc -4 PSIG over 145 rows.               ││
│  │  [▼ Evidence — expanded] ─────────────────────────────────────────────  ││
│  │   SH slope: +0.083 °F/row  (threshold: 0.3)  ✓                         ││
│  │   SC slope: -0.055 °F/row  (threshold: 0.3)  ✓                         ││
│  │   P_suc slope: -0.028 PSI/row               ✓                          ││
│  │   qc slope:    -1.2 BTU/hr/row              ✓                          ││
│  │   Rows analysed: all 145                                                ││
│  │  [▼ Recommendation — expanded] ───────────────────────────────────────  ││
│  │   All four leak indicators trending in the leak direction over the test. ││
│  │   1. Inspect all fittings and solder joints for signs of oil/leaks.     ││
│  │   2. Weigh refrigerant charge and compare to nameplate charge.          ││
│  │   3. Perform standing pressure test with nitrogen.                      ││
│  └──────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─ 🔵 WATCH ──────────────────────────────── EV-2 · Module Imbalance ─────┐│
│  │  SH(LH)=18°F vs SH(RH)=7°F. Δ=11°F. Check distributor or TXV.         ││
│  └──────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─ ✅ OK ─────────────────────────────────────── CD-1 · Condenser ─────────┐│
│  │  Approach temp: 5.2°F (normal). No blockage detected.                   ││
│  └──────────────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────────────┘
```

**⚙ Edit button** opens a threshold dialog:
```
┌─ Thresholds Editor ─────────────────────────────────────────────────────────┐
│  RF-1 · Refrigerant Leak (Trend)                                            │
│    rf1_sh_slope_f_per_row:     [0.30]   Min SH rise rate (°F/row) to flag  │
│    rf1_sc_slope_f_per_row:     [0.30]   Min SC fall rate (°F/row) to flag  │
│    rf1_min_matching_signals:   [3  ]    Of 4 signals, how many must match  │
│  ─────────────────────────────────────────────────────────────────────────  │
│  CP-1 · Liquid Slugging Risk                                                │
│    cp1_sh_critical_f:          [0.0 ]   SH at/below → CRITICAL            │
│    cp1_sh_warning_f:           [5.0 ]   SH below → WARNING                │
│  [Reset to Defaults]                           [OK]   [Cancel]              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Integration into app.py (3 changes)

```python
# --- Line 1: Import ---
from diagnostics_widget import DiagnosticsWidget

# --- Line 2: Instantiate + connect signal ---
self.diagnostics_widget = DiagnosticsWidget(self.data_manager)
self.calculations_widget.filtered_data_ready.connect(
    self.diagnostics_widget.on_data_ready
)

# --- Line 3: Add tab ---
self.tabs.addTab(self.diagnostics_widget, "🩺 Diagnostics")
```

`update_active_tab()` in app.py: Diagnostics is **passive** (data pushed via signal). No changes needed to that method.

---

## 8. How to Add a New Scenario (after implementation)

1. Open `diagnostics_engine.py`
2. Find the section for the relevant component (e.g. `# ─── CONDENSER SCENARIOS ───`)
3. Copy any existing scenario class as a template
4. Fill in: `SCENARIO_ID`, `COMPONENT`, `LABEL`, `DEFAULT_THRESHOLDS`, `run()` method, docstring
5. Scroll to the bottom and add `YourNewScenario()` to `SCENARIO_REGISTRY`
6. Done. The UI will automatically pick it up.

## 9. How to Disable a Faulty Scenario

Open `diagnostics_engine.py`, find the class (they're labelled), and set:
```python
ENABLED = False   # Disabled 2026-03-10: flagging false positives during defrost periods
```
The scenario will stop running but stays in the code with your comment for reference.

## 10. How to Adjust a Detection Method

Open the class, read the docstring to understand the current approach, edit the `run()` method. The docstring has an `UPDATE LOG` section — add a line with the date and what you changed.

---

## 11. Files Summary

| File | Action |
|------|--------|
| `diagnostics_engine.py` | NEW (~600 lines) |
| `diagnostics_widget.py` | NEW (~400 lines) |
| `app.py` | MODIFY — 3 lines only |
| `CLAUDE.md` | UPDATE at session end |
| `DIAGNOSTICS_PLAN.md` | This file — update as scenarios evolve |
