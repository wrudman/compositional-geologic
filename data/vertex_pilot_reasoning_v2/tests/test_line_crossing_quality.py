"""Generation constraints: boundary cases, area threshold, concavity and winding."""
import importlib.util
import unittest
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'generator/line_crossing_quality.py'
spec=importlib.util.spec_from_file_location('line_quality',p)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
check=module.assess_line_polygon
SQUARE=[(0,0),(1,0),(1,1),(0,1)]

class LineQualityTests(unittest.TestCase):
    def test_clear_cut_and_threshold(self):
        self.assertAlmostEqual(check(SQUARE,(-1,.5),(2,.5))['smaller_area_fraction'],.5)
        self.assertTrue(check(SQUARE,(-1,.05),(2,.05))['acceptable'])
        result=check(SQUARE,(-1,.049),(2,.049))
        self.assertFalse(result['acceptable'])
        self.assertEqual(result['classification'],'crossing')
    def test_boundary_overlap(self):
        result=check(SQUARE,(-1,0),(2,0))
        self.assertEqual(result['classification'],'boundary_overlap')
        self.assertFalse(result['acceptable'])
    def test_point_only_contact(self):
        result=check(SQUARE,(-1,1),(1,-1))
        self.assertEqual(result['classification'],'point_touch')
        self.assertFalse(result['acceptable'])
    def test_disjoint_negative_allowed(self):
        result=check(SQUARE,(-1,2),(2,2))
        self.assertEqual(result['classification'],'disjoint')
        self.assertTrue(result['acceptable'])
    def test_concave_disconnected_clipped_pieces(self):
        u=[(0,0),(3,0),(3,3),(2,3),(2,1),(1,1),(1,3),(0,3)]
        self.assertAlmostEqual(check(u,(-1,2),(4,2))['smaller_area_fraction'],2/7)
        # A line may enter the polygon but also run along another boundary edge.
        self.assertEqual(check(u,(-1,1),(4,1))['classification'],'boundary_overlap')
    def test_orientation_and_scale_invariance(self):
        first=check(SQUARE,(-1,.2),(2,.2))
        second=check(list(reversed(SQUARE)),(2,.2),(-1,.2))
        scaled=check([(2*x,2*y) for x,y in SQUARE],(-2,.4),(4,.4))
        self.assertEqual(first['acceptable'],second['acceptable'])
        self.assertAlmostEqual(first['smaller_area_fraction'],second['smaller_area_fraction'])
        self.assertAlmostEqual(first['smaller_area_fraction'],scaled['smaller_area_fraction'])

if __name__=='__main__':unittest.main()
