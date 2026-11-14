"""Task13 repair regressions; standard library only, zero new inference."""
import argparse,copy,sys,types,importlib
from unittest.mock import patch
import task13_audit as audit
from task13_audit import *


def verify(private=False):
    checks={};errors=[]
    def check(name,fn):
        try:checks[name]=fn() is True
        except Exception as exc:checks[name]=False;errors.append({'check':name,'error':type(exc).__name__+': '+str(exc)})
        if not checks[name] and not any(e['check']==name for e in errors):errors.append({'check':name,'error':'False predicate'})
    def rejects(fn):
        try:fn()
        except (ValueError,KeyError,TypeError,IndexError,RuntimeError,OSError):return True
        return False
    package=read(ROOT/'reports/task13/delivery_manifest.json');check('complete_original_package_strictly_validates',lambda:verify_package(package,private))
    ui=read(ROOT/'reports/task13/ui-demo.json');normal=ui['rows'][0]['result']
    check('all_ten_original_public_projections_strictly_validate',lambda:all(validate_public(r['result']) for name in ('ui-demo.json','backend-demo-first.json') for r in read(ROOT/'reports/task13'/name)['rows']))
    for name,change in {
        'extra_answer_body':lambda v:v.update(answer='PRIVATE'),
        'extra_context':lambda v:v.update(context=[]),
        'wrong_same_origin_url':lambda v:v['citations'][0].update(source_url='https://en.wikipedia.org/wiki/Unrelated_page'),
        'wrong_positive_lines':lambda v:v['citations'][0].update(source_lines=[1,2]),
        'extra_quote_body':lambda v:v['citations'][0].update(quote='PRIVATE'),
        'invented_official_number':lambda v:v['citations'][0].update(official_law_number=1),
        'wrong_record_hash':lambda v:v['citations'][0].update(record_sha256='0'*64),
        'wrong_quote_hash':lambda v:v['citations'][0].update(quote_sha256='0'*64),
        'wrong_catalog':lambda v:v['citations'][0].update(catalog_number=True),
        'wrong_quote_count':lambda v:v['citations'][0].update(quote_characters=True),
        'missing_license':lambda v:v['citations'][0].update(license=''),
        'wrong_source_revision':lambda v:v['citations'][0].update(source_revision_id='wrong'),
        'boolean_formal_run':lambda v:v.update(new_formal_test_runs=False),
        'unknown_selection':lambda v:v['selected_ids'].append('L99-99'),
        'unoffered_source':lambda v:v.update(offered_ids=[]),
        'negative_clock':lambda v:v['timing'].update(total_seconds=-1),
        'nonfinite_clock':lambda v:v['timing'].update(total_seconds=float('nan')),
        'missing_actual_generation':lambda v:v.update(attempts=[]),
        'invalid_actual_counter':lambda v:v['attempts'][0].update(eval_count=True),
        'oversized_prompt':lambda v:v.update(prompt_utf8_bytes=6201),
        'unbound_trace':lambda v:v['private_trace'].update(path='../outside'),
        'unbound_configuration':lambda v:v['configuration'].pop('config/task13_app.json')}.items():
        def run(change=change):
            v=copy.deepcopy(normal);change(v);return rejects(lambda:validate_public(v))
        check('reject_public_'+name,run)
    for name,change in {
        'missing_worker':lambda v:v.update(public_members=[r for r in v['public_members'] if r['path']!='scripts/query_task13.py']),
        'missing_fixed_doc':lambda v:v.update(public_members=[r for r in v['public_members'] if r['path']!='docs/TASK_13_LICENSES.md']),
        'duplicate_member':lambda v:v['public_members'].append(v['public_members'][0]),
        'unknown_package_field':lambda v:v.update(extra=True),
        'wrong_upstream':lambda v:v.update(upstream_commit='0'*40),
        'wrong_corpus':lambda v:v['private_data']['corpus'].update(sha256='0'*64),
        'wrong_model':lambda v:v['models']['answer'].update(digest='0'*64),
        'escaped_path':lambda v:v['public_members'][0].update(path='../outside'),
        'boolean_size':lambda v:v['public_members'][0].update(size_bytes=True),
        'missing_receipt':lambda v:v['receipts'].pop(),
        'wrong_producer':lambda v:v.update(source_commit='0'*40)}.items():
        def run(change=change):
            v=copy.deepcopy(package);change(v);return rejects(lambda:verify_package(v))
        check('reject_package_'+name,run)
    import task13_audit_client as client
    def timeout():
        with patch.object(client.subprocess,'run',side_effect=subprocess.TimeoutExpired('worker',420,output=b'partial',stderr=b'failed')):
            try:client.call_worker('synthetic timeout')
            except RuntimeError:return True
        return False
    check('worker_timeout_becomes_handled_RuntimeError_with_private_receipt',timeout)
    def bad_packet():
        with patch.object(client.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout='NOT JSON',stderr='')):
            return rejects(lambda:client.call_worker('synthetic malformed packet'))
    check('malformed_packet_fails_closed',bad_packet)
    def runtime_failure():
        def fake_run(command,**kwargs):
            trace=Path(command[command.index('--trace')+1]);v={'trace_id':'0'*32,'status':'refused','error':'service unavailable'};write_new(trace,v)
            return types.SimpleNamespace(returncode=0,stdout=json.dumps({'trace_id':v['trace_id'],'status':'refused','private_trace':record(trace)}),stderr='')
        with patch.object(client.subprocess,'run',side_effect=fake_run),patch.object(client,'validate_private',return_value=True):
            return rejects(lambda:client.call_worker('synthetic operational failure'))
    check('operational_failure_never_returned_as_semantic_refusal',runtime_failure)
    class Rejected(ValueError):retryable=False;response={}
    def no_retry():
        with patch('answer_json_chat.generate',side_effect=Rejected('identity differs')) as generate:
            v,a,e=request_json(None,[{'role':'user','content':'test'}],answer_config(),lambda x:x,{})
            return v is None and len(a)==generate.call_count==1 and bool(e)
    check('nonretryable_model_identity_stops_after_one_attempt',no_retry)
    def retry_format():
        response={'prompt_eval_count':12,'eval_count':5,'done_reason':'stop','message':{'content':'ok'}}
        with patch('answer_json_chat.generate',side_effect=[ValueError('format'),response]) as generate:
            v,a,e=request_json(None,[{'role':'user','content':'test'}],answer_config(),lambda x:x,{})
            return v=='ok' and len(a)==generate.call_count==2 and e is None and len(a[-1]['messages'])==2
    check('repairable_format_retains_bounded_second_attempt',retry_format)
    def repaired_public():
        v=copy.deepcopy(normal);first=copy.deepcopy(v['attempts'][0]);first['error']='ValueError: invalid format';v['attempts'][0]['attempt']=2;v['attempts'].insert(0,first)
        return validate_public(v)
    check('successful_format_repair_public_projection_remains_usable',repaired_public)
    def after_success():
        v=copy.deepcopy(normal);v['attempts'].append(copy.deepcopy(v['attempts'][0]));v['attempts'][1]['attempt']=2
        return rejects(lambda:validate_public(v))
    check('no_request_allowed_after_first_success',after_success)
    def config_type():
        v=app_config();v['ui']['share']=0
        with patch.object(audit,'app_config',return_value=v):return rejects(audit_config)
    check('integer_zero_cannot_impersonate_boolean_config',config_type)
    from prepare_task13_environment_checked import validate_targets
    for name,report in {'outside':'../outside.json','source_file':'scripts/new-receipt.json','inside_new_environment':'.runtime/task13/new-test-env/receipt.json'}.items():
        check('installer_rejects_'+name+'_before_install',lambda report=report:rejects(lambda:validate_targets('.runtime/task13/new-test-env',report)))
    def pipeline_failure():
        class Doc:
            def __init__(self,**kwargs):self.__dict__.update(kwargs)
        fakebase=types.ModuleType('kotaemon.base');fakebase.Document=Doc
        fakektem=types.ModuleType('ktem.reasoning.base');fakektem.BaseReasoning=type('BaseReasoning',(),{})
        with patch.dict(sys.modules,{'kotaemon.base':fakebase,'ktem.reasoning.base':fakektem}):
            module=importlib.import_module('task13_audit_pipeline')
            with patch.object(module,'call_worker',side_effect=RuntimeError('timeout')):
                out=list(module.IntegratedFootballPipeline().stream('test','id',[]))
            return any(getattr(d,'channel',None)=='chat' and '未能完成' in d.content for d in out) and not any(getattr(d,'channel',None)=='chat' and REFUSAL in d.content for d in out)
    check('UI_renders_explicit_failure_without_false_semantic_refusal',pipeline_failure)
    if private:
        from citation_catalog_guard import safe_render
        corpus=local_corpus();check('all99_citation_metadata_recompute_from_actual_corpus',lambda:source_map()=={cid:safe_render([cid],corpus)[1][0] for cid in corpus})
        for row in ui['rows']:
            check('private_'+row['id']+'_old_actual_trace_still_valid',lambda row=row:validate_private(read(ROOT/row['result']['private_trace']['path']),row['result']['question']))
        check('source_panel_contains_clickable_license_and_escaped_body',lambda:'href="https://creativecommons.org/licenses/by-sa/4.0/"' in panel(read(ROOT/ui['rows'][0]['result']['private_trace']['path'])))
    return {'version':'task13-audit-regressions-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'private':private,'site_packages_disabled':bool(sys.flags.no_site),'new_model_requests':0,'new_human_judgments':0,'source_sha256':{p:record(ROOT/p)['sha256'] for p in ('scripts/task13_audit.py','scripts/task13_audit_client.py','scripts/task13_audit_pipeline.py','scripts/verify_task13_audit.py','scripts/prepare_task13_environment_checked.py')},'scope':'Saved evidence and controlled corruption/mocked failures; not new answer-quality samples. Public mode reads no private corpus/models/original traces.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--private',action='store_true');p.add_argument('--report',required=True);a=p.parse_args();v=verify(a.private);write_new(ROOT/a.report,v);print(json.dumps({k:v[k] for k in ('status','passed','total','errors')},ensure_ascii=False));raise SystemExit(v['status']!='PASS')
