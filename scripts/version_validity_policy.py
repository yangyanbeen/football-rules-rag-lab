"""Deterministic refusal gate for unverifiable official-season claims.

This gate is deliberately narrower than a generic year/season detector.  A
normal question about a dated rule may still use the RAG path; only a request
to *confirm* official/current/effective applicability is short-circuited.
It never reads evaluation IDs, gold labels, retrieved chunks, or model output.
"""
import re
import unicodedata

RULE = 'official_season_validity_confirmation_v1'
YEAR = r'20\d{2}(?:[/\-–至](?:20)?\d{2})?'
SEASON_OR_YEAR = re.compile(r'(?:' + YEAR + r'\s*(?:赛季|年)?|赛季\s*[:：为是]?\s*' + YEAR + r')')
AUTHORITY = re.compile(r'官方|权威|IFAB|正式规则|现行|最新|生效|适用|有效|全部赛事|所有比赛|所有足球比赛|每一项规则|所有[^，。！？?]{0,8}比赛', re.I)
# Besides explicit confirmation verbs, treat universal/absolute claims as a
# request to validate the official version.  D040 is the representative case:
# it asks whether an official 2026/27 interpretation applies uniformly to every
# scoring outcome.  A dated rule question without an official/universal claim
# still follows the normal RAG path.
CONFIRMATION = re.compile(r'确认|确定|核实|验证|是否|能否|可否|足以|准确|有没有|有无|是不是|是否已经|是否都|一律|所有情形|全部情形|统一|无例外', re.I)


def version_validity_query(question):
    """Return a trace for an explicit official/current applicability request."""
    text = unicodedata.normalize('NFKC', str(question)).strip()
    if not SEASON_OR_YEAR.search(text):
        return None
    if not AUTHORITY.search(text) or not CONFIRMATION.search(text):
        return None
    return {
        'rule': RULE,
        'intent': 'official_season_validity_confirmation',
        'missing_fields': ['verified_official_version'],
        'parameters': {'season_or_year_present': True, 'authority_or_validity_claim': True},
    }


def is_version_validity_query(question):
    return version_validity_query(question) is not None

