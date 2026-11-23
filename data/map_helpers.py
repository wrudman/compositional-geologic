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

Most operations depend only on the shared geometry modules Graph and
FinalizeFaces. Infinite-line intersection uses the benchmark's canonical
``Questions.TraceSegment`` routine so Q12 tool results and dataset answers
cannot silently diverge.
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


class CentroidPoint:
    """A derived point, never inserted into the map's vertex/edge topology.

    Empty adjacency lists retain compatibility with the existing point-selection
    protocol. This point is not a boundary vertex and cannot define an angle.
    """
    def __init__(self, x, y, region):
        self.p = Graph.Vector(float(x), float(y))
        self.source_region = region
        self.point_kind = "centroid"
        self.outarcs = []
        self.faces = []
        self.num = None


def centroid(region):
    """Area centroid of a simple polygon (including a supported merged region).

    The shoelace formula is orientation-independent. Translate to a local origin
    before summation to reduce cancellation; boundary segmentation does not
    affect the result. A concave polygon's centroid may lie outside it.
    """
    import math
    if not getattr(region, "bounded", False):
        raise ValueError("Select a bounded region to find its centroid.")
    points = [v.p for v in region.vertices]
    if len(points) > 1 and points[0].x == points[-1].x and points[0].y == points[-1].y:
        points.pop()
    if len(points) < 3:
        raise ValueError("A centroid requires a nondegenerate polygon.")
    ox, oy = float(points[0].x), float(points[0].y)
    xy = [(float(p.x)-ox, float(p.y)-oy) for p in points]
    if not all(math.isfinite(v) for point in xy for v in point):
        raise ValueError("Polygon coordinates must be finite.")
    pairs = list(zip(xy, xy[1:] + xy[:1]))
    cross = [x*v-u*y for (x,y),(u,v) in pairs]
    area2 = math.fsum(cross)
    scale = max(max(abs(x), abs(y)) for x,y in xy)
    if scale == 0 or abs(area2) <= 1e-14*scale*scale:
        raise ValueError("The region has zero or numerically degenerate area.")
    cx = ox + math.fsum((a[0]+b[0])*c for (a,b),c in zip(pairs,cross))/(3*area2)
    cy = oy + math.fsum((a[1]+b[1])*c for (a,b),c in zip(pairs,cross))/(3*area2)
    return CentroidPoint(cx, cy, region)


def incident_edge_count(vertex, merged_regions=()):
    """Count distinct visible edge segments leaving a diagram vertex.

    Includes frame edges. Reverse half-edges represent the same edge and are
    counted once. Two collinear edges leaving in opposite directions count as
    two (e.g. a T-junction has three incident edges). Workspace unions hide
    internal edges, without mutating the original map topology.
    """
    if getattr(vertex, "point_kind", None) == "centroid" or not hasattr(vertex, "outarcs"):
        raise ValueError("Select a diagram vertex, not a center point, for incident edge count.")
    merged_sources = [set(getattr(region, "source_faces", (region,)))
                      for region in merged_regions]
    seen = set()
    for edge in vertex.outarcs:
        a, b = edge.tail, edge.head
        if a is not vertex and b is not vertex:
            continue
        if a is b:
            continue
        reverse = getattr(edge, "reverse", None)
        left, right = getattr(edge, "leftFace", None), getattr(reverse, "leftFace", None)
        if any(left in sources and right in sources for sources in merged_sources):
            continue
        seen.add(tuple(sorted((id(a), id(b)))))
    return len(seen)


def region_count():
    """Return the number of bounded regions in the current diagram."""
    if _MAP is None:
        raise RuntimeError("Call use_map(map) before region_count().")
    return sum(1 for face in _MAP.faces if face.bounded)


def _cut_polygon_triangles(points):
    """Ear clipping of a simple polygon, used to validate connected cut pieces."""
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    points=list(points)
    while len(points)>3:
        remove=next((i for i in range(len(points)) if abs(cross(points[i-1],points[i],points[(i+1)%len(points)]))<1e-12),None)
        if remove is None:break
        points.pop(remove)
    area2=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1]))
    if area2<0:points.reverse()
    remaining=list(range(len(points)));triangles=[]
    while len(remaining)>3:
        for pos,i in enumerate(remaining):
            j,k=remaining[pos-1],remaining[(pos+1)%len(remaining)]
            if cross(points[j],points[i],points[k])<=1e-12:continue
            if any(all(cross(points[u],points[v],points[q])>=-1e-12 for u,v in [(j,i),(i,k),(k,j)]) for q in remaining if q not in (j,i,k)):continue
            triangles.append((j,i,k));remaining.pop(pos);break
        else:raise ValueError("Could not validate the region boundary.")
    triangles.append(tuple(remaining))
    return points,triangles


def cut_region_areas(region, line, sides="above_below"):
    """Return two side areas, permitting overlap with part of the boundary.

    A valid cut has one connected positive-area piece on each side. Boundary
    contact alone does not cut a region; multi-piece cuts remain unsupported.
    """
    import math
    if line.get('type')!='extend':raise ValueError("Select a full line drawn with extend edge.")
    if not getattr(region,'bounded',False):raise ValueError("Select one region or union.")
    if sides not in ('above_below','left_right'):raise ValueError("Choose Above/Below or Left/Right.")
    a,b=line['a'],line['b']
    if not all(math.isfinite(float(c)) for p in (a,b) for c in (p.x,p.y)):
        raise ValueError("Line coordinates must be finite.")
    if sides=='above_below':
        if abs(b.x-a.x)<=1e-9:raise ValueError("For a vertical line, choose Left/Right.")
        if b.x<a.x:a,b=b,a
        labels=('above','below')
    else:
        if abs(b.y-a.y)<=1e-9:raise ValueError("For a horizontal line, choose Above/Below.")
        if b.y<a.y:a,b=b,a
        labels=('left','right')
    raw=[(float(v.p.x),float(v.p.y)) for v in region.vertices]
    points=[]
    for pt in raw:
        if not points or pt!=points[-1]:points.append(pt)
    if points and points[0]==points[-1]:points.pop()
    if len(points)<3:raise ValueError("Select a nonempty region.")
    points,triangles=_cut_polygon_triangles(points)
    from taxonomy_geometry_20261112 import clip,poly_area
    aa,bb=(float(a.x),float(a.y)),(float(b.x),float(b.y))
    dx,dy=b.x-a.x,b.y-a.y;length=math.hypot(dx,dy)
    signed=[(dx*(y-a.y)-dy*(x-a.x))/length for x,y in points]
    areas=[]
    for positive in (True,False):
        values=[v if positive else -v for v in signed]
        active={i:poly_area(clip([points[v] for v in tri],aa,bb,positive)) for i,tri in enumerate(triangles)}
        active={i:area for i,area in active.items() if area>1e-12}
        if not active:raise ValueError("The line must cut the region into two parts with area.")
        links={i:set() for i in active};owners={}
        for i in active:
            tri=triangles[i]
            for u,v in zip(tri,tri[1:]+tri[:1]):owners.setdefault(tuple(sorted((u,v))),[]).append(i)
        for (u,v),adjacent in owners.items():
            if len(adjacent)!=2:continue
            x,y=values[u],values[v]
            # Nonzero interior portion of the shared diagonal connects pieces.
            if max(x,y)<=1e-10:continue
            fraction=1. if min(x,y)>=0 else max(x,y)/abs(x-y)
            if math.dist(points[u],points[v])*fraction<=1e-10:continue
            i,j=adjacent;links[i].add(j);links[j].add(i)
        todo=set(active);components=0
        while todo:
            components+=1;stack=[todo.pop()]
            while stack:
                for j in links[stack.pop()] & todo:todo.remove(j);stack.append(j)
        if components!=1:raise ValueError("The line cuts the region into more than two parts.")
        areas.append(math.fsum(active.values()))
    total=poly_area(points)
    if not math.isclose(sum(areas),total,rel_tol=1e-7,abs_tol=1e-10):raise ValueError("Could not validate the cut areas.")
    return dict(zip(labels,map(float,areas)))


def crossed_edges(line):
    """Proper interior-edge crossings for a ray only.

    Ignore frame edges, defining/source endpoints, and boundary-only overlap.
    Other vertex hits are ambiguous and should be avoided by generation.
    """
    if _MAP is None:raise RuntimeError("Call use_map(map) first.")
    import math
    kind=line.get('type')
    if kind != 'ray':raise ValueError("Select a ray.")
    if kind not in ('ray','segment','extend'):raise ValueError("Choose a drawn line.")
    a=line['a'];eps=1e-9
    if kind=='ray':dx,dy=[(1,0),(0,1),(-1,0),(0,-1)][line['direction']];length=1.
    else:
        b=line['b'];dx,dy=b.x-a.x,b.y-a.y;length=math.hypot(dx,dy)
        if not length:raise ValueError("A line needs two distinct points.")
        dx,dy=dx/length,dy/length
    lo,hi=(0.,float('inf')) if kind=='ray' else (0.,length) if kind=='segment' else (-float('inf'),float('inf'))
    for origin,direction,bound in [(a.x,dx,_MAP.bounds[0]),(a.y,dy,_MAP.bounds[1])]:
        if abs(direction)<=eps:
            if origin < -eps or origin>bound+eps:return []
        else:
            x,y=sorted((-origin/direction,(bound-origin)/direction));lo=max(lo,x);hi=min(hi,y)
    if hi-lo<=eps:return []
    excluded=list(line.get('source_edge_endpoints',())) or [line['a']]+([line['b']] if kind!='ray' else [])
    def excluded_point(p):return any(math.hypot(p.x-q.x,p.y-q.y)<=eps for q in excluded)
    hits=[];overlaps=[];seen=set()
    for e in _MAP.edges:
        key=tuple(sorted((id(e.tail),id(e.head))))
        if key in seen:continue
        seen.add(key)
        left,right=getattr(e,'leftFace',None),getattr(e.reverse,'leftFace',None)
        if bool(getattr(left,'bounded',False))!=bool(getattr(right,'bounded',False)):continue
        b,c=e.tail.p,e.head.p;ex,ey=c.x-b.x,c.y-b.y
        qx,qy=b.x-a.x,b.y-a.y;den=dx*ey-dy*ex
        if abs(den)<=eps:
            if abs(dx*qy-dy*qx)<=eps:
                overlaps.append(sorted((qx*dx+qy*dy,(c.x-a.x)*dx+(c.y-a.y)*dy)))
            continue
        t=(qx*ey-qy*ex)/den;u=(qx*dy-qy*dx)/den
        if not lo+eps<t<hi-eps or not eps<u<1-eps:continue
        point=Graph.Vector(a.x+t*dx,a.y+t*dy)
        if not excluded_point(point):hits.append((t,e))
    for v in _MAP.vertices:
        p=v.p;t=(p.x-a.x)*dx+(p.y-a.y)*dy
        if (lo+eps<t<hi-eps and abs(dx*(p.y-a.y)-dy*(p.x-a.x))<=eps
            and not excluded_point(p) and not any(start-eps<=t<=end+eps for start,end in overlaps)):
            raise ValueError("The line passes through a vertex. Choose a path that crosses edges clearly.")
    return [e for _,e in sorted(hits,key=lambda pair:pair[0])]


def ray_crossed_edges(line):
    """Compatibility alias; use crossed_edges for every supported line type."""
    return crossed_edges(line)


def line_vertices(line, exclude_source_endpoints=False):
    """Distinct native map vertices exactly on segment/ray/full line (tol 1e-9).

    Exclusion is valid only when draw stored the original edge endpoints.
    It removes those two points, not other collinear vertices along the edge.
    """
    import math
    if _MAP is None:
        raise RuntimeError("Call use_map(map) before querying vertices.")
    if not isinstance(exclude_source_endpoints, bool):
        raise ValueError("exclude_source_endpoints must be True or False.")
    source=line.get("source_edge_endpoints")
    if exclude_source_endpoints and not source:
        raise ValueError("Endpoint exclusion requires a line drawn from a selected edge.")
    if line.get("type") not in ("segment","ray","extend"):
        raise ValueError("Select a drawn line.")
    a=line['a']
    b=line.get('b')
    if line['type']=='ray':
        dx,dy=[(1,0),(0,1),(-1,0),(0,-1)][line['direction']]
    else:
        dx,dy=b.x-a.x,b.y-a.y
    length=math.hypot(dx,dy)
    if not length:raise ValueError("A line needs two distinct points.")
    seen=[];found=[]
    for vertex in _MAP.vertices:
        p=vertex.p
        if abs(dx*(p.y-a.y)-dy*(p.x-a.x))/length>1e-9:continue
        t=((p.x-a.x)*dx+(p.y-a.y)*dy)/(length*length)
        if line['type']=='segment' and not -1e-9<=t<=1+1e-9:continue
        if line['type']=='ray' and t < -1e-9:continue
        if exclude_source_endpoints and any(math.hypot(p.x-q.x,p.y-q.y)<=1e-9 for q in source):continue
        if any(math.hypot(p.x-q.x,p.y-q.y)<=1e-9 for q in seen):continue
        seen.append(p);found.append((t,vertex))
    return [v for _,v in sorted(found,key=lambda item:item[0])]


def edges_parallel(first, second):
    """True for edges on distinct parallel supporting lines; collinear is False.

    Compare normalized directions with a numerical tolerance (1e-9), not a
    perceptual angle threshold. Selection direction does not affect the result.
    """
    import math
    def direction(edge):
        segments = tuple(getattr(edge, "segments", (edge,)))
        if not segments:
            raise ValueError("Select a nonempty straight edge.")
        base = None
        for seg in segments:
            a,b = seg.tail.p,seg.head.p
            if not all(math.isfinite(float(c)) for p in (a,b) for c in (p.x,p.y)):
                raise ValueError("Edge coordinates must be finite.")
            dx,dy = b.x-a.x,b.y-a.y
            length = math.hypot(dx,dy)
            if length == 0:
                raise ValueError("An edge must have nonzero length.")
            u = (dx/length,dy/length)
            if base is None:
                base=(a,u)
            else:
                origin,v = base
                if abs(v[0]*u[1]-v[1]*u[0]) > 1e-9 or abs(v[0]*(a.y-origin.y)-v[1]*(a.x-origin.x)) > 1e-9:
                    raise ValueError("Select a straight edge, not a bent chain.")
        return base
    a,u = direction(first)
    b,v = direction(second)
    aligned = abs(u[0]*v[1]-u[1]*v[0]) <= 1e-9
    separation = abs(u[0]*(b.y-a.y)-u[1]*(b.x-a.x))
    return bool(aligned and separation > 1e-9)


def point_edge_distance(point, edge):
    """Shortest distance to a finite selected edge, clamping to its endpoints.

    EdgeSel may contain multiple underlying segments of one visible edge.
    Return the minimum over those segments, never the supporting infinite line.
    """
    import math
    p = getattr(point, "p", point)
    segments = getattr(edge, "segments", (edge,))
    if not segments:
        raise ValueError("Select a nonempty edge.")
    distances = []
    for segment in segments:
        a, b = segment.tail.p, segment.head.p
        if not all(math.isfinite(float(c)) for q in (p,a,b) for c in (q.x,q.y)):
            raise ValueError("Point and edge coordinates must be finite.")
        dx, dy = b.x-a.x, b.y-a.y
        squared = dx*dx+dy*dy
        t = max(0., min(1., ((p.x-a.x)*dx+(p.y-a.y)*dy)/squared)) if squared else 0.
        distances.append(math.hypot(p.x-(a.x+t*dx), p.y-(a.y+t*dy)))
    return min(distances)


def orientation(*vertices):
    """Direction of a simple closed cycle through 3+ points in supplied order.

    The last point connects back to the first; do not repeat the first point.
    Concave cycles are allowed. Repeated points, self-intersections and zero
    area are rejected because they do not define one unambiguous cycle.
    """
    import math
    if len(vertices) < 3:
        raise ValueError("Cycle orientation requires at least three points.")
    points = [getattr(v, "p", v) for v in vertices]
    if not all(hasattr(p, "x") and hasattr(p, "y") for p in points):
        raise ValueError("Cycle orientation requires points.")
    if not all(math.isfinite(float(c)) for p in points for c in (p.x, p.y)):
        raise ValueError("Cycle coordinates must be finite.")
    origin = points[0]
    xy = [(float(p.x-origin.x), float(p.y-origin.y)) for p in points]
    if len(set(xy)) != len(xy):
        raise ValueError("Use distinct points; do not repeat the first point at the end.")
    scale = max(abs(c) for p in xy for c in p)
    tol = max(1e-15, 1e-12 * scale * scale)
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
    def on(a, b, c):
        return (abs(cross(a,b,c)) <= tol and
                min(a[0],b[0]) <= c[0] <= max(a[0],b[0]) and
                min(a[1],b[1]) <= c[1] <= max(a[1],b[1]))
    n = len(xy)
    for i in range(n):
        a,b,c = xy[i-1],xy[i],xy[(i+1)%n]
        if abs(cross(a,b,c)) <= tol and (on(a,b,c) or on(b,c,a)):
            raise ValueError("Cycle edges overlap or reverse direction.")
    for i in range(n):
        a,b = xy[i],xy[(i+1)%n]
        for j in range(i+1,n):
            if j == i+1 or (i == 0 and j == n-1):
                continue
            c,d = xy[j],xy[(j+1)%n]
            ab_c,ab_d,cd_a,cd_b = cross(a,b,c),cross(a,b,d),cross(c,d,a),cross(c,d,b)
            proper = ((ab_c > tol and ab_d < -tol or ab_c < -tol and ab_d > tol) and
                      (cd_a > tol and cd_b < -tol or cd_a < -tol and cd_b > tol))
            if proper or on(a,b,c) or on(a,b,d) or on(c,d,a) or on(c,d,b):
                raise ValueError("Cycle must not self-intersect or touch itself.")
    area2 = math.fsum(a[0]*b[1]-b[0]*a[1] for a,b in zip(xy,xy[1:]+xy[:1]))
    if abs(area2) <= tol:
        raise ValueError("Cycle has zero area; orientation is undefined.")
    return "Counterclockwise" if area2 > 0 else "Clockwise"


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


def _walk_samples(pa, pb, map, steps):
    ordered = []
    current = None
    for i in range(steps + 1):
        t = i / steps
        p = Graph.Vector((1 - t) * pa.x + t * pb.x,
                         (1 - t) * pa.y + t * pb.y)
        f = next((face for face in map.faces
                  if face.bounded and Graph.pointInsideFace(p, face)), None)
        if f is not None and f is not current:
            ordered.append(f)
            current = f
    return ordered


def _sample_faces_in_order(pa, pb, map):
    """
    Robust ordered region walk from pa to pb. Samples points densely along the
    segment and records each bounded region as it is entered. A region entered,
    left, and re-entered appears more than once. Unlike the angle-classification
    path, this never bails out on near-tangent or near-parallel geometry, so it
    is used for finite segments and rays where that gating was returning nothing.
    """
    d = Graph.vecDist(pa, pb)
    if d < epsilon:
        return []
    steps = max(120, int(800 * d))
    ordered = _walk_samples(pa, pb, map, steps)
    if ordered:
        return ordered
    # Fallback: the line may run almost exactly along shared boundaries, so every
    # sample landed on an edge. Nudge a hair to one side and retry before giving up.
    nx, ny = -(pb.y - pa.y) / d, (pb.x - pa.x) / d   # unit normal
    for off in (0.5 * smallDist, -0.5 * smallDist):
        qa = Graph.Vector(pa.x + nx * off, pa.y + ny * off)
        qb = Graph.Vector(pb.x + nx * off, pb.y + ny * off)
        ordered = _walk_samples(qa, qb, map, steps)
        if ordered:
            return ordered
    return ordered


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

def vertex_overlap(*regions, on_frame=None):
    """Return the unique shared boundary vertex of all supplied regions.

    Other regions may meet at the same point; they need not be supplied.
    Omit on_frame to search both frame and interior points; True/False filters
    whether the point also meets Outside. No match returns
    None; multiple matches raise an explicit ambiguity error.
    Boundary topology vertices are used, not only geometric corners.
    """
    if len(regions) < 2:
        raise ValueError("Meeting-vertex selection requires at least two regions.")
    common = set(regions[0].vertices)
    for region in regions[1:]:
        common.intersection_update(region.vertices)
    candidates = []
    seen = set()
    for v in regions[0].vertices:
        if v not in common or id(v) in seen:
            continue
        seen.add(id(v))
        has_outside = any(not f.bounded for f in v.faces)
        if on_frame is None or has_outside == on_frame:
            candidates.append(v)
    if not candidates:
        return None
    if len(candidates) > 1:
        labels = ", ".join(str(getattr(r, "letter", "?")) for r in regions)
        raise ValueError(
            f"Ambiguous vertex selection: Regions {labels} share "
            f"{len(candidates)} matching boundary points. "
            "Specify additional regions or a more precise selection.")
    return candidates[0]


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


def diagonal_corner(region, position):
    """Return the corner selected by the generator's diagonal description."""
    candidates = []
    corners = region.trueVertices[1:]
    for vertex in corners:
        alternatives = [other for other in corners if other is not vertex]
        bottom_left = bottom_right = top_left = top_right = True
        for other in alternatives:
            if other.p.x - vertex.p.x < -epsilon:
                bottom_left = top_left = False
            elif vertex.p.x - other.p.x < -epsilon:
                bottom_right = top_right = False
            if other.p.y - vertex.p.y < -epsilon:
                bottom_left = bottom_right = False
            elif vertex.p.y - other.p.y < -epsilon:
                top_left = top_right = False
            if (other.p.x - vertex.p.x < smallDist and
                    other.p.y - vertex.p.y < smallDist):
                bottom_left = False
            if (vertex.p.x - other.p.x < smallDist and
                    other.p.y - vertex.p.y < smallDist):
                bottom_right = False
            if (other.p.x - vertex.p.x < smallDist and
                    vertex.p.y - other.p.y < smallDist):
                top_left = False
            if (vertex.p.x - other.p.x < smallDist and
                    vertex.p.y - other.p.y < smallDist):
                top_right = False
        matches = {
            "bottom_left": bottom_left,
            "bottom_right": bottom_right,
            "top_left": top_left,
            "top_right": top_right,
        }
        if matches.get(position, False):
            candidates.append(vertex)
    if len(candidates) != 1:
        raise ValueError(
            f'Region does not have a unique "{position}" described vertex.'
        )
    return candidates[0]


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


def described_edges(region):
    """Return uniquely describable boundary edges and what each one meets.

    One geometric edge may contain several collinear half-edge segments after
    topology splitting.  The returned ``segments`` keep those pieces together.
    """
    groups = []
    true_vertices = region.trueVertices[:-1]
    for index, start in enumerate(true_vertices):
        stop = true_vertices[(index + 1) % len(true_vertices)]
        start_index = region.vertices.index(start)
        stop_index = region.vertices.index(stop)
        if start_index < stop_index:
            segments = region.edges[start_index:stop_index]
        else:
            segments = (
                region.edges[start_index:]
                + region.edges[:stop_index]
            )
        meets = []
        has_outside = False
        for segment in segments:
            opposite = segment.reverse.leftFace
            if opposite.bounded:
                if opposite not in meets:
                    meets.append(opposite)
            else:
                has_outside = True
        key = (
            tuple(sorted(id(face) for face in meets)),
            has_outside,
        )
        groups.append({
            "segments": tuple(segments),
            "meets": tuple(sorted(meets, key=lambda face: face.letter)),
            "meets_outside": has_outside,
            "description_key": key,
        })

    # A referring expression must identify exactly one geometric edge.
    key_counts = {}
    for group in groups:
        key = group["description_key"]
        key_counts[key] = key_counts.get(key, 0) + 1
    return [
        group for group in groups
        if key_counts[group["description_key"]] == 1
    ]


def edge_by_meeting(region, *meeting_objects):
    """Find the unique edge of ``region`` meeting the given regions/Outside."""
    requested_faces = {
        item for item in meeting_objects
        if item != "Outside"
    }
    requested_outside = "Outside" in meeting_objects
    matches = [
        group
        for group in described_edges(region)
        if set(group["meets"]) == requested_faces
        and group["meets_outside"] == requested_outside
    ]
    if len(matches) != 1:
        raise ValueError("The description does not identify a unique edge.")
    return matches[0]["segments"]


def edge_among(*regions):
    """Return the unique geometric edge identified by an unordered region set."""
    if len(regions) < 2:
        raise ValueError("Finding an edge requires two or more regions.")

    candidates = []
    seen_geometry = set()
    for owner in regions:
        others = [region for region in regions if region is not owner]
        try:
            segments = edge_by_meeting(owner, *others)
        except ValueError:
            continue
        geometry_key = frozenset(
            frozenset((id(segment), id(segment.reverse)))
            for segment in segments
        )
        if geometry_key not in seen_geometry:
            seen_geometry.add(geometry_key)
            candidates.append(segments)

    if len(candidates) != 1:
        raise ValueError(
            "The selected regions do not identify one unique edge."
        )
    return candidates[0]


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
    if getattr(vertex, "point_kind", None) == "centroid":
        raise ValueError("A centroid is a point, not a boundary vertex with an interior angle.")
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


def frame_edge_count(region):
    """Return the number of the region's boundary edges lying on the frame."""
    return sum(
        1
        for edge in region.edges
        if not edge.reverse.leftFace.bounded
    )


def x_of(point):
    """
    Returns the x-coordinate (left-right position) of the point.
    Larger means further right.

    Example:
        sort([u, v, w], key=x_of)   # left to right
    """
    if hasattr(point, "p"):
        return point.p.x
    return (point.box[0] + point.box[1]) / 2


def y_of(point):
    """
    Returns the y-coordinate (up-down position) of the point.
    Larger means further up.

    Example:
        sort([u, v, w], key=y_of)   # bottom to top
    """
    if hasattr(point, "p"):
        return point.p.y
    return (point.box[2] + point.box[3]) / 2


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
    Returns regions with point-only contact and no shared edge.

    This contact relation does not require a corner on both regions. Keep all
    boundary incidence points here; vertices(region) separately lists corners.

    Example:
        vertex_only_neighbors(A)
    """
    edge_nbrs = edge_neighbors(region)
    source_faces = set(getattr(region, "source_faces", (region,)))
    result = set()
    for v in region.vertices[1:]:
        for f in v.faces:
            if f.bounded and f not in source_faces and f not in edge_nbrs:
                result.add(f)
    return result


def regions_at(point):
    """
    Returns the list of regions that meet at the given point.

    Example:
        regions_at(p)
    """
    if getattr(point, "point_kind", None) == "centroid":
        raise ValueError("A centroid is not a contact vertex; select a region for neighbor queries.")
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
    if infinite:
        # Keep the public tool exactly aligned with the Q12 answer generator,
        # including its treatment of lines coinciding with region boundaries.
        import Questions as _questions
        frame_a, frame_b = _questions.GetFrameIntersections(
            pa, pb, _MAP.bounds
        )
        return set(
            _questions.TraceSegment(
                frame_a, frame_b, _MAP, min_dist=0.0005
            )
        )
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
        pa = line['a']
        pb = _ray_other_end(pa, line['direction'], _MAP.bounds)
        return _sample_faces_in_order(pa, pb, _MAP)
    if line['type'] == 'segment':
        return _sample_faces_in_order(line['a'], line['b'], _MAP)
    if line['type'] == 'extend':
        order_a, order_b = _line_endpoints(line)
        return _sample_faces_in_order(order_a, order_b, _MAP)
    raise ValueError("Unknown line type. Use segment(), ray(), or extend().")


# ==============================================================================
# REGION OPERATIONS
# ==============================================================================

def merge(*regions):
    """
    Merge two or more regions (or one list of regions) in a single call.
    Their edge-adjacency graph must be connected; pairwise adjacency is not
    required. Input order is irrelevant. As with the existing polygon tools,
    the resulting boundary must be a simple cycle without holes or pinches.
    """
    if len(regions) == 1 and isinstance(regions[0], (list, tuple)):
        regions = tuple(regions[0])
    if len(regions) < 2:
        raise ValueError("Select at least two regions to merge.")
    if any(not getattr(r, "bounded", False) or not hasattr(r, "edges") for r in regions):
        raise ValueError("Merge accepts bounded regions only.")
    if len({id(r) for r in regions}) != len(regions):
        raise ValueError("Select distinct regions to merge.")
    # Flatten existing unions for the Python API, while the survey continues
    # to select original regions. Do not modify the map's half-edge topology.
    sources = []
    for region in regions:
        sources.extend(getattr(region, "source_faces", (region,)))
    if len(set(sources)) != len(sources):
        raise ValueError("The selected regions overlap.")
    selected = set(sources)
    visited, pending = set(), [sources[0]]
    while pending:
        face = pending.pop()
        if face in visited:
            continue
        visited.add(face)
        pending.extend(e.reverse.leftFace for e in face.edges
                       if e.reverse.leftFace in selected and e.reverse.leftFace not in visited)
    if visited != selected:
        raise ValueError("Selected regions must form one connected group through shared edges; vertex-only contact does not count.")
    boundary = [e for f in sources for e in f.edges if e.reverse.leftFace not in selected]
    outgoing = {e.tail: e for e in boundary}
    if not boundary or len(outgoing) != len(boundary):
        raise ValueError("The union has a pinched boundary; select regions forming a simple boundary.")
    ordered, seen = [], set()
    edge = boundary[0]
    while edge not in seen:
        seen.add(edge)
        ordered.append(edge)
        edge = outgoing.get(edge.head)
        if edge is None:
            raise ValueError("The union boundary is not closed.")
    if edge is not ordered[0] or len(ordered) != len(boundary):
        raise ValueError("Unions with holes are not supported by the polygon tools.")
    result = _PseudoFace([e.tail for e in ordered] + [ordered[0].tail], ordered)
    result.area = sum(f.area for f in sources)
    result.source_faces = tuple(sources)
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

def regions_along_edge(edge):
    """
    Returns the bounded regions bordering a single edge.
 
    Used by neighbors() when the selection is an edge rather than a region:
    it answers "which labeled regions inside the frame sit on either side of
    this edge?". Frame edges therefore return only their bounded side.
 
    Example:
        regions_along_edge(some_edge)   # -> [region_on_one_side, region_on_other]
    """
    out = []
    for f in (edge.leftFace, edge.reverse.leftFace):
        if f is not None and getattr(f, "bounded", False) and f not in out:
            out.append(f)
    return out


def extend_piece(a, b, direction):
    """Only the added segment beyond the chosen endpoint, up to the frame."""
    import math
    if _MAP is None:raise RuntimeError("Call use_map first.")
    if direction not in ('left','right','up','down'):raise ValueError("Choose an extension direction.")
    axis='x' if direction in ('left','right') else 'y'
    delta=getattr(b.p,axis)-getattr(a.p,axis)
    if abs(delta)<1e-9:raise ValueError("Choose a direction along the edge.")
    positive=direction in ('right','up')
    start,other=(b,a) if (delta>0)==positive else (a,b)
    dx,dy=start.p.x-other.p.x,start.p.y-other.p.y
    candidates=[]
    for origin,d,limit in ((start.p.x,dx,_MAP.bounds[0]),(start.p.y,dy,_MAP.bounds[1])):
        if abs(d)>1e-12:candidates.append(((limit if d>0 else 0)-origin)/d)
    distance=min(candidates)
    if distance<=1e-9:raise ValueError("This endpoint is already on the frame.")
    end=Graph.Vector(start.p.x+distance*dx,start.p.y+distance*dy)
    return {'type':'segment','a':other.p,'b':end,'extension_direction':direction,
            'extension_part':(start.p,end),
            'source_edge_endpoints':(a.p,b.p)}


def edge_extension_lengths(line):
    """Original edge plus added portions; preserve unrounded geometry values."""
    import math
    points=line.get('source_edge_endpoints')
    if not points:raise ValueError("Choose an edge extension.")
    a,b=points
    result={'original_edge':math.hypot(b.x-a.x,b.y-a.y)}
    if line.get('extension_part'):
        start,end=line['extension_part']
        result[line['extension_direction']]=math.hypot(end.x-start.x,end.y-start.y)
    elif line.get('type')=='extend':
        from extension_directions import preferred_extension_axis
        axis=preferred_extension_axis(a,b,line.get('question_extension_direction'))
        lo,hi=sorted((a,b),key=lambda p:getattr(p,axis))
        labels=('left','right') if axis=='x' else ('down','up')
        from types import SimpleNamespace
        for label,point in zip(labels,(lo,hi)):
            coordinate=getattr(point,axis)
            limit=_MAP.bounds[0 if axis=='x' else 1]
            if abs(coordinate)<1e-9 or abs(coordinate-limit)<1e-9:
                result[label]=0.0
            else:
                piece=extend_piece(SimpleNamespace(p=a),SimpleNamespace(p=b),label)
                start,end=piece['extension_part']
                result[label]=math.hypot(end.x-start.x,end.y-start.y)
    else:raise ValueError("Choose an edge extension.")
    return result
