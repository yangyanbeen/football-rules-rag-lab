# 任务十四交付：实验档案与简历证据

按[原执行文档](../docs/DEVELOPMENT_PLAN_AND_REPORT.md)汇总任务1–14，原技术设计、执行规则及正式结果保持原样。使用入口：[简历成稿](task14/RESUME_FINAL.md)、[各方法结果与取舍](task14/RESULTS_FINAL.md)、[复验说明](../docs/TASK_14_ARCHIVE.md)。

| 原交付基线 | 已交付的证据 |
| --- | --- |
| 更新四份档案 | [实验日志](../docs/EXPERIMENT_LOG.md)、[实验汇总](all_experiments_summary.csv)、[简历证据](resume_evidence.md)、[实验登记](../data/manifests/experiment_manifest.json)；前25项登记原样保留，本轮只加第26项 |
| 每条记录具备最低字段 | [档案JSON](task14/archive.json)及[CSV](task14/experiments.csv)共28条（25条原记录、2条早于Git的阶段记录、1条本次归档）；均记录目标、对照、主要变量、数据/测试版本、代码、模型、参数、硬件、命令、原始结果、指标和结论。历史未记录项明确标注 |
| 简历数字可追溯 | 78个实测数字、9组来源。证据编号给出原始结果路径、JSON指针、逐题记录、执行命令、参数文件和SHA256。与工程、数据规模有关的数字回链到相应数据清单或审核记录 |
| 未执行写“待测” | 12类未测、未验实或示例数据标为“待测”，不作为简历成绩 |
| 保留负收益 | Top10 RRF 的 MRR@10 为0.9175，低于BM25的0.95；子块Recall@5降低；父子块MRR改善但Recall@10下降、上下文增加；CPU重排仍有耗时成本，早先引用错误和实际人审结果均保留 |

本机[专项回归](task14/regressions-final.json)与[干净公开专项回归](task14/public-regressions.json)均为43/43；[本机历史复算](task14/formal-replay-first.json)和[干净公开复算](task14/public-formal-replay.json)均为13/13。复算覆盖Dense、BM25、混合、重排、结构切分的开发和测试汇总，以及两组回答评测、一组真实人工抽样算术。任务十三追加新登记前[复验](task14/prior-task13.json)28/28。

[第一轮](task14/regressions-first.json)和[第二轮](task14/regressions-second.json)各有1个检查失败：前者断言对早期SHA文字过严，后者新增分母后反例按位置选到了原本就是人工指标的条目。最终用稳定编号定位AI指标，并用类型严格的序列化比较防止将布尔值当数字。首版档案在 `task14/drafts/`，当前有效制品在 `task14/` 直属目录。

本轮0次新模型请求、0次重跑正式测试、0条新人工判断。公开副本可在没有私有语料、模型、索引、第三方Python包的情况下复算。指标仅对应历史固定数据、方法和环境；人工12题为错误优先抽样，旧AI评分与人工评分分别存放。未改变历史应用或检索配置。
