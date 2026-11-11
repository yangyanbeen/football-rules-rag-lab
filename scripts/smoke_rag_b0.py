"""Ad hoc end-to-end smoke; never reads development/test questions or labels."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from rag_b0 import ROOT, RagB0Engine, digest

QUESTIONS=[
    ('boundary','足球场的边界线属于场内还是场外？','answered'),
    ('goal','球门两根门柱之间的距离和横梁高度各是多少？','answered'),
    ('throw_in','队员掷界外球时双脚和双手应满足什么要求？','answered'),
    ('outside','火星明天的天气怎么样？','refused'),
]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'reports/rag_b0_smoke.jsonl')
    parser.add_argument('--summary',type=Path,default=ROOT/'reports/evidence/rag_b0_smoke_manifest.json')
    args=parser.parse_args()
    output=args.output.resolve();summary=args.summary.resolve()
    if (output!=ROOT/'reports/rag_b0_smoke.jsonl' and not output.is_relative_to(ROOT/'.runtime/rag-b0')):
        raise ValueError('Full answers must remain in the ignored smoke/runtime path')
    if output.exists() or summary.exists():raise ValueError('Use new output paths; never overwrite prior smoke evidence')
    rows=[];engine=RagB0Engine()
    output.parent.mkdir(parents=True,exist_ok=True)
    try:
        with output.open('x',encoding='utf-8') as handle:
            for key,question,expected in QUESTIONS:
                row=engine.answer(question);row.update(smoke_id=key,expected_status=expected)
                handle.write(json.dumps(row,ensure_ascii=False)+'\n');handle.flush()
                rows.append(row)
                print(json.dumps({'smoke_id':key,'status':row['status'],'expected':expected,
                    'citations':[c['chunk_id'] for c in row['citations']],'error':row.get('error'),
                    'seconds':row['timing']['total_seconds']},ensure_ascii=False),flush=True)
    finally:engine.close()
    public={'captured_at':datetime.now(timezone.utc).isoformat(),'kind':'ad_hoc_chain_smoke_not_accuracy',
        'raw_path':str(output.relative_to(ROOT)).replace('\\','/'),'raw_sha256':digest(output.read_bytes()),
        'raw_public':False,'formal_eval_questions_read':False,
        'status':'PASS' if all(r['status']==r['expected_status'] for r in rows) else 'FAIL',
        'rows':[]}
    for r in rows:
        public['rows'].append({k:r[k] for k in ('smoke_id','trace_id','question','status','expected_status',
            'config_sha256','prompt_version','prompt_sha256','index_manifest_sha256','generation_attempted','timing')})
        public['rows'][-1].update(answer_sha256=digest(r['answer'].encode('utf-8')),
            retrieved_ids=[m['chunk_id'] for m in r['retrieval']['results']] if r['retrieval'] else [],
            context_ids=[m['chunk_id'] for m in r['context']],
            prompt_utf8_bytes=r.get('prompt_utf8_bytes'),
            generation_attempt_count=len(r.get('attempts',[])),
            attempts=[{'attempt':a['attempt'],'validation_error':a['validation_error'],
                'prompt_eval_count':(a['generation'] or {}).get('prompt_eval_count'),
                'eval_count':(a['generation'] or {}).get('eval_count'),
                'generation_seconds':a['generation_seconds']} for a in r.get('attempts',[])],
            citations=[{k:c[k] for k in ('chunk_id','source_url','law_number','source_lines','content_zh_sha256',
                'needs_rule_review','source_revision_verified','expert_reviewed','official_translation')} for c in r['citations']],
            generation={k:v for k,v in (r['generation'] or {}).items() if k in
                ('model','done','done_reason','prompt_eval_count','eval_count','load_duration','total_duration','model_digest')},
            error=r.get('error'))
    summary.parent.mkdir(parents=True,exist_ok=True)
    summary.write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if public['status']=='PASS' else 1)


if __name__=='__main__':main()
