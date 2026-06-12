import numpy as np
import Split
import Graph
import Frame
import FinalizeFaces
import DrawGraph

# Global settings for the generator
global numTries, epsilon
numTries = 15      # Increased attempts per face
epsilon = 0.04     # Slightly smaller to allow more room for splits

def BuildRandomMap(nfaces, x, y, seed):
    """
    Constructs a random polygonal map by iteratively splitting faces.
    """
    global vertices, edges, faces
    np.random.seed(seed)
    
    # 1. Initialize the bounding box
    Split.vertices, Split.edges, Split.faces = Frame.makeFrame(x, y)
    
    # 2. Iteratively add faces
    for i in range(nfaces - 1):
        AddRandomFace()
    
    # 3. Final cleanup of the geometry
    FinalizeFaces.FinalizeFaces(Split.vertices, Split.edges, Split.faces)
    
    # 4. Visualization (Removed Split.ShowMap as it was causing errors)
    DrawGraph.DrawGraph(Split.faces, x, y)
    
    return Graph.Map(Split.vertices, Split.edges, Split.faces, (x, y))

def AddRandomFace():
    """Attempts to split a face using a random method until success or timeout."""
    found = False
    attempts = 0
    MAX_RETRY = 100 

    while not found and attempts < MAX_RETRY:
        attempts += 1
        face = ChooseRandomFace()
        if face is None: break
        
        action = ChooseRandomAction(face)
        
        # Match actions to specific random split generators
        if action == 0: found = RandomlySplitVV(face)
        elif action == 1: found = RandomlySplitVE(face)
        elif action == 2: found = RandomlySplitEE(face)
        elif action == 3: found = RandomlySplitVVPath(face)
        elif action == 4: found = RandomlySplitVCycle(face)
        elif action == 5: found = RandomlySplitVEPath(face)            
        elif action == 6: found = RandomlySplitEEPath(face)
        elif action == 7: found = RandomlySplitSameEdgePath(face)
        elif action == 8: found = RandomlySameEdgeCycle(face)

def ChooseRandomFace():
    """Weighted selection of faces based on area."""
    valid_faces = [f for f in Split.faces if f.bounded and f.area > 0.005]
    if not valid_faces:
        return None
    
    areas = [f.area for f in valid_faces]
    total = sum(areas)
    probs = [a / total for a in areas]
    return np.random.choice(valid_faces, p=probs)

def ChooseRandomAction(face):
    """Pick split type based on vertex count."""
    k = len(face.vertices)
    
    # Define only the actions that actually exist in your Split.py
    # We are EXCLUDING 4 (VCycle) and 8 (SameEdgeCycle)
    available_actions = [0, 1, 2, 3, 5, 6, 7] 
    
    if k < 4:
        # Probability distribution excluding VV (Action 0) and the missing ones
        # Adjusted weights to sum to 1.0
        return np.random.choice([1, 2, 3, 5, 6, 7], p=[0.2, 0.5, 0.1, 0.05, 0.1, 0.05])
    else:
        # Full distribution of WORKING actions
        return np.random.choice([0, 1, 2, 3, 5, 6, 7], p=[0.1, 0.15, 0.45, 0.1, 0.1, 0.05, 0.05])

# --- Random Split Generators ---

def RandomlySplitVV(face):
    k = len(face.vertices)
    if k < 4: return False
    for _ in range(numTries):
        i = np.random.randint(0, k)
        # Choose j at least 2 steps away from i
        offset = np.random.randint(2, k - 1)
        j = (i + offset) % k
        if Split.SplitFaceVV(face, face.vertices[i], face.vertices[j]):
            return True
    return False

def RandomlySplitVE(face):
    k = len(face.edges)
    for _ in range(numTries):
        edge_idx = np.random.randint(0, k)
        e = face.edges[edge_idx]
        if not SplitableEdge(e): continue
        
        # Vertex must not be an endpoint of the chosen edge
        # Vertices on edge i are i and (i+1)%k
        remaining_indices = [idx for idx in range(k) if idx != edge_idx and idx != (edge_idx + 1) % k]
        if not remaining_indices: continue
        
        v_idx = np.random.choice(remaining_indices)
        p = RandomPointOnEdge(e)
        if Split.SplitFaceVE(face, face.vertices[v_idx], e, p):
            return True
    return False

def RandomlySplitEE(face):
    k = len(face.edges)
    if k < 2: return False
    for _ in range(numTries):
        i, j = np.random.choice(k, size=2, replace=False)
        e1, e2 = face.edges[i], face.edges[j]
        if not (SplitableEdge(e1) and SplitableEdge(e2)): continue
        
        p1, p2 = RandomPointOnEdge(e1), RandomPointOnEdge(e2)
        if Split.SplitFaceEE(face, e1, p1, e2, p2):
            return True
    return False

def RandomlySplitVVPath(face):
    k = len(face.vertices)
    if k < 2: return False
    for _ in range(numTries):
        i, j = np.random.choice(k, size=2, replace=False)
        va, vb = face.vertices[i], face.vertices[j]
        path = RandomPath(face, va.p, vb.p)
        if Split.SplitFaceVVPath(face, va, vb, path):
            return True
    return False

def RandomlySplitVCycle(face):
    k = len(face.vertices)
    for _ in range(numTries):
        v = face.vertices[np.random.randint(0, k)]
        path = RandomCycle(face, v.p)
        if Split.SplitFaceVCycle(face, v, path):
            return True
    return False

def RandomlySplitVEPath(face):
    k_v = len(face.vertices)
    k_e = len(face.edges)
    for _ in range(numTries):
        v = face.vertices[np.random.randint(0, k_v)]
        e = face.edges[np.random.randint(0, k_e)]
        if not SplitableEdge(e): continue
        p = RandomPointOnEdge(e)
        path = RandomPath(face, v.p, p)
        if Split.SplitFaceVEPath(face, v, e, p, path):
            return True
    return False

def RandomlySplitEEPath(face):
    k = len(face.edges)
    for _ in range(numTries):
        i, j = np.random.choice(k, size=2, replace=False)
        e1, e2 = face.edges[i], face.edges[j]
        if not (SplitableEdge(e1) and SplitableEdge(e2)): continue
        p1, p2 = RandomPointOnEdge(e1), RandomPointOnEdge(e2)
        path = RandomPath(face, p1, p2)
        if Split.SplitFaceEEPath(face, e1, e2, p1, p2, path):
            return True
    return False

def RandomlySplitSameEdgePath(face):
    k = len(face.edges)
    for _ in range(numTries):
        e = face.edges[np.random.randint(0, k)]
        if not TwiceSplitableEdge(e): continue
        p1 = RandomPointOnEdge(e)
        p2 = RandomPointOnEdge(e)
        # Ensure points aren't identical
        if Graph.vecDist(p1, p2) < epsilon: continue
        
        path = RandomPath(face, p1, p2)
        if Split.SplitFaceSameEdgePath(face, e, p1, p2, path):
            return True
    return False

# def RandomlySameEdgeCycle(face):
#     k = len(face.edges)
#     for _ in range(numTries):
#         e = face.edges[np.random.randint(0, k)]
#         if not SplitableEdge(e): continue
#         p = RandomPointOnEdge(e)
#         path = RandomCycle(face, p)
#         if Split.SplitFaceSameEdgeCycle(face, e, p, path):
#             return True
#     return False

# --- Helpers ---

def RandomPointOnEdge(edge):
    """Pick a point on an edge, staying away from vertices using a tight buffer."""
    t = np.random.uniform(0.1, 0.9)
    return Graph.Vector(t * edge.tail.p.x + (1 - t) * edge.head.p.x,
                        t * edge.tail.p.y + (1 - t) * edge.head.p.y)

def SplitableEdge(e):
    return Graph.edgeLength(e) > (3 * epsilon)

def TwiceSplitableEdge(e):
    return Graph.edgeLength(e) > (6 * epsilon)

def RandomPath(face, p1, p2):
    """Generates a random internal point for jagged splits."""
    return [Graph.randomPointInFace(face, False)]

def RandomCycle(face, p):
    """Generates two points to help form a loop."""
    return [Graph.randomPointInFace(face, False), Graph.randomPointInFace(face, False)]