"""
tools_human.py

A small set of CONDENSED, clickable verbs for humans solving map region problems
through a point-and-click interface.

DESIGN
------
The interface is built around a tiny set of polymorphic verbs. Each verb has a
short menu of "modes" that the UI surfaces as sub-buttons. The typical flow is:

    1. The user CLICKS an object on the diagram (a vertex, an edge, a region).
    2. The user CLICKS a verb button (e.g. "corner", "draw", "intersect").
    3. If the verb has modes, the UI shows a small sub-menu (e.g. "leftmost",
       "rightmost", "sharpest"...).
    4. The verb returns a new object, which becomes the new selection and can be
       fed into the next verb.

Because everything in / everything out is a plain object (a Point, a Region, a
Line, a list, a number, or a boolean), verbs chain naturally by clicking.

SETUP
-----
Call setup(map) once when the diagram loads:

    import tools_human as t
    t.setup(my_map)

EXAMPLE (Question 10 - sort u, v, w by distance from p)
-------
    p = meeting_point(E, C, on_frame=True)
    u = corner(J, "rightmost")
    v = meeting_point(C, H, on_frame=True)
    w = meeting_point(I, L, H, on_frame=True)
    sort([u, v, w], by="distance", reference=p)

EXAMPLE (Question 18 - travel from p to q, which regions in order)
-------
    line = draw(p, q)              # a segment
    intersect(line, "faces")       # ordered list of regions passed through

This module relies on the engine in map_helpers.py. It does not import anything
from the Questions module.
"""

import map_helpers as _engine


# ==============================================================================
# SETUP
# ==============================================================================

def setup(map):
    """
    Loads the diagram. Call once when the interface starts, before any verb
    that draws or intersects lines.

    Example:
        setup(my_map)
    """
    _engine.use_map(map)


# ==============================================================================
# GET A POINT
# Verbs that turn a region (or regions) into a single point.
# ==============================================================================

# which-mode -> engine getter, used by corner()
_CORNER_MODES = {
    "leftmost":   _engine.leftmost,
    "rightmost":  _engine.rightmost,
    "topmost":    _engine.topmost,
    "bottommost": _engine.bottommost,
    "sharpest":   _engine.sharpest_corner,
    "widest":     _engine.widest_corner,
}


def corner(obj, which="all"):
    """
    Returns one or more corners of a region or the outer frame.

    REGION MODES:
        "all"
        "leftmost"
        "rightmost"
        "topmost"
        "bottommost"
        "sharpest"
        "widest"

    FRAME MODES:
        "all"
        "top_left"
        "top_right"
        "bottom_left"
        "bottom_right"

    Examples:
        corner(A, "rightmost")
        corner(A, "all")

        corner("frame", "top_left")
        corner("frame", "all")
    """

    if obj == "frame":

        frame_points = {
            "bottom_left":  _engine.frame_corner("bottom_left"),
            "bottom_right": _engine.frame_corner("bottom_right"),
            "top_right":    _engine.frame_corner("top_right"),
            "top_left":     _engine.frame_corner("top_left"),
        }

        if which == "all":
            return list(frame_points.values())

        if which in frame_points:
            return frame_points[which]

        raise ValueError(
            'frame mode must be one of: '
            '"all", "top_left", "top_right", '
            '"bottom_left", "bottom_right".'
        )

    if which == "all":
        return _engine.vertices(obj)

    if which not in _CORNER_MODES:
        raise ValueError(
            'region mode must be one of: '
            '"all", "leftmost", "rightmost", '
            '"topmost", "bottommost", '
            '"sharpest", "widest".'
        )

    return _CORNER_MODES[which](obj)


def meeting_point(*regions, on_frame=False):
    """
    Returns the single point where the given regions all meet.

    CLICK FLOW: click two or more regions -> click "meeting point".
    Toggle "on frame" if the point also sits on the outer frame.

    Example:
        meeting_point(E, C, on_frame=True)
    """
    return _engine.vertex_overlap(*regions, on_frame=on_frame)


def boundary_sequence(face, start_vertex, go_counterclockwise=True):
    """
    Walk the boundary of `face` starting at `start_vertex` and return the
    neighboring regions encountered, in the order you pass them.

    go_counterclockwise = True  (default) → CCW travel; regions on the RIGHT.
    go_counterclockwise = False           → CW  travel; regions on the LEFT.

    Returns an ordered list of regions (a region that borders two consecutive
    edges appears only once in a run, but re-appears if you come back to it).
    Returns [] if any vertex along the boundary is ambiguous (3+ regions meeting
    at a single corner), because the sequence would be unclear.

    CLICK FLOW: click a region → click a vertex on it → click "boundary sequence"
                → toggle CW / CCW.

    Example:
        boundary_sequence(A, p)                   # CCW from p
        boundary_sequence(A, p, go_counterclockwise=False)  # CW from p
    """
    import Graph as _g
    edges = face.edges
    n = len(edges)
    if n == 0:
        return []

    # Locate the boundary edge whose TAIL is the chosen start vertex.
    # Fall back to a positional match (subdivision points can make object
    # identity unreliable on a freshly built map).
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

    # Walk the whole boundary once, collecting the region on the far side of
    # each edge. Consecutive edges that border the same region collapse into a
    # single entry; a region re-entered later in the walk re-appears.
    result = []
    for k in range(n):
        e = edges[(start_idx + k) % n]
        nb = e.reverse.leftFace
        if not result or result[-1] != nb:
            result.append(nb)

    # If the walk closed back onto the same region it started in, drop the
    # duplicate tail so the loop isn't double-counted.
    if len(result) > 1 and result[0] == result[-1]:
        result.pop()

    if not go_counterclockwise:
        result.reverse()
    return result


# ==============================================================================
# DRAW A LINE
# One verb that builds a segment, a full (infinite) line, or a ray.
# ==============================================================================

def draw(a, b=None, kind="segment"):
    """
    Draws a line you can then intersect with regions.

    CLICK FLOW (three natural cases):
      * Click an EDGE, then "draw"            -> a, b=None        (uses the edge's two ends)
      * Click TWO vertices, then "draw"       -> a=point, b=point
      * Click ONE vertex, then "draw" -> "ray"-> a=point, b="up"/"down"/"left"/"right"

    kind is one of:
        "segment"  - the finite piece between the two points (default)
        "full"     - the infinite straight line through the two points
    (kind is ignored when drawing a ray.)

    Example:
        draw(p, q)                  # segment from p to q
        draw(p, q, kind="full")     # infinite line through p and q
        draw(some_edge)             # segment along a selected edge
        draw(p, "right")            # ray going right from p
    """
    # Case 1: a selected edge (has .head/.tail), no second point.
    if b is None and hasattr(a, "head") and hasattr(a, "tail"):
        pa, pb = a.tail, a.head
        return _engine.extend(pa, pb) if kind == "full" else _engine.segment(pa, pb)

    # Case 2: a point plus a direction word -> ray.
    if isinstance(b, str):
        return _engine.ray(a, b)

    # Case 3: two points -> segment or full line.
    if b is None:
        raise ValueError("draw needs an edge, two points, or a point and a direction.")
    return _engine.extend(a, b) if kind == "full" else _engine.segment(a, b)


# ==============================================================================
# INTERSECT
# One verb that answers "what does this line hit?"
# ==============================================================================

def intersect(line, target="faces"):
    """
    Reports what a drawn line meets.

    CLICK FLOW: select a drawn line -> click "intersect" -> pick a target.

    target is one of:
        "faces"        - the regions the line passes through, in the order you
                         enter them (a region you enter twice is listed twice).
        another line   - returns True/False for whether the two lines cross.

    Example:
        intersect(line, "faces")                 # regions along the line, in order
        intersect(draw(p, q), draw(u, v))        # do these two segments cross?
    """
    if target == "faces":
        # A full (infinite) line has no canonical start, so report the set of
        # regions it passes through. A segment or ray is ordered along travel.
        if isinstance(line, dict) and line.get("type") == "extend":
            return list(_engine.regions_crossed(line))
        return _engine.regions_in_order(line)
    if isinstance(target, dict) and "type" in target:
        return _engine.crosses(line, target)
    raise ValueError('target must be "faces" or another drawn line.')


# ==============================================================================
# REGION RELATIONSHIPS
# ==============================================================================

def neighbors(region, kind="edge"):
    """
    Returns the regions touching the given region.

    CLICK FLOW: click a region -> click "neighbors" -> pick a mode.

    kind is one of:
        "edge"    - regions that share a full edge (a border) with this region
        "vertex"  - regions that touch only at a single corner, sharing no edge

    Example:
        neighbors(A, "edge")
        neighbors(A, "vertex")
    """
    if kind == "edge":
        return _engine.edge_neighbors(region)
    if kind == "vertex":
        return _engine.vertex_only_neighbors(region)
    raise ValueError('kind must be "edge" or "vertex".')


def regions_at(point):
    """
    Returns every region that meets at the given point.

    CLICK FLOW: click a vertex -> click "regions here".

    Example:
        regions_at(p)
    """
    return _engine.regions_at(point)


def merge(region_a, region_b):
    """
    Joins two regions that share a border into one combined region. The result
    behaves like any other region (you can measure its area, count its sides,
    or ask for its neighbors).

    CLICK FLOW: click two bordering regions -> click "merge".

    Example:
        measure(merge(A, B), what="sides")
        neighbors(merge(A, B), "edge")
    """
    return _engine.merge(region_a, region_b)


# ==============================================================================
# MEASURE
# One verb for every single-number measurement.
# ==============================================================================

def measure(*args, what):
    """
    Returns a single number describing the selected object(s).

    CLICK FLOW: select object(s) -> click "measure" -> pick what to measure.
    (The UI only needs to offer the modes that fit the current selection.)

    what is one of:
        "distance"  - between two points         -> measure(p, q, what="distance")
        "gap"       - between two regions         -> measure(A, B, what="gap")
        "angle"     - of a region at a vertex     -> measure(p, A, what="angle")   [degrees]
        "area"      - of a region                 -> measure(A, what="area")
        "sides"     - number of sides of a region -> measure(A, what="sides")
        "x"         - left-right position         -> measure(p, what="x")
        "y"         - up-down position            -> measure(p, what="y")
    """
    import numpy as _np
    if what == "distance":
        return _engine.dist(args[0], args[1])
    if what == "gap":
        return _engine.region_dist(args[0], args[1])
    if what == "angle":
        return _engine.angle_at(args[0], args[1]) * 180.0 / _np.pi
    if what == "area":
        return _engine.area(args[0])
    if what == "sides":
        return _engine.side_count(args[0])
    if what == "x":
        return _engine.x_of(args[0])
    if what == "y":
        return _engine.y_of(args[0])
    raise ValueError('what must be one of: distance, gap, angle, area, sides, x, y.')


# ==============================================================================
# ORDER & COMPARE
# ==============================================================================

def sort(items, by, reference=None):
    """
    Returns the items ordered smallest-to-largest by some criterion.

    CLICK FLOW: select several objects -> click "sort" -> pick a criterion ->
    (if needed) click the reference object.

    by is one of:
        "distance"  - points, by distance from `reference` (a point)
        "x"         - points, left to right
        "y"         - points, bottom to top
        "angle"     - corners of `reference` (a region), by interior angle
        "area"      - regions, smallest area first
        "sides"     - regions, fewest sides first
        "gap"       - regions, by distance from `reference` (a region)

    Example:
        sort([u, v, w], by="distance", reference=p)
        sort([A, B, C], by="area")
        sort(corner(A, "all"), by="angle", reference=A)
    """
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
        raise ValueError('by must be one of: distance, x, y, angle, area, sides, gap.')
    return sorted(items, key=key)


def closer(target, a, b):
    """
    Returns whichever of a or b is closer to target.

    Works for regions (uses the gap between regions) or points (uses straight
    distance). Use this for "which region is closer to X" questions.

    CLICK FLOW: click the target -> click "closer" -> click the two candidates.

    Example:
        closer(A, B, C)      # is region B or region C closer to region A?
    """
    if hasattr(target, "edges"):  # region
        da = _engine.region_dist(target, a)
        db = _engine.region_dist(target, b)
    else:                          # point
        da = _engine.dist(target, a)
        db = _engine.dist(target, b)
    return a if da <= db else b


VERBS = [
    "corner",
    "meeting_point",
    "boundary_sequence",

    "draw",
    "intersect",

    "neighbors",
    "regions_at",
    "merge",

    "measure",
    "sort",
    "closer",
]