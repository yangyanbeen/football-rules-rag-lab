"""Run the existing 15 graph controls and ten additional boundary scenarios."""
import json
import os
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
target = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(root/'scripts'))
os.environ['LANGSMITH_TRACING'] = 'false'
os.environ['LANGCHAIN_TRACING_V2'] = 'false'
from answer_eval_core import now, record
from rag_langgraph import Flow
from run_langgraph_flow import runtime_identity
from verify_langgraph_controls import Fixture, NORMAL, QUESTION, run

runtime_identity()
base = run()
checks = dict(base['checks'])
cases = dict(base['cases'])
errors = list(base['errors'])


def rejected_input(name, question=QUESTION, request_id=None):
    ops = Fixture()
    try:
        Flow(ops).invoke(question, request_id=request_id)
        checks[name] = False
        errors.append({'check':name,'error':'Expected input rejection'})
    except ValueError:
        checks[name] = ops.chat_calls == 0 and ops.received == []


def case(name, ops, status, reason, calls):
    value = Flow(ops).invoke(QUESTION)
    checks[name] = (value['status']==status and value['reason']==reason and value['chat_calls']==calls
                    and value['events'][-1]['node']=='finish' and len(value['attempts'])<=2)
    cases[name] = {key:value[key] for key in ('request_id','status','reason','attempts','events','chat_calls','selected_ids')}
    if not checks[name]:
        errors.append({'check':name,'error':'Unexpected branch or call count'})


rejected_input('oversize_question_rejected_before_operations', '问'*401)
rejected_input('nontext_question_rejected_before_operations', question=123)
rejected_input('invalid_request_id_rejected_before_operations', request_id='user-001')
duplicate = {'answerable':True,'chunk_ids':['fixture-1','fixture-1'],'reason':None}
unknown = {'answerable':True,'chunk_ids':['unknown'],'reason':None}
wrong_type = {'answerable':'true','chunk_ids':['fixture-1'],'reason':None}
case('duplicate_selection_normalizes_without_retry',Fixture([duplicate,NORMAL]),'answered',None,1)
case('unoffered_selection_repair_succeeds',Fixture([unknown,NORMAL]),'answered',None,2)
case('answerable_type_repair_succeeds',Fixture([wrong_type,NORMAL]),'answered',None,2)
case('source_conflict_refusal_preserved',Fixture([{'answerable':False,'chunk_ids':[],'reason':'source_conflict'}]),
     'refused','source_conflict',1)
tampered = Fixture([NORMAL])
tampered.evidence['content_zh'] = 'changed content without updating source hash'
case('changed_body_rejected_before_generation',tampered,'failed','context_integrity_error',0)
fusion_failure = Fixture()


def fail_fusion(*args):
    raise RuntimeError('controlled fusion unavailable')


fusion_failure.fusion = fail_fusion
case('fusion_failure_stops_before_model',fusion_failure,'failed','stage_error',0)
empty_rerank = Fixture()
empty_rerank.rerank = lambda *args: []
case('empty_rerank_refuses_without_model',empty_rerank,'refused','no_whole_evidence_within_budget',0)
assert len(checks)==25
result = {'created_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),
          'total':len(checks),'checks':checks,'errors':errors,'cases':cases,
          'flow_source':record(root/'scripts/rag_langgraph.py'),
          'scope':'25 checks through real compiled StateGraph with deliberately synthetic adapters; model requests are zero.'}
with target.open('x',encoding='utf-8') as f:
    json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({key:result[key] for key in ('status','passed','total','errors')},ensure_ascii=False))
raise SystemExit(result['status']!='PASS')
