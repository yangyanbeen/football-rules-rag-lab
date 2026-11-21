"""Stage-aware E11 reporting; reuse the frozen E10 quality scorer only if run."""
import argparse,json,subprocess,sys
from pathlib import Path
from e10_model_comparison import ROOT,read
from score_e7_mapping import percentile

def save(p,v):p.write_bytes((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True);done=read(a.run/'completed.json');meta=read(a.run/'metadata.json')
    get=lambda name:read(a.run/name) if (a.run/name).exists() else None
    generic=get('generic_probe.json');representative=get('representative_probe.json')
    result=dict(run_status=done['status'],quality_evaluated=False,primary_observations=done['primary_observations'],
        actual_model_calls=done['actual_model_calls'],startup_memory=get('startup_memory.json'),
        model_identity=meta['models'],generic_probe=generic,representative_probe=representative,
        inference_commit=meta['source_commit'],resident_processes=meta['resident_processes'],
        full90_executed=False,holdout_used=False,quality_gates=None,cost_gates=None)
    if done['status']=='COMPLETED':
        # Compatibility view for the unchanged scorer. The E11 probes and
        # their quality exclusion remain separately archived in this run.
        compat=a.out/'scorer-input';compat.mkdir(exist_ok=False)
        for path in a.run.glob('*.json'):
            if path.name in ('completed.json','metadata.json','D036_zero_call.json') or path.name.startswith(('primary-','confirmation-')):
                (compat/path.name).write_bytes(path.read_bytes())
        save(compat/'deployment_probe.json',generic)
        derived=a.out/'quality'
        subprocess.run([sys.executable,'-B',str(ROOT/'optimization/score_e10_model.py'),'--run',str(compat),'--out',str(derived)],check=True,cwd=ROOT)
        result.update(read(derived/'metrics.json'));result['quality_evaluated']=True
        extra_resources=[generic['resources'],representative['resources']]
        result['cost_gates']['preflights_memory']=all(v['available_min_GiB']>=1 and v['process_rss_peak_GiB']<=6.5 for v in extra_resources)
        result['cost_gates']['representative_within_90s']=representative['seconds']<=90
        if all(result['quality_gates'].values()):
            result['decision']='READY_FOR_90' if all(result['cost_gates'].values()) else 'QUALITY_PASS_COST_FAIL'
        else:result['decision']='STOP_MODEL_CANDIDATE'
        timings={}
        for variant in 'AB':
            rows=[read(path) for path in a.run.glob('primary-*.json') if read(path)['variant']==variant]
            timings[variant]={k:dict(sum=sum(r['model_timing'][k] for r in rows),p50=percentile([r['model_timing'][k] for r in rows],.5),
                p95=percentile([r['model_timing'][k] for r in rows],.95)) for k in ('load_seconds','server_resident_request_seconds','prompt_eval_seconds','generation_seconds')}
        result['separate_model_timings']=timings
    else:
        result['decision']='STARTUP_MEMORY_NOT_READY' if done['status']=='STARTUP_MEMORY_NOT_READY' else 'STOP_DEPLOYMENT_REVALIDATION'
        result['partial_primary_files']=[path.name for path in a.run.glob('primary-*.json')]
        result['quality_evaluated']=bool(result['partial_primary_files'])
        result['quality_claim']='No complete 36-observation comparison; do not infer full QA accuracy or model superiority.'
    save(a.out/'metrics.json',result)
    print(json.dumps({k:result[k] for k in ('decision','quality_evaluated','primary_observations','actual_model_calls')},ensure_ascii=False))

if __name__=='__main__':main()
