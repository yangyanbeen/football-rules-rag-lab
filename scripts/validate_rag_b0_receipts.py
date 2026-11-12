"""Standard-library receipt checks; public metadata is not proof of private reading or semantic quality."""
from __future__ import annotations
import argparse
import html
import json
import re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
from eval_dataset import ROOT,digest,load_jsonl,write_json


def validate_receipts(smoke_path,ui_path,private=False,captures_path=None,journal_path=None,failures_path=None):
    checks={}
    def check(name,value):checks[name]=bool(value)
    try:
        smoke=json.loads(Path(smoke_path).read_text('utf-8'));ui=json.loads(Path(ui_path).read_text('utf-8'))
        cfg_path=ROOT/'config/rag_b0.json';cfg=json.loads(cfg_path.read_text('utf-8'));cfg_sha=digest(cfg_path.read_bytes())
        prompt_sha=digest((ROOT/cfg['prompt_file']).read_bytes())
        ids={r['chunk_id']:r for r in json.loads((ROOT/'data/manifests/dense_chunk_ids.json').read_text('utf-8'))}
        srows,urows=smoke['rows'],ui['rows']
        sha=lambda v:isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) is not None
        check('private_full_text_not_declared_public',smoke['raw_public'] is False and ui['raw_public'] is False)
        check('no_formal_accuracy_claim',smoke['kind']=='ad_hoc_chain_smoke_not_accuracy' and smoke['formal_eval_questions_read'] is False)
        check('successful_smoke_unique_three_plus_one',smoke['status']=='PASS' and len(srows)>=4
            and len({r['trace_id'] for r in srows})==len(srows) and len({r['question'] for r in srows})==len(srows)
            and sum(r['status']=='answered' for r in srows)>=3 and sum(r['status']=='refused' for r in srows)>=1
            and all(r['status']==r['expected_status'] and not r.get('error') for r in srows))
        check('successful_ui_unique_three_plus_one',ui['kind']=='real_browser_submission' and len(urows)>=4
            and len({r['trace_id'] for r in urows})==len(urows) and len({r['question'] for r in urows})==len(urows)
            and ui['questions']==len(urows) and ui['answered']==sum(r['status']=='answered' for r in urows)>=3
            and ui['refused']==sum(r['status']=='refused' for r in urows)>=1 and all(not r.get('error') for r in urows))
        check('ui_and_smoke_question_status_pairs_match',{r['question']:r['status'] for r in srows}=={r['question']:r['status'] for r in urows})
        check('separate_backend_and_browser_trace_ids',not ({r['trace_id'] for r in srows}&{r['trace_id'] for r in urows}))
        check('all_receipts_bind_current_configuration',all(r['config_sha256']==cfg_sha for r in srows+urows))
        check('smoke_prompt_and_model_are_pinned',all(r['prompt_sha256']==prompt_sha and r['prompt_version']==cfg['prompt_version']
            and r['generation']['model_digest']==cfg['llm']['digest'] and r['generation']['model']==cfg['llm']['name']
            and r['generation']['done'] is True and r['generation']['done_reason']=='stop' for r in srows))
        check('actual_integer_token_counts_and_context_budget',all(type(r['generation'].get('prompt_eval_count')) is int
            and type(r['generation'].get('eval_count')) is int and r['generation']['prompt_eval_count']>=1
            and 1<=r['generation']['eval_count']<=cfg['llm']['num_predict']
            and r['generation']['prompt_eval_count']+cfg['llm']['num_predict']+cfg['chat_template_token_reserve']<=cfg['llm']['num_ctx'] for r in srows))
        check('smoke_retrieved_and_offered_ids_are_separate',all(len(r['retrieved_ids'])==cfg['top_k']
            and len(set(r['retrieved_ids']))==cfg['top_k'] and set(r['context_ids'])<=set(r['retrieved_ids'])
            and len(r['context_ids'])<=cfg['max_context_chunks'] and set(r['retrieved_ids'])<=set(ids) for r in srows))
        def citation_ok(c):
            url=urlsplit(c['source_url'])
            return c['chunk_id'] in ids and url.scheme=='https' and url.hostname=='en.wikipedia.org' and url.path.startswith('/wiki/')
        check('cited_ids_and_urls_are_known_format',all(citation_ok(c) for r in srows+urows for c in r['citations']))
        check('smoke_citations_bound_to_offered_body_hash',all(c['chunk_id'] in r['context_ids']
            and c['content_zh_sha256']==ids[c['chunk_id']]['content_zh_sha256'] for r in srows for c in r['citations']))
        check('answers_have_citations_and_refusals_have_none',all(bool(r['citations'])==(r['status']=='answered') for r in srows+urows))
        check('ui_loopback_and_evidence_counts',all(r['page_url']=='http://127.0.0.1:'+str(cfg['ui']['port'])+'/'
            and r['evidence_count']==len(r['citations']) for r in urows))
        check('private_hashes_and_answer_hashes_well_formed',sha(smoke['raw_sha256']) and sha(ui['raw_captures_sha256'])
            and sha(ui['private_ui_journal_snapshot_sha256']) and all(sha(r['answer_sha256']) for r in srows+urows))
        if failures_path:
            failure=json.loads(Path(failures_path).read_text('utf-8'))
            check('failure_archive_metadata_not_public_text',failure['raw_public'] is False and bool(failure['cases'])
                and all(sha(r['sha256']) and (ROOT/r['private_path']).resolve().is_relative_to(ROOT/'.runtime') for r in failure['cases']))
            if private:check('private_failure_archive_hashes',all(digest((ROOT/r['private_path']).read_bytes())==r['sha256'] for r in failure['cases']))
        if private:
            raw_path=(ROOT/smoke['raw_path']).resolve()
            if not (raw_path==ROOT/'reports/rag_b0_smoke.jsonl' or raw_path.is_relative_to(ROOT/'.runtime')):
                raise ValueError('Full smoke must stay in an ignored local path')
            raw=load_jsonl(raw_path)
            check('private_smoke_snapshot_sha',digest(raw_path.read_bytes())==smoke['raw_sha256'])
            check('private_smoke_rows_and_answers_match_receipt',len(raw)==len(srows) and all(
                r['trace_id']==s['trace_id'] and r['question']==s['question'] and r['status']==s['status']
                and digest(r['answer'].encode())==s['answer_sha256'] for r,s in zip(raw,srows)))
            capture_file=Path(captures_path or ROOT/ui.get('raw_captures_path','.runtime/rag-b0/ui-captures.jsonl')).resolve()
            snapshot_file=Path(journal_path or ROOT/ui.get('private_ui_journal_snapshot_path','.runtime/rag-b0/ui-events-delivery-snapshot.jsonl')).resolve()
            if not all(p.is_relative_to(ROOT/'.runtime') for p in (capture_file,snapshot_file)):
                raise ValueError('Full UI records must stay under ignored runtime')
            captures=load_jsonl(capture_file);journal={r['trace_id']:r for r in load_jsonl(snapshot_file)}
            check('private_ui_captures_and_snapshot_hashes',digest(capture_file.read_bytes())==ui['raw_captures_sha256']
                and digest(snapshot_file.read_bytes())==ui['private_ui_journal_snapshot_sha256'])
            matched=len(captures)==len(urows);flat=lambda v:re.sub(r'\s+','',html.unescape(v))
            for capture,receipt in zip(captures,urows):
                event=journal[capture['trace_id']]
                matched &= capture['trace_id']==receipt['trace_id'] and event['question']==receipt['question'] and event['status']==receipt['status']
                matched &= capture['trace_id'] in capture['body_text'] and digest(event['answer'].encode())==receipt['answer_sha256']
                matched &= digest(capture['last_answer_text'].encode())==receipt['rendered_last_answer_sha256']
                matched &= capture['evidence_count']==len(event['citations'])==receipt['evidence_count']
                matched &= all(flat(s['text']) in flat(capture['last_answer_text']) for s in (event.get('generation') or {}).get('validated_statements',[]))
                matched &= all(any(link['href']==c['source_url'] and c['chunk_id'] in link['text'] for link in capture['links']) for c in event['citations'])
            check('private_actual_browser_answer_panel_trace_match',matched)
            corpus={r['chunk_id']:r for r in load_jsonl(ROOT/'data/processed/rag_chunks_zh.jsonl')}
            sources=True
            for event in raw+[journal[r['trace_id']] for r in urows]:
                for match in event.get('context',[]):
                    original=corpus[match['chunk_id']]
                    sources &= match['content_zh']==original['content_zh'] and match['metadata']=={k:v for k,v in original.items() if k!='content_zh'}
                for citation in event['citations']:
                    original=corpus[citation['chunk_id']]
                    sources &= all(citation[k]==original[k] for k in ('source_url','law_number','source_lines','content_zh_sha256'))
            check('private_original_bodies_and_citation_metadata_match',sources)
    except (OSError,ValueError,KeyError,TypeError,AttributeError,IndexError) as exc:
        return {'status':'FAIL','checks':checks,'errors':[type(exc).__name__+': '+str(exc)],'private_records_checked':private}
    return {'status':'PASS_PRIVATE_RECEIPTS' if private and all(checks.values()) else ('PASS_PUBLIC_RECEIPTS' if all(checks.values()) else 'FAIL'),
        'passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':[k for k,v in checks.items() if not v],
        'private_records_checked':private,'semantic_answer_accuracy_proven':False,
        'scope':'Receipt/provenance consistency; public metadata alone does not prove private UI execution or answer correctness'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke-manifest',type=Path,default=ROOT/'reports/evidence/rag_b0_smoke_manifest.json')
    parser.add_argument('--ui-manifest',type=Path,default=ROOT/'reports/evidence/rag_b0_ui_manifest.json')
    parser.add_argument('--private',action='store_true');parser.add_argument('--ui-captures',type=Path)
    parser.add_argument('--ui-journal',type=Path);parser.add_argument('--failures-manifest',type=Path)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    result=validate_receipts(args.smoke_manifest,args.ui_manifest,args.private,args.ui_captures,args.ui_journal,args.failures_manifest)
    result['captured_at']=datetime.now(timezone.utc).isoformat()
    if args.report:
        report=args.report.resolve()
        if report.exists() or not report.is_relative_to(ROOT/'reports'):raise ValueError('Use a new report under reports/')
        write_json(report,result)
    print(json.dumps({k:result[k] for k in ('status','passed','total','errors') if k in result},ensure_ascii=False))
    raise SystemExit(1 if result['status']=='FAIL' else 0)


if __name__=='__main__':main()
