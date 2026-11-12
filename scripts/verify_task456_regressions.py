"""Regression and preservation checks for the Task 4-6 delivery supplement."""
from __future__ import annotations
import argparse,copy,json,shutil,subprocess,sys,threading
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import dense_index,rag_b0
from rag_b0_worker_client import call_worker
from eval_dataset import ROOT,digest,load_jsonl,write_json
from validate_eval_receipt import validate_receipt
from validate_rag_b0_receipts import validate_receipts
from audit_remote_delivery import TASK6_RELEASE,release_is_ancestor
from smoke_rag_b0 import smoke_passed


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--reference-commit',default='HEAD');args=parser.parse_args()
    report=args.report.resolve()
    if report.exists() or not report.is_relative_to(ROOT/'reports'):raise ValueError('Use a new report path')
    temp=ROOT/'.tmp'/('task456-regression-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'));temp.mkdir(parents=True)
    runtime=ROOT/'.runtime/rag-b0'/temp.name;runtime.mkdir(parents=True)
    checks={}
    def record(name,value):checks[name]=bool(value)
    def rejects(fn):
        try:fn()
        except ValueError:return True
        return False
    cfg=rag_b0.load_config();sample=load_jsonl(ROOT/'reports/rag_b0_smoke.jsonl')[0];packet=sample['generation']['raw_response']
    record('unchanged_original_config_accepted',cfg['llm']['num_predict']==1024)
    for name,section,field,value in [('negative_predict','llm','num_predict',-1),('boolean_predict','llm','num_predict',True),
        ('boolean_gpu','llm','num_gpu',False),('boolean_threads','llm','num_thread',True),('negative_timeout','llm','timeout_seconds',-1),
        ('bad_port','ui','port',-1),('remote_host','ui','host','0.0.0.0'),('negative_budget',None,'input_utf8_byte_budget',-1),
        ('boolean_temperature','llm','temperature',False),('wrong_digest','llm','digest','bad'),('unknown_option','llm','api','/ignored')]:
        changed=copy.deepcopy(cfg);(changed if section is None else changed[section])[field]=value
        path=temp/(name+'.json');write_json(path,changed)
        record('config_reject_'+name,rejects(lambda p=path:rag_b0.load_config(p)))
    chat=rag_b0.PinnedChat(cfg)
    cases=[('wrong_model',lambda r:r.update(model='wrong')),('missing_count',lambda r:r.pop('prompt_eval_count')),
        ('negative_count',lambda r:r.update(prompt_eval_count=-1)),('boolean_count',lambda r:r.update(eval_count=True)),
        ('wrong_role',lambda r:r['message'].update(role='user')),('missing_message',lambda r:r.pop('message')),
        ('overflow',lambda r:r.update(prompt_eval_count=cfg['llm']['num_ctx'])),('too_many_predictions',lambda r:r.update(eval_count=1025)),
        ('truncated',lambda r:r.update(done_reason='length'))]
    for name,mutate in cases:
        bad=copy.deepcopy(packet);mutate(bad)
        with patch.object(chat,'verify_model'),patch.object(chat,'request',return_value=bad):
            record('model_packet_reject_'+name,rejects(lambda:chat.generate([])))
    with patch.object(chat,'verify_model'),patch.object(chat,'request',return_value=packet):
        record('valid_real_model_packet_accepted',chat.generate([])==packet)
    with patch.object(chat,'verify_model',side_effect=[None,ValueError('changed pin')]),patch.object(chat,'request',return_value=packet):
        try:chat.generate([]);preserved=False
        except rag_b0.GenerationRejected as exc:preserved=exc.response==packet and not exc.retryable and exc.stage=='post_generation_model_identity'
        record('post_generation_pin_failure_preserves_response',preserved)
    def engine():
        obj=rag_b0.RagB0Engine.__new__(rag_b0.RagB0Engine)
        obj.config=cfg;obj.config_sha256=digest(rag_b0.CONFIG.read_bytes());obj.prompt=(ROOT/cfg['prompt_file']).read_text('utf-8');obj.prompt_sha256=digest(obj.prompt.encode())
        obj.index=SimpleNamespace(path=dense_index.DEFAULT_INDEX,query=lambda *a:copy.deepcopy(sample['retrieval']));obj.lock=threading.RLock();return obj
    obj=engine();bad=copy.deepcopy(packet);bad['message']['content']='REFUSE: 资料不足，但球门高度肯定是999米。'
    obj.chat=SimpleNamespace(generate=lambda *a:bad);row=obj.answer('临时故障检查')
    record('refusal_displays_only_controlled_text',row['status']=='refused' and row['answer']==rag_b0.REFUSAL and not row['citations'])
    record('untrusted_refusal_reason_preserved_privately','999' in row['generation']['raw_content'])
    obj=engine();obj.chat=SimpleNamespace(generate=lambda *a:(_ for _ in ()).throw(OSError('deliberate network failure')))
    row=obj.answer('临时故障检查')
    record('network_failure_has_per_attempt_error',len(row['attempts'])==1 and row['attempts'][0]['validation_error'] and row['attempts'][0]['error_stage']=='model_request')
    obj=engine();obj.chat=SimpleNamespace(generate=lambda *a:None)
    with patch.object(obj.chat,'generate',side_effect=[rag_b0.GenerationRejected('deliberate truncation',packet),OSError('second failure')]):row=obj.answer('临时故障检查')
    record('failed_retry_does_not_reuse_previous_generation',len(row['attempts'])==2 and row['generation'] is None and row['attempts'][0]['generation'] is not None and row['attempts'][-1]['validation_error'])
    def worker_result(value):
        def fake(command,**kwargs):
            write_json(Path(command[command.index('--trace')+1]),value)
            return SimpleNamespace(returncode=0,stdout='{}',stderr='')
        with patch('rag_b0_worker_client.subprocess.run',side_effect=fake):return call_worker(sample['question'])
    record('valid_real_worker_trace_accepted',worker_result(copy.deepcopy(sample))['status']=='answered')
    mutations=[('missing_timing',lambda r:r.pop('timing')),('wrong_status',lambda r:r.update(status='invented')),
        ('forged_url',lambda r:r['citations'][0].update(source_url='https://invalid.example/invented')),
        ('forged_answer',lambda r:r.update(answer='这是伪造的答案。')),('stale_config',lambda r:r.update(config_sha256='0'*64)),
        ('bad_messages',lambda r:r.update(messages=[None])),('forged_body',lambda r:r['context'][0].update(content_zh='伪造原文。')),
        ('raw_response_mismatch',lambda r:r['generation']['raw_response']['message'].update(content='ANSWER: 伪造的另一条内容。')),
        ('summary_token_mismatch',lambda r:r['generation'].update(eval_count=999)),
        ('missing_generation_flag',lambda r:r.update(generation_attempted=False))]
    for name,mutate in mutations:
        changed=copy.deepcopy(sample);mutate(changed);result=worker_result(changed)
        record('worker_reject_'+name,result['status']=='refused' and result['refusal_reason']=='isolated_worker_failed' and not result['citations'])
    record('malformed_worker_does_not_crash',worker_result({'question':sample['question']})['status']=='refused')
    record('nontext_worker_input_fails_closed',call_worker(None)['status']=='refused')
    ready={'status':'READY','records':50,'config_sha256':digest(rag_b0.CONFIG.read_bytes())}
    with patch('rag_b0_worker_client.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(ready),stderr='')):
        record('wrong_ready_record_count_rejected',rejects(lambda:call_worker(check=True)))
    fixture=temp/'receipt-fixture';shutil.copytree(ROOT/'data/eval',fixture/'data/eval')
    for name in ('docs/TECHNICAL_DESIGN.md','docs/DEVELOPMENT_PLAN_AND_REPORT.md','docs/UPSTREAM_VERSION.md',
                 'data/processed/rag_chunks_zh.jsonl','data/manifests/rag_dataset_manifest.json'):
        dst=fixture/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dst)
    path=fixture/'data/eval/human_review_receipt.json';receipt=json.loads(path.read_text('utf-8'));receipt['records'][0]['decision']='changes_requested';write_json(path,receipt)
    path=fixture/'data/eval/dataset_manifest.json';manifest=json.loads(path.read_text('utf-8'));manifest['human_review']['receipt_sha256']=digest((fixture/'data/eval/human_review_receipt.json').read_bytes());write_json(path,manifest)
    with patch.object(dense_index,'ROOT',fixture),patch.object(dense_index.subprocess,'check_output',return_value=dense_index.UPSTREAM):
        record('task5_rejects_rehashed_invalid_human_receipt',rejects(dense_index.snapshot_inputs))
    record('real_original_task4_receipt_still_valid',validate_receipt()['status']=='PASS_PUBLIC_RECEIPT')
    smoke=ROOT/'reports/evidence/rag_b0_smoke_manifest.json';ui=ROOT/'reports/evidence/rag_b0_ui_manifest.json'
    record('original_public_rag_receipts_valid',validate_receipts(smoke,ui)['status']=='PASS_PUBLIC_RECEIPTS')
    for name,mutate in [('duplicate_question',lambda s,u:s['rows'][1].update(question=s['rows'][0]['question'])),
        ('wrong_ui_count',lambda s,u:u.update(answered=99)),('wrong_body_hash',lambda s,u:s['rows'][0]['citations'][0].update(content_zh_sha256='0'*64)),
        ('wrong_config',lambda s,u:u['rows'][0].update(config_sha256='0'*64)),('error_masquerades_refusal',lambda s,u:s['rows'][-1].update(error='model failed'))]:
        s=json.loads(smoke.read_text('utf-8'));u=json.loads(ui.read_text('utf-8'));mutate(s,u)
        sp=temp/(name+'-smoke.json');up=temp/(name+'-ui.json');write_json(sp,s);write_json(up,u)
        record('public_receipt_reject_'+name,validate_receipts(sp,up)['status']=='FAIL')
    public=temp/'public-only'
    for name in ('scripts/eval_dataset.py','scripts/validate_rag_b0_receipts.py','config/rag_b0.json','config/rag_b0_system.txt',
        'data/manifests/dense_chunk_ids.json','reports/evidence/rag_b0_smoke_manifest.json','reports/evidence/rag_b0_ui_manifest.json'):
        target=public/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
    proc=subprocess.run([sys.executable,'-B','scripts/validate_rag_b0_receipts.py'],cwd=public,capture_output=True,text=True,encoding='utf-8',timeout=30)
    record('public_only_receipt_check_without_corpus_models_or_private_logs',proc.returncode==0 and not (public/'data/processed').exists() and not (public/'.runtime').exists())
    captures=load_jsonl(ROOT/'.runtime/rag-b0/ui-captures.jsonl');wanted={r['trace_id'] for r in captures}
    journal=[r for r in load_jsonl(ROOT/'.runtime/rag-b0/ui-events-delivery-snapshot.jsonl') if r['trace_id'] in wanted]
    cap=runtime/'captures.jsonl';log=runtime/'journal.jsonl'
    for path,values in ((cap,captures),(log,journal)):path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in values),encoding='utf-8')
    ui_output=temp/'new-ui-receipt.json'
    proc=subprocess.run([sys.executable,'-B','scripts/summarize_rag_b0_ui.py','--captures',str(cap),'--journal',str(log),'--output',str(ui_output)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=30)
    record('new_ui_receipt_needs_no_archived_prototype_failures',proc.returncode==0 and ui_output.exists())
    gate=temp/'portable-task6.json'
    # Gate reports are intentionally under reports; this is a current recheck,
    # using old real captures as a regression fixture, not new browser evidence.
    gate=report.parent/'task6_portability_regression.json'
    if gate.exists():raise ValueError('Portable gate report already exists; use a new report directory')
    proc=subprocess.run([sys.executable,'-B','scripts/verify_rag_b0.py','--report',str(gate),'--ui-captures',str(cap),
        '--ui-journal',str(log),'--reference-commit',args.reference_commit],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=90)
    record('task6_gate_runs_without_hardcoded_private_trace',proc.returncode==0 and json.loads(gate.read_text('utf-8'))['status']=='PASS')
    current=subprocess.check_output(['git','rev-parse',args.reference_commit],cwd=ROOT,text=True).strip()
    record('original_task6_release_survives_authorized_descendant',release_is_ancestor(TASK6_RELEASE,current))
    record('moved_original_task6_tag_rejected',not release_is_ancestor(current,current) if current!=TASK6_RELEASE else True)
    failed=copy.deepcopy(load_jsonl(ROOT/'reports/rag_b0_smoke.jsonl'));failed[-1]['error']='deliberate service failure'
    record('smoke_does_not_count_service_failure_as_correct_refusal',not smoke_passed(failed))
    baseline=json.loads((ROOT/'.runtime/task456-audit/before.json').read_text('utf-8'))
    record('original_index_and_manifest_unchanged',baseline['index']=={**dense_index.inventory(dense_index.DEFAULT_INDEX),'index_manifest.json':digest((dense_index.DEFAULT_INDEX/'index_manifest.json').read_bytes())})
    record('original_real_human_ledger_unchanged',baseline['ledger_sha256']==digest((ROOT/'.runtime/eval_review/reviews.jsonl').read_bytes()))
    historical={p:s for p,s in baseline['tracked'].items() if p.startswith(('data/eval/','reports/')) and p not in ('reports/README.md','reports/all_experiments_summary.csv','reports/resume_evidence.md')}
    record('original_delivery_reports_and_evaluation_bytes_unchanged',all(digest((ROOT/p).read_bytes())==sha for p,sha in historical.items()))
    result={'captured_at':datetime.now(timezone.utc).isoformat(),'status':'PASS' if all(checks.values()) else 'FAIL',
        'passed':sum(checks.values()),'total':len(checks),'checks':checks,'reference_commit':current,
        'real_human_reviews_created':False,'real_model_requests_in_this_script':0,'formal_quality_metrics_computed':False,
        'scope':'Simulated packets and isolated fixtures; portable gate replays preserved real smoke/UI. Fresh live evidence is reported separately.',
        'source_sha256':{name:digest((ROOT/'scripts'/name).read_bytes()) for name in ('dense_index.py','rag_b0.py','rag_b0_worker_client.py',
            'verify_rag_b0.py','summarize_rag_b0_ui.py','validate_rag_b0_receipts.py','verify_task456_regressions.py','audit_remote_delivery.py')}}
    write_json(report,result)
    print(json.dumps({'status':result['status'],'passed':result['passed'],'total':result['total'],'failed':[k for k,v in checks.items() if not v]}))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
