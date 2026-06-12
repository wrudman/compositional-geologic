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
    def __init__(self, res_map, img_size):
        self.res_map = res_map
        self.img_size = img_size
        self.actions = []  # This is the list add_action appends to
        
        # Counters and Label Tracking
        self.counters = {"vertex": 1, "angle": 1, "edge": 1}
        self.used_labels = {"vertex": set(), "angle": set(), "edge": set()}

    def add_action(self, func, *args, **kwargs):
        """
        The missing method: Stores a function and its arguments 
        to be executed later during render().
        """
        self.actions.append((func, args, kwargs))

    def _generate_label(self, category, prefix):
        """Internal helper to handle auto-enumeration logic."""
        label = f"{prefix}{self.counters[category]}"
        while label in self.used_labels[category]:
            self.counters[category] += 1
            label = f"{prefix}{self.counters[category]}"
        self.used_labels[category].add(label)
        return label

    def add_vertex_action(self, vertex, label=None, auto_enumerate=False):
        """High-level method to add a vertex labeling task."""
        final_label = label
        if auto_enumerate:
            final_label = self._generate_label("vertex", "v")
        elif label:
            self.used_labels["vertex"].add(str(label))
            
        # Now self.add_action will work!
        self.add_action(tool_label_vertex, vertex, final_label)

    def add_angle_action(self, angle_data, label=None, auto_enumerate=False):
        """High-level method to add an angle labeling task."""
        final_label = label
        if auto_enumerate:
            final_label = self._generate_label("angle", "a")
        elif label:
            self.used_labels["angle"].add(str(label))
            
        self.add_action(tool_label_angle, angle_data, final_label)
    
    # --- NEW METHOD FOR EDGES ---
    def add_edge_action(self, edge, label=None, auto_enumerate=False, color=(0, 200, 200, 255)):
        """High-level method to add an edge labeling task."""
        final_label = label
        if auto_enumerate:
            # Generates e1, e2, e3...
            final_label = self._generate_label("edge", "e")
        elif label:
            self.used_labels["edge"].add(str(label))
            
        # Register the tool function and its parameters
        self.add_action(tool_label_edge, edge, final_label, color)
    
    def add_region_action(self, face, label=None, color=None):
        """High-level method to highlight a specific region and optionally relabel it."""
        self.add_action(tool_highlight_region, face, label, color)


    # --- ADD NEW LINES ---
    def add_auxiliary_line_action(self, line_type, *args, **kwargs):
        """
        Generic method to add auxiliary lines.
        line_type: tool_draw_extended_edge, tool_draw_points_line, or tool_draw_axis_line
        """
        self.add_action(line_type, *args, **kwargs)

    def render(self):
            from PIL import Image, ImageDraw
            img = Image.new("RGBA", self.img_size, (255, 255, 255, 255))
            draw = ImageDraw.Draw(img)
            manager = LabelManager()

            # 1. Draw the base map (Faces)
            DrawGraph.DrawAllFaces(self.res_map, draw, manager)

            # 2. Separate actions (Added "line" category)
            region_actions = [a for a in self.actions if "region" in a[0].__name__.lower()]
            angle_actions = [a for a in self.actions if "angle" in a[0].__name__.lower()]
            edge_actions = [a for a in self.actions if "edge" in a[0].__name__.lower()]
            vertex_actions = [a for a in self.actions if "vertex" in a[0].__name__.lower()]
            # NEW: Catch any auxiliary line tool
            line_actions = [a for a in self.actions if "line" in a[0].__name__.lower() 
                            and "region" not in a[0].__name__.lower()] 

            # 3. EXECUTION ORDER:
            
            # Step A: Region highlights (Bottom layer)
            for func, args, kwargs in region_actions:
                func(draw, img, manager, *args, **kwargs)

            # Step B: Base map edges (Black lines)
            for edge in self.res_map.edges:
                p1 = DrawGraph.V2P(edge.tail.p)
                p2 = DrawGraph.V2P(edge.head.p)
                draw.line([p1, p2], fill=(0, 0, 0, 255), width=6)

            # Step C: Geometry annotations
            for func, args, kwargs in angle_actions + edge_actions + vertex_actions:
                func(draw, img, manager, *args, **kwargs)

            # Step D: Auxiliary Lines (Top layer - Blue lines)
            # We draw these last so they are never covered by black edges
            for func, args, kwargs in line_actions:
                func(draw, img, manager, *args, **kwargs)
                
            return img
    # ---ADD NEW ACTIONS OR CLEAR NEW CANVAS ---
    def undo_action(self):
        """Removes the last added annotation action."""
        if self.actions:
            last_action = self.actions.pop()
            print(f"Undid action: {last_action[0].__name__}")
        else:
            print("No actions to undo.")




# --- GEOMETRY HELPERS ---

def find_label_position(manager, target_px, target_py, text_w, text_h, frame_bounds, canvas_size=None):
    """
    Finds label position with three tiers of search:
    1. Tight Internal (Right next to point)
    2. Mid-Range Internal (Double distance, still inside frame)
    3. External (Outside frame with leader line)
    """
    f_min, f_max = frame_bounds
    c_w, c_h = canvas_size if canvas_size else (1000, 1000)
    
    SAFE_MARGIN = 2 
    COLLISION_PADDING = 2 # Reduced for tighter packing

    # --- 1. INTERNAL PLACEMENT (Tier 1: Tight & Tier 2: Mid-Range) ---
    # Tier 1 offsets (close) and Tier 2 offsets (roughly double distance)
    search_tiers = [
        [(15, -22), (15, 12), (-45, -22), (-45, 12)], # Tier 1: Tight
        [(35, -45), (35, 30), (-75, -45), (-75, 30)]  # Tier 2: Mid-Range
    ]

    for offsets in search_tiers:
        for ox, oy in offsets:
            tx, ty = target_px + ox, target_py + oy
            # Ensure it stays inside the frame bounds
            if f_min < tx < f_max - text_w and f_min < ty < f_max - text_h:
                if not manager.is_overlapping(tx + text_w/2, ty + text_h/2, text_w, text_h, padding=COLLISION_PADDING):
                    return (tx, ty), False, None

    # --- 2. EXTERNAL PLACEMENT (Tier 3: Outside Frame) ---
    # Only happens if both Tier 1 and Tier 2 are blocked
    dists = {'L': target_px - f_min, 'R': f_max - target_px, 'T': target_py - f_min, 'B': f_max - target_py}
    edge = min(dists, key=dists.get)
    
    for depth in [0, 30, 60]: # Gradually move further out if needed
        for s_off in [0, 35, -35, 70, -70]:
            if edge == 'L':
                tx = min(f_min - 25 - depth - text_w, target_px - 50 - text_w)
                ty = target_py - (text_h / 2) + s_off
            elif edge == 'R':
                tx = max(f_max + 15 + depth, target_px + 50)
                ty = target_py - (text_h / 2) + s_off
            elif edge == 'T':
                tx = target_px - (text_w / 2) + s_off
                ty = min(f_min - 25 - depth - text_h, target_py - 50 - text_h)
            else: # Bottom
                tx = target_px - (text_w / 2) + s_off
                ty = max(f_max + 15 + depth, target_py + 50)

            # Canvas boundary protection
            tx = max(SAFE_MARGIN, min(tx, c_w - text_w - SAFE_MARGIN))
            ty = max(SAFE_MARGIN, min(ty, c_h - text_h - SAFE_MARGIN))

            if not manager.is_overlapping(tx + text_w/2, ty + text_h/2, text_w, text_h, padding=COLLISION_PADDING):
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

def tool_draw_extended_edge(draw, img, manager, edge, color=(0, 0, 255, 255), width=8):
    """Extends an existing map edge to the frame boundaries."""
    p1 = DrawGraph.V2P(edge.tail.p)
    p2 = DrawGraph.V2P(edge.head.p)
    ext_start = get_extended_point(p2, p1)
    ext_end = get_extended_point(p1, p2)
    draw.line([ext_start, ext_end], fill=color, width=width)

def tool_draw_points_line(draw, img, manager, v1_p, v2_p, extend=False, color=(0, 0, 255, 255), width=8):
    """Draws a line between two arbitrary points (e.g., a diagonal)."""
    p1 = DrawGraph.V2P(v1_p)
    p2 = DrawGraph.V2P(v2_p)
    if extend:
        p1 = get_extended_point(p2, p1)
        p2 = get_extended_point(p1, p2)
    draw.line([p1, p2], fill=color, width=width)

def tool_draw_axis_line(draw, img, manager, vertex_p, direction='H', color=(0, 0, 255, 255), width=8):
    """Draws a horizontal or vertical reference line through a point."""
    f_min, f_max = 100, 900
    px, py = DrawGraph.V2P(vertex_p)
    if direction.upper() == 'H':
        draw.line([(f_min, py), (f_max, py)], fill=color, width=width)
    else:
        draw.line([(px, f_min), (px, f_max)], fill=color, width=width)

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


def tool_highlight_region(draw, img, manager, face, label=None, color=None):
    """
    Highlights a region and adds a sub-label (like '(1)') below the 
    original face letter (like 'A').
    """
    if not face.bounded: return
    
    # 1. Highlight the background
    fill_color = color if color else (147, 112, 219, 100) # Soft purple highlight
    points = DrawGraph.FaceVertex2P(face)
    draw.polygon(points, fill=fill_color)
    
    # 2. Get the center point for labeling
    lp, d = Graph.LetterPointFace(face)
    cx, cy = DrawGraph.V2P(lp)
    
    # Font settings
    font_main = DrawGraph.GetSystemFont(50 if d > 0.06 else 30)
    font_sub = DrawGraph.GetSystemFont(35 if d > 0.06 else 22)
    
    # 3. Draw the original face letter (A, B, C...) slightly higher
    draw.text((cx, cy - 15), face.letter, fill=(0,0,0,255), font=font_main, 
              anchor="mm", stroke_width=2, stroke_fill=(255,255,255,255))
    
    # 4. Draw the new label ( (1), (2)... ) slightly lower
    if label:
        draw.text((cx, cy + 25), str(label), fill=(200, 0, 0, 255), font=font_sub, 
                  anchor="mm", stroke_width=1, stroke_fill=(255,255,255,255))
    
    # Reserve the combined area in the Label Manager
    manager.reserve(cx, cy, 50, 80)

def draw_leader_with_arrow(draw, start_pos, end_pos, color):
    draw.line([start_pos, end_pos], fill=color, width=2)
    angle = math.atan2(end_pos[1] - start_pos[1], end_pos[0] - start_pos[0])
    arrow_len, spread = 20, 0.4
    p1 = (start_pos[0] + arrow_len * math.cos(angle + spread), start_pos[1] + arrow_len * math.sin(angle + spread))
    p2 = (start_pos[0] + arrow_len * math.cos(angle - spread), start_pos[1] + arrow_len * math.sin(angle - spread))
    draw.polygon([start_pos, p1, p2], fill=color)

def draw_labeled_feature(draw, img, manager, point, label_text, font, color, frame_bounds=(100, 900)):
    """Standard tool for labeling with improved leader line length."""
    px, py = DrawGraph.V2P(point)
    # Estimate text dimensions
    text_w, text_h = 45, 30 
    
    canvas_size = (img.width, img.height)
    pos_data, needs_leader, edge = find_label_position(
        manager, px, py, text_w, text_h, frame_bounds, canvas_size
    )
    
    if pos_data:
        tx, ty = pos_data
        if needs_leader:
            # 1. Get the specific point on the text box  start the line
            conn_p = get_connection_point(tx, ty, text_w, text_h, edge)
            
            # 2. Draw a line from the label connection point to the vertex
            # This ensures the line is as long as the distance requires
            draw.line([conn_p, (px, py)], fill=color, width=2)
            
            # 3. Draw the arrowhead specifically at the vertex (px, py)
            # This points exactly at the feature being labeled
            draw_arrow_head(draw, conn_p, (px, py), color)
            
        # Draw the label text
        draw.text((tx, ty), label_text, fill=color, font=font, 
                  stroke_width=2, stroke_fill=(255,255,255,255))
        
        # Reserve the area in the manager
        manager.reserve(tx + text_w/2, ty + text_h/2, text_w, text_h)

def draw_arrow_head(draw, start_pos, end_pos, color):
    """Draws an arrowhead at end_pos, pointing away from start_pos."""
    # Calculate angle of the line
    angle = math.atan2(end_pos[1] - start_pos[1], end_pos[0] - start_pos[0])
    
    arrow_len = 15
    spread = 0.5 # Radians
    
    # Calculate the two 'fins' of the arrowhead
    p1 = (end_pos[0] - arrow_len * math.cos(angle - spread), 
          end_pos[1] - arrow_len * math.sin(angle - spread))
    p2 = (end_pos[0] - arrow_len * math.cos(angle + spread), 
          end_pos[1] - arrow_len * math.sin(angle + spread))
    
    draw.polygon([end_pos, p1, p2], fill=color)

def reset_label_session():
    global USED_LABELS
    USED_LABELS['vertex'].clear()
    USED_LABELS['angle'].clear()
    USED_LABELS['edges'].clear()

def tool_label_vertex(draw, img, manager, vertex, label_text=None, color=(0, 0, 255, 255)):
    # 1. Draw the Dot (the space is already reserved in render())
    px, py = DrawGraph.V2P(vertex.p)
    draw.ellipse([px-10, py-10, px+10, py+10], fill=(255, 0, 0, 255))
    
    # 2. Draw the Text (find_label_position will now avoid the dot AND the angle text)
    if label_text is not None:
        font_labels = DrawGraph.GetSystemFont(35)
        draw_labeled_feature(draw, img, manager, vertex.p, str(label_text), font_labels, color)

def tool_label_angle(draw, img, manager, angle_data, label_text=None, color=(0, 128, 0, 255)):
    """
    Labels the angle in the opposite (exterior) position. 
    If crowded, uses an arrow pointing toward the arc boundary.
    """
    arc_radius = 40
    text_w, text_h = 30, 20
    
    # 1. Draw the interior arc
    tool_draw_interior_arc(draw, img, manager, angle_data, radius=arc_radius, color=color)
    
    if label_text:
        v_p = angle_data.p
        px, py = DrawGraph.V2P(v_p)
        
        # Calculate the point on the ARC (interior)
        # This is where the arrow tip will land
        arc_target_p = calculate_angle_center_point(angle_data, distance=arc_radius)
        tpx, tpy = DrawGraph.V2P(arc_target_p)
        
        # Calculate the base direction vector for the OUTSIDE (Exterior)
        # We find the vector from arc_target to vertex, then extend it out
        inner_p = calculate_angle_center_point(angle_data, distance=45)
        dx = v_p.x - inner_p.x
        dy = v_p.y - inner_p.y
        
        final_lx, final_ly = None, None
        needs_arrow = False
        
        # Search Rings (1.0 is close, 2.0+ triggers arrow)
        search_rings = [(1.1, False), (1.9, True), (2.7, True)]
        
        for dist_mult, use_arrow in search_rings:
            for offset_angle in [0, 0.4, -0.4, 0.8, -0.8]:
                cos_a, sin_a = math.cos(offset_angle), math.sin(offset_angle)
                rx = (dx * cos_a - dy * sin_a) * dist_mult
                ry = (dx * sin_a + dy * cos_a) * dist_mult
                
                lx, ly = DrawGraph.V2P(Graph.Vector(v_p.x + rx, v_p.y + ry))
                
                # Check for overlap with Dots, Vertex Text, or other Angle Text
                if not manager.is_overlapping(lx, ly, text_w, text_h, padding=2):
                    final_lx, final_ly = lx, ly
                    needs_arrow = use_arrow
            if final_lx: break

        # Fallback placement
        if final_lx is None:
            final_lx, final_ly = DrawGraph.V2P(Graph.Vector(v_p.x + dx, v_p.y + dy))

        # 2. Draw the connection
        if needs_arrow:
            # We draw the line from the external text to the internal arc point
            # Note: This line will pass very close to or through the vertex
            draw.line([(final_lx, final_ly), (tpx, tpy)], fill=color, width=1)
            draw_arrow_head(draw, (final_lx, final_ly), (tpx, tpy), color)

        # 3. Final Text Render
        font = DrawGraph.GetSystemFont(30)
        draw.text((final_lx, final_ly), str(label_text), fill=color, font=font, 
                  anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))
        
        manager.reserve(final_lx, final_ly, text_w, text_h, padding=2)


def calculate_angle_center_point(angle_data, distance=60):
    """
    Finds a point along the angle bisector inside the face.
    angle_data: namedtuple(p, parent_face)
    """
    v_p = angle_data.p # This is the Vector/Point
    face = angle_data.parent_face
    
    # Manually find edges to avoid the 'int' return error from ArcsAtVertexInFace
    e_in = next((e for e in face.edges if e.head.p == v_p), None)
    e_out = next((e for e in face.edges if e.tail.p == v_p), None)
    
    if not e_in or not e_out:
        # Fallback: if edges aren't found, return original point
        return v_p
    
    # 2. Get directions (in radians)
    # Direction of the edge leaving V
    dir_out = e_out.direction 
    # Direction of the edge coming into V (reverse it to get direction away from V)
    dir_in = e_in.reverse.direction 
    
    # 3. Calculate the interior sweep
    diff = dir_out - dir_in
    while diff < 0:
        diff += 2 * np.pi
    while diff >= 2 * np.pi:
        diff -= 2 * np.pi
    
    # The bisector direction is the start direction + half the interior sweep
    bisector_dir = dir_in + (diff / 2)
    
    # 4. Create the offset vector (Scaling distance to math space)
    # Assuming 800 is your coordinate scale factor
    offset_x = math.cos(bisector_dir) * (distance / 800)
    offset_y = math.sin(bisector_dir) * (distance / 800)
    
    return Graph.Vector(v_p.x + offset_x, v_p.y + offset_y)


USED_ANGLE_LABELS = set()

def tool_draw_interior_arc(draw, img, manager, angle_data, radius=40, color=(0, 150, 0, 255)):
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


import math
def tool_label_edge(draw, img, manager, edge, label_text=None, color=(200, 0, 255, 255)):
    """
    1. Highlights edge with a 'Bright Purple' glow.
    2. If label_text is provided, places it at the midpoint.
    3. Uses a two-sided collision check to prevent overlapping labels.
    """
    p1 = DrawGraph.V2P(edge.tail.p)
    p2 = DrawGraph.V2P(edge.head.p)

    # 1. BRIGHT PURPLE HIGHLIGHT
    # White background stroke for contrast
    draw.line([p1, p2], fill=(255, 255, 255, 255), width=14) 
    # Core Purple line
    draw.line([p1, p2], fill=color, width=10) 

# 2. OPTIONAL LABELING
    if label_text:
        mid_x = (p1[0] + p2[0]) / 2
        mid_y = (p1[1] + p2[1]) / 2
        
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = math.sqrt(dx**2 + dy**2)
        if length == 0: return
        
        # Unit normal vector
        nx, ny = -dy / length, dx / length
        
        text_w, text_h = 32, 22
        font = DrawGraph.GetSystemFont(28)
        
        # IMPROVED: Flip Logic based on Odd/Even parity
        # This prevents adjacent short edges (like 5 and 6) from crowding the same side.
        try:
            val = int(label_text)
            if val % 2 == 0:
                # Even numbers prefer Side B (Inside)
                search_offsets = [-30, 30, -55, 55]
            else:
                # Odd numbers prefer Side A (Outside)
                search_offsets = [30, -30, 55, -55]
        except ValueError:
            search_offsets = [30, -30, 50, -50]

        final_tx, final_ty = None, None
        
        # Check positions with increased padding (5 instead of 2) for better spacing
        for dist in search_offsets:
            tx, ty = mid_x + nx * dist, mid_y + ny * dist
            if not manager.is_overlapping(tx, ty, text_w, text_h, padding=5):
                final_tx, final_ty = tx, ty
                break
        
        # Fallback
        if final_tx is None:
            final_tx, final_ty = mid_x + nx * 60, mid_y + ny * 60

        # Draw the text with white stroke for maximum pop
        draw.text((final_tx, final_ty), str(label_text), fill=color, font=font, 
                  anchor="mm", stroke_width=3, stroke_fill=(255, 255, 255, 255))
        
        manager.reserve(final_tx, final_ty, text_w, text_h, padding=5)
   

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


import random

def main():
    maxX, maxY = 1.0, 1.0
    seed = random.randint(0, 9999)
    Graph.initialize()
    res_map = BuildRandomMap.BuildRandomMap(8, maxX, maxY, seed)
    
    img_size = (int(200 + 800 * maxX), int(200 + 800 * maxY))
    purple = (200, 0, 255, 255)

    bounded_faces = [f for f in res_map.faces if f.bounded]
    if not bounded_faces: return
    target_face = random.choice(bounded_faces)

    # --- IMAGE 1: edge_highlight.png ---
    # Pure highlight, no text
    session_h = AnnotationSession(res_map, img_size)
    session_h.add_edge_action(target_face.edges[0], label=None, color=purple)
    
    session_h.render().save("edge_highlight.png")
    print("Saved: edge_highlight.png")

# --- IMAGE 2: edge_labeled.png ---
    session_l = AnnotationSession(res_map, img_size)

    processed_true_edges = set()
    edge_counter = 1
    
    for edge in target_face.edges:
        t_edge = getattr(edge, 'trueEdge', edge) 
        t_id = id(t_edge)
        
        if t_id not in processed_true_edges:
            session_l.add_edge_action(edge, label=str(edge_counter), color=purple)
            processed_true_edges.add(t_id)
            edge_counter += 1
        else:
            session_l.add_edge_action(edge, label=None, color=purple)
    
    session_l.render().save("edge_labeled.png")
    print("Saved: edge_labeled.png")

if __name__ == "__main__":
    main()
