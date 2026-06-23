# HVAC Lab Viewer — Claude Reference Guide
> **Auto-loaded every session. This is the single source of truth for the app architecture.**
> Last updated: 2026-03-09 — Sessions 1-8

---

## 1. What Is This App?

**HVAC Lab Viewer** is a **PyQt6 desktop application** for analyzing lab test data from commercial HVAC refrigeration systems. It is used by engineers to:

1. **Load raw sensor data** (CSV/Excel) from a data acquisition system
2. **Map sensors** to a refrigerant circuit diagram (interactive drag-drop)
3. **Compute thermodynamic performance** (CoolProp for R290/propane) — superheat, subcooling, enthalpies, mass flow, capacity
4. **Diagnose problems** automatically using 29 built-in diagnostic scenarios that flag sensor errors, refrigerant leaks, compressor issues, condenser fouling, TXV problems, etc.

**Tech stack:** Python 3.11+, PyQt6, pandas, numpy, CoolProp, matplotlib

**Entry point:** `app.py` → `MainWindow` → 5 tabs

---

## 2. Application Layout

```
┌─ Sensor Panel (left, 350px fixed) ──┐  ┌─ Tab Widget (right) ────────────────────────────┐
│  Load CSV / Load Session / Save      │  │  [Diagram] [Graph] [Comparison] [Calculations]  │
│  Sensor list from loaded CSV         │  │  [Diagnostics]                                   │
│  Range editor                        │  │                                                   │
│  Sensor → port assignment            │  │  (active tab content fills this area)              │
└──────────────────────────────────────┘  └──────────────────────────────────────────────────┘
```

### Tab Descriptions:
| Tab | File(s) | Purpose |
|-----|---------|---------|
| **Diagram** | `diagram_widget.py`, `diagram_components.py`, `component_schemas.py` | Interactive circuit diagram — drag sensors to ports. Defines the system topology. |
| **Graph** | `graph_widget.py` | Time-series plotting of any sensor columns |
| **Comparison** | `comparison_widget.py` | Side-by-side comparison of multiple test sessions |
| **Calculations** | `calculations_widget.py` | Thermodynamic results table (NestedHeaderView), audit dialog, P-h diagram, calculation summary |
| **Diagnostics** | `diagnostics_widget.py` + `diagnostics_engine.py` | 29 automated diagnostic scenarios — flags issues, shows evidence + recommendations |

### Signal Flow:
```
DataManager.data_changed / diagram_model_changed
    → CalculationsWidget (runs batch calculations)
        → emits filtered_data_ready(processed_df)
            → DiagnosticsWidget.on_data_ready(processed_df)
                → diagnostics_engine.run_all_diagnostics(processed_df, ...)
                    → list of Finding objects → rendered as cards
```

---

## 3. Project Location & Files

```
C:\Users\silam\OneDrive\Documents\Lab viewer\HVAC_Dev\
```

### Core Pipeline Files (in execution order):

| # | File | Responsibility |
|---|------|---------------|
| 1 | `circuit_semantics.py` | Public API for module labels, abbreviations, sensor key names |
| 2 | `data_manager.py` | Load/save sessions; runs migration on load |
| 3 | `diagram_template_loader.py` | Loads diagram templates; also runs migration |
| 4 | `calculation_orchestrator.py` | Orchestrates full batch calculation; builds sensor maps; handles shared vs cassette |
| 5 | `calculation_engine.py` | Row-by-row thermodynamic calculations (CoolProp for R290) |
| 6 | `cycle_solver.py` | Steady-state cycle solver — predicts operating point from component specs (scipy + CoolProp) |
| 7 | `ph_diagram_generator.py` | Saturation data for P-h diagram (used by Calculations audit dialog) |
| 8 | `calculations_widget.py` | Main results table (NestedHeaderView), audit dialog, calculation summary, P-h diagram in audit |

### Diagnostics Files:

| File | Responsibility |
|------|---------------|
| `diagnostics_engine.py` (~4400 lines) | 29 scenario classes, Finding dataclass, expression evaluator, rule config system |
| `diagnostics_widget.py` (~1700 lines) | DiagnosticsWidget (card UI), RulesDialog (visual rule builder), ColumnManagerDialog, ThresholdsDialog |
| `rules_config.json` | Persisted rule overrides (v2.0 format — structured conditions, no free-text expressions) |
| `custom_diagnostics.json` | User-created custom scenarios (persisted) |
| `defrost_detection.py` | Detects hot gas defrost periods from pressure differential — used by HG-1/HG-2 scenarios |

### Other Important Files:

| File | Role |
|------|------|
| `app.py` | Entry point, MainWindow, tab setup, signal wiring |
| `sensor_panel.py` | Left panel — CSV loading, sensor list, range editor |
| `diagram_widget.py` | Interactive circuit diagram (drag-drop sensor mapping) |
| `graph_widget.py` | Time-series graph tab |
| `mapping_dialog.py` | Sensor-to-port mapping dialog |
| `snapshot_manager.py` | Session snapshot management |
| `logging_setup.py` | Centralized logging config |

---

## 4. System Types

| Type | Detection | Description |
|------|-----------|-------------|
| `'shared'` | `n_compressors == 1` | One compressor + one condenser shared by all evaporator modules (modular / non-modular units) |
| `'cassette'` | `n_compressors > 1` | Each unit has its own independent compressor + condenser + evaporator loop |

**Detection function** (in `calculation_orchestrator.py`):
```python
def _detect_system_type(diagram_model: dict) -> str:
    comps = diagram_model.get('components', {})
    n_compressors = sum(1 for c in comps.values() if c.get('type') == 'Compressor')
    return 'cassette' if n_compressors > 1 else 'shared'
```

### Supported Configurations:

| Config | System Type | Modules | Columns |
|--------|------------|---------|---------|
| Non-modular | shared | 1 (Left) | 30 |
| 2-module | shared | Left + Right | 42 |
| 3-module | shared | Left + Center + Right | 54 |
| Cassette 1-unit | cassette | 1 | 30 |
| Cassette 2-unit | cassette | 2 | 60 |
| Cassette 3-unit | cassette | 3 | 90 |

---

## 5. Module Label Conventions

### Labels & Abbreviations
| Full Label | `module_abbrev(label)` | `module_abbrev(label, upper=True)` |
|------------|----------------------|-----------------------------------|
| `'Left'`   | `'lh'`              | `'LH'`                           |
| `'Center'` | `'ctr'`             | `'CTR'`                          |
| `'Right'`  | `'rh'`              | `'RH'`                           |

### Public API — `circuit_semantics.py`
```python
module_abbrev(label, upper=False)   # 'Left' -> 'lh' or 'LH'
txv_outlet_key(label)               # 'Left' -> 'T_1b-lh'  (coil inlet / TXV outlet)
coil_outlet_key(label)              # 'Left' -> 'T_2a-LH'  (coil outlet)
get_all_module_labels(model)        # returns sorted list from diagram model e.g. ['Left','Right']
```

### Clean Naming Convention (post-migration)
| Module | TXV outlet (coil inlet) | Coil outlet | TXV inlet |
|--------|------------------------|-------------|-----------|
| Left   | `T_1b-lh`              | `T_2a-LH`  | `T_4b-lh` |
| Center | `T_1b-ctr`             | `T_2a-CTR` | `T_4b-ctr`|
| Right  | `T_1b-rh`              | `T_2a-RH`  | `T_4b-rh` |

---

## 6. Column Naming — Shared vs Cassette

### Shared System Columns
Single compressor/condenser — columns are NOT suffixed:
```
P_suction, P_disch, T_2b, T_3a, T_3b, T_4a, T_waterin, T_waterout
T_sat.comp.in, S.H_total, D_comp.in, H_comp.in, S_comp.in
T_sat.cond, S.C, rpm, m_dot, qc
```
Per-module (shared) — suffixed with lowercase abbrev or uppercase:
```
T_1a-{ab}, T_1b-{ab}, T_2a-{AB}, T_4b-{ab}
T_sat.{ab}, S.H_{ab} coil, D_coil {ab}, H_coil {ab}, S_coil {ab}
T_sat.txv.{ab}, S.C-txv.{ab}, H_txv.{ab}
h_4b_{AB}, h_2a_{AB}       <- hidden P-h columns
h_3a, h_4a, h_2b           <- hidden shared enthalpy columns
```

### Cassette System Columns
Every column is per-unit suffixed with `-{ab}`:
```
P_suc-{ab}, P_disch-{ab}, T_2b-{ab}, T_3a-{ab}, T_3b-{ab}, T_4a-{ab}
T_waterin-{ab}, T_waterout-{ab}, T_sat.comp.in-{ab}, S.H_total-{ab}
D_comp.in-{ab}, H_comp.in-{ab}, S_comp.in-{ab}, T_sat.cond-{ab}
S.C-{ab}, rpm-{ab}, m_dot-{ab}, qc-{ab}
h_2b-{ab}, h_3a-{ab}, h_4a-{ab}            <- hidden enthalpy columns
h_4b_{AB}-{ab}, h_2a_{AB}-{ab}             <- hidden P-h columns
P_suc_pa-{ab}, P_cond_pa-{ab}              <- internal Pa pressures
```

---

## 7. Key Functions by File

### `calculation_orchestrator.py`
```python
_detect_system_type(diagram_model)              # -> 'shared' | 'cassette'
_build_required_sensor_roles(module_labels)     # -> dict of roles for shared system
_build_cassette_unit_sensor_map(...)            # -> sensor_map for one cassette unit
run_batch_processing(...)                       # main entry; branches on system_type
```

### `calculation_engine.py`
```python
calculate_row_performance(row, sensor_map, comp_specs,
                          refrigerant='R290',
                          module_labels=None,      # drives coil loop
                          system_type='shared')    # 'shared'|'cassette'
```
- Dynamic coil loop over `module_labels`
- Produces `h_4b_{AB}`, `h_2a_{AB}` per label; `h_4b_values` for capacity sum
- RPM: from `comp_specs.get('speed_rpm')` — None for fixed-speed shows `---`

### `calculations_widget.py`
```python
_build_header_data(module_labels)           # -> (ms, ss, us, cn) for shared layout
_build_header_data_cassette(module_labels)  # -> (ms, ss, us, cn) for cassette layout
_rebuild_column_schema(self)                # detects type, calls correct builder
generate_calculation_summary(self, row)     # branches on system_type
generate_audit_text(self, row)              # all sections cassette-aware
```

### Header Layout — `NestedHeaderView`
4-row QPainter header with main sections, sub-headers, units, and column names.
**Shared layout** (3-module = 54 cols): per-module coil blocks -> shared comp/cond block -> per-module TXV blocks -> TOTAL
**Cassette layout** (per unit = 30 cols/unit): per-unit coil(8) + comp_in(7) + comp_out(2) + cond(7) + TXV(4) + total(2)

---

## 8. Data Migration (on session load)

Applied automatically in `data_manager.py` -> `load_session()` and `diagram_template_loader.py`:
```python
{'T_1c-rh': 'T_1b-rh',    # Right coil inlet legacy anomaly
 'T_2a-ctr': 'T_2a-CTR'}  # Center coil outlet case fix
```

---

## 9. Diagnostics System — FULL ARCHITECTURE

### 9.1 Overview
The Diagnostics tab is the 5th tab ("Diagnostics"). It automatically analyzes the computed `processed_df` from the Calculations tab and generates intelligent warnings, flags, and troubleshooting recommendations.

### 9.2 Engine Architecture (`diagnostics_engine.py`)

**Pattern:** Scenario Registry — each diagnostic check is a self-contained class.

```python
@dataclass
class Finding:
    scenario_id:    str          # e.g. 'RF-1'
    label:          str          # display name
    component:      str          # 'Compressor', 'Condenser', etc.
    severity:       str          # 'CRITICAL' | 'WARNING' | 'WATCH' | 'OK' | 'INFO'
    summary:        str          # one-liner on card header
    evidence:       str          # multi-line values/slopes
    recommendation: str          # detailed "POSSIBLE CAUSES" action steps
    affected_rows:  list
    uses_trend:     bool
```

**Base class:**
```python
class DiagnosticScenario:
    SCENARIO_ID = ''
    COMPONENT = ''
    LABEL = ''
    DESCRIPTION = ''           # "What is this fault?" text
    LOGIC = ''                 # "How is it detected?" text
    DEFAULT_THRESHOLDS = {}    # adjustable via Thresholds dialog
    DEFAULT_EXPRESSIONS = {}   # structured conditions for visual rule builder
    ENABLED = True

    def run(self, df, ctx, thresholds) -> list[Finding]:  # Python-based detection
    def t(self, thresholds, key):                          # threshold lookup helper
```

### 9.3 The 30 Built-in Scenarios

| ID | Class | Component | What It Detects |
|----|-------|-----------|-----------------|
| RF-1 | `RF1_RefrigerantLeakTrend` | Refrigerant | 4-signal leak trend (SH rising, SC falling, P_suc falling, qc falling) |
| RF-2 | `RF2_Undercharge` | Refrigerant | Low charge (high SH + low SC point check) |
| RF-3 | `RF3_Overcharge` | Refrigerant | Excess charge (high SC + low SH + high P_disch) |
| RF-4 | `RF4_NonCondensables` | Refrigerant | Air/nitrogen in circuit (P_disch > CoolProp predicted) |
| CP-1 | `CP1_LiquidSluggingRisk` | Compressor | Zero/negative superheat at compressor inlet |
| CP-2 | `CP2_CompressorOverheating` | Compressor | T_3a (discharge temp) too high |
| CP-3 | `CP3_NotCompressing` | Compressor | Pressure ratio below 1.5 (mechanical failure) |
| CP-4 | `CP4_PressureRatioExtreme` | Compressor | PR > 10 (sensor error, not real) |
| CP-5 | `CP5_DischargeTempTrend` | Compressor | T_3a trending upward (developing problem) |
| CP-6 | `CP6_HighCompressionRatio` | Compressor | CR 5.5-10 range (operational warning) |
| CD-1 | `CD1_CondenserBlockage` | Condenser | High approach temp (T_sat.cond - T_waterout) |
| CD-2 | `CD2_WaterFlowIssue` | Condenser | Water DT too high (low GPM) or too low |
| EV-1 | `EV1_CoilRestrictionOrIcing` | Evaporator | Per-module coil SH too high (starved) or too low (flooding) |
| EV-2 | `EV2_ModuleImbalance` | Evaporator | SH spread across modules (shared systems, >=2 modules only) |
| EV-3 | `EV3_CoilIcingTrend` | Evaporator | T_sat < 32F + 3 declining signals = icing |
| TX-1 | `TX1_TXVStarvedOrBlocked` | TXV | Very high coil SH (TXV restriction) |
| TX-2 | `TX2_TXVFlooding` | TXV | Very low coil SH (TXV stuck open) |
| TX-3 | `TX3_TXVHunting` | TXV | High std dev of coil SH (TXV oscillating) |
| DI-1 | `DI1_DistributorImbalance` | Distributor | SH imbalance + SC drop on affected branch |
| DI-2 | `DI2_FilterDryerBlockage` | Filter Dryer | SC drop across liquid line (S.C - S.C-txv) |
| DI-3 | `DI3_EvaporatorDistributorRestriction` | Evap Distributor | T_1b > T_1a (flash gas in distributor) |
| SL-1 | `SL1_SuctionLineRestriction` | Suction Line | SH gain between coils and compressor (shared, >=2 modules) |
| HG-1 | `HG1_DefrostIneffective` | Hot Gas Defrost | Defrost cycle doesn't raise coil temp enough (Python-only) |
| HG-2 | `HG2_DefrostTooFrequent` | Hot Gas Defrost | Too many defrost cycles detected (Python-only) |
| SI-1 | `SI1_NegativeSubcooling` | Sensors | SC < 0 (impossible — sensor error or massive undercharge) |
| SI-2 | `SI2_EnthalpyReversal` | Sensors | H_comp.in < H_txv (evaporator running backwards) |
| SI-3 | `SI3_SubAtmosphericPressure` | Sensors | P_suction < -14 PSIG (below vacuum — sensor error) |
| SI-4 | `SI4_TemperatureOrderViolation` | Sensors | T_3a < T_2b or T_4a > T_3b or T_waterout < T_waterin |
| SI-5 | `SI5_PressureSaturationConflict` | Sensors | CoolProp state point outside valid phase region (Python-only) |
| PV-1 | `PV1_PredictedVsActual` | System | Cycle solver prediction vs actual sensors — pinpoints root cause from deviation pattern |

### 9.4 Dual Evaluation Paths

Each scenario has TWO ways to be evaluated:

1. **Expression-based** (via `rules_config.json` + `_evaluate_rule()`):
   - User-editable structured conditions (dropdowns, no free-text)
   - Stored in `DEFAULT_EXPRESSIONS` class attribute or overridden in `rules_config.json`
   - 25 of 29 scenarios use this path by default

2. **Python-only** (via `scenario.run()` method):
   - Full Python logic with CoolProp calls, complex conditionals
   - Used when `DEFAULT_EXPRESSIONS == {}` (RF-4, HG-1, HG-2, SI-5)
   - Also used as fallback if expression eval fails

**Priority in `run_all_diagnostics()`:**
```
if rules_config has expressions for this scenario:
    evaluate expressions -> get Finding
    patch recommendation from run() method   <-- IMPORTANT (added Session 8)
else:
    call scenario.run() directly
```

**Critical design decision (Session 8 fix):** When expression-based evaluation fires, the recommendation text is patched from the scenario's `run()` method. Without this, `_evaluate_rule()` would show the DESCRIPTION ("what is this fault?") instead of the detailed "POSSIBLE CAUSES" recommendation. The patching logic calls `run()` only for non-OK findings, extracts recommendations by severity, and patches them into the expression-based Finding objects.

### 9.5 Structured Condition Format (v2.0)

```json
{
  "CRITICAL": {
    "join": "and",           // "and" | "or" | "at_least"
    "min_count": 4,          // only for "at_least" join
    "conditions": [
      {
        "column": "S.H_total",
        "column2": "",        // empty for single-column functions
        "function": "slope",  // mean|slope|std|last|pct_above|pct_below|diff_mean|abs_diff_mean|pressure_ratio
        "operator": ">",
        "value": 0.10
      }
    ]
  }
}
```

**Two-column functions:** `diff_mean(A, B)` = mean(A) - mean(B), `abs_diff_mean(A, B)` = |mean(A) - mean(B)|, `pressure_ratio(P_disch, P_suc)` = (mean(P_d)+14.696)/(mean(P_s)+14.696)

### 9.6 Widget Architecture (`diagnostics_widget.py`)

**Main classes:**
- `DiagnosticsWidget` — main tab widget, summary bar, card scroll area, toolbar buttons
- `FindingCard` — expandable card for one Finding (Evidence / Recommendation / What is this? / Logic sections)
- `RulesDialog` — visual rule builder (called via "Rules" toolbar button)
- `SeverityBlock` — one severity level in the rule builder (join combo + condition rows + test button)
- `ConditionRow` — single condition: column dropdown + function dropdown + operator + value (+ optional column2)
- `ThresholdsDialog` — edit numeric thresholds per scenario
- `ColumnManagerDialog` — browse raw columns (with descriptions) + create/edit computed columns
- `ComputedColumnEditor` — sub-dialog for defining computed columns (average, max, min, spread, difference, sum)

**UI layout:**
```
┌─ summary bar ────────────────────────────────────────────────────────────┐
│  N CRITICAL  N WARNING  N WATCH  N OK   [Filter] [Rules] [Thresholds]   │
│                                          [Columns] [Custom]             │
├──────────────────────────────────────────────────────────────────────────┤
│  scrollable list of FindingCard widgets (sorted by severity)             │
│  Each card: colored header + summary + expandable Evidence/Recommendation│
└──────────────────────────────────────────────────────────────────────────┘
```

### 9.7 Recommendation System

Every scenario's `run()` method contains detailed, per-severity "POSSIBLE CAUSES" recommendations. For example, SI-1 (Negative Subcooling) CRITICAL lists 7 numbered root causes:
1. Sensor error, 2. Pressure sensor, 3. Wrong refrigerant, 4. Massive undercharge, 5. Non-condensables, 6. Water GPM too low, 7. Water inlet temp too high

These recommendations are sourced from `run()` even when expression evaluation is used (via the patching mechanism in `run_all_diagnostics()`).

### 9.8 Data Available for Diagnostics

From `processed_df` (computed by Calculations tab):
- **Pressures:** `P_suction`, `P_disch` (PSIG); `P_suc` / `P_cond` (Pa internal)
- **Temps:** `T_2b` (comp inlet), `T_3a` (comp outlet), `T_3b` (cond inlet), `T_4a` (cond outlet)
- **Water:** `T_waterin`, `T_waterout`
- **Saturated temps:** `T_sat.comp.in`, `T_sat.cond`
- **Superheat:** `S.H_total` (at comp inlet), `S.H_{ab} coil` (per module, at coil outlet)
- **Subcooling:** `S.C` (at cond outlet), `S.C-txv.{ab}` (at TXV inlet per module)
- **Enthalpies:** `H_comp.in`, `H_coil {ab}`, `H_txv.{ab}`, hidden h_2b/h_3a/h_4a/h_4b cols
- **Mass flow:** `m_dot` (lb/hr); **Capacity:** `qc` (BTU/hr)
- **Hidden enthalpy columns:** `h_2b` (comp inlet), `h_3a` (comp outlet), `h_3b` (cond inlet), `h_4a` (cond outlet) — all kJ/kg

---

## 10. Session History

### Sessions 1-3: Cassette + Dynamic Label Refactor
- Converted all hardcoded Left/Center/Right references to dynamic `module_labels`
- Added cassette system type (independent compressor per unit)
- Refactored calculation_engine, calculation_orchestrator, calculations_widget
- Added data migration for legacy column names

### Session 4: RPM Fix + Diagnostics Brainstorm
- Fixed RPM column for fixed-speed compressors (shows `---` gracefully)
- Brainstormed diagnostics tab architecture

### Sessions 5-6: Diagnostics Engine Implementation
- Built `diagnostics_engine.py` with 29 scenario classes
- Built `diagnostics_widget.py` with FindingCard UI, ThresholdsDialog
- Expression-based evaluation system
- Custom scenario support (user-defined rules via JSON)

### Session 7: Visual Rule Builder + Recommendation Deep Dive
- **Removed all advanced/free-text expression mode** — now fully visual dropdowns
- Added two-column functions: `diff_mean`, `abs_diff_mean`, `pressure_ratio`
- Added "AT LEAST N of M" join mode (for RF-1 multi-signal scenarios)
- Converted all 25 expression-based rules from free-text to structured conditions
- Added `ColumnManagerDialog` (raw column browser + computed columns)
- Added `ComputedColumnEditor` (average/max/min/spread/difference/sum)
- **Recommendation deep dive**: Expanded ALL 29 scenarios with comprehensive root cause lists (6-8 numbered POSSIBLE CAUSES per severity level), covering sensor errors, mechanical failures, water-side issues, electrical, refrigerant-side, etc.
- Regenerated `rules_config.json` in v2.0 format (zero `advanced_expression` keys)

### Session 8: Recommendation Display Fix
- **Bug found**: Expression-evaluated rules showed DESCRIPTION text in the "Recommendation" section instead of the detailed "POSSIBLE CAUSES" text. Root cause: `_evaluate_rule()` used `scenario.DESCRIPTION` as the recommendation field.
- **Fix**: Added recommendation patching in `run_all_diagnostics()` — after expression evaluation fires a non-OK finding, the scenario's `run()` method is called to extract the proper recommendation text, which is then patched into the Finding object.
- Result: All 25 expression-evaluated scenarios now show their detailed per-severity recommendations.

### Session 9: Refrigeration Simulator Accuracy + Steady-State Cycle Solver

**HTML Simulator (`refrigeration_sim_v3.html`) — Complete Overhaul:**
- Replaced entire R290 saturation table with CoolProp-verified data (35 points, pressures within 0.1%, enthalpies within 0.3%)
- Added `cpLiquid(T_F)` interpolation for subcooled liquid Cp (was hardcoded 1.8, now 1.456–1.770 based on temperature)
- Added vapor density table `rhoVapSat(T_F)` for mass flow
- Fixed gamma from 1.14 → 1.22 (R290 actual Cp/Cv)
- Replaced ideal-gas compression with real-gas corrected model (correction factor 0.51 validated across PR=2–4)
- Added mass flow, capacity (BTU/hr, tons), COP, enthalpy map to header metrics and info panel
- Validated against CoolProp: T_disch within 2.5°F, COP within 3%, flash quality within 0.6%

**New File: `cycle_solver.py`** (~470 lines)
- Steady-state vapor compression cycle solver for R290 (and any CoolProp refrigerant)
- Solves 2-unknown system (T_evap, T_cond) using scipy.optimize.fsolve
- **Residual eq 1:** Evaporator energy balance: m_dot*(h1−h4) = UA_evap*(T_air − T_evap)
- **Residual eq 2:** Mass-flow balance: m_dot_compressor = m_dot_TXV
- Condenser modeled via NTU-effectiveness method (exact for constant-T condensation)
- Key data classes: `ComponentSpecs`, `ExternalConditions`, `CycleSolution`
- `extract_specs_from_model(diagram_model)` — reads UA, Cv, η_is from component properties
- `extract_conditions_from_df(processed_df, rated_inputs)` — reads water temp/GPM, air temp from sensor data
- `compute_deviations(solution, actual, thresholds)` — predicted vs actual comparison per parameter
- `infer_root_cause(deviations)` — pattern-matches deviation signatures to fault types
- `run_cycle_prediction(diagram_model, processed_df, rated_inputs)` in orchestrator — call after batch processing

**`component_schemas.py` — New solver properties:**
- `Compressor.isentropic_eff` (float, default 0.72, range 0.4–0.95)
- `Condenser.ua_condenser` (float, default 800.0 W/K, range 50–10000)
- `Evaporator.ua_evaporator` (float, default 600.0 W/K, range 50–10000)
- `TXV.cv_txv` (float, default 0.5, range 0.01–5.0)
- These appear automatically in the component properties dialog — no new UI code needed

**`diagnostics_engine.py` — New scenario PV-1:**
- `PV1_PredictedVsActual` — 30th scenario, COMPONENT='System', Python-only
- Runs cycle solver inline if not pre-computed (uses `diagram_model` from context)
- Builds formatted evidence table: Predicted | Actual | Δ | Flag per parameter
- Calls `infer_root_cause()` → maps deviation pattern to: undercharge/TXV restriction, TXV oversized, condenser fouling, evaporator underperforming, compressor degradation
- Severity: OK (all within tol) → WATCH (1-2 moderate) → WARNING → CRITICAL
- `DiagnosticContext` extended with `cycle_prediction: CycleSolution | None` and `diagram_model: dict`
- `run_all_diagnostics()` extended with `diagram_model=` and `cycle_prediction=` params (backward-compatible)
- Auto-runs solver if `diagram_model` provided but `cycle_prediction` is None
- `diagnostics_widget.py` now passes `model` as `diagram_model=` to `run_all_diagnostics()`

**`calculation_orchestrator.py` — New helper:**
- `run_cycle_prediction(diagram_model, processed_df, rated_inputs)` — call after `run_batch_processing()` to pre-compute the cycle prediction for passing to diagnostics

### Session 10: CAD-Style Pipe Route Engine (2026-06-09)

**Complete remodel of pipe geometry in `diagram_components.py` (PipeItem):**
- Pipe shape is now explicit data: `pipe_data['route']` = vertex chain `[[x,y],...]` from start port to end port, saved in sessions
- **Invariants:** every segment exactly horizontal or vertical (slants impossible); first/last vertex always pinned to the ports
- Rendering = draw the polyline. All routing heuristics (exit stubs, midpoint rules, facing tests, tolerances) DELETED from paint path
- Auto-route runs ONCE to seed a new pipe (`_seed_route`); legacy `waypoints` are migrated to a route on first load, then the key is removed
- Component move → `_pin_end` stretches only the adjacent segment; rest of route stays put
- **Interaction:** drag any segment to slide it along its normal (cursor shows ↕/↔); segments touching a port auto-split by duplicating the port vertex. `WaypointHandle` class and double-click-to-add-waypoint REMOVED
- `straighten_waypoints()` (name kept for widget compat) now flattens jogs < `JOG_THRESHOLD` (15px) by leveling neighbor runs; port-pinned runs never move
- `_sanitize_route` enforces invariants: drops zero-length segments, inserts corners for diagonals, merges collinear runs
- Toolbar: "Align Ports" button nudges the smaller component (never Evaporator/Condenser/Compressor/ShelvingGrid/AirSensorArray) so facing ports line up exactly (≤20px), making pipes dead straight
- Copy/paste offsets `route` by +100 like component positions

### Session 11: Calculation Engine Fixes + New Metrics (2026-06-10)

**Physics fixes in `calculate_row_performance` (live engine):**
- Condenser balance prefers `h_3b` (measured condenser inlet) over `h_3a`, falling back to the original spec's 3a≈3b adiabatic-discharge-line assumption when T_3b unmapped
- Suction saturation now at dew point (Q=1); condenser at bubble point (Q=0) — identical for R290, correct for future blends
- `rpm` echoes to results regardless of water-balance success
- Water temp fallback uses explicit None checks (was `or`, broke on 0.0)
- `calculate_volumetric_efficiency`: 0 °F rated temps no longer treated as missing (`is None` checks)

**New hidden columns (available to diagnostics rule builder):**
- `m_dot_disp` — displacement-based mass flow (lb/hr) = ρ_2b·disp·rpm·η_vol; cross-check against water-side `m_dot`
- `qc_coils` — coil-side capacity (equal-split assumption); `Q_line_gain` = qc − qc_coils = suction-line heat gain
- `W_comp` (BTU/hr, refrigerant-side), `COP`, `EER`
- `eta_is` — isentropic efficiency from measured T_3a; primary compressor-health trend metric
- Cassette: all suffixed `-{ab}` via rename_map

**Orchestrator:** `run_batch_processing` now enriches `comp_specs` with `gather_compressor_specs()` + Step-1 `eta_vol` (clamped to [0.3, 1.0], default 0.85)

**Design rationale recovered (original spec docs deleted):** h_3a≈h_3b and qc-at-compressor (mixed-flow point is the only rigorous total-flow×enthalpy point) were deliberate spec choices, preserved as fallback/primary respectively. Cassette: each unit has its own balancing valve → per-unit gpm_water is correct as-is.

**Dead code REMOVED (Session 11b):** `compute_cycle`, `_compute_single_coil`, `compute_8_point_cycle`, `calculate_mass_flow_rate`, `calculate_system_performance`, `calculate_performance_from_compressor`, `aggregate_values`, `cm3_to_m3`, `rpm_to_rps` (engine, now 468 lines); `calculate_full_system`, `calculate_per_circuit`, `gather_temperatures_from_ports`, `gather_pressures_from_ports` (orchestrator, now 636 lines); files `coolprop_calculator.py` and `calculation_output_generator.py` deleted (the latter imported a nonexistent `CalculationOrchestrator` class); `data_manager.filter_by_pressure_threshold` + `get_on_time_filtered_data` (contradictory dead ON-filters) removed — live ON-filter is discharge-based in `calculations_widget._apply_discharge_filter`. NOTE: old scripts `test_calculations.py`, `debug_ph_diagram.py`, `extract_plot_values.py`, `test_column_names.py` reference removed code and no longer run.

**Session 11c — Measured GPM + Water-Flow Instability (user-reported averaging-masking problem):**
- New sensor role `GPM_water` → Condenser `water_flow_gpm` port (port already existed in component_schemas, never consumed). Wired into shared roles + cassette map.
- Engine: per-row measured GPM takes priority over constant rated `gpm_water`; the GPM actually used is echoed as `gpm` column (cassette: `gpm-{ab}`)
- **CD-3 `CD3_WaterFlowInstability`** (32nd scenario, Condenser, Python-only): detects averages masking instability via 3 signals — S.C sign flips ≥3 in window, qc CV >25%, measured GPM CV >10%. 2+ signals = WARNING, 1 = WATCH. Window default 60 rows.
- Rationale: varying water GPM made instantaneous S.C swing ± and qc explode while means looked normal; root cause fixed by measured GPM, CD-3 guards unmapped/unstable cases.

**Session 11d — Diagram State Overlay (Analysis mode):**
- `app.py`: `filtered_data_ready` also connected to `diagram_widget.on_processed_data` (caches column means)
- `diagram_widget.apply_state_overlay()` runs in Analysis mode after scene build: per pipe, uses `fluid_state` × `pressure_side` × `circuit_label` to pick the right computed column and flags contradictions:
  - liquid/high → FLASH GAS when `S.C-txv.{ab}` (or `S.C`) ≤ 0.5 °F
  - gas/low → FLOODBACK when `S.H_{ab} coil` (or `S.H_total`) ≤ 0.5 °F
  - gas/high → WET COMPRESSION when `T_3a − T_sat.cond` ≤ 2 °F
  - cassette columns resolved with `-{ab}` suffix; circuit_label may be the string 'None' (treated as unlabeled)
- Violations: dashed magenta pen (also replaces `_original_pen` so deselect keeps it), midpoint ⚠ label (in `overlay_items`), tooltip explanation. Healthy pipes untouched.
- Workflow: run Calculations → switch Diagram tab to Analysis mode.

**Session 11e — Finding→Diagram Locate + Sensor Pre-Flight:**
- FindingCard gains "📍 Show on diagram" button (non-OK findings) → `FindingCard.locate_requested` → `DiagnosticsWidget.locate_on_diagram` → `MainWindow.on_locate_finding` switches to Diagram tab → `diagram_widget.highlight_finding(finding)`
- `highlight_finding`: maps `Finding.component` to component types via `_FINDING_TYPE_MAP` ('Suction Line' → low/gas pipes; 'Refrigerant'/'System' → all components), parses '— Unit XX' from cassette labels to filter by circuit_label, draws 3.5s yellow halo rects (z=60), centers view
- **SQ-1 `SQ1_SensorQuality`** (33rd scenario, Sensors, Python-only): pre-flight on echoed raw sensor columns — DROPOUT (>30% NaN), STUCK (zero variance ≥20 rows), SPIKES (>6σ). Any dropout/stuck → WARNING ("other findings suspect"); spikes only → WATCH. Window 120 rows.

**Session 12 — Test Request System Phase 1 (2026-06-11):**
- Master plan lives in `TEST_REQUEST_PLAN.md` — READ IT before touching this area. Phases need per-phase user approval; plans must be pitched in plain language first.
- New: `test_request_library.py` (library/ folder of separate small JSON DBs: catalogs per part type, criteria per case, elp_codes, projects/requests; stable ids + provenance; **parts snapshot-frozen into requests**), `test_request_dialog.py` (form UI), "Test Requests" menu in app.py.
- Targets saved per case model double as the criteria source for the Phase 2 scorecard.
- Phase 1 rework: schema-driven part records (`PART_FIELD_DEFS` — every field has a consumer), supplier PN primary + optional company PN, user units in³/RPM with conversions in `compressor_to_rated_inputs()`, and "Save + Apply to session" (compressor datasheet → rated_inputs + diagram Compressor props + refrigerant + GPM).
- Phase 3 core: `diagram_from_request.py` + `templates/` (7 templates ingested from the user's hand-built diagrams at `Lab viewer/2.0/Config`: tmpl_ID5SL12/ID5SL4/ID5SL6/RLN3MA/RMN2MA/RMN3WE/RMN5MA + index.json; the earlier ID6SU12WE-derived template was deleted). "Generate process diagram" button on the request form. Nearest-match by system/modules/circuits; exact match = verbatim template; module surgery only as fallback. The user's verdict stands: never trust procedural layout — templates must come from hand-built diagrams. `build_diagram_for_request()` tags the returned model with transient `'_generated_from'` (template file + source); both callers pop it and show it in their success dialogs.
- §5b handoff bug FIXED (2026-06-11): the 🆕 New slot ended with a `print` referencing undefined `config_key` (wizard leftover) → `NameError` in a Qt slot → PyQt6 aborted the app right after swapping the model; relaunch restored the old diagram, which looked like "old templates loading". Templates were always faithful to 2.0/Config.
- Diagram tab "🆕 New" button REWIRED to the same automatic path (uses the most recent test request, one confirm, zero picking). The old `NewDiagramWizard`/`diagram_template_loader` file-picker flow is no longer reachable from the UI — `new_diagram_wizard.py`, `diagram_template_loader.py`, `diagram_template_patcher.py`, `diagram_templates.py` are legacy (procedural fallback only).

**Session 11b additions:**
- **CP-7 `CP7_MassFlowCrossCheck`** (31st scenario, Compressor, Python-only): compares `m_dot` vs `m_dot_disp`, |dev|>15% WATCH, >30% WARNING, direction-specific recommendations; silent when m_dot_disp unavailable
- **"Exclude defrost" checkbox** in Calculations control row → `_apply_defrost_exclusion()`: drops rows where |DP−SP| ≤ 10 psi before batch processing
- New perf columns added to reindex whitelist (`_perf_cols` in `run_calculation`) and to the calculation summary tables (shared + cassette)

### Session 13 — Canonical Sensor Naming + Auto-Map (2026-06-15)

**The problem:** Each CSV has ~150 columns; manual mapping = 150 clicks. Worse, generated diagrams had no off-diagram sensor slots (Ambient/Walls/Electrical), so wall temps and electrical sensors had no home.

**New file: `sensor_canonical.py`** — Pure function `canonical_for_port(comp_type, props, port, unit_tag='')` → `(canonical_id, human_label)`. Stable ASTM-style naming across all 7 case families:
- Refrigeration: `T_suc.in`, `T_disc.out`, `P_suc`, `P_disc`, `T_cond.in/out`, `T_w.in/out`, `gpm_w`, `T_txv.{lh|ctr|rh}.in/bulb`, `T_dist.{tag}.in/out.{N}`, `T_coil.{tag}.in/out.{N}`
- Air arrays (dynamic N): `T_air.disc.s{N}`, `T_air.sec.s{N}`, `T_air.ret.s{N}` (curtain types `Primary/Secondary/Return` also dispatch as role_key prefixes)
- Fan: `T_air.fan_{in|off}.{tag}.{LE|RE}` (2-sensor) or `.s{N}` (more)
- Product sims: `T_prod.{row_id}.{col_id}.{r|f}` — rows `top/r2/r3/.../btm` from `shelf_rows`; cols `LE/LE48/RE48/RE` (4-col) or `LE/Ctr/RE` (3-col), with `col_distances` template override
- Cassette unit suffix: `.u1`, `.u2` everywhere (in addition to circuit-label tags)
- `resolve_canonical_from_role_key(model, role_key)` handles ALL role_key shapes: 3-part `Type.cid.port`, 2-part legacy `cid.port` (looks up type), curtain-type prefix, `sensorbox.boxid.sensor_id`, and `custom_xxx` returns None

**Auto-added sensor boxes** (in `diagram_from_request.py:_ensure_canonical_sensor_boxes`): every generated diagram now ships with two canonical boxes:
- `box_ambient_walls` — 9 slots: `T_amb.dry.a/b`, `T_amb.wet`, `T_wall.front/rear/left/right`, `T_ceil`, `T_evap_misc`
- `box_electrical_system` — cassette-aware via `electrical_system_slots(n_compressors)`: `W_case`, `A_case`, `V_case`, `W_fan`, `A_fan`, `W_aswt`, `A_aswt`, `W_frame`, `A_frame`, `t_run`, `f_defrost`, `f_alwaysoff`, `m_dot_meas`, `T_liq.main`, and per-compressor `W_comp.uN`/`A_comp.uN`/`V_comp.uN`
- Slot IDs ARE the canonical names; `_looks_like_canonical()` recognizes them and returns directly without label-pattern matching

**Alias DB** (`library/sensor_aliases/seed.json` + `learned.json`): 179 canonicals, 420+ aliases seeded by walking all 7 historical configs' `sensor_roles` → CSV name pairs. `learned.json` grows every time `map_sensor_to_role` is called — confirmed mappings save the CSV name as a new alias for that canonical.

**Auto-map on CSV load** (`data_manager.auto_map_csv_to_canonical`): after `load_csv` ingests new columns, walks them against `_load_alias_db()` (seed + learned). Exact match → auto-map; normalized match (`normalize_for_match` strips spaces/punctuation/case) → auto-map; unknown → user maps once and it's learned.
- **96% auto-map rate** on ID5SL12 (142/147 CSV columns). The 5 misses are all computed/derived (S.H., Liqcond, AVG Prod Temp) which are calc-engine outputs, not raw sensors.

**Role-key enumeration** (`data_manager._enumerate_diagram_role_keys`): yields every possible role on the current diagram, including DYNAMIC ports not in static schema — ShelvingGrid (`sensor_r{0..R-1}_{top|bottom}_c{0..C-1}`), Fan (`sensor_{0..N-1}`), AirSensorArray (both `{Curtain}Air.cid.{i}` and `AirSensorArray.cid.{i}` forms), plus sensor-box slots.

**Tooltip on dots** (`diagram_widget._add_role_dot`): shows `<b>{canonical_id}</b><br>{human_label}<br>Mapped: {csv_name}` (or "Unmapped") + click hints. Falls back to legacy port tooltip when canonical resolution fails.

**Files added/changed this session:**
- NEW: `sensor_canonical.py` (~280 lines)
- NEW: `library/sensor_aliases/seed.json` (179 canonicals)
- NEW: `library/sensor_aliases/learned.json` (grows over time)
- `data_manager.py`: `auto_map_csv_to_canonical()`, `_enumerate_diagram_role_keys()`, `_load_alias_db()`, `_save_learned_alias()`, alias save on `map_sensor_to_role`
- `diagram_from_request.py`: `_ensure_canonical_sensor_boxes()` injected into both template and reduction paths
- `diagram_widget.py`: tooltip rewrite to lead with canonical + human
- `component_schemas.py`: added SP/DP/RPM sensor ports to Compressor (earlier in session)

**One-shot seed scripts (run when alias DB needs refresh):**
```python
# Inline in any debug session
from sensor_canonical import resolve_canonical_from_role_key
from collections import defaultdict
import json, os
aliases = defaultdict(set)
for fn in os.listdir(r'C:\Users\silam\OneDrive\Documents\Lab viewer\2.0\Config'):
    with open(os.path.join(CONFIG_DIR, fn)) as f: cfg = json.load(f)
    dm = cfg.get('diagramModel', {})
    for rk, csv in (dm.get('sensor_roles') or {}).items():
        res = resolve_canonical_from_role_key(dm, rk)
        if res: aliases[res[0]].add(csv.strip())
# Then dump to library/sensor_aliases/seed.json
```

---

## 11. Quick Syntax Check
```bash
cd "C:\Users\silam\OneDrive\Documents\Lab viewer\HVAC_Dev"
python -m py_compile circuit_semantics.py data_manager.py diagram_template_loader.py calculation_orchestrator.py calculation_engine.py ph_diagram_generator.py calculations_widget.py diagnostics_engine.py diagnostics_widget.py cycle_solver.py component_schemas.py && echo ALL OK
```

---

## 12. Do NOT Hardcode
- Module labels (`'Left'`, `'Center'`, `'Right'`) — use `get_all_module_labels(model)`
- Abbreviations (`'lh'`, `'ctr'`, `'rh'`) — use `module_abbrev(label)`
- Column lists — derive from labels using the `_build_header_data*` functions
- `['LH', 'CTR', 'RH'][i]` index tricks — use dict keyed by label instead
- Number of modules (e.g. `range(3)`) — use `len(module_labels)`

---

## 13. When to Update This File
Update at the END of any session where you:
- Add or rename a column used in the table, audit text, or summary
- Add a new system type (beyond `shared` / `cassette`)
- Add a new file to the pipeline
- Change a public API function signature
- Change column naming conventions
- Add new diagnostic scenarios
- Change the rule evaluation architecture
- Add new UI dialogs or major widget changes
- Add new sensor roles or component types

---

## 14. Claude Agent Usage Notes

- **Background agents (`run_in_background: true`):** Output file is always 0 bytes — DO NOT try to `Read` it. Results arrive automatically as `<task-notification>` in the conversation when the agent completes. Just wait.
- **Parallel blocking agents:** Launch multiple Task calls in a single message without `run_in_background`. Results return directly in tool output. Preferred for research tasks.
- **Subagent token efficiency:** Do ONE thorough explore pass, then write findings to CLAUDE.md or the plan file. Do NOT re-explore the same files in multiple agents.
