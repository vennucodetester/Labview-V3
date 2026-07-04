# Graph Tab — Phantom Series Fix & Toolbar Redesign

Status: PLANNING ONLY (2026-07-03). Companion to WORKFLOW_REDESIGN_PLAN.md /
MAPPING_AND_HIGHLIGHT_FIX_PLAN.md. Two problems:

1. The graph plots sensors the user never selected (two greyed "Not on
   diagram" sensors), with nothing checked in the panel.
2. The graph toolbar is a flat row of nine buttons (Reset Zoom, Box Zoom,
   Lock X, Lock Y, Fit Y, Range, Apply Range, Auto-Detect Defrost, Capture
   Snapshot) — organically grown, no organizing idea. The owner wants
   direct-manipulation zoom (scroll on the axis itself) and a clean,
   SolidWorks-grade organization.

---

## Part 1 — Phantom graphs: root cause (verified) and fix

### Root cause

The plotted set is `data_manager.graph_sensors` (`graph_widget.py:389`),
which is **restored from persisted session state** — `graphSensors` in the
session JSON (`data_manager.py:393`, `:1642`) and carried through every
undo/auto-save snapshot (`:1568`, `:1620`). On top of that,
`_resolve_graph_sensors` (`graph_widget.py:272–330`) resolves stale entries
to CSV columns via aggressive normalization (strip/lowercase/alnum-only), so
even outdated labels persisted long ago still land on today's columns —
including columns that are unmapped/"Not on diagram" in the current view.

Net effect: plotting state survives across sessions invisibly. The panel's
Graph checkboxes are rebuilt from the CSV-driven view and show nothing
checked, while the graph obeys a hidden set restored from disk. The two
phantom series ("Return Air 2 in RE", "Return Air 12 in RE") are exactly the
two columns that fail to auto-map — leftovers from an earlier session's
graph selections, fuzzily re-resolved.

### Fix spec

1.1 **One source of truth, always visible.** The graph plots exactly the
    rows whose Graph checkbox is checked in the sensor panel — nothing
    else. If a `graph_sensors` entry has no visible panel row after a CSV
    load, it is PRUNED at load time (with a one-line status message:
    "Dropped N stale graph selections"). No invisible plotting state, ever.
1.2 **Checkbox round-trip.** Any surviving `graph_sensors` entry must render
    as a CHECKED box on its panel row (including rows in the Ungrouped /
    "Not on diagram" section — if it's plotted, its checkbox is visibly on).
1.3 **Kill fuzzy resolution at plot time.** `_resolve_graph_sensors`'s
    normalized matching goes away; after 1.1 the checked row already knows
    its exact dataframe column (the row IS a CSV column in the CSV-driven
    panel). Plot that column only. (The whitespace-normalization fix at CSV
    load, MAPPING plan §2.4, removes the last reason for fuzziness.)
1.4 **Session persistence stays** (graph selections are worth saving) but is
    validated against the loaded CSV on restore, same pruning rule as 1.1.

---

## Part 2 — Toolbar redesign: direct manipulation first

### Design rule (the owner's SolidWorks point, made explicit)

A control earns a toolbar slot only if it is (a) used constantly and (b) not
expressible as a direct gesture on the graph itself. Everything else goes
into one grouped menu or becomes a gesture. Budget: **max 3 visible controls
on the graph toolbar.**

### Gestures (replace five buttons)

| Gesture | Action |
|---|---|
| **Scroll wheel over the Y-axis strip** | Dynamic Y zoom, anchored at the cursor's value — the owner's headline request. Zoom in/out smoothly as you scroll; X untouched. |
| Scroll wheel over the X-axis strip | Dynamic X (time) zoom anchored at cursor; Y untouched. |
| Scroll wheel inside the plot | X (time) zoom anchored at cursor. Shift+scroll = Y zoom. |
| Left-drag inside the plot | Pan. |
| Right-drag (or hold B + drag) | Box zoom. |
| Double-click plot | Fit everything (X and Y). |
| Double-click Y-axis strip | Fit Y only. Double-click X-axis: fit X only. |

The axis strips must have generous hit zones (the full margin area left of /
below the plot) and a subtle hover highlight so discoverability is not a
problem.

### Toolbar after (3 controls)

`[ Fit ]  [ 📷 Snapshot ]  [ Tools ▾ ]`

- **Fit** — same as double-click; kept as a button for discoverability.
- **Snapshot** — Capture Snapshot as-is (feeds Comparison tab).
- **Tools ▾** — menu holding: Auto-Detect Defrost…, Sensor Ranges… (the
  current Range/Apply Range pair becomes one dialog with its own Apply), and
  any future one-off actions.

### Removed outright

| Button | Why it can go |
|---|---|
| Reset Zoom | = Fit (double-click / Fit button). |
| Box Zoom (mode toggle) | = right-drag gesture; no modal state needed. |
| Lock X / Lock Y | Existed to constrain wheel-zoom; axis-anchored scrolling makes the constraint the DEFAULT (scroll on the axis you want). Delete. |
| Fit Y | = double-click the Y axis. |
| Range / Apply Range | Merged into one "Sensor Ranges…" dialog under Tools ▾. |

The stats table under the graph and the CSV/Config caption stay unchanged.

---

## Part 3 — Standing UI rule for ALL future work

Written down so "adding buttons without a plan" stops being possible:

1. Every tab has a toolbar BUDGET (Graph: 3, Diagram: Mode + Zoom + report
   per MAPPING plan Part 1). A new feature must either fit the budget by
   replacing something, become a gesture, or live in that tab's single
   Tools ▾ menu — a new top-level button is never the default.
2. Prefer direct manipulation on the artifact (scroll the axis, drag the
   component, right-click the row) over remote-control buttons.
3. State that changes what the user sees must be visible somewhere
   (checkbox, chip, status bar) — the phantom-graph bug is what hidden
   state looks like.

## Part 4 — Acceptance

With IDD5SL12WE open and `DataDOE80f.csv` loaded:
1. Fresh app start → Graph tab is EMPTY until a Graph checkbox is checked;
   the two "Return Air … RE" phantom series are gone; if a stale session had
   them, the status bar reports the pruning.
2. Checking any green row plots exactly that CSV column; the row's checkbox
   reflects it; unchecking removes it.
3. Scrolling over the Y axis zooms Y only, smoothly, centered on the cursor;
   over the X axis zooms time only; double-click fits; right-drag box-zooms.
4. The toolbar shows exactly Fit / Snapshot / Tools ▾. Auto-Detect Defrost
   and Sensor Ranges work from the Tools menu.
5. Save session → reload → graph selections restore ONLY for columns present
   in the loaded CSV, and their checkboxes are checked.
