# 报告阅读说明

这里同时保留原工程历史交付和后续公开 checkout 实测。根目录下原任务报告是历史证据；当前各轮结果在 `acceptance/` 与 `evidence/`，不能混淆运行范围。

- 任务一二：TASK_01_02_DELIVERY.md、TASK_01_02_RECHECK_2026-11-11.md、task1_task2_after-task3.json。
- 问答引用修复：ANSWER_QUALITY_FIX_2026-11-11.md、answer-quality-contract-verification-2026-11-11.json、answer-quality-ui-verification-2026-11-11.json。
- 任务三：TASK_03_DELIVERY.md、task3_dataset_validation.json、task3_delivery_verification.json。
- 实验与简历证据：all_experiments_summary.csv、resume_evidence.md。
- 公开文件与原始哈希：PUBLICATION_MANIFEST.json。

原活动日志、会话记录、截图、账号凭据、数据库和完整语料不公开。因此部分原报告引用的文件只在原工程存在，不能据此声称公开仓库包含全部运行状态。原报告按字节保存；本机绝对路径是历史记录，不是新目录安装命令。

## 后续补交付的实测证据

`TASK_01_03_REDELIVERY.md` 是当前逐项交付报告；`acceptance/` 保存本轮实际重跑结果，`evidence/` 保存当前服务/启动证据、代码对应关系及明确标注为历史的 UI 三问摘要。

最初服务未运行导致的 31/32 失败也保留在 `evidence/task1_task2_before_service_restart.json`，恢复后的 32/32 在 `acceptance/task1_task2_recheck.json`。后端开发回归的16/16不作为独立测试集准确率。

`PUBLICATION_MANIFEST.json` 是首次 Git 导入快照，保留当时字节；当前文件覆盖以 `data/manifests/project_file_manifest.json` 为准，不能把历史快照当作实时清单。

## 最新缺陷关闭证据

- `acceptance/fresh_delivery.json`：独立环境、冻结数据、普通账号五份资料、新 UI 三问和服务检查，33/33。
- `evidence/fresh_ui_three_questions.json`：本轮浏览器三问摘要、时间、答案哈希及来源；完整 DOM/回答不公开。
- `evidence/fresh_database_initial.json`：新库初始化时仅有 admin、零资料；后续普通账号自行上传。
- `evidence/fresh_runtime_installation.json`：独立安装范围、真实失败原因与成功日志哈希，完整日志留本机。
- `acceptance/task3_fresh_environment.json`：新环境执行未改动的任务三 suite。
- `acceptance/fresh_answer_quality_contract.json`：新环境 19 项引用契约。

旧的 `task123_recheck_summary.json`、代码对应关系和历史 UI 文件保留原范围，当前不再用“新旧启动代码相同”作为通过条件；本轮运行覆盖层有实际修复，当前代码哈希见 fresh_delivery。

## 任务四候选与门禁

最新任务四已按原标准交付：`acceptance/task4_delivery_gate.json`为26/26 PASS、真实人工90/90；`task4_human_release_verification.json`为15/15 PASS；`evidence/task4_human_review_ui.json`为已封存只读页面证据。去姓名/备注人工凭证在`data/eval/human_review_receipt.json`。先看`TASK_04_DELIVERY.md`顶部当前结论，以下为早期阶段说明。

`TASK_04_DELIVERY.md` 保留候选准备及后续授权签收过程。`acceptance/task4_structure.json` 和 `task4_workflow_verification.json` 是自动检查通过；早期人工0/90、测试未冻结的失败已另存`task4_candidate_gate_historical.json`。不要把自动PASS或合成指标/签名当作人工评测集完成。`task4_corpus_regression.json`为原数据独立回归。

以上为原候选阶段。用户随后授权90题批量通过，当前按负责人模式批准并冻结：`task4_owner_acceptance.json`、`task4_owner_workflow_verification.json`。原逐题人工门禁仍23/26未通过，保存为 `task4_original_human_gate_after_owner_approval.json`；已有2条真实人工记录保留，批量批准不冒充逐题人工gold。
