
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
        
        self.setBrush(QBrush(QColor('#f0f0f0')))
        self.setPen(QPen(QColor('black'), 2))
        
        self.label = QGraphicsTextItem(f'[{name}]', self)
        text_rect = self.label.boundingRect()
        self.label.setPos((width - text_rect.width()) / 2, (height - text_rect.height()) / 2)
        
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    def add_port(self, port_name, rx, ry):
        port = QGraphicsEllipseItem(-4, -4, 8, 8, self)
        port.setBrush(QBrush(QColor('green')))
        port.setPos(rx, ry)
        self.ports[port_name] = port

class SplitterBox(SimpleBox):
    def __init__(self, name, x, y, num_outlets, width=120, height=40):
        super().__init__(name, x, y, width, height)
        self.add_port('inlet', width / 2, 0)
        
        manifold_y_split = height + 20
        manifold_path = QPainterPath()
        manifold_path.moveTo(width / 2, height)
        manifold_path.lineTo(width / 2, manifold_y_split)
        
        manifold_width = max(width, num_outlets * 30)
        start_x = (width - manifold_width) / 2
        
        manifold_path.moveTo(start_x, manifold_y_split)
        manifold_path.lineTo(start_x + manifold_width, manifold_y_split)
        
        spacing = manifold_width / (num_outlets - 1)
        for i in range(num_outlets):
            px = start_x + i * spacing
            manifold_path.moveTo(px, manifold_y_split)
            manifold_path.lineTo(px, manifold_y_split + 15)
            self.add_port(f'out{i+1}', px, manifold_y_split + 15)
            
        manifold_item = QGraphicsPathItem(manifold_path, self)
        manifold_item.setPen(QPen(QColor('black'), 2))

class CombinerBox(SimpleBox):
    def __init__(self, name, x, y, num_inlets, width=120, height=40):
        super().__init__(name, x, y, width, height)
        self.add_port('outlet', width / 2, height)
        
        manifold_y_split = -20
        manifold_path = QPainterPath()
        manifold_path.moveTo(width / 2, 0)
        manifold_path.lineTo(width / 2, manifold_y_split)
        
        manifold_width = max(width, num_inlets * 30)
        start_x = (width - manifold_width) / 2
        
        manifold_path.moveTo(start_x, manifold_y_split)
        manifold_path.lineTo(start_x + manifold_width, manifold_y_split)
        
        spacing = manifold_width / (num_inlets - 1)
        for i in range(num_inlets):
            px = start_x + i * spacing
            manifold_path.moveTo(px, manifold_y_split)
            manifold_path.lineTo(px, manifold_y_split - 15)
            self.add_port(f'in{i+1}', px, manifold_y_split - 15)
            
        manifold_item = QGraphicsPathItem(manifold_path, self)
        manifold_item.setPen(QPen(QColor('black'), 2))

class SimplePipe(QGraphicsPathItem):
    def __init__(self, start_pos, end_pos, is_loop=False):
        super().__init__()
        self.setPen(QPen(QColor('blue'), 3))
        path = QPainterPath()
        path.moveTo(start_pos)
        if is_loop:
            # Draw a nice clean line going left and all the way up to close the loop
            path.lineTo(start_pos.x(), start_pos.y() + 40)
            path.lineTo(start_pos.x() - 250, start_pos.y() + 40)
            path.lineTo(start_pos.x() - 250, end_pos.y() - 40)
            path.lineTo(end_pos.x(), end_pos.y() - 40)
            path.lineTo(end_pos)
        else:
            path.lineTo(end_pos)
        self.setPath(path)

class SimpleApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Full Loop Test Diagram')
        self.resize(1000, 900)
        
        self.view = QGraphicsView()
        self.scene = QGraphicsScene()
        self.view.setScene(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setCentralWidget(self.view)
        
        center_x = 500
        
        self.comp = SimpleBox('Compressor', center_x, 50)
        self.comp.add_port('inlet', 60, 0)
        self.comp.add_port('outlet', 60, 60)
        self.scene.addItem(self.comp)
        
        self.cond = SimpleBox('Condenser', center_x, 150)
        self.cond.add_port('inlet', 60, 0)
        self.cond.add_port('outlet', 60, 60)
        self.scene.addItem(self.cond)
        
        self.txv = SimpleBox('TXV', center_x, 250)
        self.txv.add_port('inlet', 60, 0)
        self.txv.add_port('outlet', 60, 60)
        self.scene.addItem(self.txv)
        
        self.dist = SplitterBox('Distributor', center_x, 350, 6)
        self.scene.addItem(self.dist)
        
        # Evaporator needs 6 inlets and 6 outlets (assuming straightforward flow)
        self.evap = SimpleBox('Evaporator', center_x, 500)
        manifold_width = max(120, 6 * 30)
        start_x = (120 - manifold_width) / 2
        spacing = manifold_width / 5
        for i in range(6):
            px = start_x + i * spacing
            self.evap.add_port(f'in{i+1}', px, 0)
            self.evap.add_port(f'out{i+1}', px, 60)
        self.scene.addItem(self.evap)
        
        self.combiner = CombinerBox('Header', center_x, 650, 6)
        self.scene.addItem(self.combiner)
        
        # Connect everything
        self.add_pipe(self.comp.ports['outlet'], self.cond.ports['inlet'])
        self.add_pipe(self.cond.ports['outlet'], self.txv.ports['inlet'])
        self.add_pipe(self.txv.ports['outlet'], self.dist.ports['inlet'])
        
        # 6 lines from Dist to Evap
        for i in range(1, 7):
            self.add_pipe(self.dist.ports[f'out{i}'], self.evap.ports[f'in{i}'])
            
        # 6 lines from Evap to Combiner
        for i in range(1, 7):
            self.add_pipe(self.evap.ports[f'out{i}'], self.combiner.ports[f'in{i}'])
            
        # 1 line from Combiner looping back to Compressor
        self.add_pipe(self.combiner.ports['outlet'], self.comp.ports['inlet'], is_loop=True)

    def add_pipe(self, port1, port2, is_loop=False):
        pipe = SimplePipe(port1.scenePos(), port2.scenePos(), is_loop)
        self.scene.addItem(pipe)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SimpleApp()
    window.show()
    sys.exit(app.exec())

