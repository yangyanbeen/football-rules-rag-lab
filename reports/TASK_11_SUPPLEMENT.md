# 任务十一缺陷补交付

日期2026-11-13。基线PR22/e542340，分支fix/task-11-delivery-audit，版本v0.11.1-task11-audit；发布结果以GitHub合并记录为准。原技术/执行要求不变。

## 已修复

修复配置部分字段漏验、来源/字符区间关联、预算重复与评分丢题、索引ID/词项/向量复用校验、主异常覆盖、历史源码绑定、运行清单/计数/串行时钟以及父块查询回执来源问题。详见[当前审查说明](../docs/TASK_11_AUDIT.md)。17项接口缺口及4项有效对照在隔离环境复现，不冒充线上事故或评测题。

实际只修改五份既有模块：structure_aware_chunking、structure_retrieval_eval、structure_retrieval_live、run_structure_comparison、query_parent_child。固定1.0配置和正式实验输出原样保留，新查询及父块证据另用1.1回执；旧无版本查询仅按原已发布字节兼容。

## 验收

| 范围 | 最终结果 | 证据 |
| --- | --- | --- |
| 原缺口复现 | 21/21 | reproduction-final-v2.json；17反例+4有效对照 |
| 新修复回归 | 32/32 | regressions-complete.json，绑定当前修复代码 |
| 原专项合同 | 46/46 | contract-current.json，包含原开发保存结果复算 |
| 当前独立公开复验 | 16/16 | public-current.json，Python -S、7种重新哈希错误记录拒绝 |
| 原发布版历史门禁 | 25/25 | historical-public.json，在原e542340公开checkout运行原门禁 |
| 实际新查询 | 2次Embedding | query-current.json及parent-fresh内嵌query_receipt，固定生产提交 |
| 完整父正文装配 | 三组各5/5 | parent-from-current、parent-from-legacy、parent-fresh；前两组0次新Embedding |
| 本机完整补交付 | 31/31 | delivery-final.json |
| 最终公开补交付 | 17/17，内含24/24 | public-complete.json，无私有语料/模型/索引/第三方包 |

证据目录：[rechecks/task11-audit-20261113](rechecks/task11-audit-20261113)。0次新正式test、0答案LLM请求；两次非评测查询不能用于声称新质量/性能成绩。中间15/21复现工具失败及早期回执保留，原因和最终依据见审查说明。

## 原任务标准与保全

- 切分脚本、独立120行父子JSONL、99原ID/102子/18父映射、tokenizer和字符/token分布、表格/条件完整性、同锁集三方案比较、重复/冗余口径、错误与原交付说明均保留。
- 原正式dev/test、原chunking_comparison、授权与STARTED/COMPLETED两条账本未改。当前代码按原生产提交身份严格复算历史，原门禁保留在原版本，本轮另有补交付门禁。
- 原643公开文件除五份声明修复模块及当前导航/清单外保全；19实验对象原样保留，追加第20项TASK-011-AUDIT。历史日志、CSV、简历证据仅追加。
- 25份私有索引、61原语料、新父子JSONL、人审及178原工程静态文件校验保留；全文、向量、模型、依赖与凭据不公开。
- 通过小提交、PR、新标签交付，专用football-rules-rag-lab以外仓库不写入，旧标签不移动。

## 实验结果没有改写

原预算内base/child/parent_child测试R5分别97.5%/95%/97.5%，R10为100%/97.5%/97.5%。父块上下文成本更高，预算会丢证据。T002/T030/T003及所有负收益继续保留；修复回执可信性不等于解决这些质量权衡，后续按新实验规则优化。
