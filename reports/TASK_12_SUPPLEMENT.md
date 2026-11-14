# 任务十二缺陷复核与补交付

日期：2026-11-14。基线 `cd2e034f85f0018f25ab82024047259e2513c458`；分支 `fix/task-12-delivery-audit`；补丁版本 `v0.12.1-task12-audit`。最终合并提交与PR以GitHub记录为准。

**工程缺口已修复并复验；原标准所需的新回答人工抽样仍为0/12。因此任务十二尚不能签为全部验收完成。** 原技术/执行文档、模型配置、正式测试成绩和历史报告不改。

## 已复现并修复的缺陷

| 问题 | 修复与证据 |
| --- | --- |
| 完成产物集合为空仍放行 | 强制检查6个准确产物名称及实际文件哈希；原漏洞通过内存反例复现，不改真实文件 |
| 完成记录分割写成dev或生产提交写错仍放行 | 对照开始记录绑定split/source_commit，保留生产时间和原代码校验 |
| 错误分析仅校验文件哈希，未从评分复算 | 逐题重算缺失要点、条件、坏引用、错误拒答、运行/评分错误，要求完整相等 |
| 实际请求提示、JSON Schema、计数和输出选择漏验 | 新增原响应审计，绑定回答与评分的完整messages/format、真实计数、解析结果、拒答原因和时钟；非标签引用也检查record SHA |
| 人工账本只检查少量身份字段 | 完整检查题目、答案/trace/context SHA、向量长度、判定枚举、审阅者、理由、时区时间、提交方式；拒答不能标成覆盖规则要点 |
| 人工读写缺乏完整性和并发保护 | 验证既有账本再追加、文件排他锁、flush/fsync；破损/未结束行拒收，修订只追加、不增加独立题数 |
| 缺少真实人工结果导出和完成门禁 | 脱敏逐项决定和样本指标独立复算；缺题或uncertain保持PENDING；严格验收返回非零，不把工程PASS当作人审PASS |
| 审核材料与提交表单绑定不足 | 新页面每次核对冻结语料，展示标签段及当次可见全文，表单绑定答案与标签版本；旧表单和无效字段拒收 |
| 旧发布门禁固定21实验/创建标签前状态，补丁后操作入口不清 | 新补交付入口核验22实验并保留21原对象；历史生产脚本不改，旧数量回执仍按原发布阶段解释 |

原漏洞证据：[legacy_gaps](answer_evaluation_audit/legacy_gaps.json)中3项均为 `legacy_accepted_invalid: true`。这些是合成反例，不能当作真实实验文件曾被损坏。新代码 `answer_audit_v2.py` 和 `answer_review_v2.py` 追加增强，不覆盖原生产脚本。

## 实际复验

| 检查范围 | 结果 | 记录 |
| --- | --- | --- |
| 新增专项、合成负向与原90题响应复核 | 53/53 PASS | [regression-final-v3](answer_evaluation_audit/regression-final-v3.json) |
| Python -S公开副本，无模型/私有语料/响应 | 44/44 PASS | [public-final-v3](answer_evaluation_audit/public-final-v3.json) |
| 实际本机页面与无效提交拒绝 | 14/14 PASS | [http-review-final](answer_evaluation_audit/http-review-final.json) |
| 原专项和保存结果重放 | 42/42 PASS | [legacy-contract](answer_evaluation_audit/legacy-contract.json) |
| 独立指标算术 | 19/19 PASS | [independent-arithmetic](answer_evaluation_audit/independent-arithmetic.json) |
| 原完整本机门禁，注册第22实验之前 | 20/20 PASS | [legacy-delivery](answer_evaluation_audit/legacy-delivery.json) |
| 原完整公开门禁，注册第22实验之前 | 24/24 PASS | [legacy-public](answer_evaluation_audit/legacy-public.json) |
| 当前本机补交付工程门禁 | 26/26 PASS；完整验收false | [delivery-final](answer_evaluation_audit/delivery-final.json) |
| 当前Python -S公开完整补交付门禁 | 23/23 PASS；完整验收false | [public-delivery](answer_evaluation_audit/public-delivery.json) |

最终补交付门禁记录为 [delivery-final](answer_evaluation_audit/delivery-final.json)。它单列工程状态、真实人工状态和 `task12_fully_accepted`；工程通过不改变人审未完成的事实。用 `--require-complete` 的实际运行不会因人审缺失返回成功。

首轮专项46/47中的1个失败来自Windows沙箱临时目录清理权限，并非真实账本失败。原回执保留为regression-first；合成夹具改放工作区被忽略的.tmp独立目录，随后47/47，扩充公开摘要与版本绑定后53/53。没有删除失败回执或把它替换成PASS。

## 人工验收剩余项

本轮 [真实审核快照](answer_evaluation_audit/human-review-status.json)：0/12，`PENDING`，没有人工语义分数。12题固定为T001、T003、T004、T005、T006、T007、T008、T009、T010、T011、T013、T014。

本机审核页：http://127.0.0.1:7865/ ，已在浏览器打开，HTTP200与14项校验实测通过。需要本人阅读并逐项提交；错误可以判“否”，无需把所有答案判对。合成回归使用隔离测试文件，从未提交到真实人工账本。旧90题标签批准也不算这12题新答案判断。

操作、脱敏导出和追加新快照的完整验收命令见 [ANSWER_REVIEW_WORKFLOW](../docs/ANSWER_REVIEW_WORKFLOW.md)。必须满足12题全部有明确判断，缺题或uncertain需继续核对；没有此证据不能交付为全部完成。该抽样偏向错误，不能将其分数外推到整个测试集或写成裁判专家验证。

## 原问答质量与边界

本轮新增推理0次、正式test重跑0次。原test50的AI要点覆盖40/100、引用22/71、条件56/100、正确拒答10/10、错误拒答5/40均保留；dev中D016重复选择ID导致的运行错误也保留。相同小模型答与评可能共同误判，尚未测出真实人工答案质量。

原任务12要求报告这些指标、模型、样本和人工方法，没有最低分数目标。本轮是评测可靠性补交付，不声称修好了全部足球答案，也没有用测试题修改模型/提示或提高旧成绩。未来质量改进需要独立实验、开发集选型与新增授权/证据，不能改写这次固定测试。

## 保全、仓库与回滚

736个原公开文件除当前导航/全局清单/允许追加日志外原字节保留；21原实验对象保持，新审计注册第22项。原61语料、25索引、父子派生语料、180份正式私有答案/评分响应和旧人审账本单独核验。原工程178静态文件、10冻结文件、4历史前缀及运行依赖另由发布检查保全。

只向 `yangyanbeen/football-rules-rag-lab` 新分支提交并建立PR；21旧标签保持，新标签为 `v0.12.1-task12-audit`。其他既有仓库只读。小提交可逐项审查；查看旧版可独立checkout `v0.12.0-answer-evaluation`，不要删除测试账本后重跑。完整规则/模型/私有审核姓名与备注不上公开仓库。

后续任务13/14继续原计划；当前补交付不将人审缺口隐藏在“所有测试通过”后面。
