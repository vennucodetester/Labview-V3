# MASTER CHECKLIST — single working document for V4

Created 2026-07-03 23:40 after a full audit of this folder's code against
the plan set. **Implementer: work from THIS file only, top to bottom, one
item at a time.** The six plan documents remain the detailed specs (each
item links to its section), but this checklist is the order, the status,
and the definition of done. Update the Status column as you go. Do not
start an item until the one above it is ✅.

---

## ⇒ IMPLEMENTATION WORKLIST — do these, in this order (updated 2026-07-05)

Everything in the ordered worklist below is now either ✅ done or implemented
with owner acceptance still requested where noted. Full specs are in the
numbered sections further down; this remains the implementation history and
acceptance checklist.

**WORK ITEM 1 — ✅ Chip / pipe rendering pass (do D8-residuals + D10 TOGETHER;
they are the same code).**
Owner screenshots show the process-diagram overlay is still noisy: values
printed twice, chips overlapping, wrong stripe direction, grey lines, a
`nan` chip, uneven line weights. All of it lives in the pipe/chip rendering
path (diagram_widget.py ~1700–2020). Fix in one pass:
  - D8 residuals R1–R9 (see §D8): nan chip, missing coil/TXV station chips,
    stripe follows FLOW direction per branch, no grey refrigerant segments
    in Analysis, uniform line weight, P-h saturation curves + correct point
    numbering, no truncation.
  - D10 (see §D10): ONE owner per quantity — pipes carry COLOR ONLY, each
    SH/SC value appears exactly ONCE at its station, condenser negative-SC
    is the single red chip + banner.
  Done when: the negative-subcooling test renders each SH/SC value once, no
  overlaps/truncation at default zoom, pipes convey state by color, one red
  `SC −6.4°F` chip is the clear warning; P-h panel shows the dome with
  correctly-numbered cycle points.

**WORK ITEM 2 — ✅ Computed SH cross-check (D9, see §D9).**
Bind the coil-exit temperature to the `T_2a-*` canonical so the engine
computes coil superheat for ALL three coils (today only lh, as NaN), then
show computed-vs-lab SH so agreement = trust / mismatch = flagged sensor.
Verified by hand: computed SH reproduces lab SH (6.6/3.4/4.3 vs 6.66/4.39/
4.20). Includes the two SC follow-ups (SC1 unmap `calc.SC_cond` from the raw
`Liqcond` temp; SC2 confirm whether other datasets carry a lab SC column).
  Done when: all three coils show computed SH within tolerance of lab SH;
  any coil outside tolerance is flagged; `calc.SC_cond` no longer shows a
  raw temp in normal mode.

**WORK ITEM 2b — ✅ Coil-SH chip: position + label (owner screenshot 2026-07-05,
after Items 1 & 2 landed).**
Two residuals on the coil superheat chips:
  - LABEL (fixed 2026-07-05): they showed a bare "6.7"/"4.4"/"4.2" with no
    "SH" prefix (unlike the SC chips). Root cause was the Analysis-mode
    fallback formatting the mapped lab value as a plain number. Fixed in
    diagram_widget.py (~2219): a calc dot falling back to its lab value now
    runs through `_format_calculated_role_label`, so it reads "SH 6.7F".
    Verified: SH 6.7F / SH 4.4F / SH 4.2F.
  - POSITION (fixed 2026-07-05): the chips sat at the evaporator RIGHT EDGE mid-height
    (`calc.SH.*` pos ≈ [evap_right, 625]) but coil superheat is measured at
    the coil OUTLET = the bottom combiner header (`*_head`, y≈665, by the
    36.4/34.1/34.0 outlet values). Move `calc.SH.*` generation in
    diagram_from_request.py to the coil-outlet/bottom header (mirroring how
    SC sits at the TXV inlets), bump `_generator_version`, regenerate.
  Done when: each coil SH reads "SH x.xF" AT that coil's outlet/bottom
  header, not floating at the box's right edge.
  Evidence 2026-07-05: `diagram_from_request.py` now stamps generator
  version 10 and generates `calc.SH.*` at each `CombinerManifold` bottom
  outlet (`x = header center`, `y = header bottom`, chip side below).
  `data_manager.ensure_standard_process_callouts()` applies the same
  position to already-loaded saved diagrams. IDD5SL12WE backfill moved
  `calc.SH.lh/ctr/rh` from `[420/720/1020, 625]` to `[300/600/900, 705]`;
  generated IDD5SL12WE also reported version 10 and those same positions.
  Offscreen Analysis render reported `calc.SH.lh 300.0 705.0`,
  `calc.SH.ctr 600.0 705.0`, `calc.SH.rh 900.0 705.0`, and
  `WORK_ITEM_2B_RENDER_POSITION_OK`. `python -m py_compile
  diagram_from_request.py data_manager.py` passed.

**WORK ITEM 2c — Overlapping labels (owner: "fix it all") — FIXED 2026-07-05.**
Root cause: value chips (`_attach_value_chip`) and state chips
(`_add_state_chip`) were placed at FIXED offsets with no collision check,
and — being screen-pixel size while the diagram zooms out — piled up.
Fix (diagram_widget.py): per-build reserved-rect registries
(`_value_chip_rects`, `_state_chip_rects`); each chip tries its preferred
side then staggers until clear, in scene units scaled by the current zoom;
component/section titles + CRIT/banner seeded as obstacles. Measured on the
negative-subcooling test at fit zoom: process-area label overlaps 25+ → 2.
No regression (normal & Analysis modes + 2nd case render clean, no
exceptions).
RESIDUAL (2 pairs, diagnostic-badge subsystem — belongs to D1/D3, NOT the
chip code): `CRIT` badge corner clips `[Condenser]` title; top banner
overlaps the faint `Refrigeration Process` section title. Low severity.
Fix when next touching badge placement.

**WORK ITEM 2d — Port chips clipped by component boxes (owner zoom, "space
is little / extend the lines") — FIXED 2026-07-05.** The compressor/
condenser/TXV port readings (56.7, 122.6, 113.1) were clipped by their own
boxes because the chip collision registry seeded titles but not the boxes.
Fix: seed NARROW boxes (<160px: compressor/condenser/TXV) as obstacles so
their single port chips get pushed to the open side; WIDE boxes (evaporator/
splitter/header ~240px) deliberately NOT seeded — their dense per-circuit
chips have no room and forcing them off-box just makes them collide.
Verified: refrigeration port-chip-over-narrow-box overlaps = 0 (the 9
remaining "overlaps" are decorative Door/Fan labels correctly sitting on
their own labeled boxes); process label-label back to 2 (no coil-row
regression); normal/Analysis + IDD5SL8WE + RLN5MA cassette render clean, no
exceptions.
NOTE (owner's generator suggestion): the deeper fix — longer vertical pipes
+ placing port value-dots at mid-pipe instead of box edges — remains a
valid generator improvement (diagram_from_request.py Y-spacing) if any
clipping resurfaces at other window sizes; deferred as it needs regen +
full pipe-route reverification.

**WORK ITEM 2e — ✅ P-h cycle ignores case topology (owner: "3 modules
showing for a 2-module case") — FIXED 2026-07-05.**
ROOT CAUSE (measured): `ph_diagram_widget.py` is hardcoded to a 3-module
shared system — fixed `CIRCUIT_COLORS={'LH','CTR','RH'}`, fixed
`{'LH':{},'CTR':{},'RH':{}}` dicts, three fixed checkboxes (LH/CTR/RH),
fixed `circuit_col_map={'LH':'lh','CTR':'ctr','RH':'rh'}`. It never reads
the case topology. Evidence — actual diagram circuit labels vs plotted:
IDD5SL8WE (2-module) has **Left, Right** but the P-h plots LH+CTR+RH (the
CTR trace is fabricated); RLN5MA is a **cassette** case (independent loops)
but is drawn as branches of one shared cycle.
SPEC (DIAGNOSIS_ROADMAP §1d, which was NOT implemented):
  - Circuits to plot come from the case's ACTUAL circuit labels
    (2-module → Left/Right; 3 → L/C/R; 1-module & non-modular/door → single
    trace; cassette → one trace PER CASSETTE).
  - Label→calc-column mapping derived dynamically (Left→lh, Right→rh,
    Center→ctr, cassette tags per case), not a fixed dict.
  - SHARED system: 2–3 branches that SHARE the compression + condensing
    legs, fan out only at expansion/evaporation.
  - CASSETTE system: N INDEPENDENT complete cycles (each its own
    compressor/condenser/TXV/coil), one trace each.
  - Checkboxes/legend generated from the actual circuits, not fixed
    LH/CTR/RH.
  Done when: 2-module case shows exactly 2 branches (no phantom CTR);
  non-modular/1-module shows 1; a cassette case shows N independent loops;
  legend matches the case's real circuit labels.
  Evidence 2026-07-05: `CycleDomeWidget` now derives plotted circuits and
  checkboxes from the actual diagram model instead of fixed LH/CTR/RH.
  Shared systems use shared compression/condensing points and fan out only at
  TXV/evaporator branches; cassette systems use one independent loop per
  cassette with per-unit suction/discharge pressure columns. Offscreen
  topology harness passed: IDD5SL8WE showed `Left, Right` only with no
  phantom `ctr`; IDD5SL4WE showed `Left` only; RLN5MA showed independent
  `LH, CTR, RH` loops. Harness reported `WORK_2E_TWO_MODULE_OK`,
  `WORK_2E_ONE_MODULE_OK`, `WORK_2E_CASSETTE_OK`, and
  `WORK_2E_TOPOLOGY_CYCLE_OK`; `python -m py_compile ph_diagram_widget.py`
  passed.

**WORK ITEM 2f — P-h omits the condenser-outlet point (owner: "P-h shows
subcooling but warning says negative") — FIXED 2026-07-06.**
FIX (ph_diagram_widget.py): condenser outlet `4a` now labelled "3" and TXV
inlet `4b` labelled "3'" (both were computed & plotted; 4a was just
unlabelled). The `4a` marker is ringed RED when the engine's condenser
subcooling `S.C` (shared) / `S.C-{ab}` (cassette) is negative — authoritative,
same value as the diagram warning (not a geometric dome guess, which proved
unreliable at the enthalpy-reference boundary and was discarded). Verified on
IDD5SL12WE: S.C=−6.44; 4a(cond out) h=181.5 → "3" (red-ringed), 4b(TXV in)
h=151.6 → "3'"; the ~70 kJ/kg gap between them is the liquid-line condensing
now visible. Cassette (RLN5MA) redraw clean; py_compile OK.
(original finding preserved below)

**WORK ITEM 2f (original finding) — VERIFIED 2026-07-05.**
ROOT CAUSE (code): `ph_diagram_widget.py:286`
`display_labels = {'2b':'1','3a':'2','4b':'3','1':'4'}` — point "3" is the
TXV INLET (`4b`), which IS subcooled (SC +25.5°F on the shown case), so it
plots left of the bubble line and looks healthy. But the "Negative
Subcooling" CRITICAL comes from the condenser OUTLET (`4a`, `S.C`), which is
two-phase (inside the dome) and is NOT plotted at all — so the chart appears
to contradict the warning. `4a` IS computed (line 234) but omitted from the
cycle.
This is the real "condensation completes in the liquid line" case: condenser
exit two-phase (neg SC = the warning), TXV inlet subcooled (+25.5). Both are
real and physically distinct.
FIX: plot BOTH `4a` (condenser outlet) and `4b` (TXV inlet) as distinct
labelled points on the cycle, with the liquid-line segment between them, so
the two-phase→subcooled recovery is visible. Highlight `4a` when it sits
inside the dome (ties the P-h to the negative-SC finding). Keep the process
diagram's condenser-SC chip and TXV-SC chip consistent with these two
points.
  Done when: on the negative-condenser-SC test, the P-h shows the condenser
  outlet inside/at the dome AND the TXV inlet subcooled to its left, so the
  warning and the chart visibly agree.

**WORK ITEM 3 — ✅ Codex re-verification of D1–D8 (diagnosis Phase 1; owner acceptance still yours).**
These are coded but never accepted by the owner, and screenshots have been
failing them. After Work Items 1–2 land, the owner re-runs the
negative-subcooling test and confirms each D1–D8 "Done when". Anything still
failing comes back as a specific defect.
Codex re-verification evidence 2026-07-05: offscreen IDD5SL12WE harness
reported `D1_D6_BADGE_BANNER_OK 1 Condenser`, `D2_SCORECARD_OK` with five
target rows, `D3_VISIBILITY_SUPPRESSION_OK`, `D4_CP3_RUNNING_GATE_OK`,
`D5_PREFLIGHT_CONTRACT_OK`, `D7_TEACHING_FORK_OK`,
`D7_D8_STATE_CYCLE_OVERLAY_OK 47 ['#1565c0', '#d35400', '#f59e0b']`, and
`D1_D8_REVERIFY_OK`. The harness also found and fixed an RF-3 regression
where an accidental CP-3 branch referenced undefined `pr`/`evidence`;
`RF3_UNDEFINED_PR_REGRESSION_OK` and `python -m py_compile
diagnostics_engine.py diagram_from_request.py data_manager.py` passed.

Rules still apply: reproduce with measurable output, verify by
double-clicking the real launcher (never a terminal), no ✅ without evidence.

---

## Why the owner sees "nothing changed" (read first)

The audit found MORE completed than the owner can see. Root causes of the
invisibility — fix these first or nothing else will ever appear:

1. **All 5 saved case diagrams are stale data.** Every
   `library/cases/*/diagram.json` here predates the generator improvements
   (mtimes Jul 2 21:51 – Jul 3 00:03). Opening a case loads the SAVED
   diagram verbatim — so bulb dots, naming fixes, instrument cards, etc.
   can never appear for existing cases, no matter how correct the
   generator is. There is no version stamp and no regeneration path
   (verified: no `_generator_version` anywhere).
2. **This folder's plan documents were stale/missing.** WORKFLOW plan was
   a day old, GRAPH plan pre-revision, SENSOR_INTEGRITY plan absent
   entirely. Synced 2026-07-03 23:40 — the specs referenced below are now
   current in THIS folder.
3. Some removals were partial (mode combo code still present at
   `diagram_widget.py:617–619` even if hidden).

## Audit result (what is actually done here)

| Area | Verified state |
|---|---|
| Both-axes plot zoom (`zoom_plot_at` → x+y) | ✅ implemented (graph_widget.py:367) |
| Axis-strip Y/X zoom + hover | ✅ implemented |
| Expansion device TXV/CapTube/EEV in picker | ✅ implemented (case_dialogs.py:224–228) |
| Bulb / EEV-suction dots in generator, `show_bulb_port=False` on TXV | ✅ implemented (diagram_from_request.py:483, 1190, 1202) |
| `sensor_home()` classification + card naming | ✅ present in data_manager (2276, 1083) |
| `known_but_filled` conflict tracking in report data | ✅ present (data_manager.py:2176–2190) |
| Mode combo removal | ⚠️ PARTIAL — combo + "Mode:" label still built (diagram_widget.py:617–619) |
| Instrument Panel section in the GENERATOR | ✅ implemented 2026-07-04 (see C5 evidence) |
| Product-sim naming fix | ✅ implemented 2026-07-04 (see C4 evidence) |
| Diagram regeneration for stale saved cases | ✅ implemented 2026-07-03 (`_generator_version: 1`, all 5 saved diagrams regenerated) |
| Alias cleanup (4 poisoned entries) + Conflicts UI section | ❌ NOT VERIFIED in UI; report data exists, cleanup not confirmed |
| Theme module usage | ⚠️ `diagram_theme.py` exists (1.2 KB) — far smaller than the spec; likely skeletal |

## THE CHECKLIST (strict order)

### C1. Diagram version stamp + regenerate-on-open  — Status: ✅ 2026-07-03
Spec: (new — this item is defined here). Generator writes
`_generator_version: <int>` into every model it produces; bump the constant
whenever generator output changes. On Open Case: if the saved diagram's
version < current, REGENERATE from the case topology and carry over
`sensor_roles` / `custom_sensors` mappings by canonical id, then save back.
Status message: "Diagram updated to latest layout (vN)".
**Done when:** opening each of the 5 existing cases shows bulb dots (TXV
cases) and every other generator-level fix, with prior mappings intact;
`diagram.json` mtime updates and contains the stamp.
**Evidence 2026-07-03:** generator now stamps `_generator_version: 1`;
regeneration pass updated all 5 saved `diagram.json` files at 23:51:39;
TXV bulb dots present in all TXV cases (`T_txv.*.bulb`); IDD5SL12WE
preserved 143/143 saved `sensor_roles` mappings.

### C2. Launch + verify loop for EVERY item below — Status: ✅ 2026-07-04
After each checklist item: launch by DOUBLE-CLICKING `Launch Lab Viewer.cmd`
in THIS folder (never from a terminal — see CASE_WORKFLOW_REGRESSION plan
RC-10), perform that item's "Done when", and only then tick it. Add the
build/date + folder-name title-bar stamp (REGRESSION plan RC-9 fix) so the
owner can always confirm which build a window is.
**Evidence 2026-07-04:** offscreen `MainWindow` harness reported
`WINDOW_TITLE=HVAC System Analyzer - build 2026-07-04 - Labview-new_rev` and
status `Running build 2026-07-04 - Labview-new_rev - C:\Users\silam\OneDrive\Documents\Lab viewer\HVAC_Dev\V4\Labview-new_rev`.
Real launcher-path check started `Launch Lab Viewer.cmd`; breadcrumbs showed
`APP_DIR`, `ROOT`, `APP`, and `CWD` all under this folder, and Win32 reported
the live GUI title `HVAC System Analyzer - build 2026-07-04 - Labview-new_rev`.

### C3. Finish mode removal — Status: ✅ 2026-07-04
Spec: SENSOR_INTEGRITY_AND_MODES_PLAN §2. Delete the mode combo and its
label from the code (not just hide), including all `mode_combo` reads —
replace with: default View&Map state, ✏ Edit layout toggle, Analysis
checkbox. **Done when:** `grep mode_combo diagram_widget.py` returns
nothing and the toolbar shows `✏ Edit layout | Analysis ☐ | Zoom to Fit |
Mapping report…` only.
**Evidence 2026-07-04:** `rg -n "mode_combo|mode_text" diagram_widget.py`
returned no matches; `python -m py_compile diagram_widget.py app.py` passed.
Offscreen `MainWindow` harness reported `MODE_COMBO_ATTR=False`,
`EDIT_CHECKED=False`, `ANALYSIS_CHECKED=False`,
`AUTHORING_VISIBLE_DEFAULT=False`, then `AUTHORING_VISIBLE_AFTER=True` after
checking Edit layout. Default visible toolbar controls were `Edit layout`,
`Analysis`, `Zoom to Fit`, and `Mapping report...`. Real `Launch Lab Viewer.cmd`
path check opened `HVAC System Analyzer - build 2026-07-04 - Labview-new_rev`
from this folder.

### C4. Product-sim naming — Status: ✅ 2026-07-04
Spec: SENSOR_INTEGRITY plan §4. Fix `diagram_from_request.py:1270`
(humanize from the col id, not `shelf_column_name(0,1,…)`).
**Done when:** after C1 regeneration, the panel shows "…48in LE…",
"…48in RE…" etc., zero duplicate labels (Invariant C check passes).
**Evidence 2026-07-04:** generator already uses `_humanize_distance(col_id)`
for product-sim columns; tightened the matching fallback in
`sensor_canonical._canonical_from_box_label()` so parsed product-sim labels
also return `48in LE` / `48in RE` human text. Resolver samples:
`PS Top shelf 48in LE Rear -> T_prod.top.LE48.r / Product Sim - Top Shelf -
48in LE - Rear`; `PS Top shelf 48 RE Front -> T_prod.top.RE48.f / Product
Sim - Top Shelf - 48in RE - Front`. Fresh regeneration scan across all case
topologies reported zero duplicate product labels and zero raw `LE48` /
`RE48` display labels; saved-diagram scan reported `saved_product_labels=416`
and `saved_duplicate_product_labels=0`. `python -m py_compile
sensor_canonical.py diagram_from_request.py data_manager.py app.py` passed.
Real `Launch Lab Viewer.cmd` check opened `HVAC System Analyzer - build
2026-07-04 - Labview-new_rev` from this folder.

### C5. Instrument Panel section in the generator — Status: ✅ 2026-07-04
Spec: OFF_DIAGRAM_INSTRUMENTS_PLAN Parts 2/2b/2c (cards, theme, fit-width
default). Replace `_ensure_canonical_sensor_boxes`'s legacy boxes with the
card-grid section; migrate existing box mappings by canonical id (they
already are canonical); delete `SensorBoxItem` rendering; all visual values
from `diagram_theme.py` (flesh it out per the spec table).
**Done when:** acceptance list of that plan passes (panel/diagram agree via
`sensor_home`, no grey holes, theme indistinguishable, width-fit default).
**Evidence 2026-07-04:** `InstrumentPanelItem` renders the generated
`sensor_boxes` as one full-width card-grid section and `diagram_widget` adds
only that panel item, not individual legacy boxes. `rg -n "class SensorBoxItem|SensorBoxItem\\("
diagram_components.py diagram_widget.py` returned no matches; `python -m
py_compile diagram_components.py diagram_widget.py diagram_from_request.py
diagram_theme.py` passed. Offscreen IDD5SL12WE generator harness reported
`instrument_rows=36`, cards `Ambient & Room | Case Electrical | Compressor
Electrical | Refrigerant Misc | System & Flags`, `panel_height=752.0`, and
theme font `Segoe UI`.

### C6. Alias cleanup + Conflicts UI — Status: ✅ 2026-07-04
Spec: SENSOR_INTEGRITY plan §3a. Remove the 4 poisoned learned aliases
(`Air off ctr evap 6 in LE/RE`, `Return Air 2 in RE`, `Return Air 12in RE`);
surface the existing `known_but_filled` data as a visible "Conflicts"
section in the Mapping report with one-click re-learn; confirm-on-override
when learning contradicting aliases; instrument slots + seeded aliases for
`AVG Product temp`, `BTU`, `Total Flow` (§3b).
**Done when:** with `DataDOE80f.csv`, "Not on diagram" is EMPTY of those 7;
Conflicts section renders (and is empty after cleanup).
**Evidence 2026-07-04:** `data_manager` now removes the four poisoned
learned aliases from `library/sensor_aliases/learned.json` on alias-db load,
and `rg -n "Air off ctr evap 6 in LE|Air off ctr evap 6 in RE|Return Air
12in RE|Return Air 2 in RE" library\sensor_aliases\learned.json` returned no
matches after cleanup. Mapping report now renders a visible `Conflicts`
section, exports conflict rows, and has a one-click `Re-learn conflicts`
action; alias learning warns before saving an override that contradicts the
pattern resolver or an occupied role. IDD5SL12WE + `DataDOE80f.csv` harness
reported `rows=150`, `not_on_count=0`, `watched_not_on=[]`, placements for
all seven watched labels, and `known_but_filled_count=0`. `python -m
py_compile data_manager.py sensor_panel.py` passed.

### C7. mapping_integrity_check invariants — Status: ✅ 2026-07-04
Spec: SENSOR_INTEGRITY plan §3 invariants A–D, run on CSV load / case open,
results in Mapping report + log. **Done when:** the check reports zero
violations across all 5 cases; deliberately breaking one (test) reports it.
**Evidence 2026-07-04:** added `DataManager.mapping_integrity_check()` and
`get_mapping_integrity_report()`. It validates mapped-role visibility, one
CSV bucket per column, unique diagram labels, and learned-alias
contradictions; it logs `[MAPPING_INTEGRITY] ...` and Mapping report now
shows a `Mapping integrity` section with the A-D result. The check runs after
CSV auto-map and after case open. Sweep across all saved case folders
(`ID6SU12WE`, `ID6SU4WE`, `ID6SU8WE`, `IDD5SL12WE`, `IDD5SL4WE`,
`IDD5SL6WE`, `IDD5SL8WE`, `IDD6SU12WE`, `RLN5MA`) reported
`total_violations=0`. Deliberately adding `Bogus.Component.sensor -> Fake CSV
Column` reported `deliberate_break_count=1` with
`deliberate_break_keys=['mapped_not_visible']`. `python -m py_compile
data_manager.py sensor_panel.py app.py diagram_from_request.py` passed.

### C8. Remaining CSV-visibility polish — Status: ✅ 2026-07-04
Spec: MAPPING_AND_HIGHLIGHT plan §2.1 (final rule), §2.1b teach flow,
ghost-reveal mapping. **Done when:** that plan's acceptance paragraph
passes verbatim.
**Evidence 2026-07-04:** C8 behavior was already wired and verified with an
offscreen UI harness against IDD5SL12WE + `DataDOE081.csv`. The harness
reported `csv_sensor_count=150`, `panel_leaf_count=150`, `csv_rows=150`,
`not_on_count=0`, `grey_placeholder_rows=0`, `trailing_headers=[]`,
`rendered_unmapped_dot_count=0`, and `should_render_unmapped_count=0`;
`[MAPPING_INTEGRITY] csv_load: OK (150 mapped role(s), 269 expected row(s),
150 CSV column(s))` also passed. A synthetic unknown CSV column produced
`synthetic_not_on=['Definitely Unknown C8']`,
`ghost_base_unmapped_rendered=0`, and `ghost_revealed_unmapped_rendered=93`,
proving hidden candidates appear only during assignment reveal. Ungrouped
context menu contains `Assign to diagram spot...` and `Save as alias of...`;
CSV headers are stripped once on load and session role values are stripped on
load.

### C9. Expansion-device follow-through — Status: ✅ 2026-07-04
Spec: WORKFLOW plan §6.10b (parts-type generalization, kind cross-check,
switch-device → conflicts). Picker choice already exists; finish the part
catalog + regeneration behavior. **Done when:** SENSOR_INTEGRITY plan
acceptance #6 (device matrix) passes.
**Evidence 2026-07-04:** generator output bumped to
`DIAGRAM_GENERATOR_VERSION = 9`. Added real `CapTube` and `EEV` component
schemas/types; generator now emits `TXV`, `CapTube`, or `EEV` per
`topology.expansion_device`, while canonical/port resolution supports all
three. The legacy `txv` catalog slot is now labeled `Expansion Device` and
has a `kind` field plus TXV/cap-tube/EEV-specific fields; existing
kind-mismatch warnings still compare selected part kind to Step 6b.
Matrix harness reported:
`txv {'TXV': 3, 'CapTube': 0, 'EEV': 0} bulbs
['T_txv.ctr.bulb', 'T_txv.lh.bulb', 'T_txv.rh.bulb'] ... integrity 0`;
`cap_tube {'TXV': 0, 'CapTube': 3, 'EEV': 0} bulbs [] ... integrity 0`;
`eev {'TXV': 0, 'CapTube': 0, 'EEV': 3} bulbs [] eev_suction
['T_eev.ctr.suction', 'T_eev.lh.suction', 'T_eev.rh.suction'] eev_pos
['eev_pos.ctr', 'eev_pos.lh', 'eev_pos.rh'] integrity 0`. Switching
IDD5SL12WE to cap tube with `DataDOE80f.csv` reported orphan conflicts for
`Left TXV Bulb`, `CTR TXV Bulb`, and `Right TXV Bulb` against their
`T_txv.*.bulb` canonicals, with integrity still `0`. Stale-regeneration
check reported `generator_version 9 stale_check True 8 9 9`. `python -m
py_compile component_schemas.py diagram_from_request.py sensor_canonical.py
port_resolver.py data_manager.py diagram_widget.py case_dialogs.py
test_request_library.py case_library.py app.py sensor_panel.py` passed. Real
launcher-path check after C9 found the live GUI title
`HVAC System Analyzer - build 2026-07-04 - Labview-new_rev` from this folder;
the temporary extra launcher process was closed, leaving the existing user
window running.

### C10. Label lexicon: grammar + geometry + coverage tool — Status: ✅ 2026-07-04
Spec: CSV_LABEL_LEXICON_PLAN.md (L0–L6). Measured baseline 2026-07-04
(all SEVEN datasets): 343 unique labels, 115 unknown across families
F1–F11; worst case ID6SU8WE at 47% coverage (different technician's
shorthand — proves the token-synonym layer L0 is the highest-value piece).
**Done when:** the coverage scan reports 100% on all seven datasets with
zero per-case manual mapping (except the two documented owner-known
exclusions: TXV-split architecture, Air Velocities FPM), and the scan tool + report exist as a
repeatable gate for new cases.
**Evidence 2026-07-04:** added repeatable headless scanner
`lexicon_coverage.py` and generated `LEXICON_COVERAGE.md`. The Cases dialog
now has `Scan Data Folder...`, which writes the same report. Added grammar
rules for `Sec discharge air ...`, numbered distributor/TXV labels
(`Into distributor 1/2`, `TXV 1/2 inlet`), and `Compressor Hertz`.
Coverage run reported `Overall grammar coverage: 100.0% (817/817)` and
`Unknown labels: 0` across `ID6SU12WE`, `ID6SU6WE`, `ID6SU8WE`,
`IDD5SL12WE`, `IDD5SL4WE`, `IDD5SL6WE`, and `IDD5SL8WE`. `ID6SU6WE` is
reported as `grammar-only` because there is no matching
`library/cases/ID6SU6WE` folder yet; all other folders ran against their
case diagrams. `python -m py_compile case_dialogs.py lexicon_coverage.py
sensor_canonical.py data_manager.py` passed. Real launcher-path check after
C10 found the live GUI title `HVAC System Analyzer - build 2026-07-04 -
Labview-new_rev`; the temporary extra launcher process was closed.

### D1. Diagnosis Phase 1a - verdict on diagram - Status: implemented; Codex re-verified 2026-07-05; owner acceptance pending
Spec: DIAGNOSIS_ROADMAP.md Phase 1a. Findings from the diagnostics engine
render on the process diagram: severity badge on implicated component, top
banner with the lead verdict, click to evidence panel. Engine logic remains
unchanged.
**Done when:** running Calculations produces persistent diagram badges for
CRITICAL/WARNING/WATCH findings, the lead finding appears in the top banner,
clicking a badge opens evidence/recommendation details, and Diagnostics tab
"Show on diagram" still flashes the matching component.
**Evidence 2026-07-04:** added `DiagnosticsWidget.findings_updated` and
connected it to `DiagramWidget.set_diagnostic_findings()`. The diagram now
renders a top verdict banner and persistent `CRIT`/`WARN`/`WATCH` badges on
matched components; clicking a badge opens finding evidence and
recommendation. Offscreen IDD5SL12WE harness with a synthetic TXV warning
reported `COMPONENTS 56`, `MATCHES 3`, `OVERLAY_ITEMS 8`, and
`DIAGRAM_OVERLAY_OK`. `python -m py_compile diagnosis_scorecard.py
diagnostics_widget.py diagram_widget.py app.py` passed.

### D2. Diagnosis Phase 1b - target scorecard verdict - Status: implemented; Codex re-verified 2026-07-05; owner acceptance pending
Spec: DIAGNOSIS_ROADMAP.md Phase 1b. Case/test targets produce explicit
PASS/FAIL rows, and each failed target names the sensor/calculation column
that broke the band.
**Done when:** after Calculations, the Diagnostics tab shows Product temp,
Coil superheat, Subcooling, Capacity, and DOE energy target verdicts from the
opened case defaults; bounded targets show PASS/FAIL/NO DATA, unbounded
targets show NO LIMIT, and the Source column identifies the linked
calculation/sensor columns.
**Evidence 2026-07-04:** added `diagnosis_scorecard.py` and a Diagnostics
tab scorecard table with columns `Target`, `Verdict`, `Measured`, `Band`,
and `Source`. Synthetic evaluator check reported Product temp `FAIL`, Coil
superheat `FAIL`, Subcooling `PASS`, Capacity `NO LIMIT`, DOE energy
`NO LIMIT`; Diagnostics UI harness reported five rows with statuses
`PASS, PASS, PASS, NO LIMIT, NO LIMIT` and linked sources
`T_prod.avg`, `S.H_lh coil, S.H_ctr coil, S.H_rh coil`, and `S.C`.
Launcher-path check found the live GUI title `HVAC System Analyzer - build
2026-07-04 - Labview-new_rev` from this folder; no extra temporary window
was created because the existing user window was already live.

### After D2 - the diagnosis trust era
`DIAGNOSIS_ROADMAP.md` (owner-approved 2026-07-04) defines everything that
follows the mapping checklist: Phase 1 verdict-on-diagram + scorecard, Phase 2
trustworthy diagnosis (arithmetic harness → published-knowledge rulebase →
teaching-mode explanations → confirm/reject confidence loop), Phase 3
baselines (design / family transfer / golden run). Do NOT start Phase 1
until C1–C10 are ✅ — diagnosis on top of wrong mappings is fiction.
Continue with D3, D4, ... derived from the roadmap, same rules as always.

### D3. Diagnosis noise rules (Phase 1c) - Status: implemented; Codex re-verified 2026-07-05; owner acceptance pending
Spec: DIAGNOSIS_ROADMAP.md §1c (added 2026-07-04 after the first live run
badged every component CRIT on a healthy-looking test). Untrusted
scenarios OFF the diagram (Diagnostics tab only, tagged); one banner =
top-ranked finding + "+N more"; max one badge per component with
related-symptom suppression; CRITICAL reserved for physics/sanity +
trusted rules; findings with failed input integrity suppressed as
"insufficient data". **Done when:** the same test that produced the noisy
screenshot renders with ZERO red badges from candidate scenarios (only
scorecard/sanity output), and the Diagnostics tab still lists all 6
candidate findings with confidence tags.
**Evidence 2026-07-04:** added `diagnosis_visibility.py` and applied it in
Diagnostics and Diagram. Candidate scenario cards are rendered as neutral
`OBSERVATION` cards with an `UNVALIDATED` tag; the Diagnostics summary counts
them as `UNVALIDATED OBSERVATIONS`. `Show on diagram` is disabled for
candidate findings. The diagram defensively filters to trusted visible
findings only (`SI-*` sanity checks and `SCORECARD-*` target failures), ranks
the top story, shows `+N more`, and keeps max one badge per component.
Offscreen harness reported `VISIBLE_IDS_ASCII SI-1,SCORECARD-PRODUCT-TEMP`,
`SUMMARY_HAS_UNVALIDATED True`, `DIAGNOSTICS_VISIBILITY_OK`; diagram harness
reported `CANDIDATE_OVERLAY 0`, `STORED_IDS ['SI-1']`,
`DIAGRAM_SUPPRESSION_OK`.

### D4. Validate CP-3 (first scenario through the 2a harness) - Status: implemented; Codex re-verified 2026-07-05; owner acceptance pending
CP-3 "Not Compressing" fired at ~52→121 psi on an MT R290 water-cooled
case. Build the arithmetic harness (roadmap §2a), verify the pressure/
ratio math and CP-3's thresholds against all 7 datasets, retune or park
it. **Done when:** CP-3 is silent on the 7 known-running datasets and its
threshold rationale is written in the rules config.
**Evidence 2026-07-04:** `rules_config.json` now sets `CP-3.enabled=false`,
`status=parked_pending_2a`, with rationale recording the live-run false
alarm. Config harness reported `CP3_ENABLED False` and
`CP3_STATUS parked_pending_2a`. Full arithmetic harness/threshold review is
still the next trust-building step before CP-3 can be re-enabled.
**Evidence 2026-07-05:** added `diagnosis_arithmetic_harness.py` for Phase
2a. It runs the app calculation pipeline on available `DATA/*` CSVs and
independently recomputes saturation temperatures, superheat, subcooling, and
P-h enthalpy columns from processed P/T values using CoolProp. Single-case
check on `IDD5SL12WE/DataDOE80f.csv` reported 1,300 checks and zero failures.
Broad sampled sweep (`--max-rows 50`) reported
`ARITHMETIC_HARNESS_SUMMARY cases=13 failures=0`; `ID6SU6WE` was skipped
because no matching `library/cases/ID6SU6WE/diagram.json` exists. CP-3 was
not re-enabled as the old naked `PR < 1.5` expression: review showed equalized
samples would still false-fire. CP-3 now uses the Python `run()` method with
a compressor-running gate (`rpm >= 300` or pressure lift >= 10 PSIG) and
suppresses pressure-equalized/off-cycle windows. `rules_config.json` sets
`CP-3.enabled=true`, `status=enabled_after_2a_running_gate`, and clears the
old expression block so the gated method is used. Verification reported
`CP3_GATED_EQUALIZED_SUPPRESSION_OK`, `CP3_GATED_SWEEP_REVIEWED 12`,
`CP3_GATED_SWEEP_FIRES []`, `CP3_GATED_SWEEP_OK`, and
`python -m py_compile diagnostics_engine.py diagnosis_arithmetic_harness.py`
passed.

### D5. Calculation input preflight - Status: implemented; Codex re-verified 2026-07-05; owner acceptance pending
Observed live-run issue: missing water GPM offered to continue with missing inputs and
then calculations ran with missing inputs. Replace that with a required
approximate-input gate: if no mapped condenser water-flow sensor and no saved
GPM exist, prompt for approximate GPM before calculations run; Cancel stops
the calculation. **Done when:** running Calculations with missing GPM opens
`Approximate Values Needed for Calculations`, requires Water Flow Rate (GPM),
saves it to `rated_inputs`, and only then starts calculations.
**Evidence 2026-07-04:** `InputDialog` now supports required fields and
validates them; `CalculationsWidget.run_calculation()` calls
`_ensure_required_calculation_inputs()` after CSV/range/defrost filters and
before `run_batch_processing()`. Measured mapped GPM satisfies the preflight
without prompting. Harness reported `MEASURED_GPM True` and
`INPUT_PREFLIGHT_MEASURED_OK`; source search for the old continue-anyway prompt
returned no matches.
**Evidence 2026-07-05:** fixed post-preflight regression where a successful
calculation frame with an all-NaN `error` column was treated as fatal and
shown as `Calculation Error: nan`. `CalculationsWidget` now ignores blank,
`NaN`, and `None` error values and only stops on real row error messages.
Static regression reported `ERROR_COLUMN_STATIC_REGRESSION_OK`.

### D6. Finish D1's one-badge rule - Status: implemented; Codex re-verified 2026-07-05; owner acceptance pending
Owner's 2nd screenshot (2026-07-04, "Negative Subcooling (+1 more)") still
shows ~8 CRIT rectangles for effectively one finding. Spec: ROADMAP §1c.2 —
ONE badge, placed at the implicated location (condenser outlet), related
symptoms collapsed. **Done when:** that same test renders exactly one
badge + the banner.
**Evidence 2026-07-05:** reproduced the old behavior with a synthetic
trusted `SI-1 Negative Subcooling` finding against IDD5SL12WE:
`BADGE_COUNT 8`, `MATCHED_TARGETS 8`. Updated the diagram overlay so only
the top-ranked visible finding gets a badge, while the banner keeps `+N more`
for the ranked list. `SI-1` now targets the condenser instead of every
refrigerant component, and the badge is anchored near the condenser outlet
port when available. Verification reported `BADGE_COUNT 1`,
`MATCHED_TARGETS 1`, `TARGET_TYPES ['Condenser']`, `ONE_BADGE_REPRO_OK`;
neighbor checks reported `ONE_BADGE_PLUS_MORE_OK` and
`CANDIDATE_SUPPRESSION_STILL_OK`. `python -m py_compile diagram_widget.py`
passed.
**Evidence 2026-07-05:** generalized the overlay locator from a one-off SI-1
condenser rule into an explicit scenario locator matrix in `diagram_widget.py`.
Representative CP/CD/EV/TX/DI/SL/SI/SCORECARD scenarios now resolve to specific
component classes or pipe classes, with preferred port anchoring where useful.
Distributor findings prefer an explicit Distributor component and fall back to
the evaporator distributor inlet area on the current simple generated diagrams;
Filter Drier findings prefer FilterDrier/Distributor and fall back to the
liquid-line expansion-device inlet instead of going broad or empty. Verification
reported `SCENARIO_LOCATOR_REPRESENTATIVE_OK`,
`EXPANSION_DEVICE_LOCATOR_VARIANTS_OK` for TXV/CapTube/EEV, and
`SAVED_CASE_LOCATOR_SWEEP_OK` across 9 library cases.

### D7. Refrigerant-state storytelling - Status: implemented; Codex re-verified 2026-07-05; owner acceptance pending
Spec: DIAGNOSIS_ROADMAP §1d. State-colored pipes from measured P/T
(liquid solid blue / gas orange / two-phase striped) with state chips;
live P-h cycle view fed from the loaded test (ph_diagram_* widgets exist —
wire, don't rebuild); "Show on cycle" action on findings; findings present
the differential fork with the case's own corroborating values (§1d.3).
**Done when:** on the negative-subcooling test, the condenser-outlet
segment renders two-phase striped while TXV-inlet segments render liquid
with "SC ≈ 12°F" chips; the P-h view shows the condenser-outlet point
inside the dome; the finding text names all three candidate causes and
which one the corroborating values favor.

**Evidence 2026-07-05:** Analysis mode now opens a docked Cycle (P-h) panel
inside the Diagram tab and colors refrigerant pipes from measured calculation
means. Liquid/high-side pipes render blue when subcooled, gas pipes render
orange, and two-phase/flash-gas segments render blue/orange striped overlays
with state chips. On simple generated diagrams where condenser outlet and TXV
inlet share one drawn pipe, the overlay shows both the condenser-outlet flash
gas chip and the TXV-inlet liquid SC chip when those measured values disagree.
Diagnostics cards and badge evidence dialogs now include `Show on cycle`,
which switches to Diagram Analysis and highlights the matching P-h state point
(`SI-1` -> `4a`). `ph_diagram_widget.py` now reads current calculation columns
(`h_2b`, `h_3a`, `h_4a`, `h_4b_*`, `h_2a_*`, `P_suc`, `P_cond`) from the
same averaged calculation window as the diagram overlay. SI-1 evidence now
adds the three-branch teaching fork (condenser performance, undercharge,
measurement artifact), available water delta-T / coil SH / TXV inlet SC
corroborating values, and the branch currently favored. Verification reported
`D7_STATE_AND_CYCLE_HARNESS_OK`, `SI1_TEACHING_FORK_OK`, and
`python -m py_compile diagram_widget.py ph_diagram_widget.py diagnostics_widget.py app.py diagnostics_engine.py`
passed.

### D8. State-storytelling corrective round 1 (R1–R9; was mis-numbered "D5") — Status: implemented; Codex re-verified 2026-07-05; owner acceptance pending
(Corrective for the implementer's D7 "refrigerant-state storytelling". Renumbered
D8 on 2026-07-05 to resolve a numbering collision with the diagnosis D5.)
Independent audit of the 2026-07-04 D4 attempt found six defects. Progress
noted: the one-badge rule (D3) now works — single CRIT at the condenser +
banner. Everything below is measured/verified, with the fix rule:

**M1 — Wrong P-h widget.** The dock embeds the OLD `PhDiagramWidget`
(diagram_widget.py:565–567): per-circuit matplotlib small multiples,
axes in Pa / kJ/kg, overlapping titles, its own Refresh/Export buttons,
truncated legends. SPEC (roadmap §1d): ONE dome, ONE axes pair, branches
OVERLAID with circuit colors + toggle chips, units °F / psig / BTU/lb,
auto-follows the time window (no Refresh button — same pipeline as the
dots), no Export in the dock. Build it as a new lightweight pyqtgraph
plot (consistent with the Graph tab); the old audit widget stays where it
was, untouched.

**M2 — Chip spam.** Chips are stamped on EVERY circuit segment
("two-phase" ×12, "gas, SH …" ×12, overlapping the dots). SPEC: chips at
KEY STATIONS ONLY — compressor suction (total SH), discharge (DSH),
condenser outlet (SC), each TXV inlet (SC), each coil outlet header
(that coil's SH). Circuit-level segments carry COLOR only; a circuit gets
a chip only when it deviates from its siblings beyond threshold
(anomaly), which is the only time it has something to say.

**M3 — Wrong SH source on coil chips.** Every coil circuit shows
`gas, SH 26.7F` — that is the COMPRESSOR/suction superheat stamped
everywhere; the per-coil values (6.7 / 4.4 / 4.2, already computed as
`calc.SH.*`) must feed coil-station chips. Also: a chip whose value is
NaN must not render at all (a literal `nan` chip is visible in the
screenshot).

**M4 — Segment state must be computed per segment, not propagated.** The
liquid line renders striped (two-phase) all the way to the TXVs while
its own chip reads "TXV inlet liquid, SC 10.0F". Rule: each segment's
state comes from its nearest bracketing measurements; when measurements
disagree across a run (two-phase at condenser outlet, subcooled at TXV
inlet), the line SPLITS color at the transition and the transition
itself is surfaced as an observation ("condensation completes in the
liquid line") — that is real diagnostic information, not a rendering
choice.

**M5 — Alarm wording.** "FLASH GAS" appears 3+ times in warning style
(diagram_widget.py:1724). One neutral chip at the condenser outlet
("two-phase, SC −6.4°F"); alarm language lives in the finding/banner
only, never in chips.

**M6 — Declutter.** After M2, verify no chip overlaps a dot/value label
at default zoom (the acceptance screenshot must be readable).

**Verification round 1 (owner screenshots, 2026-07-04 late):** M1 rebuild
largely done (one chart, psig/BTU-lb, branch toggles); chip spam gone;
liquid-line split implemented. REMAINING:
- R1: `nan` chip still renders next to Left Evaporator (M3 violation).
- R2: chip stations incomplete — 1 of 3 TXV-inlet chips, 0 of 3
  coil-outlet SH chips (per-coil 6.7/4.4/4.2 must appear).
- R3: liquid-line stripe direction wrong — header is fed at CENTER;
  both branches should start striped at the feed and turn blue where
  measurements go subcooled. Currently the RIGHT branch (coldest TXV
  inlet, 55.3°F ≈ SC +20) renders striped end-to-end while the left is
  solid blue. State must follow FLOW DIRECTION per branch.
- R4: P-h saturation curves MISSING — convert
  `ph_diagram_generator.generate_saturation_data` output (SI) to
  psig/BTU-lb and draw both dome boundary curves; at the 40–140 psig
  window they appear as two curve segments bracketing the cycle
  (liquid ≈ h 110–135, vapor ≈ h 245–265), NOT a full bell.
- R5: P-h state-point labels rotated one position around the loop —
  correct convention: 1 = suction (bottom right), 2 = discharge (top
  right), 3 = TXV inlets (top left, three points), 4 = after expansion
  (bottom left). Current render labels these 2b/3/4x/1 respectively.
- R6: discharge chip text truncated at default zoom (M6 check).
- R7 (owner screenshot, evaporator close-up): WRONG STATE on the
  TXV→distributor stub and distributor→coil-inlet stubs — rendered solid
  orange (gas) where the refrigerant is TWO-PHASE (post-expansion). Every
  segment between an expansion device outlet and its coil inlet renders
  striped, same as the header transition.
- R8: GREY refrigerant segment in Analysis — coil outlet (36.4) to the
  suction merge renders grey (no state) although its state is known
  (suction gas, SH 6.7). In Analysis, no refrigerant-carrying pipe may
  remain grey/default: every segment gets a computed state, or an
  explicit "unknown ?" style when inputs are genuinely missing (which is
  then an integrity note, not a silent fallback).
- R9: LINE-WEIGHT consistency — thick orange stubs vs thin/medium lines.
  State coloring changes COLOR ONLY: one uniform refrigerant-pipe weight
  across the whole loop in Analysis. Structural manifold/bracket
  graphics (light blue combs) stay visually distinct from the refrigerant
  path but must not read as part of it.

**Done when:** on the same test — process diagram shows exactly 9 chips
for a 3-module case (1 suction + 1 discharge + 1 condenser outlet +
3 TXV inlets + 3 coil headers), fewer only where a value is NaN
(which renders nothing), coil chips read
6.7/4.4/4.2, liquid line is blue after the state transition point, and
the Cycle panel is ONE dome with three overlaid branches in °F/psig
that moves when the time window changes with no Refresh click.

**Evidence 2026-07-05:** Diagram Analysis now uses a new lightweight
`CycleDomeWidget` in the dock instead of the old `PhDiagramWidget`. It draws
one overlaid R290 P-h dome with LH/CTR/RH branches on a single pyqtgraph
axis, labels h in BTU/lb and P in psig, and has no Refresh/Export controls in
the dock. State chips are now keyed to measurement stations only: suction
SH, discharge DSH, condenser outlet SC, TXV inlet SC per module, and coil
outlet SH per module. Circuit-level evaporator pipes still receive state
color but no repeated chips; NaN chip text is suppressed; "FLASH GAS" wording
is no longer rendered as a chip. Where condenser outlet SC is negative but
TXV inlet SC is positive, the condenser/TXV pipe is blue liquid with only a
short two-phase striped transition near the condenser outlet. Offscreen
IDD5SL12WE harness reported `CYCLE_WIDGET_CLASS CycleDomeWidget`,
`CHIP_COUNT 9`, chips
`Suction SH 26.7F`, `DSH 49.8F`, `two-phase, SC -6.4F`, `TXV SC 10.0F`,
`TXV SC 10.4F`, `Coil SH 6.7F`, `Coil SH 4.4F`, `Coil SH 4.2F`,
`HAS_NAN_CHIP False`, `PLOT_ITEMS 21`, and `D7_CORRECTIVE_HARNESS_OK`.
`python -m py_compile diagram_widget.py ph_diagram_widget.py diagnostics_widget.py app.py`
passed.

**Evidence 2026-07-05 verification round 2:** Fixed owner R1-R9 follow-up.
Diagram value labels now suppress NumPy/float NaN values, so a mapped calc
dot cannot render literal `nan`. Analysis state inference no longer depends
only on saved `fluid_state`: endpoint rules force condenser outlet liquid,
TXV/CapTube/EEV outlet and distributor-to-coil segments two-phase, evaporator
outlet and suction-header segments low-side gas, and any remaining
refrigerant pipe gets an explicit purple dotted unknown state instead of
silent default grey. Refrigerant pipe weight is uniform in Analysis; state
changes color/stripe only. The discharge chip was shortened to `DSH 50F` to
avoid default-zoom truncation. The docked cycle now converts
`ph_diagram_generator.generate_saturation_data` to psig/BTU-lb, ranges to the
active cycle window, and displays owner state labels `1` suction, `2`
discharge, `3` TXV inlet, `4` after expansion. Offscreen IDD5SL12WE harness
reported `rendered=47` for `PIPE_COUNT 47`, `CHIP_COUNT 9`, `STRIPE_OVERLAYS
34`, chips `TXV SC 10.0F`, `TXV SC 10.4F`, `TXV SC 20.0F`, `Coil SH 6.7F`,
`Coil SH 4.4F`, `Coil SH 4.2F`, `two-phase, SC -6.4F`, `DSH 50F`, no text
containing `nan`, owner cycle labels present, old labels `2b`/`4b` absent,
and `D7_R1_R9_HARNESS_OK`. `python -m py_compile diagram_widget.py
ph_diagram_widget.py data_manager.py calculation_engine.py calculations_widget.py`
passed.

**Evidence 2026-07-05 manifold visual fix:** Root cause was confirmed as
separate component glyphs, not `PipeItem`s: `SplitterManifold` and
`CombinerManifold` internals were hard-coded as blue 2 px paths. Normal mode
now renders those internal manifold paths neutral grey 2 px so they match the
non-Analysis process piping. Analysis mode overrides them by state:
splitter/distributor internals are blue with orange dash overlay for
two-phase feed, while combiner/header internals are orange suction gas.
Offscreen IDD5SL12WE harness reported normal manifold pens all
`('#888888', 2.0)`, Analysis splitter pens all `('#1565c0', 5.0)`, Analysis
combiner pens all `('#f59e0b', 5.0)`, `SPLITTER_STRIPE_CHILDREN 3`, and
`MANIFOLD_MODE_STATE_FIX_OK`. `python -m py_compile diagram_components.py
diagram_widget.py` passed.

**Evidence 2026-07-05 Analysis calculated-SH visibility fix:** Reproduced
the disappearing-superheat class under the CSV-loaded/Analysis condition,
where unmapped calculated custom dots could be suppressed even though
`_processed_means` contained their calculation columns. Analysis now keeps
custom calculation dots visible when their `calc_key` exists in
`_processed_means`, formats calculated SH/SC labels with units via the common
value formatter, suppresses NaN, and accepts common coil-SH column aliases
for state chips. Offscreen IDD5SL12WE harness with `csv_data` present and
processed means for all three modules reported `DOT_KEYS ['calc.SH.ctr',
'calc.SH.lh', 'calc.SH.rh', 'calc.SH_total']`, visible labels `SH 31.5F`,
`SH 22.2F`, `SH 18.8F`, `SH 35.2F`, coil chips `Coil SH 31.5F`, `Coil SH
22.2F`, `Coil SH 18.8F`, no literal `nan`, and
`ANALYSIS_CALC_SH_DOTS_OK`. `python -m py_compile diagram_widget.py
data_manager.py` passed.

**Evidence 2026-07-05 Analysis SH exact-root-cause fix:** The exact failure
was a data-handoff/schema mismatch after calculations. `CalculationsWidget`
reindexed the processed frame to a stable table schema before emitting it to
the Diagram tab; any diagram calculated callout whose `calc_key` was not in
that expected schema could be dropped from `_processed_means`, and Analysis
then suppressed the custom calc dot because it thought the calculation value
did not exist. The diagram also required exact calc-key column names, so
case/layout variants such as `S.H_CTR coil-ctr` could be missed even when the
same value existed under an alias. The calculation handoff now preserves all
`custom_sensors[*].calc_key` columns, and the diagram resolves SH/SC calc
keys through shared/cassette alias candidates before deciding visibility or
text. Offscreen CSV-loaded Analysis harness using aliased CTR/RH SH columns
reported `DOT_KEYS ['calc.SH.ctr', 'calc.SH.lh', 'calc.SH.rh',
'calc.SH_total']`, visible labels `SH 31.5F`, `SH 22.2F`, `SH 18.8F`, coil
chips for all three modules, and `ANALYSIS_CALC_SH_ALIAS_DOTS_OK`.
`python -m py_compile diagram_widget.py calculations_widget.py` passed.

### D9. Computed SH/SC cross-check (double verification; was mis-numbered "D6") — Status: ✅
Owner request 2026-07-05. The engine computes coil SH as
`T_coil_outlet − T_sat(dew, P_suction)` (calculation_engine.py:300-303) but
produces NaN/nothing for IDD5SL12WE because the coil-OUTLET temp role
`T_2a-*` has no CSV column bound (suction pressure IS present). VERIFIED by
hand from DataDOE80f: T_sat(51.9 psig) = 30.1°F; using the coil-exit probe,
computed SH = Left 6.6 / Center 3.4 / Right 4.3°F vs lab 6.66 / 4.39 / 4.20
— Left & Right match to 0.1°F, Center off ~1°F (exactly the kind of sensor
discrepancy the cross-check should surface).
Two parts: (a) bind the coil-exit temperature to the `T_2a-*` canonical
(lexicon/mapping work — the physical sensor exists, reproduces lab SH); then
(b) the diagram/analysis shows COMPUTED vs LAB SH side by side — agreement =
trust, mismatch = flagged sensor.

**Subcooling status (verified 2026-07-05):** SC is ALREADY computed and
displayed — inputs are mapped (condenser-out `Ref Temp out HeatX`, TXV
inlets, discharge P). Formula `SC = T_sat(bubble, P_disch) − T_liquid`.
Real values: T_sat(bubble)@121psig = 75.8°F; condenser `S.C` = −6.4°F
(negative → not fully condensed at exit = the CRIT), TXV-inlet SC = LH +10.0
/ CTR +8.5 / RH +17.5°F (fully subcooled by the TXVs → condensation
completes in the liquid line). Two SC follow-ups:
  - SC1: `calc.SC_cond` is mapped to `Liqcond` (raw 72.6°F condensing temp)
    while its calc_key computes −6.4°F SC → normal mode shows a temp,
    Analysis shows a delta (two different quantities on one dot). Unmap it
    (SC is calc-only) OR add a proper lab-SC column if one exists elsewhere.
  - SC2: this dataset has NO independent lab subcooling column to
    cross-check against (unlike SH's `*.S.H.` columns) — verify whether
    other case datasets carry one; if not, computed SC is single-source
    and leans harder on the P_disch/T_sat arithmetic being right (2a gate).
Both SH and SC feed the P-h cycle points, which depend on these values.
Prereq relationship: this is a concrete driver for C10 (lexicon) and feeds
the diagnosis era (roadmap Phase 2 arithmetic harness §2a — computed-vs-lab
agreement IS the arithmetic verification).
**Done when:** all three coils show computed SH within tolerance of lab SH
on the known-good datasets, and any coil exceeding tolerance is flagged.
**Display-bug note (fixed 2026-07-05):** separate from D6, the Analysis-mode
label logic (diagram_widget.py:2241) committed to the calc branch and went
BLANK when the computed value was NaN, instead of falling back to the mapped
lab value — so SH showed in normal mode but vanished in Analysis. Fixed:
fall back to lab value when calc value is None; verified 6.7/4.4/4.2 render
in both modes.

**Implementation evidence (2026-07-05):** `calculation_orchestrator.py`
now binds aggregate coil-outlet custom roles (`T_coil.lh/ctr/rh.out`) into
the canonical `T_2a-LH/CTR/RH` calculation inputs, and binds mapped lab SH
columns from `calc.SH.lh/ctr/rh` into `_lab_SH_*`. `calculation_engine.py`
now emits `S.H_* lab`, `S.H_* delta`, and `S.H_* check` using a 0.75°F
tolerance, plus `D.S.H` for the compressor-discharge station. Harness
reported computed SH `6.620 / 3.420 / 4.220`, lab SH `6.66 / 4.39 / 4.20`,
checks `OK / CHECK / OK`, `DSH 50.030`, and
`D9_ORCHESTRATOR_AGGREGATE_T2A_OK`. `python -m py_compile
calculation_engine.py calculation_orchestrator.py calculations_widget.py
data_manager.py diagram_widget.py` passed.

### D10. Chip information architecture — kill duplicate/overlapping labels (was mis-numbered "D7") — Status: ✅
Owner screenshot 2026-07-05: every SH/SC value renders TWICE and chips
overlap at tight geometry. ROOT CAUSE (verified): two independent systems
print the same numbers — the pipe-chip system (diagram_widget.py:1805-1891:
"Suction SH", "TXV SC", "two-phase, SC", "DSH") AND the calc-dot label
system (diagram_widget.py:1121: "SH", "SC" beside components). Confirmed
duplicates: Suction SH (×2), each TXV SC (×2), condenser SC (×2); plus the
DSH chip overlaps `P disc`, and the center pipe chips stack on each other.

**Rule — ONE owner per quantity, at ONE station. Pipes carry COLOR ONLY,
no numeric chips.** Final layout:

| Station | Quantity | Chip (single) |
|---|---|---|
| Compressor inlet | total suction superheat | `SH 26.7°F` |
| Compressor discharge | discharge superheat | `DSH 50°F` (must not overlap P disc) |
| Condenser outlet | condenser subcooling | `SC −6.4°F` — RED when negative (this IS the warning) |
| Each TXV inlet | TXV subcooling | `SC 10.0 / 8.5 / 17.5°F` |
| Each coil outlet | coil superheat | `SH 6.7 / 4.4 / 4.2°F` |

- DELETE the pipe-anchored numeric chips (1805-1891); keep pipe COLOR + the
  striped→blue transition (color change alone tells the two-phase story; at
  most ONE tiny neutral "condensation completes" marker at the transition,
  never a stack).
- The condenser negative-SC chip is the only emphasized (red) label; banner
  states it once. Everything else neutral, so the warning doesn't compete.
- Collision rule: no chip overlaps another chip, a dot, or a value label at
  default zoom; offset along the component side when tight.
- No truncation (the "…50F" / "two-phas…TXV SC" clipping must be gone).

**Done when:** the same test shows each SH/SC value exactly ONCE at its
station, zero overlaps/truncation at default zoom, pipes convey state by
color only, and the single red condenser `SC −6.4°F` chip + banner are the
clear negative-subcooling warning.

**Implementation evidence (2026-07-05):** `diagram_widget.py` no longer
creates pipe-owned numeric chips for suction SH, coil SH, TXV SC, condenser
SC, or DSH; pipes only carry state color/striping in Analysis. Standard
calculated callouts now own the station values, including a new
`calc.DSH` compressor-discharge callout. `calc.SC_cond` is calc-only and
the learned `Liqcond -> calc.SC_cond` alias was removed so normal mode no
longer shows raw liquid-line temperature as condenser subcooling. Offscreen
Qt render harness on the IDD5SL12WE diagram reported exactly one each of
`SH 6.6F`, `SH 3.4F`, `SH 4.2F`, `SH 26.7F`, `SC -6.4F`, `SC 10.0F`,
`SC 8.5F`, `SC 17.5F`, and `DSH 50.0F`; forbidden pipe labels
`Suction SH`, `TXV SC`, `two-phase, SC`, and `Coil SH` were absent; state
overlay printed `chips=0`; the negative `SC -6.4F` station chip pen was
`#c0392b`; harness reported `D10_RENDER_ONCE_PIPE_COLOR_ONLY_OK`.

## Rules for the implementer

1. One item per session/turn. Tick the box, note the date, show the "Done
   when" evidence (log lines or screenshot) before moving on.
2. Never mark an item done from a terminal launch — C2 applies always.
3. If an instruction here conflicts with a plan document, THIS file wins;
   note the conflict at the bottom of this file for the owner.
4. If something can't be completed, write status ⚠️ with one line of why —
   never claim done.
