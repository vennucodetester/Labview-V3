"""
diagram_widget.py - Interactive Refrigeration Diagram Designer

Complete interactive diagram editor with:
- Drag-and-drop component placement
- Movable, resizable, rotatable components
- Visual pipe connections with waypoints
- Copy/paste functionality
- Property editing with live updates
"""
import uuid
import logging
import math
from collections import deque
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QFileDialog, QFrame, QGraphicsView,
                             QGraphicsScene, QMessageBox, QComboBox, QToolBar,
                             QDockWidget, QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox, QMenu,
                             QGraphicsItem, QGraphicsItemGroup, QGraphicsRectItem, QDialog,
                             QDialogButtonBox, QCheckBox, QApplication, QSplitter)
from PyQt6.QtGui import QPainter, QColor, QPen, QAction, QBrush, QMouseEvent, QPainterPath
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QTimer, QEvent, QRectF
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsEllipseItem, QGraphicsTextItem

from component_schemas import SCHEMAS
from diagram_components import BaseComponentItem, PipeItem, JunctionComponentItem, TXVComponentItem, DistributorComponentItem, SensorBulbComponentItem, SensorComponentItem, FanComponentItem, AirSensorArrayComponentItem, ShelvingGridComponentItem, InstrumentPanelItem, DraggableTextItem, HotGasBypassItem, HotGasLoopItem, RemoteLineEndpointItem, SplitterComponentItem, CombinerComponentItem
import diagram_components as dc_module
from diagnosis_visibility import finding_sort_key, is_diagram_visible_finding
# libavoid_router removed â€” all pipes use explicit routes (see _raw_route in PipeItem)

logger = logging.getLogger(__name__)


class PropertyDialog(QDialog):
    """Property editor dialog for components (opened on double-click)."""
    
    def __init__(self, data_manager, item, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.current_item = item
        self.temp_changes = {}  # Store changes temporarily until OK is clicked
        
        component_data = item.component_data
        self.setWindowTitle(f"Edit {component_data['type']} Properties")
        self.setModal(True)
        self.setMinimumWidth(400)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        
        # Form layout for properties
        self.form_layout = QFormLayout()
        main_layout.addLayout(self.form_layout)
        
        # Populate properties
        self.populate_properties()
        
        # OK/Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept_changes)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
    
    def populate_properties(self):
        """Populate the form with component properties."""
        item = self.current_item
        component_data = item.component_data
        schema = item.schema
        self.property_editors = {}  # Store for Condenser fan_cfm/fan_rpm enable logic

        # Title
        self.form_layout.addRow(QLabel(f"<h3>{component_data['type']}</h3>"))

        # Component properties from schema
        for prop_name, prop_schema in schema.get('properties', {}).items():
            prop_type = prop_schema['type']
            current_value = component_data.get('properties', {}).get(prop_name)

            if prop_type == 'integer':
                editor = QSpinBox()
                editor.setRange(prop_schema.get('min', 0), prop_schema.get('max', 9999))
                editor.setValue(current_value if current_value is not None else prop_schema.get('default', 0))
                editor.valueChanged.connect(lambda val, p=prop_name: self.store_property(p, val))
                label = f"{prop_name} (BTU/hr)" if prop_name == "capacity" else prop_name
                self.form_layout.addRow(QLabel(label), editor)
                self.property_editors[prop_name] = editor
            elif prop_type == 'float':
                editor = QDoubleSpinBox()
                editor.setRange(prop_schema.get('min', 0.0), prop_schema.get('max', 99999.0))
                editor.setValue(current_value if current_value is not None else prop_schema.get('default', 0.0))
                editor.valueChanged.connect(lambda val, p=prop_name: self.store_property(p, val))
                self.form_layout.addRow(QLabel(prop_name), editor)
                self.property_editors[prop_name] = editor
            elif prop_type == 'string':
                editor = QLineEdit()
                editor.setText(current_value or prop_schema.get('default', ''))
                editor.textChanged.connect(lambda val, p=prop_name: self.store_property(p, val))
                self.form_layout.addRow(QLabel(prop_name), editor)
                self.property_editors[prop_name] = editor
            elif prop_type == 'enum':
                editor = QComboBox()
                options = prop_schema.get('options', [])
                # circuit_label: enforce unique Left/Center/Right per component type
                if prop_name == 'circuit_label' and self.data_manager:
                    available = self._filter_circuit_label_options(
                        options, current_value, component_data.get('type'),
                        getattr(self.current_item, 'component_id', None)
                    )
                    editor.addItems(available)
                else:
                    editor.addItems(options)
                if current_value and editor.findText(current_value) >= 0:
                    editor.setCurrentText(current_value)
                elif options and editor.count() > 0:
                    editor.setCurrentIndex(0)
                editor.currentTextChanged.connect(lambda val, p=prop_name: self.store_property(p, val))
                label = "Flip" if prop_name == "flip" else prop_name
                self.form_layout.addRow(QLabel(label), editor)
                self.property_editors[prop_name] = editor

        # Condenser: grey out fan_cfm and fan_rpm when Water Cooled (so user cannot enter values)
        if component_data.get('type') == 'Condenser':
            ct_combo = self.property_editors.get('condenser_type')
            fan_cfm = self.property_editors.get('fan_cfm')
            fan_rpm = self.property_editors.get('fan_rpm')
            if ct_combo is not None and fan_cfm is not None and fan_rpm is not None:
                def update_fan_enabled():
                    is_air = ct_combo.currentText() == 'Air Cooled'
                    fan_cfm.setEnabled(is_air)
                    fan_rpm.setEnabled(is_air)
                ct_combo.currentTextChanged.connect(update_fan_enabled)
                update_fan_enabled()  # apply initial state
        
        # Rotation control
        rotate_btn = QPushButton("ðŸ”„ Rotate 90Â°")
        rotate_btn.clicked.connect(self.rotate_component)
        self.form_layout.addRow(rotate_btn)

        # Size controls - only for box-type components
        if not isinstance(item, (JunctionComponentItem, TXVComponentItem, DistributorComponentItem,
                                SensorBulbComponentItem, FanComponentItem, AirSensorArrayComponentItem,
                                ShelvingGridComponentItem)):
            size = component_data.get('size', {'width': 100, 'height': 60})
            width_spin = QSpinBox()
            width_spin.setRange(50, 500)
            width_spin.setValue(size['width'])
            width_spin.valueChanged.connect(lambda val: self.store_size(val, None))
            self.form_layout.addRow(QLabel("Width"), width_spin)
            height_spin = QSpinBox()
            height_spin.setRange(30, 300)
            height_spin.setValue(size['height'])
            height_spin.valueChanged.connect(lambda val: self.store_size(None, val))
            self.form_layout.addRow(QLabel("Height"), height_spin)

        # Special size controls for AirSensorArray
        if isinstance(item, AirSensorArrayComponentItem):
            block_width = component_data.get('properties', {}).get('block_width', 400)
            block_height = component_data.get('properties', {}).get('block_height', 25)
            width_spin = QSpinBox()
            width_spin.setRange(150, 2000)
            width_spin.setValue(block_width)
            width_spin.valueChanged.connect(lambda val: self.store_property('block_width', val))
            self.form_layout.addRow(QLabel("Block Width"), width_spin)
            height_spin = QSpinBox()
            height_spin.setRange(15, 50)
            height_spin.setValue(block_height)
            height_spin.valueChanged.connect(lambda val: self.store_property('block_height', val))
            self.form_layout.addRow(QLabel("Block Height"), height_spin)

        # Special size controls for ShelvingGrid
        if isinstance(item, ShelvingGridComponentItem):
            shelf_width = component_data.get('properties', {}).get('shelf_width', 100)
            shelf_height = component_data.get('properties', {}).get('shelf_height', 60)
            row_gap = component_data.get('properties', {}).get('row_gap', 20)
            width_spin = QSpinBox()
            width_spin.setRange(50, 300)
            width_spin.setValue(shelf_width)
            width_spin.valueChanged.connect(lambda val: self.store_property('shelf_width', val))
            self.form_layout.addRow(QLabel("Shelf Width"), width_spin)
            height_spin = QSpinBox()
            height_spin.setRange(30, 150)
            height_spin.setValue(shelf_height)
            height_spin.valueChanged.connect(lambda val: self.store_property('shelf_height', val))
            self.form_layout.addRow(QLabel("Shelf Height"), height_spin)
            gap_spin = QSpinBox()
            gap_spin.setRange(0, 100)
            gap_spin.setValue(row_gap)
            gap_spin.valueChanged.connect(lambda val: self.store_property('row_gap', val))
            self.form_layout.addRow(QLabel("Row Gap"), gap_spin)

    def _filter_circuit_label_options(self, options, current_value, comp_type, comp_id):
        """Filter circuit_label options so only one component per type can have Left/Center/Right.
        Returns list of available options (always includes 'None' and current value if set).
        """
        if not options or not self.data_manager:
            return options
        model = self.data_manager.diagram_model or {}
        components = model.get('components', {}) or {}
        taken = set()
        for cid, c in components.items():
            if cid != comp_id and c.get('type') == comp_type:
                lbl = (c.get('properties') or {}).get('circuit_label')
                if lbl and lbl in ('Left', 'Center', 'Right'):
                    taken.add(lbl)
        # Available: None always; Left/Center/Right only if not taken OR if this component has it
        available = [
            o for o in options
            if o == 'None' or o not in taken or o == current_value
        ]
        return available if available else options

    def store_property(self, prop_name, value):
        """Store property change temporarily (applied on OK)."""
        if 'properties' not in self.temp_changes:
            self.temp_changes['properties'] = {}
        self.temp_changes['properties'][prop_name] = value
    
    def store_size(self, width, height):
        """Store size change temporarily."""
        if 'size' not in self.temp_changes:
            current_size = self.current_item.component_data.get('size', {'width': 100, 'height': 60})
            self.temp_changes['size'] = current_size.copy()
        
        if width is not None:
            self.temp_changes['size']['width'] = width
        if height is not None:
            self.temp_changes['size']['height'] = height
    
    def rotate_component(self):
        """Store rotation change temporarily."""
        current_rotation = self.current_item.component_data.get('rotation', 0)
        new_rotation = (current_rotation + 90) % 360
        self.temp_changes['rotation'] = new_rotation
        
        # Show immediate visual feedback
        self.current_item.setRotation(new_rotation)
    
    def accept_changes(self):
        """Apply all changes and close dialog."""
        # Apply properties
        if 'properties' in self.temp_changes:
            if 'properties' not in self.current_item.component_data:
                self.current_item.component_data['properties'] = {}
            self.current_item.component_data['properties'].update(self.temp_changes['properties'])
        
        # Apply size
        if 'size' in self.temp_changes:
            self.current_item.component_data['size'] = self.temp_changes['size']
            self.current_item.update_size(self.temp_changes['size']['width'], 
                                         self.temp_changes['size']['height'])
        
        # Apply rotation
        if 'rotation' in self.temp_changes:
            self.current_item.component_data['rotation'] = self.temp_changes['rotation']
        
        # Rebuild ports to reflect changes
        self.current_item.rebuild_ports()
        
        print(f"[PROPERTY DIALOG] Changes applied to {self.current_item.component_data['type']}")
        self.accept()
    
    def reject(self):
        """Discard changes and close dialog."""
        # Revert rotation if it was changed
        if 'rotation' in self.temp_changes:
            original_rotation = self.current_item.component_data.get('rotation', 0)
            self.current_item.setRotation(original_rotation)
        
        print(f"[PROPERTY DIALOG] Changes discarded")
        super().reject()


# Keep PropertyEditor as an alias for backwards compatibility (will be removed later)
PropertyEditor = PropertyDialog


# ---------------------------------------------------------------------------
# Topology Preview Dialog â€” interactive loop preview before diagram generation
# ---------------------------------------------------------------------------

def _tpd_draw_box(scene, title, x, y, w, h):
    path = QPainterPath()
    path.addRect(0, 0, w, h)
    item = QGraphicsPathItem(path)
    item.setPos(x, y)
    item.setBrush(QBrush(QColor('#222222')))
    item.setPen(QPen(QColor('#4DA6FF'), 2))
    lbl = QGraphicsTextItem(title, item)
    lbl.setDefaultTextColor(QColor('#FFFFFF'))
    lbl.setPos(6, 6)
    scene.addItem(item)
    return item


def _tpd_draw_pipe(scene, pts):
    path = QPainterPath()
    path.moveTo(QPointF(*pts[0]))
    for pt in pts[1:]:
        path.lineTo(QPointF(*pt))
    pipe = QGraphicsPathItem(path)
    pipe.setPen(QPen(QColor('#888888'), 2))
    pipe.setZValue(-1)
    scene.addItem(pipe)


def _tpd_build_scene(scene, num_modules, num_circuits):
    scene.clear()

    CENTER_X   = 600
    MOD_SPACING = 300
    COMP_W, COMP_H = 120, 60
    COND_W, COND_H = 120, 60
    TXV_W,  TXV_H  = 120, 60
    EVAP_W, EVAP_H = 240, 80

    Y_COMP  = 100
    Y_COND  = 200
    Y_TXV   = 330
    Y_EVAP  = 430
    BRANCH_Y  = Y_COND + COND_H + 30
    CKT_IN_Y  = Y_TXV  + TXV_H  + 20
    CKT_OUT_Y = Y_EVAP + EVAP_H + 20
    MERGE_Y   = Y_EVAP + EVAP_H + 55

    if num_modules == 1:
        mod_xs  = [CENTER_X]
        mod_lbs = [""]
    elif num_modules == 2:
        mod_xs  = [CENTER_X - MOD_SPACING // 2, CENTER_X + MOD_SPACING // 2]
        mod_lbs = ["LH", "RH"]
    else:
        mod_xs  = [CENTER_X - MOD_SPACING, CENTER_X, CENTER_X + MOD_SPACING]
        mod_lbs = ["LH", "CTR", "RH"]

    LEFTMOST = mod_xs[0] - 200

    # Shared: Compressor + Condenser
    _tpd_draw_box(scene, "[Compressor]",
                  CENTER_X - COMP_W // 2, Y_COMP, COMP_W, COMP_H)
    _tpd_draw_box(scene, "[Condenser]",
                  CENTER_X - COND_W // 2, Y_COND, COND_W, COND_H)
    _tpd_draw_pipe(scene, [[CENTER_X, Y_COMP + COMP_H], [CENTER_X, Y_COND]])

    cond_out = [CENTER_X, Y_COND + COND_H]

    # Evaporator circuit x-positions (evenly spaced)
    import math
    def _snap(v): return math.floor(v / 20 + 0.5) * 20
    span = (num_circuits - 1) * 20 if num_circuits > 1 else 0
    ckt_local_xs = [_snap(EVAP_W / 2 + (i - 1) * 20 - span / 2)
                    for i in range(1, num_circuits + 1)]

    mod_evap_outlets = []

    for mod_x, lb in zip(mod_xs, mod_lbs):
        lp = f"[{lb} " if lb else "["
        evap_left = mod_x - EVAP_W // 2

        _tpd_draw_box(scene, f"{lp}TXV]",
                      mod_x - TXV_W // 2, Y_TXV, TXV_W, TXV_H)
        _tpd_draw_box(scene, f"{lp}Evaporator]",
                      evap_left, Y_EVAP, EVAP_W, EVAP_H)

        # cond â†’ TXV
        _tpd_draw_pipe(scene, [cond_out,
                                [CENTER_X, BRANCH_Y],
                                [mod_x,    BRANCH_Y],
                                [mod_x,    Y_TXV]])

        txv_out = [mod_x, Y_TXV + TXV_H]

        # TXV â†’ each circuit inlet
        for lx in ckt_local_xs:
            cx = int(evap_left + lx)
            _tpd_draw_pipe(scene, [txv_out,
                                   [mod_x, CKT_IN_Y],
                                   [cx,    CKT_IN_Y],
                                   [cx,    Y_EVAP]])

        # Each circuit outlet â†’ module merge point
        mod_merge = [mod_x, CKT_OUT_Y]
        for lx in ckt_local_xs:
            cx = int(evap_left + lx)
            _tpd_draw_pipe(scene, [[cx, Y_EVAP + EVAP_H],
                                   [cx, CKT_OUT_Y],
                                   [mod_x, CKT_OUT_Y]])

        mod_evap_outlets.append(mod_merge)

    # Collect module outlets â†’ loopback
    merge_pt = [CENTER_X, MERGE_Y]
    for evap_out in mod_evap_outlets:
        _tpd_draw_pipe(scene, [evap_out,
                                [evap_out[0], MERGE_Y],
                                [CENTER_X,    MERGE_Y]])

    # Loopback to compressor inlet
    _tpd_draw_pipe(scene, [merge_pt,
                            [CENTER_X, MERGE_Y + 30],
                            [LEFTMOST, MERGE_Y + 30],
                            [LEFTMOST, Y_COMP - 30],
                            [CENTER_X, Y_COMP - 30],
                            [CENTER_X, Y_COMP]])


class DiagramWidget(QWidget):
    """Interactive diagram designer widget."""
    
    # Signal emitted when a sensor port is clicked (sensor_name)
    sensor_port_clicked = pyqtSignal(str)
    mapping_report_requested = pyqtSignal()
    
    def __init__(self, data_manager):
        super().__init__()
        self.data_manager = data_manager
        self.component_items = {}
        self.pipe_items = {}
        self.sensor_boxes = {}  # Track sensor boxes
        self.overlay_items = []  # Mapping mode overlay items
        self.dot_items = {}  # role_key -> visible sensor dot item
        self._diagnostic_findings = []
        self._diagnostic_overlay_items = []
        self._processed_means = None  # column means from last Calculations run (state overlay)
        self._processed_df = None
        
        self.current_tool = None
        self.pipe_mode = False
        self.pipe_start_port = None
        self.custom_sensor_mode = None  # For custom sensor placement
        self.sensor_box_mode = False  # For sensor box placement
        
        self.clipboard_components = []
        self.property_editor = None  # Will be set by MainWindow
        
        # Group management - simpler approach
        self.groups = {}  # group_id -> list of component_ids
        self.next_group_id = 1
        
        # Custom sensor points tracking
        self.custom_sensor_points = {}  # sensor_id -> {type, position, label}
        self._last_reveal_unmapped_candidates = False
        self._sensor_dot_relayout_timer = QTimer(self)
        self._sensor_dot_relayout_timer.setSingleShot(True)
        self._sensor_dot_relayout_timer.timeout.connect(self._refresh_sensor_dot_layout_for_zoom)
        
        self.setupUi()
        self.connect_signals()

    def update_ui(self):
        """Update the diagram when data changes (e.g., sensor mappings)."""
        try:
            print("[DIAGRAM] update_ui() called - rebuilding scene")
            self.build_scene_from_model()
            print("[DIAGRAM] Scene rebuilt")
        except Exception as e:
            logger.exception("[DIAGRAM] update_ui failed")
            try:
                self._show_render_error_banner(f"Diagram failed to update: {e}")
            except Exception:
                logger.exception("[DIAGRAM] failed to show render error banner")
    
    def on_sensor_port_clicked(self, port_item):
        """Handle clicks on sensor ports - map selected sensor if unmapped, or emit signal if mapped."""
        component = port_item.parent_component
        comp_type = component.component_data.get('type', '')
        component_id = component.component_id
        port_name = port_item.port_name

        # Role key must match format used when building scene: CompType.comp_id.port_name
        role_key = f"{comp_type}.{component_id}.{port_name}"
        mapped_sensor = self.data_manager.get_mapped_sensor_for_role(role_key)

        if mapped_sensor:
            print(f"[SENSOR PORT CLICK] Sensor port clicked: {role_key} -> {mapped_sensor}")
            self.sensor_port_clicked.emit(mapped_sensor)
        else:
            # Unmapped: if a sensor is selected, map it (same as role dot behavior)
            selected = list(self.data_manager.selected_sensors)
            if selected:
                sensor_name = selected[-1]
                print(f"[MAP] Port click: mapping {sensor_name} to {role_key}")
                self.data_manager.map_sensor_to_role(role_key, sensor_name)
                self.update_sensor_dots()
                print(f"[MAP] Successfully mapped {sensor_name} to {role_key}")
            else:
                print(f"[SENSOR PORT CLICK] Sensor port clicked but not mapped: {role_key}")
    
    def setupUi(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Toolbar
        self.toolbar = QToolBar("Component Palette")
        main_layout.addWidget(self.toolbar)
        self.populate_toolbar()
        
        # Scene
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        
        # IMPROVED: Better rendering quality for clarity
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.view.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self.view.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, False)
        
        # IMPROVED: Cleaner grid background like simplified version
        self.view.setStyleSheet("""
            QGraphicsView {
                background: qlineargradient(x1:0, y1:0, x2:20, y2:20,
                    stop:0 #f5f5f5, stop:0.05 #f5f5f5,
                    stop:0.05 #e0e0e0, stop:0.1 #e0e0e0,
                    stop:0.1 #f5f5f5);
                background-repeat: repeat;
                border: none;
            }
        """)
        
        # Enable rubber band selection (drag to select)
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        
        # Enable zoom functionality with mouse wheel
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.view.wheelEvent = self.view_wheel_event
        self.view.mouseReleaseEvent = self.view_mouse_release_event
        self.zoom_factor = 1.0
        
        # Track panning mode
        self.is_panning = False
        
        self.analysis_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.analysis_splitter.addWidget(self.view)
        self.cycle_panel = self._create_cycle_panel()
        self.cycle_panel.setVisible(False)
        self.analysis_splitter.addWidget(self.cycle_panel)
        self.analysis_splitter.setStretchFactor(0, 3)
        self.analysis_splitter.setStretchFactor(1, 1)
        self.analysis_splitter.setSizes([1100, 420])

        main_layout.addWidget(self.analysis_splitter)
        
        self.setAcceptDrops(True)

    def _create_cycle_panel(self):
        panel = QFrame(self)
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        panel.setMinimumWidth(360)
        panel.setStyleSheet("QFrame{background:#ffffff;border-left:1px solid #d0d7de;}")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("Cycle (P-h)")
        title.setStyleSheet("font-weight:bold;color:#1f2933;")
        header.addWidget(title)
        header.addStretch()
        collapse = QPushButton("Collapse")
        collapse.setFixedHeight(24)
        collapse.clicked.connect(lambda: self.analysis_checkbox.setChecked(False))
        header.addWidget(collapse)
        layout.addLayout(header)

        try:
            from ph_diagram_widget import CycleDomeWidget
            self.ph_diagram_widget = CycleDomeWidget(self.data_manager)
            layout.addWidget(self.ph_diagram_widget, 1)
        except Exception as exc:
            self.ph_diagram_widget = None
            msg = QLabel(f"P-h view failed to initialize: {exc}")
            msg.setWordWrap(True)
            msg.setStyleSheet("color:#8a1f11;background:#fff4e5;padding:8px;")
            layout.addWidget(msg, 1)
            logger.exception("[DIAGRAM] Failed to initialize P-h cycle panel")
        return panel
        
    def populate_toolbar(self):
        """Populate toolbar with mapping-first controls."""
        self._drawing_only_widgets = []
        self._drawing_only_actions = []

        self.edit_layout_checkbox = QCheckBox("Edit layout")
        self.edit_layout_checkbox.setToolTip("Enable component movement and diagram authoring tools")
        self.edit_layout_checkbox.toggled.connect(self._on_edit_layout_toggled)
        self.toolbar.addWidget(self.edit_layout_checkbox)

        self.analysis_checkbox = QCheckBox("Analysis")
        self.analysis_checkbox.setToolTip("Show calculated state overlays when calculation results exist")
        self.analysis_checkbox.toggled.connect(self._on_analysis_toggled)
        self.toolbar.addWidget(self.analysis_checkbox)

        self.toolbar.addSeparator()

        # Components dropdown menu
        components_btn = QPushButton("ðŸ“¦ Components")
        components_menu = QMenu(self)
        
        essential_components = [
            "Compressor",
            "Condenser",
            "Evaporator",
            "TXV",
            "FilterDrier",
            "Distributor",
            "Junction",
            "HotGasBypassValve",
            "HotGasLoop",
            "Sensor",
            "Fan",
            "AirSensorArray",
            "ShelvingGrid"
        ]
        
        for comp_type in essential_components:
            if comp_type in SCHEMAS:
                action = components_menu.addAction(comp_type)
                action.triggered.connect(lambda checked, t=comp_type: self.set_tool(t))
        
        components_btn.setMenu(components_menu)
        components_action = self.toolbar.addWidget(components_btn)
        self._drawing_only_widgets.append(components_btn)
        self._drawing_only_actions.append(components_action)
        
        sep_components = self.toolbar.addSeparator()
        self._drawing_only_actions.append(sep_components)
        
        # Edit dropdown menu
        edit_btn = QPushButton("âœï¸ Edit")
        edit_menu = QMenu(self)
        
        # Group action
        group_action = edit_menu.addAction("Group (Ctrl+G)")
        group_action.triggered.connect(self.group_selection)
        
        # Ungroup action
        ungroup_action = edit_menu.addAction("Ungroup (Ctrl+Shift+G)")
        ungroup_action.triggered.connect(self.ungroup_selection)
        
        edit_menu.addSeparator()
        
        # Zoom to fit action
        zoom_fit_action = edit_menu.addAction("Zoom to Fit Width")
        zoom_fit_action.triggered.connect(self.zoom_to_fit)
        zoom_fit_all_action = edit_menu.addAction("Fit Everything")
        zoom_fit_all_action.triggered.connect(lambda: self.zoom_to_fit(full=True))
        
        edit_menu.addSeparator()
        
        # Add sensor box action
        add_box_action = edit_menu.addAction("Add Sensor Box")
        add_box_action.triggered.connect(self.set_sensor_box_tool)
        
        edit_menu.addSeparator()
        
        # Clear sensor mappings action
        clear_mappings_action = edit_menu.addAction("Clear All Sensor Mappings")
        clear_mappings_action.triggered.connect(self.clear_all_sensor_mappings)

        edit_menu.addSeparator()

        # Delete old custom sensors action
        delete_custom_action = edit_menu.addAction("Delete All Custom Sensors")
        delete_custom_action.triggered.connect(self._delete_all_custom_sensors)

        edit_btn.setMenu(edit_menu)
        edit_action = self.toolbar.addWidget(edit_btn)
        self._drawing_only_widgets.append(edit_btn)
        self._drawing_only_actions.append(edit_action)
        
        sep_edit = self.toolbar.addSeparator()
        self._drawing_only_actions.append(sep_edit)

        self.toolbar.addSeparator()

        zoom_fit_btn = QPushButton("Zoom to Fit")
        zoom_fit_btn.setToolTip("Fit page width; Ctrl-click fits everything")
        zoom_fit_btn.clicked.connect(self.zoom_to_fit)
        self.toolbar.addWidget(zoom_fit_btn)

        self.toolbar.addSeparator()

        mapping_report_btn = QPushButton("Mapping report...")
        mapping_report_btn.setToolTip("Open the CSV-to-diagram mapping report")
        mapping_report_btn.clicked.connect(self.mapping_report_requested.emit)
        self.toolbar.addWidget(mapping_report_btn)

        self.toolbar.addSeparator()

        # Grid snap toggle
        self.snap_checkbox = QCheckBox("Snap to Grid")
        self.snap_checkbox.setChecked(False)
        self.snap_checkbox.toggled.connect(self._on_snap_toggled)
        snap_action = self.toolbar.addWidget(self.snap_checkbox)
        self._drawing_only_widgets.append(self.snap_checkbox)
        self._drawing_only_actions.append(snap_action)

        # Straighten pipes button
        straighten_btn = QPushButton("Straighten Pipes")
        straighten_btn.setToolTip("Straighten selected pipes (Ctrl+L) â€” removes micro-staircases")
        straighten_btn.clicked.connect(self._straighten_selected_pipes)
        straighten_action = self.toolbar.addWidget(straighten_btn)
        self._drawing_only_widgets.append(straighten_btn)
        self._drawing_only_actions.append(straighten_action)

        # Align ports button
        align_btn = QPushButton("Align Ports")
        align_btn.setToolTip("Nudge components so connected ports line up â€” "
                             "makes pipes render as straight 90Â° runs")
        align_btn.clicked.connect(self._align_connected_components)
        align_action = self.toolbar.addWidget(align_btn)
        self._drawing_only_widgets.append(align_btn)
        self._drawing_only_actions.append(align_action)

        self._sync_edit_layout_controls()

    def _edit_layout_enabled(self):
        return bool(getattr(self, "edit_layout_checkbox", None)
                    and self.edit_layout_checkbox.isChecked())

    def _analysis_enabled(self):
        return bool(getattr(self, "analysis_checkbox", None)
                    and self.analysis_checkbox.isChecked())

    def _sync_edit_layout_controls(self):
        edit_enabled = self._edit_layout_enabled()
        for action in getattr(self, "_drawing_only_actions", []):
            action.setVisible(edit_enabled)
        for item in getattr(self, "_drawing_only_widgets", []):
            item.setVisible(edit_enabled)

    def _on_edit_layout_toggled(self, checked):
        self._sync_edit_layout_controls()
        if not checked:
            self.current_tool = None
            self.custom_sensor_mode = None
            self.sensor_box_mode = False
            if self.pipe_start_port is not None:
                try:
                    self.pipe_start_port.setScale(1.0)
                except RuntimeError:
                    pass
                self.pipe_start_port = None
        self.apply_interaction_mode()

    def _on_analysis_toggled(self, checked):
        self._sync_cycle_panel()
        self.build_scene_from_model()

    def _sync_cycle_panel(self):
        panel = getattr(self, 'cycle_panel', None)
        if panel is None:
            return
        enabled = self._analysis_enabled()
        panel.setVisible(enabled)
        if enabled and self._processed_df is not None and getattr(self, 'ph_diagram_widget', None):
            try:
                self.ph_diagram_widget.load_filtered_data(self._processed_df)
            except Exception:
                logger.exception("[DIAGRAM] Failed to load data into P-h cycle panel")

    def _show_sensor_point_menu(self, event, role_key, currently_enabled=True):
        """Right-click context menu on a sensor dot â€” enable/disable this spot or groups."""
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction

        # Parse role_key to get comp_type, comp_id, port
        parts = role_key.split('.')
        comp_type = parts[0] if parts else ''
        comp_id   = parts[1] if len(parts) > 1 else ''
        comp      = self.data_manager.diagram_model.get('components', {}).get(comp_id, {})
        clbl      = (comp.get('properties') or {}).get('circuit_label', '') or ''
        if clbl == 'None':
            clbl = ''

        menu = QMenu(self.view)

        # Toggle this single spot
        if currently_enabled:
            act_toggle = QAction("Disable this spot", menu)
            act_toggle.triggered.connect(lambda: self._toggle_sensor_point(role_key, False))
        else:
            act_toggle = QAction("Enable this spot", menu)
            act_toggle.triggered.connect(lambda: self._toggle_sensor_point(role_key, True))
        menu.addAction(act_toggle)

        menu.addSeparator()

        # Group: all of same type
        if comp_type:
            act_type_off = QAction(f"Disable all [{comp_type}]", menu)
            act_type_off.triggered.connect(
                lambda: self._bulk_sensor_points(comp_type=comp_type, enabled=False))
            menu.addAction(act_type_off)

            act_type_on = QAction(f"Enable all [{comp_type}]", menu)
            act_type_on.triggered.connect(
                lambda: self._bulk_sensor_points(comp_type=comp_type, enabled=True))
            menu.addAction(act_type_on)

        # Group: all of same circuit
        if clbl:
            menu.addSeparator()
            act_cir_off = QAction(f"Disable all [{clbl} circuit]", menu)
            act_cir_off.triggered.connect(
                lambda: self._bulk_sensor_points(circuit_label=clbl, enabled=False))
            menu.addAction(act_cir_off)

            act_cir_on = QAction(f"Enable all [{clbl} circuit]", menu)
            act_cir_on.triggered.connect(
                lambda: self._bulk_sensor_points(circuit_label=clbl, enabled=True))
            menu.addAction(act_cir_on)

        menu.addSeparator()

        act_all_on  = QAction("Enable ALL spots", menu)
        act_all_on.triggered.connect(lambda: self._bulk_sensor_points(enabled=True))
        menu.addAction(act_all_on)

        act_all_off = QAction("Disable ALL spots", menu)
        act_all_off.triggered.connect(lambda: self._bulk_sensor_points(enabled=False))
        menu.addAction(act_all_off)

        # Unmap option (only when enabled + mapped)
        if currently_enabled:
            current_mapping = self.data_manager.get_mapped_sensor_for_role(role_key)
            if current_mapping:
                menu.addSeparator()
                act_unmap = QAction(f"Unmap [{current_mapping}]", menu)
                act_unmap.triggered.connect(
                    lambda: self._do_unmap(role_key, current_mapping))
                menu.addAction(act_unmap)

        # Show near cursor
        view_pos = self.view.mapFromScene(event.scenePos())
        global_pos = self.view.mapToGlobal(view_pos)
        menu.exec(global_pos)

    def _toggle_sensor_point(self, role_key, enabled):
        self.data_manager.set_sensor_point_enabled(role_key, enabled)
        self.build_scene_from_model()

    def _bulk_sensor_points(self, comp_type=None, circuit_label=None, enabled=True):
        self.data_manager.set_sensor_points_enabled_by(
            comp_type=comp_type, circuit_label=circuit_label, enabled=enabled)
        self.build_scene_from_model()

    def _do_unmap(self, role_key, sensor_name):
        self.data_manager.unmap_role(role_key)
        self.build_scene_from_model()
        print(f"[UNMAP] Unmapped {sensor_name} from {role_key}")

    # Components that should never be nudged by Align Ports (anchors)
    _ALIGN_FIXED_TYPES = {'Evaporator', 'Condenser', 'Compressor',
                          'ShelvingGrid', 'AirSensorArray'}
    _ALIGN_MAX_NUDGE = 20  # px â€” bigger offsets are treated as intentional

    def _align_connected_components(self):
        """Nudge the smaller of two pipe-connected components so the two
        ports line up exactly, letting the pipe render perfectly straight.
        Each component is moved at most once per pass."""
        moved = set()
        nudges = 0
        for pipe in self.pipe_items.values():
            sp, ep = pipe.start_port_item, pipe.end_port_item
            s_comp = getattr(sp, 'parent_component', None)
            e_comp = getattr(ep, 'parent_component', None)
            if s_comp is None or e_comp is None or s_comp is e_comp:
                continue
            s_pos, e_pos = sp.get_scene_position(), ep.get_scene_position()
            sv = pipe._get_port_exit_vector(sp)
            ev = pipe._get_port_exit_vector(ep)
            dx, dy = e_pos.x() - s_pos.x(), e_pos.y() - s_pos.y()
            s_h = abs(sv.x()) > abs(sv.y())
            e_h = abs(ev.x()) > abs(ev.y())
            if (s_h and e_h and sv.x() * dx > 0 and ev.x() * dx < 0
                    and 0 < abs(dy) <= self._ALIGN_MAX_NUDGE):
                offset = QPointF(0, dy)   # facing horizontally, level them
            elif ((not s_h) and (not e_h) and sv.y() * dy > 0 and ev.y() * dy < 0
                    and 0 < abs(dx) <= self._ALIGN_MAX_NUDGE):
                offset = QPointF(dx, 0)   # facing vertically, center them
            else:
                continue
            target = self._pick_alignment_target(s_comp, e_comp)
            if target is None or target.component_id in moved:
                continue
            sign = 1 if target is s_comp else -1
            target.setPos(target.pos() + offset * sign)
            moved.add(target.component_id)
            nudges += 1
        print(f"[ALIGN] Nudged {nudges} component(s) to align ports")

    def _pick_alignment_target(self, a, b):
        """Pick which of two components to nudge: never an anchor type if
        avoidable, otherwise the one with the smaller footprint."""
        a_fixed = (a.component_data or {}).get('type') in self._ALIGN_FIXED_TYPES
        b_fixed = (b.component_data or {}).get('type') in self._ALIGN_FIXED_TYPES
        if a_fixed and b_fixed:
            return None
        if a_fixed:
            return b
        if b_fixed:
            return a
        try:
            a_area = a.boundingRect().width() * a.boundingRect().height()
            b_area = b.boundingRect().width() * b.boundingRect().height()
            return a if a_area <= b_area else b
        except Exception:
            return a

    def _straighten_selected_pipes(self):
        """Straighten selected pipes, or all pipes if none selected."""
        selected = [item for item in self.scene.selectedItems()
                    if isinstance(item, PipeItem)]
        if not selected:
            selected = list(self.pipe_items.values())
        count = 0
        for pipe in selected:
            pipe.straighten_waypoints()
            count += 1
        print(f"[STRAIGHTEN] Processed {count} pipe(s)")

    def _on_snap_toggled(self, checked):
        """Toggle grid snapping on/off."""
        dc_module._grid_snap_enabled = checked
        print(f"[SNAP] Grid snap {'enabled' if checked else 'disabled'}")

    def set_tool(self, tool_name):
        """Set the active placement tool."""
        if not self._edit_layout_enabled():
            self.edit_layout_checkbox.setChecked(True)
        self.current_tool = tool_name
        self.pipe_mode = False
        self.custom_sensor_mode = None
        self.sensor_box_mode = False
        print(f"[TOOL] Set to {tool_name}")
    
    def set_custom_sensor_tool(self, sensor_type):
        """Set custom sensor placement mode."""
        if not self._edit_layout_enabled():
            self.edit_layout_checkbox.setChecked(True)
        self.custom_sensor_mode = sensor_type
        self.current_tool = None
        self.pipe_mode = False
        print(f"[TOOL] Custom sensor mode: {sensor_type} - Click to place")
    
    def set_sensor_box_tool(self):
        """Set sensor box placement mode."""
        if not self._edit_layout_enabled():
            self.edit_layout_checkbox.setChecked(True)
        self.sensor_box_mode = True
        self.current_tool = None
        self.pipe_mode = False
        self.custom_sensor_mode = None
        print(f"[TOOL] Sensor box mode - Click to place box")
    
    def clear_all_sensor_mappings(self):
        """Clear all sensor mappings and refresh the display."""
        self.data_manager.clear_all_sensor_mappings()
        print("[TOOL] All sensor mappings cleared - all sensors now appear orange (unmapped)")
    
    def connect_signals(self):
        self.data_manager.diagram_model_changed.connect(self.build_scene_from_model)
        self.data_manager.data_changed.connect(self.on_data_changed)
        if hasattr(self.data_manager, 'selection_changed'):
            self.data_manager.selection_changed.connect(self.update_sensor_highlighting)
        # Connect new lightweight update signal
        if hasattr(self.data_manager, 'sensor_mapping_changed'):
            self.data_manager.sensor_mapping_changed.connect(self.on_sensor_mapping_changed)
        self.scene.selectionChanged.connect(self.on_scene_selection_changed)
        self.view.mousePressEvent = self.view_mouse_press_event
    
    def on_aggregation_changed(self, aggregation):
        """Handle aggregation method selection change."""
        print(f"[AGGREGATION] Changed to: {aggregation}")
        self.data_manager.set_value_aggregation(aggregation)
        # Note: set_value_aggregation already emits data_changed, which will trigger updates everywhere
        # But we also explicitly update sensor dots to ensure immediate visual feedback
        self.update_sensor_dots()
    
    def on_data_changed(self):
        """Handle data changes, particularly sensor selection changes."""
        # Update sensor highlighting in the diagram
        self.update_sensor_highlighting()
        # Also update sensor dot values when data changes (time range, aggregation, etc.)
        self.update_sensor_dots()
    
    def update_sensor_highlighting(self):
        """Update sensor highlighting based on current selection."""
        reveal_candidates = self._revealing_hidden_mapping_candidates()
        if reveal_candidates != getattr(self, '_last_reveal_unmapped_candidates', False):
            self._last_reveal_unmapped_candidates = reveal_candidates
            self.build_scene_from_model()
            return
        # OPTIMIZED: Rebuilding the scene is too slow unless the hidden
        # candidate-dot set changed. update_sensor_dots handles selection color.
        self.update_sensor_dots()
        
    def on_sensor_mapping_changed(self, role_key, sensor_name, is_mapped):
        """Handle lightweight sensor mapping updates."""
        # Use the optimized update method
        self.update_sensor_dots()

    def locate_sensor(self, sensor_name: str, role_key: str = "", canonical: str = "") -> bool:
        """Center the view on a visible diagram dot by CSV label, role key, or canonical id."""
        if not sensor_name and not role_key and not canonical:
            return False

        target = None
        target_role = role_key or ""
        roles = self.data_manager.diagram_model.get('sensor_roles', {}) or {}

        if role_key:
            target = self.dot_items.get(role_key)
            if target is not None and target.scene() is not self.scene:
                target = None

        for role_key, mapped in roles.items():
            if target is not None:
                break
            if mapped != sensor_name:
                continue
            target = self.dot_items.get(role_key)
            target_role = role_key
            if target is not None and target.scene() is self.scene:
                break
            try:
                from sensor_canonical import resolve_canonical_from_role_key
                resolved = resolve_canonical_from_role_key(self.data_manager.diagram_model, role_key)
                resolved_canonical = resolved[0] if resolved else None
                target = self.dot_items.get(resolved_canonical)
                target_role = resolved_canonical or role_key
                if target is not None and target.scene() is self.scene:
                    break
            except Exception:
                pass
            target = None

        if target is None and canonical:
            for rk, dot in self.dot_items.items():
                if rk == canonical:
                    target = dot
                    target_role = rk
                    break
                try:
                    from sensor_canonical import resolve_canonical_from_role_key
                    resolved = resolve_canonical_from_role_key(self.data_manager.diagram_model, rk)
                    if resolved and resolved[0] == canonical:
                        target = dot
                        target_role = rk
                        break
                except Exception:
                    pass

        if target is None:
            for box_item in self.sensor_boxes.values():
                for sensor_info in box_item.sensors.values():
                    rk = sensor_info.get('role_key')
                    if rk == target_role or rk == canonical or roles.get(rk) == sensor_name:
                        target = sensor_info.get('dot')
                        target_role = rk or target_role
                        break
                if target is not None:
                    break

        if target is None:
            if self._revealing_hidden_mapping_candidates():
                try:
                    mw = self.window()
                    if hasattr(mw, 'statusBar'):
                        mw.statusBar().showMessage(
                            "Select a revealed diagram spot to assign this CSV sensor",
                            4000
                        )
                except Exception:
                    pass
                self.zoom_to_fit()
                print(f"[LOCATE SENSOR] Revealed candidate dots for sensor={sensor_name}")
                return True
            print(f"[LOCATE SENSOR] No visible diagram dot for sensor={sensor_name}, role={target_role}, canonical={canonical}")
            return False

        self.view.centerOn(target)
        self.view.ensureVisible(target.sceneBoundingRect().adjusted(-120, -120, 120, 120), 80, 80)
        self._flash_sensor_dot(target, target_role)
        mapped = roles.get(target_role)
        if not mapped:
            try:
                mw = self.window()
                if hasattr(mw, 'statusBar'):
                    mw.statusBar().showMessage("No data mapped to this diagram spot in the loaded CSV", 3500)
            except Exception:
                pass
        print(f"[LOCATE SENSOR] Centered diagram on sensor={sensor_name}, role={target_role}, canonical={canonical}")
        return True

    def _flash_sensor_dot(self, target, role_key: str = ""):
        if hasattr(target, 'setBrush'):
            target.setBrush(QBrush(QColor('#00D4FF')))
            target.setPen(QPen(QColor(Qt.GlobalColor.black), 3))
            target.setScale(2.6)
            QTimer.singleShot(1800, self.update_sensor_dots)

    def _format_sensor_value_label(self, value):
        if hasattr(self.data_manager, "format_sensor_value"):
            return self.data_manager.format_sensor_value(value)
        if value is None:
            return ""
        if isinstance(value, (int, float)):
            return f"{value:.1f}"
        return str(value)

    def _format_calculated_role_label(self, role_key, calc_key, value):
        value_text = self._format_sensor_value_label(value)
        if not value_text:
            return ""
        key = role_key or calc_key or ""
        if key.startswith('calc.SH'):
            return f"SH {value_text}F"
        if key.startswith('calc.DSH') or (calc_key or "") == 'D.S.H':
            return f"DSH {value_text}F"
        if key.startswith('calc.SC') or (calc_key or "").startswith('S.C'):
            return f"SC {value_text}F"
        return value_text

    def _processed_value_for_calc_key(self, calc_key):
        if not calc_key or self._processed_means is None:
            return None
        candidates = [calc_key]
        try:
            import re
            m = re.match(r'^(S\.H_)([a-z]+)( coil)$', calc_key)
            if m:
                ab = m.group(2)
                candidates.extend([
                    f'{m.group(1)}{ab.upper()}{m.group(3)}',
                    f'{calc_key}-{ab}',
                    f'{m.group(1)}{ab.upper()}{m.group(3)}-{ab}',
                ])
            m = re.match(r'^(S\.C-txv\.)([a-z]+)$', calc_key)
            if m:
                ab = m.group(2)
                candidates.extend([f'{calc_key}-{ab}', f'{m.group(1)}{ab.upper()}'])
        except Exception:
            pass
        for col in candidates:
            if col in self._processed_means.index:
                value = self._processed_means.get(col)
                try:
                    if value is not None and not math.isnan(float(value)):
                        return float(value)
                except (TypeError, ValueError):
                    continue
        return None

    def _instrument_panel_geometry(self, model):
        """Return x, y, width for the full-width instrument section."""
        comps = model.get('components', {}) or {}
        lefts = []
        rights = []
        bottoms = []
        for comp in comps.values():
            pos = comp.get('position') or [0, 0]
            size = comp.get('size') or {}
            x = float(pos[0]) if len(pos) > 0 else 0.0
            y = float(pos[1]) if len(pos) > 1 else 0.0
            w = float(size.get('width', 120) or 120)
            h = float(size.get('height', 60) or 60)
            lefts.append(x)
            rights.append(x + w)
            bottoms.append(y + h)
        x = min(lefts) if lefts else 0.0
        right = max(rights) if rights else x + 980.0
        y = (max(bottoms) if bottoms else 100.0) + 70.0
        width = max(980.0, right - x)
        return (x, y, width)
    
    def build_scene_from_model(self):
        """Rebuild the entire scene from the diagram model."""
        self.scene.clear()
        self.component_items.clear()
        self.pipe_items.clear()
        self.sensor_boxes.clear()
        self.overlay_items.clear()
        self.dot_items.clear()
        self._diagnostic_overlay_items.clear()
        # Reserved footprints (scene coords) of value/calc chips, so each new
        # chip can be nudged to a clear spot instead of stacking on its
        # neighbours. Reset every rebuild; consulted by _attach_value_chip.
        self._value_chip_rects = []
        self._state_chip_rects = []
        self._chip_obstacles_seeded = False

        model = self.data_manager.diagram_model
        
        # Propagate circuit labels, fluid states, and pressure sides before building
        self._propagate_circuit_labels()
        self._propagate_fluid_states()
        self._propagate_pressure_sides()
        
        render_errors = []

        # Create the instrument panel from all canonical sensor-box slots.
        sensor_boxes = model.get('sensor_boxes', {}) or {}
        if sensor_boxes:
            try:
                panel_item = InstrumentPanelItem(
                    "__instrument_panel",
                    sensor_boxes,
                    self.data_manager,
                    self._instrument_panel_geometry(model),
                    show_unmapped=self._revealing_hidden_mapping_candidates(),
                )
                if panel_item.sensors:
                    self.scene.addItem(panel_item)
                    self.sensor_boxes[panel_item.box_id] = panel_item
                    self._attach_sensor_handlers_to_box(panel_item)
            except Exception:
                render_errors.append("instrument panel")
                logger.exception("[DIAGRAM] Failed to render instrument panel")
        
        # Create components
        for comp_id, comp_data in model.get('components', {}).items():
            try:
                comp_type = comp_data.get('type')
                # Use custom components for special types
                if comp_type == 'Junction':
                    item = BaseComponentItem(comp_id, comp_data, self.data_manager)
                elif comp_type == 'TXV':
                    item = BaseComponentItem(comp_id, comp_data, self.data_manager)
                elif comp_type == 'HotGasBypassValve':
                    item = HotGasBypassItem(comp_id, comp_data, self.data_manager)
                elif comp_type == 'HotGasLoop':
                    item = HotGasLoopItem(comp_id, comp_data, self.data_manager)
                elif comp_type == 'Distributor':
                    item = DistributorComponentItem(comp_id, comp_data, self.data_manager)
                elif comp_type == 'SensorBulb':
                    item = SensorBulbComponentItem(comp_id, comp_data, self.data_manager)
                elif comp_type == 'Sensor':
                    item = SensorComponentItem(comp_id, comp_data, self.data_manager)
                elif comp_type == 'Fan':
                    item = FanComponentItem(comp_id, comp_data, self.data_manager)
                elif comp_type == 'AirSensorArray':
                    item = AirSensorArrayComponentItem(comp_id, comp_data, self.data_manager)
                elif comp_type == 'ShelvingGrid':
                    item = ShelvingGridComponentItem(comp_id, comp_data, self.data_manager)
                elif comp_type == 'RemoteLineEndpoint':
                    item = RemoteLineEndpointItem(comp_id, comp_data, self.data_manager)
                elif comp_type == 'SplitterManifold':
                    item = SplitterComponentItem(comp_id, comp_data, self.data_manager)
                elif comp_type == 'CombinerManifold':
                    item = CombinerComponentItem(comp_id, comp_data, self.data_manager)
                elif comp_type == 'SimpleSensorDot':
                    from diagram_components import SimpleSensorDotItem
                    item = SimpleSensorDotItem(comp_id, comp_data, self.data_manager)
                else:
                    item = BaseComponentItem(comp_id, comp_data, self.data_manager)
                self.scene.addItem(item)
                self.component_items[comp_id] = item
            except Exception:
                render_errors.append(f"component {comp_id}")
                logger.exception("[DIAGRAM] Failed to render component %s", comp_id)
        
        # --- NEW ROUTING LOGIC ---
        # Prune dead pipes from model (e.g. template pipes for circuits that were reduced)
        pipes_to_delete = []
        for pipe_id, pipe_data in model.get('pipes', {}).items():
            start_comp_id = pipe_data.get('start_component_id')
            end_comp_id = pipe_data.get('end_component_id')
            start_comp = self.component_items.get(start_comp_id)
            end_comp = self.component_items.get(end_comp_id)
            
            if not start_comp or not end_comp or \
               pipe_data.get('start_port') not in start_comp.ports or \
               pipe_data.get('end_port') not in end_comp.ports:
                pipes_to_delete.append(pipe_id)
                
        for pid in pipes_to_delete:
            del model['pipes'][pid]

        # libavoid removed â€” every pipe carries its own explicit route now.
        
        # Create pipes
        for pipe_id, pipe_data in model.get('pipes', {}).items():
            try:
                start_comp_id = pipe_data['start_component_id']
                end_comp_id = pipe_data['end_component_id']
                
                if start_comp_id in self.component_items and end_comp_id in self.component_items:
                    start_comp = self.component_items[start_comp_id]
                    end_comp = self.component_items[end_comp_id]
                    
                    start_port = start_comp.ports.get(pipe_data['start_port'])
                    end_port = end_comp.ports.get(pipe_data['end_port'])
                    
                    if start_port and end_port:
                        pipe_item = PipeItem(pipe_id, pipe_data, start_port, end_port)
                        self.scene.addItem(pipe_item)
                        self.pipe_items[pipe_id] = pipe_item
            except Exception:
                render_errors.append(f"pipe {pipe_id}")
                logger.exception("[DIAGRAM] Failed to render pipe %s", pipe_id)
        
        # Restore group attributes after rebuild
        for group_id, comp_ids in self.groups.items():
            for comp_id in comp_ids:
                if comp_id in self.component_items:
                    self.component_items[comp_id].group_id = group_id
                    self.component_items[comp_id].setOpacity(0.9)

        # Secondary-fluid condenser arrows are scene overlays so they remain
        # visible above process pipes and below sensor markers.
        self.add_condenser_secondary_flow_arrows()

        # Always overlay sensor role dots (since they are now clean visuals)
        try:
            self.add_sensor_role_dots()
        except Exception:
            render_errors.append("sensor role dots")
            logger.exception("[DIAGRAM] Failed to render sensor role dots")

        # Analysis overlay is independent of mapping/editing.
        if self._analysis_enabled():
            self.apply_state_overlay()

        self._render_diagnostic_overlay()

        # Apply interaction mode (disable editing in Mapping/Analysis)
        self.apply_interaction_mode()

        # For simple-mode (generated) diagrams: lock everything regardless of mode
        if model.get('_simple_mode'):
            for item in self.component_items.values():
                item.setFlag(item.GraphicsItemFlag.ItemIsMovable, False)
                item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, False)
            for item in self.pipe_items.values():
                item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, False)
                item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        if render_errors:
            self._show_render_error_banner(
                f"{len(render_errors)} diagram item(s) failed to render - see log"
            )

    def _show_render_error_banner(self, message: str):
        """Show a visible diagram warning without interrupting the user."""
        text = QGraphicsTextItem(message)
        text.setDefaultTextColor(QColor("#8a1f11"))
        text.setZValue(100000)
        rect = text.boundingRect().adjusted(-12, -8, 12, 8)
        bg = QGraphicsRectItem(rect)
        bg.setBrush(QBrush(QColor("#fff4e5")))
        bg.setPen(QPen(QColor("#d9822b"), 1.5))
        bg.setZValue(99999)
        bg.setPos(-40, -70)
        text.setPos(bg.pos().x() + 12, bg.pos().y() + 8)
        self.scene.addItem(bg)
        self.scene.addItem(text)
        self.overlay_items.extend([bg, text])

    def on_processed_data(self, processed_df):
        """Receive processed results from the Calculations tab and cache the
        column means for the Analysis-mode state overlay."""
        try:
            if processed_df is None or processed_df.empty:
                self._processed_means = None
                self._processed_df = None
            else:
                self._processed_df = processed_df.copy()
                self._processed_means = processed_df.mean(numeric_only=True)
            if self._analysis_enabled() and self._processed_df is not None and getattr(self, 'ph_diagram_widget', None):
                try:
                    self.ph_diagram_widget.load_filtered_data(self._processed_df)
                except Exception:
                    logger.exception("[DIAGRAM] Failed to refresh P-h cycle panel")
            print(f"[STATE OVERLAY] Cached means for "
                  f"{0 if self._processed_means is None else len(self._processed_means)} columns")
            if self._analysis_enabled():
                self.build_scene_from_model()
        except Exception as e:
            print(f"[STATE OVERLAY] Failed to cache processed data: {e}")

    # Finding.component -> diagram component types (for finding->diagram highlight)
    _FINDING_TYPE_MAP = {
        'Compressor':        ['Compressor'],
        'Condenser':         ['Condenser'],
        'Evaporator':        ['Evaporator'],
        'TXV':               ['TXV'],
        'Expansion Device':   ['TXV', 'CapTube', 'EEV'],
        'Cap Tube':          ['CapTube'],
        'Capillary Tube':    ['CapTube'],
        'EEV':               ['EEV'],
        'Distributor':       ['Distributor'],
        'Evap Distributor':  ['Distributor', 'Evaporator'],
        'Filter Dryer':      ['FilterDrier', 'FilterDryer', 'Distributor'],
        'Refrigerant':       ['Compressor', 'Condenser', 'TXV', 'CapTube', 'EEV', 'Evaporator'],
        'Sensors':           ['Sensor', 'SensorBulb'],
        'Sensors / Calculations': ['Sensor', 'SensorBulb', 'Condenser', 'Compressor'],
        'Hot Gas Defrost':   ['HotGasBypassValve', 'HotGasLoop'],
    }

    _SCENARIO_LOCATOR_MAP = {
        # Refrigerant charge findings are broad thermodynamic stories; put the
        # single badge at the liquid-line/condenser-outlet checkpoint.
        'RF-1': {'types': ['Condenser'], 'port': 'outlet'},
        'RF-2': {'types': ['Condenser'], 'port': 'outlet'},
        'RF-3': {'types': ['Condenser'], 'port': 'outlet'},
        'RF-4': {'types': ['Condenser'], 'port': 'outlet'},

        'CP-1': {'types': ['Compressor'], 'port': 'inlet'},
        'CP-2': {'types': ['Compressor'], 'port': 'outlet'},
        'CP-3': {'types': ['Compressor']},
        'CP-4': {'types': ['Compressor']},
        'CP-5': {'types': ['Compressor'], 'port': 'outlet'},
        'CP-6': {'types': ['Compressor']},
        'CP-7': {'types': ['Compressor']},

        'CD-1': {'types': ['Condenser']},
        'CD-2': {'types': ['Condenser']},
        'CD-3': {'types': ['Condenser']},

        'EV-1': {'types': ['Evaporator']},
        'EV-2': {'types': ['Evaporator']},
        'EV-3': {'types': ['Evaporator']},

        'TX-1': {'types': ['TXV', 'CapTube', 'EEV'], 'port': 'outlet'},
        'TX-2': {'types': ['TXV', 'CapTube', 'EEV'], 'port': 'outlet'},
        'TX-3': {'types': ['TXV', 'CapTube', 'EEV'], 'port': 'outlet'},

        'DI-1': {'types': ['Distributor', 'Evaporator'], 'ports': ['inlet', 'dist_inlet']},
        'DI-2': {'types': ['FilterDrier', 'FilterDryer', 'Distributor', 'TXV', 'CapTube', 'EEV', 'Condenser'], 'ports': ['inlet', 'outlet']},
        'DI-3': {'types': ['Distributor', 'Evaporator'], 'ports': ['inlet', 'dist_inlet']},

        'SL-1': {'pipe': {'pressure_side': 'low', 'fluid_state': 'gas'}},

        'HG-1': {'types': ['HotGasBypassValve', 'HotGasLoop']},
        'HG-2': {'types': ['HotGasBypassValve', 'HotGasLoop']},

        'SI-1': {'types': ['Condenser'], 'port': 'outlet'},
        'SI-2': {'types': ['TXV', 'CapTube', 'EEV', 'Evaporator']},
        'SI-3': {'types': ['Compressor']},
        'SI-4': {'types': ['Condenser', 'TXV', 'CapTube', 'EEV', 'Evaporator']},
        'SI-5': {'types': ['Compressor', 'Condenser']},
        'SQ-1': {'types': ['Sensor', 'SensorBulb']},

        'SCORECARD-PRODUCT-TEMP': {'types': ['Evaporator']},
        'SCORECARD-COIL-SUPERHEAT': {'types': ['Evaporator']},
        'SCORECARD-SUBCOOLING': {'types': ['Condenser'], 'port': 'outlet'},
        'SCORECARD-CAPACITY': {'types': ['Compressor']},
        'SCORECARD-DOE': {'types': ['Condenser']},
    }

    def set_diagnostic_findings(self, findings):
        """Receive diagnostics results and render persistent verdict markers."""
        self._diagnostic_findings = [
            f for f in (findings or [])
            if is_diagram_visible_finding(f)
        ]
        try:
            self._render_diagnostic_overlay()
        except Exception:
            logger.exception("[DIAGRAM] Failed to render diagnostic verdict overlay")

    def _finding_module_abbrev(self, finding):
        """Return lh/ctr/rh when the finding names a specific module."""
        from circuit_semantics import module_abbrev

        chunks = [
            getattr(finding, 'label', '') or '',
            getattr(finding, 'component', '') or '',
            getattr(finding, 'summary', '') or '',
        ]
        for text in chunks:
            if 'Unit ' in text:
                try:
                    return text.split('Unit ')[-1].strip().split()[0].lower()
                except Exception:
                    pass
        normalized = ' '.join(chunks).replace('—', ' ').replace('-', ' ')
        for token in ('Left', 'Center', 'Right'):
            if token.lower() in normalized.lower().split():
                return module_abbrev(token)
        for token in ('LH', 'CTR', 'RH'):
            if token.lower() in normalized.lower().split():
                return token.lower()
        return None

    def _locator_spec_for_finding(self, finding):
        scenario_id = str(getattr(finding, 'scenario_id', '') or '')
        label = getattr(finding, 'label', '') or ''
        if scenario_id in self._SCENARIO_LOCATOR_MAP:
            return self._SCENARIO_LOCATOR_MAP[scenario_id]
        if 'Negative Subcooling' in label:
            return self._SCENARIO_LOCATOR_MAP['SI-1']
        return None

    def _component_items_for_types(self, types):
        matches = []
        for component_type in types:
            matches.extend(
                c for c in self.component_items.values()
                if c.component_data.get('type') == component_type
            )
        return matches

    def _finding_target_items(self, finding):
        from circuit_semantics import module_abbrev

        comp_name = (getattr(finding, 'component', '') or '').strip()
        unit_ab = self._finding_module_abbrev(finding)
        spec = self._locator_spec_for_finding(finding)

        if spec and spec.get('pipe'):
            constraints = spec['pipe']
            items = [
                p for p in self.pipe_items.values()
                if all(p.pipe_data.get(k) == v for k, v in constraints.items())
            ]
        elif spec and spec.get('types'):
            types = spec['types']
            items = self._component_items_for_types(types)
        elif comp_name == 'Suction Line':
            items = [p for p in self.pipe_items.values()
                     if p.pipe_data.get('pressure_side') == 'low'
                     and p.pipe_data.get('fluid_state') == 'gas']
        elif comp_name in ('System',):
            items = list(self.component_items.values())
        else:
            base_comp = comp_name.replace('—', '-').split('-')[0].strip()
            types = self._FINDING_TYPE_MAP.get(base_comp, [base_comp])
            items = self._component_items_for_types(types)

        if unit_ab:
            def _matches_unit(item):
                lbl = (item.component_data.get('properties', {}) or {}).get('circuit_label') \
                      if hasattr(item, 'component_data') else None
                return lbl and module_abbrev(lbl) == unit_ab
            filtered = [i for i in items if _matches_unit(i)]
            if filtered:
                items = filtered
        return items

    def _badge_rect_for_finding(self, finding, target):
        spec = self._locator_spec_for_finding(finding) or {}
        port_names = spec.get('ports') or spec.get('port')
        if isinstance(port_names, str):
            port_names = [port_names]
        if port_names and hasattr(target, 'ports'):
            for port_name in port_names:
                port = target.ports.get(port_name)
                if port is not None:
                    p = port.sceneBoundingRect().center()
                    return QRectF(p.x() + 8, p.y() - 18, 54, 22)
        r = target.sceneBoundingRect()
        return QRectF(r.right() - 12, r.top() - 18, 54, 22)

    def _render_diagnostic_overlay(self):
        for item in list(self._diagnostic_overlay_items):
            try:
                if item.scene():
                    self.scene.removeItem(item)
            except (RuntimeError, Exception):
                pass
        self._diagnostic_overlay_items = []

        findings = [
            f for f in self._diagnostic_findings
            if is_diagram_visible_finding(f)
        ]
        if not findings or not self.scene:
            return

        findings.sort(key=finding_sort_key)
        top = findings[0]
        bounds = self.scene.itemsBoundingRect()
        x = bounds.left() + 16
        y = bounds.top() + 12
        banner_text = getattr(top, 'summary', '') or getattr(top, 'label', 'Diagnostic finding')
        if len(findings) > 1:
            banner_text += f"  (+{len(findings) - 1} more)"
        banner = QGraphicsTextItem(banner_text[:160])
        banner.setDefaultTextColor(QColor('#1f2933'))
        banner.setTextWidth(700)
        banner.setPos(x + 12, y + 7)
        banner.setZValue(75)
        rect = QRectF(x, y, min(760, max(360, banner.boundingRect().width() + 28)), 42)
        bg = QGraphicsRectItem(rect)
        bg.setPen(QPen(QColor('#f0b429'), 2))
        bg.setBrush(QBrush(QColor(255, 248, 220, 235)))
        bg.setZValue(74)
        bg.setToolTip("Click to show ranked visible findings")
        bg.mousePressEvent = lambda event, fs=list(findings): self._show_ranked_findings_dialog(fs)
        banner.setToolTip("Click to show ranked visible findings")
        banner.mousePressEvent = lambda event, fs=list(findings): self._show_ranked_findings_dialog(fs)
        self.scene.addItem(bg)
        self.scene.addItem(banner)
        self._diagnostic_overlay_items.extend([bg, banner])

        severity = getattr(top, 'severity', 'WATCH')
        label = {'CRITICAL': 'CRIT', 'WARNING': 'WARN', 'WATCH': 'WATCH'}.get(severity, severity)
        color = {'CRITICAL': '#c0392b', 'WARNING': '#e67e22', 'WATCH': '#2980b9'}.get(severity, '#2980b9')
        targets = self._finding_target_items(top)
        if targets:
            target = targets[0]
            try:
                badge_rect = self._badge_rect_for_finding(top, target)
                badge_bg = QGraphicsRectItem(badge_rect)
                badge_bg.setPen(QPen(QColor(color), 2))
                badge_bg.setBrush(QBrush(QColor('#ffffff')))
                badge_bg.setZValue(78)
                badge = QGraphicsTextItem(label)
                badge.setDefaultTextColor(QColor(color))
                badge.setPos(badge_rect.left() + 6, badge_rect.top() + 2)
                badge.setZValue(79)
                tooltip = (
                    f"{getattr(top, 'label', '')}\n\n"
                    f"{getattr(top, 'summary', '')}\n\n"
                    f"Evidence:\n{getattr(top, 'evidence', '')}\n\n"
                    f"Recommendation:\n{getattr(top, 'recommendation', '')}"
                )
                badge_bg.setToolTip(tooltip)
                badge.setToolTip(tooltip)
                badge_bg.mousePressEvent = lambda event, f=top: self._show_finding_evidence_dialog(f)
                badge.mousePressEvent = lambda event, f=top: self._show_finding_evidence_dialog(f)
                self.scene.addItem(badge_bg)
                self.scene.addItem(badge)
                self._diagnostic_overlay_items.extend([badge_bg, badge])
            except Exception:
                logger.exception("[DIAGRAM] Failed to render diagnostic badge")

    def _show_finding_evidence_dialog(self, finding):
        dlg = QDialog(self)
        dlg.setWindowTitle(getattr(finding, 'label', 'Diagnostic finding'))
        layout = QVBoxLayout(dlg)
        text = QLabel(
            f"<b>{getattr(finding, 'severity', '')}: {getattr(finding, 'summary', '')}</b><br><br>"
            f"<b>Evidence</b><br><pre>{getattr(finding, 'evidence', '')}</pre>"
            f"<b>Recommendation</b><br><pre>{getattr(finding, 'recommendation', '')}</pre>"
        )
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(text)
        show_cycle_btn = QPushButton("Show on cycle")
        show_cycle_btn.clicked.connect(lambda: self.show_finding_on_cycle(finding))
        layout.addWidget(show_cycle_btn)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dlg.accept)
        layout.addWidget(buttons)
        dlg.resize(560, 360)
        dlg.exec()

    def show_finding_on_cycle(self, finding):
        """Open Analysis and highlight the finding's state point on the P-h panel."""
        if getattr(self, 'analysis_checkbox', None) and not self.analysis_checkbox.isChecked():
            self.analysis_checkbox.setChecked(True)
        else:
            self._sync_cycle_panel()
        if self._processed_df is not None and getattr(self, 'ph_diagram_widget', None):
            try:
                self.ph_diagram_widget.load_filtered_data(self._processed_df)
                self.ph_diagram_widget.highlight_finding(finding)
            except Exception:
                logger.exception("[DIAGRAM] Failed to highlight finding on P-h cycle")

    def _show_ranked_findings_dialog(self, findings):
        dlg = QDialog(self)
        dlg.setWindowTitle("Visible Diagram Findings")
        layout = QVBoxLayout(dlg)
        lines = []
        for index, finding in enumerate(findings, start=1):
            lines.append(
                f"<b>{index}. {getattr(finding, 'severity', '')}: "
                f"{getattr(finding, 'label', '')}</b><br>"
                f"{getattr(finding, 'summary', '')}<br>"
            )
        text = QLabel("<br>".join(lines) or "No visible findings.")
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dlg.accept)
        layout.addWidget(buttons)
        dlg.resize(560, 360)
        dlg.exec()

    def highlight_finding(self, finding):
        """Flash a highlight halo around the component(s) a diagnostic
        finding points at, and center the view on the first one.
        Called from MainWindow when a card's 'Show on diagram' is clicked."""
        comp_name = (getattr(finding, 'component', '') or '').strip()
        items = self._finding_target_items(finding)
        if not items:
            print(f"[LOCATE] No diagram items matched finding component '{comp_name}'")
            return

        halos = []
        for item in items:
            try:
                rect = item.sceneBoundingRect().adjusted(-14, -14, 14, 14)
                halo = QGraphicsRectItem(rect)
                halo.setPen(QPen(QColor('#FFC107'), 4))
                halo.setBrush(QBrush(QColor(255, 193, 7, 50)))
                halo.setZValue(60)
                self.scene.addItem(halo)
                halos.append(halo)
            except Exception:
                continue

        def _remove():
            for h in halos:
                try:
                    if h.scene():
                        self.scene.removeItem(h)
                except (RuntimeError, Exception):
                    pass
        QTimer.singleShot(3500, _remove)

        try:
            self.view.centerOn(items[0])
        except Exception:
            pass
        print(f"[LOCATE] Highlighted {len(items)} item(s) for '{comp_name}'")

    # Thresholds for state violations (Â°F)
    _FLASH_GAS_SC_MIN = 0.5     # liquid line must hold at least this subcooling
    _FLOODBACK_SH_MIN = 0.5     # suction line must hold at least this superheat
    _WET_DISCHARGE_SH_MIN = 2.0  # discharge must be clearly superheated

    def apply_state_overlay(self):
        """Render measured refrigerant state on pipes in Analysis mode."""
        means = self._processed_means
        if means is None:
            return
        import math as _math
        from PyQt6.QtGui import QFont
        from circuit_semantics import module_abbrev
        from calculation_orchestrator import _detect_system_type

        system_type = _detect_system_type(self.data_manager.diagram_model)

        def get(col):
            v = means.get(col)
            try:
                if v is None or _math.isnan(float(v)):
                    return None
            except (TypeError, ValueError):
                return None
            return float(v)

        def get_any(*cols):
            for col in cols:
                val = get(col)
                if val is not None:
                    return val
            return None

        def component_type(comp_id):
            item = self.component_items.get(comp_id)
            return item.component_data.get('type') if item else None

        def component_label_abbrev(comp_id):
            item = self.component_items.get(comp_id)
            if not item:
                return None
            props = item.component_data.get('properties') or {}
            return module_tag(props.get('circuit_label'))

        def module_tag(label):
            if label in (None, '', 'None'):
                return None
            return module_abbrev(label)

        def _state_for_pipe(pipe_data):
            fluid = pipe_data.get('fluid_state')
            side = pipe_data.get('pressure_side')
            lbl = pipe_data.get('circuit_label')
            lbl = None if lbl in (None, '', 'None') else lbl
            ab = module_tag(lbl)
            sfx = f'-{ab}' if (system_type == 'cassette' and ab) else ''
            start_id = pipe_data.get('start_component_id')
            end_id = pipe_data.get('end_component_id')
            start_type = component_type(start_id)
            end_type = component_type(end_id)
            start_port = pipe_data.get('start_port')
            end_port = pipe_data.get('end_port')
            expansion_types = {'TXV', 'CapTube', 'EEV'}
            manifold_types = {'SplitterManifold', 'CombinerManifold', 'Junction'}
            if ab is None:
                ab = component_label_abbrev(start_id) or component_label_abbrev(end_id)
                sfx = f'-{ab}' if (system_type == 'cassette' and ab) else ''
            if start_type == 'Condenser' and start_port == 'outlet':
                fluid, side = 'liquid', 'high'
            elif start_type in expansion_types and start_port == 'outlet':
                fluid, side = 'two-phase', 'low'
            elif start_type == 'SplitterManifold' and end_type == 'Evaporator':
                fluid, side = 'two-phase', 'low'
            elif start_type == 'Evaporator' and str(start_port or '').startswith('outlet'):
                fluid, side = 'gas', 'low'
            elif start_type == 'CombinerManifold' or end_type == 'Compressor':
                fluid, side = 'gas', 'low'

            condenser_outlet_pipe = start_type == 'Condenser' and start_port == 'outlet'
            expansion_inlet_pipe = end_type in expansion_types and end_port == 'inlet'
            expansion_outlet_pipe = start_type in expansion_types
            evap_outlet_pipe = start_type == 'Evaporator' and str(start_port or '').startswith('outlet')
            suction_pipe = end_type == 'Compressor' and end_port == 'inlet'
            discharge_pipe = start_type == 'Compressor' and start_port == 'outlet'

            if fluid == 'liquid' and side == 'high':
                txv_sc = get(f'S.C-txv.{ab}') if ab else None
                cond_sc = get(f'S.C{sfx}') if get(f'S.C{sfx}') is not None else get('S.C')
                if condenser_outlet_pipe:
                    state = 'two-phase' if cond_sc is not None and cond_sc <= self._FLASH_GAS_SC_MIN else 'liquid'
                    stripe_fraction = None
                    if state == 'two-phase' and txv_sc is not None and txv_sc > self._FLASH_GAS_SC_MIN:
                        state = 'liquid'
                        stripe_fraction = 0.24
                    return {
                        'state': state,
                        'chip': None,
                        'chip_key': None,
                        'stripe_fraction': stripe_fraction,
                        'detail': (
                            f'Condenser outlet subcooling {cond_sc:.1f} F.' if cond_sc is not None
                            else 'Condenser outlet liquid state.'
                        ),
                    }
                sc = txv_sc if txv_sc is not None else cond_sc
                state = 'two-phase' if sc is not None and sc <= self._FLASH_GAS_SC_MIN else 'liquid'
                return {
                    'state': state,
                    'chip': None,
                    'chip_key': None,
                    'detail': f'TXV inlet subcooling {txv_sc:.1f} F.' if txv_sc is not None else 'High-side liquid line.',
                }

            if fluid == 'gas' and side == 'low':
                coil_sh = get_any(
                    f'S.H_{ab} coil',
                    f'S.H_{(ab or "").upper()} coil',
                    f'S.H_{ab} coil-{ab}',
                    f'S.H_{(ab or "").upper()} coil-{ab}',
                ) if ab else None
                total_sh = get_any(f'S.H_total{sfx}', f'S.H_total-{ab}', 'S.H_total')
                sh = total_sh if suction_pipe else coil_sh
                if suction_pipe and total_sh is not None:
                    sh = total_sh
                elif evap_outlet_pipe and coil_sh is not None:
                    sh = coil_sh
                if sh is not None and sh <= self._FLOODBACK_SH_MIN:
                    return {
                        'state': 'two-phase',
                        'chip': None,
                        'chip_key': None,
                        'detail': (
                            f'Superheat {sh:.1f} F - liquid refrigerant may be returning '
                            'toward the compressor.'
                        ),
                    }
                return {
                    'state': 'low-gas',
                    'chip': None,
                    'chip_key': None,
                    'detail': f'Superheat {sh:.1f} F.' if sh is not None else 'Superheated suction gas.',
                }

            if fluid == 'gas' and side == 'high':
                t3a = get(f'T_3a{sfx}')
                tsat = get(f'T_sat.cond{sfx}')
                dsh = (t3a - tsat) if (t3a is not None and tsat is not None) else None
                if dsh is not None and dsh <= self._WET_DISCHARGE_SH_MIN:
                    return {
                        'state': 'two-phase',
                        'chip': None,
                        'chip_key': None,
                        'detail': (
                            f'Discharge superheat {dsh:.1f} F - discharge gas is barely '
                            'superheated.'
                        ),
                    }
                return {
                    'state': 'high-gas',
                    'chip': None,
                    'chip_key': None,
                    'detail': f'Discharge superheat {dsh:.1f} F.' if dsh is not None else 'High-side discharge gas.',
                }

            if fluid == 'two-phase':
                return {
                    'state': 'two-phase',
                    'chip': None,
                    'chip_key': None,
                    'detail': 'Two-phase expansion/evaporator feed.',
                }

            return {
                'state': 'unknown',
                'chip': None,
                'chip_key': None,
                'detail': 'Refrigerant state is unknown because this segment is missing semantic measurements.',
            }

        palette = {
            'liquid': ('#1565C0', None),
            'low-gas': ('#F59E0B', None),
            'high-gas': ('#D35400', None),
            'two-phase': ('#1565C0', '#F59E0B'),
            'unknown': ('#7C3AED', None),
        }

        rendered = 0
        warnings = 0
        rendered_chip_keys = set()
        chip_count = 0

        def _state_pen(color, width=5, style=Qt.PenStyle.SolidLine):
            pen = QPen(QColor(color), width, style)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            return pen

        def _apply_manifold_analysis_state():
            for item in self.component_items.values():
                comp_type = item.component_data.get('type')
                manifold_item = getattr(item, '_manifold_item', None)
                if manifold_item is None:
                    continue
                if comp_type == 'SplitterManifold':
                    # Distributor internals are downstream of expansion: two-phase feed.
                    manifold_item.setPen(_state_pen('#1565C0'))
                    stripe = QGraphicsPathItem(manifold_item.path(), item)
                    stripe.setPen(_state_pen('#F59E0B', style=Qt.PenStyle.DashLine))
                    stripe.setZValue(manifold_item.zValue() + 1)
                    self.overlay_items.append(stripe)
                elif comp_type == 'CombinerManifold':
                    # Header internals are evaporator outlet/suction gas.
                    manifold_item.setPen(_state_pen('#F59E0B'))

        for pipe_id, pipe in self.pipe_items.items():
            state_info = _state_for_pipe(pipe.pipe_data)
            if not state_info:
                continue
            rendered += 1
            if state_info.get('warning'):
                warnings += 1
            base_color, stripe_color = palette[state_info['state']]
            if state_info.get('stripe_fraction') is not None and stripe_color is None:
                stripe_color = '#F59E0B'
            pen_width = 5
            pen_style = Qt.PenStyle.DotLine if state_info['state'] == 'unknown' else Qt.PenStyle.SolidLine
            pen = QPen(QColor(base_color), pen_width, pen_style)
            pipe.setPen(pen)
            pipe._original_pen = pen  # survive select/deselect cycles
            if stripe_color:
                stripe_path = pipe.path()
                stripe_fraction = state_info.get('stripe_fraction')
                if stripe_fraction is not None:
                    stripe_path = QPainterPath()
                    stripe_path.moveTo(pipe.path().pointAtPercent(0))
                    steps = 12
                    for idx in range(1, steps + 1):
                        pct = max(0.0, min(float(stripe_fraction), 1.0)) * idx / steps
                        stripe_path.lineTo(pipe.path().pointAtPercent(pct))
                stripe = QGraphicsPathItem(stripe_path)
                stripe.setPos(pipe.pos())
                stripe.setPen(QPen(QColor(stripe_color), pen_width, Qt.PenStyle.DashLine))
                stripe.setZValue(pipe.zValue() + 1)
                stripe.setToolTip(state_info.get('detail', ''))
                self.scene.addItem(stripe)
                self.overlay_items.append(stripe)
            try:
                station_chips = [state_info] + list(state_info.get('extra_chips') or [])
                for chip_info in station_chips:
                    chip_text = chip_info.get('chip')
                    chip_key = chip_info.get('chip_key')
                    if not (chip_key and chip_text and chip_key not in rendered_chip_keys):
                        continue
                    pct = float(chip_info.get('chip_pct', 0.5))
                    point = pipe.path().pointAtPercent(max(0.0, min(pct, 1.0)))
                    if self._add_state_chip(point, chip_text, chip_info.get('detail', state_info.get('detail', ''))):
                        rendered_chip_keys.add(chip_key)
                        chip_count += 1
            except Exception:
                pass
            detail = state_info.get('detail', '')
            if detail:
                pipe.setToolTip((pipe.toolTip() or '') + f"\n\nAnalysis: {detail}")
        _apply_manifold_analysis_state()
        print(f"[STATE OVERLAY] rendered={rendered} warning_states={warnings} chips={chip_count}")

    def _add_state_chip(self, point, chip_text, tooltip=''):
        if not chip_text or str(chip_text).strip().lower() == 'nan':
            return False
        from PyQt6.QtGui import QFont
        txt = QGraphicsTextItem(chip_text)
        f = QFont()
        f.setBold(True)
        f.setPointSize(7)
        txt.setFont(f)
        txt.setDefaultTextColor(QColor('#1f2933'))
        txt_rect = txt.boundingRect().adjusted(-4, -2, 4, 2)
        bg = QGraphicsRectItem(txt_rect)
        bg.setBrush(QBrush(QColor(255, 255, 255, 238)))
        bg.setPen(QPen(QColor('#9fb3c8'), 1))
        # Nudge off any already-placed chip: try the default spot, then step
        # upward/downward until clear (these are true scene-coord items).
        base_x, base_y = point.x() + 8, point.y() - 30
        rw = txt_rect.width(); rh = txt_rect.height()
        reserved = getattr(self, '_state_chip_rects', None)
        if reserved is None:
            reserved = self._state_chip_rects = []
        pos_x, pos_y = base_x, base_y
        for k in range(0, 12):
            for dy in ((0,) if k == 0 else (-(rh + 4) * k, (rh + 4) * k)):
                cand = QRectF(base_x, base_y + dy, rw, rh)
                if not any(cand.intersects(r) for r in reserved) and \
                   not any(cand.intersects(r) for r in getattr(self, '_value_chip_rects', [])):
                    pos_x, pos_y = base_x, base_y + dy
                    reserved.append(cand)
                    break
            else:
                continue
            break
        bg.setPos(pos_x, pos_y)
        bg.setZValue(63)
        txt.setPos(bg.pos().x() + 4, bg.pos().y() + 1)
        txt.setZValue(64)
        bg.setToolTip(tooltip or '')
        txt.setToolTip(tooltip or '')
        self.scene.addItem(bg)
        self.scene.addItem(txt)
        self.overlay_items.extend([bg, txt])
        return True

    def add_condenser_secondary_flow_arrows(self):
        """Draw condenser air/water arrows as scene overlays.

        The component paint also has subtle equipment glyphs, but mapped
        sensor dots need a visible secondary-fluid path that sits above pipes.
        """
        from PyQt6.QtWidgets import QGraphicsPathItem
        from PyQt6.QtGui import QBrush, QPen

        def add_vertical_arrow(x, start_y, tip_y, color):
            path = QPainterPath()
            path.moveTo(x, start_y)
            path.lineTo(x, tip_y)

            direction_up = tip_y < start_y
            base_y = tip_y + (12 if direction_up else -12)
            path.moveTo(x - 7, base_y)
            path.lineTo(x + 7, base_y)
            path.lineTo(x, tip_y)
            path.closeSubpath()

            item = QGraphicsPathItem(path)
            item.setPen(QPen(QColor(color), 4))
            item.setBrush(QBrush(QColor(color)))
            item.setZValue(75)
            self.scene.addItem(item)
            self.overlay_items.append(item)
            return item

        for item in self.component_items.values():
            comp_data = item.component_data or {}
            if comp_data.get('type') != 'Condenser':
                continue

            props = comp_data.get('properties', {}) or {}
            condenser_type = props.get('condenser_type', 'Air Cooled')
            mapped_rect = item.mapRectToScene(item.rect())
            rect = mapped_rect.boundingRect() if hasattr(mapped_rect, 'boundingRect') else mapped_rect

            if condenser_type == 'Water Cooled':
                water_color = '#0077B6'
                water_in_x = rect.left() + rect.width() * 0.25
                water_out_x = rect.left() + rect.width() * 0.75
                add_vertical_arrow(water_in_x, rect.bottom() + 32, rect.bottom(), water_color)
                add_vertical_arrow(water_out_x, rect.top(), rect.top() - 32, water_color)
            else:
                air_color = '#607D8B'
                for idx in range(1, 4):
                    x = rect.left() + rect.width() * idx / 4
                    add_vertical_arrow(x, rect.bottom() + 28, rect.bottom(), air_color)
                    add_vertical_arrow(x, rect.top(), rect.top() - 28, air_color)

    def add_sensor_role_dots(self):
        """Create sensor dots at strategic locations with canonical role keys.
        In Mapping: show sensor number when mapped, else empty.
        In Analysis: show average value when mapped, else empty.
        """
        if getattr(self.data_manager, 'ensure_standard_process_callouts', None):
            try:
                self.data_manager.ensure_standard_process_callouts()
            except Exception as exc:
                print(f"[PROCESS_CALLOUTS] Diagram backfill failed: {exc}")

        # Ensure every port has an entry in sensor_points (all ON by default).
        # Also tries to apply saved defaults for this layout type.
        self.data_manager.populate_sensor_points()
        topo = self.data_manager.diagram_model.get('_topology', {})
        if topo:
            self.data_manager.apply_sensor_point_defaults(topo)

        is_analysis = self._analysis_enabled()
        
        role_dot_candidates = []
        direct_custom_dots = []
        port_canonical_roles = {}

        # Add dots for all in/out/sensor ports on all components
        for comp_id, item in self.component_items.items():
            comp_type = item.component_data.get('type')

            if (self.data_manager.diagram_model.get('_simple_mode')
                    and comp_type in ('SplitterManifold', 'CombinerManifold', 'Junction')
                    and getattr(self.data_manager, 'csv_data', None) is None):
                continue

            props = item.component_data.get('properties', {}) or {}
            rendered_port_names = set()

            def append_role_dot_candidate(port_name, port, port_pos, synthetic=False):
                try:
                    port_type = port.port_def.get('type')
                except Exception:
                    port_type = None

                # Show dots for in, out, and sensor type ports
                if port_type in ('in', 'out', 'sensor'):
                    # For Sensor components, only the dedicated measurement (sensor) port
                    # should be mappable. Skip inlet/outlet to avoid accidental mapping.
                    if comp_type == 'Sensor' and port_type in ('in', 'out'):
                        return
                    # Generated LabeledBox components (hot-gas bypass/solenoid,
                    # liquid-line solenoid) use ports only for pipe routing. The
                    # actual mapped solenoid sensors live in canonical sensor
                    # boxes, so showing port dots here creates confusing floaters.
                    if (self.data_manager.diagram_model.get('_simple_mode')
                            and comp_type == 'LabeledBox'):
                        return
                    # Avoid duplicate dots near evaporators by suppressing manifold connecting ports
                    if comp_type == 'SplitterManifold' and port_type == 'out':
                        return
                    if comp_type == 'CombinerManifold' and port_type == 'in':
                        return
                    pos = self._offset_role_dot_from_port(port_pos, port)

                    # Create meaningful role key for diagnostics
                    # For AirSensorArray, include curtain type for better mapping
                    if comp_type == 'AirSensorArray':
                        curtain_type = item.component_data.get('properties', {}).get('curtain_type', 'Primary')
                        # Extract sensor number from port_name (e.g., "sensor_1" -> 1)
                        sensor_num = port_name.split('_')[-1] if '_' in port_name else '1'
                        role_key = f"{curtain_type}Air.{comp_id}.{sensor_num}"
                    else:
                        # Standard format: component_type.component_id.port_name
                        role_key = f"{comp_type}.{comp_id}.{port_name}"

                    enabled = self.data_manager.is_sensor_point_enabled(role_key)

                    # Resolve canonical name for a much cleaner label
                    display_name = role_key
                    try:
                        from sensor_canonical import resolve_canonical_from_role_key
                        cres = resolve_canonical_from_role_key(self.data_manager.diagram_model, role_key)
                        if cres and cres[0]:
                            display_name = cres[0]
                    except Exception:
                        pass
                    if display_name and display_name != role_key:
                        port_canonical_roles.setdefault(display_name, role_key)

                    mapped_sensor = self.data_manager.get_mapped_sensor_for_role(role_key)

                    label = ""
                    if mapped_sensor:
                        val = self.data_manager.get_sensor_value(mapped_sensor)
                        label = self._format_sensor_value_label(val)

                    side = self._role_dot_side_for_port(port)
                    role_dot_candidates.append({
                        'component_id': comp_id,
                        'port_item': port,
                        'true_pos': port_pos,
                        'ideal_pos': pos,
                        'side': side,
                        'role_key': role_key,
                        'label': label,
                        'enabled': enabled,
                        'is_custom': False,
                        'lock_position': True,
                    })

            for port_name, port in item.ports.items():
                rendered_port_names.add(port_name)
                append_role_dot_candidate(port_name, port, port.get_scene_position())

            # Simple-mode component graphics intentionally omit some schema
            # ports (for example compressor pressure taps and condenser water
            # sensors). The mapping resolver still treats those roles as valid,
            # so synthesize diagram dots for any enumerated role without an
            # actual PortItem.
            try:
                from port_resolver import enumerate_ports_for_component
                expected_ports = enumerate_ports_for_component(comp_type, props)
            except Exception:
                expected_ports = []
            for port_name in expected_ports:
                if port_name in rendered_port_names:
                    continue
                proxy = self._role_dot_port_proxy(item, comp_type, port_name)
                if proxy is None:
                    continue
                port_pos = self._scene_pos_for_role_dot_proxy(item, proxy)
                append_role_dot_candidate(port_name, proxy, port_pos, synthetic=True)

        # Add custom sensor points
        custom_sensors = self.data_manager.diagram_model.get('custom_sensors', {})
        self.custom_sensor_points = custom_sensors.copy()
        
        for sensor_id, sensor_data in custom_sensors.items():
            pos_data = sensor_data['position']
            pos = QPointF(pos_data[0], pos_data[1])
            side = self._normalize_chip_side(sensor_data.get('display_side'))
            sensor_type = sensor_data['type']

            replacement_role = port_canonical_roles.get(sensor_id)
            if replacement_role:
                self._migrate_duplicate_custom_mapping(sensor_id, replacement_role)
                continue
            
            # Use sensor_id as role_key for mapping
            mapped_sensor = self.data_manager.get_mapped_sensor_for_role(sensor_id)
            calc_key = sensor_data.get('calc_key')
            label = ""
            # In Analysis mode prefer the computed value, but fall back to the
            # mapped lab value when the calc column is missing/NaN — otherwise a
            # calc dot that shows fine in normal mode goes blank in Analysis.
            if is_analysis and calc_key and self._processed_means is not None:
                val = self._processed_value_for_calc_key(calc_key)
                if val is not None:
                    label = self._format_calculated_role_label(sensor_id, calc_key, val)
            if (not label and mapped_sensor
                    and not (sensor_data.get('calc_only') or sensor_id == 'calc.SC_cond')):
                val = self.data_manager.get_sensor_value(mapped_sensor)
                # A calc dot falling back to its mapped lab value must still
                # carry the SH/SC prefix, so it reads "SH 6.7F" like the
                # computed chips — not a bare "6.7".
                if calc_key:
                    label = self._format_calculated_role_label(sensor_id, calc_key, val)
                else:
                    label = self._format_sensor_value_label(val)

            hosted = self._edge_host_for_custom_dot(pos)
            if hosted:
                role_dot_candidates.append({
                    'component_id': hosted['component_id'],
                    'port_item': None,
                    'true_pos': pos,
                    'ideal_pos': hosted['pos'],
                    'side': hosted['side'],
                    'role_key': sensor_id,
                    'label': label,
                    'enabled': True,
                    'is_custom': True,
                    'custom_sensor_data': sensor_data,
                    'sensor_id': sensor_id,
                    'component_rect': hosted['rect'],
                    'lock_position': True,
                })
                continue
            
            direct_custom_dots.append((pos, sensor_id, label, sensor_data, side))

        for candidate in self._distribute_role_dot_candidates(role_dot_candidates):
            if not self._should_render_role_dot(candidate['role_key']):
                continue
            self._add_role_dot(candidate['pos'], candidate['role_key'], candidate['label'],
                               is_custom=candidate.get('is_custom', False),
                               custom_sensor_data=candidate.get('custom_sensor_data'),
                               sensor_id=candidate.get('sensor_id'),
                               port_item=candidate.get('port_item'),
                               enabled=candidate.get('enabled', True),
                               side=candidate.get('chip_side', candidate['side']))

        for pos, sensor_id, label, sensor_data, side in direct_custom_dots:
            if not self._should_render_role_dot(sensor_id):
                continue
            self._add_role_dot(pos, sensor_id, label, is_custom=True,
                               custom_sensor_data=sensor_data,
                               sensor_id=sensor_id, side=side)
        
        # TODO: Add sensors from sensor boxes
        # This will be implemented in Phase 2

    def _revealing_hidden_mapping_candidates(self) -> bool:
        """Reveal hidden, unmapped diagram dots while assigning an unmatched CSV column."""
        if getattr(self.data_manager, 'csv_data', None) is None:
            return False
        needs_assignment = getattr(self.data_manager, 'selected_sensor_needs_diagram_assignment', None)
        return bool(needs_assignment and needs_assignment())

    def _is_revealed_candidate_dot(self, role_key: str) -> bool:
        if not self._revealing_hidden_mapping_candidates():
            return False
        if self.data_manager.get_mapped_sensor_for_role(role_key):
            return False
        is_process = self.data_manager.is_visible_diagram_role(role_key)
        is_instrument = (
            hasattr(self.data_manager, 'is_instrument_role')
            and self.data_manager.is_instrument_role(role_key)
        )
        return is_process or is_instrument

    def _should_render_role_dot(self, role_key: str) -> bool:
        """After CSV load, show mapped dots only, plus temporary assignment candidates."""
        custom = (self.data_manager.diagram_model.get('custom_sensors') or {}).get(role_key) or {}
        if (self._analysis_enabled() and custom.get('calc_key')
                and self._processed_value_for_calc_key(custom.get('calc_key')) is not None):
            return True
        if getattr(self.data_manager, 'csv_data', None) is None:
            return True
        if self.data_manager.get_mapped_sensor_for_role(role_key):
            return True
        return self._is_revealed_candidate_dot(role_key)

    def _get_sensor_color(self, role_key, mapped_sensor=None):
        """Get color based on sensor status (range-aware)"""
        if not mapped_sensor:
            mapped_sensor = self.data_manager.get_mapped_sensor_for_role(role_key)

        # Get sensor status from data manager
        status = self.data_manager.get_sensor_status(mapped_sensor, role_key)

        # Color mapping:
        # - unmapped: Grey
        # - no_range: Yellow (mapped but no range set)
        # - in_range: Green
        # - out_of_range: Red
        color_map = {
            'unmapped': '#808080',      # Grey
            'no_range': '#FFD700',      # Gold/Yellow
            'in_range': '#4CAF50',      # Green
            'out_of_range': '#F44336'   # Red
        }

        return QColor(color_map.get(status, '#FFA500'))  # Default to orange if unknown

    def _canonical_for_marker_shape(self, role_key):
        """Resolve the canonical ID used to choose marker geometry."""
        try:
            from sensor_canonical import resolve_canonical_from_role_key
            cres = resolve_canonical_from_role_key(self.data_manager.diagram_model, role_key)
            if cres and cres[0]:
                return cres[0]
        except Exception:
            pass
        return role_key or ''

    def _sensor_marker_kind(self, role_key):
        """Return a stable semantic marker kind for a role/canonical ID."""
        canon = self._canonical_for_marker_shape(role_key)
        if canon.startswith('calc.SH'):
            return 'superheat'
        if canon.startswith('calc.SC'):
            return 'subcooling'
        if canon.startswith('P_') or canon.startswith(('P_suc', 'P_disc', 'P_dis')):
            return 'pressure'
        if canon.startswith(('m_dot', 'gpm')):
            return 'flow'
        if canon.startswith('rpm'):
            return 'speed'
        if canon.startswith('calc.'):
            return 'calculated'
        if canon.startswith('T_'):
            return 'temperature'
        return 'other'

    def _sensor_marker_shape_name(self, kind):
        return {
            'temperature': 'circle',
            'pressure': 'diamond',
            'flow': 'right triangle',
            'superheat': 'hexagon',
            'subcooling': 'square',
            'speed': 'vertical rectangle',
            'calculated': 'small square',
            'other': 'small square',
        }.get(kind, 'small square')

    def _make_sensor_marker_item(self, role_key, radius):
        """Create the correct visible marker shape for the role kind."""
        from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsRectItem, QGraphicsPathItem

        kind = self._sensor_marker_kind(role_key)
        r = float(radius)
        d = r * 2.0

        if kind == 'temperature':
            item = QGraphicsEllipseItem(-r, -r, d, d)
        elif kind == 'pressure':
            path = QPainterPath()
            path.moveTo(0, -r)
            path.lineTo(r, 0)
            path.lineTo(0, r)
            path.lineTo(-r, 0)
            path.closeSubpath()
            item = QGraphicsPathItem(path)
        elif kind == 'flow':
            path = QPainterPath()
            path.moveTo(r, 0)
            path.lineTo(-r, -r)
            path.lineTo(-r, r)
            path.closeSubpath()
            item = QGraphicsPathItem(path)
        elif kind == 'superheat':
            path = QPainterPath()
            for idx, (x, y) in enumerate([
                (-r * 0.55, -r),
                (r * 0.55, -r),
                (r, 0),
                (r * 0.55, r),
                (-r * 0.55, r),
                (-r, 0),
            ]):
                if idx == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            path.closeSubpath()
            item = QGraphicsPathItem(path)
        elif kind == 'subcooling':
            item = QGraphicsRectItem(-r, -r, d, d)
        elif kind == 'speed':
            item = QGraphicsRectItem(-r * 0.6, -r, r * 1.2, d)
        else:
            item = QGraphicsRectItem(-r * 0.8, -r * 0.8, d * 0.8, d * 0.8)

        item.setData(3, kind)
        item.setData(4, self._sensor_marker_shape_name(kind))
        return item

    def _short_role_label(self, role_key):
        """Compact visible dot label; full canonical stays in the tooltip."""
        canon = role_key
        try:
            from sensor_canonical import resolve_canonical_from_role_key
            cres = resolve_canonical_from_role_key(self.data_manager.diagram_model, role_key)
            if cres and cres[0]:
                canon = cres[0]
        except Exception:
            pass

        parts = canon.split('.')
        if canon.startswith('T_air.fan_in.'):
            return f"FI {parts[2]} {parts[3]}" if len(parts) > 3 else canon
        if canon.startswith('T_air.fan_off.'):
            return f"FO {parts[2]} {parts[3]}" if len(parts) > 3 else canon
        if canon.startswith('T_air.cond_in.'):
            unit = f" {parts[3]}" if len(parts) > 3 else ''
            return f"CI {parts[2]}{unit}" if len(parts) > 2 else canon
        if canon.startswith('T_air.cond_out.'):
            unit = f" {parts[3]}" if len(parts) > 3 else ''
            return f"CO {parts[2]}{unit}" if len(parts) > 2 else canon
        if canon.startswith('T_air.disc.'):
            return f"DA {parts[-1]}"
        if canon.startswith('T_air.sec.'):
            return f"SA {parts[-1]}"
        if canon.startswith('T_air.ret.'):
            return f"RA {parts[-1]}"
        if canon.startswith('T_prod.'):
            custom = (self.data_manager.diagram_model.get('custom_sensors') or {}).get(role_key) or {}
            paired = custom.get('paired_canonical')
            if paired:
                b = paired.split('.')
                if len(parts) >= 4 and len(b) >= 4:
                    return f"{parts[1]}/{b[1]} {parts[2]}"
            return f"{parts[1]} {parts[2]} {parts[3]}" if len(parts) > 3 else canon
        if canon.startswith('T_door.'):
            suffix_map = {
                'top.L': 'TL', 'top.R': 'TR',
                'ctr': 'C', 'btm.L': 'BL', 'btm.R': 'BR',
            }
            suffix = '.'.join(parts[2:])
            return f"D{parts[1][1:]} {suffix_map.get(suffix, suffix)}" if len(parts) > 2 else canon
        if canon.startswith('T_mull.'):
            suffix_map = {'top': 'T', 'upper': 'U', 'ctr': 'C', 'lower': 'L', 'btm': 'B'}
            return f"M {parts[1]} {suffix_map.get(parts[2], parts[2])}" if len(parts) > 2 else canon
        if canon.startswith('T_coil.'):
            direction = parts[2][0] if len(parts) > 2 and parts[2] else ''
            return f"{parts[1]} {direction}{parts[3]}" if len(parts) > 3 else canon
        if canon.startswith('T_txv.'):
            direction = parts[2][0] if len(parts) > 2 and parts[2] else ''
            return f"txv {parts[1]} {direction}" if len(parts) > 2 else canon
        if canon.startswith('T_eev.'):
            suffix = parts[2] if len(parts) > 2 else ''
            return f"eev {parts[1]} {suffix[:1]}" if suffix else canon
        if canon.startswith('T_dist.'):
            return f"dist {parts[1]}" if len(parts) > 1 else canon
        if canon.startswith('T_defrost.'):
            return f"def {parts[1]}" if len(parts) > 1 else canon
        if canon.startswith('calc.SH_total'):
            return 'SH total'
        if canon.startswith('calc.SH.'):
            return f"SH {parts[-1].upper()}" if parts else 'SH'
        if canon.startswith('calc.SC_txv.'):
            return f"SC TXV {parts[-1].upper()}" if parts else 'SC TXV'
        if canon.startswith('calc.SC_cond'):
            return f"SC {parts[-1].upper()}" if canon != 'calc.SC_cond' else 'SC cond'
        if canon.startswith('P_suc'):
            return 'P suc'
        if canon.startswith('P_disc') or canon.startswith('P_dis'):
            return 'P disc'
        if canon.startswith('m_dot'):
            return 'flow'
        if role_key.startswith('SplitterManifold.') and role_key.endswith('.inlet'):
            try:
                comp_id = role_key.split('.')[1]
                comp = (self.data_manager.diagram_model.get('components') or {}).get(comp_id, {})
                label = ((comp.get('properties') or {}).get('circuit_label') or '').lower()
                tag = {'left': 'lh', 'center': 'ctr', 'right': 'rh'}.get(label, label)
                return f"dist {tag}" if tag and tag != 'none' else 'dist'
            except Exception:
                return 'dist'
        if canon == role_key:
            return None
        return canon.replace('T_', '').replace('P_', 'P ')

    def _normalize_chip_side(self, side):
        side = (side or 'right').lower()
        return {
            'above': 'top',
            'below': 'bottom',
            'top': 'top',
            'bottom': 'bottom',
            'left': 'left',
            'right': 'right',
        }.get(side, 'right')

    def _migrate_duplicate_custom_mapping(self, old_role, new_role):
        """Move saved mappings from duplicate generated callouts to real ports."""
        try:
            roles = self.data_manager.diagram_model.setdefault('sensor_roles', {})
            if old_role in roles and new_role not in roles:
                roles[new_role] = roles[old_role]
            roles.pop(old_role, None)
        except Exception:
            pass

    def _edge_host_for_custom_dot(self, pos):
        """Return component edge metadata when a generated custom dot belongs
        on an equipment edge. Free-air dots are intentionally left alone."""
        host_types = {
            'Compressor', 'Condenser', 'TXV', 'CapTube', 'EEV', 'Evaporator', 'Distributor',
            'Header', 'SplitterManifold', 'CombinerManifold', 'SensorBulb',
            'HotGasBypassValve', 'HotGasLoop', 'RemoteLineEndpoint',
        }
        tolerance = 4.0
        best = None

        for comp_id, item in self.component_items.items():
            comp_type = (item.component_data or {}).get('type')
            if comp_type not in host_types:
                continue
            try:
                mapped_rect = item.mapRectToScene(item.rect())
                rect = mapped_rect.boundingRect() if hasattr(mapped_rect, 'boundingRect') else mapped_rect
            except Exception:
                continue
            if not rect.isValid():
                continue

            within_x = rect.left() - tolerance <= pos.x() <= rect.right() + tolerance
            within_y = rect.top() - tolerance <= pos.y() <= rect.bottom() + tolerance
            if not (within_x and within_y):
                continue

            edge_distances = [
                ('left', abs(pos.x() - rect.left())),
                ('right', abs(pos.x() - rect.right())),
                ('top', abs(pos.y() - rect.top())),
                ('bottom', abs(pos.y() - rect.bottom())),
            ]
            side, distance = min(edge_distances, key=lambda pair: pair[1])
            if distance > tolerance:
                continue

            x = max(rect.left() + 8, min(rect.right() - 8, pos.x()))
            y = max(rect.top() + 8, min(rect.bottom() - 8, pos.y()))
            if side == 'left':
                snapped = QPointF(rect.left(), y)
            elif side == 'right':
                snapped = QPointF(rect.right(), y)
            elif side == 'top':
                snapped = QPointF(x, rect.top())
            else:
                snapped = QPointF(x, rect.bottom())

            if best is None or distance < best['distance']:
                best = {
                    'component_id': comp_id,
                    'side': side,
                    'pos': snapped,
                    'rect': rect,
                    'distance': distance,
                }

        return best

    def _role_dot_port_proxy(self, component_item, comp_type, port_name):
        """Build a lightweight PortItem-like anchor for schema ports omitted
        from the simplified graphics item."""
        schema = SCHEMAS.get(comp_type, {}) or {}
        props = component_item.component_data.get('properties', {}) or {}
        port_def = None

        for candidate in schema.get('ports', []) or []:
            if candidate.get('name') == port_name:
                port_def = dict(candidate)
                break

        if port_def is None and comp_type == 'Condenser':
            condenser_type = props.get('condenser_type', 'Air Cooled')
            conditional = (schema.get('conditional_ports') or {}).get(condenser_type, [])
            for candidate in conditional:
                if candidate.get('name') == port_name:
                    port_def = dict(candidate)
                    break

        if port_def is None:
            return None

        class RoleDotPortProxy:
            pass

        proxy = RoleDotPortProxy()
        proxy.parent_component = component_item
        proxy.port_name = port_name
        proxy.port_def = port_def
        return proxy

    def _scene_pos_for_role_dot_proxy(self, component_item, port_proxy):
        """Map a synthetic schema port position onto the component scene."""
        try:
            width = component_item.rect().width()
            height = component_item.rect().height()
            px, py = port_proxy.port_def.get('position', [0.5, 0.5])
            return component_item.mapToScene(QPointF(px * width, py * height))
        except Exception:
            try:
                rect = component_item.sceneBoundingRect()
                return QPointF(rect.center().x(), rect.center().y())
            except Exception:
                return QPointF(0, 0)

    def _route_endpoint_for_port(self, port_item, distance_along_pipe=0.0):
        """Return a point on the actual connected pipe route for this port.

        Generated simple diagrams can draw a pipe into a different edge than
        the legacy schema port definition suggests. The pipe route is the
        visible truth, so role dots should anchor there.
        """
        if port_item is None:
            return None

        for pipe in getattr(port_item, 'connected_pipes', []) or []:
            route = pipe.pipe_data.get('route') or []
            if len(route) < 2:
                continue

            if getattr(pipe, 'start_port_item', None) is port_item:
                endpoint = route[0]
                neighbor = route[1]
            elif getattr(pipe, 'end_port_item', None) is port_item:
                endpoint = route[-1]
                neighbor = route[-2]
            else:
                continue

            x0, y0 = float(endpoint[0]), float(endpoint[1])
            if not distance_along_pipe:
                return QPointF(x0, y0)

            dx = float(neighbor[0]) - x0
            dy = float(neighbor[1]) - y0
            length = (dx * dx + dy * dy) ** 0.5
            if length <= 0.001:
                return QPointF(x0, y0)
            step = min(float(distance_along_pipe), length)
            return QPointF(x0 + dx / length * step,
                           y0 + dy / length * step)

        return None

    def _pipe_anchor_for_role_dot(self, comp, comp_type, port_name, port_item):
        """Prefer the visible refrigeration pipe route over schema side rules."""
        direct = self._route_endpoint_for_port(port_item)
        if direct is not None:
            return direct

        # Pressure taps are measurements on the suction/discharge lines, not
        # separate side ports on the compressor body.
        aliases = {
            ('Compressor', 'SP'): ('inlet', 14.0),
            ('Compressor', 'DP'): ('outlet', 14.0),
        }
        alias = aliases.get((comp_type, port_name))
        if alias:
            ref_port_name, distance = alias
            ref_port = getattr(comp, 'ports', {}).get(ref_port_name)
            return self._route_endpoint_for_port(ref_port, distance)

        return None

    def _offset_role_dot_from_port(self, scene_pos, port_item):
        """Draw mapping dots on component perimeters, not in open air."""
        if port_item is None:
            return scene_pos

        try:
            comp = port_item.parent_component
            comp_type = (comp.component_data or {}).get('type')
            port_name = port_item.port_name or ''
            port_def = port_item.port_def or {}
        except Exception:
            return scene_pos

        try:
            mapped_rect = comp.mapRectToScene(comp.rect())
            rect = mapped_rect.boundingRect() if hasattr(mapped_rect, 'boundingRect') else mapped_rect
        except Exception:
            try:
                rect = comp.sceneBoundingRect()
            except Exception:
                return scene_pos

        pipe_anchor = self._pipe_anchor_for_role_dot(comp, comp_type, port_name, port_item)
        if pipe_anchor is not None:
            return pipe_anchor

        def clamp(value, lo, hi):
            if hi < lo:
                return value
            return max(lo, min(hi, value))

        def on_top(x):
            return QPointF(clamp(x, rect.left() + 8, rect.right() - 8), rect.top())

        def on_bottom(x):
            return QPointF(clamp(x, rect.left() + 8, rect.right() - 8), rect.bottom())

        def on_left(y):
            return QPointF(rect.left(), clamp(y, rect.top() + 8, rect.bottom() - 8))

        def on_right(y):
            return QPointF(rect.right(), clamp(y, rect.top() + 8, rect.bottom() - 8))

        # Evaporator flow is top-in / bottom-out. Keep the mapping dots on
        # those real header edges so the callouts match the refrigerant path.
        if comp_type == 'Evaporator':
            if port_name.startswith('inlet_circuit_'):
                return on_top(scene_pos.x())
            elif port_name.startswith('outlet_circuit_'):
                return on_bottom(scene_pos.x())
            elif port_name.startswith('sensor_top_'):
                return on_top(scene_pos.x())
            elif port_name.startswith('sensor_bottom_'):
                return on_bottom(scene_pos.x())
            elif port_name == 'dist_inlet':
                return on_top(scene_pos.x())
            elif port_name == 'dist_outlet':
                return on_bottom(scene_pos.x())
            else:
                return on_right(scene_pos.y())

        elif comp_type == 'Condenser':
            water_in_x = rect.left() + rect.width() * 0.25
            water_out_x = rect.left() + rect.width() * 0.75
            if port_name == 'water_flow_gpm':
                return QPointF(water_in_x, rect.bottom() + 16)
            elif port_name == 'water_in_temp':
                return on_bottom(water_in_x)
            elif port_name == 'water_out_temp':
                return on_top(water_out_x)
            elif port_name == 'inlet':
                return on_left(rect.top() + 18)
            elif port_name == 'outlet':
                return on_right(rect.bottom() - 18)
            else:
                return on_right(scene_pos.y())

        elif comp_type == 'Compressor':
            if port_name == 'SP':
                return on_left(rect.top() + 18)
            elif port_name == 'DP':
                return on_right(rect.top() + 18)
            elif port_name == 'RPM':
                return on_left(rect.bottom() - 18)
            elif port_name == 'inlet':
                return on_left(rect.top() + 32)
            elif port_name == 'outlet':
                return on_right(rect.bottom() - 32)

        elif comp_type == 'TXV':
            if port_name == 'inlet':
                return on_left(rect.top() + 18)
            elif port_name == 'outlet':
                return on_right(rect.bottom() - 18)
            elif port_name == 'bulb':
                return on_right(rect.center().y())

        elif comp_type in ('SplitterManifold', 'CombinerManifold', 'Distributor', 'Header'):
            if port_name.startswith(('inlet', 'in_')):
                return on_top(scene_pos.x())
            elif port_name.startswith(('outlet', 'out_')):
                return on_bottom(scene_pos.x())
            else:
                return on_right(scene_pos.y())

        else:
            try:
                px, py = port_def.get('position', [0.5, 0.5])
                if px <= 0.05:
                    return on_left(scene_pos.y())
                elif px >= 0.95:
                    return on_right(scene_pos.y())
                elif py <= 0.05:
                    return on_top(scene_pos.x() + 8)
                elif py >= 0.95:
                    return on_bottom(scene_pos.x() + 8)
                else:
                    return on_right(scene_pos.y())
            except Exception:
                return on_right(scene_pos.y())

        return scene_pos

    def _role_dot_side_for_port(self, port_item):
        """Return the component side used for per-edge dot distribution."""
        if port_item is None:
            return 'right'

        try:
            comp = port_item.parent_component
            comp_type = (comp.component_data or {}).get('type')
            port_name = port_item.port_name or ''
            port_def = port_item.port_def or {}
        except Exception:
            return 'right'

        if comp_type == 'Evaporator':
            if port_name.startswith(('inlet_circuit_', 'dist_inlet')):
                return 'top'
            if port_name.startswith(('outlet_circuit_', 'dist_outlet')):
                return 'bottom'
            if port_name.startswith('sensor_top_'):
                return 'top'
            if port_name.startswith('sensor_bottom_'):
                return 'bottom'
            return 'right'

        if comp_type == 'Condenser':
            if port_name in ('water_in_temp', 'water_out_temp', 'inlet'):
                return 'left'
            return 'right'

        if comp_type == 'Compressor':
            if port_name in ('SP', 'RPM', 'inlet'):
                return 'left'
            return 'right'

        if comp_type == 'TXV':
            if port_name == 'inlet':
                return 'left'
            return 'right'

        if comp_type in ('SplitterManifold', 'CombinerManifold', 'Distributor', 'Header'):
            if port_name.startswith(('inlet', 'in_')):
                return 'top'
            if port_name.startswith(('outlet', 'out_')):
                return 'bottom'
            return 'right'

        try:
            px, py = port_def.get('position', [0.5, 0.5])
            if px <= 0.05:
                return 'left'
            if px >= 0.95:
                return 'right'
            if py <= 0.05:
                return 'top'
            if py >= 0.95:
                return 'bottom'
        except Exception:
            pass
        return 'right'

    def _distribute_role_dot_candidates(self, candidates):
        """Spread role dots along each component edge to prevent dot overlap."""
        if not candidates:
            return []

        groups = {}
        for candidate in candidates:
            key = (candidate.get('component_id'), candidate.get('side') or 'right')
            groups.setdefault(key, []).append(candidate)

        distributed = []
        for (_component_id, side), group in groups.items():
            movable_group = []
            for candidate in group:
                if candidate.get('lock_position'):
                    candidate['pos'] = candidate['ideal_pos']
                    candidate['chip_side'] = self._outward_side_for_dot(
                        candidate['pos'], candidate.get('port_item'), side
                    )
                    distributed.append(candidate)
                else:
                    movable_group.append(candidate)

            group = movable_group
            if not group:
                continue

            if len(group) == 1:
                group[0]['pos'] = group[0]['ideal_pos']
                group[0]['chip_side'] = self._outward_side_for_dot(
                    group[0]['pos'], group[0].get('port_item'), side
                )
                distributed.extend(group)
                continue

            vertical = side in ('left', 'right')
            coords = sorted(
                [(c['ideal_pos'].y() if vertical else c['ideal_pos'].x(), c) for c in group],
                key=lambda pair: pair[0]
            )

            try:
                comp_rect = coords[0][1].get('component_rect')
                if not comp_rect or not comp_rect.isValid():
                    comp_rect = coords[0][1]['port_item'].parent_component.sceneBoundingRect()
            except Exception:
                comp_rect = QRectF()

            margin = 8
            title_margin = 24
            if vertical and comp_rect.isValid():
                lo = comp_rect.top() + title_margin
                hi = comp_rect.bottom() - margin
            elif comp_rect.isValid():
                lo = comp_rect.left() + margin
                hi = comp_rect.right() - margin
            else:
                lo = min(coord for coord, _candidate in coords)
                hi = max(coord for coord, _candidate in coords)

            if hi < lo and comp_rect.isValid():
                if vertical:
                    lo = comp_rect.top() + margin
                    hi = comp_rect.bottom() - margin
                else:
                    lo = comp_rect.left() + margin
                    hi = comp_rect.right() - margin

            screen_spacing = 24 if vertical else 34
            spacing = max(18, screen_spacing / self._current_view_scale())
            values = [max(lo, min(hi, coord)) for coord, _candidate in coords]
            for idx in range(1, len(values)):
                values[idx] = max(values[idx], values[idx - 1] + spacing)

            overflow = values[-1] - hi
            if overflow > 0:
                values = [value - overflow for value in values]
                for idx in range(len(values) - 2, -1, -1):
                    values[idx] = min(values[idx], values[idx + 1] - spacing)

            underflow = lo - values[0]
            if underflow > 0:
                values = [value + underflow for value in values]

            if values[-1] > hi and len(values) > 1:
                if vertical:
                    ideal_center = sum(coord for coord, _candidate in coords) / len(coords)
                    center = max(lo, min(hi, ideal_center))
                    span = spacing * (len(values) - 1)
                    start = center - span / 2
                    values = [start + spacing * idx for idx in range(len(values))]
                else:
                    step = (hi - lo) / (len(values) - 1) if hi > lo else 0
                    values = [lo + step * idx for idx in range(len(values))]

            for value, (_ideal_coord, candidate) in zip(values, coords):
                ideal = candidate['ideal_pos']
                if vertical:
                    candidate['pos'] = QPointF(ideal.x(), value)
                else:
                    candidate['pos'] = QPointF(value, ideal.y())
                candidate['chip_side'] = self._outward_side_for_dot(candidate['pos'], candidate.get('port_item'), side)
                distributed.append(candidate)

        return distributed

    def _outward_side_for_dot(self, dot_pos, port_item, fallback='right'):
        """Choose the value-chip side from geometry so chips extend away from components."""
        try:
            rect = port_item.parent_component.sceneBoundingRect()
        except Exception:
            return fallback or 'right'

        tolerance = 2
        if dot_pos.y() <= rect.top() + tolerance:
            return 'top'
        if dot_pos.y() >= rect.bottom() - tolerance:
            return 'bottom'
        if dot_pos.x() <= rect.left() + tolerance:
            return 'left'
        if dot_pos.x() >= rect.right() - tolerance:
            return 'right'

        dx = dot_pos.x() - rect.center().x()
        dy = dot_pos.y() - rect.center().y()
        if abs(dx) >= abs(dy):
            return 'right' if dx >= 0 else 'left'
        return 'bottom' if dy >= 0 else 'top'

    def _add_role_dot(self, scene_pos, role_key, label_text, is_custom=False,
                      custom_sensor_data=None, sensor_id=None, port_item=None,
                      enabled=True, side='right'):
        from PyQt6.QtWidgets import QGraphicsTextItem, QGraphicsLineItem
        from PyQt6.QtGui import QBrush, QPen

        mapped_sensor = self.data_manager.get_mapped_sensor_for_role(role_key)
        is_selected = mapped_sensor and mapped_sensor in self.data_manager.selected_sensors
        is_revealed_candidate = self._is_revealed_candidate_dot(role_key)

        # Marker item - geometry shows measurement kind; color shows status.
        # Selected: bright cyan, 2.8x scale (distinct from out-of-range red)
        SELECTED_COLOR = QColor('#00D4FF')  # Bright cyan - impossible to miss
        DOT_RADIUS = 6
        SELECTED_SCALE = 2.2

        # DISABLED: grey, semi-transparent, no label, X drawn on top
        if not enabled:
            dot = self._make_sensor_marker_item(role_key, DOT_RADIUS)
            disabled_color = QColor('#606060')
            disabled_color.setAlphaF(0.45)
            dot.setBrush(QBrush(disabled_color))
            dot.setPen(QPen(QColor('#404040'), 1))
            dot.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            dot.setZValue(100)
            dot.setPos(scene_pos)
            dot.setCursor(Qt.CursorShape.PointingHandCursor)
            dot.setToolTip(f"Sensor spot OFF\nRight-click to enable")
            dot.setData(0, role_key)
            # X mark
            x1 = QGraphicsLineItem(-3, -3, 3, 3, dot)
            x2 = QGraphicsLineItem(-3,  3, 3, -3, dot)
            x_pen = QPen(QColor('#CCCCCC'), 1)
            x1.setPen(x_pen); x2.setPen(x_pen)
            self.scene.addItem(dot)
            self.dot_items[role_key] = dot

            def on_disabled_press(event, rk=role_key):
                if event.button() == Qt.MouseButton.RightButton:
                    self._show_sensor_point_menu(event, rk, currently_enabled=False)
                event.accept()
            dot.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
            dot.mousePressEvent = on_disabled_press
            return  # skip label for disabled dots

        dot = self._make_sensor_marker_item(role_key, DOT_RADIUS)
        if is_selected:
            dot.setBrush(QBrush(SELECTED_COLOR))
            dot.setPen(QPen(QColor(Qt.GlobalColor.black), 2))
            dot.setScale(SELECTED_SCALE)
        elif is_revealed_candidate:
            ghost = QColor('#90A4AE')
            ghost.setAlphaF(0.55)
            dot.setBrush(QBrush(ghost))
            dot.setPen(QPen(QColor('#546E7A'), 1))
            dot.setScale(1.0)
            dot.setOpacity(0.65)
        else:
            dot_color = self._get_sensor_color(role_key, mapped_sensor)
            dot.setBrush(QBrush(dot_color))
            dot.setPen(QPen(QColor(Qt.GlobalColor.black), 1))
            dot.setScale(1.0)

        # Store sensor_id for property viewing and deletion
        if is_custom and sensor_id:
            dot.setData(2, sensor_id)  # Store sensor_id in slot 2
            dot.setData(1, 'custom_sensor')  # Mark as custom sensor in slot 1
        
        dot.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        dot.setZValue(100)
        dot.setPos(scene_pos)
        dot.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Store role_key for later updates
        dot.setData(0, role_key)
        
        # Build the canonical + human tooltip header (always show first)
        canon_lines = []
        try:
            from sensor_canonical import resolve_canonical_from_role_key
            cres = resolve_canonical_from_role_key(self.data_manager.diagram_model, role_key)
            if cres:
                canon_lines.append(f"<b>{cres[0]}</b>")
                canon_lines.append(cres[1])
            shape_name = dot.data(4)
            if shape_name:
                canon_lines.append(f"<small>Marker: {shape_name}</small>")
            if mapped_sensor:
                canon_lines.append(f"<i>Mapped:</i> {mapped_sensor}")
            elif is_revealed_candidate:
                canon_lines.append("<i>Candidate spot for selected CSV sensor</i>")
            else:
                canon_lines.append("<i>Unmapped</i>")
        except Exception:
            pass

        if canon_lines:
            if custom_sensor_data and custom_sensor_data.get('paired_canonical'):
                canon_lines.append(f"<small>Shared with: {custom_sensor_data['paired_canonical']}</small>")
            tooltip = "<br>".join(canon_lines)
            tooltip += "<br><br><small>Left-click: map Â· Right-click: menu</small>"
        elif port_item and hasattr(port_item, 'toolTip'):
            tooltip = port_item.toolTip()
        elif is_custom:
            if mapped_sensor:
                tooltip = f"Mapped: {mapped_sensor}"
            else:
                tooltip = "Custom Sensor"
            tooltip += f"\n\nLeft-click: View properties"
            tooltip += f"\nDouble-click: Show detailed info"
            tooltip += f"\nCtrl+Left: Map sensor"
            tooltip += f"\nRight-click: Delete"
        else:
            if mapped_sensor:
                tooltip = f"Mapped: {mapped_sensor}\nLeft-click: Select sensor\nRight-click: Unmap"
            else:
                tooltip = "Left-click: Map sensor\nRight-click: Unmap"
        dot.setToolTip(tooltip)
        
        # Label creation removed per user request. Labels will be handled as hover tooltips.
        # Click handler to map selected sensor -> role (left click) or unmap (right click)
        # Defer left-click action to avoid interrupting double-click detection
        single_click = { 'timer': None }

        def perform_single_click_action():
                if mapped_sensor:
                    # If sensor is mapped, select it in the sensor panel
                    self.data_manager.toggle_sensor_selection(mapped_sensor, multi_select=False)
                    print(f"[SELECT] Selected sensor {mapped_sensor} from diagram")
                else:
                    # If not mapped, map selected sensor
                    selected = list(self.data_manager.selected_sensors)
                    if selected:
                        sensor_name = selected[-1]
                        print(f"[MAP] Attempting to map {sensor_name} to {role_key}")
                        self.data_manager.map_sensor_to_role(role_key, sensor_name)
                        # Update sensor dots immediately instead of full scene rebuild
                        self.update_sensor_dots()
                        print(f"[MAP] Successfully mapped {sensor_name} to {role_key}")
                        # Debug: Show current mapping status
                        # self.data_manager.debug_sensor_mappings()
                    elif is_custom and sensor_id and self.property_editor:
                        # For unmapped custom sensors with no selected sensor, show properties
                        self.property_editor.show_custom_sensor_properties(sensor_id, custom_sensor_data)
                        print(f"[VIEW] Showing properties for {sensor_id}")

        def on_press(event):
            if event.button() == Qt.MouseButton.LeftButton:
                # Schedule single-click action after double-click interval
                try:
                    from PyQt6.QtWidgets import QApplication
                    interval = QApplication.instance().doubleClickInterval() if QApplication.instance() else 250
                except Exception:
                    interval = 250
                if single_click['timer'] and single_click['timer'].isActive():
                    single_click['timer'].stop()
                t = QTimer()
                t.setSingleShot(True)
                t.timeout.connect(perform_single_click_action)
                single_click['timer'] = t
                t.start(interval)
            elif event.button() == Qt.MouseButton.RightButton:
                if is_custom:
                    # Delete custom sensor
                    if sensor_id:
                        self._delete_custom_sensor(sensor_id)
                        print(f"[DELETE] Deleted custom sensor {sensor_id}")
                else:
                    # Show context menu: disable/enable + unmap options
                    self._show_sensor_point_menu(event, role_key, currently_enabled=True)
            event.accept()
        dot.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
        dot.mousePressEvent = on_press
        
        # Add double-click functionality for sensor information popup
        def on_double_click(event):
            if event.button() == Qt.MouseButton.LeftButton:
                # Cancel pending single-click action
                if single_click['timer'] and single_click['timer'].isActive():
                    single_click['timer'].stop()
                if is_custom and sensor_id:
                    # Show custom sensor properties in a popup dialog
                    self.show_sensor_info_dialog(sensor_id, custom_sensor_data, is_custom=True)
                elif mapped_sensor:
                    # Show mapped sensor information
                    self.show_sensor_info_dialog(mapped_sensor, None, is_custom=False, role_key=role_key)
                else:
                    # Unmapped role: still show diagnostics to explain what's missing
                    self.show_sensor_info_dialog(f"(Unmapped) {role_key}", None, is_custom=False, role_key=role_key)
                # no-op: handled above (custom, mapped, or unmapped diagnostics)
            event.accept()
        
        dot.mouseDoubleClickEvent = on_double_click
        
        # Add to scene and track
        self.scene.addItem(dot)
        self.overlay_items.append(dot)
        self.dot_items[role_key] = dot

        if self.data_manager.diagram_model.get('_simple_mode'):
            visible_label = label_text
            short_label = self._short_role_label(role_key)
            if short_label in ('P suc', 'P disc'):
                visible_label = f"{short_label} {label_text}".strip()
            if not visible_label:
                return
            self._attach_value_chip(dot, visible_label, side, DOT_RADIUS)

    def _attach_value_chip(self, dot, text, side, dot_radius):
        """Small value tag anchored to the dot itself. Because the dot ignores
        view transforms, children live in screen pixels â€” the chip stays glued
        to its dot at every zoom level with no collision search needed."""
        from PyQt6.QtWidgets import QGraphicsSimpleTextItem, QGraphicsPathItem
        from PyQt6.QtGui import QBrush, QPen, QPainterPath

        label = QGraphicsSimpleTextItem(text)
        f = label.font()
        f.setPointSizeF(7.5)
        label.setFont(f)
        label.setBrush(QBrush(QColor('#1F3B5C')))
        br = label.boundingRect()

        pad_x, pad_y = 3.0, 1.0
        gap = dot_radius + 4
        w, h = br.width(), br.height()

        # Candidate local offsets, in preference order starting from the
        # requested side. Chips are screen-pixel children (ignore zoom), so a
        # collision is tested in SCENE units by dividing by the current view
        # scale — footprints correctly grow as the diagram zooms out.
        def offsets_for(s):
            base = {
                'left':   (-gap - w - pad_x, -gap - h - pad_y),
                'right':  (gap + pad_x,      -gap - h - pad_y),
                'top':    (-w / 2,           -gap - h - pad_y),
                'bottom': (-w / 2,            gap + pad_y),
            }
            return base.get(s, base['right'])

        order = [side, 'right', 'left', 'top', 'bottom']
        seen = set(); order = [s for s in order if not (s in seen or seen.add(s))]
        candidates = []
        for s in order:
            ox, oy = offsets_for(s)
            candidates.append((ox, oy))
            # vertical stagger fallbacks on the same side (stack up / down)
            for k in (1, 2, 3):
                step = (h + 4) * k
                candidates.append((ox, oy - step))
                candidates.append((ox, oy + step))

        scale = self._current_view_scale() or 1.0
        # Seed obstacles once per build with component/section title rects and
        # any CRIT/badge overlays, so chips also avoid drawn labels — not just
        # each other.
        if not getattr(self, '_chip_obstacles_seeded', False):
            self._chip_obstacles_seeded = True
            from PyQt6.QtWidgets import QGraphicsSimpleTextItem, QGraphicsTextItem
            # NARROW component boxes (compressor/condenser/TXV ~120px) are
            # obstacles: their single port chips must be pushed to the open
            # side, never left clipped by the box. WIDE boxes (evaporator/
            # splitter/header ~240px) are NOT seeded — their inline per-circuit
            # chips have no room to escape and forcing them off-box just makes
            # them collide with each other.
            for item in self.component_items.values():
                try:
                    r = item.sceneBoundingRect()
                    if r.width() < 160:
                        self._value_chip_rects.append(r)
                except Exception:
                    pass
            for it in self.scene.items():
                if isinstance(it, (QGraphicsSimpleTextItem, QGraphicsTextItem)):
                    t = (it.text() if isinstance(it, QGraphicsSimpleTextItem)
                         else it.toPlainText()).strip()
                    if t.startswith('[') or t in ('CRIT',) or 'CRITICAL' in t:
                        self._value_chip_rects.append(it.sceneBoundingRect())
        dot_scene = dot.scenePos()
        chosen = candidates[0]
        for ox, oy in candidates:
            sx = dot_scene.x() + (ox - pad_x) / scale
            sy = dot_scene.y() + (oy - pad_y) / scale
            sw = (w + 2 * pad_x) / scale
            sh = (h + 2 * pad_y) / scale
            cand_rect = QRectF(sx, sy, sw, sh)
            if not any(cand_rect.intersects(r) for r in self._value_chip_rects):
                chosen = (ox, oy)
                self._value_chip_rects.append(cand_rect)
                break
        else:
            # everything collided — keep first candidate but still reserve it
            ox, oy = chosen
            self._value_chip_rects.append(QRectF(
                dot_scene.x() + (ox - pad_x) / scale,
                dot_scene.y() + (oy - pad_y) / scale,
                (w + 2 * pad_x) / scale, (h + 2 * pad_y) / scale))
        lx, ly = chosen

        chip_rect = QRectF(lx - pad_x, ly - pad_y,
                           br.width() + 2 * pad_x, br.height() + 2 * pad_y)
        path = QPainterPath()
        path.addRoundedRect(chip_rect, 3, 3)
        is_negative_sc = text.startswith('SC -') or text.startswith('SC −')
        chip = QGraphicsPathItem(path, dot)
        chip.setBrush(QBrush(QColor(255, 235, 235, 245) if is_negative_sc else QColor(255, 255, 255, 235)))
        chip.setPen(QPen(QColor('#c0392b') if is_negative_sc else QColor(31, 59, 92, 120), 1.1 if is_negative_sc else 0.5))
        chip.setZValue(1)

        label.setParentItem(chip)
        if is_negative_sc:
            label.setBrush(QBrush(QColor('#c0392b')))
        label.setPos(lx, ly)
        label.setZValue(2)

    def _attach_sensor_handlers_to_box(self, box_item):
        """Attach mapping handlers to instrument-panel sensor dots."""
        for sensor_id, sensor_info in box_item.sensors.items():
            dot = sensor_info.get('dot')
            if dot:
                role_key = sensor_info['role_key']
                if not self._should_render_role_dot(role_key):
                    dot.setVisible(False)
                    for key in ('number_item', 'value_item', 'label_item'):
                        item = sensor_info.get(key)
                        if item is not None:
                            item.setVisible(False)
                
                # Create handlers - capture variables by value using default parameters
                single_click = {'timer': None}
                
                def perform_single_click_action(rk=role_key):
                    mapped_sensor = self.data_manager.get_mapped_sensor_for_role(rk)
                    if mapped_sensor:
                        # If sensor is mapped, select it in the sensor panel
                        self.data_manager.toggle_sensor_selection(mapped_sensor, multi_select=False)
                        print(f"[SELECT] Selected sensor {mapped_sensor} from diagram")
                    else:
                        # If not mapped, map selected sensor
                        selected = list(self.data_manager.selected_sensors)
                        if selected:
                            sensor_name = selected[-1]
                            print(f"[MAP] Attempting to map {sensor_name} to {rk}")
                            self.data_manager.map_sensor_to_role(rk, sensor_name)
                            self.update_sensor_dots()
                            print(f"[MAP] Successfully mapped {sensor_name} to {rk}")
                
                def on_press(event, rk=role_key, sid=sensor_id):
                    if event.button() == Qt.MouseButton.LeftButton:
                        # Schedule single-click action after double-click interval
                        try:
                            from PyQt6.QtWidgets import QApplication
                            interval = QApplication.instance().doubleClickInterval() if QApplication.instance() else 250
                        except Exception:
                            interval = 250
                        if single_click['timer'] and single_click['timer'].isActive():
                            single_click['timer'].stop()
                        t = QTimer()
                        t.setSingleShot(True)
                        t.timeout.connect(lambda: perform_single_click_action(rk))
                        single_click['timer'] = t
                        t.start(interval)
                    elif event.button() == Qt.MouseButton.RightButton:
                        # Show context menu for sensor
                        current_mapping = self.data_manager.get_mapped_sensor_for_role(rk)
                        from PyQt6.QtWidgets import QMenu
                        menu = QMenu()
                        
                        if current_mapping:
                            unmap_action = menu.addAction("Unmap Sensor")
                            unmap_action.triggered.connect(lambda checked, r=rk: self._unmap_sensor_from_role(r))
                        else:
                            map_action = menu.addAction("Map Sensor")
                            map_action.triggered.connect(lambda: perform_single_click_action(rk))
                        
                        if self._edit_layout_enabled():
                            menu.addSeparator()

                            edit_action = menu.addAction("Edit Label")
                            edit_action.triggered.connect(lambda checked, bi=box_item, s=sid: self._edit_sensor_label(bi, s))

                            delete_action = menu.addAction("Delete Sensor")
                            delete_action.triggered.connect(lambda checked, bi=box_item, s=sid: self._delete_sensor_from_box(bi, s))
                        
                        menu.exec(event.screenPos())
                        event.accept()
                        return
                    event.accept()
                
                dot.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
                dot.mousePressEvent = on_press
                
                # Add double-click handler
                def on_double_click(event, rk=role_key):
                    if event.button() == Qt.MouseButton.LeftButton:
                        # Cancel pending single-click action
                        if single_click['timer'] and single_click['timer'].isActive():
                            single_click['timer'].stop()
                        
                        mapped_sensor = self.data_manager.get_mapped_sensor_for_role(rk)
                        if mapped_sensor:
                            self.show_sensor_info_dialog(mapped_sensor, None, is_custom=False, role_key=rk)
                        else:
                            self.show_sensor_info_dialog(f"(Unmapped) {rk}", None, is_custom=False, role_key=rk)
                    event.accept()
                
                dot.mouseDoubleClickEvent = on_double_click

    def update_sensor_dots(self):
        """Update existing sensor dots with current mapping status without rebuilding the entire scene."""
        is_analysis = self._analysis_enabled()
        reveal_candidates = self._revealing_hidden_mapping_candidates()
        if reveal_candidates != getattr(self, '_last_reveal_unmapped_candidates', False):
            self._last_reveal_unmapped_candidates = reveal_candidates
            self.build_scene_from_model()
            return
        
        updated_count = 0
        
        # Update existing sensor dots and labels
        for item in self.overlay_items:
            if hasattr(item, 'setData') and item.data(0) is not None:
                role_key = item.data(0)  # role_key is stored in data(0)
                
                # Get current mapping status
                mapped_sensor = self.data_manager.get_mapped_sensor_for_role(role_key)
                is_selected = mapped_sensor and mapped_sensor in self.data_manager.selected_sensors
                is_candidate = self._is_revealed_candidate_dot(role_key)
                should_show = self._should_render_role_dot(role_key)
                if hasattr(item, 'setVisible'):
                    item.setVisible(should_show)
                if hasattr(item, 'setOpacity'):
                    item.setOpacity(0.65 if is_candidate else 1.0)
                if not should_show:
                    continue
                
                # Update dot color and size based on mapping status (for graphics items with brush)
                if hasattr(item, 'setBrush') and not hasattr(item, 'setPlainText'):
                    if is_selected:
                        item.setBrush(QBrush(QColor('#00D4FF')))  # Bright cyan - selected
                        if hasattr(item, 'setPen'):
                            item.setPen(QPen(QColor(Qt.GlobalColor.black), 2))
                        if hasattr(item, 'setScale'):
                            item.setScale(2.2)
                    elif is_candidate:
                        ghost = QColor('#90A4AE')
                        ghost.setAlphaF(0.55)
                        item.setBrush(QBrush(ghost))
                        if hasattr(item, 'setPen'):
                            item.setPen(QPen(QColor('#546E7A'), 1))
                        if hasattr(item, 'setScale'):
                            item.setScale(1.0)
                    else:
                        # Use new range-aware color scheme
                        dot_color = self._get_sensor_color(role_key, mapped_sensor)
                        item.setBrush(QBrush(dot_color))
                        if hasattr(item, 'setPen'):
                            item.setPen(QPen(QColor(Qt.GlobalColor.black), 1))
                        if hasattr(item, 'setScale'):
                            item.setScale(1.0)
                    updated_count += 1
                
                # Update label text (for text items)
                elif hasattr(item, 'setPlainText'):
                    # Preserve position before updating text (important for DraggableTextItem)
                    saved_pos = None
                    if isinstance(item, DraggableTextItem):
                        saved_pos = item.pos()
                    
                    if mapped_sensor:
                        # Always show values, not sensor numbers, so time range/aggregation changes are visible
                        val = self.data_manager.get_sensor_value(mapped_sensor)
                        label_text = self._format_sensor_value_label(val)
                    else:
                        label_text = ""
                    item.setPlainText(label_text)
                    
                    # Restore position if it was a DraggableTextItem
                    if saved_pos is not None:
                        item.setPos(saved_pos)
                    
                    updated_count += 1
        
        # Update sensor box placeholders (not in overlay_items)
        for box_item in self.sensor_boxes.values():
            for sensor_id, sensor_info in box_item.sensors.items():
                dot = sensor_info.get('dot')
                number_item = sensor_info.get('number_item')
                value_item = sensor_info.get('value_item')
                
                if dot:
                    role_key = sensor_info['role_key']
                    mapped_sensor = self.data_manager.get_mapped_sensor_for_role(role_key)
                    is_selected = mapped_sensor and mapped_sensor in self.data_manager.selected_sensors
                    is_candidate = self._is_revealed_candidate_dot(role_key)
                    should_show = self._should_render_role_dot(role_key)
                    dot.setVisible(should_show)
                    dot.setOpacity(0.65 if is_candidate else 1.0)
                    for extra_item in (number_item, value_item, sensor_info.get('label_item')):
                        if extra_item is not None:
                            extra_item.setVisible(should_show)
                    if not should_show:
                        continue
                    
                    # Update dot color and size
                    if is_selected:
                        dot_color = QColor('#00D4FF')  # Bright cyan - selected
                        pen_width = 4
                        dot.setScale(2.8)
                    elif is_candidate:
                        dot_color = QColor('#90A4AE')
                        dot_color.setAlphaF(0.55)
                        pen_width = 1
                        dot.setScale(1.0)
                    else:
                        # Use new range-aware color scheme
                        dot_color = self._get_sensor_color(role_key, mapped_sensor)
                        pen_width = 2 if mapped_sensor else 1
                        dot.setScale(1.0)

                    dot.setBrush(QBrush(dot_color))
                    dot.setPen(QPen(QColor(Qt.GlobalColor.black), pen_width))
                    
                    # Update number item (column 2)
                    if number_item:
                        if mapped_sensor:
                            num = self.data_manager.get_sensor_number(mapped_sensor)
                            number_text = f"#{num}" if num is not None else ""
                        else:
                            number_text = ""
                        number_item.setPlainText(number_text)
                    
                    # Update value item (column 3)
                    if value_item:
                        if mapped_sensor:
                            val = self.data_manager.get_sensor_value(mapped_sensor)
                            value_text = self._format_sensor_value_label(val)
                        else:
                            value_text = ""
                        value_item.setPlainText(value_text)
                    
                    updated_count += 1

    def apply_interaction_mode(self):
        edit_enabled = self._edit_layout_enabled()
        for comp in self.component_items.values():
            comp.setFlag(comp.GraphicsItemFlag.ItemIsMovable, edit_enabled)
            comp.setFlag(comp.GraphicsItemFlag.ItemIsSelectable, edit_enabled)
        for pipe in self.pipe_items.values():
            pipe.setAcceptedMouseButtons(
                (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
                if edit_enabled else Qt.MouseButton.NoButton
            )
    
    def view_wheel_event(self, event):
        """Scroll the diagram document; Ctrl+wheel zooms."""
        if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            delta = event.angleDelta().y()
            bar = self.view.verticalScrollBar()
            bar.setValue(bar.value() - delta)
            event.accept()
            return

        """Handle Ctrl+mouse wheel for zooming in and out."""
        # Get the wheel delta (positive = zoom in, negative = zoom out)
        delta = event.angleDelta().y()
        
        # Calculate zoom factor
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        
        if delta > 0:
            # Zoom in
            factor = zoom_in_factor
            new_zoom = self.zoom_factor * factor
            
            # Limit zoom in
            if new_zoom > 10.0:
                return
            
            self.zoom_factor = new_zoom
        else:
            # Zoom out - limited by diagram width
            factor = zoom_out_factor
            new_zoom = self.zoom_factor * factor
            
            # Calculate minimum zoom based on diagram width
            items_rect = self.scene.itemsBoundingRect()
            if not items_rect.isEmpty():
                view_width = self.view.viewport().width()
                diagram_width = items_rect.width()
                min_zoom_for_width = (view_width * 0.8) / diagram_width if diagram_width > 0 else 0.1
                min_zoom = max(0.05, min_zoom_for_width)
            else:
                min_zoom = 0.1
            
            if new_zoom < min_zoom:
                return
            
            self.zoom_factor = new_zoom
        
        # Apply the zoom
        self.view.scale(factor, factor)
        self._schedule_sensor_dot_relayout()
        
        event.accept()
    
    def zoom_in(self):
        """Zoom in the view."""
        factor = 1.15
        self.zoom_factor *= factor
        if self.zoom_factor > 10.0:
            self.zoom_factor = 10.0
            return
        self.view.scale(factor, factor)
        self._schedule_sensor_dot_relayout()
    
    def zoom_out(self):
        """Zoom out the view - limited by diagram width."""
        factor = 1 / 1.15
        new_zoom = self.zoom_factor * factor
        
        # Calculate minimum zoom based on diagram width (not height)
        items_rect = self.scene.itemsBoundingRect()
        if not items_rect.isEmpty():
            view_width = self.view.viewport().width()
            diagram_width = items_rect.width()
            # Allow zooming out to show full width plus 20% margin
            min_zoom_for_width = (view_width * 0.8) / diagram_width if diagram_width > 0 else 0.1
            min_zoom = max(0.05, min_zoom_for_width)  # Absolute minimum 0.05
        else:
            min_zoom = 0.1
        
        if new_zoom < min_zoom:
            print(f"[ZOOM] Limit reached (min: {min_zoom:.2f}x based on width)")
            return
        
        self.zoom_factor = new_zoom
        self.view.scale(factor, factor)
        self._schedule_sensor_dot_relayout()
    
    def zoom_reset(self):
        """Reset zoom to 100%."""
        # Reset the view transform
        self.view.resetTransform()
        self.zoom_factor = 1.0
        self._schedule_sensor_dot_relayout()
    
    def zoom_to_fit(self, checked=False, full: bool = False, top: bool = True):
        """Fit page width by default; Ctrl-click or full=True fits everything."""
        try:
            if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
                full = True
        except Exception:
            pass

        items_rect = self.scene.itemsBoundingRect()

        if items_rect.isEmpty():
            print("[ZOOM FIT] No items to fit")
            return

        margin = 50
        items_rect.adjust(-margin, -margin, margin, margin)

        if full:
            self.view.fitInView(items_rect, Qt.AspectRatioMode.KeepAspectRatio)
            self.zoom_factor = self.view.transform().m11()
            self._schedule_sensor_dot_relayout()
            print(f"[ZOOM FIT] Fitted everything in view (zoom: {self.zoom_factor:.2f}x)")
            return

        viewport = self.view.viewport()
        view_width = max(1, viewport.width())
        view_height = max(1, viewport.height())
        scale = view_width / max(1.0, items_rect.width())

        self.view.resetTransform()
        self.view.scale(scale, scale)
        self.zoom_factor = scale

        center_x = items_rect.center().x()
        if top:
            center_y = items_rect.top() + (view_height / (2.0 * max(scale, 0.01)))
        else:
            center_y = items_rect.center().y()
        self.view.centerOn(center_x, center_y)
        self._schedule_sensor_dot_relayout()
        print(f"[ZOOM FIT] Fitted page width (zoom: {self.zoom_factor:.2f}x)")

    def _current_view_scale(self):
        try:
            scale = abs(self.view.transform().m11())
            return scale if scale > 0.01 else 0.01
        except Exception:
            return 1.0

    def _schedule_sensor_dot_relayout(self):
        try:
            self._sensor_dot_relayout_timer.start(150)
        except Exception:
            pass

    def _refresh_sensor_dot_layout_for_zoom(self):
        try:
            self.build_scene_from_model()
        except Exception as exc:
            print(f"[ZOOM] Sensor dot relayout failed: {exc}")
    
    # ------------------------------------------------------------------
    def group_selection(self):
        """Group selected components (called from menu)."""
        selected_items = self.scene.selectedItems()
        components_to_group = [item for item in selected_items
                             if isinstance(item, (BaseComponentItem, JunctionComponentItem, TXVComponentItem, DistributorComponentItem, SensorBulbComponentItem, FanComponentItem, AirSensorArrayComponentItem, ShelvingGridComponentItem, HotGasBypassItem, HotGasLoopItem, RemoteLineEndpointItem))]
        
        if len(components_to_group) >= 2:
            self.create_group(components_to_group)
            print(f"[GROUP] Created group with {len(components_to_group)} component(s)")
        else:
            print("[GROUP] Select at least 2 components to group")
    
    def ungroup_selection(self):
        """Ungroup selected group (called from menu)."""
        selected_items = self.scene.selectedItems()
        for item in selected_items:
            if hasattr(item, 'group_id'):
                self.ungroup_by_id(item.group_id)
                return
        print("[UNGROUP] No group selected")
    
    def view_mouse_release_event(self, event):
        """Handle mouse release - restore drag mode after panning."""
        if event.button() == Qt.MouseButton.MiddleButton:
            # Create fake LEFT button release event to properly clean up ScrollHandDrag state
            fake_event = QMouseEvent(
                QEvent.Type.MouseButtonRelease,
                event.position(),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.NoButton,  # buttons() - no buttons pressed after release
                event.modifiers()
            )
            # Pass fake event to base class first to clean up panning state
            QGraphicsView.mouseReleaseEvent(self.view, fake_event)
            # Then restore normal drag mode
            self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.is_panning = False
            return
        
        # Default behavior
        QGraphicsView.mouseReleaseEvent(self.view, event)
    
    def _delete_custom_sensor(self, sensor_id):
        """Delete a custom sensor by ID."""
        # Remove from data manager
        if 'custom_sensors' in self.data_manager.diagram_model:
            if sensor_id in self.data_manager.diagram_model['custom_sensors']:
                del self.data_manager.diagram_model['custom_sensors'][sensor_id]
        
        # Remove from local tracking
        if sensor_id in self.custom_sensor_points:
            del self.custom_sensor_points[sensor_id]
        
        # Unmap if mapped
        self.data_manager.unmap_role(sensor_id)
        
        # Rebuild scene to reflect changes
        self.build_scene_from_model()

    def _delete_all_custom_sensors(self):
        """Delete all old-style custom sensor points with confirmation."""
        from PyQt6.QtWidgets import QMessageBox

        custom_sensors = self.data_manager.diagram_model.get('custom_sensors', {})
        if not custom_sensors:
            QMessageBox.information(self, "Custom Sensors", "No old custom sensors found.")
            return

        count = len(custom_sensors)
        reply = QMessageBox.question(
            self, "Delete Custom Sensors",
            f"Delete all {count} old custom sensor(s)?\n\nThis removes them and their mappings.\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Unmap all custom sensor roles
        for sensor_id in list(custom_sensors.keys()):
            self.data_manager.unmap_role(sensor_id)

        # Clear the data
        self.data_manager.diagram_model['custom_sensors'] = {}
        self.custom_sensor_points = {}

        self.build_scene_from_model()
        print(f"[TOOL] Deleted {count} old custom sensors")

    def _unmap_sensor_from_role(self, role_key):
        """Unmap a sensor from a role."""
        current_mapping = self.data_manager.get_mapped_sensor_for_role(role_key)
        if current_mapping:
            self.data_manager.unmap_role(role_key)
            self.update_sensor_dots()
            print(f"[UNMAP] Unmapped {current_mapping} from {role_key}")
    
    def _delete_sensor_from_box(self, box_item, sensor_id):
        """Delete a sensor from a sensor box."""
        sensor_info = box_item.sensors.get(sensor_id, {}) if hasattr(box_item, 'sensors') else {}
        source_box_id = sensor_info.get('box_id', getattr(box_item, 'box_id', ''))
        source_sensor_id = sensor_info.get('sensor_id', sensor_id)
        self.data_manager.remove_sensor_from_box(source_box_id, source_sensor_id)
        self.build_scene_from_model()
        print(f"[DELETE] Deleted sensor from box")
    
    def _edit_sensor_label(self, box_item, sensor_id):
        """Edit the label of a sensor in a box."""
        from PyQt6.QtWidgets import QInputDialog
        sensor_info = box_item.sensors.get(sensor_id, {}) if hasattr(box_item, 'sensors') else {}
        current_label = sensor_info.get('label', '')
        label, ok = QInputDialog.getText(self, "Edit Sensor Label", "Sensor Label:", text=current_label)
        if ok and label:
            source_sensor_id = sensor_info.get('sensor_id', sensor_id)
            source_box = sensor_info.get('box_data', getattr(box_item, 'box_data', {}))
            sensor_info['label'] = label
            if 'sensors' in source_box:
                for sensor in source_box['sensors']:
                    if sensor.get('id') == source_sensor_id:
                        sensor['label'] = label
                        break
            # Trigger rebuild to update display
            box_item.rebuild_sensors()
            self.data_manager.diagram_model_changed.emit()
            print(f"[EDIT] Updated sensor label to '{label}'")
    
    def show_sensor_info_dialog(self, sensor_name, custom_sensor_data=None, is_custom=False, role_key=None):
        """Show a popup dialog with detailed sensor information and diagnostics."""
        print(f"[DIALOG] Creating sensor info dialog for: {sensor_name}")
        print(f"[DIALOG] Is custom: {is_custom}, role_key: {role_key}")
        
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Sensor Information - {sensor_name}")
        dialog.setMinimumSize(500, 400)
        print(f"[DIALOG] Dialog created, about to show...")
        
        layout = QVBoxLayout(dialog)
        
        # Title
        title_label = QLabel(f"<h2>{sensor_name}</h2>")
        layout.addWidget(title_label)
        
        # Information text area
        info_text = QTextEdit()
        info_text.setReadOnly(True)
        
        info_content = []
        
        if is_custom and custom_sensor_data:
            # Custom sensor information
            info_content.append("=== CUSTOM SENSOR ===")
            info_content.append(f"Type: {custom_sensor_data.get('type', 'Unknown').replace('_', ' ').title()}")
            
            pos = custom_sensor_data.get('position', [0, 0])
            info_content.append(f"Position: ({pos[0]:.1f}, {pos[1]:.1f})")
            
            # Auto-detected properties
            if custom_sensor_data.get('auto_detected'):
                info_content.append("\n=== AUTO-DETECTED PROPERTIES ===")
                circuit = custom_sensor_data.get('circuit_label', 'None')
                pressure = custom_sensor_data.get('pressure_side', 'any')
                fluid = custom_sensor_data.get('fluid_state', 'any')
                
                info_content.append(f"Circuit: {circuit}")
                info_content.append(f"Pressure Side: {pressure}")
                info_content.append(f"Fluid State: {fluid}")
            else:
                info_content.append("\n=== PROPERTIES ===")
                info_content.append("No auto-detected properties available")
        else:
            # Mapped sensor information with comprehensive diagnostics
            info_content.append("=== MAPPED SENSOR ===")
            info_content.append(f"Sensor Name: {sensor_name}")
            
            if role_key:
                info_content.append(f"Role Key: {role_key}")
            
            # Get sensor number
            sensor_number = self.data_manager.get_sensor_number(sensor_name)
            if sensor_number is not None:
                info_content.append(f"Sensor Number: {sensor_number}")
            
            # === COMPREHENSIVE DATA DIAGNOSTICS ===
            info_content.append("\n=== DATA DIAGNOSTICS ===")
            
            # Check if CSV data exists
            if self.data_manager.csv_data is None:
                info_content.append("âŒ CSV Data: NOT LOADED")
            elif self.data_manager.csv_data.empty:
                info_content.append("âŒ CSV Data: EMPTY")
            else:
                info_content.append(f"âœ… CSV Data: LOADED ({len(self.data_manager.csv_data)} rows, {len(self.data_manager.csv_data.columns)} columns)")
            
            # Check if sensor exists in CSV
            if self.data_manager.csv_data is not None and not self.data_manager.csv_data.empty:
                if sensor_name in self.data_manager.csv_data.columns:
                    info_content.append(f"âœ… Sensor Column: FOUND in CSV")
                    
                    # Get raw sensor data
                    sensor_column = self.data_manager.csv_data[sensor_name]
                    total_values = len(sensor_column)
                    non_null_values = len(sensor_column.dropna())
                    null_count = total_values - non_null_values
                    
                    info_content.append(f"   â€¢ Total values: {total_values}")
                    info_content.append(f"   â€¢ Non-null values: {non_null_values}")
                    info_content.append(f"   â€¢ Null values: {null_count}")
                    
                    if non_null_values > 0:
                        # Show sample values
                        sample_values = sensor_column.dropna().head(5).tolist()
                        info_content.append(f"   â€¢ Sample values: {sample_values}")
                        
                        # Show data types
                        info_content.append(f"   â€¢ Data type: {sensor_column.dtype}")
                        
                        # Show min/max if numeric
                        try:
                            numeric_data = pd.to_numeric(sensor_column, errors='coerce').dropna()
                            if len(numeric_data) > 0:
                                info_content.append(f"   â€¢ Min value: {numeric_data.min():.2f}")
                                info_content.append(f"   â€¢ Max value: {numeric_data.max():.2f}")
                                info_content.append(f"   â€¢ Average: {numeric_data.mean():.2f}")
                        except:
                            info_content.append("   â€¢ Data type: Non-numeric")
                    else:
                        info_content.append("   âŒ All values are null/empty")
                else:
                    info_content.append(f"âŒ Sensor Column: NOT FOUND in CSV")
                    info_content.append("   Available columns:")
                    available_cols = [col for col in self.data_manager.csv_data.columns if col != 'Timestamp']
                    for i, col in enumerate(available_cols[:10]):  # Show first 10 columns
                        info_content.append(f"   â€¢ {col}")
                    if len(available_cols) > 10:
                        info_content.append(f"   ... and {len(available_cols) - 10} more columns")
            
            # Check filtered data
            info_content.append("\n=== FILTERING STATUS ===")
            filtered_data = self.data_manager.get_filtered_data()
            if filtered_data is None:
                info_content.append("âŒ Filtered Data: NULL")
            elif filtered_data.empty:
                info_content.append("âŒ Filtered Data: EMPTY")
            else:
                info_content.append(f"âœ… Filtered Data: {len(filtered_data)} rows")
                
                if sensor_name in filtered_data.columns:
                    filtered_sensor_data = filtered_data[sensor_name].dropna()
                    info_content.append(f"   â€¢ Filtered sensor values: {len(filtered_sensor_data)}")
                else:
                    info_content.append(f"   âŒ Sensor not in filtered data")
            
            # Check time range settings
            info_content.append(f"\n=== TIME RANGE SETTINGS ===")
            info_content.append(f"Current Range: {self.data_manager.time_range}")
            if self.data_manager.time_range == 'Custom' and self.data_manager.custom_time_range:
                custom_range = self.data_manager.custom_time_range
                info_content.append(f"Custom Start: {custom_range.get('start', 'Not set')}")
                info_content.append(f"Custom End: {custom_range.get('end', 'Not set')}")
            
            # Check aggregation method
            info_content.append(f"Aggregation Method: {self.data_manager.value_aggregation}")
            
            # Get current sensor value with detailed diagnostics
            info_content.append("\n=== CURRENT VALUE ===")
            sensor_value = self.data_manager.get_sensor_value(sensor_name)
            if sensor_value is not None:
                if isinstance(sensor_value, (int, float)):
                    info_content.append(f"âœ… Current Value: {sensor_value:.2f}")
                else:
                    info_content.append(f"âœ… Current Value: {sensor_value}")
            else:
                info_content.append("âŒ Current Value: NULL/No data available")
                
                # Additional diagnostics for why value might be null
                if self.data_manager.csv_data is not None and sensor_name in self.data_manager.csv_data.columns:
                    info_content.append("\n=== WHY NO DATA? ===")
                    if filtered_data is None or filtered_data.empty:
                        info_content.append("â€¢ Filtered data is empty (time range issue?)")
                    else:
                        sensor_data = filtered_data[sensor_name].dropna()
                        if len(sensor_data) == 0:
                            info_content.append("â€¢ All sensor values are null/empty after filtering")
                        else:
                            info_content.append(f"â€¢ Sensor has {len(sensor_data)} valid values but get_sensor_value() returned None")
                            info_content.append("â€¢ Possible aggregation method issue")
            
            # Get sensor ranges if available
            if hasattr(self.data_manager, 'sensor_ranges') and sensor_name in self.data_manager.sensor_ranges:
                ranges = self.data_manager.sensor_ranges[sensor_name]
                min_val = ranges.get('min')
                max_val = ranges.get('max')
                if min_val is not None or max_val is not None:
                    info_content.append(f"\n=== RANGES ===")
                    if min_val is not None:
                        info_content.append(f"Minimum: {min_val}")
                    if max_val is not None:
                        info_content.append(f"Maximum: {max_val}")
        
        info_text.setPlainText('\n'.join(info_content))
        layout.addWidget(info_text)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        print(f"[DIALOG] About to execute dialog...")
        dialog.exec()
        print(f"[DIALOG] Dialog execution completed")
    
    def show_sensor_info_dialog(self, sensor_name, custom_sensor_data=None, is_custom=False, role_key=None):
        """Show the lab-facing sensor summary for a diagram point."""
        if is_custom and not role_key:
            role_key = sensor_name

        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit

        info = self._build_sensor_info(role_key, sensor_name, custom_sensor_data)
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Sensor Information - {info['default_label']}")
        dialog.setMinimumSize(620, 460)

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"<h2>{info['default_label']}</h2>"))

        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setPlainText(self._format_sensor_info_text(info))
        layout.addWidget(info_text)

        button_row = QHBoxLayout()
        range_btn = QPushButton("Edit Range...")
        range_btn.clicked.connect(lambda: self._open_range_editor_from_info(dialog))
        button_row.addWidget(range_btn)
        button_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

        dialog.exec()

    def _build_sensor_info(self, role_key, fallback_name, custom_sensor_data=None):
        from sensor_canonical import resolve_canonical_from_role_key

        row = None
        if role_key:
            for candidate in self.data_manager.get_expected_sensor_rows(include_disabled=True):
                if candidate.get('role_key') == role_key:
                    row = candidate
                    break

        canonical = role_key or fallback_name
        human = fallback_name
        if row:
            canonical = row.get('canonical') or canonical
            human = row.get('human_label') or human
            default_label = row.get('default_label') or human or canonical
        else:
            resolved = resolve_canonical_from_role_key(self.data_manager.diagram_model, role_key or fallback_name)
            if resolved:
                canonical, human = resolved
            default_label = (custom_sensor_data or {}).get('label') or human or canonical

        csv_column = self.data_manager.get_mapped_sensor_for_role(role_key) if role_key else None
        if not csv_column and fallback_name and fallback_name in self.data_manager.get_sensor_list():
            csv_column = fallback_name

        calc_key = (custom_sensor_data or {}).get('calc_key')
        stats_source = "No data"
        stats_column = None
        stats = None

        filtered = self.data_manager.get_filtered_data()
        if csv_column and filtered is not None and csv_column in filtered.columns:
            stats = self._stats_for_series(filtered[csv_column])
            stats_source = "CSV column (current filter)"
            stats_column = csv_column
        elif calc_key and self._processed_df is not None and calc_key in self._processed_df.columns:
            stats = self._stats_for_series(self._processed_df[calc_key])
            stats_source = "Calculated result"
            stats_column = calc_key

        full_points = 0
        if csv_column and self.data_manager.csv_data is not None and csv_column in self.data_manager.csv_data.columns:
            full_points = len(self.data_manager.csv_data[csv_column].dropna())
        elif calc_key and self._processed_df is not None and calc_key in self._processed_df.columns:
            full_points = len(self._processed_df[calc_key].dropna())

        csv_column_ref = "---"
        if csv_column and self.data_manager.csv_data is not None and csv_column in self.data_manager.csv_data.columns:
            csv_column_ref = f"Col {self._excel_column_name(list(self.data_manager.csv_data.columns).index(csv_column))}"

        range_key = csv_column or default_label
        range_info = (
            self.data_manager.sensor_ranges.get(range_key)
            or self.data_manager.sensor_ranges.get(default_label)
            or self.data_manager.sensor_ranges.get(role_key or '')
        )

        return {
            "default_label": default_label,
            "csv_column": csv_column,
            "canonical": canonical,
            "role_key": role_key,
            "location": human,
            "sensor_type": (custom_sensor_data or {}).get('type'),
            "calc_key": calc_key,
            "stats_source": stats_source,
            "stats_column": stats_column,
            "csv_column_ref": csv_column_ref,
            "stats": stats or {},
            "full_points": full_points,
            "filtered_rows": 0 if filtered is None else len(filtered),
            "time_range": self.data_manager.time_range,
            "range_key": range_key,
            "range_info": range_info,
        }

    @staticmethod
    def _stats_for_series(series):
        import pandas as pd
        raw = series.dropna()
        numeric = pd.to_numeric(series, errors='coerce').dropna()
        if numeric.empty:
            return {
                "points": len(raw),
                "numeric_points": 0,
                "average": None,
                "minimum": None,
                "maximum": None,
                "range": None,
            }
        minimum = float(numeric.min())
        maximum = float(numeric.max())
        return {
            "points": int(len(raw)),
            "numeric_points": int(len(numeric)),
            "average": float(numeric.mean()),
            "minimum": minimum,
            "maximum": maximum,
            "range": maximum - minimum,
        }

    @staticmethod
    def _fmt_stat(value):
        return "---" if value is None else f"{value:.2f}"

    @staticmethod
    def _excel_column_name(index):
        name = ""
        while index >= 0:
            name = chr(65 + (index % 26)) + name
            index = index // 26 - 1
        return name

    def _format_sensor_info_text(self, info):
        stats = info.get("stats") or {}
        range_info = info.get("range_info")
        lines = [
            "SENSOR LABELS",
            f"Sensor name - default: {info.get('default_label') or '---'}",
            f"Sensor name in CSV file: {info.get('csv_column') or 'Not mapped / not loaded'}",
            f"CSV column: {info.get('csv_column_ref') or '---'}",
        ]
        if info.get("calc_key"):
            lines.append(f"Calculated column: {info.get('calc_key')}")
            lines.append(f"Calculated value: {info.get('calc_key')}")

        lines.extend([
            "",
            "DATA SUMMARY",
            f"Time/filter range: {info.get('time_range')}",
            f"Rows in current filter: {info.get('filtered_rows')}",
            f"Data points in full source: {info.get('full_points')}",
            f"Valid data points used: {stats.get('numeric_points', 0)}",
            f"Average: {self._fmt_stat(stats.get('average'))}",
            f"Minimum: {self._fmt_stat(stats.get('minimum'))}",
            f"Maximum: {self._fmt_stat(stats.get('maximum'))}",
            f"Data range (max - min): {self._fmt_stat(stats.get('range'))}",
            "",
            "ACCEPTABLE RANGE",
        ])
        if range_info:
            lines.append(f"Range key: {info.get('range_key')}")
            lines.append(f"Minimum allowed: {range_info.get('min')}")
            lines.append(f"Maximum allowed: {range_info.get('max')}")
        else:
            lines.append("No acceptable range set.")
            lines.append(f"Range key: {info.get('range_key') or '---'}")
        return "\n".join(lines)

    def _open_range_editor_from_info(self, parent_dialog):
        from range_editor_dialog import RangeEditorDialog
        dialog = RangeEditorDialog(self.data_manager, parent=self)
        dialog.exec()
        parent_dialog.accept()

    def _generate_smart_label(self, sensor_type, sensor_data):
        """Generate smart label for custom sensors based on type and detected circuit."""
        # Sensor type abbreviations
        type_abbrev = {
            'superheat': 'SH',
            'subcooling': 'SC',
            'calculation': 'CALC',
            'suction_temp': 'ST',
            'discharge_temp': 'DT',
            'liquid_temp': 'LT',
            'ambient_temp': 'AMB',
            'case_temp': 'CT'
        }

        if sensor_data.get('calc_key'):
            return sensor_data.get('label') or sensor_data.get('calc_key')
        
        abbrev = type_abbrev.get(sensor_type, sensor_type.upper()[:3])
        
        # Add circuit suffix if detected
        if sensor_data.get('auto_detected'):
            circuit = sensor_data.get('circuit_label', 'None')
            if circuit == 'Left':
                return f"{abbrev}-LH"
            elif circuit == 'Center':
                return f"{abbrev}-CTR"
            elif circuit == 'Right':
                return f"{abbrev}-RH"
        
        # No circuit detected
        return abbrev
    
    def _propagate_circuit_labels(self):
        """
        Propagate circuit labels through all pipes in the network.
        This runs after components are loaded but before visual items are created.
        """
        model = self.data_manager.diagram_model
        components = model.get('components', {})
        pipes = model.get('pipes', {})
        
        # First pass: Build a temporary component map for lookups
        temp_comp_map = {}
        for comp_id, comp_data in components.items():
            temp_comp_map[comp_id] = comp_data
        
        # Update each pipe's circuit label
        updated_count = 0
        for pipe_id, pipe_data in pipes.items():
            start_comp_id = pipe_data.get('start_component_id')
            end_comp_id = pipe_data.get('end_component_id')
            
            if not start_comp_id or not end_comp_id:
                continue
            
            # Get component data
            start_comp_data = temp_comp_map.get(start_comp_id)
            end_comp_data = temp_comp_map.get(end_comp_id)
            
            if not start_comp_data or not end_comp_data:
                continue
            
            # Try to determine circuit label using tracing
            circuit_label = self._trace_circuit_label_from_data(
                start_comp_id, start_comp_data, pipe_data.get('start_port'),
                end_comp_id, end_comp_data, pipe_data.get('end_port'),
                temp_comp_map, pipes
            )
            
            # Update if different
            if pipe_data.get('circuit_label') != circuit_label:
                pipe_data['circuit_label'] = circuit_label
                updated_count += 1
        
        if updated_count > 0:
            print(f"[PROPAGATE] Updated circuit labels for {updated_count} pipes")
    
    def _propagate_fluid_states(self):
        """
        Propagate fluid states through all pipes in the network.
        - Junction: propagate non-'any' inlet fluid to all outlet pipes.
        - Iterate until stable, then run per-pipe reconciliation.
        """
        model = self.data_manager.diagram_model
        components = model.get('components', {})
        pipes = model.get('pipes', {})
        
        # Build component and pipe maps for efficient lookup
        comp_map = {comp_id: comp_data for comp_id, comp_data in components.items()}
        pipe_map = {pipe_id: pipe_data for pipe_id, pipe_data in pipes.items()}
        
        # Build connection graph: component_id -> port_name -> connected_pipes
        connections = {}
        for pipe_id, pipe_data in pipes.items():
            start_comp = pipe_data.get('start_component_id')
            start_port = pipe_data.get('start_port')
            end_comp = pipe_data.get('end_component_id')
            end_port = pipe_data.get('end_port')
            
            if not all([start_comp, start_port, end_comp, end_port]):
                continue
            
            # Add to connections graph
            if start_comp not in connections:
                connections[start_comp] = {}
            if start_port not in connections[start_comp]:
                connections[start_comp][start_port] = []
            connections[start_comp][start_port].append(pipe_id)
            
            if end_comp not in connections:
                connections[end_comp] = {}
            if end_port not in connections[end_comp]:
                connections[end_comp][end_port] = []
            connections[end_comp][end_port].append(pipe_id)
        
        total_updates = 0
        # Iteratively propagate junction inlet fluid to all outlets
        for _ in range(3):  # a few passes to reach stability on small graphs
            updates_this_pass = 0
            for comp_id, comp_data in comp_map.items():
                if comp_data.get('type') != 'Junction':
                    continue
                
                # Collect inlet fluids
                inlet_fluids = set()
                for port_name, pipe_ids in connections.get(comp_id, {}).items():
                    if port_name.startswith('inlet_'):
                        for pid in pipe_ids:
                            pd = pipe_map.get(pid)
                            if not pd:
                                continue
                            # pipe that ends at this junction inlet
                            if pd.get('end_component_id') == comp_id and pd.get('end_port') == port_name:
                                f = pd.get('fluid_state', 'any')
                                if f != 'any':
                                    inlet_fluids.add(f)
                
                if not inlet_fluids:
                    continue
                
                # If multiple different non-any fluids exist, skip to avoid bad inference
                if len(inlet_fluids) > 1:
                    # Could log a warning here for diagnostics
                    continue
                inferred_fluid = next(iter(inlet_fluids))
                
                # Apply to all outlet pipes that are 'any'
                for port_name, pipe_ids in connections.get(comp_id, {}).items():
                    if port_name.startswith('outlet_'):
                        for pid in pipe_ids:
                            pd = pipe_map.get(pid)
                            if not pd:
                                continue
                            if pd.get('start_component_id') == comp_id and pd.get('start_port') == port_name:
                                if pd.get('fluid_state', 'any') == 'any':
                                    pd['fluid_state'] = inferred_fluid
                                    updates_this_pass += 1
            total_updates += updates_this_pass
            if updates_this_pass == 0:
                break
        if total_updates > 0:
            print(f"[PROPAGATE] Junction fluid propagation updated {total_updates} pipe(s)")
        
        # Final reconciliation per-pipe
        updated_count = 0
        for pipe_id, pipe_data in pipes.items():
            start_comp_id = pipe_data.get('start_component_id')
            end_comp_id = pipe_data.get('end_component_id')
            if not start_comp_id or not end_comp_id:
                continue
            start_comp_data = comp_map.get(start_comp_id)
            end_comp_data = comp_map.get(end_comp_id)
            if not start_comp_data or not end_comp_data:
                continue
            start_fluid = self._get_effective_fluid_state_from_data(start_comp_id, start_comp_data, 
                                                                   pipe_data.get('start_port'), 
                                                                   connections, pipe_map, comp_map)
            end_fluid = self._get_effective_fluid_state_from_data(end_comp_id, end_comp_data,
                                                                 pipe_data.get('end_port'),
                                                                 connections, pipe_map, comp_map)
            if start_fluid == 'any' or end_fluid == 'any':
                new_fluid_state = start_fluid if start_fluid != 'any' else end_fluid
            elif start_fluid == end_fluid:
                new_fluid_state = start_fluid
            else:
                continue
            if pipe_data.get('fluid_state') != new_fluid_state:
                pipe_data['fluid_state'] = new_fluid_state
                updated_count += 1
        if updated_count > 0:
            print(f"[PROPAGATE] Reconciled fluid states for {updated_count} pipe(s)")

    def _propagate_pressure_sides(self):
        """
        Propagate pressure side through junctions in a direction-independent manner.
        Prefer concrete sides ('high'/'low'); leave as 'any' only if unknown.
        """
        model = self.data_manager.diagram_model
        components = model.get('components', {})
        pipes = model.get('pipes', {})
        
        comp_map = {cid: c for cid, c in components.items()}
        # Iterate a few times to stabilize
        total_updates = 0
        for _ in range(3):
            updates = 0
            for pid, pd in pipes.items():
                scid = pd.get('start_component_id'); sp = pd.get('start_port')
                ecid = pd.get('end_component_id'); ep = pd.get('end_port')
                if not (scid and ecid and sp and ep):
                    continue
                sc = comp_map.get(scid); ec = comp_map.get(ecid)
                if not (sc and ec):
                    continue
                # Derive effective pressure for the endpoints using schema + neighbor pipes
                start_eff = self._get_effective_pressure_side_from_data(scid, sc, sp, model.get('pipes', {}))
                end_eff = self._get_effective_pressure_side_from_data(ecid, ec, ep, model.get('pipes', {}))
                if start_eff == 'any' and end_eff == 'any':
                    continue
                if start_eff == 'any':
                    eff = end_eff
                elif end_eff == 'any':
                    eff = start_eff
                elif start_eff == end_eff:
                    eff = start_eff
                else:
                    eff = 'any'
                if eff != 'any' and pd.get('pressure_side') != eff:
                    pd['pressure_side'] = eff
                    updates += 1
            total_updates += updates
            if updates == 0:
                break
        if total_updates > 0:
            print(f"[PROPAGATE] Updated pressure sides for {total_updates} pipe(s)")

    def _get_effective_pressure_side_from_data(self, comp_id, comp_data, port_name, pipes):
        """
        Determine effective pressure side for a port using component schema; if 'any',
        scan connected pipes for a concrete side.
        """
        from component_schemas import SCHEMAS
        schema = SCHEMAS.get(comp_data.get('type'), {})
        # Find static port
        for p in schema.get('ports', []):
            if p.get('name') == port_name:
                side = p.get('pressure_side', 'any')
                if side != 'any':
                    return side
                break
        # Dynamic ports
        for dyn_key in ('dynamic_ports', 'dynamic_ports_2'):
            dp = schema.get(dyn_key)
            if dp and port_name.startswith(dp.get('prefix', '')):
                side = dp.get('port_details', {}).get('pressure_side', 'any')
                if side != 'any':
                    return side
        # Infer from connected pipes
        inferred = None
        for pid, pd in pipes.items():
            if (pd.get('start_component_id') == comp_id and pd.get('start_port') == port_name) or \
               (pd.get('end_component_id') == comp_id and pd.get('end_port') == port_name):
                ps = pd.get('pressure_side', 'any')
                if ps != 'any':
                    inferred = ps
                    break
        return inferred or 'any'
    
    def _get_effective_fluid_state_from_data(self, comp_id, comp_data, port_name, connections, pipe_map, comp_map):
        """
        Get effective fluid state for a port using raw data (before visual items are created).
        """
        # Get component type and find port definition
        comp_type = comp_data.get('type')
        
        # Get port definition from component schema
        schema = SCHEMAS.get(comp_type, {})
        all_ports = list(schema.get('ports', []))
        
        port_def = None
        for port in all_ports:
            if port.get('name') == port_name:
                port_def = port
                break
        
        # If no port definition found, try dynamic ports (support two groups)
        if not port_def and 'dynamic_ports' in schema:
            dynamic_ports = schema['dynamic_ports']
            if port_name.startswith(dynamic_ports.get('prefix', '')):
                port_def = dynamic_ports.get('port_details', {})
        if not port_def and 'dynamic_ports_2' in schema:
            dynamic_ports = schema['dynamic_ports_2']
            if port_name.startswith(dynamic_ports.get('prefix', '')):
                port_def = dynamic_ports.get('port_details', {})
        
        if not port_def:
            return 'any'
        
        # Get the port's defined fluid state
        port_fluid = port_def.get('fluid_state', 'any')
        
        # If the port has a specific fluid state (not 'any'), use it
        if port_fluid != 'any':
            return port_fluid
        
        # For ports with 'any' fluid state (like junction ports), trace through connected pipes
        if comp_id in connections and port_name in connections[comp_id]:
            for pipe_id in connections[comp_id][port_name]:
                pipe_data = pipe_map.get(pipe_id)
                if pipe_data:
                    pipe_fluid = pipe_data.get('fluid_state', 'any')
                    if pipe_fluid != 'any':
                        return pipe_fluid
        
        # If no connected pipes or all pipes have 'any', return the port's default
        return port_fluid
    
    def _trace_circuit_label_from_data(self, start_comp_id, start_comp_data, start_port_name,
                                        end_comp_id, end_comp_data, end_port_name,
                                        comp_map, pipes):
        """
        Trace circuit label using raw data (before visual items are created).
        """
        # Try to get circuit label directly from components
        start_circuit = start_comp_data.get('properties', {}).get('circuit_label', 'None')
        end_circuit = end_comp_data.get('properties', {}).get('circuit_label', 'None')
        
        # Check if we found non-None labels
        if start_circuit and start_circuit != 'None':
            return start_circuit
        if end_circuit and end_circuit != 'None':
            return end_circuit
        
        # If no direct labels, walk through junction networks to find the nearest labeled component.
        if start_comp_data.get('type') == 'Junction':
            traced_label = self._find_circuit_label_via_junctions(start_comp_id, comp_map, pipes)
            if traced_label != 'None':
                return traced_label

        if end_comp_data.get('type') == 'Junction':
            traced_label = self._find_circuit_label_via_junctions(end_comp_id, comp_map, pipes)
            if traced_label != 'None':
                return traced_label

        return 'None'
    
    def _find_circuit_label_via_junctions(self, seed_comp_id, comp_map, pipes):
        """
        Breadth-first search starting from a junction to find the nearest component
        that has an explicit circuit label. Only traverses through other junctions.
        """
        visited = set()
        queue = deque([seed_comp_id])

        while queue:
            comp_id = queue.popleft()
            if comp_id in visited:
                continue
            visited.add(comp_id)

            comp_data = comp_map.get(comp_id)
            if not comp_data:
                continue

            circuit_label = comp_data.get('properties', {}).get('circuit_label', 'None')
            if circuit_label and circuit_label != 'None':
                return circuit_label

            if comp_data.get('type') != 'Junction':
                continue

            for pipe_data in pipes.values():
                if pipe_data.get('start_component_id') == comp_id:
                    neighbor = pipe_data.get('end_component_id')
                    if neighbor and neighbor not in visited:
                        queue.append(neighbor)
                if pipe_data.get('end_component_id') == comp_id:
                    neighbor = pipe_data.get('start_component_id')
                    if neighbor and neighbor not in visited:
                        queue.append(neighbor)

        return 'None'
    
    def _get_effective_fluid_state(self, component, port):
        """
        Get the effective fluid state for a port by tracing through connected pipes.
        For junction ports that default to 'any', this traces back to find the actual fluid state.
        """
        # Get the port's defined fluid state
        port_fluid = port.port_def.get('fluid_state', 'any')
        
        # If the port has a specific fluid state (not 'any'), use it
        if port_fluid != 'any':
            return port_fluid
        
        # For ports with 'any' fluid state (like junction ports), trace through the network
        # to find the actual fluid state from connected components
        traced_fluid = self._trace_fluid_state_through_network(component.component_id, port.port_name, visited=set())
        if traced_fluid != 'any':
            return traced_fluid
        
        # If no connected pipes or all pipes have 'any', return the port's default
        return port_fluid

    def _get_effective_pressure_side(self, component, port):
        """
        Determine effective pressure side for a port. If the port's schema is 'any'
        (e.g., junctions), try infer from connected pipes' pressure sides.
        """
        port_pressure = port.port_def.get('pressure_side', 'any')
        print(f"[EFFECTIVE PRESSURE] Port {component.component_id}.{port.port_name} has pressure: {port_pressure}")
        if port_pressure != 'any':
            return port_pressure
        
        # For ports with 'any' pressure side (like junction ports), trace through the network
        # to find the actual pressure side from connected components
        print(f"[EFFECTIVE PRESSURE] Tracing pressure for {component.component_id}.{port.port_name}")
        traced_pressure = self._trace_pressure_side_through_network(component.component_id, port.port_name, visited=set())
        print(f"[EFFECTIVE PRESSURE] Traced result: {traced_pressure}")
        if traced_pressure != 'any':
            return traced_pressure
        
        # Infer from any connected pipe that has a concrete pressure_side
        for pipe_item in getattr(port, 'connected_pipes', []) or []:
            try:
                ps = pipe_item.pipe_data.get('pressure_side', 'any')
                if ps != 'any':
                    return ps
            except Exception:
                continue
        return 'any'

    def _trace_circuit_label(self, start_comp, start_port, end_comp, end_port):
        """
        Intelligently trace circuit label through junctions.
        Follows refrigerant flow direction to find the actual component with circuit_label.
        """
        # Try to get circuit label directly from components
        start_circuit = start_comp.component_data.get('properties', {}).get('circuit_label', 'None')
        end_circuit = end_comp.component_data.get('properties', {}).get('circuit_label', 'None')
        
        # Check if we found non-None labels
        found_labels = []
        if start_circuit and start_circuit != 'None':
            found_labels.append(start_circuit)
        if end_circuit and end_circuit != 'None':
            found_labels.append(end_circuit)
        
        # If both components have labels (should be same or one None), prefer non-None
        if len(found_labels) > 0:
            return found_labels[0]
        
        # If no direct labels, check if either is a junction - trace through network
        start_type = start_comp.component_data.get('type')
        end_type = end_comp.component_data.get('type')
        
        # Determine port types for flow direction
        start_port_type = start_port.port_def.get('type', 'out')  # Default to 'out'
        end_port_type = end_port.port_def.get('type', 'in')      # Default to 'in'
        
        # Trace backward from start if it's a junction and we're connecting from an inlet
        if start_type == 'Junction' and start_port_type == 'out':
            traced_label = self._trace_backward_through_network(start_comp.component_id, visited=set())
            if traced_label != 'None':
                return traced_label
        
        # Trace forward from end if it's a junction and we're connecting to an outlet
        if end_type == 'Junction' and end_port_type == 'in':
            traced_label = self._trace_forward_through_network(end_comp.component_id, visited=set())
            if traced_label != 'None':
                return traced_label
        
        # Trace backward from end if it's a junction
        if end_type == 'Junction':
            traced_label = self._trace_backward_through_network(end_comp.component_id, visited=set())
            if traced_label != 'None':
                return traced_label
        
        # Trace forward from start if it's a junction
        if start_type == 'Junction':
            traced_label = self._trace_forward_through_network(start_comp.component_id, visited=set())
            if traced_label != 'None':
                return traced_label
        
        return 'None'
    
    def _trace_pressure_side_through_network(self, comp_id, port_name, visited):
        """
        Trace pressure side through the piping network bidirectionally.
        Returns pressure_side from the first non-junction component found.
        """
        if comp_id in visited:
            return 'any'
        visited.add(comp_id)
        
        # Get component
        if comp_id not in self.component_items:
            return 'any'
        
        comp = self.component_items[comp_id]
        comp_type = comp.component_data.get('type')
        
        # If not a junction, get its pressure side from the port definition
        if comp_type != 'Junction':
            # Get the port's pressure side from schema
            port_def = None
            schema = SCHEMAS.get(comp_type, {})
            
            # Check static ports
            for p in schema.get('ports', []):
                if p.get('name') == port_name:
                    port_def = p
                    break
            
            # Check dynamic ports
            if not port_def:
                for dyn_key in ('dynamic_ports', 'dynamic_ports_2'):
                    dp = schema.get(dyn_key)
                    if dp and port_name.startswith(dp.get('prefix', '')):
                        port_def = dp.get('port_details', {})
                        break
            
            if port_def:
                pressure_side = port_def.get('pressure_side', 'any')
                if pressure_side != 'any':
                    return pressure_side
            return 'any'
        
        # It's a junction - trace through all connected pipes
        model = self.data_manager.diagram_model
        pipes = model.get('pipes', {})
        
        # Check pipes connected to this port
        for pipe_id, pipe_data in pipes.items():
            if (pipe_data.get('start_component_id') == comp_id and pipe_data.get('start_port') == port_name) or \
               (pipe_data.get('end_component_id') == comp_id and pipe_data.get('end_port') == port_name):
                # Get the other component
                other_comp_id = pipe_data.get('start_component_id') if pipe_data.get('end_component_id') == comp_id else pipe_data.get('end_component_id')
                other_port = pipe_data.get('start_port') if pipe_data.get('end_component_id') == comp_id else pipe_data.get('end_port')
                
                if other_comp_id and other_comp_id in self.component_items:
                    traced_pressure = self._trace_pressure_side_through_network(other_comp_id, other_port, visited.copy())
                    if traced_pressure != 'any':
                        return traced_pressure
        
        # If no pipes found, try to find any component in the system with concrete pressure values
        # This helps when the network isn't fully connected yet
        print(f"[TRACE PRESSURE] Checking other components for pressure values...")
        for other_comp_id, other_comp in self.component_items.items():
            if other_comp_id != comp_id and other_comp_id not in visited:
                other_comp_type = other_comp.component_data.get('type')
                if other_comp_type != 'Junction':
                    print(f"[TRACE PRESSURE] Checking {other_comp_type} component {other_comp_id}")
                    # Check all ports of this component for concrete pressure values
                    schema = SCHEMAS.get(other_comp_type, {})
                    for port_def in schema.get('ports', []):
                        pressure_side = port_def.get('pressure_side', 'any')
                        if pressure_side != 'any':
                            print(f"[TRACE PRESSURE] Found pressure {pressure_side} in {other_comp_type} port {port_def.get('name')}")
                            return pressure_side
                    
                    # Check dynamic ports
                    for dyn_key in ('dynamic_ports', 'dynamic_ports_2'):
                        dp = schema.get(dyn_key)
                        if dp:
                            pressure_side = dp.get('port_details', {}).get('pressure_side', 'any')
                            if pressure_side != 'any':
                                print(f"[TRACE PRESSURE] Found pressure {pressure_side} in {other_comp_type} dynamic port")
                                return pressure_side
        
        return 'any'
    
    def _trace_fluid_state_through_network(self, comp_id, port_name, visited):
        """
        Trace fluid state through the piping network bidirectionally.
        Returns fluid_state from the first non-junction component found.
        """
        if comp_id in visited:
            return 'any'
        visited.add(comp_id)
        
        # Get component
        if comp_id not in self.component_items:
            return 'any'
        
        comp = self.component_items[comp_id]
        comp_type = comp.component_data.get('type')
        
        # If not a junction, get its fluid state from the port definition
        if comp_type != 'Junction':
            # Get the port's fluid state from schema
            port_def = None
            schema = SCHEMAS.get(comp_type, {})
            
            # Check static ports
            for p in schema.get('ports', []):
                if p.get('name') == port_name:
                    port_def = p
                    break
            
            # Check dynamic ports
            if not port_def:
                for dyn_key in ('dynamic_ports', 'dynamic_ports_2'):
                    dp = schema.get(dyn_key)
                    if dp and port_name.startswith(dp.get('prefix', '')):
                        port_def = dp.get('port_details', {})
                        break
            
            if port_def:
                fluid_state = port_def.get('fluid_state', 'any')
                if fluid_state != 'any':
                    return fluid_state
            return 'any'
        
        # It's a junction - trace through all connected pipes
        model = self.data_manager.diagram_model
        pipes = model.get('pipes', {})
        
        # Check pipes connected to this port
        for pipe_id, pipe_data in pipes.items():
            if (pipe_data.get('start_component_id') == comp_id and pipe_data.get('start_port') == port_name) or \
               (pipe_data.get('end_component_id') == comp_id and pipe_data.get('end_port') == port_name):
                # Get the other component
                other_comp_id = pipe_data.get('start_component_id') if pipe_data.get('end_component_id') == comp_id else pipe_data.get('end_component_id')
                other_port = pipe_data.get('start_port') if pipe_data.get('end_component_id') == comp_id else pipe_data.get('end_port')
                
                if other_comp_id and other_comp_id in self.component_items:
                    traced_fluid = self._trace_fluid_state_through_network(other_comp_id, other_port, visited.copy())
                    if traced_fluid != 'any':
                        return traced_fluid
        
        # If no pipes found, try to find any component in the system with concrete fluid values
        # This helps when the network isn't fully connected yet
        for other_comp_id, other_comp in self.component_items.items():
            if other_comp_id != comp_id and other_comp_id not in visited:
                other_comp_type = other_comp.component_data.get('type')
                if other_comp_type != 'Junction':
                    # Check all ports of this component for concrete fluid values
                    schema = SCHEMAS.get(other_comp_type, {})
                    for port_def in schema.get('ports', []):
                        fluid_state = port_def.get('fluid_state', 'any')
                        if fluid_state != 'any':
                            return fluid_state
                    
                    # Check dynamic ports
                    for dyn_key in ('dynamic_ports', 'dynamic_ports_2'):
                        dp = schema.get(dyn_key)
                        if dp:
                            fluid_state = dp.get('port_details', {}).get('fluid_state', 'any')
                            if fluid_state != 'any':
                                return fluid_state
        
        return 'any'
    
    def _trace_fluid_through_connection(self, start_comp, start_port, end_comp, end_port):
        """
        Trace fluid state through a specific connection between two components.
        This method tries to find a concrete fluid state by tracing through the network
        from both ends of the connection.
        """
        # Try tracing from start component
        start_traced = self._trace_fluid_state_through_network(start_comp.component_id, start_port.port_name, visited=set())
        if start_traced != 'any':
            return start_traced
        
        # Try tracing from end component
        end_traced = self._trace_fluid_state_through_network(end_comp.component_id, end_port.port_name, visited=set())
        if end_traced != 'any':
            return end_traced
        
        # If both traces return 'any', try to find fluid state from existing pipes in the network
        model = self.data_manager.diagram_model
        pipes = model.get('pipes', {})
        
        # Look for any pipe that has a concrete fluid state
        for pipe_id, pipe_data in pipes.items():
            fluid_state = pipe_data.get('fluid_state', 'any')
            if fluid_state != 'any':
                # Check if this pipe is connected to either of our components
                start_comp_id = pipe_data.get('start_component_id')
                end_comp_id = pipe_data.get('end_component_id')
                
                if (start_comp_id == start_comp.component_id or start_comp_id == end_comp.component_id or
                    end_comp_id == start_comp.component_id or end_comp_id == end_comp.component_id):
                    return fluid_state
        
        return 'any'
    
    def _trace_pressure_through_connection(self, start_comp, start_port, end_comp, end_port):
        """
        Trace pressure side through a specific connection between two components.
        This method tries to find a concrete pressure side by tracing through the network
        from both ends of the connection.
        """
        # Try tracing from start component
        start_traced = self._trace_pressure_side_through_network(start_comp.component_id, start_port.port_name, visited=set())
        if start_traced != 'any':
            return start_traced
        
        # Try tracing from end component
        end_traced = self._trace_pressure_side_through_network(end_comp.component_id, end_port.port_name, visited=set())
        if end_traced != 'any':
            return end_traced
        
        # If both traces return 'any', try to find pressure from existing pipes in the network
        model = self.data_manager.diagram_model
        pipes = model.get('pipes', {})
        
        # Look for any pipe that has a concrete pressure side
        for pipe_id, pipe_data in pipes.items():
            pressure_side = pipe_data.get('pressure_side', 'any')
            if pressure_side != 'any':
                # Check if this pipe is connected to either of our components
                start_comp_id = pipe_data.get('start_component_id')
                end_comp_id = pipe_data.get('end_component_id')
                
                if (start_comp_id == start_comp.component_id or start_comp_id == end_comp.component_id or
                    end_comp_id == start_comp.component_id or end_comp_id == end_comp.component_id):
                    return pressure_side
        
        return 'any'
    
    def _trace_backward_through_network(self, comp_id, visited):
        """
        Trace backward through the piping network following inlet connections.
        Returns circuit_label from the first non-junction component found.
        """
        if comp_id in visited:
            return 'None'
        visited.add(comp_id)
        
        # Get component
        if comp_id not in self.component_items:
            return 'None'
        
        comp = self.component_items[comp_id]
        comp_type = comp.component_data.get('type')
        
        # If not a junction, get its circuit label
        if comp_type != 'Junction':
            circuit_label = comp.component_data.get('properties', {}).get('circuit_label', 'None')
            if circuit_label != 'None':
                return circuit_label
            return 'None'
        
        # It's a junction - find pipes connected to its inlet ports
        model = self.data_manager.diagram_model
        pipes = model.get('pipes', {})
        
        for pipe_id, pipe_data in pipes.items():
            # Check if this pipe connects TO this junction (i.e., junction is the end)
            if pipe_data.get('end_component_id') == comp_id:
                # Get the port type
                end_port_name = pipe_data.get('end_port')
                if end_port_name and end_port_name.startswith('inlet_'):
                    # This pipe feeds into the junction - trace from the start component
                    start_comp_id = pipe_data.get('start_component_id')
                    if start_comp_id:
                        result = self._trace_backward_through_network(start_comp_id, visited)
                        if result != 'None':
                            return result
        
        return 'None'
    
    def _trace_forward_through_network(self, comp_id, visited):
        """
        Trace forward through the piping network following outlet connections.
        Returns circuit_label from the first non-junction component found.
        """
        if comp_id in visited:
            return 'None'
        visited.add(comp_id)
        
        # Get component
        if comp_id not in self.component_items:
            return 'None'
        
        comp = self.component_items[comp_id]
        comp_type = comp.component_data.get('type')
        
        # If not a junction, get its circuit label
        if comp_type != 'Junction':
            circuit_label = comp.component_data.get('properties', {}).get('circuit_label', 'None')
            if circuit_label != 'None':
                return circuit_label
            return 'None'
        
        # It's a junction - find pipes connected to its outlet ports
        model = self.data_manager.diagram_model
        pipes = model.get('pipes', {})
        
        for pipe_id, pipe_data in pipes.items():
            # Check if this pipe starts FROM this junction
            if pipe_data.get('start_component_id') == comp_id:
                # Get the port type
                start_port_name = pipe_data.get('start_port')
                if start_port_name and start_port_name.startswith('outlet_'):
                    # This pipe goes out from the junction - trace to the end component
                    end_comp_id = pipe_data.get('end_component_id')
                    if end_comp_id:
                        result = self._trace_forward_through_network(end_comp_id, visited)
                        if result != 'None':
                            return result
        
        return 'None'
    
    def _detect_nearby_pipe_properties(self, position, radius=50):
        """
        Detect nearby pipe properties for smart sensor placement.
        Returns dict with fluid_state, pressure_side, circuit_label, and detected flag.
        """
        default_props = {
            'fluid_state': 'any',
            'pressure_side': 'any',
            'circuit_label': 'None',
            'detected': False
        }
        
        # Find pipes within radius
        nearby_pipes = []
        for pipe_id, pipe_item in self.pipe_items.items():
            pipe_data = pipe_item.pipe_data
            
            # Calculate distance to the actual pipe path
            pipe_path = pipe_item.path()
            if pipe_path.isEmpty():
                continue
                
            # Get the pipe path as a QPainterPath
            # Sample points along the path to find the closest distance
            min_distance = float('inf')
            
            # Sample points along the path (every 10 pixels)
            path_length = pipe_path.length()
            if path_length > 0:
                sample_count = max(10, int(path_length / 10))
                for i in range(sample_count + 1):
                    percent = i / sample_count
                    point = pipe_path.pointAtPercent(percent)
                    if not point.isNull():
                        distance = ((position.x() - point.x())**2 + (position.y() - point.y())**2)**0.5
                        min_distance = min(min_distance, distance)
            
            # Also check distance to start and end points
            start_comp_id = pipe_data.get('start_component_id')
            end_comp_id = pipe_data.get('end_component_id')
            
            if start_comp_id in self.component_items:
                start_comp = self.component_items[start_comp_id]
                start_pos = start_comp.scenePos()
                distance = ((position.x() - start_pos.x())**2 + (position.y() - start_pos.y())**2)**0.5
                min_distance = min(min_distance, distance)
                
            if end_comp_id in self.component_items:
                end_comp = self.component_items[end_comp_id]
                end_pos = end_comp.scenePos()
                distance = ((position.x() - end_pos.x())**2 + (position.y() - end_pos.y())**2)**0.5
                min_distance = min(min_distance, distance)
            
            if min_distance <= radius:
                nearby_pipes.append((min_distance, pipe_data))
        
        # If no nearby pipes, return default
        if not nearby_pipes:
            print(f"[SENSOR DETECT] No pipes found within {radius} pixels of ({position.x():.1f}, {position.y():.1f})")
            return default_props
        
        # Use the closest pipe
        nearby_pipes.sort(key=lambda x: x[0])
        closest_pipe = nearby_pipes[0][1]
        closest_distance = nearby_pipes[0][0]
        print(f"[SENSOR DETECT] Found {len(nearby_pipes)} pipes near ({position.x():.1f}, {position.y():.1f}), closest at distance {closest_distance:.1f}")
        
        # Extract properties from closest pipe
        circuit_label = closest_pipe.get('circuit_label', 'None')
        
        # If the pipe itself doesn't have a circuit label, try tracing through its connections
        if circuit_label == 'None':
            start_comp_id = closest_pipe.get('start_component_id')
            end_comp_id = closest_pipe.get('end_component_id')
            
            # Try tracing backward from start
            if start_comp_id and start_comp_id in self.component_items:
                traced = self._trace_backward_through_network(start_comp_id, visited=set())
                if traced != 'None':
                    circuit_label = traced
            
            # If still None, try tracing forward from end
            if circuit_label == 'None' and end_comp_id and end_comp_id in self.component_items:
                traced = self._trace_forward_through_network(end_comp_id, visited=set())
                if traced != 'None':
                    circuit_label = traced
        
        detected_props = {
            'fluid_state': closest_pipe.get('fluid_state', 'any'),
            'pressure_side': closest_pipe.get('pressure_side', 'any'),
            'circuit_label': circuit_label,
            'detected': True
        }
        
        return detected_props
    
    def view_mouse_press_event(self, event):
        """Handle mouse clicks for component placement and pipe drawing."""
        # Right button - cancel pipe drawing
        if event.button() == Qt.MouseButton.RightButton:
            if self.pipe_start_port is not None:
                # Reset visual feedback
                try:
                    self.pipe_start_port.setScale(1.0)
                except RuntimeError:
                    pass
                self.pipe_start_port = None
                print("[CANCEL] Right-click cancelled pipe drawing")
                return
        
        # Middle button for panning
        if event.button() == Qt.MouseButton.MiddleButton:
            self.is_panning = True
            self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            # Create fake LEFT button event (ScrollHandDrag only responds to left button)
            # Preserve position, buttons state, and modifiers from middle button event
            fake_event = QMouseEvent(
                QEvent.Type.MouseButtonPress,
                event.position(),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,  # buttons() - only left button is pressed
                event.modifiers()
            )
            QGraphicsView.mousePressEvent(self.view, fake_event)
            return
        
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.view.mapToScene(event.pos())
            
            # Check if clicking on a port
            item = self.scene.itemAt(scene_pos, self.view.transform())
            
            from diagram_components import PortItem
            if isinstance(item, PortItem):
                if not self._edit_layout_enabled():
                    print("[PIPE] Ignored port click because Edit layout is off")
                    QGraphicsView.mousePressEvent(self.view, event)
                    return
                # Port clicked - pipe mode
                if self.pipe_start_port is None:
                    self.pipe_start_port = item
                    # Visual feedback - make selected port larger
                    item.setScale(1.5)
                    print(f"[PIPE] Start: {item.parent_component.component_data.get('type')}.{item.port_name} (Press ESC to cancel)")
                else:
                    # Create pipe
                    print(f"[PIPE] End: {item.parent_component.component_data.get('type')}.{item.port_name}")
                    # Reset visual feedback (guard if item was deleted)
                    try:
                        if self.pipe_start_port:
                            self.pipe_start_port.setScale(1.0)
                    except RuntimeError:
                        pass
                    self.create_pipe(self.pipe_start_port, item)
                    self.pipe_start_port = None
                return
            else:
                # Extra diagnostics when clicking near ports but not hitting them
                if item:
                    print(f"[CLICK] Clicked on: {type(item).__name__}")
                else:
                    print(f"[CLICK] Clicked on empty space at ({scene_pos.x():.1f}, {scene_pos.y():.1f})")
            
            # Place custom sensor point if sensor mode is active
            if self.custom_sensor_mode:
                # Check if a sensor is selected - if so, remove any old custom sensor points for this sensor
                selected_sensors = list(self.data_manager.selected_sensors)
                selected_sensor = None
                
                if selected_sensors:
                    selected_sensor = selected_sensors[-1]  # Get the most recently selected sensor
                    print(f"[SENSOR PLACE] Selected sensor: '{selected_sensor}'")
                    
                    # Find all existing custom sensor points mapped to this sensor
                    old_custom_roles = self.data_manager.get_custom_sensor_roles_for_sensor(selected_sensor)
                    
                    if old_custom_roles:
                        print(f"[SENSOR MOVE] Found {len(old_custom_roles)} existing custom sensor point(s) for '{selected_sensor}'")
                        for old_role in old_custom_roles:
                            print(f"[SENSOR MOVE] Removing old custom sensor: {old_role}")
                            
                            # Remove from custom_sensor_points
                            if old_role in self.custom_sensor_points:
                                del self.custom_sensor_points[old_role]
                                print(f"[SENSOR MOVE]   - Removed from custom_sensor_points")
                            
                            # Remove from diagram model
                            if 'custom_sensors' in self.data_manager.diagram_model:
                                if old_role in self.data_manager.diagram_model['custom_sensors']:
                                    del self.data_manager.diagram_model['custom_sensors'][old_role]
                                    print(f"[SENSOR MOVE]   - Removed from diagram_model")
                            
                            # Remove the mapping
                            self.data_manager.unmap_role(old_role)
                            print(f"[SENSOR MOVE]   - Unmapped role")
                    else:
                        print(f"[SENSOR PLACE] No existing custom sensor points found for '{selected_sensor}' (this is the first placement)")
                else:
                    print(f"[SENSOR PLACE] No sensor selected - creating unmapped custom sensor point")
                
                sensor_id = f"custom_{self.custom_sensor_mode}_{uuid.uuid4().hex[:6]}"
                print(f"[SENSOR PLACE] Creating new custom sensor with ID: {sensor_id}")
                
                # Auto-detect nearby pipe properties (within 50 pixels)
                detected_props = self._detect_nearby_pipe_properties(scene_pos, radius=50)
                
                # Create sensor with detected properties
                sensor_data = {
                    'type': self.custom_sensor_mode,
                    'position': [scene_pos.x(), scene_pos.y()],
                    'label': self.custom_sensor_mode,
                    'fluid_state': detected_props['fluid_state'],
                    'pressure_side': detected_props['pressure_side'],
                    'circuit_label': detected_props['circuit_label'],
                    'auto_detected': detected_props['detected']
                }
                
                self.custom_sensor_points[sensor_id] = sensor_data
                
                # Store in diagram model for persistence
                if 'custom_sensors' not in self.data_manager.diagram_model:
                    self.data_manager.diagram_model['custom_sensors'] = {}
                self.data_manager.diagram_model['custom_sensors'][sensor_id] = sensor_data
                
                # Enhanced logging (before clearing mode)
                sensor_type_display = self.custom_sensor_mode
                if detected_props['detected']:
                    print(f"[SENSOR PLACE] Placed {sensor_type_display} at ({scene_pos.x():.1f}, {scene_pos.y():.1f})")
                    print(f"[SENSOR PLACE]   -> Circuit: {detected_props['circuit_label']} | Pressure: {detected_props['pressure_side']} | Fluid: {detected_props['fluid_state']}")
                else:
                    print(f"[SENSOR PLACE] Placed {sensor_type_display} at ({scene_pos.x():.1f}, {scene_pos.y():.1f}) - NO DETECTION")
                
                # Auto-map to selected sensor if one is selected
                if selected_sensor:
                    self.data_manager.map_sensor_to_role(sensor_id, selected_sensor)
                    print(f"[SENSOR PLACE] Auto-mapped '{selected_sensor}' to custom sensor point {sensor_id}")
                    # Keep the sensor selected so user can move it again if needed
                else:
                    print(f"[SENSOR PLACE] No auto-mapping (no sensor selected)")
                
                self.custom_sensor_mode = None
                self.build_scene_from_model()
                return
            
            # Place sensor box if mode is active
            if self.sensor_box_mode:
                box_id = self.data_manager.add_sensor_box(scene_pos)
                self.sensor_box_mode = False
                print(f"[BOX PLACE] Placed sensor box at ({scene_pos.x():.1f}, {scene_pos.y():.1f})")
                return
            
            # Place component if tool is active
            if self.current_tool:
                comp_id = self.data_manager.add_component_to_model(self.current_tool, scene_pos)
                self.current_tool = None
                self.build_scene_from_model()
                # Auto-open PropertyDialog for the new component
                if comp_id in self.component_items:
                    self.on_component_double_clicked(self.component_items[comp_id])
                return
            
            # If we reach here and none of the special modes are active,
            # let the default behavior handle component selection
            if not self.pipe_start_port and not self.custom_sensor_mode and not self.current_tool and not self.sensor_box_mode:
                # Default behavior for component selection
                QGraphicsView.mousePressEvent(self.view, event)
                return
        
        # Default behavior for all other cases
        QGraphicsView.mousePressEvent(self.view, event)
    
    def create_group(self, components):
        """Create a group - simpler approach using IDs."""
        group_id = self.next_group_id
        self.next_group_id += 1
        
        # Store component IDs in the group
        comp_ids = [comp.component_id for comp in components]
        self.groups[group_id] = comp_ids
        
        # Mark each component as grouped
        for comp in components:
            comp.group_id = group_id
            comp.setOpacity(0.9)  # Slightly transparent to show grouped
        
        # Don't show border yet - will show when selected
        
        print(f"[GROUP] Created group {group_id} with {len(comp_ids)} component(s)")
    
    def hide_all_group_borders(self):
        """Hide all group borders."""
        items_to_remove = []
        for item in self.scene.items():
            if hasattr(item, 'is_group_border'):
                items_to_remove.append(item)
        for item in items_to_remove:
            self.scene.removeItem(item)
    
    def update_group_visual(self, group_id):
        """Update or create visual border for a group (only shown when selected)."""
        if group_id not in self.groups:
            return
        
        # Remove old border if exists
        for item in self.scene.items():
            if hasattr(item, 'is_group_border') and item.group_border_id == group_id:
                self.scene.removeItem(item)
        
        # Get all components in the group
        group_components = []
        for comp_id in self.groups[group_id]:
            if comp_id in self.component_items:
                group_components.append(self.component_items[comp_id])
        
        if not group_components:
            return
        
        # Calculate bounding rect for all components
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')
        
        for comp in group_components:
            try:
                rect = comp.sceneBoundingRect()
                min_x = min(min_x, rect.left())
                min_y = min(min_y, rect.top())
                max_x = max(max_x, rect.right())
                max_y = max(max_y, rect.bottom())
            except RuntimeError:
                # Component was deleted
                continue
        
        # Create border with padding
        padding = 10
        border = QGraphicsRectItem(
            min_x - padding,
            min_y - padding,
            max_x - min_x + 2 * padding,
            max_y - min_y + 2 * padding
        )
        border.setPen(QPen(QColor("#FFA500"), 2, Qt.PenStyle.DashLine))
        border.setBrush(QBrush(Qt.GlobalColor.transparent))
        border.setZValue(-1)
        border.is_group_border = True
        border.group_border_id = group_id
        self.scene.addItem(border)
        
        print(f"[GROUP] Updated visual for group {group_id}")
    
    def ungroup_by_id(self, group_id):
        """Ungroup components by group ID."""
        if group_id not in self.groups:
            return
        
        # Remove group marking from components
        for comp_id in self.groups[group_id]:
            if comp_id in self.component_items:
                comp = self.component_items[comp_id]
                if hasattr(comp, 'group_id'):
                    delattr(comp, 'group_id')
                comp.setOpacity(1.0)  # Restore full opacity
        
        # Remove visual border
        for item in self.scene.items():
            if hasattr(item, 'is_group_border') and item.group_border_id == group_id:
                self.scene.removeItem(item)
        
        # Remove group from tracking
        del self.groups[group_id]
        
        print(f"[UNGROUP] Group {group_id} ungrouped")
    
    def ungroup(self, item):
        """Ungroup - check if item is in a group and ungroup it."""
        if hasattr(item, 'group_id'):
            self.ungroup_by_id(item.group_id)
    
    def create_pipe(self, start_port, end_port):
        """Create a pipe connection between two ports."""
        start_comp = start_port.parent_component
        end_comp = end_port.parent_component
        
        # Validation
        if start_comp == end_comp:
            print("[PIPE] Cannot connect to same component")
            return
        
        if start_port.port_name == end_port.port_name:
            print("[PIPE] Cannot connect same port")
            return
        
        # Check fluid state compatibility - with intelligent tracing for junctions
        start_state = self._get_effective_fluid_state(start_comp, start_port)
        end_state = self._get_effective_fluid_state(end_comp, end_port)
        
        if start_state == 'any' or end_state == 'any':
            # If both are 'any', try to trace through the network to find a concrete value
            if start_state == 'any' and end_state == 'any':
                # Try to trace from both ends to find a concrete fluid state
                traced_fluid = self._trace_fluid_through_connection(start_comp, start_port, end_comp, end_port)
                fluid_state = traced_fluid if traced_fluid != 'any' else 'any'
            else:
                fluid_state = start_state if start_state != 'any' else end_state
        elif start_state == end_state:
            fluid_state = start_state
        else:
            # Lenient: allow pipe creation and default fluid to 'any'
            print(f"[PIPE] Fluid state mismatch: {start_state} vs {end_state} -> defaulting to 'any'")
            fluid_state = 'any'
        
        # Determine pressure side using effective tracing (direction-independent)
        start_pressure = self._get_effective_pressure_side(start_comp, start_port)
        end_pressure = self._get_effective_pressure_side(end_comp, end_port)
        
        if start_pressure == 'any' or end_pressure == 'any':
            # If both are 'any', try to trace through the network to find a concrete value
            if start_pressure == 'any' and end_pressure == 'any':
                # Try to trace from both ends to find a concrete pressure side
                traced_pressure = self._trace_pressure_through_connection(start_comp, start_port, end_comp, end_port)
                print(f"[PIPE TRACE] Traced pressure: {traced_pressure} for {start_comp.component_id}.{start_port.port_name} -> {end_comp.component_id}.{end_port.port_name}")
                pressure_side = traced_pressure if traced_pressure != 'any' else 'any'
            else:
                pressure_side = start_pressure if start_pressure != 'any' else end_pressure
        elif start_pressure == end_pressure:
            pressure_side = start_pressure
        else:
            # Lenient: allow creation and default to 'any' on mismatch
            print(f"[PIPE] Pressure mismatch: {start_pressure} vs {end_pressure} -> defaulting to 'any'")
            pressure_side = 'any'
        
        # Determine circuit label from connected components - with intelligent tracing through junctions
        circuit_label = self._trace_circuit_label(start_comp, start_port, end_comp, end_port)
        
        # Create pipe
        pipe_id = self.data_manager.add_pipe_to_model(
            start_comp.component_id,
            start_port.port_name,
            end_comp.component_id,
            end_port.port_name,
            fluid_state,
            pressure_side,
            circuit_label
        )
        
        # Enhanced logging
        start_type = start_comp.component_data.get('type')
        end_type = end_comp.component_data.get('type')
        print(f"[PIPE] Created: {start_type}->{end_type} | Fluid: {fluid_state} | Pressure: {pressure_side} | Circuit: {circuit_label}")
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        # Escape - Cancel everything and deselect
        if event.key() == Qt.Key.Key_Escape:
            # Cancel pipe drawing
            if self.pipe_start_port is not None:
                # Reset visual feedback
                try:
                    self.pipe_start_port.setScale(1.0)
                except RuntimeError:
                    pass
                self.pipe_start_port = None
                print("[ESC] Cancelled pipe drawing")
            
            # Cancel custom sensor placement
            if self.custom_sensor_mode is not None:
                self.custom_sensor_mode = None
                print("[ESC] Cancelled sensor placement")
            
            # Cancel component placement
            if self.current_tool is not None:
                self.current_tool = None
                print("[ESC] Cancelled component placement")
            
            # Deselect all items
            self.scene.clearSelection()
            print("[ESC] Deselected all items")
            return
        
        # Space bar - enable panning mode
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if not self.is_panning:
                self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
                self.is_panning = True
                print("[PAN] Panning mode ON (hold Space + drag)")
            return
        
        # Delete
        if event.key() == Qt.Key.Key_Delete:
            selected_items = self.scene.selectedItems()
            
            # Delete components (including Junction, TXV, Distributor)
            comp_ids_to_delete = []
            for item in selected_items:
                if isinstance(item, (BaseComponentItem, JunctionComponentItem, TXVComponentItem, DistributorComponentItem, SensorBulbComponentItem, FanComponentItem, AirSensorArrayComponentItem, ShelvingGridComponentItem, HotGasBypassItem, HotGasLoopItem, SensorComponentItem, RemoteLineEndpointItem)):
                    comp_ids_to_delete.append(item.component_id)
            
            if comp_ids_to_delete:
                # Clean up groups that contain deleted components
                for comp_id in comp_ids_to_delete:
                    for group_id, comp_ids in list(self.groups.items()):
                        if comp_id in comp_ids:
                            # Remove component from group
                            self.groups[group_id].remove(comp_id)
                            # If group now has less than 2 components, dissolve it
                            if len(self.groups[group_id]) < 2:
                                self.ungroup_by_id(group_id)
                
                self.data_manager.remove_components_from_model(comp_ids_to_delete)
                print(f"[DELETE] Removed {len(comp_ids_to_delete)} component(s)")
            
            # Delete pipes
            pipe_ids_to_delete = []
            for item in selected_items:
                if isinstance(item, PipeItem):
                    pipe_ids_to_delete.append(item.pipe_id)
            
            if pipe_ids_to_delete:
                self.data_manager.remove_pipes_from_model(pipe_ids_to_delete)
                print(f"[DELETE] Removed {len(pipe_ids_to_delete)} pipe(s)")
        
        # Group (Ctrl+G)
        elif event.key() == Qt.Key.Key_G and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            selected_items = self.scene.selectedItems()
            components_to_group = [item for item in selected_items
                                 if isinstance(item, (BaseComponentItem, JunctionComponentItem, TXVComponentItem, DistributorComponentItem, SensorBulbComponentItem, FanComponentItem, AirSensorArrayComponentItem, ShelvingGridComponentItem, HotGasBypassItem, HotGasLoopItem, SensorComponentItem, RemoteLineEndpointItem))]
            
            if len(components_to_group) >= 2:
                self.create_group(components_to_group)
                print(f"[GROUP] Created group with {len(components_to_group)} component(s)")
            else:
                print("[GROUP] Select at least 2 components to group")
        
        # Ungroup (Ctrl+Shift+G)
        elif event.key() == Qt.Key.Key_G and event.modifiers() == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            selected_items = self.scene.selectedItems()
            for item in selected_items:
                if hasattr(item, 'group_id'):
                    self.ungroup_by_id(item.group_id)
                    return
        
        # Straighten Pipes (Ctrl+L)
        elif event.key() == Qt.Key.Key_L and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self._straighten_selected_pipes()

        # Select All (Ctrl+A)
        elif event.key() == Qt.Key.Key_A and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            for item in self.scene.items():
                if isinstance(item, (BaseComponentItem, JunctionComponentItem, TXVComponentItem, DistributorComponentItem, PipeItem, SensorBulbComponentItem, FanComponentItem, AirSensorArrayComponentItem, ShelvingGridComponentItem, HotGasBypassItem, HotGasLoopItem, SensorComponentItem, RemoteLineEndpointItem)):
                    item.setSelected(True)
            print("[SELECT ALL] All items selected")
        
        # Copy (Ctrl+C)
        elif event.key() == Qt.Key.Key_C and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            selected_items = self.scene.selectedItems()
            self.clipboard_components = []
            self.clipboard_pipes = []
            self.clipboard_was_grouped = False
            
            # Collect all selected components
            selected_comp_ids = set()
            for item in selected_items:
                if isinstance(item, (BaseComponentItem, JunctionComponentItem, TXVComponentItem, DistributorComponentItem, SensorBulbComponentItem, FanComponentItem, AirSensorArrayComponentItem, ShelvingGridComponentItem, HotGasBypassItem, HotGasLoopItem, SensorComponentItem, RemoteLineEndpointItem)):
                    comp_data = {
                        'type': item.component_data['type'],
                        'properties': item.component_data.get('properties', {}).copy(),
                        'size': item.component_data.get('size', {'width': 100, 'height': 60}).copy() if 'size' in item.component_data else None,
                        'rotation': item.component_data.get('rotation', 0),
                        'position': item.scenePos(),
                        'comp_id': item.component_id
                    }
                    self.clipboard_components.append(comp_data)
                    selected_comp_ids.add(item.component_id)
            
                    # Check if this component is in a group
                    if hasattr(item, 'group_id'):
                        self.clipboard_was_grouped = True
            
            # Collect all pipes between selected components
            if self.clipboard_components:
                for pipe_id, pipe_data in self.data_manager.diagram_model.get('pipes', {}).items():
                    start_id = pipe_data['start_component_id']
                    end_id = pipe_data['end_component_id']
                    # Only copy pipes where both ends are in selection
                    if start_id in selected_comp_ids and end_id in selected_comp_ids:
                        pipe_copy = {
                            'start_component_id': start_id,
                            'end_component_id': end_id,
                            'start_port': pipe_data['start_port'],
                            'end_port': pipe_data['end_port'],
                            'route': [list(p) for p in pipe_data.get('route') or []],
                            'waypoints': pipe_data.get('waypoints', []).copy() if 'waypoints' in pipe_data else []
                        }
                        self.clipboard_pipes.append(pipe_copy)
                
                print(f"[COPY] {len(self.clipboard_components)} component(s) and {len(self.clipboard_pipes)} pipe(s) copied")
        
        # Paste (Ctrl+V)
        elif event.key() == Qt.Key.Key_V and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if self.clipboard_components:
                # Map old component IDs to new ones
                id_mapping = {}
                
                # Create all components first
                for comp_data in self.clipboard_components:
                    orig_pos = comp_data.get('position', [0, 0])
                    
                    # Handle both QPointF and list formats
                    if isinstance(orig_pos, QPointF):
                        offset_pos = QPointF(orig_pos.x() + 100, orig_pos.y() + 100)
                    else:
                        offset_pos = QPointF(orig_pos[0] + 100, orig_pos[1] + 100)
                    
                    new_comp_id = self.data_manager.add_component_to_model(comp_data['type'], offset_pos)
                    
                    new_comp = self.data_manager.diagram_model['components'][new_comp_id]
                    new_comp['properties'] = comp_data['properties'].copy()
                    if comp_data['size']:
                        new_comp['size'] = comp_data['size'].copy()
                        new_comp['rotation'] = comp_data['rotation']
                    
                    # Store mapping
                    id_mapping[comp_data['comp_id']] = new_comp_id
                
                # Create all pipes with new component IDs
                if hasattr(self, 'clipboard_pipes') and self.clipboard_pipes:
                    for pipe_data in self.clipboard_pipes:
                        old_start = pipe_data['start_component_id']
                        old_end = pipe_data['end_component_id']
                        
                        # Map to new IDs
                        new_start = id_mapping.get(old_start)
                        new_end = id_mapping.get(old_end)
                        
                        if new_start and new_end:
                            # Create pipe in model
                            pipe_id = f"pipe_{uuid.uuid4().hex[:8]}"
                            new_pipe = {
                                'start_component_id': new_start,
                                'end_component_id': new_end,
                                'start_port': pipe_data['start_port'],
                                'end_port': pipe_data['end_port'],
                                'route': [[p[0] + 100, p[1] + 100] for p in pipe_data.get('route') or []],
                                'waypoints': [[wp[0] + 100, wp[1] + 100] for wp in pipe_data['waypoints']]
                            }
                            self.data_manager.diagram_model['pipes'][pipe_id] = new_pipe
                
                # If original was grouped, create a group for pasted components BEFORE rebuild
                new_comp_ids = list(id_mapping.values())
                should_group = hasattr(self, 'clipboard_was_grouped') and self.clipboard_was_grouped and len(new_comp_ids) >= 2
                
                self.build_scene_from_model()
                
                # Create group for pasted components after scene is rebuilt
                if should_group:
                    # Get the newly created component items
                    pasted_components = []
                    for new_id in new_comp_ids:
                        if new_id in self.component_items:
                            pasted_components.append(self.component_items[new_id])
                    
                    if len(pasted_components) >= 2:
                        self.create_group(pasted_components)
                        print(f"[PASTE] Created group for pasted components")
                
                print(f"[PASTE] {len(self.clipboard_components)} component(s) and {len(self.clipboard_pipes) if hasattr(self, 'clipboard_pipes') else 0} pipe(s) pasted")

                # Auto-open PropertyDialog for each pasted component
                for new_id in new_comp_ids:
                    if new_id in self.component_items:
                        self.on_component_double_clicked(self.component_items[new_id])
        
        super().keyPressEvent(event)
    
    def keyReleaseEvent(self, event):
        """Handle key release events."""
        # Space bar released - restore selection mode
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if self.is_panning:
                self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
                self.is_panning = False
                print("[PAN] Panning mode OFF")
            return
        
        super().keyReleaseEvent(event)
    
    def on_scene_selection_changed(self):
        """Update property editor when selection changes - handle groups."""
        selected_items = self.scene.selectedItems()
        
        # Hide all group borders first
        self.hide_all_group_borders()
        
        # If a pipe is selected, don't interfere with group selection
        has_pipe_selected = any(isinstance(item, PipeItem) for item in selected_items)
        
        if not has_pipe_selected:
            # Check if any selected component is in a group - if so, select entire group
            selected_group_id = None
            for item in selected_items[:]:  # Copy list to avoid modification during iteration
                if isinstance(item, (BaseComponentItem, JunctionComponentItem, TXVComponentItem, DistributorComponentItem, SensorBulbComponentItem, FanComponentItem, AirSensorArrayComponentItem, ShelvingGridComponentItem)):
                    if hasattr(item, 'group_id'):
                        # Select all components in the same group
                        group_id = item.group_id
                        selected_group_id = group_id
                        for comp_id in self.groups.get(group_id, []):
                            if comp_id in self.component_items:
                                try:
                                    self.component_items[comp_id].setSelected(True)
                                except RuntimeError:
                                    pass  # Item was deleted
                        print(f"[SELECTED] Group {group_id} selected")
                        break
            
            # Show border only for selected group
            if selected_group_id:
                self.update_group_visual(selected_group_id)
                return
        
        # Normal selection handling
        if len(selected_items) == 1:
            item = selected_items[0]
            if isinstance(item, (BaseComponentItem, JunctionComponentItem, TXVComponentItem, DistributorComponentItem, SensorBulbComponentItem, FanComponentItem, AirSensorArrayComponentItem, ShelvingGridComponentItem)):
                print(f"[SELECTED] {item.component_data['type']} ({item.component_id})")
                if self.property_editor:
                    self.property_editor.show_properties(item)
            elif isinstance(item, PipeItem):
                print(f"[SELECTED] Pipe ({item.pipe_id})")
                # Extra diagnostics for pipe selection
                try:
                    pd = item.pipe_data
                    print(f"[SELECT] fluid={pd.get('fluid_state')} pressure={pd.get('pressure_side')} circuit={pd.get('circuit_label')} waypoints={len(pd.get('waypoints', []))}")
                    print(f"[SELECT] start={pd.get('start_component_id')}.{pd.get('start_port')} -> end={pd.get('end_component_id')}.{pd.get('end_port')}")
                except Exception as e:
                    print(f"[SELECT] Error printing pipe: {e}")
                if self.property_editor:
                    self.property_editor.show_pipe_properties(item)
        elif len(selected_items) > 1:
            # Check if all selected items are pipes
            selected_pipes = [item for item in selected_items if isinstance(item, PipeItem)]
            if selected_pipes and len(selected_pipes) == len(selected_items):
                print(f"[SELECTED] {len(selected_pipes)} pipes")
                if self.property_editor:
                    self.property_editor.show_multiple_pipe_properties(selected_pipes)
            else:
                if self.property_editor:
                    self.property_editor.show_properties(None)
        else:
            if self.property_editor:
                self.property_editor.show_properties(None)
    
    def on_component_double_clicked(self, component_item):
        """Handle double-click on a component - open property dialog."""
        from diagram_components import (BaseComponentItem, JunctionComponentItem, TXVComponentItem, 
                                       DistributorComponentItem, SensorBulbComponentItem, 
                                       FanComponentItem, AirSensorArrayComponentItem, ShelvingGridComponentItem,
                                       SensorComponentItem)
        
        # Only handle component items (not pipes or other items)
        if not isinstance(component_item, (BaseComponentItem, JunctionComponentItem, TXVComponentItem, 
                                          DistributorComponentItem, SensorBulbComponentItem, 
                                          FanComponentItem, AirSensorArrayComponentItem, ShelvingGridComponentItem,
                                          SensorComponentItem)):
            return
        
        # Open the property dialog
        dialog = PropertyDialog(self.data_manager, component_item, self)
        result = dialog.exec()
        
        if result == QDialog.DialogCode.Accepted:
            print(f"[PROPERTY DIALOG] Changes accepted for {component_item.component_data['type']}")
            # Refresh tooltips on the component and its ports
            if hasattr(component_item, 'update_tooltip'):
                component_item.update_tooltip()
            for port in component_item.ports.values():
                if hasattr(port, '_update_tooltip'):
                    port._update_tooltip()
        else:
            print(f"[PROPERTY DIALOG] Changes cancelled for {component_item.component_data['type']}")
    
    # Sensor box callback methods
    def on_sensor_box_double_clicked(self, box_item):
        """Handle double-click on sensor box."""
        print(f"[BOX DOUBLE-CLICK] Sensor box '{box_item.title}' clicked")
    
    def on_add_sensor_to_box(self, box_item):
        """Handle adding a sensor to sensor box."""
        from PyQt6.QtWidgets import QInputDialog
        
        label, ok = QInputDialog.getText(self, "Add Sensor", "Sensor Label:")
        if ok and label:
            sensor_id = self.data_manager.add_sensor_to_box(box_item.box_id, label)
            if sensor_id:
                print(f"[BOX] Added sensor '{label}' to box")
                self.build_scene_from_model()
    
    def on_edit_box_title(self, box_item):
        """Handle editing sensor box title."""
        from PyQt6.QtWidgets import QInputDialog
        
        title, ok = QInputDialog.getText(self, "Edit Header", "Header:", text=box_item.title)
        if ok and title:
            self.data_manager.update_sensor_box_title(box_item.box_id, title)
            box_item.edit_title(title)
            self.build_scene_from_model()
    
    def on_delete_sensor_box(self, box_item):
        """Handle deleting sensor box."""
        from PyQt6.QtWidgets import QMessageBox
        
        reply = QMessageBox.question(
            self, 
            "Delete Box", 
            f"Delete '{box_item.title}' and all its sensors?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.data_manager.remove_sensor_box(box_item.box_id)
            self.build_scene_from_model()
            print(f"[BOX] Deleted sensor box '{box_item.title}'")


class SensorDot(QFrame):
    """Clickable sensor role dot overlay used in Mapping mode."""
    def __init__(self, data_manager, role_key, label_text):
        super().__init__()
        self.data_manager = data_manager
        self.role_key = role_key
        self.label_text = label_text
        # Graphics proxy via QGraphicsView expects QGraphicsItem; use simple ellipse via QGraphicsView painting
        # We'll render as a small circle using a lightweight QGraphicsItem-like pattern
        from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsTextItem
        from PyQt6.QtGui import QBrush, QPen
        from PyQt6.QtCore import Qt
        self.dot_item = QGraphicsEllipseItem(-6, -6, 12, 12)
        self.dot_item.setBrush(QBrush(QColor('#ff5722')))
        self.dot_item.setPen(QPen(Qt.GlobalColor.black, 1))
        self.dot_item.setZValue(100)
        self.text_item = QGraphicsTextItem(label_text)
        self.text_item.setDefaultTextColor(QColor('#000'))
        self.text_item.setZValue(100)
        self.text_item.setPos(8, -6)
        # Attach mouse events
        self.dot_item.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.dot_item.mousePressEvent = self.on_mouse_press

    def setPos(self, pos):
        self.dot_item.setPos(pos)
        self.text_item.setPos(pos + QPointF(8, -6))

    def scene(self):
        # Provide accessors used by caller
        return self.dot_item.scene()

    def on_mouse_press(self, event):
        # Map currently selected sensor (if any) to this role
        selected = list(self.data_manager.selected_sensors)
        if selected:
            sensor_name = selected[-1]
            print(f"[MAP] Attempting to map {sensor_name} to {self.role_key}")
            self.data_manager.map_sensor_to_role(self.role_key, sensor_name)
            print(f"[MAP] Successfully mapped {sensor_name} to {self.role_key}")
            # Debug: Show current mapping status
            self.data_manager.debug_sensor_mappings()
        event.accept()

