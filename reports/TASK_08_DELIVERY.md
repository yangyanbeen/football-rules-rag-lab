# 任务八交付报告：BM25中文检索基线

日期2026-11-12；基准main8b21522；分支feat/task-08-bm25-baseline。原技术/执行规则不改。**任务八按原标准通过，完整本机门禁35/35**，记录见[task8_delivery_gate.json](retrieval/bm25_b0/acceptance/task8_delivery_gate.json)。

当前专项74/74、复现恢复8/8；无语料/索引/模型/分词依赖、Python -S公开副本复算五组成功（9项检查）。原任务四26/26、任务六62/62、任务七43/43回归通过；分别记录，不相加作为质量样本。最终文档归档后的门禁见acceptance/task8_delivery_final.json。

## 原交付物

| 原要求 | 已实现 |
| --- | --- |
| build_bm25_index.py与可复现分词/词典 | 固定jieba0.42.1官方包/默认词典SHA，21词自定义表、12停用词；准确模式HMM=False；数字、规则号、否定条件保留 |
| BM25索引 | 本机data/indexes/bm25/{body,title_body,path_body}各99段；正文和词频不公开，3份索引manifest公开 |
| run_bm25_retrieval.py | dev→三模板选择→源码/回执提交冻结→prepare-test→唯一test；单独授权与使用账本 |
| bm25_baseline.json与逐题结果 | 已保存3组dev、1组test的预测/正分数/3次计时、来源映射、模型无调用声明、manifest与错误分析 |
| BM25_RETRIEVAL.md | 分词、公式、参数、计时、安装/重建/复算、规则/数字/术语案例与限制齐全 |
| 原技术5.1分词设置对比 | 独立补充dev搜索模式对照，明确在正式测试之后；没有重新选择正式B0或重测test |

## 已完成的真实测量

准确模式开发40题（32可回答/8不可回答），三模板结果：body R@5=93.75%、R@10=96.875%、MRR=.888889；title_body R@5/10=96.875%、MRR=.893229；path_body R@5=93.75%、R@10=96.875%、MRR=.889881。按预先MRR优先规则选择title_body。

源码b71bbb1生成dev；74项检查及全部开发/选择结果提交后，65e751648d7a108cdb8e1acde2710f313639414a冻结唯一正式test。50题包括40可回答/10不可回答：**Recall@5=97.5%（39/40），Recall@10=100%（40/40），MRR@10=.95，完整支持集合覆盖@5=95.625%**。150次查询总P50/P95=.265350/.377535ms；另有3次预热。

相同锁定集原Dense R@5/10=95%、MRR=.860417；BM25分别增加2.5和5个百分点、MRR增加.089583。计时范围、质量分母和多支持区别见技术说明；没有生成答案准确率、QPS或生产性能提升结论。

## 验证、失败与复现修补

- 合成/索引检查初版54/54；首次dev末尾的独立复算误拒绝原有L08A/L08B稳定ID，保留dev/body/failure及原预测，不改旧数据。修复并增加原99种ID检查后55/55，成功三模板另存development/。
- 正式测试前74/74：手算BM25、词典/数字/规则/术语、错误输入、重签哈希后的索引损坏、12种dev记录破坏及三组复算。原测试只执行一次，STARTED/COMPLETED两条台账，未调参。
- 公开恢复检查发现producer提交变化会使字节相同的重建索引被过度拒绝；补齐payload/资源身份与独立Git来源核对，支持--index新dev，元数据导出只验证旧记录。正式65e7516源码与测试记录不回写；修补验证另存portability.json。
- 补充分词对比：40题dev搜索模式，R@5/10=96.875%、MRR=.901042；它发生在正式test之后，明确标为探索，不能追认成测试前选择。准确模式正式B0与唯一测试保留。
- 补充脚本的test_questions_read:false表示没有将测试题加载到检索器。共享dev复算仍哈希测试文件字节，说明保存在segmentation-dev/INTEGRITY_SCOPE.json；不宣称零测试文件I/O。
- jieba运行出现已知pkg_resources弃用警告，核心262包与模型环境未升级。完整倒排、第三方源码和原文均只在本机。

## 交付范围与保全

原Corpus B0、61文件、正式Dense索引、90条人工账本、评测锁、旧Dense授权/使用台账、旧交付报告、10冻结文件/4历史前缀/178原工程文件均保留。任务八新增74项及专项保护不改原门槛；搜索对照与恢复dev不算新增测试样本。

输入、输出与源码SHA见各run_manifest、bm25_indexes.json、test_authorization.json和最终验收。公开代码/配置/词表/问题排名分数计时及来源哈希；不公开规则全文、词频索引、向量、账户或密钥。原11个实验对象保留，只追加本阶段。

本机三个准确模式索引均完成新目录真实重建，index.json和source_map.json逐字节一致。恢复缺陷修补后的新dev40题保持R@5/10=96.875%、MRR=.893229；该记录独立保存在portability回执指向的新目录，不替换原开发/正式测试。原工程178文件保全由前序43项门禁核对。

运行/重建/复算见[BM25_RETRIEVAL](../docs/BM25_RETRIEVAL.md)，边界见[TASK_08_SCOPE](../docs/TASK_08_SCOPE.md)和[分词补充子任务](../docs/TASK_08_SEGMENTATION_SUPPLEMENT.md)。提交继续独立PR、小步Git与v0.8.0-bm25-b0新标签，仅向football-rules-rag-lab写入，旧仓库及旧标签不动。任务九的RRF按原计划继续。
