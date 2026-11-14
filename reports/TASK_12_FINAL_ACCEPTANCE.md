# 任务十二最终验收与缺陷补充

本轮基线：`c6cf77c5c0ccab92b097b9bda700dff12219b859`；分支 `fix/task-12-human-acceptance`；新补丁版本 `v0.12.2-task12-acceptance`。原技术设计、任务执行规则、任务1—11及任务12旧报告/成绩保留。

## 本次补齐的实际缺口

1. **真实人工结果未归档。** 已读取本人在审核页逐题提交的12题、13条记录，其中一次修订按最后有效记录计分；没有重复计成13题。没有缺题和uncertain项，现已追加脱敏快照，旧0/12快照保留为历史。
2. **当前交付状态未更新。** 使用原严格门禁加新人工快照，实际26/26、退出码0、`task12_fully_accepted=true`，不通过修改原门槛取得完成状态。新增当前阶段门禁支持累计23项实验，旧门禁保留其22实验阶段含义。
3. **人工结果缺少独立统计和错误分析。** 新增标准库独立复算、零分母保护、逐项AI/人工差异及错误清单，拒答指标与内容指标按各自口径报告。
4. **本地编目被显示成官方条号。** L03-02的装备内容和L03-04的比赛官员/VAR概述原属本地第3组，不能据此宣称这些内容是官方第3条。新增独立显示防护和私有预览，将本地编目与未核验官方条号分开；旧语料、索引、正式答案和人工判定不改。
5. **公开凭证可混入私有信息的校验缺口。** 新验收层严格限制私有账本回执只含path/size/hash，拒绝夹带姓名或备注；公开摘要整型计数另做严格类型和独立算术验证。

## 原交付基线对应

| 原任务12要求 | 现有交付与本轮补充 |
| --- | --- |
| 可运行B0及优化检索作为输入 | 原任务6B0、任务10开发选定Top40保持；本轮不重跑模型 |
| 答案限制于检索证据 | 原90题完整原响应只读校验；显示防护只使用同一完整原段 |
| 检查引用、规则编号、条件/例外和版本提示 | 原机械检查与本轮真实逐项判断结合；编号误用新增防护，保留非官方/非专家/版本未核验提示 |
| 无答案、冲突、版本不明和相似不支持 | 原4类探针及逐题结果保留；人审错误拒答和无关引用另列 |
| 回答评测脚本与answer_quality_results.json | 原正式dev40/test50与五指标不改；新增answer_acceptance和verify_task12_final |
| 逐题回答、引用、错误分析 | 原完整回答私有保全；公开脱敏人工决定及human-quality-analysis新增归档 |
| 样本数、模型配置、人工判断方法 | 原配置保持，12题真实提交、13条含修订、固定错误优先抽样；AI辅助性质明确披露 |
| 人工抽样核对引用 | 12/12完成；人工快照、账本SHA、实际本机验收及公开复算回执齐全 |

## 真实12题人工结果

来源：[脱敏逐项决定](answer_evaluation_acceptance/human-review-completed.json)、[独立统计与错误分析](answer_evaluation_acceptance/human-quality-analysis.json)。原始姓名、备注和完整规则正文保留本机，不公开。

| 指标 | 分子/分母 | 结果 |
| --- | --- | --- |
| 人工答案要点覆盖 | 21/27 | 77.78% |
| 人工引用正确 | 9/20 | 45.00% |
| 人工条件/例外保留 | 21/27 | 77.78% |
| 按原标签/状态统计的正确拒答 | 0/0 | null；样本没有不可回答题 |
| 按原标签/状态统计的错误拒答 | 2/12 | 16.67% |
| 人工判断回答/拒答选择恰当 | 10/12 | 83.33% |

这12题按原规定优先抽取错误/拒答等情况，不代表全部50题。用户在AI给出选项建议后逐题提交，不能称独立盲审、裁判专家认证或无辅助标注。上述数值不替代原test50的AI要点40/100、引用22/71、条件56/100及拒答10/10、错误拒答5/40，不构成优化前后对照。

### 人审发现的回答与引用质量问题

- T001、T009：资料存在答案但系统拒答。
- T004：没有明确回答罚球弧圆心；其他限制条件已覆盖。
- T014：提及岗位名称但没有回答对应职责及是否强制配备，不能按关键词出现计正确。
- T003、T007、T010、T013及T014：存在被人工否定的支持性/相关性引用。
- T006：内容覆盖本地标签，但引用编号错位，因此引用判否；不能改写原记录抹掉这一问题。

按原任务标准，任务12负责完成评测与错误归档，没有最低准确率目标。**评测任务完成不表示所有答案已修好。** 后续问答策略优化、任务13整合必须建立新实验和证据，不能根据这些测试题修改旧答案或抬高旧分数。

## 编号显示修复的使用方式

`scripts/citation_catalog_guard.py` 提供独立派生展示：

```powershell
.venv/Scripts/python.exe -B scripts/citation_catalog_guard.py --question-id T006 --report .runtime/task12-acceptance/new-preview.json --html .runtime/task12-acceptance/new-preview.html
```

输出路径必须全新且在.runtime，避免公开长答案。预览保留原答案SHA、原trace、原文、来源、署名许可和校核提示；显示“本地编目第3组”，不再断言“官方第3条”。新引用字段分为catalog_number和official_law_number，后者为null；原值仅在source_catalog_metadata保留。被标记段必须匹配冻结record/body SHA，否则拒绝套用注释。

主题核对参考：[IFAB第4条队员装备](https://www.theifab.com/laws/latest/the-players-equipment/)、[第6条其他比赛官员](https://www.theifab.com/laws/latest/the-other-match-officials/)。这仅核对编目与官方主题的区别，不将当前网站版本替换为本地历史资料，也不把跨条款段落强行映射为唯一官方条号。

原7865审核页继续展示当时的冻结答案，保留人审可追溯性；派生预览没有参与原人工评分，不能把展示改变解释成已测得质量提升。原B0应用与新适配器的集成仍属于任务13。

## 实际验证与当前复验

- [新增专项最终记录](answer_evaluation_acceptance/cases-final.json)：28/28 PASS，包含真实指标、零分母、私有信息泄漏反例、编号版本绑定和派生展示。
- [公开无模型专项](answer_evaluation_acceptance/public-cases.json)：Python -S隔离副本21/21 PASS，不需要全文、模型或私有账本。
- [原专项重放](answer_evaluation_acceptance/prior-regression.json)：53/53 PASS，原dev/test仅只读复算。
- [原严格完整验收](answer_evaluation_acceptance/prior-full-acceptance.json)：26/26 PASS，完整验收true；没有改旧脚本或编造人工提交。
- [当前本机完整门禁](answer_evaluation_acceptance/delivery-final.json)：26/26 PASS，task12_fully_accepted=true。
- [当前无模型公开完整门禁](answer_evaluation_acceptance/public-delivery.json)：Python -S隔离副本22/22 PASS，task12_fully_accepted=true。

当前入口：

```powershell
.venv/Scripts/python.exe -B scripts/verify_task12_final.py --report .runtime/task12-acceptance/recheck-new.json
python -S -B scripts/verify_task12_final.py --public-only --report reports/rechecks/task12-public-new.json
```

report路径必须未存在。保留完整Git历史，用于核对生产提交。公开副本只能复算脱敏结果、哈希和已保存验收回执；真实私有账本匹配由本机门禁验证。

## 保全与版本

原764公开文件除当前导航及允许追加索引外保留，22原实验对象原样后追加第23项。原22标签不移动；61原语料、25索引、父子派生语料、180正式私有答案/评分响应、旧标签人审账本及本轮真实13条账本保全。模型/参数/依赖未改，新模型请求和新正式test运行均为0。原工程178静态文件及原10冻结/4前缀另由发布检查验证。

本轮只写指定实验仓库 `yangyanbeen/football-rules-rag-lab`，按小提交、分支、PR及新标签发布；其他原有仓库不动。任务12按原评测与人工抽样标准交付，下一项任务13。
