"""Verify the independently installed checkout and fresh browser evidence.

Read full answers only from ignored local files; publish hashes and check
results. This supplements the unchanged original task criteria, not a new
accuracy benchmark. The browser questions must actually be submitted first.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import re
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from kotaemon_runtime_env import configure_local_runtime

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'third_party/kotaemon-v0.12.0'
PIN = '9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text('utf-8'))


def git(*args):
    return subprocess.check_output(['git', '-C', str(UPSTREAM), *args]).decode().strip()


def private_path(value):
    path = (ROOT / value).resolve(strict=True)
    if not path.is_relative_to(ROOT / '.runtime'):
        raise ValueError('Full answers and DOM must remain under ignored .runtime/')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ui-capture', required=True)
    parser.add_argument('--regression-report', required=True)
    parser.add_argument('--app-url', default='http://127.0.0.1:7861/')
    parser.add_argument('--original-root', type=Path)
    parser.add_argument('--original-snapshot', type=Path)
    args = parser.parse_args()
    address = urlsplit(args.app_url)
    if address.hostname not in ('127.0.0.1', 'localhost') or address.scheme != 'http':
        raise ValueError('Only the local application is accepted')
    checks = []

    def record(name, passed, detail=None):
        checks.append({'check': name, 'passed': bool(passed), 'detail': detail})

    record('project_virtualenv', Path(sys.prefix).resolve() == (ROOT / '.venv').resolve())
    record('standalone_python_inside_new_checkout', Path(sys.base_prefix).resolve().is_relative_to(ROOT / '.runtime/python'))
    record('python_3_10_22', sys.version_info[:3] == (3, 10, 22))
    record('pinned_official_clean_upstream', git('rev-parse', 'HEAD') == PIN and not git('status', '--porcelain', '--untracked-files=no')
           and git('remote', 'get-url', 'origin') == 'https://github.com/Cinnamon/kotaemon.git')
    assets = configure_local_runtime()
    record('own_verified_tokenizer_cache', Path(assets['tiktoken_cache']).is_relative_to(ROOT / '.cache'))
    record('own_real_nltk_resources', Path(assets.get('nltk_data', '/')).is_relative_to(ROOT / '.cache'))

    requirements_path = ROOT / '.runtime/install-local/runtime-requirements.txt'
    requirements = []
    for line in requirements_path.read_text('utf-8').splitlines():
        if re.match(r'^[A-Za-z0-9_.-]+==', line):
            req = Requirement(line.rstrip(' \\'))
            if req.marker is None or req.marker.evaluate():
                requirements.append(req)
    installed = list(metadata.distributions())
    versions = {canonicalize_name(d.metadata['Name']): d.version for d in installed}
    mismatch = [str(req) for req in requirements if versions.get(canonicalize_name(req.name), '') not in req.specifier]
    record('all_exported_locked_runtime_versions', len(requirements) >= 250 and not mismatch,
           {'active_requirements': len(requirements), 'installed_distributions': len(installed), 'mismatches': mismatch,
            'export_sha256': sha(requirements_path.read_bytes()), 'upstream_uv_lock_sha256': sha((UPSTREAM / 'uv.lock').read_bytes())})
    foreign = [d.metadata['Name'] for d in installed if not Path(d.locate_file('')).resolve().is_relative_to(ROOT)]
    record('all_package_locations_inside_new_checkout', not foreign, {'foreign_packages': foreign})
    editables = {}
    for name in ('kotaemon', 'ktem'):
        direct = json.loads(metadata.distribution(name).read_text('direct_url.json'))
        editables[name] = direct['url'].replace('file:///', '')
    record('editable_sources_inside_pinned_new_checkout', all(
        Path(unquote(path)).resolve().is_relative_to(UPSTREAM) for path in editables.values()))

    lock = read_json(ROOT / 'data/manifests/task1_task2_baseline_lock.json')
    failures = [row['path'] for row in lock['files'] if sha((ROOT / row['path']).read_bytes()) != row['sha256']]
    record('ten_frozen_specification_and_corpus_files', len(lock['files']) == 10 and not failures, failures)
    failed_prefixes = [row['path'] for row in lock['append_only_files'] if sha((ROOT / row['path']).read_bytes()[:row['original_size_bytes']]) != row['original_prefix_sha256']]
    record('four_historical_report_prefixes_preserved', len(lock['append_only_files']) == 4 and not failed_prefixes, failed_prefixes)
    inventory = read_json(ROOT / 'data/manifests/local_data_files.json')['files']
    bad_data = [row['path'] for row in inventory if sha((ROOT / row['path']).read_bytes()) != row['sha256']]
    record('all_61_local_corpus_files_preserved', len(inventory) == 61 and not bad_data, bad_data)

    database = UPSTREAM / 'ktem_app_data/user_data/sql.db'
    connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    normal = connection.execute('select id,admin from user where username=?', ('yanyanbeen',)).fetchone()
    admin = connection.execute('select id,admin from user where username=?', ('admin',)).fetchone()
    sources = [dict(r) for r in connection.execute('select id,name,path,size,user from index__1__source')]
    own = [r for r in sources if normal and r['user'] == normal['id']]
    record('ordinary_account_is_not_admin', normal and normal['admin'] == 0)
    record('five_files_owned_by_ordinary_account', len(own) == len(sources) == 5)
    record('admin_private_files_not_transferred', admin and not any(r['user'] == admin['id'] for r in sources))
    md = [r for r in lock['files'] if re.search(r'/0[1-5]_.+\.md$', r['path'])]
    expected = {Path(r['path']).name: r for r in md}
    files_match = len(own) == 5 and set(r['name'] for r in own) == set(expected)
    for row in own:
        saved = UPSTREAM / 'ktem_app_data/user_data/files/index_1' / row['path']
        files_match = files_match and row['path'] == expected.get(row['name'], {}).get('sha256') and saved.is_file() and sha(saved.read_bytes()) == row['path']
    record('five_uploaded_markdown_files_match_frozen_bytes', files_match)
    # Upstream does not populate relation.user; ownership lives on Source.
    chunk_count = connection.execute("select count(*) from index__1__index i join index__1__source s on s.id=i.source_id where i.relation_type='document' and s.user=?", (normal['id'],)).fetchone()[0]
    record('temporary_ui_index_has_50_chunks', chunk_count == 50, {'chunks': chunk_count, 'formal_RAG_B0': False})
    initial = read_json(ROOT / 'reports/evidence/fresh_database_initial.json')
    record('fresh_database_started_empty', initial['new_database'] and not initial['copied_old_database'] and initial['source_files_before_upload'] == 0)
    # Model registries are examined without exposing their JSON specs or keys.
    table_names = {r[0] for r in connection.execute("select name from sqlite_master where type='table'")}
    pools = {}
    for name in sorted(table_names):
        if name in ('llm_table', 'embedding', 'reranking'):
            pools[name] = [r[0] for r in connection.execute(f'select name from "{name}"')]
    record('local_model_registries_only', pools == {'embedding': ['ollama'], 'llm_table': ['ollama'], 'reranking': []})
    indexes = [json.loads(r[0]) for r in connection.execute('select config from ktem__index')]
    record('single_private_file_collection', len(indexes) == 1 and indexes[0].get('private') is True)
    connection.close()

    from football_evidence import get_engine
    from run_answer_quality_regression import structural_checks
    engine = get_engine()
    cases = {r['id']: r for r in (json.loads(x) for x in (ROOT / 'data/quality_regression/development_cases.jsonl').read_text('utf-8').splitlines())}
    capture_path = private_path(args.ui_capture)
    captures = read_json(capture_path)
    events = [json.loads(x) for x in (ROOT / '.cache/football-quality/ui-events.jsonl').read_text('utf-8').splitlines() if x.strip()]
    ui_summary = []
    for number, item in enumerate(captures, 1):
        case = cases[item['question_id']]
        found = [r for r in events if r['question'] == case['question'] and 'upstream_retrieved' in r]
        result = found[-1] if found else None
        errors = structural_checks(engine, result) if result else ['UI journal missing']
        if result:
            cites = {r['chunk_id'] for r in result['citations']}
            for group in case.get('required_chunk_groups', []):
                if not cites.intersection(group): errors.append('missing required citation group')
            if cites.intersection(case.get('forbidden_chunks', [])): errors.append('forbidden citation')
            if result['status'] != case['expected_status']: errors.append('unexpected status')
            delta = (datetime.fromisoformat(item['captured_at'].replace('Z', '+00:00')) - datetime.fromisoformat(result['captured_at'])).total_seconds()
            if not 0 <= delta <= 600: errors.append('journal/DOM timestamps not contemporaneous')
            bot = item['bot'][-1]['text'] if item['bot'] else ''
            panels = '\n'.join(r['text'] for r in item['panels'])
            for cite in result['citations']:
                if not all(q in bot and q in panels for q in cite['quotes']): errors.append('complete source paragraph absent from visible answer/panel')
                if not any(cite['chunk_id'] in x['text'] and x['href'] == cite['source_url'] for x in item['links']): errors.append('citation link absent from DOM')
            if len(item['bot']) != number or item['resources_tab'] or item['url'] != args.app_url: errors.append('unexpected browser user/page state')
            if not result['upstream_retrieved'] or not result['allowed_document_ids']: errors.append('file scope not exercised')
            owned_ids = {r['id'] for r in own}
            if any(x['file_id'] not in owned_ids for x in result['upstream_retrieved']): errors.append('retrieval crossed owned file scope')
        record('fresh_browser_' + item['question_id'], not errors, {'errors': errors})
        ui_summary.append({'question_id': item['question_id'], 'question': case['question'], 'captured_at': item['captured_at'],
                           'passed': not errors, 'citation_chunk_ids': sorted(cites) if result else [],
                           'answer_sha256': sha(result['answer'].encode()) if result else None,
                           'visible_answer_sha256': sha(item['bot'][-1]['text'].encode()) if item['bot'] else None,
                           'citation_urls': sorted({c['source_url'] for c in result['citations']}) if result else []})
    record('exactly_three_new_browser_questions', [x['question_id'] for x in captures] == ['Q1', 'Q2', 'Q3'])
    regression_path = private_path(args.regression_report)
    regression = read_json(regression_path)
    record('fresh_16_development_regressions', regression['passed'] == regression['total'] == 16 and all(not structural_checks(engine, r) for r in regression['results']))
    contracts = read_json(ROOT / 'reports/acceptance/fresh_answer_quality_contract.json')
    record('fresh_19_evidence_contracts', contracts['passed'] == contracts['total'] == 19)
    task3 = read_json(ROOT / 'reports/acceptance/task3_fresh_environment.json')
    record('task3_unchanged_original_suite', task3['status'] == 'PASS' and task3['input_files_unchanged'])
    stderr = (ROOT / '.runtime/fresh-runtime-20261111/app-fixed.stderr.log').read_text('utf-8', errors='replace')
    disallowed = [x for x in ('Traceback', 'No models in pool', 'nltk_data', 'huggingface.co', 'GraphRAG dependencies not installed') if x in stderr]
    record('no_runtime_failure_or_optional_remote_tokenizer_retry', not disallowed, {'errors': disallowed,
           'informational_warning': 'Chroma clamps requested 100 candidates to the actual 50 stored chunks.'})
    record('stderr_contains_only_known_chroma_capacity_notice', all(
        not line.strip() or line.startswith('Number of requested results 100 is greater than number of elements in index 50, updating n_results = 50')
        for line in stderr.splitlines()))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(args.app_url, timeout=10) as response:
        record('live_independent_application_http_200', response.status == 200)
    with opener.open('http://127.0.0.1:11434/api/tags', timeout=10) as response:
        models = {x['name']: x['digest'] for x in json.load(response)['models']}
    record('original_ollama_model_digests', models.get('qwen2.5:3b') == '357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b'
           and models.get('bge-m3:latest') == '7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab')
    if bool(args.original_root) != bool(args.original_snapshot):
        raise ValueError('Original root and pre-change snapshot must be provided together')
    if args.original_root:
        snapshot = read_json(args.original_snapshot)
        changed = [name for name, checksum in snapshot.items() if sha((args.original_root / name).read_bytes()) != checksum]
        record('original_178_static_files_unchanged', len(snapshot) == 178 and not changed, {'files': len(snapshot), 'changed': changed})
        record('original_project_has_no_root_git', not (args.original_root / '.git').exists())
    evidence = ROOT / 'reports/evidence/fresh_ui_three_questions.json'
    evidence.write_text(json.dumps({'scope': 'Fresh ordinary-account browser UI submission; private DOM and full outputs excluded.',
                                   'url': args.app_url, 'private_capture_sha256': sha(capture_path.read_bytes()), 'qa': ui_summary}, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    result = {'captured_at': datetime.now(timezone.utc).isoformat(), 'status': 'PASS' if all(x['passed'] for x in checks) else 'FAIL',
              'scope': 'New checkout core Ollama runtime, fresh browser acceptance and unchanged tasks 1-3; not a locked quality benchmark.',
              'passed': sum(x['passed'] for x in checks), 'total': len(checks), 'checks': checks,
              'runtime_code_sha256': {name: sha((ROOT / name).read_bytes()) for name in (
                  'scripts/run_kotaemon_local.py', 'scripts/kotaemon_runtime_env.py', 'scripts/kotaemon_local_retrieval.py',
                  'scripts/football_quality_pipeline.py', 'scripts/football_evidence.py', 'config/answer_quality.json',
                  'scripts/install_local_runtime.ps1', 'scripts/run_baseline_check.ps1', 'scripts/prepare_kotaemon_assets.py')},
              'private_regression_sha256': sha(regression_path.read_bytes()),
              'limitations': ['Core runtime from original lock; optional advanced torch/graph/dev extras not installed.',
                              'Ollama model service is reused explicitly; no old virtualenv or account/index database used.',
                              'Development question checks do not measure expert accuracy, Recall, MRR or nDCG.',
                              'Wikipedia/translation/version review qualifications remain unchanged; tasks 4-14 remain open.']}
    (ROOT / 'reports/acceptance/fresh_delivery.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps({'status': result['status'], 'passed': result['passed'], 'total': result['total'], 'failed': [x for x in checks if not x['passed']]}, ensure_ascii=False))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
