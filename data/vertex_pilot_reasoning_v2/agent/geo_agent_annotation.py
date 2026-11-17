"""
geo_agent_annotation.py — the ANNOTATION arm's tool schema and dispatch.

Pairs with geo_env_annotation.AnnotationEnv. The episode loop, image encoding,
and answer extraction are reused from geo_agent unchanged.

    import geo_env_annotation as gea, geo_agent_annotation as gaa

    env = gea.AnnotationEnv(num_regions=8, seed=35, addressing="descriptor")
    result = gaa.run_episode(env, "Which regions share an edge with region B?")

WHAT MAKES THIS ARM DIFFERENT
-----------------------------
Annotation tools draw; they do not answer. Every tool returns a confirmation
sentence ("Highlighted Region B.") and nothing about the map. The model has to
read its answer off the re-rendered diagram. The system prompt below says so
explicitly, because a model carrying over habits from the compositional arm
will otherwise wait for a tool to tell it something.

THREE ARMS
----------
tool_mode selects the experimental condition:

  "auto"      tools offered, model chooses            (tool_choice="auto")
  "required"  tools offered, first `force_first_n` turns must call a tool
  "none"      no schema sent, and a system prompt that never mentions tools

The "none" prompt is deliberately identical to the compositional arm's "none"
prompt: with no tools, the two arms are the same experiment, and any gap
between them is a bug rather than a finding.

ADDRESSING
----------
build_tools(addressing) emits a schema matching the env's addressing mode:

  "descriptor"  a vertex is named by region + corner property, or by the
                regions that meet there.
  "coordinate"  a vertex is named by normalized x/y in [0,1], snapped to the
                nearest actual vertex. The closer analog to a mouse click.

Keep the env and the schema on the same mode; mismatched args just error.

!! WORDING NOT YET VERIFIED AGAINST THE SURVEY UI !!
Every tool name and description below is written from AnnotationSession's
method signatures, not from what annotation participants actually read on
screen. Replace the marked strings with the UI's own labels and help text
before using this for a fairness comparison. Until then, an auto-vs-none gap
is partly a gap in prompt wording, not purely in the affordance.
"""

import json

from geo_agent import (          # reused unchanged
    _image_content,
    _strip_old_images,
    _extract_answer,
    _show,
    MODEL,
    SAMPLING,
    EXTRA_BODY,
)
from openai import OpenAI


# ============================================================
# SYSTEM PROMPTS — one per arm
# ============================================================
_PREAMBLE = """You are answering questions about a geologic map diagram.

The diagram shows lettered regions (A, B, C, ...) inside a square frame.
"""

_TOOLS_ARE_MUTE = """They do not
answer questions — they only draw. A tool will confirm what it drew, but it
will never tell you anything about the map. Everything you conclude must come
from looking at the updated diagram.
"""

_TOOL_FEEDBACK = """After each tool call you will receive the tool's confirmation and an updated
diagram showing the new annotation.
"""

_ANSWER_RULES = """When you are ready, give your final answer on its own line in the form:
ANSWER: <your answer>

Answer format rules:
- A set of regions: comma-separated labels, e.g. "A, C, F". If none, write "None".
- An ordered sequence: keep the order, e.g. "B, D, A".
- A number: just the number.
- Yes/no: "Yes" or "No"."""

SYSTEM_PROMPT_AUTO = _PREAMBLE + """
You have optional annotation tools that mark up the diagram. """ + _TOOLS_ARE_MUTE + """
Use a tool when marking something would make what you see clearer. If you can
already answer from the image, just answer.

""" + _TOOL_FEEDBACK + "\n" + _ANSWER_RULES

SYSTEM_PROMPT_FORCED = _PREAMBLE + """
You have annotation tools that mark up the diagram. """ + _TOOLS_ARE_MUTE + """
Start by marking up the diagram, then read your answer off the result.

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
# VERTEX ARGUMENT SHAPES
# ============================================================
_DESCRIPTOR_VERTEX_PROPS = {
    "region": {
        "type": "string",
        "description": "Region letter whose corner you mean, e.g. 'A'. "
                       "Use 'frame' for a corner of the diagram frame.",
    },
    "which": {
        "type": "string",
        "enum": ["leftmost", "rightmost", "topmost", "bottommost",
                 "bottom_left", "bottom_right", "top_left", "top_right",
                 "sharpest", "widest"],
        "description": "Which corner of that region.",
    },
    "regions": {
        "type": "array", "items": {"type": "string"},
        "description": "Alternative to region/which: two or more region "
                       "letters, naming the point where they all meet.",
    },
    "on_frame": {
        "type": "boolean",
        "description": "For 'regions': whether the meeting point is on the frame.",
    },
}

_COORDINATE_VERTEX_PROPS = {
    "x": {"type": "number",
          "description": "Horizontal position in the frame, 0.0 at the left "
                         "edge to 1.0 at the right edge."},
    "y": {"type": "number",
          "description": "Vertical position in the frame, 0.0 at the bottom "
                         "edge to 1.0 at the top edge."},
}


def _vertex_props(addressing):
    return dict(_COORDINATE_VERTEX_PROPS if addressing == "coordinate"
                else _DESCRIPTOR_VERTEX_PROPS)


def _vertex_hint(addressing):
    if addressing == "coordinate":
        return ("Give the position of the vertex as x and y between 0 and 1; "
                "the nearest actual vertex is used.")
    return ("Name the vertex either as a corner of one region (region + "
            "which) or as the point where several regions meet (regions).")


# ============================================================
# TOOL SCHEMAS
# ============================================================
def build_tools(addressing="descriptor"):
    """Emit the annotation tool schema for the given addressing mode."""
    vprops = _vertex_props(addressing)
    vhint = _vertex_hint(addressing)

    return [
        {
            "type": "function",
            "function": {
                "name": "highlight_region",
                # !! placeholder wording
                "description": "Shade one region so it stands out from the rest "
                               "of the diagram.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "region": {"type": "string",
                                   "description": "Region letter, e.g. 'A'."},
                    },
                    "required": ["region"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "label_vertex",
                # !! placeholder wording
                "description": ("Mark a vertex with a dot and give it a name "
                                "(v1, v2, ...) so you can refer to it later. "
                                + vhint),
                "parameters": {
                    "type": "object",
                    "properties": dict(vprops),
                    "required": (["x", "y"] if addressing == "coordinate" else []),
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "label_angle",
                # !! placeholder wording
                "description": ("Draw an arc at one corner of one region, "
                                "showing the interior angle there, and name it "
                                "(a1, a2, ...). " + vhint),
                "parameters": {
                    "type": "object",
                    "properties": dict(
                        vprops,
                        region={"type": "string",
                                "description": "The region whose interior "
                                               "angle is marked."},
                    ),
                    "required": (["region", "x", "y"] if addressing == "coordinate"
                                 else ["region"]),
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "label_edge",
                # !! placeholder wording
                "description": "Highlight the border between two regions and "
                               "name it (e1, e2, ...).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "edge": {
                            "type": "array", "items": {"type": "string"},
                            "description": "Two region letters whose shared "
                                           "border you mean, e.g. ['A','B'].",
                        },
                    },
                    "required": ["edge"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "union",
                # !! placeholder wording
                "description": "Shade two bordering regions as one combined "
                               "region, hiding the border between them.",
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
                "name": "draw_line",
                # !! placeholder wording
                "description": ("Draw a construction line on the diagram.\n"
                                "  style='extend_edge'  extend the border "
                                "between two regions out to the frame\n"
                                "  style='axis'         a horizontal or "
                                "vertical line through a vertex\n"
                                "  style='segment'      a segment between two "
                                "vertices\n"
                                "  style='full'         the full line through "
                                "two vertices\n" + vhint),
                "parameters": {
                    "type": "object",
                    "properties": dict(
                        vprops,
                        style={
                            "type": "string",
                            "enum": ["extend_edge", "axis", "segment", "full"],
                            "description": "Default 'segment'.",
                        },
                        edge={
                            "type": "array", "items": {"type": "string"},
                            "description": "For style='extend_edge': two "
                                           "region letters, e.g. ['A','B'].",
                        },
                        direction={
                            "type": "string", "enum": ["H", "V"],
                            "description": "For style='axis'.",
                        },
                        **{
                            "from": {
                                "type": "object",
                                "properties": _vertex_props(addressing),
                                "description": "For style='segment' or 'full': "
                                               "the starting vertex.",
                            },
                            "to": {
                                "type": "object",
                                "properties": _vertex_props(addressing),
                                "description": "For style='segment' or 'full': "
                                               "the ending vertex.",
                            },
                        },
                    ),
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "undo",
                # !! placeholder wording
                "description": "Remove the most recent annotation from the "
                               "diagram.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


TOOLS = build_tools("descriptor")

_TOOL_NAMES = ("highlight_region", "label_vertex", "label_angle",
               "label_edge", "union", "draw_line", "undo")


# ============================================================
# DISPATCH
# ============================================================
def dispatch(env, name, args):
    """Execute one model-issued annotation call. Returns confirmation text.

    Thin, unlike the compositional dispatch: AnnotationEnv.run already takes
    the model's argument shape, because an annotation call carries its whole
    selection and leaves no buffer behind.
    """
    if name not in _TOOL_NAMES:
        raise ValueError(f"Unknown tool {name!r}")
    return env.run(name, args or {})


# ============================================================
# EPISODE LOOP
# ============================================================
def run_episode(env, question, max_turns=8, client=None,
                thinking=True, verbose=1, show_images=None,
                addressing=None, tool_mode="auto", force_first_n=1):
    """Annotation-arm episode. Mirrors geo_agent.run_episode.

    tool_mode: "auto"     tools offered, model chooses
               "required" first `force_first_n` turns must contain a tool call
               "none"     no schema sent; image-only baseline

    addressing defaults to the env's own mode, so the schema and the env always
    agree unless you deliberately override it.

    verbose: 0 = silent
             1 = tool calls and their outputs
             2 = adds the model's visible content each turn
             3 = adds reasoning_content and the raw message repr
    """
    if tool_mode not in _SYSTEM_PROMPTS:
        raise ValueError(f"tool_mode must be one of {TOOL_MODES}, got {tool_mode!r}")

    client = client or OpenAI()
    verbose = int(verbose)
    if show_images is None:
        show_images = verbose >= 1

    addressing = addressing or getattr(env, "addressing", "descriptor")
    tools = None if tool_mode == "none" else build_tools(addressing)

    if verbose:
        print(f"\n{'='*60}\n[{tool_mode}/{addressing}] Q: {question}\n{'='*60}",
              flush=True)
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
    extra_body = dict(EXTRA_BODY)
    if not thinking:
        extra_body["chat_template_kwargs"] = {"enable_thinking": False}

    for turn in range(max_turns):
        kwargs = dict(model=MODEL,
                      messages=_strip_old_images(messages),
                      extra_body=extra_body,
                      **SAMPLING)
        if tools is not None:
            kwargs["tools"] = tools
            # Force a call on the first `force_first_n` turns only; let it
            # answer afterwards, otherwise it can never stop calling tools and
            # emit ANSWER:.
            kwargs["tool_choice"] = ("required"
                                     if (tool_mode == "required"
                                         and turn < force_first_n)
                                     else "auto")

        response = client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        if verbose >= 3:
            print(f"\nRAW RESPONSE: {msg!r}", flush=True)
            reasoning = getattr(msg, "reasoning_content", None)
            if reasoning:
                print(f"\n--- turn {turn+1} thinking ---\n{reasoning}", flush=True)
        if verbose >= 2 and msg.content:
            print(f"\n--- turn {turn+1} content ---\n{msg.content}", flush=True)

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
                    "tool_mode": tool_mode, "addressing": addressing,
                    "final_image": final}

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
            trace.append({"tool": tc.function.name, "args": args,
                          "output": output})
            if verbose:
                print(f"[turn {turn+1}] {tc.function.name}({args})\n"
                      f"    -> {output}", flush=True)
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": output})

        updated = env.render()
        if show_images:
            _show(updated, f"{tool_mode}_turn{turn+1}")
        last_turn = (turn == max_turns - 1)
        nudge = ("This is the updated diagram. You have no more tool calls left "
                 "— give your final answer now as 'ANSWER: ...'."
                 if last_turn else
                 "This is the updated diagram. Continue, or give your final "
                 "answer as 'ANSWER: ...'.")
        messages.append({"role": "user", "content": [
            _image_content(updated),
            {"type": "text", "text": nudge},
        ]})

    # One additional answer-only request after the normal interaction budget.
    # Keep the schema for compatibility, but explicitly prohibit tool calls.
    kwargs = dict(model=MODEL, messages=_strip_old_images(messages),
                  extra_body=extra_body, **SAMPLING)
    if tools is not None:
        kwargs.update(tools=tools, tool_choice="none")
    response = client.chat.completions.create(**kwargs)
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
            "tool_mode": tool_mode, "addressing": addressing,
            "final_image": final, "forced_final": True,
            "finish_reason": finish_reason,
            "note": "answer-only request incomplete" if incomplete else
                    "extra answer-only request after max_turns"}


# ============================================================
# BATCH over a dataset
# ============================================================
def run_dataset(dataset_items, max_turns=8, client=None, verbose=False,
                tool_mode="auto", addressing="descriptor", env_factory=None):
    """dataset_items: entries from dataset_24_balanced.json ('items').

    env_factory: callable(item) -> a fresh AnnotationEnv. A fresh env per item
    is mandatory: union and draw_line mutate the diagram.
    """
    import geo_env_annotation

    client = client or OpenAI()
    env_factory = env_factory or (
        lambda item: geo_env_annotation.AnnotationEnv(
            num_regions=item["region_count"], seed=item["seed"],
            addressing=addressing))

    results = []
    for item in dataset_items:
        q = item["question"]
        env = env_factory(item)
        out = run_episode(env, q["question_text"], max_turns=max_turns,
                          client=client, verbose=verbose, tool_mode=tool_mode,
                          addressing=addressing)
        results.append({
            "pair_id": item.get("pair_id"),
            "question_id": q.get("question_id"),
            "arm": "annotation",
            "tool_mode": tool_mode,
            "addressing": addressing,
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
    """Run every tool_mode over the same items; returns one flat list of rows."""
    rows = []
    for mode in modes:
        rows += run_dataset(dataset_items, tool_mode=mode, **kw)
    return rows