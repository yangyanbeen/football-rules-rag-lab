"""Task12 final release gate: actual metrics, probes, regressions and preserved baselines."""
import argparse,json,subprocess
from answer_eval_core import *


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True);a=p.parse_args();checks={};errors=[]
    def check(name,fn):
        try:
            checks[name]=bool(fn())
            if not checks[name]:errors.append({'check':name,'error':'False predicate'})
        except Exception as exc:checks[name]=False;errors.append({'check':name,'error':str(exc)})
    def receipt(name):
        v=read(DIRECTORY/'acceptance'/name)
        return v['status']=='PASS' and type(v['passed']) is int and v['passed']==v['total']==len(v['checks']) and all(b is True for b in v['checks'].values())
    for name in ('contract-final.json','arithmetic-final.json','delivery-complete.json','public-complete.json','prior-task11-regression.json'):
        check(name+'_all_actual_checks_pass',lambda name=name:receipt(name))
    def probes():
        v=read(DIRECTORY/'evidence/probes.json')
        return v['status']=='PASS' and v['passed']==v['total']==len(v['cases'])==4 and {r['id'] for r in v['cases']}=={'outside','version','similar_negative','source_conflict'} and all(r['passed'] is True and r['status']=='refused' and r['error'] is None and record(ROOT/r['trace']['path'])==r['trace'] for r in v['cases'])
    check('four_real_or_explicit_synthetic_robustness_probes',probes)
    check('independent_public_checkout_no_models_and_no_new_inference',lambda:read(DIRECTORY/'acceptance/public-complete.json')['site_packages_disabled'] is True and read(DIRECTORY/'acceptance/public-complete.json')['new_model_requests']==0)
    def frozen_native():
        d=read(DIRECTORY/'dev/run_started.json');t=read(DIRECTORY/'test/run_started.json')
        return all(d['inputs'][p]==t['inputs'][p]==record(ROOT/p) for p in NATIVE+RESOURCES)
    check('dev_and_test_identical_production_metrics_prompts_and_policy',frozen_native)
    check('original20_git_tags_unchanged_locally',lambda:git('show-ref','--tags')==read(PRIVATE/'before.json')['tags'].strip())
    registered=read(ROOT/'data/manifests/experiment_manifest.json')['experiments'][-1]
    check('21st_experiment_real_source_commit_and_native_hashes',lambda:registered['id']=='TASK-012-ANSWER-EVALUATION' and all(registered['source_sha256'][p]==record(ROOT/p)['sha256']==digest(subprocess.check_output(['git','show',registered['source_commit']+':'+p],cwd=ROOT)) for p in NATIVE))
    def cpu():
        models=read(DIRECTORY/'evidence/model_runtime.json')['models'];pins={config()['llm']['name']:config()['llm']['digest'],'bge-m3:latest':read(ROOT/'config/dense_index.json')['model']['digest']}
        return all(any(m['name']==name and m['digest']==sha and m['size_vram']==0 for m in models) for name,sha in pins.items())
    check('actual_pinned_answer_and_embedding_models_observed_on_cpu',cpu)
    bundle=read(DIRECTORY/'evidence/local_answer_bundle.json')
    check('all90_complete_local_answers_and_review_html_delivered',lambda:bundle['formal_answer_count']==90 and all(record(ROOT/r['path'])==r for r in bundle['artifacts']))
    check('human_accuracy_not_fabricated',lambda:read(ROOT/'reports/answer_quality_results.json')['new_human_answer_judgments']==0 and read(DIRECTORY/'human_review_sample.json')['status']=='PENDING')
    result={'version':'answer-release-gate-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,
      'source_sha256':record(__file__)['sha256'],'new_model_requests':0,'delivery_scope':'Automated answer evaluation and review-ready artifacts; human semantic acceptance remains pending without actual decisions'}
    write_new(ROOT/a.report,result);print(json.dumps({k:result[k] for k in ('status','passed','total','errors')}));return result['status']!='PASS'


if __name__=='__main__':raise SystemExit(main())
