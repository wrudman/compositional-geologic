import numpy as np
import Graph

global borders, commonVertex

def FinalizeFaces(v,e,f):
    global vertices, edges, faces
    vertices = v
    edges = e
    faces = f
    RebuildActiveTopology()
    for i in range(len(faces)):
        faces[i].num=i
    for fa in faces:
        fa.trueVertices = SetTrueVertices(fa)
        fa.numSides = len(fa.trueVertices)-1
    AssignColors()
    AssignLetters()
    return faces


def RebuildActiveTopology():
    """Remove references to faces and edges replaced during splitting."""
    global vertices, edges, faces

    active_edges = []
    seen_edges = set()
    for face in faces:
        face.vertices = Graph.getVertices(face.edges)
        for edge in face.edges:
            # Membership in an active face boundary is authoritative.
            edge.leftFace = face
            edge_id = id(edge)
            if edge_id not in seen_edges:
                seen_edges.add(edge_id)
                active_edges.append(edge)

    active_edge_ids = {id(edge) for edge in active_edges}
    if any(id(edge.reverse) not in active_edge_ids for edge in active_edges):
        raise ValueError("Invalid finalized map: an active edge has no active reverse half-edge.")

    # Mutate the shared list so Split.edges and future Map objects see cleanup.
    edges[:] = active_edges

    for vertex in vertices:
        vertex.outarcs = []
    for edge in edges:
        edge.tail.outarcs.append(edge)

    active_face_ids = {id(face) for face in faces}
    for vertex in vertices:
        vertex.outarcs.sort(key=lambda edge: edge.direction)
        vertex.faces = []
        seen_faces = set()
        for edge in vertex.outarcs:
            face = edge.leftFace
            face_id = id(face)
            if face_id in active_face_ids and face_id not in seen_faces:
                seen_faces.add(face_id)
                vertex.faces.append(face)

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

    # 1. Properly initialize a 2D matrix (Independent lists)
    borders = [[0 for _ in range(ff)] for _ in range(ff)]

    # 2. Create a lookup map: face_object_id -> index_in_list
    # This solves the "Face.num is too high" problem
    face_to_idx = {id(f): idx for idx, f in enumerate(faces)}

    # 3. Fill the adjacency matrix
    for e in edges:
        # Get the unique IDs for the faces on both sides of the edge
        id_left = id(e.leftFace)
        id_right = id(e.reverse.leftFace)

        # Check if both faces actually exist in our current face list
        if id_left in face_to_idx and id_right in face_to_idx:
            i = face_to_idx[id_left]
            j = face_to_idx[id_right]
            borders[i][j] = 1
        else:
            # This edge belongs to a face that was deleted or replaced
            # during the Split process. We skip it.
            continue
    # 4. Calculate neighbor counts for the coloring heuristic
    numBorders = [0] * ff
    for i in range(ff):
        numBorders[i] = sum(borders[i])

    # We ignore the outer frame (usually index 0) for ordering
    numBorders[0] = ff + 100

    # 5. Greedy Ordering (Smallest Last)
    face_order = []
    temp_numBorders = list(numBorders)
    for _ in range(ff):
        j = np.argmin(temp_numBorders)
        face_order = [j] + face_order
        for k in range(ff):
            if borders[j][k]:
                temp_numBorders[k] -= 1
        temp_numBorders[j] = 10000 + ff

    # 6. Find common vertices (for vertex-coloring constraints)
    commonVertex = FindCommonVertices(vertices, faces)

    # 7. Assign and apply colors
    color_assignments = AssignColors1(face_order, borders)
    for i in range(ff):
        faces[face_order[i]].color = color_assignments[i]

def AssignColors1(face_order, borders):
    ff = len(face_order)
    aa = [0] * ff
    for i in range(1, ff):
        # Index 0 is background, indices 1-6 are available colors
        # 2 = available, 1 = shares vertex, 0 = shares edge (illegal)
        possColors = [0] + [2] * 6
        li = face_order[i]

        for j in range(i):
            lj = face_order[j]
            if borders[li][lj]:
                possColors[aa[j]] = 0
            elif commonVertex[li][lj]:
                if possColors[aa[j]] > 1: # Only downgrade if it wasn't already 0
                    possColors[aa[j]] = 1

        if 2 in possColors:
            aa[i] = possColors.index(2)
        else:
            # Fallback to vertex-sharing color if no edge-sharing colors are free
            aa[i] = possColors.index(1)
    return aa

def FindCommonVertices(vertices, faces):
    ff = len(faces)

    # 1. Properly initialize a 2D matrix (Independent lists)
    # Using [[False]*ff]*ff creates pointers to the same list; this way is safer:
    commonVertex = [[False for _ in range(ff)] for _ in range(ff)]

    # 2. Create a lookup map: face_object_id -> index_in_the_current_list
    # This ensures that even if a face's .num is 50, if it's the 3rd item, it uses index 2.
    face_to_idx = {id(f): idx for idx, f in enumerate(faces)}

    for v in vertices:
        # v.faces contains the face objects meeting at this vertex
        v_faces = v.faces
        num_v_faces = len(v_faces)

        for i in range(num_v_faces - 1):
            face_i = v_faces[i]
            for j in range(i + 1, num_v_faces):
                face_j = v_faces[j]

                # 3. Use the mapping to get safe indices (0 to ff-1)
                try:
                    idx_i = face_to_idx[id(face_i)]
                    idx_j = face_to_idx[id(face_j)]

                    commonVertex[idx_i][idx_j] = True
                    commonVertex[idx_j][idx_i] = True
                except KeyError:
                    # This happens if a vertex still references a deleted face
                    continue

    return commonVertex



def AssignLetters():
    global faces
    a = np.array(range(1,len(faces)))
    np.random.shuffle(a)
    faces[0].letter = "Outside"
    for i in range(1,len(faces)):
        faces[i].letter = chr(ord('@')+a[i-1])
