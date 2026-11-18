"""Regression checks using saved diagram topology; no model/GPU required."""
import ast,json,unittest
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
node=next(n for n in ast.parse((ROOT/'tools/map_helpers.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='vertex_overlap')
namespace={}
exec(compile(ast.Module(body=[node],type_ignores=[]),'vertex_overlap','exec'),namespace)
select=namespace['vertex_overlap']
class Obj:pass

def load(item):
    graph=json.loads((ROOT/'dataset/graphs'/f'{item}.json').read_text())
    vertices={}
    for value in graph['vertices']:
        v=Obj();v.num=value['id'];v.faces=[];vertices[v.num]=v
        if value['x'] in (0,graph['bounds'][0]) or value['y'] in (0,graph['bounds'][1]):
            v.faces.append(SimpleNamespace(bounded=False))
    faces={}
    for value in graph['regions']:
        f=Obj();f.bounded=True;f.letter=value['label'];f.vertices=[vertices[i] for i in value['vertex_ids']];faces[f.letter]=f
        for v in f.vertices:v.faces.append(f)
    return faces

class VertexTests(unittest.TestCase):
    def test_extra_incident_regions_allowed(self):
        f=load('vertex_097_c02')
        self.assertEqual(select(f['E'],f['P'],on_frame=True).num,17)
        self.assertEqual(select(f['M'],f['P']).num,24)
    def test_automatic_frame_selection(self):
        f=load('vertex_097_c02')
        self.assertEqual(select(f['E'],f['P']).num,17)
        self.assertEqual(select(f['M'],f['P']).num,24)
    def test_auto_does_not_guess_between_locations(self):
        a,b=Obj(),Obj();a.letter='A';b.letter='B'
        interior,frame=Obj(),Obj()
        interior.faces=[a,b];frame.faces=[a,b,SimpleNamespace(bounded=False)]
        a.bounded=b.bounded=True
        a.vertices=b.vertices=[interior,frame]
        with self.assertRaisesRegex(ValueError,'Ambiguous'):select(a,b)
        self.assertIs(select(a,b,on_frame=True),frame)
        self.assertIs(select(a,b,on_frame=False),interior)
    def test_frame_filter_still_applies(self):
        f=load('vertex_097_c02')
        self.assertIsNone(select(f['E'],f['P'],on_frame=False))
        self.assertIsNone(select(f['M'],f['P'],on_frame=True))
    def test_second_failure_map(self):
        f=load('vertex_097_c05')
        self.assertEqual(select(f['B'],f['R']).num,23)
        self.assertEqual(select(f['B'],f['C']).num,22)
    def test_multiple_candidates_are_ambiguous(self):
        a,b=Obj(),Obj();a.letter='A';b.letter='B';a.bounded=b.bounded=True
        vs=[Obj(),Obj()]
        for v in vs:v.faces=[a,b]
        a.vertices=vs+[vs[0]];b.vertices=vs
        with self.assertRaisesRegex(ValueError,'Ambiguous'):select(a,b)
    def test_disjoint_and_no_input(self):
        a,b=Obj(),Obj();a.vertices=[];b.vertices=[]
        self.assertIsNone(select(a,b))
        with self.assertRaises(ValueError):select()

if __name__=='__main__':unittest.main()
