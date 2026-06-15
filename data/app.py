# app.py
import math
import streamlit as st
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

DISPLAY_SIDE = 600
MATH_SCALE = 800.0

# Xiaohui's palette
GOLD_FILL = (255, 215, 0, 230)
GOLD_OUTLINE = (184, 134, 11, 255)
TEAL = (0, 255, 204, 255)
CYAN_EDGE = (0, 255, 255, 235)
YELLOW_REGION = (255, 255, 0, 100)
GRAY_SOLID = (150, 150, 150, 255)   # opaque highlight: replaces the old yellow film
UNION_PURPLE = (147, 112, 219, 255)
GREEN_ANGLE = (0, 150, 0, 255)
BLUE = (0, 0, 255, 255)

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
    st.session_state.last_click = None
    st.session_state.click_targets = None
    st.session_state.pending_angle_vertex = None
    st.session_state.annotations = []
    st.session_state.lines = []        # [(name, line_dict)]
    st.session_state.angles = []       # [(name, AngleSel)]
    st.session_state.named_edges = []  # [(name, EdgeSel)]
    st.session_state.unions = []       # [{"name","face","pair","label_xy"}]
    st.session_state.union_consumed = []   # constituent faces now hidden inside a union
    st.session_state.undo_stack = []   # snapshots for single-step undo
    st.session_state.point_names = {}
    st.session_state.program = []
    st.session_state.log = []
    st.session_state.counters = {"p": 1, "L": 1, "U": 1, "r": 1, "a": 1, "e": 1}

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

def point_name(v, create=True):
    key = id(v)
    if key in st.session_state.point_names:
        return st.session_state.point_names[key]
    if not create:
        return None
    name = next_name("p")
    st.session_state.point_names[key] = name
    st.session_state.annotations.append({"kind": "point", "p": v.p, "label": name})
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
    if is_vertex(o):  return point_name(o)
    return str(o)

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
        nm = point_name(o, create=False)
        return nm if nm else f"point ({o.p.x:.2f}, {o.p.y:.2f})"
    if isinstance(o, dict) and "type" in o:
        return {"segment": "a segment", "extend": "a full line", "ray": "a ray"}[o["type"]]
    if isinstance(o, float): return f"{o:.4f}"
    return str(o)

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
    """Thick cyan marker stroke + endpoint caps; optional name label."""
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

def highlight_region_solid(odraw, face, fill=GRAY_SOLID):
    """Opaque recolor of a region (new solid color, not a translucent film).
    Keeps the black outline and the region letter readable on top."""
    pts = [DrawGraph.V2P(v.p) for v in face.vertices]
    odraw.polygon(pts, fill=fill, outline=(0, 0, 0, 255))
    for e in face.edges:
        odraw.line([DrawGraph.V2P(e.tail.p), DrawGraph.V2P(e.head.p)],
                   fill=(0, 0, 0, 255), width=4)
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

    # ---- PASS 1: region fills go UNDERNEATH points/lines/angles, so a
    # reference point is never hidden under a highlight. The unbounded outer
    # face is never filled (it would blanket the whole canvas).
    for ann in st.session_state.annotations:
        if ann["kind"] == "region" and getattr(ann["obj"], "bounded", False):
            highlight_region_solid(odraw, ann["obj"], ann.get("color", GRAY_SOLID))
    for o in st.session_state.selection:
        if o != "frame" and is_region(o) and getattr(o, "bounded", False):
            highlight_region_solid(odraw, o, GRAY_SOLID)

    # ---- PASS 2: markers (points, lines, angles, edges) on top of fills.
    for ann in st.session_state.annotations:
        kind = ann["kind"]
        if kind == "point":
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
            # label once at the midpoint of the first segment
            highlight_edge_x(odraw, o.segments[0], label=edge_name(o))
        elif is_vertex(o):
            highlight_vertex_x(odraw, o.p, ring=True)

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

# ============================================================
# 7. TOOL DEFINITIONS
# ============================================================
TOOLS = ["corner", "meeting_point", "regions_at", "boundary_sequence",
         "draw line", "intersect", "neighbors", "merge", "measure", "sort"]

TOOL_LABELS = {
    "corner":            "Corner",
    "meeting_point":     "Meeting Point",
    "regions_at":        "Regions At",
    "boundary_sequence": "Boundary Sequence",
    "draw line":         "Draw Line",
    "intersect":         "Intersect",
    "neighbors":         "Neighbors",
    "merge":             "Merge",
    "measure":           "Measure",
    "sort":              "Sort",
}

INSTRUCTIONS = {
    "corner": "Select ONE region (or the FRAME). Then pick which corner.",
    "meeting_point": "Select TWO OR MORE regions that meet at one point.",
    "regions_at": "Select ONE point.",
    "boundary_sequence": "Select ONE region, then ONE of its corner points.",
    "draw line": "Two points → segment/full line • one point → ray • one edge → line along it. Chain segments to build paths or cycles.",
    "intersect": "Pick one of your drawn lines, then ask what it hits.",
    "neighbors": "Select ONE region (unions U1, U2… also work).",
    "merge": "Select TWO regions sharing a border → creates a solid purple U1, U2, …",
    "measure": "Pick what to measure. For angles: select a saved angle (a1, a2…) from the buffer, or create one (click corner → 📐 Angle here → region).",
    "sort": "Select several objects (all points or all regions). For distance/gap the FIRST selection is the reference. For angle: select ONE region.",
}

MEASURE_NEEDS = {
    "distance": "Select TWO points.",
    "gap": "Select TWO regions.",
    "angle": "Select ONE saved angle — press 'Select a1' in the buffer (or create one: corner → 📐 → region).",
    "area": "Select ONE region.",
    "sides": "Select ONE region (unions work).",
    "x": "Select ONE point.",
    "y": "Select ONE point.",
}

def validate(tool, modes):
    s = sel_sig()
    nR, nV, nE, nA, nF = (len(s["regions"]), len(s["vertices"]),
                          len(s["edges"]), len(s["angles"]), len(s["frame"]))
    if tool == "corner":
        return (s["n"] == 1 and (nR == 1 or nF == 1), "Need 1 region or the frame.")
    if tool == "meeting_point":
        return (nR >= 2 and nR == s["n"], f"Need 2+ regions — have {nR}.")
    if tool == "regions_at":
        return (s["n"] == 1 and nV == 1, "Need exactly 1 point.")
    if tool == "boundary_sequence":
        return (s["n"] == 2 and nR == 1 and nV == 1, "Need 1 region + 1 point.")
    if tool == "draw line":
        if modes.get("style") == "ray":
            return (s["n"] == 1 and nV == 1, "Ray needs exactly 1 point.")
        ok = (s["n"] == 2 and nV == 2) or (s["n"] == 1 and nE == 1)
        return (ok, "Need 2 points, or 1 edge, or 1 point + ray.")
    if tool == "intersect":
        return (len(st.session_state.lines) > 0, "Draw a line first.")
    if tool == "neighbors":
        return (s["n"] == 1 and nR == 1, "Need exactly 1 region.")
    if tool == "merge":
        return (s["n"] == 2 and nR == 2, "Need exactly 2 regions.")
    if tool == "measure":
        w = modes.get("what")
        if not w: return (False, "Pick what to measure.")
        if w == "angle":
            return (s["n"] == 1 and nA == 1, MEASURE_NEEDS["angle"])
        need = {"distance": (0, 2), "gap": (2, 0),
                "area": (1, 0), "sides": (1, 0), "x": (0, 1), "y": (0, 1)}[w]
        ok = (nR, nV) == need and s["n"] == sum(need)
        return (ok, MEASURE_NEEDS[w])
    if tool == "sort":
        by = modes.get("by")
        if not by: return (False, "Pick a criterion.")
        if by in ("x", "y"): return (nV == s["n"] and nV >= 2, "Select 2+ points.")
        if by == "distance": return (nV == s["n"] and nV >= 3,
                                     "Select reference point FIRST, then 2+ points.")
        if by in ("area", "sides"): return (nR == s["n"] and nR >= 2, "Select 2+ regions.")
        if by == "gap": return (nR == s["n"] and nR >= 3,
                                "Select reference region FIRST, then 2+ regions.")
        if by == "angle": return (nR == 1 and s["n"] == 1,
                                  "Select ONE region — its corners get sorted.")
    return (False, "")

# ============================================================
# 8. EXECUTION + PROGRAM TRACE
# ============================================================
def add_program(line): st.session_state.program.append(line)
def add_log(text):     st.session_state.log.append(text)

# ---- single-step UNDO -------------------------------------------------------
_UNDO_KEYS = ["selection", "annotations", "lines", "angles", "named_edges",
              "unions", "union_consumed", "point_names", "counters",
              "program", "log"]

def push_undo():
    """Snapshot the tracked state BEFORE a mutating action so it can be undone."""
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
    st.rerun()

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
        point_name(result)
    elif is_region(result) and getattr(result, "bounded", False):
        st.session_state.annotations.append(
            {"kind": "region", "obj": result, "color": GRAY_SOLID})

def finish(tool, call_str, result, assign_prefix="r", visualize=True):
    if visualize:
        visualize_result(result)
    if assign_prefix:
        var = next_name(assign_prefix)
        add_program(f"{var} = {call_str}")
    else:
        add_program(call_str)
    add_log(f"`{call_str}` → **{describe(result)}**")
    st.session_state.selection = []
    st.rerun()

def run_tool(tool, modes):
    sel = st.session_state.selection
    s = sel_sig()
    try:
        if tool == "corner":
            which = modes["which"]
            result = T.corner(sel[0], which)
            finish(tool, f'corner({code_name(sel[0])}, "{which}")', result,
                   "p" if not isinstance(result, list) else "r")

        elif tool == "meeting_point":
            onf = modes["on_frame"]
            result = T.meeting_point(*sel, on_frame=onf)
            args = ", ".join(code_name(o) for o in sel)
            finish(tool, f"meeting_point({args}, on_frame={onf})", result, "p")

        elif tool == "regions_at":
            result = T.regions_at(sel[0])
            finish(tool, f"regions_at({code_name(sel[0])})", result)

        elif tool == "boundary_sequence":
            reg, vtx = s["regions"][0], s["vertices"][0]
            ccw = modes["ccw"]
            result = T.boundary_sequence(reg, vtx, go_counterclockwise=ccw)
            finish(tool, f"boundary_sequence({reg.letter}, {code_name(vtx)}, "
                         f"go_counterclockwise={ccw})", result)

        elif tool == "draw line":
            style = modes["style"]
            if style == "ray":
                d = modes["ray_direction"]
                line = T.draw(sel[0], d)
                call = f'draw({code_name(sel[0])}, "{d}")'
            elif s["edges"]:
                va, vb = edgesel_endpoints(s["edges"][0])
                kind = "full" if style == "full line" else "segment"
                line = T.draw(va, vb, kind=kind)
                call = f'draw({code_name(va)}, {code_name(vb)}, kind="{kind}")  # along {code_name(s["edges"][0])}'
            else:
                kind = "full" if style == "full line" else "segment"
                line = T.draw(sel[0], sel[1], kind=kind)
                call = f'draw({code_name(sel[0])}, {code_name(sel[1])}, kind="{kind}")'
            name = next_name("L")
            st.session_state.lines.append((name, line))
            st.session_state.annotations.append({"kind": "line", "line": line, "label": name})
            add_program(f"{name} = {call}")
            add_log(f"`{name} = {call}` → drawn")
            st.session_state.selection = []
            st.rerun()

        elif tool == "intersect":
            lname, line = modes["line"]
            if modes["target"] == "faces":
                result = T.intersect(line, "faces")
                finish(tool, f'intersect({lname}, "faces")', result, visualize=False)
            else:
                tname, tline = modes["target"]
                result = T.intersect(line, tline)
                finish(tool, f"intersect({lname}, {tname})", result, visualize=False)

        elif tool == "neighbors":
            kind = modes["kind"]
            result = T.neighbors(sel[0], kind)
            finish(tool, f'neighbors({code_name(sel[0])}, "{kind}")', result)

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
            add_log(f"`{uname} = merge({fa.letter}, {fb.letter})` → new solid region **{uname}**")
            st.session_state.selection = []
            st.rerun()

        elif tool == "measure":
            w = modes["what"]
            if w == "angle":
                a = s["angles"][0]
                val = Graph.angleAtFace(a.vertex, a.face) * 180.0 / math.pi
                finish(tool, f'measure({angle_name(a)}, what="angle")', round(val, 2))
            else:
                result = T.measure(*sel, what=w)
                args = ", ".join(code_name(o) for o in sel)
                finish(tool, f'measure({args}, what="{w}")', result)

        elif tool == "sort":
            by = modes["by"]

            def _sort_value(it, ref):
                if by == "distance": return map_helpers.dist(it, ref)
                if by == "gap":      return map_helpers.region_dist(it, ref)
                if by == "x":        return map_helpers.x_of(it)
                if by == "y":        return map_helpers.y_of(it)
                if by == "area":     return map_helpers.area(it)
                if by == "sides":    return map_helpers.side_count(it)
                if by == "angle":    return map_helpers.angle_at(it, ref) * 180.0 / math.pi
                return 0

            def _fmt(v):
                return f"{int(v)}" if by == "sides" else f"{v:.3f}"

            def _sort_log(call_str, result, ref):
                add_program(call_str + "   # smallest \u2192 largest")
                ordered = "  \u2192  ".join(
                    f"{code_name(it)} ({_fmt(_sort_value(it, ref))})" for it in result)
                add_log(f"`{call_str}` \u2014 **smallest \u2192 largest:**  {ordered}")
                st.session_state.selection = []
                st.rerun()

            if by == "angle":
                reg = s["regions"][0]
                corners = T.corner(reg, "all")
                result = T.sort(corners, by="angle", reference=reg)
                _sort_log(f'sort(corner({reg.letter}, "all"), by="angle", reference={reg.letter})',
                          result, reg)
            elif by in ("distance", "gap"):
                ref, items = sel[0], sel[1:]
                result = T.sort(list(items), by=by, reference=ref)
                arg = ", ".join(code_name(o) for o in items)
                _sort_log(f'sort([{arg}], by="{by}", reference={code_name(ref)})', result, ref)
            else:
                result = T.sort(list(sel), by=by)
                arg = ", ".join(code_name(o) for o in sel)
                _sort_log(f'sort([{arg}], by="{by}")', result, None)

    except Exception as ex:
        add_log(f"❌ **{tool}** failed: {ex}")
        st.session_state.selection = []
        st.rerun()

# ============================================================
# 9. LAYOUT
# ============================================================
col1, col2 = st.columns([3, 2])

with col1:
    display_img = render().resize((DISPLAY_SIDE, DISPLAY_SIDE), Image.Resampling.LANCZOS)
    coords = streamlit_image_coordinates(display_img, key="map_click")

    if coords is not None and coords != st.session_state.last_click:
        st.session_state.last_click = coords
        st.session_state.click_targets = hit_test(coords["x"], coords["y"])
        st.session_state.pending_angle_vertex = None

    targets = st.session_state.click_targets
    candidate_buttons = []
    if targets and any(targets):
        v, f, e = targets
        if v:
            nm = point_name(v, create=False)
            lbl = nm if nm else f"({v.p.x:.2f},{v.p.y:.2f})"
            candidate_buttons.append((f"📍 Point {lbl}", "vertex", v))
            candidate_buttons.append(("📐 Angle here…", "angle", v))
        if f:
            candidate_buttons.append((f"⬛ Region {f.letter}", "region", f))
        if e:
            for opt in edge_options(e):
                candidate_buttons.append((f"➖ {opt.text}", "edge", opt))

    if candidate_buttons:
        st.caption("You clicked near — add to selection:")
        ccols = st.columns(4)
        for i, (label, kind, obj) in enumerate(candidate_buttons):
            if ccols[i % 4].button(label, key=f"cand_{i}", use_container_width=True):
                push_undo()
                if kind == "angle":
                    st.session_state.pending_angle_vertex = obj
                elif kind == "edge":
                    if edge_name(obj) is None:
                        st.session_state.named_edges.append((next_name("e"), obj))
                    st.session_state.selection.append(obj)
                    st.session_state.click_targets = None
                else:
                    st.session_state.selection.append(obj)
                    if kind == "vertex":
                        point_name(obj)
                    st.session_state.click_targets = None
                st.rerun()

    pav = st.session_state.pending_angle_vertex
    if pav is not None:
        st.caption("Angle of which region?")
        regs = T.regions_at(pav)
        acols = st.columns(4)
        for i, rg in enumerate(regs):
            if acols[i % 4].button(f"angle of Region {rg.letter}",
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
                st.rerun()

    # --- frame / clear ---
    ucols = st.columns(4)
    if ucols[0].button("Select FRAME", use_container_width=True):
        push_undo()
        st.session_state.selection.append("frame")
        st.rerun()
    if ucols[1].button("Clear selection", use_container_width=True):
        push_undo()
        st.session_state.selection = []
        st.session_state.click_targets = None
        st.session_state.pending_angle_vertex = None
        st.rerun()

    # --- SAVED OBJECTS BUFFER (angles + edges) ---
    # Unions are NOT listed here anymore: a merged region is selected by clicking
    # it directly on the map (it shows up as "Region U1").
    saved = []
    for aname, a_sel in st.session_state.angles:
        saved.append((f"Select {aname} (angle, Region {a_sel.face.letter})", a_sel))
    for ename, e_sel in st.session_state.named_edges:
        saved.append((f"Select {ename} ({e_sel.text})", e_sel))
    if saved:
        st.caption("Saved objects:")
        scols = st.columns(4)
        for i, (label, obj) in enumerate(saved):
            if scols[i % 4].button(label, key=f"saved_{i}", use_container_width=True):
                push_undo()
                st.session_state.selection.append(obj)
                st.rerun()

with col2:
    st.subheader("Tools")
    tcols = st.columns(5)
    for i, t_name in enumerate(TOOLS):
        is_active = (st.session_state.active_tool == t_name)
        display = TOOL_LABELS.get(t_name, t_name)
        label = f"✅ {display}" if is_active else display
        if tcols[i % 5].button(label, key=f"tool_{t_name}", use_container_width=True):
            st.session_state.active_tool = t_name
            st.rerun()

    tool = st.session_state.active_tool
    modes = {}

    if tool:
        display = TOOL_LABELS.get(tool, tool)
        st.markdown(f"### {display}")
        st.info(INSTRUCTIONS[tool])

        if st.session_state.selection:
            st.write("**Selected:** " + ", ".join(describe(o) for o in st.session_state.selection))

        if tool == "corner":
            s = sel_sig()
            opts = (["all", "top_left", "top_right", "bottom_left", "bottom_right"]
                    if s["frame"] else
                    ["all", "leftmost", "rightmost", "topmost", "bottommost", "sharpest", "widest"])
            modes["which"] = st.radio("Which corner?", opts, horizontal=True, key="rad_corner")
        elif tool == "meeting_point":
            modes["on_frame"] = st.radio("Is the point on the frame?", [False, True],
                                         format_func=lambda b: "Yes" if b else "No",
                                         horizontal=True, key="rad_onframe")
        elif tool == "boundary_sequence":
            modes["ccw"] = st.radio("Walk direction", [True, False],
                                    format_func=lambda b: "Counter-clockwise" if b else "Clockwise",
                                    horizontal=True, key="rad_ccw")
        elif tool == "draw line":
            modes["style"] = st.radio("Line style", ["segment", "full line", "ray"],
                                      horizontal=True, key="rad_style")
            if modes["style"] == "ray":
                modes["ray_direction"] = st.radio("Direction", ["up", "down", "left", "right"],
                                                  horizontal=True, key="rad_raydir")
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
        elif tool == "neighbors":
            modes["kind"] = st.radio("Neighbor type", ["edge", "vertex"],
                                     format_func=lambda k: "Share an edge" if k == "edge"
                                     else "Touch only at a corner",
                                     horizontal=True, key="rad_nbr")
        elif tool == "measure":
            modes["what"] = st.radio("Measure what?",
                                     ["distance", "gap", "angle", "area", "sides", "x", "y"],
                                     index=None, horizontal=True, key="rad_measure")
        elif tool == "sort":
            modes["by"] = st.radio("Sort by",
                                   ["distance", "x", "y", "angle", "area", "sides", "gap"],
                                   index=None, horizontal=True, key="rad_sort")

        ready, msg = validate(tool, modes)
        if tool == "intersect" and modes.get("target") is None:
            ready = False
        if not ready:
            st.warning(msg)
        if st.button("▶ RUN", type="primary", disabled=not ready, use_container_width=True):
            push_undo()
            run_tool(tool, modes)

    st.subheader("Program")
    if st.session_state.program:
        st.code("\n".join(st.session_state.program), language="python")
    else:
        st.caption("(your actions become code here)")

    st.subheader("Output")
    if not st.session_state.log:
        st.caption("(results will appear here)")
    for entry in reversed(st.session_state.log[-10:]):
        st.markdown(entry)

# ---------- scratch pad ----------
st.subheader("📝 Scratch pad")
st.caption("Free-form notes / answers (e.g. list every pair that satisfies a property). "
           "Kept until you load a new map.")
st.text_area("scratch", key="scratch_pad", height=140, label_visibility="collapsed")

# ---------- footer ----------
st.markdown("---")
fcols = st.columns(4)
if fcols[0].button("↩ Undo last move", use_container_width=True,
                   disabled=not st.session_state.undo_stack):
    undo_last()
if fcols[1].button("Clear drawings & program", use_container_width=True):
    for k in ["annotations", "lines", "angles", "named_edges", "unions",
              "union_consumed", "undo_stack", "program", "log"]:
        st.session_state[k] = []
    st.session_state.point_names = {}
    st.session_state.counters = {"p": 1, "L": 1, "U": 1, "r": 1, "a": 1, "e": 1}
    st.rerun()
if fcols[2].button("Clear output log", use_container_width=True):
    st.session_state.log = []
    st.rerun()
if fcols[3].button("New random map", use_container_width=True):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()
