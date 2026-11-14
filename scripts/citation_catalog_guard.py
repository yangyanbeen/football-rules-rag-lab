"""Render a separate derived preview without asserting local catalog IDs as official laws."""
from __future__ import annotations
import argparse,copy,html
from urllib.parse import urlsplit
from answer_eval_core import *

POLICY='config/citation_catalog_notes.json'


def load_policy():
    value=read(ROOT/POLICY)
    if set(value)!={'version','policy','entries'} or value['version']!='citation-catalog-notes-1.0':
        raise ValueError('Invalid catalog display policy')
    ids=[]
    for r in value['entries']:
        if set(r)!={'chunk_id','record_sha256','content_zh_sha256','catalog_number','official_law_number','note','reference_urls'}:
            raise ValueError('Unknown catalog policy fields')
        if r['chunk_id'] in ids or not re.fullmatch(r'L\d{2}[A-Z]?-\d{2}',r['chunk_id']):raise ValueError('Invalid/duplicate catalog ID')
        ids.append(r['chunk_id'])
        if not sha(r['record_sha256']) or not sha(r['content_zh_sha256']) or type(r['catalog_number']) is not int or not 1<=r['catalog_number']<=17 or r['official_law_number'] is not None:
            raise ValueError('Invalid identity or invented official law number')
        if not isinstance(r['note'],str) or not r['note'].strip() or not r['reference_urls']:raise ValueError('Missing catalog notice')
        if any(urlsplit(u).scheme!='https' or urlsplit(u).netloc!='www.theifab.com' for u in r['reference_urls']):raise ValueError('Not an official reference URL')
    return {r['chunk_id']:r for r in value['entries']}


def safe_render(selected,corpus):
    if not isinstance(selected,list) or any(not isinstance(cid,str) for cid in selected) or len(set(selected))!=len(selected) or len(selected)>3:
        raise ValueError('Invalid selected source list')
    original,citations=render(selected,corpus)
    if not selected:return original,[]
    notes=load_policy();parts=['根据现有资料，相关完整段落如下：'];result=[]
    for cid,c in zip(selected,citations):
        r=corpus[cid];body=r['content_zh'];note=notes.get(cid)
        # Original bodies and source identities remain untouched, even in this preview.
        if note and (note['record_sha256']!=r['record_sha256'] or note['content_zh_sha256']!=r['content_zh_sha256'] or note['catalog_number']!=r['law_number']):
            raise ValueError('Catalog note belongs to another corpus version')
        ref=copy.deepcopy(c);ref.pop('law_number')
        ref.update(source_catalog_metadata={'law_number':c['law_number']},catalog_number=c['law_number'],official_law_number=None,
            law_reference_kind='local_catalog_only',catalog_notice=note['note'] if note else '本地语料编目编号；官方条号未独立核验。')
        start,end=c['source_lines']
        parts.extend([body,f"来源：{cid} · 本地编目第{c['law_number']}组 · L{start}–L{end} · {c['source_url']}",
            '编号说明：'+ref['catalog_notice'],f"署名与许可：{c['source_attribution']} · {c['license']} · {c['license_url']}"])
        if c['needs_rule_review']:parts.append('校核提示：'+'；'.join(c['review_notes']))
        result.append(ref)
    parts.append(BOUNDARY)
    return '\n\n'.join(parts),result


def make_preview(qid):
    from answer_review_v2 import review_context,evidence,source_corpus
    context=review_context()
    if qid not in context['predictions']:raise ValueError('Unknown frozen test question')
    actual=evidence(qid,context);pred=context['predictions'][qid]
    answer,cites=safe_render(pred['selected_ids'],source_corpus())
    return {'version':'catalog-display-preview-1.0','question_id':qid,'question':context['labels'][qid]['question'],
        'source_answer_sha256':pred['answer_sha256'],'source_trace':pred['trace'],'policy':record(ROOT/POLICY),
        'answer':answer,'answer_sha256':digest(answer.encode()),'citations':cites,'new_model_requests':0,
        'scope':'Derived display preview only; original formal answer, scores and human judgments unchanged. No relevance filtering or new quality claim.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--question-id',required=True);p.add_argument('--report',required=True);p.add_argument('--html');a=p.parse_args()
    path=(ROOT/a.report).resolve()
    if not path.is_relative_to(ROOT/'.runtime'):raise ValueError('Full answer previews must remain private under .runtime')
    target=(ROOT/a.html).resolve() if a.html else None
    if target is not None and (not target.is_relative_to(ROOT/'.runtime') or target.exists()):raise ValueError('HTML preview must be a new private path')
    if path.exists():raise ValueError('JSON preview already exists')
    value=make_preview(a.question_id);write_new(path,value)
    if a.html:
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('x',encoding='utf-8') as f:f.write('<!doctype html><meta charset="utf-8"><title>引用编目显示修复预览</title><h1>派生显示预览：'+html.escape(value['question'])+'</h1><p>原实验和人工审核保持原样；本页仅修正编号显示。</p><pre style="white-space:pre-wrap">'+html.escape(value['answer'])+'</pre>')
    print(json.dumps({'question_id':a.question_id,'private_preview':record(path),'new_model_requests':0},ensure_ascii=False))
