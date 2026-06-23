import pyqtgraph as pg
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QHBoxLayout, QFrame,
                             QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
                             QToolButton, QMenu, QInputDialog, QDialog, QDialogButtonBox,
                             QLineEdit, QComboBox, QFormLayout)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QAction
import pandas as pd
from datetime import datetime
from timestamp_diagnostics import log_conversion, compare_timestamps


class SnapshotCaptureDialog(QDialog):
    """Dialog for capturing snapshots with batch selection"""

    def __init__(self, snapshot_manager, default_name, parent=None):
        super().__init__(parent)
        self.snapshot_manager = snapshot_manager
        self.setWindowTitle("Capture Snapshot")
        self.setMinimumWidth(400)

        layout = QFormLayout(self)

        # Snapshot name
        self.name_edit = QLineEdit(default_name)
        layout.addRow("Snapshot Name:", self.name_edit)

        # Batch selection
        self.batch_combo = QComboBox()
        self.batch_combo.addItem("(No Batch)", None)

        # Add existing batches
        for batch in snapshot_manager.get_all_batches():
            self.batch_combo.addItem(batch.name, batch.id)

        # Select current batch if one is active
        if snapshot_manager.current_batch_id:
            for i in range(self.batch_combo.count()):
                if self.batch_combo.itemData(i) == snapshot_manager.current_batch_id:
                    self.batch_combo.setCurrentIndex(i)
                    break

        self.batch_combo.addItem("+ Create New Batch...", "NEW")
        layout.addRow("Batch:", self.batch_combo)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

    def get_snapshot_name(self):
        """Get the entered snapshot name"""
        return self.name_edit.text().strip()

    def get_batch_id(self):
        """Get the selected batch ID or handle new batch creation"""
        selected_data = self.batch_combo.currentData()

        if selected_data == "NEW":
            # Create new batch
            batch_name, ok = QInputDialog.getText(
                self,
                "New Batch",
                "Batch Name:",
                text="Batch 1"
            )
            if ok and batch_name.strip():
                new_batch = self.snapshot_manager.create_batch(batch_name.strip())
                return new_batch.id
            return None

        return selected_data


class GraphWidget(QWidget):
    """
    Python translation of 'tab-graph.html'.
    Uses pyqtgraph for high-performance plotting and includes a detailed stats legend.
    """
    def __init__(self, data_manager):
        super().__init__()
        self.data_manager = data_manager
        
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')
        
        # Multi-range selection state
        self.range_regions = []  # List of dict: {'region': LinearRegionItem, 'mode': 'keep'|'delete'}
        
        self.setupUi()
        self.connect_signals()

    def setupUi(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        
        # --- Control Bar ---
        control_bar = QFrame()
        control_bar.setStyleSheet("background-color: #f0f0f0; border-bottom: 1px solid #ddd;")
        control_layout = QHBoxLayout(control_bar)
        
        self.reset_zoom_btn = QPushButton("Reset Zoom")
        
        # Create dropdown button for range selection
        self.range_btn = QToolButton()
        self.range_btn.setText("Range")
        self.range_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        range_menu = QMenu(self.range_btn)
        keep_action = QAction("Keep Range", self)
        keep_action.triggered.connect(lambda: self.start_range_selection('keep'))
        delete_action = QAction("Delete Range", self)
        delete_action.triggered.connect(lambda: self.start_range_selection('delete'))
        range_menu.addAction(keep_action)
        range_menu.addAction(delete_action)
        self.range_btn.setMenu(range_menu)
        self.range_btn.setToolTip("Keep Range: include data | Delete Range: exclude data")
        
        self.apply_range_btn = QPushButton("Apply Range")
        self.apply_range_btn.setEnabled(False)
        self.apply_range_btn.setToolTip("Apply the selected time range")

        self.auto_detect_btn = QPushButton("Auto-Detect Defrost")
        self.auto_detect_btn.setToolTip("Automatically detect defrost periods using pressure differential")

        self.snapshot_btn = QPushButton("📸 Capture Snapshot")
        self.snapshot_btn.setToolTip("Capture current graph view as a snapshot for comparison")

        control_layout.addWidget(self.reset_zoom_btn)
        control_layout.addWidget(self.range_btn)
        control_layout.addWidget(self.apply_range_btn)
        control_layout.addWidget(self.auto_detect_btn)
        control_layout.addWidget(self.snapshot_btn)
        control_layout.addStretch()

        # File visibility labels
        self.file_info_label = QLabel()
        self.file_info_label.setStyleSheet("font-size: 10px; color: #555;")
        self.file_info_label.setWordWrap(True)
        control_layout.addWidget(self.file_info_label)
        main_layout.addWidget(control_bar)

        # --- Plot Widget ---
        # Use DateAxisItem to show actual timestamps from CSV
        self.plot_widget = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem()})
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.getAxis('left').setLabel('Sensor Value')
        self.plot_widget.getAxis('bottom').setLabel('Time')
        
        # We are using a custom legend table, so the built-in one is not needed.
        # self.legend = self.plot_widget.addLegend() 
        main_layout.addWidget(self.plot_widget, 4) # Give plot more space

        # --- Custom Legend/Stats Table ---
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(6)
        self.stats_table.setHorizontalHeaderLabels(["Sensor Name", "Color", "Avg", "Min", "Max", "Delta"])
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.stats_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.stats_table.setMaximumHeight(250)
        main_layout.addWidget(self.stats_table, 1) # Give table minimal space

    def connect_signals(self):
        self.reset_zoom_btn.clicked.connect(self.plot_widget.autoRange)
        self.apply_range_btn.clicked.connect(self.apply_custom_range)
        self.auto_detect_btn.clicked.connect(self.auto_detect_defrost)
        self.snapshot_btn.clicked.connect(self.capture_snapshot)

    def update_ui(self):
        """Redraws the graph and stats table based on the DataManager's state."""
        print(f"[GRAPH_UPDATE] update_ui() called - START")

        # Update file visibility labels
        import os
        csv_name = os.path.basename(self.data_manager.csv_path) if self.data_manager.csv_path else "No CSV loaded"
        config_name = os.path.basename(self.data_manager.config_path) if self.data_manager.config_path else "No Config loaded"
        self.file_info_label.setText(f"CSV: {csv_name} | Config: {config_name}")

        try:
            self.plot_widget.clear()
            self.stats_table.setRowCount(0)
            print(f"[GRAPH_UPDATE] Cleared plot and table - SUCCESS")
        except Exception as e:
            print(f"[GRAPH_UPDATE] ERROR clearing plot/table: {e}")
            return

        # Use filtered data based on time range
        df = self.data_manager.get_filtered_data()
        sensors_to_plot = self.data_manager.graph_sensors

        print(f"[GRAPH_UPDATE] Data check - df: {df is not None}, sensors: {sensors_to_plot}, empty: {df.empty if df is not None else 'N/A'}")
        
        if df is None or not sensors_to_plot or df.empty:
            print(f"[GRAPH_UPDATE] No data to plot - returning early")
            return
            

        colors = ['#E74C3C', '#3498DB', '#2ECC71', '#F39C12', '#9B59B6', '#1ABC9C']
        
        timestamps = None
        unix_timestamps = None
        has_timestamps = False
        if 'Timestamp' in df.columns:
            try:
                # Convert to pandas datetime first
                timestamps = pd.to_datetime(df['Timestamp'])
                has_timestamps = True
                
                # Filter out NaT values to prevent invalid Unix timestamp conversion
                valid_mask = timestamps.notna()
                if not valid_mask.all():
                    print(f"[GRAPH] WARNING: Found {valid_mask.sum()} valid timestamps out of {len(timestamps)} total (removing NaT)")
                    timestamps = timestamps[valid_mask]
                    df = df[valid_mask].copy()  # Also filter the DataFrame to keep alignment
                
                print(f"[GRAPH] Original timestamps: {timestamps.iloc[0]} to {timestamps.iloc[-1]}")
                print(f"[GRAPH] Timestamp dtype: {timestamps.dtype}")
                print(f"[GRAPH] Timestamp timezone: {timestamps.dtype.tz if hasattr(timestamps.dtype, 'tz') else 'None'}")
                
                # CRITICAL FIX: Handle naive timestamps for DateAxisItem
                # 
                # The Problem:
                # - CSV contains: 2025-04-13 06:02:32 (local CDT time, UTC-5)
                # - When we convert to Unix naively, pandas treats it as if it's UTC
                # - This creates a 5-hour offset
                # - DateAxisItem then subtracts its utcOffset and displays UTC time
                # - Result: displayed time is shifted backward by 5 hours
                # 
                # The Solution:
                # - Convert the naive local timestamp to UTC FIRST
                # - UTC time = Local time + timezone_offset (e.g., 06:02:32 CDT + 5h = 11:02:32 UTC)
                # - Then convert this UTC time to Unix
                # - DateAxisItem will display the UTC time, but it LOOKS like local time in the chart
                # 
                # Example:
                # - CSV: 2025-04-13 06:02:32 (CDT)
                # - UTC: 2025-04-13 11:02:32 (UTC)
                # - Unix: 1744542152
                # - DateAxisItem: utcfromtimestamp(1744542152 - 18000) = utcfromtimestamp(1744524152) = 2025-04-13 06:02:32 ✅
                
                if timestamps.dt.tz is None:
                    # Naive timestamps - treat as local time
                    import time
                    
                    # Get local timezone offset in seconds
                    if time.daylight:
                        offset_sec = time.altzone  # e.g., 18000 for CDT (UTC-5)
                        tz_name = time.tzname[1]
                    else:
                        offset_sec = time.timezone
                        tz_name = time.tzname[0]
                    
                    print(f"[GRAPH] Detected local timezone: {tz_name}")
                    print(f"[GRAPH] Timezone offset from UTC: {-offset_sec}s ({-offset_sec/3600:.0f} hours)")
                    
                    # Convert local time to UTC by ADDING the offset
                    # offset_sec is POSITIVE for west of UTC (e.g., 18000 for CDT which is UTC-5)
                    # UTC time = Local time + offset_sec
                    # Example: 06:02:32 CDT + 18000s (5 hours) = 11:02:32 UTC
                    utc_timestamps = timestamps + pd.Timedelta(seconds=offset_sec)
                    
                    print(f"[GRAPH] Converted local to UTC: {utc_timestamps.iloc[0]}")
                    
                    # Now convert UTC timestamps to Unix
                    unix_timestamps = utc_timestamps.astype('int64') // 10**9
                else:
                    # Timezone-aware timestamps - convert directly to Unix
                    unix_timestamps = timestamps.astype('int64') // 10**9
                
                print(f"[GRAPH] Unix timestamps (for DateAxisItem): {unix_timestamps.iloc[0]} to {unix_timestamps.iloc[-1]}")
                # Verify what DateAxisItem will display (only for naive timestamps where time is imported)
                if timestamps.dt.tz is None:
                    import time
                    test_display = pd.to_datetime(unix_timestamps.iloc[0] - (-18000 if time.daylight else -21600), unit='s')
                    print(f"[GRAPH] DateAxisItem will display (UTC): {test_display}")
                
            except Exception as e:
                print(f"Timestamp conversion failed: {e}. Plotting by index.")
                import traceback
                traceback.print_exc()
        
        print(f"[GRAPH_UPDATE] Setting up stats table with {len(sensors_to_plot)} sensors")
        self.stats_table.setRowCount(len(sensors_to_plot))
        
        print(f"[GRAPH_UPDATE] Starting to plot {len(sensors_to_plot)} sensors")
        for i, sensor_name in enumerate(sensors_to_plot):
            print(f"[GRAPH_UPDATE] Processing sensor {i+1}/{len(sensors_to_plot)}: {sensor_name}")
            if sensor_name in df.columns:
                print(f"[GRAPH_UPDATE] Sensor {sensor_name} found in data")
                # Faster rendering: thinner pens, disable antialias via pen if desired
                pen = pg.mkPen(color=colors[i % len(colors)], width=1.5)
                y_data = df[sensor_name].to_numpy()

                # Plotting
                if has_timestamps:
                    # Use Unix timestamps for DateAxisItem
                    # Ensure arrays are aligned by resetting index if needed
                    if len(unix_timestamps) != len(y_data):
                        print(f"[GRAPH_UPDATE] WARNING: Array length mismatch! unix_timestamps={len(unix_timestamps)}, y_data={len(y_data)}")
                        # Reset index to ensure alignment
                        df_reset = df.reset_index(drop=True)
                        y_data = df_reset[sensor_name].to_numpy()
                        timestamps_reset = pd.to_datetime(df_reset['Timestamp'])
                        if timestamps_reset.dt.tz is None:
                            import time
                            offset_sec = time.altzone if time.daylight else time.timezone
                            utc_timestamps_reset = timestamps_reset + pd.Timedelta(seconds=offset_sec)
                            unix_timestamps = utc_timestamps_reset.astype('int64') // 10**9
                        else:
                            unix_timestamps = timestamps_reset.astype('int64') // 10**9
                    
                    x_data = unix_timestamps.to_numpy()
                    print(f"[GRAPH_UPDATE] Plotting {sensor_name} with timestamps")
                    self.plot_widget.plot(x=x_data, y=y_data, pen=pen, name=sensor_name)
                    print(f"[GRAPH] Plotting {sensor_name} with Unix timestamps: {x_data[0]} to {x_data[-1]}")
                else:
                    # Plot by index if no timestamps
                    x_data = range(len(y_data))
                    print(f"[GRAPH_UPDATE] Plotting {sensor_name} by index")
                    self.plot_widget.plot(x=x_data, y=y_data, pen=pen, name=sensor_name)
            else:
                print(f"[GRAPH_UPDATE] Sensor {sensor_name} NOT found in data")

            # --- Update Stats Table ---
            self.stats_table.setItem(i, 0, QTableWidgetItem(sensor_name))
            
            # Color swatch
            color_item = QTableWidgetItem()
            color_item.setBackground(pg.mkColor(colors[i % len(colors)]))
            self.stats_table.setItem(i, 1, color_item)
            
            # Calculate stats
            if sensor_name in df.columns:
                valid_data = df[sensor_name].dropna()
                if not valid_data.empty:
                    avg_val = valid_data.mean()
                    min_val = valid_data.min()
                    max_val = valid_data.max()
                    delta_val = max_val - min_val

                    self.stats_table.setItem(i, 2, QTableWidgetItem(f"{avg_val:.2f}"))
                    self.stats_table.setItem(i, 3, QTableWidgetItem(f"{min_val:.2f}"))
                    self.stats_table.setItem(i, 4, QTableWidgetItem(f"{max_val:.2f}"))
                    self.stats_table.setItem(i, 5, QTableWidgetItem(f"{delta_val:.2f}"))
                else:
                    for j in range(2, 6):
                        self.stats_table.setItem(i, j, QTableWidgetItem("N/A"))
            else:
                for j in range(2, 6):
                    self.stats_table.setItem(i, j, QTableWidgetItem("N/A"))
        
        # Set X-axis range to show all data (fixes "All Data" thin line issue)
        if has_timestamps and unix_timestamps is not None and len(sensors_to_plot) > 0:
            try:
                # Filter out invalid Unix timestamps (negative values from NaT conversion)
                valid_unix = unix_timestamps[unix_timestamps > 0]  # Valid Unix timestamps are positive
                if len(valid_unix) > 0:
                    x_min = float(valid_unix.min())
                    x_max = float(valid_unix.max())
                    
                    # Only set range if it's valid and spans more than a tiny range
                    if x_max > x_min and (x_max - x_min) > 1:
                        # Set X-axis range to show all data with small padding
                        self.plot_widget.setXRange(x_min, x_max, padding=0.02)
                        print(f"[GRAPH_UPDATE] Set X-axis range: {x_min} to {x_max} (span: {x_max - x_min} seconds)")
                    else:
                        print(f"[GRAPH_UPDATE] WARNING: Invalid timestamp range - min={x_min}, max={x_max}")
                else:
                    print(f"[GRAPH_UPDATE] WARNING: No valid Unix timestamps found (all are negative/NaT)")
            except Exception as e:
                print(f"[GRAPH_UPDATE] ERROR setting X-axis range: {e}")
                import traceback
                traceback.print_exc()

    def capture_snapshot(self):
        """Captures the current graph view as a snapshot for comparison.
        IMPORTANT: Only captures data within the current viewport (zoom) range.
        """
        # Get CSV data info
        if self.data_manager.csv_data is None:
            QMessageBox.warning(self, "No Data", "Please load CSV data before capturing a snapshot.")
            return

        # Show dialog to get snapshot name and batch selection
        dialog = SnapshotCaptureDialog(
            self.data_manager.snapshot_manager,
            f"Snapshot {len(self.data_manager.snapshot_manager.snapshots) + 1}",
            self
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        snapshot_name = dialog.get_snapshot_name()
        if not snapshot_name:
            return

        batch_id = dialog.get_batch_id()

        # Get current viewport settings
        view_range = self.plot_widget.viewRange()
        x_range = view_range[0]  # Current zoom X-axis range (Unix timestamps)
        y_range = view_range[1]  # Current zoom Y-axis range

        view_settings = {
            'sensors': list(self.data_manager.graph_sensors),
            'time_range': self.data_manager.time_range,
            'custom_time_range': self.data_manager.custom_time_range,
            'custom_time_ranges': self.data_manager.custom_time_ranges,
            'aggregation': self.data_manager.value_aggregation,
            'x_range': x_range,
            'y_range': y_range
        }

        # Get filtered data (already decimated by time range)
        full_data = self.data_manager.get_filtered_data()

        if full_data is None or full_data.empty:
            QMessageBox.warning(self, "No Data", "No data available to capture.")
            return

        # CRITICAL: Filter data to ONLY visible viewport range
        # This ensures snapshot can zoom IN but not OUT beyond captured bounds
        viewport_data = full_data.copy()

        if 'Timestamp' in viewport_data.columns:
            try:
                # Convert timestamps to Unix for comparison with x_range
                timestamps = pd.to_datetime(viewport_data['Timestamp'])

                # Handle timezone offset (same as in update_ui)
                import time
                if time.daylight:
                    offset_sec = time.altzone
                else:
                    offset_sec = time.timezone

                # Convert to UTC then Unix
                utc_timestamps = timestamps + pd.Timedelta(seconds=offset_sec)
                unix_timestamps = utc_timestamps.astype('int64') // 10**9

                # Filter to viewport X-range
                x_min, x_max = x_range
                mask = (unix_timestamps >= x_min) & (unix_timestamps <= x_max)
                viewport_data = viewport_data[mask].copy()

                print(f"[SNAPSHOT] Filtered data from {len(full_data)} to {len(viewport_data)} points (viewport only)")

            except Exception as e:
                print(f"[SNAPSHOT] Warning: Could not filter by viewport range: {e}")
                # Fall back to full data if filtering fails
                viewport_data = full_data.copy()

        if viewport_data.empty:
            QMessageBox.warning(self, "No Data in Viewport", "No data points in current zoom range.")
            return

        # Calculate statistics for viewport data only
        statistics = {}
        for sensor_name in self.data_manager.graph_sensors:
            if sensor_name in viewport_data.columns:
                valid_data = viewport_data[sensor_name].dropna()
                if not valid_data.empty:
                    statistics[sensor_name] = {
                        'avg': float(valid_data.mean()),
                        'min': float(valid_data.min()),
                        'max': float(valid_data.max()),
                        'std': float(valid_data.std())
                    }

        # Get CSV source filename
        csv_source = getattr(self.data_manager, 'csv_path', 'Unknown')
        if csv_source and csv_source != 'Unknown':
            import os
            csv_source = os.path.basename(csv_source)

        # Create snapshot with viewport-only data
        try:
            snapshot = self.data_manager.snapshot_manager.create_snapshot(
                name=snapshot_name,
                csv_source=csv_source,
                view_settings=view_settings,
                data=viewport_data,  # Only viewport data, not full data!
                statistics=statistics,
                batch_id=batch_id  # Assign to selected batch
            )

            # Emit signal to update UI
            self.data_manager.snapshots_changed.emit()

            print(f"[SNAPSHOT] Created snapshot '{snapshot_name}' with {len(viewport_data)} viewport data points")
            QMessageBox.information(
                self,
                "Snapshot Created",
                f"Snapshot '{snapshot_name}' created successfully!\n\n"
                f"Data points (viewport only): {len(viewport_data)}\n"
                f"Sensors: {len(self.data_manager.graph_sensors)}\n"
                f"Note: Snapshot locked to current zoom level"
            )

        except Exception as e:
            print(f"[SNAPSHOT] Error creating snapshot: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to create snapshot: {str(e)}")
    
    def start_range_selection(self, mode):
        """Start creating a new range selection (keep or delete)."""
        print(f"[GRAPH RANGE] Starting {mode} range selection")
        
        # Determine colors based on mode
        if mode == 'keep':
            brush_color = QColor(100, 149, 237, 80)  # Semi-transparent blue
            pen_color = QColor(30, 144, 255)  # Bright blue edges
        else:  # delete
            brush_color = QColor(237, 100, 100, 80)  # Semi-transparent red
            pen_color = QColor(255, 30, 30)  # Bright red edges
        
        # Create a new linear region item for selection
        range_region = pg.LinearRegionItem(
            values=[0, 1],
            brush=pg.mkBrush(brush_color),
            movable=True,
            pen=pg.mkPen(color=pen_color, width=3),
            hoverPen=pg.mkPen(color=QColor(255, 165, 0), width=5)  # Orange on hover
        )
        self.plot_widget.addItem(range_region)
        
        # Add to range regions list
        self.range_regions.append({'region': range_region, 'mode': mode})
        
        # Enable apply button
        self.apply_range_btn.setEnabled(True)
        
        # Position the region based on actual data timestamps if available
        df = self.data_manager.get_filtered_data()
        if df is not None and 'Timestamp' in df.columns:
            try:
                timestamps = pd.to_datetime(df['Timestamp']).astype('int64') // 10**9
                mid_point = (timestamps.min() + timestamps.max()) / 2
                width = (timestamps.max() - timestamps.min()) * 0.3
                range_region.setRegion([mid_point - width/2, mid_point + width/2])
                print(f"[GRAPH RANGE] Positioned {mode} range region based on data: {mid_point - width/2} to {mid_point + width/2}")
            except Exception as e:
                print(f"[GRAPH RANGE] Error positioning range region: {e}")
                # Fallback to view range
                view_range = self.plot_widget.viewRange()[0]
                mid_point = (view_range[0] + view_range[1]) / 2
                width = (view_range[1] - view_range[0]) * 0.3
                range_region.setRegion([mid_point - width/2, mid_point + width/2])
        else:
            print(f"[GRAPH RANGE] No data or Timestamp column found, using view range")
            # Fallback to view range
            view_range = self.plot_widget.viewRange()[0]
            mid_point = (view_range[0] + view_range[1]) / 2
            width = (view_range[1] - view_range[0]) * 0.3
            range_region.setRegion([mid_point - width/2, mid_point + width/2])

    def apply_custom_range(self):
        """Apply all selected time ranges (keep/delete) as filters."""
        if not self.range_regions:
            QMessageBox.warning(self, "No Ranges Selected", "Please select at least one range before applying.")
            return
        
        print(f"[GRAPH RANGE] Applying {len(self.range_regions)} range selections")
        
        # Get the data to determine if we're using timestamps or indices
        df = self.data_manager.get_filtered_data()
        if df is None or df.empty:
            print(f"[GRAPH RANGE] No data available")
            return
        
        # Separate keep and delete ranges
        keep_ranges = []
        delete_ranges = []
        
        # Process each range region
        import time
        for range_info in self.range_regions:
            range_region = range_info['region']
            mode = range_info['mode']
            start_unix, end_unix = range_region.getRegion()
            
            # Convert Unix timestamps to datetime
            if 'Timestamp' in df.columns:
                try:
                    if time.daylight:
                        offset_sec = time.altzone
                    else:
                        offset_sec = time.timezone
                    
                    start_utc = pd.to_datetime(start_unix, unit='s')
                    end_utc = pd.to_datetime(end_unix, unit='s')
                    start_dt = start_utc - pd.Timedelta(seconds=offset_sec)
                    end_dt = end_utc - pd.Timedelta(seconds=offset_sec)
                    
                    if mode == 'keep':
                        keep_ranges.append((start_dt, end_dt))
                    else:
                        delete_ranges.append((start_dt, end_dt))
                    print(f"[GRAPH RANGE] {mode.capitalize()} range: {start_dt} to {end_dt}")
                except Exception as e:
                    print(f"[GRAPH RANGE] Error converting timestamp for {mode} range: {e}")
                    import traceback
                    traceback.print_exc()
        
        # Call data manager's multi-range filter method
        self.data_manager.set_multi_range_filter(keep_ranges, delete_ranges)

        # If the user kept a specific range, also apply it as the global time filter
        # so Diagnostics, Calculations, and Diagram all see the same window.
        if keep_ranges:
            _start = min(s for s, _ in keep_ranges)
            _end   = max(e for _, e in keep_ranges)
            self.data_manager.set_custom_time_range(_start, _end)
            _mw = self.window()
            if hasattr(_mw, 'sensor_panel'):
                _mw.sensor_panel.set_time_range_display('From Graph')

        # Clear all range regions from graph
        for range_info in self.range_regions:
            self.plot_widget.removeItem(range_info['region'])
        self.range_regions.clear()
        self.apply_range_btn.setEnabled(False)
        
        # Refresh the graph display
        print(f"[GRAPH RANGE] Refreshing graph display with multi-range filter...")
        try:
            self.update_ui()
            print(f"[GRAPH RANGE] update_ui() completed successfully")
        except Exception as e:
            print(f"[GRAPH RANGE] ERROR in update_ui(): {e}")
            import traceback
            traceback.print_exc()
        
        # Show confirmation message
        keep_count = len(keep_ranges)
        delete_count = len(delete_ranges)
        QMessageBox.information(
            self,
            "Custom Ranges Applied",
            f"Applied {keep_count} keep range(s) and {delete_count} delete range(s).\n\n"
            f"The time range selector has been set to 'Custom'."
        )
        
        print(f"Multi-range filter applied: {keep_count} keep, {delete_count} delete")

    def auto_detect_defrost(self):
        """Open auto-detect defrost dialog and apply selected periods as delete ranges."""
        from defrost_autodetect_dialog import DefrostAutoDetectDialog
        import logging

        # Preserve the user's current time range selection (e.g., "24 Hours").
        # We apply defrost deletion as a non-destructive filter layered on top
        # of whatever time range is currently active.
        current_range = getattr(self.data_manager, "time_range", "All Data")

        dialog = DefrostAutoDetectDialog(
            data_manager=self.data_manager,
            parent=self
        )

        if dialog.exec():
            # Get selected periods
            selected_periods = dialog.get_selected_periods()

            if selected_periods:
                # Ensure multi-range filter structure exists
                if not isinstance(self.data_manager.custom_time_ranges, dict):
                    self.data_manager.custom_time_ranges = {'keep': [], 'delete': []}
                self.data_manager.custom_time_ranges.setdefault('keep', [])
                self.data_manager.custom_time_ranges.setdefault('delete', [])

                # If the user was already in single-range Custom mode, preserve that
                # time window by converting it into an implicit keep-range.
                if current_range == "Custom" and getattr(self.data_manager, "custom_time_range", None):
                    try:
                        ctr = self.data_manager.custom_time_range
                        start = ctr.get("start")
                        end = ctr.get("end")
                        if start is not None and end is not None and not self.data_manager.custom_time_ranges.get("keep"):
                            self.data_manager.custom_time_ranges["keep"] = [(start, end)]
                    except Exception:
                        pass

                # Replace (not append) delete ranges with newly detected periods
                self.data_manager.custom_time_ranges['delete'] = [(s, e) for s, e in selected_periods]

                logging.info(f"[AUTO_DETECT] Added {len(selected_periods)} defrost periods as delete ranges")

                # Invalidate cache and update UI
                self.data_manager._invalidate_filtered_cache()
                self.data_manager.data_changed.emit()
            else:
                logging.info("[AUTO_DETECT] No periods selected")
