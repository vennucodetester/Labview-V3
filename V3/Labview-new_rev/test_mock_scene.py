import sys
from PyQt6.QtWidgets import QApplication, QGraphicsScene
from data_manager import DataManager
from diagram_components import CompressorComponentItem, CondenserComponentItem, EvaporatorComponentItem
from libavoid_router import apply_libavoid_routing

app = QApplication(sys.argv)
dm = DataManager()
scene = QGraphicsScene()

comp1 = CompressorComponentItem('comp1', {'position': [100, 100]}, dm)
comp2 = CondenserComponentItem('comp2', {'position': [300, 100]}, dm)
comp3 = EvaporatorComponentItem('comp3', {'position': [200, 300]}, dm)

scene.addItem(comp1)
scene.addItem(comp2)
scene.addItem(comp3)

component_items = {
    'comp1': comp1,
    'comp2': comp2,
    'comp3': comp3
}

pipes_model = {
    'pipe1': {
        'start_component_id': 'comp1',
        'start_port': 'outlet',
        'end_component_id': 'comp2',
        'end_port': 'inlet'
    }
}

print("Running libavoid routing...")
apply_libavoid_routing(component_items, pipes_model)
print("Finished!")
