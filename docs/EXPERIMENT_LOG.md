# 实验记录

只记录实际运行过的实验。没有结果时写“未测/未运行”，不要填估算值。正式评测应附机器可读逐题结果、数据版本和 commit；当前只有任务二的 UI 冒烟，没有正式效果指标。

## 结果汇总

| ID | 日期 | Commit | 数据/评测版本 | 变更 | Recall@5 | MRR@10 | 引用命中率 | 检索 P50/P95 | 决定 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TASK-002-UI | 2026-11-10 | `9ad3e4e` | 5 份 Markdown / UI 临时索引 50 chunks；非锁定评测集 | Kotaemon 本机运行冒烟 | 未测 | 未测 | 未测 | 未测 | 运行链路通过；问答/引用错位，进入任务 3 并后续评测 |

## 实验模板

### EXP-XXX：标题

- 日期/commit：
- 假设：
- 对照组：
- 唯一主要变量：
- 语料/评测集版本及样本量：
- 模型、参数、硬件：
- 运行次数与计时方法：
- 结果文件：
- 指标变化：
- 失败案例/副作用：
- 结论：保留 / 继续 / 撤销
- 后续行动：

## 归档：TASK-002 初始环境尝试（2026-11-10）

- 当时只完成上游版本选择。Python 为 3.9.12，缺少隔离环境、Ollama 和项目源码；Docker Engine 无法连接，WSL 返回 `E_ACCESSDENIED`。
- GitHub HTTPS 下载在当时的 shell 网络层失败，固定源码目录不存在。
- 当时的启动脚本按预期因源码缺失退出；应用和三条问题均未运行。
- 这是任务二设置完成前的历史尝试，已被后续成功运行取代。保留原日志：`reports/task2_environment_check_2026-11-10.log`、`reports/kotaemon-baseline-20261110-202156.log`。

## Task run: TASK-002 Kotaemon UI smoke（2026-11-10）

- 上游：Cinnamon/kotaemon v0.12.0，HEAD `9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9`，Apache-2.0。
- 环境：项目 `.venv`，Python 3.10.22；依赖来自固定 checkout 的 `uv.lock`。
- 模型与检索配置：Ollama `qwen2.5:3b` 聊天模型 + `bge-m3` Embedding；Chroma `index_1`；hybrid retrieval；Top-K 10；reranking、LLM relevant scoring 关闭；中文回答。
- Windows 存储兼容：默认 LanceDB 文档存储初始化遇到 OS error 5。`scripts/run_kotaemon_local.py` 仅在运行时换用上游 `SimpleFileDocumentStore`，未修改上游 checkout；Chroma 保持原配置。
- 实际界面导入五份 Markdown，应用日志分别记录 10、13、13、7、7 个 chunk，共 50 个；5/5 完成转换和 Embedding。这些临时 chunk 不保留 Corpus B0 的 99 个稳定 ID，只作为界面冒烟输入。
- 实际界面提交 Q1 越位、Q2 直接任意球、Q3 球门球；三题均产生回答并显示来源面板。逐字回答与错位细节见 `docs/KOTAEMON_BASELINE.md`。
- 质量观察：Q1 的回答编号与可见越位证据未可靠对应；Q2 混入点球/界外球/守门员材料回答直接任意球；Q3 把球门球问题引用到任意球文档。三条回答均作为后续检查的失败样本保留。
- 未创建 gold label 评测集；Recall、MRR、nDCG、正式引用命中率和受控检索延迟均未测。没有简历指标可以从本次运行得出。
- 验收：任务二的运行交付基线通过（固定源码、真实 UI、5 份文档索引、3 条中文回答、来源行为记录）。这不代表答案质量通过，也不代表已经建立正式 RAG B0。下一步进入任务三，以原始 99 个稳定知识段为输入。
- 启动脚本复核：初次 `-CheckOnly` 发现 PowerShell 的内联 Python 引号传递错误（`reports/kotaemon-baseline-20261110-222521.log`）；改用 `scripts/check_kotaemon_runtime.py` 后再次运行成功，固定 commit、Python 3.10.22 和 `kotaemon`/`ktem`/`chromadb` 模块检查均通过，退出码 0（`reports/kotaemon-baseline-20261110-222605.log`）。检查模式没有启动第二个服务。
- 证据：`reports/task2-indexing-windows-overlay-final-2026-11-10.log`、`reports/kotaemon-app-windows-overlay-2026-11-10.log`、`reports/kotaemon-baseline-20261110-222605.log`、`docs/KOTAEMON_BASELINE.md`。


## TASK-001-DELIVERY：任务一交付补验（2026-11-10）

- 依据：`docs/DEVELOPMENT_PLAN_AND_REPORT.md` 原任务一的工作内容、交付基线与通过条件；技术设计和任务要求保持固定。本条补充真实补验记录，不追填不存在的历史命令。
- 输入：Corpus B0，5 份 Markdown、99 条中文知识段、99 条英中对照记录、18 页来源、现有 corpus manifest 与 validation report。
- 执行命令（项目根目录）：`.\.venv\Scripts\python.exe scripts/audit_task1_task2.py`。
- 文件清单生成/复核命令：`.\.venv\Scripts\python.exe scripts/update_project_manifest.py` 与 `.\.venv\Scripts\python.exe scripts/update_project_manifest.py --verify`。
- 已核对结果：5/5 文档 SHA-256 与 corpus manifest 一致；中文/英中各 99 条，ID 唯一且两侧集合一致；空正文、缺来源 URL、无效来源行范围、未知来源 ID 均为 0；覆盖第 1—17 条；来源 CSV/JSON 各 18 条；36 份 raw 文本快照；28 个知识段带复核提示，专家审校数为 0。
- 执行边界：只读取并校验语料；两个构建脚本使用 compile() 做语法检查，未执行重建。技术文档、任务文档、原五份 Markdown、两份 JSONL 和 corpus manifest 以补验前 SHA-256 锁定。
- 本次环境：项目 `.venv` Python 3.10.22，Kotaemon/ktem 0.12.0；当前安装依赖和模型缓存状态写入机器报告。这是任务二准备后的实际环境，与本报告早期 Python 3.9 的历史记录对应不同时间点。
- 项目根目录仍无 Git 元数据；上游子目录 HEAD 为固定 commit，tracked source clean。
- 运行日志按“活动源文件 → 静态归档快照”登记在 `data/manifests/runtime_log_snapshots.json`；归档快照参加 SHA-256 验收，原活动日志继续供服务写入，避免交付哈希随运行失效。旧文件清单保留在 `reports/archive/task1_task2_2026-11-10/project_file_manifest.before-supplement.json`。
- 机器结果：`reports/task1_task2_acceptance.json`；原标准逐项交付映射：`reports/TASK_01_02_DELIVERY.md`；固定输入清单：`data/manifests/task1_task2_baseline_lock.json`。
- 本轮仅补齐任务一、二已有交付内容；正式检索指标、答案准确率均未测，不生成任何简历性能数字。

## TASK-002-DELIVERY：任务二交付补验（2026-11-10）

- 依据：原任务二固定上游、隔离环境、三条中文冒烟和配置记录要求。
- 补齐事实：实际安装关键依赖版本与固定 uv.lock 逐项对应；应用分块参数由持久化集合配置和固定源码路由共同解析，结果为 TokenSplitter / 1024 tokens / overlap 256 tokens。
- 启动检查命令：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_baseline_check.ps1 -CheckOnly`，本轮退出码 0；日志 `reports/kotaemon-baseline-20261110-232421.log`。
- 浏览器实测：本地应用 HTTP 200；三条原问题和非空回答仍在 UI，Information panel 存在；原始页面文本、逐题回答和捕获时间写入 `reports/task2-ui-evidence-2026-11-10.json`。
- 本地模型服务：浏览器读取 Ollama 0.40.16 与当前两模型清单，名称、digest 和读取时间保存在 `reports/task2-model-runtime-2026-11-10.json`。
- 配置补充：`docs/KOTAEMON_BASELINE.md` 文末；本机命令与模型字段补充：`docs/LOCAL_SETUP.md` 文末。
- 验收结果由 `reports/task1_task2_acceptance.json` 的 task2_status 和最终文件清单校验共同确认。原三条回答中的内容/引用错误保留；原任务二没有答案准确率门槛，不更改其通过标准。

- 本轮机器补验实际结果：任务一 PASS、任务二 PASS，共 24/24 项通过；完整判定及逐项证据已写入 `reports/task1_task2_acceptance.json` 和 `reports/TASK_01_02_DELIVERY.md`。最终文件清单在全部交付内容保存后生成并执行 --verify。


## TASK-001-002-RECHECK：按原交付标准再次排查（2026-11-11）

- 时区：Asia/Shanghai；依据仍为 DEVELOPMENT_PLAN_AND_REPORT 原任务一、二，技术设计和任务规则不变。
- 来源深核：18 页 raw/clean 校验值重新计算一致；来源 CSV 与 JSON 元数据一致；99 条英文段落均能由保存的来源行范围重建为相同文本。5 份 Markdown、99/99 对齐记录、18 来源、36 raw 快照检查通过。28 条复核提示、专家审校数 0 未改变。
- 实际重启先后遇到 SOCKS 代理缺 socksio、tokenizer 缓存未固定的失败；保留 `reports/kotaemon-startup-2026-11-11.log` 和 `reports/kotaemon-startup-fixed-2026-11-11.log`。修复为当前进程跳过不支持的 SOCKS、补充本机 NO_PROXY、验证本地 cl100k_base 缓存后设置缓存路径，并改真实导入四个运行模块；没有改全局代理或上游源码。
- 新增资源准备/校验命令：`.\.venv\Scripts\python.exe scripts/prepare_kotaemon_assets.py --verify-only`；实际退出码 0，verification PASS，cl100k_base 固定哈希及 NLTK stopwords/punkt_tab 所需文件通过。本次没有重新下载模型或重装依赖。
- 启动命令：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_baseline_check.ps1`，本次环境变量、Ollama 命令、页面当前会话 Chinese/ollama 选项及停止方法完整追加在 LOCAL_SETUP 当日章节。
- 成功启动日志：`reports/kotaemon-startup-cached-2026-11-11.log`；PowerShell transcript：`reports/kotaemon-baseline-20261111-124053.log`。先前 CheckOnly 日志 `reports/kotaemon-baseline-20261111-123702.log` 也保留；CheckOnly 不替代成功服务运行。
- 真实三问：以当前会话 Chinese、ollama、simple、citation highlight 重新提交 Q1—Q3，三题均生成结束且有 Information panel。逐字回答和逐题来源面板为 `reports/task2-ui-evidence-2026-11-11.json`，服务版本/模型 digest 为 `reports/task2-model-runtime-2026-11-11.json`。答案与引用错误如实保留，未算正式准确率。
- 今日验收命令：

```powershell
.\.venv\Scripts\python.exe scripts/audit_task1_task2.py --live --ui-evidence reports/task2-ui-evidence-2026-11-11.json --model-evidence reports/task2-model-runtime-2026-11-11.json --startup-log reports/kotaemon-startup-cached-2026-11-11.log --output reports/task1_task2_acceptance-2026-11-11.json
.\.venv\Scripts\python.exe scripts/update_project_manifest.py
.\.venv\Scripts\python.exe scripts/update_project_manifest.py --verify
```

- 初轮今日结果：Task 1 PASS、Task 2 PASS，32/32。收尾在追加所有文档并冻结运行日志后，再运行上述验收和清单命令；机器判定保存在当日 JSON，文件清单只读验证必须零错误才交付。
- 保留昨日清单与日志归档；今天新增三个活动日志的静态副本，逐项记录 source/archive/captured_at/size/SHA，避免运行中的日志追加破坏文件冻结。原活动日志仍保留，应用和模型服务继续运行供查看。
- 固定输入十文件及四份报告旧字节前缀未变；仅补齐原任务一、二的现有要求。根目录无 Git；未执行语料构建脚本或改写 Corpus B0。

- 本轮最终实际执行结果：在线验收 Task 1 PASS、Task 2 PASS、32/32，退出码 0；全部文档保存后项目清单生成 128 个静态文件，5 份运行日志快照，--verify 返回 errors: 0、退出码 0。技术/任务/Corpus B0 十个固定输入和四份既有报告前缀核对通过。签收报告已更新为最终结果，本记录保存后再次冻结并验证清单。


## ANSWER-QUALITY-FIX：原三问、引用与拒答修复（2026-11-11）

- 目标：修复任务二原始三问暴露的判罚内容及引用错位；保持技术设计、任务交付要求与 Corpus B0 不变。
- 诊断：Ollama 旧日志明确 prompt 被限到2050，原应用多次 Got 0 cited docs；粗块混入相似规则。原逐字答案继续保存。
- 实现：scripts/football_evidence.py、scripts/football_quality_pipeline.py、config/answer_quality.json；启动器默认挂载本地 simple 覆盖层，原上游 checkout 不变。细化稳定单元检索、规则主题范围、每规则Top4、明确上下文预算、ID受约束选择、完整单元摘录及程序绑定引用；无有效来源则拒答。
- 实验历程：保留 original-three-first 和 regression-first/second/third/fourth 全部原始结果。结构检查初次未能识别语义错段；逐段模型支持判定又造成误拒答，未采用。最终规则主题隔离和有限窗口通过开发回归；没有把调试题当冻结测试集。
- 最终实际命令：`.\.venv\Scripts\python.exe scripts/run_answer_quality_regression.py --output reports/answer-quality-regression-final-2026-11-11.json`，退出码0，16/16。`.\.venv\Scripts\python.exe scripts/verify_answer_quality.py`，退出码0，19/19。
- 真实运行：按 run_baseline_check.ps1 重启，成功日志 kotaemon-quality-fix-2026-11-11.log；transcript kotaemon-baseline-20261111-134128.log。实际UI五问（原三问+资料外拒答+错误前提纠正）均生成结束，来源和服务日志对照5/5。截图、逐字页面内容、原始推理和对照JSON都在reports下以answer-quality开头。
- 版本：实现manifest记录代码、配置、语料SHA及两模型digest；未初始化Git、未重抓或重译语料。旧十文件固定锁与四份报告前缀仍应通过原审计。
- 边界：摘录正确只证明与既有语料一致；资料本身28个复核提示、专家审校0不变。无通用准确率、正式Recall或简历性能数字。本轮落实原任务6/12的相关要求，不标记其整项完成。
- 最终交付：ANSWER_QUALITY_FIX说明及阶段报告；活动日志归档后执行原任务一二在线复核，再重建项目manifest并以--verify零错误签收。应用和Ollama保留运行供用户检查。


- 本轮最终在线签收：收紧任意球主题分类后，原16例再次退出码0；19项证据契约再次退出码0；补查任意球类型题返回L13-01/L13-05。最终进程日志 `kotaemon-quality-fix-final-2026-11-11.log` / transcript `kotaemon-baseline-20261111-135518.log`；在此进程重新执行原三问，更新UI对应校验5/5，完整UI日志8条（保留初轮）。原任务一二再次按原标准在线验收32/32、Task1/Task2 PASS，退出码0，结果 `reports/task1_task2_after-quality-fix-2026-11-11.json`。


## TASK-003：统一数据结构与既有语料适配（2026-11-11）

- 目标与依据：原任务三的schema、空值、稳定ID、来源/版本/许可/翻译/复核/哈希适配要求；原技术文档和交付规则不变。
- 输入基线：Corpus B0五份Markdown、中文99条、英中99条、语料manifest、18页来源清单和原task1/task2固定锁。原文件只读，无重抓/重译/重切分。
- 实现：新增RAG_DATA_SCHEMA.md、build_rag_dataset.py、validate_rag_dataset.py、verify_task3_delivery.py；派生文件rag_chunks_zh.jsonl、rag_chunks_parallel.jsonl，dataset manifest保存13项输入哈希、实现/Schema/输出哈希、99项ID映射和版本限制。
- 环境：项目Python3.10.22、Windows；转换与校验使用标准库，无Embedding/LLM调用，模型和硬件性能指标不适用。根目录无Git，未初始化；以文件SHA追踪。
- 正式构建命令：`.\.venv\Scripts\python.exe scripts/build_rag_dataset.py`；退出码0，5分卷、99/99记录、99唯一ID、99空parent，98段落+1表格，28复核提示、专家审校0。来源总18页、实际引用17页。
- 独立校验：`.\.venv\Scripts\python.exe scripts/validate_rag_dataset.py`；退出码0，18/18 PASS；原始JSON结果reports/task3_dataset_validation.json。
- 交付复核：`.\.venv\Scripts\python.exe scripts/verify_task3_delivery.py`；退出码0，8/8 PASS、16/16坏数据拒绝；reports/task3_delivery_verification.json保存真实子命令、输出和退出码。新目录构建、原位置重跑字节一致；英中输入倒序仍按ID关联；覆盖原目录被拒绝。
- 注入错误仅在.tmp派生副本进行，含假URL/源ID、无效行号、重复/缺ID、虚构parent、错误审校/核验状态、正文修改、表格损坏和假provenance；派生哈希重新计算后仍被原输入对照校验拒绝。原语料和正式派生输出没有损坏。
- 额外交付：本机Kotaemon普通账号yanyanbeen经Resources创建，再用随机密码实际登录；Settings显示当前用户。密码只存.runtime/kotaemon-account.json，公开记录不导出密码或摘要；已有admin和5份私有索引文件未移动。
- 原任务回归：在线重跑audit_task1_task2.py，输出reports/task1_task2_after-task3.json；任务一、二PASS，32/32，退出码0。
- 结果边界：本轮完成任务三数据适配；无正式人工标签、RAG B0或检索/答案性能成绩。数据版本corpus-b0-rag-adapter-1.0.0，content ID和两输出SHA见dataset manifest。
- 交付说明：reports/TASK_03_DELIVERY.md；字段权威说明docs/RAG_DATA_SCHEMA.md；账号说明docs/LOCAL_ACCOUNT.md。登记all_experiments_summary.csv、resume_evidence.md和experiment_manifest.json，仅写真实工程证据。
- 最终文件清单：保留上轮159文件manifest到reports/archive/task3_2026-11-11；所有交付文档保存后重建project_file_manifest.json并运行--verify，零错误才签收。模型和应用保持运行。


## TASK-001-003-SUPPLEMENT：公开交付复核（2026-11-11）

原技术设计与任务验收标准保持不变；原工程及 Corpus B0 不修改。基线 Git main：a3f573fe9e7e489efc165739a0c7f8b27509cfea；补交付分支 fix/tasks-01-03-delivery-supplement。

发现并补齐：规定路径的当前文件清单、公开可查看的任务二证据、16条既有开发题输入、可指定输入/输出的契约检查、任务三隔离执行及统一复核入口。

实际执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/recheck_tasks_01_03.ps1 -RuntimeRoot "<已有原工程目录>"
python scripts/manage_delivery_manifest.py
python scripts/manage_delivery_manifest.py --verify
```

初次在线检查31/32，原因是应用与Ollama未启动；按原配置恢复后32/32。原任务三独立校验18/18、原交付suite8/8、16类重签哈希坏数据全部拒绝；16条后端开发回归和19项引用契约均通过。完整统一入口已实际运行，退出码0。文件清单在所有补交付文件暂存后生成并只读核对。

新结果：reports/acceptance/task123_recheck_summary.json；逐项基线与限制：reports/TASK_01_03_REDELIVERY.md；当前操作权威说明：docs/TASK_01_03_SUPPLEMENT.md。

历史UI三问保留原日期与哈希，不描述为本轮浏览器三问；本轮新跑的是后端开发题。未进行全新依赖安装、正式检索评测或性能优化。原工程178项静态文件未变；本地全文、账号、数据库和完整模型输出不进公开Git。
