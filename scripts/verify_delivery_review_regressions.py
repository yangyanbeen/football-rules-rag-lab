"""Review-tool regressions using synthetic inputs and preserved task 2/3 receipts."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from delivery_review_io import (new_report, new_report_directory, select_ui_event,
                                visible_answer, complete_checks, valid_task3_receipt)

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    report = new_report(ROOT, args.report)
    temp = ROOT / '.tmp' / ('delivery-review-' + uuid.uuid4().hex)
    temp.mkdir(parents=True)
    checks = {}

    def check(name, value): checks[name] = bool(value)
    def rejects(f):
        try: f()
        except (ValueError, FileExistsError): return True
        return False

    prior = temp / 'prior.json'
    prior.write_text('{"historic":true}', 'utf-8')
    checksum = hashlib.sha256(prior.read_bytes()).hexdigest()
    check('existing_receipt_rejected', rejects(lambda: new_report(ROOT, prior)))
    check('outside_report_path_rejected', rejects(lambda: new_report(ROOT, ROOT.parent / 'outside.json')))
    check('report_cannot_be_source_file', rejects(lambda: new_report(ROOT, ROOT / 'scripts/input.json')))
    check('new_json_path_allowed', new_report(ROOT, temp / 'new.json') == temp / 'new.json')
    check('report_root_rejected', rejects(lambda: new_report_directory(ROOT, ROOT / 'reports')))
    check('outside_report_directory_rejected', rejects(lambda: new_report_directory(ROOT, ROOT.parent / 'outside')))
    for script, flag in [('verify_task3_isolated.py', '--report'), ('verify_answer_quality.py', '--output')]:
        p = subprocess.run([sys.executable, '-B', str(ROOT/'scripts'/script), flag, str(prior)], cwd=ROOT,
                           capture_output=True, text=True, encoding='utf-8', timeout=40)
        check(script + '_refuses_existing_receipt', p.returncode != 0 and 'Refusing to overwrite' in p.stderr)
    p = subprocess.run([sys.executable, '-B', str(ROOT/'scripts/verify_fresh_delivery.py'), '--ui-capture', 'unused',
                        '--regression-report', 'unused', '--report-dir', str(ROOT/'reports')], cwd=ROOT,
                       capture_output=True, text=True, encoding='utf-8', timeout=40)
    check('fresh_gate_refuses_shared_reports_before_reading_inputs', p.returncode != 0 and 'new subdirectory' in p.stderr)
    check('prior_receipt_bytes_preserved', hashlib.sha256(prior.read_bytes()).hexdigest() == checksum)
    answer = '**规则**\n\n> 完整条件 &gt; 1\n\n来源：[L01-01](https://example.org/rule)'
    event = {'question': 'q', 'captured_at': '2026-11-11T00:00:00+00:00', 'answer': answer, 'upstream_retrieved': []}
    capture = {'captured_at': '2026-11-11T00:01:00Z', 'bot': [{'text': '规则\n完整条件 > 1\n来源：L01-01'}]}
    check('formatting_and_html_entities_normalized', visible_answer(answer) == '规则完整条件>1来源：L01-01')
    check('unique_contemporaneous_full_answer_matches', select_ui_event(capture, 'q', [event]) == event)
    later = {**event, 'captured_at': '2026-11-12T00:00:00+00:00'}
    check('later_same_question_does_not_break_historical_replay', select_ui_event(capture, 'q', [event, later]) == event)
    check('later_event_cannot_attest_old_capture', rejects(lambda: select_ui_event(capture, 'q', [later])))
    bad = copy.deepcopy(capture); bad['bot'][-1]['text'] += '额外虚构结论'
    check('appended_unsupported_answer_rejected', rejects(lambda: select_ui_event(bad, 'q', [event])))
    bad = copy.deepcopy(capture); bad['bot'][-1]['text'] = '完整条件 > 1'
    check('quote_only_partial_answer_rejected', rejects(lambda: select_ui_event(bad, 'q', [event])))
    check('ambiguous_matching_events_rejected', rejects(lambda: select_ui_event(capture, 'q', [event, event])))
    check('wrong_question_rejected', rejects(lambda: select_ui_event(capture, 'other', [event])))
    check('stale_event_rejected', rejects(lambda: select_ui_event({**capture, 'captured_at':'2026-11-11T00:11:00Z'}, 'q', [event])))
    check('naive_capture_timestamp_rejected', rejects(lambda: select_ui_event({**capture, 'captured_at':'2026-11-11T00:01:00'}, 'q', [event])))
    good = {'passed': 2, 'total': 2, 'checks': [{'check':'a','passed':True},{'check':'b','passed':True}]}
    check('actual_check_receipt_accepted', complete_checks(good, 2))
    check('counts_without_individual_checks_rejected', not complete_checks({**good, 'checks': []}, 2))
    check('aggregate_pass_with_failed_row_rejected', not complete_checks({**good, 'checks':[good['checks'][0],{'check':'b','passed':False}]}, 2))
    check('duplicate_check_names_rejected', not complete_checks({**good, 'checks':[good['checks'][0]]*2}, 2))
    check('boolean_counts_rejected', not complete_checks({'passed':True, 'total':True,'checks':[{'check':'a','passed':True}]}, 1))
    task3 = json.loads((ROOT/'reports/rechecks/task1-7-audit-20261112/acceptance/task3-before.json').read_text('utf-8'))
    check('original_real_task3_receipt_accepted', valid_task3_receipt(task3))
    for name, change in [('missing_suite', lambda v:v.update(original_delivery_suite=None)),
                         ('failed_negative', lambda v:v['original_delivery_suite']['negative_cases'][0].update(passed=False)),
                         ('failed_process', lambda v:v['execution'].update(exit_code=1)),
                         ('failed_validation', lambda v:v['canonical_validation']['checks'][0].update(passed=False))]:
        altered = copy.deepcopy(task3); change(altered)
        check('task3_' + name + '_rejected', not valid_task3_receipt(altered))
    result = {'captured_at':datetime.now(timezone.utc).isoformat(), 'status':'PASS' if all(checks.values()) else 'FAIL',
              'passed':sum(checks.values()), 'total':len(checks), 'checks':checks,
              'scope':'Synthetic formatting/path/receipt cases and preserved Task3 receipt. No model or formal test requests.',
              'source_sha256':{n:hashlib.sha256((ROOT/'scripts'/n).read_bytes()).hexdigest() for n in (
                  'delivery_review_io.py','verify_delivery_review_regressions.py','verify_fresh_delivery.py',
                  'verify_task3_isolated.py','verify_answer_quality.py','recheck_fresh_delivery.ps1')}}
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open('x', encoding='utf-8') as h: h.write(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','passed','total')}))
    return 0 if result['status']=='PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
