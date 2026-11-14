"""Task13 integration delivery gate; public replay and optional local preservation checks."""
import argparse,io,tarfile
from task13_replay import *
from task13_package import verify as verify_package,OUTPUT as PACKAGE

BASE='10897adeee92841c22b1f83992b4ee6c5abdae70'
MUTABLE={'README.md','docs/DELIVERY_STATUS.md','docs/PUBLIC_SETUP.md','docs/EXPERIMENT_LOG.md','reports/README.md',
    'reports/all_experiments_summary.csv','reports/resume_evidence.md','data/manifests/experiment_manifest.json','data/manifests/project_file_manifest.json'}
FOLDER=ROOT/'reports/task13'


def all_checks(v,count):
    return v['status']=='PASS' and v['passed']==v['total']==len(v['checks'])==count and all(b is True for b in v['checks'].values()) and not v['errors']


def verify(public_only=False):
    checks={};errors=[]
    def check(name,fn):
        try:
            checks[name]=fn() is True
            if not checks[name]:errors.append({'check':name,'error':'False predicate'})
        except Exception as exc:checks[name]=False;errors.append({'check':name,'error':type(exc).__name__+': '+str(exc)})
    with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','archive','--format=tar',BASE],cwd=ROOT))) as arc:
        old={m.name:arc.extractfile(m).read() for m in arc.getmembers() if m.isfile()}
    check('781_prior_public_files_preserved_except_navigation',lambda:len(old)==781 and all((ROOT/n).read_bytes()==b for n,b in old.items() if n not in MUTABLE))
    for n in ('docs/EXPERIMENT_LOG.md','reports/all_experiments_summary.csv','reports/resume_evidence.md'):
        check(n+'_append_only',lambda n=n:(ROOT/n).read_bytes().startswith(old[n]))
    registry=read(ROOT/'data/manifests/experiment_manifest.json');previous=json.loads(old['data/manifests/experiment_manifest.json']);entry=registry['experiments'][-1]
    check('23_prior_experiment_objects_preserved',lambda:len(previous['experiments'])==23 and registry['experiments'][:23]==previous['experiments'])
    check('24th_integration_experiment_registered',lambda:len(registry['experiments'])==24 and entry['id']=='TASK-013-INTEGRATED-DELIVERY' and entry['baseline_commit']==BASE and entry['formal_test_runs_added']==0 and entry['new_human_judgments']==0 and all(record(ROOT/r['path'])==r for r in entry['artifacts']))
    check('registered_source_committed_and_identical',lambda:all(digest(subprocess.check_output(['git','show',entry['source_commit']+':'+n],cwd=ROOT))==h==record(ROOT/n)['sha256'] for n,h in entry['source_sha256'].items()))
    package=read(ROOT/PACKAGE);cfg=app_config();environment=read(FOLDER/'environment-final.json');preflight=read(FOLDER/'preflight.json');rebuild=read(FOLDER/'index-rebuild.json')
    check('runtime_package_files_receipts_and_models_verify',lambda:verify_package(package,not public_only))
    check('fresh_isolated_262_package_environment_completed',lambda:environment['status']=='PASS' and environment['fresh_environment'] is True and environment['system_site_packages'] is False and environment['existing_environment_changed'] is False and environment['new_environment']==str(Path(cfg['environment']).parent.parent).replace('\\','/') and len(environment['actual']['packages'])==262 and environment['actual']['isolated'] is True and all(o['exit_code']==0 for o in environment['operations']))
    provenance=read(FOLDER/'requirements-provenance.json')
    check('requirements_match_fixed_upstream_lock_export',lambda:provenance['status']=='PASS' and provenance['exact_offline_reexport_matches'] is True and provenance['requirements']==environment['requirements']==record(ROOT/'infra/task13-runtime-requirements.txt') and provenance['upstream_commit']==environment['upstream_commit']==package['upstream_commit'])
    check('retained_initial_install_failure_disclosed',lambda:read(FOLDER/'environment.json')['status']=='FAIL' and 'TEMP/TMP' in (ROOT/'docs/TASK_13_REPRODUCTION.md').read_text('utf-8'))
    for n in ('corpus-import.json','clean-corpus-import.json'):
        v=read(FOLDER/n)
        check(n+'_61_files_99_original_records',lambda v=v:v['status']=='PASS' and v['files']==61 and v['records']==99 and v['corpus']==package['private_data']['corpus'] and v['inventory']==record(ROOT/'data/manifests/local_data_files.json') and v['new_model_requests']==0 and v['secondary_chunking'] is False)
    clean=read(FOLDER/'clean-corpus-import.json')
    check('real_clean_public_checkout_copied_all61_with_python_S',lambda:clean['clean_public_checkout_before_import'] is True and clean['site_packages_disabled'] is True and len(clean['copied_files'])==61 and not clean['existing_verified_files'])
    rc=read(ROOT/'config/reranker_experiment.json')
    check('preflight_bound_to_models_config_and_new_environment',lambda:preflight['status']=='PASS' and preflight['records']==99 and preflight['configuration']==source_identity() and preflight['corpus']==package['private_data']['corpus'] and preflight['packages']==environment['actual']['packages'] and preflight['answer_model']==package['models']['answer'] and preflight['embedding_model']==package['models']['embedding'] and preflight['reranker_model_files']==rc['files'] and preflight['reranker_revision']==rc['revision'] and preflight['upstream_commit']==package['upstream_commit'] and preflight['new_model_inference_requests']==0 and preflight['ui_assets_verified'] is True)
    check('new_indexes_rebuilt_99_vectors_without_overwriting',lambda:rebuild['status']=='PASS' and rebuild['records']==99 and rebuild['dimensions']==1024 and rebuild['configuration']==source_identity() and rebuild['previous_indexes_overwritten'] is False and rebuild['new_formal_test_runs']==0 and len(rebuild['embedding_batches'])==25 and sum(b['inputs'] for b in rebuild['embedding_batches'])==99 and all(rebuild[k]==package['private_data']['indexes'][k] and rebuild[k]['path']==cfg[k]+'/index_manifest.json' for k in ('dense_index','bm25_index')))
    backend=read(FOLDER/'backend-demo-first.json');ui=read(FOLDER/'ui-demo.json')
    check('five_actual_backend_cases_replay_public_metadata',lambda:replay_demo(backend))
    check('five_actual_browser_cases_replay_public_metadata',lambda:replay_demo(ui,True))
    check('ten_distinct_real_worker_traces',lambda:len({r['result']['trace_id'] for v in (backend,ui) for r in v['rows']})==10 and len({r['result']['private_trace']['path'] for v in (backend,ui) for r in v['rows']})==10)
    check('actual_backend_producer_runtime_matches_current',lambda:all(subprocess.check_output(['git','show',backend['source_commit']+':'+n],cwd=ROOT)==(ROOT/n).read_bytes() for n in ('scripts/task13_core.py','scripts/task13_engine.py','scripts/query_task13.py','scripts/task13_worker_client.py')))
    check('actual_browser_source_hashes_match_current',lambda:all(record(ROOT/n)['sha256']==h for n,h in ui['source_sha256'].items()))
    contract=read(FOLDER/'contract-final.json');public_cases=read(FOLDER/'public-cases-clean.json')
    check('45_private_contract_and_corruption_checks_recorded',lambda:all_checks(contract,45) and contract['private'] is True and contract['new_model_requests']==0 and all(record(ROOT/n)['sha256']==h for n,h in contract['source_sha256'].items()))
    check('28_public_cases_passed_in_real_clean_python_S_checkout',lambda:all_checks(public_cases,28) and public_cases['site_packages_disabled'] is True and public_cases['private_data_accessed'] is False and public_cases['new_model_requests']==0 and public_cases['clean_public_checkout'] is True and all(record(ROOT/n)['sha256']==h for n,h in public_cases['source_sha256'].items()))
    from verify_task13_public_cases import verify as verify_public_cases
    check('public_adversarial_checks_independently_recompute',lambda:all_checks(verify_public_cases(),28))
    prior=read(FOLDER/'prior-task12.json')
    check('task12_original26_gate_actually_passed_before_registration',lambda:all_checks(prior,26) and prior['task12_fully_accepted'] is True and prior['human_reviews']==12 and prior['human_ledger_entries']==13 and prior['source_sha256']==record(ROOT/'scripts/verify_task12_final.py')['sha256'])
    from answer_audit_v2 import strict_run
    for split in ('dev','test'):
        check(split+'_original_answer_results_replay_without_inference',lambda split=split:strict_run(split,not public_only)['samples']==answer_config()['formal_samples'][split])
    for p in ('reports/TASK_13_DELIVERY.md','docs/TASK_13_REPRODUCTION.md','docs/TASK_13_LICENSES.md','frontend/start_integrated_rag.ps1','config/task13_app.json'):
        check(p+'_delivered',lambda p=p:(ROOT/p).is_file() and (ROOT/p).stat().st_size>100)
    check('public_git_has_no_full_corpus_models_databases_or_raw_answers',lambda:not any(n.startswith(('data/raw/','data/processed/','data/indexes/','.runtime/','.models/','.venv/','third_party/')) for n in subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode('utf-8').split('\0') if n))
    if not public_only:
        before=read(ROOT/'.runtime/task13/before.json')
        check('269_original_private_corpus_indexes_traces_ledgers_unchanged',lambda:len(before['private'])==269 and all(digest((ROOT/n).read_bytes())==h for n,h in before['private'].items()))
        check('23_previous_git_tags_unchanged',lambda:len(before['tags'].splitlines())==23 and all(line in subprocess.check_output(['git','show-ref','--tags'],cwd=ROOT,text=True).splitlines() for line in before['tags'].splitlines()))
        def packages():
            code='import importlib.metadata as m,json;print(json.dumps({d.metadata["Name"]:d.version for d in m.distributions()}))'
            existing=json.loads(subprocess.check_output([str(ROOT/'.venv/Scripts/python.exe'),'-B','-c',code],cwd=ROOT,text=True))
            fresh=json.loads(subprocess.check_output([str(ROOT/cfg['environment']),'-B','-c',code],cwd=ROOT,text=True))
            return existing==before['packages']==fresh==environment['actual']['packages']
        check('existing_and_fresh_actual_262_packages_equal',packages)
        from verify_task13_contract import verify as verify_contract
        check('45_private_contract_checks_recompute',lambda:all_checks(verify_contract(True),45))
        def actual_browser():
            from capture_task13_ui import capture
            actual=capture();actual.pop('captured_at');saved=copy.deepcopy(ui);saved.pop('captured_at')
            return actual==saved
        check('five_actual_browser_DOM_answers_journal_and_sources_recompute',actual_browser)
        def artifacts():
            for key,field in (('dense_index','artifact_files'),('bm25_index','artifacts')):
                folder=ROOT/cfg[key];m=read(folder/'index_manifest.json')
                for name,ref in m[field].items():
                    p=(folder/name).resolve()
                    if not p.is_relative_to(folder.resolve()) or {'size_bytes':p.stat().st_size,'sha256':digest(p.read_bytes())}!=ref:return False
            return True
        check('rebuilt_dense_and_BM25_payloads_match_private_manifests',artifacts)
    return {'version':'task13-delivery-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'task13_fully_accepted':all(checks.values()),'public_only':public_only,'new_model_requests':0,'new_human_judgments':0,'new_formal_test_runs':0,'source_sha256':record(__file__)['sha256'],'runtime_package':record(ROOT/PACKAGE),'scope':'Task13 integration/reproduction acceptance, retaining prior formal scores and quality limitations. Public checks replay metadata; private checks bind saved original inference and browser evidence.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--public-only',action='store_true');p.add_argument('--report',required=True);a=p.parse_args();v=verify(a.public_only);write_new(ROOT/a.report,v);print(json.dumps({k:v[k] for k in ('status','passed','total','errors','task13_fully_accepted')},ensure_ascii=False));raise SystemExit(v['status']!='PASS')
