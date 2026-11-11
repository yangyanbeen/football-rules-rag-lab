# 任务四人工评测数据

版本football-eval-0.1.0；AI起草后已完成90/90逐题人工核对，原正式交付26/26通过，状态human_reviewed_and_test_locked。人工凭证human_review_receipt.json仅含题目哈希、判定与时间；完整姓名/备注日志留本机。此前owner_approval_receipt.json批量批准凭证作为历史保留，不替代人工确认。本次不是裁判专家或现行官方规则认证。

| 文件 | 数量/用途 |
| --- | --- |
| annotations.json | 自拟问题与拟定要点/ID/难负例理由，唯一编辑入口 |
| retrieval_dev.jsonl | 40 条人工核对开发题：32 可回答，8 应拒答 |
| retrieval_test.jsonl | 50 条人工核对锁定测试题：40 可回答，10 应拒答；保持原冻结内容 |
| answer_eval.jsonl | 与上述 90 题一一对应的答案/拒答标签 |
| hard_negatives.jsonl | 90 对相似但不足以支持目标的候选段，各附理由与来源 |
| dataset_manifest.json | 版本、哈希、数量、人工状态与测试冻结状态 |

题目、条件/例外、来源元数据和难负例理由都绑定 annotation_sha256。真实人工确认仍只由复核页面写入忽略的 `.runtime/eval_review/reviews.jsonl`；本次批量批准使用独立 owner_approval_receipt.json，不生成虚假的human勾选记录。人工冻结与负责人授权冻结分别保留审阅性质。

本目录只含自拟问题、标注要点、来源 ID/URL/哈希，不含 99 段正文。页面在本机读取忽略的语料展示全文。规则来源为 Wikipedia contributors；来源页与 CC BY-SA 4.0 许可链接见每条 source_references。由来源内容整理的答案要点及解释按 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) 标示为改编标注，非官方译文；代码 Apache-2.0 不能覆盖这部分来源许可。

详细字段、复核方法、指标口径与冻结规则见 `docs/EVAL_DATASET.md`。本任务没有测量系统准确率；后续正式计分须绑定固定模型/配置与测试哈希，不能拿本目录测试题选择参数。
