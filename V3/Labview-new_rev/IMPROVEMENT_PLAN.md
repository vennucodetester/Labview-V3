# App Improvement Plan
> **See "ROUND 2" at the bottom for the current action plan (2026-07-01 feedback).**

# Round 1 — Original Scope (partially implemented)
> Drafted 2026-07-01. Based on a code review of `diagram_widget.py` (sensor dot placement),
> `graph_widget.py` (Graph tab), and an overall pass of the app structure.
> Each area lists: what's wrong (with the code evidence), what to change, and effort.

---

## Priority 1 — Process Diagram: Sensor Dot Placement & Readability

### What's wrong today (root causes found in code)

1. **Hardcoded pixel offsets collide on small components** — `_offset_role_dot_from_port()`
   (`diagram_widget.py:1580`) places dots with fixed constants: Compressor `SP` at
   `top+18` and `inlet` at `top+32` on the *same left edge* — only 14 px apart while each
   dot is 12 px in diameter. TXV, Condenser, Compressor all use these magic 18/32 px
   offsets. Any component drawn small (or with several side ports) produces overlapping
   or touching dots.
2. **No dot-vs-dot collision handling.** Labels have a greedy collision pass
   (`_place_role_label`, 45 attempts against `_role_label_rects`), but the **dots
   themselves have none** — two ports resolving to the same perimeter point simply stack.
3. **Dots scale with zoom.** `QGraphicsEllipseItem` radius is a constant 6 scene units
   with no `ItemIgnoresTransformations`, so zooming out shrinks dots into an unreadable
   smear, and the selected-dot 2.2× scale makes overlap worse.
4. **Labels are disconnected from their dots.** In simple mode, labels are 6 pt text
   placed by lane-shifting up to ±4 lanes away (`_candidate_role_label_rect`). When the
   collision search pushes a label 3–4 lanes from its dot there is **no leader line**, so
   you can't tell which value belongs to which dot.
5. **No level-of-detail.** All dots + labels render at every zoom level; a 3-module
   diagram with pressure/SH/SC callouts becomes a wall of tiny text.
6. **No manual escape hatch.** Custom sensors have `display_side`, but port dots can't be
   nudged by the user, so a bad automatic placement is permanent.

### Proposed scope

**Phase A — Placement engine (the core fix)**
- Replace the per-component `if/elif` offset table with a two-step layout:
  1. Assign each dot to a component **side** (keep the current semantic side choices —
     they're good).
  2. Run a **1-D distribution pass per side**: collect all dots assigned to one edge,
     sort by their ideal position, then enforce a minimum spacing (e.g. 18 px) by
     spreading them along the edge — same idea as axis-label decluttering. This kills
     the SP/inlet collision class entirely and works for any component size/port count.
- When a dot is moved away from its port by the distribution pass (> ~10 px), draw a thin
  **leader line** from dot to true port location so the association stays visible.

**Phase B — Screen-constant rendering + level-of-detail**
- Set `ItemIgnoresTransformations` on dots and labels (constant on-screen size at any
  zoom), with a scene-position anchor.
- LOD rules by view scale: zoomed way out → dots only (no labels); mid → dots +
  short labels; zoomed in → dots + label + value. Cheap: one check in a `viewport`
  scale-changed hook that toggles label visibility.
- Bump label font from 6 pt to 8 pt and give labels a semi-opaque white background
  (`QGraphicsSimpleTextItem` + backing rect) so they read over pipes.

**Phase C — Callout-style side sensors**
- Pressure/SH/SC and other "meta" side sensors (Compressor SP/DP/RPM, TXV bulb,
  calc callouts) get a **callout treatment**: small label box offset outside the
  component with a leader line, stacked vertically in a mini-column per side —
  like dimension callouts in CAD, not free-floating dots.
- Labels always paired with the leader line; label placement collision pass reused but
  operating on the callout column, not arbitrary lanes.

**Phase D — Manual nudge (escape hatch)**
- Drag a dot/callout to reposition; store offset in the diagram model
  (`sensor_point_offsets: {role_key: [dx, dy]}`) so it persists in sessions and wins over
  automatic placement. Right-click → "Reset position".

*Effort: A ≈ 1 session, B ≈ 0.5, C ≈ 1, D ≈ 0.5. A+B alone fix the stated complaint.*

---

## Priority 2 — Graph Tab: Professional Plotting

### What's wrong today (from `graph_widget.py`)

1. **One Y axis for everything** — axis is literally labeled `"Sensor Value"` (line 151).
   Plotting P_disch (~200 psig) with a superheat (~10 °F) flattens the small signal into
   a line. This is the single biggest "not professional" cause.
2. **Zoom problems have a concrete source**: after every replot, `setXRange(...)` is
   forced (line 369), which fights pyqtgraph's auto-range and discards the user's zoom
   whenever `update_ui()` fires (any data_changed signal). There's also no rubber-band
   zoom mode, no per-axis zoom, and "Reset Zoom" is just `autoRange`.
3. **No performance settings**: antialiasing off, no `setDownsampling(auto=True)`, no
   `setClipToView(True)` — large CSVs (100k+ rows × several curves) pan/zoom sluggishly
   and look jagged.
4. **6-color palette** recycles after 6 sensors (line 203); curves 7+ are
   indistinguishable. Pen width 1.5 with no antialias looks pixelated.
5. **Fragile timezone hack**: manual `time.altzone` arithmetic (lines 246–280) is applied
   with *today's* DST state to *the CSV's* dates — data recorded across a DST boundary
   or viewed in a different season shifts by an hour. Same hack is copy-pasted in
   `capture_snapshot` and `apply_custom_range`.
6. **No data readout**: no crosshair/hover cursor, no way to inspect a point's value.
   The legend lives only in a separate stats table; the plot itself has no legend.
7. **Full clear+replot** on every update; stats table shows full-range stats, not the
   zoomed viewport, so what you see and what the table says disagree.
8. **~44 debug `print()` calls** in the paint path.

### Proposed scope

**Phase A — Visual + zoom correctness (the stated complaints)**
- Enable `pg.setConfigOptions(antialias=True)`, `setDownsampling(auto=True, mode='peak')`,
  `setClipToView(True)`. Pen width 2, proper dash-differentiation option.
- Replace 6-color list with a 12+ color colorblind-safe palette (Tab10/Set2 style).
- **Preserve user zoom across replots**: capture `viewRange()` before rebuild, restore
  after, and only auto-range on first plot or explicit "Reset Zoom". Remove the forced
  `setXRange` on every update.
- Add zoom modes: mouse-wheel = zoom (already pyqtgraph default), drag = pan, plus a
  **rubber-band zoom** toggle button (`ViewBox.RectMode`); "Reset Zoom" per-axis options.
- Axis styling: units in axis labels, tick font, subtle grid; plot title = CSV name.

**Phase B — Unit-aware axes**
- Group selected sensors by unit family (temperature / pressure / percent / power /
  flow) using the canonical sensor DB (`sensor_canonical.py` already classifies most).
- Two options — pick one at design review:
  1. **Dual Y-axis** (left = first unit group, right = second) via pyqtgraph
     multi-ViewBox; simplest, handles the common temp+pressure case.
  2. **Stacked linked subplots** (one plot per unit group, shared X axis) via
     `GraphicsLayoutWidget`; scales to any number of groups, reads like commissioning
     software. *Recommended.*

**Phase C — Data readout**
- Crosshair + hover readout: vertical line following the mouse, floating label showing
  timestamp + value of each visible curve at that X (nearest-point lookup).
- In-plot legend (click to show/hide a curve) in addition to the stats table.
- Stats table computes over the **visible X range**, updating on zoom (debounced), so
  the table matches what's on screen. Keep a "full range" toggle.

**Phase D — Correctness & hygiene**
- Centralize timestamp→Unix conversion in ONE helper in `data_manager` using
  `pd.Series.dt.tz_localize(local_tz).tz_convert('UTC')` (per-timestamp DST-correct),
  used by plot, snapshot, and range-apply. Delete the three copy-pasted `time.altzone`
  blocks.
- Replace `print()` with `logging` (logging_setup already exists).
- Delete `graph_widget_old.py` once the new widget lands.

*Effort: A ≈ 0.5 session, B ≈ 1 (stacked subplots), C ≈ 0.5–1, D ≈ 0.5.*

---

## Priority 3 — Overall App Improvements (observed in this pass)

### 3.1 Responsiveness: everything runs on the UI thread
No `QThread`/worker anywhere in the app. CSV load, batch CoolProp calculations
(thousands of rows × property calls), the cycle solver, and all 33 diagnostics run
synchronously — the window freezes ("Not Responding" on Windows) during them.
**Scope:** move `run_batch_processing` + `run_all_diagnostics` into a worker thread with
a progress dialog and cancel button; results delivered via signal. This is the largest
perceived-quality win after the two priorities above. *(≈ 1–1.5 sessions; needs care —
CoolProp is thread-safe, but all Qt updates must stay on the main thread.)*

### 3.2 Logging & debug cruft
~330 `print()` calls across the widgets (134 in diagram_widget alone) despite
`logging_setup.py` existing. Also leftover test scaffolding in production paths — e.g.
`test_double_click` wrapper permanently installed on every sensor dot
(`diagram_widget.py:1963-1973`). **Scope:** sweep prints → `logging.debug/info`, delete
test wrappers. *(≈ 0.5 session, mechanical.)*

### 3.3 Dead / legacy file cleanup
Known-legacy modules still in the tree and importable: `graph_widget_old.py`,
`diagram_widget_simple.py`, `new_diagram_wizard.py`, `diagram_template_loader.py`,
`diagram_template_patcher.py`, `diagram_templates.py` (884 lines), plus stale scripts
CLAUDE.md already flags as broken (`test_calculations.py`, `debug_ph_diagram.py`, …).
**Scope:** move to a `legacy/` folder or delete after confirming no imports. *(≈ 0.25.)*

### 3.4 Diagram interaction robustness
- Single-vs-double-click on dots is hand-rolled with a `QTimer` per dot and monkey-patched
  `mousePressEvent` closures — fragile and adds a 250 ms lag to every mapping click.
  **Scope:** proper `QGraphicsObject` dot class with standard event overrides.
- `update_sensor_dots()` rebuilds all overlay items on every mapping/selection change;
  on big cassette diagrams this is visible lag. **Scope:** update only the affected dot.
- No undo/redo in the diagram editor (component moves, pipe drags, deletions are
  permanent). **Scope:** QUndoStack for move/delete/route edits. *(Larger — optional.)*

### 3.5 UI consistency & polish
- Styling is ad-hoc inline stylesheets per widget (`#f0f0f0` control bars, mixed fonts).
  **Scope:** one shared QSS theme + consistent toolbar pattern across the 5 tabs.
- Error reporting is inconsistent: some failures print to console only (user sees nothing),
  some raise message boxes. **Scope:** one `show_error` helper + top-level excepthook
  dialog so silent failures become visible.
- Sensor panel: with ~150 columns, add a search/filter box and "unmapped only" filter to
  complement Session-13 auto-mapping.

### 3.6 Data-layer hygiene
- The Timestamp/timezone conversion (3.x in Graph scope) also affects Comparison and
  snapshot alignment — fix once in `data_manager`, consume everywhere.
- Session save/load has no schema version stamp; migrations are ad-hoc dicts. **Scope:**
  add `session_version` and a single ordered migration list.
- No autosave / crash recovery for diagram edits (Session-12 handoff bug showed a crash
  loses work). **Scope:** timed autosave of the diagram model to a recovery file.

### 3.7 Testing
No runnable test suite (existing test scripts reference deleted code). **Scope:** start
with pure-logic tests only — `calculation_engine`, `cycle_solver`, `sensor_canonical`,
diagnostics expression evaluator — no Qt needed; run via `pytest` in CI or pre-commit.
*(≈ 1 session for the initial harness + engine tests.)*

---

## Suggested Order of Execution

| Step | Item | Why first |
|------|------|-----------|
| 1 | Diagram dots Phase A+B (placement engine + constant-size/LOD) | Your #1 complaint; self-contained |
| 2 | Graph Phase A (zoom preservation, downsampling, palette, antialias) | Your #2 complaint; quick wins |
| 3 | Graph Phase B (unit-grouped stacked subplots) | The "professional" look |
| 4 | Worker-thread calculations (3.1) | Biggest overall feel improvement |
| 5 | Graph Phase C+D, Diagram Phase C+D | Rounds out both tabs |
| 6 | Cleanup: logging, dead files, click handling (3.2–3.4) | Low risk, do alongside |
| 7 | Theme/error consistency, autosave, tests (3.5–3.7) | Ongoing hardening |

Each step should be its own session with user review before moving on
(per the project's per-phase approval convention).

---
---

# ROUND 2 — Plan from 2026-07-01 Screenshot Feedback (PLAN ONLY — no code until approved)

Three problems reported after the first implementation pass. Each was traced to a
specific root cause in the current code before planning the fix.

---

## R2-1. Diagram: dots/chips still overlap each other and component text

### Root causes (verified in code)

1. **Mixed coordinate spaces.** Dots and value chips render in *device* (screen) pixels
   (`ItemIgnoresTransformations`), but the edge-distribution pass spaces dots in *scene*
   units (fixed 18). Zoomed out to 60%, that 18-scene-unit gap becomes ~11 screen px
   while every dot stays 12 px — dots and their chips physically overlap
   (Condenser right edge: "72.6" printed over "76.5").
2. **Chips can point INTO the component.** Chip direction comes from the same
   `side` lookup table used for distribution. Wherever the lookup disagrees with where
   the dot actually sits, the chip lands inside the box on top of the title text
   ("P suc 51.9" over "[Compressor]").
3. **Component titles and chips fight for the same band.** Titles are scene-space
   items near the top-left of the box; device-space chips near top corners land on them
   at most zoom levels.

### Fix plan

- **F1 — Zoom-aware spacing.** The distribution pass takes the current view scale and
  spaces dots at `max(18, 16 / view_scale)` scene units, so dots are never closer than
  ~16 *screen* px. Re-run a lightweight "reposition-only" pass on zoom change
  (debounced ~150 ms; moves existing items, no scene rebuild). Hook into the existing
  `wheelEvent` / `zoom_in` / `zoom_out` / `zoom_to_fit` paths in `diagram_widget.py`.
- **F2 — Geometric outward direction.** Stop trusting the side lookup for chip
  direction. Compute it from geometry at placement time: compare the dot position to the
  component's scene rect — chip always extends *away from the rect center*
  (left edge → chip leftward, top edge → chip upward). The lookup table remains only
  for grouping dots per edge.
- **F3 — Reserve the title band.** Either (a) move component titles to the center of
  the box (they are short: "[Compressor]"), or (b) shift the topmost dot on left/right
  edges down below the title line. Decide (a) vs (b) at review — (a) is simpler and
  looks cleaner.
- **F4 — Same-corner stacking.** Where two ports resolve to the same corner
  (Condenser inlet + water_in at top-left), the F1 distribution already separates them
  vertically; verify visually and tune margins.
- **Verification:** launch the app on the 3-module template, screenshot at 50% / 100% /
  200% zoom, confirm zero overlapping chips (last round's miss — compile checks alone
  don't catch layout bugs).

## R2-2. Diagram: evaporator dots must match the real flow direction

### The physics (user-stated; matches the old comment in `_offset_role_dot_from_port`)
Refrigerant **enters from the TOP** (distributor → top header circuits) and
**leaves from the BOTTOM** (bottom header → suction line). The actual pipe ports already
live on the top/bottom headers. The current code *artificially relocates* circuit dots
to the left/right edges (`inlet_circuit_ → left`, `outlet_circuit_ → right`) — a
holdover from when side placement was considered less visually sensitive.

### Fix plan

- **F5 — Put circuit dots where the ports are.**
  - `inlet_circuit_N` → dot ON the top edge at the true port's x position
    (spread horizontally by the F1 pass if crowded).
  - `outlet_circuit_N` → dot ON the bottom edge, same rule.
  - `dist_inlet` → top edge; `dist_outlet` → bottom edge.
  - `sensor_top_N` / `sensor_bottom_N` (coil temp sensors) stay top/bottom as now —
    they then share those edges with circuit dots, so the horizontal distribution must
    interleave both groups (single pass per edge, sorted by x).
  - Update `_role_dot_side_for_port`; delete the Evaporator left/right relocation from
    `_offset_role_dot_from_port`.
- **F6 — Chips above/below, outside the box.** With F2, top-edge chips extend upward
  (into the thin distributor-pipe area — acceptable), bottom-edge chips downward. If
  the top row gets crowded, alternate chips above/below the dot row as a tiebreak.
- **Bonus:** evaporator left/right edges become free — the per-module SH/SC calc
  callouts (custom sensors "6.7" / "4.4") get those clean edges, removing their current
  overlap with the outlet dot column.

## R2-3. Graph: enabling a second sensor group appears to do nothing (REGRESSION)

### Root cause (verified at `graph_widget.py:424-426`)
The new zoom-preservation restores the previous X **and Y** range on *every* redraw.
Enable superheat (Y ≈ 0–15), then enable pressures (Y ≈ 50–200): the pressure curves
ARE plotted, but the Y window stays frozen at 0–15, so they render off-screen — looks
exactly like "the other group doesn't turn on". Before the change every redraw
auto-ranged, which showed everything (at the cost of losing zoom — the original
complaint). Both behaviors are needed, keyed on *why* the redraw happened.

### Fix plan

- **F7 — Preserve zoom only when the curve set is unchanged.** Track
  `self._last_plotted_sensors`. In `update_ui`:
  - Sensor list identical → restore previous X and Y (current behavior — user is
    zooming/filtering the same view).
  - Sensor list changed → keep the previous **X** range (the framed time window) but
    **auto-fit Y** to all curves visible in that window (reuse `fit_y_to_view()`);
    full `autoRange()` only on first plot or CSV change.
- **F8 — Unit-grouped stacked subplots (the real fix for "all sensor types at once").**
  One mixed Y axis can never show pressures and superheats together readably. Replace
  the single `PlotWidget` with a `GraphicsLayoutWidget` that builds one subplot per
  **unit family**, stacked vertically, all X axes linked:
  - Classification: map each column to a family — temperature (`T_*`, `S.H*`, `S.C*`),
    pressure (`P_*`), flow (`gpm*`, `m_dot*`), electrical (`W_*`, `A_*`, `V_*`),
    other/unitless — via the canonical alias DB (`sensor_canonical.py` +
    `library/sensor_aliases/`) first, name-prefix heuristics as fallback.
  - Only families with enabled sensors get a subplot; a single family behaves exactly
    like today's plot. Each subplot has its own Y axis with the family unit label;
    only the bottom subplot shows the time axis.
  - **Toolbar semantics:** Reset Zoom / Box Zoom / Lock X apply to all subplots
    (linked X); Lock Y and Fit Y apply per-subplot (Fit Y fits each). Same buttons,
    no new UI.
  - **Range select / defrost regions:** `LinearRegionItem` added to every subplot,
    positions synced both ways; applying reads from any one of them.
  - **Snapshot capture:** viewport = linked X range + per-subplot Y ranges; store
    per-family Y in `view_settings` (backward compatible — old snapshots restore into
    the first subplot's family).
  - **Stats table:** unchanged (already per-sensor), plus a "Family" column so rows
    group visibly.
- **F9 — Regression checklist** for the graph tab (until an automated harness exists):
  load CSV → enable temp group → enable pressure group → both visible; zoom in →
  enable third group → X preserved, Y fitted; disable all → re-enable → sane view.

---

## Round 2 execution order

| Step | Items | Size | Notes |
|------|-------|------|-------|
| 1 | F7 (graph regression) | small | Restores lost functionality — do first |
| 2 | F5 + F6 (evaporator flow-correct dots) | medium | Pure placement logic |
| 3 | F1 + F2 + F3 + F4 (overlap engine) | medium-large | Zoom-aware relayout is the tricky part |
| 4 | F8 (stacked unit subplots) | large | Pitch subplot layout mockup before building |
| 5 | F9 + GUI verification pass | small | Screenshots at 3 zoom levels, both tabs |

Each step lands separately with a visual check before the next; F8 gets a plain-language
pitch (layout sketch) before any code, per project convention.
