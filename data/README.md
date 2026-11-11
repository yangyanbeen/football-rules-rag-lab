# 数据层

- 冻结原数据：5 份中文 Markdown、99 条稳定知识段及英中对照，保留本地。
- 统一格式：任务三中文/英中 JSONL 各 99 条，保留本地；Schema 见 `docs/RAG_DATA_SCHEMA.md`。
- 来源：`manifests/sources.csv`，18 页 Wikipedia 条目；99 段实际引用 17 页。
- 冻结约束：`manifests/task1_task2_baseline_lock.json`。
- 任务三版本和旧 ID 映射：`manifests/rag_dataset_manifest.json`。
- 全文恢复白名单：`manifests/local_data_files.json`，只列相对路径、字节数和哈希，不含全文。

`data/raw/` 和 `data/processed/` 按原文档规则不公开。`scripts/import_local_corpus.py` 只从已有本地原工程复制白名单文件，拒绝覆盖不同数据；这些文件仍被 Git 忽略。

Wikipedia 文本及 AI 中文整理不是 IFAB 官方赛季规则。保留原来源 URL、贡献者历史链接、CC BY-SA 4.0 元数据、可见 revision 状态；历史版本正文尚未逐页独立回取核验，0 段专家审校，28 段有复核提示。本次不新增全文分发或改变数据许可。

任务四候选数据在 [eval/](eval/README.md)，只公开自拟问题、标注要点、ID/来源哈希和负例理由，不复制正文。当前为 AI 草稿，人工核对及测试冻结尚未完成；不可称为正式人工gold测试集。
