import os
import json
import graphviz
import math

# Add the portable graphviz binary to PATH so python graphviz package can find it
GRAPHVIZ_BIN = r"C:\Users\silam\OneDrive\Documents\Lab viewer\HVAC_Dev\windows_10_cmake_Release_Graphviz-15.0.0-win64\Graphviz-15.0.0-win64\bin"
if GRAPHVIZ_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] += os.pathsep + GRAPHVIZ_BIN

def apply_graphviz_layout(model: dict) -> dict:
    """
    Takes an un-routed diagram model (where components might have arbitrary x,y)
    and uses Graphviz to compute optimal, non-overlapping orthogonal positions.
    Returns the updated model.
    """
    dot = graphviz.Digraph(engine='dot')
    
    # Configure graph attributes for schematic layout
    dot.attr(splines='ortho')
    dot.attr(nodesep='1.5')   # Horizontal spacing between nodes
    dot.attr(ranksep='2.5')   # Vertical spacing between ranks
    dot.attr(rankdir='TB')    # Top-to-Bottom
    
    # 1. Add all components as nodes
    # We use roughly standard shapes for scaling. 
    for comp_id, comp_data in model.get('components', {}).items():
        ctype = comp_data.get('type')
        
        # Air sensors don't get routed by pipes, they just float. 
        # We'll handle them manually after the main graph layout.
        if ctype in ['SensorBox', 'AirSensorArray']:
            continue
            
        dot.node(comp_id, shape='box', width='1.5', height='1.5')

    # 2. Add all connections as edges
    for conn_id, conn_data in model.get('pipes', {}).items():
        start_id = conn_data.get('start_component_id')
        end_id = conn_data.get('end_component_id')
        
        # Skip connections involving sensors just in case
        if start_id in model['components'] and end_id in model['components']:
            if model['components'][start_id].get('type') in ['SensorBox', 'AirSensorArray'] or \
               model['components'][end_id].get('type') in ['SensorBox', 'AirSensorArray']:
                continue
                
        dot.edge(start_id, end_id)

    # 3. Generate layout JSON
    try:
        json_data = dot.pipe(format='json').decode('utf-8')
        layout_data = json.loads(json_data)
        
        # We need to find the maximum Y to flip the coordinates (Graphviz Y is up, Qt Y is down)
        max_y = 0
        for obj in layout_data.get('objects', []):
            pos_str = obj.get('pos')
            if pos_str:
                try:
                    x, y = map(float, pos_str.split(','))
                    if y > max_y:
                        max_y = y
                except:
                    pass

        # 4. Apply calculated positions back to the model
        scale_factor = 2.5 # Scale Graphviz points to Qt pixels
        
        for obj in layout_data.get('objects', []):
            comp_id = obj.get('name')
            pos_str = obj.get('pos')
            
            if comp_id in model['components'] and pos_str:
                try:
                    x, y = map(float, pos_str.split(','))
                    
                    # Convert to Qt coordinate system: flip Y, scale up, apply offset
                    qt_x = x * scale_factor
                    qt_y = (max_y - y) * scale_factor
                    
                    model['components'][comp_id]['position'] = [qt_x, qt_y]
                except Exception as e:
                    print(f"Error applying pos {pos_str} to {comp_id}: {e}")

        # 5. Clear all waypoints so the Pipe auto-router kicks in to draw straight lines
        for pipe_id in model.get('pipes', {}):
            model['pipes'][pipe_id]['waypoints'] = []
            if 'route' in model['pipes'][pipe_id]:
                del model['pipes'][pipe_id]['route']

        # 6. Post-process Air Sensors to place them above Evaporators
        _position_air_sensors(model)

    except Exception as e:
        print(f"Graphviz layout failed: {e}")
        # If it fails, return the original model to fallback on old coordinates
        pass
        
    return model

def _position_air_sensors(model):
    """
    Air sensors aren't piped, so Graphviz ignores them. 
    We just find the Evaporators and place sensors near them.
    """
    # Find bounding box of evaporators
    evap_xs = []
    min_y = float('inf')
    
    for comp_id, comp in model['components'].items():
        if comp.get('type') in ['Evaporator', 'AirSensorArray']:
            pos = comp.get('position', [0, 0])
            x = pos[0]
            y = pos[1]
            if comp.get('type') == 'Evaporator':
                evap_xs.append(x)
            if y < min_y:
                min_y = y
                
    if not evap_xs:
        return
        
    # Center sensors
    center_x = sum(evap_xs) / len(evap_xs)
    
    # Place SensorBox
    for comp_id, comp in model['components'].items():
        if comp.get('type') == 'SensorBox':
            pos = comp.get('position', [0, 0])
            comp['position'] = [center_x, min_y - 250]
            
    # Place AirSensorArray
    for comp_id, comp in model['components'].items():
        if comp.get('type') == 'AirSensorArray':
            pos = comp.get('position', [0, 0])
            comp['position'] = [center_x, min_y - 120]
