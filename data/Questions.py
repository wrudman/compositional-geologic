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
smallAng=0.15
failureOutput = ("", "", False, 0)


#Definiton for convexity, passing thorough interior etc
# convex_def = (
#     "A region is convex if, for any two points inside the region, the straight line between them stays entirely inside the region (e.g., a square or a circle).\n"
#     "A region is not convex if it has a "dent" or "cave-in." In this case, you can pick two points inside the region such that the straight line between them is not entirely contained within the region.\n"
# )
# union_def = (
#     "A region union is the region formed by two or more adjacent regions. The union is treated as a single region. The shared boundary between the original regions is ignored and is not part of the outer boundary of the resulting region.\n"
# )
# int_angle_def = (
#     "An interior angle is the angle inside a region at a corner (vertex), formed by the two edges meeting at that vertex.\n"
# )

union_def  = ""
int_angle_def = ""
border_edge_def = (
    "Bordering along an edge is not the same as bordering along a vertex.\n"
)
pass_interior_def = (
    "Do not include a region if the line only coincides with its boundary without entering its interior.\n" 
)
multiple_times_def = (
    "If the line enters and exits a region more than once, list it multiple times.\n"
)
outside_def = (
    "Treat the area outside the frame as a region labeled “Outside”.\n"
)
none_answer_def = (
    "Enter \"None\" if there are none.\n"
)



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
    question = "Which regions share an edge with region " + face.letter + "?\n\n"
    question += "A region that touches region " + face.letter + " only at a vertex does not count.\n"
    question += none_answer_def
    answerSet = set()
    for e in face.edges:
        fb = e.reverse.leftFace        
        if fb.bounded:
            answerSet.add(fb)
    answerText = Faces2Text(answerSet)         
    return question, answerText, answerSet, len(answerSet)

#                          QUESTION 2

def Question2(fa, fb):
    """Comparative reasoning: Do two regions have the same number of edges?"""
    if fa == fb or not fa.bounded or not fb.bounded:
        return failureOutput
    
    # Reuse your existing numSides attribute
    count_a = fa.numSides
    count_b = fb.numSides
    
    question = f"Do region {fa.letter} and region {fb.letter} have the same number of edges?\n"
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

# #                          QUESTION 3            

# def Question3(map):
#     question = "Which if any of the regions are not convex?\n" + convex_def 
#     answerSet = set()
#     for face in map.faces:            
#         if face.bounded and not face.convex:
#             answerSet.add(face)
#     answerText = Faces2Text(answerSet)         
#     return question, answerText, answerSet, 1+len(answerSet)
    


#                          QUESTION 4

def Question4(face,v,cyclicDirection,vIdentCode):
    if v not in face.vertices:
        return failureOutput
    vName = identifyVertexForQ11(v,face,vIdentCode)
    if vName == "":
         return failureOutput  
    questionText = "Let v₁ be " + vName + ". "
    questionText += "Starting at v₁, trace the boundary of region " + face.letter + " "
    questionText += cyclicPhrase(cyclicDirection) + " until you return to v₁. "
    questionText += "List, in order, the regions on the other side of " + face.letter + "’s boundary.\n\n"
    questionText += outside_def
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
    question = "Which pairs of regions share a vertex but do not share an edge?\n\n"
    question += none_answer_def
    answerSet = set()
    for v in map.vertices:  
        ff = v.faces
        for i in range(len(ff)-1):
            if ff[i].bounded:
                fi = ff[i]
                eer = Graph.reverseEdges(ff[i].edges)
                for j in range(i+1, len(ff)):
                    fj = ff[j]
                    if fj.bounded and disjointLists(eer,fj.edges) and (fi,fj) not in answerSet and (fj,fi) not in answerSet:
                        answerSet.add((fi,fj))
    if len(answerSet) == 0:
        answerText = "None"
    elif len(answerSet) > 6:
        return failureOutput
    else:
        answerText = FacePairCollection2Text(answerSet)
    return question, answerText, answerSet, 1+len(answerSet)


# #                          QUESTIONS 6 & 7
# def Question6(map):
#     global answerSet
#     question = "Which pairs of regions, if any, share two or more disconnected edges? " 
#     question += "Do not include the outside of the frame.\n"
#     answerSet = set()
#     for f in map.faces[1:]:
#         Question6A(f,False)
#     if len(answerSet)==0:
#         return failureOutput
#     return question, FacePairCollection2Text(answerSet), answerSet, 1+len(answerSet)

def Question7(map):
    global answerSet
    question = "Which regions meet the outside of the frame " 
    question += "along two or more disconnected edges?\n\n"
    question += none_answer_def
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
    question = "Which regions have " + str(k) + " edges?\n\n" 
    question += none_answer_def
    answerSet = set()
    for f in map.faces:
        if f.bounded and f.numSides == k:
            answerSet.add(f)
    return question, Faces2Text(answerSet), answerSet, 1+len(answerSet)

def Question9(f):
    question = "How many edges does region " + f.letter + " have?"
    k = f.numSides
    return question, str(k), k, 1+k


#                          QUESTION 10

def Question10(vp,vu,vv,vw,codeP,codeU,codeV,codeW):
    if not distinct([vp,vu,vv,vw]):
        return failureOutput
    distA = Graph.pointDist(vp.p,vu.p)
    distB = Graph.pointDist(vp.p,vv.p)
    distC = Graph.pointDist(vp.p,vw.p)
    dists, text, vertexPairs = order3([distA,distB,distC], ["v₂","v₃","v₄"], 
                                      [vu,vv,vw])
    q = Question10Quality(dists)
    if q==0:
        return failureOutput  
    question = LetVerticesBeText([vp,vu,vv,vw],['v₁','v₂','v₃','v₄'],[codeP,codeU,codeV,codeW]) 
    if question == "":
        return failureOutput                
    question = question + "\nOrder v₂, v₃, and v₄ from closest to farthest from v₁."
    answerText = "[" + text[0] + ", " + text[1] + ", " + text[2] + "]" 
    return question, answerText, vertexPairs, q


      
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
    if n != 4:
        return failureOutput
    angles = []
    for v in vvs:
        angles += [Graph.angleAtFace(v,fa)]
    angles, indices = parallelSort(angles,list(range(len(vvs))))
    quality = Q11Quality(angles,n)
    if quality == 0:
        return failureOutput  
    subscript_digits = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
    angle_labels = ["a" + str(i + 1).translate(subscript_digits) for i in range(n)]
    question = "Region " + fa.letter + " has " + str(n) + " interior angles, labeled as follows: "
    for i in range(n):
        vName = identifyVertexForQ11(vvs[i],fa,codes[i])
        if vName == "":
            return failureOutput
        question += ("(" + str(i + 1) + ") " + angle_labels[i] +
                     " is the angle at " + vName)
        if i == n - 1:
            question += ". "
        elif i == n - 2:
            question += "; and "
        else:
            question += "; "
    question += ("Order angles " + ", ".join(angle_labels[:-1]) +
                 ", and " + angle_labels[-1] +
                 " from smallest to largest." + int_angle_def)
    answerList = [vvs[index] for index in indices]
    answerText = "[" + ", ".join(angle_labels[index] for index in indices) + "]"
    return question, answerText, answerList, quality
   
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


def Question12(va, vb, code, map):
    """
    Question 12: Extend an edge 'e1' into an infinite line L1 and list 
    the regions it passes through in sequence.
    Uses the 'Midpoint Sampling' logic for high robustness.
    """
    # 1. Validation: Do not extend edges that are part of the map boundary frame
    if BoundaryEdge(va.p, vb.p, map.bounds):
        return failureOutput
    
    # 2. Identify the edge using an e-number label plus a human-readable description.
    texts = identifyEdgeTexts(va, vb)
    print(f"DEBUG: Original Edge Points: ({va.p.x}, {va.p.y}) to ({vb.p.x}, {vb.p.y})")
    print(f"DEBUG: Edge Label Found: {texts}")
    if not texts:
        return failureOutput
    edge_label = "e₁"
    line_label = "L1"
        
    # 3. Calculate intersections with the frame to simulate an "infinite" line
    pa_ext, pb_ext = GetFrameIntersections(va.p, vb.p, map.bounds)
    print(f"DEBUG: Extended Line Endpoints: {pa_ext}, {pb_ext}")

    # Thresholds for the Robustness Check
    EPSILON_THRESHOLD = 0.0005
    VISUAL_THRESHOLD = 0.06

    # 4. Get the "Absolute Truth" path (mathematical sequence)
    true_path = TraceSegment(pa_ext, pb_ext, map, min_dist=EPSILON_THRESHOLD)
    
    # 5. Get the "Visually Robust" path (what is clearly seen)
    robust_path = TraceSegment(pa_ext, pb_ext, map, min_dist=VISUAL_THRESHOLD)

    # 6. REJECTION LOGIC (Hard Rejection)
    true_letters = [f.letter for f in true_path]
    robust_letters = [f.letter for f in robust_path]

    if not true_letters or true_letters != robust_letters:
        return failureOutput

    # The line has no intrinsic direction, so Q12 uses an unordered set rather
    # than a path sequence for both its machine-readable and text answers.
    unique_faces = set(true_path)
    unique_letters = sorted(f.letter for f in unique_faces)

    # 6. Formulate the final question text
    question = (f"Let {edge_label} be {decode(texts, code)}. "
                f"Extend {edge_label} in both directions to form straight line {line_label}. "
                f"Which distinct regions’ interiors does {line_label} pass through?\n\n")
    question += pass_interior_def
    question += none_answer_def

    # Format the answer as a set {A, B, C}
    answer_text = "{" + ", ".join(unique_letters) + "}"
    
    # Quality based on unique regions
    quality = 1.0 + (len(unique_letters) * 0.5)
    
    return question, answer_text, unique_faces, quality

def GetFrameIntersections(p1, p2, bounds):
    """
    Extends the segment p1-p2 to the boundaries of the box defined by bounds.
    Returns two points on the frame.
    """
    maxX, maxY = bounds
    dx = p2.x - p1.x
    dy = p2.y - p1.y
    
    t_values = []
    
    if abs(dx) > 1e-9:
        t_values.append(-p1.x / dx)
        t_values.append((maxX - p1.x) / dx)
    
    if abs(dy) > 1e-9:
        t_values.append(-p1.y / dy)
        t_values.append((maxY - p1.y) / dy)
        
    valid_pts = []
    for t in t_values:
        px = p1.x + t * dx
        py = p1.y + t * dy
        if -1e-5 <= px <= maxX + 1e-5 and -1e-5 <= py <= maxY + 1e-5:
            valid_pts.append(Graph.Vector(px, py))
            
    if len(valid_pts) < 2:
        return p1, p2  # Fallback
        
    p_start = valid_pts[0]
    p_end = max(valid_pts, key=lambda p: Graph.vecDist(p_start, p))
    
    return p_start, p_end

def BoundaryEdge(pa, pb, bounds):
    """
    Checks if the segment formed by points pa and pb lies entirely on the 
    frame boundary (the edges of the diagram).
    """
    bigX, bigY = bounds
    eps = 0.001

    on_left = (abs(pa.x) < eps and abs(pb.x) < eps)
    on_right = (abs(pa.x - bigX) < eps and abs(pb.x - bigX) < eps)
    on_bottom = (abs(pa.y) < eps and abs(pb.y) < eps)
    on_top = (abs(pa.y - bigY) < eps and abs(pb.y - bigY) < eps)

    if pa == pb or on_left or on_right or on_bottom or on_top:
        return True
        
    return False
                          




#                          QUESTION 13-15

def Question13(v, code):
    possIDs = []
    for f in v.faces:
        if not f.bounded:
            return failureOutput
        possIDs += faceExtremeVertexID(v, f, True)

    if not possIDs:
        return failureOutput

    id = decode(possIDs, code)
    question = "Let v₁ be " + id + ". Which regions meet at v₁?"

    answerNames = sorted([f.letter for f in v.faces if f.bounded])
    answerText = "{" + ", ".join(answerNames) + "}"

    return question, answerText, answerNames, len(answerNames)
    

def Question14(fa,fb):
    fu = FaceUnion(fa,fb)
    if fu==False:
        return failureOutput
    question = UnionText(fa,fb,'U')
    question += "How many edges does U have? \n"
    question += union_def
    return question, str(fu.numSides), fu.numSides, fu.numSides + len(fu.edges) 

def Question15(fa,fb,map):
    if fa==fb or not fa.bounded or not fb.bounded:
        return failureOutput
    fu = FaceUnion(fa,fb)
    if fu==False:
        return failureOutput
    question = UnionText(fa,fb,'U')
    question += "Which regions share an edge with U?\n\n"
    question += "A region that touches U only at a vertex does not count.\n"
    question += union_def
    question += none_answer_def
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
    # This question uses one union only, so the union can be named
    # consistently with every other union question.
    if sum(type(f) is list for f in faces) != 1:
        return failureOutput
    newFaces = []
    question = ""
    for f in faces:
        if type(f) is list:
            [fa,fb] = f
            f = FaceUnion(fa,fb)
            if f==False:
                return failureOutput
            f.letter = 'U'
            question += UnionText(fa,fb,f.letter)
        newFaces += [f]
    letters = [f.letter for f in newFaces]
    if len(letters) == 1:
        region_text = letters[0]
    elif len(letters) == 2:
        region_text = letters[0] + " and " + letters[1]
    else:
        region_text = ", ".join(letters[:-1]) + ", and " + letters[-1]
    question += "Order regions " + region_text + " from smallest to largest by area.\n"
    question += union_def
    areas = []
    for f in newFaces:
        areas += [f.area]
    areas, newFaces = parallelSort(areas,newFaces)
    for i in range(len(areas)-1):
        if areas[i+1] < areas[i]*1.5:
            return failureOutput 
    return question, Faces2Text(newFaces), newFaces, len(newFaces)


# # ==========================================
# #                          QUESTION 17
# # ==========================================
# def Question17(fa, fb):
#     """
#     Checks if the union of two adjacent regions is convex.
#     Returns: (question, answerText, is_convex, quality)
#     """
#     if fa == fb or not fa.bounded or not fb.bounded or fa.num == 0 or fb.num == 0:
#         return None, None, False, 0.0

#     # FaceUnion is your helper that merges the geometry of two faces
#     fu = FaceUnion(fa, fb)
    
#     if fu == False:
#         # This usually means they aren't actually adjacent
#         return None, None, False, 0.0

#     # fu.convex is a boolean calculated by your computeConvex function
#     is_convex = fu.convex
    
#     # Updated wording: "Let U be the union..."
#     question = f"Let U be the union of regions {fa.letter} and {fb.letter}. Is U convex? \n"
#     question += union_def
#     question += convex_def
#     answerText = "Yes" if is_convex else "No"
#     quality = 1.0
    
#     return question, answerText, is_convex, quality


def Question18(va, vb, codeA, codeB, map):
    """
    Question 18: Travel in a straight line from point v₁ to point v₂.
    Lists the regions passed through in sequence, including duplicates.
    """
    # 1. Validation: Ensure points are distinct and not sharing a face
    if va == vb:
        return failureOutput
    for f in va.faces:
        if f in vb.faces:
            return failureOutput

    # 2. Generate vertex identification text
    question_init = LetVerticesBeText([va, vb], ['v₁', 'v₂'], [codeA, codeB])
    if question_init == "":
        return failureOutput

    # 3. Use TraceSegment to find the sequence of regions
    EPSILON_THRESHOLD = 0.0005 
    VISUAL_THRESHOLD = 0.06    

    true_path = TraceSegment(va.p, vb.p, map, min_dist=EPSILON_THRESHOLD)
    robust_path = TraceSegment(va.p, vb.p, map, min_dist=VISUAL_THRESHOLD)

    # 4. REJECTION LOGIC
    true_letters = [f.letter for f in true_path]
    robust_letters = [f.letter for f in robust_path]

    if not true_letters or true_letters != robust_letters:
        return failureOutput

    # 5. Formulate Question Text
    question = question_init
    question += "Consider the straight line segment from v₁ to v₂. List, in order, "
    question += "the regions whose interiors the segment passes through.\n\n"
    question += (
        "If the segment only touches or runs along a region’s boundary without entering "
        "its interior, do not include that region. If it enters the same region more than "
        "once, list that region each time.\n"
    )

    # 6. Format Answer
    answer_text = "[" + ", ".join(true_letters) + "]"
    
    quality_score = len(true_letters) * 1.0
    
    return question, answer_text, true_path, quality_score

#                          QUESTION 19
def Question19(va, direction, code, map):
    """
    Question 19: Travel from vertex v₁ in a specified cardinal direction 
    (Up, Down, Left, Right) until hitting the frame.
    """
    # 1. Basic Check: Ensure the movement is valid
    if not Q19Check(va, direction, map):
        return failureOutput
        
    vName = identifyVertex(va, code)
    if vName == "":
        return failureOutput  

    # 2. Find the target point on the frame based on direction
    pa = va.p
    pb = Q19OtherEnd(pa, direction, map.bounds)

    # 3. Use TraceSegment with Dual-Threshold Robustness Check
    EPSILON_THRESHOLD = 0.0005 
    VISUAL_THRESHOLD = 0.06    

    true_path = TraceSegment(pa, pb, map, min_dist=EPSILON_THRESHOLD)
    robust_path = TraceSegment(pa, pb, map, min_dist=VISUAL_THRESHOLD)

    # 4. REJECTION LOGIC
    true_letters = [f.letter for f in true_path]
    robust_letters = [f.letter for f in robust_path]

    if not true_letters or true_letters != robust_letters:
        return failureOutput

    # 5. Formulate Question Text
    phrase1, phrase2 = Q19DirectionPhrases(direction)
    question = (f"Let v₁ be {vName}. Starting at v₁, travel {phrase1} "
                f"until you reach {phrase2} of the frame. "
                f"List the regions whose interiors you pass through, in the order encountered.\n\n")
    question += pass_interior_def
    question += multiple_times_def

    # 6. Format Answer
    answer_text = "[" + ", ".join(true_letters) + "]"
    
    quality_score = len(true_letters) * 1.0
    
    return question, answer_text, true_path, quality_score

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
             return "horizontally to the right", "the right edge"
        case 1: 
             return "vertically upward", "the top edge"
        case 2: 
             return "horizontally to the left", "the left edge"
        case 3: 
             return "vertically downward", "the bottom edge"

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




#                          QUESTION 20-21

def Question20(va,vb,vc, direction, codeA, codeB, codeC):
    if not distinct([va,vb,vc]):
        return failureOutput
    question = LetVerticesBeText([va,vb,vc],['v₁','v₂','v₃'],[codeA,codeB,codeC])
    if question == "":
        return failureOutput
    question += "\nOrder v₁, v₂, and v₃ from "
    if direction == 0:
        c = [va.p.x, vb.p.x, vc.p.x]
        question += "left to right."
    else:
        c = [va.p.y, vb.p.y, vc.p.y]  
        question += "bottom to top."
    c, vvs, names = order3(c,[va,vb,vc], ['v₁','v₂','v₃'])
    quality = min(c[1]-c[0], c[2]-c[1])
    if quality < 0.05:
       return failureOutput  
    answerText = "[" + names[0] + ", " + names[1] + ", " + names[2] + "]" 
    return question, answerText, vvs, quality

def Question21(va,vb,vc, codeA, codeB, codeC):
    global smallAng
    if not distinct([va,vb,vc]):
        return failureOutput
    # Orientation questions should require at least one vertex from inside the
    # diagram. Three frame vertices reduce the task to reading the outer box
    # and do not exercise the compositional vertex-finding workflow.
    if all(frameEdgeForVertex(v) is not None for v in (va, vb, vc)):
        return failureOutput
    question = LetVerticesBeText([va,vb,vc],['v₁','v₂','v₃'],[codeA,codeB,codeC]) 
    if question == "":
        return failureOutput
    question += "Following the cycle v₁ → v₂ → v₃ → v₁, is the direction clockwise or counterclockwise?"
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
    question = LetVerticesBeText([va,vb,vc,vd],['v₁','v₂','v₃','v₄'],             
                                   [codeA,codeB,codeC,codeD])
    if question == "":
        return failureOutput
    question += "\nDoes the line segment between v₁ and v₂ cross "
    question += "the line segment between v₃ and v₄?"
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
       d1, d2 = "bottommost", "topmost"
    question = "Which pairs of regions share a vertex that is the " + d1
    question += " vertex of one region and the " + d2 + " vertex of the other?\n\n"
    question += none_answer_def
    facePairs = Q23Compute(map,dir)
    answerText = FacePairCollection2Text(facePairs)
    if len(facePairs) > 6:
        return failureOutput
    return question, answerText, facePairs, 1+len(facePairs)

def Q23Compute(map,dir):
    # Vertex.num is not guaranteed to remain contiguous after topology edits,
    # so key the buckets by the actual vertex objects rather than list indices.
    extremeVertices = {v: [set(), set()] for v in map.vertices}
    for face in map.faces[1:]:
        va,vb = ExtremeVerticesOfFace(face,dir)
        if va is not None:
            extremeVertices.setdefault(va, [set(), set()])[0].add(face)
        if vb is not None:
            extremeVertices.setdefault(vb, [set(), set()])[1].add(face)
    facePairs = set()
    for pair in extremeVertices.values():
        valid_combinations = {p for p in product(pair[0], pair[1]) if p[0] != p[1]}
        facePairs.update(valid_combinations)
    return facePairs

def ExtremeVerticesOfFace(face,dir):
    """Return mathematically unique min/max vertices, or None for a tie.

    A phrase such as "the leftmost vertex" is valid whenever exactly one
    vertex has the minimum coordinate. Only coordinates equal within the
    numerical geometry tolerance are treated as a non-unique extreme.
    """
    vertices = face.vertices[:-1]  # omit the repeated closing vertex
    if len(vertices) < 2:
        return None, None
    coordinate = (lambda v: v.p.x) if dir == 0 else (lambda v: v.p.y)
    ordered = sorted(vertices, key=coordinate)
    min_vertex = (ordered[0]
                  if coordinate(ordered[1]) - coordinate(ordered[0]) > epsilon
                  else None)
    max_vertex = (ordered[-1]
                  if coordinate(ordered[-1]) - coordinate(ordered[-2]) > epsilon
                  else None)
    return min_vertex, max_vertex

#                          QUESTION 24

def Question24(fa,fb,fc):
    if SharesVertex(fa,[fb,fc]):
        return failureOutput
    if not distinct([fa,fb,fc]):
        return failureOutput
    question = "Which region is closer to "  + fa.letter + ": " 
    question += fb.letter + " or " + fc.letter + "? " 
    question += "\n\nThe distance between two regions is defined as the distance between their closest points.\n"
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
    Checks if a region shares a SEGMENT (edge) with the frame.
    Returns: (str, str, bool, float)
    """
    if not face or not hasattr(face, 'vertices'):
        return None, None, False, 0.0
        
    maxX, maxY = map_bounds
    tol = 0.001 
    
    def endpoints_on_same_frame_side(va, vb):
        ax, ay = va.p.x, va.p.y
        bx, by = vb.p.x, vb.p.y
        return (abs(ax) < tol and abs(bx) < tol or
                abs(ax - maxX) < tol and abs(bx - maxX) < tol or
                abs(ay) < tol and abs(by) < tol or
                abs(ay - maxY) < tol and abs(by - maxY) < tol)

    touches_edge = any(
        endpoints_on_same_frame_side(face.vertices[i], face.vertices[i + 1])
        for i in range(len(face.vertices) - 1)
    )
            
    question = (f"Does any edge of region {face.letter} lie on the frame?\n\n"
                "Touching the frame only at a vertex does not count.")
    answerText = "Yes" if touches_edge else "No"
    quality = 1.0 
    
    return question, answerText, touches_edge, quality

#                          QUESTION 26
def Question26(map):
    """Counts the total number of labeled, bounded regions."""
    regions = [f for f in map.faces if f.bounded]
    num_regions = len(regions)
    
    question = "How many labeled regions are there in the diagram?"
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
        return None, None, None, 0.0
        
    # Sort regions by area in descending order
    sorted_regions = sorted(regions, key=lambda f: f.area, reverse=True)
    
    if len(sorted_regions) > 1 and sorted_regions[0].area < sorted_regions[1].area * 1.5:
        return None, None, None, 0.0

    max_face = sorted_regions[0]
    
    question = "Which region has the largest area?"
    answer_text = max_face.letter
    
    return question, answer_text, max_face, 1.0


#                          QUESTION 28
# ==========================================
def Question28(fa, fb):
    """
    Determines if fa is clearly above or below fb by comparing vertical bounds.
    Uses a 0.05 buffer to ensure the spatial relationship is visually obvious.
    """
    if fa == fb or not fa.bounded or not fb.bounded or fa.num == 0 or fb.num == 0:
        return None, None, None, 0.0
    
    # BoundingBox (fa.box) index map: [0]:minX, [1]:maxX, [2]:minY, [3]:maxY
    a_min_y, a_max_y = fa.box[2], fa.box[3]
    b_min_y, b_max_y = fb.box[2], fb.box[3]

    if a_min_y > b_max_y + 0.05: 
        answerText = "above"
        gap = a_min_y - b_max_y
    elif a_max_y < b_min_y - 0.05:
        answerText = "below"
        gap = b_min_y - a_max_y
    else:
        return None, None, None, 0.0

    question = f"Is region {fa.letter} entirely above or entirely below region {fb.letter}?"
    quality = 1.0 + gap
    
    return question, answerText, answerText, quality

def Question29(fe, fb, map, samples=400):
    """
    Question 25-29 Style: Find max intermediate regions.
    Rejects the question if the result depends on 'scraping' (dist < 0.05).
    """
    if fe == fb or not fe.bounded or not fb.bounded:
        return failureOutput

    max_robust_count = 0
    VISUAL_THRESHOLD = 0.15
    EPSILON_THRESHOLD = 0.0005 

    # Graph.randomPointInFace uses NumPy's global RNG. Isolate Q29's sampling
    # so that the same question is reproducible and does not change the random
    # state used by the rest of the question generator.
    random_state = np.random.get_state()
    np.random.seed(29029)
    try:
        for _ in range(samples):
            pa = Graph.randomPointInFace(fe, True)
            pb = Graph.randomPointInFace(fb, True)

            true_path = TraceSegment(pa, pb, map, min_dist=EPSILON_THRESHOLD)
            true_set = {f.letter for f in true_path if f != fe and f != fb}
            true_count = len(true_set)

            robust_path = TraceSegment(pa, pb, map, min_dist=VISUAL_THRESHOLD)
            robust_set = {f.letter for f in robust_path if f != fe and f != fb}
            robust_count = len(robust_set)

            if true_count != robust_count:
                return failureOutput

            if robust_count > max_robust_count:
                max_robust_count = robust_count
    finally:
        np.random.set_state(random_state)

    if max_robust_count == 0:
        return failureOutput

    question = (f"Consider all possible straight line segments connecting a point in the interior of region {fe.letter} "
                f"to a point in the interior of region {fb.letter}. "
                f"What is the maximum number of distinct regions, excluding regions {fe.letter} and {fb.letter}, "
                f"that such a line segment can pass through?\n\n")
    question += pass_interior_def

    return question, str(max_robust_count), max_robust_count, 1.0 + (max_robust_count * 0.5)


import numpy as np

def TraceSegment(pa, pb, map, min_dist=0.05):
    """
    Traces the sequence of regions from pa to pb.
    Filters out regions if the segment only lies on the boundary.
    """
    intersections = []
    intersections.append({'p': pa, 't': 0.0})
    intersections.append({'p': pb, 't': 1.0})
    
    # 1. Find all intersections with map edges
    for edge in map.edges:
        # Parallel lines have no unique intersection point. Collinear overlap
        # is handled later by the two-sided midpoint interior test, so it must
        # not be passed to lineIntersect (whose denominator would be zero).
        if Graph.parallel(pa, pb, edge.tail.p, edge.head.p):
            continue
        if Graph.crossLines(pa, pb, edge.tail.p, edge.head.p):
            p_cross = Graph.lineIntersect(pa, pb, edge.tail.p, edge.head.p)
            
            if abs(pb.x - pa.x) > 1e-5:
                t = (p_cross.x - pa.x) / (pb.x - pa.x)
            else:
                t = (p_cross.y - pa.y) / (pb.y - pa.y)
            
            if 0.0001 < t < 0.9999:
                intersections.append({'p': p_cross, 't': t})

    # 2. Sort points chronologically
    intersections.sort(key=lambda x: x['t'])
    
    # 3. Remove duplicate points (vertex hits)
    unique_pts = [intersections[0]['p']]
    for i in range(1, len(intersections)):
        if Graph.pointDist(intersections[i]['p'], unique_pts[-1]) > 0.0001:
            unique_pts.append(intersections[i]['p'])

    path_sequence = []
    
    # 4. Calculate the perpendicular vector for offset checking
    dx = pb.x - pa.x
    dy = pb.y - pa.y
    length = np.sqrt(dx**2 + dy**2)
    
    offset_dist = 0.002 
    if length > 1e-7:
        perp_x = (-dy / length) * offset_dist
        perp_y = (dx / length) * offset_dist
    else:
        perp_x, perp_y = 0, 0

    for i in range(len(unique_pts) - 1):
        p1 = unique_pts[i]
        p2 = unique_pts[i+1]
        
        if Graph.pointDist(p1, p2) < min_dist:
            continue
            
        mid = Graph.midpoint(p1, p2)
        
        p_left = Graph.Vector(mid.x + perp_x, mid.y + perp_y)
        p_right = Graph.Vector(mid.x - perp_x, mid.y - perp_y)

        for face in map.faces:
            if not face.bounded:
                continue
            
            if Graph.pointInsideFace(p_left, face) and Graph.pointInsideFace(p_right, face):
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
    if v.num < 4:
       return [frameCornerVertexID(v.num)]
    possIDs = []
    for face in v.faces:
        if face.bounded:
            possIDs += faceExtremeVertexID(v,face,True)
    return possIDs if possIDs else faceMeetingID(v)

def identifyVertexForQ11(v,face,code):
    if v.num < 4:
       return frameCornerVertexID(v.num)
    possIDs = faceExtremeVertexID(v,face,False)
    if not possIDs:
       possIDs = vertexFaceMeetForQ11(v,face)
    if len(possIDs) == 0:
        return ""
    return decode(possIDs,code)

def boundedMeetingFaces(v):
     """Return every bounded region incident to v, including collinear boundary splits."""
     return [face for face in v.faces if face.bounded]


def frameEdgeForVertex(v):
     """Return the frame side containing v, or None for an interior vertex."""
     outside = next((face for face in v.faces if not face.bounded), None)
     if outside is None:
          return None
     frame_vertices = outside.vertices
     min_x = min(va.p.x for va in frame_vertices)
     max_x = max(va.p.x for va in frame_vertices)
     min_y = min(va.p.y for va in frame_vertices)
     max_y = max(va.p.y for va in frame_vertices)
     if abs(v.p.x - min_x) < epsilon:
          return "left"
     if abs(v.p.x - max_x) < epsilon:
          return "right"
     if abs(v.p.y - min_y) < epsilon:
          return "bottom"
     if abs(v.p.y - max_y) < epsilon:
          return "top"
     return None


def meetingVertexText(v, faces):
     side = frameEdgeForVertex(v)
     regions = Faces2TextForVertexID(faces)
     if side is not None:
          return ("the vertex on the " + side +
                  " edge of the frame where regions " + regions + " meet")
     return ("the vertex not on the frame where regions " + regions +
             " meet and no other labeled region meets")


def faceMeetingID(v):
     ffl = boundedMeetingFaces(v)
     if len(ffl) < 2:
          return []
     fa = ffl[0]
     ff = set(ffl)
     text = meetingVertexText(v, ffl)
     # Use all boundary vertices, not only geometric corners. Otherwise a
     # collinear split point can make the same description ambiguous.
     for va in fa.vertices:
         if (va != v and ff == set(boundedMeetingFaces(va)) and
             frameEdgeForVertex(va) == frameEdgeForVertex(v)):
              return []
     return [text]

  

def vertexFaceMeetForQ11(v,face):
     if not face.bounded or v not in face.trueVertices:
          return []
     ffb = [f for f in boundedMeetingFaces(v) if f != face]
     if len(ffb) == 0:
          return []
     ff = set([face] + ffb)
     for va in face.vertices:
         if (va != v and ff == set(boundedMeetingFaces(va)) and
             frameEdgeForVertex(va) == frameEdgeForVertex(v)):
              return []
     return [meetingVertexText(v, [face] + ffb)]



def faceExtremeVertexID(v, face, angleOption):
    """
    Identifies if a vertex v is a geometric extreme (left/right/top/bottom/angle)
    within a specific face.
    """
    if v not in face.trueVertices:
        return []

    alternatives = [alt for alt in face.trueVertices if alt != v]
    
    if not alternatives:
        return []

    left, right = horizontallyDistinct(v, alternatives)
    bottom, top = verticallyDistinct(v, alternatives)
    
    acute, obtuse = False, False
    if angleOption:
        acute, obtuse = angleDistinct(v, face)

    texts = []

    if left:
        texts.append("the leftmost vertex of " + face.letter)
    elif right:
        texts.append("the rightmost vertex of " + face.letter)

    if bottom:
        texts.append("the bottommost vertex of " + face.letter)
    elif top:
        texts.append("the topmost vertex of " + face.letter)

    if acute:
        texts.append("the vertex of " + face.letter + " with the sharpest angle")
    elif obtuse:
        texts.append("the vertex of " + face.letter + " with the widest angle")

    if not texts:    
        return CornerText(v, face, alternatives)
    
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
    if topRight:
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

def identifyEdgeLabel(va, vb, map):
    """
    Returns a stable e-number for the undirected edge between va and vb.
    Reverse half-edges share the same label.
    """
    edge_keys = []
    for edge in map.edges:
        key = tuple(sorted([edge.tail.num, edge.head.num]))
        if key not in edge_keys:
            edge_keys.append(key)

    target_key = tuple(sorted([va.num, vb.num]))
    if target_key in edge_keys:
        return "e" + str(edge_keys.index(target_key) + 1)
    return "e1"

def identifyEdgeFace(va, vb, fa):
    # Combined description logic
    return idEdgeByBounds(va, vb, fa)

def idEdgeByBounds(va, vb, fa):
    """
    Identifies the edge of face 'fa' by checking what lies on the opposite side.
    Includes a strict check to ensure boundary descriptions are coordinate-accurate.
    """
    oppFaces = SingleEdgeOppFaces(va, vb, fa)
    if not oppFaces:
        return []
    
    maxX, maxY = 1.0, 1.0 
    
    on_left   = abs(va.p.x) < 1e-5 and abs(vb.p.x) < 1e-5
    on_right  = abs(va.p.x - maxX) < 1e-5 and abs(vb.p.x - maxX) < 1e-5
    on_bottom = abs(va.p.y) < 1e-5 and abs(vb.p.y) < 1e-5
    on_top    = abs(va.p.y - maxY) < 1e-5 and abs(vb.p.y - maxY) < 1e-5
    
    is_on_frame = on_left or on_right or on_bottom or on_top

    if not oppFaces[0].bounded:
        if is_on_frame:
            oppText = "the outside of the frame"
        else:
            return [] 
            
    elif len(oppFaces) == 1:
        oppText = f"region {oppFaces[0].letter}"
        
    else:
        letters = [f.letter for f in oppFaces]
        oppText = "regions " + ", ".join(letters[:-1]) + ", and " + letters[-1]
    
    return [f"the edge of {fa.letter} that meets {oppText}"]

def SingleEdgeOppFaces(va, vb, f):
    """
    Finds faces on the opposite side of the segment defined by va and vb.
    """
    oppFaces = []
    
    try:
        indexA = f.vertices.index(va)
        indexB = f.vertices.index(vb)
    except ValueError:
        return []

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
            oppFaces.append(oppFace)
            
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
    is_set = isinstance(faces, set)
    ordered_faces = sorted(faces, key=lambda face: face.letter) if is_set else faces
    if is_set:
        faceText = "{"
    else:
        faceText = "["
    first = True
    for face in ordered_faces:
         if first:
             first = False
         else:
           faceText += ", "
         faceText += face.letter
    if is_set:
        return faceText+"}" 
    else:
        return faceText + "]"

def FacePairCollection2Text(fps):
    if len(fps) == 0:
        return "None"
    first = True
    is_set = isinstance(fps, set)
    ordered_pairs = (
        sorted(
            fps,
            key=lambda pair: tuple(sorted((pair[0].letter, pair[1].letter))),
        )
        if is_set else fps
    )
    if is_set:
        text = "{"
    else:
        text = "["   
    for fp in ordered_pairs:
         fa,fb = fp
         if first:
            first = False
         else:    
             text += ", "             
         text +=  FacePair2Text(fa,fb)
    if is_set:
        text += "}"
    else:
        text += "]" 
    return text 
 


def FacePair2Text(fa,fb):
    first, second = sorted((fa.letter, fb.letter))
    return "(" + first + ", " + second + ")" 

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
     
def LineCrossesFaces(pa, pb, visibleSeg, map, min_dist=0.0005):
    """
    Checks which faces the line segment pa-pb crosses.
    min_dist: The minimum length the segment must travel inside a face 
              to be counted.
    """
    global epsilon, smallAng, angleeps
    
    dist_ab = Graph.vecDist(pa, pb)
    if dist_ab < epsilon: 
        return [], -1
    
    angles_a = {}
    angles_b = {}
    coincident_vertices = set()
    
    for v in map.vertices:
        if Graph.vecDist(v.p, pa) < epsilon or Graph.vecDist(v.p, pb) < epsilon:
            coincident_vertices.add(v)
        else:
            angles_a[v.num] = Graph.signedAngle(pb, pa, v.p)
            angles_b[v.num] = Graph.signedAngle(pa, pb, v.p)

    crossed_faces = []
    min_quality = 100
    
    for face in map.faces[1:]:
        extreme_left = -100
        extreme_right = 100
        valid_face = False

        for i in range(len(face.vertices) - 1):
            v1 = face.vertices[i]
            v2 = face.vertices[i+1]
            
            ang_a1 = angles_a.get(v1.num, 100)
            ang_b1 = angles_b.get(v1.num, 100)
            
            if v1 in coincident_vertices or abs(ang_a1) < angleeps:
                 continue
            
            d_val = max(ang_a1, -ang_b1) if ang_a1 > 0 else min(ang_a1, -ang_b1)
            extreme_left = max(extreme_left, np.sin(d_val))
            extreme_right = min(extreme_right, np.sin(d_val))
            
            if v2 in coincident_vertices:
                is_left, is_right = OnePointDefSide(ang_a1, ang_b1)
            else:
                ang_a2 = angles_a.get(v2.num, 100)
                ang_b2 = angles_b.get(v2.num, 100)
                is_left, is_right = TwoPointDefSide(ang_a1, ang_a2, ang_b1, ang_b2, visibleSeg)          
            
            if is_left:
                extreme_left = max(extreme_left, smallAng * 1.1)
            if is_right:
                extreme_right = min(extreme_right, -smallAng * 1.1)
            
            valid_face = True

        if not valid_face:
            continue

        if -smallAng < extreme_left < smallAng or -smallAng < extreme_right < smallAng:
           return [], -1
        
        if extreme_left > smallAng and extreme_right < -smallAng:
            actual_path_len = CalculateIntersectionLength(pa, pb, face)
            
            if actual_path_len > min_dist:
                crossed_faces.append(face) 
                min_quality = min(min_quality, abs(extreme_left), abs(extreme_right))
            
    return crossed_faces, min_quality

def CalculateIntersectionLength(pa, pb, face):
    """ Helper to find the total length of segment pa-pb inside a given face """
    pts = [pa, pb]
    for edge in face.edges:
        if Graph.crossLines(pa, pb, edge.tail.p, edge.head.p):
            p_cross = Graph.lineIntersect(pa, pb, edge.tail.p, edge.head.p)
            pts.append(p_cross)
    
    if abs(pb.x - pa.x) > 0.0001:
        pts.sort(key=lambda p: p.x if pb.x > pa.x else -p.x)
    else:
        pts.sort(key=lambda p: p.y if pb.y > pa.y else -p.y)
        
    total_len = 0
    for i in range(len(pts) - 1):
        mid = Graph.midpoint(pts[i], pts[i+1])
        if Graph.pointInsideFace(mid, face):
            total_len += Graph.vecDist(pts[i], pts[i+1])
    return total_len

def TwoPointDefSide(aj, ak, bj, bk, visibleSeg):
    # Logic for determining which side of the line a segment lies on
    left = visibleSeg and ((aj > np.pi/2 and bj > -np.pi/2) or (aj < np.pi/2 and bj < -np.pi/2))
    left = left or (aj > np.pi/2 and ak < np.pi/2) or (aj < np.pi/2 and ak > np.pi/2)
    left = left or (bj > -np.pi/2 and bk < -np.pi/2) or (bj < -np.pi/2 and bk > -np.pi/2)
    
    right = visibleSeg and ((aj > -np.pi/2 and bj > np.pi/2) or (aj < -np.pi/2 and bj < np.pi/2))
    right = right or (bj > np.pi/2 and bk < np.pi/2) or (bj < np.pi/2 and bk > np.pi/2)
    right = right or (aj > -np.pi/2 and ak < -np.pi/2) or (aj < -np.pi/2 and ak > -np.pi/2)
    return left, right

def OnePointDefSide(aj, bj):
    left =  (aj > np.pi/2 and bj > -np.pi/2) or (aj < np.pi/2 and bj < -np.pi/2)
    right = (aj > -np.pi/2 and bj > np.pi/2) or (aj < -np.pi/2 and bj < np.pi/2)
    return left, right

def TwoPointDefSide(aj,ak,bj,bk,visibleSeg):
    left = visibleSeg and ((aj > np.pi/2 and bj > -np.pi/2) or (aj < np.pi/2 and bj < -np.pi/2))
    left = left or (aj > np.pi/2 and ak < np.pi/2) or (aj < np.pi/2 and ak > np.pi/2)
    left = left or (bj > -np.pi/2 and bk < -np.pi/2) or (bj < -np.pi/2 and bk > -np.pi/2)
    right = visibleSeg and ((aj > -np.pi/2 and bj > np.pi/2) or (aj < -np.pi/2 and bj < np.pi/2))
    right = right or (bj > np.pi/2 and bk < np.pi/2) or (bj < np.pi/2 and bk > np.pi/2)
    right = right or (aj > -np.pi/2 and ak < -np.pi/2) or (aj < -np.pi/2 and ak > -np.pi/2)
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
