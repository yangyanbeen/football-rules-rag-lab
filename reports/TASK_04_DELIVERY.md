# 任务四交付检查与阶段报告

日期：2026-11-11。**当前尚未正式交付：人工确认0/90，测试未冻结。** 原技术文档与任务四标准保持不变；本文件不把自动检查通过写成人工标注完成。

## 原交付基线逐项核对

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
