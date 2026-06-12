import Graph
import Split
import FinalizeFaces
import numpy as np
from itertools import product
import random
import matplotlib.pyplot as plt



global epsilon, angleeps,smallDist, smallAng, failureOutput
epsilon = 0.0001
angleeps = 0.00001
smallDist = 0.07
smallAng=0.1
failureOutput = ("", "", False, 0)

class PseudoFace:
    def __init__(self,vertices,edges):
        self.vertices = vertices
        self.edges = edges
        self.bounded = True
        self.convex = Graph.computeConvex(self)
        self.box = Graph.BoundingBox(self)
        self.trueVertices  = FinalizeFaces.SetTrueVertices(self)  
        self.numSides = len(self.trueVertices)-1
        self.letter = 'Z'


#                          QUESTION 1 

def DisplayQAs(qaList):
    for qa in qaList:
        question,answerText = qa
        print(question)
        print(answerText)
         



def Question1(face):
    question = "Which regions border region " + face.letter + " along an edge?"
    answerSet = set()
    for e in face.edges:
        fb = e.reverse.leftFace        
        if fb.bounded:
            answerSet.add(fb)
    answerText = Faces2Text(answerSet)         
    return question, answerText, answerSet, len(answerSet)

#                          QUESTION 2

def Question2(fa, fb):
    """Comparative reasoning: Do two regions have the same number of sides?"""
    if fa == fb or not fa.bounded or not fb.bounded:
        return failureOutput
    
    # Reuse your existing numSides attribute
    count_a = fa.numSides
    count_b = fb.numSides
    
    question = f"Do region {fa.letter} and region {fb.letter} have the same number of sides?"
    answerText = "Yes" if count_a == count_b else "No"
    
    # Quality: More sides = harder counting task
    quality = (count_a + count_b) / 4.0
    return question, answerText, (count_a == count_b), quality                                               



def DirsOnLeftSide(d,da,db):
    global angleeps
    if da < d:
        da = da+2*np.pi
    if db < d:
        db = db+2*np.pi   
    return d-angleeps < da and da < db and db < d+np.pi+angleeps



def Q2FacesFromVertices(vvs,quad):
    global verticesIn,angleeps
    verticesIn = set()
    quadDirs=[]
    for i in range(4):
        quadDirs += [Graph.PointDirection(quad[i],quad[i+1])]
    for v in vvs:
        if inQuad(v.p,quad): 
            verticesIn.add(v)
            for f in v.faces:
                AddFacesIn(f)
        else: 
            for i in range(4):
                if PointOnQuadBoundary(v.p,quad[i],quad[i+1]):
                    for e in v.outarcs:
                        if BetweenDirs(quadDirs[i],e.direction,quadDirs[i]+np.pi):
                           AddFacesIn(e.leftFace)
                           AddFacesIn(e.reverse.leftFace)


def inQuad(p,quad):
    for i in range(4):
        if quad[i+1] != quad[i] and not leftOf(p,quad[i],quad[i+1]):
            return False
    return True


def leftOf(p,qa,qb):
    return (p.y-qa.y)*(qb.x-qa.x) - (p.x-qa.x)*(qb.y-qa.y) > epsilon

# returns True if p lies on the line strictly between pa and pb (with an epsilon separation)  
def PointOnQuadBoundary(p,qa,qb):
    global epsilon
    return ((abs((p.y-qa.y)*(qb.x-qa.x) - (p.x-qa.x)*(qb.y-qa.y)) < epsilon) and 
               ((p.x-qa.x)*(qb.x-p.x) + (p.y-qa.y)*(qb.y-p.y) > epsilon))

def Q2FacesFromEdges(edges,quad):
    for e in edges:
        if EdgeCrossesThroughQuad(e,quad): 
            AddFacesIn(e.leftFace)
            AddFacesIn(e.reverse.leftFace)
        if EdgeAlignsBoundary(e,quad):
            AddFacesIn(e.leftFace)

def EdgeAlignsBoundary(e,quad):
    for i in range(4):
        if DirectedSegmentsAlign(e.tail.p,e.head.p,quad[i],quad[i+1]):
           return True
    return False

# pa,pb,qa,qb are collinear; pa-pb is parallel to qa-qb (rather than anti-parallel)
# and overlaps it.

def DirectedSegmentsAlign(pa,pb,qa,qb):
    return (Graph.parallel(pa,pb,qa,qb) and Graph.parallel(qa,pa,qa,qb) and
            ((pb.x-pa.x)*(qb.x-qa.x) + (pb.y-pa.y)*(qb.y-qa.y) > epsilon) and
            ((pb.x-qa.x)*(pb.x-pa.x) + (pb.y-qa.y)*(pb.y-pa.y) > epsilon) and
            ((qb.x-pa.x)*(pb.x-pa.x) + (qb.y-pa.y)*(pb.y-pa.y) > epsilon))

def AddFacesIn(face):
    global facesIn, facesOut
    if face.bounded and face not in facesOut:
       facesIn.add(face)

def EdgeCrossesThroughQuad(e,quad):
    global verticesIn
    if e.tail in verticesIn or e.head in verticesIn:
        return False
    if (quad[0]==quad[1]) or (quad[2]==quad[3]):
        return False
    pt = e.tail.p
    ph = e.head.p
    if (Graph.parallel(pt,ph,quad[0],quad[1]) or
        Graph.parallel(pt,ph,quad[2],quad[3])):
        return False
    crossBot =  Graph.lineIntersect(pt,ph,quad[0],quad[1])
    crossTop =  Graph.lineIntersect(pt,ph,quad[2],quad[3])
    midpoint = Graph.midpoint(crossBot,crossTop)
    return (Graph.lineBetween(crossBot,quad[0],quad[1]) and 
              Graph.lineBetween(crossBot,pt,ph) and
              Graph.lineBetween(crossTop,quad[2],quad[3]) and
              Graph.lineBetween(crossTop,pt,ph) and
              inQuad(midpoint,quad))
  
      
def VerticesBetweenOnFace(face,va,vb):
    i = face.vertices.index(va)
    j = face.vertices.index(vb)
    if i < j:
        return face.vertices[i+1:j]
    else:
        return face.vertices[i+1:] + face.vertices[1:j]
           
  
def BetweenDirs(da,db,dc):
    global angleeps
    ba = db - da
    cb = dc - db
    if ba < 0:
        ba = ba+2*np.pi
    if cb < 0:
        cb = ba+2*np.pi
    return ba < np.pi-angleeps and cb < np.pi-angleeps  

#                          QUESTION 3            

def Question3(map):
    question = "Which if any of the regions are not convex?"
    answerSet = set()
    for face in map.faces:            
        if face.bounded and not face.convex:
            answerSet.add(face)
    answerText = Faces2Text(answerSet)         
    return question, answerText, answerSet, 1+len(answerSet)
    


#                          QUESTION 4

def Question4(face,v,cyclicDirection,vIdentCode):
    if v not in face.vertices:
        return failureOutput
    vName = identifyVertex(v,vIdentCode)
    if vName == "":
         return failureOutput  
    questionText = "Let p be " + vName + ". "
    questionText += "Suppose that someone starts at p and goes " + cyclicPhrase(cyclicDirection)
    questionText += " around " + face.letter + " until they have returned to p. "
    questionText += "What regions do they pass on their " + oppSidePhrase(cyclicDirection) 
    questionText += " in sequence? For this question, include the outside of the frame."
    answerList = Question4Compute(face,v,cyclicDirection)
    if (answerList == []):
        return failureOutput
    answerText = Faces2Text(answerList) 
    return questionText, answerText, answerList, len(answerList)

# Exclude questions where the path passes some face on a single vertex, because
# of ambiguity

def Question4Compute(face,v,CyclicDirection):
    faceList = []
    found = False
    Done = False
    for e in face.edges:       
        if len(e.tail.outarcs) > 3: # Avoid the ambiguity involved when two faces meet at a single vertex
            return []
        if e.tail == v:
            found = True
        if found:
            newFace = e.reverse.leftFace
            if faceList == []:
                faceList = [newFace]
            elif faceList[-1] != newFace:
                faceList += [newFace]   
    if face.edges[-1].head != v:
        for e in face.edges:
            newFace = e.reverse.leftFace
            if faceList[-1] != newFace:
                faceList += [newFace]
            if e.head == v:
                break
    if not CyclicDirection:  
        faceList.reverse()
    return faceList
    
        
def cyclicPhrase(direction):
    if direction:
        return "counterclockwise"
    else:
        return "clockwise"

def oppSidePhrase(direction):
     if direction:
         return "right"
     else:
         return "left"

#                          QUESTION 5

def Question5(map):
    question = "Which pairs of regions, if any, meet at a vertex but not along an edge?"
    answerSet = set()
    answerText="{"
    found = False
    for v in map.vertices:  
        ff = v.faces
        for i in range(len(ff)-1):
            if ff[i].bounded:
                fi = ff[i]
                eer = Graph.reverseEdges(ff[i].edges)
                for j in range(i+1, len(ff)):
                    fj = ff[j]
                    if disjointLists(eer,fj.edges) and (fi,fj) not in answerSet and (fj,fi) not in answerSet:
                        if found:
                            answerText += ", " + FacePair2Text(fi,fj)
                        else:
                            answerText += FacePair2Text(fi,fj)
                            found = True
                        answerSet.add((fi,fj))
    if len(answerSet) == 0:
        answerText = "None"
    else:
        answerText += "}"    
    return question, answerText, answerSet, 1+len(answerSet)


#                          QUESTIONS 6 & 7
def Question6(map):
    global answerSet
    question = "Which pairs of regions, if any, meet along two or more disconnected edges? " 
    question += "Do not include the outside of the frame."
    answerSet = set()
    for f in map.faces[1:]:
        Question6A(f,False)
    if len(answerSet)==0:
        return failureOutput
    return question, FacePairCollection2Text(answerSet), answerSet, 1+len(answerSet)

def Question7(map):
    global answerSet
    question = "Which regions, if any, meet the outside of the frame " 
    question += "along two or more disconnected edges?"
    answerSet = set() 
    Question6A(map.faces[0],True)
    return question, Faces2Text(answerSet), answerSet, 1+len(answerSet)



def Question6A(f,isFrame):
    global answerSet
    ee = f.edges
    oppfaces = [ee[0].reverse.leftFace]
    for i in range(1,len(ee)):
        opp = ee[i].reverse.leftFace
        if (opp.num > f.num and opp in oppfaces and   # Avoid finding the same pair in opposite order
              opp != ee[i-1].reverse.leftFace):
             if oppfaces.index(opp)==0:
                 for k in range(i+1,len(ee)):
                     if ee[k].reverse.leftFace != opp:
                         if isFrame:
                             answerSet.add(opp)
                         else:
                             answerSet.add((f,opp))
             elif isFrame:
                 answerSet.add(opp)
             else:
                 answerSet.add((f,opp))
        oppfaces += [opp]

#                          QUESTIONS 8 and 9
 
def Question8(map,k):
    question = "Which regions have " + str(k) + " sides?" 
    answerSet = set()
    for f in map.faces:
        if f.bounded and f.numSides == k:
            answerSet.add(f)
    return question, Faces2Text(answerSet), answerSet, 1+len(answerSet)

def Question9(f):
    question = "How many sides does region " + f.letter + " have?"
    k = f.numSides
    return question, str(k), k, 1+k


#                          QUESTION 10

def Question10(vp,vu,vv,vw,codeP,codeU,codeV,codeW):
    if not distinct([vp,vu,vv,vw]):
        return failureOutput
    distA = Graph.pointDist(vp.p,vu.p)
    distB = Graph.pointDist(vp.p,vv.p)
    distC = Graph.pointDist(vp.p,vw.p)
    dists, text, vertexPairs = order3([distA,distB,distC], ["u","v","w"], 
                                      [vu,vv,vw])
    q = Question10Quality(dists)
    if q==0:
        return failureOutput  
    question = LetVerticesBeText([vp,vu,vv,vw],['p','u','v','w'],[codeP,codeU,codeV,codeW]) 
    if question == "":
        return failureOutput                
    question = question + "Sort u, v, w in increasing order of distance from p."
    return question, text, vertexPairs, q


      
def Question10Quality(dists):
    if dists[0] == 0:
        return 0
    r1 = dists[1] / dists[0]
    r2 = dists[2] / dists[1]
    if r1 < 1.5 or r2 <  1.5:
        return 0
    else:
        return r1 + r2 

    


def Q10VerticesTexts(v1,v2,count):
    match count:
          case 0:
             v1Name = "a"
             v2Name = "b"
             dName = "x"
          case 1:
             v1Name = "c"
             v2Name = "d"
             dName = "y"
          case 2:
             v1Name = "p"
             v2Name = "q"
             dName = "z"
    vTexts1 = vertexIdentifiers(v1)
    vTexts2 = vertexIdentifiers(v2)
    texts = []
    for te1 in vTexts1:
        for te2 in vTexts2:
            text = "Let " + v1Name + " be " + te1 + ".\n" 
            text += "Let " + v2Name + " be " + te2 + ".\n"  
            text += "Let " + dName + " be the distance from " + v1Name + " to " +  v2Name + ".\n"
            texts = texts + [text]
    return texts

#                          QUESTION 11

def Question11(fa,codes):  
    global smallAng
    vvs = fa.trueVertices[1:]
    n = len(vvs)
    angles = []
    for v in vvs:
        angles += [Graph.angleAtFace(v,fa)]
    angles, indices = parallelSort(angles,list(range(len(vvs))))
    quality = Q11Quality(angles,n)
    if quality == 0:
        return failureOutput  
    question = "Region " + fa.letter + " has " + str(n) + " vertices: "
    for i in range(n):
        vName = identifyVertexForQ11(vvs[i],fa,codes[i])
        if vName == "":
            return failureOutput
        question = question + "(" + str(i+1) + ") " + vName
        if i==n-1:
            question += ". "
        else:
            question += "; "
    question += "Sort these in increasing order by the size of the interior angle at each corner."
    answerList = []
    for i in range(n):
        answerList += [vvs[indices[i]]]
        indices[i] += 1
    return question, str(indices), answerList, quality
   
def Q11Quality(angles,n):
    quality = 7
    for i in range(n-1):
         diff = angles[i+1] - (angles[i] + (10*np.pi/180))
         if diff < 0:    
             return 0
         else:
            if diff < quality:
               quality = diff
    return quality


#                          QUESTION 12
def Question12(va, vb, code, map):
    """
    Evaluates regions crossed by extending an edge into an infinite line.
    Includes a consistency check between mathematical and visual thresholds.
    """
    if BoundaryEdge(va.p, vb.p, map.bounds):
        return failureOutput
        
    texts = identifyEdgeTexts(va, vb)
    if texts == []:
        return failureOutput

    # --- ROBUSTNESS SAFEGUARD ---
    # Define thresholds: 0.0005 for math truth, 0.03 for visual clarity
    MATH_THRESHOLD = 0.0001
    VISUAL_THRESHOLD = 0.03

    # 1. Get Mathematical Ground Truth (True crosses)
    true_answers, t_qual = LineCrossesFaces(va.p, vb.p, True, map, threshold=MATH_THRESHOLD)
    
    # 2. Get Visual Ground Truth (Clear crosses)
    robust_answers, r_qual = LineCrossesFaces(va.p, vb.p, True, map, threshold=VISUAL_THRESHOLD)

    # 3. REJECTION LOGIC: 
    # If the lists differ, the line passes too close to a boundary/vertex.
    # We discard the question to maintain benchmark purity.
    if [f.letter for f in true_answers] != [f.letter for f in robust_answers]:
        return failureOutput
    
    # If the engine itself flagged an error or ambiguity
    if r_qual < 0:
        return failureOutput
    # ----------------------------

    question = "Let m be " + decode(texts, code) + ". "
    question += "Suppose m is extended in both directions along straight line L. "
    question += "Which are the regions R in the diagram for which L passes through the interior of R? "
    question += "(Do not include a region R if L only aligns with the boundary of R, "
    question += "and does not go through R's interior)"

    if len(robust_answers) == 0:
        answerNameList = "None"
    else:
        # Use list comprehension for cleaner Pythonic style
        answerNameList = [a.letter for a in robust_answers]
        
    # Quality scales with complexity (number of regions crossed)
    return question, str(answerNameList), robust_answers, len(robust_answers) * r_qual

  
def BoundaryEdge(pa,pb,bounds):
    bigX,bigY = bounds
    return (pa == pb or ((pa.x == pb.x) and (pa.x in [0,bigX])) or 
            ((pa.y == pb.y) and (pa.y in [0,bigY])))
       
                            



def LineCrossesFaces(pa, pb, visibleSeg, map, threshold=None):
    global epsilon, angleeps
    # Use the provided threshold or fall back to the global smallAng
    current_threshold = threshold if threshold is not None else smallAng

    d_dist = Graph.vecDist(pa, pb)
    if d_dist < epsilon: 
        return [], -1
        
    n = len(map.vertices)
    angleAtA = [100] * n
    angleAtB = [100] * n
    coins = []
    
    for i in range(n):
        v = map.vertices[i]
        if Graph.vecDist(v.p, pa) < epsilon or Graph.vecDist(v.p, pb) < epsilon:
            coins.append(v)
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
            if v1 in coins or abs(angleAtA[j]) < angleeps:
                 continue
            
            v2 = f.vertices[i+1]
            k = v2.num
            
            d_val = max(angleAtA[j], -angleAtB[j]) if angleAtA[j] > 0 else min(angleAtA[j], -angleAtB[j])
            
            extremeLeft = max(extremeLeft, np.sin(d_val))
            extremeRight = min(extremeRight, np.sin(d_val))
            
            if v2 in coins:
                dLeft, dRight = OnePointDefSide(angleAtA[j], angleAtB[j])
            else:
                dLeft, dRight = TwoPointDefSide(angleAtA[j], angleAtA[k], angleAtB[j], angleAtB[k], visibleSeg)          
            
            if dLeft:
                extremeLeft = 1
            if dRight:
                extremeRight = -1
        
        # USE THE PARAMETERIZED THRESHOLD HERE
        if -current_threshold < extremeLeft < current_threshold or -current_threshold < extremeRight < current_threshold:
           return [], -1
           
        if extremeLeft > current_threshold and extremeRight < -current_threshold:
            crossedFaces.append(f) 
            
        quality = min(quality, abs(extremeLeft), abs(extremeRight))
        
    return crossedFaces, quality








#                          QUESTION 13-15

def Question13(v,code):
    answerNames = []
    answer = []
    possIDs = []
    for f in v.faces:
        if not f.bounded:
           return failureOutput
        answerNames += [f.letter]
        answer += [f] 
        possIDs += faceExtremeVertexID(v,f,True)
    if possIDs == []:
        return failureOutput
    id = decode(possIDs,code)
    question = "Let p be " + id + ". Which regions meet at p?"
    return question, str(answerNames), answer, len(answer)
    

def Question14(fa,fb):
    fu = FaceUnion(fa,fb)
    if fu==False:
        return failureOutput
    question = UnionText(fa,fb,'U')
    question += "How many sides does U have?"
    return question, str(fu.numSides), fu.numSides, fu.numSides + len(fu.edges) 

def Question15(fa,fb,map):
    if fa==fb or not fa.bounded or not fb.bounded:
        return failureOutput
    fu = FaceUnion(fa,fb)
    if fu==False:
        return failureOutput
    question = UnionText(fa,fb,'U')
    lastLetter = chr(ord('@')+len(map.faces)-1)
    question += "Which of the labelled regions A-" + lastLetter + " does U border on an edge?"
    answerSet = set()
    for e in fa.edges:
        f = e.reverse.leftFace
        if f != fb and f.bounded:
            answerSet.add(f)
    for e in fb.edges:
        f = e.reverse.leftFace
        if f != fa and f.bounded:
            answerSet.add(f)
    answerText = Faces2Text(answerSet)
    return question, answerText, answerSet, len(answerSet)

#                          QUESTION 16

def Question16(faces,map):
    newFaces = []
    question = ""
    pairNum = len(map.faces) + 3
    for f in faces:
        if type(f) is list:
            [fa,fb] = f
            f = FaceUnion(fa,fb)
            if f==False:
                return failureOutput
            f.letter = chr(ord('@')+pairNum)
            pairNum += 1
            question += UnionText(fa,fb,f.letter)
        newFaces += [f]
    question += "Sort regions " + Faces2Text(newFaces) + " in order of increasing area:"
    areas = []
    for f in newFaces:
        areas += [f.area]
    areas, newFaces = parallelSort(areas,newFaces)
    for i in range(len(areas)-1):
        if areas[i+1] < areas[i]*1.5:
            return failureOutput 
    return question, Faces2Text(newFaces), newFaces, len(newFaces)


# ==========================================
#                          QUESTION 17
# ==========================================
def Question17(fa, fb):
    """
    Checks if the union of two adjacent regions is convex.
    Returns: (question, answerText, is_convex, quality)
    """
    if fa == fb or not fa.bounded or not fb.bounded or fa.num == 0 or fb.num == 0:
        return None, None, False, 0.0

    # FaceUnion is your helper that merges the geometry of two faces
    fu = FaceUnion(fa, fb)
    
    if fu == False:
        # This usually means they aren't actually adjacent
        return None, None, False, 0.0

    # fu.convex is a boolean calculated by your computeConvex function
    is_convex = fu.convex
    
    # Updated wording: "Let U be the union..."
    question = f"Let U be the union of regions {fa.letter} and {fb.letter}. Is U convex?"
    answerText = "Yes" if is_convex else "No"
    quality = 1.0
    
    return question, answerText, is_convex, quality

#                          QUESTION 18
def Question18(va, vb, codeA, codeB,  map):
    if va==vb:
        return failureOutput
    for f in va.faces:
        if f in vb.faces:
            return failureOutput
    question = LetVerticesBeText([va,vb],['p','q'],[codeA,codeB])
    if question == "":
        return failureOutput
    question += "If you travel in a straight line from p to q, "
    question += "what regions do you pass through in the interior, in sequence? "
    question += "(If you enter and exit a region more than once, list it multiple times.)"
    possFaces, quality = LineCrossesFaces(va.p,vb.p,False,map) 
    if quality < 0:
        return failureOutput
    answers = FacesCrossedInOrder(va.p,vb.p,possFaces)
    return question, Faces2Text(answers), answers, len(answers)*quality


#                          QUESTION 19
def Question19(va, direction, code, map):
    if not Q19Check(va,direction,map):
        return failureOutput
    vName = identifyVertex(va,code)
    if vName == "":
         return failureOutput  
    question = "Let p be " + vName 
    phrase1, phrase2 = Q19DirectionPhrases(direction)
    question += ". Suppose that you travel in a " + phrase1  
    question += " from p until you reach the " + phrase2 + " of the frame. "
    question += "What regions do you pass through in the interior, in sequence? "
    question += "(If you enter and exit a region more than once, list it multiple times.)"
    answers, quality = Q19Compute(va.p,direction,map)
    if quality <= 0:
       return failureOutput
    return question, Faces2Text(answers), answers, len(answers)*quality

def Q19Check(va,direction,map):
    if va.num < 4:
         return False
    if map.faces[0] not in va.faces:
        return True
    (bigX,bigY) = map.bounds
    return ((direction == 0 and va.p.x == 0) or (direction == 1 and va.p.y == 0) or
            (direction == 2 and va.p.x == bigX) or (direction == 3 and va.p.y == bigY))

def Q19DirectionPhrases(direction):
    match direction:
        case 0: 
             return "horizontal line to the right","right side"
        case 1: 
             return "vertical line upward", "top"
        case 2: 
             return "horizontal line to the left", "left side"
        case 3: 
             return "vertical line downward", "bottom"

def Q19Compute(pa,direction,map):
    global epsilon, smallAng
    pb = Q19OtherEnd(pa,direction,map.bounds)
    if direction == 3:
       direction = -1
    direction = direction*np.pi/2
    n = len(map.vertices)
    angleAtA = [100]*n
    coins= []
    for i in range(n):
        v = map.vertices[i]
        if Graph.vecDist(v.p,pa) < epsilon:
            coins += [v]
        else:
           angleAtA[i] = Graph.PointDirection(pa,v.p)-direction
           if angleAtA[i] < -np.pi:
               angleAtA[i] += 2*np.pi
           if angleAtA[i] > np.pi:
               angleAtA[i] -= 2*np.pi
    crossedFaces = []
    quality = 100
    for f in map.faces[1:]:
        extremeLeft = -100
        extremeRight = 100
        nv = len(f.vertices)-1
        for i in range(nv):
            v1 = f.vertices[i]
            j = v1.num
            if (v1 in coins or abs(angleAtA[j]) < angleeps):
                 continue
            d = np.sin(angleAtA[j])
            extremeLeft = max(extremeLeft,d)
            extremeRight = min(extremeRight,d)
            v2 = f.vertices[i+1]
            if v2 not in coins:
                 dLeft, dRight = OnePointDefSide(angleAtA[j],angleAtA[v2.num])          
                 if dLeft:
                     extremeLeft = 1
                 if dRight:
                     extremeRight = -1
        if -smallAng < extremeLeft < smallAng or -smallAng < extremeRight < smallAng:
           return [], -1
        if Q19EdgesCross(pa,pb,angleAtA,f):
            crossedFaces += [f] 
        quality = min(quality,abs(extremeLeft),abs(extremeRight))
    crossedFaces = FacesCrossedInOrder(pa,pb,crossedFaces)
    return crossedFaces, quality

  
def Q19OtherEnd(p,direction,bounds):
    maxX, maxY = bounds
    match direction:
        case 0:
             return Graph.Vector(maxX,p.y)
        case 1:
             return Graph.Vector(p.x,maxY)
        case 2:
             return Graph.Vector(0,p.y)
        case 3:
             return Graph.Vector(p.x,0)


def Q19DefSide(aj,ak):
    left = (aj > np.pi/2 and ak < np.pi/2) or (aj < np.pi/2 and ak > np.pi/2)
    right = right or (aj > -np.pi/2 and ak < -np.pi/2) or (aj < -np.pi/2 and ak > -np.pi/2)
    return left, right

def Q19EdgesCross(pa,pb,angleAtA,f):
    for e in f.edges:
        if ((angleAtA[e.tail.num]*angleAtA[e.head.num]) < 0 and
              CrossLines(pa,pb,e.tail.p,e.head.p)):
            return True
    return False 


def Q19ComputeRobust(pa, direction, map):
    VISUAL_THRESHOLD = 0.03
    pb = Q19OtherEnd(pa, direction, map.bounds)
    
    true_path = TraceSegment(pa, pb, map, min_dist=0.0005)
    robust_path = TraceSegment(pa, pb, map, min_dist=VISUAL_THRESHOLD)
    
    if [f.letter for f in true_path] != [f.letter for f in robust_path]:
        return [], -1
        
    return robust_path, 1.0








#                          QUESTION 20-21

def Question20(va,vb,vc, direction, codeA, codeB, codeC):
    if not distinct([va,vb,vc]):
        return failureOutput
    question = LetVerticesBeText([va,vb,vc],['u','v','w'],[codeA,codeB,codeC])
    if question == "":
        return failureOutput
    question += "Order u, v, and w in order " 
    if direction == 0:
        c = [va.p.x, vb.p.x, vc.p.x]
        question += "left to right."
    else:
        c = [va.p.y, vb.p.y, vc.p.y]  
        question += "bottom to top."
    c, vvs, names = order3(c,[va,vb,vc], ['u','v', 'w'])
    quality = min(c[1]-c[0], c[2]-c[1])
    if quality < 0.05:
       return failureOutput  
    answerText = "[" + names[0] + ", " + names[1] + ", " + names[2] + "]" 
    return question, answerText, vvs, quality

def Question21(va,vb,vc, codeA, codeB, codeC):
    global smallAng
    if not distinct([va,vb,vc]):
        return failureOutput
    question = LetVerticesBeText([va,vb,vc],['u','v','w'],[codeA,codeB,codeC]) 
    question += "Suppose that someone travels from u to v to w back to u."
    question += " Is this cycle clockwise or counterclockwise?"
    angleAtA = Graph.signedAngle(vc.p,va.p,vb.p)
    angleAtB = Graph.signedAngle(va.p,vb.p,vc.p)
    angleAtC = Graph.signedAngle(vb.p,vc.p,va.p)
    if np.pi-max(abs(angleAtA),abs(angleAtB),abs(angleAtC)) < smallAng:
        return failureOutput
    if angleAtB > 0:
       answerText = "clockwise"
       answer = -1
    else:
       answerText = "counterclockwise"
       answer = 1
    angleAtB = abs(angleAtB)
    angleAtC = abs(Graph.signedAngle(vb.p,vc.p,va.p))
    angleAtA = abs(Graph.signedAngle(vc.p,va.p,vb.p))
    quality = np.pi - max(angleAtA, angleAtB, angleAtC)
    if min(quality, angleAtA, angleAtB, angleAtC) < smallAng:
       return failureOutput
    return question, answerText, answer, quality

#                          QUESTION 22

def Question22(va,vb,vc,vd,codeA,codeB,codeC,codeD):
    if not distinct([va,vb,vc,vd]):
        return failureOutput
    question = LetVerticesBeText([va,vb,vc,vd],['p','q','u','v'],             
                                   [codeA,codeB,codeC,codeD])
    if question == "":
        return failureOutput
    question += "Does the line segment between p and q cross "
    question += "the line segment between u and v?"
    crosses, quality = CrossLines(va.p,vb.p,vc.p,vd.p)
    if (quality == 0):
        return failureOutput
    if crosses:
        return question, "Yes", True, quality
    return question, "No", False, quality

def CrossLines(pa,pb,pc,pd):
    nab = Graph.UnitNormal(pa,pb)
    ncd = Graph.UnitNormal(pc,pd)
    dota = Q22DotProd(pa,pc,ncd)
    dotb = Q22DotProd(pb,pc,ncd)
    dotc = Q22DotProd(pc,pa,nab)
    dotd = Q22DotProd(pd,pa,nab)    
    if (dota*dotb < 0) and (dotc*dotd) < 0:
       answer = True
       quality = min(abs(dota),abs(dotb),abs(dotc),abs(dotd))
    else: 
        answer = False
        if (dota*dotb < 0):
           quality = min(abs(dotc),abs(dotd))
        elif (dotc*dotd < 0):
           quality = min(abs(dota),abs(dotb))
        else:
           quality = max(min(abs(dotc),abs(dotd)),min(abs(dota),abs(dotb)))
    if quality < 0.02:
        quality = 0
    return answer,quality

   

def Q22DotProd(p1,p2,n):
    return ((p1.x-p2.x)*n.x) + ((p1.y-p2.y)*n.y)



#                          QUESTION 23
def Question23(dir,map):
    if dir == 0:
       d1, d2 = "leftmost", "rightmost"
    else:
       d1, d2 ="bottom", "top"
    question = "List all pairs of regions <X.Y> such that the " + d1
    question += " vertex of X is the same as the " + d2 + " vertex of Y."
    facePairs = Q23Compute(map,dir)
    answerText = FacePairCollection2Text(facePairs)
    return question, answerText, facePairs, 1+len(facePairs)

def Q23Compute(map,dir):
    extremeVertices = []
    for v in map.vertices:
        extremeVertices += [[set(),set()]]
    for face in map.faces[1:]:
        va,vb = ExtremeVerticesOfFace(face,dir)
        extremeVertices[va.num][0].add(face)
        extremeVertices[vb.num][1].add(face)        
    facePairs = []
    for pair in extremeVertices:
        facePairs += list(product(pair[0],pair[1]))
    return facePairs

def ExtremeVerticesOfFace(face,dir):
    big = -100
    small = 100
    for v in face.vertices[1:]:
        if dir == 0:
            val = v.p.x
        else:
            val = v.p.y
        if val > big:
            big = val
            bigV = v
        if val < small:
            small = val
            smallV = v
    return smallV,bigV

#                          QUESTION 24

def Question24(fa,fb,fc):
    if SharesVertex(fa,[fb,fc]):
        return failureOutput
    if not distinct([fa,fb,fc]):
        return failureOutput
    question = "Which region is closer to "  + fa.letter + ": " 
    question += fb.letter + " or " + fc.letter + "? " 
    question += "(Consider the distance between two regions to be the distance between their closest points.)"
    dab = Graph.distBetweenFaces(fa,fb)
    dac = Graph.distBetweenFaces(fa,fc)
    if dab < dac:
        answer,close,far = fb,dab,dac
    else:
        answer,close,far = fc,dac,dab
    if far <= 1.3*close:
        return failureOutput
    elif far > 2*close:
        quality = 2
    else:
        quality = far/close
    return question, answer.letter, answer, quality

#                          QUESTION 25
# ==========================================
def Question25(face, map_bounds):
    """
    Checks if a region shares at least one full SEGMENT (edge) with the frame.
    This logic prevents a 'Yes' answer if the region only touches the frame at a corner point.
    """
    if not face or not hasattr(face, 'edges'):
        return None, None, False, 0.0
        
    maxX, maxY = map_bounds
    tol = 0.001 
    touches_frame_edge = False
    
    # Iterate through all boundary edges of the specific face
    for edge in face.edges:
        # Get the coordinates of the two endpoints of the current edge
        v1, v2 = edge.v1.p, edge.v2.p 
        
        # An edge is on the frame boundary if both endpoints are on the same boundary line
        on_left   = (abs(v1.x - 0) < tol and abs(v2.x - 0) < tol)
        on_right  = (abs(v1.x - maxX) < tol and abs(v2.x - maxX) < tol)
        on_bottom = (abs(v1.y - 0) < tol and abs(v2.y - 0) < tol)
        on_top    = (abs(v1.y - maxY) < tol and abs(v2.y - maxY) < tol)
        
        if on_left or on_right or on_top or on_bottom:
            touches_frame_edge = True
            break # Exit early once a qualifying edge is found

    question = f"Does region {face.letter} have any exterior edges that touch the frame?"
    answer_text = "Yes" if touches_frame_edge else "No"
    
    # Quality: Standard binary classification task
    quality = 1.0 
    
    # Return: (Question text, Answer text, Boolean result, Quality score)
    return question, answer_text, touches_frame_edge, quality


#                          QUESTION 25
# ==========================================
def Question25(face, map_bounds):
    """
    Checks if a region shares a SEGMENT (edge) with the frame.
    Returns: (str, str, bool, float)
    """
    if not face or not hasattr(face, 'vertices'):
        return None, None, False, 0.0
        
    maxX, maxY = map_bounds
    tol = 0.001 
    
    on_left = on_right = on_top = on_bottom = 0
    
    # Use [:-1] to avoid counting the overlapping start/end vertex twice
    for v in face.vertices[:-1]:
        px, py = v.p.x, v.p.y
        if abs(px - 0) < tol: on_left += 1
        if abs(px - maxX) < tol: on_right += 1
        if abs(py - 0) < tol: on_bottom += 1
        if abs(py - maxY) < tol: on_top += 1

    # If 2 distinct vertices lie on the same boundary, 
    # the edge between them must lie on that boundary.
    touches_edge = (on_left >= 2 or on_right >= 2 or 
                    on_top >= 2 or on_bottom >= 2)
            
    question = f"Does region {face.letter} have any exterior edges that touch the frame?"
    answerText = "Yes" if touches_edge else "No"
    quality = 1.0 
    
    return question, answerText, touches_edge, quality

#                          QUESTION 26
def Question26(map):
    """Counts the total number of labeled, bounded regions."""
    regions = [f for f in map.faces if f.bounded]
    num_regions = len(regions)
    
    question = "How many regions are there in the diagram in total? Provide only the total number."
    answerText = str(num_regions)
    
    # Quality: Higher complexity (more faces) yields higher quality
    quality = num_regions / 5.0 
    return question, answerText, num_regions, quality

# ==========================================
#                          QUESTION 27
# ==========================================
def Question27(res_map):
    """
    Identifies the region with the largest area.
    Ensures the difference between the largest and second largest 
    is visually distinguishable.
    """
    # Filter for internal, bounded regions only (skipping Face 0/@)
    regions = [f for f in res_map.faces if f.bounded and f.num > 0]
    
    if not regions:
        # Return 4 values to maintain consistent unpacking in the pilot script
        return None, None, None, 0.0
        
    # Sort regions by area in descending order
    sorted_regions = sorted(regions, key=lambda f: f.area, reverse=True)
    
    # DATA QUALITY CHECK:
    # If the largest area is not at least 1.5x larger than the second largest,
    # it is too difficult for a human (or AI) to distinguish visually.
    # We return None to signal that this map is "bad" for this specific question.
    if len(sorted_regions) > 1 and sorted_regions[0].area < sorted_regions[1].area * 1.5:
        return None, None, None, 0.0

    max_face = sorted_regions[0]
    
    # Construct the Q&A pair
    question = "Which internal region has the largest area in the diagram?"
    answer_text = max_face.letter
    
    # Return: (Question, Answer, Metadata/Object, Quality Score)
    return question, answer_text, max_face, 1.0


#                          QUESTION 28
# ==========================================
#                          QUESTION 28
# ==========================================
def Question28(fa, fb):
    """
    Determines if fa is clearly above or below fb by comparing vertical bounds.
    Uses a 0.05 buffer to ensure the spatial relationship is visually obvious.
    """
    # Validation: ensure regions are different, internal, and bounded
    if fa == fb or not fa.bounded or not fb.bounded or fa.num == 0 or fb.num == 0:
        return None, None, None, 0.0
    
    # BoundingBox (fa.box) index map: [0]:minX, [1]:maxX, [2]:minY, [3]:maxY
    # In Cartesian: higher Y is "above"
    a_min_y, a_max_y = fa.box[2], fa.box[3]
    b_min_y, b_max_y = fb.box[2], fb.box[3]

    # Case 1: Region A's bottom is higher than Region B's top
    if a_min_y > b_max_y + 0.05: 
        answerText = "above"
        gap = a_min_y - b_max_y
    # Case 2: Region A's top is lower than Region B's bottom
    elif a_max_y < b_min_y - 0.05:
        answerText = "below"
        gap = b_min_y - a_max_y
    else:
        # Vertical overlap exists; the relationship isn't "strictly" above/below
        return None, None, None, 0.0

    question = f"Is region {fa.letter} above or below region {fb.letter}?"
    
    # Saliency Quality: The larger the clear vertical gap, the higher the quality
    quality = 1.0 + gap
    
    return question, answerText, answerText, quality


#                          QUESTION 29 (Debug Version)

# def Question29(fe, fb, map, samples=200):
#     if fe == fb or not fe.bounded or not fb.bounded:
#         return failureOutput

#     max_count = 0
#     best_path = []
#     best_pts = (None, None)

#     for _ in range(samples):
#         # 1. Random Sample two points
#         pa = Graph.randomPointInFace(fe, True)
#         pb = Graph.randomPointInFace(fb, True)

#         # 2. Find all edges that cross pa-pb
#         crossed_faces = set()
#         for edge in map.edges:
#             # Use crossline to see if it intersects 
#             if Graph.crossLines(pa, pb, edge.tail.p, edge.head.p):
#                 # If it there is an intersection, then two faces at the edges are intersected
#                 if edge.leftFace and edge.leftFace.bounded:
#                     crossed_faces.add(edge.leftFace)
#                 if edge.reverse.leftFace and edge.reverse.leftFace.bounded:
#                     crossed_faces.add(edge.reverse.leftFace)

#         # 3. Get rid of starting and ending point, only finding the middle regions
#         intermediates = {f for f in crossed_faces if f != fe and f != fb}
        
#         if len(intermediates) > max_count:
#             max_count = len(intermediates)
#             best_path = sorted([f.letter for f in intermediates])
#             best_pts = (pa, pb)
    
#     question = f"Consider all possible straight line segments connecting a point in the interior of region {fe.letter} "
#     question += f"to a point in the interior of region {fb.letter}. "
#     question += "What is the maximum number of distinct regions (excluding the two regions themselves) "
#     question += "that such a line segment can pass through?"


#     print(f"Corrected Path: {best_path}, Count: {max_count}")
#     return question, str(max_count), max_count, 1.0

def Question29(fe, fb, map, samples=400):
    """
    Question 25-29 Style: Find max intermediate regions.
    Rejects the question if the result depends on 'scraping' (dist < 0.05).
    """
    if fe == fb or not fe.bounded or not fb.bounded:
        return failureOutput

    max_robust_count = 0
    # The 'Human-Visible' Threshold
    VISUAL_THRESHOLD = 0.03
    # The 'Absolute Truth' Threshold
    EPSILON_THRESHOLD = 0.0005 

    for _ in range(samples):
        pa = Graph.randomPointInFace(fe, True)
        pb = Graph.randomPointInFace(fb, True)

        # 1. Calculate the 'Perfect' Ground Truth
        true_path = TraceSegment(pa, pb, map, min_dist=EPSILON_THRESHOLD)
        true_set = {f.letter for f in true_path if f != fe and f != fb}
        true_count = len(true_set)

        # 2. Calculate the 'Visually Clear' Path
        robust_path = TraceSegment(pa, pb, map, min_dist=VISUAL_THRESHOLD)
        robust_set = {f.letter for f in robust_path if f != fe and f != fb}
        robust_count = len(robust_set)

        # HARD REJECTION: If the 'Truth' and 'Visuals' differ, 
        # this specific two regions are too ambiguous/scraped. Skip it.
        if true_count != robust_count:
            return failureOutput

        # If they match, it's a high-quality, clear path.
        if robust_count > max_robust_count:
            max_robust_count = robust_count

    # If no visually clear path exists at all, reject the whole question for this map
    if max_robust_count == 0:
        return None

    # Final Question Formulation
    question = (f"Consider all possible straight line segments connecting a point in the interior of region {fe.letter} "
                f"to a point in the interior of region {fb.letter}. "
                f"What is the maximum number of distinct regions (excluding {fe.letter} and {fb.letter}) "
                f"that such a line segment can pass through?")

    # Return: question, answer, numeric answer, quality score
    return question, str(max_robust_count), max_robust_count, 1.0 + (max_robust_count * 0.5)


def TraceSegment(pa, pb, map, min_dist=0.05):
    """
    Traces the sequence of regions passed by the segment from pa to pb.
    Only includes regions where the segment travels a distance > min_dist.
    """
    intersections = []
    # Always include the start and end of the segment
    intersections.append({'p': pa, 't': 0.0})
    intersections.append({'p': pb, 't': 1.0})
    
    for edge in map.edges:
        if Graph.crossLines(pa, pb, edge.tail.p, edge.head.p):
            p_cross = Graph.lineIntersect(pa, pb, edge.tail.p, edge.head.p)
            
            # Parametric position 't' (0 to 1) along the segment to sort them
            if abs(pb.x - pa.x) > 0.00001:
                t = (p_cross.x - pa.x) / (pb.x - pa.x)
            else:
                t = (p_cross.y - pa.y) / (pb.y - pa.y)
            
            # Only count intersections strictly between the endpoints
            if 0.0001 < t < 0.9999:
                intersections.append({'p': p_cross, 't': t})

    # Sort intersections from pa to pb
    intersections.sort(key=lambda x: x['t'])
    
    # Clean up duplicate points (e.g., hitting a vertex)
    unique_pts = [intersections[0]['p']]
    for i in range(1, len(intersections)):
        if Graph.pointDist(intersections[i]['p'], unique_pts[-1]) > 0.0001:
            unique_pts.append(intersections[i]['p'])

    path_sequence = []
    for i in range(len(unique_pts) - 1):
        p1 = unique_pts[i]
        p2 = unique_pts[i+1]
        
        # Determine if this segment is long enough to be "visible"
        segment_len = Graph.pointDist(p1, p2)
        if segment_len < min_dist:
            continue
            
        # Use midpoint to identify which face this segment is inside
        mid = Graph.midpoint(p1, p2)
        for face in map.faces:
            if face.bounded and Graph.pointInsideFace(mid, face):
                path_sequence.append(face)
                break 
                
    return path_sequence










#                       SHARED SUBROUTINES

def LetVerticesBeText(vertices,names,codes):
    text =""
    for i in range(len(vertices)):
        vName = identifyVertex(vertices[i],codes[i])
        if vName == "":
            return ""
        text += "Let " + names[i] + " be " + vName  + ". "
    return text


def identifyVertex(v,code):
    possIDs = vertexIdentifiers(v)
    if len(possIDs) == 0:
        return ""
    return decode(possIDs,code)

def vertexIdentifiers(v):
    possIDs = faceMeetingID(v)
    for face in v.faces:
        if face.bounded:
            possIDs += faceExtremeVertexID(v,face,True)
    if v.num < 4:
       possIDs += [frameCornerVertexID(v.num)]
    return possIDs

def identifyVertexForQ11(v,face,code):
    possIDs = vertexFaceMeetForQ11(v,face) + faceExtremeVertexID(v,face,False)
    if v.num < 4:
       possIDs += [frameCornerVertexID(v.num)]
    if len(possIDs) == 0:
        return ""
    return decode(possIDs,code)

def faceMeetingID(v):
     ffl = v.faces
     fa = ffl[0]
     ff = set(ffl)
     text = "the meeting point of regions " + Faces2TextForVertexID(ffl)
     for va in fa.vertices[1:]:
         if va !=v and ff.issubset(set(va.faces)) :
              return []
     return [text]

  

def vertexFaceMeetForQ11(v,face):
     ff = set(v.faces)
     ffb = v.faces.copy()
     ffb.remove(face)
     for va in face.vertices[1:]:
         if va !=v and ff.issubset(set(va.faces)) :
              return []
     return ["the meeting point of " + Faces2TextForVertexID([face]+ffb)]



def faceExtremeVertexID(v,face,angleOption):
    if v not in face.trueVertices:
        return []
    alternatives = face.trueVertices[1:]
    alternatives.remove(v)
    distinct = 0.1
    left, right = horizontallyDistinct(v,alternatives)
    bottom, top = verticallyDistinct(v,alternatives)
    if angleOption:
        acute,obtuse = angleDistinct(v,face)
    else: 
        acute,obtuse = False,False
    if left:
        texts = ["the leftmost vertex of " + face.letter] 
    elif right:
       texts = ["the rightmost vertex of " + face.letter] 
    else:
       texts = []
    if bottom:
        texts += ["the bottommost vertex of " + face.letter] 
    elif top:
       texts += ["the topmost vertex of " + face.letter]     
    if acute:
        texts += ["the vertex of " + face.letter + " with the sharpest angle"]
    elif obtuse:
        texts += ["the vertex of " + face.letter + " with the widest angle"]      
    if texts == []:    
        return CornerText(v,face,alternatives)
    else:
        return texts

def horizontallyDistinct(v,alternatives):
    global smallDist
    left = True
    right = True
    for a in alternatives:
        if a.p.x < v.p.x + smallDist:
            left = False        
        if a.p.x > v.p.x - smallDist:
            right = False    
    return left,right

def verticallyDistinct(v,alternatives):
    bottom = True
    top = True
    for a in alternatives:
        if a.p.y < v.p.y + smallDist:
            bottom = False        
        if a.p.y > v.p.y - smallDist:
            top = False
    return bottom,top

def angleDistinct(v,face):
    if not face.bounded or not face.convex or v not in face.trueVertices:
        return False, False
    vang = Graph.angleAtFace(v,face)
    sharp = True
    obtuse = True 
    for va in face.trueVertices:
        if va == v:
            continue
        ang = Graph.angleAtFace(va,face)
        if ang < vang + np.pi/9:
            sharp = False
        if ang > vang - np.pi/9:
            obtuse = False
    return sharp, obtuse            


def frameCornerVertexID(n):
    str = "the vertex at the "
    match n:
       case 0:
          str += "bottom left "
       case 1: 
          str += "bottom right "
       case 2:
          str += "top right "
       case 3:
          str += "top left "
    return str + "of the overall diagram"

def CornerText(v,face,alternatives):
    bottomLeft=True
    bottomRight=True
    topLeft=True
    topRight=True
    for a in alternatives:
        if (a.p.x-v.p.x < -epsilon):
           bottomLeft, topLeft = False,False
        elif (v.p.x-a.p.x < -epsilon):
           bottomRight, topRight = False,False
        if (a.p.y-v.p.y < -epsilon):
           bottomLeft, bottomRight = False,False
        elif (v.p.y-a.p.y < -epsilon):
           topLeft, topRight = False,False
        if (a.p.x-v.p.x < smallDist and a.p.y-v.p.y < smallDist):
            bottomLeft=False
        if (v.p.x-a.p.x < smallDist and a.p.y-v.p.y < smallDist):
            bottomRight=False
        if (a.p.x-v.p.x < smallDist and v.p.y-a.p.y < smallDist):
            topLeft=False
        if (v.p.x-a.p.x < smallDist and v.p.y-a.p.y < smallDist):
            topRight=False
    if bottomLeft:
        return ["the bottom left vertex of " + face.letter]
    if bottomRight:
        return ["the bottom right vertex of " + face.letter]
    if topLeft:
        return ["the top left vertex of " + face.letter]
    if bottomRight:
        return ["the top right vertex of " + face.letter]
    return []

def identifyEdgeTexts(va,vb):
    texts = []
    for fa in va.faces:
        if va in fa.trueVertices and vb in fa.trueVertices:
            for i in range(len(fa.trueVertices)-1):
                if va == fa.trueVertices[i]:
                    if vb == fa.trueVertices[i+1]:
                        texts = texts + identifyEdgeFace(va,vb,fa)
                    elif vb == fa.trueVertices[i-1]:           
                        texts = texts + identifyEdgeFace(vb,va,fa)
    return texts
              
def identifyEdgeFace(va,vb,fa):
     return idEdgeByBounds(va,vb,fa) + idExtremeEdge(va,vb,fa)

def idEdgeByBounds(va,vb,fa):
    oppFaces = SingleEdgeOppFaces(va,vb,fa)
    if oppFaces == []:
        return []
    if not oppFaces[0].bounded:
        oppText = "the outside of the frame"
    elif len(oppFaces) == 1:
        oppText = "region " + oppFaces[0].letter
    elif len(oppFaces) == 2:
             oppText = "regions " + oppFaces[0].letter + " and " + oppFaces[1].letter
    else: 
        oppText = "regions "
        for i in range(len(oppFaces)-1):
            oppText += oppFaces[i].letter + ", "
        oppText += "and " + oppFaces[-1].letter
    text = "the edge of " + fa.letter + " that meets " + oppText 
    return [text]

def SingleEdgeOppFaces(va,vb,f):
    oppFaces = []
    indexA = f.vertices.index(va)
    indexB = f.vertices.index(vb)
    ee = f.edges
    n = len(ee)
    if indexA < indexB:
        edgesIn = f.edges[indexA:indexB]
        edgesOut = f.edges[indexB:n] + f.edges[0:indexA]
    else:
        edgesIn = f.edges[indexA:n] + f.edges[0:indexB]
        edgesOut = f.edges[indexB:indexA]
    for e in edgesIn:
        oppFace = e.reverse.leftFace
        if oppFace not in oppFaces:
            oppFaces += [oppFace]
    for e in edgesOut:
        if e.reverse.leftFace in oppFaces:
            return []
    return oppFaces

def idExtremeEdge(va,vb,fa):
    global smallDist
    tilt = np.pi/6
    dir = Graph.PointDirection(va.p,vb.p)
    if (dir < tilt) or (np.pi - tilt < dir < np.pi+tilt) or (2*np.pi -tilt < dir):
        return idHorizontalEdge(va,vb,fa)
    elif (np.pi/2 - tilt < dir < np.pi/2+tilt) or (3*np.pi/2 - tilt < dir < 3*np.pi/2+tilt):
        return idVerticalEdge(va,vb,fa)
    else:
        return []

def idVerticalEdge(va,vb,fa):
    global smallDist
    minX = True
    maxX = True
    leftAB = max(va.p.x,vb.p.x) + smallDist
    rightAB = min(va.p.x,vb.p.x) - smallDist
    for v in fa.vertices:
        if v != va and v != vb:
            if v.p.x < leftAB:
                minX = False
            if v.p.x > rightAB:
                maxX = False
    if minX:
        return ["the leftmost edge of " + fa.letter]
    elif maxX:
        return ["the rightmost edge of " + fa.letter]
    else:
        return []
    

def idHorizontalEdge(va,vb,fa):
    global smallDist
    minY = True
    maxY = True
    botAB = max(va.p.y,vb.p.y) + smallDist
    topAB = min(va.p.y,vb.p.y) -smallDist
    for v in fa.vertices:
        if v != va and v != vb:
            if v.p.y < botAB:
                minY = False
            if v.p.y > topAB:
                maxY = False
    if minY:
        return ["the bottom edge of " + fa.letter]
    elif maxY:
        return ["the top edge of " + fa.letter]
    else:
        return []


  
#def CountTrueEdges(face):
#    prevEdge = face.edges[-1]
#    count = 0
#    for e in face.edges:
#        if e.trueEdge != prevEdge.trueEdge:
#            count += 1
#        prevEdge = e
#    return count

def Faces2TextForVertexID(faces):    
    outside = False
    properFaces = []
    for i in range(len(faces)):
        if faces[i].bounded:
            properFaces += [faces[i]]
        else:
            outside = True
    text = properFaces[0].letter
    if len(properFaces) == 2:
        text += " and " +  properFaces[1].letter
    elif len(properFaces) > 2:
        for i in range(1,len(properFaces)-1):
            text += ", " + properFaces[i].letter
        text += ", and " + properFaces[-1].letter
    if outside:
        text += " with the outside of the frame"
    return text
    

     
def Faces2Text(faces):
    if len(faces) == 0:
        return "None"
    if type(faces) is set:
        faceText = "{"
    else:
        faceText = "["
    first = True
    for face in faces:
         if first:
             first = False
         else:
           faceText += ", "
         faceText += face.letter
    if type(faces) is set:
        return faceText+"}" 
    else:
        return faceText + "]"

def FacePairCollection2Text(fps):
    if len(fps) == 0:
        return "None"
    first = True
    if type(fps) is set:
        text = "{"
    else:
        text = "["   
    for fp in fps:
         fa,fb = fp
         if first:
            first = False
         else:    
             text += ", "             
         text +=  FacePair2Text(fa,fb)
    if type(fps) is set:
        text += "}"
    else:
        text += "]" 
    return text 
 


def FacePair2Text(fa,fb):
    return "(" + fa.letter + ", " + fb.letter + ")" 

def disjointLists(la,lb):
    disjoint = True
    for x in la:
        if x in lb:
            return False
    return True

# As far as I can tell, Pythons library routines for doing this generally are absurdly awkward
def order3(m,a,b):   
    if m[0] < m[1]:
        if m[1] < m[2]:
            i,j,k = 0,1,2
        elif m[0] < m[2]:
            i,j,k = 0,2,1 
        else: 
            i,j,k = 2,0,1  
    else:   
        if m[0] < m[2]:
            i,j,k = 1,0,2
        elif m[1] < m[2]:
            i,j,k = 1,2,0
        else: 
            i,j,k = 2,1,0           
    return [m[i],m[j],m[k]], [a[i],a[j],a[k]], [b[i],b[j],b[k]]    

def parallelSort(values,ll):
    for i in range(1,len(values)):
        j = i
        while j > 0 and values[j] < values[j-1]:
           values[j-1],values[j] = values[j],values[j-1]
           ll[j-1],ll[j] = ll[j],ll[j-1]
           j -= 1

    return values, ll

def decode(l,code):
    return l[code%len(l)]
          

def FaceUnion(f1,f2):  #Only for pairs of regions that meet in consecutive edges
    [found,start,stop] = consecCommonEdges(f1,f2)
    if not found:
        return False
    va,vb = start.tail, stop.head
    vv1, ee1 = VerticesBetween(vb,va,f1)
    vv2, ee2 = VerticesBetween(va,vb,f2)
    pf = PseudoFace(vv1+vv2+[vv1[0]],ee1+ee2)
    pf.area = f1.area + f2.area
    return pf


def consecCommonEdges(f1,f2):
    n = len(f1.edges)
    stop = -1
    start = -1
    if f1.edges[0].reverse in f2.edges:        
        for i in range(1,n):
            if f1.edges[i].reverse in f2.edges:
                if start != -1:
                    return [False,False,False]
                if stop != -1:
                    start = i
            else:
               if stop == -1:    
                   stop = i-1
        if start == -1:
            start = 0
    else:
        for i in range(1,n):
            if f1.edges[i].reverse in f2.edges:           
                if stop != -1:
                    return [False,False,False]
                if start == -1:
                    start = i
            else:
                if start != -1 and stop == -1:
                    stop = i-1
        if stop == -1:
            stop = n-1
    if start != -1 and stop != -1:
        return True, f1.edges[start], f1.edges[stop]
    else:
        return False, False, False

def VerticesBetween(va,vb,f):
    n = len(f.edges)
    b = f.vertices.index(va)
    t = f.vertices.index(vb)
    if b < t:
        return f.vertices[b:t], f.edges[b:t]
    else:
        return f.vertices[b:n]+f.vertices[0:t], f.edges[b:n]+f.edges[0:t]

def UnionText(fa,fb,uname):
    return "Let " + uname + " be the union of regions " + fa.letter + " and " + fb.letter + ". " 

def ShowPseudoFace(f):
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


def FacesCrossedInOrder(pa,pb,faces):
    currentFace = False
    fine = int(100*(abs(pb.x-pa.x) + abs(pb.y-pa.y)))
    crossedFaces =  []
    for i in range(fine+1):
        t = i/fine
        px = (1-t)*pa.x + t*pb.x
        py = (1-t)*pa.y + t*pb.y
        if (currentFace != False and
               Graph.pointInsideFace(Graph.Vector(px,py),currentFace)):
            continue
        for face in faces:
            if (face != currentFace and 
                 Graph.pointInsideFace(Graph.Vector(px,py),face)):
                currentFace = face
                crossedFaces += [face]
    return crossedFaces
     
def LineCrossesFacesRobust(pa, pb, visibleSeg, map):
    """
    Runs LineCrossesFaces twice with different thresholds.
    Returns (faces, quality) if consistent, else ([], -1).
    """
    VISUAL_THRESHOLD = 0.03   # Human-clear
    MATH_THRESHOLD = 0.0005    # Mathematical truth
    
    # 1. Get Mathematical Ground Truth
    true_faces, t_qual = LineCrossesFaces(pa, pb, visibleSeg, map, threshold=MATH_THRESHOLD)
    
    # 2. Get Visual Ground Truth
    robust_faces, r_qual = LineCrossesFaces(pa, pb, visibleSeg, map, threshold=VISUAL_THRESHOLD)
    
    # 3. Compare the sets of faces (using letters/labels)
    true_set = [f.letter for f in true_faces]
    robust_set = [f.letter for f in robust_faces]
    
    # REJECT if they are not identical
    if true_set != robust_set or t_qual < 0 or r_qual < 0:
        return [], -1
        
    return robust_faces, r_qual

def TwoPointDefSide(aj,ak,bj,bk,visibleSeg):
    left = visibleSeg and ((aj > np.pi/2 and bj > -np.pi/2) or (aj < np.pi/2 and bj < -np.pi/2))
    left = left or (aj > np.pi/2 and ak < np.pi/2) or (aj < np.pi/2 and ak > np.pi/2)
    left = left or (bj > -np.pi/2 and bk < -np.pi/2) or (bj < -np.pi/2 and bk > -np.pi/2)
    right = visibleSeg and ((aj > -np.pi/2 and bj > np.pi/2) or (aj < -np.pi/2 and bj < np.pi/2))
    right = right or (bj > np.pi/2 and bk < np.pi/2) or (bj < np.pi/2 and bk > np.pi/2)
    right = right or (aj > -np.pi/2 and ak < -np.pi/2) or (aj < -np.pi/2 and ak > -np.pi/2)
#    if (left or right):
#        print(left, right, aj, ak, bj, bk)
    return left, right

def OnePointDefSide(aj,bj):
    left =  (aj > np.pi/2 and bj > -np.pi/2) or (aj < np.pi/2 and bj < -np.pi/2)
    right = (aj > -np.pi/2 and bj > np.pi/2) or (aj < -np.pi/2 and bj < np.pi/2)
    return left, right


def LineCrossesFacesOld(pa,pb,map):
    global smallDist, epsilon
    n = Graph.UnitNormal(pa,pb)
    dotProds = []
    for v in map.vertices:
        dotProds  += [Q22DotProd(v.p,pa,n)]
    interiorFaces = []
    worstQuality = 100
    for f in map.faces:
        if f.bounded:
            bigPos = -epsilon
            bigNeg = -epsilon
            smallPos = 100
            smallNeg = 100
            coin = 0
            for v in f.vertices[1:]:
                d = dotProds[v.num]
                if d > epsilon:
                    bigPos = max(bigPos,d)
                    smallPos = min(smallPos,d)
                if -d > epsilon:
                    bigNeg = max(bigNeg,-d)
                    smallNeg = min(smallNeg,-d)
                if abs(dotProds[v.num]) < epsilon:
                    coin += 1
            quality, crosses = qualityCross(pa,pb,f,bigPos,smallPos,bigNeg,smallNeg,coin)
#            print(f,bigPos,smallPos,bigNeg,smallNeg,coin,quality,crosses)           
            if quality < 0:            
                return [], -1
            if crosses:
                interiorFaces += [f]            
            worstQuality = min(worstQuality,quality)
    return interiorFaces, worstQuality*(len(interiorFaces)+1) 

def distinct(l):
   for i in range(len(l)-1):
       for j in range(i+1,len(l)):
           if l[i]==l[j]:
               return False
   return True

def qualityCross(pa,pb,f,bigPos,smallPos,bigNeg,smallNeg,coin):
    global smallDist
    offset = smallDist
    if coin > 0:
        offset = 0.01
    if bigPos > offset and bigNeg > offset:
       return min(bigPos,bigNeg), True
    if coin >= 2:
       return 100, False
    if smallNeg == 100:
        quality = smallPos
        if obviouslyOneSide(f,pa,pb):
            return 0.5, False
    elif smallPos == 100:
        quality = smallNeg
        if obviouslyOneSide(f,pa,pb):
            return 0.5, False
    else: 
        quality = -1
    if quality < offset:
        quality = -1
    return quality, False

# f has already been determined to be on one side of the line pa-pb, but it lies fairly close
# to the lineThe question is, is it visually obvious that it is on one side of the line?
def obviouslyOneSide(f,pa,pb):
    for v in f.vertices[1:]:
        if obviouslyVertexOneSide(v.p,pa,pb):
            return True
    for e in f.edges:
        if (obviouslyVertexOneSide(pa,e.tail.p,e.head.p) or
            obviouslyVertexOneSide(pb,e.tail.p,e.head.p)):
             return True
    return False


def obviouslyVertexOneSide(px,pa,pb):
    vp = Graph.vecProject(px,pa,pb)
    return Graph.lineBetween(vp,pa,pb) and Graph.vecDist(px,vp) < 0.2


def SharesVertex(f,faces):
    for v in f.vertices[1:]:
        for ff in faces:
            if ff in v.faces:
                return True
    return False


