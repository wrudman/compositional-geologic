"""Keep region-corner counting separate from point-contact topology."""
import contextlib,io,os,tempfile,unittest
import BuildRandomMap,Questions as Q
from test_vertex_boundary_order import fan_fixture

class CornerSemanticsTests(unittest.TestCase):
    def test_straight_target_point_is_not_its_corner(self):
        faces,vertices=fan_fixture();target=faces['M'];junction=vertices[6]
        self.assertIn(junction,Q._vp_vertices(target))
        self.assertNotIn(junction,Q._vp_corners(target))
        self.assertIn(junction,Q._vp_corners(faces['D']))

    def test_point_only_neighbors_do_not_require_target_corner(self):
        faces,vertices=fan_fixture()
        self.assertEqual({f.letter for f in Q._vp_neighbors(faces['M'],list(faces.values()))},{'D','N'})

    def test_native_count_and_path_candidates_use_corners(self):
        previous=os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                with contextlib.redirect_stdout(io.StringIO()):m=BuildRandomMap.BuildRandomMap(16,1,1,6100,structure_complexity='high')
                faces={f.letter:f for f in m.faces if f.bounded}
                candidates=list(Q.VertexPropertyCandidates(m,{'seed':6100},condition_ids=['C-090','C-091','C-093','C-095']))
                for c in candidates:
                    e=c['evidence'];cid=c['condition_id']
                    if cid=='C-090':self.assertEqual(c['complexity'],len(Q._vp_corners(faces[e['region']])))
                    if cid in {'C-093','C-095'}:
                        for label,count in e['frame_vertex_counts'].items():self.assertEqual(count,sum(Q._vp_on_frame(v) for v in Q._vp_corners(faces[label])))
                    if cid=='C-091':
                        self.assertEqual(c['complexity'],e['region_vertex_count']-2)
                        self.assertGreaterEqual(min(e['clockwise_intermediate'],e['counterclockwise_intermediate']),1)
                        self.assertNotEqual(e['clockwise_intermediate'],e['counterclockwise_intermediate'])
                self.assertTrue(candidates)
            finally:os.chdir(previous)

if __name__=='__main__':unittest.main()
