"""Produce reviewable E7 delivery from verified live traces and source audits."""
import csv
import io
import json
import subprocess
from collections import Counter
from pathlib import Path
from score_e7_mapping import ROOT, read, sha, ratio

PRIVATE=ROOT/'.runtime/phase2/e7-scored'
EXPERIMENT=ROOT/'optimization/experiments/E7_evidence_mapping'
OUTPUT=ROOT.parent/'2026-11-18/handoff-md-x20-2/outputs'


def dump(path,value):
    path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())


def fraction(value):
    return f"{value['numerator']}/{value['denominator']}"+(f"（{100*value['value']:.2f}%）" if value['value'] is not None else '')


def grades(v):
    names={'correct':'完整正确','partial':'部分正确','incorrect':'错误','false_refusal':'误拒答','boundary_refusal':'不完整上下文拒答'}
    return '；'.join(f'{names.get(k,k)} {n}' for k,n in v['grades'].items())


def main():
    m=read(PRIVATE/'E7_mapping_metrics.json');v=read(PRIVATE/'archive_verification.json')
    assert m['decision']=='STOP_E7_CANDIDATE' and v['paired_evidence_packets_verified']==56
    OUTPUT.mkdir(exist_ok=True)
    a,b=(m['full_evidence_aggregate'][x] for x in 'AB')
    # Keep the frozen whole-point scoring intact. These paragraphs do directly
    # support part of the position answer; expose that distinction explicitly.
    partial_ids={'D017-native':{'L01-06','L14-03'}}
    sensitivity={}
    for arm in 'AB':
        rs=[r for r in m['cases'] if r['variant']==arm and r['full_evidence']]
        extra=[dict(case_id=r['case_id'],repeat=r['repeat'],chunk_id=c)
               for r in rs for c in r['unsupported_ids'] if c in partial_ids.get(r['case_id'],set())]
        original=m['full_evidence_aggregate'][arm]['citation_support']
        sensitivity[arm]=dict(historical_whole_point_support=original,extra_partial_support=extra,
            broader_direct_fragment_support=ratio(original['numerator']+len(extra),original['denominator']))
    sensitivity.update(dict(review='Post-run Codex source reading; no new human/expert adjudication.',
        reason='D017 L01-06 and L14-03 support the outside-area/arc or entry-timing fragment, but not the complete frozen location point (in field AND outside area), position behind the mark, or exact 9.15m. Their source text is not wholly unrelated or fabricated. Keep completeness and polarity errors separate from fragment-level citation relevance.',
        original_grades_changed=False,adoption_decision_changed=False))
    dump(PRIVATE/'citation_partial_sensitivity.json',sensitivity)
    buf=io.StringIO();w=csv.writer(buf,lineterminator='\n')
    w.writerow(['case','repeat','necessary_point','available','decomposed','truly_supporting_segment_mapped','mapped_support_selected','final_render_covers_point','model_requirement_indices','mapped_ids','selected_support_ids','trace_sha256'])
    for r in m['cases']:
        if r['variant']!='B':continue
        for p in r['point_mapping_audit']:
            w.writerow([r['case_id'],r['repeat'],p['necessary_point'],p['available'],p['decomposed'],p['truly_supporting_segment_mapped'],p['mapped_support_selected'],p['final_render_covers_point'],json.dumps(p['model_requirement_indices']),','.join(p['truly_supporting_mapped_ids']),','.join(p['selected_support_ids']),r['trace_sha256']])
    (PRIVATE/'E7_point_mapping_audit.csv').write_bytes(b'\xef\xbb\xbf'+buf.getvalue().encode())
    lines=[
      '# E7：显式问题要点映射与确定性选段 A/B 专项', '',
      '**结论：停止本候选，不进入全量 90 题，不合并。** 四道充分证据误拒答题恢复，但 T026 扩充版仅 1/4 完整正确，T034 扩充版 0/4，原正确 D017 退化。总指标的提升不能抵消这些预登记门槛失败。', '',
      '## 实验边界与版本', '',
      '- 运行对照：D036 修复版 `59867813e8eb16709b0be1946708d8c03a33b9cb` + 原 Prompt A。E7 推理代码快照：`0b79fc4`；从 E6 归档分支 `d4ed9fc` 建立本地 `optimization/e7-explicit-evidence-map`。',
      '- 12 道独立题、14 份上下文、每份每组 4 次，交替 AB/BA，共 112 次真实回答模型调用。另有一次预热及两组 D036 零调用检查，均不计入 112 次质量分母。',
      '- 证据来自 D036 最终封存轨迹；T026/T034 扩充版复用 E6 相同的 E5-A 归档正文。查询、证据、顺序及模型参数逐字固定。本轮没有重新执行 Embedding 或 Reranker，延迟属于固定检索结果后的回答流程。',
      '- Qwen2.5:3b、Ollama 0.40.16、CPU 8 线程、temperature=0、seed=42、num_ctx=8192、num_predict=1024，与对照一致。固定参数下仍观察到相同 Prompt 的输出差异，报告全部四次，不推断波动原因。',
      '- 40 题留出集只做既有冻结哈希核验，没有推理或评分。生产 scripts/config 与 `5986781` 字节一致，原检索、装配、来源校验和原文渲染保留。', '',
      '## 候选与机制验证', '',
      'B 使用独立 `requirements[{requirement,supporting_ids}]` Schema，单次模型调用同时拆要点和映射。程序检验本次提供的 ID，再穷举至多 3 段的组合：覆盖模型自列要点最多 → 段数最少 → 原候选顺序。只要有支持段就沿用现有部分回答协议；全为空则返回既有 insufficient_evidence。没有新增回答合成调用。', '',
      'Schema 限 1–8 项、每项 120 字；重复合法 ID 稳定去重，未知 ID、空白要点、重复字段和超限拒绝。保持最多两次回答尝试及原 Graph 来源/正文/引用校验。Schema 不含 source_conflict/version_unverified 字段，此候选将空支持统一到不足证据；上游版本门禁保留。这是候选协议的局限，不能声称已验证全部拒答契约。', '',
      '- 选择器 632 项校验通过，其中 600 例用独立位掩码穷举核对最优组合和两层平局规则。',
      '- Graph 接入 9 项通过：合法映射、非法 ID 后重试、两次失败结束、空支持拒答、部分支持回答、A 原解析保留、双组 D036 响应不消费、篡改正文前置拦截。',
      '- 112 份原始响应哈希、56 对同正文、56 份映射到选择结果的绑定，以及 112 份原文渲染绑定全部复核。', '',
      '## 逐题重复结果', '',
      '| 上下文 | A：同期对照（4 次） | B：候选（4 次） | A / B 必要要点支持引用 |',
      '| --- | --- | --- | --- |']
    for key,g in m['groups'].items():
        lines.append(f"| {key} | {grades(g['A'])} | {grades(g['B'])} | {fraction(g['A']['citation_support'])} / {fraction(g['B']['citation_support'])} |")
    lines += ['',
      'T034-native 缺少关键段，候选仅覆盖后两项（011），只算部分正确；不把它计为完整证据误拒答恢复，也不借候选自报覆盖把它记成完整正确。', '',
      '## 两个关键问题的回答', '',
      '**充分证据下误拒答能否减少：本专项可以。** D001/D002/D003/D012 四道独立题，对照各 4/4 误拒答，候选各 4/4 完整正确，共 16 次恢复；没有新增可答题误拒答。D001 正确映射绿色规则到 L01-01 后，后续程序正常回答，没有再在映射之后拒答。结构化输出与程序选段是一个整体候选，尚未消融，不能把收益单独归因于其中一部分。', '',
      '**T026 有干扰段时能否稳定选对：仍不行。** 原上下文候选 4/4 选中 L12-06 并完整正确；扩充版只有首轮如此，其后三轮仅选 L12-15，得分均为 001。L12-06 在四轮都被模型映射过，后三轮并非完全漏映射：', '',
      '| 扩充版轮次 | 模型覆盖表中的 L12-06 / L12-15 | 最终选段 | 独立要点得分 |',
      '| --- | --- | --- | --- |',
      '| 1 | L12-06 覆盖 3 项；L12-15 覆盖 2 项 | L12-06 | 111 |',
      '| 2–4 | L12-06 仅覆盖 1 项；L12-15 被错填到全部 3 项 | L12-15 | 001 |', '',
      '后三轮模型把 L12-02（手球）及 L12-15（不当行为与身体犯规边界）错误当作“技术性违例与不当行为分类”的完整依据。程序按错误关系表计算，L12-15 单段覆盖三项；添加 L12-06 不增加自报覆盖，最少段数规则排除了它。计算没有违反实验规则，错误首先发生在模型的支持判断，近义要点重复也放大了该问题。', '',
      '## 退化与映射定位', '',
      '- **T034-expanded：A 4/4 完整，B 4/4 错误。** 模型未明确拆出三项必要内容，也未映射 L07-03。首轮新增执行动作要点，导致 L14-03 覆盖自列两项；后三轮仅泛问整体计分比较，把 L14-01/L14-03 都填为支持，同分时原顺序较早的 L14-03 获选。正确证据均在 Prompt，错在拆解和支持关系。',
      '- **D017：A 4/4 完整，B 首轮完整、后三轮错误。** 后三轮把题目明确排除的主罚者和守门员列为要点，全部映射到 L14-03，未列出场内/罚球区外、罚球点后和 9.15 米，遗漏首位 L14-02。首轮虽选中正确段，还新增 L01-06。',
      '- **T014：A 完整/错误/错误/错误；B 错误/完整/完整/完整。** 首轮候选把两项都错映射到 L06-05，后续改到 L06-06。保存每次结果，仅说明这次四次观测，不能称为稳定修复。',
      '- **D021：B 最终原文 4/4 完整，但第 2–4 轮的映射文字把“任意球可能越位”反写成“不构成越位”。** L13-05 原文实际反驳该模型断言；原文渲染避免把断言直接展示为答案。证据映射不能直接用作可信解释或答案内容。',
      '- 配对正确变错误共 8 次：D017 第 2–4 轮、T034-expanded 第 1–4 轮、T014 第 1 轮。跨组新选入且不支持完整冻结要点的引用共 5 次：D017 的 L01-06 一次及 L14-03 三次、T014 的 L06-05 一次；部分支持与明确错主题须分开看。', '',
      '## 质量与开销（专项观测，非全量准确率）', '',
      '下表只统计证据完整的 13 份上下文，每组 52 次观测；包含同一题重复及 T026 两版上下文，不是 52 道独立题。T034-native 的四次另列。', '',
      '| 指标 | A | B |', '| --- | --- | --- |',
      f"| 必要要点覆盖 | {fraction(a['point_coverage'])} | {fraction(b['point_coverage'])} |",
      f"| 必要要点支持引用（历史严格口径） | {fraction(a['citation_support'])} | {fraction(b['citation_support'])} |",
      f"| 完整正确观测 | {a['grades'].get('correct',0)}/52 | {b['grades'].get('correct',0)}/52 |",
      f"| 误拒答观测 | {a['grades'].get('false_refusal',0)}/52 | {b['grades'].get('false_refusal',0)}/52 |",
      f"| 输入 / 输出 Token | {a['input_tokens']} / {a['output_tokens']} | {b['input_tokens']} / {b['output_tokens']} |",
      f"| P50 / P95 秒 | {a['latency_p50_seconds']:.3f} / {a['latency_p95_seconds']:.3f} | {b['latency_p50_seconds']:.3f} / {b['latency_p95_seconds']:.3f} |",
      f"| Schema/解析拒绝尝试、重试 | {a['rejected_attempts']}、{a['retries']} | {b['rejected_attempts']}、{b['retries']} |", '',
      '**引用口径的边界：** 历史严格指标要求一段完整支持至少一个冻结要点。D017 的 L01-06 和 L14-03 确实支持部分位置/进入时机，不能称其原文全无依据；它们不足以支持完整位置要点和其他遗漏条件。另列较宽松的“直接支持任一相关片段”敏感性统计：A 34/86，B 52/57；D017 引用变为 5/5，但完整回答仍为 1/4。本轮所有停止结论保持不变。未修改原标签或把较宽松分数混入历史主指标。', '',
      '预检记录含 Schema 大小；既有 6200 字节预算按完整 messages 计。将 UTF-8 字节全部当 Token 的保守上界曾使三个 A 上下文超过 8192，这不是实际 Token 超限：归档实际输入为 1396/1492/1608，真实新调用也均通过。实际最大 messages 6194 字节、输入 1608 Token、输出 155 Token，输入+输出+512 预留最大 2147；没有删段、上下文截断、输出长度耗尽或临时加预算。', '',
      '## 独立原文与三列审查', '',
      '对 56 次候选输出的 19 种不同映射做了 Codex 原文审查（没有新增真人或裁判专家复核）。128 次必要要点观测中，明确拆出 89 次、真支持段被映射 80 次、映射支持段入选 77 次；原文渲染最终覆盖 95 次。后一个数字更高，说明有些必要要点虽未正确映射，仍被完整原段顺带覆盖。', '',
      '模型列出的 142 次“要点—段”关系中，整项直接支持 81 次；其余含复合要点仅部分支持、主题混淆或极性错误。这一比例不等同于最终引用支持率。逐条语义判断、部分支持及负向判断理由见 mapping_source_review.json；CSV 逐项保留“是否拆出、真支持段是否映射、是否入选”三列及最终独立得分。', '',
      '## 门槛与处置', '',
      '| 登记门槛 | 结果 |', '| --- | --- |']
    for gate,passed in m['pilot_gates'].items():lines.append(f"| {gate} | {'通过' if passed else '未通过'} |")
    lines += ['',
      '正确拒答 18/18、技术完成 90/90、完整正确至少 51/72 是下一步全量验收标准，本轮因专项失败没有运行，不能声称已达到。D036 的两次真实门禁检查均为检索 0、回答模型 0；这只验证该专项门禁。', '',
      '运行代码仍是原 D036 修复版；E7 独立 Schema、选段器和研究材料仅保留在本地实验分支，未推送、合并或替换 UI/Worker。历史完整 90 题依然是 D036 修复版的 51/72 完整正确、18/18 正确拒答、90/90 技术完成；历史引用支持 72/118（61.02%），与 A1 73/117（62.39%）的差距仍未验收消除。', '',
      '下一轮已有依据检查逐段支持判定，同时保留拆解错误和极性反转的观测。当前不改 Top-K、Embedding、Chunk 或装配，也未启动第二个候选、逐段模型或任何留出集实验。', '',
      '## 复算与证据', '',
      '```powershell',
      '.runtime/task17/venv/Scripts/python.exe -B optimization/verify_e7_evidence_map.py',
      '.runtime/task17/venv/Scripts/python.exe -B optimization/verify_e7_graph.py',
      '.runtime/task17/venv/Scripts/python.exe -B optimization/verify_e7_archive.py',
      '.runtime/task17/venv/Scripts/python.exe -B optimization/review_e7_mapping_sources.py --run .runtime/phase2/e7-pilot --prepared .runtime/phase2/e7-prepared-final/prepared.json --out .runtime/phase2/e7-scored/mapping_source_review.json',
      '.runtime/task17/venv/Scripts/python.exe -B optimization/score_e7_mapping.py --run .runtime/phase2/e7-pilot --prepared .runtime/phase2/e7-prepared-final/prepared.json --review .runtime/phase2/e7-scored/mapping_source_review.json --out .runtime/phase2/e7-scored',
      '```', '',
      '首次准备目录 `.runtime/phase2/e7-prepared` 未用于推理；最终预登记为 e7-prepared-final。复跑真实调用需用新目录，禁止覆盖本次 raw/completed。', '',
      '- 预登记：`optimization/experiments/E7_evidence_mapping/manifest.json`。',
      '- 原始 112 条：`.runtime/phase2/e7-pilot/`，元数据记录推理提交及模型；completed.json 固定每份哈希。',
      '- 实际固定正文/来源：`.runtime/phase2/e7-prepared-final/prepared.json`；预算：同目录 budget_preflight.json。',
      '- 指标：`optimization/reports/E7_mapping_metrics.json`；完整明细及三列审查：同目录 E7_mapping_calls.csv / E7_point_mapping_audit.csv。',
      '- 原文阅读记录：`optimization/experiments/E7_evidence_mapping/mapping_source_review.json`；这是推理后的评分材料，不在推理输入中。',
      '- 收据及用户可读报告：本聊天 outputs/E7_mapping_receipt.json、E7_mapping_report.md。', '']
    report='\n'.join(lines)
    (ROOT/'optimization/experiments/E7_evidence_mapping.md').write_bytes(report.encode())
    (OUTPUT/'E7_mapping_report.md').write_bytes(report.encode())
    files={
        PRIVATE/'E7_mapping_metrics.json':('optimization/reports/E7_mapping_metrics.json','E7_mapping_metrics.json'),
        PRIVATE/'E7_mapping_calls.csv':('optimization/reports/E7_mapping_calls.csv','E7_mapping_calls.csv'),
        PRIVATE/'E7_point_mapping_audit.csv':('optimization/reports/E7_point_mapping_audit.csv','E7_point_mapping_audit.csv'),
        PRIVATE/'mapping_source_review.json':('optimization/experiments/E7_evidence_mapping/mapping_source_review.json','E7_mapping_source_review.json'),
        PRIVATE/'citation_partial_sensitivity.json':('optimization/reports/E7_citation_partial_sensitivity.json','E7_citation_partial_sensitivity.json'),
        PRIVATE/'archive_verification.json':('optimization/reports/E7_archive_verification.json','E7_archive_verification.json'),
        ROOT/'.runtime/phase2/e7-prepared-final/budget_preflight.json':('optimization/reports/E7_budget_preflight.json','E7_budget_preflight.json')}
    for source,(repo,dest) in files.items():
        (ROOT/repo).write_bytes(source.read_bytes());(OUTPUT/dest).write_bytes(source.read_bytes())
    (OUTPUT/'E7_fixed_contexts.json').write_bytes((ROOT/'.runtime/phase2/e7-prepared-final/prepared.json').read_bytes())
    for arm in 'AB':(OUTPUT/f'E7_prompt_{arm}.txt').write_bytes((EXPERIMENT/f'prompt_{arm}.txt').read_bytes())
    receipt=dict(experiment='E7',decision=m['decision'],inference_commit=read(ROOT/'.runtime/phase2/e7-pilot/metadata.json')['source_commit'],
        branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
        delivery_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        runtime_control_commit='59867813e8eb16709b0be1946708d8c03a33b9cb',runtime_equal_to_control=True,
        independent_questions=12,contexts=14,quality_invocations=112,raw_hash_manifest=sha(ROOT/'.runtime/phase2/e7-pilot/completed.json'),
        tests={'selector':632,'graph':9,**v},full90_executed=False,holdout_used=False,pushed=False,merged=False,
        outputs={p.name:sha(p) for p in OUTPUT.glob('E7_*') if p.name!='E7_mapping_receipt.json'})
    dump(OUTPUT/'E7_mapping_receipt.json',receipt)
    print(json.dumps(dict(decision=m['decision'],report=str(OUTPUT/'E7_mapping_report.md'),outputs=len(receipt['outputs'])),ensure_ascii=False))


if __name__=='__main__':main()
