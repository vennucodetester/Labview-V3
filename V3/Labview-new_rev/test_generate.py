import sys
from PyQt6.QtWidgets import QApplication
from data_manager import DataManager
from diagram_widget import DiagramWidget
from diagram_from_request import build_diagram_for_request

app = QApplication(sys.argv)
dm = DataManager()
model = build_diagram_for_request({
    "modules": [
        {"type": "Evaporator", "count": 2}
    ],
    "condenser": "Air-Cooled"
})
dm.diagram_model = model

w = DiagramWidget(dm)
w.build_scene_from_model()
print("Done!")
