"""Experimental E7 schema and exhaustive, deterministic evidence coverage selection.

No grading labels, question IDs or football-specific rules belong in this module.
Partial evidence follows the existing extractive contract: render supported text;
refuse with the existing enum only when no requirement has a supporting ID.
"""
import itertools
import json

MAX_REQUIREMENTS = 8
MAX_REQUIREMENT_CHARS = 120


def mapping_schema(offered, limit=3):
    validate_offered(offered, limit)
    return {
        'type': 'object',
        'properties': {'requirements': {
            'type': 'array', 'minItems': 1, 'maxItems': MAX_REQUIREMENTS,
            'items': {
                'type': 'object',
                'properties': {
                    'requirement': {'type': 'string', 'minLength': 1,
                                    'maxLength': MAX_REQUIREMENT_CHARS},
                    'supporting_ids': {'type': 'array', 'minItems': 0,
                                       'maxItems': len(offered),
                                       'items': {'type': 'string', 'enum': list(offered)}},
                },
                'required': ['requirement', 'supporting_ids'],
                'additionalProperties': False,
            },
        }},
        'required': ['requirements'], 'additionalProperties': False,
    }


def validate_offered(offered, limit):
    if (not isinstance(offered, list) or not 1 <= len(offered) <= 5
            or any(not isinstance(c, str) or not c.strip() for c in offered)
            or len(set(offered)) != len(offered) or type(limit) is not int
            or not 1 <= limit <= 3):
        raise ValueError('Invalid offered IDs or selection cap')


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate JSON property')
        value[key] = item
    return value


def parse_mapping(content, offered, limit=3):
    validate_offered(offered, limit)
    value = json.loads(content, object_pairs_hook=unique_object)
    if not isinstance(value, dict) or set(value) != {'requirements'}:
        raise ValueError('Invalid mapping object')
    reqs = value['requirements']
    if not isinstance(reqs, list) or not 1 <= len(reqs) <= MAX_REQUIREMENTS:
        raise ValueError('Invalid requirement count')
    normalized = []
    seen = set()
    for req in reqs:
        if not isinstance(req, dict) or set(req) != {'requirement', 'supporting_ids'}:
            raise ValueError('Invalid requirement object')
        text, ids = req['requirement'], req['supporting_ids']
        if (not isinstance(text, str) or not text.strip()
                or len(text) > MAX_REQUIREMENT_CHARS):
            raise ValueError('Invalid requirement text')
        key = ''.join(text.split()).casefold()
        if key in seen:
            raise ValueError('Duplicate requirement text')
        seen.add(key)
        if (not isinstance(ids, list) or len(ids) > len(offered)
                or any(not isinstance(c, str) or c not in offered for c in ids)):
            raise ValueError('Unknown/unoffered supporting ID')
        normalized.append({'requirement': text, 'supporting_ids': list(dict.fromkeys(ids))})
    candidates = []
    for size in range(limit + 1):
        for indices in itertools.combinations(range(len(offered)), size):
            ids = [offered[i] for i in indices]
            mask = [bool(set(ids).intersection(r['supporting_ids'])) for r in normalized]
            candidates.append(((-sum(mask), size, indices), ids, mask))
    _, selected, covered = min(candidates, key=lambda item: item[0])
    selection = {'answerable': bool(selected), 'chunk_ids': selected,
                 'reason': None if selected else 'insufficient_evidence'}
    return selection, {
        'requirements': normalized, 'model_requirement_coverage': covered,
        'covered_count': sum(covered), 'requirement_count': len(normalized),
        'selected_ids': selected, 'selection': selection,
        'objective': 'maximum mapped requirements; fewer IDs; original offered order',
        'semantics_verified_by_program': False,
    }
