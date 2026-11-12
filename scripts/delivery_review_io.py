"""Small, dependency-free guards for repeatable delivery reviews."""
from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path


def new_report(root: Path, value: str | Path) -> Path:
    path = (root / value).resolve()
    if path.suffix != '.json' or not any(path.is_relative_to(root / p) for p in ('reports', '.tmp')):
        raise ValueError('Use a JSON report under reports/ or .tmp/')
    if path.exists():
        raise ValueError('Refusing to overwrite an existing report')
    return path


def new_report_directory(root: Path, value: str | Path) -> Path:
    path = (root / value).resolve()
    if path == root / 'reports' or not path.is_relative_to(root / 'reports'):
        raise ValueError('Use a new subdirectory under reports/')
    # Reserve all outputs together, before any runtime or model work.
    path.mkdir(parents=True, exist_ok=False)
    return path


def visible_answer(answer: str) -> str:
    """Normalize only the formatting emitted by football_evidence.render_answer."""
    value = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', answer)
    value = re.sub(r'\*\*|^> ?', '', value, flags=re.MULTILINE)
    return re.sub(r'\s+', '', html.unescape(value))


def complete_checks(receipt: dict, count: int, passed_key='passed', total_key='total') -> bool:
    checks = receipt.get('checks', [])
    return (type(receipt.get(passed_key)) is int and type(receipt.get(total_key)) is int
            and receipt[passed_key] == receipt[total_key] == count
            and isinstance(checks, list) and len(checks) == count
            and all(isinstance(x, dict) and x.get('passed') is True for x in checks)
            and len({x.get('check') for x in checks}) == count)


def valid_task3_receipt(receipt: dict) -> bool:
    suite = receipt.get('original_delivery_suite') or {}
    validation = receipt.get('canonical_validation') or {}
    cases = suite.get('negative_cases', [])
    return (receipt.get('status') == 'PASS' and receipt.get('input_files_unchanged') is True
            and receipt.get('execution', {}).get('exit_code') == 0
            and complete_checks(validation, 18, 'passed_checks', 'total_checks')
            and complete_checks(suite, 8, 'positive_checks_passed', 'positive_checks_total')
            and suite.get('negative_cases_rejected') == suite.get('negative_cases_total') == 16
            and isinstance(cases, list) and len(cases) == 16
            and all(c.get('passed') is True for c in cases))


def select_ui_event(capture: dict, question: str, events: list[dict]) -> dict:
    timestamp = datetime.fromisoformat(capture['captured_at'].replace('Z', '+00:00'))
    if timestamp.tzinfo is None:
        raise ValueError('Browser capture requires an aware timestamp')
    bot = capture['bot'][-1]['text']
    candidates = []
    for event in events:
        if event.get('question') != question or 'upstream_retrieved' not in event:
            continue
        generated = datetime.fromisoformat(event['captured_at'].replace('Z', '+00:00'))
        if generated.tzinfo is None:
            raise ValueError('UI event requires an aware timestamp')
        if 0 <= (timestamp - generated).total_seconds() <= 600 and visible_answer(event['answer']) == re.sub(r'\s+', '', bot):
            candidates.append(event)
    if len(candidates) != 1:
        raise ValueError('Need exactly one contemporaneous UI event with the complete visible answer')
    return candidates[0]
