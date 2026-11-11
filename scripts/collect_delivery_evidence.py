"""Export nonsecret current checks and clearly labelled historical UI evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--audit-report', required=True)
    parser.add_argument('--regression-report', required=True)
    parser.add_argument('--startup-log')
    args = parser.parse_args()
    runtime = args.runtime_root.resolve(strict=True)
    audit_path = (runtime / args.audit_report).resolve(strict=True)
    regression_path = (ROOT / args.regression_report).resolve(strict=True)
    if not audit_path.is_relative_to(runtime / '.tmp') or not regression_path.is_relative_to(ROOT):
        raise ValueError('Use an audit under runtime .tmp and a regression inside this checkout')
    now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
    accepted, evidence = ROOT / 'reports/acceptance', ROOT / 'reports/evidence'
    accepted.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)

    def write(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')

    audit_raw = audit_path.read_bytes()
    audit = json.loads(audit_raw)
    public_audit = json.loads(json.dumps(audit, ensure_ascii=False).replace(str(runtime).replace('\\', '\\\\'), '<LOCAL_RUNTIME>'))
    public_audit['review_context'] = {
        'current_runtime': 'Original local environment; source/config hashes checked below',
        'audit_source_sha256': sha(audit_raw),
        'ui_evidence_time_scope': 'Historical real UI questions, not fresh browser questions',
        'fresh_checks': 'Current loopback services, installed packages, database, frozen corpus, source provenance',
    }
    write(accepted / 'task1_task2_recheck.json', public_audit)

    regression_raw = regression_path.read_bytes()
    regression = json.loads(regression_raw)
    summary = {'generated_at': now, 'scope': 'Fresh development regressions; not a locked benchmark or expert judgement',
               'private_full_output_sha256': sha(regression_raw), 'passed': regression['passed'], 'total': regression['total'],
               'cases': [{'id': r['case']['id'], 'question': r['question'], 'captured_at': r['captured_at'],
                          'status': r['status'], 'passed': r['automated_passed'], 'errors': r['automated_errors'],
                          'citation_chunk_ids': [c['chunk_id'] for c in r['citations']],
                          'answer_characters': len(r['answer']), 'answer_sha256': sha(r['answer'].encode('utf-8'))}
                         for r in regression['results']]}
    write(accepted / 'development_regression_summary.json', summary)

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    services = {}
    for name, url in [('application', 'http://127.0.0.1:7860/'), ('models', 'http://127.0.0.1:11434/api/tags')]:
        try:
            with opener.open(url, timeout=8) as response:
                data = response.read()
                services[name] = {'url': url, 'http_status': response.status, 'body_sha256': sha(data)}
                if name == 'models':
                    services[name]['models'] = [{k: row[k] for k in ('name', 'digest', 'size') if k in row}
                                               for row in json.loads(data)['models']]
        except Exception as exc:
            services[name] = {'url': url, 'error': f'{type(exc).__name__}: {exc}'}
    write(evidence / 'current_services.json', {'captured_at': now, 'services': services})

    historical = runtime / 'reports/answer-quality-ui-evidence-2026-11-11.json'
    raw = historical.read_bytes()
    ui = json.loads(raw)
    # Do not export raw DOM, previous conversations, account state or all answers.
    write(evidence / 'historical_ui_three_questions.json', {
        'scope': 'Historical UI proof; original dates retained. Current UI startup is checked separately.',
        'source_sha256': sha(raw), 'captured_at': ui['captured_at'], 'url': ui['url'], 'http_status': ui['http_status'],
        'information_panel_present': ui['information_panel_present'],
        'qa': [{'question_id': q['question_id'], 'question': q['question'],
                'answer_characters': len(q['answer']), 'answer_sha256': sha(q['answer'].encode('utf-8')),
                'information_panel_present': q['information_panel_present'], 'source_links': q['source_links']}
               for q in ui['qa']]})

    matching = []
    for name in ['scripts/run_kotaemon_local.py', 'scripts/run_baseline_check.ps1',
                 'scripts/kotaemon_runtime_env.py', 'scripts/check_kotaemon_runtime.py',
                 'scripts/football_evidence.py', 'scripts/football_quality_pipeline.py', 'config/answer_quality.json']:
        a, b = (ROOT / name).read_bytes(), (runtime / name).read_bytes()
        matching.append({'path': name, 'checkout_sha256': sha(a), 'runtime_sha256': sha(b), 'same': a == b})
    write(evidence / 'runtime_code_correspondence.json', {'captured_at': now, 'files': matching,
          'scope': 'Current runtime is external; does not claim dependencies installed in public checkout'})

    if args.startup_log:
        log = (ROOT / args.startup_log).resolve(strict=True)
        if not log.is_relative_to(ROOT / '.runtime'):
            raise ValueError('Use a private startup log inside this checkout .runtime')
        content = log.read_bytes()
        snapshot = ROOT / '.runtime/task123-review-20261111/startup-frozen.stdout.log'
        snapshot.write_bytes(content)
        lines = content.decode('utf-8', errors='replace').splitlines()
        tokens = ('Local runtime:', 'Football answer profile:', 'Pinned upstream:', 'Document store:',
                  'Vector store:', 'Running on local URL:', 'GraphRAG dependencies not installed.',
                  'LightRAG dependencies not installed.', 'Nano-GraphRAG dependencies not installed.')
        selected = [x.replace(str(runtime), '<LOCAL_RUNTIME>') for x in lines if any(t in x for t in tokens)]
        (evidence / 'task2_startup.txt').write_text('Captured at: ' + now + '\nScope: selected nonsecret lines; paths redacted.\n'
            + 'Original captured log SHA-256: ' + sha(content) + '\n' + '\n'.join(selected) + '\n', 'utf-8')

    task3 = json.loads((accepted / 'task3_recheck.json').read_text('utf-8'))
    contracts = json.loads((accepted / 'answer_quality_contract.json').read_text('utf-8'))
    ok = (audit['status'] == 'PASS' and all(x['same'] for x in matching)
          and regression['passed'] == regression['total'] == 16 and contracts['passed'] == contracts['total'] == 19
          and task3['status'] == 'PASS' and all(v.get('http_status') == 200 for v in services.values()))
    result = {'generated_at': now, 'status': 'PASS' if ok else 'FAIL',
              'task1': audit['task1_status'], 'task2': audit['task2_status'], 'task3': task3['status'],
              'task1_task2_checks': [sum(c['passed'] for c in audit['checks']), len(audit['checks'])],
              'task3_dataset_checks': [task3['canonical_validation']['passed_checks'], task3['canonical_validation']['total_checks']],
              'task3_delivery_checks': [task3['original_delivery_suite']['positive_checks_passed'], task3['original_delivery_suite']['positive_checks_total']],
              'corrupt_cases_rejected': [task3['original_delivery_suite']['negative_cases_rejected'], task3['original_delivery_suite']['negative_cases_total']],
              'development_regression': [regression['passed'], regression['total']],
              'answer_contracts': [contracts['passed'], contracts['total']],
              'limitations': ['UI three-question evidence is historical, with new live service/backend checks.',
                             'No fresh dependency installation in the public checkout.',
                             'Full corpus and model outputs remain local; formal RAG B0 and tasks 4-14 are not complete.']}
    write(accepted / 'task123_recheck_summary.json', result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
