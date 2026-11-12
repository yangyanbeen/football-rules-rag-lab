# Dense Retrieval B0（任务七）

本页为任务七当前测量口径；原技术设计和执行计划不改。完整结果与逐项验收见reports/TASK_07_DELIVERY.md，逐题原始记录在reports/retrieval/dense_b0。

## 1. 固定检索链路

固定99段Corpus B0 → 任务五原BGE-M3 F16、1024维CPU8线程Embedding → 原Chroma0.5.16 cosine索引 → Top10排名。问题使用RAG B0相同的NFKC与首尾/连续空白规范化，最多1200 UTF-8字节。候选包含全部99段，不以gold、规则号或难负例预过滤。

- 模型：bge-m3:latest，digest 7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab；Ollama0.40.16；CPU num_gpu=0。
- 原索引manifest SHA：f0c52d56e86d5b3a3d660e13a98870684b254b039ae77b2267a698e9814d0e4e；原向量fingerprint：1f709033daf4df83416da434f2b0f4b15181273c9465780e53977a050346fa07。
- 语料：corpus-b0-rag-adapter-1.0.0；SHA 05dcd08126b5c71031ebe025f1a4ed1b73e00f71007b60ac0a3e0814f386a0b3。
- 文档模板、L2归一化和Chroma HNSW参数均沿用config/dense_index.json。本轮不重编码文档、不重建索引或调参。
- 离线召回深度10，前5用于Recall@5。任务六UI仍独立查询Top5；本报告不宣称离线Top10前缀与每次独立Top5 ANN调用必然完全相同。
- 不调用Qwen答案LLM、不启用官方版本拒答路由。不可回答题仍返回相似块，检索相似度不等于答案可信度；拒答质量按任务十二评测。

## 2. 题目与指标分母

评测版本football-eval-0.1.0，90题真实人工证据标注已签收。开发40题（32可回答/8不可回答）；锁定测试50题（40/10）。标签衡量在固定社区快照中寻找标注证据的能力，不是官方现行规则认证或裁判专家审校。

| 指标 | 固定公式 |
| --- | --- |
| Recall@5/10 | 可回答题中，至少一个expected_chunk_id出现在TopK的题目数 / 可回答题数；沿用原技术设计题级定义 |
| MRR@10 | 每条可回答题首个标注支持块的倒数排名，未入前10记0；取均值 |
| all_gold_coverage@5 | 每条可回答题命中的标注支持ID数/该题支持ID数，另取均值；这是附加诊断 |
| nDCG | 无分级相关性标签，不报告 |

多支持块题只命中一个可计Recall命中，但不能称已完整覆盖回答条件。标签可能不穷尽所有等价支持块，未标注不等于事实无关。不可回答题从检索质量分母排除，延迟仍计入全部问题。

## 3. 延迟、预热和重复次数

config/dense_retrieval_b0.json固定并发1；每集合用固定非评测问题预热3次，再每题串行测量3次。**第一次排名用于质量计分**；三次全部用于延迟，不挑最好一次。各次排名和分数保存，可复核是否一致。

- normalization_seconds：NFKC及空白处理。
- query_embedding_seconds：原DenseIndex.query计时，包含本地HTTP Embedding、每次encode前后固定模型检查及向量归一化；不是裸神经网络前向耗时。
- vector_search_seconds：原向量查询、metadata/距离复算及结果排序；不是裸HNSW时间。
- total_seconds：perf_counter_ns从规范化开始至Dense查询返回。排除进程/索引加载、预热、预测写盘、指标计算和答案生成。

保存秒数原值，汇总换算毫秒；P50/P95使用排序后线性插值q*(n-1)。开发120个测量、测试150个测量；另列可回答/不可回答延迟和样本量。索引/模型加载时间、预热和整轮wall clock独立保存。单机串行样本、后台服务未专门隔离，不外推生产QPS或宣称延迟优化。

## 4. 防止标签泄漏与版本漂移

run_dense_retrieval.py先检查原26项人工门禁和公开凭证；检索循环只获得question_id和question，gold只供之后的评分和错误分析。原完整性验证器会读取开发/测试元数据做结构校验，这不等于将测试用于Embedding参数选择。

先在合成夹具和开发集完成程序调试，提交代码/配置；prepare-test绑定开发manifest/summary、54项算术与110项合同检查的报告及源码SHA、原测试锁/数据/模型/索引/代码快照。正式test必须匹配该凭证，purpose=final_report、used_for_parameter_selection=false，并使用全新运行目录。

原data/eval/dataset_manifest.json、锁定时间和其中历史formal_test_runs不回填。实际任务七使用另记test_usage.jsonl的STARTED/COMPLETED或FAILED事件。错误不能删除样本后照常报成功；逐请求requests.jsonl立即flush，保留本题后续重复失败前已经成功的调用。

## 5. 文件与复算

| 文件（每个dev/test目录） | 内容 |
| --- | --- |
| predictions.jsonl | 每题规范化query、原问题SHA、Top10 ID/rank/score/distance/来源，以及3次测量 |
| requests.jsonl | 每次成功请求立即落盘的排名/耗时/Embedding计数；无原文或向量 |
| source_map.json | 99条原ID、正文/record哈希和来源URL/行号/规则号，供独立核对 |
| summary.json | 指标、逐题评分、分组延迟和聚合错误分析 |
| error_analysis.json | 原始排名派生的错误分析；dev含可复核ID案例，test仅聚合类别 |
| run_started.json、run_manifest.json | 时序、输入/代码/模型/索引及制品SHA，启动和预热记录 |

recompute_dense_retrieval.py只用标准库和Git元数据，读取公开评测/配置/元数据与已保存预测；不需要模型、全文语料或向量库。它核对制品、源码提交与配置哈希，重新计算全部指标/延迟，拒绝覆盖已有报告。

```powershell
.\.venv\Scripts\python.exe scripts/recompute_dense_retrieval.py --run-dir reports/retrieval/dense_b0/dev --output reports/retrieval/dev-replay-new.json
.\.venv\Scripts\python.exe scripts/recompute_dense_retrieval.py --run-dir reports/retrieval/dense_b0/test --output reports/retrieval/test-replay-new.json
```

如需新增真实测量，沿用原模型/索引和新目录；先dev，再prepare-test，最后test。具体本轮运行命令见交付报告。不要直接覆盖既有目录、重写使用台账或修改测试题。

## 6. 错误分析与后续

开发集D020的标注支持L17-01未进Top10，显示同为球出界/重启类语义仍可能误召回相近块。D015虽首位命中L15-05，另一个支持L12-05只在第7位，说明题级Recall不能代表全部证据齐全；这些案例未用于改变本轮原索引或模型。

任务七建立诚实对照，结果无须达到预设百分比。任务八再在同一语料/评测版本建立BM25；后续参数选择仍只看开发集，测试用于冻结方案报告。答案/条件/引用质量与检索命中分开，禁止将Recall写成答案准确率。
