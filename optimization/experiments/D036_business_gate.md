# D036 确定性拒答门禁修复与90题回归

验收判定：**PASS_D036_GATE**。实现提交：`86a01e938067f89bcc7dbbb1524d7e53426116f4`。对照是A1/E4的真实90题，当前候选仅加入缺参累计黄牌处罚查询的运行时业务判断。

该通过仅限用户指定的缺参拒答验收：真实新调用中T014正确→错误，引用支持率62.39%→61.02%；T005由误拒答恢复正确，不能据完整正确数仍为51/72宣称逐题零退化。整体质量仍有未通过的验收项，当前分支不合并、不推送。

## 规则与接口

scripts/disciplinary_query_policy.py由图和默认线性Worker共用。在有效问题完成输入校验、入口已有历史改写之后，判断跨场累计黄牌＋索要具体停赛场数＋缺赛事或赛季；命中即在检索和回答模型前返回refused，提示补充缺失项。
一般原因解释、同场纪律问题、参数齐全和意图不明确的问题继续原流程。参数齐全不代表资料足以回答某赛季处罚，仍由原检索/生成链路决定。识别覆盖本次35个中文边界用例及常见明确赛事名称、年份/赛季范围、显式赛事标签；不声称覆盖所有自然语言表达。
公开refusal_reason仍用已有insufficient_evidence；私有business_decision记录规则、意图、缺失字段和已识别参数。校验器按有效问题重算业务决定，并严格绑定提示、零检索和零模型调用。没有扩展公开字段集合；同步纳入源文件版本校验。来源哈希、引用渲染和最多两次回答模型调用仍保留。

## 三关验收

|检查|结果|
|---|---|
|boundary|PASS|
|parser|PASS|
|mechanisms|PASS|
|A1_control_replay|PASS|
|worker_boundaries|PASS|
|browser|PASS|
|correct_refusal_18_of_18|PASS|
|complete_at_least_51|PASS|
|technical_90_of_90|PASS|
|no_new_false_refusals|PASS|

双入口边界84/84；E4解析32/32；机制25/25。边界用例、Worker与浏览器场景独立记录，不计入原90题分母。

A0拒答响应与E4选择L12-09响应分别回放到两个入口，均在回答模型前结束、原响应未消费。A1全部90题控制回放只有D036状态/提示改变，其他89题状态、选段、引用、全文及原因完全一致。回放本身没有真实模型请求，其耗时不能当成在线推理延迟。

## 同一固定90题指标

|指标|A1/E4实测|固定A1响应控制回放|候选真实推理|
|---|---:|---:|---:|
|可答完整正确|51/72（70.83%）|51/72（70.83%）|51/72（70.83%）|
|整体正确|68/90（75.56%）|69/90（76.67%）|69/90（76.67%）|
|正确拒答|17/18（94.44%）|18/18（100.00%）|18/18（100.00%）|
|错误拒答|11/72（15.28%）|11/72（15.28%）|10/72（13.89%）|
|技术完成|90/90（100.00%）|90/90（100.00%）|90/90（100.00%）|
|引用支持|73/117（62.39%）|73/116（62.93%）|72/118（61.02%）|
|必要要点覆盖|134/172（77.91%）|134/172（77.91%）|134/172（77.91%）|
|模型调用|87|86（历史响应记账）|86|
|输入Token|114026|112780（历史响应记账）|112780|
|输出Token|2151|2130（历史响应记账）|2140|

候选实际Graph延迟：P50=16.248s，P95=18.261s；A1分别为16.548s、18.759s。均按90次Flow调用计，包含前置拒答；预热排除。不同轮次的负载与模型状态影响比较，不宣称稳定加速。

## 逐题得失与新增误拒答

改善题：D036,T005。退化题：T014。新增可答题误拒答：无。

首个实际回答请求的消息和Schema与A1逐字一致：86题。固定响应控制中仅D036变化；真实新调用中其余选段差异必须作为模型决策变化另列，不能统算为规则收益。

评分保持冻结口径：D009本轮结果逐字复现A0，沿用A0的引用审核掩码，仅计L08A-02；没有因其他实验中不同选段组合的审核记录而重标本次输出。全部新组合/复用依据在source_reviews.tsv，既有冻结标签未修改。

|题号|A1|候选|候选选段|规则命中|
|---|---|---|---|---|
|D001|false_refusal|false_refusal|无|否|
|D002|false_refusal|false_refusal|无|否|
|D003|false_refusal|false_refusal|无|否|
|D004|correct|correct|L03-01|否|
|D005|correct|correct|L04-01|否|
|D006|correct|correct|L12-14|否|
|D007|correct|correct|L06-02|否|
|D008|correct|correct|L07-01|否|
|D009|correct|correct|L08A-02,L01-07|否|
|D010|correct|correct|L08B-02|否|
|D011|incorrect|incorrect|L09-03|否|
|D012|false_refusal|false_refusal|无|否|
|D013|correct|correct|L11-01,L11-03,L12-05|否|
|D014|correct|correct|L12-04|否|
|D015|correct|correct|L15-05|否|
|D016|correct|correct|L13-05,L17-01|否|
|D017|correct|correct|L14-02|否|
|D018|correct|correct|L15-01,L16-01,L16-04|否|
|D019|incorrect|incorrect|L16-04,L17-04,L08B-02|否|
|D020|correct|correct|L17-01,L16-01,L16-02|否|
|D021|partial|partial|L11-03,L12-05,L15-03|否|
|D022|correct|correct|L16-03,L17-04,L17-05|否|
|D023|correct|correct|L12-11,L12-01,L12-12|否|
|D024|correct|correct|L09-04|否|
|D025|correct|correct|L04-01|否|
|D026|partial|partial|L10-02|否|
|D027|correct|correct|L09-02,L08B-04,L14-04|否|
|D028|correct|correct|L05-01|否|
|D029|correct|correct|L08A-01|否|
|D030|correct|correct|L12-10,L03-01,L12-12|否|
|D031|correct|correct|L02-01|否|
|D032|false_refusal|false_refusal|无|否|
|D033|correct_refusal|correct_refusal|无|否|
|D034|correct_refusal|correct_refusal|无|否|
|D035|correct_refusal|correct_refusal|无|否|
|D036|incorrect|correct_refusal|无|是|
|D037|correct_refusal|correct_refusal|无|否|
|D038|correct_refusal|correct_refusal|无|否|
|D039|correct_refusal|correct_refusal|无|否|
|D040|correct_refusal|correct_refusal|无|否|
|T001|false_refusal|false_refusal|无|否|
|T002|correct|correct|L01-02,L17-03,L01-07|否|
|T003|correct|correct|L01-01,L14-02,L16-03|否|
|T004|partial|partial|L14-02|否|
|T005|false_refusal|correct|L03-01|否|
|T006|correct|correct|L03-04|否|
|T007|correct|correct|L04-05,L03-02,L11-03|否|
|T008|correct|correct|L04-02|否|
|T009|false_refusal|false_refusal|无|否|
|T010|correct|correct|L05-04,L12-15,L12-16|否|
|T011|correct|correct|L05-03|否|
|T012|correct|correct|L06-01,L03-04,L06-06|否|
|T013|correct|correct|L06-04,L07-01,L06-02|否|
|T014|correct|incorrect|L06-05,L06-04,L03-04|否|
|T015|false_refusal|false_refusal|无|否|
|T016|correct|correct|L07-01,L06-04,L14-03|否|
|T017|false_refusal|false_refusal|无|否|
|T018|incorrect|incorrect|L17-05|否|
|T019|correct|correct|L08B-03,L17-06,L17-04|否|
|T020|correct|correct|L08B-04|否|
|T021|correct|correct|L09-02,L15-01,L16-01|否|
|T022|correct|correct|L15-01,L16-01,L17-06|否|
|T023|partial|partial|L07-03|否|
|T024|correct|correct|L11-06|否|
|T025|correct|correct|L11-09,L03-04,L12-08|否|
|T026|partial|partial|L12-01,L12-02,L12-15|否|
|T027|correct|correct|L12-07,L12-11|否|
|T028|incorrect|incorrect|L12-02|否|
|T029|correct|correct|L13-02,L16-02,L13-05|否|
|T030|correct|correct|L01-05,L13-01,L13-05|否|
|T031|correct|correct|L13-07|否|
|T032|partial|partial|L14-05|否|
|T033|correct|correct|L14-03|否|
|T034|false_refusal|false_refusal|无|否|
|T035|correct|correct|L15-02|否|
|T036|correct|correct|L15-04,L15-01,L15-02|否|
|T037|correct|correct|L16-04|否|
|T038|correct|correct|L16-02,L17-01,L16-03|否|
|T039|correct|correct|L17-03,L01-07|否|
|T040|correct|correct|L17-05|否|
|T041|correct_refusal|correct_refusal|无|否|
|T042|correct_refusal|correct_refusal|无|否|
|T043|correct_refusal|correct_refusal|无|否|
|T044|correct_refusal|correct_refusal|无|否|
|T045|correct_refusal|correct_refusal|无|否|
|T046|correct_refusal|correct_refusal|无|否|
|T047|correct_refusal|correct_refusal|无|否|
|T048|correct_refusal|correct_refusal|无|否|
|T049|correct_refusal|correct_refusal|无|否|
|T050|correct_refusal|correct_refusal|无|否|

## 默认Worker、多轮和浏览器

|场景|最终状态|回答模型调用|业务门禁|边界结果|
|---|---|---:|---|---|
|missing_both|refused|0|命中|True|
|missing_season|refused|0|命中|True|
|missing_competition|refused|0|命中|True|
|complete_parameters|refused|1|未命中|True|
|general_explanation|refused|1|未命中|True|
|same_match|answered|1|未命中|True|
|history_parameters|refused|1|未命中|True|

非门禁场景最终是否答对另行观察：{"general_explanation": false, "same_match": true}。一般解释若仍被原模型拒答，表示现有选证/生成问题尚存；没有通过本规则强制它回答，也不以边界放行冒充语义正确。
真实多轮记录保留original question、effective query、query_resolution与Worker trace；只有历史参数确实进入有效请求，才按参数齐全处理。该专项不代表任意长会话参数持久化或记忆功能。
首次Worker多轮探针发现既有改写器返回unchanged，丢失上轮明确的赛事/赛季；初始失败保留在d036-gate-live-worker.json。最终修复只为该意图从近期用户问题继承显式参数，不从助手回答取事实，遇新话题或无关主题停止；复测见d036-gate-live-worker-v2.json。历史解析自身可能调用既有改写模型，本文“0次”指命中门禁后回答模型调用为0；单轮缺参场景没有历史改写调用。
浏览器实际采集9场景，9项通过；包含原有8场景及新增缺参处罚查询。核验会话隔离、历史格式化零Worker、问题改写、切换主题、实际页面补参提示和零回答调用。浏览器/Worker延迟单列，不并入Graph P95。

## 完整性、成本与适用边界

Prompt A、原语料、索引清单、固定90题与新40题留出集字节未变。未调用留出集进行计分，答案质量沿用既有Codex原文核验及单独记录的新来源组合审核；无新增人工或裁判专家审核。Top-K、Embedding、Chunk Size没有调整。
正式统计只使用完成并封存completed.json的最终90题。调试阶段的未完成短跑保留在d036-gate-live90和d036-gate-live90-v2，因补齐同场与泛称联赛边界而停止；不与最终轮次拼接或选择性抽题。单独预热、Worker、浏览器和未完成请求不并入90题Token；未完成请求的Token无法完整核算。首次旧PowerShell启动失败发生在正式推理前，后改用PowerShell7。
PASS_D036_GATE仅表示本轮缺参处罚拒答规则通过指定验收，不等于整体RAG质量已达到生产门槛。当前分支本地保留，未合并或推送。

复算：先用score_experiments.py对d036-gate-live90-final与replay90-final的score-dev/score-test、当前source_reviews.tsv计分，再运行optimization/summarize_d036_gate.py --out <输出目录>。原始逐题Prompt、通道/精排结果、模型响应、业务决定与图事件位于.runtime/phase2/d036-gate-live90-final。
