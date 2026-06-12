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

# --- GEOMETRY HELPERS ---

def find_label_position(manager, target_px, target_py, text_w, text_h, frame_bounds):
    """Calculates best (x, y) for a label. Returns: (pos, needs_leader, edge_type)"""
    f_min, f_max = frame_bounds
    
    # Phase 1: Local Search (Proximal)
    local_offsets = [(20, -30), (20, 30), (-60, -30), (-60, 30)]
    for ox, oy in local_offsets:
        tx, ty = target_px + ox, target_py + oy
        if not manager.is_overlapping(tx, ty, text_w, text_h):
            if f_min < tx < f_max and f_min < ty < f_max:
                return (tx, ty), False, None

    # Phase 2: Margin Search (Distal)
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
        else: # Bottom
            tx, ty = target_px - 20 + s_off, max(f_max + 25, target_py + MIN_ARROW_LEN)

        if not manager.is_overlapping(tx + text_w/2, ty + text_h/2, text_w, text_h):
            return (tx, ty), True, edge
    return None, False, None

def get_connection_point(tx, ty, text_w, text_h, edge):
    """Determines where the leader line attaches to the text bounding box."""
    if edge == 'L': return (tx + text_w, ty + text_h / 2)
    if edge == 'R': return (tx, ty + text_h / 2)
    if edge == 'T': return (tx + text_w / 2, ty + text_h)
    return (tx + text_w / 2, ty) # Bottom


def get_extended_point(p1, p2, frame_bounds=(100, 900)):
    """Calculates the intersection of a ray (p1->p2) with the frame."""
    f_min, f_max = frame_bounds
    x1, y1 = p1
    x2, y2 = p2
    
    dx = x2 - x1
    dy = y2 - y1
    
    # Avoid division by zero for perfectly vertical/horizontal lines
    t_values = []
    if dx != 0:
        t_values.append((f_min - x1) / dx)
        t_values.append((f_max - x1) / dx)
    if dy != 0:
        t_values.append((f_min - y1) / dy)
        t_values.append((f_max - y1) / dy)
    
    # We only want t > 0 (points in the direction of the extension)
    # The smallest positive t is the first boundary we hit
    valid_t = [t for t in t_values if t > 0]
    if not valid_t: return p2
    
    t = min(valid_t)
    return (x1 + t * dx, y1 + t * dy)

BLUE = (0, 0, 255, 255)

#Extending Line 

def draw_extended_edge(draw, edge, frame_bounds=(100, 900)):
    """Case 1: Extend an existing edge to the frame boundaries in both directions."""
    p1 = DrawGraph.V2P(edge.tail.p)
    p2 = DrawGraph.V2P(edge.head.p)
    
    ext_start = get_extended_point(p2, p1, frame_bounds) # Extend backwards
    ext_end = get_extended_point(p1, p2, frame_bounds)   # Extend forwards
    
    draw.line([ext_start, ext_end], fill=BLUE, width=6)

def draw_line_between_points(draw, v1_p, v2_p, extend=False, frame_bounds=(100, 900)):
    """Case 2: Connect two arbitrary points. Optional extension."""
    p1 = DrawGraph.V2P(v1_p)
    p2 = DrawGraph.V2P(v2_p)
    
    if extend:
        p1 = get_extended_point(p2, p1, frame_bounds)
        p2 = get_extended_point(p1, p2, frame_bounds)
        
    draw.line([p1, p2], fill=BLUE, width=4)

def draw_axis_aligned_line(draw, vertex_p, direction='H', frame_bounds=(100, 900)):
    """Case 3: Draw a horizontal or vertical line passing through a vertex."""
    f_min, f_max = frame_bounds
    px, py = DrawGraph.V2P(vertex_p)
    
    if direction.upper() == 'H':
        draw.line([(f_min, py), (f_max, py)], fill=BLUE, width=4)
    else: # Vertical
        draw.line([(px, f_min), (px, f_max)], fill=BLUE, width=4)

#Hightlighting functions
def highlight_vertex(draw, vertex_p, color=(255, 215, 0, 200)):
    """
    Draw a gold small circle for the point
    """
    px, py = DrawGraph.V2P(vertex_p)
    r = 12  
    
    draw.ellipse(
        [px - r, py - r, px + r, py + r], 
        fill=color, 
        outline=(184, 134, 11, 255), # DarkGoldenrod outline
        width=4
    )

def highlight_edge(draw, edge, color=(0, 255, 255, 120)):
    """Draws a thick, semi-transparent blue (Cyan) highlighter effect over an edge."""
    p1 = DrawGraph.V2P(edge.tail.p)
    p2 = DrawGraph.V2P(edge.head.p)
    # Width 15 creates a thick 'marker' stroke
    draw.line([p1, p2], fill=color, width=10)

# --- DRAWING HELPERS ---

def draw_leader_with_arrow(draw, start_pos, end_pos, color):
    draw.line([start_pos, end_pos], fill=color, width=2)
    angle = math.atan2(end_pos[1] - start_pos[1], end_pos[0] - start_pos[0])
    arrow_len, spread = 20, 0.4
    p1 = (start_pos[0] + arrow_len * math.cos(angle + spread), start_pos[1] + arrow_len * math.sin(angle + spread))
    p2 = (start_pos[0] + arrow_len * math.cos(angle - spread), start_pos[1] + arrow_len * math.sin(angle - spread))
    draw.polygon([start_pos, p1, p2], fill=color)

def draw_labeled_feature(draw, manager, point, label_text, font, color, frame_bounds=(100, 900)):
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

# --- PRIMARY TOOLS ---

def label_vertices(res_map, vertex_list, manager, maxX, maxY, filename="tool_labeled_points.png"):
    img_w, img_h = int(200 + 800 * maxX), int(200 + 800 * maxY)
    img = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    DrawGraph.DrawAllFaces(res_map, draw, manager) 

    font_labels = DrawGraph.GetSystemFont(35)
    for i, v in enumerate(vertex_list):
        px, py = DrawGraph.V2P(v.p)
        draw.ellipse([px-10, py-10, px+10, py+10], fill=(255,0,0,255), outline=(0,0,0,255), width=2)
        draw_labeled_feature(draw, manager, v.p, f"P{i+1}", font_labels, (0,0,255,255))
    
    img.save(filename)

def label_interior_angles(res_map, angle_list, manager, maxX, maxY, filename="tool_labeled_angles.png"):
    img_w, img_h = int(200 + 800 * maxX), int(200 + 800 * maxY)
    img = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    DrawGraph.DrawAllFaces(res_map, draw, manager) 

    font_labels = DrawGraph.GetSystemFont(35)
    for i, angle_data in enumerate(angle_list):
        px, py = DrawGraph.V2P(angle_data.p)
        draw.ellipse([px-8, py-8, px+8, py+8], fill=(255,0,0,255), outline=(0,0,0,255), width=2)
        draw_labeled_feature(draw, manager, angle_data.p, f"a{i+1}", font_labels, (0,0,255,255))

    p_bl, p_tr = DrawGraph.V2P(Graph.Vector(0, 0)), DrawGraph.V2P(Graph.Vector(1.0, 1.0))
    draw.rectangle([p_bl[0], p_tr[1], p_tr[0], p_bl[1]], outline=(0,0,0,255), width=4)
    img.save(filename)

# --- UNION AND MAIN ---

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

    u_lp, _ = Graph.LetterPointFace(fa) # simplified U placement
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
    Graph.initialize()
    maxX, maxY = 1.0, 1.0
    seed = random.randint(0, 9999)
    res_map = BuildRandomMap.BuildRandomMap(8, maxX, maxY, seed)
    label_man = LabelManager()

    # Label Vertices
    vertex_pool = [v for v in res_map.vertices if len(v.outarcs) > 2] or res_map.vertices
    selected_vertices = random.sample(vertex_pool, min(5, len(vertex_pool)))
    label_vertices(res_map, selected_vertices, label_man, maxX, maxY)
    
    # Label Angles
    all_angles = []
    for face in res_map.faces:
        if face.bounded:
            verts = face.vertices[:-1] if face.vertices[0] == face.vertices[-1] else face.vertices
            all_angles.extend([Angle(v.p, face) for v in verts])
    label_interior_angles(res_map, random.sample(all_angles, min(len(all_angles), 5)), label_man, maxX, maxY)

    print(f"Map processing complete with seed {seed}.")



    #Extending lines and Highlighting
    # 1. Setup Canvas (Standard setup like your other tools)
    img_w, img_h = int(200 + 800 * maxX), int(200 + 800 * maxY)
    img = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # Draw the base map first
    DrawGraph.DrawAllFaces(res_map, draw, label_man)

    # # --- CASE 1: EXTENDING A RANDOM EDGE ---
    # # Filter for bounded edges if you want to avoid extending the infinite outer frame
    bounded_edges = [e for e in res_map.edges if e.leftFace.bounded or e.reverse.leftFace.bounded]

    if bounded_edges:
        # Randomly select one edge from the list
        some_edge = random.choice(bounded_edges)
        
    #     print(f"Randomly extending edge connecting {some_edge.tail.p} and {some_edge.head.p}")
    #     draw_extended_edge(draw, some_edge)
    # else:
    #     print("No valid bounded edges found to extend.")

    # --- CASE 2: LINE BETWEEN TWO POINTS (With Extension) ---
    # Pick two random vertices and draw an extended line passing through both
    # if len(res_map.vertices) >= 2:
    #     v1, v2 = random.sample(res_map.vertices, 2)
    #     draw_line_between_points(draw, v1.p, v2.p, extend=False)

    # # # --- CASE 3: AXIS-ALIGNED LINE ---
    # # # Pick a vertex and draw a vertical line through it
    # some_vertex = random.choice(res_map.vertices)
    # draw_axis_aligned_line(draw, some_vertex.p, direction='H')

    # --- NEW: HIGHLIGHTING ---
    # Highlight a specific vertex in Yellow/Gold
    # highlight_vertex(draw, some_vertex.p, color=(255, 215, 0, 200))
    
    # # Highlight a specific edge
    highlight_edge(draw, some_edge, color=(0,0,255,255)) # Transparent Green

    # Save the result
    img.save("test1.png")

if __name__ == "__main__":
    main()