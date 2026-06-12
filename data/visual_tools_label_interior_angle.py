import numpy as np
import random
import os
import math
from PIL import Image, ImageDraw
from collections import namedtuple

# Ensure these custom modules are in your python path
import Graph
import BuildRandomMap 
import DrawGraph 
import Questions

# Data structure for angle tasks - move to Graph.py?
Angle = namedtuple('Angle', ['p', 'parent_face'])

class LabelManager:
    """Manages spatial UI to prevent labels from overlapping."""
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

# --- GEOMETRY & ANNOTATION HELPERS ---

def find_label_position(manager, target_px, target_py, text_w, text_h, frame_bounds):
    """Finds non-overlapping coordinates for a text label near a point."""
    f_min, f_max = frame_bounds
    # Try 4 diagonal corners first
    local_offsets = [(25, -35), (25, 35), (-65, -35), (-65, 35)]
    for ox, oy in local_offsets:
        tx, ty = target_px + ox, target_py + oy
        if not manager.is_overlapping(tx, ty, text_w, text_h):
            if f_min < tx < f_max and f_min < ty < f_max:
                return (tx, ty), False, None

    # Fallback: Find closest frame edge and use a leader line (arrow)
    dists = {'L': target_px - f_min, 'R': f_max - target_px, 'T': target_py - f_min, 'B': f_max - target_py}
    edge = min(dists, key=dists.get)
    for s_off in [0, 45, -45]:
        if edge == 'L': tx, ty = target_px - 80, target_py - 15 + s_off
        elif edge == 'R': tx, ty = target_px + 40, target_py - 15 + s_off
        elif edge == 'T': tx, ty = target_px - 20 + s_off, target_py - 80
        else: tx, ty = target_px - 20 + s_off, target_py + 40
        if not manager.is_overlapping(tx + text_w/2, ty + text_h/2, text_w, text_h):
            return (tx, ty), True, edge
    return None, False, None

def get_connection_point(tx, ty, text_w, text_h, edge):
    """Determines where the leader line touches the label box."""
    if edge == 'L': return (tx + text_w, ty + text_h / 2)
    if edge == 'R': return (tx, ty + text_h / 2)
    if edge == 'T': return (tx + text_w / 2, ty + text_h)
    return (tx + text_w / 2, ty)

def draw_leader_with_arrow(draw, start_pos, end_pos, color):
    """Draws a line with a small triangular arrowhead."""
    draw.line([start_pos, end_pos], fill=color, width=2)
    angle = math.atan2(end_pos[1] - start_pos[1], end_pos[0] - start_pos[0])
    arrow_len, spread = 15, 0.4
    p1 = (start_pos[0] + arrow_len * math.cos(angle + spread), start_pos[1] + arrow_len * math.sin(angle + spread))
    p2 = (start_pos[0] + arrow_len * math.cos(angle - spread), start_pos[1] + arrow_len * math.sin(angle - spread))
    draw.polygon([start_pos, p1, p2], fill=color)

def draw_labeled_feature(draw, manager, point, label_text, font, color, frame_bounds=(100, 900)):
    """Draws text labels with smart positioning and optional leader lines."""
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

def draw_interior_arc(draw, angle_data, radius=40, color=(0, 150, 0, 255)):
    p_center = angle_data.p
    face = angle_data.parent_face
    
    # 1. Get the neighbors in the specific face
    e_in = next((e for e in face.edges if e.head.p == p_center), None)
    e_out = next((e for e in face.edges if e.tail.p == p_center), None)
    
    if not e_in or not e_out: return

    # 2. CONVERT ALL POINTS TO PIXELS FIRST
    # Center pixel
    cx, cy = DrawGraph.V2P(p_center)
    # Previous vertex pixel
    px_prev, py_prev = DrawGraph.V2P(e_in.tail.p)
    # Next vertex pixel
    px_next, py_next = DrawGraph.V2P(e_out.head.p)

    # 3. Calculate pixel-based vectors
    # This ensures the angle perfectly matches the drawn lines
    v_prev = (px_prev - cx, py_prev - cy)
    v_next = (px_next - cx, py_next - cy)

    # 4. Calculate angles in PIL's coordinate system
    ang_prev = math.degrees(math.atan2(v_prev[1], v_prev[0]))
    ang_next = math.degrees(math.atan2(v_next[1], v_next[0]))

    # 5. Define the interior sweep (From Prev to Next)
    start, end = ang_prev, ang_next
    
    while end < start:
        end += 360
    
    sweep = end - start
    
    # Skip straight lines
    if abs(sweep - 180.0) < 0.1:
        return

    # 6. Draw using the pixel-based bounding box
    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
    draw.arc(bbox, start=start, end=end, fill=color, width=5)

USED_LABELS = {'vertex': set(), 'angle': set()}

def reset_label_session():
    """Resets tracking for duplicated labels."""
    global USED_LABELS
    USED_LABELS['vertex'].clear()
    USED_LABELS['angle'].clear()

def tool_label_vertices(draw, manager, vertex_list, labels=None):
    """Labels vertices with red anchors and blue text."""
    global USED_LABELS
    if labels is None:
        labels = [str(i+1) for i in range(len(vertex_list))]
    
    font = DrawGraph.GetSystemFont(35)
    for v, text in zip(vertex_list, labels):
        USED_LABELS['vertex'].add(text)
        px, py = DrawGraph.V2P(v.p)
        draw.ellipse([px-10, py-10, px+10, py+10], fill=(255,0,0,255), outline=(0,0,0,255), width=2)
        draw_labeled_feature(draw, manager, v.p, text, font, (0,0,255,255))

def tool_label_interior_angles(draw, manager, angle_list, labels=None):
    """Labels interior angles with green arcs and green text."""
    global USED_LABELS
    if labels is None:
        labels = [str(i+1) for i in range(len(angle_list))]
    
    font = DrawGraph.GetSystemFont(35)
    for angle_data, text in zip(angle_list, labels):
        USED_LABELS['angle'].add(text)
        draw_interior_arc(draw, angle_data)
        draw_labeled_feature(draw, manager, angle_data.p, text, font, (0,150,0,255))


# --- HIGHLIGHTING A REGION ---
def tool_highlight_face(draw, face, color=(0, 255, 255, 110)):
    """
    Fills a specific region with a semi-transparent highlight color.
    Uses an overlay to properly support alpha blending in PIL.
    """

    # Convert all vertex coordinates of the face to pixel coordinates
    pixel_coords = [DrawGraph.V2P(v.p) for v in face.vertices]

    # Create transparent overlay (needed because PIL polygon alpha is unreliable on main canvas)
    overlay = Image.new('RGBA', draw.im.size, (255, 255, 255, 0))
    temp_draw = ImageDraw.Draw(overlay)
    # Draw filled polygon on overlay
    temp_draw.polygon(pixel_coords, fill=color)

    return overlay




# --- MAIN EXECUTION ---

def main():
    maxX, maxY = 1.0, 1.0
    seed = random.randint(0, 9999)

    # Initialize map and label tracking
    Graph.initialize()
    res_map = BuildRandomMap.BuildRandomMap(8, maxX, maxY, seed)
    label_man = LabelManager()
    reset_label_session()

    # 1. Initialize Persistent Canvas
    img_w, img_h = int(200 + 800 * maxX), int(200 + 800 * maxY)
    img = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Layer 0: Draw base graph
    DrawGraph.DrawAllFaces(res_map, draw, label_man)

    # 2. Pick a bounded face
    bounded_faces = [f for f in res_map.faces if f.bounded]
    if not bounded_faces:
        print("No bounded regions found.")
        return

    target_face = random.choice(bounded_faces)
    print(f"Studying Region: {target_face.letter}")


    # 3. ONLY: Highlight region
    highlight_layer = tool_highlight_face(
        draw,
        target_face,
        color = (0, 255, 255, 90)  # light green
    )

    img = Image.alpha_composite(img, highlight_layer)

    # 4. Save result
    out_file = "region_highlight.png"
    img.save(out_file)
    print(f"Saved highlighted region image as {out_file}")


if __name__ == "__main__":
    main()