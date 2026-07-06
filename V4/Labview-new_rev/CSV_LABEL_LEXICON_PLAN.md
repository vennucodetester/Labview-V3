# CSV Label Lexicon — Scaling Auto-Mapping to Every Case

Status: PLANNING/SCOPE ONLY (updated 2026-07-04 after the owner added the
ID6SU* datasets). Based on a full scan of every CSV header in `DATA/` —
**7 case variations, 343 unique labels, 115 unknown.** Goal: a new case's
CSV should auto-map ~100% on first load. Onboarding a case must take
minutes, not a week.

## Scan result (measured 2026-07-04, all 7 cases)

| Case | Unique labels | Unknown | Coverage |
|---|---|---|---|
| IDD5SL12WE (12 ft) | 150 | 0 | 100% (vocabulary source) |
| IDD5SL4WE (4 ft) | 79 | 2 | 98% |
| IDD5SL6WE (6 ft) | 109 | 10 | 91% |
| IDD5SL8WE (8 ft) | 115 | 16 | 87% |
| ID6SU12WE | 160 | 28 | 83% |
| ID6SU6WE | 104 | 27 | 75% |
| ID6SU8WE | 115 | 61 | **47%** |

The 115 unknowns still compress into a finite family list — mostly
MECHANICAL rules, plus a handful of new hardware concepts:

| Family | Examples | Rule that kills it |
|---|---|---|
| F1. Any inch position | `… Air 36 in LE/RE`, `36in` (no space) | Parse `<N> in/​in` for ANY N (grammar L1) + geometry slots (L2) |
| F2. Center positions | `PS Top shelf CTR …`, `Primary Disch Air CTR`, `Return Air CTR` | CTR is a valid column/position everywhere, incl. air bands |
| F3. Unqualified singular | `Into Distrubutor`, `S.H.`, `L Coil Inlet` (one probe per coil) | Uniqueness rule (L3) |
| F5. Token synonyms & abbreviations (the ID6SU8WE killer — 53% unknown) | `Disch`→Discharge, `Sec`→Secondary, `L/R`→Left/Right (`L Coil`, `R TXV Bulb Temp`, `L DA Sensor`), `HE`→HeatX (`Water in HE`), `coil`↔`evap` (`Air In L Coil 6in LE` vs `Air in left evap 6 in LE`), `condeser` typo, double spaces (`Secondary  Disch`), case-insensitivity (`inlet of filter drier`, `subcooling LH`) | A token-normalization layer BEFORE matching (L0) — one synonym table applied to every label |
| F6. Row-name variants | `PS 2nd/3rd/4th shelf` vs `Second/Third/Fourth`, `Fifth shelf` (new row count) | Ordinal ↔ word equivalence in L0; row count from topology |
| F7. Numbered instead of sided units | `TXV 1 inlet`, `TXV 2 inlet`, `Into distributor 1/2` | Number↔side equivalence: unit N maps to the Nth expansion circuit left-to-right |
| F8. TXV-split architecture (ID6SU8WE) | `Into TXV Split`, `Out of TXV Split L/R`, `Common coil outlet` | NEW topology element: one expansion device feeding multiple coils through a splitter (see Owner inputs) |
| F9. Three-phase / aux electrical (ID6SU12WE, confirmed in real headers) | `L1/L2/L3 Amps/Volts/Watts`, `Total L1/L2/L3 Watts`, `120V …`, `Total Amps/Volts/Watts` | New instrument-card family, grammar `[Total] L<n>|120V <unit>` |
| F10. Filter drier (confirmed) | `Inlet of filter drier`, `Case inlet after filter drier` | Picker option (owner decision) + liquid-line slots |
| F11. Misc singles | `Compressor Hertz` (≡ RPM family), `Air Velocities FPM` (new sensor type), `AVG Air In/Off`, `Subcooling RH/LH` (calc synonyms), `Blank` (dead column), `Time` (second timestamp col) | Seeded aliases; ignore-list for `Blank`/`Time`-style columns |

**Root cause unchanged, now proven at scale:** a dictionary built from one
case. ID6SU8WE — written by a different technician with different
shorthand — drops to 47% because the dictionary knows words, not language.
The grammar + a token-synonym layer turns every family above into one rule
instead of hundreds of entries.

## The fix — grammar + geometry, not more dictionary entries

### L0. Token-normalization layer (new — kills F5/F6, the biggest family)
Before any matching, every label is tokenized and each token normalized
through ONE synonym table: `disch→discharge`, `sec→secondary`,
`l/r→left/right` (when positional), `he→heatx`, `coil↔evap` (air-sensor
context), `ctr→center`, `2nd→second` (all ordinals), lowercase, collapse
whitespace, common-typo tolerance (`distrubutor`, `condeser`). The table
lives in ONE data file next to the alias DB; adding a technician's new
shorthand is a one-line edit, never code.
`<Band> Air <N> in <LE|RE>` parses for ANY number N → canonical
`T_air.<band>.<N><le|re>`. Same for product columns:
`PS <row> shelf [<N>] <LE|CTR|RE> <Front|Rear>` for any N. The inch value
is DATA, not vocabulary. (Normalization already tolerates the `Distrubutor`
typo class — keep that.)

### L2. Slots generated from geometry (gives grammar somewhere to land)
Air-band and shelf-column dots must be generated from the case's length
and family pitch (rulebook), and — like `_ensure_product_sensor_dot`
already does for shelves — a dot for a NEW inch position found in the CSV
is created at its proportional x on the band. No fixed position lists
anywhere.

### L3. Uniqueness rule for unqualified names (kills F3)
When a case has exactly ONE candidate of a kind (one module → one
distributor, one superheat, one TXV…), the unqualified label ("Into
Distributor", "S.H.", "Coil Inlet 3") resolves to that sole candidate.
Applies generally: qualifier-less labels are valid whenever resolution is
unambiguous for THIS case's topology.

### L4. New canonical families for the F4 hardware (confirm against real CSV)
- **Three-phase electrical**: `L1/L2/L3` volts/amps/watts + per-phase
  totals + `120V` aux circuit + `Total Amps/Volts/Watts` → rows on the
  Case Electrical instrument card (grammar: `[Total] L<n>|120V <unit>`).
- **Filter drier**: `Inlet of filter drier`, `Case inlet after filter
  drier` → liquid-line temp slots. Requires the filter drier to exist as
  an OPTIONAL topology element (the old dead wizard had it; the new picker
  doesn't — add as a picker option or auto-add the component/dots when a
  case's parts/CSV include one — owner to confirm preference).
- **Per-coil outlet probes**: `CTR Coil Outlet`, `Left Coil Out 2` —
  grammar must accept both `Out` and `Outlet`, with and without circuit
  number (single probe per coil vs per circuit).
- **AVG aggregates**: `AVG Air In/Off`, `AVG Product temp` → calculated/
  aggregate instrument slots alongside `BTU`, `Total Flow`.

### L5. The coverage tool (kills the week-per-case problem)
A "Scan data folder…" action (Cases screen) — also runnable headless:
reads every CSV header in a chosen folder tree, resolves every label
through the CURRENT grammar, and writes `LEXICON_COVERAGE.md`: coverage %
per case, unknowns grouped by detected family, each with a suggested
resolution. **Onboarding a new case = drop its CSVs in, run the scan, get
100% (or consciously teach the exceptions via the alias flow) BEFORE the
test ever runs.** This scan also becomes a regression gate: grammar
changes must keep all existing datasets at 100%.

### L6. Known loose end folded in
`Compressor RPM` shows mapped but has no dot — the compressor's `RPM`
port is enumerated but never rendered (predicted in SENSOR_INTEGRITY plan
§5.3 suspects). Resolve via Invariant A: render an RPM chip on the
compressor or classify RPM as an instrument slot.

## Owner decisions & remaining inputs

1. ✅ ID6SU* datasets added to DATA (2026-07-04) — F4 confirmed against
   real headers and expanded into F5–F11 above.
2. ✅ **Filter drier = picker option** (owner decision 2026-07-04): a
   checkbox/option in the New Case topology picker (WORKFLOW plan §5 gains
   it as an optional-components step alongside defrost); when checked, the
   generator draws the filter drier on the liquid line after the condenser
   with its inlet/outlet temp slots. Auto-SUGGEST only: if a scanned CSV
   contains filter-drier labels for a case configured without one, the
   coverage report says so — it never silently adds hardware.
3. OPEN — TXV-split architecture (F8): ID6SU8WE has ONE expansion device
   feeding TWO coils through a split (`Into TXV Split`, `Out of TXV Split
   L/R`, `Common coil outlet`). The current topology model (one expansion
   device per module, or per cassette) cannot represent this. Owner to
   describe how this case is actually plumbed so the picker/generator can
   model it (e.g., "shared TXV + splitter" as an expansion-device layout
   variant).
4. OPEN — `Air Velocities FPM` (F11): where should air-velocity readings
   live — instrument card or a dot on the airflow band?

## Acceptance

1. Coverage scan reports **100% on all four existing datasets** (the 18
   current unknowns resolve via L1–L3 with zero per-case manual work).
2. Opening each case + loading its CSV: "Not on diagram" is empty (or
   contains only labels the owner deliberately left untaught).
3. After ID6SU12WE data arrives: same 100% via L4, including filter-drier
   dots and three-phase electrical card rows.
4. A brand-new case folder dropped into DATA reaches ≥95% coverage on
   first scan with no code changes; the report explains every miss.
