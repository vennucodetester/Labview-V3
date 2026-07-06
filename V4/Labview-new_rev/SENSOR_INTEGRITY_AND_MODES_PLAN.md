# Sensor Integrity, Diagram Modes & Graph Zoom — Fix Plan

Status: PLANNING ONLY (2026-07-03, afternoon). Deep-dive completed; every
root cause below was verified by direct resolution tests against case
IDD5SL12WE + its CSVs, or by reading the cited code. Companion to
GRAPH_TAB_REDESIGN_PLAN.md, MAPPING_AND_HIGHLIGHT_FIX_PLAN.md,
OFF_DIAGRAM_INSTRUMENTS_PLAN.md.

---

## 1. Graph: plot-area scroll zooms BOTH axes (owner decision)

Axis-strip zoom is approved as-is (Y strip → Y only, X strip → X only).
Change: **scrolling inside the plot area zooms X and Y TOGETHER**, anchored
at the cursor (`GraphViewBox.wheelEvent`, graph_widget.py:70 — currently
routes to a single axis). Modifiers: Shift+scroll = Y only, Ctrl+scroll =
X only (both optional conveniences; the axis strips already cover
single-axis). GRAPH_TAB_REDESIGN_PLAN.md Part 2 gesture table is amended
by this section.

## 2. Diagram modes: kill the Drawing/Mapping/Analysis combo

The three-mode combo is legacy structure. Nothing about mapping requires a
"mode" (clicking a dot can always map/select), and analysis is an overlay,
not a place. New model, within the toolbar budget:

| Control | Behavior |
|---|---|
| *(default state — no name, no combo)* | View & Map: dots clickable (select / locate / map from panel selection), components NOT draggable, nothing editable by accident. This is where users live. |
| **✏ Edit layout** (toggle) | Replaces Drawing mode. When ON: components draggable, and the authoring controls appear (Components ▾, Snap to Grid, Straighten Pipes, Align Ports). When OFF they are hidden. Edits auto-save to the case (with the RC-2 ownership guard). |
| **Analysis** (checkbox toggle) | Replaces Analysis mode: overlays computed values/states on the diagram whenever calculation results exist. Independent of everything else — you can have it on while mapping. |
| **Zoom to Fit** | Width-fit per OFF_DIAGRAM_INSTRUMENTS_PLAN §2c. |

Toolbar default view: `[✏ Edit layout] [Analysis ☐] [Zoom to Fit] [Mapping report…]`.
The `Mode:` combo, and the concept of modes, are deleted. Ghost-reveal for
assigning Ungrouped sensors (MAPPING plan §2.1) triggers on selecting an
Ungrouped sensor — no mode required.

## 3. "Not on diagram (7)" — why it happened, and the invariants that stop it

### Verified root causes (resolution traced column by column)

**3a. Polluted alias entries (4 of 7).**
- `Air off ctr evap 6 in LE/RE` resolve to `T_air.fan_in.ctr.*` — an
  air-OFF column pointing at a fan-IN canonical (wrong family; the LH/RH
  equivalents correctly resolve to `fan_off`).
- `Return Air 2 in RE` resolves to `T_air.disc.s11` (a DISCHARGE slot);
  `Return Air 12in RE` resolves to `T_air.ret.s4` (wrong return slot).
These bad targets' slots are already occupied by their rightful columns, so
auto-map returns `known_but_filled` and the columns fall into "Not on
diagram" with **no conflict warning**. The wrong entries almost certainly
come from the learned-alias store (one historical mis-mapping is remembered
forever, `data_manager._save_learned_alias`).

Fixes:
1. One-time cleanup: remove the four bad learned aliases.
2. `known_but_filled` becomes a surfaced CONFLICT: Mapping report gets a
   "Conflicts" section showing column → canonical → what occupies it, with
   one-click "re-learn this column" (forgets the alias, re-resolves by
   pattern).
3. Learning an alias that CONTRADICTS the pattern-derived canonical (or
   steals an occupied canonical) requires an explicit confirm at map time —
   silent poisoning of the alias DB becomes impossible.

**3b. Genuinely unknown summary columns (3 of 7).** `AVG Product temp`,
`BTU`, `Total Flow` have no canonical at all. They are lab summary values —
they belong on the Instrument Panel. Fix: add canonical instrument slots
(System & Flags card: e.g. `q_btu`, `m_flow.total`, `T_prod.avg`) with
seeded aliases so they auto-map for every future CSV. Rule: recurring lab
summary columns get instrument slots; one-off oddities stay in Ungrouped
for the teach flow.

### Invariants (the "never again, anywhere" part)

A `mapping_integrity_check()` runs after every CSV load / case open; any
violation appears in the Mapping report and the log:
- **A. Mapped ⇒ visible.** Every `sensor_roles` entry must resolve to a
  renderable, currently-visible dot (catches the TXV-bulb class, §5).
- **B. One bucket per column.** Every CSV column is exactly one of
  mapped / instrument / ungrouped, and panel + diagram agree (single
  `sensor_home()` — OFF_DIAGRAM plan Part 1).
- **C. Unique labels.** No two panel rows may render the same human label
  (catches the product-sim class, §4); collisions are auto-suffixed AND
  reported.
- **D. Aliases can't contradict patterns silently** (3a.3 above).

## 4. Product Sim duplicate names — root cause & fix

**Verified:** `diagram_from_request.py:1195` builds every product column's
human name via `shelf_column_name(0, 1, [col_id])` — `col_idx=0` always
hits the "endpoint" branch and returns **'LE' for every column**, so
`PS Top shelf LE / 48 LE / 48 RE / RE` all display as "… - LE - Front/Rear".
(The canonical ids are correct and distinct — `T_prod.top.LE.f`,
`T_prod.top.LE48.f`, `T_prod.top.RE48.r`, … — only the display name
collapses.)

Fixes:
1. Humanize from the column id itself: `_humanize_distance(col_id)`
   (`sensor_canonical.py:96`) — labels become "LE", "48in LE", "48in RE",
   "RE". Distances always appear in the label; names are unique by
   construction.
2. Same distance-qualified names must appear in the panel rows, tooltips,
   and the diagram dot labels — one naming function, used everywhere.
3. Invariant C (§3) guards the whole class.

## 5. TXV bulb — mapped but invisible; and its correct physical home

**Verified:** the case diagram has `sensor_roles` entries
`TXV.left_txv.bulb / center / right → '<X> TXV Bulb'` (hence green rows in
the panel), but the generated diagram contains **no SensorBulb components
and the TXV item renders no 'bulb' port dot** — the mapping points at
nothing visible. Classic mapped-but-invisible.

Physical truth (drives placement): a TXV sensing bulb is strapped to the
**suction line at the evaporator outlet** (downstream of the coil/header),
where it senses superheat for the valve. It does NOT sit on the TXV body.

Fixes:
1. The generator adds one bulb dot per expansion circuit, positioned ON the
   suction pipe just downstream of the CombinerManifold (header) outlet of
   its module, labeled "{Left/Center/Right} TXV Bulb", canonical
   `T_txv.{tag}.bulb` (unchanged — existing mappings carry over).
   **Conditional on the case's expansion device (owner addition,
   WORKFLOW_REDESIGN_PLAN §6.10b):** bulb dots exist ONLY when the case
   uses a TXV. Cap-tube cases draw a CapTube component and enumerate NO
   bulb role at all; EEV cases draw an EEV component with an electronic
   suction-temp probe dot (`T_eev.{tag}.suction`) at the same physical
   location instead of a bulb, plus an optional "EEV Position %" instrument
   slot. Switching a case's expansion device regenerates these slots, and
   any orphaned mappings (e.g., bulb columns after a switch to cap tube)
   appear in the Mapping report as conflicts — never silently dropped.
2. The phantom `bulb` port on the TXV component is removed from role-key
   enumeration (or transparently re-anchored to the new dot) so role keys
   can never target an unrendered port again — and the enumeration must
   respect the expansion-device rule (a cap-tube case enumerating a bulb
   role is an Invariant-A violation).
3. Audit for the rest of the class: run Invariant A against all five cases'
   diagrams; every mapped-but-invisible role found gets either a rendered
   dot or a migration to the right anchor. (Known suspects to check: any
   canonical table entries for ports that components don't draw — e.g.
   compressor RPM port, condenser water ports on air-cooled variants.)

## 6. Order of work

1. §3 invariants + Mapping-report Conflicts section (they make every other
   fix verifiable), plus the one-time alias cleanup.
2. §5 bulb dots + Invariant-A audit of all cases.
3. §4 product-sim naming.
4. §2 modes removal (coordinate with MAPPING plan Part 1 toolbar work).
5. §1 graph both-axes plot zoom (one-line routing change + modifier keys).

## 7. Acceptance (IDD5SL12WE + DataDOE80f.csv)

1. Plot-area scroll zooms both axes about the cursor; Y strip still zooms Y
   only; X strip X only.
2. No `Mode:` combo. Default state maps/selects but cannot move components;
   ✏ Edit layout reveals authoring tools and enables dragging; Analysis is
   a toggle overlay.
3. "Not on diagram" contains ZERO of the seven current columns: the four
   mis-aliased ones map to their correct air slots after cleanup, and the
   three summary columns land on the System & Flags instrument card. The
   Mapping report shows conflicts (none after cleanup) and integrity-check
   results.
4. Product-sim panel rows and dot labels all read with distances ("Top
   Shelf - 48in LE - Front"); zero duplicate labels app-wide (Invariant C).
5. Three TXV bulb dots visible on the suction lines at the evaporator
   outlets, green, carrying the existing mappings; Invariant A reports
   zero mapped-but-invisible sensors across all five cases.
6. Expansion-device matrix: generate a test case per device kind —
   TXV case shows bulb dots; cap-tube case shows CapTube components, zero
   bulb dots, and no bulb entry anywhere in panel/report; EEV case shows
   EEV components with suction-probe dots and an "EEV Position %" slot on
   the System & Flags card. Switching an existing TXV case to cap tube
   moves its previously-mapped bulb columns into the Mapping report's
   Conflicts section.
