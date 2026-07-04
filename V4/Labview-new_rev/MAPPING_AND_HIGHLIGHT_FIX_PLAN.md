# Mapping, Highlight & Toolbar Fix Plan

Status: PLANNING ONLY — investigation completed 2026-07-02 against case
IDD5SL12WE with the CSVs in `DATA/IDD5SL12WE/`. Follows
`WORKFLOW_REDESIGN_PLAN.md`; this document covers three issues found while
using the partially-implemented Cases workflow:

1. The Diagram tab toolbar still carries authoring buttons that look redundant.
2. "Sensor data in the CSV is not loading onto the process diagram"
   (example given: center coil outlet).
3. Clicking a sensor label in the sensor panel no longer highlights the sensor
   on the diagram.

No code in this file. Implementers follow this top to bottom. Every claim
below was verified against the code/data at the cited location.

---

## Part 0 — Verified facts (the evidence everything below rests on)

| # | Fact | Evidence |
|---|---|---|
| F1 | None of the three IDD5SL12WE CSVs contain ANY coil-outlet column. They have `Left/CTR/Right Coil Inlet 1–6` but no outlet equivalents. Full 151-column header inspected. | `DATA/IDD5SL12WE/*.csv` header row |
| F2 | The status bar in the user's session read `Sensors: 246 | Mapped: 143 | Gaps CSV:0 Dots:102`. `CSV:0` means ZERO CSV columns failed to map; `Dots:102` means 102 diagram sensor slots have no CSV column feeding them. 143 + 102 ≈ 246 planned slots. | `sensor_panel.py:719–737` (`update_stats`), `data_manager.py:1810–1815` (gaps print) |
| F3 | Auto-mapping walks CSV columns → alias DB → free role key; unmatched columns get status `unknown`, slots with no column simply stay unmapped. | `data_manager.py:1708–1818` (`auto_map_csv_to_canonical`) |
| F4 | The click-to-highlight chain is: `sensor_panel.on_item_clicked` (`sensor_panel.py:236`) → `toggle_sensor_selection` (`data_manager.py:671–692`, emits `data_changed`) → `app.show_sensor_on_diagram` (`app.py:155–164`, forces Diagram tab) → `diagram_widget.locate_sensor` (`diagram_widget.py:893–938`). |
| F5 | `locate_sensor` ONLY searches `sensor_roles` (mappings). An unmapped/"Default" row can NEVER be located or highlighted — it exits with a console print `[LOCATE SENSOR] No visible diagram dot mapped to …` (`diagram_widget.py:899–929`). |
| F6 | Single-click selection is a TOGGLE: clicking an already-selected sensor clears the selection (`data_manager.py:686–691`), which also suppresses the cyan highlight. |
| F7 | Every diagnostic in this app is a `print()`. The app is launched via `Launch Lab Viewer.pyw`/`.vbs` — no console — and `logs/app_*.log` only captures the `logging` module (the 2026-07-02 logs contain 2 lines each). All `[LOCATE SENSOR]`, `[AUTO_MAP]`, `[MAP]` evidence is being thrown away at runtime. | `logging_setup.py`, `logs/` inspection |
| F8 | The `Import Mappings` toolbar button is a stub: it shows a "Not Implemented" message box and does nothing (`diagram_widget.py:523–526`). |
| F9 | `Save Layout` persists per-layout sensor-dot ON/OFF defaults keyed by the OLD topology schema (`_topology` → `_get_layout_key`, `diagram_widget.py:647–661`, `data_manager.py:2183–2191`). |
| F10 | Every `data_changed` emission triggers a FULL scene rebuild of the visible Diagram tab (`app.py:140` → `update_active_tab` → `diagram_widget.update_ui:440` → `build_scene_from_model`), i.e., a whole-scene teardown on every sensor-panel click. |
| F11 | Several CSV headers carry trailing spaces (`Right TXV Inlet `, `Into Right Distributor `, `Into Left Distrubutor ` — note also the "Distrubutor" typo). Alias matching strips whitespace on one side (`data_manager.py:1743,1769`) but mappings store the RAW column name (`data_manager.py:1797`). |

---

## Part 1 — Toolbar: what each button is, and its verdict

The user's instinct is right: in the case-centric workflow (diagram is
generated from the case and saved with it), day-to-day work happens in
Mapping/Analysis mode, and authoring tools are only needed to touch up
generator output. Verdicts:

| Button | What it actually does | Verdict |
|---|---|---|
| 📥 Import Mappings | Nothing — stub popup (F8) | **Delete now.** Its promised job ("restore mappings from a previous session") is exactly what Open Case does in the new flow. |
| 📦 Components ▾ | Palette to hand-place components | **Keep, but only in Drawing mode** (hidden otherwise). Needed to touch up generated diagrams until the generator is perfect. |
| ✏️ Edit ▾ (Group/Ungroup/Zoom/Add Sensor Box/Clear mappings/Delete custom sensors) | Mixed bag | **Split.** Zoom to Fit stays always-visible. Group/Ungroup/Add Sensor Box → Drawing mode only. "Clear All Sensor Mappings" / "Delete All Custom Sensors" are destructive — move behind Drawing mode too. |
| Mode: Drawing/Mapping/Analysis | Core mode switch | **Keep — and make it the toolbar's anchor.** Default mode after Open Case should be Mapping (not Drawing). |
| Snap to Grid | Drawing aid | Drawing mode only. |
| Straighten Pipes / Align Ports | Fix generator/hand-edit pipe geometry | Drawing mode only. |
| 💾 Save Layout | Saves dot ON/OFF defaults keyed by OLD schema (F9) | **Remove the button.** In the case-centric flow the case OWNS its diagram: dot ON/OFF changes should auto-persist into the case's saved diagram (`cases/<id>/diagram.json`) the same way other diagram edits do. The old-schema layout-key store is replaced by this (aligns with WORKFLOW_REDESIGN_PLAN §6.10). |

**Toolbar spec after the change:** always visible = `Mode:` selector + Zoom to
Fit. Drawing mode reveals the authoring group (Components, Edit, Snap,
Straighten, Align). Mapping/Analysis modes show a lean bar plus the new
"Mapping report" button (Part 2). No popups anywhere in this rework.

---

## Part 2 — "CSV data not loading onto the diagram" — root cause

### Root cause (verified, two layers)

**Layer 1 — the example sensor has no data in the file.** "Center coil
outlet" does not exist in any of the three CSVs (F1). The lab files include
coil INLET thermocouples (1–6 per coil) but zero coil OUTLET columns. The
status bar proves the general case (F2): **every single CSV column was
successfully mapped** (`Gaps CSV:0`); the 102 "missing" items are diagram
slots the generated diagram *offers* (coil outlets, door thermocouples, etc.)
for which the loaded CSV simply has no measurement.

**Layer 2 — the UI hides this distinction, so it reads as a loading bug.**
The sensor panel lists every planned slot with "Default" in the Sensor #
column, colored almost identically to rows that carry real data. There is no
way for the user to tell "this slot has no column in the file" apart from
"this data failed to load". The auto-map report and gaps data that would
explain it (`last_auto_map_report`, `get_mapping_gaps`) exist in memory
(F3) but have **no UI at all** — the only surfaces are a console print nobody
can see (F7) and a terse status-bar suffix.

### Fixes to implement

2.1 **CSV-driven visibility — FINAL RULE (owner decision 2026-07-03,
    revision 2; supersedes both the original "grey out empty slots" spec
    and revision 1's "grey rows inside groups / grey dots in Mapping
    mode"). With a CSV loaded there are NO grey placeholders anywhere:**

    - **Panel groups contain ONLY CSV-backed rows — all green.** Planned
      slots with no CSV column (coil outlets, missing return-air probes,
      calculated slots with no source, etc.) are NOT listed — no italic/grey
      "—" rows inside groups. Group headers count only what's shown
      (`Coil - CTR (6)` not `(6/12)`).
    - **One "Ungrouped" section at the bottom** lists CSV columns that
      matched nothing on the diagram — data that arrived with no home.
      This is the only non-green content in the panel, and it's where the
      user decides how to teach the app the new column (see 2.1b).
    - **Diagram: dots with no CSV data are hidden in ALL modes, including
      Mapping.** No grey dots at all.
    - **Reveal-on-demand replaces Mapping-mode grey dots:** selecting an
      Ungrouped sensor while in Mapping mode temporarily reveals the hidden
      candidate dots (ghosted) so one can be clicked to map; they hide
      again once the sensor is mapped or deselected. This keeps manual
      mapping possible without permanent grey clutter.
    - **Before any CSV is loaded**: the panel and diagram show the planned
      slots as today (nothing else exists to show); the CSV-driven view
      replaces it at load time and reverts if the CSV is cleared.

2.1b **"Teach the database" flow for Ungrouped columns.** Right-clicking an
    Ungrouped sensor offers "Assign to diagram spot…" (the reveal-on-demand
    mapping above) and "Save as alias of…" (pick the canonical sensor it
    represents; writes to the alias DB so every future CSV auto-maps it).
    The Mapping report (2.2) lists the same ungrouped columns so they can
    be worked through in one sitting.

2.2 **Mapping report dialog.** New button ("Mapping report…") in the sensor
    panel footer, enabled after a CSV loads. Three sections, driven entirely
    by data that already exists (F3): (a) mapped columns with their dot
    (role/canonical), (b) CSV columns that matched nothing (status
    `unknown`), (c) diagram slots with no CSV column (the current 102), each
    with its human label. Exportable to CSV. This turns the invisible
    `[AUTO_MAP]` print into something the user can act on.

2.3 **Auto-map determinism check.** `auto_map_csv_to_canonical` assigns each
    column to the FIRST free role key (`data_manager.py:1789`) in enumeration
    order. Verify (and if needed enforce) that numbered columns land on the
    matching numbered circuit dot — `CTR Coil Inlet 4` must map to circuit 4's
    dot, not "the first free inlet dot". Sort candidate role keys by their
    circuit index before assignment; add a regression test with the
    IDD5SL12WE header.

2.4 **Normalize CSV headers at load.** Strip leading/trailing whitespace from
    all column names once in `load_csv` (F11). The alias DB already strips
    for matching; storing raw names with trailing spaces into `sensor_roles`
    creates permanent whitespace-sensitive keys downstream (see also Part 3).
    Keep a one-time cleanup that strips existing `sensor_roles` values when a
    session loads.

### Superseded note

An earlier revision of this plan said "do not hide the empty slots, grey
them." The owner has since decided the opposite (2.1 above): hide them
everywhere except Mapping mode. The planned slots still exist in the diagram
model — hiding is a VIEW rule, not a deletion — so a future CSV that includes
coil-outlet columns lights them up again automatically.

---

## Part 3 — Click-to-highlight — root cause

### Root cause (two distinct causes, one primary)

**Primary (verified): highlight is impossible for exactly the rows the user
is clicking.** `locate_sensor` only searches existing mappings
(`sensor_roles`) for the clicked name (F5). Unmapped/"Default" rows — coil
outlets, door thermocouples, i.e., the rows the user clicks while
investigating issue #2 — have no mapping, so locate exits silently (its
"couldn't find it" message is a print nobody sees, F7). The panel row KNOWS
its canonical id and shows it in the tooltip (`sensor_panel.py:433–439`), but
never passes it along.

**Secondary (verified behavior, compounds the confusion):**
- Clicking an already-selected sensor DESELECTS it (F6) — so the second click
  on the same row removes the highlight, which reads as "highlighting is
  flaky".
- Every click triggers a full scene rebuild (F10): slow with ~246 dots, and
  any transient flash effect is rebuilt-over.
- Whitespace-sensitive keys (F11): rows whose mapped CSV column has a
  trailing space depend on exact string equality along the chain
  (`locate_sensor` compares `mapped != sensor_name` at
  `diagram_widget.py:901`); any later normalization on one side breaks those
  specific sensors.

### Fixes to implement

3.1 **Locate must work for unmapped slots (the primary fix).** The panel emits
    the row's canonical id alongside the operational key (extend
    `sensor_locate_requested` or add a parallel signal). `locate_sensor`
    resolution order becomes: mapped sensor name → role key → **canonical id
    → `dot_items[canonical/role_key]` even when unmapped** (the dots exist,
    grey, in `dot_items` — `diagram_widget.py:1954, 2118`). Clicking "Center
    Coil Outlet 3" then centers and flashes the grey dot, with a status-bar
    note "No data mapped to this spot in the loaded CSV" — tying Part 2 and
    Part 3 together for the user.

3.2 **Decouple highlight from selection toggling.** A single click always
    locates + flashes (temporary ~2 s pulse that survives repaints), and
    separately sets selection. Deselection (toggle-off) must not suppress the
    locate flash. Keep multi-select semantics unchanged.

3.3 **Stop rebuilding the scene on selection-only changes.** Selection
    changes should call `update_sensor_dots` (which is already
    selection-aware, `diagram_widget.py:2253–2286`), NOT
    `build_scene_from_model`. Introduce a lightweight `selection_changed`
    signal (or a flag on `data_changed`) so `app.update_active_tab` skips the
    rebuild when only selection changed. This fixes both flash survival and
    click latency.

3.4 **Make the diagnostics visible (do this FIRST).** Route stdout prints
    into the existing logging setup (a stdout→logging redirect in
    `logging_setup.py`), so `[LOCATE SENSOR]`, `[AUTO_MAP]`, `[MAP]` lines
    land in `logs/app_*.log` even under the `.pyw` launcher. Every remaining
    "it silently doesn't work" report becomes diagnosable from the log file.
    (Longer term the redesign says these flows shouldn't need popups OR
    console archaeology — but the log capture is one small change that pays
    for itself immediately.)

### Verification procedure for the implementer

1. Apply 3.4 first. Launch, load the IDD5SL12WE case + `DataDOE081.csv`.
2. Click a MAPPED row (e.g., "Suction Pressure"): log must show a locate hit;
   diagram centers and the dot flashes. Click it again: flash still happens
   (3.2), selection toggles off.
3. Click an UNMAPPED row (e.g., a coil outlet): diagram centers on the grey
   dot and flashes it; status bar explains no data (3.1). Before the fix, the
   log will show `[LOCATE SENSOR] No visible diagram dot mapped to …` — that
   line is the confirmation of the primary root cause.
4. Click rows whose CSV column has a trailing space (`Right TXV Inlet `,
   `Into Right Distributor `): locate must still hit after 2.4's
   normalization.
5. Status bar `Selected:` count must match panel selection after each click
   (`sensor_panel.py:726` counts tree items, not `selected_sensors` — align
   the two while in there).

---

## Part 4 — Implementation order

1. **3.4 log capture** (tiny, unblocks diagnosis of everything else).
2. **2.4 header normalization** + one-time session mapping cleanup.
3. **3.1 + 3.2 locate/highlight rework**, then **3.3 rebuild-avoidance**.
4. **2.1 panel visual states + 2.2 mapping report dialog.**
5. **2.3 auto-map determinism** (verify first; fix only if circuit numbers
   actually shuffle).
6. **Part 1 toolbar rework** (delete stub, mode-gate authoring tools, remove
   Save Layout in favor of case-owned persistence — coordinate with
   WORKFLOW_REDESIGN_PLAN §6.10/Phase 3 so the layout-key store is replaced,
   not duplicated).

Acceptance for the whole plan: with the IDD5SL12WE case open and
`DataDOE081.csv` loaded — the sensor panel lists ONLY the 150 CSV columns;
every row inside a group is green/mapped; zero italic/grey placeholder rows
exist anywhere in groups; CSV columns with no diagram home appear solely in
the "Ungrouped" section; the diagram shows NO grey dots in ANY mode;
selecting an Ungrouped sensor in Mapping mode temporarily reveals ghosted
candidate dots for click-mapping; right-clicking an Ungrouped sensor offers
"Save as alias of…" which persists to the alias DB; clicking any CSV-backed
row centers and flashes its dot; the mapping report still lists the hidden
no-data slots (hidden, not deleted); the toolbar shows only Mode + Zoom
(+ report) outside Drawing mode.
