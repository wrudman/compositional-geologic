"""
geo_env.py — headless port of the GeoLogic survey interface (app.py).

The VLM sees exactly what a human participant saw:
  * the same diagram, rebuilt from (num_regions, seed) via BuildRandomMap
  * the same render() pipeline, colors, fonts, and label cache
  * the same 460x460 display image
  * the same participant-facing tool output text

Sections 4 (drawing primitives), 5 (rendering), and 8 (execution) are ported
from app.py with `st.session_state` replaced by an explicit Env object.
The practice/tutorial branches are dropped; survey behavior is unchanged.

Usage:
    import geo_env
    env = geo_env.Env(num_regions=8, seed=35, structure_complexity="high")
    img = env.render()                      # PIL image, 460x460

    env.select_region("A")
    out = env.run("neighbors", {"kind": "edge"})
    print(out)                              # participant-facing text
    img = env.render()                      # updated image

    # or let the harness search for a valid seed:
    env = geo_env.make_env(8, structure_complexity="high")
"""

import math
from edge_label_layout import edge_label_position
import os
import random
import re
import tempfile

from PIL import Image, ImageDraw

import Graph
import BuildRandomMap
import DrawGraph
import map_helpers
import tools_human as T
from sel_types import AngleSel, EdgeSel

# The "high" complexity generator rejects far more candidate splits, and
# Graph.InteriorEdge prints a block for every rejection. Silence it.
Graph.debug = False


# ============================================================
# CONSTANTS  (verbatim from app.py)
# ============================================================
DISPLAY_SIDE = 460
MATH_SCALE = 800.0

GOLD_FILL = (255, 215, 0, 230)
GOLD_OUTLINE = (184, 134, 11, 255)
TEAL = (0, 255, 204, 255)
ANGLE_SELECT = (203, 32, 107, 255)
CYAN_EDGE = (0, 255, 255, 235)
GRAY_SOLID = (150, 150, 150, 190)
UNION_PURPLE = (147, 112, 219, 180)
GREEN_ANGLE = (0, 150, 0, 255)
BLUE = (0, 0, 255, 255)

TOOLS = ["centroid", "vertex", "find edge", "neighbors", "draw line", "intersect", "merge", "measure", "sort"]

STRUCTURE_COMPLEXITIES = ("current", "high")


# ============================================================
# TYPE CHECKERS  (verbatim from app.py section 0)
# ============================================================
def is_angle(o):   return type(o).__name__ == "AngleSel"
def is_edgesel(o): return type(o).__name__ == "EdgeSel"
def is_vertex(o):  return hasattr(o, "outarcs")
def is_region(o):
    return (not is_angle(o) and not is_edgesel(o)
            and hasattr(o, "edges") and hasattr(o, "bounded"))


class Env:
    """One survey item: a diagram plus the participant's accumulated workspace."""

    def __init__(self, num_regions, seed, maxX=1.0, maxY=1.0,
                 structure_complexity="current", keep_generator_images=False):
        if structure_complexity not in STRUCTURE_COMPLEXITIES:
            raise ValueError(
                f"structure_complexity must be one of {STRUCTURE_COMPLEXITIES}.")
        Graph.initialize()
        self.maxX, self.maxY = maxX, maxY
        self.num_regions = num_regions
        self.seed = seed
        self.structure_complexity = structure_complexity

        self.res_map = self._build_map(num_regions, maxX, maxY, seed,
                                       structure_complexity,
                                       keep_generator_images)
        self.generation_trace = list(getattr(self.res_map, "generation_trace", []))

        map_helpers.use_map(self.res_map)
        T.setup(self.res_map)

        self.img_size = (int(200 + 800 * maxX), int(200 + 800 * maxY))

        # Lock label positions once. LetterPointFace is stochastic; without the
        # cache the region letters jitter between turns. This matters more under
        # "high", whose concave regions have smaller inscribed radii.
        self.face_label_cache = {}
        for face in self.res_map.faces:
            if face.bounded:
                face._cache_idx = id(face)
                self.face_label_cache[id(face)] = Graph.LetterPointFace(face)

        self.selection = []
        self.annotations = []
        self.lines = []
        self.angles = []
        self.named_edges = []
        self.unions = []
        self.union_consumed = []
        self.consumed_ids = set()      # faces absorbed into a union
        self.point_names = {}
        self.program = []
        self.log = []
        self.tool_calls = []
        self.counters = {"v": 1, "L": 1, "U": 1, "r": 1, "a": 1, "e": 1}
        self.history = []              # undo stack of workspace snapshots

    @staticmethod
    def _build_map(num_regions, maxX, maxY, seed, structure_complexity,
                   keep_generator_images):
        """BuildRandomMap calls DrawGraph.DrawGraph, which writes Attempt1_*.png
        into the current working directory. A headless harness does not want
        that side effect, so build inside a scratch directory unless asked."""
        if keep_generator_images:
            return BuildRandomMap.BuildRandomMap(
                num_regions, maxX, maxY, seed,
                structure_complexity=structure_complexity)
        with tempfile.TemporaryDirectory() as scratch:
            cwd = os.getcwd()
            os.chdir(scratch)
            try:
                return BuildRandomMap.BuildRandomMap(
                    num_regions, maxX, maxY, seed,
                    structure_complexity=structure_complexity)
            finally:
                os.chdir(cwd)

    # ---------- convenient lookups ----------
    @property
    def faces(self):
        """Letter -> face. A merged region replaces the two faces it absorbed:
        after merge(G, H) the map offers U, and G and H are no longer selectable."""
        out = {}
        for f in self.res_map.faces:
            if f.bounded and id(f) not in self.consumed_ids:
                out[f.letter] = f
        for union in self.unions:
            out[union["name"]] = union["face"]
        return out

    def region(self, letter):
        try:
            return self.faces[letter]
        except KeyError:
            raise KeyError(
                f"No region {letter!r}. Available: "
                f"{', '.join(sorted(self.faces))}") from None

    # ============================================================
    # 2. NAMING & DESCRIPTIONS
    # ============================================================
    def next_name(self, prefix):
        self.counters.setdefault(prefix, 1)
        n = self.counters[prefix]
        self.counters[prefix] += 1
        if prefix == "U":
            return prefix
        return f"{prefix}{n}"

    def point_name(self, v, create=True):
        key = id(v)
        if key in self.point_names:
            return self.point_names[key]
        if not create:
            return None
        name = self.next_name("c" if getattr(v, "point_kind", None) == "centroid" else "v")
        self.point_names[key] = name
        self.annotations.append({"kind": "point", "p": v.p, "label": name, "obj": v})
        return name

    def angle_name(self, a_sel):
        for name, sel in self.angles:
            if sel == a_sel:
                return name
        return "a?"

    def edge_name(self, e_sel):
        for name, sel in self.named_edges:
            if sel == e_sel:
                return name
        return None

    def code_name(self, o):
        if o == "frame":  return '"frame"'
        if is_angle(o):   return self.angle_name(o)
        if is_edgesel(o):
            nm = self.edge_name(o)
            return nm if nm else f"edge[{o.text}]"
        if is_region(o):  return o.letter
        if is_vertex(o):  return self.point_name(o)
        return str(o)

    def describe(self, o):
        if is_angle(o):
            return f"angle {self.angle_name(o)} (in Region {o.face.letter})"
        if is_edgesel(o):
            nm = self.edge_name(o)
            return f"edge {nm} ({o.text})" if nm else o.text
        if isinstance(o, (list, tuple, set)):
            items = list(o)
            return "(nothing)" if not items else ", ".join(self.describe(x) for x in items)
        if o is None: return "(nothing)"
        if isinstance(o, bool): return "YES" if o else "NO"
        if o == "frame": return "the Frame"
        if is_region(o):
            return f"Region {o.letter}" if getattr(o, "bounded", True) else "the Outside (frame)"
        if is_vertex(o):
            nm = self.point_name(o, create=False)
            return nm if nm else "Vertex"
        if isinstance(o, dict) and "type" in o:
            return {"segment": "a segment", "extend": "an edge extension", "ray": "a ray"}[o["type"]]
        if isinstance(o, float): return f"{o:.4f}"
        return str(o)

    def answer_like_text(self, o):
        if is_angle(o):
            return self.angle_name(o)
        if is_edgesel(o):
            nm = self.edge_name(o)
            return nm if nm else o.text
        if isinstance(o, (list, tuple, set)):
            items = list(o)
            if isinstance(o, set):
                items.sort(key=lambda item: self.answer_like_text(item))
            return "None" if not items else ", ".join(self.answer_like_text(x) for x in items)
        if o is None:
            return "None"
        if isinstance(o, bool):
            return "Yes" if o else "No"
        if o == "frame":
            return "Frame"
        if is_region(o):
            return o.letter if getattr(o, "bounded", True) else "Outside"
        if is_vertex(o):
            nm = self.point_name(o, create=False)
            return nm if nm else "Vertex"
        if isinstance(o, dict) and "type" in o:
            return {"segment": "segment", "extend": "edge extension", "ray": "ray"}[o["type"]]
        if isinstance(o, float):
            return f"{o:.4f}"
        return str(o)

    def sel_sig(self):
        s = self.selection
        return {
            "regions":  [o for o in s if o != "frame" and is_region(o)],
            "vertices": [o for o in s if o != "frame" and is_vertex(o)],
            "edges":    [o for o in s if is_edgesel(o)],
            "angles":   [o for o in s if is_angle(o)],
            "frame":    [o for o in s if o == "frame"],
            "n": len(s),
        }

    # ============================================================
    # SELECTION  (the VLM's equivalent of clicking the diagram)
    # ============================================================
    def clear_selection(self):
        """Deselect everything. Does not undo any completed tool call."""
        self.selection = []
        return self

    # ---------- undo ----------
    _SNAPSHOT_ATTRS = ("selection", "annotations", "lines", "angles",
                       "named_edges", "unions", "union_consumed", "consumed_ids",
                       "point_names", "program", "log", "tool_calls", "counters")

    def _snapshot(self):
        """Shallow-copy every workspace container, plus the face list, so one
        completed tool call can be rolled back. Graph geometry is never mutated
        in place, so shallow copies are sufficient.

        The selection is snapshotted as empty: a tool call always ends with a
        cleared buffer (or one holding only what the call itself found), so
        rolling back to a partially-built selection would restore state the
        participant never saw."""
        state = {name: self._copy_container(getattr(self, name))
                 for name in self._SNAPSHOT_ATTRS}
        state["selection"] = []
        state["res_map_faces"] = list(self.res_map.faces)
        state["face_label_cache"] = dict(self.face_label_cache)
        self.history.append(state)

    @staticmethod
    def _copy_container(value):
        if isinstance(value, list):
            return list(value)
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, set):
            return set(value)
        return value

    def undo(self):
        """Roll back the most recent tool call, restoring the workspace exactly
        as it stood before. Returns participant-facing text."""
        if not self.history:
            return "There is nothing to undo."
        undone = self.tool_calls[-1]["tool"] if self.tool_calls else None
        state = self.history.pop()
        for name in self._SNAPSHOT_ATTRS:
            setattr(self, name, state[name])
        self.res_map.faces[:] = state["res_map_faces"]
        self.face_label_cache = state["face_label_cache"]
        if undone:
            return f"Undid the last **{undone}** action."
        return "Undid the last action."

    def clear_all(self):
        """Undo every tool call, returning the diagram to its starting state."""
        n = len(self.history)
        while self.history:
            self.undo()
        if not n:
            return "The diagram is already in its starting state."
        return f"Cleared the workspace. Undid {n} action{'s' if n != 1 else ''}."

    def select_region(self, letter):
        self.selection.append(self.region(letter))
        return self

    def select_frame(self):
        self.selection.append("frame")
        return self

    def select_vertex(self, v):
        self.point_name(v)
        self.selection.append(v)
        return self

    def select_angle(self, vertex, face):
        sel = AngleSel(vertex, face)
        if not any(saved == sel for _, saved in self.angles):
            aname = self.next_name("a")
            self.angles.append((aname, sel))
            self.annotations.append(
                {"kind": "angle", "vertex": vertex, "face": face, "label": aname})
        if sel not in self.selection:
            self.selection.append(sel)
        return self

    def select_edge(self, edge_sel):
        if self.edge_name(edge_sel) is None:
            self.named_edges.append((self.next_name("e"), edge_sel))
        if edge_sel not in self.selection:
            self.selection.append(edge_sel)
        return self

    def edge_between(self, letter_a, letter_b):
        """Build the EdgeSel for the shared edge of two regions."""
        fa, fb = self.region(letter_a), self.region(letter_b)
        segs = [e for e in fa.edges if e.reverse.leftFace is fb]
        if not segs:
            raise ValueError(f"Regions {letter_a} and {letter_b} share no edge.")
        return EdgeSel(segs, None, f"edge between {letter_a} and {letter_b}")

    def edge_among(self, *letters):
        """Build the EdgeSel for the edge of the first region meeting the rest.

        Mirrors tools_human.find(..., object="edge") / edge(region, *meets).
        Accepts the string "Outside" for the outside of the frame.
        """
        objs = [l if l == "Outside" else self.region(l) for l in letters]
        result = T.find(*objs, object="edge")
        if result is None:
            raise ValueError(f"No edge found among {', '.join(letters)}.")
        segs = list(result) if isinstance(result, (list, tuple)) else [result]
        if not segs:
            raise ValueError(f"No edge found among {', '.join(letters)}.")
        return EdgeSel(segs, None, f"edge among {', '.join(letters)}")

    # ============================================================
    # 3. LINE GEOMETRY
    # ============================================================
    def _extend_to_frame(self, a, b):
        dx, dy = b.x - a.x, b.y - a.y
        ts = []
        if abs(dx) > 1e-9: ts += [(0 - a.x) / dx, (self.maxX - a.x) / dx]
        if abs(dy) > 1e-9: ts += [(0 - a.y) / dy, (self.maxY - a.y) / dy]
        pts = []
        for t in ts:
            x, y = a.x + t * dx, a.y + t * dy
            if -1e-6 <= x <= self.maxX + 1e-6 and -1e-6 <= y <= self.maxY + 1e-6:
                pts.append((t, Graph.Vector(x, y)))
        pts.sort(key=lambda z: z[0])
        return pts[0][1], pts[-1][1]

    def line_endpoints_math(self, line):
        if line["type"] == "segment":
            return line["a"], line["b"]
        if line["type"] == "extend":
            return self._extend_to_frame(line["a"], line["b"])
        if line["type"] == "ray":
            a = line["a"]
            ends = {0: Graph.Vector(self.maxX, a.y), 1: Graph.Vector(a.x, self.maxY),
                    2: Graph.Vector(0, a.y), 3: Graph.Vector(a.x, 0)}
            return a, ends[line["direction"]]

    def edgesel_endpoints(self, es):
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
    # 4. DRAWING PRIMITIVES  (verbatim from app.py)
    # ============================================================
    @staticmethod
    def highlight_vertex_x(odraw, p, ring=False):
        px, py = DrawGraph.V2P(p)
        if ring:
            odraw.ellipse([px-15, py-15, px+15, py+15], outline=TEAL, width=4)
        else:
            odraw.ellipse([px-12, py-12, px+12, py+12], fill=GOLD_FILL,
                          outline=GOLD_OUTLINE, width=4)

    @staticmethod
    def highlight_edge_x(odraw, e, label=None):
        p1, p2 = DrawGraph.V2P(e.tail.p), DrawGraph.V2P(e.head.p)
        odraw.line([p1, p2], fill=CYAN_EDGE, width=14)
        for (px, py) in (p1, p2):
            odraw.ellipse([px-7, py-7, px+7, py+7], fill=CYAN_EDGE)
        if label:
            mx, my = (p1[0]+p2[0])//2, (p1[1]+p2[1])//2
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            length = max(1.0, math.hypot(dx, dy))
            nx, ny = -dy / length, dx / length
            if abs(nx) >= abs(ny):
                if nx > 0:
                    nx, ny = -nx, -ny
            elif ny > 0:
                nx, ny = -nx, -ny
            label_xy = (round(mx + 30 * nx), round(my + 30 * ny))
            font = DrawGraph.GetSystemFont(32)
            label_xy = edge_label_position(odraw, p1, p2, label, font, label_xy, 2)
            odraw.text(label_xy, label, fill=(0, 100, 130, 255), font=font,
                       anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))

    @staticmethod
    def draw_interior_arc_x(odraw, vertex, face, label=None,
                            radius=45, color=GREEN_ANGLE, width=5):
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

    @staticmethod
    def draw_union_label(draw, xy, name, font_big):
        lx, ly = xy
        draw.text((lx, ly), name, fill=(0, 0, 0, 255), font=font_big,
                  anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))

    @staticmethod
    def draw_union_solid(draw, union, font_big):
        pair = union.get("pair", ())
        faces = pair if pair else (union["face"],)
        for face in faces:
            pts = [DrawGraph.V2P(v.p) for v in face.vertices]
            draw.polygon(pts, fill=UNION_PURPLE)

        segments = {}
        for face in faces:
            for edge in face.edges:
                a = (round(edge.tail.p.x, 9), round(edge.tail.p.y, 9))
                b = (round(edge.head.p.x, 9), round(edge.head.p.y, 9))
                key = tuple(sorted((a, b)))
                segments.setdefault(key, []).append(edge)
        for occurrences in segments.values():
            if len(occurrences) == 1:
                edge = occurrences[0]
                draw.line([DrawGraph.V2P(edge.tail.p), DrawGraph.V2P(edge.head.p)],
                          fill=(0, 0, 0, 255), width=6)

    def _face_label_lp_d(self, face):
        idx = getattr(face, "_cache_idx", None)
        if idx is not None and idx in self.face_label_cache:
            return self.face_label_cache[idx]
        return Graph.LetterPointFace(face)

    def highlight_region_solid(self, odraw, face, fill=GRAY_SOLID, draw_label=True):
        pts = [DrawGraph.V2P(v.p) for v in face.vertices]
        odraw.polygon(pts, fill=fill, outline=(0, 0, 0, 255))
        for e in face.edges:
            odraw.line([DrawGraph.V2P(e.tail.p), DrawGraph.V2P(e.head.p)],
                       fill=(0, 0, 0, 255), width=4)
        if draw_label:
            lp, d = self._face_label_lp_d(face)
            coords = DrawGraph.V2P(lp)
            font = DrawGraph.GetSystemFont(80 if d > 0.06 else 45)
            odraw.text(coords, face.letter, fill=(0, 0, 0, 255), font=font, anchor="mm",
                       stroke_width=2, stroke_fill=(255, 255, 255, 255))

    # ---- union bookkeeping ----
    def _consumed_to_union_map(self):
        m = {}
        for union in self.unions:
            for f in union["pair"]:
                m[id(f)] = union["face"]
        return m

    @staticmethod
    def _edge_interior_to_union(e, cmap):
        fa, fb = e.leftFace, e.reverse.leftFace
        if not (getattr(fa, "bounded", False) and getattr(fb, "bounded", False)):
            return False
        ua, ub = cmap.get(id(fa)), cmap.get(id(fb))
        return ua is not None and ua is ub

    # ============================================================
    # 5. RENDERING  (ported from app.py; practice branches removed)
    # ============================================================
    def render(self, side=DISPLAY_SIDE):
        img = Image.new("RGBA", self.img_size, (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        DrawGraph.DrawAllFaces(self.res_map, draw, None,
                               label_cache=self.face_label_cache)

        font = DrawGraph.GetSystemFont(35)
        font_big = DrawGraph.GetSystemFont(80)

        for union in self.unions:
            self.draw_union_solid(draw, union, font_big)

        overlay = Image.new("RGBA", self.img_size, (255, 255, 255, 0))
        odraw = ImageDraw.Draw(overlay)
        union_face_ids = {id(u["face"]) for u in self.unions}

        # PASS 1 — region fills beneath markers
        for ann in self.annotations:
            if ann["kind"] == "region" and getattr(ann["obj"], "bounded", False):
                face = ann["obj"]
                self.highlight_region_solid(
                    odraw, face, ann.get("color", GRAY_SOLID),
                    draw_label=id(face) not in union_face_ids)
        for o in self.selection:
            if o != "frame" and is_region(o) and getattr(o, "bounded", False):
                self.highlight_region_solid(
                    odraw, o, GRAY_SOLID,
                    draw_label=id(o) not in union_face_ids)

        for union in self.unions:
            self.draw_union_label(odraw, union["label_xy"], union["name"], font_big)

        # PASS 2 — markers
        for ann in self.annotations:
            kind = ann["kind"]
            if kind == "point":
                self.highlight_vertex_x(odraw, ann["p"])
                if ann.get("label"):
                    px, py = DrawGraph.V2P(ann["p"])
                    odraw.text((px + 16, py - 32), ann["label"], fill=BLUE, font=font,
                               stroke_width=2, stroke_fill=(255, 255, 255, 255))
            elif kind == "line":
                a, b = self.line_endpoints_math(ann["line"])
                pa, pb = DrawGraph.V2P(a), DrawGraph.V2P(b)
                line_width = 5 if ann["line"]["type"] == "extend" else 6
                odraw.line([pa, pb], fill=BLUE, width=line_width)
                if ann.get("label"):
                    if ann["line"]["type"] == "extend":
                        source_a = DrawGraph.V2P(ann["line"]["a"])
                        source_b = DrawGraph.V2P(ann["line"]["b"])

                        def nearest_source(frame_point):
                            return min((source_a, source_b),
                                       key=lambda s: ((frame_point[0] - s[0]) ** 2
                                                      + (frame_point[1] - s[1]) ** 2))
                        exposed_pairs = [(pa, nearest_source(pa)), (pb, nearest_source(pb))]
                        outer, inner = max(exposed_pairs,
                                           key=lambda pair: ((pair[0][0] - pair[1][0]) ** 2
                                                             + (pair[0][1] - pair[1][1]) ** 2))
                        mx = round(outer[0] * 0.58 + inner[0] * 0.42)
                        my = round(outer[1] * 0.58 + inner[1] * 0.42)
                    else:
                        mx = (pa[0] + pb[0]) // 2
                        my = (pa[1] + pb[1]) // 2
                    odraw.text((mx, my), ann["label"], fill=BLUE, font=font,
                               anchor="mm", stroke_width=2,
                               stroke_fill=(255, 255, 255, 255))
            elif kind == "angle":
                self.draw_interior_arc_x(odraw, ann["vertex"], ann["face"],
                                         label=ann.get("label"))

        # named edges persist after the selection clears
        cmap = self._consumed_to_union_map()
        for edge_label, edge_selection in self.named_edges:
            visible = [seg for seg in edge_selection.segments
                       if not self._edge_interior_to_union(seg, cmap)]
            for i, segment in enumerate(visible):
                self.highlight_edge_x(odraw, segment,
                                      label=edge_label if i == 0 else None)

        # live selection markers
        for o in self.selection:
            if o == "frame":
                seen = set()
                for edge in self.res_map.edges:
                    left = getattr(edge, "leftFace", None)
                    right = getattr(getattr(edge, "reverse", None), "leftFace", None)
                    if not (getattr(left, "bounded", False)
                            != getattr(right, "bounded", False)):
                        continue
                    a = DrawGraph.V2P(edge.tail.p)
                    b = DrawGraph.V2P(edge.head.p)
                    key = tuple(sorted((a, b)))
                    if key in seen:
                        continue
                    seen.add(key)
                    odraw.line([a, b], fill=TEAL, width=10)
            elif is_angle(o):
                self.draw_interior_arc_x(odraw, o.vertex, o.face,
                                         label=self.angle_name(o),
                                         color=ANGLE_SELECT, width=6)
            elif is_edgesel(o):
                for e in o.segments:
                    self.highlight_edge_x(odraw, e)
                self.highlight_edge_x(odraw, o.segments[0], label=self.edge_name(o))
            elif is_vertex(o):
                self.highlight_vertex_x(odraw, o.p, ring=True)

        img.alpha_composite(overlay)
        if side:
            return img.convert("RGB").resize((side, side), Image.Resampling.LANCZOS)
        return img.convert("RGB")

    # ============================================================
    # 8. EXECUTION
    # ============================================================
    def visualize_result(self, result):
        if is_angle(result) or is_edgesel(result):
            return
        if isinstance(result, (list, tuple, set)):
            for r in result:
                self.visualize_result(r)
            return
        if result is None or isinstance(result, (bool, int, float, str)):
            return
        if is_vertex(result):
            self.point_name(result)
        elif is_region(result) and getattr(result, "bounded", False):
            self.annotations.append(
                {"kind": "region", "obj": result, "color": GRAY_SOLID})

    def _finish(self, tool, call_str, result, assign_prefix="r", visualize=True):
        if visualize:
            self.visualize_result(result)
        if assign_prefix:
            var = self.next_name(assign_prefix)
            self.program.append(f"{var} = {call_str}")
        else:
            self.program.append(call_str)
        output_text = self.answer_like_text(result)
        message = participant_output_for_tool(self, tool, call_str, result, output_text)
        self.log.append(message)
        self.tool_calls.append({"tool": tool, "input": call_str,
                                "output_text": output_text, "display_text": message})
        if tool == "measure":
            self.tool_calls[-1]["output"] = result
        self.clear_selection()
        return message

    def _finish_vertex(self, call_str, result, trace_tool="vertex"):
        """Vertex keeps previously found points in the buffer; regions/frame are consumed."""
        keep, seen = [], set()
        for o in self.selection:
            if o == "frame" or is_region(o):
                continue
            keep.append(o)
            if is_vertex(o):
                seen.add(id(o))
        self.selection = keep

        new_pts = result if isinstance(result, list) else ([result] if result is not None else [])
        for v in new_pts:
            if is_vertex(v) and id(v) not in seen:
                seen.add(id(v))
                self.point_name(v)
                self.selection.append(v)

        labels = [self.code_name(v) for v in new_pts if is_vertex(v)]
        if len(labels) == 1:
            self.program.append(f"{labels[0]} = {call_str}")
        elif len(labels) > 1:
            self.program.append(f"[{', '.join(labels)}] = {call_str}")
        else:
            self.program.append(call_str)
        output_text = self.answer_like_text(result)
        message = participant_output_for_tool(self, trace_tool, call_str, result, output_text)
        self.log.append(message)
        self.tool_calls.append({"tool": trace_tool, "input": call_str,
                                "output_text": output_text, "display_text": message})
        return message

    def _finish_edge(self, call_str, edge_sel):
        """Found edges get a name, persist in named_edges, and stay selected."""
        self.select_edge(edge_sel)
        name = self.edge_name(edge_sel)
        self.program.append(f"{name} = {call_str}")
        output_text = name
        message = participant_output_for_tool(self, "find edge", call_str,
                                              edge_sel, output_text)
        self.log.append(message)
        self.tool_calls.append({"tool": "find edge", "input": call_str,
                                "output_text": output_text, "display_text": message})
        return message

    def _ranking_finish(self, call_str, result, by):
        self.program.append(call_str + "   # smallest -> largest")
        ordered = self.answer_like_text(result)
        edge_groups = None
        if by == "edge_length":
            edge_groups = [[self.code_name(item) for item in group]
                           for group in T.sort(result, by=by, grouped=True)]
            ordered = ", ".join(" = ".join(group) for group in edge_groups)
        message = participant_output_for_tool(self, "sort", call_str, result, ordered)
        self.log.append(message)
        self.tool_calls.append({"tool": "sort", "input": call_str,
                                "output_text": ordered, "display_text": message})
        if edge_groups is not None:
            self.tool_calls[-1].update(sort_by=by, tie_groups=edge_groups,
                                      has_ties=any(len(group)>1 for group in edge_groups))
        self.clear_selection()
        return message

    def run(self, tool, modes=None):
        """Execute one tool against the current selection. Returns participant text."""
        modes = modes or {}
        self._snapshot()
        sel = self.selection
        s = self.sel_sig()
        try:
            # ---- CENTROID (Find mode) ----
            if tool == "centroid":
                if not s["regions"] or s["frame"] or s["edges"] or s["angles"]:
                    raise ValueError("Select one or more regions to find centroids.")
                points = []
                for region in s["regions"]:
                    existing = next((a.get("obj") for a in self.annotations
                                     if getattr(a.get("obj"), "point_kind", None) == "centroid"
                                     and a["obj"].source_region is region), None)
                    points.append(existing if existing is not None else T.find(region, object="centroid"))
                call = f'find({", ".join(r.letter for r in s["regions"])}, object="centroid")'
                return self._finish_vertex(call, points[0] if len(points)==1 else points, "find")
            # ---- VERTEX ----
            if tool == "vertex":
                if s["frame"]:
                    which = modes["which"]
                    result = T.vertex("frame", which=which)
                    return self._finish_vertex(f'vertex("frame", which="{which}")', result)
                elif len(s["regions"]) >= 2:
                    onf = modes.get("on_frame", False)
                    result = T.vertex(*s["regions"], on_frame=onf)
                    args = ", ".join(o.letter for o in s["regions"])
                    return self._finish_vertex(f"vertex({args}, on_frame={onf})", result)
                else:
                    reg = s["regions"][0]
                    which = modes["which"]
                    result = T.vertex(reg, which=which)
                    return self._finish_vertex(f'vertex({reg.letter}, which="{which}")', result)

            # ---- FIND EDGE ----
            elif tool == "find edge":
                es = s["edges"][0]
                letters = modes.get("letters", [])
                call = (f'find({", ".join(letters)}, object="edge")'
                        if letters else 'find(object="edge")')
                return self._finish_edge(call, es)

            # ---- NEIGHBORS ----
            elif tool == "neighbors":
                if s["edges"] and not s["regions"] and not s["vertices"]:
                    seen, result, names = set(), [], []
                    cmap = {id(f): u["face"] for u in self.unions for f in u["pair"]}
                    for es in s["edges"]:
                        for seg in es.segments:
                            for face in T.neighbors(seg):
                                face = cmap.get(id(face), face)
                                if id(face) not in seen:
                                    seen.add(id(face))
                                    result.append(face)
                        names.append(self.edge_name(es) or "edge")
                    call = (f"neighbors([{', '.join(names)}])"
                            if len(names) > 1 else f"neighbors({names[0]})")
                    return self._finish(tool, call, result)

                elif s["vertices"] and not s["regions"]:
                    seen, result = set(), []
                    for v in s["vertices"]:
                        for face in T.neighbors(v):
                            if id(face) not in seen:
                                seen.add(id(face))
                                result.append(face)
                    names = [self.code_name(v) for v in s["vertices"]]
                    call = (f"neighbors([{', '.join(names)}])"
                            if len(names) > 1 else f"neighbors({names[0]})")
                    return self._finish(tool, call, result)

                elif s["regions"] and s["vertices"]:
                    reg, vtx = s["regions"][0], s["vertices"][0]
                    ccw = modes.get("ccw", True)
                    result = T.neighbors(reg, "ordered", start=vtx, go_counterclockwise=ccw)
                    return self._finish(tool,
                                        f'neighbors({reg.letter}, "ordered", '
                                        f"start={self.code_name(vtx)}, "
                                        f"go_counterclockwise={ccw})", result)
                else:
                    reg = s["regions"][0]
                    kind = modes["kind"]
                    result = T.neighbors(reg, kind)
                    return self._finish(tool, f'neighbors({reg.letter}, "{kind}")', result)

            # ---- DRAW LINE ----
            elif tool == "draw line":
                style = modes["style"]
                va = vb = None
                if style == "ray":
                    d = modes["ray_direction"]
                    line = T.draw(sel[0], d)
                    call = f'draw({self.code_name(sel[0])}, "{d}")'
                elif s["edges"]:
                    va, vb = self.edgesel_endpoints(s["edges"][0])
                    kind = "full" if style == "full line" else "segment"
                    line = T.draw(va, vb, kind=kind, extension_direction=modes.get("extension_direction"))
                    call = f'draw({self.code_name(s["edges"][0])}, kind="{kind}")'
                    if modes.get("extension_direction"):
                        call = call[:-1] + f', extension_direction="{modes["extension_direction"]}")' 
                else:
                    kind = "full" if style == "full line" else "segment"
                    line = T.draw(sel[0], sel[1], kind=kind)
                    call = (f'draw({self.code_name(sel[0])}, '
                            f'{self.code_name(sel[1])}, kind="{kind}")')
                if s["edges"]:
                    line['source_edge_endpoints'] = (va.p, vb.p)
                    line["source_edge_label"] = self.code_name(s["edges"][0])
                name = self.next_name("L")
                self.lines.append((name, line))
                self.annotations.append({"kind": "line", "line": line, "label": name})
                self.program.append(f"{name} = {call}")
                if style == "ray":
                    article = "an" if modes["ray_direction"] == "up" else "a"
                    message = (f"Drew **{name}**, {article} {modes['ray_direction']}ward "
                               f"ray from {self.code_name(sel[0])}.")
                elif modes.get("extension_direction"):
                    message = f'Extended **{self.code_name(s["edges"][0])}** {modes["extension_direction"]} to the frame. Extended edge: **{name}**.'
                elif style == "full line":
                    if s["edges"]:
                        message = (f"Extended **{self.code_name(s['edges'][0])}** in both "
                                   f"directions as **{name}**.")
                    else:
                        message = (f"Drew **{name}**, a full line through "
                                   f"{self.code_name(sel[0])} and {self.code_name(sel[1])}.")
                else:
                    a_nm = self.code_name(va) if s["edges"] else self.code_name(sel[0])
                    b_nm = self.code_name(vb) if s["edges"] else self.code_name(sel[1])
                    message = f"Drew **{name}**, a segment between {a_nm} and {b_nm}."
                self.log.append(message)
                self.tool_calls.append({"tool": tool, "input": call,
                                        "output_text": name, "display_text": message})
                self.clear_selection()
                return message

            # ---- INTERSECT ----
            elif tool == "intersect":
                lname, line = modes["line"]
                if modes.get("target") == "edges":
                    T.setup(self.res_map)
                    result=T.intersect(line,"edges")
                    message=self._finish(tool,f'intersect({lname}, "edges")',len(result),visualize=False)
                    self.tool_calls[-1]['crossed_edges']=T._crossed_edge_details(result)
                    return message
                if modes.get("target") == "vertices":
                    T.setup(self.res_map)
                    result=T.intersect(line,"vertices")
                    return self._finish_vertex(f'intersect({lname}, "vertices")',result,trace_tool="intersect")
                if modes.get("target") == "faces":
                    result = T.intersect(line, "faces")
                    return self._finish(tool, f'intersect({lname}, "faces")',
                                        result, visualize=False)
                tname, tline = modes["target"]
                result = T.intersect(line, tline)
                return self._finish(tool, f"intersect({lname}, {tname})",
                                    result, visualize=False)

            # ---- MERGE ----
            elif tool == "merge":
                fa, fb = s["regions"][0], s["regions"][1]
                fu = T.merge(fa, fb)
                uname = self.next_name("U")
                fu.letter = uname

                pair_vertices, seen = [], set()
                for source in (fa, fb):
                    for vertex in source.vertices:
                        if id(vertex) not in seen:
                            seen.add(id(vertex))
                            pair_vertices.append(vertex)
                label_point = Graph.Vector(
                    sum(v.p.x for v in pair_vertices) / len(pair_vertices),
                    sum(v.p.y for v in pair_vertices) / len(pair_vertices))

                # G and H are absorbed: they stop being selectable, U takes over.
                self.consumed_ids = set(self.consumed_ids) | {id(fa), id(fb)}
                fu._cache_idx = id(fu)
                self.face_label_cache = dict(self.face_label_cache)
                self.face_label_cache[id(fu)] = (label_point, 0.07)

                self.unions.append({"name": uname, "face": fu, "pair": (fa, fb),
                                    "label_xy": DrawGraph.V2P(label_point)})
                self.union_consumed += [fa, fb]
                self.program.append(f"{uname} = merge({fa.letter}, {fb.letter})")
                message = (f"Created merged Region **{uname}** from Regions "
                           f"{fa.letter} and {fb.letter}.")
                self.log.append(message)
                self.tool_calls.append({"tool": tool,
                                        "input": f"merge({fa.letter}, {fb.letter})",
                                        "output_text": uname, "display_text": message})
                self.clear_selection()
                return message

            # ---- MEASURE ----
            elif tool == "measure":
                w = modes["what"]

                if w == "extension" and modes.get("line"):
                    lname,line=modes["line"]
                    from extension_directions import question_extension_direction
                    points=line.get("source_edge_endpoints")
                    if points:
                        line["question_extension_direction"]=question_extension_direction(*points,getattr(self,"question_text",""),self.res_map)
                    value=T.measure(line,what="extension")
                    message=self._finish(tool,f'measure({lname}, what="extension", source_edge="{line.get("source_edge_label","edge")}")',value,visualize=False)
                    self.tool_calls[-1]["extension_lengths"]=value
                    return message
                elif w == "area" and modes.get("line"):
                    if s["n"]!=1 or len(s["regions"])!=1:
                        raise ValueError("Select one region and one full line.")
                    lname,line=modes["line"];region=s["regions"][0]
                    sides=modes.get("area_sides","above_below")
                    result=T.measure(region,what="area",line=line,area_sides=sides)
                    message=self._finish(tool,f'measure({region.letter}, what="area", line={lname}, area_sides="{sides}")',result,visualize=False)
                    self.tool_calls[-1]['areas']=result
                    return message

                elif w == "distance":
                    if len(s["vertices"]) == 1 and len(s["edges"]) == 1 and s["n"] == 2:
                        point, edge = s["vertices"][0], s["edges"][0]
                        value = T.measure(point, edge, what="distance")
                        return self._finish(tool,
                            f'measure({self.code_name(point)}, {self.edge_name(edge)}, what="distance")',
                            value, visualize=False)
                    if modes.get("line"):
                        lname, line = modes["line"]
                        val = T.measure(line, what="distance")
                        return self._finish(
                            tool, f'measure({lname}, what="distance")',
                            val, visualize=False)
                    if len(s["regions"]) == 2 and s["n"] == 2:
                        fa, fb = s["regions"]
                        val = T.measure(fa, fb, what="distance")
                        return self._finish(
                            tool,
                            f'measure({fa.letter}, {fb.letter}, what="distance")',
                            val)
                    p, q = s["vertices"][0], s["vertices"][1]
                    val = T.measure(p, q, what="distance")
                    return self._finish(
                        tool,
                        f'measure({self.code_name(p)}, {self.code_name(q)}, '
                        f'what="distance")', val)

                elif w == "parallel":
                    if s["n"] != 2 or len(s["edges"]) != 2:
                        raise ValueError("Select exactly two straight edges.")
                    a,b = s["edges"]
                    value = T.measure(a,b,what=w)
                    return self._finish(tool, f'measure({self.edge_name(a)}, {self.edge_name(b)}, what="parallel")', value, visualize=False)

                elif w == "convexity":
                    if s["n"] != 1 or len(s["regions"]) != 1:
                        raise ValueError("Select exactly one region or union for convexity.")
                    reg = s["regions"][0]
                    value = T.measure(reg, what=w)
                    return self._finish(tool, f'measure({reg.letter}, what="convexity")', value, visualize=False)

                elif w == "incident_edge_count":
                    if s["n"] != 1 or len(s["vertices"]) != 1:
                        raise ValueError("Select exactly one diagram vertex for incident edge count.")
                    vertex = s["vertices"][0]
                    value = T.measure(vertex, what=w,
                                      merged_regions=[u["face"] for u in self.unions])
                    return self._finish(tool,
                        f'measure({self.code_name(vertex)}, what="incident_edge_count")',
                        value, visualize=False)

                elif w == "angle":
                    a = s["angles"][0]
                    val = T.measure(a.vertex, a.face, what="angle")
                    call_str = f'measure({self.angle_name(a)}, what="angle")'
                    self.program.append(f'{self.next_name("r")} = {call_str}')
                    output_text = f"{val:.4f}"
                    message = participant_output_for_tool(self, "measure", call_str,
                                                          val, output_text)
                    self.log.append(message)
                    self.tool_calls.append({"tool": tool, "input": call_str,
                                            "output_text": output_text,
                                            "output": val,
                                            "display_text": message})
                    self.clear_selection()
                    return message

                elif w == "regions":
                    val = T.measure("frame", what="regions")
                    return self._finish(tool, 'measure("frame", what="regions")',
                                        val, visualize=False)

                elif w == "orientation":
                    points = s["vertices"]
                    if len(points) < 3 or s["n"] != len(points):
                        raise ValueError("Select at least three points in cycle order.")
                    names = ", ".join(self.code_name(v) for v in points)
                    call_str = f'measure({names}, what="orientation")'
                    val = T.measure(*points, what="orientation")
                    return self._finish(tool, call_str, val, visualize=False)

                else:  # area, edge_count (alias: sides), frame_edge_count
                    reg = s["regions"][0]
                    val = T.measure(reg, what=w)
                    recorded = "edge_count" if w == "sides" else w
                    return self._finish(tool,
                                        f'measure({reg.letter}, what="{recorded}")', val)

            # ---- SORT ----
            elif tool == "sort":
                by = modes["by"]
                if by == "angle":
                    angles = list(s["angles"])
                    result = T.sort(angles, by="angle")
                    arg = ", ".join(self.angle_name(a) for a in angles)
                    return self._ranking_finish(f'sort([{arg}], by="angle")', result, "angle")
                elif by == "area":
                    regs = list(s["regions"])
                    result = T.sort(regs, by="area")
                    arg = ", ".join(o.letter for o in regs)
                    return self._ranking_finish(f'sort([{arg}], by="area")', result, "area")
                elif by == "edge_length":
                    edges = list(s["edges"])
                    result = T.sort(edges, by="edge_length")
                    arg = ", ".join(self.code_name(e) for e in edges)
                    return self._ranking_finish(f'sort([{arg}], by="edge_length")', result, "edge_length")
                elif by in ("left_right", "bottom_top"):
                    pts = list(s["vertices"])
                    result = T.sort(pts, by=by)
                    arg = ", ".join(self.code_name(o) for o in pts)
                    return self._ranking_finish(f'sort([{arg}], by="{by}")', result, by)
                else:
                    ref, rest = s["vertices"][0], s["vertices"][1:]
                    result = T.sort(rest, by="distance", reference=ref)
                    arg = ", ".join(self.code_name(o) for o in rest)
                    return self._ranking_finish(
                        f'sort([{arg}], by="distance", reference={self.code_name(ref)})',
                        result, "distance")

            raise ValueError(f"Unknown tool {tool!r}. One of: {TOOLS}")

        except Exception as ex:
            message = (f"This tool could not complete this operation. "
                       f"Check your selection and settings, then try again.")
            self.log.append(message)
            self.tool_calls.append({"tool": tool, "input": f"run {tool}",
                                    "output_text": message, "display_text": message,
                                    "error": str(ex)})
            self.clear_selection()
            return message


# ============================================================
# CONSTRUCTION HELPER
# ============================================================
def make_env(num_regions, structure_complexity="high", seed=None,
             maxX=1.0, maxY=1.0, max_attempts=200, rng=None):
    """Build an Env, searching for a workable seed if none is given.

    BuildRandomMap raises ValueError when GraphCheck rejects the planar
    embedding, and can quietly return fewer regions than requested when
    AddRandomFace exhausts its retries. Both happen more often under
    structure_complexity="high", so a search wrapper is useful there.

    Passing an explicit seed disables the search: the map is built once and
    any failure propagates, which is what a dataset replay wants.
    """
    if seed is not None:
        env = Env(num_regions, seed, maxX, maxY,
                  structure_complexity=structure_complexity)
        if len(env.faces) != num_regions:
            raise ValueError(
                f"Seed {seed} produced {len(env.faces)} regions, not {num_regions}.")
        return env

    rng = rng or random.Random()
    for _ in range(max_attempts):
        candidate = rng.randint(1, 1_000_000_000)
        try:
            env = Env(num_regions, candidate, maxX, maxY,
                      structure_complexity=structure_complexity)
        except ValueError:
            continue
        if len(env.faces) == num_regions:
            return env
    raise RuntimeError(
        f"No valid {num_regions}-region map found in {max_attempts} attempts "
        f"at structure_complexity={structure_complexity!r}.")


# ============================================================
# PARTICIPANT-FACING OUTPUT  (ported from app.py)
# ============================================================
def natural_join(items):
    labels = [str(item).strip() for item in items if str(item).strip()]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return f"{', '.join(labels[:-1])}, and {labels[-1]}"


def participant_output_for_tool(env, tool, call_str, result, output_text=None):
    shown = output_text if output_text is not None else env.answer_like_text(result)
    if tool == "measure" and any(f'what="{mode}"' in call_str for mode in ("distance", "area", "angle")) and isinstance(result,(int,float)) and not isinstance(result,bool):
        shown = f"{result:.4f}"
    no_result = result is None or (
        isinstance(result, (list, tuple, set)) and not result)
    shown_as_list = (
        natural_join(env.answer_like_text(item) for item in result)
        if isinstance(result, (list, tuple, set)) and result else shown)
    emphasized = f"**{shown}**"
    emphasized_list = f"**{shown_as_list}**"

    if 'object="centroid"' in call_str:
        points = result if isinstance(result, list) else [result]
        return "Found and labeled " + "; ".join(
            f"{env.code_name(p)} as the centroid of Region {p.source_region.letter}"
            for p in points) + "."

    if tool == "vertex":
        property_match = re.search(r'which="([^"]+)"', call_str)
        region_match = re.match(r"vertex\(([^,\)]+)", call_str)
        if property_match and region_match:
            target = region_match.group(1).strip().strip('"')
            property_name = property_match.group(1).replace("_", " ")
            target_text = "the frame" if target == "frame" else f"Region {target}"
            if no_result:
                return f"No {property_name} vertex was found for {target_text}."
            if property_name == "all":
                return f"Found and labeled all vertices of {target_text}: {emphasized_list}."
            return (f"Found and labeled {emphasized_list} as the {property_name} "
                    f"vertex of {target_text}.")
        meeting_match = re.match(r"vertex\((.+),\s*on_frame=(True|False)\)", call_str)
        if meeting_match:
            regions = [part.strip() for part in meeting_match.group(1).split(",")]
            location = "on the frame" if meeting_match.group(2) == "True" else "not on the frame"
            region_text = natural_join(regions)
            if no_result:
                return f"No vertex was found where Regions {region_text} meet {location}."
            location_sentence = ("This vertex is on the frame."
                                 if meeting_match.group(2) == "True"
                                 else "This vertex is not on the frame.")
            return (f"Found and labeled {emphasized_list} where Regions {region_text} "
                    f"meet. {location_sentence}")
        if no_result:
            return "No matching vertex was found."
        return f"Found and labeled vertex {emphasized}."

    if tool == "find edge":
        among_match = re.match(r"find\((.+),\s*object=\"edge\"\)", call_str)
        if among_match:
            parts = [p.strip() for p in among_match.group(1).split(",")]
            region_text = natural_join(
                "the Outside" if p == "Outside" else f"Region {p}" for p in parts)
            if no_result:
                return f"No edge was found between {region_text}."
            return f"Found and labeled {emphasized} as the edge between {region_text}."
        if no_result:
            return "No matching edge was found."
        return f"Found and labeled edge {emphasized}."

    if tool == "neighbors":
        region_match = re.match(r'neighbors\(([A-Z][A-Za-z0-9]*),\s*"(edge|vertex)"\)', call_str)
        if region_match:
            name = region_match.group(1)
            if region_match.group(2) == "edge":
                if no_result:
                    return f"No regions share an edge with Region {name}."
                return f"Regions that share an edge with Region {name}: {emphasized}."
            if no_result:
                return f"No regions touch Region {name} at a vertex without sharing an edge."
            return (f"Regions that touch Region {name} at a vertex without sharing "
                    f"an edge: {emphasized}.")
        ordered_match = re.match(
            r'neighbors\(([A-Z][A-Za-z0-9]*),\s*"ordered",\s*start=([^,]+),\s*'
            r"go_counterclockwise=(True|False)\)", call_str)
        if ordered_match:
            direction = "counterclockwise" if ordered_match.group(3) == "True" else "clockwise"
            if no_result:
                return (f"The {direction} order from {ordered_match.group(2).strip()} "
                        "could not be determined. Try a different starting vertex.")
            return (f"Regions around Region {ordered_match.group(1)}, starting at "
                    f"{ordered_match.group(2).strip()} and moving {direction}: {emphasized}.")
        single_match = re.match(r"neighbors\(([^\)]+)\)", call_str)
        if single_match:
            selected = single_match.group(1).strip()
            if no_result:
                return f"No neighboring regions were found for {selected}."
            if selected.startswith("v"):
                return f"Regions meeting at {selected}: {emphasized}."
            if selected.startswith("e"):
                return f"Regions bordering {selected}: {emphasized}."
            return f"Regions neighboring {selected}: {emphasized}."
        if no_result:
            return "No neighboring regions were found."
        return f"Neighboring regions: {emphasized}."

    if tool == "intersect" and '"edges"' in call_str:
        line_name=call_str.split("(",1)[1].split(",",1)[0]
        count=result if isinstance(result,int) else len(result)
        return f"Number of edges {line_name} crosses: **{count}**."
    if tool == "intersect" and '"vertices"' in call_str:
        vertices=result if isinstance(result,list) else []
        line_name = call_str.split("(", 1)[1].split(",", 1)[0]
        return (f"Number of vertices {line_name} passes through: **{len(vertices)}**.\n\n"
                f"Vertices: **{shown if vertices else 'None'}**.")
    if tool == "intersect":
        line_match = re.match(r'intersect\(([^,]+),\s*"faces"\)', call_str)
        if line_match:
            if no_result:
                return f"{line_match.group(1).strip()} does not cross any regions."
            return f"Regions crossed by {line_match.group(1).strip()}: {emphasized}."
        lines_match = re.match(r"intersect\(([^,]+),\s*([^\)]+)\)", call_str)
        if lines_match and isinstance(result, bool):
            first, second = lines_match.group(1).strip(), lines_match.group(2).strip()
            return f"Do {first} and {second} intersect? **{'Yes' if result else 'No'}**."
        if no_result:
            return "No intersection was found."
        return f"Intersection result: {emphasized}."

    if tool == "measure":
        what_match = re.search(r'what="([^"]+)"', call_str)
        what = what_match.group(1) if what_match else "measurement"
        args = call_str[len("measure("):].split(", what=", 1)[0]
        if what == "extension" and isinstance(result,dict):
            original = result.get("original_edge",0)
            source = re.search(r'source_edge="([^"]+)"',call_str)
            source_name = " " + source.group(1) if source else ""
            parts = [f"Original edge{source_name}: **{original:.4f}**."]
            extensions = [(key,value) for key,value in result.items() if key != "original_edge"]
            parts += [f"{key.capitalize()} extension: **{value:.4f}**." for key,value in extensions]
            return " ".join(parts)
        if what == "parallel":
            return f"Are {args.replace(', ', ' and ')} parallel? **{'Yes' if result else 'No'}**."
        if what == "convexity":
            return f"Is Region {args} convex? **{'Yes' if result else 'No'}**."
        if what == "incident_edge_count":
            return f"The number of edges incident to {args}, including frame edges: {emphasized}."
        if what == "area" and isinstance(result,dict) and ('above' in result or 'left' in result):
            line_name=re.search(r'line=([^,)]+)',call_str).group(1)
            labels=('above','below') if 'above' in result else ('left','right')
            return " ".join(f"Area {label} of {line_name}: **{result[label]:.4f}**." if label in ('left','right') else f"Area {label} {line_name}: **{result[label]:.4f}**." for label in labels)
        if what == "area":
            return f"Area of Region {args}: {emphasized}."
        if what in ("sides", "edge_count"):
            return f"The number of edges of Region {args}: {emphasized}."
        if what == "frame_edge_count":
            return f"The number of edges of Region {args} that lie on the frame: {emphasized}."
        if what == "regions":
            return f"The number of regions in the frame: {emphasized}."
        if what == "orientation":
            return f"Cycle orientation for {args.replace(', ', ' -> ')}: {emphasized}."
        if what == "distance":
            if re.fullmatch(r"L\d+", args.strip()):
                return f"Length of {args}: {emphasized}."
            endpoints = natural_join(part.strip() for part in args.split(","))
            return f"Distance between {endpoints}: {emphasized}."
        if what == "angle":
            return f"Angle measurement for {args} (degrees): {emphasized}."
        return f"Measurement result: {emphasized}."

    if tool == "sort":
        by_match = re.search(r'by="([^"]+)"', call_str)
        by = by_match.group(1) if by_match else "value"
        lead = {
            "angle": "Angles from smallest to largest",
            "area": "Regions from smallest to largest by area",
            "left_right": "Vertices from left to right",
            "bottom_top": "Vertices from bottom to top",
            "edge_length": "Edges from shortest to longest",
            "distance": "Vertices from nearest to farthest",
        }.get(by, "Sorted objects")
        return f"{lead}: {emphasized}."

    return f"Result: {emphasized}."