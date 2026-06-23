"""
diagram_widget_simple.py - Simplified Interactive Diagram Designer

Inspired by the clarity of the HTML version - single file, easy to understand.
Features:
- Click component buttons to add to canvas
- Drag components to move them
- Click ports to draw connections
- Delete with Delete key
- Simple property editing
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QGraphicsView, QGraphicsScene, QFrame,
                             QFormLayout, QLineEdit, QSpinBox, QComboBox)
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsTextItem, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsItem
from PyQt6.QtGui import QPainterPath

from component_schemas import SCHEMAS


# ============================================================================
# SIMPLE COMPONENTS
# ============================================================================

class SimplePort(QGraphicsEllipseItem):
    """A simple connection port - just a colored dot."""
    
    def __init__(self, name, port_def, parent_component):
        super().__init__(-4, -4, 8, 8)
        self.port_name = name
        self.port_def = port_def
        self.parent_component = parent_component
        self.connected_lines = []
        
        # Simple color coding
        fluid = port_def.get('fluid_state', 'any')
        colors = {
            'gas': '#FF5722',      # Red
            'liquid': '#2196F3',   # Blue
            'two-phase': '#9C27B0', # Purple
            'any': '#4CAF50'       # Green
        }
        self.setBrush(QBrush(QColor(colors.get(fluid, '#4CAF50'))))
        self.setPen(QPen(Qt.GlobalColor.white, 1))
        self.setParentItem(parent_component)
        self.setZValue(10)
        
    def get_scene_pos(self):
        """Get center position in scene coordinates."""
        return self.scenePos()


class SimpleComponent(QGraphicsRectItem):
    """A simple draggable component block."""
    
    def __init__(self, comp_id, comp_data):
        size = comp_data.get('size', {'width': 100, 'height': 60})
        super().__init__(0, 0, size['width'], size['height'])
        
        self.comp_id = comp_id
        self.comp_data = comp_data
        self.ports = {}
        
        # Simple styling - light blue box with dark border
        self.setBrush(QBrush(QColor("#E3F2FD")))
        self.setPen(QPen(QColor("#1976D2"), 2))
        
        # Label
        self.label = QGraphicsTextItem(comp_data['type'], self)
        self.label.setDefaultTextColor(QColor("#000000"))
        self.label.setPos(5, 5)
        
        # Make it interactive
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        
        # Set position
        pos = comp_data.get('position', [0, 0])
        if isinstance(pos, QPointF):
            self.setPos(pos)
        else:
            self.setPos(pos[0], pos[1])
        
        # Build ports from schema
        self.build_ports()
    
    def build_ports(self):
        """Build all ports from schema."""
        schema = SCHEMAS.get(self.comp_data['type'], {})
        width = self.rect().width()
        height = self.rect().height()
        
        # Fixed ports from schema
        for port_def in schema.get('ports', []):
            name = port_def['name']
            pos = port_def['position']
            x = pos[0] * width
            y = pos[1] * height
            
            port = SimplePort(name, port_def, self)
            port.setPos(x, y)
            self.ports[name] = port
    
    def itemChange(self, change, value):
        """Update connected lines when moved."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.update_connected_lines()
        return super().itemChange(change, value)
    
    def update_connected_lines(self):
        """Update all connected connection lines."""
        for port in self.ports.values():
            for line in port.connected_lines:
                line.update_path()


class SimpleConnectionLine(QGraphicsPathItem):
    """A simple orthogonal connection line between two ports."""
    
    def __init__(self, line_id, start_port, end_port):
        super().__init__()
        self.line_id = line_id
        self.start_port = start_port
        self.end_port = end_port
        
        # Track in ports
        start_port.connected_lines.append(self)
        end_port.connected_lines.append(self)
        
        # Simple styling - colored line
        fluid = start_port.port_def.get('fluid_state', 'any')
        colors = {
            'gas': '#FF5722',
            'liquid': '#2196F3',
            'two-phase': '#9C27B0',
            'any': '#4CAF50'
        }
        self.setPen(QPen(QColor(colors.get(fluid, '#4CAF50')), 3))
        
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(1)
        
        self.update_path()
    
    def update_path(self):
        """Draw simple orthogonal path between ports."""
        start = self.start_port.get_scene_pos()
        end = self.end_port.get_scene_pos()
        
        # Simple right-angle routing
        path = QPainterPath()
        path.moveTo(start)
        mid_x = (start.x() + end.x()) / 2
        path.lineTo(mid_x, start.y())
        path.lineTo(mid_x, end.y())
        path.lineTo(end)
        
        self.setPath(path)


# ============================================================================
# SIMPLE PROPERTY EDITOR
# ============================================================================

class SimplePropertyEditor(QWidget):
    """Simple property editor - just the basics."""
    
    def __init__(self):
        super().__init__()
        self.current_item = None
        self.layout = QFormLayout(self)
        self.layout.addWidget(QLabel("Select a component"))
    
    def show_properties(self, item):
        """Show properties for selected component."""
        # Clear layout
        while self.layout.count():
            child = self.layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        if not item or not isinstance(item, SimpleComponent):
            self.current_item = None
            self.layout.addWidget(QLabel("Select a component"))
            return
        
        self.current_item = item
        schema = SCHEMAS.get(item.comp_data['type'], {})
        
        # Title
        title = QLabel(f"<b>{item.comp_data['type']}</b>")
        self.layout.addRow(title)
        
        # Properties from schema
        for prop_name, prop_schema in schema.get('properties', {}).items():
            prop_type = prop_schema['type']
            current_val = item.comp_data.get('properties', {}).get(prop_name)
            
            if prop_type == 'integer':
                editor = QSpinBox()
                editor.setRange(prop_schema.get('min', 0), prop_schema.get('max', 999))
                editor.setValue(current_val if current_val else prop_schema.get('default', 0))
                editor.valueChanged.connect(lambda v, p=prop_name: self.update_prop(p, v))
                self.layout.addRow(prop_name, editor)
            
            elif prop_type == 'string':
                editor = QLineEdit()
                editor.setText(current_val or prop_schema.get('default', ''))
                editor.textChanged.connect(lambda v, p=prop_name: self.update_prop(p, v))
                self.layout.addRow(prop_name, editor)
            
            elif prop_type == 'enum':
                editor = QComboBox()
                editor.addItems(prop_schema.get('options', []))
                if current_val:
                    editor.setCurrentText(current_val)
                editor.currentTextChanged.connect(lambda v, p=prop_name: self.update_prop(p, v))
                self.layout.addRow(prop_name, editor)
        
        # Size controls
        size = item.comp_data.get('size', {'width': 100, 'height': 60})
        
        width_spin = QSpinBox()
        width_spin.setRange(50, 500)
        width_spin.setValue(size['width'])
        width_spin.valueChanged.connect(self.update_width)
        self.layout.addRow("Width", width_spin)
        
        height_spin = QSpinBox()
        height_spin.setRange(30, 300)
        height_spin.setValue(size['height'])
        height_spin.valueChanged.connect(self.update_height)
        self.layout.addRow("Height", height_spin)
    
    def update_prop(self, prop_name, value):
        """Update property value."""
        if not self.current_item:
            return
        if 'properties' not in self.current_item.comp_data:
            self.current_item.comp_data['properties'] = {}
        self.current_item.comp_data['properties'][prop_name] = value
    
    def update_width(self, width):
        """Update component width."""
        if not self.current_item:
            return
        size = self.current_item.comp_data.get('size', {'width': 100, 'height': 60})
        size['width'] = width
        self.current_item.setRect(0, 0, width, size['height'])
        self.current_item.build_ports()
        self.current_item.update_connected_lines()
    
    def update_height(self, height):
        """Update component height."""
        if not self.current_item:
            return
        size = self.current_item.comp_data.get('size', {'width': 100, 'height': 60})
        size['height'] = height
        self.current_item.setRect(0, 0, size['width'], height)
        self.current_item.build_ports()
        self.current_item.update_connected_lines()


# ============================================================================
# SIMPLE DIAGRAM WIDGET
# ============================================================================

class SimpleDiagramWidget(QWidget):
    """
    Simplified diagram designer - inspired by HTML version.
    
    Like the HTML version:
    - Left panel with component buttons
    - Right canvas area
    - Click to add components
    - Click ports to connect
    - Clear and simple
    """
    
    def __init__(self, data_manager):
        super().__init__()
        self.data_manager = data_manager
        self.components = {}
        self.lines = {}
        
        self.current_tool = None
        self.connecting_from_port = None
        
        self.setup_ui()
        self.connect_signals()
    
    def setup_ui(self):
        """Setup the UI - left palette, right canvas."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Left Panel - Component Palette (like HTML version)
        left_panel = QFrame()
        left_panel.setStyleSheet("""
            QFrame {
                background: white;
                border-right: 1px solid #ccc;
            }
        """)
        left_panel.setFixedWidth(250)
        left_layout = QVBoxLayout(left_panel)
        
        # Title
        title = QLabel("<h2>Components</h2>")
        left_layout.addWidget(title)
        
        subtitle = QLabel("Click to add to canvas")
        subtitle.setStyleSheet("color: #666;")
        left_layout.addWidget(subtitle)
        
        left_layout.addSpacing(10)
        
        # Component buttons (like HTML)
        components = [
            ("Compressor", "#475569"),
            ("Condenser", "#3B82F6"),
            ("TXV", "#F59E0B"),
            ("Distributor", "#10B981"),
            ("Evaporator", "#06B6D4"),
        ]
        
        for name, color in components:
            if name in SCHEMAS:
                btn = QPushButton(name)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {color};
                        color: white;
                        border: none;
                        border-radius: 6px;
                        padding: 12px;
                        font-weight: bold;
                        text-align: left;
                    }}
                    QPushButton:hover {{
                        background: {color};
                        filter: brightness(110%);
                    }}
                """)
                btn.clicked.connect(lambda checked, n=name: self.set_tool(n))
                left_layout.addWidget(btn)
        
        left_layout.addStretch()
        
        # Clear button at bottom
        clear_btn = QPushButton("Clear Canvas")
        clear_btn.setStyleSheet("""
            QPushButton {
                background: #EF4444;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #DC2626;
            }
        """)
        clear_btn.clicked.connect(self.clear_canvas)
        left_layout.addWidget(clear_btn)
        
        # Right Panel - Canvas
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Canvas header
        header = QFrame()
        header.setStyleSheet("background: white; padding: 10px;")
        header_layout = QHBoxLayout(header)
        header_title = QLabel("<h2>Diagram Canvas</h2>")
        header_layout.addWidget(header_title)
        right_layout.addWidget(header)
        
        # Graphics view with grid background (like HTML)
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setStyleSheet("""
            QGraphicsView {
                background: qlineargradient(x1:0, y1:0, x2:20, y2:20,
                    stop:0 #f5f5f5, stop:0.05 #f5f5f5,
                    stop:0.05 #e0e0e0, stop:0.1 #e0e0e0,
                    stop:0.1 #f5f5f5);
                background-repeat: repeat;
            }
        """)
        right_layout.addWidget(self.view)
        
        # Assemble
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, 1)
    
    def connect_signals(self):
        """Connect signals."""
        self.data_manager.diagram_model_changed.connect(self.rebuild_scene)
        self.scene.selectionChanged.connect(self.on_selection_changed)
        self.view.mousePressEvent = self.canvas_clicked
    
    def set_tool(self, tool_name):
        """Set active component placement tool."""
        self.current_tool = tool_name
        self.connecting_from_port = None
        print(f"[TOOL] {tool_name}")
    
    def canvas_clicked(self, event):
        """Handle canvas clicks - place components or connect ports."""
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.view.mapToScene(event.pos())
            item = self.scene.itemAt(scene_pos, self.view.transform())
            
            # Check if clicking a port
            if isinstance(item, SimplePort):
                if self.connecting_from_port is None:
                    # Start connection
                    self.connecting_from_port = item
                    print(f"[CONNECT] Started from {item.port_name}")
                else:
                    # Complete connection
                    self.create_connection(self.connecting_from_port, item)
                    self.connecting_from_port = None
                return
            
            # Place component if tool active
            if self.current_tool:
                self.data_manager.add_component_to_model(self.current_tool, scene_pos)
                self.current_tool = None
                return
        
        # Default behavior
        QGraphicsView.mousePressEvent(self.view, event)
    
    def create_connection(self, start_port, end_port):
        """Create connection between two ports."""
        start_comp = start_port.parent_component
        end_comp = end_port.parent_component
        
        # Validation
        if start_comp == end_comp:
            print("[CONNECT] Can't connect to same component")
            return
        
        # Determine fluid state
        start_fluid = start_port.port_def.get('fluid_state', 'any')
        end_fluid = end_port.port_def.get('fluid_state', 'any')
        
        if start_fluid == 'any':
            fluid = end_fluid
        elif end_fluid == 'any':
            fluid = start_fluid
        elif start_fluid == end_fluid:
            fluid = start_fluid
        else:
            print(f"[CONNECT] Fluid mismatch: {start_fluid} vs {end_fluid}")
            return
        
        # Create in model
        self.data_manager.add_pipe_to_model(
            start_comp.comp_id,
            start_port.port_name,
            end_comp.comp_id,
            end_port.port_name,
            fluid
        )
        print(f"[CONNECT] {start_comp.comp_id}.{start_port.port_name} -> {end_comp.comp_id}.{end_port.port_name}")
    
    def rebuild_scene(self):
        """Rebuild scene from data model."""
        self.scene.clear()
        self.components.clear()
        self.lines.clear()
        
        model = self.data_manager.diagram_model
        
        # Create components
        for comp_id, comp_data in model.get('components', {}).items():
            comp = SimpleComponent(comp_id, comp_data)
            self.scene.addItem(comp)
            self.components[comp_id] = comp
        
        # Create connections
        for line_id, line_data in model.get('pipes', {}).items():
            start_comp_id = line_data['start_component_id']
            end_comp_id = line_data['end_component_id']
            
            if start_comp_id in self.components and end_comp_id in self.components:
                start_comp = self.components[start_comp_id]
                end_comp = self.components[end_comp_id]
                
                start_port = start_comp.ports.get(line_data['start_port'])
                end_port = end_comp.ports.get(line_data['end_port'])
                
                if start_port and end_port:
                    line = SimpleConnectionLine(line_id, start_port, end_port)
                    self.scene.addItem(line)
                    self.lines[line_id] = line
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        # Delete key
        if event.key() == Qt.Key.Key_Delete:
            selected = self.scene.selectedItems()
            
            # Delete components
            comp_ids = [item.comp_id for item in selected if isinstance(item, SimpleComponent)]
            if comp_ids:
                self.data_manager.remove_components_from_model(comp_ids)
                print(f"[DELETE] {len(comp_ids)} component(s)")
            
            # Delete lines
            line_ids = [item.line_id for item in selected if isinstance(item, SimpleConnectionLine)]
            if line_ids:
                self.data_manager.remove_pipes_from_model(line_ids)
                print(f"[DELETE] {len(line_ids)} line(s)")
        
        super().keyPressEvent(event)
    
    def on_selection_changed(self):
        """Handle selection changes."""
        selected = self.scene.selectedItems()
        if len(selected) == 1 and isinstance(selected[0], SimpleComponent):
            print(f"[SELECTED] {selected[0].comp_data['type']}")
    
    def clear_canvas(self):
        """Clear all components from canvas."""
        model = self.data_manager.diagram_model
        model['components'] = {}
        model['pipes'] = {}
        self.data_manager.diagram_model_changed.emit()
        print("[CLEAR] Canvas cleared")
    
    def update_ui(self):
        """Update UI - called by main window."""
        # Scene already updates via signals
        pass

