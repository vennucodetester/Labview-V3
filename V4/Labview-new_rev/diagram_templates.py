"""
diagram_templates.py

Pure-Python module (no Qt, no signals) that builds a complete diagram_model
dict from a configuration dict provided by NewDiagramWizard.

Public API
----------
build_diagram_from_config(config) -> dict
    Dispatches to the correct case-type builder and returns a ready-to-use
    diagram_model that can be assigned straight to data_manager.diagram_model.

All builder functions write directly to the model dict and return it.
No signals are fired here — the caller fires diagram_model_changed once.
"""

import uuid
from graphviz_layout import apply_graphviz_layout

# ---------------------------------------------------------------------------
#  Layout constants
# ---------------------------------------------------------------------------
MODULE_SPACING_X   = 460    # horizontal px between module/door columns
EVAP_Y             = 500    # y-position of evaporator row (from top)
COMP_Y             = 60     # y-position of shared compressor
COND_Y             = 60     # y-position of shared condenser
SPLITTER_Y         = 200    # y-position of liquid-line splitter
COLLECTOR_Y        = 780    # y-position of suction-line collector
TXV_Y              = 340    # y-position of TXV
MERGER_Y           = 700    # y-position of per-module merger junction
HOT_GAS_VALVE_Y    = 340    # y-position of hot gas bypass valve (same row as TXV)
HOT_GAS_LOOP_Y     = 620    # y-position of hot gas loop
FILTER_DRIER_Y     = COMP_Y # y-position of filter drier (same row as comp/cond)
FAN_Y              = 1020   # y-position of fan (below evap)
AIR_ARRAY_POST_Y   = 1120   # y-position of post-coil air array
AIR_ARRAY_PRIM_Y   = 1200   # y-position of primary curtain
AIR_ARRAY_SEC_Y    = 1290   # y-position of secondary curtain (dual only)
RETURN_AIR_Y       = 1420   # y-position of return air block
SHELVING_Y         = 1520   # y-position of shelving grid
SENSOR_BOX_X       = 50
SENSOR_BOX_Y       = 1700
REMOTE_LIQUID_X    = 50     # x for "Liquid Line In" remote stub (left side)
REMOTE_SUCTION_X   = 50     # x for "Suction Line Out" stub (right side — set per case)
LEFT_OFFSET_X      = 200    # x of leftmost module/door column

CIRCUIT_LABELS = ['Left', 'Center', 'Right']

MODULE_COUNT = {
    '12 ft': 3,
    '8 ft':  2,
    '6 ft':  2,
    '4 ft':  1,
}

# Default component sizes (w, h) used when templates create components
COMP_SIZE   = {'width': 120, 'height': 60}
COND_SIZE   = {'width': 160, 'height': 60}
FD_SIZE     = {'width': 80,  'height': 40}
TXV_SIZE    = {'width': 50,  'height': 80}
EVAP_SIZE   = {'width': 140, 'height': 120}
MERGER_SIZE = {'width': 20,  'height': 60}
SPLIT_SIZE  = {'width': 20,  'height': 60}
JUNC_SIZE   = {'width': 20,  'height': 60}
HGB_SIZE    = {'width': 60,  'height': 50}
HGL_SIZE    = {'width': 100, 'height': 50}
FAN_SIZE    = {'width': 80,  'height': 50}
AIR_ARRAY_SIZE  = {'width': 300, 'height': 30}
REM_SIZE    = {'width': 140, 'height': 60}
SENS_BULB_SIZE  = {'width': 40,  'height': 40}


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _make_id(prefix: str) -> str:
    """Generate a unique component/pipe id with a short hex suffix."""
    return f"{prefix}_{uuid.uuid4().hex[:6]}"


def _empty_model() -> dict:
    return {
        'components':     {},
        'pipes':          {},
        'sensor_roles':   {},
        'custom_sensors': {},
        'sensor_boxes':   {},
        'port_semantics': {},
    }


def _add_component(model: dict, comp_type: str, x: float, y: float,
                   props: dict = None, size: dict = None,
                   rotation: float = 0) -> str:
    """Add a component to the model and return its generated id."""
    comp_id = _make_id(comp_type.lower()[:8])
    model['components'][comp_id] = {
        'type':       comp_type,
        'position':   [x, y],
        'properties': props or {},
        'size':       size or {'width': 100, 'height': 60},
        'rotation':   rotation,
    }
    return comp_id


def _add_pipe(model: dict,
              start_id: str, start_port: str,
              end_id: str,   end_port: str,
              fluid: str  = 'any',
              pressure: str = 'any',
              label: str  = 'None',
              waypoints: list = None) -> str:
    """Add a pipe to the model and return its generated id."""
    pipe_id = _make_id('pipe')
    model['pipes'][pipe_id] = {
        'start_component_id': start_id,
        'start_port':         start_port,
        'end_component_id':   end_id,
        'end_port':           end_port,
        'fluid_state':        fluid,
        'pressure_side':      pressure,
        'circuit_label':      label,
        'waypoints':          waypoints or [],
    }
    return pipe_id


def _add_sensor_box(model: dict, x: float, y: float) -> str:
    """Add an empty 'Other Sensors' sensor box."""
    box_id = _make_id('sensorbox')
    model['sensor_boxes'][box_id] = {
        'title':    'Other Sensors',
        'position': [x, y],
        'sensors':  [],
    }
    return box_id


# ---------------------------------------------------------------------------
#  Shared refrigerant-circuit sub-builders
# ---------------------------------------------------------------------------

def _build_shared_head_end(model: dict, config: dict, x_comp: float, x_cond: float
                           ) -> dict:
    """Add Compressor + Condenser (shared) and optionally a FilterDrier.

    Returns a dict of created ids: comp_id, cond_id, fd_id (or None).
    The final component's outlet is at 'liquid_exit_id' / 'liquid_exit_port'
    ready to connect to the next element (Splitter or first TXV).
    """
    condenser_type = config.get('condenser_type', 'Air Cooled')

    # Compressor
    comp_id = _add_component(model, 'Compressor', x_comp, COMP_Y,
                              props={'circuit_label': 'None'},
                              size=COMP_SIZE)

    # Condenser
    cond_id = _add_component(model, 'Condenser', x_cond, COND_Y,
                              props={'condenser_type': condenser_type,
                                     'circuit_label': 'None'},
                              size=COND_SIZE)

    # Comp → Cond
    _add_pipe(model, comp_id, 'outlet', cond_id, 'inlet',
              fluid='gas', pressure='high', label='None')

    # Optional Filter Drier
    fd_id = None
    fd_x  = x_cond + COND_SIZE['width'] + 60
    if config.get('include_filter_dryer', False):
        fd_id = _add_component(model, 'FilterDrier', fd_x, FILTER_DRIER_Y,
                               props={'circuit_label': 'None'},
                               size=FD_SIZE)
        _add_pipe(model, cond_id, 'outlet', fd_id, 'inlet',
                  fluid='liquid', pressure='high', label='None')

    liquid_exit_id   = fd_id if fd_id else cond_id
    liquid_exit_port = 'outlet'

    # Auto-map shared head-end sensors
    model['sensor_roles']['T_2a'] = f"Compressor.{comp_id}.inlet"
    model['sensor_roles']['P_suc'] = f"Compressor.{comp_id}.inlet"
    model['sensor_roles']['T_3a'] = f"Compressor.{comp_id}.outlet"
    model['sensor_roles']['P_dis'] = f"Compressor.{comp_id}.outlet"

    return {
        'comp_id':          comp_id,
        'cond_id':          cond_id,
        'fd_id':            fd_id,
        'liquid_exit_id':   liquid_exit_id,
        'liquid_exit_port': liquid_exit_port,
        'fd_x':             fd_x,
    }


def _build_remote_head_end(model: dict, config: dict, x_start: float) -> dict:
    """Add two RemoteLineEndpoint stubs for Remote cases.

    Returns similar dict to _build_shared_head_end but with stub ids instead
    of comp/cond.  The suction stub id is stored separately so the caller can
    connect the collector's outlet to it.
    """
    liq_stub_id = _add_component(model, 'RemoteLineEndpoint',
                                  REMOTE_LIQUID_X, COMP_Y,
                                  props={'label': 'Liquid Line In'},
                                  size=REM_SIZE)

    fd_id = None
    fd_x  = REMOTE_LIQUID_X + REM_SIZE['width'] + 60
    if config.get('include_filter_dryer', False):
        fd_id = _add_component(model, 'FilterDrier', fd_x, FILTER_DRIER_Y,
                               props={'circuit_label': 'None'},
                               size=FD_SIZE)
        _add_pipe(model, liq_stub_id, 'connection', fd_id, 'inlet',
                  fluid='liquid', pressure='high', label='None')

    liquid_exit_id   = fd_id if fd_id else liq_stub_id
    liquid_exit_port = 'outlet' if fd_id else 'connection'

    return {
        'comp_id':          None,
        'cond_id':          None,
        'liq_stub_id':      liq_stub_id,
        'fd_id':            fd_id,
        'liquid_exit_id':   liquid_exit_id,
        'liquid_exit_port': liquid_exit_port,
    }


def _build_module_refrigerant_loop(model: dict, config: dict,
                                   module_x: float, circuit_label: str,
                                   liquid_in_id: str, liquid_in_port: str,
                                   suction_out_id: str, suction_out_port: str,
                                   liquid_waypoints: list = None,
                                   suction_waypoints: list = None,
                                   ) -> dict:
    """Build the per-module refrigerant components: TXV → Evap → Merger.

    Connects liquid_in → TXV → Evap → Merger → suction_out.
    Returns ids of key components.
    """
    expansion_type   = config.get('expansion_type', 'TXV')
    circuits         = config.get('circuits_per_module', 6)
    include_hot_gas  = config.get('include_hot_gas_bypass', False)

    # TXV / Cap Tube
    txv_id = _add_component(model, 'TXV', module_x, TXV_Y,
                             props={'expansion_device_type': expansion_type,
                                    'circuit_label': circuit_label,
                                    'circuits': circuits},
                             size=TXV_SIZE)
    _add_pipe(model, liquid_in_id, liquid_in_port, txv_id, 'inlet',
              fluid='liquid', pressure='high', label=circuit_label,
              waypoints=liquid_waypoints)

    # SensorBulb for TXV (skip for Cap Tube)
    bulb_id = None
    if expansion_type == 'TXV':
        bulb_x = module_x + max(100, circuits * 22 + 20) + 20
        bulb_id = _add_component(model, 'SensorBulb',
                                  bulb_x, TXV_Y,
                                  props={'circuit_label': circuit_label},
                                  size=SENS_BULB_SIZE)
        # Route bulb connection cleanly under the evaporator
        under_y = EVAP_Y + 120 + 20
        _add_pipe(model, bulb_id, 'connection', txv_id, 'bulb',
                  fluid='gas', pressure='low', label=circuit_label,
                  waypoints=[
                      [bulb_x + SENS_BULB_SIZE['width']/2, TXV_Y + SENS_BULB_SIZE['height']],
                      [bulb_x + SENS_BULB_SIZE['width']/2, under_y],
                      [module_x + TXV_SIZE['width']/2, under_y],
                      [module_x + TXV_SIZE['width']/2, TXV_Y + TXV_SIZE['height']]
                  ])

    # Evaporator
    evap_id = _add_component(model, 'Evaporator', module_x, EVAP_Y,
                              props={'circuits': circuits,
                                     'port_spacing': 20,
                                     'inlet_distributor': 'Yes',
                                     'outlet_distributor': 'No',
                                     'circuit_label': circuit_label,
                                     'fan_sensor_count': 4,
                                     'air_flow_direction': 'Bottom to Top'},
                              size={'width': max(100, circuits * 22 + 20),
                                    'height': 120})

    # TXV → Evap (connects to dist_inlet when inlet_distributor=Yes)
    _add_pipe(model, txv_id, 'outlet', evap_id, 'dist_inlet',
              fluid='two-phase', pressure='low', label=circuit_label)

    # Auto-map evap sensors
    abbrev = {'Left': 'lh', 'Center': 'ctr', 'Right': 'rh'}.get(circuit_label, 'lh')
    if circuit_label != 'None':
        model['sensor_roles'][f'T_1a-{abbrev}'] = f"Evaporator.{evap_id}.dist_inlet"
        model['sensor_roles'][f'T_1b-{abbrev}'] = f"Evaporator.{evap_id}.outlet_circuit_1"

    # Merger junction: N circuit outlets → 1 suction outlet
    merger_id = _add_component(model, 'Junction',
                                module_x + 180, MERGER_Y,
                                props={'inlet_count': circuits,
                                       'outlet_count': 1,
                                       'port_spacing': 20,
                                       'circuit_label': circuit_label},
                                size={'width': 20,
                                      'height': max(40, circuits * 20 + 20)})

    # Evap outlets → Merger inlets
    for i in range(1, circuits + 1):
        _add_pipe(model, evap_id, f'outlet_circuit_{i}',
                  merger_id, f'inlet_{i}',
                  fluid='gas', pressure='low', label=circuit_label)

    # Hot Gas Bypass (optional)
    hgv_id = None
    hgl_id = None
    if include_hot_gas:
        hgv_id = _add_component(model, 'HotGasBypassValve',
                                  module_x + 80, HOT_GAS_VALVE_Y,
                                  props={'circuit_label': circuit_label},
                                  size=HGB_SIZE)
        hgl_id = _add_component(model, 'HotGasLoop',
                                  module_x + 80, HOT_GAS_LOOP_Y,
                                  props={'circuit_label': circuit_label},
                                  size=HGL_SIZE)
        # HGB: inlet comes from high-side liquid line (connected by caller if shared)
        # HGB outlet → HGL inlet
        _add_pipe(model, hgv_id, 'outlet', hgl_id, 'inlet',
                  fluid='two-phase', pressure='low', label=circuit_label)
        # HGL outlet → Merger inlet_1 (first inlet)
        _add_pipe(model, hgl_id, 'outlet', merger_id, f'inlet_{circuits}',
                  fluid='gas', pressure='low', label=circuit_label)

    # Merger → suction collector / compressor
    _add_pipe(model, merger_id, 'outlet_1',
              suction_out_id, suction_out_port,
              fluid='gas', pressure='low', label=circuit_label,
              waypoints=suction_waypoints)

    return {
        'txv_id':    txv_id,
        'bulb_id':   bulb_id,
        'evap_id':   evap_id,
        'merger_id': merger_id,
        'hgv_id':    hgv_id,
        'hgl_id':    hgl_id,
    }


def _build_air_side(model: dict, config: dict,
                    column_xs: list,
                    total_width: float) -> None:
    """Add Fan, post-coil AirSensorArray, discharge curtain(s), return air block,
    and ShelvingGrid for every column in column_xs.

    column_xs  — list of x-positions for each column
    total_width — width of the full case (for return air block)
    """
    curtain_type = config.get('air_curtain_type', 'single')
    shelf_rows   = config.get('shelf_rows', 5)
    n_cols       = len(column_xs)

    for col_x in column_xs:
        # Fan
        _add_component(model, 'Fan', col_x, FAN_Y,
                       props={'sensor_count': 4, 'circuit_label': 'None'},
                       size=FAN_SIZE)

        # Post-coil air sensor array (measures air leaving coil)
        _add_component(model, 'AirSensorArray', col_x, AIR_ARRAY_POST_Y,
                       props={'curtain_type': 'Primary',
                              'sensor_count': 2,
                              'block_width':  int(total_width / n_cols) - 20,
                              'block_height': 25},
                       size={'width': int(total_width / n_cols) - 20, 'height': 25})

        # Primary discharge curtain
        _add_component(model, 'AirSensorArray', col_x, AIR_ARRAY_PRIM_Y,
                       props={'curtain_type': 'Primary',
                              'sensor_count': 2,
                              'block_width':  int(total_width / n_cols) - 20,
                              'block_height': 25},
                       size={'width': int(total_width / n_cols) - 20, 'height': 25})

        # Secondary curtain (dual only)
        if curtain_type == 'dual':
            _add_component(model, 'AirSensorArray', col_x, AIR_ARRAY_SEC_Y,
                           props={'curtain_type': 'Secondary',
                                  'sensor_count': 2,
                                  'block_width':  int(total_width / n_cols) - 20,
                                  'block_height': 25},
                           size={'width': int(total_width / n_cols) - 20, 'height': 25})

        # ShelvingGrid (one per column)
        shelving_type = 'Non-Modular' if config.get('_shelving_non_modular', False) else 'Modular'
        _add_component(model, 'ShelvingGrid', col_x, SHELVING_Y,
                       props={'shelving_type': shelving_type,
                              'module_count':  1,
                              'door_count':    1,
                              'shelf_rows':    shelf_rows,
                              'shelf_width':   100,
                              'shelf_height':  60,
                              'row_gap':       20},
                       size={'width': 120, 'height': shelf_rows * 20 + 40})

    # Return air block — spans full case width, centred below all columns
    return_x = column_xs[0]
    _add_component(model, 'AirSensorArray', return_x, RETURN_AIR_Y,
                   props={'curtain_type': 'Return',
                          'sensor_count': 2,
                          'block_width':  int(total_width) - 20,
                          'block_height': 25},
                   size={'width': int(total_width) - 20, 'height': 25})


# ---------------------------------------------------------------------------
#  Public builder: Modular Self-Contained
# ---------------------------------------------------------------------------

def build_modular_self_contained(config: dict) -> dict:
    """Build a modular self-contained refrigerant diagram.

    Topology:
      Compressor → Condenser [→ FilterDrier] → Splitter(N out)
      For each module i:
          Splitter.outlet_i → TXV_i → Evap_i → Merger_i
          [Hot Gas Bypass: HGB_i.outlet → HGL_i → Merger_i.last_inlet]
      Merger_i.outlet_1 → Collector → Compressor.inlet
    """
    model    = _empty_model()
    n_mods   = MODULE_COUNT.get(config.get('case_size', '12 ft'), 3)
    labels   = CIRCUIT_LABELS[:n_mods]

    # Column x-positions for each module
    col_xs = [LEFT_OFFSET_X + i * MODULE_SPACING_X for i in range(n_mods)]
    total_w = n_mods * MODULE_SPACING_X

    # Shared head-end centred above the column array
    head_x_comp = col_xs[0]
    head_x_cond = head_x_comp + COMP_SIZE['width'] + 60
    head = _build_shared_head_end(model, config, head_x_comp, head_x_cond)

    comp_id = head['comp_id']

    # Sensor box
    _add_sensor_box(model, SENSOR_BOX_X, SENSOR_BOX_Y + n_mods * 30)

    # For single module (4ft) — no splitter/collector needed
    if n_mods == 1:
        loop = _build_module_refrigerant_loop(
            model, config,
            module_x=col_xs[0],
            circuit_label=labels[0],
            liquid_in_id=head['liquid_exit_id'],
            liquid_in_port=head['liquid_exit_port'],
            suction_out_id=comp_id,
            suction_out_port='inlet',
        )
        # Hot gas valve inlet from high-side
        if config.get('include_hot_gas_bypass', False) and loop['hgv_id']:
            _add_pipe(model, head['liquid_exit_id'], head['liquid_exit_port'],
                      loop['hgv_id'], 'inlet',
                      fluid='gas', pressure='high', label=labels[0])
    else:
        # Splitter junction: 1 in, N out
        circuits_per_mod = config.get('circuits_per_module', 6)
        
        # Center the junctions
        center_x = (col_xs[0] + col_xs[-1]) / 2 + EVAP_SIZE['width'] / 2
        splitter_id = _add_component(model, 'Junction', center_x, SPLITTER_Y,
                                     props={'inlet_count': 1,
                                            'outlet_count': n_mods,
                                            'port_spacing': 40,
                                            'circuit_label': 'None'},
                                     size={'width': 20,
                                           'height': n_mods * 40 + 20})

        _add_pipe(model, head['liquid_exit_id'], head['liquid_exit_port'],
                  splitter_id, 'inlet_1',
                  fluid='liquid', pressure='high', label='None',
                  waypoints=[
                      [head['fd_x'] if head.get('fd_id') else head_x_cond + COND_SIZE['width'], COND_Y + 30],
                      [center_x + 10, COND_Y + 30],
                      [center_x + 10, SPLITTER_Y]
                  ])

        # Collector junction: N in, 1 out
        collector_id = _add_component(model, 'Junction',
                                       center_x, COLLECTOR_Y,
                                       props={'inlet_count': n_mods,
                                              'outlet_count': 1,
                                              'port_spacing': 40,
                                              'circuit_label': 'None'},
                                       size={'width': 20,
                                             'height': n_mods * 40 + 20})

        _add_pipe(model, collector_id, 'outlet_1', comp_id, 'inlet',
                  fluid='gas', pressure='low', label='None',
                  waypoints=[
                      [center_x + 10, COLLECTOR_Y + n_mods * 40 + 20],
                      [head_x_comp + 10, COLLECTOR_Y + n_mods * 40 + 20],
                      [head_x_comp + 10, COMP_Y + 60]
                  ])

        # Per-module loops
        for i, (label, col_x) in enumerate(zip(labels, col_xs)):
            loop = _build_module_refrigerant_loop(
                model, config,
                module_x=col_x,
                circuit_label=label,
                liquid_in_id=splitter_id,
                liquid_in_port=f'outlet_{i + 1}',
                suction_out_id=collector_id,
                suction_out_port=f'inlet_{i + 1}',
                liquid_waypoints=[
                    [center_x + 20, SPLITTER_Y + i * 40 + 20],
                    [center_x + 80, SPLITTER_Y + i * 40 + 20],
                    [center_x + 80, SPLITTER_Y + n_mods * 40 + 40 + i * 10],
                    [col_x + TXV_SIZE['width'] / 2, SPLITTER_Y + n_mods * 40 + 40 + i * 10],
                    [col_x + TXV_SIZE['width'] / 2, TXV_Y]
                ],
                suction_waypoints=[
                    [col_x + 180 + 10, MERGER_Y + max(40, circuits_per_mod * 20 + 20)],
                    [col_x + 180 + 10, COLLECTOR_Y - 40 - i * 10],
                    [center_x, COLLECTOR_Y - 40 - i * 10],
                    [center_x, COLLECTOR_Y + i * 40 + 20]
                ]
            )
            # Hot gas valve inlet from high-side (tap off the condenser/FD outlet)
            if config.get('include_hot_gas_bypass', False) and loop['hgv_id']:
                _add_pipe(model, head['liquid_exit_id'], head['liquid_exit_port'],
                          loop['hgv_id'], 'inlet',
                          fluid='gas', pressure='high', label=label)

    # Air side
    _build_air_side(model, config, col_xs, total_w)

    model = apply_graphviz_layout(model)
    return model


# ---------------------------------------------------------------------------
#  Public builder: Modular Remote
# ---------------------------------------------------------------------------

def build_modular_remote(config: dict) -> dict:
    """Like modular_self_contained but uses RemoteLineEndpoint stubs instead of
    Compressor + Condenser."""
    model  = _empty_model()
    n_mods = MODULE_COUNT.get(config.get('case_size', '12 ft'), 3)
    labels = CIRCUIT_LABELS[:n_mods]
    col_xs = [LEFT_OFFSET_X + i * MODULE_SPACING_X for i in range(n_mods)]
    total_w = n_mods * MODULE_SPACING_X

    head = _build_remote_head_end(model, config, LEFT_OFFSET_X)

    # Suction stub (placed at far right)
    suc_stub_x = col_xs[-1] + MODULE_SPACING_X
    suc_stub_id = _add_component(model, 'RemoteLineEndpoint',
                                  suc_stub_x, COMP_Y,
                                  props={'label': 'Suction Line Out'},
                                  size=REM_SIZE)

    _add_sensor_box(model, SENSOR_BOX_X, SENSOR_BOX_Y + n_mods * 30)

    if n_mods == 1:
        loop = _build_module_refrigerant_loop(
            model, config,
            module_x=col_xs[0],
            circuit_label=labels[0],
            liquid_in_id=head['liquid_exit_id'],
            liquid_in_port=head['liquid_exit_port'],
            suction_out_id=suc_stub_id,
            suction_out_port='connection',
        )
    else:
        center_x = (col_xs[0] + col_xs[-1]) / 2 + EVAP_SIZE['width'] / 2
        splitter_id = _add_component(model, 'Junction', center_x, SPLITTER_Y,
                                     props={'inlet_count': 1,
                                            'outlet_count': n_mods,
                                            'port_spacing': 40,
                                            'circuit_label': 'None'},
                                     size={'width': 20, 'height': n_mods * 40 + 20})
        _add_pipe(model, head['liquid_exit_id'], head['liquid_exit_port'],
                  splitter_id, 'inlet_1',
                  fluid='liquid', pressure='high', label='None',
                  waypoints=[
                      [head['fd_x'] if head.get('fd_id') else REMOTE_LIQUID_X + REM_SIZE['width'], COMP_Y + 30],
                      [center_x + 10, COMP_Y + 30],
                      [center_x + 10, SPLITTER_Y]
                  ])

        collector_id = _add_component(model, 'Junction', center_x, COLLECTOR_Y,
                                      props={'inlet_count': n_mods,
                                             'outlet_count': 1,
                                             'port_spacing': 40,
                                             'circuit_label': 'None'},
                                      size={'width': 20, 'height': n_mods * 40 + 20})
        _add_pipe(model, collector_id, 'outlet_1', suc_stub_id, 'connection',
                  fluid='gas', pressure='low', label='None',
                  waypoints=[
                      [center_x + 10, COLLECTOR_Y + n_mods * 40 + 20],
                      [suc_stub_x + 10, COLLECTOR_Y + n_mods * 40 + 20],
                      [suc_stub_x + 10, COMP_Y + 60]
                  ])

        for i, (label, col_x) in enumerate(zip(labels, col_xs)):
            _build_module_refrigerant_loop(
                model, config,
                module_x=col_x,
                circuit_label=label,
                liquid_in_id=splitter_id,
                liquid_in_port=f'outlet_{i + 1}',
                suction_out_id=collector_id,
                suction_out_port=f'inlet_{i + 1}',
                liquid_waypoints=[
                    [center_x + 20, SPLITTER_Y + i * 40 + 20],
                    [center_x + 80, SPLITTER_Y + i * 40 + 20],
                    [center_x + 80, SPLITTER_Y + n_mods * 40 + 40 + i * 10],
                    [col_x + TXV_SIZE['width'] / 2, SPLITTER_Y + n_mods * 40 + 40 + i * 10],
                    [col_x + TXV_SIZE['width'] / 2, TXV_Y]
                ],
                suction_waypoints=[
                    [col_x + 180 + 10, MERGER_Y + max(40, config.get('circuits_per_module', 6) * 20 + 20)],
                    [col_x + 180 + 10, COLLECTOR_Y - 40 - i * 10],
                    [center_x, COLLECTOR_Y - 40 - i * 10],
                    [center_x, COLLECTOR_Y + i * 40 + 20]
                ]
            )

    _build_air_side(model, config, col_xs, total_w)
    return model


# ---------------------------------------------------------------------------
#  Shared single-loop non-modular builder
# ---------------------------------------------------------------------------

def _build_non_modular_loop(model: dict, config: dict,
                             liquid_in_id: str, liquid_in_port: str,
                             suction_out_id: str, suction_out_port: str,
                             col_xs: list) -> None:
    """Single evaporator loop for non-modular / freedom cases."""
    # Use first column x for refrigerant components
    mod_x = col_xs[0]

    loop = _build_module_refrigerant_loop(
        model, config,
        module_x=mod_x,
        circuit_label='None',          # non-modular: no module label
        liquid_in_id=liquid_in_id,
        liquid_in_port=liquid_in_port,
        suction_out_id=suction_out_id,
        suction_out_port=suction_out_port,
    )

    # Hot gas bypass inlet from high-side
    if config.get('include_hot_gas_bypass', False) and loop['hgv_id']:
        _add_pipe(model, liquid_in_id, liquid_in_port,
                  loop['hgv_id'], 'inlet',
                  fluid='gas', pressure='high', label='None')


# ---------------------------------------------------------------------------
#  Public builder: Non-Modular Self-Contained
# ---------------------------------------------------------------------------

def build_non_modular_self_contained(config: dict) -> dict:
    """Single evap, multiple door columns for fans/shelving/air.

    door_count drives: N Fan columns, N ShelvingGrid columns, AirSensorArray widths.
    """
    model    = _empty_model()
    n_doors  = config.get('door_count', 3)
    col_xs   = [LEFT_OFFSET_X + i * MODULE_SPACING_X for i in range(n_doors)]
    total_w  = n_doors * MODULE_SPACING_X

    # Mark shelving as non-modular
    config['_shelving_non_modular'] = True

    head_x_comp = col_xs[0]
    head_x_cond = head_x_comp + COMP_SIZE['width'] + 60
    head = _build_shared_head_end(model, config, head_x_comp, head_x_cond)

    _build_non_modular_loop(
        model, config,
        liquid_in_id=head['liquid_exit_id'],
        liquid_in_port=head['liquid_exit_port'],
        suction_out_id=head['comp_id'],
        suction_out_port='inlet',
        col_xs=col_xs,
    )

    _add_sensor_box(model, SENSOR_BOX_X, SENSOR_BOX_Y)
    _build_air_side(model, config, col_xs, total_w)
    return model


# ---------------------------------------------------------------------------
#  Public builder: Non-Modular Remote
# ---------------------------------------------------------------------------

def build_non_modular_remote(config: dict) -> dict:
    model   = _empty_model()
    n_doors = config.get('door_count', 3)
    col_xs  = [LEFT_OFFSET_X + i * MODULE_SPACING_X for i in range(n_doors)]
    total_w = n_doors * MODULE_SPACING_X

    config['_shelving_non_modular'] = True

    head = _build_remote_head_end(model, config, LEFT_OFFSET_X)

    suc_x = col_xs[-1] + MODULE_SPACING_X
    suc_stub_id = _add_component(model, 'RemoteLineEndpoint',
                                  suc_x, COMP_Y,
                                  props={'label': 'Suction Line Out'},
                                  size=REM_SIZE)

    _build_non_modular_loop(
        model, config,
        liquid_in_id=head['liquid_exit_id'],
        liquid_in_port=head['liquid_exit_port'],
        suction_out_id=suc_stub_id,
        suction_out_port='connection',
        col_xs=col_xs,
    )

    _add_sensor_box(model, SENSOR_BOX_X, SENSOR_BOX_Y)
    _build_air_side(model, config, col_xs, total_w)
    return model


# ---------------------------------------------------------------------------
#  Public builder: Cassette
# ---------------------------------------------------------------------------

def build_cassette(config: dict) -> dict:
    """N fully independent refrigerant loops (each with own comp + cond).

    All units share the same config (TXV type, condenser type, filter dryer,
    hot gas bypass, circuits per unit).

    The shelving / fan / air side is driven by the *underlying case* (modular or
    non-modular) chosen separately in the wizard.
    """
    model      = _empty_model()
    n_units    = config.get('cassette_count', 1)
    unit_labels = CIRCUIT_LABELS[:n_units]

    # --- Refrigerant side: one independent loop per unit ---
    # Space units further apart so the loops don't overlap
    unit_spacing = MODULE_SPACING_X * 2
    unit_xs = [LEFT_OFFSET_X + i * unit_spacing for i in range(n_units)]

    unit_suction_stubs = []   # not needed — comp is per-unit, loop connects back to it

    for i, (label, ux) in enumerate(zip(unit_labels, unit_xs)):
        # Each cassette unit has its own compressor + condenser
        comp_x = ux
        cond_x = comp_x + COMP_SIZE['width'] + 60
        condenser_type = config.get('condenser_type', 'Air Cooled')

        unit_comp_id = _add_component(model, 'Compressor', comp_x, COMP_Y,
                                       props={'circuit_label': label},
                                       size=COMP_SIZE)
        unit_cond_id = _add_component(model, 'Condenser', cond_x, COND_Y,
                                       props={'condenser_type': condenser_type,
                                              'circuit_label': label},
                                       size=COND_SIZE)
        _add_pipe(model, unit_comp_id, 'outlet', unit_cond_id, 'inlet',
                  fluid='gas', pressure='high', label=label)

        # Optional filter drier per unit
        fd_id = None
        fd_x  = cond_x + COND_SIZE['width'] + 60
        if config.get('include_filter_dryer', False):
            fd_id = _add_component(model, 'FilterDrier', fd_x, FILTER_DRIER_Y,
                                   props={'circuit_label': label},
                                   size=FD_SIZE)
            _add_pipe(model, unit_cond_id, 'outlet', fd_id, 'inlet',
                      fluid='liquid', pressure='high', label=label)

        liq_id   = fd_id if fd_id else unit_cond_id
        liq_port = 'outlet'

        loop = _build_module_refrigerant_loop(
            model, config,
            module_x=ux,
            circuit_label=label,
            liquid_in_id=liq_id,
            liquid_in_port=liq_port,
            suction_out_id=unit_comp_id,
            suction_out_port='inlet',
        )

        if config.get('include_hot_gas_bypass', False) and loop['hgv_id']:
            _add_pipe(model, liq_id, liq_port,
                      loop['hgv_id'], 'inlet',
                      fluid='gas', pressure='high', label=label)

    # --- Air / shelving side: follows *underlying case* ---
    cassette_case_type = config.get('cassette_case_type', 'non_modular')
    if cassette_case_type == 'modular':
        n_air_cols = MODULE_COUNT.get(config.get('cassette_case_size', '12 ft'), 3)
    else:
        n_air_cols = config.get('cassette_door_count', 3)

    # Place air-side columns starting from same left offset
    col_xs   = [LEFT_OFFSET_X + i * MODULE_SPACING_X for i in range(n_air_cols)]
    total_w  = n_air_cols * MODULE_SPACING_X

    config['_shelving_non_modular'] = (cassette_case_type == 'non_modular')
    _build_air_side(model, config, col_xs, total_w)

    _add_sensor_box(model, SENSOR_BOX_X, SENSOR_BOX_Y + n_units * 30)
    return model


# ---------------------------------------------------------------------------
#  Public builder: Freedom
# ---------------------------------------------------------------------------

def build_freedom(config: dict) -> dict:
    """Freedom case — identical topology to non-modular self-contained, always
    one condensing unit, always self-contained.  Typically 1-door column."""
    # Freedom: treat as 1-door non-modular SC
    config['door_count'] = config.get('door_count', 1)
    config['_shelving_non_modular'] = False  # Freedom uses modular shelving style

    model   = _empty_model()
    n_doors = config.get('door_count', 1)
    col_xs  = [LEFT_OFFSET_X + i * MODULE_SPACING_X for i in range(n_doors)]
    total_w = max(MODULE_SPACING_X, n_doors * MODULE_SPACING_X)

    head_x_comp = col_xs[0]
    head_x_cond = head_x_comp + COMP_SIZE['width'] + 60
    head = _build_shared_head_end(model, config, head_x_comp, head_x_cond)

    _build_non_modular_loop(
        model, config,
        liquid_in_id=head['liquid_exit_id'],
        liquid_in_port=head['liquid_exit_port'],
        suction_out_id=head['comp_id'],
        suction_out_port='inlet',
        col_xs=col_xs,
    )

    _add_sensor_box(model, SENSOR_BOX_X, SENSOR_BOX_Y)
    _build_air_side(model, config, col_xs, total_w)
    return model


# ---------------------------------------------------------------------------
#  Dispatcher
# ---------------------------------------------------------------------------

def build_diagram_from_config(config: dict) -> dict:
    """Dispatch to the correct builder based on config['case_type'].

    config['case_type'] must be one of:
        'modular_self_contained'
        'modular_remote'
        'non_modular_self_contained'
        'non_modular_remote'
        'cassette'
        'freedom'
    """
    builders = {
        'modular_self_contained':     build_modular_self_contained,
        'modular_remote':             build_modular_remote,
        'non_modular_self_contained': build_non_modular_self_contained,
        'non_modular_remote':         build_non_modular_remote,
        'cassette':                   build_cassette,
        'freedom':                    build_freedom,
    }
    case_type = config.get('case_type', 'non_modular_self_contained')
    builder   = builders.get(case_type)
    if builder is None:
        raise ValueError(f"Unknown case_type: {case_type!r}. "
                         f"Expected one of: {list(builders)}")
    model = builder(config)
    model = apply_graphviz_layout(model)
    return model
