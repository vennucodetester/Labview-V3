"""
Calculations Widget (REBUILT from goal.md Step 4)

Provides the new unified calculation tab with:
- QTreeWidget for hierarchical data display
- Custom NestedHeaderView for complex multi-level headers
- Integration with run_batch_processing() orchestrator
- Replaces old coolprop_calculator.py system entirely
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTreeWidget, QTreeWidgetItem, QHeaderView, QLabel,
                             QMessageBox, QApplication, QDialog, QTableWidget,
                             QTableWidgetItem, QMenu, QTextEdit, QDialogButtonBox,
                             QSplitter, QGroupBox, QCheckBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QFont, QColor, QClipboard, QAction
import pandas as pd
from input_dialog import InputDialog
import math
from ph_diagram_audit_widget import PhDiagramAuditWidget
from process_diagram_audit_widget import ProcessDiagramAuditWidget


def _build_header_data(module_labels: list) -> tuple:
    """Build the 4 header lists for a SHARED-compressor layout.

    All modules share one compressor / condenser / mass-flow block.

    Returns (main_sections, sub_sections, units, column_names) where:
    - main_sections : list of (label_str, column_span) tuples
    - sub_sections  : list of per-column descriptive labels
    - units         : list of per-column unit strings
    - column_names  : list of DataFrame column keys (data keys)
    """
    from circuit_semantics import module_abbrev, txv_outlet_key, coil_outlet_key

    COIL_SUB   = ["TXV out", "TXV out", "Coil out", "T sat",
                  "Superheat", "Density", "Enthalpy", "Entropy"]
    COIL_UNITS = ["°F", "°F", "°F", "°F",
                  "°F", "kg/m³", "kJ/kg", "kJ/(kg·K)"]
    TXV_SUB    = ["Temp", "T sat", "Subcool", "Enthalpy"]
    TXV_UNITS  = ["°F", "°F", "°F", "kJ/kg"]

    ms, ss, us, cn = [], [], [], []

    # ── Per-module coil sections ─────────────────────────────────────────
    for label in module_labels:
        ab   = module_abbrev(label)
        ab_u = module_abbrev(label, upper=True)
        ms.append((f'AT {ab_u} coil', 8))
        ss.extend(COIL_SUB)
        us.extend(COIL_UNITS)
        cn.extend([
            f'T_1a-{ab}',
            txv_outlet_key(label),    # T_1b-lh / T_1b-ctr / T_1b-rh
            coil_outlet_key(label),   # T_2a-LH / T_2a-CTR / T_2a-RH
            f'T_sat.{ab}',
            f'S.H_{ab} coil',
            f'D_coil {ab}',
            f'H_coil {ab}',
            f'S_coil {ab}',
        ])

    # ── Fixed: compressor inlet (7 cols) ────────────────────────────────
    ms.append(("At compressor inlet", 7))
    ss.extend(["Pressure", "Temp", "T sat", "Superheat", "Density", "Enthalpy", "Entropy"])
    us.extend(["PSIG", "°F", "°F", "°F", "kg/m³", "kJ/kg", "kJ/(kg·K)"])
    cn.extend(["P_suction", "T_2b", "T_sat.comp.in", "S.H_total",
               "D_comp.in", "H_comp.in", "S_comp.in"])

    # ── Fixed: compressor outlet (2 cols) ───────────────────────────────
    ms.append(("Comp outlet", 2))
    ss.extend(["Temp", "RPM"])
    us.extend(["°F", "RPM"])
    cn.extend(["T_3a", "rpm"])

    # ── Fixed: condenser (7 cols) ───────────────────────────────────────
    ms.append(("At Condenser", 7))
    ss.extend(["Inlet", "Pressure", "Outlet", "T sat", "Subcool", "Water in", "Water out"])
    us.extend(["°F", "PSIG", "°F", "°F", "°F", "°F", "°F"])
    cn.extend(["T_3b", "P_disch", "T_4a", "T_sat.cond", "S.C", "T_waterin", "T_waterout"])

    # ── Per-module TXV sections ──────────────────────────────────────────
    for label in module_labels:
        ab   = module_abbrev(label)
        ab_u = module_abbrev(label, upper=True)
        ms.append((f'At TXV {ab_u}', 4))
        ss.extend(TXV_SUB)
        us.extend(TXV_UNITS)
        cn.extend([
            f'T_4b-{ab}',
            f'T_sat.txv.{ab}',
            f'S.C-txv.{ab}',
            f'H_txv.{ab}',
        ])

    # ── Fixed: total (2 cols) ────────────────────────────────────────────
    ms.append(("TOTAL", 2))
    ss.extend(["Mass flow", "Capacity"])
    us.extend(["lb/hr", "BTU/hr"])
    cn.extend(["m_dot", "qc"])

    return ms, ss, us, cn


def _build_header_data_cassette(module_labels: list) -> tuple:
    """Build the 4 header lists for a CASSETTE layout.

    Each unit has its own independent compressor / condenser / mass-flow block.
    Column names match the per-unit suffixed columns produced by run_batch_processing()
    in cassette mode (e.g. T_2b-lh, P_suc-lh, m_dot-lh, qc-lh).

    Returns (main_sections, sub_sections, units, column_names).
    """
    from circuit_semantics import module_abbrev, txv_outlet_key, coil_outlet_key

    COIL_SUB   = ["TXV out", "TXV out", "Coil out", "T sat",
                  "Superheat", "Density", "Enthalpy", "Entropy"]
    COIL_UNITS = ["°F", "°F", "°F", "°F",
                  "°F", "kg/m³", "kJ/kg", "kJ/(kg·K)"]
    TXV_SUB    = ["Temp", "T sat", "Subcool", "Enthalpy"]
    TXV_UNITS  = ["°F", "°F", "°F", "kJ/kg"]
    # Per-unit compressor-inlet: Pressure, Temp, T sat, Superheat, Density, Enthalpy, Entropy
    COMP_IN_SUB   = ["Pressure", "Temp", "T sat", "Superheat", "Density", "Enthalpy", "Entropy"]
    COMP_IN_UNITS = ["PSIG", "°F", "°F", "°F", "kg/m³", "kJ/kg", "kJ/(kg·K)"]
    # Per-unit compressor-outlet: Temp, RPM
    COMP_OUT_SUB   = ["Temp", "RPM"]
    COMP_OUT_UNITS = ["°F", "RPM"]
    # Per-unit condenser: Inlet, Pressure, Outlet, T sat, Subcool, Water in, Water out
    COND_SUB   = ["Inlet", "Pressure", "Outlet", "T sat", "Subcool", "Water in", "Water out"]
    COND_UNITS = ["°F", "PSIG", "°F", "°F", "°F", "°F", "°F"]
    # Per-unit total: Mass flow, Capacity
    TOTAL_SUB   = ["Mass flow", "Capacity"]
    TOTAL_UNITS = ["lb/hr", "BTU/hr"]

    ms, ss, us, cn = [], [], [], []

    for label in module_labels:
        ab   = module_abbrev(label)
        ab_u = module_abbrev(label, upper=True)

        # Coil section (8 cols)
        ms.append((f'AT {ab_u} coil', 8))
        ss.extend(COIL_SUB)
        us.extend(COIL_UNITS)
        cn.extend([
            f'T_1a-{ab}',
            txv_outlet_key(label),
            coil_outlet_key(label),
            f'T_sat.{ab}',
            f'S.H_{ab} coil',
            f'D_coil {ab}',
            f'H_coil {ab}',
            f'S_coil {ab}',
        ])

        # Per-unit compressor inlet (7 cols)
        ms.append((f'{ab_u} Comp inlet', 7))
        ss.extend(COMP_IN_SUB)
        us.extend(COMP_IN_UNITS)
        cn.extend([
            f'P_suc-{ab}',
            f'T_2b-{ab}',
            f'T_sat.comp.in-{ab}',
            f'S.H_total-{ab}',
            f'D_comp.in-{ab}',
            f'H_comp.in-{ab}',
            f'S_comp.in-{ab}',
        ])

        # Per-unit compressor outlet (2 cols)
        ms.append((f'{ab_u} Comp out', 2))
        ss.extend(COMP_OUT_SUB)
        us.extend(COMP_OUT_UNITS)
        cn.extend([f'T_3a-{ab}', f'rpm-{ab}'])

        # Per-unit condenser (7 cols)
        ms.append((f'{ab_u} Condenser', 7))
        ss.extend(COND_SUB)
        us.extend(COND_UNITS)
        cn.extend([
            f'T_3b-{ab}',
            f'P_disch-{ab}',
            f'T_4a-{ab}',
            f'T_sat.cond-{ab}',
            f'S.C-{ab}',
            f'T_waterin-{ab}',
            f'T_waterout-{ab}',
        ])

        # Per-unit TXV (4 cols)
        ms.append((f'At TXV {ab_u}', 4))
        ss.extend(TXV_SUB)
        us.extend(TXV_UNITS)
        cn.extend([
            f'T_4b-{ab}',
            f'T_sat.txv.{ab}',
            f'S.C-txv.{ab}',
            f'H_txv.{ab}',
        ])

        # Per-unit total (2 cols)
        ms.append((f'{ab_u} Total', 2))
        ss.extend(TOTAL_SUB)
        us.extend(TOTAL_UNITS)
        cn.extend([f'm_dot-{ab}', f'qc-{ab}'])

    return ms, ss, us, cn


class NestedHeaderView(QHeaderView):
    """
    Custom QHeaderView that draws 4-ROW nested headers matching Calculations-DDT.xlsx layout.

    Creates a FOUR-row header structure:
    - Row 1: Main section headers (e.g., "AT LH coil", "At compressor inlet")
    - Row 2: Sub-section headers (e.g., "TXV out", "Coil out", "Density")
    - Row 3: Units (e.g., "°F", "kg/m³", "kJ/kg")
    - Row 4: Actual column names (e.g., "T_1a-lh", "D_coil lh")

    Call configure() after construction (or after diagram changes) to set the
    column schema dynamically — no hardcoded LH/CTR/RH here.
    """

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setStretchLastSection(True)
        # Start with empty lists; CalculationsWidget._rebuild_column_schema() will
        # call configure() immediately after construction.
        self.main_sections = []
        self.sub_sections  = []
        self.units         = []
        self.column_names  = []
        self.sub_headers   = []
        self.data_keys     = []

    def configure(self, main_sections, sub_sections, units, column_names):
        """Replace all header data and trigger a repaint.

        Called by CalculationsWidget._rebuild_column_schema() whenever the
        diagram model changes (new session, new template, wizard).
        """
        self.main_sections = main_sections
        self.sub_sections  = sub_sections
        self.units         = units
        self.column_names  = column_names
        self.sub_headers   = column_names   # backward compatibility alias
        self.data_keys     = column_names
        self.update()

    def paintEvent(self, event):
        """Custom paint event to draw 4-ROW nested headers (we fully render all rows)."""
        painter = QPainter(self.viewport())
        painter.save()

        height_quarter = self.height() // 4

        # ===== ROW 1: Main Section Headers (Top quarter) =====
        font = self.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        painter.setFont(font)
        painter.fillRect(0, 0, self.width(), height_quarter, QColor(220, 220, 220))

        col_index = 0
        for text, span in self.main_sections:
            if span == 0:
                continue

            first_col_rect = self.sectionViewportPosition(col_index)
            last_col_rect = self.sectionViewportPosition(col_index + span - 1)
            group_width = (last_col_rect + self.sectionSize(col_index + span - 1)) - first_col_rect

            rect = self.rect()
            rect.setLeft(first_col_rect)
            rect.setWidth(group_width)
            rect.setTop(0)
            rect.setHeight(height_quarter)

            painter.setPen(QColor(80, 80, 80))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

            col_index += span

        # ===== ROW 2: Sub-section Headers (Second quarter) =====
        font.setBold(False)
        font.setPointSize(font.pointSize() - 1)
        font.setItalic(True)
        painter.setFont(font)
        painter.fillRect(0, height_quarter, self.width(), height_quarter, QColor(240, 240, 240))

        for col_idx, sub_text in enumerate(self.sub_sections):
            col_rect = self.sectionViewportPosition(col_idx)
            col_width = self.sectionSize(col_idx)

            rect = self.rect()
            rect.setLeft(col_rect)
            rect.setWidth(col_width)
            rect.setTop(height_quarter)
            rect.setHeight(height_quarter)

            painter.setPen(QColor(100, 100, 100))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, sub_text)

        # ===== ROW 3: Units (Third quarter) =====
        font.setItalic(True)
        font.setBold(False)
        font.setPointSize(max(9, font.pointSize() - 1))
        painter.setFont(font)
        painter.fillRect(0, height_quarter * 2, self.width(), height_quarter, QColor(230, 240, 255))

        for col_idx, unit_text in enumerate(self.units):
            col_rect = self.sectionViewportPosition(col_idx)
            col_width = self.sectionSize(col_idx)

            rect = self.rect()
            rect.setLeft(col_rect)
            rect.setWidth(col_width)
            rect.setTop(height_quarter * 2)
            rect.setHeight(height_quarter)

            painter.setPen(QColor(120, 120, 120))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            painter.drawText(rect.adjusted(2, 0, -2, 0), Qt.AlignmentFlag.AlignCenter, unit_text)

        # ===== ROW 4: Actual column names (Bottom quarter) =====
        font.setItalic(False)
        font.setBold(False)
        font.setPointSize(max(9, font.pointSize()))
        painter.setFont(font)
        painter.fillRect(0, height_quarter * 3, self.width(), height_quarter, QColor(255, 255, 255))

        for col_idx, col_name in enumerate(self.column_names):
            col_rect = self.sectionViewportPosition(col_idx)
            col_width = self.sectionSize(col_idx)

            rect = self.rect()
            rect.setLeft(col_rect)
            rect.setWidth(col_width)
            rect.setTop(height_quarter * 3)
            rect.setHeight(height_quarter)

            painter.setPen(QColor(120, 120, 120))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            painter.drawText(rect.adjusted(2, 0, -2, 0), Qt.AlignmentFlag.AlignCenter, col_name)

        painter.restore()

    def sizeHint(self):
        """Quadruple the height for 4 rows."""
        size = super().sizeHint()
        size.setHeight(size.height() * 4)
        return size


class CalculationAuditDialog(QDialog):
    """Dialog to display detailed calculation audit for a specific row with visual diagrams."""

    def __init__(self, audit_text, row_index, row_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Calculation Audit - Row {row_index}")

        # Set dialog to be resizable and maximizable
        from PyQt6.QtCore import Qt
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)

        # Start with a reasonable size (80% of screen)
        if parent:
            screen = parent.screen()
        else:
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()

        screen_size = screen.availableGeometry()
        width = int(screen_size.width() * 0.85)
        height = int(screen_size.height() * 0.85)
        self.resize(width, height)

        self.audit_text = audit_text
        self.row_data = row_data

        main_layout = QVBoxLayout(self)

        # MAIN HORIZONTAL SPLITTER: Left (diagrams) + Right (calculations)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # ===== LEFT PANEL: Visual Diagrams (stacked vertically) =====
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(5)

        # PH Diagram (takes 55% of left panel)
        try:
            self.ph_widget = PhDiagramAuditWidget(row_data)
            left_layout.addWidget(self.ph_widget, stretch=55)
        except Exception as e:
            error_label = QLabel(f"Error loading PH diagram: {e}")
            left_layout.addWidget(error_label, stretch=55)

        # Process Diagram (takes 45% of left panel - increased for better visibility)
        try:
            self.process_widget = ProcessDiagramAuditWidget(row_data)
            left_layout.addWidget(self.process_widget, stretch=45)
        except Exception as e:
            error_label = QLabel(f"Error loading process diagram: {e}")
            left_layout.addWidget(error_label, stretch=45)

        main_splitter.addWidget(left_widget)

        # ===== RIGHT PANEL: Calculation Summary =====
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 0, 0, 0)
        right_layout.setSpacing(5)

        # Header
        summary_header = QLabel("Calculation Summary")
        header_font = QFont()
        header_font.setBold(True)
        header_font.setPointSize(11)
        summary_header.setFont(header_font)
        right_layout.addWidget(summary_header)

        # Calculation text display - SHOW FULL DETAILS BY DEFAULT
        self.calc_display = QTextEdit()
        self.calc_display.setReadOnly(True)
        # Start with full audit text showing all 9 sections
        self.calc_display.setPlainText(audit_text)
        right_layout.addWidget(self.calc_display)

        # "Show Summary" button (toggles to compact HTML view)
        self.details_button = QPushButton("Show Summary")
        self.details_button.clicked.connect(self.toggle_full_details)
        right_layout.addWidget(self.details_button)

        main_splitter.addWidget(right_widget)

        # 50/50 split between diagrams and calculations
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 1)

        main_layout.addWidget(main_splitter)

        # Close button
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        main_layout.addWidget(buttons)

    def toggle_full_details(self):
        """Toggle between full audit text and compact summary."""
        if self.details_button.text() == "Show Summary":
            # Switch to HTML summary view
            summary_html = self.generate_calculation_summary(self.row_data, self.audit_text)
            self.calc_display.setHtml(summary_html)
            self.details_button.setText("Show Full Details")
        else:
            # Switch back to full audit text (all 9 sections)
            self.calc_display.setPlainText(self.audit_text)
            self.details_button.setText("Show Summary")

    def _circuit_superheat_rows(self, row_data, safe_get) -> str:
        """Return HTML <tr> rows for Circuit Superheat table — dynamic per module."""
        from circuit_semantics import get_all_module_labels, module_abbrev, coil_outlet_key
        labels = get_all_module_labels(
            self.parent().data_manager.diagram_model
            if self.parent() and hasattr(self.parent(), 'data_manager') else {}
        ) or ['Left']
        rows = []
        for lbl in labels:
            ab   = module_abbrev(lbl)
            ab_u = module_abbrev(lbl, upper=True)
            rows.append(
                f"<tr>"
                f"<td>{ab_u}</td>"
                f"<td>{safe_get(f'S.H_{ab} coil')}</td>"
                f"<td>{safe_get(coil_outlet_key(lbl))}</td>"
                f"<td>{safe_get(f'H_coil {ab}')}</td>"
                f"</tr>"
            )
        return "\n".join(rows)

    def _txv_inlet_row(self, row_data, safe_get) -> str:
        """Return the first TXV Inlet HTML <tr> row using the first available module."""
        from circuit_semantics import get_all_module_labels, module_abbrev
        labels = get_all_module_labels(
            self.parent().data_manager.diagram_model
            if self.parent() and hasattr(self.parent(), 'data_manager') else {}
        ) or ['Left']
        if not labels:
            return ""
        ab = module_abbrev(labels[0])
        ab_u = module_abbrev(labels[0], upper=True)
        return (
            f"<tr>"
            f"<td>TXV Inlet ({ab_u})</td>"
            f"<td>{safe_get(f'T_4b-{ab}')}</td>"
            f"<td>—</td>"
            f"<td>{safe_get(f'H_txv.{ab}')}</td>"
            f"</tr>"
        )

    def _get_diagram_model(self):
        """Return the diagram model from the parent CalculationsWidget, or {}."""
        try:
            p = self.parent()
            if p and hasattr(p, 'data_manager'):
                return p.data_manager.diagram_model or {}
        except Exception:
            pass
        return {}

    def _calculate_approach_temp(self, row_data, ab: str = ''):
        """Calculate approach temperature safely.

        For cassette, pass ab=module_abbrev(label) so per-unit column names are used.
        """
        try:
            suffix = f'-{ab}' if ab else ''
            t_water = row_data.get(f'T_waterin{suffix}')
            t_sat   = row_data.get(f'T_sat.cond{suffix}')
            if t_water is None or t_sat is None:
                return "N/A"
            if isinstance(t_water, float) and math.isnan(t_water):
                return "N/A"
            if isinstance(t_sat, float) and math.isnan(t_sat):
                return "N/A"
            approach = float(t_water) - float(t_sat)
            return f"{t_water:.2f} - {t_sat:.2f} = {approach:.1f} °F"
        except (ValueError, TypeError):
            return "N/A"

    def generate_calculation_summary(self, row_data, audit_text):
        """Generate HTML-formatted calculation summary from row data.

        Detects system type (shared vs cassette) and builds an appropriate layout.
        """
        from circuit_semantics import get_all_module_labels, module_abbrev as _mab
        from calculation_orchestrator import _detect_system_type

        model       = self._get_diagram_model()
        labels      = get_all_module_labels(model) or ['Left']
        system_type = _detect_system_type(model)

        def safe_get(key, default="N/A"):
            val = row_data.get(key)
            if val is None or (isinstance(val, float) and math.isnan(val)):
                return default
            if isinstance(val, float):
                return f"{val:.2f}"
            return str(val)

        CSS = """
        <style>
            body { font-family: Arial, sans-serif; font-size: 10pt; }
            h3 { color: #333; border-bottom: 2px solid #007bff; padding-bottom: 5px; margin-top: 15px; }
            table { border-collapse: collapse; width: 100%; margin-top: 10px; }
            th { background-color: #007bff; color: white; padding: 8px; text-align: left; font-weight: bold; }
            td { padding: 6px 8px; border-bottom: 1px solid #ddd; }
            tr:hover { background-color: #f5f5f5; }
            .good { color: #28a745; font-weight: bold; }
            .warning { color: #fd7e14; font-weight: bold; }
            .bad { color: #dc3545; font-weight: bold; }
            .label { font-weight: bold; color: #555; }
            .status { font-size: 14pt; }
        </style>"""

        def status_icon(value, good_condition):
            return "✓" if good_condition else ("⚠" if value is not None else "?")

        LEGEND = """
        <h3>📊 Legend</h3>
        <p>
        <span class="status">✓</span> = Normal operation<br>
        <span class="status">⚠</span> = Warning / Anomaly<br>
        <span class="good">Green values</span> = Good<br>
        <span class="warning">Orange values</span> = Marginal<br>
        <span class="bad">Red values</span> = Problem / Reverse flow
        </p>"""

        # ── Circuit Superheat table — same for both layouts ──────────────
        circuit_sh_rows = self._circuit_superheat_rows(row_data, safe_get)

        if system_type == 'cassette':
            # ── Cassette: per-unit sections ──────────────────────────────
            unit_sections = ""
            for lbl in labels:
                ab   = _mab(lbl)
                ab_u = _mab(lbl, upper=True)
                sfx  = f'-{ab}'

                qc       = row_data.get(f'qc{sfx}', 0)
                sc       = row_data.get(f'S.C{sfx}', 0)
                sh_total = row_data.get(f'S.H_total{sfx}', 0)
                qc_color = "#28a745" if (qc and qc > 0) else "#dc3545"
                sc_color = "#28a745" if (sc and sc > 0) else "#dc3545"
                sh_color = "#28a745" if (sh_total and sh_total > 5) else "#fd7e14"
                qc_st = status_icon(qc, qc is not None and qc > 0)
                sc_st = status_icon(sc, sc is not None and sc > 0)
                sh_st = status_icon(sh_total, sh_total is not None and sh_total > 5)

                unit_sections += f"""
                <h3>🔧 Unit {ab_u} Performance</h3>
                <table>
                <tr><td class="label">Status</td><td class="label">Parameter</td>
                    <td class="label">Value</td><td class="label">Unit</td></tr>
                <tr><td class="status">{qc_st}</td><td>Capacity</td>
                    <td style="color:{qc_color};font-weight:bold;">{safe_get(f'qc{sfx}')}</td>
                    <td>BTU/hr</td></tr>
                <tr><td class="status">{sc_st}</td><td>Subcooling</td>
                    <td style="color:{sc_color};font-weight:bold;">{safe_get(f'S.C{sfx}')}</td>
                    <td>°F</td></tr>
                <tr><td class="status">{sh_st}</td><td>Total Superheat</td>
                    <td style="color:{sh_color};font-weight:bold;">{safe_get(f'S.H_total{sfx}')}</td>
                    <td>°F</td></tr>
                <tr><td></td><td>Mass Flow Rate</td>
                    <td>{safe_get(f'm_dot{sfx}')}</td><td>lb/hr</td></tr>
                <tr><td></td><td>Mass Flow (displacement check)</td>
                    <td>{safe_get(f'm_dot_disp{sfx}')}</td><td>lb/hr</td></tr>
                <tr><td></td><td>Coil Capacity</td>
                    <td>{safe_get(f'qc_coils{sfx}')}</td><td>BTU/hr</td></tr>
                <tr><td></td><td>Suction Line Heat Gain</td>
                    <td>{safe_get(f'Q_line_gain{sfx}')}</td><td>BTU/hr</td></tr>
                <tr><td></td><td>Compressor Work (refrigerant side)</td>
                    <td>{safe_get(f'W_comp{sfx}')}</td><td>BTU/hr</td></tr>
                <tr><td></td><td>COP</td>
                    <td>{safe_get(f'COP{sfx}')}</td><td>—</td></tr>
                <tr><td></td><td>EER</td>
                    <td>{safe_get(f'EER{sfx}')}</td><td>BTU/(hr·W)</td></tr>
                <tr><td></td><td>Isentropic Efficiency (η_is)</td>
                    <td>{safe_get(f'eta_is{sfx}')}</td><td>—</td></tr>
                </table>

                <h3>🔄 Unit {ab_u} Cycle State Points</h3>
                <table>
                <tr><th>Location</th><th>Temperature (°F)</th>
                    <th>Pressure (PSIG)</th><th>Enthalpy (kJ/kg)</th></tr>
                <tr><td>Compressor Inlet</td><td>{safe_get(f'T_2b{sfx}')}</td>
                    <td>{safe_get(f'P_suc{sfx}')}</td>
                    <td>{safe_get(f'H_comp.in{sfx}')}</td></tr>
                <tr><td>Compressor Outlet</td><td>{safe_get(f'T_3a{sfx}')}</td>
                    <td>{safe_get(f'P_disch{sfx}')}</td><td>—</td></tr>
                <tr><td>Condenser Inlet</td><td>{safe_get(f'T_3b{sfx}')}</td>
                    <td>{safe_get(f'P_disch{sfx}')}</td><td>—</td></tr>
                <tr><td>Condenser Outlet</td><td>{safe_get(f'T_4a{sfx}')}</td>
                    <td>{safe_get(f'P_disch{sfx}')}</td><td>—</td></tr>
                <tr><td>TXV Inlet ({ab_u})</td><td>{safe_get(f'T_4b-{ab}')}</td>
                    <td>—</td><td>{safe_get(f'H_txv.{ab}')}</td></tr>
                </table>

                <h3>💧 Unit {ab_u} Condenser Water Side</h3>
                <table>
                <tr><th>Parameter</th><th>Value</th></tr>
                <tr><td>Water Inlet Temp</td><td>{safe_get(f'T_waterin{sfx}')} °F</td></tr>
                <tr><td>Water Outlet Temp</td><td>{safe_get(f'T_waterout{sfx}')} °F</td></tr>
                <tr><td>Condenser Sat Temp</td><td>{safe_get(f'T_sat.cond{sfx}')} °F</td></tr>
                <tr><td>Approach Temp</td><td>{self._calculate_approach_temp(row_data, ab)}</td></tr>
                </table>"""

            html = f"""<html><head>{CSS}</head><body>
            <h3>🌡️ Circuit Superheat</h3>
            <table>
            <tr><th>Circuit</th><th>Superheat (°F)</th>
                <th>Evap Outlet Temp (°F)</th><th>Enthalpy (kJ/kg)</th></tr>
            {circuit_sh_rows}
            </table>
            {unit_sections}
            {LEGEND}
            </body></html>"""

        else:
            # ── Shared compressor: classic single-block layout ────────────
            qc       = row_data.get('qc', 0)
            sc       = row_data.get('S.C', 0)
            sh_total = row_data.get('S.H_total', 0)
            qc_color = "#28a745" if (qc and qc > 0) else "#dc3545"
            sc_color = "#28a745" if (sc and sc > 0) else "#dc3545"
            sh_color = "#28a745" if (sh_total and sh_total > 5) else "#fd7e14"
            qc_st = status_icon(qc, qc is not None and qc > 0)
            sc_st = status_icon(sc, sc is not None and sc > 0)
            sh_st = status_icon(sh_total, sh_total is not None and sh_total > 5)

            html = f"""<html><head>{CSS}</head><body>

            <h3>🔧 System Performance</h3>
            <table>
            <tr><td class="label">Status</td><td class="label">Parameter</td>
                <td class="label">Value</td><td class="label">Unit</td></tr>
            <tr><td class="status">{qc_st}</td><td>Capacity (qc)</td>
                <td style="color:{qc_color};font-weight:bold;">{safe_get('qc')}</td>
                <td>BTU/hr</td></tr>
            <tr><td class="status">{sc_st}</td><td>Subcooling (SC)</td>
                <td style="color:{sc_color};font-weight:bold;">{safe_get('S.C')}</td>
                <td>°F</td></tr>
            <tr><td class="status">{sh_st}</td><td>Total Superheat</td>
                <td style="color:{sh_color};font-weight:bold;">{safe_get('S.H_total')}</td>
                <td>°F</td></tr>
            <tr><td></td><td>Mass Flow Rate</td>
                <td>{safe_get('m_dot')}</td><td>lb/hr</td></tr>
            <tr><td></td><td>Mass Flow (displacement check)</td>
                <td>{safe_get('m_dot_disp')}</td><td>lb/hr</td></tr>
            <tr><td></td><td>Coil Capacity (qc_coils)</td>
                <td>{safe_get('qc_coils')}</td><td>BTU/hr</td></tr>
            <tr><td></td><td>Suction Line Heat Gain</td>
                <td>{safe_get('Q_line_gain')}</td><td>BTU/hr</td></tr>
            <tr><td></td><td>Compressor Work (refrigerant side)</td>
                <td>{safe_get('W_comp')}</td><td>BTU/hr</td></tr>
            <tr><td></td><td>COP</td>
                <td>{safe_get('COP')}</td><td>—</td></tr>
            <tr><td></td><td>EER</td>
                <td>{safe_get('EER')}</td><td>BTU/(hr·W)</td></tr>
            <tr><td></td><td>Isentropic Efficiency (η_is)</td>
                <td>{safe_get('eta_is')}</td><td>—</td></tr>
            </table>

            <h3>🌡️ Circuit Superheat</h3>
            <table>
            <tr><th>Circuit</th><th>Superheat (°F)</th>
                <th>Evap Outlet Temp (°F)</th><th>Enthalpy (kJ/kg)</th></tr>
            {circuit_sh_rows}
            </table>

            <h3>🔄 Cycle State Points</h3>
            <table>
            <tr><th>Location</th><th>Temperature (°F)</th>
                <th>Pressure (PSIG)</th><th>Enthalpy (kJ/kg)</th></tr>
            <tr><td>Compressor Inlet</td><td>{safe_get('T_2b')}</td>
                <td>{safe_get('P_suction')}</td><td>{safe_get('H_comp.in')}</td></tr>
            <tr><td>Compressor Outlet</td><td>{safe_get('T_3a')}</td>
                <td>{safe_get('P_disch')}</td><td>—</td></tr>
            <tr><td>Condenser Inlet</td><td>{safe_get('T_3b')}</td>
                <td>{safe_get('P_disch')}</td><td>—</td></tr>
            <tr><td>Condenser Outlet</td><td>{safe_get('T_4a')}</td>
                <td>{safe_get('P_disch')}</td><td>—</td></tr>
            {self._txv_inlet_row(row_data, safe_get)}
            </table>

            <h3>💧 Condenser Water Side</h3>
            <table>
            <tr><th>Parameter</th><th>Value</th></tr>
            <tr><td>Water Inlet Temp</td><td>{safe_get('T_waterin')} °F</td></tr>
            <tr><td>Water Outlet Temp</td><td>{safe_get('T_waterout')} °F</td></tr>
            <tr><td>Condenser Sat Temp</td><td>{safe_get('T_sat.cond')} °F</td></tr>
            <tr><td>Approach Temp</td><td>{self._calculate_approach_temp(row_data)}</td></tr>
            </table>

            {LEGEND}
            </body></html>"""

        return html


class CalculationsWidget(QWidget):
    """
    New unified Calculations tab widget.

    Replaces the old coolprop_calculator.py system with the new
    run_batch_processing() orchestrator.
    """

    # Signal emitted when processed data is ready for P-h diagram
    filtered_data_ready = pyqtSignal(object)

    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.processed_df = None
        self.audit_mode = False

        self.setup_ui()

        # Rebuild column schema now, and again whenever the diagram changes
        if hasattr(self.data_manager, 'diagram_model_changed'):
            self.data_manager.diagram_model_changed.connect(self._rebuild_column_schema)
        self._rebuild_column_schema()

        # Enable keyboard shortcuts
        copy_shortcut = QAction("Copy", self)
        copy_shortcut.setShortcut("Ctrl+C")
        copy_shortcut.triggered.connect(self.on_copy_triggered)
        self.addAction(copy_shortcut)
    
    def on_copy_triggered(self):
        """Handle Ctrl+C keyboard shortcut for tree widget."""
        # Determine which widget has focus
        focused_widget = QApplication.focusWidget()

        if focused_widget == self.tree_widget:
            # Copy from tree widget
            self.copy_tree_selection()

    def _rebuild_column_schema(self):
        """Rebuild the header and clear stale data whenever the diagram model changes.

        Branches on system_type:
        - 'shared'   → _build_header_data()         (one compressor/condenser block)
        - 'cassette' → _build_header_data_cassette() (per-unit blocks for every module)

        Called once on construction and again on every diagram_model_changed signal.
        """
        from circuit_semantics import get_all_module_labels
        from calculation_orchestrator import _detect_system_type

        model       = self.data_manager.diagram_model if self.data_manager else {}
        labels      = get_all_module_labels(model) or ['Left']
        system_type = _detect_system_type(model)

        if system_type == 'cassette':
            ms, ss, us, cn = _build_header_data_cassette(labels)
        else:
            ms, ss, us, cn = _build_header_data(labels)

        self.header.configure(ms, ss, us, cn)

        self.tree_widget.setColumnCount(len(cn))
        self.tree_widget.setHeaderLabels(cn)
        self.tree_widget.clear()

        self.processed_df = None
        if hasattr(self, 'export_button'):
            self.export_button.setEnabled(False)

    def setup_ui(self):
        """Create the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # ==================== Compact Control Panel ====================
        # All controls in one line: discharge press input, Apply, Export buttons, Inputs, status
        control_row = QHBoxLayout()
        control_row.setContentsMargins(0, 0, 0, 0)
        control_row.setSpacing(8)

        self.lbl_filter = QLabel("discharge press")
        self.lbl_filter.setStyleSheet("font-size: 10pt; color: #333;")
        control_row.addWidget(self.lbl_filter)

        from PyQt6.QtWidgets import QDoubleSpinBox, QTableWidget
        self.spn_filter = QDoubleSpinBox()
        self.spn_filter.setDecimals(2)
        self.spn_filter.setRange(-1e12, 1e12)
        self.spn_filter.setValue(55.0)
        self.spn_filter.setFixedWidth(90)
        control_row.addWidget(self.spn_filter)

        self.btn_filter = QPushButton("Apply")
        self.btn_filter.setFixedHeight(24)
        self.btn_filter.clicked.connect(self.on_apply_filter)
        control_row.addWidget(self.btn_filter)

        # Exclude hot-gas defrost periods (pressure differential collapse)
        self.chk_exclude_defrost = QCheckBox("Exclude defrost")
        self.chk_exclude_defrost.setChecked(False)
        self.chk_exclude_defrost.setToolTip(
            "Drop rows where |P_disch − P_suction| ≤ 10 psi (hot-gas defrost or "
            "off-cycle equalization) so they don't distort superheat, capacity "
            "and diagnostics averages")
        control_row.addWidget(self.chk_exclude_defrost)

        control_row.addStretch()

        # Export buttons
        self.export_button = QPushButton("Export CSV")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_to_csv)
        control_row.addWidget(self.export_button)

        self.export_mapping_button = QPushButton("Export Mapping")
        self.export_mapping_button.setToolTip("Export port mapping and required roles to CSV")
        self.export_mapping_button.clicked.connect(self.export_mapping_audit)
        control_row.addWidget(self.export_mapping_button)

        # Inputs button
        self.enter_inputs_button = QPushButton("Inputs")
        self.enter_inputs_button.clicked.connect(self.open_input_dialog)
        control_row.addWidget(self.enter_inputs_button)

        # Info button for audit mode
        self.info_btn = QPushButton("ℹ")
        self.info_btn.setFixedSize(24, 24)
        self.info_btn.setStyleSheet("""
            QPushButton {
                border: 1px solid #999;
                border-radius: 12px;
                font-size: 12pt;
                font-weight: bold;
                background-color: #f0f0f0;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
        """)
        self.info_btn.setCheckable(True)
        self.info_btn.setToolTip("Click to enable calculation audit mode")
        self.info_btn.clicked.connect(self.toggle_audit_mode)
        control_row.addWidget(self.info_btn)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: gray; font-size: 9pt; font-style: italic;")
        control_row.addWidget(self.status_label)

        layout.addLayout(control_row)

        # current discharge pressure threshold (None => no filter)
        self._dp_threshold = None

        # ==================== Tree Widget with Nested Headers ====================
        self.tree_widget = QTreeWidget()

        # Create and set custom header
        self.header = NestedHeaderView(self.tree_widget)
        self.tree_widget.setHeader(self.header)

        # Set the sub-header labels
        self.tree_widget.setHeaderLabels(self.header.sub_headers)

        # Configure tree appearance
        self.tree_widget.setAlternatingRowColors(True)
        self.tree_widget.setRootIsDecorated(False)  # No expand/collapse icons
        self.tree_widget.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_tree_context_menu)
        self.tree_widget.itemClicked.connect(self.on_tree_item_clicked)

        layout.addWidget(self.tree_widget, 1)  # Stretch factor 1

        # Note: Average row is now integrated into main tree_widget (see populate_tree method)

    def open_input_dialog(self):
        """
        Open the input dialog for entering rated performance inputs.

        This method:
        1. Creates an InputDialog instance
        2. Pre-fills it with existing rated_inputs from data_manager
        3. If user clicks OK, saves the new values
        4. Provides feedback to the user
        """
        dialog = InputDialog(self)

        # Pre-fill with existing values from data_manager
        dialog.set_data(self.data_manager.rated_inputs)

        # Show dialog and wait for user action
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # User clicked OK - get the data
            new_data = dialog.get_data()

            # Save to data_manager
            self.data_manager.rated_inputs = new_data

            # Provide feedback
            QMessageBox.information(
                self,
                "Inputs Saved",
                "Rated performance inputs have been saved successfully.\n\n"
                "You can now click 'Apply' to run calculations."
            )

            # Update status
            self.status_label.setText("✓ Rated inputs saved. Ready to run calculations.")
            self.status_label.setStyleSheet("color: green; font-size: 10pt;")

    def run_calculation(self):
        """Run the full batch calculation using the new unified engine."""

        # SOFT WARNING: Check for rated inputs
        # If missing, calculation will skip mass flow and capacity calculations
        required_fields = [
            'gpm_water',
        ]

        rated_inputs = self.data_manager.rated_inputs
        missing_fields = []

        for field in required_fields:
            value = rated_inputs.get(field)
            if value is None or value == 0.0:
                missing_fields.append(field)

        if missing_fields:
            # Show user-friendly field names
            field_labels = {
                'gpm_water': 'Water Flow Rate (GPM)',
            }

            missing_labels = [field_labels.get(f, f) for f in missing_fields]

            # SOFT WARNING - Allow user to continue
            reply = QMessageBox.question(
                self,
                "Incomplete System Parameters",
                "Some system parameters are missing:\n\n" +
                "\n".join(f"• {label}" for label in missing_labels) +
                "\n\nMass flow and cooling capacity calculations will be skipped.\n"
                "Other calculations will proceed normally.\n\n"
                "Continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.No:
                return  # User chose to stop

        def _set_status(msg, color='blue'):
            self.status_label.setText(msg)
            self.status_label.setStyleSheet(f"color: {color}; font-size: 10pt;")
            QApplication.processEvents()

        _set_status("⏳ Step 1/4: Loading data…")

        try:
            # 1. Get filtered data from data manager
            base_df = self.data_manager.get_filtered_data()

            # apply discharge pressure filter if user set threshold
            input_df = self._apply_discharge_filter(base_df)

            # optionally exclude defrost / equalization rows
            input_df = self._apply_defrost_exclusion(input_df)

            if input_df is None or input_df.empty:
                _set_status("❌ No data to process. Please load a CSV file.", 'red')
                QMessageBox.warning(self, "No Data", "Please load a CSV file first.")
                return

            print(f"[CALCULATIONS] Starting calculation on {len(input_df)} rows...")
            _set_status(f"⏳ Step 2/4: Running thermodynamic calculations ({len(input_df)} rows)…")

            # 2. Call the NEW orchestrator function (replaces coolprop_calculator.py)
            from calculation_orchestrator import run_batch_processing
            processed_df = run_batch_processing(self.data_manager, input_df)

            # 3. Check for errors
            if 'error' in processed_df.columns:
                error_msg = processed_df['error'].iloc[0] if len(processed_df) > 0 else "Unknown error"
                _set_status(f"❌ Error: {error_msg}", 'red')
                QMessageBox.critical(
                    self,
                    "Calculation Error",
                    f"An error occurred during calculation:\n\n{error_msg}\n\n"
                    "Please ensure:\n"
                    "1. Rated inputs are entered (click 'Enter Rated Inputs' button)\n"
                    "2. All required sensors are mapped in the Diagram tab"
                )
                return

            _set_status("⏳ Step 3/4: Building results table…")

            # 4. Store and display results
            # Force a stable schema: include ALL expected columns and fill missing with NaN
            # This prevents adjacent/shifted values when some sensors are unmapped
            expected_cols = list(self.header.data_keys)
            
            # Add hidden calculation columns needed for audit report (dynamic per module/system)
            from circuit_semantics import get_all_module_labels, module_abbrev as _mab
            from calculation_orchestrator import _detect_system_type as _dst
            _labels      = get_all_module_labels(self.data_manager.diagram_model) or ['Left']
            _system_type = _dst(self.data_manager.diagram_model)
            # Performance/cross-check columns (Session 11) — must survive the
            # reindex so they reach the summary, audit and diagnostics
            _perf_cols = ['m_dot_disp', 'qc_coils', 'Q_line_gain',
                          'W_comp', 'COP', 'EER', 'eta_is', 'gpm']
            if _system_type == 'cassette':
                # Cassette: per-unit h-columns are suffixed with unit abbreviation
                hidden_cols = []
                for _lbl in _labels:
                    _ab = _mab(_lbl)
                    _u  = _mab(_lbl, upper=True)
                    hidden_cols += [
                        f'h_2b-{_ab}', f'h_3a-{_ab}', f'h_4a-{_ab}',
                        f'h_4b_{_u}-{_ab}', f'h_2a_{_u}-{_ab}',
                    ]
                    hidden_cols += [f'{c}-{_ab}' for c in _perf_cols]
            else:
                # Shared: common h-columns + per-module coil enthalpies
                hidden_cols = ['h_3a', 'h_4a', 'h_2b'] + list(_perf_cols)
                for _lbl in _labels:
                    _u = _mab(_lbl, upper=True)
                    hidden_cols += [f'h_4b_{_u}', f'h_2a_{_u}']
            for col in hidden_cols:
                if col not in expected_cols and col in processed_df.columns:
                    expected_cols.append(col)
            
            # Reindex to ensure all expected columns exist (adds NaN for missing, keeps existing)
            processed_df = processed_df.reindex(columns=expected_cols)
            self.processed_df = processed_df
            self.populate_tree(processed_df)

            # 5. Enable export
            self.export_button.setEnabled(True)

            _set_status("⏳ Step 4/4: Running diagnostics…")

            # 6. Emit signal for Diagnostics tab (and P-h Diagram)
            self.filtered_data_ready.emit(processed_df)

            # 7. Update status
            _set_status(f"✓ Complete! {len(processed_df)} rows processed.", 'green')
            print(f"[CALCULATIONS] Calculation complete! {len(processed_df)} rows processed.")

        except Exception as e:
            print(f"[CALCULATIONS] ERROR during calculation: {e}")
            import traceback
            traceback.print_exc()
            _set_status(f"❌ Error: {str(e)}", 'red')
            QMessageBox.critical(self, "Calculation Error", f"An error occurred:\n\n{str(e)}")

    def on_apply_filter(self):
        """Store threshold from UI and re-run calculation."""
        try:
            self._dp_threshold = float(self.spn_filter.value())
        except Exception:
            self._dp_threshold = None
        self.run_calculation()

    def _apply_defrost_exclusion(self, df: pd.DataFrame) -> pd.DataFrame:
        """Drop rows where the discharge-suction differential has collapsed
        (≤ 10 psi) — hot-gas defrost or off-cycle equalization.  These rows
        are not steady-state refrigeration and distort every average.
        Active only when the 'Exclude defrost' checkbox is on."""
        try:
            if df is None or df.empty:
                return df
            if not getattr(self, 'chk_exclude_defrost', None) or \
                    not self.chk_exclude_defrost.isChecked():
                return df
            from port_resolver import (find_suction_pressure_sensor,
                                       find_discharge_pressure_sensor)
            sp = find_suction_pressure_sensor(self.data_manager.diagram_model)
            dp = find_discharge_pressure_sensor(self.data_manager.diagram_model)
            if not sp or not dp or sp not in df.columns or dp not in df.columns:
                print("[CALCULATIONS] defrost exclusion skipped: SP/DP not mapped")
                return df
            mask = (df[dp] - df[sp]).abs() > 10.0
            out = df[mask].copy()
            print(f"[CALCULATIONS] defrost exclusion: kept {len(out)}/{len(df)} rows "
                  f"(dropped {len(df) - len(out)} low-differential rows)")
            return out
        except Exception as e:
            print(f"[CALCULATIONS] defrost exclusion error: {e}")
            return df

    def _apply_discharge_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """Keep only rows where mapped Compressor DP >= threshold.

        If threshold is None, or mapping/column missing, return df unchanged.
        """
        try:
            if df is None or df.empty:
                return df
            if self._dp_threshold is None:
                return df
            # Find discharge pressure column (inline Sensor first, then legacy Compressor.DP)
            from port_resolver import find_discharge_pressure_sensor
            dp_col = find_discharge_pressure_sensor(self.data_manager.diagram_model)
            if not dp_col or dp_col not in df.columns:
                print(f"[CALCULATIONS] discharge press filter skipped: DP not mapped or not in DF: {dp_col}")
                return df
            thr = self._dp_threshold
            out = df[df[dp_col] >= thr].copy()
            print(f"[CALCULATIONS] discharge press filter: {dp_col} >= {thr} -> {len(out)}/{len(df)} rows")
            return out
        except Exception as e:
            print(f"[CALCULATIONS] discharge press filter error: {e}")
            return df

    def populate_tree(self, df):
        """Populate the tree widget with calculated data."""
        self.tree_widget.clear()

        # Get the data keys from the header
        data_keys = self.header.data_keys

        items = []
        for index, row in df.iterrows():
            row_data = []
            for key in data_keys:
                val = row.get(key)
                # Treat NaN/NA as missing
                try:
                    import math
                    is_missing = val is None or (isinstance(val, float) and math.isnan(val))
                except Exception:
                    # Fallback for pandas NA
                    is_missing = val is None
                if is_missing:
                    row_data.append("---")
                elif isinstance(val, (int, float)):
                    row_data.append(f"{val:.2f}")  # Format numbers
                else:
                    row_data.append(str(val))

            item = QTreeWidgetItem(row_data)
            items.append(item)

        self.tree_widget.addTopLevelItems(items)

        # Add average row at the end
        avg_row_data = []
        for key in data_keys:
            if key in df.columns:
                col_data = df[key].dropna()
                if len(col_data) > 0 and pd.api.types.is_numeric_dtype(col_data):
                    avg_val = col_data.mean()
                    avg_row_data.append(f"{avg_val:.2f}")
                else:
                    avg_row_data.append("---")
            else:
                avg_row_data.append("---")

        # Set first column to "AVERAGE" as identifier
        if len(avg_row_data) > 0:
            avg_row_data[0] = "AVERAGE"

        avg_item = QTreeWidgetItem(avg_row_data)
        # Style the average row: bold text and light blue background
        from PyQt6.QtGui import QFont, QBrush, QColor
        font = QFont()
        font.setBold(True)
        for col in range(len(data_keys)):
            avg_item.setFont(col, font)
            avg_item.setBackground(col, QBrush(QColor("#E3F2FD")))

        self.tree_widget.addTopLevelItem(avg_item)

        # Resize columns after adding data
        for i in range(len(data_keys)):
            self.tree_widget.resizeColumnToContents(i)

        print(f"[CALCULATIONS] Populated tree with {len(items)} data rows + 1 average row and {len(data_keys)} columns")


    def show_tree_context_menu(self, position):
        """Show context menu for copy operations on tree widget."""
        menu = QMenu(self)
        
        copy_action = QAction("Copy", self)
        copy_action.triggered.connect(self.copy_tree_selection)
        menu.addAction(copy_action)
        
        menu.exec(self.tree_widget.viewport().mapToGlobal(position))


    def copy_tree_selection(self):
        """Copy selected tree widget data to clipboard."""
        selected_items = self.tree_widget.selectedItems()
        if not selected_items:
            return
        
        clipboard = QApplication.clipboard()
        rows = []
        
        for item in selected_items:
            row_data = []
            for col in range(self.tree_widget.columnCount()):
                row_data.append(item.text(col))
            rows.append("\t".join(row_data))
        
        clipboard.setText("\n".join(rows))

    def export_to_csv(self):
        """Export the processed data to CSV."""
        if self.processed_df is None or self.processed_df.empty:
            QMessageBox.warning(self, "No Data", "No data to export")
            return

        from PyQt6.QtWidgets import QFileDialog

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Calculated Data",
            "calculated_results.csv",
            "CSV Files (*.csv);;All Files (*)"
        )

        if not filename:
            return  # User cancelled

        try:
            # Export only the displayed columns, in the same order, with UTF-8 BOM
            display_keys = [k for k in self.header.data_keys if k in self.processed_df.columns]
            export_df = self.processed_df[display_keys] if display_keys else self.processed_df
            export_df.to_csv(filename, index=False, encoding='utf-8-sig')
            QMessageBox.information(
                self,
                "Export Successful",
                f"Data exported successfully to:\n{filename}"
            )
            print(f"[CALCULATIONS] Exported {len(self.processed_df)} rows to {filename}")

        except Exception as e:
            print(f"[CALCULATIONS] ERROR during export: {e}")
            QMessageBox.critical(self, "Export Error", f"Failed to export:\n{str(e)}")

    def export_mapping_audit(self):
        """Export both port-level mapping and required role mapping CSVs for auditing."""
        try:
            port_path = self.data_manager.export_port_mapping_csv("port_mapping_audit.csv")
            roles_path = self.data_manager.export_required_roles_csv("required_roles_mapping.csv")
            QMessageBox.information(
                self,
                "Mapping Audit Exported",
                f"Wrote:\n- {port_path}\n- {roles_path}\n\nAttach these CSVs with corrections to remap."
            )
        except Exception as e:
            print(f"[MAPPING EXPORT] ERROR: {e}")
            QMessageBox.critical(self, "Mapping Export Error", str(e))
    
    def toggle_audit_mode(self):
        """Toggle audit mode on/off."""
        self.audit_mode = not self.audit_mode
        if self.audit_mode:
            self.info_btn.setStyleSheet("""
                QPushButton {
                    border: 1px solid #0078d4;
                    border-radius: 12px;
                    font-size: 12pt;
                    font-weight: bold;
                    background-color: #0078d4;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #005a9e;
                }
            """)
            self.status_label.setText("Audit mode ON - Click any row to see calculations")
        else:
            self.info_btn.setStyleSheet("""
                QPushButton {
                    border: 1px solid #999;
                    border-radius: 12px;
                    font-size: 12pt;
                    font-weight: bold;
                    background-color: #f0f0f0;
                }
                QPushButton:hover {
                    background-color: #e0e0e0;
                }
                QPushButton:pressed {
                    background-color: #d0d0d0;
                }
            """)
            self.status_label.setText("Ready")
    
    def on_tree_item_clicked(self, item, column):
        """Handle row click - show audit dialog if audit mode is active."""
        if not self.audit_mode:
            return

        if self.processed_df is None or self.processed_df.empty:
            QMessageBox.warning(self, "No Data", "No calculation data available for audit")
            return

        # Get row index
        row_index = self.tree_widget.indexOfTopLevelItem(item)
        if row_index < 0:
            return

        # Check if this is the average row (last row with "AVERAGE" in first column)
        if item.text(0) == "AVERAGE":
            # Compute average Series from DataFrame
            avg_data = self.processed_df.mean(numeric_only=True)
            # For non-numeric columns, use first value or empty string
            for col in self.processed_df.columns:
                if col not in avg_data:
                    avg_data[col] = self.processed_df[col].iloc[0] if len(self.processed_df) > 0 else ""

            # Generate audit text for average row
            audit_text = self.generate_audit_text("AVERAGE", avg_data)

            # Show dialog with row_data for diagrams
            dialog = CalculationAuditDialog(audit_text, "AVERAGE", avg_data, self)
            dialog.exec()
            return

        # Normal data row
        if row_index >= len(self.processed_df):
            return

        # Get the row data
        row_data = self.processed_df.iloc[row_index]

        # Generate audit text
        audit_text = self.generate_audit_text(row_index, row_data)

        # Show enhanced dialog with visuals + text
        dialog = CalculationAuditDialog(audit_text, row_index, row_data, self)
        dialog.exec()
    
    def generate_audit_text(self, row_index, row_data):
        """Generate detailed audit text for a specific row."""
        lines = []
        
        # Log all values from row_data to file for detailed debugging
        import os
        from datetime import datetime
        log_dir = "audit_logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        log_file = os.path.join(log_dir, f"audit_row_{row_index}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        with open(log_file, 'w') as f:
            f.write(f"ROW {row_index} - AUDIT GENERATION LOG\n")
            f.write("="*80 + "\n\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n\n")
            
            if hasattr(row_data, 'index'):
                all_cols = list(row_data.index)
                f.write(f"Total columns in row_data: {len(all_cols)}\n\n")
                f.write("ALL COLUMNS AND VALUES:\n")
                for col in sorted(all_cols):
                    try:
                        val = row_data.get(col) if hasattr(row_data, 'get') else row_data[col]
                        if val is None:
                            f.write(f"{col:30s} = None\n")
                        elif isinstance(val, float) and math.isnan(val):
                            f.write(f"{col:30s} = NaN\n")
                        else:
                            f.write(f"{col:30s} = {val}\n")
                    except:
                        f.write(f"{col:30s} = ERROR READING\n")
        
        # Header
        lines.append("=" * 80)
        lines.append(f"CALCULATION AUDIT - ROW {row_index}")
        lines.append("=" * 80)
        lines.append("")
        
        # SECTION 1: Add summary section showing key values from row_data
        from circuit_semantics import get_all_module_labels, module_abbrev as _mab_s1
        from calculation_orchestrator import _detect_system_type as _dst_s1
        _s1_model   = self.data_manager.diagram_model if self.data_manager else {}
        _s1_labels  = get_all_module_labels(_s1_model) or ['Left']
        _s1_stype   = _dst_s1(_s1_model)
        lines.append("SECTION 1: KEY VALUES FROM SELECTED ROW")
        lines.append("-" * 80)
        if hasattr(row_data, 'index'):
            if _s1_stype == 'cassette':
                key_cols = []
                for _lbl in _s1_labels:
                    _ab = _mab_s1(_lbl)
                    key_cols += [f'T_3a-{_ab}', f'T_4a-{_ab}', f'P_disch-{_ab}',
                                 f'P_suc-{_ab}', f'T_2b-{_ab}', f'T_waterin-{_ab}',
                                 f'T_waterout-{_ab}', f'H_comp.in-{_ab}',
                                 f'H_txv.{_ab}', f'm_dot-{_ab}', f'qc-{_ab}']
            else:
                key_cols = ['T_3a', 'T_4a', 'P_disch', 'P_suction', 'T_2b',
                            'T_waterin', 'T_waterout', 'H_comp.in', 'm_dot', 'qc']
                for _lbl in _s1_labels:
                    key_cols.append(f'H_txv.{_mab_s1(_lbl)}')
            for col in key_cols:
                try:
                    val = row_data.get(col) if hasattr(row_data, 'get') else (row_data[col] if col in row_data.index else None)
                    if val is not None and not (isinstance(val, float) and math.isnan(val)):
                        lines.append(f"  {col:20s} = {val}")
                    else:
                        lines.append(f"  {col:20s} = Missing/NaN")
                except:
                    lines.append(f"  {col:20s} = Error reading")
        lines.append("")
        lines.append(f"Detailed audit log saved to: {log_file}")
        lines.append("")
        
        # Helper function to safely get value from row_data (define early so it's available throughout)
        def get_value(col_name, default=None):
            """Get value from row_data, trying multiple methods."""
            val = None
            if hasattr(row_data, 'get'):
                val = row_data.get(col_name, default)
            if val is default and hasattr(row_data, '__getitem__'):
                try:
                    if col_name in row_data.index:
                        val = row_data[col_name]
                except (KeyError, IndexError):
                    pass
            if val is None or (isinstance(val, float) and math.isnan(val)):
                val = default
            return val
        
        # Get specs for rated inputs
        comp_specs = {}
        try:
            comp_specs = self.data_manager.rated_inputs
        except Exception as e:
            lines.append(f"Warning: Could not retrieve rated inputs: {e}")
            lines.append("")
        
        # Section 2: Rated Inputs
        lines.append("=" * 80)
        lines.append("SECTION 2: RATED INPUTS")
        lines.append("=" * 80)
        lines.append("")
        
        for key, val in comp_specs.items():
            if isinstance(val, (int, float)) and not math.isnan(val):
                lines.append(f"  {key:20s} : {val:.4f}")
            else:
                lines.append(f"  {key:20s} : Not set")
        lines.append("")
        
        # Section 3: Unit Conversions
        lines.append("=" * 80)
        lines.append("SECTION 3: UNIT CONVERSIONS")
        lines.append("=" * 80)
        lines.append("")
        
        # Determine system type + first-module abbreviation for column name lookups
        from circuit_semantics import (get_all_module_labels, module_abbrev as _mab_s3,
                                       txv_outlet_key, coil_outlet_key)
        from calculation_orchestrator import _detect_system_type as _dst_s3
        _s3_model  = self.data_manager.diagram_model if self.data_manager else {}
        _s3_labels = get_all_module_labels(_s3_model) or ['Left']
        _s3_stype  = _dst_s3(_s3_model)
        # First unit abbreviation used to build per-unit column name lookups below
        _first_ab  = _mab_s3(_s3_labels[0]) if _s3_labels else 'lh'
        _first_ab_u = _mab_s3(_s3_labels[0], upper=True) if _s3_labels else 'LH'

        # For cassette the pressure columns carry a unit suffix; for shared they do not.
        _p_suc_col   = f'P_suc-{_first_ab}'  if _s3_stype == 'cassette' else 'P_suction'
        _p_disch_col = f'P_disch-{_first_ab}' if _s3_stype == 'cassette' else 'P_disch'

        p_suc_psig = row_data.get(_p_suc_col, None)
        if p_suc_psig is not None and not math.isnan(p_suc_psig):
            p_suc_pa = (p_suc_psig + 14.7) * 6894.76
            lines.append(f"Suction Pressure:")
            lines.append(f"  Input: {p_suc_psig:.2f} PSIG")
            lines.append(f"  Formula: ({p_suc_psig:.2f} + 14.7) × 6894.76")
            lines.append(f"  Output: {p_suc_pa:.2f} Pa")
            lines.append("")

        p_disch_psig = row_data.get(_p_disch_col, None)
        if p_disch_psig is not None and not math.isnan(p_disch_psig):
            p_disch_pa = (p_disch_psig + 14.7) * 6894.76
            lines.append(f"Discharge Pressure:")
            lines.append(f"  Input: {p_disch_psig:.2f} PSIG")
            lines.append(f"  Formula: ({p_disch_psig:.2f} + 14.7) × 6894.76")
            lines.append(f"  Output: {p_disch_pa:.2f} Pa")
            lines.append("")

        # Show temperature conversions for the key sensors of the first unit/module.
        # Cassette uses per-unit suffixed names; shared uses canonical names.
        if _s3_stype == 'cassette':
            _sfx = f'-{_first_ab}'
            temp_sensors = [
                f'T_1a-{_first_ab}',
                coil_outlet_key(_s3_labels[0]),
                f'T_2b{_sfx}',
                f'T_3a{_sfx}',
                f'T_4a{_sfx}',
                f'T_4b-{_first_ab}',
            ]
        else:
            temp_sensors = [
                f'T_1a-{_first_ab}',
                coil_outlet_key(_s3_labels[0]),
                'T_2b', 'T_3a', 'T_4a',
                f'T_4b-{_first_ab}',
            ]
        for sensor_key in temp_sensors:
            val_f = row_data.get(sensor_key) if hasattr(row_data, 'get') else None
            if val_f is None and hasattr(row_data, '__getitem__'):
                try:
                    val_f = row_data[sensor_key]
                except (KeyError, IndexError):
                    pass
            if val_f is not None and isinstance(val_f, (int, float)) and not math.isnan(val_f):
                val_k = (val_f + 459.67) * 5.0 / 9.0
                lines.append(f"{sensor_key}:")
                lines.append(f"  Input: {val_f:.2f} °F")
                lines.append(f"  Formula: ({val_f:.2f} + 459.67) × 5/9")
                lines.append(f"  Output: {val_k:.2f} K")
                lines.append("")

        # Section 4: Saturation Temperatures
        lines.append("=" * 80)
        lines.append("SECTION 4: SATURATION TEMPERATURES (from CoolProp)")
        lines.append("=" * 80)
        lines.append("")

        # Suction saturation — look up from the first module's T_sat column
        _t_sat_suc_col  = (f'T_sat.{_first_ab}-{_first_ab}'
                           if _s3_stype == 'cassette'
                           else f'T_sat.{_first_ab}')
        if p_suc_psig is not None and not math.isnan(p_suc_psig):
            p_suc_pa = (p_suc_psig + 14.7) * 6894.76
            lines.append(f"Suction Saturation (dew point):")
            lines.append(f"  CoolProp: PropsSI('T', 'P', {p_suc_pa:.2f}, 'Q', 1, 'R290')")
            t_sat_suc_f = row_data.get(_t_sat_suc_col)
            if t_sat_suc_f is not None and not math.isnan(t_sat_suc_f):
                lines.append(f"  Result: {t_sat_suc_f:.2f} °F")
            lines.append("")

        # Discharge saturation
        _t_sat_cond_col = (f'T_sat.cond-{_first_ab}'
                           if _s3_stype == 'cassette'
                           else 'T_sat.cond')
        if p_disch_psig is not None and not math.isnan(p_disch_psig):
            p_disch_pa = (p_disch_psig + 14.7) * 6894.76
            lines.append(f"Discharge Saturation:")
            lines.append(f"  CoolProp: PropsSI('T', 'P', {p_disch_pa:.2f}, 'Q', 0, 'R290')")
            t_sat_disch_f = row_data.get(_t_sat_cond_col)
            if t_sat_disch_f is not None and not math.isnan(t_sat_disch_f):
                lines.append(f"  Result: {t_sat_disch_f:.2f} °F")
            lines.append("")
        
        # Section 5: Key Property Calculations
        lines.append("=" * 80)
        lines.append("SECTION 5: KEY PROPERTY CALCULATIONS")
        lines.append("=" * 80)
        lines.append("")
        lines.append("This section shows the key thermodynamic properties (enthalpy, density) at")
        lines.append("important points in the refrigeration cycle. These values are essential")
        lines.append("for calculating mass flow rate and cooling capacity.")
        lines.append("")
        
        # Build column-name helpers based on system type (already resolved above as _s3_*)
        # _s3_stype, _s3_labels, _first_ab, _p_disch_col are all available from Section 3 block.

        # Compressor Inlet (h_2b) - needed for evaporator enthalpy change
        _t_2b_col    = f'T_2b-{_first_ab}'     if _s3_stype == 'cassette' else 'T_2b'
        _hcin_col    = f'H_comp.in-{_first_ab}' if _s3_stype == 'cassette' else 'H_comp.in'
        _dcin_col    = f'D_comp.in-{_first_ab}' if _s3_stype == 'cassette' else 'D_comp.in'
        _sh_tot_col  = f'S.H_total-{_first_ab}' if _s3_stype == 'cassette' else 'S.H_total'

        t_2b = row_data.get(_t_2b_col)
        h_2b = row_data.get(_hcin_col)
        if h_2b is not None and not math.isnan(h_2b):
            lines.append("Compressor Inlet (Point 2b):")
            if t_2b is not None and not math.isnan(t_2b):
                lines.append(f"  Temperature: {t_2b:.2f} °F")
            lines.append(f"  Enthalpy (h_2b): {h_2b:.3f} kJ/kg")
            lines.append(f"    This is the refrigerant enthalpy entering the compressor.")
            lines.append(f"    It represents the energy content after leaving the evaporator.")
            d = row_data.get(_dcin_col)
            if d is not None and not math.isnan(d):
                lines.append(f"  Density: {d:.3f} kg/m³")
            sh = row_data.get(_sh_tot_col)
            if sh is not None and not math.isnan(sh):
                lines.append(f"  Total Superheat: {sh:.2f} °F")
            lines.append("")

        # Compressor Outlet / Condenser Inlet (h_3a)
        _t_3a_col = f'T_3a-{_first_ab}' if _s3_stype == 'cassette' else 'T_3a'
        _h_3a_col = f'h_3a-{_first_ab}' if _s3_stype == 'cassette' else 'h_3a'
        t_3a = row_data.get(_t_3a_col)

        h_3a = None
        for col_name in [_h_3a_col, 'H_3a', 'H_comp.out', 'h_comp.out']:
            val = row_data.get(col_name) if hasattr(row_data, 'get') else None
            if val is None and hasattr(row_data, '__getitem__'):
                try:
                    val = row_data[col_name]
                except (KeyError, IndexError):
                    continue
            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                h_3a = val / 1000 if val > 1000 else val
                break

        # Fallback: calculate from T_3a and P_disch
        if h_3a is None and t_3a is not None and not math.isnan(t_3a):
            if p_disch_psig is not None and not math.isnan(p_disch_psig):
                try:
                    from CoolProp.CoolProp import PropsSI
                    h_3a = PropsSI('H', 'T', (t_3a + 459.67) * 5.0 / 9.0,
                                   'P', (p_disch_psig + 14.7) * 6894.76, 'R290') / 1000
                except Exception:
                    pass

        if h_3a is not None and not math.isnan(h_3a):
            lines.append("Compressor Outlet / Condenser Inlet (Point 3a):")
            if t_3a is not None and not math.isnan(t_3a):
                lines.append(f"  Temperature: {t_3a:.2f} °F")
            lines.append(f"  Enthalpy (h_3a): {h_3a:.3f} kJ/kg")
            if p_disch_psig is not None:
                lines.append(f"    Calculated from: T_3a = {t_3a:.2f} °F, P_disch = {p_disch_psig:.2f} PSIG")
            lines.append(f"    This is the refrigerant enthalpy leaving the compressor.")
            lines.append(f"    It represents the energy content after compression.")
            lines.append("")

        # Condenser Outlet (h_4a)
        _t_4a_col = f'T_4a-{_first_ab}' if _s3_stype == 'cassette' else 'T_4a'
        _h_4a_col = f'h_4a-{_first_ab}' if _s3_stype == 'cassette' else 'h_4a'
        t_4a = row_data.get(_t_4a_col)

        h_4a = None
        for col_name in [_h_4a_col, 'H_4a', 'H_cond.out', 'h_cond.out']:
            val = row_data.get(col_name) if hasattr(row_data, 'get') else None
            if val is None and hasattr(row_data, '__getitem__'):
                try:
                    val = row_data[col_name]
                except (KeyError, IndexError):
                    continue
            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                h_4a = val / 1000 if val > 1000 else val
                break

        # Fallback: calculate from T_4a and P_disch
        if h_4a is None and t_4a is not None and not math.isnan(t_4a):
            if p_disch_psig is not None and not math.isnan(p_disch_psig):
                try:
                    from CoolProp.CoolProp import PropsSI
                    h_4a = PropsSI('H', 'T', (t_4a + 459.67) * 5.0 / 9.0,
                                   'P', (p_disch_psig + 14.7) * 6894.76, 'R290') / 1000
                except Exception:
                    pass

        if h_4a is not None and not math.isnan(h_4a):
            lines.append("Condenser Outlet (Point 4a):")
            if t_4a is not None and not math.isnan(t_4a):
                lines.append(f"  Temperature: {t_4a:.2f} °F")
            lines.append(f"  Enthalpy (h_4a): {h_4a:.3f} kJ/kg")
            if p_disch_psig is not None:
                lines.append(f"    Calculated from: T_4a = {t_4a:.2f} °F, P_disch = {p_disch_psig:.2f} PSIG")
            lines.append(f"    This is the refrigerant enthalpy leaving the condenser.")
            lines.append(f"    It represents the energy content after rejecting heat to water.")
            lines.append("")

        # TXV Inlets (h_4b) — dynamic: one entry per module present in diagram
        from circuit_semantics import get_all_module_labels, module_abbrev as _mab
        _audit_labels = get_all_module_labels(self.data_manager.diagram_model) or ['Left']

        def _get_h4b(lbl):
            ab   = _mab(lbl)
            ab_u = _mab(lbl, upper=True)
            # For cassette, h_4b hidden column is renamed to h_4b_{AB_U}-{ab}
            _h4b_hidden = (f'h_4b_{ab_u}-{ab}' if _s3_stype == 'cassette'
                           else f'h_4b_{ab_u}')
            # Try H_txv column first (same name for both layouts), then hidden column
            for col_name in [f'H_txv.{ab}', _h4b_hidden]:
                val = row_data.get(col_name) if hasattr(row_data, 'get') else None
                if val is None and hasattr(row_data, '__getitem__'):
                    try:
                        if col_name in row_data.index:
                            val = row_data[col_name]
                    except (KeyError, IndexError):
                        continue
                if val is not None and not (isinstance(val, float) and math.isnan(val)):
                    return val / 1000 if val > 1000 else val
            # Fallback: calculate from T_4b and the unit's discharge pressure
            _p_d_col_h4b = f'P_disch-{ab}' if _s3_stype == 'cassette' else 'P_disch'
            t_4b_f = row_data.get(f'T_4b-{ab}') if hasattr(row_data, 'get') else None
            p_d    = row_data.get(_p_d_col_h4b)  if hasattr(row_data, 'get') else None
            if t_4b_f is not None and not math.isnan(t_4b_f) and \
               p_d is not None and not math.isnan(p_d):
                try:
                    from CoolProp.CoolProp import PropsSI
                    h_jkg = PropsSI('H', 'T', (t_4b_f + 459.67) * 5/9,
                                    'P', (p_d + 14.7) * 6894.76, 'R290')
                    return h_jkg / 1000
                except Exception:
                    pass
            return None

        h_4b_by_label = {lbl: _get_h4b(lbl) for lbl in _audit_labels}

        lines.append("TXV Inlets (Point 4b - Before Expansion):")
        for lbl, h_val in h_4b_by_label.items():
            ab   = _mab(lbl)
            ab_u = _mab(lbl, upper=True)
            t_4b_f = row_data.get(f'T_4b-{ab}')
            if h_val is not None and not math.isnan(h_val):
                if t_4b_f is not None and not math.isnan(t_4b_f):
                    lines.append(f"  {ab_u} Circuit - Temperature: {t_4b_f:.2f} °F")
                lines.append(f"    Enthalpy (h_4b_{ab_u}): {h_val:.3f} kJ/kg")

        # Calculate and show average (dynamic)
        h_4b_values = [v for v in h_4b_by_label.values()
                       if v is not None and not math.isnan(v)]
        
        if h_4b_values:
            h_4b_avg = sum(h_4b_values) / len(h_4b_values)
            if len(h_4b_values) > 1:
                h_4b_list = " + ".join([f"{v:.3f}" for v in h_4b_values])
                lines.append(f"  Average Enthalpy (h_4b_avg): ({h_4b_list}) / {len(h_4b_values)} = {h_4b_avg:.3f} kJ/kg")
            else:
                lines.append(f"  Average Enthalpy (h_4b_avg): {h_4b_avg:.3f} kJ/kg")
            module_list = ", ".join(_mab(l, upper=True) for l in _audit_labels)
            lines.append(f"    This average represents the refrigerant enthalpy before expansion")
            lines.append(f"    across all circuits ({module_list}). We use the average")
            lines.append(f"    because the circuits may have slightly different conditions.")
        else:
            lines.append("  Average Enthalpy: Cannot calculate (missing TXV inlet data)")
        lines.append("")
        
        # Show evaporator enthalpy change preview
        if h_2b is not None and not math.isnan(h_2b) and h_4b_values:
            h_2b_kjkg = h_2b if h_2b < 1000 else h_2b / 1000
            delta_h_evap = h_2b_kjkg - h_4b_avg
            lines.append("Evaporator Enthalpy Change (Preview):")
            lines.append(f"  Δh_evap = h_2b - h_4b_avg")
            lines.append(f"  Δh_evap = {h_2b_kjkg:.3f} - {h_4b_avg:.3f} = {delta_h_evap:.3f} kJ/kg")
            lines.append(f"    This is the energy absorbed by the refrigerant in the evaporator.")
            lines.append(f"    It will be used to calculate cooling capacity.")
            lines.append("")
        
        # Section 6: Mass Flow & Capacity Calculations
        lines.append("=" * 80)
        lines.append("SECTION 6: MASS FLOW & CAPACITY CALCULATIONS")
        lines.append("=" * 80)
        lines.append("")
        lines.append("This section calculates the mass flow rate of refrigerant and the total")
        lines.append("cooling capacity. We use energy balance between water and refrigerant sides.")
        lines.append("")
        
        # Get all required values - READ DIRECTLY FROM row_data
        # Log all retrievals to log file
        with open(log_file, 'a') as f:
            f.write("\n" + "="*80 + "\n")
            f.write("VALUE RETRIEVAL LOG\n")
            f.write("="*80 + "\n\n")
        
        # Enhanced get_value with logging
        def get_value_logged(col_name, default=None):
            """Get value from row_data with logging."""
            val = get_value(col_name, default)
            with open(log_file, 'a') as f:
                f.write(f"  {col_name:30s} -> {val}\n")
            return val
        
        gpm_water  = comp_specs.get('gpm_water')
        # Water temp column names differ between shared and cassette
        _wtin_col  = f'T_waterin-{_first_ab}'  if _s3_stype == 'cassette' else 'T_waterin'
        _wtout_col = f'T_waterout-{_first_ab}' if _s3_stype == 'cassette' else 'T_waterout'
        t_waterin  = get_value_logged(_wtin_col)
        t_waterout = get_value_logged(_wtout_col)

        # Enthalpy lookups — use suffixed column names for cassette
        # h_3a
        h_3a = None
        _h_3a_s6_cols = ([f'h_3a-{_first_ab}'] if _s3_stype == 'cassette' else []) + \
                        ['h_3a', 'H_3a', 'H_comp.out', 'h_comp.out']
        for col_name in _h_3a_s6_cols:
            val = get_value_logged(col_name)
            if val is not None:
                h_3a = val / 1000 if val > 1000 else val
                with open(log_file, 'a') as f:
                    f.write(f"  h_3a FOUND in column '{col_name}' = {h_3a:.3f} kJ/kg\n")
                break

        if h_3a is None:
            t_3a_f      = get_value_logged(_t_3a_col)
            p_disch_psig_s6 = get_value_logged(_p_disch_col)
            if t_3a_f is not None and p_disch_psig_s6 is not None:
                try:
                    from CoolProp.CoolProp import PropsSI
                    h_3a = PropsSI('H', 'T', (t_3a_f + 459.67) * 5.0 / 9.0,
                                   'P', (p_disch_psig_s6 + 14.7) * 6894.76, 'R290') / 1000
                    with open(log_file, 'a') as f:
                        f.write(f"  h_3a CALCULATED from T_3a={t_3a_f:.2f}°F, P_disch={p_disch_psig_s6:.2f} PSIG = {h_3a:.3f} kJ/kg\n")
                except Exception as e:
                    with open(log_file, 'a') as f:
                        f.write(f"  h_3a CALCULATION FAILED: {e}\n")

        # h_4a
        h_4a = None
        _h_4a_s6_cols = ([f'h_4a-{_first_ab}'] if _s3_stype == 'cassette' else []) + \
                        ['h_4a', 'H_4a', 'H_cond.out', 'h_cond.out']
        for col_name in _h_4a_s6_cols:
            val = get_value_logged(col_name)
            if val is not None:
                h_4a = val / 1000 if val > 1000 else val
                with open(log_file, 'a') as f:
                    f.write(f"  h_4a FOUND in column '{col_name}' = {h_4a:.3f} kJ/kg\n")
                break

        if h_4a is None:
            t_4a_f      = get_value_logged(_t_4a_col)
            p_disch_psig_s6 = get_value_logged(_p_disch_col)
            if t_4a_f is not None and p_disch_psig_s6 is not None:
                try:
                    from CoolProp.CoolProp import PropsSI
                    h_4a = PropsSI('H', 'T', (t_4a_f + 459.67) * 5.0 / 9.0,
                                   'P', (p_disch_psig_s6 + 14.7) * 6894.76, 'R290') / 1000
                    with open(log_file, 'a') as f:
                        f.write(f"  h_4a CALCULATED from T_4a={t_4a_f:.2f}°F, P_disch={p_disch_psig_s6:.2f} PSIG = {h_4a:.3f} kJ/kg\n")
                except Exception as e:
                    with open(log_file, 'a') as f:
                        f.write(f"  h_4a CALCULATION FAILED: {e}\n")

        # h_2b (compressor inlet enthalpy)
        h_2b = None
        _h_2b_s6_cols = ([f'h_2b-{_first_ab}', f'H_comp.in-{_first_ab}']
                         if _s3_stype == 'cassette' else []) + \
                        ['H_comp.in', 'h_2b', 'H_2b', 'h_comp.in']
        for col_name in _h_2b_s6_cols:
            val = get_value_logged(col_name)
            if val is not None:
                h_2b = val / 1000 if val > 1000 else val
                with open(log_file, 'a') as f:
                    f.write(f"  h_2b FOUND in column '{col_name}' = {h_2b:.3f} kJ/kg\n")
                break

        if h_2b is None:
            t_2b_f     = get_value_logged(_t_2b_col)
            p_suc_psig_s6 = get_value_logged(_p_suc_col)
            if t_2b_f is not None and p_suc_psig_s6 is not None:
                try:
                    from CoolProp.CoolProp import PropsSI
                    h_2b = PropsSI('H', 'T', (t_2b_f + 459.67) * 5.0 / 9.0,
                                   'P', (p_suc_psig_s6 + 14.7) * 6894.76, 'R290') / 1000
                    with open(log_file, 'a') as f:
                        f.write(f"  h_2b CALCULATED from T_2b={t_2b_f:.2f}°F, P_suction={p_suc_psig_s6:.2f} PSIG = {h_2b:.3f} kJ/kg\n")
                except Exception as e:
                    with open(log_file, 'a') as f:
                        f.write(f"  h_2b CALCULATION FAILED: {e}\n")
        
        # Note: h_4b_by_label and _audit_labels were built in Section 5 above
        # and are available as local variables for use in Section 6
        
        # Step 1: Water Flow Input
        if not gpm_water or math.isnan(gpm_water):
            lines.append("Step 1 - Water Flow Input:")
            lines.append("  gpm_water = Not set in rated inputs")
            lines.append("  ERROR: Cannot proceed without water flow rate")
            lines.append("")
        else:
            lines.append("Step 1 - Water Flow Input:")
            lines.append(f"  gpm_water = {gpm_water:.4f} GPM")
            lines.append("    This is the water flow rate through the condenser.")
            lines.append("    It tells us how much water is flowing per minute.")
            lines.append("")
        
        # Step 2: Water Temperature Change
        if t_waterin is not None and t_waterout is not None and not math.isnan(t_waterin) and not math.isnan(t_waterout):
            delta_t_water = t_waterout - t_waterin
            lines.append("Step 2 - Water Temperature Change:")
            lines.append(f"  T_water_out = {t_waterout:.2f} °F")
            lines.append(f"  T_water_in  = {t_waterin:.2f} °F")
            lines.append(f"  ΔT_water = T_water_out - T_water_in")
            lines.append(f"  ΔT_water = {t_waterout:.2f} - {t_waterin:.2f} = {delta_t_water:.2f} °F")
            lines.append("    This is how much the water temperature increased.")
            lines.append("    The water got hotter because it absorbed heat from the refrigerant.")
            lines.append("")
        else:
            lines.append("Step 2 - Water Temperature Change:")
            lines.append("  ERROR: Missing water temperature data")
            lines.append("")
        
        # Step 3: Water-Side Heat Rejection (with educational breakdown)
        if gpm_water and t_waterin is not None and t_waterout is not None:
            delta_t_water = t_waterout - t_waterin
            lines.append("Step 3 - Water-Side Heat Rejection (Q_water):")
            lines.append("    The water absorbs heat from the refrigerant in the condenser.")
            lines.append("    We calculate this using the water properties:")
            lines.append("")
            lines.append("    Q_water = density_water × gpm_water × cp_water × ΔT_water")
            lines.append("")
            lines.append("    Where:")
            lines.append("      density_water = 8.34 lb/gal (weight of water per gallon)")
            lines.append("      cp_water = 1.0 BTU/(lb·°F) (heat capacity of water)")
            lines.append("      Conversion factor = 60 min/hr (convert GPM to gallons/hour)")
            lines.append("")
            lines.append("    Combining these:")
            lines.append("      density_water × cp_water × 60 = 8.34 × 1.0 × 60 = 500.4")
            lines.append("")
            lines.append("    So the formula simplifies to:")
            lines.append("      Q_water = 500.4 × gpm_water × ΔT_water")
            lines.append("")
            q_water = 500.4 * gpm_water * delta_t_water
            lines.append(f"    Q_water = 500.4 × {gpm_water:.4f} × {delta_t_water:.2f}")
            lines.append(f"    Q_water = {q_water:.2f} BTU/hr")
            lines.append("")
            lines.append("    This is the total heat rejected by the refrigerant to the water.")
            lines.append("    By conservation of energy, this equals the heat rejected by refrigerant.")
            lines.append("")
        
        # Step 4: Condenser Enthalpy Change (Refrigerant Side)
        # Show step 4 even if values are missing, but indicate the issue
        if h_3a is None or h_4a is None:
            lines.append("Step 4 - Condenser Enthalpy Change (Refrigerant Side):")
            lines.append("  ERROR: Missing enthalpy data")
            if h_3a is None:
                lines.append("    h_3a (Compressor Outlet) not found in calculation results")
            if h_4a is None:
                lines.append("    h_4a (Condenser Outlet) not found in calculation results")
            lines.append("    Cannot calculate mass flow rate without these values.")
            lines.append("")
        elif h_3a is not None and h_4a is not None and not math.isnan(h_3a) and not math.isnan(h_4a):
            lines.append("Step 4 - Condenser Enthalpy Change (Refrigerant Side):")
            lines.append("    The refrigerant loses energy (enthalpy) as it flows through the condenser.")
            lines.append("    This energy is transferred to the water.")
            lines.append("")
            
            # Convert kJ/kg to BTU/lb
            h_3a_jkg = h_3a * 1000  # Convert kJ/kg to J/kg
            h_4a_jkg = h_4a * 1000
            h_3a_btulb = h_3a_jkg * 0.0004299  # Convert J/kg to BTU/lb
            h_4a_btulb = h_4a_jkg * 0.0004299
            delta_h_ref_cond_btulb = h_3a_btulb - h_4a_btulb
            
            lines.append(f"    h_3a (Compressor Outlet) = {h_3a:.3f} kJ/kg")
            lines.append(f"      = {h_3a_jkg:.1f} J/kg")
            lines.append(f"      = {h_3a_btulb:.3f} BTU/lb")
            lines.append("")
            lines.append(f"    h_4a (Condenser Outlet) = {h_4a:.3f} kJ/kg")
            lines.append(f"      = {h_4a_jkg:.1f} J/kg")
            lines.append(f"      = {h_4a_btulb:.3f} BTU/lb")
            lines.append("")
            lines.append(f"    Δh_ref_cond = h_3a - h_4a")
            lines.append(f"    Δh_ref_cond = {h_3a_btulb:.3f} - {h_4a_btulb:.3f}")
            lines.append(f"    Δh_ref_cond = {delta_h_ref_cond_btulb:.3f} BTU/lb")
            lines.append("")
            lines.append("    This is how much enthalpy (energy per pound) the refrigerant lost")
            lines.append("    in the condenser. This energy was transferred to the water.")
            lines.append("")
        
        # Step 5: Mass Flow Rate of Refrigerant (User's Formula)
        # Show step 5 even if values are missing, but indicate the issue
        if not (gpm_water and t_waterin is not None and t_waterout is not None):
            lines.append("Step 5 - Mass Flow Rate of Refrigerant:")
            lines.append("  ERROR: Missing water flow or temperature data")
            lines.append("    Cannot calculate mass flow rate.")
            lines.append("")
        elif h_3a is None or h_4a is None or math.isnan(h_3a) or math.isnan(h_4a):
            lines.append("Step 5 - Mass Flow Rate of Refrigerant:")
            lines.append("  ERROR: Missing condenser enthalpy data (h_3a or h_4a)")
            lines.append("    Cannot calculate mass flow rate without these values.")
            lines.append("")
        elif (gpm_water and t_waterin is not None and t_waterout is not None and 
            h_3a is not None and h_4a is not None and not math.isnan(h_3a) and not math.isnan(h_4a)):
            delta_t_water = t_waterout - t_waterin
            q_water = 500.4 * gpm_water * delta_t_water
            h_3a_jkg = h_3a * 1000
            h_4a_jkg = h_4a * 1000
            h_3a_btulb = h_3a_jkg * 0.0004299
            h_4a_btulb = h_4a_jkg * 0.0004299
            delta_h_ref_cond_btulb = h_3a_btulb - h_4a_btulb
            
            if delta_h_ref_cond_btulb > 0:
                lines.append("Step 5 - Mass Flow Rate of Refrigerant:")
                lines.append("")
                lines.append("    Formula (as specified):")
                lines.append("      massflow_ref = (m × cp × dt) / delta_h_ref")
                lines.append("")
                lines.append("    Where:")
                lines.append("      m = mass flow rate of water (lb/hr)")
                lines.append("      cp = specific heat of water (BTU/(lb·°F))")
                lines.append("      dt = water temperature change (°F)")
                lines.append("      delta_h_ref = enthalpy change of refrigerant in condenser (BTU/lb)")
                lines.append("")
                
                # Calculate mass flow rate of water
                # density_water = 8.34 lb/gal
                # gpm_water is in gallons per minute
                # Convert to lb/hr: 8.34 lb/gal × gpm gal/min × 60 min/hr
                mass_flow_water_lbhr = 8.34 * gpm_water * 60
                cp_water_value = 1.0
                
                lines.append("    First, calculate mass flow rate of water (m):")
                lines.append("      m = density_water × gpm_water × 60 min/hr")
                lines.append(f"      m = 8.34 lb/gal × {gpm_water:.4f} gal/min × 60 min/hr")
                lines.append(f"      m = {mass_flow_water_lbhr:.2f} lb/hr")
                lines.append("")
                
                lines.append("    Now calculate the formula:")
                lines.append("      massflow_ref = (m × cp × dt) / delta_h_ref")
                lines.append("")
                lines.append("    Where:")
                lines.append(f"      m = {mass_flow_water_lbhr:.2f} lb/hr")
                lines.append(f"      cp = {cp_water_value:.1f} BTU/(lb·°F)")
                lines.append(f"      dt = ΔT_water = {delta_t_water:.2f} °F")
                lines.append(f"      delta_h_ref = Δh_ref_cond = {delta_h_ref_cond_btulb:.3f} BTU/lb")
                lines.append("")
                
                # Calculate using the formula
                numerator = mass_flow_water_lbhr * cp_water_value * delta_t_water
                massflow_ref = numerator / delta_h_ref_cond_btulb
                
                lines.append(f"    Calculation:")
                lines.append(f"      massflow_ref = ({mass_flow_water_lbhr:.2f} × {cp_water_value:.1f} × {delta_t_water:.2f}) / {delta_h_ref_cond_btulb:.3f}")
                lines.append(f"      massflow_ref = {numerator:.2f} / {delta_h_ref_cond_btulb:.3f}")
                lines.append(f"      massflow_ref = {massflow_ref:.2f} lb/hr")
                lines.append("")
                lines.append("    Note: This is equivalent to Q_water / delta_h_ref_cond,")
                lines.append("          since Q_water = m × cp × dt")
                lines.append("")
                lines.append("    This is the mass flow rate of refrigerant through the system.")
                lines.append("    It tells us how many pounds of refrigerant flow per hour.")
                lines.append("")
                
                # Step 6: Evaporator Enthalpy Change (with averaging)
                if h_2b is not None and not math.isnan(h_2b):
                    h_4b_values = [v for v in h_4b_by_label.values()
                                   if v is not None and not math.isnan(v)]
                    
                    if h_4b_values:
                        lines.append("Step 6 - Evaporator Enthalpy Change:")
                        lines.append("    The refrigerant gains energy (enthalpy) in the evaporator.")
                        lines.append("    This energy comes from the air being cooled.")
                        lines.append("")
                        
                        # Convert h_2b to kJ/kg if needed
                        h_2b_kjkg = h_2b if h_2b < 1000 else h_2b / 1000
                        
                        lines.append(f"    h_2b (Compressor Inlet / Evap Outlet) = {h_2b_kjkg:.3f} kJ/kg")
                        h_2b_jkg = h_2b_kjkg * 1000
                        h_2b_btulb = h_2b_jkg * 0.0004299
                        lines.append(f"      = {h_2b_btulb:.3f} BTU/lb")
                        lines.append("")
                        
                        lines.append("    h_4b (TXV Inlets - Before Expansion):")
                        h_4b_list = []
                        h_4b_btulb_list = []
                        # Build ordered (label, value) pairs from h_4b_by_label so names match
                        _h4b_labeled = [
                            (_mab(lbl, upper=True), v)
                            for lbl, v in h_4b_by_label.items()
                            if v is not None and not math.isnan(v)
                        ]
                        for circuit_name, h_val in _h4b_labeled:
                            h_val_jkg = h_val * 1000
                            h_val_btulb = h_val_jkg * 0.0004299
                            h_4b_list.append(f"{h_val:.3f}")
                            h_4b_btulb_list.append(h_val_btulb)
                            lines.append(f"      h_4b_{circuit_name} = {h_val:.3f} kJ/kg = {h_val_btulb:.3f} BTU/lb")

                        # Calculate average
                        h_4b_avg = sum(h_4b_values) / len(h_4b_values)
                        h_4b_avg_jkg = h_4b_avg * 1000
                        h_4b_avg_btulb = h_4b_avg_jkg * 0.0004299

                        lines.append("")
                        if len(h_4b_values) > 1:
                            h_4b_labels_str = " + ".join(f"h_4b_{n}" for n, _ in _h4b_labeled)
                            h_4b_sum_str    = " + ".join([f"{v:.3f}" for v in h_4b_values])
                            lines.append(f"    h_4b_avg = ({h_4b_labels_str}) / {len(h_4b_values)}")
                            lines.append(f"    h_4b_avg = ({h_4b_sum_str}) / {len(h_4b_values)}")
                            lines.append(f"    h_4b_avg = {h_4b_avg:.3f} kJ/kg = {h_4b_avg_btulb:.3f} BTU/lb")
                            lines.append("")
                            _circuit_names_str = ", ".join(n for n, _ in _h4b_labeled)
                            lines.append(f"    Note: We average the circuits ({_circuit_names_str}) because")
                            lines.append("          they may have slightly different conditions.")
                        else:
                            lines.append(f"    h_4b_avg = {h_4b_avg:.3f} kJ/kg = {h_4b_avg_btulb:.3f} BTU/lb")
                            lines.append("    (Only one circuit available)")
                            lines.append("")
                        
                        delta_h_evap_btulb = h_2b_btulb - h_4b_avg_btulb
                        lines.append(f"    Δh_evap = h_2b - h_4b_avg")
                        lines.append(f"    Δh_evap = {h_2b_btulb:.3f} - {h_4b_avg_btulb:.3f}")
                        lines.append(f"    Δh_evap = {delta_h_evap_btulb:.3f} BTU/lb")
                        lines.append("")
                        lines.append("    This is how much enthalpy (energy per pound) the refrigerant")
                        lines.append("    gained in the evaporator. This energy came from the air.")
                        lines.append("")
                        
                        # Step 7: Cooling Capacity
                        lines.append("Step 7 - Total Cooling Capacity (Q_c):")
                        lines.append("")
                        lines.append("    Formula:")
                        lines.append("      Q_c = massflow_ref × delta_h_evap")
                        lines.append("")
                        lines.append("    This tells us the total cooling capacity: how much heat")
                        lines.append("    the system removes from the air per hour.")
                        lines.append("")
                        
                        q_c = massflow_ref * delta_h_evap_btulb
                        lines.append(f"    Calculation:")
                        lines.append(f"      Q_c = {massflow_ref:.2f} lb/hr × {delta_h_evap_btulb:.3f} BTU/lb")
                        lines.append(f"      Q_c = {q_c:.2f} BTU/hr")
                        lines.append("")
                        
                        # Summary: Show final values from table
                        m_dot_table = row_data.get('m_dot')
                        qc_table = row_data.get('qc')
                        
                        lines.append("=" * 80)
                        lines.append("FINAL VALUES (as displayed in calculation table):")
                        lines.append("=" * 80)
                        lines.append("")
                        if m_dot_table is not None and not math.isnan(m_dot_table):
                            lines.append(f"  m_dot (Mass Flow Rate) = {m_dot_table:.2f} lb/hr")
                            if abs(m_dot_table - massflow_ref) < 0.01:
                                lines.append("    ✓ Matches calculated value")
                            else:
                                lines.append(f"    Calculated value: {massflow_ref:.2f} lb/hr")
                        else:
                            lines.append("  m_dot = Not calculated")
                        
                        if qc_table is not None and not math.isnan(qc_table):
                            lines.append(f"  qc (Cooling Capacity) = {qc_table:.2f} BTU/hr")
                            if abs(qc_table - q_c) < 0.01:
                                lines.append("    ✓ Matches calculated value")
                            else:
                                lines.append(f"    Calculated value: {q_c:.2f} BTU/hr")
                        else:
                            lines.append("  qc = Not calculated")
                        lines.append("")
        
        # Helper function for sign-aware formatting
        def format_sign_aware(value, unit="°F", decimal_places=1):
            """Format a value with sign and directional arrow."""
            if value is None or (isinstance(value, float) and math.isnan(value)):
                return "N/A"

            sign_str = "+" if value >= 0 else ""
            arrow = "↑" if value > 0 else ("↓" if value < 0 else "→")
            formatted_val = f"{sign_str}{value:.{decimal_places}f}{unit}"
            return f"{formatted_val} {arrow}"

        # Section 7: Per-Circuit Superheat/Subcool Analysis
        lines.append("=" * 80)
        lines.append("SECTION 7: PER-CIRCUIT SUPERHEAT/SUBCOOL ANALYSIS")
        lines.append("=" * 80)
        lines.append("")
        lines.append("This section shows superheat and subcool values for each circuit.")
        lines.append("Positive superheat indicates proper evaporation (good).")
        lines.append("Negative subcool may indicate refrigerant charge issues (concern).")
        lines.append("")

        # Get superheat values
        sh_lh = get_value('S.H_lh coil')
        sh_ctr = get_value('S.H_ctr coil')
        sh_rh = get_value('S.H_rh coil')
        sh_total = get_value('S.H_total')

        # Get subcool values
        sc_main = get_value('S.C')
        sc_lh = get_value('S.C-txv.lh')
        sc_ctr = get_value('S.C-txv.ctr')
        sc_rh = get_value('S.C-txv.rh')

        lines.append("EVAPORATOR SUPERHEAT (by circuit):")
        lines.append("-" * 40)
        if sh_lh is not None and not math.isnan(sh_lh):
            lines.append(f"  LH Circuit:    {format_sign_aware(sh_lh, '°F', 1)}")
        else:
            lines.append("  LH Circuit:    N/A")

        if sh_ctr is not None and not math.isnan(sh_ctr):
            lines.append(f"  CTR Circuit:   {format_sign_aware(sh_ctr, '°F', 1)}")
        else:
            lines.append("  CTR Circuit:   N/A")

        if sh_rh is not None and not math.isnan(sh_rh):
            lines.append(f"  RH Circuit:    {format_sign_aware(sh_rh, '°F', 1)}")
        else:
            lines.append("  RH Circuit:    N/A")

        if sh_total is not None and not math.isnan(sh_total):
            lines.append(f"  Total System:  {format_sign_aware(sh_total, '°F', 1)}")
        else:
            lines.append("  Total System:  N/A")
        lines.append("")

        lines.append("CONDENSER SUBCOOL:")
        lines.append("-" * 40)
        if sc_main is not None and not math.isnan(sc_main):
            lines.append(f"  Main Condenser:  {format_sign_aware(sc_main, '°F', 1)}")
            if sc_main < 0:
                lines.append("    WARNING: Negative subcool indicates potential issue!")
        else:
            lines.append("  Main Condenser:  N/A")
        lines.append("")

        lines.append("TXV INLET SUBCOOL (by circuit):")
        lines.append("-" * 40)
        if sc_lh is not None and not math.isnan(sc_lh):
            lines.append(f"  LH Circuit:    {format_sign_aware(sc_lh, '°F', 1)}")
            if sc_lh < 0:
                lines.append("    WARNING: Negative subcool - check charge/TXV!")
        else:
            lines.append("  LH Circuit:    N/A")

        if sc_ctr is not None and not math.isnan(sc_ctr):
            lines.append(f"  CTR Circuit:   {format_sign_aware(sc_ctr, '°F', 1)}")
            if sc_ctr < 0:
                lines.append("    WARNING: Negative subcool - check charge/TXV!")
        else:
            lines.append("  CTR Circuit:   N/A")

        if sc_rh is not None and not math.isnan(sc_rh):
            lines.append(f"  RH Circuit:    {format_sign_aware(sc_rh, '°F', 1)}")
            if sc_rh < 0:
                lines.append("    WARNING: Negative subcool - check charge/TXV!")
        else:
            lines.append("  RH Circuit:    N/A")
        lines.append("")

        # Section 8: ASCII P-h Diagram Snapshot
        lines.append("=" * 80)
        lines.append("SECTION 8: P-h DIAGRAM SNAPSHOT")
        lines.append("=" * 80)
        lines.append("")
        lines.append("Pressure-Enthalpy diagram state points for the refrigeration cycle:")
        lines.append("")

        # Get pressure values
        p_suction = get_value('P_suction')
        p_disch = get_value('P_disch')

        # Get enthalpy values (already have some from earlier)
        h_1_lh = get_value('H_coil lh')
        h_1_ctr = get_value('H_coil ctr')
        h_1_rh = get_value('H_coil rh')
        h_2 = get_value('H_comp.in')
        h_3 = h_3a if h_3a is not None else get_value('H_comp.out')

        # Convert enthalpies to kJ/kg if needed
        def convert_h(h_val):
            if h_val is None or (isinstance(h_val, float) and math.isnan(h_val)):
                return None
            return h_val if h_val < 1000 else h_val / 1000

        h_1_lh = convert_h(h_1_lh)
        h_1_ctr = convert_h(h_1_ctr)
        h_1_rh = convert_h(h_1_rh)
        h_2 = convert_h(h_2)
        h_3 = convert_h(h_3)
        h_4 = h_4a if h_4a is not None else get_value('H_cond.out')
        h_4 = convert_h(h_4)

        # Convert pressures to absolute (PSIA)
        def to_psia(psig_val):
            if psig_val is None or (isinstance(psig_val, float) and math.isnan(psig_val)):
                return None
            return psig_val + 14.7

        p_suc_psia = to_psia(p_suction)
        p_dis_psia = to_psia(p_disch)

        lines.append("────────────────────────────────────────────────────────────────────────────────")
        lines.append("Point  Description              Pressure (PSIA)    Enthalpy (kJ/kg)")
        lines.append("────────────────────────────────────────────────────────────────────────────────")

        # Point 1 - Evaporator Outlets (show average or individual)
        h_1_avg = None
        h_1_vals = [h for h in [h_1_lh, h_1_ctr, h_1_rh] if h is not None and not math.isnan(h)]
        if h_1_vals:
            h_1_avg = sum(h_1_vals) / len(h_1_vals)

        if p_suc_psia is not None and h_1_avg is not None:
            lines.append(f"  1    Evap Outlet (avg)       {p_suc_psia:8.1f}           {h_1_avg:8.2f}")
        else:
            p_str = f"{p_suc_psia:8.1f}" if p_suc_psia is not None else "    N/A "
            h_str = f"{h_1_avg:8.2f}" if h_1_avg is not None else "    N/A "
            lines.append(f"  1    Evap Outlet (avg)       {p_str}           {h_str}")

        # Point 2 - Compressor Inlet
        if p_suc_psia is not None and h_2 is not None:
            lines.append(f"  2    Comp Inlet              {p_suc_psia:8.1f}           {h_2:8.2f}")
        else:
            p_str = f"{p_suc_psia:8.1f}" if p_suc_psia is not None else "    N/A "
            h_str = f"{h_2:8.2f}" if h_2 is not None else "    N/A "
            lines.append(f"  2    Comp Inlet              {p_str}           {h_str}")

        # Point 3 - Compressor Outlet / Condenser Inlet
        if p_dis_psia is not None and h_3 is not None:
            lines.append(f"  3    Comp Outlet / Cond In   {p_dis_psia:8.1f}           {h_3:8.2f}")
        else:
            p_str = f"{p_dis_psia:8.1f}" if p_dis_psia is not None else "    N/A "
            h_str = f"{h_3:8.2f}" if h_3 is not None else "    N/A "
            lines.append(f"  3    Comp Outlet / Cond In   {p_str}           {h_str}")

        # Point 4 - Condenser Outlet / TXV Inlet
        if p_dis_psia is not None and h_4 is not None:
            lines.append(f"  4    Cond Outlet / TXV In    {p_dis_psia:8.1f}           {h_4:8.2f}")
        else:
            p_str = f"{p_dis_psia:8.1f}" if p_dis_psia is not None else "    N/A "
            h_str = f"{h_4:8.2f}" if h_4 is not None else "    N/A "
            lines.append(f"  4    Cond Outlet / TXV In    {p_str}           {h_str}")

        lines.append("────────────────────────────────────────────────────────────────────────────────")
        lines.append("")

        lines.append("Circuit Superheat/Subcool Summary:")
        sh_vals = []
        if sh_lh is not None and not math.isnan(sh_lh):
            sh_vals.append(f"LH: {format_sign_aware(sh_lh, '°F', 1)}")
        if sh_ctr is not None and not math.isnan(sh_ctr):
            sh_vals.append(f"CTR: {format_sign_aware(sh_ctr, '°F', 1)}")
        if sh_rh is not None and not math.isnan(sh_rh):
            sh_vals.append(f"RH: {format_sign_aware(sh_rh, '°F', 1)}")

        if sh_vals:
            lines.append("  Superheat:  " + "  |  ".join(sh_vals))
        else:
            lines.append("  Superheat:  N/A")

        sc_vals = []
        if sc_lh is not None and not math.isnan(sc_lh):
            sc_vals.append(f"LH: {format_sign_aware(sc_lh, '°F', 1)}")
        if sc_ctr is not None and not math.isnan(sc_ctr):
            sc_vals.append(f"CTR: {format_sign_aware(sc_ctr, '°F', 1)}")
        if sc_rh is not None and not math.isnan(sc_rh):
            sc_vals.append(f"RH: {format_sign_aware(sc_rh, '°F', 1)}")

        if sc_vals:
            lines.append("  Subcool:    " + "  |  ".join(sc_vals))
        else:
            lines.append("  Subcool:    N/A")
        lines.append("")

        # Section 9: ASCII Process Flow
        lines.append("=" * 80)
        lines.append("SECTION 9: PROCESS FLOW DIAGRAM")
        lines.append("=" * 80)
        lines.append("")
        lines.append("Component flow and operating conditions:")
        lines.append("")
        lines.append("  COMPRESSOR → CONDENSER → TXV → EVAPORATOR → [back to COMPRESSOR]")
        lines.append("")
        lines.append("────────────────────────────────────────────────────────────────────────────────")

        # Get temperatures
        t_comp_in = get_value('T_2b')
        t_comp_out = get_value('T_3a')
        t_cond_out = get_value('T_4a')
        t_txv_lh = get_value('T_4b-lh')
        t_txv_ctr = get_value('T_4b-ctr')
        t_txv_rh = get_value('T_4b-rh')
        t_evap_lh = get_value('T_2a-LH')
        t_evap_ctr = get_value('T_2a-ctr')
        t_evap_rh = get_value('T_2a-RH')

        # Temperature flow
        lines.append("TEMPERATURES (°F):")
        t_comp_in_str = f"{t_comp_in:5.1f}" if (t_comp_in is not None and not math.isnan(t_comp_in)) else "  N/A"
        t_comp_out_str = f"{t_comp_out:5.1f}" if (t_comp_out is not None and not math.isnan(t_comp_out)) else "  N/A"
        t_cond_out_str = f"{t_cond_out:5.1f}" if (t_cond_out is not None and not math.isnan(t_cond_out)) else "  N/A"

        lines.append(f"  Comp In: {t_comp_in_str} → Comp Out: {t_comp_out_str} → Cond Out: {t_cond_out_str}")

        # TXV temps (per circuit)
        lines.append("  TXV Inlets:")
        if t_txv_lh is not None and not math.isnan(t_txv_lh):
            lines.append(f"    LH:  {t_txv_lh:5.1f}°F")
        if t_txv_ctr is not None and not math.isnan(t_txv_ctr):
            lines.append(f"    CTR: {t_txv_ctr:5.1f}°F")
        if t_txv_rh is not None and not math.isnan(t_txv_rh):
            lines.append(f"    RH:  {t_txv_rh:5.1f}°F")

        # Evaporator outlets (per circuit)
        lines.append("  Evap Outlets:")
        if t_evap_lh is not None and not math.isnan(t_evap_lh):
            lines.append(f"    LH:  {t_evap_lh:5.1f}°F")
        if t_evap_ctr is not None and not math.isnan(t_evap_ctr):
            lines.append(f"    CTR: {t_evap_ctr:5.1f}°F")
        if t_evap_rh is not None and not math.isnan(t_evap_rh):
            lines.append(f"    RH:  {t_evap_rh:5.1f}°F")
        lines.append("")

        # Pressure flow
        lines.append("PRESSURES (PSIG):")
        p_suc_str = f"{p_suction:6.1f}" if (p_suction is not None and not math.isnan(p_suction)) else "   N/A"
        p_dis_str = f"{p_disch:6.1f}" if (p_disch is not None and not math.isnan(p_disch)) else "   N/A"
        lines.append(f"  Suction: {p_suc_str} → Discharge: {p_dis_str}")
        lines.append("")

        # Diagnostic summary
        lines.append("DIAGNOSTIC SUMMARY:")
        lines.append("-" * 40)

        # Subcool assessment
        if sc_main is not None and not math.isnan(sc_main):
            if sc_main < 0:
                lines.append(f"  Subcool:    {format_sign_aware(sc_main, '°F', 1)}  (ISSUE - LOW CHARGE!)")
            elif sc_main < 5:
                lines.append(f"  Subcool:    {format_sign_aware(sc_main, '°F', 1)}  (LOW - check charge)")
            elif sc_main > 20:
                lines.append(f"  Subcool:    {format_sign_aware(sc_main, '°F', 1)}  (HIGH - possible overcharge)")
            else:
                lines.append(f"  Subcool:    {format_sign_aware(sc_main, '°F', 1)}  (OK)")
        else:
            lines.append("  Subcool:    N/A")

        # Superheat assessment
        if sh_total is not None and not math.isnan(sh_total):
            if sh_total < 0:
                lines.append(f"  Superheat:  {format_sign_aware(sh_total, '°F', 1)}  (CRITICAL - LIQUID TO COMP!)")
            elif sh_total < 5:
                lines.append(f"  Superheat:  {format_sign_aware(sh_total, '°F', 1)}  (LOW - risk of flooding)")
            elif sh_total > 25:
                lines.append(f"  Superheat:  {format_sign_aware(sh_total, '°F', 1)}  (HIGH - low capacity)")
            else:
                lines.append(f"  Superheat:  {format_sign_aware(sh_total, '°F', 1)}  (OK)")
        else:
            lines.append("  Superheat:  N/A")
        lines.append("")

        # Note about future image support
        lines.append("Note: Future versions may include graphical P-h diagrams and process flow")
        lines.append("      visualizations using base64-encoded images.")
        lines.append("")

        # Footer
        lines.append("=" * 80)
        lines.append("END OF CALCULATION AUDIT")
        lines.append("=" * 80)

        return "\n".join(lines)
