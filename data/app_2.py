import streamlit as st
st.set_page_config(layout="wide", page_title="Geometry Reasoning Survey")

import streamlit.components.v1 as components
import json, pickle, os, random, re, math, html, hashlib
import uuid
from PIL import Image, ImageDraw
from io import BytesIO
import base64
from datetime import datetime  # NEW: for action log timestamps

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:
    psycopg = None
    Jsonb = None

import Graph
import BuildRandomMap
import DrawGraph
from visual_tools_annotation import (
    AnnotationSession,
    tool_draw_points_line,
    tool_highlight_region,
    draw_union,
    get_shared_edges,
    tool_label_vertex,
    tool_label_angle,
    highlight_edge,
    tool_draw_axis_line,
    tool_draw_extended_edge,
    draw_line_label,
    tool_label_edge_list,
)


def tool_draw_labeled_vertex_segment(draw, img, manager, v1, v1_label, v2, v2_label, line_label):
    """Render two labeled vertices and their segment as one undoable action."""
    tool_label_vertex(draw, img, manager, v1, v1_label)
    tool_label_vertex(draw, img, manager, v2, v2_label)
    tool_draw_points_line(draw, img, manager, v1.p, v2.p, extend=False, label=line_label)


def tool_draw_labeled_vertex_axis(draw, img, manager, vertex, vertex_label, direction, line_label):
    """Render a labeled origin vertex and its axis line as one undoable action."""
    tool_label_vertex(draw, img, manager, vertex, vertex_label)
    tool_draw_axis_line(draw, img, manager, vertex.p, direction=direction, label=line_label)


def tool_draw_labeled_vertex_ray(draw, img, manager, vertex, vertex_label, direction, line_label):
    """Render a labeled origin vertex and a cardinal ray to the frame."""
    tool_label_vertex(draw, img, manager, vertex, vertex_label)
    px, py = DrawGraph.V2P(vertex.p)
    endpoints = {
        "left": (100, py),
        "right": (900, py),
        "up": (px, 100),
        "down": (px, 900),
    }
    end_pos = endpoints[direction]
    draw.line([(px, py), end_pos], fill=(0, 0, 255, 255), width=6)
    draw_line_label(draw, manager, (px, py), end_pos, line_label, (0, 0, 255, 255))


def _extend_math_line_to_frame(a, b, max_x=1.0, max_y=1.0):
    """Return the two frame intersections of the infinite line through a-b."""
    dx, dy = b.x - a.x, b.y - a.y
    candidates = []
    if abs(dx) > 1e-9:
        candidates.extend(((0.0 - a.x) / dx, (max_x - a.x) / dx))
    if abs(dy) > 1e-9:
        candidates.extend(((0.0 - a.y) / dy, (max_y - a.y) / dy))
    intersections = []
    for t in candidates:
        x, y = a.x + t * dx, a.y + t * dy
        if -1e-6 <= x <= max_x + 1e-6 and -1e-6 <= y <= max_y + 1e-6:
            intersections.append((t, Graph.Vector(x, y)))
    if len(intersections) < 2:
        return a, b
    intersections.sort(key=lambda item: item[0])
    return intersections[0][1], intersections[-1][1]


def tool_draw_compositional_edge_extension(
    draw,
    img,
    manager,
    source_a,
    source_b,
    label=None,
    color=(0, 0, 255, 255),
    width=5,
):
    """Draw a grouped visual edge as a frame-to-frame line.

    The label is placed on the longer exposed extension, following the
    compositional survey, rather than over the source edge midpoint.
    """
    frame_a, frame_b = _extend_math_line_to_frame(source_a, source_b)
    pa, pb = DrawGraph.V2P(frame_a), DrawGraph.V2P(frame_b)
    source_pa, source_pb = DrawGraph.V2P(source_a), DrawGraph.V2P(source_b)
    draw.line([pa, pb], fill=color, width=width)
    if not label:
        return

    def nearest_source(frame_point):
        return min(
            (source_pa, source_pb),
            key=lambda source: (
                (frame_point[0] - source[0]) ** 2
                + (frame_point[1] - source[1]) ** 2
            ),
        )

    exposed_pairs = [(pa, nearest_source(pa)), (pb, nearest_source(pb))]
    outer, inner = max(
        exposed_pairs,
        key=lambda pair: (
            (pair[0][0] - pair[1][0]) ** 2
            + (pair[0][1] - pair[1][1]) ** 2
        ),
    )
    anchor_x = outer[0] * 0.58 + inner[0] * 0.42
    anchor_y = outer[1] * 0.58 + inner[1] * 0.42
    dx, dy = pb[0] - pa[0], pb[1] - pa[1]
    length = math.hypot(dx, dy) or 1.0
    tx = anchor_x - (dy / length) * 18
    ty = anchor_y + (dx / length) * 18
    font = DrawGraph.GetSystemFont(35)
    bbox = draw.textbbox((tx, ty), str(label), font=font, anchor="mm")
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        (tx, ty),
        str(label),
        fill=color,
        font=font,
        anchor="mm",
        stroke_width=3,
        stroke_fill=(255, 255, 255, 255),
    )
    manager.reserve(tx, ty, text_w, text_h)


def tool_draw_label_edge_list_extension(
    draw,
    img,
    manager,
    res_map,
    edge_segments,
    edge_label,
    source_a,
    source_b,
    label=None,
):
    """Draw an extended line and retain its named source edge as one action."""
    # Match compositional_survey.py's layer order: the thin blue extension is
    # subordinate to the thick cyan source edge.
    tool_draw_compositional_edge_extension(
        draw,
        img,
        manager,
        source_a,
        source_b,
        label=label,
    )
    tool_label_edge_list(
        draw,
        img,
        manager,
        res_map,
        edge_segments,
        edge_label,
        (0, 255, 255, 235),
    )

# print("\n🚀 === [Python] Streamlit Render Loop Triggered ===")  # COMMENTED OUT

DISPLAY_SIDE = 400
MATH_SCALE = 800.0
DEFAULT_PARTICIPANT_ID = "local_demo"
SURVEY_VERSION = "multi_page_with_incremental_tool_tutorial_v19_12_question_forms"
RESPONSE_SCHEMA_VERSION = "3.5"
SURVEY_CONDITION = "annotation"
CODE_VERSION = (
    os.environ.get("RENDER_GIT_COMMIT")
    or os.environ.get("GIT_COMMIT")
    or "local"
)
TIME_LIMIT_SECONDS = None
SURVEY_QUESTION_COUNT = 12
RESULTS_DIR = os.path.join(os.getcwd(), "survey_results")
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
QUESTION_FORM_ASSIGNMENT_VERSION = "compositional_questions_v2_12_question_forms"
SURVEY_FORM_QUESTION_IDS = {
    "A": {
        "15", "23", "24",
        "12", "21", "11", "4", "25", "13",
        "9", "18", "26",
    },
    "B": {
        "19", "2", "1",
        "5", "16", "27", "20", "28", "14",
        "8", "10", "22",
    },
}
ANSWER_HINTS_HUMAN = {
    "number": "Enter a number.",
    "single_region": "Enter one region label, e.g. A.",
    "region_set": "List all matching regions in any order, separated by commas, e.g. A, B, C. If none, write None.",
    "region_sequence": "List the regions in order, separated by commas, e.g. A, B, C.",
    "region_pairs": "List each pair in parentheses, in any order, e.g. (A, B), (C, D). If none, write None.",
    "ordered_items": "List the named objects in order, separated by commas.",
    "number_sequence": "List the item numbers in order, separated by commas, e.g. 1, 2, 3.",
}

QUESTION_HINT_TYPES = {
    "1": "region_set",
    "4": "region_sequence",
    "5": "region_pairs",
    "7": "region_set",
    "8": "region_set",
    "9": "number",
    "10": "ordered_items",
    "11": "ordered_items",
    "12": "region_set",
    "13": "region_set",
    "14": "number",
    "15": "region_set",
    "16": "region_sequence",
    "18": "region_sequence",
    "19": "region_sequence",
    "20": "ordered_items",
    "23": "region_pairs",
    "26": "number",
    "27": "single_region",
    "29": "number",
}

REGION_HIGHLIGHT = (150, 150, 150, 190)
DEMO_QUESTION = {
    "question_id": "demo_tools",
    "seed": 18,
    "num_regions": 5,
    "question_text": "Tool practice",
    "answer_placeholder": "",
}
DEMO_STEPS = {
    2: {
        "title": "Select one Region, one Angle, one Vertex, and one Edge.",
        "definition": "",
        "context": "",
        "instruction": "",
        "success": "Great — you identified all four kinds of objects.",
        "expected_action": None,
        "tool_mode": "Region",
    },
    3: {
        "title": "Highlight",
        "definition": "Highlight adds a persistent mark to a selected object.",
        "context": (
            "If you'd like, you can also try highlighting an angle, edge, or region. "
            "Choose the corresponding type under Selection, select one object, and click RUN."
        ),
        "context_after_success": True,
        "instruction": "Choose **Highlight**. Under **Selection**, choose **Vertex** and select the **leftmost vertex of Region B**. Then click **RUN**.",
        "success": "Good — the highlighted point is the leftmost vertex of Region B.",
        "expected_action": "commit_vertex",
        "tool_mode": "Vertex",
    },
    4: {
        "title": "Connecting two vertices",
        "definition": "A line can connect two selected vertices.",
        "context": "",
        "context_after_success": True,
        "instruction": (
            "Choose **Draw Line** and keep **Segment** selected.\n\n"
            "The **leftmost vertex of Region B** is already selected for you.\n\n"
            "Under **Selection**, keep **Vertex** selected and click the "
            "**rightmost vertex of Region D**.\n\n"
            "Then click **RUN**."
        ),
        "success": "Good — {line_label} connects the two selected vertices.",
        "expected_action": "confirm_connection",
        "tool_mode": "Vertex",
    },
    5: {
        "title": "Ray from a vertex",
        "definition": "A ray starts at a selected vertex and travels in one direction to the frame.",
        "context": "You can also draw rays upward, downward, or leftward from any selected vertex.",
        "context_after_success": True,
        "instruction": (
            "Keep **Draw Line** selected and choose **Right**.\n\n"
            "The **leftmost vertex of Region B** is already selected for you.\n\n"
            "Then click **RUN**."
        ),
        "success": "Good — {line_label} is a rightward ray from the selected vertex.",
        "expected_action": "commit_ray",
        "tool_mode": "Vertex",
    },
    6: {
        "title": "Extending an edge",
        "definition": "Extend edge continues a selected edge in both directions as a straight line.",
        "context": "The extension stays on the same straight line as the selected edge.",
        "context_after_success": True,
        "instruction": (
            "Keep **Draw Line** selected and choose **Extend edge**.\n\n"
            "Under **Selection**, choose **Edge** and select the edge shared by **Regions B and C**.\n\n"
            "Then click **RUN**."
        ),
        "success": "Good — {line_label} extends the selected edge in both directions.",
        "expected_action": "extend_edge",
        "tool_mode": "Edge",
    },
    7: {
        "title": "Measuring distance",
        "definition": "Measure Distance finds the distance between two selected vertices.",
        "context": (
            "If you'd like, you can also try measuring an angle or the area of a region. "
            "Choose the corresponding option under Measure, then select one angle or one region."
        ),
        "context_after_success": True,
        "instruction": (
            "Choose **Measure** and keep **Distance** selected.\n\n"
            "The **leftmost vertex of Region B** is already selected for you.\n\n"
            "Under **Selection**, keep **Vertex** selected and click the "
            "**rightmost vertex of Region D**.\n\n"
            "Then click **RUN**. The result will appear in **Output** on the right."
        ),
        "success": "Good — the Output in the lower-right corner shows the measured distance.",
        "expected_action": "measure_distance",
        "tool_mode": "Vertex",
    },
    8: {
        "title": "Union of two regions",
        "definition": "A union combines two neighboring regions into one larger region.",
        "context": "",
        "context_after_success": True,
        "instruction": (
            "Finally, choose **Merge**.\n\n"
            "Under **Selection**, choose **Region** and select **Regions A and E**. "
            "The regions share an edge, so they can be merged.\n\n"
            "Then click **RUN**."
        ),
        "success": "Good — the union treats the two neighboring regions as one larger region.",
        "expected_action": "execute_union",
        "tool_mode": "Region",
    },
}
DEMO_CLOCKWISE_STEP = 2.1
DEMO_FRAME_STEP = 2.2
DEMO_TOTAL_STEPS = max(DEMO_STEPS)
DEMO_REVIEW_STEP = DEMO_TOTAL_STEPS + 1
PRACTICE_DIRECTION_DEFINITIONS = """
**Clockwise:** movement around a circle in the top, right, bottom, left direction.

**Counterclockwise:** movement around a circle in the top, left, bottom, right direction.
"""

PRACTICE_FRAME_DEFINITIONS = """
**Frame:** the diagram's outer boundary.

**Outside of the frame:** the area outside the diagram frame.
"""

PRACTICE_ENTITY_DEFINITIONS = """
**Vertex:** a point where two or more edges meet.

**Edge:** a line segment that forms part of a region boundary.

**Region:** one enclosed area of the diagram.

**Angle:** the angle inside a region at a vertex, formed by the two edges that meet there.
"""

PRACTICE_UNION_DEFINITION = """
**Union:** a combination of two neighboring regions treated as one larger region.
"""

DEFINITIONS_TEXT = (
    PRACTICE_DIRECTION_DEFINITIONS
    + PRACTICE_FRAME_DEFINITIONS
    + PRACTICE_ENTITY_DEFINITIONS
    + PRACTICE_UNION_DEFINITION
)

TOOL_GUIDE_TEXT = """
**Highlight**

- Select one vertex, angle, edge, or region, then click **RUN** to leave a persistent annotation.
- For a shared edge, choose which adjacent region's boundary you mean.

**Measure**

- Select two vertices to measure their distance.
- Select one angle to measure its size.
- Select one region to measure its area.

**Draw Line**

- Select two vertices to draw a segment.
- Select one vertex and a direction to draw a ray.
- Select one edge to extend it in both directions as a straight line.

**Merge**

- Select two neighboring regions that share an edge, then click **RUN** to create Region U.
"""

TOOLS_GUIDE_TEXT = """
First choose an object type under Selection and select objects from the diagram. Then choose Highlight, Measure, Draw Line, or Merge under Tool.

Highlight marks the selected vertex, angle, edge, or region.

Measure can return distance, angle, or area, depending on the selection.

Draw Line can create a segment, a cardinal ray, or extend a selected edge.

Merge combines two selected neighboring regions.

Use Undo if you want to remove your most recent annotation.

Use Clear All to clear the drawing workspace and Output, not your answer.
"""
FALLBACK_QUESTION_BANK = [
    {
        "question_id": "q001_region_h_angle_sort",
        "seed": 42,
        "num_regions": 8,
        "question_text": (
            "Region H has 4 vertices: (1) the vertex at the top right of the overall diagram; "
            "(2) the leftmost vertex of H; (3) the meeting point of H, C, and I; "
            "(4) the meeting point of H, I, and A with the outside of the frame. "
            "Sort these in increasing order by the size of the interior angle at each corner."
        ),
        "answer_type": "fill_in_the_blank",
        "answer_placeholder": "Example: 2, 4, 1, 3",
    },
    {
        "question_id": "q002_total_regions",
        "seed": 35,
        "num_regions": 8,
        "question_text": "How many regions are there in the diagram in total?",
        "answer_type": "fill_in_the_blank",
        "answer_placeholder": "Enter a number",
    },
    {
        "question_id": "q003_regions_bordering_b",
        "seed": 73,
        "num_regions": 8,
        "question_text": (
            "Which regions border region B along an edge? "
            "Bordering along an edge is not the same as bordering along a vertex."
        ),
        "answer_type": "fill_in_the_blank",
        "answer_placeholder": "Example: A, C, F",
    },
]

ATTENTION_CHECK_QUESTION = {
    "question_id": "attention_check_select_2",
    "pair_id": "attention_check",
    "seed": 42,
    "num_regions": 8,
    "diagram_complexity": "attention_check",
    "question_text": (
        "Regardless of the diagram shown below, please select option 2 "
        "for this question."
    ),
    "answer": "2",
    "answer_type": "multiple_choice",
    "answer_placeholder": "",
    "choices": ["1", "2", "3", "4", "5"],
    "image_path": "",
    "image_path_color": "",
    "image_path_bw": "",
    "is_attention_check": True,
}


def add_attention_check(questions):
    # Normalize both new and previously saved sessions to the midpoint.
    questions = [q for q in questions if not q.get("is_attention_check")]
    insert_index = len(questions) // 2
    questions.insert(insert_index, dict(ATTENTION_CHECK_QUESTION))
    return questions


def find_dataset_path():
    explicit_path = st.query_params.get("dataset_path") or os.environ.get("GEOMETRY_SURVEY_DATASET")
    if explicit_path and os.path.exists(explicit_path):
        return explicit_path

    candidates = []
    for root, _, files in os.walk(os.getcwd()):
        if "dataset_24_balanced.json" in files:
            candidates.append(os.path.join(root, "dataset_24_balanced.json"))
    if candidates:
        return sorted(candidates)[-1]

    legacy_candidates = []
    for root, _, files in os.walk(os.getcwd()):
        if "dataset_25_balanced.json" in files:
            legacy_candidates.append(os.path.join(root, "dataset_25_balanced.json"))
    return sorted(legacy_candidates)[-1] if legacy_candidates else ""


def normalize_dataset_item(item: dict, item_index: int) -> dict:
    question = item.get("question", item)
    question_id = question.get("question_id", item.get("pair_id", f"q_{item_index:03d}"))
    return {
        "question_id": str(question_id),
        "pair_id": item.get("pair_id", f"pair_{item_index:03d}"),
        "seed": item.get("seed", question.get("seed", 42)),
        "num_regions": item.get("region_count", question.get("num_regions", 8)),
        "diagram_complexity": item.get("diagram_complexity", ""),
        "question_text": question.get("question_text", ""),
        "answer": question.get("answer", ""),
        "answer_type": question.get("answer_type", "fill_in_the_blank"),
        "answer_placeholder": question.get("answer_placeholder", ""),
        "choices": question.get("choices", []),
        "image_path": item.get("image_path", item.get("image_path_color", "")),
        "image_path_color": item.get("image_path_color", ""),
        "image_path_bw": item.get("image_path_bw", ""),
    }


def get_dataset_metadata(payload) -> dict:
    if not isinstance(payload, dict):
        return {
            "dataset_version": "fallback_or_legacy_list",
            "dataset_role": "unknown",
        }
    return {
        "dataset_version": payload.get("dataset_version", "unknown"),
        "dataset_role": payload.get("dataset_role", "unknown"),
        "generated_at": payload.get("generated_at", ""),
        "total_pairs": payload.get("total_pairs", ""),
        "region_count_quota": payload.get("region_count_quota", {}),
        "medium_region_counts_with_extra_diagram": payload.get("medium_region_counts_with_extra_diagram", []),
        "excluded_question_ids": payload.get("excluded_question_ids", []),
        "active_question_ids": payload.get("active_question_ids", []),
    }


def assigned_survey_form(participant_id: str) -> str:
    """Use the same deterministic A/B assignment as the compositional survey."""
    digest = hashlib.sha256(
        f"{QUESTION_FORM_ASSIGNMENT_VERSION}:{participant_id}".encode("utf-8")
    ).digest()
    return "A" if digest[0] % 2 == 0 else "B"


def load_question_bank(participant_id: str, survey_form: str):
    dataset_path = find_dataset_path()
    if not dataset_path:
        return FALLBACK_QUESTION_BANK, "", {
            "dataset_version": "fallback_question_bank",
            "dataset_role": "fallback",
        }

    with open(dataset_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    dataset_metadata = get_dataset_metadata(payload)
    raw_items = payload.get("items", payload if isinstance(payload, list) else [])
    normalized_items = [
        normalize_dataset_item(item, idx)
        for idx, item in enumerate(raw_items)
    ]
    normalized_items = [
        item for item in normalized_items
        if item.get("question_text") and item.get("seed") is not None
    ]
    if len(normalized_items) < SURVEY_QUESTION_COUNT:
        return FALLBACK_QUESTION_BANK, "", {
            "dataset_version": "fallback_question_bank",
            "dataset_role": "fallback",
            "source_dataset_path": dataset_path,
            "source_dataset_item_count": len(normalized_items),
        }

    form_ids = SURVEY_FORM_QUESTION_IDS.get(survey_form, set())
    selected_items = [
        item for item in normalized_items
        if str(item.get("question_id")) in form_ids
    ]
    if len(selected_items) != SURVEY_QUESTION_COUNT:
        selected_items = list(normalized_items)
        sampler = random.Random(f"{QUESTION_FORM_ASSIGNMENT_VERSION}:{participant_id}:fallback")
        sampler.shuffle(selected_items)
        selected_items = selected_items[: min(SURVEY_QUESTION_COUNT, len(selected_items))]
    else:
        sampler = random.Random(
            f"{QUESTION_FORM_ASSIGNMENT_VERSION}:{participant_id}:{survey_form}"
        )
        sampler.shuffle(selected_items)
    return selected_items, dataset_path, dataset_metadata


def _answer_matches_choices(answer, choices):
    answer_norm = str(answer).strip().lower()
    return bool(answer_norm) and answer_norm in {
        str(choice).strip().lower()
        for choice in choices
    }


def get_two_choice_options(question: dict):
    question_text = question.get("question_text", "")
    question_lower = question_text.lower()
    answer_text = str(question.get("answer", ""))

    explicit_choices = question.get("choices") or []
    if explicit_choices and _answer_matches_choices(answer_text, explicit_choices):
        return explicit_choices

    yes_no_question = re.match(
        r"^\s*(do|does|did|is|are|was|were|can|could|will|would|has|have)\b",
        question_lower,
    )
    if yes_no_question and answer_text.strip().lower() in {"yes", "no"}:
        return ["Yes", "No"]

    if (
        re.search(r"\bclockwise\s+or\s+counterclockwise\b", question_lower)
        or re.search(r"\bcounterclockwise\s+or\s+clockwise\b", question_lower)
        or re.search(r"\bcounter-clockwise\s+or\s+clockwise\b", question_lower)
        or re.search(r"\bclockwise\s+or\s+counter-clockwise\b", question_lower)
    ):
        if answer_text.strip().lower() in {"clockwise", "counterclockwise", "counter-clockwise"}:
            return ["Clockwise", "Counterclockwise"]

    if (
        re.search(r"\babove\s+or\s+below\b", question_lower)
        or re.search(r"\bbelow\s+or\s+above\b", question_lower)
    ):
        if answer_text.strip().lower() in {"above", "below"}:
            return ["Above", "Below"]
    return None


def normalized_answer_type(question: dict):
    if get_two_choice_options(question):
        return "two_choice"
    return "fill_in_the_blank"


def ordered_items_answer_hint(question):
    question_text = str(question.get("question_text", ""))
    match = re.search(r"\b([va])(_?\d+|[₀-₉]+)", question_text, flags=re.IGNORECASE)
    base_hint = ANSWER_HINTS_HUMAN["ordered_items"]
    if not match:
        return base_hint

    prefix, index_text = match.groups()
    if index_text.startswith("_"):
        examples = [f"{prefix}_{i}" for i in range(1, 4)]
    elif re.fullmatch(r"[₀-₉]+", index_text):
        subscript_digits = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
        examples = [f"{prefix}{str(i).translate(subscript_digits)}" for i in range(1, 4)]
    else:
        examples = [f"{prefix}{i}" for i in range(1, 4)]
    return f"{base_hint[:-1]}, e.g. {', '.join(examples)}."


def answer_hint_for(question):
    if normalized_answer_type(question) == "two_choice":
        return ""
    qid = str(question.get("question_id", ""))
    hint_type = QUESTION_HINT_TYPES.get(qid)
    if hint_type:
        if hint_type == "ordered_items":
            return ordered_items_answer_hint(question)
        return ANSWER_HINTS_HUMAN.get(hint_type, "")

    answer = str(question.get("answer", "")).strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", answer):
        return ANSWER_HINTS_HUMAN["number"]
    if re.fullmatch(r"[A-Z]", answer):
        return ANSWER_HINTS_HUMAN["single_region"]
    if answer.startswith("{("):
        return ANSWER_HINTS_HUMAN["region_pairs"]
    if answer.startswith("{") or answer.lower() == "none":
        return ANSWER_HINTS_HUMAN["region_set"]
    if answer.startswith("["):
        if re.search(r"v[₀-₉0-9]|a[₀-₉0-9]", answer):
            return ordered_items_answer_hint(question)
        if re.search(r"\d", answer):
            return ANSWER_HINTS_HUMAN["number_sequence"]
        return ANSWER_HINTS_HUMAN["region_sequence"]
    return ""


_SUBSCRIPT_DIGIT_TRANSLATION = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


def _normalize_answer_notation(value):
    text = str(value or "").translate(_SUBSCRIPT_DIGIT_TRANSLATION)
    return re.sub(
        r"\b([va])_?(?=\d)",
        lambda match: match.group(1).lower(),
        text,
        flags=re.IGNORECASE,
    )


def _answer_tokens(value):
    text = _normalize_answer_notation(value).strip()
    if not text:
        return []
    if text.lower() == "none":
        return ["none"]
    ignored_words = {
        "region", "regions", "vertex", "vertices", "angle", "angles",
        "edge", "edges", "object", "objects", "item", "items",
        "and", "or", "then", "the", "of", "frame",
    }
    return [
        token.lower()
        for token in re.findall(r"v[₀-₉0-9]+|a[₀-₉0-9]+|[A-Za-z]+|\d+(?:\.\d+)?", text)
        if token.lower() not in ignored_words
    ]


def _normalized_region_pairs(value):
    """Canonicalize unordered region pairs while preserving pair membership."""
    text = _normalize_answer_notation(value).strip()
    if text.lower() == "none":
        return [("none",)]

    pair_contents = re.findall(r"\(([^()]*)\)", text)
    if not pair_contents:
        return None

    pairs = []
    for content in pair_contents:
        tokens = [
            token.upper()
            for token in _answer_tokens(content)
            if len(token) == 1 and token.isalpha()
        ]
        if len(tokens) != 2 or tokens[0] == tokens[1]:
            return None
        pairs.append(tuple(sorted(tokens)))
    return sorted(pairs)


def _normalized_single_unwrapped_region_pair(value):
    """Accept ``A, B`` as shorthand only when exactly one pair is expected."""
    text = _normalize_answer_notation(value).strip()
    if not text or "(" in text or ")" in text:
        return None
    tokens = [
        token.upper()
        for token in _answer_tokens(text)
        if len(token) == 1 and token.isalpha()
    ]
    if len(tokens) != 2 or tokens[0] == tokens[1]:
        return None
    return [tuple(sorted(tokens))]


def _expand_ordered_item_shorthand(submitted_tokens, correct_tokens):
    """Allow 3,2,1 as shorthand for v3,v2,v1 (and likewise for angles)."""
    if not submitted_tokens or not all(token.isdigit() for token in submitted_tokens):
        return submitted_tokens
    correct_matches = [re.fullmatch(r"([va])(\d+)", token) for token in correct_tokens]
    if not correct_matches or any(match is None for match in correct_matches):
        return submitted_tokens
    prefixes = {match.group(1) for match in correct_matches}
    if len(prefixes) != 1:
        return submitted_tokens
    prefix = prefixes.pop()
    return [prefix + token for token in submitted_tokens]


def _ordered_item_prefixes(tokens):
    prefixes = set()
    for token in tokens:
        match = re.fullmatch(r"([va])\d+", token)
        if match:
            prefixes.add(match.group(1))
    return prefixes


def _answer_hint_type(question):
    qid = str(question.get("question_id", ""))
    hint_type = QUESTION_HINT_TYPES.get(qid)
    if hint_type:
        return hint_type
    answer = str(question.get("answer", "")).strip()
    if answer.startswith("{("):
        return "region_pairs"
    if answer.startswith("{") or answer.lower() == "none":
        return "region_set"
    if answer.startswith("["):
        if re.search(r"v[₀-₉0-9]|a[₀-₉0-9]", answer):
            return "ordered_items"
        if re.search(r"\d", answer):
            return "number_sequence"
        return "region_sequence"
    if re.fullmatch(r"\d+(?:\.\d+)?", answer):
        return "number"
    if re.fullmatch(r"[A-Z]", answer):
        return "single_region"
    return ""


def format_answer_for_feedback(question):
    answer = str(question.get("answer", "")).strip()
    if not answer:
        return ""
    if normalized_answer_type(question) == "two_choice":
        options = get_two_choice_options(question) or []
        for option in options:
            if str(option).strip().lower() == answer.lower():
                return str(option)
        return answer
    hint_type = _answer_hint_type(question)
    if answer.lower() == "none":
        return "None"
    if hint_type == "region_pairs":
        return answer.strip("{}[] ")
    if hint_type in {"region_set", "region_sequence", "ordered_items", "number_sequence"}:
        tokens = _answer_tokens(answer)
        if not tokens:
            return answer.strip("{}[] ")
        if hint_type in {"region_set", "region_sequence"}:
            tokens = [token.upper() if len(token) == 1 and token.isalpha() else token for token in tokens]
        return ", ".join(tokens)
    return answer


def answer_is_correct(question, answer):
    correct = _normalize_answer_notation(question.get("answer", "")).strip()
    if not correct:
        return None
    submitted = _normalize_answer_notation(answer).strip()
    if normalized_answer_type(question) == "two_choice":
        return submitted.lower() == correct.lower()
    hint_type = _answer_hint_type(question)
    if hint_type == "number":
        try:
            return float(submitted) == float(correct)
        except ValueError:
            return submitted.lower() == correct.lower()
    submitted_tokens = _answer_tokens(submitted)
    correct_tokens = _answer_tokens(correct)
    if hint_type == "region_pairs":
        submitted_pairs = _normalized_region_pairs(submitted)
        correct_pairs = _normalized_region_pairs(correct)
        if submitted_pairs is None and correct_pairs is not None and len(correct_pairs) == 1:
            submitted_pairs = _normalized_single_unwrapped_region_pair(submitted)
        return submitted_pairs is not None and submitted_pairs == correct_pairs
    if hint_type == "region_set":
        return sorted(submitted_tokens) == sorted(correct_tokens)
    if hint_type == "ordered_items":
        correct_prefixes = _ordered_item_prefixes(correct_tokens)
        submitted_prefixes = _ordered_item_prefixes(submitted_tokens)
        if correct_prefixes and submitted_prefixes and submitted_prefixes != correct_prefixes:
            return False
        submitted_tokens = _expand_ordered_item_shorthand(
            submitted_tokens,
            correct_tokens,
        )
        return submitted_tokens == correct_tokens
    if hint_type in {"region_sequence", "number_sequence"}:
        return submitted_tokens == correct_tokens
    return "".join(submitted.lower().split()) == "".join(correct.lower().split())


def _safe_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(value))
    return safe[:80] or DEFAULT_PARTICIPANT_ID


def get_participant_and_instance_ids() -> tuple[str, str]:
    """Return the person ID and the durable ID for this particular survey run.

    A recruitment link containing only ``participant_id`` intentionally maps to
    one stable run, so opening that link in another tab resumes the same survey.
    A caller can explicitly provide a different ``survey_instance`` when a new,
    separate attempt is required for the same participant.
    """
    raw_participant_id = st.query_params.get("participant_id") or st.query_params.get("pid")
    raw_survey_instance = st.query_params.get("survey_instance")

    if raw_participant_id:
        participant_id = _safe_id(raw_participant_id)
    elif raw_survey_instance:
        participant_id = _safe_id(raw_survey_instance)
    else:
        participant_id = _safe_id(
            f"participant_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        )

    survey_instance_id = _safe_id(raw_survey_instance or participant_id)
    st.session_state["participant_id"] = participant_id
    st.session_state["survey_instance_id"] = survey_instance_id
    return participant_id, survey_instance_id


PARTICIPANT_ID, SURVEY_INSTANCE_ID = get_participant_and_instance_ids()
SURVEY_FORM = assigned_survey_form(PARTICIPANT_ID)
QUESTION_BANK, DATASET_PATH, DATASET_METADATA = load_question_bank(
    PARTICIPANT_ID, SURVEY_FORM
)
QUESTION_BANK = add_attention_check(QUESTION_BANK)
PERSIST_FILE = f"/tmp/geo_session_{SURVEY_CONDITION}_{SURVEY_INSTANCE_ID}.pkl"
if not st.query_params.get("survey_instance"):
    next_params = {"survey_instance": SURVEY_INSTANCE_ID}
    if st.query_params.get("participant_id") or st.query_params.get("pid"):
        next_params["participant_id"] = PARTICIPANT_ID
    st.query_params.from_dict(next_params)
    st.rerun()

# ── NEW: Action Log Helpers ────────────────────────────────────────────────────

def _ts() -> str:
    """Return current timestamp string: YYYY-MM-DD HH:MM:SS.mmm"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _parse_ts(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")
    except Exception:
        return None


def seconds_since(timestamp: str) -> float:
    parsed = _parse_ts(timestamp)
    if not parsed:
        return 0.0
    return max(0.0, (datetime.now() - parsed).total_seconds())


def elapsed_between_timestamps(start: str, end: str):
    parsed_start = _parse_ts(start)
    parsed_end = _parse_ts(end)
    if not parsed_start or not parsed_end:
        return None
    return round(max(0.0, (parsed_end - parsed_start).total_seconds()), 3)


def format_elapsed(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def keep_session_query_params():
    # Replace the whole query string in one browser history update. Calling
    # clear() and then assigning separately can create a rapid pushState loop.
    st.query_params.from_dict({
        "participant_id": PARTICIPANT_ID,
        "survey_instance": SURVEY_INSTANCE_ID,
    })


def drawing_pad_component(html_code: str):
    """Serve the drawing pad as a real Streamlit component so Chrome accepts the bridge."""
    try:
        base = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        base = os.getcwd()
    comp_dir = os.path.join(base, "drawing_pad_comp")
    os.makedirs(comp_dir, exist_ok=True)
    index_path = os.path.join(comp_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html_code)
    return components.declare_component("drawing_pad_bridge", path=comp_dir)


def get_client_action_meta() -> dict:
    return {
        "client_timestamp": st.query_params.get("client_timestamp", ""),
        "client_elapsed_ms": st.query_params.get("client_elapsed_ms", ""),
        "click_x": st.query_params.get("bridge_click_x", ""),
        "click_y": st.query_params.get("bridge_click_y", ""),
    }


def demo_target_matches(data: dict, demo_step: int, detail: dict) -> bool:
    """Validate the requested practice object, not just the action type."""
    if demo_step not in set(DEMO_STEPS):
        return True
    if demo_step == 2:
        return True
    if demo_step == 3:
        face_b = next((f for f in data["session"].res_map.faces
                       if f.bounded and getattr(f, "letter", "") == "B"), None)
        if not face_b:
            return False
        min_x = min(v.p.x for v in face_b.vertices)
        valid_ids = {
            str(getattr(v, "num", id(v)))
            for v in face_b.vertices
            if abs(v.p.x - min_x) < 1e-9
        }
        return str(detail.get("vertex_id", "")) in valid_ids
    face_b = next((f for f in data["session"].res_map.faces
                   if f.bounded and getattr(f, "letter", "") == "B"), None)
    face_d = next((f for f in data["session"].res_map.faces
                   if f.bounded and getattr(f, "letter", "") == "D"), None)
    face_c = next((f for f in data["session"].res_map.faces
                   if f.bounded and getattr(f, "letter", "") == "C"), None)
    if not face_b or not face_c or not face_d:
        return False
    b_min_x = min(v.p.x for v in face_b.vertices)
    d_max_x = max(v.p.x for v in face_d.vertices)
    valid_starts = {str(v.num) for v in face_b.vertices if abs(v.p.x - b_min_x) < 1e-9}
    valid_ends = {str(v.num) for v in face_d.vertices if abs(v.p.x - d_max_x) < 1e-9}
    if demo_step == 4:
        return str(detail.get("from", "")) in valid_starts and str(detail.get("to", "")) in valid_ends
    if demo_step == 5:
        return str(detail.get("vertex_id", "")) in valid_starts
    if demo_step == 6:
        selected_endpoints = {str(detail.get("tail", "")), str(detail.get("head", ""))}
        shared_edge_ids = get_shared_edges(face_b, face_c)
        return any(
            id(edge) in shared_edge_ids
            and selected_endpoints == {
                str(getattr(edge.tail, "num", id(edge.tail))),
                str(getattr(edge.head, "num", id(edge.head))),
            }
            for edge in face_b.edges
        )
    if demo_step == 7:
        return (str(detail.get("from_vertex_id", "")) in valid_starts
                and str(detail.get("to_vertex_id", "")) in valid_ends)
    return set(detail.get("faces", [])) == {"A", "E"}


TUTORIAL_GUIDED_STAGES = (
    "selection",
    "clockwise",
    "frame",
    "highlight",
    "segment",
    "ray",
    "extend_edge",
    "measure_distance",
    "merge",
)


def tutorial_stage_for_step(step) -> str | None:
    return {
        DEMO_CLOCKWISE_STEP: "clockwise",
        DEMO_FRAME_STEP: "frame",
        2: "selection",
        3: "highlight",
        4: "segment",
        5: "ray",
        6: "extend_edge",
        7: "measure_distance",
        8: "merge",
    }.get(step)


def tutorial_step_entry(data: dict, stage: str) -> dict:
    summary = data.setdefault("tutorial_summary", {})
    steps = summary.setdefault("steps", {})
    return steps.setdefault(stage, {
        "completed": False,
        "completion_method": None,
        "used_completed_example": False,
        "tool_errors": 0,
        "started_at": None,
        "completed_at": None,
        "duration_seconds": None,
    })


def start_tutorial_step(data: dict, stage: str | None = None) -> dict | None:
    stage = stage or tutorial_stage_for_step(data.get("demo_step"))
    if not stage:
        return None
    entry = tutorial_step_entry(data, stage)
    if not entry.get("started_at"):
        entry["started_at"] = _ts()
    return entry


def mark_tutorial_step_completed(data: dict, stage: str | None = None) -> None:
    stage = stage or tutorial_stage_for_step(data.get("demo_step"))
    if not stage:
        return
    entry = start_tutorial_step(data, stage)
    completed_at = _ts()
    entry["completed"] = True
    entry["completion_method"] = (
        "completed_example" if entry.get("used_completed_example") else "independent"
    )
    entry["completed_at"] = completed_at
    entry["duration_seconds"] = elapsed_between_timestamps(
        entry.get("started_at"), completed_at
    )
    summary = data.setdefault("tutorial_summary", {})
    summary["completion_status"] = "in_progress"
    summary.setdefault("started_at", data.get("demo_start_time") or completed_at)


def mark_tutorial_tool_error(data: dict, stage: str | None = None) -> None:
    stage = stage or tutorial_stage_for_step(data.get("demo_step"))
    if not stage:
        return
    entry = start_tutorial_step(data, stage)
    entry["tool_errors"] = int(entry.get("tool_errors", 0) or 0) + 1


def summarize_annotation_tool_calls(calls: list[dict]) -> dict:
    valid_calls = [call for call in calls if isinstance(call, dict)]
    tool_counts = {}
    function_counts = {}
    tool_function_counts = {}
    error_count = 0
    for call in valid_calls:
        tool = str(call.get("tool", "unknown"))
        function = str(call.get("function", "unknown"))
        tool_counts[tool] = tool_counts.get(tool, 0) + 1
        function_counts[function] = function_counts.get(function, 0) + 1
        tool_function = f"{tool}.{function}"
        tool_function_counts[tool_function] = tool_function_counts.get(tool_function, 0) + 1
        if call.get("call_type") == "error" or call.get("function") == "error":
            error_count += 1
    return {
        "total_tool_calls": len(valid_calls),
        "tool_counts": dict(sorted(tool_counts.items())),
        "function_counts": dict(sorted(function_counts.items())),
        "tool_function_counts": dict(sorted(tool_function_counts.items())),
        "error_count": error_count,
    }


def refresh_annotation_tutorial_summary(data: dict) -> dict:
    summary = data.setdefault("tutorial_summary", {})
    steps = summary.setdefault("steps", {})
    metric_end = summary.get("completed_at") or _ts()
    summary["total_duration_seconds"] = elapsed_between_timestamps(
        summary.get("started_at"), metric_end
    )
    summary["guided_duration_seconds"] = elapsed_between_timestamps(
        summary.get("started_at"), summary.get("guided_completed_at")
    )
    summary["free_exploration_seconds"] = elapsed_between_timestamps(
        summary.get("guided_completed_at"),
        summary.get("free_exploration_completed_at")
        or (metric_end if summary.get("guided_completed_at") else None),
    )
    summary["total_steps"] = len(TUTORIAL_GUIDED_STAGES)
    summary["independently_completed_steps"] = sum(
        steps.get(stage, {}).get("completion_method") == "independent"
        for stage in TUTORIAL_GUIDED_STAGES
    )
    summary["completed_example_steps"] = sum(
        steps.get(stage, {}).get("completion_method") == "completed_example"
        for stage in TUTORIAL_GUIDED_STAGES
    )
    summary["skipped_steps"] = sum(
        steps.get(stage, {}).get("completion_method") == "skipped"
        for stage in TUTORIAL_GUIDED_STAGES
    )
    summary["total_tool_errors"] = sum(
        int(steps.get(stage, {}).get("tool_errors", 0) or 0)
        for stage in TUTORIAL_GUIDED_STAGES
    )
    summary.setdefault(
        "free_exploration_tool_calls",
        {"total_tool_calls": 0, "tool_counts": {}, "error_count": 0},
    )
    return summary


def mark_annotation_tutorial_completed(data: dict) -> None:
    summary = data.setdefault("tutorial_summary", {})
    completed_at = _ts()
    summary["completion_status"] = "completed"
    summary["completion_method"] = "guided_tutorial"
    summary["completed_at"] = completed_at
    summary.setdefault("started_at", data.get("demo_start_time") or completed_at)
    guided_completed_at = summary.get("guided_completed_at")
    if guided_completed_at:
        summary["free_exploration_completed_at"] = completed_at
        free_calls = []
        for entry in data.get("action_log", []):
            if entry.get("question_id") != DEMO_QUESTION["question_id"]:
                continue
            timestamp = entry.get("server_timestamp")
            if timestamp and timestamp < guided_completed_at:
                continue
            call = compositional_tool_call_from_action(entry, len(free_calls) + 1)
            if call is not None:
                free_calls.append(call)
        summary["free_exploration_tool_calls"] = summarize_annotation_tool_calls(free_calls)
    refresh_annotation_tutorial_summary(data)


def _action_geometry_context(data: dict, detail: dict) -> dict:
    """Resolve logged object IDs to replayable diagram coordinates."""
    session = data.get("session")
    res_map = getattr(session, "res_map", None)
    if res_map is None:
        return {}

    def vertex_record(vertex_id):
        if vertex_id in (None, "", "none"):
            return None
        vertex = next(
            (
                candidate for candidate in getattr(res_map, "vertices", [])
                if str(getattr(candidate, "num", id(candidate))) == str(vertex_id)
            ),
            None,
        )
        if vertex is None:
            return {"object_id": f"vertex:{vertex_id}", "vertex_id": str(vertex_id)}
        return {
            "object_id": f"vertex:{vertex_id}",
            "vertex_id": str(vertex_id),
            "coordinates": {
                "x": float(vertex.p.x),
                "y": float(vertex.p.y),
                "coordinate_system": "diagram",
            },
        }

    geometry = {}
    vertex_fields = {
        "vertex_id", "from_vertex_id", "to_vertex_id", "from", "to",
        "tail", "head", "tail_id", "head_id",
    }
    for field in vertex_fields:
        if field in detail:
            record = vertex_record(detail.get(field))
            if record is not None:
                geometry[field] = record
    for field in ("source_endpoints", "extended_endpoints"):
        endpoints = detail.get(field)
        if isinstance(endpoints, (list, tuple)) and len(endpoints) == 2:
            geometry[field] = {
                "coordinate_system": "diagram",
                "points": endpoints,
            }

    face_idx = detail.get("face_idx")
    face_label = detail.get("face")
    if face_idx is not None or face_label not in (None, "", "U"):
        face = next(
            (
                candidate for candidate in getattr(res_map, "faces", [])
                if (
                    face_idx is not None
                    and str(getattr(candidate, "_cache_idx", "")) == str(face_idx)
                )
                or (
                    face_idx is None
                    and str(getattr(candidate, "letter", "")) == str(face_label)
                )
            ),
            None,
        )
        if face is not None:
            label = getattr(face, "letter", detail.get("face", "?"))
            geometry["face"] = {
                "object_id": f"region:{label}",
                "face_idx": getattr(face, "_cache_idx", face_idx),
                "label": label,
                "vertices": [
                    vertex_record(getattr(vertex, "num", id(vertex)))
                    for vertex in getattr(face, "vertices", [])
                ],
            }
    source_faces = detail.get("faces")
    if isinstance(source_faces, (list, tuple)):
        geometry["source_faces"] = []
        for label in source_faces:
            face = next(
                (
                    candidate for candidate in getattr(res_map, "faces", [])
                    if str(getattr(candidate, "letter", "")) == str(label)
                ),
                None,
            )
            if face is None:
                continue
            geometry["source_faces"].append(
                {
                    "object_id": f"region:{label}",
                    "face_idx": getattr(face, "_cache_idx", None),
                    "label": str(label),
                    "vertices": [
                        vertex_record(getattr(vertex, "num", id(vertex)))
                        for vertex in getattr(face, "vertices", [])
                    ],
                }
            )
    return geometry


def log_action(data: dict, action_type: str, detail=None) -> None:
    """
    Append one entry to data['action_log'].
    Each entry includes both server timing and, when available, browser-side timing.
    This list is backend-only; never displayed to the user.
    """
    if "action_log" not in data:
        data["action_log"] = []
    if detail is None:
        detail = {}
    if not isinstance(detail, dict):
        detail = {"message": str(detail)}
    else:
        detail = dict(detail)
    geometry = _action_geometry_context(data, detail)
    if geometry:
        detail["geometry"] = geometry
    client_meta = get_client_action_meta()
    entry = {
        "event_id": f"event_{len(data['action_log']) + 1:06d}",
        "server_timestamp": _ts(),
        "client_timestamp": client_meta["client_timestamp"],
        "client_elapsed_ms": client_meta["client_elapsed_ms"],
        "survey_elapsed_seconds": seconds_since(data.get("survey_start_time", "")),
        "participant_id": data.get("participant_id", PARTICIPANT_ID),
        "action": action_type,
        "detail": detail,
        "trial_index": data.get("current_trial_index", 0),
        "question_id": data.get("current_question", {}).get("question_id", ""),
        "action_count": len(data["session"].actions),
    }
    if (
        action_type in {"select_vertex", "select_angle", "select_edge", "select_region"}
        and client_meta["click_x"] not in ("", None)
        and client_meta["click_y"] not in ("", None)
    ):
        try:
            entry["click_coordinates"] = {
                "x": float(client_meta["click_x"]),
                "y": float(client_meta["click_y"]),
                "coordinate_system": "display_canvas",
            }
        except (TypeError, ValueError):
            pass
    if data.get("phase") == "demo":
        preselected_inputs = data.get("demo_preselected_inputs", [])
        preselected_action = {
            4: "confirm_connection",
            5: "commit_ray",
            7: "measure_distance",
        }.get(data.get("demo_step"))
        if preselected_inputs and action_type == preselected_action:
            detail["input_origin"] = (
                "tutorial_preselected"
                if data.get("demo_step") == 5
                else "tutorial_partially_preselected"
            )
            detail["preselected_inputs"] = list(preselected_inputs)
        summary = data.get("tutorial_summary", {})
        guided_completed_at = summary.get("guided_completed_at")
        entry["tutorial_phase"] = (
            "free_exploration" if guided_completed_at else "guided"
        )
        entry["tutorial_step"] = (
            None if guided_completed_at
            else tutorial_stage_for_step(data.get("demo_step"))
        )
    data["action_log"].append(entry)
    if data.get("phase") == "demo":
        demo_step = data.get("demo_step", 0)
        expected_action = DEMO_STEPS.get(demo_step, {}).get("expected_action")
        if isinstance(expected_action, list):
            expected_matches = action_type in expected_action
        else:
            expected_matches = action_type == expected_action
        # Once the required action for this step has succeeded, the user may
        # freely try the same tool on other objects.  Re-validating every later
        # attempt against the tutorial target silently undoes those optional
        # annotations.
        step_already_completed = data.get("demo_pending_completion") == demo_step
        if expected_matches and not step_already_completed:
            if demo_target_matches(data, demo_step, detail):
                entry["detail"]["tutorial_target_correct"] = True
                data["demo_pending_completion"] = demo_step
                data["demo_incorrect_target_message"] = ""
            else:
                entry["detail"]["tutorial_target_correct"] = False
                entry["detail"]["tutorial_error"] = True
                mark_tutorial_tool_error(data)
                # Keep an incorrect edge extension visible: the tool worked,
                # but the participant chose the wrong target. Other guided
                # actions are still rolled back so their prefilled state and
                # visible labels remain deterministic.
                retain_incorrect_annotation = demo_step == 6
                entry["detail"]["incorrect_annotation_retained"] = retain_incorrect_annotation
                if (
                    not retain_incorrect_annotation
                    and data.get("session")
                    and data["session"].actions
                ):
                    data["session"].undo_action()
                    sync_line_label_counter(data)
                tutorial_error_message = {
                    3: "That is a vertex, but it is not the leftmost vertex of Region B. Try again.",
                    4: "Use Region B's leftmost vertex as the start and Region D's rightmost vertex as the end. Try again.",
                    5: "Draw a rightward ray from Region B's leftmost vertex. Try again.",
                    6: "Select the edge shared by Regions B and C, then extend it. Try again.",
                    7: "Measure from Region B's leftmost vertex to Region D's rightmost vertex. Try again.",
                    8: "Select Regions A and E, then execute the union. Try again.",
                }.get(demo_step, "Try the requested object again.")
                entry["detail"]["tutorial_error_message"] = tutorial_error_message
                data["demo_incorrect_target_message"] = tutorial_error_message
    # Print the log entry for William's backend inspection
    print(json.dumps(entry, ensure_ascii=False, default=str))

# ──────────────────────────────────────────────────────────────────────────────

def create_annotation_session_for_question(question: dict):
    Graph.initialize()
    maxX, maxY = 1.0, 1.0
    if question.get("question_id") == DEMO_QUESTION["question_id"]:
        res_map = build_circular_practice_map(question.get("num_regions", 6), maxX, maxY)
    else:
        res_map = BuildRandomMap.BuildRandomMap(
            question.get("num_regions", 8),
            maxX,
            maxY,
            seed=question.get("seed", 42),
        )
    img_size = (int(200 + 800 * maxX), int(200 + 800 * maxY))
    return AnnotationSession(res_map, img_size)


def build_circular_practice_map(num_regions=5, maxX=1.0, maxY=1.0):
    """The same stable octagonal practice map used by compositional_survey.py."""
    n = 8
    cx, cy = maxX / 2, maxY / 2
    radius = min(maxX, maxY) * 0.47
    angle_offset = math.pi / n
    ring = [
        Graph.Vertex(Graph.Vector(
            cx + radius * math.cos(angle_offset + 2 * math.pi * i / n),
            cy + radius * math.sin(angle_offset + 2 * math.pi * i / n),
        ))
        for i in range(n)
    ]
    upper_split = Graph.Vertex(Graph.Vector(0.45, 0.57))
    lower_split = Graph.Vertex(Graph.Vector(0.58, 0.42))
    vertices = ring + [upper_split, lower_split]
    edge_roots, edge_lookup = [], {}

    def edge_between(tail, head):
        key = (id(tail), id(head))
        if key in edge_lookup:
            return edge_lookup[key]
        edge = Graph.Edge(tail, head, True)
        edge_roots.append(edge)
        edge_lookup[(id(tail), id(head))] = edge
        edge_lookup[(id(head), id(tail))] = edge.reverse
        return edge

    boundary_edges = [edge_between(ring[i], ring[(i + 1) % n]) for i in range(n)]
    face_vertex_paths = [
        [ring[0], ring[1], upper_split, lower_split],
        [ring[1], ring[2], ring[3], upper_split],
        [ring[3], ring[4], ring[5], upper_split],
        [ring[5], ring[6], ring[7], lower_split, upper_split],
        [ring[7], ring[0], lower_split],
    ]
    faces = []
    for i, path in enumerate(face_vertex_paths[: max(1, min(5, int(num_regions or 5)))]):
        face_edges = [edge_between(path[j], path[(j + 1) % len(path)]) for j in range(len(path))]
        face = Graph.Face(face_edges, True)
        face.letter = chr(ord("A") + i)
        face.color = (i % 6) + 1
        face.trueEdges = face.edges
        faces.append(face)
        for edge in face_edges:
            edge.leftFace = face
    outside_edges = [boundary_edges[i].reverse for i in range(n - 1, -1, -1)]
    outside = Graph.Face(outside_edges, False)
    outside.letter = "Outside"
    outside.trueEdges = outside.edges
    for edge in outside_edges:
        edge.leftFace = outside
    for vertex in vertices:
        vertex.faces = [face for face in [outside] + faces if vertex in getattr(face, "vertices", [])]
    edges = []
    for edge in edge_roots:
        edges.extend([edge, edge.reverse])
    return Graph.Map(vertices, edges, [outside] + faces, [maxX, maxY])


def render_demo_direction_diagram(session):
    """Match compositional_survey.py's practice diagram and direction overlay."""
    res_map = session.res_map
    img_size = (1000, 1000)
    img = Image.new("RGBA", img_size, (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    DrawGraph.InitColors(alpha=153)
    black = (0, 0, 0, 255)
    font_bold = DrawGraph.GetSystemFont(80)
    font_small = DrawGraph.GetSystemFont(45)
    for face in res_map.faces:
        if not face.bounded:
            continue
        pts = [DrawGraph.V2P(v.p) for v in face.vertices]
        draw.polygon(pts, fill=DrawGraph.colors[getattr(face, "color", 0)], outline=black, width=4)
        cache_idx = getattr(face, "_cache_idx", None)
        if cache_idx is not None and cache_idx in session.face_label_cache:
            lp, distance = session.face_label_cache[cache_idx]
        else:
            lp, distance = Graph.LetterPointFace(face)
        draw.text(DrawGraph.V2P(lp), face.letter, fill=black,
                  font=font_bold if distance > 0.06 else font_small, anchor="mm")
    for edge in res_map.edges:
        if (getattr(getattr(edge, "leftFace", None), "bounded", False)
                and not getattr(getattr(edge.reverse, "leftFace", None), "bounded", False)):
            draw.line([DrawGraph.V2P(edge.tail.p), DrawGraph.V2P(edge.head.p)], fill=black, width=8)

    cx = cy = 0.5
    candidates = list(res_map.vertices)
    targets = [Graph.Vector(cx, 1.0), Graph.Vector(1.0, cy), Graph.Vector(cx, 0.0), Graph.Vector(0.0, cy)]
    cardinal = [min(candidates, key=lambda v: Graph.vecDist(v.p, target)) for target in targets]
    points = [DrawGraph.V2P(vertex.p) for vertex in cardinal]
    demo_color = (30, 102, 210, 255)
    demo_font = DrawGraph.GetSystemFont(42)
    for index, point in enumerate(points, start=1):
        x, y = point
        draw.ellipse([x - 17, y - 17, x + 17, y + 17], fill=(255, 255, 255, 245),
                     outline=demo_color, width=7)
        draw.text((x + 22, y - 22), str(index), fill=demo_color, font=demo_font,
                  stroke_width=3, stroke_fill=(255, 255, 255, 255))
    for start, end in zip(points, points[1:] + points[:1]):
        sx, sy = start
        ex, ey = end
        dx, dy = ex - sx, ey - sy
        length = max(math.hypot(dx, dy), 1)
        ux, uy = dx / length, dy / length
        line_start = (sx + ux * 22, sy + uy * 22)
        line_end = (ex - ux * 27, ey - uy * 27)
        draw.line([line_start, line_end], fill=demo_color, width=7)
        px, py = -uy, ux
        base_x, base_y = line_end[0] - ux * 18, line_end[1] - uy * 18
        draw.polygon([line_end, (base_x + px * 10, base_y + py * 10),
                      (base_x - px * 10, base_y - py * 10)], fill=demo_color)
    return img.resize((DISPLAY_SIDE, DISPLAY_SIDE), Image.Resampling.LANCZOS)


def render_demo_frame_diagram(session):
    """Highlight the polygon's exterior boundary as the frame."""
    img = session.render()
    draw = ImageDraw.Draw(img)
    frame_color = (20, 184, 166, 255)
    label_color = (75, 85, 99, 255)
    label_font = DrawGraph.GetSystemFont(38)
    # Remove the renderer's rectangular canvas boundary; in this tutorial,
    # the polygon's exterior edges are the frame.
    draw.rectangle(
        [90, 90, img.width - 90, img.height - 90],
        outline=(255, 255, 255, 255),
        width=18,
    )
    seen_frame_segments = set()
    for edge in session.res_map.edges:
        left_bounded = bool(getattr(getattr(edge, "leftFace", None), "bounded", False))
        reverse_face = getattr(getattr(edge, "reverse", None), "leftFace", None)
        right_bounded = bool(getattr(reverse_face, "bounded", False))
        if left_bounded == right_bounded:
            continue
        a = DrawGraph.V2P(edge.tail.p)
        b = DrawGraph.V2P(edge.head.p)
        segment_key = tuple(sorted((a, b)))
        if segment_key in seen_frame_segments:
            continue
        seen_frame_segments.add(segment_key)
        draw.line([a, b], fill=frame_color, width=9)
    draw.text((img.width // 2, 48), "Outside of the frame", fill=label_color,
              font=label_font, anchor="mm")
    draw.text((img.width // 2, 135), "Frame", fill=frame_color,
              font=label_font, anchor="mm", stroke_width=2,
              stroke_fill=(255, 255, 255, 255))
    return img.resize((DISPLAY_SIDE, DISPLAY_SIDE), Image.Resampling.LANCZOS)


def get_current_question(data: dict) -> dict:
    idx = data.get("current_trial_index", 0)
    return QUESTION_BANK[min(idx, len(QUESTION_BANK) - 1)]


def start_trial(data: dict, trial_index: int) -> None:
    question = QUESTION_BANK[trial_index]
    data["current_trial_index"] = trial_index
    data["current_question"] = question
    data["trial_start_time"] = _ts()
    data["trial_action_start_index"] = len(data.get("action_log", []))
    data["current_answer"] = ""
    data["current_notes"] = ""
    data["answer_feedback"] = None
    data["last_measurement"] = None
    data["last_run_message"] = ""
    data["session"] = create_annotation_session_for_question(question)
    data["union_buffer"] = []
    data["selected_vertex_ids"] = []
    data["selected_region_indices"] = []
    data["selected_angles"] = []
    data["selected_edges"] = []
    data["selected_angle"] = None
    data["selected_edge"] = None
    data["vertex_selection_labels"] = {}
    data["vertex_selection_label_counter"] = 1
    data["last_active_id"] = "none"
    data["v_start"] = None
    data["v_start_id"] = ""
    data["line_label_counter"] = 1
    data["tool_mode"] = "Vertex"
    data["measure_kind"] = "distance"


def start_demo(data: dict) -> None:
    data["phase"] = "demo"
    data["demo_step"] = 0
    data["demo_start_time"] = _ts()
    data["demo_end_time"] = ""
    data["demo_pending_completion"] = None
    data["demo_direction_answered"] = False
    data["demo_direction_correct"] = None
    data["demo_incorrect_target_message"] = ""
    data["demo_selected_types"] = []
    data["definitions_open"] = False
    data["tools_guide_open"] = False
    st.session_state["definitions_open"] = False
    st.session_state["tools_guide_open"] = False
    data["demo_preselected_inputs"] = []
    data["current_notes"] = ""
    data["answer_feedback"] = None
    data["last_measurement"] = None
    data["last_run_message"] = ""
    data["current_question"] = DEMO_QUESTION
    data["session"] = create_annotation_session_for_question(DEMO_QUESTION)
    data["union_buffer"] = []
    data["selected_vertex_ids"] = []
    data["selected_region_indices"] = []
    data["selected_angles"] = []
    data["selected_edges"] = []
    data["selected_angle"] = None
    data["selected_edge"] = None
    data["vertex_selection_labels"] = {}
    data["vertex_selection_label_counter"] = 1
    data["last_active_id"] = "none"
    data["v_start"] = None
    data["v_start_id"] = ""
    data["line_label_counter"] = 1
    data["tool_mode"] = "Vertex"
    data["measure_kind"] = "distance"
    data["tutorial_summary"] = {
        "started_at": data["demo_start_time"],
        "completed_at": None,
        "completion_status": "in_progress",
        "completion_method": None,
        "guided_completed_at": None,
        "free_exploration_started_at": None,
        "free_exploration_completed_at": None,
        "steps": {},
        "free_exploration_tool_calls": {
            "total_tool_calls": 0,
            "tool_counts": {},
            "error_count": 0,
        },
    }


def prefill_demo_vertex_inputs(data: dict, demo_step: int) -> None:
    """Preselect only the first vertex needed by each guided vertex step."""
    if demo_step not in {4, 5, 7}:
        return
    if demo_step == 7:
        data["measure_kind"] = "distance"
    faces = {
        face.letter: face
        for face in data["session"].res_map.faces
        if getattr(face, "bounded", False)
    }
    face_b = faces.get("B")
    if not face_b:
        return
    left_b = min(face_b.vertices, key=lambda vertex: vertex.p.x)
    vertices = [left_b]
    data["selected_vertex_ids"] = [
        str(getattr(vertex, "num", id(vertex)))
        for vertex in vertices
    ]
    data["demo_preselected_inputs"] = [
        {
            "object_type": "vertex",
            "vertex_id": str(getattr(vertex, "num", id(vertex))),
            "provided_by": "system",
        }
        for vertex in vertices
    ]
    sync_vertex_selection_labels(data)


def begin_survey(data: dict) -> None:
    mark_annotation_tutorial_completed(data)
    data["phase"] = "survey"
    data["demo_end_time"] = _ts()
    data["survey_start_time"] = _ts()
    data["definitions_open"] = False
    data["tools_guide_open"] = False
    st.session_state["definitions_open"] = False
    st.session_state["tools_guide_open"] = False
    start_trial(data, 0)


def skip_practice_to_review(data: dict) -> None:
    data["demo_step"] = DEMO_REVIEW_STEP
    data["tool_mode"] = "Vertex"
    data["measure_kind"] = "distance"
    data["demo_feedback_message"] = ""
    data["demo_pending_completion"] = None
    data["demo_incorrect_target_message"] = ""
    data["union_buffer"] = []
    data["selected_vertex_ids"] = []
    data["selected_region_indices"] = []
    data["selected_angles"] = []
    data["selected_edges"] = []
    data["selected_angle"] = None
    data["selected_edge"] = None
    data["vertex_selection_labels"] = {}
    data["vertex_selection_label_counter"] = 1
    data["v_start"] = None
    data["v_start_id"] = ""
    log_action(data, "skip_practice")


def create_new_data() -> dict:
    data = {
        "survey_version": SURVEY_VERSION,
        "survey_form": SURVEY_FORM,
        "condition": SURVEY_CONDITION,
        "participant_id": PARTICIPANT_ID,
        "survey_instance": SURVEY_INSTANCE_ID,
        "landing_choice_made": False,
        "entry_route": None,
        "phase": "demo",
        "dataset_path": DATASET_PATH,
        "dataset_metadata": DATASET_METADATA,
        "dataset_version": DATASET_METADATA.get("dataset_version", "unknown"),
        "dataset_role": DATASET_METADATA.get("dataset_role", "unknown"),
        "survey_start_time": "",
        "survey_end_time": "",
        "time_limit_seconds": None,
        "timer_hidden": False,
        "ended_by": "",
        "completed": False,
        "trials": [],
        "action_log": [],
    }
    data.setdefault("answer_feedback", None)
    start_demo(data)
    return data


PRACTICE_REQUIRED_SELECTIONS = ("Region", "Angle", "Vertex", "Edge")


def sync_demo_selected_types(data: dict) -> list[str]:
    """Derive Practice 1 checklist state from objects that remain selected.

    This matches the compositional tutorial: removing the only selected object
    of a type immediately makes that checklist item incomplete again.
    """
    selected = set()
    if data.get("selected_region_indices"):
        selected.add("Region")
    if data.get("selected_angles") or data.get("selected_angle"):
        selected.add("Angle")
    if data.get("selected_vertex_ids"):
        selected.add("Vertex")
    if data.get("selected_edges") or data.get("selected_edge"):
        selected.add("Edge")
    ordered = [label for label in PRACTICE_REQUIRED_SELECTIONS if label in selected]
    data["demo_selected_types"] = ordered
    return ordered


def selection_state_snapshot(data: dict) -> dict:
    return {
        "selected_vertex_ids": list(data.get("selected_vertex_ids", [])),
        "selected_region_indices": list(data.get("selected_region_indices", [])),
        "selected_angles": [dict(item) for item in data.get("selected_angles", [])],
        "selected_edges": [dict(item) for item in data.get("selected_edges", [])],
        "selected_angle": dict(data["selected_angle"]) if data.get("selected_angle") else None,
        "selected_edge": dict(data["selected_edge"]) if data.get("selected_edge") else None,
        "vertex_selection_labels": dict(data.get("vertex_selection_labels", {})),
        "vertex_selection_label_counter": int(data.get("vertex_selection_label_counter", 1)),
    }


def push_selection_undo(data: dict) -> None:
    stack = data.setdefault("selection_undo_stack", [])
    stack.append(selection_state_snapshot(data))
    if len(stack) > 50:
        del stack[:-50]


def restore_selection_snapshot(data: dict, snapshot: dict) -> None:
    for key, value in snapshot.items():
        data[key] = value
    sync_vertex_selection_labels(data)
    sync_demo_selected_types(data)


_SELECTION_ACTIONS = {
    "set_tool_mode", "set_measure_kind", "practice_select_geom",
    "select_vertex", "select_angle", "select_edge", "select_region",
    "deselect_vertex", "deselect_angle", "deselect_edge", "deselect_region",
    "clear_vertex_selection", "add_to_buffer", "remove_from_buffer", "clear_buffer",
}

_INTERFACE_ACTIONS = {
    "undo", "clear_all", "clear_union", "begin_demo", "skip_practice",
    "complete_clockwise_demo", "incorrect_clockwise_demo",
}


def _annotation_output(kind, label=None, **extra):
    output = {"type": "annotation", "kind": kind}
    if label:
        output["label"] = label
    output.update({key: value for key, value in extra.items() if value not in (None, "")})
    return output


def compositional_tool_call_from_action(entry: dict, order: int) -> dict | None:
    """Translate an executed annotation action to the compositional tool-call schema."""
    action = str(entry.get("action", ""))
    detail = entry.get("detail", {})
    detail = detail if isinstance(detail, dict) else {"message": str(detail)}
    tool = function = input_text = output_text = None
    output = None
    call_type = "annotation"

    if action == "commit_vertex":
        label = detail.get("label")
        tool, function = "highlight", "vertex"
        input_text = f"highlight(vertex={label or detail.get('vertex_id', '?')})"
        output = _annotation_output("point", label, vertex_id=detail.get("vertex_id"))
    elif action == "commit_angle":
        label = detail.get("label")
        face = detail.get("face")
        tool, function = "highlight", "angle"
        input_text = f"highlight(angle={label or detail.get('vertex_id', '?')}, region={face or '?'})"
        output = _annotation_output("angle", label, region=face, vertex_id=detail.get("vertex_id"))
    elif action == "commit_edge":
        label = detail.get("label") or "edge"
        tool, function = "highlight", "edge"
        input_text = f"highlight(edge={label})"
        output = _annotation_output(
            "edge", label,
            adjacent_regions=detail.get("adjacent_regions"),
            tail=detail.get("tail"),
            head=detail.get("head"),
        )
    elif action in {"commit_region", "commit_union_highlight"}:
        face = "U" if action == "commit_union_highlight" else detail.get("face")
        tool, function = "highlight", "region"
        input_text = f"highlight(region={face or '?'})"
        output = _annotation_output("region", face)
    elif action == "confirm_connection":
        line = detail.get("line")
        start = detail.get("from_label") or detail.get("from")
        end = detail.get("to_label") or detail.get("to")
        tool, function = "draw line", "segment"
        input_text = f"draw({start}, {end}, kind=\"segment\")"
        output = _annotation_output("line", line, line_type="segment", endpoints=[start, end])
    elif action == "commit_ray":
        line = detail.get("line")
        start = detail.get("vertex_label") or detail.get("vertex_id")
        direction = detail.get("direction")
        tool, function = "draw line", "ray"
        input_text = f"draw({start}, \"{direction}\")"
        output = _annotation_output(
            "line", line, line_type="ray", origin=start, direction=direction
        )
    elif action in {"commit_axis_h", "commit_axis_v"}:
        line = detail.get("line")
        start = detail.get("vertex_label") or detail.get("vertex_id")
        direction = "horizontal" if action == "commit_axis_h" else "vertical"
        tool, function = "draw line", "full line"
        input_text = f"draw({start}, kind=\"{direction}\")"
        output = _annotation_output(
            "line", line, line_type="full", origin=start, direction=direction
        )
    elif action == "extend_edge":
        edge = detail.get("edge") or "edge"
        line = detail.get("line")
        tool, function = "draw line", "extend edge"
        input_text = f"draw({edge}, kind=\"full\")"
        output = _annotation_output(
            "line", line, line_type="full", source_edge=edge,
            endpoints=[detail.get("tail"), detail.get("head")],
        )
    elif action == "execute_union":
        faces = list(detail.get("faces", []))
        tool, function = "merge", "merge"
        input_text = f"merge({', '.join(faces)})"
        output = _annotation_output("region", "U", source_regions=faces)
    elif action.startswith("measure_"):
        function = {
            "measure_region": "area",
            "measure_distance": "distance",
            "measure_angle": "angle",
            "measure_edge": "edge_length",
        }.get(action, action.removeprefix("measure_"))
        tool, call_type = "measure", "analysis"
        output = {"type": "number"}
        if action == "measure_region":
            input_text = f"measure({detail.get('label', 'region')}, what=\"area\")"
            output.update({"value": detail.get("area"), "unit": "square units"})
        elif action == "measure_angle":
            input_text = f"measure({detail.get('label', 'angle')}, what=\"angle\")"
            output.update({"value": detail.get("degrees"), "unit": "degrees"})
        elif action == "measure_distance":
            start = detail.get("from_label") or detail.get("from_vertex_id")
            end = detail.get("to_label") or detail.get("to_vertex_id")
            input_text = f"measure({start}, {end}, what=\"distance\")"
            output.update({"value": detail.get("length"), "unit": "length units"})
        else:
            input_text = "measure(edge, what=\"length\")"
            output.update({"value": detail.get("length"), "unit": "length units"})
    else:
        return None

    if isinstance(output, dict):
        # Keep participant-facing labels while also retaining the exact
        # diagram geometry captured by log_action().  Labels such as v1/e1
        # are session-local names and are not sufficient to replay a program.
        geometry = detail.get("geometry")
        if isinstance(geometry, dict) and geometry:
            output["geometry"] = geometry
        output_text = output.get("label")
        if output_text in (None, ""):
            output_text = output.get("value")
    try:
        display_text = participant_output_for_action(entry)
    except NameError:
        display_text = None
    call = {
        "call_id": (
            f"call_{entry.get('event_id')}"
            if entry.get("event_id") else f"call_{order:06d}"
        ),
        "source_event_id": entry.get("event_id"),
        "order": order,
        "status": "active",
        "undone": False,
        "cleared": False,
        "tool": tool,
        "function": function,
        "call_type": call_type,
        "input": input_text,
        "arguments": {
            "action": action,
            "parameters": detail,
        },
        "output": output,
        "output_text": "" if output_text is None else str(output_text),
        "display_text": display_text or ("" if output_text is None else str(output_text)),
        "timestamp": entry.get("server_timestamp"),
        "survey_elapsed_seconds": entry.get("survey_elapsed_seconds"),
        "tutorial_step": entry.get("tutorial_step"),
        "tutorial_phase": entry.get("tutorial_phase"),
    }
    return call


def compositional_selection_events(actions: list[dict]) -> list[dict]:
    """Separate selection and interface history using the compositional event schema."""
    events = []
    selection_after = []
    selection_mode = None

    def inferred_mode(action_name: str, detail: dict) -> str | None:
        if action_name == "practice_select_geom":
            return str(detail.get("kind") or "").title() or None
        for object_type in ("vertex", "angle", "edge", "region"):
            if object_type in action_name:
                return object_type.title()
        return None

    def same_selected_object(selected: dict, removed: dict) -> bool:
        selected_type = selected.get("object_type")
        if selected_type != removed.get("object_type"):
            return False
        selected_detail = selected.get("description", {})
        removed_detail = removed.get("description", {})
        if selected_type == "vertex":
            return str(selected_detail.get("vertex_id")) == str(removed_detail.get("vertex_id"))
        if selected_type == "angle":
            return (
                str(selected_detail.get("vertex_id")) == str(removed_detail.get("vertex_id"))
                and str(selected_detail.get("face_idx")) == str(removed_detail.get("face_idx"))
            )
        if selected_type == "edge":
            selected_endpoints = {
                str(selected_detail.get("tail_id")), str(selected_detail.get("head_id"))
            }
            removed_endpoints = {
                str(removed_detail.get("tail_id")), str(removed_detail.get("head_id"))
            }
            if None not in {
                selected_detail.get("tail_id"), selected_detail.get("head_id"),
                removed_detail.get("tail_id"), removed_detail.get("head_id"),
            }:
                return selected_endpoints == removed_endpoints
            return str(selected_detail.get("edge_idx")) == str(removed_detail.get("edge_idx"))
        if selected_type == "region":
            return str(selected_detail.get("face_idx")) == str(removed_detail.get("face_idx"))
        return selected.get("object_label") == removed.get("object_label")

    def selection_object_id(object_type: str, detail: dict) -> str:
        if object_type == "vertex":
            return f"vertex:{detail.get('vertex_id')}"
        if object_type == "region":
            return f"region:{detail.get('face') or detail.get('face_idx')}"
        if object_type == "angle":
            return (
                f"angle:{detail.get('face') or detail.get('face_idx')}:"
                f"vertex:{detail.get('vertex_id')}"
            )
        if object_type == "edge":
            endpoints = sorted(
                (str(detail.get("tail_id")), str(detail.get("head_id")))
            )
            return f"edge:vertex:{endpoints[0]}--vertex:{endpoints[1]}"
        return f"{object_type}:{detail.get('label') or detail.get('message')}"

    for entry in actions:
        action = str(entry.get("action", ""))
        if action not in _SELECTION_ACTIONS and action not in _INTERFACE_ACTIONS:
            continue
        detail = entry.get("detail", {})
        detail = detail if isinstance(detail, dict) else {"message": str(detail)}
        if action in {"set_tool_mode", "set_measure_kind"}:
            selection_mode = detail.get("mode") or detail.get("bridge_mode") or detail.get("message")
        else:
            inferred_selection_mode = inferred_mode(action, detail)
            if inferred_selection_mode is not None:
                selection_mode = inferred_selection_mode
        event = {
            "source_event_id": entry.get("event_id"),
            "order": len(events) + 1,
            "action": action,
            "timestamp": entry.get("server_timestamp"),
            "survey_elapsed_seconds": entry.get("survey_elapsed_seconds"),
        }
        if entry.get("click_coordinates"):
            event["click_coordinates"] = entry.get("click_coordinates")
        # Tutorial actions are tagged at collection time by log_action().
        # Preserve that context in selection events just as tool-call events do,
        # so analysts can distinguish guided steps from free exploration without
        # reconstructing the tutorial timeline from timestamps.
        if "tutorial_phase" in entry:
            event["tutorial_phase"] = entry.get("tutorial_phase")
        if "tutorial_step" in entry:
            event["tutorial_step"] = entry.get("tutorial_step")
        if action in _INTERFACE_ACTIONS:
            event["event_type"] = "interface"
            event["details"] = detail
            if action == "clear_all":
                selection_after = []
            event["selection_after"] = list(selection_after)
        elif action in {"set_tool_mode", "set_measure_kind"}:
            event["selection_mode"] = selection_mode
            event["details"] = detail
            event["selection_after"] = list(selection_after)
        else:
            event["selection_mode"] = selection_mode
            object_type = action.removeprefix("select_").removeprefix("deselect_")
            event["object"] = {
                "object_id": selection_object_id(object_type, detail),
                "object_type": object_type,
                "object_label": (
                    detail.get("marker_label")
                    or detail.get("face")
                    or detail.get("label")
                    or detail.get("vertex_id")
                    or detail.get("face_idx")
                    or detail.get("edge_idx")
                ),
                "description": detail,
            }
            geometry = detail.get("geometry")
            if isinstance(geometry, dict) and geometry:
                event["object"]["geometry"] = geometry
            if action.startswith("select_"):
                selection_after.append(event["object"])
            elif action.startswith("deselect_") and selection_after:
                matching_selection = next(
                    (
                        item for item in reversed(selection_after)
                        if same_selected_object(item, event["object"])
                    ),
                    None,
                )
                if matching_selection is not None:
                    event["object"]["object_label"] = matching_selection.get("object_label")
                selection_after = [
                    item for item in selection_after
                    if not same_selected_object(item, event["object"])
                ]
            elif action in {"clear_vertex_selection", "clear_buffer"}:
                selection_after = []
            event["selection_after"] = list(selection_after)
        events.append(event)
    return events


def apply_tool_call_statuses(calls: list[dict], actions: list[dict]) -> None:
    """Mark calls affected by Undo/Clear All while preserving execution history."""
    calls_by_event = {
        call.get("source_event_id"): call
        for call in calls if call.get("source_event_id")
    }
    for entry in actions:
        detail = entry.get("detail", {})
        if not isinstance(detail, dict):
            continue
        if entry.get("action") == "undo":
            target_id = detail.get("target_event_id")
            if target_id in calls_by_event:
                target_call = calls_by_event[target_id]
                target_call["status"] = "undone"
                target_call["undone"] = True
                target_call["undone_by_event_id"] = entry.get("event_id")
                target_call["undone_at"] = entry.get("server_timestamp")
        elif entry.get("action") == "clear_all":
            for event_id in detail.get("affected_event_ids", []):
                if (
                    event_id in calls_by_event
                    and calls_by_event[event_id].get("status") == "active"
                ):
                    target_call = calls_by_event[event_id]
                    target_call["status"] = "cleared"
                    target_call["cleared"] = True
                    target_call["cleared_by_event_id"] = entry.get("event_id")
                    target_call["cleared_at"] = entry.get("server_timestamp")


def active_tool_event_ids(actions: list[dict]) -> list[str]:
    """Return currently active tool event IDs after applying Undo/Clear All."""
    calls = []
    for entry in actions:
        call = compositional_tool_call_from_action(entry, len(calls) + 1)
        if call is not None:
            calls.append(call)
    apply_tool_call_statuses(calls, actions)
    return [
        call["source_event_id"]
        for call in calls
        if call.get("status") == "active" and call.get("source_event_id")
    ]


def undo_target_event_id(actions: list[dict], action_count: int) -> str | None:
    """Match the top AnnotationSession action to its active annotation event.

    Analysis calls such as measurements do not enter AnnotationSession.actions,
    so the newest tool event is not necessarily the object that Undo removes.
    The recorded action_count and call type identify the corresponding event.
    """
    calls = []
    entries_by_id = {}
    for entry in actions:
        event_id = entry.get("event_id")
        if event_id:
            entries_by_id[event_id] = entry
        call = compositional_tool_call_from_action(entry, len(calls) + 1)
        if call is not None:
            calls.append(call)
    apply_tool_call_statuses(calls, actions)
    for call in reversed(calls):
        event_id = call.get("source_event_id")
        entry = entries_by_id.get(event_id, {})
        if (
            call.get("status") == "active"
            and call.get("call_type") == "annotation"
            and int(entry.get("action_count", -1)) == int(action_count)
        ):
            return event_id
    return None


def annotation_score_summary(responses: dict) -> dict:
    records = [
        response for response in responses.values()
        if isinstance(response, dict)
        and str(response.get("answer", "")).strip()
        and isinstance(response.get("is_correct"), bool)
    ]
    substantive = [r for r in records if not r.get("is_attention_check", False)]
    attention = [r for r in records if r.get("is_attention_check", False)]
    def score_group(group):
        correct = sum(bool(response.get("is_correct")) for response in group)
        total = len(group)
        return correct, total, round(correct / total, 4) if total else None

    substantive_correct, substantive_total, substantive_accuracy = score_group(substantive)
    overall_correct, overall_total, overall_accuracy = score_group(records)
    attention_passed, attention_total, _ = score_group(attention)
    return {
        "substantive_correct": substantive_correct,
        "substantive_total": substantive_total,
        "substantive_accuracy": substantive_accuracy,
        "overall_correct": overall_correct,
        "overall_total": overall_total,
        "overall_accuracy": overall_accuracy,
        "attention_checks_passed": attention_passed,
        "attention_checks_total": attention_total,
        "attention_check_pass": (
            attention_passed == attention_total if attention_total else None
        ),
    }


def annotation_tool_summary(responses: dict) -> dict:
    substantive = [
        response for response in responses.values()
        if isinstance(response, dict) and not response.get("is_attention_check", False)
    ]
    tool_counts = {}
    total = 0
    active = 0
    undone = 0
    cleared = 0
    questions_using_tools = 0
    for response in substantive:
        calls = [call for call in response.get("tool_calls", []) if isinstance(call, dict)]
        if calls:
            questions_using_tools += 1
        total += len(calls)
        for call in calls:
            is_undone = bool(call.get("undone")) or call.get("status") == "undone"
            is_cleared = bool(call.get("cleared")) or call.get("status") == "cleared"
            undone += is_undone
            cleared += is_cleared
            active += not is_undone and not is_cleared
            tool = str(call.get("tool", "unknown"))
            tool_counts[tool] = tool_counts.get(tool, 0) + 1
    return {
        "total_tool_calls": total,
        "active_tool_calls": active,
        "undone_tool_calls": undone,
        "cleared_tool_calls": cleared,
        "questions_using_tools": questions_using_tools,
        "tool_counts": dict(sorted(tool_counts.items())),
    }


def annotation_dataset_metadata(data: dict) -> dict:
    path = data.get("dataset_path", DATASET_PATH)
    metadata = data.get("dataset_metadata", DATASET_METADATA) or {}
    digest = None
    if path and os.path.exists(path):
        try:
            with open(path, "rb") as dataset_file:
                digest = hashlib.sha256(dataset_file.read()).hexdigest()
        except OSError:
            digest = None
    return {
        "version": metadata.get("dataset_version", data.get("dataset_version")),
        "role": metadata.get("dataset_role", data.get("dataset_role")),
        "generated_at": metadata.get("generated_at"),
        "file": os.path.basename(path) if path else None,
        "sha256": digest,
    }


def build_result_payload(data: dict) -> dict:
    responses = {}
    for trial in data.get("trials", []):
        question = trial.get("question", {})
        question_index = trial.get("question_index", trial.get("trial_index", 0))
        question_id = str(question.get("question_id", f"q_{question_index:03d}"))
        responses[question_id] = trial
    demo_actions = [
        entry for entry in data.get("action_log", [])
        if entry.get("question_id") == DEMO_QUESTION["question_id"]
    ]
    tutorial_calls = []
    for entry in demo_actions:
        call = compositional_tool_call_from_action(entry, len(tutorial_calls) + 1)
        if call is not None:
            detail = entry.get("detail", {})
            if isinstance(detail, dict) and detail.get("tutorial_error"):
                error_message = (
                    detail.get("tutorial_error_message")
                    or "Incorrect tutorial target."
                )
                call["call_type"] = "error"
                call["function"] = "error"
                call["output"] = {
                    "type": "error",
                    "message": error_message,
                }
                call["output_text"] = ""
                call["display_text"] = error_message
            tutorial_calls.append(call)
    apply_tool_call_statuses(tutorial_calls, demo_actions)
    tutorial_summary = refresh_annotation_tutorial_summary(data)
    tutorial_steps = tutorial_summary.setdefault("steps", {})
    guided_completed_at = tutorial_summary.get("guided_completed_at")
    for call in tutorial_calls:
        timestamp = call.get("timestamp")
        if not call.get("tutorial_phase"):
            call["tutorial_phase"] = (
                "free_exploration"
                if guided_completed_at and timestamp and timestamp >= guided_completed_at
                else "guided"
            )
        if call.get("tutorial_phase") == "free_exploration":
            call["tutorial_step"] = None
        elif not call.get("tutorial_step") and timestamp:
            for stage, step_entry in tutorial_steps.items():
                started_at = step_entry.get("started_at")
                completed_at = step_entry.get("completed_at")
                if (
                    started_at
                    and timestamp >= started_at
                    and (not completed_at or timestamp <= completed_at)
                ):
                    call["tutorial_step"] = stage
                    break
    stage_titles = {
        "clockwise": "Clockwise",
        "frame": "Frame and outside of the frame",
        "selection": DEMO_STEPS[2]["title"],
        "highlight": DEMO_STEPS[3]["title"],
        "segment": DEMO_STEPS[4]["title"],
        "ray": DEMO_STEPS[5]["title"],
        "extend_edge": DEMO_STEPS[6]["title"],
        "measure_distance": DEMO_STEPS[7]["title"],
        "merge": DEMO_STEPS[8]["title"],
    }
    for stage in TUTORIAL_GUIDED_STAGES:
        entry = tutorial_step_entry(data, stage)
        entry.setdefault("title", stage_titles.get(stage, stage))
        step_calls = [
            call for call in tutorial_calls
            if call.get("tutorial_phase") == "guided"
            and call.get("tutorial_step") == stage
        ]
        entry["tool_calls"] = step_calls
        entry["tool_usage"] = summarize_annotation_tool_calls(step_calls)
    tutorial_summary["tool_calls"] = tutorial_calls
    free_exploration_calls = [
        call for call in tutorial_calls
        if call.get("tutorial_phase") == "free_exploration"
    ]
    tutorial_summary["free_exploration_calls"] = free_exploration_calls
    tutorial_summary["free_exploration_tool_calls"] = (
        summarize_annotation_tool_calls(free_exploration_calls)
    )
    tutorial_summary["selection_events"] = compositional_selection_events(demo_actions)
    tutorial_summary["tool_usage"] = summarize_annotation_tool_calls(tutorial_calls)
    tutorial_completed = tutorial_summary.get("completion_status") == "completed"
    score_summary = annotation_score_summary(responses)
    tool_summary = annotation_tool_summary(responses)
    survey_completed_at = data.get("survey_end_time") or None
    post_survey_responses = data.get("post_survey_responses", {})
    study_completed_at = (
        post_survey_responses.get("submitted_at")
        if isinstance(post_survey_responses, dict)
        else None
    ) or survey_completed_at
    return {
        "response_schema_version": RESPONSE_SCHEMA_VERSION,
        "code_version": CODE_VERSION,
        "condition": SURVEY_CONDITION,
        "participant_id": data.get("participant_id", PARTICIPANT_ID),
        "survey_instance": data.get("survey_instance", SURVEY_INSTANCE_ID),
        "survey_version": SURVEY_VERSION,
        "survey_form": data.get("survey_form", SURVEY_FORM),
        "dataset": annotation_dataset_metadata(data),
        "saved_at": _ts(),
        "study_started_at": data.get("demo_start_time") or None,
        "study_completed_at": study_completed_at,
        "total_duration_seconds": elapsed_between_timestamps(
            data.get("demo_start_time", ""),
            study_completed_at or "",
        ),
        "survey_started_at": data.get("survey_start_time") or None,
        "survey_completed_at": survey_completed_at,
        "survey_duration_seconds": elapsed_between_timestamps(
            data.get("survey_start_time", ""),
            survey_completed_at or "",
        ),
        "survey_question_index": data.get("current_trial_index", 0),
        "max_confirmed_question_index": max(
            (trial.get("question_index", trial.get("trial_index", -1)) for trial in data.get("trials", [])),
            default=-1,
        ),
        "survey_completed": data.get("completed", False),
        "tutorial_completed": tutorial_completed,
        "post_survey_completed": data.get("post_survey_completed", False),
        "entry_route": data.get("entry_route"),
        "question_bank": QUESTION_BANK,
        "responses": responses,
        "score_summary": score_summary,
        "tool_usage_summary": tool_summary,
        "post_survey_responses": post_survey_responses,
        "tutorial_summary": tutorial_summary,
    }


def result_file_path(data: dict) -> str:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    survey_instance = _safe_id(data.get("survey_instance", SURVEY_INSTANCE_ID))
    return os.path.join(
        RESULTS_DIR,
        f"geometry_survey_{SURVEY_CONDITION}_{survey_instance}.json",
    )


def save_results_json(data: dict) -> str:
    path = result_file_path(data)
    temp_path = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(build_result_payload(data), f, indent=2, ensure_ascii=False, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_path, path)
    return path


def save_results_postgres(data: dict) -> bool:
    """Upsert one durable JSONB snapshot per survey instance on Render."""
    if not DATABASE_URL:
        return False
    if psycopg is None:
        raise RuntimeError("DATABASE_URL is set but psycopg is not installed")

    payload = build_result_payload(data)
    json_payload = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS public.survey_response_runs (
                    condition TEXT NOT NULL,
                    participant_id TEXT NOT NULL,
                    survey_instance TEXT NOT NULL,
                    survey_version TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    survey_completed BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (condition, survey_version, survey_instance)
                )
                """
            )
            cur.execute(
                """
                INSERT INTO public.survey_response_runs (
                    condition, participant_id, survey_instance, survey_version,
                    payload, survey_completed
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (condition, survey_version, survey_instance) DO UPDATE SET
                    participant_id = EXCLUDED.participant_id,
                    payload = EXCLUDED.payload,
                    survey_completed = EXCLUDED.survey_completed,
                    updated_at = NOW()
                """,
                (
                    payload["condition"],
                    payload["participant_id"],
                    payload["survey_instance"],
                    payload["survey_version"],
                    Jsonb(json_payload),
                    bool(payload.get("survey_completed")),
                ),
            )
    return True


def save_results(data: dict) -> str:
    """Persist to Postgres on Render, with local JSON retained as a fallback."""
    if DATABASE_URL:
        try:
            save_results_postgres(data)
            return "Postgres"
        except Exception as exc:
            # A transient database outage must not interrupt a participant's
            # submission. Render logs retain the error while local JSON keeps
            # the latest recoverable snapshot on this instance.
            print(f"Postgres result save failed; using local JSON fallback: {exc!r}")
    return save_results_json(data)


def finalize_current_trial(data: dict, answer: str, ended_by: str, is_correct=None) -> None:
    question = data.get("current_question", get_current_question(data))
    question_index = data.get("current_trial_index", 0)
    trial_start_time = data.get("trial_start_time", "")
    trial_end_time = _ts()
    parsed_start = _parse_ts(trial_start_time)
    parsed_end = _parse_ts(trial_end_time)
    response_time_seconds = None
    if parsed_start and parsed_end:
        response_time_seconds = round(max(0.0, (parsed_end - parsed_start).total_seconds()), 3)
    trial_actions = list(data.get("action_log", [])[data.get("trial_action_start_index", 0):])
    raw_tool_actions = [
        entry for entry in trial_actions if entry.get("action") != "submit_answer"
    ]
    tool_calls = []
    for entry in raw_tool_actions:
        call = compositional_tool_call_from_action(entry, len(tool_calls) + 1)
        if call is not None:
            tool_calls.append(call)
    apply_tool_call_statuses(tool_calls, raw_tool_actions)
    selection_events = compositional_selection_events(raw_tool_actions)
    executed_action_names = {
        "commit_vertex", "commit_angle", "commit_edge", "commit_region", "commit_union_highlight",
        "confirm_connection", "commit_axis_h", "commit_axis_v", "commit_ray", "extend_edge", "execute_union",
        "measure_distance", "measure_angle", "measure_edge", "measure_region",
        "clear_union", "undo", "clear_all",
    }
    executed_actions = [
        entry for entry in raw_tool_actions
        if entry.get("action") in executed_action_names
    ]
    trial_record = {
        "participant_id": data.get("participant_id", PARTICIPANT_ID),
        "survey_version": SURVEY_VERSION,
        "question_id": str(question.get("question_id", "")),
        "question_index": question_index,
        "trial_index": question_index,
        "is_attention_check": bool(question.get("is_attention_check")),
        "question": question,
        "question_started_at": trial_start_time,
        "trial_start_time": trial_start_time,
        "trial_end_time": trial_end_time,
        "answer": answer,
        "scratch_pad": data.get("current_notes", ""),
        "correct_answer": question.get("answer", ""),
        "is_correct": is_correct,
        "survey_elapsed_seconds": seconds_since(data.get("survey_start_time", "")),
        "response_time_seconds": response_time_seconds,
        "submitted_at": trial_end_time,
        "tool_calls": tool_calls,
        "selection_events": selection_events,
        "raw_actions": raw_tool_actions,
        "executed_actions": executed_actions,
        "program": [call.get("input", "") for call in tool_calls],
        "active_program": [
            call.get("input", "") for call in tool_calls
            if call.get("status") == "active"
        ],
        "output_log": [
            call.get("display_text", "") for call in tool_calls
            if call.get("call_type") == "analysis"
        ],
        "notes": data.get("current_notes", ""),
        "ended_by": ended_by,
        "selection_event_count": len(selection_events),
        "annotation_action_count": sum(
            call.get("call_type") == "annotation" for call in tool_calls
        ),
        "tool_call_count": len(tool_calls),
    }
    data.setdefault("trials", []).append(trial_record)


def complete_survey(data: dict, ended_by: str) -> None:
    if data.get("completed"):
        return
    data["completed"] = True
    data["ended_by"] = ended_by
    data["survey_end_time"] = _ts()
    data["result_file"] = save_results(data)


def load_session_postgres():
    """Load the latest full Streamlit session snapshot for this survey run."""
    if not DATABASE_URL or psycopg is None:
        return None
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS public.survey_session_snapshots (
                    condition TEXT NOT NULL,
                    survey_version TEXT NOT NULL,
                    survey_instance TEXT NOT NULL,
                    participant_id TEXT NOT NULL,
                    session_snapshot BYTEA NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (condition, survey_version, survey_instance)
                )
                """
            )
            cur.execute(
                """
                SELECT session_snapshot
                FROM public.survey_session_snapshots
                WHERE condition = %s
                  AND survey_version = %s
                  AND survey_instance = %s
                """,
                (SURVEY_CONDITION, SURVEY_VERSION, SURVEY_INSTANCE_ID),
            )
            row = cur.fetchone()
    if not row:
        return None
    restored = pickle.loads(bytes(row[0]))
    if not isinstance(restored, dict) or restored.get("survey_version") != SURVEY_VERSION:
        return None
    restored["participant_id"] = PARTICIPANT_ID
    restored["survey_instance"] = SURVEY_INSTANCE_ID
    restored["condition"] = SURVEY_CONDITION
    return restored


def save_session_postgres(data: dict) -> bool:
    """Upsert the complete resumable state for this survey run."""
    if not DATABASE_URL or psycopg is None:
        return False
    snapshot = pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS public.survey_session_snapshots (
                    condition TEXT NOT NULL,
                    survey_version TEXT NOT NULL,
                    survey_instance TEXT NOT NULL,
                    participant_id TEXT NOT NULL,
                    session_snapshot BYTEA NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (condition, survey_version, survey_instance)
                )
                """
            )
            cur.execute(
                """
                INSERT INTO public.survey_session_snapshots (
                    condition, survey_version, survey_instance,
                    participant_id, session_snapshot
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (condition, survey_version, survey_instance) DO UPDATE SET
                    participant_id = EXCLUDED.participant_id,
                    session_snapshot = EXCLUDED.session_snapshot,
                    updated_at = NOW()
                """,
                (
                    SURVEY_CONDITION,
                    SURVEY_VERSION,
                    SURVEY_INSTANCE_ID,
                    PARTICIPANT_ID,
                    snapshot,
                ),
            )
    return True


def load_or_create_session():
    # Prefer the local snapshot while this Render instance is alive. It may be
    # newer than Postgres if the most recent database write briefly failed.
    if os.path.exists(PERSIST_FILE):
        try:
            with open(PERSIST_FILE, "rb") as f:
                data = pickle.load(f)
                data["participant_id"] = PARTICIPANT_ID
                data["survey_instance"] = SURVEY_INSTANCE_ID
                data["condition"] = SURVEY_CONDITION
                if data.get("survey_version") != SURVEY_VERSION:
                    return create_new_data()
                # print(f"💾 Loaded session from disk, actions={len(data['session'].actions)}")  # COMMENTED OUT
                return data
        except Exception as e:
            pass  # print(f"⚠️ Failed to load session: {e}")  # COMMENTED OUT

    # Render's /tmp is ephemeral. After a restart or redeploy, resume from the
    # durable snapshot instead of silently starting the participant over.
    if DATABASE_URL:
        try:
            restored = load_session_postgres()
            if restored is not None:
                return restored
        except Exception as exc:
            print(f"Postgres session load failed; starting a new session: {exc!r}")

    return create_new_data()

def save_session(data):
    data["participant_id"] = PARTICIPANT_ID
    data["survey_instance"] = SURVEY_INSTANCE_ID
    data["condition"] = SURVEY_CONDITION
    try:
        temp_path = f"{PERSIST_FILE}.{uuid.uuid4().hex}.tmp"
        with open(temp_path, "wb") as f:
            pickle.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, PERSIST_FILE)
        # print(f"💾 Saved session to disk, actions={len(data['session'].actions)}")  # COMMENTED OUT
    except Exception as exc:
        print(f"Local session save failed: {exc!r}")
    if DATABASE_URL:
        try:
            save_session_postgres(data)
        except Exception as exc:
            print(f"Postgres session save failed; keeping local session: {exc!r}")


def clear_canvas_state(data: dict) -> int:
    cleared_count = len(data["session"].actions)
    while data["session"].actions:
        data["session"].undo_action()
    data["union_buffer"] = []
    data["selected_vertex_ids"] = []
    data["selected_region_indices"] = []
    data["selected_angles"] = []
    data["selected_edges"] = []
    data["selected_angle"] = None
    data["selected_edge"] = None
    data["vertex_selection_labels"] = {}
    data["vertex_selection_label_counter"] = 1
    data["last_active_id"] = "none"
    data["v_start"] = None
    data["v_start_id"] = ""
    data["last_measurement"] = None
    data["last_run_message"] = ""
    data["current_notes"] = ""
    data["line_label_counter"] = 1
    data["demo_preselected_inputs"] = []
    data["selection_undo_stack"] = []
    return cleared_count


def available_marker_labels(sess, category: str, prefix: str, count: int) -> list[str]:
    """Return the labels RUN would allocate, without mutating the session."""
    hidden_edge_ids = sess.get_active_hidden_edges()
    label_arg_index = {"vertex": 1, "angle": 2, "edge": 2}[category]
    marker_name = f"label_{category}"
    active_used = set()
    for action_func, action_args, _action_kwargs in sess.actions:
        action_name = getattr(action_func, "__name__", "").lower()
        is_combined_angle = category == "angle" and "combined_angle" in action_name
        is_labeled_vertex_composite = category == "vertex" and (
            "labeled_vertex_segment" in action_name
            or "labeled_vertex_axis" in action_name
            or "labeled_vertex_ray" in action_name
        )
        if marker_name not in action_name and not is_combined_angle:
            if not is_labeled_vertex_composite:
                continue
        if sess.is_marker_obsolete(action_func, action_args, hidden_edge_ids):
            continue
        if category == "vertex" and "labeled_vertex_segment" in getattr(action_func, "__name__", "").lower():
            for label in (action_args[1] if len(action_args) > 1 else None, action_args[3] if len(action_args) > 3 else None):
                if label and re.fullmatch(rf"{re.escape(prefix)}\d+", str(label)):
                    active_used.add(str(label))
            continue
        if category == "vertex" and "labeled_vertex_axis" in action_name:
            label = action_args[1] if len(action_args) > 1 else None
            if label and re.fullmatch(rf"{re.escape(prefix)}\d+", str(label)):
                active_used.add(str(label))
            continue
        if category == "vertex" and "labeled_vertex_ray" in action_name:
            label = action_args[1] if len(action_args) > 1 else None
            if label and re.fullmatch(rf"{re.escape(prefix)}\d+", str(label)):
                active_used.add(str(label))
            continue
        combined_label_index = 3 if is_combined_angle else label_arg_index
        label = action_args[combined_label_index] if len(action_args) > combined_label_index else None
        if label and re.fullmatch(rf"{re.escape(prefix)}\d+", str(label)):
            active_used.add(str(label))

    labels = []
    counter = 1
    while len(labels) < count:
        candidate = f"{prefix}{counter}"
        if candidate not in active_used:
            labels.append(candidate)
        counter += 1
    return labels


def sync_vertex_selection_labels(data: dict) -> None:
    """Number only the vertices in the current selection, in selection order."""
    selected_ids = [str(value) for value in data.get("selected_vertex_ids", [])]
    labels = available_marker_labels(data["session"], "vertex", "v", len(selected_ids))
    data["vertex_selection_labels"] = {
        vertex_id: labels[index]
        for index, vertex_id in enumerate(selected_ids)
    }
    data["vertex_selection_label_counter"] = len(selected_ids) + 1


def clear_existing_union_state(data: dict) -> dict:
    kept_actions = []
    removed_count = 0
    cleared_unions = []
    seen_unions = set()
    for action_func, action_args, action_kwargs in data["session"].actions:
        action_name = getattr(action_func, "__name__", "").lower()
        if "union" in action_name or "combined" in action_name:
            removed_count += 1
            if "draw_union" in action_name and len(action_args) >= 3:
                regions = tuple(sorted(
                    str(getattr(face, "letter", "?"))
                    for face in action_args[1:3]
                ))
                if regions not in seen_unions:
                    seen_unions.add(regions)
                    cleared_unions.append(list(regions))
        else:
            kept_actions.append((action_func, action_args, action_kwargs))
    data["session"].actions = kept_actions
    data["union_buffer"] = []
    data["last_active_id"] = "none"
    data["v_start"] = None
    data["v_start_id"] = ""
    return {
        "removed_actions": removed_count,
        "cleared_unions": cleared_unions,
    }


def find_vertex_by_id(res_map, vertex_id):
    for v in res_map.vertices:
        if str(getattr(v, "num", id(v))) == str(vertex_id):
            return v
    return None


def same_vertex(a, b):
    if a is None or b is None:
        return False
    return a is b or getattr(a, "num", None) == getattr(b, "num", None)


def vertex_labeled_name(sess, vertex):
    for action_func, action_args, action_kwargs in reversed(sess.actions):
        action_name = getattr(action_func, "__name__", "")
        if action_name in {
            getattr(tool_draw_labeled_vertex_axis, "__name__", ""),
            getattr(tool_draw_labeled_vertex_ray, "__name__", ""),
        }:
            if action_args and same_vertex(action_args[0], vertex) and len(action_args) > 1:
                return str(action_args[1])
            continue
        if action_name != getattr(tool_label_vertex, "__name__", ""):
            continue
        if not action_args or not same_vertex(action_args[0], vertex):
            continue
        if len(action_args) > 1 and action_args[1]:
            return str(action_args[1])
        action_kwargs = action_kwargs or {}
        for key in ("label", "name"):
            value = action_kwargs.get(key)
            if value:
                return str(value)
        auto_label = action_kwargs.get("auto_label") or action_kwargs.get("auto_enumerate_label")
        if auto_label:
            return str(auto_label)
        # AnnotationSession auto-enumerates vertex labels in action order.
        count = 0
        for prev_func, prev_args, prev_kwargs in sess.actions:
            if getattr(prev_func, "__name__", "") == getattr(tool_label_vertex, "__name__", "") and prev_args:
                count += 1
                if same_vertex(prev_args[0], vertex):
                    return f"v{count}"
    return None


def vertex_meeting_name(vertex):
    region_names = []
    seen = set()
    for edge in getattr(vertex, "outarcs", []):
        for face in [edge.leftFace, edge.reverse.leftFace if hasattr(edge, "reverse") else None]:
            if not face or not getattr(face, "bounded", False):
                continue
            if id(face) in seen:
                continue
            seen.add(id(face))
            region_names.append(str(getattr(face, "letter", "?")))
    if region_names:
        return f"v ({'|'.join(region_names)})"
    return "selected vertex"


def vertex_display_name(sess, vertex):
    return vertex_labeled_name(sess, vertex) or vertex_meeting_name(vertex)


def find_face_by_cache_idx(res_map, face_idx):
    for face in res_map.faces:
        if hasattr(face, "_cache_idx") and str(face._cache_idx) == str(face_idx):
            return face
    return None


def find_edge_by_vertex_ids(res_map, tail_id, head_id):
    for edge in res_map.edges:
        t = int(getattr(edge.tail, "num", id(edge.tail)))
        h = int(getattr(edge.head, "num", id(edge.head)))
        if (t == int(tail_id) and h == int(head_id)) or (t == int(head_id) and h == int(tail_id)):
            return edge
    return None


def grouped_visual_edge_endpoints(session, selected_edge):
    """Return the farthest endpoints across all live segments of a visual edge."""
    if selected_edge is None:
        return None, None, []
    target_root = getattr(selected_edge, "trueEdge", selected_edge)
    selected_reverse = getattr(selected_edge, "reverse", None)
    target_reverse_root = (
        getattr(selected_reverse, "trueEdge", selected_reverse)
        if selected_reverse is not None
        else None
    )
    hidden_ids = session.get_active_hidden_edges()
    segments = []
    seen_pairs = set()
    for edge in session.res_map.edges:
        reverse_edge = getattr(edge, "reverse", None)
        pair = tuple(
            sorted((id(edge), id(reverse_edge) if reverse_edge else id(edge)))
        )
        if pair in seen_pairs:
            continue
        if (
            id(edge) in hidden_ids
            or (reverse_edge is not None and id(reverse_edge) in hidden_ids)
        ):
            continue
        edge_root = getattr(edge, "trueEdge", edge)
        reverse_root = (
            getattr(reverse_edge, "trueEdge", reverse_edge)
            if reverse_edge is not None
            else None
        )
        if (
            edge_root not in {target_root, target_reverse_root}
            and reverse_root not in {target_root, target_reverse_root}
        ):
            continue
        seen_pairs.add(pair)
        segments.append(edge)

    if not segments:
        segments = [selected_edge]
    vertices = []
    seen_vertices = set()
    for edge in segments:
        for vertex in (edge.tail, edge.head):
            vertex_id = str(getattr(vertex, "num", id(vertex)))
            if vertex_id not in seen_vertices:
                seen_vertices.add(vertex_id)
                vertices.append(vertex)
    if len(vertices) < 2:
        return selected_edge.tail, selected_edge.head, segments

    best_pair = (vertices[0], vertices[1])
    best_distance = -1.0
    for index, first in enumerate(vertices):
        for second in vertices[index + 1:]:
            distance = distance_between_points(first.p, second.p)
            if distance > best_distance:
                best_distance = distance
                best_pair = (first, second)
    return best_pair[0], best_pair[1], segments


def edge_segment_keys(edges):
    """Return direction-independent vertex-ID pairs for an edge segment list."""
    return {
        tuple(sorted((
            str(getattr(edge.tail, "num", id(edge.tail))),
            str(getattr(edge.head, "num", id(edge.head))),
        )))
        for edge in edges
    }


def persistent_edge_label(session, selected_edge):
    """Reuse the e-label already assigned to the same grouped visual edge."""
    if selected_edge is None:
        return None
    _source_a, _source_b, selected_segments = grouped_visual_edge_endpoints(
        session,
        selected_edge,
    )
    selected_keys = edge_segment_keys(selected_segments)
    hidden_edge_ids = session.get_active_hidden_edges()
    for action_func, action_args, _action_kwargs in reversed(session.actions):
        action_name = getattr(action_func, "__name__", "").lower()
        if "label_edge" not in action_name or len(action_args) < 3:
            continue
        if session.is_marker_obsolete(action_func, action_args, hidden_edge_ids):
            continue
        stored_edges = action_args[1]
        if not isinstance(stored_edges, list):
            stored_edges = [stored_edges]
        if edge_segment_keys(stored_edges) == selected_keys:
            return action_args[2]
    return None


def polygon_area_for_face(face):
    pts = [v.p for v in face.vertices]
    if len(pts) < 3:
        return 0.0
    total = 0.0
    for i, point in enumerate(pts):
        next_point = pts[(i + 1) % len(pts)]
        total += point.x * next_point.y - next_point.x * point.y
    return abs(total) / 2.0


def distance_between_points(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def interior_angle_degrees(face, vertex):
    verts = list(face.vertices)
    idx = next((i for i, v in enumerate(verts) if v is vertex or getattr(v, "num", None) == getattr(vertex, "num", None)), -1)
    if idx < 0 or len(verts) < 3:
        return None
    prev_v = verts[(idx - 1) % len(verts)]
    next_v = verts[(idx + 1) % len(verts)]
    ax, ay = prev_v.p.x - vertex.p.x, prev_v.p.y - vertex.p.y
    bx, by = next_v.p.x - vertex.p.x, next_v.p.y - vertex.p.y
    dot = ax * bx + ay * by
    mag = math.hypot(ax, ay) * math.hypot(bx, by)
    if mag <= 1e-12:
        return None
    cos_value = max(-1.0, min(1.0, dot / mag))
    return math.degrees(math.acos(cos_value))


def union_boundary_vertices(sess, face):
    """Return the ordered outer boundary of the union containing *face*."""
    union_group = sess.get_union_group(face) if face and hasattr(sess, "get_union_group") else None
    if not union_group:
        return []
    func, args, _kwargs = union_group
    if "draw_union" not in func.__name__.lower() or len(args) < 3:
        return []
    union_faces = [args[1], args[2]]
    union_face_ids = {id(item) for item in union_faces}
    adjacency = {}
    vertices_by_id = {}
    seen_edges = set()
    for union_face in union_faces:
        for edge in union_face.edges:
            reverse = getattr(edge, "reverse", None)
            other_face = reverse.leftFace if reverse else None
            if other_face is not None and id(other_face) in union_face_ids:
                continue
            tail_id = str(getattr(edge.tail, "num", id(edge.tail)))
            head_id = str(getattr(edge.head, "num", id(edge.head)))
            edge_key = tuple(sorted((tail_id, head_id)))
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            vertices_by_id[tail_id] = edge.tail
            vertices_by_id[head_id] = edge.head
            adjacency.setdefault(tail_id, []).append(head_id)
            adjacency.setdefault(head_id, []).append(tail_id)
    if len(adjacency) < 3 or any(len(neighbors) != 2 for neighbors in adjacency.values()):
        return []
    start = next(iter(adjacency))
    ordered_ids = []
    previous = None
    current = start
    for _ in range(len(adjacency) + 1):
        ordered_ids.append(current)
        neighbors = adjacency[current]
        next_id = neighbors[0] if neighbors[0] != previous else neighbors[1]
        if next_id == start:
            break
        previous, current = current, next_id
    if len(ordered_ids) != len(adjacency):
        return []
    boundary = [vertices_by_id[vertex_id] for vertex_id in ordered_ids]
    # A merge can turn a former corner into a point lying on one straight
    # outer boundary.  Such a 180-degree point is not an angle of Region U.
    changed = True
    while changed and len(boundary) >= 3:
        changed = False
        simplified = []
        for i, current in enumerate(boundary):
            previous = boundary[(i - 1) % len(boundary)]
            following = boundary[(i + 1) % len(boundary)]
            incoming = (current.p.x - previous.p.x, current.p.y - previous.p.y)
            outgoing = (following.p.x - current.p.x, following.p.y - current.p.y)
            cross = incoming[0] * outgoing[1] - incoming[1] * outgoing[0]
            dot = incoming[0] * outgoing[0] + incoming[1] * outgoing[1]
            scale = max(math.hypot(*incoming) * math.hypot(*outgoing), 1e-12)
            if abs(cross) <= 1e-7 * scale and dot > 0:
                changed = True
                continue
            simplified.append(current)
        boundary = simplified
    return boundary


def interior_angle_for_vertices(vertices, vertex):
    """Measure a polygon interior angle, including reflex angles."""
    target_id = str(getattr(vertex, "num", id(vertex)))
    idx = next(
        (i for i, item in enumerate(vertices)
         if str(getattr(item, "num", id(item))) == target_id),
        -1,
    )
    if idx < 0 or len(vertices) < 3:
        return None
    area_twice = sum(
        item.p.x * vertices[(i + 1) % len(vertices)].p.y
        - vertices[(i + 1) % len(vertices)].p.x * item.p.y
        for i, item in enumerate(vertices)
    )
    prev_v = vertices[(idx - 1) % len(vertices)]
    curr_v = vertices[idx]
    next_v = vertices[(idx + 1) % len(vertices)]
    incoming = (curr_v.p.x - prev_v.p.x, curr_v.p.y - prev_v.p.y)
    outgoing = (next_v.p.x - curr_v.p.x, next_v.p.y - curr_v.p.y)
    turn = math.degrees(math.atan2(
        incoming[0] * outgoing[1] - incoming[1] * outgoing[0],
        incoming[0] * outgoing[0] + incoming[1] * outgoing[1],
    ))
    interior = 180.0 - turn if area_twice > 0 else 180.0 + turn
    return interior % 360.0


def measured_angle_degrees(sess, face, vertex):
    union_vertices = union_boundary_vertices(sess, face)
    if union_vertices:
        return interior_angle_for_vertices(union_vertices, vertex), "Region U"
    return interior_angle_degrees(face, vertex), f"Region {getattr(face, 'letter', '?')}"


def faces_for_region_measure(sess, face):
    if face and hasattr(sess, "get_union_group"):
        union_group = sess.get_union_group(face)
        if union_group:
            func, args, kwargs = union_group
            if "draw_union" in func.__name__.lower() and len(args) >= 3:
                # draw_union stores (res_map, face_a, face_b, label_cache,
                # maxX, maxY).  Only the two faces belong in the area sum.
                return list(args[1:3])
    return [face] if face else []


def measure_region(sess, face):
    faces = [f for f in faces_for_region_measure(sess, face) if f is not None]
    area = sum(polygon_area_for_face(f) for f in faces)
    label = "Union" if len(faces) > 1 else f"Region {getattr(face, 'letter', '?')}"
    return {
        "kind": "region",
        "label": label,
        "area": round(area, 4),
        "face_count": len(faces),
    }


def edge_measure_segments(sess, edge):
    if edge is None:
        return []
    target_root = getattr(edge, "trueEdge", edge)
    target_rev_root = getattr(edge.reverse, "trueEdge", edge.reverse) if hasattr(edge, "reverse") else None
    hover_faces = []
    for face in [edge.leftFace, edge.reverse.leftFace if hasattr(edge, "reverse") else None]:
        if not face or not face.bounded:
            continue
        if face not in hover_faces:
            hover_faces.append(face)
        for action_func, action_args, action_kwargs in sess.actions:
            if "draw_union" in action_func.__name__.lower() and len(action_args) >= 3:
                fa, fb = action_args[1], action_args[2]
                if face == fa and fb not in hover_faces:
                    hover_faces.append(fb)
                elif face == fb and fa not in hover_faces:
                    hover_faces.append(fa)

    segments = []
    seen = set()
    for face in hover_faces:
        for e in face.edges:
            s_id = id(e)
            s_rev_id = id(e.reverse) if hasattr(e, "reverse") else None
            seg_pair = tuple(sorted([s_id, s_rev_id or s_id]))
            if seg_pair in seen:
                continue
            if getattr(e, "trueEdge", e) == target_root or (
                target_rev_root and getattr(e, "trueEdge", e) == target_rev_root
            ):
                seen.add(seg_pair)
                segments.append(e)
    return segments or [edge]


def measure_edge(sess, edge):
    segments = edge_measure_segments(sess, edge)
    length = sum(distance_between_points(e.tail.p, e.head.p) for e in segments)
    return {
        "kind": "edge",
        "label": "Edge",
        "length": round(length, 4),
        "segment_count": len(segments),
    }


def set_last_measurement(data, result):
    data["last_measurement"] = result
    data["last_run_message"] = ""


def next_line_label(data):
    counter = int(data.get("line_label_counter", 1))
    data["line_label_counter"] = counter + 1
    return f"L{counter}"


def show_completed_demo_step(data: dict) -> None:
    """Show the current guided practice task completed with its expected inputs."""
    demo_step = int(data.get("demo_step", 0))
    if demo_step not in DEMO_STEPS or demo_step == 2:
        return

    clear_canvas_state(data)
    sess = data["session"]
    faces = {
        face.letter: face
        for face in sess.res_map.faces
        if getattr(face, "bounded", False)
    }
    face_b = faces.get("B")
    face_c = faces.get("C")
    face_d = faces.get("D")
    if not face_b or not face_c or not face_d:
        return

    left_b = min(face_b.vertices, key=lambda vertex: vertex.p.x)
    right_d = max(face_d.vertices, key=lambda vertex: vertex.p.x)
    left_b_id = str(getattr(left_b, "num", id(left_b)))
    right_d_id = str(getattr(right_d, "num", id(right_d)))
    tutorial_entry = start_tutorial_step(data)
    if tutorial_entry is not None:
        tutorial_entry["used_completed_example"] = True
        tutorial_entry["completed_example_requested_at"] = _ts()
    log_action(data, "show_completed_example", {
        "demo_step": demo_step,
        "used_completed_example": True,
    })

    if demo_step == 3:
        vertex_label = available_marker_labels(sess, "vertex", "v", 1)[0]
        sess.add_vertex_action(left_b, label=vertex_label, auto_enumerate=False)
        log_action(data, "commit_vertex", {
            "vertex_id": left_b_id,
            "label": vertex_label,
        })
    elif demo_step == 4:
        vertex_labels = available_marker_labels(sess, "vertex", "v", 2)
        line_label = next_line_label(data)
        sess.add_action(
            tool_draw_labeled_vertex_segment,
            left_b,
            vertex_labels[0],
            right_d,
            vertex_labels[1],
            line_label,
        )
        log_action(data, "confirm_connection", {
            "from": left_b_id,
            "to": right_d_id,
            "from_label": vertex_labels[0],
            "to_label": vertex_labels[1],
            "line": line_label,
        })
    elif demo_step == 5:
        vertex_label = available_marker_labels(sess, "vertex", "v", 1)[0]
        line_label = next_line_label(data)
        sess.add_auxiliary_line_action(
            tool_draw_labeled_vertex_ray,
            left_b,
            vertex_label,
            "right",
            line_label,
        )
        log_action(data, "commit_ray", {
            "vertex_id": left_b_id,
            "vertex_label": vertex_label,
            "direction": "right",
            "line": line_label,
        })
    elif demo_step == 6:
        shared_edge_ids = get_shared_edges(face_b, face_c)
        target_edge = next(
            (edge for edge in face_b.edges if id(edge) in shared_edge_ids),
            None,
        )
        if target_edge is None:
            return
        line_label = next_line_label(data)
        sess.add_auxiliary_line_action(
            tool_draw_extended_edge,
            target_edge,
            label=line_label,
        )
        log_action(data, "extend_edge", {
            "tail": int(getattr(target_edge.tail, "num", id(target_edge.tail))),
            "head": int(getattr(target_edge.head, "num", id(target_edge.head))),
            "edge": available_marker_labels(sess, "edge", "e", 1)[0],
            "line": line_label,
        })
    elif demo_step == 7:
        length = distance_between_points(left_b.p, right_d.p)
        result = {
            "kind": "distance",
            "label": "Distance between vertices",
            "length": round(length, 4),
            "from_vertex_id": left_b_id,
            "to_vertex_id": right_d_id,
            "from_label": "v1",
            "to_label": "v2",
        }
        set_last_measurement(data, result)
        log_action(data, "measure_distance", result)
    elif demo_step == 8:
        face_a = faces.get("A")
        face_e = faces.get("E")
        if not face_a or not face_e or not get_shared_edges(face_a, face_e):
            return
        sess.add_union_action(face_a, face_e, maxX=1.0, maxY=1.0)
        data["last_run_message"] = ""
        log_action(data, "execute_union", {"faces": ["A", "E"]})

    data["selected_vertex_ids"] = []
    data["selected_region_indices"] = []
    data["selected_angle"] = None
    data["selected_edge"] = None
    data["selected_angles"] = []
    data["selected_edges"] = []
    sync_vertex_selection_labels(data)
    save_session(data)


def sync_line_label_counter(data):
    """Set the next line label from the auxiliary lines still visible."""
    highest = 0
    for _func, _args, kwargs in data["session"].actions:
        label = kwargs.get("label") if isinstance(kwargs, dict) else None
        if "labeled_vertex_segment" in getattr(_func, "__name__", "").lower() and len(_args) > 4:
            label = _args[4]
        elif "labeled_vertex_axis" in getattr(_func, "__name__", "").lower() and len(_args) > 3:
            label = _args[3]
        elif "labeled_vertex_ray" in getattr(_func, "__name__", "").lower() and len(_args) > 3:
            label = _args[3]
        match = re.fullmatch(r"L(\d+)", str(label or ""))
        if match:
            highest = max(highest, int(match.group(1)))
    data["line_label_counter"] = highest + 1


def format_measurement_display(measurement: dict):
    kind = measurement.get("kind", "measurement")
    if kind == "region":
        value = measurement.get("area", "")
        unit = "area units"
        detail = ""
    elif kind == "angle":
        value = measurement.get("degrees", "")
        unit = "degrees"
        detail = ""
    elif kind == "edge":
        value = measurement.get("length", "")
        unit = "length units"
        detail = f"Segments measured: {measurement.get('segment_count', 1)}"
    elif kind == "distance":
        value = measurement.get("length", "")
        unit = "length units"
        from_label = measurement.get("from_label") or f"vertex {measurement.get('from_vertex_id', '?')}"
        to_label = measurement.get("to_label") or f"vertex {measurement.get('to_vertex_id', '?')}"
        detail = f"From {from_label} to {to_label}"
    else:
        value = measurement
        unit = ""
        detail = ""
    return {
        "label": measurement.get("label", kind.title()),
        "value": value,
        "unit": unit,
        "detail": detail,
    }


def participant_output_for_action(entry: dict, angle_number=None, vertex_labels=None):
    """Return a concise participant-facing result for an executed tool action."""
    action = entry.get("action", "")
    detail = entry.get("detail", {})
    detail_dict = detail if isinstance(detail, dict) else {}
    if action == "commit_vertex":
        vertex_id = str(detail_dict.get("vertex_id", ""))
        vertex_label = detail_dict.get("label") or (vertex_labels or {}).get(vertex_id)
        return f"Highlighted vertex {vertex_label}." if vertex_label else "Highlighted a vertex."
    if action == "commit_angle":
        angle_label = detail_dict.get("label") or (f"a{angle_number}" if angle_number is not None else "an angle")
        return f"Highlighted {angle_label} in Region {detail_dict.get('face', '?')}."
    if action == "commit_edge":
        return f"Highlighted an edge of Region {detail_dict.get('face', '?')}."
    if action in {"commit_region", "commit_union_highlight"}:
        face = detail_dict.get("face") if detail_dict else ""
        legacy_detail = detail_dict.get("message", "") if detail_dict else detail
        if not face and isinstance(legacy_detail, str):
            match = re.search(r"face=([^\s]+)", legacy_detail)
            face = match.group(1) if match else "?"
        if action == "commit_union_highlight":
            face = "U"
        return f"Highlighted Region {face or '?'}."
    if action == "confirm_connection":
        from_label = detail_dict.get("from_label") or (vertex_labels or {}).get(str(detail_dict.get("from", "")))
        to_label = detail_dict.get("to_label") or (vertex_labels or {}).get(str(detail_dict.get("to", "")))
        endpoints = f"{from_label} and {to_label}" if from_label and to_label else "two vertices"
        return f"Drew {detail_dict.get('line', 'a line')} between {endpoints}."
    if action == "commit_axis_h":
        vertex_label = detail_dict.get("vertex_label") or (vertex_labels or {}).get(str(detail_dict.get("vertex_id", "")))
        origin = f" through vertex {vertex_label}" if vertex_label else ""
        return f"Drew horizontal line {detail_dict.get('line', '')}{origin}.".replace(" .", ".")
    if action == "commit_axis_v":
        vertex_label = detail_dict.get("vertex_label") or (vertex_labels or {}).get(str(detail_dict.get("vertex_id", "")))
        origin = f" through vertex {vertex_label}" if vertex_label else ""
        return f"Drew vertical line {detail_dict.get('line', '')}{origin}.".replace(" .", ".")
    if action == "commit_ray":
        vertex_label = detail_dict.get("vertex_label") or (vertex_labels or {}).get(str(detail_dict.get("vertex_id", "")))
        origin = f" from vertex {vertex_label}" if vertex_label else ""
        direction = detail_dict.get("direction", "")
        return f"Drew {direction}ward ray {detail_dict.get('line', '')}{origin}.".replace(" .", ".")
    if action == "extend_edge":
        edge_label = detail_dict.get("edge")
        line_label = detail_dict.get("line", "")
        if edge_label:
            return f"Extended edge {edge_label} in both directions as line {line_label}."
        return f"Extended an edge in both directions as line {line_label}.".replace(" line .", ".")
    if action == "execute_union":
        faces = detail_dict.get("faces", [])
        return f"Created the union of Regions {' and '.join(faces)}."
    if action == "measure_distance" and detail_dict:
        return f"Measured distance between the two selected vertices: {detail_dict.get('length', '')} length units."
    if action.startswith("measure_") and detail_dict:
        display = format_measurement_display(detail_dict)
        result = f"Measured {display['label']}: {display['value']} {display['unit']}".strip() + "."
        if display["detail"]:
            result += f" {display['detail']}."
        return result
    if action == "undo":
        return "Undid the most recent annotation."
    if action == "clear_all":
        return None
    return None


def render_output_panel(data: dict) -> None:
    """Render participant-facing tool results after component actions are handled."""
    st.markdown(
        '<div style="font-size:1.25rem; font-weight:600; margin:0.45rem 0 0.25rem 0;">Output</div>',
        unsafe_allow_html=True,
    )
    if (
        data.get("phase") == "demo"
        and data.get("demo_step") in DEMO_STEPS
        and data.get("demo_step") != 2
    ):
        st.markdown(
            '<div style="background:#eff6ff; color:#1e3a8a; '
            'border:1px solid #bfdbfe; border-radius:0.5rem; '
            'padding:0.55rem 0.7rem; margin:0.55rem 0 0.7rem; font-size:0.9rem;">'
            'After you click <strong>RUN</strong>, the result will appear here.'
            '</div>',
            unsafe_allow_html=True,
        )
    current_output_entries = []
    angle_output_count = 0
    output_vertex_labels = {}
    current_question_id = data.get("current_question", {}).get("question_id", "")
    current_trial = data.get("current_trial_index", 0)
    for entry in data.get("action_log", []):
        if entry.get("question_id", "") != current_question_id:
            continue
        if data.get("phase") == "survey" and entry.get("trial_index") != current_trial:
            continue
        if entry.get("action") == "clear_all":
            current_output_entries = []
            angle_output_count = 0
            output_vertex_labels = {}
            continue
        if entry.get("action") == "undo":
            undo_detail = entry.get("detail", {})
            target_event_id = (
                undo_detail.get("target_event_id")
                if isinstance(undo_detail, dict)
                else None
            )
            current_output_entries = [
                (event_id, text)
                for event_id, text in current_output_entries
                if event_id != target_event_id
            ]
            participant_output = participant_output_for_action(entry)
            if participant_output:
                current_output_entries.append(
                    (entry.get("event_id"), participant_output)
                )
            continue
        if entry.get("action") == "select_vertex":
            selection_detail = entry.get("detail", {})
            if isinstance(selection_detail, dict):
                vertex_id = str(selection_detail.get("vertex_id", ""))
                label = selection_detail.get("label")
                if vertex_id and label:
                    output_vertex_labels[vertex_id] = label
        elif entry.get("action") == "deselect_vertex":
            selection_detail = entry.get("detail", {})
            if isinstance(selection_detail, dict):
                output_vertex_labels.pop(str(selection_detail.get("vertex_id", "")), None)
        if entry.get("action") == "commit_angle":
            angle_output_count += 1
        participant_output = participant_output_for_action(
            entry,
            angle_number=angle_output_count if entry.get("action") == "commit_angle" else None,
            vertex_labels=output_vertex_labels,
        )
        if participant_output:
            current_output_entries.append(
                (entry.get("event_id"), participant_output)
            )
    if not current_output_entries:
        st.caption("(results will appear here)")
    else:
        for _, participant_output in reversed(current_output_entries[-25:]):
            st.markdown(f"- {participant_output}")

data = load_or_create_session()
sess = data["session"]
data.setdefault("phase", "demo")
data.setdefault("survey_form", SURVEY_FORM)
data.setdefault("landing_choice_made", False)
data.setdefault("entry_route", "tutorial")
data.setdefault("demo_step", 0)
data.setdefault("demo_pending_completion", None)
data.setdefault("demo_direction_answered", False)
data.setdefault("demo_direction_correct", None)
data.setdefault("demo_incorrect_target_message", "")
data.setdefault("demo_start_time", _ts())
data.setdefault("demo_end_time", "")
data.setdefault("survey_start_time", "")
data.setdefault("trials", [])
data.setdefault("current_trial_index", 0)
data.setdefault("current_question", get_current_question(data))
data.setdefault("condition", SURVEY_CONDITION)
data.setdefault("survey_instance", SURVEY_INSTANCE_ID)
data.setdefault("current_answer", "")
data.setdefault("answer_feedback", None)
data.setdefault("completed", False)
data.setdefault("post_survey_completed", False)
data.setdefault("post_survey_responses", {})
data.setdefault("post_survey_missing_required", [])
data.setdefault("ended_by", "")
data.setdefault("survey_end_time", "")
data.setdefault("dataset_path", DATASET_PATH)
data.setdefault("dataset_metadata", DATASET_METADATA)
data.setdefault("dataset_version", DATASET_METADATA.get("dataset_version", "unknown"))
data.setdefault("dataset_role", DATASET_METADATA.get("dataset_role", "unknown"))
data.setdefault("current_notes", "")
data.setdefault("last_measurement", None)
data.setdefault("last_run_message", "")
data.setdefault("timer_hidden", False)
data.setdefault("definitions_open", False)
data.setdefault("tools_guide_open", False)
data.setdefault("line_label_counter", 1)
data.setdefault("measure_kind", {"Vertex": "distance", "Angle": "angle", "Region": "area"}.get(data.get("tool_mode"), "distance"))
data.setdefault("selected_vertex_ids", [])
data.setdefault("selected_region_indices", [])
data.setdefault("selection_undo_stack", [])
data.setdefault("selected_angle", None)
data.setdefault("selected_edge", None)
data.setdefault("selected_angles", [data["selected_angle"]] if data.get("selected_angle") else [])
data.setdefault("selected_edges", [data["selected_edge"]] if data.get("selected_edge") else [])
data.setdefault("vertex_selection_labels", {})
data.setdefault("vertex_selection_label_counter", 1)
data.setdefault("demo_selected_types", [])
data.setdefault("tutorial_summary", {
    "started_at": data.get("demo_start_time") or _ts(),
    "completed_at": (
        data.get("demo_end_time") or None
        if data.get("phase") == "survey" or data.get("demo_end_time")
        else None
    ),
    "completion_status": (
        "completed"
        if data.get("phase") == "survey" or data.get("demo_end_time")
        else "in_progress"
    ),
    "completion_method": (
        "guided_tutorial"
        if data.get("phase") == "survey" or data.get("demo_end_time")
        else None
    ),
    "guided_completed_at": (
        data.get("demo_end_time") or None
        if data.get("phase") == "survey" or data.get("demo_end_time")
        else None
    ),
    "free_exploration_started_at": None,
    "free_exploration_completed_at": None,
    "steps": {},
    "free_exploration_tool_calls": {
        "total_tool_calls": 0,
        "tool_counts": {},
        "error_count": 0,
    },
})
if data.get("phase") == "demo":
    start_tutorial_step(data)
sync_vertex_selection_labels(data)
data["time_limit_seconds"] = None

# Keep the complete survey workspace within a typical laptop viewport.
st.markdown(
    """
    <style>
        .stMainBlockContainer {
            padding-top: 3.25rem;
            padding-bottom: 0.5rem;
        }
        div[data-testid="stVerticalBlock"] {
            gap: 0.65rem;
        }
        div[data-testid="stForm"] {
            padding: 0.8rem 0.9rem 0.85rem !important;
        }
        div[data-testid="stForm"] label {
            margin-bottom: 0.1rem !important;
        }
        div[data-testid="stForm"] div[data-testid="stTextArea"] textarea {
            min-height: 42px !important;
            height: 42px !important;
            padding-top: 0.45rem !important;
            padding-bottom: 0.45rem !important;
        }
        div[data-testid="stForm"] button {
            min-height: 2.25rem !important;
            padding-top: 0.35rem !important;
            padding-bottom: 0.35rem !important;
        }
        h1, h2, h3 {
            margin-top: 0.2rem !important;
            margin-bottom: 0.35rem !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- BACKEND ROUTER ---
query_params = dict(st.query_params)

if data.get("completed") and data.get("post_survey_completed"):
    result_path = data.get("result_file") or save_results(data)
    data["result_file"] = result_path
    save_session(data)
    st.title("Survey Complete")
    st.write("Thank you. Your responses have been saved.")
    if result_path == "Postgres":
        st.caption("Your response was stored securely.")
    else:
        st.caption(f"Saved result file: {result_path}")
    st.stop()

if data.get("completed") and not data.get("post_survey_completed"):
    # Save the completed formal survey before collecting the questionnaire;
    # submission below upserts the same participant record with these answers.
    data["result_file"] = save_results(data)
    save_session(data)
    st.caption("Post-survey questionnaire")
    st.title("Tell us about your experience")
    st.markdown(
        "Please answer the following questions about your experience with the tutorial, "
        "survey, and tools."
    )
    st.markdown(
        """
        <style>
        div[data-testid="stForm"] div[role="radiogroup"]:has(> label:nth-child(5)) {
            display:grid !important; grid-template-columns:repeat(5,1fr) !important;
            gap:0 !important; width:min(100%,380px) !important;
        }
        div[data-testid="stForm"] div[role="radiogroup"]:has(> label:nth-child(5)) > label {
            margin:0 !important; width:100% !important; justify-content:center !important;
        }
        div[data-testid="stForm"] div[data-testid="stTextArea"] textarea {
            min-height:100px !important; height:100px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    missing_post_fields = set(data.get("post_survey_missing_required", []))

    def show_post_required_message(key):
        if key in missing_post_fields:
            st.markdown(
                "<div style='color:#d32f2f;font-size:0.875rem;margin-top:-0.6rem;"
                "margin-bottom:0.8rem'>Please select a response.</div>",
                unsafe_allow_html=True,
            )

    def post_five_point_scale(prompt, key):
        st.markdown(f"**{prompt}**")
        value = st.radio(
            prompt, [1, 2, 3, 4, 5], index=None, horizontal=True,
            label_visibility="collapsed", key=key,
        )
        st.markdown(
            "<div style='width:min(100%,380px);display:grid;grid-template-columns:1fr 1fr 1fr;"
            "color:#6b7280;font-size:0.875rem;margin-top:-0.4rem;margin-bottom:1rem'>"
            "<div>Strongly disagree</div><div style='text-align:center'>Neutral</div>"
            "<div style='text-align:right'>Strongly agree</div></div>",
            unsafe_allow_html=True,
        )
        show_post_required_message(key)
        return value

    post_widget_fields = {
        "annotation_post_tutorial_clarity": "tutorial_easy_to_understand",
        "annotation_post_instruction_clarity": "instructions_clear",
        "annotation_post_tools_easy": "tools_easy_to_use",
        "annotation_post_tools_useful": "tools_useful_for_answering",
        "annotation_post_questions_easy": "questions_easy_to_answer",
        "annotation_post_length": "survey_length_appropriate",
        "annotation_post_assistance": "used_external_assistance",
        "annotation_post_assistance_details": "external_assistance_details",
        "annotation_post_technical": "experienced_technical_issues",
        "annotation_post_technical_details": "technical_issue_details",
        "annotation_post_other": "other_feedback",
    }
    saved_post = data.get("post_survey_responses", {})
    if "annotation_post_other" not in st.session_state:
        saved_feedback = [
            str(saved_post.get(key, "")).strip()
            for key in ("other_feedback", "ambiguous_questions", "difficult_tools")
        ]
        combined_saved_feedback = "\n\n".join(
            feedback for feedback in saved_feedback if feedback
        )
        if combined_saved_feedback:
            st.session_state.annotation_post_other = combined_saved_feedback
    for widget_key, response_key in post_widget_fields.items():
        if widget_key not in st.session_state and response_key in saved_post:
            st.session_state[widget_key] = saved_post[response_key]

    with st.form("annotation_post_survey_questionnaire"):
        if missing_post_fields:
            st.error("Please answer the highlighted questions before continuing.")
        st.caption(
            "Required: For each statement, select 1 (Strongly disagree) "
            "to 5 (Strongly agree)."
        )
        post_five_point_scale(
            "The tutorial was easy to understand.", "annotation_post_tutorial_clarity"
        )
        post_five_point_scale(
            "The instructions in the survey were clear.", "annotation_post_instruction_clarity"
        )
        post_five_point_scale("The tools were easy to operate.", "annotation_post_tools_easy")
        post_five_point_scale(
            "The tools were useful for answering the questions.",
            "annotation_post_tools_useful",
        )
        post_five_point_scale(
            "The survey questions were easy to answer.", "annotation_post_questions_easy"
        )
        post_five_point_scale(
            "The length of the survey was appropriate.", "annotation_post_length"
        )
        st.markdown("**Use of external assistance**")
        st.caption(
            "Your answer will not affect your compensation or survey results. "
            "We ask only to better understand how participants completed the survey."
        )
        st.radio(
            "Did you use any external assistance, such as paper, a calculator, "
            "a search engine, or help from another person, while answering the questions?",
            ["No", "Yes", "Prefer not to say"], index=None, horizontal=True,
            key="annotation_post_assistance",
        )
        show_post_required_message("annotation_post_assistance")
        st.text_input(
            "If yes, what did you use? (Optional)",
            key="annotation_post_assistance_details",
        )
        st.markdown("**Technical issues**")
        st.radio(
            "Did you experience any technical problems while completing the survey?",
            ["No", "Yes"], index=None, horizontal=True, key="annotation_post_technical",
        )
        show_post_required_message("annotation_post_technical")
        st.text_input(
            "If yes, please describe what happened. (Optional)",
            key="annotation_post_technical_details",
        )
        st.markdown("#### Additional feedback")
        st.text_area(
            "Is there anything else you would like us to know? (Optional)",
            key="annotation_post_other",
        )
        submitted_post_survey = st.form_submit_button("Submit Questionnaire", type="primary")

    if submitted_post_survey:
        required_post_fields = [
            "annotation_post_tutorial_clarity",
            "annotation_post_instruction_clarity",
            "annotation_post_tools_easy",
            "annotation_post_tools_useful",
            "annotation_post_questions_easy",
            "annotation_post_length",
            "annotation_post_assistance",
            "annotation_post_technical",
        ]
        missing = [
            key for key in required_post_fields
            if st.session_state.get(key) is None
        ]
        if missing:
            data["post_survey_missing_required"] = missing
            save_session(data)
            st.rerun()
        data["post_survey_missing_required"] = []
        data["post_survey_responses"] = {
            response_key: st.session_state.get(widget_key)
            for widget_key, response_key in post_widget_fields.items()
        }
        if data["post_survey_responses"].get("used_external_assistance") == "No":
            data["post_survey_responses"]["external_assistance_details"] = ""
        if data["post_survey_responses"].get("experienced_technical_issues") == "No":
            data["post_survey_responses"]["technical_issue_details"] = ""
        data["post_survey_responses"].update(
            {"placement": "post_survey", "submitted_at": _ts()}
        )
        data["post_survey_completed"] = True
        data["result_file"] = save_results(data)
        save_session(data)
        st.rerun()
    st.stop()

if not data.get("landing_choice_made"):
    instruction_col, _instruction_space = st.columns([3, 2], gap="small")
    with instruction_col:
        st.title("Survey Instructions")
        st.markdown(
            "In this survey, you will answer questions based on a series of diagrams.\n\n"
            "**Your goal is to answer as many questions correctly as possible.**\n\n"
            "Before the survey begins, you will complete a brief tutorial to help "
            "you become familiar with the task and learn how to use the survey interface.\n\n"
            "The tutorial is for practice only and is not scored.\n\n"
            "Please use only the tools provided within the survey interface. Do not "
            "use any external tools or assistance, including pen and paper, calculators, "
            "other websites, or AI tools.\n\n"
            "Please complete the survey in one sitting using a laptop or desktop computer.\n\n"
            "Click **Start Tutorial** when you are ready."
        )
        if st.button("Start Tutorial", type="primary"):
            start_demo(data)
            data["demo_step"] = 2
            data["tool_mode"] = DEMO_STEPS[2]["tool_mode"]
            data["landing_choice_made"] = True
            data["entry_route"] = "tutorial"
            start_tutorial_step(data, "selection")
            log_action(data, "begin_demo")
            save_session(data)
            st.rerun()
    st.stop()

bridge_action_key = ""
if "bridge_act" in query_params:
    bridge_action_key = str(query_params.get("action_id", ""))

if (
    "bridge_act" in query_params
    and bridge_action_key
    and st.session_state.get("_last_routed_bridge_action") != bridge_action_key
):
    # Query parameters survive Streamlit reruns. Consume each component action
    # only once; otherwise a later selection rerun can execute the previous
    # RUN action again (and draw an apparently random old edge).
    st.session_state["_last_routed_bridge_action"] = bridge_action_key
    act = query_params["bridge_act"]
    tgt_id = query_params.get("bridge_tgt", "none")
    if act in {
        "set_tool_mode", "set_measure_kind",
        "select_vertex", "select_angle", "select_edge", "select_region",
        "remove_selected_vertex", "remove_selected_angle", "remove_selected_edge", "remove_selected_region",
    }:
        data["last_run_message"] = ""

    if act == "set_tool_mode":
        requested_mode = query_params.get("bridge_mode", "Vertex")
        if requested_mode in {"Vertex", "Angle", "Edge", "Region"}:
            data["tool_mode"] = requested_mode
            default_measure_kind = {"Vertex": "distance", "Angle": "angle", "Region": "area"}.get(requested_mode)
            if default_measure_kind:
                data["measure_kind"] = default_measure_kind
            log_action(data, "set_tool_mode", {"mode": requested_mode})
            save_session(data)

    if act == "set_measure_kind":
        requested_kind = query_params.get("bridge_measure_kind", "distance")
        measure_modes = {"distance": "Vertex", "angle": "Angle", "area": "Region"}
        if requested_kind in measure_modes:
            requested_mode = measure_modes[requested_kind]
            data["measure_kind"] = requested_kind
            data["tool_mode"] = requested_mode
            log_action(
                data,
                "set_measure_kind",
                {"kind": requested_kind, "mode": requested_mode},
            )
            save_session(data)

    if act == "practice_select_geom" and data.get("phase") == "demo" and data.get("demo_step") == 2:
        kind = str(query_params.get("bridge_kind", "")).title()
        if kind in {"Region", "Angle", "Vertex", "Edge"}:
            log_action(data, "practice_select_geom", {"kind": kind})
            sync_demo_selected_types(data)
            save_session(data)

    if (
        act == "continue_selection_review"
        and data.get("phase") == "demo"
        and data.get("demo_step") == 2
        and set(sync_demo_selected_types(data)) == set(PRACTICE_REQUIRED_SELECTIONS)
    ):
        mark_tutorial_step_completed(data, "selection")
        clear_canvas_state(data)
        data["demo_selected_types"] = []
        data["demo_step"] = DEMO_CLOCKWISE_STEP
        data["tool_mode"] = "Vertex"
        start_tutorial_step(data, "clockwise")
        save_session(data)
        st.rerun()

    if act == "select_angle":
        face_idx = int(query_params.get("bridge_face", "-1"))
        selected_angles = list(data.get("selected_angles", []))
        selected_angle_marker = available_marker_labels(
            sess, "angle", "a", len(selected_angles) + 1
        )[len(selected_angles)]
        candidate_angle = {
            "vertex_id": str(tgt_id),
            "face_idx": face_idx,
            "face": str(query_params.get("bridge_face_name", "?")),
            "marker_label": selected_angle_marker,
        }
        angle_key = (candidate_angle["vertex_id"], candidate_angle["face_idx"])
        if not any((str(item.get("vertex_id")), int(item.get("face_idx", -1))) == angle_key for item in selected_angles):
            push_selection_undo(data)
            selected_angles.append(dict(candidate_angle))
        data["selected_angle"] = candidate_angle
        data["selected_angles"] = selected_angles
        if data.get("phase") == "demo" and data.get("demo_step") == 2:
            sync_demo_selected_types(data)
        log_action(data, "select_angle", data["selected_angle"])
        save_session(data)
    elif act == "remove_selected_angle":
        remove_index = int(query_params.get("bridge_selection_index", "-1"))
        selected_angles = list(data.get("selected_angles", []))
        if selected_angles or data.get("selected_angle"):
            push_selection_undo(data)
        if not (0 <= remove_index < len(selected_angles)):
            remove_index = len(selected_angles) - 1
        removed = selected_angles.pop(remove_index) if selected_angles else (data.get("selected_angle") or {})
        log_action(data, "deselect_angle", removed)
        data["selected_angles"] = selected_angles
        data["selected_angle"] = dict(selected_angles[-1]) if selected_angles else None
        if data.get("phase") == "demo" and data.get("demo_step") == 2:
            sync_demo_selected_types(data)
        save_session(data)

    if act == "select_edge":
        edge_idx = int(query_params.get("bridge_edge_idx", "-1"))
        tail_id = int(query_params.get("bridge_tail", "-1"))
        head_id = int(query_params.get("bridge_head", "-1"))
        target_edge = (
            sess.res_map.edges[edge_idx]
            if 0 <= edge_idx < len(sess.res_map.edges)
            else find_edge_by_vertex_ids(sess.res_map, tail_id, head_id)
        )
        selected_edge_marker = persistent_edge_label(sess, target_edge)
        if not selected_edge_marker:
            selected_count = len(data.get("selected_edges", []))
            selected_edge_marker = available_marker_labels(
                sess, "edge", "e", selected_count + 1
            )[selected_count]
        candidate_edge = {
            "edge_idx": edge_idx,
            "tail_id": tail_id,
            "head_id": head_id,
            "label": str(query_params.get("bridge_label", "Edge")),
            "marker_label": selected_edge_marker,
        }
        selected_edges = list(data.get("selected_edges", []))
        edge_key = frozenset((candidate_edge["tail_id"], candidate_edge["head_id"]))
        if not any(frozenset((int(item.get("tail_id", -1)), int(item.get("head_id", -1)))) == edge_key for item in selected_edges):
            push_selection_undo(data)
            selected_edges.append(dict(candidate_edge))
        data["selected_edge"] = candidate_edge
        data["selected_edges"] = selected_edges
        if data.get("phase") == "demo" and data.get("demo_step") == 2:
            sync_demo_selected_types(data)
        log_action(data, "select_edge", data["selected_edge"])
        save_session(data)
    elif act == "remove_selected_edge":
        remove_index = int(query_params.get("bridge_selection_index", "-1"))
        selected_edges = list(data.get("selected_edges", []))
        if selected_edges or data.get("selected_edge"):
            push_selection_undo(data)
        if not (0 <= remove_index < len(selected_edges)):
            remove_index = len(selected_edges) - 1
        removed = selected_edges.pop(remove_index) if selected_edges else (data.get("selected_edge") or {})
        log_action(data, "deselect_edge", removed)
        data["selected_edges"] = selected_edges
        data["selected_edge"] = dict(selected_edges[-1]) if selected_edges else None
        if data.get("phase") == "demo" and data.get("demo_step") == 2:
            sync_demo_selected_types(data)
        save_session(data)

    # print(f"🔥 [Bridge] Action: {act} | Target: {tgt_id}")  # COMMENTED OUT

    hidden_edge_ids = sess.get_active_hidden_edges()
    target_v = None
    if tgt_id and tgt_id != "none":
        for v in sess.res_map.vertices:
            if str(getattr(v, "num", id(v))) == str(tgt_id):
                target_v = v
                data["last_active_id"] = str(tgt_id)
                break

    if act in {"commit_vertex", "commit_axis_h", "commit_axis_v", "commit_ray"}:
        selected_ids = [str(value) for value in data.get("selected_vertex_ids", [])]
        if len(selected_ids) == 1:
            selected_id = selected_ids[0]
            target_v = next(
                (v for v in sess.res_map.vertices
                 if str(getattr(v, "num", id(v))) == selected_id),
                target_v,
            )
            tgt_id = selected_id

    if target_v:
        is_obsolete = sess.is_marker_obsolete(tool_label_vertex, [target_v], hidden_edge_ids)
        if not is_obsolete:
            if act == "select_vertex":
                selected_ids = [str(v) for v in data.get("selected_vertex_ids", [])]
                target_id = str(tgt_id)
                if target_id not in selected_ids:
                    push_selection_undo(data)
                    # Selection is a persistent reference list, not the input
                    # buffer of a particular tool.  Keep every distinct vertex;
                    # tools such as Segment and Distance independently require
                    # exactly two selected vertices before RUN is enabled.
                    selected_ids.append(target_id)
                data["selected_vertex_ids"] = selected_ids
                sync_vertex_selection_labels(data)
                if data.get("phase") == "demo" and data.get("demo_step") == 2:
                    sync_demo_selected_types(data)
                log_action(data, "select_vertex", {
                    "vertex_id": target_id,
                    "label": data["vertex_selection_labels"][target_id],
                    "selection": selected_ids,
                })
                save_session(data)

            elif act == "remove_selected_vertex":
                target_id = str(tgt_id)
                if target_id in [str(value) for value in data.get("selected_vertex_ids", [])]:
                    push_selection_undo(data)
                data["selected_vertex_ids"] = [
                    value for value in data.get("selected_vertex_ids", [])
                    if str(value) != target_id
                ]
                sync_vertex_selection_labels(data)
                if data.get("phase") == "demo" and data.get("demo_step") == 2:
                    sync_demo_selected_types(data)
                log_action(data, "deselect_vertex", {"vertex_id": target_id})
                save_session(data)

            elif act == "commit_vertex":
                selected_label = data.get("vertex_selection_labels", {}).get(str(tgt_id))
                sess.add_vertex_action(
                    target_v,
                    label=selected_label,
                    auto_enumerate=selected_label is None,
                )
                log_action(data, "commit_vertex", {
                    "vertex_id": str(tgt_id),
                    "label": selected_label,
                })
                data["selected_vertex_ids"] = []
                sync_vertex_selection_labels(data)
                save_session(data)
                if data.get("phase") == "demo" and data.get("demo_incorrect_target_message"):
                    st.toast("Try the requested vertex", icon="⚠️")

            elif act == "set_start_point":
                data["v_start"] = target_v
                data["v_start_id"] = str(tgt_id)
                log_action(data, "set_start_point", f"vertex_id={tgt_id}")  # NEW
                save_session(data)

            elif act == "confirm_connection":
                selected_ids = [str(v) for v in data.get("selected_vertex_ids", [])]
                selected_vertices = [
                    vertex for selected_id in selected_ids
                    for vertex in sess.res_map.vertices
                    if str(getattr(vertex, "num", id(vertex))) == selected_id
                ]
                if len(selected_vertices) == 2 and selected_vertices[0].p != selected_vertices[1].p:
                    v1, target_v = selected_vertices
                    from_id, tgt_id = selected_ids
                    selected_labels = data.get("vertex_selection_labels", {})
                    from_label = selected_labels.get(from_id)
                    to_label = selected_labels.get(tgt_id)
                    line_label = next_line_label(data)
                    sess.add_action(
                        tool_draw_labeled_vertex_segment,
                        v1,
                        from_label,
                        target_v,
                        to_label,
                        line_label,
                    )
                    log_action(data, "confirm_connection", {
                        "from": from_id,
                        "to": str(tgt_id),
                        "from_label": from_label,
                        "to_label": to_label,
                        "line": line_label,
                    })
                    data["v_start"] = None
                    data["v_start_id"] = ""
                    data["selected_vertex_ids"] = []
                    sync_vertex_selection_labels(data)
                    save_session(data)

            elif act == "commit_axis_h":
                selected_label = data.get("vertex_selection_labels", {}).get(str(tgt_id))
                line_label = next_line_label(data)
                sess.add_auxiliary_line_action(
                    tool_draw_labeled_vertex_axis, target_v, selected_label, "H", line_label
                )
                log_action(data, "commit_axis_h", {
                    "vertex_id": str(tgt_id),
                    "vertex_label": selected_label,
                    "line": line_label,
                })
                data["selected_vertex_ids"] = []
                sync_vertex_selection_labels(data)
                save_session(data)

            elif act == "commit_axis_v":
                selected_label = data.get("vertex_selection_labels", {}).get(str(tgt_id))
                line_label = next_line_label(data)
                sess.add_auxiliary_line_action(
                    tool_draw_labeled_vertex_axis, target_v, selected_label, "V", line_label
                )
                log_action(data, "commit_axis_v", {
                    "vertex_id": str(tgt_id),
                    "vertex_label": selected_label,
                    "line": line_label,
                })
                data["selected_vertex_ids"] = []
                sync_vertex_selection_labels(data)
                save_session(data)

            elif act == "commit_ray":
                direction = str(query_params.get("bridge_direction", "right")).lower()
                if direction not in {"up", "down", "left", "right"}:
                    direction = "right"
                selected_label = data.get("vertex_selection_labels", {}).get(str(tgt_id))
                line_label = next_line_label(data)
                sess.add_auxiliary_line_action(
                    tool_draw_labeled_vertex_ray,
                    target_v,
                    selected_label,
                    direction,
                    line_label,
                )
                log_action(data, "commit_ray", {
                    "vertex_id": str(tgt_id),
                    "vertex_label": selected_label,
                    "direction": direction,
                    "line": line_label,
                })
                data["selected_vertex_ids"] = []
                sync_vertex_selection_labels(data)
                save_session(data)

            elif act == "commit_angle":
                face_idx = int(query_params.get("bridge_face", "-1"))
                target_face = None
                for face in sess.res_map.faces:
                    if hasattr(face, '_cache_idx') and face._cache_idx == face_idx:
                        target_face = face
                        break
                if target_face and target_v:
                    is_union = False
                    union_faces_list = None
                    for action_func, action_args, action_kwargs in sess.actions:
                        if "draw_union" in action_func.__name__.lower() and len(action_args) >= 3:
                            fa, fb = action_args[1], action_args[2]
                            if target_face == fa or target_face == fb:
                                is_union = True
                                union_faces_list = [fa, fb]
                                break
                    
                    if is_union and union_faces_list:
                        union_corners = union_boundary_vertices(sess, target_face)
                        target_id = str(getattr(target_v, "num", id(target_v)))
                        is_union_corner = any(
                            str(getattr(corner, "num", id(corner))) == target_id
                            for corner in union_corners
                        )
                        if not is_union_corner:
                            data["selected_angle"] = None
                            data["selected_angles"] = []
                            save_session(data)
                            st.warning("This point lies on a straight boundary of Region U, so it is not an angle.")
                            angle_label = None
                        else:
                            angle_label = sess._generate_label("angle", "a")
                            sess.add_combined_angle_action(union_corners, target_v, angle_label)
                    else:
                        sess.add_angle_action((target_face, target_v), label=None, auto_enumerate=True)
                        angle_label = sess.actions[-1][1][-1] if sess.actions else None
                    if not is_union or angle_label is not None:
                        log_action(data, "commit_angle", {
                            "vertex_id": str(tgt_id),
                            "face_idx": face_idx,
                            "face": "U" if is_union else getattr(target_face, "letter", "?"),
                            "label": angle_label,
                        })
                        data["selected_angle"] = None
                        data["selected_angles"] = []
                        save_session(data)

        else:
            st.warning(f"Vertex {tgt_id} is obsolete.")

    if act == "commit_edge":
        face_side = query_params.get("bridge_side", "main")
        edge_idx = int(query_params.get("bridge_edge_idx", "-1"))
        tail_id = int(query_params.get("bridge_tail", "-1"))
        head_id = int(query_params.get("bridge_head", "-1"))
        target_e = sess.res_map.edges[edge_idx] if 0 <= edge_idx < len(sess.res_map.edges) else None
        if target_e is None:
            for edge in sess.res_map.edges:
                t = int(getattr(edge.tail, "num", id(edge.tail)))
                h = int(getattr(edge.head, "num", id(edge.head)))
                if (t == tail_id and h == head_id) or (t == head_id and h == tail_id):
                    target_e = edge
                    break
        if target_e:
            f_main = target_e.leftFace
            f_oppo = target_e.reverse.leftFace if hasattr(target_e, 'reverse') else None

            # For frame edges, the bounded face is whichever side is bounded
            if face_side == "main":
                chosen_face = f_main if (f_main and f_main.bounded) else f_oppo
            else:
                chosen_face = f_oppo if (f_oppo and f_oppo.bounded) else f_main

            if chosen_face and chosen_face.bounded:
                target_root = getattr(target_e, "trueEdge", target_e)
                target_rev_root = getattr(target_e.reverse, "trueEdge", target_e.reverse) if hasattr(target_e, 'reverse') else None

                # Add union partner if chosen_face is part of a union
                faces_to_search = [chosen_face]
                for action_func, action_args, action_kwargs in sess.actions:
                    if "draw_union" in action_func.__name__.lower() and len(action_args) >= 3:
                        fa, fb = action_args[1], action_args[2]
                        if chosen_face == fa:
                            faces_to_search.append(fb)
                            break
                        elif chosen_face == fb:
                            faces_to_search.append(fa)
                            break

                face_segments = [
                    e for face in faces_to_search
                    for e in face.edges
                    if getattr(e, "trueEdge", e) == target_root or
                    (target_rev_root and getattr(e, "trueEdge", e) == target_rev_root)
                ]
                # A trueEdge may span both the visible boundary of U and an
                # old constituent seam hidden by the merge.  Highlight only
                # the segments that still exist in the displayed topology.
                active_hidden_edges = sess.get_active_hidden_edges()
                face_segments = [
                    e for e in face_segments
                    if id(e) not in active_hidden_edges
                    and (not hasattr(e, "reverse") or id(e.reverse) not in active_hidden_edges)
                ]

                if face_segments:
                    # print(f"face_side={face_side}, chosen_face={chosen_face.letter}, faces_to_search={[f.letter for f in faces_to_search]}, segments={len(face_segments)}")  # COMMENTED OUT
                    sess.add_edge_action(face_segments, label=None, auto_enumerate=True)
                    adjacent_regions = sorted({
                        getattr(face, "letter", "?")
                        for face in (f_main, f_oppo)
                        if face and face.bounded
                    })
                    log_action(data, "commit_edge", {
                        "side": face_side,
                        "tail": tail_id,
                        "head": head_id,
                        "face": getattr(chosen_face, "letter", "?"),
                        "segments": len(face_segments),
                        "adjacent_regions": adjacent_regions,
                    })
                    data["selected_edge"] = None
                    data["selected_edges"] = []
                    save_session(data)


    elif act == "extend_edge":
        edge_idx = int(query_params.get("bridge_edge_idx", "-1"))
        tail_id = int(query_params.get("bridge_tail", "-1"))
        head_id = int(query_params.get("bridge_head", "-1"))
        target_e = sess.res_map.edges[edge_idx] if 0 <= edge_idx < len(sess.res_map.edges) else None
        if target_e is None:
            for edge in sess.res_map.edges:
                t = int(getattr(edge.tail, "num", id(edge.tail)))
                h = int(getattr(edge.head, "num", id(edge.head)))
                if (t == tail_id and h == head_id) or (t == head_id and h == tail_id):
                    target_e = edge
                    break
        if target_e:
            selected_edge_data = data.get("selected_edge") or {}
            edge_label = (
                persistent_edge_label(sess, target_e)
                or selected_edge_data.get("marker_label")
                or available_marker_labels(sess, "edge", "e", 1)[0]
            )
            source_a, source_b, source_segments = grouped_visual_edge_endpoints(
                sess,
                target_e,
            )
            frame_a, frame_b = _extend_math_line_to_frame(source_a.p, source_b.p)
            line_label = next_line_label(data)
            sess.add_auxiliary_line_action(
                tool_draw_label_edge_list_extension,
                sess.res_map,
                source_segments,
                edge_label,
                source_a.p,
                source_b.p,
                label=line_label,
            )
            log_action(data, "extend_edge", {
                "tail": int(getattr(source_a, "num", id(source_a))),
                "head": int(getattr(source_b, "num", id(source_b))),
                "selected_segment": {
                    "tail_vertex_id": tail_id,
                    "head_vertex_id": head_id,
                },
                "source_endpoints": [
                    [round(float(source_a.p.x), 6), round(float(source_a.p.y), 6)],
                    [round(float(source_b.p.x), 6), round(float(source_b.p.y), 6)],
                ],
                "extended_endpoints": [
                    [round(float(frame_a.x), 6), round(float(frame_a.y), 6)],
                    [round(float(frame_b.x), 6), round(float(frame_b.y), 6)],
                ],
                "segment_count": len(source_segments),
                "edge": edge_label,
                "line": line_label,
            })
            # Remove the cyan selection overlay after execution so the newly
            # drawn blue extension and its label remain clearly visible.
            data["selected_edge"] = None
            data["selected_edges"] = []
            save_session(data)
            if data.get("phase") == "demo" and data.get("demo_incorrect_target_message"):
                st.toast("Edge extended — now try the edge shared by Regions B and C", icon="⚠️")

    elif act in {"select_region", "remove_selected_region"}:
        face_idx = int(query_params.get("bridge_face", "-1"))
        selected_face = find_face_by_cache_idx(sess.res_map, face_idx)
        selected_face_label = getattr(selected_face, "letter", "?")
        if selected_face is not None and hasattr(sess, "get_union_group"):
            if sess.get_union_group(selected_face):
                selected_face_label = "U"
        selected_indices = [int(value) for value in data.get("selected_region_indices", [])]
        if act == "select_region" and face_idx >= 0 and face_idx not in selected_indices:
            push_selection_undo(data)
            # As with vertices, preserve all reference selections. Merge still
            # requires exactly two regions and remains disabled otherwise.
            selected_indices.append(face_idx)
            data["selected_region_indices"] = selected_indices
            if data.get("phase") == "demo" and data.get("demo_step") == 2:
                sync_demo_selected_types(data)
            log_action(data, "select_region", {
                "face_idx": face_idx,
                "face": selected_face_label,
                "selection": selected_indices,
            })
        elif act == "remove_selected_region":
            if face_idx in selected_indices:
                push_selection_undo(data)
            data["selected_region_indices"] = [value for value in selected_indices if value != face_idx]
            if data.get("phase") == "demo" and data.get("demo_step") == 2:
                sync_demo_selected_types(data)
            log_action(data, "deselect_region", {
                "face_idx": face_idx,
                "face": selected_face_label,
            })
        save_session(data)

    elif act == "commit_region":
        selected_indices = [int(value) for value in data.get("selected_region_indices", [])]
        face_idx = selected_indices[0] if len(selected_indices) == 1 else int(query_params.get("bridge_face", "-1"))
        custom_label = query_params.get("custom_label", "").strip()
        target_face = None
        for face in sess.res_map.faces:
            if hasattr(face, '_cache_idx') and face._cache_idx == face_idx:
                target_face = face
                break
        if target_face:
            label_to_save = custom_label if custom_label != "" else None
            union_group = sess.get_union_group(target_face) if hasattr(sess, "get_union_group") else None
            if union_group and hasattr(sess, "add_union_highlight_action"):
                sess.add_union_highlight_action(
                    union_group, label=label_to_save, color=REGION_HIGHLIGHT
                )
                log_action(data, "commit_union_highlight", {
                    "face": "U", "face_idx": face_idx, "custom_label": custom_label,
                })
            else:
                sess.add_region_action(target_face, label=label_to_save, color=REGION_HIGHLIGHT)
                log_action(data, "commit_region", {
                    "face": getattr(target_face, "letter", "?"),
                    "face_idx": face_idx,
                    "custom_label": custom_label,
                })
            data["selected_region_indices"] = []
            save_session(data)

    elif act == "add_to_buffer":
        face_idx = int(query_params.get("bridge_face", "-1"))
        target_face = None
        for face in sess.res_map.faces:
            if hasattr(face, '_cache_idx') and face._cache_idx == face_idx:
                target_face = face
                break
        if target_face:
            buffer_faces = data.get("union_buffer", [])
            if len(buffer_faces) == 1:
                first_face = buffer_faces[0]
                shared_edges = get_shared_edges(first_face, target_face)
                if not shared_edges:
                    st.error(f"Cannot merge: Region {target_face.letter} is not a neighbor of {first_face.letter}.")
                else:
                    buffer_faces.append(target_face)
                    data["union_buffer"] = buffer_faces
                    log_action(data, "add_to_buffer", f"face={getattr(target_face,'letter','?')} face_idx={face_idx} buffer_size={len(buffer_faces)}")  # NEW
                    save_session(data)
            else:
                if target_face not in buffer_faces:
                    buffer_faces.append(target_face)
                    data["union_buffer"] = buffer_faces
                    log_action(data, "add_to_buffer", f"face={getattr(target_face,'letter','?')} face_idx={face_idx} buffer_size={len(buffer_faces)}")  # NEW
                    save_session(data)

    elif act == "remove_from_buffer":
        face_idx = int(query_params.get("bridge_face", "-1"))
        buffer_faces = data.get("union_buffer", [])
        removed = [f for f in buffer_faces if getattr(f, '_cache_idx', -1) == face_idx]
        data["union_buffer"] = [f for f in buffer_faces if getattr(f, '_cache_idx', -1) != face_idx]
        removed_letter = getattr(removed[0], 'letter', '?') if removed else '?'
        log_action(data, "remove_from_buffer", f"face={removed_letter} face_idx={face_idx}")  # NEW
        save_session(data)

    elif act == "clear_buffer":
        cleared = [getattr(f, 'letter', '?') for f in data.get("union_buffer", [])]
        data["union_buffer"] = []
        log_action(data, "clear_buffer", f"cleared={cleared}")  # NEW
        save_session(data)

    elif act == "clear_union":
        clear_detail = clear_existing_union_state(data)
        log_action(data, "clear_union", clear_detail)
        save_session(data)

    elif act == "execute_union":
        selected_indices = [int(value) for value in data.get("selected_region_indices", [])]
        buffer_faces = [
            face for selected_idx in selected_indices
            for face in sess.res_map.faces
            if getattr(face, "_cache_idx", -1) == selected_idx
        ]
        if len(buffer_faces) == 2:
            if not get_shared_edges(buffer_faces[0], buffer_faces[1]):
                st.error("The selected regions must share an edge.")
            else:
                faces_letters = [getattr(f, 'letter', '?') for f in buffer_faces]
                sess.add_union_action(buffer_faces[0], buffer_faces[1], maxX=1.0, maxY=1.0)
                data["selected_region_indices"] = []
                data["last_run_message"] = ""
                log_action(data, "execute_union", {"faces": faces_letters})
                save_session(data)

    elif act == "commit_union_highlight":
        face_idx = int(query_params.get("bridge_face", "-1"))
        custom_label = query_params.get("custom_label", "").strip()
        target_face = None
        for face in sess.res_map.faces:
            if hasattr(face, '_cache_idx') and face._cache_idx == face_idx:
                target_face = face
                break
        if target_face and hasattr(sess, 'get_union_group'):
            union_group = sess.get_union_group(target_face)
            if union_group and hasattr(sess, 'add_union_highlight_action'):
                u_label = custom_label if custom_label != "" else None
                sess.add_union_highlight_action(union_group, label=u_label, color=REGION_HIGHLIGHT)
                log_action(data, "commit_union_highlight", {
                    "face": "U",
                    "face_idx": face_idx,
                    "custom_label": custom_label,
                })
                data["selected_region_indices"] = []
                save_session(data)

    elif act == "measure_region":
        selected_indices = [int(value) for value in data.get("selected_region_indices", [])]
        face_idx = selected_indices[0] if len(selected_indices) == 1 else query_params.get("bridge_face", "-1")
        target_face = find_face_by_cache_idx(sess.res_map, face_idx)
        if target_face:
            result = measure_region(sess, target_face)
            set_last_measurement(data, result)
            log_action(data, "measure_region", result)
            data["selected_region_indices"] = []
            save_session(data)

    elif act == "measure_angle":
        stored_angle = data.get("selected_angle") or (
            data.get("selected_angles", [])[-1] if data.get("selected_angles") else {}
        )
        angle_vertex_id = query_params.get("bridge_tgt", stored_angle.get("vertex_id", tgt_id))
        angle_face_idx = query_params.get("bridge_face", stored_angle.get("face_idx", "-1"))
        target_v = find_vertex_by_id(sess.res_map, angle_vertex_id)
        target_face = find_face_by_cache_idx(sess.res_map, angle_face_idx)
        if target_face and target_v:
            degrees, region_label = measured_angle_degrees(sess, target_face, target_v)
            if degrees is not None:
                result = {
                    "kind": "angle",
                    "label": f"Angle in {region_label}",
                    "degrees": round(degrees, 1),
                    "vertex_id": str(angle_vertex_id),
                }
                set_last_measurement(data, result)
                log_action(data, "measure_angle", result)
                data["selected_angle"] = None
                data["selected_angles"] = []
                save_session(data)

    elif act == "measure_edge":
        target_e = find_edge_by_vertex_ids(
            sess.res_map,
            query_params.get("bridge_tail", "-1"),
            query_params.get("bridge_head", "-1"),
        )
        if target_e:
            result = measure_edge(sess, target_e)
            set_last_measurement(data, result)
            log_action(data, "measure_edge", result)
            data["selected_edge"] = None
            data["selected_edges"] = []
            save_session(data)

    elif act == "measure_distance":
        selected_ids = [str(v) for v in data.get("selected_vertex_ids", [])]
        selected_vertices = [
            vertex for selected_id in selected_ids
            for vertex in sess.res_map.vertices
            if str(getattr(vertex, "num", id(vertex))) == selected_id
        ]
        if len(selected_vertices) == 2 and selected_vertices[0].p != selected_vertices[1].p:
            start_v, target_v = selected_vertices
            length = distance_between_points(start_v.p, target_v.p)
            result = {
                "kind": "distance",
                "label": "Distance between vertices",
                "length": round(length, 4),
                "from_vertex_id": selected_ids[0],
                "to_vertex_id": selected_ids[1],
                "from_label": data.get("vertex_selection_labels", {}).get(selected_ids[0])
                or vertex_display_name(sess, start_v),
                "to_label": data.get("vertex_selection_labels", {}).get(selected_ids[1])
                or vertex_display_name(sess, target_v),
            }
            set_last_measurement(data, result)
            log_action(data, "measure_distance", result)
            data["selected_vertex_ids"] = []
            sync_vertex_selection_labels(data)
            save_session(data)

    elif act == "cancel_connection":
        log_action(data, "clear_vertex_selection", {"selection": data.get("selected_vertex_ids", [])})
        data["v_start"] = None
        data["v_start_id"] = ""
        data["selected_vertex_ids"] = []
        sync_vertex_selection_labels(data)
        data["last_active_id"] = "none"
        save_session(data)

    # Clear the consumed component event only after its state changes have been
    # persisted.  This is one atomic history update, so it cannot create the old
    # pushState loop and cannot interrupt the action before it is saved.
    keep_session_query_params()

# --- REFRESH STATE ---
sess = data["session"]
action_count = len(sess.actions)
last_active_id = data.get("last_active_id", "none")
has_start_point = data.get("v_start") is not None
start_point_id = data.get("v_start_id", "")

# ── NEW: Handle undo — log it and print the full action log so far ─────────────
# The undo button in the Tools area calls sess.undo_action() directly via st.rerun().
# We detect it by comparing the persisted log's last action_count to current count.
# (Undo is handled in the Tools block below; logging happens there.)
# ──────────────────────────────────────────────────────────────────────────────

# --- FACE DATA ---
faces_data = []
for face in sess.res_map.faces:
    if not face.bounded:
        continue
    if hasattr(face, '_cache_idx') and face._cache_idx in sess.face_label_cache:
        lp, d = sess.face_label_cache[face._cache_idx]
        cx = lp.x * MATH_SCALE + 100
        cy = 900.0 - (lp.y * MATH_SCALE)
        pcx = cx / (sess.img_size[0] / DISPLAY_SIDE)
        pcy = cy / (sess.img_size[1] / DISPLAY_SIDE)
    else:
        continue

    face_display = face.letter
    for action_func, action_args, action_kwargs in sess.actions:
        if "draw_union" in action_func.__name__.lower() and len(action_args) >= 3:
            fa, fb = action_args[1], action_args[2]
            if face == fa or face == fb:
                face_display = "U"
                break

    face_vertices = []
    for edge in face.edges:
        v = edge.tail
        v_num = int(getattr(v, "num", id(v)))
        render_x = v.p.x * MATH_SCALE + 100
        render_y = 900.0 - (v.p.y * MATH_SCALE)
        pvx = render_x / (sess.img_size[0] / DISPLAY_SIDE)
        pvy = render_y / (sess.img_size[1] / DISPLAY_SIDE)
        face_vertices.append({"id": v_num, "x": pvx, "y": pvy})

    current_hidden = sess.get_active_hidden_edges()
    face_is_obsolete = bool(sess.is_marker_obsolete(tool_highlight_region, [face], current_hidden))

    union_partner_idx = None
    for action_func, action_args, action_kwargs in sess.actions:
        if "draw_union" in action_func.__name__.lower() and len(action_args) >= 3:
            fa, fb = action_args[1], action_args[2]
            if face == fa and hasattr(fb, '_cache_idx'):
                union_partner_idx = fb._cache_idx
                break
            elif face == fb and hasattr(fa, '_cache_idx'):
                union_partner_idx = fa._cache_idx
                break

    # Compute valid corner ids for angle hover filtering
    valid_corner_ids = []
    for edge in face.edges:
        v = edge.tail
        v_num = int(getattr(v, "num", id(v)))
        is_angle_obsolete = sess.is_marker_obsolete(
            tool_label_angle, [sess.res_map, (face, v)], current_hidden
        )
        if not is_angle_obsolete:
            valid_corner_ids.append(v_num)

    faces_data.append({
        "cache_idx": face._cache_idx,
        "letter": face.letter,
        "display": face_display,
        "cx": pcx,
        "cy": pcy,
        "vertices": face_vertices,
        "is_obsolete": face_is_obsolete,
        "union_partner_idx": union_partner_idx,
        "valid_corner_ids": valid_corner_ids,
    })

# --- EDGE DATA ---
def get_face_display(face, valid):
    if not valid:
        return "Frame"
    for af, aa, ak in sess.actions:
        if "draw_union" in af.__name__.lower() and len(aa) >= 3:
            if face == aa[1] or face == aa[2]:
                return "U"
    return face.letter

edges_data = []
hidden_edge_ids = sess.get_active_hidden_edges()
seen_edge_pairs = set()

for edge_idx, edge in enumerate(sess.res_map.edges):
    e_id = id(edge)
    e_rev_id = id(edge.reverse) if hasattr(edge, 'reverse') else None
    pair = tuple(sorted([e_id, e_rev_id or e_id]))
    if pair in seen_edge_pairs:
        continue
    seen_edge_pairs.add(pair)

    is_hidden = e_id in hidden_edge_ids or (e_rev_id and e_rev_id in hidden_edge_ids)
    f_main = edge.leftFace
    f_oppo = edge.reverse.leftFace if hasattr(edge, 'reverse') else None
    is_main_valid = bool(f_main and f_main.bounded)
    is_oppo_valid = bool(f_oppo and f_oppo.bounded)
    main_name = get_face_display(f_main, is_main_valid)
    oppo_name = get_face_display(f_oppo, is_oppo_valid)

    px1 = (edge.tail.p.x * MATH_SCALE + 100) / (sess.img_size[0] / DISPLAY_SIDE)
    py1 = (900.0 - edge.tail.p.y * MATH_SCALE) / (sess.img_size[1] / DISPLAY_SIDE)
    px2 = (edge.head.p.x * MATH_SCALE + 100) / (sess.img_size[0] / DISPLAY_SIDE)
    py2 = (900.0 - edge.head.p.y * MATH_SCALE) / (sess.img_size[1] / DISPLAY_SIDE)

    edge_is_obsolete = bool(is_hidden)

    # Build full segment list for hover highlight (same logic as commit_edge)
    target_root = getattr(edge, "trueEdge", edge)
    target_rev_root = getattr(edge.reverse, "trueEdge", edge.reverse) if hasattr(edge, 'reverse') else None

    # Find which faces to search (main + union partner if any)
    hover_faces = []
    for face in [f_main, f_oppo]:
        if not face or not face.bounded:
            continue
        if face not in hover_faces:
            hover_faces.append(face)
        for action_func, action_args, action_kwargs in sess.actions:
            if "draw_union" in action_func.__name__.lower() and len(action_args) >= 3:
                fa, fb = action_args[1], action_args[2]
                if face == fa and fb not in hover_faces:
                    hover_faces.append(fb)
                elif face == fb and fa not in hover_faces:
                    hover_faces.append(fa)

    all_segments = []
    seen_seg_pairs = set()
    for face in hover_faces:
        for e in face.edges:
            s_id = id(e)
            s_rev_id = id(e.reverse) if hasattr(e, 'reverse') else None
            seg_pair = tuple(sorted([s_id, s_rev_id or s_id]))
            if seg_pair in seen_seg_pairs:
                continue
            if getattr(e, "trueEdge", e) == target_root or \
               (target_rev_root and getattr(e, "trueEdge", e) == target_rev_root):
                seen_seg_pairs.add(seg_pair)
                sx1 = (e.tail.p.x * MATH_SCALE + 100) / (sess.img_size[0] / DISPLAY_SIDE)
                sy1 = (900.0 - e.tail.p.y * MATH_SCALE) / (sess.img_size[1] / DISPLAY_SIDE)
                sx2 = (e.head.p.x * MATH_SCALE + 100) / (sess.img_size[0] / DISPLAY_SIDE)
                sy2 = (900.0 - e.head.p.y * MATH_SCALE) / (sess.img_size[1] / DISPLAY_SIDE)
                all_segments.append({"x1": sx1, "y1": sy1, "x2": sx2, "y2": sy2})

    edges_data.append({
        "edge_idx": edge_idx,
        "tail_id": int(getattr(edge.tail, "num", id(edge.tail))),
        "head_id": int(getattr(edge.head, "num", id(edge.head))),
        "tail_x": float(edge.tail.p.x), "tail_y": float(edge.tail.p.y),
        "head_x": float(edge.head.p.x), "head_y": float(edge.head.p.y),
        "x1": px1, "y1": py1, "x2": px2, "y2": py2,
        "segments": all_segments,  # NEW
        "is_hidden": bool(is_hidden),
        "is_obsolete": edge_is_obsolete,
        "is_frame": not (is_main_valid and is_oppo_valid),
        "main_name": main_name,
        "oppo_name": oppo_name,
        "main_valid": is_main_valid,
        "oppo_valid": is_oppo_valid,
    })
# --- VERTEX DATA ---
vertices_data = []
hidden_edge_ids_for_v = sess.get_active_hidden_edges()
for v in sess.res_map.vertices:
    render_x = v.p.x * MATH_SCALE + 100
    render_y = 900.0 - (v.p.y * MATH_SCALE)
    px = render_x / (sess.img_size[0] / DISPLAY_SIDE)
    py = render_y / (sess.img_size[1] / DISPLAY_SIDE)
    v_is_obsolete = bool(sess.is_marker_obsolete(tool_label_vertex, [v], hidden_edge_ids_for_v))

    # Collect neighboring region names for display
    neighbor_regions = []
    seen_face_ids = set()
    for e in v.outarcs:
        for face in [e.leftFace, e.reverse.leftFace if hasattr(e, 'reverse') else None]:
            if not face or not face.bounded:
                continue
            if id(face) in seen_face_ids:
                continue
            seen_face_ids.add(id(face))
            # Use union display name if applicable
            display = face.letter
            for af, aa, ak in sess.actions:
                if "draw_union" in af.__name__.lower() and len(aa) >= 3:
                    if face == aa[1] or face == aa[2]:
                        display = "U"
                        break
            if display not in neighbor_regions:
                neighbor_regions.append(display)

    vertices_data.append({
        "id": int(getattr(v, "num", id(v))),
        "x": px, "y": py,
        "label": getattr(v, "num", ""),
        "is_obsolete": v_is_obsolete,
        "neighbor_regions": neighbor_regions,
    })

# --- DEMO OR SURVEY QUESTION ---
current_question = data.get("current_question", get_current_question(data))
current_trial_index = data.get("current_trial_index", 0)
show_drawing_pad = not (
    data.get("phase") == "demo"
    and data.get("demo_step", 0) in {0, DEMO_CLOCKWISE_STEP, DEMO_FRAME_STEP}
)
tool_mode = data.get("tool_mode", "Vertex")
if (
    data.get("phase") == "demo"
    and data.get("demo_step") == 7
    and data.get("demo_pending_completion") != 7
):
    data["measure_kind"] = "distance"
measure_kind = data.get(
    "measure_kind",
    {"Vertex": "distance", "Angle": "angle", "Region": "area"}.get(tool_mode, "distance"),
)
if "definitions_open" not in st.session_state:
    st.session_state["definitions_open"] = bool(data.get("definitions_open"))
if "tools_guide_open" not in st.session_state:
    st.session_state["tools_guide_open"] = bool(data.get("tools_guide_open"))

if data.get("phase") == "demo":
    demo_step = data.get("demo_step", 0)
    if demo_step > 0:
        practice_stage = (
            1
            if demo_step in {2, DEMO_CLOCKWISE_STEP, DEMO_FRAME_STEP}
            else 2
        )
        st.progress(practice_stage / 2)
    if demo_step == 0:
        st.subheader("Tool Practice")
        intro_col, _ = st.columns([3, 2], gap="small")
        with intro_col:
            st.write("Try a short guided practice before the survey.")
            st.info("Practice helps you learn the tools and does not count toward your survey performance.")
            st.write("Practice using the tools before you begin.")
            if st.button("Begin Practice", type="primary", use_container_width=True):
                data["demo_step"] = 2
                data["tool_mode"] = DEMO_STEPS[2]["tool_mode"]
                start_tutorial_step(data, "selection")
                log_action(data, "begin_demo")
                save_session(data)
                st.rerun()
    elif demo_step in DEMO_STEPS:
        step = DEMO_STEPS[demo_step]
        selection_review_complete = (
            demo_step == 2
            and set(sync_demo_selected_types(data)) == set(PRACTICE_REQUIRED_SELECTIONS)
        )
        st.caption("Practice 1 of 2" if demo_step == 2 else "Practice 2 of 2")
        if demo_step == 2:
            practice_heading = (
                "Review the four kinds of objects you selected."
                if selection_review_complete
                else step["title"]
            )
            st.markdown(
                f'<div style="font-size:18px; font-weight:600; line-height:1.35; '
                f'min-height:2.7em; margin:0.1rem 0 0.9rem 0;">'
                f'{html.escape(practice_heading)}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.subheader(step["title"])
        if demo_step == 2:
            # Match compositional's 3:5:3 page rhythm: concise feedback on
            # the left, the selected diagram immediately to its right, and
            # Help in the existing right-hand column below.
            practice_copy_col, _, _ = st.columns([3, 5, 3], gap="small")
        else:
            practice_copy_col, _ = st.columns([3, 2], gap="small")
        with practice_copy_col:
            if step["definition"]:
                st.write(step["definition"])
            if step.get("context") and not step.get("context_after_success"):
                st.info(step["context"])
            if demo_step == 2:
                selected_types = set(sync_demo_selected_types(data))
                selection_complete = selected_types == set(PRACTICE_REQUIRED_SELECTIONS)
                # Completed-selection feedback is rendered inside the drawing
                # component so it sits directly beside the selected diagram.
            else:
                completed_step = data.get("demo_pending_completion") == demo_step
                if completed_step:
                    success_message = step["success"]
                    line_action_for_step = {
                        4: "confirm_connection",
                        5: "commit_ray",
                        6: "extend_edge",
                    }.get(demo_step)
                    if line_action_for_step:
                        line_label = "The line"
                        for entry in reversed(data.get("action_log", [])):
                            if entry.get("action") == line_action_for_step:
                                line_label = entry.get("detail", {}).get("line") or line_label
                                break
                        success_message = success_message.format(line_label=line_label)
                    st.success(success_message)
                    if step.get("context_after_success") and step.get("context"):
                        st.info(step["context"])
                    if st.button("Continue", type="primary", key=f"continue_demo_{demo_step}"):
                        mark_tutorial_step_completed(data)
                        clear_canvas_state(data)
                        data["demo_pending_completion"] = None
                        data["demo_incorrect_target_message"] = ""
                        data["demo_step"] = DEMO_REVIEW_STEP if demo_step == DEMO_TOTAL_STEPS else demo_step + 1
                        next_step = DEMO_STEPS.get(data["demo_step"])
                        if next_step:
                            data["tool_mode"] = next_step["tool_mode"]
                            prefill_demo_vertex_inputs(data, data["demo_step"])
                            start_tutorial_step(data)
                        else:
                            completed_at = _ts()
                            summary = data.setdefault("tutorial_summary", {})
                            summary["guided_completed_at"] = completed_at
                            summary["free_exploration_started_at"] = completed_at
                        save_session(data)
                        st.rerun()
                else:
                    st.info(step["instruction"])
                    if data.get("demo_incorrect_target_message"):
                        st.warning(data["demo_incorrect_target_message"])
    elif demo_step == DEMO_CLOCKWISE_STEP:
        st.caption("Practice 1 of 2")
        st.markdown(
            '<div style="font-size:18px; font-weight:600; line-height:1.35; '
            'min-height:2.7em; margin:0.1rem 0 0.9rem 0;">'
            'Determine whether the arrows move clockwise or counterclockwise.</div>',
            unsafe_allow_html=True,
        )
        clockwise_copy_col, clockwise_diagram_col, clockwise_help_col = st.columns(
            [3, 5, 3], gap="small"
        )
        with clockwise_copy_col:
            st.markdown(
                "**Clockwise** follows the direction of a clock's hands: "
                "top → right → bottom → left.  \n"
                "**Counterclockwise** goes in the opposite direction: "
                "top → left → bottom → right."
            )
            st.markdown("**Which direction do the numbered vertices and arrows show?**")
            direction_answer = st.radio(
                "Choose one:",
                ["Clockwise", "Counterclockwise"],
                index=None,
                horizontal=True,
                key="clockwise_demo_answer",
                disabled=data.get("demo_direction_answered", False),
            )
            if not data.get("demo_direction_answered", False):
                if st.button(
                    "Check Answer",
                    type="primary",
                    disabled=direction_answer is None,
                    key="check_clockwise_demo",
                ):
                    is_correct = direction_answer == "Clockwise"
                    data["demo_direction_answered"] = True
                    data["demo_direction_correct"] = is_correct
                    log_action(data, "complete_clockwise_demo" if is_correct else "incorrect_clockwise_demo", {"answer": direction_answer})
                    if not is_correct:
                        mark_tutorial_tool_error(data, "clockwise")
                    save_session(data)
                    st.rerun()
            if data.get("demo_direction_answered"):
                if data.get("demo_direction_correct"):
                    st.success("Correct — the arrows move clockwise.")
                    if st.button(
                        "Continue",
                        type="primary",
                        use_container_width=True,
                        key="continue_clockwise_demo",
                    ):
                        mark_tutorial_step_completed(data, "clockwise")
                        data["demo_step"] = DEMO_FRAME_STEP
                        start_tutorial_step(data, "frame")
                        save_session(data)
                        st.rerun()
                else:
                    st.error("Not quite — the arrows move clockwise: from the top, toward the right, then downward and around.")
                    if st.button("Try again", type="primary", key="retry_clockwise_demo"):
                        data["demo_direction_answered"] = False
                        data["demo_direction_correct"] = None
                        save_session(data)
                        st.rerun()
        with clockwise_diagram_col:
            clockwise_pad_left, clockwise_image_col, clockwise_pad_right = st.columns(
                [1, 5, 1], gap="small"
            )
            with clockwise_image_col:
                st.image(render_demo_direction_diagram(sess), width=380)
        with clockwise_help_col:
            st.markdown(
                '<div style="font-size:1.25rem; font-weight:600; '
                'line-height:1.2; margin:0 0 0.25rem;">Help</div>',
                unsafe_allow_html=True,
            )
            clockwise_definitions_open = st.session_state.get("definitions_open", False)
            if st.button(
                "▾ Definitions" if clockwise_definitions_open else "▸ Definitions",
                key="toggle_clockwise_definitions",
                use_container_width=True,
            ):
                clockwise_definitions_open = not clockwise_definitions_open
                st.session_state["definitions_open"] = clockwise_definitions_open
                data["definitions_open"] = clockwise_definitions_open
                save_session(data)
                st.rerun()
            if clockwise_definitions_open:
                st.markdown(PRACTICE_ENTITY_DEFINITIONS + PRACTICE_DIRECTION_DEFINITIONS)

            st.markdown(
                '<div style="font-size:1.25rem; font-weight:600; '
                'margin:0.8rem 0 0.25rem;">Quick actions</div>',
                unsafe_allow_html=True,
            )
            clockwise_undo_col, clockwise_clear_col = st.columns(2, gap="small")
            with clockwise_undo_col:
                st.button(
                    "↩ Undo",
                    key="clockwise_review_undo",
                    use_container_width=True,
                    disabled=True,
                )
            with clockwise_clear_col:
                st.button(
                    "Clear all",
                    key="clockwise_review_clear",
                    use_container_width=True,
                    disabled=True,
                )
            st.markdown(
                '<div style="font-size:1.25rem; font-weight:600; '
                'margin:0.8rem 0 0.25rem;">Sketch pad</div>',
                unsafe_allow_html=True,
            )
            st.text_area(
                "Sketch pad",
                key="clockwise_review_notes",
                placeholder=(
                    "Use this space for notes or rough work. Your final answer "
                    "must be entered in the answer box."
                ),
                height=130,
                label_visibility="collapsed",
            )
            st.markdown(
                '<div style="font-size:1.25rem; font-weight:600; '
                'margin:0.8rem 0 0;">Output</div>',
                unsafe_allow_html=True,
            )
            st.caption("(results will appear here)")
    elif demo_step == DEMO_FRAME_STEP:
        st.caption("Practice 1 of 2")
        st.markdown(
            '<div style="font-size:18px; font-weight:600; line-height:1.35; '
            'min-height:2.7em; margin:0.1rem 0 0.9rem 0;">'
            'Review the frame and outside of the frame.</div>',
            unsafe_allow_html=True,
        )
        frame_copy_col, frame_diagram_col, frame_help_col = st.columns(
            [3, 5, 3], gap="small"
        )
        with frame_copy_col:
            st.markdown(
                "The **frame** is the diagram's outer boundary.  \n"
                "The **outside of the frame** is the area beyond that boundary."
            )
            if st.button(
                "Continue",
                type="primary",
                use_container_width=True,
                key="continue_frame_demo",
            ):
                mark_tutorial_step_completed(data, "frame")
                first_tool_step = 3
                data["demo_step"] = first_tool_step
                data["tool_mode"] = DEMO_STEPS[first_tool_step]["tool_mode"]
                start_tutorial_step(data)
                save_session(data)
                st.rerun()
        with frame_diagram_col:
            frame_pad_left, frame_image_col, frame_pad_right = st.columns(
                [1, 5, 1], gap="small"
            )
            with frame_image_col:
                st.image(render_demo_frame_diagram(sess), width=380)
        with frame_help_col:
            st.markdown(
                '<div style="font-size:1.25rem; font-weight:600; '
                'line-height:1.2; margin:0 0 0.25rem;">Help</div>',
                unsafe_allow_html=True,
            )
            frame_definitions_open = st.session_state.get("definitions_open", False)
            if st.button(
                "▾ Definitions" if frame_definitions_open else "▸ Definitions",
                key="toggle_frame_definitions",
                use_container_width=True,
            ):
                frame_definitions_open = not frame_definitions_open
                st.session_state["definitions_open"] = frame_definitions_open
                data["definitions_open"] = frame_definitions_open
                save_session(data)
                st.rerun()
            if frame_definitions_open:
                st.markdown(PRACTICE_ENTITY_DEFINITIONS + PRACTICE_FRAME_DEFINITIONS)

            st.markdown(
                '<div style="font-size:1.25rem; font-weight:600; '
                'margin:0.8rem 0 0.25rem;">Quick actions</div>',
                unsafe_allow_html=True,
            )
            frame_undo_col, frame_clear_col = st.columns(2, gap="small")
            with frame_undo_col:
                st.button(
                    "↩ Undo",
                    key="frame_review_undo",
                    use_container_width=True,
                    disabled=True,
                )
            with frame_clear_col:
                st.button(
                    "Clear all",
                    key="frame_review_clear",
                    use_container_width=True,
                    disabled=True,
                )
            st.markdown(
                '<div style="font-size:1.25rem; font-weight:600; '
                'margin:0.8rem 0 0.25rem;">Sketch pad</div>',
                unsafe_allow_html=True,
            )
            st.text_area(
                "Sketch pad",
                key="frame_review_notes",
                placeholder=(
                    "Use this space for notes or rough work. Your final answer "
                    "must be entered in the answer box."
                ),
                height=130,
                label_visibility="collapsed",
            )
            st.markdown(
                '<div style="font-size:1.25rem; font-weight:600; '
                'margin:0.8rem 0 0;">Output</div>',
                unsafe_allow_html=True,
            )
            st.caption("(results will appear here)")
    else:
        st.caption("Practice 2 of 2")
        st.subheader("Review Before the Survey")
        review_notice_col, _ = st.columns([3, 2], gap="small")
        with review_notice_col:
            st.markdown(
                """
**Definitions** and **Tool Guide** are available on the right and will remain available throughout the survey. Refer to them whenever you need help with a diagram object or tool.

This survey is **not a test of your ability to operate the tools**. You can answer the questions without them, but the tools can make many questions **substantially easier**, so we recommend becoming comfortable with them.

Feel free to explore other tools before starting the survey. **Useful examples** include highlighting an object, drawing a ray, extending an edge, measuring a distance, angle, or area, or merging neighboring regions.

Read the **instructions under the diagram** to see what else each tool can do.
"""
            )
        if st.button("Start Survey", type="primary"):
            data["demo_feedback_message"] = ""
            begin_survey(data)
            save_session(data)
            st.rerun()
else:
    question_col, _question_spacer = st.columns([3, 1], gap="small")
    with question_col:
        st.caption(f"Question {current_trial_index + 1} of {len(QUESTION_BANK)}")
        demo_feedback_message = data.get("demo_feedback_message", "")
        if demo_feedback_message:
            st.info(demo_feedback_message)
            data["demo_feedback_message"] = ""
            save_session(data)
        raw_question_text = str(current_question["question_text"])
        # Keep the main task separate from the shared line-tracing caveats.
        # The dataset stores these with single newlines, which HTML otherwise
        # collapses into one dense paragraph.
        raw_question_text = re.sub(
            r"\s+(?=Do not include a region if the line only coincides with its boundary)",
            "\n\n",
            raw_question_text,
            count=1,
        )
        question_text = html.escape(raw_question_text)
        question_text = '<div style="height:0.55rem;"></div>'.join(
            paragraph.replace("\n", " ").strip()
            for paragraph in re.split(r"\n\s*\n", question_text)
            if paragraph.strip()
        )
        st.markdown(
            f'<div style="font-size:17px; font-weight:600; line-height:1.24; '
            f'margin:0 0 0.6rem 0;">{question_text}</div>',
            unsafe_allow_html=True,
        )

    feedback = data.get("answer_feedback")
    feedback_for_current = feedback and feedback.get("trial_index") == current_trial_index
    answer_col, _ = st.columns([1, 1], gap="small")

    with answer_col:
        if feedback_for_current:
            feedback_col, _feedback_spacer = st.columns([3, 1], gap="small")
            with feedback_col:
                if feedback.get("is_correct") is False:
                    original_response = feedback.get("answer", "")
                    correct_answer = feedback.get("correct_answer_display", feedback.get("correct_answer", ""))
                    st.error(
                        f"**Incorrect.**  \n"
                        f"**Your response:** {original_response}  \n"
                        f"**Correct answer:** {correct_answer}"
                    )
                else:
                    st.success("Correct.")
            continue_label = "Continue"
            continue_col, _continue_spacer = st.columns([1, 3], gap="small")
            with continue_col:
                if st.button(continue_label, type="primary", use_container_width=True):
                    data["answer_feedback"] = None
                    next_trial_index = current_trial_index + 1
                    if feedback.get("is_last_question") or next_trial_index >= len(QUESTION_BANK):
                        complete_survey(data, "completed")
                    else:
                        start_trial(data, next_trial_index)
                        save_results(data)
                    save_session(data)
                    st.rerun()
        else:
            with st.form("answer_form", clear_on_submit=False):
                answer_widget_key = f"answer_{current_trial_index}_{current_question['question_id']}"
                if normalized_answer_type(current_question) == "two_choice":
                    answer_value = st.radio(
                        "Answer:",
                        get_two_choice_options(current_question),
                        index=None,
                        horizontal=True,
                        key=f"{answer_widget_key}_choice",
                    )
                else:
                    answer_value = st.text_area(
                        "Answer:",
                        value=data.get("current_answer", ""),
                        height=68,
                        placeholder=current_question.get("answer_placeholder", ""),
                        key=f"{answer_widget_key}_area",
                    )
                    answer_hint = answer_hint_for(current_question)
                    if answer_hint:
                        safe_answer_hint = html.escape(answer_hint)
                        st.markdown(
                            '<div style="font-size:0.78rem; line-height:1.2; color:#4b5563; '
                            'background:#f3f4f6; border-left:3px solid #9ca3af; '
                            'padding:0.25rem 0.45rem; margin-top:0.05rem; margin-bottom:0.35rem; '
                            'border-radius:0 0.3rem 0.3rem 0;">'
                            f'{safe_answer_hint}</div>',
                            unsafe_allow_html=True,
                        )
                is_last_question = current_trial_index >= len(QUESTION_BANK) - 1
                button_label = "Confirm Answer"
                submitted_answer = st.form_submit_button(button_label, type="primary")
                if submitted_answer:
                    cleaned_answer = (answer_value or "").strip()
                    if not cleaned_answer:
                        st.error("Please provide an answer before continuing.")
                    else:
                        is_correct = answer_is_correct(current_question, cleaned_answer)
                        data["current_answer"] = cleaned_answer
                        log_action(
                            data,
                            "submit_answer",
                            {
                                "question_id": current_question["question_id"],
                                "answer_type": normalized_answer_type(current_question),
                                "answer": cleaned_answer,
                                "is_correct": is_correct,
                            },
                        )
                        finalize_current_trial(data, cleaned_answer, "answered", is_correct)
                        data["current_notes"] = ""
                        data["answer_feedback"] = {
                            "trial_index": current_trial_index,
                            "question_id": current_question["question_id"],
                            "answer": cleaned_answer,
                            "correct_answer": current_question.get("answer", ""),
                            "correct_answer_display": format_answer_for_feedback(current_question),
                            "is_correct": is_correct,
                            "is_last_question": is_last_question,
                        }
                        save_results(data)
                        save_session(data)
                        st.rerun()

demo_review = (
    data.get("phase") == "demo"
    and data.get("demo_step") == DEMO_REVIEW_STEP
)
main_work_col, main_info_col = st.columns([8, 3], gap="small")

with main_work_col:
    if not DATASET_PATH:
        st.warning("Dataset JSON was not found. Using fallback questions.")

with main_info_col:
    if show_drawing_pad:
        # The Help column is created after the full-width page copy, so its
        # natural top can sit much lower than the content it supports. Keep it
        # near the top, with phase-specific offsets for the different headers.
        guided_help_translate = "-10rem" if data.get("phase") == "survey" else "0"
        if demo_review:
            guided_help_translate = "-20rem"
        if (
            data.get("phase") == "demo"
            and data.get("demo_step") in DEMO_STEPS
            and data.get("demo_step") != 2
        ):
            guided_help_translate = (
                "-8rem"
                if data.get("demo_pending_completion") == data.get("demo_step")
                else "-10rem"
            )
        if guided_help_translate != "0":
            st.markdown(
                '<span id="guided-help-panel-marker"></span>'
                '<style>'
                'div[data-testid="stColumn"]:has(#guided-help-panel-marker) {'
                f'transform:translateY({guided_help_translate});'
                '}'
                '</style>',
                unsafe_allow_html=True,
            )
        st.markdown(
            '<div style="position:relative; top:-0.2rem; font-family:\'Source Sans 3\', \'Source Sans Pro\', sans-serif; '
            'font-size:1.25rem; font-weight:600; line-height:1.2; margin:-0.35rem 0 0.25rem 0;">Help</div>',
            unsafe_allow_html=True,
        )
        incomplete_guided_step = (
            data.get("phase") == "demo"
            and data.get("demo_step") in DEMO_STEPS
            and data.get("demo_step") != 2
            and data.get("demo_pending_completion") != data.get("demo_step")
        )
        if incomplete_guided_step:
            with st.expander("Having trouble with this step?"):
                st.caption(
                    "Click below to see this step completed for you. Then click Continue."
                )
                if st.button(
                    "Show Completed Example",
                    key=f"show_completed_demo_{data.get('demo_step')}",
                    use_container_width=True,
                ):
                    show_completed_demo_step(data)
                    st.rerun()

        definitions_open = st.session_state["definitions_open"]
        if st.button(
            ("▾ Definitions" if definitions_open else "▸ Definitions"),
            key="toggle_definitions",
            use_container_width=True,
        ):
            definitions_open = not definitions_open
            st.session_state["definitions_open"] = definitions_open
            data["definitions_open"] = definitions_open
            save_session(data)
            st.rerun()
        if definitions_open:
            visible_definitions = DEFINITIONS_TEXT
            if data.get("phase") == "demo":
                visible_definitions = PRACTICE_ENTITY_DEFINITIONS
                if data.get("demo_step") == DEMO_CLOCKWISE_STEP:
                    visible_definitions += PRACTICE_DIRECTION_DEFINITIONS
                elif data.get("demo_step") == DEMO_FRAME_STEP:
                    visible_definitions += PRACTICE_FRAME_DEFINITIONS
                elif data.get("demo_step", 0) >= 8:
                    visible_definitions += PRACTICE_UNION_DEFINITION
            st.markdown(visible_definitions)

        show_tool_guide = not (
            data.get("phase") == "demo" and data.get("demo_step") == 2
        )
        if show_tool_guide:
            tools_guide_open = st.session_state["tools_guide_open"]
            if st.button(
                ("▾ Tool Guide" if tools_guide_open else "▸ Tool Guide"),
                key="toggle_tool_guide",
                use_container_width=True,
            ):
                tools_guide_open = not tools_guide_open
                st.session_state["tools_guide_open"] = tools_guide_open
                data["tools_guide_open"] = tools_guide_open
                save_session(data)
                st.rerun()
            if tools_guide_open:
                st.markdown(TOOL_GUIDE_TEXT)

        st.markdown(
            '<div style="font-size:1.25rem; font-weight:600; margin:0.4rem 0 0.25rem 0;">Quick actions</div>',
            unsafe_allow_html=True,
        )
        undo_col, clear_col = st.columns(2, gap="small")
        with undo_col:
            selection_undo_available = bool(data.get("selection_undo_stack"))
            if st.button(
                "↩ Undo",
                use_container_width=True,
                disabled=(action_count == 0 and not selection_undo_available),
            ):
                if sess.actions:
                    last_func, last_args, last_kwargs = sess.actions[-1]
                    current_actions = [
                        entry
                        for entry in data.get("action_log", [])
                        if entry.get("question_id", "")
                        == current_question.get("question_id", "")
                        and (
                            data.get("phase") != "survey"
                            or entry.get("trial_index") == current_trial_index
                        )
                    ]
                    target_event_id = undo_target_event_id(
                        current_actions,
                        action_count,
                    )
                    log_action(data, "undo", {
                        "undone_action": last_func.__name__,
                        "remaining_after": action_count - 1,
                        "target_event_id": target_event_id,
                    })
                    sess.undo_action()
                elif selection_undo_available:
                    restore_selection_snapshot(data, data["selection_undo_stack"].pop())
                    log_action(data, "undo", {"undone_action": "selection", "remaining_after": 0})
                sync_line_label_counter(data)
                next_step = DEMO_STEPS.get(data.get("demo_step", 0))
                if data.get("phase") == "demo" and next_step:
                    data["tool_mode"] = next_step["tool_mode"]
                data["union_buffer"] = []
                data["last_active_id"] = "none"
                data["v_start"] = None
                data["v_start_id"] = ""
                save_session(data)
                print("\n── Action Log Snapshot (after undo) ──────────────────────────────────────")
                for i, entry in enumerate(data.get("action_log", []), 1):
                    print(f"  {i:>3}. [{entry.get('server_timestamp', '')}] {entry['action']:<30} | {entry['detail']}")
                print("──────────────────────────────────────────────────────────────────────────\n")
                st.rerun()
        with clear_col:
            output_action_names = {
                "commit_vertex", "commit_angle", "commit_edge", "commit_region",
                "commit_union_highlight", "confirm_connection", "commit_axis_h",
                "commit_axis_v", "commit_ray", "extend_edge", "execute_union", "measure_distance",
                "measure_angle", "measure_edge", "measure_region", "undo",
            }
            has_visible_output = False
            for entry in data.get("action_log", []):
                if entry.get("question_id", "") != current_question.get("question_id", ""):
                    continue
                if data.get("phase") == "survey" and entry.get("trial_index") != current_trial_index:
                    continue
                if entry.get("action") == "clear_all":
                    has_visible_output = False
                elif entry.get("action") in output_action_names:
                    has_visible_output = True
            has_temporary_selection = any((
                data.get("selected_vertex_ids"), data.get("selected_region_indices"),
                data.get("selected_angles"), data.get("selected_edges"),
                data.get("selected_angle"), data.get("selected_edge"),
            ))
            clear_disabled = not any((
                action_count, has_visible_output, has_temporary_selection,
                data.get("last_measurement"), data.get("current_notes"),
            ))
            clear_help = "Clears annotations, selections, measurements, Output, and the sketch pad. It does not change your answer."
            if st.button("Clear all", use_container_width=True, disabled=clear_disabled, help=clear_help):
                current_actions = [
                    entry
                    for entry in data.get("action_log", [])
                    if entry.get("question_id", "")
                    == current_question.get("question_id", "")
                    and (
                        data.get("phase") != "survey"
                        or entry.get("trial_index") == current_trial_index
                    )
                ]
                cleared_event_ids = active_tool_event_ids(current_actions)
                cleared_count = clear_canvas_state(data)
                notes_key_to_clear = f"notes_{current_trial_index}_{current_question['question_id']}"
                st.session_state.pop(notes_key_to_clear, None)
                log_action(data, "clear_all", {
                    "cleared_actions": cleared_count,
                    "affected_event_ids": cleared_event_ids,
                })
                save_session(data)
                st.rerun()

        if (
            data.get("phase") == "demo"
            and data.get("demo_step") in DEMO_STEPS
            and data.get("demo_step") != 2
        ):
            st.markdown(
                '<div style="background:#eff6ff; color:#1e3a8a; '
                'border:1px solid #bfdbfe; border-radius:0.5rem; '
                'padding:0.55rem 0.7rem; margin:0.65rem 0 0.5rem; font-size:0.9rem;">'
                'If you make a mistake, use <strong>Undo</strong> to reverse your most recent action. '
                'Use <strong>Clear all</strong> to reset the practice workspace.'
                '</div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            '<div style="font-size:1.25rem; font-weight:600; margin:0 0 0.35rem 0;">Sketch pad</div>',
            unsafe_allow_html=True,
        )
        notes_key = f"notes_{current_trial_index}_{current_question['question_id']}"
        if data.get("phase") == "survey" and (data.get("answer_feedback") or {}).get("trial_index") == current_trial_index:
            st.session_state[notes_key] = ""
        updated_notes = st.text_area(
            "Sketch pad",
            value=data.get("current_notes", ""),
            height=110,
            key=notes_key,
            label_visibility="collapsed",
            placeholder="Use this space for notes or rough work. Your final answer must be entered in the answer box.",
        )
        if updated_notes != data.get("current_notes", ""):
            data["current_notes"] = updated_notes
            save_session(data)

# print(f"🎨 Rendering with {len(sess.actions)} actions")  # COMMENTED OUT
bg_image = sess.render()
if data.get("phase") == "demo":
    # The practice regions already form their own closed shape. Hide the
    # renderer's heavy outer frame here to keep the tutorial diagram cleaner;
    # survey diagrams retain the frame because some questions refer to it.
    practice_draw = ImageDraw.Draw(bg_image)
    practice_draw.rectangle(
        [90, 90, bg_image.width - 90, bg_image.height - 90],
        outline=(255, 255, 255, 255),
        width=18,
    )
display_bg = bg_image.resize((DISPLAY_SIDE, DISPLAY_SIDE), Image.Resampling.LANCZOS)
buffered = BytesIO()
display_bg.save(buffered, format="PNG")
img_base64 = base64.b64encode(buffered.getvalue()).decode()

# --- EVALUATE UNION STATUS FOR JAVASCRIPT ---
has_existing_union = any("draw_union" in action_func.__name__.lower() for action_func, _, _ in sess.actions)
buffer_indices = [int(f._cache_idx) for f in data.get("union_buffer", []) if hasattr(f, '_cache_idx')]
buffer_letters = [str(f.letter) for f in data.get("union_buffer", []) if hasattr(f, 'letter')]
# A completed merge consumes its two region inputs.  Older/stale component
# state can otherwise leave both constituent faces selected, which redraws the
# shared edge and shows Region U twice.
pending_region_indices = [int(value) for value in data.get("selected_region_indices", [])]
if has_existing_union and len(pending_region_indices) == 2 and hasattr(sess, "get_union_group"):
    pending_faces = [
        next(
            (face for face in sess.res_map.faces if getattr(face, "_cache_idx", -1) == face_idx),
            None,
        )
        for face_idx in pending_region_indices
    ]
    union_groups = [sess.get_union_group(face) if face is not None else None for face in pending_faces]
    if union_groups[0] and union_groups[1] and union_groups[0] == union_groups[1]:
        data["selected_region_indices"] = []
        pending_region_indices = []
        save_session(data)
selected_vertex_ids = [str(value) for value in data.get("selected_vertex_ids", [])]
selected_angle = data.get("selected_angle") or None
selected_edge = data.get("selected_edge") or None
selected_angles = list(data.get("selected_angles", []))
selected_edges = list(data.get("selected_edges", []))
# Migrate sessions saved before multi-selection was introduced.
if selected_angle and not selected_angles:
    selected_angles = [dict(selected_angle)]
if selected_edge and not selected_edges:
    selected_edges = [dict(selected_edge)]
angle_preview_labels = available_marker_labels(sess, "angle", "a", len(selected_angles) + 1)
edge_preview_labels = available_marker_labels(sess, "edge", "e", len(selected_edges) + 1)
vertex_selection_labels = {
    str(key): str(value)
    for key, value in data.get("vertex_selection_labels", {}).items()
}
selected_region_indices = pending_region_indices
selected_region_letters = {}
selection_hidden_edge_ids = sess.get_active_hidden_edges()
for face in sess.res_map.faces:
    if not face.bounded or not hasattr(face, "_cache_idx"):
        continue
    display_letter = str(face.letter)
    if (
        hasattr(sess, "get_union_group")
        and sess.get_union_group(face)
        and sess.is_marker_obsolete(tool_highlight_region, [face], selection_hidden_edge_ids)
    ):
        display_letter = "U"
    selected_region_letters[int(face._cache_idx)] = display_letter
selection_rows_by_type = {label: [] for label in PRACTICE_REQUIRED_SELECTIONS}
for vertex_id in selected_vertex_ids:
    vertex = next(
        (v for v in sess.res_map.vertices if str(getattr(v, "num", id(v))) == vertex_id),
        None,
    )
    label = vertex_selection_labels.get(vertex_id) or (
        vertex_display_name(sess, vertex) if vertex else f"Vertex {vertex_id}"
    )
    selection_rows_by_type["Vertex"].append(
        f'<div class="selection-row"><span>{html.escape(label)}</span>'
        f'<button class="selection-remove" data-kind="vertex" data-id="{html.escape(vertex_id)}" '
        f'aria-label="Remove {html.escape(label)}">✕</button></div>'
    )
for face_idx in selected_region_indices:
    label = f"Region {selected_region_letters.get(face_idx, '?')}"
    selection_rows_by_type["Region"].append(
        f'<div class="selection-row"><span>{html.escape(label)}</span>'
        f'<button class="selection-remove" data-kind="region" data-id="{face_idx}" '
        f'aria-label="Remove {html.escape(label)}">✕</button></div>'
    )
for selection_index, angle_selection in enumerate(selected_angles):
    marker_label = angle_preview_labels[selection_index]
    face_name = str(angle_selection.get("face", "?")).strip() or "?"
    label = f"angle {marker_label} (in Region {face_name})"
    selection_rows_by_type["Angle"].append(
        f'<div class="selection-row"><span>{html.escape(label)}</span>'
        f'<button class="selection-remove" data-kind="angle" data-id="{selection_index}" '
        f'aria-label="Remove {html.escape(label)}">✕</button></div>'
    )
for selection_index, edge_selection in enumerate(selected_edges):
    marker_label = edge_preview_labels[selection_index]
    edge_description = str(edge_selection.get("label", "")).strip()
    if edge_description.lower().startswith("edge:"):
        legacy_names = [
            part.strip()
            for part in re.split(r"\s*(?:/|\|)\s*", edge_description.split(":", 1)[1])
            if part.strip()
        ]
        if len(legacy_names) >= 2:
            edge_description = f"edge between {legacy_names[0]} and {legacy_names[1]}"
        elif legacy_names:
            edge_description = f"frame edge of {legacy_names[0]}"
    if not edge_description:
        edge_description = "selected edge"
    label = f"edge {marker_label} ({edge_description})"
    selection_rows_by_type["Edge"].append(
        f'<div class="selection-row"><span>{html.escape(label)}</span>'
        f'<button class="selection-remove" data-kind="edge" data-id="{selection_index}" '
        f'aria-label="Remove {html.escape(label)}">✕</button></div>'
    )
selection_rows = [
    row
    for label in PRACTICE_REQUIRED_SELECTIONS
    for row in selection_rows_by_type[label]
]
selection_rows_html = "".join(selection_rows)
selection_section_class = "selection-section" if selection_rows else "selection-section hidden"

demo_active_category = ""
selection_only_demo = data.get("phase") == "demo" and data.get("demo_step") == 2
selection_practice_types = set(
    sync_demo_selected_types(data)
    if selection_only_demo
    else data.get("demo_selected_types", [])
)
selection_review_demo = (
    selection_only_demo
    and selection_practice_types == set(PRACTICE_REQUIRED_SELECTIONS)
)
selection_practice_rows = "".join(
    f'<div style="font-size:0.95rem; line-height:1.55; color:{"#047857" if label in selection_practice_types else "#6b7280"};">'
    f'{"✓" if label in selection_practice_types else "○"} {html.escape(label)}</div>'
    for label in PRACTICE_REQUIRED_SELECTIONS
)
selection_practice_panel = (
    '<div style="border:1px solid #d1d5db; border-radius:0.4rem; '
    'padding:0.55rem 0.7rem; margin:0.35rem 0;">'
    f'{selection_practice_rows}</div>'
    '<div style="color:rgba(49,51,63,0.6); font-family:-apple-system, '
    'BlinkMacSystemFont, \'Segoe UI\', sans-serif; '
    'font-size:0.875rem; font-weight:400; line-height:1.4; '
    'letter-spacing:normal; margin-top:0.35rem;">'
    'Select exactly one object of each type. After selecting one Region, '
    'switch Selection to Angle, then Vertex, then Edge. The checklist will '
    'show your progress. Refer to Definitions on the right if needed.</div>'
    if selection_only_demo and not selection_review_demo
    else ""
)
selection_mode_options = "".join(
    f'<label class="mode-option"><input type="radio" name="toolMode" value="{mode}" '
    f'{"checked" if tool_mode == mode else ""}>{mode}</label>'
    for mode in ["Region", "Angle", "Vertex", "Edge"]
)
selection_practice_banner = (
    '<div class="practice-banner"><strong>The diagram is interactive.</strong> '
    'Select objects by clicking directly on the diagram above.</div>'
    if selection_only_demo and not selection_review_demo
    else ""
)
selection_review_panel = (
    '<div id="selectionReviewPanel" class="selection-review-panel">'
    '<div class="selection-review-success">Great — you identified all four kinds of objects.</div>'
    '<div class="selection-review-caption">The diagram shows the region, angle, vertex, and edge you selected.</div>'
    '<button id="continueSelectionReview" class="selection-review-continue">Continue</button>'
    '</div>'
    if selection_review_demo
    else ""
)
demo_line_style = {4: "segment", 5: "right"}.get(
    data.get("demo_step") if data.get("phase") == "demo" else None,
    "",
)
component_display_side = 390 if selection_only_demo else DISPLAY_SIDE
component_control_width = 315 if selection_only_demo else 276
component_min_height = component_display_side + (
    20 if selection_review_demo else (130 if selection_only_demo else 20)
)
component_body_display = "grid" if selection_only_demo else "flex"
component_body_columns = (
    "grid-template-columns:minmax(315px,3fr) minmax(390px,5fr);"
    if selection_only_demo
    else ""
)
component_diagram_column_width = "100%" if selection_only_demo else f"{component_display_side}px"
component_control_column_width = "100%" if selection_only_demo else f"{component_control_width}px"
component_body_gap = 16 if selection_only_demo else 56
component_pad_shadow = "none"
survey_ui_reset_token = data.get("survey_start_time", "") if data.get("phase") == "survey" else ""
review_ui_reset_token = (
    data.get("demo_start_time", "")
    if data.get("phase") == "demo" and data.get("demo_step") == DEMO_REVIEW_STEP
    else ""
)
if data.get("phase") == "demo":
    demo_active_category = {
        3: "highlight",
        4: "draw",
        5: "draw",
        6: "draw",
        7: "measure",
        8: "merge",
    }.get(data.get("demo_step"), "")

obsolete_faces_union_info = {}
if hasattr(sess, 'get_union_group'):
    for face in sess.res_map.faces:
        if not face.bounded: continue
        hidden_edge_ids = sess.get_active_hidden_edges()
        if sess.is_marker_obsolete(tool_highlight_region, [face], hidden_edge_ids):
            ug = sess.get_union_group(face)
            if ug:
                func, args, kwargs = ug
                faces_in_ug = args[1:] if "draw_union" in func.__name__.lower() else args
                names = ", ".join([f.letter for f in faces_in_ug if hasattr(f, "letter")])
                obsolete_faces_union_info[face._cache_idx] = names

html_code = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            margin: 0; padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: transparent; display: {component_body_display}; gap: {component_body_gap}px;
            width:100%; box-sizing:border-box; {component_body_columns}
        }}
        .diagram-column {{ width:{component_diagram_column_width}; display:flex; flex-direction:column; align-items:{"center" if selection_only_demo else "stretch"}; gap:10px; }}
        .pad-container {{ position: relative; width: {component_display_side}px; height: {component_display_side}px; border-radius: 8px; overflow: hidden; box-shadow: {component_pad_shadow}; }}
        canvas {{ position: absolute; top: 0; left: 0; width:{component_display_side}px; height:{component_display_side}px; cursor: crosshair; }}
        .right-panel {{ width: {component_control_column_width}; min-height: {component_display_side}px; height:auto; background: transparent; border: none; padding: 0; box-sizing: border-box; display: flex; flex-direction: column; box-shadow: none; overflow:visible; }}
        {'.right-panel > :not(#selectionReviewPanel) { display:none !important; }' if selection_review_demo else ''}
        {'.pad-container { pointer-events:none; } canvas { cursor:default; }' if selection_review_demo else ''}
        .practice-banner {{ width:100%; box-sizing:border-box; background:#eff6ff; color:#1e3a8a; border:1px solid #bfdbfe; border-radius:0.5rem; padding:0.75rem 1rem; margin-top:0.65rem; font-size:0.9rem; line-height:1.4; text-align:left; }}
        .selection-review-panel {{ width:100%; box-sizing:border-box; padding-top:0.35rem; }}
        .selection-review-success {{ box-sizing:border-box; background:#e9f7ee; color:#177534; border-radius:0.5rem; padding:1rem; font-size:0.95rem; line-height:1.4; margin-bottom:0.65rem; }}
        .selection-review-caption {{ color:rgba(49,51,63,0.6); font-size:0.875rem; line-height:1.4; margin-bottom:0.65rem; }}
        .selection-review-continue {{ width:100%; box-sizing:border-box; border:1px solid #ff4b4b; border-radius:0.4rem; background:#ff4b4b; color:#fff; padding:0.65rem 1rem; font-size:1rem; font-weight:600; cursor:pointer; }}
        .selection-review-continue:hover {{ background:#e94343; border-color:#e94343; }}
        #actionsHeading, #toolGrid {{ order: 1; }}
        #drawToolSettings, #measureToolSettings {{ order: 2; margin:2px 0 7px; }}
        #vertexPanel, #anglePanel, #edgePanel, #regionPanel {{ order: 3; }}
        #runRequirement {{ order: 4; }}
        #selectionControls {{ order: 5; }}
        #placeholderText {{ order: 6; }}
        #panelHeader {{ display: none; }}
        .tool-heading {{ margin:0 0 7px; color:#111827; font-size:1.1rem; font-weight:600; line-height:1.2; }}
        .mode-row {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }}
        .mode-option {{ display: flex; align-items: center; gap: 5px; color: #303440; font-size: 15px; cursor: pointer; }}
        .mode-option input {{ accent-color: #ff4b4b; cursor: pointer; }}
        .selection-list {{ margin:0 0 10px; }}
        .section-title {{ margin:2px 0 5px; color:#6b7280; font-size:12px; font-weight:700; letter-spacing:.04em; text-transform:uppercase; }}
        .selection-row {{ display:flex; align-items:center; justify-content:space-between; gap:8px; padding:5px 7px; margin-top:4px; border-radius:6px; color:#374151; font-size:14px; }}
        .selection-row > span::before {{ content:'•'; margin-right:10px; color:#374151; }}
        .selection-row:hover {{ background:rgba(150,150,150,0.15); }}
        .selection-remove {{ opacity:1; color:#b42318; background:#fff5f5; border:1px solid #efb7b2; font-size:18px; font-weight:700; line-height:1; min-height:2rem; padding:0.1rem 0.4rem; cursor:pointer; border-radius:6px; transition:background-color .15s ease,border-color .15s ease; }}
        .selection-remove:hover {{ color:#8f1d14; background:#fee4e2; border-color:#d92d20; }}
        .selection-echo {{ display:none !important; }}
        .tool-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:6px 10px; margin-bottom:8px; }}
        .tool-choice {{ background:#fff; color:#374151; border:1px solid #cbd5e1; padding:8px 7px; border-radius:5px; cursor:pointer; font-size:15px; font-weight:400; text-align:left; }}
        .tool-choice:hover {{ background:#f8fafc; border-color:#94a3b8; }}
        .tool-choice.active {{ background:#e3f9ea; border-color:#8fd4a8; color:#1e5631; }}
        .tool-info {{ display:none; box-sizing:border-box; width:100%; background:#eaf3ff; color:#0756a5; border-radius:10px; padding:14px 18px; font-size:15px; line-height:1.5; }}
        .tool-info ul {{ margin:0; padding-left:22px; }}
        .tool-info li {{ padding-left:5px; }}
        .category-section {{ display:none; }}
        .setting-label {{ margin:2px 0 4px; color:#4b5563; font-size:13px; font-weight:600; }}
        .setting-choice {{ display:flex; align-items:center; gap:6px; margin:4px 0 6px; color:#374151; font-size:14px; }}
        .setting-choice input {{ accent-color:#ff4b4b; }}
        .ray-directions {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:0 12px; margin:0 0 6px 22px; }}
        .run-requirement {{ display:none; color:rgba(49,51,63,0.6); background:transparent; border:none; border-radius:0; font-size:14px; font-weight:400; line-height:1.4; padding:0; margin:7px 0 10px; }}
        .status-box, .angle-box, .region-box {{ padding: 10px; margin-bottom: 9px; font-size: 15px; font-weight: 500; border-radius: 0 5px 5px 0; }}
        .status-box {{ background-color: #EDF7ED; border-left: 3px solid #4CAF50; color: #1E4620; }}
        .angle-box, .region-box {{ background-color: #FFF8E1; border-left: 3px solid #FFA000; color: #5D4037; }}
        .edge-box {{ padding:5px 7px; margin:0 0 8px; color:#374151; font-size:14px; }}
        .info-box {{ padding: 8px; background-color: #E3F2FD; border-left: 3px solid #2196F3; color: #0D47A1; margin-bottom: 8px; font-size: 12px; border-radius: 0 5px 5px 0; }}
        .hidden {{ display: none !important; }}
        .action-btn, .angle-btn, .edge-btn, .region-btn {{ background: #ffffff; color: #374151; border: 1px solid #cbd5e1; padding: 11px; border-radius: 6px; cursor: pointer; font-weight: 500; margin-top: 5px; width: 100%; font-size: 15px; transition: background 0.2s, border-color 0.2s; }}
        .action-btn:hover, .angle-btn:hover, .edge-btn:hover, .region-btn:hover {{ background: #f8fafc; border-color: #94a3b8; }}
        .measure-btn {{ background: #ffffff; color: #374151; border: 1px solid #cbd5e1; padding: 11px; border-radius: 6px; cursor: pointer; font-weight: 500; margin-top: 5px; width: 100%; font-size: 15px; transition: background 0.2s, border-color 0.2s; }}
        .measure-btn:hover {{ background: #f8fafc; border-color: #94a3b8; }}
        .sec-btn {{ background: #ffffff; color: #374151; border: 1px solid #cbd5e1; margin-top: 5px; width:100%; text-align:center; padding:11px; border-radius:6px; cursor:pointer; font-size:15px; font-weight:500; box-shadow:0 1px 1px rgba(15,23,42,0.04); }}
        .sec-btn:hover {{ background: #f8fafc; border-color: #94a3b8; }}
        .cancel-btn {{ background: #ffffff; color: #374151; border: 1px solid #cbd5e1; }}
        .cancel-btn:hover {{ background: #f8fafc; border-color: #94a3b8; }}
        .run-btn {{ background:#ff4b4b; color:#fff; border-color:#ff4b4b; font-weight:600; }}
        .run-btn:hover {{ background:#e94343; color:#fff; border-color:#e94343; }}
        .run-btn:disabled {{ background:#f3f4f6; color:#a3a7b0; border-color:#d1d5db; cursor:not-allowed; opacity:1; }}
        .run-btn:disabled:hover {{ background:#f3f4f6; color:#a3a7b0; border-color:#d1d5db; }}
    </style>
</head>
<body>
    <div class="right-panel">
        {selection_review_panel}
        <div id="actionsHeading" class="tool-heading {'hidden' if selection_only_demo else ''}">Tools</div>
        <div id="toolGrid" class="tool-grid {'hidden' if selection_only_demo else ''}">
            <button class="tool-choice" data-category="highlight">Highlight</button>
            <button class="tool-choice" data-category="measure">Measure</button>
            <button class="tool-choice" data-category="draw">Draw Line</button>
            <button class="tool-choice" data-category="merge">Merge</button>
        </div>
        <div id="drawToolSettings" class="category-section" data-category="draw">
            <div class="setting-label">Draw Line</div>
            <label class="setting-choice"><input type="radio" name="globalDrawKind" value="segment"> Segment</label>
            <label class="setting-choice"><input type="radio" name="globalDrawKind" value="ray"> Ray</label>
            <div id="rayDirectionSettings" class="ray-directions hidden">
                <label class="setting-choice"><input type="radio" name="globalRayDirection" value="up"> Up</label>
                <label class="setting-choice"><input type="radio" name="globalRayDirection" value="down"> Down</label>
                <label class="setting-choice"><input type="radio" name="globalRayDirection" value="left"> Left</label>
                <label class="setting-choice"><input type="radio" name="globalRayDirection" value="right"> Right</label>
            </div>
            <label class="setting-choice"><input type="radio" name="globalDrawKind" value="extend" {'checked' if tool_mode == 'Edge' else ''}> Extend edge</label>
        </div>
        <div id="measureToolSettings" class="category-section" data-category="measure">
            <div class="setting-label">Measure what?</div>
            <div class="mode-row">
                <label class="mode-option"><input type="radio" name="globalMeasureKind" value="distance" {'checked' if measure_kind == 'distance' else ''}> Distance</label>
                <label class="mode-option"><input type="radio" name="globalMeasureKind" value="angle" {'checked' if measure_kind == 'angle' else ''}> Angle</label>
                <label class="mode-option"><input type="radio" name="globalMeasureKind" value="area" {'checked' if measure_kind == 'area' else ''}> Area</label>
            </div>
        </div>
        <div id="selectionControls">
            <div class="tool-heading" style="font-size:1.25rem; font-weight:600; margin:0.5rem 0 0.35rem 0;">Selection</div>
            <div class="mode-row" role="radiogroup" aria-label="Select object type">
                {selection_mode_options}
            </div>
            {selection_practice_panel}
            <div id="selectionSection" class="{selection_section_class}">
                <div id="selectionList" class="selection-list">{selection_rows_html}</div>
            </div>
        </div>
        <h3 id="panelHeader" style="margin-top:0; color:#111; font-size:18px; border-bottom:2px solid #F0F0F0; padding-bottom:10px;">Tools: {tool_mode}</h3>

        <div id="placeholderText" class="hidden"></div>

        <div id="vertexPanel" class="hidden">
            <div id="normalForm">
                <div class="category-section" data-category="highlight">
                    <button class="action-btn run-btn" id="submitBtn">▶ RUN</button>
                </div>
                <div class="category-section" data-category="draw" style="margin-top:8px;">
                    <label style="display:none"><input type="radio" name="vertexLineStyle" value="segment" {'checked' if demo_line_style in {'', 'segment'} else ''}></label>
                    <label style="display:none"><input type="radio" name="vertexLineStyle" value="up" {'checked' if demo_line_style == 'up' else ''}></label>
                    <label style="display:none"><input type="radio" name="vertexLineStyle" value="down" {'checked' if demo_line_style == 'down' else ''}></label>
                    <label style="display:none"><input type="radio" name="vertexLineStyle" value="left" {'checked' if demo_line_style == 'left' else ''}></label>
                    <label style="display:none"><input type="radio" name="vertexLineStyle" value="right" {'checked' if demo_line_style == 'right' else ''}></label>
                    <button class="sec-btn run-btn" id="runVertexLineBtn">▶ RUN</button>
                </div>
                <div class="category-section" data-category="measure">
                    <button class="measure-btn run-btn" id="measureDistanceSingleBtn">▶ RUN</button>
                </div>
            </div>
            <div id="connectionForm" class="hidden">
                <div class="category-section" data-category="draw">
                    <button class="action-btn run-btn" id="confirmConnectBtn">▶ RUN</button>
                </div>
                <div class="category-section" data-category="measure">
                    <button class="measure-btn run-btn" id="measureDistanceBtn">▶ RUN</button>
                </div>
                <button class="action-btn cancel-btn" id="cancelConnectBtn">Clear Selection</button>
            </div>
        </div>

        <div id="anglePanel" class="hidden">
            <div class="category-section" data-category="highlight"><button class="angle-btn run-btn" id="commitAngleBtn">▶ RUN</button></div>
            <div class="category-section" data-category="measure">
                <button type="button" class="measure-btn run-btn" id="measureAngleBtn" onclick="runMeasureAngle()">▶ RUN</button>
            </div>
        </div>

        <div id="edgePanel" class="hidden">
            <div id="edgeHiddenWarning" class="info-box hidden">
                This edge is hidden by a union.
            </div>
            <div id="edgeActiveContent" class="hidden">
                <div id="edgeSelectionBox" class="edge-box selection-echo">
                    <span id="edge_label_span">-</span>
                </div>
                <div id="edgeBoundaryPrompt" class="category-section" data-category="highlight" style="font-size:12px; color:#777; margin-bottom:8px;">Which region's boundary?</div>
                <div class="category-section" data-category="highlight">
                    <label class="setting-choice" id="edgeMainChoice"><input type="radio" name="edgeSide" value="main"> <span id="edgeMainLabel">-</span></label>
                    <label class="setting-choice" id="edgeOppoChoice"><input type="radio" name="edgeSide" value="oppo"> <span id="edgeOppoLabel">-</span></label>
                    <button class="edge-btn run-btn" id="edgeHighlightRun">▶ RUN</button>
                </div>
                <div class="category-section" data-category="draw">
                    <button class="sec-btn run-btn" id="extendEdgeBtn">▶ RUN</button>
                </div>
            </div>
        </div>

        <div id="regionPanel" class="hidden">
            <div id="mergedFormationAlert" class="status-box selection-echo hidden" style="background-color: #E8F5E9; border-left-color: #2E7D32; color: #1B5E20;">
                <b>Region U</b>
            </div>
            
            <div id="normalRegionBox" class="region-box selection-echo">
                <b>Region:</b> <span id="region_label_span">-</span>
            </div>

            <div class="category-section" data-category="highlight">
                <button class="region-btn run-btn" id="commitRegionBtn">▶ RUN</button>
                <button class="region-btn run-btn hidden" id="commitUnionHighlightBtn">▶ RUN</button>
            </div>
            <div class="category-section" data-category="measure">
                <button class="measure-btn run-btn" id="measureRegionBtn">▶ RUN</button>
            </div>
            <button class="sec-btn hidden" id="clearUnionBtn" style="margin-top: 8px; background: #F5F5F5; color: #333; border-color: #BBB;">Clear Region U</button>

            <div id="unionConstructionSection" style="display:none; margin-top:20px; border-top:1px dashed #DDD; padding-top:15px;">
                <span style="font-size:12px; font-weight:bold; color:#777;">Union Construction:</span>
                <button class="sec-btn" id="addToBufferBtn" style="margin-top: 8px;">➕ Add to Union Buffer</button>
                <button class="sec-btn cancel-btn" id="removeFromBufferBtn" style="margin-top: 8px; display:none;">Remove from Buffer</button>
                <div id="bufferWarning" style="color: #D32F2F; font-size: 11px; margin-top: 5px; font-weight: 500;" class="hidden"></div>
            </div>

            <div id="globalBufferBox" data-category="merge" style="margin-top:15px;" class="category-section">
                <p class="selection-echo">Selected regions: <b id="staged_letters_span">-</b></p>
                <div style="display: flex; gap: 8px;">
                    <button class="action-btn run-btn" id="execUnionBtn" style="flex:1; margin-top:0;">▶ RUN</button>
                </div>
            </div>
        </div>
        <div id="runRequirement" class="run-requirement"></div>
    </div>

    <div class="diagram-column">
        <div class="pad-container">
            <canvas id="bgCanvas" width="{DISPLAY_SIDE}" height="{DISPLAY_SIDE}"></canvas>
            <canvas id="interactionCanvas" width="{DISPLAY_SIDE}" height="{DISPLAY_SIDE}"></canvas>
        </div>
        {selection_practice_banner}
        <div id="toolInfo" class="tool-info"></div>
    </div>

    <script>
        function sendStreamlit(type, data) {{
            window.parent.postMessage(Object.assign({{isStreamlitMessage: true, type: type}}, data), "*");
        }}
        const StreamlitBridge = {{
            ready: function() {{ sendStreamlit("streamlit:componentReady", {{apiVersion: 1}}); }},
            height: function(h) {{ sendStreamlit("streamlit:setFrameHeight", {{height: h}}); }},
            value: function(v) {{ sendStreamlit("streamlit:setComponentValue", {{value: v, dataType: "json"}}); }}
        }};

        const toolMode = "{tool_mode}";
        const measureKind = "{measure_kind}";
        const lastRunMessage = {json.dumps(data.get("last_run_message", ""))};
        const selectionOnlyDemo = {str(selection_only_demo).lower()};
        const tutorialLineStyle = {json.dumps(demo_line_style)};
        const hasStartPoint = {str(has_start_point).lower()};
        const startPointId = "{start_point_id}";
        const lastActiveId = "{last_active_id}";
        const selectedVertexIds = {json.dumps(selected_vertex_ids)};
        const selectedVertexLabels = {json.dumps(vertex_selection_labels)};
        const selectedRegionIndices = {json.dumps(selected_region_indices)};
        const selectedAngle = {json.dumps(selected_angle)};
        const selectedEdge = {json.dumps(selected_edge)};
        const selectedAngles = {json.dumps(selected_angles)};
        const selectedEdges = {json.dumps(selected_edges)};
        const anglePreviewLabels = {json.dumps(angle_preview_labels)};
        const edgePreviewLabels = {json.dumps(edge_preview_labels)};
        
        const hasExistingUnion = {str(has_existing_union).lower()};
        const bufferIndices = {json.dumps(buffer_indices)};
        const bufferLetters = {json.dumps(buffer_letters)};
        const obsoleteFacesUnionInfo = {json.dumps(obsolete_faces_union_info)};

        const vertices = {json.dumps(vertices_data)};
        const facesData = {json.dumps(faces_data)};
        const edgesData = {json.dumps(edges_data)};

        const bgCanvas = document.getElementById('bgCanvas');
        const bgCtx = bgCanvas.getContext('2d');
        const interCanvas = document.getElementById('interactionCanvas');
        const interCtx = interCanvas.getContext('2d');
        const pageLoadClientMs = Date.now();

        const img = new Image();
        img.onload = () => bgCtx.drawImage(img, 0, 0);
        img.src = "data:image/png;base64,{img_base64}";

        let hoverV = null, hoverFace = null, hoverEdge = null;
        let selectedElement = null;
        let lockedV = null, lockedFace = null, lockedEdge = null;
        const tutorialActiveCategory = {json.dumps(demo_active_category)};
        const surveyUiResetToken = {json.dumps(survey_ui_reset_token)};
        const reviewUiResetToken = {json.dumps(review_ui_reset_token)};
        if (reviewUiResetToken && sessionStorage.getItem('annotationReviewResetToken') !== reviewUiResetToken) {{
            sessionStorage.removeItem('annotationActiveTool');
            sessionStorage.removeItem('annotationLineStyle');
            sessionStorage.removeItem('annotationDrawKind');
            sessionStorage.setItem('annotationReviewResetToken', reviewUiResetToken);
        }}
        if (surveyUiResetToken && sessionStorage.getItem('annotationSurveyResetToken') !== surveyUiResetToken) {{
            sessionStorage.removeItem('annotationActiveTool');
            sessionStorage.removeItem('annotationLineStyle');
            sessionStorage.removeItem('annotationDrawKind');
            sessionStorage.setItem('annotationSurveyResetToken', surveyUiResetToken);
        }}
        let activeCategory = tutorialActiveCategory || sessionStorage.getItem('annotationActiveTool') || null;
        if (tutorialActiveCategory) sessionStorage.setItem('annotationActiveTool', tutorialActiveCategory);
        const savedLineStyle = tutorialLineStyle || sessionStorage.getItem('annotationLineStyle') || 'segment';
        const savedDrawKind = tutorialLineStyle
            ? (tutorialLineStyle === 'segment' ? 'segment' : 'ray')
            : sessionStorage.getItem('annotationDrawKind')
                || (savedLineStyle === 'segment' ? 'segment' : 'ray');
        document.querySelectorAll('input[name="vertexLineStyle"]').forEach(input => {{
            input.checked = input.value === savedLineStyle;
            input.addEventListener('change', () => {{
                if (input.checked) sessionStorage.setItem('annotationLineStyle', input.value);
            }});
        }});
        document.querySelectorAll('input[name="globalDrawKind"]').forEach(input => {{
            input.checked = toolMode === 'Edge'
                ? input.value === 'extend'
                : input.value === savedDrawKind;
        }});
        document.querySelectorAll('input[name="globalRayDirection"]').forEach(input => {{
            input.checked = input.value === savedLineStyle;
        }});
        if (tutorialLineStyle) {{
            sessionStorage.setItem('annotationLineStyle', tutorialLineStyle);
            sessionStorage.setItem('annotationDrawKind', tutorialLineStyle === 'segment' ? 'segment' : 'ray');
        }}

        function updateRayDirectionVisibility() {{
            const raySelected = document.querySelector('input[name="globalDrawKind"]:checked')?.value === 'ray';
            document.getElementById('rayDirectionSettings')?.classList.toggle('hidden', !raySelected);
        }}
        updateRayDirectionVisibility();

        function isPointInPolygon(mx, my, polyVertices) {{
            let inside = false;
            for (let i = 0, j = polyVertices.length - 1; i < polyVertices.length; j = i++) {{
                const xi = polyVertices[i].x, yi = polyVertices[i].y;
                const xj = polyVertices[j].x, yj = polyVertices[j].y;
                const intersect = ((yi > my) !== (yj > my))
                    && (mx < (xj - xi) * (my - yi) / (yj - yi) + xi);
                if (intersect) inside = !inside;
            }}
            return inside;
        }}

        function interiorArcSpec(face, vertex, previous, following) {{
            const start = Math.atan2(previous.y - vertex.y, previous.x - vertex.x);
            const finish = Math.atan2(following.y - vertex.y, following.x - vertex.x);
            let clockwiseSweep = finish - start;
            while (clockwiseSweep < 0) clockwiseSweep += 2 * Math.PI;
            // Probe the middle of the clockwise candidate. If that direction
            // is outside the polygon, the interior is the complementary arc.
            const probeRadius = 9;
            const clockwiseMid = start + clockwiseSweep / 2;
            const clockwiseInside = isPointInPolygon(
                vertex.x + probeRadius * Math.cos(clockwiseMid),
                vertex.y + probeRadius * Math.sin(clockwiseMid),
                face.vertices
            );
            if (clockwiseInside) {{
                return {{
                    start,
                    end: start + clockwiseSweep,
                    mid: start + clockwiseSweep / 2,
                    anticlockwise: false
                }};
            }}
            const reverseSweep = 2 * Math.PI - clockwiseSweep;
            return {{
                start: finish,
                end: finish + reverseSweep,
                mid: finish + reverseSweep / 2,
                anticlockwise: false
            }};
        }}

        function unionBoundaryFace(face) {{
            if (!face?.is_obsolete || face.union_partner_idx === null) return face;
            const partner = facesData.find(f => Number(f.cache_idx) === Number(face.union_partner_idx));
            if (!partner) return face;

            const edgeMap = new Map();
            const vertexById = new Map();
            for (const source of [face, partner]) {{
                const verts = source.vertices;
                for (let i = 0; i < verts.length; i++) {{
                    const a = verts[i];
                    const b = verts[(i + 1) % verts.length];
                    vertexById.set(String(a.id), a);
                    vertexById.set(String(b.id), b);
                    const key = [String(a.id), String(b.id)].sort().join('|');
                    const entry = edgeMap.get(key) || {{count: 0, a: String(a.id), b: String(b.id)}};
                    entry.count += 1;
                    edgeMap.set(key, entry);
                }}
            }}

            const adjacency = new Map();
            for (const edge of edgeMap.values()) {{
                if (edge.count !== 1) continue;
                if (!adjacency.has(edge.a)) adjacency.set(edge.a, []);
                if (!adjacency.has(edge.b)) adjacency.set(edge.b, []);
                adjacency.get(edge.a).push(edge.b);
                adjacency.get(edge.b).push(edge.a);
            }}
            const ids = [...adjacency.keys()];
            if (ids.length < 3) return face;
            const orderedIds = [];
            const start = ids[0];
            let previous = null;
            let current = start;
            for (let guard = 0; guard <= ids.length; guard++) {{
                orderedIds.push(current);
                const neighbors = adjacency.get(current) || [];
                const next = neighbors.find(id => id !== previous && (id !== start || orderedIds.length === ids.length))
                    || neighbors.find(id => id !== previous);
                if (!next || next === start) break;
                previous = current;
                current = next;
            }}
            let boundaryVertices = orderedIds.map(id => vertexById.get(id)).filter(Boolean);
            if (boundaryVertices.length < 3) return face;
            // Remove former constituent corners that became 180-degree points
            // on U's outer boundary. They are not selectable angles of U.
            let changed = true;
            while (changed && boundaryVertices.length >= 3) {{
                changed = false;
                boundaryVertices = boundaryVertices.filter((current, index, items) => {{
                    const previous = items[(index - 1 + items.length) % items.length];
                    const following = items[(index + 1) % items.length];
                    const inX = current.x - previous.x;
                    const inY = current.y - previous.y;
                    const outX = following.x - current.x;
                    const outY = following.y - current.y;
                    const cross = inX * outY - inY * outX;
                    const dot = inX * outX + inY * outY;
                    const scale = Math.max(Math.hypot(inX, inY) * Math.hypot(outX, outY), 1e-12);
                    const isStraightThrough = Math.abs(cross) <= 1e-7 * scale && dot > 0;
                    if (isStraightThrough) changed = true;
                    return !isStraightThrough;
                }});
            }}
            if (boundaryVertices.length < 3) return face;
            return {{
                ...face,
                display: 'U',
                vertices: boundaryVertices,
                valid_corner_ids: boundaryVertices.map(v => v.id),
                is_union_boundary: true,
            }};
        }}

        if (!selectionOnlyDemo && toolMode === "Vertex" && selectedVertexIds.length > 0) {{
            const found = vertices.find(v => String(v.id) === String(selectedVertexIds[selectedVertexIds.length - 1]));
            if (found) {{
                lockedV = found;
                showVertexPanel(found);
                document.getElementById('actionsHeading').classList.remove('hidden');
                configureToolGrid('vertex');
            }}
        }} else if (!selectionOnlyDemo && toolMode === "Region" && selectedRegionIndices.length > 0) {{
            const found = facesData.find(f => Number(f.cache_idx) === Number(selectedRegionIndices[selectedRegionIndices.length - 1]));
            if (found) {{
                lockedFace = found;
                showRegionPanel(found);
                document.getElementById('actionsHeading').classList.remove('hidden');
                configureToolGrid('region');
            }}
        }} else if (!selectionOnlyDemo && toolMode === "Angle" && selectedAngle) {{
            const foundV = vertices.find(v => String(v.id) === String(selectedAngle.vertex_id));
            const rawFoundF = facesData.find(f => Number(f.cache_idx) === Number(selectedAngle.face_idx));
            const foundF = unionBoundaryFace(rawFoundF);
            if (foundV && foundF) {{
                lockedV = foundV;
                lockedFace = foundF;
                selectedElement = {{ type: "Angle", data: {{ v: foundV, f: foundF }} }};
                showAnglePanel(foundV, foundF);
                configureToolGrid('angle');
            }}
        }} else if (!selectionOnlyDemo && toolMode === "Edge" && selectedEdge) {{
            const foundE = edgesData.find(e =>
                (Number(selectedEdge.edge_idx) >= 0 && Number(e.edge_idx) === Number(selectedEdge.edge_idx)) ||
                ((Number(e.tail_id) === Number(selectedEdge.tail_id) && Number(e.head_id) === Number(selectedEdge.head_id)) ||
                 (Number(e.tail_id) === Number(selectedEdge.head_id) && Number(e.head_id) === Number(selectedEdge.tail_id)))
            );
            if (foundE) {{
                lockedEdge = foundE;
                selectedElement = {{ type: "Edge", data: foundE }};
                showEdgePanel(foundE);
                configureToolGrid('edge');
            }}
        }} else if (!selectionOnlyDemo && toolMode === "Vertex") {{
            showVertexPanel(null);
            configureToolGrid('vertex');
        }} else if (!selectionOnlyDemo && toolMode === "Angle") {{
            showAnglePanel(null, null);
            configureToolGrid('angle');
        }} else if (!selectionOnlyDemo && toolMode === "Edge") {{
            showEdgePanel(null);
            configureToolGrid('edge');
        }} else if (!selectionOnlyDemo && toolMode === "Region") {{
            showRegionPanel(null);
            configureToolGrid('region');
        }}
        if (selectionOnlyDemo && toolMode === "Angle" && selectedAngle) {{
            lockedV = vertices.find(v => String(v.id) === String(selectedAngle.vertex_id)) || null;
            lockedFace = unionBoundaryFace(
                facesData.find(f => Number(f.cache_idx) === Number(selectedAngle.face_idx)) || null
            );
            if (lockedV && lockedFace) selectedElement = {{ type: "Angle", data: {{ v: lockedV, f: lockedFace }} }};
        }} else if (selectionOnlyDemo && toolMode === "Edge" && selectedEdge) {{
            lockedEdge = edgesData.find(e =>
                (Number(selectedEdge.edge_idx) >= 0 && Number(e.edge_idx) === Number(selectedEdge.edge_idx)) ||
                ((Number(e.tail_id) === Number(selectedEdge.tail_id) && Number(e.head_id) === Number(selectedEdge.head_id)) ||
                 (Number(e.tail_id) === Number(selectedEdge.head_id) && Number(e.head_id) === Number(selectedEdge.tail_id)))
            ) || null;
            if (lockedEdge) selectedElement = {{ type: "Edge", data: lockedEdge }};
        }}

        interCanvas.addEventListener('mousemove', function(e) {{
            // The backup implementation freezes an edge after click. Without
            // this guard, moving the pointer from the diagram toward RUN can
            // silently replace lockedEdge with the last edge crossed.
            // Freeze an edge only while it is the operand of Draw Line /
            // Extend edge. In ordinary selection mode the pointer may move to
            // another edge so several edges can be retained as e1, e2, e3…
            if (selectedElement?.type === 'Edge' && activeCategory === 'draw') return;
            // Angle selections remain replaceable; other selected objects stay
            // locked until explicitly removed.
            if (selectedElement && !['Angle', 'Edge'].includes(toolMode)) return;

            const rect = interCanvas.getBoundingClientRect();
            const mx = (e.clientX - rect.left) * interCanvas.width / rect.width;
            const my = (e.clientY - rect.top) * interCanvas.height / rect.height;

            hoverV = null; hoverFace = null; hoverEdge = null;

            if (toolMode === "Vertex") {{
                for (let v of vertices) {{
                    if (v.is_obsolete) continue;
                    if (Math.sqrt((mx-v.x)**2 + (my-v.y)**2) < 20) {{
                        hoverV = v;
                        lockedV = v;
                        break;
                    }}
                }}

            }} else if (toolMode === "Angle") {{
                // Several regions meet at a vertex. Evaluate every containing
                // face instead of accepting the first facesData entry, which
                // made a neighboring ordinary region mask Region U's reflex
                // interior angle.
                const containingCandidates = [];
                const seenCandidateKeys = new Set();
                for (const rawFace of facesData) {{
                    if (!isPointInPolygon(mx, my, rawFace.vertices)) continue;
                    const candidate = unionBoundaryFace(rawFace);
                    const candidateKey = candidate.is_union_boundary
                        ? 'union'
                        : String(candidate.cache_idx);
                    if (seenCandidateKeys.has(candidateKey)) continue;
                    seenCandidateKeys.add(candidateKey);
                    let boundaryDistance = Infinity;
                    for (let i = 0; i < candidate.vertices.length; i++) {{
                        const a = candidate.vertices[i];
                        const b = candidate.vertices[(i + 1) % candidate.vertices.length];
                        const dx = b.x - a.x;
                        const dy = b.y - a.y;
                        const lengthSq = dx * dx + dy * dy;
                        let t = lengthSq > 0
                            ? ((mx - a.x) * dx + (my - a.y) * dy) / lengthSq
                            : 0;
                        t = Math.max(0, Math.min(1, t));
                        boundaryDistance = Math.min(
                            boundaryDistance,
                            Math.hypot(mx - (a.x + t * dx), my - (a.y + t * dy))
                        );
                    }}
                    containingCandidates.push({{face: candidate, boundaryDistance}});
                }}
                containingCandidates.sort((left, right) =>
                    right.boundaryDistance - left.boundaryDistance
                    || Number(Boolean(right.face.is_union_boundary))
                       - Number(Boolean(left.face.is_union_boundary))
                );
                let activeContainingFace = containingCandidates[0]?.face || null;
                if (activeContainingFace) {{
                    let nearestFaceVertex = null;
                    let strictMinDist = 9999;
                    for (let v of activeContainingFace.vertices) {{
                        const fullVect = vertices.find(origV => origV.id === v.id);
                        if (!fullVect) continue;
                        // Skip if this vertex is not a valid corner
                        if (!Array.isArray(activeContainingFace.valid_corner_ids) || !activeContainingFace.valid_corner_ids.includes(v.id)) continue;
                        const d = Math.sqrt((mx - fullVect.x)**2 + (my - fullVect.y)**2);
                        if (d < strictMinDist) {{ strictMinDist = d; nearestFaceVertex = fullVect; }}
                    }}
                    if (nearestFaceVertex && strictMinDist < 35) {{
                        hoverV = nearestFaceVertex;
                        lockedV = nearestFaceVertex;
                        hoverFace = activeContainingFace;
                        lockedFace = activeContainingFace;
                    }}
                }}

            }} else if (toolMode === "Edge") {{
                let bestEdge = null;
                let bestDist = 9999;
                for (let e of edgesData) {{
                    if (e.is_obsolete) continue;
                    const dx = e.x2 - e.x1;
                    const dy = e.y2 - e.y1;
                    const lenSq = dx*dx + dy*dy;
                    let t = lenSq > 0 ? ((mx-e.x1)*dx + (my-e.y1)*dy) / lenSq : 0;
                    t = Math.max(0, Math.min(1, t));
                    const nearX = e.x1 + t*dx;
                    const nearY = e.y1 + t*dy;
                    const dist = Math.sqrt((nearX-mx)**2 + (nearY-my)**2);
                    // At a vertex, several edges can have essentially the same
                    // distance. Prefer an internal edge over a frame edge in
                    // that tie; clicking the middle of a frame edge still
                    // selects the frame edge normally.
                    const winsByDistance = dist < bestDist - 1;
                    const winsTie = Math.abs(dist - bestDist) <= 1
                        && bestEdge?.is_frame && !e.is_frame;
                    if (winsByDistance || winsTie) {{
                        bestDist = dist;
                        bestEdge = e;
                    }}
                }}
                if (bestEdge && bestDist < 18) {{
                    hoverEdge = bestEdge;
                    lockedEdge = bestEdge;
                }}

            }} else if (toolMode === "Region") {{
                let targetFace = null;
                for (let f of facesData) {{
                    if (isPointInPolygon(mx, my, f.vertices)) {{
                        targetFace = f;
                        break;
                    }}
                }}
                if (!targetFace) {{
                    let minFaceDist = 9999;
                    for (let f of facesData) {{
                        const fd = Math.sqrt((mx - f.cx)**2 + (my - f.cy)**2);
                        if (fd < minFaceDist && fd < 60) {{ minFaceDist = fd; targetFace = f; }}
                    }}
                }}
                if (targetFace) {{
                    hoverFace = targetFace;
                    lockedFace = targetFace;
                }}
            }}

            redraw();
        }});

        interCanvas.addEventListener('click', function(e) {{
            const clickRect = interCanvas.getBoundingClientRect();
            const clickX = (e.clientX - clickRect.left) * interCanvas.width / clickRect.width;
            const clickY = (e.clientY - clickRect.top) * interCanvas.height / clickRect.height;
            interCanvas.dataset.lastClickX = String(clickX);
            interCanvas.dataset.lastClickY = String(clickY);
            if (toolMode === "Vertex") {{
                // Resolve the target from the click itself.  Relying on the
                // preceding mousemove leaves hoverV empty after a component
                // rerender and can make the second vertex click do nothing.
                const rect = interCanvas.getBoundingClientRect();
                const mx = (e.clientX - rect.left) * interCanvas.width / rect.width;
                const my = (e.clientY - rect.top) * interCanvas.height / rect.height;
                const clickedV = vertices.find(v =>
                    !v.is_obsolete && Math.hypot(mx - v.x, my - v.y) < 20
                );
                if (clickedV) {{
                    lockedV = clickedV;
                    hoverV = clickedV;
                    dispatchAction('select_vertex');
                    return;
                }}
            }}
            if (toolMode === "Region" && lockedFace && hoverFace) {{
                dispatchAction('select_region', {{ bridge_face: lockedFace.cache_idx }});
                return;
            }}
            if (toolMode === "Angle" && lockedV && lockedFace && hoverV) {{
                dispatchAction('select_angle', {{
                    bridge_face: lockedFace.cache_idx,
                    bridge_face_name: lockedFace.display
                }});
                return;
            }}
            if (toolMode === "Edge" && lockedEdge && hoverEdge) {{
                if (!selectionOnlyDemo) {{
                    // Match the stable pre-multiselect implementation: keep
                    // the exact hit-tested edge in the browser until RUN.
                    // A server rerun between click and RUN can reconstruct a
                    // different edge, especially near shared vertices.
                    selectedElement = {{ type: "Edge", data: lockedEdge }};
                    showEdgePanel(lockedEdge);
                    document.getElementById('selectionSection').classList.remove('hidden');
                    document.getElementById('selectedEdgeRow')?.remove();
                    document.getElementById('transientSelectionRow')?.remove();
                    const selectionList = document.getElementById('selectionList');
                    const transientEdgeLabel = edgeSelectionText(lockedEdge);
                    selectionList.insertAdjacentHTML(
                        'beforeend',
                        '<div id="transientSelectionRow" class="selection-row">'
                        + '<span>' + transientEdgeLabel + '</span><button id="removeTransientEdge" class="selection-remove" '
                        + 'aria-label="Remove selected edge">✕</button></div>'
                    );
                    document.getElementById('removeTransientEdge')?.addEventListener('click', () => {{
                        selectedElement = null;
                        lockedEdge = null;
                        hoverEdge = null;
                        stalePanels();
                        redraw();
                        updateRunButtonStates();
                    }});
                    redraw();
                    updateRunButtonStates();
                    // Persist only the display/selection record. Extend still
                    // uses the exact frozen edge and its coordinates.
                    dispatchAction('select_edge', {{
                        bridge_edge_idx: lockedEdge.edge_idx,
                        bridge_tail: lockedEdge.tail_id,
                        bridge_head: lockedEdge.head_id,
                        bridge_label: edgeNaturalDescription(lockedEdge)
                    }});
                    return;
                }}
                dispatchAction('select_edge', {{
                    bridge_edge_idx: lockedEdge.edge_idx,
                    bridge_tail: lockedEdge.tail_id,
                    bridge_head: lockedEdge.head_id,
                    bridge_label: edgeNaturalDescription(lockedEdge)
                }});
                return;
            }}
            if (selectedElement) {{
                dispatchAction(
                    selectedElement.type === 'Angle' ? 'remove_selected_angle' : 'remove_selected_edge'
                );
                return;
            }}
            redraw();
        }});

        function configureToolGrid() {{
            if (selectionOnlyDemo) {{
                document.getElementById('actionsHeading').classList.add('hidden');
                document.getElementById('toolGrid').classList.add('hidden');
                document.getElementById('toolInfo').style.display = 'none';
                return;
            }}
            document.getElementById('toolGrid').classList.remove('hidden');
            document.querySelectorAll('.tool-choice').forEach(button => {{
                button.style.display = 'block';
                button.classList.toggle('active', button.dataset.category === activeCategory);
            }});
            document.querySelectorAll('.category-section').forEach(section => {{
                section.style.display = section.dataset.category === activeCategory ? 'block' : 'none';
            }});
            const regionMeasureBtn = document.getElementById('measureRegionBtn');
            if (regionMeasureBtn && activeCategory === 'measure' && toolMode === 'Region') {{
                regionMeasureBtn.classList.toggle('hidden', selectedRegionIndices.length !== 1);
            }}
            const info = document.getElementById('toolInfo');
            const measureInstruction = measureKind === 'distance'
                ? '<ul><li><strong>Select TWO Vertices</strong> → returns their distance in Output.</li></ul>'
                : measureKind === 'angle'
                    ? '<ul><li><strong>Select ONE Angle</strong> → returns its angle measurement in Output.</li></ul>'
                    : '<ul><li><strong>Select ONE Region</strong> → returns its area in Output.</li></ul>';
            const instructions = {{
                highlight: '<ul><li><strong>Select ONE Vertex, Angle, Edge, or Region</strong> → highlights that object.</li></ul>',
                measure: measureInstruction,
                draw: '<ul><li><strong>Select TWO Vertices</strong> → draws a segment between them.</li><li><strong>Select ONE Vertex</strong> → draws a ray up, down, left, or right.</li><li><strong>Select ONE Edge</strong> → extends the edge in both directions.</li></ul>',
                merge: '<ul><li><strong>Select TWO Regions</strong> → merges them into one new region. The regions must share an edge.</li></ul>'
            }};
            if (activeCategory && instructions[activeCategory]) {{
                info.innerHTML = instructions[activeCategory];
                info.style.display = 'block';
            }} else {{
                info.innerHTML = '';
                info.style.display = 'none';
            }}
            requestAnimationFrame(() => {{
                StreamlitBridge.height(Math.max({component_min_height}, document.documentElement.scrollHeight + 4));
            }});
            updateRunButtonStates();
        }}

        function setRunDisabled(id, disabled) {{
            const button = document.getElementById(id);
            if (button) button.disabled = Boolean(disabled);
        }}

        function selectedAngleData() {{
            if (selectedElement?.type === 'Angle' && selectedElement.data?.v && selectedElement.data?.f) {{
                return selectedElement.data;
            }}
            if (!selectedAngle) return null;
            const v = vertices.find(candidate => String(candidate.id) === String(selectedAngle.vertex_id));
            const rawFace = facesData.find(candidate => Number(candidate.cache_idx) === Number(selectedAngle.face_idx));
            const f = unionBoundaryFace(rawFace);
            return v && f ? {{ v, f }} : null;
        }}

        function selectedEdgeData() {{
            if (selectedElement?.type === 'Edge' && selectedElement.data) {{
                return selectedElement.data;
            }}
            if (!selectedEdge) return null;
            if (lockedEdge) return lockedEdge;
            return edgesData.find(e =>
                (Number(selectedEdge.edge_idx) >= 0 && Number(e.edge_idx) === Number(selectedEdge.edge_idx))
                || (Number(e.tail_id) === Number(selectedEdge.tail_id)
                    && Number(e.head_id) === Number(selectedEdge.head_id))
                || (Number(e.tail_id) === Number(selectedEdge.head_id)
                    && Number(e.head_id) === Number(selectedEdge.tail_id))
            ) || null;
        }}

        function totalSelectedInputs() {{
            return selectedVertexIds.length + selectedRegionIndices.length
                + selectedAngles.length + selectedEdges.length;
        }}

        function updateRunButtonStates() {{
            const drawKind = document.querySelector('input[name="globalDrawKind"]:checked')?.value || 'segment';
            const rayDirection = document.querySelector('input[name="globalRayDirection"]:checked')?.value || '';
            const lineStyle = drawKind === 'ray' ? rayDirection : drawKind;
            const totalSelections = totalSelectedInputs();
            const oneVertex = selectedVertexIds.length === 1;
            const twoVertices = selectedVertexIds.length === 2;
            const oneRegion = selectedRegionIndices.length === 1;
            const twoRegions = selectedRegionIndices.length === 2;
            const oneAngle = selectedAngles.length === 1;
            const oneEdge = selectedEdges.length === 1;
            const exactlyOneVertex = oneVertex && totalSelections === 1;
            const exactlyTwoVertices = twoVertices && totalSelections === 2;
            const exactlyOneRegion = oneRegion && totalSelections === 1;
            const exactlyTwoRegions = twoRegions && totalSelections === 2;
            const angleSelected = oneAngle && totalSelections === 1 && Boolean(selectedAngleData());
            const edgeSelected = oneEdge && totalSelections === 1 && Boolean(selectedEdgeData());
            const edgeSideSelected = Boolean(document.querySelector('input[name="edgeSide"]:checked'));

            setRunDisabled('submitBtn', !exactlyOneVertex);
            setRunDisabled('runVertexLineBtn', lineStyle === 'segment' ? !exactlyTwoVertices : (!rayDirection || !exactlyOneVertex));
            setRunDisabled('measureDistanceSingleBtn', !exactlyTwoVertices);
            setRunDisabled('confirmConnectBtn', !exactlyTwoVertices);
            setRunDisabled('measureDistanceBtn', !exactlyTwoVertices);
            setRunDisabled('commitAngleBtn', !angleSelected);
            setRunDisabled('measureAngleBtn', !angleSelected);
            setRunDisabled('edgeHighlightRun', !(edgeSelected && edgeSideSelected));
            setRunDisabled('extendEdgeBtn', !edgeSelected);
            setRunDisabled('commitRegionBtn', !exactlyOneRegion);
            setRunDisabled('commitUnionHighlightBtn', !exactlyOneRegion);
            setRunDisabled('measureRegionBtn', !exactlyOneRegion);
            setRunDisabled('execUnionBtn', !(exactlyTwoRegions && !hasExistingUnion));

            let requirement = '';
            if (activeCategory === 'highlight') {{
                const ready = toolMode === 'Vertex' ? exactlyOneVertex
                    : toolMode === 'Angle' ? angleSelected
                    : toolMode === 'Edge' ? (edgeSelected && edgeSideSelected)
                    : exactlyOneRegion;
                if (!ready) requirement = toolMode === 'Edge'
                    ? 'Select one edge and choose an adjacent region.'
                    : `Select exactly one ${{toolMode.toLowerCase()}}.`;
            }} else if (activeCategory === 'measure') {{
                if (measureKind === 'distance' && !exactlyTwoVertices) requirement = 'Select exactly two vertices.';
                else if (measureKind === 'angle' && !angleSelected) requirement = 'Select exactly one angle.';
                else if (measureKind === 'area' && !exactlyOneRegion) requirement = 'Select exactly one region.';
            }} else if (activeCategory === 'draw') {{
                if (toolMode === 'Vertex') {{
                    const ready = lineStyle === 'segment' ? exactlyTwoVertices : Boolean(rayDirection) && exactlyOneVertex;
                    if (!ready) requirement = drawKind === 'ray' && !rayDirection
                        ? 'Choose a ray direction.'
                        : lineStyle === 'segment' ? 'Select exactly two vertices.' : 'Select exactly one vertex.';
                }} else if (toolMode === 'Edge' && !edgeSelected) requirement = 'Select exactly one edge.';
                else if (!['Vertex', 'Edge'].includes(toolMode)) requirement = 'Choose Vertex or Edge under Selection.';
            }} else if (activeCategory === 'merge' && !(exactlyTwoRegions && !hasExistingUnion)) {{
                requirement = hasExistingUnion
                    ? 'Clear the existing union before creating another.'
                    : 'Select exactly two neighboring regions.';
            }}
            const requirementBox = document.getElementById('runRequirement');
            requirementBox.textContent = requirement;
            requirementBox.style.display = requirement ? 'block' : 'none';
        }}

        document.querySelectorAll('.tool-choice').forEach(button => {{
            button.addEventListener('click', () => {{
                activeCategory = button.dataset.category;
                sessionStorage.setItem('annotationActiveTool', activeCategory);
                configureToolGrid();
            }});
        }});

        document.querySelectorAll('input[name="globalDrawKind"]').forEach(input => {{
            input.addEventListener('change', () => {{
                if (!input.checked) return;
                const targetMode = input.value === 'extend' ? 'Edge' : 'Vertex';
                sessionStorage.setItem('annotationDrawKind', input.value);
                if (input.value === 'segment') {{
                    sessionStorage.setItem('annotationLineStyle', 'segment');
                    document.querySelectorAll('input[name="vertexLineStyle"]').forEach(styleInput => {{
                        styleInput.checked = styleInput.value === 'segment';
                    }});
                }}
                updateRayDirectionVisibility();
                if (targetMode !== toolMode) {{
                    dispatchAction('set_tool_mode', {{bridge_mode: targetMode}});
                }} else {{
                    updateRunButtonStates();
                }}
            }});
        }});
        document.querySelectorAll('input[name="globalMeasureKind"]').forEach(input => {{
            input.addEventListener('change', () => {{
                if (!input.checked) return;
                const targetModes = {{distance: 'Vertex', angle: 'Angle', area: 'Region'}};
                dispatchAction('set_measure_kind', {{
                    bridge_measure_kind: input.value,
                    bridge_mode: targetModes[input.value]
                }});
            }});
        }});
        document.querySelectorAll('input[name="globalRayDirection"]').forEach(input => {{
            input.addEventListener('change', () => {{
                if (!input.checked) return;
                sessionStorage.setItem('annotationDrawKind', 'ray');
                sessionStorage.setItem('annotationLineStyle', input.value);
                document.querySelectorAll('input[name="vertexLineStyle"]').forEach(styleInput => {{
                    styleInput.checked = styleInput.value === input.value;
                }});
                updateRunButtonStates();
            }});
        }});
        configureToolGrid();

        document.querySelectorAll('input[name="vertexLineStyle"], input[name="edgeSide"]').forEach(input => {{
            input.addEventListener('change', updateRunButtonStates);
        }});

        function stalePanels() {{
            document.getElementById('transientSelectionRow')?.remove();
            if (selectedVertexIds.length === 0 && selectedRegionIndices.length === 0) {{
                document.getElementById('selectionSection').classList.add('hidden');
            }}
            document.getElementById('placeholderText').classList.remove('hidden');
            document.getElementById('vertexPanel').classList.add('hidden');
            document.getElementById('anglePanel').classList.add('hidden');
            document.getElementById('edgePanel').classList.add('hidden');
            document.getElementById('regionPanel').classList.add('hidden');
            lockedV = null; lockedFace = null; lockedEdge = null;
        }}

        function showVertexPanel(v) {{
            document.getElementById('placeholderText').classList.add('hidden');
            document.getElementById('anglePanel').classList.add('hidden');
            document.getElementById('edgePanel').classList.add('hidden');
            document.getElementById('regionPanel').classList.add('hidden');
            document.getElementById('vertexPanel').classList.remove('hidden');

            if (selectedVertexIds.length >= 2) {{
                document.getElementById('normalForm').classList.add('hidden');
                document.getElementById('connectionForm').classList.remove('hidden');
                const btn = document.getElementById('confirmConnectBtn');
                btn.disabled = false;
                btn.style.opacity = 1.0;
                const measureBtn = document.getElementById('measureDistanceBtn');
                measureBtn.disabled = false;
                measureBtn.style.opacity = 1.0;
            }} else {{
                document.getElementById('normalForm').classList.remove('hidden');
                document.getElementById('connectionForm').classList.add('hidden');
            }}
        }}

        function showAnglePanel(v, face) {{
            document.getElementById('placeholderText').classList.add('hidden');
            document.getElementById('vertexPanel').classList.add('hidden');
            document.getElementById('edgePanel').classList.add('hidden');
            document.getElementById('regionPanel').classList.add('hidden');
            document.getElementById('anglePanel').classList.remove('hidden');
        }}

        function edgeMarkerLabel(e) {{
            const selectedEdgeIndex = selectedEdges.findIndex(edge =>
                (Number(edge.tail_id) === Number(e.tail_id) && Number(edge.head_id) === Number(e.head_id))
                || (Number(edge.tail_id) === Number(e.head_id) && Number(edge.head_id) === Number(e.tail_id))
            );
            return edgePreviewLabels[
                selectedEdgeIndex >= 0 ? selectedEdgeIndex : selectedEdges.length
            ] || 'e1';
        }}

        function edgeNaturalDescription(e) {{
            const boundedRegionNames = [];
            if (e.main_valid) boundedRegionNames.push(e.main_name);
            if (e.oppo_valid && !boundedRegionNames.includes(e.oppo_name)) {{
                boundedRegionNames.push(e.oppo_name);
            }}
            if (boundedRegionNames.length >= 2) {{
                return `edge between ${{boundedRegionNames[0]}} and ${{boundedRegionNames[1]}}`;
            }}
            if (boundedRegionNames.length === 1) {{
                return `frame edge of ${{boundedRegionNames[0]}}`;
            }}
            return 'selected edge';
        }}

        function edgeSelectionText(e) {{
            return `edge ${{edgeMarkerLabel(e)}} (${{edgeNaturalDescription(e)}})`;
        }}

        function showEdgePanel(e) {{
            document.getElementById('placeholderText').classList.add('hidden');
            document.getElementById('vertexPanel').classList.add('hidden');
            document.getElementById('anglePanel').classList.add('hidden');
            document.getElementById('regionPanel').classList.add('hidden');
            document.getElementById('edgePanel').classList.remove('hidden');
            if (!e) {{
                document.getElementById('edgeHiddenWarning').classList.add('hidden');
                document.getElementById('edgeActiveContent').classList.remove('hidden');
                document.getElementById('edgeSelectionBox').classList.add('hidden');
                document.getElementById('edgeMainChoice').style.display = 'none';
                document.getElementById('edgeOppoChoice').style.display = 'none';
                return;
            }}
            document.getElementById('edgeSelectionBox').classList.remove('hidden');
            if (e.is_hidden) {{
                document.getElementById('edgeHiddenWarning').classList.remove('hidden');
                document.getElementById('edgeActiveContent').classList.add('hidden');
            }} else {{
                document.getElementById('edgeHiddenWarning').classList.add('hidden');
                document.getElementById('edgeActiveContent').classList.remove('hidden');
                document.getElementById('edge_label_span').innerText = edgeSelectionText(e);
                const mainChoice = document.getElementById('edgeMainChoice');
                const oppoChoice = document.getElementById('edgeOppoChoice');
                document.getElementById('edgeMainLabel').innerText = "Edge of " + e.main_name;
                document.getElementById('edgeOppoLabel').innerText = "Edge of " + e.oppo_name;
                mainChoice.style.display = e.main_valid ? 'flex' : 'none';
                oppoChoice.style.display = e.oppo_valid ? 'flex' : 'none';
            }}
        }}

        function showRegionPanel(face) {{
            document.getElementById('placeholderText').classList.add('hidden');
            document.getElementById('vertexPanel').classList.add('hidden');
            document.getElementById('anglePanel').classList.add('hidden');
            document.getElementById('edgePanel').classList.add('hidden');
            document.getElementById('regionPanel').classList.remove('hidden');

            if (!face) {{
                document.getElementById('mergedFormationAlert').classList.add('hidden');
                document.getElementById('normalRegionBox').classList.toggle('hidden', Boolean(lastRunMessage));
                document.getElementById('region_label_span').innerText = 'No region selected';
                document.getElementById('commitRegionBtn').classList.remove('hidden');
                document.getElementById('commitUnionHighlightBtn').classList.add('hidden');
                document.getElementById('measureRegionBtn').classList.remove('hidden');
                document.getElementById('globalBufferBox').classList.toggle(
                    'hidden', selectedRegionIndices.length !== 2
                );
                return;
            }}

            const isObsolete = face.cache_idx in obsoleteFacesUnionInfo;
            const isInBuffer = selectedRegionIndices.includes(face.cache_idx);
            const bufferIsFull = selectedRegionIndices.length >= 2;

            if (isObsolete) {{
                document.getElementById('mergedFormationAlert').classList.remove('hidden');
                document.getElementById('normalRegionBox').classList.add('hidden');
                document.getElementById('commitRegionBtn').classList.add('hidden');
                document.getElementById('commitUnionHighlightBtn').classList.remove('hidden');
            }} else {{
                document.getElementById('mergedFormationAlert').classList.add('hidden');
                document.getElementById('normalRegionBox').classList.remove('hidden');
                document.getElementById('region_label_span').innerText = "Region " + face.display;
                document.getElementById('commitRegionBtn').classList.remove('hidden');
                document.getElementById('commitUnionHighlightBtn').classList.add('hidden');
            }}

            const addBtn = document.getElementById('addToBufferBtn');
            const removeBtn = document.getElementById('removeFromBufferBtn');
            const clearUnionBtn = document.getElementById('clearUnionBtn');
            const bufWarn = document.getElementById('bufferWarning');
            if (clearUnionBtn) {{
                clearUnionBtn.classList.toggle('hidden', !hasExistingUnion);
            }}

            document.getElementById('unionConstructionSection').classList.add('hidden');
            if (isInBuffer) {{
                addBtn.style.display = 'none';
                removeBtn.style.display = 'block';
                bufWarn.classList.remove('hidden');
                bufWarn.innerText = "Region " + face.letter + " is inside your union buffer.";
            }} else {{
                addBtn.style.display = 'block';
                removeBtn.style.display = 'none';
                bufWarn.classList.add('hidden');
                if (hasExistingUnion || bufferIsFull || isObsolete) {{
                    addBtn.disabled = true;
                    addBtn.style.opacity = 0.5;
                    if (hasExistingUnion) {{
                        bufWarn.classList.remove('hidden');
                        bufWarn.innerText = "An active union already exists.";
                    }} else if (bufferIsFull) {{
                        bufWarn.classList.remove('hidden');
                        bufWarn.innerText = "Buffer is full (max 2 regions).";
                    }}
                }} else {{
                    addBtn.disabled = false;
                    addBtn.style.opacity = 1.0;
                }}
            }}

            const globalBox = document.getElementById('globalBufferBox');
            if (selectedRegionIndices.length === 2) {{
                document.getElementById('commitRegionBtn').classList.add('hidden');
                document.getElementById('measureRegionBtn').classList.add('hidden');
                globalBox.classList.remove('hidden');
                document.getElementById('staged_letters_span').innerText = selectedRegionIndices.map(idx => {{
                    const selectedFace = facesData.find(f => Number(f.cache_idx) === Number(idx));
                    return selectedFace ? selectedFace.letter : '?';
                }}).join(', ');
                const execBtn = document.getElementById('execUnionBtn');
                const canExecute = !hasExistingUnion;
                execBtn.disabled = !canExecute;
                execBtn.style.opacity = canExecute ? 1.0 : 0.5;
            }} else {{
                document.getElementById('measureRegionBtn').classList.remove('hidden');
                globalBox.classList.add('hidden');
            }}
        }}

        function redraw() {{
            interCtx.clearRect(0, 0, {DISPLAY_SIDE}, {DISPLAY_SIDE});

            // Persistent live selections match compositional_survey.py exactly.
            for (const selectedIdx of selectedRegionIndices) {{
                const rawFace = facesData.find(item => Number(item.cache_idx) === Number(selectedIdx));
                const f = unionBoundaryFace(rawFace);
                if (!f || !f.vertices.length) continue;
                interCtx.beginPath();
                interCtx.moveTo(f.vertices[0].x, f.vertices[0].y);
                for (let i = 1; i < f.vertices.length; i++) interCtx.lineTo(f.vertices[i].x, f.vertices[i].y);
                interCtx.closePath();
                interCtx.fillStyle = 'rgba(150,150,150,0.745)';
                interCtx.fill();
                interCtx.strokeStyle = 'rgba(0,0,0,1)';
                interCtx.lineWidth = 4;
                interCtx.stroke();
            }}
            for (const selectedId of selectedVertexIds) {{
                const v = vertices.find(item => String(item.id) === String(selectedId));
                if (!v) continue;
                interCtx.beginPath();
                interCtx.arc(v.x, v.y, 15, 0, 2*Math.PI);
                interCtx.strokeStyle = 'rgba(0,255,204,1)';
                interCtx.lineWidth = 4;
                interCtx.stroke();
                const vertexLabel = selectedVertexLabels[String(selectedId)];
                if (vertexLabel) {{
                    interCtx.font = '600 15px -apple-system, BlinkMacSystemFont, sans-serif';
                    interCtx.lineWidth = 4;
                    interCtx.strokeStyle = 'white';
                    interCtx.strokeText(vertexLabel, v.x + 11, v.y - 18);
                    interCtx.fillStyle = 'rgb(0,0,255)';
                    interCtx.fillText(vertexLabel, v.x + 11, v.y - 18);
                }}
            }}

            // Angle and Edge selections remain visible when the user switches
            // to another Selection type, just like Vertex and Region.
            for (let angleIndex = 0; angleIndex < selectedAngles.length; angleIndex++) {{
                const persistentAngle = selectedAngles[angleIndex];
                const angleV = vertices.find(v => String(v.id) === String(persistentAngle.vertex_id));
                const angleF = unionBoundaryFace(
                    facesData.find(f => Number(f.cache_idx) === Number(persistentAngle.face_idx))
                );
                if (angleV && angleF) {{
                    const idx = angleF.vertices.findIndex(v => String(v.id) === String(angleV.id));
                    if (idx !== -1) {{
                        const n = angleF.vertices.length;
                        const prev = angleF.vertices[(idx - 1 + n) % n];
                        const next = angleF.vertices[(idx + 1) % n];
                        const arcSpec = interiorArcSpec(angleF, angleV, prev, next);
                        const sameVertexSlot = selectedAngles
                            .slice(0, angleIndex)
                            .filter(angle => String(angle.vertex_id) === String(persistentAngle.vertex_id))
                            .length;
                        const angleRadius = 19 + sameVertexSlot * 8;
                        interCtx.beginPath();
                        interCtx.arc(
                            angleV.x, angleV.y, angleRadius,
                            arcSpec.start, arcSpec.end, arcSpec.anticlockwise
                        );
                        interCtx.strokeStyle = 'rgba(203,32,107,1)';
                        interCtx.lineWidth = 3;
                        interCtx.stroke();
                        interCtx.font = '600 15px -apple-system, BlinkMacSystemFont, sans-serif';
                        interCtx.lineWidth = 4;
                        interCtx.strokeStyle = 'white';
                        const angleLabel = anglePreviewLabels[angleIndex];
                        const labelX = angleV.x + (angleRadius + 17) * Math.cos(arcSpec.mid);
                        const labelY = angleV.y + (angleRadius + 17) * Math.sin(arcSpec.mid);
                        interCtx.save();
                        interCtx.textAlign = 'center';
                        interCtx.textBaseline = 'middle';
                        interCtx.strokeText(angleLabel, labelX, labelY);
                        interCtx.fillStyle = 'rgba(203,32,107,1)';
                        interCtx.fillText(angleLabel, labelX, labelY);
                        interCtx.restore();
                    }}
                }}
            }}
            for (let edgeIndex = 0; edgeIndex < selectedEdges.length; edgeIndex++) {{
                const persistentSelectedEdge = selectedEdges[edgeIndex];
                const persistentEdge = edgesData.find(e =>
                    (Number(e.tail_id) === Number(persistentSelectedEdge.tail_id) && Number(e.head_id) === Number(persistentSelectedEdge.head_id)) ||
                    (Number(e.tail_id) === Number(persistentSelectedEdge.head_id) && Number(e.head_id) === Number(persistentSelectedEdge.tail_id))
                );
                if (persistentEdge) {{
                    const segs = persistentEdge.segments?.length
                        ? persistentEdge.segments
                        : [{{x1:persistentEdge.x1, y1:persistentEdge.y1, x2:persistentEdge.x2, y2:persistentEdge.y2}}];
                    for (const seg of segs) {{
                        interCtx.beginPath();
                        interCtx.moveTo(seg.x1, seg.y1);
                        interCtx.lineTo(seg.x2, seg.y2);
                        interCtx.strokeStyle = persistentEdge.is_hidden ? 'rgba(150,150,150,0.6)' : 'rgba(0,255,255,0.92)';
                        interCtx.lineWidth = 14;
                        interCtx.stroke();
                        if (!persistentEdge.is_hidden) {{
                            for (const point of [[seg.x1, seg.y1], [seg.x2, seg.y2]]) {{
                                interCtx.beginPath();
                                interCtx.arc(point[0], point[1], 7, 0, 2*Math.PI);
                                interCtx.fillStyle = 'rgba(0,255,255,0.92)';
                                interCtx.fill();
                            }}
                        }}
                    }}
                    if (segs.length) {{
                        const seg = segs[0];
                        const dx = seg.x2 - seg.x1;
                        const dy = seg.y2 - seg.y1;
                        const length = Math.max(1, Math.hypot(dx, dy));
                        let nx = -dy / length;
                        let ny = dx / length;
                        if (Math.abs(nx) >= Math.abs(ny)) {{
                            if (nx > 0) {{ nx = -nx; ny = -ny; }}
                        }} else if (ny > 0) {{
                            nx = -nx; ny = -ny;
                        }}
                        const x = (seg.x1 + seg.x2) / 2 + 30 * nx;
                        const y = (seg.y1 + seg.y2) / 2 + 30 * ny;
                        interCtx.font = '600 15px -apple-system, BlinkMacSystemFont, sans-serif';
                        interCtx.lineWidth = 4;
                        interCtx.strokeStyle = 'white';
                        const edgeLabel = edgePreviewLabels[edgeIndex];
                        interCtx.save();
                        interCtx.textAlign = 'center';
                        interCtx.textBaseline = 'middle';
                        interCtx.strokeText(edgeLabel, x, y);
                        interCtx.fillStyle = 'rgb(0,100,130)';
                        interCtx.fillText(edgeLabel, x, y);
                        interCtx.restore();
                    }}
                }}
            }}

            const renderLock = selectedElement !== null;
            const targetV = renderLock && selectedElement.type === 'Angle'
                ? selectedElement.data.v
                : (renderLock ? lockedV : hoverV);
            const targetFace = renderLock && selectedElement.type === 'Angle'
                ? selectedElement.data.f
                : (renderLock ? lockedFace : hoverFace);
            const targetEdge = renderLock && selectedElement.type === 'Edge'
                ? selectedElement.data
                : (renderLock ? lockedEdge : hoverEdge);
            const primaryColor = renderLock ? '#FF4B4B' : '#00FFCC';
            const strokeWidth = renderLock ? 5 : 4;

            if (toolMode === "Vertex" && targetV && !targetV.is_obsolete) {{
                interCtx.beginPath();
                interCtx.arc(targetV.x, targetV.y, 15, 0, 2*Math.PI);
                interCtx.strokeStyle = primaryColor;
                interCtx.lineWidth = strokeWidth;
                interCtx.stroke();

            }} else if (toolMode === "Angle" && targetV && targetFace) {{
                const fverts = targetFace.vertices;
                const idx = fverts.findIndex(fv => fv.id === targetV.id);
                if (idx !== -1) {{
                    const n = fverts.length;
                    const prev = fverts[(idx - 1 + n) % n];
                    const next = fverts[(idx + 1) % n];
                    const arcSpec = interiorArcSpec(targetFace, targetV, prev, next);
                    const selectedAngleIndex = selectedAngles.findIndex(angle =>
                        String(angle.vertex_id) === String(targetV.id)
                        && Number(angle.face_idx) === Number(targetFace.cache_idx)
                    );
                    const priorAngles = selectedAngleIndex >= 0
                        ? selectedAngles.slice(0, selectedAngleIndex)
                        : selectedAngles;
                    const sameVertexSlot = priorAngles.filter(angle =>
                        String(angle.vertex_id) === String(targetV.id)
                    ).length;
                    const activeAngleRadius = (renderLock ? 19 : 22) + sameVertexSlot * 8;

                    if (!renderLock) {{
                        interCtx.beginPath();
                        interCtx.moveTo(targetV.x, targetV.y);
                        interCtx.lineTo(prev.x, prev.y);
                        interCtx.strokeStyle = 'rgba(255,160,0,0.7)';
                        interCtx.lineWidth = strokeWidth;
                        interCtx.stroke();
                        interCtx.beginPath();
                        interCtx.moveTo(targetV.x, targetV.y);
                        interCtx.lineTo(next.x, next.y);
                        interCtx.stroke();
                    }}

                    interCtx.beginPath();
                    interCtx.arc(
                        targetV.x, targetV.y, activeAngleRadius,
                        arcSpec.start, arcSpec.end, arcSpec.anticlockwise
                    );
                    interCtx.strokeStyle = renderLock ? 'rgba(203,32,107,1)' : 'rgba(255,100,0,0.9)';
                    interCtx.lineWidth = 3;
                    interCtx.stroke();
                    if (renderLock) {{
                        const activeAngleLabel = anglePreviewLabels[
                            selectedAngleIndex >= 0 ? selectedAngleIndex : selectedAngles.length
                        ];
                        interCtx.font = '600 15px -apple-system, BlinkMacSystemFont, sans-serif';
                        interCtx.lineWidth = 4;
                        interCtx.strokeStyle = 'white';
                        const activeLabelX = targetV.x + (activeAngleRadius + 17) * Math.cos(arcSpec.mid);
                        const activeLabelY = targetV.y + (activeAngleRadius + 17) * Math.sin(arcSpec.mid);
                        interCtx.save();
                        interCtx.textAlign = 'center';
                        interCtx.textBaseline = 'middle';
                        interCtx.strokeText(activeAngleLabel, activeLabelX, activeLabelY);
                        interCtx.fillStyle = 'rgba(203,32,107,1)';
                        interCtx.fillText(activeAngleLabel, activeLabelX, activeLabelY);
                        interCtx.restore();
                    }}
                }}

            }}  else if (toolMode === "Edge" && targetEdge) {{
                    const segs = (targetEdge.segments && targetEdge.segments.length > 0)
                        ? targetEdge.segments
                        : [{{ x1: targetEdge.x1, y1: targetEdge.y1, x2: targetEdge.x2, y2: targetEdge.y2 }}];
                    const edgeColor = targetEdge.is_hidden
                        ? 'rgba(150,150,150,0.6)'
                        : (renderLock ? 'rgba(0,255,255,0.92)' : 'rgba(255,152,0,0.9)');
                    const edgeWidth = renderLock ? 14 : 6;
                    for (let seg of segs) {{
                        interCtx.beginPath();
                        interCtx.moveTo(seg.x1, seg.y1);
                        interCtx.lineTo(seg.x2, seg.y2);
                        interCtx.strokeStyle = edgeColor;
                        interCtx.lineWidth = edgeWidth;
                        interCtx.stroke();
                        if (renderLock && !targetEdge.is_hidden) {{
                            for (const point of [[seg.x1, seg.y1], [seg.x2, seg.y2]]) {{
                                interCtx.beginPath();
                                interCtx.arc(point[0], point[1], 7, 0, 2*Math.PI);
                                interCtx.fillStyle = 'rgba(0,255,255,0.92)';
                                interCtx.fill();
                            }}
                        }}
                    }}
                    if (renderLock && segs.length > 0) {{
                        const selectedEdgeIndex = selectedEdges.findIndex(edge =>
                            (Number(edge.tail_id) === Number(targetEdge.tail_id) && Number(edge.head_id) === Number(targetEdge.head_id))
                            || (Number(edge.tail_id) === Number(targetEdge.head_id) && Number(edge.head_id) === Number(targetEdge.tail_id))
                        );
                        const activeEdgeLabel = edgePreviewLabels[
                            selectedEdgeIndex >= 0 ? selectedEdgeIndex : selectedEdges.length
                        ];
                        const labelSeg = segs[0];
                        const dx = labelSeg.x2 - labelSeg.x1;
                        const dy = labelSeg.y2 - labelSeg.y1;
                        const length = Math.max(1, Math.hypot(dx, dy));
                        let nx = -dy / length;
                        let ny = dx / length;
                        if (Math.abs(nx) >= Math.abs(ny)) {{
                            if (nx > 0) {{ nx = -nx; ny = -ny; }}
                        }} else if (ny > 0) {{
                            nx = -nx; ny = -ny;
                        }}
                        const labelX = (labelSeg.x1 + labelSeg.x2) / 2 + 30 * nx;
                        const labelY = (labelSeg.y1 + labelSeg.y2) / 2 + 30 * ny;
                        interCtx.font = '600 15px -apple-system, BlinkMacSystemFont, sans-serif';
                        interCtx.lineWidth = 4;
                        interCtx.strokeStyle = 'white';
                        interCtx.save();
                        interCtx.textAlign = 'center';
                        interCtx.textBaseline = 'middle';
                        interCtx.strokeText(activeEdgeLabel, labelX, labelY);
                        interCtx.fillStyle = 'rgb(0,100,130)';
                        interCtx.fillText(activeEdgeLabel, labelX, labelY);
                        interCtx.restore();
                    }}


            }} else if (toolMode === "Region" && targetFace) {{
                let facesToDraw = [targetFace];
                if (targetFace.is_obsolete && targetFace.union_partner_idx !== null) {{
                    const partner = facesData.find(f => f.cache_idx === targetFace.union_partner_idx);
                    if (partner) facesToDraw.push(partner);
                }}

                const fillColor = 'rgba(150,150,150,0.45)';
                const strokeColor = 'rgba(0,0,0,1.0)';

                for (let f of facesToDraw) {{
                    const fverts = f.vertices;
                    if (fverts.length > 0) {{
                        interCtx.beginPath();
                        interCtx.moveTo(fverts[0].x, fverts[0].y);
                        for (let i = 1; i < fverts.length; i++) {{
                            interCtx.lineTo(fverts[i].x, fverts[i].y);
                        }}
                        interCtx.closePath();
                        interCtx.fillStyle = fillColor;
                        interCtx.fill();
                    }}
                }}

                if (renderLock && facesToDraw.length === 1) {{
                    const fverts = facesToDraw[0].vertices;
                    if (fverts.length > 0) {{
                        interCtx.beginPath();
                        interCtx.moveTo(fverts[0].x, fverts[0].y);
                        for (let i = 1; i < fverts.length; i++) {{
                            interCtx.lineTo(fverts[i].x, fverts[i].y);
                        }}
                        interCtx.closePath();
                        interCtx.strokeStyle = strokeColor;
                        interCtx.lineWidth = 4;
                        interCtx.stroke();
                    }}
                }} else if (renderLock) {{
                    const faceAVerts = new Set(facesToDraw[0].vertices.map(v => v.id));
                    const faceBVerts = new Set(facesToDraw[1].vertices.map(v => v.id));

                    for (let f of facesToDraw) {{
                        const fverts = f.vertices;
                        const n = fverts.length;
                        for (let i = 0; i < n; i++) {{
                            const v1 = fverts[i];
                            const v2 = fverts[(i + 1) % n];
                            const isShared = faceAVerts.has(v1.id) && faceAVerts.has(v2.id)
                                          && faceBVerts.has(v1.id) && faceBVerts.has(v2.id);
                            if (isShared) continue;

                            interCtx.beginPath();
                            interCtx.moveTo(v1.x, v1.y);
                            interCtx.lineTo(v2.x, v2.y);
                            interCtx.strokeStyle = strokeColor;
                            interCtx.lineWidth = 4;
                            interCtx.stroke();
                        }}
                    }}
                }}
            }}
        }}

        function dispatchAction(actionName, extraParams) {{
            if (!lockedV && !['set_tool_mode','set_measure_kind','practice_select_geom','continue_selection_review','select_angle','measure_angle','select_edge','remove_selected_angle','remove_selected_edge','select_region','remove_selected_region','cancel_connection','commit_edge','extend_edge','measure_edge','commit_region','measure_region','add_to_buffer','remove_from_buffer','clear_buffer','clear_union','execute_union','commit_union_highlight'].includes(actionName)) {{
                alert("Please click/select a vertex first!");
                return;
            }}
            const targetId = lockedV ? lockedV.id : "none";
            const payload = {{
                action_id: actionName + "_" + Date.now() + "_" + Math.random().toString(36).slice(2),
                bridge_act: actionName,
                bridge_tgt: String(targetId),
                participant_id: "{PARTICIPANT_ID}",
                client_timestamp: new Date().toISOString(),
                client_elapsed_ms: String(Date.now() - pageLoadClientMs),
                bridge_click_x: interCanvas.dataset.lastClickX || "",
                bridge_click_y: interCanvas.dataset.lastClickY || ""
            }};
            if (extraParams) {{
                for (const [k, v] of Object.entries(extraParams)) {{
                    payload[k] = String(v);
                }}
            }}
            StreamlitBridge.value(payload);
        }}

        // Keep Angle → Measure independent of the later listener-registration
        // block.  Some Streamlit/browser combinations can interrupt that block
        // after the component is rendered, leaving a visibly enabled RUN button
        // with no click handler.
        function runMeasureAngle() {{
            if (selectedAngles.length !== 1 || totalSelectedInputs() !== 1) {{
                alert('Select exactly one angle and remove any extra selections before clicking RUN.');
                return;
            }}
            let activeAngle = selectedAngleData();
            if ((!activeAngle?.v || !activeAngle?.f)
                    && selectedAngle?.vertex_id != null
                    && selectedAngle?.face_idx != null) {{
                const v = vertices.find(candidate =>
                    String(candidate.id) === String(selectedAngle.vertex_id));
                const rawFace = facesData.find(candidate =>
                    Number(candidate.cache_idx) === Number(selectedAngle.face_idx));
                const f = unionBoundaryFace(rawFace);
                if (v && f) activeAngle = {{v, f}};
            }}
            if (!activeAngle?.v || !activeAngle?.f) {{
                alert('Select one angle before clicking RUN.');
                return;
            }}
            dispatchAction('measure_angle', {{
                bridge_tgt: activeAngle.v.id,
                bridge_face: activeAngle.f.cache_idx
            }});
        }}

        document.querySelectorAll('input[name="toolMode"]').forEach((input) => {{
            input.addEventListener('change', (event) => {{
                if (event.target.checked && event.target.value !== toolMode) {{
                    dispatchAction('set_tool_mode', {{bridge_mode: event.target.value}});
                }}
            }});
        }});

        document.getElementById('submitBtn')?.addEventListener('click', () => dispatchAction('commit_vertex'));
        document.getElementById('runVertexLineBtn')?.addEventListener('click', () => {{
            const style = document.querySelector('input[name="vertexLineStyle"]:checked')?.value;
            if (style === 'segment') {{
                if (selectedVertexIds.length === 2) dispatchAction('confirm_connection');
                else alert('Select two vertices for a segment.');
            }} else if (['up', 'down', 'left', 'right'].includes(style)) {{
                dispatchAction('commit_ray', {{ bridge_direction: style }});
            }}
            else alert('Choose a line style.');
        }});
        document.getElementById('measureDistanceSingleBtn')?.addEventListener('click', () => {{
            if (selectedVertexIds.length === 2) dispatchAction('measure_distance');
            else alert('Select two vertices to measure distance.');
        }});
        document.getElementById('confirmConnectBtn')?.addEventListener('click', () => dispatchAction('confirm_connection'));
        document.getElementById('measureDistanceBtn')?.addEventListener('click', () => dispatchAction('measure_distance'));
        document.getElementById('cancelConnectBtn')?.addEventListener('click', () => dispatchAction('cancel_connection'));

        document.getElementById('commitAngleBtn')?.addEventListener('click', () => {{
            if (selectedAngles.length !== 1 || totalSelectedInputs() !== 1) return;
            const activeAngle = selectedAngleData();
            if (!activeAngle?.v || !activeAngle?.f) return;
            dispatchAction('commit_angle', {{
                bridge_tgt: activeAngle.v.id,
                bridge_face: activeAngle.f.cache_idx
            }});
        }});
        document.getElementById('edgeHighlightRun')?.addEventListener('click', () => {{
            if (selectedEdges.length !== 1 || totalSelectedInputs() !== 1) return;
            const activeEdge = selectedEdgeData();
            if (!activeEdge) return;
            const side = document.querySelector('input[name="edgeSide"]:checked')?.value;
            if (!side) {{ alert("Choose an adjacent region first."); return; }}
            dispatchAction('commit_edge', {{ bridge_edge_idx: activeEdge.edge_idx, bridge_side: side, bridge_tail: activeEdge.tail_id, bridge_head: activeEdge.head_id }});
        }});
        document.getElementById('extendEdgeBtn')?.addEventListener('click', () => {{
            if (selectedEdges.length !== 1 || totalSelectedInputs() !== 1) return;
            const activeEdge = selectedEdgeData();
            if (!activeEdge) return;
            dispatchAction('extend_edge', {{
                bridge_edge_idx: activeEdge.edge_idx,
                bridge_tail: activeEdge.tail_id,
                bridge_head: activeEdge.head_id,
                bridge_tail_x: activeEdge.tail_x,
                bridge_tail_y: activeEdge.tail_y,
                bridge_head_x: activeEdge.head_x,
                bridge_head_y: activeEdge.head_y
            }});
        }});
        document.getElementById('commitRegionBtn')?.addEventListener('click', () => {{
            if (!lockedFace) return;
            dispatchAction('commit_region', {{ bridge_face: lockedFace.cache_idx }});
        }});
        document.getElementById('commitUnionHighlightBtn')?.addEventListener('click', () => {{
            if (!lockedFace) return;
            dispatchAction('commit_union_highlight', {{ bridge_face: lockedFace.cache_idx }});
        }});
        document.getElementById('measureRegionBtn')?.addEventListener('click', () => {{
            if (selectedRegionIndices.length === 1 && totalSelectedInputs() === 1) {{
                dispatchAction('measure_region', {{ bridge_face: selectedRegionIndices[0] }});
            }}
        }});
        document.getElementById('addToBufferBtn')?.addEventListener('click', () => {{
            if (!lockedFace) return;
            dispatchAction('add_to_buffer', {{ bridge_face: lockedFace.cache_idx }});
        }});
        document.getElementById('removeFromBufferBtn')?.addEventListener('click', () => {{
            if (!lockedFace) return;
            dispatchAction('remove_from_buffer', {{ bridge_face: lockedFace.cache_idx }});
        }});
        document.getElementById('clearBufferBtn')?.addEventListener('click', () => dispatchAction('clear_buffer'));
        document.getElementById('clearUnionBtn')?.addEventListener('click', () => dispatchAction('clear_union'));
        document.getElementById('execUnionBtn')?.addEventListener('click', () => dispatchAction('execute_union'));
        document.getElementById('continueSelectionReview')?.addEventListener('click', () => {{
            dispatchAction('continue_selection_review');
        }});
        document.querySelectorAll('.selection-remove').forEach((button) => {{
            button.addEventListener('click', () => {{
                if (button.dataset.kind === 'vertex') {{
                    const selectedVertex = vertices.find(v => String(v.id) === String(button.dataset.id));
                    if (selectedVertex) lockedV = selectedVertex;
                    dispatchAction('remove_selected_vertex');
                }} else if (button.dataset.kind === 'region') {{
                    dispatchAction('remove_selected_region', {{ bridge_face: button.dataset.id }});
                }} else if (button.dataset.kind === 'angle') {{
                    dispatchAction('remove_selected_angle', {{
                        bridge_selection_index: button.dataset.id
                    }});
                }} else if (button.dataset.kind === 'edge') {{
                    dispatchAction('remove_selected_edge', {{
                        bridge_selection_index: button.dataset.id
                    }});
                }}
            }});
        }});

        redraw();
        StreamlitBridge.ready();
        function reportComponentHeight() {{
            StreamlitBridge.height(Math.max(
                {component_min_height},
                document.documentElement.scrollHeight + 8,
                document.body.scrollHeight + 8
            ));
        }}
        reportComponentHeight();
        requestAnimationFrame(reportComponentHeight);
        window.addEventListener('load', reportComponentHeight);
        setTimeout(reportComponentHeight, 150);
    </script>
</body>
</html>
"""

if show_drawing_pad:
    _drawing_pad = drawing_pad_component(html_code)
    render_key_parts = [
        PARTICIPANT_ID,
        str(data.get("phase", "")),
        str(data.get("demo_step", "")),
        str(data.get("current_trial_index", "")),
        str(data.get("current_question", {}).get("question_id", "")),
        str(data.get("current_question", {}).get("seed", "")),
        str(action_count),
        str(tool_mode),
        str(measure_kind),
        str(has_start_point),
        str(start_point_id),
        "_".join(selected_vertex_ids),
        "_".join(str(value) for value in selected_region_indices),
        json.dumps(selected_angles, sort_keys=True),
        json.dumps(selected_edges, sort_keys=True),
        "_".join(buffer_letters),
        str(has_existing_union),
    ]
    component_key = "drawing_pad_" + str(abs(hash("|".join(render_key_parts))))
    with main_work_col:
        component_action = _drawing_pad(default=None, key=component_key)
    if isinstance(component_action, dict) and component_action.get("bridge_act"):
        action_id = component_action.get("action_id")
        if action_id and st.session_state.get("_last_component_action_id") != action_id:
            st.session_state["_last_component_action_id"] = action_id
            if component_action.get("bridge_act") == "measure_angle":
                angle_vertex_id = component_action.get("bridge_tgt", "none")
                angle_face_idx = component_action.get("bridge_face", "-1")
                target_v = find_vertex_by_id(sess.res_map, angle_vertex_id)
                target_face = find_face_by_cache_idx(sess.res_map, angle_face_idx)
                if target_face and target_v:
                    degrees, region_label = measured_angle_degrees(sess, target_face, target_v)
                    if degrees is not None:
                        result = {
                            "kind": "angle",
                            "label": f"Angle in {region_label}",
                            "degrees": round(degrees, 1),
                            "vertex_id": str(angle_vertex_id),
                        }
                        set_last_measurement(data, result)
                        log_action(data, "measure_angle", result)
                        data["selected_angle"] = None
                        data["selected_angles"] = []
                        save_session(data)
            else:
                next_query_params = {
                    "participant_id": PARTICIPANT_ID,
                    "survey_instance": SURVEY_INSTANCE_ID,
                }
                next_query_params.update({
                    key: str(value)
                    for key, value in component_action.items()
                })
                st.query_params.from_dict(next_query_params)
                st.rerun()

    with main_info_col:
        render_output_panel(data)
