# 数据与评测集规范

最后更新：2026-11-10

## 已选来源与当前状态

- 站点：英文 Wikipedia（Wikimedia），主条目：[Laws of the Game (association football)](https://en.wikipedia.org/wiki/Laws_of_the_Game_%28association_football%29)。
- 抓取范围：主条目和它直接链接的规则专题页；按页面标题白名单抓取，不全站遍历。
- 语言：来源为英文；已对主要规则段落完成中文翻译整理，并生成独立中文知识段。中文问答可先使用该中文语料；英中对照另存，避免检索时必须依赖跨语言召回。
- 本批实际获取方式：网页读取通道保存带行号的文本快照，并非 Wikimedia API 响应。原计划的 API 采集尚未实现；后续若实现，须设置有识别信息的 User-Agent，串行请求、使用 maxlag、缓存并遵守 429/Retry-After。不得把当前快照描述为 API 原始数据。
- 许可：Wikimedia 说明大多数 Wikipedia 文本采用 CC BY-SA 4.0；采集时保存页面实际许可、revision ID、标题/URL、来源和抓取时间。应用显示来源与许可说明；公开改编语料时遵循署名和相同方式共享要求。代码与语料许可证分开声明。
- 可靠性边界：Wikipedia 是社区编写的二手概述，可能遗漏、过时或有误，不是 IFAB 官方规则全文。回答需标注资料性质并链接原页面；如需声称回答依据官方现行规则，必须另获 IFAB 授权并加入合法来源。
- 当前抓取状态：2026-11-10 补抓10个缺失的页脚修订号后，18个来源均有页面可见的 revision ID，英文清洗正文共146,474字符。补充修订信息时取得的少量正文也已并入英文快照。
- 实际获取通道：本机直连 Wikimedia API 超时，且本机代理不可用；本次使用网页读取通道，保存带行号的提取文本快照，不是网站原始 HTML/API JSON。读取通道可能返回缓存。
- 版本记录：18个页面可见修订号已补齐。尝试回取指定修订号的历史页面时，读取通道返回 cache miss，因此不能宣称每个历史版本正文都已独立校验。继续使用本地原文与译文的 SHA-256 固定本次语料，未伪造修订时间。
- 输出目录：data/processed/wikipedia_2026-11-10/。主文档为「足球规则资料_网站采集版.md」及同名 HTML；离线重新整理可运行 scripts/build_rules_document.py。
- 中文输出：data/processed/wikipedia_zh_2026-11-10/，5份专题 Markdown 和各自 HTML、中文总阅读页、chunks_zh.jsonl、parallel_zh_en.jsonl 以及 corpus_manifest.json。中文99段，共20,601字符（其中汉字18,000），每段正文中位数203字符、最大425字符。这是字符统计，不是 token 统计。
- 翻译范围：主要规则正文的中文翻译和结构整理，对应英文来源摘录87,419字符；其余材料研究、历史、部分重复例子和非规则说明不计为已译。原始英文仍保留。具体过程见 TRANSLATION_LOG.md。
- 规则校核：99段中28段带有版本或来源简化提示，已标记 metadata.needs_rule_review；所有译文尚未经过足球裁判专家审校。带提示的段落不得未经审校直接充当现行赛季评测的标准答案。

## 语料来源与版本

首轮语料限定为上述 Wikipedia 文章和其直接链接的规则专题页。规则页覆盖 Laws 1–17 的标题与相关内容，避免全站抓取。当前 18 页均记录网页页脚可见 revision ID，但历史版本正文未逐页独立回取验证；本次实际内容以保存的快照和 SHA-256 为准。未来若重新获取或验证历史 revision，应新建语料版本并单独评测，不覆盖本次快照。

来源记录的目标逻辑字段至少包含：
source_id,title,publisher,edition,language,url,revision_id,revision_timestamp,downloaded_at,sha256,license,attribution,local_filename

当前 `data/manifests/sources.csv` 保存来源 ID、标题、语言、URL、可见 revision ID、获取日期、清洗文本 SHA-256、许可和获取方式；`data/processed/wikipedia_2026-11-10/sources.json` 保存更完整的来源元数据、快照文件清单以及原始/清洗文本哈希。两者用途不同，不应将 CSV 中不存在的字段误报为来源缺失。

下载后保存响应快照的 SHA-256。不要以“今天的 Wikipedia 页面”作为可复现版本，必须固定 revision ID。

## 版权与分发

Wikimedia API 可用于程序化获取内容，但必须遵守其 API 使用规则：设置描述性 User-Agent、串行/低速读取、使用 maxlag、缓存并尊重 429/Retry-After。逐页核验 CC BY-SA 许可和可能的第三方内容。语料文件单独标注作者归属链接、源 URL、许可链接、revision ID 和修改说明；改编文本按兼容的 ShareAlike 条款共享。代码许可证不会自动改变语料许可证。

## 目录约定

- data/raw/：API 原始响应，只作输入，默认不进 Git。
- data/processed/：清洗文本和 chunks，由固定 revision 快照生成，默认不进 Git。
- data/eval/：人工核对的查询与标签。确认可分发后再提交。
- data/manifests/sources.csv：来源版本、许可和校验值清单。

## 评测集字段建议

以下是字段示意，不是已创建的评测数据。基于当前语料构建正式评测集时，检索相关性应优先标注现有稳定知识段 ID（例如 `L11-03`），并另存对应页面 `source_id` 供引用核验：

{"id":"offside-001","question":"越位犯规如何判定？","expected_chunk_ids":["L11-03"],"expected_source_ids":["wiki-11"],"answerable":true,"topic":"offside","difficulty":"basic","split":"dev"}

答案评测另存参考要点和应引用的规则页/段落 ID。重切分实验不得覆盖 Corpus B0 的 chunk ID；新旧 ID 映射需单独保存，以便同一评测题能在不同切分方案间追踪证据。

## 样本设计

- 覆盖规则 1–17、条件/例外、重启方式、处罚、术语和跨段落问题。
- 覆盖可回答与不可回答题；区分资料外、版本不明确和证据不足。
- Hard negative 是主题相近但不支持目标答案的段落，记录理由并人工抽查。
- 先做 30–50 条试集验证切分和指标，再扩到正式集；锁定测试集不用于调参。
- 200 queries/40 hard negatives 可作为后续目标，不是已完成事实。
- Wikipedia 二手资料中如发现与 IFAB 现行规则冲突，记录为来源差异，不静默修正原文；此语料不能作为权威裁判结论。


## 任务三统一适配已交付（2026-11-11）

新Schema权威说明为 `docs/RAG_DATA_SCHEMA.md` 1.0.0。原 metadata 全量展开到顶层；新中文与英中JSONL各99条，id/chunk_id等于原ID，source_id不变。中文正文和英文摘录原样保留，来源 URL、行号、可见revision、许可/署名、翻译方法、28条复核提示和审校边界均保留。

新文件为 data/processed/rag_chunks_zh.jsonl、rag_chunks_parallel.jsonl；输入/输出/实现哈希与99项映射在 data/manifests/rag_dataset_manifest.json。99条parent_id=null，98 paragraph、1 table；L14-04含表格的整个知识段不拆分。来源清单仍18页，本批99条实际引用17页，总览页的来源记录没有被删除或伪造为某段引用。

主校验报告 reports/task3_dataset_validation.json：18/18 PASS。交付复核 reports/task3_delivery_verification.json：8/8 PASS，16类注入损坏全部拒绝；包括在重新计算派生行/文件哈希后仍发现内容、来源或审校状态改变。原始语料及技术/任务要求未覆盖，未新增官方赛季或专家审校承诺。本次不建立人工评测标签或正式检索索引。
