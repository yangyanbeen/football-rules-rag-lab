"""Replay public integration metadata without private texts, models or site packages."""
from urllib.parse import urlsplit
from task13_core import *


def require(value,message):
    if not value:raise ValueError(message)


def file_ref(r,parent=None):
    require(set(r)=={'path','size_bytes','sha256'},'File reference fields differ')
    p=Path(r['path']);require(not p.is_absolute() and '..' not in p.parts and '\\' not in r['path'],'Unsafe file reference')
    require(type(r['size_bytes']) is int and r['size_bytes']>0 and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Invalid file identity')
    if parent:require(p.is_relative_to(Path(parent)),'Wrong file reference root')


def validate_projection(v,case,indexes):
    cfg=app_config();ac=answer_config();known={r['chunk_id']:r for r in read(ROOT/'data/manifests/dense_chunk_ids.json')}
    require(v['question']==case['question'] and v['profile']==cfg['version'],'Question/profile differs')
    require(v['status']==case['expected_status'] and v['error'] is None and v['new_formal_test_runs']==0,'Case failed or relabelled')
    require(v['configuration']==source_identity() and v['indexes']==indexes,'Configuration/index identity differs')
    require(bool(re.fullmatch('[a-f0-9]{32}',v['trace_id'])) and bool(re.fullmatch('[a-f0-9]{64}',v['answer_sha256'])),'Invalid trace/answer digest')
    file_ref(v['private_trace'],'.runtime/task13/workers')
    for field,limit in (('retrieved_ids',10),('offered_ids',5),('selected_ids',3)):
        ids=v[field];require(isinstance(ids,list) and all(isinstance(c,str) and c in known for c in ids) and len(set(ids))==len(ids)<=limit,'Invalid '+field)
    require(set(v['selected_ids'])<=set(v['offered_ids'])<=set(v['retrieved_ids']),'Selected source not offered/retrieved')
    require((v['status']=='answered')==bool(v['selected_ids']),'Answer without sources')
    require(case['required_source'] is None or case['required_source'] in v['selected_ids'],'Missing required demonstration source')
    require([c['chunk_id'] for c in v['citations']]==v['selected_ids'],'Citation list differs')
    for c in v['citations']:
        k=known[c['chunk_id']]
        require(c['record_sha256']==k['record_sha256'] and c['content_zh_sha256']==c['quote_sha256']==k['content_zh_sha256'],'Citation body/record hash differs')
        require(c['law_reference_kind']=='local_catalog_only' and c['official_law_number'] is None and c['catalog_number']==c['source_catalog_metadata']['law_number'],'Unverified official law asserted')
        require(c['official_translation'] is False and c['expert_reviewed'] is False and c['source_revision_verified'] is False,'Unsupported authority/revision asserted')
        require(c['license']=='CC BY-SA 4.0' and c['license_url']=='https://creativecommons.org/licenses/by-sa/4.0/' and c['source_attribution']=='Wikipedia contributors','Missing source/license')
        require(urlsplit(c['source_url']).scheme=='https' and urlsplit(c['source_url']).hostname=='en.wikipedia.org','Wrong source origin')
        require(isinstance(c['source_lines'],list) and len(c['source_lines'])==2 and all(type(n) is int and n>0 for n in c['source_lines']) and c['source_lines'][0]<=c['source_lines'][1],'Invalid source lines')
        require(type(c['quote_characters']) is int and c['quote_characters']>0 and bool(c['catalog_notice']),'Missing quote metadata')
    require(type(v['prompt_utf8_bytes']) is int and 0<=v['prompt_utf8_bytes']<=ac['input_utf8_byte_budget'],'Prompt budget exceeded')
    require(isinstance(v['attempts'],list) and len(v['attempts'])<=2,'Attempt budget exceeded')
    if case['id']=='version':
        require(v['refusal_reason']=='version_unverified' and not any(v[k] for k in ('attempts','retrieved_ids','offered_ids','selected_ids','prompt_utf8_bytes')),'Version refusal performed inference')
    else:require(bool(v['attempts']) and bool(v['retrieved_ids']),'Missing actual query/generation')
    for i,a in enumerate(v['attempts']):
        require(a['attempt']==i+1 and a['error'] is None and a['done_reason']=='stop','Incomplete model attempt')
        require(type(a['eval_count']) is int and 0<a['eval_count']<=1024 and type(a['prompt_eval_count']) is int and 0<a['prompt_eval_count']<=6656,'Invalid model counters')
    require((v['refusal_reason'] is None)==(v['status']=='answered'),'Refusal reason differs')
    t=v['timing'];require(set(t)=={'retrieval_seconds','generation_seconds','total_seconds'} and all(type(x) in (int,float) and math.isfinite(x) and x>=0 for x in t.values()),'Invalid stage clock')
    require(t['total_seconds']+.01>=t['retrieval_seconds']+t['generation_seconds'],'Incomplete total clock')
    return True


def replay_demo(receipt,ui=False):
    definitions=read(ROOT/'config/task13_demo.json')['cases'];rebuild=read(ROOT/'reports/task13/index-rebuild.json')
    indexes={k:rebuild[k] for k in ('dense_index','bm25_index')}
    require(receipt['status']=='PASS' and receipt['passed']==receipt['total']==len(receipt['rows'])==5,'Incomplete five-case evidence')
    require(receipt['new_formal_test_runs']==0 and [r['id'] for r in receipt['rows']]==[c['id'] for c in definitions],'Wrong demonstration coverage/order')
    for case,row in zip(definitions,receipt['rows']):
        require(row['passed'] is True,'Failed demonstration row');validate_projection(row['result'],case,indexes)
        require(type(row['worker_wall_seconds']) in (int,float) and math.isfinite(row['worker_wall_seconds']) and row['worker_wall_seconds']>=row['result']['timing']['total_seconds'],'Invalid worker clock')
        if ui:
            require(row['browser_answer_matches_actual_trace'] is True and row['source_and_license_links_visible'] is True,'UI display/source mismatch')
            file_ref(row['browser_snapshot'],'.runtime/task13');require(bool(re.fullmatch('[a-f0-9]{64}',row['ui_event_sha256'])),'Invalid UI event digest')
    require(len({r['result']['trace_id'] for r in receipt['rows']})==5,'Reused trace ID')
    if ui:require(receipt['url']=='http://127.0.0.1:7866/' and receipt['actual_browser_submissions']==5 and receipt['raw_browser_snapshots_public'] is False,'Wrong UI evidence scope')
    else:
        require(receipt['configuration']==source_identity() and receipt['demo_definitions']==record(ROOT/'config/task13_demo.json') and receipt['formal_eval_labels_used_for_generation'] is False,'Wrong backend scope/configuration')
        require(receipt['answer_model_attempts']==sum(len(r['result']['attempts']) for r in receipt['rows']),'Attempt total differs')
    return True
