import pandas as pd
from pandas.api.types import is_datetime64_any_dtype
import json
import base64
import os
import re
import uuid
import copy
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QPixmap
from mapping_dialog import MappingDialog
import sys
from timestamp_diagnostics import log_conversion, compare_timestamps, verify_range_selection
from timestamp_fixer import fix_ambiguous_dates
from snapshot_manager import SnapshotManager

# Force stdout to flush immediately so logs appear in real-time
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None


def _migrate_sensor_role_keys(diagram_model: dict) -> dict:
    """Rename legacy sensor_role keys to the current canonical names.

    Migrations applied:
      T_1c-rh  → T_1b-rh   Right coil-inlet was misnamed (T_1c instead of T_1b)
      T_2a-ctr → T_2a-CTR  Center coil-outlet abbreviation is now uppercase (CTR not ctr)

    Mutates diagram_model['sensor_roles'] in-place and returns diagram_model.
    Safe to call multiple times — idempotent.
    """
    sr = diagram_model.get('sensor_roles')
    if not isinstance(sr, dict):
        return diagram_model
    renames = {'T_1c-rh': 'T_1b-rh', 'T_2a-ctr': 'T_2a-CTR'}
    changed = []
    for old_key, new_key in renames.items():
        if old_key in sr and new_key not in sr:
            sr[new_key] = sr.pop(old_key)
            changed.append(f'{old_key} → {new_key}')
    if changed:
        print(f"[MIGRATE] Renamed legacy sensor_role key(s): {', '.join(changed)}")
    return diagram_model


class DataManager(QObject):
    """
    Centralized class to manage all application data, including sensor groups.
    """
    data_changed = pyqtSignal()
    diagram_model_changed = pyqtSignal()
    sensor_mapping_changed = pyqtSignal(str, str, bool)  # role_key, sensor_name, is_mapped
    snapshots_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.snapshot_manager = SnapshotManager()
        self._reset_state()

    def _reset_state(self):
        """Resets all data to initial state."""
        self.csv_data = None
        self.mappings = {}
        self.selected_sensors = set()
        self.graph_sensors = set()
        self.sensor_groups = {}
        self.group_states = {}  # Format: {group_name: True/False} for expansion state
        self.sensor_ranges = {}  # Format: {sensor_name: {'min': value, 'max': value}}
        self.image_path = None
        self.image_pixmap = None
        self.config_path = None
        self.csv_path = None
        self.current_mode = 'mapping'
        self.config_sensor_list = []
        # Preserve original config headers and their mapping to current CSV headers
        self.original_config_sensor_list = []
        self.config_label_mapping = {}
        self.last_auto_map_report = {
            "csv_columns": 0,
            "mapped": 0,
            "expected_canonical": 0,
            "unmapped_csv": [],
            "unmapped_expected": [],
            "ignored_csv": [],
            "known_but_no_role": [],
            "known_but_filled": [],
            "mapped_columns": {},
        }

        self.time_range = 'All Data'  # Options: '1 Hour', '8 Hours', '24 Hours', '48 Hours', 'All Data', 'Custom'
        self.value_aggregation = 'Average'  # Options: 'Average', 'Maximum', 'Minimum'
        self.custom_time_range = None  # Stores custom time range as {'start': timestamp, 'end': timestamp}
        self.custom_time_ranges = None  # Stores multi-range filter: {'keep': [(start, end), ...], 'delete': [(start, end), ...]}

        # Cached filtered data for performance optimization
        self._cached_filtered_data = None
        self._cache_key = None  # Tuple of (time_range, custom_time_range, custom_time_ranges) for cache invalidation

        # Calculation settings
        self.refrigerant = 'R290'  # Changed from R410A to R290 (Propane) per plan.txt

        # ON-time filtering settings
        self.on_time_threshold_psig = 40.0  # Default threshold for R290 low-temp systems
        self.on_time_filtering_enabled = True
        self.on_time_percentage = 0.0
        self.on_time_row_count = 0
        self.total_row_count = 0
        self.aggregation_method = 'Average'

        # Rated inputs for volumetric efficiency calculation (Step 1 from spec)
        # Updated for Goal-2C: Added rated_capacity and rated_power (7 total)
        self.rated_inputs = {
            'rated_capacity_btu_hr': None,  # Rated cooling capacity (BTU/hr)
            'rated_power_w': None,  # Rated power consumption (W)
            'm_dot_rated_lbhr': None,  # Rated mass flow rate (lbm/hr)
            'hz_rated': None,  # Rated compressor speed (Hz)
            'disp_ft3': None,  # Compressor displacement (ft³)
            'rated_evap_temp_f': None,  # Rated evaporator temperature (°F)
            'rated_return_gas_temp_f': None,  # Rated return gas temperature (°F)
        }

        # Diagram model for refrigeration system designer
        self.diagram_model = {
            "components": {},
            "pipes": {},
            "sensor_roles": {},
            "custom_sensors": {},
            "sensor_boxes": {},   # Renamed from other_sensors_boxes
            "sensor_points": {},  # role_key → {enabled, label}
        }

    # --- load_csv and reconcile_csv are unchanged ---
    def load_csv(self, file_path):
        """
        Loads a CSV or Excel file. If a config is already loaded, it triggers
        the reconciliation process.
        """
        import os

        try:
            # Detect file type by extension
            file_ext = os.path.splitext(file_path)[1].lower()

            if file_ext in ['.xlsx', '.xls']:
                # Load Excel file (first sheet only)
                new_csv_data = pd.read_excel(file_path, sheet_name=0, engine='openpyxl' if file_ext == '.xlsx' else None)
                print(f"[LOAD_CSV] Loaded Excel file ({file_ext}): {list(new_csv_data.columns)}")
            elif file_ext == '.csv':
                new_csv_data = pd.read_csv(file_path)
                print(f"[LOAD_CSV] Loaded CSV file: {list(new_csv_data.columns)}")
            else:
                # Fallback: try CSV format
                print(f"[LOAD_CSV] Unknown extension {file_ext}, attempting CSV parse")
                new_csv_data = pd.read_csv(file_path)
                print(f"[LOAD_CSV] CSV columns: {list(new_csv_data.columns)}")
            
            # Handle timestamp column creation
            if 'Timestamp' in new_csv_data.columns:
                # Already has Timestamp column
                try:
                    new_csv_data['Timestamp'] = pd.to_datetime(new_csv_data['Timestamp'], errors='coerce')
                    print(f"[LOAD_CSV] Parsed existing Timestamp column successfully")
                except Exception:
                    print(f"[LOAD_CSV] Failed to parse existing Timestamp column")
                    pass
            elif 'Date' in new_csv_data.columns and 'Time' in new_csv_data.columns:
                # Combine Date and Time columns to create Timestamp
                try:
                    print(f"[LOAD_CSV] Found Date and Time columns, combining them...")
                    print(f"[LOAD_CSV] Sample Date values: {new_csv_data['Date'].head(3).tolist()}")
                    print(f"[LOAD_CSV] Sample Time values: {new_csv_data['Time'].head(3).tolist()}")
                    
                    # Convert Date and Time to strings and combine
                    date_str = new_csv_data['Date'].astype(str)
                    time_str = new_csv_data['Time'].astype(str)
                    timestamp_str = date_str + ' ' + time_str
                    print(f"[LOAD_CSV] Sample combined timestamp strings: {timestamp_str.head(3).tolist()}")
                    
                    # CRITICAL FIX: Use intelligent timestamp fixing
                    print(f"[LOAD_CSV] Using intelligent timestamp fixing...")
                    new_csv_data['Timestamp'] = fix_ambiguous_dates(
                        new_csv_data['Date'], 
                        new_csv_data['Time']
                    )
                    
                    print(f"[LOAD_CSV] Created Timestamp column from Date and Time columns")
                    print(f"[LOAD_CSV] Sample timestamps: {new_csv_data['Timestamp'].head(3).tolist()}")
                    print(f"[LOAD_CSV] Timestamp column created successfully: {new_csv_data['Timestamp'].dtype}")
                    
                    # Verify the timestamp range makes sense
                    if not new_csv_data['Timestamp'].dropna().empty:
                        first_ts = new_csv_data['Timestamp'].dropna().iloc[0]
                        last_ts = new_csv_data['Timestamp'].dropna().iloc[-1]
                        print(f"[LOAD_CSV] Timestamp range: {first_ts} to {last_ts}")
                        print(f"[LOAD_CSV] Duration: {last_ts - first_ts}")
                        
                        # Check for reasonable date range (not in distant future)
                        current_year = pd.Timestamp.now().year
                        if first_ts.year > current_year + 1:
                            print(f"[LOAD_CSV] WARNING: Data appears to be from future year {first_ts.year}")
                            print(f"[LOAD_CSV] This may indicate incorrect year parsing")
                    
                    # DIAGNOSTIC: Log the timestamp creation
                    log_conversion(
                        stage="DATA_LOAD",
                        description="Created Timestamp column from Date+Time",
                        value=new_csv_data['Timestamp'],
                        source_format="Date + Time strings",
                        result_dtype=str(new_csv_data['Timestamp'].dtype),
                        sample_values=new_csv_data['Timestamp'].head(3).tolist()
                    )
                    
                    # Move Timestamp to the front
                    cols = ['Timestamp'] + [col for col in new_csv_data.columns if col not in ['Timestamp', 'Date', 'Time']]
                    new_csv_data = new_csv_data[cols]
                    print(f"[LOAD_CSV] Reordered columns, new shape: {new_csv_data.shape}")
                    print(f"[LOAD_CSV] New column order: {list(new_csv_data.columns[:5])}...")
                except Exception as e:
                    print(f"[LOAD_CSV] Failed to create Timestamp from Date and Time: {e}")
                    import traceback
                    traceback.print_exc()
                    # Fallback: use first column as timestamp if it looks like a datetime
                    first_col = new_csv_data.columns[0]
                    try:
                        new_csv_data['Timestamp'] = pd.to_datetime(new_csv_data[first_col], errors='coerce')
                        print(f"[LOAD_CSV] Created Timestamp from first column: {first_col}")
                    except Exception:
                        print(f"[LOAD_CSV] No suitable timestamp column found")
            else:
                print(f"[LOAD_CSV] No 'Timestamp' column or Date/Time columns found in CSV")
            
            # Sanitize: Remove Unnamed columns created by trailing commas
            new_csv_data = self._sanitize_columns(new_csv_data)
            
            new_sensor_list = [col for col in new_csv_data.columns if col != 'Timestamp'] 

            print(f"[LOAD_CSV] config_path={self.config_path}, config_sensor_list has {len(self.config_sensor_list)} sensors")
            print(f"[LOAD_CSV] new CSV has {len(new_sensor_list)} sensors")
            
            # Store the CSV file path
            self.csv_path = file_path

            if self.config_path and self.config_sensor_list:
                print(f"[LOAD_CSV] Triggering reconciliation...")
                self.reconcile_csv(new_csv_data, new_sensor_list)
            else:
                print(f"[LOAD_CSV] Skipping reconciliation (no config loaded)")
                self.csv_data = new_csv_data
                self._invalidate_filtered_cache()
                self.data_changed.emit()
            # Auto-map CSV columns to canonical roles using the alias DB
            try:
                self.auto_map_csv_to_canonical(new_sensor_list)
            except Exception as e:
                print(f"[AUTO_MAP] Failed: {e}")
            return True
        except Exception as e:
            print(f"Error loading CSV file: {e}")
            return False

    def reconcile_csv(self, new_csv_data, new_sensor_list):
        """
        Compares the new CSV against the loaded config and opens a dialog
        for the user to map sensor name changes.
        """
        print(f"[RECONCILE_CSV] Starting reconciliation...")
        print(f"[RECONCILE_CSV] Config has {len(self.config_sensor_list)} sensors")
        print(f"[RECONCILE_CSV] CSV has {len(new_sensor_list)} sensors")
        
        orphaned = sorted([s for s in self.config_sensor_list if s not in new_sensor_list])
        new = sorted([s for s in new_sensor_list if s not in self.config_sensor_list])
        matched = sorted([s for s in self.config_sensor_list if s in new_sensor_list])
        
        print(f"[RECONCILE_CSV] Matched: {len(matched)}, Orphaned: {len(orphaned)}, New: {len(new)}")

        # Always show mapping dialog for user confirmation, even if all sensors match
        # Ensure original config list exists before showing dialog
        if not self.original_config_sensor_list:
            self.original_config_sensor_list = list(self.config_sensor_list)

        # Initialize identity mapping for matched sensors (will be shown in dialog)
        if not self.config_label_mapping:
            self.config_label_mapping = {}

        dialog = MappingDialog(orphaned, new, matched, parent=self.parent)
        if dialog.exec():
            user_mappings = dialog.get_mappings()  # old_config_name -> new_csv_name
            
            # Update old mappings dict (legacy system)
            new_mappings_dict = {}
            for old_sensor, mapping_data in self.mappings.items():
                if old_sensor in matched:
                    new_mappings_dict[old_sensor] = mapping_data
                elif old_sensor in user_mappings:
                    new_sensor_name = user_mappings[old_sensor]
                    new_mappings_dict[new_sensor_name] = mapping_data
            self.mappings = new_mappings_dict
            
            # Update sensor_roles dict to use new CSV sensor names
            roles = self.diagram_model.get('sensor_roles', {})
            updated_roles = {}
            for role_key, old_sensor_name in roles.items():
                if old_sensor_name in user_mappings:
                    # Remap to new CSV name
                    updated_roles[role_key] = user_mappings[old_sensor_name]
                    print(f"[RECONCILE] Remapped {role_key}: {old_sensor_name} -> {user_mappings[old_sensor_name]}")
                elif old_sensor_name in matched:
                    # Keep matched sensors (identical names)
                    updated_roles[role_key] = old_sensor_name
                else:
                    # Sensor was not matched - PRESERVE the original mapping
                    # (it may exist in the CSV under a different header)
                    updated_roles[role_key] = old_sensor_name
                    print(f"[RECONCILE] PRESERVED unmapped {role_key}: {old_sensor_name} (assuming different column name)")
            self.diagram_model['sensor_roles'] = updated_roles
            print(f"[RECONCILE] Updated sensor_roles: {len(roles)} -> {len(updated_roles)} mappings (all preserved)")
            
            # Update sensor_groups to use new CSV sensor names
            updated_groups = {}
            for group_name, sensor_list in self.sensor_groups.items():
                updated_sensor_list = []
                for old_sensor in sensor_list:
                    if old_sensor in user_mappings:
                        # Remap to new CSV name
                        updated_sensor_list.append(user_mappings[old_sensor])
                        print(f"[RECONCILE] Group '{group_name}': {old_sensor} -> {user_mappings[old_sensor]}")
                    elif old_sensor in matched:
                        # Keep matched sensors
                        updated_sensor_list.append(old_sensor)
                    else:
                        # Sensor was not matched - PRESERVE it (may exist under different header)
                        updated_sensor_list.append(old_sensor)
                        print(f"[RECONCILE] Group '{group_name}': PRESERVED {old_sensor}")
                updated_groups[group_name] = updated_sensor_list
            self.sensor_groups = updated_groups
            print(f"[RECONCILE] Updated sensor_groups (all mappings preserved)")
            
            self.csv_data = new_csv_data
            self._invalidate_filtered_cache()
            # Preserve original config list if not already set
            if not self.original_config_sensor_list:
                self.original_config_sensor_list = list(self.config_sensor_list)
            # Sanitize original config list to remove any Unnamed columns
            self.original_config_sensor_list = self._sanitize_sensor_list(self.original_config_sensor_list)
            # Build mapping from original config labels to new CSV labels (exclude Unnamed)
            mapping = {}
            for label in self.original_config_sensor_list:
                # Skip Unnamed columns in mapping
                if label.startswith('Unnamed:') or not label:
                    continue
                if label in matched:
                    mapping[label] = label
                elif label in user_mappings:
                    mapping[label] = user_mappings[label]
                else:
                    mapping[label] = None
            self.config_label_mapping = mapping
            # Update current config sensor list to the new CSV headers (already sanitized)
            self.config_sensor_list = new_sensor_list
            self.diagram_model_changed.emit()
            self.data_changed.emit()

    def load_session(self, file_path):
        """Loads a .json session file with specified UTF-8 encoding."""
        try:
            self._reset_state()
            self.config_path = file_path
            with open(file_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            self.mappings = session_data.get('mappings', {})
            # --- UPDATED: Now loads sensor groups from the config file ---
            self.sensor_groups = session_data.get('sensorGroups', {})
            # Load group states (expansion states)
            self.group_states = session_data.get('groupStates', {})
            # Load sensor ranges
            self.sensor_ranges = session_data.get('sensorRanges', {})
            # Load graph sensors (which sensors are checked for graphing)
            self.graph_sensors = set(session_data.get('graphSensors', []))
            # Load rated inputs
            self.rated_inputs = session_data.get('ratedInputs', {
                'm_dot_rated_lbhr': None,
                'hz_rated': None,
                'disp_ft3': None,
                'rated_evap_temp_f': None,
                'rated_return_gas_temp_f': None,
            })

            # Load diagram model - preserve existing structure
            default_diagram_model = {
                "components": {},
                "pipes": {},
                "sensor_roles": {},
                "custom_sensors": {},
                "sensor_boxes": {}  # Renamed from other_sensors_boxes
            }
            self.diagram_model = session_data.get('diagramModel', default_diagram_model)
            
            # Ensure all required fields exist and are dictionaries
            if 'sensor_roles' not in self.diagram_model or not isinstance(self.diagram_model['sensor_roles'], dict):
                self.diagram_model['sensor_roles'] = {}
            if 'custom_sensors' not in self.diagram_model or not isinstance(self.diagram_model['custom_sensors'], dict):
                self.diagram_model['custom_sensors'] = {}
            if 'sensor_boxes' not in self.diagram_model or not isinstance(self.diagram_model['sensor_boxes'], dict):
                self.diagram_model['sensor_boxes'] = {}
            if 'role_dot_labels' not in self.diagram_model or not isinstance(self.diagram_model['role_dot_labels'], dict):
                self.diagram_model['role_dot_labels'] = {}
            if 'components' not in self.diagram_model or not isinstance(self.diagram_model['components'], dict):
                self.diagram_model['components'] = {}
            if 'pipes' not in self.diagram_model or not isinstance(self.diagram_model['pipes'], dict):
                self.diagram_model['pipes'] = {}

            # Clear old sensor mappings when loading new system
            # Keep only the new smart sensor system mappings (sensor_roles)
            sensor_roles = self.diagram_model.get('sensor_roles', {})
            if sensor_roles:
                print(f"[LOAD] Found {len(sensor_roles)} smart sensor mappings")
                # Debug: Print the first few mappings
                for i, (role_key, sensor_name) in enumerate(sensor_roles.items()):
                    if i < 3:  # Show first 3 mappings
                        print(f"[LOAD]   {role_key} -> {sensor_name}")
                    elif i == 3:
                        print(f"[LOAD]   ... and {len(sensor_roles) - 3} more mappings")
                        break
            else:
                print("[LOAD] No smart sensor mappings found - starting fresh")
            
            # Migrate old Sensor.*.inlet role keys to Sensor.*.measurement
            if sensor_roles:
                migrated = {}
                migration_count = 0
                for key, val in list(sensor_roles.items()):
                    if key.startswith('Sensor.') and key.endswith('.inlet'):
                        parts = key.split('.')
                        if len(parts) == 3:
                            comp_id = parts[1]
                            comp = self.diagram_model.get('components', {}).get(comp_id, {})
                            if comp.get('type') == 'Sensor':
                                new_key = f"Sensor.{comp_id}.measurement"
                                migrated[new_key] = val
                                migration_count += 1
                                print(f"[MIGRATE] {key} -> {new_key}")
                                continue
                    migrated[key] = val
                if migration_count > 0:
                    self.diagram_model['sensor_roles'] = migrated
                    print(f"[MIGRATE] Migrated {migration_count} Sensor role key(s) from inlet to measurement")

            # Migrate legacy column-name anomalies to clean canonical names:
            #   T_1c-rh  → T_1b-rh   (Right coil-inlet key was misnamed)
            #   T_2a-ctr → T_2a-CTR  (Center coil-outlet abbreviation now uppercase)
            _migrate_sensor_role_keys(self.diagram_model)

            # Clear old legacy mappings to avoid confusion
            old_mappings_count = len(self.mappings)
            if old_mappings_count > 0:
                print(f"[LOAD] Clearing {old_mappings_count} old legacy mappings")
                self.mappings = {}  # Clear old mappings

            csv_data_obj = session_data.get('csvData')
            if csv_data_obj and 'headers' in csv_data_obj:
                self.config_sensor_list = csv_data_obj.get('headers', [])
            else:
                self.config_sensor_list = session_data.get('csvHeaders', [])

            # Normalize headers: drop only the Timestamp header, not an arbitrary first column
            if self.config_sensor_list:
                if len(self.config_sensor_list) > 0 and self.config_sensor_list[0] == 'Timestamp':
                    self.config_sensor_list = self.config_sensor_list[1:]
                else:
                    self.config_sensor_list = [h for h in self.config_sensor_list if h != 'Timestamp']
            
            # Sanitize: Remove Unnamed columns from config sensor list
            self.config_sensor_list = self._sanitize_sensor_list(self.config_sensor_list)

            # Always ensure a usable DataFrame exists even if csvPath is present but unreachable
            # This allows sessions to open immediately after saving
            if self.csv_data is None and self.config_sensor_list:
                self.csv_data = pd.DataFrame(columns=['Timestamp'] + self.config_sensor_list)

            # Try to load from imagePath first (highest quality)
            image_path = session_data.get('imagePath')
            if image_path:
                import os
                if os.path.exists(image_path):
                    self.image_pixmap = QPixmap(image_path)
                    print(f"Loaded high-quality image from: {image_path}")
            
            # Fallback to base64 if no file path or file not found
            if not self.image_pixmap or self.image_pixmap.isNull():
                image_data_base64 = session_data.get('imageData')
                if image_data_base64:
                    try:
                        header, encoded = image_data_base64.split(",", 1)
                        image_bytes = base64.b64decode(encoded)
                        pixmap = QPixmap()
                        pixmap.loadFromData(image_bytes, format='PNG')  # Force PNG for best quality
                        if not pixmap.isNull():
                            pixmap.setDevicePixelRatio(1.0)
                        self.image_pixmap = pixmap
                        print("Loaded image from base64 (compressed)")
                    except Exception as e:
                        print(f"Error decoding base64 image data: {e}")

            if self.config_sensor_list and not session_data.get('csvPath'):
                self.csv_data = pd.DataFrame(columns=['Timestamp'] + self.config_sensor_list)
            
            # Preserve original config list and initialize identity mapping for export
            self.original_config_sensor_list = list(self.config_sensor_list)
            # Sanitize original config list as well
            self.original_config_sensor_list = self._sanitize_sensor_list(self.original_config_sensor_list)
            # Build mapping only for valid (non-Unnamed) sensors
            self.config_label_mapping = {label: label for label in self.original_config_sensor_list}

            # Load snapshots if present
            if 'snapshots' in session_data:
                self.snapshot_manager.from_dict(session_data['snapshots'])
                print(f"[LOAD_SESSION] Loaded {len(self.snapshot_manager.snapshots)} snapshots")

            # If CSV is already loaded, reconcile sensor names
            if self.csv_data is not None and not self.csv_data.empty:
                current_csv_sensors = [col for col in self.csv_data.columns if col != 'Timestamp']
                if current_csv_sensors and self.config_sensor_list:
                    print(f"[LOAD_SESSION] CSV already loaded. Checking for sensor name differences...")
                    self.reconcile_csv(self.csv_data, current_csv_sensors)
                    return True  # reconcile_csv emits signals

            # Don't automatically load CSV - let user load it manually

            self.diagram_model_changed.emit()
            self.data_changed.emit()
            self.snapshots_changed.emit()
            return True
        except Exception as e:
            print(f"Error loading session file: {e}")
            return False

    # --- NEW METHODS FOR GROUP MANAGEMENT ---
    def create_group(self, group_name, sensor_names):
        """Creates a new group or adds sensors to an existing one."""
        if group_name not in self.sensor_groups:
            self.sensor_groups[group_name] = []
        
        # Remove sensors from any other group they might be in
        for name in sensor_names:
            for g_name, g_list in self.sensor_groups.items():
                if name in g_list:
                    g_list.remove(name)

        # Add sensors to the new group
        self.sensor_groups[group_name].extend(sensor_names)
        self.data_changed.emit()

    def rename_group(self, old_name, new_name):
        """Renames an existing sensor group."""
        if old_name in self.sensor_groups and new_name not in self.sensor_groups:
            self.sensor_groups[new_name] = self.sensor_groups.pop(old_name)
            self.data_changed.emit()
    
    def delete_group(self, group_name):
        """Deletes a sensor group. Sensors in the group will become ungrouped."""
        if group_name in self.sensor_groups:
            del self.sensor_groups[group_name]
            self.data_changed.emit()
    
    def set_sensor_ranges(self, ranges_dict):
        """Sets ranges for multiple sensors at once."""
        self.sensor_ranges = ranges_dict
        self.data_changed.emit()
    
    def get_sensor_ranges(self):
        """Returns the current sensor ranges."""
        return self.sensor_ranges
    
    def get_sensor_range(self, sensor_name):
        """Returns the range for a specific sensor, or None if not set."""
        return self.sensor_ranges.get(sensor_name, None)

    def get_sensor_status(self, sensor_name, role_key=None):
        """
        Get status of a sensor for color coding.

        Returns one of:
        - 'unmapped': Sensor not mapped to any role
        - 'no_range': Sensor mapped but no range set
        - 'in_range': Sensor value within defined range
        - 'out_of_range': Sensor value outside defined range

        Args:
            sensor_name: The sensor name (if already known)
            role_key: The role key to lookup sensor (if sensor_name not provided)
        """
        # If role_key provided, get the mapped sensor
        if role_key and not sensor_name:
            sensor_name = self.get_mapped_sensor_for_role(role_key)

        # Unmapped check
        if not sensor_name:
            return 'unmapped'

        # Check if range exists
        sensor_range = self.sensor_ranges.get(sensor_name)
        if not sensor_range:
            return 'no_range'

        # Get current sensor value
        sensor_value = self.get_sensor_value(sensor_name)
        if sensor_value is None:
            return 'no_range'  # No data to compare

        # Check if value is within range
        min_val = sensor_range.get('min')
        max_val = sensor_range.get('max')

        if min_val is not None and max_val is not None:
            if min_val <= sensor_value <= max_val:
                return 'in_range'
            else:
                return 'out_of_range'

        return 'no_range'

    def move_sensors_to_group(self, target_group_name, sensor_names):
        """Moves a list of sensors to a specified group."""
        # Remove sensors from their old groups
        for name in sensor_names:
            for g_list in self.sensor_groups.values():
                if name in g_list:
                    g_list.remove(name)
        
        # Add them to the new group
        if target_group_name in self.sensor_groups:
            self.sensor_groups[target_group_name].extend(sensor_names)
        
        self.data_changed.emit()


    # --- Unchanged methods below ---
    def load_image_from_path(self, file_path):
        self.image_path = file_path
        # Load image with high quality settings
        self.image_pixmap = QPixmap(file_path)
        if not self.image_pixmap.isNull():
            # Ensure high DPI scaling for crisp images
            self.image_pixmap.setDevicePixelRatio(1.0)
        self.data_changed.emit()

    def update_mapping(self, sensor_name, x, y):
        if sensor_name not in self.mappings:
            self.mappings[sensor_name] = {}
        self.mappings[sensor_name]['x'] = x
        self.mappings[sensor_name]['y'] = y
    
    def update_mapping_and_notify(self, sensor_name, x, y):
        self.update_mapping(sensor_name, x, y)
        self.data_changed.emit()

    def toggle_sensor_selection(self, sensor_name, multi_select=False):
        """
        Toggle sensor selection.
        
        Args:
            sensor_name: Name of the sensor to toggle
            multi_select: If True, adds/removes from selection. If False, replaces selection.
        """
        if multi_select:
            # Multi-select mode: toggle individual sensor
            if sensor_name in self.selected_sensors:
                self.selected_sensors.discard(sensor_name)
            else:
                self.selected_sensors.add(sensor_name)
        else:
            # Single-select mode: replace selection
            if sensor_name in self.selected_sensors:
                self.selected_sensors.clear()
            else:
                self.selected_sensors.clear()
                self.selected_sensors.add(sensor_name)
        self.data_changed.emit()

    def set_sensor_selected(self, sensor_name, is_selected):
        if is_selected:
            self.selected_sensors.clear()
            self.selected_sensors.add(sensor_name)
        else:
            self.selected_sensors.discard(sensor_name)

    def set_sensor_graphed(self, sensor_name, is_graphed):
        if is_graphed:
            self.graph_sensors.add(sensor_name)
        else:
            self.graph_sensors.discard(sensor_name)

    def get_sensor_list(self):
        if self.csv_data is not None:
            return self.csv_data.columns.tolist()[1:]
        elif self.config_sensor_list:
            return self.config_sensor_list
        expected = self.get_expected_sensor_rows()
        if expected:
            return [row['default_label'] for row in expected]
        return []

    def get_expected_sensor_rows(self, include_disabled: bool = False) -> list:
        """Return the diagram's expected sensor dots as table-ready rows.

        These rows exist before any CSV is loaded.  They are the lab-facing
        "planned sensors" generated from the process diagram, with any mapped
        CSV/lab label overlaid when old data is loaded.
        """
        try:
            from sensor_canonical import resolve_canonical_from_role_key
        except Exception:
            return []

        if not (self.diagram_model.get('components') or self.diagram_model.get('custom_sensors')
                or self.diagram_model.get('sensor_boxes')):
            return []

        try:
            self.populate_sensor_points()
        except Exception:
            pass

        roles = self.diagram_model.get('sensor_roles') or {}
        rows = []
        seen = set()
        for role_key in self._enumerate_diagram_role_keys():
            if role_key in seen:
                continue
            seen.add(role_key)
            enabled = self.is_sensor_point_enabled(role_key)
            if not include_disabled and not enabled:
                continue
            resolved = resolve_canonical_from_role_key(self.diagram_model, role_key)
            if not resolved:
                continue
            canonical, human_label = resolved
            default_label = self._default_lab_label(canonical, human_label)
            mapped_label = roles.get(role_key)
            rows.append({
                "role_key": role_key,
                "canonical": canonical,
                "default_label": default_label,
                "human_label": human_label or default_label,
                "lab_label": mapped_label or default_label,
                "mapped_label": mapped_label,
                "group": self._group_for_canonical(canonical),
                "enabled": enabled,
            })

        rows.sort(key=lambda r: (r["group"], self._sensor_sort_key(r["canonical"], r["default_label"])))
        return rows

    def get_expected_sensor_groups(self, include_disabled: bool = False) -> dict:
        groups = {}
        for row in self.get_expected_sensor_rows(include_disabled=include_disabled):
            groups.setdefault(row["group"], []).append(row["default_label"])
        return groups

    @staticmethod
    def _default_lab_label(canonical: str, human_label: str) -> str:
        """Human-facing default label the lab can type into the DAQ."""
        label = (human_label or canonical or '').strip()
        # Keep generated labels short enough for DAQ headers and PDF tables.
        for suffix in (" Temp", " Temperature"):
            if label.endswith(suffix):
                label = label[:-len(suffix)]
        return label or canonical

    @staticmethod
    def _group_for_canonical(canonical: str) -> str:
        if canonical.startswith(("T_amb", "T_wall", "T_ceil")):
            return "Ambient & Walls"
        if canonical.startswith(("W_", "A_", "V_", "t_", "f_", "m_", "gpm", "rpm")):
            return "Electrical & System"
        if canonical.startswith("T_air.disc."):
            return "Air - Discharge"
        if canonical.startswith("T_air.sec."):
            return "Air - Secondary"
        if canonical.startswith("T_air.ret."):
            return "Air - Return"
        if canonical.startswith("T_air.fan_in."):
            return "Evap Fan Air In"
        if canonical.startswith("T_air.fan_off."):
            return "Evap Fan Air Off"
        if canonical.startswith("T_air.cond_in."):
            return "Condenser Air In"
        if canonical.startswith("T_air.cond_out."):
            return "Condenser Air Out"
        if canonical.startswith("T_prod."):
            return "Product Simulators"
        if canonical.startswith("T_door."):
            return "Doors"
        if canonical.startswith("T_mull."):
            return "Mullions"
        if canonical.startswith(("P_suc", "P_disc", "T_suc", "T_disc")):
            return "Compressor"
        if canonical.startswith(("T_cond", "T_w")):
            return "Condenser"
        if canonical.startswith("T_txv."):
            parts = canonical.split(".")
            return f"TXV - {parts[1].upper()}" if len(parts) > 1 else "TXV"
        if canonical.startswith("T_dist."):
            parts = canonical.split(".")
            return f"Distributor - {parts[1].upper()}" if len(parts) > 1 else "Distributor"
        if canonical.startswith("T_coil."):
            parts = canonical.split(".")
            return f"Coil - {parts[1].upper()}" if len(parts) > 1 else "Coil"
        if canonical.startswith("calc.SH"):
            return "Calculated - Superheat"
        if canonical.startswith("calc.SC"):
            return "Calculated - Subcooling"
        return "Other Sensors"

    @staticmethod
    def _sensor_sort_key(canonical: str, label: str):
        import re
        parts = re.split(r'(\d+)', canonical or label or '')
        return [int(p) if p.isdigit() else p.lower() for p in parts]
    
    def update_refrigerant(self, refrigerant: str):
        """Updates the refrigerant type and notifies listeners."""
        self.refrigerant = refrigerant
        self.data_changed.emit()
    
    def update_aggregation_method(self, method: str):
        """Updates the aggregation method for calculations and notifies listeners."""
        self.aggregation_method = method
        self.data_changed.emit()
    
    def get_current_dataframe(self):
        """Returns the currently filtered dataframe based on time range settings."""
        return self.get_filtered_data()
    
    def get_sensor_number(self, sensor_name):
        """Returns the sequential number (1-based) for a sensor based on the full sensor list."""
        sensor_list = self.get_sensor_list()
        if sensor_name in sensor_list:
            return sensor_list.index(sensor_name) + 1
        return None
    
    def set_time_range(self, time_range):
        """Sets the time range filter for data display."""
        self.time_range = time_range
        self._invalidate_filtered_cache()
        self.data_changed.emit()
    
    def set_custom_time_range(self, start_timestamp, end_timestamp):
        """Sets a custom time range and switches to 'Custom' mode."""
        # DIAGNOSTIC: Log the input timestamps
        log_conversion(
            stage="SET_CUSTOM_RANGE_INPUT",
            description="Received start_timestamp for custom range",
            value=start_timestamp,
            timezone=getattr(start_timestamp, 'tzinfo', None),
            is_naive=getattr(start_timestamp, 'tzinfo', None) is None
        )
        log_conversion(
            stage="SET_CUSTOM_RANGE_INPUT",
            description="Received end_timestamp for custom range",
            value=end_timestamp,
            timezone=getattr(end_timestamp, 'tzinfo', None),
            is_naive=getattr(end_timestamp, 'tzinfo', None) is None
        )
        
        self.custom_time_range = {
            'start': start_timestamp,
            'end': end_timestamp
        }
        self.time_range = 'Custom'
        
        # DIAGNOSTIC: Log what was stored
        print(f"[SET_CUSTOM_RANGE] Stored custom range:")
        print(f"  Start: {self.custom_time_range['start']}")
        print(f"  End: {self.custom_time_range['end']}")
        print(f"  Duration: {self.custom_time_range['end'] - self.custom_time_range['start']}")
        
        # Also clear multi-range when setting single range (backward compatibility)
        self.custom_time_ranges = None
        
        self._invalidate_filtered_cache()
        self.data_changed.emit()
    
    def set_multi_range_filter(self, keep_ranges, delete_ranges):
        """Sets multiple time ranges for keep/delete filtering."""
        # Store ranges as list of tuples: [(start_dt, end_dt), ...]
        self.custom_time_ranges = {
            'keep': keep_ranges,
            'delete': delete_ranges
        }
        self.time_range = 'Custom'
        
        # Clear single-range filter when using multi-range
        self.custom_time_range = None
        
        self._invalidate_filtered_cache()
        self.data_changed.emit()
    
    def get_custom_time_range(self):
        """Returns the current custom time range."""
        return self.custom_time_range
    
    def set_value_aggregation(self, aggregation):
        """Sets the value aggregation method (Average, Maximum, Minimum)."""
        self.value_aggregation = aggregation
        # Note: Aggregation doesn't affect filtered data, only how values are calculated from it
        # So we don't need to invalidate filtered cache here
        self.data_changed.emit()
    
    def _invalidate_filtered_cache(self):
        """Invalidate the cached filtered data."""
        self._cached_filtered_data = None
        self._cache_key = None

    def _apply_delete_ranges(self, df):
        """Apply custom_time_ranges delete ranges to a dataframe. Returns filtered df."""
        if df is None or df.empty or 'Timestamp' not in df.columns:
            return df
        delete_ranges = (self.custom_time_ranges or {}).get('delete', [])
        if not delete_ranges:
            return df
        try:
            if not is_datetime64_any_dtype(df['Timestamp']):
                df = df.copy()
                df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
            mask = pd.Series([True] * len(df), index=df.index)
            for start_time, end_time in delete_ranges:
                start_dt = pd.to_datetime(start_time)
                end_dt = pd.to_datetime(end_time)
                mask &= ~((df['Timestamp'] >= start_dt) & (df['Timestamp'] <= end_dt))
            return df[mask]
        except Exception:
            return df
    
    def _get_cache_key(self):
        """Generate a cache key based on current filter settings."""
        # Create a hashable key from filter settings
        custom_range_key = None
        if self.custom_time_range:
            custom_range_key = (str(self.custom_time_range.get('start')), str(self.custom_time_range.get('end')))
        custom_ranges_key = None
        if self.custom_time_ranges:
            keep_key = tuple(self.custom_time_ranges.get('keep', []))
            delete_key = tuple(self.custom_time_ranges.get('delete', []))
            custom_ranges_key = (keep_key, delete_key)

        return (self.time_range, custom_range_key, custom_ranges_key)
    
    def _sanitize_columns(self, df):
        """
        Remove Unnamed columns and empty columns from a DataFrame.
        
        Args:
            df: pandas DataFrame to sanitize
            
        Returns:
            Cleaned DataFrame with Unnamed and empty columns removed
        """
        if df is None or df.empty:
            return df
        
        columns_to_drop = []
        for col in df.columns:
            # Drop columns starting with "Unnamed:" (created by pandas for trailing commas)
            if col.startswith('Unnamed:') or col == '':
                columns_to_drop.append(col)
            elif col != 'Timestamp':
                # Optionally drop columns that are completely empty (all NaN)
                if df[col].isna().all():
                    columns_to_drop.append(col)
        
        if columns_to_drop:
            print(f"[SANITIZE] Dropping {len(columns_to_drop)} invalid columns: {columns_to_drop[:5]}{'...' if len(columns_to_drop) > 5 else ''}")
            df = df.drop(columns=columns_to_drop)
        
        return df
    
    def _sanitize_sensor_list(self, sensor_list):
        """
        Remove Unnamed sensors and empty names from a sensor list.
        
        Args:
            sensor_list: List of sensor names to sanitize
            
        Returns:
            Cleaned list with Unnamed and empty sensors removed
        """
        if not sensor_list:
            return sensor_list
        
        cleaned = [s for s in sensor_list if s and not s.startswith('Unnamed:')]
        
        if len(cleaned) != len(sensor_list):
            removed = len(sensor_list) - len(cleaned)
            print(f"[SANITIZE] Removed {removed} invalid sensors from list (Unnamed/empty)")
        
        return cleaned
    
    def get_filtered_data(self):
        """
        Returns the CSV data filtered by the current time range.
        Returns the full dataframe if no valid timestamp column or if 'All Data' is selected.
        Uses caching to avoid recalculating filtered data when filter settings haven't changed.
        """
        if self.csv_data is None or self.csv_data.empty:
            return None
        
        # Check if we have a valid cache
        current_cache_key = self._get_cache_key()
        if self._cached_filtered_data is not None and self._cache_key == current_cache_key:
            return self._cached_filtered_data.copy()
        
        # Cache miss - calculate filtered data
        # If "All Data" is selected, return everything (as copy to avoid caching issues)
        if self.time_range == 'All Data':
            filtered_data = self.csv_data.copy()
            filtered_data = self._apply_delete_ranges(filtered_data)
            self._cached_filtered_data = filtered_data.copy()
            self._cache_key = current_cache_key
            return filtered_data
        
        # If "Custom" is selected, use custom time range(s) if available
        if self.time_range == 'Custom':
            # Check for multi-range filter first
            if self.custom_time_ranges and 'Timestamp' in self.csv_data.columns:
                try:
                    df = self.csv_data.copy()
                    
                    if not is_datetime64_any_dtype(df['Timestamp']):
                        df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
                    
                    # Start with all data
                    filtered_mask = pd.Series([False] * len(df), index=df.index)
                    
                    # Apply keep ranges (union - include data in ANY keep range)
                    keep_ranges = self.custom_time_ranges.get('keep', [])
                    if keep_ranges:
                        keep_mask = pd.Series([False] * len(df), index=df.index)
                        for start_time, end_time in keep_ranges:
                            start_dt = pd.to_datetime(start_time)
                            end_dt = pd.to_datetime(end_time)
                            keep_mask |= (df['Timestamp'] >= start_dt) & (df['Timestamp'] <= end_dt)
                        filtered_mask = keep_mask
                    else:
                        # If no keep ranges, start with all data
                        filtered_mask = pd.Series([True] * len(df), index=df.index)
                    
                    # Apply delete ranges (exclude data in ANY delete range)
                    delete_ranges = self.custom_time_ranges.get('delete', [])
                    if delete_ranges:
                        for start_time, end_time in delete_ranges:
                            start_dt = pd.to_datetime(start_time)
                            end_dt = pd.to_datetime(end_time)
                            filtered_mask &= ~((df['Timestamp'] >= start_dt) & (df['Timestamp'] <= end_dt))

                    filtered_df = df[filtered_mask]
                    self._cached_filtered_data = filtered_df.copy()
                    self._cache_key = current_cache_key
                    return filtered_df
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    # Fall through to return all data on error
            
            # Fall back to single-range filter (backward compatibility)
            if self.custom_time_range and 'Timestamp' in self.csv_data.columns:
                try:
                    df = self.csv_data.copy()
                    
                    if not is_datetime64_any_dtype(df['Timestamp']):
                        df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
                    
                    # Convert custom range to pandas timestamps
                    start_time = pd.to_datetime(self.custom_time_range['start'])
                    end_time = pd.to_datetime(self.custom_time_range['end'])
                    
                    # Apply the filter
                    filtered_df = df[(df['Timestamp'] >= start_time) & (df['Timestamp'] <= end_time)]
                    self._cached_filtered_data = filtered_df.copy()
                    self._cache_key = current_cache_key
                    return filtered_df
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    # Fall through to return all data on error
            
            # No custom range or no Timestamp column - return all data
            filtered_data = self.csv_data.copy()
            self._cached_filtered_data = filtered_data.copy()
            self._cache_key = current_cache_key
            return filtered_data
        
        # Check if we have a Timestamp column
        if 'Timestamp' not in self.csv_data.columns:
            filtered_data = self.csv_data.copy()
            self._cached_filtered_data = filtered_data.copy()
            self._cache_key = current_cache_key
            return filtered_data
        
        try:
            df = self.csv_data.copy()
            
            # Ensure Timestamp column is datetime type
            if not is_datetime64_any_dtype(df['Timestamp']):
                df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
                # Check if conversion was successful
                if df['Timestamp'].isna().all():
                    filtered_data = self.csv_data.copy()
                    self._cached_filtered_data = filtered_data.copy()
                    self._cache_key = current_cache_key
                    return filtered_data
            
            # Get the time range mapping
            time_ranges = {
                # New UI options
                'Last 30 min':  0.5,
                'Last 1 hr':    1,
                'Last 2 hr':    2,
                'Last 4 hr':    4,
                'Last 8 hr':    8,
                'Last 16 hr':   16,
                'Last 24 hr':   24,
                'Last 48 hr':   48,
                # Legacy options — kept for compatibility with saved sessions
                '1 Hour':  1,
                '8 Hours': 8,
                '24 Hours': 24,
                '48 Hours': 48,
                '3 Hours':  3,
                '16 Hours': 16,
            }
            
            hours = time_ranges.get(self.time_range)
            # Also accept plain numeric strings from the new UI (e.g. '0.25', '1', '8')
            if hours is None:
                try:
                    hours = float(self.time_range)
                except (ValueError, TypeError):
                    pass
            if hours is None:
                filtered_data = self.csv_data.copy()
                self._cached_filtered_data = filtered_data.copy()
                self._cache_key = current_cache_key
                return filtered_data
            
            # Get the last timestamp and calculate the cutoff time
            last_timestamp = df['Timestamp'].max()
            cutoff_time = last_timestamp - pd.Timedelta(hours=hours)
            
            # Filter the data
            filtered_df = df[df['Timestamp'] >= cutoff_time].copy()
            
            if len(filtered_df) == 0:
                filtered_data = self.csv_data.copy()
                self._cached_filtered_data = filtered_data.copy()
                self._cache_key = current_cache_key
                return filtered_data
            
            # Apply delete ranges (defrost removal) regardless of time range
            filtered_df = self._apply_delete_ranges(filtered_df)
            self._cached_filtered_data = filtered_df.copy()
            self._cache_key = current_cache_key
            return filtered_df
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            filtered_data = self.csv_data.copy()
            self._cached_filtered_data = filtered_data.copy()
            self._cache_key = current_cache_key
            return filtered_data

    def get_sensor_value(self, sensor_name):
        """Return the average value for a sensor over the selected time range."""
        filtered_data = self.get_filtered_data()
        
        if filtered_data is not None and sensor_name in filtered_data.columns:
            sensor_data = filtered_data[sensor_name].dropna()
            
            if not sensor_data.empty:
                return sensor_data.mean()
        
        return None

    
    
    def get_data_info(self):
        """
        Returns comprehensive information about the current data state and filtering.
        Used for debugging and displaying data information to users.
        """
        info = {
            'csv_loaded': self.csv_data is not None,
            'csv_path': None,
            'total_rows': 0,
            'filtered_rows': 0,
            'total_columns': 0,
            'time_range': self.time_range,
            'timestamp_range': None,
            'filtered_timestamp_range': None,
            'row_indices': None,
            'has_timestamps': False
        }
        
        if self.csv_data is None:
            return info
        
        # Basic CSV info
        info['total_rows'] = len(self.csv_data)
        info['total_columns'] = len(self.csv_data.columns) - 1  # Exclude timestamp column
        
        # Get filtered data
        filtered_data = self.get_filtered_data()
        if filtered_data is not None:
            info['filtered_rows'] = len(filtered_data)
            
            # Get row indices being used
            if not filtered_data.empty:
                info['row_indices'] = f"{filtered_data.index[0] + 2}-{filtered_data.index[-1] + 2}"  # +2 for Excel-style (1-indexed + header)
        
        # Timestamp information
        if 'Timestamp' in self.csv_data.columns:
            info['has_timestamps'] = True
            try:
                # Full data timestamp range
                timestamps = pd.to_datetime(self.csv_data['Timestamp'])
                info['timestamp_range'] = {
                    'start': timestamps.min(),
                    'end': timestamps.max()
                }
                
                # Filtered data timestamp range
                if filtered_data is not None and not filtered_data.empty:
                    filtered_timestamps = pd.to_datetime(filtered_data['Timestamp'])
                    info['filtered_timestamp_range'] = {
                        'start': filtered_timestamps.min(),
                        'end': filtered_timestamps.max()
                    }
            except Exception as e:
                print(f"Error parsing timestamps: {e}")
        
        return info
    
    def get_sensor_detailed_info(self, sensor_name):
        """
        Returns detailed information about a specific sensor including the data being used.
        """
        info = {
            'sensor_name': sensor_name,
            'sensor_number': self.get_sensor_number(sensor_name),
            'displayed_value': None,
            'aggregation_method': self.value_aggregation,
            'data_points': 0,
            'row_range': None,
            'column_letter': None,
            'min_value': None,
            'max_value': None,
            'avg_value': None
        }
        
        filtered_data = self.get_filtered_data()
        if filtered_data is None or sensor_name not in filtered_data.columns:
            return info
        
        sensor_data = filtered_data[sensor_name].dropna()
        if sensor_data.empty:
            return info
        
        # Get column letter (Excel-style)
        sensor_list = self.get_sensor_list()
        if sensor_name in sensor_list:
            col_index = sensor_list.index(sensor_name) + 1  # +1 because timestamp is column A
            info['column_letter'] = self._index_to_excel_column(col_index)
        
        # Calculate statistics
        info['min_value'] = sensor_data.min()
        info['max_value'] = sensor_data.max()
        info['avg_value'] = sensor_data.mean()
        info['data_points'] = len(sensor_data)
        
        # Get displayed value based on aggregation method
        info['displayed_value'] = self.get_sensor_value(sensor_name)
        
        # Get row range
        first_row = sensor_data.index[0] + 2  # +2 for Excel-style (1-indexed + header)
        last_row = sensor_data.index[-1] + 2
        info['row_range'] = f"{first_row}-{last_row}"
        
        return info
    
    def save_session(self, file_path):
        """
        Saves the current session state to a JSON file with the same structure as the original.
        Includes high-resolution image data optimized for reasonable file size.
        """
        try:
            from datetime import datetime
            import tempfile
            
            # Prepare session data - match original JSON structure exactly
            sanitized_diagram = self._sanitize_diagram_model(self.diagram_model)
            session_data = {
                "name": os.path.splitext(os.path.basename(file_path))[0],
                "timestamp": datetime.now().isoformat() + "Z",
                "csvPath": self._get_csv_filename(),
                "csvData": self._prepare_csv_data(),
                "imagePath": self._prepare_image_data(),
                "imageData": self._prepare_image_base64(),
                "mappings": self._prepare_mappings_with_ranges(),
                "sensorGroups": self._prepare_sensor_groups(),
                "groupStates": self._prepare_group_states(),
                "sensorRanges": self.sensor_ranges,  # Save sensor ranges
                "ratedInputs": self.rated_inputs,  # Save rated inputs for volumetric efficiency calculation
                "diagramModel": sanitized_diagram,  # Save diagram designer data (sanitized)
                "graphSensors": list(self.graph_sensors),  # Save which sensors are checked for graphing
                "snapshots": self.snapshot_manager.to_dict(),  # Save snapshots
                "ui": {
                    "selectedSensors": list(self.selected_sensors),
                    "currentMode": self.current_mode,
                    "selectedTimeRange": self.time_range
                }
            }
            
            # Atomic write: write to a temp file in the same directory, then replace
            target_dir = os.path.dirname(file_path) or "."
            base_name = os.path.basename(file_path)
            tmp_path = os.path.join(target_dir, f".{base_name}.tmp")

            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)

            # Replace the target file atomically
            os.replace(tmp_path, file_path)
            
            print(f"Session saved successfully to: {file_path}")
            return True

        except Exception as e:
            print(f"Error saving session: {e}")
            return False

    def save_session_to_dict(self):
        """
        Returns the current session state as a dictionary (for undo functionality).
        """
        try:
            from datetime import datetime
            import copy

            # Prepare session data - same structure as save_session
            sanitized_diagram = self._sanitize_diagram_model(self.diagram_model)
            session_data = {
                "name": "undo_state",
                "timestamp": datetime.now().isoformat() + "Z",
                "csvPath": self._get_csv_filename(),
                "csvData": self._prepare_csv_data(),
                "imagePath": self._prepare_image_data(),
                "imageData": self._prepare_image_base64(),
                "mappings": copy.deepcopy(self._prepare_mappings_with_ranges()),
                "sensorGroups": copy.deepcopy(self._prepare_sensor_groups()),
                "groupStates": copy.deepcopy(self._prepare_group_states()),
                "sensorRanges": copy.deepcopy(self.sensor_ranges),
                "ratedInputs": copy.deepcopy(self.rated_inputs),
                "diagramModel": sanitized_diagram,
                "graphSensors": list(self.graph_sensors),
                "ui": {
                    "selectedSensors": list(self.selected_sensors),
                    "currentMode": self.current_mode,
                    "selectedTimeRange": self.time_range
                }
            }
            return session_data
        except Exception as e:
            print(f"Error creating session dictionary: {e}")
            return None

    def load_session_from_dict(self, session_data):
        """
        Loads session state from a dictionary (for undo functionality).
        """
        try:
            # Restore state from dictionary (similar to load_session but from dict instead of file)
            self.mappings = session_data.get('mappings', {})
            self.sensor_groups = session_data.get('sensorGroups', {})
            self.group_states = session_data.get('groupStates', {})
            self.sensor_ranges = session_data.get('sensorRanges', {})
            self.graph_sensors = set(session_data.get('graphSensors', []))
            self.rated_inputs = session_data.get('ratedInputs', {
                'm_dot_rated_lbhr': None,
                'hz_rated': None,
                'disp_ft3': None,
                'rated_evap_temp_f': None,
                'rated_return_gas_temp_f': None,
            })

            # Load diagram model
            default_diagram_model = {
                "components": {},
                "pipes": {},
            }
            self.diagram_model = session_data.get('diagramModel', default_diagram_model)

            # Migrate old Sensor.*.inlet role keys to Sensor.*.measurement
            sensor_roles = self.diagram_model.get('sensor_roles', {})
            if sensor_roles:
                migrated = {}
                migration_count = 0
                for key, val in list(sensor_roles.items()):
                    if key.startswith('Sensor.') and key.endswith('.inlet'):
                        parts = key.split('.')
                        if len(parts) == 3:
                            comp_id = parts[1]
                            comp = self.diagram_model.get('components', {}).get(comp_id, {})
                            if comp.get('type') == 'Sensor':
                                new_key = f"Sensor.{comp_id}.measurement"
                                migrated[new_key] = val
                                migration_count += 1
                                continue
                    migrated[key] = val
                if migration_count > 0:
                    self.diagram_model['sensor_roles'] = migrated

            # Load UI state
            ui_state = session_data.get('ui', {})
            self.selected_sensors = set(ui_state.get('selectedSensors', []))
            self.current_mode = ui_state.get('currentMode', 'Compressor On')
            self.time_range = ui_state.get('selectedTimeRange', 'All Data')

            # Emit signals to refresh UI
            self.data_changed.emit()
            self.diagram_model_changed.emit()

            print("[DATA_MANAGER] Session state restored from dictionary")
            return True
        except Exception as e:
            print(f"Error loading session from dictionary: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    def _sanitize_diagram_model(self, diagram_model):
        """Ensure all values in diagramModel are JSON-serializable (no QPointF)."""
        def to_xy_list(pos):
            try:
                if hasattr(pos, 'x') and hasattr(pos, 'y'):
                    return [pos.x(), pos.y()]
                if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                    return [float(pos[0]), float(pos[1])]
            except Exception:
                pass
            return pos

        out = {"components": {}, "pipes": {}}
        comps = diagram_model.get("components", {}) or {}
        for cid, cdata in comps.items():
            ccopy = dict(cdata)
            if 'position' in ccopy:
                ccopy['position'] = to_xy_list(ccopy['position'])
            out["components"][cid] = ccopy
        pipes = diagram_model.get("pipes", {}) or {}
        for pid, pdata in pipes.items():
            pcopy = dict(pdata)
            if 'waypoints' in pcopy and isinstance(pcopy['waypoints'], list):
                new_wps = []
                for wp in pcopy['waypoints']:
                    new_wps.append(to_xy_list(wp))
                pcopy['waypoints'] = new_wps
            out["pipes"][pid] = pcopy
        # Pass through optional properties
        if isinstance(diagram_model, dict):
            for k in diagram_model.keys():
                if k not in out:
                    out[k] = diagram_model[k]
        return out

    # === SENSOR ROLE MAPPING API ===
    # ── Canonical sensor naming + alias DB ────────────────────────────────────

    _ALIAS_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  'library', 'sensor_aliases', 'seed.json')
    _ALIAS_DB_USER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  'library', 'sensor_aliases', 'learned.json')

    def _load_alias_db(self) -> dict:
        """Combined alias DB: seed (from 7 historical configs) + learned (this
        session's confirmed mappings).  Returns canonical -> set(alias_str).
        """
        combined = {}
        for path in (self._ALIAS_DB_PATH, self._ALIAS_DB_USER):
            try:
                with open(path, encoding='utf-8') as f:
                    d = json.load(f)
                for c, names in d.items():
                    combined.setdefault(c, set()).update(names)
            except FileNotFoundError:
                pass
            except Exception as e:
                print(f"[ALIAS_DB] Load failed for {path}: {e}")
        return combined

    def _save_learned_alias(self, canonical: str, csv_name: str):
        """Append a confirmed alias to the learned DB."""
        try:
            os.makedirs(os.path.dirname(self._ALIAS_DB_USER), exist_ok=True)
            try:
                with open(self._ALIAS_DB_USER, encoding='utf-8') as f:
                    learned = json.load(f)
            except FileNotFoundError:
                learned = {}
            entry = set(learned.get(canonical, []))
            entry.add(csv_name.strip())
            learned[canonical] = sorted(entry)
            with open(self._ALIAS_DB_USER, 'w', encoding='utf-8') as f:
                json.dump(learned, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ALIAS_DB] Save failed: {e}")

    def auto_map_csv_to_canonical(self, csv_columns) -> int:
        """For each CSV column, try to find a canonical role on the current
        diagram (via alias DB exact + normalized match) and auto-map it.

        Returns count of newly mapped columns.
        """
        from sensor_canonical import (resolve_canonical_from_role_key,
                                      normalize_for_match,
                                      _canonical_from_box_label)
        if not csv_columns:
            self.last_auto_map_report = self._build_auto_map_report([], {}, {}, {})
            return 0

        aliases = self._load_alias_db()
        for row in self.get_expected_sensor_rows(include_disabled=True):
            canonical = row.get('canonical')
            if not canonical:
                continue
            aliases.setdefault(canonical, set()).update({
                row.get('default_label') or '',
                row.get('human_label') or '',
                row.get('canonical') or '',
            })
        # Build reverse index: normalized alias -> canonical
        rev_exact = {}
        rev_norm = {}
        for canonical, names in aliases.items():
            for n in names:
                rev_exact[n.strip()] = canonical
                rev_norm[normalize_for_match(n)] = canonical

        # Build canonical -> first available role_key on this diagram
        canon_to_role_keys = {}
        for rk in self._enumerate_diagram_role_keys():
            res = resolve_canonical_from_role_key(self.diagram_model, rk)
            if res:
                canon_to_role_keys.setdefault(res[0], []).append(rk)

        # Walk CSV columns
        mapped_n = 0
        already_mapped = set((self.diagram_model.get('sensor_roles') or {}).values())
        column_results = {}
        for col in csv_columns:
            if col in already_mapped:
                column_results[col] = {"status": "already_mapped"}
                continue
            box_res = _canonical_from_box_label(col)
            box_canonical = box_res[0] if box_res else None
            norm_col = normalize_for_match(col)
            unit_specific = box_canonical and (
                norm_col.startswith('u') or 'unit' in norm_col or norm_col.startswith('ps')
                or re.search(r'(?:u|unit)\d+$', norm_col)
            )
            canonical = box_canonical if unit_specific else None
            canonical = canonical or rev_exact.get(col.strip()) or rev_norm.get(norm_col)
            if not canonical:
                canonical = box_canonical
            if not canonical:
                column_results[col] = {"status": "unknown"}
                continue
            target_keys = canon_to_role_keys.get(canonical, [])
            if not target_keys and canonical.startswith('T_prod.'):
                created_key = self._ensure_product_sensor_dot(canonical)
                if created_key:
                    target_keys = [created_key]
                    canon_to_role_keys[canonical] = target_keys
            if not target_keys:
                column_results[col] = {
                    "status": "known_but_no_role",
                    "canonical": canonical,
                }
                continue
            # Find a role_key that's not already mapped
            current = self.diagram_model.get('sensor_roles') or {}
            free_key = next((k for k in target_keys if k not in current), None)
            if not free_key:
                column_results[col] = {
                    "status": "known_but_filled",
                    "canonical": canonical,
                    "role_keys": target_keys,
                }
                continue
            self.map_sensor_to_role(free_key, col)
            already_mapped.add(col)
            mapped_n += 1
            column_results[col] = {
                "status": "mapped",
                "canonical": canonical,
                "role_key": free_key,
            }

        self.last_auto_map_report = self._build_auto_map_report(
            csv_columns, canon_to_role_keys, column_results, aliases)
        print(f"[AUTO_MAP] Auto-mapped {mapped_n} CSV columns from alias DB "
              f"(of {len(csv_columns)} columns, {len(canon_to_role_keys)} canonical roles on diagram)")
        gaps = self.get_mapping_gaps()
        if gaps.get('unmapped_csv_count') or gaps.get('unmapped_expected_count'):
            print("[AUTO_MAP] Mapping gaps: "
                  f"{gaps.get('unmapped_csv_count', 0)} CSV column(s) unknown, "
                  f"{gaps.get('unmapped_expected_count', 0)} expected sensor dot(s) unmapped, "
                  f"{gaps.get('known_but_no_role_count', 0)} known alias(es) with no dot on this diagram")
        if mapped_n:
            self.diagram_model_changed.emit()
        return mapped_n

    def _ensure_product_sensor_dot(self, canonical: str) -> str | None:
        """Create a missing product-sim custom dot from its canonical ID.

        Generated diagrams include the common shelf anchors. CSVs can contain
        additional physical positions (for example LE20). Add only the positions
        that actually appear in the loaded file instead of pre-rendering every
        historical possibility.
        """
        if not canonical or not canonical.startswith('T_prod.'):
            return None
        custom = self.diagram_model.setdefault('custom_sensors', {})
        if canonical in custom:
            return canonical

        parts = canonical.split('.')
        if len(parts) != 4:
            return None
        _, row_id, col_id, face = parts

        comps = self.diagram_model.get('components') or {}
        shelf_items = []
        for cid, comp in comps.items():
            if not str(cid).startswith('deco_shelf_'):
                continue
            pos = comp.get('position') or [0, 0]
            size = comp.get('size') or {}
            m = re.match(r'^deco_shelf_(\d+)_(\d+)$', str(cid))
            if not m:
                continue
            shelf_items.append({
                'col': int(m.group(1)),
                'row': int(m.group(2)),
                'x': float(pos[0]),
                'y': float(pos[1]),
                'w': float(size.get('width') or 0),
                'h': float(size.get('height') or 0),
            })
        if not shelf_items:
            return None

        rows = sorted({s['row'] for s in shelf_items})
        cols = sorted({s['col'] for s in shelf_items})
        if not rows or not cols:
            return None

        row_map = {'top': 0, 'btm': rows[-1]}
        for idx in range(1, rows[-1]):
            row_map[f'r{idx + 1}'] = idx
        if row_id not in row_map:
            return None
        row_idx = row_map[row_id]

        row_shelves = [s for s in shelf_items if s['row'] == row_idx]
        if not row_shelves:
            return None
        left_edge = min(s['x'] for s in row_shelves)
        right_edge = max(s['x'] + s['w'] for s in row_shelves)
        combined_w = right_edge - left_edge
        count = len(cols)
        mode = ((self.diagram_model.get('_topology') or {}).get('mode') or '').lower()
        shelf_width_in = 48 if mode == 'modular' else 30
        total_shelf_in = count * shelf_width_in

        col_norm = col_id.lower()
        if col_norm == 'le':
            inches = 0
        elif col_norm == 're':
            inches = total_shelf_in
        elif col_norm == 'ctr':
            inches = total_shelf_in / 2
        else:
            m = re.match(r'^le(\d+)$', col_norm)
            if m:
                inches = float(m.group(1))
            else:
                m = re.match(r'^re(\d+)$', col_norm)
                if m:
                    inches = total_shelf_in - float(m.group(1))
                else:
                    m = re.match(r'^c(\d+)$', col_norm)
                    if not m:
                        return None
                    denom = max(1, int(m.group(1)) + 1)
                    inches = total_shelf_in * (int(m.group(1)) / denom)

        inches = max(0, min(total_shelf_in, inches))
        x = left_edge + combined_w * (inches / total_shelf_in if total_shelf_in else 0)
        shelf = row_shelves[0]
        y = shelf['y'] if face == 'r' else shelf['y'] + shelf['h']

        custom[canonical] = {
            'type': 'temperature',
            'position': [x, y],
            'label': canonical,
            'display_side': 'above' if face == 'r' else 'below',
        }
        return canonical

    @staticmethod
    def _is_ignorable_csv_column(column_name: str) -> bool:
        """Columns that are not raw physical sensor dots for mapping purposes."""
        if column_name is None:
            return True
        name = str(column_name).strip()
        if not name:
            return True
        low = name.lower()
        if low in {'timestamp', 'date', 'time'}:
            return True
        if low.startswith('unnamed') or low.startswith('blank'):
            return True
        normalized = ''.join(ch for ch in low if ch.isalnum())
        derived = {
            'sh', 'she',
            'evap', 'avgprodtemp', 'avgprodsimtemp',
            'averageprodtemp', 'averageprodsimtemp',
        }
        return normalized in derived

    def _build_auto_map_report(self, csv_columns, canon_to_role_keys,
                               column_results, aliases) -> dict:
        """Summarize auto-map coverage for UI/reporting and future learning."""
        from sensor_canonical import resolve_canonical_from_role_key

        csv_columns = [str(c) for c in (csv_columns or [])]
        roles = self.diagram_model.get('sensor_roles') or {}
        mapped_columns = {}
        mapped_canonicals = set()
        for role_key, sensor_name in roles.items():
            res = resolve_canonical_from_role_key(self.diagram_model, role_key)
            if not res:
                continue
            canonical = res[0]
            mapped_canonicals.add(canonical)
            mapped_columns[sensor_name] = {
                "canonical": canonical,
                "role_key": role_key,
            }

        ignored_csv = []
        unmapped_csv = []
        known_but_no_role = []
        known_but_filled = []
        for col in csv_columns:
            if col in mapped_columns:
                continue
            info = column_results.get(col) or {}
            status = info.get("status")
            if self._is_ignorable_csv_column(col):
                ignored_csv.append(col)
            elif status == "known_but_no_role":
                known_but_no_role.append({
                    "csv": col,
                    "canonical": info.get("canonical"),
                })
            elif status == "known_but_filled":
                known_but_filled.append({
                    "csv": col,
                    "canonical": info.get("canonical"),
                    "role_keys": info.get("role_keys") or [],
                })
            else:
                unmapped_csv.append(col)

        unmapped_expected = []
        for canonical in sorted(canon_to_role_keys or {}):
            if canonical not in mapped_canonicals:
                unmapped_expected.append({
                    "canonical": canonical,
                    "role_keys": canon_to_role_keys.get(canonical) or [],
                })

        return {
            "csv_columns": len(csv_columns),
            "mapped": len(mapped_columns),
            "expected_canonical": len(canon_to_role_keys or {}),
            "unmapped_csv": unmapped_csv,
            "unmapped_expected": unmapped_expected,
            "ignored_csv": ignored_csv,
            "known_but_no_role": known_but_no_role,
            "known_but_filled": known_but_filled,
            "mapped_columns": mapped_columns,
            "alias_canonicals": len(aliases or {}),
        }

    def get_auto_map_report(self) -> dict:
        """Return the most recent structured auto-map report."""
        return copy.deepcopy(getattr(self, 'last_auto_map_report', {}) or {})

    def get_mapping_gaps(self) -> dict:
        """Compact counts/lists for UI status and audit messaging."""
        report = getattr(self, 'last_auto_map_report', {}) or {}
        unmapped_csv = report.get('unmapped_csv') or []
        unmapped_expected = report.get('unmapped_expected') or []
        known_but_no_role = report.get('known_but_no_role') or []
        known_but_filled = report.get('known_but_filled') or []
        return {
            "unmapped_csv_count": len(unmapped_csv),
            "unmapped_expected_count": len(unmapped_expected),
            "ignored_csv_count": len(report.get('ignored_csv') or []),
            "known_but_no_role_count": len(known_but_no_role),
            "known_but_filled_count": len(known_but_filled),
            "unmapped_csv": unmapped_csv,
            "unmapped_expected": unmapped_expected,
            "known_but_no_role": known_but_no_role,
            "known_but_filled": known_but_filled,
        }

    def _enumerate_diagram_role_keys(self):
        """Yield every role_key shape that exists on the current diagram —
        component ports (Type.cid.port) plus sensor-box slots
        (sensorbox.boxid.sensor_id).

        Includes dynamically-generated ports for ShelvingGrid, Fan, and
        AirSensorArray that don't appear in the static schema.
        """
        comps = self.diagram_model.get('components', {}) or {}
        for cid, c in comps.items():
            ctype = c.get('type')
            props = c.get('properties', {}) or {}
            try:
                from port_resolver import enumerate_ports_for_component
                ports = enumerate_ports_for_component(ctype, props)
            except Exception:
                ports = []
            for p in ports:
                yield f"{ctype}.{cid}.{p}"

            # ShelvingGrid: dynamic ports at physical grid intersections.
            # Interior horizontal edges are shared, so only the first row has
            # top ports; every shelf row contributes its bottom edge.
            if ctype == 'ShelvingGrid':
                shelf_rows = int(props.get('shelf_rows', 6) or 6)
                if props.get('shelving_type', 'Modular') == 'Modular':
                    cols_total = int(props.get('module_count', 3) or 3) + 1
                else:
                    cols_total = int(props.get('door_count', 3) or 3) + 1
                for col in range(cols_total):
                    yield f"ShelvingGrid.{cid}.sensor_r0_top_c{col}"
                for r in range(shelf_rows):
                    for col in range(cols_total):
                        yield f"ShelvingGrid.{cid}.sensor_r{r}_bottom_c{col}"

            # Fan: dynamic ports sensor_{0..N-1}
            if ctype == 'Fan':
                n = int(props.get('sensor_count', 2) or 2)
                for i in range(n):
                    yield f"Fan.{cid}.sensor_{i}"

            # AirSensorArray: role_key uses curtain type as prefix
            if ctype == 'AirSensorArray':
                curtain = (props.get('curtain_type') or 'Primary') + 'Air'
                n = int(props.get('sensor_count', 11) or 11)
                for i in range(1, n + 1):
                    yield f"{curtain}.{cid}.{i}"
                # Also yield the canonical AirSensorArray.cid.i form (used by some code)
                for i in range(1, n + 1):
                    yield f"AirSensorArray.{cid}.{i}"

        for bid, box in (self.diagram_model.get('sensor_boxes') or {}).items():
            for s in box.get('sensors', []) or []:
                yield f"sensorbox.{bid}.{s.get('id')}"

        # Free-position generated dots use their canonical id as the role key
        # (for example shelf corners, fan probes, door/mullion probes).
        for role_key in (self.diagram_model.get('custom_sensors') or {}).keys():
            yield role_key

    # ── Sensor Points ─────────────────────────────────────────────────────────

    def populate_sensor_points(self):
        """Enumerate every port on every component and add any missing entries
        to sensor_points — all enabled by default.  Safe to call repeatedly."""
        from port_resolver import list_all_ports
        if 'sensor_points' not in self.diagram_model:
            self.diagram_model['sensor_points'] = {}
        sp = self.diagram_model['sensor_points']
        try:
            for p in list_all_ports(self):
                rk = p['roleKeyPrimary']
                if rk not in sp:
                    sp[rk] = {'enabled': True, 'label': p['label']}
        except Exception as e:
            print(f"[SENSOR_POINTS] populate failed: {e}")

    def is_sensor_point_enabled(self, role_key: str) -> bool:
        sp = self.diagram_model.get('sensor_points', {})
        entry = sp.get(role_key)
        return True if entry is None else bool(entry.get('enabled', True))

    def set_sensor_point_enabled(self, role_key: str, enabled: bool):
        sp = self.diagram_model.setdefault('sensor_points', {})
        sp.setdefault(role_key, {})['enabled'] = enabled
        self.diagram_model_changed.emit()

    def set_sensor_points_enabled_by(self, comp_type: str = None,
                                     circuit_label: str = None, enabled: bool = True):
        """Bulk enable/disable by component type and/or circuit label."""
        comps = self.diagram_model.get('components', {})
        sp    = self.diagram_model.setdefault('sensor_points', {})
        for rk, entry in sp.items():
            # Parse role_key: "{Type}.{comp_id}.{port}"
            parts = rk.split('.')
            if len(parts) < 3:
                continue
            ctype = parts[0]; cid = parts[1]
            comp  = comps.get(cid, {})
            clbl  = (comp.get('properties') or {}).get('circuit_label', '') or ''
            if clbl == 'None':
                clbl = ''
            if comp_type and ctype != comp_type:
                continue
            if circuit_label and clbl != circuit_label:
                continue
            entry['enabled'] = enabled
        self.diagram_model_changed.emit()

    def _pattern_key(self, role_key: str) -> str:
        """Convert 'Compressor.comp_id.SP' → 'Compressor::SP' (portable across sessions)."""
        comps = self.diagram_model.get('components', {})
        parts = role_key.split('.')
        if len(parts) >= 3:
            ctype = parts[0]; cid = parts[1]; port = '.'.join(parts[2:])
            comp  = comps.get(cid, {})
            clbl  = (comp.get('properties') or {}).get('circuit_label', '') or ''
            if clbl == 'None':
                clbl = ''
            return f"{ctype}:{clbl}:{port}"
        return role_key

    @staticmethod
    def _get_layout_key(topo: dict) -> str:
        mode     = topo.get('mode', 'modular')
        circuits = int(topo.get('circuits_per_coil', 6) or 6)
        if mode == 'modular':
            suffix = f"{topo.get('modules', 3)}mod"
        elif mode == 'door':
            suffix = f"{topo.get('num_doors', 3)}dr"
        elif mode == 'cassette_mt':
            suffix = f"{topo.get('num_cassettes', 1)}cmt"
        elif mode == 'cassette_lt':
            suffix = f"{topo.get('num_cassettes', 1)}clt"
        else:
            suffix = 'unknown'
        return f"{suffix}_{circuits}cir"

    @staticmethod
    def _sensor_defaults_path(layout_key: str) -> str:
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'library', 'sensor_defaults')
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, f"{layout_key}.json")

    def save_sensor_point_defaults(self, topo: dict):
        """Save current on/off state as the default for this layout shape."""
        sp = self.diagram_model.get('sensor_points', {})
        defaults = {self._pattern_key(rk): {'enabled': v.get('enabled', True)}
                    for rk, v in sp.items()}
        path = self._sensor_defaults_path(self._get_layout_key(topo))
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(defaults, f, indent=2)
        print(f"[SENSOR_DEFAULTS] Saved {len(defaults)} entries → {path}")

    def apply_sensor_point_defaults(self, topo: dict) -> bool:
        """Load saved defaults and apply to current sensor_points.  Returns True if found."""
        path = self._sensor_defaults_path(self._get_layout_key(topo))
        if not os.path.exists(path):
            return False
        try:
            with open(path, encoding='utf-8') as f:
                defaults = json.load(f)
        except Exception as e:
            print(f"[SENSOR_DEFAULTS] Load failed: {e}")
            return False
        sp = self.diagram_model.setdefault('sensor_points', {})
        for rk in list(sp.keys()):
            pk = self._pattern_key(rk)
            if pk in defaults:
                sp[rk]['enabled'] = defaults[pk].get('enabled', True)
        print(f"[SENSOR_DEFAULTS] Applied {len(defaults)} defaults for layout "
              f"'{self._get_layout_key(topo)}'")
        return True

    # ─────────────────────────────────────────────────────────────────────────

    def map_sensor_to_role(self, role_key, sensor_name):
        """Map a sensor name to a canonical role key in the diagram model.
        
        Ensures that:
        1. One sensor can only be mapped to one role at a time
        2. If sensor is already mapped to a different role, it gets unmapped from that role first
        3. One role can only have one sensor mapped to it
        """
        if 'sensor_roles' not in self.diagram_model or not isinstance(self.diagram_model['sensor_roles'], dict):
            self.diagram_model['sensor_roles'] = {}
        
        roles = self.diagram_model['sensor_roles']
        print(f"[MAP] Current mappings before operation: {len(roles)}")
        print(f"[MAP] Attempting to map {sensor_name} to {role_key}")
        
        # Check if sensor is already mapped to any different roles (find ALL duplicates)
        existing_roles = []
        for existing_role_key, existing_sensor in roles.items():
            if existing_sensor == sensor_name and existing_role_key != role_key:
                existing_roles.append(existing_role_key)
        
        # Check if the target role already has a different sensor mapped to it
        existing_sensor_in_role = roles.get(role_key)
        if existing_sensor_in_role and existing_sensor_in_role != sensor_name:
            print(f"[MAP] Role {role_key} already has sensor {existing_sensor_in_role} mapped to it")
            print(f"[MAP] Automatically replacing {existing_sensor_in_role} with {sensor_name}")
            # Don't delete the role_key, we'll overwrite it below
        
        # If sensor is already mapped to different roles, unmap from ALL of them
        if existing_roles:
            print(f"[MAP] Sensor {sensor_name} already mapped to {len(existing_roles)} role(s), unmapping all:")
            for old_role in existing_roles:
                print(f"[MAP]   - Unmapping from {old_role}")
                del roles[old_role]
        
        # Map the sensor to the new role (this ensures one-to-one mapping)
        roles[role_key] = sensor_name

        # Learn this alias for future CSV loads
        try:
            from sensor_canonical import resolve_canonical_from_role_key
            res = resolve_canonical_from_role_key(self.diagram_model, role_key)
            if res:
                self._save_learned_alias(res[0], sensor_name)
        except Exception:
            pass

        print(f"[MAP] Successfully mapped {sensor_name} to {role_key}")
        print(f"[MAP] Total mappings after operation: {len(roles)}")
        
        # Validate the mapping is correct (only during mapping operations)
        self._validate_sensor_mappings()
        
        print(f"[MAP] Total mappings after validation: {len(roles)}")
        
        # Emitting explicit signal for lightweight UI updates
        # We avoid diagram_model_changed here to prevent full scene rebuilds
        self.sensor_mapping_changed.emit(role_key, sensor_name, True)
        # self.data_changed.emit()
    
    def export_audit_csv(self, output_path: str = "audit_export.csv", include_only_graphed: bool = False, on_time_only: bool = False):
        """
        Writes a lightweight audit CSV that you can open in Excel to visually validate:
        - Row 1: Config labels (Timestamp + config sensor list order)
        - Row 2: CSV labels (Timestamp + actual CSV column names mapped to those config labels)
        - Rows 3+: Data from the current filtered DataFrame (or ON-time subset),
                    restricted to the chosen columns, overwriting the file each time.

        Args:
            output_path: Target CSV path to overwrite.
            include_only_graphed: If True, restrict columns to sensors currently checked for graphing.
            on_time_only: If True, use ON-time filtered data; otherwise use time-range filtered data.
        """
        try:
            import csv
            # Determine original config labels for Row 1 (exclude Timestamp)
            base_labels = []
            if getattr(self, 'original_config_sensor_list', None):
                base_labels = [label for label in self.original_config_sensor_list if label != 'Timestamp']
            elif self.config_sensor_list:
                base_labels = [label for label in self.config_sensor_list if label != 'Timestamp']
            elif self.csv_data is not None and not self.csv_data.empty:
                base_labels = list(self.csv_data.columns[1:])
            config_labels = base_labels

            # Optionally restrict to graphed sensors
            if include_only_graphed and self.graph_sensors:
                config_labels = [s for s in config_labels if s in self.graph_sensors]

            # Build CSV labels row based on actual dataframe columns available
            df_source = None
            if on_time_only:
                df_source = self.get_on_time_filtered_data()
                print(f"[AUDIT EXPORT] Using ON-time filtered data: {len(df_source) if df_source is not None else 0} rows")
            else:
                df_source = self.get_filtered_data()
                print(f"[AUDIT EXPORT] Using time-range filtered data: {len(df_source) if df_source is not None else 0} rows")
                print(f"[AUDIT EXPORT] Current time_range setting: {self.time_range}")

            if df_source is None:
                df_source = self.csv_data if self.csv_data is not None else None
                print(f"[AUDIT EXPORT] Fallback to full CSV data: {len(df_source) if df_source is not None else 0} rows")

            # Row 2 values: mapped CSV labels for each original config label
            csv_labels = []
            if getattr(self, 'config_label_mapping', None):
                for label in config_labels:
                    mapped = self.config_label_mapping.get(label)
                    csv_labels.append(mapped if mapped in (df_source.columns if (df_source is not None and not df_source.empty) else []) else (mapped or ""))
            else:
                # Fallback: identity mapping if no mapping stored
                for label in config_labels:
                    csv_labels.append(label)

            # Final column order: Timestamp + chosen labels
            header_config = ['Timestamp'] + config_labels
            header_csv = ['Timestamp'] + csv_labels

            # Prepare data rows from df_source restricted to these columns if available
            data_rows = []
            if df_source is not None and not df_source.empty:
                # Ensure Timestamp exists; if missing, synthesize empty column for alignment
                temp_df = df_source.copy()
                if 'Timestamp' not in temp_df.columns:
                    temp_df.insert(0, 'Timestamp', None)
                # Reorder/select columns; missing columns will be filled with empty values
                for _, row in temp_df.iterrows():
                    values = []
                    # Timestamp first
                    ts_val = row.get('Timestamp')
                    values.append(ts_val if ts_val is not pd.NaT else '')
                    # Then per config label
                    for original_label, mapped_label in zip(config_labels, csv_labels):
                        col_name = mapped_label if mapped_label else original_label
                        values.append(row.get(col_name, ''))
                    data_rows.append(values)

            # Write CSV (overwrite) - handle file locking issues
            try:
                with open(output_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(header_config)
                    writer.writerow(header_csv)
                    writer.writerows(data_rows)
            except PermissionError:
                # If file is locked, try with a different name
                import time
                timestamp = int(time.time())
                backup_path = f"{output_path}.{timestamp}"
                print(f"[AUDIT EXPORT] Permission denied, trying backup path: {backup_path}")
                with open(backup_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(header_config)
                    writer.writerow(header_csv)
                    writer.writerows(data_rows)
                output_path = backup_path

            print(f"[AUDIT EXPORT] Wrote {len(data_rows)} data rows to {output_path}")
            print(f"[AUDIT EXPORT] Row1 (config): {header_config[:6]}{'...' if len(header_config) > 6 else ''}")
            print(f"[AUDIT EXPORT] Row2 (csv):    {header_csv[:6]}{'...' if len(header_csv) > 6 else ''}")
            return True
        except Exception as e:
            print(f"[AUDIT EXPORT] Error writing CSV: {e}")
            return False

    def _validate_sensor_mappings(self):
        """Validate that sensor mappings are one-to-one (no duplicates).
        
        This method only logs duplicate mappings but doesn't remove them.
        Duplicates are allowed to exist (e.g., from JSON files) and will only
        be cleaned up when there's an actual mapping conflict.
        """
        roles = self.diagram_model.get('sensor_roles', {})
        original_count = len(roles)
        # print(f"[VALIDATION] Starting validation with {original_count} mappings")
        
        # Check for duplicate sensors but don't remove them
        sensor_to_roles = {}
        duplicates_found = []
        
        for role_key, sensor_name in roles.items():
            if sensor_name in sensor_to_roles:
                duplicates_found.append((sensor_name, sensor_to_roles[sensor_name], role_key))
                print(f"[VALIDATION INFO] Sensor {sensor_name} is mapped to multiple roles: {sensor_to_roles[sensor_name]} and {role_key}")
            else:
                sensor_to_roles[sensor_name] = role_key
        
        if duplicates_found:
            print(f"[VALIDATION INFO] Found {len(duplicates_found)} sensors mapped to multiple roles")
            print(f"[VALIDATION INFO] This is normal when loading from JSON files - duplicates will be handled during mapping operations")
        else:
            # print(f"[VALIDATION INFO] No duplicate sensor mappings found")
            pass
        
        # print(f"[VALIDATION] Sensor mappings preserved: {len(roles)} total mappings")

    def unmap_role(self, role_key):
        """Remove mapping for a role key if present."""
        roles = self.diagram_model.get('sensor_roles', {})
        if role_key in roles:
            del roles[role_key]
            # Emitting explicit signal for lightweight UI updates
            self.sensor_mapping_changed.emit(role_key, "", False)
            # self.data_changed.emit()
    
    def clear_all_sensor_mappings(self):
        """Clear all sensor mappings (both old and new system)."""
        # Clear new smart sensor system mappings
        if 'sensor_roles' in self.diagram_model:
            old_count = len(self.diagram_model['sensor_roles'])
            self.diagram_model['sensor_roles'] = {}
            print(f"[CLEAR] Cleared {old_count} smart sensor mappings")
        
        # Clear old legacy mappings
        old_mappings_count = len(self.mappings)
        self.mappings = {}
        if old_mappings_count > 0:
            print(f"[CLEAR] Cleared {old_mappings_count} legacy mappings")
        
        self.diagram_model_changed.emit()
        self.data_changed.emit()
        print("[CLEAR] All sensor mappings cleared - all sensors will appear orange (unmapped)")

    def get_mapped_sensor_for_role(self, role_key):
        roles = self.diagram_model.get('sensor_roles', {})
        return roles.get(role_key)

    def is_sensor_mapped_in_roles(self, sensor_name):
        """Return True if sensor_name appears as a value in diagram_model.sensor_roles."""
        try:
            roles = self.diagram_model.get('sensor_roles', {})
            return any(mapped == sensor_name for mapped in roles.values())
        except Exception:
            return False
    
    def get_custom_sensor_roles_for_sensor(self, sensor_name):
        """Return list of custom sensor role keys (sensor IDs) that are mapped to this sensor."""
        roles = self.diagram_model.get('sensor_roles', {})
        custom_roles = []
        for role_key, mapped_sensor in roles.items():
            # Check if this is a custom sensor role (starts with 'custom_') and maps to our sensor
            if role_key.startswith('custom_') and mapped_sensor == sensor_name:
                custom_roles.append(role_key)
        return custom_roles

    def count_role_mappings(self):
        """Return count of unique sensors mapped in diagram_model.sensor_roles."""
        try:
            roles = self.diagram_model.get('sensor_roles', {})
            return len(set(roles.values()))
        except Exception:
            return 0
    
    def get_sensor_mapping_status(self, sensor_name):
        """Get the mapping status for a specific sensor."""
        roles = self.diagram_model.get('sensor_roles', {})
        
        # Find which role this sensor is mapped to
        mapped_role = None
        for role_key, mapped_sensor in roles.items():
            if mapped_sensor == sensor_name:
                mapped_role = role_key
                break
        
        return {
            'sensor_name': sensor_name,
            'is_mapped': mapped_role is not None,
            'mapped_to_role': mapped_role,
            'total_mappings': len(roles)
        }

    # === Mapping exports for audit/remapping ===
    def export_port_mapping_csv(self, output_path: str = "port_mapping_audit.csv") -> str:
        """
        Export every component port with its role keys and currently mapped CSV column.

        Columns: componentId,type,circuit_label,port,label,roleKeyPrimary,roleKeyFallback,csv_column,sensor_number,current_value
        Returns the written path.
        """
        try:
            import csv
            from port_resolver import list_all_ports

            rows = list_all_ports(self)

            with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "componentId","type","circuit_label","port","label",
                    "roleKeyPrimary","roleKeyFallback","csv_column","sensor_number","current_value"
                ])
                for r in rows:
                    props = r.get('properties') or {}
                    writer.writerow([
                        r.get('componentId'),
                        r.get('type'),
                        props.get('circuit_label', ''),
                        r.get('port'),
                        r.get('label'),
                        r.get('roleKeyPrimary'),
                        r.get('roleKeyFallback'),
                        r.get('sensor') or '',
                        r.get('sensorNumber') or '',
                        r.get('value') if r.get('value') is not None else ''
                    ])
            print(f"[MAPPING EXPORT] Wrote port mapping audit to {output_path}")
            return output_path
        except Exception as e:
            print(f"[MAPPING EXPORT] ERROR exporting port mapping: {e}")
            return output_path

    def export_required_roles_csv(self, output_path: str = "required_roles_mapping.csv") -> str:
        """
        Export the required sensor roles (from _build_required_sensor_roles) with the
        currently resolved CSV column for each role.

        Columns: role_key,component_type,port_name,csv_column
        Returns the written path.
        """
        try:
            import csv
            from circuit_semantics import get_all_module_labels
            from calculation_orchestrator import _build_required_sensor_roles, _find_sensor_for_role

            model = self.diagram_model
            module_labels = get_all_module_labels(model) or ['Left']
            required_roles = _build_required_sensor_roles(module_labels)

            from port_resolver import find_suction_pressure_sensor, find_discharge_pressure_sensor

            with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["role_key","component_type","port_name","csv_column"])
                for role_key, defs in required_roles.items():
                    # Write first matching mapping (same resolution logic as calculation)
                    csv_col = ''
                    comp_type = ''
                    port_name = ''
                    if defs:
                        comp_type = defs[0][0]
                        port_name = defs[0][1]
                    try:
                        mapped = None
                        # P_suc/P_disch: check inline Sensors first (matches run_batch_processing)
                        if role_key == 'P_suc':
                            mapped = find_suction_pressure_sensor(model)
                        elif role_key == 'P_disch':
                            mapped = find_discharge_pressure_sensor(model)
                        if mapped is None:
                            for role_def in defs:
                                mapped = _find_sensor_for_role(model, role_def)
                                if mapped:
                                    break
                        csv_col = mapped or ''
                    except Exception:
                        csv_col = ''
                    writer.writerow([role_key, comp_type, port_name, csv_col])
            print(f"[MAPPING EXPORT] Wrote required roles mapping to {output_path}")
            return output_path
        except Exception as e:
            print(f"[MAPPING EXPORT] ERROR exporting required roles: {e}")
            return output_path
    
    def debug_sensor_mappings(self):
        """Print debug information about all sensor mappings."""
        roles = self.diagram_model.get('sensor_roles', {})
        print(f"[DEBUG] Total sensor mappings: {len(roles)}")
        
        for role_key, sensor_name in roles.items():
            print(f"  {role_key} -> {sensor_name}")
        
        # Check for duplicates
        sensor_counts = {}
        for sensor_name in roles.values():
            sensor_counts[sensor_name] = sensor_counts.get(sensor_name, 0) + 1
        
        duplicates = {sensor: count for sensor, count in sensor_counts.items() if count > 1}
        if duplicates:
            print(f"[DEBUG] WARNING: Duplicate sensor mappings found: {duplicates}")
        else:
            print(f"[DEBUG] No duplicate mappings found - all mappings are unique")

    def merge_sessions_to_file(self, file_path_a, file_path_b, output_file_path):
        """Merges two session JSON files and saves the combined result to output_file_path."""
        try:
            with open(file_path_a, 'r', encoding='utf-8') as fa:
                session_a = json.load(fa)
            with open(file_path_b, 'r', encoding='utf-8') as fb:
                session_b = json.load(fb)
            merged = self._merge_sessions_data(session_a, session_b)
            with open(output_file_path, 'w', encoding='utf-8') as fo:
                json.dump(merged, fo, indent=2, ensure_ascii=False)
            print(f"Merged sessions saved to: {output_file_path}")
            return True
        except Exception as e:
            print(f"Error merging sessions: {e}")
            return False

    def _merge_sessions_data(self, session_a, session_b):
        """Merge two in-memory session dicts into one combined dict.
        Preference: values from B override A on conflicts.
        """
        from datetime import datetime

        def get_headers(sess):
            csv_obj = sess.get('csvData') or {}
            headers = csv_obj.get('headers') or sess.get('csvHeaders') or []
            return headers

        def merge_mappings(map_a, map_b):
            out = dict(map_a or {})
            for k, v in (map_b or {}).items():
                out[k] = v
            return out

        def merge_ranges(r_a, r_b):
            out = dict(r_a or {})
            for k, v in (r_b or {}).items():
                out[k] = v
            return out

        def merge_groups(g_a, g_b):
            out = {}
            for g, lst in (g_a or {}).items():
                out[g] = list(dict.fromkeys(lst))
            for g, lst in (g_b or {}).items():
                if g in out:
                    combined = list(dict.fromkeys(out[g] + lst))
                    out[g] = combined
                else:
                    out[g] = list(dict.fromkeys(lst))
            return out

        def merge_group_states(s_a, s_b):
            out = dict(s_a or {})
            for g, state in (s_b or {}).items():
                out[g] = bool(state) or bool(out.get(g, False))
            return out

        def choose_diagram(a, b):
            diag_a = (a or {}).get('diagramModel') or {}
            diag_b = (b or {}).get('diagramModel') or {}
            # Prefer the one that actually has components/pipes
            def has_content(diag):
                return bool(diag.get('components')) or bool(diag.get('pipes'))
            if has_content(diag_b):
                return diag_b
            if has_content(diag_a):
                return diag_a
            return {}

        def choose_image_path(a, b):
            path_b = b.get('imagePath') if isinstance(b, dict) else None
            path_a = a.get('imagePath') if isinstance(a, dict) else None
            return path_b or path_a

        def choose_image_data(a, b):
            data_b = b.get('imageData') if isinstance(b, dict) else None
            data_a = a.get('imageData') if isinstance(a, dict) else None
            return data_b or data_a

        mappings = merge_mappings(session_a.get('mappings'), session_b.get('mappings'))
        sensor_ranges = merge_ranges(session_a.get('sensorRanges'), session_b.get('sensorRanges'))
        sensor_groups = merge_groups(session_a.get('sensorGroups'), session_b.get('sensorGroups'))
        group_states = merge_group_states(session_a.get('groupStates'), session_b.get('groupStates'))

        # CSV headers: prefer available headers; fallback to mapping keys
        headers = get_headers(session_a) or get_headers(session_b)
        if not headers:
            if mappings:
                headers = ["Timestamp"] + sorted(list(mappings.keys()))
            else:
                headers = []

        # CSV data: preserve csvData object from the session that has it
        csv_data_obj = session_a.get('csvData') or session_b.get('csvData') or None
        if csv_data_obj and csv_data_obj.get('headers'):
            merged_csv = csv_data_obj
        else:
            merged_csv = {"headers": headers, "data": [], "rows": 0, "fileName": session_a.get('csvPath') or session_b.get('csvPath') or ""}

        merged = {
            "name": "merged_session",
            "timestamp": datetime.now().isoformat() + "Z",
            "csvPath": session_b.get('csvPath') or session_a.get('csvPath') or "",
            "csvData": merged_csv,
            "imagePath": choose_image_path(session_a, session_b),
            "imageData": choose_image_data(session_a, session_b),
            "mappings": mappings,
            "sensorGroups": sensor_groups,
            "groupStates": group_states,
            "sensorRanges": sensor_ranges,
            "diagramModel": choose_diagram(session_a, session_b),
            "ui": session_b.get('ui') or session_a.get('ui') or {"selectedSensors": [], "currentMode": "mapping", "selectedTimeRange": "All Data"}
        }

        # Carry through any optional diagram properties if present
        if 'diagramModel' in merged and isinstance(merged['diagramModel'], dict):
            merged['diagramModel'].setdefault('properties', (session_b.get('diagramModel', {}) or session_a.get('diagramModel', {})).get('properties', {}))

        return merged

    def _get_csv_filename(self):
        """Return a safe CSV filename for serialization."""
        if isinstance(self.csv_path, str) and self.csv_path:
            return os.path.basename(self.csv_path)
        return "data.csv"

    def _prepare_csv_data(self):
        """Prepares minimal CSV metadata for saving.
        To ensure compatibility and avoid non-serializable timestamp values,
        we include headers and row count only; data is left empty.
        """
        # Get sensor names from either CSV data or config sensor list
        sensor_names = []
        if self.csv_data is not None and not self.csv_data.empty:
            sensor_names = list(self.csv_data.columns[1:])  # Exclude timestamp column
        elif self.config_sensor_list:
            sensor_names = [name for name in self.config_sensor_list if name != "Timestamp"]
        else:
            sensor_names = [row['default_label'] for row in self.get_expected_sensor_rows()]
        
        # Sanitize: Remove Unnamed columns before saving to config
        sensor_names = self._sanitize_sensor_list(sensor_names)

        headers = ["Timestamp"] + sensor_names if sensor_names else []
        rows = len(self.csv_data) if (self.csv_data is not None and not self.csv_data.empty) else 0

        return {
            "headers": headers,
            "data": [],  # Intentionally empty to avoid timestamp serialization issues
            "rows": rows,
            "fileName": self._get_csv_filename()
        }
    
    def _prepare_image_data(self):
        """Prepares image path for saving."""
        if self.image_path:
            return os.path.basename(self.image_path)
        return None
    
    def _prepare_image_base64(self):
        """Prepares base64 encoded image data with size optimization."""
        if self.image_pixmap is None:
            return None
        
        try:
            from PyQt6.QtCore import Qt, QBuffer, QIODevice
            
            # Convert QPixmap to QImage for processing
            qimage = self.image_pixmap.toImage()
            
            # Optimize image size while maintaining quality
            # Scale down if image is very large (>2000px on longest side)
            max_dimension = 2000
            if qimage.width() > max_dimension or qimage.height() > max_dimension:
                scale_factor = max_dimension / max(qimage.width(), qimage.height())
                new_width = int(qimage.width() * scale_factor)
                new_height = int(qimage.height() * scale_factor)
                qimage = qimage.scaled(new_width, new_height, 
                                     Qt.AspectRatioMode.KeepAspectRatio, 
                                     Qt.TransformationMode.SmoothTransformation)
            
            # Convert to PNG format with reasonable compression
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            qimage.save(buffer, "PNG", quality=85)  # 85% quality for good balance
            
            # Convert to base64
            image_data = buffer.data()
            base64_data = base64.b64encode(image_data).decode('utf-8')
            
            return f"data:image/png;base64,{base64_data}"
            
        except Exception as e:
            print(f"Error preparing image data: {e}")
            return None
    
    def _prepare_mappings_with_ranges(self):
        """Prepares mappings with ranges embedded in each mapping."""
        mappings_with_ranges = {}
        for sensor_name, mapping in self.mappings.items():
            mapping_copy = mapping.copy()
            
            # Add range information if it exists for this sensor
            if sensor_name in self.sensor_ranges:
                range_info = self.sensor_ranges[sensor_name]
                mapping_copy["range"] = {
                    "min": range_info.get("min", 0),
                    "max": range_info.get("max", 100)
                }
            
            mappings_with_ranges[sensor_name] = mapping_copy
        
        return mappings_with_ranges
    
    def _prepare_sensor_groups(self):
        """Prepares sensor groups structure including all individual sensors."""
        # Get all sensors from either CSV data or config sensor list
        all_sensors = set()
        if self.csv_data is not None:
            all_sensors = set(self.csv_data.columns[1:])  # Exclude timestamp column
        elif self.config_sensor_list:
            # Remove timestamp if it exists in config list
            all_sensors = set([name for name in self.config_sensor_list if name != "Timestamp"])
        else:
            expected_groups = self.get_expected_sensor_groups()
            if expected_groups:
                return expected_groups
        
        # Start with existing groups
        prepared_groups = {}
        grouped_sensors = set()
        
        for group_name, sensor_list in self.sensor_groups.items():
            # Only include sensors that actually exist in our sensor list
            valid_sensors = [sensor for sensor in sensor_list if sensor in all_sensors]
            if valid_sensors:
                prepared_groups[group_name] = valid_sensors
                grouped_sensors.update(valid_sensors)
        
        # Add ungrouped sensors if any exist
        ungrouped_sensors = all_sensors - grouped_sensors
        if ungrouped_sensors:
            prepared_groups["_ungrouped"] = list(ungrouped_sensors)
        
        return prepared_groups
    
    def _prepare_group_states(self):
        """Prepares group states (which groups are expanded)."""
        # For now, default all groups to expanded (True)
        # In a more advanced implementation, this could track actual UI state
        group_states = {}
        for group_name in self.sensor_groups.keys():
            group_states[group_name] = True
        
        # Add _ungrouped state if it exists
        if "_ungrouped" in self.sensor_groups:
            group_states["_ungrouped"] = True
            
        return group_states
    
    def _index_to_excel_column(self, index):
        """Converts a 0-based column index to Excel column letter(s)."""
        result = ""
        while index >= 0:
            result = chr(65 + (index % 26)) + result
            index = index // 26 - 1
        return result
    
    @staticmethod
    def format_date_friendly(dt):
        """Formats date as 'Month Day' (e.g., 'March 15')"""
        if hasattr(dt, 'strftime'):
            # Use %#d on Windows, %-d on Unix
            import platform
            if platform.system() == 'Windows':
                return dt.strftime('%B %#d')
            else:
                return dt.strftime('%B %-d')
        return str(dt)
    
    @staticmethod
    def format_time_friendly(dt):
        """Formats time as '1:30 AM' (12-hour format with AM/PM)"""
        if hasattr(dt, 'strftime'):
            # Use %#I on Windows, %-I on Unix
            import platform
            if platform.system() == 'Windows':
                return dt.strftime('%#I:%M %p')
            else:
                return dt.strftime('%-I:%M %p')
        return str(dt)
    
    # === DIAGRAM DESIGNER METHODS ===
    
    def add_component_to_model(self, component_type, position):
        """Add a component to the diagram model."""
        from component_schemas import SCHEMAS
        
        comp_id = f"{component_type.lower()}_{uuid.uuid4().hex[:6]}"
        
        # Initialize properties with default values from schema
        schema = SCHEMAS.get(component_type, {})
        properties = {}
        for prop_name, prop_schema in schema.get('properties', {}).items():
            properties[prop_name] = prop_schema.get('default')
        
        self.diagram_model['components'][comp_id] = {
            "type": component_type,
            "position": [position.x(), position.y()],
            "properties": properties,
            "size": {"width": 100, "height": 60},
            "rotation": 0
        }
        self.diagram_model_changed.emit()
        return comp_id

    def remove_components_from_model(self, component_ids):
        """Remove components from diagram model."""
        for comp_id in component_ids:
            if comp_id in self.diagram_model['components']:
                del self.diagram_model['components'][comp_id]
        
        pipes_to_delete = []
        for pipe_id, pipe_data in self.diagram_model['pipes'].items():
            if pipe_data['start_component_id'] in component_ids or pipe_data['end_component_id'] in component_ids:
                pipes_to_delete.append(pipe_id)
        
        for pipe_id in pipes_to_delete:
            del self.diagram_model['pipes'][pipe_id]
            
        self.diagram_model_changed.emit()

    def update_component_position(self, component_id, position):
        """Update component position."""
        if component_id in self.diagram_model['components']:
            # Ensure position is stored as a plain [x, y] list for JSON serialization
            try:
                x = position.x() if hasattr(position, 'x') else position[0]
                y = position.y() if hasattr(position, 'y') else position[1]
                self.diagram_model['components'][component_id]['position'] = [x, y]
            except Exception:
                # Fallback: attempt to coerce to list if possible
                try:
                    self.diagram_model['components'][component_id]['position'] = list(position)
                except Exception:
                    pass
    
    def add_pipe_to_model(self, start_comp_id, start_port, end_comp_id, end_port, fluid_state='any', pressure_side='any', circuit_label='None'):
        """Add pipe connection to diagram model."""
        pipe_id = f"pipe_{uuid.uuid4().hex[:6]}"
        self.diagram_model['pipes'][pipe_id] = {
            "start_component_id": start_comp_id,
            "start_port": start_port,
            "end_component_id": end_comp_id,
            "end_port": end_port,
            "fluid_state": fluid_state,
            "pressure_side": pressure_side,
            "circuit_label": circuit_label,
            "waypoints": []
        }
        self.diagram_model_changed.emit()
        return pipe_id
    
    def remove_pipes_from_model(self, pipe_ids):
        """Remove pipes from diagram model."""
        for pipe_id in pipe_ids:
            if pipe_id in self.diagram_model['pipes']:
                del self.diagram_model['pipes'][pipe_id]
        self.diagram_model_changed.emit()
    
    # === SENSOR BOX METHODS ===
    def add_sensor_box(self, position):
        """Add a sensor box to the diagram model."""
        box_id = f"sensorbox_{uuid.uuid4().hex[:6]}"
        
        self.diagram_model['sensor_boxes'][box_id] = {
            "position": [position.x(), position.y()],
            "title": "Sensor Box",
            "sensors": []
        }
        self.diagram_model_changed.emit()
        return box_id
    
    def remove_sensor_box(self, box_id):
        """Remove a sensor box from diagram model."""
        if box_id in self.diagram_model['sensor_boxes']:
            # Unmap all sensors in this box
            box_data = self.diagram_model['sensor_boxes'][box_id]
            for sensor in box_data.get('sensors', []):
                sensor_id = sensor.get('id')
                role_key = f"sensorbox.{box_id}.{sensor_id}"
                self.unmap_role(role_key)
            
            del self.diagram_model['sensor_boxes'][box_id]
            self.diagram_model_changed.emit()
    
    def update_sensor_box_position(self, box_id, position):
        """Update sensor box position."""
        if box_id in self.diagram_model['sensor_boxes']:
            try:
                x = position.x() if hasattr(position, 'x') else position[0]
                y = position.y() if hasattr(position, 'y') else position[1]
                self.diagram_model['sensor_boxes'][box_id]['position'] = [x, y]
            except Exception:
                try:
                    self.diagram_model['sensor_boxes'][box_id]['position'] = list(position)
                except Exception:
                    pass
    
    def update_sensor_box_title(self, box_id, title):
        """Update sensor box title."""
        if box_id in self.diagram_model['sensor_boxes']:
            self.diagram_model['sensor_boxes'][box_id]['title'] = title
            self.diagram_model_changed.emit()
    
    def add_sensor_to_box(self, box_id, label):
        """Add a sensor to a sensor box."""
        if box_id not in self.diagram_model['sensor_boxes']:
            return None
        
        sensor_id = f"sensor_{uuid.uuid4().hex[:8]}"
        
        if 'sensors' not in self.diagram_model['sensor_boxes'][box_id]:
            self.diagram_model['sensor_boxes'][box_id]['sensors'] = []
        
        self.diagram_model['sensor_boxes'][box_id]['sensors'].append({
            'id': sensor_id,
            'label': label
        })
        self.diagram_model_changed.emit()
        return sensor_id
    
    def remove_sensor_from_box(self, box_id, sensor_id):
        """Remove a sensor from a sensor box."""
        if box_id in self.diagram_model['sensor_boxes']:
            box = self.diagram_model['sensor_boxes'][box_id]
            if 'sensors' in box:
                box['sensors'] = [s for s in box['sensors'] if s['id'] != sensor_id]
            
            # Unmap the sensor
            role_key = f"sensorbox.{box_id}.{sensor_id}"
            self.unmap_role(role_key)
            self.diagram_model_changed.emit()
