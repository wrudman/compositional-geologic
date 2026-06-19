import os
import math
import base64
import tempfile
from io import BytesIO

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageDraw

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

# Xiaohui's palette
GOLD_FILL = (255, 215, 0, 230)
GOLD_OUTLINE = (184, 134, 11, 255)
TEAL = (0, 255, 204, 255)
ANGLE_SELECT = (203, 32, 107, 255)   # deep rose: readable + aesthetic for selected angles
CYAN_EDGE = (0, 255, 255, 235)
YELLOW_REGION = (255, 255, 0, 100)
GRAY_SOLID = (150, 150, 150, 190)   # slightly transparent highlight for selected regions
UNION_PURPLE = (147, 112, 219, 255)
GREEN_ANGLE = (0, 150, 0, 255)
BLUE = (0, 0, 255, 255)

# ============================================================
# 0a. SELECTION-ROW HOVER CSS
# ------------------------------------------------------------
# Each selection row is rendered inside st.container(key=f"sel_row_{i}"),
# which Streamlit tags with a CSS class "st-key-sel_row_<i>". This rule
# matches that class by substring, so it scopes ONLY to selection rows —
# nothing else in the app is touched. The remove (✕) button stays faintly
# visible by default (so it's always clickable, even without hover/on
# touch devices) and brightens to full opacity on row hover.
# ============================================================
_SELECTION_ROW_CSS = """
<style>
div[class*="st-key-sel_row_"]{
    border-radius:6px;
    padding:1px 4px;
    transition:background-color .15s ease;
}
div[class*="st-key-sel_row_"]:hover{
    background-color:rgba(150,150,150,0.15);
}
div[class*="st-key-sel_row_"] button{
    opacity:0.25;
    transition:opacity .15s ease;
}
div[class*="st-key-sel_row_"]:hover button{
    opacity:1;
}
</style>
"""

# ============================================================
# 0b. HOVER COMPONENT  (the ONLY new machinery)
# ------------------------------------------------------------
# A tiny bidirectional Streamlit component. It:
#   * draws the rendered PNG on a base <canvas>,
#   * paints a light-gray highlight on a top <canvas> on mousemove
#     (100% client-side: NO server round-trip while hovering),
#   * returns {x, y} on click — exactly the shape the old
#     streamlit_image_coordinates returned — so every downstream
#     line of code (hit_test, selection, tools) is unchanged.
# The front-end is written to disk once and served as a static
# component, so you still only edit / run this one app.py.
# ============================================================
_GEO_CANVAS_HTML = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
 html,body{margin:0;padding:0;background:transparent;}
 #wrap{position:relative;}
 canvas{position:absolute;top:0;left:0;}
 #ov{cursor:crosshair;}
</style></head><body>
<div id="wrap"><canvas id="bg"></canvas><canvas id="ov"></canvas></div>
<script>
function send(type,data){window.parent.postMessage(Object.assign({isStreamlitMessage:true,type:type},data),"*");}
const Streamlit={
  ready:function(){send("streamlit:componentReady",{apiVersion:1});},
  height:function(h){send("streamlit:setFrameHeight",{height:h});},
  value:function(v){send("streamlit:setComponentValue",{value:v,dataType:"json"});}
};
var SIDE=460, SHAPES=null, imgEl=null, clickN=0;
var bg=document.getElementById('bg'), ov=document.getElementById('ov');
var bgx=bg.getContext('2d'), ovx=ov.getContext('2d');

function setup(image, shapes, side){
  SIDE=side; SHAPES=shapes;
  bg.width=ov.width=side; bg.height=ov.height=side;
  if(!imgEl || imgEl._src!==image){
    imgEl=new Image(); imgEl._src=image;
    imgEl.onload=function(){bgx.clearRect(0,0,side,side);bgx.drawImage(imgEl,0,0,side,side);};
    imgEl.src="data:image/png;base64,"+image;
  } else { bgx.clearRect(0,0,side,side); bgx.drawImage(imgEl,0,0,side,side); }
  Streamlit.height(side+4);
}

function distSeg(px,py,a,b){
  var vx=b[0]-a[0], vy=b[1]-a[1], wx=px-a[0], wy=py-a[1];
  var c1=vx*wx+vy*wy; if(c1<=0)return Math.hypot(px-a[0],py-a[1]);
  var c2=vx*vx+vy*vy; if(c2<=c1)return Math.hypot(px-b[0],py-b[1]);
  var t=c1/c2; return Math.hypot(px-(a[0]+t*vx),py-(a[1]+t*vy));
}
function inPoly(px,py,pts){
  var inside=false;
  for(var i=0,j=pts.length-1;i<pts.length;j=i++){
    var xi=pts[i][0],yi=pts[i][1],xj=pts[j][0],yj=pts[j][1];
    if(((yi>py)!=(yj>py))&&(px<(xj-xi)*(py-yi)/(yj-yi)+xi))inside=!inside;
  }
  return inside;
}
function angIn(px,py,a){
  var d=Math.hypot(px-a.cx,py-a.cy);
  if(Math.abs(d-a.r)>9)return false;
  var ang=Math.atan2(py-a.cy,px-a.cx)*180/Math.PI;
  while(ang<a.start)ang+=360; while(ang>=a.start+360)ang-=360;
  return ang<=a.end;
}
function pick(px,py){
  var S=SHAPES, i; if(!S)return null;
  for(i=0;i<S.vertices.length;i++){var v=S.vertices[i];
    if(Math.hypot(px-v[0],py-v[1])<11)return {t:'vertex',d:v};}
  for(i=0;i<S.angles.length;i++){ if(angIn(px,py,S.angles[i]))return {t:'angle',d:S.angles[i]}; }
  var be=null,bd=8;
  for(i=0;i<S.edges.length;i++){var e=S.edges[i],dd=distSeg(px,py,e.a,e.b); if(dd<bd){bd=dd;be=e;}}
  if(be)return {t:'edge',d:be};
  var f=S.frame;
  var nV=(Math.abs(px-f.x0)<8||Math.abs(px-f.x1)<8)&&py>=f.y0-8&&py<=f.y1+8;
  var nH=(Math.abs(py-f.y0)<8||Math.abs(py-f.y1)<8)&&px>=f.x0-8&&px<=f.x1+8;
  if(nV||nH)return {t:'frame',d:f};
  for(i=0;i<S.regions.length;i++){ if(inPoly(px,py,S.regions[i].pts))return {t:'region',d:S.regions[i]}; }
  return null;
}
var GRAY='rgba(150,150,150,';
function paint(hit){
  ovx.clearRect(0,0,SIDE,SIDE);
  if(!hit)return;
  if(hit.t==='region'){var p=hit.d.pts; ovx.beginPath(); ovx.moveTo(p[0][0],p[0][1]);
    for(var i=1;i<p.length;i++)ovx.lineTo(p[i][0],p[i][1]); ovx.closePath();
    ovx.fillStyle=GRAY+'0.45)'; ovx.fill();}
  else if(hit.t==='edge'){ovx.beginPath(); ovx.moveTo(hit.d.a[0],hit.d.a[1]); ovx.lineTo(hit.d.b[0],hit.d.b[1]);
    ovx.strokeStyle=GRAY+'0.85)'; ovx.lineWidth=12; ovx.lineCap='round'; ovx.stroke();}
  else if(hit.t==='vertex'){ovx.beginPath(); ovx.arc(hit.d[0],hit.d[1],10,0,2*Math.PI);
    ovx.fillStyle=GRAY+'0.7)'; ovx.fill();}
  else if(hit.t==='angle'){var a=hit.d; ovx.beginPath();
    ovx.arc(a.cx,a.cy,a.r,a.start*Math.PI/180,a.end*Math.PI/180,false);
    ovx.strokeStyle=GRAY+'0.85)'; ovx.lineWidth=6; ovx.stroke();}
  else if(hit.t==='frame'){var fr=hit.d; ovx.strokeStyle=GRAY+'0.85)'; ovx.lineWidth=8;
    ovx.strokeRect(fr.x0,fr.y0,fr.x1-fr.x0,fr.y1-fr.y0);}
}
ov.addEventListener('mousemove',function(e){var r=ov.getBoundingClientRect();
  paint(pick(e.clientX-r.left, e.clientY-r.top));});
ov.addEventListener('mouseleave',function(){ovx.clearRect(0,0,SIDE,SIDE);});
ov.addEventListener('click',function(e){var r=ov.getBoundingClientRect();
  clickN++; Streamlit.value({x:Math.round(e.clientX-r.left),y:Math.round(e.clientY-r.top),n:clickN});});
window.addEventListener("message",function(e){
  if(!e.data||e.data.type!=="streamlit:render")return;
  var a=e.data.args||{}; setup(a.image, a.shapes, a.side||460);});
Streamlit.ready(); Streamlit.height(SIDE+4);
</script></body></html>
"""

def _geo_canvas_component():
    """Write the front-end once and return the declared component fn."""
    try:
        base = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        base = os.getcwd()
    comp_dir = os.path.join(base, "geo_canvas_comp")
    try:
        os.makedirs(comp_dir, exist_ok=True)
        idx = os.path.join(comp_dir, "index.html")
        if (not os.path.exists(idx)) or open(idx, "r", encoding="utf-8").read() != _GEO_CANVAS_HTML:
            with open(idx, "w", encoding="utf-8") as f:
                f.write(_GEO_CANVAS_HTML)
    except Exception:
        comp_dir = os.path.join(tempfile.gettempdir(), "geo_canvas_comp")
        os.makedirs(comp_dir, exist_ok=True)
        with open(os.path.join(comp_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(_GEO_CANVAS_HTML)
    return components.declare_component("geo_canvas", path=comp_dir)

_GEO_CANVAS = _geo_canvas_component()

def geo_canvas(image_b64, shapes, side, key=None):
    return _GEO_CANVAS(image=image_b64, shapes=shapes, side=side, key=key, default=None)

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
    st.session_state.selection_meta = []   # parallel to selection: what to
                                            # retract if that item is removed
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
    st.session_state.counters = {"v": 1, "L": 1, "U": 1, "r": 1, "a": 1, "e": 1}

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
    name = next_name("v")
    st.session_state.point_names[key] = name
    st.session_state.annotations.append({"kind": "point", "p": v.p, "label": name})
    return name

def point_name_with_meta(v):
    """Same as point_name(), but also returns cleanup metadata IF this call
    just created a brand-new name + label (vs. reusing one the point already
    had). Used only at the moment a vertex enters the selection, so the
    per-item remove (✕) button can retract exactly what it added."""
    key = id(v)
    if key in st.session_state.point_names:
        return st.session_state.point_names[key], None
    name = next_name("v")
    st.session_state.point_names[key] = name
    ann = {"kind": "point", "p": v.p, "label": name}
    st.session_state.annotations.append(ann)
    return name, {"kind": "point", "point_key": key, "annotation_ref": ann}

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

# ---- selection add/clear/remove (keep selection + selection_meta in lockstep) ----
def add_to_selection(obj, meta=None):
    """Append obj to the selection together with optional cleanup metadata —
    what to retract from the map if this exact entry is later removed via the
    per-item ✕ button. meta is None for plain re-selections (frame, regions,
    edges, or re-picking an already-saved point/angle): there's nothing extra
    to clean up beyond the live highlight, which disappears on its own."""
    st.session_state.selection.append(obj)
    st.session_state.selection_meta.append(meta)

def clear_selection():
    st.session_state.selection = []
    st.session_state.selection_meta = []

def remove_selection_item(i):
    """Remove the i-th selection entry (the per-row ✕ button). If selecting
    it had just created a point label or a new angle arc, retract that too —
    but only if it was freshly created by THIS selection event; re-picking an
    already-saved point/angle and then removing it leaves the saved object
    (and its permanent mark) intact."""
    sel, meta_list = st.session_state.selection, st.session_state.selection_meta
    if i < 0 or i >= len(sel):
        return
    meta = meta_list[i] if i < len(meta_list) else None
    sel.pop(i)
    if i < len(meta_list):
        meta_list.pop(i)
    if meta:
        if meta["kind"] == "point":
            st.session_state.point_names.pop(meta["point_key"], None)
            ref = meta.get("annotation_ref")
            st.session_state.annotations = [a for a in st.session_state.annotations if a is not ref]
        elif meta["kind"] == "angle":
            entry = meta.get("angle_entry")
            st.session_state.angles = [a for a in st.session_state.angles if a is not entry]
            ref = meta.get("annotation_ref")
            st.session_state.annotations = [a for a in st.session_state.annotations if a is not ref]
    st.session_state.click_targets = None
    st.session_state.pending_angle_vertex = None

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
                                color=ANGLE_SELECT, width=6)
        elif is_edgesel(o):
            for e in o.segments:
                highlight_edge_x(odraw, e)
            # label once at the midpoint of the first segment
            highlight_edge_x(odraw, o.segments[0], label=edge_name(o))
        elif is_vertex(o):
            highlight_vertex_x(odraw, o.p, ring=True)

    img.alpha_composite(overlay)
    return img

# ---- HOVER SHAPES -----------------------------------------------------------
# Serialize the live geometry into DISPLAY-space (0..DISPLAY_SIDE) vector shapes
# so the browser can hit-test under the mouse and paint the gray highlight with
# no server round-trip. Pure read-only: reuses the same V2P transform render()
# uses, so the overlay is pixel-aligned with the PNG by construction.
def _consumed_to_union_map():
    """id(constituent face) -> the union face that swallowed it."""
    m = {}
    for union in st.session_state.unions:
        for f in union["pair"]:
            m[id(f)] = union["face"]
    return m

def _edge_interior_to_union(e, cmap):
    """True if BOTH faces touching edge e were merged into the SAME union, i.e.
    the edge now lives strictly inside a solid merged region."""
    fa, fb = e.leftFace, e.reverse.leftFace
    if not (getattr(fa, "bounded", False) and getattr(fb, "bounded", False)):
        return False
    ua, ub = cmap.get(id(fa)), cmap.get(id(fb))
    return ua is not None and ua is ub

def _vertex_interior_to_union(v, cmap):
    """True if every bounded region around v was merged into one single union and
    v does not sit on the outer frame — i.e. v is strictly inside a merged blob.
    Boundary corners of a union (which still touch a live region or the frame)
    stay selectable as corners of the union itself."""
    bounded = [f for f in v.faces if getattr(f, "bounded", False)]
    if not bounded:
        return False
    if any(not getattr(f, "bounded", False) for f in v.faces):
        return False                    # touches the outside frame -> boundary
    units = set()
    for f in bounded:
        u = cmap.get(id(f))
        if u is None:
            return False                # touches a live, un-merged region -> boundary
        units.add(id(u))
    return len(units) == 1

def build_hover_shapes():
    sx = DISPLAY_SIDE / img_size[0]
    sy = DISPLAY_SIDE / img_size[1]

    def D(p):
        X, Y = DrawGraph.V2P(p)
        return [X * sx, Y * sy]

    consumed = st.session_state.union_consumed
    cmap = _consumed_to_union_map()
    union_faces = [u["face"] for u in st.session_state.unions]

    regions = []
    for f in res_map.faces:
        if not getattr(f, "bounded", False):
            continue
        if f in consumed:
            continue
        regions.append({"id": id(f), "pts": [D(v.p) for v in f.vertices]})
    for fu in union_faces:
        regions.append({"id": id(fu), "pts": [D(v.p) for v in fu.vertices]})

    seen, edges = set(), []
    for e in res_map.edges:
        if _edge_interior_to_union(e, cmap):     # edge now inside a merged region
            continue
        a, b = D(e.tail.p), D(e.head.p)
        keyk = tuple(sorted([(round(a[0], 1), round(a[1], 1)),
                             (round(b[0], 1), round(b[1], 1))]))
        if keyk in seen:
            continue
        seen.add(keyk)
        edges.append({"a": a, "b": b})

    vertices = [D(v.p) for v in res_map.vertices
                if not _vertex_interior_to_union(v, cmap)]

    c0, c1 = D(Graph.Vector(0, 0)), D(Graph.Vector(maxX, maxY))
    frame = {"x0": min(c0[0], c1[0]), "y0": min(c0[1], c1[1]),
             "x1": max(c0[0], c1[0]), "y1": max(c0[1], c1[1])}

    angles = []
    for _nm, a_sel in st.session_state.angles:
        vertex, face = a_sel.vertex, a_sel.face
        pc = vertex.p
        e_in = next((e for e in face.edges if e.head.p == pc), None)
        e_out = next((e for e in face.edges if e.tail.p == pc), None)
        if not e_in:
            e_in = next((e for e in face.edges if Graph.vecDist(e.head.p, pc) < 1e-9), None)
        if not e_out:
            e_out = next((e for e in face.edges if Graph.vecDist(e.tail.p, pc) < 1e-9), None)
        if not e_in or not e_out:
            continue
        cx, cy = D(pc)
        pxp, pyp = D(e_in.tail.p)
        pxn, pyn = D(e_out.head.p)
        ang_prev = math.degrees(math.atan2(pyp - cy, pxp - cx))
        ang_next = math.degrees(math.atan2(pyn - cy, pxn - cx))
        start, end = ang_prev, ang_next
        while end < start:
            end += 360
        if abs((end - start) - 180.0) < 0.1:
            continue
        angles.append({"cx": cx, "cy": cy, "r": 20.0, "start": start, "end": end})

    return {"regions": regions, "edges": edges, "vertices": vertices,
            "frame": frame, "angles": angles}

# ============================================================
# 6. CLICK HIT-TESTING
# ============================================================
def get_math_coords(px, py):
    rx = px * (img_size[0] / DISPLAY_SIDE)
    ry = py * (img_size[1] / DISPLAY_SIDE)
    return Graph.Vector((rx - 100) / MATH_SCALE, (900.0 - ry) / MATH_SCALE)

def hit_test(px, py):
    cp = get_math_coords(px, py)
    cmap = _consumed_to_union_map()
    v_best, v_d = None, 25 / MATH_SCALE
    for v in res_map.vertices:
        if _vertex_interior_to_union(v, cmap):   # corner now inside a merge
            continue
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
    "vertex": (
        "- **ONE region** → pick a corner\n"
        "- **TWO+ regions** → their meeting point\n"
        "- **The FRAME** → a frame corner"
    ),
    "neighbors": (
        "- **POINT(S)** → every region meeting at any selected point\n"
        "- **EDGE(S)** → the regions on either side of each "
        "(dropping each edge's own region)\n"
        "- **ONE region** → its bordering regions "
        "(share an edge / touch at a corner)\n"
        "- **ONE region + ONE of its corners** → the regions passed, in walking order"
    ),
    "draw line": (
        "- **Two points** → segment / full line\n"
        "- **One point** → ray\n"
        "- **One edge** → a line along it\n"
        "- Chain segments together to build paths or cycles"
    ),
    "intersect": (
        "- Pick one of your drawn lines\n"
        "- Then ask what it hits — which regions, or whether it crosses another line"
    ),
    "merge": (
        "- Select **TWO regions** sharing a border\n"
        "- → creates a solid purple region: U1, U2, …"
    ),
    "measure": (
        "- **ONE thing → ONE number**\n"
        "- **length** = a drawn segment (or the distance between two selected points)\n"
        "- **angle** = one or more saved angles (a1, a2…)\n"
        "- **area / sides** = a region"
    ),
    "sort": (
        "- Select **SEVERAL objects**, then choose how to order them "
        "(smallest → largest)\n"
        "- Several points → left→right, bottom→top, or distance from the first selected\n"
        "- Several regions → area\n"
        "- ONE region → its corners by angle"
    ),
}

def validate(tool, modes):
    s = sel_sig()
    nR, nV, nE, nA, nF = (len(s["regions"]), len(s["vertices"]),
                          len(s["edges"]), len(s["angles"]), len(s["frame"]))

    if tool == "vertex":
        if nF == 1 and s["n"] == 1:        return (True, "")
        if nR == 1 and s["n"] == 1:        return (True, "")
        if nR >= 2 and nR == s["n"]:       return (True, "")
        return (False, "Select 1 region, the FRAME, or 2+ regions.")

    if tool == "neighbors":
        # one or more POINTS (and nothing else) → regions meeting at any of them
        if nV >= 1 and nV == s["n"]:                   return (True, "")
        # one or more EDGES (and nothing else) → regions on either side of each
        if nE >= 1 and nE == s["n"]:                   return (True, "")
        # a single region → its edge / vertex neighbors
        if nR == 1 and s["n"] == 1:                    return (True, "")
        # a region + one of its corners → walking order
        if nR == 1 and nV == 1 and s["n"] == 2:        return (True, "")
        return (False, "Select point(s), edge(s), 1 region, or 1 region + 1 of its corners.")

    if tool == "draw line":
        if modes.get("style") == "ray":
            return (s["n"] == 1 and nV == 1, "Ray needs exactly 1 point.")
        ok = (s["n"] == 2 and nV == 2) or (s["n"] == 1 and nE == 1)
        return (ok, "Need 2 points, or 1 edge, or 1 point + ray.")

    if tool == "intersect":
        return (len(st.session_state.lines) > 0, "Draw a line first.")

    if tool == "merge":
        return (s["n"] == 2 and nR == 2, "Need exactly 2 regions.")

    if tool == "measure":
        w = modes.get("what")
        if not w: return (False, "Pick what to measure.")
        if w == "length":
            if nV == 2 and s["n"] == 2:        return (True, "")   # two points
            if modes.get("line") is not None:  return (True, "")   # a drawn segment
            return (False, "Select two points, or pick a drawn segment.")
        if w == "angle":
            # one or more saved angles, nothing else mixed in
            return (nA >= 1 and nA == s["n"], "Select one or more saved angles (a1, a2…).")
        if w in ("area", "sides"):
            return (nR == 1 and s["n"] == 1, "Select ONE region.")
        return (False, "")

    if tool == "sort":
        by = modes.get("by")
        if not by: return (False, "Pick how to order them.")
        if by == "angle":
            return (nR == 1 and s["n"] == 1,
                    "Select ONE region — its corners get ordered by angle.")
        if by == "area":
            return (nR >= 2 and nR == s["n"], "Select 2+ regions.")
        if by in ("left_right", "bottom_top"):
            return (nV >= 2 and nV == s["n"], "Select 2+ points.")
        if by == "distance":
            return (nV >= 3 and nV == s["n"],
                    "Select the reference point FIRST, then 2+ more points.")
        return (False, "")
    return (False, "")

# ============================================================
# 8. EXECUTION + PROGRAM TRACE
# ============================================================
def add_program(line): st.session_state.program.append(line)
def add_log(text):     st.session_state.log.append(text)

# ---- single-step UNDO -------------------------------------------------------
_UNDO_KEYS = ["selection", "selection_meta", "annotations", "lines", "angles", "named_edges",
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
    clear_selection()
    st.rerun()

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
    add_log(f"`{call_str}` — **smallest → largest:**  {ordered}")
    clear_selection()
    st.rerun()

def run_tool(tool, modes):
    sel = st.session_state.selection
    s = sel_sig()
    try:
        # ---- VERTEX --------------------------------------------------------
        if tool == "vertex":
            if s["frame"]:
                which = modes["which"]
                result = T.vertex("frame", which=which)
                finish(tool, f'vertex("frame", which="{which}")', result,
                       "v" if not isinstance(result, list) else "r")
            elif len(s["regions"]) >= 2:
                onf = modes["on_frame"]
                result = T.vertex(*s["regions"], on_frame=onf)
                args = ", ".join(o.letter for o in s["regions"])
                finish(tool, f"vertex({args}, on_frame={onf})", result,
                       "v" if not isinstance(result, list) else "r")
            else:
                reg = s["regions"][0]
                which = modes["which"]
                result = T.vertex(reg, which=which)
                finish(tool, f'vertex({reg.letter}, which="{which}")', result,
                       "v" if not isinstance(result, list) else "r")

        # ---- NEIGHBORS -----------------------------------------------------
        elif tool == "neighbors":
            # several EDGES → union of the regions on either side of each
            # (each edge drops its own owning region). T.neighbors of a raw
            # half-edge returns both bordering faces; we filter + dedupe here.
            if s["edges"] and not s["regions"] and not s["vertices"]:
                seen, result, names = set(), [], []
                for es in s["edges"]:
                    owner = es.owner
                    for seg in es.segments:
                        for face in T.neighbors(seg):
                            if owner is not None and face is owner:
                                continue
                            if id(face) not in seen:
                                seen.add(id(face))
                                result.append(face)
                    names.append(edge_name(es) or "edge")
                call = (f"neighbors([{', '.join(names)}])"
                        if len(names) > 1 else f"neighbors({names[0]})")
                finish(tool, call, result)

            # several POINTS → union of the regions meeting at any of them
            elif s["vertices"] and not s["regions"]:
                seen, result = set(), []
                for v in s["vertices"]:
                    for face in T.neighbors(v):
                        if id(face) not in seen:
                            seen.add(id(face))
                            result.append(face)
                names = [code_name(v) for v in s["vertices"]]
                call = (f"neighbors([{', '.join(names)}])"
                        if len(names) > 1 else f"neighbors({names[0]})")
                finish(tool, call, result)

            elif s["regions"] and s["vertices"]:
                reg, vtx = s["regions"][0], s["vertices"][0]
                ccw = modes.get("ccw", True)
                result = T.neighbors(reg, "ordered", start=vtx, go_counterclockwise=ccw)
                finish(tool, f'neighbors({reg.letter}, "ordered", start={code_name(vtx)}, '
                             f"go_counterclockwise={ccw})", result)

            else:
                reg = s["regions"][0]
                kind = modes["kind"]
                result = T.neighbors(reg, kind)
                finish(tool, f'neighbors({reg.letter}, "{kind}")', result)

        # ---- DRAW LINE -----------------------------------------------------
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
            clear_selection()
            st.rerun()

        # ---- INTERSECT -----------------------------------------------------
        elif tool == "intersect":
            lname, line = modes["line"]
            if modes["target"] == "faces":
                result = T.intersect(line, "faces")
                finish(tool, f'intersect({lname}, "faces")', result, visualize=False)
            else:
                tname, tline = modes["target"]
                result = T.intersect(line, tline)
                finish(tool, f"intersect({lname}, {tname})", result, visualize=False)

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
            add_log(f"`{uname} = merge({fa.letter}, {fb.letter})` → new solid region **{uname}**")
            clear_selection()
            st.rerun()

        # ---- MEASURE (one thing → one number) ------------------------------
        elif tool == "measure":
            w = modes["what"]

            if w == "length":
                if s["vertices"] and len(s["vertices"]) >= 2:
                    p, q = s["vertices"][0], s["vertices"][1]
                    val = T.measure(p, q, what="length")
                    finish(tool, f'measure({code_name(p)}, {code_name(q)}, what="length")',
                           round(val, 4))
                else:
                    lname, line = modes["line"]
                    val = T.measure(line, what="length")
                    finish(tool, f'measure({lname}, what="length")', round(val, 4),
                           visualize=False)

            elif w == "angle":
                # Measure EACH selected angle: one program line + one log line each.
                for a in s["angles"]:
                    val = T.measure(a.vertex, a.face, what="angle")
                    aname = angle_name(a)
                    call_str = f'measure({aname}, what="angle")'
                    var = next_name("r")
                    add_program(f"{var} = {call_str}")
                    add_log(f"`{call_str}` → **{round(val, 2)}°**")
                clear_selection()
                st.rerun()

            else:  # area, sides
                reg = s["regions"][0]
                val = T.measure(reg, what=w)
                finish(tool, f'measure({reg.letter}, what="{w}")', val)

        # ---- SORT (several things → ordered) --------------------------------
        elif tool == "sort":
            by = modes["by"]

            if by == "angle":
                reg = s["regions"][0]
                corners = T.vertex(reg, which="all")
                result = T.sort(corners, by="angle", reference=reg)
                call_str = (f'sort(vertex({reg.letter}, which="all"), by="angle", '
                            f'reference={reg.letter})')

                # Annotate an interior ARC for every corner (not a raw point dot),
                # reusing any angle already saved for that corner+region.
                for corner in result:
                    existing = next(
                        (nm for nm, a_sel in st.session_state.angles
                         if a_sel.vertex is corner and a_sel.face is reg),
                        None)
                    if existing is None:
                        aname = next_name("a")
                        a_sel = AngleSel(corner, reg)
                        st.session_state.angles.append((aname, a_sel))
                        st.session_state.annotations.append(
                            {"kind": "angle", "vertex": corner, "face": reg, "label": aname})

                ranking_finish(call_str, result, "angle", reg)

            elif by == "area":
                regs = list(s["regions"])
                result = T.sort(regs, by="area")
                arg = ", ".join(o.letter for o in regs)
                ranking_finish(f'sort([{arg}], by="area")', result, "area", None)

            elif by in ("left_right", "bottom_top"):
                pts = list(s["vertices"])
                result = T.sort(pts, by=by)
                arg = ", ".join(code_name(o) for o in pts)
                ranking_finish(f'sort([{arg}], by="{by}")', result, by, None)

            else:  # distance from the first-selected point
                ref, rest = s["vertices"][0], s["vertices"][1:]
                result = T.sort(rest, by="distance", reference=ref)
                arg = ", ".join(code_name(o) for o in rest)
                ranking_finish(
                    f'sort([{arg}], by="distance", reference={code_name(ref)})',
                    result, "distance", ref)

    except Exception as ex:
        add_log(f"❌ **{tool}** failed: {ex}")
        clear_selection()
        st.rerun()

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

    # The active tool's button gets a soft mint-green shade (no checkmark).
    # Streamlit tags each keyed button's wrapper with class "st-key-<key>",
    # so we inject one scoped CSS rule targeting only the active tool's button.
    _active_tool = st.session_state.active_tool
    if _active_tool:
        _active_key = f"tool_{_active_tool.replace(' ', '_')}"
        st.markdown(f"""
        <style>
        div[class*="st-key-{_active_key}"] button {{
            background-color: #e3f9ea;
            border-color: #8fd4a8;
            color: #1e5631;
        }}
        div[class*="st-key-{_active_key}"] button:hover {{
            background-color: #d2f2de;
            border-color: #6fc593;
            color: #1e5631;
        }}
        div[class*="st-key-{_active_key}"] button:focus:not(:active) {{
            border-color: #6fc593;
            color: #1e5631;
        }}
        </style>
        """, unsafe_allow_html=True)

    tcols = st.columns(2)
    for i, t_name in enumerate(TOOLS):
        display = TOOL_LABELS.get(t_name, t_name)
        if tcols[i % 2].button(display, key=f"tool_{t_name.replace(' ', '_')}",
                               use_container_width=True):
            st.session_state.active_tool = t_name
            st.rerun()

    tool = st.session_state.active_tool
    modes = {}

    # --- SELECTION ---
    st.subheader("Selection")
    if st.session_state.selection:
        st.markdown(_SELECTION_ROW_CSS, unsafe_allow_html=True)
        for i, o in enumerate(st.session_state.selection):
            row = st.container(key=f"sel_row_{i}")
            rcols = row.columns([9, 1])
            rcols[0].markdown(f"- {describe(o)}")
            if rcols[1].button("✕", key=f"sel_remove_{i}", help="Remove from selection"):
                push_undo()
                remove_selection_item(i)
                st.rerun()
    else:
        st.caption("(click the map to select regions, points, or edges)")

    if tool:
        display = TOOL_LABELS.get(tool, tool)
        st.markdown(f"### {display}")
        st.info(INSTRUCTIONS[tool])

        s = sel_sig()

        if tool == "vertex":
            if s["frame"]:
                modes["which"] = st.radio(
                    "Which frame corner?",
                    ["all", "top_left", "top_right", "bottom_left", "bottom_right"],
                    horizontal=True, key="rad_vtx_frame")
            elif len(s["regions"]) >= 2:
                modes["on_frame"] = st.radio(
                    "Is the meeting point on the frame?", [False, True],
                    format_func=lambda b: "Yes" if b else "No",
                    horizontal=True, key="rad_vtx_onframe")
            else:
                modes["which"] = st.radio(
                    "Which corner?",
                    ["all", "leftmost", "rightmost", "topmost", "bottommost",
                     "sharpest", "widest"],
                    horizontal=True, key="rad_vtx_corner")

        elif tool == "neighbors":
            if s["edges"] and not s["regions"] and not s["vertices"]:
                n = len(s["edges"])
                st.caption(f"{n} edge(s) selected → the regions on either side of each "
                           "(dropping each edge's own region).")
            elif s["vertices"] and not s["regions"]:
                n = len(s["vertices"])
                st.caption(f"{n} point(s) selected → every region meeting at any of them.")
            elif s["regions"] and s["vertices"]:
                modes["kind"] = "ordered"
                modes["ccw"] = st.radio(
                    "Walk direction", [True, False],
                    format_func=lambda b: "Counter-clockwise" if b else "Clockwise",
                    horizontal=True, key="rad_nbr_ccw")
                st.caption("Region + corner → the regions passed, in walking order.")
            elif s["regions"]:
                modes["kind"] = st.radio(
                    "Neighbor type", ["edge", "vertex"],
                    format_func=lambda k: "Share an edge" if k == "edge"
                    else "Touch only at a corner",
                    horizontal=True, key="rad_nbr_kind")

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

        elif tool == "measure":
            modes["what"] = st.radio("Measure what?",
                                     ["length", "angle", "area", "sides"],
                                     index=None, horizontal=True, key="rad_measure")
            if modes["what"] == "length":
                if len(s["vertices"]) >= 2:
                    st.caption("Will measure the distance between the two selected points.")
                else:
                    segs = [(nm, ln) for nm, ln in st.session_state.lines
                            if ln.get("type") == "segment"]
                    if segs:
                        idx = st.selectbox("Which drawn segment?", range(len(segs)),
                                           format_func=lambda i: segs[i][0],
                                           key="sel_len_line")
                        modes["line"] = segs[idx]
                    else:
                        st.caption("Draw a segment first, or select two points.")
            elif modes["what"] == "angle":
                if s["angles"]:
                    st.caption(f"{len(s['angles'])} angle(s) selected — each will be measured.")
                else:
                    st.caption("Pick saved angles (a1, a2…) from the map panel, or make one: "
                               "click a corner → 📐 Angle here → region.")

        elif tool == "sort":
            opts = []   # (label, internal_value)
            if len(s["regions"]) == 1 and s["n"] == 1:
                opts = [("This region's corners, by angle", "angle")]
            elif len(s["regions"]) >= 2 and len(s["regions"]) == s["n"]:
                opts = [("By area", "area")]
            elif len(s["vertices"]) >= 2 and len(s["vertices"]) == s["n"]:
                opts = [("Left → right", "left_right"), ("Bottom → top", "bottom_top")]
                if len(s["vertices"]) >= 3:
                    opts.append(("Distance from the first point", "distance"))
            if opts:
                label2val = dict(opts)
                choice = st.radio("Order how?", [o[0] for o in opts], key="rad_sort")
                modes["by"] = label2val[choice]
            else:
                st.caption("Select 2+ points, 2+ regions, or one region (for its corners).")

        # 'merge' has no modes.

        ready, msg = validate(tool, modes)
        if tool == "intersect" and modes.get("target") is None:
            ready = False
        if not ready:
            st.warning(msg)
        if st.button("▶ RUN", type="primary", disabled=not ready, use_container_width=True):
            push_undo()
            run_tool(tool, modes)
    else:
        st.caption("Pick a tool above to begin.")

# ----------------------------------------------------------------------------
# MIDDLE PANEL — DIAGRAM + selection-building buttons + saved objects
# ----------------------------------------------------------------------------
with col_map:
    display_img = render().resize((DISPLAY_SIDE, DISPLAY_SIDE), Image.Resampling.LANCZOS)

    # encode the rendered map + serialize hover geometry, then hand both to the
    # custom canvas component. Hovering is painted in the browser; clicks come
    # back as {x, y} exactly like the old streamlit_image_coordinates call.
    _buf = BytesIO()
    display_img.save(_buf, format="PNG")
    _img_b64 = base64.b64encode(_buf.getvalue()).decode()
    coords = geo_canvas(_img_b64, build_hover_shapes(), DISPLAY_SIDE, key="map_click")

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
        ccols = st.columns(2)
        for i, (label, kind, obj) in enumerate(candidate_buttons):
            if ccols[i % 2].button(label, key=f"cand_{i}", use_container_width=True):
                push_undo()
                if kind == "angle":
                    st.session_state.pending_angle_vertex = obj
                elif kind == "edge":
                    if edge_name(obj) is None:
                        st.session_state.named_edges.append((next_name("e"), obj))
                    add_to_selection(obj)
                    st.session_state.click_targets = None
                else:
                    meta = None
                    if kind == "vertex":
                        _name, meta = point_name_with_meta(obj)
                    add_to_selection(obj, meta)
                    st.session_state.click_targets = None
                st.rerun()

    pav = st.session_state.pending_angle_vertex
    if pav is not None:
        st.caption("Angle of which region?")
        regs = T.neighbors(pav)          # regions meeting at this point
        # If any of those regions has been merged, offer the angle of the UNION
        # rather than the now-hidden constituent region.
        cmap = _consumed_to_union_map()
        seen_u, regs2 = set(), []
        for rg in regs:
            rg = cmap.get(id(rg), rg)
            if id(rg) not in seen_u:
                seen_u.add(id(rg))
                regs2.append(rg)
        regs = regs2
        acols = st.columns(2)
        for i, rg in enumerate(regs):
            if acols[i % 2].button(f"angle of Region {rg.letter}",
                                   key=f"ang_{rg.letter}", use_container_width=True):
                push_undo()
                a_sel = AngleSel(pav, rg)
                aname = next_name("a")
                angle_entry = (aname, a_sel)
                st.session_state.angles.append(angle_entry)
                ann = {"kind": "angle", "vertex": pav, "face": rg, "label": aname}
                st.session_state.annotations.append(ann)
                add_to_selection(a_sel, {"kind": "angle", "angle_entry": angle_entry,
                                         "annotation_ref": ann})
                st.session_state.pending_angle_vertex = None
                st.session_state.click_targets = None
                st.rerun()

    # --- frame / clear ---
    ucols = st.columns(2)
    if ucols[0].button("Select FRAME", use_container_width=True):
        push_undo()
        add_to_selection("frame")
        st.rerun()
    if ucols[1].button("Clear selection", use_container_width=True):
        push_undo()
        clear_selection()
        st.session_state.click_targets = None
        st.session_state.pending_angle_vertex = None
        st.rerun()

    # --- SAVED OBJECTS BUFFER (angles + edges) ---
    # Unions are NOT listed here: a merged region is selected by clicking it
    # directly on the map (it shows up as "Region U1").
    saved = []
    for aname, a_sel in st.session_state.angles:
        saved.append((f"Select {aname} (angle, Region {a_sel.face.letter})", a_sel))
    for ename, e_sel in st.session_state.named_edges:
        saved.append((f"Select {ename} ({e_sel.text})", e_sel))
    if saved:
        st.caption("Saved objects:")
        scols = st.columns(2)
        for i, (label, obj) in enumerate(saved):
            if scols[i % 2].button(label, key=f"saved_{i}", use_container_width=True):
                push_undo()
                add_to_selection(obj)
                st.rerun()

# ----------------------------------------------------------------------------
# RIGHT PANEL — quick actions, scratch pad, then program trace + output log
# (scratch pad + actions on top so they're visible without scrolling; the
#  longer-growing Program/Output sit underneath in fixed-height scrollers.)
# ----------------------------------------------------------------------------
with col_io:
    st.subheader("Quick actions")
    qcols = st.columns(2)
    if qcols[0].button("↩ Undo last move", use_container_width=True,
                       disabled=not st.session_state.undo_stack):
        undo_last()
    if qcols[1].button("Clear drawings & program", use_container_width=True):
        for k in ["annotations", "lines", "angles", "named_edges", "unions",
                  "union_consumed", "undo_stack", "program", "log"]:
            st.session_state[k] = []
        st.session_state.point_names = {}
        st.session_state.counters = {"v": 1, "L": 1, "U": 1, "r": 1, "a": 1, "e": 1}
        st.rerun()
    if qcols[0].button("Clear output log", use_container_width=True):
        st.session_state.log = []
        st.rerun()
    if qcols[1].button("New random map", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

    st.subheader("📝 Scratch pad")
    st.text_area("scratch", key="scratch_pad", height=120,
                 label_visibility="collapsed",
                 placeholder="Free-form notes / answers. Kept until you load a new map.")

    st.subheader("Program")
    if st.session_state.program:
        with st.container(height=200):
            st.code("\n".join(st.session_state.program), language="python")
    else:
        st.caption("(your actions become code here)")

    st.subheader("Output")
    if not st.session_state.log:
        st.caption("(results will appear here)")
    else:
        with st.container(height=220):
            for entry in reversed(st.session_state.log[-25:]):
                st.markdown(entry)