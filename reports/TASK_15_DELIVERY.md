# 任务十五交付报告

FAISS HNSW 独立基准已按原任务十五要求运行。使用原 Corpus B0 的 99 条文档向量和同一台机器，比较 FlatIP 与四组 HNSW。开发集按冻结规则选中 Flat。原锁定测试完成一次，数据和标签沿用前序版本。 [原执行标准](../docs/DEVELOPMENT_PLAN_AND_REPORT.md) · [配置、结果与复跑](../docs/FAISS_HNSW_EXPERIMENT.md)

| 原任务要求 | 交付证据 |
| --- | --- |
| 固定 Embedding、向量数据、机器和测试集 | [开发运行清单](task15/dev/run_manifest.json)、[测试运行清单](task15/test/run_manifest.json)、[测试冻结记录](task15/test-freeze.json) |
| 至少两种 M、efConstruction、efSearch | `M=8/16`、`efConstruction=40/100`、`efSearch=16/64`，逐项改变，搜索深度对照共享同一索引。[固定配置](../config/faiss_hnsw_experiment.json) |
| 索引构建耗时、大小与内存 | 4 个物理索引各 3 次真实独立构建，记录进程 RSS、Windows 峰值工作集与 12 次文件哈希。[构建原始读数](task15/dev/builds.json) |
| Recall@K 和查询 P50/P95 | 40 道开发题和 50 道测试题，每组每题 32 次纳秒计时。质量和近似搜索重合率见各期汇总。[测试逐题](task15/test/predictions.jsonl) · [测试汇总](task15/test/summary.json) |
| 独立脚本、清晰复跑和保留负收益 | [基准入口](../scripts/run_faiss_hnsw.py)、[FAISS_HNSW_EXPERIMENT.md](../docs/FAISS_HNSW_EXPERIMENT.md)、[公开复算](task15/replay-public.json) |

测试集五组 Recall@5 和 Recall@10 均为 97.5%（39/40）。HNSW 参考组与 Flat 的 Top10 平均重合率为98.2%，搜索 P50 为7.7 µs，Flat 为9.1 µs。达到100%重合的 S64 组 P50 为12.2 µs。参考图比 Flat 多14,449字节，构建 RSS 中位增量分别为240 KiB 和52 KiB。保留原应用及部署配置。规模扩展、端到端延迟和吞吐为待测。 [完整结果和逐题差异](task15/test/summary.json)

编目记录新追加一项，原 26 项登记和旧文档保留。开发及测试合计 90 条查询向量、23 个 Embedding 批次。文档向量直接复用，新增文档编码和答案请求均为0。公开制品记录 ID、分数、读数和哈希。索引二进制和查询向量留在本机。 [实验登记](../data/manifests/experiment_manifest.json)

回放在本机和独立公开副本各通过 17/17，核对两期质量、索引构建指标、计时和冻结溯源，并确认九种无效材料会被拒绝。公开副本使用 Python `-S -B`。 [本机回放](task15/replay-local.json) · [独立公开回放](task15/replay-public.json)
