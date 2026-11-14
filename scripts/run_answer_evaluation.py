"""Task12 dev -> committed authorization -> one reused-lock test -> read-only replay."""
from __future__ import annotations
import argparse,copy,json,os,subprocess,sys
from answer_eval_core import *


def freeze():
    source=git('rev-parse','HEAD');inputs=committed_inputs(source)
    development=replay('dev')
    if development['samples']!=40:raise ValueError('Development incomplete')
    write_new(DIRECTORY/'test_authorization.json',{'version':'answer-test-authorization-1.0','created_at':now(),
        'source_commit':source,'inputs':inputs,'development_summary':record(DIRECTORY/'dev/summary.json'),
        'test_labels':record(ROOT/'data/eval/test.jsonl'),'scope':'User-authorized Task12; one new answer assessment on previously used locked50, not unseen holdout; no test tuning',
        'retrieval_method':config()['retrieval_method'],'metrics_policy':'AI_not_human; all five rates plus denominators, failures and per-question evidence'})


def execute(split):
    from answer_eval_engine import AnswerEngine,judge
    source=git('rev-parse','HEAD');inputs=committed_inputs(source)
    folder=DIRECTORY/split;private=PRIVATE/split
    if folder.exists() or private.exists():raise ValueError('Run directory already exists; preserve it, no rerun')
    auth=None
    if split=='test':
        auth=read(DIRECTORY/'test_authorization.json')
        if auth['inputs']!=inputs or auth['test_labels']!=record(ROOT/'data/eval/test.jsonl') or auth['development_summary']!=record(DIRECTORY/'dev/summary.json'):raise ValueError('Frozen source/dev/test changed')
        raw=subprocess.check_output(['git','show','HEAD:reports/answer_evaluation/test_authorization.json'],cwd=ROOT)
        if raw!=(DIRECTORY/'test_authorization.json').read_bytes():raise ValueError('Commit authorization before test')
        if (DIRECTORY/'test_usage.jsonl').exists():raise ValueError('Formal test authorization already consumed')
    folder.mkdir(parents=True);private.mkdir(parents=True)
    started={'version':'answer-run-1.0','split':split,'started_at':now(),'source_commit':source,'inputs':inputs,
             'authorization':record(DIRECTORY/'test_authorization.json') if auth else None,'configuration':config()}
    write_new(folder/'run_started.json',started)
    if split=='test':
        with (DIRECTORY/'test_usage.jsonl').open('x',encoding='utf-8') as f:f.write(canonical({'event':'STARTED',**started}).decode()+'\n')
    engine=None
    try:
        engine=AnswerEngine();write_new(folder/'environment.json',{'retriever':engine.retriever.environment(),'answer_model':config()['llm'],'same_model_judge':True})
        qs=questions(split);predictions=[]
        for i,q in enumerate(qs,1):
            # Only the question string crosses the production answer API.
            result=engine.answer(q['question']);path=private/'answers'/ (q['question_id']+'.json');write_new(path,result)
            p=public_prediction(q,result,path);validate_public_prediction(q,p);append(folder/'predictions.jsonl',p);predictions.append(p)
            print(f"{split} answer {i}/{len(qs)} {q['question_id']} {p['status']} {p['selected_ids']} error={p['error']}",flush=True)
        # Gold labels enter the separate judge only after all answers are sealed.
        grades=[]
        for i,(q,p) in enumerate(zip(qs,predictions),1):
            result=read(ROOT/p['trace']['path']);path=private/'judges'/(q['question_id']+'.json')
            g=judge(q,p,result,engine.chat,path);append(folder/'judgments.jsonl',g);grades.append(g)
            print(f"{split} judge {i}/{len(qs)} {q['question_id']} error={g['error']}",flush=True)
        summary=summarize(split,predictions,grades);write_new(folder/'summary.json',summary)
        write_new(folder/'error_analysis.json',{'split':split,'judgment_kind':'AI_not_human','cases':[r for r in summary['per_question'] if r['missing_points'] or r['missing_conditions'] or r['bad_citation_ids'] or r['false_refusal'] or r['unsupported_answer'] or r['judge_error'] or r['runtime_error']]})
        completed={'event':'COMPLETED','completed_at':now(),'split':split,'source_commit':source,'samples':len(qs),
                   'artifacts':{p.name:record(p) for p in folder.iterdir() if p.is_file()}}
        write_new(folder/'completed.json',completed)
        if split=='test':append(DIRECTORY/'test_usage.jsonl',completed)
        print(json.dumps({'status':'COMPLETED','split':split,'samples':len(qs),'metrics':summary['metrics'],'runtime_errors':summary['runtime_errors'],'judge_errors':summary['judge_errors']},ensure_ascii=False),flush=True)
    except BaseException as exc:
        failure={'event':'FAILED','at':now(),'split':split,'error':type(exc).__name__+': '+str(exc)}
        write_new(folder/'failure.json',failure)
        if split=='test':append(DIRECTORY/'test_usage.jsonl',failure)
        raise
    finally:
        if engine is not None:engine.close()


def export():
    development=replay('dev');test=replay('test')
    ledger=rows(DIRECTORY/'test_usage.jsonl')
    if [e['event'] for e in ledger]!=['STARTED','COMPLETED']:raise ValueError('Test ledger is not one completed run')
    write_new(ROOT/'reports/answer_quality_results.json',{'version':'answer-quality-results-1.0',
      'created_at':now(),'system':'optimized_extractive','development':development,'test':test,
      'configuration':config(),'judgment_kind':'AI_not_human','new_human_answer_judgments':0,
      'human_label_approval':record(ROOT/'data/eval/human_review_receipt.json'),
      'human_method':'docs/ANSWER_EVALUATION.md; 12 deterministic test sample review kit; no human semantic scores without actual signed decisions',
      'formal_test_runs':1,'unseen_holdout':False,'artifacts':{s:{n:record(DIRECTORY/s/n) for n in ('run_started.json','predictions.jsonl','judgments.jsonl','summary.json','error_analysis.json','completed.json')} for s in ('dev','test')}})
    sample=sorted(test['per_question'],key=lambda r:(not(r['false_refusal'] or r['unsupported_answer'] or r['bad_citation_ids'] or r['missing_conditions']),r['question_id']))[:12]
    ps={p['question_id']:p for p in rows(DIRECTORY/'test/predictions.jsonl')}
    write_new(DIRECTORY/'human_review_sample.json',{'version':'answer-human-sample-1.0','selection':'errors/refusals/condition failures first, then question_id; 12 fixed samples; no selection by flattering output',
       'status':'PENDING','human_answer_judgments':0,'results_sha256':record(ROOT/'reports/answer_quality_results.json')['sha256'],
       'samples':[{'question_id':r['question_id'],'answer_sha256':ps[r['question_id']]['answer_sha256'],'private_trace':ps[r['question_id']]['trace'],
                   'decision':None,'point_decisions':None,'condition_decisions':None,'citation_decisions':None,'reviewer':None,'reviewed_at':None} for r in sample]})
    # Complete answers and source quotations are local; the public sample contains only hashes.
    import html
    blocks=['<meta charset="utf-8"><title>任务十二人工复核资料</title><h1>任务十二人工复核资料（待审核）</h1>',
            '<p>逐题检查事实、条件/例外、否定、单位、规则编号、引用是否直接支持问题。原AI分数不可直接签为人工通过。完整回答及来源只保留本机。</p>']
    qs={q['question_id']:q for q in questions('test')}
    for row in sample:
        q=qs[row['question_id']];p=ps[row['question_id']];actual=read(ROOT/p['trace']['path'])
        blocks.extend(['<hr><h2>'+html.escape(q['question_id']+' '+q['question'])+'</h2>',
                       '<h3>实际答案与引用</h3><pre style="white-space:pre-wrap">'+html.escape(actual['answer'])+'</pre>',
                       '<h3>标签与需要保留的条件</h3><pre>'+html.escape(json.dumps({k:q[k] for k in ('expected_answer_points','required_conditions','expected_chunk_ids','must_refuse')},ensure_ascii=False,indent=2))+'</pre>'])
    target=PRIVATE/'human_review.html'
    with target.open('x',encoding='utf-8') as f:f.write('\n'.join(blocks))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('dev','prepare-test','test','replay','export'));a=p.parse_args()
    if a.action in ('dev','test'):execute(a.action)
    elif a.action=='prepare-test':freeze()
    elif a.action=='export':export()
    else:
        for s in ('dev','test'):print(json.dumps({'split':s,'metrics':replay(s)['metrics']},ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
