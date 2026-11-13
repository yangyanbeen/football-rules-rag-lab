"""Materialize complete budgeted parent evidence locally; public receipts omit bodies."""
import argparse,json,subprocess
from pathlib import Path
from eval_dataset import ROOT,canonical,digest,load_jsonl
from bm25_index import record,write_new,committed
from bm25_retrieval_eval import now,producer_before
from structure_aware_chunking import DATA,MAP
from structure_retrieval_eval import mapping,contexts,budget_contexts,context_entry,fuse


def materialize(packet):
    m=mapping()
    if record(ROOT/DATA)!=m['derived_corpus']:raise ValueError('Derived body store differs')
    expected=fuse(packet['channels']['child'],m['children'])
    if canonical(expected)!=canonical(packet['rankings']['child']):raise ValueError('Child seed ranking differs')
    selection=budget_contexts(contexts([r['chunk_id'] for r in expected],'parent_child',m),m)
    bodies={r['chunk_id']:r for r in load_jsonl(ROOT/DATA)};results=[]
    for i,hit in enumerate(selection['contexts'],1):
        cid=hit['context_id'];body=bodies[cid];metadata=context_entry(cid,m)
        if body['kind']!='parent' or body['content_sha256']!=digest(body['content_zh'].encode()) or body['content_sha256']!=metadata['content_sha256']:raise ValueError('Actual parent body checksum differs')
        if any(body[k]!=metadata[k] for k in metadata):raise ValueError('Actual parent metadata differs')
        expected_sources=[m['originals'][cid]['source'] for cid in metadata['original_ids']]
        if body['sources']!=expected_sources:raise ValueError('Actual per-member parent source differs')
        results.append({'rank':i,**hit,'section_path':body['section_path'],'content_zh':body['content_zh'],
                        'content_sha256':body['content_sha256'],'original_ids':metadata['original_ids'],
                        'source_refs':body['sources'],'context_tokens':metadata['context_tokens']})
    return {'results':results,'context_tokens':selection['context_tokens'],'skipped_ids':selection['skipped_ids']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--question');p.add_argument('--replay-packet',type=Path)
    p.add_argument('--private-output',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
    from run_structure_comparison import output_path
    receipt=output_path(a.receipt);private=a.private_output.resolve()
    if not private.is_relative_to(ROOT/'.runtime/task11') or private.exists() or private.suffix!='.json':raise ValueError('Use a new private .runtime/task11 JSON')
    source=committed(('scripts/query_parent_child.py',MAP));start=now();input_ref=None
    if a.replay_packet:
        stored=json.loads(a.replay_packet.read_text('utf-8'));packet=stored['packet'];input_ref=record(a.replay_packet)
        if stored.get('is_quality_evaluation') is not False or stored.get('actual_embedding_queries')!=1:raise ValueError('Replay an actual non-evaluation query receipt')
        requests=0
    else:
        from structure_retrieval_live import Retriever
        from dense_retrieval_eval import normalize_query
        normalize_query(a.question)
        with Retriever() as engine:packet=engine.query(a.question,'ad-hoc')
        requests=1
    evidence=materialize(packet);write_new(private,evidence)
    checks={'at_least_one_real_parent_materialized':len(evidence['results'])>0,
            'actual_parent_bodies_and_member_sources_match':True,
            'parent_ids_unique':len({r['context_id'] for r in evidence['results']})==len(evidence['results']),
            'all_context_tokens_within4096':evidence['context_tokens']<=4096,
            'private_output_not_tracked':subprocess.run(['git','check-ignore','--quiet',str(private)],cwd=ROOT).returncode==0}
    safe=[{k:v for k,v in row.items() if k!='content_zh'} for row in evidence['results']]
    report={'version':'task11-actual-parent-context-1.0','started_at':start,'completed_at':now(),'source_commit':source,
            'source_sha256':record(__file__)['sha256'],'input_query_receipt':input_ref,'private_output':record(private),
            'results_without_bodies':safe,'context_tokens':evidence['context_tokens'],'skipped_ids':evidence['skipped_ids'],
            'actual_new_embedding_queries':requests,'answer_llm_requests':0,'scope':'Actual local parent body lookup from new query or recorded non-evaluation seed; replay is not new model inference.',
            'checks':checks,'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks)}
    write_new(receipt,report);print(json.dumps({k:report[k] for k in ('status','passed','total','actual_new_embedding_queries')}))


if __name__=='__main__':main()
