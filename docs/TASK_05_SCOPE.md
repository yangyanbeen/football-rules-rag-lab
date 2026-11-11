# 任务五执行范围与交付基线

代码起点：8e8b93c6556943b4d08ee82f2620a5bc21ee759a；分支feat/task-05-dense-index。原TECHNICAL_DESIGN.md、DEVELOPMENT_PLAN_AND_REPORT.md及任务一至四冻结数据保持原样。

## 输入与范围

- 任务三的data/processed/rag_chunks_zh.jsonl：99个稳定知识段、原section_path/content_zh和来源元数据。
- 任务四已人工核对并锁定的开发/测试版本。任务五只检查发布资格和文件哈希，不读取测试问题做参数选择或计分。
- 固定Kotaemon v0.12.0、Python 3.10.22；使用现有Ollama BGE-M3和Chroma 0.5.16，不安装额外深度学习框架。
- 新建独立索引与查询适配层，不改应用7860/7861及其数据库，不将旧50个应用临时块或运行缓存当作99段正式索引。

## 原要求对照

| 原要求 | 计划交付 | 验收方式 |
| --- | --- | --- |
| 固定Embedding ID/revision、维度、设备、模板、归一化和距离 | config/dense_index.json、docs/EMBEDDING_AND_INDEX.md、索引manifest | 检查精确Ollama模型digest；不把Ollama制品digest冒充HF commit |
| build_dense_index.py及重复读取/查询适配层 | scripts/build_dense_index.py、dense_index.py、query_dense_index.py | 实际构建、独立进程加载和查询 |
| 索引、ID映射、manifest | data/indexes/dense/（本机忽略目录）及公开哈希清单 | 99个ID与原语料逐一对应；不上传向量、正文或索引数据库 |
| 从空索引按文档重建 | 默认拒绝覆盖非空目录，使用新的隔离路径重建 | 两次真实编码构建，检查数量、ID、配置和向量数值一致性 |
| query返回稳定ID、分数和来源metadata | 小规模非评测示例、查询JSON输出 | 元数据与原语料对齐、距离/分数可解释；不生成答案 |
| 记录环境和耗时 | reports/acceptance/task5_*、smoke摘要 | 记录构建/重建耗时及冷/热状态；不宣称正式性能收益 |

仅实现Dense索引。BM25/RRF/Reranker、缓存、父子切分、问答集成与Recall/MRR测量按后续原任务实施。验收包含输入保全、重新加载、空目录重建、错误配置/模型/哈希拒绝及公开分发检查。原交付标准不增加或降低；附加检查用于发现实现缺陷。
