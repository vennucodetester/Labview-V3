"""
Comparison Widget - Redesigned for Side-by-Side Snapshot Comparison
Optimized for maximum graph space with horizontal snapshot selector
"""

import pyqtgraph as pg
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                             QFrame, QScrollArea, QMessageBox, QDialog, QDialogButtonBox,
                             QTextEdit, QToolButton, QGraphicsItem)
from PyQt6.QtCore import Qt, QRectF, QSizeF
from PyQt6.QtGui import QFont, QPainter, QPen, QBrush, QColor
import pandas as pd


class StatsDialog(QDialog):
    """Dialog to show statistics for all snapshots in comparison"""

    def __init__(self, left_snapshot, right_snapshot, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Snapshot Statistics")
        self.setMinimumSize(600, 400)

        layout = QVBoxLayout(self)

        # Create text display
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setFont(QFont("Courier", 9))

        stats_text = ""

        # Left snapshot stats
        if left_snapshot:
            stats_text += f"=== {left_snapshot.name} ({left_snapshot.csv_source}) ===\n\n"
            if left_snapshot.statistics:
                for sensor_name, stats in left_snapshot.statistics.items():
                    stats_text += f"{sensor_name}:\n"
                    stats_text += f"  Average: {stats['avg']:.4f}\n"
                    stats_text += f"  Minimum: {stats['min']:.4f}\n"
                    stats_text += f"  Maximum: {stats['max']:.4f}\n"
                    stats_text += f"  Std Dev: {stats['std']:.4f}\n"
                    stats_text += f"  Delta:   {stats['max'] - stats['min']:.4f}\n\n"
            stats_text += "\n"

        # Right snapshot stats
        if right_snapshot:
            stats_text += f"=== {right_snapshot.name} ({right_snapshot.csv_source}) ===\n\n"
            if right_snapshot.statistics:
                for sensor_name, stats in right_snapshot.statistics.items():
                    stats_text += f"{sensor_name}:\n"
                    stats_text += f"  Average: {stats['avg']:.4f}\n"
                    stats_text += f"  Minimum: {stats['min']:.4f}\n"
                    stats_text += f"  Maximum: {stats['max']:.4f}\n"
                    stats_text += f"  Std Dev: {stats['std']:.4f}\n"
                    stats_text += f"  Delta:   {stats['max'] - stats['min']:.4f}\n\n"

        if not stats_text:
            stats_text = "No statistics available"

        text_edit.setPlainText(stats_text)
        layout.addWidget(text_edit)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)


class SnapshotChip(QToolButton):
    """A chip-style button for snapshot selection"""

    def __init__(self, snapshot, parent=None):
        super().__init__(parent)
        self.snapshot = snapshot

        # Display compact name
        display_name = snapshot.name
        if len(display_name) > 15:
            display_name = display_name[:12] + "..."

        self.setText(f"📊 {display_name}")
        self.setToolTip(f"{snapshot.name}\nCSV: {snapshot.csv_source}\nCreated: {snapshot.created}")

        # Styling
        self.setStyleSheet("""
            QToolButton {
                background-color: #3498DB;
                color: white;
                border: none;
                border-radius: 12px;
                padding: 5px 12px;
                margin: 2px;
                font-size: 10px;
                font-weight: bold;
            }
            QToolButton:hover {
                background-color: #2980B9;
            }
            QToolButton:pressed {
                background-color: #1F618D;
            }
        """)

        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class DraggableLegendItem(pg.LegendItem):
    """Legend item that can be freely moved and resized within the plot."""

    HANDLE_SIZE = 12
    MIN_WIDTH = 120
    MIN_HEIGHT = 60

    def __init__(self):
        super().__init__(offset=(0, 0))
        self.setBrush(QBrush(QColor(255, 255, 255, 230)))
        self.setPen(QPen(QColor("#888888"), 1))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(10)

        self._resizing = False
        self._resize_start_pos = None
        self._start_geometry = None
        self._current_cursor = Qt.CursorShape.OpenHandCursor
        self.setCursor(self._current_cursor)

        # Ensure minimum size
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(self.MIN_WIDTH, self.MIN_HEIGHT)

    def _is_in_resize_handle(self, pos):
        """Check if a point is within the resize handle area."""
        rect = self.boundingRect()
        handle_rect = QRectF(
            rect.right() - self.HANDLE_SIZE,
            rect.bottom() - self.HANDLE_SIZE,
            self.HANDLE_SIZE,
            self.HANDLE_SIZE
        )
        return handle_rect.contains(pos)

    def hoverMoveEvent(self, event):
        """Update cursor when hovering over resize handle."""
        if self._is_in_resize_handle(event.pos()):
            self._update_cursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self._update_cursor(Qt.CursorShape.OpenHandCursor if not self._resizing else Qt.CursorShape.ClosedHandCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        """Reset cursor when leaving legend area."""
        self._update_cursor(Qt.CursorShape.OpenHandCursor if not self._resizing else Qt.CursorShape.ClosedHandCursor)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        """Start move or resize operation."""
        if event.button() == Qt.MouseButton.LeftButton and self._is_in_resize_handle(event.pos()):
            self._resizing = True
            self._resize_start_pos = event.pos()
            self._start_geometry = self.geometry()
            self._update_cursor(Qt.CursorShape.SizeFDiagCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self._update_cursor(Qt.CursorShape.ClosedHandCursor)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle dragging for move or resize."""
        if self._resizing and self._resize_start_pos is not None and self._start_geometry is not None:
            delta = event.pos() - self._resize_start_pos
            new_width = max(self.MIN_WIDTH, self._start_geometry.width() + delta.x())
            new_height = max(self.MIN_HEIGHT, self._start_geometry.height() + delta.y())
            self.resize(new_width, new_height)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Finish move or resize operation."""
        if event.button() == Qt.MouseButton.LeftButton and self._resizing:
            self._resizing = False
            self._resize_start_pos = None
            self._start_geometry = None
            self._update_cursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self._update_cursor(Qt.CursorShape.OpenHandCursor)

        super().mouseReleaseEvent(event)

    def paint(self, painter, option, widget=None):
        """Draw legend with a resize handle."""
        super().paint(painter, option, widget)

        # Draw resize handle in bottom-right corner
        rect = self.boundingRect()
        handle_rect = QRectF(
            rect.right() - self.HANDLE_SIZE,
            rect.bottom() - self.HANDLE_SIZE,
            self.HANDLE_SIZE,
            self.HANDLE_SIZE
        )
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#3498DB")))
        painter.drawRect(handle_rect)
        painter.restore()

    def resize(self, width, height):
        """Update legend geometry and re-layout contents."""
        super().resize(width, height)
        # Force update geometry for contained layout
        self.updateGeometry()

    def _update_cursor(self, cursor_shape):
        if self._current_cursor != cursor_shape:
            self._current_cursor = cursor_shape
            self.setCursor(cursor_shape)

class SnapshotGraphCell(QFrame):
    """A single cell in the comparison grid that displays a snapshot's graph"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.snapshot = None
        self.legend_item = None
        self._legend_initial_size = QSizeF(200, 120)
        self.setup_ui()

    def setup_ui(self):
        """Setup the cell UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        # Compact header with snapshot name and CSV
        self.label = QLabel("Click a snapshot to load")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(10)
        self.label.setFont(font)
        self.label.setStyleSheet("color: #555; padding: 3px;")
        layout.addWidget(self.label)

        # Graph plot widget (takes all remaining space)
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')
        self.plot_widget = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem()})
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.getAxis('left').setLabel('Value')
        self.plot_widget.getAxis('bottom').setLabel('Time')
        self.plot_widget.setMinimumHeight(300)
        layout.addWidget(self.plot_widget)

        # Frame styling
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setLineWidth(1)
        self.setStyleSheet("background-color: #fafafa; border: 1px solid #ccc;")

    def _ensure_legend(self):
        """Create the draggable legend if it doesn't exist."""
        if self.legend_item is None:
            self.legend_item = DraggableLegendItem()
            self.legend_item.setParentItem(self.plot_widget.plotItem.vb)
            self.legend_item.resize(self._legend_initial_size.width(), self._legend_initial_size.height())
            self.legend_item.setPos(60, 40)
        return self.legend_item

    def _remove_legend(self):
        """Remove the legend from the scene."""
        if self.legend_item:
            try:
                self.legend_item.clear()
                scene = self.legend_item.scene()
                if scene:
                    scene.removeItem(self.legend_item)
            except Exception:
                pass
            self.legend_item = None

    def is_empty(self):
        """Check if cell is empty"""
        return self.snapshot is None

    def load_snapshot(self, snapshot):
        """Load a snapshot into this cell"""
        self.snapshot = snapshot

        # Update compact header: "Name (csv) ℹ️"
        csv_short = snapshot.csv_source
        if len(csv_short) > 20:
            csv_short = csv_short[:17] + "..."

        self.label.setText(f"{snapshot.name} ({csv_short})")
        self.label.setStyleSheet("color: #000; font-weight: bold; padding: 3px;")
        self.label.setToolTip(
            f"Snapshot: {snapshot.name}\n"
            f"CSV: {snapshot.csv_source}\n"
            f"Created: {snapshot.created.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Time Range: {snapshot.view_settings.get('time_range', 'N/A')}\n"
            f"Aggregation: {snapshot.view_settings.get('aggregation', 'N/A')}\n"
            f"Sensors: {', '.join(snapshot.view_settings.get('sensors', []))}"
        )

        # Clear previous plot
        self.plot_widget.clear()
        if self.legend_item:
            try:
                self.legend_item.clear()
            except Exception:
                pass

        # Plot the data
        if snapshot.data is not None and not snapshot.data.empty:
            colors = ['#E74C3C', '#3498DB', '#2ECC71', '#F39C12', '#9B59B6', '#1ABC9C']

            # Get timestamps if available
            has_timestamps = 'Timestamp' in snapshot.data.columns
            if has_timestamps:
                timestamps = pd.to_datetime(snapshot.data['Timestamp'])

                # CRITICAL FIX: Apply timezone offset handling (same as graph_widget.py)
                # This ensures Unix timestamps match the saved view_settings x_range
                import time
                if timestamps.dt.tz is None:
                    # Naive timestamps - treat as local time and convert to UTC
                    if time.daylight:
                        offset_sec = time.altzone  # e.g., 18000 for CDT (UTC-5)
                    else:
                        offset_sec = time.timezone

                    # Convert local time to UTC by adding offset
                    utc_timestamps = timestamps + pd.Timedelta(seconds=offset_sec)
                    x_data = (utc_timestamps.astype('int64') // 10**9).to_numpy()
                else:
                    # Timezone-aware timestamps
                    x_data = (timestamps.astype('int64') // 10**9).to_numpy()

                print(f"[SNAPSHOT LOAD] Loaded {len(x_data)} timestamps with timezone offset applied")

            # Plot each sensor
            sensor_idx = 0
            legend_entries = []
            for sensor_name in snapshot.view_settings.get('sensors', []):
                if sensor_name in snapshot.data.columns:
                    pen = pg.mkPen(color=colors[sensor_idx % len(colors)], width=2)
                    y_data = snapshot.data[sensor_name].to_numpy()

                    if has_timestamps:
                        plot_item = self.plot_widget.plot(x=x_data, y=y_data, pen=pen, name=sensor_name)
                    else:
                        x_data_idx = range(len(y_data))
                        plot_item = self.plot_widget.plot(x=x_data_idx, y=y_data, pen=pen, name=sensor_name)

                    legend_entries.append((plot_item, sensor_name))

                    sensor_idx += 1

            if legend_entries:
                legend = self._ensure_legend()
                legend.clear()
                for plot_item, label in legend_entries:
                    legend.addItem(plot_item, label)

        # Apply saved view settings (zoom)
        view_settings = snapshot.view_settings
        if 'x_range' in view_settings and 'y_range' in view_settings:
            try:
                x_range = view_settings['x_range']
                y_range = view_settings['y_range']
                self.plot_widget.setXRange(x_range[0], x_range[1], padding=0)
                self.plot_widget.setYRange(y_range[0], y_range[1], padding=0)
            except Exception as e:
                print(f"[SNAPSHOT CELL] Error applying view range: {e}")

        # Update styling
        self.setStyleSheet("background-color: #f9f9f9; border: 2px solid #3498DB;")

    def clear(self):
        """Clear the cell"""
        self.snapshot = None
        self.label.setText("Click a snapshot to load")
        self.label.setStyleSheet("color: #555; padding: 3px;")
        self.label.setToolTip("")
        self.plot_widget.clear()
        self._remove_legend()
        self.setStyleSheet("background-color: #fafafa; border: 1px solid #ccc;")


class ComparisonWidget(QWidget):
    """Redesigned comparison widget for side-by-side snapshot comparison"""

    def __init__(self, data_manager):
        super().__init__()
        self.data_manager = data_manager
        self.left_cell = None
        self.right_cell = None
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        """Setup the UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Top toolbar with horizontal snapshot chips
        toolbar = self.create_toolbar()
        main_layout.addWidget(toolbar)

        # Side-by-side graph area (1x2 layout)
        graph_area = self.create_graph_area()
        main_layout.addWidget(graph_area)

    def create_toolbar(self):
        """Create the top toolbar with snapshot chips"""
        toolbar = QFrame()
        toolbar.setFrameShape(QFrame.Shape.StyledPanel)
        toolbar.setStyleSheet("background-color: #f5f5f5; border-bottom: 2px solid #ddd;")
        toolbar.setMaximumHeight(50)

        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(5, 5, 5, 5)

        # Scrollable area for snapshot chips
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setMaximumHeight(40)

        self.chip_container = QWidget()
        self.chip_layout = QHBoxLayout(self.chip_container)
        self.chip_layout.setContentsMargins(0, 0, 0, 0)
        self.chip_layout.setSpacing(5)
        self.chip_layout.addStretch()

        scroll_area.setWidget(self.chip_container)
        layout.addWidget(scroll_area, 1)

        # Control buttons
        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.clicked.connect(self.clear_all_cells)
        self.clear_btn.setMaximumWidth(100)
        layout.addWidget(self.clear_btn)

        self.stats_btn = QPushButton("Stats")
        self.stats_btn.clicked.connect(self.show_stats_dialog)
        self.stats_btn.setMaximumWidth(80)
        self.stats_btn.setToolTip("Show statistics for loaded snapshots")
        layout.addWidget(self.stats_btn)

        return toolbar

    def create_graph_area(self):
        """Create the side-by-side graph area"""
        graph_frame = QFrame()
        layout = QHBoxLayout(graph_frame)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # Left cell
        self.left_cell = SnapshotGraphCell()
        layout.addWidget(self.left_cell, 1)

        # Right cell
        self.right_cell = SnapshotGraphCell()
        layout.addWidget(self.right_cell, 1)

        return graph_frame

    def connect_signals(self):
        """Connect signals"""
        self.data_manager.snapshots_changed.connect(self.refresh_snapshot_chips)

    def refresh_snapshot_chips(self):
        """Refresh the horizontal snapshot chip bar"""
        # Clear existing chips
        while self.chip_layout.count() > 1:  # Keep the stretch
            item = self.chip_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add chips for each snapshot
        snapshots = self.data_manager.snapshot_manager.get_all_snapshots()
        for snapshot in snapshots:
            chip = SnapshotChip(snapshot)
            chip.clicked.connect(lambda checked, s=snapshot: self.on_snapshot_clicked(s))
            self.chip_layout.insertWidget(self.chip_layout.count() - 1, chip)

        print(f"[COMPARE TAB] Refreshed snapshot chips: {len(snapshots)} snapshots")

    def on_snapshot_clicked(self, snapshot):
        """Handle snapshot click - add to first empty cell (left, then right)"""
        if not snapshot:
            return

        # Load into first empty cell
        if self.left_cell.is_empty():
            self.left_cell.load_snapshot(snapshot)
            print(f"[COMPARE TAB] Loaded snapshot '{snapshot.name}' into LEFT cell")
        elif self.right_cell.is_empty():
            self.right_cell.load_snapshot(snapshot)
            print(f"[COMPARE TAB] Loaded snapshot '{snapshot.name}' into RIGHT cell")
        else:
            # Both cells are full
            QMessageBox.information(
                self,
                "Comparison Full",
                "Both comparison slots are full. Clear one to load a new snapshot."
            )

    def clear_all_cells(self):
        """Clear all cells"""
        self.left_cell.clear()
        self.right_cell.clear()
        print("[COMPARE TAB] Cleared all cells")

    def show_stats_dialog(self):
        """Show statistics dialog"""
        left_snapshot = self.left_cell.snapshot
        right_snapshot = self.right_cell.snapshot

        if not left_snapshot and not right_snapshot:
            QMessageBox.information(
                self,
                "No Snapshots",
                "Load snapshots first to view statistics."
            )
            return

        dialog = StatsDialog(left_snapshot, right_snapshot, self)
        dialog.exec()

    def update_ui(self):
        """Update the UI (called when tab becomes visible)"""
        self.refresh_snapshot_chips()
