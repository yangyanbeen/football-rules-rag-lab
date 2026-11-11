# 已测工程证据索引

本文件从任务三建立；早期任务和问答修复的历史记录以对应原报告为准。当前不声明完整RAG项目已结束，也不填未测的检索/答案成绩。

## TASK-003：稳定语料适配与数据质量控制

- 可佐证工作：为99个稳定知识单元构建统一中英文数据结构，保留来源、版本、行号、许可和翻译/审校元数据；保证旧ID映射、表格完整性及原始输入只读。
- 实测证据：18项独立校验、8项交付复核通过；16类派生坏数据在重新计算哈希后仍被拒绝；两份JSONL重复和独立目录构建字节一致。
- 数据/代码版本：data/manifests/rag_dataset_manifest.json；运行原始结果：reports/task3_dataset_validation.json、reports/task3_delivery_verification.json；逐项交付：reports/TASK_03_DELIVERY.md。
- 当前没有可用于简历的Recall、MRR、答案准确率、QPS或延迟提升数字；本阶段数据校验数不替代检索/回答成绩。

## TASK-004-PREPARE：评测候选和校验流水线（未完成人工签收）

- 已有工程证据：40开发/50测试候选、90条答案标签、90对逐题负例；稳定ID/来源/条件/拒答理由和哈希绑定；真实人工复核表与冻结门禁。
- 自动验证：结构22/22、工作流27/27、16类重签哈希坏数据全部拒绝；可由逐项回执复查。合成指标数值仅证明算术实现。
- 不能写成“已构建90条人工gold集”或“已完成任务四”；当前真实人工0/90、测试未冻结，正式交付门禁未通过。
- 回链：docs/EVAL_DATASET.md、reports/TASK_04_DELIVERY.md、reports/acceptance/task4_*、data/eval/dataset_manifest.json。真实Recall/MRR/答案质量与性能数字继续待测。

## TASK-004-OWNER-ACCEPT：负责人授权批准

- 后续用户明确授权批量通过，90题已批准并冻结，保留2条真实逐题人工记录。负责人检查10/10、专项6/6、自动工作流27/27通过。
- 该版本标记为AI起草+负责人批量签收，不能把90题写成逐题人工gold；原人工条件的未满足记录保留，未测系统性能指标仍待测。
- 回链：data/eval/owner_approval_receipt.json、reports/acceptance/task4_owner_acceptance.json、docs/TASK_04_OWNER_ACCEPTANCE.md。
