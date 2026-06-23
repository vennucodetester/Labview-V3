# Refrigeration Diagram — All 7 Scenarios at a Glance

## Wizard Options (apply to all scenarios unless noted)

| Option | Choices | Notes |
|---|---|---|
| Condenser type | Air Cooled / Water Cooled | Hidden for Remote cases |
| Expansion device | TXV / Cap Tube | Cap Tube hides the sensor bulb port |
| Filter Dryer | Yes / No | Optional |
| Defrost | None / Electric / Hot Gas / Reverse Cycle | Hot Gas auto-adds HotGasValve + HotGasLoop |
| Discharge curtain | Single / Dual | Dual adds a second AirSensorArray per column |
| Shelf rows | 3–7 | Shelving always included, one grid per column |
| Return air block | Always included | 1 AirSensorArray spanning full case width |
| Air sensor counts | NOT in wizard | Default 2 per array; user adjusts by double-clicking each array after generation |

---

## Component Presence by Scenario

| Component | Mod 12ft | Mod 8ft/6ft | Mod 4ft | Non-Mod (1–5 dr) | Cassette (1–3) | Freedom | Remote (any) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Compressor | 1 shared | 1 shared | 1 shared | 1 shared | 1 per unit | 1 shared | ✗ (stub) |
| Condenser | 1 shared | 1 shared | 1 shared | 1 shared | 1 per unit | 1 shared | ✗ (stub) |
| Filter Dryer | optional | optional | optional | optional | 1 per unit (opt) | optional | optional |
| TXV / Cap Tube | 3 (1 per module) | 2 (1 per module) | 1 | 1 | 1 per unit | 1 | same as SC |
| Sensor Bulb | 1 per TXV | 1 per TXV | 1 | 1 | 1 per unit | 1 | same as SC |
| Evaporator | 3 (1 per module) | 2 (1 per module) | 1 | 1 | 1 per unit | 1 | same as SC |
| Splitter Junction | 1 (3-way) | 1 (2-way) | ✗ | ✗ | ✗ | ✗ | same as SC |
| Merger Junction | 3 (1 per module) | 2 (1 per module) | 1 | 1 | 1 per unit | 1 | same as SC |
| Collector Junction | 1 (3-in) | 1 (2-in) | ✗ | ✗ | ✗ | ✗ | same as SC |
| HotGas Valve + Loop | 1 per module (opt) | 1 per module (opt) | 1 (opt) | 1 (opt) | 1 per unit (opt) | 1 (opt) | same as SC |
| Fan | 3 (1 per module) | 2 (1 per module) | 1 | D (1 per door) | same as underlying case | 1 | same as SC |
| Post-coil AirArray | 3 (1 per module) | 2 (1 per module) | 1 | D (1 per door) | same as underlying case | 1 | same as SC |
| Curtain AirArray | 3–6 (1 or 2 per module) | 2–4 | 1–2 | D–2D | same as underlying case | 1–2 | same as SC |
| Return Air block | 1 full-width | 1 full-width | 1 | 1 full-width | 1 full-width | 1 | same as SC |
| ShelvingGrid | 3 (1 per module col) | 2 (1 per module col) | 1 | D (1 per door col) | same as underlying case | 1 | same as SC |
| Sensor Box | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| Remote Line Endpoints | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | 2 (Liq In + Suc Out) |

> **Cassette air side / shelving note:** Cassette units sit on top of a case. The shelving, fans, and air arrays follow the **underlying case** (modular or non-modular, picked separately in the wizard) — not the cassette unit count. Only the refrigerant loops (compressor → condenser → TXV → evap) are tied to the cassette unit count.
>
> **Cassette uniform config:** All cassette units on a case always share the same design. The wizard asks once — TXV or Cap Tube, filter dryer yes/no, hot gas bypass yes/no, condenser type, circuits per unit — and applies it identically to every unit. It is not possible for unit 1 to have a TXV while unit 2 has a Cap Tube, or for one unit to have a filter dryer while another doesn't.

---

## Port Naming — The Key Principle

Port names on every component are always the same generic names: `inlet`, `outlet`, `bulb`, `outlet_circuit_1` … `outlet_circuit_N`. The port name itself **never** includes Left/Right/Center or a unit number.

What differentiates components across modules or units is the **`circuit_label` property** set on each component. The calculation engine searches the diagram for components with `circuit_label = 'Left'`, `'Center'`, `'Right'` to identify which module each component belongs to. The full sensor mapping key is:

```
"{ComponentType}.{unique_component_id}.{port_name}"
e.g.  "TXV.txv_a1b2c3.inlet"   ← the component_id is unique
```

The `circuit_label` property on that specific TXV component is what tells the engine it belongs to Left / Center / Right / unit 1 / etc.

---

## Circuit Labels and Calculation Coverage by Scenario

| Scenario | circuit_label on TXV + Evap | Calculation engine coverage |
|---|---|---|
| **Modular 12ft** | Left, Center, Right | Fully calculates all 3 modules independently |
| **Modular 8ft / 6ft** | Left, Right | Calculates LH + RH; Center column empty |
| **Modular 4ft** | Left | Calculates LH only; Center + RH empty |
| **Non-Modular (any doors)** | None | Single evap → auto-falls into LH slot |
| **Cassette 1 unit** | Left | Same as Modular 4ft |
| **Cassette 2 units** | Left (unit 1), Center (unit 2) | Unit 1 fully calculated; unit 2 limited ¹ |
| **Cassette 3 units** | Left, Center, Right | Same engine path as modular 3-module |
| **Freedom** | None | Same as Non-Modular; LH slot only |
| **Remote (any)** | Same as SC equivalent | Same as the SC version of that scenario |

> ¹ **Cassette multi-unit limitation:** The current calculation engine assumes one shared compressor and stops at the first one it finds. Units 2 and 3 are fully visible on the diagram with all their sensor ports, but multi-unit independent calculation is a future upgrade. Unit 1 is always fully calculated.

---

## How Port Names Differ Across All Scenarios (TXV Example)

The port name is always `inlet`. What changes is:
1. The unique `component_id` (auto-generated UUID)
2. The `circuit_label` property on the component

| Scenario | Mapping key | circuit_label | What it maps to |
|---|---|---|---|
| Modular 12ft — Left TXV | `TXV.txv_abc.inlet` | Left | CSV col for Left module liquid line temp |
| Modular 12ft — Center TXV | `TXV.txv_def.inlet` | Center | CSV col for Center module liquid line temp |
| Modular 12ft — Right TXV | `TXV.txv_ghi.inlet` | Right | CSV col for Right module liquid line temp |
| Non-Modular — single TXV | `TXV.txv_jkl.inlet` | None | CSV col for single liquid line temp → LH slot |
| Cassette unit 1 | `TXV.txv_mno.inlet` | Left | CSV col for unit 1 liquid line temp |
| Cassette unit 2 | `TXV.txv_pqr.inlet` | Center | CSV col for unit 2 liquid line temp |
| Cassette unit 3 | `TXV.txv_stu.inlet` | Right | CSV col for unit 3 liquid line temp |

Same logic applies to Evaporators, Merger Junctions, Hot Gas Bypass Valves, and Hot Gas Loops — they all carry the same `circuit_label` as the TXV in their module/unit.

---

## All Sensor Ports — What Exists and What It Measures

### Refrigerant Circuit (self-contained scenarios; Remote replaces comp+cond with open stubs)

| Component | Port | Measures |
|---|---|---|
| Compressor | `inlet` | Suction line temperature — State 2b |
| Compressor | `outlet` | Discharge temperature — State 3a |
| Compressor | `SP` | Suction pressure PSIG — drives T_sat low side |
| Compressor | `DP` | Discharge pressure PSIG — drives T_sat high side |
| Compressor | `RPM` | Compressor speed — drives mass flow calculation |
| Condenser | `inlet` | Hot gas entering condenser — State 3b |
| Condenser | `outlet` | Subcooled liquid leaving condenser — State 4a |
| Condenser | `water_in_temp` | *(Water Cooled only)* Cooling water inlet temp |
| Condenser | `water_out_temp` | *(Water Cooled only)* Cooling water outlet temp |
| Condenser | `water_flow_gpm` | *(Water Cooled only)* Water flow rate GPM |
| Filter Dryer | `inlet` / `outlet` | Liquid line temps before and after dryer |
| TXV *(per module/unit)* | `inlet` | Subcooled liquid entering TXV — State 4b |
| TXV *(per module/unit)* | `outlet` | Two-phase mixture leaving TXV — State 1 |
| TXV *(per module/unit)* | `bulb` | Sensing bulb temp — **absent for Cap Tube** |
| Evaporator *(per module/unit)* | `dist_inlet` | Refrigerant entering built-in distributor — State 1 |
| Evaporator *(per module/unit)* | `outlet_circuit_1` … `outlet_circuit_N` | Superheated gas leaving each of N circuits — State 2a; all averaged per module |

### Air Side (same structure across all scenarios; counts default to 2 per array)

| Component | Ports | Measures |
|---|---|---|
| AirSensorArray *(post-coil, per module/door)* | `sensor_1` … `sensor_N` | Air temp leaving evap coil |
| AirSensorArray *(primary curtain, per module/door)* | `sensor_1` … `sensor_N` | Air temp at discharge curtain |
| AirSensorArray *(secondary curtain, per module/door — dual only)* | `sensor_1` … `sensor_N` | Second curtain row |
| AirSensorArray *(return air — 1 per diagram, full width)* | `sensor_1` … `sensor_N` | Return air temp — bottom of case |
| ShelvingGrid *(per module/door column)* | `sensor_r{row}_top_c{col}` / `_bottom_c{col}` | Shelf temperature; col 0 = left end, col N = right end; shared dots at boundaries between adjacent grids |

---

## How Calculations Use All This

1. User switches to **Mapping Mode** → clicks a dot → clicks a CSV column → link stored as `"ComponentType.comp_id.port_name"` → CSV column name
2. Calculation engine finds **Left / Center / Right** TXVs and Evaporators by their `circuit_label` property — works for however many exist
3. If no labels exist (non-modular, freedom, cassette unit 1) → single evap + TXV auto-mapped to LH slot
4. All N circuit outlets per evaporator are averaged → single representative temperature per module
5. **CoolProp** computes enthalpy, entropy, density, saturation temp at each of the 8 state points
6. Derived values: superheat (4 locations), subcooling (2 locations), vapour quality after TXV, mass flow, cooling capacity, heat rejection, COP
7. Results table: 3 coil groups (LH/CTR/RH ×8 cols each), compressor in/out, condenser, 3 TXV groups, totals
8. P-h diagram: one cycle loop drawn per active module using state points 4b → 1 → 2b → 3b

---

## What Differs Between Scenarios — Summary

| What changes | Modular | Non-Modular | Cassette | Freedom | Remote |
|---|---|---|---|---|---|
| Compressor + Condenser | 1 shared | 1 shared | 1 per unit | 1 shared | **Replaced by 2 open pipe stubs** |
| Refrigerant loop count | 1 loop splits N ways | 1 loop, no split | N fully independent loops | 1 loop | Same as SC equivalent |
| circuit_label | Left/Center/Right | None | Left/Center/Right per unit | None | Same as SC |
| Fan / ShelvingGrid / AirArrays | 1 per module column | 1 per door column | **Follows underlying case, not unit count** | 1 column | Same as SC |
| Splitter + Collector junctions | Yes (if >1 module) | No | No | No | Same as SC |
| Calculation coverage | Full for all modules | LH slot only | LH only (future: all units) | LH only | Same as SC |

---

## Wizard Flow Summary

```
Pick Architecture → Modular / Non-Modular / Cassette / Freedom
     ↓
Sub-options:
  Modular  → Self-Contained or Remote; size (12/8/6/4ft); circuits per module
  Non-Mod  → Self-Contained or Remote; door count (1–5); total circuits
  Cassette → Unit count (1–3); circuits per unit
             Underlying case: Modular (size) or Non-Modular (door count)
  Freedom  → Sub-type: Non-Modular or Modular; circuits
     ↓
Condenser type (Air/Water) — hidden for Remote
Expansion device (TXV/Cap Tube)
Filter Dryer (Yes/No)
Defrost (None/Electric/Hot Gas/Reverse Cycle)
Discharge curtain (Single/Dual)
Shelf rows (3–7)
     ↓
Click "Generate"
     ↓
Template loaded → patches applied → fresh diagram on screen
Semantic state names auto-assigned to all ports
     ↓
User loads CSV → maps sensor dots → calculations and P-h diagram run
Air sensor counts adjusted by double-clicking each AirSensorArray
```

---

*Shelving and return air block are always generated — no option to disable.*
*Sensor Box ("Other Sensors") always included.*
*Air sensor counts: default 2 per array; editable via double-click on each array after generation.*
