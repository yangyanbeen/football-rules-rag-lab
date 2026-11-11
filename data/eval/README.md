# 任务四评测候选数据

版本 football-eval-0.1.0；当前为 AI 起草候选，不是已经人工确认的 gold test。

| 文件 | 数量/用途 |
| --- | --- |
| annotations.json | 自拟问题与拟定要点/ID/难负例理由，唯一编辑入口 |
| retrieval_dev.jsonl | 40 条开发候选：32 可回答，8 应拒答 |
| retrieval_test.jsonl | 50 条测试候选：40 可回答，10 应拒答；待人工确认后冻结 |
| answer_eval.jsonl | 与上述 90 题一一对应的答案/拒答标签 |
| hard_negatives.jsonl | 90 对相似但不足以支持目标的候选段，各附理由与来源 |
| dataset_manifest.json | 版本、哈希、数量、人工状态与测试冻结状态 |

题目、条件/例外、来源元数据和难负例理由都绑定 annotation_sha256。真实人工确认只由复核页面写入忽略的 `.runtime/eval_review/reviews.jsonl`，没有自动通过操作。全部匹配确认后，冻结工具才产生去姓名/备注的公开复核回执。

本目录只含自拟问题、标注要点、来源 ID/URL/哈希，不含 99 段正文。页面在本机读取忽略的语料展示全文。规则来源为 Wikipedia contributors；来源页与 CC BY-SA 4.0 许可链接见每条 source_references。由来源内容整理的答案要点及解释按 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) 标示为改编标注，非官方译文；代码 Apache-2.0 不能覆盖这部分来源许可。

详细字段、复核方法、指标口径与冻结规则见 `docs/EVAL_DATASET.md`。不要用候选标签计算正式准确率，也不要拿本目录测试题选择参数。
