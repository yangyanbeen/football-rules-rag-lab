"""Summarize the frozen business-gate run and independent A1-relative source scores."""
import argparse,csv,hashlib,io,json,math,subprocess
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PRIVATE=ROOT/'.runtime/phase2'
def read(p):return json.loads(p.read_text('utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def ratio(n,d):return dict(numerator=n,denominator=d,value=n/d if d else None)
def quantile(xs,p):
    xs=sorted(xs);at=(len(xs)-1)*p;lo=int(at);return xs[lo]+(xs[math.ceil(at)]-xs[lo])*(at-lo)
def summary(cases,traces):
    counts=Counter(v['grade'] for v in cases)
    return dict(counts=dict(counts),answerable_complete_accuracy=ratio(counts['correct'],72),
                overall_accuracy=ratio(counts['correct']+counts['correct_refusal'],90),
                correct_refusal_rate=ratio(counts['correct_refusal'],18),false_refusal_rate=ratio(counts['false_refusal'],72),
                technical_completion=ratio(sum(v['status']!='failed' for v in cases),90),
                citation_support_rate=ratio(sum(len(v['supported_citation_ids']) for v in cases),sum(len(v['selected_ids']) for v in cases)),
                requirement_coverage=ratio(sum(sum(v['point_mask']) for v in cases),sum(len(v['point_mask']) for v in cases)),
                model_calls=sum(v['chat_calls'] for v in cases),input_tokens=sum(v['input_tokens'] for v in cases),output_tokens=sum(v['output_tokens'] for v in cases),
                graph_p50_seconds=quantile([t['result']['wall_ns']/1e9 for t in traces.values()],.5),
                graph_p95_seconds=quantile([t['result']['wall_ns']/1e9 for t in traces.values()],.95))
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    reference=read(ROOT/'optimization/reports/phase2_E4_metrics.json')['metrics']['live'];old={v['question_id']:v for v in reference['cases']}
    modes={};cases_by_mode={};traces_by_mode={}
    for mode in ('replay','live'):
        run=PRIVATE/('d036-gate-'+mode+'90-final'+('-v2' if mode=='replay' else ''));completed=read(run/'completed.json');meta=read(run/'metadata.json')
        assert completed['records']==90
        traces={qid:read(run/(qid+'.json')) for qid in completed['hashes']}
        for qid,digest in completed['hashes'].items():assert sha(run/(qid+'.json'))==digest
        cases=[]
        for split in ('dev','test'):
            suffix='replay-final' if mode=='replay' else 'live'
            cases+=read(PRIVATE/f'd036-gate-{suffix}-{split}-metrics.json')['cases']
        assert len(cases)==len({v['question_id'] for v in cases})==90
        for t in traces.values():
            r=t['result'];ats=t['observations']['model_attempts'];assert len(ats)==r['chat_calls']<=2
            assert len(r['offered_ids'])<=5 and len(r['selected_ids'])<=3
            assert all(len(canonical(v['messages']))<=6200 for v in ats)
        modes[mode]=summary(cases,traces);cases_by_mode[mode]=cases;traces_by_mode[mode]=traces
    live=cases_by_mode['live'];by={v['question_id']:v for v in live}
    ranks={'runtime_error':0,'false_refusal':1,'incorrect':1,'partial':2,'correct':3,'correct_refusal':3}
    regressions=[q for q in by if ranks[by[q]['grade']]<ranks[old[q]['grade']]]
    gains=[q for q in by if ranks[by[q]['grade']]>ranks[old[q]['grade']]]
    new_false=[q for q in by if by[q]['answerable'] and by[q]['grade']=='false_refusal' and old[q]['grade']!='false_refusal']
    drift=[q for q in by if any(traces_by_mode['live'][q]['result'][k]!=old[q][k] for k in ('status','selected_ids'))]
    replay_changes=[t['question_id'] for t in traces_by_mode['replay'].values() if not all(t['comparison'].values())]
    assert replay_changes==['D036']
    boundary=read(PRIVATE/'d036-gate-boundaries-v5.json');parser=read(PRIVATE/'d036-gate-parser32.json');controls=read(PRIVATE/'d036-gate-controls25-final.json')
    worker=read(PRIVATE/'d036-gate-live-worker-v2.json');browser=read(PRIVATE/'d036-gate-browser.json')
    m=modes['live']
    gates=dict(boundary=boundary['status']=='PASS',parser=parser['status']=='PASS',mechanisms=controls['status']=='PASS',
               A1_control_replay=replay_changes==['D036'],worker_boundaries=all(v['passed'] for v in worker) and len(worker)==7,
               browser=len(browser)==9 and all(v.get('passed',True) for v in browser),
               correct_refusal_18_of_18=m['correct_refusal_rate']['numerator']==18,
               complete_at_least_51=m['answerable_complete_accuracy']['numerator']>=51,
               technical_90_of_90=m['technical_completion']['numerator']==90,no_new_false_refusals=not new_false)
    frozen=read(ROOT/'optimization/baseline/e8b0fd6/freeze.json')
    for name,ref in frozen['data'].items():assert sha(ROOT/name)==ref['sha256']
    assert sha(ROOT/'config/answer_evaluation_system.txt')==sha(ROOT/'optimization/baseline/e8b0fd6/prompt_A.txt')
    for ref in read(ROOT/'optimization/datasets/freeze_manifest.json')['files']:assert sha(ROOT/'optimization'/ref['path'])==ref['sha256']
    same_inputs=[]
    for q,t in traces_by_mode['live'].items():
        prior=read(PRIVATE/'e4-live90'/(q+'.json'))
        ats=t['observations']['model_attempts'];before=prior['observations']['model_attempts']
        if ats and before and ats[0]['messages']==before[0]['messages'] and ats[0]['schema']==before[0]['schema']:same_inputs.append(q)
    result=dict(status='PASS_D036_GATE' if all(gates.values()) else 'FAIL_D036_ACCEPTANCE',gates=gates,
                production_ready=False,overall_zero_regression=not regressions,
                citation_nonregression=m['citation_support_rate']['value']>=reference['citation_support_rate']['value'],
                implementation_commit=read(PRIVATE/'d036-gate-live90-final/metadata.json')['source_commit'],
                A1=reference,replay=modes['replay'],live=m,new_false_refusals=new_false,
                gains=gains,regressions=regressions,result_drift_ids=drift,isolated_replay_changes=replay_changes,
                unchanged_first_model_inputs=same_inputs,boundary=boundary,
                parser={k:parser[k] for k in ('status','passed','total','checks','sources','scope')},
                mechanisms={k:controls[k] for k in ('status','passed','total','checks','errors','flow_source','scope')},
                worker=[{k:v for k,v in row.items() if k!='answer'} for row in worker],
                browser=browser,cases=live,data_prompt_holdout_unchanged=True,holdout_used=False,
                scope='One shared business decision; quality labels reused from prior Codex source audits or separately reviewed paragraph sets. No new human/expert review.')
    result['source_review_ledger']={'path':'optimization/experiments/D036_business_gate/source_reviews.tsv','sha256':sha(ROOT/'optimization/experiments/D036_business_gate/source_reviews.tsv')}
    (a.out/'D036_business_gate_metrics.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    buf=io.StringIO(newline='');w=csv.writer(buf,lineterminator='\n');w.writerow(['question_id','question','A1_grade','candidate_grade','A1_status','candidate_status','A1_selected_ids','candidate_selected_ids','A1_point_mask','candidate_point_mask','business_rule_hit','model_calls','input_tokens','output_tokens'])
    for q in sorted(by):
        v=by[q];b=old[q];t=traces_by_mode['live'][q]
        w.writerow([q,v['question'],b['grade'],v['grade'],b['status'],v['status'],','.join(b['selected_ids']),','.join(v['selected_ids']),''.join(str(int(x)) for x in b['point_mask']),''.join(str(int(x)) for x in v['point_mask']),bool(t['result'].get('business_decision')),v['chat_calls'],v['input_tokens'],v['output_tokens']])
    (a.out/'D036_business_gate_cases.csv').write_bytes(b'\xef\xbb\xbf'+buf.getvalue().encode())
    report(a.out,result,traces_by_mode)
    print(json.dumps(dict(status=result['status'],gates=gates,metrics=m,gains=gains,regressions=regressions,new_false_refusals=new_false),ensure_ascii=False))
def report(out,r,traces):
    lines=['# D036 确定性拒答门禁修复与90题回归','',f"验收判定：**{r['status']}**。实现提交：`{r['implementation_commit']}`。对照是A1/E4的真实90题，当前候选仅加入缺参累计黄牌处罚查询的运行时业务判断。",'',
           '该通过仅限用户指定的缺参拒答验收：真实新调用中T014正确→错误，引用支持率62.39%→61.02%；T005由误拒答恢复正确，不能据完整正确数仍为51/72宣称逐题零退化。整体质量仍有未通过的验收项，当前分支不合并、不推送。', '',
           '## 规则与接口','',
           'scripts/disciplinary_query_policy.py由图和默认线性Worker共用。在有效问题完成输入校验、入口已有历史改写之后，判断跨场累计黄牌＋索要具体停赛场数＋缺赛事或赛季；命中即在检索和回答模型前返回refused，提示补充缺失项。',
           '一般原因解释、同场纪律问题、参数齐全和意图不明确的问题继续原流程。参数齐全不代表资料足以回答某赛季处罚，仍由原检索/生成链路决定。识别覆盖本次35个中文边界用例及常见明确赛事名称、年份/赛季范围、显式赛事标签；不声称覆盖所有自然语言表达。',
           '公开refusal_reason仍用已有insufficient_evidence；私有business_decision记录规则、意图、缺失字段和已识别参数。校验器按有效问题重算业务决定，并严格绑定提示、零检索和零模型调用。没有扩展公开字段集合；同步纳入源文件版本校验。来源哈希、引用渲染和最多两次回答模型调用仍保留。', '',
           '## 三关验收','', '|检查|结果|','|---|---|']
    for name,passed in r['gates'].items():lines.append(f"|{name}|{'PASS' if passed else 'FAIL'}|")
    lines+=['',f"双入口边界{r['boundary']['passed']}/{r['boundary']['total']}；E4解析{r['parser']['passed']}/{r['parser']['total']}；机制{r['mechanisms']['passed']}/{r['mechanisms']['total']}。边界用例、Worker与浏览器场景独立记录，不计入原90题分母。",'',
            'A0拒答响应与E4选择L12-09响应分别回放到两个入口，均在回答模型前结束、原响应未消费。A1全部90题控制回放只有D036状态/提示改变，其他89题状态、选段、引用、全文及原因完全一致。回放本身没有真实模型请求，其耗时不能当成在线推理延迟。', '',
            '## 同一固定90题指标','', '|指标|A1/E4实测|固定A1响应控制回放|候选真实推理|','|---|---:|---:|---:|']
    for label,key in [('可答完整正确','answerable_complete_accuracy'),('整体正确','overall_accuracy'),('正确拒答','correct_refusal_rate'),('错误拒答','false_refusal_rate'),('技术完成','technical_completion'),('引用支持','citation_support_rate'),('必要要点覆盖','requirement_coverage')]:
        def val(x):v=x[key];return f"{v['numerator']}/{v['denominator']}（{100*v['value']:.2f}%）"
        lines.append(f"|{label}|{val(r['A1'])}|{val(r['replay'])}|{val(r['live'])}|")
    for label,key,oldkey in [('模型调用','model_calls','calls'),('输入Token','input_tokens','input_tokens'),('输出Token','output_tokens','output_tokens')]:
        lines.append(f"|{label}|{r['A1'][oldkey]}|{r['replay'][key]}（历史响应记账）|{r['live'][key]}|")
    lines += ['',f"候选实际Graph延迟：P50={r['live']['graph_p50_seconds']:.3f}s，P95={r['live']['graph_p95_seconds']:.3f}s；A1分别为{r['A1']['graph_p50_seconds']:.3f}s、{r['A1']['graph_p95_seconds']:.3f}s。均按90次Flow调用计，包含前置拒答；预热排除。不同轮次的负载与模型状态影响比较，不宣称稳定加速。",'',
              '## 逐题得失与新增误拒答','',
              f"改善题：{','.join(r['gains']) or '无'}。退化题：{','.join(r['regressions']) or '无'}。新增可答题误拒答：{','.join(r['new_false_refusals']) or '无'}。",'',
              f"首个实际回答请求的消息和Schema与A1逐字一致：{len(r['unchanged_first_model_inputs'])}题。固定响应控制中仅D036变化；真实新调用中其余选段差异必须作为模型决策变化另列，不能统算为规则收益。",'',
              '评分保持冻结口径：D009本轮结果逐字复现A0，沿用A0的引用审核掩码，仅计L08A-02；没有因其他实验中不同选段组合的审核记录而重标本次输出。全部新组合/复用依据在source_reviews.tsv，既有冻结标签未修改。', '',
              '|题号|A1|候选|候选选段|规则命中|','|---|---|---|---|---|']
    old={v['question_id']:v for v in r['A1']['cases']}
    for v in sorted(r['cases'],key=lambda x:x['question_id']):
        q=v['question_id'];t=traces['live'][q]
        lines.append(f"|{q}|{old[q]['grade']}|{v['grade']}|{','.join(v['selected_ids']) or '无'}|{'是' if t['result'].get('business_decision') else '否'}|")
    lines+=['','## 默认Worker、多轮和浏览器','', '|场景|最终状态|回答模型调用|业务门禁|边界结果|','|---|---|---:|---|---|']
    for v in r['worker']:lines.append(f"|{v['name']}|{v['status']}|{v['answer_model_calls']}|{'命中' if v.get('business_decision') else '未命中'}|{v['passed']}|")
    lines+=['', '非门禁场景最终是否答对另行观察：'+json.dumps({v['name']:v.get('semantic_control') for v in r['worker'] if 'semantic_control' in v},ensure_ascii=False)+'。一般解释若仍被原模型拒答，表示现有选证/生成问题尚存；没有通过本规则强制它回答，也不以边界放行冒充语义正确。',
            '真实多轮记录保留original question、effective query、query_resolution与Worker trace；只有历史参数确实进入有效请求，才按参数齐全处理。该专项不代表任意长会话参数持久化或记忆功能。',
            '首次Worker多轮探针发现既有改写器返回unchanged，丢失上轮明确的赛事/赛季；初始失败保留在d036-gate-live-worker.json。最终修复只为该意图从近期用户问题继承显式参数，不从助手回答取事实，遇新话题或无关主题停止；复测见d036-gate-live-worker-v2.json。历史解析自身可能调用既有改写模型，本文“0次”指命中门禁后回答模型调用为0；单轮缺参场景没有历史改写调用。',
            f"浏览器实际采集{len(r['browser'])}场景，{sum(v.get('passed',True) for v in r['browser'])}项通过；包含原有8场景及新增缺参处罚查询。核验会话隔离、历史格式化零Worker、问题改写、切换主题、实际页面补参提示和零回答调用。浏览器/Worker延迟单列，不并入Graph P95。",'',
            '## 完整性、成本与适用边界','',
            'Prompt A、原语料、索引清单、固定90题与新40题留出集字节未变。未调用留出集进行计分，答案质量沿用既有Codex原文核验及单独记录的新来源组合审核；无新增人工或裁判专家审核。Top-K、Embedding、Chunk Size没有调整。',
            '正式统计只使用完成并封存completed.json的最终90题。调试阶段的未完成短跑保留在d036-gate-live90和d036-gate-live90-v2，因补齐同场与泛称联赛边界而停止；不与最终轮次拼接或选择性抽题。单独预热、Worker、浏览器和未完成请求不并入90题Token；未完成请求的Token无法完整核算。首次旧PowerShell启动失败发生在正式推理前，后改用PowerShell7。',
            'PASS_D036_GATE仅表示本轮缺参处罚拒答规则通过指定验收，不等于整体RAG质量已达到生产门槛。当前分支本地保留，未合并或推送。', '',
            '复算：先用score_experiments.py对d036-gate-live90-final与replay90-final的score-dev/score-test、当前source_reviews.tsv计分，再运行optimization/summarize_d036_gate.py --out <输出目录>。原始逐题Prompt、通道/精排结果、模型响应、业务决定与图事件位于.runtime/phase2/d036-gate-live90-final。']
    (out/'D036_business_gate_report.md').write_bytes(('\n'.join(lines)+'\n').encode())
if __name__=='__main__':main()
