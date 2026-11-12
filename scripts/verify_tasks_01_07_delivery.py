"""Aggregate the comprehensive review without changing original task gates."""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from delivery_review_io import new_report, valid_task3_receipt

ROOT = Path(__file__).resolve().parents[1]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path): return json.loads(path.read_text('utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-dir', default='reports/rechecks/task1-7-audit-20261112')
    parser.add_argument('--snapshot', default='.runtime/task1-7-audit/before.json')
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    report = new_report(ROOT, args.report)
    audit = (ROOT/args.audit_dir).resolve()
    if not audit.is_relative_to(ROOT/'reports'): raise ValueError('Audit evidence must remain under reports/')
    checks, receipts, errors = {}, {}, []

    def check(name, callback):
        try: checks[name] = bool(callback())
        except (OSError, ValueError, KeyError, TypeError) as exc:
            checks[name] = False; errors.append({'check':name, 'error_type':type(exc).__name__})

    def gate(name, pkey, tkey, count, statuses=('PASS',)):
        path = audit/name; receipt = load(path); receipts[name] = sha(path)
        outcomes = receipt.get('checks', [])
        passed = all(v is True for v in outcomes.values()) if isinstance(outcomes, dict) else all(v['passed'] is True for v in outcomes)
        return (receipt.get('status') in statuses and type(receipt[pkey]) is int and receipt[pkey] == receipt[tkey] == count
                and passed and len(outcomes) == count)

    specs = [('final/unified-fresh/delivery/fresh_delivery.json','passed','total',33),
             ('final/unified-fresh/answer_contract.json','passed','total',19,(None,)),
             ('final/task45/acceptance/task4_delivery_gate.json','passed','total',26),
             ('final/task45/acceptance/task4_public_receipt.json','passed','total',13,('PASS_PUBLIC_RECEIPT',)),
             ('final/task45/acceptance/task4_workflow_verification.json','passed','total',27),
             ('final/task45/acceptance/task4_human_release_verification.json','passed','total',15),
             ('final/task45/acceptance/task5_delivery_gate.json','passed','total',24),
             ('final/task45/acceptance/task45_regressions.json','passed','total',39),
             ('final/task6.json','passed','total',62),
             ('final/task6-private.json','passed','total',20,('PASS_PRIVATE_RECEIPTS',)),
             ('final/task456.json','passed','total',58),
             ('final/task7.json','passed','total',43),
             ('final/task7-replay.json','passed_checks','check_count',113),
             ('final/task7-supplement.json','passed','total',61),
             ('acceptance/task7-arithmetic.json','checks_passed','checks_total',54),
             ('acceptance/task7-contract.json','passed_checks','check_count',110),
             ('acceptance/review-tools-final.json','passed','total',37),
             ('final/wrapper-rerun.json','passed','total',4)]
    for spec in specs: check(spec[0], lambda spec=spec:gate(*spec))
    check('task3_original_18_8_16', lambda:valid_task3_receipt(load(audit/'final/unified-fresh/task3.json')))
    check('task5_18_corrupt_cases_and_exact_rebuild', lambda:
          (lambda r:r['negative_cases_rejected']==r['negative_cases_total']==18 and r['max_rebuild_vector_difference']==0)(load(audit/'final/task45/acceptance/task5_delivery_gate.json')))
    check('current_task6_three_answers_one_refusal', lambda:
          (lambda r:r['status']=='PASS' and [v['status'] for v in r['rows']]==['answered']*3+['refused'] and not r['formal_eval_questions_read'])(load(audit/'evidence/task6-live-smoke.json')))
    check('current_services_and_sealed_review', lambda:all(load(audit/'evidence/runtime-health.json')['checks'].values()))
    check('task7_no_new_formal_test_requests', lambda:load(audit/'final/task7.json')['real_test_runs_started_by_this_script']==0)
    snapshot_path = (ROOT/args.snapshot).resolve()
    if not snapshot_path.is_relative_to(ROOT/'.runtime'): raise ValueError('Preservation snapshot must stay private')
    before = load(snapshot_path)
    baseline = before['commit']
    check('baseline_snapshot_covers_exact_committed_public_tree', lambda:
          set(subprocess.check_output(['git','ls-tree','-r','--name-only',baseline],cwd=ROOT,text=True).splitlines())==set(before['tracked'])
          and all(hashlib.sha256(subprocess.check_output(['git','show',baseline+':'+p],cwd=ROOT)).hexdigest()==v for p,v in before['tracked'].items()))
    editable_reports = {'reports/README.md','reports/resume_evidence.md','reports/all_experiments_summary.csv'}
    check('all_original_eval_and_delivery_report_bytes_preserved', lambda:all(sha(ROOT/p)==v for p,v in before['tracked'].items()
          if p.startswith(('data/eval/','reports/')) and p not in editable_reports))
    check('formal_index_all_files_preserved', lambda:before['index']=={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'data/indexes/dense').rglob('*') if p.is_file()})
    check('private_human_review_ledger_preserved', lambda:sha(ROOT/'.runtime/eval_review/reviews.jsonl')==before['ledger'])
    check('authority_documents_and_original_eval_validator_preserved', lambda:all(sha(ROOT/p)==before['tracked'][p] for p in (
        'docs/TECHNICAL_DESIGN.md','docs/DEVELOPMENT_PLAN_AND_REPORT.md','docs/UPSTREAM_VERSION.md','scripts/validate_eval_dataset.py')))
    check('all_original_ten_experiment_objects_preserved', lambda:
          load(ROOT/'data/manifests/experiment_manifest.json')['experiments'][:10]==json.loads(subprocess.check_output(
              ['git','show',baseline+':data/manifests/experiment_manifest.json'],cwd=ROOT))['experiments'])
    result = {'captured_at':datetime.now(timezone.utc).isoformat(), 'status':'PASS' if all(checks.values()) else 'FAIL',
              'passed':sum(checks.values()), 'total':len(checks), 'checks':checks, 'errors':errors,
              'baseline_commit':baseline, 'receipts_sha256':receipts, 'private_snapshot_sha256':sha(snapshot_path),
              'scope':'Aggregate of original task 1-7 gates plus new regression and preservation checks; no replacement acceptance thresholds.',
              'ui_scope':'Preserved actual browser records replayed; current HTTP health and fresh backend smoke checked separately.',
              'new_formal_test_experiments_started':0,
              'source_sha256':sha(Path(__file__))}
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open('x',encoding='utf-8') as h: h.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','passed','total','errors')}))
    return 0 if result['status']=='PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
