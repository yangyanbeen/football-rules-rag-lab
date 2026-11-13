"""Unified Task9 development, frozen test fusion, public replay and actual query."""
from __future__ import annotations
import argparse,json,sys,time,uuid
from pathlib import Path
from eval_dataset import ROOT,EVAL,canonical,digest,load_jsonl
from bm25_index import committed,write_new,record
from bm25_retrieval_eval import now
from run_bm25_retrieval import reserve_test_usage,finish_test_usage,require_release
from hybrid_retrieval_eval import (BASE_DIR,LEDGER,SOURCES,INPUTS,config,snapshots,components,
                                  validate_inputs,validate_grant,replay,summarize,errors_for)
from rrf import fuse,candidates,CHANNELS,SOURCE_FIELDS


def new_report(path):
    path=Path(path).resolve()
    if path.exists() or not path.is_relative_to(ROOT/'reports') or path.suffix!='.json':raise ValueError('Use a new reports JSON')
    return path


def prepare(args):
    release=require_release()
    if LEDGER.exists():raise ValueError('Task9 offline test fusion already reserved; preserve the original run')
    source=committed(SOURCES+INPUTS);dev=Path(args.run_dir).resolve();s=replay(dev)
    if s['split']!='dev':raise ValueError('Complete development evidence required')
    verification=Path(args.verification).resolve();out=new_report(args.output)
    grant={'version':'hybrid-final-report-1.0','purpose':'final_report','used_for_parameter_selection':False,
           'prepared_at':now(),'source_commit':source,'inputs':snapshots(),'config':s['config'],
           'development_manifest':record(dev/'run_manifest.json'),'development_summary':record(dev/'summary.json'),
           'verification':record(verification),'allowed_run_directory':(BASE_DIR/'test').relative_to(ROOT).as_posix(),
           'test_sha256':release['test_lock']['sha256'],'new_channel_retrieval_requests':0}
    validate_grant(grant,BASE_DIR/'test',True);write_new(out,grant)
    print(json.dumps({'status':'OFFLINE_FUSION_REPORT_AUTHORIZED','source_commit':source,'k':s['config']['k']}))


def evaluate(args):
    split=args.mode;out=Path(args.run_dir).resolve();grant=None;auth=None
    if out.exists() or not out.is_relative_to(ROOT/'reports/retrieval'):raise ValueError('Use a new reports/retrieval directory')
    if split=='test':
        if not args.authorization:raise ValueError('Frozen authorization required before test rankings are loaded')
        auth=record(Path(args.authorization));grant=json.loads((ROOT/auth['path']).read_text('utf-8'))
        validate_grant(grant,out,True)
        if LEDGER.exists():raise ValueError('Task9 formal offline fusion already reserved')
        if args.k is not None and args.k!=grant['config']['k']:raise ValueError('Cannot change frozen k')
    require_release();source=committed(SOURCES+INPUTS);inputs=snapshots()
    cfg=grant['config'] if grant else config(args.k)
    if grant and source!=grant['source_commit']:raise ValueError('Execute the frozen fusion source commit')
    run_id=uuid.uuid4().hex;started=now();wall=time.perf_counter();owned=False;reserved=False;phase='reserve';current=None
    start={'version':'hybrid-run-1.0','run_id':run_id,'split':split,'purpose':'development' if split=='dev' else 'final_report',
           'source_commit':source,'inputs':inputs,'config':cfg,'started_at':started,'authorization':auth}
    usage={'run_id':run_id,'run_directory':out.relative_to(ROOT).as_posix(),'template':'rrf-k'+str(cfg['k']),
           'source_commit':source,'authorization':auth,'test_sha256':grant['test_sha256'] if grant else None,
           'scope':'offline rank fusion only','new_channel_retrieval_requests':0}
    try:
        if split=='test':reserve_test_usage(LEDGER,{**usage,'event':'STARTED','recorded_at':now()});reserved=True
        phase='create_directory';out.mkdir(parents=True,exist_ok=False);owned=True
        write_new(out/'run_started.json',start)
        phase='load_original_channels';original=components(split);questions=load_jsonl(EVAL/('retrieval_'+split+'.jsonl'))
        # No question labels or bodies are accepted by the fusion API.
        first=original['dense'][questions[0]['question_id']]['results'][:2]
        toy={'dense':[{**{p:r[p] for p in SOURCE_FIELDS},'rank':i,'score':1.,'distance':0.} for i,r in enumerate(first,1)],
             'bm25':[{**{p:r[p] for p in SOURCE_FIELDS},'rank':i,'score':1.} for i,r in enumerate(first,1)]}
        warmups=[]
        for _ in range(3):
            t=time.perf_counter_ns();fuse(toy,cfg['k'],10);warmups.append((time.perf_counter_ns()-t)/1e9)
        rows=[];phase='fusion'
        with (out/'predictions.jsonl').open('x',encoding='utf-8',newline='\n') as f:
            for q in questions:
                current=q['question_id'];channels={c:original[c][current] for c in CHANNELS}
                packet={c:r['results'] for c,r in channels.items()};measures=[];first_result=None
                for rep in range(1,4):
                    t=time.perf_counter_ns();result=fuse(packet,cfg['k'],10);seconds=(time.perf_counter_ns()-t)/1e9
                    if first_result is not None and canonical(first_result)!=canonical(result):raise ValueError('Unstable repeated fusion')
                    first_result=first_result or result
                    measures.append({'repetition':rep,'fusion_seconds':seconds,'result_sha256':digest(canonical(result))})
                row={'question_id':current,'question_sha256':digest(q['question'].encode()),'split':split,'run_id':run_id,
                     'channels':channels,'results':first_result,'candidate_union':sorted(candidates(packet)),'measurements':measures}
                f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');f.flush();rows.append(row)
        phase='summarize';write_new(out/'summary.json',summarize(questions,rows,cfg,split,run_id))
        write_new(out/'error_analysis.json',errors_for(questions,rows,split));validate_inputs(inputs,source,True)
        manifest={**start,'status':'COMPLETE','completed_at':now(),'wall_seconds':time.perf_counter()-wall,'module_warmups':warmups,
                  'new_channel_retrieval_requests':0,'llm_requests':0,
                  'artifacts':{n:{k:v for k,v in record(out/n).items() if k!='path'} for n in ('predictions.jsonl','summary.json','error_analysis.json','run_started.json')}}
        phase='replay';write_new(out/'run_manifest.json',manifest);checked=replay(out)
        if reserved:finish_test_usage(LEDGER,{**usage,'event':'COMPLETED','recorded_at':now(),'run_manifest':record(out/'run_manifest.json')})
        print(json.dumps({'status':'COMPLETE','split':split,'metrics':{m:r['quality']['metrics'] for m,r in checked['methods'].items()},
                          'rrf_vs_single_channels':checked['rrf_vs_single_channels']},ensure_ascii=False))
    except BaseException as exc:
        failure={'status':'FAILED','run_id':run_id,'split':split,'phase':phase,'question_id':current,'recorded_at':now(),
                 'error_type':type(exc).__name__,'error':str(exc)}
        path=out/'failure.json' if owned else ROOT/'.runtime/task9/failures'/(run_id+'.json')
        actions=[lambda:write_new(path,failure)]
        if reserved:actions.append(lambda:finish_test_usage(LEDGER,{**usage,'event':'FAILED',**failure}))
        for action in actions:
            try:action()
            except Exception as secondary:print('Failure evidence unavailable: '+type(secondary).__name__,file=sys.stderr)
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('dev','prepare-test','test','replay','query'))
    p.add_argument('--run-dir',type=Path);p.add_argument('--k',type=int);p.add_argument('--verification',type=Path)
    p.add_argument('--authorization',type=Path);p.add_argument('--output',type=Path);p.add_argument('--question')
    a=p.parse_args()
    if a.mode=='prepare-test':prepare(a)
    elif a.mode=='replay':
        output=new_report(a.output)
        result=replay(a.run_dir);write_new(output,{'status':'PASS','captured_at':now(),'run_manifest':record(a.run_dir/'run_manifest.json'),'summary':result,'new_channel_retrieval_requests':0});print(json.dumps({'status':'PASS','split':result['split']}))
    elif a.mode=='query':
        from dense_retrieval_eval import normalize_query
        output=new_report(a.output) if a.output else None
        normalize_query(a.question) # reject invalid input before loading a model/index
        cfg=config(a.k)
        from hybrid_live import HybridRetriever
        with HybridRetriever(cfg['k']) as engine:result=engine.query(a.question)
        if output:write_new(output,result)
        print(json.dumps(result,ensure_ascii=False))
    else:evaluate(a)


if __name__=='__main__':main()
