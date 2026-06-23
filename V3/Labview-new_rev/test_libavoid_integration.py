import sys
from PyQt5.QtWidgets import QApplication
from data_manager import DataManager
from diagram_widget import DiagramWidget

app = QApplication(sys.argv)
dm = DataManager()


# Trigger 3-module template
dm.save_test_request("3-module", {
    "modules": [
        {"type": "Compressor", "count": 1},
        {"type": "Condenser", "count": 1},
        {"type": "Evaporator", "count": 1}
    ]
})

widget = DiagramWidget(dm)
# This will call rebuild_scene
widget.build_scene_from_model()

print("Diagram built successfully!")
