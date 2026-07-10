import os
import html
import math
import base64
import tempfile
import json
import pickle
import random
import re
import time
import uuid
from io import BytesIO
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageDraw

import Graph
import BuildRandomMap
import DrawGraph
import map_helpers
import tools_human as T
from sel_types import AngleSel, EdgeSel

st.set_page_config(layout="wide")
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 3.5rem;
        padding-bottom: 2.5rem;
    }
    div[data-testid="stVerticalBlock"] {
        gap: 0.65rem;
    }
    div[data-testid="stForm"] {
        padding: 0.65rem 0.85rem 0.5rem;
    }
    .st-key-diagram_panel {
        transform: translateY(-7px);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

components.html(
    """
    <script>
    (function () {
      try {
        const parentWindow = window.parent;
        if (!parentWindow || parentWindow.__geometrySurveyBackGuardInstalled) return;
        parentWindow.__geometrySurveyBackGuardInstalled = true;
        parentWindow.history.pushState({geometrySurveyGuard: true}, "", parentWindow.location.href);
        parentWindow.addEventListener("popstate", function () {
          parentWindow.history.pushState({geometrySurveyGuard: true}, "", parentWindow.location.href);
        });
      } catch (err) {
        // If the browser blocks parent history access, continue without the guard.
      }
    })();
    </script>
    """,
    height=0,
)
# st.title("Geologic Region Explorer")

DISPLAY_SIDE = 460          # map render size; clicks are mapped back through this
MATH_SCALE = 800.0
DEFAULT_PARTICIPANT_ID = "local_demo"
SURVEY_VERSION = "compositional_questions_v1"
SURVEY_QUESTION_COUNT = 24
RESULTS_DIR = os.path.join(os.getcwd(), "survey_results")

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

DEFINITIONS_TEXT = """
**Vertex:** a location where two or more edges meet.

**Edge:** a line segment that forms part of a region boundary.

**Region:** one enclosed area of the diagram.

**Interior angle:** the angle inside a region at a vertex, formed by the two edges that meet there.

**Outside of the frame:** the area outside the diagram frame. When a question asks you to treat it as a region, label it as "Outside of the frame".

**Clockwise:** movement around a circle in the top, right, bottom, left direction.

**Counterclockwise:** movement around a circle in the top, left, bottom, right direction.

**Union:** a combination of two neighboring regions treated as one larger region.
"""

PRACTICE_CORE_DEFINITIONS_TEXT = """
**Vertex:** a point where two or more edges meet.

**Edge:** a line segment that forms part of a region boundary.

**Region:** one enclosed area of the diagram.

**Interior angle:** the angle inside a region at a vertex, formed by the two edges that meet there.
"""

PRACTICE_TOOL_GUIDE_TEXT = """
Now practice using a tool. We will use **Find Vertex** as an example.

Some questions may ask you to find a vertex with a particular property, such as the rightmost vertex of a region.

Try this: select **Region A**, choose **rightmost** under Find Vertex settings, then click **RUN**. The tool will label the vertex it finds.
"""

PRACTICE_TOOL_AFTER_SUCCESS_TEXT = """
Good. Find Vertex can also label meeting points of regions.

Next, click **Clear all**, select **Region A**, **Region D**, and **Region E**, keep **Is the meeting vertex on the frame?** as **No**, then click **RUN**.
"""

PRACTICE_NEIGHBORS_GUIDE_TEXT = """
Good. Now practice one more tool: **Neighbors**.

Some questions ask which regions are next to a selected object. Try this: click **Clear all**, choose **Neighbors**, select **Region A**, keep **Neighbor type** as **Share an edge**, then click **RUN**.
"""

PRACTICE_MERGE_GUIDE_TEXT = """
Very good. Region A shares an edge with Regions B, D, and E, which you can see in the **Output** section on the right.

Now try one more tool: **Merge**. Click **Clear all**, choose **Merge**, select **Region A** and **Region E**, then click **RUN**.
"""

PRACTICE_TOOL_FINAL_TEXT = """
Very good. You have now tried Find Vertex, Neighbors, and Merge.

Feel free to play with these tools as long as you would like before moving on to the official survey. You can measure a region’s area, sort different angles, draw a line to see which regions it intersects, and more.

Read the instructions under the diagram to figure out what each tool is used for.
"""

TUTORIAL_TEXT = """
This short tutorial uses a circular practice diagram, not a survey question.
Try selecting items and running a practice tool, then start the survey when you are ready.
"""

def _arc_points(cx, cy, radius, start_deg, end_deg, steps=18):
    return [
        (
            cx + radius * math.cos(math.radians(deg)),
            cy + radius * math.sin(math.radians(deg)),
        )
        for deg in [
            start_deg + (end_deg - start_deg) * i / steps
            for i in range(steps + 1)
        ]
    ]

def tutorial_diagram_data(side=360):
    cx, cy, radius = side / 2, side / 2, 118
    sectors = [
        ("W", -90, 0, "#f9c6d3", (224, 112)),
        ("X", 0, 90, "#f7d36b", (225, 237)),
        ("Y", 90, 180, "#a7d8f0", (135, 237)),
        ("Z", 180, 270, "#bde6b2", (135, 112)),
    ]
    img = Image.new("RGB", (side, side), "white")
    draw = ImageDraw.Draw(img)
    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
    regions = []
    for label, start, end, color, text_xy in sectors:
        draw.pieslice(bbox, start=start, end=end, fill=color, outline="#222222", width=3)
        polygon = [(cx, cy)] + _arc_points(cx, cy, radius, start, end) + [(cx, cy)]
        regions.append({"label": label, "pts": polygon})
        draw.text(text_xy, label, fill="#222222", anchor="mm")
    draw.ellipse(bbox, outline="#222222", width=3)
    for px, py in [(cx, cy), (cx, cy - radius), (cx + radius, cy), (cx, cy + radius), (cx - radius, cy)]:
        draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill="#111111")
    buf = BytesIO()
    img.save(buf, format="PNG")
    shapes = {
        "regions": regions,
        "edges": [],
        "vertices": [[cx, cy], [cx, cy - radius], [cx + radius, cy], [cx, cy + radius], [cx - radius, cy]],
        "angles": [],
    }
    return base64.b64encode(buf.getvalue()).decode(), shapes

def tutorial_region_from_click(coords, side=360):
    if not coords:
        return None
    cx = cy = side / 2
    dx, dy = coords["x"] - cx, coords["y"] - cy
    if math.hypot(dx, dy) > 118:
        return None
    angle = math.degrees(math.atan2(dy, dx))
    if -90 <= angle < 0:
        return "W"
    if 0 <= angle < 90:
        return "X"
    if 90 <= angle <= 180:
        return "Y"
    return "Z"

def tutorial_neighbors(label):
    return {
        "W": ["X", "Z"],
        "X": ["W", "Y"],
        "Y": ["X", "Z"],
        "Z": ["W", "Y"],
    }.get(label, [])

def tutorial_selection_text():
    items = st.session_state.setdefault("tutorial_selection", [])
    return ", ".join(items) if items else "(nothing selected yet)"

def render_tutorial_screen():
    st.session_state.setdefault("tutorial_selection", [])
    st.session_state.setdefault("tutorial_output", "")
    st.session_state.setdefault("tutorial_last_click", None)
    st.markdown(
        """
        <style>
        .tutorial-card {
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 0.85rem 1rem;
            background: #ffffff;
            min-height: 128px;
        }
        .tutorial-card h4 {
            margin: 0 0 0.35rem 0;
            font-size: 1.02rem;
        }
        .tutorial-card p, .tutorial-card li {
            font-size: 0.94rem;
            line-height: 1.45;
            color: #374151;
        }
        .tutorial-example {
            background: #f3f4f6;
            border-left: 3px solid #9ca3af;
            padding: 0.35rem 0.55rem;
            border-radius: 0 0.35rem 0.35rem 0;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            color: #111827;
            display: inline-block;
            margin-top: 0.2rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("Tool Tutorial")
    st.info(TUTORIAL_TEXT)

    left, right = st.columns([3, 2], gap="large")
    with left:
        img_b64, shapes = tutorial_diagram_data()
        coords = geo_canvas(
            img_b64,
            shapes,
            360,
            select_type="region",
            key="tutorial_geo_canvas",
        )
        if coords is not None and coords != st.session_state.tutorial_last_click:
            st.session_state.tutorial_last_click = coords
            label = tutorial_region_from_click(coords)
            if label:
                selection = st.session_state.tutorial_selection
                if label not in selection:
                    selection.append(label)
                st.session_state.tutorial_output = ""
                st.rerun()
    with right:
        st.markdown(
            """
            <div class="tutorial-card">
              <h4>1. Click the diagram</h4>
              <p>Try clicking one or two colored regions in the circular diagram.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("**Selection**")
        st.code(tutorial_selection_text())
        tool_cols = st.columns(2)
        if tool_cols[0].button("Neighbors", use_container_width=True):
            selection = st.session_state.tutorial_selection
            if selection:
                st.session_state.tutorial_output = ", ".join(tutorial_neighbors(selection[-1]))
            else:
                st.session_state.tutorial_output = "Select a region first."
            st.rerun()
        if tool_cols[1].button("Clear", use_container_width=True):
            st.session_state.tutorial_selection = []
            st.session_state.tutorial_output = ""
            st.rerun()
        if st.button("Sort selected labels", use_container_width=True):
            selection = st.session_state.tutorial_selection
            st.session_state.tutorial_output = (
                ", ".join(sorted(selection)) if selection else "Select two or more regions first."
            )
            st.rerun()
        st.markdown("**Output**")
        st.code(st.session_state.tutorial_output or "(results will appear here)")
        st.markdown(
            """
            <div class="tutorial-card">
              <h4>2. Copy the result format</h4>
              <p>Tool outputs use the same style as the answer box: comma-separated labels such as
              <span class="tutorial-example">W, X</span>.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.expander("Quick reminders", expanded=False):
        st.markdown(
            """
            - The final answer must be typed in the answer box.
            - Use labels, not full sentences, unless the question says otherwise.
            - If the question asks for an order, keep that order exactly.
            - If there is no matching answer, type `None`.
            """
        )

    start_col, note_col = st.columns([1, 3], vertical_alignment="center")
    with start_col:
        if st.button("Start Survey", type="primary", use_container_width=True):
            st.session_state.tutorial_completed = True
            st.query_params["tutorial_done"] = "1"
            st.session_state.survey_started_at = time.time()
            st.rerun()
    with note_col:
        st.caption("You can reopen definitions and tool help during the survey from the Help panel.")

FALLBACK_QUESTION_BANK = [
    {
        "question_id": "q001_total_regions",
        "seed": 35,
        "num_regions": 8,
        "question_text": "How many regions are there in the diagram in total?",
        "answer": "",
        "answer_type": "fill_in_the_blank",
        "answer_placeholder": "Enter a number",
    },
    {
        "question_id": "q002_regions_bordering_b",
        "seed": 73,
        "num_regions": 8,
        "question_text": (
            "Which regions border region B along an edge? "
            "Bordering along an edge is not the same as bordering along a vertex."
        ),
        "answer": "",
        "answer_type": "fill_in_the_blank",
        "answer_placeholder": "Example: A, C, F",
    },
    {
        "question_id": "q003_line_path",
        "seed": 42,
        "num_regions": 8,
        "question_text": "Use the tools to solve the current geometry question.",
        "answer": "",
        "answer_type": "fill_in_the_blank",
        "answer_placeholder": "Enter your answer",
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
    "is_attention_check": True,
}

PRACTICE_QUESTION = {
    "question_id": "__practice__",
    "pair_id": "practice",
    "seed": 8675309,
    "num_regions": 5,
    "diagram_complexity": "practice",
    "question_text": (
        "Practice: try the survey pad below. Select a region, edge, vertex, or angle "
        "in the diagram, run any tool, and type any short response in the answer box."
    ),
    "answer": "",
    "answer_type": "fill_in_the_blank",
    "answer_placeholder": "Example: A or A, B",
    "is_practice": True,
}

def add_attention_check(questions):
    # Reposition an attention check saved by an older session as well as
    # inserting it for a new session.  This guarantees it is never left at
    # the old second-question position.
    questions = [q for q in questions if not q.get("is_attention_check")]
    insert_index = len(questions) // 2
    questions.insert(insert_index, dict(ATTENTION_CHECK_QUESTION))
    return questions

def _safe_id(value):
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(value))
    return safe[:80] or DEFAULT_PARTICIPANT_ID

def get_participant_id():
    if st.session_state.get("participant_id"):
        return st.session_state["participant_id"]
    raw_id = (
        st.query_params.get("participant_id")
        or st.query_params.get("pid")
        or st.query_params.get("survey_instance")
    )
    if not raw_id:
        raw_id = f"participant_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        # Put the generated identity in the address bar. A hard refresh then
        # creates a new Streamlit session but keeps the same participant.
        st.query_params["pid"] = raw_id
    participant_id = _safe_id(raw_id)
    st.session_state["participant_id"] = participant_id
    return participant_id

def participant_result_path(participant_id):
    return os.path.join(
        RESULTS_DIR,
        f"compositional_survey_{_safe_id(participant_id)}.json",
    )

def load_saved_survey(participant_id):
    """Load this participant's saved question order and confirmed progress."""
    path = participant_result_path(participant_id)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    if _safe_id(payload.get("participant_id", "")) != participant_id:
        return {}
    if payload.get("survey_version") != SURVEY_VERSION:
        return {}
    return payload

def find_dataset_path():
    explicit_path = st.query_params.get("dataset_path") or os.environ.get("GEOMETRY_SURVEY_DATASET")
    if explicit_path and os.path.exists(explicit_path):
        return explicit_path
    candidates = []
    for root, _, files in os.walk(os.getcwd()):
        for filename in ("dataset_24_balanced.json", "dataset_25_balanced.json"):
            if filename in files:
                candidates.append(os.path.join(root, filename))
    return sorted(candidates)[-1] if candidates else ""

def normalize_dataset_item(item, item_index):
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
    }

def load_question_bank(participant_id):
    dataset_path = find_dataset_path()
    if not dataset_path:
        return add_attention_check(FALLBACK_QUESTION_BANK), ""
    try:
        with open(dataset_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return add_attention_check(FALLBACK_QUESTION_BANK), ""
    raw_items = payload.get("items", payload if isinstance(payload, list) else [])
    normalized = [
        normalize_dataset_item(item, idx)
        for idx, item in enumerate(raw_items)
    ]
    normalized = [
        item for item in normalized
        if item.get("question_text") and item.get("seed") is not None
    ]
    if not normalized:
        return add_attention_check(FALLBACK_QUESTION_BANK), dataset_path
    sampler = random.Random(participant_id)
    sampler.shuffle(normalized)
    selected = normalized[: min(SURVEY_QUESTION_COUNT, len(normalized))]
    return add_attention_check(selected), dataset_path

def _answer_matches_choices(answer, choices):
    answer_norm = str(answer).strip().lower()
    return bool(answer_norm) and answer_norm in {
        str(choice).strip().lower()
        for choice in choices
    }

def get_two_choice_options(question):
    question_lower = question.get("question_text", "").lower()
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
    if "clockwise or counterclockwise" in question_lower or "counterclockwise or clockwise" in question_lower:
        return ["Clockwise", "Counterclockwise"]
    if "above or below" in question_lower or "below or above" in question_lower:
        return ["Above", "Below"]
    return None

def normalized_answer_type(question):
    return "two_choice" if get_two_choice_options(question) else "fill_in_the_blank"


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

PARTICIPANT_ID = get_participant_id()
SAVED_SURVEY = load_saved_survey(PARTICIPANT_ID)
if "question_bank" not in st.session_state or "dataset_path" not in st.session_state:
    saved_questions = SAVED_SURVEY.get("questions")
    if isinstance(saved_questions, list) and saved_questions:
        st.session_state.question_bank = saved_questions
        st.session_state.dataset_path = SAVED_SURVEY.get("dataset_path", "")
    else:
        st.session_state.question_bank, st.session_state.dataset_path = load_question_bank(PARTICIPANT_ID)
st.session_state.question_bank = add_attention_check(st.session_state.question_bank)
QUESTION_BANK = st.session_state.question_bank
DATASET_PATH = st.session_state.dataset_path

# Xiaohui's palette
GOLD_FILL = (255, 215, 0, 230)
GOLD_OUTLINE = (184, 134, 11, 255)
TEAL = (0, 255, 204, 255)
ANGLE_SELECT = (203, 32, 107, 255)   # deep rose: readable + aesthetic for selected angles
CYAN_EDGE = (0, 255, 255, 235)
YELLOW_REGION = (255, 255, 0, 100)
GRAY_SOLID = (150, 150, 150, 190)   # slightly transparent highlight for selected regions
UNION_PURPLE = (147, 112, 219, 180)
GREEN_ANGLE = (0, 150, 0, 255)
BLUE = (0, 0, 255, 255)


# ============================================================
# 0a. SELECTION-ROW HOVER CSS
# ------------------------------------------------------------
# Each selection row is rendered inside st.container(key=f"sel_row_{i}"),
# which Streamlit tags with a CSS class "st-key-sel_row_<i>". This rule
# matches that class by substring, so it scopes ONLY to selection rows —
# nothing else in the app is touched. The remove (✕) button uses a persistent
# red treatment so it remains easy to discover without relying on hover.
# ============================================================
_SELECTION_ROW_CSS = """
<style>
div[class*="st-key-sel_row_"]{
    display:grid;
    grid-template-columns:minmax(0, 1fr) auto;
    align-items:center;
    gap:6px;
    border-radius:6px;
    padding:1px 4px;
    transition:background-color .15s ease;
}
div[class*="st-key-sel_row_"] > div[data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"]){
    grid-column:1;
    grid-row:1;
    min-width:0;
    width:auto !important;
}
div[class*="st-key-sel_row_"] > div[data-testid="stElementContainer"]:has([data-testid="stButton"]){
    grid-column:2;
    grid-row:1;
    justify-self:end;
    width:auto !important;
}
div[class*="st-key-sel_row_"] [data-testid="stMarkdown"],
div[class*="st-key-sel_row_"] [data-testid="stButton"]{
    width:auto !important;
}
div[class*="st-key-sel_row_"] [data-testid="stMarkdownContainer"] p{
    margin:0;
}
div[class*="st-key-sel_row_"]:hover{
    background-color:rgba(150,150,150,0.15);
}
div[class*="st-key-sel_row_"] button{
    opacity:1;
    color:#b42318;
    background-color:#fff5f5;
    border-color:#efb7b2;
    font-size:18px;
    font-weight:700;
    justify-content:center;
    min-height:2rem;
    padding:0.1rem 0.4rem;
    transition:background-color .15s ease,border-color .15s ease;
}
div[class*="st-key-sel_row_"]:hover button{
    color:#8f1d14;
    background-color:#fee4e2;
    border-color:#d92d20;
}
</style>
"""

# ============================================================
# 0b. HOVER COMPONENT  (the ONLY new machinery)
# ------------------------------------------------------------
# A tiny bidirectional Streamlit component. It:
#   * draws the rendered PNG on a base <canvas>,
#   * paints a light-gray highlight on a top <canvas> on mousemove
#     (100% client-side: NO server round-trip while hovering),
#   * returns {x, y} on click — exactly the shape the old
#     streamlit_image_coordinates returned — so every downstream
#     line of code (hit_test, selection, tools) is unchanged.
# The front-end is written to disk once and served as a static
# component, so you still only edit / run this one app.py.
# ============================================================
_GEO_CANVAS_HTML = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
 html,body{margin:0;padding:0;background:transparent;}
 #wrap{position:relative;}
 canvas{position:absolute;top:0;left:0;}
 #ov{cursor:crosshair;}
</style></head><body>
<div id="wrap"><canvas id="bg"></canvas><canvas id="ov"></canvas></div>
<script>
function send(type,data){window.parent.postMessage(Object.assign({isStreamlitMessage:true,type:type},data),"*");}
const Streamlit={
  ready:function(){send("streamlit:componentReady",{apiVersion:1});},
  height:function(h){send("streamlit:setFrameHeight",{height:h});},
  value:function(v){send("streamlit:setComponentValue",{value:v,dataType:"json"});}
};
var SIDE=460, SHAPES=null, imgEl=null, clickN=0, SELECT_TYPE='region';
var bg=document.getElementById('bg'), ov=document.getElementById('ov');
var bgx=bg.getContext('2d'), ovx=ov.getContext('2d');

function setup(image, shapes, side, selectType){
  SIDE=side; SHAPES=shapes; SELECT_TYPE=selectType||'region';
  bg.width=ov.width=side; bg.height=ov.height=side;
  if(!imgEl || imgEl._src!==image){
    imgEl=new Image(); imgEl._src=image;
    imgEl.onload=function(){bgx.clearRect(0,0,side,side);bgx.drawImage(imgEl,0,0,side,side);};
    imgEl.src="data:image/png;base64,"+image;
  } else { bgx.clearRect(0,0,side,side); bgx.drawImage(imgEl,0,0,side,side); }
  Streamlit.height(side+4);
}

function distSeg(px,py,a,b){
  var vx=b[0]-a[0], vy=b[1]-a[1], wx=px-a[0], wy=py-a[1];
  var c1=vx*wx+vy*wy; if(c1<=0)return Math.hypot(px-a[0],py-a[1]);
  var c2=vx*vx+vy*vy; if(c2<=c1)return Math.hypot(px-b[0],py-b[1]);
  var t=c1/c2; return Math.hypot(px-(a[0]+t*vx),py-(a[1]+t*vy));
}
function inPoly(px,py,pts){
  var inside=false;
  for(var i=0,j=pts.length-1;i<pts.length;j=i++){
    var xi=pts[i][0],yi=pts[i][1],xj=pts[j][0],yj=pts[j][1];
    if(((yi>py)!=(yj>py))&&(px<(xj-xi)*(py-yi)/(yj-yi)+xi))inside=!inside;
  }
  return inside;
}
function angIn(px,py,a){
  var d=Math.hypot(px-a.cx,py-a.cy);
  if(Math.abs(d-a.r)>9)return false;
  var ang=Math.atan2(py-a.cy,px-a.cx)*180/Math.PI;
  while(ang<a.start)ang+=360; while(ang>=a.start+360)ang-=360;
  return ang<=a.end;
}
function pick(px,py){
  var S=SHAPES, i; if(!S)return null;
  if(SELECT_TYPE==='vertex'){
    for(i=0;i<S.vertices.length;i++){var v=S.vertices[i];
      if(Math.hypot(px-v[0],py-v[1])<11)return {t:'vertex',d:v};}
  } else if(SELECT_TYPE==='angle'){
    for(i=0;i<S.angles.length;i++){ if(angIn(px,py,S.angles[i]))return {t:'angle',d:S.angles[i]}; }
  } else if(SELECT_TYPE==='edge'){
    var be=null,bd=8;
    for(i=0;i<S.edges.length;i++){var e=S.edges[i],segs=e.segs||[e];
      for(var j=0;j<segs.length;j++){var dd=distSeg(px,py,segs[j].a,segs[j].b);
        if(dd<bd){bd=dd;be=e;}}}
    if(be)return {t:'edge',d:be};
  } else {
    for(i=0;i<S.regions.length;i++){ if(inPoly(px,py,S.regions[i].pts))return {t:'region',d:S.regions[i]}; }
  }
  return null;
}
var GRAY='rgba(150,150,150,';
function paint(hit){
  ovx.clearRect(0,0,SIDE,SIDE);
  if(!hit)return;
  if(hit.t==='region'){var p=hit.d.pts; ovx.beginPath(); ovx.moveTo(p[0][0],p[0][1]);
    for(var i=1;i<p.length;i++)ovx.lineTo(p[i][0],p[i][1]); ovx.closePath();
    ovx.fillStyle=GRAY+'0.45)'; ovx.fill();}
  else if(hit.t==='edge'){var segs=hit.d.segs||[hit.d];
    ovx.strokeStyle=GRAY+'0.85)'; ovx.lineWidth=12; ovx.lineCap='round';
    ovx.beginPath();
    for(var i=0;i<segs.length;i++){ovx.moveTo(segs[i].a[0],segs[i].a[1]);
      ovx.lineTo(segs[i].b[0],segs[i].b[1]);}
    ovx.stroke();}
  else if(hit.t==='vertex'){ovx.beginPath(); ovx.arc(hit.d[0],hit.d[1],10,0,2*Math.PI);
    ovx.fillStyle=GRAY+'0.7)'; ovx.fill();}
  else if(hit.t==='angle'){var a=hit.d; ovx.beginPath();
    ovx.arc(a.cx,a.cy,a.r,a.start*Math.PI/180,a.end*Math.PI/180,false);
    ovx.strokeStyle=GRAY+'0.85)'; ovx.lineWidth=6; ovx.stroke();}
  else if(hit.t==='frame'){var fr=hit.d; ovx.strokeStyle=GRAY+'0.85)'; ovx.lineWidth=8;
    ovx.strokeRect(fr.x0,fr.y0,fr.x1-fr.x0,fr.y1-fr.y0);}
}
ov.addEventListener('mousemove',function(e){var r=ov.getBoundingClientRect();
  paint(pick(e.clientX-r.left, e.clientY-r.top));});
ov.addEventListener('mouseleave',function(){ovx.clearRect(0,0,SIDE,SIDE);});
ov.addEventListener('click',function(e){var r=ov.getBoundingClientRect();
  clickN++; Streamlit.value({x:Math.round(e.clientX-r.left),y:Math.round(e.clientY-r.top),n:clickN});});
window.addEventListener("message",function(e){
  if(!e.data||e.data.type!=="streamlit:render")return;
  var a=e.data.args||{}; setup(a.image, a.shapes, a.side||460, a.select_type||'region');});
Streamlit.ready(); Streamlit.height(SIDE+4);
</script></body></html>
"""

def _geo_canvas_component():
    """Write the front-end once and return the declared component fn."""
    try:
        base = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        base = os.getcwd()
    comp_dir = os.path.join(base, "geo_canvas_comp")
    try:
        os.makedirs(comp_dir, exist_ok=True)
        idx = os.path.join(comp_dir, "index.html")
        if (not os.path.exists(idx)) or open(idx, "r", encoding="utf-8").read() != _GEO_CANVAS_HTML:
            with open(idx, "w", encoding="utf-8") as f:
                f.write(_GEO_CANVAS_HTML)
    except Exception:
        comp_dir = os.path.join(tempfile.gettempdir(), "geo_canvas_comp")
        os.makedirs(comp_dir, exist_ok=True)
        with open(os.path.join(comp_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(_GEO_CANVAS_HTML)
    return components.declare_component("geo_canvas", path=comp_dir)

_GEO_CANVAS = _geo_canvas_component()

def geo_canvas(image_b64, shapes, side, select_type="region", key=None):
    return _GEO_CANVAS(
        image=image_b64, shapes=shapes, side=side, select_type=select_type,
        key=key, default=None)

# ============================================================
# 0. TYPE CHECKERS (name-based: immune to Streamlit reruns)
# ============================================================
def is_angle(o):   return type(o).__name__ == "AngleSel"
def is_edgesel(o): return type(o).__name__ == "EdgeSel"
def is_vertex(o):  return hasattr(o, "outarcs")
def is_region(o):
    return (not is_angle(o) and not is_edgesel(o)
            and hasattr(o, "edges") and hasattr(o, "bounded"))

def question_id_for(question, index):
    return question.get("question_id", f"q_{index:03d}")

def _locked_next_question_index():
    return min(
        st.session_state.get("max_confirmed_question_index", -1) + 1,
        len(QUESTION_BANK),
    )

def current_question():
    if "survey_question_index" not in st.session_state:
        st.session_state.survey_question_index = 0
    idx = _locked_next_question_index()
    idx = max(0, min(idx, len(QUESTION_BANK) - 1))
    st.session_state.survey_question_index = idx
    return QUESTION_BANK[idx]

def init_survey_timer():
    if "survey_started_at" not in st.session_state:
        st.session_state.survey_started_at = time.time()

def survey_elapsed_seconds():
    started = st.session_state.get("survey_started_at", time.time())
    return max(0, int(time.time() - started))

def format_elapsed(seconds):
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"

def render_timer():
    elapsed = survey_elapsed_seconds()
    components.html(
        f"""
        <div style="
            display:flex;
            justify-content:flex-end;
            font-family:system-ui,-apple-system,BlinkMacSystemFont,sans-serif;
        ">
          <div id="survey-timer" style="
              min-width:130px;
              border:1px solid #d7dee8;
              border-radius:8px;
              padding:6px 9px;
              background:linear-gradient(180deg,#ffffff 0%,#f6f8fb 100%);
              box-shadow:0 1px 2px rgba(15,23,42,0.06);
              text-align:right;
          ">
            <div style="
                font-size:0.62rem;
                font-weight:650;
                letter-spacing:0.08em;
                text-transform:uppercase;
                color:#64748b;
            ">Survey time</div>
            <div id="survey-timer-value" style="
                margin-top:2px;
                font-variant-numeric:tabular-nums;
                font-size:1.15rem;
                font-weight:750;
                color:#1f2937;
                line-height:1.15;
            ">{format_elapsed(elapsed)}</div>
          </div>
        </div>
        <script>
        const startSeconds = {elapsed};
        const startMs = Date.now();
        const value = document.getElementById("survey-timer-value");
        function pad(n) {{ return String(n).padStart(2, "0"); }}
        function format(total) {{
            total = Math.max(0, Math.floor(total));
            const s = total % 60;
            const mTotal = Math.floor(total / 60);
            const m = mTotal % 60;
            const h = Math.floor(mTotal / 60);
            return h ? `${{h}}:${{pad(m)}}:${{pad(s)}}` : `${{m}}:${{pad(s)}}`;
        }}
        setInterval(() => {{
            value.textContent = format(startSeconds + (Date.now() - startMs) / 1000);
        }}, 1000);
        </script>
        """,
        height=60,
    )

def build_circular_practice_map(num_regions=5, maxX=1.0, maxY=1.0):
    """A stable split-like practice diagram with a rounded boundary.

    It deliberately avoids the real survey's square frame, but still uses the
    same straight-edge graph representation so regions, edges, vertices, and
    angles remain selectable with the normal tools.
    """
    n = 8
    cx, cy = maxX / 2, maxY / 2
    radius = min(maxX, maxY) * 0.43
    angle_offset = math.pi / n

    ring = [
        Graph.Vertex(
            Graph.Vector(
                cx + radius * math.cos(angle_offset + 2 * math.pi * i / n),
                cy + radius * math.sin(angle_offset + 2 * math.pi * i / n),
            )
        )
        for i in range(n)
    ]
    upper_split = Graph.Vertex(Graph.Vector(0.45, 0.57))
    lower_split = Graph.Vertex(Graph.Vector(0.58, 0.42))
    vertices = ring + [upper_split, lower_split]

    edge_roots = []
    edge_lookup = {}

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
    for i, path in enumerate(face_vertex_paths[: max(1, int(num_regions or 5))]):
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
        vertex.faces = [
            face
            for face in [outside] + faces
            if vertex in getattr(face, "vertices", [])
        ]

    edges = []
    for edge in edge_roots:
        edges.extend([edge, edge.reverse])
    return Graph.Map(vertices, edges, [outside] + faces, [maxX, maxY])

def reset_tool_state_for_question(question):
    Graph.initialize()
    maxX, maxY = 1.0, 1.0
    seed = question.get("seed", 42)
    num_regions = question.get("num_regions", 8)
    if question.get("is_practice"):
        res_map = build_circular_practice_map(num_regions, maxX, maxY)
    else:
        res_map = BuildRandomMap.BuildRandomMap(num_regions, maxX, maxY, seed)
    map_helpers.use_map(res_map)
    T.setup(res_map)

    face_label_cache = {}
    for face in res_map.faces:
        if face.bounded:
            face._cache_idx = id(face)
            lp, d = Graph.LetterPointFace(face)
            face_label_cache[id(face)] = (lp, d)

    st.session_state.res_map = res_map
    st.session_state.face_label_cache = face_label_cache
    st.session_state.maxX, st.session_state.maxY = maxX, maxY
    st.session_state.active_tool = None
    st.session_state.selection = []
    st.session_state.selection_meta = []
    st.session_state.last_click = None
    st.session_state.click_targets = None
    st.session_state.pending_angle_vertex = None
    st.session_state.pending_edge_options = []
    st.session_state.annotations = []
    st.session_state.lines = []
    st.session_state.angles = []
    st.session_state.named_edges = []
    st.session_state.unions = []
    st.session_state.union_consumed = []
    st.session_state.undo_stack = []
    st.session_state.point_names = {}
    st.session_state.program = []
    st.session_state.log = []
    st.session_state.tool_calls = []
    st.session_state.selection_events = []
    st.session_state.question_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    st.session_state.question_started_time = time.time()
    st.session_state.counters = {"v": 1, "L": 1, "U": 1, "r": 1, "a": 1, "e": 1}
    st.session_state.loaded_question_id = question.get("question_id", "")

# ============================================================
# 1. SESSION INIT
# ============================================================
if "survey_responses" not in st.session_state:
    saved_responses = SAVED_SURVEY.get("responses", {})
    st.session_state.survey_responses = (
        saved_responses if isinstance(saved_responses, dict) else {}
    )
if "last_result_path" not in st.session_state:
    saved_path = participant_result_path(PARTICIPANT_ID)
    st.session_state.last_result_path = saved_path if SAVED_SURVEY else ""
if "survey_completed" not in st.session_state:
    st.session_state.survey_completed = bool(SAVED_SURVEY.get("survey_completed", False))
if "tutorial_completed" not in st.session_state:
    saved_responses = st.session_state.get("survey_responses", {})
    st.session_state.tutorial_completed = bool(
        SAVED_SURVEY.get("survey_completed", False)
        or (isinstance(saved_responses, dict) and bool(saved_responses))
        or st.query_params.get("skip_tutorial") == "1"
        or st.query_params.get("tutorial_done") == "1"
    )
if "timer_hidden" not in st.session_state:
    st.session_state.timer_hidden = False
if "answer_feedback" not in st.session_state:
    st.session_state.answer_feedback = None
if "max_confirmed_question_index" not in st.session_state:
    saved_confirmed = SAVED_SURVEY.get("max_confirmed_question_index")
    if isinstance(saved_confirmed, int):
        st.session_state.max_confirmed_question_index = saved_confirmed
    else:
        answered_indices = [
            int(response.get("question_index", -1))
            for response in st.session_state.survey_responses.values()
            if isinstance(response, dict) and str(response.get("answer", "")).strip()
        ]
        st.session_state.max_confirmed_question_index = max(answered_indices, default=-1)
if _locked_next_question_index() >= len(QUESTION_BANK):
    st.session_state.survey_completed = True

IS_PRACTICE = (
    not st.session_state.tutorial_completed
    and not st.session_state.survey_completed
)
if IS_PRACTICE:
    st.session_state.setdefault("practice_step", "select")
    st.session_state.setdefault("practice_rightmost_vertex_done", False)
    st.session_state.setdefault("practice_meeting_vertex_done", False)
    st.session_state.setdefault("practice_neighbors_done", False)
    st.session_state.setdefault("practice_merge_done", False)
else:
    st.session_state.pop("practice_step", None)
PRACTICE_STEP = st.session_state.get("practice_step", "select")
if IS_PRACTICE and PRACTICE_STEP not in ("select", "tools"):
    PRACTICE_STEP = "tools"
    st.session_state.practice_step = PRACTICE_STEP
if "survey_question_index" not in st.session_state:
    st.session_state.survey_question_index = 0
QUESTION = PRACTICE_QUESTION if IS_PRACTICE else current_question()
if st.session_state.answer_feedback is None:
    current_index = st.session_state.survey_question_index
    current_qid = question_id_for(QUESTION, current_index)
    saved_response = st.session_state.survey_responses.get(current_qid)
    if (
        current_index > st.session_state.max_confirmed_question_index
        and isinstance(saved_response, dict)
        and str(saved_response.get("answer", "")).strip()
    ):
        saved_answer = str(saved_response.get("answer", "")).strip()
        saved_is_correct = saved_response.get("is_correct")
        if saved_is_correct is None:
            saved_is_correct = answer_is_correct(QUESTION, saved_answer)
        st.session_state.answer_feedback = {
            "question_index": current_index,
            "question_id": current_qid,
            "answer": saved_answer,
            "correct_answer": QUESTION.get("answer", ""),
            "correct_answer_display": format_answer_for_feedback(QUESTION),
            "is_correct": saved_is_correct,
            "is_last_question": current_index >= len(QUESTION_BANK) - 1,
        }
if (
    "res_map" not in st.session_state
    or st.session_state.get("loaded_question_id") != QUESTION.get("question_id", "")
):
    reset_tool_state_for_question(QUESTION)
if not IS_PRACTICE:
    init_survey_timer()
if "tool_calls" not in st.session_state:
    st.session_state.tool_calls = []
if "selection_events" not in st.session_state:
    st.session_state.selection_events = []
if "question_started_time" not in st.session_state:
    st.session_state.question_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    st.session_state.question_started_time = time.time()

res_map = st.session_state.res_map
maxX, maxY = st.session_state.maxX, st.session_state.maxY
img_size = (int(200 + 800 * maxX), int(200 + 800 * maxY))

# ============================================================
# 2. NAMING & DESCRIPTIONS
# ============================================================
SUBSCRIPT_DIGITS = {"0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉"}
SUBSCRIPT_TO_DIGITS = {v: k for k, v in SUBSCRIPT_DIGITS.items()}

def to_subscript_number(n):
    return "".join(SUBSCRIPT_DIGITS.get(ch, ch) for ch in str(n))

def next_name(prefix):
    st.session_state.counters.setdefault(prefix, 1)
    n = st.session_state.counters[prefix]
    st.session_state.counters[prefix] += 1
    if prefix == "U":
        return prefix
    return f"{prefix}{n}"

def point_name(v, create=True):
    key = id(v)
    if key in st.session_state.point_names:
        return st.session_state.point_names[key]
    if not create:
        return None
    name = next_name("v")
    st.session_state.point_names[key] = name
    st.session_state.annotations.append({"kind": "point", "p": v.p, "label": name})
    return name

def point_name_with_meta(v):
    """Same as point_name(), but also returns cleanup metadata IF this call
    just created a brand-new name + label (vs. reusing one the point already
    had). Used only at the moment a vertex enters the selection, so the
    per-item remove (✕) button can retract exactly what it added."""
    key = id(v)
    if key in st.session_state.point_names:
        return st.session_state.point_names[key], None
    name = next_name("v")
    st.session_state.point_names[key] = name
    ann = {"kind": "point", "p": v.p, "label": name}
    st.session_state.annotations.append(ann)
    return name, {"kind": "point", "point_key": key, "annotation_ref": ann}

def angle_name(a_sel):
    for name, sel in st.session_state.angles:
        if sel == a_sel:
            return name
    return "a?"

def edge_name(e_sel):
    for name, sel in st.session_state.named_edges:
        if sel == e_sel:
            return name
    return None

def code_name(o):
    if o == "frame":  return '"frame"'
    if is_angle(o):   return angle_name(o)
    if is_edgesel(o):
        nm = edge_name(o)
        return nm if nm else f"edge[{o.text}]"
    if is_region(o):  return o.letter
    if is_vertex(o):  return point_name(o)
    return str(o)

def describe(o):
    # angle/edge checks FIRST
    if is_angle(o):
        return f"angle {angle_name(o)} (in Region {o.face.letter})"
    if is_edgesel(o):
        nm = edge_name(o)
        return f"edge {nm} ({o.text})" if nm else o.text
    if isinstance(o, (list, tuple, set)):
        items = list(o)
        return "(nothing)" if not items else ", ".join(describe(x) for x in items)
    if o is None: return "(nothing)"
    if isinstance(o, bool): return "YES" if o else "NO"
    if o == "frame": return "the Frame"
    if is_region(o):
        return f"Region {o.letter}" if getattr(o, "bounded", True) else "the Outside (frame)"
    if is_vertex(o):
        nm = point_name(o, create=False)
        return nm if nm else "Vertex"
    if isinstance(o, dict) and "type" in o:
        return {"segment": "a segment", "extend": "a full line", "ray": "a ray"}[o["type"]]
    if isinstance(o, float): return f"{o:.4f}"
    return str(o)

def answer_like_text(o):
    """Format tool results so they can be copied into the answer box."""
    if is_angle(o):
        return angle_name(o)
    if is_edgesel(o):
        nm = edge_name(o)
        return nm if nm else o.text
    if isinstance(o, (list, tuple, set)):
        items = list(o)
        return "None" if not items else ", ".join(answer_like_text(x) for x in items)
    if o is None:
        return "None"
    if isinstance(o, bool):
        return "Yes" if o else "No"
    if o == "frame":
        return "Frame"
    if is_region(o):
        return o.letter if getattr(o, "bounded", True) else "Outside"
    if is_vertex(o):
        nm = point_name(o, create=False)
        return nm if nm else "Vertex"
    if isinstance(o, dict) and "type" in o:
        return {"segment": "segment", "extend": "full line", "ray": "ray"}[o["type"]]
    if isinstance(o, float):
        return f"{o:.4f}"
    return str(o)

def sel_sig():
    s = st.session_state.selection
    return {
        "regions":  [o for o in s if o != "frame" and is_region(o)],
        "vertices": [o for o in s if o != "frame" and is_vertex(o)],
        "edges":    [o for o in s if is_edgesel(o)],
        "angles":   [o for o in s if is_angle(o)],
        "frame":    [o for o in s if o == "frame"],
        "n": len(s),
    }

PRACTICE_REQUIRED_SELECTIONS = ["Region", "Angle", "Vertex", "Edge"]

def practice_selected_entity_types():
    selected = set()
    for obj in st.session_state.get("selection", []):
        if is_region(obj):
            selected.add("Region")
        elif is_angle(obj):
            selected.add("Angle")
        elif is_vertex(obj):
            selected.add("Vertex")
        elif is_edgesel(obj):
            selected.add("Edge")
    return selected

def practice_selection_checklist_html(selected):
    rows = []
    for label in PRACTICE_REQUIRED_SELECTIONS:
        done = label in selected
        icon = "✓" if done else "○"
        color = "#047857" if done else "#6b7280"
        rows.append(
            f'<div style="font-size:0.95rem; line-height:1.55; color:{color};">'
            f'{icon} {html.escape(label)}</div>'
        )
    return "".join(rows)

def practice_rightmost_vertex_done():
    if st.session_state.get("practice_rightmost_vertex_done"):
        return True
    for call in st.session_state.get("tool_calls", []):
        if (
            isinstance(call, dict)
            and call.get("tool") == "vertex"
            and call.get("function") == "vertex"
            and 'which="rightmost"' in str(call.get("input", ""))
            and "A" in str(call.get("input", ""))
        ):
            return True
    return False

def practice_meeting_vertex_done():
    if st.session_state.get("practice_meeting_vertex_done"):
        return True
    for call in st.session_state.get("tool_calls", []):
        input_text = str(call.get("input", "")) if isinstance(call, dict) else ""
        if (
            isinstance(call, dict)
            and call.get("tool") == "vertex"
            and call.get("function") == "vertex"
            and "on_frame=False" in input_text
            and "A" in input_text
            and "D" in input_text
            and "E" in input_text
        ):
            return True
    return False

def practice_neighbors_done():
    if st.session_state.get("practice_neighbors_done"):
        return True
    for call in st.session_state.get("tool_calls", []):
        input_text = str(call.get("input", "")) if isinstance(call, dict) else ""
        if (
            isinstance(call, dict)
            and call.get("tool") == "neighbors"
            and call.get("function") == "neighbors"
            and 'neighbors(A, "edge")' in input_text
        ):
            return True
    return False

def practice_merge_done():
    if st.session_state.get("practice_merge_done"):
        return True
    for call in st.session_state.get("tool_calls", []):
        input_text = str(call.get("input", "")) if isinstance(call, dict) else ""
        if (
            isinstance(call, dict)
            and call.get("tool") == "merge"
            and call.get("function") == "merge"
            and (
                "merge(A, E)" in input_text
                or "merge(E, A)" in input_text
            )
        ):
            return True
    return False

def practice_question_text_for_step(step):
    if step == "select":
        return (
            "Practice 1 of 2: select one region, one angle, one vertex, and one edge "
            "in the diagram. Use the Selection choices to switch what you are selecting."
        )
    return (
        "Practice 2 of 2: practice using a tool."
    )

# ---- selection add/clear/remove (keep selection + selection_meta in lockstep) ----
def add_to_selection(obj, meta=None):
    """Append obj to the selection together with optional cleanup metadata —
    what to retract from the map if this exact entry is later removed via the
    per-item ✕ button. meta is None for plain re-selections (frame, regions,
    edges, or re-picking an already-saved point/angle): there's nothing extra
    to clean up beyond the live highlight, which disappears on its own."""
    st.session_state.selection.append(obj)
    st.session_state.selection_meta.append(meta)

def add_edge_to_selection(edge_obj):
    """Select a named edge once; repeated clicks keep its stable name."""
    if edge_obj in st.session_state.selection:
        return False
    add_to_selection(edge_obj)
    return True

def _selection_event_object(obj):
    if obj == "frame":
        kind, label = "frame", "frame"
    elif is_angle(obj):
        kind, label = "angle", angle_name(obj)
    elif is_edgesel(obj):
        kind, label = "edge", edge_name(obj) or obj.text
    elif is_region(obj):
        kind, label = "region", obj.letter
    elif is_vertex(obj):
        kind, label = "vertex", point_name(obj, create=False) or "unlabeled vertex"
    else:
        kind, label = "object", describe(obj)
    return {
        "object_type": kind,
        "object_label": label,
        "description": describe(obj),
    }

def record_selection_event(action, obj=None):
    """Record UI selection history separately from executed tool calls."""
    events = st.session_state.setdefault("selection_events", [])
    event = {
        "order": len(events) + 1,
        "action": action,
        "selection_mode": st.session_state.get("selection_filter"),
        "selection_after": [
            _selection_event_object(item) for item in st.session_state.selection
        ],
        "timestamp": _ts(),
        "survey_elapsed_seconds": survey_elapsed_seconds(),
    }
    if obj is not None:
        event["object"] = _selection_event_object(obj)
    events.append(event)

def clear_selection():
    st.session_state.selection = []
    st.session_state.selection_meta = []

def remove_selection_item(i):
    """Remove the i-th selection entry (the per-row ✕ button). Vertex
    labels are persistent, so deselecting a vertex leaves its point label on
    the map. Newly selected angle arcs are still retracted on deselection."""
    sel, meta_list = st.session_state.selection, st.session_state.selection_meta
    if i < 0 or i >= len(sel):
        return
    meta = meta_list[i] if i < len(meta_list) else None
    removed = sel.pop(i)
    if i < len(meta_list):
        meta_list.pop(i)
    record_selection_event("deselect", removed)
    if meta:
        if meta["kind"] == "point":
            # Vertex labels are persistent names. Deselecting a vertex only
            # removes it from the current selection; the label stays visible.
            pass
        elif meta["kind"] == "angle":
            entry = meta.get("angle_entry")
            st.session_state.angles = [a for a in st.session_state.angles if a is not entry]
            ref = meta.get("annotation_ref")
            st.session_state.annotations = [a for a in st.session_state.annotations if a is not ref]
    st.session_state.click_targets = None
    st.session_state.pending_angle_vertex = None

# ============================================================
# 3. LINE GEOMETRY
# ============================================================
def _extend_to_frame(a, b):
    dx, dy = b.x - a.x, b.y - a.y
    ts = []
    if abs(dx) > 1e-9: ts += [(0 - a.x) / dx, (maxX - a.x) / dx]
    if abs(dy) > 1e-9: ts += [(0 - a.y) / dy, (maxY - a.y) / dy]
    pts = []
    for t in ts:
        x, y = a.x + t * dx, a.y + t * dy
        if -1e-6 <= x <= maxX + 1e-6 and -1e-6 <= y <= maxY + 1e-6:
            pts.append((t, Graph.Vector(x, y)))
    pts.sort(key=lambda z: z[0])
    return pts[0][1], pts[-1][1]

def line_endpoints_math(line):
    if line["type"] == "segment":
        return line["a"], line["b"]
    if line["type"] == "extend":
        return _extend_to_frame(line["a"], line["b"])
    if line["type"] == "ray":
        a = line["a"]
        ends = {0: Graph.Vector(maxX, a.y), 1: Graph.Vector(a.x, maxY),
                2: Graph.Vector(0, a.y), 3: Graph.Vector(a.x, 0)}
        return a, ends[line["direction"]]

def edgesel_endpoints(es):
    pts = []
    for e in es.segments:
        pts += [e.tail, e.head]
    best, bd = (pts[0], pts[-1]), -1
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            d = Graph.vecDist(pts[i].p, pts[j].p)
            if d > bd:
                bd, best = d, (pts[i], pts[j])
    return best

# ============================================================
# 4. XIAOHUI-STYLE DRAWING PRIMITIVES
# ============================================================
def highlight_vertex_x(odraw, p, ring=False):
    px, py = DrawGraph.V2P(p)
    if ring:
        odraw.ellipse([px-15, py-15, px+15, py+15], outline=TEAL, width=4)
    else:
        odraw.ellipse([px-12, py-12, px+12, py+12], fill=GOLD_FILL,
                      outline=GOLD_OUTLINE, width=4)

def highlight_edge_x(odraw, e, label=None):
    """Thick cyan marker stroke + endpoint caps; optional name label."""
    p1, p2 = DrawGraph.V2P(e.tail.p), DrawGraph.V2P(e.head.p)
    odraw.line([p1, p2], fill=CYAN_EDGE, width=14)
    for (px, py) in (p1, p2):
        odraw.ellipse([px-7, py-7, px+7, py+7], fill=CYAN_EDGE)
    if label:
        mx, my = (p1[0]+p2[0])//2, (p1[1]+p2[1])//2
        font = DrawGraph.GetSystemFont(35)
        odraw.text((mx, my), label, fill=(0, 100, 130, 255), font=font,
                   anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))

def draw_interior_arc_x(odraw, vertex, face, label=None,
                        radius=45, color=GREEN_ANGLE, width=5):
    """Xiaohui's interior arc (position match + fallbacks, pixel-space sweep)."""
    p_center = vertex.p
    e_in = next((e for e in face.edges if e.head.p == p_center), None)
    e_out = next((e for e in face.edges if e.tail.p == p_center), None)
    if not e_in:
        e_in = next((e for e in face.edges
                     if e.head == vertex or Graph.vecDist(e.head.p, p_center) < 1e-9), None)
    if not e_out:
        e_out = next((e for e in face.edges
                      if e.tail == vertex or Graph.vecDist(e.tail.p, p_center) < 1e-9), None)
    if not e_in or not e_out:
        return
    cx, cy = DrawGraph.V2P(p_center)
    px_prev, py_prev = DrawGraph.V2P(e_in.tail.p)
    px_next, py_next = DrawGraph.V2P(e_out.head.p)
    ang_prev = math.degrees(math.atan2(py_prev - cy, px_prev - cx))
    ang_next = math.degrees(math.atan2(py_next - cy, px_next - cx))
    start, end = ang_prev, ang_next
    while end < start:
        end += 360
    sweep = end - start
    if abs(sweep - 180.0) < 0.1:
        return
    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
    odraw.arc(bbox, start=start, end=end, fill=color, width=width)
    if label:
        mid = math.radians(start + sweep / 2)
        lx = cx + (radius + 24) * math.cos(mid)
        ly = cy + (radius + 24) * math.sin(mid)
        font = DrawGraph.GetSystemFont(35)
        odraw.text((lx, ly), label, fill=color, font=font, anchor="mm",
                   stroke_width=2, stroke_fill=(255, 255, 255, 255))


def draw_union_label(draw, xy, name, font_big):
    lx, ly = xy
    draw.text((lx, ly), name, fill=(0, 0, 0, 255), font=font_big,
              anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))

def draw_union_solid(draw, union, font_big):
    fu = union["face"]
    pts = [DrawGraph.V2P(v.p) for v in fu.vertices]
    draw.polygon(pts, fill=UNION_PURPLE)
    for e in fu.edges:
        draw.line([DrawGraph.V2P(e.tail.p), DrawGraph.V2P(e.head.p)],
                  fill=(0, 0, 0, 255), width=6)

def _face_label_lp_d(face):
    """Stable label position for a face (uses the locked cache when available)."""
    idx = getattr(face, "_cache_idx", None)
    cache = st.session_state.get("face_label_cache", {})
    if idx is not None and idx in cache:
        return cache[idx]
    return Graph.LetterPointFace(face)

def highlight_region_solid(odraw, face, fill=GRAY_SOLID, draw_label=True):
    """Opaque recolor of a region (new solid color, not a translucent film).
    Keeps the black outline and the region letter readable on top."""
    pts = [DrawGraph.V2P(v.p) for v in face.vertices]
    odraw.polygon(pts, fill=fill, outline=(0, 0, 0, 255))
    for e in face.edges:
        odraw.line([DrawGraph.V2P(e.tail.p), DrawGraph.V2P(e.head.p)],
                   fill=(0, 0, 0, 255), width=4)
    if draw_label:
        lp, d = _face_label_lp_d(face)
        coords = DrawGraph.V2P(lp)
        font = DrawGraph.GetSystemFont(80 if d > 0.06 else 45)
        odraw.text(coords, face.letter, fill=(0, 0, 0, 255), font=font, anchor="mm",
                   stroke_width=2, stroke_fill=(255, 255, 255, 255))

# ============================================================
# 5. RENDERING
# ============================================================
def draw_circular_practice_faces(draw):
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

        if hasattr(face, "_cache_idx") and face._cache_idx in st.session_state.face_label_cache:
            lp, d = st.session_state.face_label_cache[face._cache_idx]
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

def render():
    img = Image.new("RGBA", img_size, (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    if IS_PRACTICE:
        draw_circular_practice_faces(draw)
    else:
        DrawGraph.DrawAllFaces(res_map, draw, None,
                               label_cache=st.session_state.face_label_cache)

    font = DrawGraph.GetSystemFont(35)
    font_big = DrawGraph.GetSystemFont(80)

    for union in st.session_state.unions:
        draw_union_solid(draw, union, font_big)

    overlay = Image.new("RGBA", img_size, (255, 255, 255, 0))
    odraw = ImageDraw.Draw(overlay)
    union_face_ids = {id(union["face"]) for union in st.session_state.unions}

    # ---- PASS 1: region fills go UNDERNEATH points/lines/angles, so a
    # reference point is never hidden under a highlight. The unbounded outer
    # face is never filled (it would blanket the whole canvas).
    for ann in st.session_state.annotations:
        if ann["kind"] == "region" and getattr(ann["obj"], "bounded", False):
            face = ann["obj"]
            highlight_region_solid(
                odraw, face, ann.get("color", GRAY_SOLID),
                draw_label=id(face) not in union_face_ids,
            )
    for o in st.session_state.selection:
        if o != "frame" and is_region(o) and getattr(o, "bounded", False):
            highlight_region_solid(
                odraw, o, GRAY_SOLID,
                draw_label=id(o) not in union_face_ids,
            )

    # Union labels are drawn once, after any region highlight. Drawing them in
    # both the base union and the highlight layer produces a displaced ghost U.
    for union in st.session_state.unions:
        draw_union_label(odraw, union["label_xy"], union["name"], font_big)

    # ---- PASS 2: markers (points, lines, angles, edges) on top of fills.
    for ann in st.session_state.annotations:
        kind = ann["kind"]
        if kind == "point":
            highlight_vertex_x(odraw, ann["p"])
            if ann.get("label"):
                px, py = DrawGraph.V2P(ann["p"])
                odraw.text((px + 16, py - 32), ann["label"], fill=BLUE, font=font,
                           stroke_width=2, stroke_fill=(255, 255, 255, 255))
        elif kind == "line":
            a, b = line_endpoints_math(ann["line"])
            odraw.line([DrawGraph.V2P(a), DrawGraph.V2P(b)], fill=BLUE, width=6)
            if ann.get("label"):
                mx = (DrawGraph.V2P(a)[0] + DrawGraph.V2P(b)[0]) // 2
                my = (DrawGraph.V2P(a)[1] + DrawGraph.V2P(b)[1]) // 2
                odraw.text((mx, my), ann["label"], fill=BLUE, font=font,
                           anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))
        elif kind == "angle":
            draw_interior_arc_x(odraw, ann["vertex"], ann["face"],
                                label=ann.get("label"))

    # live selection markers — angle/edge checks FIRST
    for o in st.session_state.selection:
        if o == "frame":
            p_bl, p_tr = DrawGraph.V2P(Graph.Vector(0, 0)), DrawGraph.V2P(Graph.Vector(maxX, maxY))
            odraw.rectangle([p_bl[0], p_tr[1], p_tr[0], p_bl[1]], outline=TEAL, width=10)
        elif is_angle(o):
            draw_interior_arc_x(odraw, o.vertex, o.face, label=angle_name(o),
                                color=ANGLE_SELECT, width=6)
        elif is_edgesel(o):
            for e in o.segments:
                highlight_edge_x(odraw, e)
            # label once at the midpoint of the first segment
            highlight_edge_x(odraw, o.segments[0], label=edge_name(o))
        elif is_vertex(o):
            highlight_vertex_x(odraw, o.p, ring=True)

    img.alpha_composite(overlay)
    return img

# ---- HOVER SHAPES -----------------------------------------------------------
# Serialize the live geometry into DISPLAY-space (0..DISPLAY_SIDE) vector shapes
# so the browser can hit-test under the mouse and paint the gray highlight with
# no server round-trip. Pure read-only: reuses the same V2P transform render()
# uses, so the overlay is pixel-aligned with the PNG by construction.
def _consumed_to_union_map():
    """id(constituent face) -> the union face that swallowed it."""
    m = {}
    for union in st.session_state.unions:
        for f in union["pair"]:
            m[id(f)] = union["face"]
    return m

def _edge_interior_to_union(e, cmap):
    """True if BOTH faces touching edge e were merged into the SAME union, i.e.
    the edge now lives strictly inside a solid merged region."""
    fa, fb = e.leftFace, e.reverse.leftFace
    if not (getattr(fa, "bounded", False) and getattr(fb, "bounded", False)):
        return False
    ua, ub = cmap.get(id(fa)), cmap.get(id(fb))
    return ua is not None and ua is ub

def _vertex_interior_to_union(v, cmap):
    """True if every bounded region around v was merged into one single union and
    v does not sit on the outer frame — i.e. v is strictly inside a merged blob.
    Boundary corners of a union (which still touch a live region or the frame)
    stay selectable as corners of the union itself."""
    bounded = [f for f in v.faces if getattr(f, "bounded", False)]
    if not bounded:
        return False
    if any(not getattr(f, "bounded", False) for f in v.faces):
        return False                    # touches the outside frame -> boundary
    units = set()
    for f in bounded:
        u = cmap.get(id(f))
        if u is None:
            return False                # touches a live, un-merged region -> boundary
        units.add(id(u))
    return len(units) == 1

def build_hover_shapes():
    sx = DISPLAY_SIDE / img_size[0]
    sy = DISPLAY_SIDE / img_size[1]

    def D(p):
        X, Y = DrawGraph.V2P(p)
        return [X * sx, Y * sy]

    consumed = st.session_state.union_consumed
    cmap = _consumed_to_union_map()
    union_faces = [u["face"] for u in st.session_state.unions]

    regions = []
    for f in res_map.faces:
        if not getattr(f, "bounded", False):
            continue
        if f in consumed:
            continue
        regions.append({"id": id(f), "pts": [D(v.p) for v in f.vertices]})
    for fu in union_faces:
        regions.append({"id": id(fu), "pts": [D(v.p) for v in fu.vertices]})

    # A visual edge can contain several half-edge segments when another region
    # meets it at an intermediate vertex.  Group those segments by trueEdge so
    # hover previews the same complete edge that a click will select.
    seen, edge_groups = set(), {}
    for e in res_map.edges:
        if _edge_interior_to_union(e, cmap):     # edge now inside a merged region
            continue
        a, b = D(e.tail.p), D(e.head.p)
        keyk = tuple(sorted([(round(a[0], 1), round(a[1], 1)),
                             (round(b[0], 1), round(b[1], 1))]))
        if keyk in seen:
            continue
        seen.add(keyk)
        root = getattr(e, "trueEdge", e)
        reverse_root = getattr(e.reverse, "trueEdge", e.reverse)
        group_key = tuple(sorted((id(root), id(reverse_root))))
        edge_groups.setdefault(group_key, []).append({"a": a, "b": b})
    edges = [{"segs": segs} for segs in edge_groups.values()]

    vertices = [D(v.p) for v in res_map.vertices
                if not _vertex_interior_to_union(v, cmap)]

    c0, c1 = D(Graph.Vector(0, 0)), D(Graph.Vector(maxX, maxY))
    frame = {"x0": min(c0[0], c1[0]), "y0": min(c0[1], c1[1]),
             "x1": max(c0[0], c1[0]), "y1": max(c0[1], c1[1])}

    angles = []
    for vertex, face in selectable_angle_targets():
        pc = vertex.p
        e_in = next((e for e in face.edges if e.head.p == pc), None)
        e_out = next((e for e in face.edges if e.tail.p == pc), None)
        if not e_in:
            e_in = next((e for e in face.edges if Graph.vecDist(e.head.p, pc) < 1e-9), None)
        if not e_out:
            e_out = next((e for e in face.edges if Graph.vecDist(e.tail.p, pc) < 1e-9), None)
        if not e_in or not e_out:
            continue
        cx, cy = D(pc)
        pxp, pyp = D(e_in.tail.p)
        pxn, pyn = D(e_out.head.p)
        ang_prev = math.degrees(math.atan2(pyp - cy, pxp - cx))
        ang_next = math.degrees(math.atan2(pyn - cy, pxn - cx))
        start, end = ang_prev, ang_next
        while end < start:
            end += 360
        if abs((end - start) - 180.0) < 0.1:
            continue
        angles.append({"cx": cx, "cy": cy, "r": 20.0, "start": start, "end": end})

    return {"regions": regions, "edges": edges, "vertices": vertices,
            "frame": frame, "angles": angles}

def live_selectable_regions():
    consumed = st.session_state.union_consumed
    regions = [
        f for f in res_map.faces
        if getattr(f, "bounded", False) and f not in consumed
    ]
    regions.extend(u["face"] for u in st.session_state.unions)
    return regions

def selectable_angle_targets():
    cmap = _consumed_to_union_map()
    targets = []
    for face in live_selectable_regions():
        for vertex in getattr(face, "vertices", []):
            if _vertex_interior_to_union(vertex, cmap):
                continue
            targets.append((vertex, face))
    return targets

# ============================================================
# 6. CLICK HIT-TESTING
# ============================================================
def get_math_coords(px, py):
    rx = px * (img_size[0] / DISPLAY_SIDE)
    ry = py * (img_size[1] / DISPLAY_SIDE)
    return Graph.Vector((rx - 100) / MATH_SCALE, (900.0 - ry) / MATH_SCALE)

def hit_test(px, py):
    cp = get_math_coords(px, py)
    cmap = _consumed_to_union_map()
    v_best, v_d = None, 25 / MATH_SCALE
    for v in res_map.vertices:
        if _vertex_interior_to_union(v, cmap):   # corner now inside a merge
            continue
        d = Graph.vecDist(cp, v.p)
        if d < v_d: v_d, v_best = d, v

    # A merged region (union) takes priority over the originals beneath it, and
    # its constituent faces are no longer independently selectable.
    f_hit = None
    for union in st.session_state.unions:
        if Graph.pointInsideFace(cp, union["face"]):
            f_hit = union["face"]
            break
    if f_hit is None:
        consumed = st.session_state.union_consumed
        f_hit = next((f for f in res_map.faces
                      if f.bounded and f not in consumed
                      and Graph.pointInsideFace(cp, f)), None)

    e_best, e_d = None, 20 / MATH_SCALE
    for e in res_map.edges:
        # Keep server-side clicks consistent with the browser hover layer:
        # edges swallowed into the interior of a union are not selectable.
        if _edge_interior_to_union(e, cmap):
            continue
        d = Graph.distPointFromEdge(cp, e.tail.p, e.head.p)
        if d < e_d: e_d, e_best = d, e
    return v_best, f_hit, e_best

def _display_angle_shape(vertex, face):
    sx = DISPLAY_SIDE / img_size[0]
    sy = DISPLAY_SIDE / img_size[1]

    def D(p):
        X, Y = DrawGraph.V2P(p)
        return X * sx, Y * sy

    pc = vertex.p
    e_in = next((e for e in face.edges if e.head.p == pc), None)
    e_out = next((e for e in face.edges if e.tail.p == pc), None)
    if not e_in:
        e_in = next((e for e in face.edges if Graph.vecDist(e.head.p, pc) < 1e-9), None)
    if not e_out:
        e_out = next((e for e in face.edges if Graph.vecDist(e.tail.p, pc) < 1e-9), None)
    if not e_in or not e_out:
        return None
    cx, cy = D(pc)
    pxp, pyp = D(e_in.tail.p)
    pxn, pyn = D(e_out.head.p)
    start = math.degrees(math.atan2(pyp - cy, pxp - cx))
    end = math.degrees(math.atan2(pyn - cy, pxn - cx))
    while end < start:
        end += 360
    if abs((end - start) - 180.0) < 0.1:
        return None
    return {"cx": cx, "cy": cy, "r": 20.0, "start": start, "end": end}

def _angle_shape_contains(shape, px, py):
    dist = math.hypot(px - shape["cx"], py - shape["cy"])
    if abs(dist - shape["r"]) > 11:
        return False
    ang = math.degrees(math.atan2(py - shape["cy"], px - shape["cx"]))
    while ang < shape["start"]:
        ang += 360
    while ang >= shape["start"] + 360:
        ang -= 360
    return ang <= shape["end"]

def hit_test_by_mode(px, py, mode):
    v, f, e = hit_test(px, py)
    if mode == "Region":
        return ("region", f) if f else (None, None)
    if mode == "Vertex":
        return ("vertex", v) if v else (None, None)
    if mode == "Edge":
        return ("edge", e) if e else (None, None)
    if mode == "Angle":
        best, best_delta = None, 999
        for vertex, face in selectable_angle_targets():
            shape = _display_angle_shape(vertex, face)
            if shape and _angle_shape_contains(shape, px, py):
                delta = abs(math.hypot(px - shape["cx"], py - shape["cy"]) - shape["r"])
                if delta < best_delta:
                    best_delta = delta
                    best = AngleSel(vertex, face)
        return ("angle", best) if best else (None, None)
    return (None, None)

def edge_options(e):
    root = getattr(e, "trueEdge", e)

    # If either side of this edge has been merged into a union, present it as an
    # edge of that union instead of the (now hidden) constituent region.
    consumed_to_union = {}
    for union in st.session_state.unions:
        for f in union["pair"]:
            consumed_to_union[id(f)] = union["face"]

    sides = []
    for face in (e.leftFace, e.reverse.leftFace):
        if face is None or not face.bounded:
            continue
        sides.append(consumed_to_union.get(id(face), face))

    # Both sides resolve to the same union -> this edge is interior to it; offer
    # nothing (you can't select an edge that lives inside a solid region).
    if len(sides) == 2 and sides[0] is sides[1]:
        return []

    opts = []
    seen = set()
    for face in sides:
        if id(face) in seen:
            continue
        seen.add(id(face))
        segs = [x for x in face.edges
                if getattr(x, "trueEdge", x) == root
                or getattr(x.reverse, "trueEdge", x.reverse) == root]
        if segs:
            opts.append(EdgeSel(segs, face, f"edge of {face.letter}"))
    if len(opts) == 2 and len(opts[0].segments) == len(opts[1].segments):
        na, nb = opts[0].owner.letter, opts[1].owner.letter
        return [EdgeSel(opts[0].segments, None, f"edge between {na} and {nb}")]
    return opts

# ============================================================
# 7. TOOL DEFINITIONS  (seven verbs)
# ============================================================
TOOLS = ["vertex", "neighbors", "draw line", "intersect", "merge", "measure", "sort"]

TOOL_LABELS = {
    "vertex":    "Find Vertex",
    "neighbors": "Neighbors",
    "draw line": "Draw Line",
    "intersect": "Intersect",
    "merge":     "Merge",
    "measure":   "Measure",
    "sort":      "Sort",
}

INSTRUCTIONS = {
    "vertex": (
        "- **Select ONE Region** → select all vertices or pick a vertex with a given property: leftmost / rightmost, topmost / bottommost, vertex with the smallest / largest angle.\n"
        "- **Select TWO OR MORE Regions** → find their meeting vertex or vertices.\n"
        "- **Select the Frame** → a frame corner"
    ),
    "neighbors": (
        "- **Select ONE Vertex** → find all regions that meet at that vertex.\n"
        "- **Select ONE Edge** → find the diagram regions bordering that edge. \n"
        "- **Select ONE Region** → find all neighboring regions that share an edge. \n"
        "- **Select ONE Region + ONE Vertex** → draw a cycle starting at that vertex (clockwise / counter-clockwise) and return a sequence of neighbors in order."
    ),
    "draw line": (
        "- **Select TWO Vertices** → draw a line segment or a full line that passes through both vertices. \n"
        "- **Select ONE Vertex** → draw a ray starting at that vertex that extends up / down / left /right.\n"
        "- **Select ONE Edge** → draw a line that extends the edge in both directions.\n"
    ),
    "intersect": (
        "- **Select ONE Line** → return all regions this line crosses.\n"
        "- **Select TWO Lines** → return whether or not the two lines cross."
    ),
    "merge": (
        "- **Select TWO Regions** → merge the two regions into a new region. The regions must share a border. \n"
    ),
    "measure": (
        "- **Select TWO Vertices** → return the distance between the two vertices.\n"
        "- **Select TWO Regions** → return the distance between their closest points.\n"
        "- **Select ONE Drawn Line** → return the length of the drawn line.\n"
        "- **Select ONE Angle** → return the value of the selected angle.\n"
        "- **Select ONE Region** → return the area or edge count of the selected region.\n"
        "- **Select FRAME** → return the region count for the diagram.\n"
        "- **Select THREE Vertices** → return the orientation of the cycle in selection order.\n"
    ),
    "sort": (
        "**All Objects are Sorted smallest → largest **"
        "- **Select TWO OR MORE Angles** → order the selected angles by size.\n"
        "- **Select TWO OR MORE Regions** → order the regions by area.\n"
        "- **Select TWO OR MORE Vertices** → order by left→right, bottom→top, or distance from the vertex that was selected first.\n"
    ),
}

def validate(tool, modes):
    s = sel_sig()
    nR, nV, nE, nA, nF = (len(s["regions"]), len(s["vertices"]),
                          len(s["edges"]), len(s["angles"]), len(s["frame"]))

    if tool == "vertex":
        # Vertices already sitting in the buffer — kept there from earlier
        # Vertex-tool calls (see finish_vertex) — don't block a new call.
        # Only the FRAME/region picks you just made actually drive this run.
        if nF >= 1:                        return (True, "")
        if nR == 1:                        return (True, "")
        if nR >= 2:                        return (True, "")
        return (False, "Select 1 region, the FRAME, or 2+ regions. "
                        "(Vertices already in your buffer are kept.)")

    if tool == "neighbors":
        # one POINT (and nothing else) → regions meeting at that point
        if nV == 1 and s["n"] == 1:                    return (True, "")
        # one EDGE (and nothing else) → regions on either side of it
        if nE == 1 and s["n"] == 1:                    return (True, "")
        # a single region → its edge / vertex neighbors
        if nR == 1 and s["n"] == 1:                    return (True, "")
        # a region + one of its corners → walking order
        if nR == 1 and nV == 1 and s["n"] == 2:        return (True, "")
        return (False, "Select 1 vertex, 1 edge, 1 region, or 1 region + 1 of its corners.")

    if tool == "draw line":
        if modes.get("style") == "ray":
            return (s["n"] == 1 and nV == 1, "Ray needs exactly 1 vertex.")
        ok = (s["n"] == 2 and nV == 2) or (s["n"] == 1 and nE == 1)
        return (ok, "Need 2 vertices, or 1 edge, or 1 vertex + ray.")

    if tool == "intersect":
        return (len(st.session_state.lines) > 0, "Draw a line first.")

    if tool == "merge":
        return (s["n"] == 2 and nR == 2, "Need exactly 2 regions.")

    if tool == "measure":
        w = modes.get("what")
        if not w: return (False, "Pick what to measure.")
        if w == "distance":
            if nV == 2 and s["n"] == 2:        return (True, "")   # two points
            if nR == 2 and s["n"] == 2:        return (True, "")   # two regions
            return (False, "Select two vertices or two regions.")
        if w == "length":
            if modes.get("line") is not None:  return (True, "")   # a drawn segment
            return (False, "Draw a segment first, then pick it here.")
        if w == "angle":
            return (nA == 1 and s["n"] == 1, "Select ONE angle.")
        if w in ("area", "sides"):
            return (nR == 1 and s["n"] == 1, "Select ONE region.")
        if w == "regions":
            return (nF == 1 and s["n"] == 1, "Select FRAME.")
        if w == "orientation":
            return (nV == 3 and s["n"] == 3,
                    "Select exactly three vertices in cycle order.")
        return (False, "")

    if tool == "sort":
        by = modes.get("by")
        if not by: return (False, "Pick how to order them.")
        if by == "angle":
            return (nA >= 2 and nA == s["n"],
                    "Select 2+ saved angles.")
        if by == "area":
            return (nR >= 2 and nR == s["n"], "Select 2+ regions.")
        if by in ("left_right", "bottom_top"):
            return (nV >= 2 and nV == s["n"], "Select 2+ vertices.")
        if by == "distance":
            return (nV >= 3 and nV == s["n"],
                    "Select the reference vertex FIRST, then 2+ more vertices.")
        return (False, "")
    return (False, "")

# ============================================================
# 8. EXECUTION + PROGRAM TRACE
# ============================================================
def add_program(line): st.session_state.program.append(line)
def add_log(text):     st.session_state.log.append(text)

def _tool_output(value):
    if isinstance(value, (list, tuple, set)):
        return {"type": "list", "items": [_tool_output(v) for v in value]}
    if value is None:
        return {"type": "none", "value": None}
    if isinstance(value, bool):
        return {"type": "boolean", "value": value}
    if isinstance(value, (int, float)):
        return {"type": "number", "value": value}
    if isinstance(value, str):
        return {"type": "text", "value": value}
    if is_vertex(value):
        return {"type": "annotation", "kind": "point", "label": code_name(value)}
    if is_angle(value):
        return {
            "type": "annotation",
            "kind": "angle",
            "label": angle_name(value),
            "region": value.face.letter,
        }
    if is_edgesel(value):
        return {
            "type": "annotation",
            "kind": "edge",
            "label": edge_name(value),
            "description": value.text,
        }
    if is_region(value):
        return {
            "type": "region",
            "label": value.letter if getattr(value, "bounded", True) else "Outside",
        }
    return {"type": "text", "value": describe(value)}

def infer_call_type(output):
    if isinstance(output, dict) and output.get("type") == "annotation":
        return "annotation"
    return "analysis"

def record_tool_call(tool, function, input_text, output, output_text=None, call_type=None):
    calls = st.session_state.setdefault("tool_calls", [])
    calls.append({
        "order": len(calls) + 1,
        "tool": tool,
        "function": function,
        "call_type": call_type or infer_call_type(output),
        "input": input_text,
        "output": output,
        "output_text": output_text if output_text is not None else describe(output),
        "timestamp": _ts(),
        "survey_elapsed_seconds": survey_elapsed_seconds(),
    })

# ---- single-step UNDO -------------------------------------------------------
_UNDO_KEYS = ["selection", "selection_meta", "annotations", "lines", "angles", "named_edges",
              "unions", "union_consumed", "point_names", "counters",
              "program", "log", "tool_calls"]

def push_undo():
    """Snapshot the tracked state BEFORE a mutating action so it can be undone."""
    snap = {}
    for k in _UNDO_KEYS:
        val = st.session_state.get(k)
        if isinstance(val, dict):
            snap[k] = dict(val)
        elif isinstance(val, list):
            snap[k] = list(val)
        elif isinstance(val, set):
            snap[k] = set(val)
        else:
            snap[k] = val
    st.session_state.undo_stack.append(snap)
    if len(st.session_state.undo_stack) > 50:
        st.session_state.undo_stack.pop(0)

def undo_last():
    if not st.session_state.undo_stack:
        return
    snap = st.session_state.undo_stack.pop()
    for k, v in snap.items():
        st.session_state[k] = v
    st.session_state.click_targets = None
    st.session_state.pending_angle_vertex = None
    st.rerun()

def visualize_result(result):
    if is_angle(result) or is_edgesel(result):
        return
    if isinstance(result, (list, tuple, set)):
        for r in result:
            visualize_result(r)
        return
    if result is None or isinstance(result, (bool, int, float, str)):
        return
    if is_vertex(result):
        point_name(result)
    elif is_region(result) and getattr(result, "bounded", False):
        st.session_state.annotations.append(
            {"kind": "region", "obj": result, "color": GRAY_SOLID})

def finish(tool, call_str, result, assign_prefix="r", visualize=True):
    if visualize:
        visualize_result(result)
    if assign_prefix:
        var = next_name(assign_prefix)
        add_program(f"{var} = {call_str}")
    else:
        add_program(call_str)
    output_text = answer_like_text(result)
    add_log(f"`{call_str}` → **{output_text}**")
    record_tool_call(tool, call_str.split("(", 1)[0], call_str, _tool_output(result), output_text)
    if st.session_state.get("practice_step") == "tools":
        if tool == "neighbors" and 'neighbors(A, "edge")' in call_str:
            st.session_state.practice_neighbors_done = True
            st.session_state.active_tool = "merge"
            st.session_state.selection_filter = "Region"
    clear_selection()
    st.rerun()

def finish_vertex(call_str, result, assign_prefix="v"):
    """
    Special-cased finish for the VERTEX tool only.

    Every other tool clears the whole selection buffer when it finishes, so
    the next pick starts from scratch. Vertex is the exception: many survey
    questions need several points held at once (to measure between them,
    sort them, draw a line through them...), so here we:
        1. drop ONLY the regions / frame that were the INPUT to this call —
           they're consumed, the same way they always were,
        2. keep any vertices already sitting in the buffer from earlier
           Vertex-tool calls (this is what was being wiped before),
        3. add the newly computed vertex (or vertices, when there are
           multiple meeting points) into the buffer too — skipping anything
           already there, so re-running on the same selection doesn't pile
           up duplicate buffer entries.
    Retained vertices remain until they are removed with their per-item ✕
    controls or the survey advances to another question.
    """
    keep_sel, keep_meta, seen_ids = [], [], set()
    for o, m in zip(st.session_state.selection, st.session_state.selection_meta):
        if o == "frame" or is_region(o):
            continue                       # this call's input — consumed
        keep_sel.append(o)
        keep_meta.append(m)
        if is_vertex(o):
            seen_ids.add(id(o))
    st.session_state.selection = keep_sel
    st.session_state.selection_meta = keep_meta

    new_pts = result if isinstance(result, list) else ([result] if result is not None else [])
    for v in new_pts:
        if is_vertex(v) and id(v) not in seen_ids:
            seen_ids.add(id(v))
            _name, meta = point_name_with_meta(v)
            add_to_selection(v, meta)

    if assign_prefix:
        var = next_name("r")
        add_program(f"{var} = {call_str}")
    else:
        add_program(call_str)
    output_text = answer_like_text(result)
    add_log(f"`{call_str}` → **{output_text}**")
    record_tool_call("vertex", "vertex", call_str, _tool_output(result), output_text)
    if st.session_state.get("practice_step") == "tools":
        if 'which="rightmost"' in call_str and "A" in call_str:
            st.session_state.practice_rightmost_vertex_done = True
        if "on_frame=False" in call_str and "A" in call_str and "D" in call_str and "E" in call_str:
            st.session_state.practice_meeting_vertex_done = True
            st.session_state.selection = []
            st.session_state.selection_meta = []
            st.session_state.active_tool = "neighbors"
            st.session_state.selection_filter = "Region"
    st.session_state.click_targets = None
    st.session_state.pending_angle_vertex = None
    st.rerun()

# ---- ranking display (shared by the Sort tool) ------------------------------
def _rank_value(it, by, ref):
    if by == "distance":   return map_helpers.dist(it, ref)
    if by == "left_right": return map_helpers.x_of(it)
    if by == "bottom_top": return map_helpers.y_of(it)
    if by == "area":       return map_helpers.area(it)
    if by == "angle":
        if is_angle(it):
            return map_helpers.angle_at(it.vertex, it.face) * 180.0 / math.pi
        return map_helpers.angle_at(it, ref) * 180.0 / math.pi
    return 0

def _rank_fmt(by, v):
    return f"{v:.3f}"

def ranking_finish(call_str, result, by, ref):
    add_program(call_str + "   # smallest → largest")
    ordered = answer_like_text(result)
    add_log(f"`{call_str}` → **{ordered}**")
    record_tool_call(
        "sort",
        "sort",
        call_str,
        {
            "type": "list",
            "items": [code_name(it) for it in result],
            "order": "smallest_to_largest",
            "sort_by": by,
        },
        ordered,
        "analysis",
    )
    clear_selection()
    st.rerun()

def run_tool(tool, modes):
    sel = st.session_state.selection
    s = sel_sig()
    try:
        # ---- VERTEX --------------------------------------------------------
        if tool == "vertex":
            if s["frame"]:
                which = modes["which"]
                result = T.vertex("frame", which=which)
                finish_vertex(f'vertex("frame", which="{which}")', result,
                               "v" if not isinstance(result, list) else "r")
            elif len(s["regions"]) >= 2:
                onf = modes["on_frame"]
                result = T.vertex(*s["regions"], on_frame=onf)
                args = ", ".join(o.letter for o in s["regions"])
                finish_vertex(f"vertex({args}, on_frame={onf})", result,
                               "v" if not isinstance(result, list) else "r")
            else:
                reg = s["regions"][0]
                which = modes["which"]
                result = T.vertex(reg, which=which)
                call_str = f'vertex({reg.letter}, which="{which}")'
                finish_vertex(call_str, result,
                              "v" if not isinstance(result, list) else "r")

        # ---- NEIGHBORS -----------------------------------------------------
        elif tool == "neighbors":
            # Several EDGES → all labeled/bounded regions inside the frame on
            # either side of each edge. Frame edges therefore return only
            # their bounded side. If a side has been consumed by a union,
            # expose the union rather than its hidden constituent region.
            if s["edges"] and not s["regions"] and not s["vertices"]:
                seen, result, names = set(), [], []
                consumed_to_union = {
                    id(face): union["face"]
                    for union in st.session_state.unions
                    for face in union["pair"]
                }
                for es in s["edges"]:
                    for seg in es.segments:
                        for face in T.neighbors(seg):
                            face = consumed_to_union.get(id(face), face)
                            if id(face) not in seen:
                                seen.add(id(face))
                                result.append(face)
                    names.append(edge_name(es) or "edge")
                call = (f"neighbors([{', '.join(names)}])"
                        if len(names) > 1 else f"neighbors({names[0]})")
                finish(tool, call, result)

            # several POINTS → union of the regions meeting at any of them
            elif s["vertices"] and not s["regions"]:
                seen, result = set(), []
                for v in s["vertices"]:
                    for face in T.neighbors(v):
                        if id(face) not in seen:
                            seen.add(id(face))
                            result.append(face)
                names = [code_name(v) for v in s["vertices"]]
                call = (f"neighbors([{', '.join(names)}])"
                        if len(names) > 1 else f"neighbors({names[0]})")
                finish(tool, call, result)

            elif s["regions"] and s["vertices"]:
                reg, vtx = s["regions"][0], s["vertices"][0]
                ccw = modes.get("ccw", True)
                result = T.neighbors(reg, "ordered", start=vtx, go_counterclockwise=ccw)
                finish(tool, f'neighbors({reg.letter}, "ordered", start={code_name(vtx)}, '
                             f"go_counterclockwise={ccw})", result)

            else:
                reg = s["regions"][0]
                kind = modes["kind"]
                result = T.neighbors(reg, kind)
                finish(tool, f'neighbors({reg.letter}, "{kind}")', result)

        # ---- DRAW LINE -----------------------------------------------------
        elif tool == "draw line":
            style = modes["style"]
            if style == "ray":
                d = modes["ray_direction"]
                line = T.draw(sel[0], d)
                call = f'draw({code_name(sel[0])}, "{d}")'
            elif s["edges"]:
                va, vb = edgesel_endpoints(s["edges"][0])
                kind = "full" if style == "full line" else "segment"
                line = T.draw(va, vb, kind=kind)
                call = f'draw({code_name(va)}, {code_name(vb)}, kind="{kind}")  # along {code_name(s["edges"][0])}'
            else:
                kind = "full" if style == "full line" else "segment"
                line = T.draw(sel[0], sel[1], kind=kind)
                call = f'draw({code_name(sel[0])}, {code_name(sel[1])}, kind="{kind}")'
            name = next_name("L")
            st.session_state.lines.append((name, line))
            st.session_state.annotations.append({"kind": "line", "line": line, "label": name})
            add_program(f"{name} = {call}")
            add_log(f"`{name} = {call}` → drawn")
            record_tool_call(
                tool,
                "draw",
                call,
                {"type": "annotation", "kind": "line", "label": name},
                name,
                "annotation",
            )
            clear_selection()
            st.rerun()

        # ---- INTERSECT -----------------------------------------------------
        elif tool == "intersect":
            lname, line = modes["line"]
            if modes["target"] == "faces":
                result = T.intersect(line, "faces")
                finish(tool, f'intersect({lname}, "faces")', result, visualize=False)
            else:
                tname, tline = modes["target"]
                result = T.intersect(line, tline)
                finish(tool, f"intersect({lname}, {tname})", result, visualize=False)

        # ---- MERGE ---------------------------------------------------------
        elif tool == "merge":
            fa, fb = s["regions"][0], s["regions"][1]
            fu = T.merge(fa, fb)
            uname = next_name("U")
            fu.letter = uname
            lp, _d = Graph.LetterPointFace(fu)
            st.session_state.unions.append(
                {"name": uname, "face": fu, "pair": (fa, fb),
                 "label_xy": DrawGraph.V2P(lp)})
            st.session_state.union_consumed += [fa, fb]
            add_program(f"{uname} = merge({fa.letter}, {fb.letter})")
            add_log(f"`{uname} = merge({fa.letter}, {fb.letter})` → merged region **{uname}**")
            record_tool_call(
                tool,
                "merge",
                f"merge({fa.letter}, {fb.letter})",
                {
                    "type": "annotation",
                    "kind": "union",
                    "label": uname,
                    "regions": [fa.letter, fb.letter],
                },
                uname,
                "annotation",
            )
            if st.session_state.get("practice_step") == "tools" and {fa.letter, fb.letter} == {"A", "E"}:
                st.session_state.practice_merge_done = True
            clear_selection()
            st.rerun()

        # ---- MEASURE (one thing → one number) ------------------------------
        elif tool == "measure":
            w = modes["what"]

            if w == "distance":
                if len(s["regions"]) == 2 and s["n"] == 2:
                    fa, fb = s["regions"][0], s["regions"][1]
                    val = T.measure(fa, fb, what="distance")
                    finish(tool, f'measure({fa.letter}, {fb.letter}, what="distance")',
                           round(val, 4))
                elif s["vertices"] and len(s["vertices"]) >= 2:
                    p, q = s["vertices"][0], s["vertices"][1]
                    val = T.measure(p, q, what="distance")
                    finish(tool, f'measure({code_name(p)}, {code_name(q)}, what="distance")',
                           round(val, 4))

            elif w == "length":
                lname, line = modes["line"]
                val = T.measure(line, what="length")
                finish(tool, f'measure({lname}, what="length")', round(val, 4),
                       visualize=False)

            elif w == "angle":
                a = s["angles"][0]
                val = T.measure(a.vertex, a.face, what="angle")
                aname = angle_name(a)
                call_str = f'measure({aname}, what="angle")'
                var = next_name("r")
                add_program(f"{var} = {call_str}")
                output_text = f"{round(val, 2)}"
                add_log(f"`{call_str}` → **{output_text}**")
                record_tool_call(
                    tool,
                    "measure",
                    call_str,
                    {"type": "number", "value": round(val, 2), "unit": "degrees"},
                    output_text,
                    "analysis",
                )
                clear_selection()
                st.rerun()

            elif w == "regions":
                val = T.measure("frame", what="regions")
                finish(tool, 'measure("frame", what="regions")', val,
                       visualize=False)

            elif w == "orientation":
                va, vb, vc = s["vertices"]
                call_str = (f'measure({code_name(va)}, {code_name(vb)}, '
                            f'{code_name(vc)}, what="orientation")')
                val = T.measure(va, vb, vc, what="orientation")
                finish(tool, call_str, val, visualize=False)

            else:  # area, sides
                reg = s["regions"][0]
                val = T.measure(reg, what=w)
                finish(tool, f'measure({reg.letter}, what="{w}")', val)

        # ---- SORT (several things → ordered) --------------------------------
        elif tool == "sort":
            by = modes["by"]

            if by == "angle":
                angles = list(s["angles"])
                result = T.sort(angles, by="angle")
                arg = ", ".join(angle_name(a) for a in angles)
                ranking_finish(f'sort([{arg}], by="angle")', result, "angle", None)

            elif by == "area":
                regs = list(s["regions"])
                result = T.sort(regs, by="area")
                arg = ", ".join(o.letter for o in regs)
                ranking_finish(f'sort([{arg}], by="area")', result, "area", None)

            elif by in ("left_right", "bottom_top"):
                pts = list(s["vertices"])
                result = T.sort(pts, by=by)
                arg = ", ".join(code_name(o) for o in pts)
                ranking_finish(f'sort([{arg}], by="{by}")', result, by, None)

            else:  # distance from the first-selected point
                ref, rest = s["vertices"][0], s["vertices"][1:]
                result = T.sort(rest, by="distance", reference=ref)
                arg = ", ".join(code_name(o) for o in rest)
                ranking_finish(
                    f'sort([{arg}], by="distance", reference={code_name(ref)})',
                    result, "distance", ref)

    except Exception as ex:
        add_log(f"❌ **{tool}** failed: {ex}")
        clear_selection()
        st.rerun()

def _ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def survey_answer_key(question):
    return f"answer_{st.session_state.survey_question_index}_{question.get('question_id', '')}"

def current_trial_record(question, answer, is_correct=None):
    question_started_time = st.session_state.get("question_started_time")
    response_time_seconds = None
    if question_started_time is not None:
        response_time_seconds = round(time.time() - question_started_time, 3)
    return {
        "participant_id": PARTICIPANT_ID,
        "survey_version": SURVEY_VERSION,
        "question_index": st.session_state.survey_question_index,
        "question": question,
        "answer": answer,
        "scratch_pad": st.session_state.get("scratch_pad", ""),
        "correct_answer": question.get("answer", ""),
        "is_correct": is_correct,
        "question_started_at": st.session_state.get("question_started_at"),
        "survey_elapsed_seconds": survey_elapsed_seconds(),
        "response_time_seconds": response_time_seconds,
        "submitted_at": _ts(),
        "tool_calls": list(st.session_state.get("tool_calls", [])),
        "selection_events": list(st.session_state.get("selection_events", [])),
        "program": list(st.session_state.program),
        "output_log": list(st.session_state.log),
    }

def result_file_path():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    return participant_result_path(PARTICIPANT_ID)

def save_survey_results():
    payload = {
        "participant_id": PARTICIPANT_ID,
        "survey_version": SURVEY_VERSION,
        "dataset_path": DATASET_PATH,
        "saved_at": _ts(),
        "question_count": len(QUESTION_BANK),
        "survey_question_index": st.session_state.get("survey_question_index", 0),
        "max_confirmed_question_index": st.session_state.get(
            "max_confirmed_question_index", -1
        ),
        "survey_completed": st.session_state.get("survey_completed", False),
        "questions": QUESTION_BANK,
        "responses": st.session_state.get("survey_responses", {}),
    }
    path = result_file_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
    st.session_state.last_result_path = path
    return path

if st.session_state.survey_completed:
    st.success("Survey complete. Thank you.")
    if st.session_state.last_result_path:
        st.caption(f"Saved result file: {st.session_state.last_result_path}")
    st.stop()

# ============================================================
# 9. LAYOUT  (LEFT: tools/selection/run | MIDDLE: diagram+selection+saved |
#             RIGHT: quick actions + scratch pad + output)
# ============================================================
question_number = st.session_state.survey_question_index + 1
top_left, top_right = st.columns([3, 1], gap="small")
with top_left:
    if IS_PRACTICE:
        st.caption("Practice")
    else:
        st.caption(f"Question {question_number} of {len(QUESTION_BANK)}")
    raw_question_text = (
        practice_question_text_for_step(PRACTICE_STEP)
        if IS_PRACTICE
        else str(QUESTION.get("question_text", ""))
    )
    question_text = html.escape(raw_question_text)
    question_text = "<br><br>".join(
        paragraph.replace("\n", " ").strip()
        for paragraph in re.split(r"\n\s*\n", question_text)
        if paragraph.strip()
    )
    st.markdown(
        f'<div style="font-size:18px; font-weight:600; line-height:1.35; '
        f'margin:0.1rem 0 0.9rem 0;">{question_text}</div>',
        unsafe_allow_html=True,
    )
with top_right:
    if IS_PRACTICE:
        st.caption("Timer starts after practice.")
    elif st.session_state.timer_hidden:
        if st.button("Show timer", use_container_width=True):
            st.session_state.timer_hidden = False
            st.rerun()
    else:
        timer_col, hide_timer_col = st.columns([3, 1], vertical_alignment="center")
        with timer_col:
            render_timer()
        with hide_timer_col:
            if st.button("Hide", help="Hide timer", use_container_width=True):
                st.session_state.timer_hidden = True
                st.rerun()

answer_panel, action_panel = st.columns([8, 3], gap="small")

with answer_panel:
    if IS_PRACTICE and PRACTICE_STEP == "select":
        selected_types = practice_selected_entity_types()
        st.markdown(
            '<div style="border:1px solid #d1d5db; border-radius:0.5rem; '
            'padding:0.85rem 1rem; margin-bottom:0.8rem;">'
            '<div style="font-weight:650; margin-bottom:0.35rem;">Select each kind of object once:</div>'
            f'{practice_selection_checklist_html(selected_types)}'
            '</div>',
            unsafe_allow_html=True,
        )
        ready = all(label in selected_types for label in PRACTICE_REQUIRED_SELECTIONS)
        if not ready:
            st.info("Use the Selection choices below, then click the diagram to select each object type.")
        if st.button("Continue", type="primary", disabled=not ready):
            clear_selection()
            st.session_state.practice_step = "tools"
            st.session_state.active_tool = "vertex"
            st.session_state.selection_filter = "Region"
            st.session_state.practice_rightmost_vertex_done = False
            st.session_state.practice_meeting_vertex_done = False
            st.session_state.practice_neighbors_done = False
            st.session_state.practice_merge_done = False
            st.rerun()
    else:
        practice_rightmost_done = (
            IS_PRACTICE
            and PRACTICE_STEP == "tools"
            and practice_rightmost_vertex_done()
        )
        practice_meeting_done = (
            IS_PRACTICE
            and PRACTICE_STEP == "tools"
            and practice_meeting_vertex_done()
        )
        practice_neighbor_done = (
            IS_PRACTICE
            and PRACTICE_STEP == "tools"
            and practice_neighbors_done()
        )
        practice_merge_complete = (
            IS_PRACTICE
            and PRACTICE_STEP == "tools"
            and practice_merge_done()
        )
        if IS_PRACTICE and PRACTICE_STEP == "tools":
            if practice_merge_complete:
                st.success("Very good — now you know how to use Find Vertex, Neighbors, and Merge.")
                st.markdown(PRACTICE_TOOL_FINAL_TEXT)
                if st.button("Start Survey", type="primary"):
                    st.session_state.tutorial_completed = True
                    st.query_params["tutorial_done"] = "1"
                    st.session_state.answer_feedback = None
                    st.session_state.scratch_pad = ""
                    st.session_state.survey_started_at = time.time()
                    st.rerun()
            elif practice_neighbor_done:
                st.success("Very good — now you know how to use Neighbors.")
                st.markdown(PRACTICE_MERGE_GUIDE_TEXT)
            elif practice_meeting_done:
                st.success("Very good — now you know two ways to label vertices with Find Vertex.")
                st.markdown(PRACTICE_NEIGHBORS_GUIDE_TEXT)
            elif practice_rightmost_done:
                st.success("Great — now you know how to label a vertex using a tool.")
                st.markdown(PRACTICE_TOOL_AFTER_SUCCESS_TEXT)
            else:
                st.markdown(PRACTICE_TOOL_GUIDE_TEXT)
                st.info("After you click RUN for the rightmost vertex of Region A, the next tool practice step will appear.")
        if IS_PRACTICE and PRACTICE_STEP == "tools":
            pass
        else:
            feedback = st.session_state.get("answer_feedback")
            feedback_for_current = feedback and feedback.get("question_index") == st.session_state.survey_question_index
            if feedback_for_current:
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
                continue_label = "Finish Survey" if feedback.get("is_last_question") else "Continue"
                if st.button(continue_label, type="primary"):
                    st.session_state.max_confirmed_question_index = max(
                        st.session_state.max_confirmed_question_index,
                        st.session_state.survey_question_index,
                    )
                    st.session_state.answer_feedback = None
                    if feedback.get("is_last_question"):
                        st.session_state.survey_completed = True
                    else:
                        st.session_state.survey_question_index += 1
                    save_survey_results()
                    st.rerun()
            else:
                with st.form("survey_answer_form", clear_on_submit=False):
                    key = survey_answer_key(QUESTION)
                    existing = st.session_state.survey_responses.get(QUESTION.get("question_id", ""), {}).get("answer", "")
                    if normalized_answer_type(QUESTION) == "two_choice":
                        options = get_two_choice_options(QUESTION)
                        current_index = options.index(existing) if existing in options else None
                        answer_value = st.radio("Answer:", options, index=current_index, horizontal=True, key=f"{key}_choice")
                    else:
                        answer_col, _ = st.columns([3, 2])
                        with answer_col:
                            answer_value = st.text_area(
                                "Answer:",
                                value=existing,
                                height=68,
                                placeholder=QUESTION.get("answer_placeholder", ""),
                                key=f"{key}_area",
                            )
                            answer_hint = answer_hint_for(QUESTION)
                            if answer_hint:
                                safe_answer_hint = html.escape(answer_hint)
                                st.markdown(
                                    '<div style="font-size:0.9rem; line-height:1.4; color:#4b5563; '
                                    'background:#f3f4f6; border-left:3px solid #9ca3af; '
                                    'padding:0.3rem 0.5rem; margin-top:-0.2rem; margin-bottom:0.5rem; '
                                    'border-radius:0 0.3rem 0.3rem 0;">'
                                    f'{safe_answer_hint}</div>',
                                    unsafe_allow_html=True,
                                )
                    is_last_question = st.session_state.survey_question_index >= len(QUESTION_BANK) - 1
                    button_label = "Start Survey" if IS_PRACTICE else "Confirm Answer"
                    submitted = st.form_submit_button(button_label, type="primary")
                    if submitted:
                        cleaned = (answer_value or "").strip()
                        if not cleaned:
                            st.error("Please enter an answer before continuing.")
                        elif IS_PRACTICE:
                            st.session_state.tutorial_completed = True
                            st.query_params["tutorial_done"] = "1"
                            st.session_state.answer_feedback = None
                            st.session_state.scratch_pad = ""
                            st.session_state.survey_started_at = time.time()
                            st.rerun()
                        else:
                            qid = question_id_for(QUESTION, st.session_state.survey_question_index)
                            is_correct = answer_is_correct(QUESTION, cleaned)
                            st.session_state.survey_responses[qid] = current_trial_record(QUESTION, cleaned, is_correct)
                            path = save_survey_results()
                            st.session_state.scratch_pad = ""
                            st.session_state.answer_feedback = {
                                "question_index": st.session_state.survey_question_index,
                                "question_id": qid,
                                "answer": cleaned,
                                "correct_answer": QUESTION.get("answer", ""),
                                "correct_answer_display": format_answer_for_feedback(QUESTION),
                                "is_correct": is_correct,
                                "is_last_question": is_last_question,
                            }
                            st.rerun()

    left_workspace = st.container()

with action_panel:
    st.markdown(
        '<div style="font-size:1.25rem; font-weight:600; margin:0 0 0.25rem 0;">Help</div>',
        unsafe_allow_html=True,
    )
    st.session_state.setdefault("definitions_open", False)

    definitions_open = st.session_state["definitions_open"]
    if st.button(("▾ Definitions" if definitions_open else "▸ Definitions"), key="toggle_definitions", use_container_width=True):
        st.session_state["definitions_open"] = not definitions_open
        st.rerun()
    if st.session_state["definitions_open"]:
        st.markdown(DEFINITIONS_TEXT)

    st.markdown(
        '<div style="font-size:1.25rem; font-weight:600; margin:0.4rem 0 0.25rem 0;">Quick actions</div>',
        unsafe_allow_html=True,
    )
    qcols = st.columns(2)
    if qcols[0].button("↩ Undo", help="Undo last move", use_container_width=True,
                       disabled=not st.session_state.undo_stack):
        undo_last()
    if qcols[1].button("Clear all", use_container_width=True):
        clear_selection()
        record_selection_event("clear_all")
        for k in ["annotations", "lines", "angles", "named_edges", "unions",
                  "union_consumed", "undo_stack", "program", "log", "tool_calls"]:
            st.session_state[k] = []
        st.session_state.pending_angle_vertex = None
        st.session_state.pending_edge_options = []
        st.session_state.click_targets = None
        st.session_state.point_names = {}
        st.session_state.counters = {"v": 1, "L": 1, "U": 1, "r": 1, "a": 1, "e": 1}
        st.rerun()

    right_workspace = st.container()

with left_workspace:
    col_ctrl, col_map = st.columns([3, 5], gap="small")
col_io = right_workspace

# ----------------------------------------------------------------------------
# LEFT PANEL — tools + active tool config + RUN + selection
# ----------------------------------------------------------------------------
with col_ctrl:
    SHOW_TOOLS = not (IS_PRACTICE and PRACTICE_STEP == "select")
    if not SHOW_TOOLS:
        st.session_state.active_tool = None

    st.markdown(
        """
        <style>
        div.stButton > button {
            font-size: 14px;
            font-weight: 600;
            border-radius: 5px;
            min-height: 2.2rem;
            padding: 0.25rem 0.55rem;
            justify-content: flex-start;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if SHOW_TOOLS:
        st.markdown(
            '<div style="font-size:1.25rem; font-weight:600; margin:0 0 0.35rem 0;">Tools</div>',
            unsafe_allow_html=True,
        )

    # The active tool's button gets a soft mint-green shade (no checkmark).
    # Streamlit tags each keyed button's wrapper with class "st-key-<key>",
    # so we inject one scoped CSS rule targeting only the active tool's button.
    _active_tool = st.session_state.active_tool if SHOW_TOOLS else None
    if _active_tool:
        _active_key = f"tool_{_active_tool.replace(' ', '_')}"
        st.markdown(f"""
        <style>
        div[class*="st-key-{_active_key}"] button {{
            background-color: #e3f9ea;
            border-color: #8fd4a8;
            color: #1e5631;
        }}
        div[class*="st-key-{_active_key}"] button:hover {{
            background-color: #d2f2de;
            border-color: #6fc593;
            color: #1e5631;
        }}
        div[class*="st-key-{_active_key}"] button:focus:not(:active) {{
            border-color: #6fc593;
            color: #1e5631;
        }}
        </style>
        """, unsafe_allow_html=True)

    if SHOW_TOOLS:
        st.markdown(
            """
            <style>
            .st-key-tool_button_grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 0.3rem 0.65rem;
            }
            .st-key-tool_button_grid > div[data-testid="stElementContainer"] {
                margin: 0;
                width: 100% !important;
            }
            .st-key-tool_button_grid div[data-testid="stButton"] {
                width: 100% !important;
            }
            div[data-testid="stColumn"]:has(.st-key-tool_button_grid) > div[data-testid="stVerticalBlock"] {
                gap: 0.45rem;
            }
            div[data-testid="stColumn"]:has(.st-key-tool_button_grid) [data-testid="stRadio"] {
                margin-top: -0.1rem;
                margin-bottom: -0.1rem;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        with st.container(key="tool_button_grid"):
            for t_name in TOOLS:
                display = TOOL_LABELS.get(t_name, t_name)
                if st.button(display, key=f"tool_{t_name.replace(' ', '_')}",
                             use_container_width=True):
                    st.session_state.active_tool = t_name
                    st.rerun()

    tool = st.session_state.active_tool if SHOW_TOOLS else None
    modes = {}

    if tool:
        display = TOOL_LABELS.get(tool, tool)
        st.markdown(f"**{display} settings**")

        s = sel_sig()

        if tool == "vertex":
            if s["frame"]:
                modes["which"] = st.radio(
                    "Which frame corner?",
                    ["all", "top_left", "top_right", "bottom_left", "bottom_right"],
                    horizontal=True, key="rad_vtx_frame")
            elif len(s["regions"]) >= 2:
                modes["on_frame"] = st.radio(
                    "Is the meeting vertex on the frame?", [False, True],
                    format_func=lambda b: "Yes" if b else "No",
                    horizontal=True, key="rad_vtx_onframe")
            else:
                vertex_options = [
                    "all", "leftmost", "rightmost", "topmost", "bottommost",
                    "sharpest", "widest",
                ]
                vertex_default_index = (
                    vertex_options.index("rightmost")
                    if IS_PRACTICE and PRACTICE_STEP == "tools"
                    else 0
                )
                modes["which"] = st.radio(
                    "Which corner?",
                    vertex_options,
                    index=vertex_default_index,
                    horizontal=True,
                    key="rad_vtx_corner")

        elif tool == "neighbors":
            if s["edges"] and not s["regions"] and not s["vertices"]:
                n = len(s["edges"])
                if n == 1:
                    st.caption("1 edge selected → diagram regions bordering that edge.")
                else:
                    st.caption("Select only 1 edge for this tool.")
            elif s["vertices"] and not s["regions"]:
                n = len(s["vertices"])
                if n == 1:
                    st.caption("1 vertex selected → every region meeting at that vertex.")
                else:
                    st.caption("Select only 1 vertex for this tool.")
            elif s["regions"] and s["vertices"]:
                modes["kind"] = "ordered"
                modes["ccw"] = st.radio(
                    "Walk direction", [True, False],
                    format_func=lambda b: "Counter-clockwise" if b else "Clockwise",
                    horizontal=True, key="rad_nbr_ccw")
                st.caption("Region + corner → the regions passed, in walking order.")
            elif s["regions"]:
                modes["kind"] = st.radio(
                    "Neighbor type", ["edge", "vertex"],
                    format_func=lambda k: "Share an edge" if k == "edge"
                    else "Touch only at a corner",
                    horizontal=True, key="rad_nbr_kind")

        elif tool == "draw line":
            modes["style"] = st.radio("Line style", ["segment", "full line", "ray"],
                                      horizontal=True, key="rad_style")
            if modes["style"] == "ray":
                modes["ray_direction"] = st.radio("Direction", ["up", "down", "left", "right"],
                                                  horizontal=True, key="rad_raydir")

        elif tool == "intersect":
            if st.session_state.lines:
                li = st.selectbox("Line to test", range(len(st.session_state.lines)),
                                  format_func=lambda i: st.session_state.lines[i][0],
                                  key="sel_line")
                modes["line"] = st.session_state.lines[li]
                choice = st.radio("Question", ["Which regions does it pass through?",
                                               "Does it cross another line?"],
                                  key="rad_intersect")
                if choice.startswith("Which"):
                    modes["target"] = "faces"
                else:
                    others = [j for j in range(len(st.session_state.lines)) if j != li]
                    if others:
                        lj = st.selectbox("Other line", others,
                                          format_func=lambda j: st.session_state.lines[j][0],
                                          key="sel_line2")
                        modes["target"] = st.session_state.lines[lj]
                    else:
                        st.warning("Draw a second line first.")
                        modes["target"] = None

        elif tool == "measure":
            modes["what"] = st.radio("Measure what?",
                                     ["distance", "length", "angle", "area", "sides", "regions",
                                      "orientation"],
                                     format_func=lambda value: {
                                         "sides": "edge count",
                                         "regions": "region count",
                                         "orientation": "cycle orientation",
                                     }.get(value, value),
                                     index=None, horizontal=True, key="rad_measure")
            if modes["what"] == "distance":
                if len(s["regions"]) == 2 and s["n"] == 2:
                    st.caption("Will measure the distance between the two selected regions.")
                elif len(s["vertices"]) >= 2:
                    st.caption("Will measure the distance between the two selected vertices.")
                else:
                    st.caption("Select two vertices or two regions.")
            elif modes["what"] == "length":
                segs = [(nm, ln) for nm, ln in st.session_state.lines
                        if ln.get("type") == "segment"]
                if segs:
                    idx = st.selectbox("Which drawn segment?", range(len(segs)),
                                       format_func=lambda i: segs[i][0],
                                       key="sel_len_line")
                    modes["line"] = segs[idx]
                else:
                    st.caption("Draw a segment first.")
            elif modes["what"] == "angle":
                if s["angles"]:
                    n = len(s["angles"])
                    if n == 1:
                        st.caption("1 angle selected — it will be measured.")
                    else:
                        st.caption("Select only 1 angle for this tool.")
                else:
                    st.caption("Use Select: Angle above the map, then click an angle arc.")
            elif modes["what"] == "regions":
                st.caption("Select FRAME to count all regions in the diagram.")
            elif modes["what"] == "orientation":
                st.caption("Select exactly three vertices in travel order: v₁, then v₂, then v₃.")

        elif tool == "sort":
            opts = []   # (label, internal_value)
            if len(s["angles"]) >= 2 and len(s["angles"]) == s["n"]:
                opts = [("By angle size", "angle")]
            elif len(s["regions"]) >= 2 and len(s["regions"]) == s["n"]:
                opts = [("By area", "area")]
            elif len(s["vertices"]) >= 2 and len(s["vertices"]) == s["n"]:
                opts = [("Left → right", "left_right"), ("Bottom → top", "bottom_top")]
                if len(s["vertices"]) >= 3:
                    opts.append(("Distance from the first vertex", "distance"))
            if opts:
                label2val = dict(opts)
                choice = st.radio("Order how?", [o[0] for o in opts], key="rad_sort")
                modes["by"] = label2val[choice]
            else:
                st.caption("Select 2+ angles, 2+ vertices, or 2+ regions.")

        # 'merge' has no modes.

        ready, msg = validate(tool, modes)
        if tool == "intersect" and modes.get("target") is None:
            ready = False
        if st.button("▶ RUN", type="primary", disabled=not ready,
                     use_container_width=True, key="run_active_tool"):
            push_undo()
            run_tool(tool, modes)

    # --- SELECTION ---
    st.markdown(
        '<div style="font-size:1.25rem; font-weight:600; margin:0.5rem 0 0.35rem 0;">Selection</div>',
        unsafe_allow_html=True,
    )
    st.session_state.setdefault("selection_filter", "Region")
    select_mode = st.radio(
        "Select from diagram:",
        ["Region", "Angle", "Vertex", "Edge"],
        horizontal=True,
        key="selection_filter",
        label_visibility="collapsed",
    )
    if not (IS_PRACTICE and PRACTICE_STEP == "select") and st.button("Select FRAME", use_container_width=True):
        push_undo()
        add_to_selection("frame")
        record_selection_event("select", "frame")
        st.rerun()

    if st.session_state.selection:
        st.markdown(_SELECTION_ROW_CSS, unsafe_allow_html=True)
        selection_list = (
            st.container(height=120)
            if len(st.session_state.selection) > 3
            else st.container()
        )
        with selection_list:
            for i, o in enumerate(st.session_state.selection):
                row = st.container(key=f"sel_row_{i}")
                with row:
                    st.markdown(f"- {describe(o)}")
                    if st.button("✕", key=f"sel_remove_{i}", help="Remove from selection"):
                        push_undo()
                        remove_selection_item(i)
                        st.rerun()

# ----------------------------------------------------------------------------
# MIDDLE PANEL — DIAGRAM + selection-building buttons + saved objects
# ----------------------------------------------------------------------------
diagram_panel = col_map.container(key="diagram_panel")
with diagram_panel:
    display_img = render().resize((DISPLAY_SIDE, DISPLAY_SIDE), Image.Resampling.LANCZOS)

    # encode the rendered map + serialize hover geometry, then hand both to the
    # custom canvas component. The browser only paints the selected object type.
    _buf = BytesIO()
    display_img.save(_buf, format="PNG")
    _img_b64 = base64.b64encode(_buf.getvalue()).decode()
    canvas_question_key = (
        f"map_click_{st.session_state.survey_question_index}_"
        f"{question_id_for(QUESTION, st.session_state.survey_question_index)}"
    )
    coords = geo_canvas(
        _img_b64,
        build_hover_shapes(),
        DISPLAY_SIDE,
        select_type=select_mode.lower(),
        key=canvas_question_key,
    )

    if tool:
        st.info(INSTRUCTIONS[tool])

    if coords is not None and coords != st.session_state.last_click:
        st.session_state.last_click = coords
        st.session_state.click_targets = None
        st.session_state.pending_angle_vertex = None
        st.session_state.pending_edge_options = []
        kind, obj = hit_test_by_mode(coords["x"], coords["y"], select_mode)
        if obj is not None:
            push_undo()
            if kind == "vertex":
                _name, meta = point_name_with_meta(obj)
                add_to_selection(obj, meta)
                record_selection_event("select", obj)
                st.rerun()
            elif kind == "region":
                add_to_selection(obj)
                record_selection_event("select", obj)
                st.rerun()
            elif kind == "angle":
                aname = next_name("a")
                angle_entry = (aname, obj)
                st.session_state.angles.append(angle_entry)
                ann = {"kind": "angle", "vertex": obj.vertex, "face": obj.face, "label": aname}
                st.session_state.annotations.append(ann)
                add_to_selection(obj, {"kind": "angle", "angle_entry": angle_entry,
                                       "annotation_ref": ann})
                record_selection_event("select", obj)
                st.rerun()
            elif kind == "edge":
                opts = edge_options(obj)
                if len(opts) == 1:
                    edge_obj = opts[0]
                    if edge_name(edge_obj) is None:
                        st.session_state.named_edges.append((next_name("e"), edge_obj))
                    if add_edge_to_selection(edge_obj):
                        record_selection_event("select", edge_obj)
                    st.rerun()
                elif len(opts) > 1:
                    st.session_state.pending_edge_options = opts
                    st.rerun()

    pending_edges = st.session_state.get("pending_edge_options", [])
    if pending_edges:
        st.caption("Which side of this edge?")
        for i, edge_obj in enumerate(pending_edges):
            if st.button(edge_obj.text, key=f"edge_side_{i}", use_container_width=True):
                push_undo()
                if edge_name(edge_obj) is None:
                    st.session_state.named_edges.append((next_name("e"), edge_obj))
                if add_edge_to_selection(edge_obj):
                    record_selection_event("select", edge_obj)
                st.session_state.pending_edge_options = []
                st.rerun()

    # --- SAVED OBJECTS BUFFER (angles + edges) ---
    # Unions are NOT listed here: a merged region is selected by clicking it
    # directly on the map (it shows up as "Region U").
    saved = []
    for aname, a_sel in st.session_state.angles:
        saved.append((f"Select {aname} (angle, Region {a_sel.face.letter})", a_sel))
    for ename, e_sel in st.session_state.named_edges:
        saved.append((f"Select {ename} ({e_sel.text})", e_sel))
    if saved:
        st.caption("Saved objects:")
        for i, (label, obj) in enumerate(saved):
            if st.button(label, key=f"saved_{i}", use_container_width=True):
                push_undo()
                if is_edgesel(obj):
                    if add_edge_to_selection(obj):
                        record_selection_event("select", obj)
                else:
                    add_to_selection(obj)
                    record_selection_event("select", obj)
                st.rerun()

# ----------------------------------------------------------------------------
# RIGHT PANEL — scratch pad and output log
# ----------------------------------------------------------------------------
with col_io:
    st.markdown(
        '<div style="font-size:1.25rem; font-weight:600; margin:0 0 0.35rem 0;">Sketch pad</div>',
        unsafe_allow_html=True,
    )
    st.text_area("scratch", key="scratch_pad", height=110,
                 label_visibility="collapsed",
                 placeholder="Use this space for notes or rough work. Your final answer must be entered in the answer box.")

    st.markdown(
        '<div style="font-size:1.25rem; font-weight:600; margin:0.45rem 0 0.25rem 0;">Output</div>',
        unsafe_allow_html=True,
    )
    if not st.session_state.log:
        st.caption("(results will appear here)")
    else:
        for entry in reversed(st.session_state.log[-25:]):
            st.markdown(entry)
