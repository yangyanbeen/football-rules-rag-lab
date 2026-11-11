"""Read-only verification of the authorized public GitHub repository snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from eval_dataset import ROOT, write_json

REPO='yangyanbeen/football-rules-rag-lab'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--expected-commit')
    parser.add_argument('--require-supplement',action='store_true')
    args=parser.parse_args()
    report=args.report.resolve()
    if not any(report.is_relative_to(ROOT/name) for name in ('reports','.runtime','.tmp')) or report.suffix!='.json':
        raise ValueError('Use a repository-local report JSON')
    env=os.environ.copy()
    for name in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):env.pop(name,None)
    def run(argv,raw=False,input=None):
        proc=subprocess.run(argv,cwd=ROOT,env=env,input=input,capture_output=True,timeout=90)
        if proc.returncode:raise RuntimeError(proc.stderr.decode('utf-8',errors='replace')[-1200:])
        return proc.stdout if raw else proc.stdout.decode('utf-8').strip()
    def api(path):return json.loads(run(['gh','api','repos/'+REPO+'/'+path,'--method','GET']))
    checks=[]
    def record(name,passed):checks.append({'check':name,'passed':bool(passed)})
    repo=json.loads(run(['gh','api','repos/'+REPO,'--method','GET']))
    record('authorized_public_repository_identity',repo['id']==1453703558 and repo['owner']['id']==328912604
        and repo['full_name']==REPO and not repo['private'] and repo['default_branch']=='main')
    head=api('branches/main')['commit']['sha']
    if args.expected_commit:record('remote_main_matches_expected_commit',head==args.expected_commit)
    tree=api('git/trees/'+head+'?recursive=1')
    record('remote_tree_complete',not tree.get('truncated'))
    remote={r['path']:{'mode':r['mode'],'sha':r['sha']} for r in tree['tree'] if r['type']=='blob'}
    local={}
    for line in run(['git','ls-tree','-r','-z',head],raw=True).split(b'\0'):
        if line:
            fields,name=line.split(b'\t',1);mode,kind,sha=fields.decode().split()
            if kind=='blob':local[name.decode('utf-8')]={'mode':mode,'sha':sha}
    record('every_remote_file_matches_exact_local_commit',remote==local)
    required={'data/eval/retrieval_dev.jsonl','data/eval/retrieval_test.jsonl','data/eval/answer_eval.jsonl',
        'data/eval/human_review_receipt.json','scripts/validate_eval_dataset.py','scripts/build_dense_index.py',
        'scripts/dense_index.py','scripts/query_dense_index.py','docs/EVAL_DATASET.md','docs/EMBEDDING_AND_INDEX.md',
        'data/manifests/dense_index_manifest.json','data/manifests/dense_chunk_ids.json',
        'reports/TASK_04_DELIVERY.md','reports/TASK_05_DELIVERY.md'}
    if args.require_supplement:required.update({'scripts/validate_eval_receipt.py','scripts/recheck_task45.ps1',
                                               'scripts/verify_task45_regressions.py','reports/TASK_04_05_SUPPLEMENT.md'})
    record('required_task4_task5_deliverables_present',required<=set(remote))
    record('no_private_runtime_corpus_or_index_uploaded',not any(name.startswith(('.runtime/','.venv/','.models/',
        '.cache/','data/raw/','data/processed/','data/indexes/')) for name in remote))
    manifest=json.loads(run(['git','show',head+':data/manifests/project_file_manifest.json']))
    public={r['path']:r for r in manifest['files'] if r['distribution']=='public-git'}
    record('public_file_inventory_paths_match_remote',set(public)==set(remote)-{'data/manifests/project_file_manifest.json'})
    names=list(public)
    objects=run(['git','cat-file','--batch'],raw=True,input=''.join(remote[n]['sha']+'\n' for n in names).encode())
    offset=0;bad_hashes=[]
    for name in names:
        end=objects.index(b'\n',offset)
        sha,kind,size=objects[offset:end].decode().split();size=int(size);offset=end+1
        data=objects[offset:offset+size];offset+=size+1
        if (sha!=remote[name]['sha'] or kind!='blob' or size!=public[name]['size_bytes']
                or hashlib.sha256(data).hexdigest()!=public[name]['sha256']):bad_hashes.append(name)
    record('all_public_inventory_sizes_and_hashes_match_remote',not bad_hashes)
    pulls=[]
    for number,expected in ((8,'8e8b93c6556943b4d08ee82f2620a5bc21ee759a'),(9,'3e41191c145da963fb24057bb1b39354287ebc5a')):
        pr=api('pulls/'+str(number))
        record('original_delivery_pr_'+str(number)+'_merged',pr['merged'] and pr['merge_commit_sha']==expected)
        pulls.append({'number':number,'url':pr['html_url'],'merged':pr['merged'],'merge_commit':pr['merge_commit_sha']})
    for tag,sha in (('v0.4.1-human-reviewed','8e8b93c6556943b4d08ee82f2620a5bc21ee759a'),
                    ('v0.5.0-dense','3e41191c145da963fb24057bb1b39354287ebc5a')):
        record('original_release_tag_'+tag,api('git/ref/tags/'+tag)['object']['sha']==sha)
    result={'captured_at':datetime.now(timezone.utc).isoformat(),'status':'PASS' if all(r['passed'] for r in checks) else 'FAIL',
        'passed':sum(r['passed'] for r in checks),'total':len(checks),'checks':checks,'repository':REPO,
        'remote_commit':head,'remote_files':len(remote),'required_missing':sorted(required-set(remote)),
        'inventory_hash_mismatches':bad_hashes,'original_pull_requests':pulls,'remote_mutations_performed':False}
    write_json(report,result)
    print(json.dumps({k:result[k] for k in ('status','passed','total','remote_commit','remote_files','required_missing','inventory_hash_mismatches')}))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
