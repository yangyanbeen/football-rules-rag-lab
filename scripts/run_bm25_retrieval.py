"""Measure three development templates, freeze selection, then report one locked test."""
from __future__ import annotations
import argparse,json,os,platform,sys,time,uuid
from pathlib import Path
from bm25_index import ROOT,CONFIG,RESOURCES,TEMPLATES,TIMINGS,Bm25Index,config,record,write_new,committed
from bm25_retrieval_eval import (V1_EXECUTION_FILES,now,instant,snapshots,require_inputs,replay,
                                summary,error_analysis,choose,validate_grant)
from eval_dataset import EVAL,digest,load_jsonl
from run_retrieval_metrics import authorize_test
from validate_eval_dataset import validate
from validate_eval_receipt import require_receipt

LEDGER=ROOT/'reports/retrieval/bm25_b0/test_usage.jsonl'


def report_path(value):
    path=Path(value).resolve()
    if path.exists() or path.suffix!='.json' or not path.is_relative_to(ROOT/'reports'):raise ValueError('Use a new JSON under reports/')
    return path


def require_release():
    require_receipt();result=validate(phase='delivery')
    if result['status']!='PASS' or result['human_review']['approved']!=90:raise ValueError('Original full human release required')
    return json.loads((EVAL/'dataset_manifest.json').read_text('utf-8'))


def append(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8',newline='\n') as f:f.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n');f.flush()


def reserve_test_usage(path,value):
    """Exclusive creation prevents two authorized processes starting one test."""
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8',newline='\n') as f:
        f.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())


def finish_test_usage(path,value):
    rows=load_jsonl(path)
    identity=('run_id','template','authorization','run_directory','test_sha256','source_commit')
    if (len(rows)!=1 or rows[0].get('event')!='STARTED' or value.get('event') not in ('COMPLETED','FAILED')
        or any(rows[0].get(k)!=value.get(k) for k in identity)):raise ValueError('Only the reserved run may finish once')
    append(path,value)


def prepare(args):
    release=require_release();commit=committed(V1_EXECUTION_FILES+RESOURCES)
    selection=Path(args.selection).resolve();verification=Path(args.verification).resolve()
    if not all(p.is_relative_to(ROOT/'reports') for p in (selection,verification)):raise ValueError('Public selection/verification required')
    committed([p.relative_to(ROOT).as_posix() for p in (selection,verification)],commit)
    selected=json.loads(selection.read_text('utf-8'))
    output=report_path(args.authorization);run=Path(args.run_dir).resolve()
    if run.exists() or not run.is_relative_to(ROOT/'reports/retrieval'):raise ValueError('Use a new test run directory')
    if LEDGER.exists():raise ValueError('Task8 test ledger already exists; preserve original formal run')
    ticket={'version':'bm25-final-report-1.0','purpose':'final_report','used_for_parameter_selection':False,
            'dataset_version':release['dataset_version'],'test_sha256':release['test_lock']['sha256'],
            'source_commit':commit,'inputs':snapshots(),'prepared_at':now(),'selection':record(selection),
            'verification':record(verification),'allowed_run_directory':run.relative_to(ROOT).as_posix(),
            'template':selected['selected_template']}
    validate_grant(ticket,run,current=True)
    compatibility={'purpose':'final_report','used_for_parameter_selection':False,'dataset_version':ticket['dataset_version'],
                   'test_sha256':ticket['test_sha256'],'config_sha256':digest(CONFIG.read_bytes())}
    authorize_test(release,'final_report',compatibility,CONFIG.read_bytes())
    write_new(output,ticket)
    print(json.dumps({'status':'TEST_REPORT_AUTHORIZED','template':ticket['template'],'source_commit':commit}))


def evaluate(args):
    cfg=config();split=args.mode;grant=None;auth=None
    output=Path(args.run_dir).resolve()
    if output.exists() or not output.is_relative_to(ROOT/'reports/retrieval'):raise ValueError('Use a new reports/retrieval run directory')
    if split=='test':
        if not args.authorization:raise ValueError('Test requires frozen selection and authorization before any retrieval')
        grantpath=Path(args.authorization).resolve()
        if not grantpath.is_relative_to(ROOT/'reports'):raise ValueError('Public authorization required')
        grant=json.loads(grantpath.read_text('utf-8'));validate_grant(grant,output,current=True)
        if LEDGER.exists():raise ValueError('Formal BM25 test already started; do not repeat')
        auth=record(grantpath)
    require_release();commit=committed(V1_EXECUTION_FILES+RESOURCES);inputs=snapshots()
    if grant and grant['source_commit']!=commit:raise ValueError('Test must execute the authorized source commit')
    template=grant['template'] if grant else args.template
    if template not in TEMPLATES:raise ValueError('Development requires one declared template')
    if grant and args.template and args.template!=template:raise ValueError('Cannot change selected test template')
    run_id=uuid.uuid4().hex;started=now();wall=time.perf_counter();index=None
    start={'version':'bm25-run-1.0','run_id':run_id,'split':split,'template':template,
           'purpose':'development' if split=='dev' else 'final_report','source_commit':commit,
           'inputs':inputs,'started_at':started,'authorization':auth}
    usage={'run_id':run_id,'template':template,'authorization':auth,'run_directory':output.relative_to(ROOT).as_posix(),
           'test_sha256':grant['test_sha256'] if grant else None,'source_commit':commit}
    current=None;rep=None;phase='reserve_test';reserved=False;owns_output=False
    try:
        if split=='test':
            reserve_test_usage(LEDGER,{**usage,'event':'STARTED','recorded_at':now()});reserved=True
        phase='create_directory';output.mkdir(parents=True,exist_ok=False);owns_output=True
        phase='write_start'
        write_new(output/'run_started.json',start)
        phase='load_questions';labelled=load_jsonl(EVAL/f'retrieval_{split}.jsonl')
        # Labels remain outside the retrieval loop.
        queries=[{k:q[k] for k in ('question_id','question')} for q in labelled]
        phase='load_index'
        index_path=Path(args.index).resolve() if getattr(args,'index',None) else ROOT/'data/indexes/bm25'/template
        began=time.perf_counter();index=Bm25Index(index_path);load_seconds=time.perf_counter()-began
        if index.manifest['template']!=template:raise ValueError('Index template differs from requested run')
        write_new(output/'source_map.json',index.sources)
        warmups=[]
        phase='warmup'
        for rep in range(1,4):
            sample=index.query(cfg['warmup_query'])
            warmups.append({'repetition':rep,'query':cfg['warmup_query'],'timing':sample['timing']})
        predictions=[]
        phase='retrieve'
        with (output/'predictions.jsonl').open('x',encoding='utf-8',newline='\n') as predfile:
            for question in queries:
                current=question['question_id'];measures=[];first=None
                for rep in range(1,4):
                    result=index.query(question['question']);first=first or result
                    measure={'repetition':rep,'ranked_ids':[r['chunk_id'] for r in result['results']],
                             'scores':[r['score'] for r in result['results']],**result['timing']}
                    event={'question_id':current,'question_sha256':digest(question['question'].encode()),
                           'run_id':run_id,'split':split,'template':template,**measure,'recorded_at':now()}
                    append(output/'requests.jsonl',event);measures.append(measure)
                row={'question_id':current,'question_sha256':digest(question['question'].encode()),'query':first['query'],
                     'query_tokens':first['tokens'],'run_id':run_id,'split':split,'template':template,
                     'results':first['results'],'measurements':measures}
                predfile.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');predfile.flush();predictions.append(row)
        phase='summarize';write_new(output/'summary.json',summary(labelled,predictions,template,split,run_id))
        write_new(output/'error_analysis.json',error_analysis(labelled,predictions,split))
        require_inputs(inputs,current_sources=True)
        if index.manifest!=Bm25Index(index_path).manifest:raise ValueError('Index changed during run')
        manifest={**start,'status':'COMPLETE','used_for_parameter_selection':split=='dev','completed_at':now(),
                  'wall_seconds':time.perf_counter()-wall,'load_seconds':load_seconds,'warmups':warmups,
                  'index_manifest':index.manifest,
                  'environment':{'python':sys.version.split()[0],'implementation':platform.python_implementation(),
                                 'system':platform.system(),'machine':platform.machine(),'processor':platform.processor(),
                                 'logical_cpu_count':os.cpu_count(),'concurrency':1},
                  'artifacts':{n:{k:v for k,v in record(output/n).items() if k!='path'} for n in (
                      'predictions.jsonl','requests.jsonl','source_map.json','summary.json','error_analysis.json','run_started.json')}}
        phase='replay';write_new(output/'run_manifest.json',manifest)
        checked=replay(output)
        if split=='test':finish_test_usage(LEDGER,{**usage,'event':'COMPLETED','recorded_at':now(),'run_manifest':record(output/'run_manifest.json')})
        print(json.dumps({'status':'COMPLETE','split':split,'template':template,'metrics':checked['quality']['metrics'],
                          'latency_total':checked['latency']['all']['total_seconds']},ensure_ascii=False))
    except BaseException as exc:
        failure={'status':'FAILED','run_id':run_id,'split':split,'question_id':current,'recorded_at':now(),
                 'phase':phase,'repetition':rep,'run_directory':output.relative_to(ROOT).as_posix(),
                 'error_type':type(exc).__name__,'error':str(exc)}
        failure_path=output/'failure.json' if owns_output else ROOT/'.runtime/bm25-failures'/(run_id+'.json')
        for action in ([lambda:write_new(failure_path,failure)]+([lambda:finish_test_usage(LEDGER,{**usage,**failure,'event':'FAILED'})] if reserved else [])):
            try:action()
            except Exception as secondary:print('Failure evidence write unavailable: '+type(secondary).__name__,file=sys.stderr)
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('dev','select','prepare-test','test'));p.add_argument('--template',choices=TEMPLATES)
    p.add_argument('--run-dir');p.add_argument('--development-root');p.add_argument('--selection');p.add_argument('--verification')
    p.add_argument('--authorization');p.add_argument('--output');p.add_argument('--index',type=Path);a=p.parse_args()
    if a.mode=='select':
        selection=choose(a.development_root);write_new(report_path(a.output),selection)
        print(json.dumps({'status':'SELECTED_ON_DEV','selected_template':selection['selected_template']}))
    elif a.mode=='prepare-test':prepare(a)
    else:evaluate(a)

if __name__=='__main__':main()
