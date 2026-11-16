"""Adversarial and deterministic checks for final archive/resume provenance."""
import argparse,copy,sys
from unittest.mock import patch
from task14_archive import *
from answer_eval_core import now


def verify():
    checks={};errors=[];v=read(FOLDER/'archive.json')
    def check(name,fn):
        try:
            checks[name]=fn() is True
            if not checks[name]:errors.append({'check':name,'error':'False predicate'})
        except Exception as exc:checks[name]=False;errors.append({'check':name,'error':type(exc).__name__+': '+str(exc)})
    def rejects(fn):
        try:fn()
        except (ValueError,KeyError,TypeError,IndexError,OSError):return True
        return False
    check('archive_and_all_three_rendered_outputs_recompute',lambda:verify_archive(v))
    check('all14_tasks_are_covered',lambda:{t for r in v['records'] for t in r['tasks']}==set(range(1,15)))
    check('25_history_plus2_preGit_plus1_archive_records',lambda:len(v['records'])==28 and v['historical_registry_count']==25 and len({r['id'] for r in v['records']})==28)
    check('all_required_fields_present',lambda:all(set(FIELDS)<=set(r) and all(r[k] not in (None,'',[]) for k in FIELDS if k!='tasks') for r in v['records']))
    check('78_unique_source_bound_claims',lambda:len(v['claims'])==len({c['id'] for c in v['claims']})==78 and all(c['source_record']==record(ROOT/c['source']) and c['lineage']['raw_results'] and c['lineage']['commands'] and c['lineage']['historical_commands'] for c in v['claims']))
    check('dense_latency_uses_its_own_historical_schema',lambda:claim_map(v)['dense_P50_ms']['pointer']=='/latency/stages/total_seconds/p50' and claim_map(v)['dense_P50_ms']['value']==270.1763)
    check('all_unmeasured_values_explicit_and_disallowed_in_resume',lambda:len(v['unmeasured'])==12 and all(r['status']=='待测' and r['value'] is None and r['resume_allowed'] is False for r in v['unmeasured']))
    check('preGit_code_history_not_invented',lambda:all('SHA' in r['code'].get('policy','') and '无虚构' in r['code'].get('policy','') for r in v['records'] if r['kind']=='pre_git_stage'))
    parsed=list(csv.DictReader(io.StringIO(csv_text(v))))
    check('complete_csv_roundtrip_and_identifier_order',lambda:list(parsed[0])==list(FIELDS) and [r['id'] for r in parsed]==[r['id'] for r in v['records']])
    def resume_ids():
        text=resume_text(v);ids=set(claim_map(v))
        matches=re.findall(r'\[([a-z_0-9, ]+)\]',text)
        return bool(matches) and all(k.strip() in ids for m in matches for k in m.split(','))
    check('every_resume_claim_marker_resolves',resume_ids)
    c=claim_map(v)
    check('RRF_negative_MRR_retained',lambda:c['hybrid_rrf_mrr']['value']<c['hybrid_bm25_mrr']['value'])
    check('child_Recall5_negative_retained',lambda:c['structure_child_r5']['value']<c['structure_base_r5']['value'])
    check('parent_Recall10_negative_and_context_cost_retained',lambda:c['structure_parent_child_r10']['value']<c['structure_base_r10']['value'] and c['structure_parent_child_context_tokens']['value']>c['structure_base_context_tokens']['value'])
    check('AI_and_real_human_metrics_remain_separate',lambda:c['human_citation_correctness_numerator']['value']==9 and c['human_citation_correctness_denominator']['value']==20 and c['ai_citation_correctness']['value']!=c['human_citation_correctness_value']['value'])
    changes={
        'invented_value':lambda a:a['claims'][0].update(value=500),
        'wrong_claim_hash':lambda a:a['claims'][0]['source_record'].update(sha256='0'*64),
        'wrong_pointer':lambda a:a['claims'][0].update(pointer='/wrong'),
        'unknown_claim_field':lambda a:a['claims'][0].update(private_answer='not allowed'),
        'missing_claim':lambda a:a['claims'].pop(),
        'duplicate_claim':lambda a:a['claims'].append(a['claims'][0]),
        'missing_experiment':lambda a:a['records'].pop(),
        'missing_required_hardware':lambda a:a['records'][5].pop('hardware'),
        'wrong_historical_commit':lambda a:a['records'][5]['code'].update(source_commit='0'*40),
        'missing_raw_rankings':lambda a:a['groups']['reranker'].update(source_records=[]),
        'missing_parameters':lambda a:a['groups']['reranker'].update(parameter_records=[]),
        'invented_hardware':lambda a:a['groups']['reranker']['hardware'].update(value={'logical_cpus':999}),
        'wrong_comparison_scope':lambda a:a['groups']['reranker'].update(scope='same as old Dense'),
        'unmeasured_as_measured':lambda a:a['unmeasured'][0].update(status='measured',value=.35,resume_allowed=True),
        'zero_division_human_100_percent':lambda a:a['records'][-1]['metrics'].update(human_refusal_accuracy=1.),
        'claim_as_human':lambda a:next(c for c in a['claims'] if c['id']=='ai_condition_exception_retention').update(role='human_sample'),
        'extra_top_level_body':lambda a:a.update(answer='private body'),
        'new_model_request':lambda a:a.update(new_model_requests=False),
        'new_formal_test':lambda a:a.update(new_formal_test_runs=1),
        'uncommitted_producer':lambda a:a.update(source_commit='0'*40)}
    for name,change in changes.items():
        def run(change=change):
            a=copy.deepcopy(v);change(a);return rejects(lambda:verify_archive(a))
        check('reject_'+name,run)
    for name,path in {'escape':'../outside.json','private_corpus':'data/processed/rag_chunks_zh.jsonl','model':'.models/model.json','unknown':'.tmp/anything.json'}.items():
        check('reject_resource_'+name,lambda path=path:rejects(lambda:resource(path)))
    for i,value in enumerate((True,-1,float('nan'),float('inf'))):
        check('reject_non_numeric_claim_'+str(i),lambda value=value:rejects(lambda:value_of({'source':'x','pointer':'/v','op':'value','unit':'ratio'},{'x':{'v':value}})))
    check('json_pointer_array_and_escape',lambda:pointer({'a/b':[{'~x':2}]},'/a~1b/0/~0x')==2)
    return {'version':'task14-regressions-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'new_model_requests':0,'new_formal_test_runs':0,'new_human_judgments':0,'site_packages_disabled':bool(sys.flags.no_site),'source_sha256':{p:record(ROOT/p)['sha256'] for p in ('scripts/task14_archive.py','scripts/verify_task14_archive.py',SPEC)},'scope':'Frozen public evidence, deterministic renderer and controlled in-memory corruptions; no new accuracy samples or private text read.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',required=True);a=p.parse_args();v=verify();write_new(ROOT/a.report,v);print(json.dumps({k:v[k] for k in ('status','passed','total','errors')},ensure_ascii=False));raise SystemExit(v['status']!='PASS')
