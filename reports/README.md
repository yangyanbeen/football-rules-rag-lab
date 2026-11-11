# 报告阅读说明

这里保存选定的既有交付报告和机器验收结果。它们记录原工程当时运行结果，**不是在公开 checkout 中重新跑出的成绩**。

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
