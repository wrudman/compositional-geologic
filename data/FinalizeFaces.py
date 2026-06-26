import numpy as np
import Graph

global borders, commonVertex

def FinalizeFaces(v,e,f):
    global vertices, edges, faces
    vertices = v
    edges = e
    faces = f
    for i in range(len(faces)):
        faces[i].num=i
    for fa in faces:
        fa.trueVertices = SetTrueVertices(fa)
        fa.numSides = len(fa.trueVertices)-1
    AssignColors()
    AssignLetters()
    return faces    
   
def SetTrueVertices(fa):
    ee = fa.edges
    n = len(ee)
    for i in range(n):
        if abs(ee[i].direction - ee[i-1].direction) > Graph.angleeps:
            istart = i
            break
    trueVertices = [ee[istart].tail]
    for i in range(istart+1,n):
        if abs(ee[i].direction - ee[i-1].direction) > Graph.angleeps:
            trueVertices += [ee[i].tail]
    return trueVertices + [trueVertices[0]]
        
    
def AssignColors():
    global faces, edges, borders, commonVertex
    ff = len(faces)
    borders = [[0 for _ in range(ff)] for _ in range(ff)]
    face_to_idx = {id(f): idx for idx, f in enumerate(faces)}
    for e in edges:
        id_left = id(e.leftFace)
        id_right = id(e.reverse.leftFace)
        if id_left in face_to_idx and id_right in face_to_idx:
            i = face_to_idx[id_left]
            j = face_to_idx[id_right]
            if i == j:
                continue
            borders[i][j] = 1
            borders[j][i] = 1
    commonVertex = FindCommonVertices(vertices, faces)

    assignments = [None] * ff
    if ff:
        assignments[0] = 0

    bounded_indices = [i for i, face in enumerate(faces) if face.bounded]
    bounded_indices.sort(key=lambda i: sum(borders[i]), reverse=True)
    for idx in bounded_indices:
        assignments[idx] = ChooseFaceColor(idx, assignments)

    RepairBorderColorConflicts(assignments, bounded_indices)

    for i, color in enumerate(assignments):
        faces[i].color = 0 if color is None else color


def ChooseFaceColor(face_idx, assignments):
    available = list(range(1, 7))
    border_colors = {
        assignments[j]
        for j in range(len(assignments))
        if borders[face_idx][j] and assignments[j] is not None
    }
    vertex_colors = {
        assignments[j]
        for j in range(len(assignments))
        if commonVertex[face_idx][j] and assignments[j] is not None
    }
    preferred = [color for color in available if color not in border_colors and color not in vertex_colors]
    if preferred:
        return preferred[0]
    fallback = [color for color in available if color not in border_colors]
    if fallback:
        return fallback[0]
    return min(available, key=lambda color: BorderConflictCount(face_idx, color, assignments))


def BorderConflictCount(face_idx, color, assignments):
    return sum(
        1
        for j in range(len(assignments))
        if borders[face_idx][j] and assignments[j] == color
    )


def RepairBorderColorConflicts(assignments, bounded_indices):
    for _ in range(len(bounded_indices) * 2 + 1):
        conflict = FindBorderColorConflict(assignments, bounded_indices)
        if conflict is None:
            return
        i, j = conflict
        target = i if sum(borders[i]) <= sum(borders[j]) else j
        assignments[target] = ChooseFaceColor(target, assignments[:target] + [None] + assignments[target + 1:])


def FindBorderColorConflict(assignments, bounded_indices):
    bounded_set = set(bounded_indices)
    for i in bounded_indices:
        for j in bounded_set:
            if j <= i:
                continue
            if borders[i][j] and assignments[i] == assignments[j]:
                return i, j
    return None
        
def FindCommonVertices(vertices,faces):
    ff = len(faces)
    commonVertex = [[False for _ in range(ff)] for _ in range(ff)]
    face_to_idx = {id(f): idx for idx, f in enumerate(faces)}
    for v in vertices:
        v_faces = v.faces
        num_v_faces = len(v_faces)
        for i in range(num_v_faces-1):
            face_i = v_faces[i]
            for j in range(i+1,num_v_faces):
                face_j = v_faces[j]
                if id(face_i) not in face_to_idx or id(face_j) not in face_to_idx:
                    continue
                idx_i = face_to_idx[id(face_i)]
                idx_j = face_to_idx[id(face_j)]
                commonVertex[idx_i][idx_j] = True
                commonVertex[idx_j][idx_i] = True
    return commonVertex

   
    
def AssignLetters():
    global faces
    a = np.array(range(1,len(faces)))
    np.random.shuffle(a)
    faces[0].letter = "Outside"
    for i in range(1,len(faces)):
        faces[i].letter = chr(ord('@')+a[i-1])
