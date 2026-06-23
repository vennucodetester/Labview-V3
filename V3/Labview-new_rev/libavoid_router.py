import json
import os
import subprocess
import tempfile
import sys
import logging

logger = logging.getLogger(__name__)

def apply_libavoid_routing(component_items, pipes_model):
    """
    Export the current QGraphicsScene obstacles and pins to a JSON file,
    call the Node.js libavoid router, and parse the resulting polylines back
    into the pipes_model.
    """
    request_data = {
        "obstacles": [],
        "connections": []
    }
    
    # 1. Export obstacles and their pins
    for comp_id, item in component_items.items():
        rect = item.sceneBoundingRect()
        
        obs = {
            "id": comp_id,
            "x": rect.x() - 10,  # add 10px padding
            "y": rect.y() - 10,
            "w": rect.width() + 20,
            "h": rect.height() + 20,
            "pins": []
        }
        
        for port_name, port_item in item.ports.items():
            pos = port_item.scenePos()
            
            # Infer direction based on which edge of the bounding box the port is closest to
            dx_left = abs(pos.x() - rect.left())
            dx_right = abs(pos.x() - rect.right())
            dy_top = abs(pos.y() - rect.top())
            dy_bottom = abs(pos.y() - rect.bottom())
            
            min_d = min(dx_left, dx_right, dy_top, dy_bottom)
            
            if min_d == dx_left:
                direction = 4 # Left
            elif min_d == dx_right:
                direction = 8 # Right
            elif min_d == dy_top:
                direction = 1 # Up
            else:
                direction = 2 # Down
                
            # Calculate proportional offset relative to the unpadded rect
            xOff = (pos.x() - rect.x()) / max(1.0, rect.width())
            yOff = (pos.y() - rect.y()) / max(1.0, rect.height())
            
            # Clamp to 0..1
            xOff = max(0.0, min(1.0, xOff))
            yOff = max(0.0, min(1.0, yOff))
            
            obs["pins"].append({
                "id": port_name,
                "xOff": xOff,
                "yOff": yOff,
                "dir": direction
            })
            
        request_data["obstacles"].append(obs)
        
    for pipe_id, pipe_data in pipes_model.items():
        if pipe_data.get('route_locked'):
            continue
            
        start_comp = pipe_data.get('start_component_id')
        start_port = pipe_data.get('start_port')
        end_comp = pipe_data.get('end_component_id')
        end_port = pipe_data.get('end_port')
        
        if start_comp and start_port and end_comp and end_port:
            request_data["connections"].append({
                "id": pipe_id,
                "start": {"shape": start_comp, "pin": start_port},
                "end": {"shape": end_comp, "pin": end_port}
            })
            
    # 3. Call Node.js router
    try:
        # Create temp files
        with tempfile.NamedTemporaryFile('w', delete=False, suffix='.json') as f_in:
            json.dump(request_data, f_in)
            req_file = f_in.name
            
        with tempfile.NamedTemporaryFile('w', delete=False, suffix='.json') as f_out:
            res_file = f_out.name
            
        # Get path to Node script, handling PyInstaller environment if bundled
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        script_path = os.path.join(base_dir, 'avoid_router.js')
        
        logger.info(f"Running libavoid router: node {script_path} {req_file} {res_file}")
        
        result = subprocess.run(
            ['node', script_path, req_file, res_file], 
            capture_output=True, 
            text=True,
            check=True
        )
        
        if result.stderr:
            logger.error(f"Node router stderr: {result.stderr}")
        if result.stdout:
            logger.info(f"Node router stdout: {result.stdout}")
        
        # Parse result
        with open(res_file, 'r') as f:
            routes = json.load(f)
            
        # Update pipes_model with new route
        for pipe_id, path_points in routes.items():
            if pipe_id in pipes_model:
                pipes_model[pipe_id]['route'] = path_points
                
    except subprocess.CalledProcessError as e:
        logger.error(f"libavoid routing failed with exit code {e.returncode}: {e.stderr}")
        import shutil
        shutil.copy(req_file, 'debug_request.json')
    except Exception as e:
        logger.error(f"libavoid routing failed: {e}")
        import shutil
        shutil.copy(req_file, 'debug_request.json')
    finally:
        # Cleanup temp files
        try:
            if os.path.exists(req_file): os.remove(req_file)
            if os.path.exists(res_file): os.remove(res_file)
        except:
            pass
