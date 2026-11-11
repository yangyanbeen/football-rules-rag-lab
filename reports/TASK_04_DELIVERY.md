# 任务四交付检查与阶段报告

## 最新交付：原完整标准通过（2026-11-11）

**结论：任务四已完成并交付。90/90题逐题人工核对有效，原完整门禁26/26通过。** 此结论替代下方历史阶段的“人工未齐”状态；失败报告和负责人批量批准记录保留，不回写历史结果。原TECHNICAL_DESIGN.md和DEVELOPMENT_PLAN_AND_REPORT.md未改，原人工验证器未放宽。

### 原交付基线逐项对照

| 原交付/通过条件 | 当前交付物与证据 | 结果 |
| --- | --- | --- |
| 三份规定JSONL | data/eval/retrieval_dev.jsonl（40题）、retrieval_test.jsonl（50题）、answer_eval.jsonl（90个对应标签） | 文件哈希、字段、ID、来源与一一对齐通过 |
| 标注/版本/数量/切分/冻结说明 | docs/EVAL_DATASET.md、data/eval/dataset_manifest.json、docs/TASK_04_MANUAL_REVIEW.md | 当前发布状态human_reviewed_and_test_locked |
| 可回答题人工核对支持chunk | 开发32+测试40，共72题；每条支持稳定ID及条件/例外均有匹配的四项人工通过 | 90/90全部问题确认，包含72题可回答题 |
| 不可回答题有理由 | 开发8+测试10，共18题拒答理由 | 结构及人工核对通过 |
| 覆盖及样本报告 | 两集合各覆盖规则1—17、数字/术语、条件/例外、跨段、资料外/版本题；task4_structure.json | 22/22通过；难度与类别分布见机器报告 |
| hard negative逐条理由 | hard_negatives.jsonl共90对，绑定问题、来源和理由哈希 | 每题一对，人工核对并通过 |
| 格式和指标脚本 | validate_eval_dataset.py、retrieval_metrics.py、verify_task4_workflow.py | 完整26/26、工作流27/27；16类重签哈希坏数据拒绝 |
| 锁定测试不用于调参 | 原50题内容与原锁定时间保留，used_for_parameter_selection=false、formal_test_runs=0；正式计分有配置/用途门禁 | 本轮未调用真实检索或模型，未运行正式测试计分；后续调参只用开发集 |
| 人工记录可追溯 | 本机133条事件中，90题最新有效判定全部通过；公开human_review_receipt.json仅含逐题哈希、类型、判定和时间 | 姓名、备注、四项原始记录不公开，完整日志SHA已封存 |

### 本轮修复与封存

原冻结工具拒绝给已“负责人批准并冻结”的数据补齐人工发布元数据。现新增受限转换：只有原负责人凭证有效、结构通过且90题真实人工确认全部匹配，才补齐人工发布状态、日志哈希及去身份凭证；不解除锁、不覆盖题目、不重置原锁定时间或使用历史。原正式验证器没有改动。

测试SHA-256保持 `269d49e7d65c4ad3a97b588f34093a65bbc483c7382f78b0e9cf466eaa759a62`；原锁定时间 `2026-11-11T12:31:34.505684+00:00`，人工封存时间 `2026-11-11T13:41:34.481232+00:00`。

私有日志SHA-256：`1e7161c703bce47ae7a8c3d13dafa04a09009cd8ea5311cd082e4dce309fb464`。公开人工凭证SHA-256：`69cf9f772528476c4a3da31a006edc498cfb1b411e56dfd573d033dad6460ec3`。本次没有自动生成真实人工通过；自动测试中的合成记录仅位于忽略的.tmp夹具。

### 实际验收命令与记录

```powershell
.\.venv\Scripts\python.exe scripts/validate_eval_dataset.py --phase delivery --report reports/acceptance/task4_before_human_release.json
# 首轮24/26：90题人工已通过，但缺人工发布状态与封存日志哈希；保留该失败。
.\.venv\Scripts\python.exe scripts/freeze_eval_dataset.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/recheck_task4.ps1
.\.venv\Scripts\python.exe scripts/verify_task4_human_release.py
.\.venv\Scripts\python.exe scripts/owner_approve_eval.py
.\.venv\Scripts\python.exe scripts/verify_task3_isolated.py --report reports/acceptance/task4_corpus_regression.json
```

| 证据文件（reports/acceptance/） | 实际结果 |
| --- | --- |
| task4_before_human_release.json | 修复前24/26 FAIL，缺2项元数据，人工90/90已通过 |
| task4_structure.json | 22/22 PASS |
| task4_delivery_gate.json | 26/26 PASS，人工90/90 |
| task4_workflow_verification.json | 27/27 PASS，16类坏数据全部拒绝 |
| task4_human_release_verification.json | 15/15 PASS，包含拒绝缺少/89条审核、无效负责人凭证、封存幂等、数据/锁不变、日志变化失效和公开凭证无姓名/备注 |
| task4_owner_acceptance.json | PASS_OWNER_AUTHORIZED，原批准凭证继续有效，仅为历史批准性质 |
| task4_corpus_regression.json | 原任务三主校验18/18、交付8/8、坏数据拒绝16/16，输入未变 |

审核页http://127.0.0.1:7862/已恢复只读，显示人工90/90和测试冻结。后续修订另建数据版本。代码和证据沿独立分支、小提交、PR流程保存；本轮不进入任务五，不改原有其他仓库或原本地工程。

### 本阶段边界

本次交付的是人工核对的证据检索/答案标签集及验证工作流，不是系统答案质量评测或性能优化结果。来源仍为固定Wikipedia快照与AI中文翻译，现行官方赛季/裁判专家核验状态不变。尚无正式Recall/MRR/nDCG/延迟成绩；这些按后续任务实际测量。

## 以下为负责人批准与候选阶段历史

日期：2026-11-11。**当前按负责人最新批量授权签收：90/90批准，测试已冻结。** 审阅性质是负责人委托Codex批量批准，保留2条真实逐题人工记录；不冒充90条人工gold或专家审校。

## 最新授权执行结果

用户明确要求“我授权你全部通过，赶紧操作”。已新增独立负责人批准凭证，绑定90个问题哈希及四份数据文件哈希。测试冻结哈希 `269d49e7d65c4ad3a97b588f34093a65bbc483c7382f78b0e9cf466eaa759a62`。原题目、答案标签和负例内容没有变化。

负责人检查10/10，专项检查6/6，工作流27/27通过；机器结果为 `task4_owner_acceptance.json` 和 `task4_owner_workflow_verification.json`。原人工门禁本轮仍23/26 FAIL，保存在 `task4_original_human_gate_after_owner_approval.json`；旧22/25失败也保留。本次行政签收不改变原逐题人工质量证据未齐的事实。

具体区别、使用方式及限制见 `docs/TASK_04_OWNER_ACCEPTANCE.md`。后续实验需标记 owner_approved 标签来源，不能宣称90题已经人工逐题核验。原技术文档和原人工验证器不改。

## 原候选阶段交付检查（历史保留）

| 原要求 | 已完成内容 | 当前验收状态 |
| --- | --- | --- |
| retrieval_dev.jsonl、retrieval_test.jsonl、answer_eval.jsonl | 40 开发候选、50 测试候选、90 对应答案标签 | 文件/字段/ID/来源/跨文件对应通过，标签尚待人工确认 |
| 标注准则、版本、数量、切分、冻结规则、人工复核记录 | docs/EVAL_DATASET.md、data/eval/README、dataset_manifest；本机逐题页面 | 说明与工具已备齐；真实人工记录0/90 |
| validate_eval_dataset.py | structure 与 delivery 两阶段，完整交付门禁不允许AI代签 | 结构22/22；正式门禁22/25，未通过 |
| 规则1—17、数字/术语、条件/例外、跨段、资料外/版本问题 | 两集合分别覆盖全部17条，覆盖分布已计算 | 覆盖检查通过；语义正确性需人工判定 |
| 可回答题指向人工核对支持段 | 72 道可回答候选均有稳定ID、来源/行号/正文哈希及要点 | 程序一致性通过；原规定的人工核对待完成 |
| 不可回答题有拒答理由 | 18 道资料外/版本或赛事不充分题 | 具体理由均已填写，待人工确认 |
| hard negative 逐条说明原因 | 90 对候选负例，逐题绑定来源与理由哈希 | 自动一致性通过，尚不宣称90对均获人工认可 |
| 小集验证格式与指标脚本 | 40 开发候选；独立手算夹具、坏数据与门禁检查 | 自动工作流27/27、16类重签哈希坏数据全部拒绝 |
| 锁定测试集不用于调参 | 本轮未运行真实测试预测、未改问答/检索参数；冻结与正式计分门禁已实现 | 等真实复核完成后冻结；当前不称为正式锁定测试集 |

## 已实际执行

```powershell
.\.venv\Scripts\python.exe scripts/build_eval_dataset.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/recheck_task4.ps1 -PreparationOnly
.\.venv\Scripts\python.exe scripts/verify_task3_isolated.py --report reports/acceptance/task4_corpus_regression.json
```

- `task4_structure.json`：22/22 PASS，40/50 候选；开发32可回答/8拒答，测试40可回答/10拒答；来源与冻结语料一致。
- `task4_workflow_verification.json`：27/27 PASS；含手算指标、缺预测/重复排名拒绝、16类重签哈希坏数据、人工记录真实性/失效、候选禁止冻结、冻结后禁止覆盖与测试配置门禁。
- `task4_delivery_gate.json`：**FAIL，22/25**；缺真实人工复核、测试冻结、正式发布状态。这是原要求未达的真实结果。
- `task4_corpus_regression.json`：原任务三18/18、8/8，坏数据拒绝16/16，输入不变。
- `evidence/task4_review_ui.json`：浏览器实际打开90题复核页，初始无勾选，缺CSRF的写入被403拒绝，未产生人工确认。

指标夹具里的Recall/MRR分数是虚构ID的算术期望，不能用在本系统简历或性能报告。完整冻结成功流程用显式 `.tmp` 合成记录验证；合成记录默认不能被真实门禁计作人工通过，真实签收数仍为0。

## 当前完成签收所需的一步

实际复核人打开 [本机复核页面](http://127.0.0.1:7862/)，逐题阅读支持段、要点、负例理由与来源/校核提示，选择通过或提出修改。姓名/备注只保留本机。

收到修改意见后修正 annotations.json、重建并重验；变更题的旧确认失效。实际90题均确认后，执行：

```powershell
.\.venv\Scripts\python.exe scripts/freeze_eval_dataset.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/recheck_task4.ps1
```

正式门禁通过后才能更新为“任务四已交付”、合并任务PR并进入任务五。当前只发布候选分支/草稿PR，不合并或发布完成标签。

## 基线与限制

输入代码起点4830c28a90f2d6d2b1aa31544728f283e222bed3；分支 feat/task-04-evaluation；数据版本 football-eval-0.1.0（candidate）。AI草稿来源是本 Agent 读取固定99段后的编写，没有调用本地模型生成测试预测；人工身份不冒充专家。

原 TECHNICAL_DESIGN、DEVELOPMENT_PLAN_AND_REPORT、Corpus B0 与问答参数不变。所有代码和公开评测候选只放新仓库 football-rules-rag-lab，原工程和已有其他仓库不写入。全文、完整本地复核记录与账号继续不公开。该阶段没有真实检索、答案准确率或延迟结果。
