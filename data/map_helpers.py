"""
map_helpers.py

A composable vocabulary of spatial helper functions for solving map region questions.

These functions are designed to be readable and writable by non-experts.
They can be combined freely to express complex spatial queries in plain terms.

SETUP
-----
Before using any of the line-crossing queries (regions_crossed, regions_in_order),
or frame_corner, call use_map(map) once so the helpers know which diagram to work on:

    import map_helpers as mh
    mh.use_map(my_map)

EXAMPLE (Question 10 - sort u, v, w by distance from p)
-------
    p = vertex_overlap(E, C, on_frame=True)
    u = rightmost(J)
    v = vertex_overlap(C, H, on_frame=True)
    w = vertex_overlap(I, L, H, on_frame=True)
    sort([u, v, w], key=lambda pt: dist(pt, p))

This module depends only on the shared geometry modules Graph and FinalizeFaces.
It does NOT import anything from the Questions module - every operation it needs
is implemented privately below.
"""

import numpy as np
import Graph
import FinalizeFaces


# ==============================================================================
# CONSTANTS
# ==============================================================================

epsilon = 0.0001
angleeps = 0.00001
smallDist = 0.07
smallAng = 0.1

# The current diagram. Set this once with use_map(map) before running queries.
_MAP = None


def use_map(map):
    """
    Tells the helpers which diagram (map) to work on.

    Call this once at the start, before using any query that needs to look at
    the whole diagram: regions_crossed, regions_in_order, or frame_corner.

    Example:
        use_map(my_map)
    """
    global _MAP
    _MAP = map


# ==============================================================================
# PRIVATE INTERNALS
# These are the lower-level routines that the public functions are built on.
# Non-experts do not need to call these directly.
# ==============================================================================

class _PseudoFace:
    """A synthetic region produced by merging two real regions."""
    def __init__(self, vertices, edges):
        self.vertices = vertices
        self.edges = edges
        self.bounded = True
        self.convex = Graph.computeConvex(self)
        self.box = Graph.BoundingBox(self)
        self.trueVertices = FinalizeFaces.SetTrueVertices(self)
        self.numSides = len(self.trueVertices) - 1
        self.letter = 'Z'


def _signed_dist(p1, p2, n):
    """Signed distance of p1 from the line through p2 with unit normal n."""
    return ((p1.x - p2.x) * n.x) + ((p1.y - p2.y) * n.y)


def _cross_lines(pa, pb, pc, pd):
    """
    Returns (crosses, quality): whether segment pa-pb crosses segment pc-pd,
    plus a confidence score. quality == 0 means the configuration is too
    ambiguous (near-parallel or near-touching) to judge cleanly.
    """
    nab = Graph.UnitNormal(pa, pb)
    ncd = Graph.UnitNormal(pc, pd)
    dota = _signed_dist(pa, pc, ncd)
    dotb = _signed_dist(pb, pc, ncd)
    dotc = _signed_dist(pc, pa, nab)
    dotd = _signed_dist(pd, pa, nab)
    if (dota * dotb < 0) and (dotc * dotd) < 0:
        answer = True
        quality = min(abs(dota), abs(dotb), abs(dotc), abs(dotd))
    else:
        answer = False
        if (dota * dotb < 0):
            quality = min(abs(dotc), abs(dotd))
        elif (dotc * dotd < 0):
            quality = min(abs(dota), abs(dotb))
        else:
            quality = max(min(abs(dotc), abs(dotd)), min(abs(dota), abs(dotb)))
    if quality < 0.02:
        quality = 0
    return answer, quality


def _one_point_def_side(aj, bj):
    """Definite left/right test for a single vertex relative to a line."""
    left = (aj > np.pi / 2 and bj > -np.pi / 2) or (aj < np.pi / 2 and bj < -np.pi / 2)
    right = (aj > -np.pi / 2 and bj > np.pi / 2) or (aj < -np.pi / 2 and bj < np.pi / 2)
    return left, right


def _two_point_def_side(aj, ak, bj, bk, visible_seg):
    """Definite left/right test for an edge (two vertices) relative to a line."""
    left = visible_seg and ((aj > np.pi / 2 and bj > -np.pi / 2) or (aj < np.pi / 2 and bj < -np.pi / 2))
    left = left or (aj > np.pi / 2 and ak < np.pi / 2) or (aj < np.pi / 2 and ak > np.pi / 2)
    left = left or (bj > -np.pi / 2 and bk < -np.pi / 2) or (bj < -np.pi / 2 and bk > -np.pi / 2)
    right = visible_seg and ((aj > -np.pi / 2 and bj > np.pi / 2) or (aj < -np.pi / 2 and bj < np.pi / 2))
    right = right or (bj > np.pi / 2 and bk < np.pi / 2) or (bj < np.pi / 2 and bk > np.pi / 2)
    right = right or (aj > -np.pi / 2 and ak < -np.pi / 2) or (aj < -np.pi / 2 and ak > -np.pi / 2)
    return left, right


def _line_crosses_faces(pa, pb, infinite_line, map):
    """
    Returns (faces, quality): every bounded region whose interior the line
    pa-pb passes through.

    infinite_line=True treats pa-pb as an infinite line (extended both ways).
    infinite_line=False treats it as the finite segment from pa to pb.
    """
    d = Graph.vecDist(pa, pb)
    if d < epsilon:
        return [], -1
    # Vertices keep their original creation num (never renumbered), which can be
    # larger than len(map.vertices) after rolled-back splits. Size by max num.
    n = max(v.num for v in map.vertices) + 1
    angleAtA = [100] * n
    angleAtB = [100] * n
    coins = []
    for v in map.vertices:
        i = v.num
        if Graph.vecDist(v.p, pa) < epsilon or Graph.vecDist(v.p, pb) < epsilon:
            coins += [v]
        else:
            angleAtA[i] = Graph.signedAngle(pb, pa, v.p)
            angleAtB[i] = Graph.signedAngle(pa, pb, v.p)
    crossedFaces = []
    quality = 100
    for f in map.faces[1:]:
        extremeLeft = -100
        extremeRight = 100
        nv = len(f.vertices) - 1
        for i in range(nv):
            v1 = f.vertices[i]
            j = v1.num
            if (v1 in coins or abs(angleAtA[j]) < angleeps):
                continue
            v2 = f.vertices[i + 1]
            k = v2.num
            if angleAtA[j] > 0:
                dval = max(angleAtA[j], -angleAtB[j])
            else:
                dval = min(angleAtA[j], -angleAtB[j])
            extremeLeft = max(extremeLeft, np.sin(dval))
            extremeRight = min(extremeRight, np.sin(dval))
            if v2 in coins:
                dLeft, dRight = _one_point_def_side(angleAtA[j], angleAtB[j])
            else:
                dLeft, dRight = _two_point_def_side(
                    angleAtA[j], angleAtA[k], angleAtB[j], angleAtB[k], infinite_line)
            if dLeft:
                extremeLeft = 1
            if dRight:
                extremeRight = -1
        if -smallAng < extremeLeft < smallAng or -smallAng < extremeRight < smallAng:
            return [], -1
        if extremeLeft > smallAng and extremeRight < -smallAng:
            crossedFaces += [f]
        quality = min(quality, abs(extremeLeft), abs(extremeRight))
    return crossedFaces, quality


def _faces_crossed_in_order(pa, pb, faces):
    """
    Given the (unordered) set of regions a line passes through, returns them
    in the order they are entered when travelling from pa to pb. A region that
    is entered, left, and re-entered appears more than once.
    """
    currentFace = False
    fine = int(100 * (abs(pb.x - pa.x) + abs(pb.y - pa.y)))
    if fine <= 0:
        return []
    crossedFaces = []
    for i in range(fine + 1):
        t = i / fine
        px = (1 - t) * pa.x + t * pb.x
        py = (1 - t) * pa.y + t * pb.y
        if (currentFace is not False and
                Graph.pointInsideFace(Graph.Vector(px, py), currentFace)):
            continue
        for face in faces:
            if (face != currentFace and
                    Graph.pointInsideFace(Graph.Vector(px, py), face)):
                currentFace = face
                crossedFaces += [face]
    return crossedFaces


def _ray_other_end(p, direction, bounds):
    """The point where a ray from p in the given direction meets the frame."""
    maxX, maxY = bounds
    if direction == 0:
        return Graph.Vector(maxX, p.y)
    if direction == 1:
        return Graph.Vector(p.x, maxY)
    if direction == 2:
        return Graph.Vector(0, p.y)
    if direction == 3:
        return Graph.Vector(p.x, 0)


def _ray_edges_cross(pa, pb, angleAtA, f):
    """
    True if the ray crosses any edge of region f. Matches the reference engine:
    an edge crosses when its two endpoints fall on opposite angular sides of the
    ray direction (the extremeLeft/extremeRight gating in the caller handles the
    rest). Kept faithful to the original so answers match the ground truth.
    """
    for e in f.edges:
        if angleAtA[e.tail.num] * angleAtA[e.head.num] < 0:
            return True
    return False


def _ray_crosses_faces(pa, direction, map):
    """
    Returns (ordered_faces, quality): the regions a ray from pa in the given
    direction (0=right, 1=up, 2=left, 3=down) passes through, in order.
    """
    pb = _ray_other_end(pa, direction, map.bounds)
    dir_for_match = -1 if direction == 3 else direction
    dir_radians = dir_for_match * np.pi / 2
    # Size by max vertex num (vertices are never renumbered; nums can be sparse).
    n = max(v.num for v in map.vertices) + 1
    angleAtA = [100] * n
    coins = []
    for v in map.vertices:
        i = v.num
        if Graph.vecDist(v.p, pa) < epsilon:
            coins += [v]
        else:
            angleAtA[i] = Graph.PointDirection(pa, v.p) - dir_radians
            if angleAtA[i] < -np.pi:
                angleAtA[i] += 2 * np.pi
            if angleAtA[i] > np.pi:
                angleAtA[i] -= 2 * np.pi
    crossedFaces = []
    quality = 100
    for f in map.faces[1:]:
        extremeLeft = -100
        extremeRight = 100
        nv = len(f.vertices) - 1
        for i in range(nv):
            v1 = f.vertices[i]
            j = v1.num
            if (v1 in coins or abs(angleAtA[j]) < angleeps):
                continue
            dval = np.sin(angleAtA[j])
            extremeLeft = max(extremeLeft, dval)
            extremeRight = min(extremeRight, dval)
            v2 = f.vertices[i + 1]
            if v2 not in coins:
                dLeft, dRight = _one_point_def_side(angleAtA[j], angleAtA[v2.num])
                if dLeft:
                    extremeLeft = 1
                if dRight:
                    extremeRight = -1
        if -smallAng < extremeLeft < smallAng or -smallAng < extremeRight < smallAng:
            return [], -1
        if _ray_edges_cross(pa, pb, angleAtA, f):
            crossedFaces += [f]
        quality = min(quality, abs(extremeLeft), abs(extremeRight))
    crossedFaces = _faces_crossed_in_order(pa, pb, crossedFaces)
    return crossedFaces, quality


def _consec_common_edges(f1, f2):
    """
    Finds the run of consecutive edges that f1 and f2 share.
    Returns (found, start_edge, stop_edge). found is False if the regions do
    not share a single connected run of edges.
    """
    n = len(f1.edges)
    stop = -1
    start = -1
    if f1.edges[0].reverse in f2.edges:
        for i in range(1, n):
            if f1.edges[i].reverse in f2.edges:
                if start != -1:
                    return False, False, False
                if stop != -1:
                    start = i
            else:
                if stop == -1:
                    stop = i - 1
        if start == -1:
            start = 0
    else:
        for i in range(1, n):
            if f1.edges[i].reverse in f2.edges:
                if stop != -1:
                    return False, False, False
                if start == -1:
                    start = i
            else:
                if start != -1 and stop == -1:
                    stop = i - 1
        if stop == -1:
            stop = n - 1
    if start != -1 and stop != -1:
        return True, f1.edges[start], f1.edges[stop]
    return False, False, False


def _vertices_between(va, vb, f):
    """Returns (vertices, edges) of f going from va around to vb."""
    n = len(f.edges)
    b = f.vertices.index(va)
    t = f.vertices.index(vb)
    if b < t:
        return f.vertices[b:t], f.edges[b:t]
    return f.vertices[b:n] + f.vertices[0:t], f.edges[b:n] + f.edges[0:t]


def _face_union(f1, f2):
    """
    Combines two adjacent regions into a single _PseudoFace.
    Returns False if they do not share a connected run of edges.
    """
    found, start, stop = _consec_common_edges(f1, f2)
    if not found:
        return False
    va, vb = start.tail, stop.head
    vv1, ee1 = _vertices_between(vb, va, f1)
    vv2, ee2 = _vertices_between(va, vb, f2)
    pf = _PseudoFace(vv1 + vv2 + [vv1[0]], ee1 + ee2)
    pf.area = f1.area + f2.area
    return pf


def _line_endpoints(line):
    """
    Converts a line object (from segment/ray/extend) into two Graph.Vector
    endpoints suitable for crossing/ordering computations.
    """
    if line['type'] == 'segment':
        return line['a'], line['b']
    if line['type'] == 'ray':
        if _MAP is None:
            raise RuntimeError("Call use_map(map) before using a ray.")
        return line['a'], _ray_other_end(line['a'], line['direction'], _MAP.bounds)
    if line['type'] == 'extend':
        if _MAP is None:
            raise RuntimeError("Call use_map(map) before using an extended line.")
        pa, pb = line['a'], line['b']
        dx, dy = pb.x - pa.x, pb.y - pa.y
        length = (dx * dx + dy * dy) ** 0.5
        if length < epsilon:
            return pa, pb
        ux, uy = dx / length, dy / length
        maxX, maxY = _MAP.bounds
        far = (maxX + maxY) * 2  # comfortably beyond the frame in both directions
        back = Graph.Vector(pa.x - ux * far, pa.y - uy * far)
        fwd = Graph.Vector(pb.x + ux * far, pb.y + uy * far)
        return back, fwd
    raise ValueError("Unknown line type. Use segment(), ray(), or extend().")


# ==============================================================================
# VERTEX GETTERS
# Return a single point (vertex) on the diagram.
# ==============================================================================

def vertex_overlap(*regions, on_frame=False):
    """
    Returns the point where exactly the given regions meet at a single shared vertex.

    Use this to identify a corner or junction common to several regions. Pass
    on_frame=True if the point also touches the outer frame of the diagram.

    Example:
        p = vertex_overlap(E, C, on_frame=True)
        # the point where regions E and C meet at the frame boundary
    """
    region_set = set(regions)
    for v in regions[0].vertices:
        faces_at_v = set(v.faces)
        bounded_faces = {f for f in faces_at_v if f.bounded}
        has_outside = any(not f.bounded for f in faces_at_v)
        if bounded_faces == region_set and has_outside == on_frame:
            return v
    return None


def leftmost(region):
    """
    Returns the vertex of the region furthest to the left (smallest x).

    Example:
        leftmost(A)
    """
    return min(region.trueVertices[1:], key=lambda v: v.p.x)


def rightmost(region):
    """
    Returns the vertex of the region furthest to the right (largest x).

    Example:
        rightmost(J)
    """
    return max(region.trueVertices[1:], key=lambda v: v.p.x)


def topmost(region):
    """
    Returns the vertex of the region that is highest up (largest y).

    Example:
        topmost(B)
    """
    return max(region.trueVertices[1:], key=lambda v: v.p.y)


def bottommost(region):
    """
    Returns the vertex of the region that is lowest down (smallest y).

    Example:
        bottommost(C)
    """
    return min(region.trueVertices[1:], key=lambda v: v.p.y)


def sharpest_corner(region):
    """
    Returns the vertex of the region with the smallest interior angle
    (the most pointed corner).

    Example:
        sharpest_corner(A)
    """
    return min(region.trueVertices[1:], key=lambda v: Graph.angleAtFace(v, region))


def widest_corner(region):
    """
    Returns the vertex of the region with the largest interior angle
    (the most open / flattest corner).

    Example:
        widest_corner(A)
    """
    return max(region.trueVertices[1:], key=lambda v: Graph.angleAtFace(v, region))


def frame_corner(position):
    """
    Returns the vertex at one of the four corners of the outer diagram frame.

    position must be one of: 'bottom_left', 'bottom_right', 'top_right', 'top_left'.
    Requires use_map(map) to have been called first.

    Example:
        frame_corner('bottom_left')
    """
    positions = ['bottom_left', 'bottom_right', 'top_right', 'top_left']
    if position not in positions:
        raise ValueError(f"position must be one of {positions}")
    if _MAP is None:
        raise RuntimeError("Call use_map(map) before using frame_corner().")
    return _MAP.vertices[positions.index(position)]


def vertices(region):
    """
    Returns all corner vertices of the region as a list.

    Use this when you want to sort or iterate over a region's corners.

    Example:
        sort(vertices(A), key=lambda v: angle_at(v, A))
    """
    return region.trueVertices[1:]


# ==============================================================================
# NUMERIC GETTERS
# Return a number. Designed to be passed as the key in sort(), or compared.
# ==============================================================================

def dist(point_a, point_b):
    """
    Returns the straight-line distance between two points.

    Example:
        sort([u, v, w], key=lambda pt: dist(pt, p))
    """
    return Graph.pointDist(point_a.p, point_b.p)


def region_dist(region_a, region_b):
    """
    Returns the shortest distance between two regions (the distance between
    their closest pair of points, which may lie on their boundaries).

    Example:
        region_dist(A, B)
    """
    return Graph.distBetweenFaces(region_a, region_b)


def angle_at(vertex, region):
    """
    Returns the interior angle (radians) of the region at the given vertex.

    Example:
        sort(vertices(A), key=lambda v: angle_at(v, A))
    """
    return Graph.angleAtFace(vertex, region)


def area(region):
    """
    Returns the area of the region.

    Example:
        sort([A, B, C], key=area)
    """
    return region.area


def side_count(region):
    """
    Returns the number of sides of the region.

    Example:
        side_count(merge(A, B))
    """
    return region.numSides


def x_of(point):
    """
    Returns the x-coordinate (left-right position) of the point.
    Larger means further right.

    Example:
        sort([u, v, w], key=x_of)   # left to right
    """
    return point.p.x


def y_of(point):
    """
    Returns the y-coordinate (up-down position) of the point.
    Larger means further up.

    Example:
        sort([u, v, w], key=y_of)   # bottom to top
    """
    return point.p.y


# ==============================================================================
# LINE / PATH CONSTRUCTORS
# Return a line object you can pass into the region-query functions.
# ==============================================================================

def segment(point_a, point_b):
    """
    Creates a finite line segment from point_a to point_b.

    Example:
        regions_in_order(segment(p, q))
    """
    return {'type': 'segment', 'a': point_a.p, 'b': point_b.p}


def ray(point, direction):
    """
    Creates a ray starting at point and going in one direction until it hits
    the frame. direction must be one of: 'left', 'right', 'up', 'down'.
    Requires use_map(map) to have been called first.

    Example:
        regions_in_order(ray(p, 'right'))
    """
    direction_map = {'right': 0, 'up': 1, 'left': 2, 'down': 3}
    if direction not in direction_map:
        raise ValueError(f"direction must be one of {list(direction_map.keys())}")
    return {'type': 'ray', 'a': point.p, 'direction': direction_map[direction]}


def extend(point_a, point_b):
    """
    Creates the full infinite line through point_a and point_b, extended in
    both directions until it meets the frame.

    Example:
        regions_crossed(extend(p, q))
    """
    return {'type': 'extend', 'a': point_a.p, 'b': point_b.p}


# ==============================================================================
# REGION SET QUERIES
# Return a set or ordered list of regions.
# ==============================================================================

def edge_neighbors(region):
    """
    Returns the set of regions that share at least one edge with the region.
    Regions that only touch at a single vertex are not included.

    Example:
        edge_neighbors(A)
    """
    neighbors = set()
    for e in region.edges:
        neighbor = e.reverse.leftFace
        if neighbor.bounded:
            neighbors.add(neighbor)
    return neighbors


def vertex_only_neighbors(region):
    """
    Returns the set of regions that touch the region at a vertex but share no
    edge with it.

    Example:
        vertex_only_neighbors(A)
    """
    edge_nbrs = edge_neighbors(region)
    result = set()
    for v in region.vertices[1:]:
        for f in v.faces:
            if f.bounded and f != region and f not in edge_nbrs:
                result.add(f)
    return result


def regions_at(point):
    """
    Returns the list of regions that meet at the given point.

    Example:
        regions_at(p)
    """
    return [f for f in point.faces if f.bounded]


def regions_crossed(line):
    """
    Returns an unordered set of regions whose interior the line passes through.
    The line must come from segment(), ray(), or extend(). A region counts only
    if the line goes through its interior, not merely along its boundary.
    Requires use_map(map) to have been called first.

    Example:
        regions_crossed(extend(p, q))
    """
    if _MAP is None:
        raise RuntimeError("Call use_map(map) before using regions_crossed().")
    if line['type'] == 'ray':
        faces, _ = _ray_crosses_faces(line['a'], line['direction'], _MAP)
        return set(faces)
    pa, pb = line['a'], line['b']
    infinite = (line['type'] == 'extend')
    faces, _ = _line_crosses_faces(pa, pb, infinite, _MAP)
    return set(faces)


def regions_in_order(line):
    """
    Returns an ordered list of regions in the order you enter them while
    travelling along the line. A region entered more than once appears more
    than once. The line must come from segment(), ray(), or extend().
    Requires use_map(map) to have been called first.

    Example:
        regions_in_order(segment(p, q))
        regions_in_order(ray(p, 'up'))
    """
    if _MAP is None:
        raise RuntimeError("Call use_map(map) before using regions_in_order().")
    if line['type'] == 'ray':
        faces, _ = _ray_crosses_faces(line['a'], line['direction'], _MAP)
        return faces  # already ordered
    if line['type'] == 'segment':
        pa, pb = line['a'], line['b']
        faces, _ = _line_crosses_faces(pa, pb, False, _MAP)
        return _faces_crossed_in_order(pa, pb, faces)
    if line['type'] == 'extend':
        faces, _ = _line_crosses_faces(line['a'], line['b'], True, _MAP)
        order_a, order_b = _line_endpoints(line)
        return _faces_crossed_in_order(order_a, order_b, faces)
    raise ValueError("Unknown line type. Use segment(), ray(), or extend().")


# ==============================================================================
# REGION OPERATIONS
# ==============================================================================

def merge(region_a, region_b):
    """
    Returns a new region formed by joining region_a and region_b. The two
    regions must share at least one edge. The result has its own side_count,
    area, and convexity.

    Example:
        side_count(merge(A, B))
        is_convex(merge(A, B))
    """
    result = _face_union(region_a, region_b)
    if result is False:
        raise ValueError(
            f"Regions {region_a.letter} and {region_b.letter} cannot be merged; "
            "they must share a connected run of edges.")
    return result


def is_convex(region):
    """
    Returns True if the region is convex (no inward dents), False otherwise.

    Example:
        is_convex(A)
    """
    return region.convex


# ==============================================================================
# SORTING & COMPARISON
# ==============================================================================

def sort(items, key):
    """
    Returns the items sorted in increasing order by the key function.
    key takes one item and returns a number; build it inline with lambda.

    Example:
        sort([u, v, w], key=lambda pt: dist(pt, p))
        sort([A, B, C], key=area)
    """
    return sorted(items, key=key)


def min_of(*values):
    """
    Returns the smallest of the given values.

    Example:
        min_of(region_dist(A, B), region_dist(A, C))
    """
    return min(values)


def crosses(line_a, line_b):
    """
    Returns True if line_a and line_b cross each other, False otherwise.
    Both arguments must come from segment(), ray(), or extend().

    Example:
        crosses(segment(p, q), segment(u, v))
    """
    pa, pb = _line_endpoints(line_a)
    pc, pd = _line_endpoints(line_b)
    result, quality = _cross_lines(pa, pb, pc, pd)
    if quality == 0:
        raise ValueError(
            "The lines are too close to parallel or near-touching to judge clearly.")
    return result
