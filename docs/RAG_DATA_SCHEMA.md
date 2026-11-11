# 任务三：统一 RAG 数据结构

版本：1.0.0；数据版本：`corpus-b0-rag-adapter-1.0.0`。依据原 DEVELOPMENT_PLAN_AND_REPORT 的任务三；不修改技术设计或原任务交付标准。

## 1. 输入与输出

输入为 Corpus B0 的 `chunks_zh.jsonl`、`parallel_zh_en.jsonl`、corpus manifest、五份 Markdown，以及既有 `sources.json`/`sources.csv`。原文件全部只读，不抓取、不重译、不切分。转换按 ID 关联，不依赖两份输入文件的行顺序相同。

输出：

- `data/processed/rag_chunks_zh.jsonl`：99 条中文记录。
- `data/processed/rag_chunks_parallel.jsonl`：99 条英中对照记录。
- `data/manifests/rag_dataset_manifest.json`：输入/实现/Schema/输出 SHA-256、数量、旧 ID 映射和版本边界。
- `reports/task3_dataset_validation.json`：独立校验结果及运行时间；不作为问答准确率评测。

JSONL 使用 UTF-8、每行一个完整 JSON 对象、LF 换行、对象键排序。数据和 dataset manifest 不含变化的执行时间，重复构建可以得到相同正文文件；运行日期记录在验证报告和 EXPERIMENT_LOG。

原 `metadata` 字段完整展开到记录顶层，字段值原样保留。`content_zh` 为原 `parallel_zh_en.text_zh`，与原中文 `text` 去掉首段标题路径后的正文完全相同；正文不做 strip、改字或换行替换。标题路径单独保存，供后续任务五组装检索文本。中文文件不包含英文正文；对照文件在相同记录上补充英文正文及哈希。

## 2. 字段与类型

以下字段除明确允许 null 或空数组外均必填；不允许用空字符串代替缺失值。

| 字段 | 类型/允许值 | 定义 |
| --- | --- | --- |
| `schema_version` | string；`1.0.0` | 当前结构版本 |
| `dataset_version` | string；`corpus-b0-rag-adapter-1.0.0` | 本次适配规则版本 |
| `id` / `chunk_id` | string，二者相同 | 原稳定 ID，如 L11-03；与旧 ID 一一对应 |
| `parent_id` | string 或 null；本批均 null | 没有可靠父块 ID，不从标题或相邻行推造关系 |
| `chunk_type` | `paragraph` / `table` / `unknown` | 结构类型；不猜测 definition/exception 等语义标签 |
| `title_zh` | 非空 string | 原英中对照的中文单元标题 |
| `content_zh` | 非空 string | 原中文正文，保持所有条件、例外、表格和校核提示 |
| `content_en` | 非空 string，仅英中对照文件必填 | 与同一 ID 对应的原始英文摘录 |
| `document_id` / `document_title` | 非空 string | 原中文分卷 ID 与名称 |
| `section_path` | 非空 string 数组，本批三层 | 分卷、规则标题、知识段标题；末项等于 title_zh |
| `law_number` | integer，1—17；bool 不算 integer | 原规则号；不从 ID 字符串重新猜测 |
| `source_id` / `source_title` | 非空 string | 既有来源 ID 和 sources.json 中的页面标题 |
| `source_url` | HTTPS URL | 来源页面 URL；不是新造的链接 |
| `source_language` | string；本批 `en` | 英文来源语言 |
| `source_lines` | 两个正整数 `[start,end]`，start ≤ end | 保存的网页读取快照行号；不是浏览器当前页面的行号 |
| `source_revision_id` | 非空数字 string | 读取快照页脚可见修订号；保持字符串类型 |
| `source_revision_status` | 非空 string，原值 | `reader footer ID; exact revision not independently fetched` |
| `source_revision_timestamp` | string 或 null；本批 null | 精确 revision 时间未知，不把抓取日当修订日 |
| `source_revision_verified` | boolean；本批 false | 未独立回取并核验全部指定历史版本正文 |
| `source_acquisition_method` | 非空 string | 本批 `web_reader_extracted_text`，不改称 API 或 HTML |
| `source_acquired_date` / `snapshot_date` | YYYY-MM-DD string | 来源获取日和中文元数据中的快照日，分别保留 |
| `source_raw_files` | 非空相对路径数组 | 来源清单里的既有本地快照路径 |
| `source_attribution` / `contributors_url` | 非空 string / HTTPS URL | 原署名与作者历史链接 |
| `license` / `license_url` | 非空 string / HTTPS URL | 本批 CC BY-SA 4.0 及许可链接 |
| `language` | string；本批 `zh-CN` | 原中文 metadata 的语言；对照文件也保留原值，不冒充英语已翻译 |
| `translation_method` | 非空 string | 保留 AI 翻译及编辑选择说明 |
| `translation_status` | string；本批 `ai_translated_unreviewed` | 机器整理、尚未专家审校；不升级为人工确认 |
| `official_translation` / `expert_reviewed` | boolean；本批均 false | 保留非官方翻译、无专家审校边界 |
| `needs_rule_review` | boolean | 保留原复核标志，28 条为 true |
| `review_notes` | string 数组，可为空 | 原提示逐条保留；本批 true 标志必须有说明 |
| `translated_body_sha256` | 64 位十六进制 string | 原中文正文 SHA-256，字段名和值不变 |
| `source_text_sha256` | 同上 | 原单元英文摘录 SHA-256，不是整页哈希 |
| `content_zh_sha256` | 同上 | 等于 translated_body_sha256；计算对象为 content_zh 的 UTF-8 字节 |
| `content_en_sha256` | 同上，仅对照文件必填 | 等于 source_text_sha256；计算对象为 content_en |
| `source_page_raw_sha256` | 同上 | sources.json 中整页合并快照 raw_sha256 |
| `source_page_clean_sha256` | 同上 | sources.json 中整页清洗正文 text_sha256 |
| `provenance` | 对象 | chinese_input、parallel_input、source_manifest 三个项目相对路径 |
| `record_sha256` | 64 位十六进制 string | 除本字段外所有字段的 canonical JSON SHA-256；中文和对照记录分别计算 |

Canonical JSON：UTF-8、`ensure_ascii=False`、`sort_keys=True`、`separators=(',', ':')`、禁止 NaN。正文内容哈希不包含 JSON 引号、标题前缀或尾部 JSONL 换行。

## 3. 类型判定与父子关系

`table` 只在发现 Markdown 表头和至少两个对齐单元格的分隔行时使用。整个知识段保留，包括表格前的条件、全部表头/数据行和后的校核提示，不把表格拆成独立小格。本批明确表格为 L14-04。

没有表格标记、代码围栏或混杂 HTML 的纯段落标为 paragraph；有无法确定结构的管道符、代码或 HTML 时标 unknown。当前不凭内容猜测“定义/例外”类型。所有 99 条 parent_id 都为 null；document_id 和 section_path 仅用于归属/导航，不自动当作父块 ID。

## 4. 稳定 ID 与版本升级

- 本次 `id == chunk_id == old_id`，source_id 原样保留。manifest.id_mapping 列出全部 99 个映射；重新排序不重编号。
- 新增可空兼容字段可以升级 schema 次版本；字段重命名、语义/类型变化需主版本升级，并同步两个脚本和本文件。
- 新抓取、新翻译或修改原规则事实必须产生新 corpus/dataset 版本，保留旧数据及输入哈希。
- 后续切分实验为子块生成新 ID，并保存旧 ID 到 parent 的明确映射；本次不提前制造父子结构。
- dataset_content_id 是两份 JSONL 字节用 NUL 分隔后 SHA-256；变化能被识别，不能代替 revision 正文核验或质量标签。

## 5. 构建、校验与验收

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe scripts/build_rag_dataset.py
.\.venv\Scripts\python.exe scripts/validate_rag_dataset.py
```

构建器先检查原十文件固定锁，再按 ID 合并、核对正文及元数据和来源。所有输入检查和覆盖检查完成后才写新文件。已有派生输出若相同直接复用；若不同默认失败，可选新输出目录，或在明确重建派生文件时加 --overwrite。原始语料目录和任何输入路径始终禁止覆盖。

独立重建示例：

```powershell
.\.venv\Scripts\python.exe scripts/build_rag_dataset.py --output-dir .tmp/task3-rebuild
.\.venv\Scripts\python.exe scripts/validate_rag_dataset.py --data-dir .tmp/task3-rebuild --report .tmp/task3-rebuild/validation.json
```

校验器独立读取原输入，不调用构建器的转换/分类函数。检查输出行数、重复 ID、缺值/类型、中文与英文按 ID 对齐、原元数据完整保留、source URL/ID/行号/许可/版本、正文/记录/文件哈希、parent null、表格全段完整性以及输入原文件不变。错误保存为 JSON，退出码 1；全部通过退出码 0。异常来源或元数据不能通过重算派生文件哈希来洗成合法内容。

任务三完成只表示统一数据适配和可追溯校验完成；正式索引、人工标注集和 RAG B0 按原后续任务推进。
