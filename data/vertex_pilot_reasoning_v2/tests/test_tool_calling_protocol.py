"""Offline protocol tests of actual agent-loop functions, with a mock server/env.
Does not test GPU generation, tokenizer templates, or vLLM parser internals.
"""
import ast
import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

SOURCE = Path(__file__).resolve().parents[1]/'agent/geo_agent.py'
FUNCTIONS = {'_request_kwargs', '_strip_old_images', '_request_record', '_episode_metadata', 'run_episode', '_extract_answer'}

def response(calls=None, content=None, finish='stop', reasoning=''):
    return NS(choices=[NS(message=NS(content=content, tool_calls=calls, reasoning=reasoning), finish_reason=finish)], usage={'completion_tokens': 5, 'prompt_tokens': 7, 'total_tokens': 12})

def call(name, args, identifier):
    return NS(id=identifier, function=NS(name=name, arguments=json.dumps(args)))

class Client:
    def __init__(self, responses):
        self.responses=iter(responses); self.sent=[]
        self.chat=NS(completions=NS(create=self.create))
    def create(self, **kwargs):
        self.sent.append(copy.deepcopy(kwargs)); return next(self.responses)

class Env:
    def render(self): return 'fake-diagram'

class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.executed=[]
        self.ns={'copy':copy,'json':json,'MODEL':'test-model','TOOLS':[{'type':'function','function':{'name':'neighbors','parameters':{'type':'object'}}}],
                 '_SYSTEM_PROMPTS':{'auto':'optional','none':'no tools','required':'required'}, 'TOOL_MODES':('auto','none','required'),
                 'EXTRA_BODY':{},'SAMPLING':{'max_tokens':32768},'_image_content':lambda img:{'type':'image_url','image_url':{'url':'data:fake'}},
                 'dispatch':self.dispatch}
        nodes=[n for n in ast.parse(SOURCE.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in FUNCTIONS]
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),'exec'),self.ns)
    def dispatch(self, env, name, args):
        self.executed.append((name,args)); return 'feedback-'+name
    def run_agent(self, client, **kwargs):
        return self.ns['run_episode'](Env(),'question',client=client,verbose=0,show_images=False,**kwargs)
    def test_parallel_calls_and_history(self):
        calls=[call('neighbors',{'obj':'P'},'one'),call('find',{'objs':['E','P']},'two')]
        client=Client([response(calls,finish='tool_calls'),response(content='ANSWER: E')])
        result=self.run_agent(client,max_turns=2)
        self.assertEqual(len(result['trace']),2)
        self.assertEqual(client.sent[0]['tool_choice'],'auto')
        self.assertEqual(client.sent[0]['tools'],self.ns['TOOLS'])
        history=client.sent[1]['messages']
        assistant=next(m for m in history if m['role']=='assistant')
        tools=[m for m in history if m['role']=='tool']
        self.assertEqual([c['id'] for c in assistant['tool_calls']],['one','two'])
        self.assertEqual([m['tool_call_id'] for m in tools],['one','two'])
        self.assertEqual([m['content'] for m in tools],['feedback-neighbors','feedback-find'])
        self.assertEqual(sum(b.get('type')=='image_url' for m in history if isinstance(m.get('content'),list) for b in m['content']),1)
    def test_forced_final_request(self):
        client=Client([response([call('neighbors',{'obj':'P'},'one')],finish='tool_calls'),response(content='ANSWER: E')])
        result=self.run_agent(client,max_turns=1)
        self.assertEqual(client.sent[1]['tool_choice'],'none')
        self.assertEqual(result['answer'],'E')
        self.assertEqual(result['requests'][-1]['phase'],'forced_final')
    def test_no_tools_and_thinking_off(self):
        client=Client([response(content='ANSWER: E')]); self.run_agent(client,tool_mode='none',thinking=False)
        self.assertNotIn('tools',client.sent[0]);self.assertNotIn('tool_choice',client.sent[0])
        self.assertFalse(client.sent[0]['extra_body']['chat_template_kwargs']['enable_thinking'])
    def test_reasoning_text_is_not_executed_as_a_call(self):
        client=Client([response(finish='length',reasoning='Let us call neighbors(P).')])
        result=self.run_agent(client)
        self.assertEqual(self.executed,[])
        self.assertEqual(result['incomplete_reason'],'token_limit')
        self.assertEqual(result['requests'][0]['reasoning_fields']['reasoning'],'Let us call neighbors(P).')

if __name__=='__main__':unittest.main()
