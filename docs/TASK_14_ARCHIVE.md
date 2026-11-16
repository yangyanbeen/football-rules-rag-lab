# 任务十四：读懂实验档案并复验数字

任务十四是任务1–14的最终证据归档。原[开发标准](DEVELOPMENT_PLAN_AND_REPORT.md)和历史实验记录继续保存。当前的问答入口与运行环境仍使用[任务十三修订版](TASK_13_AUDIT.md)。

| 想做什么 | 从哪里开始 |
| --- | --- |
| 找可写进简历的事实 | [当前简历稿](../reports/task14/RESUME_FINAL.md)，句末是数字的证据编号 |
| 看各方法结果与取舍 | [对照结果](../reports/task14/RESULTS_FINAL.md) |
| 筛选任务或实验 | [最终CSV](../reports/task14/experiments.csv)，另有[完整JSON](../reports/task14/archive.json) |
| 核对是否通过原交付要求 | [交付报告](../reports/TASK_14_DELIVERY.md) |
| 查看阶段原记录 | [原实验日志](EXPERIMENT_LOG.md)、[登记清单](../data/manifests/experiment_manifest.json) |

在仓库根目录，用 Python 3.12 和完整 Git 历史执行（浅克隆需先补齐历史）。以下命令只读；`-S` 禁用第三方包加载。

```powershell
python -S -B scripts/task14_archive.py show --claim reranker_top40_r5
python -S -B scripts/task14_archive.py show --group reranker
python -S -B scripts/task14_archive.py show --experiment LEGACY-TASK-001
python -S -B scripts/task14_archive.py verify
```

以 Top40 的 Recall@5 为例：`source` 与 `pointer` 指向原测试汇总里的数值；`lineage.raw_results` 列出逐题排名，`lineage.parameters` 提供固定模型、预算和参数的配置，`lineage.historical_commands` 保留原命令。质量分母是40条可回答测试题；计时覆盖全部50题。原样例只能说明固定集上的结果。导出的CSV为 UTF-8，嵌套字段存为 JSON；需要完全保留类型时读 JSON 档案。

要复算保存的正式结果、验证归档拒绝被篡改的数字，并跑完整公开验收，可以执行下面的命令。报告路径须在当前仓库内且未被占用。完整本机验收另外读取本机冻结清单；公开使用者只需 `--public-only`。

```powershell
python -S -B scripts/replay_task14.py --report .tmp/task14-replay-new.json
python -S -B scripts/verify_task14_archive.py --report .tmp/task14-regressions-new.json
python -S -B scripts/verify_task14_delivery.py --public-only --report .tmp/task14-delivery-new.json
```

应先创建 `.tmp`。原始预测、标签和人工抽样用于只读复算，操作无需私有全文、模型、索引或 GitHub 凭据。第一次和第二次回归的失败报告及首版归档均保留，仅最终回执用于验收。导出程序的 `build` 拒绝覆盖现有制品；阶段文档与既有成绩按原版本保留。

RRF 相对 BM25 的 MRR 下降、子块召回下降、父块上下文成本和原回答错误均保留。FAISS HNSW、语义缓存、LangGraph、承载量和总体答案准确率提升均为“待测”。
