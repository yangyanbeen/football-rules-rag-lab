"""Model-free Task13 boundary regressions; actual demo traces are read only."""
import argparse,copy,uuid
from task13_core import *


def verify(private=False):
    checks={};errors=[]
    def check(name,fn):
        try:
            checks[name]=fn() is True
            if not checks[name]:errors.append({'check':name,'error':'False predicate'})
        except Exception as exc:checks[name]=False;errors.append({'check':name,'error':type(exc).__name__+': '+str(exc)})
    def rejected(fn):
        try:fn()
        except (ValueError,KeyError,TypeError,IndexError,OSError):return True
        return False
    check('fixed_top40_and_loopback_only_profile',lambda:app_config()['retrieval_method']=='top40' and app_config()['ui']['host']=='127.0.0.1' and app_config()['ui']['share'] is False)
    for i,q in enumerate((None,123,True,'','  ','问'*401)):
        check('reject_invalid_query_'+str(i),lambda q=q:rejected(lambda:normalize_question(q)))
    check('query_not_silently_truncated',lambda:normalize_question('  足球规则？  ')=='足球规则？')
    for name,change in {
        'public_host':lambda c:c['ui'].update(host='0.0.0.0'),
        'sharing':lambda c:c['ui'].update(share=True),
        'wrong_port':lambda c:c['ui'].update(port=7863),
        'old_environment':lambda c:c.update(environment='.venv/Scripts/python.exe'),
        'old_dense_index':lambda c:c.update(dense_index='data/indexes/dense'),
        'dense_path_escape':lambda c:c.update(dense_index='../outside'),
        'wrong_model_policy':lambda c:c.update(answer_policy='config/rag_b0.json'),
        'wrong_corpus':lambda c:c.update(corpus='data/processed/other.jsonl'),
        'unknown_config':lambda c:c.update(unexpected=True),
        'wrong_method':lambda c:c.update(retrieval_method='top80'),
        'bool_timeout':lambda c:c.update(worker_timeout_seconds=True)}.items():
        def run(change=change):
            c=copy.deepcopy(app_config());change(c);path=ROOT/'.tmp'/('task13-config-'+uuid.uuid4().hex+'.json');write_new(path,c)
            return rejected(lambda:app_config(path.relative_to(ROOT).as_posix()))
        check('reject_config_'+name,run)
    receipt=read(ROOT/'reports/task13/backend-demo-first.json')
    check('five_actual_backend_cases_passed',lambda:receipt['status']=='PASS' and receipt['passed']==receipt['total']==5 and {r['id'] for r in receipt['rows']}=={'normal','condition','outside','citation','version'} and all(r['passed'] is True for r in receipt['rows']))
    check('demonstration_not_formal_test_or_accuracy',lambda:receipt['new_formal_test_runs']==0 and receipt['formal_eval_labels_used_for_generation'] is False and 'not formal answer accuracy' in receipt['scope'])
    if private:
        definitions={r['id']:r for r in read(ROOT/'config/task13_demo.json')['cases']}
        from run_task13_demo import case_passes
        for r in receipt['rows']:
            def run(r=r):
                p=ROOT/r['result']['private_trace']['path'];actual=read(p)
                return record(p)==r['result']['private_trace'] and public_result(actual,p)==r['result'] and case_passes(definitions[r['id']],actual)
            check(r['id']+'_actual_response_and_public_projection',run)
        source=next(r for r in receipt['rows'] if r['id']=='normal');actual=read(ROOT/source['result']['private_trace']['path'])
        mutations={
            'wrong_question':lambda v:v.update(question='other'),
            'wrong_profile':lambda v:v.update(profile='other'),
            'wrong_configuration':lambda v:v['configuration'].pop('config/task13_app.json'),
            'wrong_index':lambda v:v['indexes']['dense_index'].update(sha256='0'*64),
            'unknown_selection':lambda v:v.update(selected_ids=['L99-99']),
            'duplicate_selection':lambda v:v['selected_ids'].append(v['selected_ids'][0]),
            'changed_answer':lambda v:v.update(answer=v['answer']+'invented'),
            'changed_url':lambda v:v['citations'][0].update(source_url='https://example.invalid'),
            'changed_quote_hash':lambda v:v['citations'][0].update(quote_sha256='0'*64),
            'invented_official_law':lambda v:v['citations'][0].update(official_law_number=1),
            'lost_license':lambda v:v['citations'][0].update(license=''),
            'changed_context':lambda v:v['context'][0].update(content_zh='altered'),
            'changed_prompt':lambda v:v['messages'][0].update(content='altered'),
            'changed_model_counters':lambda v:v['attempts'][0].update(eval_count=0),
            'missing_generation':lambda v:v.update(attempts=[]),
            'unknown_worker_error':lambda v:v.update(error='failed'),
            'negative_clock':lambda v:v['timing'].update(total_seconds=-1),
            'missing_clock':lambda v:v['timing'].pop('generation_seconds')}
        for name,mutate in mutations.items():
            def run(mutate=mutate):
                v=copy.deepcopy(actual);mutate(v)
                return rejected(lambda:validate_result(v,actual['question']))
            check('reject_worker_'+name,run)
        def html_escaped():
            v=copy.deepcopy(actual);v['context'][0]['content_zh']='<script>alert(1)</script>'
            panel=render_panel(v)
            return '<script>' not in panel and '&lt;script&gt;' in panel
        check('source_panel_html_is_escaped',html_escaped)
    return {'version':'task13-contract-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL',
        'passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'private':private,
        'new_model_requests':0,'source_sha256':{n:record(ROOT/n)['sha256'] for n in ('scripts/task13_core.py','scripts/task13_engine.py','scripts/verify_task13_contract.py')},
        'scope':'Synthetic in-memory corruptions and existing integration traces; no new formal tests or human reviews.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--private',action='store_true');p.add_argument('--report',required=True);a=p.parse_args()
    v=verify(a.private);write_new(ROOT/a.report,v);print(json.dumps({k:v[k] for k in ('status','passed','total','errors')},ensure_ascii=False));raise SystemExit(v['status']!='PASS')
