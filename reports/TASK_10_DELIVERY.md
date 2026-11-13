# 任务十交付报告

基线 `73d5b88bede56dbf83df1c960c9c7e4861e2ef31`；原技术5.3与原执行计划任务10逐字不变。分支`feat/task-10-bge-reranker`，版本`v0.10.0-bge-reranker`。任务1–9、原数据/模型/索引/标签保持。可运行入口与完整说明见[实验文档](../docs/RERANKER_EXPERIMENT.md)。

## 原交付基线逐项对照

| 原要求 | 本轮交付 | 验证依据 |
| --- | --- | --- |
| BGE-Reranker与候选20/40/80/不重排 | 官方固定FP32 ONNX、真实80深候选、四方法 | config/reranker_experiment.json；scripts/bge_reranker.py、reranker_live.py |
| 统一运行脚本 | scripts/run_reranker_experiment.py | dev、prepare-test、test、replay、query；覆盖保护、失败记账 |
| 固定原Dense/BM25/RRF及同测试集 | 原99段/索引、k60/title_body，新增深度80单独配置；40dev/50test | run manifests的inputs/source/index snapshots；不改任务九Top10配置 |
| 汇总JSON | reports/reranker_results.json | dev/test独立重算与report_payload一致 |
| 前后逐题排名 | 两组predictions.jsonl及rank_changes.json | 双路原始分数/排名、RRF前80与重排全候选分数，前后Top10/支持证据名次 |
| 模型/设备/batch/预热/计时 | 版本/SHA、CPU8、batch8、512、各方法3预热、每题各1测量 | 每batch形状/时间、环境、加载单列；总链路真实测量 |
| Recall@5/10、MRR、适用nDCG | 同报，质量分母32/40 | 无分级标签nDCG=null；无答案题只进耗时 |
| 重排/总链路P50/P95 | 四方法全部报告 | dev40/test50个查询样本，普通桌面CPU，非生产SLA |
| 截断损失与错误案例 | 两组error_analysis，开发D001/D011详解 | 保留模型排序变差与候选丢失；test不调参 |
| Top40不得预设最优 | 按dev选择为top40 | f6be8bd5252da48eb5c9253de7ddde7108e88643冻结后，一次正式test；原锁集此前已用于任务7–9 |

## 实测交付结果

| 方案 | Recall@5 | Recall@10 | MRR@10 | 重排P50/P95 ms | 完整链路P50/P95 ms |
| --- | --- | --- | --- | --- | --- |
| no_rerank | 97.500% | 100.000% | 0.936458 | 0.00/0.00 | 358.42/397.62 |
| top20 | 100.000% | 100.000% | 0.975000 | 3206.33/3942.71 | 3566.06/4281.08 |
| top40 | 100.000% | 100.000% | 0.975000 | 6607.19/7335.27 | 6949.91/7696.76 |
| top80 | 100.000% | 100.000% | 0.975000 | 13021.14/13798.49 | 13363.95/14163.51 |

所选方案的多支持平均覆盖率`all_gold_coverage@5`为98.125%，未全覆盖题为T022=75.0%、T034=50.0%。Recall100%表示每题至少一个标注支持命中；全部支持段的前后名次与是否因前缀排除在`rank_changes.json`逐项列出，不能据此宣称每题证据或答案全部正确。

开发选中top40；测试结果只用于报告。不得写成400→120ms、70%、200条评测或40条难负例等未测示例。当前测的是检索，没有测答案准确率、引用正确率、拒答、QPS或生产效果。

## 验收证据

- 专项开发检查：74/74，`acceptance/contract-development.json`。早期68项保留其原范围，不当作当前代码全部检查。
- 独立公开开发复算29/29；最终公开副本（Python -S，无模型/全文/索引/包）35/35，包含25种故意错误副本拒绝与最终恢复校验；`acceptance/public-final.json`。合成错误不是质量评测样本，原始结果没有被篡改。
- 本机完整交付门禁结果：[delivery-final.json](retrieval/bge_reranker_b0/acceptance/delivery-final.json)。检查完整报告/逐题派生、源码授权顺序、实际候选/耗时、原534文件中的历史成果、22私有索引、61语料、人工账本、原16实验对象保全及新实验注册。
- 原任务九完整门禁仅重放复验，`acceptance/previous-task9.json`；没有重测原任务九测试。
- 本轮测量dev5600/test7000个重排pair、各160/200个Embedding查询；预热另有840个pair、24个Embedding查询，预热不进质量/延迟样本。非评测试跑另计，不伪装成评测样本；没有答案LLM调用。

证据目录统一为`reports/retrieval/bge_reranker_b0`。分支按实现、开发、冻结、测试、文档、验收/清单小步提交，经PR进入main并打新标签；旧标签、其他已有仓库不改。公开仓库只保存代码、配置、来源元数据及匿名稳定段ID/分数/计时/已有问题文本，私有全文/权重/向量/倒排数据/账号均不上传。

## 交付复审补齐

已补齐环境采集依赖Embedding驻留导致的冷启动问题：交付版在全部12次预热后采集环境，模拟回归12/12、独立真实冷服务8/8，当前代码专项74/74；原冷启动模拟复现10/10及加入输出别名检查的11/11记录均保留。原dev/test、冻结授权和测试账本保持原字节，无重新检索锁定测试。详见cold-start-regressions.json、cold-start-actual.json、contract-current.json及实验文档。

## 边界与下一步

99段与自建快照标签规模有限，当前结果不代表全部足球规则或生产系统。公开复算无法证明模型logit本身；实际运行使用固定官方SHA权重，本机原全文与逐输入token哈希留存。任务十一按原计划比较结构切分与父子块；本轮不改原切分或任务六网页默认链路。
