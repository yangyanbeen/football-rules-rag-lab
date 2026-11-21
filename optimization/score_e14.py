"""Audit frozen producer hashes, source support, stage clocks and resource gates."""
import argparse,hashlib,json,statistics,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from task13_audit import validate_private
from answer_eval_core import read,record,canonical,digest

def save(p,v):p.write_bytes((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
def audit(run):
    corrected_path=ROOT/'optimization/reports/E14_process_memory_reconciliation.json'
    corrected={c['trace_id']:c for c in read(corrected_path)['cases']} if corrected_path.exists() else {}
    meta=read(run/'probe-metadata.json');done=read(run/'probe-completed.json');rows=[]
    for n,ref in meta['source_files'].items():
        assert digest(subprocess.check_output(['git','show',meta['source_commit']+':'+n],cwd=ROOT))==ref['sha256']
    for name,sha in done['hashes'].items():
        path=run/name;assert digest(path.read_bytes())==sha;r=read(path);v=r['result']
        if v:
            validate_private(v,v['question'],False)
            assert v['implementation']['source_commit']==meta['source_commit']
            for n,ref in v['implementation']['sources'].items():
                if n in meta['source_files']:assert ref==meta['source_files'][n]
                else:
                    assert ref==record(ROOT/n)
                    assert digest(subprocess.check_output(['git','show',meta['source_commit']+':'+n],cwd=ROOT))==ref['sha256']
        gate=r['name'].startswith('D036');fact=r['name'].startswith('fact')
        ok=bool(v and not v['error'] and (v['status']=='refused' and v['retrieval'] is None and not v['attempts'] and v.get('business_decision') if gate else
            v['status']=='answered' and v['selected_ids']==['L01-01'] if r['name']=='fact_B' else
            ((v['status']=='refused' and not v['selected_ids']) or (v['status']=='answered' and v['selected_ids']==['L01-01'])) and not v.get('fact_recovery',{}).get('applied') if r['name']=='fact_A' else v['status']=='answered' and 'L03-01' in v['selected_ids']))
        worker_events=[e for e in r['events'] if e['stage']=='worker_enter'];pid=worker_events[0]['pid'] if worker_events else None
        events={e['stage']:e for e in r['events'] if e['pid']==pid};durations={}
        for stage in ('module_import','source_environment_validation','engine_module_import','engine_construction','retrieval_import','bm25_construction','dense_construction','reranker_construction','chat_identity_validation','lazy_retrieval_construction','answer','retrieval_query','answer_model','fact_binding','result_validation','engine_close','result_write'):
            if stage+'_start' in events and stage+'_end' in events:durations[stage]=events[stage+'_end']['monotonic']-events[stage+'_start']['monotonic']
        low=r['resources'].get('low_point');prior=[e for e in r['events'] if e['pid']==pid and low and e['monotonic']<=low['monotonic']]
        row=dict(entry=r['entry'],name=r['name'],error=r['error'],semantic_ok=ok,visible=r['visible'],seconds=r['seconds'],
            before_available_GiB=r['before']['available_GiB'],after_2s_available_GiB=r['after_2s']['available_GiB'],available_min_GiB=r['resources']['available_min_GiB'],
            worker_peak_RSS_GiB=corrected.get(v['trace_id'],{}).get('sampled_main_RSS_peak_GiB',r['resources']['role_peak_rss_GiB']['worker']),role_peaks=r['resources']['role_peak_rss_GiB'],
            low_time_ns=low['wall_ns'] if low else None,low_latest_worker_stage=max(prior,key=lambda e:e['monotonic'])['stage'] if prior else None,
            low_models=[m['name'] for m in (low.get('loaded_models') or [])] if low else [],stage_seconds=durations,
            selected_ids=v['selected_ids'] if v else None,model_calls=len(v['attempts']) if v else None,
            recovery=v.get('fact_recovery') if v else None,messages_sha256=digest(canonical(v['messages'])) if v else None,
            context_sha256=digest(canonical(v['context'])) if v else None)
        rows.append(row)
    samples=[json.loads(s) for s in (run/'resources.jsonl').read_text('utf8').splitlines()]
    gaps=[b['monotonic']-a['monotonic'] for a,b in zip(samples,samples[1:])]
    return dict(run=run.relative_to(ROOT).as_posix(),producer_commit=meta['source_commit'],status=done['status'],observations=len(rows),rows=rows,
        sampling=dict(target_wait_seconds=.25,actual_median_interval_seconds=statistics.median(gaps),actual_max_gap_seconds=max(gaps),samples=len(samples)),
        gate_passed=len(rows)==10 and all(not r['error'] and r['semantic_ok'] and (r['visible'] or r['entry']=='worker') and r['seconds']<=60 and r['available_min_GiB'] is not None and r['available_min_GiB']>=1 for r in rows))

def main(a):
    baseline=audit(a.baseline.resolve());candidate=audit(a.candidate.resolve());initial=audit(a.initial.resolve()) if a.initial else None
    before={(r['entry'],r['name']):r for r in baseline['rows']};pairs=[]
    for r in candidate['rows']:
        old=before.get((r['entry'],r['name']))
        if old:pairs.append(dict(entry=r['entry'],name=r['name'],same_actual_context=old['context_sha256']==r['context_sha256'],same_messages=old['messages_sha256']==r['messages_sha256'],wall_delta_seconds=r['seconds']-old['seconds'],worker_RSS_delta_GiB=r['worker_peak_RSS_GiB']-old['worker_peak_RSS_GiB']))
    freeze=read(ROOT/'optimization/datasets/freeze_manifest.json')
    for item in freeze['files']:assert digest((ROOT/'optimization'/item['path']).read_bytes())==item['sha256']
    value=dict(baseline=baseline,candidate=candidate,initial_preserved=initial,pairs=pairs,engineering_resource_gate=candidate['gate_passed'],
        E13_revalidation_executed=False,full90_executed=False,holdout_used=False,freeze_hashes_unchanged=True,
        decision='ELIGIBLE_FOR_E13_SPECIAL' if candidate['gate_passed'] else 'STOP_BEFORE_E13_AND_FULL90',
        warning='RSS is sampled working set, not exclusive physical memory; global availability also depends on other applications. Endpoints measured2s after response. API ps1s snapshots can miss brief overlap. No causal claim from A/B global minima alone.')
    save(ROOT/'optimization/reports/E14_metrics.json',value)
    s=['# E14：正常入口的内存与初始化诊断','',
        '2026-11-21。运行模型、Prompt、检索参数及语料沿用 E13。只验证一个工程候选：门禁后延迟构造检索依赖。候选通过可信进程环境 `FOOTBALL_LAZY_RETRIEVAL=1` 启用，默认保持原行为。',
        f"对照执行版本 `{baseline['producer_commit']}`，候选执行版本 `{candidate['producer_commit']}`。分支仅保留本地。",'',
        '**结论：** '+('串行工程资源门槛通过，可进入原E13专项。' if candidate['gate_passed'] else '候选未通过全部单请求资源门槛，停止在E13完整复验及90题回归之前。D036收益与普通问答资源问题分别报告，不能将局部改善视为整体交付通过。'),'',
        '## 实测方法','',
        '默认Worker子进程及实际网页均顺序测D036、普通可答题、已有模型驻留后的D036、事实题关闭/开启E13补答。网页每次新建会话。目标等待间隔250毫秒，叠加进程采样耗时；系统可用内存及各进程RSS/private/native peak均由外部进程记录，每约1秒查询Ollama驻留模型。记录启动前、采样低点、退出后2秒，Worker内独立记录导入、环境/来源校验、依赖构造、回答及返回。外部采样依赖未安装进锁定262包Worker环境。',
        '初轮原始记录完整保留。网页fact_A的显示断言误用了“证据”关键词，实际标准拒答是“现有资料不足以可靠回答”；那次显示核验计为测试断言失败，未据此认定模型或服务超时。修正测试后完整复测对照，再测候选；未删除或改写旧结果。','',
        '## 各入口实际结果','',
        '| 版本/入口 | 请求 | 回复秒 | 启动前GiB | 最低GiB | 退出后2秒GiB | Worker峰值RSS GiB | 低点最近Worker阶段 |',
        '|---|---|---:|---:|---:|---:|---:|---|']
    for label,data in [('A',baseline),('B',candidate)]:
        for r in data['rows']:s.append(f"| {label}/{r['entry']} | {r['name']} | {r['seconds']:.2f} | {r['before_available_GiB']:.3f} | {r['available_min_GiB']:.3f} | {r['after_2s_available_GiB']:.3f} | {r['worker_peak_RSS_GiB']:.3f} | {r['low_latest_worker_stage']} |")
    s+=['','系统最低值受其他应用影响，A/B并非同一时刻，不能直接把可用内存差归为候选节省值；Worker独立RSS和阶段构造记录提供更直接的证据。RSS也不是独占物理内存，不能简单与系统可用内存相加。','',
        '## 拆分原先14.42秒的引擎外开销','',
        '| 版本 | 阶段 | 已测样本数 | 中位秒 |','|---|---|---:|---:|']
    stages=['module_import','source_environment_validation','engine_module_import','engine_construction','retrieval_import','bm25_construction','dense_construction','reranker_construction','chat_identity_validation','lazy_retrieval_construction','result_validation','engine_close','result_write']
    for label,data in [('A',baseline),('B',candidate)]:
        for stage in stages:
            v=[r['stage_seconds'][stage] for r in data['rows'] if stage in r['stage_seconds']]
            if v:s.append(f'| {label} | {stage} | {len(v)} | {statistics.median(v):.4f} |')
    s+=['','这些阶段有包含关系，不能全部求和。候选把重型构造移入通过门禁后的回答路径，不能只看引擎外时间变短就声称正常问答总耗时也减少；表中同时报告完整请求耗时。',
        '初轮D036在3B驻留时零检索/零回答调用，Worker仍峰值约2.27GiB，可用内存最低0.813GiB，低点落在重排器构造内。因此选取延迟构造候选。保留索引快照、包版本、来源和模型身份校验；就绪检查仍完整构造检索依赖。正常请求通过门禁后使用原检索器、同一提示词和同一模型，不更改装配及选证。',
        '普通请求低点及Ollama驻留快照见逐题JSON。1秒快照没有证明短暂模型重叠的能力；未确认重叠前不调整加载/卸载或单模型驻留配置。事实绑定阶段也单独计时，不能把共有的初始化峰值归因于E13。','',
        '## 验收与保留范围','',
        f"候选10次请求的完整工程门禁：{candidate['gate_passed']}。门槛为每次正常可见回复≤60秒且全程系统可用内存≥1GiB，同时核对业务行为。完整E13专项与90题是否执行分别在 `E14_metrics.json` 记录。",'40题留出集未调用、未评分，全部冻结数据哈希一致；未调整并发、未合并或推送。E13事实补答和E14延迟构造均保持默认关闭。',
        '本轮若普通可答题仍跌破资源门槛，下一轮应针对该请求的Worker峰值与重排器构造细分，不继续叠加常驻Worker等改动。驻留可能降低启动耗时但抬高空闲占用，需要独立实验。',
        '复核文件：`optimization/reports/E14_metrics.json`；逐次完整结果与阶段事件在 `.runtime/phase2/e14-baseline01/`、`e14-baseline02/`、`e14-lazy01/`。']
    text='\n'.join(s)+'\n';(ROOT/'optimization/reports/E14_runtime_assessment.md').write_bytes(text.encode())
    if a.copy:a.copy.write_bytes(text.encode())
    print(json.dumps(dict(decision=value['decision'],baseline_observations=baseline['observations'],candidate_observations=candidate['observations'],candidate_gate=candidate['gate_passed']),ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--initial',type=Path);p.add_argument('--copy',type=Path);main(p.parse_args())
