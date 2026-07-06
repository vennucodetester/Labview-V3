from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLineEdit, QCheckBox, QTreeWidget, QTreeWidgetItem,
                             QLabel, QGroupBox, QFrame, QTreeWidgetItemIterator,
                             QAbstractItemView, QMenu, QInputDialog, QMessageBox,
                             QToolButton, QComboBox, QTextEdit, QDialog)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QAction, QFont

class SensorPanel(QWidget):
    """
    Manages the sensor list UI with a full-featured right-click context menu
    for grouping, renaming, and moving sensors.
    """
    sensor_locate_requested = pyqtSignal(str, str, str)

    def __init__(self, data_manager):
        super().__init__()
        self.data_manager = data_manager
        self.clipboard = [] # Simple clipboard for cut/paste
        self.setupUi()
        self.connect_signals()

    def setupUi(self):
        """Creates and arranges all the widgets for this panel."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        main_layout.addWidget(content_widget, 1)

        # --- Row 1: Icon toolbar (no GroupBox, no label) ---
        top_frame = QFrame()
        top_frame.setFrameShape(QFrame.Shape.StyledPanel)
        top_frame.setStyleSheet("QFrame { background: #f5f5f5; border-bottom: 1px solid #ddd; }")
        toolbar_layout = QHBoxLayout(top_frame)
        toolbar_layout.setContentsMargins(4, 3, 4, 3)
        toolbar_layout.setSpacing(3)

        self.load_config_button = QToolButton()
        self.load_config_button.setText('📁')
        self.load_config_button.setToolTip('Load session or case (.json)')
        self.load_config_button.setFixedSize(28, 28)
        self.load_config_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.load_csv_button = QToolButton()
        self.load_csv_button.setText('📊')
        self.load_csv_button.setToolTip('Load data file (.csv / .xlsx)')
        self.load_csv_button.setFixedSize(28, 28)
        self.load_csv_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.save_config_button = QToolButton()
        self.save_config_button.setText('💾')
        self.save_config_button.setToolTip('Save session')
        self.save_config_button.setFixedSize(28, 28)
        self.save_config_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.range_button = QToolButton()
        self.range_button.setText('📏')
        self.range_button.setToolTip('Set sensor value ranges for status monitoring')
        self.range_button.setFixedSize(28, 28)
        self.range_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.refresh_button = QToolButton()
        self.refresh_button.setText('↻')
        self.refresh_button.setToolTip('Refresh data manually')
        self.refresh_button.setFixedSize(28, 28)
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)


        toolbar_layout.addWidget(self.load_config_button)
        toolbar_layout.addWidget(self.load_csv_button)
        toolbar_layout.addWidget(self.save_config_button)
        toolbar_layout.addWidget(self.range_button)
        toolbar_layout.addWidget(self.refresh_button)
        toolbar_layout.addStretch()

        # Settings gear button — kept exactly as original, moved into toolbar row
        self.settings_button = QToolButton()
        self.settings_button.setText("⚙️")
        self.settings_button.setToolTip("Settings")
        self.settings_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setAutoRaise(True)

        self.settings_menu = QMenu(self)
        self.write_audit_action = self.settings_menu.addAction("Write Audit CSV")
        self.write_audit_action.triggered.connect(self.on_export_audit_clicked)
        self.settings_button.setMenu(self.settings_menu)

        toolbar_layout.addWidget(self.settings_button)
        content_layout.addWidget(top_frame)

        # --- Row 2: Time range (one compact row, no GroupBox) ---
        time_row = QHBoxLayout()
        time_row.setContentsMargins(4, 2, 4, 2)
        time_lbl = QLabel('⏱')
        time_lbl.setToolTip('Time range — affects all tabs')
        time_lbl.setFixedWidth(18)

        # Build items programmatically — fractional + whole hours 1-100
        _SPECIAL_NOTES = {12: ' (half day)', 24: ' (1 full day)', 48: ' (2 days)',
                          72: ' (3 days)', 96: ' (4 days)'}
        _TIME_ITEMS = [('All Data', 'Show all available data — no time restriction')]
        for _h in range(1, 49):
            _note = _SPECIAL_NOTES.get(_h, '')
            _unit = 'hour' if _h == 1 else 'hours'
            _TIME_ITEMS.append((str(_h), f'Last {_h} {_unit} of data{_note}'))

        self.time_range_combo = QComboBox()
        self.time_range_combo.setFixedWidth(80)  # wide enough for 'All Data' / 'From Graph'
        for _label, _tip in _TIME_ITEMS:
            self.time_range_combo.addItem(_label)
            _idx = self.time_range_combo.count() - 1
            self.time_range_combo.setItemData(_idx, _tip, Qt.ItemDataRole.ToolTipRole)
        self.time_range_combo.setToolTip(
            'Select how many hours of recent data to display.\n'
            'Applies immediately across all tabs (Diagram, Graph, Calculations, Diagnostics).\n'
            '"All Data" shows the complete loaded dataset.'
        )
        # Map legacy text keys to new numeric strings for sessions saved with old UI
        _LEGACY_MAP = {
            'Last 30 min': '0.5', 'Last 1 hr': '1',  'Last 2 hr':  '2',
            'Last 4 hr':   '4',   'Last 8 hr': '8',  'Last 16 hr': '16',
            'Last 24 hr':  '24',  'Last 48 hr': '48',
            '1 Hour': '1', '3 Hours': '3', '8 Hours': '8',
            '16 Hours': '16', '24 Hours': '24', '48 Hours': '48',
        }
        _current = _LEGACY_MAP.get(self.data_manager.time_range, self.data_manager.time_range)
        if self.time_range_combo.findText(_current) >= 0:
            self.time_range_combo.setCurrentText(_current)
        else:
            self.time_range_combo.setCurrentText('All Data')
        self.time_range_combo.currentTextChanged.connect(self._on_time_range_changed)

        hours_lbl = QLabel('hours')
        hours_lbl.setToolTip('Unit is hours — except "All Data"')
        hours_lbl.setStyleSheet('color: #666; font-size: 11px; padding-left: 2px;')

        time_row.addWidget(time_lbl)
        time_row.addWidget(self.time_range_combo)
        time_row.addWidget(hours_lbl)
        time_row.addStretch()
        content_layout.addLayout(time_row)

        # --- Row 3: Search + Graph All in one row (no GroupBox) ---
        search_row = QHBoxLayout()
        search_row.setContentsMargins(4, 2, 4, 2)
        search_row.setSpacing(4)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText('Search sensors...')

        self.select_all_graph_checkbox = QCheckBox()
        self.select_all_graph_checkbox.setTristate(True)
        self.select_all_graph_checkbox.setToolTip('Graph All — check/uncheck all sensors for graphing')

        search_row.addWidget(self.search_bar)
        search_row.addWidget(self.select_all_graph_checkbox)
        content_layout.addLayout(search_row)

        # --- Sensor tree ---
        self.sensor_tree = QTreeWidget()
        self.sensor_tree.setHeaderLabels(['▼ Sensor', 'Sensor #', 'Graph'])
        self.sensor_tree.setColumnWidth(0, 200)
        self.sensor_tree.setColumnWidth(1, 60)
        self.sensor_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.sensor_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sensor_tree.header().sectionDoubleClicked.connect(self.toggle_expand_all)
        self.sensor_tree.header().setToolTip('Double-click to expand/collapse all groups')
        self.all_expanded = True
        content_layout.addWidget(self.sensor_tree, 1)

        # --- Stats footer ---
        footer = QFrame()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(6, 4, 6, 4)
        self.stats_label = QLabel('Sensors: 0 | Mapped: 0 | Selected: 0')
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stats_label.setStyleSheet('background-color: #f0f0f0; padding: 6px; border-top: 1px solid #ddd;')
        self.mapping_report_button = QPushButton("Mapping report...")
        self.mapping_report_button.clicked.connect(self.show_mapping_report)
        self.mapping_report_button.setEnabled(False)
        footer_layout.addWidget(self.stats_label, 1)
        footer_layout.addWidget(self.mapping_report_button)
        main_layout.addWidget(footer)

    def connect_signals(self):
        self.sensor_tree.itemClicked.connect(self.on_item_clicked)
        self.search_bar.textChanged.connect(self.filter_tree_and_select)
        self.sensor_tree.customContextMenuRequested.connect(self.show_context_menu)
        self.select_all_graph_checkbox.stateChanged.connect(self.on_select_all_graph_changed)
        self.refresh_button.clicked.connect(self.force_refresh)
        
        # Connect strictly to sensor mapping change for lightweight updates
        if hasattr(self.data_manager, 'sensor_mapping_changed'):
             self.data_manager.sensor_mapping_changed.connect(self.on_sensor_mapping_changed)
        if hasattr(self.data_manager, 'selection_changed'):
             self.data_manager.selection_changed.connect(self._on_selection_changed)

    def _on_time_range_changed(self, time_range: str):
        """Propagate time range selection to data_manager (affects all tabs)."""
        if time_range == 'From Graph':
            # 'From Graph' is a display alias — the custom range is already applied by the graph;
            # just leave data_manager's custom range in place, don't reset it.
            return
        self.data_manager.set_time_range(time_range)

    def set_time_range_display(self, text: str):
        """Update the time range combo to 'From Graph' when graph applies a custom range."""
        # Normalise: internal 'Custom' string is displayed as 'From Graph'
        _display = 'From Graph' if text == 'Custom' else text
        if self.time_range_combo.findText(_display) == -1:
            self.time_range_combo.addItem(_display)
        self.time_range_combo.blockSignals(True)
        self.time_range_combo.setCurrentText(_display)
        self.time_range_combo.blockSignals(False)

    def on_item_clicked(self, item, column):
        """Handles clicks on tree items."""
        # --- GROUP ITEM CLICKED ---
        if item.childCount() > 0:
            if column == 2:  # Graph checkbox on group
                self.toggle_group_graph(item)
            else:  # Select all sensors in group
                self.select_all_in_group(item)
            return

        # --- SENSOR ITEM CLICKED ---
        sensor_name = self._sensor_key_for_item(item)
        if column == 2:
            is_checked = item.checkState(2) == Qt.CheckState.Checked
            self.data_manager.set_sensor_graphed(sensor_name, is_checked)
            self.data_manager.data_changed.emit()
        else:
            # Check if Ctrl or Shift is pressed for multi-selection
            from PyQt6.QtWidgets import QApplication
            modifiers = QApplication.keyboardModifiers()
            is_multi_select = (modifiers == Qt.KeyboardModifier.ControlModifier or 
                             modifiers == Qt.KeyboardModifier.ShiftModifier)
            
            self.data_manager.toggle_sensor_selection(sensor_name, multi_select=is_multi_select)
            self.sensor_locate_requested.emit(
                sensor_name,
                item.data(0, Qt.ItemDataRole.UserRole + 1) or "",
                item.data(0, Qt.ItemDataRole.UserRole + 2) or "",
            )
    
    def on_select_all_graph_changed(self, state):
        """Handles the select all graph checkbox toggle."""
        # If partially checked, treat click as "check all"
        if state == Qt.CheckState.PartiallyChecked.value:
            is_checked = True
        else:
            is_checked = state == Qt.CheckState.Checked.value
        
        # Get all visible/planned sensors. In expected-table mode this returns
        # mapped CSV labels when available, while keeping default labels visible.
        all_sensors = self._visible_sensor_keys() or self.data_manager.get_sensor_list()
        
        # Update all sensors' graph state
        for sensor_name in all_sensors:
            self.data_manager.set_sensor_graphed(sensor_name, is_checked)
        
        # Emit data changed to update UI
        self.data_manager.data_changed.emit()

    def show_context_menu(self, position):
        """Creates and displays the right-click menu."""
        menu = QMenu()
        item_under_cursor = self.sensor_tree.itemAt(position)
        if item_under_cursor and item_under_cursor.childCount() == 0 and not item_under_cursor.isSelected():
            self.sensor_tree.clearSelection()
            item_under_cursor.setSelected(True)
        selected_items = self.sensor_tree.selectedItems()

        if not selected_items:
            return

        # --- Menu actions for SENSOR items ---
        if all(item.childCount() == 0 for item in selected_items):
            if len(selected_items) == 1 and self._item_needs_diagram_assignment(selected_items[0]):
                assign_action = QAction("Assign to diagram spot...", self)
                assign_action.triggered.connect(
                    lambda checked=False, item=selected_items[0]: self._assign_item_to_diagram_spot(item)
                )
                menu.addAction(assign_action)

                alias_action = QAction("Save as alias of...", self)
                alias_action.triggered.connect(
                    lambda checked=False, item=selected_items[0]: self._save_item_as_alias(item)
                )
                menu.addAction(alias_action)
                menu.addSeparator()

            group_action = QAction("Group Selected Sensors", self)
            group_action.triggered.connect(self.group_selected_sensors)
            menu.addAction(group_action)

            cut_action = QAction("Cut", self)
            cut_action.triggered.connect(self.cut_sensors)
            menu.addAction(cut_action)

        # --- Menu actions for GROUP items ---
        if item_under_cursor and item_under_cursor.childCount() >= 0 and item_under_cursor.parent() is None:
            rename_action = QAction("Rename Group", self)
            rename_action.triggered.connect(lambda: self.rename_group(item_under_cursor))
            menu.addAction(rename_action)

            if self.clipboard:
                paste_action = QAction(f"Paste {len(self.clipboard)} sensor(s)", self)
                paste_action.triggered.connect(lambda: self.paste_sensors(item_under_cursor))
                menu.addAction(paste_action)
            
            delete_action = QAction("Delete Group", self)
            delete_action.triggered.connect(lambda: self.delete_group(item_under_cursor))
            menu.addAction(delete_action)

        if menu.actions():
            menu.exec(self.sensor_tree.viewport().mapToGlobal(position))

    def _item_needs_diagram_assignment(self, item) -> bool:
        if item is None or item.childCount() > 0:
            return False
        if getattr(self.data_manager, 'csv_data', None) is None:
            return False
        return bool(item.data(0, Qt.ItemDataRole.UserRole + 3))

    def _assign_item_to_diagram_spot(self, item):
        sensor_name = self._sensor_key_for_item(item)
        if not sensor_name:
            return
        self.data_manager.set_sensor_selected(sensor_name, True)
        self.sensor_locate_requested.emit(
            sensor_name,
            item.data(0, Qt.ItemDataRole.UserRole + 1) or "",
            item.data(0, Qt.ItemDataRole.UserRole + 2) or "",
        )
        print(f"[MAP] Ready to assign CSV sensor '{sensor_name}' to a revealed diagram spot")

    def _save_item_as_alias(self, item):
        sensor_name = self._sensor_key_for_item(item)
        if not sensor_name:
            return
        rows = []
        seen = set()
        for row in self.data_manager.get_expected_sensor_rows(include_disabled=True):
            canonical = (row.get('canonical') or '').strip()
            if not canonical or canonical in seen:
                continue
            seen.add(canonical)
            label = row.get('human_label') or row.get('default_label') or canonical
            rows.append((f"{label}  [{canonical}]", canonical))
        rows.sort(key=lambda item: item[0].lower())
        if not rows:
            print(f"[ALIAS_DB] No diagram sensors available for alias '{sensor_name}'")
            return
        labels = [label for label, _canonical in rows]
        selected, ok = QInputDialog.getItem(
            self,
            "Save sensor alias",
            f"Treat this CSV sensor as:",
            labels,
            0,
            False
        )
        if not ok or not selected:
            return
        canonical = dict(rows).get(selected)
        if not canonical:
            return
        warnings = []
        try:
            from sensor_canonical import _canonical_from_box_label
            pattern = _canonical_from_box_label(sensor_name)
            if pattern and pattern[0] and pattern[0] != canonical:
                warnings.append(
                    f"Pattern resolver expects {pattern[0]}, but you chose {canonical}."
                )
        except Exception:
            pass
        try:
            roles = self.data_manager.diagram_model.get('sensor_roles') or {}
            for row in self.data_manager.get_expected_sensor_rows(include_disabled=True):
                if row.get('canonical') == canonical:
                    mapped = roles.get(row.get('role_key') or '')
                    if mapped and mapped != sensor_name:
                        warnings.append(
                            f"{canonical} is already occupied by '{mapped}'."
                        )
                        break
        except Exception:
            pass
        if warnings:
            msg = "\n".join(warnings) + "\n\nSave this alias anyway?"
            answer = QMessageBox.question(
                self,
                "Confirm alias override",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.data_manager.learn_sensor_alias(canonical, sensor_name)
        try:
            self.data_manager.auto_map_csv_to_canonical(self.data_manager.get_sensor_list())
        except Exception as exc:
            print(f"[ALIAS_DB] Auto-map after alias save failed: {exc}")
        self.update_ui()

    def group_selected_sensors(self):
        """Prompts for a group name and tells the DataManager to group selected sensors."""
        selected_sensors = [item.text(0) for item in self.sensor_tree.selectedItems() if item.childCount() == 0]
        if not selected_sensors:
            return

        text, ok = QInputDialog.getText(self, 'Create Group', 'Enter group name:')
        if ok and text:
            self.data_manager.create_group(text, selected_sensors)

    def rename_group(self, group_item):
        """Prompts for a new name and renames the group in the DataManager."""
        old_name = group_item.text(0)
        new_name, ok = QInputDialog.getText(self, 'Rename Group', 'Enter new name:', text=old_name)
        if ok and new_name and new_name != old_name:
            self.data_manager.rename_group(old_name, new_name)
    
    def delete_group(self, group_item):
        """Deletes the group from the DataManager."""
        group_name = group_item.text(0)
        reply = QMessageBox.question(self, 'Delete Group', 
                                     f'Are you sure you want to delete the group "{group_name}"?\n\nSensors will be moved to Ungrouped.',
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.data_manager.delete_group(group_name)

    def cut_sensors(self):
        """Copies selected sensor names to the internal clipboard."""
        self.clipboard = [item.text(0) for item in self.sensor_tree.selectedItems() if item.childCount() == 0]
        print(f"Cut {len(self.clipboard)} sensors to clipboard.")

    def paste_sensors(self, target_group_item):
        """Moves sensors from the clipboard to the target group in the DataManager."""
        if not self.clipboard:
            return
        
        target_group_name = target_group_item.text(0)
        self.data_manager.move_sensors_to_group(target_group_name, self.clipboard)
        self.clipboard.clear()

    def update_ui(self):
        """Redraws the sensor list with groups based on the DataManager's state."""
        # Save expansion states and search text before clearing
        expansion_states = {}
        iterator = QTreeWidgetItemIterator(self.sensor_tree)
        while iterator.value():
            item = iterator.value()
            if item.childCount() > 0:  # Is a group
                expansion_states[item.text(0)] = item.isExpanded()
            iterator += 1
        
        # Save current search text
        current_search = self.search_bar.text()
        
        self.sensor_tree.clear()

        self.mapping_report_button.setEnabled(self.data_manager.csv_data is not None)

        csv_rows = []
        if self.data_manager.csv_data is not None and getattr(self.data_manager, 'get_csv_sensor_rows', None):
            csv_rows = self.data_manager.get_csv_sensor_rows()
        if csv_rows:
            self._populate_csv_sensor_rows(csv_rows, expansion_states)
            self.update_stats()
            self.update_select_all_graph_checkbox()
            if current_search:
                self.filter_tree_and_select(current_search, auto_select=False)
            return

        expected_rows = []
        expected_rows = self.data_manager.get_expected_sensor_rows()
        if expected_rows:
            self._populate_expected_sensor_rows(expected_rows, expansion_states)
            self.update_stats()
            self.update_select_all_graph_checkbox()
            if current_search:
                self.filter_tree_and_select(current_search, auto_select=False)
            return
        
        all_sensors = set(self.data_manager.get_sensor_list())
        grouped_sensors = set()

        # Create items for each group and its sensors
        for group_name, sensor_list in sorted(self.data_manager.sensor_groups.items()):
            group_item = QTreeWidgetItem(self.sensor_tree, [group_name])
            # Restore expansion state (default to True for new groups)
            group_item.setExpanded(expansion_states.get(group_name, True))
            group_item.setFlags(group_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            group_item.setCheckState(2, Qt.CheckState.Unchecked)  # Start unchecked
            # Subtle background for group headers across all columns
            group_item.setBackground(0, QColor("#e3f2fd"))  # Light blue
            group_item.setBackground(1, QColor("#e3f2fd"))
            group_item.setBackground(2, QColor("#e3f2fd"))
            for sensor_name in sorted(sensor_list):
                if sensor_name in all_sensors:
                    self.create_sensor_item(sensor_name, group_item)
                    grouped_sensors.add(sensor_name)
            self.update_group_checkbox_state(group_item)
        
        # Create "Ungrouped" for any remaining sensors
        ungrouped_list = sorted(list(all_sensors - grouped_sensors))
        if ungrouped_list:
            ungrouped_item = QTreeWidgetItem(self.sensor_tree, ["Ungrouped"])
            ungrouped_item.setExpanded(expansion_states.get("Ungrouped", True))
            ungrouped_item.setFlags(ungrouped_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            ungrouped_item.setCheckState(2, Qt.CheckState.Unchecked)
            ungrouped_item.setBackground(0, QColor("#e3f2fd"))  # Light blue
            ungrouped_item.setBackground(1, QColor("#e3f2fd"))
            ungrouped_item.setBackground(2, QColor("#e3f2fd"))
            for sensor_name in ungrouped_list:
                self.create_sensor_item(sensor_name, ungrouped_item)
            self.update_group_checkbox_state(ungrouped_item)

        self.update_stats()
        
        # Update the "Select All Graph" checkbox state
        self.update_select_all_graph_checkbox()
        
        # Reapply search filter if there was one (don't auto-select when reapplying)
        if current_search:
            self.filter_tree_and_select(current_search, auto_select=False)
        
        # Note: Removed automatic group expansion when sensors are selected
        # Users can manually expand groups as needed

    def _populate_expected_sensor_rows(self, expected_rows, expansion_states):
        """Render generated diagram sensors before a CSV has been loaded."""
        by_group = {}
        for row in expected_rows:
            by_group.setdefault(row.get('group') or 'Other Sensors', []).append(row)

        for group_name, rows in sorted(by_group.items()):
            mapped_count = sum(1 for row in rows if row.get('mapped_label'))
            group_item = QTreeWidgetItem(self.sensor_tree, [f"{group_name} ({mapped_count}/{len(rows)})"])
            group_item.setExpanded(expansion_states.get(group_name, True))
            group_item.setFlags(group_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            group_item.setCheckState(2, Qt.CheckState.Unchecked)
            group_item.setBackground(0, QColor("#e3f2fd"))
            group_item.setBackground(1, QColor("#e3f2fd"))
            group_item.setBackground(2, QColor("#e3f2fd"))
            for row in rows:
                self.create_expected_sensor_item(row, group_item)
            self.update_group_checkbox_state(group_item)

    def _populate_csv_sensor_rows(self, csv_rows, expansion_states):
        """Render only CSV-backed rows once real data is loaded."""
        by_group = {}
        for row in csv_rows:
            group_name = row.get('group') or 'Mapped Sensors'
            if row.get('not_on_diagram'):
                group_name = 'Not on diagram'
            by_group.setdefault(group_name, []).append(row)

        for group_name, rows in sorted(by_group.items(), key=lambda kv: (kv[0] == 'Not on diagram', kv[0])):
            group_item = QTreeWidgetItem(self.sensor_tree, [f"{group_name} ({len(rows)})"])
            group_item.setExpanded(expansion_states.get(group_name, True))
            group_item.setFlags(group_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            group_item.setCheckState(2, Qt.CheckState.Unchecked)
            group_item.setBackground(0, QColor("#e3f2fd"))
            group_item.setBackground(1, QColor("#e3f2fd"))
            group_item.setBackground(2, QColor("#e3f2fd"))
            for row in rows:
                self.create_csv_sensor_item(row, group_item)
            self.update_group_checkbox_state(group_item)

    def create_expected_sensor_item(self, row, parent_item):
        """Create a planned/default sensor row from the generated diagram."""
        label = row.get('default_label') or row.get('canonical') or ''
        mapped_label = row.get('mapped_label')
        sensor_key = mapped_label or label
        sensor_item = QTreeWidgetItem(parent_item)
        sensor_item.setText(0, label)
        sensor_item.setText(1, mapped_label or "-")
        sensor_item.setData(0, Qt.ItemDataRole.UserRole, sensor_key)
        sensor_item.setData(0, Qt.ItemDataRole.UserRole + 1, row.get('role_key') or '')
        sensor_item.setData(0, Qt.ItemDataRole.UserRole + 2, row.get('canonical') or '')
        sensor_item.setToolTip(
            0,
            f"Default label: {label}\n"
            f"Canonical: {row.get('canonical') or ''}\n"
            f"Lab/CSV label: {mapped_label or '(no matching column in loaded CSV)'}\n"
            f"Location: {row.get('human_label') or ''}"
        )
        sensor_item.setToolTip(
            1,
            "Lab/CSV label currently mapped to this diagram point"
            if mapped_label else "No matching column in the loaded CSV"
        )

        is_visible_role = row.get('is_visible_diagram_role', True)
        if sensor_key in self.data_manager.selected_sensors or label in self.data_manager.selected_sensors:
            color = QColor("#ffc107")
        elif mapped_label and is_visible_role:
            color = QColor("#c8e6c9")
        elif mapped_label:
            color = QColor("#bbdefb")
        else:
            color = QColor("#eeeeee")
            font = sensor_item.font(0)
            font.setItalic(True)
            sensor_item.setFont(0, font)
            sensor_item.setFont(1, font)

        sensor_item.setBackground(0, color)
        sensor_item.setBackground(1, color)
        sensor_item.setBackground(2, color)
        sensor_item.setFlags(sensor_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        sensor_item.setCheckState(
            2,
            Qt.CheckState.Checked if sensor_key in self.data_manager.graph_sensors else Qt.CheckState.Unchecked
        )

    def create_csv_sensor_item(self, row, parent_item):
        csv_column = row.get('csv_column') or ''
        label = row.get('display_label') or csv_column
        sensor_item = QTreeWidgetItem(parent_item)
        sensor_item.setText(0, label)
        number = row.get('sensor_number')
        sensor_item.setText(1, str(number) if number is not None else "")
        sensor_item.setData(0, Qt.ItemDataRole.UserRole, csv_column)
        sensor_item.setData(0, Qt.ItemDataRole.UserRole + 1, row.get('role_key') or '')
        sensor_item.setData(0, Qt.ItemDataRole.UserRole + 2, row.get('canonical') or '')
        sensor_item.setData(0, Qt.ItemDataRole.UserRole + 3, bool(row.get('not_on_diagram')))
        sensor_item.setToolTip(
            0,
            f"CSV sensor: {csv_column}\n"
            f"Diagram location: {row.get('human_label') or '(not on diagram)'}\n"
            f"Canonical: {row.get('canonical') or '(none)'}"
        )

        if csv_column in self.data_manager.selected_sensors:
            color = QColor("#ffc107")
        elif row.get('on_diagram'):
            color = QColor("#c8e6c9")
        elif row.get('not_on_diagram'):
            color = QColor("#eeeeee")
            font = sensor_item.font(0)
            font.setItalic(True)
            sensor_item.setFont(0, font)
            sensor_item.setFont(1, font)
        else:
            color = QColor("#bbdefb")

        sensor_item.setBackground(0, color)
        sensor_item.setBackground(1, color)
        sensor_item.setBackground(2, color)
        sensor_item.setFlags(sensor_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        sensor_item.setCheckState(
            2,
            Qt.CheckState.Checked if csv_column in self.data_manager.graph_sensors else Qt.CheckState.Unchecked
        )

    def show_mapping_report(self):
        report = self.data_manager.get_auto_map_report() if getattr(self.data_manager, 'get_auto_map_report', None) else {}
        dlg = QDialog(self)
        dlg.setWindowTitle("Mapping report")
        dlg.resize(780, 620)
        layout = QVBoxLayout(dlg)
        text = QTextEdit()
        text.setReadOnly(True)
        lines = []
        lines.append(f"CSV columns: {report.get('csv_columns', 0)}")
        lines.append(f"Mapped columns: {report.get('mapped', 0)}")
        lines.append(f"Expected diagram slots: {report.get('expected_canonical', 0)}")
        lines.append("")
        lines.append("Mapped columns")
        mapped = report.get('mapped_columns') or {}
        if mapped:
            for csv_name, info in sorted(mapped.items()):
                lines.append(f"  {csv_name} -> {info.get('canonical')} [{info.get('role_key')}]")
        else:
            lines.append("  (none)")
        lines.append("")
        lines.append("CSV columns with no matching diagram/alias")
        unknown = report.get('unmapped_csv') or []
        lines.extend([f"  {name}" for name in unknown] or ["  (none)"])
        lines.append("")
        lines.append("Conflicts")
        no_role_conflicts = report.get('known_but_no_role') or []
        conflicts = report.get('known_but_filled') or []
        if no_role_conflicts:
            for item in no_role_conflicts:
                lines.append(
                    f"  {item.get('csv')} -> {item.get('canonical')} "
                    "(known alias, but this diagram has no matching slot)"
                )
        if conflicts:
            for item in conflicts:
                occupied = item.get('occupied') or []
                occupied_text = "; ".join(
                    f"{occ.get('role_key')} occupied by {occ.get('csv') or '(unknown)'}"
                    for occ in occupied
                ) or ", ".join(item.get('role_keys') or [])
                lines.append(f"  {item.get('csv')} -> {item.get('canonical')} ({occupied_text})")
        if not no_role_conflicts and not conflicts:
            lines.append("  (none)")
        lines.append("")
        lines.append("Diagram slots with no CSV column")
        missing = report.get('unmapped_expected') or []
        if missing:
            for item in missing:
                lines.append(f"  {item.get('canonical')} [{', '.join(item.get('role_keys') or [])}]")
        else:
            lines.append("  (none)")
        lines.append("")
        lines.append("Ignored CSV columns")
        ignored = report.get('ignored_csv') or []
        lines.extend([f"  {name}" for name in ignored] or ["  (none)"])
        integrity = (
            self.data_manager.get_mapping_integrity_report()
            if getattr(self.data_manager, 'get_mapping_integrity_report', None)
            else {}
        )
        lines.append("")
        lines.append("Mapping integrity")
        violation_count = integrity.get('violation_count', 0)
        lines.append(f"  Source: {integrity.get('source', 'not run')}")
        lines.append(f"  Violations: {violation_count}")
        violations = integrity.get('violations') or {}
        if violations:
            for name, items in violations.items():
                lines.append(f"  {name}: {len(items)}")
                for item in items[:10]:
                    lines.append(f"    {item}")
                if len(items) > 10:
                    lines.append(f"    ... {len(items) - 10} more")
        else:
            lines.append("  A-D: OK")
        text.setPlainText("\n".join(lines))
        layout.addWidget(text)
        row = QHBoxLayout()
        export = QPushButton("Export CSV")
        relearn = QPushButton("Re-learn conflicts")
        relearn.setEnabled(bool(report.get('known_but_filled')))
        close = QPushButton("Close")
        export.clicked.connect(lambda: self._export_mapping_report(report))
        relearn.clicked.connect(lambda: self._relearn_mapping_conflicts(dlg))
        close.clicked.connect(dlg.accept)
        row.addWidget(export)
        row.addWidget(relearn)
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)
        dlg.exec()

    def _relearn_mapping_conflicts(self, dialog=None):
        if not hasattr(self.data_manager, 'relearn_known_but_filled_conflicts'):
            return
        removed = self.data_manager.relearn_known_but_filled_conflicts()
        print(f"[ALIAS_DB] Re-learn conflicts removed {removed} learned alias entr{'y' if removed == 1 else 'ies'}")
        self.update_ui()
        if dialog is not None:
            dialog.accept()
            self.show_mapping_report()

    def _export_mapping_report(self, report):
        from PyQt6.QtWidgets import QFileDialog
        import csv
        path, _ = QFileDialog.getSaveFileName(self, "Export Mapping Report", "mapping_report.csv", "CSV Files (*.csv)")
        if not path:
            return
        if not path.lower().endswith('.csv'):
            path += '.csv'
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["section", "csv_column", "canonical", "role_key"])
            for csv_name, info in sorted((report.get('mapped_columns') or {}).items()):
                writer.writerow(["mapped", csv_name, info.get('canonical'), info.get('role_key')])
            for csv_name in report.get('unmapped_csv') or []:
                writer.writerow(["unmapped_csv", csv_name, "", ""])
            for item in report.get('unmapped_expected') or []:
                for role_key in item.get('role_keys') or [""]:
                    writer.writerow(["no_csv_for_diagram_slot", "", item.get('canonical'), role_key])
            for item in report.get('known_but_filled') or []:
                occupied = "; ".join(
                    f"{occ.get('role_key')} occupied by {occ.get('csv') or ''}"
                    for occ in item.get('occupied') or []
                )
                writer.writerow(["conflict", item.get('csv'), item.get('canonical'), occupied])
            for item in report.get('known_but_no_role') or []:
                writer.writerow(["conflict_no_role", item.get('csv'), item.get('canonical'), ""])
            for csv_name in report.get('ignored_csv') or []:
                writer.writerow(["ignored_csv", csv_name, "", ""])

    def _sensor_key_for_item(self, item):
        """Return the operational sensor key for a visible row.

        Expected rows display the default lab label in column 0, but once a CSV
        is mapped the actual dataframe column must be used for selection and
        graphing.
        """
        key = item.data(0, Qt.ItemDataRole.UserRole)
        return key or item.text(0)

    def _visible_sensor_keys(self):
        keys = []
        iterator = QTreeWidgetItemIterator(self.sensor_tree)
        while iterator.value():
            item = iterator.value()
            if item.childCount() == 0:
                keys.append(self._sensor_key_for_item(item))
            iterator += 1
        return keys

    def _on_selection_changed(self):
        self.update_ui()
    
    def create_sensor_item(self, sensor_name, parent_item):
        """Helper function to create and configure a single sensor item."""
        sensor_item = QTreeWidgetItem(parent_item)
        sensor_item.setText(0, sensor_name)
        
        # Priority: Selected > visible diagram mapping > off-diagram mapping > unmapped.
        if sensor_name in self.data_manager.selected_sensors:
            color = QColor("#ffc107")  # Yellow for selected
        elif (getattr(self.data_manager, 'is_sensor_mapped_to_visible_role', None)
              and self.data_manager.is_sensor_mapped_to_visible_role(sensor_name)):
            color = QColor("#c8e6c9")  # Light green for mapped to a visible diagram dot
        elif (getattr(self.data_manager, 'is_sensor_mapped_in_roles', None)
              and self.data_manager.is_sensor_mapped_in_roles(sensor_name)):
            color = QColor("#bbdefb")  # Light blue for mapped off the process diagram
        else:
            color = QColor("#ffccbc")  # Light orange for unmapped
        
        sensor_item.setBackground(0, color)
        sensor_item.setBackground(1, color)
        sensor_item.setBackground(2, color)
        
        # Show sensor number in the Value column
        sensor_number = self.data_manager.get_sensor_number(sensor_name)
        if sensor_number is not None:
            sensor_item.setText(1, str(sensor_number))
        else:
            sensor_item.setText(1, "N/A")
        
        sensor_item.setFlags(sensor_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        if sensor_name in self.data_manager.graph_sensors:
             sensor_item.setCheckState(2, Qt.CheckState.Checked)
        else:
             sensor_item.setCheckState(2, Qt.CheckState.Unchecked)

    def filter_tree_and_select(self, text, auto_select=True):
        """Filters the tree and optionally auto-selects all visible items."""
        if auto_select:
            self.sensor_tree.clearSelection()
        iterator = QTreeWidgetItemIterator(self.sensor_tree)
        is_hidden = text.lower() != ""
        
        # First pass: hide/show sensors based on search
        while iterator.value():
            item = iterator.value()
            if item.childCount() == 0: # Is a sensor item
                matches = text.lower() in item.text(0).lower()
                item.setHidden(is_hidden and not matches)
                if auto_select and not item.isHidden():
                    item.setSelected(True)
            iterator += 1
        
        # Second pass: hide groups that have no visible sensors
        iterator = QTreeWidgetItemIterator(self.sensor_tree)
        while iterator.value():
            item = iterator.value()
            if item.childCount() > 0:  # Is a group item
                # Check if any child sensors are visible
                has_visible_children = False
                for i in range(item.childCount()):
                    child = item.child(i)
                    if not child.isHidden():
                        has_visible_children = True
                        break
                # Hide the group if no children are visible
                item.setHidden(is_hidden and not has_visible_children)
            iterator += 1

    def toggle_expand_all(self, section):
        """Double-click header to collapse/expand all groups."""
        if section == 0:  # Only on first column
            iterator = QTreeWidgetItemIterator(self.sensor_tree)
            # Check if any group is expanded
            any_expanded = False
            while iterator.value():
                item = iterator.value()
                if item.childCount() > 0 and item.isExpanded():
                    any_expanded = True
                    break
                iterator += 1

            # Toggle all groups
            iterator = QTreeWidgetItemIterator(self.sensor_tree)
            while iterator.value():
                item = iterator.value()
                if item.childCount() > 0:
                    item.setExpanded(not any_expanded)
                iterator += 1

            # Update header visual indicator
            self.all_expanded = not any_expanded
            chevron = "▼" if self.all_expanded else "▶"
            self.sensor_tree.headerItem().setText(0, f"{chevron} Sensor")
    
    def select_all_in_group(self, group_item):
        """Selects all sensors in a group."""
        from PyQt6.QtWidgets import QApplication
        modifiers = QApplication.keyboardModifiers()
        is_multi_select = (modifiers == Qt.KeyboardModifier.ControlModifier or 
                         modifiers == Qt.KeyboardModifier.ShiftModifier)
        
        if not is_multi_select:
            self.data_manager.selected_sensors.clear()
        
        for i in range(group_item.childCount()):
            child = group_item.child(i)
            sensor_name = self._sensor_key_for_item(child)
            self.data_manager.selected_sensors.add(sensor_name)
        
        self.data_manager.selection_changed.emit()
    
    def update_group_checkbox_state(self, group_item):
        """Updates group checkbox based on children states."""
        if group_item.childCount() == 0:
            return
        
        all_checked = True
        any_checked = False
        for i in range(group_item.childCount()):
            child = group_item.child(i)
            if child.checkState(2) == Qt.CheckState.Checked:
                any_checked = True
            else:
                all_checked = False
        
        if all_checked:
            group_item.setCheckState(2, Qt.CheckState.Checked)
        elif any_checked:
            group_item.setCheckState(2, Qt.CheckState.PartiallyChecked)
        else:
            group_item.setCheckState(2, Qt.CheckState.Unchecked)
    
    def toggle_group_graph(self, group_item):
        """Toggles graph checkbox for all sensors in a group."""
        # Check if all children are checked
        all_checked = True
        for i in range(group_item.childCount()):
            child = group_item.child(i)
            if child.checkState(2) != Qt.CheckState.Checked:
                all_checked = False
                break
        
        # Toggle all children
        new_state = not all_checked
        for i in range(group_item.childCount()):
            child = group_item.child(i)
            sensor_name = self._sensor_key_for_item(child)
            self.data_manager.set_sensor_graphed(sensor_name, new_state)
        
        self.data_manager.data_changed.emit()
    
    def ensure_sensor_visible(self, sensor_name):
        """Ensures a sensor is visible by expanding its group if needed."""
        # Find the sensor item in the tree
        iterator = QTreeWidgetItemIterator(self.sensor_tree)
        while iterator.value():
            item = iterator.value()
            # Check if this is the sensor we're looking for
            if item.childCount() == 0 and item.text(0) == sensor_name:
                # Expand the parent group if collapsed
                parent = item.parent()
                if parent and not parent.isExpanded():
                    parent.setExpanded(True)
                # Scroll to make it visible
                self.sensor_tree.scrollToItem(item)
                return
            iterator += 1
    
    def highlight_and_scroll_to_sensor(self, sensor_name):
        """Highlights a sensor and scrolls to it, expanding its group if needed."""
        print(f"[SENSOR HIGHLIGHT] Looking for sensor '{sensor_name}'")
        
        # Clear previous selection first
        self.sensor_tree.clearSelection()
        
        # Find the sensor item in the tree
        iterator = QTreeWidgetItemIterator(self.sensor_tree)
        while iterator.value():
            item = iterator.value()
            # Check if this is the sensor we're looking for
            if item.childCount() == 0 and (
                item.text(0) == sensor_name or self._sensor_key_for_item(item) == sensor_name
            ):
                # Expand the parent group if collapsed
                parent = item.parent()
                if parent:
                    was_expanded = parent.isExpanded()
                    if not was_expanded:
                        print(f"[SENSOR HIGHLIGHT] Group '{parent.text(0)}' is collapsed, expanding...")
                        parent.setExpanded(True)
                        # Force tree widget to update its layout
                        self.sensor_tree.update()
                        self.sensor_tree.repaint()
                        print(f"[SENSOR HIGHLIGHT] Expanded group '{parent.text(0)}' for sensor '{sensor_name}'")
                    else:
                        print(f"[SENSOR HIGHLIGHT] Group '{parent.text(0)}' was already expanded")
                else:
                    print(f"[SENSOR HIGHLIGHT] Sensor has no parent group")
                
                # Scroll to make it visible
                self.sensor_tree.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
                
                # Highlight the item by selecting it
                item.setSelected(True)
                
                print(f"[SENSOR HIGHLIGHT] Highlighted and scrolled to sensor '{sensor_name}'")
                return
            iterator += 1
        
        print(f"[SENSOR HIGHLIGHT] Sensor '{sensor_name}' not found in tree")
    
    def update_select_all_graph_checkbox(self):
        """Updates the 'Select All Graph' checkbox based on current graph state."""
        all_sensors = self._visible_sensor_keys() or self.data_manager.get_sensor_list()
        if not all_sensors:
            self.select_all_graph_checkbox.setCheckState(Qt.CheckState.Unchecked)
            return
        
        # Check how many sensors are graphed
        graphed_count = sum(1 for sensor in all_sensors if sensor in self.data_manager.graph_sensors)
        total_count = len(all_sensors)
        
        # Block signals to avoid triggering the handler
        self.select_all_graph_checkbox.blockSignals(True)
        
        if graphed_count == total_count:
            # All sensors are graphed
            self.select_all_graph_checkbox.setCheckState(Qt.CheckState.Checked)
        elif graphed_count == 0:
            # No sensors are graphed
            self.select_all_graph_checkbox.setCheckState(Qt.CheckState.Unchecked)
        else:
            # Some sensors are graphed
            self.select_all_graph_checkbox.setCheckState(Qt.CheckState.PartiallyChecked)
        
        # Unblock signals
        self.select_all_graph_checkbox.blockSignals(False)

    def update_stats(self):
        total = len(self._visible_sensor_keys() or self.data_manager.get_sensor_list())
        # Prefer new mapping system count if available
        if getattr(self.data_manager, 'count_role_mappings', None):
            mapped = self.data_manager.count_role_mappings()
        else:
            mapped = len(self.data_manager.mappings)
        selected = len(getattr(self.data_manager, 'selected_sensors', set()) or set())
        text = f"Sensors: {total} | Mapped: {mapped} | Selected: {selected}"
        if getattr(self.data_manager, 'get_mapping_gaps', None):
            gaps = self.data_manager.get_mapping_gaps()
            unmapped_csv = gaps.get('unmapped_csv_count', 0)
            missing_dots = gaps.get('unmapped_expected_count', 0)
            no_role = gaps.get('known_but_no_role_count', 0)
            if unmapped_csv or missing_dots or no_role:
                text += f" | Gaps CSV:{unmapped_csv} Dots:{missing_dots}"
                if no_role:
                    text += f" NoDot:{no_role}"
        self.stats_label.setText(text)

    def on_export_audit_clicked(self):
        """Write audit_export.csv with two header rows and filtered data (overwrite)."""
        try:
            from PyQt6.QtWidgets import QFileDialog
            # Ask for target path once; default to audit_export.csv
            default_name = "audit_export.csv"
            file_path, _ = QFileDialog.getSaveFileName(self, "Save Audit CSV", default_name, "CSV Files (*.csv)")
            if not file_path:
                return
            if not file_path.lower().endswith('.csv'):
                file_path = file_path + '.csv'
            ok = False
            # Use current time-range; do not restrict to graphed sensors by default; not ON-time only by default
            if hasattr(self.data_manager, 'export_audit_csv'):
                ok = self.data_manager.export_audit_csv(output_path=file_path, include_only_graphed=False, on_time_only=False)
            if ok:
                QMessageBox.information(self, "Audit CSV Saved", f"Wrote audit CSV to:\n{file_path}")
            else:
                QMessageBox.critical(self, "Export Failed", "Failed to write the audit CSV.")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Error writing audit CSV:\n{e}")

    def on_sensor_mapping_changed(self, role_key, sensor_name, is_mapped):
        """Handle lightweight mapped status updates without full tree rebuild."""
        if self.data_manager.csv_data is not None:
            self.update_ui()
            return

        # Update stats label
        self.update_stats()
        
        # We need to find the sensor item. Since we don't have a direct map, we search.
        # This is fast enough (100 items).
        iterator = QTreeWidgetItemIterator(self.sensor_tree)
        target_found = False
        
        # Determine if unmapping or mapping
        target_sensor_name = sensor_name
        
        # If unmapping, we might receive empty sensor name, but we know the role key.
        # But wait, unmap sends empty sensor name.
        # So we can't find the item by name if it's unmapped unless we knew what it was.
        # Actually, if is_mapped=False, we might want to iterate ALL items to refresh their color 
        # or rely on the previous state?
        # Re-reading logic: unmap emits (role_key, "", False). 
        # So we don't know WHICH sensor was unmapped just from the signal arguments if name is empty.
        # However, for 'map', we know the name.
        
        # Strategy: Iterate all items and refresh their color based on current DataManager state.
        # DataManager state is already updated when this signal fires.
        # So checking is_sensor_mapped_in_roles(item.text(0)) will return the correct new state.
        
        while iterator.value():
            item = iterator.value()
            if item.childCount() == 0:  # Sensor item
                item_sensor_name = self._sensor_key_for_item(item)
                visible_label = item.text(0)
                
                # Re-evaluate color for this sensor
                if item_sensor_name in self.data_manager.selected_sensors or visible_label in self.data_manager.selected_sensors:
                    color = QColor("#ffc107")  # Yellow
                elif (getattr(self.data_manager, 'is_sensor_mapped_to_visible_role', None)
                      and self.data_manager.is_sensor_mapped_to_visible_role(item_sensor_name)):
                    color = QColor("#c8e6c9")  # Green
                elif (getattr(self.data_manager, 'is_sensor_mapped_in_roles', None)
                      and self.data_manager.is_sensor_mapped_in_roles(item_sensor_name)):
                    color = QColor("#bbdefb")  # Mapped off diagram
                else:
                    color = QColor("#ffccbc")  # Orange/Unmapped
                
                item.setBackground(0, color)
                item.setBackground(1, color)
                item.setBackground(2, color)
            iterator += 1

    def force_refresh(self):
        """Manually trigger a full data refresh."""
        print("[SENSOR PANEL] Force refresh clicked")
        self.data_manager.data_changed.emit()
