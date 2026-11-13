# 报告阅读说明

最新任务九见[TASK_09_DELIVERY](TASK_09_DELIVERY.md)及[hybrid_rrf_results.json](hybrid_rrf_results.json)。retrieval/hybrid_rrf_b0保存双路原始排名/分数/计时、四方法输出、开发案例和测试聚合；完整30/30、专项56/56、实际双路17/17、公开副本7/7通过，原任务八35/35复验。正式RRF的Recall@5/10与BM25持平、MRR低0.0325；负收益保留，没有新检索原测试题或生成答案。

任务七最新重新交付见[TASK_07_SUPPLEMENT](TASK_07_SUPPLEMENT.md)：7组缺陷修复，新证据rechecks/task7-audit-20261112，真实开发记录retrieval/task7-audit-20261112/dev。原任务七所有证据维持原字节。最终依据acceptance/task7-delivery-final.json（43/43）、supplement-final-v2.json（61/61）、contract-final.json（110/110）、replay-final.json（113/113）、public-only-replay.json（三组无模型复算）。中间55/59/112等结果保留其当时范围；v2仅澄清底层会重放原测试记录但不发新请求，不把字段read混同为exposed。

任务七当前交付：[TASK_07_DELIVERY](TASK_07_DELIVERY.md)。retrieval/dense_b0/dev与test保存真实逐题Top10、3次计时、run manifest、汇总和错误分析；acceptance/task7_delivery_gate.json为43/43。54项算术、110项合同与113项开发期回归均为程序验证，不能当成绩样本。test_authorization.json与test_usage.jsonl绑定开发完成→代码/配置冻结→一次正式测试；旧测试锁清单未改。

锁定测试可回答40/50，Recall@5/10=38/40=95%，MRR@10=0.8604167；延迟150次，P50/P95=270.18/312.82ms。public-only-replay.json记录无私有语料/模型/索引、Python -S禁用第三方包的真实独立复算。contract-before-fix.json为开发期100/101 FAIL（曾允许额外全文字段），修复后的110/110和实际预测均不含全文；arithmetic.json保留最初无producer SHA的旧合成回执，正式凭证绑定arithmetic-final.json。

任务四至六最新补审：[TASK_04_06_SUPPLEMENT](TASK_04_06_SUPPLEMENT.md)。修复前18个检查中16个为隔离实际复现、2个为代码判断问题；不冒充线上故障。新证据在rechecks/task456-20261112：original/为任务四五原验收，final/为最终58项边界回归与新smoke/真实UI。acceptance/regressions-first.json为先前55项历史结果，不能当作最终代码证明；final/acceptance/task6_portability_regression.json重放旧记录验证工具可移植性，不能代替新页面。原任务交付报告与旧证据不覆盖。

任务四、五最新补审：[TASK_04_05_SUPPLEMENT](TASK_04_05_SUPPLEMENT.md)。修复前6组复现保留在acceptance/task45_before_fixes.json；全部新验收在rechecks/task45-20261111，不覆盖旧交付/评测记录。39项新回归与原26项/24项门禁分别记录。只读audit_remote_delivery.py检查远程文件树和公开清单哈希。

任务五当前交付见[TASK_05_DELIVERY](TASK_05_DELIVERY.md)：acceptance/task5_delivery_gate.json为24/24 PASS、18种错误拒绝；evidence/task5_dense_smoke.json只含非评测示例ID/分数和来源摘要，task5_hardware.json记录真实CPU环境。task5_before_runtime_fix.json保留首轮兼容失败；没有正式Recall/MRR或模型回答成绩。

这里同时保留原工程历史交付和后续公开 checkout 实测。根目录下原任务报告是历史证据；当前各轮结果在 `acceptance/` 与 `evidence/`，不能混淆运行范围。

- 任务一二：TASK_01_02_DELIVERY.md、TASK_01_02_RECHECK_2026-11-11.md、task1_task2_after-task3.json。
- 问答引用修复：ANSWER_QUALITY_FIX_2026-11-11.md、answer-quality-contract-verification-2026-11-11.json、answer-quality-ui-verification-2026-11-11.json。
- 任务三：TASK_03_DELIVERY.md、task3_dataset_validation.json、task3_delivery_verification.json。
- 实验与简历证据：all_experiments_summary.csv、resume_evidence.md。
- 公开文件与原始哈希：PUBLICATION_MANIFEST.json。

原活动日志、会话记录、截图、账号凭据、数据库和完整语料不公开。因此部分原报告引用的文件只在原工程存在，不能据此声称公开仓库包含全部运行状态。原报告按字节保存；本机绝对路径是历史记录，不是新目录安装命令。

## 后续补交付的实测证据

`TASK_01_03_REDELIVERY.md` 是当前逐项交付报告；`acceptance/` 保存本轮实际重跑结果，`evidence/` 保存当前服务/启动证据、代码对应关系及明确标注为历史的 UI 三问摘要。

最初服务未运行导致的 31/32 失败也保留在 `evidence/task1_task2_before_service_restart.json`，恢复后的 32/32 在 `acceptance/task1_task2_recheck.json`。后端开发回归的16/16不作为独立测试集准确率。

`PUBLICATION_MANIFEST.json` 是首次 Git 导入快照，保留当时字节；当前文件覆盖以 `data/manifests/project_file_manifest.json` 为准，不能把历史快照当作实时清单。

## 最新缺陷关闭证据

- `acceptance/fresh_delivery.json`：独立环境、冻结数据、普通账号五份资料、新 UI 三问和服务检查，33/33。
- `evidence/fresh_ui_three_questions.json`：本轮浏览器三问摘要、时间、答案哈希及来源；完整 DOM/回答不公开。
- `evidence/fresh_database_initial.json`：新库初始化时仅有 admin、零资料；后续普通账号自行上传。
- `evidence/fresh_runtime_installation.json`：独立安装范围、真实失败原因与成功日志哈希，完整日志留本机。
- `acceptance/task3_fresh_environment.json`：新环境执行未改动的任务三 suite。
- `acceptance/fresh_answer_quality_contract.json`：新环境 19 项引用契约。

旧的 `task123_recheck_summary.json`、代码对应关系和历史 UI 文件保留原范围，当前不再用“新旧启动代码相同”作为通过条件；本轮运行覆盖层有实际修复，当前代码哈希见 fresh_delivery。

## 任务四候选与门禁

最新任务四已按原标准交付：`acceptance/task4_delivery_gate.json`为26/26 PASS、真实人工90/90；`task4_human_release_verification.json`为15/15 PASS；`evidence/task4_human_review_ui.json`为已封存只读页面证据。去姓名/备注人工凭证在`data/eval/human_review_receipt.json`。先看`TASK_04_DELIVERY.md`顶部当前结论，以下为早期阶段说明。

`TASK_04_DELIVERY.md` 保留候选准备及后续授权签收过程。`acceptance/task4_structure.json` 和 `task4_workflow_verification.json` 是自动检查通过；早期人工0/90、测试未冻结的失败已另存`task4_candidate_gate_historical.json`。不要把自动PASS或合成指标/签名当作人工评测集完成。`task4_corpus_regression.json`为原数据独立回归。

以上为原候选阶段。用户随后授权90题批量通过，当前按负责人模式批准并冻结：`task4_owner_acceptance.json`、`task4_owner_workflow_verification.json`。原逐题人工门禁仍23/26未通过，保存为 `task4_original_human_gate_after_owner_approval.json`；已有2条真实人工记录保留，批量批准不冒充逐题人工gold。


## 任务六正式交付

- TASK_06_DELIVERY.md：原标准逐项核对、实际失败/修复、62/62及前序回归结果。
- acceptance/task6_delivery_gate.json：真实生成/页面、应用输出合同、故障和冻结输入保全62项通过。
- evidence/rag_b0_smoke_manifest.json、rag_b0_ui_manifest.json：后端与真实页面分别3条可回答+1条拒答，公开元数据及私有完整记录哈希。
- evidence/rag_b0_failures.json：10份原型/页面失败和历史通过文件的哈希及具体观察；原始记录不上传。
- rechecks/task6-20261111/：本次原任务四26/26、公开凭证13/13、工作流27/27、封存15/15、任务五24/24与补缺39/39，旧报告未覆盖。

原规定reports/rag_b0_smoke.jsonl完整交付位于本机并被既有忽略规则排除；公开SHA不等于公开了全文。没有正式答案准确率或检索提升数字。


## 任务一至七综合复审

最新依据 [TASK_01_07_AUDIT_DELIVERY.md](TASK_01_07_AUDIT_DELIVERY.md)。新证据在 rechecks/task1-7-audit-20261112；最终汇总final/aggregate-final.json为29/29，原任务各自门禁和新增37项专项分别统计。final/aggregate.json为新汇总器适配格式失败的真实中间记录，不覆盖。

旧报告、原始检索测试、真实UI和人工账本保留。本轮当前后端3+1实跑，UI只重验原采集，锁定测试只重放旧逐题结果。当前入口都应使用新的报告目录，避免覆盖原交付。


## 任务八BM25中文基线

最新 [TASK_08_SUPPLEMENT.md](TASK_08_SUPPLEMENT.md)：四组缺陷修复、新回归32/32、原专项74/74、完整恢复门禁35/35、恢复8/8及八组公开副本复算13/13通过。证据在 rechecks/task8-audit-20261112；中间失败报告保留，最终使用 regressions-current 和 delivery-restored-current。原正式测试及旧交付报告保持原字节。

最新 [TASK_08_DELIVERY.md](TASK_08_DELIVERY.md)；规定汇总 [bm25_baseline.json](bm25_baseline.json)，原始结果retrieval/bm25_b0/development及test。35项完整门禁、74项当前专项、8项复现保护，公开副本五组复算；原任务四/六/七回归分别通过。

初次失败保留dev/body/failure.json，该目录即使有summary也不计成功。原74项是65e7516唯一正式测试前的回执；当前74项与恢复dev另列。segmentation-dev是测试后仅开发集补充实验，准确模式正式B0及唯一test不变；INTEGRITY_SCOPE解释共享哈希I/O边界。
