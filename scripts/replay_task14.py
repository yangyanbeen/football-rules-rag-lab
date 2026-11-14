"""Read-only recomputation of frozen formal retrieval, answer and human summaries."""
import argparse,importlib,time,sys
from task14_archive import *
from answer_eval_core import now


def replay():
    checks={};errors=[];receipts=[];started=time.perf_counter()
    for module,folder in [('dense_retrieval_eval','dense_b0'),('bm25_retrieval_eval','bm25_b0'),('hybrid_retrieval_eval','hybrid_rrf_b0'),('reranker_eval','bge_reranker_b0'),('structure_retrieval_eval','structure_pc_b0')]:
        for split in ('dev','test'):
            actual_split='development/title_body' if folder=='bm25_b0' and split=='dev' else split
            directory=ROOT/'reports/retrieval'/folder/actual_split;name=folder+'_'+split
            try:
                result=importlib.import_module(module).replay(directory)
                if canonical(result)!=canonical(read(directory/'summary.json')):raise ValueError('Recomputed summary differs')
                checks[name]=True;receipts.append({'name':name,'summary':record(directory/'summary.json'),'predictions':record(directory/'predictions.jsonl'),'new_model_requests':0})
            except Exception as exc:checks[name]=False;errors.append({'check':name,'error':type(exc).__name__+': '+str(exc)})
            print(json.dumps({'check':name,'passed':checks[name]}),flush=True)
    from answer_audit_v2 import strict_run
    for split in ('dev','test'):
        name='answers_'+split
        try:
            summary=strict_run(split,False)
            if summary['samples']!=({'dev':40,'test':50}[split]):raise ValueError('Wrong sample count')
            checks[name]=True;receipts.append({'name':name,'summary':record(ROOT/'reports/answer_evaluation'/split/'summary.json'),'new_model_requests':0})
        except Exception as exc:checks[name]=False;errors.append({'check':name,'error':type(exc).__name__+': '+str(exc)})
    try:
        from answer_acceptance import analyze
        result=analyze(read(ROOT/'reports/answer_evaluation_acceptance/human-review-completed.json'))
        if canonical(result)!=canonical(read(ROOT/'reports/answer_evaluation_acceptance/human-quality-analysis.json')):raise ValueError('Human analysis differs')
        checks['actual12_human_arithmetic']=True
    except Exception as exc:checks['actual12_human_arithmetic']=False;errors.append({'check':'actual12_human_arithmetic','error':type(exc).__name__+': '+str(exc)})
    return {'version':'task14-formal-replay-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'receipts':receipts,'source_sha256':record(__file__)['sha256'],'site_packages_disabled':bool(sys.flags.no_site),'new_model_requests':0,'new_formal_test_runs':0,'new_human_judgments':0,'elapsed_seconds':time.perf_counter()-started,'scope':'Saved dev/test rankings, actual timing, predictions/judgments and explicit human vectors recomputed read only. No new inference or formal test rerun.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',required=True);a=p.parse_args();v=replay();write_new(ROOT/a.report,v);print(json.dumps({k:v[k] for k in ('status','passed','total','errors')},ensure_ascii=False));raise SystemExit(v['status']!='PASS')
