"""Shared label anchors for the five-region tutorial, in diagram coordinates."""
import Graph
import DrawGraph

TUTORIAL_LABEL_POSITIONS = {
    "A": (0.659718, 0.649145),
    "B": (0.391870, 0.750294),
    "C": (0.260553, 0.421780),
    "D": (0.569946, 0.278784),
    "E": (0.791512, 0.473333),
}


def apply_tutorial_label_positions(res_map, label_cache):
    """Update the existing cache so base maps and overlays share the anchors."""
    for face in res_map.faces:
        if not face.bounded or face.letter not in TUTORIAL_LABEL_POSITIONS:
            continue
        point = Graph.Vector(*TUTORIAL_LABEL_POSITIONS[face.letter])
        clearance = min(
            Graph.distPointFromEdge(point, edge.tail.p, edge.head.p)
            for edge in face.edges
        )
        label_cache[getattr(face, "_cache_idx", id(face))] = (point, clearance)


def draw_tutorial_faces(draw, res_map, label_cache):
    DrawGraph.InitColors(alpha=153)
    black = (0, 0, 0, 255)
    font_bold = DrawGraph.GetSystemFont(80)
    font_small = DrawGraph.GetSystemFont(45)

    for face in res_map.faces:
        if not face.bounded:
            continue
        pts = [DrawGraph.V2P(v.p) for v in face.vertices]
        fill_color = DrawGraph.colors[getattr(face, "color", 0)]
        draw.polygon(pts, fill=fill_color, outline=black, width=4)

        if hasattr(face, "_cache_idx") and face._cache_idx in label_cache:
            lp, d = label_cache[face._cache_idx]
        else:
            lp, d = Graph.LetterPointFace(face)
        coords = DrawGraph.V2P(lp)
        font = font_bold if d > 0.06 else font_small
        draw.text(coords, face.letter, fill=black, font=font, anchor="mm")

    for edge in res_map.edges:
        if (
            getattr(getattr(edge, "leftFace", None), "bounded", False)
            and not getattr(getattr(edge.reverse, "leftFace", None), "bounded", False)
        ):
            draw.line(
                [DrawGraph.V2P(edge.tail.p), DrawGraph.V2P(edge.head.p)],
                fill=black,
                width=8,
            )

