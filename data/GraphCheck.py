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
    for i in range(len(edges)-2):
        for j in range(i+2,len(edges)):    
            if (not(EdgesMeet(edges[i],edges[j])) and
                Graph.crossLines(edges[i].tail.p, edges[i].head.p,
                                edges[j].tail.p, edges[j].head.p)):
                print("Edges Cross", i, j)
                Graph.ShowEdge(edges[i])
                Graph.ShowEdge(edges[j])
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
    for f in faces:
        if not(FaceCheck(f)):
            return False
    return True
    
    

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
        
    
