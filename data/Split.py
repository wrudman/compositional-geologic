import numpy
import Graph
import Frame
import GraphCheck
import DrawGraph
import FinalizeFaces
import random
import sys

global debug 
debug = False

# --- GLOBAL TRACKING & CONSTANTS ---
face_attempts = {}  
MIN_AREA_THRESHOLD = 0.02  # Adjusted slightly lower to allow more complexity
MAX_FACE_RETRIES = 5

# --- SNAPSHOT UTILITIES (The Transaction Guard) ---

def get_map_state():
    global vertices, edges, faces
    # Deep copy lists to ensure pointers aren't corrupted during a rollback
    return list(vertices), list(edges), list(faces)

def restore_map_state(snapshot):
    global vertices, edges, faces
    vertices, edges, faces = snapshot

# --- MAIN GENERATION ENGINE ---

def randomSetup(seed):
    global vertices, edges, faces, face_attempts
    random.seed(seed)
    
    # Initialize the bounding box
    try:
        vertices, edges, faces = Frame.init_boundary() 
    except:
        return 

    face_attempts = {} 
    max_splits = 40
    splits_done = 0
    
    while splits_done < max_splits:
        # Filter for faces that are large enough and haven't hit the retry limit
        eligible_faces = [
            f for f in faces 
            if (hasattr(f, 'area') and f.area > (MIN_AREA_THRESHOLD * 3))
            and face_attempts.get(id(f), 0) < MAX_FACE_RETRIES
        ]
        
        if not eligible_faces:
            if debug: print(f"Mesh Saturated at {splits_done} splits.")
            break
            
        target_face = random.choice(eligible_faces)
        success = False
        strategy = random.random()
        
        try:
            # --- STRATEGY 1: Simple Linear Splits (60% chance) ---
            if strategy < 0.60:
                sub_strat = random.random()
                if sub_strat < 0.33: # VV
                    va, vb = random.sample(target_face.vertices, 2)
                    success = SplitFaceVV(target_face, va, vb)
                elif sub_strat < 0.66: # VE
                    v = random.choice(target_face.vertices)
                    e = random.choice(target_face.edges)
                    if v != e.tail and v != e.head:
                        p = Graph.PointOnEdge(e, random.uniform(0.2, 0.8))
                        success = SplitFaceVE(target_face, v, e, p)
                else: # EE
                    e1, e2 = random.sample(target_face.edges, 2)
                    if e1.trueEdge != e2.trueEdge:
                        p1 = Graph.PointOnEdge(e1, random.uniform(0.3, 0.7))
                        p2 = Graph.PointOnEdge(e2, random.uniform(0.3, 0.7))
                        success = SplitFaceEE(target_face, e1, p1, e2, p2)

            # --- STRATEGY 2: Path-based Splits (30% chance) ---
            elif strategy < 0.90:
                # Generate a simple 1-2 point path in the center of the face
                # This creates "organic" or "bent" edges
                face_center = target_face.centroid # Assumes Graph.Face has a centroid attr
                jitter = [Graph.Vector(face_center.x + random.uniform(-0.05, 0.05), 
                                       face_center.y + random.uniform(-0.05, 0.05))]
                
                va, vb = random.sample(target_face.vertices, 2)
                success = SplitFaceVVPath(target_face, va, vb, jitter)

            # --- STRATEGY 3:  using SplitFaceSameEdgePath instead of SplitFaceVCycle or others---
            else:
                e = random.choice(target_face.edges)
                p1 = Graph.PointOnEdge(e, 0.2)
                p2 = Graph.PointOnEdge(e, 0.8)
                # we are using SplitFaceSameEdgePath
                c = target_face.centroid
                path = [Graph.Vector((p1.x + c.x)/2, (p1.y + c.y)/2)] 
                success = SplitFaceSameEdgePath(target_face, e, p1, p2, path)
                        
        except Exception as e:
            if debug: print(f"Engine Exception: {e}")
            success = False 

        if success:
            splits_done += 1
        else:
            # Increment failure counter for this specific face object
            face_attempts[id(target_face)] = face_attempts.get(id(target_face), 0) + 1

    # Final topological cleanup and rendering
    FinalizeFaces.cleanup(faces)
    # faces = [f for f in faces if f is not None] 
    DrawGraph.draw(vertices, edges, faces)

# --- PROTECTED SPLITTING FUNCTIONS ---

def SplitFaceVV(face, va, vb):
    global faces, edges, debug
    snapshot = get_map_state()
    if debug: debugShow("SplitFaceVV", face, [va, vb], [], [], [])
    
    eea = Graph.ArcsAtVertexInFace(va, face)  
    eeb = Graph.ArcsAtVertexInFace(vb, face)
    
    if (SplitAtVAngleTooSmall(va.p, vb, eeb) or SplitAtVAngleTooSmall(vb.p, va, eea)):
        return False
    if TrueEdgesCollide(eea, eeb):
        return False
    if not face.convex and not Graph.InteriorEdge(va.p, vb.p, face, eea + eeb):
        return False
        
    try:
        ef = Graph.Edge(va, vb, True)
        er = ef.reverse
        face1 = InsertFace(face, va, vb, [er])
        face2 = InsertFace(face, vb, va, [ef])
        
        faces.remove(face) 
        faces += [face1, face2]
        edges += [ef, er]
        
        for v in face1.vertices + face2.vertices: SetVertexFaces(v)
        if debug: print("Success\n")
        return True
    except Exception as e:
        if debug: print(f"Transaction Failed: {e}")
        restore_map_state(snapshot)
        return False

def SplitFaceVE(face, v, e, p):
    global vertices, edges, faces
    snapshot = get_map_state()
    if debug: debugShow("SplitFaceVE", face, [v], [e], [p], [])
    
    eea = Graph.ArcsAtVertexInFace(v, face) 
    if SplitAtVAngleTooSmall(p, v, eea) or SplitAtEAngleTooSmall(v.p, p, e):
        return False
    if TrueEdgesCollide(eea, [e]) or Graph.tooClose(p, e.tail.p) or Graph.tooClose(p, e.head.p):
        return False
    if not face.convex and not Graph.InteriorEdge(v.p, p, face, eea + [e]):
        return False
        
    try:
        vNew = Graph.Vertex(p)
        [e1, e2] = SplitEdge(e, [vNew])
        ex = Graph.Edge(v, vNew, True)
        
        face1 = InsertFace(face, e.head, v, [ex, e2])
        face2 = InsertFace(face, v, e.tail, [e1, ex.reverse])
        
        # Careful topology update
        if e in e.tail.outarcs: e.tail.outarcs.remove(e)
        if e.reverse in e.head.outarcs: e.head.outarcs.remove(e.reverse)
        
        SplitEdgeOfFlip(e, [e2.reverse, e1.reverse])
        
        vertices.append(vNew)
        faces.remove(face)
        faces += [face1, face2]
        FixEdges([e], [e1, e2, ex])
        
        for v_obj in face1.vertices + face2.vertices: SetVertexFaces(v_obj)
        if debug: print("Success\n")
        return True
    except Exception as err:
        if debug: print(f"Transaction Failed: {err}")
        restore_map_state(snapshot)
        return False

def SplitFaceEE(face, ea, pa, eb, pb):
    global vertices, edges, faces
    snapshot = get_map_state()
    if debug: debugShow("SplitFaceEE", face, [], [ea, eb], [pa, pb], []) 
    
    if SplitAtEAngleTooSmall(pb, pa, ea) or SplitAtEAngleTooSmall(pa, pb, eb): 
        return False
    if not face.convex and not Graph.InteriorEdge(pa, pb, face, [ea, eb]): 
        return False
    if any(Graph.tooClose(p, end.p) for p in [pa, pb] for end in [ea.tail, ea.head, eb.tail, eb.head]):
        return False
        
    try:
        va, vb = Graph.Vertex(pa), Graph.Vertex(pb)
        ec = Graph.Edge(va, vb, True)
        [ea1, ea2] = SplitEdge(ea, [va])
        [eb1, eb2] = SplitEdge(eb, [vb])
        
        face1 = InsertFace(face, ea.head, eb.tail, [eb1, ec.reverse, ea2])
        face2 = InsertFace(face, eb.head, ea.tail, [ea1, ec, eb2])
        
        if ea in ea.tail.outarcs: ea.tail.outarcs.remove(ea)
        if ea.reverse in ea.head.outarcs: ea.head.outarcs.remove(ea.reverse)
        if eb in eb.tail.outarcs: eb.tail.outarcs.remove(eb)
        if eb.reverse in eb.head.outarcs: eb.head.outarcs.remove(eb.reverse)
        
        SplitEdgeOfFlip(ea, [ea2.reverse, ea1.reverse])
        SplitEdgeOfFlip(eb, [eb2.reverse, eb1.reverse])
        
        vertices += [va, vb]
        faces.remove(face)
        faces += [face1, face2]
        FixEdges([ea, eb], [ea1, ea2, eb1, eb2, ec])
        
        for v in face1.vertices + face2.vertices: SetVertexFaces(v)
        if debug: print("Success\n")
        return True
    except Exception as err:
        if debug: print(f"Transaction Failed: {err}")
        restore_map_state(snapshot)
        return False
def SplitFaceVVPath(face, va, vb, path):
    global vertices, faces, edges
    # --- ADD THIS SNAPSHOT ---
    snapshot = get_map_state()
    
    if debug:
       debugShow("SplitFaceVVPath", face, [va, vb], [], [], path) 
    
    # 1. Preliminary Geometry Checks
    eea = Graph.ArcsAtVertexInFace(va, face)  
    eeb = Graph.ArcsAtVertexInFace(vb, face)  
    if (SplitAtVAngleTooSmall(path[0], va, eea) or SplitAtVAngleTooSmall(path[-1], vb, eeb)
        or SplitAtPathAngleTooSmall([va.p] + path + [vb.p], False)):
       return False
    if not(Graph.InteriorPath(face, va.p, vb.p, path, eea, eeb)):
        return False
    if Graph.PathSelfCrossing([va.p] + path + [vb.p], va == vb):
        return False
    if (vb == va):
       return False
    #making sure the new vertex is not too close to the existing edges of the face
    for p in path:
        if not is_geometrically_clean(p, face, min_gap=0.07): 
            if debug: print(f"Rejected: Path point {p} too close to existing edge.")
            return False

    # --- START PROTECTED TRANSACTION ---
    try:
        v1 = va
        newVVS = []
        newEdges = []
        newRevEdges = []
        for p in path:
            v2 = Graph.Vertex(p)
            newVVS += [v2]
            newEdge = Graph.Edge(v1, v2, True) 
            newEdges += [newEdge]
            newRevEdges = [newEdge.reverse] + newRevEdges
            v1 = v2
        newEdge = Graph.Edge(v1, vb, True) 
        newEdges += [newEdge]
        newRevEdges = [newEdge.reverse] + newRevEdges
        
        # Area Guard usually triggers here inside BuildNewFaceFromEdges
        face1 = InsertFace(face, va, vb, newRevEdges)
        face2 = InsertFace(face, vb, va, newEdges)

        # Update global state only if the above succeeded
        for v in face.vertices + newVVS:
            SetVertexFaces(v)
        vertices += newVVS
        edges = edges + newEdges + newRevEdges 
        faces.remove(face) 
        faces += [face1, face2]
        
        if debug: print("Success\n")
        return True

    except Exception as e:
        if debug: print(f"Transaction Failed: {e}")
        # --- ADD THIS RESTORE ---
        restore_map_state(snapshot)
        return False

# def SplitFaceVCycle(face, va, path):
#     global vertices, faces, edges
#     snapshot = get_map_state()
#     if debug:
#        debugShow("SplitFaceVCycle", face, [va], [], [], path) 
    
#     eea = Graph.ArcsAtVertexInFace(va, face)  
#     if (SplitAtVAngleTooSmall(path[0], va, eea) or SplitAtVAngleTooSmall(path[-1], va, eea)
#         or SplitAtPathAngleTooSmall([va.p] + path + [va.p], True)):
#        return False
#     if not(Graph.InteriorPath(face, va.p, va.p, path, eea, eea)):
#         return False

#     try:
#         if Graph.PathSelfCrossing([va.p] + path + [va.p], True):
#             return False
            
#         newVVS = []
#         newEdges = []
#         newRevEdges = []
#         if not(Graph.PathCounterClockwise(va.p, path)):
#             path.reverse()
            
#         v1 = va
#         for p in path:
#             v2 = Graph.Vertex(p)
#             newVVS += [v2]
#             newEdge = Graph.Edge(v1, v2, True) 
#             newEdges += [newEdge]
#             newRevEdges = [newEdge.reverse] + newRevEdges
#             v1 = v2
#         newEdge = Graph.Edge(v1, va, True) 
#         newEdges += [newEdge]
#         newRevEdges = [newEdge.reverse] + newRevEdges
        
#         # Area Guard check happens inside these constructors
#         face1 = BuildNewFaceFromEdges(newEdges)
#         face2 = BuildNewFaceFromEdges(newRevEdges + FaceCycleEdgesFrom(face, va))

#         for v in face.vertices + newVVS:
#             SetVertexFaces(v)
#         vertices += newVVS
#         edges = edges + newEdges + newRevEdges 
#         faces.remove(face) 
#         faces += [face1, face2]
#         if debug: print("Success\n")
#         return True
#     except Exception as e:
#         if debug: print(f"VCycle Transaction Failed: {e}")
#         restore_map_state(snapshot)
#         return False
    
def SplitFaceVEPath(face, va, eb, pb, path):
    global vertices, faces, edges
    snapshot = get_map_state()
    if debug:
       debugShow("SplitFaceVEPath", face, [va], [eb], [pb], path) 
       
    eea = Graph.ArcsAtVertexInFace(va, face)  
    if (SplitAtVAngleTooSmall(path[0], va, eea) or SplitAtEAngleTooSmall(path[-1], pb, eb)
        or SplitAtPathAngleTooSmall([va.p] + path + [pb], False)):
       return False
    
    if not(Graph.InteriorPath(face, va.p, pb, path, eea, [eb])):
        return False
    
    # 3. GEOMETRIC CLEANLINESS (The Fix)
    # Check every 'bend' in the path, to make sure it is not too closed to Boundary
    for pt in path:
        if not is_geometrically_clean(pt, face, min_gap=0.06):
            if debug: print(f"Path point {pt} too close to boundary.")
            return False
            
    # Check the landing point on the edge
    if not is_geometrically_clean(pb, face, min_gap=0.06):
        if debug: print(f"Landing point {pb} too close to other boundary.")
        return False
    try:
        if Graph.PathSelfCrossing([va.p] + path + [pb], False):
            return False
            
        v1 = va
        newVVS = []
        newEdges = []
        newRevEdges = []
        for p in path + [pb]:
            v2 = Graph.Vertex(p)
            newVVS += [v2]
            newEdge = Graph.Edge(v1, v2, True) 
            newEdges += [newEdge]
            newRevEdges = [newEdge.reverse] + newRevEdges
            v1 = v2
        vNew = v2
        [e1, e2] = SplitEdge(eb, [vNew])
        newEdges += [e2]
        newRevEdges = [e1] + newRevEdges
        
        face1 = InsertFace(face, eb.head, va, newEdges)
        face2 = InsertFace(face, va, eb.tail, newRevEdges)
        
        eb.tail.outarcs.remove(eb)
        eb.head.outarcs.remove(eb.reverse)
        SplitEdgeOfFlip(eb, [e2.reverse, e1.reverse])
        FixEdges([eb], [e1, e2] + newEdges)

        for v in face.vertices + newVVS:
            SetVertexFaces(v)
        vertices += newVVS
        faces.remove(face) 
        faces += [face1, face2]
        if debug: print("Success\n")
        return True
    except Exception as e:
        if debug: print(f"VEPath Transaction Failed: {e}")
        restore_map_state(snapshot)
        return False
    
def SplitFaceEEPath(face, ea, eb, pa, pb, path):
    global vertices, faces, edges
    snapshot = get_map_state()
    if debug:
       debugShow("SplitFaceEEPath", face, [], [ea, eb], [pa, pb], path) 

    if (SplitAtEAngleTooSmall(path[0], pa, ea) or SplitAtEAngleTooSmall(path[-1], pb, eb)
        or SplitAtPathAngleTooSmall([pa] + path + [pb], False)):
       return False
    if not(Graph.InteriorPath(face, pa, pb, path, [ea], [eb])):
        return False

    try:
        if Graph.PathSelfCrossing([pa] + path + [pb], False):
            return False
            
        va = Graph.Vertex(pa)
        v1 = va
        newVVS = [va]
        newEdges = []
        newRevEdges = []
        for p in path + [pb]:
            v2 = Graph.Vertex(p)
            newVVS += [v2]
            newEdge = Graph.Edge(v1, v2, True) 
            newEdges += [newEdge]
            newRevEdges = [newEdge.reverse] + newRevEdges
            v1 = v2
        vb = v2
        [ea1, ea2] = SplitEdge(ea, [va])
        [eb1, eb2] = SplitEdge(eb, [vb])
        newEdges = [ea1] + newEdges + [eb2]
        newRevEdges = [eb1] + newRevEdges + [ea2]
        
        face1 = InsertFace(face, eb.head, ea.tail, newEdges)
        face2 = InsertFace(face, ea.head, eb.tail, newRevEdges)
        
        ea.tail.outarcs.remove(ea)
        ea.head.outarcs.remove(ea.reverse)
        eb.tail.outarcs.remove(eb)
        eb.head.outarcs.remove(eb.reverse)
        SplitEdgeOfFlip(ea, [ea2.reverse, ea1.reverse])
        SplitEdgeOfFlip(eb, [eb2.reverse, eb1.reverse])
        FixEdges([ea, eb], newEdges + [eb1, ea2])
        
        for v in face.vertices + newVVS:
            SetVertexFaces(v)
        vertices += newVVS
        faces.remove(face) 
        faces += [face1, face2]
        if debug: print("Success\n")
        return True
    except Exception as e:
        if debug: print(f"EEPath Transaction Failed: {e}")
        restore_map_state(snapshot)
        return False

def SplitFaceSameEdgePath(face, e, pa, pb, path):
    global vertices, faces, edges
    snapshot = get_map_state()
    if debug:
       debugShow("SplitFaceSameEdgePath", face, [], [e], [pa, pb], path) 
       
    if abs(Graph.signedAngle(pb, pa, e.head.p)) > 0.01:
        (pa, pb) = (pb, pa)      
        path.reverse()
        
    if (SplitAtEAngleTooSmall(path[0], pa, e) or SplitAtEAngleTooSmall(path[-1], pb, e)
        or SplitAtPathAngleTooSmall([pa] + path + [pb], False)):
       return False
    if not(Graph.InteriorPath(face, pa, pb, path, [e], [e])):
        return False

    try:
        if Graph.PathSelfCrossing([pa] + path + [pb], False):
            return False
            
        va = Graph.Vertex(pa)
        v1 = va
        newVVS = [va]
        newEdges = []
        newRevEdges = []
        for p in path + [pb]:
            v2 = Graph.Vertex(p)
            newVVS += [v2]
            newEdge = Graph.Edge(v1, v2, True) 
            newEdges += [newEdge]
            newRevEdges = [newEdge.reverse] + newRevEdges
            v1 = v2
        vb = v2
        [e1, e2, e3] = SplitEdge(e, [va, vb])
        newEdges = [e1] + newEdges + [e3]
        newRevEdges += [e2] 
        
        face1 = InsertFace(face, e.head, e.tail, newEdges)
        face2 = BuildNewFaceFromEdges(newRevEdges)
        
        e.tail.outarcs.remove(e)
        e.head.outarcs.remove(e.reverse)
        SplitEdgeOfFlip(e, [e3.reverse, e2.reverse, e1.reverse])
        FixEdges([e], [e2] + newEdges)
        
        for v in face.vertices + newVVS:
            SetVertexFaces(v)
        vertices += newVVS
        faces.remove(face) 
        faces += [face1, face2]
        if debug: print("Success\n")
        return True
    except Exception as e:
        if debug: print(f"SameEdgePath Transaction Failed: {e}")
        restore_map_state(snapshot)
        return False
    
# def SplitFaceSameEdgeCycle(face, e, pa, path):
#     global vertices, faces, edges
#     snapshot = get_map_state()
#     if debug:
#        debugShow("SplitFaceEECyc", face, [], [e], [pa], path) 
       
#     if (SplitAtEAngleTooSmall(path[0], pa, e) or SplitAtEAngleTooSmall(path[-1], pa, e)
#            or SplitAtPathAngleTooSmall([pa] + path + [pa], True)):
#          return False
#     if not(Graph.InteriorPath(face, pa, pa, path, [e], [e])):
#         return False

#     try:
#         if Graph.PathSelfCrossing([pa] + path + [pa], True):
#             return False
#         if not(Graph.PathCounterClockwise(pa, path)):
#             path.reverse()
            
#         va = Graph.Vertex(pa)
#         v1 = va
#         newVVS = [va]
#         newEdges = []
#         newRevEdges = []
#         for p in path:
#             v2 = Graph.Vertex(p)
#             newVVS += [v2]
#             newEdge = Graph.Edge(v1, v2, True) 
#             newEdges += [newEdge]
#             newRevEdges = [newEdge.reverse] + newRevEdges
#             v1 = v2
#         eLast = Graph.Edge(v1, va, True) 
#         newEdges += [eLast]
#         newRevEdges = [eLast.reverse] + newRevEdges
        
#         [e1, e2] = SplitEdge(e, [va])
#         newRevEdges = [e1] + newRevEdges + [e2]
        
#         face1 = InsertFace(face, e.head, e.tail, newRevEdges)
#         face2 = BuildNewFaceFromEdges(newEdges)
        
#         e.tail.outarcs.remove(e)
#         e.head.outarcs.remove(e.reverse)
#         SplitEdgeOfFlip(e, [e2.reverse, e1.reverse])
#         FixEdges([e], [e1, e2] + newEdges)
        
#         for v in face.vertices + newVVS:
#             SetVertexFaces(v)
#         vertices += newVVS
#         faces.remove(face) 
#         faces += [face1, face2]
#         if debug: print("Success\n")
#         return True
#     except Exception as e:
#         if debug: print(f"SameEdgeCycle Transaction Failed: {e}")
#         restore_map_state(snapshot)
#         return False

# --- CORE TOPOLOGY HELPERS ---

def BuildNewFaceFromEdges(newee):
    newFace = Graph.Face(newee, True)
    # Area Guard: If it fails here, the 'except' block in SplitFaceXX catches it
    if hasattr(newFace, 'area') and newFace.area < MIN_AREA_THRESHOLD:
        raise ValueError(f"Area {newFace.area:.4f} below threshold.")
    for ea in newee: ea.leftFace = newFace
    return newFace

def SetVertexFaces(v):
    """Safely rebuilds vertex-face adjacency without crashing on NoneTypes."""
    if not hasattr(v, 'outarcs') or not v.outarcs: return
    # Filter out None values and sort by angle
    v.outarcs = [e for e in v.outarcs if e is not None]
    v.outarcs = sorted(v.outarcs, key=lambda e: e.direction)
    # Rebuild face list
    v.faces = [ex.leftFace for ex in v.outarcs if hasattr(ex, 'leftFace') and ex.leftFace is not None]


# --- GEOMETRIC VALIDATION HELPERS ---

def TrueEdgesCollide(eea, eeb):
    return any(ea.trueEdge == eb.trueEdge for ea in eea for eb in eeb)

def SplitAtVAngleTooSmall(p, v, ee):
    if len(ee) < 2: return False
    return (Graph.AngleTooSmall(p, v.p, ee[0].head.p) or 
            Graph.AngleTooSmall(p, v.p, ee[1].tail.p)) 

def SplitAtEAngleTooSmall(pa, pb, e):
    return (Graph.AngleTooSmall(pa, pb, e.head.p) or 
            Graph.AngleTooSmall(pa, pb, e.tail.p))

def InsertFace(face, v1, v2, ee):
    return BuildNewFaceFromEdges(NewEdgesForFace(face, v1, v2, ee))

def NewEdgesForFace(face, v1, v2, newee):
    try:
        i, j = face.vertices.index(v1), face.vertices.index(v2)
        ee = face.edges[i:j] if i <= j else face.edges[i:] + face.edges[:j]
        return ee + newee
    except ValueError:
        raise ValueError("Vertex synchronization lost during face split.")

def SplitEdge(e, newVVS):
    vvs = [e.tail] + newVVS + [e.head]
    er = e.reverse
    newEdges = []
    for i in range(len(vvs)-1):
        nE = Graph.Edge(vvs[i], vvs[i+1], True)
        nE.trueEdge = e.trueEdge
        nE.reverse.trueEdge = er.trueEdge
        newEdges.append(nE)
    return newEdges

def SplitEdgeOfFlip(e, newEdges):
    ex = e.reverse
    flip = ex.leftFace
    if not flip or ex not in flip.edges: return 
    i = flip.edges.index(ex)
    flip.edges.pop(i)
    for en in newEdges:
        flip.edges.insert(i, en)
        i += 1
        en.leftFace = flip
    flip.vertices = Graph.getVertices(flip.edges)

def FixEdges(edgesRemove, edgesAdd):
    global edges
    for e in edgesRemove:
        if e in edges: edges.remove(e)
        if e.reverse in edges: edges.remove(e.reverse)
    for e in edgesAdd:
        edges += [e, e.reverse]

def debugShow(splitType, face, vertices, edges, points, path):
    print(f"--- Attempting {splitType} ---")
    Graph.ShowFaceShort(face)
    for v in vertices: print(f" Vertex: {v}")
    for e in edges: print(f" Edge: {e}")
    for p in points: print(f" Point: {p}")
    if path: print(" Path defined.")
def FaceCycleEdgesFrom(face,v):
    i = face.vertices.index(v)
    return face.edges[i:len(face.edges)]+face.edges[0:i]

def ShowMap(IncludeEdges):
    global vertices,edges,faces
    if IncludeEdges:
       Graph.ShowMap(vertices,edges,faces)
    else:
       Graph.ShowMap(vertices,[],faces)

def GC():
    global vertices,edges,faces
    return GraphCheck.GraphCheck(vertices,edges,faces)

def SplitAtPathAngleTooSmall(path, cycle):
    # Check all consecutive triplets in the path
    for i in range(len(path) - 2):
        if Graph.AngleTooSmall(path[i], path[i+1], path[i+2]):
            return True
    
    # If it's a closed loop, check the "seam" between the end and start
    if cycle and len(path) >= 3:
        # Check angle at path[0] using path[-2] and path[1]
        if Graph.AngleTooSmall(path[-2], path[0], path[1]):
            return True
    return False


#making a newly generated vertex is not too close to edges (that it is not connected to)
def is_geometrically_clean(point, face, min_gap=0.06):
    """
    Checks if a new point is far enough away from all edges 
    of the face that it is NOT intended to touch.
    """
    for edge in face.edges:
        # We only check edges that don't already use this point as an endpoint
        # Calculate distance from point to the line segment (edge.tail -> edge.head)
        dist = Graph.distPointFromEdge(point, edge.tail.p, edge.head.p)
        
        # If the point is NOT on this edge but is too close to it:
        if dist < min_gap and dist > 0.0001: 
            return False
    return True