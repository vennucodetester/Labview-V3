
import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QGraphicsView, QGraphicsScene
from PyQt6.QtGui import QColor, QBrush, QPen, QPainter
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
        """Add a port at relative coordinates rx, ry (0 to width/height)"""
        port = QGraphicsEllipseItem(-4, -4, 8, 8, self)
        port.setBrush(QBrush(QColor('green')))
        port.setPos(rx, ry)
        self.ports[port_name] = port

class SimplePipe(QGraphicsPathItem):
    def __init__(self, start_pos, end_pos):
        super().__init__()
        self.setPen(QPen(QColor('blue'), 3))
        # Just a straight line for this simplistic test UI
        import PyQt6.QtGui as qtg
        path = qtg.QPainterPath()
        path.moveTo(start_pos)
        path.lineTo(end_pos)
        self.setPath(path)

class SimpleApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Bare Minimum Diagram')
        self.resize(800, 800)
        
        self.view = QGraphicsView()
        self.scene = QGraphicsScene()
        self.view.setScene(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setCentralWidget(self.view)
        
        # Create ultra-simplistic components
        self.condenser = SimpleBox('Condenser', 300, 50)
        self.condenser.add_port('inlet', 60, 0)
        self.condenser.add_port('outlet', 60, 60)
        
        self.txv = SimpleBox('TXV', 300, 200)
        self.txv.add_port('inlet', 60, 0)
        self.txv.add_port('outlet', 60, 60)
        
        self.distributor = SimpleBox('Distributor', 300, 350)
        self.distributor.add_port('inlet', 60, 0)
        self.distributor.add_port('out1', 20, 60)
        self.distributor.add_port('out2', 60, 60)
        self.distributor.add_port('out3', 100, 60)
        
        self.evap = SimpleBox('Evaporator', 300, 500)
        self.evap.add_port('in1', 20, 0)
        self.evap.add_port('in2', 60, 0)
        self.evap.add_port('in3', 100, 0)
        self.evap.add_port('outlet', 60, 60)
        
        self.scene.addItem(self.condenser)
        self.scene.addItem(self.txv)
        self.scene.addItem(self.distributor)
        self.scene.addItem(self.evap)

        # Draw generic lines between them (simplistic straight lines for now, or libavoid)
        self.add_pipe(self.condenser.ports['outlet'], self.txv.ports['inlet'])
        self.add_pipe(self.txv.ports['outlet'], self.distributor.ports['inlet'])
        self.add_pipe(self.distributor.ports['out1'], self.evap.ports['in1'])
        self.add_pipe(self.distributor.ports['out2'], self.evap.ports['in2'])
        self.add_pipe(self.distributor.ports['out3'], self.evap.ports['in3'])
        
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

