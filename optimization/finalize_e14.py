"""Archive engineering, original E13 revalidation and real90 with separate gates."""
import argparse,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,record,digest,canonical
from task13_audit import validate_private

def save(p,v):p.write_bytes((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
def main(a):
    engineering=read(ROOT/'optimization/reports/E14_metrics.json');special=read(ROOT/'optimization/reports/E14_E13_special_metrics.json');quality=read(ROOT/'optimization/reports/E14_live90_metrics.json')
    assert engineering['engineering_resource_gate'] and special['all_gates_passed'] and not quality['partial']
    special_run=ROOT/'.runtime/phase2/e14-e13-special01';run=ROOT/'.runtime/phase2/e14-live90-final';done=read(run/'worker/completed.json')
    raw=[];sources={};resources=[];verified_implementations=set()
    for folder in (special_run/'worker',special_run/'browser',run/'worker'):
        complete=read(folder/('result.json' if folder.name=='browser' else 'completed.json'))
        for name,sha in complete['hashes'].items():
            p=folder/name;assert digest(p.read_bytes())==sha;value=read(p);r=value.get('result') or value.get('trace')
            assert r is not None
            identity=digest(canonical(r['implementation']));validate_private(r,r['question'],identity not in verified_implementations)
            verified_implementations.add(identity);sources[r['trace_id']]=record(p)
            if folder==run/'worker':raw.append(value)
        resources.append(record(folder/'resources.jsonl'))
    assert len(raw)==90==done['observations'] and done['status']=='COMPLETED' and quality['actual_records']==90 and not quality['pending_reviews']
    closure_path=ROOT/'optimization/reports/E14_service_closure.json'
    closure=json.loads(closure_path.read_text('utf-8-sig'))
    assert closure['ports_closed'] and closure['owned_processes_closed'] and not closure['listeners'] and not closure['owned_processes_still_present']
    save(closure_path,closure);ports={'11434':True,'7867':True}
    freeze=read(ROOT/'optimization/datasets/freeze_manifest.json')
    for item in freeze['files']:assert digest((ROOT/'optimization'/item['path']).read_bytes())==item['sha256']
    clocks=[r['seconds'] for r in raw];mem=[r['resources']['available_min_GiB'] for r in raw]
    candidate=[r for r in quality['cases'] if r['variant']=='candidate'];counts=quality['summaries']['candidate'];shadow=quality['summaries']['shared_response_shadow']
    reconciled={c['trace_id']:c for c in read(ROOT/'optimization/reports/E14_process_memory_reconciliation.json')['cases']}
    low=sorted([dict(question_id=r['name'],seconds=r['seconds'],minimum_GiB=r['resources']['available_min_GiB'],worker_main_RSS_peak_GiB=reconciled[r['result']['trace_id']]['sampled_main_RSS_peak_GiB']) for r in raw if r['resources']['available_min_GiB']<1],key=lambda r:r['minimum_GiB'])
    added=[r for r in candidate if (r.get('recovery') or {}).get('applied')]
    runtime=dict(requests=len(raw),max_seconds=max(clocks),median_seconds=statistics.median(clocks),minimum_available_GiB=min(mem),
        below1_count=len(low),below1_cases=low,at_most60_count=sum(t<=60 for t in clocks),
        actual_answer_model_calls=sum(len(r['result']['attempts']) for r in raw),retry_questions=sum(len(r['result']['attempts'])>1 for r in raw),
        input_tokens=sum(at['prompt_eval_count'] or 0 for r in raw for at in r['result']['attempts']),output_tokens=sum(at['eval_count'] or 0 for r in raw for at in r['result']['attempts']))
    engineering.update(E13_revalidation_executed=True,E13_revalidation_passed=special['all_gates_passed'],full90_executed=True,
        full90_quality_gate=all(quality['gates'][k] for k in ('complete90','refusal18','technical90','full_above51','no_wrong_supplement')),
        full90_resource_gate=quality['gates']['requests_at_most60'] and quality['gates']['available_at_least1'],
        overall_pass=quality['overall_pass'],decision='PASS_REGISTERED_E14_GATES' if quality['overall_pass'] else 'FAIL_FULL90_ACCEPTANCE',
        full90_runtime=runtime,services_closed=ports,holdout_used=False,freeze_hashes_unchanged=True,
        experiment_default_lazy=False,experiment_default_fact_recovery=False)
    save(ROOT/'optimization/reports/E14_metrics.json',engineering)
    event_files={p.relative_to(ROOT).as_posix():record(p) for name in ('e14-baseline01','e14-baseline02','e14-lazy01','e14-e13-special01','e14-live90-final') for p in (ROOT/'.runtime/phase2'/name/'events').glob('*.jsonl')}
    save(ROOT/'optimization/reports/E14_archive_verification.json',dict(trace_records=sources,resource_files=resources,event_files=event_files,services_closed=ports,service_closure_proof=record(closure_path),
        old_E13_metrics=record(ROOT/'optimization/reports/E13_special_metrics.json'),dataset_hashes_unchanged=True,holdout_used=False,full90=record(ROOT/'optimization/reports/E14_live90_metrics.json')))
    s=['','## 原E13专项复验与90题最终结果','',
        '工程10次复验通过后，已按原E13顺序完成26次Worker A/B及7项网页测试。六个候选事实问法全对、边界零错误补答、原正确对照无退化、新增引用均直接支持。未改写原E13报告。两组均使用E14延迟构造，仅事实补答开关不同。',
        '专项资源门槛通过后，固定90题已全部通过真实默认Worker运行，正常网页服务与一个浏览器页面同时驻留。每题保留实际模型原输出、Prompt、检索结果、来源证明和资源采样。对照影子只从同一次模型响应恢复补答前状态，不是第二次独立模型运行，没有虚构影子耗时或调用成本。','',
        '| 指标 | 历史D036基线 | 本轮候选 | 同响应补答前影子 |','|---|---:|---:|---:|',
        f"| 可答题完整正确 | 51/72 | {counts['full_answerable']['numerator']}/72 | {shadow['full_answerable']['numerator']}/72 |",
        f"| 正确拒答 | 18/18 | {counts['correct_refusal']['numerator']}/18 | {shadow['correct_refusal']['numerator']}/18 |",
        f"| 技术完成 | 90/90 | {counts['technical']['numerator']}/90 | 同一次模型响应 |",
        f"| 直接支持引用 | 72/118 | {counts['citation_support']['numerator']}/{counts['citation_support']['denominator']} | {shadow['citation_support']['numerator']}/{shadow['citation_support']['denominator']} |",'',
        f"实际补答题：{', '.join(r['question_id'] for r in added) or '无'}。相对历史新增完整正确：{', '.join(quality['gains']) or '无'}；原完整正确题退化：{', '.join(quality['regressions']) or '无'}。逐题必要要点和引用审核记录见 `E14_live90_metrics.json`。沿用Codex已记录的相同问题及完整原文段集合审核；新组合另留原文复核账本，不是只按标注段ID命中计分，也不是新的专家或盲评。历史51/72来自Graph归档，本轮执行默认线性Worker；未据此宣布LangGraph路由和规划节点完成新一轮验收。",'',
        f"全量最长请求{runtime['max_seconds']:.2f}秒，中位{runtime['median_seconds']:.2f}秒；{runtime['at_most60_count']}/90次≤60秒。最低可用内存{runtime['minimum_available_GiB']:.4f}GiB，{runtime['below1_count']}/90次采样低于1GiB。实际回答模型调用{runtime['actual_answer_model_calls']}次，触发格式重试的题目{runtime['retry_questions']}道，输入/输出Token合计{runtime['input_tokens']}/{runtime['output_tokens']}。",'',
        '**最终决定：** '+('登记的质量与资源门槛均通过。' if quality['overall_pass'] else '全量验收未通过。前置短专项的资源通过不能替代较长回归；质量与资源分别判定，不能因正确率提高宣布交付成功。'),
        'D036延迟构造的局部收益已复现；普通可答请求仍构造相同的检索与重排依赖，其峰值不能声称已被解决。未叠加常驻Worker、改变模型/索引参数或删除失败样本。两项候选开关默认关闭，分支保留本地。40题留出集继续封存。',
        '采样目标等待250毫秒，实际还包含进程枚举与内存读取耗时；工程候选实测中位约0.411秒、最大约0.623秒。这里的“最低值”均为采样所见，不能排除采样间隙。1秒模型驻留快照未证明短暂重叠不存在。',
        '本轮服务与浏览器已关闭，冻结数据哈希通过复核。归档验证：`E14_archive_verification.json`。']
    path=ROOT/'optimization/reports/E14_runtime_assessment.md';base=path.read_text('utf8').split('\n## 原E13专项复验与90题最终结果')[0];text=base+'\n'+'\n'.join(s)+'\n'
    text=text.replace('**结论：** 串行工程资源门槛通过，可进入原E13专项。',f"**最终结论：** D036延迟初始化的局部收益与E13质量收益已验证；完整90题为{counts['full_answerable']['numerator']}/72完整正确、18/18正确拒答、90/90技术完成。但{runtime['below1_count']}/90次采样内存余量低于1GiB，最低{runtime['minimum_available_GiB']:.4f}GiB，全量资源验收失败，候选默认关闭。",1)
    text+='\n进程内存口径校正：原采样按PID缓存角色，Windows PID复用会使少量Worker被错误归入observer。已用实际回答阶段时间窗与Worker PID回放原始逐进程RSS，表中采用Worker主进程峰值（不含venv启动器），详见 `E14_process_memory_reconciliation.json`。原始采样未修改，系统可用内存及所有验收结论不受影响；后续采样缓存键已加入进程创建时间。\n'
    path.write_bytes(text.encode())
    if a.copy:a.copy.write_bytes(text.encode())
    print(json.dumps(dict(quality=counts,runtime=runtime,overall_pass=quality['overall_pass'],gains=quality['gains'],regressions=quality['regressions']),ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--copy',type=Path);main(p.parse_args())
