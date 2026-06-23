
class SensorComponentItem(QGraphicsPathItem):
    """A dedicated sensor component drawn as a distinct dot on the line."""
    
    def __init__(self, component_id, component_data, data_manager):
        super().__init__()
        self.component_id = component_id
        self.component_data = component_data
        self.data_manager = data_manager
        self.schema = SCHEMAS.get(component_data['type'], {})
        
        # Initialize ports
        self.ports = {}
        
        # Visual setup - Distinct Blue Dot (User requested "slightly larger dot")
        # Standard port dot is usually small (~8px). Let's make this ~16-20px.
        self.setPen(QPen(QColor("#2980b9"), 2))  # Darker blue outline
        self.setBrush(QBrush(QColor("#3498db")))  # Bright blue fill
        
        # Interaction flags
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        
        # Set position from data
        pos = component_data.get('position', [0, 0])
        if isinstance(pos, QPointF):
            self.setPos(pos)
        else:
            self.setPos(pos[0], pos[1])
        
        # Set rotation from data
        rotation = component_data.get('rotation', 0)
        self.setRotation(rotation)

        # Tooltip for measurement type
        self.update_tooltip()
        
        # Build the shape and ports
        self.update_shape()
        self.rebuild_ports()

    def update_tooltip(self):
        """Update tooltip based on current measurement type."""
        measure_type = self.component_data.get('properties', {}).get('measurement_type', 'Temperature')
        label = self.component_data.get('properties', {}).get('label', '')
        tooltip = f"<b>{measure_type} Sensor</b>"
        if label:
            tooltip += f"<br><i>{label}</i>"
        self.setToolTip(tooltip)
    
    def update_shape(self):
        """Draw a circle centered at (0,0)."""
        path = QPainterPath()
        radius = 10  # Diameter = 20px
        path.addEllipse(QPointF(0, 0), radius, radius)
        self.setPath(path)
    
    def rebuild_ports(self):
        """Create inlet (left) and outlet (right) ports to allow inline connection."""
        # IMPORTANT: Save pipe connections before clearing ports
        port_connections = {}
        for port_name, port_item in self.ports.items():
            if hasattr(port_item, 'connected_pipes') and port_item.connected_pipes:
                port_connections[port_name] = list(port_item.connected_pipes)
        
        # Clear existing ports
        for port_item in list(self.ports.values()):
            port_item.setParentItem(None)
            if port_item.scene():
                port_item.scene().removeItem(port_item)
        self.ports.clear()
        
        # Inlet on Left
        inlet_def = {'name': 'inlet', 'type': 'in', 'fluid_state': 'any', 'pressure_side': 'any', 'position': [0, 0.5]}
        inlet_port = PortItem('inlet', inlet_def, self)
        # Position at left edge of the circle (radius=10)
        inlet_port.setPos(-10, 0) 
        self.ports['inlet'] = inlet_port
        
        # Outlet on Right
        outlet_def = {'name': 'outlet', 'type': 'out', 'fluid_state': 'any', 'pressure_side': 'any', 'position': [1, 0.5]}
        outlet_port = PortItem('outlet', outlet_def, self)
        # Position at right edge of the circle
        outlet_port.setPos(10, 0)
        self.ports['outlet'] = outlet_port
        
        # IMPORTANT: Restore pipe connections
        total_restored = 0
        comp_type = self.component_data['type']
        for port_name, pipes in port_connections.items():
            if port_name in self.ports:
                new_port = self.ports[port_name]
                for pipe in pipes:
                    if hasattr(new_port, 'add_connected_pipe'):
                        new_port.add_connected_pipe(pipe)
                    # Update pipe's internal port references
                    if hasattr(pipe, 'start_port_item') and hasattr(pipe, 'end_port_item'):
                        if hasattr(pipe, 'pipe_data') and hasattr(pipe, 'pipe_id'):
                            pipe_data = pipe.pipe_data
                            start_comp_id = pipe_data.get('start_component_id')
                            start_port = pipe_data.get('start_port')
                            end_comp_id = pipe_data.get('end_component_id')
                            end_port = pipe_data.get('end_port')
                            
                            if start_comp_id == self.component_id and start_port == port_name:
                                pipe.start_port_item = new_port
                            if end_comp_id == self.component_id and end_port == port_name:
                                pipe.end_port_item = new_port
                    if hasattr(pipe, 'update_path'):
                        pipe.update_path()
                    total_restored += 1

    def boundingRect(self):
        """Return the bounding rectangle."""
        return self.path().boundingRect().adjusted(-5, -5, 5, 5)
    
    def itemChange(self, change, value):
        """Handle item changes."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.data_manager.update_component_position(self.component_id, value)
            self.update_connected_pipes()
        
        if change == QGraphicsItem.GraphicsItemChange.ItemRotationHasChanged:
            self.component_data['rotation'] = value
            self.update_connected_pipes()
            
        return super().itemChange(change, value)
    
    def update_connected_pipes(self):
        """Update all pipes connected to this component's ports."""
        for port_item in self.ports.values():
            for pipe_item in port_item.connected_pipes:
                pipe_item.update_path()
    
    def mouseDoubleClickEvent(self, event):
        """Handle double-click to open property dialog."""
        if event.button() == Qt.MouseButton.LeftButton:
            if hasattr(self.scene(), 'views') and self.scene().views():
                view = self.scene().views()[0]
                if hasattr(view.parent(), 'on_component_double_clicked'):
                    view.parent().on_component_double_clicked(self)
        super().mouseDoubleClickEvent(event)
