"""Additive Task12 audit: preserve producer scripts and strengthen their evidence checks."""
from __future__ import annotations
import copy
from answer_eval_core import *
from answer_json_chat import selection_schema,grade_schema

ARTIFACTS = {'environment.json','error_analysis.json','judgments.jsonl','predictions.jsonl','run_started.json','summary.json'}


def validate_completion(split,start,completed,summary,analysis):
    if completed['split'] != split or completed['source_commit'] != start['source_commit']:
        raise ValueError('Completion producer/split differs')
    if set(completed['artifacts']) != ARTIFACTS: raise ValueError('Incomplete/unknown completed artifacts')
    expected = {'split':split,'judgment_kind':'AI_not_human','cases':[r for r in summary['per_question'] if
        r['missing_points'] or r['missing_conditions'] or r['bad_citation_ids'] or r['false_refusal'] or
        r['unsupported_answer'] or r['judge_error'] or r['runtime_error']]}
    if analysis != expected: raise ValueError('Error analysis does not recompute')
    for name,r in completed['artifacts'].items():
        if r != record(DIRECTORY/split/name): raise ValueError('Artifact identity differs: '+name)
    return True


def validate_attempts(attempts,messages,schema,parser):
    if not isinstance(attempts,list) or not 1 <= len(attempts) <= 2: raise ValueError('Invalid actual attempt count')
    parsed = None
    for i,a in enumerate(attempts):
        expected = messages if not i else messages+[{'role':'user','content':'上次输出格式无效。重新按规定只输出一个JSON对象，不加说明；不要改变原始证据。'}]
        if a['attempt'] != i+1 or a['messages'] != expected or a['format'] != schema:
            raise ValueError('Attempt prompt/format/sequence differs')
        if len(canonical(a['messages'])) > config()['input_utf8_byte_budget']:
            raise ValueError('Attempt exceeds input budget')
        if type(a['seconds']) not in (int,float) or not math.isfinite(a['seconds']) or a['seconds']<0:
            raise ValueError('Invalid actual attempt duration')
        response = a['response']
        if response is None:
            if not a['error']: raise ValueError('Missing successful actual response')
            continue
        if not a['error']:
            if response['model'] != config()['llm']['name'] or response['done'] is not True or response['done_reason']!='stop':
                raise ValueError('Actual structured response incomplete')
            if any(a[k] != response[k] for k in ('prompt_eval_count','eval_count','done_reason')):
                raise ValueError('Actual model counters differ')
            if type(a['prompt_eval_count']) is not int or a['prompt_eval_count'] <= 0 or type(a['eval_count']) is not int or not 0<a['eval_count']<=1024 or a['prompt_eval_count']+1536>8192:
                raise ValueError('Actual model counters exceed context')
            parsed = parser(response['message']['content'])
            if parsed != a['parsed'] or i != len(attempts)-1: raise ValueError('Parsed output differs or requested after success')
    return parsed


def validate_trace(q,p,g,actual,j,corpus):
    from answer_eval_engine import pack
    prompt = (ROOT/config()['prompt_file']).read_text('utf-8')
    if actual['question'] != q['question'] or j['question_id'] != q['question_id']:
        raise ValueError('Private question binding differs')
    if actual['retrieval']:
        candidates = [corpus[r['chunk_id']] for r in actual['retrieval']['results']]
        context,messages,size = pack(q['question'],candidates,config(),prompt)
        if (actual['context'],actual['messages'],actual['prompt_utf8_bytes']) != (context,messages,size):
            raise ValueError('Actual selection prompt differs')
        if actual['attempts']:
            selected = validate_attempts(actual['attempts'],messages,selection_schema(p['offered_ids'],3),
                lambda s:parse_selection(s,p['offered_ids'],config()))
            if not p['error'] and (selected is None or selected['chunk_ids']!=p['selected_ids']):
                raise ValueError('Actual selection not bound to displayed answer')
    if set(p['timing']) != {'retrieval_seconds','generation_seconds','total_seconds'}:
        raise ValueError('Missing timing stages')
    if p['timing']['total_seconds']+0.001 < p['timing']['retrieval_seconds']+p['timing']['generation_seconds']:
        raise ValueError('Stage clocks exceed end-to-end duration')
    for c in p['citations']:
        if c['record_sha256'] != corpus[c['chunk_id']]['record_sha256']:
            raise ValueError('Citation record hash differs, including non-gold citations')
    if p['status']=='refused': return True  # Legacy check already validates deterministic refusal.
    body = {'question':q['question'],'answerable':q['answerable'],'expected_answer_points':q['expected_answer_points'],
        'required_conditions':q['required_conditions'],'status':p['status'],'actual_answer':actual['answer'],
        'citations':[{k:c[k] for k in ('chunk_id','law_number','source_url','source_revision_verified','needs_rule_review')} for c in actual['citations']]}
    messages = [{'role':'system','content':(ROOT/config()['judge_prompt_file']).read_text('utf-8')},
        {'role':'user','content':json.dumps(body,ensure_ascii=False)}]
    if j['mode']!='AI_semantic_judge' or j['messages']!=messages: raise ValueError('Judge prompt/gold/actual answer differs')
    if j['attempts']:
        grade = validate_attempts(j['attempts'],messages,grade_schema(q,p),lambda s:parse_grade(s,q,p))
        if not j['error'] and grade != g['grade']: raise ValueError('Actual judge output differs')
    elif not j['error']: raise ValueError('No actual model judge request')
    return True


def strict_run(split,private=False):
    from verify_answer_delivery import validate_run
    summary = validate_run(split,private)
    validate_completion(split,read(DIRECTORY/split/'run_started.json'),read(DIRECTORY/split/'completed.json'),
        summary,read(DIRECTORY/split/'error_analysis.json'))
    if private:
        from answer_review_v2 import source_corpus
        corpus=source_corpus()
        for q,p,g in zip(questions(split),rows(DIRECTORY/split/'predictions.jsonl'),rows(DIRECTORY/split/'judgments.jsonl')):
            validate_trace(q,p,g,read(ROOT/p['trace']['path']),read(ROOT/g['trace']['path']),corpus)
    return summary
