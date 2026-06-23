# New Diagram Wizard — Implementation Plan

## Overview

Add a **"🆕 New"** toolbar button to the Diagram tab. When clicked, it opens a configuration wizard where the user selects their case type and options. The wizard loads a **pre-built JSON template** for that case type, then **patches** it for the user's specific selections (circuit count, condenser type, expansion device, optional components). The user gets a clean, topologically correct starting diagram — ready to move components around and map sensors.

---

## Core Strategy: Template Files + Patching

Previous attempts at algorithmic layout generation produced overlapping, unreadable diagrams. The solution is:

1. **Hand-build** reference diagrams in the app (one per case configuration variant)
2. **Save** each reference as a `.json` file in a `templates/` folder
3. When the wizard runs, **load** the matching template `.json`
4. **Patch** the template to match the user's specific choices (circuit count, condenser type, etc.)
5. **Assign new UUIDs** to all components/pipes so each generated diagram is independent

This guarantees clean layout every time because the layout was designed by a human.

---

## Case Type Variants (7 base templates to build by hand)

| # | Template File | Case Type | Modules/Units |
|---|---------------|-----------|---------------|
| 1 | `tmpl_modular_3module.json` | Modular (12ft) | 3 modules |
| 2 | `tmpl_modular_2module.json` | Modular (8ft/6ft) | 2 modules |
| 3 | `tmpl_modular_1module.json` | Modular (4ft) | 1 module |
| 4 | `tmpl_nonmodular_5door.json` | Non-Modular (max) | 5 doors (scaled down for fewer) |
| 5 | `tmpl_cassette_3unit.json` | Cassette (max) | 3 units (scaled down for fewer) |
| 6 | `tmpl_freedom_nonmodular.json` | Freedom Non-Modular | 1 condensing unit |
| 7 | `tmpl_freedom_modular_3module.json` | Freedom Modular | 3 modules, shared compressor+condenser |

**Remote variants** are NOT separate templates — the same template is used, with the compressor and condenser components deleted and replaced by `RemoteLineEndpoint` stubs.

**Template defaults:** Each template is built WITHOUT optional components (no filter dryer, no hot gas bypass). These are inserted by the patcher if the user checks them.

**Template circuit count default:** 6 circuits per module/evaporator. Patcher adds/removes circuit pipes for different counts.

---

## Template Folder Structure

```
HVAC_Dev/
  templates/
    tmpl_modular_3module.json
    tmpl_modular_2module.json
    tmpl_modular_1module.json
    tmpl_nonmodular_5door.json
    tmpl_cassette_3unit.json
    tmpl_freedom_nonmodular.json
    tmpl_freedom_modular_3module.json
```

Each `.json` file is a `diagramModel` dict (same structure as `data_manager.diagram_model`):
```json
{
  "components": { ... },
  "pipes": { ... },
  "sensor_roles": {},
  "custom_sensors": {},
  "sensor_boxes": {}
}
```

---

## What Each Template Includes (by default)

Each template is hand-built with:

**Refrigerant circuit (required):**
- Compressor + Condenser (Air Cooled, default)
- TXV (default) with SensorBulb
- Evaporator with `inlet_distributor='Yes'`, `circuits=6` (default)
- Merger Junction per module + Collector Junction (if multi-module)
- Splitter Junction (if multi-module)
- All refrigerant pipes with correct waypoints, fluid_state, pressure_side, circuit_label

**Peripheral (required):**
- 1 Fan per module/door
- 1 AirSensorArray (curtain_type='Discharge') per module/door
- 1 AirSensorArray (curtain_type='Primary') per module/door — single curtain by default
- 1 AirSensorArray (curtain_type='Return') spanning full width — 1 per diagram
- 1 ShelvingGrid per module/door column — `shelf_rows=5` default
- 1 SensorBox ("Other Sensors")

**NOT included in template (inserted by patcher if selected):**
- FilterDrier
- HotGasBypassValve + HotGasLoop
- Second discharge curtain (curtain_type='Secondary') for dual curtain

---

## Patching Rules (applied after template load)

### Step 0: Re-ID all components and pipes
Generate fresh UUIDs for all comp_ids and pipe_ids so each generated diagram is independent. Update all pipe `start_component_id`/`end_component_id` references to match new IDs. Preserve `sensor_roles = {}`.

### Step 1: Circuit count patching
If user picks N circuits ≠ template default (6):
1. Find each Evaporator component → update `properties['circuits'] = N`
2. For pipes connecting to `inlet_circuit_j` or `outlet_circuit_j` ports:
   - Remove pipes where j > N
   - Add pipes for j = (template_default+1) to N (using same Distributor→Evap and Evap→Merger pattern, positioned with small y-offsets from the last existing circuit pipe)

### Step 2: Condenser type patching
If user picks 'Water Cooled':
- Find Condenser component(s) → set `properties['condenser_type'] = 'Water Cooled'`
- No pipe changes needed (water ports are sensor-only, no refrigerant pipes to water)

### Step 3: Expansion device patching
If user picks 'Cap Tube':
- Find TXV component(s) → set `properties['expansion_device_type'] = 'Cap Tube'`
- Find SensorBulb component(s) connected to those TXVs → delete them + their pipes

### Step 4: Remote case patching
If Remote selected:
- Delete Compressor component(s) and all their pipes
- Delete Condenser component(s) and all their pipes
- Insert `RemoteLineEndpoint("Liquid Line In")` — connected at liquid line entry point (where condenser outlet pipe ended)
- Insert `RemoteLineEndpoint("Suction Line Out")` — connected at suction line return point (where compressor inlet pipe started)
- Insert positions: offset slightly from where the deleted components were

### Step 5: Filter Dryer insertion (if selected)
- Find the pipe connecting Condenser.outlet → Splitter/TXV.inlet (the liquid line)
- Delete that pipe
- Insert FilterDrier component midway along that pipe's path
- Add two new pipes: Condenser.outlet → FilterDrier.inlet, FilterDrier.outlet → Splitter/TXV.inlet

### Step 6: Hot Gas Bypass insertion (if selected, non-Electric/non-Reverse-cycle defrost)
- For each module/evaporator, insert:
  - `HotGasBypassValve` component (positioned between the high-pressure line and the evap suction)
  - `HotGasLoop` component (positioned at the evap suction return)
  - Pipe: tee from high-pressure liquid line → HotGasBypassValve.inlet
  - Pipe: HotGasBypassValve.outlet → HotGasLoop.inlet
  - Pipe: HotGasLoop.outlet → suction line (merger junction inlet)

### Step 7: Dual curtain insertion (if selected)
- For each module/door, insert a second `AirSensorArray` (curtain_type='Secondary') positioned adjacent to the Primary curtain (offset slightly)

### Step 8: Shelf row patching
If user picks shelf_rows ≠ 5 (template default):
- Find each ShelvingGrid component → set `properties['shelf_rows'] = N`
- No pipe changes needed (ShelvingGrid has no refrigerant pipes)

### Step 9: Curtain sensor count patching
- Find all AirSensorArray components → update their `sensor_count` property

### Step 10: Module/door/unit scaling for Non-Modular and Cassette
**Non-Modular (template has 5 doors, user picks fewer):**
- Identify which door's components to remove (rightmost doors removed first)
- Delete: Fan, AirSensorArray (Discharge + Primary), ShelvingGrid for each removed door
- Adjust Return air AirSensorArray `block_width` proportionally

**Cassette (template has 3 units, user picks fewer):**
- Delete all components belonging to removed units (each unit is a fully independent loop)
- Identify unit groups by their `circuit_label` property

---

## Defrost Types

Defrost type is informational for the wizard — affects which optional components are relevant:

| Defrost Type | Extra Components |
|--------------|-----------------|
| None | No defrost components |
| Electric | No extra refrigerant components (electric heaters are not modelled as refrigerant components) |
| Hot Gas | HotGasBypassValve + HotGasLoop (patched in per module/evap) |
| Reverse Cycle | No extra refrigerant components (reverse cycle = reversing valve, deferred for future) |

The wizard shows/hides the Hot Gas Bypass checkbox based on defrost selection:
- If defrost = 'Hot Gas' → Hot Gas Bypass checkbox auto-checked and disabled
- If defrost = 'Electric' or 'Reverse Cycle' or 'None' → Hot Gas Bypass checkbox unchecked and hidden

---

## Files to Create / Modify

| File | Action | Purpose |
|------|--------|---------|
| `templates/` (folder) | **Create** | Holds 7 hand-built template `.json` files |
| `new_diagram_wizard.py` | **Create** | `NewDiagramWizard` QDialog |
| `diagram_template_loader.py` | **Create** | Template loading + all patching logic |
| `diagram_widget.py` | Modify | Add "New" toolbar button + handler |
| `component_schemas.py` | Modify | Add `expansion_device_type` to TXV; add `RemoteLineEndpoint` schema |
| `diagram_components.py` | Modify | TXVComponentItem: suppress bulb port for Cap Tube; add `RemoteLineEndpointItem` |

---

## Component Schema Changes

### TXV — add `expansion_device_type` property
```python
"expansion_device_type": {
    "type": "enum",
    "default": "TXV",
    "options": ["TXV", "Cap Tube"]
}
```
In `TXVComponentItem.rebuild_ports()`: skip creating `bulb` port when `expansion_device_type == 'Cap Tube'`. Update label text to show "Cap Tube".

### New: `RemoteLineEndpoint` schema
```python
"RemoteLineEndpoint": {
    "properties": {
        "label": {"type": "string", "default": "Remote Connection"}
    },
    "ports": [
        {"name": "connection", "type": "in", "fluid_state": "any",
         "pressure_side": "any", "position": [0.5, 0.5]}
    ],
    "zones": []
}
```
`RemoteLineEndpointItem` class: dashed-border rectangle, label text centred, no fill. Added to `build_scene_from_model()` factory.

---

## `diagram_template_loader.py`

```python
def load_template(case_type: str, config: dict) -> dict:
    """Load the correct base template and apply all patches. Returns diagram_model dict."""

def _get_template_path(case_type: str, config: dict) -> str:
    """Map case_type + config to a template file path."""

def _reissue_ids(model: dict) -> tuple[dict, dict]:
    """Generate fresh UUIDs for all components and pipes. Returns (new_model, id_map)."""

def _patch_circuit_count(model, evap_ids, merger_ids, distributor_ids, circuits: int): ...
def _patch_condenser_type(model, condenser_ids, condenser_type: str): ...
def _patch_expansion_device(model, txv_ids, bulb_ids, expansion_type: str): ...
def _patch_remote(model, compressor_ids, condenser_ids, liquid_line_pipe_id, suction_pipe_id): ...
def _insert_filter_dryer(model, liquid_line_pipe_id): ...
def _insert_hot_gas_bypass(model, per_module_info: list): ...
def _insert_dual_curtain(model, primary_curtain_ids: list): ...
def _patch_shelf_rows(model, shelf_ids, shelf_rows: int): ...
def _patch_curtain_sensors(model, curtain_ids, sensor_count: int): ...
def _scale_nonmodular_doors(model, template_doors: int, target_doors: int): ...
def _scale_cassette_units(model, template_units: int, target_units: int): ...
```

To support patching, templates must include **metadata tags** in component properties to identify roles:
```json
"properties": {
    "template_role": "evaporator_module_1",    // e.g. evaporator, compressor, condenser, txv_module_2
    ...
}
```
The loader uses `template_role` to find which components to patch/delete/modify. These tags are stripped from the final model before loading into the app.

---

## `new_diagram_wizard.py` — Dialog Layout

```
┌────────────────────────────────────────────────────────┐
│  New Diagram Configuration                             │
├────────────────────────────────────────────────────────┤
│  CASE ARCHITECTURE                                     │
│   ○ Modular    ○ Non-Modular    ○ Cassette  ○ Freedom  │
│                                                        │
│  [Modular group]                                       │
│   Location:  ● Self-Contained  ○ Remote                │
│   Case size: ○ 12ft  ○ 8ft  ○ 6ft  ○ 4ft             │
│   Circuits per module: [6  ▲▼]                        │
│                                                        │
│  [Non-Modular group]                                   │
│   Location:  ● Self-Contained  ○ Remote                │
│   Door count:  ○1  ○2  ○3  ○4  ○5                    │
│   Total circuits: [6  ▲▼]                             │
│                                                        │
│  [Cassette group]                                      │
│   Number of units: ○1  ○2  ○3                         │
│   Circuits per unit: [6  ▲▼]                          │
│                                                        │
│  [Freedom group]                                       │
│   Sub-type: ● Non-Modular  ○ Modular                  │
│   Circuits: [6  ▲▼]                                   │
│                                                        │
│  CONDENSER  (hidden for Remote cases)                  │
│   ● Air Cooled   ○ Water Cooled                       │
│                                                        │
│  EXPANSION DEVICE                                      │
│   ● TXV    ○ Cap Tube                                 │
│                                                        │
│  DEFROST                                               │
│   ● None  ○ Electric  ○ Hot Gas  ○ Reverse Cycle      │
│   (Hot Gas Bypass components auto-added when Hot Gas)  │
│                                                        │
│  OPTIONAL COMPONENTS                                   │
│   ☑ Filter Dryer                                      │
│                                                        │
│  AIR MEASUREMENT                                       │
│   Discharge curtain: ● Single   ○ Dual                │
│   Sensors per curtain array: [6  ▲▼]                  │
│   ☑ Include return air block                          │
│                                                        │
│  SHELVING                                              │
│   ☑ Include shelving grid                             │
│   Shelf rows per column: [5  ▲▼]  (3–7)              │
│                                                        │
│                        [Cancel]  [Generate →]         │
└────────────────────────────────────────────────────────┘
```

Sections shown/hidden via architecture radio button connection to group box visibility. Condenser group hidden when Remote selected. Hot Gas Bypass auto-managed by defrost selection.

---

## `diagram_widget.py` Changes

### `populate_toolbar()` — add before Components button:
```python
new_btn = QPushButton("🆕 New")
new_btn.setToolTip("Create a new diagram from a template")
new_btn.clicked.connect(self.on_new_diagram_clicked)
self.toolbar.addWidget(new_btn)
self.toolbar.addSeparator()
```

### `on_new_diagram_clicked()`:
```python
def on_new_diagram_clicked(self):
    from new_diagram_wizard import NewDiagramWizard
    from diagram_template_loader import load_template

    wizard = NewDiagramWizard(parent=self)
    if wizard.exec() != QDialog.DialogCode.Accepted:
        return

    config = wizard.get_config()

    if self.data_manager.diagram_model.get('components'):
        reply = QMessageBox.question(
            self, "Replace Diagram",
            "This will replace the current diagram. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

    new_model = load_template(config['case_type'], config)
    self.data_manager.diagram_model = new_model
    self.data_manager.diagram_model_changed.emit()
    QTimer.singleShot(300, self.zoom_to_fit)
```

---

## Key Existing Code Reused (no changes)

| Symbol | File:Line | Notes |
|--------|-----------|-------|
| `build_scene_from_model()` | `diagram_widget.py:574` | Reused via `diagram_model_changed` signal |
| `zoom_to_fit()` | `diagram_widget.py` | Called after template load |
| `ShelvingGridComponentItem.rebuild_ports()` | `diagram_components.py:2379` | Already generates shared-junction sensor dots correctly |
| Condenser `condenser_type` property | `component_schemas.py` | Already supports 'Air Cooled' / 'Water Cooled' |
| Evap `inlet_distributor` property | `component_schemas.py` | Already supports 'Yes' / 'No' |
| `AirSensorArrayComponentItem` | `diagram_components.py` | Reused with curtain_type property |
| `HotGasBypassItem`, `HotGasLoopItem` | `diagram_components.py` | Reused directly |
| `SensorBulbComponentItem` | `diagram_components.py` | Reused directly |

---

## Implementation Order

### Phase A — Schema + Component Changes (prerequisites, no UI impact)
1. Add `expansion_device_type` to TXV schema (`component_schemas.py`)
2. Suppress TXV bulb port when Cap Tube (`diagram_components.py`)
3. Add `RemoteLineEndpoint` schema (`component_schemas.py`)
4. Add `RemoteLineEndpointItem` class + factory entry (`diagram_components.py`, `diagram_widget.py`)

### Phase B — Template Building (human work, done in the running app)
1. Open the app
2. Hand-build each of the 7 reference diagrams (see table above)
   - Build with: Air Cooled condenser, TXV, 6 circuits, NO optional components, single curtain, 5 shelf rows
   - Add `template_role` property to each component for patching identification
3. Save each diagram as `templates/tmpl_XXX.json` (save `diagramModel` only, not CSV data)

### Phase C — Template Loader (`diagram_template_loader.py`)
1. Implement `_get_template_path()`
2. Implement `_reissue_ids()`
3. Implement each patch function in order (circuit count → condenser type → expansion device → remote → filter dryer → hot gas bypass → dual curtain → shelf rows → curtain sensors → scaling)
4. Implement `load_template()` dispatcher

### Phase D — Wizard UI (`new_diagram_wizard.py`)
1. Build the dialog with all sections
2. Implement show/hide logic for architecture sub-sections
3. Implement `get_config()` method

### Phase E — Wire into `diagram_widget.py`
1. Add toolbar button
2. Add `on_new_diagram_clicked()` handler

---

---

## Making the Code Understand the Refrigeration Cycle

### The Problem

The app currently has two separate systems that don't talk to each other:

1. **The Diagram** — stores topology (what connects to what) and visual layout, with `sensor_roles` mapping ports → CSV columns
2. **The Calculation Engine** — uses hardcoded internal names (`T_1a-lh`, `T_2b`, `P_suc`) to find sensor data

The connection between them is done manually by the user mapping sensors in the diagram. But the calculation engine does not use the diagram's pipe network to understand the circuit — it just queries `sensor_roles` with fixed lookup keys. If the diagram changes (e.g. you add a third evaporator), the calculation engine doesn't automatically know.

**The goal:** When a diagram is generated by the wizard, the code should automatically know:
- Which CSV sensor (once mapped) measures compressor discharge temperature
- Which sensors are on the low-pressure side vs high-pressure side
- Which evaporator belongs to which module/circuit
- Whether a reading violates the laws of thermodynamics for this specific circuit

### The Semantic Layer: `state_name` on Ports

The fix is to add a **`state_name`** field to each port in the `sensor_roles` mapping. This is a short, machine-readable identifier for the thermodynamic role of that measurement point.

#### How it works

When the wizard generates a diagram, it assigns a `state_name` alongside the port. These are stored in a new `diagram_model['port_semantics']` dict:

```python
diagram_model['port_semantics'] = {
    # role_key → {state_name, description, module_label, expected_fluid_state, expected_pressure_side}
    "Compressor.comp_abc.inlet":   {"state_name": "comp_suction",        "module": None, "fluid": "gas",       "pressure": "low"},
    "Compressor.comp_abc.outlet":  {"state_name": "comp_discharge",      "module": None, "fluid": "gas",       "pressure": "high"},
    "Condenser.cond_abc.inlet":    {"state_name": "cond_inlet",          "module": None, "fluid": "gas",       "pressure": "high"},
    "Condenser.cond_abc.outlet":   {"state_name": "cond_outlet",         "module": None, "fluid": "liquid",    "pressure": "high"},
    "TXV.txv_abc.inlet":           {"state_name": "txv_inlet",           "module": "Left", "fluid": "liquid",  "pressure": "high"},
    "TXV.txv_abc.outlet":          {"state_name": "txv_outlet",          "module": "Left", "fluid": "two-phase","pressure": "low"},
    "TXV.txv_abc.bulb":            {"state_name": "txv_bulb",            "module": "Left", "fluid": "gas",     "pressure": "low"},
    "Evaporator.evap_abc.dist_inlet": {"state_name": "evap_inlet",       "module": "Left", "fluid": "two-phase","pressure": "low"},
    "Evaporator.evap_abc.outlet_circuit_1": {"state_name": "evap_outlet","module": "Left", "circuit": 1,       "fluid": "gas", "pressure": "low"},
    "FilterDrier.fd_abc.inlet":    {"state_name": "filter_drier_inlet",  "module": None},
    "FilterDrier.fd_abc.outlet":   {"state_name": "filter_drier_outlet", "module": None},
    ...
}
```

#### Standard state_name vocabulary

```python
# Shared / system-level
"comp_suction"          # Compressor inlet (suction line)
"comp_discharge"        # Compressor outlet (discharge line)
"cond_inlet"            # Condenser refrigerant inlet
"cond_outlet"           # Condenser refrigerant outlet (subcooled liquid)
"filter_drier_inlet"    # Filter drier inlet
"filter_drier_outlet"   # Filter drier outlet

# Per-module (module = 'Left' | 'Center' | 'Right')
"txv_inlet"             # TXV high-side inlet (subcooled liquid)
"txv_outlet"            # TXV low-side outlet (two-phase)
"txv_bulb"              # TXV sensing bulb (measures suction superheat)
"evap_inlet"            # Evaporator inlet (after distributor)
"evap_outlet"           # Evaporator outlet (superheated gas) — per circuit
"evap_suction"          # Suction line from evaporator to compressor

# Sensor/measurement points
"comp_rpm"              # Compressor speed
"cond_water_in"         # Condenser water inlet temperature
"cond_water_out"        # Condenser water outlet temperature
"cond_water_flow"       # Condenser water flow rate (GPM)
"ambient_drybulb"       # Ambient dry bulb temperature
"ambient_wetbulb"       # Ambient wet bulb temperature
"defrost_status"        # Defrost on/off signal
```

#### What the wizard generates automatically

When `load_template()` builds a new diagram, it calls `_assign_port_semantics(model)` which:
1. Walks every component in the model
2. For each component type and port, assigns the correct `state_name` based on:
   - Component type (Compressor, Condenser, TXV, Evaporator, etc.)
   - Port name (inlet, outlet, bulb, dist_inlet, outlet_circuit_N)
   - Component's `circuit_label` property (Left/Center/Right → `module` field)
3. Writes results into `diagram_model['port_semantics']`

This is pure logic — no user input needed.

### What This Enables

#### 1. Calculation Engine Uses Topology Instead of Hardcoded Names

**Today:** Calculation engine looks for `T_1a-lh` as a hardcoded internal name, resolved via a fixed lookup table in `calculation_orchestrator.py`.

**With semantic layer:** `port_resolver.py` gains a new function:
```python
def resolve_sensor_by_state(diagram_model, state_name, module=None, circuit=None):
    """Find the CSV column name for a given thermodynamic role.
    E.g. state_name='txv_inlet', module='Left' → 'Left TXV Inlet Temp (col 23)'
    """
```
The calculation engine calls this instead of hardcoded lookups. If the diagram has no Left module, it gets `None` and gracefully skips that circuit's calculations. If a new evaporator is added with a new module label, calculations automatically include it.

#### 2. Thermodynamic Validation

Because `port_semantics` stores `expected_fluid_state` and `expected_pressure_side` for each port, a new `validate_sensor_readings()` function can check:

| Rule | How it's enforced |
|------|------------------|
| Discharge temp > Suction temp | `comp_discharge` value > `comp_suction` value |
| Condenser outlet subcooled | `cond_outlet` value < saturation temp at discharge pressure |
| Evap outlet superheated | `evap_outlet` value > saturation temp at suction pressure |
| TXV bulb > evap outlet | `txv_bulb` value ≈ `evap_outlet` value (bulb measures the same point) |
| High side > Low side pressure | `P_disch` > `P_suc` |

Violations are flagged in the diagram with colored indicators (red dot on the port that's reading out-of-thermodynamic-range). This is separate from the existing sensor range system (which is user-defined min/max). Thermodynamic validation is physics-based and automatic.

#### 3. P-h Diagram is Automatically Wired

`ph_data_builder.py` currently hardcodes which sensor is "state point 1" (compressor inlet), "state point 2" (compressor outlet), etc. With the semantic layer:
```python
# Instead of:
t_comp_in = sensor_map.get('T_2b')

# It becomes:
t_comp_in = resolve_sensor_by_state(model, 'comp_suction')
```
The P-h diagram automatically uses the right sensors regardless of what the user named them in the CSV.

#### 4. Auto-Suggest Sensor Mappings

When a CSV is loaded, the `state_name` enables intelligent matching:
- Port with `state_name='comp_suction'` → search CSV columns for keywords: "suction", "comp in", "inlet", "return gas"
- Port with `state_name='txv_bulb'` + `module='Left'` → search for: "left", "txv", "bulb", "sensing"
- Port with `state_name='cond_water_out'` → search for: "water", "out", "exit"

This fuzzy-match suggestion is shown to the user in the mapping dialog (not auto-applied) for confirmation. This addresses your comment about future automation of sensor naming.

### Implementation Plan for Semantic Layer

This is a **new section added to the wizard plan**, not a replacement for any existing functionality. It adds one new data structure and one new function.

#### New: `diagram_model['port_semantics']` dict
- Stored in session JSON alongside `sensor_roles`
- Auto-populated when wizard generates a diagram
- Can also be computed on-demand by traversing the diagram model

#### New file: `circuit_semantics.py`
```python
def assign_port_semantics(model: dict) -> dict:
    """Walk all components in model, assign state_name to every port.
    Returns updated model with model['port_semantics'] populated."""

def resolve_sensor_by_state(model: dict, state_name: str,
                             module: str = None, circuit: int = None) -> str | None:
    """Find CSV column name for a thermodynamic state point.
    Returns None if no sensor is mapped to that state."""

def validate_thermodynamic_consistency(model: dict, csv_data) -> list[dict]:
    """Check sensor readings against thermodynamic rules.
    Returns list of violations: [{port, rule, expected, actual}]"""

def suggest_sensor_mappings(model: dict, csv_columns: list[str]) -> dict:
    """For each unmapped port, suggest likely CSV column matches based on state_name keywords.
    Returns {role_key: [candidate_column_names_ranked]}"""
```

#### Integration points
- `diagram_template_loader.py`: Call `assign_port_semantics(model)` at end of `load_template()`
- `data_manager.py`: Call `assign_port_semantics()` when loading a session that lacks `port_semantics` (migration)
- `calculation_orchestrator.py`: Optionally add `resolve_sensor_by_state()` as an alternative lookup path
- `diagram_widget.py`: Show thermodynamic violation indicators in Analysis mode

---

## Verification

1. `python app.py` → Diagram tab → click **"🆕 New"**
2. **Modular, 12ft, Self-Contained, Air Cooled, TXV, Filter Dryer, Hot Gas defrost, single curtain (6 sensors), 5 shelf rows:**
   - Expected: 3-module layout matching hand-built template; FilterDrier and HotGasBypassValves + HotGasLoops inserted
   - Verify no overlapping components or pipes
3. **Modular, 8ft, Remote, Cap Tube, no filter dryer, electric defrost:**
   - Expected: 2-module layout; no compressor/condenser; "Liquid Line In" + "Suction Line Out" stubs
   - TXV shows "Cap Tube" label; no bulb dots in Mapping mode; no hot gas bypass components
4. **Non-Modular, 3-door, Self-Contained, Water Cooled, TXV, no filter dryer, 4 circuits:**
   - Expected: 5-door template scaled to 3 doors; condenser has water sensor ports; 4 circuit pipes per evap
5. **Cassette, 2 units, Air Cooled, TXV, filter dryer, hot gas:**
   - Expected: 3-unit template scaled to 2 units; each unit independent; filter dryers inserted
6. **Freedom, Non-Modular, Water Cooled, Cap Tube, reverse cycle defrost:**
   - Expected: Freedom Non-Modular template; water-cooled condenser; no bulb port; no hot gas components
7. Switch to **Mapping mode** → all sensor dots on all ports
8. Save session → reload → diagram fully reconstructs from JSON
