# 足球规则RAG项目：当前可使用的简历版本

基于开源Kotaemon二次开发。数据是Wikipedia固定快照的AI中文整理，非官方赛季规则、非裁判专家审校；以下是小规模固定领域集的工程与实测事实。

- 将5份中文资料、99个稳定知识段接入可追溯问答系统，实现Dense/BM25混合检索、RRF融合、候选截断重排、结构化证据选择及来源/许可校验。[documents, chunks]
- 构建40题开发集、50题锁定测试和90对难负例；同轮候选深度固定的重排对照中，Top40方案在40条可回答测试题上的Recall@5为100%、MRR@10为0.975，开发先选方案，测试仅报告。[dev_questions, test_questions, hard_negatives, reranker_answerable, reranker_top40_r5, reranker_top40_mrr]
- 实现结构感知切分与父子块来源区间映射，从原知识段派生102子块/18父块，在4096 token预算下比较完整证据覆盖与上下文成本，保留子块召回下降和父块成本增加的结果。[children, parents, context_budget]
- 建立检索逐题评测、回答/引用/条件/拒答评测及12题真实人工抽样，支持无模型结果复算、故障回执、Git/PR小步版本与文件hash追溯。[human_samples]

## 面试时必须说明的边界

- 当前集成采用重排链路；父子块为独立对照实验，并非已全面替换线上链路。
- 同轮无重排控制Recall@5=97.5%、MRR@10=0.936458。Top40重排本机CPU P50为6607.1904ms，完整检索链P50为6949.9119ms；不可写成120ms或整体提速。[reranker_no_rerank_r5, reranker_no_rerank_mrr, reranker_top40_rerank_seconds_P50_ms, reranker_top40_total_seconds_P50_ms]
- 锁定测试已经用于前序阶段报告，不称完全未见holdout；Recall为命中任一标注支持段，不保证全部证据齐全或答案正确。
- 人审受AI建议辅助且优先抽取错误样本，不是盲审或裁判专家认证。原人工引用9/20，原AI引用正确率30.986%，保留质量缺口，不写总体准确率提升。[human_citation_correctness_numerator, human_citation_correctness_denominator, ai_citation_correctness]
- FAISS调优、语义缓存、LangGraph、QPS和未运行的示例收益均待测。

## 每个数字怎样追溯

方括号内是archive.json中的claim ID。使用 `python -S -B scripts/task14_archive.py show --claim <ID>` 查看数值、原文件SHA/JSON pointer、逐题文件、参数、硬件及执行命令；experiments.csv为完整字段汇总，RESULTS_FINAL.md保留全部正负收益。
