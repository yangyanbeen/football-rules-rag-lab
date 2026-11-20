"""Publish reviewable E9 results without promoting a failed classifier."""
import json
import subprocess
from pathlib import Path
from score_e7_mapping import ROOT,read,sha

D=ROOT/'optimization/experiments/E9_classification'
SCORED=ROOT/'.runtime/phase2/e9-scored'
LIVE=ROOT/'.runtime/phase2/e9-classification-live'
OUTPUT=ROOT.parent/'2026-11-18/handoff-md-x20-2/outputs'
NAMES={'direct_support':'直接支持','partial_support':'部分支持','refutation':'反驳','unrelated':'无关','protocol_failure':'协议失败'}

def fraction(r):
    return f"{r['numerator']}/{r['denominator']}"+(f"（{100*r['value']:.2f}%）" if r['value'] is not None else '')
def dump(p,v):p.write_bytes((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())

def main():
    m=read(SCORED/'metrics.json');check=read(SCORED/'archive_verification.json');diag=read(SCORED/'decomposition_diagnostic.json')
    assert m['decision']=='STOP_PAIRWISE_VERIFIER_ROUTE' and m['selected_variant'] is None
    OUTPUT.mkdir(exist_ok=True);p,s=(m['variants'][v] for v in 'PS')
    rows=[
      '# E9：轻量支持关系分类对照', '',
      '**结论：协议已简化成功，语义能力仍未通过；按预登记停止本 Qwen2.5:3b 的逐对核验路线。** 两版各 16 次首答，实际共 32 次，无预热、无重试。没有运行 E9 的 T026 全部 60 对、后续误拒答专项、句子 ID 或批量请求实验。运行基线保留 `5986781 + Prompt A`。', '',
      '## 输入先冻结，再写候选', '',
      '- 样本与评分冻结提交 `55817a2`；候选与真实推理提交 `de0a5a9`。已核对 Git 对象：冻结时尚不存在 P/S Prompt；samples.json 与 plan.json 此后未修改。',
      '- 从 E8 原文审查表选择 16 个不同的“要点—完整段”组合：直接支持 6、部分支持 5、反驳 1、无关 4。包括 L12-06 的两种正确支持、L12-15 的两个部分支持、同一 L12-15 对另一个要点的正确支持，以及 D021 反向断言。',
      '- 样本不是 16 道独立用户题。E8 只有一个不同的反驳组合，本轮不能估计一般反驳召回率。标签继承 E8 的 Codex 原文审查，没有新增真人或裁判专家裁定，不能称专家金标。',
      '- 两版问题要点、候选正文、字段顺序、Schema 和模型配置一致。审核标签、短引及评分规则不进入模型消息；16 对输入逐字核对。', '',
      '## 单变量对照', '',
      '| 版本 | 与前一阶段的变化 |', '| --- | --- |',
      '| P 协议版 | 保留 E8 前三段语义规则，只将输出改为唯一 relation 枚举字段，删除引文、解释和相关校验。 |',
      '| S 语义版 | 与 P 使用完全相同的枚举 Schema 和输入；只改判定指令，限制为明确所问，区分问句与断言。 |', '',
      '先完整运行 P 的 16 题，再运行 S 的同一顺序。Qwen2.5:3b、Ollama 0.40.16、CPU 8 线程、temperature=0、seed=42、num_ctx=8192、num_predict=1024 均保持原配置。首答失败会计入分母，禁止因语义误判重试、修复枚举或重写问题。实际本轮没有首答失败。', '',
      '预登记通过条件：16/16 可解析、直接支持召回至少 5/6、10 个非直接支持组合不得误升、L12-06 两对均直接支持、L12-15 两个概念对均部分支持、D021 反向断言必须反驳、四类一致至少 13/16。有多组通过时按一致数、直接召回选择，完全相同优先 P；本次没有通过组。', '',
      '## 分类结果', '',
      '| 指标 | P 协议版 | S 语义版 |', '| --- | --- |',
      f"| 首答协议通过 | {fraction(p['protocol_pass'])} | {fraction(s['protocol_pass'])} |",
      f"| 四类判定一致 | {fraction(p['agreement'])} | {fraction(s['agreement'])} |",
      f"| 直接支持精确率 | {fraction(p['direct_precision'])} | {fraction(s['direct_precision'])} |",
      f"| 直接支持召回率 | {fraction(p['direct_recall'])} | {fraction(s['direct_recall'])} |",
      f"| 错误的直接支持 | {p['false_direct']} | {s['false_direct']} |",
      f"| 部分支持误升为直接支持 | {p['partial_promoted']} | {s['partial_promoted']} |",
      '| D021 反向断言 | 部分支持（错） | 部分支持（错） |', '',
      'P 的直接支持精确率 1/1 只有一次预测，不代表可靠，只是过严时几乎不输出直接支持。S 从 1/6 召回升到 3/6，但新增两个无关段的错误直接支持，未实现可信的分类改善。E8 的 60 对与本轮 16 对类别分布不同，不能用两轮整体一致率宣称准确率提升；P/S 的同批对照才可直接比较。', '',
      '## 四类混淆矩阵', '',
      '行为原文审查标签，列为模型首答；所有协议失败列均为 0。', '']
    for variant in 'PS':
        rows += [f'### {variant}', '', '| 审查标签 ＼ 模型 | 直接支持 | 部分支持 | 反驳 | 无关 |', '| --- | ---: | ---: | ---: | ---: |']
        cm=m['variants'][variant]['confusion_matrix']
        for label in ('direct_support','partial_support','refutation','unrelated'):
            rows.append('| '+NAMES[label]+' | '+' | '.join(str(cm[label][k]) for k in ('direct_support','partial_support','refutation','unrelated'))+' |')
        rows.append('')
    rows += ['## 逐对误判和关键边界', '',
      '| 样本 | 要点 / 段 | 审查 | P | S |', '| --- | --- | --- | --- | --- |']
    cases={(r['sample_id'],r['variant']):r for r in m['cases']}
    for sid in [f'S{i:02d}' for i in range(1,17)]:
        a,b=(cases[sid,v] for v in 'PS')
        rows.append(f"| {sid} | {a['requirement']} / {a['chunk_id']} | {NAMES[a['reviewed_relation']]} | {NAMES[a['model_relation']]} | {NAMES[b['model_relation']]} |")
    rows += ['',
      '- **L12-06 只恢复一对。** S01“区分技术性违例与不当行为”从部分支持改为直接支持；S02“技术性违例与身体犯规的关系”两版都判无关。不能据首例恢复宣布概念判断稳定。',
      '- **L12-15 没有被一起误升，却也未完整分清关系。** S07 两版均为部分支持；S08 的正确部分支持被 S 改判无关。S03 对“不当行为与身体犯规的关系”本应直接支持，两版却都判部分支持。这不是“该 ID 总应拒绝”的规则。',
      '- **极性仍失败。** S12 原文表示任意球可能越位，应反驳“直接接任意球不构成越位犯规”，两版都只给部分支持；任何一版都未输出反驳。这个断言没有被误升为直接支持，但四类关系本身仍然错误。',
      '- **S 新增两次错主题的直接支持。** S14 用 L16-03 的球门球资料支持界外球断言；S15 用 L01-06 的放球点/罚球弧资料回答守门员位置条件。它们在 P 中也判错为部分支持，但升级为直接支持后会进入覆盖计算，带来新的错误选段风险。',
      '- S 相对 P 有两次纠正（S01、S05）和一次原正确分类退化（S08），净增一项四类正确；S14/S15 的误升没有改变“分类是否错”的计数，却降低了直接支持精确率，必须单列。', '',
      '输出仅为枚举，无法从模型理由解释这些错误；本报告的误判归因来自对照冻结要点与原文的外部审查，不能写成模型的内在推理。', '',
      '## 成本与协议验证', '',
      '| 指标 | P | S |', '| --- | --- |',
      f"| 模型首答调用 | {p['model_calls']} | {s['model_calls']} |",
      '| 重试 / 预热 | 0 / 0 | 0 / 0 |',
      f"| 输入 / 输出 Token | {p['input_tokens']} / {p['output_tokens']} | {s['input_tokens']} / {s['output_tokens']} |",
      f"| 累计秒数 | {p['total_seconds']:.3f} | {s['total_seconds']:.3f} |",
      f"| 单对 P50 / P95 秒 | {p['latency_p50_seconds']:.3f} / {p['latency_p95_seconds']:.3f} | {s['latency_p50_seconds']:.3f} / {s['latency_p95_seconds']:.3f} |",
      f"| 第一条秒数 | {p['first_observation_seconds']:.3f} | {s['first_observation_seconds']:.3f} |", '',
      '32 次真实调用全部首答解析成功，实际每次输出 7 Token，最大 messages 2364 UTF-8 字节、输入 514 Token，未删段或调高预算。P 为先运行阶段且首条包含冷启动影响，两阶段延迟不作为严格的性能因果比较。', '',
      'E8 的自由引文协议失败在本次简化协议中没有出现，但分类未过关；不能据此恢复更复杂核验器。单对输出更轻，仍然是一对一次请求，未验证压缩请求数量。没有跑 E9 的整轮 15 对，不能把 E8 每轮约 155 秒改写成一个未经实测的新整轮延迟。', '',
      '20 项严格枚举解析和单次调用机制测试通过；冻结顺序、16 对输入、32 条原始响应、同模型配置和实际调用上限均通过档案校验。D036 走原 Graph 在检索与模型前拒答，没有调用模型或消耗 32 次分类预算。', '',
      '## T034 / D017 独立拆解文本诊断（零模型调用）', '',
      '另复核 E7 的八份旧拆解文本，对照 E8 已审核的两份中性问句重述。它们是诊断参照，不是新拆解模型输出，也不是新旧模型 A/B。维度评分看是否明确单列所问维度，不是最终答案正确率。', '',
      '| 对象 | 旧文本 | 审查后的中性重述 |', '| --- | --- | --- |',
      '| T034 四轮 | 明确保留计分比较，但三项维度仅单列计分关联，程序性质和决胜目的未拆出；首轮还加了执行规则。 | 分别查比赛中罚球点球的程序性质、点球决胜目的、罚中次数与本场正常进球数的关系，保留两种程序与本场计分范围。 |',
      '| D017 首轮 | 第一项含“除主罚者和守门员外”，却随后又把主罚者列为要点；排除条件整体不一致。 | 每个子问都保留“执行前，除主罚者和守门员外”，只查其他队员。 |',
      '| D017 后三轮 | 分别问主罚者、守门员和其他队员位置，重新加入题目排除对象，未单列区域、前后及最小距离。 | 分别查场地边界/罚球区、相对罚球点前后、最小距离，不预填正确方向或数值。 |', '',
      '这项拆解诊断可独立于核验器继续研究，但目前尚未运行新拆解算法，也未做端到端联调。E8 已说明 D017 可能靠完整原段顺带答对，答案恢复不能替代排除条件审查。', '',
      '## 门槛及处置', '',
      '| 门槛 | P | S |', '| --- | --- | --- |']
    for key in p['gates']:rows.append(f"| {key} | {'通过' if p['gates'][key] else '未通过'} | {'通过' if s['gates'][key] else '未通过'} |")
    rows += ['',
      '**执行停止规则：** 本轮没有通过的小样本候选，停止继续用该 Qwen2.5:3b、该逐对分类方式追加调参或跑全量。未启动 E9 的 T026 60 对回归、四道充分证据误拒答题及 D021 扩大测试、原文句子 ID 输出、批处理压缩、90 题全量或 40 题留出集。它们的门槛保留，不借历史结果代替本轮验收。', '',
      '默认运行仍为 D036 修复版 `5986781 + Prompt A`，检索、上下文装配、来源校验和答案渲染均未修改。分支 `optimization/e9-lightweight-classification` 仅本地保留，未推送或合并。可以将后续精力放到已定位的拆解维度与排除条件，但不能把审查参照写成已验证的新模型能力。', '',
      '## 文件和复算', '',
      '- 冻结样本/标签：`optimization/experiments/E9_classification/samples.json`；门槛及预算：同目录 plan.json。',
      '- 原始响应：`.runtime/phase2/e9-classification-live/`，completed.json 固定 32 份原始记录哈希。',
      '- 指标和逐对错误：`optimization/reports/E9_classification_metrics.json`、E9_classification_cases.csv。',
      '- 拆解文本审查：`optimization/reports/E9_decomposition_diagnostic.json`；这是外部文本审查，无新模型调用。', '', '```powershell',
      '.runtime/task17/venv/Scripts/python.exe -B optimization/verify_e9_classification.py',
      '.runtime/task17/venv/Scripts/python.exe -B optimization/score_e9_classification.py --run .runtime/phase2/e9-classification-live --out .runtime/phase2/e9-scored',
      '.runtime/task17/venv/Scripts/python.exe -B optimization/verify_e9_archive.py',
      '.runtime/task17/venv/Scripts/python.exe -B optimization/e9_decomposition_diagnostic.py',
      '```', '',
      '上述复算不调用模型。真实重跑须使用新目录，保留本次首答记录；本轮不启动新推理。', '']
    report='\n'.join(rows)
    (ROOT/'optimization/experiments/E9_classification.md').write_bytes(report.encode())
    (OUTPUT/'E9_report.md').write_bytes(report.encode())
    copies={
        SCORED/'metrics.json':('optimization/reports/E9_classification_metrics.json','E9_classification_metrics.json'),
        SCORED/'cases.csv':('optimization/reports/E9_classification_cases.csv','E9_classification_cases.csv'),
        SCORED/'archive_verification.json':('optimization/reports/E9_archive_verification.json','E9_archive_verification.json'),
        SCORED/'decomposition_diagnostic.json':('optimization/reports/E9_decomposition_diagnostic.json','E9_decomposition_diagnostic.json'),
        ROOT/'.runtime/phase2/e9-classification-prepared/budget_preflight.json':('optimization/reports/E9_budget_preflight.json','E9_budget_preflight.json')}
    for source,(repo,dest) in copies.items():
        body=(json.dumps(read(source),ensure_ascii=False,indent=2)+'\n').encode() if source.suffix=='.json' else source.read_bytes()
        (ROOT/repo).write_bytes(body);(OUTPUT/dest).write_bytes(body)
    for name in ('samples.json','plan.json','prompt_P.txt','prompt_S.txt'):(OUTPUT/('E9_'+name)).write_bytes((D/name).read_bytes())
    dump(OUTPUT/'E9_receipt.json',dict(decision=m['decision'],freeze_commit='55817a2',inference_commit=read(LIVE/'metadata.json')['source_commit'],
        delivery_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),branch='optimization/e9-lightweight-classification',
        runtime_baseline='5986781 + Prompt A',runtime_unchanged=True,distinct_pairs=16,first_answer_observations=32,
        actual_model_calls=32,retries=0,warmup=0,T026_60_executed=False,expanded_questions_executed=False,
        sentence_ids_executed=False,batching_executed=False,new_decomposition_model_run=False,decomposition_diagnostic_model_calls=0,
        full90_executed=False,holdout_used=False,merged=False,pushed=False,raw_hash_manifest=sha(LIVE/'completed.json'),
        outputs={p.name:sha(p) for p in OUTPUT.glob('E9_*') if p.name!='E9_receipt.json'}))
    print(json.dumps(dict(decision=m['decision'],report=str(OUTPUT/'E9_report.md'),outputs=10),ensure_ascii=False))

if __name__=='__main__':main()
