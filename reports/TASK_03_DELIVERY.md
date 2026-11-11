# 任务三交付报告

日期：2026-11-11；结论：**任务三按原交付基线通过并交付。**

同时完成本机 Kotaemon 普通账号 `yanyanbeen` 的创建和真实登录。密码保存在被忽略的 `.runtime/kotaemon-account.json`，使用说明见 `docs/LOCAL_ACCOUNT.md`。

## 1. 原要求与完成情况

依据 `docs/DEVELOPMENT_PLAN_AND_REPORT.md` 原“任务 3：定义统一数据结构并适配现有语料”。技术设计、任务交付规则及原 Corpus B0 不变；本报告更新实际进度，不修改冻结计划中的历史状态。

| 原交付基线/通过条件 | 本轮结果 | 证据 |
| --- | --- | --- |
| Schema 定义字段、空值、稳定 ID 和版本升级 | 已交付 1.0.0；43 个中文字段，对照另加英文及其哈希；parent null、未知修订时间 null | `docs/RAG_DATA_SCHEMA.md` |
| 构建与校验脚本 | 已交付；按 ID 合并，独立对照原文件校验 | `scripts/build_rag_dataset.py`、`scripts/validate_rag_dataset.py` |
| 两份新 JSONL | 中文 99 条、英中对照 99 条；原文件不覆盖 | `data/processed/rag_chunks_zh.jsonl`、`rag_chunks_parallel.jsonl` |
| 99 个旧 ID 均可映射，源 ID 不变 | old_id = id = chunk_id；原 source_id 全部保留 | dataset manifest 的 99 项 id_mapping；校验报告 |
| 中文与英文按 ID 对齐 | 正文和元数据逐 ID 对比通过；英文输入倒序的内存检验仍产生相同结果 | 校验报告；delivery verification |
| 每条中文有真实来源 URL 和有效行号 | 原 URL、source_id 和 source_lines 原样保留并核对来源清单及快照 | 校验报告相应 checks |
| 版本/许可/翻译/复核/哈希规范化 | 页面与摘录哈希分开；署名、许可、原 revision 状态及全部复核提示保留 | Schema、两份 JSONL、dataset manifest |
| 不虚构父子关系和表格类型 | 99 个 parent_id 全为 null；98 paragraph、1 table；点球表 L14-04 全段保留 | 结构及表格完整性检查 |
| 不夸大修订核验或审校状态 | source_revision_verified=false、revision timestamp=null；专家审校为 0，28 条复核提示保留 | 数据/manifest/校验报告 |
| 校验 JSON 和摘要 | 主校验 18/18、交付复核 8/8、16/16 坏数据被拒绝 | `task3_dataset_validation.json`、`task3_delivery_verification.json` |
| 输入原文件不被覆盖 | 原十文件哈希及四份报告旧前缀一致；覆盖保护实测有效 | 主校验与派生输出目录保护复核 |

## 2. 实际数据摘要

| 项目 | 数量/值 |
| --- | --- |
| 原中文分卷 | 5 |
| 中文/对照记录 | 99 / 99 |
| 唯一稳定 ID | 99 |
| 来源清单页数 / 本批实际引用页数 | 18 / 17；总览来源仍在原清单，不伪造对其的引用 |
| 未推断父块 | 99 条 parent_id=null |
| 结构类型 | 98 paragraph、1 table、0 unknown |
| 有复核提示 / 专家审校 | 28 / 0 |
| 中文文件大小 | 302,368 bytes |
| 英中对照文件大小 | 400,859 bytes |
| 适配数据版本 | corpus-b0-rag-adapter-1.0.0 |
| dataset_content_id | 77aea70e0e19e08b4bf3f041e22af8d5c979416cc43b7670a6ef702ee26edce0 |

中文文件 SHA-256：`05dcd08126b5c71031ebe025f1a4ed1b73e00f71007b60ac0a3e0814f386a0b3`。英中对照文件 SHA-256：`3e3167bd3590c66c58d617796e5495440ac219cd9599245aee02ca810dd36467`。

完整输入、输出、两个实现脚本和 Schema 的哈希见 `data/manifests/rag_dataset_manifest.json`。正文不清洗、不 strip、不重译、不截断；保留原中文条件、例外、表格和校核提示。

## 3. 实际执行与验收

项目隔离 Python 3.10.22，Windows；转换、校验均只用 Python 标准库，无 Embedding/LLM 调用，也无新增模型下载。

```powershell
.\.venv\Scripts\python.exe scripts/build_rag_dataset.py
.\.venv\Scripts\python.exe scripts/validate_rag_dataset.py
.\.venv\Scripts\python.exe scripts/verify_task3_delivery.py
```

以上均实际运行并退出码 0。

主校验独立读取原输入，18/18 通过。交付复核 8/8 包含：原数据校验、原位置重复构建字节一致、新目录重建字节一致、新目录独立校验、反序英文输入仍按 ID 对齐、禁止向原输入目录输出、全部坏数据拒绝以及故障注入后原交付仍完好。

16 类故障都只在 `.tmp/task3-verification/` 的派生副本上注入：重复 ID、缺记录、改源 ID、假 URL、无效行号、虚构 parent、伪称 revision 已核验、伪称专家审校、删复核说明、改中文、改英文、截断表格、表格错标 paragraph、bool 充整数行号、缺必填字段、假 provenance。修改后的记录和文件哈希会重新计算，独立校验仍全部拒绝。原 JSONL、五份文档和当前应用索引未参与写入。

原始命令、输出、退出码、各故障触发的失败检查保存在 `reports/task3_delivery_verification.json`；失败是故障样例的预期结果，正式派生数据保持 PASS。

## 4. 账号交付

使用 Kotaemon 的 Resources → Users → Create user 创建普通账号，并在退出 admin 后用新账号登录；Settings 实际显示 `Current user: yanyanbeen`。数据库只读查询确认普通用户及密码摘要与本机凭据相符，报告不导出密码或摘要。

已有 admin 和五份已索引文件未移动、未重设权限；当前浏览器保持登录 yanyanbeen。注册证据 `reports/kotaemon-account-creation-2026-11-11.json`；取用密码的方法见 `docs/LOCAL_ACCOUNT.md`。

## 5. 工作流维护与范围

- 新权威字段说明：`docs/RAG_DATA_SCHEMA.md`。
- 实际过程：`docs/EXPERIMENT_LOG.md` 的 TASK-003；当前状态追加在 README、DATASET 和 PROJECT_AUDIT。
- 本轮实验索引：`reports/all_experiments_summary.csv`、`reports/resume_evidence.md`、`data/manifests/experiment_manifest.json`，仅登记真实数据适配，不填检索/答案成绩。
- 项目根目录仍无 Git 元数据；未初始化 Git。旧 159 文件清单归档为 `reports/archive/task3_2026-11-11/project_file_manifest.before-task3.json`。
- 新账号凭据和数据库留在忽略的本机运行目录；文件清单只冻结公开交付范围的静态文件，已有活动日志继续按静态归档机制处理。

本轮完成任务三的数据适配交付。任务四人工标签、任务五正式索引及后续正式 RAG B0 继续按原标准执行；本轮不申报 Recall、MRR、答案准确率或性能收益。Wikipedia 二手资料和未专家审校的来源边界保持原样。
