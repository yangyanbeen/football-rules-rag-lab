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

## TASK-001-003-FRESH：独立环境与浏览器缺项关闭（2026-11-11）

基于 main 40c2e9432121178427cae4c3010cdae2a3e9fbf9，分支 fix/task-02-fresh-ui-and-runtime。用户要求完成交付报告未完成的缺陷。原技术/执行文档、任务标准、Corpus B0 不变。

- 在新目录取得官方固定 commit 的干净源码；独立 Python 发行版和 uv 工具由本机副本复制到新目录，虚拟环境重新建立。原 uv.lock 导出 260 个核心依赖，require-hashes 安装，加两个 editable 固定源码包，共 262 项；版本、包和解释器位置实际验证。未安装可选高级 torch/图/开发 extras，没有复制旧虚拟环境或数据库。
- 首次全量离线 uv sync 因未缓存 torch 失败；独立环境重建曾遇 uv 默认全局缓存跨盘错误，改用本项目缓存后完成。脚本最终默认选本目录独立 Python，离线重复安装实际退出 0。失败和成功日志均在忽略的 .runtime/fresh-runtime-20261111。
- prepare_kotaemon_assets.py 下载真实 NLTK punkt/punkt_tab 并按发布者 SHA-256 核验；官方 raw 不通时使用同一官方仓库 GitHub API，资源不伪造。缓存可在虚拟环境重建后复用。新配置仅启用 Ollama/私有文件集合，无未安装图依赖或远程 tokenizer 启动重试。
- 新空数据库先留存 admin/零文件证明；通过浏览器创建普通账号 yanyanbeen，退出 admin，浏览器上传五份原 MD，5/5 成功、50 临时块。正文哈希均与冻结数据一致；未转移 admin 私有资料。
- 浏览器首问发现上游在关闭重排时仍提前读取空重排池，实际报 No models in pool。增加本地工厂明确不实例化重排/相关性打分，继续用原检索和文件范围；上游源码保持干净。重启新实例 7861 后实际重新输入 Q1/Q2/Q3，逐段原文、信息面板和来源 URL 均通过。原 7860 实例保留。
- 本机原始 UI 证据：.runtime/fresh-runtime-20261111/ui-three-dom.json；公开摘要：reports/evidence/fresh_ui_three_questions.json。完整答案/DOM/凭据/数据库/模型不公开。
- 检查器首轮把未填充的 relation.user 当作所有权而报 29/30；按上游真实 Source 所有权关联计数修正，保留失败回执，不改数据或标准。

实际统一命令（原工程/变更前快照路径仅本机提供）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/recheck_fresh_delivery.ps1 -UiCapture .runtime/fresh-runtime-20261111/ui-three-dom.json -OriginalRoot <原工程目录> -OriginalSnapshot <变更前快照JSON>
```

实际退出 0：综合 33/33，UI 3/3，开发回归 16/16，引用契约 19/19；任务三原校验 18/18、suite 8/8、坏数据拒绝 16/16。10 个冻结文件、4 个历史前缀、61 个本地语料和原工程 178 个静态文件未变。Chroma 仅保留候选容量自动收敛提示。资料资格说明保留，任务四至十四未完成，不编造正式检索/答案/延迟成绩。

当前操作说明 docs/PUBLIC_SETUP.md、docs/FRESH_ACCEPTANCE.md；当前交付 reports/TASK_01_03_REDELIVERY.md；实测 reports/acceptance/fresh_delivery.json。后续按小提交、PR 合并和标签管理；只写新仓库 football-rules-rag-lab，原有其他仓库只读。

## TASK-004-PREPARE：候选评测集和签收门禁（2026-11-11）

- 用户任务：执行原任务四，达到原交付标准。原技术/任务文档不改；起点4830c28a90f2d6d2b1aa31544728f283e222bed3，分支feat/task-04-evaluation。
- 输入：任务三99个稳定知识段，corpus-b0-rag-adapter-1.0.0；既有五份正文、英中数据、来源和模型/问答参数不变。
- 主要变量：新增自拟评测候选与可复核标注/冻结流程，不进行检索参数实验。数据football-eval-0.1.0目前candidate；40开发候选（32可回答/8拒答）、50测试候选（40/10）、90对应答案标签、90对逐题负例，两组各覆盖1—17条。
- 起草：本Agent读取固定正文后编写，明确AI来源。发现两条普遍化问法可能实际可回答“不一定”，改为缺具体赛事/赛季的数值或制度查询；补入已知等价支持段；能由一段完整回答的题不机械记为跨段。这些是AI编辑，不冒充人工评测。
- 工具：确定性构建、结构/正式交付验证、合成手算指标、16类重签哈希坏数据、实际人工逐题页面、签名失效及冻结门禁。合成复核只在.tmp夹具测试，默认不计真实人工记录；主评测数据没有被自动通过。
- 实际执行：build_eval_dataset.py；recheck_task4.ps1 -PreparationOnly；默认完整recheck_task4.ps1；verify_task3_isolated.py --report reports/acceptance/task4_corpus_regression.json。
- 自动结果：结构22/22、工作流27/27、坏数据拒绝16/16；任务三原18/18、8/8、16/16继续通过，输入未变。浏览器实际打开7862，缺CSRF的写入被403拒绝，未生成人工确认。
- 原正式门禁：FAIL，22/25；默认完整入口实际退出1。缺项是真实人工0/90、测试冻结及相应正式发布状态。PreparationOnly退出0仅代表准备检查，不是任务四交付。
- 模型与性能：未运行真实开发/测试检索或答案预测，没有本地模型调用，没有正式Recall/MRR/答案准确率/延迟成绩；手算夹具数值只验证算术实现。代码版本见候选登记，不能用合成签名/指标做简历成果。
- 后续：已向实际用户提供逐题页面http://127.0.0.1:7862/及人工要求。按真实反馈修订，全部匹配确认后freeze_eval_dataset.py再执行完整验收。此时只发布候选分支/草稿PR，不合并完成、不标完成标签、不进入任务五。
- 权威说明：docs/EVAL_DATASET.md、docs/TASK_04_SCOPE.md；阶段报告reports/TASK_04_DELIVERY.md；机器记录reports/acceptance/task4_*。姓名/备注/完整复核日志、原全文及账号保持本地。

## TASK-004-OWNER-ACCEPT：用户批量授权签收（2026-11-11）

- 用户最新指令：“我授权你全部通过，赶紧操作”。按此执行90题负责人委托批量批准，真实审阅类型owner_delegated_batch；不生成human阅读勾选，不假冒专家。
- 已有2条匹配的实际人工复核保留。原人工门禁实际重跑23/26 FAIL，独立留存task4_original_human_gate_after_owner_approval.json；没有修改原验证器或原任务/技术文档以伪造全部人工条件满足。
- 批准绑定全部annotation_sha256和四份数据文件哈希。50条测试冻结于269d49e7d65c4ad3a97b588f34093a65bbc483c7382f78b0e9cf466eaa759a62，原40/50题、答案、负例内容均未变化。
- 负责人校验10/10，专项检查6/6，工作流27/27通过；构建器已实际拒绝覆盖冻结数据。UI分别显示负责人90/90与逐题人工2/90。
- 代码：owner_approve_eval.py、UI状态更新、计分显式label-policy owner_approved；默认逐题人工策略保留。模型/检索预测未运行，无新增性能数字。
- 签收性质：按负责人授权完成本轮批准与冻结，原人工质量条件的未满足事实继续保留。记录docs/TASK_04_OWNER_ACCEPTANCE.md、owner_approval_receipt.json及task4_owner_*；原候选失败和登记作为历史保存。
- Git：追加小提交到PR #7，按负责人签收版本合并，版本v0.4.0-owner-approved；原有其他仓库与冻结语料不变。

## TASK-004-HUMAN-REOPEN：开启冻结版本逐题人工审核（2026-11-11）

- 用户指令：现在开启人工审核。在独立分支 feat/task-04-human-review 调整本地审核入口，不改原技术/任务标准。
- 新增启动选项 --allow-frozen-human-review，允许对原冻结快照追加真人审核记录。默认启动仍禁止写入冻结版本；快照文件哈希变化时拒绝继续接收记录。
- 修复页面按负责人批量批准跳过全部待人工题的问题；下拉列表分别标识真人通过与负责人批准，下一条只看实际人工状态。
- 本机7862已使用该选项重启，浏览器已加载，两个判定按钮可用，四项检查未自动勾选。页面显示负责人90/90、实际人工2/90，保留以前记录；未代用户提交审核。
- 本轮仅开启服务和查看页面，未运行新增自动化测试、正式检索或模型评测；没有新增人工通过或性能数据。原始冻结数据、测试锁与批准凭证保持原样。
- 操作说明：docs/TASK_04_MANUAL_REVIEW.md。未完成的88题须由实际复核人阅读提交；全部审核后仍需完成原正式交付校验与人工发布状态处理。

## TASK-004-HUMAN-DELIVER：90题人工核对后按原标准交付（2026-11-11）

- 用户告知人工审核全部通过并要求验收交付。实际读取私有追加日志133条事件：90个当前问题最新判定均为human通过，时间、四项检查及annotation_sha256有效；没有把133条事件计成133题，也没有由本Agent生成真实人工记录。
- 首轮原完整门禁24/26 FAIL，真实人工90/90已通过；仅缺人工发布状态及封存日志哈希，保留task4_before_human_release.json。
- 新增受限的负责人冻结快照→人工签收元数据转换：必须原批准有效、结构通过、90题人工记录匹配。保留四份标签正文、99段语料、原测试锁定时间、测试SHA和使用历史；不解除锁、不放宽原验证器/技术或任务标准。
- 暂停7862写入以封存日志，生成去姓名/备注的human_review_receipt.json，并更新发布状态与日志/凭证哈希。完整姓名、备注、原始勾选日志仍留本机忽略目录。日志SHA为1e7161c703bce47ae7a8c3d13dafa04a09009cd8ea5311cd082e4dce309fb464。
- 实际执行freeze_eval_dataset.py、recheck_task4.ps1（完整模式）、verify_task4_human_release.py、owner_approve_eval.py、verify_task3_isolated.py。结果：结构22/22、原正式交付26/26、工作流27/27、16类坏数据拒绝；封存专项15/15，原负责人10项仍有效；原任务三18/18、8/8及16类坏数据拒绝，输入未变。
- 重新冻结命令返回Already locked且不改文件。7862恢复为只读展示，人工90/90、测试冻结、提交按钮禁用；实际浏览器证据reports/evidence/task4_human_review_ui.json。封存后不继续追加审核，修订须另建数据版本。
- 交付40开发题、50锁定测试题、90对应答案/拒答标签、90对负例；两集合各覆盖1—17条。原失败回执及负责人批准凭证保留为历史；最新依据reports/TASK_04_DELIVERY.md和task4_delivery_gate.json。
- 没有运行真实检索/LLM评测、正式测试计分或调参，没有新增Recall/MRR/nDCG/延迟成绩，不宣称专家或官方赛季规则认证。后续任务五起另按原计划实施。
- Git继续独立feat/task-04-human-review分支、小步提交、PR #8与发布标签管理，仅新仓库football-rules-rag-lab写入。

## TASK-005-DENSE：固定Embedding与99段持久化向量索引（2026-11-11）

- 用户要求按同样标准执行原任务五。基线8e8b93c6556943b4d08ee82f2620a5bc21ee759a，分支feat/task-05-dense-index；原技术/任务标准、任务一至四数据和已有应用不改。
- 本机核对i7-13650HX（14核/20逻辑线程）、物理内存16,858,472,448字节和已有模型环境。选择Ollama0.40.16的bge-m3:latest，精确digest7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab；1024维F16，强制CPU8线程、8192窗口、batch4、truncate=false。
- 固定原完整section_path + content_zh模板，float32 L2归一化、Chroma0.5.16 cosine；模型前后digest校验、显式embedding_function=None。没有另装Torch、下载模型、重切表格或混入BM25/RRF/Reranker/缓存。
- 首轮原型99段成功且独立查询可用，但Chroma/PostHog遥测签名提示；独立禁用遥测组件首次缺@override而失败，未产生READY清单，完整验收正确拒绝。补声明并前置导入检查；保留两次原输出和日志，不改site-packages/上游，不覆盖原工程或已交付索引。失败见task5_before_runtime_fix.json。
- 最终代码真实构建data/indexes/dense：99×1024向量、Chroma持久化、原99行记录、位置/ID/正文及检索文本哈希映射、含实现/配置/输入/制品/运行环境的manifest。实际CPU构建43.811秒（Embedding43.062秒）；已有接口探测，非冷启动。
- 实际完整命令：build_dense_index.py；recheck_task5.ps1 -OriginalRoot <原工程目录> -OriginalSnapshot <变更前快照JSON>。后者在新.tmp目录重新编码99段，43.070秒（Embedding42.336秒）；向量最大绝对差0.0，本次字节相同，跨硬件仍只约定明确float32容差，不要求Chroma数据库位级一致。
- 结果：原标准完整24/24 PASS；18种无效输入/损坏索引拒绝。3条非评测示例各用2个新进程查询，ID/分数与原来源metadata一致；存储向量自查仅为契约检查，不是质量评测。正式回执task5_delivery_gate.json，smoke/hardware证据位于reports/evidence/。
- 输入保全：原10冻结文件、4历史前缀、61本机语料、178原工程静态文件不变；任务四manifest、人工/负责人凭证及测试与基线逐字节相同，原工程无根Git。任务五对测试文件仅读字节哈希，不解析题目做参数选择或计分。
- 分发：实际索引、向量、正文副本留本机忽略目录；仅公开config、dense_index_manifest.json和dense_chunk_ids.json等哈希元数据。不上传完整日志、账号或数据库。模型服务复用原本机Ollama，应用7860/7861/7862的代码/数据库未接管。
- 交付：docs/EMBEDDING_AND_INDEX.md、reports/TASK_05_DELIVERY.md与当前状态索引已更新。小步提交、PR与版本标签保存；仅新football-rules-rag-lab仓库写入。
- 本轮没有LLM回答、正式测试预测、Recall/MRR/nDCG、答案准确率、P95/QPS或优化提升数字；来源非官方/未专家审校边界不变。任务六起按原计划单独推进。

## TASK-004-005-SUPPLEMENT：仓库核对与6组边界缺陷修复（2026-11-11）

- 用户要求任务四、五上传仓库、查缺陷并补齐。起点3e41191c145da963fb24057bb1b39354287ebc5a，新分支fix/task-04-05-delivery-audit；原技术/任务标准不改，不进入任务六。
- 只读GitHub核对：原PR8/9已合并，两个原发布标签有效；157个公开文件的Git对象、清单大小和SHA完全匹配，规定交付物无缺失、无全文/索引/账号上传，12/12通过。
- 在隔离.tmp复现6/6：原门禁不检查缺失的公开凭证；共享路径两个实例末次close抛KeyError（查询当时仍工作，不写成查询失败）；集合打开失败留系统缓存；部分/重复/错位或错误有限距离结果被接受；api/query_template配置被忽略；允许嵌套输出进已有索引。原始复现task45_before_fixes.json。
- 修复：新公开凭证13项一致性验证和冻结工具守卫，原人工验证器不改；按路径引用计数、锁与幂等关闭及失败清理；结果形状/唯一ID/来源和实际余弦距离复算；同配置Embedding及严格字段校验；写前拒绝嵌套索引路径。
- 增加--report/--report-dir和统一recheck_task45.ps1，新报告写入独立目录，旧数据/报告/公开索引元数据不覆盖。公开克隆只有2个检查脚本和eval元数据、没有语料/日志/模型时，公开凭证仍13/13；该状态不证明私人真实阅读，原完整门禁仍需真实日志。
- 实际统一复核：recheck_task45.ps1 -ReportDir reports/rechecks/task45-20261111 -OriginalRoot <原工程目录> -OriginalSnapshot <变更前快照JSON>。原任务四26/26（人工90/90）、公开凭证13/13、工作流27/27、封存15/15、原任务五24/24及18种错误拒绝，补缺回归39/39全部通过。
- 任务五再次从新空目录真实编码99段，向量最大绝对差0.0；不使用锁定测试调参或计分。原正式索引所有文件哈希不变，最终61份旧证据/任务四数据/公开索引元数据不变，另3份入口/实验汇总随补交付更新；首轮在文档维护前64份一致的结果保留。原人工日志未追加，原10冻结、4历史前缀、61本机语料和178原工程静态文件通过保全。
- 当前依据reports/TASK_04_05_SUPPLEMENT.md及reports/rechecks/task45-20261111；旧构建producer哈希保留在旧manifest，当前reader和本次重建用新代码哈希，不回写旧实验。新增只读audit_remote_delivery.py支持后续远程逐文件复核。
- 仅新足球仓库走独立分支、小提交、PR与版本标签；全文、向量、数据库、完整日志和账号仍留本机。无新LLM回答、正式检索/答案/延迟优化成绩。


## TASK-006-RAG-B0：端到端链路与真实页面交付（2026-11-12）

- 用户要求按前序相同规则执行原任务六。起点0f6abdcc2b5ef8f35b9add68e0a1c15ee56f7fff，分支feat/task-06-rag-b0；原技术/执行文档和任务一至五输入不改。
- 固定BGE-M3/Chroma99段索引，Dense Top5；本机Qwen2.5:3b精确digest、CPU8线程，grounded-text-v7。只送入一个预算内完整块，不剪裁原块；程序绑定原URL/chunk/规则号/校核/版本/许可。
- 真实发现并保留多轮误拒答、混合JSON状态、引用/数值错配、截断、重复和残句；最终简化模型输出并校验，最多额外重试一次。完整UI导入后的HNSW原生异常通过独立问答进程隔离；只读选择器满足上游事件约定，未另建临时向量集合。
- 实际命令：query_rag_b0.py --check；run_rag_b0.py；smoke_rag_b0.py；浏览器填入并提交4问；summarize_rag_b0_ui.py；verify_rag_b0.py。62/62通过；最终后端/真实页面分别3可回答+1资料外拒答，均无处理错误，完整原始记录留本机。
- recheck_task45.ps1在新reports/rechecks/task6-20261111目录真实重验：原任务四26/26、凭证13/13、工作流27/27、封存15/15，任务五24/24及18类错误拒绝、再次编码99段最大差0.0，补缺39/39。旧报告、人工日志、正式索引与原工程保持原样。
- 交付docs/RAG_B0.md、reports/TASK_06_DELIVERY.md、机器回执/元数据摘要；10份失败/历史通过文件公开哈希但不公开正文。没有把自动检查记成人工审批，没有检索/答案准确率、P95/QPS或提升数字。单块上下文/一般语义判断的能力限制见报告。
- Git继续小步提交、独立分支、PR和v0.6.0-rag-b0标签；只写新football-rules-rag-lab仓库。任务7–14继续按原计划。

## TASK-004-006-SUPPLEMENT：8组边界缺陷关闭（2026-11-12）

- 起点main f97c0df，独立fix/task-04-06-delivery-audit。原205个公开文件没有漏传，14/14远程只读核对通过。修复前18个检查中16个为隔离实际复现，2个为明确源码问题。
- 补齐DenseIndex公开回执语义门禁；严格配置/模型包；固定拒答文案；原响应、attempt阶段和失败清理；worker原文/原包摘要/引用/呈现核对；独立smoke/UI新路径与回执校验；旧标签祖先关系。
- 首轮55项结果保留，复查原包/摘要绑定增加3项，最终58/58。模拟脚本不发模型请求；可移植62项使用旧实际记录作为回归夹具，新真实UI另列。
- 原任务四26/26（人工90/90）、公开13/13、工作流27/27、封存15/15，任务五24/24及18类错误拒绝，前轮回归39/39通过。本轮新目录真实编码99段55.836秒，最大向量差0.0，原正式索引不变。
- 最终代码477784420a1f27b8e2a4b688dae548b35c22cf96重启独立7863，后端与真实页面分别3+1无错误；最终原任务六门禁62/62，公开回执15/15，私有记录核对20/20。新证据在reports/rechecks/task456-20261112，完整记录留本机。
- 输入/人工日志/旧报告保全：冻结10文件/4前缀、61语料、178原工程静态文件，旧技术/执行文档及validate_eval_dataset.py未改；Dense新reader的评测元数据解析仅用于公开回执一致性，不做Embedding/生成/调参/计分。旧producer哈希不回写。
- 交付报告TASK_04_06_SUPPLEMENT.md，新增脚本validate_rag_b0_receipts.py、verify_task456_regressions.py，维护当前状态/运行/实验索引；小提交、PR、v0.6.1-task456-audit，旧标签不移动，仅新足球仓库写入。
- 未测正式检索/答案准确率或性能提升，单块上下文/语义判断限制保留。任务7–14继续原计划。
