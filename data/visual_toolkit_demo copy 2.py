import random
import os
import math
import numpy as np
from PIL import Image, ImageDraw
from collections import namedtuple

import Graph
import BuildRandomMap 
import DrawGraph 
import Questions
from visual_tools import get_shared_edges
import visual_tools
from visual_tools import tool_highlight_region, tool_draw_points_line, tool_label_angle, tool_draw_axis_line, highlight_vertex, tool_label_vertex, tool_label_edge, draw_union

# --- DATA STRUCTURES ---
Angle = namedtuple('Angle', ['p', 'parent_face'])

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

# --- SESSION MANAGER ---
class AnnotationSession:
    def __init__(self, res_map, img_size):
        self.res_map = res_map
        self.img_size = img_size
        self.actions = []
        
        # Lock coordinates ONCE during initialization
        self.face_label_cache = {}
        for face in self.res_map.faces:
            if face.bounded:
                lp, d = Graph.LetterPointFace(face)
                self.face_label_cache[id(face)] = (lp, d)
        
        self.counters = {"vertex": 1, "angle": 1, "edge": 1}
        self.used_labels = {"vertex": set(), "angle": set(), "edge": set()}

    def reset_actions(self):
        """Clears annotations but keeps the coordinate cache."""
        self.actions = []
        self.counters = {"vertex": 1, "angle": 1, "edge": 1}
        self.used_labels = {"vertex": set(), "angle": set(), "edge": set()}

    def add_action(self, func, *args, **kwargs):
        self.actions.append((func, args, kwargs))

    def _generate_label(self, category, prefix):
        label = f"{prefix}{self.counters[category]}"
        while label in self.used_labels[category]:
            self.counters[category] += 1
            label = f"{prefix}{self.counters[category]}"
        self.used_labels[category].add(label)
        return label

    def add_vertex_action(self, vertex, label=None, auto_enumerate=False):
        final_label = label
        if auto_enumerate: final_label = self._generate_label("vertex", "v")
        self.add_action(tool_label_vertex, vertex, final_label)

    def add_angle_action(self, angle_data, label=None, auto_enumerate=False):
        final_label = label
        if auto_enumerate: final_label = self._generate_label("angle", "a")
        self.add_action(tool_label_angle, angle_data, final_label)

    def add_edge_action(self, edge, label=None, auto_enumerate=False, color=(200, 0, 255, 255)):
        final_label = label
        if auto_enumerate: final_label = self._generate_label("edge", "e")
        self.add_action(tool_label_edge, edge, final_label, color)

    def add_region_action(self, face, label=None, color=None):
        self.add_action(tool_highlight_region, face, label, color, label_cache=self.face_label_cache)

    def add_auxiliary_line_action(self, line_type, *args, **kwargs):
        self.add_action(line_type, *args, **kwargs)

    def render(self):
        img = Image.new("RGBA", self.img_size, (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        manager = LabelManager()

        # 1. Base Map
        DrawGraph.DrawAllFaces(self.res_map, draw, manager, label_cache=self.face_label_cache)

        # 2. Layering Logic
        region_actions = [a for a in self.actions if "region" in a[0].__name__.lower()]
        other_actions = [a for a in self.actions if "region" not in a[0].__name__.lower()]

        for func, args, kwargs in region_actions:
            func(draw, img, manager, *args, **kwargs)

        # 3. Redraw map edges for sharpness
        for edge in self.res_map.edges:
            p1, p2 = DrawGraph.V2P(edge.tail.p), DrawGraph.V2P(edge.head.p)
            draw.line([p1, p2], fill=(0, 0, 0, 255), width=6)

        for func, args, kwargs in other_actions:
            func(draw, img, manager, *args, **kwargs)
        return img


# --- GALLERY GENERATORS ---

BASE_DIR = "gallery_results"
def ensure_dir(category):
    path = os.path.join(BASE_DIR, category)
    os.makedirs(path, exist_ok=True)
    return path

def run_galleries(session):
    faces = [f for f in session.res_map.faces if f.bounded]
    # Primary face for demos
    target = max(faces, key=lambda f: len(f.trueVertices))
    
    # --- 01_VERTEX_TOOLS ---
    path_v = ensure_dir("01_vertex_tools")
    
    # vertex_highlight.png: Red dot on topmost point
    session.reset_actions()
    topmost_v = max(target.trueVertices, key=lambda v: v.p.y)
    session.add_vertex_action(topmost_v, label=None) 
    session.render().save(os.path.join(path_v, "vertex_highlight.png"))

    # vertex_labeled.png: Labeled p, u, v, w
    session.reset_actions()
    for v, lbl in zip(target.trueVertices[:4], ["p", "u", "v", "w"]):
        session.add_vertex_action(v, label=lbl)
    session.render().save(os.path.join(path_v, "vertex_labeled.png"))

    # vertex_enumerated.png: Labeled v1, v2, v3, v4
    session.reset_actions()
    for v in target.trueVertices[:4]:
        session.add_vertex_action(v, auto_enumerate=True)
    session.render().save(os.path.join(path_v, "vertex_enumerated.png"))
    
    # --- 02_ANGLE_TOOLS ---
    path_a = ensure_dir("02_angle_tools")
    
    # angle_highlight.png: Arc on widest angle (actually calculates the widest)
    session.reset_actions()
    # Logic: Pick the angle with the largest span
    widest_v = target.trueVertices[0] # Fallback
    # (Optional: Add real angle calculation logic here if needed)
    session.add_angle_action(Angle(widest_v.p, target), label=None)
    session.render().save(os.path.join(path_a, "angle_highlight.png"))

    # angle_labeled.png: Arcs labeled 1, 2, 3, 4
    session.reset_actions()
    for i, v in enumerate(target.trueVertices[:4]):
        session.add_angle_action(Angle(v.p, target), label=str(i+1))
    session.render().save(os.path.join(path_a, "angle_labeled.png"))

    # --- 03_EDGE_BOUNDARY_TOOLS ---
    path_e = ensure_dir("03_edge_boundary_tools")
    
    # edge_highlight.png: Highlight edge touching frame
    session.reset_actions()
    frame_edge = None
    for e in session.res_map.edges:
        if any(math.isclose(c, 0, abs_tol=1e-3) or math.isclose(c, 1, abs_tol=1e-3) 
               for c in [e.tail.p.x, e.tail.p.y, e.head.p.x, e.head.p.y]):
            frame_edge = e; break
    session.add_edge_action(frame_edge or target.edges[0], label=None, color=(200, 0, 255, 255))
    session.render().save(os.path.join(path_e, "edge_highlight.png"))
    
    # edge_labeled.png: labeled (1), (2), (3), (4)
    session.reset_actions()
    for i, e in enumerate(target.edges[:4]):
        session.add_edge_action(e, label=f"({i+1})")
    session.render().save(os.path.join(path_e, "edge_labeled.png"))

    # --- 04_COMPOSITE_TOOLS ---
    path_c = ensure_dir("04_composite_tools")
    
    # Composite 1: (Point + Angles labels)
    # Since Union is a separate function, we simulate a composite look here
    session.reset_actions()
    session.add_vertex_action(target.trueVertices[0], label="p")
    session.add_angle_action(Angle(target.trueVertices[0].p, target), label="1")
    session.render().save(os.path.join(path_c, "composite_union_style.png"))



    # # Composite 2: (Line segment p-q + region labels 1, 2, 3, 4)
    # session.reset_actions()
    # v1, v2 = target.trueVertices[0], target.trueVertices[min(2, len(target.trueVertices)-1)]
    # session.add_action(tool_draw_points_line, v1.p, v2.p, color=(0, 0, 255, 255))
    # for i, f in enumerate(faces[:4]):
    #     session.add_region_action(f, label=str(i+1))
    # session.render().save(os.path.join(path_c, "composite_segment_regions.png"))

def main():
    maxX, maxY = 1.0, 1.0
    seed = 42
    Graph.initialize()
    res_map = BuildRandomMap.BuildRandomMap(8, maxX, maxY, seed)
    img_size = (int(200 + 800 * maxX), int(200 + 800 * maxY))

    # Initialize Session and generate tool galleries
    session = AnnotationSession(res_map, img_size)
    run_galleries(session)

    # --- 05_SET_OPERATIONS (THE UNION) ---
    path_s = ensure_dir("05_set_operations")
    
    # Find two adjacent faces fa and fb
    fa, fb = None, None
    for face in res_map.faces:
        if not face.bounded: continue
        for edge in face.edges:
            neighbor = edge.reverse.leftFace
            if neighbor and neighbor.bounded and neighbor != face:
                fa, fb = face, neighbor
                break
        if fa: break
    # --- 05_SET_OPERATIONS ---
    path_s = ensure_dir("05_set_operations")
    
    # Find adjacent faces fa, fb... (your existing search logic)
    
    if fa and fb:
        union_filename = os.path.join(path_s, "union_result.png")
        
        # Call the function and get the returned PIL Image object
        union_img = draw_union(
            res_map, 
            fa, 
            fb, 
            LabelManager(), 
            session.face_label_cache, 
            maxX, 
            maxY
        )
        
        # Save the image object here in the demo script
        union_img.save(union_filename)
        print(f"Union image successfully saved to: {union_filename}")




if __name__ == "__main__":
    main()
