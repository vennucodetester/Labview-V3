# Test Request System — Master Plan
> Status: **APPROVED DIRECTION — NOT YET BUILT. Waiting for user go-ahead per phase.**
> Created: 2026-06-11 from extended design conversation with the user.
> This document is the durable record — if the conversation is lost, build from here.

---

## 1. The Vision (in plain words)

The app stops being a data viewer and becomes **the master record of every test**.

The user's R&D reality (critical context — re-read before designing anything):
- This is **prototype development**, not monitoring of fixed machines. Hardware changes
  almost daily: TXV swaps, distributors, compressors, tubing, GPM, fan speed/diameter,
  baffles, door heat, defrost settings, condenser angle.
- The daily question is **"did my change make it better or worse?"** — never
  "is the machine degrading?" Any feature that assumes a stable system over time
  (charge baselines, drift trending, solver UA calibration) is DEAD for this user.
- A project (from DFMEA/DVP&R needs list) spawns ~100 test requests: performance
  (incl. NSF, DOE), UL, transit, load, vibration, sound — each with an ELP code.
- CSVs roll over only when full → **one CSV can contain a hardware change mid-file**.
- The lab labels sensors inconsistently today; long-term the app exports the sensor
  schedule and the lab follows it (app = source of truth). Short-term, fuzzy label
  matching is a *temporary bridge*.
- Electrical power IS in the CSV (1–2 min cadence) → DOE energy and measured-power
  COP are computable.
- Trial phase: one engineer per app instance. Design all data files for later
  **merging** of 4–5 engineers' libraries into one source of truth (stable IDs,
  provenance fields, no positional/array-index references).

## 2. The hierarchy

```
Project (e.g. "2027 reach-in platform")
 └─ Test Request (one per test type: ELP0071 transit, performance/NSF/DOE, UL …)
     └─ Revision (Rev A, B, C … auto-bumped on any hardware/setting change)
         └─ Data (CSV files / time segments collected while that rev was current)
```
Timestamps tie revisions to data. "Which compressor was in during Tuesday's data?"
must always have one indisputable answer.

## 3. Data management — SEPARATE small databases, not one lump
**(User explicitly warned: lumping everything in one place will be confusing.
Data management is critical. Honor this.)**

Proposed layout — a `library/` folder of small, single-purpose JSON files:

```
library/
  catalogs/                 ← parts: grow automatically as user types new entries
    txv.json                  (part no, type, nominal tonnage/Cv, connection, notes)
    compressors.json          (model, displacement, rated speed/Hz, rated m_dot, …)
    coils.json                (model, circuits, FPI, rows, face area, …)
    distributors.json         (model, outlets, nozzle size, …)
    fans.json                 (model, dia, CFM, speed, …)
    condensers.json           (model, water/air, nominal GPM/CFM, …)
  criteria/                 ← pass/fail targets, one file per standard/case family
    doe_reach_in.json         (DOE energy limits by case class)
    nsf_temps.json            (NSF product temp criteria)
    case_targets/<case>.json  (per case model: SH range, SC range, capacity, product temps)
  elp_codes.json            ← test-type registry (ELP0071=transit, … objective templates)
  projects/
    <project_id>/
      project.json            (name, needs list refs)
      requests/<request_id>.json   (the test request + its revisions array)
```

Rules:
- Every record gets a stable unique `id`, `created_by`, `created_at` → merge-ready.
- Catalogs are append-mostly; editing a part never silently changes history
  (requests reference part `id` + snapshot of the values at time of use).
- Nothing in `projects/` duplicates catalog data — references + frozen snapshots only.

## 4. The phases (recommended order: 1 → 2 → 4 → 5 → 3 → 6)

**Phase 1 — Test Request form. ✅ BUILT 2026-06-11.** In-app form replaces the
Word doc: project, case model, test type (ELP dropdown), objective, parts (from
catalogs), settings (GPM, CFM, defrost), targets (editable min/max table).
Saves to library; exports printable HTML. Catalogs grow as you type.
Files: `test_request_library.py` (data layer, all rules from §3 enforced incl.
snapshot-freezing), `test_request_dialog.py` (form + new-part mini-dialog),
menu bar "Test Requests" in `app.py`. Validated: save/reload round-trip,
catalog growth, snapshot freeze after catalog edit, HTML export, dialog load.

**Phase 1 rework after user review (2026-06-11/12) — design rules now enforced:**
- A part field exists ONLY if a calculation/diagram/scorecard consumes it
  (`PART_FIELD_DEFS` documents the schema; compressor carries the five
  rated-input numbers: displacement in³, rated RPM, rated lb/hr, rated evap °F,
  rated return gas °F — typed once per supplier PN from the datasheet).
- Identifiers: SUPPLIER part number is primary (`model`), company PN optional
  (`company_pn`); dropdowns show 'SUPPLIER · company'. User units: in³ and RPM;
  conversions to the engine's ft³/Hz/cm³ live in `compressor_to_rated_inputs()`
  and `IN3_TO_CM3`.
- **"Save + Apply to session"** button (the rent-payer): pushes compressor
  datasheet → `data_manager.rated_inputs` (no more re-typing the Rated Inputs
  dialog), water GPM, refrigerant, and compressor displacement/speed onto the
  diagram Compressor component (activates the m_dot_disp cross-check).
  Validated end-to-end: eta_vol computes 'calculated' (not default) from a
  catalog compressor.
- UI: scroll-area layout, pinned buttons, default target rows pre-seeded.

**Phase 2 — Target scorecard.** Picking the case auto-fills the Range Editor;
every calculation run ends with "3 of 5 targets met" + per-target gaps.

**Phase 4 — Mark change + revisions.** One click at a timestamp (or click the
graph): tick what changed, one-line note → auto Rev bump with time. The change
moment becomes a WALL in the data: averages/trends/diagnostics never blend across
it, even inside one CSV. Change history writes itself.

**Phase 5 — Label-matching bridge (temporary).** On CSV load: fuzzy auto-match
lab labels to app labels; every manual correction is REMEMBERED (synonym
dictionary) so it is never asked twice. Only genuine leftovers shown. Designed
to become unnecessary once the lab follows the app's sensor schedule.

**Phase 3 — Auto-diagram. ✅ CORE BUILT 2026-06-12.**
"Generate process diagram" button on the Test Request form →
`diagram_from_request.build_diagram_for_request()`.  Strategy: the templates
ARE the user's hand-built diagrams (the old procedural builders "don't
understand refrigeration positioning" — user verdict).  `templates/` holds
8 ingested references (ID5SL12 3-mod, ID5SL4/SL6/RMN2MA/RMN3WE 1-mod,
RLN3MA/RMN5MA dual-compressor, ID6SU12WE 3-mod) + `index.json` metadata.
Nearest-match picks by system type → module count → circuits; exact module
match = template verbatim (zero surgery); only a missing module count
triggers reduction of the 3-module reference.  Patches applied: evaporator
circuits property, condenser cooling type; mappings stripped.
Validated: 3/2/1-module + cassette all generate with 0 dangling pipes;
3-module output is pixel-identical layout to the user's ID5SL12.
KNOWN LIMIT (Phase 3.1): circuit-count changes only patch the evaporator
property — they do not add/remove per-circuit distributor stub pipes in
templates that wire circuits individually.  Sensor schedule export still TODO.

**Phase 3 (original notes) — Auto-diagram + sensor schedule.** The form knows the topology
(modular/cassette/reach-in/open/doored, modules, circuits, condenser type) →
one click generates the full process diagram (components, pipes, auto-named
sensors). Naming: adopt published standard names where they exist (ASHRAE 72 /
DOE test points), house standard for the rest, documented in-app. Export the
sensor schedule (Excel/PDF) for the lab — labels out = labels back.
NOTE: biggest build; existing assets: new_diagram_wizard.py, diagram_templates.py,
the user's existing session diagrams (collect ALL of them as fixtures first).

**Phase 6 — A/B compare + DOE automation.** Before/after (two revisions or
segments): one delta table — SH per coil, SC, capacity, COP, circuit spread —
arrows colored toward/away from target. Power integration over 24 h
(defrost-aware) computes DOE energy (manual entry first, automated when trusted);
measured power upgrades COP/η from refrigerant-side estimate to electrical truth.

## 5. The test report (output of the whole system)

Generated per request/revision, contains:
1. All entered request values (project, ELP, objective, parts, settings, targets)
2. The process diagram (rendered image)
3. The sensor schedule: every sensor the user placed — label, location, type
4. Results: scorecard vs targets, key calculated values, findings summary
5. Revision history with timestamps

## 5b. ✅ HANDOFF BUG — ROOT-CAUSED & FIXED (2026-06-11, follow-up session)

The user reported diagram generation **"still pulling old json files"**.
Investigation results:

**Templates were never the problem.** All 7 `templates/tmpl_*.json` are
byte-faithful to the hand-built diagrams in `2.0/Config` (component types +
positions verified identical, ID5SL12 = 30 comps / 52 pipes). No duplicate
templates/ folder or second `diagram_from_request.py` exists on disk. The
only saved request (TR-2026-001, shared/3-mod/6-circ) exact-matches
`tmpl_ID5SL12.json`.

**Root cause found — crash bug in the 🆕 New slot:**
`diagram_widget.on_new_diagram_clicked()` ended with
`print(f"... config_key={config_key!r}")` — a leftover from the deleted
wizard path; `config_key` is undefined → `NameError`. In PyQt6 an unhandled
exception inside a signal-invoked slot **aborts the whole app** (qFatal).
So: model swapped → app crashed an instant later → user relaunched → session
restore showed the OLD diagram. This is why offscreen validation (direct
function call, no Qt slot) passed while the live app "pulled old json".
Secondary trap: a stale pre-ingestion process would run old code pointing at
the deleted ID6SU12WE template.

**Fixes applied (verified end-to-end offscreen):**
- Removed the `config_key` NameError; 🆕 New now shows an info dialog naming
  the template used.
- `build_diagram_for_request()` tags the returned model with transient
  `'_generated_from'` (template file + source); both callers (diagram_widget
  🆕 New, test_request_dialog Generate button) pop it and display it in their
  success dialogs — the user can now SEE which file loaded, no console needed.
- Procedural fallback path also tags itself and prints a `[DIAGRAM GEN]` line.
- Verified: TR-2026-001 → tmpl_ID5SL12 verbatim (layout identical to
  hand-built ID5SL12, 0 dangling pipes, mappings cleared); 2-module surgery →
  "tmpl_ID5SL12.json (reduced to 2 module(s))", 22 comps, 0 dangling;
  cassette → tmpl_RLN3MA exact.

**Remaining live check with the user:** restart the app (kill any stale
process), click 🆕 New, confirm the dialog says `tmpl_ID5SL12.json` and the
layout is the hand-built one.

## 5c. FINAL STATE OF THE 🆕 NEW BUTTON (2026-06-12, after user went back and forth)

Sequence: user asked to revert 🆕 New to the original wizard ("AMAZING") →
reverted → user immediately reversed themselves ("NEVERMIND… Just go back to
the previous") → **the AUTOMATIC test-request-driven generation is restored
and is the current behavior of 🆕 New.**  The thing the user called "very
good / AMAZING" was the AUTO-GENERATED diagram (from their test request +
their 2.0/Config-derived templates), not the old wizard output.

Current state:
- 🆕 New = automatic: most recent test request → nearest hand-built template
  → confirm dialog → generate; success dialog names the template file used.
- The old wizard (`new_diagram_wizard.py` + `diagram_template_loader.py`) is
  again unreachable from the UI.  `diagram_template_map.json` was repointed
  at the good 2.0/Config files (12ft→ID5SL12, 6ft→ID5SL6, 4ft→ID5SL4,
  cassette_2units→RLN3MA) — harmless now, useful if the wizard ever returns.
- A generated diagram is fully reproducible: press 🆕 New again (same request
  → same template → same output).  "It's all gone" is never true for
  generated diagrams — regenerate in one click.  Hand-EDITS on top of a
  generated diagram are only safe once saved as a session (Save button).
- Lesson recorded: when the user reports the wrong layout appearing, check
  in this order: (1) which request is most recent, (2) the success dialog's
  template name, (3) stale app process.

## 6. Open items / risks (do not lose these)

- **Collect ALL existing process diagrams** from the user as fixtures before
  building Phase 3 (user offered to provide; only ID6SU12WE-15/16/20/21/22 on disk).
- **"Make sure everything is calculated correctly"** — user flagged this is hard.
  Need a GOLDEN REFERENCE: at least one test where the user knows the right
  answers (their trusted Excel/manual calc) to validate engine output end-to-end.
- ASHRAE/ASTM naming standard: verify what the standard actually specifies before
  claiming compliance; define house standard for the gaps.
- Merge tool for multi-engineer libraries: design now (IDs/provenance), build later.
- Killed ideas (do not resurrect without re-reading §1): charge gauge,
  campaign drift trending, solver UA calibration, healthy-run baselines.
- Surviving diagnostics idea: **root-cause grouping ("one villain, not ten
  alarms")** — reword recommendations in design language (e.g. "TXV likely
  undersized") not service language ("replace the valve").

## 7. Communication rule (user preference, permanent)

Pitch every feature in plain language BEFORE building: what the user will see,
click, and decide. Get explicit approval. No building on assumption.
