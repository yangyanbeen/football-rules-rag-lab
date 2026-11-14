"""Current Task13 supplement gate, retaining original complete accepted artifacts."""
import argparse,io,tarfile
from task13_audit import *

BASE='8befa040b94b7b1da1ac592f73ccf98da363e036'
FOLDER=ROOT/'reports/rechecks/task13-audit-20261114'
MUTABLE={'README.md','docs/DELIVERY_STATUS.md','docs/PUBLIC_SETUP.md','docs/EXPERIMENT_LOG.md','reports/README.md','reports/all_experiments_summary.csv','reports/resume_evidence.md','data/manifests/experiment_manifest.json','data/manifests/project_file_manifest.json'}


def verify(public=False):
    checks={};errors=[]
    def check(name,fn):
        try:
            checks[name]=fn() is True
            if not checks[name]:errors.append({'check':name,'error':'False predicate'})
        except Exception as exc:checks[name]=False;errors.append({'check':name,'error':type(exc).__name__+': '+str(exc)})
    def passed(v,n):return v['status']=='PASS' and v['passed']==v['total']==len(v['checks'])==n and all(x is True for x in v['checks'].values()) and not v['errors']
    with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','archive','--format=tar',BASE],cwd=ROOT))) as arc:
        old={m.name:arc.extractfile(m).read() for m in arc.getmembers() if m.isfile()}
    check('825_prior_public_files_preserved_except_navigation',lambda:len(old)==825 and all((ROOT/n).read_bytes()==b for n,b in old.items() if n not in MUTABLE))
    for n in ('docs/EXPERIMENT_LOG.md','reports/resume_evidence.md','reports/all_experiments_summary.csv'):check(n+'_append_only',lambda n=n:(ROOT/n).read_bytes().startswith(old[n]))
    prior=json.loads(old['data/manifests/experiment_manifest.json']);registry=read(ROOT/'data/manifests/experiment_manifest.json');entry=registry['experiments'][-1]
    check('24_original_experiment_objects_preserved',lambda:len(prior['experiments'])==24 and registry['experiments'][:24]==prior['experiments'])
    check('25th_audit_experiment_and_artifacts_valid',lambda:len(registry['experiments'])==25 and entry['id']=='TASK-013-AUDIT' and entry['baseline_commit']==BASE and entry['new_formal_test_runs']==entry['new_human_judgments']==0 and all(record(ROOT/r['path'])==r for r in entry['artifacts']))
    check('current_audit_code_bound_to_committed_source',lambda:all(record(ROOT/n)['sha256']==h==digest(subprocess.check_output(['git','show',entry['source_commit']+':'+n],cwd=ROOT)) for n,h in entry['source_sha256'].items()))
    check('original39_complete_gate_actually_passed_before_registration',lambda:passed(read(FOLDER/'prior-full.json'),39) and read(FOLDER/'prior-full.json')['task13_fully_accepted'] is True)
    gaps=read(FOLDER/'original-gaps.json');check('all_seven_original_gaps_reproduced_without_inference',lambda:gaps['status']=='GAPS_REPRODUCED' and gaps['reproduced']==gaps['total']==len(gaps['checks'])==7 and all(gaps['checks'].values()) and gaps['new_model_requests']==0)
    check('original_runtime_package_strict_member_and_data_verification',lambda:verify_package(read(ROOT/'reports/task13/delivery_manifest.json'),not public))
    revisions=read(FOLDER/'runtime-package.json')
    check('revision_package_code_resources_and_policies_identical',lambda:revisions['source_commit']==entry['source_commit'] and all(record(ROOT/r['path'])==r and digest(subprocess.check_output(['git','show',revisions['source_commit']+':'+r['path']],cwd=ROOT))==r['sha256'] for r in revisions['members']) and revisions['base_package']==record(ROOT/'reports/task13/delivery_manifest.json') and revisions['config']==record(ROOT/CONFIG) and revisions['model_policies']==source_identity() and revisions['new_formal_test_runs']==0)
    for name,count in (('regressions-complete.json',54),('public-current.json',47)):
        v=read(FOLDER/name);check(name+'_recorded_checks_pass',lambda v=v,count=count:passed(v,count) and v['new_model_requests']==0 and all(record(ROOT/n)['sha256']==h for n,h in v['source_sha256'].items()))
    check('real_clean_public_python_S_regressions_completed',lambda:read(FOLDER/'public-current.json')['clean_checkout_before_tests'] is True and read(FOLDER/'public-current.json')['site_packages_disabled'] is True)
    from verify_task13_audit import verify as regress
    check('current_regressions_recompute_without_model_requests',lambda:passed(regress(not public),47 if public else 54))
    from run_task13_audit_demo import replay
    for name,ui in (('backend-final.json',False),('ui.json',True)):
        check(name+'_five_actual_cases_replay',lambda name=name,ui=ui:replay(read(FOLDER/name),ui,not public))
    for split in ('dev','test'):
        from answer_audit_v2 import strict_run
        check(split+'_historical_formal_results_read_only_replay',lambda split=split:strict_run(split,not public)['samples']==answer_config()['formal_samples'][split])
    check('99_sources_bound_to_frozen_hashes',lambda:len(source_map())==99)
    for n in ('docs/TASK_13_AUDIT.md','reports/TASK_13_SUPPLEMENT.md','frontend/start_integrated_rag_audit.ps1'):
        check(n+'_delivered',lambda n=n:(ROOT/n).is_file() and (ROOT/n).stat().st_size>100)
    check('fixed_policies_and_isolated_revised_UI',lambda:audit_config()['ui']['port']==7867 and audit_config()['ui']['app_data']!=app_config()['ui']['app_data'] and audit_config()['environment']==app_config()['environment'])
    check('no_private_runtime_corpus_models_indexes_or_raw_responses_tracked',lambda:not any(n.startswith(('.runtime/','.models/','data/raw/','data/processed/','data/indexes/','third_party/')) for n in subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()))
    if not public:
        before=read(ROOT/'.runtime/task13-audit/before.json')
        check('298_original_private_artifacts_still_identical',lambda:len(before['private'])==298 and all(digest((ROOT/n).read_bytes())==h for n,h in before['private'].items()))
        check('24_old_tags_preserved',lambda:len(before['tags'].splitlines())==24 and all(line in subprocess.check_output(['git','show-ref','--tags'],cwd=ROOT,text=True).splitlines() for line in before['tags'].splitlines()))
        check('editable_upstream_still_clean_and_pinned',upstream_clean)
    return {'version':'task13-audit-delivery-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'public_only':public,'task13_fully_accepted':all(checks.values()),'new_model_requests':0,'new_human_judgments':0,'new_formal_test_runs':0,'source_sha256':record(__file__)['sha256'],'scope':'Original Task13 criteria plus explicit repair regressions. Original formal scores/quality errors and old artifacts are preserved.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--public-only',action='store_true');p.add_argument('--report',required=True);a=p.parse_args();v=verify(a.public_only);write_new(ROOT/a.report,v);print(json.dumps({k:v[k] for k in ('status','passed','total','errors')},ensure_ascii=False));raise SystemExit(v['status']!='PASS')
