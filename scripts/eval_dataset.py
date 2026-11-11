"""Common task 4 data/provenance helpers; no model or retrieval calls."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / 'data/eval'
CORPUS = ROOT / 'data/processed/rag_chunks_zh.jsonl'
VERSION = 'football-eval-0.1.0'
REVIEW_LEDGER = ROOT / '.runtime/eval_review/reviews.jsonl'
CHECKLIST = ('support_and_conditions', 'negative_reasons', 'source_and_version', 'answer_or_refusal')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def load_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text('utf-8').splitlines() if line.strip()]


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def write_jsonl(path, values):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b''.join(canonical(row) + b'\n' for row in values))


def source_ref(row):
    return {key: row[key] for key in (
        'chunk_id', 'source_id', 'source_url', 'source_lines', 'source_revision_id',
        'source_revision_verified', 'source_revision_status', 'content_zh_sha256',
        'needs_rule_review', 'review_notes', 'expert_reviewed', 'official_translation',
        'license', 'license_url', 'source_attribution')}


def question_digest(row):
    return digest(canonical({k: v for k, v in row.items() if k != 'annotation_sha256'}))


def active_reviews(rows, ledger=REVIEW_LEDGER, allow_synthetic=False):
    """An AI draft, stale signature or incomplete checklist is never approval."""
    if allow_synthetic and not Path(ledger).resolve().is_relative_to(ROOT/'.tmp'):
        raise ValueError('Synthetic reviews may only be exercised inside ignored .tmp fixtures')
    items = load_jsonl(ledger) if Path(ledger).exists() else []
    latest = {}
    for event in items:
        latest[event.get('question_id')] = event
    result = {}
    for row in rows:
        event = latest.get(row['question_id'], {})
        try:
            instant = datetime.fromisoformat(event.get('reviewed_at', '').replace('Z', '+00:00'))
            time_valid = instant.tzinfo is not None and instant <= datetime.now(timezone.utc)
        except (ValueError, TypeError):
            time_valid = False
        valid = (event.get('reviewer_type') == 'human'
                 and (not event.get('fixture_only') or allow_synthetic)
                 and event.get('decision') == 'approved'
                 and event.get('annotation_sha256') == row['annotation_sha256']
                 and isinstance(event.get('reviewer_name'), str) and len(event['reviewer_name'].strip()) >= 2
                 and time_valid
                 and all(event.get('checklist', {}).get(key) is True for key in CHECKLIST))
        result[row['question_id']] = {'approved': valid, 'event': event}
    return result
