
path = 'C:/Users/silam/OneDrive/Documents/Lab viewer/HVAC_Dev/diagram_components.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('# --- OVERRIDE CLASSES FOR SIMPLIFIED UI ---')
if idx != -1:
    content = content[:idx]

content = content.replace('def _legacy_paint(', 'def paint(')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

