"""Regression tests for the single-call, edge-connected merge tool."""
import contextlib
import io
import itertools
import json
from pathlib import Path
import random
import unittest
from unittest.mock import patch

import BuildRandomMap
import Graph
import map_helpers as engine
import tools_human as tools
import survey_union_helpers as survey


def grid(width, height):
    Graph.initialize()
    vertices = {(x, y): Graph.Vertex(Graph.Vector(x, y))
                for x in range(width + 1) for y in range(height + 1)}
    arcs, faces = {}, []
    for y in range(height):
        for x in range(width):
            points = [(x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)]
            edges = []
            for a, b in zip(points, points[1:] + points[:1]):
                if (a, b) not in arcs:
                    edge = Graph.Edge(vertices[a], vertices[b], True)
                    arcs[a, b], arcs[b, a] = edge, edge.reverse
                edges.append(arcs[a, b])
            face = Graph.Face(edges, True)
            faces.append(face)
            for edge in edges:
                edge.leftFace = face
            for point in points:
                vertices[point].faces.append(face)
    outside = type('Outside', (), {'bounded': False})()
    for edge in arcs.values():
        if edge.leftFace is None:
            edge.leftFace = outside
    return faces


class MergeTests(unittest.TestCase):
    def test_merge_readiness_allows_bridge_selection_in_any_order(self):
        a, b, c = grid(3, 1)
        self.assertEqual(survey.merge_selection_error((a, c), []),
                         'The selected regions are not connected by shared edges.')
        self.assertEqual(survey.merge_selection_error((a, c, b), []), '')
        a, b, c, d = grid(2, 2)
        self.assertIn('not connected', survey.merge_selection_error((a, d), []))
        faces = grid(3, 3)
        self.assertIn('holes', survey.merge_selection_error(
            [f for i, f in enumerate(faces) if i != 4], []))

    def test_survey_expands_one_union_and_preserves_undo(self):
        a, b, c, d = grid(4, 1)
        old = tools.merge(a, b)
        old.letter = 'U'
        record = {'face': old, 'name': 'U', 'pair': (a, b)}
        state = {'unions': [record], 'union_consumed': [a, b],
                 'annotations': [{'kind': 'region', 'obj': old}]}
        snapshot = {k: list(v) for k, v in state.items()}
        face, sources, existing = survey.prepare_merge((d, old, c), state['unions'])
        face.letter = existing['name']
        survey.replace_union(state, {'face': face, 'name': face.letter, 'pair': sources}, existing)
        self.assertEqual(len(state['unions']), 1)
        self.assertEqual(face.letter, 'U')
        self.assertEqual(face.area, 4)
        self.assertEqual(set(state['union_consumed']), {a, b, c, d})
        self.assertIs(state['annotations'][0]['obj'], face)
        self.assertIs(snapshot['annotations'][0]['obj'], old)
        self.assertEqual(snapshot['unions'][0]['pair'], (a, b))
        state.update(snapshot)
        self.assertIs(state['unions'][0]['face'], old)
        self.assertEqual(state['union_consumed'], [a, b])

    def test_survey_rejects_second_union_or_disconnected_extension(self):
        a, b, c, d = grid(4, 1)
        old = tools.merge(a, b)
        record = {'face': old, 'name': 'U', 'pair': (a, b)}
        with self.assertRaisesRegex(ValueError, 'Only one union'):
            survey.prepare_merge((c, d), [record])
        with self.assertRaisesRegex(ValueError, 'shared edges'):
            survey.prepare_merge((old, d), [record])
        self.assertEqual(old.area, 2)
        # An already-running survey may still have the old pseudo-face type.
        del old.source_faces
        face, sources, _ = survey.prepare_merge((old, c), [record])
        self.assertEqual(face.area, 3)
        self.assertEqual(sources, (a, b, c))

    def test_chain_all_input_orders(self):
        faces = grid(4, 1)
        for order in itertools.permutations(faces[:3]):
            union = tools.merge(*order)
            self.assertEqual(union.area, 3)
            self.assertEqual(union.numSides, 4)
            self.assertEqual(engine.edge_neighbors(union), {faces[3]})
            self.assertFalse(engine.vertex_only_neighbors(union))

    def test_no_region_count_cap_and_list_input(self):
        faces = grid(20, 1)
        union = tools.merge(faces)
        self.assertEqual(union.area, 20)
        self.assertEqual(union.numSides, 4)

    def test_nested_api_union(self):
        a, b, c = grid(3, 1)
        union = tools.merge(tools.merge(a, b), c)
        self.assertEqual(union.area, 3)
        self.assertEqual(union.numSides, 4)
        with self.assertRaisesRegex(ValueError, 'overlap'):
            tools.merge(tools.merge(a, b), a)

    def test_invalid_selections(self):
        a, b, c, d = grid(2, 2)
        for selection in ((), (a,), (a, a), (a, 'Outside')):
            with self.assertRaises(ValueError):
                tools.merge(*selection)
        with self.assertRaisesRegex(ValueError, 'shared edges'):
            tools.merge(a, d)  # Vertex-only contact.
        faces = grid(3, 1)
        with self.assertRaisesRegex(ValueError, 'shared edges'):
            tools.merge(faces[0], faces[2])

    def test_hole_is_not_silently_filled(self):
        faces = grid(3, 3)
        with self.assertRaisesRegex(ValueError, 'holes'):
            tools.merge([f for i, f in enumerate(faces) if i != 4])
        self.assertEqual(tools.merge(faces).area, 9)

    def test_actual_dataset_answers_and_unchanged_topology(self):
        path = Path(__file__).parent / 'union_merge_cases.json'
        data = json.loads(path.read_text())
        for diagram in data['diagrams']:
            seed = diagram['seed']
            random.seed(seed)
            with patch.object(BuildRandomMap.DrawGraph, 'DrawGraph'), contextlib.redirect_stdout(io.StringIO()):
                map_ = BuildRandomMap.BuildRandomMap(8, 1, 1, seed, structure_complexity='high')
            faces = {f.letter: f for f in map_.faces if f.bounded}
            topology = [(e, e.leftFace, e.reverse) for f in map_.faces for e in f.edges]
            pair = next(p for p in data['pairs'] if p['example_id'] == diagram['example_id'])
            for variant in ('before', 'after'):
                expected = pair[variant]['union']
                union = tools.merge(*(faces[name] for name in expected['regions']))
                self.assertAlmostEqual(union.area, expected['area'])
                self.assertEqual(union.numSides, expected['edge_count'])
                self.assertEqual(sorted(f.letter for f in engine.edge_neighbors(union)), expected['neighbors'])
                self.assertEqual(sorted(f.letter for f in engine.vertex_only_neighbors(union)), expected['vertex_only_neighbors'])
            for edge, face, reverse in topology:
                self.assertIs(edge.leftFace, face)
                self.assertIs(edge.reverse, reverse)


if __name__ == '__main__':
    unittest.main()
