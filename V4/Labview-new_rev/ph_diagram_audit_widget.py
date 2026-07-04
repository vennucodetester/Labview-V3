"""
PH Diagram Widget for Audit Dialog

Displays a P-h diagram for a specific row's cycle data with state indicators.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox, QHBoxLayout
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np

from ph_diagram_generator import PhDiagramGenerator
from audit_data_extractor import AuditDataExtractor


class PhDiagramAuditWidget(QWidget):
    """Widget displaying P-h diagram for a single row's cycle data."""

    def __init__(self, row_data, parent=None):
        super().__init__(parent)
        self.row_data = row_data
        self.current_circuit = 'LH'
        self.generator = PhDiagramGenerator('R290')
        self.extractor = AuditDataExtractor()

        self.setup_ui()
        self.plot_diagram()

    def setup_ui(self):
        """Create the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)  # Minimal margins
        layout.setSpacing(2)

        # Compact header with circuit selector inline
        header_layout = QHBoxLayout()
        header_layout.setSpacing(5)

        title = QLabel("P-h Diagram")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(9)  # Smaller font
        title.setFont(title_font)
        header_layout.addWidget(title)

        header_layout.addSpacing(10)

        # Circuit selector inline (more compact)
        circuit_label = QLabel("Circuit:")
        circuit_label.setFont(QFont('Arial', 8))
        header_layout.addWidget(circuit_label)

        self.circuit_combo = QComboBox()
        self.circuit_combo.addItems(['LH', 'CTR', 'RH'])
        self.circuit_combo.setCurrentText(self.current_circuit)
        self.circuit_combo.currentTextChanged.connect(self.on_circuit_changed)
        self.circuit_combo.setMaximumWidth(60)  # Compact dropdown
        header_layout.addWidget(self.circuit_combo)

        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Matplotlib canvas - maximize space
        self.figure = Figure(figsize=(7, 5.5), dpi=90)
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

    def on_circuit_changed(self, circuit):
        """Handle circuit selection change."""
        self.current_circuit = circuit
        self.plot_diagram()

    def plot_diagram(self):
        """Plot the P-h diagram with cycle points."""
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        # Generate saturation dome
        sat_data = self.generator.generate_saturation_data(
            P_min_kpa=100, P_max_kpa=4500, num_points=50
        )

        # Plot saturation lines
        ax.plot(sat_data['h_liquid'], sat_data['pressures'],
                'b-', linewidth=2, label='Saturated Liquid', alpha=0.7)
        ax.plot(sat_data['h_vapor'], sat_data['pressures'],
                'r-', linewidth=2, label='Saturated Vapor', alpha=0.7)

        # Extract cycle points for current circuit
        cycle_points = self.extractor.extract_cycle_points(self.row_data, self.current_circuit)

        # Convert pressures from PSIG to kPa for plotting
        def psig_to_kpa(psig):
            if psig is None:
                return None
            return (psig + 14.696) * 6.89476

        # Plot cycle points in order
        plot_order = ['1_evap_inlet', '2_evap_outlet', '3_comp_inlet',
                      '4_comp_outlet', '5_cond_outlet', '6_txv_outlet']

        h_values = []
        p_values = []
        point_colors = []
        point_labels = []

        for point_id in plot_order:
            if point_id not in cycle_points:
                continue

            point = cycle_points[point_id]
            h = point.get('h')
            p_psig = point.get('p')
            sh = point.get('sh')
            sc = point.get('sc')

            if h is None or p_psig is None:
                continue

            p_kpa = psig_to_kpa(p_psig)
            if p_kpa is None:
                continue

            h_values.append(h)
            p_values.append(p_kpa)

            # Determine color based on state
            label, color, severity = self.extractor.classify_state(sh=sh, sc=sc)

            # Map text color names to matplotlib colors
            color_map = {
                'red': '#dc3545',
                'orange': '#fd7e14',
                'yellow': '#ffc107',
                'green': '#28a745',
                'blue': '#007bff',
                'gray': '#6c757d'
            }
            point_colors.append(color_map.get(color, '#6c757d'))

            # Create label with state info
            point_name = point.get('name', '').replace(f' {self.current_circuit}', '')
            if sh is not None:
                label_text = f"{point_name}\nSH={sh:.1f}°F"
            elif sc is not None:
                label_text = f"{point_name}\nSC={sc:.1f}°F"
            else:
                label_text = point_name
            point_labels.append(label_text)

        # Plot cycle points
        if len(h_values) >= 2:
            # Create mapping of point_id to coordinates for segment drawing
            point_coords = {}
            for i, point_id in enumerate(plot_order):
                if i < len(h_values) and i < len(p_values):
                    point_coords[point_id] = (h_values[i], p_values[i])

            # Define cycle segments with thermodynamic process names
            # IMPORTANT: Arrow direction is ALWAYS in the order listed (start→end)
            # regardless of actual enthalpy values to maintain consistent visual flow
            cycle_segments = [
                ('1_evap_inlet', '2_evap_outlet', 'Evaporation'),
                ('2_evap_outlet', '3_comp_inlet', 'Suction Line'),
                ('3_comp_inlet', '4_comp_outlet', 'Compression'),
                ('4_comp_outlet', '5_cond_outlet', 'Condensation'),
                ('5_cond_outlet', '6_txv_outlet', 'Subcooling'),
                ('6_txv_outlet', '1_evap_inlet', 'Expansion')
            ]

            # Draw each segment with directional arrow and enthalpy change annotation
            for segment_idx, (start_id, end_id, process_name) in enumerate(cycle_segments):
                if start_id in point_coords and end_id in point_coords:
                    h1, p1 = point_coords[start_id]
                    h2, p2 = point_coords[end_id]
                    delta_h = h2 - h1

                    # Determine color and style based on enthalpy change
                    # Red for backward flow (negative Δh in evaporator/condenser)
                    if process_name == 'Evaporation' and delta_h < 0:
                        color = '#dc3545'  # Red - thermodynamic anomaly
                        linewidth = 2.5
                        linestyle = '-'
                        label_prefix = '⚠ '
                    elif process_name == 'Condensation' and delta_h > 0:
                        color = '#dc3545'  # Red - condenser heating refrigerant
                        linewidth = 2.5
                        linestyle = '-'
                        label_prefix = '⚠ '
                    else:
                        color = 'black'
                        linewidth = 1.5
                        linestyle = '--'
                        label_prefix = ''

                    # Draw line segment
                    ax.plot([h1, h2], [p1, p2], color=color,
                           linewidth=linewidth, linestyle=linestyle,
                           alpha=0.7, zorder=2)

                    # Calculate midpoint for arrow and label
                    h_mid = (h1 + h2) / 2
                    p_mid = np.sqrt(p1 * p2)  # Geometric mean for log scale

                    # FORCE arrow to ALWAYS point in logical cycle direction (1→2→3→4→1)
                    # regardless of actual enthalpy values to maintain consistent visual flow
                    arrow_offset = 0.15  # 15% along the segment

                    # Define expected direction for each process type
                    # For normal operation: evap increases h, compression increases h,
                    # condensation decreases h, expansion keeps h constant
                    expected_forward = True  # Default: h2 > h1 means forward

                    if process_name in ['Condensation', 'Subcooling']:
                        # These processes should show forward arrows even when h decreases
                        expected_forward = True  # Arrow from high h to low h is forward
                    elif process_name == 'Expansion':
                        # Expansion: arrow should go from high P to low P (down)
                        expected_forward = True

                    # ALWAYS draw arrow in the start→end direction visually
                    # Calculate arrow positions along the line from point 1 to point 2
                    h_arrow_start = h1 + (h2 - h1) * (0.5 - arrow_offset)
                    h_arrow_end = h1 + (h2 - h1) * (0.5 + arrow_offset)
                    p_arrow_start = p1 * ((p2 / p1) ** (0.5 - arrow_offset)) if p1 > 0 and p2 > 0 else p1
                    p_arrow_end = p1 * ((p2 / p1) ** (0.5 + arrow_offset)) if p1 > 0 and p2 > 0 else p2

                    # Draw arrow pointing from start to end (always forward in cycle direction)
                    ax.annotate('', xy=(h_arrow_end, p_arrow_end),
                               xytext=(h_arrow_start, p_arrow_start),
                               arrowprops=dict(arrowstyle='->', color=color,
                                             lw=linewidth, mutation_scale=15))

                    # Add Δh annotation for critical processes
                    if process_name in ['Evaporation', 'Condensation'] and abs(delta_h) > 1.0:
                        # Position label offset from midpoint
                        label_offset_x = -20 if delta_h < 0 else 20
                        label_offset_y = 0

                        delta_h_text = f'{label_prefix}Δh={delta_h:+.1f}'
                        ax.annotate(delta_h_text, xy=(h_mid, p_mid),
                                   xytext=(label_offset_x, label_offset_y),
                                   textcoords='offset points', fontsize=6,
                                   bbox=dict(boxstyle='round,pad=0.3',
                                           facecolor='white', alpha=0.8,
                                           edgecolor=color, linewidth=1),
                                   ha='center', va='center', color=color, weight='bold')

            # Plot individual points with colors
            for i, (h, p, color, label) in enumerate(zip(h_values, p_values, point_colors, point_labels)):
                ax.scatter(h, p, s=150, c=color, marker='o',
                          edgecolors='black', linewidths=2, zorder=5)

                # Add annotation
                if i % 2 == 0:  # Alternate side to avoid overlap
                    xytext = (15, 15)
                else:
                    xytext = (15, -15)

                ax.annotate(label, xy=(h, p), xytext=xytext,
                           textcoords='offset points', fontsize=7,
                           bbox=dict(boxstyle='round,pad=0.4',
                                   facecolor=color, alpha=0.6, edgecolor='black'),
                           ha='left', va='center')

        # Formatting - optimized for space
        ax.set_xlabel('Enthalpy (kJ/kg)', fontsize=9)
        ax.set_ylabel('Pressure (kPa)', fontsize=9)
        ax.set_title(f'{self.current_circuit} Circuit', fontsize=10, fontweight='bold', pad=5)
        ax.set_yscale('log')
        ax.grid(True, alpha=0.3, which='both')
        ax.tick_params(labelsize=8)  # Smaller tick labels

        # Compact legend at BOTTOM (horizontal, single row)
        from matplotlib.lines import Line2D

        legend_elements = [
            Line2D([0], [0], color='b', linewidth=1.5, alpha=0.7, label='Sat. Liquid'),
            Line2D([0], [0], color='r', linewidth=1.5, alpha=0.7, label='Sat. Vapor'),
            Line2D([0], [0], color='black', linewidth=1.5, linestyle='--', label='Normal'),
            Line2D([0], [0], color='#dc3545', linewidth=2, linestyle='-', label='⚠ Anomaly')
        ]
        ax.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, -0.08),
                  ncol=4, fontsize=7, framealpha=0.95, columnspacing=1.5)

        # Set reasonable limits - ALWAYS include saturation curves in view
        # Calculate limits that encompass BOTH saturation data AND cycle points
        h_min_sat = sat_data['h_liquid'].min() if len(sat_data['h_liquid']) > 0 else 200
        h_max_sat = sat_data['h_vapor'].max() if len(sat_data['h_vapor']) > 0 else 600
        p_min_sat = sat_data['pressures'].min() if len(sat_data['pressures']) > 0 else 100
        p_max_sat = sat_data['pressures'].max() if len(sat_data['pressures']) > 0 else 4500

        # Combine saturation bounds with cycle point bounds
        if h_values:
            h_min_cycle = min(h_values)
            h_max_cycle = max(h_values)
            # Use the wider range between saturation and cycle
            h_min = min(h_min_sat, h_min_cycle)
            h_max = max(h_max_sat, h_max_cycle)
        else:
            # No cycle points - just show saturation curves
            h_min = h_min_sat
            h_max = h_max_sat

        h_range = h_max - h_min
        ax.set_xlim(h_min - 0.1 * h_range, h_max + 0.1 * h_range)

        if p_values:
            p_min_cycle = min(p_values)
            p_max_cycle = max(p_values)
            # Use the wider range between saturation and cycle
            p_min = min(p_min_sat, p_min_cycle)
            p_max = max(p_max_sat, p_max_cycle)
        else:
            # No cycle points - just show saturation curves
            p_min = p_min_sat
            p_max = p_max_sat

        ax.set_ylim(p_min * 0.8, p_max * 1.2)

        # Tight layout with minimal padding - maximize plot area
        self.figure.tight_layout(pad=0.3, h_pad=0.5, w_pad=0.5)
        self.canvas.draw()
