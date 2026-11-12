# 任务一至七综合复审与补交付

日期：2026-11-12。基准：`24d8cabccbeeb17db096733c48a96eed60f6a304`；分支：`fix/task-01-07-comprehensive-audit`。

## 结论

**任务一至七按原交付标准复审通过。** 本轮关闭4组复验/交付缺陷，新增专项37/37、统一入口覆盖保护4/4；综合汇总29/29。原任务门禁分别列出，不把这些检查数相加当作答案准确率。原技术/执行文档、原始语料、评测标签、人工账本、正式索引和历史报告没有改写。

权威要求仍为 `docs/TECHNICAL_DESIGN.md`、`docs/DEVELOPMENT_PLAN_AND_REPORT.md`；本轮边界见 [TASK_01_07_AUDIT_SCOPE](../docs/TASK_01_07_AUDIT_SCOPE.md)。最终机器汇总：[aggregate-final.json](rechecks/task1-7-audit-20261112/final/aggregate-final.json)。

## 1. 发现并补齐的缺陷

| 编号 | 复审发现 | 修补与证据 |
| --- | --- | --- |
| F1 | 一至三复验有固定回执路径；三至五的部分工具可覆盖既有报告。任务五失败处理也可能把旧成功报告改成失败记录。 | 新报告路径预检、独占写入；统一入口使用新目录。任务三直接suite发现历史报告时引导使用隔离入口；任务五在设置失败输出位置及模型工作前拒绝旧报告。实际调用这些入口验证拒绝且旧字节不变。 |
| F2 | UI关联只取同题最新日志，后续交互可能使旧采集误配；只检查引用段落存在，未检查完整可见回答。 | 同题、带时区十分钟窗口、完整可见回答必须唯一匹配。拒绝追加虚构结论、部分答案、重复匹配、陈旧或未来日志；保留原来源段落、URL、账号文件范围检查。真实旧三问重新匹配通过。 |
| F3 | 综合验收固定读取上一轮stderr及依赖报告；19/19计数未绑定实际回归文件，任务三只读摘要PASS。 | 允许显式指定本轮日志/报告，记录SHA；19项检查绑定回归文件SHA且逐项为真，任务三须有18项校验、8项suite、16个坏例及成功退出。避免用别轮或仅摘要报告替代当前证据。 |
| F4 | 安装/验收说明仍声称任务四至十四未完成；状态表引用了错误的质量修复文件名。 | 更新当前安装、验收、状态、README及本报告，明确已完成1–7、8–14仍按计划；历史原件和四个历史前缀不改。 |

代码主要变更：`delivery_review_io.py`、`verify_fresh_delivery.py`、`verify_answer_quality.py`、`verify_task3_isolated.py`、任务三至五复验入口及两份PowerShell包装器。没有修改检索模型、索引配置、生成算法或评测标签。

修复前证据在 `before-fixes.json`：1个执行原AST的模拟、6个源码/文档观察，不冒充线上故障。其中一个源码观察表达式误匹配了已有的 `visible_answer_sha256` 输出字段，原False保留，说明与更正见 `before-fixes-correction.json`。新增回归初版30/30、覆盖后续入口后的最终37/37分别保存。

## 2. 逐项交付复核

以下路径相对于 `reports/rechecks/task1-7-audit-20261112/`。

| 任务 | 原交付要求落实 | 本轮实测/重验 | 最终证据 |
| --- | --- | --- | --- |
| 1 审计冻结 | 五份文档、99稳定ID、来源映射、环境、文件清单及实验日志 | 综合33/33包含10冻结文件、4历史前缀、61语料、262包位置/版本和178原工程文件；新清单另校验 | `final/unified-fresh/delivery/fresh_delivery.json`；当前project_file_manifest；EXPERIMENT_LOG |
| 2 固定应用 | 官方v0.12.0/固定commit、独立Python3.10.22及260锁定包+2源码包、实际中文三问和引用 | 33/33；真实历史UI三问3/3重新关联；本轮16条开发回归和19项契约通过；当前7861 HTTP200 | 同上；`final/unified-fresh/answer_contract.json`；`evidence/runtime-health.json` |
| 3 数据适配 | 99旧ID、中文/对照JSONL、来源/行号/修订边界、Schema/转换/校验脚本 | 主校验18/18、suite8/8、重新签名坏数据16/16拒绝；隔离重建字节一致、输入不变 | `final/unified-fresh/task3.json` |
| 4 人工评测集 | 40开发/50锁定测试、90答案标签和90对难负例，保留90/90人工签收 | 原门禁26/26、公开凭证13/13、工作流27/27、封存15/15；未新增人工记录，7862锁定只读 | `final/task45/acceptance/task4_*.json`；`evidence/runtime-health.json` |
| 5 正式索引 | 固定BGE-M3 F16/CPU8/1024维、Chroma99段、元数据与ID映射、空目录重建 | 24/24；18类错误拒绝；最终99段真实重编码42.441秒，最大向量差0.0；正式索引原字节不变 | `final/task45/acceptance/task5_delivery_gate.json`及对应evidence/manifests |
| 6 RAG B0 | 查询→Dense Top5→Qwen生成→引用/拒答，日志区分召回与生成 | 原门禁62/62；当前后端3回答+1拒答，无错误；私有凭证20/20；原真实UI3+1重验，当前7863 HTTP200 | `final/task6.json`、`final/task6-private.json`、`evidence/task6-live-smoke.json` |
| 7 Retrieval B0 | 固定原索引/评测、逐题预测/计时、数据/模型manifest、错误分析、独立复算 | 原43/43；算术54/54、合同110/110、复算113/113、前轮缺陷61/61；新正式test推理0 | `final/task7.json`、`final/task7-replay.json`、`final/task7-supplement.json`、`acceptance/task7-{arithmetic,contract}.json` |

前轮四五回归39/39、四六回归58/58在最终代码上通过。综合汇总工具逐项核对这些原门禁及保全，不修改各任务门槛。

## 3. 运行与证据范围

- 7861原任务二独立应用、7862已封存审核查看页已恢复；7863正式RAG应用继续运行。本轮没有重建账号、重新上传语料或写人工审核事件。
- UI采集来自此前真正浏览器提交的原记录，本轮只是重验，不宣称重新提交UI三问/3+1。当前HTTP、16开发题及RAG后端3+1为本轮实际执行。
- 两次任务五全门禁各在不同临时目录重新编码99段，最终使用第二轮42.441秒的回执。不是检索延迟或优化收益。
- 任务七解析、重放已保存dev/test排名及聚合结果，未新发锁定测试Embedding请求，未用测试集选择参数。原测试Recall@5/10=95%（38/40）、MRR@10=0.8604167及150次计时保持原字节。
- 首次汇总工具27/28失败，是适配器误以为19项契约回执有status字段；该回执原本仅提供计数/逐项检查。保留 `final/aggregate.json`，按真实格式核验后 `aggregate-final.json`29/29通过，不给原回执补造字段。
- 全文回答、DOM、启动日志、模型、向量、账号仍留本机忽略目录；公开仅提供原允许范围的代码、来源/ID/哈希、判断结果和测量元数据。

## 4. 重验命令与小步版本

从本仓库根目录执行；路径须换成新的输出目录，依赖本机冻结语料、模型和既有真实UI采集。仅克隆公开仓库不等于拥有完整私有证据。

```powershell
# 任务一至三：资源、原任务三隔离suite、16开发题、19项契约和综合33项
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/recheck_fresh_delivery.ps1 -UiCapture .runtime/fresh-runtime-20261111/ui-three-dom.json -StderrLog .runtime/task1-7-audit/kotaemon.stderr.log -ReportDir reports/rechecks/my-new-task123
# 任务四五：原门禁和一次真实独立重编码
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/recheck_task45.ps1 -ReportDir reports/rechecks/my-new-task45
# 任务六：原真实smoke/UI重新核对，不自动提交浏览器问题
.venv/Scripts/python.exe scripts/verify_rag_b0.py --report reports/rechecks/my-new-task6.json --reference-commit 423ea06
# 任务七：历史原始记录复算及保全，不重跑测试推理
.venv/Scripts/python.exe scripts/verify_task7_delivery.py --report reports/rechecks/my-new-task7.json
# 本轮补缺专项及综合汇总，均须新JSON路径
.venv/Scripts/python.exe scripts/verify_delivery_review_regressions.py --report reports/rechecks/my-new-review-tools.json
.venv/Scripts/python.exe scripts/verify_tasks_01_07_delivery.py --report reports/rechecks/my-new-aggregate.json
```

首次33项还传入原工程与变更前快照两个参数，完整命令见回执；不传时不会把两项未做的原工程保全算作通过。以上简化命令不替代首次完整记录。

小提交已按范围/复现、UI关联与路径保护、三至五入口保护、原门禁和实运行回执、文档/实验索引、文件清单分开。发布仅针对 `yangyanbeen/football-rules-rag-lab` 的本分支PR；版本标识 `v0.7.2-task1-7-audit`，旧标签不移动。回滚用PR merge commit的 `git revert -m 1` 新分支，不强推main。

## 5. 保全与后续

变更前私有快照覆盖基准303个公开文件，并与该Git提交逐字节核验；正式索引10个文件、人工账本和原评测/历史交付报告不变。10个冻结文件、4个历史前缀、61份语料、原工程178个静态文件均有原门禁证明。原10个实验对象保留，任务14登记只追加本轮。

本轮解决的是已发现的交付/复验缺陷，不代表代码不再可能有其他缺陷。Wikipedia社区资料、AI翻译未经裁判专家审校、历史版本正文未独立核验等限制保留。RAG B0单块证据与跨段能力、答案语义正确性仍按原任务十二评测；任务八至十四按原计划继续，不编造准确率、QPS或提升数字。
