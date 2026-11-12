# 任务七交付：Dense Retrieval B0（2026-11-12）

## 1. 交付结论

已按原任务七完成固定Dense检索基线。基于原99段语料、任务四开发/锁定测试和任务五原索引，交付逐题预测、汇总、模型/数据/代码manifest、错误分析及独立复算。原文要求没有预设召回目标；以下均为实际运行结果。

| 集合 | 总题 / 可回答 / 不可回答 | Recall@5 | Recall@10 | MRR@10 | 标注支持集合覆盖@5 |
| --- | --- | --- | --- | --- | --- |
| 开发 | 40 / 32 / 8 | 31/32 = 96.875% | 31/32 = 96.875% | 0.89062500 | 95.3125% |
| 锁定测试 | 50 / 40 / 10 | 38/40 = 95% | 38/40 = 95% | 0.86041667 | 93.125% |

Recall沿原技术定义，分母为可回答题，至少一个标注支持块命中即计1。MRR截断前10；支持集合覆盖为单独诊断，不改变原Recall。无分级相关标签不报nDCG。不可回答题仍做检索并计延迟，其答案拒答留任务十二。

## 2. 实测延迟

单位毫秒，以下为P50 / P95；各阶段的分位数不能直接相加。开发120次、测试150次测量，包含全部可回答/不可回答题；每题三次，质量只用第一次排名，延迟不挑选。

| 阶段 | 开发 P50 / P95 | 测试 P50 / P95 |
| --- | --- | --- |
| 问题规范化 | 0.0174 / 0.0250 | 0.0181 / 0.0248 |
| Embedding与身份校验 | 258.8287 / 307.6231 | 265.6553 / 307.3261 |
| 向量检索与结果校验 | 5.3602 / 7.5897 | 5.2696 / 7.5133 |
| 总检索 | 264.6760 / 312.1155 | 270.1763 / 312.8212 |

每集合以固定非评测问题预热3次、并发1。P50/P95为排序后q*(n-1)线性插值，原秒数全部保存。Embedding阶段包含本机HTTP与固定模型检查；向量阶段包含原metadata/距离复算及排序。总计时从NFKC/空白处理到Dense返回，排除启动、预热、写盘、打分及LLM。启动/整轮wall clock另存manifest。

本机环境：Python 3.10.22，20个逻辑CPU；Intel64 Family 6 Model 183 Stepping 1, GenuineIntel。BGE-M3固定CPU8线程；Chroma0.5.16、NumPy1.26.4、chroma-hnswlib0.7.6。后台应用未专门隔离，以上是这次串行暖态样本，不能当生产吞吐或优化收益。

## 3. 固定基线与运行时序

- 起点main：59e3ba042411be4400101a630397e5c298e26cee；分支feat/task-07-dense-retrieval-b0。
- 语料corpus-b0-rag-adapter-1.0.0，99段；SHA 05dcd08126b5c71031ebe025f1a4ed1b73e00f71007b60ac0a3e0814f386a0b3。
- 原正式索引manifest SHA f0c52d56e86d5b3a3d660e13a98870684b254b039ae77b2267a698e9814d0e4e；向量fingerprint 1f709033daf4df83416da434f2b0f4b15181273c9465780e53977a050346fa07。
- BGE-M3 F16、1024维、Ollama0.40.16，digest 7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab；每次encode前后校验，/api/ps确认CPU size_vram=0。原文档向量不重建。
- 评测football-eval-0.1.0；测试SHA 269d49e7d65c4ad3a97b588f34093a65bbc483c7382f78b0e9cf466eaa759a62，原锁定时间、原formal_test_runs字段及人审回执不改写。
- 开发源码提交：79513e86e7df19248920dbc406faabb16ae1d3b3；开发完成：2026-11-12T09:30:38.403314+00:00。
- 源码/配置冻结提交：fb8e9d824b7fd6addd857823c99846441487145d；凭证生成：2026-11-12T09:39:33.982727+00:00。
- 正式测试开始：2026-11-12T09:39:49.467088+00:00，完成：2026-11-12T09:40:32.973285+00:00；代码提交与凭证一致。
- 测量配置config/dense_retrieval_b0.json，SHA 1317815c1c1025d42561a1e0614ddbed4264a7d2fdfc484536ddc9359bb5d5eb。Top10离线排名前5计算Recall@5，在线UI仍为原Top5；不宣称两种ANN调用必然逐项相同。

本轮只有一次正式test运行（50题各3次重复，是预注册策略）；test_usage.jsonl保存STARTED/COMPLETED两条事件，绑定凭证、配置/锁集/代码和完成manifest。仅程序在已授权final_report流程中读取锁题与标注，未用测试结果修改模型、索引或参数。检索循环只接收question_id/question，gold不传入Embedding或排名器。原完整性验证会读取锁集结构/哈希，不等于测试调参。

## 4. 原交付要求逐项对应

| 原任务七要求 | 已交付 | 核验依据 |
| --- | --- | --- |
| 逐题预测 | [dev/predictions.jsonl](retrieval/dense_b0/dev/predictions.jsonl)、[test/predictions.jsonl](retrieval/dense_b0/test/predictions.jsonl) | 每题Top10、稳定ID/rank/score/distance/原来源，3次排名/计时及问题SHA |
| 汇总及可回答/不可回答样本数 | [dev/summary.json](retrieval/dense_b0/dev/summary.json)、[test/summary.json](retrieval/dense_b0/test/summary.json) | 40=32+8、50=40+10，指标分母与270次延迟可复算 |
| 数据/模型manifest | dev/test的run_manifest.json、source_map.json、run_started.json；[运行凭证](retrieval/dense_b0/test_authorization.json) | 原数据/模型/索引/配置/源码提交及SHA、CPU/环境和运行时序 |
| 错误分析 | dev/test的error_analysis.json | 来自逐题原排名；dev含ID案例，test为聚合类别，标签不保证穷尽相关性 |
| 最终口径 | [DENSE_RETRIEVAL](../docs/DENSE_RETRIEVAL.md)、[任务范围](../docs/TASK_07_SCOPE.md) | 题级any-hit Recall、MRR@10、单独多gold覆盖、预热/次数/计时/分位数 |
| 可复算且只在开发调试 | recompute_dense_retrieval.py及公开独立复算凭证 | 开发完成后冻结，再一次test；模型/语料/向量缺失仍能复算已保存预测 |

requests.jsonl每次成功立即flush，保留后续重复失败前已完成请求。真实预测只公开问题、ID/来源/哈希/分数和计时，不包含规则正文、向量、答案或账号。

## 5. 实际验收与开发期失败

证据目录：[acceptance](retrieval/dense_b0/acceptance)。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 原任务七本机交付门禁 | 43/43 PASS | task7_delivery_gate.json；含独立复算、时序、模型/数据与原资产保全 |
| 虚构ID指标手算 | 54/54 PASS | arithmetic-final.json；原retrieval_metrics.py未改 |
| 严格schema/计时合同 | 110/110 PASS | contract-final.json；无模型请求 |
| 开发数据副本复算破坏/CLI门禁 | 113/113 PASS | replay-contract.json；51个破坏案例、每个干净副本先通过 |
| dev/test独立复算 | 全部一致 | development-recomputed.json、test-recomputed.json |
| 无语料/模型/索引、禁第三方Python包的公开副本复算 | dev/test全部一致 | public-only-replay.json；真实独立Git worktree，python -S，numpy/chromadb不可导入 |
| 前序任务六与上一轮边界检查 | 62/62、58/58 PASS | previous-task6.json、previous-boundaries/regressions.json；重放历史证据，不冒称新UI |

早期合同检查100/101 FAIL：Embedding observation可以混入content_zh额外字段。实际只在虚构夹具复现，修复为完整字段白名单并检查类型/有限计数，原失败保留contract-before-fix.json。另保留arithmetic.json初始回执；正式凭证使用带producer SHA的arithmetic-final.json。未在实际预测公开过原文。

54/110/113是程序检查数，不是实测问答样本。公开复算证明已保存排名和算术一致性；本机43项额外核对私有原语料/索引/人审与变更前哈希。没有把这些自动检查记成新人工审批。

## 6. 错误与能力边界

- 开发1/32题未命中Top10；D020标注L17-01未进候选，说明球出界/重启相关语义仍可能混淆。D015首位命中L15-05，但另一标注支持L12-05位于第7，题级命中不能代表全部条件已入上下文。
- 测试2/40题未命中Top10；4题Top5没有覆盖全部标注支持ID。5条多支持题中3条Top5覆盖全部标注ID。由5增至10未新增题级命中，本轮没有据此调整检索配置。
- 原99段、90条自建领域题规模有限；标注可能不穷尽等价支持，Wikipedia AI中文整理、非官方版本/未裁判专家审校边界保留。检索命中不代表生成答案正确、条件/例外完整或已正确拒答。
- 当前是Dense基线，尚无混合检索/重排/缓存优化提升；任务八以后按原计划逐项对照。原简历示例的61%→80%等目标数字未作为实测写入。

## 7. 复现命令

本轮真实执行如下。目录已存在，新增实验应换新版本/目录，不能覆盖或重写使用台账。

```powershell
.\.venv\Scripts\python.exe scripts/verify_dense_metric_arithmetic.py --report reports/retrieval/dense_b0/acceptance/arithmetic-final.json
.\.venv\Scripts\python.exe scripts/verify_dense_retrieval_contract.py --report reports/retrieval/dense_b0/acceptance/contract-final.json
.\.venv\Scripts\python.exe scripts/run_dense_retrieval.py --mode dev --run-dir reports/retrieval/dense_b0/dev
.\.venv\Scripts\python.exe scripts/verify_dense_retrieval_replay.py --report reports/retrieval/dense_b0/acceptance/replay-contract.json
# 提交开发证据/代码后：
.\.venv\Scripts\python.exe scripts/run_dense_retrieval.py --mode prepare-test --run-dir reports/retrieval/dense_b0/test --authorization reports/retrieval/dense_b0/test_authorization.json --development-run reports/retrieval/dense_b0/dev --arithmetic-report reports/retrieval/dense_b0/acceptance/arithmetic-final.json --contract-report reports/retrieval/dense_b0/acceptance/contract-final.json
.\.venv\Scripts\python.exe scripts/run_dense_retrieval.py --mode test --run-dir reports/retrieval/dense_b0/test --authorization reports/retrieval/dense_b0/test_authorization.json
.\.venv\Scripts\python.exe scripts/verify_task7_delivery.py --report reports/retrieval/dense_b0/acceptance/task7_delivery_gate.json
# 独立公开副本：
python -S scripts/recompute_dense_retrieval.py --run-dir reports/retrieval/dense_b0/test --output reports/retrieval/my-new-test-replay.json
```

## 8. 保全、归档与Git交付

原TECHNICAL_DESIGN、DEVELOPMENT_PLAN_AND_REPORT、UPSTREAM_VERSION和原验证器字节不变；10冻结文件/4历史前缀、61语料、原正式索引全部文件、真实人工日志、旧评测/报告、原工程178静态文件保持原哈希。原工程无根Git；旧应用、生成配置与两个模型版本未改动。

本轮维护README、DELIVERY_STATUS、DENSE_RETRIEVAL、实验日志/CSV、简历证据、experiment_manifest及当前文件清单。实验注册只追加本次条目，旧条目的历史SHA保留。小步提交、独立PR、普通merge和新标签v0.7.0-retrieval-b0；既有发布标签不移动，仅yangyanbeen/football-rules-rag-lab写入，desktop-tutorial/main保持8e7bafebe26caa0dbcb64d729766513d485c73bb。

实际PR/合并SHA以GitHub记录为准；发布后用audit_remote_delivery.py --expected-commit <新main> --require-supplement --require-task6核对整个公开树/哈希，另核对本报告、任务七逐题文件/凭证/台账和新标签。任务8–13未提前执行；任务14仅同步本阶段归档。
