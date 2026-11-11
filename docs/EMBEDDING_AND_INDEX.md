# 任务五：固定Embedding与可追溯Dense索引

## 1. 配置及选择依据

权威配置为`config/dense_index.json`。原技术/任务文档、Corpus B0、任务三统一数据与任务四锁定题目均不修改。任务五单独建索引，不接管已有7860/7861应用的50个临时块或运行缓存；应用接入留任务六。

本机已有Ollama 0.40.16、BGE-M3 F16模型及Chroma 0.5.16，Python 3.10.22。复用现有模型服务和固定依赖，不新增PyTorch/SentenceTransformers安装。记录的模型制品为Ollama分发版，不宣称与HF某个commit逐字节相同。

| 项目 | 固定值 |
| --- | --- |
| 模型来源/本机名称 | BAAI/bge-m3；bge-m3:latest |
| 精确制品digest | 7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab |
| 分发/精度 | Ollama GGUF，F16，约1.16GB权重；不使用稀疏或ColBERT输出 |
| 输出维度/窗口 | 1024维 / num_ctx=8192 |
| 设备 | CPU，num_gpu=0，num_thread=8；以/api/ps的size_vram=0核对 |
| 输入与批次 | /api/embed，batch_size=4，truncate=false，keep_alive=10m |
| 文本模板 | `' / '.join(section_path) + '\n\n' + content_zh`，包含完整标题三层及原正文，不重切、不strip正文、不做Unicode规范化 |
| 查询模板 | 用户query原样，不加指令前缀；拒绝空白输入 |
| 归一化 | 转float32后逐向量L2归一化；拒绝NaN/Inf、零向量、维度或数量错误 |
| 距离/分数 | cosine distance；score=1-distance，越高越相近，不是概率 |
| 存储 | Chroma 0.5.16持久化集合football_dense_b0，显式embedding_function=None |
| 依赖 | NumPy1.26.4、chroma-hnswlib0.7.6，与现有固定环境一致 |

官方[BGE-M3模型卡](https://huggingface.co/BAAI/bge-m3)说明其1024维、8192长度以及查询不需额外指令。实际部署使用[Ollama分发版](https://ollama.com/library/bge-m3)，精确版本以本机digest为准。[Ollama Embedding接口](https://docs.ollama.com/api/embed)支持文本数组；truncate=false会在超过窗口时返回错误，避免静默丢失条件或例外。

Chroma0.5.16使用`metadata`里的`hnsw:*`配置，不套用当前新版文档的`configuration`语法。按安装版源码固定cosine、construction_ef=100、search_ef=10、M=16；num_threads=1用于固定写入/查询线程，batch_size=32和sync_threshold=32用于在99条小语料下落盘。未比较或调优这些参数，不声称HNSW优化或性能收益。索引文件属于Chroma内部持久化格式，不承诺跨版本二进制兼容。

## 2. 输入、索引与映射

输入`data/processed/rag_chunks_zh.jsonl`，固定SHA-256为`05dcd08126b5c71031ebe025f1a4ed1b73e00f71007b60ac0a3e0814f386a0b3`，99条。逐条核对原record_sha256和中文正文哈希，保留旧ID；L14-04整张表保持原样。

本机输出目录`data/indexes/dense/`：

| 文件 | 用途 |
| --- | --- |
| chroma/ | 独立Chroma SQLite与HNSW持久化文件，不与应用数据库共用 |
| embeddings.npy | 按原99行顺序保存float32、L2归一化的1024维向量，禁止pickle加载 |
| id_mapping.json | 原行位置→稳定chunk_id、record/content/检索文本哈希 |
| records.jsonl | 原99条完整中文记录，本机读取返回正文与来源metadata |
| index_manifest.json | READY状态、模型/配置/输入/实现/制品哈希、环境、批次与构建耗时 |

目录整体在Git忽略范围。公开副本仅保留`data/manifests/dense_index_manifest.json`与`dense_chunk_ids.json`等无正文元数据，实际生成情况见交付报告。向量、数据库、原正文不提交。仅克隆公开仓库仍需按PUBLIC_SETUP恢复已有许可范围内的本机语料。

适配器加载时核对配置与输入快照、全体制品哈希、99个原ID、映射、源metadata、每条集合向量与NPY一致性。禁止自动Embedding函数下载其他模型；查询使用与文档相同的固定服务、维度和归一化。返回chunk_id、rank、distance、score、content_zh及原metadata，不编造URL、不生成问答结论。

## 3. 从空目录构建与重建

在仓库根目录，先启动已有Ollama服务；不必重新下载已核对digest的模型。每批请求前后检查模型digest、Ollama版本、维度、窗口和F16；标签变化会失败，不会自动改用新模型。服务只允许无凭据的本机HTTP地址，进程内绕过失效代理。

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe scripts/build_dense_index.py
.\.venv\Scripts\python.exe scripts/query_dense_index.py --query "足球场的边界标线如何判定球出界？" --top-k 3
```

默认路径非空就拒绝覆盖，不提供--force或递归删除。需要重建时使用新目录：

```powershell
.\.venv\Scripts\python.exe scripts/build_dense_index.py --output data/indexes/dense-rebuild-001
.\.venv\Scripts\python.exe scripts/query_dense_index.py --index data/indexes/dense-rebuild-001 --query "足球场的边界标线如何判定球出界？" --top-k 3
```

路径限定为本仓库data/indexes或忽略.tmp的子目录。失败时不产生READY清单，保留失败日志和目录用于排查；修复后用新空目录，不覆盖已交付索引。重建会重新调用模型编码全部99条，不依赖旧应用缓存。

查询CLI默认省略全文，可显式加--include-content在本机读取正文；输出禁止当成未经许可的新全文分发。query_vector提供已编码向量入口，便于任务六/七复用和契约检查。

## 4. 验收、耗时与后续边界

本任务验收99条映射、持久化重载、非评测示例查询、从空目录真实重建、错误配置/模型/哈希/向量拒绝及原输入不变。具体命令、次数、环境与实测耗时记录在reports/TASK_05_DELIVERY.md、reports/acceptance/task5_*。

已实际通过核心22项；本机加原工程保全2项为24/24，18种错误全部拒绝。统一入口`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/recheck_task5.ps1`每次在新忽略目录重新编码99段，并导出无正文公开manifest/映射。可选OriginalRoot与OriginalSnapshot参数用于复核原工程；两者需一起提供。

同一进程同一路径的多个DenseIndex实例现由引用计数管理，最后一个关闭才释放系统；已验证交错关闭、重复关闭及打开集合失败的清理。本阶段仍未验证Web并发压力或QPS，应用层并发留后续接入。固定Chroma版没有公共close接口，本适配器不reset/delete集合，也不停止其他路径或尚有引用的客户端。

后续补审还增加TopK完整/唯一/对齐及距离复算检查，拒绝未固定的外部Embedding、不支持的配置语义和嵌套索引输出。原正式索引保留为原构建制品，新的reader和空目录重建有独立代码哈希。推荐统一复核`scripts/recheck_task45.ps1`，或给recheck_task5.ps1传-ReportDir以保留旧证据；详细结果见reports/TASK_04_05_SUPPLEMENT.md。

两次构建比较ID与向量数值，不要求Chroma SQLite/HNSW文件字节相同；集合UUID、创建时间和存储布局可变化。向量比较使用明确的float32容差，不预设不同硬件或软件版本位级一致。构建耗时包含接口与写盘开销，单次查询smoke耗时不是P95或性能优化结论。

任务五不解析或计分锁定测试问题，仅读其文件字节做哈希保全；不训练模型、不混BM25/RRF/Reranker/缓存、不测Recall/MRR。公开结果只证明索引可用。硬件存在GPU不代表本轮使用了GPU。
