"""Audit E4 traces and build a report without another model request."""
import argparse,hashlib,json,math,subprocess,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import canonical,config,digest,now,record
from citation_catalog_guard import safe_render

def read(p):return json.loads(p.read_text('utf-8-sig'))
def ratio(n,d):return dict(numerator=n,denominator=d,value=n/d if d else None)
def quantile(xs,q):
    xs=sorted(xs)
    if not xs:return None
    v=(len(xs)-1)*q;a=math.floor(v);b=math.ceil(v);return xs[a]+(xs[b]-xs[a])*(v-a)
def percent(r):return f"{r['numerator']}/{r['denominator']}（{100*r['value']:.2f}%）" if r['value'] is not None else '无样本'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--browser-report',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    private=ROOT/'.runtime/phase2';cfg=config();refs={x['question_id']:x for x in read(ROOT/'optimization/baseline/e8b0fd6/trace_manifest.local.json')}
    labels={x['question_id']:x for x in map(json.loads,(ROOT/'data/eval/answer_eval.jsonl').read_text('utf8').splitlines())};baseq={x['question_id']:x for x in read(ROOT/'optimization/baseline/e8b0fd6/quality_labels.json')}
    corpus={x['chunk_id']:x for x in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    basetraces={qid:read(Path(ref['private_path'])) for qid,ref in refs.items()}
    runs={};qualities={'baseline':baseq}
    for mode in ['replay','live']:
        directory=private/f'e4-{mode}90';complete=read(directory/'completed.json');assert complete['records']==90 and complete['inputs_unchanged']
        traces={}
        for qid,h in complete['hashes'].items():
            path=directory/f'{qid}.json';assert digest(path.read_bytes())==h;traces[qid]=read(path)
        assert len(traces)==90 and set(traces)==set(labels)
        runs[mode]=traces
        q=[]
        for split in ['dev','test']:q+=read(private/f'e4-{mode}-{split}-metrics.json')['cases']
        qualities[mode]={x['question_id']:x for x in q};assert len(qualities[mode])==90
    def stats(traces,grades):
        counts=Counter(x['grade'] for x in grades.values());inputs=outputs=calls=retries=parse_errors=dup=restored=quoted=0;normal_equal=normal_total=0;details=[]
        for qid,t in traces.items():
            r=t['result'];q=labels[qid];grade=grades[qid];attempts=t['observations'].get('model_attempts',[])
            assert len(attempts)==r['chat_calls']<=2 and len(r['offered_ids'])<=5 and len(r['selected_ids'])<=3
            calls+=len(attempts);retries+=max(0,len(attempts)-1)
            for ix,at in enumerate(attempts):
                assert len(canonical(at['messages']))<=6200
                response=at.get('response',{});inputs+=response.get('prompt_eval_count',0);outputs+=response.get('eval_count',0)
                if r['attempts'][ix]['outcome']!='accepted':parse_errors+=1
                raw=response.get('message',{}).get('content')
                try:obj=json.loads(raw);ids=obj.get('chunk_ids')
                except (ValueError,TypeError,AttributeError):continue
                legal=(set(obj)=={'answerable','chunk_ids','reason'} and obj['answerable'] is True and obj['reason'] is None and isinstance(ids,list) and 1<=len(ids)<=3 and all(isinstance(cid,str) and cid.strip() and cid in r['offered_ids'] for cid in ids))
                if legal and len(set(ids))<len(ids):
                    dup+=1;restored+=int(r['attempts'][ix]['outcome']=='accepted')
            for pair in t.get('parser_comparison',[]):
                if 'baseline' in pair:normal_total+=1;normal_equal+=int(pair.get('E4')==pair['baseline']);assert pair.get('E4')==pair['baseline']
            if r['status']=='answered':
                assert safe_render(r['selected_ids'],corpus)==(r['answer'],r['citations']);quoted+=1
            responses=[x.get('response',{}) for x in attempts]
            details.append(dict(question_id=qid,question=q['question'],answerable=q['answerable'],grade=grade['grade'],point_mask=grade['point_mask'],supported_citation_ids=grade['supported_citation_ids'],note=grade['note'],status=r['status'],reason=r['reason'],selected_ids=r['selected_ids'],offered_ids=r['offered_ids'],model_calls=len(attempts),input_tokens=sum(x.get('prompt_eval_count',0) for x in responses),output_tokens=sum(x.get('eval_count',0) for x in responses),wall_seconds=r['wall_ns']/1e9,answer_seconds=sum(e['elapsed_ns'] for e in r['events'] if e['node']=='answer')/1e9,answer_sha256=digest(r['answer'].encode()),trace_sha256=digest(canonical(t))))
        return dict(counts=dict(counts),answerable_complete_accuracy=ratio(counts['correct'],72),overall_accuracy=ratio(counts['correct']+counts['correct_refusal'],90),correct_refusal_rate=ratio(counts['correct_refusal'],18),false_refusal_rate=ratio(counts['false_refusal'],72),citation_support_rate=ratio(sum(len(x['supported_citation_ids']) for x in grades.values()),sum(len(t['result']['selected_ids']) for t in traces.values())),requirement_coverage=ratio(sum(sum(x['point_mask']) for x in grades.values()),sum(len(x['point_mask']) for x in grades.values())),technical_completion=ratio(sum(t['result']['status']!='failed' for t in traces.values()),90),duplicate_id_recovery=ratio(restored,dup),parse_failure_response_rate=ratio(parse_errors,calls),normal_response_parser_equivalence=ratio(normal_equal,normal_total),quote_source_integrity=ratio(quoted,quoted),calls=calls,retries=retries,input_tokens=inputs,output_tokens=outputs,graph_p50_seconds=quantile([t['result']['wall_ns']/1e9 for t in traces.values()],.5),graph_p95_seconds=quantile([t['result']['wall_ns']/1e9 for t in traces.values()],.95),cases=sorted(details,key=lambda x:x['question_id']))
    allstats={'baseline':stats(basetraces,baseq),**{mode:stats(runs[mode],qualities[mode]) for mode in runs}}
    for mode,traces in runs.items():
        for qid,t in traces.items():
            prior=basetraces[qid];r=t['result'];assert r['retrieved_ids']==prior['result']['retrieved_ids'] and r['offered_ids']==prior['result']['offered_ids']
            old_attempts=prior['observations'].get('model_attempts',[]);new_attempts=t['observations']['model_attempts']
            if old_attempts and new_attempts:assert old_attempts[0]['messages']==new_attempts[0]['messages'] and old_attempts[0]['schema']==new_attempts[0]['schema']
    live_drift=[qid for qid in labels if any(runs['live'][qid]['result'][k]!=basetraces[qid]['result'][k] for k in ['status','answer','citations','selected_ids','reason'])]
    changed=[qid for qid in labels if any(runs['replay'][qid]['result'][k]!=basetraces[qid]['result'][k] for k in ['status','answer','citations','selected_ids','reason'])];assert changed==['D016'] or set(changed)=={'D016'}
    freeze=read(ROOT/'optimization/baseline/e8b0fd6/freeze.json');modified=[]
    for path,v in freeze['sources'].items():
        if record(ROOT/path)!=v:modified.append(path)
    assert set(modified)=={'scripts/answer_eval_core.py','scripts/rag_langgraph.py'}
    for path,v in freeze['data'].items():assert record(ROOT/path)==v
    sealed=read(ROOT/'optimization/datasets/freeze_manifest.json')
    for ref in sealed['files']:assert digest((ROOT/'optimization'/ref['path']).read_bytes())==ref['sha256']
    unit=read(private/'e4-unit-v2.json');controls=read(private/'e4-controls25.json');browser=read(a.browser_report)
    browser_passed=sum(row.get('passed',True) for row in browser);browser_ok=len(browser)==8 and browser_passed==8
    assert (ROOT/cfg['prompt_file']).read_bytes()==(ROOT/'optimization/baseline/e8b0fd6/prompt_A.txt').read_bytes()
    engineering=unit['status']=='PASS' and controls['status']=='PASS' and allstats['live']['technical_completion']['numerator']==90 and allstats['live']['duplicate_id_recovery']['value']==1 and allstats['live']['correct_refusal_rate']['numerator']==18 and browser_ok
    hist={qid for qid,g in baseq.items() if g['grade'] not in ('correct','correct_refusal')};assert len(hist)==22
    result=dict(created_at=now(),experiment='E4 only, Prompt A',implementation_commit=read(private/'e4-live90/metadata.json')['source_commit'],baseline_commit=freeze['source_commit'],decision='E4 engineering gates pass; E5 not executed' if engineering else 'Parser repair validated; shared regression gate incomplete; E5 not executed',metrics=allstats,isolated_changed_question_ids=changed,historical22={m:dict(fully_correct=sum(g[qid]['grade']=='correct' for qid in hist),total=22,errors=[qid for qid in sorted(hist) if g[qid]['grade'] not in ('correct','correct_refusal')]) for m,g in qualities.items()},unit=dict(status=unit['status'],passed=unit['passed'],total=unit['total'],checks=unit['checks'],private_sha256=digest((private/'e4-unit-v2.json').read_bytes())),controls25=dict(status=controls['status'],passed=controls['passed'],total=controls['total'],checks=controls['checks'],private_sha256=digest((private/'e4-controls25.json').read_bytes())),browser=dict(records=len(browser),passed=browser_passed,all_eight_pass=browser_ok,turns=browser,private_sha256=digest(a.browser_report.read_bytes()),scope='Real Chrome + audited linear worker; separate from graph timings'),data_and_prompt_integrity=dict(modified_baseline_source_files=modified,remaining_source_files_unchanged=221,data_files_unchanged=8,sealed_datasets_unchanged=True,prompt_A_unchanged=True),source_review_ledger=record(ROOT/'optimization/experiments/E4_duplicate_repair/source_reviews.tsv'),live_metadata=read(private/'e4-live90/metadata.json'),holdout_used=False)
    result['live_result_drift_ids']=live_drift
    result['frozen_first_inputs_identical_questions']=90
    result['prompt_and_selection_budget_violations']=0
    result['controlled_unknown_id_rejection']=ratio(sum(unit['checks'][k] for k in ['unknown_id','retrieved_but_not_offered_rejected']),2)
    result['controlled_source_and_hash_rejection']=ratio(sum(unit['checks'][k] for k in ['source_mismatch_after_normalization_rejected','body_hash_mismatch_before_generation_rejected']),2)
    a.out.mkdir(parents=True,exist_ok=True);(a.out/'phase2_E4_metrics.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
    base,replay,live=[allstats[m] for m in ['baseline','replay','live']]
    decision_text='E4工程门禁通过；本轮未执行E5。' if engineering else 'E4解析修复已验证；公共回归门禁未全部通过，本轮暂不进入E5。'
    lines=['# E4：重复 ID 解析可靠性修复','',decision_text,'',
      f"实现提交：`{result['implementation_commit']}`；基线：`{freeze['source_commit']}`。独立本地分支 `optimization/phase2-e4`，未合并生产分支。Prompt 始终为 A，本轮未执行 E1 新 Prompt、E2、E3、E5 或检索参数修改。",'',
      '## 根因与修改','',
      '根因位于冻结版 scripts/answer_eval_core.py:86：parse_selection 对重复 ID 直接抛错，合法来源被连同重复项一起丢弃；图最多两次重试仍可能重复失败。当前 normalize_chunk_ids 在该文件第82行，parse_selection 在第91行；图私有审计位于 scripts/rag_langgraph.py:219 的 answer 节点。offered_ids 来自 pack 实际装入 Prompt 的证据，并非完整检索 Top10。',
      '共用解析器现在依次验证结构/类型、非空精确 ID 和实际提供范围，稳定去重并保留第一次出现的顺序；原始数组与规范化结果仍各自最多3项。原始4项即使去重后只有1项也拒绝，不放宽原 Schema 数量上限。未知、未提供、空白、非字符串标识均拒绝；不修剪或猜测 ID。',
      '生产修改仅 scripts/answer_eval_core.py 和 scripts/rag_langgraph.py。图新增私有 selection_audits：保存原始 response 与 normalized_selection；原 attempts 公开投影字段不变。线性 Worker 原有 response＋parsed 日志直接保存原始/规范化双份结果，validate_attempts 回放仍通过。JSON Schema、Prompt、模型、重试上限、来源校验和正文哈希校验均保持。','',
      '## 专项与机制测试','',f"32项专项：{unit['passed']}/{unit['total']}；原25项机制：{controls['passed']}/{controls['total']}。其中重复项由原先预期重试2次改为预期1次稳定去重，其余机制预期保持。",'',
      '|检查|结果|','|---|---|']
    lines += ['|'+name+'|'+('PASS' if ok else 'FAIL')+'|' for name,ok in unit['checks'].items()]
    lines += ['','D016 与 D010-B 的原始首答都经真实 Flow 和线性请求适配器回放：一次调用后稳定去重，第二个已排队的重复响应未被请求。这里是历史响应回放，真实 Qwen 验证见下一节。最初离线回放测试适配器遗漏融合候选，导致2项测试失败；修正测试适配器后32项通过，失败记录保留，生产修复没有因此扩大范围。','',
      '## 固定旧响应：隔离 E4 的效果','',
      '使用冻结90题相同问题、候选、实际上下文及模型原始响应，通过当前完整图重放；没有新增真实模型请求。唯一改变结果的题为 D016：failed → answered，选择 L13-05、L17-01。其余89题的状态、答案、引用和拒答原因逐项一致。这证明不含重复的正常响应没有被改选。', '',
      '|指标|冻结基线|固定旧响应＋E4|真实完整图＋E4|','|---|---:|---:|---:|']
    for title,key in [('可答题完整正确率','answerable_complete_accuracy'),('整体正确率','overall_accuracy'),('正确拒答率','correct_refusal_rate'),('错误拒答率','false_refusal_rate'),('引用支持率','citation_support_rate'),('要点覆盖率','requirement_coverage'),('技术完成率','technical_completion'),('合法重复输出解析恢复率','duplicate_id_recovery'),('解析失败输出比例','parse_failure_response_rate')]:lines.append('|'+title+'|'+'|'.join(percent(m[key]) for m in [base,replay,live])+'|')
    lines += ['','历史22道失分题专项：固定旧响应完整恢复1/22（D016）；真实回归完整恢复2/22（D016、T014）。T014本轮模型选对来源，旧解析器同样接受，不计为去重的直接收益。18道无答案题真实结果17/18，失败题为D036。',
      '重复恢复率的分母随重试消除而变化：原D016两次重复均失败（0/2）；修复后首答即成功并停止（1/1），没有为了凑样本继续生成。',
      '回放列的模型调用/Token 是所采用历史响应的记账，回放本身没有发出这些请求；不可把回放耗时当真实推理延迟。真实回归重新执行检索、重排、生成、引用检查与图收尾。历史22题和18道无答案题均为90题子集，没有加进分母。正确率与引用评分由 Codex 核验原文，沿用逐字一致或已审阅的相同来源组合；新增来源组合单独核验。没有新增人工/专家审核，也没有使用新留出集。','',
      '|成本与性能|冻结基线|固定响应记账|真实完整图＋E4|','|---|---:|---:|---:|']
    for title,key in [('生成请求（含重试）','calls'),('额外重试次数','retries'),('输入Token','input_tokens'),('输出Token','output_tokens')]:lines.append(f"|{title}|{base[key]}|{replay[key]}|{live[key]}|")
    lines += [f"|图端到端P50（秒）|{base['graph_p50_seconds']:.3f}|不适用|{live['graph_p50_seconds']:.3f}|",f"|图端到端P95（秒）|{base['graph_p95_seconds']:.3f}|不适用|{live['graph_p95_seconds']:.3f}|",'',
      '端到端分位数按90题 Flow.invoke 计时，包含版本直接拒答；真实回归一次独立预热不计入题目Token和分位数。D016、D010排在前两题用于真实专项验证，其余按题号运行，合计90个唯一题目。线性浏览器耗时单列，不与图混算。与历史单轮耗时比较受执行顺序、机器负载及模型运行波动影响，不把所有差异归因于去重。','',
      '## 真实模型专项与归因','']
    for qid in ['D016','D010']:
        t=runs['live'][qid];r=t['result'];lines += [f"### {qid}",'',f"真实调用 {r['chat_calls']} 次，状态 {r['status']}，选择 {r['selected_ids']}。",'']
        for audit in r['selection_audits']:lines += ['原始输出：','```json',(audit.get('response') or {}).get('message',{}).get('content','<no response>'),'```','规范化输出：','```json',json.dumps(audit['normalized_selection'],ensure_ascii=False),'```','']
    lines += [f"本轮对同一实际响应的新旧解析器比较：正常合法响应 {percent(live['normal_response_parser_equivalence'])} 等价；合法重复响应恢复率 {percent(live['duplicate_id_recovery'])}。D016真实重复被恢复；D010本轮若无重复，只能证明正常请求通过，其重复首答路径由历史D010-B响应回放验证，未启用B Prompt。",'',
      f"真实已回答结果的原文/引用完整性：{percent(live['quote_source_integrity'])}；篡改正文、来源不匹配和未知ID仍由受控测试证明拒绝。线上没有未知ID样本时，不伪造线上未知ID拒绝率。",'',
      f"真实回归与冻结基线结果不同的题号：{','.join(live_drift)}。只有D016的改变在固定响应控制实验中能归因于E4。D036本轮返回依赛事而定的原文，旧解析器同样接受该响应，仍按must_refuse契约失败计分；没有改标签或将其描述为编造停赛数字。其他题的模型选段变化独立保留，不作为解析修复收益。",'',
      '## 浏览器门禁','',f"采集 {len(browser)}/8，验证通过 {browser_passed}/8。",'', '|轮次|问题|结果|来源|','|---|---|---|---|']
    lines += [f"|{i}|{b['question']}|{'PASS' if b.get('passed',True) else 'FAIL'}|{','.join(b['citations']) or '无'}|" for i,b in enumerate(browser,1)]
    lines += ['','表格、要点、来源追问须精确复用本会话原始来源且不调用Worker；代词追问须正确改写并选择支持段；话题切换和新会话不得污染。采集完成不等于通过。如出现选证错误，原样记录，不以E4名义改历史机制或Prompt。','',
      '## 结论与下一步边界','',
      decision_text,
      f"正确拒答目标为至少95%，本轮为{percent(live['correct_refusal_rate'])}，仍有D036失败。该题的业务拒答契约与条件性原文回答保留待后续审计，本轮没有重标或降低验收标准。",
      'E4只修复可确定性恢复的重复标识，不能解决有证据却拒答、主题相近却选错、复合问题漏答或T034上下文遗漏。本轮没有执行E5；是否进入下一项按上述实际门禁决定，不能用解析成功替代语义质量。',
      '',f"冻结源码223项中，只有明确授权的2个生产源文件改变；另221项、8个数据文件、A Prompt及4个封存数据集哈希保持。新40题留出集仍待人工审核，本轮未用于调参、计分或模型请求。",'',
      '完整逐题指标、原始/规范化输出、源文件及数据哈希保存在伴随JSON及本机私有 .runtime/phase2/e4-live90。']
    text='\n'.join(lines).rstrip()+'\n';(a.out/'phase2_E4_duplicate_repair.md').write_bytes(text.encode('utf8'))
    (ROOT/'optimization/experiments/E4_duplicate_repair.md').write_bytes(text.encode('utf8'))
    print(json.dumps(dict(decision=result['decision'],live={k:v for k,v in live.items() if k!='cases'},browser_passed=browser_passed),ensure_ascii=False))
if __name__=='__main__':main()
