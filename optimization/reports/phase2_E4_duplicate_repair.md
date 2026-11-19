# E4：重复 ID 解析可靠性修复

E4解析修复已验证；公共回归门禁未全部通过，本轮暂不进入E5。

实现提交：`790ba09c4f9b4f40a75e15695bc68a800bd31b56`；基线：`e8b0fd6bbdb70b1144d9a4e7f03d811da593b0f5`。独立本地分支 `optimization/phase2-e4`，未合并生产分支。Prompt 始终为 A，本轮未执行 E1 新 Prompt、E2、E3、E5 或检索参数修改。

## 根因与修改

根因位于冻结版 scripts/answer_eval_core.py:86：parse_selection 对重复 ID 直接抛错，合法来源被连同重复项一起丢弃；图最多两次重试仍可能重复失败。当前 normalize_chunk_ids 在该文件第82行，parse_selection 在第91行；图私有审计位于 scripts/rag_langgraph.py:219 的 answer 节点。offered_ids 来自 pack 实际装入 Prompt 的证据，并非完整检索 Top10。
共用解析器现在依次验证结构/类型、非空精确 ID 和实际提供范围，稳定去重并保留第一次出现的顺序；原始数组与规范化结果仍各自最多3项。原始4项即使去重后只有1项也拒绝，不放宽原 Schema 数量上限。未知、未提供、空白、非字符串标识均拒绝；不修剪或猜测 ID。
生产修改仅 scripts/answer_eval_core.py 和 scripts/rag_langgraph.py。图新增私有 selection_audits：保存原始 response 与 normalized_selection；原 attempts 公开投影字段不变。线性 Worker 原有 response＋parsed 日志直接保存原始/规范化双份结果，validate_attempts 回放仍通过。JSON Schema、Prompt、模型、重试上限、来源校验和正文哈希校验均保持。

## 专项与机制测试

32项专项：32/32；原25项机制：25/25。其中重复项由原先预期重试2次改为预期1次稳定去重，其余机制预期保持。

|检查|结果|
|---|---|
|normal_ids_unchanged|PASS|
|legal_duplicates_stable_order|PASS|
|all_duplicates_one_id|PASS|
|raw_object_not_mutated|PASS|
|unknown_id|PASS|
|empty_id|PASS|
|whitespace_id|PASS|
|nonstring_id|PASS|
|null_id|PASS|
|bool_id|PASS|
|list_type|PASS|
|too_many_distinct|PASS|
|too_many_raw_even_if_duplicates|PASS|
|empty_answer|PASS|
|unknown_field|PASS|
|wrong_answerable_type|PASS|
|non_null_answer_reason|PASS|
|refusal_cannot_select|PASS|
|retrieved_but_not_offered_rejected|PASS|
|no_trimming_of_source_ids|PASS|
|controlled_refusal_unchanged|PASS|
|malformed_json|PASS|
|not_object|PASS|
|missing_field|PASS|
|two_duplicate_responses_stop_after_first|PASS|
|second_duplicate_response_not_requested|PASS|
|unknown_ids_retries_stop_at_two|PASS|
|source_mismatch_after_normalization_rejected|PASS|
|body_hash_mismatch_before_generation_rejected|PASS|
|source_conflict_still_refuses|PASS|
|D016_original_graph_and_linear_replay|PASS|
|D010_B_first_response_original_graph_and_linear_replay|PASS|

D016 与 D010-B 的原始首答都经真实 Flow 和线性请求适配器回放：一次调用后稳定去重，第二个已排队的重复响应未被请求。这里是历史响应回放，真实 Qwen 验证见下一节。最初离线回放测试适配器遗漏融合候选，导致2项测试失败；修正测试适配器后32项通过，失败记录保留，生产修复没有因此扩大范围。

## 固定旧响应：隔离 E4 的效果

使用冻结90题相同问题、候选、实际上下文及模型原始响应，通过当前完整图重放；没有新增真实模型请求。唯一改变结果的题为 D016：failed → answered，选择 L13-05、L17-01。其余89题的状态、答案、引用和拒答原因逐项一致。这证明不含重复的正常响应没有被改选。

|指标|冻结基线|固定旧响应＋E4|真实完整图＋E4|
|---|---:|---:|---:|
|可答题完整正确率|50/72（69.44%）|51/72（70.83%）|51/72（70.83%）|
|整体正确率|68/90（75.56%）|69/90（76.67%）|68/90（75.56%）|
|正确拒答率|18/18（100.00%）|18/18（100.00%）|17/18（94.44%）|
|错误拒答率|10/72（13.89%）|10/72（13.89%）|11/72（15.28%）|
|引用支持率|70/116（60.34%）|72/118（61.02%）|73/117（62.39%）|
|要点覆盖率|132/172（76.74%）|134/172（77.91%）|134/172（77.91%）|
|技术完成率|89/90（98.89%）|90/90（100.00%）|90/90（100.00%）|
|合法重复输出解析恢复率|0/2（0.00%）|1/1（100.00%）|1/1（100.00%）|
|解析失败输出比例|2/88（2.27%）|0/87（0.00%）|0/87（0.00%）|

历史22道失分题专项：固定旧响应完整恢复1/22（D016）；真实回归完整恢复2/22（D016、T014）。T014本轮模型选对来源，旧解析器同样接受，不计为去重的直接收益。18道无答案题真实结果17/18，失败题为D036。
重复恢复率的分母随重试消除而变化：原D016两次重复均失败（0/2）；修复后首答即成功并停止（1/1），没有为了凑样本继续生成。
回放列的模型调用/Token 是所采用历史响应的记账，回放本身没有发出这些请求；不可把回放耗时当真实推理延迟。真实回归重新执行检索、重排、生成、引用检查与图收尾。历史22题和18道无答案题均为90题子集，没有加进分母。正确率与引用评分由 Codex 核验原文，沿用逐字一致或已审阅的相同来源组合；新增来源组合单独核验。没有新增人工/专家审核，也没有使用新留出集。

|成本与性能|冻结基线|固定响应记账|真实完整图＋E4|
|---|---:|---:|---:|
|生成请求（含重试）|88|87|87|
|额外重试次数|1|0|0|
|输入Token|115332|114026|114026|
|输出Token|2193|2158|2151|
|图端到端P50（秒）|16.479|不适用|16.548|
|图端到端P95（秒）|19.332|不适用|18.759|

端到端分位数按90题 Flow.invoke 计时，包含版本直接拒答；真实回归一次独立预热不计入题目Token和分位数。D016、D010排在前两题用于真实专项验证，其余按题号运行，合计90个唯一题目。线性浏览器耗时单列，不与图混算。与历史单轮耗时比较受执行顺序、机器负载及模型运行波动影响，不把所有差异归因于去重。

## 真实模型专项与归因

### D016

真实调用 1 次，状态 answered，选择 ['L13-05', 'L17-01']。

原始输出：
```json
{"answerable":true,"chunk_ids":["L13-05","L17-01","L17-01"],"reason":null}
```
规范化输出：
```json
{"answerable": true, "chunk_ids": ["L13-05", "L17-01"], "reason": null}
```

### D010

真实调用 1 次，状态 answered，选择 ['L08B-02']。

原始输出：
```json
{"answerable":true,"chunk_ids":["L08B-02"],"reason":null}
```
规范化输出：
```json
{"answerable": true, "chunk_ids": ["L08B-02"], "reason": null}
```

本轮对同一实际响应的新旧解析器比较：正常合法响应 86/86（100.00%） 等价；合法重复响应恢复率 1/1（100.00%）。D016真实重复被恢复；D010本轮若无重复，只能证明正常请求通过，其重复首答路径由历史D010-B响应回放验证，未启用B Prompt。

真实已回答结果的原文/引用完整性：62/62（100.00%）；篡改正文、来源不匹配和未知ID仍由受控测试证明拒绝。线上没有未知ID样本时，不伪造线上未知ID拒绝率。

真实回归与冻结基线结果不同的题号：D009,D016,D023,D027,D036,T005,T014,T016,T036。只有D016的改变在固定响应控制实验中能归因于E4。D036本轮返回依赛事而定的原文，旧解析器同样接受该响应，仍按must_refuse契约失败计分；没有改标签或将其描述为编造停赛数字。其他题的模型选段变化独立保留，不作为解析修复收益。

## 浏览器门禁

采集 8/8，验证通过 8/8。

|轮次|问题|结果|来源|
|---|---|---|---|
|1|请按这份知识库说明，球门开口通常有多宽、多高？|PASS|L01-03|
|2|把刚才的答案整理成表格|PASS|L01-03|
|3|把上一轮回答列成要点|PASS|L01-03|
|4|刚才的答案引用了哪些来源？|PASS|L01-03|
|5|那它的高度呢？|PASS|L01-03|
|6|换个话题，按资料说明普通场上队员能否戴手套，并列出可核对的来源。|PASS|L04-05|
|7|按资料说明普通场上队员能否戴手套，并列出可核对的来源。|PASS|L04-05|
|8|把刚才的答案整理成表格|PASS|无|

表格、要点、来源追问须精确复用本会话原始来源且不调用Worker；代词追问须正确改写并选择支持段；话题切换和新会话不得污染。采集完成不等于通过。如出现选证错误，原样记录，不以E4名义改历史机制或Prompt。

## 结论与下一步边界

E4解析修复已验证；公共回归门禁未全部通过，本轮暂不进入E5。
正确拒答目标为至少95%，本轮为17/18（94.44%），仍有D036失败。该题的业务拒答契约与条件性原文回答保留待后续审计，本轮没有重标或降低验收标准。
E4只修复可确定性恢复的重复标识，不能解决有证据却拒答、主题相近却选错、复合问题漏答或T034上下文遗漏。本轮没有执行E5；是否进入下一项按上述实际门禁决定，不能用解析成功替代语义质量。

冻结源码223项中，只有明确授权的2个生产源文件改变；另221项、8个数据文件、A Prompt及4个封存数据集哈希保持。新40题留出集仍待人工审核，本轮未用于调参、计分或模型请求。

完整逐题指标、原始/规范化输出、源文件及数据哈希保存在伴随JSON及本机私有 .runtime/phase2/e4-live90。
