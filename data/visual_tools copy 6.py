import numpy as np
import random
import os
import math
from PIL import Image, ImageDraw
from collections import namedtuple
import RandomQuestions 
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
            self.actions = []
            self.temp_selection = None  # To store a Vertex or Point object
            
            # --- NEW: Lock the random coordinates here ---
            self.face_label_cache = {}
            for face in self.res_map.faces:
                if face.bounded:
                    # Calculate once and store the result
                    lp, d = Graph.LetterPointFace(face)
                    self.face_label_cache[id(face)] = (lp, d)
            
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
            """
            High-level method to highlight a specific region. 
            Passes the session's face_label_cache directly to the tool.
            """
            self.add_action(
                tool_highlight_region, 
                face, 
                label, 
                color, 
                label_cache=self.face_label_cache  # Bind the cache here
            )


    # --- ADD NEW LINES ---
    def add_auxiliary_line_action(self, line_type, *args, **kwargs):
        """
        Generic method to add auxiliary lines.
        line_type: tool_draw_extended_edge, tool_draw_points_line, or tool_draw_axis_line
        """
        self.add_action(line_type, *args, **kwargs)
    def render(self):
        from PIL import Image, ImageDraw
        
        # --- 1. PRE-PASS: Identify Union State ---
        unioned_faces = set()
        shared_edge_ids = set()
        union_actions = []
        
        for action in self.actions:
            func, args, kwargs = action
            if func.__name__ == "draw_union":
                fa, fb = args[0], args[1]
                unioned_faces.update([fa, fb])
                shared_edge_ids.update(get_shared_edges(fa, fb))
                union_actions.append(action)

        # --- 2. BASE LAYER: Original Map ---
        # Draw the map as it was originally
        base_img = Image.new("RGBA", self.img_size, (255, 255, 255, 255))
        base_draw = ImageDraw.Draw(base_img)
        
        for face in self.res_map.faces:
            if not face.bounded: continue
            base_draw.polygon(DrawGraph.FaceVertex2P(face), fill=DrawGraph.colors[face.color])

        # --- 3. ACTION LAYER: Union & Highlights ---
        # Draw the Union first (via the function)
        for func, args, kwargs in union_actions:
            base_img = func(base_img, self.res_map, *args, shared_edge_ids=shared_edge_ids)

        # Draw individual highlights ONLY if the face isn't in a union
        temp_manager = LabelManager()
        for func, args, kwargs in self.actions:
            if "highlight" in func.__name__.lower():
                target_face = args[0]
                if target_face not in unioned_faces:
                    func(base_draw, base_img, temp_manager, *args, **kwargs)

        # --- 4. LINE LAYER: Black Edges ---
        # Redraw black edges last so they sit on top of fills, skipping shared ones
        for edge in self.res_map.edges:
            if id(edge) in shared_edge_ids: continue
            p1, p2 = DrawGraph.V2P(edge.tail.p), DrawGraph.V2P(edge.head.p)
            base_draw.line([p1, p2], fill=(0, 0, 0, 255), width=6)

        # --- 5. OVERLAY LAYER: Labels & Icons ---
        overlay_img = Image.new("RGBA", self.img_size, (255, 255, 255, 0))
        overlay_draw = ImageDraw.Draw(overlay_img)
        manager = LabelManager()
        font_bold = DrawGraph.GetSystemFont(80)
        
        # Draw labels (A, B, C, U)
        for face in self.res_map.faces:
            if not face.bounded: continue
            lp, d = self.face_label_cache.get(id(face), (None, 0))
            if not lp: continue
            coords = DrawGraph.V2P(lp)
            
            if face in unioned_faces:
                # Place 'U' only once at the center of the first face in the union list
                if face == list(unioned_faces)[0]:
                    overlay_draw.text(coords, "U", fill=(0, 0, 0, 255), font=font_bold, anchor="mm",
                                    stroke_width=2, stroke_fill=(255, 255, 255, 255))
            else:
                f_style = font_bold if d > 0.06 else DrawGraph.GetSystemFont(45)
                overlay_draw.text(coords, face.letter, fill=(0, 0, 0, 255), font=f_style, anchor="mm")

        # Draw other tools (Points, Angles, etc.)
        for func, args, kwargs in self.actions:
            if func.__name__ not in ["draw_union", "tool_highlight_region"]:
                func(overlay_draw, overlay_img, manager, *args, **kwargs)

        #Draw Temporary Points
        if self.temp_selection:
            # Call your drawing function to put a highlight on the image
            # e.g., draw_temp_highlight(self.temp_selection)
            pass

        # Composite everything
        base_img.paste(overlay_img, (0, 0), overlay_img)
        return base_img
    # ---ADD NEW ACTIONS OR CLEAR NEW CANVAS ---
    def undo_action(self):
        """Removes the last added annotation action."""
        if self.actions:
            last_action = self.actions.pop()
            print(f"Undid action: {last_action[0].__name__}")
        else:
            print("No actions to undo.")
    def clear(self):
        """Resets the canvas actions and counters for a fresh image."""
        self.actions = []
        self.counters = {"vertex": 1, "angle": 1, "edge": 1}
        self.used_labels = {"vertex": set(), "angle": set(), "edge": set()}
        # Note: We do NOT clear face_label_cache. That stays forever.




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
    
    # Increased halo size to +5 for "PPT-level" visibility
    draw.ellipse(
        [px - (r + 2), py - (r + 2), px + (r + 2), py + (r + 2)], 
        fill=(255, 255, 255, 255)
    )
    
    # Original Golden Dot
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


def tool_highlight_region(draw, img, manager, face, label=None, color=None, label_cache=None):
    """
    Highlights a region and ensures text labels perfectly align with the base map.
    """
    if not face.bounded: return
    
    # 1. Retrieve the LOCKED coordinates and d-value (radius)
    face_id = id(face)
    if label_cache and face_id in label_cache:
        lp, d = label_cache[face_id]
    else:
        # Emergency fallback (should be avoided by using the cache)
        lp, d = Graph.LetterPointFace(face)
        
    cx, cy = DrawGraph.V2P(lp)
    
    # 2. Draw the highlight polygon
    fill_color = color if color else (147, 112, 219, 100) # Soft purple
    draw.polygon(DrawGraph.FaceVertex2P(face), fill=fill_color)
    
    # 3. Synchronized Font Logic
    # We use exactly 80 and 45 to match DrawGraph.DrawAllFaces
    is_large = d > 0.06
    font_main = DrawGraph.GetSystemFont(80 if is_large else 45)
    font_sub = DrawGraph.GetSystemFont(35 if is_large else 22)
    
    # 4. Redraw the main letter (A, B, C...)
    # We redraw it with a white stroke to ensure it remains legible over the highlight
    draw.text((cx, cy), face.letter, fill=(0, 0, 0, 255), font=font_main, 
              anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))
    
    # 5. Draw the sub-label ( (1), (2)... )
    if label:
        # Adjust the vertical offset based on font size
        vertical_offset = 45 if is_large else 28
        draw.text((cx, cy + vertical_offset), str(label), fill=(200, 0, 0, 255), 
                  font=font_sub, anchor="mm", stroke_width=1, 
                  stroke_fill=(255, 255, 255, 255))
    
    # Update manager to prevent other labels from crowding this region
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
    # 1. Draw a significantly larger white "Base"
    px, py = DrawGraph.V2P(vertex.p)
    
    # Large white halo (Radius 12)
    draw.ellipse([px-12, py-12, px+12, py+12], fill=(255, 255, 255, 255))
    
    # # Core Red Dot (Radius 10)
    draw.ellipse([px-10, py-10, px+10, py+10], fill=(255, 0, 0, 255))
    
    # 2. Draw the Text
    if label_text is not None:
        font_labels = DrawGraph.GetSystemFont(35)
        # Note: If your draw_labeled_feature doesn't have white stroke, 
        # you might need to check that function too!
        draw_labeled_feature(draw, img, manager, vertex.p, str(label_text), font_labels, color)

def tool_label_angle(draw, img, manager, angle_data, label_text=None, color=(0, 128, 0, 255)):
    """
    Labels the angle in the opposite position by reversing the direction vector.
    Now handles angle_data as (face, vertex) tuple.
    """
    # --- UNPACK TUPLE ---
    # face is needed for edge calculations inside helper functions
    # vertex is needed for the origin point
    face, vertex = angle_data
    
    arc_radius = 40
    text_w, text_h = 30, 20
    
    # 1. Draw the interior arc
    # Ensure tool_draw_interior_arc is also updated to unpack angle_data!
    tool_draw_interior_arc(draw, img, manager, angle_data, radius=arc_radius, color=color)
    
    if label_text:
        # Access the vertex property .p for math coordinates
        v_p = vertex.p
        px, py = DrawGraph.V2P(v_p)
        
        # Calculate the point on the ARC
        # Ensure this helper function also accepts/unpacks the (face, vertex) tuple
        arc_target_p = calculate_angle_center_point(angle_data, distance=arc_radius)
        tpx, tpy = DrawGraph.V2P(arc_target_p)
        
        # --- Reverse the direction vector ---
        inner_p = calculate_angle_center_point(angle_data, distance=45)
        dx = inner_p.x - v_p.x
        dy = inner_p.y - v_p.y
        
        final_lx, final_ly = None, None
        needs_arrow = False
        
        # Search Rings for label placement
        search_rings = [(1.1, False), (1.9, True), (2.7, True)]
        
        for dist_mult, use_arrow in search_rings:
            for offset_angle in [0, 0.4, -0.4, 0.8, -0.8]:
                cos_a, sin_a = math.cos(offset_angle), math.sin(offset_angle)
                rx = (dx * cos_a - dy * sin_a) * dist_mult
                ry = (dx * sin_a + dy * cos_a) * dist_mult
                
                # Calculate candidate label position in math space and convert to pixels
                lx, ly = DrawGraph.V2P(Graph.Vector(v_p.x + rx, v_p.y + ry))
                
                if not manager.is_overlapping(lx, ly, text_w, text_h, padding=2):
                    final_lx, final_ly = lx, ly
                    needs_arrow = use_arrow
                    break
            if final_lx: break

        # Fallback if no non-overlapping space found
        if final_lx is None:
            final_lx, final_ly = DrawGraph.V2P(Graph.Vector(v_p.x + dx, v_p.y + dy))

        # 2. Draw the connection (leader line)
        if needs_arrow:
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
    # --- FIX: Unpack the tuple ---
    face, vertex = angle_data
    v_p = vertex.p 
    
    # Manually find edges
    e_in = next((e for e in face.edges if e.head.p == v_p), None)
    e_out = next((e for e in face.edges if e.tail.p == v_p), None)
    
    if not e_in or not e_out:
        return v_p
    
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

def tool_draw_interior_arc(draw, img, manager, angle_data, radius=40, color=(255, 0, 0, 255)):
    # --- UNPACK THE TUPLE ---
    # Since we passed (target_f, target_v) from app.py
    face, vertex = angle_data
    
    # Use the vertex's math position .p
    p_center_math = vertex.p 
    p_center_pixel = DrawGraph.V2P(p_center_math)
    
    e_in = next((e for e in face.edges if e.head.p == p_center_math), None)
    e_out = next((e for e in face.edges if e.tail.p == p_center_math), None)
    
    if not e_in or not e_out:
        return

    cx, cy = p_center_pixel
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

    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]

    # 1. THE HALO: Draw a thicker white arc first
    # width=9 provides roughly a 2-pixel border around a width=5 line
    draw.arc(bbox, start=start, end=end, fill=(255, 255, 255, 255), width=7)

    # 2. THE CORE: Draw the primary colored arc
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
   

def draw_union(img, res_map, fa, fb, shared_edge_ids):
    """
    Called during the render loop to apply the union visual effect.
    """
    draw = ImageDraw.Draw(img)
    
    # 1. Soft Purple Fill (Low alpha to prevent 'intense' overlap)
    union_fill = (147, 112, 219, 100) 
    
    for face in [fa, fb]:
        draw.polygon(DrawGraph.FaceVertex2P(face), fill=union_fill)

    # 2. Erase the internal boundary
    # We draw over the shared edges with the SAME color as the fill
    # This makes the two faces look like one single region
    for edge in res_map.edges:
        if id(edge) in shared_edge_ids:
            p1 = DrawGraph.V2P(edge.tail.p)
            p2 = DrawGraph.V2P(edge.head.p)
            # Width 10 ensures we fully cover the underlying 6px black line
            draw.line([p1, p2], fill=union_fill, width=10)

    # 3. The Label is handled in the overlay pass of render() 
    # to ensure it stays on top of everything.
    return img

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
