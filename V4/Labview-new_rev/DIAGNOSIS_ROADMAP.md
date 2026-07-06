# Diagnosis Roadmap — "Look at the diagram and know what to change"

Status: **APPROVED BY OWNER 2026-07-04** — this is the agreed direction
for everything after MASTER_CHECKLIST C10. The owner's end goal: open a
test, look at the diagram, and see WHAT is wrong and WHICH parameter to
change.
Owner constraints that shape everything here:

- **The owner is building this app to DEVELOP refrigeration expertise, not
  to apply expertise he already has.** No step may assume the owner can do
  expert analysis by hand. The diagnostic knowledge comes from published
  refrigeration fundamentals encoded in the app; the app teaches as it
  diagnoses.
- Baseline strategy approved by owner: design baseline → family transfer →
  golden run (Phase 3).
- Healthy skepticism about the 33 existing scenarios: they are UNVALIDATED
  until proven on real data. Trust is earned through the feedback loop
  (Phase 2c), never assumed.

Prerequisite: MASTER_CHECKLIST C1–C10 complete (mappings/lexicon correct —
diagnosis on top of wrong data is fiction).

---

## Phase 1 — Make what exists visible (A + B)

**1a. Verdict on the diagram.** Findings from the diagnostics engine render
ON the process diagram: severity badge on the implicated component, a
banner line at top ("Undercharge suspected — SH high, SC low"), click →
evidence panel. Purely presentation; engine untouched.

**1b. Scorecard verdict.** The case/test targets produce an explicit
PASS/FAIL header per target, each failed target linked to the sensor/calc
that broke it. Answers "is this test acceptable?" before any diagnosis.

**1c. Presentation discipline — the noise rules (added 2026-07-04 after
the first live run painted CRIT boxes on every component of a
healthy-looking test).** These are hard requirements, not styling:

1. **Untrusted scenarios never paint the diagram.** All 33 scenarios start
   as CANDIDATES (roadmap §2d). Candidate findings live ONLY in the
   Diagnostics tab, tagged "unvalidated". The diagram shows findings from
   TRUSTED scenarios plus target/scorecard failures — nothing else. On day
   one that means the diagram shows scorecard results and the SI physics
   sanity checks only; red spreads as trust is earned, not before.
2. **One story, not N badges.** Findings are ranked (severity × scenario
   confidence × upstream-ness); the banner states the TOP finding only,
   with "+N more" opening the ranked list. A component carries at most ONE
   badge — the highest finding implicating it. Related-symptom suppression:
   when a root-cause finding fires (e.g., compressor), downstream findings
   that are its expected consequences (starved TXVs, warm coils) collapse
   under it instead of badging separately — six red boxes from one cause is
   a rendering of the dependency tree, not six alarms.
3. **Severity discipline.** CRITICAL is reserved for physics-impossible /
   sensor-sanity violations and confirmed-trusted rules; everything else
   presents as an observation (neutral chip), never red.
4. **Every visible finding must survive the sanity of its own inputs** —
   a scenario whose input columns failed integrity/mapping checks is
   suppressed with a "insufficient data" note, not shown red.
5. First validation task from this incident: CP-3 "Not Compressing" fired
   on a test with ~52→121 psi (healthy-looking compression for an MT R290
   water-cooled case) — run it through the 2a harness + threshold review
   before it is ever allowed on the diagram again.

**1d. Refrigerant-state storytelling (added 2026-07-04 — owner request;
this is the learning bridge the app was missing).** Two linked views,
both fed by MEASURED data, not static topology:

1. **State-colored pipes on the process diagram.** ANALYSIS MODE ONLY —
   with Analysis off, lines keep today's single neutral color. When on,
   each pipe segment renders its computed refrigerant state: subcooled
   liquid = solid blue, superheated gas = orange (deep orange on the
   discharge/high side, lighter orange on the suction side — pressure_side
   is already tracked per pipe), two-phase = striped blue/orange, with
   a small state chip at key points ("liquid, SC 12°F" at TXV inlet;
   "two-phase" after each TXV). The existing `fluid_state` propagation and
   Analysis overlay are the substrate; the change is computing state from
   live P/T per segment and making it the DEFAULT Analysis view. A
   negative-subcooling event then LOOKS like what it is: stripes where
   blue should be, right at the condenser outlet.
2. **Live P-h cycle view.** The existing ph_diagram widgets plot the
   actual cycle points (from the same calculations) on the saturation
   dome, updated with the loaded test. Every finding gets a "Show on
   cycle" action highlighting the offending state point (e.g., condenser
   outlet sitting INSIDE the dome = negative subcooling made visible).
   A compact P-h thumbnail may sit beside the process diagram in Analysis
   mode; clicking opens the full view.
3. **Findings must teach the fork, not just the flag** (2c applied
   concretely): the negative-subcooling finding must present the
   three-way differential — condenser performance vs undercharge vs
   pressure-drop measurement artifact — with the case's OWN corroborating
   values (water ΔT, coil SH, downstream SC at TXV inlets) and state
   which branch the evidence currently favors.

**P-h view detailed spec (owner Q&A 2026-07-04):**
- **Dome:** one saturation curve per REFRIGERANT (from the property
  library via the existing `ph_diagram_generator`), identical for every
  case configuration. Topology never alters the dome — it only decides
  how many traces are drawn on it.
- **Component→leg mapping:** compressor = suction→discharge leg;
  condenser = high-pressure leftward leg; each TXV = vertical
  constant-enthalpy drop; each evaporator = low-pressure rightward leg
  ending at its own superheat point. Components are legs of the path,
  not objects placed between the lines.
- **Configurations:** shared system (1–3 modules) = ONE cycle whose
  expansion/evaporation portion fans into 2–3 overlaid branches
  (branch spread is itself diagnostic); cassette = N independent traces
  with per-cassette toggle chips; single module = one trace.
- **Location:** collapsible Cycle panel docked beside the process diagram
  in Analysis view (thumbnail → expand), plus "Show on cycle" on every
  finding (offending state point highlighted/pulsing). Not a separate
  top-level tab.
- **Data:** identical pipeline to the diagram dots — same time-range
  filter, same aggregation; changing the selected hours moves the cycle
  points in lockstep with the diagram. Enthalpy computed from measured
  P/T pairs via the property library (as Calculations already does).
  Default = averaged window (steady-state snapshot); a time scrubber
  animating the cycle over the test is a LATER enhancement, not day one.
- **What appears on the cycle (owner Q&A round 2):** only components that
  CHANGE the refrigerant state get a leg — compressor (rising leg),
  condenser (top leg), expansion device (vertical drop), evaporators
  (bottom legs). Distributors/headers/junctions are points on the path
  (no state change → no leg); filter drier is a point unless clogged
  (then a visible pressure step — itself diagnostic). The process diagram
  is NEVER multiplied: a 3-module shared case remains ONE process diagram
  and ONE cycle with ×3 overlaid TXV/evap branches; N cassettes = N full
  traces with per-cassette toggle chips on one dome.
- **Activation flow (explicit):** open case → Diagram tab as always →
  tick the Analysis checkbox → pipes take state colors AND a Cycle
  thumbnail docks at the right edge of the diagram view → click thumbnail
  (or a finding's "Show on cycle") to expand the full P-h panel beside
  the diagram, offending point pulsing. Untick Analysis → gone. Never on
  the Cases screen, never a separate top-level tab.

## Phase 2 — Trustworthy diagnosis (C, reframed)

**2a. Arithmetic verification harness (implementer's job, NOT the
owner's).** A headless test that recomputes every calculated column
(SH, SC, saturation temps, mass-flow cross-check, capacity) from raw CSV
values using the textbook formulas, independently of the app's pipeline,
and asserts agreement. Catches software bugs the way the zoom bug was
caught: by measurement. No domain judgment involved. This gate runs in CI
fashion on all 7 datasets before any scenario work.

**2b. Knowledge base from PUBLISHED fundamentals.** The symptom→cause→
adjustment rules are standard service knowledge (SH/SC interpretation
matrix, pressure-ratio norms, defrost recovery patterns). Encode them as
data (like the family rulebook): each rule = conditions + cause +
adjustable parameter + direction (+ magnitude when computable from the
case's parts/settings, e.g. GPM from design flow, charge steps in oz).
Existing 33 scenarios are mapped ONTO this base: keep, retune, or park
each one. Rules reference the case's ACTUAL knobs (charge, TXV turns,
GPM, CFM, defrost schedule, setpoints).

**2c. Teaching mode — every finding explains its reasoning (owner
requirement).** A finding is a worked example, always showing: the
measured values, the targets, the physical reasoning chain in plain
language, the recommended adjustment, and what WOULD have pointed to the
alternative cause ("if SC were normal, suspect the TXV instead"). The
owner learns the discipline BY USING the app — this is a primary product
goal, not a nicety.

**2d. Confidence loop instead of upfront validation.** Every surfaced
finding carries Confirm / Reject buttons. When the lab later learns the
true cause, the owner clicks once; the app records outcome vs prediction
per scenario per family. Scenario scoreboards (fired/confirmed/rejected)
decide what stays enabled by default and how thresholds tune per family.
The validation set builds itself during normal work — no expert backlog
required. Scenarios start in "candidate" state (shown with a confidence
tag), graduate to "trusted" on evidence.

## Phase 3 — Baselines for every case, including first-of-kind (D)

Three layers, handing off:

**3a. Design baseline (day one, automatic).** Targets seeded from family +
temp class + parts + settings (compressor rated data, TXV tons, design
GPM/CFM, refrigerant): expected SH/SC bands, pressure windows, product
temp band. Catches gross problems on the first run of a never-tested case.

**3b. Family transfer (day one, borrowed).** Sibling cases (same family +
temp class), normalized per foot / per circuit / per module, provide
expected PATTERNS: discharge-air profile shape, steady-state SH, defrost
recovery curve. New case of an existing family inherits them with a
"borrowed from siblings" tag. First-of-kind family: only 3a applies (true
for any lab on earth).

**3c. Golden run (earned).** The first test the owner marks acceptable
becomes the case's own baseline; later tests render as DELTAS on the
diagram ("suction 4°F warmer than golden, all else equal"). A per-test
parameter log (charge, TXV setting, GPM, …) lets the app state "the only
change vs the passing run is +3 oz charge." Layers 3a/3b remain as
sanity rails.

## Later (parked)

- Model-residual localization (extend PV1 / cycle solver): biggest
  predicted-vs-measured residual points at the suspect component.
- Learned patterns across accumulated history — revisit after a season of
  3c data and 2d outcomes exist.

## Order of work

1. Phase 1a+1b (presentation of existing machinery + targets).
2. Phase 2a harness; then 2b/2c knowledge base + teaching mode; 2d loop.
3. Phase 3a (seeded targets) → 3b (sibling transfer) → 3c (golden runs).

Each phase lands behind the same evidence rules as everything else in
MASTER_CHECKLIST / DEBUGGING_METHODOLOGY: measured acceptance, real-launch
verification, no claim without evidence.
