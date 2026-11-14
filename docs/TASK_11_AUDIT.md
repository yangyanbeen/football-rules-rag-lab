# 任务十一缺陷复审与当前复验入口

基线为e542340ebab150bc4a37a478f9f5e7d05027f52e（PR22/v0.11.0）。原技术设计、执行计划、TASK_11_SCOPE、CHUNKING_STRATEGY、原交付及正式结果保留原字节；本轮补交付另记。未修改模型、256/4096阈值、检索参数、数据或标签。

## 修复内容

| 组别 | 原问题 | 修复 |
| --- | --- | --- |
| 固定配置 | 只检查部分字段，BM25参数或tokenizer名称可与实际执行不一致 | 1.0配置全部字段和JSON类型按规范化哈希固定，改变须另升版本 |
| 来源与区间 | 原段spans、引用行范围及正文/来源哈希关联未完整校验 | 原段完整区间、所有层的整数边界、来源行/哈希/规则号逐项验证 |
| 预算与评分API | 重复context可重复计费；quality的zip可静默丢题 | 验证上下文唯一性/顺序/整数token数、问题与预测完整一一对应及支持ID；coverage独立验证区间 |
| 真实索引 | ID数组顺序未绑定向量布局，词项载荷未从实际文本复算 | 固定base/child ID顺序、变化/复用清单、原向量身份；重算BM25载荷并逐条检查96个未变子块向量复用，在访问模型前拒绝错误索引 |
| 异常 | 清理失败可覆盖查询主异常 | 保留主异常并记录次级清理异常；单独清理失败仍报错 |
| 历史兼容 | replay要求当前脚本SHA等于旧测量时SHA，安装修复后无法重放旧实验 | 源码身份校验绑定原生产提交；数据/配置仍校验原冻结文件；当前执行仍要求源码已提交，历史结果不改贴新版本 |
| 运行记录 | 可接受空run_started、布尔/浮点请求计数、额外字段、浮点模型上下文及物理不可能的串行耗时 | 完整schema/UUID/用途、精确JSON类型、环境、生产文件大小与SHA、总墙钟包含所有串行查询及预热 |
| 父块入口 | 保存查询只凭两个标志判定实际查询，缺少来源及输入证明；预检查漏依赖 | 新structure-query-1.1记录原始问题、规范化包、源码/输入快照、时间、环境、索引前后快照和真实请求观测；父块执行前校验全部依赖 |

17项缺口通过隔离接口检查复现，另外4项有效输入对照，共21项。它们不是17个线上事故或质量样本。修复回归增加11项边界，共32/32；原46项合同仍通过。

## 回执版本和旧数据

原无版本的actual-query.json缺少时间/环境来源证明，当前入口只允许与原发布文件**逐字节相同**的旧回执；任意重写/增加空白/替换标志均拒绝。新保存查询使用structure-query-1.1，保留原始问题，支持全角数字与空白规范化后仍正确校验问题哈希。

父块装配使用task11-actual-parent-context-1.1，记录执行依赖、内嵌新查询或外部回执引用、私有正文输出哈希。公开结果只含父ID、逐成员来源、正文哈希、预算和跳过项；本机实际读取的父正文独立校验。保存查询重放不再计为一次新模型检索。

原dev/test仍为structure-run-1.0，数据、排名、质量、延迟记录、授权与两条账本不变。新代码可严格重放它们。原verify_structure_delivery.py及19实验注册校验是**原发布版门禁**，在旧标签运行；本轮另用verify_task11_audit_delivery.py，没有降低旧门槛或覆盖回执。

## 验证证据

新目录：reports/rechecks/task11-audit-20261113。

- reproduction.json为修改前真实原代码的21/21隔离复现；reproduction-final-v2.json用最终工具隔离原生产快照后仍21/21。
- reproduction-final.json的15/21 FAIL属于复现工具中间版本：当前源码已更新，原重放器先被当前源码快照差异拦截，六项反例未到目标检查。工具随后显式隔离原生产快照，v2纠正；该文件保留，不冒充产品验收失败或最终通过。
- regressions-first/final是当时源码的中间结果；当前32项依据regressions-complete.json。原46项依据contract-current.json，全部绑定当前源码。
- 当前Python -S公开副本16/16，包含原dev/test、查询/父块元数据复算和7个重新哈希的错误运行副本拒绝。原发布提交独立公开门禁25/25另列。
- 固定修复提交后实际发出2次非评测Embedding；完成新查询回执重放、原旧回执重放和直接查询三组完整父正文装配，各5/5。重放两组为0次新模型请求。0答案LLM、0新正式test。
- 补交付完整门禁31/31；最终公开副本17/17，内含24/24完整公开补交付门禁。本机模式额外核验25索引文件、61原语料、新父子JSONL、人审及三份实际私有正文；公开模式不假装能从哈希重算私有模型向量或正文。

## 真实结果限制继续保留

原50题测试中，base/child/parent_child预算内R5=.975/.95/.975，R10=1/.975/.975，MRR=.936458/.923958/.945833；原parent_child平均上下文3648.80 tokens，base1954.06。T002拆分丢完整支持、T030部分支持缺失、T003预算跳过父块继续保留。

本轮修复输入/证据可信性和接口可靠性，不提供新的Recall提升、冗余下降、答案正确率或QPS。若要改变切分/预算以改善上述负收益，必须开新的预声明实验，保持本轮原测试记录。

## 当前复核命令

```powershell
.venv/Scripts/python.exe -B scripts/verify_task11_audit.py --report reports/rechecks/task11-repeat/regressions.json
.venv/Scripts/python.exe -B scripts/verify_structure_contract.py --dev-dir reports/retrieval/structure_pc_b0/dev --report reports/rechecks/task11-repeat/contract.json
.venv/Scripts/python.exe -B scripts/verify_task11_audit_delivery.py --complete --report reports/rechecks/task11-repeat/delivery.json
# 公开副本：系统Python -S -B，最后一条增加--public-only，保留Git历史
# 真实查询只用于新非评测问题；正文输出使用新的忽略路径
.venv/Scripts/python.exe -B scripts/query_parent_child.py --question "请查询球员装备安全规定。" --private-output .runtime/task11/next-parent.json --receipt reports/rechecks/task11-repeat/parent.json
```

使用新输出路径，既有报告不覆盖；不要重复正式test命令。旧原发布门禁可在v0.11.0-structure-parent-child独立checkout重放。本轮交付报告见reports/TASK_11_SUPPLEMENT.md。
