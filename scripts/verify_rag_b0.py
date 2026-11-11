"""Task 6 contract, real smoke/UI and preservation gate; no formal eval scoring."""
from __future__ import annotations
import argparse
import copy
import html
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from eval_dataset import ROOT, digest, load_jsonl, write_json
from dense_index import DEFAULT_INDEX, inventory
from rag_b0 import (CONFIG, RagB0Engine, PinnedChat, load_config, normalize_query,
                    pack_context, passages_for, validate_payload, citations_for, render_panel)
from rag_b0_worker_client import call_worker

BASE='0f6abdcc2b5ef8f35b9add68e0a1c15ee56f7fff'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    report=args.report.resolve()
    if not report.is_relative_to(ROOT/'reports') or report.exists():
        raise ValueError('Use a new report path under reports/')
    checks={}
    def record(name,value):checks[name]=bool(value)
    def rejects(callback):
        try:callback()
        except ValueError:return True
        return False
    cfg=load_config();prompt=(ROOT/cfg['prompt_file']).read_text('utf-8')
    raw=ROOT/'reports/rag_b0_smoke.jsonl';rows=load_jsonl(raw)
    smoke=json.loads((ROOT/'reports/evidence/rag_b0_smoke_manifest.json').read_text('utf-8'))
    record('normalization_nfkc_and_whitespace',normalize_query('  ＡＢＣ\n 足球  ',cfg)=='ABC 足球')
    record('empty_query_rejected',rejects(lambda:normalize_query(' \n ',cfg)))
    record('nontext_query_rejected',rejects(lambda:normalize_query(None,cfg)))
    record('oversize_query_rejected',rejects(lambda:normalize_query('中'*401,cfg)))
    record('smoke_original_required_path_and_sha',smoke['raw_path']=='reports/rag_b0_smoke.jsonl' and smoke['raw_sha256']==digest(raw.read_bytes()))
    record('smoke_three_answers_one_refusal',len(rows)>=4 and sum(r['status']=='answered' for r in rows)>=3 and any(r['smoke_id']=='outside' and r['status']=='refused' for r in rows))
    record('smoke_real_generation_no_errors',all(r['generation_attempted'] and r['generation']['done_reason']=='stop' and not r.get('error') for r in rows))
    record('smoke_no_formal_eval_claim',smoke['formal_eval_questions_read'] is False and smoke['kind']=='ad_hoc_chain_smoke_not_accuracy')
    corpus={r['chunk_id']:r for r in load_jsonl(ROOT/'data/processed/rag_chunks_zh.jsonl')}
    index_sha=digest((DEFAULT_INDEX/'index_manifest.json').read_bytes())
    record('smoke_current_config_prompt_and_index',all(r['config_sha256']==digest(CONFIG.read_bytes()) and r['prompt_sha256']==digest(prompt.encode()) and r['index_manifest_sha256']==index_sha for r in rows))
    record('smoke_dense_top5_distinct_from_context',all(len(r['retrieval']['results'])==cfg['top_k'] and r['context'] and len(r['context'])<=cfg['top_k'] for r in rows))
    aligned=True;budget=True;valid=True
    for r in rows:
        for m in r['retrieval']['results']:
            original=corpus[m['chunk_id']]
            aligned &= m['content_zh']==original['content_zh'] and m['metadata']=={k:v for k,v in original.items() if k!='content_zh'}
        selected,messages,schema,size=pack_context(r['normalized_query'],r['retrieval']['results'],cfg,prompt)
        budget &= selected==r['context'] and messages==r['messages'] and size==r['prompt_utf8_bytes'] and size<=cfg['input_utf8_byte_budget']
        statements=validate_payload(r['generation']['parsed_payload'],selected,cfg)
        valid &= citations_for(statements,selected)==r['citations']
    record('retrieved_original_bodies_and_all_metadata_exact',aligned)
    record('whole_blocks_and_exact_prompt_budget_reproducible',budget)
    record('generated_statements_resolve_to_true_original_sources',valid)
    record('actual_token_context_with_output_and_reserve',all(r['generation']['prompt_eval_count']+cfg['llm']['num_predict']+cfg['chat_template_token_reserve']<=cfg['llm']['num_ctx'] for r in rows))
    record('outside_refuses_without_assertions_or_citations',all(not r['citations'] and not r['generation']['parsed_payload']['statements'] for r in rows if r['status']=='refused'))
    record('trace_separates_evidence_generation_and_answer',all(r['context'] and r['generation']['raw_content'] and r['answer'] and r['trace_id'] for r in rows))
    offered=rows[0]['context'];pid=passages_for(offered[0],cfg)[0]['passage_id']
    payload={'answerable':True,'statements':[{'text':'这是一条依据资料的回答。','passage_id':pid}],'refusal_reason':None}
    checked=validate_payload(payload,offered,cfg)
    record('program_restores_verbatim_original_paragraph',checked[0]['support_quote'] in offered[0]['content_zh'])
    cases={
        'unknown_passage':{**payload,'statements':[{'text':'这是一条错误引用。','passage_id':'L99-99:p1'}]},
        'unoffered_passage':{**payload,'statements':[{'text':'这是一条未提供的引用。','passage_id':'L17-04:p1'}]},
        'fabricated_quote_field':{**payload,'statements':[{'text':'这是一条错误引用。','passage_id':pid,'support_quote':'编造'}]},
        'invented_url':{**payload,'statements':[{'text':'查看 https://invalid.example/','passage_id':pid}]},
        'model_html':{**payload,'statements':[{'text':'<script>bad()</script>','passage_id':pid}]},
        'invented_citation_markup':{**payload,'statements':[{'text':'这条回答是错误的 [虚构来源]','passage_id':pid}]},
        'empty_answer':{**payload,'statements':[]},
        'integer_boolean':{**payload,'answerable':1},
        'contradictory_refusal':{**payload,'answerable':False},
        'refusal_missing_reason':{'answerable':False,'statements':[],'refusal_reason':None},
        'refusal_html':{'answerable':False,'statements':[],'refusal_reason':'<b>错误</b>'},
        'answer_with_refusal_reason':{**payload,'refusal_reason':'矛盾'},
        'excess_statements':{**payload,'statements':payload['statements']*5},
        'overlong_statement':{**payload,'statements':[{'text':'中'*161,'passage_id':pid}]},
        'unsupported_numeric_fact':{**payload,'statements':[{'text':'该数值为98765米。','passage_id':pid}]},
    }
    for name,value in cases.items():record('reject_'+name,rejects(lambda v=value:validate_payload(v,offered,cfg)))
    chat=PinnedChat(cfg)
    def response_request(path,payload=None):
        if path=='/api/version':return {'version':cfg['llm']['ollama_version']}
        if path=='/api/tags':return {'models':[{'name':cfg['llm']['name'],'digest':cfg['llm']['digest']}]}
        return response_request.response
    for name,response in (
        ('truncated',{'done':True,'done_reason':'length'}),
        ('unfinished',{'done':False,'done_reason':'stop'}),
        ('context_overflow',{'done':True,'done_reason':'stop','prompt_eval_count':cfg['llm']['num_ctx']})):
        response_request.response=response
        with patch.object(chat,'request',side_effect=response_request):record('reject_model_'+name,rejects(lambda:chat.generate([],{})))
    with patch.object(chat,'request',return_value={'version':'wrong'}):record('reject_ollama_version_change',rejects(chat.verify_model))
    with patch.object(chat,'request',side_effect=[{'version':cfg['llm']['ollama_version']},{'models':[]}]) :
        record('reject_missing_pinned_model',rejects(chat.verify_model))
    record('reject_remote_chat_provider',rejects(lambda:PinnedChat(cfg,'https://example.com')))
    # Failure exercise uses the real index but deliberately no model request.
    engine=RagB0Engine()
    try:
        with patch.object(engine.index,'query',side_effect=RuntimeError('deliberate unavailable embedding service')):
            failure=engine.answer('规则查询')
        record('service_failure_fails_closed_with_trace',failure['status']=='refused' and failure['error'].startswith('RuntimeError:') and not failure['citations'] and not failure['generation_attempted'])
        official=engine.answer('请给出2026赛季现行IFAB官方规则')
        record('official_unverified_version_refused_before_generation',official['status']=='refused' and official['refusal_reason']=='official_version_not_verified' and not official['generation_attempted'])
    finally:engine.close()
    with patch('rag_b0_worker_client.subprocess.run',side_effect=OSError('deliberate unavailable worker')):
        worker=call_worker('资料查询')
    record('worker_failure_fails_closed',worker['status']=='refused' and worker['refusal_reason']=='isolated_worker_failed' and not worker['citations'])
    pipe=(ROOT/'scripts/rag_b0_pipeline.py').read_text('utf-8')
    record('ui_history_not_factual_context',"result=call_worker(message)" in pipe and 'call_worker(history' not in pipe)
    ui_path=ROOT/'.runtime/rag-b0/ui-captures.jsonl'
    captures=load_jsonl(ui_path);journal={r['trace_id']:r for r in load_jsonl(ROOT/'.runtime/rag-b0/ui-events.jsonl')}
    mixed=journal['6634f9e466e149fd8ca17024ade83a8e']
    record('actual_prior_ui_numeric_citation_error_now_rejected',rejects(lambda:validate_payload(mixed['generation']['parsed_payload'],mixed['context'],cfg)))
    visible=True
    for c in captures:
        r=journal[c['trace_id']]
        flat=lambda t:re.sub(r'\s+','',html.unescape(t))
        visible &= c['page_url']=='http://127.0.0.1:7863/' and c['trace_id'] in c['body_text'] and not r.get('error')
        if r['status']=='answered':
            visible &= all(flat(s['text']) in flat(c['last_answer_text']) for s in r['generation']['validated_statements'])
            visible &= all(any(link['href']==cit['source_url'] and cit['chunk_id'] in link['text'] for link in c['links']) for cit in r['citations'])
            visible &= c['evidence_count']==len(r['citations'])
        else:visible &= '不足' in c['last_answer_text'] and not c['evidence_count']
    record('real_browser_three_answers_and_one_refusal',len(captures)==4 and sum(journal[c['trace_id']]['status']=='answered' for c in captures)==3)
    record('real_browser_answer_links_original_panels_trace_match',visible)
    record('ui_generation_uses_current_config',all(journal[c['trace_id']]['config_sha256']==digest(CONFIG.read_bytes()) for c in captures))
    lock=json.loads((ROOT/'data/manifests/task1_task2_baseline_lock.json').read_text('utf-8'))
    record('original_frozen_10_files',all(digest((ROOT/r['path']).read_bytes())==r['sha256'] for r in lock['files']))
    record('original_append_only_4_prefixes',all(digest((ROOT/r['path']).read_bytes()[:r['original_size_bytes']])==r['original_prefix_sha256'] for r in lock['append_only_files']))
    local=json.loads((ROOT/'data/manifests/local_data_files.json').read_text('utf-8'))['files']
    record('original_local_corpus_61_files',len(local)==61 and all(digest((ROOT/r['path']).read_bytes())==r['sha256'] for r in local))
    historical=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE,'data/eval','config/dense_index.json',
        'data/manifests/dense_index_manifest.json','data/manifests/dense_chunk_ids.json','scripts/dense_index.py',
        'scripts/validate_eval_dataset.py','scripts/run_kotaemon_local.py','scripts/football_quality_pipeline.py'],cwd=ROOT,text=True).splitlines()
    record('prior_eval_index_and_old_launch_code_unchanged',all((ROOT/name).read_bytes()==subprocess.check_output(['git','show',BASE+':'+name],cwd=ROOT) for name in historical))
    index_manifest=json.loads((DEFAULT_INDEX/'index_manifest.json').read_text('utf-8'))
    record('original_dense_artifacts_and_manifest',inventory(DEFAULT_INDEX)==index_manifest['artifact_files'] and index_sha=='f0c52d56e86d5b3a3d660e13a98870684b254b039ae77b2267a698e9814d0e4e')
    record('original_private_human_reviews_unchanged',digest((ROOT/'.runtime/eval_review/reviews.jsonl').read_bytes())=='1e7161c703bce47ae7a8c3d13dafa04a09009cd8ea5311cd082e4dce309fb464')
    original=ROOT.parent/'football-rules-rag-project'
    snapshot=json.loads((ROOT.parent/'2026-11-06/new-chat/.tmp/github-publication/original-project-before.json').read_text('utf-8'))
    record('original_project_static_178_files',len(snapshot)==178 and all(digest((original/name).read_bytes())==sha for name,sha in snapshot.items()))
    record('original_project_has_no_root_git',not (original/'.git').exists())
    record('full_smoke_and_ui_traces_ignored',all(subprocess.run(['git','check-ignore','--quiet',str(p.relative_to(ROOT))],cwd=ROOT).returncode==0 for p in (raw,ui_path,ROOT/'.runtime/rag-b0/ui-events.jsonl')))
    record('task6_document_and_launcher_present',all((ROOT/name).is_file() for name in ('docs/RAG_B0.md','docs/TASK_06_SCOPE.md','frontend/start_rag_b0.ps1')))
    output={'captured_at':datetime.now(timezone.utc).isoformat(),'status':'PASS' if all(checks.values()) else 'FAIL',
        'passed':sum(checks.values()),'total':len(checks),'checks':checks,'reference_commit':BASE,
        'smoke_raw_sha256':digest(raw.read_bytes()),'ui_captures_sha256':digest(ui_path.read_bytes()),
        'negative_cases':len(cases),'not_formal_accuracy':True,'source_sha256':{
            p.name:digest(p.read_bytes()) for p in sorted((ROOT/'scripts').glob('*rag_b0*.py'))}}
    write_json(report,output)
    print(json.dumps({'status':output['status'],'passed':output['passed'],'total':output['total'],
        'failed':[k for k,v in checks.items() if not v]}))
    raise SystemExit(0 if all(checks.values()) else 1)


if __name__=='__main__':main()
