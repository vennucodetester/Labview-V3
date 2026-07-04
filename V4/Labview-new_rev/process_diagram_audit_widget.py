"""
Process Diagram Widget for Audit Dialog

Displays a simplified process flow diagram showing component states.
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QGraphicsView,
                             QGraphicsScene, QGraphicsRectItem, QGraphicsTextItem,
                             QGraphicsLineItem, QGraphicsEllipseItem, QComboBox, QHBoxLayout,
                             QPushButton, QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt, QRectF, QPointF, QSizeF, QMarginsF
from PyQt6.QtGui import QFont, QPen, QBrush, QColor, QPainter, QPageLayout, QPageSize
from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtSvg import QSvgGenerator

from audit_data_extractor import AuditDataExtractor


class ProcessDiagramAuditWidget(QWidget):
    """Widget displaying process flow diagram for a single row's cycle data."""

    def __init__(self, row_data, parent=None):
        super().__init__(parent)
        self.row_data = row_data
        self.current_circuit = 'LH'
        self.extractor = AuditDataExtractor()

        self.setup_ui()
        self.draw_diagram()

    def setup_ui(self):
        """Create the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)  # Minimal margins
        layout.setSpacing(2)

        # Compact header with circuit selector inline
        header_layout = QHBoxLayout()
        header_layout.setSpacing(5)

        title = QLabel("Process Flow")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(9)  # Smaller font
        title.setFont(title_font)
        header_layout.addWidget(title)

        header_layout.addSpacing(10)

        # Circuit selector inline
        circuit_label = QLabel("Circuit:")
        circuit_label.setFont(QFont('Arial', 8))
        header_layout.addWidget(circuit_label)

        self.circuit_combo = QComboBox()
        self.circuit_combo.addItems(['LH', 'CTR', 'RH'])
        self.circuit_combo.setCurrentText(self.current_circuit)
        self.circuit_combo.currentTextChanged.connect(self.on_circuit_changed)
        self.circuit_combo.setMaximumWidth(60)  # Compact
        header_layout.addWidget(self.circuit_combo)

        header_layout.addStretch()

        # Export button
        self.export_btn = QPushButton("💾 Export")
        self.export_btn.setToolTip("Export diagram as PNG, PDF, or SVG")
        self.export_btn.clicked.connect(self.export_diagram)
        self.export_btn.setMaximumWidth(80)
        header_layout.addWidget(self.export_btn)

        layout.addLayout(header_layout)

        # Graphics view - maximize space
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setBackgroundBrush(QBrush(QColor(250, 250, 250)))  # Light gray background
        layout.addWidget(self.view)

    def on_circuit_changed(self, circuit):
        """Handle circuit selection change."""
        self.current_circuit = circuit
        self.draw_diagram()

    def draw_diagram(self):
        """Draw optimized process flow diagram with maximum horizontal space utilization."""
        self.scene.clear()

        # Extract cycle points
        cycle_points = self.extractor.extract_cycle_points(self.row_data, self.current_circuit)

        # Optimized WIDE layout for maximum horizontal space utilization
        # Total available: ~800x240px, use smaller margins
        margin = 20

        # Component positions for WIDE rectangular flow
        # CONDENSER: Top, stretched horizontally across most of width
        cond_x, cond_y = margin + 120, margin
        cond_w, cond_h = 480, 45

        # COMPRESSOR: Right side, vertically centered (larger for readability)
        comp_x, comp_y = margin + 660, margin + 75
        comp_w, comp_h = 100, 90

        # EVAPORATOR: Bottom, aligned with condenser horizontally
        evap_x, evap_y = margin + 120, margin + 175
        evap_w, evap_h = 480, 45

        # TXV: Left side, vertically centered (as valve symbol)
        txv_x, txv_y = margin + 40, margin + 95
        txv_w, txv_h = 35, 50

        # Draw components with health-based coloring
        # 1. CONDENSER (Top)
        cond_state = self._get_component_state(cycle_points, '5_cond_outlet')
        cond_color = self._get_state_color(cond_state[1])
        self._draw_heat_exchanger(cond_x, cond_y, cond_w, cond_h, "CONDENSER", cond_color)

        # 2. COMPRESSOR (Right)
        comp_state = self._get_component_state(cycle_points, '3_comp_inlet')
        comp_color = self._get_state_color(comp_state[1])
        self._draw_compressor(comp_x, comp_y, comp_w, comp_h, "COMP", comp_color)

        # 3. EVAPORATOR (Bottom)
        evap_state = self._get_component_state(cycle_points, '2_evap_outlet')
        evap_color = self._get_state_color(evap_state[1])
        self._draw_heat_exchanger(evap_x, evap_y, evap_w, evap_h, "EVAPORATOR", evap_color)

        # 4. TXV (Left, as valve symbol)
        self._draw_txv_symbol(txv_x, txv_y, txv_w, txv_h)

        # Draw rectangular flow path with professional line styling
        pen = QPen(QColor('#2c3e50'), 4)  # Thicker for hierarchy
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)  # Rounded ends
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)  # Smooth corners

        arrow_pen = QPen(QColor('#2c3e50'), 2.5)
        arrow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        arrow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        # Define connection points for state labels
        # Following refrigeration cycle: Evap → Comp → Cond → TXV → Evap

        # 1. Evaporator outlet (2a) to Compressor inlet (2b)
        # Horizontal line from evap right edge
        evap_out_x = evap_x + evap_w
        evap_out_y = evap_y + evap_h/2
        comp_in_x = comp_x + comp_w/2
        comp_in_y = comp_y + comp_h

        self._draw_flow_line(evap_out_x, evap_out_y, comp_in_x, evap_out_y, pen)  # Horizontal
        self._draw_flow_line(comp_in_x, evap_out_y, comp_in_x, comp_in_y, pen)  # Vertical up
        self._add_state_label("2a", evap_out_x + 5, evap_out_y - 15, cycle_points.get('2_evap_outlet'))
        self._add_state_label("2b", comp_in_x + 10, comp_in_y - 5, cycle_points.get('3_comp_inlet'))
        self._draw_arrow(comp_in_x, comp_in_y - 20, comp_in_x, comp_in_y - 10, arrow_pen)

        # 2. Compressor outlet (3a) to Condenser inlet (3b)
        # Vertical line from comp top, then horizontal to cond right edge
        comp_out_x = comp_x + comp_w/2
        comp_out_y = comp_y
        cond_in_x = cond_x + cond_w
        cond_in_y = cond_y + cond_h/2

        self._draw_flow_line(comp_out_x, comp_out_y, comp_out_x, cond_in_y, pen)  # Vertical up
        self._draw_flow_line(comp_out_x, cond_in_y, cond_in_x, cond_in_y, pen)  # Horizontal left
        self._add_state_label("3a", comp_out_x + 10, comp_out_y + 5, cycle_points.get('4_comp_outlet'))
        self._add_state_label("3b", cond_in_x - 25, cond_in_y - 15, cycle_points.get('4_comp_outlet'))
        self._draw_arrow(cond_in_x - 20, cond_in_y, cond_in_x - 10, cond_in_y, arrow_pen)

        # 3. Condenser outlet (4a) to TXV inlet (4b)
        # Horizontal line from cond left edge, then vertical down to TXV
        cond_out_x = cond_x
        cond_out_y = cond_y + cond_h/2
        txv_in_x = txv_x + txv_w/2
        txv_in_y = txv_y

        self._draw_flow_line(cond_out_x, cond_out_y, txv_in_x, cond_out_y, pen)  # Horizontal left
        self._draw_flow_line(txv_in_x, cond_out_y, txv_in_x, txv_in_y, pen)  # Vertical down
        self._add_state_label("4a", cond_out_x - 15, cond_out_y - 15, cycle_points.get('5_cond_outlet'))
        self._add_state_label("4b", txv_in_x + 15, txv_in_y + 5, cycle_points.get('6_txv_outlet'))
        self._draw_arrow(txv_in_x, txv_in_y + 10, txv_in_x, txv_in_y + 20, arrow_pen)

        # 4. TXV outlet (1) to Evaporator inlet
        # Vertical line from TXV bottom, then horizontal to evap left edge
        txv_out_x = txv_x + txv_w/2
        txv_out_y = txv_y + txv_h
        evap_in_x = evap_x
        evap_in_y = evap_y + evap_h/2

        dash_pen = QPen(QColor('#3498DB'), 4, Qt.PenStyle.DashLine)  # Blue for two-phase
        dash_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        dash_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        dash_pen.setDashPattern([6, 3])  # Custom dash pattern
        self._draw_flow_line(txv_out_x, txv_out_y, txv_out_x, evap_in_y, dash_pen)  # Vertical down
        self._draw_flow_line(txv_out_x, evap_in_y, evap_in_x, evap_in_y, dash_pen)  # Horizontal right
        self._add_state_label("1", txv_out_x - 20, txv_out_y + 15, cycle_points.get('1_evap_inlet'))
        self._draw_arrow(evap_in_x + 10, evap_in_y, evap_in_x + 20, evap_in_y, arrow_pen)

        # Set scene rect to fit wide optimized layout
        self.scene.setSceneRect(0, 0, 800, 240)

    def _draw_heat_exchanger(self, x, y, w, h, label, color):
        """Draw a professional heat exchanger with gradients, tube details, and shadows."""
        from PyQt6.QtGui import QLinearGradient, QRadialGradient
        from PyQt6.QtWidgets import QGraphicsLineItem

        # 1. Drop shadow (drawn first, behind everything)
        shadow_offset = 4
        shadow_rect = QGraphicsRectItem(x + shadow_offset, y + shadow_offset, w, h)
        shadow_rect.setPen(QPen(Qt.PenStyle.NoPen))
        shadow_rect.setBrush(QBrush(QColor(0, 0, 0, 50)))
        self.scene.addItem(shadow_rect)

        # 2. Main body with metallic gradient
        gradient = QLinearGradient(x, y, x, y + h)
        gradient.setColorAt(0.0, QColor("#E8E8E8"))   # Top - lighter
        gradient.setColorAt(0.5, QColor("#FAFAFA"))   # Center - lightest
        gradient.setColorAt(1.0, QColor("#D0D0D0"))   # Bottom - darker

        rect = QGraphicsRectItem(x, y, w, h)
        rect.setBrush(QBrush(gradient))
        rect.setPen(QPen(QColor("#2C3E50"), 3))
        self.scene.addItem(rect)

        # 3. Internal tube detail (horizontal lines representing tubes)
        tube_pen = QPen(QColor("#999999"), 1)
        num_tubes = 7
        for i in range(1, num_tubes):
            tube_y = y + (h / num_tubes) * i
            tube_line = QGraphicsLineItem(x + 5, tube_y, x + w - 5, tube_y)
            tube_line.setPen(tube_pen)
            self.scene.addItem(tube_line)

        # 4. Fins/baffles on edges (vertical lines)
        fin_pen = QPen(QColor("#AAAAAA"), 1)
        num_fins = int(w / 15)  # One fin every 15 pixels
        for i in range(num_fins):
            fin_x = x + 10 + (i * 15)
            # Left side fins
            if i < 3:
                fin_line = QGraphicsLineItem(fin_x, y, fin_x, y + h)
                fin_line.setPen(fin_pen)
                self.scene.addItem(fin_line)
            # Right side fins
            if i > num_fins - 4:
                fin_line = QGraphicsLineItem(fin_x, y, fin_x, y + h)
                fin_line.setPen(fin_pen)
                self.scene.addItem(fin_line)

        # 5. Highlight edge (inner white line for 3D effect)
        highlight = QGraphicsRectItem(x + 2, y + 2, w - 4, h - 4)
        highlight.setPen(QPen(QColor(255, 255, 255, 80), 1))
        highlight.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.scene.addItem(highlight)

        # 6. Temperature-based accent (colored glow on top edge)
        if "CONDENSER" in label:
            accent_color = QColor("#FF6B6B")  # Hot red
        else:  # EVAPORATOR
            accent_color = QColor("#4ECDC4")  # Cool cyan

        accent_rect = QGraphicsRectItem(x, y - 2, w, 4)
        accent_rect.setPen(QPen(Qt.PenStyle.NoPen))
        accent_rect.setBrush(QBrush(accent_color))
        self.scene.addItem(accent_rect)

        # 7. State indicator glow (if critical)
        if color == QColor('#dc3545'):  # Red/critical
            glow_rect = QGraphicsRectItem(x - 3, y - 3, w + 6, h + 6)
            glow_rect.setPen(QPen(color, 2))
            glow_rect.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self.scene.addItem(glow_rect)

        # 8. Add label centered with better styling
        text = QGraphicsTextItem(label)
        text.setFont(QFont('Arial', 12, QFont.Weight.Bold))
        text.setDefaultTextColor(QColor('#2C3E50'))
        text_width = text.boundingRect().width()
        text.setPos(x + (w - text_width)/2, y + h/2 - 10)
        self.scene.addItem(text)

    def _draw_compressor(self, x, y, w, h, label, color):
        """Draw a professional compressor with gradients, rotor detail, and shadows."""
        from PyQt6.QtGui import QRadialGradient, QPainterPath
        from PyQt6.QtWidgets import QGraphicsPathItem
        import math

        center_x = x + w / 2
        center_y = y + h / 2

        # 1. Drop shadow (drawn first, behind everything)
        shadow_offset = 4
        shadow = QGraphicsEllipseItem(x + shadow_offset, y + shadow_offset, w, h)
        shadow.setPen(QPen(Qt.PenStyle.NoPen))
        shadow.setBrush(QBrush(QColor(0, 0, 0, 60)))
        self.scene.addItem(shadow)

        # 2. Main body with radial gradient (3D cylindrical effect)
        gradient = QRadialGradient(center_x - w/6, center_y - h/6, max(w, h)/2)
        gradient.setColorAt(0.0, QColor("#F5F5F5"))   # Highlight
        gradient.setColorAt(0.5, QColor("#D8D8D8"))   # Mid-tone
        gradient.setColorAt(0.8, QColor("#B0B0B0"))   # Shadow
        gradient.setColorAt(1.0, QColor("#909090"))   # Dark edge

        ellipse = QGraphicsEllipseItem(x, y, w, h)
        ellipse.setBrush(QBrush(gradient))
        ellipse.setPen(QPen(QColor("#2C3E50"), 3))
        self.scene.addItem(ellipse)

        # 3. Internal rotor blades (curved blades showing rotation)
        rotor_path = QPainterPath()
        num_blades = 4
        blade_length = min(w, h) * 0.3

        for i in range(num_blades):
            angle = (i * 360 / num_blades) * (math.pi / 180)
            # Blade start point (from center)
            start_x = center_x + math.cos(angle) * 5
            start_y = center_y + math.sin(angle) * 5
            # Blade end point
            end_x = center_x + math.cos(angle) * blade_length
            end_y = center_y + math.sin(angle) * blade_length
            # Curved blade (add control point for curve)
            control_x = center_x + math.cos(angle + 0.3) * blade_length * 0.7
            control_y = center_y + math.sin(angle + 0.3) * blade_length * 0.7

            rotor_path.moveTo(start_x, start_y)
            rotor_path.quadTo(control_x, control_y, end_x, end_y)

        rotor_item = QGraphicsPathItem(rotor_path)
        rotor_item.setPen(QPen(QColor("#555555"), 2))
        self.scene.addItem(rotor_item)

        # 4. Center hub (small circle in center)
        hub_radius = 8
        hub = QGraphicsEllipseItem(center_x - hub_radius, center_y - hub_radius,
                                   hub_radius * 2, hub_radius * 2)
        hub_gradient = QRadialGradient(center_x - 3, center_y - 3, hub_radius)
        hub_gradient.setColorAt(0.0, QColor("#C0C0C0"))
        hub_gradient.setColorAt(1.0, QColor("#707070"))
        hub.setBrush(QBrush(hub_gradient))
        hub.setPen(QPen(QColor("#404040"), 1.5))
        self.scene.addItem(hub)

        # 5. Rotation direction arrow (curved arrow)
        arrow_path = QPainterPath()
        arrow_radius = min(w, h) * 0.4
        # Draw arc
        start_angle = 30
        span_angle = 300
        arrow_rect = QRectF(center_x - arrow_radius, center_y - arrow_radius,
                           arrow_radius * 2, arrow_radius * 2)
        arrow_path.arcMoveTo(arrow_rect, start_angle)
        arrow_path.arcTo(arrow_rect, start_angle, span_angle)
        # Add arrow head
        end_angle = (start_angle + span_angle) * (math.pi / 180)
        arrow_end_x = center_x + math.cos(end_angle) * arrow_radius
        arrow_end_y = center_y - math.sin(end_angle) * arrow_radius
        arrow_path.lineTo(arrow_end_x + 5, arrow_end_y - 5)
        arrow_path.moveTo(arrow_end_x, arrow_end_y)
        arrow_path.lineTo(arrow_end_x + 8, arrow_end_y + 2)

        arrow_item = QGraphicsPathItem(arrow_path)
        arrow_item.setPen(QPen(QColor("#3498DB"), 1.5, Qt.PenStyle.DashLine))
        self.scene.addItem(arrow_item)

        # 6. Highlight edge (inner white arc for 3D effect)
        highlight = QGraphicsEllipseItem(x + 3, y + 3, w - 6, h - 6)
        highlight.setPen(QPen(QColor(255, 255, 255, 100), 1.5))
        highlight.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.scene.addItem(highlight)

        # 7. State indicator glow (if critical)
        if color == QColor('#dc3545'):  # Red/critical
            glow = QGraphicsEllipseItem(x - 4, y - 4, w + 8, h + 8)
            glow.setPen(QPen(color, 3))
            glow.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self.scene.addItem(glow)

        # 8. Add label with better styling
        text = QGraphicsTextItem(label)
        text.setFont(QFont('Arial', 11, QFont.Weight.Bold))
        text.setDefaultTextColor(QColor('#2C3E50'))
        text_width = text.boundingRect().width()
        text.setPos(x + (w - text_width)/2, y + h/2 - 10)
        self.scene.addItem(text)

        return ellipse

    def _draw_txv(self, x, y, w, h, label, color):
        """Draw a TXV (triangle/restriction)."""
        rect = QGraphicsRectItem(x, y, w, h)
        rect.setPen(QPen(color, 3))
        rect.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 30)))
        self.scene.addItem(rect)

        # Add label
        text = QGraphicsTextItem(label)
        text.setFont(QFont('Arial', 8, QFont.Weight.Bold))
        text.setPos(x + 5, y + h/2 - 10)
        self.scene.addItem(text)

        return rect

    def _draw_flow_line(self, x1, y1, x2, y2, pen):
        """Draw a flow line between two points."""
        line = QGraphicsLineItem(x1, y1, x2, y2)
        line.setPen(pen)
        self.scene.addItem(line)

    def _add_state_annotation(self, x, y, point_data):
        """Add state annotation text near a flow line."""
        if not point_data:
            return

        p = point_data.get('p')
        t = point_data.get('t')
        sh = point_data.get('sh')
        sc = point_data.get('sc')

        lines = []
        if t is not None:
            lines.append(f"T: {t:.1f}°F")
        if p is not None:
            lines.append(f"P: {p:.1f} PSIG")
        if sh is not None:
            lines.append(f"SH: {sh:.1f}°F")
        if sc is not None:
            lines.append(f"SC: {sc:.1f}°F")

        if lines:
            text = QGraphicsTextItem("\n".join(lines))
            text.setFont(QFont('Arial', 7))
            text.setPos(x, y)
            self.scene.addItem(text)

    def _get_component_state(self, cycle_points, point_id):
        """Get the state classification for a component."""
        if point_id not in cycle_points:
            return ("Unknown", "gray", "UNKNOWN")

        point = cycle_points[point_id]
        sh = point.get('sh')
        sc = point.get('sc')

        return self.extractor.classify_state(sh=sh, sc=sc)

    def _get_state_color(self, color_name):
        """Convert color name to QColor."""
        color_map = {
            'red': QColor('#dc3545'),
            'orange': QColor('#fd7e14'),
            'yellow': QColor('#ffc107'),
            'green': QColor('#28a745'),
            'blue': QColor('#007bff'),
            'gray': QColor('#6c757d')
        }
        return color_map.get(color_name, QColor('#6c757d'))

    def _draw_txv_symbol(self, x, y, w, h):
        """Draw a professional TXV valve symbol with gradient and detail."""
        from PyQt6.QtGui import QPolygonF, QLinearGradient, QPainterPath
        from PyQt6.QtWidgets import QGraphicsPolygonItem, QGraphicsPathItem

        center_x = x + w / 2
        center_y = y + h / 2

        # 1. Drop shadow
        shadow_triangle = QPolygonF([
            QPointF(center_x + 2, y + 2),
            QPointF(x + 2, y + h + 2),
            QPointF(x + w + 2, y + h + 2)
        ])
        shadow_item = QGraphicsPolygonItem(shadow_triangle)
        shadow_item.setPen(QPen(Qt.PenStyle.NoPen))
        shadow_item.setBrush(QBrush(QColor(0, 0, 0, 60)))
        self.scene.addItem(shadow_item)

        # 2. Valve body (rounded rectangle in center)
        body_width = w * 0.6
        body_height = h * 0.7
        body_x = center_x - body_width / 2
        body_y = center_y - body_height / 2

        # Gradient for metallic appearance
        body_gradient = QLinearGradient(body_x, body_y, body_x + body_width, body_y)
        body_gradient.setColorAt(0.0, QColor("#E0E0E0"))
        body_gradient.setColorAt(0.5, QColor("#C8C8C8"))
        body_gradient.setColorAt(1.0, QColor("#A8A8A8"))

        body_rect = QGraphicsRectItem(body_x, body_y, body_width, body_height)
        body_rect.setBrush(QBrush(body_gradient))
        body_rect.setPen(QPen(QColor("#404040"), 2))
        self.scene.addItem(body_rect)

        # 3. Restriction orifice (hourglass shape in center)
        orifice_path = QPainterPath()
        orifice_width = body_width * 0.4
        orifice_height = body_height * 0.8
        orifice_x = center_x - orifice_width / 2
        orifice_y = center_y - orifice_height / 2

        # Top section
        orifice_path.moveTo(orifice_x, orifice_y)
        orifice_path.lineTo(orifice_x + orifice_width, orifice_y)
        # Taper to narrow middle
        orifice_path.lineTo(center_x + orifice_width * 0.15, center_y)
        orifice_path.lineTo(center_x - orifice_width * 0.15, center_y)
        orifice_path.closeSubpath()

        # Bottom section
        orifice_path.moveTo(center_x - orifice_width * 0.15, center_y)
        orifice_path.lineTo(center_x + orifice_width * 0.15, center_y)
        orifice_path.lineTo(orifice_x + orifice_width, orifice_y + orifice_height)
        orifice_path.lineTo(orifice_x, orifice_y + orifice_height)
        orifice_path.closeSubpath()

        orifice_item = QGraphicsPathItem(orifice_path)
        orifice_item.setPen(QPen(QColor("#E74C3C"), 1.5))  # Red for critical component
        orifice_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.scene.addItem(orifice_item)

        # 4. Actuator/capillary tube (small rectangle on top)
        actuator_width = body_width * 0.4
        actuator_height = h * 0.2
        actuator_x = center_x - actuator_width / 2
        actuator_y = body_y - actuator_height - 2

        actuator_gradient = QLinearGradient(actuator_x, actuator_y,
                                           actuator_x, actuator_y + actuator_height)
        actuator_gradient.setColorAt(0.0, QColor("#D4AF37"))  # Brass/gold
        actuator_gradient.setColorAt(1.0, QColor("#B8860B"))

        actuator_rect = QGraphicsRectItem(actuator_x, actuator_y,
                                         actuator_width, actuator_height)
        actuator_rect.setBrush(QBrush(actuator_gradient))
        actuator_rect.setPen(QPen(QColor("#8B6914"), 1.5))
        self.scene.addItem(actuator_rect)

        # 5. Connection line from actuator to valve
        connection = QGraphicsLineItem(center_x, actuator_y + actuator_height,
                                       center_x, body_y)
        connection.setPen(QPen(QColor("#999999"), 1))
        self.scene.addItem(connection)

        # 6. Flow direction arrow (through orifice)
        arrow_path = QPainterPath()
        arrow_start_y = center_y - 12
        arrow_end_y = center_y + 12
        arrow_path.moveTo(center_x, arrow_start_y)
        arrow_path.lineTo(center_x, arrow_end_y)
        # Arrow head
        arrow_path.lineTo(center_x - 4, arrow_end_y - 4)
        arrow_path.moveTo(center_x, arrow_end_y)
        arrow_path.lineTo(center_x + 4, arrow_end_y - 4)

        arrow_item = QGraphicsPathItem(arrow_path)
        arrow_item.setPen(QPen(QColor("#3498DB"), 2))
        self.scene.addItem(arrow_item)

        # 7. Highlight on valve body
        highlight = QGraphicsRectItem(body_x + 1, body_y + 1,
                                     body_width - 2, body_height * 0.3)
        highlight.setPen(QPen(Qt.PenStyle.NoPen))
        highlight.setBrush(QBrush(QColor(255, 255, 255, 60)))
        self.scene.addItem(highlight)

        # 8. Add TXV label with better styling
        text = QGraphicsTextItem("TXV")
        text.setFont(QFont('Arial', 10, QFont.Weight.Bold))
        text.setDefaultTextColor(QColor('#2C3E50'))
        text_width = text.boundingRect().width()
        text.setPos(center_x - text_width/2, y + h + 5)
        self.scene.addItem(text)

    def _add_state_label(self, label, x, y, point_data):
        """Add simple state point label showing only state number and temperature."""
        from PyQt6.QtGui import QLinearGradient

        if not point_data:
            # Still show the label even if no data
            text = QGraphicsTextItem(label)
            text.setFont(QFont('Arial', 10, QFont.Weight.Bold))
            text.setDefaultTextColor(QColor('#2c3e50'))
            text.setPos(x, y)
            self.scene.addItem(text)
            return

        # Get temperature only
        t = point_data.get('t')

        # Build simple label: state number and temperature only
        if t is not None:
            label_text = f"{label}\nT={t:.0f}°F"
        else:
            label_text = label

        text = QGraphicsTextItem(label_text)
        text.setFont(QFont('Arial', 10, QFont.Weight.Bold))
        text.setDefaultTextColor(QColor('#2C3E50'))

        # Calculate dimensions
        bbox = text.boundingRect()
        padding = 3
        box_x = x - padding
        box_y = y - padding
        box_w = bbox.width() + (padding * 2)
        box_h = bbox.height() + (padding * 2)

        # 1. Drop shadow for call-out
        shadow_bg = QGraphicsRectItem(box_x + 2, box_y + 2, box_w, box_h)
        shadow_bg.setPen(QPen(Qt.PenStyle.NoPen))
        shadow_bg.setBrush(QBrush(QColor(0, 0, 0, 40)))
        self.scene.addItem(shadow_bg)

        # 2. Background with subtle gradient
        gradient = QLinearGradient(box_x, box_y, box_x, box_y + box_h)
        gradient.setColorAt(0.0, QColor(255, 255, 255, 250))
        gradient.setColorAt(1.0, QColor(245, 247, 250, 245))

        bg = QGraphicsRectItem(box_x, box_y, box_w, box_h)
        bg.setPen(QPen(QColor('#2C3E50'), 1.5))
        bg.setBrush(QBrush(gradient))
        self.scene.addItem(bg)

        # 3. Accent line on left edge (color-coded by temperature)
        if t is not None:
            if t > 120:
                accent_color = QColor("#E74C3C")  # Hot red
            elif t > 80:
                accent_color = QColor("#F39C12")  # Orange
            elif t > 50:
                accent_color = QColor("#2ECC71")  # Green
            else:
                accent_color = QColor("#3498DB")  # Blue

            accent_line = QGraphicsRectItem(box_x, box_y, 3, box_h)
            accent_line.setPen(QPen(Qt.PenStyle.NoPen))
            accent_line.setBrush(QBrush(accent_color))
            self.scene.addItem(accent_line)

        # 4. Text with better positioning
        text.setPos(x, y)
        self.scene.addItem(text)

    def _draw_arrow(self, x1, y1, x2, y2, pen):
        """Draw an arrow from (x1, y1) to (x2, y2)."""
        from PyQt6.QtWidgets import QGraphicsLineItem
        import math

        # Draw the line
        line = QGraphicsLineItem(x1, y1, x2, y2)
        line.setPen(pen)
        self.scene.addItem(line)

        # Calculate arrow head
        angle = math.atan2(y2 - y1, x2 - x1)
        arrow_size = 8

        # Arrow head points
        p1_x = x2 - arrow_size * math.cos(angle - math.pi / 6)
        p1_y = y2 - arrow_size * math.sin(angle - math.pi / 6)
        p2_x = x2 - arrow_size * math.cos(angle + math.pi / 6)
        p2_y = y2 - arrow_size * math.sin(angle + math.pi / 6)

        # Draw arrow head as polygon
        from PyQt6.QtGui import QPolygonF
        from PyQt6.QtWidgets import QGraphicsPolygonItem

        arrow_head = QPolygonF([
            QPointF(x2, y2),
            QPointF(p1_x, p1_y),
            QPointF(p2_x, p2_y)
        ])

        arrow_item = QGraphicsPolygonItem(arrow_head)
        arrow_item.setPen(pen)
        arrow_item.setBrush(QBrush(pen.color()))
        self.scene.addItem(arrow_item)

    def _draw_warning_summary(self, warnings):
        """Draw warning summary box."""
        box_x, box_y = 10, 10
        box_w, box_h = 200, 100

        # Background
        rect = QGraphicsRectItem(box_x, box_y, box_w, box_h)
        rect.setPen(QPen(QColor('#333333'), 2))
        rect.setBrush(QBrush(QColor(255, 255, 255, 230)))
        self.scene.addItem(rect)

        # Title
        title = QGraphicsTextItem("CYCLE STATE SUMMARY")
        title.setFont(QFont('Arial', 8, QFont.Weight.Bold))
        title.setPos(box_x + 5, box_y + 5)
        self.scene.addItem(title)

        # Warnings
        y_offset = 25
        if not warnings:
            text = QGraphicsTextItem("✓ All states healthy")
            text.setFont(QFont('Arial', 7))
            text.setDefaultTextColor(QColor('#28a745'))
            text.setPos(box_x + 5, box_y + y_offset)
            self.scene.addItem(text)
        else:
            for i, warning in enumerate(warnings[:3]):  # Show max 3 warnings
                severity_icon = "🔴" if warning['severity'] == 'CRITICAL' else "🟡"
                text = QGraphicsTextItem(f"{severity_icon} {warning['location']}")
                text.setFont(QFont('Arial', 7))
                text.setPos(box_x + 5, box_y + y_offset + i * 20)
                self.scene.addItem(text)

                detail = QGraphicsTextItem(f"  {warning['value']}")
                detail.setFont(QFont('Arial', 6))
                detail.setPos(box_x + 10, box_y + y_offset + i * 20 + 12)
                self.scene.addItem(detail)

    def export_diagram(self):
        """Export the process diagram in PNG, PDF, or SVG format."""
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Process Diagram",
            f"process_diagram_{self.current_circuit}.png",
            "PNG Images (*.png);;PDF Files (*.pdf);;SVG Files (*.svg);;All Files (*)"
        )

        if not file_path:
            return  # User cancelled

        try:
            # Determine format from file extension or filter
            file_lower = file_path.lower()

            if file_lower.endswith('.pdf'):
                self._export_as_pdf(file_path)
            elif file_lower.endswith('.svg'):
                self._export_as_svg(file_path)
            else:
                # Default to PNG
                if not file_lower.endswith('.png'):
                    file_path += '.png'
                self._export_as_png(file_path)

            QMessageBox.information(
                self,
                "Export Successful",
                f"Diagram exported to:\n{file_path}"
            )
            print(f"[PROCESS DIAGRAM] Exported to {file_path}")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export diagram:\n{str(e)}"
            )
            print(f"[PROCESS DIAGRAM] Export error: {e}")

    def _export_as_png(self, file_path):
        """Export diagram as high-resolution PNG."""
        # Get scene bounds
        scene_rect = self.scene.sceneRect()

        # Create high-resolution image (300 DPI equivalent)
        from PyQt6.QtGui import QImage
        scale_factor = 3.0  # 3x for high resolution

        image = QImage(
            int(scene_rect.width() * scale_factor),
            int(scene_rect.height() * scale_factor),
            QImage.Format.Format_ARGB32
        )
        image.fill(Qt.GlobalColor.white)

        # Render with anti-aliasing
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.scale(scale_factor, scale_factor)

        self.scene.render(painter)
        painter.end()

        image.save(file_path, "PNG", quality=100)

    def _export_as_pdf(self, file_path):
        """Export diagram as vector PDF."""
        # Get scene bounds
        scene_rect = self.scene.sceneRect()

        # Create printer for PDF
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(file_path)
        printer.setResolution(600)  # 600 DPI for high quality

        # Set page size to fit diagram (landscape orientation for wide diagrams)
        page_size = QPageSize(QSizeF(scene_rect.width() * 0.352778,
                                      scene_rect.height() * 0.352778),
                              QPageSize.Unit.Millimeter)
        printer.setPageSize(page_size)

        # Set minimal margins
        page_layout = QPageLayout(page_size,
                                  QPageLayout.Orientation.Landscape,
                                  QMarginsF(5, 5, 5, 5))
        printer.setPageLayout(page_layout)

        # Render with anti-aliasing
        painter = QPainter(printer)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        self.scene.render(painter)
        painter.end()

    def _export_as_svg(self, file_path):
        """Export diagram as vector SVG."""
        # Get scene bounds
        scene_rect = self.scene.sceneRect()

        # Create SVG generator
        generator = QSvgGenerator()
        generator.setFileName(file_path)
        generator.setSize(scene_rect.size().toSize())
        generator.setViewBox(scene_rect)
        generator.setTitle(f"Process Diagram - {self.current_circuit} Circuit")
        generator.setDescription("Refrigeration process flow diagram")

        # Render with anti-aliasing
        painter = QPainter(generator)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        self.scene.render(painter)
        painter.end()
