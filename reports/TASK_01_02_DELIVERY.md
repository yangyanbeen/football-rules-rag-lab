# 任务一、任务二交付签收记录

日期：2026-11-10（Asia/Shanghai）  
结论：**任务一通过并交付；任务二按原运行验收标准通过并交付。**  
机器验收：`reports/task1_task2_acceptance.json`，24/24 项检查通过。文件清单在所有交付内容保存后使用 `scripts/update_project_manifest.py --verify` 复核。

## 1. 固定依据与本次范围

依据是 `docs/TECHNICAL_DESIGN.md` 和 `docs/DEVELOPMENT_PLAN_AND_REPORT.md` 原有任务一、二。本次补齐遗漏的审计日志、实际依赖版本、分块参数和日志归档，不增加任务编号，不改变原任务范围、交付物或通过条件。

`data/manifests/task1_task2_baseline_lock.json` 保存补齐前的技术文档、任务文档、五份 Markdown、两份 JSONL 及 corpus manifest 的 SHA-256，共 10 个固定文件。最终检查确认这些文件字节未变。四份既有交付报告的原文前缀也有字节长度与 SHA-256，最终核对一致；事实补充追加在文末。

## 2. 任务一逐项交付

| 原要求 | 实际结果 | 交付证据 |
| --- | --- | --- |
| 审计数量与 Corpus B0 一致 | 5 份文档、99 条中文、99 条英中对照、18 页来源、36 个 raw 快照；规则 1—17 覆盖 | `reports/task1_task2_acceptance.json` 的 task1 |
| ID 唯一、正文非空、双语对齐 | 99 个唯一 ID，两侧集合相同；无空中文/英文；双语内容哈希一致 | 同上；原 JSONL 保留 |
| 来源可追溯、行号有效 | 99/99 有 URL、来源 ID 和有效行范围；来源版本、许可、快照存在 | 同上；`data/manifests/sources.csv`、英文 `sources.json` |
| 五份原文不被修改 | 5/5 SHA-256 与 corpus manifest 一致，固定输入哈希一致 | `data/manifests/task1_task2_baseline_lock.json` |
| 区分已完成、待实现、异常和风险 | 保留原审计报告与历史环境，文末追加本次补验和当前环境出处 | `docs/PROJECT_AUDIT.md` 第 11 节 |
| 文件清单含路径、大小、SHA-256、用途 | 静态文件和日志归档快照纳入完整项目清单；可只读验证哈希与覆盖范围 | `data/manifests/project_file_manifest.json` |
| 实验日志记录审计日期、命令、结果 | 已补 TASK-001-DELIVERY 条目，并记录本次真实补验命令和结果 | `docs/EXPERIMENT_LOG.md` 文末 |
| 环境检查有记录；无 Git 时不初始化 | 本次 Python 3.10.22、依赖/模型缓存状态有机器快照；根目录仍无 Git | 机器报告 task1.supplement_environment；原报告保留首次审计状态 |

两个原始语料构建脚本仅做 compile() 语法检查，本次没有执行会改写语料的重建命令。28 段规则复核提示、专家审校数 0 的来源边界仍保留。

## 3. 任务二逐项交付

| 原要求 | 实际结果 | 交付证据 |
| --- | --- | --- |
| 固定仓库/tag/commit、许可证、来源与日期 | Cinnamon/kotaemon v0.12.0 / `9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9` / Apache-2.0；本机 tracked source clean | `docs/UPSTREAM_VERSION.md`；机器报告 |
| 隔离环境并记录 Python 与关键依赖 | 项目 `.venv` Python 3.10.22；九项关键包实际版本已逐项核对锁文件/固定源码 | `docs/KOTAEMON_BASELINE.md` 文末；机器报告 task2.dependencies |
| 准备、启动、停止和常见错误说明 | 保留原说明；追加本机 uv/Ollama 路径、模型缓存、命令和应用模型字段 | `docs/LOCAL_SETUP.md` 文末 |
| 启动脚本及真实运行证据 | 启动检查退出码 0；应用实际 HTTP 200；原索引和应用日志存在 | `scripts/run_baseline_check.ps1`；`reports/kotaemon-baseline-20261110-232421.log`；UI 原始证据 |
| 记录 Embedding、存储、分块、Top-K、LLM 和引用行为 | bge-m3 / Chroma + SimpleFile 兼容覆盖层 / TokenSplitter 1024 tokens、overlap 256 tokens / Top-K 10 / qwen2.5:3b / 原三问引用表现 | `docs/KOTAEMON_BASELINE.md`；机器报告 task2 |
| 至少三个中文问题得到结果 | Q1 越位、Q2 直接任意球、Q3 球门球均有原始回答；Information panel 存在 | `reports/task2-ui-evidence-2026-11-10.json`，含时间、URL、HTTP 状态、回答及页面原文 |
| 不以应用临时切分替代正式知识索引 | 5 个文档、50 个应用临时 chunk；99 个原始稳定知识段继续作为 Corpus B0 | 索引日志、SQLite 只读统计与固定输入检查 |
| 不提交真实服务密钥 | 模型服务为本机 Ollama；新增配置证据只保存适配类、模型和本机端点，未导出 api_key | 基线记录与 `task2-model-runtime-2026-11-10.json` |

当前分块参数由 SQLite File Collection 的继承设置与固定 route() 默认值解析得到：chunk_size=0 / chunk_overlap=0 表示继承，实际 1024/256；计数 tokenizer 默认是 tiktoken 的 cl100k_base。模型名称与 digest 单独保存，当前 Ollama server 为 0.40.16。

本机 Windows 默认 LanceDB 文档存储初始化曾出现 OS error 5，已由项目启动器在运行时换用上游 SimpleFileDocumentStore；固定上游源码保持一致。失败尝试作为历史证据保留。

## 4. 日志冻结与文件清单

此前哈希不一致来自持续增长的 Ollama 活动日志，五份语料始终一致。本次保留旧清单 `reports/archive/task1_task2_2026-11-10/project_file_manifest.before-supplement.json`，将两个活动服务日志截取为静态归档，逐项登记于 `data/manifests/runtime_log_snapshots.json`。

项目清单明确列出这两个活动原路径，归档副本参与完整 SHA-256 验证；其他交付文件继续逐文件验证。运行服务继续写入活动日志时，归档证据与已交付哈希保持稳定。`--verify` 同时检查文件大小、哈希、未列入清单的文件、缺失文件和归档映射。

## 5. 复核命令与结果边界

在项目根目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_baseline_check.ps1 -CheckOnly
.\.venv\Scripts\python.exe scripts/audit_task1_task2.py
.\.venv\Scripts\python.exe scripts/update_project_manifest.py
.\.venv\Scripts\python.exe scripts/update_project_manifest.py --verify
```

首次补验机器结果为任务一 PASS、任务二 PASS、24/24。最终清单在本记录和机器结果保存后生成，`--verify` 必须零错误才完成签收。

原三条回答存在内容或引用错误，原始答案完整保留。原任务二要求验证运行并记录结果，没有答案准确率门槛；本次按原要求验收，后续仍按原任务中的检索、引用绑定、拒答和答案评测要求处理这些缺陷。正式 RAG B0、Recall/MRR/nDCG、答案/引用准确率及性能收益均未测，本次不计为成果。
