"""
diagram_template_patcher.py

Applies surgical patches to a loaded diagramModel dict based on wizard config.
No pipe auto-connection — the user wires disconnected pipes manually.
All changes are applied in-memory before the scene is rebuilt.

Public API
----------
patch_diagram_model(model, config) → model (mutated in-place and returned)
"""

import uuid
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------------

def _make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:6]}"


def _components_of_type(model: dict, comp_type: str) -> list[tuple[str, dict]]:
    """Return [(comp_id, comp_data), ...] for all components of given type."""
    return [
        (cid, c)
        for cid, c in model['components'].items()
        if c.get('type') == comp_type
    ]


def _remove_component(model: dict, comp_id: str) -> None:
    """Delete a component and all pipes connected to it.
    Also removes any sensor_roles entries that reference the removed component.
    """
    # Remove from components
    model['components'].pop(comp_id, None)

    # Remove connected pipes
    pipes_to_delete = [
        pid for pid, p in model['pipes'].items()
        if p.get('start_component_id') == comp_id
        or p.get('end_component_id') == comp_id
    ]
    for pid in pipes_to_delete:
        model['pipes'].pop(pid, None)

    # Remove sensor_roles entries for this component
    roles_to_delete = [
        key for key in model.get('sensor_roles', {})
        if key.split('.')[1] == comp_id   # role_key format: "Type.comp_id.port"
    ]
    for key in roles_to_delete:
        model['sensor_roles'].pop(key, None)

    if pipes_to_delete:
        logger.debug("Removed component %s and %d pipe(s)", comp_id, len(pipes_to_delete))


def _find_position_near(model: dict, comp_type_hint: str,
                         offset_x: float = 120, offset_y: float = 0) -> list:
    """Find a position offset from an existing component of comp_type_hint.
    Falls back to a safe default position if no such component exists.
    """
    # Try to find any component of the hinted type to use as anchor
    candidates = _components_of_type(model, comp_type_hint)
    if candidates:
        _, c = candidates[0]
        pos = c.get('position', [0, 0])
        return [pos[0] + offset_x, pos[1] + offset_y]

    # Fall back: offset from diagram centre
    if model['components']:
        xs = [c['position'][0] for c in model['components'].values()]
        ys = [c['position'][1] for c in model['components'].values()]
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        return [cx + offset_x, cy + offset_y]

    return [200 + offset_x, 200 + offset_y]


def _add_component(model: dict, comp_type: str, position: list,
                   props: dict = None, size: dict = None) -> str:
    """Add a component to the model; return its new id."""
    comp_id = _make_id(comp_type.lower()[:10])
    model['components'][comp_id] = {
        'type':       comp_type,
        'position':   position,
        'properties': props or {},
        'size':       size or {'width': 100, 'height': 60},
        'rotation':   0,
    }
    return comp_id


# ---------------------------------------------------------------------------
#  Individual patch operations
# ---------------------------------------------------------------------------

def _patch_filter_dryer(model: dict, config: dict) -> None:
    """Add or remove FilterDrier component based on config['include_filter_dryer']."""
    want_fd = config.get('include_filter_dryer', False)
    existing = _components_of_type(model, 'FilterDrier')

    if want_fd and not existing:
        # Place near Condenser (or RemoteLineEndpoint for remote cases)
        anchor = ('Condenser' if _components_of_type(model, 'Condenser')
                  else 'RemoteLineEndpoint')
        pos = _find_position_near(model, anchor, offset_x=160, offset_y=0)
        cid = _add_component(model, 'FilterDrier', pos,
                              props={'circuit_label': 'None'},
                              size={'width': 80, 'height': 40})
        logger.info("Patcher: added FilterDrier %s at %s (unconnected)", cid, pos)

    elif not want_fd and existing:
        for cid, _ in existing:
            _remove_component(model, cid)
        logger.info("Patcher: removed %d FilterDrier component(s)", len(existing))


def _patch_hot_gas_bypass(model: dict, config: dict) -> None:
    """Add or remove HotGasBypassValve + HotGasLoop components."""
    want_hgb = config.get('include_hot_gas_bypass', False)
    existing_valves = _components_of_type(model, 'HotGasBypassValve')
    existing_loops  = _components_of_type(model, 'HotGasLoop')

    if want_hgb and not existing_valves:
        # Add one pair per evaporator (or one pair if no evaporators)
        evaporators = _components_of_type(model, 'Evaporator')
        targets = evaporators if evaporators else [(None, None)]
        for evap_id, evap_data in targets:
            if evap_data is not None:
                pos = list(evap_data.get('position', [0, 0]))
                valve_pos = [pos[0] - 140, pos[1] - 80]
                loop_pos  = [pos[0] - 140, pos[1] + 20]
            else:
                valve_pos = _find_position_near(model, 'TXV', offset_x=0, offset_y=-80)
                loop_pos  = _find_position_near(model, 'TXV', offset_x=0, offset_y=+20)

            # Inherit circuit_label from evaporator if available
            cl = (evap_data.get('properties', {}).get('circuit_label', 'None')
                  if evap_data else 'None')

            vid = _add_component(model, 'HotGasBypassValve', valve_pos,
                                  props={'circuit_label': cl},
                                  size={'width': 60, 'height': 50})
            lid = _add_component(model, 'HotGasLoop', loop_pos,
                                  props={'circuit_label': cl},
                                  size={'width': 100, 'height': 50})
            logger.info("Patcher: added HotGasBypassValve %s + HotGasLoop %s "
                        "(circuit_label=%s, unconnected)", vid, lid, cl)

    elif not want_hgb:
        for cid, _ in existing_valves:
            _remove_component(model, cid)
        for cid, _ in existing_loops:
            _remove_component(model, cid)
        if existing_valves or existing_loops:
            logger.info("Patcher: removed %d HotGasBypassValve + %d HotGasLoop",
                        len(existing_valves), len(existing_loops))


def _patch_expansion_device(model: dict, config: dict) -> None:
    """Flip expansion_device_type on all TXV components.

    Cap Tube: set property, remove any pipes connected to the 'bulb' port.
    TXV:      set property (bulb port will reappear when scene rebuilds).
    """
    want_type = config.get('expansion_type', 'TXV')  # 'TXV' | 'Cap Tube'
    txvs = _components_of_type(model, 'TXV')

    for cid, comp in txvs:
        props = comp.setdefault('properties', {})
        current = props.get('expansion_device_type', 'TXV')
        if current == want_type:
            continue

        props['expansion_device_type'] = want_type

        if want_type == 'Cap Tube':
            # Remove pipes connected to this component's 'bulb' port
            bulb_pipes = [
                pid for pid, p in model['pipes'].items()
                if (p.get('start_component_id') == cid and p.get('start_port') == 'bulb')
                or (p.get('end_component_id')   == cid and p.get('end_port')   == 'bulb')
            ]
            for pid in bulb_pipes:
                model['pipes'].pop(pid, None)
            if bulb_pipes:
                logger.debug("Patcher: removed %d bulb pipe(s) for TXV %s", len(bulb_pipes), cid)

        logger.info("Patcher: TXV %s expansion_device_type → %s", cid, want_type)


def _patch_condenser_type(model: dict, config: dict) -> None:
    """Set condenser_type property on all Condenser components."""
    want_ctype = config.get('condenser_type', 'Air Cooled')
    for cid, comp in _components_of_type(model, 'Condenser'):
        props = comp.setdefault('properties', {})
        if props.get('condenser_type') != want_ctype:
            props['condenser_type'] = want_ctype
            logger.info("Patcher: Condenser %s condenser_type → %s", cid, want_ctype)


def _patch_shelving(model: dict, config: dict) -> None:
    """Update shelf_rows property on all ShelvingGrid components."""
    want_rows = config.get('shelf_rows')
    if want_rows is None:
        return
    want_rows = int(want_rows)
    for cid, comp in _components_of_type(model, 'ShelvingGrid'):
        props = comp.setdefault('properties', {})
        if props.get('shelf_rows') != want_rows:
            props['shelf_rows'] = want_rows
            logger.info("Patcher: ShelvingGrid %s shelf_rows → %d", cid, want_rows)


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def patch_diagram_model(model: dict, config: dict) -> dict:
    """Apply wizard-driven patches to a loaded template diagramModel.

    Patches applied (in order):
    1. Filter Dryer   — add if wanted and missing; remove if unwanted and present
    2. Hot Gas Bypass — add HotGasBypassValve+HotGasLoop per evap if wanted and missing; remove if unwanted
    3. Expansion type — flip expansion_device_type on all TXV components
    4. Condenser type — update condenser_type property on all Condenser components
    5. Shelving rows  — update shelf_rows property on all ShelvingGrid components

    No pipes are auto-connected when components are added.
    Pipes are removed when components are deleted.
    sensor_roles entries for deleted components are removed.

    Returns model (mutated in-place).
    """
    _patch_filter_dryer(model, config)
    _patch_hot_gas_bypass(model, config)
    _patch_expansion_device(model, config)
    _patch_condenser_type(model, config)
    _patch_shelving(model, config)

    n_comp = len(model.get('components', {}))
    n_pipe = len(model.get('pipes', {}))
    logger.info("Patcher complete: %d components, %d pipes in model", n_comp, n_pipe)
    return model
