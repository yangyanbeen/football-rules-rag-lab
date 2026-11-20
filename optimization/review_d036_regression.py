"""Prepare source-review ledger for gate regression, reusing reviewed paragraph sets."""
import argparse,csv,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text('utf8'))
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--ledger',type=Path,required=True);p.add_argument('--queue',type=Path,required=True);a=p.parse_args()
    prior=ROOT/'optimization/experiments/E5_A_candidate_window/source_reviews.tsv'
    rows={}
    by_set={}
    for line in csv.reader(prior.open(encoding='utf8'),delimiter='\t'):
        key,grade,bits,ids,note=line;rows[key]=line
        qid,cids=key.split('|',1);by_set[(qid,frozenset(cids.split(',')))]=(grade,bits,ids,note)
    for item in read(ROOT/'optimization/baseline/e8b0fd6/quality_labels.json')+read(ROOT/'optimization/reports/phase2_E4_metrics.json')['metrics']['live']['cases']:
        ids=item.get('selected_ids',[])
        if ids:
            by_set[(item['question_id'],frozenset(ids))]=(item['grade'],''.join(str(int(x)) for x in item['point_mask']),','.join(item['supported_citation_ids']) or '-',item['note'])
    if a.ledger.exists():
        for line in csv.reader(a.ledger.open(encoding='utf8'),delimiter='\t'):
            if line:rows[line[0]]=line
    labels={q['question_id']:q for q in map(json.loads,(ROOT/'data/eval/answer_eval.jsonl').read_text('utf8').splitlines())}
    corpus={q['chunk_id']:q for q in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    queue=[];count=0
    for path in sorted(a.run.glob('[DT][0-9][0-9][0-9].json')):
        t=read(path);r=t['result'];qid=t['question_id'];count+=1
        if r['status']!='answered':continue
        key=qid+'|'+','.join(r['selected_ids'])
        if key in rows:continue
        known=by_set.get((qid,frozenset(r['selected_ids'])))
        if known:
            grade,bits,ids,note=known
            rows[key]=[key,grade,bits,ids,'Reuse prior source review for identical question and paragraph set; order may differ. '+note]
        else:
            queue.append(dict(key=key,question=labels[qid]['question'],points=labels[qid]['expected_answer_points'],
                              sources=[dict(chunk_id=cid,content_zh=corpus[cid]['content_zh']) for cid in r['selected_ids']]))
    a.ledger.parent.mkdir(parents=True,exist_ok=True)
    a.ledger.write_bytes(('\n'.join('\t'.join(v) for v in rows.values())+'\n').encode())
    a.queue.write_bytes((json.dumps(queue,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(dict(completed=count,pending_source_reviews=len(queue),queue=queue),ensure_ascii=False))
if __name__=='__main__':main()
