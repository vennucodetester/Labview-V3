"""
diagram_template_loader.py

Loads a hand-crafted diagramModel from a session JSON file, driven by a
persistent config-key → file-path mapping stored in diagram_template_map.json.

Public API
----------
get_config_key(config)          → stable string key for a wizard config dict
load_template_diagram(config, parent_widget=None)
                                → diagramModel dict, or None if user cancelled

Internal helpers
----------------
load_mapping()                  → dict
save_mapping(mapping)
extract_diagram_model(path)     → dict
get_or_pick_template(key, parent_widget, force=False)  → path str or None
"""

import os
import json
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Paths
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
MAPPING_FILE    = os.path.join(_HERE, 'diagram_template_map.json')
TEMPLATES_FOLDER = os.path.join(_HERE, 'templates')


# ---------------------------------------------------------------------------
#  Config-key derivation
# ---------------------------------------------------------------------------

def get_config_key(config: dict) -> str:
    """Derive a stable, human-readable string key from a wizard config dict.

    Examples
    --------
    modular_self_contained_12ft
    modular_remote_8ft
    non_modular_self_contained_3door
    non_modular_remote_5door
    cassette_2units
    freedom
    """
    ct = config.get('case_type', '')

    if ct.startswith('modular') and not ct.startswith('non_modular'):
        size = config.get('case_size', '').replace(' ', '')   # '12 ft' → '12ft'
        return f"{ct}_{size}"

    elif ct.startswith('non_modular'):
        doors = config.get('door_count', 1)
        return f"{ct}_{doors}door"

    elif ct == 'cassette':
        units = config.get('cassette_count', 1)
        return f"cassette_{units}units"

    else:  # 'freedom' or unrecognised
        return ct


# ---------------------------------------------------------------------------
#  Mapping file I/O
# ---------------------------------------------------------------------------

def load_mapping() -> dict:
    """Load diagram_template_map.json.  Returns empty dict if file missing."""
    if not os.path.isfile(MAPPING_FILE):
        return {}
    try:
        with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception as exc:
        logger.warning("Could not load template mapping file: %s", exc)
    return {}


def save_mapping(mapping: dict) -> None:
    """Persist diagram_template_map.json atomically."""
    tmp = MAPPING_FILE + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=2)
        os.replace(tmp, MAPPING_FILE)
    except Exception as exc:
        logger.error("Could not save template mapping file: %s", exc)


# ---------------------------------------------------------------------------
#  Session JSON → diagramModel extraction
# ---------------------------------------------------------------------------

def extract_diagram_model(json_path: str) -> dict:
    """Read a full session JSON and return only its 'diagramModel' dict.

    The returned dict will always have these keys (even if absent in file):
        components, pipes, sensor_roles, custom_sensors, sensor_boxes, role_dot_labels
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        session = json.load(f)

    dm = session.get('diagramModel', {})

    # Ensure all expected keys are present
    for key in ('components', 'pipes', 'sensor_roles',
                'custom_sensors', 'sensor_boxes', 'role_dot_labels'):
        if key not in dm:
            dm[key] = {}

    # Migrate any legacy sensor_role key names (T_1c-rh → T_1b-rh, T_2a-ctr → T_2a-CTR)
    from data_manager import _migrate_sensor_role_keys
    _migrate_sensor_role_keys(dm)

    return dm


# ---------------------------------------------------------------------------
#  File picker + mapping persistence
# ---------------------------------------------------------------------------

def get_or_pick_template(config_key: str, parent_widget=None,
                          force: bool = False) -> str | None:
    """Return the template file path for config_key.

    If already mapped and force=False  →  return existing path immediately.
    Otherwise open a QFileDialog.  If user cancels  →  return None.
    On success, save the new mapping and return the chosen path.
    """
    mapping = load_mapping()

    # Return cached path unless forced to re-pick
    if not force and config_key in mapping:
        cached = mapping[config_key]
        if os.path.isfile(cached):
            logger.info("Template resolved from mapping: %s → %s", config_key, cached)
            return cached
        else:
            logger.warning("Cached template file not found, will re-pick: %s", cached)

    # Open file dialog
    from PyQt6.QtWidgets import QFileDialog

    start_dir = TEMPLATES_FOLDER if os.path.isdir(TEMPLATES_FOLDER) else _HERE

    chosen, _ = QFileDialog.getOpenFileName(
        parent_widget,
        f"Select template file for  '{config_key}'",
        start_dir,
        "JSON Session Files (*.json);;All Files (*)"
    )

    if not chosen:
        return None   # user cancelled

    mapping[config_key] = chosen
    save_mapping(mapping)
    logger.info("Template mapped: %s → %s", config_key, chosen)
    return chosen


# ---------------------------------------------------------------------------
#  Top-level function called by diagram_widget
# ---------------------------------------------------------------------------

def load_template_diagram(config: dict, parent_widget=None) -> dict | None:
    """Resolve a template file for the wizard config and return its diagramModel.

    Returns None if the user cancels the file picker or the file cannot be read.
    """
    config_key = get_config_key(config)
    logger.info("Loading template for config_key=%r", config_key)

    file_path = get_or_pick_template(config_key, parent_widget=parent_widget)
    if file_path is None:
        logger.info("Template load cancelled by user.")
        return None

    try:
        model = extract_diagram_model(file_path)
        n_comp = len(model.get('components', {}))
        n_pipe = len(model.get('pipes', {}))
        logger.info("Template loaded: %d components, %d pipes from %s",
                    n_comp, n_pipe, file_path)
        return model
    except Exception as exc:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(
            parent_widget,
            "Template Load Error",
            f"Could not read template file:\n{file_path}\n\n{exc}"
        )
        logger.error("Failed to load template %s: %s", file_path, exc)
        return None
