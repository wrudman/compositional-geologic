import random
import os
import math
import numpy as np
from PIL import Image, ImageDraw
from collections import namedtuple
from VisualProblem import VisualProblem
import RandomQuestions

import Graph
import BuildRandomMap 
import DrawGraph 
import Questions
from visual_tools import get_shared_edges
import importlib
import visual_tools
from visual_tools import tool_highlight_region, tool_draw_points_line, tool_label_angle, tool_draw_axis_line, tool_label_edge, draw_union, tool_draw_interior_arc, draw_labeled_feature, tool_label_vertex, highlight_vertex
importlib.reload(visual_tools)
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
# --- SESSION MANAGER ---
class AnnotationSession:
    def __init__(self, res_map, img_size):
        self.res_map = res_map
        self.img_size = img_size
        self.actions = []
        
        self.face_label_cache = {}
        for face in self.res_map.faces:
            if face.bounded:
                lp, d = Graph.LetterPointFace(face)
                self.face_label_cache[id(face)] = (lp, d)
        
        self.counters = {"vertex": 1, "angle": 1, "edge": 1}
        self.used_labels = {"vertex": set(), "angle": set(), "edge": set()}

    def reset_actions(self):
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
        # FORCE: Use the local tool_label_vertex defined in this script
        self.add_action(tool_label_vertex, vertex, final_label)

    def add_angle_action(self, angle_data, label=None, auto_enumerate=False):
        final_label = label
        if auto_enumerate: final_label = self._generate_label("angle", "a")
        self.add_action(tool_label_angle, angle_data, final_label)

    def add_edge_action(self, edge, label=None, auto_enumerate=False, color=(200, 0, 255, 255)):
        final_label = label
        if auto_enumerate: final_label = self._generate_label("edge", "e")
        # FORCE: Use the local tool_label_edge if you re-defined it here
        self.add_action(tool_label_edge, edge, final_label, color)

    def add_region_action(self, face, label=None, color=None):
        self.add_action(tool_highlight_region, face, label, color, label_cache=self.face_label_cache)

    def render(self):
        img = Image.new("RGBA", self.img_size, (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        manager = LabelManager()

        DrawGraph.DrawAllFaces(self.res_map, draw, manager, label_cache=self.face_label_cache)

        region_actions = [a for a in self.actions if "region" in a[0].__name__.lower()]
        other_actions = [a for a in self.actions if "region" not in a[0].__name__.lower()]

        for func, args, kwargs in region_actions:
            func(draw, img, manager, *args, **kwargs)

        for edge in self.res_map.edges:
            p1, p2 = DrawGraph.V2P(edge.tail.p), DrawGraph.V2P(edge.head.p)
            draw.line([p1, p2], fill=(0, 0, 0, 255), width=6)

        for func, args, kwargs in other_actions:
            func(draw, img, manager, *args, **kwargs)
        return img
# class AnnotationSession:
#     def __init__(self, res_map, img_size):
#         self.res_map = res_map
#         self.img_size = img_size
#         self.actions = []
        
#         # Lock coordinates ONCE during initialization
#         self.face_label_cache = {}
#         for face in self.res_map.faces:
#             if face.bounded:
#                 lp, d = Graph.LetterPointFace(face)
#                 self.face_label_cache[id(face)] = (lp, d)
        
#         self.counters = {"vertex": 1, "angle": 1, "edge": 1}
#         self.used_labels = {"vertex": set(), "angle": set(), "edge": set()}

#     def reset_actions(self):
#         """Clears annotations but keeps the coordinate cache."""
#         self.actions = []
#         self.counters = {"vertex": 1, "angle": 1, "edge": 1}
#         self.used_labels = {"vertex": set(), "angle": set(), "edge": set()}

#     def add_action(self, func, *args, **kwargs):
#         self.actions.append((func, args, kwargs))

#     def _generate_label(self, category, prefix):
#         label = f"{prefix}{self.counters[category]}"
#         while label in self.used_labels[category]:
#             self.counters[category] += 1
#             label = f"{prefix}{self.counters[category]}"
#         self.used_labels[category].add(label)
#         return label

#     def add_vertex_action(self, vertex, label=None, auto_enumerate=False):
#         final_label = label
#         if auto_enumerate: final_label = self._generate_label("vertex", "v")
#         self.add_action(tool_label_vertex, vertex, final_label)

#     def add_angle_action(self, angle_data, label=None, auto_enumerate=False):
#         final_label = label
#         if auto_enumerate: final_label = self._generate_label("angle", "a")
#         self.add_action(tool_label_angle, angle_data, final_label)

#     def add_edge_action(self, edge, label=None, auto_enumerate=False, color=(200, 0, 255, 255)):
#         final_label = label
#         if auto_enumerate: final_label = self._generate_label("edge", "e")
#         self.add_action(tool_label_edge, edge, final_label, color)

#     def add_region_action(self, face, label=None, color=None):
#         self.add_action(tool_highlight_region, face, label, color, label_cache=self.face_label_cache)

#     def add_auxiliary_line_action(self, line_type, *args, **kwargs):
#         self.add_action(line_type, *args, **kwargs)

#     def render(self):
#         img = Image.new("RGBA", self.img_size, (255, 255, 255, 255))
#         draw = ImageDraw.Draw(img)
#         manager = LabelManager()

#         # 1. Base Map
#         DrawGraph.DrawAllFaces(self.res_map, draw, manager, label_cache=self.face_label_cache)

#         # 2. Layering Logic
#         region_actions = [a for a in self.actions if "region" in a[0].__name__.lower()]
#         other_actions = [a for a in self.actions if "region" not in a[0].__name__.lower()]

#         for func, args, kwargs in region_actions:
#             func(draw, img, manager, *args, **kwargs)

#         # 3. Redraw map edges for sharpness
#         for edge in self.res_map.edges:
#             p1, p2 = DrawGraph.V2P(edge.tail.p), DrawGraph.V2P(edge.head.p)
#             draw.line([p1, p2], fill=(0, 0, 0, 255), width=6)

#         for func, args, kwargs in other_actions:
#             func(draw, img, manager, *args, **kwargs)
#         return img


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


import random
import os
import math


def render_step_by_step_hints(problem, session):
    trace = problem.expert_visual_trace # e.g., ["highlight_fa", "highlight_fb", "union"]
    
    for i, step in enumerate(trace):
        # 1. Dispatch the string to the actual function
        if step == "highlight_fa":
            session.add_region_action(problem.fa, color=(255, 0, 0, 100))
        elif step == "highlight_fb":
            session.add_region_action(problem.fb, color=(0, 0, 255, 100))
        elif step == "union":
            # Special case: Union replaces the previous render logic
            img = draw_union_with_annotations(session.res_map, problem.fa, problem.fb, ...)
            img.save(f"hint_{problem.key}_step_{i}.png")
            continue
            
        # 2. Save the intermediate image for every step
        session.render().save(f"hint_{problem.key}_step_{i}.png")

def get_face_by_name(res_map, target_name):
    """
    Iterates through all faces in the map to find the one matching the name (e.g., 'C').
    """
    for face in res_map.faces:
        # Checking against the .name attribute of the Face class
        if face.letter == target_name:
            return face
    return None



def main():
    # 1. ENVIRONMENT SETUP
    maxX, maxY = 1.0, 1.0
    seed = 42
    Graph.initialize()
    
    # Using local functions with white borders
    visual_tools.tool_label_vertex = tool_label_vertex
    visual_tools.highlight_vertex = highlight_vertex
    
    res_map = BuildRandomMap.BuildRandomMap(8, maxX, maxY, seed)
    img_size = (int(200 + 800 * maxX), int(200 + 800 * maxY))
    session = AnnotationSession(res_map, img_size)

    # NEW: Run the gallery generator first
    run_galleries(session)
    
    # # 2. PPT SCENARIO 01: QUESTION 18
    # path_q18 = ensure_dir("ppt_demo_q18")
    # session.reset_actions()
    # try:
    #     p_v = next(v for v in res_map.vertices if v.num == 5) 
    #     q_v = next(v for v in res_map.vertices if v.num == 12) 
    # except StopIteration:
    #     p_v, q_v = res_map.vertices[0], res_map.vertices[-1]

    # session.add_vertex_action(p_v, label="P")
    # session.render().save(os.path.join(path_q18, "01a_grounding_P.png"))
    # session.add_vertex_action(q_v, label="Q")
    # session.render().save(os.path.join(path_q18, "01b_grounding_Q.png"))

    # 2. PPT SCENARIO 01: QUESTION 18 - Path Reasoning (P to Q via D, H, C)
    path_q18 = ensure_dir("ppt_demo_q18")
    session.reset_actions()
    
    try:
        p_v = next(v for v in res_map.vertices if v.num == 5) 
        q_v = next(v for v in res_map.vertices if v.num == 12) 
    except StopIteration:
        p_v, q_v = res_map.vertices[0], res_map.vertices[-1]

    # STEP 1: Grounding - Identify P and Q
    session.add_vertex_action(p_v, label="P")
    session.render().save(os.path.join(path_q18, "01a_grounding_P.png"))
    
    session.add_vertex_action(q_v, label="Q")
    session.render().save(os.path.join(path_q18, "01b_grounding_Q.png"))

    # STEP 2: Intent - Draw the line connecting them
    # Using your existing tool_draw_points_line
    session.add_action(tool_draw_points_line, p_v.p, q_v.p, color=(255, 0, 0, 255))
    session.render().save(os.path.join(path_q18, "02_path_line.png"))

    # STEP 3: Sequential Reasoning - Highlight Regions D, H, and C
    path_steps = ["D", "H", "C"]
    
    for i, region_name in enumerate(path_steps):
        target_face = get_face_by_name(res_map, region_name)
        if target_face:
            # We add a highlight for each step. 
            # label=str(i+1) will add (1), (2), (3) to the regions
            session.add_region_action(
                target_face, 
                label=str(i+1), 
                color=(255, 255, 0, 80) # Semi-transparent yellow
            )
            
            # Save the progress
            filename = f"03_step_{i+1}_region_{region_name}.png"
            session.render().save(os.path.join(path_q18, filename))
            print(f"Saved step {i+1}: Region {region_name}")

    
    # 3. PPT SCENARIO 02: QUESTION 11
    path_q11 = ensure_dir("ppt_demo_q11")
    session.reset_actions()
    target_face = get_face_by_name(res_map, "H")
    
    if target_face:
        session.add_region_action(target_face, label="H", color=(255, 255, 0, 80))
        face_vertices = [e.tail for e in target_face.edges]
        for i, v in enumerate(face_vertices):
            lbl = str(i + 1)
            session.add_vertex_action(v, label=lbl)
            session.add_action(tool_draw_interior_arc, Angle(p=v.p, parent_face=target_face), radius=40)
            session.render().save(os.path.join(path_q11, f"02_vertex_{lbl}.png"))

    print("All tasks complete. Check gallery_results and ppt_demo folders.")


def find_adjacent_faces(m_obj):
    """Helper to find two faces sharing an edge."""
    for face in m_obj.faces:
        if not face.bounded: continue
        for edge in face.edges:
            neighbor = edge.reverse.leftFace
            if neighbor and neighbor.bounded and neighbor != face:
                return face, neighbor
    return None, None

def get_face_by_label(session, label):
    # This searches the session's cache for the face associated with the letter
    for face, face_label in session.face_label_cache.items():
        if face_label == label:
            return face
    return None


if __name__ == "__main__":
    main()


