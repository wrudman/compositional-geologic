import os
import html
import hashlib
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

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:
    psycopg = None
    Jsonb = None

st.set_page_config(layout="wide")
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 1.25rem;
    }
    div[data-testid="stVerticalBlock"] {
        gap: 0.5rem;
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

DISPLAY_SIDE = 400          # compact enough to keep the initial workspace in one viewport
MATH_SCALE = 800.0
DEFAULT_PARTICIPANT_ID = "local_demo"
SURVEY_VERSION = "compositional_questions_v2_12_question_forms"
RESPONSE_SCHEMA_VERSION = "3.8"
CODE_VERSION = (
    os.environ.get("RENDER_GIT_COMMIT")
    or os.environ.get("GIT_COMMIT")
    or "local"
)
SURVEY_QUESTION_COUNT = 12
RESULTS_DIR = os.path.join(os.getcwd(), "survey_results")
DATABASE_URL = os.environ.get("DATABASE_URL")

# Two complementary forms drawn from the 24-question bank. Each contains
# 3 easy, 6 medium, and 3 hard diagrams and covers the major tool families.
SURVEY_FORM_QUESTION_IDS = {
    "A": {
        "15", "23", "24",                  # hard
        "12", "21", "11", "4", "25", "13",  # medium
        "9", "18", "26",                   # easy
    },
    "B": {
        "19", "2", "1",                    # hard
        "5", "16", "27", "20", "28", "14",  # medium
        "8", "10", "22",                   # easy
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

DEFINITIONS_TEXT = """
**Vertex:** a location where two or more edges meet.

**Edge:** a line segment that forms part of a region boundary.

**Region:** one enclosed area of the diagram.

**Angle:** the angle inside a region at a vertex, formed by the two edges that meet there.

**Frame:** the diagram's outer boundary.

**Outside of the frame:** the area outside the diagram frame.

**Clockwise:** movement around a circle in the top, right, bottom, left direction.

**Counterclockwise:** movement around a circle in the top, left, bottom, right direction.

**Union:** a combination of two neighboring regions treated as one larger region.
"""

PRACTICE_CORE_DEFINITIONS_TEXT = """
**Vertex:** a point where two or more edges meet.

**Edge:** a line segment that forms part of a region boundary.

**Region:** one enclosed area of the diagram.

**Angle:** the angle inside a region at a vertex, formed by the two edges that meet there.
"""

PRACTICE_DIRECTION_DEFINITIONS_TEXT = PRACTICE_CORE_DEFINITIONS_TEXT + """

**Clockwise:** movement around a circle in the top, right, bottom, left direction.

**Counterclockwise:** movement around a circle in the top, left, bottom, right direction.
"""

PRACTICE_FRAME_DEFINITIONS_TEXT = PRACTICE_CORE_DEFINITIONS_TEXT + """

**Frame:** the diagram's outer boundary.

**Outside of the frame:** the area outside the diagram frame.
"""

PRACTICE_TOOL_GUIDE_TEXT = """
We’ll start with **Find**, using its **Vertex** mode. Some questions may ask for a vertex with a property, such as the **rightmost vertex of a region**.

**Try this:** Select **Region A**, choose **rightmost**, then click **RUN**. The tool will label the vertex it finds.
"""

PRACTICE_NEIGHBORS_GUIDE_TEXT = """
Good. Next, practice **Neighbors**.

We now want to find all regions that share an edge with **Region A**.

Choose **Neighbors**, select **Region A**, keep **Neighbor type** as **Share an edge**, then click **RUN**.
"""

PRACTICE_ORDERED_NEIGHBORS_GUIDE_TEXT = """
Very good. Neighbors can also list **the regions surrounding a selected region in order**.

Imagine walking around a region's boundary from a selected vertex. The tool lists each surrounding region in the order you encounter it.

The two inputs—**Region A** and its **rightmost vertex**—are already selected. The vertex sets the starting point. Choose **Clockwise**, then click **RUN**.
"""

PRACTICE_MERGE_GUIDE_TEXT = """
Very good. Now try one final tool: **Merge**. We use this tool to combine two neighboring regions into one larger region, called a **union**.

Select **Region A** and **Region E**, then click **RUN**.
"""

PRACTICE_DRAW_LINE_GUIDE_TEXT = """
Very good. Now use **Draw Line** to draw a line segment.

Two vertices are already selected for you: the **leftmost vertex of Region B** first, followed by the **rightmost vertex of Region D**. These are the two endpoints of the segment.

Choose **segment** under Line style, then click **RUN**.
"""

PRACTICE_INTERSECT_GUIDE_TEXT = """
Good. The segment you drew is saved as a line.

Choose **Intersect**, select **Which regions does it pass through?**, then click **RUN** to see which regions the line crosses.
"""

PRACTICE_MEASURE_AREA_GUIDE_TEXT = """
Good. Now practice **Measure** with a basic property.

**Region B** is already selected for you. Choose **area** under Measure settings, then click **RUN**.
"""

PRACTICE_MEASURE_ORIENTATION_GUIDE_TEXT = """
Good. Measure can also identify the direction of a cycle.

Three vertices are already selected for you in this order:

1. The leftmost vertex of Region B.
2. The rightmost vertex of Region A.
3. The leftmost vertex of Region D.

Their selection order defines the cycle.

Choose **cycle orientation** under Measure settings, then click **RUN**. The output will be clockwise or counterclockwise.
"""

PRACTICE_SORT_ANGLES_GUIDE_TEXT = """
Good. Now practice **Sort**.

Choose **Angle** under Selection and select these three interior angles:

1. Region B's angle at its leftmost vertex.
2. Region A's angle at its rightmost vertex on the frame.
3. Region D's angle at its rightmost vertex.

Choose **By angle size**, then click **RUN**. The output lists them from smallest to largest.
"""

PRACTICE_TOOL_FINAL_TEXT = """
**Definitions** and **Tool Guide** are available on the right and will remain available throughout the survey. Refer to them whenever you need help with a diagram object or tool.

This survey is **not a test of your ability to operate the tools**. You can answer the questions without them, but the tools can make many questions **substantially easier**, so we recommend becoming comfortable with them.

Feel free to explore other tools before starting the survey. **Useful examples** include drawing a ray, extending an edge, measuring a distance or edge count, finding the neighbors of a vertex or edge, or sorting regions and vertices.

Read the **instructions under the diagram** to see what else each tool can do.
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
            st.session_state.survey_started_at = time.time()
            st.session_state.definitions_open = False
            st.session_state.tool_guide_open = False
            mark_tutorial_completed()
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

def _database_connection():
    """Open a short-lived Postgres connection when DATABASE_URL is configured."""
    if not DATABASE_URL:
        return None
    if psycopg is None:
        raise RuntimeError(
            "DATABASE_URL is configured, but psycopg is not installed. "
            "Add psycopg[binary]>=3.2,<4 to requirements.txt."
        )
    return psycopg.connect(DATABASE_URL)

def _ensure_survey_responses_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS public.survey_responses (
                participant_id TEXT NOT NULL,
                survey_version TEXT NOT NULL,
                payload JSONB NOT NULL,
                survey_completed BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (participant_id, survey_version)
            )
            """
        )

def _load_saved_survey_postgres(participant_id):
    with _database_connection() as conn:
        _ensure_survey_responses_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload
                FROM public.survey_responses
                WHERE participant_id = %s AND survey_version = %s
                """,
                (participant_id, SURVEY_VERSION),
            )
            row = cur.fetchone()
    return row[0] if row else {}

def _save_survey_postgres(payload):
    json_payload = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    with _database_connection() as conn:
        _ensure_survey_responses_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.survey_responses (
                    participant_id,
                    survey_version,
                    payload,
                    survey_completed
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (participant_id, survey_version)
                DO UPDATE SET
                    payload = EXCLUDED.payload,
                    survey_completed = EXCLUDED.survey_completed,
                    updated_at = NOW()
                """,
                (
                    payload["participant_id"],
                    payload["survey_version"],
                    Jsonb(json_payload),
                    bool(payload.get("survey_completed")),
                ),
            )

def load_saved_survey(participant_id):
    """Load this participant's saved question order and confirmed progress."""
    if DATABASE_URL:
        payload = _load_saved_survey_postgres(participant_id)
        if not isinstance(payload, dict):
            return {}
        if _safe_id(payload.get("participant_id", "")) != participant_id:
            return {}
        if payload.get("survey_version") != SURVEY_VERSION:
            return {}
        return payload

    # Local development fallback when no database has been configured.
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

def assigned_survey_form(participant_id):
    """Assign A/B reproducibly so a refresh never changes a participant's form."""
    digest = hashlib.sha256(
        f"{SURVEY_VERSION}:{participant_id}".encode("utf-8")
    ).digest()
    return "A" if digest[0] % 2 == 0 else "B"

def load_question_bank(participant_id, survey_form):
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
    form_ids = SURVEY_FORM_QUESTION_IDS.get(survey_form, set())
    selected = [
        item for item in normalized
        if str(item.get("question_id")) in form_ids
    ]
    if len(selected) != SURVEY_QUESTION_COUNT:
        # Keep the survey usable with a different/fallback dataset, while making
        # the intended 24-question dataset use the curated balanced forms above.
        selected = list(normalized)
        sampler = random.Random(f"{SURVEY_VERSION}:{participant_id}:fallback")
        sampler.shuffle(selected)
        selected = selected[: min(SURVEY_QUESTION_COUNT, len(selected))]
    else:
        sampler = random.Random(f"{SURVEY_VERSION}:{participant_id}:{survey_form}")
        sampler.shuffle(selected)
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
        # When there is only one correct pair, the two labels are already
        # unambiguous without parentheses (for example, "E, J"). For answers
        # containing multiple pairs, parentheses remain required so pair
        # membership cannot be misread.
        if submitted_pairs is None and correct_pairs and len(correct_pairs) == 1:
            submitted_labels = [
                token.upper()
                for token in _answer_tokens(submitted)
                if len(token) == 1 and token.isalpha()
            ]
            if len(submitted_labels) == 2 and submitted_labels[0] != submitted_labels[1]:
                submitted_pairs = [tuple(sorted(submitted_labels))]
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
if "survey_form" not in st.session_state:
    saved_form = SAVED_SURVEY.get("survey_form")
    st.session_state.survey_form = (
        saved_form
        if saved_form in SURVEY_FORM_QUESTION_IDS
        else assigned_survey_form(PARTICIPANT_ID)
    )
if "question_bank" not in st.session_state or "dataset_path" not in st.session_state:
    saved_questions = (
        SAVED_SURVEY.get("question_bank")
        or SAVED_SURVEY.get("questions")
    )
    if isinstance(saved_questions, list) and saved_questions:
        st.session_state.question_bank = saved_questions
        st.session_state.dataset_path = find_dataset_path()
    else:
        (
            st.session_state.question_bank,
            st.session_state.dataset_path,
        ) = load_question_bank(PARTICIPANT_ID, st.session_state.survey_form)
st.session_state.question_bank = add_attention_check(st.session_state.question_bank)
QUESTION_BANK = st.session_state.question_bank
DATASET_PATH = st.session_state.dataset_path

# Xiaohui's palette
GOLD_FILL = (255, 215, 0, 230)
GOLD_OUTLINE = (184, 134, 11, 255)
TEAL = (0, 255, 204, 255)
PRACTICE_FRAME_TEAL = (20, 184, 166, 255)
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

def _ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def init_survey_timer():
    if "survey_started_at" not in st.session_state:
        st.session_state.survey_started_at = time.time()
    if not st.session_state.get("survey_started_timestamp"):
        st.session_state.survey_started_timestamp = _ts()

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

def bind_current_map_helpers():
    """Keep helper modules pointed at the current diagram across Streamlit reruns."""
    res_map = st.session_state.get("res_map")
    if res_map is not None:
        map_helpers.use_map(res_map)
        T.setup(res_map)

# ============================================================
# 1. SESSION INIT
# ============================================================
if "survey_responses" not in st.session_state:
    saved_responses = SAVED_SURVEY.get("responses", {})
    st.session_state.survey_responses = (
        saved_responses if isinstance(saved_responses, dict) else {}
    )
if "post_survey_responses" not in st.session_state:
    saved_post_survey = SAVED_SURVEY.get("post_survey_responses", {})
    st.session_state.post_survey_responses = (
        saved_post_survey if isinstance(saved_post_survey, dict) else {}
    )
if "tutorial_summary" not in st.session_state:
    saved_tutorial_summary = SAVED_SURVEY.get("tutorial_summary", {})
    st.session_state.tutorial_summary = (
        saved_tutorial_summary if isinstance(saved_tutorial_summary, dict) else {}
    )
    if not st.session_state.tutorial_summary:
        st.session_state.tutorial_summary = {
            "started_at": None,
            "completed_at": None,
            "completion_status": "not_started",
            "completion_method": None,
            "steps": {},
        }
if "tutorial_tool_calls" not in st.session_state:
    saved_tutorial_calls = st.session_state.get("tutorial_summary", {}).get(
        "tool_calls", []
    )
    st.session_state.tutorial_tool_calls = (
        list(saved_tutorial_calls) if isinstance(saved_tutorial_calls, list) else []
    )
if "tutorial_selection_events" not in st.session_state:
    saved_tutorial_events = st.session_state.get("tutorial_summary", {}).get(
        "selection_events", []
    )
    st.session_state.tutorial_selection_events = (
        list(saved_tutorial_events) if isinstance(saved_tutorial_events, list) else []
    )
if "last_result_path" not in st.session_state:
    saved_path = participant_result_path(PARTICIPANT_ID)
    st.session_state.last_result_path = saved_path if SAVED_SURVEY else ""
if "survey_completed" not in st.session_state:
    st.session_state.survey_completed = bool(SAVED_SURVEY.get("survey_completed", False))
if "tutorial_completed" not in st.session_state:
    saved_responses = st.session_state.get("survey_responses", {})
    st.session_state.tutorial_completed = bool(
        SAVED_SURVEY.get("tutorial_completed", False)
        or SAVED_SURVEY.get("survey_completed", False)
        or st.session_state.get("tutorial_summary", {}).get("completion_status")
        in ("completed", "skipped")
        or (isinstance(saved_responses, dict) and bool(saved_responses))
    )
if "post_survey_preview_seen" not in st.session_state:
    st.session_state.post_survey_preview_seen = bool(
        SAVED_SURVEY.get("post_survey_preview_seen", False)
    )
if "post_survey_completed" not in st.session_state:
    st.session_state.post_survey_completed = bool(
        SAVED_SURVEY.get("post_survey_completed", False)
    )
if "landing_choice_made" not in st.session_state:
    saved_progress_exists = bool(
        SAVED_SURVEY
        or st.session_state.get("survey_responses")
        or st.session_state.get("tutorial_summary", {}).get("completion_status")
        in ("in_progress", "completed", "skipped")
    )
    st.session_state.landing_choice_made = bool(
        SAVED_SURVEY.get("entry_route") or saved_progress_exists
    )
if "entry_route" not in st.session_state:
    st.session_state.entry_route = SAVED_SURVEY.get("entry_route")
if "survey_started_timestamp" not in st.session_state:
    st.session_state.survey_started_timestamp = SAVED_SURVEY.get(
        "survey_started_at"
    )
if "survey_completed_timestamp" not in st.session_state:
    st.session_state.survey_completed_timestamp = SAVED_SURVEY.get(
        "survey_completed_at"
    )
if "study_started_timestamp" not in st.session_state:
    st.session_state.study_started_timestamp = (
        SAVED_SURVEY.get("study_started_at")
        or st.session_state.get("tutorial_summary", {}).get("started_at")
        or st.session_state.get("survey_started_timestamp")
        or datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    )
if "study_completed_timestamp" not in st.session_state:
    st.session_state.study_completed_timestamp = SAVED_SURVEY.get(
        "study_completed_at"
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
    st.session_state.setdefault("practice_neighbors_done", False)
    st.session_state.setdefault("practice_ordered_neighbors_done", False)
    st.session_state.setdefault("practice_draw_line_done", False)
    st.session_state.setdefault("practice_draw_line_ref", None)
    st.session_state.setdefault("practice_intersect_done", False)
    st.session_state.setdefault("practice_measure_area_done", False)
    st.session_state.setdefault("practice_measure_orientation_done", False)
    st.session_state.setdefault("practice_sort_angles_done", False)
    st.session_state.setdefault("practice_merge_done", False)
    st.session_state.setdefault("practice_entities_feedback_acknowledged", False)
    st.session_state.setdefault("practice_frame_review_done", False)
    st.session_state.setdefault("practice_pending_feedback", None)
    st.session_state.setdefault("practice_guided_complete", False)
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
bind_current_map_helpers()
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
        return {"segment": "a segment", "extend": "an edge extension", "ray": "a ray"}[o["type"]]
    if isinstance(o, float): return f"{o:.4f}"
    return str(o)

def _point_coordinates(point):
    """Return stable diagram-space coordinates for response logging."""
    if point is None or not hasattr(point, "x") or not hasattr(point, "y"):
        return None
    return [round(float(point.x), 6), round(float(point.y), 6)]

def _vertex_geometry(vertex):
    return {
        "vertex_id": getattr(vertex, "num", None),
        "coordinates": _point_coordinates(getattr(vertex, "p", None)),
    }

def _edge_geometry(edge_sel):
    segments = []
    for segment in getattr(edge_sel, "segments", ()):
        segments.append(
            {
                "tail_vertex_id": getattr(segment.tail, "num", None),
                "head_vertex_id": getattr(segment.head, "num", None),
                "tail": _point_coordinates(getattr(segment.tail, "p", None)),
                "head": _point_coordinates(getattr(segment.head, "p", None)),
            }
        )
    return {"segments": segments}

def _angle_geometry(angle_sel):
    vertex = angle_sel.vertex
    face = angle_sel.face
    geometry = {
        "region": face.letter if getattr(face, "bounded", True) else "Outside",
        "vertex_id": getattr(vertex, "num", None),
        "vertex": _point_coordinates(getattr(vertex, "p", None)),
    }
    vertices = list(getattr(face, "vertices", ()))
    # Graph.getVertices() repeats the first vertex at the end to close the
    # polygon. Remove that duplicate before finding the two angle rays;
    # otherwise an angle at the first vertex records itself as a ray point.
    if len(vertices) >= 2 and vertices[0] is vertices[-1]:
        vertices.pop()
    if vertex in vertices and len(vertices) >= 3:
        index = vertices.index(vertex)
        geometry["ray_points"] = [
            _point_coordinates(vertices[index - 1].p),
            _point_coordinates(vertices[(index + 1) % len(vertices)].p),
        ]
    return geometry

def _object_geometry(obj):
    if is_angle(obj):
        return _angle_geometry(obj)
    if is_edgesel(obj):
        return _edge_geometry(obj)
    if is_vertex(obj):
        return _vertex_geometry(obj)
    return {}

def answer_like_text(o):
    """Format tool results so they can be copied into the answer box."""
    if is_angle(o):
        return angle_name(o)
    if is_edgesel(o):
        nm = edge_name(o)
        return nm if nm else o.text
    if isinstance(o, (list, tuple, set)):
        items = list(o)
        if isinstance(o, set):
            items.sort(key=lambda item: answer_like_text(item))
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
        return {"segment": "segment", "extend": "edge extension", "ray": "ray"}[o["type"]]
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

def practice_last_output(tool, input_contains=None):
    """Return the participant-facing output from the latest matching practice call."""
    for call in reversed(st.session_state.get("tool_calls", [])):
        if not isinstance(call, dict) or call.get("tool") != tool:
            continue
        if input_contains and input_contains not in str(call.get("input", "")):
            continue
        return str(call.get("output_text", "")).strip()
    return ""

def continue_after_practice_feedback(stage):
    """Move to the next guided tool only after the participant reads feedback."""
    mark_tutorial_step_completed(stage)
    next_step = {
        "rightmost": ("neighbors", "Region"),
        "neighbors": ("neighbors", "Region"),
        "ordered_neighbors": ("draw line", "Vertex"),
        "draw": ("intersect", "Vertex"),
        "intersect": ("measure", "Region"),
        "area": ("measure", "Vertex"),
        "orientation": ("sort", "Angle"),
        "sort": ("merge", "Region"),
    }
    clear_selection()

    # Start each new page clean. Draw → Intersect is the one exception: the
    # saved line and its annotation must remain available to Intersect.
    if stage == "draw":
        st.session_state.annotations = [
            ann for ann in st.session_state.annotations if ann.get("kind") == "line"
        ]
        st.session_state.angles = []
        st.session_state.named_edges = []
        st.session_state.point_names = {}
    else:
        st.session_state.annotations = []
        st.session_state.lines = []
        st.session_state.angles = []
        st.session_state.named_edges = []
        st.session_state.point_names = {}
        st.session_state.counters = {"v": 1, "L": 1, "U": 1, "r": 1, "a": 1, "e": 1}
    st.session_state.program = []
    st.session_state.log = []
    st.session_state.tool_calls = []

    st.session_state.practice_pending_feedback = None
    if stage == "merge":
        # Begin free exploration with a clean practice canvas. The guided
        # tutorial metrics and recorded calls remain in tutorial_summary.
        st.session_state.unions = []
        st.session_state.union_consumed = []
        st.session_state.undo_stack = []
        st.session_state.pending_angle_vertex = None
        st.session_state.pending_edge_options = []
        st.session_state.click_targets = None
        st.session_state.practice_guided_complete = True
        st.session_state.definitions_open = False
        st.session_state.tool_guide_open = False
        guided_completed_at = _ts()
        tutorial_summary = st.session_state.setdefault("tutorial_summary", {})
        tutorial_summary["guided_completed_at"] = guided_completed_at
        tutorial_summary["free_exploration_started_at"] = guided_completed_at
        tutorial_summary["free_exploration_tool_calls"] = {
            "total_tool_calls": 0,
            "tool_counts": {},
            "error_count": 0,
        }
    else:
        active_tool, selection_filter = next_step[stage]
        st.session_state.active_tool = active_tool
        st.session_state.selection_filter = selection_filter
        current_index = TUTORIAL_GUIDED_STAGES.index(stage)
        start_tutorial_step(TUTORIAL_GUIDED_STAGES[current_index + 1])
        practice_mode_resets = {
            "rightmost": "rad_vtx_onframe",
            "ordered_neighbors": "rad_style",
            "draw": "rad_intersect",
            "intersect": "rad_measure",
            "area": "rad_measure",
            "orientation": "rad_sort",
        }
        mode_key = practice_mode_resets.get(stage)
        if mode_key:
            st.session_state[mode_key] = None
        if stage == "neighbors":
            # Ordered Neighbors teaches the starting-point and direction
            # concepts. Preselect its known inputs so the participant does not
            # have to repeat the object-selection work from Practice 1.
            faces = {
                face.letter: face
                for face in res_map.faces
                if getattr(face, "bounded", False)
            }
            region_a = faces["A"]
            rightmost_a = max(region_a.vertices, key=lambda vertex: vertex.p.x)
            add_to_selection(region_a)
            _name, vertex_meta = point_name_with_meta(rightmost_a)
            add_to_selection(rightmost_a, vertex_meta)
        elif stage == "ordered_neighbors":
            # Draw Line teaches how two endpoints define a segment. Supply the
            # endpoints so the participant can focus on that new operation.
            faces = {
                face.letter: face
                for face in res_map.faces
                if getattr(face, "bounded", False)
            }
            endpoints = (
                min(faces["B"].vertices, key=lambda vertex: vertex.p.x),
                max(faces["D"].vertices, key=lambda vertex: vertex.p.x),
            )
            for vertex in endpoints:
                _name, vertex_meta = point_name_with_meta(vertex)
                add_to_selection(vertex, vertex_meta)
        elif stage == "intersect":
            # Measure Area takes one region as input. Preselect it so this step
            # focuses on choosing the property to measure.
            region_b = next(
                face
                for face in res_map.faces
                if getattr(face, "bounded", False) and face.letter == "B"
            )
            add_to_selection(region_b)
        elif stage == "area":
            # Cycle Orientation uses three ordered vertices. Supply them in the
            # intended order so the participant can focus on interpreting the
            # cycle rather than locating the points again.
            ring = list(res_map.vertices[:8])
            for vertex in (ring[3], ring[0], ring[5]):
                _name, vertex_meta = point_name_with_meta(vertex)
                add_to_selection(vertex, vertex_meta)
    refresh_tutorial_summary_metrics()
    save_survey_results()
    st.rerun()

def practice_rightmost_vertex_done():
    if st.session_state.get("practice_rightmost_vertex_done"):
        return True
    for call in st.session_state.get("tool_calls", []):
        if (
            isinstance(call, dict)
            and call.get("tool") in {"find", "vertex"}
            and call.get("function") in {"find", "vertex"}
            and 'which="rightmost"' in str(call.get("input", ""))
            and "A" in str(call.get("input", ""))
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

def practice_ordered_neighbors_done():
    if st.session_state.get("practice_ordered_neighbors_done"):
        return True
    for call in st.session_state.get("tool_calls", []):
        input_text = str(call.get("input", "")) if isinstance(call, dict) else ""
        if (
            isinstance(call, dict)
            and call.get("tool") == "neighbors"
            and call.get("function") == "neighbors"
            and 'neighbors(A, "ordered"' in input_text
            and "go_counterclockwise=False" in input_text
        ):
            return True
    return False

def practice_merge_done():
    if not st.session_state.get("practice_sort_angles_done", False):
        return False
    has_expected_union = any(
        {face.letter for face in union.get("pair", ())} == {"A", "E"}
        for union in st.session_state.get("unions", [])
    )
    if not has_expected_union:
        return False
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
        if practice_selected_entity_types() == set(PRACTICE_REQUIRED_SELECTIONS):
            if not st.session_state.get("practice_entities_feedback_acknowledged", False):
                return "Review the four kinds of objects you selected."
            if not st.session_state.get("practice_frame_review_done", False):
                return "Review the frame and outside of the frame."
            return "Determine whether the arrows move clockwise or counterclockwise."
        return (
            "Practice 1 of 2: Select one Region, one Angle, one Vertex, and one Edge."
        )
    return "Practice 2 of 2: practice using the tools."

def current_practice_tool_stage():
    """Return the guided tool step currently awaiting completion."""
    if not practice_rightmost_vertex_done():
        return "rightmost"
    if not practice_neighbors_done():
        return "neighbors"
    if not practice_ordered_neighbors_done():
        return "ordered_neighbors"
    if not st.session_state.get("practice_draw_line_done", False):
        return "draw"
    if not st.session_state.get("practice_intersect_done", False):
        return "intersect"
    if not st.session_state.get("practice_measure_area_done", False):
        return "area"
    if not st.session_state.get("practice_measure_orientation_done", False):
        return "orientation"
    if not st.session_state.get("practice_sort_angles_done", False):
        return "sort"
    return "merge"

TUTORIAL_GUIDED_STAGES = (
    "selection_practice",
    "rightmost",
    "neighbors",
    "ordered_neighbors",
    "draw",
    "intersect",
    "area",
    "orientation",
    "sort",
    "merge",
)

def tutorial_step_entry(stage):
    summary = st.session_state.setdefault("tutorial_summary", {})
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

def start_tutorial_step(stage):
    entry = tutorial_step_entry(stage)
    if not entry.get("started_at"):
        entry["started_at"] = _ts()
    return entry

def mark_tutorial_step_completed(stage):
    entry = start_tutorial_step(stage)
    completed_at = _ts()
    entry["completed"] = True
    entry["completion_method"] = (
        "completed_example" if entry.get("used_completed_example") else "independent"
    )
    entry["completed_at"] = completed_at
    entry["duration_seconds"] = elapsed_between_timestamps(
        entry.get("started_at"),
        completed_at,
    )
    summary = st.session_state.tutorial_summary
    summary["completion_status"] = "in_progress"
    if not summary.get("started_at"):
        summary["started_at"] = _ts()
    save_survey_results()

def mark_tutorial_tool_error():
    if not (
        IS_PRACTICE
        and st.session_state.get("practice_step") == "tools"
        and not st.session_state.get("practice_guided_complete", False)
    ):
        return
    stage = current_practice_tool_stage()
    entry = start_tutorial_step(stage)
    entry["tool_errors"] = int(entry.get("tool_errors", 0)) + 1
    save_survey_results()

def summarize_tutorial_tool_calls(calls):
    valid_calls = [call for call in calls if isinstance(call, dict)]
    tool_counts = {}
    error_count = 0
    for call in valid_calls:
        tool = str(call.get("tool", "unknown"))
        tool_counts[tool] = tool_counts.get(tool, 0) + 1
        if (
            call.get("call_type") == "error"
            or call.get("function") == "error"
        ):
            error_count += 1
    return {
        "total_tool_calls": len(valid_calls),
        "tool_counts": dict(sorted(tool_counts.items())),
        "error_count": error_count,
    }

def refresh_tutorial_summary_metrics():
    summary = st.session_state.setdefault("tutorial_summary", {})
    steps = summary.setdefault("steps", {})
    completed_at = summary.get("completed_at")
    metric_end = completed_at or _ts()
    summary["total_duration_seconds"] = elapsed_between_timestamps(
        summary.get("started_at"),
        metric_end,
    )
    summary["guided_duration_seconds"] = elapsed_between_timestamps(
        summary.get("started_at"),
        summary.get("guided_completed_at"),
    )
    summary["free_exploration_seconds"] = elapsed_between_timestamps(
        summary.get("guided_completed_at"),
        summary.get("free_exploration_completed_at") or (
            metric_end if summary.get("guided_completed_at") else None
        ),
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
    summary["skipped_steps"] = (
        len(TUTORIAL_GUIDED_STAGES)
        if summary.get("completion_status") == "skipped"
        else sum(
            steps.get(stage, {}).get("completion_method") == "skipped"
            for stage in TUTORIAL_GUIDED_STAGES
        )
    )
    summary["total_tool_errors"] = sum(
        int(steps.get(stage, {}).get("tool_errors", 0) or 0)
        for stage in TUTORIAL_GUIDED_STAGES
    )
    summary.setdefault(
        "free_exploration_tool_calls",
        {"total_tool_calls": 0, "tool_counts": {}, "error_count": 0},
    )
    tutorial_calls = list(st.session_state.get("tutorial_tool_calls", []))
    summary["tool_calls"] = tutorial_calls
    for stage in TUTORIAL_GUIDED_STAGES:
        step = tutorial_step_entry(stage)
        step_calls = [
            call for call in tutorial_calls
            if call.get("tutorial_phase") == "guided"
            and call.get("tutorial_step") == stage
        ]
        step["tool_calls"] = step_calls
        step["tool_usage"] = summarize_tutorial_tool_calls(step_calls)
    free_calls = [
        call for call in tutorial_calls
        if call.get("tutorial_phase") == "free_exploration"
    ]
    summary["free_exploration_calls"] = free_calls
    summary["free_exploration_tool_calls"] = summarize_tutorial_tool_calls(
        free_calls
    )
    summary["tool_usage"] = summarize_tutorial_tool_calls(tutorial_calls)
    summary["selection_events"] = list(
        st.session_state.get("tutorial_selection_events", [])
    )
    return summary

def mark_tutorial_completed():
    summary = st.session_state.setdefault("tutorial_summary", {})
    completed_at = _ts()
    summary["completion_status"] = "completed"
    summary["completion_method"] = "guided_tutorial"
    summary["completed_at"] = completed_at
    if not summary.get("started_at"):
        summary["started_at"] = completed_at
    if summary.get("guided_completed_at"):
        summary["free_exploration_completed_at"] = completed_at
    refresh_tutorial_summary_metrics()
    save_survey_results()

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
    record = {
        "object_type": kind,
        "object_label": label,
        "description": describe(obj),
    }
    # Region labels already identify their geometry in the saved diagram.
    # Temporary vertex/edge/angle names do not, so retain their true geometry.
    record.update(_object_geometry(obj))
    return record

def record_selection_event(action, obj=None, selection_before=None):
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
    if selection_before is not None:
        event["selection_before"] = [
            _selection_event_object(item) for item in selection_before
        ]
    if obj is not None:
        event["object"] = _selection_event_object(obj)
    events.append(event)
    if IS_PRACTICE:
        tutorial_events = st.session_state.setdefault(
            "tutorial_selection_events", []
        )
        tutorial_event = dict(event)
        tutorial_event["order"] = len(tutorial_events) + 1
        tutorial_event["tutorial_phase"] = (
            "free_exploration"
            if st.session_state.get("practice_guided_complete", False)
            else "guided"
        )
        tutorial_event["tutorial_step"] = (
            None
            if tutorial_event["tutorial_phase"] == "free_exploration"
            else current_practice_tool_stage()
        )
        tutorial_events.append(tutorial_event)

def record_interface_event(action, details=None):
    """Record a UI-only action without counting it as a reasoning tool call."""
    events = st.session_state.setdefault("selection_events", [])
    event = {
        "order": len(events) + 1,
        "action": action,
        "event_type": "interface",
        "timestamp": _ts(),
        "survey_elapsed_seconds": survey_elapsed_seconds(),
    }
    if details:
        event["details"] = details
    events.append(event)
    if IS_PRACTICE:
        tutorial_events = st.session_state.setdefault(
            "tutorial_selection_events", []
        )
        tutorial_event = dict(event)
        tutorial_event["order"] = len(tutorial_events) + 1
        tutorial_event["tutorial_phase"] = (
            "free_exploration"
            if st.session_state.get("practice_guided_complete", False)
            else "guided"
        )
        tutorial_event["tutorial_step"] = (
            None
            if tutorial_event["tutorial_phase"] == "free_exploration"
            else current_practice_tool_stage()
        )
        tutorial_events.append(tutorial_event)

def clear_selection():
    st.session_state.selection = []
    st.session_state.selection_meta = []

def remove_selection_item(i):
    """Remove one live selection while leaving labeled objects on the map."""
    sel, meta_list = st.session_state.selection, st.session_state.selection_meta
    if i < 0 or i >= len(sel):
        return
    selection_before = list(sel)
    meta = meta_list[i] if i < len(meta_list) else None
    removed = sel.pop(i)
    if i < len(meta_list):
        meta_list.pop(i)
    record_selection_event(
        "deselect",
        removed,
        selection_before=selection_before,
    )
    if meta:
        if meta["kind"] == "point":
            # Vertex labels are persistent names. Deselecting a vertex only
            # removes it from the current selection; the label stays visible.
            pass
        elif meta["kind"] == "angle":
            # A labeled angle remains available for direct re-selection, just
            # like a labeled vertex. Clear all still removes all annotations.
            pass
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
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = max(1.0, math.hypot(dx, dy))
        nx, ny = -dy / length, dx / length
        # Vertex labels sit to the right of their markers, so keep a nearly
        # vertical edge's name on the left. For a nearly horizontal edge,
        # prefer the space above it.
        if abs(nx) >= abs(ny):
            if nx > 0:
                nx, ny = -nx, -ny
        elif ny > 0:
            nx, ny = -nx, -ny
        label_xy = (round(mx + 30 * nx), round(my + 30 * ny))
        font = DrawGraph.GetSystemFont(32)
        odraw.text(label_xy, label, fill=(0, 100, 130, 255), font=font,
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
    # Paint the two source regions directly. This is more robust than relying
    # on the helper's pseudo-face vertex walk, which can collapse to only one
    # side of a union when a practice-map boundary has split half-edges.
    pair = union.get("pair", ())
    faces = pair if pair else (union["face"],)
    for face in faces:
        pts = [DrawGraph.V2P(v.p) for v in face.vertices]
        draw.polygon(pts, fill=UNION_PURPLE)

    # Draw only the outside boundary. A segment occurring in both source
    # regions is their shared edge and must disappear inside the union.
    segments = {}
    for face in faces:
        for edge in face.edges:
            a = (round(edge.tail.p.x, 9), round(edge.tail.p.y, 9))
            b = (round(edge.head.p.x, 9), round(edge.head.p.y, 9))
            key = tuple(sorted((a, b)))
            segments.setdefault(key, []).append(edge)
    for occurrences in segments.values():
        if len(occurrences) == 1:
            edge = occurrences[0]
            draw.line([DrawGraph.V2P(edge.tail.p), DrawGraph.V2P(edge.head.p)],
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
    frame_review = (
        IS_PRACTICE
        and PRACTICE_STEP == "select"
        and practice_selected_entity_types() == set(PRACTICE_REQUIRED_SELECTIONS)
        and st.session_state.get("practice_entities_feedback_acknowledged", False)
        and not st.session_state.get("practice_frame_review_done", False)
    )
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
    direction_demo = (
        IS_PRACTICE
        and PRACTICE_STEP == "select"
        and practice_selected_entity_types() == set(PRACTICE_REQUIRED_SELECTIONS)
        and st.session_state.get("practice_entities_feedback_acknowledged", False)
        and st.session_state.get("practice_frame_review_done", False)
    )
    concept_review = frame_review or direction_demo
    visible_annotations = [] if concept_review else st.session_state.annotations
    visible_selection = [] if concept_review else st.session_state.selection

    # ---- PASS 1: region fills go UNDERNEATH points/lines/angles, so a
    # reference point is never hidden under a highlight. The unbounded outer
    # face is never filled (it would blanket the whole canvas).
    for ann in visible_annotations:
        if ann["kind"] == "region" and getattr(ann["obj"], "bounded", False):
            face = ann["obj"]
            highlight_region_solid(
                odraw, face, ann.get("color", GRAY_SOLID),
                draw_label=id(face) not in union_face_ids,
            )
    for o in visible_selection:
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
    for ann in visible_annotations:
        kind = ann["kind"]
        if kind == "point":
            highlight_vertex_x(odraw, ann["p"])
            if ann.get("label"):
                px, py = DrawGraph.V2P(ann["p"])
                odraw.text((px + 16, py - 32), ann["label"], fill=BLUE, font=font,
                           stroke_width=2, stroke_fill=(255, 255, 255, 255))
        elif kind == "line":
            a, b = line_endpoints_math(ann["line"])
            pa, pb = DrawGraph.V2P(a), DrawGraph.V2P(b)
            # Keep a full extension visually subordinate to the selected
            # source edge, which is drawn later as the thick cyan segment.
            line_width = 5 if ann["line"]["type"] == "extend" else 6
            odraw.line([pa, pb], fill=BLUE, width=line_width)
            if ann.get("label"):
                if ann["line"]["type"] == "extend":
                    # Put the line name on the longer exposed extension rather
                    # than at the source edge's midpoint, where v/e labels
                    # already compete for space.
                    source_a = DrawGraph.V2P(ann["line"]["a"])
                    source_b = DrawGraph.V2P(ann["line"]["b"])
                    def nearest_source(frame_point):
                        return min(
                            (source_a, source_b),
                            key=lambda source: (
                                (frame_point[0] - source[0]) ** 2
                                + (frame_point[1] - source[1]) ** 2
                            ),
                        )
                    exposed_pairs = [
                        (pa, nearest_source(pa)),
                        (pb, nearest_source(pb)),
                    ]
                    outer, inner = max(
                        exposed_pairs,
                        key=lambda pair: (
                            (pair[0][0] - pair[1][0]) ** 2
                            + (pair[0][1] - pair[1][1]) ** 2
                        ),
                    )
                    mx = round(outer[0] * 0.58 + inner[0] * 0.42)
                    my = round(outer[1] * 0.58 + inner[1] * 0.42)
                else:
                    mx = (pa[0] + pb[0]) // 2
                    my = (pa[1] + pb[1]) // 2
                odraw.text((mx, my), ann["label"], fill=BLUE, font=font,
                           anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))
        elif kind == "angle":
            draw_interior_arc_x(odraw, ann["vertex"], ann["face"],
                                label=ann.get("label"))

    # Named edges remain visible after the live selection is cleared. Clicking
    # the same geometry reuses its existing e-label instead of creating a new one.
    if not concept_review:
        consumed_map = _consumed_to_union_map()
        for edge_label, edge_selection in st.session_state.named_edges:
            visible_segments = [
                segment
                for segment in edge_selection.segments
                if not _edge_interior_to_union(segment, consumed_map)
            ]
            for segment_index, segment in enumerate(visible_segments):
                highlight_edge_x(
                    odraw,
                    segment,
                    label=edge_label if segment_index == 0 else None,
                )

    # live selection markers — angle/edge checks FIRST. Once the four selection
    # tasks are complete, replace their mixed highlights with a clean direction
    # demonstration on the same diagram.
    for o in visible_selection:
        if o == "frame":
            # Highlight the map's actual outer boundary, not its rectangular
            # coordinate bounds. The practice map has an octagonal frame.
            seen_frame_segments = set()
            for edge in res_map.edges:
                left = getattr(edge, "leftFace", None)
                right = getattr(getattr(edge, "reverse", None), "leftFace", None)
                if not (
                    getattr(left, "bounded", False)
                    != getattr(right, "bounded", False)
                ):
                    continue
                a = DrawGraph.V2P(edge.tail.p)
                b = DrawGraph.V2P(edge.head.p)
                key = tuple(sorted((a, b)))
                if key in seen_frame_segments:
                    continue
                seen_frame_segments.add(key)
                odraw.line([a, b], fill=TEAL, width=10)
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

    if frame_review:
        seen_frame_segments = set()
        for edge in res_map.edges:
            left = getattr(edge, "leftFace", None)
            right = getattr(getattr(edge, "reverse", None), "leftFace", None)
            if getattr(left, "bounded", False) == getattr(right, "bounded", False):
                continue
            a = DrawGraph.V2P(edge.tail.p)
            b = DrawGraph.V2P(edge.head.p)
            key = tuple(sorted((a, b)))
            if key in seen_frame_segments:
                continue
            seen_frame_segments.add(key)
            odraw.line([a, b], fill=PRACTICE_FRAME_TEAL, width=9)
        label_font = DrawGraph.GetSystemFont(38)
        odraw.text(
            (img_size[0] // 2, 48),
            "Outside of the frame",
            fill=(75, 85, 99, 255),
            font=label_font,
            anchor="mm",
        )
        odraw.text(
            (img_size[0] // 2, 135),
            "Frame",
            fill=PRACTICE_FRAME_TEAL,
            font=label_font,
            anchor="mm",
            stroke_width=2,
            stroke_fill=(255, 255, 255, 255),
        )

    if direction_demo:
        direction = st.session_state.get("practice_direction_target", "Clockwise")
        cx, cy = maxX / 2, maxY / 2
        candidates = list(getattr(res_map, "vertices", []))
        targets = [
            Graph.Vector(cx, maxY),
            Graph.Vector(maxX, cy),
            Graph.Vector(cx, 0),
            Graph.Vector(0, cy),
        ]
        cardinal = [
            min(candidates, key=lambda v: Graph.vecDist(v.p, target))
            for target in targets
        ]
        if direction == "Counterclockwise":
            cardinal = [cardinal[0], cardinal[3], cardinal[2], cardinal[1]]

        points = [DrawGraph.V2P(vertex.p) for vertex in cardinal]
        demo_color = (30, 102, 210, 255)
        demo_font = DrawGraph.GetSystemFont(42)
        for index, point in enumerate(points, start=1):
            x, y = point
            odraw.ellipse([x - 17, y - 17, x + 17, y + 17], fill=(255, 255, 255, 245),
                          outline=demo_color, width=7)
            odraw.text((x + 22, y - 22), str(index), fill=demo_color, font=demo_font,
                       stroke_width=3, stroke_fill=(255, 255, 255, 255))
        for start, end in zip(points, points[1:] + points[:1]):
            sx, sy = start
            ex, ey = end
            dx, dy = ex - sx, ey - sy
            length = max(math.hypot(dx, dy), 1)
            ux, uy = dx / length, dy / length
            line_start = (sx + ux * 22, sy + uy * 22)
            line_end = (ex - ux * 27, ey - uy * 27)
            odraw.line([line_start, line_end], fill=demo_color, width=7)
            px, py = -uy, ux
            tip = line_end
            base_x, base_y = tip[0] - ux * 18, tip[1] - uy * 18
            odraw.polygon([
                tip,
                (base_x + px * 10, base_y + py * 10),
                (base_x - px * 10, base_y - py * 10),
            ], fill=demo_color)

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
TOOLS = ["find", "neighbors", "draw line", "intersect", "merge", "measure", "sort"]

TOOL_LABELS = {
    "find":      "Find",
    "vertex":    "Find Vertex",
    "edge":      "Find Edge",
    "neighbors": "Neighbors",
    "draw line": "Draw Line",
    "intersect": "Intersect",
    "merge":     "Merge",
    "measure":   "Measure",
    "sort":      "Sort",
}

INSTRUCTIONS = {
    "find": (
        "- **Find a vertex:** select ONE Region, then choose leftmost / rightmost / topmost / bottommost / sharpest / widest.\n"
        "- **Find a meeting vertex:** select TWO OR MORE Regions, then specify whether the vertex is on the frame.\n"
        "- **Find a frame vertex:** select the FRAME, then choose one corner or all corners.\n"
        "- **Find an edge:** choose Find Edge, then select TWO OR MORE Regions that uniquely identify the edge."
    ),
    "vertex": (
        "- **Select ONE Region** → select all vertices or pick a vertex with a given property: leftmost / rightmost, topmost / bottommost, vertex with the smallest / largest angle.\n"
        "- **Select TWO OR MORE Regions** → find their meeting vertex or vertices.\n"
        "- **Select the FRAME** (the diagram's outer boundary) → label one or all of its vertices."
    ),
    "edge": (
        "- **Select TWO OR MORE Regions** → find the unique edge identified by those Regions."
    ),
    "neighbors": (
        "- **Select ONE Vertex** → find all regions that meet at that vertex.\n"
        "- **Select ONE Edge** → find the diagram regions bordering that edge. \n"
        "- **Select ONE Region** → find all neighboring regions that share an edge. \n"
        "- **Select ONE Region + ONE Vertex** → draw a cycle starting at that vertex (clockwise / counter-clockwise) and return a sequence of neighbors in order."
    ),
    "draw line": (
        "- **Select TWO Vertices** → draw a line segment between them. \n"
        "- **Select ONE Vertex** → draw a ray starting at that vertex that extends up / down / left /right.\n"
        "- **Select ONE Edge** → extend the edge in both directions as a straight line.\n"
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

TOOL_GUIDE_TEXT = """
**Find**

- **Vertex—position:** select one region to find its leftmost, rightmost, topmost, or bottommost vertex.
- **Vertex—angle:** select one region to find its sharpest or widest vertex.
- **Vertex—meeting point:** select two or more regions to find where they meet.
- **Vertex—frame:** select the frame to find one or all frame corners.
- **Edge:** select two or more regions that uniquely identify the edge.

**Neighbors**

- Find the regions next to a selected region, edge, or vertex.
- Starting from a selected vertex of a region, list the neighboring regions in clockwise or counterclockwise order.

**Draw Line**

- Draw a segment between two vertices.
- Draw a ray from one vertex in a chosen direction.
- Extend a selected edge in both directions as a straight line.

**Intersect**

- Find which regions a drawn line passes through.
- Check whether two drawn lines cross.

**Merge**

- Combine exactly two neighboring regions into one larger union.
- In this survey, a union cannot be merged with another region.

**Measure**

- **Distance:** measure the distance between two vertices or two regions.
- **Angle:** measure a selected angle in degrees.
- **Area:** measure the area of one region.
- **Edge count:** count how many edges form the boundary of one region.
- **Region count:** count how many regions are in the entire diagram.
- **Cycle orientation:** determine whether three selected vertices go clockwise or counterclockwise in the order clicked.

**Sort**

- Order selected angles by size.
- Order selected regions by area.
- Order selected vertices by position or distance.
"""

def validate(tool, modes):
    s = sel_sig()
    nR, nV, nE, nA, nF = (len(s["regions"]), len(s["vertices"]),
                          len(s["edges"]), len(s["angles"]), len(s["frame"]))

    if tool == "find":
        object_type = modes.get("object")
        if object_type not in {"vertex", "edge"}:
            return (False, "Choose whether to find a vertex or an edge.")
        return validate(object_type, modes)

    if tool == "vertex":
        # Vertices already sitting in the buffer — kept there from earlier
        # Vertex-tool calls (see finish_vertex) — don't block a new call.
        # Only the FRAME/region picks you just made actually drive this run.
        if nF >= 1:
            return (modes.get("which") is not None, "Choose which frame corner to find.")
        if nR == 1:
            return (modes.get("which") is not None, "Choose which corner to find.")
        if nR >= 2:
            return (modes.get("on_frame") is not None,
                    "Choose whether the meeting vertex is on the frame.")
        if IS_PRACTICE:
            return (False, "Select 1 region or 2+ regions. "
                           "(Vertices already in your buffer are kept.)")
        return (False, "Select 1 region, the FRAME, or 2+ regions. "
                       "(Vertices already in your buffer are kept.)")

    if tool == "edge":
        if nR < 2 or nR != s["n"]:
            return (
                False,
                "Select two or more regions that identify the edge.",
            )
        try:
            T.find(
                s["regions"][0], *s["regions"][1:], object="edge"
            )
        except ValueError:
            return (
                False,
                "Those regions do not identify one unique edge.",
            )
        return (True, "")

    if tool == "neighbors":
        # one POINT (and nothing else) → regions meeting at that point
        if nV == 1 and s["n"] == 1:                    return (True, "")
        # one EDGE (and nothing else) → regions on either side of it
        if nE == 1 and s["n"] == 1:                    return (True, "")
        # a single region → its edge / vertex neighbors
        if nR == 1 and s["n"] == 1:
            return (modes.get("kind") is not None, "Choose a neighbor type.")
        # a region + one of its corners → walking order
        if nR == 1 and nV == 1 and s["n"] == 2:
            region, start_vertex = s["regions"][0], s["vertices"][0]
            if modes.get("ccw") is None:
                return (False, "Choose a walk direction.")
            vertex_is_on_region = any(
                candidate is start_vertex
                or Graph.vecDist(candidate.p, start_vertex.p) < 1e-9
                for candidate in getattr(region, "vertices", [])
            )
            if not vertex_is_on_region:
                return (
                    False,
                    f"The selected starting vertex is not on Region {region.letter}. "
                    f"Choose a vertex of Region {region.letter}.",
                )
            if (
                IS_PRACTICE
                and PRACTICE_STEP == "tools"
                and st.session_state.get("practice_neighbors_done", False)
                and not st.session_state.get("practice_ordered_neighbors_done", False)
            ):
                faces = {
                    face.letter: face
                    for face in res_map.faces
                    if getattr(face, "bounded", False)
                }
                expected_vertex = max(
                    faces["A"].vertices,
                    key=lambda vertex: vertex.p.x,
                )
                if (
                    region.letter != "A"
                    or start_vertex is not expected_vertex
                    or modes.get("ccw", True)
                ):
                    return (
                        False,
                        "For this practice step, select Region A and its rightmost vertex, "
                        "then choose Clockwise.",
                    )
            return (True, "")
        return (False, "Select 1 vertex, 1 edge, 1 region, or 1 region + 1 of its corners.")

    if tool == "draw line":
        style = modes.get("style")
        if style is None:
            return (False, "Choose a line style.")
        if style == "ray":
            return (s["n"] == 1 and nV == 1, "Ray needs exactly 1 vertex.")
        if style == "full line":
            return (s["n"] == 1 and nE == 1, "Extend edge needs exactly 1 edge.")
        ok = s["n"] == 2 and nV == 2
        if (
            ok
            and IS_PRACTICE
            and PRACTICE_STEP == "tools"
            and st.session_state.get("practice_ordered_neighbors_done", False)
            and not st.session_state.get("practice_draw_line_done", False)
        ):
            faces = {
                face.letter: face
                for face in res_map.faces
                if getattr(face, "bounded", False)
            }
            expected = [
                min(faces["B"].vertices, key=lambda vertex: vertex.p.x),
                max(faces["D"].vertices, key=lambda vertex: vertex.p.x),
            ]
            if (
                modes.get("style") != "segment"
                or nV != 2
                or any(actual is not target for actual, target in zip(s["vertices"], expected))
            ):
                return (
                    False,
                    "For this practice step, select the two specified vertices in the listed order and choose segment.",
                )
        return (ok, "Segment needs exactly 2 vertices.")

    if tool == "intersect":
        if not st.session_state.lines:
            return (False, "Draw a line first.")
        if (
            IS_PRACTICE
            and PRACTICE_STEP == "tools"
            and st.session_state.get("practice_draw_line_done", False)
            and not st.session_state.get("practice_intersect_done", False)
            and modes.get("line", (None, None))[1]
                is not st.session_state.get("practice_draw_line_ref")
        ):
            return (False, "For this practice step, select the segment created in the previous step.")
        return (True, "")

    if tool == "merge":
        if s["n"] != 2 or nR != 2:
            return (False, "Select exactly two regions.")
        union_face_ids = {id(union["face"]) for union in st.session_state.unions}
        if any(id(region) in union_face_ids for region in s["regions"]):
            return (False, "Select two original regions. A union cannot be merged again.")
        if (
            IS_PRACTICE
            and PRACTICE_STEP == "tools"
            and st.session_state.get("practice_sort_angles_done", False)
            and not st.session_state.get("practice_merge_done", False)
            and {region.letter for region in s["regions"]} != {"A", "E"}
        ):
            return (False, "For this practice step, select Region A and Region E.")
        return (True, "")

    if tool == "measure":
        w = modes.get("what")
        if not w: return (False, "Pick what to measure.")
        if w == "distance":
            if nV == 2 and s["n"] == 2:        return (True, "")   # two points
            if nR == 2 and s["n"] == 2:        return (True, "")   # two regions
            return (False, "Select two vertices or two regions.")
        if w == "angle":
            return (nA == 1 and s["n"] == 1, "Select ONE angle.")
        if w in ("area", "sides"):
            return (nR == 1 and s["n"] == 1, "Select ONE region.")
        if w == "regions":
            return (nF == 1 and s["n"] == 1, "Select FRAME.")
        if w == "orientation":
            if nV != 3 or s["n"] != 3:
                return (False, "Select exactly three vertices in cycle order.")
            if (
                IS_PRACTICE
                and PRACTICE_STEP == "tools"
                and st.session_state.get("practice_measure_area_done", False)
                and not st.session_state.get("practice_measure_orientation_done", False)
            ):
                ring = list(res_map.vertices[:8])
                expected = [ring[3], ring[0], ring[5]]
                if any(actual is not target for actual, target in zip(s["vertices"], expected)):
                    return (
                        False,
                        "For this practice step, select the three specified vertices in the listed order.",
                    )
            return (True, "")
        return (False, "")

    if tool == "sort":
        by = modes.get("by")
        if not by: return (False, "Pick how to order them.")
        if by == "angle":
            if (
                IS_PRACTICE
                and PRACTICE_STEP == "tools"
                and st.session_state.get("practice_measure_orientation_done", False)
                and not st.session_state.get("practice_sort_angles_done", False)
            ):
                faces = {
                    face.letter: face
                    for face in res_map.faces
                    if getattr(face, "bounded", False)
                }
                expected = {
                    AngleSel(min(faces["B"].vertices, key=lambda vertex: vertex.p.x), faces["B"]),
                    AngleSel(max(faces["A"].vertices, key=lambda vertex: vertex.p.x), faces["A"]),
                    AngleSel(max(faces["D"].vertices, key=lambda vertex: vertex.p.x), faces["D"]),
                }
                if nA != 3 or set(s["angles"]) != expected:
                    return (False, "For this practice step, select the three specified angles.")
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

def natural_join(items):
    """Join short labels as natural English without changing their stored values."""
    labels = [str(item).strip() for item in items if str(item).strip()]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return f"{', '.join(labels[:-1])}, and {labels[-1]}"

def participant_output_for_tool(tool, call_str, result, output_text=None):
    """Return a concise, natural-language result for the participant-facing Output."""
    shown = output_text if output_text is not None else answer_like_text(result)
    no_result = result is None or (
        isinstance(result, (list, tuple, set)) and not result
    )
    shown_as_list = (
        natural_join(answer_like_text(item) for item in result)
        if isinstance(result, (list, tuple, set)) and result
        else shown
    )
    emphasized = f"**{shown}**"
    emphasized_list = f"**{shown_as_list}**"

    if tool in ("find", "vertex") and 'object="edge"' not in call_str:
        property_match = re.search(r'which="([^"]+)"', call_str)
        region_match = re.match(r"(?:vertex|find)\(([^,\)]+)", call_str)
        if property_match and region_match:
            target = region_match.group(1).strip().strip('"')
            property_name = property_match.group(1).replace("_", " ")
            target_text = "the frame" if target == "frame" else f"Region {target}"
            if no_result:
                return f"No {property_name} vertex was found for {target_text}."
            if property_name == "all":
                return f"Found and labeled all vertices of {target_text}: {emphasized_list}."
            return f"Found and labeled {emphasized_list} as the {property_name} vertex of {target_text}."
        meeting_match = re.match(
            r"(?:vertex|find)\((.+?)(?:,\s*object=\"vertex\")?,\s*"
            r"on_frame=(True|False)\)",
            call_str,
        )
        if meeting_match:
            regions = [part.strip() for part in meeting_match.group(1).split(",")]
            location = "on the frame" if meeting_match.group(2) == "True" else "not on the frame"
            region_text = natural_join(regions)
            if no_result:
                return f"No vertex was found where Regions {region_text} meet {location}."
            location_sentence = (
                "This vertex is on the frame."
                if meeting_match.group(2) == "True"
                else "This vertex is not on the frame."
            )
            return f"Found and labeled {emphasized_list} where Regions {region_text} meet. {location_sentence}"
        if no_result:
            return "No matching vertex was found."
        return f"Found and labeled vertex {emphasized}."

    if tool == "edge" or (
        tool == "find" and 'object="edge"' in call_str
    ):
        if no_result:
            return "No uniquely matching edge was found."
        return f"Found and labeled {emphasized}."

    if tool == "neighbors":
        region_match = re.match(r'neighbors\(([A-Z][A-Za-z0-9]*),\s*"(edge|vertex)"\)', call_str)
        if region_match:
            region_name = region_match.group(1)
            if region_match.group(2) == "edge":
                if no_result:
                    return f"No regions share an edge with Region {region_name}."
                return f"Regions that share an edge with Region {region_name}: {emphasized}."
            if no_result:
                return f"No regions touch Region {region_name} at a vertex without sharing an edge."
            return (
                f"Regions that touch Region {region_name} at a vertex without sharing an edge: "
                f"{emphasized}."
            )
        ordered_match = re.match(
            r'neighbors\(([A-Z][A-Za-z0-9]*),\s*"ordered",\s*start=([^,]+),\s*go_counterclockwise=(True|False)\)',
            call_str,
        )
        if ordered_match:
            direction = "counterclockwise" if ordered_match.group(3) == "True" else "clockwise"
            if no_result:
                return (
                    f"The {direction} order from {ordered_match.group(2).strip()} "
                    "could not be determined. Try a different starting vertex."
                )
            return (
                f"Regions around Region {ordered_match.group(1)}, starting at "
                f"{ordered_match.group(2).strip()} and moving {direction}: {emphasized}."
            )
        single_match = re.match(r"neighbors\(([^\)]+)\)", call_str)
        if single_match:
            selected = single_match.group(1).strip()
            if no_result:
                return f"No neighboring regions were found for {selected}."
            if selected.startswith("v"):
                return f"Regions meeting at {selected}: {emphasized}."
            if selected.startswith("e"):
                return f"Regions bordering {selected}: {emphasized}."
            if selected.startswith("["):
                return f"Regions neighboring the selected objects: {emphasized}."
            return f"Regions neighboring {selected}: {emphasized}."
        if no_result:
            return "No neighboring regions were found."
        return f"Neighboring regions: {emphasized}."

    if tool == "intersect":
        line_match = re.match(r'intersect\(([^,]+),\s*"faces"\)', call_str)
        if line_match:
            if no_result:
                return f"{line_match.group(1).strip()} does not cross any regions."
            return f"Regions crossed by {line_match.group(1).strip()}: {emphasized}."
        lines_match = re.match(r"intersect\(([^,]+),\s*([^\)]+)\)", call_str)
        if lines_match and isinstance(result, bool):
            first, second = lines_match.group(1).strip(), lines_match.group(2).strip()
            return f"Do {first} and {second} intersect? **{'Yes' if result else 'No'}**."
        if no_result:
            return "No intersection was found."
        return f"Intersection result: {emphasized}."

    if tool == "measure":
        what_match = re.search(r'what="([^"]+)"', call_str)
        what = what_match.group(1) if what_match else "measurement"
        args = call_str[len("measure("):].split(", what=", 1)[0]
        if what == "area":
            return f"Area of Region {args}: {emphasized}."
        if what in ("sides", "edge_count"):
            return f"The number of edges of Region {args}: {emphasized}."
        if what == "regions":
            return f"The number of regions in the frame: {emphasized}."
        if what == "orientation":
            vertices = args.replace(", ", " → ")
            return f"Cycle orientation for {vertices}: {emphasized}."
        if what == "distance":
            endpoints = natural_join(part.strip() for part in args.split(","))
            return f"Distance between {endpoints}: {emphasized}."
        if what == "angle":
            return f"Angle measurement for {args} (degrees): {emphasized}."
        return f"Measurement result: {emphasized}."

    if tool == "sort":
        by_match = re.search(r'by="([^"]+)"', call_str)
        by = by_match.group(1) if by_match else "value"
        lead = {
            "angle": "Angles from smallest to largest",
            "area": "Regions from smallest to largest by area",
            "left_right": "Vertices from left to right",
            "bottom_top": "Vertices from bottom to top",
            "distance": "Vertices from nearest to farthest",
        }.get(by, "Sorted objects")
        return f"{lead}: {emphasized}."

    return f"Result: {emphasized}."

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
        return {
            "type": "annotation",
            "kind": "point",
            "label": code_name(value),
            "origin": "tool_output",
            **_vertex_geometry(value),
        }
    if is_angle(value):
        return {
            "type": "annotation",
            "kind": "angle",
            "label": angle_name(value),
            **_angle_geometry(value),
        }
    if is_edgesel(value):
        return {
            "type": "annotation",
            "kind": "edge",
            "label": edge_name(value),
            "description": value.text,
            **_edge_geometry(value),
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

def record_tool_call(
    tool,
    function,
    input_text,
    output,
    output_text=None,
    call_type=None,
    display_text=None,
):
    calls = st.session_state.setdefault("tool_calls", [])
    tutorial_phase = None
    tutorial_step = None
    if IS_PRACTICE:
        guided_complete = st.session_state.get("practice_guided_complete", False)
        tutorial_phase = (
            "free_exploration" if guided_complete else "guided"
        )
        # Resolve the stage before appending the new call. Several tutorial
        # completion checks inspect existing calls, so resolving afterward
        # incorrectly attributes a successful call to the following step.
        tutorial_step = (
            None if guided_complete else current_practice_tool_stage()
        )
    if display_text is None:
        visible_log = st.session_state.get("log", [])
        display_text = visible_log[-1] if visible_log else output_text
    normalized_function = function
    if tool == "measure":
        if 'what="area"' in input_text:
            normalized_function = "area"
        elif 'what="distance"' in input_text:
            normalized_function = "distance"
        elif 'what="angle"' in input_text:
            normalized_function = "angle"
        elif 'what="edges"' in input_text:
            normalized_function = "edge_count"
        elif 'what="regions"' in input_text:
            normalized_function = "region_count"
        elif 'what="orientation"' in input_text:
            normalized_function = "cycle_orientation"
    call = {
        "order": len(calls) + 1,
        "status": "active",
        "undone": False,
        "cleared": False,
        "tool": tool,
        "function": normalized_function,
        "call_type": call_type or infer_call_type(output),
        "input": input_text,
        "output": output,
        "output_origin": "tool_execution",
        "output_text": output_text if output_text is not None else describe(output),
        "display_text": display_text,
        "timestamp": _ts(),
        "survey_elapsed_seconds": survey_elapsed_seconds(),
        "selection_context": [
            _selection_event_object(item)
            for item in st.session_state.get("selection", [])
        ],
        "selection_context_timing": "after_execution",
    }
    calls.append(call)
    if IS_PRACTICE:
        call["tutorial_phase"] = tutorial_phase
        call["tutorial_step"] = tutorial_step
        tutorial_calls = st.session_state.setdefault("tutorial_tool_calls", [])
        tutorial_call = dict(call)
        tutorial_call["order"] = len(tutorial_calls) + 1
        tutorial_calls.append(tutorial_call)
        tutorial_summary = st.session_state.setdefault("tutorial_summary", {})
        refresh_tutorial_summary_metrics()
        save_survey_results()

# ---- single-step UNDO -------------------------------------------------------
_UNDO_KEYS = ["selection", "selection_meta", "annotations", "lines", "angles", "named_edges",
              "unions", "union_consumed", "point_names", "counters",
              "program", "log"]

def push_undo():
    """Snapshot the tracked state BEFORE a mutating action so it can be undone."""
    snap = {
        # Tool calls are behavioral data, not only interface state. Keep the
        # count so undo_last() can mark calls made by the undone action without
        # deleting them from the participant's recorded trajectory.
        "_tool_call_count": len(st.session_state.get("tool_calls", [])),
    }
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
    selection_before = list(st.session_state.get("selection", []))
    snap = st.session_state.undo_stack.pop()
    calls = st.session_state.setdefault("tool_calls", [])
    previous_call_count = int(snap.get("_tool_call_count", len(calls)))
    newly_undone_calls = [
        call for call in calls[previous_call_count:]
        if not call.get("undone")
    ]
    if newly_undone_calls:
        undone_at = _ts()
        next_undo_order = (
            sum(bool(call.get("undone")) for call in calls) + 1
        )
        for offset, call in enumerate(newly_undone_calls):
            call["undone"] = True
            call["status"] = "undone"
            call["undone_at"] = undone_at
            call["undo_order"] = next_undo_order + offset
    for k, v in snap.items():
        if k.startswith("_"):
            continue
        st.session_state[k] = v
    events = st.session_state.setdefault("selection_events", [])
    undo_event = {
            "order": len(events) + 1,
            "action": "undo",
            "event_type": "interface",
            "undone_tool_call_orders": [
                call.get("order") for call in newly_undone_calls
            ],
            "selection_before": [
                _selection_event_object(item) for item in selection_before
            ],
            "selection_after": [
                _selection_event_object(item)
                for item in st.session_state.get("selection", [])
            ],
            "timestamp": _ts(),
            "survey_elapsed_seconds": survey_elapsed_seconds(),
        }
    events.append(undo_event)
    if IS_PRACTICE:
        tutorial_events = st.session_state.setdefault(
            "tutorial_selection_events", []
        )
        tutorial_event = dict(undo_event)
        tutorial_event["order"] = len(tutorial_events) + 1
        tutorial_event["tutorial_phase"] = (
            "free_exploration"
            if st.session_state.get("practice_guided_complete", False)
            else "guided"
        )
        tutorial_event["tutorial_step"] = (
            None
            if tutorial_event["tutorial_phase"] == "free_exploration"
            else current_practice_tool_stage()
        )
        tutorial_events.append(tutorial_event)
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
    add_log(participant_output_for_tool(tool, call_str, result, output_text))
    record_tool_call(tool, call_str.split("(", 1)[0], call_str, _tool_output(result), output_text)
    if st.session_state.get("practice_step") == "tools":
        if tool == "neighbors" and 'neighbors(A, "edge")' in call_str:
            st.session_state.practice_neighbors_done = True
            st.session_state.practice_pending_feedback = "neighbors"
        elif (
            tool == "neighbors"
            and st.session_state.get("practice_neighbors_done", False)
            and 'neighbors(A, "ordered"' in call_str
            and "go_counterclockwise=False" in call_str
        ):
            st.session_state.practice_ordered_neighbors_done = True
            st.session_state.practice_pending_feedback = "ordered_neighbors"
        elif (
            tool == "intersect"
            and st.session_state.get("practice_draw_line_done", False)
            and 'intersect(' in call_str
            and '"faces"' in call_str
        ):
            st.session_state.practice_intersect_done = True
            st.session_state.practice_pending_feedback = "intersect"
        elif (
            tool == "measure"
            and st.session_state.get("practice_intersect_done", False)
            and 'measure(B, what="area")' in call_str
        ):
            st.session_state.practice_measure_area_done = True
            st.session_state.practice_pending_feedback = "area"
        elif (
            tool == "measure"
            and st.session_state.get("practice_measure_area_done", False)
            and 'what="orientation"' in call_str
        ):
            st.session_state.practice_measure_orientation_done = True
            st.session_state.practice_pending_feedback = "orientation"
    clear_selection()
    st.rerun()

def finish_vertex(call_str, result, assign_prefix="v", trace_tool="vertex"):
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

    vertex_labels = [code_name(vertex) for vertex in new_pts if is_vertex(vertex)]
    if len(vertex_labels) == 1:
        add_program(f"{vertex_labels[0]} = {call_str}")
    elif len(vertex_labels) > 1:
        add_program(f"[{', '.join(vertex_labels)}] = {call_str}")
    else:
        add_program(call_str)
    output_text = answer_like_text(result)
    add_log(participant_output_for_tool(trace_tool, call_str, result, output_text))
    record_tool_call(trace_tool, "find" if trace_tool == "find" else "vertex",
                     call_str, _tool_output(result), output_text)
    if st.session_state.get("practice_step") == "tools":
        if (
            not st.session_state.get("practice_rightmost_vertex_done", False)
            and 'which="rightmost"' in call_str
            and "A" in call_str
        ):
            st.session_state.practice_rightmost_vertex_done = True
            st.session_state.practice_pending_feedback = "rightmost"
    st.session_state.click_targets = None
    st.session_state.pending_angle_vertex = None
    st.rerun()


def finish_edge(call_str, edge_selection, trace_tool="edge"):
    """Consume the region input and retain the newly grounded named edge."""
    clear_selection()
    edge_label = next_name("e")
    st.session_state.named_edges.append((edge_label, edge_selection))
    add_to_selection(edge_selection)
    add_program(f"{edge_label} = {call_str}")
    output_text = edge_label
    add_log(
        participant_output_for_tool(
            trace_tool, call_str, edge_selection, output_text
        )
    )
    record_tool_call(
        trace_tool,
        "find" if trace_tool == "find" else "edge",
        call_str,
        {
            "type": "annotation",
            "kind": "edge",
            "label": edge_label,
            **_edge_geometry(edge_selection),
        },
        output_text,
        "annotation",
    )
    st.session_state.click_targets = None
    st.session_state.pending_edge_options = []
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
    add_log(participant_output_for_tool("sort", call_str, result, ordered))
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
    if (
        st.session_state.get("practice_step") == "tools"
        and st.session_state.get("practice_measure_orientation_done", False)
        and by == "angle"
    ):
        st.session_state.practice_sort_angles_done = True
        st.session_state.practice_pending_feedback = "sort"
    clear_selection()
    st.rerun()

def run_tool(tool, modes):
    sel = st.session_state.selection
    s = sel_sig()
    try:
        # ---- VERTEX --------------------------------------------------------
        if tool == "vertex" or (
            tool == "find" and modes.get("object") == "vertex"
        ):
            trace_tool = "find" if tool == "find" else "vertex"
            if s["frame"]:
                which = modes["which"]
                result = T.find("frame", object="vertex", which=which)
                call_str = (
                    f'find("frame", object="vertex", which="{which}")'
                    if trace_tool == "find"
                    else f'vertex("frame", which="{which}")'
                )
                finish_vertex(call_str, result,
                              "v" if not isinstance(result, list) else "r",
                              trace_tool)
            elif len(s["regions"]) >= 2:
                onf = modes["on_frame"]
                result = T.find(
                    *s["regions"], object="vertex", on_frame=onf
                )
                args = ", ".join(o.letter for o in s["regions"])
                call_str = (
                    f'find({args}, object="vertex", on_frame={onf})'
                    if trace_tool == "find"
                    else f"vertex({args}, on_frame={onf})"
                )
                finish_vertex(call_str, result,
                              "v" if not isinstance(result, list) else "r",
                              trace_tool)
            else:
                reg = s["regions"][0]
                which = modes["which"]
                result = T.find(
                    reg, object="vertex", which=which
                )
                call_str = (
                    f'find({reg.letter}, object="vertex", which="{which}")'
                    if trace_tool == "find"
                    else f'vertex({reg.letter}, which="{which}")'
                )
                finish_vertex(call_str, result,
                              "v" if not isinstance(result, list) else "r",
                              trace_tool)

        # ---- EDGE ----------------------------------------------------------
        elif tool == "edge" or (
            tool == "find" and modes.get("object") == "edge"
        ):
            trace_tool = "find" if tool == "find" else "edge"
            region = s["regions"][0]
            meeting_objects = s["regions"][1:]
            segments = T.find(
                region, *meeting_objects, object="edge"
            )
            selected_labels = [obj.letter for obj in s["regions"]]
            description = (
                "the edge identified by Regions "
                + natural_join(selected_labels)
            )
            edge_selection = EdgeSel(
                segments,
                None,
                description,
            )
            argument_text = ", ".join(
                (
                    f'"{obj}"'
                    if isinstance(obj, str)
                    else obj.letter
                )
                for obj in meeting_objects
            )
            finish_edge(
                (
                    f'find({region.letter}, {argument_text}, object="edge")'
                    if trace_tool == "find"
                    else f"edge({region.letter}, {argument_text})"
                ),
                edge_selection,
                trace_tool,
            )

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
                call = f'draw({code_name(s["edges"][0])}, kind="{kind}")'
            else:
                kind = "full" if style == "full line" else "segment"
                line = T.draw(sel[0], sel[1], kind=kind)
                call = f'draw({code_name(sel[0])}, {code_name(sel[1])}, kind="{kind}")'
            name = next_name("L")
            st.session_state.lines.append((name, line))
            st.session_state.annotations.append({"kind": "line", "line": line, "label": name})
            add_program(f"{name} = {call}")
            if style == "ray":
                article = "an" if d == "up" else "a"
                add_log(
                    f"Drew **{name}**, {article} {d}ward ray "
                    f"from {code_name(sel[0])}."
                )
            elif style == "full line":
                if s["edges"]:
                    add_log(
                        f"Extended **{code_name(s['edges'][0])}** in both directions "
                        f"as **{name}**."
                    )
                else:
                    add_log(
                        f"Drew **{name}**, a full line through "
                        f"{code_name(sel[0])} and {code_name(sel[1])}."
                    )
            else:
                start_name = code_name(va) if s["edges"] else code_name(sel[0])
                end_name = code_name(vb) if s["edges"] else code_name(sel[1])
                add_log(f"Drew **{name}**, a segment between {start_name} and {end_name}.")
            record_tool_call(
                tool,
                "draw",
                call,
                {"type": "annotation", "kind": "line", "label": name},
                name,
                "annotation",
            )
            if (
                st.session_state.get("practice_step") == "tools"
                and st.session_state.get("practice_ordered_neighbors_done", False)
                and style == "segment"
            ):
                st.session_state.practice_draw_line_done = True
                st.session_state.practice_draw_line_ref = line
                st.session_state.practice_pending_feedback = "draw"
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
            if len(s["regions"]) != 2 or s["n"] != 2:
                st.error("Select exactly two regions.")
                return
            union_face_ids = {id(union["face"]) for union in st.session_state.unions}
            if any(id(region) in union_face_ids for region in s["regions"]):
                st.error("Select two original regions. A union cannot be merged again.")
                return
            fa, fb = s["regions"][0], s["regions"][1]
            fu = T.merge(fa, fb)
            uname = next_name("U")
            fu.letter = uname
            pair_vertices = []
            seen_pair_vertices = set()
            for source_face in (fa, fb):
                for vertex in source_face.vertices:
                    if id(vertex) not in seen_pair_vertices:
                        seen_pair_vertices.add(id(vertex))
                        pair_vertices.append(vertex)
            label_point = Graph.Vector(
                sum(vertex.p.x for vertex in pair_vertices) / len(pair_vertices),
                sum(vertex.p.y for vertex in pair_vertices) / len(pair_vertices),
            )
            st.session_state.unions.append(
                {"name": uname, "face": fu, "pair": (fa, fb),
                 "label_xy": DrawGraph.V2P(label_point)})
            st.session_state.union_consumed += [fa, fb]
            add_program(f"{uname} = merge({fa.letter}, {fb.letter})")
            add_log(f"Created merged Region **{uname}** from Regions {fa.letter} and {fb.letter}.")
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
            if (
                st.session_state.get("practice_step") == "tools"
                and st.session_state.get("practice_sort_angles_done", False)
                and {fa.letter, fb.letter} == {"A", "E"}
            ):
                st.session_state.practice_merge_done = True
                st.session_state.practice_pending_feedback = "merge"
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

            elif w == "angle":
                a = s["angles"][0]
                val = T.measure(a.vertex, a.face, what="angle")
                aname = angle_name(a)
                call_str = f'measure({aname}, what="angle")'
                var = next_name("r")
                add_program(f"{var} = {call_str}")
                output_text = f"{round(val, 2)}"
                add_log(participant_output_for_tool("measure", call_str, val, output_text))
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
                recorded_measure = "edge_count" if w == "sides" else w
                finish(
                    tool,
                    f'measure({reg.letter}, what="{recorded_measure}")',
                    val,
                )

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
        mark_tutorial_tool_error()
        tool_name = TOOL_LABELS.get(tool, tool).strip()
        participant_message = (
            f"❌ {tool_name} could not complete this operation. "
            "Check your selection and settings, then try again."
        )
        add_log(participant_message)
        record_tool_call(
            tool,
            "error",
            f"run {tool}",
            {"type": "error", "message": str(ex)},
            participant_message,
            "error",
        )
        clear_selection()
        st.rerun()

def show_completed_practice_step():
    """Run the current guided task with its expected inputs and show the normal result."""
    stage = current_practice_tool_stage()
    entry = start_tutorial_step(stage)
    entry["used_completed_example"] = True
    entry["completed_example_requested_at"] = _ts()
    save_survey_results()

    # Present a clean worked solution. Keep research history such as
    # selection_events and tutorial timing, but remove all visible workspace
    # state and prior tool output so only the correct example remains.
    clear_selection()
    for key in (
        "annotations",
        "lines",
        "angles",
        "named_edges",
        "unions",
        "union_consumed",
        "undo_stack",
        "program",
        "log",
        "tool_calls",
    ):
        st.session_state[key] = []
    st.session_state.pending_angle_vertex = None
    st.session_state.pending_edge_options = []
    st.session_state.click_targets = None
    st.session_state.point_names = {}
    st.session_state.counters = {
        "v": 1,
        "L": 1,
        "U": 1,
        "r": 1,
        "a": 1,
        "e": 1,
    }

    faces = {
        face.letter: face
        for face in res_map.faces
        if getattr(face, "bounded", False)
    }

    def select(*objects):
        clear_selection()
        for obj in objects:
            add_to_selection(obj)

    if stage == "rightmost":
        select(faces["A"])
        run_tool("find", {"object": "vertex", "which": "rightmost"})
    elif stage == "neighbors":
        select(faces["A"])
        run_tool("neighbors", {"kind": "edge"})
    elif stage == "ordered_neighbors":
        right_a = max(faces["A"].vertices, key=lambda vertex: vertex.p.x)
        select(faces["A"], right_a)
        run_tool("neighbors", {"kind": "ordered", "ccw": False})
    elif stage == "draw":
        left_b = min(faces["B"].vertices, key=lambda vertex: vertex.p.x)
        right_d = max(faces["D"].vertices, key=lambda vertex: vertex.p.x)
        select(left_b, right_d)
        run_tool("draw line", {"style": "segment"})
    elif stage == "intersect":
        if not st.session_state.lines:
            left_b = min(faces["B"].vertices, key=lambda vertex: vertex.p.x)
            right_d = max(faces["D"].vertices, key=lambda vertex: vertex.p.x)
            line = T.draw(left_b, right_d, kind="segment")
            st.session_state.lines.append(("L1", line))
            st.session_state.annotations.append({"kind": "line", "line": line, "label": "L1"})
            st.session_state.practice_draw_line_ref = line
        line_entry = st.session_state.lines[0]
        run_tool("intersect", {"line": line_entry, "target": "faces"})
    elif stage == "area":
        select(faces["B"])
        run_tool("measure", {"what": "area"})
    elif stage == "orientation":
        ring = list(res_map.vertices[:8])
        select(ring[3], ring[0], ring[5])
        run_tool("measure", {"what": "orientation"})
    elif stage == "sort":
        targets = [
            AngleSel(min(faces["B"].vertices, key=lambda vertex: vertex.p.x), faces["B"]),
            AngleSel(max(faces["A"].vertices, key=lambda vertex: vertex.p.x), faces["A"]),
            AngleSel(max(faces["D"].vertices, key=lambda vertex: vertex.p.x), faces["D"]),
        ]
        for angle in targets:
            if not any(saved == angle for _, saved in st.session_state.angles):
                st.session_state.angles.append((next_name("a"), angle))
        select(*targets)
        run_tool("sort", {"by": "angle"})
    else:  # merge
        select(faces["A"], faces["E"])
        run_tool("merge", {})

def remove_merged_region(index):
    """Remove one union and restore its source regions without clearing other work."""
    if index < 0 or index >= len(st.session_state.unions):
        return
    push_undo()
    union = st.session_state.unions.pop(index)
    union_face = union["face"]
    source_faces = union["pair"]
    union_name = union.get("name", getattr(union_face, "letter", "U"))

    kept_selection, kept_meta = [], []
    for obj, meta in zip(st.session_state.selection, st.session_state.selection_meta):
        if obj is union_face:
            continue
        kept_selection.append(obj)
        kept_meta.append(meta)
    st.session_state.selection = kept_selection
    st.session_state.selection_meta = kept_meta
    st.session_state.annotations = [
        annotation
        for annotation in st.session_state.annotations
        if annotation.get("obj") is not union_face
    ]
    st.session_state.union_consumed = [
        face
        for remaining_union in st.session_state.unions
        for face in remaining_union["pair"]
    ]

    if IS_PRACTICE and PRACTICE_STEP == "tools":
        st.session_state.practice_merge_done = False
        if st.session_state.get("practice_pending_feedback") == "merge":
            st.session_state.practice_pending_feedback = None
        st.session_state.practice_guided_complete = False

    source_names = [face.letter for face in source_faces]
    source_text = natural_join(source_names)
    add_log(f"Removed Region **{union_name}** and restored Regions **{source_text}**.")
    record_interface_event(
        "undo_merge",
        {
            "removed_union": union_name,
            "restored_regions": source_names,
        },
    )
    st.rerun()

def elapsed_between_timestamps(started_at, completed_at):
    if not started_at or not completed_at:
        return None
    timestamp_format = "%Y-%m-%d %H:%M:%S.%f"
    try:
        started = datetime.strptime(started_at, timestamp_format)
        completed = datetime.strptime(completed_at, timestamp_format)
    except (TypeError, ValueError):
        return None
    return round(max(0.0, (completed - started).total_seconds()), 3)

def survey_answer_key(question):
    return f"answer_{st.session_state.survey_question_index}_{question.get('question_id', '')}"

def current_trial_record(question, answer, is_correct=None):
    question_started_time = st.session_state.get("question_started_time")
    response_time_seconds = None
    if question_started_time is not None:
        response_time_seconds = round(time.time() - question_started_time, 3)
    return {
        "question_id": question.get("question_id", ""),
        "question_index": st.session_state.survey_question_index,
        "is_attention_check": bool(question.get("is_attention_check")),
        "answer": answer,
        "scratch_pad": st.session_state.get("scratch_pad", ""),
        "is_correct": is_correct,
        "question_started_at": st.session_state.get("question_started_at"),
        "survey_elapsed_seconds": survey_elapsed_seconds(),
        "response_time_seconds": response_time_seconds,
        "submitted_at": _ts(),
        "tool_calls": list(st.session_state.get("tool_calls", [])),
        "selection_events": list(st.session_state.get("selection_events", [])),
    }

def result_file_path():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    return participant_result_path(PARTICIPANT_ID)

def compact_response_record(question_id, response):
    """Normalize old and new response records into response schema v3."""
    if not isinstance(response, dict):
        return {}
    question = response.get("question", {})
    is_attention_check = response.get("is_attention_check")
    if is_attention_check is None and isinstance(question, dict):
        is_attention_check = bool(question.get("is_attention_check"))
    return {
        "question_id": str(response.get("question_id") or question_id),
        "question_index": response.get("question_index"),
        "is_attention_check": bool(is_attention_check),
        "answer": response.get("answer", ""),
        "scratch_pad": response.get("scratch_pad", ""),
        "is_correct": response.get("is_correct"),
        "question_started_at": response.get("question_started_at"),
        "survey_elapsed_seconds": response.get("survey_elapsed_seconds"),
        "response_time_seconds": response.get("response_time_seconds"),
        "submitted_at": response.get("submitted_at"),
        "tool_calls": list(response.get("tool_calls", [])),
        "selection_events": list(response.get("selection_events", [])),
    }

def response_score_summary(responses):
    records = [
        response
        for response in responses.values()
        if isinstance(response, dict)
        and str(response.get("answer", "")).strip()
        and isinstance(response.get("is_correct"), bool)
    ]
    substantive = [
        response for response in records
        if not response.get("is_attention_check", False)
    ]
    attention = [
        response for response in records
        if response.get("is_attention_check", False)
    ]

    def score_group(group):
        correct = sum(bool(response.get("is_correct")) for response in group)
        total = len(group)
        return correct, total, round(correct / total, 4) if total else None

    substantive_correct, substantive_total, substantive_accuracy = score_group(
        substantive
    )
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

def response_tool_summary(responses):
    substantive = [
        response
        for response in responses.values()
        if isinstance(response, dict)
        and not response.get("is_attention_check", False)
    ]
    tool_counts = {}
    total_tool_calls = 0
    undone_tool_calls = 0
    cleared_tool_calls = 0
    questions_using_tools = 0
    for response in substantive:
        calls = [
            call for call in response.get("tool_calls", [])
            if isinstance(call, dict)
        ]
        if calls:
            questions_using_tools += 1
        total_tool_calls += len(calls)
        undone_tool_calls += sum(bool(call.get("undone")) for call in calls)
        cleared_tool_calls += sum(bool(call.get("cleared")) for call in calls)
        for call in calls:
            tool = str(call.get("tool", "unknown"))
            tool_counts[tool] = tool_counts.get(tool, 0) + 1
    return {
        "total_tool_calls": total_tool_calls,
        "active_tool_calls": sum(
            not call.get("undone") and not call.get("cleared")
            for response in substantive
            for call in response.get("tool_calls", [])
            if isinstance(call, dict)
        ),
        "undone_tool_calls": undone_tool_calls,
        "cleared_tool_calls": cleared_tool_calls,
        "questions_using_tools": questions_using_tools,
        "tool_counts": dict(sorted(tool_counts.items())),
    }

def current_dataset_metadata():
    if not DATASET_PATH:
        return {"version": "fallback", "file": None, "sha256": None}
    metadata = {}
    try:
        with open(DATASET_PATH, "r", encoding="utf-8") as f:
            dataset_payload = json.load(f)
        if isinstance(dataset_payload, dict):
            metadata = {
                "version": dataset_payload.get("dataset_version"),
                "role": dataset_payload.get("dataset_role"),
                "generated_at": dataset_payload.get("generated_at"),
            }
    except (OSError, ValueError, TypeError):
        metadata = {}
    try:
        with open(DATASET_PATH, "rb") as f:
            dataset_sha256 = hashlib.sha256(f.read()).hexdigest()
    except OSError:
        dataset_sha256 = None
    metadata.update(
        {
            "file": os.path.basename(DATASET_PATH),
            "sha256": dataset_sha256,
        }
    )
    return metadata

def save_survey_results():
    compact_responses = {
        str(question_id): compact_response_record(question_id, response)
        for question_id, response in st.session_state.get(
            "survey_responses", {}
        ).items()
        if isinstance(response, dict)
    }
    st.session_state.survey_responses = compact_responses
    score_summary = response_score_summary(compact_responses)
    tool_summary = response_tool_summary(compact_responses)
    tutorial_summary = refresh_tutorial_summary_metrics()
    completed_at = st.session_state.get("survey_completed_timestamp")
    if st.session_state.get("survey_completed") and not completed_at:
        completed_at = _ts()
        st.session_state.survey_completed_timestamp = completed_at
    study_completed_at = st.session_state.get("study_completed_timestamp")
    if st.session_state.get("post_survey_completed") and not study_completed_at:
        study_completed_at = _ts()
        st.session_state.study_completed_timestamp = study_completed_at
    recorded_survey_elapsed = (
        max(
            (
                response.get("survey_elapsed_seconds") or 0
                for response in compact_responses.values()
            ),
            default=0,
        )
        if compact_responses
        else 0
    )
    survey_duration_seconds = (
        elapsed_between_timestamps(
            st.session_state.get("survey_started_timestamp"),
            completed_at,
        )
        if completed_at
        else recorded_survey_elapsed
    )
    saved_at = _ts()
    study_duration_end = study_completed_at or saved_at
    survey_duration_end = completed_at or saved_at
    payload = {
        "response_schema_version": RESPONSE_SCHEMA_VERSION,
        "code_version": CODE_VERSION,
        "condition": "compositional",
        "participant_id": PARTICIPANT_ID,
        "survey_instance": PARTICIPANT_ID,
        "survey_version": SURVEY_VERSION,
        "survey_form": st.session_state.get("survey_form"),
        "dataset": current_dataset_metadata(),
        "saved_at": saved_at,
        "study_started_at": st.session_state.get("study_started_timestamp"),
        "study_completed_at": study_completed_at,
        "total_duration_seconds": elapsed_between_timestamps(
            st.session_state.get("study_started_timestamp"),
            study_duration_end,
        ),
        "survey_started_at": st.session_state.get("survey_started_timestamp"),
        "survey_completed_at": completed_at,
        "survey_duration_seconds": (
            elapsed_between_timestamps(
                st.session_state.get("survey_started_timestamp"),
                survey_duration_end,
            )
            if st.session_state.get("survey_started_timestamp")
            else survey_duration_seconds
        ),
        "survey_question_index": st.session_state.get("survey_question_index", 0),
        "max_confirmed_question_index": st.session_state.get(
            "max_confirmed_question_index", -1
        ),
        "survey_completed": st.session_state.get("survey_completed", False),
        "tutorial_completed": st.session_state.get("tutorial_completed", False),
        "post_survey_completed": st.session_state.get("post_survey_completed", False),
        "entry_route": st.session_state.get("entry_route"),
        "question_bank": QUESTION_BANK,
        "responses": compact_responses,
        "score_summary": score_summary,
        "tool_usage_summary": tool_summary,
        "post_survey_responses": st.session_state.get("post_survey_responses", {}),
        "tutorial_summary": tutorial_summary,
    }
    if DATABASE_URL:
        _save_survey_postgres(payload)
        destination = "Postgres"
    else:
        destination = result_file_path()
        with open(destination, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
    st.session_state.last_result_path = destination
    return destination

if not st.session_state.landing_choice_made:
    st.title("Survey Instructions")
    st.markdown(
        "In this survey, you will answer questions based on a series of diagrams.\n\n"
        "**Your goal is to answer as many questions correctly as possible.**\n\n"
        "Before the survey begins, you will complete a brief tutorial to help "
        "you become familiar with the task and learn how to use the survey interface.\n\n"
        "The tutorial is **for practice only and is not scored**.\n\n"
        "Please use **only the tools provided within the survey interface**. Do not "
        "use any external tools or assistance, including pen and paper, calculators, "
        "other websites, or AI tools.\n\n"
        "Please complete the survey in one sitting using a laptop or desktop computer.\n\n"
        "Click Start Tutorial when you are ready."
    )

    if st.button(
        "Start Tutorial",
        type="primary",
        use_container_width=False,
    ):
        st.session_state.landing_choice_made = True
        st.session_state.entry_route = "tutorial"
        tutorial_summary = st.session_state.setdefault("tutorial_summary", {})
        if not tutorial_summary.get("started_at"):
            tutorial_summary["started_at"] = _ts()
        tutorial_summary["completion_status"] = "in_progress"
        start_tutorial_step("selection_practice")
        save_survey_results()
        st.rerun()
    st.stop()

if st.session_state.survey_completed and st.session_state.post_survey_completed:
    # Use an explicit completion banner instead of Streamlit's theme-dependent
    # alert component, whose text can be vertically clipped in some browsers.
    st.markdown(
        '<div style="box-sizing:border-box; width:100%; padding:0.8rem 1rem; '
        'border-radius:0.65rem; background:#e8f7ec; color:#16833a; '
        'font-size:1rem; font-weight:500; line-height:1.5; overflow:visible;">'
        'Survey complete. Thank you.</div>',
        unsafe_allow_html=True,
    )
    if st.session_state.last_result_path:
        st.caption("Your responses have been saved.")
    st.stop()

if st.session_state.survey_completed and not st.session_state.post_survey_completed:
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
            display: grid !important;
            grid-template-columns: repeat(5, 1fr) !important;
            gap: 0 !important;
            width: min(100%, 380px) !important;
        }
        div[data-testid="stForm"] div[role="radiogroup"]:has(> label:nth-child(5)) > label {
            margin: 0 !important;
            width: 100% !important;
            justify-content: center !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    missing_preview_fields = set(
        st.session_state.get("post_survey_missing_required", [])
    )

    def show_required_message(key):
        if key in missing_preview_fields:
            st.markdown(
                "<div style='color:#d32f2f;font-size:0.875rem;margin-top:-0.6rem;"
                "margin-bottom:0.8rem'>Please select a response.</div>",
                unsafe_allow_html=True,
            )

    def five_point_scale(prompt, left_label, middle_label, right_label, key):
        st.markdown(
            f"<strong>{html.escape(prompt)}</strong> "
            "<span style='color:#d32f2f'>*</span>",
            unsafe_allow_html=True,
        )
        value = st.radio(
            prompt,
            [1, 2, 3, 4, 5],
            index=None,
            horizontal=True,
            label_visibility="collapsed",
            key=key,
        )
        st.markdown(
            "<div style='width:min(100%, 380px);display:grid;"
            "grid-template-columns:1fr 1fr 1fr;align-items:start;"
            "color:#6b7280;font-size:0.875rem;margin-top:-0.4rem;margin-bottom:1rem'>"
            f"<div style='text-align:left'>{left_label}</div>"
            f"<div style='text-align:center'>{middle_label}</div>"
            f"<div style='text-align:right'>{right_label}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        show_required_message(key)
        return value

    saved_preview = st.session_state.get("post_survey_responses", {})
    preview_widget_fields = {
        "preview_tutorial_clarity": "tutorial_easy_to_understand",
        "preview_instruction_clarity": "instructions_clear",
        "preview_tools_easy_to_use": "tools_easy_to_use",
        "preview_tools_useful": "tools_useful_for_answering",
        "preview_questions_easy_to_answer": "questions_easy_to_answer",
        "preview_survey_length_appropriate": "survey_length_appropriate",
        "preview_used_external_assistance": "used_external_assistance",
        "preview_external_assistance_details": "external_assistance_details",
        "preview_experienced_technical_issues": "experienced_technical_issues",
        "preview_technical_issue_details": "technical_issue_details",
        "preview_other_feedback": "other_feedback",
    }
    if "preview_other_feedback" not in st.session_state:
        saved_feedback = [
            str(saved_preview.get(key, "")).strip()
            for key in ("other_feedback", "ambiguous_questions", "difficult_tools")
        ]
        combined_saved_feedback = "\n\n".join(
            feedback for feedback in saved_feedback if feedback
        )
        if combined_saved_feedback:
            st.session_state.preview_other_feedback = combined_saved_feedback
    for widget_key, response_key in preview_widget_fields.items():
        if widget_key not in st.session_state and response_key in saved_preview:
            st.session_state[widget_key] = saved_preview[response_key]

    with st.form("post_survey_questionnaire_form"):
        if missing_preview_fields:
            st.error("Please answer the highlighted questions before continuing.")
        st.caption(
            "Required questions are marked with *. For each statement, select "
            "1 (Strongly disagree) to 5 (Strongly agree)."
        )
        five_point_scale(
            "The tutorial was easy to understand.",
            "Strongly disagree",
            "Neutral",
            "Strongly agree",
            key="preview_tutorial_clarity",
        )
        five_point_scale(
            "The instructions in the survey were clear.",
            "Strongly disagree",
            "Neutral",
            "Strongly agree",
            key="preview_instruction_clarity",
        )
        five_point_scale(
            "The tools were easy to operate.",
            "Strongly disagree",
            "Neutral",
            "Strongly agree",
            key="preview_tools_easy_to_use",
        )
        five_point_scale(
            "The tools were useful for answering the questions.",
            "Strongly disagree",
            "Neutral",
            "Strongly agree",
            key="preview_tools_useful",
        )
        five_point_scale(
            "The survey questions were easy to answer.",
            "Strongly disagree",
            "Neutral",
            "Strongly agree",
            key="preview_questions_easy_to_answer",
        )
        five_point_scale(
            "The length of the survey was appropriate.",
            "Strongly disagree",
            "Neutral",
            "Strongly agree",
            key="preview_survey_length_appropriate",
        )
        st.markdown("**Use of external assistance**")
        st.caption(
            "Your answer will not affect your compensation or survey results. "
            "We ask only to better understand how participants completed the survey."
        )
        external_assistance_prompt = (
            "Did you use any external assistance, such as paper, a calculator, "
            "a search engine, or help from another person, while answering the questions?"
        )
        st.markdown(
            f"{html.escape(external_assistance_prompt)} "
            "<span style='color:#d32f2f'>*</span>",
            unsafe_allow_html=True,
        )
        st.radio(
            external_assistance_prompt,
            ["No", "Yes", "Prefer not to say"],
            index=None,
            horizontal=True,
            label_visibility="collapsed",
            key="preview_used_external_assistance",
        )
        show_required_message("preview_used_external_assistance")
        st.text_input(
            "If yes, what did you use? (Optional)",
            key="preview_external_assistance_details",
        )
        st.markdown("**Technical issues**")
        technical_issues_prompt = (
            "Did you experience any technical problems while completing the survey?"
        )
        st.markdown(
            f"{html.escape(technical_issues_prompt)} "
            "<span style='color:#d32f2f'>*</span>",
            unsafe_allow_html=True,
        )
        st.radio(
            technical_issues_prompt,
            ["No", "Yes"],
            index=None,
            horizontal=True,
            label_visibility="collapsed",
            key="preview_experienced_technical_issues",
        )
        show_required_message("preview_experienced_technical_issues")
        st.text_input(
            "If yes, please describe what happened. (Optional)",
            key="preview_technical_issue_details",
        )
        st.markdown("#### Additional feedback")
        st.text_area(
            "Is there anything else you would like to share? (Optional)",
            key="preview_other_feedback",
        )
        if st.form_submit_button("Submit", type="primary"):
            required_fields = [
                "preview_tutorial_clarity",
                "preview_instruction_clarity",
                "preview_tools_easy_to_use",
                "preview_tools_useful",
                "preview_questions_easy_to_answer",
                "preview_survey_length_appropriate",
                "preview_used_external_assistance",
                "preview_experienced_technical_issues",
            ]
            missing = [
                key for key in required_fields
                if st.session_state.get(key) is None
            ]
            if missing:
                st.session_state.post_survey_missing_required = missing
                st.rerun()
            else:
                st.session_state.post_survey_missing_required = []
                st.session_state.post_survey_responses = {
                    response_key: st.session_state.get(widget_key)
                    for widget_key, response_key in preview_widget_fields.items()
                }
                st.session_state.post_survey_responses.update(
                    {
                        "placement": "post_survey",
                        "submitted_at": _ts(),
                    }
                )
                st.session_state.post_survey_preview_seen = True
                st.session_state.post_survey_completed = True
                save_survey_results()
                st.rerun()
    st.stop()

# ============================================================
# 9. LAYOUT  (LEFT: tools/selection/run | MIDDLE: diagram+selection+saved |
#             RIGHT: quick actions + scratch pad + output)
# ============================================================
question_number = st.session_state.survey_question_index + 1
if (
    not IS_PRACTICE
    and st.session_state.get("last_question_scroll_index")
    != st.session_state.survey_question_index
):
    components.html(
        """
        <script>
        setTimeout(function () {
          try { window.parent.scrollTo({top: 0, left: 0, behavior: "instant"}); }
          catch (err) { window.parent.scrollTo(0, 0); }
        }, 0);
        </script>
        """,
        height=0,
    )
    st.session_state.last_question_scroll_index = (
        st.session_state.survey_question_index
    )
top_left, top_right = st.columns([3, 1], gap="small")
with top_left:
    if IS_PRACTICE:
        st.caption("Practice")
    else:
        # Match the annotation survey: progress is its own line immediately
        # above the question prompt.
        st.caption(f"Question {question_number} of {len(QUESTION_BANK)}")
    raw_question_text = (
        practice_question_text_for_step(PRACTICE_STEP)
        if IS_PRACTICE
        else str(QUESTION.get("question_text", ""))
    )
    question_paragraphs = [
        paragraph.replace("\n", " ").strip()
        for paragraph in re.split(r"\n\s*\n", html.escape(raw_question_text))
        if paragraph.strip()
    ]
    question_text = "".join(
        f'<div style="margin:{"0" if index == 0 else "0.45rem"} 0 0 0;">'
        f'{paragraph}</div>'
        for index, paragraph in enumerate(question_paragraphs)
    )
    tutorial_title_height = "2.7em" if IS_PRACTICE else "auto"
    st.markdown(
        f'<div style="font-size:18px; font-weight:600; line-height:1.35; '
        f'min-height:{tutorial_title_height}; margin:0.1rem 0 0.9rem 0;">'
        f'{question_text}</div>',
        unsafe_allow_html=True,
    )

answer_panel, action_panel = st.columns([8, 3], gap="small")

if IS_PRACTICE and PRACTICE_STEP == "tools":
    st.markdown(
        """
        <style>
        .st-key-answer_panel_content {
            min-height: 24rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

with answer_panel.container(key="answer_panel_content"):
    if IS_PRACTICE and PRACTICE_STEP == "select":
        # The first practice instructions live beside the diagram below so the
        # diagram stays visible in the first viewport.
        pass
    else:
        practice_rightmost_done = (
            IS_PRACTICE
            and PRACTICE_STEP == "tools"
            and practice_rightmost_vertex_done()
        )
        practice_neighbor_done = (
            IS_PRACTICE
            and PRACTICE_STEP == "tools"
            and practice_neighbors_done()
        )
        practice_ordered_neighbor_done = (
            IS_PRACTICE
            and PRACTICE_STEP == "tools"
            and practice_ordered_neighbors_done()
        )
        practice_draw_done = (
            IS_PRACTICE
            and PRACTICE_STEP == "tools"
            and st.session_state.get("practice_draw_line_done", False)
        )
        practice_intersection_done = (
            IS_PRACTICE
            and PRACTICE_STEP == "tools"
            and st.session_state.get("practice_intersect_done", False)
        )
        practice_area_done = (
            IS_PRACTICE
            and PRACTICE_STEP == "tools"
            and st.session_state.get("practice_measure_area_done", False)
        )
        practice_orientation_done = (
            IS_PRACTICE
            and PRACTICE_STEP == "tools"
            and st.session_state.get("practice_measure_orientation_done", False)
        )
        practice_angle_sort_done = (
            IS_PRACTICE
            and PRACTICE_STEP == "tools"
            and st.session_state.get("practice_sort_angles_done", False)
        )
        practice_merge_complete = (
            IS_PRACTICE
            and PRACTICE_STEP == "tools"
            and practice_merge_done()
        )
        if IS_PRACTICE and PRACTICE_STEP == "tools":
            pending_feedback = st.session_state.get("practice_pending_feedback")
            if st.session_state.get("practice_guided_complete", False):
                st.markdown(PRACTICE_TOOL_FINAL_TEXT)
                if st.button("Start Survey", type="primary"):
                    st.session_state.tutorial_completed = True
                    st.session_state.answer_feedback = None
                    st.session_state.scratch_pad = ""
                    st.session_state.survey_started_at = time.time()
                    st.session_state.definitions_open = False
                    st.session_state.tool_guide_open = False
                    mark_tutorial_completed()
                    st.rerun()
            elif pending_feedback:
                if pending_feedback == "rightmost":
                    output = (
                        practice_last_output("find", 'which="rightmost"')
                        or practice_last_output("vertex", 'which="rightmost"')
                        or "The labeled vertex"
                    )
                    message = f"Great — {output} is the rightmost vertex of Region A."
                elif pending_feedback == "neighbors":
                    output = practice_last_output("neighbors", 'neighbors(A, "edge")')
                    message = f"Very good — {output} are the regions that share an edge with Region A."
                elif pending_feedback == "ordered_neighbors":
                    output = practice_last_output(
                        "neighbors",
                        'neighbors(A, "ordered"',
                    ) or "the listed regions"
                    message = (
                        f"Very good — the output is {output}. Begin at the selected vertex "
                        "and move clockwise around Region A's boundary. The output lists the "
                        "surrounding regions in the order you encounter them.\n\nHere, "
                        "Outside represents the area outside the frame and appears because "
                        "Region A touches the frame. Outside is not a labeled region."
                    )
                elif pending_feedback == "draw":
                    output = practice_last_output("draw line") or "The labeled line"
                    message = f"Very good — {output} is the line segment connecting the two selected vertices."
                elif pending_feedback == "intersect":
                    output = practice_last_output("intersect", '"faces"') or "the listed regions"
                    message = f"Very good — the line segment crosses these regions: {output}."
                elif pending_feedback == "area":
                    output = practice_last_output("measure", 'what="area"')
                    message = f"Very good — Measure found that Region B has area {output}."
                elif pending_feedback == "orientation":
                    output = practice_last_output("measure", 'what="orientation"')
                    message = (
                        f"Very good — the three vertices form a {output} cycle when followed "
                        "in the order in which you clicked them."
                    )
                elif pending_feedback == "sort":
                    output = practice_last_output("sort") or "the selected angles"
                    message = f"Very good — the result {output} lists the selected angles from smallest to largest."
                else:  # merge
                    output = practice_last_output("merge") or "U"
                    message = (
                        f"Very good — Merge created Region {output}, the union of Regions A and E. "
                        "The two neighboring regions are now treated as one larger region."
                    )
                st.success(message)
                if st.button("Continue", type="primary"):
                    continue_after_practice_feedback(pending_feedback)
            elif practice_ordered_neighbor_done:
                if practice_angle_sort_done:
                    st.markdown(PRACTICE_MERGE_GUIDE_TEXT)
                elif practice_orientation_done:
                    st.markdown(PRACTICE_SORT_ANGLES_GUIDE_TEXT)
                elif practice_area_done:
                    st.markdown(PRACTICE_MEASURE_ORIENTATION_GUIDE_TEXT)
                elif practice_intersection_done:
                    st.markdown(PRACTICE_MEASURE_AREA_GUIDE_TEXT)
                elif practice_draw_done:
                    st.markdown(PRACTICE_INTERSECT_GUIDE_TEXT)
                else:
                    st.markdown(PRACTICE_DRAW_LINE_GUIDE_TEXT)
            elif practice_neighbor_done:
                st.markdown(PRACTICE_ORDERED_NEIGHBORS_GUIDE_TEXT)
            elif practice_rightmost_done:
                st.markdown(PRACTICE_NEIGHBORS_GUIDE_TEXT)
            else:
                st.markdown(PRACTICE_TOOL_GUIDE_TEXT)
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
                            st.session_state.answer_feedback = None
                            st.session_state.scratch_pad = ""
                            st.session_state.survey_started_at = time.time()
                            st.session_state.definitions_open = False
                            st.session_state.tool_guide_open = False
                            mark_tutorial_completed()
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
    if (
        IS_PRACTICE
        and PRACTICE_STEP == "tools"
        and not st.session_state.get("practice_pending_feedback")
        and not st.session_state.get("practice_guided_complete", False)
    ):
        with st.expander("Having trouble with this step?"):
            st.caption(
                "Click below to see this step completed for you. Then click Continue."
            )
            if st.button(
                "Show Completed Example",
                key="show_completed_practice_step",
                use_container_width=True,
            ):
                show_completed_practice_step()
    st.session_state.setdefault(
        "definitions_open",
        IS_PRACTICE and PRACTICE_STEP == "select",
    )

    definitions_open = st.session_state["definitions_open"]
    if st.button(("▾ Definitions" if definitions_open else "▸ Definitions"), key="toggle_definitions", use_container_width=True):
        st.session_state["definitions_open"] = not definitions_open
        st.rerun()
    if st.session_state["definitions_open"]:
        if IS_PRACTICE and PRACTICE_STEP == "select":
            if practice_selected_entity_types() != set(PRACTICE_REQUIRED_SELECTIONS):
                practice_definitions = PRACTICE_CORE_DEFINITIONS_TEXT
            elif not st.session_state.get("practice_entities_feedback_acknowledged", False):
                practice_definitions = PRACTICE_CORE_DEFINITIONS_TEXT
            elif not st.session_state.get("practice_frame_review_done", False):
                practice_definitions = PRACTICE_FRAME_DEFINITIONS_TEXT
            else:
                practice_definitions = PRACTICE_DIRECTION_DEFINITIONS_TEXT
            st.markdown(practice_definitions)
        else:
            st.markdown(DEFINITIONS_TEXT)

    show_tool_guide = not (IS_PRACTICE and PRACTICE_STEP == "select")
    if show_tool_guide:
        st.session_state.setdefault("tool_guide_open", False)
        tool_guide_open = st.session_state["tool_guide_open"]
        if st.button(
            ("▾ Tool Guide" if tool_guide_open else "▸ Tool Guide"),
            key="toggle_tool_guide",
            use_container_width=True,
        ):
            st.session_state["tool_guide_open"] = not tool_guide_open
            st.rerun()
        if st.session_state["tool_guide_open"]:
            st.markdown(TOOL_GUIDE_TEXT)

    st.markdown(
        '<div style="font-size:1.25rem; font-weight:600; margin:0.4rem 0 0.25rem 0;">Quick actions</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <style>
        div[class*="st-key-quick_action_buttons"] button {
            justify-content: center !important;
            min-height: 2.5rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="quick_action_buttons"):
        qcols = st.columns(2)
        if qcols[0].button("↩ Undo", help="Undo last move", use_container_width=True,
                           disabled=not st.session_state.undo_stack):
            undo_last()
        if qcols[1].button("Clear all", use_container_width=True):
            selection_before = list(st.session_state.selection)
            calls_before_clear = list(st.session_state.get("tool_calls", []))
            cleared_at = _ts()
            for call in calls_before_clear:
                if not call.get("undone") and not call.get("cleared"):
                    call["cleared"] = True
                    call["status"] = "cleared"
                    call["cleared_at"] = cleared_at
            clear_selection()
            record_selection_event(
                "clear_all",
                selection_before=selection_before,
            )
            st.session_state.selection_events[-1]["cleared_tool_call_orders"] = [
                call.get("order") for call in calls_before_clear
                if call.get("cleared_at") == cleared_at
            ]
            for k in ["annotations", "lines", "angles", "named_edges", "unions",
                      "union_consumed", "undo_stack", "program", "log"]:
                st.session_state[k] = []
            st.session_state.pending_angle_vertex = None
            st.session_state.pending_edge_options = []
            st.session_state.click_targets = None
            st.session_state.point_names = {}
            st.session_state.counters = {"v": 1, "L": 1, "U": 1, "r": 1, "a": 1, "e": 1}
            st.rerun()
    show_practice_action_hint = (
        IS_PRACTICE
        and PRACTICE_STEP == "tools"
    )
    if show_practice_action_hint:
        st.markdown(
            '<div style="background:#eff6ff; color:#1e3a8a; '
            'border:1px solid #bfdbfe; border-radius:0.5rem; '
            'padding:0.55rem 0.7rem; margin:0.75rem 0 0.5rem; font-size:0.9rem;">'
            'If you make a mistake, use <strong>Undo</strong> to reverse your '
            'most recent action. Use <strong>Clear all</strong> to reset the '
            'practice workspace.'
            '</div>',
            unsafe_allow_html=True,
        )

    right_workspace = st.container()

with left_workspace:
    col_ctrl, col_map = st.columns([3, 5], gap="small")
col_io = right_workspace

# ----------------------------------------------------------------------------
# LEFT PANEL — tools + active tool config + RUN + selection
# ----------------------------------------------------------------------------
with col_ctrl:
    SHOW_TOOLS = not (IS_PRACTICE and PRACTICE_STEP == "select")
    PRACTICE_OBJECTS_READY = (
        IS_PRACTICE
        and PRACTICE_STEP == "select"
        and practice_selected_entity_types() == set(PRACTICE_REQUIRED_SELECTIONS)
    )
    PRACTICE_ENTITIES_FEEDBACK = (
        PRACTICE_OBJECTS_READY
        and not st.session_state.get("practice_entities_feedback_acknowledged", False)
    )
    PRACTICE_FRAME_REVIEW = (
        PRACTICE_OBJECTS_READY
        and st.session_state.get("practice_entities_feedback_acknowledged", False)
        and not st.session_state.get("practice_frame_review_done", False)
    )
    PRACTICE_DIRECTION_DEMO = (
        PRACTICE_OBJECTS_READY
        and st.session_state.get("practice_entities_feedback_acknowledged", False)
        and st.session_state.get("practice_frame_review_done", False)
    )
    PRACTICE_CONCEPT_REVIEW = (
        PRACTICE_ENTITIES_FEEDBACK or PRACTICE_FRAME_REVIEW or PRACTICE_DIRECTION_DEMO
    )
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

        if tool in ("find", "vertex"):
            if tool == "find":
                current_selection_filter = st.session_state.get(
                    "selection_filter"
                )
                previous_selection_filter = st.session_state.get(
                    "_find_seen_selection_filter"
                )
                if (
                    current_selection_filter == "Edge"
                    and previous_selection_filter != "Edge"
                ):
                    # Selection → Edge means the participant is thinking about
                    # edges, so surface Find Edge immediately. They can then
                    # switch Selection back to Region to choose the owner.
                    st.session_state.rad_find_object = "edge"
                st.session_state._find_seen_selection_filter = (
                    current_selection_filter
                )
                find_default = (
                    1
                    if current_selection_filter == "Edge"
                    else 0
                )
                modes["object"] = st.radio(
                    "What do you want to find?",
                    ["vertex", "edge"],
                    format_func=lambda value: (
                        "Find Vertex" if value == "vertex" else "Find Edge"
                    ),
                    index=find_default,
                    horizontal=True,
                    key="rad_find_object",
                )
            else:
                modes["object"] = "vertex"

            if modes["object"] == "edge":
                if len(s["regions"]) >= 2 and len(s["regions"]) == s["n"]:
                    selected_labels = natural_join(
                        region.letter for region in s["regions"]
                    )
                    st.caption(
                        f"Will find the edge identified by Regions "
                        f"{selected_labels}."
                    )
            elif s["frame"]:
                modes["which"] = st.radio(
                    "Which frame corner?",
                    ["all", "top_left", "top_right", "bottom_left", "bottom_right"],
                    horizontal=True, key="rad_vtx_frame")
            elif len(s["regions"]) >= 2:
                modes["on_frame"] = st.radio(
                    "Is the meeting vertex on the frame?", [False, True],
                    format_func=lambda b: "Yes" if b else "No",
                    index=None if IS_PRACTICE and PRACTICE_STEP == "tools" else 0,
                    horizontal=True, key="rad_vtx_onframe")
            else:
                vertex_options = [
                    "all", "leftmost", "rightmost", "topmost", "bottommost",
                    "sharpest", "widest",
                ]
                vertex_default_index = (
                    None if IS_PRACTICE and PRACTICE_STEP == "tools" else 0
                )
                modes["which"] = st.radio(
                    "Which corner?",
                    vertex_options,
                    index=vertex_default_index,
                    horizontal=True,
                    key="rad_vtx_corner")

        elif tool == "edge":
            modes["object"] = "edge"
            st.caption(
                "Select two or more Regions that uniquely identify the edge. "
                "Selection order does not matter."
            )

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
                    "Walk direction", [False, True],
                    format_func=lambda b: "Counterclockwise" if b else "Clockwise",
                    index=None if IS_PRACTICE and PRACTICE_STEP == "tools" else 0,
                    horizontal=True, key="rad_nbr_ccw")
                st.caption("Region + corner → the regions passed, in walking order.")
            elif s["regions"]:
                modes["kind"] = st.radio(
                    "Neighbor type", ["edge", "vertex"],
                    format_func=lambda k: "Share an edge" if k == "edge"
                    else "Touch only at a corner",
                    index=None if IS_PRACTICE and PRACTICE_STEP == "tools" else 0,
                    horizontal=True, key="rad_nbr_kind")

        elif tool == "draw line":
            modes["style"] = st.radio(
                "Line style",
                ["segment", "full line", "ray"],
                format_func=lambda value: "extend edge" if value == "full line" else value,
                index=None if IS_PRACTICE and PRACTICE_STEP == "tools" else 0,
                horizontal=True,
                key="rad_style",
            )
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
                                  index=None if IS_PRACTICE and PRACTICE_STEP == "tools" else 0,
                                  key="rad_intersect")
                if choice and choice.startswith("Which"):
                    modes["target"] = "faces"
                elif choice:
                    others = [j for j in range(len(st.session_state.lines)) if j != li]
                    if others:
                        lj = st.selectbox("Other line", others,
                                          format_func=lambda j: st.session_state.lines[j][0],
                                          key="sel_line2")
                        modes["target"] = st.session_state.lines[lj]
                    else:
                        st.warning("Draw a second line first.")
                        modes["target"] = None
                else:
                    modes["target"] = None

        elif tool == "measure":
            modes["what"] = st.radio("Measure what?",
                                     ["distance", "angle", "area", "sides", "regions",
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
            elif modes["what"] == "angle":
                if s["angles"]:
                    n = len(s["angles"])
                    if n == 1:
                        st.caption("1 angle selected — it will be measured.")
                    else:
                        st.caption("Select only 1 angle for this tool.")
                else:
                    st.caption("Use Select: Angle above the map, then click an angle arc.")
            elif modes["what"] == "area":
                if len(s["regions"]) == 1 and s["n"] == 1:
                    st.caption("1 region selected — its area will be measured.")
                else:
                    st.caption("Select ONE region to measure its area.")
            elif modes["what"] == "sides":
                if len(s["regions"]) == 1 and s["n"] == 1:
                    st.caption("1 region selected — its edge count will be measured.")
                else:
                    st.caption("Select ONE region to measure its edge count.")
            elif modes["what"] == "regions":
                st.caption("Select FRAME to count all regions in the diagram.")
            elif modes["what"] == "orientation":
                st.caption("Click exactly three vertices in sequence: first v₁, then v₂, then v₃.")

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
                choice = st.radio(
                    "Order how?",
                    [o[0] for o in opts],
                    index=None if IS_PRACTICE and PRACTICE_STEP == "tools" else 0,
                    key="rad_sort",
                )
                modes["by"] = label2val.get(choice)
            else:
                st.caption("Select 2+ angles, 2+ vertices, or 2+ regions.")

        elif tool == "merge" and st.session_state.unions:
            for remove_union_index, union in enumerate(st.session_state.unions):
                union_name = union.get("name", "U")
                if st.button(
                    f"Clear Region {union_name}",
                    key=f"remove_union_{remove_union_index}",
                    use_container_width=True,
                ):
                    remove_merged_region(remove_union_index)

        # Merge has no RUN sub-options; the controls above manage existing unions.

        ready, msg = validate(tool, modes)
        if tool == "intersect" and modes.get("target") is None:
            ready = False
        if not ready and msg:
            st.caption(msg)
        if st.button("▶ RUN", type="primary", disabled=not ready,
                     use_container_width=True, key="run_active_tool"):
            push_undo()
            run_tool(tool, modes)

    # --- SELECTION ---
    if (
        IS_PRACTICE
        and PRACTICE_STEP == "tools"
        and st.session_state.get("practice_measure_orientation_done", False)
        and not st.session_state.get("practice_sort_angles_done", False)
        and not st.session_state.get("practice_pending_feedback")
    ):
        st.session_state.selection_filter = "Angle"
    st.session_state.setdefault("selection_filter", "Region")
    if PRACTICE_ENTITIES_FEEDBACK:
        select_mode = "none"
        st.success("Great — you identified all four kinds of objects.")
        st.caption("The diagram shows the region, angle, vertex, and edge you selected.")
        if st.button("Continue", type="primary", use_container_width=True,
                     key="continue_entities_feedback"):
            st.session_state.practice_entities_feedback_acknowledged = True
            st.rerun()
    elif PRACTICE_FRAME_REVIEW:
        select_mode = "none"
        st.markdown(
            "The **frame** is the diagram's outer boundary.  \n"
            "The **outside of the frame** is the area beyond that boundary."
        )
        if st.button("Continue", type="primary", use_container_width=True,
                     key="continue_frame_review"):
            st.session_state.practice_frame_review_done = True
            st.rerun()
    elif PRACTICE_DIRECTION_DEMO:
        select_mode = "none"
        st.session_state.setdefault("practice_direction_target", "Clockwise")
        st.session_state.setdefault("practice_direction_answered", False)
        st.session_state.setdefault("practice_direction_correct", None)
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
            key="practice_direction_answer",
            disabled=st.session_state.practice_direction_answered,
        )
        if not st.session_state.practice_direction_answered:
            if st.button("Check answer", type="primary", use_container_width=True,
                         disabled=direction_answer is None):
                st.session_state.practice_direction_correct = (
                    direction_answer == st.session_state.practice_direction_target
                )
                st.session_state.practice_direction_answered = True
                st.rerun()
        elif st.session_state.practice_direction_correct:
            st.success("Correct — the arrows move clockwise.")
        else:
            st.error(
                "Not quite — the arrows move clockwise: "
                "top → right → bottom → left."
            )
    else:
        st.markdown(
            '<div style="font-size:1.25rem; font-weight:600; margin:0.5rem 0 0.35rem 0;">Selection</div>',
            unsafe_allow_html=True,
        )
        select_mode = st.radio(
            "Select from diagram:",
            ["Region", "Angle", "Vertex", "Edge"],
            horizontal=True,
            key="selection_filter",
            label_visibility="collapsed",
        )
        if IS_PRACTICE and PRACTICE_STEP == "select":
            selected_types = practice_selected_entity_types()
            st.markdown(
                '<div style="border:1px solid #d1d5db; border-radius:0.4rem; '
                'padding:0.55rem 0.7rem; margin:0.35rem 0;">'
                f'{practice_selection_checklist_html(selected_types)}'
                '</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                "Select exactly one object of each type. After selecting one Region, "
                "switch Selection to Angle, then Vertex, then Edge. The checklist will "
                "show your progress. Refer to Definitions on the right if needed."
            )
    if not IS_PRACTICE and st.button("Select FRAME", use_container_width=True):
        push_undo()
        add_to_selection("frame")
        record_selection_event("select", "frame")
        st.rerun()

    if st.session_state.selection and not PRACTICE_CONCEPT_REVIEW:
        st.markdown(_SELECTION_ROW_CSS, unsafe_allow_html=True)
        if IS_PRACTICE and PRACTICE_STEP == "tools":
            st.caption("Click **✕** next to a selected item to remove only that item.")
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

    if IS_PRACTICE and PRACTICE_STEP == "select" and PRACTICE_DIRECTION_DEMO:
        direction_answered = st.session_state.get("practice_direction_answered", False)
        if st.button("Continue", type="primary",
                     disabled=not (PRACTICE_DIRECTION_DEMO and direction_answered),
                     use_container_width=True):
            selection_entry = tutorial_step_entry("selection_practice")
            selection_entry["direction_answer_correct"] = bool(
                st.session_state.get("practice_direction_correct", False)
            )
            mark_tutorial_step_completed("selection_practice")
            clear_selection()
            st.session_state.annotations = []
            st.session_state.lines = []
            st.session_state.angles = []
            st.session_state.named_edges = []
            st.session_state.point_names = {}
            st.session_state.program = []
            st.session_state.log = []
            st.session_state.tool_calls = []
            st.session_state.undo_stack = []
            st.session_state.counters = {"v": 1, "L": 1, "U": 1, "r": 1, "a": 1, "e": 1}
            st.session_state.practice_step = "tools"
            st.session_state.active_tool = "find"
            st.session_state.selection_filter = "Region"
            st.session_state.rad_vtx_corner = None
            st.session_state.definitions_open = False
            st.session_state.practice_rightmost_vertex_done = False
            st.session_state.practice_neighbors_done = False
            st.session_state.practice_ordered_neighbors_done = False
            st.session_state.practice_draw_line_done = False
            st.session_state.practice_draw_line_ref = None
            st.session_state.practice_intersect_done = False
            st.session_state.practice_measure_area_done = False
            st.session_state.practice_measure_orientation_done = False
            st.session_state.practice_sort_angles_done = False
            st.session_state.practice_merge_done = False
            st.session_state.practice_pending_feedback = None
            st.session_state.practice_guided_complete = False
            st.session_state.practice_direction_answered = False
            st.session_state.practice_direction_correct = None
            start_tutorial_step("rightmost")
            save_survey_results()
            st.rerun()

# ----------------------------------------------------------------------------
# MIDDLE PANEL — DIAGRAM + direct object selection
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

    if IS_PRACTICE and PRACTICE_STEP == "select" and not PRACTICE_CONCEPT_REVIEW:
        st.markdown(
            '<div style="background:#eff6ff; color:#1e3a8a; '
            'border:1px solid #bfdbfe; border-radius:0.5rem; '
            'padding:0.55rem 0.7rem; margin:-0.2rem 0 0.7rem; font-size:0.9rem;">'
            '<strong>The diagram is interactive.</strong> Select objects by clicking '
            'directly on the diagram above.'
            '</div>',
            unsafe_allow_html=True,
        )

    if tool:
        instruction_text = INSTRUCTIONS[tool]
        if IS_PRACTICE and tool in ("find", "vertex"):
            instruction_text = "\n".join(
                line
                for line in instruction_text.splitlines()
                if "Find a frame vertex" not in line
                and "Select the FRAME" not in line
            )
        st.info(instruction_text)

    if (
        not PRACTICE_CONCEPT_REVIEW
        and coords is not None
        and coords != st.session_state.last_click
    ):
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
                existing_entry = next(
                    ((name, saved) for name, saved in st.session_state.angles if saved == obj),
                    None,
                )
                if existing_entry is None:
                    aname = next_name("a")
                    angle_entry = (aname, obj)
                    st.session_state.angles.append(angle_entry)
                    ann = {"kind": "angle", "vertex": obj.vertex, "face": obj.face, "label": aname}
                    st.session_state.annotations.append(ann)
                if obj not in st.session_state.selection:
                    add_to_selection(obj)
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
    if show_practice_action_hint:
        st.markdown(
            '<div style="background:#eff6ff; color:#1e3a8a; '
            'border:1px solid #bfdbfe; border-radius:0.5rem; '
            'padding:0.55rem 0.7rem; margin:0.55rem 0 0.7rem; font-size:0.9rem;">'
            'After you click <strong>RUN</strong>, the result will appear here.'
            '</div>',
            unsafe_allow_html=True,
        )
    if not st.session_state.log:
        st.caption("(results will appear here)")
    else:
        for entry in reversed(st.session_state.log[-25:]):
            st.markdown(entry)
