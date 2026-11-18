"""
geo_agent.py — Qwen3.5-9B answering GeoLogic survey questions with OPTIONAL tools.

The model sees the same 460x460 diagram a human participant saw. Each turn it may
either answer directly or call one of the seven survey verbs. A tool call is
executed against the real map, and the model receives back the participant-facing
output text PLUS the re-rendered diagram — exactly the two channels a human got.

Three experimental arms, selected with tool_mode:

    "auto"      tools offered, model chooses          (tool_choice="auto")
    "required"  tools offered, first call is forced   (tool_choice="required" on turn 0)
    "none"      no tool schemas in context at all     (image-only baseline)

SETUP (one time, on a compute node):

    uv pip install vllm --torch-backend=auto --extra-index-url https://wheels.vllm.ai/nightly
    pip install -U openai

    vllm serve Qwen/Qwen3.5-9B \
        --port 8000 --tensor-parallel-size 1 --max-model-len 131072 \
        --reasoning-parser qwen3 \
        --enable-auto-tool-choice --tool-call-parser qwen3_coder

    export OPENAI_BASE_URL="http://localhost:8000/v1"
    export OPENAI_API_KEY="EMPTY"

USAGE:

    import geo_env, geo_agent
    env = geo_env.Env(num_regions=8, seed=35)
    result = geo_agent.run_episode(
        env, "Which regions border region B along an edge?", tool_mode="auto")
    print(result["answer"])
    for turn in result["trace"]:
        print(turn["tool"], turn["args"], "->", turn["output"])
"""

import base64
import json
from io import BytesIO

from openai import OpenAI

import geo_env
import copy

import os, sys, subprocess, tempfile

MODEL = "Qwen/Qwen3.5-9B"

# Thinking-mode sampling params, per the model card's best practices.
SAMPLING = dict(
    temperature=1.0,
    top_p=0.95,
    presence_penalty=1.5,
    max_tokens=10024,
)
EXTRA_BODY = {"top_k": 20}


# ============================================================
# SYSTEM PROMPTS — one per arm
# ============================================================
_PREAMBLE = """You are answering questions about a geologic map diagram.

The diagram shows lettered regions (A, B, C, ...) inside a square frame.
"""

_TOOL_FEEDBACK = """After each tool call you will receive the tool's output and an updated diagram
showing the result highlighted.
"""

_ANSWER_RULES = """When you are ready, give your final answer on its own line in the form:
ANSWER: <your answer>

Answer format rules:
- A set of regions: comma-separated labels, e.g. "A, C, F". If none, write "None".
- An ordered sequence: keep the order, e.g. "B, D, A".
- A number: just the number.
- Yes/no: "Yes" or "No"."""

SYSTEM_PROMPT_AUTO = _PREAMBLE + """
You have optional tools that operate on the diagram. You do not have to use them
— if you can answer from the image, just answer. Use a tool when it would make
you more confident.

""" + _TOOL_FEEDBACK + "\n" + _ANSWER_RULES

SYSTEM_PROMPT_FORCED = _PREAMBLE + """
You have tools that operate on the diagram. Start by calling a tool to establish
what you see in the image, then answer once the tool output settles the question.

""" + _TOOL_FEEDBACK + "\n" + _ANSWER_RULES

SYSTEM_PROMPT_NOTOOLS = _PREAMBLE + """
Answer from the diagram alone. Read it carefully before you commit.

""" + _ANSWER_RULES

# Backwards compatibility with anything that imported the old name.
SYSTEM_PROMPT = SYSTEM_PROMPT_AUTO

_SYSTEM_PROMPTS = {
    "auto": SYSTEM_PROMPT_AUTO,
    "required": SYSTEM_PROMPT_FORCED,
    "none": SYSTEM_PROMPT_NOTOOLS,
}
TOOL_MODES = tuple(_SYSTEM_PROMPTS)


# ============================================================
# TOOL SCHEMAS — the seven survey verbs
# ============================================================
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "find",
            "description": (
                "Find a described vertex or edge.\n\n"
                "Returns a vertex (or, with which=\"all\", every vertex).\n\n"
                "ONE REGION            -> a corner of it, chosen by `which`:\n"
                "    \"all\", \"leftmost\", \"rightmost\", \"topmost\", \"bottommost\",\n"
                "    \"bottom_left\", \"bottom_right\", \"top_left\", \"top_right\",\n"
                "    \"sharpest\", \"widest\"\n"
                "THE FRAME (\"frame\")   -> a frame corner, chosen by `which`:\n"
                "    \"all\", \"top_left\", \"top_right\", \"bottom_left\", \"bottom_right\"\n"
                "TWO OR MORE REGIONS   -> their unique shared boundary point; other regions may also meet there\n"
                "                         (omit on_frame to search all locations; multiple matches are ambiguous).\n\n"
                "With object=\"edge\": return the unique edge of the first region that "
                "meets the supplied regions. Use the string \"Outside\" for the outside "
                "of the frame. A returned edge can contain several collinear topology "
                "segments but behaves as one question-level edge.\n\n"
                "Examples:\n"
                "    find(A, object=\"vertex\", which=\"rightmost\")\n"
                "    find(\"frame\", object=\"vertex\", which=\"top_left\")\n"
                "    find(E, C, object=\"vertex\", on_frame=True)\n"
                "    find(A, B, object=\"edge\")\n"
                "    find(A, \"Outside\", object=\"edge\")"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "objs": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Region letters, e.g. ['A'] or ['A','D','E']. "
                                       "Use ['frame'] for the diagram frame, or "
                                       "'Outside' for the outside of the frame.",
                    },
                    "object": {
                        "type": "string", "enum": ["vertex", "edge"],
                        "description": "Default \"vertex\".",
                    },
                    "which": {
                        "type": "string",
                        "enum": ["all", "leftmost", "rightmost", "topmost", "bottommost",
                                 "bottom_left", "bottom_right", "top_left", "top_right",
                                 "sharpest", "widest"],
                        "description": "Default \"all\".",
                    },
                    "on_frame": {
                        "type": "boolean",
                        "description": "For two or more regions: whether the meeting "
                                       "point lies on the frame. Optional: omit to search both frame and interior points.",
                    },
                },
                "required": ["objs"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "neighbors",
            "description": (
                "Returns the regions related to the selection.\n\n"
                "A POINT                  -> every region that meets at that point.\n"
                "AN EDGE                  -> the labeled regions inside the frame on either\n"
                "                            side of the edge.\n"
                "A REGION, kind=\"edge\"    -> regions sharing a full edge (a border).\n"
                "A REGION, kind=\"vertex\"  -> regions touching only at a corner.\n"
                "A REGION, kind=\"ordered\" -> the bordering regions in walking order;\n"
                "    give start=<a corner> and go_counterclockwise=<True/False>.\n"
                "    (CCW -> regions on the right; CW -> regions on the left. Returns []\n"
                "    if a corner where 3+ regions meet makes the order ambiguous.)\n\n"
                "Examples:\n"
                "    neighbors(p)\n"
                "    neighbors(some_edge)\n"
                "    neighbors(A, \"edge\")\n"
                "    neighbors(A, \"vertex\")\n"
                "    neighbors(A, \"ordered\", start=p, go_counterclockwise=True)"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "obj": {
                        "type": "string",
                        "description": "A region letter (e.g. 'A'), a labeled vertex "
                                       "name (e.g. 'v1'), or a labeled edge name "
                                       "(e.g. 'e1').",
                    },
                    "edge": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Alternative to obj: two region letters naming "
                                       "a shared edge, e.g. ['A','B'].",
                    },
                    "kind": {
                        "type": "string", "enum": ["edge", "vertex", "ordered"],
                        "description": "Default \"edge\". Applies when obj is a region.",
                    },
                    "start": {
                        "type": "string",
                        "description": "A labeled vertex name, e.g. 'v1'. Required for "
                                       "kind=\"ordered\".",
                    },
                    "go_counterclockwise": {
                        "type": "boolean",
                        "description": "Default true.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draw",
            "description": (
                "Draws a line you can then intersect with regions.\n\n"
                "  * an EDGE                 -> draw(edge)            (uses the edge's ends)\n"
                "  * TWO vertices            -> draw(p, q)\n"
                "  * ONE vertex + direction  -> draw(p, \"up\"/\"down\"/\"left\"/\"right\")  (a ray)\n\n"
                "kind: \"segment\" (default) or \"full\" (the infinite line through the points).\n"
                "      (kind is ignored when drawing a ray.)"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "vertices": {
                        "type": "array", "items": {"type": "string"},
                        "description": "One or two labeled vertex names, e.g. ['v1','v2'].",
                    },
                    "edge": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Two region letters naming a shared edge to draw from.",
                    },
                    "kind": {
                        "type": "string", "enum": ["segment", "full"],
                        "description": "Default \"segment\".",
                    },
                    "direction": {
                        "type": "string", "enum": ["up", "down", "left", "right"],
                        "description": "Give one vertex plus a direction to draw a ray.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "intersect",
            "description": (
                "Ask a line what it hits.\n\n"
                "target = \"faces\"       -> regions the line passes through, in travel order\n"
                "                          (a full/infinite line returns them unordered).\n"
                "target = another line  -> True/False: do the two lines cross?\n\n"
                "Examples:\n"
                "    intersect(line, \"faces\")\n"
                "    intersect(draw(p, q), draw(u, v))"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "line": {"type": "string", "description": "Line name, e.g. 'L1'."},
                    "target": {
                        "type": "string",
                        "description": "\"faces\", or the name of a second drawn line "
                                       "(e.g. 'L2'). Default \"faces\".",
                    },
                },
                "required": ["line"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "merge",
            "description": (
                "Join two regions that share a border into one combined region. The result "
                "behaves like any region: measure its area or sides, ask for its neighbors."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "region_a": {"type": "string"},
                    "region_b": {"type": "string"},
                },
                "required": ["region_a", "region_b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "measure",
            "description": (
                "Measure a single thing and get back a single number.\n\n"
                "what:\n"
                "    \"distance\" a drawn line -> its length\n"
                "               (or two points -> the straight-line distance between them)\n"
                "               (or two regions -> the distance between their closest points)\n"
                "    \"angle\"   a corner (its point + the region it belongs to)\n"
                "              -> the interior angle there, in degrees\n"
                "    \"area\"    a region -> its area\n"
                "    \"edge_count\" a region -> how many boundary edges it has\n"
                "    \"frame_edge_count\" a region -> how many of its edges lie on the frame\n"
                "    \"regions\" the frame -> how many bounded regions are in the diagram\n"
                "    \"orientation\" three ordered vertices -> clockwise or counterclockwise\n\n"
                "Examples:\n"
                "    measure(L1, what=\"distance\")\n"
                "    measure(p, q, what=\"distance\")    # distance between two points\n"
                "    measure(A, B, what=\"distance\")    # distance between two regions\n"
                "    measure(p, A, what=\"angle\")       # angle at corner p inside region A\n"
                "    measure(A, what=\"area\")\n"
                "    measure(A, what=\"edge_count\")\n"
                "    measure(\"frame\", what=\"regions\")\n"
                "    measure(v1, v2, v3, what=\"orientation\")"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "what": {
                        "type": "string",
                        "enum": ["distance", "angle", "area", "edge_count",
                                 "frame_edge_count", "regions", "orientation"],
                    },
                    "regions": {"type": "array", "items": {"type": "string"}},
                    "vertices": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Labeled vertex names, e.g. ['v1','v2','v3'].",
                    },
                    "line": {
                        "type": "string",
                        "description": "A drawn line name, e.g. 'L1', for "
                                       "what=\"distance\".",
                    },
                },
                "required": ["what"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sort",
            "description": (
                "Put several objects in and get them back in order, smallest -> largest.\n"
                "Sort only ranks things that have a numeric size.\n\n"
                "by:\n"
                "    \"angle\"       saved angle objects by interior angle\n"
                "                  (or corners of a region with `reference` set to that region)\n"
                "    \"area\"        regions, by area\n"
                "    \"left_right\"  points, left to right\n"
                "    \"bottom_top\"  points, bottom to top\n"
                "    \"distance\"    points, by distance from `reference` (a point)\n\n"
                "Examples:\n"
                "    sort([a1, a2, a3, a4], by=\"angle\")\n"
                "    sort([A, B, C], by=\"area\")\n"
                "    sort([u, v, w], by=\"left_right\")\n"
                "    sort([u, v, w], by=\"distance\", reference=p)"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "by": {
                        "type": "string",
                        "enum": ["angle", "area", "left_right", "bottom_top", "distance"],
                    },
                    "regions": {"type": "array", "items": {"type": "string"}},
                    "vertices": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Labeled vertex names, e.g. ['v1','v2'].",
                    },
                    "angles": {
                        "type": "array",
                        "items": {
                            "type": "array", "items": {"type": "string"},
                            "description": "[region_letter, vertex_name] pair naming a corner.",
                        },
                    },
                    "reference": {
                        "type": "string",
                        "description": "A labeled vertex name for by=\"distance\", or a "
                                       "region letter for by=\"angle\" over that region's corners.",
                    },
                },
                "required": ["by"],
            },
        },
    },
]


# ============================================================
# DISPATCH — model arguments -> selection + env.run()
# ============================================================
def _vertex_by_name(env, name):
    """Resolve a label like 'v1' back to the Vertex object."""
    for v in env.res_map.vertices:
        if env.point_names.get(id(v)) == name:
            return v
    raise ValueError(f"No vertex named {name!r}. Find and label it first with find_vertex.")


def _line_by_name(env, name):
    for entry in env.lines:
        if entry[0] == name:
            return entry
    raise ValueError(f"No line named {name!r}. Draw it first with draw_line.")


def dispatch(env, name, args):
    """Execute one model-issued tool call. Returns participant-facing text."""
    env.clear_selection()

    if name == "find":
        objs = args.get("objs", [])
        if args.get("object") == "edge":
            if len(objs) < 2:
                raise ValueError("Finding an edge requires two or more regions.")
            env.select_edge(env.edge_among(*objs))
            return env.run("find edge", {})
        if objs == ["frame"]:
            env.select_frame()
            return env.run("vertex", {"which": args.get("which", "all")})
        for r in objs:
            env.select_region(r)
        if len(objs) >= 2:
            return env.run("vertex", {"on_frame": args.get("on_frame")})
        return env.run("vertex", {"which": args.get("which", "all")})

    if name == "neighbors":
        if args.get("edge"):
            a, b = args["edge"]
            env.select_edge(env.edge_between(a, b))
            return env.run("neighbors", {})
        obj = args.get("obj", "")
        if obj.startswith("v"):
            env.select_vertex(_vertex_by_name(env, obj))
            return env.run("neighbors", {})
        if obj.startswith("e"):
            env.select_edge(_edge_by_name(env, obj))
            return env.run("neighbors", {})
        env.select_region(obj)
        if args.get("kind") == "ordered" or args.get("start"):
            env.select_vertex(_vertex_by_name(env, args["start"]))
            return env.run("neighbors",
                           {"kind": "ordered",
                            "ccw": args.get("go_counterclockwise", True)})
        return env.run("neighbors", {"kind": args.get("kind", "edge")})

    if name == "draw":
        kind = args.get("kind", "segment")
        style = "full line" if kind == "full" else "segment"
        if args.get("direction"):
            env.select_vertex(_vertex_by_name(env, args["vertices"][0]))
            return env.run("draw line",
                           {"style": "ray", "ray_direction": args["direction"]})
        if args.get("edge"):
            a, b = args["edge"]
            env.select_edge(env.edge_between(a, b))
            return env.run("draw line", {"style": style})
        for vname in args.get("vertices", []):
            env.select_vertex(_vertex_by_name(env, vname))
        return env.run("draw line", {"style": style})

    if name == "intersect":
        line = _line_by_name(env, args["line"])
        target = args.get("target", "faces")
        if target and target != "faces":
            return env.run("intersect",
                           {"line": line, "target": _line_by_name(env, target)})
        return env.run("intersect", {"line": line, "target": "faces"})

    if name == "merge":
        env.select_region(args["region_a"])
        env.select_region(args["region_b"])
        return env.run("merge", {})

    if name == "measure":
        what = args["what"]
        if what == "regions":
            env.select_frame()
        elif what == "angle":
            face = env.region(args["regions"][0])
            env.select_angle(_vertex_by_name(env, args["vertices"][0]), face)
        elif what == "distance" and args.get("line"):
            return env.run("measure",
                           {"what": "distance", "line": _line_by_name(env, args["line"])})
        else:
            for r in args.get("regions", []):
                env.select_region(r)
            for vname in args.get("vertices", []):
                env.select_vertex(_vertex_by_name(env, vname))
        return env.run("measure", {"what": what})

    if name == "sort":
        by = args["by"]
        ref = args.get("reference")
        if by == "angle":
            if args.get("angles"):
                for region_letter, vname in args["angles"]:
                    env.select_angle(_vertex_by_name(env, vname), env.region(region_letter))
            elif ref:
                face = env.region(ref)
                for vname in args.get("vertices", []):
                    env.select_angle(_vertex_by_name(env, vname), face)
            return env.run("sort", {"by": by})
        if by == "area":
            for r in args["regions"]:
                env.select_region(r)
            return env.run("sort", {"by": by})
        if by == "distance" and ref:
            env.select_vertex(_vertex_by_name(env, ref))   # reference goes first
        for vname in args["vertices"]:
            env.select_vertex(_vertex_by_name(env, vname))
        return env.run("sort", {"by": by})

    raise ValueError(f"Unknown tool {name!r}")


def _edge_by_name(env, name):
    for label, sel in env.named_edges:
        if label == name:
            return sel
    raise ValueError(f"No edge named {name!r}. Find it first with find(object='edge').")


# ============================================================
# AGENT LOOP
# ============================================================
def _image_content(img):
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}


def _strip_old_images(messages):
    """Return a copy of messages where only the LAST image block survives.
    Text, tool calls, and tool outputs are all preserved."""
    msgs = copy.deepcopy(messages)

    # Find the index of the last message that carries an image.
    last_img_idx = None
    for i, m in enumerate(msgs):
        if isinstance(m.get("content"), list) and any(
                b.get("type") == "image_url" for b in m["content"]):
            last_img_idx = i

    for i, m in enumerate(msgs):
        if i == last_img_idx or not isinstance(m.get("content"), list):
            continue
        kept = [b for b in m["content"] if b.get("type") != "image_url"]
        dropped = len(m["content"]) - len(kept)
        if dropped:
            kept.append({"type": "text",
                         "text": "[earlier diagram omitted — see the current one below]"})
        m["content"] = kept

    return msgs


def _request_kwargs(tool_mode, turn, force_first_n=1):
    """Per-turn tools/tool_choice for each arm.

    'required' is forced on the first `force_first_n` turns only. If it stayed on
    for every turn the model could never emit a tool-free final answer and every
    episode would run to max_turns.
    """
    if tool_mode == "none":
        return {}                                   # no schemas in context at all
    if tool_mode == "auto":
        return {"tools": TOOLS, "tool_choice": "auto"}
    if tool_mode == "required":
        return {"tools": TOOLS,
                "tool_choice": "required" if turn < force_first_n else "auto"}
    raise ValueError(f"tool_mode must be one of {TOOL_MODES}, got {tool_mode!r}")


DEBUG_DIR = os.environ.get("GEO_DEBUG_DIR", tempfile.mkdtemp(prefix="geo_"))
_step = [0]


def _show(img, tag=""):
    """Save + display a render. Works in notebooks, iTerm2/kitty, or falls back to a path."""
    _step[0] += 1
    path = os.path.join(DEBUG_DIR, f"{_step[0]:03d}_{tag or 'step'}.png")
    img.save(path)

    # 1) Jupyter / IPython
    try:
        from IPython.display import display
        get_ipython()               # raises NameError outside IPython
        display(img)
        print(f"[img] {path}")
        return path
    except Exception:
        pass

    # 2) Inline in a graphics-capable terminal (iTerm2, kitty, WezTerm)
    try:
        if os.environ.get("TERM_PROGRAM") == "iTerm.app":
            import base64
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            sys.stdout.write(f"\033]1337;File=inline=1;width=40:{b64}\a\n")
            sys.stdout.flush()
        elif os.environ.get("TERM", "").startswith("xterm-kitty"):
            subprocess.run(["kitty", "+kitten", "icat", path], check=False)
    except Exception:
        pass

    print(f"[img] {path}")
    return path


def _rule(text):
    print(f"\n{'=' * 60}\n{text}\n{'=' * 60}", flush=True)


def _request_record(response, turn, phase, response_log_path=None):
    """Persist the complete SDK response, including unknown/extra fields."""
    def plain(value):
        if hasattr(value, "model_dump"):
            return plain(value.model_dump())
        if isinstance(value, dict):
            return {k: plain(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [plain(v) for v in value]
        if hasattr(value, "__dict__"):
            return plain(vars(value))
        return value
    import re
    raw = plain(response)
    message = raw["choices"][0]["message"]
    fields = {k: message[k] for k in ("reasoning", "reasoning_content", "reasoning_details")
              if message.get(k) is not None}
    # Some servers put reasoning inside content blocks or <think> tags.
    content = message.get("content")
    if isinstance(content, str) and "<think>" in content:
        fields["content_think_blocks"] = re.findall(r"<think>(.*?)</think>", content, flags=re.S)
    elif isinstance(content, list):
        blocks = [v for v in content if isinstance(v, dict) and
                  any(t in str(v.get("type", "")).lower() for t in ("reasoning", "thinking"))]
        if blocks:
            fields["content_reasoning_blocks"] = blocks
    def has_text(value):
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, list):
            return any(has_text(v) for v in value)
        if isinstance(value, dict):
            return any(has_text(v) for k, v in value.items()
                       if k in ("text", "content", "reasoning", "thinking", "summary"))
        return False
    saved = any(has_text(v) for v in fields.values())
    usage = raw.get("usage") or {}
    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    record = {"turn": turn, "phase": phase,
              "finish_reason": raw["choices"][0].get("finish_reason"),
              "usage": usage, "reasoning_fields": fields,
              "reasoning_capture_status": "captured" if saved else
                  "missing_despite_reasoning_tokens" if reasoning_tokens else "not_returned",
              "raw_response": raw}
    if response_log_path is not None:
        from pathlib import Path
        import os
        path = Path(response_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as log:
            log.write(json.dumps(record, ensure_ascii=False) + "\n")
            log.flush()
            os.fsync(log.fileno())
    return record


def _episode_metadata(requests, msg):
    reason = requests[-1]["finish_reason"] if requests else None
    text = (msg.content or "").strip()
    incomplete = ("token_limit" if reason == "length" else
                  "content_filter" if reason == "content_filter" else
                  "unexpected_tool_call" if msg.tool_calls else
                  "empty_response" if not text else None)
    return {"requests": requests, "finish_reason": reason,
            "status": "incomplete" if incomplete else "completed",
            "incomplete_reason": incomplete,
            "usage_totals": {key: sum((req.get("usage") or {}).get(key, 0) or 0
                                      for req in requests)
                             for key in ("prompt_tokens", "completion_tokens", "total_tokens")}}


def run_episode(env, question, max_turns=8, client=None,
                thinking=True, verbose=1, show_images=None,
                tool_mode="auto", force_first_n=1, response_log_path=None):
    """Let the model answer `question` about `env`.

    tool_mode: "auto"     tools offered, model chooses
               "required" first `force_first_n` turns must contain a tool call
               "none"     no tools in context; image-only baseline

    verbose: 0 = silent
             1 = tool calls and their outputs (the old verbose=True behavior)
             2 = adds the model's visible content each turn
             3 = adds reasoning_content and the raw message repr
    show_images: display renders inline. Defaults to (verbose >= 1).
    """
    if tool_mode not in _SYSTEM_PROMPTS:
        raise ValueError(f"tool_mode must be one of {TOOL_MODES}, got {tool_mode!r}")

    client = client or OpenAI()
    verbose = int(verbose)
    if show_images is None:
        show_images = verbose >= 1

    if verbose:
        _rule(f"[{tool_mode}] Q: {question}")
    if show_images:
        _show(env.render(), f"initial_{tool_mode}")

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPTS[tool_mode]},
        {"role": "user", "content": [
            _image_content(env.render()),
            {"type": "text", "text": question},
        ]},
    ]

    trace = []
    request_records = []
    extra_body = dict(EXTRA_BODY)
    if not thinking:
        extra_body["chat_template_kwargs"] = {"enable_thinking": False}

    for turn in range(max_turns):
        response = client.chat.completions.create(
            model=MODEL,
            messages=_strip_old_images(messages),
            extra_body=extra_body,
            **_request_kwargs(tool_mode, turn, force_first_n),
            **SAMPLING,
        )
        request_records.append(_request_record(response, turn + 1, "normal", response_log_path))
        msg = response.choices[0].message

        if verbose >= 3:
            print(f"\nRAW RESPONSE: {msg!r}", flush=True)
            reasoning = getattr(msg, "reasoning_content", None)
            if reasoning:
                print(f"\n--- turn {turn+1} thinking ---\n{reasoning}", flush=True)
        if verbose >= 2 and msg.content:
            print(f"\n--- turn {turn+1} content ---\n{msg.content}", flush=True)

        # Append only the final content, not reasoning_content — the model card's
        # best practice is to keep thinking out of multi-turn history.
        assistant_entry = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls and tool_mode != "none":
            assistant_entry["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name,
                              "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]
        messages.append(assistant_entry)

        # In the "none" arm a stray tool call is ignored and treated as text.
        if not msg.tool_calls or tool_mode == "none":
            answer = _extract_answer(msg.content or "")
            final = env.render()
            if verbose:
                print(f"\nANSWER: {answer!r}  ({turn + 1} turns, "
                      f"{len(trace)} tool calls, mode={tool_mode})", flush=True)
            if show_images:
                _show(final, f"final_{tool_mode}")
            return {"answer": answer, "raw": msg.content, "trace": trace,
                    "messages": messages, "turns": turn + 1,
                    "tool_mode": tool_mode, "final_image": final,
                    **_episode_metadata(request_records, msg)}

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (TypeError, ValueError):
                args = {}
            try:
                output = dispatch(env, tc.function.name, args)
            except Exception as ex:
                output = (f"That tool call could not be completed ({ex}). "
                          "Check your arguments and try again.")
            trace.append({"tool": tc.function.name, "args": args, "output": output})
            if response_log_path is not None:
                from pathlib import Path
                with Path(str(response_log_path) + ".tools.jsonl").open("a") as log:
                    log.write(json.dumps({"turn": turn + 1, "tool_call_id": tc.id,
                                          "tool": tc.function.name, "args": args,
                                          "output": output}, ensure_ascii=False) + "\n")
                    log.flush()
                    __import__("os").fsync(log.fileno())
            if verbose:
                print(f"[turn {turn+1}] {tc.function.name}({args})\n"
                      f"    -> {output}", flush=True)

            messages.append({"role": "tool", "tool_call_id": tc.id, "content": output})

        # Show the updated diagram after this turn's tool calls.
        updated = env.render()
        if show_images:
            _show(updated, f"{tool_mode}_turn{turn+1}")
        last_turn = (turn == max_turns - 1)
        nudge = ("This is the updated diagram. You have no more tool calls left — "
                 "give your final answer now as 'ANSWER: ...'."
                 if last_turn else
                 "This is the updated diagram. Continue, or give your final answer "
                 "as 'ANSWER: ...'.")
        messages.append({"role": "user", "content": [
            _image_content(updated),
            {"type": "text", "text": nudge},
        ]})

    # One additional answer-only request after the normal interaction budget.
    # Keep the schema for compatibility, but explicitly prohibit tool calls.
    kwargs = dict(model=MODEL, messages=_strip_old_images(messages),
                  extra_body=extra_body, **SAMPLING)
    if tool_mode != "none":
        kwargs.update(tools=TOOLS, tool_choice="none")
    response = client.chat.completions.create(**kwargs)
    request_records.append(_request_record(response, max_turns + 1, "forced_final", response_log_path))
    msg = response.choices[0].message
    messages.append({"role": "assistant", "content": msg.content or ""})
    finish_reason = response.choices[0].finish_reason
    incomplete = bool(msg.tool_calls) or finish_reason == "length" or not (msg.content or "").strip()
    answer = None if incomplete else _extract_answer(msg.content)
    final = env.render()
    if verbose:
        print(f"\nFINAL ANSWER: {answer!r} ({max_turns + 1} requests)", flush=True)
    if show_images:
        _show(final, f"final_{tool_mode}")
    return {"answer": answer, "raw": msg.content, "trace": trace,
            "messages": messages, "turns": max_turns + 1,
            "tool_mode": tool_mode, 
            "final_image": final, "forced_final": True,
            **_episode_metadata(request_records, msg),
            "note": "answer-only request incomplete" if incomplete else
                    "extra answer-only request after max_turns"}


def _extract_answer(text):
    for line in reversed(text.splitlines()):
        if line.strip().upper().startswith("ANSWER:"):
            return line.split(":", 1)[1].strip()
    return text.strip()


# ============================================================
# BATCH over a dataset
# ============================================================
def run_dataset(dataset_items, max_turns=8, client=None, verbose=False,
                tool_mode="auto", env_factory=None):
    """dataset_items: entries from dataset_24_balanced.json ('items').

    env_factory: callable(item) -> a fresh env. Defaults to geo_env.Env. Pass your
    own to run AnnotationEnv, a different addressing scheme, etc. A fresh env per
    item is mandatory: merge and draw mutate state.
    """
    client = client or OpenAI()
    env_factory = env_factory or (
        lambda item: geo_env.Env(num_regions=item["region_count"], seed=item["seed"]))
    results = []
    for item in dataset_items:
        q = item["question"]
        env = env_factory(item)
        out = run_episode(env, q["question_text"], max_turns=max_turns,
                          client=client, verbose=verbose, tool_mode=tool_mode)
        results.append({
            "pair_id": item.get("pair_id"),
            "question_id": q.get("question_id"),
            "tool_mode": tool_mode,
            "question": q["question_text"],
            "gold": q.get("answer"),
            "predicted": out["answer"],
            "n_tool_calls": len(out["trace"]),
            "tools_used": [t["tool"] for t in out["trace"]],
            "turns": out["turns"],
        })
        print(f"[{tool_mode}] {item.get('pair_id')}: {out['answer']!r} "
              f"(gold {q.get('answer')!r}, {len(out['trace'])} tool calls)")
    return results


def run_all_arms(dataset_items, modes=TOOL_MODES, **kw):
    """Run every arm over the same items and return one flat list of rows."""
    rows = []
    for mode in modes:
        rows += run_dataset(dataset_items, tool_mode=mode, **kw)
    return rows