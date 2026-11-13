"""Synthetic boundaries and metadata mutations; no retrieval/model calls."""
import argparse,copy,json,types,uuid
from pathlib import Path
from eval_dataset import ROOT,canonical,digest
from bm25_index import write_new,record
from bm25_retrieval_eval import now
from structure_aware_chunking import split_spans,distribution
import structure_retrieval_eval as ev
from run_structure_comparison import output_path,run_path


def rejects(fn):
    try:fn()
    except (ValueError,TypeError,KeyError,FileExistsError):return True
    return False


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--dev-dir',type=Path);a=p.parse_args();out=output_path(a.report)
    checks={};errors=[]
    def check(name,fn):
        try:
            checks[name]=bool(fn())
            if not checks[name]:errors.append({'check':name,'error':'False predicate'})
        except Exception as exc:checks[name]=False;errors.append({'check':name,'error':str(exc)})
    tok=types.SimpleNamespace(encode=lambda text,**_:types.SimpleNamespace(ids=list(text)))
    check('small_body_unchanged',lambda:split_spans('abc',tok,4)==[(0,3)])
    text='aa\n\nbb\n\ncc'
    check('overlong_complete_paragraphs_only',lambda:split_spans(text,tok,5)==[(0,4),(4,8),(8,10)])
    check('exact_whitespace_reassembly',lambda:''.join(text[x:y] for x,y in split_spans(text,tok,5))==text)
    check('oversize_table_not_cut',lambda:split_spans(text,tok,5,True)==[(0,len(text))])
    check('indivisible_condition_paragraph_not_cut',lambda:split_spans('如果aaa但是bbb',tok,3)==[(0,10)])
    check('bool_limit_rejected',lambda:rejects(lambda:split_spans('abc',tok,True)))
    check('empty_body_rejected',lambda:rejects(lambda:split_spans('',tok,4)))
    check('negative_limit_rejected',lambda:rejects(lambda:split_spans('abc',tok,-1)))
    check('median_and_linear_p95',lambda:distribution([1,2,3,4])['median']==2.5 and abs(distribution([1,2,3,4])['P95']-3.85)<1e-10)
    m={'originals':{'A':{'characters':10,'context_tokens':10,'spans':[{'original_id':'A','start':0,'end':10}]}},
       'children':{'C1':{'parent_id':'P','context_tokens':5,'spans':[{'original_id':'A','start':0,'end':5}]},
                   'C2':{'parent_id':'P','context_tokens':5,'spans':[{'original_id':'A','start':5,'end':10}]}},
       'parents':{'P':{'context_tokens':12,'spans':[{'original_id':'A','start':0,'end':10}]}}}
    rows=[{'context_id':'C1','seed_rank':1},{'context_id':'C2','seed_rank':2}]
    check('partial_child_not_complete_evidence',lambda:ev.coverage(rows[:1],m)[0]==set())
    check('sibling_union_recovers_complete_evidence',lambda:ev.coverage(rows,m)[0]=={'A'})
    check('adjacent_children_no_overlap_redundancy',lambda:ev.coverage(rows,m)[1]['redundancy_rate']==0)
    check('duplicate_context_positions_half_redundant',lambda:ev.coverage([rows[0],rows[0]],m)[1]['redundancy_rate']==.5)
    check('parent_deduplicates_same_law_hits',lambda:ev.contexts(['C1','C2'],'parent_child',m)==[{'context_id':'P','seed_rank':1}])
    check('parent_retains_first_seed_rank',lambda:ev.contexts(['C2','C1'],'parent_child',m)[0]['seed_rank']==1)
    check('budget_skips_whole_parent',lambda:ev.budget_contexts([{'context_id':'P','seed_rank':1}],m,11)['contexts']==[])
    check('budget_no_silent_partial_truncation',lambda:ev.budget_contexts(rows,m,6)['skipped_ids']==['C2'])
    check('budget_exact_boundary_accepted',lambda:len(ev.budget_contexts(rows,m,10)['contexts'])==2)
    check('bool_budget_rejected',lambda:rejects(lambda:ev.budget_contexts(rows,m,True)))
    q=[{'question_id':'SYNTHETIC','answerable':True,'expected_chunk_ids':['A']}];packet={'rankings':{'child':[{'chunk_id':'C1'},{'chunk_id':'C2'}],'base':[{'chunk_id':'A'}]}}
    check('conservative_mrr_waits_for_complete_second_child',lambda:ev.quality(q,[packet],'child',m)['metrics']['MRR@10']==.5)
    check('whole_parent_mrr_one_explicit_expansion',lambda:ev.quality(q,[packet],'parent_child',m)['metrics']['MRR@10']==1.)
    check('no_graded_labels_ndcg_null',lambda:ev.quality(q,[packet],'base',m)['nDCG@10'] is None)
    channels={'dense':[{'chunk_id':'A','rank':1,'score':.8,'distance':.2}],'bm25':[{'chunk_id':'A','rank':1,'score':2.}]}
    check('hand_rrf_two_channels',lambda:abs(ev.fuse(channels,{'A':1})[0]['score']-2/61)<1e-12)
    def bad(channel,field,value):
        copy_=copy.deepcopy(channels);copy_[channel][0][field]=value;return rejects(lambda:ev.fuse(copy_,{'A':1}))
    for channel,field,value,label in [('dense','rank',True,'bool_rank'),('dense','distance',float('nan'),'nan_distance'),
        ('dense','score',float('inf'),'infinite_score'),('dense','score',.7,'distance_score_mismatch'),('bm25','score',0.,'zero_bm25'),('bm25','score',-1.,'negative_bm25'),('dense','chunk_id','UNKNOWN','unknown_id')]:
        check('reject_'+label,lambda c=channel,f=field,v=value:bad(c,f,v))
    check('reject_missing_channel',lambda:rejects(lambda:ev.fuse({'dense':channels['dense']},{'A':1})))
    check('reject_81_candidates',lambda:rejects(lambda:ev.fuse({'dense':channels['dense']*81,'bm25':[]},{'A':1})))
    check('no_bm25_oov_zero_fill',lambda:len(ev.fuse({'dense':channels['dense'],'bm25':[]},{'A':1}))==1)
    temp=ROOT/'.tmp'/('task11-contract-'+uuid.uuid4().hex);temp.mkdir(parents=True)
    existing=temp/'already.json';existing.write_text('{}','utf-8')
    check('existing_report_rejected',lambda:rejects(lambda:output_path(existing)))
    check('outside_report_rejected',lambda:rejects(lambda:output_path(ROOT.parent/'outside.json')))
    check('wrong_split_directory_rejected',lambda:rejects(lambda:run_path(ROOT/'reports/retrieval/elsewhere','test')))
    from run_bm25_retrieval import reserve_test_usage,finish_test_usage
    ledger=temp/'ledger.jsonl';usage={'run_id':'synthetic','template':'synthetic','authorization':None,'run_directory':'.tmp/synthetic','test_sha256':'a'*64,'source_commit':'b'*40}
    reserve_test_usage(ledger,{**usage,'event':'STARTED'})
    check('exclusive_test_reservation_one_winner',lambda:rejects(lambda:reserve_test_usage(ledger,{**usage,'event':'STARTED'})))
    check('wrong_run_cannot_finish',lambda:rejects(lambda:finish_test_usage(ledger,{**usage,'run_id':'other','event':'COMPLETED'})))
    finish_test_usage(ledger,{**usage,'event':'FAILED'})
    check('failure_also_consumes_formal_reservation',lambda:rejects(lambda:finish_test_usage(ledger,{**usage,'event':'COMPLETED'})))
    mapping=ev.mapping();check('all99_source_ids_and_contiguous_children_map',lambda:ev.validate_mapping(mapping))
    def bad_map(mutate):
        value=copy.deepcopy(mapping);mutate(value);return rejects(lambda:ev.validate_mapping(value))
    cid=next(iter(mapping['children']));pid=next(iter(mapping['parents']))
    check('reject_child_gap',lambda:bad_map(lambda v:v['children'][cid]['spans'][0].update(start=1)))
    check('reject_forged_original_source',lambda:bad_map(lambda v:v['originals'][next(iter(v['originals']))]['source'].update(content_zh_sha256='0'*64)))
    check('reject_wrong_parent_members',lambda:bad_map(lambda v:v['parents'][pid]['original_ids'].append('UNKNOWN')))
    check('reject_boolean_body_length',lambda:bad_map(lambda v:v['children'][cid].update(body_tokens=True)))
    if a.dev_dir:
        summary=ev.replay(a.dev_dir)
        check('actual_development_all_methods_recompute',lambda:summary['split']=='dev' and len(summary['methods'])==3)
        check('actual_development40_and32_denominators',lambda:summary['methods']['base']['budgeted']['questions']==40 and summary['methods']['base']['budgeted']['answerable_denominator']==32)
    value={'version':'structure-contract-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,
           'source_sha256':{p:record(ROOT/p)['sha256'] for p in ev.NATIVE},'actual_model_requests':0,'new_test_queries':0,
           'scope':'Synthetic arithmetic/boundaries and metadata copies; optional saved development replay. Not retrieval quality samples.'}
    write_new(out,value);print(json.dumps({k:value[k] for k in ('status','passed','total','errors')}));return 0 if value['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
