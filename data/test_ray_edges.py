"""C-112: proper ray crossings, automatic origin/frame exclusion."""
import contextlib,importlib.util,io
from types import SimpleNamespace
import unittest
import Graph,tools_human as t
from test_merge_multiple_regions import grid
from test_incident_edge_count import load_functions
class RayEdgeTests(unittest.TestCase):
    def setUp(self):
        self.fs=grid(2,3)
        vertices=list({v for f in self.fs for v in f.vertices})
        edges=list({e for f in self.fs for e in f.edges})
        self.m=SimpleNamespace(vertices=vertices,edges=edges,faces=self.fs,bounds=(2,3));t.setup(self.m)
    def point(self,x,y):return SimpleNamespace(p=Graph.Vector(x,y),outarcs=[])
    def test_origin_frame_reverse_and_ray_order(self):
        ray=t.draw(self.point(.5,3),'down');hits=t.intersect(ray,'edges')
        self.assertEqual(len(hits),2)
        self.assertEqual([e.segments[0].tail.p.y for e in hits],[2,1])
        # Add reverse half edges: still one count per physical crossing.
        self.m.edges += [e.reverse for e in list(self.m.edges)]
        self.assertEqual(len(t.intersect(ray,'edges')),2)
        self.assertEqual(len(t.intersect(t.draw(self.point(.5,2),'down'),'edges')),1)
        self.assertEqual(t.intersect(t.draw(self.point(.5,.5),'down'),'edges'),[])
    def test_ambiguous_vertex_overlap_and_nonray_rejected(self):
        self.assertEqual(t.intersect(t.draw(self.point(1,3),'down'),'edges'),[])
        # A diagonal isn't part of cardinal-ray API. Test a point hit without overlap
        # using a vertical ray through a native triangle's top vertex.
        p=self.point(.5,1.5);self.m.vertices.append(p)
        with self.assertRaisesRegex(ValueError,'passes through a vertex'):t.intersect(t.draw(self.point(.5,3),'down'),'edges')
        with self.assertRaisesRegex(ValueError,'Select a ray'):t.intersect(t.draw(self.point(.2,0),self.point(1.8,3)),'edges')
    def test_full_line_and_segment_rejected(self):
        a,b=self.point(.5,.5),self.point(.5,2.5)
        for kind in ['full','segment']:
            with self.assertRaisesRegex(ValueError,'Select a ray'):
                t.intersect(t.draw(a,b,kind=kind),'edges')

    def test_model_dispatch_and_persistent_edge_names(self):
        spec=importlib.util.spec_from_file_location('ray_edge_env','geo_agent/geo_env.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        ns=load_functions('geo_agent/geo_agent.py',{'dispatch','_vertex_by_name','_edge_by_name','_line_by_name'})
        with contextlib.redirect_stdout(io.StringIO()):e=m.Env(8,6100,structure_complexity='high')
        t.setup(e.res_map)
        chosen=None
        for v in e.res_map.vertices:
            line=t.draw(v,'down')
            try:result=t.intersect(line,'edges')
            except ValueError:continue
            if result:chosen=(line,result);break
        self.assertIsNotNone(chosen)
        line,result=chosen;e.lines.append(('L1',line))
        msg=ns['dispatch'](e,'intersect',{'line':'L1','target':'edges'})
        self.assertIn(f'**{len(result)}**',msg);self.assertNotIn('Edges:',msg)
        self.assertEqual(e.tool_calls[-1]['tool'],'intersect')
        self.assertFalse(e.named_edges);self.assertFalse(e.selection)
        self.assertEqual(len(e.tool_calls[-1]['crossed_edges']),len(result))
        self.assertEqual(e.tool_calls[-1]['output_text'],str(len(result)))
    def test_survey_names_and_trace(self):
        class State(dict):__getattr__=dict.__getitem__
        class Rerun(BaseException):pass
        state=State(res_map=self.m,selection=[],named_edges=[])
        outputs=[];ns={'st':SimpleNamespace(session_state=state),'T':t,'next_name':lambda prefix:f'e{len(state.named_edges)+1}'}
        load_functions('compositional_survey.py',{'run_tool','sel_sig','is_vertex','is_region','is_angle','is_edgesel'},ns)
        ns['edge_name']=lambda edge:next((name for name,e in state.named_edges if e==edge),None)
        def finish(tool,call,value,**kw):outputs.append((tool,call,value));raise Rerun()
        ns['finish']=finish
        with self.assertRaises(Rerun):ns['run_tool']('intersect',{'line':('L1',t.draw(self.point(.5,3),'down')),'target':'edges'})
        self.assertEqual(len(state.named_edges),0);self.assertEqual(outputs[0][0],'intersect')
        self.assertEqual(outputs[0][2],2)
if __name__=='__main__':unittest.main()
