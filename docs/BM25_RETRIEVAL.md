# BM25 中文检索基线（任务八）

原要求：TECHNICAL_DESIGN第5.1节、DEVELOPMENT_PLAN_AND_REPORT任务八，原件不改。汇总在 [bm25_baseline.json](../reports/bm25_baseline.json)，交付在 [TASK_08_DELIVERY](../reports/TASK_08_DELIVERY.md)。

## 1. 数据、实现与固定参数

同一99段Corpus B0、40开发题/50锁定测试题和任务七Dense记录。ID、原文、来源、人工标签和正式Dense索引不变。BM25索引只保存本机倒排所需词频/长度/来源映射，无Embedding或答案LLM调用，未接入现有UI。

分词来自官方 [jieba](https://github.com/fxsjy/jieba) 0.42.1 [PyPI包](https://pypi.org/project/jieba/0.42.1/)，包SHA `055ca12f62674fafed09427f176506079bc135638a14e23e25be909131928db2`，默认dict.txt SHA `7197c3211ddd98962b036cdf40324d1ea2bfaa12bd028e68faa70111a88e12a8`。安装和运行均核对官方压缩包及54个实际文件，不只相信可改写的本地清单。MIT许可原件留在隔离安装目录。

- 正式B0：准确模式、HMM=False；NFKC、casefold、折叠空白。配置在config/bm25_b0.json。
- 自写足球词表21词，固定词频200000，见bm25_userdict.txt；12个停用词见bm25_stopwords.txt。否定、条件词、数字及单位保留。
- 第十一条/第11条/第１１条统一为rule:11和11；整数、小数独立保留，如7.32、2.44。规则号只是词项，不筛选候选，不把chunk ID加入正文。
- `body`只用content_zh；`title_body`为title_zh换行正文；`path_body`为完整section_path拼接后换行正文。没有复制正文到多个字段加权。
- 自行实现透明BM25评分，无rank_bm25额外依赖。k1=1.5，b=0.75，查询唯一词项计一次；长度为实际保留token数。

```text
idf(t) = ln(1 + (N-df(t)+0.5)/(df(t)+0.5))
score(q,d) = Σ idf(t) × tf(t,d)×(k1+1) /
                 (tf(t,d)+k1×(1-b+b×len(d)/avgdl))
```

正IDF形式参照 [Lucene BM25Similarity](https://lucene.apache.org/core/9_9_1/core/org/apache/lucene/search/similarities/BM25Similarity.html)；本项目显式使用上述完整公式和参数，未声称逐位兼容Lucene的长度编码。仅返回得分大于0的至多Top10，同分按chunk_id升序，OOV返回空列表，不用零分块填满排名。

## 2. 开发选择与正式结果

只在dev按MRR@10、Recall@5、Recall@10降序选择，并列按body/title_body/path_body顺序。三组执行源码b71bbb1，结果和74项合成/故障/独立复算检查提交后，在65e7516冻结正式测试方案并授权。

| 准确模式模板 | Dev Recall@5 | Recall@10 | MRR@10 | 总检索P50/P95 ms，120次 |
| --- | --- | --- | --- | --- |
| body | 93.750% | 96.875% | 0.888889 | 0.278550 / 0.350340 |
| title_body，选中 | 96.875% | 96.875% | 0.893229 | 0.266600 / 0.342935 |
| path_body | 93.750% | 96.875% | 0.889881 | 0.280100 / 0.361335 |

| 同一锁定测试 | Recall@5 | Recall@10 | MRR@10 | all_gold_coverage@5 |
| --- | --- | --- | --- | --- |
| 原Dense B0 | 95%（38/40） | 95%（38/40） | 0.860417 | 93.125% |
| BM25 title_body | 97.5%（39/40） | 100%（40/40） | 0.950000 | 95.625% |

共50题，其中40条可回答、10条不可回答；不可回答不进入检索质量分母，全部题计延迟。题级Recall是至少命中一个支持ID；完整支持集合覆盖另列。无分级标签，不报nDCG。检索结果不等于答案正确率。

BM25测试150次总检索P50=0.265350ms、P95=0.377535ms。相同锁定集下，Recall@5相对Dense增加2.5个百分点、Recall@10增加5个百分点、MRR@10增加0.089583。它们是当前小规模快照集的单路结果，不推导生成质量或生产吞吐。

## 3. 计时与可复算证据

每集合固定非评测问题预热3次，再每题3次、并发1。第一次排名计质量，全部重复计延迟；规范化、分词、评分/排序和总耗时分开保存，使用perf_counter_ns与线性插值q×(n−1)。索引/词典加载、语料校验、写盘、授权和复算不含在查询延迟；整轮wall和加载时间另存。jieba的词典初始化缓存不是问答结果缓存。

Dense原延迟包含Embedding HTTP与固定模型/向量检查，BM25是99段Python词法计算；报告各自实测口径，不用二者时间差声称端到端优化百分比或QPS。

成功主实验为3×120开发测量加150测试测量，共510；另有12次预热。predictions.jsonl逐题保存query、token、排名/正分数、原来源元数据及3次计时；requests.jsonl每次成功请求立即flush。summary/error_analysis、源码/资源/输入/索引manifest及STARTED/COMPLETED账本保留。公开不含正文、倒排词频或向量。

测试凭证绑定3组dev选择、74项回执、源码65e7516、数据锁、词表和索引身份。原Task4 test_lock及旧Dense使用账本不回填；任务八test_usage.jsonl只有这一次正式运行的两条事件。测试错例只聚合报告：Top5漏1题，Top10漏0题。

## 4. 分词模式补充对照（明确在正式测试之后）

按原技术文档补充 [分词子任务](TASK_08_SEGMENTATION_SUPPLEMENT.md)，同一40题dev、title_body及其他固定参数，仅换成jieba搜索模式、HMM=False。搜索模式重叠词正常计TF/长度；它的Dev Recall@5/10均96.875%、MRR@10=0.901042，120次P50/P95=0.239200/0.334935ms。

这组数据是在唯一正式测试完成之后生成，作为单独的开发探索保存，没有追认成测试前的选择证据。准确模式仍是正式B0，搜索模式没有新测试成绩。结果见segmentation-dev/comparison.json、原始预测和独立复算。读取边界：未加载测试问题供检索、未读取测试分数；共享dev复算器会为完整性校验哈希测试文件字节，不能说完全没有测试文件I/O。

## 5. 典型诊断与限制

- 规则号探针“第十一条：越位位置本身是否就是越位犯规？”保留rule:11/11，Top1为L11-01；Top3也有L12-05，说明编号词不排除相似犯规内容。
- 小数探针“7.32米和2.44米分别对应球门的哪些尺寸？”保留两个小数和“米”，Top1为L01-03。
- 术语探针“间接任意球能否直接射入对方球门？”保留“间接任意球”，Top1为L13-05。探针不增加评测准确率样本。
- Dev D001“人工草坪的颜色有什么限制？”的支持L01-01未入Top10，显示词面表达差异仍会漏召回；没有据此添加同义词。原query/token/gold及排名可在dev错误分析核验。
- 资料来源是Wikipedia社区快照，中文AI翻译未经裁判专家审校，历史正文未独立核验。本任务没有改变这些边界。

## 6. 安装、重建与复算

先按PUBLIC_SETUP导入原61个语料文件，使用现有Python3.10.22。隔离安装不改原262包或上游源码；首次下载约19MB，后续可离线verify-only。当前锁定Setuptools下会显示jieba使用pkg_resources的弃用警告，已记录；不升级核心依赖来隐藏它。

```powershell
.venv/Scripts/python.exe scripts/install_bm25_runtime.py
.venv/Scripts/python.exe scripts/install_bm25_runtime.py --verify-only
# 首次恢复三个本地索引；已有目录会拒绝覆盖
.venv/Scripts/python.exe scripts/build_bm25_index.py --template body
.venv/Scripts/python.exe scripts/build_bm25_index.py --template title_body
.venv/Scripts/python.exe scripts/build_bm25_index.py --template path_body
# 已存在的公开原索引元数据只核验，不改写
.venv/Scripts/python.exe scripts/export_bm25_manifests.py
# 用新目录执行dev；可以--index指定独立重建的索引
.venv/Scripts/python.exe scripts/run_bm25_retrieval.py dev --template title_body --run-dir reports/retrieval/my-new-bm25-dev
# 只复算已保存原始结果，不需要全文、jieba、模型或私有索引
python -S scripts/recompute_bm25_retrieval.py --run-dir reports/retrieval/bm25_b0/test --output reports/rechecks/my-new-bm25-test-replay.json
.venv/Scripts/python.exe scripts/compare_bm25_segmentation.py --replay-only --output-dir reports/retrieval/bm25_b0/segmentation-dev
# 完整本机交付门禁需要本机数据/索引/审核账本，报告必须新建
.venv/Scripts/python.exe scripts/verify_bm25_delivery.py --report reports/rechecks/my-new-task8-delivery.json
```

重建索引可能来自较晚合法提交；校验保持原postings/来源映射字节、语料/资源身份，并分别核对新producer的Git来源。旧原始manifest不重签。复现修复只在新dev中验证，未重跑正式test。Git不足历史对象时需取得完整历史后复算。
