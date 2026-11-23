"""Incident edge count: shared geometry, model dispatch and survey handlers."""
import ast
import contextlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import Graph
import map_helpers as engine
import tools_human as tools
from test_merge_multiple_regions import grid

ROOT=Path(__file__).resolve().parent

def load_functions(file,names,namespace=None):
    namespace={} if namespace is None else namespace
    nodes=[n for n in ast.parse(Path(file).read_text()).body
           if isinstance(n,ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(file),'exec'),namespace)
    return namespace

class IncidentCountTests(unittest.TestCase):
    def test_corner_frame_junction_and_interior(self):
        faces=grid(2,2)
        vertices={(v.p.x,v.p.y):v for f in faces for v in f.vertices}
        self.assertEqual(tools.measure(vertices[0,0],what='incident_edge_count'),2)
        self.assertEqual(tools.measure(vertices[1,0],what='incident_edge_count'),3)
        self.assertEqual(tools.measure(vertices[1,1],what='incident_edge_count'),4)
        self.assertEqual(tools.measure(faces[0],what='edge_count'),4)

    def test_half_edge_reverse_and_duplicates_count_once(self):
        face=grid(1,1)[0];v=face.vertices[0];original=list(v.outarcs)
        v.outarcs.extend(original+[e.reverse for e in original])
        self.assertEqual(engine.incident_edge_count(v),2)

    def test_union_hides_internal_edges_without_changing_original_count(self):
        a,b=grid(2,1);v=next(v for v in a.vertices if v.p.x==1 and v.p.y==0)
        merged=tools.merge(a,b)
        self.assertEqual(tools.measure(v,what='incident_edge_count'),3)
        self.assertEqual(tools.measure(v,what='incident_edge_count',merged_regions=[merged]),2)
        self.assertEqual(tools.measure(v,what='incident_edge_count'),3)

    def test_centers_regions_and_multiple_points_rejected(self):
        face=grid(1,1)[0];c=tools.find(face,object='centroid')
        for args in [(c,),(face,),('frame',),(face.vertices[0],face.vertices[1])]:
            with self.assertRaises(ValueError):tools.measure(*args,what='incident_edge_count')

    def test_model_dispatch_schema_and_numeric_trace(self):
        spec=importlib.util.spec_from_file_location('incident_env',ROOT/'geo_agent/geo_env.py')
        envmodule=importlib.util.module_from_spec(spec);spec.loader.exec_module(envmodule)
        ns=load_functions(ROOT/'geo_agent/geo_agent.py',{'dispatch','_vertex_by_name','_edge_by_name','_line_by_name'})
        with contextlib.redirect_stdout(io.StringIO()):env=envmodule.Env(5,6100,structure_complexity='high')
        v=min(env.res_map.vertices,key=lambda v:(v.p.x,v.p.y));label=env.point_name(v)
        expected=engine.incident_edge_count(v)
        msg=ns['dispatch'](env,'measure',{'what':'incident_edge_count','vertices':[label]})
        self.assertIn(str(expected),msg);self.assertIn('incident',msg)
        self.assertEqual(env.tool_calls[-1]['tool'],'measure');self.assertEqual(env.tool_calls[-1]['output_text'],str(expected))
        self.assertFalse(env.selection)
        env.undo();self.assertFalse(env.tool_calls)
        with self.assertRaises(ValueError):ns['dispatch'](env,'measure',{'what':'incident_edge_count','vertices':[label,label]})
        tree=ast.parse((ROOT/'geo_agent/geo_agent.py').read_text())
        schemas=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='TOOLS' for t in n.targets)))
        measure=next(s['function'] for s in schemas if s['function']['name']=='measure')
        self.assertIn('incident_edge_count',measure['parameters']['properties']['what']['enum'])

    def test_human_validation_execution_and_trace(self):
        class State(dict):
            __getattr__=dict.__getitem__
            __setattr__=dict.__setitem__
        class Rerun(BaseException):pass
        def rerun():raise Rerun()
        face=grid(1,1)[0];v=face.vertices[0]
        state=State(selection=[v],unions=[])
        outputs=[]
        ns={'st':SimpleNamespace(session_state=state),'T':tools,'IS_PRACTICE':False}
        load_functions(ROOT/'compositional_survey.py',{'validate','sel_sig','is_vertex','is_region','is_angle','is_edgesel','run_tool'},ns)
        def finish(tool,call,value,**kw):
            outputs.append((tool,call,value));state.selection=[];rerun()
        ns.update(finish=finish,code_name=lambda v:'v1')
        self.assertTrue(ns['validate']('measure',{'what':'incident_edge_count'})[0])
        with self.assertRaises(Rerun):ns['run_tool']('measure',{'what':'incident_edge_count'})
        self.assertEqual(outputs,[('measure','measure(v1, what="incident_edge_count")',2)])
        state.selection=[tools.find(face,object='centroid')]
        self.assertFalse(ns['validate']('measure',{'what':'incident_edge_count'})[0])

if __name__=='__main__':unittest.main()
