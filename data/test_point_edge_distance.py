"""Finite point-to-edge distance, shared by survey and agent."""
import contextlib
import importlib.util
import io
import math
from types import SimpleNamespace
import unittest
import Graph
import tools_human as tools
from sel_types import EdgeSel
from test_incident_edge_count import load_functions
from test_merge_multiple_regions import grid

def point(x,y):return SimpleNamespace(p=Graph.Vector(x,y),outarcs=[])
def segment(a,b):return SimpleNamespace(tail=point(*a),head=point(*b),reverse=None,leftFace=None)

class PointEdgeDistanceTests(unittest.TestCase):
    def test_projection_endpoints_reverse_and_contact(self):
        edge=segment((0,0),(2,0))
        for coords,expected in [((1,3),3),((-1,1),math.sqrt(2)),((3,4),math.sqrt(17)),((1,0),0),((2,0),0)]:
            p=point(*coords)
            self.assertAlmostEqual(tools.measure(p,edge,what='distance'),expected)
            self.assertAlmostEqual(tools.measure(edge,p,what='distance'),expected)
        diagonal=segment((0,0),(2,2))
        self.assertAlmostEqual(tools.measure(point(0,2),diagonal,what='distance'),math.sqrt(2))

    def test_selected_edge_and_center(self):
        face=grid(1,1)[0]
        center=tools.find(face,object='centroid')
        edge=EdgeSel([face.edges[0]],face,'bottom')
        self.assertEqual(tools.measure(center,edge,what='distance'),.5)
        compound=EdgeSel([segment((0,0),(1,0)),segment((1,0),(2,0))],face,'bottom')
        self.assertEqual(tools.measure(point(1.5,2),compound,what='distance'),2)
        with self.assertRaises(ValueError):tools.measure(center,EdgeSel([],face,'empty'),what='distance')

    def test_model_dispatch_and_trace(self):
        spec=importlib.util.spec_from_file_location('point_edge_env','geo_agent/geo_env.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        ns=load_functions('geo_agent/geo_agent.py',{'dispatch','_vertex_by_name','_edge_by_name','_line_by_name'})
        with contextlib.redirect_stdout(io.StringIO()):e=m.Env(5,6100,structure_complexity='high')
        face=next(f for f in e.res_map.faces if f.bounded)
        edge=EdgeSel([face.edges[0]],face,'test');e.select_edge(edge);label=e.edge_name(edge);e.clear_selection()
        p=face.vertices[2];name=e.point_name(p)
        expected=round(tools.measure(p,edge,what='distance'),4)
        msg=ns['dispatch'](e,'measure',{'what':'distance','vertices':[name],'edge':label})
        self.assertIn(str(expected),msg);self.assertIn(label,e.tool_calls[-1]['input'])
        self.assertFalse(e.selection)
        with self.assertRaises(ValueError):ns['dispatch'](e,'measure',{'what':'distance','vertices':[name,name],'edge':label})

    def test_survey_validation_and_handler(self):
        class State(dict):__getattr__=dict.__getitem__
        class Rerun(BaseException):pass
        face=grid(1,1)[0];p=tools.find(face,object='centroid');edge=EdgeSel([face.edges[0]],face,'bottom')
        state=State(selection=[edge,p]);out=[]
        ns={'st':SimpleNamespace(session_state=state),'T':tools,'IS_PRACTICE':False}
        load_functions('compositional_survey.py',{'validate','sel_sig','is_vertex','is_region','is_angle','is_edgesel','run_tool'},ns)
        def finish(tool,call,value,**kw):out.append((call,value));raise Rerun()
        ns.update(finish=finish,code_name=lambda o:'e1' if o is edge else 'c1')
        self.assertTrue(ns['validate']('measure',{'what':'distance'})[0])
        with self.assertRaises(Rerun):ns['run_tool']('measure',{'what':'distance'})
        self.assertEqual(out,[('measure(c1, e1, what="distance")',.5)])
        state.selection=[edge,face]
        self.assertFalse(ns['validate']('measure',{'what':'distance'})[0])

if __name__=='__main__':unittest.main()
