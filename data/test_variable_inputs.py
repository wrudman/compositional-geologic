"""Variable-size questions, scalar compatibility, and one-call survey batches."""
import ast
import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
import BuildRandomMap
import Graph
import Questions as Q
import RandomQuestions as R
import reference_programs as refs
import tools_human as T
from sel_types import AngleSel
from test_merge_multiple_regions import grid


ROOT = Path(__file__).parent


def survey_functions(names, namespace):
    """Exercise production handlers without starting a survey or contacting its DB."""
    module = ast.parse((ROOT / "compositional_survey.py").read_text())
    functions = [node for node in module.body if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=functions, type_ignores=[]), "survey_handlers", "exec"), namespace)
    return namespace


class VariableInputTests(unittest.TestCase):
    def setUp(self):
        self.counts = R.INPUT_COUNTS.copy()

    def tearDown(self):
        R.INPUT_COUNTS.update(self.counts)

    def test_batch_measurements_preserve_order_and_scalar_results(self):
        faces = grid(6, 1)
        for what in ("area", "edge_count", "sides"):
            self.assertEqual(T.measure(faces, what=what), [T.measure(f, what=what) for f in faces])
        angles = [AngleSel(f.vertices[0], f) for f in faces]
        self.assertEqual(T.measure(angles, what="angle"), [90.] * 6)
        self.assertEqual(T.measure([(a.vertex, a.face) for a in angles], what="angle"), [90.] * 6)
        self.assertEqual(T.measure(angles[0], what="angle"), 90.)
        self.assertEqual(T.measure(faces[1:], what="distance", reference=faces[0]), [0., 1., 2., 3., 4.])
        vertices = [face.vertices[0] for face in faces]
        self.assertEqual(T.measure(vertices[1:], what="distance", reference=vertices[0]), [1., 2., 3., 4., 5.])
        self.assertEqual(T.measure(vertices[0], vertices[-1], what="distance"), 5.)

    def test_invalid_batch_inputs_and_orientation(self):
        a, b = grid(2, 1)
        cases = [([], "angle", {}), ([a, b], "distance", {}),
                 ([a], "distance", {"reference": a.vertices[0]}),
                 ([a], "angle", {}), ([a.vertices[0]], "area", {}),
                 ([a, b], "orientation", {})]
        for objects, what, kwargs in cases:
            with self.subTest(what=what, objects=objects), self.assertRaises(ValueError):
                T.measure(objects, what=what, **kwargs)
        self.assertIn(T.measure(*a.vertices[:3], what="orientation"), ("Clockwise", "Counterclockwise"))
        with self.assertRaisesRegex(ValueError, "exactly three"):
            T.measure(*a.vertices[:4], what="orientation")
        with self.assertRaises(ValueError):
            T.measure(a, b, what="area")

    def test_sort_more_than_three(self):
        faces = grid(6, 1)
        vertices = [f.vertices[0] for f in faces]
        self.assertEqual(T.sort(vertices[::-1], by="left_right"), vertices)
        self.assertEqual(T.sort(vertices[:0:-1], by="distance", reference=vertices[0]), vertices[1:])
        self.assertEqual(len(T.sort(faces, by="area")), 6)
        self.assertEqual(len(T.sort([AngleSel(faces[0].vertices[i], faces[0]) for i in range(4)], by="angle")), 4)

    def test_n_point_questions_and_multidigit_reference_labels(self):
        Graph.initialize()
        vertices = [Graph.Vertex(Graph.Vector(i / 12, 0.1)) for i in range(11)]
        with patch.object(Q, "identifyVertex", return_value="the leftmost vertex of A"):
            position = Q.Question20(vertices, 0, [0] * 11)
            self.assertIn("v₁₁", position[0])
            self.assertEqual(len(position[2]), 11)
            text_ref = refs.build_reference_program(20, position[0])
            input_ref = refs.build_reference_program_from_inputs(20, vertices, 0, [0] * 11)
            self.assertEqual(text_ref, input_ref)
            reference = Graph.Vertex(Graph.Vector(0, 0))
            targets = [Graph.Vertex(Graph.Vector(1.5 ** i, 0)) for i in range(6)]
            distance = Q.Question10(reference, targets, [0] * 7)
            self.assertEqual(len(distance[2]), 6)
            self.assertEqual(refs.build_reference_program(10, distance[0]),
                             refs.build_reference_program_from_inputs(10, reference, targets, [0] * 7))

    def test_n_angle_question_same_region(self):
        face = SimpleNamespace(letter="A", trueVertices=[None] + list(range(6)))
        with patch.object(Graph, "angleAtFace", side_effect=lambda vertex, face: 0.3 + vertex * 0.25), \
             patch.object(Q, "identifyVertexForQ11", return_value="the leftmost vertex of A"):
            result = Q.Question11(face, [0] * 6)
            self.assertIn("Region A has 6 interior angles", result[0])
            self.assertEqual(len(result[2]), 6)
            self.assertEqual(refs.build_reference_program(11, result[0]),
                             refs.build_reference_program_from_inputs(11, face, [0] * 6))

    def test_union_questions_accept_more_regions(self):
        faces = grid(7, 1)
        for i, face in enumerate(faces):
            face.letter = chr(65 + i)
        map_ = SimpleNamespace(faces=faces)
        cases = [(14, Q.Question14, (faces[:3],)),
                 (15, Q.Question15, (faces[:3], None, map_)),
                 (33, Q.Question33, (faces[:3], None, faces[3]))]
        for qid, function, inputs in cases:
            result = function(*inputs)
            self.assertTrue(result[0])
            self.assertIn("A, B, and C", result[0])
            self.assertEqual(refs.build_reference_program(qid, result[0]),
                             refs.build_reference_program_from_inputs(qid, *inputs))
        # Distinct areas make a five-object order with a three-region union.
        for face, area in zip(faces[3:], [5., 8., 13., 21.]):
            face.area = area
        entries = [faces[:3], *faces[3:]]
        result = Q.Question16(entries, map_)
        self.assertEqual(len(result[2]), 5)
        self.assertEqual(refs.build_reference_program(16, result[0]),
                         refs.build_reference_program_from_inputs(16, entries, map_))

    def test_existing_bank_reference_coverage(self):
        bank = ROOT / "Balanced_24_Diagram_Question_Pairs/dataset_24_balanced.json"
        if not bank.exists():
            bank = ROOT / "dataset_24_balanced.json"
        data = json.loads(bank.read_text())
        items = data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))
        seen = set()
        for item in items:
            q = item["question"]
            program = refs.build_reference_program(q["question_id"], q["question_text"])
            self.assertEqual(program["tool_version"], T.TOOL_VERSION)
            seen.add(q["question_id"])
        self.assertEqual(seen, set(refs.ACTIVE_QUESTION_IDS))
        program = refs.build_reference_program(2, "Do regions A and B have the same number of edges?")
        self.assertEqual(program["tool_call_site_count"], 1)

    def test_survey_batch_one_call_with_labeled_values(self):
        faces = grid(5, 1)
        namespace = survey_functions({"measurement_batch_finish"}, {
            "T": T, "code_name": lambda obj: obj.letter,
            "_tool_output": lambda obj: {"type": "region", "label": obj.letter},
            "add_program": Mock(), "add_log": Mock(), "record_tool_call": Mock(),
            "clear_selection": Mock(), "st": SimpleNamespace(rerun=Mock()),
        })
        namespace["measurement_batch_finish"](faces, "edge_count")
        namespace["record_tool_call"].assert_called_once()
        output = namespace["record_tool_call"].call_args.args[3]
        self.assertEqual(output["measurement_count"], 5)
        self.assertEqual([row["label"] for row in output["items"]], [f.letter for f in faces])
        self.assertEqual([row["value"] for row in output["items"]], [4] * 5)
        namespace["clear_selection"].assert_called_once()

    def test_generation_configuration_validation(self):
        for counts in ({"angle": 2}, {"union": 1}, {"position": True}, {"distance": 2.5}, {"bad": 3}):
            with self.assertRaises(ValueError):
                R.set_input_counts(**counts)
        R.set_input_counts(union=3, angle=5, distance=5, position=6, area=5)
        self.assertEqual(R.INPUT_COUNTS["position"], 6)

    def test_sort_ties_for_every_mode(self):
        faces = grid(3, 1)
        square = faces[0]
        left = [v for v in square.vertices[:-1] if v.p.x == 0]
        right = next(v for v in square.vertices if v.p.x == 1)
        self.assertEqual(T.sort([left[0], right, left[1]], by="left_right", grouped=True), [left, [right]])
        bottom = [v for v in square.vertices[:-1] if v.p.y == 0]
        self.assertEqual(T.sort(bottom, by="bottom_top", grouped=True), [bottom])
        self.assertEqual(T.sort(faces, by="area", grouped=True), [faces])
        angles = [AngleSel(v, square) for v in square.vertices[:-1]]
        self.assertEqual(T.sort(angles, by="angle", grouped=True), [angles])
        self.assertEqual(T.sort(square.vertices[:-1], by="angle", reference=square, grouped=True), [square.vertices[:-1]])
        origin = square.vertices[0]
        equidistant = [v for v in square.vertices[:-1] if T.measure(origin, v, what="distance") == 1]
        self.assertEqual(T.sort(equidistant, by="distance", reference=origin, grouped=True), [equidistant])
        self.assertEqual(T.sort([right], by="distance", reference=origin, grouped=True), [[right]])

    def test_sort_tolerance_is_not_rounding_or_transitive(self):
        values = [0., 0.75e-9, 1.5e-9, 0.00101, 0.00102]
        points = [Graph.Vertex(Graph.Vector(x, 0)) for x in values]
        self.assertEqual(T.sort(points, by="left_right", grouped=True),
                         [points[:2], [points[2]], [points[3]], [points[4]]])
        self.assertEqual(T.sort(points[::-1], by="left_right"), points)
        self.assertEqual(T.sort([], by="area", grouped=True), [])

    def test_survey_sort_tie_display_and_record(self):
        import re
        points = [Graph.Vertex(Graph.Vector(x, y)) for x, y in [(0, 0), (1, 0), (0, 1)]]
        labels = {id(p): f"v{i + 1}" for i, p in enumerate(points)}
        namespace = survey_functions({"ranking_finish", "participant_output_for_tool", "natural_join"}, {
            "T": T, "re": re, "code_name": lambda p: labels[id(p)],
            "answer_like_text": lambda p: labels[id(p)],
            "add_program": Mock(), "add_log": Mock(), "record_tool_call": Mock(),
            "clear_selection": Mock(), "st": SimpleNamespace(session_state={}, rerun=Mock()),
        })
        result = T.sort(points, by="left_right")
        namespace["ranking_finish"]('sort([v1, v2, v3], by="left_right")', result, "left_right", None)
        namespace["add_log"].assert_called_once_with("Vertices from left to right: **v1 = v3, v2**.")
        output = namespace["record_tool_call"].call_args.args[3]
        self.assertEqual(output["tie_groups"], [["v1", "v3"], ["v2"]])
        self.assertTrue(output["has_ties"])
        self.assertEqual(output["items"], ["v1", "v3", "v2"])

    def test_survey_validation_and_batch_undo(self):
        class State(dict):
            __getattr__ = dict.__getitem__
            __setattr__ = dict.__setitem__
        faces = grid(5, 1)
        state = State(selection=faces[:], selection_meta=[], annotations=[], lines=[],
                      angles=[], named_edges=[], unions=[], union_consumed=[],
                      point_names={}, counters={}, program=[], log=[], undo_stack=[])
        signature = {"regions": faces, "vertices": [], "angles": [], "edges": [], "frame": [], "n": 5}
        keys = ["selection", "selection_meta", "annotations", "lines", "angles", "named_edges",
                "unions", "union_consumed", "point_names", "counters", "program", "log"]
        namespace = survey_functions({"validate", "measurement_batch_finish", "record_tool_call", "push_undo", "undo_last"}, {
            "T": T, "IS_PRACTICE": False, "sel_sig": lambda: signature,
            "st": SimpleNamespace(session_state=state, rerun=Mock()),
            "code_name": lambda obj: obj.letter,
            "_tool_output": lambda obj: {"type": "region", "label": obj.letter},
            "_selection_event_object": lambda obj: {"label": obj.letter},
            "_ts": lambda: "test-time", "survey_elapsed_seconds": lambda: 1.,
            "_UNDO_KEYS": keys, "add_program": state.program.append, "add_log": state.log.append,
            "clear_selection": lambda: state.update(selection=[]),
        })
        for what in ("area", "sides", "distance"):
            self.assertTrue(namespace["validate"]("measure", {"what": what})[0])
        self.assertFalse(namespace["validate"]("measure", {"what": "orientation"})[0])
        self.assertTrue(namespace["validate"]("sort", {"by": "area"})[0])
        namespace["push_undo"]()
        namespace["measurement_batch_finish"](faces, "edge_count")
        self.assertEqual(len(state.tool_calls), 1)
        self.assertEqual(state.tool_calls[0]["input_count"], 5)
        self.assertEqual(state.tool_calls[0]["function"], "edge_count")
        self.assertTrue(state.tool_calls[0]["batch"])
        self.assertEqual(state.selection, [])
        namespace["undo_last"]()
        self.assertEqual(state.selection, faces)
        self.assertEqual(state.program, [])
        self.assertEqual(state.log, [])
        self.assertEqual(state.tool_calls[0]["status"], "undone")

    def test_real_map_generation_and_reference_agreement(self):
        R.set_input_counts(union=3, angle=5, distance=4, position=5, area=4)
        pending = {10, 11, 14, 15, 16, 20, 30, 33}
        import random
        old_map = getattr(R, "map", None)
        try:
            with patch.object(BuildRandomMap.DrawGraph, "DrawGraph"):
                for seed in range(100, 125):
                    random.seed(seed)
                    try:
                        with contextlib.redirect_stdout(io.StringIO()):
                            R.map = BuildRandomMap.BuildRandomMap(12, 1, 1, seed, structure_complexity="high")
                    except ValueError:
                        # The existing map generator rejects invalid embeddings.
                        continue
                    for qid in sorted(pending):
                        for _ in range(3):
                            result = getattr(R, f"randomQuestion{qid}")()
                            if result[0]:
                                self.assertEqual(refs.build_reference_program(qid, result[0]), R.last_reference_program)
                                pending.remove(qid)
                                break
                    if not pending:
                        break
        finally:
            R.map = old_map
        self.assertEqual(pending, set())


if __name__ == "__main__":
    unittest.main()
