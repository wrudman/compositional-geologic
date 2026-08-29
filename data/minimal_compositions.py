"""
minimal_compositions.py

Type-level reference compositions for every implemented question in
``Questions.py``, using ONLY the seven public human verbs:

    find   neighbors   draw   intersect   merge   measure   sort

There are no other tool calls. Call setup(map) once before using anything here.

Q3, Q6, and Q17 are commented out in ``Questions.py``.  Q7 and Q34 are
implemented there but are not in the current random-question pool.  They are
still represented below so this file covers the whole implemented bank.

An ``UNSUPPORTED`` function means the question genuinely cannot be expressed
with the current vocabulary; its docstring states the smallest missing mode.

"""

from tools_human import (
    find, neighbors, draw, intersect, merge, measure, sort,
    setup,
)


# Live ``def QuestionN`` functions in Questions.py.  The three commented-out
# question types (3, 6, 17) deliberately do not appear here.
IMPLEMENTED_QUESTION_IDS = (
    1, 2, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
    18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
    30, 31, 32, 33, 34,
)

# Question types expressible exactly with the current seven verbs.
SUPPORTED_QUESTION_IDS = tuple(
    q for q in IMPLEMENTED_QUESTION_IDS if q not in {7, 28, 29}
)
UNSUPPORTED_QUESTION_IDS = (7, 28, 29)


def Q1(X):
    return neighbors(X, "edge")

def Q2(A, B):
    return measure(A, what="sides") == measure(B, what="sides")

def Q4(face, v, go_counterclockwise):
    return neighbors(face, "ordered", start=v,
                     go_counterclockwise=go_counterclockwise)

def Q5(all_regions):
    seen, pairs = set(), []
    for r in all_regions:
        for nb in neighbors(r, "vertex"):
            key = tuple(sorted([r.letter, nb.letter]))
            if key not in seen:
                seen.add(key)
                pairs.append((r, nb))
    return pairs

def Q7(all_regions):
    """UNSUPPORTED: needs disconnected boundary-component counting.

    ``neighbors`` reports that a region meets the outside, but it does not
    report whether that contact consists of two or more disconnected edges.
    Add ``measure(region, what="frame_contact_components")`` (or an
    equivalent edge-component mode) to support Q7.
    """
    raise NotImplementedError(
        "Q7 needs the number of disconnected frame-contact components."
    )

def Q8(all_regions, k):
    return [r for r in all_regions if measure(r, what="sides") == k]

def Q9(X):
    return measure(X, what="sides")

def Q10(p, u, v, w):
    return sort([u, v, w], by="distance", reference=p)

def Q11(X):
    return sort(find(X, object="vertex", which="all"), by="angle", reference=X)

def Q12(va, vb):
    return intersect(draw(va, vb, kind="full"), "faces")

def Q13(p):
    return neighbors(p)

def Q14(A, B):
    return measure(merge(A, B), what="sides")

def Q15(A, B):
    return neighbors(merge(A, B), "edge")

def Q16(region_list):
    return sort(region_list, by="area")

def Q18(p, q):
    return intersect(draw(p, q), "faces")

def Q19(p, direction):
    label = {0: "right", 1: "up", 2: "left", 3: "down"}[direction]
    return intersect(draw(p, label), "faces")

def Q20(u, v, w, axis):
    return sort([u, v, w], by=("left_right" if axis == 0 else "bottom_top"))

def Q21(u, v, w):
    return measure(u, v, w, what="orientation")

def Q22(p, q, u, v):
    return intersect(draw(p, q), draw(u, v))

def Q23(all_regions, axis):
    lo, hi = ("leftmost", "rightmost") if axis == 0 else ("bottommost", "topmost")
    return [
        (X, Y)
        for X in all_regions
        for Y in all_regions
        if X != Y
        and find(X, object="vertex", which=lo)
        == find(Y, object="vertex", which=hi)
    ]

def Q24(A, B, C):
    return min([B, C], key=lambda region: measure(A, region, what="distance"))

def Q25(X):
    return measure(X, what="frame_edge_count") > 0

def Q26():
    return measure("frame", what="regions")

def Q27(all_regions):
    return sort(all_regions, by="area")[-1]

def Q28(A, B):
    """UNSUPPORTED: needs vertical extents, not centroid ordering.

    ``sort(..., by="bottom_top")`` orders regions by one representative y
    value.  Q28 asks whether *every point* of A is above/below *every point*
    of B, which requires comparing their topmost and bottommost extents.
    Add a region relation such as ``measure(A, B, what="vertical_relation")``.
    """
    raise NotImplementedError("Q28 needs whole-region vertical separation.")

def Q29(A, B):
    """UNSUPPORTED: needs optimization over arbitrary interior endpoints.

    The seven verbs can evaluate one specified segment, but cannot enumerate
    or optimize over every segment joining an interior point of A to one in B.
    Add an optimization mode returning the maximum number of intermediate
    regions (and preserve the question's non-scraping robustness rule).
    """
    raise NotImplementedError("Q29 needs continuous segment-path optimization.")

def Q30(A, B):
    U = merge(A, B)
    start = find(U, object="vertex", which="bottommost")
    return neighbors(U, "ordered", start=start, go_counterclockwise=False)

def Q31(edge_1):
    crossed = intersect(draw(edge_1, kind="full"), "faces")
    return max(crossed, key=lambda region: measure(region, what="edge_count"))

def Q32(X):
    adjacent = neighbors(X, "edge")
    return max(adjacent, key=lambda region: measure(region, what="area"))

def Q33(A, B, C):
    U = merge(A, B)
    return (
        measure(U, what="edge_count")
        == measure(C, what="edge_count")
    )

def Q34(v1, v2):
    right_ray_faces = intersect(draw(v1, "right"), "faces")
    down_ray_faces = intersect(draw(v2, "down"), "faces")
    return [face for face in right_ray_faces if face in down_ray_faces]
