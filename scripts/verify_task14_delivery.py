"""Verify the final evidence archive and preserve prior project deliveries."""
import argparse
import sys

from task14_archive import (BASE, FIELDS, FOLDER, ROOT, SPEC, baseline, baseline_names,
                            canonical, digest, git, read, record, verify_archive, write_new)
from answer_eval_core import now


APPEND = ('docs/EXPERIMENT_LOG.md', 'reports/all_experiments_summary.csv', 'reports/resume_evidence.md')
REGISTRY = 'data/manifests/experiment_manifest.json'
INVENTORY = 'data/manifests/project_file_manifest.json'
MUTABLE = {*APPEND, REGISTRY, INVENTORY, 'README.md', 'docs/DELIVERY_STATUS.md', 'reports/README.md'}
PRIVATE = ('.runtime', '.models', '.venv', 'third_party', 'data/raw', 'data/processed')
NEW_TAG = 'v0.14.0-final-evidence-archive'
STAGE = 'TASK-014-FINAL-ARCHIVE'
ZERO_KEYS = ('new_model_requests', 'new_formal_test_runs', 'new_human_judgments')
ARTIFACTS = {
    'config/task14_archive.json', 'docs/TASK_14_SCOPE.md', 'docs/TASK_14_ARCHIVE.md',
    'scripts/task14_archive.py', 'scripts/replay_task14.py', 'scripts/verify_task14_archive.py',
    'scripts/verify_task14_delivery.py',
    *('reports/task14/'+n for n in (
        'archive.json', 'experiments.csv', 'RESUME_FINAL.md', 'RESULTS_FINAL.md', 'prior-task13.json',
        'formal-replay-first.json', 'regressions-final.json', 'public-formal-replay.json',
        'public-regressions.json', 'regressions-first.json', 'regressions-second.json',
    )),
}


def passed(v, n):
    return (v['status']=='PASS' and v['passed']==v['total']==len(v['checks'])==n
            and all(x is True for x in v['checks'].values()) and v['errors']==[])


def no_new(v):
    return all(type(v[k]) is int and v[k]==0 for k in ZERO_KEYS)


def verify(public_only):
    import csv
    import io
    import json
    import subprocess
    import tarfile

    checks,errors={},[]
    def check(name, fn):
        try:
            if fn() is not True:
                raise ValueError('False predicate')
            checks[name]=True
        except Exception as exc:
            checks[name]=False
            errors.append({'check':name,'error':type(exc).__name__+': '+str(exc)})

    archive=read(FOLDER/'archive.json')
    registry=read(ROOT/REGISTRY)
    old_registry=json.loads(baseline(REGISTRY))
    registered=registry['experiments'][-1]
    tracked=set(git('ls-files').splitlines())

    def frozen():
        with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','archive','--format=tar',BASE],cwd=ROOT))) as tar:
            old={m.name:tar.extractfile(m).read() for m in tar if m.isfile()}
        return (len(old)==858 and set(old)==baseline_names() and set(old)<=tracked
                and all((ROOT/n).read_bytes()==b for n,b in old.items() if n not in MUTABLE))

    check('858_old_public_files_and_both_authority_documents_preserved',frozen)
    for n in APPEND:
        check(n+'_append_only',lambda n=n:(ROOT/n).read_bytes().startswith(baseline(n)))
    check('25_old_registry_objects_exact',lambda:len(old_registry['experiments'])==25
          and canonical(registry['experiments'][:-1])==canonical(old_registry['experiments']))
    entry_keys={'id','objective','control','main_variable','dataset_version','evaluation_version',
                'source_commit','archive_producer','model','parameters','hardware','commands',
                'artifacts','metrics','decision','limitations'}
    check('new_final_archive_registration_complete',lambda:len(registry['experiments'])==26
          and registered['id']==STAGE and all(registered.get(k) for k in entry_keys)
          and registered['archive_producer']==archive['source_commit'] and no_new(registered['metrics']))
    check('registry_hashes_resolve_to_tracked_files',lambda:{a['path'] for a in registered['artifacts']}==ARTIFACTS
          and len(registered['artifacts'])==len(ARTIFACTS) and ARTIFACTS<=tracked
          and all(record(ROOT/a['path'])==a for a in registered['artifacts']))
    check('registered_code_matches_its_git_producer',lambda:all(git('show',registered['source_commit']+':'+p,raw=True)==(ROOT/p).read_bytes()
          for p in (SPEC,'scripts/task14_archive.py','scripts/replay_task14.py','scripts/verify_task14_archive.py','scripts/verify_task14_delivery.py')))

    def summaries():
        rows=list(csv.DictReader(io.StringIO((ROOT/APPEND[1]).read_text('utf-8-sig'))))
        return (len(rows)==26 and [r['experiment_id'] for r in rows]==[r['id'] for r in registry['experiments']]
                and all(k is not None and v is not None for k,v in rows[-1].items())
                and all(rows[-1][k]=='待测' for k in ('Recall_at_5','MRR_at_10','answer_accuracy')))

    check('legacy_csv_25_plus_one_archive_only_row',summaries)
    check('canonical_archive_rebuild_and_exports_match',lambda:verify_archive(archive))
    check('28_records_cover_tasks_1_through_14_with_all_fields',lambda:len(archive['records'])==28
          and all(set(FIELDS)<=set(r) for r in archive['records'])
          and {t for r in archive['records'] for t in r['tasks']}==set(range(1,15)))
    check('78_measured_claims_and_9_lineage_groups',lambda:len({c['id'] for c in archive['claims']})==78
          and len(archive['claims'])==78 and len(archive['groups'])==9
          and all(c['status']=='measured' and c['lineage']['raw_results'] and c['lineage']['commands']
                  for c in archive['claims']))
    check('12_unmeasured_with_no_resume_use',lambda:len(archive['unmeasured'])==12 and
          all(r['status']=='待测' and r['value'] is None and r['resume_allowed'] is False for r in archive['unmeasured']))
    check('archive_has_no_new_model_formal_or_review_results',lambda:no_new(archive))
    prior=read(FOLDER/'prior-task13.json')
    check('prior_task13_28_passed_before_archive_registration',lambda:passed(prior,28)
          and prior['task13_fully_accepted'] is True and no_new(prior))
    for n in ('regressions-first.json','regressions-second.json'):
        check(n+'_historical_failure_retained',lambda n=n:(lambda v:v['status']=='FAIL'
              and v['passed']==42 and v['total']==43 and len(v['errors'])==1 and no_new(v))(read(FOLDER/n)))

    def public_snapshot(v):
        receipt=v['public_checkout']
        sha=receipt['commit']
        return (receipt['clean_before_run'] is True and receipt['private_paths_absent']==list(PRIVATE)
                and git('rev-parse',sha)==sha
                and all(git('show',sha+':'+n,raw=True)==(ROOT/n).read_bytes() for n in (
                    'scripts/task14_archive.py', 'scripts/verify_task14_archive.py', 'scripts/replay_task14.py',
                    SPEC, 'reports/task14/archive.json')))

    for n in ('regressions-final.json','public-regressions.json'):
        def regression(n=n):
            r=read(FOLDER/n)
            return (passed(r,43) and no_new(r) and r['site_packages_disabled'] is True
                    and r['source_sha256']=={p:record(ROOT/p)['sha256'] for p in (
                        'scripts/task14_archive.py','scripts/verify_task14_archive.py',SPEC)}
                    and (n=='regressions-final.json' or public_snapshot(r)))
        check(n+'_43_archive_and_tampering_checks',regression)
    for n in ('formal-replay-first.json','public-formal-replay.json'):
        def replay(n=n):
            r=read(FOLDER/n)
            return (passed(r,13) and no_new(r) and r['site_packages_disabled'] is True
                    and r['source_sha256']==record(ROOT/'scripts/replay_task14.py')['sha256']
                    and {x['name'] for x in r['receipts']}==set(r['checks'])-{'actual12_human_arithmetic'}
                    and len(r['receipts'])==12 and all(x['new_model_requests']==0 and
                        all(record(ROOT/x[k]['path'])==x[k] for k in ('summary','predictions') if k in x)
                        for x in r['receipts'])
                    and (n=='formal-replay-first.json' or public_snapshot(r)))
        check(n+'_13_historical_recomputations',replay)
    check('public_tree_excludes_private_directories',lambda:not any(
        n.startswith(tuple(p+'/' for p in PRIVATE)) for n in tracked))
    check('archive_and_delivery_documents_are_linked',lambda:all(
        p in (ROOT/n).read_text('utf-8') for n,p in (
            ('README.md','reports/TASK_14_DELIVERY.md'),('reports/README.md','task14/RESUME_FINAL.md'),
            ('docs/DELIVERY_STATUS.md','TASK_14_DELIVERY.md'),('docs/TASK_14_ARCHIVE.md','TASK_14_DELIVERY.md'),
            ('reports/resume_evidence.md','task14/RESUME_FINAL.md'),('docs/EXPERIMENT_LOG.md',STAGE))
        ) and (ROOT/'reports/TASK_14_DELIVERY.md').is_file())
    check('public_inventory_matches_index',lambda:(lambda v:
          v['file_count']==len(tracked)+60==len(v['files']) and
          {r['path'] for r in v['files'] if r['distribution']=='public-git'}==tracked-{INVENTORY} and
          all(record(ROOT/r['path'])=={k:r[k] for k in ('path','size_bytes','sha256')}
              for r in v['files'] if r['distribution']=='public-git'))(read(ROOT/INVENTORY)))
    if public_only:
        check('public_gate_runs_without_local_artifacts',lambda:bool(sys.flags.no_site) and not any((ROOT/p).exists() for p in PRIVATE))
    else:
        local=read(ROOT/'.runtime/task14/before.json')
        check('private_323_frozen_files_preserved',lambda:local['base']==BASE and len(local['private'])==323
              and all(digest((ROOT/p).read_bytes())==sha for p,sha in local['private'].items()))
        check('25_old_local_tags_preserved',lambda:len(local['tags'].splitlines())==25 and
              [x for x in git('show-ref','--tags').splitlines() if not x.endswith(' refs/tags/'+NEW_TAG)]
              ==local['tags'].strip().splitlines())
        check('local_gate_works_without_third_party_packages',lambda:bool(sys.flags.no_site))
        check('61_corpus_hashes_match_inventory',lambda:(lambda v:
              len([r for r in v['files'] if r['distribution']=='local-only'])==61 and
              all(record(ROOT/r['path'])=={k:r[k] for k in ('path','size_bytes','sha256')}
                  for r in v['files'] if r['distribution']=='local-only'))(read(ROOT/INVENTORY)))
    accepted=all(checks.values())
    return {'version':'task14-delivery-1.0','captured_at':now(),'status':'PASS' if accepted else 'FAIL',
            'task14_fully_accepted':accepted,'passed':sum(checks.values()),'total':len(checks),
            'checks':checks,'errors':errors,'public_only':public_only,'baseline_commit':BASE,
            'source_sha256':record(__file__)['sha256'],'new_model_requests':0,'new_formal_test_runs':0,
            'new_human_judgments':0}


if __name__=='__main__':
    import json
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--public-only',action='store_true')
    p.add_argument('--report',required=True)
    a=p.parse_args()
    out=verify(a.public_only)
    write_new(ROOT/a.report,out)
    print(json.dumps({k:out[k] for k in ('status','passed','total','errors')},ensure_ascii=False))
    raise SystemExit(out['status']!='PASS')
