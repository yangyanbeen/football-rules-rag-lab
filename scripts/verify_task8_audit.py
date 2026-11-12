"""Isolated Task8 defect reproductions and regression checks; no locked-test requests."""
from __future__ import annotations
import argparse,copy,json,shutil,subprocess,uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import bm25_retrieval_eval as ev
import run_bm25_retrieval as runner
from bm25_index import ROOT,record,write_new,SOURCES
from compare_bm25_segmentation import replay_comparison
from eval_dataset import digest

BASE='93687ce5a73853a63782d2204225b046697c7028'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path,required=True);p.add_argument('--expect-gaps',action='store_true');a=p.parse_args()
    report=a.report.resolve()
    if report.exists() or not report.is_relative_to(ROOT/'reports'):raise ValueError('Use a new reports file')
    temp=ROOT/'.tmp'/('task8-audit-'+uuid.uuid4().hex);temp.mkdir(parents=True)
    checks={};errors=[]
    def check(name,fn):
        try:checks[name]=bool(fn())
        except Exception as exc:checks[name]=False;errors.append({'check':name,'error_type':type(exc).__name__,'error':str(exc)})
    def rejects(fn):
        try:fn()
        except (ValueError,OSError,KeyError,TypeError):return True
        return False
    def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False),'utf-8')
    base=ROOT/'reports/retrieval/bm25_b0'
    def seg_case(name,mutate):
        folder=temp/name;shutil.copytree(base/'segmentation-dev',folder)
        m=json.loads((folder/'manifest.json').read_text('utf-8'))
        for n in m['artifacts']:m['artifacts'][n]=record(folder/n)
        mutate(m,folder);save(folder/'manifest.json',m)
        return rejects(lambda:replay_comparison(folder))
    def main_case(name,mutate):
        folder=temp/name;shutil.copytree(base/'development/title_body',folder)
        m=json.loads((folder/'run_manifest.json').read_text('utf-8'));mutate(m)
        start={k:m[k] for k in ('version','run_id','split','template','purpose','source_commit','inputs','started_at','authorization')}
        save(folder/'run_started.json',start)
        m['artifacts']['run_started.json']={k:v for k,v in record(folder/'run_started.json').items() if k!='path'}
        save(folder/'run_manifest.json',m)
        return rejects(lambda:ev.replay(folder))
    def git_record(commit,name):
        raw=subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT)
        return {'path':name,'size_bytes':len(raw),'sha256':digest(raw)}
    def future_source(m):
        m['source_commit']=BASE
        m['inputs'].update({p:git_record(BASE,p) for p in ev.V1_EXECUTION_FILES})
    def future_index(m):
        m['index_manifest']['source_commit']=BASE
        m['index_manifest']['sources']={p:git_record(BASE,p) for p in SOURCES}
    cases={
        'reject_segmentation_missing_artifacts':lambda:seg_case('missing-artifacts',lambda m,f:m.update(artifacts={})),
        'reject_segmentation_missing_sources':lambda:seg_case('missing-sources',lambda m,f:m.update(sources={})),
        'reject_segmentation_missing_inputs':lambda:seg_case('missing-inputs',lambda m,f:m.update(inputs={})),
        'reject_segmentation_wrong_mode':lambda:seg_case('wrong-mode',lambda m,f:m.update(mode='accurate')),
        'reject_segmentation_hmm_change':lambda:seg_case('hmm',lambda m,f:m.update(HMM=True)),
        'reject_segmentation_boolean_test_count':lambda:seg_case('bool-count',lambda m,f:m.update(new_test_runs=False)),
        'reject_segmentation_missing_warmups':lambda:seg_case('warmups',lambda m,f:m.update(warmups=[])),
        'reject_segmentation_negative_wall':lambda:seg_case('wall',lambda m,f:m.update(wall_seconds=-1)),
        'reject_source_commit_after_run':lambda:main_case('future-source',future_source),
        'reject_index_producer_after_run':lambda:main_case('future-index',future_index),
    }
    def forged_comparison(m,folder):
        path=folder/'comparison.json';value=json.loads(path.read_text('utf-8'))
        value['search']['metrics']['Recall@5']=0;save(path,value);m['artifacts']['comparison.json']=record(path)
    cases['reject_resigned_wrong_comparison']=lambda:seg_case('wrong-comparison',forged_comparison)
    def uncommitted_grant():
        grant=json.loads((base/'test_authorization.json').read_text('utf-8'))
        for key in ('selection','verification'):
            target=temp/(key+'.json');shutil.copyfile(ROOT/grant[key]['path'],target);grant[key]=record(target)
        return rejects(lambda:ev.validate_grant(grant,base/'test'))
    cases['reject_uncommitted_grant_receipts']=uncommitted_grant
    def exclusive_ledger():
        target=temp/'synthetic-ledger.jsonl';value={'run_id':'synthetic','event':'STARTED'}
        reserve=getattr(runner,'reserve_test_usage',runner.append)
        reserve(target,value);old=target.read_bytes()
        return rejects(lambda:reserve(target,dict(value,run_id='second')) ) and target.read_bytes()==old
    cases['exclusive_test_reservation']=exclusive_ledger
    def mkdir_failure():
        root=temp/'synthetic-root';out=root/'reports/retrieval/failure';original=Path.mkdir
        def mkdir(path,*args,**kwargs):
            if path==out and kwargs.get('exist_ok') is False:raise OSError('synthetic directory failure')
            return original(path,*args,**kwargs)
        args=SimpleNamespace(mode='dev',run_dir=out,template='title_body',authorization=None,index=None)
        with patch.object(runner,'ROOT',root),patch.object(runner,'require_release'),patch.object(runner,'committed',return_value=BASE),patch.object(runner,'snapshots',return_value={}),patch.object(runner,'load_jsonl',return_value=[]),patch.object(Path,'mkdir',mkdir):
            try:runner.evaluate(args)
            except OSError as exc:
                return str(exc)=='synthetic directory failure' and (out/'failure.json').exists()
        return False
    cases['directory_failure_has_evidence']=mkdir_failure
    # Reproduction expects these protections to be absent in the baseline.
    for name,fn in cases.items():check(name,(lambda fn=fn:not fn()) if a.expect_gaps else fn)
    if not a.expect_gaps:
        check('original_three_dev_and_test_replay',lambda:all(ev.replay(base/'development'/t)['split']=='dev' for t in ('body','title_body','path_body')) and ev.replay(base/'test')['split']=='test')
        check('original_segmentation_replay',lambda:replay_comparison(base/'segmentation-dev')['split']=='dev')
        check('finite_huge_integer_rejected',lambda:not ev.finite(10**10000))
        def invalid_identity_before_dataset_read():
            def mutate(m):m['split']='../../forbidden'
            with patch.object(ev,'load_jsonl',side_effect=AssertionError('Dataset read before identity validation')):
                return main_case('invalid-split',mutate)
        check('invalid_split_rejected_before_dataset_read',invalid_identity_before_dataset_read)
    result={'version':'task8-audit-regression-1.0','captured_at':ev.now(),
            'status':('GAPS_REPRODUCED' if a.expect_gaps else 'PASS') if all(checks.values()) else 'FAIL',
            'baseline':BASE,'passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,
            'scope':'Isolated modified copies and synthetic failure/ledger operations; no original evidence changed',
            'new_locked_test_retrievals':0,'source_sha256':record(Path(__file__))['sha256']}
    write_new(report,result);print(json.dumps({k:result[k] for k in ('status','passed','total','errors')}))
    return 0 if all(checks.values()) else 1


if __name__=='__main__':raise SystemExit(main())
