# 回答、引用和拒答评测

## 固定输入和系统

原任务十二依据见DEVELOPMENT_PLAN_AND_REPORT.md；本轮边界见TASK_12_SCOPE.md。任务四原始90条标签与人工批准凭证不改，dev40（可回答32/必须拒答8），test50（可回答40/必须拒答10）。测试集在前序任务已经使用，本次是复用锁集的新回答实验，不是未见留出集。

检索采用任务十在开发集选择的top40：BGE-M3固定模型、原99段、原Chroma和title_body BM25索引、Dense80+BM2580、RRF k60、BAAI/bge-reranker-base固定revision 2cfc18c9415c912f9d8155881c133215df768a70、FP32 ONNX、CPU8/batch8/max512。任务十一父子块的测试结果没有用于重选本轮参数。

回答与自动评分均固定qwen2.5:3b，digest 357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b，Ollama0.40.16、temperature0/seed42/CPU8、num_ctx8192、num_predict1024。全部messages序列化后6200 UTF-8字节上限，模板预留512；完整输入和输出计数保留。字节预算是保守上界，不宣称等于精确模型token数。

新AnswerEngine与原RagB0Engine隔离。取前5候选，按整段预算选择，不能截断条件和表格；模型最多选3个实际提供的ID。程序逐字展示整段，并从冻结元数据生成引用、规则编号、行号、修订ID、许可/署名和校核提示；统一提示非官方/非专家审校/历史修订未核验。模型不编写最终规则正文或来源URL。这是保守的摘录回答配置，可能冗长或答非所问；引用真实并不保证回答问题。

旧RAG B0问答/界面/提示不改，任务六已有实跑记录作为输入可运行性依据。本次只有一个新系统的正式质量结果，没有重测旧B0的答案基线；不得写成Rerank单变量带来的回答提升。集成当前页面属于任务13。

## 五项指标及分母

| 指标 | 判定单位 | 分母与失败处理 |
| --- | --- | --- |
| 答案要点覆盖率 | 标签的每个expected_answer_point在实际回答中是否语义正确表达 | 全部可回答题要点总数；拒答/漏答计未覆盖 |
| 引用正确率 | 每个实际引用是否支持所展示规则结论且直接回答问题的一部分 | 实际引用总数；无引用时null；相似话题、错误条件/编号/版本不能算正确 |
| 条件/例外保留率 | 每个required_condition是否完整表达 | 标签条件总数；拒答或省略计未保留 |
| 正确拒答率 | 原标签不可回答且实际受控拒答、无运行错误 | 原不可回答题数；运行失败不奖励为正确拒答 |
| 错误拒答率 | 原标签可回答但实际拒答（含运行失败） | 原可回答题数；运行错误另列 |

对于实际作答的样本，前三项由固定小模型在**所有回答先封存之后**自动语义评分，逐项布尔向量、理由、原始请求/响应都保留。实际拒答没有展示规则要点或引用，确定性计未覆盖，不再请求评分模型；后两项由冻结answerable标签与实际输出状态确定。通过Ollama JSON Schema约束回答/拒答分支、实际提供的ID、评分布尔数组长度及必填理由；应用层仍验证，不能只相信约束。最多2次格式尝试，失败不虚构分数，自动向量全false并单列judge_errors。全false只代表未取得可用正面评分，不能解释成已证明全部错误。

回答模型和评分模型相同，存在自我偏好、共同误判及小模型能力限制。前三项必须称**AI自动评分**，不得作为人工准确率或专家规则正确率。来源逐字一致/哈希/URL/行号检查是独立机械契约，不能替代引用相关性评审。额外字面命中只做诊断；同义表达可能无法字面匹配，不能用它作为语义结论。没有人工新判定时human_semantic_metrics为null、人审样本数0。

## 人工判定方法

`human_review_sample.json`在test完成后确定12题：优先错误拒答、资料外误答、不支持引用和缺失条件，然后按题号排序补足。不按有利成绩挑样。记录每题实际answer SHA及私有原始记录SHA，不能用旧标签人审批准代替这些新回答的审核。

本机`.runtime/task12/human_review.html`包含12题完整问答、来源和原标签；`.runtime/task12/test/answers/`包含全部50题完整问答。人工逐项读取问题、实际答案和原段：

1. 对照每个要点与条件，特别检查否定、数值、单位、适用对象、例外与多部分问题。
2. 对每个引用判“支持且相关/不支持或不相关/无法判定”，不能只看URL存在。检查规则编号、行号、版本和校核提示没有被升级为官方结论。
3. 单独判应否拒答；证据冲突或需要未核验版本时不能强行择一；有明确支持的一般资料问题不应因非官方边界而全拒答。
4. 记录逐项判断、问题号、answer SHA、审阅者、时间和具体理由；不确定项交二次审阅。核对差异后才生成单独人工统计，人审样本分母与全50题AI统计分开。

当前交付不生成虚假的human记录。已有90条标签人工批准凭证仅证明标签曾被批准，不证明译文已获裁判审校，也不证明新回答正确。任何后续实际人审以新增回执保存，不覆盖本轮AI报告或原人审账本。

需要记录实际人审时，运行`.venv/Scripts/python.exe -B scripts/serve_answer_review.py --port 7864`并打开`http://127.0.0.1:7864/`。每个要点、条件和引用须明确选是/否/无法判定，填写理由后逐题提交；没有预选或自动全部批准。新增真实人工账本只写`.runtime/task12/human_answer_reviews.jsonl`，姓名/备注不公开。封存AI报告和抽样记录仍保持生成时的人审0状态，后续实际人审须单独发布补充结果。

## 使用和复算

本仓库当前formal dev/test目录均为已运行证据。下列开发/授权/正式测试命令说明实际流程，**不能在已有目录删除证据后重复正式test**：

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv/Scripts/python.exe -B scripts/verify_answer_evaluation.py --report reports/answer_evaluation/acceptance/new-contract.json
.venv/Scripts/python.exe -B scripts/run_answer_evaluation.py dev
# commit开发结果，再生成并commit test_authorization.json
.venv/Scripts/python.exe -B scripts/run_answer_evaluation.py prepare-test
.venv/Scripts/python.exe -B scripts/run_answer_evaluation.py test
.venv/Scripts/python.exe -B scripts/run_answer_evaluation.py export
```

公开仓库已含逐题问题/来源元数据/回答SHA/自动判定/全部五项分子分母。无模型、无全文的复算（需要完整Git历史检查生产提交；report必须是新路径）：

```powershell
python -S -B scripts/run_answer_evaluation.py replay
python -S -B scripts/verify_answer_public.py --complete --report reports/answer_evaluation/acceptance/new-public.json
python -S -B scripts/verify_answer_delivery.py --public-only --complete --report reports/answer_evaluation/acceptance/new-delivery.json
```

本机完整门禁用`.venv/Scripts/python.exe -B scripts/verify_answer_delivery.py --complete --report <新路径>`，核对私有完整答案、证据原段、实际模型输出、评分原文和旧索引/语料/人审账本。公开副本无法重新证明私有推理发生或重新判定语义，只能独立复算公开投影、输入身份和判定向量；完整记录的SHA供本机审查。

`verify_answer_release.py`是**发布前本机门禁**，要求发布前快照中的20标签仍是全部旧标签；创建本轮新标签后不应重复把它当作当前门禁。发布后复验使用上述delivery或public入口。任务十一等历史门禁带当时累计实验数要求，应在各自原标签独立checkout使用；当前累计交付保全以本轮门禁为准。

四种独立探针通过`run_answer_probes.py --report <新路径>`执行：真实资料外问答、官方版本请求、D001真实难负例单独提供，以及明确标注为合成的同版本来源冲突。探针不进入90题质量分母。原失败记录在dev-before-warmup、dev-before-id-fix保留：环境观测需先加载Embedding，规则ID还包含L08A/L08B；开发中明确了普通资料问答与官方版本确认的区别。没有修改原标签和原Corpus。

## 交付入口

正式汇总：`reports/answer_quality_results.json`。逐题公开投影：`reports/answer_evaluation/{dev,test}/predictions.jsonl`及`judgments.jsonl`；每题评分与错误：`summary.json`和`error_analysis.json`。公开不包含原规则全文、完整回答或模型原始长文本；完整问答与证据位于本机`.runtime/task12/{dev,test}/answers`和`judges`，人审页面同目录。新结果、已知错误及交付检查见`reports/TASK_12_DELIVERY.md`。
