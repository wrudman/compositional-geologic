"""Shared generation-only checks for visually clear infinite-line crossings.

The 5% minimum smaller-side area fraction is a provisional stimulus constraint,
not a mathematical definition of crossing. Existing items are never relabeled.
"""
import math

DEFAULT_MIN_SMALLER_AREA_FRACTION = 0.05


def _area(points):
    if len(points) < 3:
        return 0.0
    return abs(sum(a[0]*b[1]-b[0]*a[1]
                   for a, b in zip(points, points[1:]+points[:1]))) / 2


def _clip_half_plane(points, signed_distance, sign):
    """Clip a simple polygon; collinear connectors cancel in signed area.

    A concave polygon may produce several pieces. The returned closed walk can
    connect them along the clipping line; shoelace area sums their total area.
    """
    out = []
    for a, b in zip(points, points[1:]+points[:1]):
        da, db = sign*signed_distance(a), sign*signed_distance(b)
        inside_a, inside_b = da >= 0, db >= 0
        if inside_a:
            out.append(a)
        if inside_a != inside_b:
            t = da/(da-db)
            out.append((a[0]+t*(b[0]-a[0]), a[1]+t*(b[1]-a[1])))
    return out


def assess_line_polygon(points, a, b,
                        min_smaller_area_fraction=DEFAULT_MIN_SMALLER_AREA_FRACTION,
                        distance_tolerance=1e-9):
    """Classify crossing/touch/overlap and reject unclear cuts for generation.

    Disjoint negatives are valid. Point-only contact or a positive-length
    boundary overlap is rejected, even when another part is crossed. For a
    crossing, each half-plane must contain at least 5% of the polygon's area.
    Fractions refer to this region's area, not the diagram's total area.
    """
    if not 0 < min_smaller_area_fraction <= 0.5:
        raise ValueError('min_smaller_area_fraction must be in (0, 0.5].')
    points = [(float(x), float(y)) for x, y in points]
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    if not all(math.isfinite(v) for p in points+[a,b] for v in p):
        raise ValueError('Nonfinite polygon/line coordinates.')
    total = _area(points)
    dx, dy = b[0]-a[0], b[1]-a[1]
    length = math.hypot(dx, dy)
    if length <= distance_tolerance or total <= 0:
        raise ValueError('Line and polygon must be nondegenerate.')
    def distance(p):
        return (dx*(p[1]-a[1])-dy*(p[0]-a[0]))/length
    distances = [distance(p) for p in points]
    positive = any(v > distance_tolerance for v in distances)
    negative = any(v < -distance_tolerance for v in distances)
    overlap = any(abs(distance(p)) <= distance_tolerance and
                  abs(distance(q)) <= distance_tolerance and
                  math.dist(p,q) > distance_tolerance
                  for p,q in zip(points, points[1:]+points[:1]))
    on_line = any(abs(v) <= distance_tolerance for v in distances)
    classification = ('boundary_overlap' if overlap else
                      'crossing' if positive and negative else
                      'point_touch' if on_line else 'disjoint')
    fraction = None
    if positive and negative:
        left = _area(_clip_half_plane(points, distance, 1))
        right = _area(_clip_half_plane(points, distance, -1))
        if abs(left+right-total) > max(total*1e-8,1e-12):
            raise ValueError('Clipped areas do not recover polygon area.')
        fraction = min(left,right)/total
    acceptable = (classification == 'disjoint' or
                  classification == 'crossing' and
                  fraction+1e-12 >= min_smaller_area_fraction)
    reason = (None if acceptable else
              'boundary_overlap' if overlap else
              'point_touch' if classification == 'point_touch' else
              'smaller_piece_below_minimum_area_fraction')
    return {'classification':classification, 'acceptable':acceptable,
            'smaller_area_fraction':fraction,
            'minimum_smaller_area_fraction':min_smaller_area_fraction,
            'rejection_reason':reason}
