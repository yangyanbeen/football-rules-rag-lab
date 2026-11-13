"""Task9 hand arithmetic, bad packets, failure lifecycle and saved-dev mutations."""
import argparse,copy,json,math,shutil,uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from eval_dataset import ROOT,canonical,digest
from bm25_index import record,write_new
from bm25_retrieval_eval import now
from rrf import fuse,candidates,METHODS,CHANNELS
import hybrid_retrieval_eval as ev
import run_hybrid_retrieval as runner


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True)
    p.add_argument('--development-run',type=Path);a=p.parse_args();report=runner.new_report(a.report)
    temp=ROOT/'.tmp'/('rrf-contract-'+uuid.uuid4().hex);temp.mkdir(parents=True)
    checks={};errors=[]
    def check(name,fn):
        try:checks[name]=bool(fn())
        except Exception as exc:checks[name]=False;errors.append({'check':name,'type':type(exc).__name__,'error':str(exc)})
    def rejects(fn):
        try:fn()
        except (ValueError,KeyError,TypeError,OSError):return True
        return False
    def row(cid,rank,channel):
        return {'chunk_id':cid,'source_url':'https://en.wikipedia.org/wiki/Football','source_lines':[1,2],'law_number':1,
                'record_sha256':'0'*64,'content_zh_sha256':'1'*64,'rank':rank,'score':1. if channel=='bm25' else .9,
                **({'distance':.1} if channel=='dense' else {})}
    def packet(dense=('a','b'),bm=('b','c')):
        return {'dense':[row(c,i,'dense') for i,c in enumerate(dense,1)],'bm25':[row(c,i,'bm25') for i,c in enumerate(bm,1)]}
    source=packet();result=fuse(source)
    check('overlap_document_promoted_by_two_ranks',lambda:result['rrf'][0]['chunk_id']=='b')
    check('hand_score_rank2_plus_rank1',lambda:result['rrf'][0]['score']==float(Fraction(1,62)+Fraction(1,61)))
    check('missing_channel_contributes_zero',lambda:next(r for r in result['rrf'] if r['chunk_id']=='a')['score']==float(Fraction(1,61)))
    check('cross_channel_ids_deduplicated',lambda:len(result['rrf'])==3 and len({r['chunk_id'] for r in result['rrf']})==3)
    check('both_original_ranks_scores_and_distance_preserved',lambda:result['rrf'][0]['sources']=={'dense':{'rank':2,'score':.9,'distance':.1},'bm25':{'rank':1,'score':1.}})
    check('source_metadata_preserved',lambda:result['rrf'][0]['source_lines']==[1,2] and result['rrf'][0]['record_sha256']=='0'*64)
    check('union_dense_first_round_robin_deduplicates',lambda:[r['chunk_id'] for r in result['union']]==['a','b','c'])
    check('union_has_no_invented_score',lambda:all(r['score'] is None for r in result['union']))
    check('single_channel_ranks_preserved',lambda:all([r['chunk_id'] for r in result[c]]==[r['chunk_id'] for r in source[c]] for c in CHANNELS))
    check('exact_ties_use_chunk_id_order',lambda:[r['chunk_id'] for r in fuse(packet(('b','a'),('a','b')))['rrf']]==['a','b'])
    check('k_zero_is_supported',lambda:fuse(source,0)['rrf'][0]['score']==1.5)
    check('k_configured_changes_scores',lambda:fuse(source,20)['rrf'][0]['score']!=result['rrf'][0]['score'])
    check('empty_channels_return_empty_lists',lambda:all(not r for r in fuse(packet((),())).values()))
    check('empty_bm25_does_not_fill_zero_matches',lambda:not fuse(packet(('a','b'),()))['bm25'])
    check('one_channel_rrf_uses_original_order',lambda:[r['chunk_id'] for r in fuse(packet(('b','a'),()))['rrf']]==['b','a'])
    twenty=packet(tuple('d'+str(i) for i in range(10)),tuple('b'+str(i) for i in range(10)))
    check('full_union_20_but_all_outputs_budget_10',lambda:len(candidates(twenty))==20 and all(len(v)==10 for v in fuse(twenty).values()))
    check('inputs_not_mutated',lambda:source==packet())
    for name,value in [('boolean',True),('negative',-1),('float',60.0),('too_large',1000001)]:
        check('reject_k_'+name,lambda value=value:rejects(lambda:fuse(source,value)))
    for name,value in [('boolean',True),('zero',0),('oversized',100)]:
        check('reject_topk_'+name,lambda value=value:rejects(lambda:fuse(source,60,value)))
    def bad(mutate):
        value=copy.deepcopy(source);mutate(value);return rejects(lambda:fuse(value))
    for name,mutate in [
        ('duplicate_within_channel',lambda v:v['dense'].append(dict(v['dense'][0],rank=3))),
        ('missing_channel',lambda v:v.pop('bm25')),
        ('extra_channel',lambda v:v.update(other=[])),
        ('rank_gap',lambda v:v['dense'][0].update(rank=0)),
        ('boolean_rank',lambda v:v['dense'][0].update(rank=True)),
        ('nan_score',lambda v:v['bm25'][0].update(score=math.nan)),
        ('zero_bm25_score',lambda v:v['bm25'][0].update(score=0)),
        ('huge_integer',lambda v:v['bm25'][0].update(score=10**10000)),
        ('boolean_law',lambda v:v['dense'][0].update(law_number=True)),
        ('dense_score_distance',lambda v:v['dense'][0].update(distance=.8)),
        ('conflicting_metadata',lambda v:v['bm25'][0].update(source_lines=[2,3])),
        ('extra_corpus_body',lambda v:v['dense'][0].update(content_zh='forbidden synthetic body'))]:
        check('reject_packet_'+name,lambda mutate=mutate:bad(mutate))
    def no_test_without_grant():
        args=SimpleNamespace(mode='test',run_dir=temp/'reports/retrieval/test',authorization=None)
        with patch.object(runner,'ROOT',temp),patch.object(runner,'components',side_effect=AssertionError('Must not load test rankings')):
            return rejects(lambda:runner.evaluate(args))
    check('no_test_input_loaded_without_grant',no_test_without_grant)
    def reservation():
        path=temp/'reservation.jsonl'
        def start(n):
            try:runner.reserve_test_usage(path,{'run_id':str(n),'event':'STARTED'});return True
            except FileExistsError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:values=list(pool.map(start,(1,2)))
        return sum(values)==1 and len(ev.load_jsonl(path))==1
    check('one_atomic_reservation_under_concurrency',reservation)
    check('task9_ledger_is_separate_from_task8',lambda:runner.LEDGER!=ROOT/'reports/retrieval/bm25_b0/test_usage.jsonl')
    def fail_components():
        fake=temp/'synthetic-root';out=fake/'reports/retrieval/failed'
        args=SimpleNamespace(mode='dev',run_dir=out,k=None)
        with patch.object(runner,'ROOT',fake),patch.object(runner,'require_release'),patch.object(runner,'committed',return_value=ev.BASE),patch.object(runner,'snapshots',return_value={}),patch.object(runner,'components',side_effect=RuntimeError('synthetic component failure')):
            try:runner.evaluate(args)
            except RuntimeError as exc:
                failure=json.loads((out/'failure.json').read_text('utf-8'))
                return str(exc)=='synthetic component failure' and failure['phase']=='load_original_channels' and not (out/'run_manifest.json').exists()
        return False
    check('failed_run_preserves_primary_error_and_failure_marker',fail_components)
    if a.development_run:
        original=a.development_run.resolve()
        check('complete_development_replay',lambda:ev.replay(original)['split']=='dev')
        def corrupt(name,filename,mutate):
            folder=temp/name;shutil.copytree(original,folder);path=folder/filename
            value=ev.load_jsonl(path) if filename.endswith('.jsonl') else json.loads(path.read_text('utf-8'))
            mutate(value)
            raw=('\n'.join(json.dumps(r,ensure_ascii=False,allow_nan=False) for r in value)+'\n') if filename.endswith('.jsonl') else json.dumps(value,ensure_ascii=False,allow_nan=False)
            path.write_text(raw,'utf-8');m=json.loads((folder/'run_manifest.json').read_text('utf-8'))
            if filename!='run_manifest.json':m['artifacts'][filename]={k:v for k,v in record(path).items() if k!='path'}
            else:m=value
            (folder/'run_manifest.json').write_text(json.dumps(m,ensure_ascii=False),'utf-8')
            return rejects(lambda:ev.replay(folder))
        for name,filename,mutate in [
            ('wrong_fused_score','predictions.jsonl',lambda v:v[0]['results']['rrf'][0].update(score=0)),
            ('wrong_channel_score','predictions.jsonl',lambda v:v[0]['channels']['bm25']['results'][0].update(score=123)),
            ('wrong_channel_timing','predictions.jsonl',lambda v:v[0]['channels']['dense']['measurements'][0].update(total_seconds=0)),
            ('wrong_source_rank','predictions.jsonl',lambda v:v[0]['results']['rrf'][0]['sources']['dense'].update(rank=99)),
            ('wrong_union','predictions.jsonl',lambda v:v[0].update(candidate_union=[])),
            ('missing_question','predictions.jsonl',lambda v:v.pop()),
            ('duplicate_question','predictions.jsonl',lambda v:v.append(copy.deepcopy(v[0]))),
            ('wrong_repeat_digest','predictions.jsonl',lambda v:v[0]['measurements'][0].update(result_sha256='0'*64)),
            ('boolean_repetition','predictions.jsonl',lambda v:v[0]['measurements'][0].update(repetition=True)),
            ('negative_fusion_time','predictions.jsonl',lambda v:v[0]['measurements'][0].update(fusion_seconds=-1)),
            ('wrong_summary','summary.json',lambda v:v['methods']['rrf']['quality']['metrics'].update(**{'Recall@5':0})),
            ('wrong_error_analysis','error_analysis.json',lambda v:v['counts']['rrf'].update(miss_at_5=999)),
            ('missing_artifacts','run_manifest.json',lambda v:v.update(artifacts={})),
            ('wrong_scope_boolean','run_manifest.json',lambda v:v.update(new_channel_retrieval_requests=False)),
            ('missing_warmups','run_manifest.json',lambda v:v.update(module_warmups=[]))]:
            check('saved_dev_rejects_'+name,lambda name=name,filename=filename,mutate=mutate:corrupt(name,filename,mutate))
    result={'version':'hybrid-contract-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL',
            'passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,
            'development_replay_checked':bool(a.development_run),'development_manifest':record(a.development_run/'run_manifest.json') if a.development_run else None,
            'source_sha256':{p:record(ROOT/p)['sha256'] for p in ev.SOURCES},'new_channel_retrieval_requests':0,
            'scope':'Toy arithmetic, isolated corrupt development copies, synthetic failures and reservation; no test ranking scoring'}
    write_new(report,result);print(json.dumps({k:result[k] for k in ('status','passed','total','errors')}))
    return 0 if all(checks.values()) else 1


if __name__=='__main__':raise SystemExit(main())
