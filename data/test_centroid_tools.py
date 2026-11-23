"""Centroid geometry and shared human/model tool contract."""
import ast
import contextlib
import importlib.util
import io
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import Graph
import map_helpers as engine
import tools_human as tools

ROOT=Path(__file__).resolve().parent

def polygon(coords, label='A'):
    points=[SimpleNamespace(p=Graph.Vector(x,y)) for x,y in coords]
    return SimpleNamespace(vertices=points+[points[0]],bounded=True,letter=label,edges=[])

class CentroidTests(unittest.TestCase):
    def assertPoint(self,p,x,y):
        self.assertAlmostEqual(p.p.x,x);self.assertAlmostEqual(p.p.y,y)

    def test_area_weighted_not_vertex_mean_and_winding_independent(self):
        points=[(0,0),(2,0),(2,1),(1,1),(1,2),(0,2)]
        for ring in (points,list(reversed(points))):
            self.assertPoint(tools.find(polygon(ring),object='centroid'),5/6,5/6)

    def test_subdivided_edges_do_not_change_centroid(self):
        self.assertPoint(engine.centroid(polygon([(0,0),(1,0),(4,0),(4,2),(0,2)])),2,1)
        self.assertPoint(engine.centroid(polygon([(0,0),(4,0),(0,2)])),4/3,2/3)

    def test_invalid_inputs(self):
        for ring in [[(0,0),(1,0),(2,0)],[(0,0),(1,0),(math.inf,1)]]:
            with self.assertRaises(ValueError):engine.centroid(polygon(ring))
        with self.assertRaises(ValueError):tools.find('frame',object='centroid')
        with self.assertRaises(ValueError):tools.find(object='centroid')

    def test_batch_distance_sort_draw_orientation_and_no_angle(self):
        regions=[polygon([(x,y),(x+1,y),(x+1,y+1),(x,y+1)],label)
                 for x,y,label in [(0,0,'A'),(2,0,'B'),(0,2,'C')]]
        a,b,c=tools.find(*regions,object='centroid')
        self.assertEqual(tools.measure(a,b,what='distance'),2)
        self.assertEqual(tools.measure(a,b,c,what='orientation'),'Counterclockwise')
        self.assertEqual(tools.sort([b,a],by='left_right'),[a,b])
        self.assertEqual(tools.measure(tools.draw(a,b),what='distance'),2)
        self.assertEqual(tools.draw(a,'right')['type'],'ray')
        with self.assertRaises(ValueError):tools.measure(a,regions[0],what='angle')

    def test_merged_region_and_no_topology_change(self):
        from test_merge_multiple_regions import grid
        a,b,c=grid(3,1)
        before=[len(v.outarcs) for f in (a,b,c) for v in f.vertices]
        union=tools.merge(a,b,c)
        self.assertPoint(tools.find(union,object='centroid'),1.5,.5)
        self.assertEqual(before,[len(v.outarcs) for f in (a,b,c) for v in f.vertices])

    def test_real_model_dispatch_and_undo(self):
        def module(name,file):
            spec=importlib.util.spec_from_file_location(name,file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
        envmod=module('centroid_env',ROOT/'geo_agent/geo_env.py')
        tree=ast.parse((ROOT/'geo_agent/geo_agent.py').read_text())
        ns={}
        exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('dispatch','_vertex_by_name','_edge_by_name','_line_by_name')],type_ignores=[]),'agent_dispatch','exec'),ns)
        agent=SimpleNamespace(**ns)
        with contextlib.redirect_stdout(io.StringIO()):env=envmod.Env(5,6100,structure_complexity='high')
        before=(len(env.res_map.vertices),len(env.res_map.edges))
        msg=agent.dispatch(env,'find',{'objs':['A','B'],'object':'centroid'})
        self.assertIn('c1 as the centroid of Region A',msg)
        self.assertIn('c2 as the centroid of Region B',msg)
        self.assertEqual(env.tool_calls[-1]['tool'],'find')
        a=agent._vertex_by_name(env,'c1');b=agent._vertex_by_name(env,'c2')
        self.assertTrue(agent.dispatch(env,'measure',{'what':'distance','vertices':['c1','c2']}))
        self.assertNotIn('error',env.tool_calls[-1])
        self.assertEqual(agent._vertex_by_name(env,'c1'),a)
        env.clear_selection();env.select_region('A');self.assertIn('c1',env.run('centroid',{}))
        self.assertEqual(len([x for x in env.annotations if getattr(x.get('obj'),'point_kind',None)=='centroid']),2)
        self.assertEqual(before,(len(env.res_map.vertices),len(env.res_map.edges)))
        env.render()
        env.clear_all()
        with self.assertRaises(ValueError):agent._vertex_by_name(env,'c1')

    def test_human_handlers_retain_points_and_log_geometry(self):
        source=(ROOT/'compositional_survey.py').read_text();tree=ast.parse(source)
        names={'is_vertex','is_region','is_angle','is_edgesel','sel_sig','next_name','point_name','point_name_with_meta','code_name','finish_vertex','run_tool','_point_coordinates','_vertex_geometry','_tool_output','validate'}
        funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
        class State(dict):
            __getattr__=dict.__getitem__
            __setattr__=dict.__setitem__
        state=State(selection=[],selection_meta=[],annotations=[],point_names={},counters={},angles=[],named_edges=[])
        class Rerun(BaseException):pass
        def rerun():raise Rerun()
        recorded=[]
        ns={'st':SimpleNamespace(session_state=state,rerun=rerun),'T':tools,'Graph':Graph,'IS_PRACTICE':False,
            'add_to_selection':lambda obj,meta:(state.selection.append(obj),state.selection_meta.append(meta)),
            'add_program':Mock(),'add_log':Mock(),'answer_like_text':lambda r:'centroid',
            'participant_output_for_tool':lambda *a:'centroid found',
            'record_tool_call':lambda *a:recorded.append(a)}
        exec(compile(ast.Module(body=funcs,type_ignores=[]),'survey_handlers','exec'),ns)
        region=polygon([(0,0),(2,0),(2,2),(0,2)])
        # Region protocol requires edges as in real Graph faces.
        region.edges=[]
        state.selection=[region];state.selection_meta=[None]
        self.assertTrue(ns['validate']('find',{'object':'centroid'})[0])
        with self.assertRaises(Rerun):ns['run_tool']('find',{'object':'centroid'})
        self.assertEqual(ns['code_name'](state.selection[0]),'c1')
        output=recorded[0][3]
        self.assertEqual(output['point_kind'],'centroid');self.assertEqual(output['source_region'],'A')
        self.assertEqual(output['coordinates'],[1.,1.])

if __name__=='__main__':unittest.main()
