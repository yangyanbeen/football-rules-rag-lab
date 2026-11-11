# RAG B0：任务六端到端问答

本页说明任务六当前实现。原TECHNICAL_DESIGN.md和DEVELOPMENT_PLAN_AND_REPORT.md保持原样；任务六逐项验收见reports/TASK_06_DELIVERY.md。

## 1. 实际链路

```text
固定Kotaemon v0.12.0 App / ChatPage（127.0.0.1:7863）
  → 独立Python问答进程（每条请求新建，串行）
  → NFKC + 首尾/连续空白规范化
  → 任务五BGE-M3查询Embedding → 正式Chroma Dense Top5
  → 按输入预算保留完整知识块，按原空行给段落临时编号
  → 本机Qwen2.5:3b结构化生成中文text并选择passage_id
  → 校验结构/已提供段落ID，恢复原文和原始来源metadata
  → 显示回答引用、完整知识块、许可、版本与审校状态
```

资料不足、无效输出、模型/Embedding服务失败、问答子进程失败时均拒答，不附确定答案或虚构引用。历史对话保留在独立UI数据库，但不作为新问题的事实证据；本阶段不支持依赖上文指代的追问。

## 2. 固定配置

| 项目 | B0配置 |
| --- | --- |
| 上游 | Kotaemon v0.12.0，commit 9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9；原checkout不改 |
| 语料 | 5份AI中文整理、99个原ID；corpus-b0-rag-adapter-1.0.0 |
| Embedding | 复用任务五config/dense_index.json：bge-m3:latest、F16、1024维、L2、CPU8线程 |
| 向量索引 | data/indexes/dense，Chroma0.5.16 cosine，manifest SHA f0c52d56e86d5b3a3d660e13a98870684b254b039ae77b2267a698e9814d0e4e |
| Top-K | 固定5；score=1-distance，不是答案置信概率 |
| 生成模型 | qwen2.5:3b，Q4_K_M，digest 357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b |
| 推理参数 | Ollama0.40.16；CPU8线程、num_gpu=0、temperature=0、seed=42、num_ctx=8192、num_predict=1024 |
| 提示词 | config/rag_b0_system.txt；grounded-generation-v4，确切SHA见每条trace |
| 配置 | config/rag_b0.json；每条trace记录配置SHA、提示词SHA和索引manifest SHA |
| 接口 | http://127.0.0.1:11434/api/chat；非流式、结构化JSON，无付费Key |

Ollama官方说明支持JSON Schema形式的format和stream=false；本实现另行校验done_reason、模型digest及实际token计数。[Chat API](https://docs.ollama.com/api/chat)、[结构化输出](https://docs.ollama.com/capabilities/structured-outputs)。

## 3. 证据预算和引用

问题规范化后最多1200 UTF-8字节。messages连同响应schema的序列化输入预算6200 UTF-8字节，另留512模板token和1024输出token；对当前Qwen字节BPE采取保守上界，并检查实际prompt_eval_count。6200字节不等于6200个汉字或token。

按检索排名逐块尝试，超预算的整块不传给模型，继续检查后续候选；不截断块内条件、表格或校核提示。完整Top5、实际送入的context、精确messages/schema与字节数分别记录，能看见预算排除了哪些结果。本阶段没有压缩/重切Corpus B0或修改Task5索引。

passage_id形如L01-03:p1，只是本次原块按双换行划分的原段地址，不是新chunk版本。模型只返回text和已有passage_id；程序从该地址恢复chunk_id及完整support_quote。这样避免让模型重新抄写来源时改字。引用示例形式为`[L01-03 · 第1条 · L187–L189](原source_url)`；URL、规则号和行号均取原metadata。

L起止行来自采集时的带行号网页快照，不是网页锚点或规则书页码。现有revision ID对应正文未独立回取核验，引用链接不冒充已验证的历史版本链接。

结构校验能证明引用段落实际被提供、摘录逐字来自原文；不能证明生成text的每个结论必被该段语义蕴含。当前保留完整证据以便检查，正式答案质量、条件遗漏和拒答误判在任务十二评测，本任务不声明准确率。模型仍可能误拒答或错误选段。

## 4. 启动和试用

前提沿用PUBLIC_SETUP.md及EMBEDDING_AND_INDEX.md：独立.venv和锁定包已安装、本机Ollama运行、两个精确模型及99段正式索引存在。仅克隆公开仓库不会得到私有语料或实际向量索引。

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe scripts/query_rag_b0.py --check
powershell -NoProfile -ExecutionPolicy Bypass -File frontend/start_rag_b0.ps1
# 打开 http://127.0.0.1:7863/
# 运行终端按Ctrl+C停止这一个实例；旧7860/7861/7862保留。
```

命令行单问及完整本机记录：

```powershell
.\.venv\Scripts\python.exe scripts/query_rag_b0.py --query "球门两根门柱之间的距离和横梁高度各是多少？" --trace .runtime/rag-b0/my-question.json
```

已有trace不覆盖。若7863已在运行，直接访问；端口被占用时不要关闭不属于本任务的进程。回滚此任务使用该PR的git revert；独立UI数据库留在忽略目录，不覆盖原应用数据库。

## 5. UI与进程隔离

UI确实使用固定上游App/ChatPage，通过新增BaseReasoning和只读BaseIndex适配层接入。只读选择器满足上游事件要求，但不创建第二份Chroma集合、不提供上传/网页采集/在线搜索。页面只接收完整校验后的答案，不提前展示未校验生成token。会话命名使用首问，不额外调用模型；资料编辑、推荐追问和思维导图不参与本链路。

本机实际发现：同进程导入完整Kotaemon后，DenseIndex初始化读取Chroma/HNSW向量触发Windows access violation，详见本机import-start.log。最终通过子进程加载索引和问答；无需改变依赖、上游或索引。每条问题启动一个子进程，存在额外耗时，不宣称吞吐优化。UI进程串行调度，不能据此推导生产QPS。

独立应用状态：.runtime/rag-b0/kotaemon/。该本机固定知识库入口不启用账号管理；原应用账号、私人文件与数据库保持原状。模型和检索调用只指向本机；上游可选前端资产仍沿用其CDN，不宣称整站已完全离线。

## 6. 日志、验收和分发

- reports/rag_b0_smoke.jsonl：规定交付路径，至少3条可回答+1条资料外；包含问题、Top5、实际证据、LLM原响应、恢复引用、拒答原因、耗时与trace ID。
- .runtime/rag-b0/ui-events.jsonl：真实页面请求完整日志；workers/保存逐次子进程trace。
- .runtime/rag-b0/ui-captures.jsonl：真实页面DOM采集，绑定trace ID和最后回答；不拿后端调用冒充页面操作。
- 公开reports/evidence/rag_b0_smoke_manifest.json和rag_b0_ui_manifest.json：只公开状态、ID、来源及哈希/计数，不包含完整答案或规则正文。
- 公开reports/acceptance/task6_delivery_gate.json：合同/坏输出、真实smoke/UI、冻结数据保全的机器验收；失败及重跑用新文件保存。

完整问答记录可能包含原语料全文，沿用既有reports/*.jsonl和.runtime忽略规则，仅在本机交付；公开代码不上传模型响应、原文、向量或账号。哈希回执不能让缺少本机资料的人独立阅读私有证据，公开复核与完整本机验收的范围不同。

```powershell
# 首次 smoke 使用原规定路径；脚本拒绝覆盖既有结果。
.\.venv\Scripts\python.exe scripts/smoke_rag_b0.py
# 重验时指定新的忽略输出和新的公开摘要路径：
.\.venv\Scripts\python.exe scripts/smoke_rag_b0.py --output .runtime/rag-b0/my-recheck.jsonl --summary reports/evidence/my-recheck.json
# 完整交付检查需已有本机smoke和真实UI采集；报告路径必须新建：
.\.venv\Scripts\python.exe scripts/verify_rag_b0.py --report reports/acceptance/my-task6-recheck.json
```

原Task4开发/测试题和标签不用于本任务参数选择或正式计分。没有新增BM25/RRF、Reranker、缓存、父子切分，也没有Recall/MRR/nDCG、P95/QPS或效果提升数字。
