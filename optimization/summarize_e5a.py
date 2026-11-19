import json,hashlib,subprocess,shutil,math
from pathlib import Path
R=Path(__file__).resolve().parents[1];P=R/'.runtime/phase2'
import argparse
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=R/'optimization/reports');O=p.parse_args().out;O.mkdir(parents=True,exist_ok=True)
read=lambda p:json.loads(p.read_text('utf8'))
base=read(R/'optimization/reports/phase2_E4_metrics.json');a=base['metrics']['live'];scored=[]
for split in ['dev','test']:scored+=read(P/f'e5a-{split}-metrics.json')['cases']
assert len(scored)==len({x['question_id'] for x in scored})==90
by={x['question_id']:x for x in scored};old={x['question_id']:x for x in a['cases']};traces={q:read(P/f'e5a-live90/{q}.json') for q in by};ctx=read(P/'e5a-context-audit.json')
for q,t in traces.items():
 assert len(t['result']['offered_ids'])<=5 and len(t['result']['selected_ids'])<=3 and t['result']['chat_calls']<=2
 for x in t['observations']['model_attempts']:assert len(json.dumps(x['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())<=6200
def ratio(n,d):return dict(numerator=n,denominator=d,value=n/d if d else None)
def pct(r):return f"{r['numerator']}/{r['denominator']}（{r['value']*100:.2f}%）"
def quant(xs,q):
 xs=sorted(xs);v=(len(xs)-1)*q;i=int(v);return xs[i]+(xs[math.ceil(v)]-xs[i])*(v-i)
counts={g:sum(x['grade']==g for x in scored) for g in set(x['grade'] for x in scored)}
m=dict(counts=counts,answerable_complete_accuracy=ratio(counts.get('correct',0),72),overall_accuracy=ratio(counts.get('correct',0)+counts.get('correct_refusal',0),90),correct_refusal_rate=ratio(counts.get('correct_refusal',0),18),false_refusal_rate=ratio(counts.get('false_refusal',0),72),citation_support_rate=ratio(sum(len(x['supported_citation_ids']) for x in scored),sum(len(x['selected_ids']) for x in scored)),technical_completion=ratio(sum(x['status']!='failed' for x in scored),90),requirement_coverage=ratio(sum(sum(x['point_mask']) for x in scored),sum(len(x['point_mask']) for x in scored)),calls=sum(x['chat_calls'] for x in scored),input_tokens=sum(x['input_tokens'] for x in scored),output_tokens=sum(x['output_tokens'] for x in scored),graph_p50_seconds=quant([x['seconds'] for x in scored],.5),graph_p95_seconds=quant([x['seconds'] for x in scored],.95))
rank={'correct':3,'correct_refusal':3,'partial':2,'incorrect':1,'false_refusal':1,'runtime_error':0}
regressions=[q for q in by if rank[by[q]['grade']]<rank[old[q]['grade']]];gains=[q for q in by if rank[by[q]['grade']]>rank[old[q]['grade']]]
passed=not regressions and m['citation_support_rate']['value']>=a['citation_support_rate']['value'] and by['T034']['grade']=='correct' and m['technical_completion']['numerator']==90
result=dict(experiment='E5-A only; Prompt A + E4',implementation_commit=read(P/'e5a-live90/metadata.json')['source_commit'],A1_reference_commit='790ba09',candidate_passed=passed,decision='Candidate passes recorded E5-A gates; E5-B/C not executed' if passed else 'Do not promote candidate; E5-B/C not executed',A1=a,A2=m,regressions=regressions,gains=gains,contexts=ctx,cases=scored,holdout_used=False,packing_tests=read(P/'e5a-packing-tests.json'),parser_tests={k:read(P/'e5a-parser32.json')[k] for k in ['status','passed','total']},controls25={k:read(P/'e5a-controls25.json')[k] for k in ['status','passed','total']})
result['browser']=read(P/'e5a-browser/report.json')
O.joinpath('phase2_E5_A_metrics.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
lines=['# E5-A 候选窗口实验','', '本轮仅扩大候选考察范围，未实施E5-B预算策略或E5-C覆盖感知选段。', '',f"实现提交：`{result['implementation_commit']}`。对照A1为Prompt A＋E4（790ba09/f146e46）；A0=e8b0fd6仍保留。",'',
'唯一运行代码变量：answer_eval_engine.pack 原先只遍历前max_context_chunks（5）项，现在遍历前10项，并在已装入5项时停止。仍逐次按完整JSON消息计算6200 UTF-8字节，不截正文，不改排序、模型、Prompt、重排或解析器，不读gold ID。', '',
f"离线90题核算中13题增加一段，原证据均保留为前缀；其余77题不变（含3道前置版本拒答）。T034：4段5631B→5段6069B，新增第8名L14-01，L07-03仍保留。该例第5、6、7名均不能装入剩余字节预算，第8名较短才能进入；此结果不是任何Top10扩容都必然成功的保证。",'',
'装配专项5/5、E4解析专项32/32、机制25/25通过；随后真实执行全部90题，主测试T034、D021、T032、D002、D019、D001先跑且计入同一90题。统计不重复计数22道历史错题或18道无答案题。','',
'|指标|A0 历史|A1 实测|A2：E5-A 实测|','|---|---:|---:|---:|']
for label,k in [('可答题完整正确','answerable_complete_accuracy'),('整体正确','overall_accuracy'),('正确拒答','correct_refusal_rate'),('错误拒答','false_refusal_rate'),('引用支持','citation_support_rate'),('必要要点覆盖','requirement_coverage'),('技术完成','technical_completion')]:lines.append('|'+label+'|'+pct(base['metrics']['baseline'][k])+'|'+pct(a[k])+'|'+pct(m[k])+'|')
for label,k in [('模型调用','calls'),('输入Token','input_tokens'),('输出Token','output_tokens'),('图P50秒','graph_p50_seconds'),('图P95秒','graph_p95_seconds')]:lines.append(f"|{label}|{base['metrics']['baseline'][k]}|{a[k]}|{m[k]}|")
lines+=['','预热单独保存、不计题目Token；图延迟不与浏览器交互混算。A1与A2为不同时间的一次实测，温度0/固定seed也不能排除输出漂移；输入未变题的选段变化不能直接归因于装配。语义评分采用既有审核过的原段组合或新Codex原文核验，不声称新增人工/专家审核。','',
'## 六道主回归题','', '|题号|A1|A2|A2实际选择|','|---|---|---|---|']
for q in ['T034','D021','T032','D002','D019','D001']:lines.append(f"|{q}|{old[q]['grade']}|{by[q]['grade']}|{','.join(by[q]['selected_ids']) or '无'}|")
lines+=['',f"完整程度退化题：{','.join(regressions) or '无'}；改善题：{','.join(gains) or '无'}。引用支持率是否不低于A1：{m['citation_support_rate']['value']>=a['citation_support_rate']['value']}。",'',
'## T034 实际证据链','']
t=traces['T034'];lines+=['实际offered_ids：`'+','.join(t['result']['offered_ids'])+'`。','原始输出：','```json',t['observations']['model_attempts'][0]['response']['message']['content'],'```','',by['T034']['note'],'',
'## 浏览器及退化检查','',f"浏览器采集{len(result['browser'])}/8，通过{sum(x.get('passed',True) for x in result['browser'])}/8；此为候选版本的实际线性Worker交互，与图延迟分开。",'',
'T026：A1选L12-01、L12-02、L12-15，尚支持不当行为处罚这一要点；A2上下文多了L12-03后，模型选择L12-01、L12-02、L12-03，遗漏仍在上下文中的L12-06/L12-15，必要要点覆盖由1/3变0/3。该题属于发生上下文变化的退化样本，不以其他题答对抵消。跨轮单次结果不足以断言稳定因果，但未满足本轮门禁，按失败处理。','',
'## 判定','',result['decision'],
'未通过时保留实验提交与原始结果，恢复A1的装配逻辑，不通过继续叠加B/C掩盖退化。任何已存在的D036拒答契约问题继续原标准计分，数据和Prompt不重标。E5-B/C应在独立实验中决定，本轮没有执行。', '',
'原始消息、Schema、响应、规范化结果、图节点耗时及逐题哈希归档于.runtime/phase2/e5a-live90；数据集/模型/Prompt版本在metadata.json。新40题留出集未用于模型运行或计分。']
text='\n'.join(lines).rstrip()+'\n';(O/'phase2_E5_A_candidate_window.md').write_bytes(text.encode());(R/'optimization/experiments/E5_A_candidate_window.md').write_bytes(text.encode());(R/'optimization/reports/phase2_E5_A_metrics.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps(dict(passed=passed,metrics=m,regressions=regressions,gains=gains),ensure_ascii=False))
