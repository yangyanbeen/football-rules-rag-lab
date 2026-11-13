"""Build-time independent controls, development and one frozen final test matrix."""
import argparse,json,sys,time,uuid
from pathlib import Path
from eval_dataset import ROOT,EVAL,canonical,digest,load_jsonl
from bm25_index import record,write_new,committed
from bm25_retrieval_eval import now
from run_bm25_retrieval import require_release,reserve_test_usage,finish_test_usage
from structure_aware_chunking import config
from structure_retrieval_eval import (DIRECTORY,LEDGER,SOURCES,INPUTS,ARTIFACTS,snapshots,mapping,
                                      summarize,errors,replay,validate_grant)


def output_path(value):
    if value is None:raise ValueError('Output is required')
    path=Path(value).resolve()
    if not path.is_relative_to(ROOT/'reports') or path.exists() or path.suffix!='.json':raise ValueError('Use a new report JSON')
    return path


def run_path(value,split):
    if value is None:raise ValueError('Run directory is required')
    path=Path(value).resolve()
    if path.exists() or path.parent!=DIRECTORY or (path.name!='test' if split=='test' else not path.name.startswith('dev')):raise ValueError('Use a fresh task11 split directory')
    return path


def prepare(args):
    output=output_path(args.output)
    if LEDGER.exists():raise ValueError('Task11 formal test is already consumed')
    require_release();source=committed(SOURCES+INPUTS);dev=Path(args.run_dir).resolve();s=replay(dev)
    if s['split']!='dev':raise ValueError('Need development first')
    committed(tuple(p.relative_to(ROOT).as_posix() for p in (dev/'run_manifest.json',dev/'summary.json',Path(args.verification).resolve())),source)
    grant={'version':'structure-test-grant-1.0','purpose':'final_report','prepared_at':now(),'source_commit':source,
           'inputs':snapshots(),'development_manifest':record(dev/'run_manifest.json'),'development_summary':record(dev/'summary.json'),
           'verification':record(args.verification),'selected_method':s['selected_on_this_split'],
           'allowed_run_directory':(DIRECTORY/'test').relative_to(ROOT).as_posix(),'test_sha256':digest((EVAL/'retrieval_test.jsonl').read_bytes())}
    validate_grant(grant,DIRECTORY/'test',True);write_new(output,grant)
    print(json.dumps({'status':'FROZEN_TEST_AUTHORIZED','selected_on_dev':grant['selected_method'],'source_commit':source}))


def evaluate(args):
    split=args.mode;out=run_path(args.run_dir,split);grant=None;authorization=None
    if split=='test':
        if args.authorization is None or LEDGER.exists():raise ValueError('One unused frozen authorization required')
        authorization=record(args.authorization);grant=json.loads((ROOT/authorization['path']).read_text('utf-8'));validate_grant(grant,out,True)
    require_release();source=committed(SOURCES+INPUTS,grant['source_commit'] if grant else None);inputs=snapshots()
    run_id=uuid.uuid4().hex;started=now();wall=time.perf_counter();owned=False;reserved=False;phase='reserve';qid=None
    start={'version':'structure-run-1.0','split':split,'run_id':run_id,'source_commit':source,'inputs':inputs,
           'config':config(),'started_at':started,'authorization':authorization,'purpose':'development' if split=='dev' else 'final_report'}
    usage={'run_id':run_id,'run_directory':out.relative_to(ROOT).as_posix(),'source_commit':source,'authorization':authorization,
           'template':'structure-base-child-parent-matrix','test_sha256':grant['test_sha256'] if grant else None}
    try:
        if split=='test':reserve_test_usage(LEDGER,{**usage,'event':'STARTED','recorded_at':now()});reserved=True
        out.mkdir(parents=True,exist_ok=False);owned=True;write_new(out/'run_started.json',start)
        phase='load_questions';questions=load_jsonl(EVAL/('retrieval_'+split+'.jsonl'))
        queries=[{k:q[k] for k in ('question_id','question')} for q in questions]
        from structure_retrieval_live import Retriever,files
        phase='load_index'
        with Retriever() as engine:
            before=files();warmups=[engine.query(config()['warmup_question']) for _ in range(3)];environment=engine.environment()
            rows=[];phase='measure'
            with (out/'predictions.jsonl').open('x',encoding='utf-8',newline='\n') as f:
                for q in queries:
                    qid=q['question_id'];packet=engine.query(q['question'],qid);rows.append(packet)
                    f.write(canonical(packet).decode()+'\n');f.flush();print(json.dumps({'progress':len(rows),'total':len(queries),'question_id':qid}),flush=True)
        after=files();phase='score';summary=summarize(questions,rows,split,mapping())
        write_new(out/'summary.json',summary);write_new(out/'error_analysis.json',errors(summary))
        if inputs!=snapshots():raise ValueError('Inputs changed during run')
        value={**start,'status':'COMPLETE','completed_at':now(),'wall_seconds':time.perf_counter()-wall,
               'environment':environment,'warmups':warmups,'index_snapshots':{'before':before,'after':after},
               'actual_embedding_queries':len(rows)+3,'answer_llm_requests':0,
               'artifacts':{name:record(out/name) for name in ARTIFACTS}}
        write_new(out/'run_manifest.json',value);phase='replay';replay(out)
        if reserved:finish_test_usage(LEDGER,{**usage,'event':'COMPLETED','recorded_at':now(),'run_manifest':record(out/'run_manifest.json')})
        print(json.dumps({'status':'COMPLETE','split':split,'selected_on_this_split':summary['selected_on_this_split'],
                          'metrics':{m:r['budgeted']['metrics'] for m,r in summary['methods'].items()}}))
    except BaseException as exc:
        failure={'status':'FAILED','run_id':run_id,'split':split,'phase':phase,'question_id':qid,'recorded_at':now(),'error_type':type(exc).__name__,'error':str(exc)}
        actions=[lambda:write_new(out/'failure.json' if owned else ROOT/'.runtime/task11/failures'/(run_id+'.json'),failure)]
        if reserved:actions.append(lambda:finish_test_usage(LEDGER,{**usage,'event':'FAILED',**failure}))
        for action in actions:
            try:action()
            except BaseException as secondary:print('Secondary failure recording error: '+type(secondary).__name__,file=sys.stderr)
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('dev','prepare-test','test','replay','query'))
    p.add_argument('--run-dir',type=Path);p.add_argument('--authorization',type=Path);p.add_argument('--verification',type=Path);p.add_argument('--output',type=Path);p.add_argument('--question');a=p.parse_args()
    if a.mode=='prepare-test':prepare(a)
    elif a.mode=='replay':
        out=output_path(a.output) if a.output else None;s=replay(a.run_dir)
        if out:write_new(out,{'status':'PASS','summary':s,'new_model_requests':0})
        print(json.dumps({'status':'PASS','split':s['split']}))
    elif a.mode=='query':
        out=output_path(a.output)
        source=committed(SOURCES+INPUTS)
        from dense_retrieval_eval import normalize_query
        normalize_query(a.question)
        from structure_retrieval_live import Retriever
        with Retriever() as engine:packet=engine.query(a.question,'ad-hoc')
        write_new(out,{'source_commit':source,'packet':packet,'actual_embedding_queries':1,'answer_llm_requests':0,'is_quality_evaluation':False})
    else:evaluate(a)


if __name__=='__main__':main()
