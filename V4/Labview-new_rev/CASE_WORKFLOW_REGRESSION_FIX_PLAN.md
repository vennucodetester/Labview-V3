# Case Workflow Regression — Root Causes & Fix Plan

Status: PLANNING ONLY (investigated 2026-07-02, late evening). Companion to
`WORKFLOW_REDESIGN_PLAN.md` (the approved design) and
`MAPPING_AND_HIGHLIGHT_FIX_PLAN.md`. This document covers the two complaints
after the first Cases implementation landed:

1. "I can't open the process diagrams."
2. "Something extra was created that talks about test requests again, and it
   opens the old method of creating a process diagram."

Every root cause below was verified by reading the code at the cited line, by
log evidence in `logs/`, or by headless reproduction (offscreen Qt, real
library data). The implementer should re-run the reproductions in Part 3
before and after fixing.

---

## Part 0 — What was verified to WORK (do not "fix" these)

- **Open Case works end-to-end in this app copy.** Offscreen full-GUI
  simulation: `CaseLibraryDialog.open_selected()` on case `IDD5SL12WE` →
  `apply_case_to_session` → 56 components, 615 scene items, zoom-to-fit 0.32,
  entire diagram inside the viewport. The implementer's own smoke logs
  (`case-open-smoke-ok IDD5SL12WE 56 47 615`, 23:07) agree.
- `generate_case_diagram` works for the stored topologies.
- Session loading (via the folder button) still works — log 23:17 shows a
  session with 147 mappings loading fine.
- The stdout→log capture from the earlier plan was implemented and works
  (all print diagnostics now land in `logs/app_*.log`).
- The old Diagram-tab "New Diagram" button, `TopologyPreviewDialog`, and the
  broken sensor-panel TEST button were correctly deleted.

So "can't open" is NOT a crash in the Open Case path. The causes are below.

---

## Part 1 — Root causes

### RC-1 (the "extra thing"): the legacy Test Request system was kept,
### violating the approved plan

`app.py:361–365` re-adds a **Test Requests** menu ("New Test Request…",
"Open Test Request…") pointing at the ORIGINAL `test_request_dialog.py`,
which still contains the old 4-row topology button UI (`_pick_modular`,
line 355) and the old **Generate process diagram** button (line 327,
handler `_on_generate_diagram` line 528). `WORKFLOW_REDESIGN_PLAN.md` §9
explicitly ordered this dialog replaced and the menu removed. This is the
"old method" the user rediscovered.

### RC-2 (the dangerous one): the legacy dialog silently OVERWRITES the open
### case's saved diagram — this is the most likely cause of "can't open my
### process diagrams"

Verified mechanism:
- `app.py:151` connects `diagram_model_changed` → `save_active_case_diagram`.
- `save_active_case_diagram` (app.py:432–443) writes the CURRENT
  `diagram_model` into `library/cases/<case_id>/diagram.json` whenever
  `_case_diagram_autosave_enabled` is True and `case_id` is set.
- Opening a case sets both (`app.py:394–396`).
- The legacy dialog's Generate (`test_request_dialog.py:550`:
  `dm.diagram_model.clear(); update(model)` + emit) **never clears `case_id`
  or the autosave flag**.

Sequence: open case → later open the legacy Test Request dialog → click
Generate → the legacy-generated diagram (old topology, no case linkage,
sensor mappings wiped) is INSTANTLY autosaved over the case's `diagram.json`.
From then on, opening that case loads the wrong/blank-looking diagram —
experienced as "I can't open my process diagrams", and hours of sensor
mapping stored in the case diagram are gone. The same hole exists for ANY
future code path that swaps `diagram_model` without clearing the case link
(e.g., loading a plain session: `open_session_file_dialog` DOES clear the
flag at app.py:195 — the legacy dialog is the one that doesn't).

### RC-3: migration was implemented despite the owner's explicit "no
### migration" decision

`case_library.py:284–334` (`migrate_projects_if_needed`, called from
`app.py:371`) seeded `library/cases/` from the old request library the owner
called unreliable — 5 auto-created cases (ID6SU12WE, IDD5SL12WE, IDD5SL8WE,
IDD6SU12WE, RLN5MA) with topologies derived from the messed-up old data.
`WORKFLOW_REDESIGN_PLAN.md` decision #8 / §7 says: archive, don't convert.
CAUTION: the user has since worked inside migrated case **IDD5SL12WE** (its
`diagram.json`, 78 KB, holds their ~147 sensor mappings) — that one must be
preserved.

### RC-4: the New Case dialog is NOT the approved progressive picker

`case_dialogs.py:157–324` shows every topology field at once (family, size,
open/doored, temp class, system, cassettes, airflow, circuits, defrost,
cooling, shelf rows in one flat form) with only enable/disable syncing. The
owner's core requirement — "one decision at a time; redundant options never
shown" (§5) — is not implemented. Also two spec deviations inside it:
- `defrost_type` combo (line 208) is missing `off_time` (spec: five values).
- Family rulebook (`case_library.py:36–44` AND the already-written
  `library/case_families.json`) uses Reach-in pitch/shelf **32** — the
  resolved decision is **30** (PLAN_REVIEW_RESOLUTIONS.md Finding 7). Note
  `ensure_family_rulebook` will NOT overwrite the existing JSON file; both
  the constant and the on-disk file must be corrected.

### RC-5: the "open a case/diagram file" fallback is filename-magic and fails
### silently

`open_case_or_diagram_file` (app.py:201–266) only recognizes files literally
named `case.json` or `diagram.json`. Anything else returns False (log
evidence: `case_handler False` twice at 23:13) and silently falls through to
legacy session loading. A case or diagram JSON that was renamed, exported, or
lives outside the library opens as a "session" — producing garbage or nothing,
with no message. This is a second contributor to "can't open the process
diagrams."

### RC-6: launcher rewriting reaches into the OTHER app copy

`launch_sync.py` force-rewrites `Launch Lab Viewer.cmd` in BOTH this folder
and `…/Lab viewer/HVAC_Dev/V3/Labview-new_rev/` (a second, older copy of the
app that contains the user's old sessions/diagram JSONs) to point at THIS
copy. If the user launches from the V3 folder expecting that environment,
they silently get this app + this library instead — their old diagrams appear
"gone". Even if intended, doing this silently on every startup is wrong.

### RC-7 (minor, latent): init-order fragility around the mode combo

Log 22:48 shows `on_mode_changed → build_scene_from_model →
AttributeError: 'DiagramWidget' object has no attribute 'scene'` — the
mode-combo signal can fire before the scene exists (toolbar is built before
the scene in `setupUi`). It surfaced in a dev harness, but the ordering
hazard is real in the shipped code.

### RC-8 (hygiene): stored topology is a merged old+new blob with a
### merge-order bug

`ensure_old_topology` (case_library.py:68–124) writes BOTH schemas into
`case.json` topology, and line 122 (`legacy.update(topo)`) lets STALE old
keys (e.g., a previously stored `mode`) override freshly derived ones — so
editing a case's new-schema fields may not change what the generator sees.
Line 123 is a no-op. The plan's schema (§5: store ONLY the new schema, derive
the legacy view on demand) was not followed.

---

## Part 2 — Fix plan (ordered)

**Step 1 — Close the corruption hole first (RC-2).**
`save_active_case_diagram` must refuse to write unless the diagram in memory
actually belongs to the open case: tag the in-memory model with the case id
when a case is applied (`diagram_model['_case_id'] = case['id']` inside
`apply_case_to_session`) and require it to match `data_manager.case_id`
before saving. Independently: ANY flow that replaces `diagram_model` outside
the case system must clear `case_id` and the autosave flag. (Step 2 removes
the main offender, but the guard must exist regardless — it is the last line
of defense for case data.)

**Step 2 — Remove the legacy Test Request system (RC-1).**
Delete the `Test Requests` menu (app.py:361–365) and `new_test_request` /
`open_test_request` / `_legacy_test_library`. Gut `test_request_dialog.py`
down to `NewPartDialog` (still used by `case_dialogs.py:36`) — move it into
its own module (`part_dialogs.py`) and delete the rest of the file. Keep
`test_request_library.py` as the parts-catalog/HTML-export data layer (it no
longer gets a UI). Anything the old dialog did that users still need
(printable export, targets) already exists in the Cases dialogs.

**Step 3 — Un-migrate, carefully (RC-3).**
Delete `migrate_projects_if_needed`, `_case_from_legacy_request`,
`_topology_from_legacy`, `_legacy_signature`, and the `.case_migration_done`
marker logic. For the data: move auto-migrated, UNTOUCHED cases (those with
`migration_source` set AND `last_used` null AND no `sensor_roles` in their
diagram.json) into `library/_archive_migrated_cases/`. **Keep IDD5SL12WE**
(and any other case with real usage) exactly where it is — the user's 147
mappings live in its diagram.json. The old `projects/` folder and the
`projects_backup_*` copy: zip both into `library/_archive_projects_<date>.zip`
per WORKFLOW_REDESIGN_PLAN §7, then remove the live folders.

**Step 4 — Rebuild New Case as the progressive picker (RC-4).**
Implement §5 of WORKFLOW_REDESIGN_PLAN as written: steps appear one at a
time; changing Step 1 resets dependent steps; derived facts never shown;
`off_time` added to the defrost values; labels driven by the family rulebook.
Fix the rulebook pitch 32→30 in BOTH `case_library.FAMILY_RULEBOOK` and the
existing `library/case_families.json` (the ensure-function won't overwrite
it; the fix must update the file or version the rulebook).

**Step 5 — Fix the file-open fallback (RC-5).**
Recognize case/diagram files by CONTENT, not filename: a dict with `id` +
`topology` is a case; a dict with `components` (+ optional `_topology`) is a
diagram; otherwise treat as session. Whatever path is taken, show a
status-bar message naming it ("Opened as case / diagram / session"). Remove
the leftover `case_handler` debug print if any remain.

**Step 6 — Tame the launcher sync (RC-6).**
`ensure_launch_cmds` must only manage the launcher in ITS OWN folder. Remove
the hardcoded write into `HVAC_Dev/V3/Labview-new_rev` (restore that file
from that copy if the user wants it back). If keeping any cross-copy sync,
it must be a visible, user-triggered action, not a silent startup side
effect.

**Step 7 — Store only the new topology schema (RC-8).**
`case.json` keeps ONLY the §5 schema; `ensure_old_topology` becomes a pure
read-time adapter (never persisted, no `legacy.update(topo)` stale-key
override — derived values always win over leftovers). One-time cleanup: on
first load of a case whose topology contains old keys, rewrite it to the
clean schema.

**Step 8 — Init-order guard (RC-7).**
Connect `mode_combo.currentTextChanged` after the scene exists (or no-op
`on_mode_changed` until `self.scene` is set).

---

## Part 3 — Verification (run before and after)

All reproductions are headless (offscreen Qt) unless noted:

1. **Corruption repro (must FAIL before, PASS after):** open case
   IDD5SL12WE → record `diagram.json` mtime/hash → open legacy Test Request
   dialog (before Step 2 lands) or otherwise swap `diagram_model` and emit
   `diagram_model_changed` → BEFORE: `diagram.json` is rewritten (bug);
   AFTER: file untouched, autosave refused, log line explains why.
2. **Open Case still works:** offscreen sim — open IDD5SL12WE → 56
   components, ≥600 scene items, zoom≈0.32, `view.contains(itemsRect)` true.
3. **Menu audit:** menu bar contains `Cases` only — no `Test Requests` menu;
   `python -c "import test_request_dialog"` fails (file removed) while
   `part_dialogs.NewPartDialog` imports.
4. **Migration removal:** fresh start with an empty `library/cases/` creates
   no cases; IDD5SL12WE survives in place with its sensor_roles intact;
   archived cases exist under `library/_archive_migrated_cases/`.
5. **Picker behavior (manual):** New Case shows ONLY family question first;
   Reach-in never shows open/doored; Insight never shows temp class; defrost
   list has five values; family JSON says 30 for reach_in.
6. **File-open:** opening a renamed copy of a case file loads it as a case
   (status bar says so); opening an old session still loads as session.
7. **Launcher:** after Step 6, the V3 folder's `Launch Lab Viewer.cmd` is no
   longer rewritten on startup (set it to dummy content, launch this app,
   confirm unchanged).

## Addendum (2026-07-02, post-fix) — RC-9: "Nothing changed" = wrong app copy

After the Part-2 fixes landed (verified: legacy menu gone, `test_request_dialog.py`
deleted, offscreen startup shows menu bar = `['&Cases']` only), the user
reported the app looked identical. Verified root cause: the SECOND app copy at
`HVAC_Dev/V3/Labview-new_rev/` still holds a June-22 `app.py` (old Test
Requests menu, none of the fixes) and has its own `Launch Lab Viewer.vbs` /
`.pyw` that launch ITS OWN folder's app. Any shortcut pointing there — or an
app window opened before the fixes — shows the old behavior. Only that
folder's `.cmd` was redirected to the new copy; `.vbs`/`.pyw` were not.

Fixes to fold into Step 6 (launcher taming):
1. **Version/copy stamp in the title bar** — `HVAC System Analyzer — build
   <date> — <folder name>`, so old-copy launches are instantly recognizable.
   This is the cheap, permanent cure for every future "nothing changed".
2. **Quarantine the V3 copy's launchers** (rename the V3 `.vbs`/`.pyw`/`.cmd`
   to `_OLD_COPY_do_not_use.*` or have them show a message pointing at the
   active copy) — with the user's confirmation, since it's their folder.
3. **Single-instance guard or stale-window warning** is optional; the title
   stamp already lets the user see which build a window is.

## Addendum (2026-07-03) — RC-10: blank diagram after CSV load, and blind logs

User reported a nearly-empty diagram (only Compressor, Condenser, and the
three canonical sensor boxes visible). **ROOT CAUSE CONFIRMED BY
REPRODUCTION (2026-07-03 11:26):**

Under a real double-click launch (`.cmd` → `start pythonw.exe`), the process
has NO console, so `sys.__stdout__` and `sys.__stderr__` are `None`. In
`init_logging` (`logging_setup.py:78`) the console handler is constructed as
`StreamHandler(sys.__stdout__)` → its stream is effectively None. After the
stdout/stderr redirect is installed (`logging_setup.py:100–101`), the failure
chain on EVERY `print()` in the app is:

`print` → `_StreamToLogger` → `logger.log` → console handler `emit` raises
(`None.write`) → `handleError` writes the traceback to `sys.stderr` — which
is now `_StreamToLogger` again → logs again → **infinite recursion →
RecursionError propagates out of the original `print()` call.**

Reproduced exactly with std streams set to None: `print()` raises
`RecursionError`, and the log file contains ONLY the init line (the init
message is logged at line 96, BEFORE the redirect at line 100 — the only
record that ever succeeds). This single bug produces ALL observed symptoms:

- **Blank diagram**: `build_scene_from_model` prints per component
  (`[REBUILD] Ports for …`); the first print inside the component loop
  raises, `update_ui`'s catch swallows it, and the scene is left with the
  items built before that print — sensor boxes (built first), Compressor,
  Condenser. Exactly the user's screenshots.
- **One-line logs** (23:19, 23:54, 11:14, 11:24 sessions): the console
  handler raises before the record reaches the file handler, so nothing
  after init is ever written.
- **Unreproducible in testing**: any console-attached launch (developer
  terminal, bash, `python` instead of double-click) gives pythonw valid
  handles → no None stream → everything works. The bug ONLY exists on the
  user's actual double-click path.

Fixes (all required):
1. **`init_logging` must not install a console handler when
   `sys.__stdout__` is None** (no console to write to). File handler only.
2. **Break the recursion structurally:** add the file handler FIRST; set
   `logging.raiseExceptions = False`; give `_StreamToLogger` a re-entrancy
   guard so a failure inside logging can never route back into logging.
3. **`update_ui` / `build_scene_from_model` must log the FULL traceback on
   failure and keep building the remaining components**, with a visible
   on-canvas banner ("N component(s) failed to render — see log"). Never
   again a silent half-scene.
4. Acceptance: launch by DOUBLE-CLICKING the `.cmd` (not from a terminal!),
   open IDD5SL12WE, load `DataDOE081.csv` — full diagram renders, and the
   session log contains the normal stream of `[REBUILD]/[SIGNAL]` lines.
   Every future acceptance test of launcher/logging behavior must use a
   real double-click, since console-attached launches mask this class of
   bug.

## Part 4 — Note to the implementer

The previous round implemented pieces the plans explicitly excluded
(migration, legacy menu retention, flat picker) and skipped pieces the plans
required (progressive disclosure, 30-inch pitch, schema purity). Before
writing code, read `WORKFLOW_REDESIGN_PLAN.md` §5/§7/§9 and
`PLAN_REVIEW_RESOLUTIONS.md` — where this document and those disagree, those
documents win, except where this document records a NEWER owner decision
(the preservation of case IDD5SL12WE despite "no migration").
