import numpy as np
import random
import os
import math
from PIL import Image, ImageDraw
from collections import namedtuple

import Graph
import BuildRandomMap 
import DrawGraph 
import Questions

# Data structure for angles
Angle = namedtuple('Angle', ['p', 'parent_face'])

"""
LabelManager handles collision avoidance for map annotations.
Maintains a registry of 'reserved' rectangular areas to ensure labels for 
vertices, regions, and angles remain legible without overlapping.
"""
class LabelManager:
    def __init__(self):
        self.reserved_areas = []

    def reserve(self, x, y, width, height, padding=10):
        x1, y1 = x - width/2 - padding, y - height/2 - padding
        x2, y2 = x + width/2 + padding, y + height/2 + padding
        self.reserved_areas.append((x1, y1, x2, y2))

    def is_overlapping(self, x, y, width, height, padding=10):
        nx1, ny1 = x - width/2 - padding, y - height/2 - padding
        nx2, ny2 = x + width/2 + padding, y + height/2 + padding
        for (ex1, ey1, ex2, ey2) in self.reserved_areas:
            if not (nx2 < ex1 or nx1 > ex2 or ny2 < ey1 or ny1 > ey2):
                return True
        return False
    

# Action: we record a list of actions, and allow users to undo actions
class Action:
    """Stores a function and its arguments to be replayed later."""
    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def execute(self, draw, img, manager):
        """Runs the stored command on the provided canvas/image."""
        return self.func(draw, img, manager, *self.args, **self.kwargs)
    

class AnnotationSession:
    """Manages the history of actions and handles the 'Undo' logic."""
    def __init__(self, res_map, img_size):
        self.res_map = res_map
        self.img_size = img_size
        self.actions = [] 

    def add_action(self, func, *args, **kwargs):
        """Add a new step to the list."""
        new_action = Action(func, *args, **kwargs)
        self.actions.append(new_action)

    def undo_last(self):
        """Standard undo: removes the most recent step."""
        if self.actions:
            self.actions.pop()

    def remove_step(self, index):
        """Advanced undo: remove Step 2 while keeping Step 3 and 4."""
        if 0 <= index < len(self.actions):
            self.actions.pop(index)

    def render(self):
        """Redraws everything from scratch based on the action list."""
        # 1. Create fresh background
        img = Image.new("RGBA", self.img_size, (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        manager = LabelManager() 
        
        # 2. Draw the base map
        DrawGraph.DrawAllFaces(self.res_map, draw, manager)
        
        # 3. Replay all actions in order
        for action in self.actions:
            action.execute(draw, img, manager)
            
        return img


# --- GEOMETRY HELPERS ---

def find_label_position(manager, target_px, target_py, text_w, text_h, frame_bounds):
    """Calculates best (x, y) for a label. Returns: (pos, needs_leader, edge_type)"""
    f_min, f_max = frame_bounds
    
    local_offsets = [(20, -30), (20, 30), (-60, -30), (-60, 30)]
    for ox, oy in local_offsets:
        tx, ty = target_px + ox, target_py + oy
        if not manager.is_overlapping(tx, ty, text_w, text_h):
            if f_min < tx < f_max and f_min < ty < f_max:
                return (tx, ty), False, None

    dists = {'L': target_px - f_min, 'R': f_max - target_px, 'T': target_py - f_min, 'B': f_max - target_py}
    edge = min(dists, key=dists.get)
    MIN_ARROW_LEN = 50
    
    for s_off in [0, 45, -45, 90, -90, 135, -135]:
        if edge == 'L':
            tx, ty = min(f_min - 75, target_px - MIN_ARROW_LEN - text_w), target_py - 15 + s_off
        elif edge == 'R':
            tx, ty = max(f_max + 25, target_px + MIN_ARROW_LEN), target_py - 15 + s_off
        elif edge == 'T':
            tx, ty = target_px - 20 + s_off, min(f_min - 65, target_py - MIN_ARROW_LEN - text_h)
        else:
            tx, ty = target_px - 20 + s_off, max(f_max + 25, target_py + MIN_ARROW_LEN)

        if not manager.is_overlapping(tx + text_w/2, ty + text_h/2, text_w, text_h):
            return (tx, ty), True, edge
    return None, False, None

def get_connection_point(tx, ty, text_w, text_h, edge):
    if edge == 'L': return (tx + text_w, ty + text_h / 2)
    if edge == 'R': return (tx, ty + text_h / 2)
    if edge == 'T': return (tx + text_w / 2, ty + text_h)
    return (tx + text_w / 2, ty)

def get_extended_point(p1, p2, frame_bounds=(100, 900)):
    f_min, f_max = frame_bounds
    x1, y1 = p1
    x2, y2 = p2
    
    dx = x2 - x1
    dy = y2 - y1
    
    t_values = []
    if dx != 0:
        t_values.append((f_min - x1) / dx)
        t_values.append((f_max - x1) / dx)
    if dy != 0:
        t_values.append((f_min - y1) / dy)
        t_values.append((f_max - y1) / dy)
    
    valid_t = [t for t in t_values if t > 0]
    if not valid_t: return p2
    
    t = min(valid_t)
    return (x1 + t * dx, y1 + t * dy)

BLUE = (0, 0, 255, 255)

def draw_extended_edge(draw, edge, frame_bounds=(100, 900)):
    p1 = DrawGraph.V2P(edge.tail.p)
    p2 = DrawGraph.V2P(edge.head.p)
    
    ext_start = get_extended_point(p2, p1, frame_bounds)
    ext_end = get_extended_point(p1, p2, frame_bounds)
    
    draw.line([ext_start, ext_end], fill=BLUE, width=6)

def draw_line_between_points(draw, v1_p, v2_p, extend=False, frame_bounds=(100, 900)):
    p1 = DrawGraph.V2P(v1_p)
    p2 = DrawGraph.V2P(v2_p)
    
    if extend:
        p1 = get_extended_point(p2, p1, frame_bounds)
        p2 = get_extended_point(p1, p2, frame_bounds)
        
    draw.line([p1, p2], fill=BLUE, width=4)

def draw_axis_aligned_line(draw, vertex_p, direction='H', frame_bounds=(100, 900)):
    f_min, f_max = frame_bounds
    px, py = DrawGraph.V2P(vertex_p)
    
    if direction.upper() == 'H':
        draw.line([(f_min, py), (f_max, py)], fill=BLUE, width=4)
    else:
        draw.line([(px, f_min), (px, f_max)], fill=BLUE, width=4)

def highlight_vertex(draw, vertex_p, color=(255, 215, 0, 200)):
    px, py = DrawGraph.V2P(vertex_p)
    r = 12  
    
    draw.ellipse(
        [px - r, py - r, px + r, py + r], 
        fill=color, 
        outline=(184, 134, 11, 255),
        width=4
    )

def highlight_edge(draw, edge, color=(0, 255, 255, 120)):
    p1 = DrawGraph.V2P(edge.tail.p)
    p2 = DrawGraph.V2P(edge.head.p)
    draw.line([p1, p2], fill=color, width=10)

def draw_leader_with_arrow(draw, start_pos, end_pos, color):
    draw.line([start_pos, end_pos], fill=color, width=2)
    angle = math.atan2(end_pos[1] - start_pos[1], end_pos[0] - start_pos[0])
    arrow_len, spread = 20, 0.4
    p1 = (start_pos[0] + arrow_len * math.cos(angle + spread), start_pos[1] + arrow_len * math.sin(angle + spread))
    p2 = (start_pos[0] + arrow_len * math.cos(angle - spread), start_pos[1] + arrow_len * math.sin(angle - spread))
    draw.polygon([start_pos, p1, p2], fill=color)

def draw_labeled_feature(draw, img, manager, point, label_text, font, color, frame_bounds=(100, 900)):
    """Standard tool for labeling. Prefixed with (draw, img, manager)."""
    px, py = DrawGraph.V2P(point)
    text_w, text_h = 45, 30
    
    pos_data, needs_leader, edge = find_label_position(manager, px, py, text_w, text_h, frame_bounds)
    
    if pos_data:
        tx, ty = pos_data
        if needs_leader:
            conn_p = get_connection_point(tx, ty, text_w, text_h, edge)
            draw_leader_with_arrow(draw, (px, py), conn_p, color)
            
        draw.text((tx, ty), label_text, fill=color, font=font, stroke_width=2, stroke_fill=(255,255,255,255))
        manager.reserve(tx + text_w/2, ty + text_h/2, text_w, text_h)

def reset_label_session():
    global USED_LABELS
    USED_LABELS['vertex'].clear()
    USED_LABELS['angle'].clear()

def label_vertices(res_map, vertex_list, labels=None, manager=None, maxX=1.0, maxY=1.0, filename="tool_labeled_points.png"):
    global USED_LABELS
    category = 'vertex'
    
    if labels is not None:
        if len(vertex_list) != len(labels):
            raise ValueError("Mismatch")
        for l in labels:
            USED_LABELS[category].add(l)
    else:
        labels = []
        for i in range(len(vertex_list)):
            l = str(i + 1)
            USED_LABELS[category].add(l)
            labels.append(l)

    img_w, img_h = int(200 + 800 * maxX), int(200 + 800 * maxY)
    img = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    DrawGraph.DrawAllFaces(res_map, draw, manager) 
    font_labels = DrawGraph.GetSystemFont(35)

    for v, label_text in zip(vertex_list, labels):
        px, py = DrawGraph.V2P(v.p)
        draw.ellipse([px-10, py-10, px+10, py+10], fill=(255,0,0,255))
        # Note: Internal call passes 'img' as required by updated signature
        draw_labeled_feature(draw, img, manager, v.p, label_text, font_labels, (0,0,255,255))
    
    img.save(filename)
    return img

USED_ANGLE_LABELS = set()

def tool_draw_interior_arc(draw, img, manager, angle_data, radius=45, color=(0, 150, 0, 255)):
    """Draws an interior arc based on the face's CCW topology."""
    p_center = angle_data.p
    face = angle_data.parent_face
    
    e_in = next((e for e in face.edges if e.head.p == p_center), None)
    e_out = next((e for e in face.edges if e.tail.p == p_center), None)
    
    if not e_in or not e_out:
        return

    cx, cy = DrawGraph.V2P(p_center)
    px_prev, py_prev = DrawGraph.V2P(e_in.tail.p)
    px_next, py_next = DrawGraph.V2P(e_out.head.p)

    v_prev = (px_prev - cx, py_prev - cy)
    v_next = (px_next - cx, py_next - cy)

    ang_prev = math.degrees(math.atan2(v_prev[1], v_prev[0]))
    ang_next = math.degrees(math.atan2(v_next[1], v_next[0]))

    start, end = ang_prev, ang_next
    while end < start:
        end += 360
    
    if abs((end - start) - 180.0) < 0.1:
        return

    # Change py to cy
    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
    draw.arc(bbox, start=start, end=end, fill=color, width=5)

def draw_union(res_map, fa, fb, manager, maxX, maxY, filename="union_result.png"):
    img_w, img_h = int(200 + 800 * maxX), int(200 + 800 * maxY)
    img = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    DrawGraph.InitColors(alpha=153)
    font_bold, font_small = DrawGraph.GetSystemFont(80), DrawGraph.GetSystemFont(45)
    shared_edge_ids = get_shared_edges(fa, fb)
    
    for face in res_map.faces:
        if not face.bounded: continue
        fill_color = (147, 112, 219, 180) if face in (fa, fb) else DrawGraph.colors[face.color]
        draw.polygon(DrawGraph.FaceVertex2P(face), fill=fill_color)

    for edge in res_map.edges:
        if id(edge) in shared_edge_ids: continue
        draw.line([DrawGraph.V2P(edge.tail.p), DrawGraph.V2P(edge.head.p)], fill=(0,0,0,255), width=6)

    for face in res_map.faces:
        if face.bounded and face not in (fa, fb):
            lp, d = Graph.LetterPointFace(face)
            coords = DrawGraph.V2P(lp)
            draw.text(coords, face.letter, fill=(0,0,0,255), font=(font_bold if d > 0.06 else font_small), anchor="mm")
            manager.reserve(coords[0], coords[1], 35, 35)

    u_lp, _ = Graph.LetterPointFace(fa)
    draw.text(DrawGraph.V2P(u_lp), "U", fill=(0,0,0,255), font=font_bold, anchor="mm")
    
    p_bl, p_tr = DrawGraph.V2P(Graph.Vector(0, 0)), DrawGraph.V2P(Graph.Vector(1.0, 1.0))
    draw.rectangle([p_bl[0], p_tr[1], p_tr[0], p_bl[1]], outline=(0,0,0,255), width=4)
    img.save(filename)

def get_shared_edges(fa, fb):
    shared = set()
    for edge in fa.edges:
        if edge.reverse.leftFace == fb:
            shared.update([id(edge), id(edge.reverse)])
    return shared


def main():
    maxX, maxY = 1.0, 1.0
    seed = random.randint(0, 9999)
    Graph.initialize()
    res_map = BuildRandomMap.BuildRandomMap(8, maxX, maxY, seed)
    
    img_w, img_h = int(200 + 800 * maxX), int(200 + 800 * maxY)
    img_size = (img_w, img_h)
    
    session = AnnotationSession(res_map, img_size)

    bounded_faces = [f for f in res_map.faces if f.bounded]
    if not bounded_faces:
        print("No bounded regions found.")
        return
    target_face = random.choice(bounded_faces)
    print(f"Studying Region: {target_face.letter}")

    # Standardized Tool: Highlight
    def tool_highlight_region(draw, img, manager, face, color):
        pixel_coords = [DrawGraph.V2P(v.p) for v in face.trueVertices ]
        overlay = Image.new('RGBA', img.size, (255, 255, 255, 0))
        d = ImageDraw.Draw(overlay)
        d.polygon(pixel_coords, fill=color)
        img.alpha_composite(overlay)

    session.add_action(tool_highlight_region, target_face, color=(255, 255, 0, 70))

    f_verts = target_face.trueVertices [:-1] if target_face.trueVertices [0] == target_face.trueVertices [-1] else target_face.trueVertices 
    
    font = DrawGraph.GetSystemFont(35)
    for i, v in enumerate(f_verts):
        # Standardized Tool: Dot
        def tool_draw_dot(draw, img, manager, p):
            px, py = DrawGraph.V2P(p)
            draw.ellipse([px-8, py-8, px+8, py+8], fill=(255,0,0,255))
        
        session.add_action(tool_draw_dot, v.p)
        session.add_action(draw_labeled_feature, v.p, f"v{i+1}", font, (0, 0, 255, 255))

        angle_info = Angle(v.p, target_face)
        session.add_action(tool_draw_interior_arc, angle_info)

    final_img = session.render()
    out_file = "region_study_with_actions.png"
    final_img.save(out_file)
    print(f"Process complete. Final image saved as {out_file}")

if __name__ == "__main__":
    main()