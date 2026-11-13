# 任务九缺陷复查与补交付

日期：2026-11-13。基线8553f390（PR #18、v0.9.0-hybrid-rrf），分支fix/task-09-delivery-audit。原技术/执行/任务标准不改，本报告补充原 [TASK_09_DELIVERY](TASK_09_DELIVERY.md)。

**四组交付缺陷已修复。** 原任务九门禁30/30、原专项56/56、新回归29/29、真实查询17/17通过；原RRF测试结果和负收益结论不变。

## 1. 缺陷、复现与修复

| 组 | 原问题与影响 | 修复 | 证据 |
| --- | --- | --- | --- |
| 返回对象共享 | source_lines与输入列表共享，sources还在不同方法的结果间共享；调用者标注返回结果会污染原排名或其他方法的出处 | 每个输出结果独立拷贝嵌套来源，保持数值/排名不变 | before-fixes的2个隔离反例；修复后输入及方法之间不再联动 |
| 命令预检 | query在检查已存在/无效输出路径前先加载模型并检索；空问题也先初始化索引 | 提前校验输出、问题及参数；replay也先校验输出路径 | 3个模拟引擎调用反例；修复后无效命令不构造引擎 |
| 清理异常 | Dense关闭失败时，finally中的索引保全错误会覆盖第一个清理异常 | 尝试保全检查，保留第一个异常，第二个错误只记录诊断 | 合成双故障反例，不是实际索引损坏 |
| 真实查询证据 | 完整门禁只相信17项PASS标记及少量字段，没有重算已保存的融合内容、阶段耗时、模型信息 | 标准库逐条重算四方法排名/分数/来源，验证模型/请求/耗时包含关系与Git生产源码；新1.1回执附生产提交和前后13个索引文件哈希，并与原公开索引身份核对 | 原门禁接受改错RRF分数的副本30/30；修复后同一反例被拒绝；14个旧回执篡改反例及6个新回执反例 |

6/6修复前复现和错误分数副本的30/30通过均在隔离调用/读取副本中完成，原文件没有被篡改。2b8522d保存复现，3777911修复对象、预检、清理和证据重算，429ba59补齐索引快照身份核对；原指标没有重新调参。

## 2. 验证记录

证据在 [rechecks/task9-audit-20261113](rechecks/task9-audit-20261113)。

| 项目 | 结果 | 文件 |
| --- | --- | --- |
| 修复前接口缺口 | 6/6 GAPS_REPRODUCED | before-fixes.json |
| 原完整门禁错误接受篡改回执 | GAP_REPRODUCED，旧门禁30/30 | before-forged-live-gate.json |
| 新回归，含原/新回执和非法调用 | 29/29 PASS | regressions-final.json |
| 原任务九专项，新代码检查原开发副本及新dev | 56/56 PASS | contract-current.json |
| 原任务九完整交付，新真实查询证据 | 30/30 PASS | delivery-current.json |
| 修复后真实双路4查询 | 17/17 PASS | live-smoke.json |
| 故意改错回执被完整门禁拒绝 | PASS，错误输入的门禁预期FAIL 29/30 | negative-case-proof.json、expected-invalid-live-gate.json |
| 无私有环境的公开副本复算 | 10/10 PASS | public-only-replay.json |
| 历史成果及原索引/语料/人工账本保全 | 17/17 PASS | preservation.json |

regressions-first.json为早期22/22通过；最终29项新增原索引身份和生产提交等反例。预期错误输入的29/30 FAIL是验证“坏证据必须被拒绝”，不是有效交付未通过，不能删掉该记录或当作真实运行故障。

## 3. 新运行及历史兼容

- 新dev目录retrieval/task9-audit-20261113/dev：原40题、120次融合测量；Dense、BM25、union、RRF四方法的全部质量汇总与原dev一致。RRF仍为Recall@5/10=100%、MRR=.9296875。
- 新4条真实查询沿用既定规则号、数字、术语、OOV问题，均非原测试题；只调用本机原BGE-M3与BM25，无答案生成。1.1回执记录实际生产提交3777911及完整索引前后哈希，当前严格校验器再复核，不把历史原回执改签成新版本。
- 原1.0真实查询回执按其实际生产提交ae3c3b5核对源码；原文没有前后索引快照，不能回填伪装。其排名、分数、来源、计时和模型信息同样会重新校验。
- 公开detached检出无.runtime、.venv、语料、索引，python -S下无jieba/numpy/chromadb；重算原dev、原test、新dev，并验证原/新两份真实查询回执，共10项通过。没有新发测试检索或生成新的正式测试融合报告。

新隔离拷贝会增加融合处理工作。本轮dev观测P50/P95=.500500/.561215ms（120次），只保留为功能运行记录；检查进程可能重叠，未按独立性能基准控制负载，不据此下性能因果结论。原dev/test延迟及原逐题记录不覆盖。

## 4. 交付与复验

新增标准库接口`hybrid_live.validate_live_smoke`可独立检查公开回执；完整门禁新增可选--live-report用于验收新真实查询。默认仍验证原回执及原实验，不要求历史源码哈希与当前代码硬相等，而核对实际生产Git对象与时间。

```powershell
.venv/Scripts/python.exe -B scripts/verify_task9_audit.py --live-report reports/rechecks/task9-audit-20261113/live-smoke.json --report reports/rechecks/my-task9-audit.json
.venv/Scripts/python.exe -B scripts/verify_hybrid_live.py --report reports/rechecks/my-new-live-smoke.json
.venv/Scripts/python.exe -B scripts/verify_hybrid_delivery.py --live-report reports/rechecks/my-new-live-smoke.json --report reports/rechecks/my-task9-delivery.json
python -S scripts/run_hybrid_retrieval.py replay --run-dir reports/retrieval/hybrid_rrf_b0/test --output reports/rechecks/my-saved-test-replay.json
```

脚本拒绝覆盖已有输出。verify_task9_preservation.py依赖本机复查前快照；该快照不上传，公开版本通过Git历史及清单核对，不能代替本机完整保全检查。

保留原514个文件中的历史成果、全部原报告、原15个实验对象、22个原私有索引、61份语料及人工账本。仅追加审查对象、更新当前说明/日志/实验索引/文件清单。原TECHNICAL_DESIGN、DEVELOPMENT_PLAN_AND_REPORT、TASK_09_SCOPE和TASK_09_DELIVERY均保持原字节。

原正式测试RRF仍为97.5%/100%/.9175，Recall与BM25持平、MRR低于BM25 .95；这项负收益不属于本轮要“修高”的交付缺陷。原授权与两条测试使用事件不变，未新增正式test融合或原测试题检索，不添加答案准确率/QPS/提速结论。

通过独立PR及补充标签v0.9.1-task9-audit交付；旧标签、原工程及其他已有仓库不动。全文、倒排索引、向量、依赖和账号均不上传。
