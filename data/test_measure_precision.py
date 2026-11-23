"""Four decimals for presentation; full precision in measurement traces."""
import contextlib,importlib.util,io,re
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from test_incident_edge_count import load_functions

RAW=.123456789123
class PrecisionTests(unittest.TestCase):
    def test_survey_formatter(self):
        ns={'re':re,'answer_like_text':str,'natural_join':lambda x:', '.join(map(str,x))}
        load_functions('compositional_survey.py',{'participant_output_for_tool'},ns);f=ns['participant_output_for_tool']
        for mode in ['area','distance','angle']:
            self.assertIn('0.1235',f('measure',f'measure(A, what="{mode}")',RAW))
            self.assertIn('1.0000',f('measure',f'measure(A, what="{mode}")',1))
        s=f('measure','measure(v1, what="incident_edge_count")',3)
        self.assertNotIn('3.0000',s)
        s=f('measure','measure(H, what="area", line=L1)',{'above':RAW,'below':1-RAW})
        self.assertIn('0.1235',s);self.assertIn('0.8765',s)
    def test_batch_display_and_raw_trace(self):
        class Rerun(BaseException):pass
        calls=[];logs=[]
        ns={'T':SimpleNamespace(measure=lambda *a,**kw:[RAW]),'code_name':lambda x:'A',
            '_tool_output':lambda x:{'label':'A'},'add_program':lambda x:None,'add_log':logs.append,
            'record_tool_call':lambda *a:calls.append(a),'clear_selection':lambda:None,
            'st':SimpleNamespace(rerun=lambda:(_ for _ in ()).throw(Rerun()))}
        load_functions('compositional_survey.py',{'measurement_batch_finish'},ns)
        with self.assertRaises(Rerun):ns['measurement_batch_finish']([object()],'area')
        self.assertEqual(calls[0][3]['items'][0]['value'],RAW)
        self.assertIn('0.1235',logs[0])
    def test_model_raw_and_visible_output(self):
        spec=importlib.util.spec_from_file_location('precision_env','geo_agent/geo_env.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        with contextlib.redirect_stdout(io.StringIO()):e=m.Env(5,6100,structure_complexity='high')
        face=next(f for f in e.res_map.faces if f.bounded)
        e.select_region(face.letter)
        with patch.object(m.T,'measure',return_value=RAW):msg=e.run('measure',{'what':'area'})
        self.assertIn('0.1235',msg);self.assertEqual(e.tool_calls[-1]['output'],RAW)
        e.select_angle(face.vertices[0],face)
        with patch.object(m.T,'measure',return_value=RAW):msg=e.run('measure',{'what':'angle'})
        self.assertIn('0.1235',msg);self.assertEqual(e.tool_calls[-1]['output'],RAW)
if __name__=='__main__':unittest.main()
