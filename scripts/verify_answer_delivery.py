"""Task12 independent public replay and optional actual local answer/source verification."""
import argparse,io,json,subprocess,tarfile
from datetime import datetime
from answer_eval_core import *

MUTABLE={'README.md','docs/DELIVERY_STATUS.md','docs/PUBLIC_SETUP.md','docs/EXPERIMENT_LOG.md','reports/README.md',
 'reports/resume_evidence.md','reports/all_experiments_summary.csv','data/manifests/experiment_manifest.json','data/manifests/project_file_manifest.json'}


def validate_run(split,private=False):
    folder=DIRECTORY/split;start=read(folder/'run_started.json');completed=read(folder/'completed.json')
    if start['split']!=split or completed['event']!='COMPLETED' or completed['samples']!=config()['formal_samples'][split] or (folder/'failure.json').exists():raise ValueError('Incomplete/failed answer run')
    begin=datetime.fromisoformat(start['started_at']);end=datetime.fromisoformat(completed['completed_at'])
    produced=datetime.fromisoformat(git('show','-s','--format=%cI',start['source_commit']))
    if not produced<=begin<end<=datetime.now().astimezone():raise ValueError('Invalid producer/run chronology')
    if start['inputs']!=committed_inputs(start['source_commit']) or start['configuration']!=config():raise ValueError('Producer/source/config differs')
    for name,r in completed['artifacts'].items():
        if record(folder/name)!=r:raise ValueError('Completed artifact differs: '+name)
    summary=replay(split);ps=rows(folder/'predictions.jsonl');gs=rows(folder/'judgments.jsonl')
    if private:
        corpus={r['chunk_id']:r for r in rows(ROOT/'data/processed/rag_chunks_zh.jsonl')}
        from answer_eval_engine import pack
        prompt=(ROOT/config()['prompt_file']).read_text('utf-8')
        for q,p,g in zip(questions(split),ps,gs):
            trace=ROOT/p['trace']['path'];judgetrace=ROOT/g['trace']['path']
            if record(trace)!=p['trace'] or record(judgetrace)!=g['trace']:raise ValueError('Local trace hash differs')
            actual=read(trace);j=read(judgetrace)
            if public_prediction(q,actual,trace)!=p or j['grade']!=g['grade'] or j['error']!=g['error']:raise ValueError('Public projection differs from actual response')
            if actual['retrieval']:
                from reranker_eval import validate_packet,config as reranker_config
                from rrf import SOURCE_FIELDS
                known={cid:{k:r[k] for k in SOURCE_FIELDS} for cid,r in corpus.items()}
                validate_packet(actual['retrieval'],q['question'],'top40',known,reranker_config())
                candidates=[corpus[v['chunk_id']] for v in actual['retrieval']['results']]
                context,messages,size=pack(q['question'],candidates,config(),prompt)
                if actual['context']!=context or actual['messages']!=messages or actual['prompt_utf8_bytes']!=size:raise ValueError('Offered original evidence differs')
            elif p['refusal_reason']!='version_unverified':raise ValueError('Unexpected missing retrieval')
            if render(p['selected_ids'],corpus)!=(actual['answer'],p['citations']):raise ValueError('Answer/source quote or citation differs')
            for a in actual['attempts']:
                if not a['error']:
                    packet=a['response']
                    if packet['model']!=config()['llm']['name'] or packet['done'] is not True or packet['done_reason']!='stop':raise ValueError('Actual model response incomplete')
                    parsed=parse_selection(packet['message']['content'],p['offered_ids'],config())
                    if a['parsed']!=parsed:raise ValueError('Selection response differs')
            if j['error'] is None and (not j['attempts'] or parse_grade(j['attempts'][-1]['response']['message']['content'],q,p)!=g['grade']):raise ValueError('Actual judge response differs')
            quotes='\n'.join(corpus[cid]['content_zh'] for cid in p['selected_ids'])
            if g['literal_points']!=[normalized(t) in normalized(quotes) for t in q['expected_answer_points']] or g['literal_conditions']!=[normalized(t) in normalized(quotes) for t in q['required_conditions']]:raise ValueError('Literal diagnostics differ')
    return summary


def verify(output,public_only=False,complete=False):
    checks={};errors=[]
    def check(name,fn):
        try:
            checks[name]=bool(fn())
            if not checks[name]:errors.append({'check':name,'error':'False predicate'})
        except Exception as exc:checks[name]=False;errors.append({'check':name,'error':type(exc).__name__+': '+str(exc)})
    raw=subprocess.check_output(['git','archive','--format=tar',BASE],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as a:old={m.name:a.extractfile(m).read() for m in a.getmembers() if m.isfile()}
    check('667_historical_public_files_preserved_except_navigation',lambda:len(old)==667 and all((ROOT/p).read_bytes()==b for p,b in old.items() if p not in MUTABLE))
    original= json.loads(old['data/manifests/experiment_manifest.json']);registry=read(ROOT/'data/manifests/experiment_manifest.json')
    check('20_existing_experiment_objects_preserved',lambda:len(original['experiments'])==20 and registry['experiments'][:20]==original['experiments'])
    for p in ('docs/EXPERIMENT_LOG.md','reports/resume_evidence.md','reports/all_experiments_summary.csv'):check(p+'_append_only',lambda p=p:(ROOT/p).read_bytes().startswith(old[p]))
    for s in ('dev','test'):check(s+'_producer_inputs_metrics_vectors_and_traces',lambda s=s:validate_run(s,not public_only)['samples']==config()['formal_samples'][s])
    check('one_completed_test_ledger_only',lambda:[r['event'] for r in rows(DIRECTORY/'test_usage.jsonl')]==['STARTED','COMPLETED'])
    def authorization():
        start=read(DIRECTORY/'test/run_started.json');auth=read(DIRECTORY/'test_authorization.json')
        return (start['authorization']==record(DIRECTORY/'test_authorization.json') and auth['inputs']==start['inputs'] and
          auth['test_labels']==record(ROOT/'data/eval/test.jsonl') and auth['development_summary']==record(DIRECTORY/'dev/summary.json') and
          subprocess.check_output(['git','show',start['source_commit']+':reports/answer_evaluation/test_authorization.json'],cwd=ROOT)==(DIRECTORY/'test_authorization.json').read_bytes())
    check('dev_selected_config_and_committed_test_authorization',authorization)
    def formal():
        f=read(ROOT/'reports/answer_quality_results.json')
        return f['development']==replay('dev') and f['test']==replay('test') and f['configuration']==config() and f['judgment_kind']=='AI_not_human' and f['new_human_answer_judgments']==0 and f['formal_test_runs']==1 and f['unseen_holdout'] is False and f['human_label_approval']==record(ROOT/'data/eval/human_review_receipt.json')
    check('required_five_metrics_numerators_denominators_and_human_scope',formal)
    def sample():
        f=read(DIRECTORY/'human_review_sample.json');p={r['question_id']:r for r in rows(DIRECTORY/'test/predictions.jsonl')}
        chosen=sorted(replay('test')['per_question'],key=lambda r:(not(r['false_refusal'] or r['unsupported_answer'] or r['bad_citation_ids'] or r['missing_conditions']),r['question_id']))[:12]
        return f['status']=='PENDING' and f['human_answer_judgments']==0 and f['results_sha256']==record(ROOT/'reports/answer_quality_results.json')['sha256'] and [r['question_id'] for r in f['samples']]==[r['question_id'] for r in chosen] and all(r['answer_sha256']==p[r['question_id']]['answer_sha256'] and r['decision'] is None and r['reviewer'] is None for r in f['samples'])
    check('12_human_samples_bound_to_answers_without_fabricated_approval',sample)
    tracked=git('ls-files').splitlines()
    check('no_full_rules_models_indexes_runtime_or_credentials_tracked',lambda:not any(p.startswith(('data/raw/','data/processed/','data/indexes/','.runtime/','.models/','.venv/','third_party/')) for p in tracked))
    if not public_only:
        before=read(PRIVATE/'before.json')
        check('25_original_private_indexes_unchanged',lambda:len(before['indexes'])==25 and all(digest((ROOT/p).read_bytes())==h for p,h in before['indexes'].items()))
        check('61_original_corpus_files_unchanged',lambda:all(record(ROOT/r['path'])=={k:r[k] for k in ('path','size_bytes','sha256')} for r in read(ROOT/'data/manifests/local_data_files.json')['files']))
        check('parent_child_derived_corpus_unchanged',lambda:digest((ROOT/'data/processed/rag_chunks_parent_child.jsonl').read_bytes())==before['derived'])
        check('original_human_review_ledger_unchanged',lambda:digest((ROOT/'.runtime/eval_review/reviews.jsonl').read_bytes())==before['human_review_sha256'])
        check('local_human_review_full_answers_delivered',lambda:(PRIVATE/'human_review.html').stat().st_size>1000)
    if complete:
        for p in ('docs/ANSWER_EVALUATION.md','reports/TASK_12_DELIVERY.md'):check(p+'_delivered',lambda p=p:(ROOT/p).stat().st_size>1000)
        check('21st_experiment_registered_with_actual_artifacts',lambda:len(registry['experiments'])==21 and registry['experiments'][-1]['id']=='TASK-012-ANSWER-EVALUATION' and all(record(ROOT/r['path'])==r for r in registry['experiments'][-1]['artifacts']))
    value={'version':'answer-delivery-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,
      'public_only':public_only,'complete':complete,'new_model_requests':0,'source_sha256':record(__file__)['sha256'],
      'human_answer_review_status':'PENDING; automated delivery does not assert human semantic accuracy'}
    write_new(output,value);return value


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True);p.add_argument('--public-only',action='store_true');p.add_argument('--complete',action='store_true');a=p.parse_args();r=verify(ROOT/a.report,a.public_only,a.complete);print(json.dumps(r,ensure_ascii=False));raise SystemExit(r['status']!='PASS')
