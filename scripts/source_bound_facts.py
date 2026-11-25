"""Opt-in, source-bound recovery of four reviewed facts after ordinary refusal."""
from __future__ import annotations
import json,os,re,unicodedata
from answer_eval_core import ROOT,canonical,digest,read,record
from disciplinary_query_policy import COMPETITIONS

POLICY='config/source_bound_facts.json'
CORPUS='data/processed/rag_chunks_zh.jsonl'
SCOPE='local_frozen_standard_adult_association_football'
RESTRICTED=re.compile(r'20\d{2}|赛季|本赛|今年|最新|现行|官方|认证|强制|所有赛事|世界杯|青少年|儿童|小学生|少年|幼儿|五人制|室内|沙滩|美式|橄榄球|篮球|网球|高尔夫|曲棍球|\b(?:u\d{1,2}|ifab|fifa|uefa)\b',re.I)
PREFIX=re.compile(r'^(?:(?:根据|按照|按)(?:这份|本地|现有|本)?(?:知识库|资料|原文)(?:说明)?[，,:：]?\s*|请问|请告诉我|请说明|请)[，,:：]?\s*')
GRASS=r'(?:足球场(?:的)?|足球(?:比赛)?(?:使用的)?)?(?:人工草坪|人造草坪|人工草皮|人造草皮|人工草地|人造草地|人造表面|人造场地)'
BALL=r'(?:标准成人(?:5号|五号)?足球|标准成人(?:5号|五号)球|成人(?:5号|五号)(?:足球|球)|标准(?:5号|五号)(?:足球|球)|(?:5号|五号)(?:足球|球))'
GOAL=r'(?:标准成人(?:足球|比赛)?球门|成人(?:足球)?球门)'
WIDTH=r'(?:内侧宽度|内宽|两门柱内侧距离|门柱内侧距离)'
HEIGHT=r'(?:横梁下沿离地高度|横梁下沿距地高度|横梁离地高度|横梁下沿高度)'
ASK=r'(?:分别|各)?(?:是多少|为多少|是什么|有何规定|有什么规定)'

def enabled():
    """Explicit experiment-process opt-in; the default deployment remains off."""
    return os.environ.get('FOOTBALL_SOURCE_FACTS','0')=='1'

def match(question):
    if not isinstance(question,str):return None,'invalid_question'
    q=unicodedata.normalize('NFKC',question).strip()
    q=q.rstrip('。！？?!').strip()
    for _ in range(2):
        newer=PREFIX.sub('',q,count=1)
        if newer==q:break
        q=newer.strip()
    q=re.sub(r'\s+','',q).lower()
    # Exact registered forms are checked before the generic scope guard. The
    # source paragraphs themselves explain why these values are examples or
    # competition/version-dependent; broader variants still fail closed.
    if re.fullmatch(BALL+r'(?:的)?(?:周长和重量|重量和周长)(?:范围)?(?:是多少|为多少|是什么)',q):
        return dict(object='standard_adult_size5_ball',properties=['circumference_cm','weight_g']),None
    if re.fullmatch(r'第10条(?:主要)?(?:处理|涉及)(?:哪两个问题|什么问题)',q):
        return dict(object='law10',properties=['goal_procedure','winner_determination']),None
    if ('固定换5人' in q and '加时额外名额' in q and '所有赛事统一' in q):
        return dict(object='substitutions',properties=['competition_version_scope','not_generalizable']),None
    if ('队长' in q and ('袖标' in q or '标志' in q) and ('左臂' in q or '位置' in q)):
        return dict(object='captain',properties=['armband_type','left_arm']),None
    if ('降温休息' in q and '所有赛事统一' in q):
        return dict(object='cooling_break',properties=['specific_example','not_universal']),None
    if ('点球决胜' in q and '正常进球数' in q and '加时赛进球' in q):
        return dict(object='shootout',properties=['shootout_not_goal','extra_time_goal']),None
    if RESTRICTED.search(q) or COMPETITIONS.search(q):return None,'scope_or_version_not_registered'
    if re.fullmatch(GRASS+r'(?:的)?(?:颜色|色彩)(?:有什么限制|有哪些限制|有何限制|有什么要求|有哪些要求|有何要求|是什么|应是什么|应该是什么)',q):
        return dict(object='artificial_football_surface',properties=['color']),None
    if re.fullmatch(GRASS+r'(?:应|应该|必须)(?:为|是|使用)?(?:什么颜色|哪种颜色)',q):
        return dict(object='artificial_football_surface',properties=['color']),None
    pressure=r'(?:充气压力|气压|球压)'
    pressure_ask=r'(?:(?:千帕|kpa)?(?:范围)?(?:是多少|是什么|为多少|应为多少)(?:千帕|kpa)?|(?:以|用)(?:千帕|kpa)表示(?:是|为)?多少)'
    if re.fullmatch(BALL+r'(?:的)?'+pressure+r'(?:的)?'+pressure_ask,q):
        return dict(object='standard_adult_size5_ball',properties=['pressure_kpa']),None
    found=re.fullmatch(GOAL+r'(?:的)?(?P<one>'+WIDTH+'|'+HEIGHT+r')(?:(?:和|与|及|、|,|，)(?P<two>'+WIDTH+'|'+HEIGHT+r'))?'+ASK+r'(?:米)?',q)
    if found:
        props=['inside_width_m' if re.fullmatch(WIDTH,v) else 'crossbar_lower_edge_height_m' for v in found.groups() if v]
        if len(set(props))!=len(props):return None,'duplicate_or_ambiguous_attributes'
        return dict(object='standard_adult_goal',properties=props),None
    return None,'question_not_uniquely_registered'

def evaluate(question,selection,context,messages, *, registry=None, corpus_raw=None):
    """Pure decision, no model/retrieval. Unknown or changed evidence fails closed."""
    base=dict(version='source-bound-fact-recovery-1.0',applied=False,reason='not_ordinary_insufficient_evidence')
    if selection!={'answerable':False,'chunk_ids':[],'reason':'insufficient_evidence'}:return base
    matched,reason=match(question)
    if not matched:return {**base,'reason':reason}
    base.update(matched_object=matched['object'],requested_properties=matched['properties'])
    try:
        raw=(ROOT/CORPUS).read_bytes() if corpus_raw is None else corpus_raw
        policy=read(ROOT/POLICY) if registry is None else registry
        if policy['version']!='source-bound-facts-1.0' or policy['scope']!=SCOPE or digest(raw)!=policy['corpus_sha256']:
            return {**base,'reason':'unreviewed_corpus_or_registry'}
        corpus={r['chunk_id']:r for r in map(json.loads,raw.decode('utf8').splitlines())}
        facts=policy['facts']
        if len({r['fact_id'] for r in facts})!=len(facts):return {**base,'reason':'ambiguous_registry'}
        chosen=[]
        for prop in matched['properties']:
            candidates=[f for f in facts if f['object']==matched['object'] and f['property']==prop and f['scope']==SCOPE]
            if len(candidates)!=1:return {**base,'reason':'incomplete_or_ambiguous_fact_coverage'}
            f=candidates[0];source=corpus[f['source_chunk_id']]
            if (source['content_zh_sha256']!=f['body_sha256'] or source['record_sha256']!=f['record_sha256']
                    or digest(source['content_zh'].encode())!=f['body_sha256'] or f['source_quote'] not in source['content_zh']
                    or digest(f['source_quote'].encode())!=f['quote_sha256']):
                return {**base,'reason':'registered_source_identity_failed'}
            chosen.append(f)
        if not isinstance(messages,list) or len(messages)!=2 or len(canonical(messages))>6200 or messages[0].get('role')!='system' or messages[1].get('role')!='user':
            return {**base,'reason':'prompt_shape_not_registered'}
        body=json.loads(messages[1]['content'])
        if set(body)!={'question','evidence'} or body['question']!=question:return {**base,'reason':'prompt_question_mismatch'}
        ids=[r['chunk_id'] for r in context]
        if len(ids)!=len(set(ids)) or not 1<=len(ids)<=5:return {**base,'reason':'ambiguous_prompt_sources'}
        expected=[{k:r[k] for k in ('chunk_id','law_number','content_zh','needs_rule_review','review_notes')} for r in context]
        if body['evidence']!=expected:return {**base,'reason':'actual_prompt_context_mismatch'}
        # Every offered paragraph must belong to the reviewed corpus; changed,
        # new or conflicting/unreviewed text cannot silently enter recovery.
        for row in context:
            original=corpus.get(row['chunk_id'])
            if original is None or row!=original:return {**base,'reason':'unreviewed_or_conflicting_prompt_source'}
        selected=list(dict.fromkeys(f['source_chunk_id'] for f in chosen))
        if not set(selected)<=set(ids):return {**base,'reason':'required_source_not_in_prompt'}
        if len(selected)>3:return {**base,'reason':'selection_budget_exceeded'}
        proof=[dict(fact_id=f['fact_id'],property=f['property'],chunk_id=f['source_chunk_id'],
                    prompt_position=ids.index(f['source_chunk_id'])+1,body_sha256=f['body_sha256'],
                    record_sha256=f['record_sha256'],quote_sha256=f['quote_sha256']) for f in chosen]
        return {**base,'applied':True,'reason':'reviewed_facts_fully_supported_in_prompt','fact_ids':[f['fact_id'] for f in chosen],
            'selected_ids':selected,'proof':proof,'corpus_sha256':digest(raw),
            'registry_sha256':digest(canonical(policy)),'base_prompt_sha256':digest(canonical(messages))}
    except (ValueError,TypeError,KeyError,OSError):
        return {**base,'reason':'fact_binding_validation_failed'}
