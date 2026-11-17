"""Offline evaluation; standard-library only; never calls a model or edits raw results."""
import argparse,csv,json,re,unicodedata,hashlib
from pathlib import Path
from collections import Counter
SCORER_VERSION = "format_type_aware_v1"
SET_TYPES={'C-009','C-099','C-101'}
VERTEX_ORDER_TYPES={'C-027','C-030'}
REGION_ORDER_TYPES={'C-093','C-098'}

def canonical(value,qid):
    text=unicodedata.normalize('NFKC',str(value)).strip()
    text=re.sub(r'^ANSWER\s*:\s*','',text,flags=re.I).strip()
    text=text.replace('**','').strip().rstrip('.').strip()
    if qid in SET_TYPES|VERTEX_ORDER_TYPES|REGION_ORDER_TYPES:
        if text.lower()=='none':return ()
        text=text.strip('[]() \t\n')
        pieces=re.split(r'\s*[,;]\s*',text)
        pattern=r'v\s*_?\s*(\d+)' if qid in VERTEX_ORDER_TYPES else r'([A-Z])'
        parsed=[]
        for piece in pieces:
            match=re.fullmatch(pattern,piece.strip(),re.I)
            if not match:return ('UNPARSED',text)
            parsed.append(match.group(1).upper())
        # Duplicate entries remain invalid rather than silently disappearing.
        if qid in SET_TYPES:return tuple(sorted(parsed))
        return tuple(parsed)
    if qid=='C-100':
        pairs=re.findall(r'\(\s*([A-Z])\s*,\s*([A-Z])\s*\)',text,re.I)
        if not pairs or re.sub(r'\(\s*[A-Z]\s*,\s*[A-Z]\s*\)|[;\s]','',text,flags=re.I):return ('UNPARSED',text)
        # Pair members unordered; sequence of contact heights remains ordered.
        return tuple(tuple(sorted((a.upper(),b.upper()))) for a,b in pairs)
    return ' '.join(text.lower().split())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-dir',required=True,type=Path)
    parser.add_argument('--dataset',type=Path,default=Path(__file__).resolve().parent/'dataset/dataset.json')
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args()
    output=args.output_dir or args.run_dir/'evaluation'/SCORER_VERSION
    if output.resolve()==args.run_dir.resolve():
        raise SystemExit('Evaluation output must be separate from raw records')
    output.mkdir(parents=True,exist_ok=True)
    data=json.loads(args.dataset.read_text());items={i['item_id']:i for i in data['items']}
    digest=hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    records=[]
    for setup_folder in ('compositional_auto','no_tools'):
        for path in sorted((args.run_dir/setup_folder).glob('*.json')):
            record=json.loads(path.read_text())
            if record.get('dataset_sha256') not in (None,digest):
                raise ValueError(f'Dataset hash mismatch: {path}')
            records.append(record)
    seen=set();rows=[]
    for record in records:
        key=(record['setup'],record['item_id'])
        if key in seen:raise ValueError(f'Duplicate episode: {key}')
        seen.add(key)
        item=items[record['item_id']];q=item['question'];answer=record.get('answer')
        # The stored extraction is a convenience, not an evaluation verdict.
        if 'answer' not in record:
            text=record.get('raw_final') or ''
            answer=next((line.split(':',1)[1].strip() for line in reversed(text.splitlines())
                         if line.strip().upper().startswith('ANSWER:')),text.strip())
        complete=record.get('status')=='completed' and not record.get('run_error')
        gold=q['answer'];qid=q['question_id']
        correct=bool(complete and answer is not None and canonical(answer,qid)==canonical(gold,qid))
        rows.append(dict(setup=record['setup'],item_id=record['item_id'],question_id=qid,
            level=item['question_complexity']['level'],status=record.get('status'),
            incomplete_reason=record.get('incomplete_reason'),answer=answer,gold=gold,
            scored_correct=correct,n_tool_calls=record.get('n_tool_calls',0),
            elapsed_s=record.get('elapsed_s'),scorer_version=SCORER_VERSION))
    with (output/'scored_episodes.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['item_id']);w.writeheader();w.writerows(rows)
    groups=[]
    for setup in sorted({r['setup'] for r in rows}):
        a=[r for r in rows if r['setup']==setup];n=len(a)
        groups.append(dict(setup=setup,recorded=n,expected=len(items),
            completed=sum(r['status']=='completed' for r in a),correct=sum(r['scored_correct'] for r in a),
            accuracy_over_recorded=sum(r['scored_correct'] for r in a)/n if n else None,
            incomplete_reasons=dict(Counter(r['incomplete_reason'] for r in a if r['status']=='incomplete')),
            used_tools=sum(r['n_tool_calls']>0 for r in a)))
    summary=dict(scorer_version=SCORER_VERSION,dataset_sha256=digest,partial_run=len(rows)!=2*len(items),groups=groups)
    (output/'evaluation_summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
    print('Evaluation saved to:',output)

if __name__=='__main__':main()
