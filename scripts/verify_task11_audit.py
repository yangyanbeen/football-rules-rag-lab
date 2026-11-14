"""Isolated old/current Task11 regression audit; zero model or test queries."""
import argparse,contextlib,copy,io,json,subprocess,sys,types,uuid
from pathlib import Path
from unittest.mock import patch
from eval_dataset import ROOT,EVAL,canonical,digest,load_jsonl
from bm25_index import record,write_new
from bm25_retrieval_eval import now
import structure_aware_chunking as chunk
import structure_retrieval_eval as ev
import structure_retrieval_live as live
import query_parent_child as parent

BASE='e542340ebab150bc4a37a478f9f5e7d05027f52e'
NAMES=('scripts/structure_aware_chunking.py','scripts/structure_retrieval_eval.py','scripts/structure_retrieval_live.py','scripts/run_structure_comparison.py','scripts/query_parent_child.py')


def historic(name):
    module=types.ModuleType('task11_old_'+Path(name).stem);module.__file__=str(ROOT/name)
    exec(compile(subprocess.check_output(['git','show',BASE+':'+name],cwd=ROOT),module.__file__,'exec'),module.__dict__);return module


def rejects(fn):
    try:fn()
    except (ValueError,KeyError,TypeError,FileExistsError):return True
    return False


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--expect-gaps',action='store_true');p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    from run_structure_comparison import output_path
    output=output_path(a.report);temp=ROOT/'.tmp'/('task11-audit-'+uuid.uuid4().hex);temp.mkdir(parents=True)
    target=historic(NAMES[1]) if a.expect_gaps else ev
    tc=historic(NAMES[0]) if a.expect_gaps else chunk;tl=historic(NAMES[2]) if a.expect_gaps else live;tp=historic(NAMES[4]) if a.expect_gaps else parent
    checks={};errors=[];observed={}
    def check(name,fn,gap=False):
        try:
            fixed=bool(fn());checks[name]=(not fixed if a.expect_gaps and gap else fixed)
            observed[name]={'fixed_behavior':fixed,'expected_original_gap':a.expect_gaps and gap}
            if not checks[name]:errors.append({'check':name,'error':'Unexpected behavior'})
        except Exception as exc:checks[name]=False;errors.append({'check':name,'error':str(exc),'type':type(exc).__name__})
    def gap(name,fn):check(name,fn,True)
    for field,value in [('bm25_k1',2.),('tokenizer_model','UNPINNED')]:
        def changed_config(field=field,value=value):
            root=temp/field;(root/'config').mkdir(parents=True);cfg=chunk.config();cfg[field]=value
            (root/chunk.CONFIG).write_bytes(canonical(cfg))
            with patch.object(tc,'ROOT',root):return rejects(tc.config)
        gap('reject_changed_'+field,changed_config)
    m=ev.mapping();first=next(iter(m['originals']))
    def changed_map(change):
        value=copy.deepcopy(m);change(value);return rejects(lambda:target.validate_mapping(value))
    gap('reject_original_span_outside_body',lambda:changed_map(lambda v:v['originals'][first]['spans'][0].update(start=1,end=v['originals'][first]['characters']+1)))
    gap('reject_forged_source_line_range',lambda:changed_map(lambda v:v['originals'][first]['source'].update(source_lines=[1,1])))
    gap('reject_body_hash_different_from_source',lambda:changed_map(lambda v:v['originals'][first].update(content_sha256='0'*64)))
    row={'context_id':first,'seed_rank':1}
    gap('budget_rejects_duplicate_context',lambda:rejects(lambda:target.budget_contexts([row,row],m)))
    questions=load_jsonl(EVAL/'retrieval_dev.jsonl');packets=load_jsonl(ev.DIRECTORY/'dev/predictions.jsonl')
    gap('quality_rejects_silently_truncated_zip',lambda:rejects(lambda:target.quality(questions[:2],packets[:1],'base',m)))
    def cleanup():
        engine=object.__new__(tl.Retriever);engine.close=lambda:(_ for _ in ()).throw(ValueError('SECONDARY_CLEANUP'))
        try:
            with engine:raise RuntimeError('PRIMARY_QUERY')
        except Exception as exc:return type(exc) is RuntimeError and str(exc)=='PRIMARY_QUERY'
    gap('cleanup_preserves_primary_query_error',cleanup)
    def changed_ids():
        index=json.loads((ROOT/ev.INDEX).read_text('utf-8'));index['child_ids'][0],index['child_ids'][1]=index['child_ids'][1],index['child_ids'][0]
        read=Path.read_text
        def text(path,*args,**kwargs):
            if path in (ROOT/ev.INDEX,tl.HOME/'index_manifest.json'):return json.dumps(index)
            return read(path,*args,**kwargs)
        with patch.object(Path,'read_text',text),patch('dense_index.PinnedEmbedder',lambda *_:None):return rejects(tl.Retriever)
    gap('reject_swapped_child_vector_id_order',changed_ids)
    def later_code():
        values=ev.snapshots();values[NAMES[1]]={**values[NAMES[1]],'sha256':'0'*64}
        with patch.object(target,'snapshots',return_value=values):
            try:return target.replay(ev.DIRECTORY/'dev')['split']=='dev'
            except ValueError:return False
    gap('historical_replay_survives_later_installed_code',later_code)
    # A fully isolated development directory; no published evidence is edited.
    fixture=temp/'runs/dev';fixture.mkdir(parents=True)
    saved={n:(ev.DIRECTORY/'dev'/n).read_bytes() for n in (*ev.ARTIFACTS,'run_manifest.json')}
    def bad_run(change):
        manifest=json.loads(saved['run_manifest.json']);start=json.loads(saved['run_started.json']);rows=[json.loads(x) for x in saved['predictions.jsonl'].splitlines()]
        change(manifest,start,rows)
        for name,raw in saved.items():(fixture/name).write_bytes(raw)
        (fixture/'run_started.json').write_bytes(canonical(start)+b'\n');(fixture/'predictions.jsonl').write_bytes(b''.join(canonical(r)+b'\n' for r in rows))
        manifest['artifacts']={n:record(fixture/n) for n in ev.ARTIFACTS};(fixture/'run_manifest.json').write_bytes(canonical(manifest)+b'\n')
        with patch.object(target,'DIRECTORY',fixture.parent),patch.object(target,'snapshots',return_value=manifest['inputs']):return rejects(lambda:target.replay(fixture))
    cases={
      'empty_run_started':lambda m,s,r:s.clear(),
      'boolean_answer_request_count':lambda m,s,r:m.update(answer_llm_requests=False),
      'float_embedding_request_count':lambda m,s,r:m.update(actual_embedding_queries=float(m['actual_embedding_queries'])),
      'unknown_manifest_body_field':lambda m,s,r:m.update(content_zh='SYNTHETIC_EXTRA_FIELD'),
      'float_context_length':lambda m,s,r:m['environment']['embedding_runtime'].update(context_length=8192.),
      'serial_wall_omits_query_duration':lambda m,s,r:[row.update(timing={k:v*1000 for k,v in row['timing'].items()}) for row in r]}
    for name,fn in cases.items():gap('reject_'+name,lambda fn=fn:bad_run(fn))
    def forged_saved_query():
        stored=json.loads((ev.DIRECTORY/'acceptance/actual-query.json').read_text('utf-8'));stored.pop('source_commit');stored['actual_embedding_queries']=True
        src=temp/'forged.json';src.write_bytes(canonical(stored));out=temp/'forged-receipt.json';private=ROOT/'.runtime/task11'/('synthetic-audit-'+uuid.uuid4().hex+'.json')
        evidence={'results':[{'context_id':'SYNTHETIC'}],'context_tokens':1,'skipped_ids':[]}
        with patch.object(sys,'argv',['parent','--replay-packet',str(src),'--receipt',str(out),'--private-output',str(private)]),patch.object(tp,'committed',return_value=BASE),patch.object(tp,'materialize',return_value=evidence),patch('run_structure_comparison.output_path',return_value=out),contextlib.redirect_stdout(io.StringIO()):return rejects(tp.main)
    gap('reject_saved_query_without_producer_and_boolean_count',forged_saved_query)
    check('valid_original_mapping_still_passes',lambda:target.validate_mapping(m))
    check('valid_original_query_ranking_still_passes',lambda:bool(target.summarize(questions[:1],packets[:1],'dev',m)))
    check('valid_budget_boundary_preserved',lambda:target.budget_contexts([row],m,m['originals'][first]['context_tokens'])['contexts']==[row])
    check('empty_coverage_remains_zero',lambda:target.coverage([],m)[1]['redundancy_rate']==0)
    if not a.expect_gaps:
        def bad_coverage():
            value=copy.deepcopy(m);value['originals'][first]['spans'][0]['end']+=1
            return rejects(lambda:ev.coverage([row],value))
        check('coverage_rejects_out_of_body_span',bad_coverage)
        def bad_tokens():
            value=copy.deepcopy(m);value['originals'][first]['context_tokens']=True
            return rejects(lambda:ev.budget_contexts([row],value))
        check('budget_rejects_boolean_context_tokens',bad_tokens)
        check('budget_rejects_boolean_seed_rank',lambda:rejects(lambda:ev.budget_contexts([{**row,'seed_rank':True}],m)))
        child=next(iter(m['children']))
        check('contexts_reject_duplicate_seeds',lambda:rejects(lambda:ev.contexts([child,child],'child',m)))
        check('quality_rejects_duplicate_question_ids',lambda:rejects(lambda:ev.quality([questions[0],questions[0]],[packets[0],packets[0]],'base',m)))
        raw=(ev.DIRECTORY/'acceptance/actual-query.json').read_bytes()
        check('exact_legacy_query_receipt_still_valid',lambda:ev.validate_saved_query(json.loads(raw),raw))
        check('legacy_query_with_extra_whitespace_rejected',lambda:rejects(lambda:ev.validate_saved_query(json.loads(raw),raw+b'\n')))
        idx=json.loads((ROOT/ev.INDEX).read_text('utf-8'))
        check('original_index_layout_still_valid',lambda:live.validate_layout(idx,m,idx['base_ids']) is None)
        def wrong_reuse():
            value=copy.deepcopy(idx);value['reused_unchanged_child_vectors']=True
            return rejects(lambda:live.validate_layout(value,m,idx['base_ids']))
        check('index_rejects_boolean_reuse_count',wrong_reuse)
        def wrong_lexical():
            path=live.HOME/'lexical.json';read=Path.read_text;payload=json.loads(read(path,'utf-8'));payload['child']['avgdl']+=1
            def text(p,*args,**kwargs):return json.dumps(payload) if p==path else read(p,*args,**kwargs)
            with patch.object(Path,'read_text',text),patch('dense_index.PinnedEmbedder',lambda *_:None):return rejects(live.Retriever)
        check('actual_lexical_payload_recomputed_before_model_access',wrong_lexical)
        def all_sources_preflight():
            names=[]
            def reject_source(values):names.extend(values);raise ValueError('SYNTHETIC_UNCOMMITTED')
            with patch.object(sys,'argv',['parent','--question','Synthetic preflight','--private-output',str(ROOT/'.runtime/task11'/('preflight-'+uuid.uuid4().hex+'.json')),'--receipt',str(temp/'none.json')]),patch('run_structure_comparison.output_path',return_value=temp/'none.json'),patch.object(parent,'committed',side_effect=reject_source):
                return rejects(parent.main) and set(ev.SOURCES+ev.INPUTS+('scripts/query_parent_child.py',))<=set(names)
        check('parent_query_preflights_all_execution_sources',all_sources_preflight)
    value={'version':'task11-audit-regressions-1.0','captured_at':now(),'baseline':BASE,'expected_original_gaps':a.expect_gaps,
           'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'observed':observed,
           'source_sha256':{p:record(ROOT/p)['sha256'] for p in NAMES+('scripts/verify_task11_audit.py',)},
           'new_model_requests':0,'new_test_queries':0,'scope':'Synthetic inputs, in-memory index/config mutations and rehashed temporary dev copies; mocked service, no model inference or changed original evidence.'}
    write_new(output,value);print(json.dumps({k:value[k] for k in ('status','passed','total','errors')}));return 0 if value['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
