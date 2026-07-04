# Plan Review — Findings & Resolutions

Companion to `WORKFLOW_REDESIGN_PLAN.md`. An external review traced the plan
against the code (2026-07-02). Every finding below was re-verified, dispositioned
with the owner, and the master plan amended. Implementers: read this once for
context; the master plan remains the single source of truth.

---

## Finding 1 — Migration by case_model is risky (conflicting old topologies)

**Claim:** Existing ID6SU12WE requests carry contradictory topologies
(2-module Modular vs Reach-in vs 3-module Open); "most recent wins" would
silently bury the others.

**Verified:** Yes — old requests store all four count fields plus a mode, and
the same case model appears with different modes.

**Resolution (OWNER DECISION): there is NO migration.** The owner considers the
old library data messed up and will recreate every case from scratch in the new
system. Consequences:
- Master plan §7 replaced: archive `library/projects/` as a zip backup, then the
  new version starts with an empty `library/cases/`.
- Parts **catalogs are kept** (`library/catalogs/`, `elp_codes.json`) — they are
  clean, and re-entering datasheets would be pointless friction.
- All migration tooling is descoped. Reviewer's question about suffixed
  duplicate cases: moot.

## Finding 2 — New topology schema breaks existing readers of `_topology`

**Claim:** `data_manager.py` still reads `mode`, `modules`, `num_doors`,
`num_cassettes`, `circuits_per_coil` (e.g., ~line 1900 and ~2183).

**Verified:** Yes — `data_manager.py:1900` reads `_topology.mode` for shelf
math; `:2183–2191` builds a sensor-default key from `circuits_per_coil` +
per-mode counts.

**Resolution:** No compatibility shim. Since there is no migration and no old
data to honor, these readers are **updated to the new schema in the same phase
that introduces it** (master plan §6.10, Phase 3). The sensor-point-defaults
key derivation must be redefined on the new schema
(`family / size_count / system / cassette_count / circuits`).

## Finding 3 — Defrost/airflow changes are real generator work

**Claim:** Hot-gas hardware is welded to the `cassette_lt` branch
(`diagram_from_request.py:721`), cassette MT gets the simple loop (`:637`),
and reversed airflow triggers off `is_cassette` (`:898`) — not off explicit
flags.

**Verified:** Yes.

**Resolution:** Already planned (master plan §6.4, §6.5) — restated explicitly
as *restructuring*, not renaming: the defrost valve set becomes a composable
add-on any loop (shared or cassette) can receive, and air-band ordering keys
off `cassette_airflow == reverse`. Scoped into Phase 3/4.

## Finding 4 — Session linkage needs more than adding `case_id`

**Claim:** `save_session_to_dict` (~`data_manager.py:1483`) persists
`ratedInputs` and `diagramModel` but not `refrigerant`; undo uses the same
serializer, so both paths must carry the new fields.

**Verified:** Yes.

**Resolution:** Master plan §6.9 added: session save/load (and therefore the
undo stack, which reuses `save_session_to_dict`) must persist `case_id` **and**
`refrigerant`. Acceptance check: open case → change refrigerant → save session
→ reload → both survive; Ctrl+Z never drops the case link.

## Finding 5 — Plan removes projects but requests/export are project-bound

**Claim:** The dialog and printable export depend on project name
(`test_request_dialog.py:127`, `test_request_library.py:408`).

**Resolution:** The **project concept is dropped entirely** (owner starts
fresh; nothing to carry over). The printable test export prints the **case
model + case summary block** where the project name used to be. `add_project`,
`projects()`, and the project combo go on the deletion list (master plan §9).

## Finding 6 — Deletion list confirmation + broken TEST button

**Claim:** `new_diagram_wizard.py` and the template path are uncalled; also
`app.py` imports `build_simple_loop_diagram`, which **does not exist** — the
sensor-panel TEST button is already broken.

**Verified:** Yes — `def build_simple_loop_diagram` exists nowhere; clicking
that button today raises ImportError. Deleting it is a bug fix, not a loss.

**Resolution:** Deletion list stands; note added to master plan §9.

## Finding 7 — "Visual upgrade" partly exists; shelf width is 30", not 32"

**Claim:** Doors/mullions/secondary air bands already exist in
`build_bare_minimum_diagram` — Phase 4 is *adapt to the family rulebook*, not
build-from-scratch. Also code uses 30" non-modular shelf width
(`diagram_from_request.py:1185`, `data_manager.py:1902–1904`) vs the plan's 32".

**Verified:** Yes on both counts.

**Resolution (OWNER DECISION): 30 inches is correct.** The plan's earlier 32"
(from conversation) was wrong; the family rulebook now says Reach-in pitch =
30" (doors, mullions, shelf columns). The two hardcoded `48 if … else 30`
sites are replaced by a single rulebook lookup (§6.6). Phase 4 rephrased as
adaptation of existing drawing code.

---

## Reviewer's open questions — answers of record

| # | Question | Answer |
|---|---|---|
| 1 | Conflicting topologies at migration: suffix duplicates or flag for review? | **Moot — no migration.** Owner recreates all cases fresh; old library is archived only. |
| 2 | Can `cassette_count` differ from `size_count` (e.g., 3-door Reach-in, 2 cassettes)? | **Yes (owner).** Picker keeps asking cassette count. Layout rule (§6.8): cassettes divide the case width **evenly**, independent of door/mullion positions; refrigeration loops, fans, and loop labels belong to cassettes (LH/CTR/RH or U1…Un); shelves/doors/mullions stay on the family's own pitch grid. No alignment between the two grids is attempted. |
| 3 | `None / Off-time`: one enum value or two? | **Two values** (planner decision): `defrost_type ∈ {none, off_time, electric, hot_gas, cool_gas}`. `none` and `off_time` draw identical hardware (nothing extra) but differ in printable-export wording and settings expectations (off-time has a schedule; none does not). |
| 4 | Do old project names matter? | **Moot — no migration.** The archived zip is the only record; the new system has no project concept. |

## Amendments applied to WORKFLOW_REDESIGN_PLAN.md

1. §7 rewritten: **no migration — fresh start**; archive old `library/projects/`,
   keep catalogs.
2. All Reach-in pitch references corrected **32" → 30"**, including the §5b
   rulebook entry; shelf-width constants consolidated to the rulebook (§6.6).
3. §5 Step 5a: cassette count explicitly independent of size count; §6.8 layout
   rule added.
4. §5 Step 7: defrost enum expanded to five stored values.
5. §6.9 (session persists `case_id` + `refrigerant`, undo included) and
   §6.10 (update `data_manager` `_topology` readers to the new schema) added.
6. §9: project-concept removals added; broken TEST-button note added.
7. §11 phases updated (migration removed; schema-reader updates placed in
   Phase 3).
