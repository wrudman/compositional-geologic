"""
geo_env_annotation.py — the ANNOTATION arm of the tool comparison.

Parallel to geo_env.Env, but backed by AnnotationSession from
visual_tools_annotation.py instead of the compositional verbs in tools_human.

THE KEY DIFFERENCE
------------------
Compositional tools ANSWER:   neighbors(B, "edge") -> "Regions that share an
                              edge with Region B: **A, C, D**."
Annotation tools only DRAW:   highlight_region(B) -> "Highlighted Region B."

An annotation tool returns no information about the map. Every fact the model
uses has to be read off the re-rendered image. That is the whole point of the
contrast, and it means an annotation episode is a visual-reasoning task with a
markup aid, not a tool-use task.

Public surface matches geo_env.Env closely enough that geo_agent's episode loop
works unchanged:

    env = AnnotationEnv(num_regions=8, seed=35)
    img = env.render()                       # PIL, 460x460
    txt = env.run("highlight_region", {"region": "B"})
    env.undo()
    env.clear_all()

SELECTION
---------
A human clicks a vertex. The model has to name one. Addressing is pluggable via
the `addressing` argument; see resolve_vertex below. Default is "descriptor",
which reuses tools_human's corner selectors to *point at* a vertex without
revealing anything about it.
"""

import math

from PIL import Image

import Graph
import BuildRandomMap
import DrawGraph
import map_helpers
import tools_human as T
import visual_tools_annotation as VA

import tempfile
import os

DISPLAY_SIDE = 460

ANNOTATION_TOOLS = [
    "label_vertex", "label_angle", "label_edge", "highlight_region",
    "union", "draw_line", "undo",
]


STRUCTURE_COMPLEXITIES = ("current", "high")

class AnnotationEnv:
    """One survey item, annotated rather than queried.

    Builds its own res_map. Do not share a map with a geo_env.Env: the two
    classes write different values into face._cache_idx and would clobber each
    other's label caches.
    """

    def __init__(self, num_regions, seed, maxX=1.0, maxY=1.0,
                 addressing="descriptor", structure_complexity="current",
                 keep_generator_images=False):
        if structure_complexity not in STRUCTURE_COMPLEXITIES:
            raise ValueError(
                f"structure_complexity must be one of {STRUCTURE_COMPLEXITIES}.")
        Graph.initialize()
        self.maxX, self.maxY = maxX, maxY
        self.num_regions = num_regions
        self.seed = seed
        self.structure_complexity = structure_complexity

        self.res_map = self._build_map(num_regions, maxX, maxY, seed,
                                       structure_complexity,
                                       keep_generator_images)
        map_helpers.use_map(self.res_map)
        T.setup(self.res_map)

        self.img_size = (int(200 + 800 * maxX), int(200 + 800 * maxY))
        self.session = VA.AnnotationSession(self.res_map, self.img_size)
        self.addressing = addressing

        self.log = []
        self.tool_calls = []
        self.program = []
    
    @staticmethod                                 
    def _build_map(num_regions, maxX, maxY, seed, structure_complexity,
                   keep_generator_images):
        if keep_generator_images:
            return BuildRandomMap.BuildRandomMap(
                num_regions, maxX, maxY, seed,
                structure_complexity=structure_complexity)
        with tempfile.TemporaryDirectory() as scratch:
            cwd = os.getcwd()
            os.chdir(scratch)
            try:
                return BuildRandomMap.BuildRandomMap(
                    num_regions, maxX, maxY, seed,
                    structure_complexity=structure_complexity)
            finally:
                os.chdir(cwd)

    # ---------- lookups ----------
    @property
    def faces(self):
        """Letter -> face. Unions are visual only here: draw_union hides the
        shared edge but does not create a new face object, so the constituent
        regions stay addressable."""
        return {f.letter: f for f in self.res_map.faces if f.bounded}

    def region(self, letter):
        try:
            return self.faces[letter]
        except KeyError:
            raise KeyError(
                f"No region {letter!r}. Available: "
                f"{', '.join(sorted(self.faces))}") from None

    # ---------- vertex addressing ----------
    def resolve_vertex(self, spec):
        """Turn a model-supplied vertex reference into a Vertex object.

        "descriptor" mode: spec is {"region": "A", "which": "leftmost"} or
            {"regions": ["A","B","C"]} for a meeting point. Reuses the same
            selectors a compositional agent gets, purely as a pointing device.

        "coordinate" mode: spec is {"x": 0.42, "y": 0.65} in normalized map
            coordinates; snaps to the nearest vertex. Closer to a mouse click,
            but VLMs localize poorly, so expect misses.
        """
        if self.addressing == "coordinate":
            if "x" not in spec or "y" not in spec:
                raise ValueError('Coordinate addressing needs "x" and "y".')
            target = Graph.Vector(float(spec["x"]), float(spec["y"]))
            best, best_d = None, float("inf")
            for v in self.res_map.vertices:
                d = Graph.vecDist(v.p, target)
                if d < best_d:
                    best, best_d = v, d
            if best is None:
                raise ValueError("No vertices in the map.")
            return best

        # descriptor mode
        if spec.get("regions"):
            objs = [self.region(r) for r in spec["regions"]]
            result = T.vertex(*objs, on_frame=spec.get("on_frame", False))
            if isinstance(result, (list, tuple)):
                if not result:
                    raise ValueError("Those regions do not meet at a vertex.")
                return result[0]
            if result is None:
                raise ValueError("Those regions do not meet at a vertex.")
            return result

        if spec.get("region") == "frame":
            result = T.vertex("frame", which=spec.get("which", "top_left"))
        elif spec.get("region"):
            result = T.vertex(self.region(spec["region"]),
                              which=spec.get("which", "leftmost"))
        else:
            raise ValueError('Vertex needs "region" (+ "which") or "regions".')

        if isinstance(result, (list, tuple)):
            if not result:
                raise ValueError("No such vertex.")
            return result[0]
        if result is None:
            raise ValueError("No such vertex.")
        return result

    def resolve_edge_segments(self, letter_a, letter_b):
        """All half-edges of A that border B."""
        fa, fb = self.region(letter_a), self.region(letter_b)
        segs = [e for e in fa.edges if e.reverse.leftFace is fb]
        if not segs:
            raise ValueError(f"Regions {letter_a} and {letter_b} share no edge.")
        return segs

    # ---------- rendering ----------
    def render(self, side=DISPLAY_SIDE):
        img = self.session.render().convert("RGB")
        if side:
            return img.resize((side, side), Image.Resampling.LANCZOS)
        return img

    # ---------- execution ----------
    def _finish(self, tool, call_str, message):
        self.program.append(call_str)
        self.log.append(message)
        self.tool_calls.append({"tool": tool, "input": call_str,
                                "output_text": message, "display_text": message})
        return message

    def run(self, tool, args=None):
        """Execute one annotation tool. Returns participant-facing text.

        The text confirms what was drawn and says nothing about the map. To
        learn anything the model must look at the next render.
        """
        args = args or {}
        try:
            if tool == "label_vertex":
                v = self.resolve_vertex(args)
                self.session.add_vertex_action(v, auto_enumerate=True)
                label = self._last_label("vertex")
                return self._finish(
                    tool, f"label_vertex({args})",
                    f"Labeled a vertex as **{label}**.")

            if tool == "label_angle":
                face = self.region(args["region"])
                v = self.resolve_vertex(args)
                self.session.add_angle_action((face, v), auto_enumerate=True)
                label = self._last_label("angle")
                return self._finish(
                    tool, f"label_angle({args})",
                    f"Marked the angle in Region {args['region']} "
                    f"as **{label}**.")

            if tool == "label_edge":
                a, b = args["edge"]
                segs = self.resolve_edge_segments(a, b)
                self.session.add_edge_action(segs, auto_enumerate=True)
                label = self._last_label("edge")
                return self._finish(
                    tool, f"label_edge({args})",
                    f"Highlighted the edge between Regions {a} and {b} "
                    f"as **{label}**.")

            if tool == "highlight_region":
                face = self.region(args["region"])
                self.session.add_region_action(face)
                return self._finish(
                    tool, f"highlight_region({args})",
                    f"Highlighted Region {args['region']}.")

            if tool == "union":
                fa = self.region(args["region_a"])
                fb = self.region(args["region_b"])
                if not any(e.reverse.leftFace is fb for e in fa.edges):
                    raise ValueError(
                        f"Regions {args['region_a']} and {args['region_b']} "
                        "share no border.")
                self.session.add_union_action(fa, fb, self.maxX, self.maxY)
                return self._finish(
                    tool, f"union({args})",
                    f"Merged Regions {args['region_a']} and "
                    f"{args['region_b']} into one shaded region.")

            if tool == "draw_line":
                style = args.get("style", "segment")
                if style == "extend_edge":
                    a, b = args["edge"]
                    seg = self.resolve_edge_segments(a, b)[0]
                    self.session.add_auxiliary_line_action(
                        VA.tool_draw_extended_edge, seg)
                    msg = (f"Extended the edge between Regions {a} and {b} "
                           "to the frame.")
                elif style == "axis":
                    v = self.resolve_vertex(args)
                    d = args.get("direction", "H")
                    self.session.add_auxiliary_line_action(
                        VA.tool_draw_axis_line, v.p, d)
                    word = "horizontal" if d.upper() == "H" else "vertical"
                    msg = f"Drew a {word} line through the vertex."
                else:
                    v1 = self.resolve_vertex(args["from"])
                    v2 = self.resolve_vertex(args["to"])
                    self.session.add_auxiliary_line_action(
                        VA.tool_draw_points_line, v1.p, v2.p,
                        style == "full")
                    msg = ("Drew a full line through the two vertices."
                           if style == "full"
                           else "Drew a segment between the two vertices.")
                return self._finish(tool, f"draw_line({args})", msg)

            if tool == "undo":
                if not self.session.actions:
                    return self._finish(tool, "undo()",
                                        "There is nothing to undo.")
                self.session.undo_action()
                return self._finish(tool, "undo()",
                                    "Undid the last annotation.")

            raise ValueError(
                f"Unknown tool {tool!r}. One of: {ANNOTATION_TOOLS}")

        except Exception as ex:
            message = ("This tool could not complete this operation. "
                       "Check your selection and settings, then try again.")
            self.log.append(message)
            self.tool_calls.append({"tool": tool, "input": f"run {tool}",
                                    "output_text": message,
                                    "display_text": message,
                                    "error": f"{type(ex).__name__}: {ex}"})
            return message

    def _last_label(self, category):
        """The label AnnotationSession just auto-assigned."""
        if not self.session.actions:
            return "?"
        func, a, _ = self.session.actions[-1]
        name = func.__name__.lower()
        if "label_vertex" in name:
            return a[1] if len(a) > 1 else "?"
        if "label_angle" in name or "label_edge" in name:
            return a[2] if len(a) > 2 else "?"
        return "?"

    # ---------- whole-workspace controls ----------
    def undo(self):
        return self.run("undo")

    def clear_all(self):
        n = len(self.session.actions)
        while self.session.actions:
            self.session.undo_action()
        self.log, self.tool_calls, self.program = [], [], []
        if not n:
            return "The diagram is already in its starting state."
        return f"Cleared the workspace. Undid {n} annotation{'s' if n != 1 else ''}."

    # geo_agent compatibility: nothing to clear between calls, since every
    # annotation call carries its own selection.
    def clear_selection(self):
        return self