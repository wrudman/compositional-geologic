
import numpy
import Graph
import GraphCheck
epsilon = 0.01
angleeps = 0.01

def makeFrame(x,y):
    global vertices, edges, faces
    Graph.initialize()
    vlb = Graph.Vertex(Graph.Vector(0,0))
    vrb = Graph.Vertex(Graph.Vector(x,0))
    vrt = Graph.Vertex(Graph.Vector(x,y))
    vlt = Graph.Vertex(Graph.Vector(0,y))
    
    vertices = [vlb,vrb,vrt,vlt]

    eb = Graph.Edge(vlb,vrb,True)
    er = Graph.Edge(vrb,vrt,True)
    et = Graph.Edge(vrt,vlt,True)
    el = Graph.Edge(vlt,vlb,True)

    ebx = eb.reverse
    erx = er.reverse
    etx = et.reverse
    elx = el.reverse

    vlb.outarcs = [eb,elx]
    vrb.outarcs = [er,ebx]
    vrt.outarcs = [et,erx]
    vlt.outarcs = [etx,el]

    edges = [eb,ebx,er,erx,et,etx,el,elx]
    
    outside = Graph.Face([elx,etx,erx,ebx], False)
    outside.trueEdges = outside.edges
    frame = Graph.Face([eb,er,et,el], True)  
    frame.trueEdges = frame.edges  
    faces = [outside,frame]
    vlb.faces = faces
    vrb.faces = faces
    vrt.faces = faces
    vlt.faces = [outside,frame]
    eb.leftFace = frame
    el.leftFace = frame
    et.leftFace = frame
    er.leftFace = frame
    ebx.leftFace = outside
    elx.leftFace = outside
    etx.leftFace = outside
    erx.leftFace = outside


    return vertices,edges,faces

def initGraph():
    global vertices, edges, faces
    vertices = []
    edges = []
    faces = []

def test1():
    initGraph()
    makeFrame(1,1)
    for v in vertices:
        print(str(v))
    for e in edges:
        print(str(e))
    for f in faces:
        print(str(f))
    return GraphCheck.GraphCheck(vertices,edges,faces)

