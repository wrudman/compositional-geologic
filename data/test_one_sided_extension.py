import contextlib,importlib.util,io,math,unittest
from types import SimpleNamespace
import Graph,map_helpers as m,tools_human as t
from test_incident_edge_count import load_functions
class ExtensionTests(unittest.TestCase):
 def test_directions_and_reversed_endpoints(self):
  m._MAP=SimpleNamespace(bounds=[1,1])
  p=lambda x,y:SimpleNamespace(p=Graph.Vector(x,y))
  for a,b,d,target in [(p(.2,.3),p(.6,.5),'right',(1,.7)),(p(.2,.3),p(.6,.5),'left',(0,.2)),(p(.5,.2),p(.5,.6),'up',(.5,1)),(p(.2,.5),p(.6,.5),'right',(1,.5)),(p(.5,.2),p(.5,.6),'down',(.5,0))]:
   for x,y in [(a,b),(b,a)]:
    l=t.draw(x,y,extension_direction=d)
    self.assertEqual(l['type'],'segment');self.assertAlmostEqual(l['b'].x,target[0]);self.assertAlmostEqual(l['b'].y,target[1])
    self.assertAlmostEqual(t.measure(l,what='extension')[d],math.hypot(l['extension_part'][0].x-target[0],l['extension_part'][0].y-target[1]))
    self.assertAlmostEqual(t.measure(l,what='extension')['original_edge'],math.hypot(a.p.x-b.p.x,a.p.y-b.p.y))
  with self.assertRaises(ValueError):t.draw(p(.5,.2),p(.5,.6),extension_direction='right')
  with self.assertRaises(ValueError):t.draw(p(.5,.5),p(1,.5),extension_direction='right')
 def test_legacy_lines_remain_available(self):
  a=SimpleNamespace(p=Graph.Vector(.2,.5));b=SimpleNamespace(p=Graph.Vector(.6,.5))
  edge=object()
  ns={'math':math,'edgesel_endpoints':lambda e:(a,b)}
  load_functions('compositional_survey.py',{'available_edge_extensions'},ns)
  old_full={'type':'extend','a':a.p,'b':b.p}
  old_one={'type':'segment','a':b.p,'b':Graph.Vector(1,.5),'extension_direction':'right','source_edge_endpoints':(a.p,b.p)}
  entries=ns['available_edge_extensions']([('L1',old_full),('L2',old_one)],[('e1',edge)])
  self.assertEqual([x[0] for x in entries],['L1','L2'])
  self.assertEqual(old_full['source_edge_label'],'e1')
  self.assertEqual(old_one['extension_part'][0],b.p)
  self.assertEqual(old_one['a'],a.p)
 def test_dominant_axis_and_wording_override(self):
  from extension_directions import preferred_extension_axis
  self.assertEqual(preferred_extension_axis((0,0),(.1,.8)),'y')
  self.assertEqual(preferred_extension_axis((0,0),(.8,.1)),'x')
  self.assertEqual(preferred_extension_axis((0,0),(.1,.8),'right'),'x')
  m._MAP=SimpleNamespace(bounds=[1,1])
  a=SimpleNamespace(p=Graph.Vector(.4,.4));b=SimpleNamespace(p=Graph.Vector(.5,.6))
  line=t.draw(a,b,kind='full');line['source_edge_endpoints']=(a.p,b.p)
  self.assertEqual(set(t.measure(line,what='extension')),{'original_edge','up','down'})
  line['question_extension_direction']='right'
  self.assertEqual(set(t.measure(line,what='extension')),{'original_edge','left','right'})
 def test_both_directions(self):
  m._MAP=SimpleNamespace(bounds=[1,1])
  a=SimpleNamespace(p=Graph.Vector(.2,.5));b=SimpleNamespace(p=Graph.Vector(.6,.5))
  line=t.draw(a,b,kind='full');line['source_edge_endpoints']=(a.p,b.p)
  result=t.measure(line,what='extension')
  self.assertAlmostEqual(result['original_edge'],.4)
  self.assertAlmostEqual(result['left'],.2);self.assertAlmostEqual(result['right'],.4)
 def test_model_draw_and_measure(self):
  spec=importlib.util.spec_from_file_location('extension_env','geo_agent/geo_env.py');envmod=importlib.util.module_from_spec(spec);spec.loader.exec_module(envmod)
  with contextlib.redirect_stdout(io.StringIO()):env=envmod.Env(5,6100,structure_complexity='high')
  edge=next(e for e in env.res_map.edges if abs(e.head.p.x-e.tail.p.x)>1e-9 and max(e.head.p.x,e.tail.p.x)<.999)
  from sel_types import EdgeSel
  env.select_edge(EdgeSel([edge],None,'example'))
  msg=env.run('draw line',{'style':'full line','extension_direction':'right'})
  self.assertIn('Extended edge',msg);self.assertEqual(env.lines[-1][1]['type'],'segment')
  ns=load_functions('geo_agent/geo_agent.py',{'dispatch','_line_by_name'})
  msg=ns['dispatch'](env,'measure',{'what':'extension','line':env.lines[-1][0]})
  self.assertNotIn('could not',msg);self.assertNotIn('error',env.tool_calls[-1])
if __name__=='__main__':unittest.main()
