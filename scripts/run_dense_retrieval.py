"""Measure fixed dense retrieval; develop first and authorize locked-test reporting."""
from __future__ import annotations
import argparse, importlib.metadata, json, os, platform, subprocess, sys, time, uuid
from datetime import datetime,timezone
from pathlib import Path
from eval_dataset import ROOT,EVAL,CORPUS,digest,load_jsonl,write_json
from dense_retrieval_eval import (CONFIG,SOURCES,SOURCE_FIELDS,load_config,normalize_query,snapshots,
 require_matching_snapshots,require_committed_sources,file_record,replay,summarize)
from run_retrieval_metrics import authorize_test
from validate_eval_dataset import validate
from validate_eval_receipt import require_receipt
import dense_retrieval_contracts as contracts


def now():return datetime.now(timezone.utc).isoformat()


def new_report(path):
    path=Path(path).resolve()
    if not path.is_relative_to(ROOT/'reports') or path.suffix!='.json' or path.exists():
        raise ValueError('Use a new JSON report inside reports/')
    return path


def require_original_release():
    require_receipt()
    result=validate(phase='delivery')
    if result['status']!='PASS' or result['human_review']['approved']!=90:
        raise ValueError('Original task4 full human-reviewed delivery gate must pass')
    return json.loads((EVAL/'dataset_manifest.json').read_text('utf-8'))


def prepare_test(args):
    release=require_original_release();cfg=load_config()
    development=Path(args.development_run).resolve()
    summary=replay(development)
    if summary['split']!='dev' or summary['quality']['questions']!=40:raise ValueError('Complete development run required')
    gates=[]
    for path in (args.arithmetic_report,args.contract_report):
        value=json.loads(Path(path).read_text('utf-8'))
        if value['status']!='PASS':raise ValueError('Development verification failed')
        outcomes=value['checks']
        passed=list(outcomes.values()) if isinstance(outcomes,dict) else [r['passed'] for r in outcomes]
        if not passed or not all(x is True for x in passed):raise ValueError('Incomplete development verification checks')
        gates.append(file_record(path))
    contract=json.loads(Path(args.contract_report).read_text('utf-8'))
    if contract.get('source_sha256',{}).get('dense_retrieval_eval.py')!=digest((ROOT/'scripts/dense_retrieval_eval.py').read_bytes()):
        raise ValueError('Contract verification does not match current evaluation implementation')
    for path,names in ((args.arithmetic_report,('verify_dense_metric_arithmetic.py','retrieval_metrics.py')),
                       (args.contract_report,('verify_dense_retrieval_contract.py','dense_retrieval_eval.py'))):
        hashes=json.loads(Path(path).read_text('utf-8')).get('source_sha256',{})
        if any(hashes.get(n)!=digest((ROOT/'scripts'/n).read_bytes()) for n in names):
            raise ValueError('Verification report producer/source hash differs')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    require_committed_sources(commit)
    list(contracts.verification_receipts(gates,commit,file_record))
    output=new_report(args.authorization)
    run_dir=Path(args.run_dir).resolve()
    if not run_dir.is_relative_to(ROOT/'reports/retrieval') or run_dir.exists():raise ValueError('Test run must use a new reports/retrieval directory')
    ticket={'authorization_version':'dense-final-report-1.0','prepared_at':now(),'purpose':'final_report',
      'used_for_parameter_selection':False,'dataset_version':release['dataset_version'],
      'test_sha256':release['test_lock']['sha256'],'test_locked_at':release['test_lock'].get('locked_at'),
      'config_sha256':digest(CONFIG.read_bytes()),'config':cfg,'source_commit':commit,'input_snapshots':snapshots(),
      'development_manifest':file_record(development/'run_manifest.json'),'development_summary':file_record(development/'summary.json'),
      'development_verification':gates,'allowed_run_directory':run_dir.relative_to(ROOT).as_posix(),
      'formal_test_parameter_choices':'None; original model/index and preregistered measurement policy unchanged',
      'original_dataset_manifest_not_modified':True}
    authorize_test(release,'final_report',ticket,CONFIG.read_bytes())
    write_json(output,ticket)
    print(json.dumps({'status':'TEST_REPORT_AUTHORIZED','source_commit':commit,'authorization':output.relative_to(ROOT).as_posix()}))


def append_usage(path,event):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8',newline='\n') as handle:
        handle.write(json.dumps(event,ensure_ascii=False,allow_nan=False)+'\n')


def persist_failure(output,ledger,usage,split,run_id,request,exc):
    failure={'status':'FAILED','run_id':run_id,'split':split,'recorded_at':now(),'request':request,
             'error':type(exc).__name__+': '+str(exc)}
    # A disk/permission failure may affect one channel; attempt both without
    # replacing the original exception. Never claim durable recording if both fail.
    actions=[lambda:write_json(output/'failure.json',failure)]
    if split=='test':actions.append(lambda:append_usage(ledger,{**usage,'event':'FAILED',**failure}))
    for action in actions:
        try:action()
        except Exception as secondary:print('Failure evidence channel unavailable: '+type(secondary).__name__,file=sys.stderr)


def evaluate(args):
    cfg=load_config();release=require_original_release();split=args.mode
    output=Path(args.run_dir).resolve()
    if not output.is_relative_to(ROOT/'reports/retrieval') or output.exists():
        raise ValueError('Use a new directory under reports/retrieval; preserve previous attempts')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    require_committed_sources(commit)
    before=snapshots();ticket=None
    if split=='test':
        if not args.authorization:raise ValueError('Locked test requires a preregistered authorization')
        ticket=json.loads(Path(args.authorization).read_text('utf-8'))
        contracts.grant_metadata(ticket,release,cfg,digest(CONFIG.read_bytes()),output.relative_to(ROOT).as_posix())
        authorize_test(release,'final_report',ticket,CONFIG.read_bytes())
        require_matching_snapshots(ticket['input_snapshots']);require_committed_sources(ticket['source_commit'])
        if ticket['config']!=cfg or ticket['allowed_run_directory']!=output.relative_to(ROOT).as_posix():
            raise ValueError('Authorized configuration/run directory differs')
        for record in [ticket['development_manifest'],ticket['development_summary']]+ticket['development_verification']:
            if file_record(ROOT/record['path'])!=record:raise ValueError('Development evidence changed since test authorization')
        devdir=(ROOT/ticket['development_manifest']['path']).resolve().parent
        if replay(devdir)['split']!='dev':raise ValueError('Authorized development run is invalid')
        devmanifest=json.loads((devdir/'run_manifest.json').read_text('utf-8'))
        if contracts.instant(devmanifest['completed_at'])>contracts.instant(ticket['prepared_at']):raise ValueError('Development postdates authorization')
        for receipt in contracts.verification_receipts(ticket['development_verification'],ticket['source_commit'],file_record):
            stamp=next((receipt[k] for k in ('generated_at','checked_at','captured_at') if k in receipt),None)
            if contracts.instant(stamp)>contracts.instant(ticket['prepared_at']):raise ValueError('Verification postdates authorization')
        commit=ticket['source_commit']
    # Only these two fields cross into the retrieval loop. Gold is scored later.
    labelled=load_jsonl(EVAL/f'retrieval_{split}.jsonl')
    queries=[{'question_id':q['question_id'],'question':q['question']} for q in labelled]
    if len(queries)!=(40 if split=='dev' else 50):raise ValueError('Unexpected fixed split size')
    run_id=uuid.uuid4().hex;started_at=now();whole_started=time.perf_counter()
    output.mkdir(parents=True)
    ledger=output.parent/'test_usage.jsonl'
    usage={'run_id':run_id,'run_directory':output.relative_to(ROOT).as_posix(),'split':split,'purpose':'final_report',
      'used_for_parameter_selection':False,'source_commit':commit,'config_sha256':digest(CONFIG.read_bytes()),
      'test_sha256':release['test_lock']['sha256']}
    index=None;current_request=None
    try:
        if split=='test':
            usage['authorization']=file_record(args.authorization)
            append_usage(ledger,{**usage,'event':'STARTED','recorded_at':now()})
        write_json(output/'run_started.json',{'run_id':run_id,'started_at':started_at,'split':split,
          'source_commit':commit,'input_snapshots':before,'authorization':file_record(args.authorization) if ticket else None})
        from dense_index import DenseIndex,PinnedEmbedder,inventory
        original_artifacts={**inventory(ROOT/cfg['dense_index']),
                            'index_manifest.json':file_record(ROOT/cfg['dense_index']/'index_manifest.json')}
        startup=time.perf_counter()
        embedder=PinnedEmbedder(json.loads((ROOT/cfg['dense_config']).read_text('utf-8')))
        index=DenseIndex(ROOT/cfg['dense_index'],ROOT/cfg['dense_config'],embedder=embedder)
        startup_seconds=time.perf_counter()-startup
        source_map=[{k:r[k] for k in SOURCE_FIELDS} for r in index.rows]
        write_json(output/'source_map.json',source_map)
        warmups=[]
        for rep in range(1,cfg['warmup_repetitions']+1):
            began=time.perf_counter_ns();r=index.query(normalize_query(cfg['warmup_query']),cfg['top_k'])
            warmups.append({'repetition':rep,'query':cfg['warmup_query'],'timing':r['timing'],
                            'total_seconds':(time.perf_counter_ns()-began)/1e9})
        cpu_runtime=embedder.runtime();predictions=[]
        with (output/'predictions.jsonl').open('x',encoding='utf-8',newline='\n') as handle, (output/'requests.jsonl').open('x',encoding='utf-8',newline='\n') as journal:
            for q in queries:
                measurements=[];first_results=None
                for rep in range(1,cfg['measured_repetitions']+1):
                    current_request={'question_id':q['question_id'],'repetition':rep,'stage':'query'}
                    began=time.perf_counter_ns();query=normalize_query(q['question'])
                    normalization_seconds=(time.perf_counter_ns()-began)/1e9
                    r=index.query(query,cfg['top_k'])
                    total_seconds=(time.perf_counter_ns()-began)/1e9
                    measurements.append({'repetition':rep,'normalization_seconds':normalization_seconds,
                      **r['timing'],'total_seconds':total_seconds,'ranked_ids':[m['chunk_id'] for m in r['results']],
                      'distances':[m['distance'] for m in r['results']],'scores':[m['score'] for m in r['results']],
                      'embedding_observation':dict(embedder.observations[-1])})
                    journal.write(json.dumps({'question_id':q['question_id'],'query':query,'run_id':run_id,
                      'split':split,'measurement':measurements[-1]},ensure_ascii=False,allow_nan=False)+'\n');journal.flush()
                    if rep==1:first_results=[{**{k:m['metadata'][k] for k in SOURCE_FIELDS},
                      **{k:m[k] for k in ('rank','distance','score')}} for m in r['results']]
                row={'question_id':q['question_id'],'question_sha256':digest(q['question'].encode('utf-8')),
                  'query':query,'split':split,'run_id':run_id,'results':first_results,'measurements':measurements}
                handle.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');handle.flush();predictions.append(row)
        cpu_runtime_after=embedder.runtime()
        if snapshots()!=before or digest(CORPUS.read_bytes())!=index.cfg['corpus_sha256']:
            raise ValueError('Data/code/config changed during measurement')
        index_manifest=json.loads((index.path/'index_manifest.json').read_text('utf-8'))
        index.close();index=None
        if original_artifacts!={**inventory(ROOT/cfg['dense_index']),'index_manifest.json':file_record(ROOT/cfg['dense_index']/'index_manifest.json')}:
            raise ValueError('Formal dense index artifacts changed during read-only open/query/close')
        summary=summarize(labelled,predictions,cfg,source_map,split,run_id)
        write_json(output/'summary.json',summary);write_json(output/'error_analysis.json',summary['error_analysis'])
        manifest={'manifest_version':'dense-retrieval-run-1.0','status':'COMPLETE','run_id':run_id,'split':split,
          'purpose':'development' if split=='dev' else 'final_report','used_for_parameter_selection':False,
          'started_at':started_at,'completed_at':now(),'source_commit':commit,'config':cfg,'input_snapshots':before,
          'dataset_version':release['dataset_version'],'corpus_version':index_manifest['config']['corpus_version'],
          'corpus_sha256':index_manifest['config']['corpus_sha256'],'index_manifest_sha256':original_artifacts['index_manifest.json']['sha256'],
          'index_version':index_manifest['index_version'],'index_vector_fingerprint':index_manifest['vector_fingerprint'],
          'index_producer_implementation_sha256':index_manifest['implementation_sha256'],
          'model_artifact':embedder.model_info,'model_runtime_before':cpu_runtime,'model_runtime_after':cpu_runtime_after,
          'environment':{'python':platform.python_version(),'platform':platform.platform(),'processor':platform.processor(),
            'logical_cpus':os.cpu_count(),'packages':{p:importlib.metadata.version(p) for p in ('numpy','chromadb','chroma-hnswlib')}},
          'startup_loading_seconds':startup_seconds,'warmups':warmups,'whole_run_wall_seconds':time.perf_counter()-whole_started,
          'query_request_count':len(queries)*cfg['measured_repetitions'],'warmup_request_count':len(warmups),
          'llm_generation_requests':0,'gold_passed_to_retrieval':False,'formal_index_artifacts_unchanged':True,
          'authorization':file_record(args.authorization) if ticket else None,
          'artifacts':{name:file_record(output/name) for name in ('predictions.jsonl','requests.jsonl','run_started.json','source_map.json','summary.json','error_analysis.json')},
          'scope':'Real fixed dense retrieval only; public predictions contain no corpus bodies/vectors/answers'}
        write_json(output/'run_manifest.json',manifest)
        replay(output)
        if split=='test':append_usage(ledger,{**usage,'event':'COMPLETED','recorded_at':now(),
          'run_manifest':file_record(output/'run_manifest.json')})
        print(json.dumps({'status':'COMPLETE','split':split,'questions':len(predictions),
          'metrics':summary['quality']['metrics'],'latency_samples':summary['latency']['samples'],
          'latency_total_ms':summary['latency']['stages']['total_seconds']},ensure_ascii=False))
    except BaseException as exc:
        persist_failure(output,ledger,usage,split,run_id,current_request,exc)
        raise
    finally:
        if index is not None:
            primary_active=sys.exc_info()[0] is not None
            try:index.close()
            except Exception as cleanup:
                if primary_active:print('Index cleanup also failed: '+type(cleanup).__name__,file=sys.stderr)
                else:
                    persist_failure(output,ledger,usage,split,run_id,current_request,cleanup)
                    raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('dev','prepare-test','test'),required=True)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--authorization',type=Path)
    parser.add_argument('--development-run',type=Path)
    parser.add_argument('--arithmetic-report',type=Path)
    parser.add_argument('--contract-report',type=Path)
    args=parser.parse_args()
    if args.mode=='prepare-test':
        if not all((args.authorization,args.development_run,args.arithmetic_report,args.contract_report)):
            parser.error('prepare-test requires authorization, development-run, arithmetic-report and contract-report')
        prepare_test(args)
    else:evaluate(args)
    return 0

if __name__=='__main__':raise SystemExit(main())
