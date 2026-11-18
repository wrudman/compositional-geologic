"""Read-only audit of parsed API responses, executed traces and saved history.
Server responses are already parsed: absence of markup here cannot rule out a
vLLM parser/tokenizer issue before the API response was constructed.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def audit(run_dir):
    counts=Counter();issues=[];markup=[];failures=[]
    for setup in ('compositional_auto','no_tools'):
        for path in sorted((run_dir/setup).glob('*.json')):
            d=json.loads(path.read_text());counts[setup+'_episodes']+=1
            calls=[]
            for r in d['requests']:
                counts[setup+'_requests']+=1
                message=r['raw_response']['choices'][0]['message']
                calls.extend(message.get('tool_calls') or [])
                text=json.dumps(r.get('reasoning_fields',{}),ensure_ascii=False)+'\n'+str(message.get('content') or '')
                for marker in ('<tool_call>','<function=','<|tool_call|>'):
                    if marker in text:markup.append({'item_id':d['item_id'],'setup':setup,'turn':r['turn'],'marker':marker})
            counts[setup+'_parsed_tool_calls']+=len(calls)
            assistant_calls=[c for m in d['messages'] if m['role']=='assistant' for c in m.get('tool_calls',[])]
            outputs=[m for m in d['messages'] if m['role']=='tool']
            try:
                assert len(calls)==len(d['trace'])==len(outputs)
                assert [c['id'] for c in calls]==[c['id'] for c in assistant_calls]==[m['tool_call_id'] for m in outputs]
                for c,t,out in zip(calls,d['trace'],outputs):
                    assert c['function']['name']==t['tool']
                    assert json.loads(c['function']['arguments'])==t['args']
                    assert out['content']==t['output']
            except (AssertionError,ValueError,KeyError) as e:
                issues.append({'item_id':d['item_id'],'setup':setup,'issue':repr(e)})
            for t in d['trace']:
                if 'could not be completed' in t['output'].lower():
                    failures.append({'item_id':d['item_id'],'tool':t['tool'],'output':t['output']})
            if d['status']=='incomplete' and not calls:
                counts[setup+'_incomplete_without_any_call']+=1
    return {'scope':'Saved parsed responses/history; not a live GPU/parser/template test',
            'counts':dict(counts),'trace_or_history_mismatches':issues,
            'tool_markup_in_returned_text':markup,'dispatch_failure_feedback':failures,
            'server_tokenizer_chat_template_verified':False,
            'live_tool_calling_diagnostic_performed':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',type=Path,default=ROOT/'runs/raw_32768_v2')
    p.add_argument('--output',type=Path,default=ROOT/'analysis_32768/tool_calling_audit.json')
    a=p.parse_args();result=audit(a.run_dir)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(result,indent=2,ensure_ascii=False))
