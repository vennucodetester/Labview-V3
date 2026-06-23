import sys
import argparse
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTabWidget, QLabel, QFrame, QPushButton,
                             QFileDialog)
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import Qt, QTimer

# Initialize logging early, before other imports that might log
from logging_setup import init_logging


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="HVAC System Analyzer")
    parser.add_argument(
        "--log",
        type=str,
        default=None,
        help="Path to log file (default: logs/app_YYYYMMDD_HHMMSS.log)"
    )
    return parser.parse_args()


# Parse args and initialize logging
args = parse_args()
log_file = init_logging(args.log)

# Import our component classes
from data_manager import DataManager
from sensor_panel import SensorPanel
from diagram_widget import DiagramWidget
from graph_widget import GraphWidget
from comparison_widget import ComparisonWidget
from mapping_dialog import MappingDialog
from calculations_widget import CalculationsWidget
from diagnostics_widget import DiagnosticsWidget

class MainWindow(QMainWindow):
    """The main application window, orchestrating all other components."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HVAC System Analyzer (Python Edition)")
        self.setGeometry(100, 100, 1600, 900)
        self.set_light_theme()

        self.data_manager = DataManager(self)

        # Undo stack to store application states
        self.undo_stack = []
        self.max_undo_levels = 20

        # Timer for auto-saving state (with cooldown to avoid too frequent saves)
        self.auto_save_timer = QTimer()
        self.auto_save_timer.setSingleShot(True)
        self.auto_save_timer.timeout.connect(self.save_state)
        self.last_save_time = 0 

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Instantiate UI Components ---
        self.sensor_panel = SensorPanel(self.data_manager)
        
        self.diagram_widget = DiagramWidget(self.data_manager)
        self.graph_widget = GraphWidget(self.data_manager)
        self.comparison_widget = ComparisonWidget(self.data_manager)
        self.calculations_widget = CalculationsWidget(self.data_manager)
        self.diagnostics_widget  = DiagnosticsWidget(self.data_manager)
        self.calculations_widget.filtered_data_ready.connect(
            self.diagnostics_widget.on_data_ready
        )
        # Feed processed results to the diagram for the Analysis state overlay
        self.calculations_widget.filtered_data_ready.connect(
            self.diagram_widget.on_processed_data
        )
        # Diagnostics card 'Show on diagram' → switch tab + highlight component
        self.diagnostics_widget.locate_on_diagram.connect(self.on_locate_finding)

        # --- Assemble Layout ---
        self.sensor_panel.setFixedWidth(350) 
        main_layout.addWidget(self.sensor_panel)
        
        right_panel = self.setup_tabs()
        main_layout.addWidget(right_panel)
        
        # --- Connect Signals and Slots ---
        self.connect_signals()

        # --- Test Request system (TEST_REQUEST_PLAN.md Phase 1) ---
        self.setup_menu()

        # Save initial state for undo
        QTimer.singleShot(500, self.save_state)

        # Ensure window becomes visible and focused shortly after startup
        QTimer.singleShot(150, self._bring_to_front)

    def _bring_to_front(self):
        try:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            print("[APP] Main window shown and focused")
        except Exception:
            pass

    def setup_tabs(self):
        """Creates the tab widget and populates it with our custom widgets."""
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        self.tabs.addTab(self.diagram_widget, "Diagram")
        self.tabs.addTab(self.graph_widget, "Graph")
        self.tabs.addTab(self.comparison_widget, "Comparison")
        self.tabs.addTab(self.calculations_widget, "Calculations")
        self.tabs.addTab(self.diagnostics_widget,  "🩺 Diagnostics")

        right_layout.addWidget(self.tabs)
        return right_panel

    def connect_signals(self):
        """Central place to connect all component signals to controller slots."""
        self.sensor_panel.load_csv_button.clicked.connect(self.open_csv_file_dialog)
        self.sensor_panel.load_config_button.clicked.connect(self.open_session_file_dialog)
        self.sensor_panel.save_config_button.clicked.connect(self.save_session_file_dialog)
        self.sensor_panel.range_button.clicked.connect(self.open_range_editor_dialog)
        self.sensor_panel.test_simple_button.clicked.connect(self.test_simple_diagram)
        
        # Update UI only for the active tab to reduce redundant work
        self.data_manager.data_changed.connect(self.update_active_tab)
        # Also listen to diagram model changes for standard component sensor mappings
        self.data_manager.diagram_model_changed.connect(self.update_active_tab)

        # Auto-save state on significant changes (with cooldown)
        self.data_manager.data_changed.connect(self.schedule_auto_save)
        self.data_manager.diagram_model_changed.connect(self.schedule_auto_save)
        # Ensure mapping changes trigger auto-save (since we removed data_changed emit)
        if hasattr(self.data_manager, 'sensor_mapping_changed'):
            self.data_manager.sensor_mapping_changed.connect(self.schedule_auto_save)

        # --- FIX: Removed connection to the non-existent signal ---
        # self.sensor_panel.graph_sensor_toggled.connect(self.on_graph_sensor_toggled)
        
        # Connect diagram widget sensor port clicks to sensor panel highlighting
        self.diagram_widget.sensor_port_clicked.connect(self.sensor_panel.highlight_and_scroll_to_sensor)

    def open_csv_file_dialog(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Open Data File", "",
            "Data Files (*.csv *.xlsx *.xls);;CSV Files (*.csv);;Excel Files (*.xlsx *.xls);;All Files (*)"
        )
        if file_name:
            self.data_manager.load_csv(file_name)
            # Save state after loading CSV for undo
            QTimer.singleShot(200, self.save_state)

    def open_session_file_dialog(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Session File", "", "JSON Files (*.json)")
        if file_name:
            self.data_manager.load_session(file_name)
            # Save state after loading session for undo
            QTimer.singleShot(200, self.save_state)
    
    def test_simple_diagram(self):
        """Quickly generate and load a simple vertical loop diagram."""
        from diagram_from_request import build_simple_loop_diagram
        model = build_simple_loop_diagram()
        self.data_manager.diagram_model = model
        self.diagram_widget.update_ui()
        
    def save_session_file_dialog(self):
        file_name, _ = QFileDialog.getSaveFileName(self, "Save Session File", "", "JSON Files (*.json)")
        if file_name:
            if not file_name.lower().endswith('.json'):
                file_name = file_name + '.json'
            self.data_manager.save_session(file_name)

    def open_range_editor_dialog(self):
        """Open the range editor dialog"""
        from range_editor_dialog import RangeEditorDialog
        dialog = RangeEditorDialog(self.data_manager, self)
        dialog.exec()

    # --- FIX: Removed the unused slot method ---
    # def on_graph_sensor_toggled(self, sensor_name, is_selected_for_graph):
    #     self.data_manager.set_sensor_graphed(sensor_name, is_selected_for_graph)
    #     self.data_manager.data_changed.emit()

    def schedule_auto_save(self):
        """Schedule auto-save with 2-second cooldown to avoid too frequent saves."""
        import time
        current_time = time.time()

        # Only schedule if enough time has passed since last save
        if current_time - self.last_save_time >= 2.0:
            # Stop any pending timer and start a new one
            self.auto_save_timer.stop()
            self.auto_save_timer.start(2000)  # Save after 2 seconds of inactivity

    def save_state(self):
        """Save current state to undo stack."""
        import time
        try:
            # Update last save time
            self.last_save_time = time.time()

            state = self.data_manager.save_session_to_dict()
            if state is None:
                print(f"[UNDO] Failed to create state dictionary")
                return

            self.undo_stack.append(state)
            # Limit undo stack size
            if len(self.undo_stack) > self.max_undo_levels:
                self.undo_stack.pop(0)
            print(f"[UNDO] State saved. Stack size: {len(self.undo_stack)}")
        except Exception as e:
            print(f"[UNDO] Error saving state: {e}")
            import traceback
            traceback.print_exc()

    def undo(self):
        """Restore previous state from undo stack."""
        if len(self.undo_stack) > 1:
            # Remove current state
            self.undo_stack.pop()
            # Get previous state
            previous_state = self.undo_stack[-1]
            try:
                self.data_manager.load_session_from_dict(previous_state)
                print(f"[UNDO] State restored. Stack size: {len(self.undo_stack)}")
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(self, "Undo", "Previous state restored.")
            except Exception as e:
                print(f"[UNDO] Error restoring state: {e}")
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Undo Error", f"Could not restore previous state: {e}")
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Undo", "No more undo history available.")

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts for the main window."""
        from PyQt6.QtCore import Qt

        # Ctrl+Z for undo
        if event.key() == Qt.Key.Key_Z and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.undo()
        elif event.key() == Qt.Key.Key_Escape:
            # Deselect all sensors when Escape is pressed
            self.data_manager.selected_sensors.clear()
            self.data_manager.data_changed.emit()
        else:
            super().keyPressEvent(event)

    def setup_menu(self):
        """Menu bar for the Test Request library."""
        menu = self.menuBar().addMenu('Test &Requests')
        act_new = menu.addAction('New Test Request…')
        act_new.triggered.connect(self.new_test_request)
        act_open = menu.addAction('Open Test Request…')
        act_open.triggered.connect(self.open_test_request)

    def _library(self):
        from test_request_library import TestRequestLibrary
        if not hasattr(self, '_test_library'):
            self._test_library = TestRequestLibrary()
        return self._test_library

    def new_test_request(self):
        from test_request_dialog import TestRequestDialog
        dlg = TestRequestDialog(self._library(), parent=self,
                                data_manager=self.data_manager)
        dlg.exec()

    def open_test_request(self):
        from PyQt6.QtWidgets import QInputDialog, QMessageBox
        from test_request_dialog import TestRequestDialog
        lib = self._library()
        requests = lib.all_requests()
        if not requests:
            QMessageBox.information(self, 'Test Requests',
                                    'No test requests in the library yet.')
            return
        labels = [f"{r.get('request_no')} — {r.get('elp_code')} — "
                  f"{r.get('title') or r.get('case_model') or '(untitled)'}"
                  for r in requests]
        choice, ok = QInputDialog.getItem(self, 'Open Test Request',
                                          'Pick a request:', labels,
                                          0, False)
        if not ok:
            return
        rq = requests[labels.index(choice)]
        dlg = TestRequestDialog(lib, request=rq, parent=self,
                                data_manager=self.data_manager)
        dlg.exec()

    def on_locate_finding(self, finding):
        """Jump to the Diagram tab and flash the component a finding points at."""
        self.tabs.setCurrentWidget(self.diagram_widget)
        self.diagram_widget.highlight_finding(finding)

    def on_tab_changed(self, index):
        # When user switches tabs, refresh that tab only
        self.update_active_tab()

        # Hide sensor panel when Compare tab is active to maximize graph space
        # Comparison tab is at index 2 (0=Diagram, 1=Graph, 2=Comparison, etc.)
        if index == 2:  # Comparison tab
            self.sensor_panel.hide()
            print("[APP] Sensor panel hidden (Compare tab active)")
        else:
            self.sensor_panel.show()
            print("[APP] Sensor panel shown")

    def update_active_tab(self):
        print("[SIGNAL] update_active_tab() called")
        # Always keep sensor panel in sync (lightweight)
        try:
            self.sensor_panel.update_ui()
        except Exception:
            pass
        # Update only the visible right-hand tab
        current_widget = self.tabs.currentWidget()
        try:
            if current_widget is self.diagram_widget:
                print("[SIGNAL] Updating diagram_widget")
                self.diagram_widget.update_ui()
            elif current_widget is self.graph_widget:
                print("[SIGNAL] Updating graph_widget")
                self.graph_widget.update_ui()
            elif current_widget is self.comparison_widget:
                print("[SIGNAL] Updating comparison_widget")
                self.comparison_widget.update_ui()
            elif current_widget is self.calculations_widget:
                # Update calculations widget (pressure threshold filtering)
                print("[SIGNAL] Updating calculations_widget (threshold filtering)")
                pass  # Widget updates on demand via filter button
            else:
                # Other widgets
                print("[SIGNAL] Updating other widget")
                pass
        except Exception as e:
            print(f"[SIGNAL] Error in update_active_tab: {e}")
            pass

    def set_light_theme(self):
        """Sets a professional light theme for the application."""
        app = QApplication.instance()
        app.setStyle("Fusion")
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(240, 240, 240))
        palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.black)
        palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(245, 245, 245))
        palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.black)
        palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.black)
        palette.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
        palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.black)
        palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
        app.setPalette(palette)
        self.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #c4c4c4; background: #ffffff; }
            QTabBar::tab { 
                background: #e1e1e1; color: #333; padding: 10px 25px; 
                font-weight: bold; border: 1px solid #c4c4c4; border-bottom: none;
                border-top-left-radius: 4px; border-top-right-radius: 4px;
            }
            QTabBar::tab:selected { 
                background: #ffffff; color: #007bff; border-bottom: 2px solid #007bff;
            }
        """)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

