# 任务一至三逐项复核与补交付报告

日期：2026-11-11（Asia/Shanghai）。原技术设计、任务定义与交付基线不变。

## 结论

**前三项任务按原标准完成，本次补齐公开仓库交付缺项，并实际重新执行验收。** 这不表示任务四至十四或整个 RAG 项目完成。

开始时原任务一二检查为 31/32：语料和文件检查通过，本地应用与模型服务未运行。按原配置恢复后，在线验收为 32/32。失败记录与修复后的记录均保留，没有用历史 PASS 覆盖初始失败。

## 逐项交付基线

| 任务 | 原要求 | 本次核对结果与交付 |
| --- | --- | --- |
| 1 | PROJECT_AUDIT 区分完成/待做/异常 | 原报告保留，当前变更补充于本报告、DELIVERY_STATUS 与 TASK_01_03_SUPPLEMENT |
| 1 | 文件清单包含路径、字节、SHA-256、用途 | 原本机清单复核 177 项、10 个快照、0 错误；新 checkout 补交规定路径的当前清单与验证工具 |
| 1 | EXPERIMENT_LOG 记录命令和结果 | 追加本次补交付条目，保留原有内容和冻结前缀 |
| 1 | 5 文档/99 段/18 来源，ID 唯一、英中对应、来源可追溯 | 原验收脚本重算原文/清洗哈希并重建 99 段英文摘录，检查通过 |
| 1 | 不改原文档；Git 不存在时不初始化 | 原工程 178 个静态文件未变、仍无根 Git；新仓库 Git 是后续用户单独授权建立 |
| 2 | 固定上游、许可、Python 与依赖 | Kotaemon v0.12.0 / 9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9；Python 3.10.22；关键依赖匹配锁文件 |
| 2 | 启动、关闭、常见问题、非敏感配置和启动器 | 原文档/启动器保留；实际恢复本地应用和 Ollama，四个关键运行模块真实导入成功 |
| 2 | 至少 3 个中文问题得到结果，日志/截图证明运行 | 已有真实 UI 三问按原哈希核对并交付摘要；新启动日志与 HTTP 200 已交付；本轮另外实际重跑 16 条后端开发题 |
| 2 | 记录默认模型、存储、分块、Top-K、引用行为 | 原 KOTAEMON_BASELINE 保留；重查本地 qwen2.5:3b、bge-m3、Chroma、兼容文档存储、1024/256 与 Top-K10 |
| 3 | Schema、构建/校验脚本、两份新 JSONL、机器报告及摘要 | Schema 和原构建/校验脚本不变；两份 JSONL 各99条；本地文件与版本清单相符；新隔离复核报告已交付 |
| 3 | 99 个旧 ID/source ID 不变，按 ID 对齐，URL/行号有效 | 主校验 18/18、原 suite 8/8；英文倒序后仍按 ID 合并，来源边界保留 |
| 3 | 不覆盖输入，不虚构父块/审校状态 | 隔离 suite 执行前后原 checkout 输入一致；98 paragraph、1 table、99 parent=null；16 类重新计算哈希后的坏数据仍全部拒绝 |

## 本次实测结果

| 检查 | 结果 | 机器证据 |
| --- | --- | --- |
| 原任务一二在线验收 | 32/32 PASS | acceptance/task1_task2_recheck.json |
| 任务三独立数据校验 | 18/18 PASS | acceptance/task3_recheck.json → canonical_validation |
| 原任务三交付 suite | 8/8 PASS | 同文件 → original_delivery_suite |
| 重新计算哈希的坏数据拒绝 | 16/16 | 同文件 → negative_cases |
| 16 条开发问答回归 | 16/16 PASS | acceptance/development_regression_summary.json |
| 引用/证据契约 | 19/19 PASS | acceptance/answer_quality_contract.json |
| 原工程静态文件 | 178 项未变 | acceptance/original_inputs_preserved.json |

完整统一入口 `scripts/recheck_tasks_01_03.ps1` 已实际执行，不仅检查各脚本是否存在。汇总为 `acceptance/task123_recheck_summary.json`。

## 证据范围与限制

当前验收分为：原工程的真实既有运行环境、新公开 checkout 的数据/覆盖层代码，以及原日期的真实 UI 三问。`evidence/runtime_code_correspondence.json` 核对关键运行文件和配置一致；没有声称在全新环境重新安装全部依赖。

本次没有在浏览器重新提交三问；16 条新结果来自本地后端开发回归。历史 UI 证据标明原日期、来源文件哈希、问题、答案哈希和来源链接；完整回答留在原本机报告。当前浏览器能够打开应用并显示原普通账号登录状态。新账号没有自动获得 admin 的私有文档，这不属于前三项任务的正式索引导入。

启动时出现可选 GraphRAG/LightRAG 未安装与远程 tokenizer 请求失败后回退等既有警告；实际应用、本地模型、所需 tokenizer、问答回归和引用契约检查通过。没有把可选功能描述为可用。

数据全文、完整模型输出、账号、索引、数据库、缓存不公开。所有新增文件清单、源代码修改、报告和复核入口通过新仓库的补交付 PR 记录，原有其他仓库不写入。当前清单用 `scripts/manage_delivery_manifest.py --verify` 只读核对，清单自身不递归列入哈希。
