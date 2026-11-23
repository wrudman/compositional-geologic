"""Selected-edge length sorting, including composite edges and model dispatch."""
import contextlib,importlib.util,io
import unittest
from sel_types import EdgeSel
from test_merge_multiple_regions import grid
from test_incident_edge_count import load_functions
import tools_human as t

class EdgeSortTests(unittest.TestCase):
    def test_many_edges_ties_and_composite(self):
        faces=grid(3,1)
        edges=[EdgeSel([f.edges[0]],f,str(i)) for i,f in enumerate(faces)]
        composite=EdgeSel([faces[0].edges[0],faces[1].edges[0]],None,'long')
        self.assertEqual(t.edge_length(composite),2)
        self.assertEqual(t.sort([composite,*edges],by='edge_length'),[*edges,composite])
        self.assertEqual(t.sort([composite,*edges],by='edge_length',grouped=True),[edges,[composite]])
        duplicate=EdgeSel([faces[0].edges[0],faces[0].edges[0].reverse],None,'duplicate')
        self.assertEqual(t.edge_length(duplicate),1)
        with self.assertRaises(ValueError):t.sort([edges[0],faces[0]],by='edge_length')
        with self.assertRaises(ValueError):t.sort([edges[0]],by='edge_length')
    def test_model_dispatch(self):
        spec=importlib.util.spec_from_file_location('edge_sort_env','geo_agent/geo_env.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        with contextlib.redirect_stdout(io.StringIO()):env=m.Env(5,6100,structure_complexity='high')
        face=next(f for f in env.res_map.faces if f.bounded)
        edges=[EdgeSel([e],face,str(i)) for i,e in enumerate(face.edges[:3])]
        env.named_edges=[(f'e{i+1}',e) for i,e in enumerate(edges)]
        ns=load_functions('geo_agent/geo_agent.py',{'dispatch','_edge_by_name'})
        output=ns['dispatch'](env,'sort',{'by':'edge_length','edges':['e1','e2','e3']})
        self.assertIn('Edges from shortest to longest',output)
        self.assertFalse(env.selection);self.assertNotIn('error',env.tool_calls[-1])
if __name__=='__main__':unittest.main()
