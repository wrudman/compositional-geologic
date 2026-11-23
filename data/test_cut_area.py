"""C-043 areas only: clipping, region/line validation and both interfaces."""
import contextlib,importlib.util,io,math
from types import SimpleNamespace
import unittest
import Graph,tools_human as t
from test_merge_multiple_regions import grid
from test_incident_edge_count import load_functions

def point(x,y):return SimpleNamespace(p=Graph.Vector(x,y),outarcs=[])
def line(a,b):return t.draw(point(*a),point(*b),kind='full')
class CutAreaTests(unittest.TestCase):
    def test_rectangle_sloping_and_reversed_line(self):
        r=grid(1,1)[0]
        for l in [line((0,.25),(1,.25)),line((1,.25),(0,.25))]:
            self.assertEqual(t.measure(r,what='area',line=l),{'above':.75,'below':.25})
        v=t.measure(r,what='area',line=line((0,0),(1,1)))
        self.assertAlmostEqual(v['above'],.5);self.assertAlmostEqual(v['below'],.5)
    def test_concave_union_and_invalid_cuts(self):
        fs=grid(2,2);r=t.merge(fs[0],fs[1],fs[2])
        self.assertEqual(t.measure(r,what='area',line=line((0,.5),(2,.5))),{'above':2.,'below':1.})
        square=fs[0]
        for l in [line((0,2),(1,2)),line((0,0),(1,0)),line((.5,0),(.5,1)),t.draw(point(0,.5),'right')]:
            with self.assertRaises(ValueError):t.measure(square,what='area',line=l)
        # A U shape cut horizontally produces three pieces, so reject.
        coords=[(0,0),(3,0),(3,3),(2,3),(2,1),(1,1),(1,3),(0,3)]
        u=SimpleNamespace(vertices=[point(x,y) for x,y in coords],edges=[],bounded=True)
        with self.assertRaisesRegex(ValueError,'more than two'):t.measure(u,what='area',line=line((0,2),(3,2)))
    def test_left_right_vertical_and_boundary_overlap(self):
        square=grid(1,1)[0]
        for l in [line((.25,0),(.25,1)),line((.25,1),(.25,0))]:
            self.assertEqual(t.measure(square,what='area',line=l,area_sides='left_right'),{'left':.25,'right':.75})
        # Boundary notch lies on the cut, but both resulting sides are connected.
        coords=[(0,0),(3,0),(3,3),(2,3),(2,1),(1,1),(1,3),(0,3)]
        u=SimpleNamespace(vertices=[point(x,y) for x,y in coords],edges=[],bounded=True)
        result=t.measure(u,what='area',line=line((1,0),(1,3)),area_sides='left_right')
        self.assertAlmostEqual(result['left'],3);self.assertAlmostEqual(result['right'],4)
        self.assertAlmostEqual(sum(result.values()),7)

    def test_model_dispatch_and_no_comparison_output(self):
        spec=importlib.util.spec_from_file_location('cut_env','geo_agent/geo_env.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        ns=load_functions('geo_agent/geo_agent.py',{'dispatch','_vertex_by_name','_edge_by_name','_line_by_name'})
        with contextlib.redirect_stdout(io.StringIO()):e=m.Env(5,6100,structure_complexity='high')
        r=next(f for f in e.res_map.faces if f.bounded and f.convex)
        y=(min(v.p.y for v in r.vertices)+max(v.p.y for v in r.vertices))/2
        e.lines.append(('L1',line((0,y),(1,y))))
        msg=ns['dispatch'](e,'measure',{'what':'area','regions':[r.letter],'line':'L1'})
        self.assertIn('Area above L1:',msg);self.assertIn('Area below L1:',msg)
        self.assertNotIn('larger',msg);self.assertNotIn('Yes',msg);self.assertFalse(e.selection)
        x=(min(v.p.x for v in r.vertices)+max(v.p.x for v in r.vertices))/2
        e.lines.append(('L2',line((x,0),(x,1))))
        msg=ns['dispatch'](e,'measure',{'what':'area','regions':[r.letter],'line':'L2','area_sides':'left_right'})
        self.assertIn('Area left of L2:',msg);self.assertIn('Area right of L2:',msg)
        self.assertEqual(set(e.tool_calls[-1]['areas']),{'left','right'})

    def test_survey_real_finish_output_and_trace(self):
        # Keep real finish/formatting/serialization, rather than mocking finish.
        import re
        from unittest.mock import Mock
        class State(dict): __getattr__=dict.__getitem__
        class Rerun(BaseException): pass
        logs=[];records=[]
        ns={'re':re,'st':SimpleNamespace(session_state=State(),rerun=lambda:(_ for _ in ()).throw(Rerun())),
            'next_name':lambda prefix:'r1','add_program':Mock(),'add_log':logs.append,
            'record_tool_call':lambda *args:records.append(args),'clear_selection':Mock(),
            'natural_join':lambda xs:', '.join(xs)}
        load_functions('compositional_survey.py',{'finish','answer_like_text','participant_output_for_tool',
            '_tool_output','is_angle','is_edgesel','is_region','is_vertex'},ns)
        r=grid(1,1)[0]
        for mode,l in [('above_below',line((0,.25),(1,.25))),('left_right',line((.25,0),(.25,1)))]:
            result=t.measure(r,what='area',line=l,area_sides=mode)
            with self.assertRaises(Rerun):
                ns['finish']('measure',f'measure(C, what="area", line=L1, area_sides="{mode}")',result,visualize=False)
            self.assertEqual(records[-1][3],{'type':'measurements','values':result})
            self.assertIn('0.2500',logs[-1]);self.assertIn('0.7500',logs[-1])
        ns['clear_selection'].assert_called()

    def test_survey_handler_and_validation(self):
        class State(dict):__getattr__=dict.__getitem__
        class Rerun(BaseException):pass
        r=grid(1,1)[0];l=line((0,.25),(1,.25));state=State(selection=[r],lines=[('L1',l)])
        ns={'st':SimpleNamespace(session_state=state),'T':t,'IS_PRACTICE':False};out=[]
        load_functions('compositional_survey.py',{'validate','run_tool','sel_sig','is_vertex','is_region','is_angle','is_edgesel'},ns)
        def finish(tool,call,value,**kw):out.append(value);raise Rerun()
        ns['finish']=finish;modes={'what':'area','cut_area':True,'line':('L1',l)}
        self.assertTrue(ns['validate']('measure',modes)[0])
        with self.assertRaises(Rerun):ns['run_tool']('measure',modes)
        self.assertEqual(out,[{'above':.75,'below':.25}])
        self.assertFalse(ns['validate']('measure',{'what':'area','cut_area':True})[0])
if __name__=='__main__':unittest.main()
