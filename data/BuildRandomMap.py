import numpy as np
import Split
import Graph
import Frame
import FinalizeFaces
import DrawGraph
import GraphCheck

# Global settings for the generator
global numTries, epsilon
numTries = 15      # Increased attempts per face
epsilon = 0.04     # Slightly smaller to allow more room for splits

def BuildRandomMap(nfaces, x, y, seed, structure_complexity="current"):
    """
    Constructs a random polygonal map by iteratively splitting faces.
    """
    global vertices, edges, faces, generation_trace
    if structure_complexity not in {"current", "high"}:
        raise ValueError(
            "structure_complexity must be either 'current' or 'high'."
        )
    np.random.seed(seed)
    generation_trace = []
    
    # 1. Initialize the bounding box
    Split.vertices, Split.edges, Split.faces = Frame.makeFrame(x, y)
    
    # 2. Iteratively add faces
    for i in range(nfaces - 1):
        AddRandomFace(structure_complexity)
    
    # 3. Final cleanup of the geometry
    FinalizeFaces.FinalizeFaces(Split.vertices, Split.edges, Split.faces)

    # Never render or return a map whose planar embedding is invalid.  In
    # particular, an unregistered edge crossing can make one labeled face
    # appear as multiple disconnected pieces.
    if not GraphCheck.GraphCheck(Split.vertices, Split.edges, Split.faces):
        raise ValueError(f"Invalid generated map for seed {seed}: edge crossing or inconsistent topology")
    
    # 4. Visualization (Removed Split.ShowMap as it was causing errors)
    DrawGraph.DrawGraph(Split.faces, x, y)
    
    result = Graph.Map(Split.vertices, Split.edges, Split.faces, (x, y))
    result.generation_trace = list(generation_trace)
    return result

def AddRandomFace(structure_complexity="current"):
    """Attempts to split a face using a random method until success or timeout."""
    found = False
    attempts = 0
    MAX_RETRY = 100 

    global last_successful_split
    while not found and attempts < MAX_RETRY:
        attempts += 1
        last_successful_split = None
        face = ChooseRandomFace()
        if face is None: break
        
        action = ChooseRandomAction(face, structure_complexity)
        
        # Match actions to specific random split generators
        if action == 0: found = RandomlySplitVV(face)
        elif action == 1: found = RandomlySplitVE(face)
        elif action == 2: found = RandomlySplitEE(face)
        elif action == 3: found = RandomlySplitVVPath(face, structure_complexity)
        elif action == 4: found = RandomlySplitVCycle(face)
        elif action == 5: found = RandomlySplitVEPath(face, structure_complexity)
        elif action == 6: found = RandomlySplitEEPath(face, structure_complexity)
        elif action == 7: found = RandomlySplitSameEdgePath(face, structure_complexity)
        elif action == 8: found = RandomlySameEdgeCycle(face)

        if found and last_successful_split is not None:
            generation_trace.append(dict(last_successful_split))


def RecordSuccessfulSplit(split_type, internal_bend_count=0):
    """Record the split that actually succeeded, not merely an attempted action."""
    global last_successful_split
    last_successful_split = {
        "split_type": split_type,
        "is_path_split": split_type.endswith("Path"),
        "internal_bend_count": int(internal_bend_count),
    }
    return True

def ChooseRandomFace():
    """Weighted selection of faces based on area."""
    valid_faces = [f for f in Split.faces if f.bounded and f.area > 0.005]
    if not valid_faces:
        return None
    
    areas = [f.area for f in valid_faces]
    total = sum(areas)
    probs = [a / total for a in areas]
    return np.random.choice(valid_faces, p=probs)

def ChooseRandomAction(face, structure_complexity="current"):
    """Pick split type based on vertex count."""
    k = len(face.vertices)
    
    # Define only the actions that actually exist in your Split.py
    # We are EXCLUDING 4 (VCycle) and 8 (SameEdgeCycle)
    available_actions = [0, 1, 2, 3, 5, 6, 7] 
    
    if structure_complexity == "high":
        if k < 4:
            return np.random.choice(
                [1, 2, 3, 5, 6, 7],
                p=[0.10, 0.25, 0.20, 0.15, 0.15, 0.15],
            )
        return np.random.choice(
            [0, 1, 2, 3, 5, 6, 7],
            p=[0.05, 0.10, 0.20, 0.20, 0.15, 0.15, 0.15],
        )

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
            return RecordSuccessfulSplit("VV")
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
            return RecordSuccessfulSplit("VE")
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
            return RecordSuccessfulSplit("EE")
    return False

def RandomlySplitVVPath(face, structure_complexity="current"):
    k = len(face.vertices)
    if k < 2: return False
    for _ in range(numTries):
        i, j = np.random.choice(k, size=2, replace=False)
        va, vb = face.vertices[i], face.vertices[j]
        path = RandomPath(face, va.p, vb.p, structure_complexity)
        if Split.SplitFaceVVPath(face, va, vb, path):
            return RecordSuccessfulSplit("VVPath", len(path))
    return False

def RandomlySplitVCycle(face):
    k = len(face.vertices)
    for _ in range(numTries):
        v = face.vertices[np.random.randint(0, k)]
        path = RandomCycle(face, v.p)
        if Split.SplitFaceVCycle(face, v, path):
            return True
    return False

def RandomlySplitVEPath(face, structure_complexity="current"):
    k_v = len(face.vertices)
    k_e = len(face.edges)
    for _ in range(numTries):
        v = face.vertices[np.random.randint(0, k_v)]
        e = face.edges[np.random.randint(0, k_e)]
        if not SplitableEdge(e): continue
        p = RandomPointOnEdge(e)
        path = RandomPath(face, v.p, p, structure_complexity)
        if Split.SplitFaceVEPath(face, v, e, p, path):
            return RecordSuccessfulSplit("VEPath", len(path))
    return False

def RandomlySplitEEPath(face, structure_complexity="current"):
    k = len(face.edges)
    for _ in range(numTries):
        i, j = np.random.choice(k, size=2, replace=False)
        e1, e2 = face.edges[i], face.edges[j]
        if not (SplitableEdge(e1) and SplitableEdge(e2)): continue
        p1, p2 = RandomPointOnEdge(e1), RandomPointOnEdge(e2)
        path = RandomPath(face, p1, p2, structure_complexity)
        if Split.SplitFaceEEPath(face, e1, e2, p1, p2, path):
            return RecordSuccessfulSplit("EEPath", len(path))
    return False

def RandomlySplitSameEdgePath(face, structure_complexity="current"):
    k = len(face.edges)
    for _ in range(numTries):
        e = face.edges[np.random.randint(0, k)]
        if not TwiceSplitableEdge(e): continue
        p1 = RandomPointOnEdge(e)
        p2 = RandomPointOnEdge(e)
        # Ensure points aren't identical
        if Graph.vecDist(p1, p2) < epsilon: continue
        
        path = RandomPath(face, p1, p2, structure_complexity)
        if Split.SplitFaceSameEdgePath(face, e, p1, p2, path):
            return RecordSuccessfulSplit("SameEdgePath", len(path))
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

def RandomPath(face, p1, p2, structure_complexity="current"):
    """Generate ordered bend vertices between two split endpoints."""
    if structure_complexity == "current":
        # Preserve the pre-existing generator exactly for all current callers.
        return [Graph.randomPointInFace(face, False)]

    bend_count = int(np.random.choice([2, 3]))
    dx = p2.x - p1.x
    dy = p2.y - p1.y
    length = np.hypot(dx, dy)
    if length < epsilon:
        return [Graph.randomPointInFace(face, False)]

    normal_x = -dy / length
    normal_y = dx / length
    max_offset = min(0.14, max(0.035, 0.24 * length))

    # Projection positions are ordered from p1 to p2. Only the perpendicular
    # displacement is random, preventing the bends from doubling back.
    for _ in range(30):
        first_side = np.random.choice([-1.0, 1.0])
        path = []
        for index in range(1, bend_count + 1):
            t = index / (bend_count + 1)
            side = first_side if index % 2 else -first_side
            offset = side * np.random.uniform(0.45, 1.0) * max_offset
            offset *= np.sin(np.pi * t)
            point = Graph.Vector(
                p1.x + t * dx + offset * normal_x,
                p1.y + t * dy + offset * normal_y,
            )
            path.append(point)

        if all(Graph.pointInsideFace(point, face) for point in path):
            return path

    # The split-level geometry checks can still reject this conservative
    # fallback and retry another face/action.
    return [Graph.randomPointInFace(face, False)]

def RandomCycle(face, p):
    """Generates two points to help form a loop."""
    return [Graph.randomPointInFace(face, False), Graph.randomPointInFace(face, False)]
