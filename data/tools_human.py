"""
tools_human.py

A point-and-click vocabulary of exactly SIX verbs for solving map-region
problems. The six verbs below are the whole public surface — there are no
lower-level getters to learn. Anything more specific (which corner, which
walk direction, value-vs-ranking) is a *mode* of one of the six, chosen in
the UI, not a separate verb.

THE SIX VERBS
-------------
    vertex      get a point
                  one region            -> a corner of it
                  two or more regions   -> the point where they meet
                  the frame             -> a frame corner
    neighbors   get regions
                  a point               -> the regions meeting there
                  a region              -> the regions bordering it
                                           (share an edge, touch at a corner,
                                            or in walking order from a corner)
    draw        make a line             (segment, full line, or ray)
    intersect   ask a line what it hits (which regions, or another line)
    merge       join two bordering regions into one
    measure     a property of the selection
                  one object            -> a single number
                  several objects       -> them ranked, smallest -> largest

Everything in / everything out is a plain object (a Point, a Region, a Line, a
list, a number, or a boolean), so verbs chain by clicking.

SETUP
-----
    import tools_human as t
    t.setup(my_map)
"""

import map_helpers as _engine


# ==============================================================================
# SETUP
# ==============================================================================

def setup(map):
    """Load the diagram. Call once when the interface starts."""
    _engine.use_map(map)


# ==============================================================================
# VERB 1 — VERTEX     (get a point)
# ==============================================================================

def vertex(*objs, which="all", on_frame=False):
    """
    Returns a vertex (or, with which="all", every vertex).

    ONE REGION            -> a corner of it, chosen by `which`:
        "all", "leftmost", "rightmost", "topmost", "bottommost",
        "sharpest", "widest"
    THE FRAME ("frame")   -> a frame corner, chosen by `which`:
        "all", "top_left", "top_right", "bottom_left", "bottom_right"
    TWO OR MORE REGIONS   -> the single point where they all meet
                             (set on_frame=True if it lies on the frame).

    Examples:
        vertex(A, which="rightmost")
        vertex("frame", which="top_left")
        vertex(E, C, on_frame=True)
    """
    if len(objs) == 1 and objs[0] == "frame":
        return _frame_corner(which)
    if len(objs) == 1:
        return _region_corner(objs[0], which)
    return _engine.vertex_overlap(*objs, on_frame=on_frame)


# ==============================================================================
# VERB 2 — NEIGHBORS     (get regions)
# ==============================================================================

def neighbors(obj, kind="edge", start=None, go_counterclockwise=True):
    """
    Returns the regions related to the selection.

    A POINT                  -> every region that meets at that point.
    A REGION, kind="edge"    -> regions sharing a full edge (a border).
    A REGION, kind="vertex"  -> regions touching only at a corner.
    A REGION, kind="ordered" -> the bordering regions in walking order;
        give start=<a corner> and go_counterclockwise=<True/False>.
        (CCW -> regions on the right; CW -> regions on the left. Returns []
        if a corner where 3+ regions meet makes the order ambiguous.)

    Examples:
        neighbors(p)
        neighbors(A, "edge")
        neighbors(A, "vertex")
        neighbors(A, "ordered", start=p, go_counterclockwise=True)
    """
    if _is_point(obj):
        return _engine.regions_at(obj)
    if kind == "edge":
        return _engine.edge_neighbors(obj)
    if kind == "vertex":
        return _engine.vertex_only_neighbors(obj)
    if kind == "ordered":
        return _boundary_walk(obj, start, go_counterclockwise)
    raise ValueError('kind must be "edge", "vertex", or "ordered".')


# ==============================================================================
# VERB 3 — DRAW     (make a line)
# ==============================================================================

def draw(a, b=None, kind="segment"):
    """
    Draws a line you can then intersect with regions.

      * an EDGE                 -> draw(edge)            (uses the edge's ends)
      * TWO vertices            -> draw(p, q)
      * ONE vertex + direction  -> draw(p, "up"/"down"/"left"/"right")  (a ray)

    kind: "segment" (default) or "full" (the infinite line through the points).
          (kind is ignored when drawing a ray.)
    """
    if b is None and hasattr(a, "head") and hasattr(a, "tail"):
        pa, pb = a.tail, a.head
        return _engine.extend(pa, pb) if kind == "full" else _engine.segment(pa, pb)
    if isinstance(b, str):
        return _engine.ray(a, b)
    if b is None:
        raise ValueError("draw needs an edge, two points, or a point and a direction.")
    return _engine.extend(a, b) if kind == "full" else _engine.segment(a, b)


# ==============================================================================
# VERB 4 — INTERSECT     (ask a line what it hits)
# ==============================================================================

def intersect(line, target="faces"):
    """
    target = "faces"       -> regions the line passes through, in travel order
                              (a full/infinite line returns them unordered).
    target = another line  -> True/False: do the two lines cross?

    Examples:
        intersect(line, "faces")
        intersect(draw(p, q), draw(u, v))
    """
    if target == "faces":
        if isinstance(line, dict) and line.get("type") == "extend":
            return list(_engine.regions_crossed(line))
        return _engine.regions_in_order(line)
    if isinstance(target, dict) and "type" in target:
        return _engine.crosses(line, target)
    raise ValueError('target must be "faces" or another drawn line.')


# ==============================================================================
# VERB 5 — MERGE     (join two bordering regions)
# ==============================================================================

def merge(region_a, region_b):
    """
    Join two regions that share a border into one combined region. The result
    behaves like any region: measure its area or sides, ask for its neighbors.
    """
    return _engine.merge(region_a, region_b)


# ==============================================================================
# VERB 6 — MEASURE     (a property of the selection)
# ==============================================================================

def measure(*args, what, reference=None):
    """
    ONE object  -> a single number.   SEVERAL objects -> a ranking (small->large).

    what:
        "distance"  2 points   -> distance between them
                    3+ points  -> first point is the reference; the rest are
                                  ranked by distance from it
        "gap"       2 regions  -> gap between them
                    3+ regions -> first region is the reference; the rest are
                                  ranked by gap from it
        "angle"     1 region   -> its corners ranked by interior angle
                    point+region -> the interior angle (degrees) at that corner
        "area"      1 region   -> area        | 2+ regions -> ranked
        "sides"     1 region   -> side count  | 2+ regions -> ranked
        "x"         1 point    -> x position  | 2+ points  -> ranked left->right
        "y"         1 point    -> y position  | 2+ points  -> ranked bottom->top

    Examples:
        measure(A, what="area")
        measure(A, B, C, what="area")          # ranked
        measure(p, u, v, w, what="distance")   # p is the reference
        measure(X, what="angle")               # corners of X, ranked
    """
    import numpy as _np
    items = list(args)

    if what == "angle":
        if len(items) == 1 and _is_region(items[0]):
            reg = items[0]
            return _rank(_region_corner(reg, "all"), "angle", reg)
        return _engine.angle_at(items[0], items[1]) * 180.0 / _np.pi

    if what in ("area", "sides", "x", "y"):
        return _measure_one(items[0], what) if len(items) == 1 else _rank(items, what)

    if what == "distance":
        if len(items) == 2 and reference is None:
            return _engine.dist(items[0], items[1])
        ref = reference if reference is not None else items[0]
        rest = items if reference is not None else items[1:]
        return _rank(rest, "distance", ref)

    if what == "gap":
        if len(items) == 2 and reference is None:
            return _engine.region_dist(items[0], items[1])
        ref = reference if reference is not None else items[0]
        rest = items if reference is not None else items[1:]
        return _rank(rest, "gap", ref)

    raise ValueError('what must be one of: distance, gap, angle, area, sides, x, y.')


# ==============================================================================
# PRIVATE IMPLEMENTATION  (not part of the vocabulary)
# ==============================================================================

def _is_point(o):
    return hasattr(o, "outarcs")

def _is_region(o):
    return hasattr(o, "edges") and hasattr(o, "bounded")


_CORNER_MODES = {
    "leftmost":   _engine.leftmost,
    "rightmost":  _engine.rightmost,
    "topmost":    _engine.topmost,
    "bottommost": _engine.bottommost,
    "sharpest":   _engine.sharpest_corner,
    "widest":     _engine.widest_corner,
}


def _region_corner(region, which):
    if which == "all":
        return _engine.vertices(region)
    if which not in _CORNER_MODES:
        raise ValueError(
            'region corner must be one of: "all", "leftmost", "rightmost", '
            '"topmost", "bottommost", "sharpest", "widest".')
    return _CORNER_MODES[which](region)


def _frame_corner(which):
    pts = {
        "bottom_left":  _engine.frame_corner("bottom_left"),
        "bottom_right": _engine.frame_corner("bottom_right"),
        "top_right":    _engine.frame_corner("top_right"),
        "top_left":     _engine.frame_corner("top_left"),
    }
    if which == "all":
        return list(pts.values())
    if which in pts:
        return pts[which]
    raise ValueError(
        'frame corner must be one of: "all", "top_left", "top_right", '
        '"bottom_left", "bottom_right".')


def _boundary_walk(face, start_vertex, go_counterclockwise):
    import Graph as _g
    edges = face.edges
    n = len(edges)
    if n == 0:
        return []

    start_idx = None
    for i, e in enumerate(edges):
        if e.tail == start_vertex:
            start_idx = i
            break
    if start_idx is None:
        for i, e in enumerate(edges):
            if _g.vecDist(e.tail.p, start_vertex.p) < 1e-9:
                start_idx = i
                break
    if start_idx is None:
        return []

    result = []
    for k in range(n):
        e = edges[(start_idx + k) % n]
        nb = e.reverse.leftFace
        if not result or result[-1] != nb:
            result.append(nb)
    if len(result) > 1 and result[0] == result[-1]:
        result.pop()
    if not go_counterclockwise:
        result.reverse()
    return result


def _measure_one(obj, what):
    if what == "area":  return _engine.area(obj)
    if what == "sides": return _engine.side_count(obj)
    if what == "x":     return _engine.x_of(obj)
    if what == "y":     return _engine.y_of(obj)


def _rank(items, by, reference=None):
    if by == "distance":
        key = lambda it: _engine.dist(it, reference)
    elif by == "x":
        key = _engine.x_of
    elif by == "y":
        key = _engine.y_of
    elif by == "angle":
        key = lambda it: _engine.angle_at(it, reference)
    elif by == "area":
        key = _engine.area
    elif by == "sides":
        key = _engine.side_count
    elif by == "gap":
        key = lambda it: _engine.region_dist(it, reference)
    else:
        raise ValueError('cannot rank by ' + repr(by))
    return sorted(items, key=key)


# The six human verbs — the entire public vocabulary.
VERBS = ["vertex", "neighbors", "draw", "intersect", "merge", "measure"]
