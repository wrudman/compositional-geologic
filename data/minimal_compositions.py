"""
minimal_compositions.py

Each map question solved with ONLY the seven human verbs:

    vertex   neighbors   draw   intersect   merge   measure   sort

There are no other tool calls. Call setup(map) once before using anything here.

NOTES ON TWO BROKEN QUESTIONS
The two questions that cannot be expressed with the current seven verbs are
marked UNSUPPORTED below, with explanations of what would need to be added.

Q21 relied on measure(p, what="x") and measure(p, what="y") for a
signed-area calculation. Those options were removed. No remaining verb
produces a raw coordinate value, so Q21 is unsupported.

Q24 relied on measure(..., what="gap") for region-to-region distance.
Gap was removed. Q24 is unsupported.

"""

from tools_human import (
    vertex, neighbors, draw, intersect, merge, measure, sort,
    setup,
)


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

def Q8(all_regions, k):
    return [r for r in all_regions if measure(r, what="sides") == k]

def Q9(X):
    return measure(X, what="sides")

def Q10(p, u, v, w):
    return sort([u, v, w], by="distance", reference=p)

def Q11(X):
    return sort(vertex(X, which="all"), by="angle", reference=X)

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
    """UNSUPPORTED. Needs raw x/y coordinates (removed from measure).
    Restore measure(what="x"/"y") or add an orientation(u,v,w) verb."""
    raise NotImplementedError("Q21 needs x/y coordinates; not in current vocabulary.")

def Q22(p, q, u, v):
    return intersect(draw(p, q), draw(u, v))

def Q23(all_regions, axis):
    lo, hi = ("leftmost", "rightmost") if axis == 0 else ("bottommost", "topmost")
    return [
        (X, Y)
        for X in all_regions
        for Y in all_regions
        if X != Y and vertex(X, which=lo) == vertex(Y, which=hi)
    ]

def Q24(A, B, C):
    """UNSUPPORTED. Needs region-to-region distance (gap; removed from measure).
    Restore measure(what="gap") or add a closer(A, B, C) verb."""
    raise NotImplementedError("Q24 needs gap distance; not in current vocabulary.")