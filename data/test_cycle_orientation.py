"""Variable-size cycle orientation across geometry, model and survey."""
import contextlib
import importlib.util
import io
from types import SimpleNamespace
import unittest
import Graph
import tools_human as tools
from test_incident_edge_count import load_functions


def points(coords):
    return [SimpleNamespace(p=Graph.Vector(x,y),outarcs=[]) for x,y in coords]

class CycleOrientationTests(unittest.TestCase):
    def test_simple_convex_concave_and_collinear_boundary(self):
        for coords in [[(0,0),(2,0),(2,2),(0,2)],
                       [(0,0),(2,0),(2,2),(1,1),(0,2)],
                       [(0,0),(1,0),(2,0),(2,2),(0,2)]]:
            p=points(coords)
            self.assertEqual(tools.measure(*p,what='orientation'),'Counterclockwise')
            self.assertEqual(tools.measure(*reversed(p),what='orientation'),'Clockwise')

    def test_invalid_cycles(self):
        for coords in [[(0,0),(1,1)],[(0,0),(1,0),(2,0)],
                       [(0,0),(2,2),(0,2),(2,0)],
                       [(0,0),(2,0),(2,2),(0,0)],
                       [(0,0),(2,0),(1,0),(1,2),(0,2)]]:
            with self.subTest(coords=coords),self.assertRaises(ValueError):
                tools.measure(*points(coords),what='orientation')

    def test_actual_model_dispatch_and_trace(self):
        spec=importlib.util.spec_from_file_location('cycle_env','geo_agent/geo_env.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        ns=load_functions('geo_agent/geo_agent.py',{'dispatch','_vertex_by_name','_edge_by_name','_line_by_name'})
        with contextlib.redirect_stdout(io.StringIO()):e=m.Env(5,6100,structure_complexity='high')
        corners=[min(e.res_map.vertices,key=lambda v:(v.p.x,v.p.y)),
                 max(e.res_map.vertices,key=lambda v:(v.p.x,-v.p.y)),
                 max(e.res_map.vertices,key=lambda v:(v.p.x,v.p.y)),
                 min(e.res_map.vertices,key=lambda v:(v.p.x,-v.p.y))]
        labels=[e.point_name(v) for v in corners]
        result=ns['dispatch'](e,'measure',{'what':'orientation','vertices':labels})
        self.assertIn('Counterclockwise',result)
        self.assertTrue(all(label in e.tool_calls[-1]['input'] for label in labels))
        self.assertFalse(e.selection)

    def test_survey_handler_with_five_points(self):
        class State(dict):
            __getattr__=dict.__getitem__
        class Rerun(BaseException):pass
        p=points([(0,0),(2,0),(2,2),(1,1),(0,2)])
        state=State(selection=p)
        ns={'st':SimpleNamespace(session_state=state),'T':tools,'IS_PRACTICE':False}
        load_functions('compositional_survey.py',{'validate','sel_sig','is_vertex','is_region','is_angle','is_edgesel','run_tool'},ns)
        out=[]
        def finish(tool,call,result,**kw):
            out.append((call,result));raise Rerun()
        ns.update(finish=finish,code_name=lambda v:'v'+str(next(i for i,x in enumerate(p,1) if x is v)))
        self.assertTrue(ns['validate']('measure',{'what':'orientation'})[0])
        with self.assertRaises(Rerun):ns['run_tool']('measure',{'what':'orientation'})
        self.assertEqual(out,[('measure(v1, v2, v3, v4, v5, what="orientation")','Counterclockwise')])

if __name__=='__main__':unittest.main()
