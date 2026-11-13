# 混合召回与RRF实验（任务九）

依据原技术设计5.2与原任务9；范围及先后顺序见 [TASK_09_SCOPE](TASK_09_SCOPE.md)，交付见 [TASK_09_DELIVERY](../reports/TASK_09_DELIVERY.md)，规定汇总为 [hybrid_rrf_results.json](../reports/hybrid_rrf_results.json)。原权威文档未修改。

## 1. 数据、排名与预算

固定原99段Corpus B0、40题dev（32可回答/8不可回答）、50题test（40可回答/10不可回答）。Dense采用任务七固定BGE-M3/Chroma结果；BM25采用任务八开发阶段选定的准确分词title_body结果，不使用后续搜索分词探索。原查询规范化、源ID、正文、标签、词表、索引、原始逐题预测和两路耗时不变。

每路输入原Top10，候选按chunk_id合并，跨路只保留一个候选并记录两个来源。每个方法最终输出至多10条，作为相同的下游候选预算；源列表不足时不补零分。双路内部评分集合自然可达20条，单路只有原10条，本实验不声称所有方法内部评分池相同，也不把完整20条并集覆盖当作Top10提升。没有原Top20/40/80排名，不对更深候选做结论。

| 方法 | 排序定义 | score含义 |
| --- | --- | --- |
| dense | 原Dense排名，至多Top10 | 原1-cosine distance |
| bm25 | 原正分BM25排名，至多Top10 | 原BM25分数 |
| union | 按Dense第1、BM25第1、Dense第2、BM25第2交替，跳过已出现ID，取Top10 | null，避免虚构可比得分 |
| rrf | 双路排名贡献求和，同分按chunk_id升序，取Top10 | RRF排名分数 |

并集本身无排名，所以不能直接计算MRR；主对照的union是预先规定的交替排名控制。完整并集另报无序集合覆盖、最小/最大/平均数量。两路原始分数保留用于诊断，从不直接相加。

## 2. RRF实现与参数

```text
RRF(d) = Σ 1 / (k + rank_i(d))
```

排名从1开始；缺失通道贡献0。默认k=60，配置在config/hybrid_rrf.json；独立dev可用--k覆盖并写入manifest。k要求非布尔整数，范围0至1,000,000。内部用标准库Fraction排序，避免数学同分被浮点求和顺序打散；公开score为对应float，同分再按ID升序。

`rrf.py`只接受排名、分数和来源元数据，不接受问题gold、正文或答案。跨路同ID去重；同路重复ID、排名断档、非有限分数、冲突来源、额外正文字段等直接拒绝，缺失整个通道不静默降级；显式空BM25列表是正常OOV情况。

候选保存六个原来源字段和sources：分别含dense/bm25原rank、score，Dense还保留distance。逐题channels内保存原两路整条预测，包括原3次测量，与原输入逐字节规范化JSON比较。测量后的融合结果也由独立的逐候选分数求和参考实现核验90题。

## 3. 开发与正式报告顺序

1. 4690303提交固定实验和执行实现；40项手算、边界、失败/预约检查通过后，使用原dev结果生成融合实验。
2. 包含开发篡改反例的56项专项通过，ae3c3b5提交dev、检查回执及真实查询检查器，冻结执行代码和默认k=60。
3. 凭证绑定该提交、原数据/两路结果哈希、dev manifest/summary、56项完整回执及唯一test输出路径，然后进行一次正式离线test融合。
4. 正式test没有重新调用Dense或BM25检索器，也没有答案生成；独立STARTED/COMPLETED账本仅有两条事件。测试结果不用于修改参数。

原测试集已在任务七、八用于单路报告；它不是本轮全新未曝光holdout。输入快照会哈希原test文件以验证完整性，不能说开发阶段没有测试文件I/O。只有正式报告阶段加载原测试排名进行融合/评分；开发调试只用dev与合成数据。

## 4. 结果

每题至少命中一条标注支持即计Recall命中；多支持完整覆盖另列。不可回答题不进入质量分母，仍保留两路/融合结果及耗时。无分级标签，不报告nDCG。

| 集合/方法 | Recall@5 | Recall@10 | MRR@10 |
| --- | --- | --- | --- |
| Dev Dense | 96.875% | 96.875% | 0.890625 |
| Dev BM25 | 96.875% | 96.875% | 0.893229 |
| Dev union | 100% | 100% | 0.895833 |
| Dev RRF | 100% | 100% | 0.929688 |
| Test Dense | 95% | 95% | 0.860417 |
| Test BM25 | 97.5% | 100% | 0.950000 |
| Test union | 100% | 100% | 0.886250 |
| Test RRF | 97.5% | 100% | 0.917500 |

结论：在当前固定测试上，RRF相比Dense的Recall@5增加2.5个百分点、Recall@10增加5个百分点、MRR增加0.057083；与BM25的两项Recall持平，MRR下降0.0325。RRF不是当前最佳排序方法，不将它包装为全面提升。union的Top5命中更高但MRR低于BM25，说明证据进入候选与最佳证据排在前面是不同目标。后续Reranker保留各方案作对照，当前UI默认Dense链路未改变。

完整无序并集的可回答题支持覆盖在dev/test均为100%，对应平均候选15.8/15.66条；test实际13–19条。这个集合诊断不能和单路Top10排名指标直接作公平提速或质量提升结论。

## 5. 开发案例与测试聚合

- D001“人工草坪的颜色有什么限制？”：支持L01-01在Dense第1，BM25原Top10未命中，RRF第2，union第1。语义通道补足词面漏召回。
- D020“球最后被守方触及并整体越过球门线但没有得分，一般如何重启？”：支持L17-01在BM25第2，Dense原Top10未命中，RRF第4，union第3。词法通道补足Dense漏召回。
- 原始来源、双路贡献与所有32条可回答dev案例保存在dev/error_analysis.json。test/error_analysis.json仅聚合各方法Top5/10漏召回数，不给测试错例调参建议。

## 6. 计时与真实查询

融合模块以双候选合成包预热3次；每题3次，第一份排名计质量，全部测量计延迟，并发1、无缓存。计时包含输入/来源检查、去重、四方法结果构造及排序，不含读文件、原通道网络请求、写盘或事后复算。结果摘要用q×(n−1)线性插值计算P50/P95。

- dev新融合处理120次：P50/P95=0.226100/0.265995ms。
- test新融合处理150次：P50/P95=0.223900/0.279570ms。
- 原Dense/BM25查询耗时原样保留并各自汇总；两路原运行时间不同，未相加冒充本轮实测端到端时间。

另有4条非原测试题的真实查询，包括规则号、数字、术语和BM25 OOV。17项检查通过：两路实际运行、结果来源/去重/公式可复算、分阶段与总计时一致、CPU固定模型、原索引字节不变。实际规范化、Dense、BM25、融合及总耗时在live-smoke.json逐条保存；它们没有评测gold，不计准确率或延迟基准样本，不生成答案。

环境观察在两次融合完成后单独采集并标明时间，没有回填原manifest。Windows、Python3.10.22、20逻辑CPU、物理内存16,858,472,448字节；CPU BGE-M3固定原digest、8线程、num_gpu=0。完整包版本、硬件及确定性/随机种子说明见acceptance/environment.json。原jieba弃用警告保留，不修改核心依赖隐藏警告。

## 7. 运行与复算

仅克隆公开仓库即可在标准库模式复算已有实验；使用新的输出文件名：

```powershell
python -S scripts/run_hybrid_retrieval.py replay --run-dir reports/retrieval/hybrid_rrf_b0/dev --output reports/rechecks/my-rrf-dev.json
python -S scripts/run_hybrid_retrieval.py replay --run-dir reports/retrieval/hybrid_rrf_b0/test --output reports/rechecks/my-rrf-test.json
# 新dev参数实验：原B0结果不覆盖，不再次正式测试
python -S scripts/run_hybrid_retrieval.py dev --k 20 --run-dir reports/retrieval/my-rrf-k20-dev
```

新dev运行还要求本机原人工账本，以复核90/90原交付；公开副本只复算已有记录。真实查询须先按PUBLIC_SETUP恢复语料、两个原索引、固定依赖和本机Ollama/BGE-M3：

```powershell
.venv/Scripts/python.exe -B scripts/run_hybrid_retrieval.py query --question "请检索第十一条下关于越位的资料段落。" --output reports/rechecks/my-live-hybrid.json
.venv/Scripts/python.exe -B scripts/verify_hybrid_live.py --report reports/rechecks/my-hybrid-smoke.json
.venv/Scripts/python.exe -B scripts/verify_hybrid_contract.py --development-run reports/retrieval/hybrid_rrf_b0/dev --report reports/rechecks/my-rrf-contract.json
.venv/Scripts/python.exe -B scripts/verify_hybrid_delivery.py --report reports/rechecks/my-task9-delivery.json
```

正式test入口必须有提交过的dev与检查回执，再prepare-test；已有Task9账本会拒绝重复预约。日常阅读复验使用replay，不删除账本重跑。数据、代码或候选深度变化应新建任务/实验版本。Git历史须完整，才能验证原生产提交与输入对象。
