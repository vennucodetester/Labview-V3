import sys
from PyQt6.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QMainWindow, QVBoxLayout, QWidget, QGraphicsPathItem, QGraphicsTextItem, QGraphicsEllipseItem, QPushButton, QHBoxLayout, QLabel, QSpinBox, QComboBox
from PyQt6.QtGui import QBrush, QPen, QPainterPath, QColor
from PyQt6.QtCore import Qt, QPointF

# --- SIMPLE ISOLATED COMPONENTS ---

class SimpleBox(QGraphicsPathItem):
    def __init__(self, title, width=120, height=60, has_in=True, has_out=True):
        super().__init__()
        self.width = width
        self.height = height
        
        path = QPainterPath()
        path.addRect(0, 0, width, height)
        self.setPath(path)
        
        self.setBrush(QBrush(QColor('#222222')))
        self.setPen(QPen(QColor('#4DA6FF'), 2))
        
        self.text = QGraphicsTextItem(self)
        title_html = title.replace('\n', '<br>')
        self.text.setHtml(f"<div align='center' style='color: white; font-family: sans-serif; font-size: 10pt;'>{title_html}</div>")
        self.text.setTextWidth(width)
        
        rect = self.text.boundingRect()
        y_pos = (height - rect.height()) / 2
        self.text.setPos(0, y_pos)
        
        self.inlet_pos = QPointF(width/2, 0) if has_in else None
        self.outlet_pos = QPointF(width/2, height) if has_out else None
        
        if has_in:
            self.draw_port(self.inlet_pos, QColor('#FF5555'))
        if has_out:
            self.draw_port(self.outlet_pos, QColor('#55FF55'))

    def draw_port(self, pos, color):
        port = QGraphicsEllipseItem(-4, -4, 8, 8, self)
        port.setPos(pos)
        port.setBrush(QBrush(color))
        port.setPen(QPen(Qt.GlobalColor.white, 1))

class ColoredBox(QGraphicsPathItem):
    def __init__(self, title, width, height, bg_color):
        super().__init__()
        path = QPainterPath()
        path.addRect(0, 0, width, height)
        self.setPath(path)
        self.setBrush(QBrush(QColor(bg_color)))
        self.setPen(QPen(QColor('#000000'), 1))
        self.text = QGraphicsTextItem(self)
        title_html = title.replace('\n', '<br>')
        self.text.setHtml(f"<div align='center' style='color: black; font-family: sans-serif; font-size: 10pt;'>{title_html}</div>")
        self.text.setTextWidth(width)
        
        rect = self.text.boundingRect()
        y_pos = (height - rect.height()) / 2
        self.text.setPos(0, y_pos)

class SplitterManifold(QGraphicsPathItem):
    def __init__(self, num_splits=6, width=120, height=40, is_reversed=False):
        super().__init__()
        
        self.num_splits = num_splits
        self.is_reversed = is_reversed
        
        self.setBrush(QBrush(Qt.GlobalColor.transparent))
        self.setPen(QPen(Qt.GlobalColor.transparent))
        
        path = QPainterPath()
        
        if num_splits == 1:
            if not is_reversed:
                self.inlet_pos = QPointF(width/2, 0)
                self.outlet_positions = [QPointF(width/2, height + 15)]
                path.moveTo(width/2, 0)
                path.lineTo(width/2, height + 15)
                self.draw_port(self.inlet_pos, QColor('#FF5555'))
                self.draw_port(self.outlet_positions[0], QColor('#55FF55'))
            else:
                self.outlet_pos = QPointF(width/2, height + 15)
                self.inlet_positions = [QPointF(width/2, 0)]
                path.moveTo(width/2, 0)
                path.lineTo(width/2, height + 15)
                self.draw_port(self.inlet_positions[0], QColor('#FF5555'))
                self.draw_port(self.outlet_pos, QColor('#55FF55'))
        else:
            manifold_width = max(width, num_splits * 30)
            start_x = (width - manifold_width) / 2
            spacing = manifold_width / (num_splits - 1)
            
            if not is_reversed:
                self.inlet_pos = QPointF(width/2, 0)
                self.outlet_positions = []
                
                manifold_y = height
                path.moveTo(width/2, 0)
                path.lineTo(width/2, manifold_y)
                path.moveTo(start_x, manifold_y)
                path.lineTo(start_x + manifold_width, manifold_y)
                
                for i in range(num_splits):
                    px = start_x + i * spacing
                    path.moveTo(px, manifold_y)
                    path.lineTo(px, manifold_y + 15)
                    self.outlet_positions.append(QPointF(px, manifold_y + 15))
                    self.draw_port(QPointF(px, manifold_y + 15), QColor('#55FF55'))
                    
                self.draw_port(self.inlet_pos, QColor('#FF5555'))
            else:
                self.outlet_pos = QPointF(width/2, height + 15)
                self.inlet_positions = []
                
                manifold_y = 15
                path.moveTo(width/2, manifold_y)
                path.lineTo(width/2, height + 15)
                path.moveTo(start_x, manifold_y)
                path.lineTo(start_x + manifold_width, manifold_y)
                
                for i in range(num_splits):
                    px = start_x + i * spacing
                    path.moveTo(px, manifold_y)
                    path.lineTo(px, 0)
                    self.inlet_positions.append(QPointF(px, 0))
                    self.draw_port(QPointF(px, 0), QColor('#FF5555'))
                    
                self.draw_port(self.outlet_pos, QColor('#55FF55'))
            
        manifold_item = QGraphicsPathItem(path, self)
        manifold_item.setPen(QPen(QColor('#4DA6FF'), 2))

    def draw_port(self, pos, color):
        port = QGraphicsEllipseItem(-4, -4, 8, 8, self)
        port.setPos(pos)
        port.setBrush(QBrush(color))
        port.setPen(QPen(Qt.GlobalColor.white, 1))

class EvaporatorBox(QGraphicsPathItem):
    def __init__(self, title="Evaporator", num_circuits=6, width=120, height=60):
        super().__init__()
        
        path = QPainterPath()
        path.addRect(0, 0, width, height)
        self.setPath(path)
        
        self.setBrush(QBrush(QColor('#222222')))
        self.setPen(QPen(QColor('#4DA6FF'), 2))
        
        self.text = QGraphicsTextItem(self)
        title_html = title.replace('\n', '<br>')
        self.text.setHtml(f"<div align='center' style='color: white; font-family: sans-serif; font-size: 10pt;'>{title_html}</div>")
        self.text.setTextWidth(width)
        
        rect = self.text.boundingRect()
        y_pos = (height - rect.height()) / 2
        self.text.setPos(0, y_pos)
        
        self.inlet_positions = []
        self.outlet_positions = []
        
        if num_circuits == 1:
            px = width / 2
            in_pos = QPointF(px, 0)
            out_pos = QPointF(px, height)
            self.inlet_positions.append(in_pos)
            self.outlet_positions.append(out_pos)
            self.draw_port(in_pos, QColor('#FF5555'))
            self.draw_port(out_pos, QColor('#55FF55'))
        else:
            manifold_width = max(width, num_circuits * 30)
            start_x = (width - manifold_width) / 2
            spacing = manifold_width / (num_circuits - 1)
            
            for i in range(num_circuits):
                px = start_x + i * spacing
                in_pos = QPointF(px, 0)
                out_pos = QPointF(px, height)
                self.inlet_positions.append(in_pos)
                self.outlet_positions.append(out_pos)
                self.draw_port(in_pos, QColor('#FF5555'))
                self.draw_port(out_pos, QColor('#55FF55'))

    def draw_port(self, pos, color):
        port = QGraphicsEllipseItem(-4, -4, 8, 8, self)
        port.setPos(pos)
        port.setBrush(QBrush(color))
        port.setPen(QPen(Qt.GlobalColor.white, 1))

def draw_pipe(scene, start_pt, end_pt):
    path = QPainterPath()
    path.moveTo(start_pt)
    
    mid_y = (start_pt.y() + end_pt.y()) / 2
    path.lineTo(start_pt.x(), mid_y)
    path.lineTo(end_pt.x(), mid_y)
    path.lineTo(end_pt.x(), end_pt.y())
    
    pipe = QGraphicsPathItem(path)
    pipe.setPen(QPen(QColor('#888888'), 2))
    pipe.setZValue(-1)
    scene.addItem(pipe)

def draw_loopback_pipe(scene, start_pt, end_pt, leftmost_x):
    path = QPainterPath()
    path.moveTo(start_pt)
    
    path.lineTo(start_pt.x(), start_pt.y() + 30)
    path.lineTo(leftmost_x, start_pt.y() + 30)
    path.lineTo(leftmost_x, end_pt.y() - 30)
    path.lineTo(end_pt.x(), end_pt.y() - 30)
    path.lineTo(end_pt.x(), end_pt.y())
    
    pipe = QGraphicsPathItem(path)
    pipe.setPen(QPen(QColor('#888888'), 2))
    pipe.setZValue(-1)
    scene.addItem(pipe)

def draw_sensor_line(scene, txv, head):
    txv_left = txv.scenePos() + QPointF(0, txv.height / 2)
    attach_pt = head.scenePos() + head.outlet_pos + QPointF(0, 20)
    
    path = QPainterPath()
    path.moveTo(txv_left)
    
    clearance_x = txv_left.x() - 80
    
    path.lineTo(clearance_x, txv_left.y())
    path.lineTo(clearance_x, attach_pt.y())
    path.lineTo(attach_pt.x(), attach_pt.y())
    
    pipe = QGraphicsPathItem(path)
    pipe.setPen(QPen(QColor('#9932CC'), 2))
    pipe.setZValue(-1)
    scene.addItem(pipe)

def _draw_branch_pipe(scene, start_pt, end_pt, branch_y):
    """start_pt → down to branch_y → horizontal to end_pt.x → down/up to end_pt.y"""
    path = QPainterPath()
    path.moveTo(start_pt)
    path.lineTo(start_pt.x(), branch_y)
    path.lineTo(end_pt.x(), branch_y)
    path.lineTo(end_pt)
    pipe = QGraphicsPathItem(path)
    pipe.setPen(QPen(QColor('#888888'), 2))
    pipe.setZValue(-1)
    scene.addItem(pipe)

def _draw_up_arrow(scene, x, y_bottom, y_top):
    path = QPainterPath()
    path.moveTo(x, y_bottom)
    path.lineTo(x, y_top)
    # arrow head
    path.lineTo(x - 5, y_top + 5)
    path.moveTo(x, y_top)
    path.lineTo(x + 5, y_top + 5)
    
    arrow = QGraphicsPathItem(path)
    arrow.setPen(QPen(QColor('#555555'), 2))
    scene.addItem(arrow)

def _draw_boundary(scene, label_text, x, y, w, h):
    from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsTextItem
    from PyQt6.QtGui import QPen, QBrush, QColor
    from PyQt6.QtCore import Qt
    
    rect = QGraphicsRectItem(x, y, w, h)
    pen = QPen(QColor('#AAAAAA'), 2)
    pen.setStyle(Qt.PenStyle.DashLine)
    rect.setPen(pen)
    rect.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    rect.setZValue(-10)
    scene.addItem(rect)
    
    label = QGraphicsTextItem(label_text)
    label.setDefaultTextColor(QColor('#888888'))
    label.setPos(x + 5, y + 5)
    scene.addItem(label)

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Isolated Loop Test - Variations")
        self.resize(1200, 950)
        
        self.current_mode = 'modular'
        self.current_count = 3
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # Single Unified Toolbar
        toolbar = QHBoxLayout()
        
        toolbar.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Modular", "Non-Modular (Doors)", "Cassette MT", "Cassette LT"])
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        toolbar.addWidget(self.mode_combo)
        
        toolbar.addSpacing(20)
        toolbar.addWidget(QLabel("Count:"))
        self.count_combo = QComboBox()
        self.count_combo.currentTextChanged.connect(self.update_diagram)
        toolbar.addWidget(self.count_combo)
        
        toolbar.addSpacing(20)
        self.circuit_label = QLabel("Circuits:")
        toolbar.addWidget(self.circuit_label)
        self.circuit_spin = QSpinBox()
        self.circuit_spin.setRange(1, 8)
        self.circuit_spin.setValue(6)
        self.circuit_spin.valueChanged.connect(self.update_diagram)
        toolbar.addWidget(self.circuit_spin)
        
        toolbar.addSpacing(20)
        toolbar.addWidget(QLabel("Shelf Rows:"))
        self.shelf_spin = QSpinBox()
        self.shelf_spin.setRange(3, 8)
        self.shelf_spin.setValue(5)
        self.shelf_spin.valueChanged.connect(self.update_diagram)
        toolbar.addWidget(self.shelf_spin)
        
        toolbar.addSpacing(20)
        toolbar.addWidget(QLabel("Case Type:"))
        self.case_combo = QComboBox()
        self.case_combo.addItems(["Doored", "Open"])
        self.case_combo.currentTextChanged.connect(self.update_diagram)
        toolbar.addWidget(self.case_combo)
        
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        self.view = QGraphicsView()
        self.scene = QGraphicsScene()
        self.scene.setBackgroundBrush(QBrush(QColor('#EEEEEE')))
        self.view.setScene(self.scene)
        layout.addWidget(self.view)
        
        self.on_mode_changed()

    def on_mode_changed(self):
        mode = self.mode_combo.currentText()
        self.count_combo.blockSignals(True)
        self.count_combo.clear()
        
        if mode == "Modular":
            self.count_combo.addItems(["1 Module", "2 Modules", "3 Modules"])
            self.count_combo.setCurrentIndex(2) # Default 3
            self.circuit_spin.setEnabled(True)
        else:
            self.count_combo.addItems(["1 Door", "2 Doors", "3 Doors", "4 Doors", "5 Doors"])
            self.count_combo.setCurrentIndex(4) # Default 5
            
            if mode.startswith("Cassette"):
                self.circuit_spin.setEnabled(False)
            else:
                self.circuit_spin.setEnabled(True)
                
        self.count_combo.blockSignals(False)
        self.update_diagram()

    def update_diagram(self):
        self.scene.clear()
        
        mode_text = self.mode_combo.currentText()
        if mode_text == "Modular":
            self.current_mode = 'modular'
        elif mode_text == "Non-Modular (Doors)":
            self.current_mode = 'door'
        elif mode_text == "Cassette MT":
            self.current_mode = 'cassette_mt'
        else:
            self.current_mode = 'cassette_lt'
            
        self.current_count = self.count_combo.currentIndex() + 1

        num_modules = self.current_count if self.current_mode == 'modular' else 1
        CENTER_X = 600
        MOD_SPACING = 300

        # ── Fixed y positions ────────────────────────────────────────────────
        Y_COMP  = 100   # compressor top
        Y_COND  = 190   # condenser top
        Y_TXV   = 350   # TXV top  (one per module)
        Y_EVAP  = 495   # Evaporator top (one per module)
        EVAP_H  = 80
        COMP_W  = 120;  COMP_H  = 60
        COND_W  = 120;  COND_H  = 60
        TXV_W   = 120;  TXV_H   = 60
        num_circuits = self.circuit_spin.value()
        EVAP_W  = 240
        if self.current_mode == 'door':
            EVAP_W = 240 * self.current_count

        if num_modules == 1:
            mod_xs  = [CENTER_X]
            mod_lbs = [""]
        elif num_modules == 2:
            mod_xs  = [CENTER_X - MOD_SPACING // 2, CENTER_X + MOD_SPACING // 2]
            mod_lbs = ["LH", "RH"]
        else:
            mod_xs  = [CENTER_X - MOD_SPACING, CENTER_X, CENTER_X + MOD_SPACING]
            mod_lbs = ["LH", "CTR", "RH"]
        
        # ── Compute Case Dimensions ──────────────────────────────────────────
        if self.current_mode == 'modular':
            total_w = num_modules * EVAP_W + (num_modules - 1) * (MOD_SPACING - EVAP_W)
            left_edge = mod_xs[0] - EVAP_W / 2
            right_edge = mod_xs[-1] + EVAP_W / 2
            combined_w = total_w
        else: # door or cassette
            total_w = 240 * self.current_count
            left_edge = CENTER_X - total_w / 2
            right_edge = CENTER_X + total_w / 2
            combined_w = total_w
            
        process_x = left_edge - 200
        process_w = combined_w + 300

        if not self.current_mode.startswith('cassette'):
            LEFTMOST = left_edge - 100
            
            # ── Shared boxes ─────────────────────────────────────────────────────
            comp = SimpleBox("Compressor", width=COMP_W, height=COMP_H)
            comp.setPos(CENTER_X - COMP_W // 2, Y_COMP)
            self.scene.addItem(comp)
    
            cond = SimpleBox("Condenser", width=COND_W, height=COND_H)
            cond.setPos(CENTER_X - COND_W // 2, Y_COND)
            self.scene.addItem(cond)
    
            draw_pipe(self.scene, comp.scenePos() + comp.outlet_pos, cond.scenePos() + cond.inlet_pos)
            cond_out = cond.scenePos() + cond.outlet_pos
    
            BRANCH_Y   = Y_COND + COND_H + 30
            MERGE_Y    = Y_EVAP + EVAP_H + 85
    
            mod_evap_outlets = []
            for mod_x, lb in zip(mod_xs, mod_lbs):
                lp = f"{lb} " if lb else ""
    
                txv = SimpleBox(f"{lp}TXV", width=TXV_W, height=TXV_H)
                txv.setPos(mod_x - TXV_W // 2, Y_TXV)
                self.scene.addItem(txv)
    
                evap = EvaporatorBox(f"{lp}Evaporator", num_circuits=num_circuits, width=EVAP_W, height=EVAP_H)
                evap.setPos(mod_x - EVAP_W // 2, Y_EVAP)
                self.scene.addItem(evap)
    
                dist_h = 40
                dist = SplitterManifold(num_splits=num_circuits, width=EVAP_W, height=dist_h, is_reversed=False)
                dist.setPos(mod_x - EVAP_W // 2, Y_EVAP - dist_h - 15)
                self.scene.addItem(dist)
    
                head_h = 40
                head = SplitterManifold(num_splits=num_circuits, width=EVAP_W, height=head_h, is_reversed=True)
                head.setPos(mod_x - EVAP_W // 2, Y_EVAP + EVAP_H)
                self.scene.addItem(head)
    
                txv_in  = txv.scenePos() + txv.inlet_pos
                _draw_branch_pipe(self.scene, cond_out, txv_in, BRANCH_Y)
    
                head_out = head.scenePos() + head.outlet_pos
                mod_evap_outlets.append(head_out)
    
            merge_pt = QPointF(CENTER_X, MERGE_Y)
            for evap_out in mod_evap_outlets:
                _draw_branch_pipe(self.scene, evap_out, merge_pt, MERGE_Y)
    
            draw_loopback_pipe(self.scene, merge_pt, comp.scenePos() + comp.inlet_pos, LEFTMOST)
            _draw_boundary(self.scene, "Refrigeration Process", process_x, Y_COMP - 50, process_w, MERGE_Y - Y_COMP + 80)
            
        else:
            # ── Cassette Mode ────────────────────────────────────────────────
            if self.current_count in [1, 2]:
                num_cassettes = 1
                cas_lbs = [""]
            elif self.current_count in [3, 4]:
                num_cassettes = 2
                cas_lbs = ["LH", "RH"]
            else: # 5Dr
                num_cassettes = 2 if self.current_mode == 'cassette_mt' else 3
                cas_lbs = ["LH", "RH"] if num_cassettes == 2 else ["LH", "CTR", "RH"]
                
            cas_slice_w = combined_w / num_cassettes
            cas_evap_w = cas_slice_w * 0.5
            cas_xs = [left_edge + cas_slice_w / 2 + i * cas_slice_w for i in range(num_cassettes)]
            
            global_merge_y = Y_EVAP + EVAP_H + 85
            
            for cx, lb in zip(cas_xs, cas_lbs):
                comp = SimpleBox("Compressor", width=COMP_W, height=COMP_H)
                comp.setPos(cx - COMP_W // 2, Y_COMP)
                self.scene.addItem(comp)
                
                if self.current_mode == 'cassette_mt':
                    cond = SimpleBox("Condenser", width=COND_W, height=COND_H)
                    cond.setPos(cx - COND_W // 2, Y_COND)
                    self.scene.addItem(cond)
                    
                    txv = SimpleBox("TXV", width=TXV_W, height=TXV_H)
                    txv.setPos(cx - TXV_W // 2, Y_TXV)
                    self.scene.addItem(txv)
                    
                    evap = EvaporatorBox("Evaporator", num_circuits=1, width=cas_evap_w, height=EVAP_H)
                    evap.setPos(cx - cas_evap_w // 2, Y_EVAP)
                    self.scene.addItem(evap)
                    
                    comp_out = comp.scenePos() + comp.outlet_pos
                    cond_in = cond.scenePos() + cond.inlet_pos
                    cond_out = cond.scenePos() + cond.outlet_pos
                    txv_in = txv.scenePos() + txv.inlet_pos
                    
                    draw_pipe(self.scene, comp_out, cond_in)
                    draw_pipe(self.scene, cond_out, txv_in)
                    
                    dist_h = 40
                    dist = SplitterManifold(num_splits=1, width=cas_evap_w, height=dist_h, is_reversed=False)
                    dist.setPos(cx - cas_evap_w // 2, Y_EVAP - dist_h - 15)
                    self.scene.addItem(dist)
                    
                    head_h = 40
                    head = SplitterManifold(num_splits=1, width=cas_evap_w, height=head_h, is_reversed=True)
                    head.setPos(cx - cas_evap_w // 2, Y_EVAP + EVAP_H)
                    self.scene.addItem(head)
                    
                    head_out = head.scenePos() + head.outlet_pos
                    comp_in = comp.scenePos() + comp.inlet_pos
                    
                    LEFTMOST_CAS = cx - max(cas_evap_w / 2 + 40, 100)
                    draw_pipe(self.scene, head_out, QPointF(cx, global_merge_y))
                    draw_pipe(self.scene, QPointF(cx, global_merge_y), QPointF(LEFTMOST_CAS, global_merge_y))
                    draw_pipe(self.scene, QPointF(LEFTMOST_CAS, global_merge_y), QPointF(LEFTMOST_CAS, Y_COMP - 20))
                    draw_pipe(self.scene, QPointF(LEFTMOST_CAS, Y_COMP - 20), QPointF(comp_in.x(), Y_COMP - 20))
                    draw_pipe(self.scene, QPointF(comp_in.x(), Y_COMP - 20), comp_in)
                    
                    bound_left = cx - cas_evap_w/2 - 60
                    bound_width = (cx + cas_evap_w/2 + 60) - bound_left
                    
                else: # LT Cassette
                    bypass_w = 60
                    bypass_y = Y_COND
                    sol_y = Y_COND + COND_H + 30
                    bypass_x = cx - 140
                    
                    hgbv = SimpleBox("Hot Gas\nBypass", width=bypass_w, height=50)
                    hgbv.setPos(bypass_x, bypass_y)
                    self.scene.addItem(hgbv)
                    
                    hgs = SimpleBox("Hot Gas\nSolenoid", width=bypass_w, height=50)
                    hgs.setPos(bypass_x, sol_y)
                    self.scene.addItem(hgs)
                    
                    cond = SimpleBox("Condenser", width=COND_W, height=COND_H)
                    cond.setPos(cx - COND_W // 2, Y_COND)
                    self.scene.addItem(cond)
                    
                    lls = SimpleBox("Liquid Line\nSolenoid", width=COND_W, height=40)
                    lls.setPos(cx - COND_W // 2, sol_y)
                    self.scene.addItem(lls)
                    
                    txv = SimpleBox("TXV", width=TXV_W, height=TXV_H)
                    txv.setPos(cx - TXV_W // 2, Y_TXV)
                    self.scene.addItem(txv)
                    
                    evap = EvaporatorBox("Evaporator", num_circuits=2, width=cas_evap_w, height=EVAP_H)
                    evap.setPos(cx - cas_evap_w // 2, Y_EVAP)
                    self.scene.addItem(evap)
                    
                    dist_h = 40
                    dist = SplitterManifold(num_splits=2, width=cas_evap_w, height=dist_h, is_reversed=False)
                    dist.setPos(cx - cas_evap_w // 2, Y_EVAP - dist_h - 15)
                    self.scene.addItem(dist)
                    
                    head_h = 40
                    head = SplitterManifold(num_splits=2, width=cas_evap_w, height=head_h, is_reversed=True)
                    head.setPos(cx - cas_evap_w // 2, Y_EVAP + EVAP_H)
                    self.scene.addItem(head)
                    
                    comp_out = comp.scenePos() + comp.outlet_pos
                    split_y = Y_COMP + COMP_H + 15
                    draw_pipe(self.scene, comp_out, QPointF(cx, split_y))
                    
                    hgbv_in = hgbv.scenePos() + hgbv.inlet_pos
                    draw_pipe(self.scene, QPointF(cx, split_y), QPointF(hgbv_in.x(), split_y))
                    draw_pipe(self.scene, QPointF(hgbv_in.x(), split_y), hgbv_in)
                    
                    draw_pipe(self.scene, hgbv.scenePos() + hgbv.outlet_pos, hgs.scenePos() + hgs.inlet_pos)
                    
                    cond_in = cond.scenePos() + cond.inlet_pos
                    draw_pipe(self.scene, QPointF(cx, split_y), QPointF(cond_in.x(), split_y))
                    draw_pipe(self.scene, QPointF(cond_in.x(), split_y), cond_in)
                    
                    draw_pipe(self.scene, cond.scenePos() + cond.outlet_pos, lls.scenePos() + lls.inlet_pos)
                    draw_pipe(self.scene, lls.scenePos() + lls.outlet_pos, txv.scenePos() + txv.inlet_pos)
                    
                    dist_in = dist.scenePos() + dist.inlet_pos
                    asc_y = dist_in.y() - 25
                    txv_out = txv.scenePos() + txv.outlet_pos
                    hgs_out = hgs.scenePos() + hgs.outlet_pos
                    
                    asc_label = QGraphicsTextItem("ASC")
                    asc_label.setDefaultTextColor(QColor('#555555'))
                    asc_label.setPos(cx + 5, asc_y - 10)
                    self.scene.addItem(asc_label)
                    
                    draw_pipe(self.scene, txv_out, dist_in)
                    
                    draw_pipe(self.scene, hgs_out, QPointF(hgs_out.x(), asc_y))
                    draw_pipe(self.scene, QPointF(hgs_out.x(), asc_y), QPointF(cx, asc_y))
                    
                    comp_in = comp.scenePos() + comp.inlet_pos
                    head_out = head.scenePos() + head.outlet_pos
                    LEFTMOST_CAS = cx - max(cas_evap_w / 2 + 40, 180)
                    draw_pipe(self.scene, head_out, QPointF(cx, global_merge_y))
                    draw_pipe(self.scene, QPointF(cx, global_merge_y), QPointF(LEFTMOST_CAS, global_merge_y))
                    draw_pipe(self.scene, QPointF(LEFTMOST_CAS, global_merge_y), QPointF(LEFTMOST_CAS, Y_COMP - 20))
                    draw_pipe(self.scene, QPointF(LEFTMOST_CAS, Y_COMP - 20), QPointF(comp_in.x(), Y_COMP - 20))
                    draw_pipe(self.scene, QPointF(comp_in.x(), Y_COMP - 20), comp_in)
                    
                    bound_left = min(cx - cas_evap_w/2 - 60, cx - 180)
                    bound_width = (cx + cas_evap_w/2 + 60) - bound_left
                
                # Boundary box for this individual cassette
                _draw_boundary(self.scene, f"Refrigeration Process [{lb} Cassette]", bound_left, Y_COMP - 40, bound_width, global_merge_y - Y_COMP + 40)
            
            MERGE_Y = global_merge_y

        # Y positions (MERGE_Y is where the loopback starts)
        base_y = MERGE_Y + 100
        
        is_cassette = self.current_mode.startswith('cassette')
        
        if is_cassette:
            ret_air_y = base_y
            ret_air = ColoredBox("Return Air", width=combined_w, height=30, bg_color="#FFCDD2")
            ret_air.setPos(left_edge, ret_air_y)
            self.scene.addItem(ret_air)
            
            fan_y = base_y + 40
            pri_air_y = fan_y + 60 + 10
            
            pri_air = ColoredBox("Primary Discharge Air", width=combined_w, height=30, bg_color="#B3E5FC")
            pri_air.setPos(left_edge, pri_air_y)
            self.scene.addItem(pri_air)
            
            air_bottom_y = pri_air_y
        else:
            pri_air_y = base_y
            pri_air = ColoredBox("Primary Discharge Air", width=combined_w, height=30, bg_color="#B3E5FC")
            pri_air.setPos(left_edge, pri_air_y)
            self.scene.addItem(pri_air)
            
            if self.current_mode == 'modular':
                sec_air = ColoredBox("Secondary Discharge Air", width=combined_w, height=30, bg_color="#FFF9C4")
                sec_air.setPos(left_edge, base_y + 40)
                self.scene.addItem(sec_air)
                fan_y = base_y + 80
            else:
                fan_y = base_y + 40
                
            ret_air_y = fan_y + 60 + 10
            ret_air = ColoredBox("Return Air", width=combined_w, height=30, bg_color="#FFCDD2")
            ret_air.setPos(left_edge, ret_air_y)
            self.scene.addItem(ret_air)
            
            air_bottom_y = ret_air_y

        # Fans
        fan_size = 60
        if self.current_mode == 'modular':
            for mx, label in zip(mod_xs, mod_lbs):
                fan_label = f"Fan {label}".strip() if label else "Fan"
                fan = ColoredBox(fan_label, width=fan_size, height=fan_size, bg_color="#E0E0E0")
                fan.setPos(mx - fan_size / 2, fan_y)
                self.scene.addItem(fan)
                
                # Airflow arrows
                _draw_up_arrow(self.scene, mx, fan_y + fan_size + 10, fan_y + fan_size)
                _draw_up_arrow(self.scene, mx, fan_y, fan_y - 10)
        else: # door mode or cassette mode
            slice_w = combined_w / self.current_count
            for i in range(self.current_count):
                fx = left_edge + (slice_w / 2) + (i * slice_w)
                fan = ColoredBox(f"Fan Dr {i+1}", width=fan_size, height=fan_size, bg_color="#E0E0E0")
                fan.setPos(fx - fan_size / 2, fan_y)
                self.scene.addItem(fan)
                
                # Airflow arrows
                if is_cassette:
                    _draw_up_arrow(self.scene, fx, fan_y - 10, fan_y)
                    _draw_up_arrow(self.scene, fx, fan_y + fan_size, fan_y + fan_size + 10)
                else:
                    _draw_up_arrow(self.scene, fx, fan_y + fan_size + 10, fan_y + fan_size)
                    _draw_up_arrow(self.scene, fx, fan_y, fan_y - 10)

        air_y = base_y - 40
        air_h = (air_bottom_y + 30 + 40) - air_y
        _draw_boundary(self.scene, "Airflow Diagram", process_x, air_y, process_w, air_h)

        # ── Shelving Diagram ──────────────────────────────────────────────────
        shelf_base_y = air_bottom_y + 30 + 100
        num_rows = self.shelf_spin.value()
        shelf_height = 30
        shelf_gap = 10
        shelf_total_h = num_rows * (shelf_height + shelf_gap)
        
        if self.current_mode == 'modular':
            col_w = EVAP_W
            col_xs = [mx - EVAP_W / 2 for mx in mod_xs]
        else: # door mode
            col_w = combined_w / self.current_count
            col_xs = [left_edge + i * col_w for i in range(self.current_count)]
            
        for cx in col_xs:
            for r in range(num_rows):
                sy = shelf_base_y + r * (shelf_height + shelf_gap)
                # Adding a small horizontal gap so columns don't perfectly touch
                shelf = ColoredBox(f"Shelf {r+1}", width=col_w - 6, height=shelf_height, bg_color="#F0F0F0") 
                shelf.setPos(cx + 3, sy)
                self.scene.addItem(shelf)
                
        shelf_bound_h = shelf_total_h + 60
        _draw_boundary(self.scene, "Shelving Diagram", process_x, shelf_base_y - 40, process_w, shelf_bound_h)

        # ── Doors Diagram ─────────────────────────────────────────────────────
        if self.case_combo.currentText() == "Doored":
            door_base_y = shelf_base_y + shelf_total_h + 80
            door_height = 240
            
            mullion_w = 16
            
            if self.current_mode == 'modular':
                M = len(mod_xs)
                # LH End Mullion
                lh_mullion = ColoredBox("", width=mullion_w, height=door_height, bg_color="#B0BEC5")
                lh_mullion.setPos(left_edge - mullion_w - 10, door_base_y)
                self.scene.addItem(lh_mullion)
                
                # RH End Mullion
                rh_mullion = ColoredBox("", width=mullion_w, height=door_height, bg_color="#B0BEC5")
                rh_mullion.setPos(right_edge + 10, door_base_y)
                self.scene.addItem(rh_mullion)
                
                # Doors and CTR Mullions
                door_w = EVAP_W / 2 - 2
                for m, mx in enumerate(mod_xs):
                    door1 = ColoredBox(f"Door {2*m+1}", width=door_w, height=door_height, bg_color="#E1F5FE")
                    door1.setPos(mx - EVAP_W/2, door_base_y)
                    self.scene.addItem(door1)
                    
                    door2 = ColoredBox(f"Door {2*m+2}", width=door_w, height=door_height, bg_color="#E1F5FE")
                    door2.setPos(mx + 2, door_base_y)
                    self.scene.addItem(door2)
                    
                    if m < M - 1:
                        ctr_x = (mod_xs[m] + mod_xs[m+1]) / 2
                        ctr_mullion = ColoredBox("", width=mullion_w, height=door_height, bg_color="#B0BEC5")
                        ctr_mullion.setPos(ctr_x - mullion_w / 2, door_base_y)
                        self.scene.addItem(ctr_mullion)
            else: # door mode
                N = self.current_count
                gap = 4
                total_mullion_w = (N + 1) * mullion_w
                total_gap_w = (2 * N) * gap
                door_w = (combined_w - total_mullion_w - total_gap_w) / N
                
                current_x = left_edge
                
                # LH End Mullion
                lh_mullion = ColoredBox("", width=mullion_w, height=door_height, bg_color="#B0BEC5")
                lh_mullion.setPos(current_x, door_base_y)
                self.scene.addItem(lh_mullion)
                current_x += mullion_w + gap
                
                for i in range(N):
                    door = ColoredBox(f"Door {i+1}", width=door_w, height=door_height, bg_color="#E1F5FE")
                    door.setPos(current_x, door_base_y)
                    self.scene.addItem(door)
                    current_x += door_w + gap
                    
                    if i < N - 1:
                        ctr_mullion = ColoredBox("", width=mullion_w, height=door_height, bg_color="#B0BEC5")
                        ctr_mullion.setPos(current_x, door_base_y)
                        self.scene.addItem(ctr_mullion)
                        current_x += mullion_w + gap
                
                # RH End Mullion
                rh_mullion = ColoredBox("", width=mullion_w, height=door_height, bg_color="#B0BEC5")
                rh_mullion.setPos(current_x, door_base_y)
                self.scene.addItem(rh_mullion)
                    
            door_bound_h = door_height + 60
            _draw_boundary(self.scene, "Doors Diagram", process_x, door_base_y - 40, process_w, door_bound_h)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = TestWindow()
    w.show()
    sys.exit(app.exec())
