# 项目现状审计报告

审计日期：2026-11-10  
审计任务：任务 1——项目现状审计与环境检查  
总体结论：**通过（附环境待准备项）**

## 1. 审计范围与结论

按 `docs/DEVELOPMENT_PLAN_AND_REPORT.md` 任务 1 的验收要求，检查项目文档、语料文件、JSONL 结构、来源追溯、处理脚本语法和当前 Python/RAG 相关环境。审计过程没有重建或编辑现有中文语料。

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| 5 份中文规则文档 | 通过 | 5/5 文件存在；文档字节级 SHA-256 与中文 corpus manifest 一致。 |
| 中文/英中 JSONL | 通过 | 两份各 99 条；JSON 可解析；ID 均唯一且两侧 ID 集合一致；无空文本。 |
| 来源追溯 | 通过 | 99/99 中文记录具有 source URL、格式有效的 source line 范围和来源 ID；来源 ID 均在 18 页清单中。 |
| 规则条目覆盖 | 通过 | 当前知识段覆盖规则 1—17。 |
| 来源清单 | 通过 | `sources.csv` 和 `sources.json` 各含 18 个来源；URL、可见 revision ID 和 SHA-256 信息齐全。原始快照哈希在 JSON 元数据中，清洗文本哈希也记录于 CSV。 |
| 现有校验报告 | 通过 | `validation_report.json` 为 PASS，5 个文档、99 个知识段和 18 个来源计数与当前文件一致。 |
| 处理脚本语法 | 通过 | 两个离线构建脚本均可由当前 Python 编译检查。没有运行会重写语料的构建脚本。 |
| RAG 运行环境 | 待准备 | 当前没有 Kotaemon、Embedding 相关包、向量数据库包或本地模型缓存；细节见第 4 节。 |
| Git 元数据 | 不存在 | 项目目录不是 Git 仓库；没有初始化仓库，也未运行 Git diff。 |

**任务 1 判定：**交付物和数据审计验收项均通过。当前缺少 RAG 运行依赖属于任务 2/5 的环境准备事项，不是语料完整性失败。可以进入任务 2；启动结果需按任务 2 另行记录。

## 2. 文件与语料统计

- 原始目录 `data/raw/wikipedia_2026-11-10/` 存有 36 个网页文本快照文件。这些文件包括主快照及补充/页脚片段，不等于 36 个独立网页。
- 来源清单记录 18 个英文 Wikipedia 页面；所有页面有网页中可见的 revision ID。
- 英文清洗输出目录和来源元数据文件存在。
- 中文目录有 5 份主题 Markdown、5 份对应 HTML、中文总阅读 HTML、`chunks_zh.jsonl`、`parallel_zh_en.jsonl`、`corpus_manifest.json` 和 `validation_report.json`。
- `chunks_zh.jsonl`：99 条；重复 ID 0；空中文正文 0。
- `parallel_zh_en.jsonl`：99 条；重复 ID 0；空中文或英文正文 0；与中文 JSONL 的 ID 完全对齐。
- 来源字段：缺少 `source_url` 的记录 0；无效或缺失 `source_lines` 的记录 0；未知 `source_id` 的记录 0。
- 需要规则复核的记录 28 条；`expert_reviewed=true` 的记录 0 条。译文仍不是裁判专家审校文本。
- `data/eval/` 目录存在但为空；评测问题集尚未创建。`data/indexes/`、`reports/` 目录不存在；向量索引与 RAG 评测结果尚未生成。

来源版本边界：18 个 revision ID 是网页页脚可见编号；指定历史 revision 正文未逐页独立回取验证。本次本地内容以保存的文本快照与 SHA-256 固定，不能表述为已由 Wikimedia API 验证所有历史版本。

## 3. 数据完整性检查结果

本次执行的只读检查包括：

1. 读取来源 CSV、英文来源 JSON、中文 corpus manifest 和 `validation_report.json`。
2. 逐行解析两份 JSONL，检查空行、JSON 错误、ID 重复、双语 ID 对齐、文本为空、来源 URL、来源行号格式、来源 ID 和规则条目覆盖。
3. 对 5 份中文 Markdown 重新计算 SHA-256，并与 corpus manifest 比较。
4. 检查 18 条来源记录是否具备 URL、可见 revision ID、许可、清洗文本 hash；并检查 JSON 来源元数据中的原始快照 hash。
5. 用 Python `compile()` 检查 `scripts/build_rules_document.py` 和 `scripts/build_chinese_rules.py` 的语法，不执行生成脚本。

结果：以上检查全部通过。已有 `validation_report.json` 也与本次统计相符。此类结构检查不判断规则事实是否准确、不验证译文质量、不等同于裁判专家校审或 RAG 效果评测。

## 4. 当前运行环境检查

检查环境：项目所用 Python 命令返回 Python 3.9.12。

| 组件 | 检查结果 |
| --- | --- |
| `requests`、`beautifulsoup4` | 已安装 |
| PyTorch | 已安装，版本 `2.8.0+cpu`；CUDA 不可用 |
| `transformers`、`sentence-transformers`、`huggingface_hub` | 未安装 |
| Chroma、FAISS、Qdrant、LanceDB Python 包 | 均未安装 |
| LangChain、LangGraph | 均未安装 |
| Kotaemon Python 模块 / `ktem` | 未安装；项目根目录也没有 Kotaemon checkout |
| Hugging Face、Torch Hub、Sentence Transformers 常见本地模型缓存 | 检查路径均不存在；未发现已缓存 Embedding 模型 |
| Python 构建脚本语法 | `build_rules_document.py`、`build_chinese_rules.py` 均 PASS |

当前没有满足直接运行 RAG 的依赖和本地模型。任务 2 需要固定 Kotaemon 版本并建立运行环境；任务 5 需根据机器资源、模型获取方式和应用兼容性再选择 Embedding 与向量存储。由于当前 PyTorch 是 CPU 构建，若采用本地模型，需先测定可接受的下载体积和 CPU 推理延迟，或选择可用的远程 Embedding 服务；本审计没有连接或调用任何模型服务。

## 5. 文档一致性与修订

审计发现此前文档将计划与实际采集方式混写，且部分状态未随语料完成更新。本次修订了以下文件，没有改动 5 份中文规则文档及任何 JSONL 语料：

- `README.md`：改为说明本批使用网页读取通道生成带行号快照；明确后续 API 采集仍属计划。
- `docs/DATASET.md`：区分本批实际获取方法与未来 API 采集方案；说明当前 CSV 与 JSON 来源元数据分别保存哪些 hash；评测示例改用现有 chunk ID。
- `docs/PROJECT_SCOPE.md`：明确当前 Wikipedia 语料不是固定赛季的 IFAB 官方规则集；赛季问题不得无依据地回答为现行官方规则。
- `docs/DECISIONS.md`：保留原 API 采集方案，并新增 ADR-004 记录网页读取快照这一实际获取通道及版本核验边界。

修订后，README、DATASET、DECISIONS、COLLECTION_LOG、TRANSLATION_LOG 与 TECHNICAL_DESIGN 对实际采集方式的描述一致：本批不是 API 原始响应；18 个页面有可见 revision ID，但历史正文未逐页验证。`sources.csv` 不单独保存 `raw_sha256`，该字段存在于 `sources.json`；这是清单分工，不是来源哈希缺失。

## 6. 风险与待办

| 项目 | 状态/处理 |
| --- | --- |
| RAG 依赖、应用和模型缺失 | 任务 2/5 环境准备；不阻止任务 1 通过。 |
| 评测集尚不存在 | 在任务 4 建立开发集和锁定测试集；不得把现有语料结构 PASS 当成 Recall 或答案准确率。 |
| 28 条知识段带规则复核提示、全部译文未专家校审 | 检索和回答需保留校核元数据；选作标准答案前人工复核。 |
| Wikipedia 是二手概述且不是单一官方赛季规则 | 用户问题若要求官方现行版本，应说明现有资料边界；不可将其当作权威裁判结论。 |
| revision ID 与历史正文未逐页独立核验 | 报告和引用保留核验状态；未来正式抓取需新建版本，不覆盖快照。 |
| 项目没有 Git 元数据 | 遵照约定不初始化；用 `project_file_manifest.json`、数据 manifest 和实验日志追踪。 |
| 生成脚本可能覆盖 processed 输出 | 本次未运行；后续运行前应在独立副本或确认输出变更范围。 |

## 7. 交付物与任务一验收

- 本文件：`docs/PROJECT_AUDIT.md`。
- 文件清单：`data/manifests/project_file_manifest.json`。记录本次审计范围内的相对路径、字节数、SHA-256、类别和用途；不含自身 hash，并排除 `.git`、虚拟环境、缓存、Python bytecode 和密钥文件。
- 没有修改现有 5 份中文文档、中文/英中 JSONL 或 processed 语料输出。

| 任务一交付基线 | 结果 |
| --- | --- |
| 报告区分已完成、待实现和异常/限制 | 通过 |
| 关键目录、来源清单和两个构建脚本存在 | 通过 |
| 来源、文档、JSONL 数量及质量项已统计 | 通过 |
| Python、依赖、模型、向量库、Kotaemon、Git 状态已检查 | 通过；RAG 组件待安装 |
| 中文语料未被修改 | 通过 |
| 文件 SHA-256 manifest 已生成并可复核 | 通过 |

**任务一当时的建议（历史记录）：**进入任务 2，固定 Kotaemon 上游 tag/commit 并尝试启动。任务 2 的后续实际结果已记录在本报告第 10 节。


## 9. 任务二初始环境尝试（设置前历史记录，2026-11-10）

此处记录任务二设置前的首次失败尝试：当时 Python 3.9.12 低于上游要求，GitHub HTTPS 请求失败，固定源码目录不存在；Docker Engine 不可连接，WSL 返回 E_ACCESSDENIED。启动检查脚本因源码缺失退出，应用和三问尚未运行。原始日志见 `reports/task2_environment_check_2026-11-10.log` 与 `reports/kotaemon-baseline-20261110-202156.log`。后续完成情况以第 10 节为准。

## 10. 任务二完成更新（2026-11-10）

后续在固定 checkout `9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9` 上建立 Python 3.10.22 项目隔离环境，使用 Ollama `qwen2.5:3b` 与 `bge-m3`，以 Chroma 为向量存储导入五份中文 Markdown，生成 50 个 Kotaemon 临时 chunk。默认 LanceDB 文档存储在 Windows 初始化时遇到 OS error 5；运行时切换到上游 `SimpleFileDocumentStore` 后五份文档均完成索引。上游 checkout 未修改。

三条中文问题均在真实 UI 中得到回答并显示来源面板，但回答/引用都发现不匹配。原始回答、配置、逐题判定和边界见 `docs/KOTAEMON_BASELINE.md`。因此任务二按“应用运行、三问有结果、来源行为留证”的交付基线通过；答案正确性、引用正确率、正式 RAG B0 和检索指标仍未测。后续任务不得把 50 个临时 chunk 当作 Corpus B0 的 99 个稳定 chunk。成功索引证据见 `reports/task2-indexing-windows-overlay-final-2026-11-10.log`。


## 11. 任务一交付补齐与最终复核（2026-11-10）

原任务一要求保持固定。本次补齐 `docs/EXPERIMENT_LOG.md` 中缺少的 TASK-001-DELIVERY 审计日期、执行命令、实际结果与证据路径；重新读取五份文档和两份 JSONL，核对 5/99/99/18 数量、ID 对齐、来源 URL/行号及校验值。命令为 `.\.venv\Scripts\python.exe scripts/audit_task1_task2.py`，机器结果保存为 `reports/task1_task2_acceptance.json`。

技术设计、任务交付标准和 Corpus B0 以 `data/manifests/task1_task2_baseline_lock.json` 固定；本次未改写这些输入。原有四份报告的既有字节前缀同样纳入检查，补充事实追加在文末，保留早期环境和失败尝试的历史记录。

此前项目清单中的 Ollama 活动日志随服务继续写入而改变。本轮保留旧清单，将活动日志归档为静态快照，并在 `data/manifests/runtime_log_snapshots.json` 逐项记录原路径、归档路径、截取时间、字节数和 SHA-256；`project_file_manifest.json` 对静态快照计算哈希，明确列示活动源日志。完整清单可使用 `.\.venv\Scripts\python.exe scripts/update_project_manifest.py --verify` 只读复核。

本次运行环境为任务二准备后的项目 Python 3.10.22，当前依赖版本、Kotaemon、模型缓存及向量库状态见机器报告。报告前文 Python 3.9/依赖缺失属于首次审计时点；本次不把历史状态改写为当前状态。规则事实和译文的审校边界继续按原记录保留。

原标准逐项交付映射及最终签收记录见 `reports/TASK_01_02_DELIVERY.md`。任务三及其后任务的交付物未计入本次任务一、二验收。


## 12. 任务一二再次排查与补齐（2026-11-11）

本次继续依据原任务一、二验收，未改动技术设计、任务文档、五份中文文档、两个 JSONL 或 corpus manifest。原十个固定输入的 SHA-256 与四份报告旧前缀锁均通过；报告只追加本次实际事实。

任务一进一步把“来源字段存在”核对到可还原内容：18 页来源的 raw/clean SHA-256 均由已有 36 个快照重新计算一致；CSV/JSON 的 URL、revision、许可和正文哈希逐项一致；99 条英文本均能从声明的来源行范围按原清理逻辑还原，且与英中对照数据完全一致。5/99/99/18 数量、稳定 ID、非空正文、规则 1—17、五份文档哈希均通过。该检查证明本地快照追溯一致，不证明 revision 历史正文已经在线逐页验证，也不证明译文已专家校审。

任务二实际重启发现旧检查只定位模块而未真实导入，遗漏了 SOCKS 代理问题；进一步发现分词缓存依赖之前的临时环境变量。现已由进程内网络/缓存准备、真实模块导入检查和资源准备脚本补齐；按同一启动脚本成功启动并重新完成三条中文问答，未复用昨日回答作为今日冒烟结果。完整步骤和非阻塞上游警告追加于 LOCAL_SETUP，逐字问答和质量观察追加于 KOTAEMON_BASELINE。

当前实测 Python 3.10.22、固定 Kotaemon v0.12.0 checkout clean；九项关键包与固定锁文件或 editable 源码一致；Ollama 0.40.16，模型 qwen2.5:3b 与 bge-m3；应用 HTTP 200。项目根目录仍无 Git，未初始化。

完整命令：`.\.venv\Scripts\python.exe scripts/audit_task1_task2.py --live --ui-evidence reports/task2-ui-evidence-2026-11-11.json --model-evidence reports/task2-model-runtime-2026-11-11.json --startup-log reports/kotaemon-startup-cached-2026-11-11.log --output reports/task1_task2_acceptance-2026-11-11.json`。初轮今日机器结果 32/32 PASS，最终以同命令生成的 `reports/task1_task2_acceptance-2026-11-11.json` 和最后执行的文件清单 `--verify` 共同确认。新增检查是对原要求的实际落实，未扩大或降低任务通过条件。今日总交付映射见 `reports/TASK_01_02_RECHECK_2026-11-11.md`；昨天 24/24 报告保留为历史。


## 13. 回答与引用修复后的当前状态（2026-11-11）

用户要求修复三条问答质量后，已在本地运行覆盖层落实稳定ID证据选择、完整知识段摘录、逐请求上下文预算、程序绑定来源和拒答。原三条错误已在实际UI复验修复；开发回归16/16、证据契约19/19、UI与推理记录对应5/5。详细实现及保留的失败历程见 `docs/ANSWER_QUALITY_FIX.md`。本段更新修复后的状态，前文“仍存在三问错误”属于修复前的历史记录。

最终运行在同一固定上游、隔离环境和原Corpus B0上；原技术/任务标准不变，任务3—12的正式交付并未由此全部完成。按原任务一二脚本重新在线验收32/32通过，结果 `reports/task1_task2_after-quality-fix-2026-11-11.json`。源文档与旧报告前缀锁保持一致；无Git初始化。


## 14. 任务三适配与账号交付（2026-11-11）

已完成新schema、构建/独立校验脚本和两份99条派生JSONL，详见 reports/TASK_03_DELIVERY.md。99旧ID可逐条映射、源ID不变；中文/英文按ID合并，不依赖输入排序；父块留空、1个原表格完整保留；所有原来源/许可/翻译/复核元数据及哈希保持对应。

实际主校验18/18、交付复核8/8、16坏数据全部拒绝；两份JSONL重复及新目录构建字节一致。原技术/任务/Corpus B0十文件及四份报告旧前缀校验通过。任务一二也在本轮再次在线只读复核32/32通过，reports/task1_task2_after-task3.json；原五份应用文件和索引保持原状。

本机普通账号yanyanbeen通过管理页面创建并实际登录；凭据存于忽略的.runtime目录，公开证据不包含密码或密码摘要。新账号没有搬取原admin私有文件。项目根目录仍无Git，未初始化。任务四的人工标签及后续正式索引仍按原任务处理。
