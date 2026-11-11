# 任务五交付报告：固定Embedding和可追溯Dense索引

日期：2026-11-11。**任务五已按原交付标准完成：完整检查24/24通过，18种无效输入/损坏索引全部拒绝。** 本报告只签收索引可用性，不发布检索质量或优化收益。

## 1. 原要求逐项对照

依据原DEVELOPMENT_PLAN_AND_REPORT.md任务五；原文及TECHNICAL_DESIGN.md保持字节不变。

| 原交付/通过条件 | 实际交付和结果 | 证据 |
| --- | --- | --- |
| 固定Embedding版本、设备、模板、维度、归一化和距离 | BGE-M3精确Ollama制品digest、1024维F16、CPU8线程；完整section_path+content_zh；float32 L2、cosine | config/dense_index.json、docs/EMBEDDING_AND_INDEX.md |
| build_dense_index.py及可重复读取/查询适配层 | 构建CLI、DenseIndex适配器、查询CLI、明确关闭自动Embedding函数 | scripts/build_dense_index.py、dense_index.py、query_dense_index.py |
| 索引、ID映射、manifest | 独立data/indexes/dense/：Chroma、NPY、records、映射、READY清单；公开仅元数据 | data/manifests/dense_index_manifest.json、dense_chunk_ids.json；实际索引本机忽略 |
| 99个原知识段及ID可核对 | 集合99条、向量99×1024、顺序映射与原99行一致；每条向量/来源metadata逐一核对；L14-04表格未拆 | task5_delivery_gate.json |
| 从空索引按文档重建 | 新.tmp目录重新调用模型编码全部99段，独立进程落盘再加载；不依赖旧应用缓存 | 重建目录和两次时间见机器回执 |
| query返回稳定ID、分数和来源metadata | 3条临时示例各用2个新进程查询，Top3 ID一致、分数容差检查、metadata与原记录完全一致 | reports/evidence/task5_dense_smoke.json |
| 记录运行时间和环境 | Intel i7-13650HX，14核/20逻辑线程，物理内存16,858,472,448字节；强制CPU8线程，Ollama报告size_vram=0 | task5_hardware.json、索引manifest与验收回执 |

## 2. 固定版本及制品

- 代码起点：8e8b93c6556943b4d08ee82f2620a5bc21ee759a；独立分支feat/task-05-dense-index。
- 上游保持Kotaemon v0.12.0 / 9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9，Python3.10.22。
- Ollama0.40.16；模型bge-m3:latest，digest `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`。该digest固定Ollama分发制品，不冒充HF revision。
- Chroma0.5.16、chroma-hnswlib0.7.6、NumPy1.26.4，未增改原锁定包。
- 原中文JSONL SHA `05dcd08126b5c71031ebe025f1a4ed1b73e00f71007b60ac0a3e0814f386a0b3`；向量序列指纹 `1f709033daf4df83416da434f2b0f4b15181273c9465780e53977a050346fa07`。
- 本机index_manifest SHA `f0c52d56e86d5b3a3d660e13a98870684b254b039ae77b2267a698e9814d0e4e`。公开副本保留该值和所有本机制品哈希。
- 本机索引制品合计5,426,386字节（不含index_manifest自身）；全部99条完整记录、向量、SQLite/HNSW文件不公开。

## 3. 实际运行和耗时

正式CPU构建总计43.811秒，其中Embedding43.062秒；从新空目录重建总计43.070秒，其中Embedding42.336秒。构建前已用单条非评测文本验证接口，模型服务处于热状态；不是冷启动测量，也不是性能提升对照。

两次均重新编码全部99段。向量最大绝对差0.0，在本次同环境下字节相同；验收仍使用atol=2e-6、rtol=1e-5，不承诺不同硬件或软件版本位级复现。Chroma集合UUID、数据库布局与时间可变，不要求两次二进制文件哈希相同。

示例仅验证API和持久化，不来自评测文件、不赋相关性分数：

| 示例 | 返回Top3稳定ID | 查询Embedding/向量搜索（秒） |
| --- | --- | --- |
| 足球场的边界标线如何判定球出界？ | L01-01、L15-02、L01-02 | 0.217 / 0.0054 |
| 裁判出示黄牌和红牌分别表示什么？ | L12-07、L12-16、L12-10 | 0.244 / 0.0056 |
| 足球比赛中，角旗附近的弧线有什么用途？ | L01-07、L17-03、L01-02 | 0.234 / 0.0066 |

示例结果含相似候选，不表示Top3都能支持答案。score=1-cosine distance，不是置信概率。以上是单次smoke耗时，不是P50/P95、QPS或正式检索质量成绩。实际距离、分数及来源URL/行号/正文哈希见smoke摘要，不上传正文。

## 4. 真实失败及修复

首轮原型完成99段编码和查询，但固定Chroma/PostHog依赖有遥测调用签名提示。采用独立DisabledTelemetry组件后，首次集成因缺Chroma要求的@override声明失败；该次没有生成READY清单，完整验收正确拒绝缺失manifest的输出。

补上声明并在编码前检查组件导入；没有升级依赖或修改site-packages/上游。两次早期输出均移入忽略.tmp目录保留，没有删除或覆盖已完成任务数据。最终代码重新从空目录构建，完整验收和所有子进程stderr检查通过。失败详情见task5_before_runtime_fix.json，原始日志留.runtime/task5/。

## 5. 完整验收与保全

```powershell
.\.venv\Scripts\python.exe scripts/build_dense_index.py
# 完整运行的本机补充参数；占位符替换为已有路径：
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/recheck_task5.ps1 -OriginalRoot <原工程目录> -OriginalSnapshot <变更前快照JSON>
```

不带补充参数也可执行recheck_task5.ps1，核心22项；本次加原工程保全2项，实际24/24。默认每次重验都会在新忽略目录重新编码99段，约需一轮构建时间；不会覆盖正式索引。

实际检查包括99个ID/完整来源对齐、1024维单位向量、完整标题/正文及表格、持久化读取、3条查询各2个新进程、一致的余弦分数、空目录真实重建、固定CPU模型，以及18种错误拒绝：

- 物理文件损坏；重签哈希后的重复ID、错误维度、零向量、伪造来源和数据库向量与NPY不符。
- 错误manifest数量、未完成构建、模型digest变化、不同配置、输出越界、覆盖非空目录。
- NaN/零Embedding、空查询、非法TopK、查询向量维度错误、布尔TopK。

原10个冻结文件、4个历史前缀、61份本机语料、178份原工程静态文件均未变；原工程无根Git。任务四manifest、人工/负责人凭证和锁定测试文件与起点提交逐字节一致。任务五不解析测试题或标签用于调参/计分，仅读其文件字节核对哈希。模型与新索引服务不改现有7860/7861/7862应用的代码或数据库。

## 6. 交付记录和后续

- 详细复现：docs/EMBEDDING_AND_INDEX.md；范围：docs/TASK_05_SCOPE.md。
- 正式机器验收：reports/acceptance/task5_delivery_gate.json，PASS24/24；18/18错误拒绝。
- 无全文示例：reports/evidence/task5_dense_smoke.json；硬件：task5_hardware.json。
- 公开索引元数据和99个ID映射：data/manifests/dense_index_manifest.json、dense_chunk_ids.json。
- 实验：docs/EXPERIMENT_LOG.md、data/manifests/experiment_manifest.json、reports/all_experiments_summary.csv。
- Git：小步提交、独立分支、PR与发布标签；只写新football-rules-rag-lab仓库，原有其他仓库保持不变。

任务六继续接入查询、证据、LLM、提示词、引用及拒答。当前任务五没有新增问答UI、BM25/RRF/Reranker/缓存，也没有测Recall/MRR/nDCG或答案准确率；正式检索基线按任务七实施。原Wikipedia/AI翻译/非专家审校和非官方赛季边界保持不变。
