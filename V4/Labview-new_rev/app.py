import sys
import argparse
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTabWidget, QLabel, QFrame, QPushButton,
                             QFileDialog)
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import Qt, QTimer

# Initialize logging early, before other imports that might log
from logging_setup import init_logging
from launch_sync import ensure_launch_cmds


ensure_launch_cmds()


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
        self._case_diagram_autosave_enabled = False

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
        # Diagnostics card 'Show on diagram' â†’ switch tab + highlight component
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
        self.tabs.addTab(self.diagnostics_widget,  "ðŸ©º Diagnostics")

        right_layout.addWidget(self.tabs)
        return right_panel

    def connect_signals(self):
        """Central place to connect all component signals to controller slots."""
        self.sensor_panel.load_csv_button.clicked.connect(self.open_csv_file_dialog)
        self.sensor_panel.load_config_button.clicked.connect(self.open_session_file_dialog)
        self.sensor_panel.save_config_button.clicked.connect(self.save_session_file_dialog)
        self.sensor_panel.range_button.clicked.connect(self.open_range_editor_dialog)
        
        # Update UI only for the active tab to reduce redundant work
        self.data_manager.data_changed.connect(self.update_active_tab)
        # Also listen to diagram model changes for standard component sensor mappings
        self.data_manager.diagram_model_changed.connect(self.update_active_tab)

        # Auto-save state on significant changes (with cooldown)
        self.data_manager.data_changed.connect(self.schedule_auto_save)
        self.data_manager.diagram_model_changed.connect(self.schedule_auto_save)
        self.data_manager.diagram_model_changed.connect(self.save_active_case_diagram)
        # Ensure mapping changes trigger auto-save (since we removed data_changed emit)
        if hasattr(self.data_manager, 'sensor_mapping_changed'):
            self.data_manager.sensor_mapping_changed.connect(self.schedule_auto_save)

        # --- FIX: Removed connection to the non-existent signal ---
        # self.sensor_panel.graph_sensor_toggled.connect(self.on_graph_sensor_toggled)
        
        # Connect diagram widget sensor port clicks to sensor panel highlighting
        self.diagram_widget.sensor_port_clicked.connect(self.sensor_panel.highlight_and_scroll_to_sensor)
        self.sensor_panel.sensor_locate_requested.connect(self.show_sensor_on_diagram)

    def show_sensor_on_diagram(self, sensor_name: str, role_key: str = "", canonical: str = ""):
        """Switch to the Diagram tab and bring the selected sensor dot into view."""
        if not sensor_name and not role_key and not canonical:
            return
        self.tabs.setCurrentWidget(self.diagram_widget)
        if hasattr(self.diagram_widget, 'locate_sensor'):
            found = self.diagram_widget.locate_sensor(sensor_name, role_key=role_key, canonical=canonical)
            if not found and hasattr(self, 'statusBar'):
                self.statusBar().showMessage("No visible diagram dot found for this sensor row", 3500)

    def show_diagram_tab_and_fit(self, delay_ms: int = 150):
        """Show the Diagram tab and fit the current scene after layout settles."""
        self.tabs.setCurrentWidget(self.diagram_widget)
        QTimer.singleShot(0, self.diagram_widget.zoom_to_fit)
        QTimer.singleShot(delay_ms, self.diagram_widget.zoom_to_fit)

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
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Session or Case File", "", "JSON Files (*.json)")
        if file_name:
            if self.open_case_or_diagram_file(file_name):
                QTimer.singleShot(200, self.save_state)
                return
            self._case_diagram_autosave_enabled = False
            self.data_manager.case_id = None
            self.data_manager.load_session(file_name)
            self.show_diagram_tab_and_fit()
            self.statusBar().showMessage("Opened as session", 4000)
            # Save state after loading session for undo
            QTimer.singleShot(200, self.save_state)

    def open_case_or_diagram_file(self, file_name: str) -> bool:
        """Open case workflow JSONs selected through the legacy config button."""
        import json
        import os

        try:
            with open(file_name, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            return False
        if not isinstance(payload, dict):
            return False

        folder = os.path.dirname(file_name)
        case = None
        diagram = None
        opened_as = ""

        if payload.get("id") and isinstance(payload.get("topology"), dict):
            case = payload
            diagram_path = os.path.join(folder, "diagram.json")
            if os.path.exists(diagram_path):
                with open(diagram_path, "r", encoding="utf-8") as f:
                    diagram = json.load(f)
            else:
                diagram = self._case_library().load_diagram(case["id"])
            opened_as = "case"
        elif isinstance(payload.get("components"), (dict, list)):
            diagram = payload
            case_path = os.path.join(folder, "case.json")
            if os.path.exists(case_path):
                with open(case_path, "r", encoding="utf-8") as f:
                    case = json.load(f)
                opened_as = "case"
            else:
                case_id = os.path.basename(folder) or "opened_diagram"
                case = {
                    "id": case_id,
                    "model": case_id,
                    "topology": diagram.get("_topology", {}),
                    "settings": {},
                    "parts": {},
                }
                opened_as = "diagram"
        else:
            return False

        if not case:
            return False
        if not diagram:
            from diagram_from_request import generate_case_diagram

            diagram = generate_case_diagram(case.get("topology", {}), self._case_library().families())

        from case_library import apply_case_to_session

        self._case_diagram_autosave_enabled = False
        apply_case_to_session(case, diagram, self.data_manager, emit_signals=False)
        try:
            lib_cases = os.path.abspath(self._case_library().cases_dir)
            selected = os.path.abspath(file_name)
            self._case_diagram_autosave_enabled = (
                opened_as == "case"
                and os.path.commonpath([lib_cases, selected]) == lib_cases
            )
            if self._case_diagram_autosave_enabled:
                self._case_library().mark_used(case["id"])
        except Exception:
            self._case_diagram_autosave_enabled = False
        self.show_diagram_tab_and_fit()
        self.diagram_widget.build_scene_from_model()
        label = case.get("model") or case.get("id")
        self.statusBar().showMessage(f"Opened as {opened_as}: {label}", 4000)
        return True
    
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
        """Menu bar for the case-centric workflow."""
        menu = self.menuBar().addMenu('&Cases')
        act_cases = menu.addAction('Cases...')
        act_cases.triggered.connect(self.open_cases)
        act_new_case = menu.addAction('New Case / Process Diagram...')
        act_new_case.triggered.connect(self.new_case_process_diagram)

    def _case_library(self):
        from case_library import CaseLibrary
        if not hasattr(self, '_case_library_inst'):
            self._case_library_inst = CaseLibrary()
        return self._case_library_inst

    def new_case_process_diagram(self):
        from case_dialogs import NewCaseDialog
        dlg = NewCaseDialog(self._case_library(), parent=self, data_manager=self.data_manager)
        if dlg.exec() and self.data_manager.case_id:
            self._case_diagram_autosave_enabled = True
            self.show_diagram_tab_and_fit()

    def open_cases(self):
        from case_dialogs import CaseLibraryDialog
        dlg = CaseLibraryDialog(self._case_library(), parent=self,
                                data_manager=self.data_manager)
        dlg.exec()
        if self.data_manager.case_id:
            self._case_diagram_autosave_enabled = True
            self.show_diagram_tab_and_fit()

    def save_active_case_diagram(self):
        """Persist diagram edits for the actively opened case workflow."""
        if not getattr(self, "_case_diagram_autosave_enabled", False):
            return
        case_id = getattr(self.data_manager, "case_id", None)
        if not case_id:
            return
        try:
            diagram = self.data_manager._sanitize_diagram_model(self.data_manager.diagram_model)
            diagram_case_id = diagram.get("_case_id")
            if diagram_case_id != case_id:
                print(
                    f"[CASE_LIBRARY] Refusing autosave for case {case_id}: "
                    f"diagram belongs to {diagram_case_id!r}"
                )
                return
            self._case_library().save_diagram(case_id, diagram)
        except Exception as exc:
            print(f"[CASE_LIBRARY] Could not save active case diagram: {exc}")

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


