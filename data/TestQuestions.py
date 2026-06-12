from Graph import Map, Vector, vecDist 
import Split, Questions, Frame, FinalizeFaces, DrawGraph, BuildRandomMap
import numpy as np

global map
global epsilon
epsilon = 0.00001

def randomSetup(seed):
    global map
    map= BuildRandomMap.BuildRandomMap(10,1,1,seed)


def setup1():
    global map
    setup1A()
    faces = FinalizeFaces.FinalizeFaces(Split.vertices,Split.edges,Split.faces)
    DrawGraph.DrawGraph(faces,1,1)
    map = Map(Split.vertices,Split.edges,Split.faces,(1,1))

def setup1A():
    setup1B()
    face = FindFace(Split.faces, [(0,0.7), (1,0.7), (1,1), (0,1)])
    ea = FindEdge(face.edges, [(0,0.7),(1,0.7)])
    eb = FindEdge(face.edges, [(1,1),(0,1)])
    Split.SplitFaceEE(face,ea,Vector(0.3,0.7),eb,Vector(0.3,1))

def setup1B():
    global vertices,edges,faces
    Split.vertices, Split.edges, Split.faces = Frame.makeFrame(1,1)
    frame = Split.faces[1]
    ea = frame.edges[3]
    eb = frame.edges[1]
    Split.SplitFaceEE(frame,ea, Vector(0,0.7),eb, Vector(1,0.7)) 
    face = FindFace(Split.faces, [(0,0), (1,0), (1,0.7), (0,0.7)])
    ea = FindEdge(face.edges, [(0,0.7),(0,0)])
    eb = FindEdge(face.edges, [(1,0),(1,0.7)])
    Split.SplitFaceEE(face,ea, Vector(0,0.3),eb, Vector(1,0.3))


def setup2():
    global map
    setup2B()
    faces = FinalizeFaces.FinalizeFaces(Split.vertices,Split.edges,Split.faces)
    DrawGraph.DrawGraph(faces,1,1)
    map = Map(Split.vertices,Split.edges,Split.faces,(1,1))

def setup2A():
    setup1A()
    face = FindFace(Split.faces, [(0.3,0.7), (1,0.7), (1,1), (0.3,1)])
    ea = FindEdge(face.edges, [(0.3,0.7), (1,0.7)])
    eb = FindEdge(face.edges, [(1,1), (0.3,1)])
    Split.SplitFaceEE(face,ea, Vector(0.4,0.7),eb, Vector(0.4,1))
    

def setup2B():
    setup2A()
    face = FindFace(Split.faces, [(0.4,0.7), (1,0.7), (1,1), (0.4,1)])
    ea = FindEdge(face.edges, [(0.4,0.7), (1,0.7)])
    eb = FindEdge(face.edges, [(1,1), (0.4,1)])
    Split.SplitFaceEE(face,ea, Vector(0.6,0.7),eb, Vector(0.6,1))
    face = FindFace(Split.faces, [(0.6,0.7), (1,0.7), (1,1), (0.6,1)])
    ea = FindEdge(face.edges, [(0.6,0.7), (1,0.7)])
    eb = FindEdge(face.edges, [(1,1), (0.6,1)])
    Split.SplitFaceEE(face,ea, Vector(0.8,0.7),eb, Vector(0.8,1))


def setup3():
    global map
    setup3A()
    faces = FinalizeFaces.FinalizeFaces(Split.vertices,Split.edges,Split.faces)
    DrawGraph.DrawGraph(faces,1,1)
    map = Map(Split.vertices,Split.edges,Split.faces,(1,1))

def setup3A():
    setup1A()
    face = FindFace(Split.faces, [(0,0.3), (1,0.3), (1,0.7), (0,0.7)])
    v = Split.vertices[4]
    e = FindEdge(face.edges, [(0,0.3),(1,0.3)])
    Split.SplitFaceVE(face,v,e, Vector(0.5,0.3))
    face = FindFace(Split.faces, [(0,0.7), (0.5,0.3), (1,0.3), (1,0.7)])
    va = Split.vertices[5]
    vb = Split.vertices[10]
    Split.SplitFaceVV(face,va,vb)

    
def setup4():
    global map
    setup1A()
    face = FindFace(Split.faces, [(0,0.3), (1,0.3), (1,0.7), (0,0.7)])
    va = Split.vertices[4]
    vb = Split.vertices[7]
    Split.SplitFaceVV(face,va,vb)
    face = FindFace(Split.faces, [(0,0.7),(1,0.3), (1,0.7),(0.3,0.7)])
    va = Split.vertices[8]
    vb = Split.vertices[7]
    Split.SplitFaceVV(face,va,vb)
    faces = FinalizeFaces.FinalizeFaces(Split.vertices,Split.edges,Split.faces)
    DrawGraph.DrawGraph(faces,1,1)
    map = Map(Split.vertices,Split.edges,Split.faces,(1,1))

def setup5():
    global map
    setup1A()
    face = FindFace(Split.faces, [(0,0.3), (1,0.3), (1,0.7), (0,0.7)])
    v = Split.vertices[4]
    e = FindEdge(face.edges, [(0,0.3),(1,0.3)])
    Split.SplitFaceVE(face,v,e, Vector(0.15,0.3))
    face = FindFace(Split.faces, [(0,0.7), (0.15,0.3), (1,0.3), (1,0.7)])
    va = Split.vertices[8]
    vb = Split.vertices[10]
    Split.SplitFaceVV(face,va,vb)
    faces = FinalizeFaces.FinalizeFaces(Split.vertices,Split.edges,Split.faces)
    DrawGraph.DrawGraph(faces,1,1)
    map = Map(Split.vertices,Split.edges,Split.faces,(1,1))

def setup6():
    global map
    setup1B()
    face = FindFace(Split.faces, [(0,0.3), (1,0.3), (1,0.7), (0,0.7)])
    ea = FindEdge(face.edges, [(0,0.3), (1,0.3)])    
    eb = FindEdge(face.edges, [(1,0.7), (0,0.7)])    
    Split.SplitFaceEE(face,ea,Vector(0.4,0.3),eb,Vector(0.4,0.7))
    face = FindFace(Split.faces, [(0.4,0.3), (1,0.3), (1,0.7), (0.4,0.7)])
    ea = FindEdge(face.edges, [(0.4,0.3), (1,0.3)])     
    eb = FindEdge(face.edges, [(1,0.7), (0.4,0.7)])    
    Split.SplitFaceEE(face,ea,Vector(0.6,0.3),eb,Vector(0.6,0.7))
    face = FindFace(Split.faces, [(0,0.3), (0.4,0.3), (0.4,0.7), (0,0.7)])
    edge = FindEdge(face.edges, [(0,0.7), (0,0.3)])
    pa =  Vector(0,0.6)
    pb =  Vector(0,0.4)
    path = [ Vector(0.2,0.6),  Vector(0.2,0.4)]
    Split.SplitFaceSameEdgePath(face,edge,pa,pb,path)
    face = FindFace(Split.faces, [(0.6,0.3), (1,0.3), (1,0.7), (0.6,0.7)])
    edge = FindEdge(face.edges, [(1,0.3), (1,0.7)])
    pa =  Vector(1,0.6)
    pb =  Vector(1,0.4)
    path = [ Vector(0.8,0.6),  Vector(0.8,0.4)]
    Split.SplitFaceSameEdgePath(face,edge,pa,pb,path)
    faces = FinalizeFaces.FinalizeFaces(Split.vertices,Split.edges,Split.faces)
    DrawGraph.DrawGraph(faces,1,1)
    map = Map(Split.vertices,Split.edges,Split.faces,(1,1))

def setup7():
    global map
    setup1B()
    face = FindFace(Split.faces, [(0,0.3), (1,0.3), (1,0.7), (0,0.7)])
    ea = FindEdge(face.edges, [(0,0.3), (1,0.3)])    
    eb = FindEdge(face.edges, [(1,0.7), (0,0.7)])    
    Split.SplitFaceEE(face,ea,Vector(0.4,0.3),eb,Vector(0.4,0.7))
    face = FindFace(Split.faces, [(0.4,0.3), (1,0.3), (1,0.7), (0.4,0.7)])
    ea = FindEdge(face.edges, [(0.4,0.3), (1,0.3)])     
    eb = FindEdge(face.edges, [(1,0.7), (0.4,0.7)])    
    Split.SplitFaceEE(face,ea,Vector(0.6,0.3),eb,Vector(0.6,0.7))
    face = FindFace(Split.faces, [(0,0.3), (0.4,0.3), (0.4,0.7), (0,0.7)])
    edge = FindEdge(face.edges, [(0.4,0.3), (0.4,0.7)])
    pa =  Vector(0.4,0.4)
    pb =  Vector(0.4,0.6)
    path = [ Vector(0.2,0.4),  Vector(0.2,0.6)]
    Split.SplitFaceSameEdgePath(face,edge,pa,pb,path)
    face = FindFace(Split.faces, [(0.6,0.3), (1,0.3), (1,0.7), (0.6,0.7)])
    edge = FindEdge(face.edges, [(0.6,0.7), (0.6,0.3)])
    pa =  Vector(0.6,0.4)
    pb =  Vector(0.6,0.6)
    path = [ Vector(0.8,0.4),  Vector(0.8,0.6)]
    Split.SplitFaceSameEdgePath(face,edge,pa,pb,path)
    faces = FinalizeFaces.FinalizeFaces(Split.vertices,Split.edges,Split.faces)
    DrawGraph.DrawGraph(faces,1,1)
    map = Map(Split.vertices,Split.edges,Split.faces,(1,1))

def test1(n):
    return Questions.Question1(FindFaceByName(n))

def test2(n1,n2):
    global map
    face1 = FindFaceByName(n1)
    face2 = FindFaceByName(n2)
    return Questions.Question2(face1,face2,map)
    
def test3():
    global map
    return Questions.Question3(map)

def test4(nf,nv,cyclicDirection,code):
    return Questions.Question4(FindFaceByName(nf), map.vertices[nv], cyclicDirection, code)

def test5():
    global map
    return Questions.Question5(map)

def test6():
    global map
    return Questions.Question6(map)

def test7():
    global map
    return Questions.Question7(map)

def test8(k):
    global map
    return Questions.Question8(map,k)

def test9(n):
    global map
    face = FindFaceByName(n)
    return Questions.Question9(face)

def test10(np,nu,nv,nw,codeP,codeU,codeV,codeW):
     global map
     vv = map.vertices
     return Questions.Question10(vv[np],vv[nu],vv[nv],vv[nw],codeP,codeU,codeV,codeW)



def test10A():
    randomSetup(1)
    test10(7,0,0,13,9,1,0,1,2)
    
def test10B():
    randomSetup(2)
    test10(0,4,0,13,15,0,17,12,0)

def test11(n,codes):
    return Questions.Question11(FindFaceByName(n),codes)

def test12(na,nb,code):
    return Questions.Question12(map.vertices[na], map.vertices[nb],code,map)

def test13(n,code):
    return Questions.Question13(map.vertices[n], code)

def test14(na,nb):
    return Questions.Question14(FindFaceByName(na),FindFaceByName(nb))

def test15(na,nb):
    return Questions.Question15(FindFaceByName(na),FindFaceByName(nb),map)

def test16(names):
    faces = []
    for n in names:
        if type(n) is list:
            [na, nb] = n
            faces += [[FindFaceByName(na),FindFaceByName(nb)]]
        else:
            faces += [FindFaceByName(n)]
    return Questions.Question16(faces,map)

def test17():
    return Questions.Question17(map)

def test18(na,nb,codeA,codeB):
    return Questions.Question18(map.vertices[na], map.vertices[nb],codeA,codeB,map)

def test19(n,direction,code):
    return Questions.Question19(map.vertices[n],direction,code,map)

def test20(na,nb,nc,direction,codeA,codeB,codeC):
    return Questions.Question20(map.vertices[na], map.vertices[nb],map.vertices[nc],
                                direction,codeA,codeB,codeB,)
def test21(na,nb,nc,codeA,codeB,codeC):
    return Questions.Question21(map.vertices[na], map.vertices[nb],map.vertices[nc],
                                codeA,codeB,codeC)

def test22(na,nb,nc,nd,codeA,codeB,codeC,codeD):
    return Questions.Question22(map.vertices[na], map.vertices[nb],map.vertices[nc],
                                map.vertices[nd],codeA,codeB,codeC,codeD)

def test23(dir):
    return Questions.Question23(dir,map)

def test24(na,nb,nc):
    return Questions.Question24(FindFaceByName(na),FindFaceByName(nb),
                                FindFaceByName(nc))

def FindFaceByName(name):
    global map
    for face in map.faces:
        if face.letter == name:
            return face
    print("No face", name, "found")
  
def FindFace(faces, points):
     vecs = Points2Vectors(points)
     for face in faces:
              if face.bounded and MatchFaceToPoints(face,vecs):
                  return face
     print("FindFace Unsuccessful")
     return False

def FindEdgeByNumbers(na,nb):
    global map
    for e in map.edges:
        if e.tail.num == na and e.head.num == nb:
            return e
    print("No edge ", na, nb, " found")
 
      
def FindEdge(edges,points):
    vecs = Points2Vectors(points)
    for edge in edges:
        if MatchEdgeToPoints(edge,vecs):
            return edge
    print("FindEdge Unsuccessful")
    return False

def Points2Vectors(points):
    vecs = []
    for p in points:
        x,y = p
        vecs += [ Vector(x,y)]
    return vecs

def MatchFaceToPoints(face,vecs):
    for vec in vecs:
        found = False
        for v in face.vertices:
            found = vecDist(v.p,vec) < 0.02
            if found:
               break
        if not found:
            return False
    return True

def MatchEdgeToPoints(edge,vecs):
    return (vecDist(edge.tail.p,vecs[0]) < 0.02 and  
            vecDist(edge.head.p,vecs[1]) < 0.02)        
