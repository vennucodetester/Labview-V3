# Workflow Redesign Plan — Case-Centric Single Entry Point

Status: APPROVED DIRECTION (owner decisions recorded 2026-07-02; external review
resolved same day — see `PLAN_REVIEW_RESOLUTIONS.md`). Planning document —
no code in this file. Implementers follow this top to bottom.

Owner decisions this plan is built on:
1. **One case, many tests** — a case is configured once; test requests are small
   records attached to it.
2. **Open case first, then CSV** — the session always knows which case it belongs to.
3. **Formula-only diagram generation** — delete the abandoned wizard and the
   hand-drawn-template-reuse machinery.
4. **Case families are real product lines** — Insight and Reach-in today, FW and
   others later. Each family carries fixed physical rules (§5b), so the picker
   derives geometry instead of asking for it.
5. **Cassettes are a system choice, not a case kind** — cassettes can be fitted
   in either family; cassette count may differ from door/module count; cassette
   airflow can be conventional or reverse.
6. **Defrost type is a configuration choice** (hot gas / cool gas / electric /
   off-time / none), usually LT but sometimes MT — so it is asked, not inferred.
7. **No live preview** in the picker. Condenser default = Water (Air available).
8. **No migration** — the old request library is considered unreliable; the
   owner recreates every case fresh. Old data is archived, not converted (§7).
9. **Reach-in pitch is 30 inches** (doors, mullions, shelf columns) — matches
   existing code; the earlier 32" figure was wrong.

---

## 1. The core concept change

Today the app has ONE merged object (the Test Request) that mixes case identity,
topology, parts, settings, and pass/fail targets — and the session has no link to
it, forcing the user back through the dialog during testing.

The redesign splits this into two objects and links the session to the first:

```
CaseConfiguration  (created ONCE per physical case, reused forever)
 ├─ identity:  case model name (e.g. ID5SL12), notes
 ├─ topology:  output of the new step-by-step picker (§5)
 ├─ parts:     compressor / condenser / txv / coil / distributor / fan
 │             (catalog references + frozen snapshots — mechanism unchanged)
 ├─ settings:  refrigerant, charge, water GPM, fan CFM, defrost schedule, setpoints
 ├─ diagram:   the generated process diagram model, saved WITH the case
 └─ default targets (seed values for new tests)

TestRequest  (many per case, cheap to create)
 ├─ test type (ELP), title, objective
 ├─ targets (pre-filled from the case's defaults, editable per test)
 ├─ revisions, request number — unchanged from today
 └─ case_id  (the case it belongs to)

Session  (the live working state)
 └─ case_id + refrigerant — BOTH persisted in session JSON and in the
    auto-save/undo state (§6.9)
    (active test_request_id: deferred, see §10.1)
```

Storage layout (replaces `library/projects/…`):

```
library/
  catalogs/            (unchanged — parts catalogs, KEPT as-is)
  elp_codes.json       (unchanged, KEPT)
  case_families.json   (NEW — family rulebook, §5b)
  cases/<case_id>/case.json        ← topology, parts refs, settings, defaults
  cases/<case_id>/diagram.json     ← generated diagram model
  cases/<case_id>/tests/<test_id>.json
```

There is **no project level**. The project concept is removed everywhere,
including the printable export, which prints the case model + case summary
block instead of a project name.

---

## 2. The single entry point

One menu / toolbar action: **"Cases"** → opens the **Case Library screen**.
It is the ONLY way diagrams and test requests are created or opened.

Case Library screen contents:
- Searchable list of all cases (case model, family, topology one-liner, #tests,
  last used).
- Buttons: **Open Case**, **New Case…**, **New Test for selected case…**,
  **Open/Export Test…**.
- Double-click a case = Open Case.

Remove every other diagram entry point (full deletion list in §9):
- "New Diagram" button on the Diagram tab (`TopologyPreviewDialog`).
- "Test simple" button on the sensor panel (already broken today — §9 note).
- The `Test Requests` menu (replaced by Cases).
- The dead `new_diagram_wizard.py` and template-matching path (§8).

---

## 3. Flow A — first time with a new case ("New Case…")

A single guided dialog with a left-side step list, moving forward only:

1. **Identity** — case model name (free text w/ duplicate check), notes.
2. **Topology** — the new progressive picker (§5). Nothing else on screen.
3. **Parts** — same catalog combos as today (unknown part → NewPartDialog,
   unchanged). Cross-checks from §6.7 run here.
4. **Settings** — refrigerant, charge, GPM, CFM, defrost schedule, setpoints.
   (Defrost *type* was already answered in the picker; here it's the schedule.
   If defrost type is `none`, no schedule is asked.)
5. **Review & Create** — read-only summary of every derived + chosen value.

On **Create**:
- Generate the diagram (formula generator, §6), save it into the case folder.
- Load the case into the session (diagram + settings + rated inputs, §4 rules).
- Jump to the Diagram tab. **No confirmation popups, no info popups** —
  a transient status-bar message only ("Case ID5SL12 created and loaded").

## 4. Flow B — every time after ("Open Case")

One click. Silently and automatically:
1. Diagram model → session (replacing current; if the current session has
   unsaved sensor mappings on a DIFFERENT case, one confirm — the only popup
   allowed in this flow).
2. Refrigerant → session.
3. Rated inputs derived from the compressor part snapshot + water GPM
   (existing `compressor_to_rated_inputs` logic — keep it, relocate it).
4. Compressor displacement/RPM onto diagram Compressor components.
5. `session.case_id = case.id`. Saved sessions and auto-save states carry it,
   so reopening a session restores the case link without touching the library.

Then the testing phase is just: **Open Case → Load CSV → work.** The existing
canonical auto-mapping (`auto_map_csv_to_canonical`) runs as it does today.
The test request dialog is never needed during testing.

If a CSV is loaded with no case open: non-blocking banner on the sensor panel
("No case loaded — open one from Cases") — do NOT block ad-hoc CSV browsing.

## 4b. Flow C — new test on an existing case ("New Test…")

Small form, nothing about the case in it:
- Test type (ELP), title, objective.
- Targets table, pre-filled from the case's default targets.
- Buttons: **Save**, **Save + Export printable** (existing HTML export, reuse
  `request_to_html`; the export's former project-name slot now prints the case
  model + case summary pulled from the case).

---

## 5. Topology picker — total overhaul (progressive disclosure)

Principle: **one decision at a time; a decision that is answered or made
redundant by an earlier choice is never shown.** Steps appear only after the
previous step is answered; changing an earlier step resets the steps that
depend on it.

```
Step 1  Case family                    Insight | Reach-in   (extensible, §5b)
                │
Step 2  Size   Insight  → "How many modules?"  1–3   (48" each → 4/8/12 ft)
               Reach-in → "How many doors?"    1–5   (30" each)
                │
Step 3  Open or Doored?                Insight ONLY (Reach-in is always doored
                                        — question never shown)
                │
Step 4  Temperature class MT | LT      Reach-in ONLY (Insight is always MT
                                        — question never shown)
                │
Step 5  Refrigeration system           Shared compressor | Cassettes
          if Cassettes:
            5a  How many cassettes?    1–5  (independent of Step-2 count —
                                        a 3-door case may have 2 cassettes;
                                        layout rule in §6.8)
            5b  Airflow                Conventional | Reverse
                                        (Reverse = return air ABOVE the fans,
                                         discharge air BELOW the fans)
                │
Step 6  Circuits
          Shared + Insight   → "Circuits per coil (per module)"   1–12, default 6
          Shared + Reach-in  → "Total circuits"                    1–12, default 6
          Cassettes          → "Circuits per cassette"             1–12, default 6
                │
Step 6b Expansion device            TXV | Cap Tube | EEV   (default TXV)
          (one choice per case; applies to every module/cassette loop.
           Drives which component is drawn, whether a sensing bulb exists,
           and which sensor slots are generated — see §6.11)
                │
Step 7  Defrost type       none | off_time | electric | hot_gas | cool_gas
          (asked for EVERY case regardless of temp class — usually LT has one,
           but some MT cases do too. hot_gas / cool_gas add defrost valve
           hardware to the diagram, §6.4. none vs off_time draw the same
           hardware — nothing — but differ in settings/export wording, and
           `none` skips the defrost-schedule field in Settings.)
                │
Step 8  Condenser cooling              Water (default) | Air
                │
Step 9  Shelf rows                     3–8
```

**Derived silently — never asked, never shown** (this kills today's Family,
System type, Case type dropdowns and the Doored checkbox):

| Fact | Insight | Reach-in |
|---|---|---|
| Case length | modules × 48" | doors × 30" |
| Mullions | every 48" + LH & RH ends | every 30" + LH & RH ends |
| Doors (if doored) | French style, 2 per 48" module | 1 per 30", always |
| Air curtain bands | dual (Primary + Secondary discharge) | single (Primary only) |
| Shelf width | 48" columns | 30" columns |
| Temp class | MT always | (asked, Step 4) |
| system_type | shared or cassette per Step 5 | same |
| Fan direction | conventional, unless cassette + Reverse chosen | same |

**Stored topology schema** (single source of truth, ONE count field — today all
four counts are saved with stale values):

```
{ family, size_count, open_or_doored, temp_class,
  system: shared|cassette, cassette_count?, cassette_airflow?,
  circuits, expansion_device: txv|cap_tube|eev,
  defrost_type, condenser_cooling, shelf_rows }
```

This replaces today's `mode` / `cassette_mt` / `cassette_lt` distinction:
"Cassette LT" is now simply *cassettes + a gas-defrost type* — the hardware
follows from the defrost answer, not from a separate case kind.

No live preview (owner decision). The Review step (§3.5) shows the derived
facts as text so the user can verify before Create.

## 5b. The family rulebook (future-proofing for FW and others)

All family-specific physical rules live in ONE data file
(`library/case_families.json`), not in code branches:

```
{ "insight":  { "display": "Insight",  "module_pitch_in": 48,
                "size_question": "modules", "size_range": [1, 3],
                "door_style": "french_pair_per_module",
                "open_allowed": true,  "air_curtains": "dual",
                "shelf_width_in": 48,  "temp_classes": ["MT"] },
  "reach_in": { "display": "Reach-in", "module_pitch_in": 30,
                "size_question": "doors", "size_range": [1, 5],
                "door_style": "one_per_pitch",
                "open_allowed": false, "air_curtains": "single",
                "shelf_width_in": 30,  "temp_classes": ["MT", "LT"] } }
```

Adding the FW family later = adding one entry to this file (plus any new
door-style renderer if FW needs one). The picker builds Steps 1–4 from this
data; it never hardcodes family names.

---

## 6. Diagram generation — formula only, with accuracy fixes

Keep exactly one generator: `build_bare_minimum_diagram` (rename to
`generate_case_diagram`, input = the new topology schema + family rulebook).
Fix these known wrong-decision sources:

1. **Stale cassette circuits (bug).** The old dialog disabled the circuits
   spinner for cassettes but the generator still consumed its leftover value.
   Fixed structurally: circuits per cassette is an explicit Step-6 answer.
2. **Hardcoded Water/shared (bug).** The Diagram-tab quick path forced
   `condenser_cooling='Water'`, `system_type='shared'` regardless of reality.
   Fixed by deleting that path — the case topology is the only input.
3. **Ignored/conflicting fields.** `family`, `system_type` combo, `doored`
   checkbox, `case_type` combo could disagree with the button rows and were
   partly ignored. Fixed by derivation (§5) — one source of truth.
4. **Defrost hardware decoupled from case kind.** Today the HGBV / Hot Gas
   Solenoid / Liquid Line Solenoid set is welded into the `cassette_lt`
   drawing branch. Restructure it as a composable add-on that ANY loop
   (shared or cassette, MT or LT) receives when `defrost_type` is `hot_gas`
   or `cool_gas`. `electric`, `off_time`, `none` draw nothing extra on the
   refrigeration loop (electric defrost watts already live in the electrical
   sensor box). This is restructuring work, not a field rename.
5. **Airflow direction is an explicit flag.** Reversed bands (return above
   fans, discharge below) currently trigger off `is_cassette`; new rule:
   trigger off `cassette_airflow == reverse` only.
6. **Family geometry drives decorations — by adaptation.** Door/mullion/air-band
   drawing code already exists in `build_bare_minimum_diagram`; the work is
   rewiring it to the family rulebook (§5b) and new schema, not writing it
   from scratch. Includes consolidating the shelf-width constants — today
   hardcoded as `48 if modular else 30` in TWO places
   (`diagram_from_request.py:1185` and `data_manager.py:1902–1904`) — into a
   single rulebook lookup.
7. **Parts vs topology cross-checks (new, non-blocking warnings at Review):**
   - Condenser part `cooling_type` ≠ Step-8 cooling → warn, offer to sync.
   - Coil part `circuits` ≠ Step-6 circuits → warn, offer to sync.
   - Distributor part `outlets` ≠ Step-6 circuits → warn.
   Warnings never block Create; they exist so the diagram and the parts list
   can't silently contradict each other again.
8. **Cassette-vs-size layout rule (new).** Cassette count is independent of
   door/module count. Rule: cassettes divide the case width EVENLY; loops,
   fans, and loop labels (LH/CTR/RH or U1…Un) belong to cassettes; doors,
   mullions, and shelf columns stay on the family's own pitch grid. The two
   grids are NOT aligned to each other.
9. **Session persistence (gap found in review).** `save_session_to_dict`
   (~`data_manager.py:1483`) currently omits `refrigerant`. It must persist
   BOTH `case_id` and `refrigerant`; the undo stack reuses the same
   serializer, so undo automatically carries them. Acceptance: open case →
   change refrigerant → save → reload → both survive; Ctrl+Z never drops the
   case link.
10b. **Expansion device drives components and sensors (owner addition
    2026-07-03).** The Step-6b choice applies to every expansion circuit
    (each module of a shared system, each cassette loop):
    - **TXV** → TXV component per circuit + **sensing-bulb dot on the
      suction line at that circuit's evaporator outlet** (canonical
      `T_txv.{tag}.bulb`) + TXV-inlet temp slot + TXV subcooling callout.
    - **Cap Tube** → CapTube component (drawn in the same position) —
      **NO bulb dot anywhere, and no bulb role/canonical is enumerated**
      for the case. Liquid-line inlet temp slot and subcooling callout
      remain (they measure the liquid line, not the valve).
    - **EEV** → EEV component — no mechanical bulb; instead an
      **EEV suction-temp probe dot** at the same suction-line location
      (canonical `T_eev.{tag}.suction`), plus an optional instrument slot
      for the EEV control signal (`eev_pos.{tag}`, "EEV Position %") on the
      System & Flags card, since electronically controlled valves usually
      log it.
    Changing a case's expansion device later regenerates these slots; any
    sensor previously mapped to a slot that no longer exists (e.g., bulb
    columns after switching to cap tube) must surface in the Mapping
    report as a conflict — never silently dropped.
    Parts catalog: the `txv` part type generalizes to an **expansion
    device** part with a kind field (txv / cap_tube / eev) and
    kind-specific spec fields (TXV: nominal tons, refrigerant; cap tube:
    bore/length; EEV: model, steps/max opening). Cross-check (§6.7): part
    kind must match Step-6b, warn on mismatch.

10. **Old-schema readers inside data_manager (gap found in review).**
    `data_manager.py:1900` reads `_topology.mode`; `:2183–2191` derives the
    sensor-point-defaults key from `circuits_per_coil` + per-mode counts.
    No compatibility shim (no old data survives — §7): update these readers
    to the new schema in the same phase that introduces it. The
    sensor-defaults key becomes
    `family / size_count / system / cassette_count / circuits`.

---

## 7. No migration — fresh start (owner decision)

The old request library is considered unreliable; nothing is converted.

- On first launch of the new version: zip `library/projects/` into
  `library/_archive_projects_<date>.zip`, then remove the live folder.
  The archive is the only record of old requests.
- `library/catalogs/` and `elp_codes.json` are KEPT untouched — part
  datasheets are clean and expensive to re-enter.
- The owner recreates each case through the New Case flow as it is needed.
- No migration script, no conflict handling, no legacy-project metadata.

---

## 8. Background note for implementers (why deletions are safe)

Two large diagram subsystems are already unreachable from the UI:
- `new_diagram_wizard.py` (old configuration dialog) — no caller.
- The template-matching path: `build_diagram_for_request`,
  `build_shared_from_template`, `_pick_template`, `_template_index` in
  `diagram_from_request.py`, plus `diagram_templates.py` (procedural fallback),
  `diagram_template_loader.py`, `diagram_template_patcher.py`,
  `diagram_template_map.json`, and the `templates/` folder. Its purpose was to
  clone previously hand-drawn diagrams; the owner has chosen formula-only.

## 9. Deletion list

| Item | Action |
|---|---|
| `new_diagram_wizard.py` | delete file |
| `diagram_templates.py` | delete file |
| `diagram_template_loader.py`, `diagram_template_patcher.py`, `diagram_template_map.json` | delete |
| `templates/` folder | delete (archive a zip first) |
| `diagram_from_request.py`: `build_diagram_for_request`, `build_shared_from_template`, `_pick_template`, `_template_index`, `_load_template`, label-normalization helpers used only by them | delete functions |
| `diagram_widget.py`: `TopologyPreviewDialog`, `on_new_diagram_clicked`, the "New Diagram" toolbar button | delete |
| Sensor panel `test_simple_button` + `app.test_simple_diagram` | delete — NOTE: this button is ALREADY broken; it imports `build_simple_loop_diagram`, which does not exist anywhere. Deleting is a bug fix. |
| `app.py` `Test Requests` menu (`new_test_request`, `open_test_request`) | replace with single `Cases` action |
| `test_request_dialog.py` action buttons: `Generate process diagram`, `Save + Apply to session` | removed — behavior absorbed by Open Case (§4); dialog itself is replaced by New Case dialog (§3) + New Test form (§4b) |
| Project concept: `TestRequestLibrary.projects()`, `add_project`, project combo in the dialog, project name in `request_to_html` | remove; export prints case model + summary instead |
| `library/projects/` data | archive as zip, remove live folder (§7) |

## 10. Deferred items (agreed to add later, not in this build)

1. **Active test tracking in-session** (title-bar indicator, scorecard wiring).
   Owner has no master plan for this yet; the `case_id` link ships now and a
   `test_request_id` slot can be added to the session schema without breaking
   anything.
2. **FW case family** — added via the family rulebook (§5b) when defined.
3. Default target values per temp class (e.g., LT product temp band) — seed
   MT defaults as today; LT defaults TBD by owner.

## 11. Implementation order

1. **Data layer**: new library schema (cases/tests, family rulebook), archive
   of old `library/projects/` (§7), session `case_id` + `refrigerant`
   persistence (§6.9). No UI changes yet.
2. **Case Library screen + Open Case flow** (§2, §4). Session linkage done here.
3. **New Case dialog with progressive topology picker** (§3, §5, §5b) +
   generator input-schema change, accuracy fixes (§6.1–6.5, 6.7, 6.8), and
   updating data_manager's old-schema readers (§6.10) in the same phase.
4. **Generator visual adaptation** (§6.6 — rewire existing mullion/door/air-band
   drawing to the family rulebook; consolidate shelf-width constants).
5. **New Test form + export** (§4b, project-free export).
6. **Deletions** (§9) + remove old menu; final pass on popups (only the single
   confirm in §4 remains).

Each phase leaves the app runnable; phases 1–2 can ship before the picker
overhaul lands.
