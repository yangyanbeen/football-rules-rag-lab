"""Conservative business gate for competition-specific yellow-card suspensions.

Only the effective request text is examined. No evaluation labels, source IDs,
retrieval results or model outputs participate in this decision.
"""
import re
import unicodedata

RULE = 'cumulative_yellow_suspension_missing_parameters_v1'
PUBLIC_REASON = 'insufficient_evidence'
NUMBER = r'[零一二三四五六七八九十百两\d]+'
COMPETITIONS = re.compile(
    r'中国足球协会超级联赛|英格兰足球超级联赛|中国足球超级联赛|'
    r'欧洲冠军联赛|国际足联世界杯|中国足协杯|英格兰足总杯|'
    r'中超|中甲|中乙|英超|英冠|西甲|德甲|意甲|法甲|欧冠|欧联杯?|世界杯|亚洲杯|欧洲杯|足总杯')
GENERAL = re.compile(r'(为什么|为何|原因|解释|说明|由谁|谁来|是否|有没有|有无).*(统一|通用|取决|决定|因赛事|因联赛|不同赛事|不一样)')
PLACEHOLDER = re.compile(r'某|未指明|不明确|未知|未提供|任何|所有|各个|这个|那个|本联赛|该联赛')
YEAR = r'20\d{2}(?:[/\-–至](?:20)?\d{2})?'
SEASON = re.compile(r'(' + YEAR + r')(?:\s*(?:赛季|年))|(?:赛季\s*[:：为是]?\s*)(' + YEAR + r')')


def _missing_explicitly(text, field):
    names = r'(?:赛事|联赛|比赛名称)' if field == 'competition' else r'(?:赛季|年份)'
    for match in re.finditer(r'(?:没有|没|未|不知|未知|不清楚|缺少)([^，,。；;?？]{0,8})' + names, text):
        if not re.search(r'20\d{2}', match.group(1)):
            return True
    return bool(re.search(names + r'.{0,3}(?:未给|未知|不详|未定|不明确|不清楚)', text))


def suspension_request(question):
    text = unicodedata.normalize('NFKC', question).strip()
    if GENERAL.search(text) or re.search(r'取决于什么|由谁决定|谁来决定|有什么区别|有何区别|如何区分', text):
        return False
    if re.search(r'同一场|同场|一场比赛|本场', text) and not re.search(r'跨场|跨多场|多场比赛|不同比赛', text):
        return False
    cumulative = re.search(r'累计|累积|累計|跨场|跨多场|多场比赛', text)
    yellow = re.search(r'黄牌|黄卡', text)
    implicit_cards = re.search(r'(?:累计|累积)\s*' + NUMBER + r'\s*张', text) and not re.search(r'红牌|红卡', text)
    penalty = re.search(r'停赛|禁赛|停几场|停多少场|停几轮|停多少轮', text)
    specific = re.search(r'几场|多少场|几轮|多少轮|多少场次|停赛场数|禁赛场数|'
                         r'(?:停赛|禁赛).{0,8}(?:多久|多长|具体|确定|一定|' + NUMBER + r'\s*[场轮])|'
                         r'(?:具体|确定|一定).{0,8}(?:停赛|禁赛)', text)
    return bool(cumulative and (yellow or implicit_cards) and penalty and specific)


def evaluate_suspension_query(question):
    """Return a trace decision only for an unambiguous concrete missing-input query."""
    if not suspension_request(question):
        return None
    text = unicodedata.normalize('NFKC', question).strip()
    competition = None
    found = COMPETITIONS.search(text)
    if found:
        competition = found.group()
    else:
        named = re.search(r'(?:赛事|联赛名称)\s*[:：为是]\s*([^，,。;；?？\s]{2,24})', text)
        if named and not PLACEHOLDER.search(named.group(1)):
            competition = named.group(1)
        if competition is None:
            named = re.search(r'(?:^|[，,:：；;\s]|请问|关于|针对|按)([\u4e00-\u9fffA-Za-z0-9·]{2,20}(?:联赛|杯赛|锦标赛|杯))'
                              r'(?=的|中|[，,:：；;\s]|20\d{2}|累计|累积|跨场|赛季)', text)
            if named and not PLACEHOLDER.search(named.group(1)) and named.group(1) not in ('足球联赛','足球杯赛','职业联赛'):
                competition = named.group(1)
    if _missing_explicitly(text, 'competition'):
        competition = None
    match = SEASON.search(text)
    season = next((v for v in match.groups() if v), None) if match else None
    # Common season ranges are sufficient even when the literal word 赛季 is omitted.
    if season is None:
        match = re.search(r'20\d{2}[/\-](?:20)?\d{2}', text)
        season = match.group() if match else None
    if _missing_explicitly(text, 'season'):
        season = None
    fields = {'competition': competition, 'season': season}
    missing = [key for key, value in fields.items() if value is None]
    if not missing:
        return None
    return {'rule': RULE, 'intent': 'cross_match_yellow_suspension_count',
            'missing_fields': missing, 'parameters': fields}


def refusal_message(decision):
    missing = decision['missing_fields']
    fields = '和'.join('赛事名称' if field == 'competition' else '赛季' for field in missing)
    return '需要知道具体赛事和赛季，才能确定累计黄牌的停赛场数。请补充' + fields + '。'
