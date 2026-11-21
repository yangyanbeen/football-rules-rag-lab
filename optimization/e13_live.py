"""Sequential normal Worker E13 comparisons; no alternate retrieval or model."""
import argparse,copy,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,record,canonical,digest
from task13_audit_client import call_worker
from task13_audit import public_projection,validate_public
from citation_catalog_guard import safe_render
from e10_resources import Sampler,snapshot

PLAN=ROOT/'optimization/experiments/E13_source_facts/plan.json'
def save(p,v):
    with p.open('x',encoding='utf8') as f:json.dump(v,f,ensure_ascii=False,indent=2)
def source_refs():
    names=subprocess.check_output(['git','ls-files','scripts','config'],cwd=ROOT,text=True).splitlines()
    return {n:record(ROOT/n) for n in names}
def content_score(result,case,facts):
    if case.get('facts'):
        ids=result['selected_ids'];wanted=[facts[k] for k in case['facts']]
        mask=[f['source_chunk_id'] in ids for f in wanted];support={f['source_chunk_id'] for f in wanted}
    elif case.get('support'):
        ids=result['selected_ids'];mask=[bool(set(v)&set(ids)) for v in case['support']];support={i for v in case['support'] for i in v}
    else:return dict(grade='boundary_observation',wrong_supplement=bool(result.get('fact_recovery',{}).get('applied')))
    grade='runtime_error' if result['error'] else 'false_refusal' if result['status']=='refused' else 'correct' if all(mask) else 'partial' if any(mask) else 'incorrect'
    return dict(grade=grade,point_mask=mask,citation_numerator=sum(i in support for i in ids),citation_denominator=len(ids),
        wrong_supplement=bool(result.get('fact_recovery',{}).get('applied')) and
            (not all(mask) or any(i not in support for i in ids)))

def run(out,pid,mode):
    assert not out.exists();out.mkdir(parents=True)
    plan=read(PLAN);refs=source_refs()
    for n in ('optimization/e13_live.py','optimization/experiments/E13_source_facts/plan.json'):
        refs[n]=record(ROOT/n)
    registry=read(ROOT/'config/source_bound_facts.json');facts={f['fact_id']:f for f in registry['facts']}
    sampler=Sampler(pid,out/'resources.jsonl')
    save(out/'metadata.json',dict(mode=mode,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_files=refs,hardware=snapshot(),normal_entry='Unmodified call_worker subprocess boundary; fact fallback opt-in only in B.',
        feature_registry=record(ROOT/'config/source_bound_facts.json'),holdout_used=False,
        control_scope='Independent live A/B calls' if mode=='special' else 'Actual candidate model response plus deterministic pre-recovery shadow A; not a second independent model run'))
    cases=[c for c in plan['pressure_questions'] if not c.get('replay_only')]+plan['correct_controls']+plan['boundary_controls']
    if mode=='special':
        schedule=[dict(case=c,variant=v) for i,c in enumerate(cases) for v in ('AB' if i%2==0 else 'BA')]
    else:
        assert read(ROOT/'optimization/reports/E13_special_metrics.json')['all_gates_passed']
        labels=read(ROOT/'optimization/datasets/dev_40.json')+read(ROOT/'optimization/datasets/regression_50.json')
        assert len(labels)==90
        schedule=[dict(case=dict(name=c['question_id'],question=c['question']),variant='B') for c in labels]
    save(out/'schedule.json',schedule);rows=[];hashes={};prior=os.environ.get('FOOTBALL_SOURCE_FACTS');status='COMPLETED'
    try:
        for pos,item in enumerate(schedule,1):
            c=item['case'];variant=item['variant'];os.environ['FOOTBALL_SOURCE_FACTS']='1' if variant=='B' else '0'
            before=sampler.begin(c['name']+'-'+variant);start=time.perf_counter();r=None;error=None;reference=None
            try:
                r,reference,wall=call_worker(c['question'])
                p=public_projection(r,ROOT/reference['path']);validate_public(p,True)
            except Exception as exc:error=type(exc).__name__+': '+str(exc)
            value=dict(name=c['name'],question=c['question'],variant=variant,seconds=time.perf_counter()-start,
                result=r,private_trace=reference,error=error,resources=sampler.end(before))
            if r:
                value['score']=content_score(r,c,facts) if mode=='special' else None
                sel=r['attempts'][-1]['parsed'] if r['attempts'] and not r['attempts'][-1]['error'] else None
                value['raw_model_selection']=sel
                if r.get('fact_recovery',{}).get('applied'):
                    assert sel==dict(answerable=False,chunk_ids=[],reason='insufficient_evidence')
                    # Original model decision and original source renderer form
                    # the paired deterministic control, without a second call.
                    a=copy.deepcopy(r);a.pop('fact_recovery',None)
                    a.update(status='refused',selected_ids=[],refusal_reason='insufficient_evidence')
                    a['answer'],a['citations']=safe_render([],{v['chunk_id']:v for v in r['context']})
                    value['shared_response_control']=a
                elif mode=='regression':value['shared_response_control']=copy.deepcopy(r)
            file=c['name']+'-'+variant+'.json';save(out/file,value);hashes[file]=digest((out/file).read_bytes());rows.append(value)
            print(json.dumps(dict(done=pos,total=len(schedule),name=c['name'],variant=variant,
                status=r['status'] if r else None,selected=r['selected_ids'] if r else None,
                recovery=r.get('fact_recovery') if r else None,score=value.get('score'),
                seconds=value['seconds'],available_min_GiB=value['resources']['available_min_GiB'],error=error),ensure_ascii=False),flush=True)
            if (value.get('score') or {}).get('wrong_supplement'):
                status='STOP_WRONG_SUPPLEMENT';break
            if sampler.aborted:status='RESOURCE_STOP';break
        assert all(record(ROOT/n)==v for n,v in refs.items())
    except Exception:
        status='SCRIPT_ERROR'
        raise
    finally:
        sampler.close()
        if prior is None:os.environ.pop('FOOTBALL_SOURCE_FACTS',None)
        else:os.environ['FOOTBALL_SOURCE_FACTS']=prior
        save(out/'completed.json',dict(status=status,observations=len(rows),hashes=hashes,holdout_used=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['special','regression']);p.add_argument('--out',type=Path,required=True);p.add_argument('--server-pid',type=int,required=True);a=p.parse_args();run(a.out,a.server_pid,a.mode)
