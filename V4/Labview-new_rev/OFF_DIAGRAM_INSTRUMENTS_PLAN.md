# Off-Diagram Instruments — Structure & Consistency Plan

Status: PLANNING ONLY (2026-07-03). Companion to
MAPPING_AND_HIGHLIGHT_FIX_PLAN.md (CSV-driven visibility) and
GRAPH_TAB_REDESIGN_PLAN.md (UI budget rules). Covers the sensor-box area of
the diagram page and its disagreement with the sensor panel.

## The two problems in the screenshot

**P1 — Panel and diagram contradict each other.** The panel's "Not on
diagram (29)" group contains sensors that are plainly visible ON the diagram
with live values (Ambient Dry Bulb A/B, Wall temps, Compressor Watts, Run
Time, Flowmeter, Main Liquid Line Temp…). Two different definitions of "on
the diagram" are in play: the panel's grouping only counts component/process
dots, while these sensors are mapped into SENSOR-BOX slots. (The old color
legend in `sensor_panel.create_sensor_item` even distinguished "mapped to a
visible diagram dot" from "mapped off the process diagram" — the new
CSV-driven grouping lost that distinction.)

**P2 — The box area has no layout system.** The three boxes ("Ambient &
Walls", "Case Electrical & System", "Compressor Aux") are dropped at
generation time as absolute positions (`_ensure_canonical_sensor_boxes`,
anchor + fixed 390px gaps) with fixed slot lists. After CSV-driven hiding,
invisible slots leave HOLES instead of compacting — hence the scattered
floating rows with huge vertical gaps. Nothing defines column widths,
category order, alignment, or where new slots go. It reads as unplanned
because it is.

---

## Part 1 — One definition of "home" (fixes P1)

A single data_manager function classifies every CSV column:

```
sensor_home(column) -> 'process'     (mapped to a component/process dot)
                     | 'instrument'  (mapped to an instrument-panel slot, §2)
                     | None          (truly homeless)
```

Rules:
- The sensor panel's groups use it: process-mapped rows group as today;
  instrument-mapped rows group under their instrument CATEGORY name (§2) —
  NOT under "Not on diagram".
- **"Not on diagram" (the Ungrouped section) contains ONLY `None` rows** —
  CSV columns with no home anywhere. After this fix the reference session's
  count drops from 29 to the genuinely homeless few (e.g., `Return Air 2 in
  RE`, `Return Air 12in RE`, `BTU`, `Total Flow`, `AVG Product temp`,
  `Air off ctr evap …` — each of which is then either taught an alias or
  assigned a slot via the MAPPING plan §2.1b flow).
- Locate/highlight (MAPPING plan Part 3) works identically for instrument
  slots: clicking "Ambient Dry Bulb A" scrolls to and flashes its card row.

## Part 2 — The Instrument Panel: a designed section, not floating boxes

Replace the three floating sensor boxes with ONE full-width diagram section,
consistent with the page's existing vertical rhythm — the user scrolls:

```
[ Refrigeration Process ]
[ Airflow Diagram      ]
[ Shelving Diagram     ]
[ Instrument Panel     ]   ← NEW, full width, grows downward as needed
```

Inside the Instrument Panel boundary: a fixed **3-column card grid**. Cards
in a defined order, each card auto-sized to its VISIBLE rows (no holes —
hidden slots compact away; a card with zero visible rows is not drawn):

| # | Card | Canonical families (data-driven, one table in code) |
|---|---|---|
| 1 | Ambient & Room | `T_amb.*`, wall/ceiling temps (`T_wall.*`, `T_ceil*`) |
| 2 | Case Electrical | `W_case*`, `A_case*`, `V_case*`, `W_fan*`, `A_fan*`, `W_aswt*`, `A_aswt*`, `W_frame*`, `A_frame*` |
| 3 | Compressor Electrical | `W_comp*`, `A_comp*`, `V_comp*` (one card per unit when multi-compressor) |
| 4 | System & Flags | `t_run`, `f_defrost`, `f_alwaysoff`, `m_dot_meas`, totals (`*.total`) |
| 5 | Refrigerant Misc | `T_liq.main`, flowmeter inlet temp, other loose refrigerant temps |
| 6 | Other Instruments | any instrument slot not matched above (never invisible-by-accident) |

Row layout inside a card — one aligned grid, identical everywhere:

```
● Sensor Label            #nnn      value
```

- Dot (status color), label left-aligned, sensor # right-aligned in its
  column, live value right-aligned. No per-box drift; one shared column
  spec.
- Rows sort in the card's canonical order (defined in the same table), not
  insertion order.
- Cards flow top-to-bottom, left-to-right; the section boundary grows with
  content. Vertical space is free — NEVER squeeze; add rows downward.
- The whole section participates in Zoom-to-Fit and locate-scrolling.

Migration: `_ensure_canonical_sensor_boxes`'s three hardcoded boxes and
their absolute positions are replaced by this generated section; existing
saved diagrams get their box slot mappings carried into the matching cards
(mappings are keyed by canonical ids already — no re-mapping needed).

## Part 2b — Visual language: ONE theme for the whole page (owner requirement)

Background: `SensorBoxItem` (diagram_components.py:3521) is a leftover from
an older design iteration — it carries its own fonts, its own three-column
header ("Sensor Label / # / sensor value"), its own frame style, none of
which the rest of the diagram uses. The process diagram evolved
(`BaseComponentItem`, Boundary sections, dot/label chips) and the boxes
never followed. The Instrument Panel must NOT inherit any of that: it is
drawn with the SAME visual primitives as the process diagram, and the old
SensorBoxItem rendering is deleted.

Shared style spec (extract into ONE place — a `diagram_theme.py` module or
constants block — and make BOTH the process diagram and the Instrument
Panel read from it; no second copy of any value):

| Element | Rule |
|---|---|
| Section boundary | Identical to the existing section boundaries ("Refrigeration Process", "Airflow Diagram", "Shelving Diagram"): same dashed grey pen, same title font/placement. "Instrument Panel" is just the fourth sibling — visually indistinguishable in style. |
| Cards | Drawn like components: same rectangle style as `BaseComponentItem` (same border color/width, same fill/gradient, same corner treatment), same title convention as component labels (e.g., `[Ambient & Room]`). A card should look like a component that happens to contain sensor rows — not like a spreadsheet. |
| Sensor dots | The SAME dot: same radius, same status color scheme (`_get_sensor_color` grey/gold/green/red), same selection/flash behavior as process dots. No square checkbox-style markers (the current boxes use green squares — gone). |
| Value labels | The same label-chip style used next to process dots (white rounded chip, same font, same offsets) — a value on a card looks exactly like a value on the condenser. |
| Fonts | One font family + size set for the entire scene (component labels, card rows, section titles at their existing sizes). No per-item `QFont('Arial', 9)` scattered around — all from the theme module. |
| Spacing | One spacing grid (row height, card padding, column gutter) defined in the theme module; cards and components share margins so columns visually align with the diagrams above. |
| Column headers | The per-box "Sensor Label / # / sensor value" header rows are REMOVED — alignment makes them unnecessary, and no other part of the diagram has table headers. Sensor # stays as part of the row, de-emphasized (smaller/grey), since it is lab-useful. |

Rule going forward (extends the standing UI rule in
GRAPH_TAB_REDESIGN_PLAN.md Part 3): any new on-canvas element must take its
colors, fonts, pens, and spacing from the theme module. A visual value that
appears literally in a component class is a review defect.

## Part 2c — Viewing model: fit WIDTH, scroll height (owner decision 2026-07-03)

The diagram page is a vertically growing document (Process → Airflow →
Shelving → Instrument Panel). Fitting the whole page makes everything
shrink as sections are added. Therefore:

- **"Zoom to Fit" fits the page WIDTH only** (content width + small margin
  scaled to the viewport width). The vertical dimension is NOT scaled to
  fit — the user scrolls down through the sections at a readable size.
- **This is also the DEFAULT view**: after Open Case, New Case, session
  load, or diagram generation, the view is width-fitted and scrolled to the
  TOP of the page (Refrigeration Process first).
- Vertical navigation: mouse wheel scrolls vertically (as in any document);
  the existing middle-drag pan stays. Locate/highlight (clicking a sensor in
  the panel) scrolls vertically to the target at the current zoom rather
  than re-fitting.
- "Fit everything" (both axes) remains available as a secondary action for
  overview purposes — e.g., Ctrl+click on Zoom to Fit or a menu entry — but
  is never the default.
- The existing width-based minimum-zoom clamp in the diagram wheel-zoom
  already agrees with this model; keep it consistent with the new fit.

## Part 3 — Interaction consistency

- Clicking an instrument row's dot behaves exactly like a process dot
  (select/locate; map when in Mapping mode with a selection).
- CSV-driven visibility (MAPPING plan §2.1) applies: only slots with data
  show; ghost-reveal in Mapping mode when assigning an Ungrouped sensor.
- The panel's group headers for instrument categories use the card names,
  so panel and diagram use the SAME words for the same things.

## Part 4 — Acceptance (reference: IDD5SL12WE + DataDOE80f.csv)

1. Panel "Not on diagram" shrinks to only truly homeless columns; every row
   in it is absent from the diagram, and every mapped sensor's panel group
   name matches the card it appears in.
2. The Instrument Panel renders as one boundary section under Shelving:
   3-column card grid, zero empty holes, aligned label/#/value columns,
   cards only for non-empty categories.
3. Clicking "Ambient Dry Bulb A" in the panel scrolls the diagram to its
   card row and flashes it; clicking the row's dot selects the sensor in
   the panel.
4. Load a CSV with more/fewer instrument columns: cards compact/grow
   accordingly; nothing overlaps; Zoom-to-Fit includes the section.
5. Viewing model: opening a case lands width-fitted at the top of the page;
   clicking Zoom to Fit never changes the vertical scale to squeeze the
   whole page in; wheel scrolls down through Airflow/Shelving/Instrument
   Panel at constant zoom; locate scrolls to the target without re-fitting.
6. Theme check: screenshot the full page — the Instrument Panel is visually
   indistinguishable in style from the sections above it (same boundary
   pen/title, same box style, same dots, same chips, same fonts). No green
   square markers, no table headers, no leftover SensorBoxItem rendering
   anywhere. `grep` finds no hardcoded fonts/pens in the card code — all
   values come from the theme module.
