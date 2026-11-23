"""Parallel edges: distinct supporting lines, shared survey/model behavior."""
import contextlib
import importlib.util
import io
from types import SimpleNamespace
import unittest
import tools_human as tools
from sel_types import EdgeSel
from test_point_edge_distance import segment
from test_incident_edge_count import load_functions

class ParallelTests(unittest.TestCase):
    def test_geometry(self):
        a=segment((0,0),(2,0))
        for b,expected in [(segment((3,1),(0,1)),True),
                           (segment((0,0),(0,2)),False),
                           (segment((3,0),(4,0)),False),
                           (segment((0,1),(2,2)),False)]:
            self.assertIs(tools.measure(a,b,what='parallel'),expected)
        diagonal=segment((0,0),(2,2))
        self.assertTrue(tools.measure(diagonal,segment((1,2),(3,4)),what='parallel'))
        for b in [segment((0,0),(0,0)),EdgeSel([],None,'empty'),
                  EdgeSel([segment((0,0),(1,0)),segment((1,0),(1,1))],None,'bent')]:
            with self.assertRaises(ValueError):tools.measure(a,b,what='parallel')
        chain=EdgeSel([segment((0,0),(1,0)),segment((1,0),(2,0))],None,'straight')
        self.assertTrue(tools.measure(chain,segment((0,1),(1,1)),what='parallel'))

    def test_model_dispatch_and_trace(self):
        spec=importlib.util.spec_from_file_location('parallel_env','geo_agent/geo_env.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        ns=load_functions('geo_agent/geo_agent.py',{'dispatch','_edge_by_name','_vertex_by_name','_line_by_name'})
        with contextlib.redirect_stdout(io.StringIO()):e=m.Env(5,6100,structure_complexity='high')
        face=next(f for f in e.res_map.faces if f.bounded)
        first=EdgeSel([face.edges[0]],face,'first');second=EdgeSel([face.edges[1]],face,'second')
        e.select_edge(first);e.select_edge(second);labels=[e.edge_name(x) for x in (first,second)];e.clear_selection()
        msg=ns['dispatch'](e,'measure',{'what':'parallel','edges':labels})
        self.assertIn('parallel?',msg);self.assertIn('Yes' if tools.measure(first,second,what='parallel') else 'No',msg)
        self.assertFalse(e.selection);self.assertEqual(e.tool_calls[-1]['tool'],'measure')
        with self.assertRaises(ValueError):ns['dispatch'](e,'measure',{'what':'parallel','edges':labels[:1]})

    def test_survey_handler(self):
        class State(dict):__getattr__=dict.__getitem__
        class Rerun(BaseException):pass
        a=EdgeSel([segment((0,0),(1,0))],None,'a');b=EdgeSel([segment((0,1),(1,1))],None,'b')
        state=State(selection=[a,b]);out=[]
        ns={'st':SimpleNamespace(session_state=state),'T':tools,'IS_PRACTICE':False}
        load_functions('compositional_survey.py',{'validate','sel_sig','is_vertex','is_region','is_angle','is_edgesel','run_tool'},ns)
        def finish(tool,call,value,**kw):out.append((call,value));raise Rerun()
        ns.update(finish=finish,code_name=lambda x:'e1' if x is a else 'e2')
        self.assertTrue(ns['validate']('measure',{'what':'parallel'})[0])
        with self.assertRaises(Rerun):ns['run_tool']('measure',{'what':'parallel'})
        self.assertEqual(out,[('measure(e1, e2, what="parallel")',True)])

if __name__=='__main__':unittest.main()
