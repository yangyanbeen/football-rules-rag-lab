"""Task12 model-free contracts and transparent AI-assisted answer metrics."""
from __future__ import annotations
import hashlib,json,math,re,subprocess,unicodedata
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE='9c6f5a4a4b7b60511d948c3ae056400fa48327a6'
CONFIG='config/answer_evaluation.json'
DIRECTORY=ROOT/'reports/answer_evaluation'
PRIVATE=ROOT/'.runtime/task12'
PROFILES=('optimized_extractive',)
NATIVE=('scripts/answer_eval_core.py','scripts/answer_eval_engine.py','scripts/run_answer_evaluation.py',
        'scripts/verify_answer_evaluation.py','scripts/verify_answer_delivery.py')
RESOURCES=(CONFIG,'config/answer_evaluation_system.txt','config/answer_evaluation_judge.txt','docs/TASK_12_SCOPE.md')
INPUTS=('data/eval/answer_eval.jsonl','data/eval/retrieval_dev.jsonl','data/eval/retrieval_test.jsonl',
        'data/eval/human_review_receipt.json','reports/reranker_results.json','config/rag_b0.json',
        'config/reranker_experiment.json','config/dense_index.json')
BOUNDARY='资料为固定Wikipedia快照的AI中文整理，非官方赛季规则，未经过裁判专家审校；历史修订正文未独立核验。'
REFUSAL='现有资料不足以可靠回答这个问题，无法据此给出确定结论。'


def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def digest(raw):return hashlib.sha256(raw).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def read(path):return json.loads(Path(path).read_text('utf-8'))
def rows(path):return [json.loads(line) for line in Path(path).read_text('utf-8').splitlines() if line.strip()]
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True,encoding='utf-8').strip()


def record(path):
    p=Path(path).resolve();raw=p.read_bytes()
    if not p.is_relative_to(ROOT):raise ValueError('Path outside checkout')
    return {'path':p.relative_to(ROOT).as_posix(),'size_bytes':len(raw),'sha256':digest(raw)}


def write_new(path,value):
    p=Path(path).resolve()
    if not p.is_relative_to(ROOT):raise ValueError('Output outside checkout')
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8',newline='\n') as f:f.write(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n')


def append(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('a',encoding='utf-8',newline='\n') as f:f.write(canonical(value).decode()+'\n');f.flush()


def config():
    c=read(ROOT/CONFIG)
    if c['version']!='answer-evaluation-1.0' or c['retrieval_method']!='top40':raise ValueError('Changed Task12 policy')
    if (c['input_utf8_byte_budget'],c['max_context_chunks'],c['max_selected_chunks'],c['max_generation_attempts'])!=(6200,5,3,2):raise ValueError('Changed answer budgets')
    old=read(ROOT/'config/rag_b0.json')
    if c['llm']!=old['llm'] or c['chat_template_token_reserve']!=512:raise ValueError('Model or context policy differs from pinned B0')
    if c['input_utf8_byte_budget']+512+c['llm']['num_predict']>c['llm']['num_ctx']:raise ValueError('Context reserve overflow')
    if read(ROOT/c['retrieval_selection_source'])['selected_method_on_dev']!=c['retrieval_method']:raise ValueError('Not the development-selected retrieval configuration')
    return c


def committed_inputs(source):
    if not re.fullmatch('[a-f0-9]{40}',source) or subprocess.run(['git','merge-base','--is-ancestor',source,'HEAD'],cwd=ROOT,capture_output=True).returncode:raise ValueError('Invalid producer commit')
    result={}
    # Pin every current production/evaluator dependency, including reused adapters.
    producer_paths=git('ls-tree','-r','--name-only',source,'scripts','config').splitlines()
    names=NATIVE+RESOURCES+INPUTS+tuple(p for p in producer_paths if p.endswith(('.py','.json','.txt')) and p not in NATIVE+RESOURCES+INPUTS)
    for p in dict.fromkeys(names):
        raw=subprocess.check_output(['git','show',source+':'+p],cwd=ROOT)
        if raw!=(ROOT/p).read_bytes():raise ValueError('Uncommitted source/input: '+p)
        result[p]={'path':p,'size_bytes':len(raw),'sha256':digest(raw)}
    return result


def questions(split):
    result=[r for r in rows(ROOT/'data/eval/answer_eval.jsonl') if r['split']==split]
    if len(result)!=config()['formal_samples'][split] or len({q['question_id'] for q in result})!=len(result):raise ValueError('Wrong question count/IDs')
    return result


def normalized(s):return re.sub(r'\s+','',unicodedata.normalize('NFKC',s)).casefold()


def parse_selection(content,offered,cfg):
    p=json.loads(content)
    if not isinstance(p,dict) or set(p)!={'answerable','chunk_ids','reason'} or type(p['answerable']) is not bool or not isinstance(p['chunk_ids'],list):raise ValueError('Invalid selection schema')
    ids=p['chunk_ids']
    if not all(isinstance(cid,str) for cid in ids) or len(set(ids))!=len(ids):raise ValueError('Duplicate/invalid IDs')
    if p['answerable']:
        if p['reason'] is not None or not 1<=len(ids)<=cfg['max_selected_chunks'] or not set(ids)<=set(offered):raise ValueError('Answer has unknown/unoffered evidence or reason')
    elif ids or p['reason'] not in ('insufficient_evidence','source_conflict','version_unverified'):raise ValueError('Invalid controlled refusal')
    return p


def parse_grade(content,q,prediction):
    v=json.loads(content)
    if not isinstance(v,dict) or set(v)!={'points','conditions','citations','reason'}:raise ValueError('Invalid judge schema')
    sizes={'points':len(q['expected_answer_points']),'conditions':len(q['required_conditions']),'citations':len(prediction['citations'])}
    for k,n in sizes.items():
        if not isinstance(v[k],list) or len(v[k])!=n or any(type(b) is not bool for b in v[k]):raise ValueError('Judge vector length/type differs: '+k)
    if not isinstance(v['reason'],str) or not 1<=len(v['reason'])<=500:raise ValueError('Missing/oversize judge reason')
    if prediction['status']=='refused' and any(v['points']+v['conditions']+v['citations']):raise ValueError('Refusal cannot contain covered claims')
    return v


def render(selected,by_id):
    if not selected:return REFUSAL+'\n'+BOUNDARY,[]
    text=['根据现有资料，相关完整段落如下：'];cites=[]
    keys=('source_id','source_url','source_lines','source_revision_id','source_revision_status','source_revision_verified',
          'law_number','needs_rule_review','review_notes','expert_reviewed','official_translation',
          'source_attribution','license','license_url','content_zh_sha256','record_sha256')
    for cid in selected:
        r=by_id[cid];quote=r['content_zh']
        if digest(quote.encode())!=r['content_zh_sha256']:raise ValueError('Source body hash differs')
        c={k:r[k] for k in keys};c.update(chunk_id=cid,title=r['section_path'][-1],quote_sha256=digest(quote.encode()),quote_characters=len(quote))
        cites.append(c);a,b=c['source_lines']
        text.extend([quote,f"来源：{cid} · 第{c['law_number']}条 · L{a}–L{b} · {c['source_url']}"])
        if c['needs_rule_review']:text.append('校核提示：'+'；'.join(c['review_notes']))
    text.append(BOUNDARY)
    return '\n\n'.join(text),cites


def public_prediction(q,result,trace):
    return {'question_id':q['question_id'],'question':q['question'],'split':q['split'],'annotation_sha256':q['annotation_sha256'],
      'profile':'optimized_extractive','status':result['status'],'refusal_reason':result['refusal_reason'],'error':result['error'],
      'selected_ids':result['selected_ids'],'offered_ids':result['offered_ids'],'retrieved_ids':result['retrieved_ids'],
      'answer_sha256':digest(result['answer'].encode()),'answer_characters':len(result['answer']),'citations':result['citations'],
      'boundary_preserved':result['answer'].endswith(BOUNDARY),'prompt_utf8_bytes':result['prompt_utf8_bytes'],
      'timing':result['timing'],'model_digest':config()['llm']['digest'],'trace':record(trace),
      'generation_attempts':[{k:a.get(k) for k in ('attempt','error','prompt_eval_count','eval_count','done_reason')} for a in result['attempts']]}


def validate_public_prediction(q,p):
    if p['question_id']!=q['question_id'] or p['question']!=q['question'] or p['split']!=q['split'] or p['annotation_sha256']!=q['annotation_sha256']:raise ValueError('Question binding differs')
    if p['profile']!='optimized_extractive' or p['status'] not in ('answered','refused'):raise ValueError('Invalid profile/status')
    for key,maxsize in [('retrieved_ids',10),('offered_ids',5),('selected_ids',3)]:
        ids=p[key]
        if not isinstance(ids,list) or len(ids)>maxsize or any(not isinstance(v,str) or not re.fullmatch(r'L\d{2}-\d{2}',v) for v in ids) or len(set(ids))!=len(ids):raise ValueError('Invalid IDs: '+key)
    if not set(p['selected_ids'])<=set(p['offered_ids'])<=set(p['retrieved_ids']):raise ValueError('Unretrieved or unoffered citation')
    if [c['chunk_id'] for c in p['citations']]!=p['selected_ids'] or (p['status']=='answered')!=bool(p['selected_ids']):raise ValueError('Answer/citation status differs')
    if p['status']=='answered' and (p['error'] is not None or p['refusal_reason'] is not None):raise ValueError('Failed result asserted answer')
    if p['status']=='refused' and not isinstance(p['refusal_reason'],str):raise ValueError('Missing refusal reason')
    if p['boundary_preserved'] is not True or p['model_digest']!=config()['llm']['digest']:raise ValueError('Lost version boundary/model pin')
    if type(p['prompt_utf8_bytes']) is not int or not 0<=p['prompt_utf8_bytes']<=6200:raise ValueError('Input budget exceeded')
    ref=p['trace'];path=(ROOT/ref['path']).resolve()
    if not path.is_relative_to(PRIVATE) or not sha(ref['sha256']) or type(ref['size_bytes']) is not int or ref['size_bytes']<1:raise ValueError('Unsafe private trace reference')
    if not sha(p['answer_sha256']) or type(p['answer_characters']) is not int or p['answer_characters']<1:raise ValueError('Invalid answer identity')
    for value in p['timing'].values():
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:raise ValueError('Invalid timing')
    for c in p['citations']:
        original=read(ROOT/'data/manifests/structure_parent_child.json')['originals'].get(c['chunk_id'])
        if not original or c['law_number']!=original['law_number'] or c['quote_characters']!=original['characters'] or c['title']!=original['section_path'][-1]:raise ValueError('Citation original ID/law/title/length differs')
        for k,v in original['source'].items():
            if c.get(k)!=v:raise ValueError('Citation frozen source metadata differs: '+k)
        expected=next((r for r in q['source_references'] if r['chunk_id']==c['chunk_id']),None)
        # An unlabelled citation is allowed to be scored as a quality error, not hidden.
        if expected:
            for k in ('source_url','source_lines','law_number','source_revision_id','needs_rule_review','content_zh_sha256'):
                if k in expected and c[k]!=expected[k]:raise ValueError('Citation source differs: '+k)
        if not sha(c['quote_sha256']) or c['quote_sha256']!=c['content_zh_sha256']:raise ValueError('Quote identity differs')
        if c['expert_reviewed'] is not False or c['official_translation'] is not False or c['source_revision_verified'] is not False:raise ValueError('Unverified source upgraded to official')
    if not isinstance(p['generation_attempts'],list) or len(p['generation_attempts'])>2:raise ValueError('Invalid generation attempts')
    for i,a in enumerate(p['generation_attempts'],1):
        if a['attempt']!=i:raise ValueError('Attempt sequence differs')
        if a['error'] is None:
            if type(a['prompt_eval_count']) is not int or type(a['eval_count']) is not int or not 0<a['eval_count']<=1024 or a['prompt_eval_count']+1024+512>8192 or a['done_reason']!='stop':raise ValueError('Invalid model counters')
    if p['status']=='answered' and (not p['generation_attempts'] or p['generation_attempts'][-1]['error'] is not None):raise ValueError('Answered without completed actual generation')
    return True


def sha(s):return isinstance(s,str) and re.fullmatch('[a-f0-9]{64}',s) is not None


def score_row(q,p,g):
    validate_public_prediction(q,p)
    if set(g)!= {'question_id','judgment_kind','grade','error','trace','literal_points','literal_conditions'} or g['question_id']!=q['question_id'] or g['judgment_kind']!='AI_not_human':raise ValueError('Grade binding differs')
    v=parse_grade(json.dumps(g['grade'],ensure_ascii=False),q,p)
    if not g['trace'] or not sha(g['trace']['sha256']) or not (ROOT/g['trace']['path']).resolve().is_relative_to(PRIVATE):raise ValueError('Missing judge trace')
    for k,labels in [('literal_points',q['expected_answer_points']),('literal_conditions',q['required_conditions'])]:
        if len(g[k])!=len(labels) or any(type(x) is not bool for x in g[k]):raise ValueError('Literal vector differs')
    if g['error'] and any(v['points']+v['conditions']+v['citations']):raise ValueError('Failed judge must remain zero, no fabricated positives')
    answered=p['status']=='answered'
    return {'question_id':q['question_id'],'answerable':q['answerable'],'status':p['status'],
      'points_correct':sum(v['points']),'points_total':len(v['points']),
      'conditions_correct':sum(v['conditions']),'conditions_total':len(v['conditions']),
      'citations_correct':sum(v['citations']),'citations_total':len(v['citations']),
      'correct_refusal':not q['answerable'] and not answered and p['error'] is None,
      'false_refusal':q['answerable'] and not answered,'runtime_error':p['error'] is not None,'judge_error':g['error'] is not None,
      'literal_points_correct':sum(g['literal_points']),'literal_conditions_correct':sum(g['literal_conditions']),
      'missing_points':[label for label,ok in zip(q['expected_answer_points'],v['points']) if not ok],
      'missing_conditions':[label for label,ok in zip(q['required_conditions'],v['conditions']) if not ok],
      'bad_citation_ids':[c['chunk_id'] for c,ok in zip(p['citations'],v['citations']) if not ok],
      'unsupported_answer':not q['answerable'] and answered,'judge_reason':v['reason']}


def ratio(n,d):return {'numerator':n,'denominator':d,'value':n/d if d else None}


def summarize(split,predictions,grades):
    qs=questions(split)
    if len(predictions)!=len(qs) or len(grades)!=len(qs):raise ValueError('Incomplete predictions/grades')
    evaluated=[score_row(q,p,g) for q,p,g in zip(qs,predictions,grades)]
    total=lambda k:sum(r[k] for r in evaluated)
    answerable=sum(q['answerable'] for q in qs);unanswerable=len(qs)-answerable
    metrics={name:ratio(total(a),total(b)) for name,a,b in [('answer_point_coverage','points_correct','points_total'),('citation_correctness','citations_correct','citations_total'),('condition_exception_retention','conditions_correct','conditions_total')]}
    metrics.update(correct_refusal_rate=ratio(total('correct_refusal'),unanswerable),false_refusal_rate=ratio(total('false_refusal'),answerable))
    return {'split':split,'samples':len(qs),'answerable':answerable,'must_refuse':unanswerable,
      'judgment_kind':'AI_not_human','human_answer_judgments':0,'metrics':metrics,
      'literal_diagnostics':{'points':ratio(total('literal_points_correct'),total('points_total')),'conditions':ratio(total('literal_conditions_correct'),total('conditions_total'))},
      'runtime_errors':total('runtime_error'),'judge_errors':total('judge_error'),
      'answered':sum(p['status']=='answered' for p in predictions),'refused':sum(p['status']=='refused' for p in predictions),
      'human_semantic_metrics':None,'per_question':evaluated,
      'interpretation':'AI point/condition/citation judgments are provisional, not human accuracy or expert rules validation. Literal diagnostics are not semantic quality.'}


def replay(split):
    folder=DIRECTORY/split
    p=rows(folder/'predictions.jsonl');g=rows(folder/'judgments.jsonl');summary=summarize(split,p,g)
    if canonical(summary)!=canonical(read(folder/'summary.json')):raise ValueError('Saved summary does not recompute')
    return summary
