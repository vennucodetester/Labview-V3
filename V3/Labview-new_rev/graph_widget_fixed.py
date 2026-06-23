import pyqtgraph as pg
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QHBoxLayout, QFrame, 
                             QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
import pandas as pd
from datetime import datetime
import numpy as np

class GraphWidget(QWidget):
    """
    COMPLETELY REWRITTEN Graph Widget - No more DateAxisItem mess!
    Uses simple numeric plotting with proper timestamp handling.
    """
    def __init__(self, data_manager):
        super().__init__()
        self.data_manager = data_manager
        
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')
        
        # Custom range selection state
        self.range_selection_mode = False
        self.range_region = None
        self.original_timestamps = None  # Store original timestamps for mapping

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
        self.select_range_btn = QPushButton("📅 Select Custom Range")
        self.select_range_btn.setCheckable(True)
        self.select_range_btn.setToolTip("Click to enable range selection, then drag on the graph to select a custom time range")
        self.apply_range_btn = QPushButton("Apply Range")
        self.apply_range_btn.setEnabled(False)
        self.apply_range_btn.setToolTip("Apply the selected time range")
        self.export_btn = QPushButton("Export")
        
        control_layout.addWidget(self.reset_zoom_btn)
        control_layout.addWidget(self.select_range_btn)
        control_layout.addWidget(self.apply_range_btn)
        control_layout.addWidget(self.export_btn)
        control_layout.addStretch()
        main_layout.addWidget(control_bar)

        # --- Plot Widget ---
        # NO MORE DateAxisItem! Use simple PlotWidget with custom axis
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.getAxis('left').setLabel('Sensor Value')
        self.plot_widget.getAxis('bottom').setLabel('Time')
        
        # Set up custom X-axis with proper timestamp labels
        self.setup_custom_x_axis()
        
        main_layout.addWidget(self.plot_widget, 4)

        # --- Custom Legend/Stats Table ---
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(6)
        self.stats_table.setHorizontalHeaderLabels(["Sensor Name", "Color", "Avg", "Min", "Max", "Delta"])
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.stats_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.stats_table.setMaximumHeight(250)
        main_layout.addWidget(self.stats_table, 1)

    def setup_custom_x_axis(self):
        """Set up custom X-axis to display timestamps properly."""
        # Get the bottom axis
        self.x_axis = self.plot_widget.getAxis('bottom')
        
        # Create a custom axis item that will handle timestamp formatting
        self.x_axis.setLabel('Time')
        
    def format_timestamp_axis(self, timestamps):
        """Format X-axis to show actual timestamps from CSV."""
        if timestamps is None or len(timestamps) == 0:
            return
            
        # Store original timestamps for range selection mapping
        self.original_timestamps = timestamps.copy()
        
        # Create a custom tick formatter
        def format_tick(value, scale):
            try:
                # Convert numeric position back to timestamp
                if hasattr(self, 'original_timestamps') and self.original_timestamps is not None:
                    # Find the closest timestamp
                    idx = int(round(value))
                    if 0 <= idx < len(self.original_timestamps):
                        ts = self.original_timestamps.iloc[idx]
                        # Format as readable date/time
                        return ts.strftime('%m/%d %H:%M')
                return str(value)
            except:
                return str(value)
        
        # Apply the custom formatter
        self.x_axis.setTickFormat(format_tick)
        
        print(f"[GRAPH] Set up custom X-axis with {len(timestamps)} timestamps")
        print(f"[GRAPH] First timestamp: {timestamps.iloc[0]}")
        print(f"[GRAPH] Last timestamp: {timestamps.iloc[-1]}")

    def connect_signals(self):
        self.reset_zoom_btn.clicked.connect(self.plot_widget.autoRange)
        self.select_range_btn.toggled.connect(self.toggle_range_selection)
        self.apply_range_btn.clicked.connect(self.apply_custom_range)
        self.export_btn.clicked.connect(self.export_graph)

    def update_ui(self):
        """Redraws the graph and stats table based on the DataManager's state."""
        self.plot_widget.clear()
        self.stats_table.setRowCount(0)

        # Use filtered data based on time range
        df = self.data_manager.get_filtered_data()
        sensors_to_plot = self.data_manager.graph_sensors

        if df is None or not sensors_to_plot or df.empty:
            print(f"[GRAPH] No data to plot - df: {df is not None}, sensors: {len(sensors_to_plot) if sensors_to_plot else 0}")
            return

        print(f"[GRAPH] Plotting {len(sensors_to_plot)} sensors with {len(df)} data points")
        print(f"[GRAPH] Data columns: {list(df.columns)[:5]}...")

        colors = ['#E74C3C', '#3498DB', '#2ECC71', '#F39C12', '#9B59B6', '#1ABC9C']
        
        # Handle timestamps properly
        timestamps = None
        has_timestamps = False
        x_data = None
        
        if 'Timestamp' in df.columns:
            try:
                # Convert to pandas datetime if not already
                timestamps = pd.to_datetime(df['Timestamp'])
                has_timestamps = True
                
                # Use simple numeric indexing for X-axis (0, 1, 2, ...)
                x_data = np.arange(len(timestamps))
                
                print(f"[GRAPH] Using timestamps - range: {timestamps.iloc[0]} to {timestamps.iloc[-1]}")
                print(f"[GRAPH] Data points: {len(timestamps)}")
                
                # Set up custom X-axis formatting
                self.format_timestamp_axis(timestamps)
                
            except Exception as e:
                print(f"[GRAPH] Timestamp conversion failed: {e}")
                has_timestamps = False
                x_data = np.arange(len(df))
        else:
            print(f"[GRAPH] No Timestamp column found, using index")
            x_data = np.arange(len(df))
        
        self.stats_table.setRowCount(len(sensors_to_plot))
        
        for i, sensor_name in enumerate(sensors_to_plot):
            if sensor_name in df.columns:
                pen = pg.mkPen(color=colors[i % len(colors)], width=1.5)
                y_data = df[sensor_name].to_numpy()

                # Plot using numeric X-axis
                self.plot_widget.plot(x_data, y_data, pen=pen, name=sensor_name)
                print(f"[GRAPH] Plotted {sensor_name} with {len(y_data)} points")

                # Update Stats Table
                self.stats_table.setItem(i, 0, QTableWidgetItem(sensor_name))
                
                # Color swatch
                color_item = QTableWidgetItem()
                color_item.setBackground(pg.mkColor(colors[i % len(colors)]))
                self.stats_table.setItem(i, 1, color_item)
                
                # Calculate stats
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

    def export_graph(self):
        """Exports the current graph view to an image file."""
        exporter = pg.exporters.ImageExporter(self.plot_widget.plotItem)
        exporter.export('graph_export.png')
        print("Graph exported to graph_export.png")
    
    def toggle_range_selection(self, checked):
        """Toggle custom range selection mode."""
        self.range_selection_mode = checked
        
        if checked:
            # Enable range selection mode
            self.select_range_btn.setStyleSheet("background-color: #4CAF50; color: white;")
            self.select_range_btn.setText("📅 Drag to Select Range")
            
            # Remove existing range region if any
            if self.range_region:
                self.plot_widget.removeItem(self.range_region)
            
            # Create a new linear region item for selection
            self.range_region = pg.LinearRegionItem(
                values=[0, 1],
                brush=pg.mkBrush(QColor(100, 149, 237, 80)),
                movable=True,
                pen=pg.mkPen(color=QColor(30, 144, 255), width=3),
                hoverPen=pg.mkPen(color=QColor(255, 165, 0), width=5)
            )
            self.plot_widget.addItem(self.range_region)
            
            # Enable apply button
            self.apply_range_btn.setEnabled(True)
            
            # Position the region based on data range
            if hasattr(self, 'original_timestamps') and self.original_timestamps is not None:
                # Position in the middle 30% of the data
                data_length = len(self.original_timestamps)
                start_idx = int(data_length * 0.35)
                end_idx = int(data_length * 0.65)
                self.range_region.setRegion([start_idx, end_idx])
                print(f"[GRAPH RANGE] Positioned range region at indices {start_idx} to {end_idx}")
            else:
                # Fallback to view range
                view_range = self.plot_widget.viewRange()[0]
                mid_point = (view_range[0] + view_range[1]) / 2
                width = (view_range[1] - view_range[0]) * 0.3
                self.range_region.setRegion([mid_point - width/2, mid_point + width/2])
        else:
            # Disable range selection mode
            self.select_range_btn.setStyleSheet("")
            self.select_range_btn.setText("📅 Select Custom Range")
            
            # Remove the range region
            if self.range_region:
                self.plot_widget.removeItem(self.range_region)
                self.range_region = None
            
            # Disable apply button
            self.apply_range_btn.setEnabled(False)
    
    def apply_custom_range(self):
        """Apply the selected time range as the custom range."""
        if not self.range_region:
            return
        
        # Get the selected range values (these are now numeric indices!)
        start_idx, end_idx = self.range_region.getRegion()
        print(f"[GRAPH RANGE] Selected range (indices): {start_idx} to {end_idx}")
        
        # Convert indices to actual timestamps
        if hasattr(self, 'original_timestamps') and self.original_timestamps is not None:
            try:
                # Clamp indices to valid range
                start_idx = max(0, min(int(start_idx), len(self.original_timestamps) - 1))
                end_idx = max(0, min(int(end_idx), len(self.original_timestamps) - 1))
                
                # Get actual timestamps
                start_dt = self.original_timestamps.iloc[start_idx]
                end_dt = self.original_timestamps.iloc[end_idx]
                
                print(f"[GRAPH RANGE] Converted to timestamps: {start_dt} to {end_dt}")
                print(f"[GRAPH RANGE] Duration: {end_dt - start_dt}")
                
                # Set the custom time range in data manager
                self.data_manager.set_custom_time_range(start_dt, end_dt)
                
                # Disable selection mode
                self.select_range_btn.setChecked(False)
                
                # Refresh the graph display
                print(f"[GRAPH RANGE] Refreshing graph display with custom range...")
                self.update_ui()
                
                # Show confirmation message
                QMessageBox.information(
                    self,
                    "Custom Range Applied",
                    f"Custom time range set:\n\n"
                    f"From: {start_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"To: {end_dt.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"The time range selector has been set to 'Custom'."
                )
                
                print(f"Custom range applied: {start_dt} to {end_dt}")
                
            except Exception as e:
                print(f"[GRAPH RANGE] Error applying range: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[GRAPH RANGE] No original timestamps available")
            QMessageBox.warning(
                self,
                "Range Selection Error",
                "No timestamp data available for range selection."
            )
