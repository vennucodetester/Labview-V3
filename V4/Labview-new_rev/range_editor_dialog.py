"""
Range Editor Dialog - Set sensor value ranges for status monitoring
Supports group-level and individual sensor range configuration
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QDoubleSpinBox, QGroupBox,
                             QFormLayout, QMessageBox, QTreeWidget,
                             QTreeWidgetItem, QAbstractItemView,
                             QTreeWidgetItemIterator)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor


class RangeEditorDialog(QDialog):
    """Dialog for setting sensor value ranges with tree-based selection"""

    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.setWindowTitle("Sensor Range Editor")
        self.setMinimumSize(700, 500)

        self.temp_ranges = {}  # Temporary storage for ranges before applying
        self.group_ranges = {}  # Group-level ranges

        # Initialize temp storage with current ranges
        self.temp_ranges = self.data_manager.sensor_ranges.copy()

        self.all_expanded = True
        self.setup_ui()
        self.refresh_tree()

    def setup_ui(self):
        """Setup the dialog UI"""
        main_layout = QVBoxLayout(self)

        # Title and instructions
        title_label = QLabel("<h2>Sensor Range Editor</h2>")
        main_layout.addWidget(title_label)

        instructions = QLabel(
            "Set min/max ranges for sensors. Sensor dots will show:\n"
            "• Grey (unmapped) • Yellow (mapped, no range) "
            "• Green (in range) • Red (out of range)"
        )
        instructions.setStyleSheet("color: #555; font-size: 10px; padding: 5px;")
        main_layout.addWidget(instructions)

        # Horizontal layout: Tree | Range controls
        content_layout = QHBoxLayout()

        # Left panel: Tree (sensor-panel style)
        left_panel = self.create_tree_panel()
        content_layout.addWidget(left_panel, 1)

        # Right panel: Range input
        right_panel = self.create_range_panel()
        content_layout.addWidget(right_panel, 2)

        main_layout.addLayout(content_layout)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.clear_btn = QPushButton("Clear All Ranges")
        self.clear_btn.clicked.connect(self.clear_all_ranges)
        button_layout.addWidget(self.clear_btn)

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self.apply_ranges)
        button_layout.addWidget(self.apply_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        main_layout.addLayout(button_layout)

    def create_tree_panel(self):
        """Create the left panel with sensor-panel-style tree"""
        panel = QGroupBox("Sensors")
        layout = QVBoxLayout(panel)

        # Select All / Select None buttons
        select_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all)
        self.select_none_btn = QPushButton("Select None")
        self.select_none_btn.clicked.connect(self.select_none)
        select_layout.addWidget(self.select_all_btn)
        select_layout.addWidget(self.select_none_btn)
        select_layout.addStretch()
        layout.addLayout(select_layout)

        self.range_tree = QTreeWidget()
        self.range_tree.setHeaderLabels(["▼ Sensor"])
        self.range_tree.setColumnWidth(0, 200)
        self.range_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.range_tree.header().sectionDoubleClicked.connect(self.toggle_expand_all)
        self.range_tree.header().setToolTip("Double-click to expand/collapse all groups")
        self.range_tree.itemSelectionChanged.connect(self.on_tree_selection_changed)
        layout.addWidget(self.range_tree, 1)

        # Selected count label
        self.selected_count_label = QLabel("Selected: 0 sensors")
        self.selected_count_label.setStyleSheet("color: #555; font-size: 10px;")
        layout.addWidget(self.selected_count_label)

        return panel

    def create_range_panel(self):
        """Create the right panel for range input"""
        panel = QGroupBox("Range Settings")
        layout = QVBoxLayout(panel)

        form_layout = QFormLayout()

        # Min value
        self.min_spin = QDoubleSpinBox()
        self.min_spin.setRange(-999999, 999999)
        self.min_spin.setDecimals(2)
        self.min_spin.setValue(0)
        form_layout.addRow("Minimum Value:", self.min_spin)

        # Max value
        self.max_spin = QDoubleSpinBox()
        self.max_spin.setRange(-999999, 999999)
        self.max_spin.setDecimals(2)
        self.max_spin.setValue(100)
        form_layout.addRow("Maximum Value:", self.max_spin)

        layout.addLayout(form_layout)

        # Set range button
        self.set_range_btn = QPushButton("Set Range")
        self.set_range_btn.clicked.connect(self.set_range)
        layout.addWidget(self.set_range_btn)

        # Clear range button for selected
        self.clear_selected_btn = QPushButton("Clear Range for Selected")
        self.clear_selected_btn.clicked.connect(self.clear_selected_ranges)
        layout.addWidget(self.clear_selected_btn)

        layout.addStretch()

        # Current ranges display
        self.current_ranges_label = QLabel()
        self.current_ranges_label.setWordWrap(True)
        self.current_ranges_label.setStyleSheet(
            "background-color: #f5f5f5; padding: 10px; border: 1px solid #ccc;"
        )
        layout.addWidget(QLabel("Current Ranges:"))
        layout.addWidget(self.current_ranges_label)

        return panel

    def get_selected_sensors(self):
        """Return set of sensor names from current tree selection (expand groups to child sensors)."""
        selected = set()
        for item in self.range_tree.selectedItems():
            if item.childCount() > 0:
                # Group: add all child sensors
                for i in range(item.childCount()):
                    child = item.child(i)
                    selected.add(child.text(0))
            else:
                # Sensor
                selected.add(item.text(0))
        return selected

    def refresh_tree(self, preserve_selection=False):
        """Rebuild tree with current temp_ranges, preserving expansion state."""
        # Save expansion states before clearing
        expansion_states = {}
        iterator = QTreeWidgetItemIterator(self.range_tree)
        while iterator.value():
            item = iterator.value()
            if item.childCount() > 0:
                expansion_states[item.text(0)] = item.isExpanded()
            iterator += 1

        # Save selection if requested
        selected_sensors = self.get_selected_sensors() if preserve_selection else set()

        self.range_tree.clear()

        all_sensors = set(self.data_manager.get_sensor_list())
        if not all_sensors:
            self.range_tree.headerItem().setText(0, "▼ Sensor")
            return

        grouped_sensors = set()

        # Create items for each group and its sensors (mirror sensor_panel structure)
        for group_name, sensor_list in sorted(self.data_manager.sensor_groups.items()):
            group_item = QTreeWidgetItem(self.range_tree, [group_name])
            group_item.setExpanded(expansion_states.get(group_name, True))
            # Light green tint if all children ranged, else light blue
            if sensor_list and all(s in self.temp_ranges for s in sensor_list):
                group_item.setBackground(0, QColor("#c8e6c9"))
            else:
                group_item.setBackground(0, QColor("#e3f2fd"))
            for sensor_name in sorted(sensor_list):
                if sensor_name in all_sensors:
                    self._create_sensor_item(sensor_name, group_item)
                    grouped_sensors.add(sensor_name)

        # Create "Ungrouped" for any remaining sensors
        ungrouped_list = sorted(list(all_sensors - grouped_sensors))
        if ungrouped_list:
            ungrouped_item = QTreeWidgetItem(self.range_tree, ["Ungrouped"])
            ungrouped_item.setExpanded(expansion_states.get("Ungrouped", True))
            if all(s in self.temp_ranges for s in ungrouped_list):
                ungrouped_item.setBackground(0, QColor("#c8e6c9"))
            else:
                ungrouped_item.setBackground(0, QColor("#e3f2fd"))
            for sensor_name in ungrouped_list:
                self._create_sensor_item(sensor_name, ungrouped_item)

        # Restore selection
        if preserve_selection and selected_sensors:
            iterator = QTreeWidgetItemIterator(self.range_tree)
            while iterator.value():
                item = iterator.value()
                if item.childCount() == 0 and item.text(0) in selected_sensors:
                    item.setSelected(True)
                iterator += 1

        self.on_tree_selection_changed()

    def _create_sensor_item(self, sensor_name, parent_item):
        """Create a sensor item with ranged/not-ranged color coding."""
        sensor_item = QTreeWidgetItem(parent_item)
        sensor_item.setText(0, sensor_name)

        if sensor_name in self.temp_ranges:
            color = QColor("#c8e6c9")  # Light green for ranged
            r = self.temp_ranges[sensor_name]
            sensor_item.setToolTip(0, f"Range: [{r['min']:.1f} - {r['max']:.1f}]")
        else:
            color = QColor("#ffffff")  # Default for not ranged
            sensor_item.setToolTip(0, "No range set")

        sensor_item.setBackground(0, color)

    def toggle_expand_all(self, section):
        """Double-click header to collapse/expand all groups."""
        if section == 0:
            iterator = QTreeWidgetItemIterator(self.range_tree)
            any_expanded = False
            while iterator.value():
                item = iterator.value()
                if item.childCount() > 0 and item.isExpanded():
                    any_expanded = True
                    break
                iterator += 1

            iterator = QTreeWidgetItemIterator(self.range_tree)
            while iterator.value():
                item = iterator.value()
                if item.childCount() > 0:
                    item.setExpanded(not any_expanded)
                iterator += 1

            self.all_expanded = not any_expanded
            chevron = "▼" if self.all_expanded else "▶"
            self.range_tree.headerItem().setText(0, f"{chevron} Sensor")

    def select_all(self):
        """Select all sensors in the tree."""
        self.range_tree.clearSelection()
        iterator = QTreeWidgetItemIterator(self.range_tree)
        while iterator.value():
            item = iterator.value()
            if item.childCount() == 0:
                item.setSelected(True)
            iterator += 1
        self.on_tree_selection_changed()

    def select_none(self):
        """Clear selection."""
        self.range_tree.clearSelection()
        self.on_tree_selection_changed()

    def on_tree_selection_changed(self):
        """Handle tree selection change - update display."""
        selected = self.get_selected_sensors()
        count = len(selected)
        self.selected_count_label.setText(f"Selected: {count} sensor{'s' if count != 1 else ''}")
        self.update_current_ranges_display()

    def set_range(self):
        """Set range for all currently selected sensors."""
        min_val = self.min_spin.value()
        max_val = self.max_spin.value()

        if min_val >= max_val:
            QMessageBox.warning(
                self,
                "Invalid Range",
                "Minimum value must be less than maximum value."
            )
            return

        selected = self.get_selected_sensors()
        if not selected:
            QMessageBox.warning(
                self,
                "No Selection",
                "Please select one or more sensors or groups in the tree."
            )
            return

        range_dict = {'min': min_val, 'max': max_val}
        for sensor_name in selected:
            self.temp_ranges[sensor_name] = range_dict.copy()

        # Update group_ranges for groups that now have all sensors ranged
        for group_name, sensors in self.data_manager.sensor_groups.items():
            if sensors and all(s in self.temp_ranges for s in sensors):
                self.group_ranges[group_name] = range_dict.copy()

        QMessageBox.information(
            self,
            "Range Set",
            f"Range [{min_val:.1f} - {max_val:.1f}] set for {len(selected)} sensor(s)"
        )

        self.refresh_tree(preserve_selection=True)

    def clear_selected_ranges(self):
        """Clear ranges for selected sensors."""
        selected = self.get_selected_sensors()
        if not selected:
            QMessageBox.warning(
                self,
                "No Selection",
                "Please select one or more sensors or groups in the tree."
            )
            return

        for sensor_name in selected:
            if sensor_name in self.temp_ranges:
                del self.temp_ranges[sensor_name]

        # Clear group_ranges for groups that no longer have all sensors ranged
        for group_name in list(self.group_ranges.keys()):
            sensors = self.data_manager.sensor_groups.get(group_name, [])
            if not all(s in self.temp_ranges for s in sensors):
                del self.group_ranges[group_name]

        QMessageBox.information(
            self,
            "Ranges Cleared",
            f"Ranges cleared for {len(selected)} sensor(s)"
        )

        self.refresh_tree(preserve_selection=True)

    def clear_all_ranges(self):
        """Clear all ranges."""
        reply = QMessageBox.question(
            self,
            "Clear All Ranges",
            "Are you sure you want to clear all sensor ranges?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.temp_ranges.clear()
            self.group_ranges.clear()
            self.refresh_tree()
            QMessageBox.information(self, "Ranges Cleared", "All sensor ranges have been cleared.")

    def update_current_ranges_display(self):
        """Update the current ranges display based on selection."""
        selected = self.get_selected_sensors()
        if not selected:
            self.current_ranges_label.setText("<i>No sensors selected</i>")
            return

        range_text = f"<b>Selected:</b> {len(selected)} sensor(s)<br><br>"
        range_text += "<b>Sensors (sample):</b><br>"

        sorted_sensors = sorted(selected)
        for sensor_name in sorted_sensors[:10]:
            if sensor_name in self.temp_ranges:
                r = self.temp_ranges[sensor_name]
                range_text += f"• {sensor_name}: [{r['min']:.1f} - {r['max']:.1f}]<br>"
            else:
                range_text += f"• {sensor_name}: <i>No range</i><br>"

        if len(selected) > 10:
            range_text += f"<i>...and {len(selected) - 10} more</i><br>"

        with_range = sum(1 for s in selected if s in self.temp_ranges)
        range_text += f"<br><b>Total:</b> {with_range}/{len(selected)} sensors with ranges"

        self.current_ranges_label.setText(range_text)

    def apply_ranges(self):
        """Apply the ranges to data manager"""
        self.data_manager.sensor_ranges = self.temp_ranges.copy()
        self.data_manager.data_changed.emit()
        self.accept()
