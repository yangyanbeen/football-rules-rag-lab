"""BM25 arithmetic, tokenization, index and saved-development fault regressions."""
from __future__ import annotations
import argparse,copy,json,math,shutil,sys,uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from bm25_index import (ROOT,TEMPLATES,SOURCE_FIELDS,Tokenizer,Bm25Index,rank,normalize,
                        build,record,write_new)
from bm25_retrieval_eval import V1_EXECUTION_FILES,replay,choose,now,validate_grant
from eval_dataset import digest,load_jsonl
import run_bm25_retrieval as runner


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True)
    p.add_argument('--development-root',type=Path);args=p.parse_args()
    report=runner.report_path(args.report);temp=ROOT/'.tmp'/('bm25-contract-'+uuid.uuid4().hex);temp.mkdir()
    checks={}
    def check(name,value):checks[name]=bool(value)
    def rejects(callback):
        try:callback()
        except (ValueError,KeyError,TypeError,OSError):return True
        return False
    toy={'N':3,'avgdl':2.,'df':{'越位':2,'任意球':2,'罚球':1},'documents':[
        {'chunk_id':'a','length':2,'tf':{'越位':2}},
        {'chunk_id':'b','length':2,'tf':{'任意球':1,'罚球':1}},
        {'chunk_id':'c','length':2,'tf':{'越位':1,'任意球':1}}]}
    result=rank(toy,['越位'],top_k=3);idf=math.log(1.6)
    check('hand_bm25_first_score',math.isclose(result[0]['score'],idf*5/3.5,abs_tol=1e-12))
    check('hand_bm25_second_score',math.isclose(result[1]['score'],idf,abs_tol=1e-12))
    check('hand_expected_rank_order',[r['chunk_id'] for r in result]==['a','c'])
    check('query_tf_counts_unique_once',rank(toy,['越位','越位'],top_k=3)==result)
    check('oov_returns_empty',rank(toy,['不存在'],top_k=3)==[])
    check('empty_tokens_returns_empty',rank(toy,[],top_k=3)==[])
    ubiquitous={'N':2,'avgdl':1.,'df':{'x':2},'documents':[{'chunk_id':i,'length':1,'tf':{'x':1}} for i in ('b','a')]}
    check('idf_ubiquitous_term_still_positive',rank(ubiquitous,['x'],top_k=2)[0]['score']>0)
    check('ties_use_stable_id',[r['chunk_id'] for r in rank(ubiquitous,['x'],top_k=2)]==['a','b'])
    check('rank_never_zero_fills',len(result)==2)
    for name,value in [('zero',0),('boolean',True),('negative',-1),('oversize',4),('float',2.)]:
        check('invalid_top_k_'+name,rejects(lambda value=value:rank(toy,['越位'],top_k=value)))
    for name,k,b in [('bool_k',True,.75),('nan_k',float('nan'),.75),('negative_k',-1,.75),('bad_b',1.5,2),('bool_b',1.5,True)]:
        check('invalid_parameters_'+name,rejects(lambda k=k,b=b:rank(toy,['越位'],k,b,3)))
    tokenizer=Tokenizer()
    check('jieba_0421_archive_bound',tokenizer.dependency['dependency']['version']=='0.42.1' and len(tokenizer.dependency['files'])==54)
    check('default_dictionary_sha_pinned',tokenizer.dependency['default_dictionary_sha256']=='7197c3211ddd98962b036cdf40324d1ea2bfaa12bd028e68faa70111a88e12a8')
    check('chinese_and_arabic_rule_number_match',tokenizer.tokens('第十一条')==tokenizer.tokens('第11条')==['rule:11','11'])
    check('fullwidth_rule_number_normalizes',tokenizer.tokens('第１１条')==['rule:11','11'])
    check('decimal_values_preserved',all(v in tokenizer.tokens('7.32米、2.44米、9.15米') for v in ('7.32','2.44','9.15','米')))
    check('fullwidth_decimal_preserved','7.32' in tokenizer.tokens('７．３２米'))
    check('english_nfkc_casefold',tokenizer.tokens('ＦＩＦＡ')==['fifa'])
    check('football_terms_preserved','间接任意球' in tokenizer.tokens('间接任意球能否直接进球'))
    check('direct_and_indirect_not_conflated',tokenizer.tokens('直接任意球')!=tokenizer.tokens('间接任意球'))
    check('negation_and_conditions_not_stopwords',all(w not in tokenizer.stop for w in ('不','不得','如果','必须','除外')))
    check('normalization_matches_query_policy',normalize('  ＡＢＣ\n  足球 ')=='abc 足球')
    for name,value in [('empty',' '),('nontext',None),('oversize','中'*401)]:check('invalid_query_'+name,rejects(lambda value=value:normalize(value)))
    indexes={t:Bm25Index(ROOT/'data/indexes/bm25'/t) for t in TEMPLATES}
    for template,index in indexes.items():
        check(template+'_99_ids',len(index.sources)==99 and len(index.payload['documents'])==99)
        a=index.query('第11条越位位置如何判定？');b=index.query('第11条越位位置如何判定？')
        check(template+'_deterministic_query',a['results']==b['results'] and a['tokens']==b['tokens'])
        check(template+'_no_full_text_in_results',all(set(v)==set(SOURCE_FIELDS)|{'rank','score'} for v in a['results']))
    check('index_build_never_overwrites',rejects(lambda:build(ROOT/'data/indexes/bm25/body','body')))
    check('index_build_rejects_dense_path',rejects(lambda:build(ROOT/'data/indexes/dense/new-index','body')))
    base=ROOT/'data/indexes/bm25/body'
    index_mutations=[('changed_tf',lambda x:x['documents'][0]['tf'].update({'虚构词':1})),
                     ('changed_df',lambda x:x['df'].update({'虚构词':99})),
                     ('changed_length',lambda x:x['documents'][0].update(length=1)),
                     ('changed_avgdl',lambda x:x.update(avgdl=x['avgdl']+1)),
                     ('bool_document_count',lambda x:x.update(N=True)),
                     ('duplicate_id',lambda x:x['documents'][1].update(chunk_id=x['documents'][0]['chunk_id'])),
                     ('extra_text_field',lambda x:x.update(content_zh='synthetic forbidden text'))]
    for name,mutate in index_mutations:
        folder=temp/name;shutil.copytree(base,folder)
        payload=json.loads((folder/'index.json').read_text('utf-8'));mutate(payload)
        (folder/'index.json').write_text(json.dumps(payload,ensure_ascii=False),'utf-8')
        manifest=json.loads((folder/'index_manifest.json').read_text('utf-8'))
        manifest['artifacts']['index.json']={k:v for k,v in record(folder/'index.json').items() if k!='path'}
        (folder/'index_manifest.json').write_text(json.dumps(manifest),'utf-8')
        check('rehash_does_not_hide_'+name,rejects(lambda folder=folder:Bm25Index(folder)))
    noauth=temp/'unused-run'
    with patch.object(runner,'require_release',side_effect=AssertionError('No release/model work before authorization')):
        check('unauthorized_test_rejected_early',rejects(lambda:runner.evaluate(SimpleNamespace(mode='test',run_dir=ROOT/'reports/retrieval/not-created-test',authorization=None))))
    check('invalid_grant_schema_rejected',rejects(lambda:validate_grant({'purpose':'development'},noauth)))
    check('no_formal_test_directory_created',not (ROOT/'reports/retrieval/not-created-test').exists())
    development_checked=False
    if args.development_root:
        root=args.development_root.resolve();selected=choose(root);development_checked=True
        check('all_three_dev_templates_replay',len(selected['development_runs'])==3)
        for template in TEMPLATES:
            s=replay(root/template)
            check(template+'_fixed_dev_counts',s['quality']['questions']==40 and s['quality']['answerable_denominator']==32 and s['quality']['unanswerable_excluded']==8)
            check(template+'_120_measurements',s['latency']['all']['total_seconds']['samples']==120)
        mutations=[('summary_score', 'summary.json',lambda v:v['quality']['metrics'].update({'MRR@10':1.})),
                   ('result_score','predictions.jsonl',lambda v:v[0]['results'][0].update(score=-1)),
                   ('result_bool_rank','predictions.jsonl',lambda v:v[0]['results'][0].update(rank=True)),
                   ('result_bool_law','predictions.jsonl',lambda v:v[0]['results'][0].update(law_number=True)),
                   ('extra_body','predictions.jsonl',lambda v:v[0]['results'][0].update(content_zh='synthetic forbidden text')),
                   ('wrong_query','predictions.jsonl',lambda v:v[0].update(query='wrong query')),
                   ('missing_prediction','predictions.jsonl',lambda v:v.pop()),
                   ('duplicate_prediction','predictions.jsonl',lambda v:v.append(copy.deepcopy(v[0]))),
                   ('boolean_repetition','predictions.jsonl',lambda v:v[0]['measurements'][0].update(repetition=True)),
                   ('negative_timing','predictions.jsonl',lambda v:v[0]['measurements'][0].update(total_seconds=-1)),
                   ('journal_ranking','requests.jsonl',lambda v:v[0].update(ranked_ids=[])),
                   ('journal_future','requests.jsonl',lambda v:v[0].update(recorded_at='2099-01-01T00:00:00+00:00'))]
        for name,filename,mutate in mutations:
            folder=temp/('replay-'+name);shutil.copytree(root/'body',folder)
            path=folder/filename;value=load_jsonl(path) if filename.endswith('jsonl') else json.loads(path.read_text('utf-8'))
            mutate(value)
            path.write_text(('\n'.join(json.dumps(r,ensure_ascii=False) for r in value)+'\n') if filename.endswith('jsonl') else json.dumps(value,ensure_ascii=False),'utf-8')
            manifest=json.loads((folder/'run_manifest.json').read_text('utf-8'))
            manifest['artifacts'][filename]={k:v for k,v in record(path).items() if k!='path'}
            (folder/'run_manifest.json').write_text(json.dumps(manifest),'utf-8')
            check('saved_dev_rejects_'+name,rejects(lambda folder=folder:replay(folder)))
    result={'version':'bm25-contract-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL',
            'passed':sum(checks.values()),'total':len(checks),'checks':checks,'development_replay_checked':development_checked,
            'source_sha256':{p:record(ROOT/p)['sha256'] for p in V1_EXECUTION_FILES},
            'scope':'Toy hand arithmetic, actual tokenizer/index checks, isolated corrupt copies; no real locked-test retrieval or model calls.'}
    write_new(report,result)
    print(json.dumps({k:result[k] for k in ('status','passed','total','development_replay_checked')}))
    if not all(checks.values()):print(json.dumps([k for k,v in checks.items() if not v]))
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
