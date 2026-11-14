"""Strict, append-only human judgments; no generated or implicit approvals."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from answer_eval_core import *

LEDGER = PRIVATE/'human_answer_reviews.jsonl'
VERDICTS = ('yes', 'no', 'uncertain')


def review_context():
    sample = read(DIRECTORY/'human_review_sample.json')
    predictions = {p['question_id']: p for p in rows(DIRECTORY/'test/predictions.jsonl')}
    labels = {q['question_id']: q for q in questions('test')}
    if sample['results_sha256'] != record(ROOT/'reports/answer_quality_results.json')['sha256']:
        raise ValueError('Frozen results changed')
    ids = [s['question_id'] for s in sample['samples']]
    if len(ids) != 12 or len(set(ids)) != 12:
        raise ValueError('Expected twelve distinct fixed samples')
    for s in sample['samples']:
        p = predictions[s['question_id']]
        if s['answer_sha256'] != p['answer_sha256'] or s['private_trace'] != p['trace']:
            raise ValueError('Sample/answer binding differs')
    context = {n: record(ROOT/n) for n in ('reports/answer_evaluation/human_review_sample.json',
        'reports/answer_evaluation/test/predictions.jsonl', 'data/eval/answer_eval.jsonl')}
    return {'ids': ids, 'predictions': predictions, 'labels': labels,
            'identity': digest(canonical(context)), 'inputs': context}


def validate_review(row, context):
    required = {'version','question_id','answer_sha256','private_trace','reviewer_type','reviewer',
        'reviewed_at','point_decisions','condition_decisions','citation_decisions',
        'refusal_appropriate','reason','submission_channel'}
    if not isinstance(row, dict) or row.get('version') not in ('answer-human-review-1.0','answer-human-review-1.1'):
        raise ValueError('Invalid review version')
    if row['version'].endswith('1.1'): required |= {'context_sha256'}
    if set(row) != required: raise ValueError('Missing or unknown review fields')
    qid = row['question_id']
    if qid not in context['ids']: raise ValueError('Not a selected sample')
    p = context['predictions'][qid]; q = context['labels'][qid]
    if row['answer_sha256'] != p['answer_sha256'] or row['private_trace'] != p['trace']:
        raise ValueError('Review bound to a different answer/trace')
    if 'context_sha256' in row and row['context_sha256'] != context['identity']:
        raise ValueError('Changed review sample or labels')
    if row['reviewer_type'] != 'human' or row['submission_channel'] != 'explicit local browser form':
        raise ValueError('Not an explicit human form submission')
    for key, length in (('reviewer',100),('reason',2000)):
        if not isinstance(row[key],str) or not row[key].strip() or len(row[key]) > length:
            raise ValueError('Missing/oversize '+key)
    t = datetime.fromisoformat(row['reviewed_at'])
    minimum = datetime.fromisoformat(read(DIRECTORY/'test/completed.json')['completed_at'])
    if t.tzinfo is None or not minimum <= t <= datetime.now(timezone.utc):
        raise ValueError('Review timestamp outside answer lifecycle')
    for k, size in (('point_decisions',len(q['expected_answer_points'])),
                    ('condition_decisions',len(q['required_conditions'])),
                    ('citation_decisions',len(p['citations']))):
        if not isinstance(row[k],list) or len(row[k]) != size or any(v not in VERDICTS for v in row[k]):
            raise ValueError('Invalid judgment vector: '+k)
    if row['refusal_appropriate'] not in VERDICTS: raise ValueError('Invalid refusal judgment')
    if p['status'] == 'refused' and 'yes' in row['point_decisions']+row['condition_decisions']:
        raise ValueError('A controlled refusal contains no covered claims')
    return row


@contextmanager
def ledger_lock(path=LEDGER):
    """Fail on concurrent writers; never remove a lock owned by another process."""
    path = Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    lock = path.with_suffix(path.suffix+'.lock')
    fd = os.open(lock, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    try:
        os.write(fd,str(os.getpid()).encode()); os.close(fd); fd = None
        yield
    finally:
        if fd is not None: os.close(fd)
        lock.unlink()


def read_reviews(context, path=LEDGER):
    path = Path(path)
    data = path.read_bytes() if path.exists() else b''
    if data and not data.endswith(b'\n'): raise ValueError('Truncated review ledger')
    result = []
    for line in data.decode('utf-8').splitlines():
        if not line.strip(): raise ValueError('Blank review ledger row')
        result.append(validate_review(json.loads(line),context))
    return result


def save_review(row, context, path=LEDGER):
    validate_review(row,context)
    with ledger_lock(path):
        read_reviews(context,path)  # Refuse to append onto corrupt history.
        with Path(path).open('a',encoding='utf-8',newline='\n') as f:
            f.write(canonical(row).decode()+'\n'); f.flush(); os.fsync(f.fileno())


def aggregate(context, records):
    latest = {}
    for r in records: latest[r['question_id']] = validate_review(r,context)
    per_question = []
    for qid in context['ids']:
        if qid not in latest: continue
        r = latest[qid]; p = context['predictions'][qid]
        per_question.append({k:r[k] for k in ('question_id','answer_sha256','point_decisions',
            'condition_decisions','citation_decisions','refusal_appropriate')} |
            {'status':p['status'],'answerable':context['labels'][qid]['answerable']})
    metrics = {}
    for metric,key in (('answer_point_coverage','point_decisions'),('citation_correctness','citation_decisions'),
                       ('condition_exception_retention','condition_decisions')):
        values = [v for r in per_question for v in r[key]]
        metrics[metric] = dict(ratio(values.count('yes'),len(values)),uncertain=values.count('uncertain'))
    unresolved = [r['question_id'] for r in per_question if 'uncertain' in
        r['point_decisions']+r['condition_decisions']+r['citation_decisions']+[r['refusal_appropriate']]]
    missing = [qid for qid in context['ids'] if qid not in latest]
    return {'version':'answer-human-summary-1.1','judgment_kind':'human_explicit_form',
        'status':'REVIEW_COMPLETE' if not missing and not unresolved else 'PENDING',
        'required_samples':12,'reviewed_samples':len(latest),'ledger_entries':len(records),
        'missing_ids':missing,'unresolved_ids':unresolved,'context_sha256':context['identity'],
        'metrics':metrics,'per_question':per_question,
        'scope':'Fixed error-prioritized twelve-question sample; not representative of all50, not expert rules certification. Completion is review completion, not all answers correct. Uncertain stays in denominator.'}


def snapshot(context, path=LEDGER):
    with ledger_lock(path):
        result = aggregate(context,read_reviews(context,path))
        result['private_ledger'] = record(path) if Path(path).exists() else None
        return result


def validate_public_summary(value, context):
    """Recompute public sample metrics without disclosing names or private comments."""
    required={'version','judgment_kind','status','required_samples','reviewed_samples','ledger_entries',
        'missing_ids','unresolved_ids','context_sha256','metrics','per_question','scope'}
    if not required<=set(value) or set(value)-required-{'captured_at','private_ledger'}:
        raise ValueError('Unknown public summary fields or private information')
    ids=[];synthetic=[]
    keys={'question_id','answer_sha256','point_decisions','condition_decisions','citation_decisions',
        'refusal_appropriate','status','answerable'}
    for r in value['per_question']:
        if set(r)!=keys or r['question_id'] in ids or r['question_id'] not in context['ids']:
            raise ValueError('Invalid public human row or private fields leaked')
        qid=r['question_id'];ids.append(qid);p=context['predictions'][qid]
        if r['status']!=p['status'] or r['answerable'] is not context['labels'][qid]['answerable']:
            raise ValueError('Public review answer/label differs')
        # Internal validation fixture only; never saved or represented as a human record.
        synthetic.append({k:r[k] for k in ('question_id','answer_sha256','point_decisions',
            'condition_decisions','citation_decisions','refusal_appropriate')} |
            {'version':'answer-human-review-1.1','private_trace':p['trace'],'reviewer_type':'human',
             'reviewer':'PUBLIC VALIDATION ONLY','reviewed_at':now(),'reason':'PUBLIC VALIDATION ONLY',
             'submission_channel':'explicit local browser form','context_sha256':context['identity']})
    expected=aggregate(context,synthetic)
    for k in ('version','judgment_kind','status','required_samples','reviewed_samples','missing_ids',
              'unresolved_ids','context_sha256','metrics','per_question','scope'):
        if value[k]!=expected[k]: raise ValueError('Public human summary does not recompute: '+k)
    if type(value['ledger_entries']) is not int or value['ledger_entries']<len(ids):
        raise ValueError('Invalid append-only review count')
    receipt=value.get('private_ledger')
    if ids and (not receipt or receipt['path']!=LEDGER.relative_to(ROOT).as_posix() or not sha(receipt['sha256']) or type(receipt['size_bytes']) is not int or receipt['size_bytes']<1):
        raise ValueError('Missing private ledger receipt')
    return True


def evidence(qid, context):
    p = context['predictions'][qid]; path = ROOT/p['trace']['path']
    if record(path) != p['trace']: raise ValueError('Changed actual answer trace')
    actual = read(path)
    if digest(actual['answer'].encode()) != p['answer_sha256']: raise ValueError('Changed answer')
    return actual


def source_corpus():
    path = ROOT/'data/processed/rag_chunks_zh.jsonl'
    expected = next(r for r in read(ROOT/'data/manifests/local_data_files.json')['files'] if r['path']==path.relative_to(ROOT).as_posix())
    if record(path) != {k:expected[k] for k in ('path','size_bytes','sha256')}:
        raise ValueError('Changed original corpus; refuse to show altered review evidence')
    return {r['chunk_id']:r for r in rows(path)}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',required=True)
    parser.add_argument('--require-complete',action='store_true')
    args = parser.parse_args()
    result = snapshot(review_context()); result['captured_at'] = now()
    write_new(ROOT/args.report,result)
    print(json.dumps({k:result[k] for k in ('status','reviewed_samples','required_samples','missing_ids','unresolved_ids')},ensure_ascii=False))
    return 2 if args.require_complete and result['status']!='REVIEW_COMPLETE' else 0


if __name__=='__main__': raise SystemExit(main())
