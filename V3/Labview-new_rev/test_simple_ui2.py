
import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QGraphicsView, QGraphicsScene
from PyQt6.QtGui import QColor, QBrush, QPen, QPainter, QPainterPath
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsTextItem, QGraphicsEllipseItem, QGraphicsPathItem

class SimpleBox(QGraphicsRectItem):
    def __init__(self, name, x, y, width=120, height=60):
        super().__init__(0, 0, width, height)
        self.setPos(x, y)
        self.name = name
        self.ports = {}
        
        # Simple styling: Light gray fill, black outline
        self.setBrush(QBrush(QColor('#f0f0f0')))
        self.setPen(QPen(QColor('black'), 2))
        
        # Add label
        self.label = QGraphicsTextItem(f'[{name}]', self)
        # Center the text
        text_rect = self.label.boundingRect()
        self.label.setPos((width - text_rect.width()) / 2, (height - text_rect.height()) / 2)
        
        # Make draggable
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    def add_port(self, port_name, rx, ry):
        """Add a port at relative coordinates rx, ry"""
        port = QGraphicsEllipseItem(-4, -4, 8, 8, self)
        port.setBrush(QBrush(QColor('green')))
        port.setPos(rx, ry)
        self.ports[port_name] = port

class SplitterBox(SimpleBox):
    def __init__(self, name, x, y, num_outlets, width=120, height=40):
        super().__init__(name, x, y, width, height)
        
        # Top inlet
        self.add_port('inlet', width / 2, 0)
        
        manifold_y_start = height
        manifold_y_drop = 20
        manifold_y_split = manifold_y_start + manifold_y_drop
        
        manifold_path = QPainterPath()
        # Single line coming down from the box
        manifold_path.moveTo(width / 2, manifold_y_start)
        manifold_path.lineTo(width / 2, manifold_y_split)
        
        # Calculate width of the horizontal split line based on number of outlets
        # Allow at least 20px per outlet
        manifold_width = max(width, num_outlets * 30)
        start_x = (width - manifold_width) / 2
        
        if num_outlets > 1:
            # Horizontal line
            manifold_path.moveTo(start_x, manifold_y_split)
            manifold_path.lineTo(start_x + manifold_width, manifold_y_split)
            
            # Drops and ports
            spacing = manifold_width / (num_outlets - 1)
            for i in range(num_outlets):
                px = start_x + i * spacing
                manifold_path.moveTo(px, manifold_y_split)
                manifold_path.lineTo(px, manifold_y_split + 15)
                self.add_port(f'out{i+1}', px, manifold_y_split + 15)
        else:
            manifold_path.moveTo(width / 2, manifold_y_split)
            manifold_path.lineTo(width / 2, manifold_y_split + 15)
            self.add_port('out1', width / 2, manifold_y_split + 15)
            
        manifold_item = QGraphicsPathItem(manifold_path, self)
        manifold_item.setPen(QPen(QColor('black'), 2))

class SimplePipe(QGraphicsPathItem):
    def __init__(self, start_pos, end_pos):
        super().__init__()
        self.setPen(QPen(QColor('blue'), 3))
        path = QPainterPath()
        path.moveTo(start_pos)
        path.lineTo(end_pos)
        self.setPath(path)

class SimpleApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Bare Minimum Diagram with Splitters')
        self.resize(1000, 800)
        
        self.view = QGraphicsView()
        self.scene = QGraphicsScene()
        self.view.setScene(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setCentralWidget(self.view)
        
        # Create standard box
        self.condenser = SimpleBox('Condenser', 400, 50)
        self.condenser.add_port('inlet', 60, 0)
        self.condenser.add_port('outlet', 60, 60)
        self.scene.addItem(self.condenser)
        
        # 2-way splitter
        self.split2 = SplitterBox('Splitter (2)', 200, 250, 2)
        self.scene.addItem(self.split2)
        
        # 3-way distributor
        self.dist3 = SplitterBox('Distributor (3)', 400, 250, 3)
        self.scene.addItem(self.dist3)
        
        # 6-way distributor
        self.dist6 = SplitterBox('Distributor (6)', 650, 250, 6)
        self.scene.addItem(self.dist6)

        # Evaporator (just to show connecting)
        self.evap = SimpleBox('Evaporator', 400, 500)
        self.evap.add_port('in1', 0, 0)
        self.evap.add_port('in2', 60, 0)
        self.evap.add_port('in3', 120, 0)
        self.scene.addItem(self.evap)

        # Draw lines from 3-way dist to evap
        self.add_pipe(self.condenser.ports['outlet'], self.dist3.ports['inlet'])
        self.add_pipe(self.dist3.ports['out1'], self.evap.ports['in1'])
        self.add_pipe(self.dist3.ports['out2'], self.evap.ports['in2'])
        self.add_pipe(self.dist3.ports['out3'], self.evap.ports['in3'])
        
    def add_pipe(self, port1, port2):
        pos1 = port1.scenePos()
        pos2 = port2.scenePos()
        pipe = SimplePipe(pos1, pos2)
        self.scene.addItem(pipe)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SimpleApp()
    window.show()
    sys.exit(app.exec())

