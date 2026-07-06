"""
P-h Diagram Widget

Displays interactive P-h diagrams with circuit-specific overlays and toggles.
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QCheckBox, QComboBox, QGroupBox, QFormLayout,
                             QMessageBox, QSpinBox, QFileDialog)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import pandas as pd
import pyqtgraph as pg
from ph_diagram_plotter import PhDiagramPlotter
from ph_diagram_generator import PhDiagramGenerator


class CycleDomeWidget(QWidget):
    """Compact single-axis P-h cycle view for the process diagram dock."""

    CIRCUIT_PALETTE = [
        '#ff6b6b', '#4ecdc4', '#45b7d1', '#f59e0b',
        '#7c3aed', '#10b981', '#ef4444', '#64748b',
    ]

    def __init__(self, data_manager):
        super().__init__()
        self.data_manager = data_manager
        self.current_data = None
        self.highlight_point = None
        self._sat_cache = None
        self.generator = PhDiagramGenerator('R290')
        self.circuits = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        top = QHBoxLayout()
        title = QLabel("R290 P-h Cycle")
        title.setStyleSheet("font-weight:bold;color:#1f2933;")
        top.addWidget(title)
        top.addStretch()
        self.checks = {}
        self.toggle_layout = top
        self._sync_circuit_toggles()
        layout.addLayout(top)

        self.plot = pg.PlotWidget()
        self.plot.setBackground('w')
        self.plot.showGrid(x=True, y=True, alpha=0.22)
        self.plot.setLabel('bottom', 'h', units='BTU/lb')
        self.plot.setLabel('left', 'P', units='psig')
        self.plot.getAxis('bottom').setPen(pg.mkPen('#475569'))
        self.plot.getAxis('left').setPen(pg.mkPen('#475569'))
        layout.addWidget(self.plot, 1)

        self.status_label = QLabel("Waiting for calculation data")
        self.status_label.setStyleSheet("color:#64748b;font-size:11px;")
        layout.addWidget(self.status_label)

    @staticmethod
    def _h_kjkg_to_btulb(value):
        return float(value) * 0.429922614

    @staticmethod
    def _pa_to_psig(value):
        return float(value) / 6894.76 - 14.696

    def _sat_lines(self):
        if self._sat_cache is not None:
            return self._sat_cache
        try:
            sat = self.generator.generate_saturation_data(P_min_kpa=250, P_max_kpa=1300, num_points=120)
            h_liq = [self._h_kjkg_to_btulb(v) for v in sat['h_liquid']]
            h_vap = [self._h_kjkg_to_btulb(v) for v in sat['h_vapor']]
            p_psig = [self._pa_to_psig(v * 1000.0) for v in sat['pressures']]
            self._sat_cache = (h_liq, h_vap, p_psig)
        except Exception:
            self._sat_cache = ([], [], [])
        return self._sat_cache

    def load_filtered_data(self, filtered_df, circuit_data=None):
        if filtered_df is None or filtered_df.empty:
            self.current_data = None
            self.status_label.setText("No calculation data")
            self.plot.clear()
            return
        self.current_data = filtered_df
        self._sync_circuit_toggles()
        self._redraw()

    def highlight_finding(self, finding):
        scenario_id = str(getattr(finding, 'scenario_id', '') or '')
        label = str(getattr(finding, 'label', '') or '')
        if scenario_id == 'SI-1' or 'Negative Subcooling' in label or scenario_id.startswith('CD-'):
            self.highlight_point = '4a'
        elif scenario_id.startswith(('TX-', 'DI-')):
            self.highlight_point = '4b'
        elif scenario_id.startswith('EV-'):
            self.highlight_point = '2a'
        elif scenario_id.startswith('CP-'):
            self.highlight_point = '2b'
        else:
            self.highlight_point = None
        self._redraw()

    def _num(self, row, *names):
        for name in names:
            if name in row.index and pd.notna(row.get(name)):
                try:
                    return float(row.get(name))
                except (TypeError, ValueError):
                    pass
        return None

    @staticmethod
    def _label_abbrev(label, upper=False):
        text = str(label or '').strip()
        lookup = {
            'left': 'lh', 'lh': 'lh',
            'center': 'ctr', 'centre': 'ctr', 'ctr': 'ctr',
            'right': 'rh', 'rh': 'rh',
            'none': 'lh', '': 'lh',
        }
        ab = lookup.get(text.lower(), text.lower().replace(' ', '_') or 'lh')
        return ab.upper() if upper else ab

    @staticmethod
    def _display_label(label, fallback):
        text = str(label or '').strip()
        if not text or text.lower() == 'none':
            return fallback
        return text

    def _system_type(self):
        try:
            from calculation_orchestrator import _detect_system_type
            return _detect_system_type(self.data_manager.diagram_model or {})
        except Exception:
            comps = (self.data_manager.diagram_model or {}).get('components') or {}
            n_comp = sum(1 for comp in comps.values() if comp.get('type') == 'Compressor')
            return 'cassette' if n_comp > 1 else 'shared'

    def _actual_circuits(self):
        model = self.data_manager.diagram_model or {}
        system_type = self._system_type()
        labels = []
        if system_type == 'shared':
            try:
                from circuit_semantics import get_all_module_labels
                labels = get_all_module_labels(model)
            except Exception:
                labels = []
        if not labels:
            seen = set()
            preferred_types = {'Compressor', 'Condenser', 'TXV', 'CapTube', 'EEV', 'Evaporator'}
            for comp in (model.get('components') or {}).values():
                if comp.get('type') not in preferred_types:
                    continue
                label = (comp.get('properties') or {}).get('circuit_label')
                if label in (None, '', 'None'):
                    continue
                if label not in seen:
                    seen.add(label)
                    labels.append(label)
        if not labels:
            labels = [None]

        def sort_key(label):
            order = {'Left': 0, 'LH': 0, 'Center': 1, 'CTR': 1, 'Right': 2, 'RH': 2}
            return (order.get(label, 100), str(label or ''))

        circuits = []
        for idx, label in enumerate(sorted(labels, key=sort_key)):
            ab = self._label_abbrev(label)
            key = ab or f'unit_{idx + 1}'
            circuits.append({
                'key': key,
                'label': label,
                'display': self._display_label(label, 'Cycle'),
                'ab': ab,
                'upper': self._label_abbrev(label, upper=True),
                'color': self.CIRCUIT_PALETTE[idx % len(self.CIRCUIT_PALETTE)],
            })
        return circuits

    def _sync_circuit_toggles(self):
        circuits = self._actual_circuits()
        existing = set(self.checks.keys())
        wanted = {c['key'] for c in circuits}
        for key in list(existing - wanted):
            cb = self.checks.pop(key)
            self.toggle_layout.removeWidget(cb)
            cb.deleteLater()
        for circuit in circuits:
            key = circuit['key']
            color = circuit['color']
            if key not in self.checks:
                cb = QCheckBox(circuit['display'])
                cb.setChecked(True)
                cb.stateChanged.connect(lambda _state, self=self: self._redraw())
                self.checks[key] = cb
                self.toggle_layout.addWidget(cb)
            cb = self.checks[key]
            cb.setText(circuit['display'])
            cb.setStyleSheet(f"QCheckBox{{color:{color};font-weight:bold;}}")
        self.circuits = circuits

    def _pressure_psig(self, row, *names):
        value = self._num(row, *names)
        if value is None:
            return None
        return self._pa_to_psig(value) if value > 1000 else value

    @staticmethod
    def _valid_h(value):
        return value is not None and 50 < value < 700

    def _points(self, row):
        system_type = self._system_type()
        shared_p_suc = self._pressure_psig(row, 'P_suc', 'P_suction', 'Press.suc')
        shared_p_cond = self._pressure_psig(row, 'P_cond', 'P_disch', 'Press disch')
        shared_common = {}
        if system_type == 'shared':
            for name, pressure, cols in [
                ('2b', shared_p_suc, ('h_2b', 'Enthalpy', 'H_comp.in')),
                ('3a', shared_p_cond, ('h_3a', 'H_comp.out')),
                ('4a', shared_p_cond, ('h_4a', 'H_cond.out')),
            ]:
                h = self._num(row, *cols)
                if self._valid_h(h) and pressure is not None:
                    shared_common[name] = (self._h_kjkg_to_btulb(h), pressure)

        by_circuit = {}
        for circuit in self.circuits:
            key = circuit['key']
            ab = circuit['ab']
            up = circuit['upper']
            if system_type == 'cassette':
                p_suc = self._pressure_psig(row, f'P_suc-{ab}', f'P_suction-{ab}', 'P_suc', 'P_suction')
                p_cond = self._pressure_psig(row, f'P_cond-{ab}', f'P_disch-{ab}', f'P_disch.{ab}', 'P_cond', 'P_disch')
                pts = {}
                for name, pressure, cols in [
                    ('2b', p_suc, (f'h_2b-{ab}', f'h_2b_{up}', 'h_2b')),
                    ('3a', p_cond, (f'h_3a-{ab}', f'h_3a_{up}', 'h_3a')),
                    ('4a', p_cond, (f'h_4a-{ab}', f'h_4a_{up}', 'h_4a')),
                ]:
                    h = self._num(row, *cols)
                    if self._valid_h(h) and pressure is not None:
                        pts[name] = (self._h_kjkg_to_btulb(h), pressure)
            else:
                p_suc = shared_p_suc
                p_cond = shared_p_cond
                pts = dict(shared_common)

            h_2a = self._num(row, f'h_2a_{up}', f'h_2a_{up}-{ab}', f'H_coil {ab}')
            if self._valid_h(h_2a) and p_suc is not None:
                pts['2a'] = (self._h_kjkg_to_btulb(h_2a), p_suc)
            h_4b = self._num(row, f'h_4b_{up}', f'h_4b_{up}-{ab}', f'H_txv.{ab}', f'Enthalpy_txv_{ab}')
            if self._valid_h(h_4b) and p_cond is not None:
                pts['4b'] = (self._h_kjkg_to_btulb(h_4b), p_cond)
            if self._valid_h(h_4b) and p_suc is not None:
                pts['1'] = (self._h_kjkg_to_btulb(h_4b), p_suc)
            by_circuit[key] = pts
        return by_circuit

    def _redraw(self):
        self.plot.clear()
        if self.current_data is None or self.current_data.empty:
            return

        row = self.current_data.mean(numeric_only=True)
        h_liq, h_vap, p_psig = self._sat_lines()
        if h_liq and h_vap:
            self.plot.plot(h_liq, p_psig, pen=pg.mkPen('#111827', width=2))
            self.plot.plot(h_vap, p_psig, pen=pg.mkPen('#111827', width=2))

        by_circuit = self._points(row)
        order = ['2b', '3a', '4a', '4b', '1', '2a', '2b']
        display_labels = {'2b': '1', '3a': '2', '4b': '3', '1': '4'}
        plotted = []
        all_x, all_y = [], []
        circuit_lookup = {c['key']: c for c in self.circuits}
        for circuit_key, pts in by_circuit.items():
            circuit = circuit_lookup.get(circuit_key)
            if not circuit:
                continue
            if not self.checks[circuit_key].isChecked():
                continue
            coords = [pts[name] for name in order if name in pts]
            if len(coords) < 2:
                continue
            color = circuit['color']
            xs, ys = zip(*coords)
            self.plot.plot(xs, ys, pen=pg.mkPen(color, width=3))
            for point_name, (x, y) in pts.items():
                self.plot.plot([x], [y], pen=None, symbol='o', symbolSize=8,
                               symbolBrush=pg.mkBrush(color), symbolPen=pg.mkPen('w', width=1))
                display_name = display_labels.get(point_name)
                if display_name:
                    label = pg.TextItem(display_name, color=color, anchor=(0, 1))
                    label.setPos(x + 0.6, y)
                    self.plot.addItem(label)
                if point_name == self.highlight_point:
                    self.plot.plot([x], [y], pen=None, symbol='o', symbolSize=22,
                                   symbolBrush=pg.mkBrush(0, 0, 0, 0),
                                   symbolPen=pg.mkPen('#c0392b', width=3))
            plotted.append(circuit['display'])
            all_x.extend(xs)
            all_y.extend(ys)

        if all_x and all_y:
            min_x, max_x = min(all_x), max(all_x)
            min_y, max_y = min(all_y), max(all_y)
            self.plot.setXRange(min_x - 8, max_x + 8, padding=0)
            self.plot.setYRange(max(0, min_y - 20), max_y + 25, padding=0)
        self.status_label.setText("Showing " + (", ".join(plotted) if plotted else "no selected circuits"))


class PhDiagramWidget(QWidget):
    """
    Widget for displaying P-h diagrams with circuit-specific cycle overlays.
    """
    
    def __init__(self, data_manager):
        super().__init__()
        self.data_manager = data_manager
        self.plotter = PhDiagramPlotter('R290')
        self.current_data = None
        self.current_circuit_data = None
        self.highlight_point = None
        
        self.setup_ui()
    
    def setup_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # ==================== Title ====================
        title = QLabel("P-h Diagram (R290)")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title.setFont(title_font)
        main_layout.addWidget(title)
        
        # ==================== Control Panel ====================
        control_panel = self._create_control_panel()
        main_layout.addWidget(control_panel)
        
        # ==================== Matplotlib Canvas ====================
        self.figure = Figure(figsize=(16, 10), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        main_layout.addWidget(self.canvas, 1)
        
        # ==================== Status Bar ====================
        self.status_label = QLabel("Ready. Load filtered data from Calculations tab.")
        self.status_label.setStyleSheet("color: gray; font-style: italic;")
        main_layout.addWidget(self.status_label)
    
    def _create_control_panel(self):
        """Create the control panel with toggles and buttons."""
        panel = QGroupBox("Display Options")
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(15)
        
        # ========== Circuit Toggle Checkboxes ==========
        circuits_group = QGroupBox("Circuits")
        circuits_layout = QHBoxLayout()
        circuits_layout.setContentsMargins(5, 5, 5, 5)
        
        self.check_lh = QCheckBox("Left Hand (LH)")
        self.check_lh.setChecked(True)
        self.check_lh.stateChanged.connect(self.on_display_options_changed)
        circuits_layout.addWidget(self.check_lh)
        
        self.check_ctr = QCheckBox("Center (CTR)")
        self.check_ctr.setChecked(True)
        self.check_ctr.stateChanged.connect(self.on_display_options_changed)
        circuits_layout.addWidget(self.check_ctr)
        
        self.check_rh = QCheckBox("Right Hand (RH)")
        self.check_rh.setChecked(True)
        self.check_rh.stateChanged.connect(self.on_display_options_changed)
        circuits_layout.addWidget(self.check_rh)
        
        circuits_group.setLayout(circuits_layout)
        layout.addWidget(circuits_group)
        
        # ========== Background Lines Toggles ==========
        background_group = QGroupBox("Background")
        background_layout = QHBoxLayout()
        background_layout.setContentsMargins(5, 5, 5, 5)
        
        self.check_isotherms = QCheckBox("Isotherms")
        self.check_isotherms.setChecked(True)
        self.check_isotherms.stateChanged.connect(self.on_display_options_changed)
        background_layout.addWidget(self.check_isotherms)
        
        self.check_isentropes = QCheckBox("Isentropes")
        self.check_isentropes.setChecked(True)
        self.check_isentropes.stateChanged.connect(self.on_display_options_changed)
        background_layout.addWidget(self.check_isentropes)
        
        background_group.setLayout(background_layout)
        layout.addWidget(background_group)
        
        # ========== Action Buttons ==========
        self.btn_refresh = QPushButton("🔄 Refresh Diagram")
        self.btn_refresh.clicked.connect(self.on_display_options_changed)
        layout.addWidget(self.btn_refresh)
        
        self.btn_export = QPushButton("💾 Export as PNG")
        self.btn_export.clicked.connect(self.on_export_diagram)
        layout.addWidget(self.btn_export)
        
        layout.addStretch()
        panel.setLayout(layout)
        return panel
    
    def load_filtered_data(self, filtered_df, circuit_data=None):
        """
        Load filtered data and circuit-specific data for plotting.
        
        Args:
            filtered_df: DataFrame with calculated outputs
            circuit_data: Optional dict with circuit-specific calculations
        """
        if filtered_df is None or filtered_df.empty:
            self.status_label.setText("❌ No data to display. Filter data in Calculations tab first.")
            self.status_label.setStyleSheet("color: red;")
            return
        
        self.current_data = filtered_df
        self.current_circuit_data = circuit_data or {}
        
        print(f"\n[PH DIAGRAM] Data loaded: {len(filtered_df)} rows")
        
        self.status_label.setText(f"✓ Loaded {len(filtered_df)} rows. Displaying latest row on diagram.")
        self.status_label.setStyleSheet("color: green;")
        
        # Refresh diagram
        self.on_display_options_changed()
    
    def on_display_options_changed(self):
        """Handle changes to display options and redraw 3 diagrams (one per module)."""
        if self.current_data is None or self.current_data.empty:
            self.status_label.setText("❌ No data loaded. Use Calculations tab to filter data first.")
            self.status_label.setStyleSheet("color: red;")
            return
        
        try:
            # Use the same averaged steady-state snapshot as the diagram overlay.
            data_row = self.current_data.mean(numeric_only=True)
            
            # Build common points (non-circuit-specific)
            common_points = self._extract_common_points(data_row)
            
            # Build circuit-specific points
            circuit_points = self._extract_circuit_points(data_row)
            
            # Get toggle states
            show_lh = self.check_lh.isChecked()
            show_ctr = self.check_ctr.isChecked()
            show_rh = self.check_rh.isChecked()
            show_isotherms = self.check_isotherms.isChecked()
            show_isentropes = self.check_isentropes.isChecked()
            
            # Clear previous plot
            self.figure.clear()
            self.figure.patch.set_facecolor('white')
            
            # Determine which circuits to display
            circuits_to_plot = []
            if show_lh:
                circuits_to_plot.append('LH')
            if show_ctr:
                circuits_to_plot.append('CTR')
            if show_rh:
                circuits_to_plot.append('RH')
            
            # Create subplots: 1 row, 3 columns (one for each module)
            num_circuits = len(circuits_to_plot)
            if num_circuits == 0:
                self.status_label.setText("⚠️ No circuits selected for display.")
                self.status_label.setStyleSheet("color: orange;")
                self.canvas.draw()
                return
            
            axes = []
            for idx, circuit in enumerate(circuits_to_plot):
                ax = self.figure.add_subplot(1, 3, idx + 1)
                axes.append((circuit, ax))
            
            # Plot each circuit on its own subplot
            for circuit, ax in axes:
                ax.set_facecolor('#F8F9FA')
                
                # Get saturation line
                h_f, h_g, P_sat = self.plotter.get_saturation_line()
                
                # Plot saturation line
                ax.fill_betweenx(P_sat, h_f, h_g, alpha=0.1, color='gray')
                ax.plot(h_f, P_sat, 'k-', linewidth=2.5, label='Saturated liquid (Q=0)')
                ax.plot(h_g, P_sat, 'k-', linewidth=2.5, label='Saturated vapor (Q=1)')
                
                # Plot background lines
                if show_isotherms:
                    self._plot_isotherms(ax)
                
                if show_isentropes:
                    self._plot_isentropes(ax)
                
                # Merge common points with circuit-specific points
                if circuit in circuit_points:
                    complete_cycle = {**common_points, **circuit_points[circuit]}
                    self._plot_circuit_cycle(ax, circuit, complete_cycle)
                
                # Formatting
                ax.set_xlabel('Enthalpy [kJ/kg]', fontsize=11, fontweight='bold')
                ax.set_ylabel('Pressure [Pa]', fontsize=11, fontweight='bold')
                ax.set_title(f'P-h Diagram - {circuit} Circuit', fontsize=12, fontweight='bold', pad=15)
                
                ax.set_xlim(250, 550)
                ax.set_ylim(0.05e5, 4.5e6)  # 0.05 MPa to 4.5 MPa in Pa
                ax.set_yscale('log')
                
                ax.grid(True, which='both', alpha=0.3, linestyle='-', linewidth=0.5)
                ax.grid(True, which='minor', alpha=0.1, linestyle=':', linewidth=0.3)
                
                handles, labels = ax.get_legend_handles_labels()
                ax.legend(handles, labels, loc='best', fontsize=9, framealpha=0.95)
            
            self.figure.suptitle('P-h Diagrams for R290 - Latest Data Point', 
                                fontsize=14, fontweight='bold', y=0.98)
            self.figure.tight_layout()
            self.canvas.draw()
            
            self.status_label.setText(f"✓ Diagram updated. Showing {len(circuits_to_plot)} circuit(s): {', '.join(circuits_to_plot)}")
            self.status_label.setStyleSheet("color: green;")
            
        except Exception as e:
            self.status_label.setText(f"❌ Error plotting diagram: {str(e)}")
            self.status_label.setStyleSheet("color: red;")
            print(f"[PH DIAGRAM] Plot error: {e}")
            import traceback
            traceback.print_exc()
    
    def _extract_common_points(self, data_row):
        """
        Extract common (non-circuit-specific) state points from data row.

        Now uses NEW column names from unified calculation system (run_batch_processing).
        """
        common_points = {}

        # Debug: Print available columns
        print(f"\n[COMMON POINTS] Available columns: {list(data_row.index)[:20]}...")

        # Helper function to convert psig to Pa
        def psig_to_pa(psig):
            """Convert psig to Pa (Pascals)."""
            if psig is None or pd.isna(psig):
                return None
            psi_abs = psig + 14.696  # Convert to absolute pressure
            pa = psi_abs * 6894.76  # Convert to Pascals
            return pa

        # Get pressures (NEW column names: 'Press.suc', 'Press disch' in psig)
        P_suc_psig = data_row.get('Press.suc')
        P_disch_psig = data_row.get('Press disch')

        P_suc_pa = psig_to_pa(P_suc_psig) if P_suc_psig is not None else None
        P_disch_pa = psig_to_pa(P_disch_psig) if P_disch_psig is not None else None

        print(f"  Pressures: P_suc={P_suc_psig} psig ({P_suc_pa} Pa), P_disch={P_disch_psig} psig ({P_disch_pa} Pa)")

        # State 2b (Compressor inlet) - NEW column name: 'Enthalpy'
        if 'Enthalpy' in data_row.index and P_suc_pa is not None:
            h = data_row['Enthalpy']
            try:
                h_f = float(h)
                # Validate ranges: h should be 250-550 kJ/kg, P should be 0.05e5 to 4.5e6 Pa
                if 200 < h_f < 700 and 0.01e5 < P_suc_pa < 5e6 and pd.notna(h):
                    common_points['2b'] = {'h': h_f, 'P': P_suc_pa}
                    print(f"  ✓ 2b (Compressor Inlet): h={h_f:.2f} kJ/kg, P={P_suc_pa:.0f} Pa")
                else:
                    print(f"  ✗ 2b: Values out of range h={h_f:.2f}, P={P_suc_pa:.0f}")
            except (ValueError, TypeError) as e:
                print(f"  ✗ 2b: Cannot convert to float - {e}")
        else:
            print(f"  ✗ 2b: Enthalpy={('Enthalpy' in data_row.index)}, P_suc_pa={P_suc_pa is not None}")

        print(f"[COMMON POINTS] Extracted {len(common_points)} points\n")
        return common_points
    
    def _extract_circuit_points(self, data_row):
        """
        Extract circuit-specific state points from data row.

        Now uses NEW column names from unified calculation system (run_batch_processing).
        """
        circuit_points = {'LH': {}, 'CTR': {}, 'RH': {}}

        print(f"\n[CIRCUIT POINTS] Extracting circuit points...")

        # Helper function to convert psig to Pa
        def psig_to_pa(psig):
            """Convert psig to Pa (Pascals)."""
            if psig is None or pd.isna(psig):
                return None
            psi_abs = psig + 14.696  # Convert to absolute pressure
            pa = psi_abs * 6894.76  # Convert to Pascals
            return pa

        # Get pressures (NEW column names: 'Press.suc', 'Press disch' in psig)
        P_suc_psig = data_row.get('Press.suc')
        P_disch_psig = data_row.get('Press disch')

        P_suc_pa = psig_to_pa(P_suc_psig) if P_suc_psig is not None else None
        P_disch_pa = psig_to_pa(P_disch_psig) if P_disch_psig is not None else None

        # Map circuit names to DataFrame column suffixes
        circuit_col_map = {
            'LH': 'lh',
            'CTR': 'ctr',
            'RH': 'rh'
        }

        for circuit, col_suffix in circuit_col_map.items():
            print(f"  Circuit {circuit}:")

            # State 2a (Evaporator outlet - superheat point on low-pressure line)
            # NEW column name: 'H_coil lh', 'H_coil ctr', 'H_coil rh'
            h_col = f'H_coil {col_suffix}'
            if h_col in data_row.index and P_suc_pa is not None:
                h = data_row[h_col]
                try:
                    h_f = float(h)
                    if 200 < h_f < 700 and 0.01e5 < P_suc_pa < 5e6 and pd.notna(h):
                        circuit_points[circuit]['2a'] = {'h': h_f, 'P': P_suc_pa}
                        print(f"    ✓ 2a (Evaporator Outlet): h={h_f:.2f} kJ/kg, P={P_suc_pa:.0f} Pa ({P_suc_pa/1e5:.1f} bar)")
                    else:
                        print(f"    ✗ 2a: Values out of range h={h_f:.2f}, P={P_suc_pa:.0f}")
                except (ValueError, TypeError) as e:
                    print(f"    ✗ 2a: Cannot convert to float - {e}")
            else:
                print(f"    ✗ 2a: {h_col}={h_col in data_row.index}, P_suc_pa={P_suc_pa is not None}")

            # State 4b (TXV inlet - subcooling point on high-pressure line)
            # NEW column name: 'Enthalpy_txv_lh', 'Enthalpy_txv_ctr', 'Enthalpy_txv_rh'
            h_col = f'Enthalpy_txv_{col_suffix}'
            if h_col in data_row.index and P_disch_pa is not None:
                h = data_row[h_col]
                try:
                    h_f = float(h)
                    if 200 < h_f < 700 and 0.01e5 < P_disch_pa < 5e6 and pd.notna(h):
                        circuit_points[circuit]['4b'] = {'h': h_f, 'P': P_disch_pa}
                        print(f"    ✓ 4b (TXV Inlet): h={h_f:.2f} kJ/kg, P={P_disch_pa:.0f} Pa ({P_disch_pa/1e5:.1f} bar)")
                    else:
                        print(f"    ✗ 4b: Values out of range h={h_f:.2f}, P={P_disch_pa:.0f}")
                except (ValueError, TypeError) as e:
                    print(f"    ✗ 4b: Cannot convert to float - {e}")
            else:
                print(f"    ✗ 4b: {h_col}={h_col in data_row.index}, P_disch_pa={P_disch_pa is not None}")

        print(f"[CIRCUIT POINTS] Extracted {sum(len(pts) for pts in circuit_points.values())} total points\n")
        return circuit_points
    
    def _plot_circuit_cycle(self, ax, circuit, points):
        """Plot circuit cycle path and points."""
        color = self.plotter.circuit_colors[circuit]
        
        # Plot points
        for point_name, point_data in points.items():
            h = point_data.get('h')
            P = point_data.get('P')
            if h is not None and P is not None:
                ax.plot(h, P, 'o', color=color, markersize=9, zorder=10)
                ax.text(h, P, f'  {circuit}-{point_name}', fontsize=9,
                       verticalalignment='center', color=color, alpha=0.9, fontweight='bold')
        
        # Draw cycle path (use both circuit-specific and common points)
        # For circuit cycles: 2a (circuit) -> 2b (common) -> 3a (common) -> 3b (common) -> 4a (common) -> 4b (circuit) -> back to 2a
        cycle_order = ['2a', '2b', '3a', '3b', '4a', '4b']
        h_cycle = []
        P_cycle = []
        points_in_cycle = []
        
        for point_name in cycle_order:
            if point_name in points:
                h_cycle.append(points[point_name]['h'])
                P_cycle.append(points[point_name]['P'])
                points_in_cycle.append(point_name)
        
        # Close cycle
        if h_cycle and len(h_cycle) > 1:
            h_cycle.append(h_cycle[0])
            P_cycle.append(P_cycle[0])
            print(f"    Plotting cycle for {circuit}: {' -> '.join(points_in_cycle)} -> {points_in_cycle[0]}")
            ax.plot(h_cycle, P_cycle, '-', color=color, linewidth=3, 
                   label=f'{circuit} Circuit ({len(points_in_cycle)} points)', zorder=9, alpha=0.85)
        else:
            print(f"    ⚠ {circuit} circuit incomplete: only {len(h_cycle)} points")
    
    def _extract_common_points(self, data_row):
        """Extract common state points from the current calculation columns."""
        common_points = {}

        def psig_to_pa(psig):
            if psig is None or pd.isna(psig):
                return None
            return (float(psig) + 14.696) * 6894.76

        def num(*names):
            for name in names:
                if name in data_row.index and pd.notna(data_row.get(name)):
                    try:
                        return float(data_row.get(name))
                    except (TypeError, ValueError):
                        pass
            return None

        p_suc = num('P_suc') or psig_to_pa(num('Press.suc', 'P_suction'))
        p_cond = num('P_cond') or psig_to_pa(num('Press disch', 'P_disch'))
        for point_name, pressure, h_names in [
            ('2b', p_suc, ('h_2b', 'Enthalpy', 'H_comp.in')),
            ('3a', p_cond, ('h_3a', 'H_comp.out')),
            ('4a', p_cond, ('h_4a', 'H_cond.out')),
        ]:
            h = num(*h_names)
            if h is not None and pressure is not None and 200 < h < 700 and 0.01e5 < pressure < 5e6:
                common_points[point_name] = {'h': h, 'P': pressure}
        return common_points

    def _extract_circuit_points(self, data_row):
        """Extract per-branch state points from the current calculation columns."""
        circuit_points = {'LH': {}, 'CTR': {}, 'RH': {}}

        def psig_to_pa(psig):
            if psig is None or pd.isna(psig):
                return None
            return (float(psig) + 14.696) * 6894.76

        def num(*names):
            for name in names:
                if name in data_row.index and pd.notna(data_row.get(name)):
                    try:
                        return float(data_row.get(name))
                    except (TypeError, ValueError):
                        pass
            return None

        p_suc = num('P_suc') or psig_to_pa(num('Press.suc', 'P_suction'))
        p_cond = num('P_cond') or psig_to_pa(num('Press disch', 'P_disch'))
        for circuit, suffix in {'LH': 'lh', 'CTR': 'ctr', 'RH': 'rh'}.items():
            h_2a = num(f'h_2a_{circuit}', f'H_coil {suffix}')
            if h_2a is not None and p_suc is not None and 200 < h_2a < 700:
                circuit_points[circuit]['2a'] = {'h': h_2a, 'P': p_suc}
            h_4b = num(f'h_4b_{circuit}', f'Enthalpy_txv_{suffix}')
            if h_4b is not None and p_cond is not None and 200 < h_4b < 700:
                circuit_points[circuit]['4b'] = {'h': h_4b, 'P': p_cond}
            if h_4b is not None and p_suc is not None and 200 < h_4b < 700:
                circuit_points[circuit]['1'] = {'h': h_4b, 'P': p_suc}
        return circuit_points

    def _plot_circuit_cycle(self, ax, circuit, points):
        """Plot circuit cycle path and optionally highlight a finding state point."""
        color = self.plotter.circuit_colors[circuit]
        for point_name, point_data in points.items():
            h = point_data.get('h')
            P = point_data.get('P')
            if h is not None and P is not None:
                ax.plot(h, P, 'o', color=color, markersize=8, zorder=10)
                ax.text(h, P, f'  {circuit}-{point_name}', fontsize=8,
                        verticalalignment='center', color=color, alpha=0.9, fontweight='bold')

        cycle_order = ['2a', '2b', '3a', '4a', '4b', '1']
        h_cycle, p_cycle, points_in_cycle = [], [], []
        for point_name in cycle_order:
            if point_name in points:
                h_cycle.append(points[point_name]['h'])
                p_cycle.append(points[point_name]['P'])
                points_in_cycle.append(point_name)
        if len(h_cycle) > 1:
            h_cycle.append(h_cycle[0])
            p_cycle.append(p_cycle[0])
            ax.plot(h_cycle, p_cycle, '-', color=color, linewidth=2.5,
                    label=f'{circuit} Circuit ({len(points_in_cycle)} points)',
                    zorder=9, alpha=0.85)

        if self.highlight_point and self.highlight_point in points:
            target = points[self.highlight_point]
            ax.plot(target['h'], target['P'], 'o', markerfacecolor='none',
                    markeredgecolor='#c0392b', markersize=18,
                    markeredgewidth=3.0, zorder=20,
                    label=f'Highlighted {self.highlight_point}')
            ax.text(target['h'], target['P'], f"  check {self.highlight_point}",
                    fontsize=10, color='#c0392b', fontweight='bold',
                    verticalalignment='bottom')

    def highlight_finding(self, finding):
        scenario_id = str(getattr(finding, 'scenario_id', '') or '')
        label = str(getattr(finding, 'label', '') or '')
        if scenario_id == 'SI-1' or 'Negative Subcooling' in label:
            self.highlight_point = '4a'
        elif scenario_id.startswith(('TX-', 'DI-')):
            self.highlight_point = '4b'
        elif scenario_id.startswith('EV-'):
            self.highlight_point = '2a'
        elif scenario_id.startswith('CP-'):
            self.highlight_point = '2b'
        elif scenario_id.startswith('CD-'):
            self.highlight_point = '4a'
        else:
            self.highlight_point = None
        if self.current_data is not None:
            self.on_display_options_changed()

    def _plot_isotherms(self, ax):
        """Plot constant temperature lines."""
        temperatures = [250, 270, 290, 310, 330, 350]  # K
        for T in temperatures:
            try:
                h_iso, P_iso = self.plotter.get_isotherm_line(T)
                if len(h_iso) > 1:
                    ax.plot(h_iso, P_iso, 'b--', alpha=0.25, linewidth=0.7)
                    mid_idx = len(h_iso) // 2
                    ax.text(h_iso[mid_idx], P_iso[mid_idx], f'{T-273.15:.0f}°C',
                           fontsize=7, color='blue', alpha=0.5, rotation=0)
            except:
                pass
    
    def _plot_isentropes(self, ax):
        """Plot constant entropy lines."""
        try:
            P_test = 1.5e6
            s_values = []
            from CoolProp.CoolProp import PropsSI
            for Q in [0.2, 0.4, 0.6, 0.8]:
                s = PropsSI('S', 'P', P_test, 'Q', Q, 'R290') / 1000
                s_values.append(s)
            
            for s in s_values:
                try:
                    h_isen, P_isen = self.plotter.get_isentrope_line(s * 1000)
                    if len(h_isen) > 1:
                        ax.plot(h_isen, P_isen, 'g--', alpha=0.15, linewidth=0.7)
                except:
                    pass
        except:
            pass
    
    def on_export_diagram(self):
        """Export diagram as PNG."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export P-h Diagram",
            "",
            "PNG Images (*.png);;PDF Files (*.pdf);;SVG Files (*.svg)"
        )
        
        if file_path:
            try:
                self.figure.savefig(file_path, dpi=300, bbox_inches='tight', facecolor='white')
                QMessageBox.information(self, "Success", f"Diagram exported to:\n{file_path}")
                self.status_label.setText(f"✓ Exported to {file_path}")
                self.status_label.setStyleSheet("color: green;")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export: {str(e)}")
                self.status_label.setText(f"❌ Export failed: {str(e)}")
                self.status_label.setStyleSheet("color: red;")
