"""
Auto-detection dialog for defrost periods using pressure differential analysis.
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QSlider, QSpinBox, QPushButton, QGroupBox,
                             QTableWidget, QTableWidgetItem, QCheckBox,
                             QTextEdit, QHeaderView, QMessageBox)
from PyQt6.QtCore import Qt
from defrost_detection import (detect_defrost_periods, get_pressure_statistics,
                               get_pressure_sensors_from_compressor)
import logging


class DefrostAutoDetectDialog(QDialog):
    """Dialog for auto-detecting defrost periods using pressure differential."""

    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.detected_periods = []

        # Get pressure sensor columns from compressor port mappings
        self.discharge_col, self.suction_col = get_pressure_sensors_from_compressor(data_manager)

        if not self.discharge_col or not self.suction_col:
            QMessageBox.warning(
                parent,
                "Compressor Ports Not Mapped",
                "Please map sensors to the Compressor's SP (Suction Pressure) and "
                "DP (Discharge Pressure) ports in the diagram before using auto-detection."
            )
            self.reject()
            return

        self.setWindowTitle("Auto-Detect Defrost Periods")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)

        self.setup_ui()
        self.update_pressure_stats()

    def setup_ui(self):
        layout = QVBoxLayout()

        # ==================== Detection Parameters ====================
        params_group = QGroupBox("Detection Parameters")
        params_layout = QVBoxLayout()

        # Threshold slider
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel("Pressure Differential Threshold (psi):"))
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setMinimum(5)
        self.threshold_slider.setMaximum(20)
        self.threshold_slider.setValue(10)
        self.threshold_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.threshold_slider.setTickInterval(1)
        self.threshold_slider.valueChanged.connect(self.on_threshold_changed)
        threshold_layout.addWidget(self.threshold_slider)

        self.threshold_label = QLabel("10")
        self.threshold_label.setMinimumWidth(30)
        threshold_layout.addWidget(self.threshold_label)
        params_layout.addLayout(threshold_layout)

        # Min duration spinbox
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Minimum Duration (minutes):"))
        self.duration_spinbox = QSpinBox()
        self.duration_spinbox.setMinimum(1)
        self.duration_spinbox.setMaximum(30)
        self.duration_spinbox.setValue(2)
        duration_layout.addWidget(self.duration_spinbox)
        duration_layout.addStretch()
        params_layout.addLayout(duration_layout)

        # Detect button
        detect_btn = QPushButton("Detect Defrost Periods")
        detect_btn.clicked.connect(self.run_detection)
        params_layout.addWidget(detect_btn)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # ==================== Pressure Statistics ====================
        stats_group = QGroupBox("Pressure Statistics")
        stats_layout = QVBoxLayout()

        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setMaximumHeight(100)
        stats_layout.addWidget(self.stats_text)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # ==================== Detected Periods Table ====================
        periods_group = QGroupBox("Detected Periods")
        periods_layout = QVBoxLayout()

        self.periods_table = QTableWidget()
        self.periods_table.setColumnCount(6)
        self.periods_table.setHorizontalHeaderLabels([
            "Select", "Period #", "Start Time", "End Time", "Duration (min)", "Avg Diff (psi)"
        ])
        self.periods_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.periods_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.periods_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.periods_table.setAlternatingRowColors(True)
        self.periods_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        periods_layout.addWidget(self.periods_table)

        # Summary label
        self.summary_label = QLabel("No periods detected yet. Click 'Detect Defrost Periods' to analyze data.")
        self.summary_label.setStyleSheet("font-weight: bold; margin-top: 5px;")
        periods_layout.addWidget(self.summary_label)

        periods_group.setLayout(periods_layout)
        layout.addWidget(periods_group)

        # ==================== Action Buttons ====================
        button_layout = QHBoxLayout()

        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all_periods)
        button_layout.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self.deselect_all_periods)
        button_layout.addWidget(deselect_all_btn)

        button_layout.addStretch()

        apply_btn = QPushButton("Apply Selected")
        apply_btn.clicked.connect(self.apply_selected)
        apply_btn.setStyleSheet("font-weight: bold;")
        button_layout.addWidget(apply_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def on_threshold_changed(self, value):
        """Update threshold label when slider changes."""
        self.threshold_label.setText(str(value))

    def update_pressure_stats(self):
        """Display pressure statistics from current data."""
        df = self.data_manager.get_filtered_data()

        if df is None or df.empty:
            self.stats_text.setText("No data available.")
            return

        stats = get_pressure_statistics(df, self.discharge_col, self.suction_col)

        if not stats:
            self.stats_text.setText("Could not calculate pressure statistics.")
            return

        text = f"""Compressor Port Mappings:
  - DP (Discharge Pressure): {stats['discharge_col']} (Mean = {stats['discharge_mean']:.1f} psi)
  - SP (Suction Pressure): {stats['suction_col']} (Mean = {stats['suction_mean']:.1f} psi)

Normal Differential: Mean = {stats['differential_mean']:.1f} psi, Min = {stats['differential_min']:.1f} psi

Algorithm: Detects periods where abs(DP - SP) <= Threshold"""

        self.stats_text.setText(text)

    def run_detection(self):
        """Run defrost detection with current parameters."""
        df = self.data_manager.get_filtered_data()

        if df is None or df.empty:
            logging.warning("[AUTO_DETECT] No data available for detection")
            self.summary_label.setText("No data available.")
            return

        threshold = self.threshold_slider.value()
        min_duration = self.duration_spinbox.value()

        logging.info(f"[AUTO_DETECT] Running detection with threshold={threshold} psi, min_duration={min_duration} min")
        logging.info(f"[AUTO_DETECT] Using sensors: DP={self.discharge_col}, SP={self.suction_col}")

        self.detected_periods = detect_defrost_periods(
            df,
            self.discharge_col,
            self.suction_col,
            threshold,
            min_duration
        )

        self.populate_periods_table()

    def populate_periods_table(self):
        """Populate the table with detected periods."""
        self.periods_table.setRowCount(len(self.detected_periods))

        for row_idx, (start_time, end_time, duration, avg_diff) in enumerate(self.detected_periods):
            # Checkbox
            checkbox = QCheckBox()
            checkbox.setChecked(True)  # Default to selected
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            self.periods_table.setCellWidget(row_idx, 0, checkbox_widget)

            # Period number
            self.periods_table.setItem(row_idx, 1, QTableWidgetItem(str(row_idx + 1)))

            # Start time
            start_str = start_time.strftime("%Y-%m-%d %H:%M:%S") if hasattr(start_time, 'strftime') else str(start_time)
            self.periods_table.setItem(row_idx, 2, QTableWidgetItem(start_str))

            # End time
            end_str = end_time.strftime("%Y-%m-%d %H:%M:%S") if hasattr(end_time, 'strftime') else str(end_time)
            self.periods_table.setItem(row_idx, 3, QTableWidgetItem(end_str))

            # Duration
            self.periods_table.setItem(row_idx, 4, QTableWidgetItem(f"{duration:.1f}"))

            # Average differential
            self.periods_table.setItem(row_idx, 5, QTableWidgetItem(f"{avg_diff:.1f}"))

        # Update summary
        if self.detected_periods:
            total_duration = sum(p[2] for p in self.detected_periods)
            avg_duration = total_duration / len(self.detected_periods)

            # Get data duration
            df = self.data_manager.get_filtered_data()
            if df is not None and 'Timestamp' in df.columns and len(df) > 0:
                data_duration = (df['Timestamp'].iloc[-1] - df['Timestamp'].iloc[0]).total_seconds() / 60.0
                percentage = (total_duration / data_duration * 100) if data_duration > 0 else 0
                self.summary_label.setText(
                    f"Found {len(self.detected_periods)} defrost periods | "
                    f"Total: {total_duration:.1f} min ({percentage:.1f}% of data) | "
                    f"Average: {avg_duration:.1f} min"
                )
            else:
                self.summary_label.setText(
                    f"Found {len(self.detected_periods)} defrost periods | "
                    f"Total: {total_duration:.1f} min | Average: {avg_duration:.1f} min"
                )
        else:
            self.summary_label.setText("No defrost periods detected with current parameters.")

    def select_all_periods(self):
        """Select all periods in the table."""
        for row in range(self.periods_table.rowCount()):
            checkbox_widget = self.periods_table.cellWidget(row, 0)
            if checkbox_widget:
                checkbox = checkbox_widget.layout().itemAt(0).widget()
                checkbox.setChecked(True)

    def deselect_all_periods(self):
        """Deselect all periods in the table."""
        for row in range(self.periods_table.rowCount()):
            checkbox_widget = self.periods_table.cellWidget(row, 0)
            if checkbox_widget:
                checkbox = checkbox_widget.layout().itemAt(0).widget()
                checkbox.setChecked(False)

    def apply_selected(self):
        """Apply selected periods as delete ranges."""
        if not self.detected_periods:
            logging.warning("[AUTO_DETECT] No periods to apply")
            self.reject()
            return

        # Get selected periods
        selected_periods = []
        for row in range(self.periods_table.rowCount()):
            checkbox_widget = self.periods_table.cellWidget(row, 0)
            if checkbox_widget:
                checkbox = checkbox_widget.layout().itemAt(0).widget()
                if checkbox.isChecked():
                    start_time, end_time, duration, avg_diff = self.detected_periods[row]
                    selected_periods.append((start_time, end_time))

        if not selected_periods:
            logging.warning("[AUTO_DETECT] No periods selected")
            self.reject()
            return

        # Store selected periods
        self.selected_periods = selected_periods

        logging.info(f"[AUTO_DETECT] Applying {len(selected_periods)} defrost periods as delete ranges")

        self.accept()

    def get_selected_periods(self):
        """Return the selected periods as delete ranges."""
        return getattr(self, 'selected_periods', [])


# Import QWidget for checkbox container
from PyQt6.QtWidgets import QWidget
