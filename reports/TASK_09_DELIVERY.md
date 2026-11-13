# 任务九交付：混合召回与RRF

日期：2026-11-13。起点e5bdb70，执行分支feat/task-09-hybrid-rrf。原技术设计/执行文档及交付标准保持原字节，范围见 [TASK_09_SCOPE](../docs/TASK_09_SCOPE.md)。

**任务九已达到原交付标准：完整门禁30/30、专项56/56、真实查询17/17、公开副本复算7/7，前序任务八35/35通过。** 验收文件、版本与GitHub提交可相互回查；没有把负收益改写为提升。

## 1. 原交付要求逐项对应

| 原要求 | 交付及验证 |
| --- | --- |
| RRF模块 | scripts/rrf.py：默认k=60，可配置；精确分数排序、稳定同分、按ID去重、保留通道原rank/score/来源 |
| 统一运行脚本 | scripts/run_hybrid_retrieval.py：dev、prepare-test、test、replay、query；hybrid_live.py实际双路查询 |
| 规定结果文件 | reports/hybrid_rrf_results.json，严格从原预测复算四方法dev/test质量、耗时口径和相对优劣 |
| 双路与融合逐题排名 | retrieval/hybrid_rrf_b0/dev和test/predictions.jsonl；原两路完整记录、四方法排名、原分数/距离/耗时、新融合三次测量和输出哈希 |
| 同数据、测试、候选预算 | 原99段/40dev/50test；每路原Top10，四方法输出上限10；内部双路并集至多20，单列无序覆盖诊断 |
| 错误分析 | dev具体案例、test仅聚合；无分级标签，不虚构nDCG |
| 文档与复现 | docs/RRF_EXPERIMENT.md，离线/真实查询/验收命令、版本、源数据哈希、环境和限制齐全 |

## 2. 正式结果与去留

| 50题test中的40条可回答 | Recall@5 | Recall@10 | MRR@10 |
| --- | --- | --- | --- |
| Dense | 95% | 95% | 0.860417 |
| BM25 | 97.5% | 100% | 0.950000 |
| 交替并集Top10 | 100% | 100% | 0.886250 |
| RRF k=60 | 97.5% | 100% | 0.917500 |

RRF优于Dense；与BM25两项Recall持平，MRR下降0.0325。保留为可追溯的候选生成选项，未替代最佳单路排序结论，也未改变UI默认Dense链路。后续Reranker应保留BM25、并集和RRF对照，不能只引用与Dense相比的提升而隐去BM25更优的MRR。

开发集RRF的Recall@5/10均100%、MRR=.9296875，正式test没有达到同样的MRR；如实保留。原题集已用于前序单路报告，不称全新未见测试集。

## 3. 顺序与测试证据

- 4690303实现固定协议，40/40合成、边界、预约与失败检查通过。
- 40题dev完成后56/56专项通过，ae3c3b5提交dev和验收并冻结代码、输入、k=60。
- 凭证绑定该Git提交、dev manifest/summary、56项逐检查/源码回执及唯一输出目录；随后进行一次离线正式test融合。
- Task9独立账本仅有STARTED/COMPLETED两条；原Dense/BM25正式测试账本和结果不改，没有新调用两路测试检索器、没有答案生成或测试调参。
- 实际双路查询4条、17/17通过；包括BM25 OOV，不使用原测试问题，不计准确率。固定BGE-M3 CPU、无付费服务、原正式索引字节不变。
- acceptance/public-only-replay.json：无语料、索引、.runtime、.venv，python -S下无jieba/numpy/chromadb，dev/test两组完整复算。
- acceptance/previous-task8.json：原任务八35项门禁复验；Task9完整门禁还独立核验90题RRF公式、原480文件/22索引/61语料、原14实验对象及人工账本。

验收文件位于 [retrieval/hybrid_rrf_b0/acceptance](retrieval/hybrid_rrf_b0/acceptance)。本轮未遇到需覆盖历史运行的失败；坏数据与合成故障通过隔离副本验证，不能描述为实际生产事故。若有交付核对过程的失败，保留原报告并在最终记录说明。

## 4. 耗时、环境和数据边界

dev/test各预热3个双候选合成包，每题重复3次，合计270次新融合处理；第一次排名计质量，全部计时。test融合处理P50/P95=.223900/.279570ms，包含校验、去重及四种输出构造，不是完整检索或答案延迟。两路原始耗时分别保留，不跨时间拼接端到端计时。

环境在融合后单独观察：Python3.10.22、Windows、20逻辑CPU、16,858,472,448字节内存；详细固定包、模型/设备和采集时间见environment.json。没有回填历史manifest。实际查询分阶段和总计时另列，不作为优化百分比、QPS或生产SLA。

来源是原Wikipedia社区快照、中文AI翻译未经裁判专家审校；不称官方赛季完整规则书或答案准确率。公开结果没有规则全文、倒排词频、向量、账号、依赖包或运行数据库。原工程和其他已有仓库不动。

## 5. 版本与后续

补充当前README、运行说明、EXPERIMENT_LOG、all_experiments_summary.csv、resume_evidence及experiment_manifest；原14个实验对象保持不变。文件清单随最终提交生成。小提交通过独立PR交付，版本标签 `v0.9.0-hybrid-rrf`；旧标签不移动。任务10继续原BGE-Reranker及候选截断计划，不在本轮声称已完成。
