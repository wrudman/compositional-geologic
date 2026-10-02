"""Structured, instance-level reference programs for the 24 active questions.

The representation is deliberately an expression tree rather than Python
source.  It preserves grounding operations, supports nested composition, and
does not impose an arbitrary execution order on independent subexpressions.
"""

from __future__ import annotations

import re
from typing import Any


SCHEMA_VERSION = "geo_reference_program_v2"
TOOL_VERSION = "2026-10-02-batch-measure"


def indexed_label(prefix, index):
    return prefix + str(index).translate(str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉"))
ACTIVE_QUESTION_IDS = (
    1, 2, 4, 5, 8, 9, 10, 11, 12, 13, 14, 15,
    16, 18, 19, 20, 21, 22, 23, 26, 30, 31, 32, 33,
)
EXPERIMENTAL_QUESTION_IDS = ()


def entity(entity_type: str, name: str) -> dict[str, Any]:
    return {"node": "entity", "entity_type": entity_type, "name": name}


def variable(name: str) -> dict[str, str]:
    return {"node": "variable", "name": name}


def literal(value: Any) -> dict[str, Any]:
    return {"node": "literal", "value": value}


def call(function: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
    node = {"node": "call", "function": function, "args": list(args)}
    if kwargs:
        node["kwargs"] = kwargs
    return node


def operation(operator: str, *args: Any, **attributes: Any) -> dict[str, Any]:
    node = {"node": "operation", "operator": operator, "args": list(args)}
    node.update(attributes)
    return node


def _region(letter: str) -> dict[str, Any]:
    return entity("region", letter)


def _regions(text: str) -> list[str]:
    return re.findall(r"\b[A-Z]\b", text)


def _vertex(description: str) -> dict[str, Any]:
    """Translate one generated vertex description into a Find call."""
    description = description.strip().rstrip(".")

    match = re.fullmatch(
        r"the vertex at the (bottom left|bottom right|top right|top left) "
        r"of the overall diagram",
        description,
    )
    if match:
        return call(
            "find", entity("frame", "frame"),
            object=literal("vertex"),
            which=literal(match.group(1).replace(" ", "_")),
        )

    match = re.fullmatch(
        r"the (leftmost|rightmost|topmost|bottommost) vertex of ([A-Z])",
        description,
    )
    if match:
        return call(
            "find", _region(match.group(2)),
            object=literal("vertex"), which=literal(match.group(1))
        )

    match = re.fullmatch(
        r"the (bottom left|bottom right|top left|top right) vertex of ([A-Z])",
        description,
    )
    if match:
        return call(
            "find", _region(match.group(2)),
            object=literal("vertex"),
            which=literal(match.group(1).replace(" ", "_")),
        )

    match = re.fullmatch(
        r"the vertex of ([A-Z]) with the (sharpest|widest) angle",
        description,
    )
    if match:
        return call(
            "find", _region(match.group(1)),
            object=literal("vertex"), which=literal(match.group(2))
        )

    match = re.fullmatch(
        r"the vertex(?: on the (left|right|top|bottom) edge of the frame| "
        r"not on the frame) where regions (.+?) meet(?: and no other labeled "
        r"region meets)?",
        description,
    )
    if match:
        letters = _regions(match.group(2))
        kwargs = {
            "object": literal("vertex"),
            "on_frame": literal(match.group(1) is not None),
        }
        return call("find", *[_region(letter) for letter in letters], **kwargs)

    raise ValueError(f"Unsupported vertex description: {description!r}")


def _let_vertex_bindings(question_text: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"Let (v[₀₁₂₃₄₅₆₇₈₉]+) be (.*?)\.(?=\s*(?:Let v[₀₁₂₃₄₅₆₇₈₉]+|Starting|Which|"
        r"Consider|Following|Order|Does|From))",
        re.DOTALL,
    )
    return [
        {"name": name, "expression": _vertex(description)}
        for name, description in pattern.findall(question_text)
    ]


def _edge(description: str) -> dict[str, Any]:
    description = description.strip().rstrip(".")
    match = re.fullmatch(
        r"the edge of ([A-Z]) that meets (?:region ([A-Z])|regions (.+)|"
        r"the outside of the frame)",
        description,
        flags=re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"Unsupported edge description: {description!r}")
    owner = _region(match.group(1).upper())
    if "outside of the frame" in description.lower():
        meeting_objects = [entity("outside", "Outside")]
    elif match.group(2):
        meeting_objects = [_region(match.group(2).upper())]
    else:
        meeting_objects = [
            _region(letter) for letter in _regions(match.group(3).upper())
        ]
    return call(
        "find", owner, *meeting_objects, object=literal("edge")
    )


def _union_parts(question_text: str) -> list[str]:
    match = re.search(
        r"Let U be the union of regions ([A-Z][^.]+)\.", question_text
    )
    if not match:
        raise ValueError("Could not find union definition.")
    return _regions(match.group(1))


def _count_nodes(value: Any, node_kind: str) -> int:
    if isinstance(value, dict):
        count = int(value.get("node") == node_kind)
        return count + sum(_count_nodes(item, node_kind) for item in value.values())
    if isinstance(value, list):
        return sum(_count_nodes(item, node_kind) for item in value)
    return 0


def _batch_measurements(node):
    """Use one batch call where a reference previously repeated a measurement.

    v2 operations associate values with candidates by input index:
    all_equal(values), filter_by_values(candidates, values, equals), and
    argmax_by_values(candidates, values). These are mental/list operations,
    not additional tools.
    """
    if isinstance(node, list):
        return [_batch_measurements(value) for value in node]
    if not isinstance(node, dict):
        return node
    node = {key: _batch_measurements(value) for key, value in node.items()}
    if node.get("node") != "operation":
        return node
    args = node.get("args", [])
    if node.get("operator") == "equal" and len(args) == 2:
        a, b = args
        if (a.get("function") == b.get("function") == "measure"
                and a.get("kwargs") == b.get("kwargs")
                and len(a["args"]) == len(b["args"]) == 1):
            return operation("all_equal", call("measure", [a["args"][0], b["args"][0]], **a["kwargs"]))
    if node.get("operator") == "filter":
        predicate = node.get("predicate", {})
        if predicate.get("operator") == "equal":
            measured, expected = predicate["args"]
            if measured.get("function") == "measure":
                return operation("filter_by_values", args[0],
                                 call("measure", args[0], **measured["kwargs"]), expected)
    if node.get("operator") == "argmax" and node.get("key", {}).get("function") == "measure":
        # Bind a computed candidate collection so it is evaluated only once.
        candidates = variable("candidates")
        return operation("let", args[0], name="candidates", body=operation(
            "argmax_by_values", candidates,
            call("measure", candidates, **node["key"]["kwargs"])))
    return node


def _program(
    question_id: int,
    expression: dict[str, Any],
    bindings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    program = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "level": "instance",
        "question_id": question_id,
        "bindings": bindings or [],
        "return": _batch_measurements(expression),
    }
    # This is an AST-size measure (primitive call sites), not a dynamic trace
    # count.  A call site inside a filter/comprehension can execute repeatedly.
    program["tool_call_site_count"] = _count_nodes(program, "call")
    program["description_resolution_count"] = sum(
        1
        for node in _walk_nodes(program)
        if node.get("node") == "operation"
        and node.get("operator") == "resolve_description"
    )
    return program


def _walk_nodes(value: Any):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk_nodes(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_nodes(item)


def build_reference_program(question_id: int, question_text: str) -> dict[str, Any]:
    """Build the complete structured reference for one generated instance."""
    if question_id not in ACTIVE_QUESTION_IDS + EXPERIMENTAL_QUESTION_IDS:
        raise ValueError(f"Question {question_id} is not registered.")

    letters = _regions(question_text)
    all_regions = entity("collection", "all_labeled_regions")

    if question_id == 1:
        return _program(1, call("neighbors", _region(letters[0]), literal("edge")))
    if question_id == 2:
        return _program(2, operation(
            "equal",
            call("measure", _region(letters[0]), what=literal("edge_count")),
            call("measure", _region(letters[1]), what=literal("edge_count")),
        ))
    if question_id == 4:
        bindings = _let_vertex_bindings(question_text)
        face = re.search(r"boundary of region ([A-Z])", question_text).group(1)
        ccw = "counterclockwise" in question_text
        return _program(4, call(
            "neighbors", _region(face), literal("ordered"),
            start=variable("v₁"), go_counterclockwise=literal(ccw),
        ), bindings)
    if question_id == 5:
        body = operation(
            "unordered_unique_pairs",
            operation(
                "flat_map",
                all_regions,
                body=call("neighbors", variable("region"), literal("vertex")),
            ),
        )
        return _program(5, body)
    if question_id == 8:
        k = int(re.search(r"have (\d+) edges", question_text).group(1))
        return _program(8, operation(
            "filter", all_regions,
            predicate=operation(
                "equal",
                call("measure", variable("region"), what=literal("edge_count")),
                literal(k),
            ),
        ))
    if question_id == 9:
        return _program(9, call(
            "measure", _region(letters[0]), what=literal("edge_count")
        ))
    if question_id == 10:
        bindings = _let_vertex_bindings(question_text)
        return _program(10, call(
            "sort", [variable(binding["name"]) for binding in bindings[1:]],
            by=literal("distance"), reference=variable("v₁"),
        ), bindings)
    if question_id == 11:
        region = re.search(r"Region ([A-Z]) has", question_text).group(1)
        angle_matches = re.findall(
            r"(a[₀₁₂₃₄₅₆₇₈₉]+) is the angle at (.*?)(?=;|\. Order)", question_text
        )
        bindings = [
            {"name": label, "expression": _vertex(description)}
            for label, description in angle_matches
        ]
        sorted_vertices = call(
            "sort",
            [variable(label) for label, _ in angle_matches],
            by=literal("angle"),
            reference=_region(region),
        )
        return _program(11, operation(
            "return_labels_for_ordered_objects",
            sorted_vertices,
            labels=[label for label, _ in angle_matches],
        ), bindings)
    if question_id == 12:
        match = re.search(r"Let e₁ be (.*?)\. Extend", question_text)
        bindings = [{"name": "e₁", "expression": _edge(match.group(1))}]
        return _program(12, call(
            "intersect",
            call("draw", variable("e₁"), kind=literal("full")),
            literal("faces"),
        ), bindings)
    if question_id == 13:
        bindings = _let_vertex_bindings(question_text)
        return _program(13, call("neighbors", variable("v₁")), bindings)
    if question_id in (14, 15, 16):
        union_regions = _union_parts(question_text)
        bindings = [{"name": "U", "expression": call(
            "merge", *[_region(name) for name in union_regions]
        )}]
        if question_id == 14:
            expression = call(
                "measure", variable("U"), what=literal("edge_count")
            )
        elif question_id == 15:
            expression = call("neighbors", variable("U"), literal("edge"))
        else:
            listed = re.search(
                r"Order regions (.*?) from smallest", question_text
            ).group(1)
            names = _regions(listed)
            items = [variable("U") if name == "U" else _region(name) for name in names]
            expression = call("sort", items, by=literal("area"))
        return _program(question_id, expression, bindings)
    if question_id == 18:
        bindings = _let_vertex_bindings(question_text)
        return _program(18, call(
            "intersect", call("draw", variable("v₁"), variable("v₂")),
            literal("faces"),
        ), bindings)
    if question_id == 19:
        bindings = _let_vertex_bindings(question_text)
        direction = {
            "horizontally to the right": "right",
            "vertically upward": "up",
            "horizontally to the left": "left",
            "vertically downward": "down",
        }
        label = next(value for phrase, value in direction.items() if phrase in question_text)
        return _program(19, call(
            "intersect", call("draw", variable("v₁"), literal(label)),
            literal("faces"),
        ), bindings)
    if question_id == 20:
        bindings = _let_vertex_bindings(question_text)
        by = "left_right" if "left to right" in question_text else "bottom_top"
        return _program(20, call(
            "sort", [variable(binding["name"]) for binding in bindings],
            by=literal(by),
        ), bindings)
    if question_id == 21:
        bindings = _let_vertex_bindings(question_text)
        return _program(21, call(
            "measure", variable("v₁"), variable("v₂"), variable("v₃"),
            what=literal("orientation"),
        ), bindings)
    if question_id == 22:
        bindings = _let_vertex_bindings(question_text)
        return _program(22, call(
            "intersect",
            call("draw", variable("v₁"), variable("v₂")),
            call("draw", variable("v₃"), variable("v₄")),
        ), bindings)
    if question_id == 23:
        horizontal = "leftmost" in question_text
        lo, hi = (
            ("leftmost", "rightmost") if horizontal
            else ("bottommost", "topmost")
        )
        return _program(23, operation(
            "filter_region_pairs", all_regions,
            predicate=operation(
                "equal",
                call(
                    "find", variable("first"),
                    object=literal("vertex"), which=literal(lo),
                ),
                call(
                    "find", variable("second"),
                    object=literal("vertex"), which=literal(hi),
                ),
            ),
            exclude_equal=True,
        ))
    if question_id == 24:
        match = re.search(
            r"closer to ([A-Z]): ([A-Z]) or ([A-Z])", question_text
        )
        reference, first, second = match.groups()
        return _program(24, operation(
            "argmin",
            [_region(first), _region(second)],
            key=call(
                "measure", _region(reference), variable("candidate"),
                what=literal("distance"),
            ),
        ))
    if question_id == 25:
        return _program(25, operation(
            "greater_than",
            call("measure", _region(letters[0]), what=literal("frame_edge_count")),
            literal(0),
        ))
    if question_id == 26:
        return _program(26, call(
            "measure", entity("frame", "frame"), what=literal("regions")
        ))
    if question_id == 27:
        return _program(27, operation(
            "last", call("sort", all_regions, by=literal("area"))
        ))
    if question_id == 28:
        match = re.search(
            r"Is region ([A-Z]) entirely above or entirely below region ([A-Z])",
            question_text,
        )
        first, second = match.groups()
        return _program(28, operation(
            "relative_vertical_order",
            _region(first), _region(second),
            ordered=call(
                "sort", [_region(first), _region(second)],
                by=literal("bottom_top"),
            ),
        ))

    if question_id == 30:
        union_regions = _union_parts(question_text)
        bindings = [
            {"name": "U", "expression": call("merge", *[_region(name) for name in union_regions])},
            {"name": "v₁", "expression": call(
                "find", variable("U"), object=literal("vertex"), which=literal("bottommost")
            )},
        ]
        return _program(30, call(
            "neighbors", variable("U"), literal("ordered"), start=variable("v₁"),
            go_counterclockwise=literal(False),
        ), bindings)
    if question_id == 31:
        match = re.search(r"Let e₁ be (.*?)\. Extend", question_text)
        bindings = [{"name": "e₁", "expression": _edge(match.group(1))}]
        crossed = call("intersect", call("draw", variable("e₁"), kind=literal("full")), literal("faces"))
        return _program(31, operation(
            "argmax", crossed,
            key=call("measure", variable("candidate"), what=literal("edge_count")),
        ), bindings)
    if question_id == 32:
        face = re.search(r"share an edge with region ([A-Z])", question_text).group(1)
        return _program(32, operation(
            "argmax", call("neighbors", _region(face), literal("edge")),
            key=call("measure", variable("candidate"), what=literal("area")),
        ))
    if question_id == 33:
        union_regions = _union_parts(question_text)
        other = re.search(r"U and region ([A-Z])", question_text).group(1)
        bindings = [{"name": "U", "expression": call("merge", *[_region(name) for name in union_regions])}]
        return _program(33, operation(
            "equal",
            call("measure", variable("U"), what=literal("edge_count")),
            call("measure", _region(other), what=literal("edge_count")),
        ), bindings)
    if question_id == 34:
        bindings = _let_vertex_bindings(question_text)
        right = call("intersect", call("draw", variable("v₁"), literal("right")), literal("faces"))
        down = call("intersect", call("draw", variable("v₂"), literal("down")), literal("faces"))
        return _program(34, operation("set_intersection", right, down), bindings)

    raise AssertionError("Active question dispatch is incomplete.")


def validate_active_coverage() -> None:
    """Static guard: dispatch and declared active ids must remain synchronized."""
    if len(ACTIVE_QUESTION_IDS) != 24 or len(set(ACTIVE_QUESTION_IDS)) != 24:
        raise ValueError("Reference program registry must contain 24 unique ids.")


def build_reference_program_from_inputs(
    question_id: int, *inputs: Any
) -> dict[str, Any]:
    """Build a reference AST from generator inputs before question text exists."""
    import Questions

    all_regions = entity("collection", "all_labeled_regions")

    def described_vertex(vertex_obj, code, face=None):
        description = (
            Questions.identifyVertexForQ11(vertex_obj, face, code)
            if face is not None
            else Questions.identifyVertex(vertex_obj, code)
        )
        if not description:
            raise ValueError("Vertex has no valid generated description.")
        return _vertex(description)

    def vertex_bindings(vertices, codes):
        return [
            {
                "name": indexed_label("v", index + 1),
                "expression": described_vertex(vertex_obj, code),
            }
            for index, (vertex_obj, code) in enumerate(zip(vertices, codes))
        ]

    if question_id == 1:
        (face,) = inputs
        return _program(1, call("neighbors", _region(face.letter), literal("edge")))
    if question_id == 2:
        first, second = inputs
        return _program(2, operation(
            "equal",
            call("measure", _region(first.letter), what=literal("edge_count")),
            call("measure", _region(second.letter), what=literal("edge_count")),
        ))
    if question_id == 4:
        face, start, ccw, code = inputs
        bindings = [{"name": "v₁", "expression": described_vertex(start, code, face)}]
        return _program(4, call(
            "neighbors", _region(face.letter), literal("ordered"),
            start=variable("v₁"), go_counterclockwise=literal(bool(ccw)),
        ), bindings)
    if question_id == 5:
        return _program(5, operation(
            "unordered_unique_pairs",
            operation(
                "flat_map", all_regions,
                body=call("neighbors", variable("region"), literal("vertex")),
            ),
        ))
    if question_id == 8:
        _map, k = inputs
        return _program(8, operation(
            "filter", all_regions,
            predicate=operation(
                "equal",
                call("measure", variable("region"), what=literal("edge_count")),
                literal(int(k)),
            ),
        ))
    if question_id == 9:
        (face,) = inputs
        return _program(9, call(
            "measure", _region(face.letter), what=literal("edge_count")
        ))
    if question_id == 10:
        if len(inputs) == 3:
            p, targets, codes = inputs
            vertices = [p] + list(targets)
        else:
            p, u, v, w, *codes = inputs
            vertices = [p, u, v, w]
        bindings = vertex_bindings(vertices, codes)
        return _program(10, call(
            "sort", [variable(binding["name"]) for binding in bindings[1:]],
            by=literal("distance"), reference=variable("v₁"),
        ), bindings)
    if question_id == 11:
        face, codes = inputs
        vertices = face.trueVertices[1:]
        labels = [indexed_label("a", i + 1) for i in range(len(vertices))]
        bindings = [
            {
                "name": label,
                "expression": described_vertex(vertex_obj, code, face),
            }
            for label, vertex_obj, code in zip(labels, vertices, codes)
        ]
        ordered = call(
            "sort", [variable(label) for label in labels],
            by=literal("angle"), reference=_region(face.letter),
        )
        return _program(11, operation(
            "return_labels_for_ordered_objects", ordered, labels=labels
        ), bindings)
    if question_id == 12:
        va, vb, code, _map = inputs
        descriptions = Questions.identifyEdgeTexts(va, vb)
        if not descriptions:
            raise ValueError("Edge has no valid generated description.")
        description = Questions.decode(descriptions, code)
        bindings = [{"name": "e₁", "expression": _edge(description)}]
        return _program(12, call(
            "intersect",
            call("draw", variable("e₁"), kind=literal("full")),
            literal("faces"),
        ), bindings)
    if question_id == 13:
        vertex_obj, code = inputs
        bindings = [{"name": "v₁", "expression": described_vertex(vertex_obj, code)}]
        return _program(13, call("neighbors", variable("v₁")), bindings)
    if question_id in (14, 15):
        union_regions = list(inputs[0]) if isinstance(inputs[0], (list, tuple)) else list(inputs[:2])
        bindings = [{"name": "U", "expression": call(
            "merge", *[_region(face.letter) for face in union_regions]
        )}]
        expression = (
            call("measure", variable("U"), what=literal("edge_count"))
            if question_id == 14
            else call("neighbors", variable("U"), literal("edge"))
        )
        return _program(question_id, expression, bindings)
    if question_id == 16:
        face_entries, _map = inputs
        union_pair = next(
            (entry for entry in face_entries if isinstance(entry, list)),
            None,
        )
        if union_pair is None:
            raise ValueError("Q16 requires exactly one region union.")
        union_regions = union_pair
        bindings = [{"name": "U", "expression": call(
            "merge", *[_region(face.letter) for face in union_regions]
        )}]
        items = [
            variable("U") if isinstance(entry, list) else _region(entry.letter)
            for entry in face_entries
        ]
        return _program(16, call("sort", items, by=literal("area")), bindings)
    if question_id == 20 and len(inputs) == 3:
        vertices, direction, codes = inputs
        bindings = vertex_bindings(vertices, codes)
        return _program(20, call(
            "sort", [variable(binding["name"]) for binding in bindings],
            by=literal("left_right" if direction == 0 else "bottom_top"),
        ), bindings)
    if question_id in (18, 20, 21, 22):
        vertex_count = {18: 2, 20: 3, 21: 3, 22: 4}[question_id]
        vertices = inputs[:vertex_count]
        if question_id == 18:
            codes = inputs[vertex_count:vertex_count * 2]
        elif question_id in (20, 21):
            codes = inputs[-vertex_count:]
        else:
            codes = inputs[vertex_count:]
        bindings = vertex_bindings(vertices, codes)
        if question_id == 18:
            expression = call(
                "intersect", call("draw", variable("v₁"), variable("v₂")),
                literal("faces"),
            )
        elif question_id == 20:
            direction = inputs[3]
            expression = call(
                "sort", [variable("v₁"), variable("v₂"), variable("v₃")],
                by=literal("left_right" if direction == 0 else "bottom_top"),
            )
        elif question_id == 21:
            expression = call(
                "measure", variable("v₁"), variable("v₂"), variable("v₃"),
                what=literal("orientation"),
            )
        else:
            expression = call(
                "intersect",
                call("draw", variable("v₁"), variable("v₂")),
                call("draw", variable("v₃"), variable("v₄")),
            )
        return _program(question_id, expression, bindings)
    if question_id == 19:
        vertex_obj, direction, code, _map = inputs
        bindings = [{"name": "v₁", "expression": described_vertex(vertex_obj, code)}]
        label = {0: "right", 1: "up", 2: "left", 3: "down"}[int(direction)]
        return _program(19, call(
            "intersect", call("draw", variable("v₁"), literal(label)),
            literal("faces"),
        ), bindings)
    if question_id == 23:
        direction, _map = inputs
        lo, hi = (
            ("leftmost", "rightmost")
            if int(direction) == 0
            else ("bottommost", "topmost")
        )
        return _program(23, operation(
            "filter_region_pairs", all_regions,
            predicate=operation(
                "equal",
                call("find", variable("first"), object=literal("vertex"), which=literal(lo)),
                call("find", variable("second"), object=literal("vertex"), which=literal(hi)),
            ),
            exclude_equal=True,
        ))
    if question_id == 24:
        reference, first, second = inputs
        return _program(24, operation(
            "argmin", [_region(first.letter), _region(second.letter)],
            key=call(
                "measure", _region(reference.letter), variable("candidate"),
                what=literal("distance"),
            ),
        ))
    if question_id == 25:
        face = inputs[0]
        return _program(25, operation(
            "greater_than",
            call("measure", _region(face.letter), what=literal("frame_edge_count")),
            literal(0),
        ))
    if question_id == 26:
        return _program(26, call(
            "measure", entity("frame", "frame"), what=literal("regions")
        ))
    if question_id == 27:
        return _program(27, operation(
            "last", call("sort", all_regions, by=literal("area"))
        ))
    if question_id == 28:
        first, second = inputs
        return _program(28, operation(
            "relative_vertical_order",
            _region(first.letter), _region(second.letter),
            ordered=call(
                "sort", [_region(first.letter), _region(second.letter)],
                by=literal("bottom_top"),
            ),
        ))
    if question_id == 30:
        first, second, _clockwise = inputs
        union_regions = list(first) if isinstance(first, (list, tuple)) else [first, second]
        bindings = [
            {"name": "U", "expression": call("merge", *[_region(face.letter) for face in union_regions])},
            {"name": "v₁", "expression": call(
                "find", variable("U"), object=literal("vertex"), which=literal("bottommost")
            )},
        ]
        return _program(30, call(
            "neighbors", variable("U"), literal("ordered"), start=variable("v₁"),
            go_counterclockwise=literal(False),
        ), bindings)
    if question_id == 31:
        va, vb, code, _map = inputs
        descriptions = Questions.identifyEdgeTexts(va, vb)
        if not descriptions:
            raise ValueError("Edge has no valid generated description.")
        bindings = [{"name": "e₁", "expression": _edge(Questions.decode(descriptions, code))}]
        crossed = call("intersect", call("draw", variable("e₁"), kind=literal("full")), literal("faces"))
        return _program(31, operation(
            "argmax", crossed,
            key=call("measure", variable("candidate"), what=literal("edge_count")),
        ), bindings)
    if question_id == 32:
        (face,) = inputs
        return _program(32, operation(
            "argmax", call("neighbors", _region(face.letter), literal("edge")),
            key=call("measure", variable("candidate"), what=literal("area")),
        ))
    if question_id == 33:
        first, second, other = inputs
        union_regions = list(first) if isinstance(first, (list, tuple)) else [first, second]
        bindings = [{"name": "U", "expression": call(
            "merge", *[_region(face.letter) for face in union_regions]
        )}]
        return _program(33, operation(
            "equal",
            call("measure", variable("U"), what=literal("edge_count")),
            call("measure", _region(other.letter), what=literal("edge_count")),
        ), bindings)
    if question_id == 34:
        first_face, second_face, _first_vertex, _second_vertex, _map = inputs
        bindings = [
            {"name": "v₁", "expression": call(
                "find", _region(first_face.letter), object=literal("vertex"), which=literal("leftmost")
            )},
            {"name": "v₂", "expression": call(
                "find", _region(second_face.letter), object=literal("vertex"), which=literal("topmost")
            )},
        ]
        right = call("intersect", call("draw", variable("v₁"), literal("right")), literal("faces"))
        down = call("intersect", call("draw", variable("v₂"), literal("down")), literal("faces"))
        return _program(34, operation("set_intersection", right, down), bindings)

    raise ValueError(f"No structured input builder for Q{question_id}.")
