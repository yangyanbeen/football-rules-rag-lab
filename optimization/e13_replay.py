"""Frozen-response recovery/boundary audit: no live model requests."""
import argparse,copy,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import canonical,config,parse_selection,read,record,digest
from answer_eval_engine import pack
from source_bound_facts import evaluate
from citation_catalog_guard import safe_render

def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
def main(out):
    corpus={r['chunk_id']:r for r in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    registry=read(ROOT/'config/source_bound_facts.json');cfg=config();prompt=(ROOT/cfg['prompt_file']).read_text('utf8')
    refused=dict(answerable=False,chunk_ids=[],reason='insufficient_evidence')
    plan=read(ROOT/'optimization/experiments/E13_source_facts/plan.json')
    rows=[]
    def check(name,q,context,messages,expected,selection=None,policy=None):
        d=evaluate(q,selection or refused,context,messages,registry=policy)
        assert d['applied'] is expected,(name,d)
        if d['applied']:
            answer,cites=safe_render(d['selected_ids'],corpus)
            assert [c['chunk_id'] for c in cites]==d['selected_ids'] and answer
        rows.append(dict(name=name,question=q,expected_apply=expected,decision=d,passed=True))
    for case in plan['pressure_questions']:
        source='L01-01' if case['name'].startswith('grass') else 'L02-02' if case['name'].startswith('pressure') else 'L01-03'
        context,messages,_=pack(case['question'],[corpus[source]],cfg,prompt)
        check(case['name'],case['question'],context,messages,True)
    for case in plan['boundary_controls']:
        context,messages,_=pack(case['question'],[corpus[c] for c in ('L01-01','L01-03','L02-02')],cfg,prompt)
        check(case['name'],case['question'],context,messages,False)
    q='人工草坪的颜色有什么限制？';c,m,_=pack(q,[corpus['L01-01'],corpus['L01-03']],cfg,prompt)
    check('only_retrieved_not_prompt',q,c[1:],pack(q,c[1:],cfg,prompt)[1],False)
    check('prompt_context_mismatch',q,c,messages=pack(q,c[1:],cfg,prompt)[1],expected=False)
    altered=copy.deepcopy(c);altered[0]['content_zh']=altered[0]['content_zh'].replace('绿色','红色')
    changed=copy.deepcopy(m);payload=json.loads(changed[1]['content']);payload['evidence'][0]['content_zh']=altered[0]['content_zh'];changed[1]['content']=json.dumps(payload,ensure_ascii=False)
    check('conflicting_changed_body',q,altered,changed,False)
    altered=copy.deepcopy(c);altered[0]['record_sha256']='0'*64
    check('record_hash_changed',q,altered,m,False)
    check('model_source_conflict',q,c,m,False,dict(refused,reason='source_conflict'))
    check('model_version_refusal',q,c,m,False,dict(refused,reason='version_unverified'))
    check('model_already_answered',q,c,m,False,dict(answerable=True,chunk_ids=['L01-01'],reason=None))
    policy=copy.deepcopy(registry);policy['corpus_sha256']='0'*64
    check('corpus_version_changed',q,c,m,False,policy=policy)
    q2='成人球门的内侧宽度和横梁离地高度分别是多少？';c2,m2,_=pack(q2,[corpus['L01-03']],cfg,prompt)
    policy=copy.deepcopy(registry);policy['facts']=[f for f in policy['facts'] if f['property']!='crossbar_lower_edge_height_m']
    check('only_one_of_two_attributes_verified',q2,c2,m2,False,policy=policy)
    policy=copy.deepcopy(registry);policy['facts'].append(dict(policy['facts'][0],fact_id='ambiguous_copy'))
    check('two_fact_records_match_one_attribute',q,c,m,False,policy=policy)
    for text in ('天然草坪的颜色有什么限制？','儿童5号球球压是多少千帕？','英超成人球门内侧宽度是多少米？',
                 '标准成人球门的内宽是多少厘米？','人工草坪的颜色和材质分别是什么？','它的球压范围是多少？'):
        cc,mm,_=pack(text,c,cfg,prompt);check('confusion_'+str(len(rows)),text,cc,mm,False)
    # Observe only decisions actually archived from the unchanged original model.
    run=ROOT/'.runtime/phase2/d036-gate-live90-final';ledger={r['question_id']:r for r in read(ROOT/'optimization/reports/D036_business_gate_metrics.json')['cases']}
    archive=[]
    for qid,h in read(run/'completed.json')['hashes'].items():
        p=run/(qid+'.json');assert digest(p.read_bytes())==h;t=read(p);r=t['result'];ats=t['observations'].get('model_attempts',[])
        if not ats:archive.append(dict(question_id=qid,applied=False,reason='original_pre_model_gate'));continue
        sel=parse_selection(ats[-1]['response']['message']['content'],r['offered_ids'],cfg)
        c=[corpus[cid] for cid in r['offered_ids']]
        d=evaluate(t['question'],sel,c,ats[0]['messages'])
        if d['applied']:assert ledger[qid]['answerable'] and ledger[qid]['grade']=='false_refusal',(qid,d)
        archive.append(dict(question_id=qid,applied=d['applied'],decision=d,original_status=r['status'],original_selected_ids=r['selected_ids']))
    changed=[r['question_id'] for r in archive if r['applied']]
    assert changed==['D001','D002','T001'],changed
    save(out,dict(status='PASS',boundary_cases=rows,archive90=archive,archive_changes=changed,
        new_model_calls=0,all_boundaries_passed=True,no_wrong_supplements=True,holdout_used=False,
        scoring='Frozen-response counterfactual and injected boundary cases; not live QA accuracy.'))
    print(json.dumps(dict(status='PASS',boundary_checks=len(rows),archive_changes=changed,new_model_calls=0),ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args().out)
