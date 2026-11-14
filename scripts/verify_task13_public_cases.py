"""Adversarial checks of public integration metadata; zero inference or human judgments."""
import argparse,copy,sys
from task13_replay import *


def verify():
    backend=read(ROOT/'reports/task13/backend-demo-first.json');ui=read(ROOT/'reports/task13/ui-demo.json');checks={};errors=[]
    def check(name,fn):
        try:checks[name]=fn() is True
        except Exception as e:checks[name]=False;errors.append({'check':name,'error':str(e)})
    check('actual_backend_replays',lambda:replay_demo(backend));check('actual_browser_replays',lambda:replay_demo(ui,True))
    changes={
        'wrong_question':lambda r:r['rows'][0]['result'].update(question='other'),
        'wrong_profile':lambda r:r['rows'][0]['result'].update(profile='other'),
        'wrong_config':lambda r:r['rows'][0]['result']['configuration'].pop('config/task13_app.json'),
        'wrong_index':lambda r:r['rows'][0]['result']['indexes']['dense_index'].update(sha256='0'*64),
        'unknown_id':lambda r:r['rows'][0]['result']['selected_ids'].append('L99-99'),
        'duplicate_id':lambda r:r['rows'][0]['result']['retrieved_ids'].append('L01-03'),
        'unoffered_selection':lambda r:r['rows'][0]['result'].update(offered_ids=[]),
        'lost_quote_hash':lambda r:r['rows'][0]['result']['citations'][0].update(quote_sha256='0'*64),
        'invented_official_law':lambda r:r['rows'][0]['result']['citations'][0].update(official_law_number=1),
        'invented_expert_review':lambda r:r['rows'][0]['result']['citations'][0].update(expert_reviewed=True),
        'missing_license':lambda r:r['rows'][0]['result']['citations'][0].update(license=''),
        'source_origin':lambda r:r['rows'][0]['result']['citations'][0].update(source_url='https://example.invalid'),
        'backwards_lines':lambda r:r['rows'][0]['result']['citations'][0].update(source_lines=[2,1]),
        'budget':lambda r:r['rows'][0]['result'].update(prompt_utf8_bytes=6201),
        'missing_generation':lambda r:r['rows'][0]['result'].update(attempts=[]),
        'zero_model_count':lambda r:r['rows'][0]['result']['attempts'][0].update(eval_count=0),
        'negative_clock':lambda r:r['rows'][0]['result']['timing'].update(total_seconds=-1),
        'nonfinite_clock':lambda r:r['rows'][0]['result']['timing'].update(total_seconds=float('nan')),
        'private_path_escape':lambda r:r['rows'][0]['result']['private_trace'].update(path='../secret'),
        'wrong_counts':lambda r:r.update(total=4),
        'missing_case':lambda r:r['rows'].pop(),
        'failed_row':lambda r:r['rows'][0].update(passed=False),
        'false_ui_link':lambda r:r['rows'][0].update(source_and_license_links_visible=False),
        'false_ui_body':lambda r:r['rows'][0].update(browser_answer_matches_actual_trace=False),
        'invented_review':lambda r:r.update(actual_browser_submissions=0),
        'formal_rerun':lambda r:r.update(new_formal_test_runs=1)}
    for name,change in changes.items():
        def run(change=change):
            value=copy.deepcopy(ui);change(value)
            try:replay_demo(value,True)
            except (ValueError,TypeError,KeyError,IndexError):return True
            return False
        check('reject_'+name,run)
    return {'version':'task13-public-cases-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'new_model_requests':0,'new_human_judgments':0,'site_packages_disabled':bool(sys.flags.no_site),'private_data_accessed':False,'source_sha256':{n:record(ROOT/n)['sha256'] for n in ('scripts/task13_replay.py','scripts/verify_task13_public_cases.py')}}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True);a=p.parse_args();v=verify();write_new(ROOT/a.report,v);print(json.dumps({k:v[k] for k in ('status','passed','total','errors')}));raise SystemExit(v['status']!='PASS')
