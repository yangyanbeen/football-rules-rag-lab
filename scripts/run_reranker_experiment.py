"""Task10 actual dev/frozen test matrix, public replay and ad-hoc retrieval."""
from __future__ import annotations
import argparse,json,sys,time,uuid
from pathlib import Path
from eval_dataset import ROOT,EVAL,canonical,digest,load_jsonl
from bm25_index import record,write_new,committed
from bm25_retrieval_eval import now
from run_bm25_retrieval import require_release,reserve_test_usage,finish_test_usage
from reranker_eval import (DIRECTORY,LEDGER,METHODS,SOURCES,INPUTS,ARTIFACTS,config,snapshots,
                           validate_inputs,validate_grant,replay,summarize,errors_for)


def new_report(value):
    p=Path(value).resolve()
    if p.exists() or not p.is_relative_to(ROOT/'reports') or p.suffix!='.json':raise ValueError('Use new reports JSON')
    return p


def run_path(value):
    p=Path(value).resolve()
    if p.exists() or not p.is_relative_to(ROOT/'reports/retrieval'):raise ValueError('Use a new reports/retrieval directory')
    return p


def prepare(args):
    require_release()
    if LEDGER.exists():raise ValueError('Task10 test is already reserved; never repeat the formal run')
    cfg=config();source=committed(SOURCES+INPUTS);dev=Path(args.run_dir).resolve();summary=replay(dev)
    if summary['split']!='dev':raise ValueError('Development must complete first')
    out=new_report(args.output);verification=Path(args.verification).resolve()
    grant={'version':'reranker-final-report-1.0','purpose':'final_report','used_for_parameter_selection':False,
           'prepared_at':now(),'source_commit':source,'inputs':snapshots(),'config':cfg,
           'development_manifest':record(dev/'run_manifest.json'),'development_summary':record(dev/'summary.json'),
           'verification':record(verification),'selected_method':summary['selected_on_this_split'],
           'allowed_run_directory':(DIRECTORY/'test').relative_to(ROOT).as_posix(),
           'test_sha256':digest((EVAL/'retrieval_test.jsonl').read_bytes())}
    validate_grant(grant,DIRECTORY/'test',True);write_new(out,grant)
    print(json.dumps({'status':'TEST_MATRIX_AUTHORIZED','selected_on_dev':grant['selected_method'],'source_commit':source}))


def evaluate(args):
    split=args.mode;out=run_path(args.run_dir);grant=None;auth=None
    if split=='test':
        if not args.authorization:raise ValueError('Test needs frozen development authorization')
        auth=record(args.authorization);grant=json.loads((ROOT/auth['path']).read_text('utf-8'));validate_grant(grant,out,True)
        if LEDGER.exists():raise ValueError('Task10 formal test already started')
    require_release();cfg=config();source=committed(SOURCES+INPUTS);inputs=snapshots()
    if grant and source!=grant['source_commit']:raise ValueError('Test must execute its frozen source commit')
    run_id=uuid.uuid4().hex;started=now();wall=time.perf_counter();owned=False;reserved=False;phase='reserve';current=None
    start={'version':'reranker-run-1.1','run_id':run_id,'split':split,'purpose':'development' if split=='dev' else 'final_report',
           'source_commit':source,'inputs':inputs,'config':cfg,'started_at':started,'authorization':auth}
    usage={'run_id':run_id,'run_directory':out.relative_to(ROOT).as_posix(),'template':'bge-top20-40-80-matrix',
           'source_commit':source,'authorization':auth,'test_sha256':grant['test_sha256'] if grant else None}
    try:
        if split=='test':reserve_test_usage(LEDGER,{**usage,'event':'STARTED','recorded_at':now()});reserved=True
        phase='create_directory';out.mkdir(parents=True,exist_ok=False);owned=True;write_new(out/'run_started.json',start)
        phase='load_questions';questions=load_jsonl(EVAL/('retrieval_'+split+'.jsonl'))
        # Retrieval receives question text only, never answerability, support IDs or negative labels.
        queries=[{k:q[k] for k in ('question_id','question')} for q in questions]
        from reranker_live import RerankerRetriever
        from hybrid_live import index_files
        phase='load_models';loading=time.perf_counter()
        with RerankerRetriever(cfg) as engine:
            load_seconds=time.perf_counter()-loading;before=engine.before
            source_map=json.loads((ROOT/'reports/retrieval/dense_b0/dev/source_map.json').read_text('utf-8'))
            write_new(out/'source_map.json',source_map)
            warmups={m:[] for m in METHODS};phase='warmup'
            for m in METHODS:
                for _ in range(cfg['warmup_repetitions']):warmups[m].append(engine.query(cfg['warmup_question'],m))
            phase='capture_environment';environment=engine.environment()
            rows=[];phase='measure'
            with (out/'predictions.jsonl').open('x',encoding='utf-8',newline='\n') as f:
                for i,q in enumerate(queries):
                    current=q['question_id'];order=METHODS[i%4:]+METHODS[:i%4];packets={}
                    for m in order:packets[m]=engine.query(q['question'],m)
                    row={'question_id':current,'question_sha256':digest(q['question'].encode()),'run_id':run_id,
                         'split':split,'order':list(order),'variants':packets}
                    f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');f.flush();rows.append(row)
                    print(json.dumps({'progress':i+1,'total':len(queries),'question_id':current,
                                      'chain_seconds':{m:round(packets[m]['timing']['total_seconds'],3) for m in METHODS}}),flush=True)
        after=index_files();phase='summarize'
        write_new(out/'summary.json',summarize(questions,rows,split));write_new(out/'error_analysis.json',errors_for(questions,rows,split,include_partial=True))
        validate_inputs(inputs,source,True)
        manifest={**start,'status':'COMPLETE','completed_at':now(),'wall_seconds':time.perf_counter()-wall,
                  'environment':environment,'load_seconds':load_seconds,'warmups':warmups,
                  'index_snapshots':{'before':before,'after':after},
                  'artifacts':{n:{k:v for k,v in record(out/n).items() if k!='path'} for n in ARTIFACTS}}
        phase='replay';write_new(out/'run_manifest.json',manifest);checked=replay(out)
        if reserved:finish_test_usage(LEDGER,{**usage,'event':'COMPLETED','recorded_at':now(),'run_manifest':record(out/'run_manifest.json')})
        print(json.dumps({'status':'COMPLETE','split':split,'selected_on_this_split':checked['selected_on_this_split'],
                          'metrics':{m:r['quality']['metrics'] for m,r in checked['methods'].items()}},ensure_ascii=False))
    except BaseException as exc:
        failure={'status':'FAILED','run_id':run_id,'split':split,'phase':phase,'question_id':current,'recorded_at':now(),
                 'error_type':type(exc).__name__,'error':str(exc)}
        actions=[lambda:write_new(out/'failure.json' if owned else ROOT/'.runtime/task10/failures'/(run_id+'.json'),failure)]
        if reserved:actions.append(lambda:finish_test_usage(LEDGER,{**usage,'event':'FAILED',**failure}))
        for action in actions:
            try:action()
            except BaseException as secondary:print('Secondary failure recording error: '+type(secondary).__name__,file=sys.stderr)
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('dev','prepare-test','test','replay','query'))
    p.add_argument('--run-dir',type=Path);p.add_argument('--authorization',type=Path);p.add_argument('--verification',type=Path)
    p.add_argument('--output',type=Path);p.add_argument('--question');p.add_argument('--method',choices=METHODS,default='top20');a=p.parse_args()
    if a.mode=='prepare-test':prepare(a)
    elif a.mode=='replay':
        output=new_report(a.output) if a.output else None
        result=replay(a.run_dir)
        if output:write_new(output,{'status':'PASS','captured_at':now(),'run_manifest':record(a.run_dir/'run_manifest.json'),'summary':result,'new_model_requests':0})
        print(json.dumps({'status':'PASS','split':result['split']}))
    elif a.mode=='query':
        output=new_report(a.output) if a.output else None
        from dense_retrieval_eval import normalize_query
        normalize_query(a.question)
        from reranker_live import RerankerRetriever
        with RerankerRetriever(config()) as engine:result=engine.query(a.question,a.method)
        if output:write_new(output,result)
        print(json.dumps(result,ensure_ascii=False))
    else:evaluate(a)


if __name__=='__main__':main()
