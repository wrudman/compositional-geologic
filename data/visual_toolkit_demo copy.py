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

# --- TOOL FUNCTIONS ---

def tool_highlight_region(draw, img, manager, face, label=None, color=None, label_cache=None):
    if not face.bounded: return
    lp, d = label_cache[id(face)] if label_cache else Graph.LetterPointFace(face)
    cx, cy = DrawGraph.V2P(lp)
    
    # --- COLOR SYNCHRONIZATION ---
    # Default Highlight Yellow: (255, 255, 0)
    # We use 100 alpha for the region fill, but 255 (solid) for the text
    highlight_yellow_fill = color if color else (255, 255, 0, 100)
    
    # Extract the RGB part for the text to make it opaque (or use a specific dark yellow/gold)
    # This ensures the "(1)" label is the same hue as the highlight
    text_color = (200, 180, 0, 255) # A darker gold/yellow so it is readable on white
    
    # 1. Draw the Highlight Polygon
    draw.polygon(DrawGraph.FaceVertex2P(face), fill=highlight_yellow_fill)
    
    is_large = d > 0.06
    font_main = DrawGraph.GetSystemFont(80 if is_large else 45)
    font_sub = DrawGraph.GetSystemFont(35 if is_large else 22)
    
    # 2. Redraw Base Letter (A, B, C...) in Black for contrast
    draw.text((cx, cy), face.letter, fill=(0, 0, 0, 255), font=font_main, 
              anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))
    
    # 3. Draw Sub-label ( (1), (2)... ) in the matching Yellow/Gold color
    if label:
        v_off = 45 if is_large else 28
        draw.text(
            (cx, cy + v_off), 
            str(label), 
            fill=text_color,  # Applied matching yellow/gold color here
            font=font_sub, 
            anchor="mm", 
            stroke_width=1, 
            stroke_fill=(255, 255, 255, 255)
        )
        
    manager.reserve(cx, cy, 60, 90)

def tool_label_vertex(draw, img, manager, vertex, label_text=None, color=(0, 0, 255, 255)):
    px, py = DrawGraph.V2P(vertex.p)
    draw.ellipse([px-10, py-10, px+10, py+10], fill=(255, 0, 0, 255))
    if label_text:
        font = DrawGraph.GetSystemFont(35)
        # Using simplified placement for brevity
        draw.text((px+15, py-20), str(label_text), fill=color, font=font, stroke_width=1, stroke_fill=(255,255,255,255))

def tool_label_edge(draw, img, manager, edge, label_text=None, color=(200, 0, 255, 255)):
    p1, p2 = DrawGraph.V2P(edge.tail.p), DrawGraph.V2P(edge.head.p)
    draw.line([p1, p2], fill=color, width=10)
    if label_text:
        mx, my = (p1[0]+p2[0])/2, (p1[1]+p2[1])/2
        draw.text((mx, my), str(label_text), fill=color, font=DrawGraph.GetSystemFont(28), anchor="mm", stroke_width=2, stroke_fill=(255,255,255,255))

def tool_label_angle(draw, img, manager, angle_data, label_text=None, color=(0, 128, 0, 255)):
    # Basic implementation for drawing arc
    p_center = angle_data.p
    cx, cy = DrawGraph.V2P(p_center)
    bbox = [cx - 40, cy - 40, cx + 40, cy + 40]
    draw.arc(bbox, start=0, end=90, fill=color, width=5) # Example arc
    if label_text:
        draw.text((cx+30, cy+30), str(label_text), fill=color, font=DrawGraph.GetSystemFont(30), anchor="mm")

def tool_draw_axis_line(draw, img, manager, vertex_p, direction='H', color=(0, 0, 255, 255), width=8):
    px, py = DrawGraph.V2P(vertex_p)
    if direction.upper() == 'H': draw.line([(100, py), (900, py)], fill=color, width=width)
    else: draw.line([(px, 100), (px, 900)], fill=color, width=width)

def tool_draw_extended_edge(draw, img, manager, edge, color=(0, 0, 255, 255), width=8):
    p1, p2 = DrawGraph.V2P(edge.tail.p), DrawGraph.V2P(edge.head.p)
    draw.line([p1, p2], fill=color, width=width) # Simplified extension

def tool_draw_points_line(draw, img, manager, v1_p, v2_p, color=(0, 0, 255, 255), width=6):
    p1, p2 = DrawGraph.V2P(v1_p), DrawGraph.V2P(v2_p)
    draw.line([p1, p2], fill=color, width=width)

def draw_union(res_map, fa, fb, manager, label_cache, maxX, maxY, filename="union_result.png"):
    img_w, img_h = int(200 + 800 * maxX), int(200 + 800 * maxY)
    img = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    DrawGraph.InitColors(alpha=153)
    font_bold = DrawGraph.GetSystemFont(80)
    font_small = DrawGraph.GetSystemFont(45)
    
    # Get the shared boundary to hide it
    shared_edge_ids = get_shared_edges(fa, fb)
    
    # 1. First Pass: Draw all face colors
    for face in res_map.faces:
        if not face.bounded: continue
        # Highlight color for the union pair, standard color for others
        fill_color = (147, 112, 219, 180) if face in (fa, fb) else DrawGraph.colors[face.color]
        draw.polygon(DrawGraph.FaceVertex2P(face), fill=fill_color)

    # 2. Second Pass: Draw black edges (Layered on top of colors)
    for edge in res_map.edges:
        # If this is the shared edge between fa and fb, don't draw it
        if id(edge) in shared_edge_ids:
            continue
        
        p1, p2 = DrawGraph.V2P(edge.tail.p), DrawGraph.V2P(edge.head.p)
        # Draw the black line
        draw.line([p1, p2], fill=(0, 0, 0, 255), width=6)

    # 3. Third Pass: Draw text labels (Layered on top of everything)
    for face in res_map.faces:
        if not face.bounded: continue
        
        # Use cached position
        lp, d = label_cache[id(face)]
        coords = DrawGraph.V2P(lp)
        
        if face not in (fa, fb):
            # Draw standard letters (A, B, C...)
            f_style = font_bold if d > 0.06 else font_small
            draw.text(coords, face.letter, fill=(0, 0, 0, 255), font=f_style, anchor="mm")
            manager.reserve(coords[0], coords[1], 35, 35)

    # 4. Draw the "U" label for the unioned region
    # We use fa's cached location for the "U"
    u_lp, _ = label_cache[id(fa)]
    draw.text(DrawGraph.V2P(u_lp), "U", fill=(0, 0, 0, 255), font=font_bold, anchor="mm",
              stroke_width=2, stroke_fill=(255, 255, 255, 255))
    
    # 5. Save and Return
    img.save(filename)
    print(f"Union image saved to: {filename}")
    return img

# --- GALLERY GENERATORS ---

BASE_DIR = "gallery_results"
def ensure_dir(category):
    path = os.path.join(BASE_DIR, category)
    os.makedirs(path, exist_ok=True)
    return path

def run_galleries(session):
    faces = [f for f in session.res_map.faces if f.bounded]
    target = random.choice(faces)

    # Vertex
    path = ensure_dir("vertex")
    session.reset_actions()
    for v in target.trueVertices: session.add_vertex_action(v, auto_enumerate=True)
    session.render().save(os.path.join(path, "vertex_enumerated.png"))

    # Edge
    path = ensure_dir("edge")
    session.reset_actions()
    for i, e in enumerate(target.edges): session.add_edge_action(e, label=str(i+1))
    session.render().save(os.path.join(path, "edge_labeled.png"))

    # Region
    path = ensure_dir("region")
    session.reset_actions()
    session.add_region_action(target, label="(1)")
    session.render().save(os.path.join(path, "region_dual_labeled.png"))

def main():
    maxX, maxY = 1.0, 1.0
    seed = 42
    Graph.initialize()
    res_map = BuildRandomMap.BuildRandomMap(8, maxX, maxY, seed)
    img_size = (int(200 + 800 * maxX), int(200 + 800 * maxY))

    session = AnnotationSession(res_map, img_size)
    run_galleries(session)

    # Union
    fa, fb = None, None
    for face in res_map.faces:
        if not face.bounded: continue
        for edge in face.edges:
            neighbor = edge.reverse.leftFace
            if neighbor and neighbor.bounded and neighbor != face:
                fa, fb = face, neighbor; break
        if fa: break
    
    if fa and fb:
        draw_union(res_map, fa, fb, LabelManager(), session.face_label_cache, maxX, maxY, 
                   filename=os.path.join(BASE_DIR, "region/union_result.png"))

if __name__ == "__main__":
    main()