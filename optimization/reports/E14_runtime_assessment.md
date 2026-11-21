# E14：正常入口的内存与初始化诊断

2026-11-21。运行模型、Prompt、检索参数及语料沿用 E13。只验证一个工程候选：门禁后延迟构造检索依赖。候选通过可信进程环境 `FOOTBALL_LAZY_RETRIEVAL=1` 启用，默认保持原行为。
对照执行版本 `3ee17ad54bb6dfe7b37133c12dd388a575fbeabc`，候选执行版本 `3ee17ad54bb6dfe7b37133c12dd388a575fbeabc`。分支仅保留本地。

**最终结论：** D036延迟初始化的局部收益与E13质量收益已验证；完整90题为54/72完整正确、18/18正确拒答、90/90技术完成。但10/90次采样内存余量低于1GiB，最低0.9135GiB，全量资源验收失败，候选默认关闭。

## 实测方法

默认Worker子进程及实际网页均顺序测D036、普通可答题、已有模型驻留后的D036、事实题关闭/开启E13补答。网页每次新建会话。目标等待间隔250毫秒，叠加进程采样耗时；系统可用内存及各进程RSS/private/native peak均由外部进程记录，每约1秒查询Ollama驻留模型。记录启动前、采样低点、退出后2秒，Worker内独立记录导入、环境/来源校验、依赖构造、回答及返回。外部采样依赖未安装进锁定262包Worker环境。
初轮原始记录完整保留。网页fact_A的显示断言误用了“证据”关键词，实际标准拒答是“现有资料不足以可靠回答”；那次显示核验计为测试断言失败，未据此认定模型或服务超时。修正测试后完整复测对照，再测候选；未删除或改写旧结果。

## 各入口实际结果

| 版本/入口 | 请求 | 回复秒 | 启动前GiB | 最低GiB | 退出后2秒GiB | Worker峰值RSS GiB | 低点最近Worker阶段 |
|---|---|---:|---:|---:|---:|---:|---|
| A/worker | D036_first | 11.53 | 5.580 | 3.404 | 5.598 | 2.147 | reranker_construction_start |
| A/worker | players | 33.17 | 5.594 | 1.081 | 3.365 | 2.286 | answer_model_start |
| A/worker | D036_resident | 12.60 | 3.367 | 1.100 | 3.386 | 2.283 | reranker_construction_start |
| A/worker | fact_A | 33.06 | 3.385 | 1.229 | 3.318 | 2.086 | answer_model_start |
| A/worker | fact_B | 33.09 | 3.319 | 1.211 | 3.449 | 2.096 | engine_construction_end |
| A/browser | D036_first | 13.28 | 3.024 | 0.950 | 2.943 | 2.266 | result_validation_start |
| A/browser | players | 34.48 | 2.951 | 1.015 | 3.111 | 2.104 | result_validation_start |
| A/browser | D036_resident | 13.15 | 3.109 | 1.126 | 3.096 | 2.061 | result_validation_start |
| A/browser | fact_A | 33.44 | 3.097 | 0.756 | 3.076 | 2.333 | result_validation_start |
| A/browser | fact_B | 34.65 | 3.075 | 1.149 | 3.212 | 2.439 | answer_model_start |
| B/worker | D036_first | 4.68 | 5.905 | 5.808 | 5.844 | 0.039 | result_validation_start |
| B/worker | players | 33.12 | 5.837 | 1.503 | 3.610 | 2.099 | answer_model_start |
| B/worker | D036_resident | 4.76 | 3.618 | 3.540 | 3.588 | 0.040 | result_validation_start |
| B/worker | fact_A | 32.35 | 3.589 | 1.542 | 3.597 | 2.072 | answer_model_start |
| B/worker | fact_B | 33.41 | 3.597 | 1.557 | 3.595 | 2.117 | reranker_construction_start |
| B/browser | D036_first | 5.58 | 3.184 | 3.104 | 3.137 | 0.039 | chat_identity_validation_start |
| B/browser | players | 35.36 | 3.137 | 1.143 | 3.506 | 2.362 | answer_model_start |
| B/browser | D036_resident | 4.79 | 3.648 | 3.669 | 3.667 | 0.039 | result_validation_start |
| B/browser | fact_A | 33.18 | 3.661 | 1.153 | 3.469 | 2.332 | result_validation_start |
| B/browser | fact_B | 34.81 | 3.479 | 1.105 | 3.322 | 2.092 | answer_model_start |

系统最低值受其他应用影响，A/B并非同一时刻，不能直接把可用内存差归为候选节省值；Worker独立RSS和阶段构造记录提供更直接的证据。RSS也不是独占物理内存，不能简单与系统可用内存相加。

## 拆分原先14.42秒的引擎外开销

| 版本 | 阶段 | 已测样本数 | 中位秒 |
|---|---|---:|---:|
| A | module_import | 10 | 0.1952 |
| A | source_environment_validation | 10 | 1.3161 |
| A | engine_module_import | 10 | 0.0163 |
| A | engine_construction | 10 | 7.5465 |
| A | retrieval_import | 10 | 0.0692 |
| A | bm25_construction | 10 | 1.6554 |
| A | dense_construction | 10 | 1.8932 |
| A | reranker_construction | 10 | 3.3289 |
| A | chat_identity_validation | 10 | 0.0949 |
| A | result_validation | 10 | 1.1931 |
| A | engine_close | 10 | 0.0765 |
| A | result_write | 10 | 0.0252 |
| B | module_import | 10 | 0.1808 |
| B | source_environment_validation | 10 | 1.2641 |
| B | engine_module_import | 10 | 0.0156 |
| B | engine_construction | 10 | 0.5015 |
| B | retrieval_import | 6 | 0.0671 |
| B | bm25_construction | 6 | 1.6130 |
| B | dense_construction | 6 | 2.0238 |
| B | reranker_construction | 6 | 3.2481 |
| B | chat_identity_validation | 10 | 0.0880 |
| B | lazy_retrieval_construction | 6 | 7.0578 |
| B | result_validation | 10 | 1.0478 |
| B | engine_close | 10 | 0.0703 |
| B | result_write | 10 | 0.0240 |

这些阶段有包含关系，不能全部求和。候选把重型构造移入通过门禁后的回答路径，不能只看引擎外时间变短就声称正常问答总耗时也减少；表中同时报告完整请求耗时。
初轮D036在3B驻留时零检索/零回答调用，Worker仍峰值约2.27GiB，可用内存最低0.813GiB，低点落在重排器构造内。因此选取延迟构造候选。保留索引快照、包版本、来源和模型身份校验；就绪检查仍完整构造检索依赖。正常请求通过门禁后使用原检索器、同一提示词和同一模型，不更改装配及选证。
普通请求低点及Ollama驻留快照见逐题JSON。1秒快照没有证明短暂模型重叠的能力；未确认重叠前不调整加载/卸载或单模型驻留配置。事实绑定阶段也单独计时，不能把共有的初始化峰值归因于E13。

## 验收与保留范围

候选10次请求的完整工程门禁：True。门槛为每次正常可见回复≤60秒且全程系统可用内存≥1GiB，同时核对业务行为。完整E13专项与90题是否执行分别在 `E14_metrics.json` 记录。
40题留出集未调用、未评分，全部冻结数据哈希一致；未调整并发、未合并或推送。E13事实补答和E14延迟构造均保持默认关闭。
本轮若普通可答题仍跌破资源门槛，下一轮应针对该请求的Worker峰值与重排器构造细分，不继续叠加常驻Worker等改动。驻留可能降低启动耗时但抬高空闲占用，需要独立实验。
复核文件：`optimization/reports/E14_metrics.json`；逐次完整结果与阶段事件在 `.runtime/phase2/e14-baseline01/`、`e14-baseline02/`、`e14-lazy01/`。


## 原E13专项复验与90题最终结果

工程10次复验通过后，已按原E13顺序完成26次Worker A/B及7项网页测试。六个候选事实问法全对、边界零错误补答、原正确对照无退化、新增引用均直接支持。未改写原E13报告。两组均使用E14延迟构造，仅事实补答开关不同。
专项资源门槛通过后，固定90题已全部通过真实默认Worker运行，正常网页服务与一个浏览器页面同时驻留。每题保留实际模型原输出、Prompt、检索结果、来源证明和资源采样。对照影子只从同一次模型响应恢复补答前状态，不是第二次独立模型运行，没有虚构影子耗时或调用成本。

| 指标 | 历史D036基线 | 本轮候选 | 同响应补答前影子 |
|---|---:|---:|---:|
| 可答题完整正确 | 51/72 | 54/72 | 51/72 |
| 正确拒答 | 18/18 | 18/18 | 18/18 |
| 技术完成 | 90/90 | 90/90 | 同一次模型响应 |
| 直接支持引用 | 72/118 | 75/123 | 72/120 |

实际补答题：D001, D002, T001。相对历史新增完整正确：D001, D002, T001；原完整正确题退化：无。逐题必要要点和引用审核记录见 `E14_live90_metrics.json`。沿用Codex已记录的相同问题及完整原文段集合审核；新组合另留原文复核账本，不是只按标注段ID命中计分，也不是新的专家或盲评。历史51/72来自Graph归档，本轮执行默认线性Worker；未据此宣布LangGraph路由和规划节点完成新一轮验收。

全量最长请求43.43秒，中位40.14秒；90/90次≤60秒。最低可用内存0.9135GiB，10/90次采样低于1GiB。实际回答模型调用86次，触发格式重试的题目0道，输入/输出Token合计112780/2154。

**最终决定：** 全量验收未通过。前置短专项的资源通过不能替代较长回归；质量与资源分别判定，不能因正确率提高宣布交付成功。
D036延迟构造的局部收益已复现；普通可答请求仍构造相同的检索与重排依赖，其峰值不能声称已被解决。未叠加常驻Worker、改变模型/索引参数或删除失败样本。两项候选开关默认关闭，分支保留本地。40题留出集继续封存。
采样目标等待250毫秒，实际还包含进程枚举与内存读取耗时；工程候选实测中位约0.411秒、最大约0.623秒。这里的“最低值”均为采样所见，不能排除采样间隙。1秒模型驻留快照未证明短暂重叠不存在。
本轮服务与浏览器已关闭，冻结数据哈希通过复核。归档验证：`E14_archive_verification.json`。

进程内存口径校正：原采样按PID缓存角色，Windows PID复用会使少量Worker被错误归入observer。已用实际回答阶段时间窗与Worker PID回放原始逐进程RSS，表中采用Worker主进程峰值（不含venv启动器），详见 `E14_process_memory_reconciliation.json`。原始采样未修改，系统可用内存及所有验收结论不受影响；后续采样缓存键已加入进程创建时间。
