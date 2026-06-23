import os

path = 'C:/Users/silam/OneDrive/Documents/Lab viewer/HVAC_Dev/diagram_components.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# remove everything after '# --- OVERRIDE CLASSES FOR SIMPLIFIED UI ---'
idx = content.find('# --- OVERRIDE CLASSES FOR SIMPLIFIED UI ---')
if idx != -1:
    content = content[:idx]

new_content = '''
# --- OVERRIDE CLASSES FOR SIMPLIFIED UI ---

class SplitterComponentItem(BaseComponentItem):
    def __init__(self, component_id, component_data, data_manager):
        super().__init__(component_id, component_data, data_manager)
        self.setBrush(QBrush(Qt.GlobalColor.transparent))
        self.setPen(QPen(Qt.GlobalColor.transparent))
        if hasattr(self, 'label') and self.label:
            self.label.setVisible(False)
            
    def rebuild_ports(self):
        for port in list(self.ports.values()):
            if port.scene():
                port.scene().removeItem(port)
        self.ports.clear()

        num_outlets = self.component_data.get('properties', {}).get('circuits', 6)
        width = self.rect().width()
        height = 40
        
        manifold_y_split = height + 20
        manifold_path = QPainterPath()
        manifold_path.moveTo(width / 2, 0)
        manifold_path.lineTo(width / 2, manifold_y_split)
        
        manifold_width = max(width, num_outlets * 30)
        start_x = (width - manifold_width) / 2
        
        manifold_path.moveTo(start_x, manifold_y_split)
        manifold_path.lineTo(start_x + manifold_width, manifold_y_split)
        
        spacing = manifold_width / max(1, num_outlets - 1)
        for i in range(num_outlets):
            px = start_x + i * spacing
            manifold_path.moveTo(px, manifold_y_split)
            manifold_path.lineTo(px, manifold_y_split + 15)
            self._add_manifold_port(f'out_{i+1}', px, manifold_y_split + 15, 'outlet')
            
        manifold_item = QGraphicsPathItem(manifold_path, self)
        manifold_item.setPen(QPen(QColor('#4DA6FF'), 2))
        self._add_manifold_port('inlet', width / 2, 0, 'inlet')

    def _add_manifold_port(self, name, x, y, port_type):
        port_def = {'type': port_type, 'id': f'{self.component_id}_{name}'}
        port = PortItem(self, self.data_manager, port_def, f'port_{name}')
        port.setPos(x, y)
        self.ports[name] = port

class CombinerComponentItem(BaseComponentItem):
    def __init__(self, component_id, component_data, data_manager):
        super().__init__(component_id, component_data, data_manager)
        self.setBrush(QBrush(Qt.GlobalColor.transparent))
        self.setPen(QPen(Qt.GlobalColor.transparent))
        if hasattr(self, 'label') and self.label:
            self.label.setVisible(False)

    def rebuild_ports(self):
        for port in list(self.ports.values()):
            if port.scene():
                port.scene().removeItem(port)
        self.ports.clear()

        num_inlets = self.component_data.get('properties', {}).get('circuits', 6)
        width = self.rect().width()
        height = 40
        
        manifold_y_split = -20
        manifold_path = QPainterPath()
        manifold_path.moveTo(width / 2, height)
        manifold_path.lineTo(width / 2, manifold_y_split)
        
        manifold_width = max(width, num_inlets * 30)
        start_x = (width - manifold_width) / 2
        
        manifold_path.moveTo(start_x, manifold_y_split)
        manifold_path.lineTo(start_x + manifold_width, manifold_y_split)
        
        spacing = manifold_width / max(1, num_inlets - 1)
        for i in range(num_inlets):
            px = start_x + i * spacing
            manifold_path.moveTo(px, manifold_y_split)
            manifold_path.lineTo(px, manifold_y_split - 15)
            self._add_manifold_port(f'in_{i+1}', px, manifold_y_split - 15, 'inlet')
            
        manifold_item = QGraphicsPathItem(manifold_path, self)
        manifold_item.setPen(QPen(QColor('#4DA6FF'), 2))
        self._add_manifold_port('outlet', width / 2, height, 'outlet')

    def _add_manifold_port(self, name, x, y, port_type):
        port_def = {'type': port_type, 'id': f'{self.component_id}_{name}'}
        port = PortItem(self, self.data_manager, port_def, f'port_{name}')
        port.setPos(x, y)
        self.ports[name] = port

class DistributorComponentItem(SplitterComponentItem): pass
class HeaderComponentItem(CombinerComponentItem): pass
class JunctionComponentItem(SplitterComponentItem): pass

class SimpleBoxComponentItem(BaseComponentItem):
    def rebuild_ports(self):
        for port in list(self.ports.values()):
            if port.scene():
                port.scene().removeItem(port)
        self.ports.clear()
        
        width = self.rect().width()
        height = self.rect().height()
        
        # default inlet and outlet
        self._add_simple_port('inlet', width / 2, 0, 'inlet')
        self._add_simple_port('outlet', width / 2, height, 'outlet')

    def _add_simple_port(self, name, x, y, port_type):
        port_def = {'type': port_type, 'id': f'{self.component_id}_{name}'}
        port = PortItem(self, self.data_manager, port_def, f'port_{name}')
        port.setPos(x, y)
        self.ports[name] = port

class CompressorComponentItem(SimpleBoxComponentItem): pass
class CondenserComponentItem(SimpleBoxComponentItem): pass
class TXVComponentItem(SimpleBoxComponentItem): pass
class HotGasBypassItem(SimpleBoxComponentItem): pass
class FanComponentItem(SimpleBoxComponentItem): pass
class SensorBulbComponentItem(SimpleBoxComponentItem): pass
class AirSensorArrayComponentItem(SimpleBoxComponentItem): pass
class ShelvingGridComponentItem(SimpleBoxComponentItem): pass
class SensorComponentItem(SimpleBoxComponentItem): pass
class HotGasLoopItem(SimpleBoxComponentItem): pass

class EvaporatorComponentItem(SimpleBoxComponentItem):
    def rebuild_ports(self):
        for port in list(self.ports.values()):
            if port.scene():
                port.scene().removeItem(port)
        self.ports.clear()
        
        circuits = self.component_data.get('properties', {}).get('circuits', 6)
        width = self.rect().width()
        height = self.rect().height()
        
        manifold_width = max(width, circuits * 30)
        start_x = (width - manifold_width) / 2
        spacing = manifold_width / max(1, circuits - 1) if circuits > 1 else 0
        
        for i in range(circuits):
            px = start_x + i * spacing
            self._add_simple_port(f'inlet_{i+1}', px, 0, 'inlet')
            self._add_simple_port(f'outlet_{i+1}', px, height, 'outlet')
'''

with open(path, 'w', encoding='utf-8') as f:
    f.write(content + new_content)
