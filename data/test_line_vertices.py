"""Distinct map-vertex queries and source-edge endpoint exclusions."""
import contextlib,importlib.util,io
from types import SimpleNamespace
import unittest
import Graph,tools_human as t
from sel_types import EdgeSel
from test_incident_edge_count import load_functions
from test_merge_multiple_regions import grid
class LineVertexTests(unittest.TestCase):
    def setUp(self):
        self.fs=grid(3,1)
        self.v=list({v for f in self.fs for v in f.vertices})
        self.m=SimpleNamespace(vertices=self.v,faces=self.fs,bounds=(3,1))
        t.setup(self.m)
    def test_full_line_endpoint_exclusion_and_unique_points(self):
        f=self.fs[1];line=t.draw([f.edges[0]],kind='full')
        self.assertEqual(len(t.intersect(line,'vertices')),2)
        r=t.intersect(line,'vertices')
        self.assertEqual([p.p.x for p in r],[0,3])
        self.m.vertices.append(SimpleNamespace(p=Graph.Vector(0,0),outarcs=[]))
        self.assertEqual(len(t.intersect(line,'vertices')),2)
    def test_segment_ray_empty_and_invalid_exclusion(self):
        f=self.fs[1];line=t.draw([f.edges[0]])
        self.assertEqual(t.intersect(line,'vertices'),[])
        p=next(v for v in self.v if v.p.x==1 and v.p.y==0)
        self.assertEqual(len(t.intersect(t.draw(p,'right'),'vertices')),3)
        self.assertIn(p,t.intersect(t.draw(p,'right'),'vertices'))
    def test_real_model_draw_dispatch_and_trace(self):
        spec=importlib.util.spec_from_file_location('line_vertices_env','geo_agent/geo_env.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        ns=load_functions('geo_agent/geo_agent.py',{'dispatch','_vertex_by_name','_edge_by_name','_line_by_name'})
        with contextlib.redirect_stdout(io.StringIO()):e=m.Env(5,6100,structure_complexity='high')
        f=next(f for f in e.res_map.faces if f.bounded);edge=EdgeSel([f.edges[0]],f,'test')
        e.select_edge(edge);label=e.edge_name(edge);e.clear_selection()
        # Public model draw_line uses edge_regions rather than a named-edge input;
        # exercise native environment drawing with a saved edge selection.
        e.select_edge(edge);e.run('draw line',{'style':'full line'})
        name,line=e.lines[-1];self.assertIn('source_edge_endpoints',line)
        msg=ns['dispatch'](e,'intersect',{'line':name,'target':'vertices'})
        self.assertIn('Number of vertices',msg);self.assertEqual(e.tool_calls[-1]['tool'],'intersect')
        expected=t.intersect(line,'vertices')
        self.assertTrue(all(any(a['kind']=='point' and a['p'] is v.p for a in e.annotations) for v in expected))
    def test_survey_execution_and_formatter(self):
        class State(dict):__getattr__=dict.__getitem__
        state=State(res_map=self.m,selection=[],lines=[]);out=[]
        class Rerun(BaseException):pass
        def finish_vertex(call,result,**kw):out.append((call,result,kw));raise Rerun()
        ns={'st':SimpleNamespace(session_state=state),'T':t,'finish_vertex':finish_vertex}
        load_functions('compositional_survey.py',{'run_tool','sel_sig','is_vertex','is_region','is_angle','is_edgesel'},ns)
        line=t.draw([self.fs[1].edges[0]],kind='full')
        with self.assertRaises(Rerun):ns['run_tool']('intersect',{'line':('L1',line),'target':'vertices'})
        self.assertEqual(len(out[0][1]),2);self.assertEqual(out[0][2]['trace_tool'],'intersect')
if __name__=='__main__':unittest.main()
