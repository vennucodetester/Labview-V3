
import re

with open('diagram_components.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
in_paint = False
indent_level = 0

for i, line in enumerate(lines):
    stripped = line.strip()
    current_indent = len(line) - len(line.lstrip())
    
    if stripped.startswith('def paint(self, painter, option, widget=None):'):
        # Check if we are inside DraggableTextItem, SensorBoxItem, PortItem, PipeItem, RemoteLineEndpointItem
        # Actually it's easier to just rename ALL component paint methods.
        # We can detect if it's a component item if the class ends in 'ComponentItem'
        pass

    new_lines.append(line)


with open('diagram_components.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
in_component_class = False

for line in lines:
    stripped = line.strip()
    
    if stripped.startswith('class '):
        if 'ComponentItem' in line or 'Item' in line:
            # specifically we don't want to disable paint for PortItem, PipeItem, SensorBoxItem, DraggableTextItem, RemoteLineEndpointItem
            exclude = ['PortItem', 'PipeItem', 'SensorBoxItem', 'DraggableTextItem', 'RemoteLineEndpointItem']
            if any(ex in line for ex in exclude):
                in_component_class = False
            else:
                in_component_class = True
        else:
            in_component_class = False

    if in_component_class and stripped.startswith('def paint(self'):
        # Rename paint to legacy_paint to disable custom drawing
        line = line.replace('def paint', 'def _legacy_paint')
        print('Disabled paint in a component class')

    new_lines.append(line)

with open('diagram_components.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print('Done!')

