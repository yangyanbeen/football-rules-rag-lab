"""Read-only reproductions of original Task13 validation/runtime gaps."""
import argparse,copy,subprocess
from unittest.mock import patch
from task13_core import *


def reproduce():
    import task13_worker_client as client,task13_package as package
    from task13_replay import replay_demo
    from answer_eval_engine import request_json
    from rag_b0 import GenerationRejected
    checks={}
    with patch.object(client.subprocess,'run',side_effect=subprocess.TimeoutExpired('worker',420)):
        try:client.call_worker('test')
        except subprocess.TimeoutExpired:checks['timeout_escapes_UI_supported_error_types']=not issubclass(subprocess.TimeoutExpired,(ValueError,KeyError,TypeError,OSError,RuntimeError,TimeoutError))
    manifest=copy.deepcopy(read(ROOT/'reports/task13/delivery_manifest.json'))
    manifest['public_members']=[r for r in manifest['public_members'] if r['path']!='scripts/query_task13.py']
    checks['missing_worker_package_member_accepted']=package.verify(manifest)
    ui=copy.deepcopy(read(ROOT/'reports/task13/ui-demo.json'));ui['rows'][0]['result']['answer']='UNEXPECTED_PRIVATE_BODY'
    checks['extra_full_answer_field_accepted']=replay_demo(ui,True)
    ui=copy.deepcopy(read(ROOT/'reports/task13/ui-demo.json'));ui['rows'][0]['result']['citations'][0]['source_url']='https://en.wikipedia.org/wiki/Unrelated_page'
    checks['unrelated_same_origin_citation_accepted']=replay_demo(ui,True)
    cfg=copy.deepcopy(app_config());cfg['ui']['share']=0;path=ROOT/'.tmp/task13-audit'/('share-zero-'+uuid.uuid4().hex+'.json');write_new(path,cfg)
    checks['integer_zero_accepted_as_boolean_config']=app_config(path.relative_to(ROOT).as_posix())['ui']['share']==0
    row=next(r for r in read(ROOT/'reports/task13/backend-demo-first.json')['rows'] if r['id']=='outside')
    failure=copy.deepcopy(read(ROOT/row['result']['private_trace']['path']));failure.update(error='RuntimeError: service failed',refusal_reason='runtime_or_validation_error',attempts=[])
    checks['failed_runtime_validates_as_refusal']=validate_result(failure,failure['question'])
    with patch('answer_json_chat.generate',side_effect=GenerationRejected('Wrong pinned model',{},retryable=False)) as generated:
        request_json(None,[{'role':'user','content':'test'}],answer_config(),lambda s:s,{})
        checks['nonretryable_identity_error_requested_twice']=generated.call_count==2
    return {'version':'task13-original-gap-reproduction-1.0','captured_at':now(),'status':'GAPS_REPRODUCED' if all(checks.values()) else 'REPRODUCTION_INCOMPLETE','reproduced':sum(checks.values()),'total':len(checks),'checks':checks,'new_model_requests':0,'new_human_judgments':0,'scope':'Controlled copies/mocks of original code. True means an original gap reproduced, not an accepted production answer. No old evidence modified.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',required=True);a=p.parse_args();v=reproduce();write_new(ROOT/a.report,v);print(json.dumps(v,ensure_ascii=False));raise SystemExit(v['reproduced']!=v['total'])
