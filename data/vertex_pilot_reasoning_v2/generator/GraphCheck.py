import numpy
import Graph
import Frame

epsilon = 0.00001


def GraphCheck(vertices,edges,faces):
    return (VerticesCheck(vertices, edges, faces) and
            EdgesCheck(vertices, edges, faces) and
            FacesCheck(vertices, edges, faces))

def VerticesCheck(vertices, edges, faces):
    global epsilon
    for v in vertices:
#       print("Checking", str(v))
        if not(VertexCheck(v,edges,faces)):
#           print("Failed VertexCheck", str(v))
            return False;
    for i in range(len(vertices)-1):
        for j in range(i+1,len(vertices)):
            if Graph.pointDist(vertices[i].p,vertices[j].p) < epsilon:
                return False
    return True

def VertexCheck(v,edges,faces):
    ee = v.outarcs
    ff = v.faces
    if (len(ee) != len(ff)):
        return False
#   print("LengthChecl")
    for e in ee:
#       print("Checking-Vertex-EdgeCheck",str(e))
        if e.tail != v:
            return False
        if e not in edges:
            return False
#       print("Vertex-EdgeCheck",str(e))
    for f in ff:
#       print(str(f))
        if v not in f.vertices:
            return False
        if f not in faces:
            return False
#       print("Vertex-FaceCheck",str(f))
    ea = ee[0]
    for eb in ee[1:len(ee)]:
#       print("Checking",str(ea),str(eb))
        if eb.direction < ea.direction:
            return False
        ea=eb
    ees=ee[1:len(ee)]+[ee[0]]
    for f,e,es in zip(ff,ee,ees):
#      print("Checking",str(f),str(e),str(es))
       if f != e.leftFace or f != es.reverse.leftFace:
            return False
    return True

def EdgesCheck(vertices,edges,faces):
    for e in edges:
        if not(EdgeCheck(e,vertices,edges,faces)):
            return  False;
    # Check each geometric (undirected) segment exactly once.  The old check
    # assumed reverse half-edges were adjacent in `edges` and skipped nearby
    # list indices.  After splitting, that ordering is not guaranteed, so a
    # real crossing could be missed and a face could become self-intersecting.
    geometric_edges = []
    seen = set()
    for e in edges:
        key = frozenset((e.tail.num, e.head.num))
        if key not in seen:
            seen.add(key)
            geometric_edges.append(e)
    for i in range(len(geometric_edges)-1):
        for j in range(i+1,len(geometric_edges)):
            ea = geometric_edges[i]
            eb = geometric_edges[j]
            if (not(EdgesMeet(ea,eb)) and
                Graph.crossLines(ea.tail.p, ea.head.p,
                                 eb.tail.p, eb.head.p)):
                print("Edges Cross", i, j)
                Graph.ShowEdge(ea)
                Graph.ShowEdge(eb)
                return False
    return True

def EdgeCheck(e,vertices,edges,faces):
    if e.tail not in vertices:
        return False
    if e.head not in vertices:
        return False
    if e.head == e.tail:
        return False
    if e.leftFace not in faces:
        return False
    if e not in e.leftFace.edges:
        return False
    er = e.reverse
    if (er.reverse != e or er not in edges or er.head != e.tail or 
                          er.tail != e.head):
        return False 
    return True

def EdgesMeet(ea,eb):
    return (ea.tail == eb.tail or ea.tail == eb.head or
            ea.head == eb.tail or ea.head == eb.head)

def FacesCheck(vertices,edges,faces):
    width = max(v.p.x for v in vertices) - min(v.p.x for v in vertices)
    height = max(v.p.y for v in vertices) - min(v.p.y for v in vertices)
    min_clearance = 0.02 * min(width, height)
    for f in faces:
        if not(FaceCheck(f)):
            return False
        if f.bounded and FaceHasNarrowNeck(f, min_clearance):
            return False
    return True


def PointSegmentDistance(p, a, b):
    dx = b.x - a.x
    dy = b.y - a.y
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return Graph.pointDist(p, a)
    t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / length_squared
    t = max(0.0, min(1.0, t))
    projection = Graph.Vector(a.x + t * dx, a.y + t * dy)
    return Graph.pointDist(p, projection)


def SegmentDistance(ea, eb):
    return min(
        PointSegmentDistance(ea.tail.p, eb.tail.p, eb.head.p),
        PointSegmentDistance(ea.head.p, eb.tail.p, eb.head.p),
        PointSegmentDistance(eb.tail.p, ea.tail.p, ea.head.p),
        PointSegmentDistance(eb.head.p, ea.tail.p, ea.head.p),
    )


def FaceHasNarrowNeck(face, min_clearance):
    """Reject visually pinched faces whose nonincident boundaries nearly touch."""
    ee = face.edges
    for i in range(len(ee) - 1):
        for j in range(i + 1, len(ee)):
            if EdgesMeet(ee[i], ee[j]):
                continue
            if SegmentDistance(ee[i], ee[j]) < min_clearance:
                return True
    return False
    
    

def FaceCheck(f):
    global epsilon
    vv = f.vertices
    n = len(vv)-1
    if n < 3:
        return False
    ee = f.edges
    if (len(ee) != n):
        return False
    for va,vb,e in zip(vv,vv[1:n],ee):
       if ((va != e.tail) or (vb != e.head)):
           return False
    if (f.bounded and 
          (f.convex != Graph.computeConvex(f) or 
           abs(f.area - Graph.computeArea(f)) > epsilon)):
        return False
    return True
        
    
