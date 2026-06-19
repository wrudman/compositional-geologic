# app.py
import base64
import json
import math
import os
import pickle
from io import BytesIO
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageDraw
from streamlit_image_coordinates import streamlit_image_coordinates

import Graph
import BuildRandomMap
import DrawGraph
import map_helpers
import tools_human as T
from sel_types import AngleSel, EdgeSel

st.set_page_config(layout="wide", page_title="Geo Tools")
st.title("Geologic Region Explorer")

DISPLAY_SIDE = 460          # map render size; clicks are mapped back through this
MATH_SCALE = 800.0
USE_URL_PICKERS = True
PERSIST_FILE = "/private/tmp/compositional_geo_tools_state.pkl"

# Xiaohui's palette
GOLD_FILL = (255, 215, 0, 230)
GOLD_OUTLINE = (184, 134, 11, 255)
TEAL = (0, 255, 204, 255)
CYAN_EDGE = (0, 255, 255, 235)
YELLOW_REGION = (255, 255, 0, 100)
GRAY_SELECTION = (120, 120, 120, 95)
GRAY_OUTLINE = (90, 90, 90, 210)
UNION_PURPLE = (147, 112, 219, 255)
GREEN_ANGLE = (0, 150, 0, 255)
BLUE = (0, 0, 255, 255)

PERSIST_KEYS = [
    "res_map", "face_label_cache", "maxX", "maxY", "active_tool", "selection",
    "vertex_region_mode", "vf_meeting_region_labels", "last_click",
    "click_targets", "pending_angle_vertex", "pending_confirm_vertex_id",
    "pending_confirm_kind", "pending_confirm_id", "pending_confirm_action",
    "pending_confirm_obj", "result_summary", "annotations", "lines",
    "angles", "named_edges", "unions", "union_consumed", "undo_stack",
    "vertex_names", "vertex_descriptions", "point_names", "program", "log",
    "translations", "counters",
    "last_neighbor_action", "last_draw_action", "last_measure_action",
    "last_sort_action", "rad_neighbor_action", "rad_draw_action",
    "rad_measure_action", "rad_sort_action",
]

def load_persisted_state():
    if "res_map" in st.session_state or not os.path.exists(PERSIST_FILE):
        return
    try:
        with open(PERSIST_FILE, "rb") as f:
            saved = pickle.load(f)
        for key, value in saved.items():
            st.session_state[key] = value
    except Exception:
        return

def persist_state():
    try:
        saved = {key: st.session_state.get(key) for key in PERSIST_KEYS if key in st.session_state}
        with open(PERSIST_FILE, "wb") as f:
            pickle.dump(saved, f)
    except Exception:
        pass

def persist_and_rerun():
    persist_state()
    st.rerun()

# ============================================================
# 0. TYPE CHECKERS (name-based: immune to Streamlit reruns)
# ============================================================
def is_angle(o):   return type(o).__name__ == "AngleSel"
def is_edgesel(o): return type(o).__name__ == "EdgeSel"
def is_vertex(o):  return hasattr(o, "outarcs")
def is_region(o):
    return (not is_angle(o) and not is_edgesel(o)
            and hasattr(o, "edges") and hasattr(o, "bounded"))

# ============================================================
# 1. SESSION INIT
# ============================================================
load_persisted_state()

if "res_map" not in st.session_state:
    Graph.initialize()
    maxX, maxY = 1.0, 1.0
    seed = 42
    res_map = BuildRandomMap.BuildRandomMap(8, maxX, maxY, seed)
    map_helpers.use_map(res_map)
    T.setup(res_map)

    # lock region label positions ONCE
    face_label_cache = {}
    for face in res_map.faces:
        if face.bounded:
            face._cache_idx = id(face)
            lp, d = Graph.LetterPointFace(face)
            face_label_cache[id(face)] = (lp, d)

    st.session_state.res_map = res_map
    st.session_state.face_label_cache = face_label_cache
    st.session_state.maxX, st.session_state.maxY = maxX, maxY
    st.session_state.active_tool = None
    st.session_state.selection = []
    st.session_state.vertex_region_mode = None
    st.session_state.vf_meeting_region_labels = []
    st.session_state.last_click = None
    st.session_state.click_targets = None
    st.session_state.pending_angle_vertex = None
    st.session_state.pending_confirm_vertex_id = None
    st.session_state.pending_confirm_kind = None
    st.session_state.pending_confirm_id = None
    st.session_state.pending_confirm_action = None
    st.session_state.pending_confirm_obj = None
    st.session_state.result_summary = None
    st.session_state.annotations = []
    st.session_state.lines = []        # [(name, line_dict)]
    st.session_state.angles = []       # [(name, AngleSel)]
    st.session_state.named_edges = []  # [(name, EdgeSel)]
    st.session_state.unions = []       # [{"name","face","pair","label_xy"}]
    st.session_state.union_consumed = []   # constituent faces now hidden inside a union
    st.session_state.undo_stack = []   # snapshots for single-step undo
    st.session_state.vertex_names = {}
    st.session_state.vertex_descriptions = {}
    st.session_state.program = []
    st.session_state.log = []
    st.session_state.translations = []
    st.session_state.counters = {"v": 1, "L": 1, "U": 1, "r": 1, "a": 1, "e": 1}

map_helpers.use_map(st.session_state.res_map)
T.setup(st.session_state.res_map)

if "vertex_names" not in st.session_state:
    old_names = st.session_state.get("point_names", {})
    st.session_state.vertex_names = {}
    old_to_new = {}
    for old_name in old_names.values():
        if old_name not in old_to_new:
            old_to_new[old_name] = f"v{len(old_to_new) + 1}"
    for key, old_name in old_names.items():
        st.session_state.vertex_names[key] = old_to_new.get(old_name, old_name)
    for ann in st.session_state.get("annotations", []):
        if ann.get("kind") == "point":
            ann["kind"] = "vertex"
        if ann.get("label") in old_to_new:
            ann["label"] = old_to_new[ann["label"]]
    for key_name in ("program", "log"):
        rewritten = []
        for entry in st.session_state.get(key_name, []):
            for old_name, new_name in old_to_new.items():
                entry = entry.replace(old_name, new_name)
            rewritten.append(entry)
        st.session_state[key_name] = rewritten
if "v" not in st.session_state.counters:
    st.session_state.counters["v"] = len(st.session_state.vertex_names) + 1
if "vertex_descriptions" not in st.session_state:
    st.session_state.vertex_descriptions = {}
if "translations" not in st.session_state:
    st.session_state.translations = []
else:
    st.session_state.translations = [
        entry for entry in st.session_state.translations
        if not entry.startswith("Intersect returned ")
    ]
for ann in st.session_state.get("annotations", []):
    if ann.get("kind") == "vertex" and ann.get("label") and ann.get("p") is not None:
        p = ann["p"]
        st.session_state.vertex_names.setdefault(f"{p.x:.6f},{p.y:.6f}", ann["label"])
        for v in st.session_state.res_map.vertices:
            if Graph.vecDist(v.p, p) < 1e-6:
                st.session_state.vertex_names.setdefault(id(v), ann["label"])

res_map = st.session_state.res_map
maxX, maxY = st.session_state.maxX, st.session_state.maxY
img_size = (int(200 + 800 * maxX), int(200 + 800 * maxY))


# ============================================================
# 2. NAMING & DESCRIPTIONS
# ============================================================
def next_name(prefix):
    n = st.session_state.counters[prefix]
    st.session_state.counters[prefix] += 1
    return f"{prefix}{n}"

def vertex_keys(v):
    return (id(v), f"{v.p.x:.6f},{v.p.y:.6f}")

def find_existing_vertex_name(v):
    for key in vertex_keys(v):
        if key in st.session_state.vertex_names:
            return st.session_state.vertex_names[key]
    for ann in st.session_state.get("annotations", []):
        if ann.get("kind") != "vertex" or not ann.get("label") or ann.get("p") is None:
            continue
        if Graph.vecDist(ann["p"], v.p) < 1e-6:
            for key in vertex_keys(v):
                st.session_state.vertex_names[key] = ann["label"]
            return ann["label"]
    return None

def vertex_name(v, create=True):
    existing = find_existing_vertex_name(v)
    if existing:
        return existing
    if not create:
        return None
    name = next_name("v")
    for key in vertex_keys(v):
        st.session_state.vertex_names[key] = name
    st.session_state.annotations.append({"kind": "vertex", "p": v.p, "label": name})
    return name

def angle_name(a_sel):
    for name, sel in st.session_state.angles:
        if sel == a_sel:
            return name
    return "a?"

def edge_name(e_sel):
    for name, sel in st.session_state.named_edges:
        if sel == e_sel:
            return name
    return None

def code_name(o):
    if o == "frame":  return '"frame"'
    if is_angle(o):   return angle_name(o)
    if is_edgesel(o):
        nm = edge_name(o)
        return nm if nm else f"edge[{o.text}]"
    if is_region(o):  return o.letter
    if is_vertex(o):  return vertex_name(o)
    return str(o)

def vertex_ref(v):
    nm = vertex_name(v, create=False)
    return nm if nm else f"vertex({v.p.x:.2f}, {v.p.y:.2f})"

def set_vertex_description(v, text):
    for key in vertex_keys(v):
        st.session_state.vertex_descriptions[key] = text

def vertex_phrase(v):
    nm = vertex_name(v, create=False)
    if nm:
        return f"vertex {nm}"
    return f"vertex ({v.p.x:.2f}, {v.p.y:.2f})"

def label_vertex_sentence(description, name):
    article = "" if description.lower().startswith("the ") else "the "
    return f"Labeled {article}{description} as {name}."

def describe(o):
    # angle/edge checks FIRST
    if is_angle(o):
        return f"angle {angle_name(o)} (in Region {o.face.letter})"
    if is_edgesel(o):
        nm = edge_name(o)
        return f"edge {nm} ({o.text})" if nm else o.text
    if isinstance(o, (list, tuple, set)):
        items = list(o)
        return "(nothing)" if not items else ", ".join(describe(x) for x in items)
    if o is None: return "(nothing)"
    if isinstance(o, bool): return "YES" if o else "NO"
    if o == "frame": return "the Frame"
    if is_region(o):
        return f"Region {o.letter}" if getattr(o, "bounded", True) else "the Outside (frame)"
    if is_vertex(o):
        nm = vertex_name(o, create=False)
        return nm if nm else f"vertex ({o.p.x:.2f}, {o.p.y:.2f})"
    if isinstance(o, dict) and "type" in o:
        return {"segment": "a segment", "extend": "a full line", "ray": "a ray"}[o["type"]]
    if isinstance(o, float): return f"{o:.4f}"
    return str(o)

def raw_output(o):
    if is_angle(o):
        return angle_name(o)
    if is_edgesel(o):
        return edge_name(o) or f"edge[{o.text}]"
    if isinstance(o, (list, tuple)):
        return "[" + ", ".join(raw_output(x) for x in o) + "]"
    if isinstance(o, set):
        return "{" + ", ".join(sorted(raw_output(x) for x in o)) + "}"
    if o is None:
        return "None"
    if isinstance(o, bool):
        return "True" if o else "False"
    if o == "frame":
        return '"frame"'
    if is_region(o):
        return getattr(o, "letter", "?") if getattr(o, "bounded", True) else '"Outside"'
    if is_vertex(o):
        return vertex_ref(o)
    if isinstance(o, float):
        return f"{o:.4f}"
    return str(o)

def draw_log_sentence(name, action, start, end=None, direction=None, edge=None, kind=None):
    if action == "ray_vertex":
        return f"Drew {name}: a ray from {vertex_phrase(start)} toward {direction}."
    line_kind = "full line" if kind == "full" else "line segment"
    sentence = f"Drew {name}: a {line_kind} from {vertex_phrase(start)} to {vertex_phrase(end)}."
    if edge is not None:
        sentence += f" It follows {describe(edge)}."
    return sentence

def intersect_translation(line_name, target, result):
    if target == "faces":
        regions = [display_item(face) for face in result]
        if not regions:
            return f"{line_name} does not pass through any regions."
        return f"{line_name} passes through {', '.join(regions)}."
    target_name = target[0]
    if result is None or result is False or str(result).upper() in ("NO", "FALSE", "NONE"):
        return f"{line_name} and {target_name} do not intersect."
    if result:
        return f"{line_name} and {target_name} intersect at {vertex_phrase(result)}."
    return f"{line_name} and {target_name} do not intersect."

def sel_sig():
    s = st.session_state.selection
    return {
        "regions":  [o for o in s if o != "frame" and is_region(o)],
        "vertices": [o for o in s if o != "frame" and is_vertex(o)],
        "edges":    [o for o in s if is_edgesel(o)],
        "angles":   [o for o in s if is_angle(o)],
        "frame":    [o for o in s if o == "frame"],
        "n": len(s),
    }

# ============================================================
# 3. LINE GEOMETRY
# ============================================================
def _extend_to_frame(a, b):
    dx, dy = b.x - a.x, b.y - a.y
    ts = []
    if abs(dx) > 1e-9: ts += [(0 - a.x) / dx, (maxX - a.x) / dx]
    if abs(dy) > 1e-9: ts += [(0 - a.y) / dy, (maxY - a.y) / dy]
    pts = []
    for t in ts:
        x, y = a.x + t * dx, a.y + t * dy
        if -1e-6 <= x <= maxX + 1e-6 and -1e-6 <= y <= maxY + 1e-6:
            pts.append((t, Graph.Vector(x, y)))
    pts.sort(key=lambda z: z[0])
    return pts[0][1], pts[-1][1]

def line_endpoints_math(line):
    if line["type"] == "segment":
        return line["a"], line["b"]
    if line["type"] == "extend":
        return _extend_to_frame(line["a"], line["b"])
    if line["type"] == "ray":
        a = line["a"]
        ends = {0: Graph.Vector(maxX, a.y), 1: Graph.Vector(a.x, maxY),
                2: Graph.Vector(0, a.y), 3: Graph.Vector(a.x, 0)}
        return a, ends[line["direction"]]

def edgesel_endpoints(es):
    pts = []
    for e in es.segments:
        pts += [e.tail, e.head]
    best, bd = (pts[0], pts[-1]), -1
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            d = Graph.vecDist(pts[i].p, pts[j].p)
            if d > bd:
                bd, best = d, (pts[i], pts[j])
    return best

# ============================================================
# 4. XIAOHUI-STYLE DRAWING PRIMITIVES
# ============================================================
def highlight_vertex_x(odraw, p, ring=False):
    px, py = DrawGraph.V2P(p)
    if ring:
        odraw.ellipse([px-15, py-15, px+15, py+15], outline=TEAL, width=4)
    else:
        odraw.ellipse([px-12, py-12, px+12, py+12], fill=GOLD_FILL,
                      outline=GOLD_OUTLINE, width=4)

def highlight_edge_x(odraw, e, label=None):
    """Thick cyan marker stroke + end-vertex caps; optional name label."""
    p1, p2 = DrawGraph.V2P(e.tail.p), DrawGraph.V2P(e.head.p)
    odraw.line([p1, p2], fill=CYAN_EDGE, width=14)
    for (px, py) in (p1, p2):
        odraw.ellipse([px-7, py-7, px+7, py+7], fill=CYAN_EDGE)
    if label:
        mx, my = (p1[0]+p2[0])//2, (p1[1]+p2[1])//2
        font = DrawGraph.GetSystemFont(35)
        odraw.text((mx, my), label, fill=(0, 100, 130, 255), font=font,
                   anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))

def draw_interior_arc_x(odraw, vertex, face, label=None,
                        radius=45, color=GREEN_ANGLE, width=5):
    """Xiaohui's interior arc (position match + fallbacks, pixel-space sweep)."""
    p_center = vertex.p
    e_in = next((e for e in face.edges if e.head.p == p_center), None)
    e_out = next((e for e in face.edges if e.tail.p == p_center), None)
    if not e_in:
        e_in = next((e for e in face.edges
                     if e.head == vertex or Graph.vecDist(e.head.p, p_center) < 1e-9), None)
    if not e_out:
        e_out = next((e for e in face.edges
                      if e.tail == vertex or Graph.vecDist(e.tail.p, p_center) < 1e-9), None)
    if not e_in or not e_out:
        return
    cx, cy = DrawGraph.V2P(p_center)
    px_prev, py_prev = DrawGraph.V2P(e_in.tail.p)
    px_next, py_next = DrawGraph.V2P(e_out.head.p)
    ang_prev = math.degrees(math.atan2(py_prev - cy, px_prev - cx))
    ang_next = math.degrees(math.atan2(py_next - cy, px_next - cx))
    start, end = ang_prev, ang_next
    while end < start:
        end += 360
    sweep = end - start
    if abs(sweep - 180.0) < 0.1:
        return
    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
    odraw.arc(bbox, start=start, end=end, fill=color, width=width)
    if label:
        mid = math.radians(start + sweep / 2)
        lx = cx + (radius + 24) * math.cos(mid)
        ly = cy + (radius + 24) * math.sin(mid)
        font = DrawGraph.GetSystemFont(35)
        odraw.text((lx, ly), label, fill=color, font=font, anchor="mm",
                   stroke_width=2, stroke_fill=(255, 255, 255, 255))

def draw_union_solid(draw, union, font_big):
    fu = union["face"]
    pts = [DrawGraph.V2P(v.p) for v in fu.vertices]
    draw.polygon(pts, fill=UNION_PURPLE)
    for e in fu.edges:
        draw.line([DrawGraph.V2P(e.tail.p), DrawGraph.V2P(e.head.p)],
                  fill=(0, 0, 0, 255), width=6)
    lx, ly = union["label_xy"]
    draw.text((lx, ly), union["name"], fill=(0, 0, 0, 255), font=font_big,
              anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))

def _face_label_lp_d(face):
    """Stable label position for a face (uses the locked cache when available)."""
    idx = getattr(face, "_cache_idx", None)
    cache = st.session_state.get("face_label_cache", {})
    if idx is not None and idx in cache:
        return cache[idx]
    return Graph.LetterPointFace(face)

def highlight_region_solid(odraw, face, fill=GRAY_SELECTION):
    """Soft translucent region highlight; keeps the label readable."""
    pts = [DrawGraph.V2P(v.p) for v in face.vertices]
    odraw.polygon(pts, fill=fill, outline=GRAY_OUTLINE)
    for e in face.edges:
        odraw.line([DrawGraph.V2P(e.tail.p), DrawGraph.V2P(e.head.p)],
                   fill=GRAY_OUTLINE, width=4)
    lp, d = _face_label_lp_d(face)
    coords = DrawGraph.V2P(lp)
    font = DrawGraph.GetSystemFont(80 if d > 0.06 else 45)
    odraw.text(coords, face.letter, fill=(0, 0, 0, 255), font=font, anchor="mm",
               stroke_width=2, stroke_fill=(255, 255, 255, 255))

# ============================================================
# 5. RENDERING
# ============================================================
def render():
    img = Image.new("RGBA", img_size, (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    DrawGraph.DrawAllFaces(res_map, draw, None,
                           label_cache=st.session_state.face_label_cache)

    font = DrawGraph.GetSystemFont(35)
    font_big = DrawGraph.GetSystemFont(80)

    for union in st.session_state.unions:
        draw_union_solid(draw, union, font_big)

    overlay = Image.new("RGBA", img_size, (255, 255, 255, 0))
    odraw = ImageDraw.Draw(overlay)

    # ---- PASS 1: region fills go UNDERNEATH vertices/lines/angles, so a
    # reference vertex is never hidden under a highlight. The unbounded outer
    # face is never filled (it would blanket the whole canvas).
    for ann in st.session_state.annotations:
        if ann["kind"] == "region" and getattr(ann["obj"], "bounded", False):
            highlight_region_solid(odraw, ann["obj"], ann.get("color", GRAY_SELECTION))
    for o in st.session_state.selection:
        if o != "frame" and is_region(o) and getattr(o, "bounded", False):
            highlight_region_solid(odraw, o, GRAY_SELECTION)

    # ---- PASS 2: markers (vertices, lines, angles, edges) on top of fills.
    for ann in st.session_state.annotations:
        kind = ann["kind"]
        if kind in ("vertex", "point"):
            highlight_vertex_x(odraw, ann["p"])
            if ann.get("label"):
                px, py = DrawGraph.V2P(ann["p"])
                odraw.text((px + 16, py - 32), ann["label"], fill=BLUE, font=font,
                           stroke_width=2, stroke_fill=(255, 255, 255, 255))
        elif kind == "line":
            a, b = line_endpoints_math(ann["line"])
            odraw.line([DrawGraph.V2P(a), DrawGraph.V2P(b)], fill=BLUE, width=6)
            if ann.get("label"):
                mx = (DrawGraph.V2P(a)[0] + DrawGraph.V2P(b)[0]) // 2
                my = (DrawGraph.V2P(a)[1] + DrawGraph.V2P(b)[1]) // 2
                odraw.text((mx, my), ann["label"], fill=BLUE, font=font,
                           anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))
        elif kind == "angle":
            draw_interior_arc_x(odraw, ann["vertex"], ann["face"],
                                label=ann.get("label"))

    # live selection markers — angle/edge checks FIRST
    for o in st.session_state.selection:
        if o == "frame":
            p_bl, p_tr = DrawGraph.V2P(Graph.Vector(0, 0)), DrawGraph.V2P(Graph.Vector(maxX, maxY))
            odraw.rectangle([p_bl[0], p_tr[1], p_tr[0], p_bl[1]], outline=TEAL, width=10)
        elif is_angle(o):
            draw_interior_arc_x(odraw, o.vertex, o.face, label=angle_name(o),
                                color=TEAL, width=6)
        elif is_edgesel(o):
            for e in o.segments:
                highlight_edge_x(odraw, e)
            # label once at the center of the first segment
            highlight_edge_x(odraw, o.segments[0], label=edge_name(o))
        elif is_vertex(o):
            highlight_vertex_x(odraw, o.p, ring=True)

    pending_obj = st.session_state.get("pending_confirm_obj")
    pending_vertex = pending_obj if is_vertex(pending_obj) else find_selectable_vertex(st.session_state.get("pending_confirm_vertex_id"))
    if pending_vertex is not None:
        highlight_vertex_x(odraw, pending_vertex.p, ring=True)
    pending_kind = st.session_state.get("pending_confirm_kind")
    pending_id = st.session_state.get("pending_confirm_id")
    if pending_kind == "region":
        pending_region = pending_obj if is_region(pending_obj) else find_selectable_region(pending_id)
        if pending_region is not None and getattr(pending_region, "bounded", False):
            highlight_region_solid(odraw, pending_region, GRAY_SELECTION)
    elif pending_kind == "edge":
        pending_edge = pending_obj if pending_obj is not None else find_selectable_edge(pending_id)
        if pending_edge is not None:
            highlight_edge_x(odraw, pending_edge)
    elif pending_kind == "edge_object" and pending_obj is not None:
        for e in pending_obj.segments:
            highlight_edge_x(odraw, e)

    img.alpha_composite(overlay)
    return img

# ============================================================
# 6. CLICK HIT-TESTING
# ============================================================
def get_math_coords(px, py):
    rx = px * (img_size[0] / DISPLAY_SIDE)
    ry = py * (img_size[1] / DISPLAY_SIDE)
    return Graph.Vector((rx - 100) / MATH_SCALE, (900.0 - ry) / MATH_SCALE)

def hit_test(px, py):
    cp = get_math_coords(px, py)
    v_best, v_d = None, 25 / MATH_SCALE
    for v in res_map.vertices:
        d = Graph.vecDist(cp, v.p)
        if d < v_d: v_d, v_best = d, v

    # A merged region (union) takes priority over the originals beneath it, and
    # its constituent faces are no longer independently selectable.
    f_hit = None
    for union in st.session_state.unions:
        if Graph.pointInsideFace(cp, union["face"]):
            f_hit = union["face"]
            break
    if f_hit is None:
        consumed = st.session_state.union_consumed
        f_hit = next((f for f in res_map.faces
                      if f.bounded and f not in consumed
                      and Graph.pointInsideFace(cp, f)), None)

    e_best, e_d = None, 20 / MATH_SCALE
    for e in res_map.edges:
        d = Graph.distPointFromEdge(cp, e.tail.p, e.head.p)
        if d < e_d: e_d, e_best = d, e
    return v_best, f_hit, e_best

def image_to_data_url(img):
    buf = BytesIO()
    img.convert("RGBA").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

def selectable_region_data():
    consumed = st.session_state.union_consumed
    regions = []
    for face in res_map.faces:
        if not getattr(face, "bounded", False) or face in consumed:
            continue
        regions.append(face)
    for union in st.session_state.unions:
        regions.append(union["face"])

    data = []
    for face in regions:
        verts = []
        for v in face.vertices:
            px, py = DrawGraph.V2P(v.p)
            verts.append({
                "x": px / (img_size[0] / DISPLAY_SIDE),
                "y": py / (img_size[1] / DISPLAY_SIDE),
            })
        data.append({
            "id": getattr(face, "letter", str(id(face))),
            "label": getattr(face, "letter", "?"),
            "vertices": verts,
        })
    return data

def find_selectable_region(region_id):
    rid = str(region_id)
    by_label = find_selectable_region_by_label(rid)
    if by_label is not None:
        return by_label
    consumed = st.session_state.union_consumed
    for face in res_map.faces:
        if str(id(face)) == rid and getattr(face, "bounded", False) and face not in consumed:
            return face
    for union in st.session_state.unions:
        face = union["face"]
        if str(id(face)) == rid:
            return face
    return None

def find_selectable_region_by_label(region_label):
    label = str(region_label)
    consumed = st.session_state.union_consumed
    for face in res_map.faces:
        if getattr(face, "letter", "") == label and getattr(face, "bounded", False) and face not in consumed:
            return face
    for union in st.session_state.unions:
        face = union["face"]
        if getattr(face, "letter", "") == label:
            return face
    return None

def find_selectable_vertex(vertex_id):
    vid = str(vertex_id)
    if vid.isdigit():
        idx = int(vid)
        if 0 <= idx < len(res_map.vertices):
            return res_map.vertices[idx]
    for v in res_map.vertices:
        if str(id(v)) == vid:
            return v
    return None

def find_selectable_edge(edge_id):
    eid = str(edge_id)
    if eid.isdigit():
        idx = int(eid)
        if 0 <= idx < len(res_map.edges):
            return res_map.edges[idx]
    for e in res_map.edges:
        if str(id(e)) == eid:
            return e
    return None

def regions_from_labels(labels):
    regions = []
    for label in labels:
        face = find_selectable_region_by_label(label)
        if face is not None and face not in regions:
            regions.append(face)
    return regions

def vertex_in_region(vertex, region):
    return any(Graph.vecDist(vertex.p, v.p) < 1e-9 for v in face_vertices_unique(region))

def clear_query_keys(*keys):
    for key in keys:
        if key in st.query_params:
            del st.query_params[key]

def selectable_vertex_data():
    vertices = list(res_map.vertices)
    sig = sel_sig()
    if (
        st.session_state.get("active_tool") == "neighbors"
        and st.session_state.get("rad_neighbor_action") == "ordered"
        and len(sig["regions"]) == 1
        and len(sig["vertices"]) == 0
    ):
        vertices = face_vertices_unique(sig["regions"][0])
    data = []
    for v in vertices:
        px, py = DrawGraph.V2P(v.p)
        data.append({
            "id": str(id(v)),
            "x": px / (img_size[0] / DISPLAY_SIDE),
            "y": py / (img_size[1] / DISPLAY_SIDE),
        })
    return data

def selectable_edge_data():
    seen = set()
    data = []
    for i, e in enumerate(res_map.edges):
        root = getattr(e, "trueEdge", e)
        key = id(root)
        if key in seen:
            continue
        seen.add(key)
        p1, p2 = DrawGraph.V2P(e.tail.p), DrawGraph.V2P(e.head.p)
        data.append({
            "id": str(i),
            "x1": p1[0] / (img_size[0] / DISPLAY_SIDE),
            "y1": p1[1] / (img_size[1] / DISPLAY_SIDE),
            "x2": p2[0] / (img_size[0] / DISPLAY_SIDE),
            "y2": p2[1] / (img_size[1] / DISPLAY_SIDE),
        })
    return data

def hover_selection_picker(display_img, allowed_kinds, active_tool=None, active_action=None):
    kinds_json = json.dumps(sorted(allowed_kinds))
    vertices_json = json.dumps(selectable_vertex_data() if "vertex" in allowed_kinds else [])
    regions_json = json.dumps(selectable_region_data() if "region" in allowed_kinds else [])
    edges_json = json.dumps(selectable_edge_data() if "edge" in allowed_kinds else [])
    img_src = image_to_data_url(display_img)
    active_tool_json = json.dumps(active_tool)
    active_action_json = json.dumps(active_action)
    html = f"""
    <div style="width:{DISPLAY_SIDE}px;">
      <div style="position:relative; width:{DISPLAY_SIDE}px; height:{DISPLAY_SIDE}px; border-radius:8px; overflow:hidden;">
        <canvas id="pickBg" width="{DISPLAY_SIDE}" height="{DISPLAY_SIDE}" style="position:absolute; left:0; top:0;"></canvas>
        <canvas id="pickOverlay" width="{DISPLAY_SIDE}" height="{DISPLAY_SIDE}" style="position:absolute; left:0; top:0; cursor:pointer;"></canvas>
      </div>
      <div id="pickStatus" style="font: 13px -apple-system, BlinkMacSystemFont, sans-serif; color:#444; margin-top:8px; min-height:20px;">Hovering: none</div>
    </div>
    <script>
      const allowedKinds = {kinds_json};
      const vertices = {vertices_json};
      const regions = {regions_json};
      const edges = {edges_json};
      const activeTool = {active_tool_json};
      const activeAction = {active_action_json};
      const bg = document.getElementById("pickBg");
      const bctx = bg.getContext("2d");
      const overlay = document.getElementById("pickOverlay");
      const ctx = overlay.getContext("2d");
      const statusEl = document.getElementById("pickStatus");
      const img = new Image();
      let hover = null;
      img.onload = () => bctx.drawImage(img, 0, 0, {DISPLAY_SIDE}, {DISPLAY_SIDE});
      img.src = "{img_src}";

      function insidePolygon(x, y, points) {{
        let inside = false;
        for (let i = 0, j = points.length - 1; i < points.length; j = i++) {{
          const xi = points[i].x, yi = points[i].y;
          const xj = points[j].x, yj = points[j].y;
          const intersect = ((yi > y) !== (yj > y)) &&
            (x < (xj - xi) * (y - yi) / ((yj - yi) || 1e-9) + xi);
          if (intersect) inside = !inside;
        }}
        return inside;
      }}

      function distToSegment(px, py, e) {{
        const dx = e.x2 - e.x1, dy = e.y2 - e.y1;
        const len2 = dx * dx + dy * dy || 1e-9;
        const t = Math.max(0, Math.min(1, ((px - e.x1) * dx + (py - e.y1) * dy) / len2));
        const x = e.x1 + t * dx, y = e.y1 + t * dy;
        return Math.hypot(px - x, py - y);
      }}

      function findHover(x, y) {{
        if (allowedKinds.includes("vertex")) {{
          let best = null, bd = 18;
          for (const v of vertices) {{
            const d = Math.hypot(x - v.x, y - v.y);
            if (d < bd) {{ best = v; bd = d; }}
          }}
          if (best) return {{ kind: "vertex", data: best }};
        }}
        if (allowedKinds.includes("edge")) {{
          let best = null, bd = 14;
          for (const e of edges) {{
            const d = distToSegment(x, y, e);
            if (d < bd) {{ best = e; bd = d; }}
          }}
          if (best) return {{ kind: "edge", data: best }};
        }}
        if (allowedKinds.includes("region")) {{
          for (const r of regions) {{
            if (insidePolygon(x, y, r.vertices)) return {{ kind: "region", data: r }};
          }}
        }}
        return null;
      }}

      function redraw() {{
        ctx.clearRect(0, 0, {DISPLAY_SIDE}, {DISPLAY_SIDE});
        if (!hover) return;
        if (hover.kind === "vertex") {{
          const v = hover.data;
          ctx.beginPath();
          ctx.arc(v.x, v.y, 15, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(120,120,120,0.22)";
          ctx.strokeStyle = "rgba(80,80,80,0.9)";
          ctx.lineWidth = 4;
          ctx.fill();
          ctx.stroke();
        }} else if (hover.kind === "edge") {{
          const e = hover.data;
          ctx.beginPath();
          ctx.moveTo(e.x1, e.y1);
          ctx.lineTo(e.x2, e.y2);
          ctx.strokeStyle = "rgba(80,80,80,0.9)";
          ctx.lineWidth = 10;
          ctx.lineCap = "round";
          ctx.stroke();
        }} else if (hover.kind === "region") {{
          const r = hover.data;
          ctx.beginPath();
          ctx.moveTo(r.vertices[0].x, r.vertices[0].y);
          for (let i = 1; i < r.vertices.length; i++) ctx.lineTo(r.vertices[i].x, r.vertices[i].y);
          ctx.closePath();
          ctx.fillStyle = "rgba(120,120,120,0.18)";
          ctx.strokeStyle = "rgba(80,80,80,0.85)";
          ctx.lineWidth = 4;
          ctx.fill();
          ctx.stroke();
        }}
      }}

      overlay.addEventListener("mousemove", (event) => {{
        const rect = overlay.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        hover = findHover(x, y);
        statusEl.textContent = hover ? "Hovering: " + hover.kind : "Hovering: none";
        redraw();
      }});

      overlay.addEventListener("mouseleave", () => {{
        hover = null;
        statusEl.textContent = "Hovering: none";
        redraw();
      }});

      overlay.addEventListener("click", () => {{
        if (!hover) return;
        const url = new URL(window.parent.location.href);
        url.searchParams.set("pick_kind", hover.kind);
        url.searchParams.set("pick_id", hover.data.id);
        if (activeTool) url.searchParams.set("active_tool", activeTool);
        if (activeAction) url.searchParams.set("pick_action", activeAction);
        window.parent.location.replace(url.toString());
      }});
    </script>
    """
    components.html(html, height=DISPLAY_SIDE + 35, width=DISPLAY_SIDE + 20)

def vertex_region_picker(display_img, meeting_labels=None):
    if meeting_labels is None:
        meeting_labels = []
    regions_json = json.dumps(selectable_region_data())
    meeting_labels_json = json.dumps(meeting_labels)
    img_src = image_to_data_url(display_img)
    html = f"""
    <div style="width:{DISPLAY_SIDE}px;">
      <div style="font: 13px -apple-system, BlinkMacSystemFont, sans-serif; color:#444; margin-bottom:8px;">
        Vertex: hover to preview a region, then click to hold it. Use one button to replace the current region, or the other to add it to a meeting vertex.
      </div>
      <div style="position:relative; width:{DISPLAY_SIDE}px; height:{DISPLAY_SIDE}px; border-radius:8px; overflow:hidden;">
        <canvas id="vfBg" width="{DISPLAY_SIDE}" height="{DISPLAY_SIDE}" style="position:absolute; left:0; top:0;"></canvas>
        <canvas id="vfOverlay" width="{DISPLAY_SIDE}" height="{DISPLAY_SIDE}" style="position:absolute; left:0; top:0; cursor:pointer;"></canvas>
      </div>
      <div id="vfStatus" style="font: 13px -apple-system, BlinkMacSystemFont, sans-serif; color:#444; margin-top:8px; min-height:20px;">
        Hovering: none
      </div>
      <div style="display:grid; grid-template-columns:1fr; gap:8px; margin-top:8px;">
        <button id="vfUseOnly" disabled
          style="width:100%; padding:10px; border-radius:6px; border:0; background:#1565C0; color:white; font-weight:700; opacity:0.45; cursor:not-allowed;">
          Confirm: use this region for a vertex
        </button>
        <button id="vfAddMeeting" disabled
          style="width:100%; padding:10px; border-radius:6px; border:0; background:#7E57C2; color:white; font-weight:700; opacity:0.45; cursor:not-allowed;">
          Confirm: add region for meeting vertex
        </button>
      </div>
    </div>
    <script>
      const regions = {regions_json};
      const currentMeetingLabels = {meeting_labels_json};
      const bg = document.getElementById("vfBg");
      const bctx = bg.getContext("2d");
      const overlay = document.getElementById("vfOverlay");
      const ctx = overlay.getContext("2d");
      const statusEl = document.getElementById("vfStatus");
      const useOnlyBtn = document.getElementById("vfUseOnly");
      const addMeetingBtn = document.getElementById("vfAddMeeting");
      const img = new Image();
      let hoverRegion = null;
      let lockedRegion = null;
      img.onload = () => bctx.drawImage(img, 0, 0, {DISPLAY_SIDE}, {DISPLAY_SIDE});
      img.src = "{img_src}";

      function insidePolygon(x, y, vertices) {{
        let inside = false;
        for (let i = 0, j = vertices.length - 1; i < vertices.length; j = i++) {{
          const xi = vertices[i].x, yi = vertices[i].y;
          const xj = vertices[j].x, yj = vertices[j].y;
          const intersect = ((yi > y) !== (yj > y)) &&
            (x < (xj - xi) * (y - yi) / ((yj - yi) || 1e-9) + xi);
          if (intersect) inside = !inside;
        }}
        return inside;
      }}

      function drawRegion(region, locked=false) {{
        if (!region || !region.vertices.length) return;
        ctx.beginPath();
        ctx.moveTo(region.vertices[0].x, region.vertices[0].y);
        for (let i = 1; i < region.vertices.length; i++) {{
          ctx.lineTo(region.vertices[i].x, region.vertices[i].y);
        }}
        ctx.closePath();
        ctx.fillStyle = locked ? "rgba(120,120,120,0.28)" : "rgba(120,120,120,0.18)";
        ctx.strokeStyle = locked ? "rgba(80,80,80,0.9)" : "rgba(90,90,90,0.75)";
        ctx.lineWidth = locked ? 5 : 4;
        ctx.fill();
        ctx.stroke();
      }}

      function redraw() {{
        ctx.clearRect(0, 0, {DISPLAY_SIDE}, {DISPLAY_SIDE});
        drawRegion(hoverRegion, false);
        drawRegion(lockedRegion, true);
      }}

      function setActionButtonsEnabled(enabled) {{
        for (const btn of [useOnlyBtn, addMeetingBtn]) {{
          btn.disabled = !enabled;
          btn.style.opacity = enabled ? "1" : "0.45";
          btn.style.cursor = enabled ? "pointer" : "not-allowed";
        }}
      }}

      overlay.addEventListener("mousemove", (event) => {{
        const rect = overlay.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        hoverRegion = null;
        for (const region of regions) {{
          if (insidePolygon(x, y, region.vertices)) {{
            hoverRegion = region;
            break;
          }}
        }}
        statusEl.textContent = hoverRegion
          ? "Hovering: Region " + hoverRegion.label
          : (lockedRegion ? "Selected: Region " + lockedRegion.label : "Hovering: none");
        redraw();
      }});

      overlay.addEventListener("mouseleave", () => {{
        hoverRegion = null;
        statusEl.textContent = lockedRegion ? "Selected: Region " + lockedRegion.label : "Hovering: none";
        redraw();
      }});

      overlay.addEventListener("click", () => {{
        if (!hoverRegion) return;
        lockedRegion = hoverRegion;
        statusEl.textContent = "Selected: Region " + lockedRegion.label;
        setActionButtonsEnabled(true);
        redraw();
      }});

      function submitRegion(mode) {{
        if (!lockedRegion) return;
        const url = new URL(window.parent.location.href);
        url.searchParams.set("vf_region", lockedRegion.id);
        url.searchParams.set("vf_region_label", lockedRegion.label);
        url.searchParams.set("vf_mode", mode);
        if (mode === "add") {{
          const labels = currentMeetingLabels.slice();
          if (!labels.includes(lockedRegion.label)) labels.push(lockedRegion.label);
          url.searchParams.set("vf_region_labels", labels.join("|"));
        }}
        url.searchParams.set("active_tool", "vertex");
        window.parent.location.replace(url.toString());
      }}

      useOnlyBtn.addEventListener("click", () => submitRegion("replace"));
      addMeetingBtn.addEventListener("click", () => submitRegion("add"));
    </script>
    """
    components.html(html, height=DISPLAY_SIDE + 150, width=DISPLAY_SIDE + 20)

def edge_options(e):
    root = getattr(e, "trueEdge", e)

    # If either side of this edge has been merged into a union, present it as an
    # edge of that union instead of the (now hidden) constituent region.
    consumed_to_union = {}
    for union in st.session_state.unions:
        for f in union["pair"]:
            consumed_to_union[id(f)] = union["face"]

    sides = []
    for face in (e.leftFace, e.reverse.leftFace):
        if face is None or not face.bounded:
            continue
        sides.append(consumed_to_union.get(id(face), face))

    # Both sides resolve to the same union -> this edge is interior to it; offer
    # nothing (you can't select an edge that lives inside a solid region).
    if len(sides) == 2 and sides[0] is sides[1]:
        return []

    opts = []
    seen = set()
    for face in sides:
        if id(face) in seen:
            continue
        seen.add(id(face))
        segs = [x for x in face.edges
                if getattr(x, "trueEdge", x) == root
                or getattr(x.reverse, "trueEdge", x.reverse) == root]
        if segs:
            opts.append(EdgeSel(segs, face, f"edge of {face.letter}"))
    if len(opts) == 2 and len(opts[0].segments) == len(opts[1].segments):
        na, nb = opts[0].owner.letter, opts[1].owner.letter
        return [EdgeSel(opts[0].segments, None, f"edge between {na} and {nb}")]
    return opts

def allowed_selection_kinds(tool, modes, sig):
    """Which click candidates make sense for the current tool action."""
    if tool is None:
        return {"vertex", "angle", "region", "edge"}
    if tool == "vertex":
        return {"region"}
    if tool == "neighbors":
        action = modes.get("neighbor_action")
        if action == "vertices": return {"vertex"}
        if action == "edges": return {"edge"}
        if action in ("region_edge", "region_vertex"): return {"region"}
        if action == "ordered":
            if len(sig["regions"]) == 1 and len(sig["vertices"]) == 0:
                return {"vertex"}
            if len(sig["vertices"]) == 1 and len(sig["regions"]) == 0:
                return {"region"}
            if sig["n"] == 0:
                return {"region", "vertex"}
            return set()
        return set()
    if tool == "draw line":
        action = modes.get("draw_action")
        if action in ("segment_vertices", "ray_vertex"):
            return {"vertex"}
        if action in ("segment_edge", "line_edge"):
            return {"edge"}
        return set()
    if tool == "intersect":
        return set()
    if tool == "merge":
        return {"region"}
    if tool == "measure":
        action = modes.get("measure_action")
        if action == "length_vertices": return {"vertex"}
        if action == "angle": return {"angle"}
        if action in ("area", "sides"): return {"region"}
        return set()
    if tool == "sort":
        action = modes.get("sort_action")
        if action in ("left_right", "bottom_top", "distance"):
            return {"vertex"}
        if action in ("angle", "area"):
            return {"region"}
        return set()
    return {"vertex", "angle", "region", "edge"}

# ============================================================
# 7. TOOL DEFINITIONS  (seven verbs)
# ============================================================
TOOLS = ["vertex", "neighbors", "draw line", "intersect", "merge", "measure", "sort"]

TOOL_LABELS = {
    "vertex":    "Vertex",
    "neighbors": "Neighbors",
    "draw line": "Draw Line",
    "intersect": "Intersect",
    "merge":     "Merge",
    "measure":   "Measure",
    "sort":      "Sort",
}

INSTRUCTIONS = {
    "vertex": "Choose one region for one of its vertices, or choose two or more regions for their meeting vertex.",
    "neighbors": "Choose the neighbor question you want to ask, then select the needed object(s).",
    "draw line": "Choose the kind of helper line you want, then select the needed vertex/edge.",
    "intersect": "Choose a drawn line and the intersection question.",
    "merge": "Choose two neighboring regions to merge into one solid region.",
    "measure": "Choose what to measure, then select the needed object(s).",
    "sort": "Choose the ordering you want, then select the objects to sort.",
}

NEIGHBOR_ACTIONS = {
    "vertices": "Find regions meeting at a vertex",
    "edges": "Find regions sharing the selected edge",
    "region_edge": "Find regions bordering a region along an edge",
    "region_vertex": "Find regions touching a region at a vertex",
    "ordered": "Walk from a vertex around a region",
}

DRAW_ACTIONS = {
    "segment_vertices": "Draw a segment between two vertices",
    "ray_vertex": "Draw a ray from one vertex",
    "segment_edge": "Trace one edge as a segment",
    "line_edge": "Extend one edge as a full line",
}

MEASURE_ACTIONS = {
    "length_vertices": "Measure distance between two vertices",
    "length_line": "Measure a drawn segment",
    "angle": "Measure saved angle(s)",
    "area": "Measure area of one region",
    "sides": "Count sides of one region",
}

SORT_ACTIONS = {
    "angle": "Sort a region's vertices by angle",
    "area": "Sort regions by area",
    "left_right": "Sort vertices left to right",
    "bottom_top": "Sort vertices bottom to top",
    "distance": "Sort vertices by distance from a reference vertex",
}

def validate(tool, modes):
    s = sel_sig()
    nR, nV, nE, nA, nF = (len(s["regions"]), len(s["vertices"]),
                          len(s["edges"]), len(s["angles"]), len(s["frame"]))

    if tool == "vertex":
        if nF == 1 and s["n"] == 1:        return (False, "Clear the frame selection and choose a region instead.")
        if nR == 1 and s["n"] == 1:
            if st.session_state.get("vertex_region_mode") == "meeting":
                return (False, "Add at least one more region for the meeting vertex.")
            descriptions = modes.get("descriptions", [])
            if not descriptions:
                return (False, "Choose at least one vertex description.")
            if len(descriptions) > 2:
                return (False, "Choose at most two vertex descriptions.")
            matches = vertex_by_descriptions(s["regions"][0], descriptions)
            if not matches:
                return (False, "No vertex in this region matches those descriptions. Reselect the region or change descriptions.")
            if len(matches) > 1:
                return (False, "More than one vertex matches. Add another description or choose a different region.")
            return (True, "")
        if nR >= 2 and nR == s["n"]:
            matches = meeting_vertex_candidates(s["regions"], modes.get("on_frame", False))
            if len(matches) == 1:
                return (True, "")
            if len(matches) == 0:
                if modes.get("has_frame_candidates"):
                    return (False, "These regions do not identify a meeting vertex yet. Add another region or change the frame setting.")
                return (False, "These regions do not identify a meeting vertex yet. Add another region.")
            return (False, "These regions still identify more than one meeting vertex. Add another region.")
        return (False, "")

    if tool == "neighbors":
        action = modes.get("neighbor_action")
        if not action: return (False, "Choose a neighbor action.")
        if action == "vertices":
            return (nV == 1 and s["n"] == 1, "Select a vertex.")
        if action == "edges":
            return (nE == 1 and s["n"] == 1, "Select an edge.")
        if action in ("region_edge", "region_vertex"):
            return (nR == 1 and s["n"] == 1, "Select one region.")
        if action == "ordered":
            ready = (
                nR == 1 and nV == 1 and s["n"] == 2
                and vertex_in_region(s["vertices"][0], s["regions"][0])
            )
            return (ready, "Select one region and one of its vertices.")
        return (False, "")

    if tool == "draw line":
        action = modes.get("draw_action")
        if not action: return (False, "Choose a line action.")
        if action == "segment_vertices":
            return (s["n"] == 2 and nV == 2, "Select exactly two vertices.")
        if action == "ray_vertex":
            return (s["n"] == 1 and nV == 1, "Select exactly one vertex.")
        if action in ("segment_edge", "line_edge"):
            return (s["n"] == 1 and nE == 1, "Select exactly one edge.")
        return (False, "")

    if tool == "intersect":
        return (len(st.session_state.lines) > 0, "Draw a line first.")

    if tool == "merge":
        return (s["n"] == 2 and nR == 2, "Need exactly 2 regions.")

    if tool == "measure":
        action = modes.get("measure_action")
        if not action: return (False, "Pick what to measure.")
        if action == "length_vertices":
            return (nV == 2 and s["n"] == 2, "Select exactly two vertices.")
        if action == "length_line":
            return (modes.get("line") is not None, "Choose a drawn segment.")
        if action == "angle":
            return (nA >= 1 and nA == s["n"], "Select one or more saved angles (a1, a2…).")
        if action in ("area", "sides"):
            return (nR == 1 and s["n"] == 1, "Select one region.")
        return (False, "")

    if tool == "sort":
        by = modes.get("sort_action")
        if not by: return (False, "Pick how to order them.")
        if by == "angle":
            return (nR == 1 and s["n"] == 1,
                    "Select one region; its vertices will be ordered by angle.")
        if by == "area":
            return (nR >= 2 and nR == s["n"], "Select 2+ regions.")
        if by in ("left_right", "bottom_top"):
            return (nV >= 2 and nV == s["n"], "Select 2+ vertices.")
        if by == "distance":
            return (nV >= 3 and nV == s["n"],
                    "Select the reference vertex FIRST, then 2+ more vertices.")
        return (False, "")
    return (False, "")

# ============================================================
# 8. EXECUTION + PROGRAM TRACE
# ============================================================
def add_program(line):
    st.session_state.program.append(line)
def add_log(text):     st.session_state.log.append(text)
def add_translation(text): st.session_state.translations.append(text)

# ---- single-step tool UNDO -------------------------------------------------
_UNDO_KEYS = ["selection", "annotations", "lines", "angles", "named_edges",
              "unions", "union_consumed", "vertex_names", "vertex_descriptions",
              "point_names", "counters", "program", "log", "translations",
              "vertex_region_mode", "vf_meeting_region_labels",
              "pending_confirm_vertex_id", "pending_confirm_kind", "pending_confirm_id",
              "pending_confirm_action", "pending_confirm_obj", "result_summary"]

def push_undo():
    """Snapshot the tracked state BEFORE creating a durable tool step."""
    snap = {}
    for k in _UNDO_KEYS:
        val = st.session_state.get(k)
        if isinstance(val, dict):
            snap[k] = dict(val)
        elif isinstance(val, list):
            snap[k] = list(val)
        elif isinstance(val, set):
            snap[k] = set(val)
        else:
            snap[k] = val
    st.session_state.undo_stack.append(snap)
    if len(st.session_state.undo_stack) > 50:
        st.session_state.undo_stack.pop(0)

def undo_last():
    if not st.session_state.undo_stack:
        return
    snap = st.session_state.undo_stack.pop()
    for k, v in snap.items():
        st.session_state[k] = v
    st.session_state.click_targets = None
    st.session_state.pending_angle_vertex = None
    persist_and_rerun()

def clear_action_selection(clear_result=False):
    """Clear temporary inputs after a tool action has finished."""
    st.session_state.selection = []
    st.session_state.vertex_region_mode = None
    st.session_state.vf_meeting_region_labels = []
    st.session_state.click_targets = None
    st.session_state.pending_angle_vertex = None
    st.session_state.pending_confirm_vertex_id = None
    st.session_state.pending_confirm_kind = None
    st.session_state.pending_confirm_id = None
    st.session_state.pending_confirm_action = None
    st.session_state.pending_confirm_obj = None
    st.session_state.last_click = None
    st.session_state.vf_last_selected_region = None
    if clear_result:
        st.session_state.result_summary = None

def clear_selection_if_action_changed(key, value):
    previous = st.session_state.get(key)
    st.session_state[key] = value
    if previous is not None and previous != value:
        clear_action_selection(clear_result=True)
        persist_and_rerun()

def restore_action_state(tool, action):
    if not action:
        return
    key_by_tool = {
        "neighbors": "rad_neighbor_action",
        "draw line": "rad_draw_action",
        "measure": "rad_measure_action",
        "sort": "rad_sort_action",
    }
    last_key_by_tool = {
        "neighbors": "last_neighbor_action",
        "draw line": "last_draw_action",
        "measure": "last_measure_action",
        "sort": "last_sort_action",
    }
    key = key_by_tool.get(tool)
    if key:
        st.session_state[key] = action
    last_key = last_key_by_tool.get(tool)
    if last_key:
        st.session_state[last_key] = action

def region_letters_for_vertex(v):
    letters = []
    for face in T.neighbors(v):
        label = getattr(face, "letter", "?") if getattr(face, "bounded", True) else "Outside"
        if label not in letters:
            letters.append(label)
    return letters

def vertex_meeting_label(v):
    letters = region_letters_for_vertex(v)
    return f"meeting vertex of regions {', '.join(letters)}" if letters else "selected vertex"

def region_label(face):
    return getattr(face, "letter", "?") if getattr(face, "bounded", True) else "Outside"

def display_item(o):
    if is_region(o):
        return region_label(o)
    if is_vertex(o):
        nm = vertex_name(o, create=False)
        return nm if nm else vertex_meeting_label(o)
    if is_angle(o):
        return angle_name(o)
    if is_edgesel(o):
        return edge_name(o) or o.text
    if isinstance(o, bool):
        return "Yes" if o else "No"
    return str(o)

def summary_collection(label, items):
    values = [display_item(item) for item in items]
    return f"{label}: {{{', '.join(values) if values else 'none'}}}"

def summary_order(label, items):
    values = [display_item(item) for item in items]
    return f"{label}: {' → '.join(values) if values else 'none'}"

def summary_value(label, value):
    return f"{label}: {display_item(value)}"

def visualize_result(result):
    if is_angle(result) or is_edgesel(result):
        return
    if isinstance(result, (list, tuple, set)):
        for r in result:
            visualize_result(r)
        return
    if result is None or isinstance(result, (bool, int, float, str)):
        return
    if is_vertex(result):
        vertex_name(result)
    elif is_region(result) and getattr(result, "bounded", False):
        st.session_state.annotations.append(
            {"kind": "region", "obj": result, "color": GRAY_SELECTION})

def finish(tool, call_str, result, assign_prefix="r", visualize=True, translation=None):
    if visualize:
        visualize_result(result)
    if assign_prefix:
        if assign_prefix == "v" and is_vertex(result):
            var = vertex_name(result)
        else:
            var = next_name(assign_prefix)
        add_program(f"{var} = {call_str}")
    else:
        add_program(call_str)
    add_log(f"`{call_str}` → `{raw_output(result)}`")
    if callable(translation):
        add_translation(translation(var if assign_prefix else None))
    elif translation:
        add_translation(translation)
    else:
        add_translation(f"{tool.title()} returned {describe(result)}.")
    clear_action_selection()
    persist_and_rerun()

def face_vertices_unique(face):
    seen = set()
    out = []
    for v in face.vertices:
        key = id(v)
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out

def filter_vertices_by_description(face, vertices, description):
    if not vertices:
        return []
    eps = 1e-9
    if description == "leftmost":
        val = min(v.p.x for v in vertices)
        return [v for v in vertices if abs(v.p.x - val) <= eps]
    if description == "rightmost":
        val = max(v.p.x for v in vertices)
        return [v for v in vertices if abs(v.p.x - val) <= eps]
    if description == "topmost":
        val = max(v.p.y for v in vertices)
        return [v for v in vertices if abs(v.p.y - val) <= eps]
    if description == "bottommost":
        val = min(v.p.y for v in vertices)
        return [v for v in vertices if abs(v.p.y - val) <= eps]
    if description in ("sharpest", "widest"):
        scored = [(Graph.angleAtFace(v, face), v) for v in vertices]
        target = min(a for a, _ in scored) if description == "sharpest" else max(a for a, _ in scored)
        return [v for a, v in scored if abs(a - target) <= 1e-9]
    return vertices

def vertex_by_descriptions(face, descriptions):
    candidates = face_vertices_unique(face)
    for description in descriptions:
        candidates = filter_vertices_by_description(face, candidates, description)
    return candidates

def vertex_label_from_descriptions(face, descriptions):
    display = {
        "leftmost": "leftmost",
        "rightmost": "rightmost",
        "topmost": "topmost",
        "bottommost": "bottommost",
        "sharpest": "sharpest angle",
        "widest": "widest angle",
    }
    return " and ".join(display.get(p, p) for p in descriptions) + f" vertex of Region {face.letter}"

def meeting_vertex_candidates(regions, on_frame=False):
    if len(regions) < 2:
        return []
    candidates = face_vertices_unique(regions[0])
    out = []
    for v in candidates:
        if not all(v in face_vertices_unique(face) for face in regions):
            continue
        touches_frame = any(not getattr(face, "bounded", True) for face in getattr(v, "faces", []))
        if bool(touches_frame) != bool(on_frame):
            continue
        out.append(v)
    return out

if "vf_region" in st.query_params:
    selected_region = find_selectable_region(st.query_params.get("vf_region"))
    if selected_region is None:
        selected_region = find_selectable_region_by_label(st.query_params.get("vf_region_label", ""))
    vf_mode = st.query_params.get("vf_mode", "replace")
    labels_param = st.query_params.get("vf_region_labels", "")
    clear_query_keys("vf_region", "vf_region_label", "vf_mode", "vf_region_labels", "active_tool")
    if st.session_state.active_tool != "vertex":
        clear_action_selection(clear_result=True)
    st.session_state.active_tool = "vertex"
    if selected_region is not None:
        selected_label = getattr(selected_region, "letter", "")
        if vf_mode == "add":
            st.session_state.vertex_region_mode = "meeting"
            labels = [label for label in labels_param.split("|") if label] if labels_param else []
            if not labels:
                labels = list(st.session_state.get("vf_meeting_region_labels", []))
            existing_region_labels = [
                getattr(o, "letter", "")
                for o in st.session_state.selection
                if o != "frame" and is_region(o)
            ]
            for label in existing_region_labels:
                if label and label not in labels:
                    labels.append(label)
            if selected_label and selected_label not in labels:
                labels.append(selected_label)
            st.session_state.vf_meeting_region_labels = labels
            st.session_state.selection = regions_from_labels(labels)
        else:
            st.session_state.vertex_region_mode = "single_vertex"
            st.session_state.vf_meeting_region_labels = []
            st.session_state.selection = [selected_region]
        st.session_state.click_targets = None
        st.session_state.pending_angle_vertex = None
        st.session_state.last_click = None
        st.session_state.vf_last_selected_region = getattr(selected_region, "letter", "")
    persist_and_rerun()

if "pick_kind" in st.query_params and "pick_id" in st.query_params:
    pick_kind = st.query_params.get("pick_kind")
    pick_id = st.query_params.get("pick_id")
    active_tool_param = st.query_params.get("active_tool")
    pick_action = st.query_params.get("pick_action")
    clear_query_keys("pick_kind", "pick_id", "pick_action", "active_tool")
    if active_tool_param in TOOLS:
        if st.session_state.active_tool != active_tool_param:
            clear_action_selection(clear_result=True)
        st.session_state.active_tool = active_tool_param
        restore_action_state(active_tool_param, pick_action)
    if pick_kind == "vertex":
        v = find_selectable_vertex(pick_id)
        if v is not None:
            st.session_state.pending_confirm_kind = "vertex"
            st.session_state.pending_confirm_id = pick_id
            st.session_state.pending_confirm_action = pick_action
            st.session_state.pending_confirm_obj = v
            st.session_state.pending_confirm_vertex_id = pick_id
            st.session_state.click_targets = None
            st.session_state.pending_angle_vertex = None
            st.session_state.last_click = None
            st.session_state.result_summary = None
    elif pick_kind == "region":
        f = find_selectable_region(pick_id)
        if f is not None:
            st.session_state.pending_confirm_kind = "region"
            st.session_state.pending_confirm_id = pick_id
            st.session_state.pending_confirm_action = pick_action
            st.session_state.pending_confirm_obj = f
            st.session_state.pending_confirm_vertex_id = None
            st.session_state.click_targets = None
            st.session_state.pending_angle_vertex = None
            st.session_state.last_click = None
            st.session_state.result_summary = None
    elif pick_kind == "edge":
        e = find_selectable_edge(pick_id)
        if e is not None:
            st.session_state.pending_confirm_kind = "edge"
            st.session_state.pending_confirm_id = pick_id
            st.session_state.pending_confirm_action = pick_action
            st.session_state.pending_confirm_obj = e
            st.session_state.pending_confirm_vertex_id = None
            st.session_state.click_targets = None
            st.session_state.pending_angle_vertex = None
            st.session_state.last_click = None
            st.session_state.result_summary = None
    persist_and_rerun()

if st.query_params.get("active_tool") in TOOLS:
    requested_tool = st.query_params.get("active_tool")
    if st.session_state.active_tool != requested_tool:
        clear_action_selection(clear_result=True)
    st.session_state.active_tool = requested_tool
    clear_query_keys("active_tool")
    persist_and_rerun()

if (
    st.session_state.get("vertex_region_mode") == "meeting"
    and st.session_state.get("vf_meeting_region_labels")
):
    restored_regions = regions_from_labels(st.session_state.vf_meeting_region_labels)
    current_region_labels = [
        getattr(o, "letter", "")
        for o in st.session_state.selection
        if o != "frame" and is_region(o)
    ]
    restored_labels = [getattr(o, "letter", "") for o in restored_regions]
    if restored_labels and current_region_labels != restored_labels:
        st.session_state.selection = restored_regions

# ---- ranking display (shared by the Sort tool) ------------------------------
def _rank_value(it, by, ref):
    if by == "distance":   return map_helpers.dist(it, ref)
    if by == "left_right": return map_helpers.x_of(it)
    if by == "bottom_top": return map_helpers.y_of(it)
    if by == "area":       return map_helpers.area(it)
    if by == "angle":      return map_helpers.angle_at(it, ref) * 180.0 / math.pi
    return 0

def _rank_fmt(by, v):
    return f"{v:.3f}"

def ranking_finish(call_str, result, by, ref):
    add_program(call_str + "   # smallest → largest")
    ordered = "  →  ".join(
        f"{code_name(it)} ({_rank_fmt(by, _rank_value(it, by, ref))})" for it in result)
    add_log(f"`{call_str}` → `[{ordered}]`")
    translated_order = " -> ".join(display_item(it) for it in result)
    add_translation(f"Sorted from smallest to largest: {translated_order}.")
    clear_action_selection()
    persist_and_rerun()

def run_tool(tool, modes):
    sel = st.session_state.selection
    s = sel_sig()
    try:
        # ---- VERTEX --------------------------------------------------------
        if tool == "vertex":
            if s["frame"]:
                which = modes["which"]
                result = T.vertex("frame", which=which)
                if not isinstance(result, list):
                    description = f"the {which} vertex of the frame"
                    set_vertex_description(result, description)
                else:
                    description = f"all {which} vertices of the frame"
                finish(tool, f'vertex("frame", which="{which}")', result,
                       "v" if not isinstance(result, list) else "r",
                       translation=lambda name: label_vertex_sentence(description, name))
            elif len(s["regions"]) >= 2:
                onf = modes["on_frame"]
                matches = meeting_vertex_candidates(s["regions"], onf)
                if len(matches) != 1:
                    st.error("Please choose regions that identify exactly one meeting vertex.")
                    return
                result = matches[0]
                args = ", ".join(o.letter for o in s["regions"])
                region_list = ", ".join(f"Region {o.letter}" for o in s["regions"])
                frame_text = " on the frame" if onf else ""
                description = f"the meeting vertex of {region_list}{frame_text}"
                set_vertex_description(result, description)
                finish(tool, f"vertex({args}, on_frame={onf})", result, "v",
                       translation=lambda name: label_vertex_sentence(description, name))
            else:
                reg = s["regions"][0]
                descriptions = modes["descriptions"]
                matches = vertex_by_descriptions(reg, descriptions)
                if len(matches) != 1:
                    st.error("Please choose descriptions that identify exactly one vertex.")
                    return
                result = matches[0]
                which = " and ".join(descriptions)
                label = vertex_label_from_descriptions(reg, descriptions)
                visualize_result(result)
                var = vertex_name(result)
                set_vertex_description(result, label)
                call_str = f'vertex({reg.letter}, which="{which}")'
                add_program(f"{var} = {call_str}")
                add_log(f"`{call_str}` → `{var}`")
                add_translation(label_vertex_sentence(label, var))
                clear_action_selection()
                persist_and_rerun()

        # ---- NEIGHBORS -----------------------------------------------------
        elif tool == "neighbors":
            action = modes["neighbor_action"]
            if action == "edges":
                seen, result, names = set(), [], []
                for es in s["edges"]:
                    for seg in es.segments:
                        for face in (seg.leftFace, seg.reverse.leftFace):
                            if face is None or not getattr(face, "bounded", False):
                                continue
                            if id(face) not in seen:
                                seen.add(id(face))
                                result.append(face)
                    names.append(edge_name(es) or "edge")
                call = (f"neighbors([{', '.join(names)}])"
                        if len(names) > 1 else f"neighbors({names[0]})")
                st.session_state.result_summary = summary_collection("Regions", result)
                finish(tool, call, result)

            elif action == "vertices":
                seen, result = set(), []
                for v in s["vertices"]:
                    for face in T.neighbors(v):
                        if id(face) not in seen:
                            seen.add(id(face))
                            result.append(face)
                names = [vertex_ref(v) for v in s["vertices"]]
                call = (f"neighbors([{', '.join(names)}])"
                        if len(names) > 1 else f"neighbors({names[0]})")
                st.session_state.result_summary = summary_collection("Regions", result)
                finish(tool, call, result)

            elif action == "ordered":
                reg, vtx = s["regions"][0], s["vertices"][0]
                ccw = modes.get("ccw", True)
                result = T.neighbors(reg, "ordered", start=vtx, go_counterclockwise=ccw)
                st.session_state.result_summary = summary_order("Region order", result)
                finish(tool, f'neighbors({reg.letter}, "ordered", start={code_name(vtx)}, '
                             f"go_counterclockwise={ccw})", result)

            else:
                reg = s["regions"][0]
                kind = "edge" if action == "region_edge" else "vertex"
                result = T.neighbors(reg, kind)
                st.session_state.result_summary = summary_collection("Regions", result)
                finish(tool, f'neighbors({reg.letter}, "{kind}")', result)

        # ---- DRAW LINE -----------------------------------------------------
        elif tool == "draw line":
            action = modes["draw_action"]
            name = next_name("L")
            if action == "ray_vertex":
                d = modes["ray_direction"]
                line = T.draw(sel[0], d)
                call = f'draw({vertex_ref(sel[0])}, "{d}")'
                draw_log = draw_log_sentence(name=name, action=action, start=sel[0], direction=d)
            elif action in ("segment_edge", "line_edge"):
                edge = s["edges"][0]
                va, vb = edgesel_endpoints(s["edges"][0])
                kind = "full" if action == "line_edge" else "segment"
                line = T.draw(va, vb, kind=kind)
                call = f'draw({vertex_ref(va)}, {vertex_ref(vb)}, kind="{kind}")  # along {code_name(s["edges"][0])}'
                draw_log = draw_log_sentence(name=name, action=action, start=va, end=vb, edge=edge, kind=kind)
            else:
                kind = "segment"
                line = T.draw(sel[0], sel[1], kind=kind)
                call = f'draw({vertex_ref(sel[0])}, {vertex_ref(sel[1])}, kind="{kind}")'
                draw_log = draw_log_sentence(name=name, action=action, start=sel[0], end=sel[1], kind=kind)
            st.session_state.lines.append((name, line))
            st.session_state.annotations.append({"kind": "line", "line": line, "label": name})
            add_program(f"{name} = {call}")
            add_log(f"`{name} = {call}` → `status=drawn`")
            add_translation(draw_log)
            st.session_state.result_summary = f"Drawn line: {name}"
            clear_action_selection()
            persist_and_rerun()

        # ---- INTERSECT -----------------------------------------------------
        elif tool == "intersect":
            lname, line = modes["line"]
            if modes["target"] == "faces":
                result = T.intersect(line, "faces")
                st.session_state.result_summary = summary_collection("Regions", result)
                finish(tool, f'intersect({lname}, "faces")', result, visualize=False,
                       translation=intersect_translation(lname, "faces", result))
            else:
                tname, tline = modes["target"]
                result = T.intersect(line, tline)
                st.session_state.result_summary = summary_value("Result", result)
                finish(tool, f"intersect({lname}, {tname})", result, visualize=False,
                       translation=intersect_translation(lname, modes["target"], result))

        # ---- MERGE ---------------------------------------------------------
        elif tool == "merge":
            fa, fb = s["regions"][0], s["regions"][1]
            fu = T.merge(fa, fb)
            uname = next_name("U")
            fu.letter = uname
            lp, _d = Graph.LetterPointFace(fu)
            st.session_state.unions.append(
                {"name": uname, "face": fu, "pair": (fa, fb),
                 "label_xy": DrawGraph.V2P(lp)})
            st.session_state.union_consumed += [fa, fb]
            add_program(f"{uname} = merge({fa.letter}, {fb.letter})")
            add_log(f"`merge({fa.letter}, {fb.letter})` → `{uname}`")
            add_translation(f"Merged Region {fa.letter} and Region {fb.letter} into new region {uname}.")
            st.session_state.result_summary = f"New region: {uname}"
            clear_action_selection()
            persist_and_rerun()

        # ---- MEASURE (one thing → one number) ------------------------------
        elif tool == "measure":
            action = modes["measure_action"]

            if action == "length_vertices":
                p, q = s["vertices"][0], s["vertices"][1]
                val = T.measure(p, q, what="length")
                st.session_state.result_summary = f"Length: {round(val, 4)}"
                finish(tool, f'measure({code_name(p)}, {code_name(q)}, what="length")',
                       round(val, 4))

            elif action == "length_line":
                lname, line = modes["line"]
                val = T.measure(line, what="length")
                st.session_state.result_summary = f"Length: {round(val, 4)}"
                finish(tool, f'measure({lname}, what="length")', round(val, 4),
                       visualize=False)

            elif action == "angle":
                # Measure EACH selected angle: one program line + one log line each.
                for a in s["angles"]:
                    val = T.measure(a.vertex, a.face, what="angle")
                    aname = angle_name(a)
                    call_str = f'measure({aname}, what="angle")'
                    var = next_name("r")
                    add_program(f"{var} = {call_str}")
                    add_log(f"`{call_str}` → `{round(val, 2)}`")
                    add_translation(f"Measured angle {aname}: {round(val, 2)} degrees.")
                angle_values = [
                    f"{angle_name(a)} = {round(T.measure(a.vertex, a.face, what='angle'), 2)}°"
                    for a in s["angles"]
                ]
                st.session_state.result_summary = f"Angles: {{{', '.join(angle_values)}}}"
                clear_action_selection()
                persist_and_rerun()

            else:  # area, sides
                reg = s["regions"][0]
                val = T.measure(reg, what=action)
                label = "Area" if action == "area" else "Sides"
                st.session_state.result_summary = f"{label}: {val}"
                finish(tool, f'measure({reg.letter}, what="{action}")', val)

        # ---- SORT (several things → ordered) --------------------------------
        elif tool == "sort":
            by = modes["sort_action"]

            if by == "angle":
                reg = s["regions"][0]
                region_vertices = T.vertex(reg, which="all")
                result = T.sort(region_vertices, by="angle", reference=reg)
                call_str = (f'sort(vertex({reg.letter}, which="all"), by="angle", '
                            f'reference={reg.letter})')

                # Annotate an interior ARC for every vertex (not a raw vertex dot),
                # reusing any angle already saved for that vertex+region.
                for vertex in result:
                    existing = next(
                        (nm for nm, a_sel in st.session_state.angles
                         if a_sel.vertex is vertex and a_sel.face is reg),
                        None)
                    if existing is None:
                        aname = next_name("a")
                        a_sel = AngleSel(vertex, reg)
                        st.session_state.angles.append((aname, a_sel))
                        st.session_state.annotations.append(
                            {"kind": "angle", "vertex": vertex, "face": reg, "label": aname})

                st.session_state.result_summary = summary_order("Vertex order", result)
                ranking_finish(call_str, result, "angle", reg)

            elif by == "area":
                regs = list(s["regions"])
                result = T.sort(regs, by="area")
                arg = ", ".join(o.letter for o in regs)
                st.session_state.result_summary = summary_order("Region order", result)
                ranking_finish(f'sort([{arg}], by="area")', result, "area", None)

            elif by in ("left_right", "bottom_top"):
                pts = list(s["vertices"])
                result = T.sort(pts, by=by)
                arg = ", ".join(code_name(o) for o in pts)
                st.session_state.result_summary = summary_order("Vertex order", result)
                ranking_finish(f'sort([{arg}], by="{by}")', result, by, None)

            else:  # distance from the first-selected vertex
                ref, rest = s["vertices"][0], s["vertices"][1:]
                result = T.sort(rest, by="distance", reference=ref)
                arg = ", ".join(code_name(o) for o in rest)
                st.session_state.result_summary = summary_order("Vertex order", result)
                ranking_finish(
                    f'sort([{arg}], by="distance", reference={code_name(ref)})',
                    result, "distance", ref)

    except Exception as ex:
        add_log(f"❌ **{tool}** failed: {ex}")
        clear_action_selection()
        persist_and_rerun()

# ============================================================
# 9. LAYOUT  (LEFT: tools/selection/run | MIDDLE: diagram+selection+saved |
#             RIGHT: quick actions + scratch pad + program + output)
# ============================================================
col_ctrl, col_map, col_io = st.columns([4, 5, 4], gap="medium")

# ----------------------------------------------------------------------------
# LEFT PANEL — TOOLS + current selection + active tool config + RUN
# ----------------------------------------------------------------------------
with col_ctrl:
    st.subheader("Tools")
    tcols = st.columns(2)
    for i, t_name in enumerate(TOOLS):
        is_active = (st.session_state.active_tool == t_name)
        display = TOOL_LABELS.get(t_name, t_name)
        label = f"✅ {display}" if is_active else display
        if tcols[i % 2].button(label, key=f"tool_{t_name}", use_container_width=True):
            if st.session_state.active_tool != t_name:
                clear_action_selection(clear_result=True)
            st.session_state.active_tool = t_name
            if t_name != "vertex":
                st.session_state.vertex_region_mode = None
                st.session_state.vf_meeting_region_labels = []
            persist_and_rerun()

    tool = st.session_state.active_tool
    modes = {}

    # --- CURRENT STEP SELECTION ---
    st.subheader("Current Step Selection")
    if st.session_state.selection:
        st.markdown("\n".join(f"- {describe(o)}" for o in st.session_state.selection))
    else:
        st.caption("(select inputs for the current tool step)")
    if st.session_state.get("vf_last_selected_region") and tool == "vertex":
        st.caption(f"Last Confirmed Region: {st.session_state.vf_last_selected_region}")

    if tool:
        display = TOOL_LABELS.get(tool, tool)
        st.markdown(f"### {display}")
        st.info(INSTRUCTIONS[tool])
        status_already_shown = False

        s = sel_sig()

        if tool == "vertex":
            if s["frame"]:
                st.info("Frame selection is disabled for Vertex. Clear the selection and choose a region.")
            elif len(s["regions"]) >= 2:
                letters = ", ".join(r.letter for r in s["regions"])
                st.markdown("**Meeting vertex regions:**")
                st.markdown("\n".join(f"- Region {r.letter}" for r in s["regions"]))
                st.caption("To include another region, hover/click it on the map and choose Confirm: add region for meeting vertex.")
                frame_matches = meeting_vertex_candidates(s["regions"], True)
                modes["has_frame_candidates"] = bool(frame_matches)
                if frame_matches:
                    non_frame_matches = meeting_vertex_candidates(s["regions"], False)
                    default_on_frame = not non_frame_matches
                    modes["on_frame"] = st.radio(
                        "Is the meeting vertex on the frame?", [False, True],
                        index=1 if default_on_frame else 0,
                        format_func=lambda b: "Yes" if b else "No",
                        horizontal=True, key="rad_vtx_onframe")
                else:
                    modes["on_frame"] = False
                matches = meeting_vertex_candidates(s["regions"], modes["on_frame"])
                if len(matches) == 1:
                    st.success(f"Ready: unique meeting vertex of regions {letters}.")
                    status_already_shown = True
                elif len(matches) == 0:
                    if modes["has_frame_candidates"]:
                        st.warning("No unique meeting vertex yet. Add another region, remove a region, or change the frame setting.")
                    else:
                        st.warning("No unique meeting vertex yet. Add another region or remove a region.")
                    status_already_shown = True
                else:
                    st.warning(f"Still ambiguous: these regions match {len(matches)} meeting vertices. Add another region.")
                    status_already_shown = True
            else:
                if len(s["regions"]) == 1:
                    if st.session_state.get("vertex_region_mode") == "meeting":
                        st.markdown("**Meeting vertex regions:**")
                        st.markdown(f"- Region {s['regions'][0].letter}")
                        st.info("Add at least one more region for the meeting vertex.")
                        st.caption("Hover/click another region on the map and choose Confirm: add region for meeting vertex.")
                        modes["descriptions"] = []
                    else:
                        st.caption("Region selected. Which vertex do you want?")
                        st.caption("If this is the wrong region, choose another region and click Confirm: use this region for a vertex. To build a meeting vertex, choose another region and click Confirm: add region for meeting vertex.")
                        modes["descriptions"] = st.multiselect(
                            "Corner description",
                            ["leftmost", "rightmost", "topmost", "bottommost", "sharpest", "widest"],
                            max_selections=2,
                            key="multi_vtx_descriptions",
                            placeholder="Choose 1 or 2",
                        )
                        if modes["descriptions"]:
                            matches = vertex_by_descriptions(s["regions"][0], modes["descriptions"])
                            if len(matches) == 1:
                                st.success(f"Ready: {vertex_label_from_descriptions(s['regions'][0], modes['descriptions'])}")
                            elif len(matches) == 0:
                                st.error("No vertex in this region matches those descriptions. Reselect the region or change descriptions.")
                            else:
                                st.warning("More than one vertex matches. Add another description or choose a different region.")
                        else:
                            st.info("Choose at least one description after selecting a region.")
                        status_already_shown = True
                else:
                    modes["descriptions"] = []
                    st.info("Hover over the map to preview a region. Click to hold it, then choose how to use that region.")
                    status_already_shown = True

        elif tool == "neighbors":
            action = st.radio(
                "What do you want to find?",
                list(NEIGHBOR_ACTIONS.keys()),
                format_func=lambda k: NEIGHBOR_ACTIONS[k],
                key="rad_neighbor_action")
            clear_selection_if_action_changed("last_neighbor_action", action)
            modes["neighbor_action"] = action
            if action == "vertices":
                st.caption("Select a vertex.")
            elif action == "edges":
                st.caption("Select an edge.")
            elif action in ("region_edge", "region_vertex"):
                st.caption("Select one region.")
            else:
                st.caption("Select one region and one of its vertices.")
                modes["kind"] = "ordered"
                modes["ccw"] = st.radio(
                    "Walk direction", [True, False],
                    format_func=lambda b: "Counter-clockwise" if b else "Clockwise",
                    horizontal=True, key="rad_nbr_ccw")
            status_already_shown = True

        elif tool == "draw line":
            action = st.radio(
                "What do you want to draw?",
                list(DRAW_ACTIONS.keys()),
                format_func=lambda k: DRAW_ACTIONS[k],
                key="rad_draw_action")
            clear_selection_if_action_changed("last_draw_action", action)
            modes["draw_action"] = action
            if action == "ray_vertex":
                modes["ray_direction"] = st.radio("Direction", ["up", "down", "left", "right"],
                                                  horizontal=True, key="rad_raydir")
                st.caption("Select one vertex.")
            elif action in ("segment_edge", "line_edge"):
                st.caption("Select one edge.")
            else:
                st.caption("Select two vertices.")

        elif tool == "intersect":
            if st.session_state.lines:
                li = st.selectbox("Line to test", range(len(st.session_state.lines)),
                                  format_func=lambda i: st.session_state.lines[i][0],
                                  key="sel_line")
                modes["line"] = st.session_state.lines[li]
                choice = st.radio("Question", ["Which regions does it pass through?",
                                               "Does it cross another line?"],
                                  key="rad_intersect")
                if choice.startswith("Which"):
                    modes["target"] = "faces"
                else:
                    others = [j for j in range(len(st.session_state.lines)) if j != li]
                    if others:
                        lj = st.selectbox("Other line", others,
                                          format_func=lambda j: st.session_state.lines[j][0],
                                          key="sel_line2")
                        modes["target"] = st.session_state.lines[lj]
                    else:
                        st.warning("Draw a second line first.")
                        modes["target"] = None

        elif tool == "measure":
            action = st.radio(
                "What do you want to measure?",
                list(MEASURE_ACTIONS.keys()),
                format_func=lambda k: MEASURE_ACTIONS[k],
                key="rad_measure_action")
            clear_selection_if_action_changed("last_measure_action", action)
            modes["measure_action"] = action
            if action == "length_vertices":
                st.caption("Select exactly two vertices.")
            elif action == "length_line":
                segs = [(nm, ln) for nm, ln in st.session_state.lines
                        if ln.get("type") == "segment"]
                if segs:
                    idx = st.selectbox("Which drawn segment?", range(len(segs)),
                                       format_func=lambda i: segs[i][0],
                                       key="sel_len_line")
                    modes["line"] = segs[idx]
                else:
                    st.caption("Draw a segment first.")
            elif action == "angle":
                if s["angles"]:
                    st.caption(f"{len(s['angles'])} angle(s) selected — each will be measured.")
                else:
                    st.caption("Pick saved angles (a1, a2…) from the map panel, or make one: "
                               "click a vertex → 📐 Angle Here → region.")
            else:
                st.caption("Select one region.")

        elif tool == "sort":
            action = st.radio(
                "How do you want to order them?",
                list(SORT_ACTIONS.keys()),
                format_func=lambda k: SORT_ACTIONS[k],
                key="rad_sort_action")
            clear_selection_if_action_changed("last_sort_action", action)
            modes["sort_action"] = action
            if action == "angle":
                st.caption("Select one region.")
            elif action == "area":
                st.caption("Select two or more regions.")
            elif action == "distance":
                st.caption("Select the reference vertex first, then two or more vertices.")
            else:
                st.caption("Select two or more vertices.")

        # 'merge' has no modes.

        ready, msg = validate(tool, modes)
        if tool == "intersect" and modes.get("target") is None:
            ready = False
        if not ready and msg and not status_already_shown:
            st.warning(msg)
        if st.button("▶ Run", type="primary", disabled=not ready, use_container_width=True):
            push_undo()
            run_tool(tool, modes)
    else:
        st.caption("Pick a tool above to begin.")

# ----------------------------------------------------------------------------
# MIDDLE PANEL — DIAGRAM + selection-building buttons + saved objects
# ----------------------------------------------------------------------------
with col_map:
    display_img = render().resize((DISPLAY_SIDE, DISPLAY_SIDE), Image.Resampling.LANCZOS)
    current_sig = sel_sig()
    allowed_kinds = allowed_selection_kinds(st.session_state.active_tool, modes, current_sig)
    use_vertex_region_picker = (
        USE_URL_PICKERS
        and
        st.session_state.active_tool == "vertex"
        and current_sig["n"] == len(current_sig["regions"])
        and st.session_state.pending_angle_vertex is None
    )
    use_hover_selection_picker = (
        USE_URL_PICKERS
        and
        not use_vertex_region_picker
        and bool(allowed_kinds & {"vertex", "region", "edge"})
        and st.session_state.pending_angle_vertex is None
    )

    if use_vertex_region_picker:
        meeting_labels = list(st.session_state.get("vf_meeting_region_labels", []))
        if st.session_state.get("vertex_region_mode") == "meeting":
            for region in current_sig["regions"]:
                label = getattr(region, "letter", "")
                if label and label not in meeting_labels:
                    meeting_labels.append(label)
        vertex_region_picker(display_img, meeting_labels)
        coords = None
    elif use_hover_selection_picker:
        active_action = (
            modes.get("neighbor_action") or modes.get("draw_action")
            or modes.get("measure_action") or modes.get("sort_action")
        )
        hover_selection_picker(display_img, allowed_kinds, st.session_state.active_tool, active_action)
        coords = None
    else:
        coords = streamlit_image_coordinates(display_img, key="map_click")

    if coords is not None and coords != st.session_state.last_click:
        st.session_state.last_click = coords
        st.session_state.click_targets = hit_test(coords["x"], coords["y"])
        st.session_state.pending_angle_vertex = None

    pending_kind = st.session_state.get("pending_confirm_kind")
    pending_id = st.session_state.get("pending_confirm_id")
    pending_obj = st.session_state.get("pending_confirm_obj")
    if pending_kind == "vertex":
        pending_vertex = pending_obj if is_vertex(pending_obj) else find_selectable_vertex(pending_id)
        if pending_vertex is not None:
            pending_action = st.session_state.get("pending_confirm_action")
            if (
                st.session_state.get("active_tool") == "draw line"
                and pending_action == "segment_vertices"
            ):
                vertex_number = min(len(sel_sig()["vertices"]) + 1, 2)
                st.caption(f"Selected vertex {vertex_number}")
            else:
                st.caption(f"Selected vertex: {vertex_meeting_label(pending_vertex)}")
            if st.button("Confirm Vertex", use_container_width=True):
                if pending_vertex not in st.session_state.selection:
                    st.session_state.selection.append(pending_vertex)
                st.session_state.pending_confirm_kind = None
                st.session_state.pending_confirm_id = None
                st.session_state.pending_confirm_action = None
                st.session_state.pending_confirm_obj = None
                st.session_state.pending_confirm_vertex_id = None
                st.session_state.click_targets = None
                persist_and_rerun()
    elif pending_kind == "region":
        pending_region = pending_obj if is_region(pending_obj) else find_selectable_region(pending_id)
        if pending_region is not None:
            st.caption(f"Selected region: Region {pending_region.letter}")
            if st.button("Confirm Region", use_container_width=True):
                if pending_region not in st.session_state.selection:
                    st.session_state.selection.append(pending_region)
                st.session_state.pending_confirm_kind = None
                st.session_state.pending_confirm_id = None
                st.session_state.pending_confirm_action = None
                st.session_state.pending_confirm_obj = None
                st.session_state.click_targets = None
                persist_and_rerun()
    elif pending_kind == "edge":
        pending_edge = pending_obj if pending_obj is not None else find_selectable_edge(pending_id)
        if pending_edge is not None:
            opts = edge_options(pending_edge)
            st.caption("Selected edge:")
            if not opts:
                st.info("This edge is not selectable in the current map state.")
            for i, opt in enumerate(opts):
                if st.button(f"Confirm {opt.text}", key=f"confirm_edge_{i}", use_container_width=True):
                    st.session_state.selection.append(opt)
                    st.session_state.pending_confirm_kind = None
                    st.session_state.pending_confirm_id = None
                    st.session_state.pending_confirm_action = None
                    st.session_state.pending_confirm_obj = None
                    st.session_state.click_targets = None
                    persist_and_rerun()
    elif pending_kind == "edge_object":
        pending_edge_obj = pending_obj
        if pending_edge_obj is not None:
            st.caption(f"Selected edge: {pending_edge_obj.text}")
            if st.button(f"Confirm {pending_edge_obj.text}", use_container_width=True):
                st.session_state.selection.append(pending_edge_obj)
                st.session_state.pending_confirm_kind = None
                st.session_state.pending_confirm_id = None
                st.session_state.pending_confirm_action = None
                st.session_state.pending_confirm_obj = None
                st.session_state.click_targets = None
                persist_and_rerun()

    pending_vertex = find_selectable_vertex(st.session_state.get("pending_confirm_vertex_id"))
    if pending_vertex is not None and pending_kind != "vertex":
        pending_action = st.session_state.get("pending_confirm_action")
        if (
            st.session_state.get("active_tool") == "draw line"
            and pending_action == "segment_vertices"
        ):
            vertex_number = min(len(sel_sig()["vertices"]) + 1, 2)
            st.caption(f"Selected vertex {vertex_number}")
        else:
            st.caption(f"Selected vertex: {vertex_meeting_label(pending_vertex)}")
        if st.button("Confirm Vertex", use_container_width=True):
            if pending_vertex not in st.session_state.selection:
                st.session_state.selection.append(pending_vertex)
            st.session_state.pending_confirm_vertex_id = None
            st.session_state.click_targets = None
            persist_and_rerun()

    if st.session_state.get("result_summary"):
        st.success(st.session_state.result_summary)

    targets = st.session_state.click_targets
    candidate_buttons = []
    if targets and any(targets):
        v, f, e = targets
        if v and "vertex" in allowed_kinds:
            nm = vertex_name(v, create=False)
            lbl = nm if nm else f"({v.p.x:.2f},{v.p.y:.2f})"
            candidate_buttons.append((f"📍 Vertex {lbl}", "vertex", v))
        if v and "angle" in allowed_kinds:
            candidate_buttons.append(("📐 Angle Here...", "angle", v))
        if f and "region" in allowed_kinds:
            candidate_buttons.append((f"⬛ Region {f.letter}", "region", f))
        if e and "edge" in allowed_kinds:
            for opt in edge_options(e):
                candidate_buttons.append((f"➖ {opt.text}", "edge", opt))

    if candidate_buttons:
        st.caption("You clicked near — add to selection:")
        ccols = st.columns(2)
        for i, (label, kind, obj) in enumerate(candidate_buttons):
            if ccols[i % 2].button(label, key=f"cand_{i}", use_container_width=True):
                if kind == "angle":
                    st.session_state.pending_angle_vertex = obj
                elif kind == "edge":
                    st.session_state.pending_confirm_kind = "edge_object"
                    st.session_state.pending_confirm_id = i
                    st.session_state.pending_confirm_action = None
                    st.session_state.pending_confirm_obj = obj
                    st.session_state.click_targets = None
                else:
                    st.session_state.pending_confirm_kind = kind
                    st.session_state.pending_confirm_id = str(id(obj))
                    st.session_state.pending_confirm_action = None
                    st.session_state.pending_confirm_obj = obj
                    if kind == "vertex":
                        st.session_state.pending_confirm_vertex_id = None
                    st.session_state.click_targets = None
                persist_and_rerun()

    pav = st.session_state.pending_angle_vertex
    if pav is not None:
        st.caption("Angle of which region?")
        regs = T.neighbors(pav)          # regions meeting at this vertex
        acols = st.columns(2)
        for i, rg in enumerate(regs):
            if acols[i % 2].button(f"Angle of Region {rg.letter}",
                                   key=f"ang_{rg.letter}", use_container_width=True):
                push_undo()
                a_sel = AngleSel(pav, rg)
                aname = next_name("a")
                st.session_state.angles.append((aname, a_sel))
                st.session_state.annotations.append(
                    {"kind": "angle", "vertex": pav, "face": rg, "label": aname})
                st.session_state.selection.append(a_sel)
                st.session_state.pending_angle_vertex = None
                st.session_state.click_targets = None
                persist_and_rerun()

    # --- clear ---
    if st.button("Clear Selection", use_container_width=True):
        clear_action_selection()
        persist_and_rerun()

    # --- REUSABLE OBJECTS BUFFER (explicitly saved artifacts only) ---
    # Unions are NOT listed here: a merged region is selected by clicking it
    # directly on the map (it shows up as "Region U1").
    saved = []
    for aname, a_sel in st.session_state.angles:
        if "angle" in allowed_kinds:
            saved.append((f"Use {aname}: Angle in Region {a_sel.face.letter}", a_sel))
    if saved:
        st.caption("Reusable Marked Objects:")
        scols = st.columns(2)
        for i, (label, obj) in enumerate(saved):
            if scols[i % 2].button(label, key=f"saved_{i}", use_container_width=True):
                st.session_state.selection.append(obj)
                persist_and_rerun()

# ----------------------------------------------------------------------------
# RIGHT PANEL — quick actions, scratch pad, then program trace + output log
# (scratch pad + actions on top so they're visible without scrolling; the
#  longer-growing Program/Output sit underneath in fixed-height scrollers.)
# ----------------------------------------------------------------------------
with col_io:
    st.subheader("Quick Actions")
    qcols = st.columns(2)
    if qcols[0].button("↩ Undo Last Tool Step", use_container_width=True,
                       disabled=not st.session_state.undo_stack):
        undo_last()
    if qcols[1].button("Clear Drawings & Program", use_container_width=True):
        for k in ["annotations", "lines", "angles", "named_edges", "unions",
                  "union_consumed", "undo_stack", "program", "log", "translations"]:
            st.session_state[k] = []
        st.session_state.vertex_names = {}
        st.session_state.vertex_descriptions = {}
        st.session_state.point_names = {}
        st.session_state.pending_confirm_vertex_id = None
        st.session_state.pending_confirm_kind = None
        st.session_state.pending_confirm_id = None
        st.session_state.pending_confirm_action = None
        st.session_state.pending_confirm_obj = None
        st.session_state.result_summary = None
        st.session_state.counters = {"v": 1, "L": 1, "U": 1, "r": 1, "a": 1, "e": 1}
        persist_and_rerun()
    if qcols[0].button("Clear Output Log", use_container_width=True):
        st.session_state.log = []
        st.session_state.translations = []
        st.session_state.result_summary = None
        persist_and_rerun()
    if qcols[1].button("New Random Map", use_container_width=True):
        if os.path.exists(PERSIST_FILE):
            os.remove(PERSIST_FILE)
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

    st.subheader("📝 Scratch pad")
    st.text_area("scratch", key="scratch_pad", height=120,
                 label_visibility="collapsed",
                 placeholder="Free-form notes / answers. Kept until you load a new map.")

    st.subheader(f"Program ({len(st.session_state.program)} steps)")
    if st.session_state.program:
        with st.container(height=200):
            newest_first = list(reversed(st.session_state.program[-25:]))
            numbered = [
                f"{len(st.session_state.program) - i}. {line}"
                for i, line in enumerate(newest_first)
            ]
            st.code("\n".join(numbered), language="python")
    else:
        st.caption("(your tool steps become code here)")

    st.subheader("Output")
    if not st.session_state.log:
        st.caption("(results will appear here)")
    else:
        with st.container(height=220):
            for entry in reversed(st.session_state.log[-25:]):
                st.markdown(entry)

    st.subheader("Translation")
    if not st.session_state.translations:
        st.caption("(natural-language translations will appear here)")
    else:
        with st.container(height=180):
            for entry in reversed(st.session_state.translations[-25:]):
                st.markdown(entry)

persist_state()
