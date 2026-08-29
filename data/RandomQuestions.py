import Questions
import numpy as np
import Graph
import TestQuestions
from itertools import combinations

global numTries
global map
global debug
global failureOutput
global last_reference_program
numTries = 10
debug = True
failureOutput = ("", "", False, 0)
last_reference_program = None
# Optional dataset-level filters for line-path questions. Ordinary generation
# keeps the full range; high-complexity generation selects a difficulty band.
line_path_length_bands = {}
question11_visual_difficulty_filter = False
question16_balanced_union_area_filter = False
question2_high_edge_count_filter = False
question15_complex_union_neighbor_filter = False
question10_distance_ratio_band = None
question27_largest_area_ratio_filter = False
question4_answer_length_band = None
question13_answer_length_band = None
question22_visual_difficulty_filter = False
question22_target_answer = None
question1_complex_neighbor_filter = False
question5_complex_pair_filter = False
question24_distance_difficulty_filter = False


def set_line_path_length_band(question_id, min_length=None, max_length=None):
    """Restrict a line-path question by distinct-region count."""
    if min_length is None and max_length is None:
        line_path_length_bands.pop(question_id, None)
        return
    line_path_length_bands[question_id] = (min_length, max_length)


def set_question19_path_length_band(min_length=None, max_length=None):
    """Backward-compatible Q19 wrapper around the shared line-path policy."""
    set_line_path_length_band(19, min_length, max_length)


def _apply_line_path_length_filter(question_id, result):
    """Reject results outside the configured distinct-region band."""
    if not result[0] or question_id not in line_path_length_bands:
        return result
    min_length, max_length = line_path_length_bands[question_id]
    distinct_count = len(set(result[2]))
    if min_length is not None and distinct_count < min_length:
        return failureOutput
    if max_length is not None and distinct_count > max_length:
        return failureOutput
    return result


def set_question11_visual_difficulty_filter(enabled=False):
    """Enable the high-mode four-angle, visually distinguishable Q11 filter."""
    global question11_visual_difficulty_filter
    question11_visual_difficulty_filter = bool(enabled)


def set_question16_balanced_union_area_filter(enabled=False):
    """Require high-mode Q16 to use three moderately separated areas."""
    global question16_balanced_union_area_filter
    question16_balanced_union_area_filter = bool(enabled)


def set_question2_high_edge_count_filter(enabled=False):
    """Use visually similar, non-trivial edge counts for high-mode Q2."""
    global question2_high_edge_count_filter
    question2_high_edge_count_filter = bool(enabled)


def set_question15_complex_union_neighbor_filter(enabled=False):
    """Require a non-trivial union boundary and neighbor set in high Q15."""
    global question15_complex_union_neighbor_filter
    question15_complex_union_neighbor_filter = bool(enabled)


def set_question10_distance_ratio_band(min_ratio=None, max_ratio=None):
    """Restrict both adjacent sorted-distance ratios for high-mode Q10."""
    global question10_distance_ratio_band
    if min_ratio is None and max_ratio is None:
        question10_distance_ratio_band = None
        return
    question10_distance_ratio_band = (min_ratio, max_ratio)


def set_question27_largest_area_ratio_filter(enabled=False):
    """Keep the two largest regions visually distinct but not obvious."""
    global question27_largest_area_ratio_filter
    question27_largest_area_ratio_filter = bool(enabled)


def set_question4_answer_length_band(min_length=None, max_length=None):
    """Restrict high-mode boundary-trace answers by sequence length."""
    global question4_answer_length_band
    if min_length is None and max_length is None:
        question4_answer_length_band = None
        return
    question4_answer_length_band = (min_length, max_length)


def set_question13_answer_length_band(min_length=None, max_length=None):
    """Restrict Q13 by the number of bounded regions meeting at its vertex."""
    global question13_answer_length_band
    if min_length is None and max_length is None:
        question13_answer_length_band = None
        return
    question13_answer_length_band = (min_length, max_length)


def set_question22_visual_difficulty_filter(enabled=False, target_answer=None):
    """Enable high-mode segment-intersection geometry and answer balancing."""
    global question22_visual_difficulty_filter, question22_target_answer
    question22_visual_difficulty_filter = bool(enabled)
    question22_target_answer = target_answer if enabled else None


def set_question1_complex_neighbor_filter(enabled=False):
    global question1_complex_neighbor_filter
    question1_complex_neighbor_filter = bool(enabled)


def set_question5_complex_pair_filter(enabled=False):
    global question5_complex_pair_filter
    question5_complex_pair_filter = bool(enabled)


def set_question24_distance_difficulty_filter(enabled=False):
    global question24_distance_difficulty_filter
    question24_distance_difficulty_filter = bool(enabled)


def _question1_hard_candidate(face):
    if len(complex_faces()) < 6 or face.numSides < 6:
        return False
    edge_neighbors = {
        edge.reverse.leftFace for edge in face.edges
        if edge.reverse.leftFace and edge.reverse.leftFace.bounded
    }
    if not 4 <= len(edge_neighbors) <= 6:
        return False
    vertex_neighbors = {
        other for vertex in face.vertices for other in vertex.faces
        if other and other.bounded and other != face
    }
    return bool(vertex_neighbors - edge_neighbors)


def _question5_hard_map():
    faces = complex_faces()
    if len(faces) < 6:
        return False
    result = Questions.Question5(map)
    if not result[0] or not 2 <= len(result[2]) <= 4:
        return False
    edge_pairs = 0
    noncontact_pairs = 0
    for fa, fb in combinations(faces, 2):
        shares_edge = any(edge.reverse.leftFace == fb for edge in fa.edges)
        shares_vertex = bool(set(fa.vertices) & set(fb.vertices))
        edge_pairs += int(shares_edge)
        noncontact_pairs += int(not shares_vertex)
    if edge_pairs < 2 or noncontact_pairs < 2:
        return False
    big_x, big_y = map.bounds
    tolerance = 1e-8
    return any(
        any(
            tolerance < vertex.p.x < big_x - tolerance
            and tolerance < vertex.p.y < big_y - tolerance
            and fa in vertex.faces and fb in vertex.faces
            for vertex in map.vertices
        )
        for fa, fb in result[2]
    )


def _question22_hard_geometry(va, vb, vc, vd):
    """Return intersection details when a Q22 candidate meets hard geometry."""
    big_x, big_y = map.bounds
    diagonal = float(np.hypot(big_x, big_y))
    a, b, c, d = [vertex.p for vertex in (va, vb, vc, vd)]

    def distance(p, q):
        return float(np.hypot(q.x - p.x, q.y - p.y))

    if min(distance(a, b), distance(c, d)) < 0.30 * diagonal:
        return None

    overlap_x = min(max(a.x, b.x), max(c.x, d.x)) - max(
        min(a.x, b.x), min(c.x, d.x)
    )
    overlap_y = min(max(a.y, b.y), max(c.y, d.y)) - max(
        min(a.y, b.y), min(c.y, d.y)
    )
    if overlap_x < 0.03 * big_x or overlap_y < 0.03 * big_y:
        return None

    rx, ry = b.x - a.x, b.y - a.y
    sx, sy = d.x - c.x, d.y - c.y
    denominator = rx * sy - ry * sx
    if abs(denominator) < 1e-8:
        return None
    qpx, qpy = c.x - a.x, c.y - a.y
    t = (qpx * sy - qpy * sx) / denominator
    u = (qpx * ry - qpy * rx) / denominator
    crosses = 0.0 < t < 1.0 and 0.0 < u < 1.0

    if crosses:
        if not (0.15 <= t <= 0.85 and 0.15 <= u <= 0.85):
            return None
    else:
        if not (-0.25 <= t <= 1.25 and -0.25 <= u <= 1.25):
            return None
    return {"crosses": crosses, "t": float(t), "u": float(u)}


def _question15_candidate_details(fa, fb):
    """Return edge-neighbors, vertex-only distractors, and union side count."""
    union_face = Questions.FaceUnion(fa, fb)
    if union_face is False:
        return None
    edge_neighbors = set()
    for face, other in ((fa, fb), (fb, fa)):
        for edge in face.edges:
            neighbor = edge.reverse.leftFace
            if neighbor != other and neighbor.bounded:
                edge_neighbors.add(neighbor)
    vertex_neighbors = {
        face
        for source in (fa, fb)
        for vertex in source.vertices
        for face in vertex.faces
        if face.bounded and face not in (fa, fb)
    }
    return edge_neighbors, vertex_neighbors - edge_neighbors, union_face.numSides


def _question11_angle_profile_is_eligible(face):
    """Keep four angles challenging, distinguishable, and label-readable."""
    vertices = face.trueVertices[1:]
    if len(vertices) != 4:
        return False
    big_x, big_y = map.bounds
    diagonal = float(np.hypot(big_x, big_y))
    # A numerically valid quadrilateral can be a very thin sliver. Four fixed
    # annotations cannot be read there, even when its angles are well separated.
    box_width = face.box[1] - face.box[0]
    box_height = face.box[3] - face.box[2]
    if box_width < 0.16 * big_x or box_height < 0.16 * big_y:
        return False
    if face.area < 0.025 * big_x * big_y:
        return False
    for first, second in combinations(vertices, 2):
        if Graph.pointDist(first.p, second.p) < 0.10 * diagonal:
            return False

    # Mirror the renderer's angle-label geometry in map coordinates and reject
    # candidates whose labels would overlap even though their vertices do not.
    label_radius = 69.0 / 800.0 * max(big_x, big_y)
    label_points = []
    for vertex in vertices:
        incoming = next((edge for edge in face.edges if edge.head == vertex), None)
        outgoing = next((edge for edge in face.edges if edge.tail == vertex), None)
        if incoming is None or outgoing is None:
            return False
        angle_in = float(np.arctan2(
            -(incoming.tail.p.y - vertex.p.y),
            incoming.tail.p.x - vertex.p.x,
        ))
        angle_out = float(np.arctan2(
            -(outgoing.head.p.y - vertex.p.y),
            outgoing.head.p.x - vertex.p.x,
        ))
        while angle_out < angle_in:
            angle_out += 2 * np.pi
        midpoint = angle_in + (angle_out - angle_in) / 2.0
        label_points.append((
            vertex.p.x + label_radius * np.cos(midpoint),
            vertex.p.y - label_radius * np.sin(midpoint),
        ))
    minimum_label_spacing = 0.075 * diagonal
    for first, second in combinations(label_points, 2):
        if float(np.hypot(first[0] - second[0], first[1] - second[1])) < minimum_label_spacing:
            return False

    angles_degrees = sorted(
        float(np.degrees(Graph.angleAtFace(vertex, face))) for vertex in vertices
    )
    adjacent_gaps = [
        angles_degrees[index + 1] - angles_degrees[index]
        for index in range(3)
    ]
    return min(adjacent_gaps) >= 12.0 and max(adjacent_gaps) <= 60.0


def choose_from_complex_candidates(candidates, score_function, top_fraction=0.40):
    """Randomly choose within the most structurally complex candidate band."""
    candidates = list(candidates)
    if not candidates:
        return None
    scored = sorted(
        ((float(score_function(candidate)), candidate) for candidate in candidates),
        key=lambda pair: pair[0],
        reverse=True,
    )
    keep_count = max(1, int(np.ceil(len(scored) * top_fraction)))
    top_candidates = [candidate for _, candidate in scored[:keep_count]]
    return np.random.choice(top_candidates)


def complex_faces():
    global map
    return [face for face in map.faces if face.bounded]


def complex_vertices():
    global map
    return list(map.vertices)


def internal_adjacent_edges():
    global map
    return [
        edge for edge in map.edges
        if edge.leftFace.bounded and edge.reverse.leftFace.bounded
    ]


def _ask(question_id, question_function, *inputs):
    """Capture structured semantics before the question text is rendered."""
    global last_reference_program
    last_reference_program = None
    try:
        reference = Questions.BuildReferenceProgram(question_id, *inputs)
    except (ValueError, TypeError, IndexError):
        return failureOutput
    result = question_function(*inputs)
    if result[0] and result[3] > 0:
        last_reference_program = reference
    return result

def randomSetup(seed):
    global map
    TestQuestions.randomSetup(seed)
    map = TestQuestions.map

def GenRandomBenmarks(nmaps,nquestions,nfaces,x,y):
    for i in range(nmaps):    
        map=BuildRandomMap.BuildRandomMaps(nfaces,x,y,2*i)
        if GraphCheck.GraphCheck(map.vertices,map.edges,map.faces):
            qaPairs = randomQuestions(nquestions,2*i+1)
            RecordQAPairs(qaPairs)
        else:
            RecordMapBug(map)
    
def displayRandomQuestion(key,seed):
    map = TestQuestions.map
    np.random.seed(seed)
    for i in range(50):
        question, answerText, answer, quality = tryrandomQuestion(key)
        if quality > 0:
            print("Question " + str(key) +":", question)
            print("Answer:", answerText)
            return

def randomQuestions(nquestions,seed):
    np.random.seed(seed)
    count = 0
    qaPairs = []
    enabled_questions = (
        [q for q in range(1, 30) if q not in {3, 6, 7, 17}]
        + list(range(30, 34))
    )
    nums = np.random.permutation(enabled_questions)
    for q in nums:
        qaPair = triesRandomQuestion(q)
        (question, answer) = qaPair
        if question != False:
            print("Question " + str(q) + ":", question)
            print("Answer:", answer)
            qaPairs += [qaPair]
            count += 1
            if count >= nquestions:
                return qaPairs

def triesRandomQuestion(key, include_reference=False):
    global numTries
    qaPairs = []
    qualities = []
    references = []
    n = numTries
    if key in [3,5,6,7,8,17,23]:
        n=1
    for i in range(n):
        question, answerText, answer, quality = tryrandomQuestion(key)
        if quality > 0:
            qaPairs += [(question,answerText)]
            qualities += [quality]
            references += [last_reference_program]
    if len(qaPairs) == 0: 
        return (False, False, None) if include_reference else (False, False)
    s = sum(qualities)
    prob = []
    for q in qualities:
        prob += [q/s]
    i = np.random.choice(len(qaPairs),p=prob)
    if include_reference:
        return qaPairs[i][0], qaPairs[i][1], references[i]
    return qaPairs[i]
   

def tryrandomQuestion(key):
     match key:
         case 1:
             return randomQuestion1()
         case 2:
             return randomQuestion2()
         case 3:
             return randomQuestion3()
         case 4:
             return randomQuestion4()
         case 5:
             return randomQuestion5()
         case 6:
             return randomQuestion6()
         case 7:
             return randomQuestion7()
         case 8:
             return randomQuestion8()
         case 9:
             return randomQuestion9()
         case 10:
             return randomQuestion10()
         case 11:
             return randomQuestion11()
         case 12:
             return randomQuestion12()
         case 13:
             return randomQuestion13()
         case 14:
             return randomQuestion14()
         case 15:
             return randomQuestion15()
         case 16:
             return randomQuestion16()
         case 17:
             return randomQuestion17()
         case 18:
             return randomQuestion18()
         case 19:
             return randomQuestion19()
         case 20:
             return randomQuestion20()
         case 21:
             return randomQuestion21()
         case 22:
             return randomQuestion22()
         case 23:
             return randomQuestion23()
         case 24:
             return randomQuestion24()
         case 25:
             return randomQuestion25()
         case 26:
             return randomQuestion26()
         case 27:
             return randomQuestion27()
         case 28:
             return randomQuestion28()
         case 29:
             return randomQuestion29()
         case 30:
             return randomQuestion30()
         case 31:
             return randomQuestion31()
         case 32:
             return randomQuestion32()
         case 33:
             return randomQuestion33()
         case 34:
             return randomQuestion34()


def randomQuestion1():
    global map
    candidates = complex_faces()
    if question1_complex_neighbor_filter:
        candidates = [face for face in candidates if _question1_hard_candidate(face)]
    face = choose_from_complex_candidates(candidates, Questions.FaceLocalComplexity)
    if face is None:
        return failureOutput
    return _ask(1, Questions.Question1, face)

#                          RANDOM QUESTION 29
def randomQuestion2():
    global map
    if question2_high_edge_count_filter:
        eligible_faces = [face for face in complex_faces() if face.numSides >= 5]
        yes_pairs = []
        no_pairs = []
        for fa, fb in combinations(eligible_faces, 2):
            difference = abs(fa.numSides - fb.numSides)
            if difference == 0:
                yes_pairs.append((fa, fb))
            elif difference in {1, 2}:
                no_pairs.append((fa, fb))
        if yes_pairs and no_pairs:
            candidates = yes_pairs if np.random.random() < 0.5 else no_pairs
        else:
            candidates = yes_pairs or no_pairs
        if not candidates:
            return failureOutput
        fa, fb = candidates[np.random.choice(len(candidates))]
        return _ask(2, Questions.Question2, fa, fb)

    # Pick two distinct random faces to compare their sides
    pool = sorted(
        complex_faces(), key=Questions.FaceLocalComplexity, reverse=True
    )[:max(2, int(np.ceil(len(complex_faces()) * 0.5)))]
    fa, fb = np.random.choice(pool, size=2, replace=False)
    return _ask(2, Questions.Question2, fa, fb)

def randomQuestion3():
    return failureOutput

def randomQuestion4():
    global map
    eligible_faces = [
        face for face in complex_faces()
        if all(len(vertex.outarcs) <= 3 for vertex in face.vertices)
    ]
    if not eligible_faces:
        return failureOutput
    if question4_answer_length_band is not None:
        min_length, max_length = question4_answer_length_band
        candidates = []
        for face in eligible_faces:
            for vertex in face.vertices[1:]:
                for direction in (True, False):
                    answer = Questions.Question4Compute(face, vertex, direction)
                    answer_length = len(answer)
                    if answer_length < min_length:
                        continue
                    if max_length is not None and answer_length > max_length:
                        continue
                    has_repeat = answer_length > len(set(answer))
                    score = Questions.FaceLocalComplexity(face)
                    candidates.append((has_repeat, score, face, vertex, direction))
        if not candidates:
            return failureOutput
        # Repeated, non-consecutive neighbors add memory load. Prefer them when
        # available, but do not require them for every hard boundary trace.
        repeated = [candidate for candidate in candidates if candidate[0]]
        selection_pool = repeated or candidates
        selection_pool.sort(key=lambda item: item[1], reverse=True)
        keep_count = max(1, int(np.ceil(len(selection_pool) * 0.4)))
        _, _, face, v, direction = selection_pool[np.random.choice(keep_count)]
        return _ask(4, Questions.Question4, face, v, direction, randomCodes(1))
    face = choose_from_complex_candidates(
        eligible_faces, Questions.FaceLocalComplexity
    )
    v = np.random.choice(face.vertices[1:])
    direction = np.random.choice([True,False])
    return _ask(4, Questions.Question4, face, v, direction, randomCodes(1))

def randomQuestion5():
    global map
    if question5_complex_pair_filter and not _question5_hard_map():
        return failureOutput
    return _ask(5, Questions.Question5, map)

def randomQuestion6():
    return failureOutput

def randomQuestion7():
    global map
    return Questions.Question7(map)

def randomQuestion8():
    global map
    k = np.random.choice([3,4,5,6],p=[1/6,1/3,1/3,1/6])
    return _ask(8, Questions.Question8, map, k)

def randomQuestion9():
    global map
    face = choose_from_complex_candidates(
        complex_faces(), Questions.FaceLocalComplexity
    )
    return _ask(9, Questions.Question9, face)

def randomQuestion10():
    global map
    if question10_distance_ratio_band is not None:
        min_ratio, max_ratio = question10_distance_ratio_band
        reference_vertices = sorted(
            map.vertices,
            key=Questions.VertexLocalComplexity,
            reverse=True,
        )[:max(1, int(np.ceil(len(map.vertices) * 0.6)))]
        candidates = []
        minimum_distance = 0.08 * (map.bounds[0] ** 2 + map.bounds[1] ** 2) ** 0.5
        for vp in reference_vertices:
            alternates = [vertex for vertex in map.vertices if vertex != vp]
            for triple in combinations(alternates, 3):
                ordered = sorted(
                    ((Graph.pointDist(vp.p, vertex.p), vertex) for vertex in triple),
                    key=lambda item: item[0],
                )
                distances = [item[0] for item in ordered]
                if distances[0] < minimum_distance:
                    continue
                ratios = (
                    distances[1] / distances[0],
                    distances[2] / distances[1],
                )
                if any(ratio < min_ratio for ratio in ratios):
                    continue
                if max_ratio is not None and any(ratio > max_ratio for ratio in ratios):
                    continue
                candidates.append((vp, [item[1] for item in ordered]))
        if not candidates:
            return failureOutput
        vp, ordered_vertices = candidates[np.random.choice(len(candidates))]
        va, vb, vc = np.random.permutation(ordered_vertices)
        codeP, codeA, codeB, codeC = randomCodes(4)
        return _ask(
            10, Questions.Question10,
            vp, va, vb, vc, codeP, codeA, codeB, codeC,
        )

    vp = np.random.choice(map.vertices)
    distances = []
    alternates = []
    for v in map.vertices:
        if v != vp:
            alternates += [v]
            distances += [Graph.pointDist(vp.p,v.p)]
    found, va, vb, vc = RandomSeparatedTriples(alternates,distances,1.5)
    if not found:
        return failureOutput
    [va,vb,vc] = np.random.permutation([va,vb,vc])
    codeP,codeA,codeB,codeC = randomCodes(4)
    return _ask(
        10, Questions.Question10,
        vp, va, vb, vc, codeP, codeA, codeB, codeC,
    )

def randomQuestion11():
    global map
    eligible_faces = [
        face for face in map.faces
        if face.bounded and len(face.trueVertices) - 1 == 4
    ]
    if question11_visual_difficulty_filter:
        eligible_faces = [
            face for face in eligible_faces
            if _question11_angle_profile_is_eligible(face)
        ]
    if not eligible_faces:
        return failureOutput
    face = choose_from_complex_candidates(
        eligible_faces, Questions.FaceLocalComplexity
    )
    codes = randomCodes(4)
    return _ask(11, Questions.Question11, face, codes)

def randomQuestion12():
    global map
    face = choose_from_complex_candidates(
        complex_faces(), Questions.FaceLocalComplexity
    )
    vertices = face.trueVertices[:-1]
    eligible_pairs = [
        (vertices[i], vertices[(i + 1) % len(vertices)])
        for i in range(len(vertices))
        if not Questions.BoundaryEdge(
            vertices[i].p,
            vertices[(i + 1) % len(vertices)].p,
            map.bounds,
        )
    ]
    if not eligible_pairs:
        return failureOutput
    va, vb = eligible_pairs[np.random.choice(len(eligible_pairs))]
    result = _ask(12, Questions.Question12, va, vb, randomCodes(1), map)
    return _apply_line_path_length_filter(12, result)

def randomQuestion13():
    global map
    candidates = complex_vertices()
    if question13_answer_length_band is not None:
        min_length, max_length = question13_answer_length_band
        candidates = [
            vertex for vertex in candidates
            if not any(not face.bounded for face in vertex.faces)
            and (min_length is None or len({
                face for face in vertex.faces if face.bounded
            }) >= min_length)
            and (max_length is None or len({
                face for face in vertex.faces if face.bounded
            }) <= max_length)
        ]
    if not candidates:
        return failureOutput
    v = choose_from_complex_candidates(
        candidates, Questions.VertexLocalComplexity
    )
    return _ask(13, Questions.Question13, v, randomCodes(1))

def randomQuestion14():
    global map
    eligible_edges = internal_adjacent_edges()
    if not eligible_edges:
        return failureOutput
    e = choose_from_complex_candidates(
        eligible_edges,
        lambda edge: Questions.AdjacentPairLocalComplexity(
            edge.leftFace, edge.reverse.leftFace
        ),
    )
    return _ask(14, Questions.Question14, e.leftFace, e.reverse.leftFace)

def randomQuestion15():
    global map
    eligible_edges = internal_adjacent_edges()
    if not eligible_edges:
        return failureOutput
    if question15_complex_union_neighbor_filter:
        if len(complex_faces()) < 5:
            return failureOutput
        candidates = []
        seen_pairs = set()
        for edge in eligible_edges:
            fa, fb = edge.leftFace, edge.reverse.leftFace
            pair_key = frozenset((id(fa), id(fb)))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            details = _question15_candidate_details(fa, fb)
            if details is None:
                continue
            edge_neighbors, vertex_only, union_sides = details
            if 3 <= len(edge_neighbors) <= 5 and union_sides >= 5 and vertex_only:
                score = (
                    len(edge_neighbors) * 10
                    + union_sides
                    + Questions.AdjacentPairLocalComplexity(fa, fb)
                )
                candidates.append((score, fa, fb))
        if not candidates:
            return failureOutput
        candidates.sort(key=lambda item: item[0], reverse=True)
        keep_count = max(1, int(np.ceil(len(candidates) * 0.4)))
        _, fa, fb = candidates[np.random.choice(keep_count)]
        return _ask(15, Questions.Question15, fa, fb, map)
    e = choose_from_complex_candidates(
        eligible_edges,
        lambda edge: Questions.AdjacentPairLocalComplexity(
            edge.leftFace, edge.reverse.leftFace
        ),
    )
    return _ask(
        15, Questions.Question15, e.leftFace, e.reverse.leftFace, map
    )

def randomQuestion16():
    global map
    if question16_balanced_union_area_filter:
        bounded_faces = [face for face in map.faces if face.bounded]
        adjacent_pairs = []
        seen_pairs = set()
        for edge in internal_adjacent_edges():
            fa, fb = edge.leftFace, edge.reverse.leftFace
            pair_key = frozenset((id(fa), id(fb)))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            adjacent_pairs.append((fa, fb))

        candidates = []
        for fa, fb in adjacent_pairs:
            union_area = fa.area + fb.area
            remaining = [face for face in bounded_faces if face not in (fa, fb)]
            for face_a, face_b in combinations(remaining, 2):
                ordered_areas = sorted((union_area, face_a.area, face_b.area))
                lower_ratio = ordered_areas[1] / ordered_areas[0]
                upper_ratio = ordered_areas[2] / ordered_areas[1]
                if 1.3 <= lower_ratio <= 1.6 and 1.3 <= upper_ratio <= 1.6:
                    candidates.append([[fa, fb], face_a, face_b])
        if not candidates:
            return failureOutput
        facepairs = candidates[np.random.choice(len(candidates))]
        return _ask(16, Questions.Question16, facepairs, map)

    nfaces =  np.random.choice([3,4], p=[2/3,1/3])
    facesLeft = [face for face in map.faces if face.bounded]
    nfaces = min(nfaces, len(facesLeft))
    if nfaces < 2:
        return failureOutput
    facepairs = []
    for i in range(nfaces):
        if not facesLeft:
            break
        fa = np.random.choice(facesLeft)
        facesLeft.remove(fa)
        options = []
        pair = np.random.choice([False,True],p=[2/3,1/3])
        if pair:
            for e in fa.edges:
                fx = e.reverse.leftFace
                if fx in facesLeft and fx not in options:
                    options += [e.reverse.leftFace]
            if len(options) > 0:
                fb = np.random.choice(options)
                facesLeft.remove(fb)
                facepairs += [[fa,fb]]
        if (not pair) or (len(options) == 0):
            facepairs += [fa]
    return _ask(16, Questions.Question16, facepairs, map)

# ==========================================
#                   RANDOM QUESTION 17
# ==========================================
def randomQuestion17():
    return failureOutput

def randomQuestion18():
    global map
    pool = sorted(
        complex_vertices(), key=Questions.VertexLocalComplexity, reverse=True
    )[:max(2, int(np.ceil(len(complex_vertices()) * 0.6)))]
    va,vb = np.random.choice(pool,size=2,replace=False)
    codeA,codeB = randomCodes(2)
    result = _ask(18, Questions.Question18, va, vb, codeA, codeB, map)
    return _apply_line_path_length_filter(18, result)

#                          RANDOM QUESTION 19
def randomQuestion19():
    """
    Randomly selects a vertex and a cardinal direction to trace a ray.
    """
    global map
    # Pick a vertex that is not on the very edge if possible, 
    # but Q19Check will handle the boundary logic anyway.
    v = choose_from_complex_candidates(
        complex_vertices(), Questions.VertexLocalComplexity
    )
    
    # Randomly choose one of the 4 cardinal directions:
    # 0: Right, 1: Up, 2: Left, 3: Down
    direction = np.random.choice([0, 1, 2, 3])
    
    code = randomCodes(1)
    
    # Question19 retains its dual-threshold ambiguity guard.  A dataset may
    # additionally request a short/medium or long compositional path band.
    result = _ask(19, Questions.Question19, v, direction, code, map)
    if not result[0]:
        return result
    return _apply_line_path_length_filter(19, result)

def randomQuestion20():
    global map
    pool = sorted(
        complex_vertices(), key=Questions.VertexLocalComplexity, reverse=True
    )[:max(3, int(np.ceil(len(complex_vertices()) * 0.65)))]
    va,vb,vc = np.random.choice(pool,size=3,replace=False)
    direction = np.random.choice([0,1])
    codeA, codeB, codeC = randomCodes(3)
    return _ask(
        20, Questions.Question20,
        va, vb, vc, direction, codeA, codeB, codeC,
    )

def randomQuestion21():
    global map
    pool = sorted(
        complex_vertices(), key=Questions.VertexLocalComplexity, reverse=True
    )[:max(3, int(np.ceil(len(complex_vertices()) * 0.65)))]
    va,vb,vc = np.random.choice(pool,size=3,replace=False)
    codeA, codeB, codeC = randomCodes(3)
    return _ask(
        21, Questions.Question21, va, vb, vc, codeA, codeB, codeC
    )

def randomQuestion22():
    global map
    pool = sorted(
        complex_vertices(), key=Questions.VertexLocalComplexity, reverse=True
    )[:max(4, int(np.ceil(len(complex_vertices()) * 0.70)))]
    attempts = 250 if question22_visual_difficulty_filter else 1
    for _ in range(attempts):
        va,vb,vc,vd = np.random.choice(pool,size=4,replace=False)
        if question22_visual_difficulty_filter:
            geometry = _question22_hard_geometry(va, vb, vc, vd)
            if geometry is None:
                continue
            if (
                question22_target_answer is not None
                and geometry["crosses"] != question22_target_answer
            ):
                continue
        codeA, codeB, codeC, codeD = randomCodes(4)
        result = _ask(
            22, Questions.Question22,
            va, vb, vc, vd, codeA, codeB, codeC, codeD,
        )
        if result[0]:
            return result
    return failureOutput


def randomQuestion23():
    global map
    dir = np.random.choice(2)
    return _ask(23, Questions.Question23, dir, map)

def randomQuestion24():
    global map, numTries
    for i in range(numTries):
        ranked = sorted(
            complex_faces(), key=Questions.FaceLocalComplexity, reverse=True
        )
        pool = ranked[:max(3, int(np.ceil(len(ranked) * 0.65)))]
        fa,fb,fc = np.random.choice(pool,size=3,replace=False)
        if question24_distance_difficulty_filter:
            dab = Graph.distBetweenFaces(fa, fb)
            dac = Graph.distBetweenFaces(fa, fc)
            close, far = sorted((dab, dac))
            frame_diagonal = float(np.hypot(*map.bounds))
            if close < 0.05 * frame_diagonal:
                continue
            ratio = far / close if close > 0 else float("inf")
            if not 1.3 <= ratio <= 1.6:
                continue
        question, answerText, answer, quality = _ask(
            24, Questions.Question24, fa, fb, fc
        )
        if quality > 0:
            return question, answerText, answer, quality
    return failureOutput
        


#                          RANDOM QUESTION 25
def randomQuestion25():
    global map
    # 1. Filter out the 'Outside' face (Face 0/@)
    valid_faces = [f for f in map.faces if f.num > 0 and f.bounded]
    
    if not valid_faces:
        return None, None, False, 0.0
        
    bounds = getattr(map, 'bounds', (1.0, 1.0))
    
    # 2. Sort faces into 'Yes' and 'No' pools
    yes_pool = []
    no_pool = []
    
    for f in valid_faces:
        # We run the logic check silently to categorize
        _, _, touches, _ = Questions.Question25(f, bounds)
        if touches:
            yes_pool.append(f)
        else:
            no_pool.append(f)
            
    # 3. 50/50 Selection Logic
    # If both pools have candidates, flip a coin
    if yes_pool and no_pool:
        if np.random.random() > 0.5:
            selected_face = choose_from_complex_candidates(
                yes_pool, Questions.FaceLocalComplexity
            )
        else:
            selected_face = choose_from_complex_candidates(
                no_pool, Questions.FaceLocalComplexity
            )
    elif yes_pool:
        selected_face = choose_from_complex_candidates(
            yes_pool, Questions.FaceLocalComplexity
        )
    elif no_pool:
        selected_face = choose_from_complex_candidates(
            no_pool, Questions.FaceLocalComplexity
        )
    else:
        return None, None, False, 0.0

    return _ask(25, Questions.Question25, selected_face, bounds)

#                          RANDOM QUESTION 26
def randomQuestion26():
    global map
    return _ask(26, Questions.Question26, map)

# ==========================================
#                   RANDOM QUESTION 27
# ==========================================
def randomQuestion27():
    """
    Global wrapper for Question 27. 
    Note: This question doesn't need a random face input because 
    it evaluates the whole map to find the 'max'.
    """
    global map
    if question27_largest_area_ratio_filter:
        regions = sorted(complex_faces(), key=lambda face: face.area, reverse=True)
        if len(regions) < 2 or regions[1].area <= 0:
            return failureOutput
        ratio = regions[0].area / regions[1].area
        if not 1.3 <= ratio <= 1.5:
            return failureOutput
    # We only pass 'map'. 
    # Passing 'face' here would cause the "2 given but 1 expected" error.
    return _ask(27, Questions.Question27, map)

#                          RANDOM QUESTION 28
def randomQuestion28():
    global map
    # Pick two distinct random faces
    ranked = sorted(
        complex_faces(), key=Questions.FaceLocalComplexity, reverse=True
    )
    pool = ranked[:max(2, int(np.ceil(len(ranked) * 0.65)))]
    fa, fb = np.random.choice(pool, size=2, replace=False)
    return _ask(28, Questions.Question28, fa, fb)

#                          RANDOM QUESTION 29
def randomQuestion29():
    """
    Randomly selects two distinct bounded faces to find the maximum 
    number of intermediate regions between them.
    """
    global map
    # Ensure we have at least 2 bounded faces
    bounded_faces = [f for f in map.faces[1:] if f.bounded]
    if len(bounded_faces) < 2:
        return failureOutput
        
    fa, fb = np.random.choice(bounded_faces, size=2, replace=False)
    
    # Calls the new sampling-based Question 29
    return Questions.Question29(fa, fb, map)


def _adjacent_face_pairs():
    pairs = []
    seen = set()
    for fa in complex_faces():
        for edge in fa.edges:
            fb = edge.reverse.leftFace
            if not fb or not fb.bounded or fb == fa:
                continue
            key = tuple(sorted((id(fa), id(fb))))
            if key not in seen and Questions.FaceUnion(fa, fb) is not False:
                seen.add(key)
                pairs.append((fa, fb))
    return pairs


def randomQuestion30():
    candidates = _adjacent_face_pairs()
    if not candidates:
        return failureOutput
    for index in np.random.permutation(len(candidates)):
        fa, fb = candidates[index]
        result = _ask(30, Questions.Question30, fa, fb, True)
        if result[0] and 4 <= len(result[2]) <= 6:
            return result
    return failureOutput


def randomQuestion31():
    edges = internal_adjacent_edges()
    if not edges:
        return failureOutput
    edge = edges[np.random.choice(len(edges))]
    return _ask(31, Questions.Question31, edge.tail, edge.head, randomCodes(1), map)


def randomQuestion32():
    candidates = [face for face in complex_faces() if face.numSides >= 5]
    face = choose_from_complex_candidates(candidates, Questions.FaceLocalComplexity)
    if face is None:
        return failureOutput
    return _ask(32, Questions.Question32, face)


def randomQuestion33():
    pairs = _adjacent_face_pairs()
    if not pairs:
        return failureOutput
    yes_candidates = []
    no_candidates = []
    for fa, fb in pairs:
        union = Questions.FaceUnion(fa, fb)
        for fc in complex_faces():
            if fc in (fa, fb) or min(union.numSides, fc.numSides) < 5:
                continue
            difference = abs(union.numSides - fc.numSides)
            if difference == 0:
                yes_candidates.append((fa, fb, fc))
            elif difference in (1, 2):
                no_candidates.append((fa, fb, fc))
    candidates = (
        yes_candidates if yes_candidates and (not no_candidates or np.random.random() < 0.5)
        else no_candidates
    )
    if not candidates:
        return failureOutput
    fa, fb, fc = candidates[np.random.choice(len(candidates))]
    return _ask(33, Questions.Question33, fa, fb, fc)


def randomQuestion34():
    faces = complex_faces()
    if len(faces) < 2:
        return failureOutput
    pairs = list(combinations(faces, 2))
    directed_pairs = pairs + [(second, first) for first, second in pairs]
    for index in np.random.permutation(len(directed_pairs)):
        fc, fd = directed_pairs[index]
        vc = min(fc.trueVertices[1:], key=lambda vertex: vertex.p.x)
        vd = max(fd.trueVertices[1:], key=lambda vertex: vertex.p.y)
        result = _ask(34, Questions.Question34, fc, fd, vc, vd, map)
        if result[0]:
            return result
    return failureOutput


def randomCodes(k):
    if k==1:
        return np.random.choice(2520)
    else:
        return np.random.choice(2520,size=k)

# return items a,b,c such that b.value >= a.value*ratio and c.value >= b.value*ratio
# all such triples <a,b,c> are equiprobable.

def RandomSeparatedTriples(list,values,ratio):      
#    values,list = zip(*sorted(zip(values,list))) Keeps giving erratic bugs
    values, list = Questions.parallelSort(values,list)
    n = len(list)
    num1step, num2step = CountTriples(values,ratio)
    if num2step[0] == 0:
        return False,False,False,False
    t2 = sum(num2step)
    prob = [0]*n
    for i in range(n):
        prob[i] = num2step[i]/t2
    first = np.random.choice(n,p=prob)
    for i in range(n):
        if values[i] < values[first]*ratio:
            num1step[i]=0
    t1 = sum(num1step)
    prob = [0]*n
    for i in range(n):
        prob[i] = num1step[i]/t1
    second = np.random.choice(n,p=prob)
    for i in range(second+1,n):
        if values[i] >= values[second]*ratio:
           istart = i
           break
    prob = [0]*(istart) + [1/(n-istart)]*(n-istart)
    third = np.random.choice(n,p=prob) 
    return True,list[first],list[second],list[third]   
        
    

def CountTriples(values,ratio):
    n = len(values)
    i=0
    j=1
    num1step=[0]*n    # num1step[i] The number of values j such that value[j] >= ratio*value[i]
    while (j < n):
        if values[j] >= ratio*values[i]:
            num1step[i] = n-j
            i += 1
        else:
            j += 1
    sum = [0]*n
    for i in range(2,n):
        sum[n-i] = sum[n+1-i]+num1step[n-i]
    i=0
    j=1
    num2step=[0]*n    # num2step[i] = The number of pairs j,k such that i,j,k is a valid triple
    while (j < n):
        if values[j] >= ratio*values[i]:
            num2step[i] = sum[j]
            i += 1
        else:
            j += 1
    return num1step, num2step


#generate problems by a specific complexity tier
def get_questions_by_tier(mymap, tier, count):

    global map
    map = mymap

    buckets = {
        "easy": [1, 8, 9, 13, 26, 27],
        "medium": [2, 3, 5, 6, 7, 10, 11, 14, 15, 16, 20, 23, 24, 25, 28],
        "hard": [4, 12, 17, 18, 19, 21, 22, 29] 
    }
    
    selected_questions = []
    pool = buckets[tier].copy()
    np.random.shuffle(pool)
    
    while len(selected_questions) < count and len(pool) > 0:
        key = pool.pop()
        # triesRandomQuestion is your existing function that runs the logic
        qaPair = triesRandomQuestion(key) 
        if qaPair[0] != False:
            selected_questions.append(qaPair)
            
    return selected_questions
