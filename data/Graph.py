import numpy as np
angleeps = 0.00001
epsilon = 0.00001
smallAngle = 0.3
smallDist = 0.07

debug=True

class Vector:
    def __init__(self,x,y):
        self.x = x
        self.y = y
    def __str__(self):
        return f'< {self.x} {self.y} >'

class Vertex:
    def __init__(self,p):
        global vertexNum
        self.num = vertexNum
        vertexNum += 1
        self.p = p
        self.outarcs= []
        self.faces = [] 
 
    def __str__(self):
        return f'Vertex {self.num}'

class Edge:
    def __init__(self,tail,head,first):
        self.tail = tail
        self.tail.outarcs += [self]
        self.head = head
        self.leftFace = None
        if first:
            self.reverse = Edge(head,tail,False)
            self.reverse.reverse = self
        self.direction = PointDirection(tail.p,head.p)        
        self.trueEdge = self

    def __str__(self):
       return f'Edge {str(self.tail)} {str(self.head)}'

class Face:
    def __init__(self,edges,bounded):
        global faceNum
        self.num = faceNum
        self.letter = chr(ord('@')+faceNum)
        faceNum += 1
        self.edges = edges
        self.vertices = getVertices(edges)
        self.bounded = bounded
        self.numSides = len(edges)
        self.trueVertices = self.vertices
        if bounded:
            self.area = computeArea(self);
            self.convex = computeConvex(self);
            self.box = BoundingBox(self)

    def __str__(self):  
        return 'Face: ' + str(self.num) + " " + self.letter

class Map:
    def __init__(self,vertices,edges,faces,bounds):
        self.vertices = vertices
        self.edges = edges
        self.faces = faces
        self.bounds = bounds
 

def initialize():
    global vertexNum, faceNum
    vertexNum = 0
    faceNum = 0

def getVertices(edges):
    vv = [edges[0].tail]
    for e in edges:
        vv += [e.head]
    return vv

def getTrueEdges(face):
    ee = set()
    for e in face.edges:
        ee.add(e.trueEdge)
    return ee

def reverseEdges(ees):
    er = []
    for e in ees:
        er = [e.reverse] + er
    return er

def computeArea(face):
    sum = 0
    for e in face.edges:
       sum = sum + (e.tail.p.y + e.head.p.y)*(e.head.p.x - e.tail.p.x)
    return -(sum/2)

def computeConvex(face):
    ee = face.edges
    for i in range(len(ee)-1):
        if not(convexEdgeAngle(ee[i],ee[i+1])):
            return False;
    return convexEdgeAngle(ee[-1],ee[0])

def InteriorPath(face,pa,pb,path,eea,eeb):
# Case 1: If the path is empty, it's a direct straight cut from pa to pb
    if not path:
        return InteriorEdge(pa, pb, face, eea + eeb)
    if not InteriorEdge(pa,path[0],face,eea):
        return False
    k = len(path)
    if not InteriorEdge(path[k-1],pb,face,eeb):
        return False
    for i in range(k-1):
        if not InteriorEdge(path[i],path[i+1],face,[]):
            return False
    if not PathWellSeparated([pa]+path+[pb],face):
        return False
    return True

def PathSelfCrossing(path,loop):
    if len(path) < 4:
       return False
    for i in range(len(path)-3):
        for j in range(i+2,len(path)-1):
            if (not(i==0 and j==len(path)-2 and loop) and
               crossLines(path[i],path[i+1],path[j],path[j+1])):
               return True
    return False

def PathCounterClockwise(va,path):
    angsum = 0
    for i in range(0,len(path)-1):
        angsum = angsum + signedAngle(path[i],va,path[i+1])
    return angsum > 0

    

def InteriorEdge(pa,pb,face,contactEdges):
    global angleeps
    global debug
    mid = midpoint(pa,pb)
    if not(pointInsideFace(mid,face)):
#       print("Fail Midpoint" + str(mid))
        return False
    d = PointDirection(pa,pb)
    for e in contactEdges:
        if abs(d-e.direction) < angleeps:
           return False
#   print ("Pass Direction")
    for e in face.edges:
        if (e not in contactEdges) and crossLines(pa,pb,e.tail.p,e.head.p):
            if debug:
                print("Cross: pa", str(pa), " pb ", str(pb))
                ShowEdge(e)
                print("")
            return False
    return True

# check that all but the start and end vertices of path are well separated from
# the edges of face
def PathWellSeparated(path,face):
    pathname = ""
#    for p in path:
#        pathname += str(p) + ", "
#    print("PathWellSeparated:" + pathname + str(face))
    tooClose = 0.06
    npath = len(path)
    for v in face.vertices[1:]:
           for i in range(1,npath-1):
               if vecDist(v.p,path[i]) < tooClose:
                   return False
               if i < npath-2 and distPointFromEdge(v.p,path[i],path[i+1]) < tooClose:
                   return False
           if (vecDist(v.p,path[0]) > epsilon and 
               distPointFromEdge(v.p,path[0],path[1]) < tooClose):
                return False
           if (vecDist(v.p,path[-1]) > epsilon and 
               distPointFromEdge(v.p,path[-2],path[-1]) < tooClose):
                return False
    for p in path[1:npath-1]:
        for e in face.edges:
            if distPointFromEdge(p,e.tail.p,e.head.p) < tooClose:
                return False
    return True
           

def midpoint(pa,pb):
    return Vector((pa.x+pb.x)/2, (pa.y+pb.y)/2)

def angleAtFace(v,face):
    edges = ArcsAtVertexInFace(v,face)
    ea = edges[0]
    eb = edges[1].reverse
    d = eb.direction - ea.direction
    if d < 0:
        d += 2*np.pi
    return d    

def ArcsAtVertexInFace(v,face):
    edges = [0,0]
    for e in face.edges:
        if e.tail == v:
            edges[0] = e;
        if e.head == v:
            edges[1] = e
    return edges


def crossLines(at,ah,bt,bh):
    global angleeps
    if parallel(at,ah,bt,bh):
        pt = vecProject(at,bt,bh)
        ph = vecProject(ah,bt,bh)
        if not(tooClose(at,pt)):
            return False
        return (lineBetween(pt,bt,bh) or lineBetween(ph,bt,bh) or
            lineBetween(bt,pt,ph) or lineBetween(bh,pt,ph))
    pcross = lineIntersect(at,ah,bt,bh)
    return lineBetween(pcross,at,ah) and lineBetween(pcross,bt,bh)

def parallel(at,ah,bt,bh):  # Either parallel or anti-parallel
    return abs((bh.y-bt.y)*(ah.x-at.x) - (bh.x-bt.x)*(ah.y-at.y)) < angleeps

def LetterPointFace(face):
#   vv = face.vertices
#   pc = MeanOfVertices(vv[1:])
#   if face.convex:
#       return pc
    minX, maxX, minY, maxY = BoundingBox(face)
    count = 0
    maxD = 0
    while count < 40:
        p = randomPointInsideBox(minX, maxX, minY, maxY,True)       
        if pointInsideFace(p,face):
           count += 1
           dist = distPointFromFaceCutoff(p,face,maxD)
           if (dist > maxD):
              maxD = dist
              bestP = p
    return bestP, maxD

def randomPointInFace(face,uniform):
    minX, maxX, minY, maxY = face.box
    while True:
        p = randomPointInsideBox(minX,maxX,minY,maxY,uniform)
        if pointInsideFace(p,face):
            return p

def distBetweenFaces(f1,f2):
    for v in f1.vertices[1:]:
        if v in f2.vertices[1:]:
            return 0
    minD = 100
    for v1 in f1.vertices[1:]:
        for v2 in f2.vertices[2:]:
            d = pointDist(v1.p,v2.p)
            minD = min(minD,d)            
    for v in f1.vertices[1:]:
       for e in f2.edges:
           d=distPointFromEdge(v.p,e.tail.p,e.head.p)
           minD = min(minD,d)
    for v in f2.vertices[1:]:
       for e in f1.edges:
           d=distPointFromEdge(v.p,e.tail.p,e.head.p)
           minD = min(minD,d)    
    return minD

# Find the distance from point p to face, but we are only interested in that value
# if it is greater than maxD. As soon as it is determined that it is less than maxD,
# terminate the computation

def distPointFromFaceCutoff(p,face,maxD):
    minD = 100
    for v in face.vertices:
        dist = vecDist(p,v.p)
        if dist <= maxD:
           return maxD-1
        if dist < minD:
           minD = dist
    for e in face.edges:
        dist = distPointFromEdge(p,e.tail.p,e.head.p)
        if dist < maxD:
           return maxD-1
        if dist < minD:
           minD = dist
    return minD


def BoundingBox(face):
    maxX = -100
    minX = 100
    maxY = -100
    minY = 100
    for v in face.vertices:
        if (v.p.x < minX):
            minX = v.p.x
        if (v.p.x > maxX):
            maxX = v.p.x
        if (v.p.y < minY):
            minY = v.p.y
        if (v.p.y > maxY):
             maxY = v.p.y
    return minX, maxX, minY, maxY
 
def randomPointInsideBox(minX, maxX, minY, maxY,uniform):
    global epsilon
    if uniform:
        return Vector(np.random.uniform(minX,maxX),np.random.uniform(minY,maxY))    
    else:
        tx = clippedNormal(epsilon)
        ty = clippedNormal(epsilon)
        return Vector(tx*minX + (1-tx)*maxX, ty*minY + (1-ty)*maxY)

def clippedNormal(clip):
    while True:  
        x = np.random.normal(loc=0.5,scale=0.2)
        if clip < x and x < 1-clip:
            return x          
          


def MeanOfVertices(vv):
    mx = 0
    my = 0
    for v in vv:
        mx += v.p.x
        my += v.p.y
    return Vector(mx/len(vv), my/len(vv))


def convexEdgeAngle(e1, e2):
    global angleeps
    d = e2.direction - e1.direction
    p = np.pi
    return (((-angleeps <= d) and (d <= p+angleeps)) or 
            ((-2*p-angleeps <= d) and (d <= angleeps-p)))

def pointInsideFace(p,face):
    global angleeps, epsilon
    d = distPointFromFaceCutoff(p,face,epsilon)
    if (d <= epsilon):
        return False
    Sum = 0
    vv = face.vertices
    for i in range(len(vv)-1):
        pa = vv[i].p
        pb = vv[i+1].p
        Sum += signedAngle(pa,p,pb)
    return abs(Sum-2*np.pi) < angleeps

# the distance from p to the edge from pa to pb, assuming that the nearest point is not either
# pa or pb
def distPointFromEdge(p,pa,pb):
    z = vecProject(p,pa,pb)
    if lineBetween(z,pa,pb):
        return vecDist(p,z)
    else: 
        return 100



def edgeLength(e):
    return vecDist(e.tail.p,e.head.p)

def vecPlus(u,v):
    return Vector(u.x+v.x, u.y+v.y)

def vecMinus(v,u):
    return Vector(v.x-u.x, v.y-u.y)

def scalarTimesVec(c,v):
    return Vector(c*v.x,c*v.y)

def vecLength(v):
    return np.sqrt(v.x**2 + v.y**2)

def vecDist(u,v):
    return vecLength(vecMinus(v,u))

def vecProject(u,vt,vh):
    q = vecMinus(vh,vt)
    lq = vecLength(q)
    q = scalarTimesVec(1/lq,q)
    dd = (u.x-vt.x)*q.x + (u.y-vt.y)*q.y
    return vecPlus(vt,scalarTimesVec(dd,q))



# for u,v,w, points already determined to be collinear lineBetween(u,v,w) returns True if
# u lies between v and w inclusive, with roundoff

def lineBetween(u,v,w):
    global epsilon
    return (((v.x-epsilon < u.x < w.x+epsilon) or (w.x-epsilon <= u.x <= v.x+epsilon)) and
            ((v.y-epsilon < u.y < w.y+epsilon) or (w.y-epsilon <= u.y <= v.y+epsilon)))

def lineIntersect(a,b,c,d):
   e = b.x - a.x
   f = c.x - d.x
   g = d.x - a.x
   h = b.y - a.y
   i = c.y - d.y
   j = d.y - a.y
   t = (g*i-j*f)/(e*i-h*f)
   return Vector(a.x+t*(b.x-a.x),a.y+t*(b.y-a.y))

def tooClose(pa,pb):
    global smallDist
    return pointDist(pa,pb) < smallDist
   
def pointDist(pa,pb):
    return np.sqrt((pb.x-pa.x)**2+(pb.y-pa.y)**2)


def AngleTooSmall(a,b,c):
    global smallAngle
    d = signedAngle(a,b,c)
    return (abs(d) < smallAngle) or (abs(d-np.pi) < smallAngle) or (abs(d+np.pi) < smallAngle)

def signedAngle(a,b,c): # angle between b->a and b->c. Between -pi and pi
    d = PointDirection(b,c) - PointDirection(b,a)
    if d < -np.pi:
       d += 2*np.pi 
    if d > np.pi:
       d -= 2*np.pi
    return d

def UnitNormal(pa,pb):
    ux = pb.x-pa.x
    uy = pb.y-pa.y
    ll = np.sqrt(ux*ux+uy*uy)
    ux = ux/ll
    uy = uy/ll
    return Vector(uy,-ux)


def PointDirection(a,b):
    d = np.arctan2(b.y-a.y, b.x-a.x) 
    if d < 0:
       d += 2*np.pi 
    return d

def ShowVertex(v):
    print("Vertex, Num=", v.num, "x ", v.p.x, "y ", v.p.y)
    print("Outarcs:")
    for e in v.outarcs:
        print(str(e))
    for f in v.faces:
        print(str(f))

def ShowEdge(e):
    print("Edge From ", e.tail.num, "To ",  e.head.num)
    print("Direction:", e.direction)
    print("Reverse", str(e.reverse))
    print("TrueEdge", str(e.trueEdge))
    print("LeftFace", str(e.leftFace))

def ShowEdgeShort(e):
     print("Edge From ", e.tail.num, "To ",  e.head.num)

def ShowFace(f):
    print("Face:", f.num, f.letter)
    print("Vertices:")
    for v in f.vertices:
        print(str(v))
    print("Edges")
    for e in f.edges:
        print(str(e))
    print("Bounded", f.bounded)
    if (f.bounded):  
        print("Convex", f.convex, "Area", f.area)
        trueText = "True Vertices: "
        for v in f.trueVertices:
            trueText += str(v) + ", "
        print(trueText)

def ShowFaceShort(f):
    s = str(f) + " Vertices: " 
    for v in f.vertices:
        s += str(v) + "  "
    print(s)

def ShowMap(vertices,edges,faces):
    for v in vertices:
        ShowVertex(v)
        print("")
    print("")
    for f in faces:
        ShowFace(f)
        print("")
    print("")
    for e in edges:
         ShowEdge(e)
         print("")

