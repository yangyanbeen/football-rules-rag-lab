"""Model-free evidence binding for the final business-gate regression artifacts."""
import argparse,json,hashlib,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import canonical,config,parse_selection,BOUNDARY
from disciplinary_query_policy import evaluate_suspension_query,refusal_message
from citation_catalog_guard import safe_render
from rrf import fuse
from task13_audit import validate_private,public_projection
def read(p):return json.loads(p.read_text('utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    base=ROOT/'.runtime/phase2';run=base/'d036-gate-live90-final';done=read(run/'completed.json');meta=read(run/'metadata.json');cfg=config()
    labels={v['question_id']:v for v in map(json.loads,(ROOT/'data/eval/answer_eval.jsonl').read_text('utf8').splitlines())}
    corpus={v['chunk_id']:v for v in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    counts=dict(traces=0,normal_parser_attempts=0,source_renders=0,rrf_recomputations=0,business_zero_call=0,worker_public_contracts=0)
    for qid,h in done['hashes'].items():
        path=run/(qid+'.json');assert sha(path)==h;t=read(path);r=t['result'];obs=t['observations'];q=labels[qid]['question']
        assert t['question']==q and r['question_sha256']==hashlib.sha256(q.encode()).hexdigest()
        decision=evaluate_suspension_query(q);assert r.get('business_decision')==decision
        ats=obs['model_attempts'];assert len(ats)==len(r['attempts'])==len(r['selection_audits'])==r['chat_calls']<=2
        if decision:
            assert r['status']=='refused' and r['chat_calls']==r['embedding_queries']==r['reranked_pairs']==0
            assert r['answer']==refusal_message(decision)+'\n'+BOUNDARY
            assert [v['node'] for v in r['events']]==['route','refusal','finish']
            assert obs=={'model_attempts':[]} and not r['retrieved_ids'] and not r['citations'];counts['business_zero_call']+=1
        for item,audit in zip(ats,r['selection_audits']):
            assert len(canonical(item['messages']))<=6200 and item['response']==audit['response']
            assert parse_selection(item['response']['message']['content'],r['offered_ids'],cfg)==audit['normalized_selection']
            counts['normal_parser_attempts']+=1
        if r['status']=='answered':
            assert safe_render(r['selected_ids'],corpus)==(r['answer'],r['citations']);counts['source_renders']+=1
        if obs.get('channels'):
            assert fuse(obs['channels'],60,80)['rrf']==obs['fused'];counts['rrf_recomputations']+=1
            assert len(obs['reranked'])==40
            assert [v['chunk_id'] for v in obs['reranked'][:10]]==r['retrieved_ids']
            assert obs['evidence']==[corpus[c] for c in r['retrieved_ids']]
        counts['traces']+=1
    assert counts['traces']==90 and counts['business_zero_call']==1
    for item in read(base/'d036-gate-live-worker-v2.json'):
        ref=item['private_trace'];path=ROOT/ref['path'];assert sha(path)==ref['sha256']
        r=read(path);validate_private(r,r['question'],True);public_projection(r,path);counts['worker_public_contracts']+=1
    for name,ref in meta['source_files'].items():assert sha(ROOT/name)==ref['sha256']
    assert (ROOT/'scripts/answer_eval_engine.py').read_bytes()==subprocess.check_output(['git','show','6e9f6f0:scripts/answer_eval_engine.py'],cwd=ROOT)
    for name,ref in read(ROOT/'optimization/baseline/e8b0fd6/freeze.json')['data'].items():assert sha(ROOT/name)==ref['sha256']
    for ref in read(ROOT/'optimization/datasets/freeze_manifest.json')['files']:assert sha(ROOT/'optimization'/ref['path'])==ref['sha256']
    runtime_changes=subprocess.check_output(['git','diff','--name-only','6e9f6f0','HEAD','--','scripts','config'],cwd=ROOT,text=True).splitlines()
    allowed={'scripts/disciplinary_query_policy.py','scripts/rag_langgraph.py','scripts/task13_engine.py','scripts/task13_core.py','scripts/task13_audit.py','scripts/task13_query_rewrite.py','scripts/run_langgraph_flow.py'}
    assert set(runtime_changes)==allowed,runtime_changes
    value=dict(status='PASS',checks=counts,formal_raw_hashes_verified=90,model_requests_in_verification=0,
               source_prompt_data_indexes_and_holdout_verified=True,A1_packing_restored=True,
               runtime_changes=runtime_changes,formal_run_commit=meta['source_commit'],
               quality_scope='Evidence verification only; quality acceptance comes from independent scored metrics.')
    with a.out.open('xb') as f:f.write(canonical(value))
    print(json.dumps(value,ensure_ascii=False))
if __name__=='__main__':main()
