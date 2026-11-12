# 任务七缺陷补齐与重新交付

## 当前结论

本轮关闭7组交付缺陷。完整交付门禁43/43、新缺陷回归61/61、原合同110/110、原复算回归113/113和算术54/54通过。修复后的入口真实完成40题开发集、120次测量；原开发、原锁定测试、新开发记录均在无模型/语料/索引、禁第三方包的公开副本中复算一致。

原始任务七检索结果保留：锁定测试40条可回答题中38条命中，Recall@5/10=95%、MRR@10=0.8604167，总检索P50/P95=270.1763/312.82121ms（150次）。本轮没有重新检索锁定测试、没有修改预测或重签旧凭证，原测试使用台账仍是一次正式报告的STARTED/COMPLETED两条事件。

起点main 1694b563cb29e0468e75f7c53f5f117e7affa967；分支fix/task-07-delivery-audit。范围见[补交付基线](../docs/TASK_07_SUPPLEMENT_SCOPE.md)。新标签v0.7.1-task7-audit，旧v0.7.0-retrieval-b0保持原提交。实际PR/合并SHA以GitHub记录为准。

## 1. 发现与修复

[修复前证据](rechecks/task7-audit-20261112/before_fixes.json)共20项：17项为隔离开发副本/模拟源码变化/模拟写入失败，3项为源码检查；均不是线上事故。另[凭证代码核对](rechecks/task7-audit-20261112/authorization_before_code_audit.json)记录通用重放遗漏的凭证字段，属于源码发现。所有破坏样例只作用于.tmp中的副本和虚构数据。

| 组 | 缺陷 | 已补齐 |
| --- | --- | --- |
| D7-01 历史复算 | 旧源码SHA必须等于当前文件，合法修复后旧结果不能复算 | 新测量仍严格验证当前已提交源码；历史复算读取原Git提交声明的源码清单并逐文件验SHA，数据/配置仍匹配当前冻结文件。使用当前严格合同复算，旧manifest不改 |
| D7-02 依赖覆盖 | 授权依赖run_retrieval_metrics.py未纳入源码快照 | 新执行覆盖13个源文件，包括该依赖和新增合同模块；旧快照11项保留，补充Git来源核对，不伪造历史运行签名 |
| D7-03 计时关系 | HTTP大于Embedding、load大于server total、预热/整轮耗时遗漏仍通过 | 校验请求分段/HTTP/server及预热/整轮的包含关系和严格数值类型，原270个样本在新检查下仍一致 |
| D7-04 元数据合同 | 错误runtime name/context、布尔预热次数、反向日期及额外正文字段被接受 | 固定型号/digest/CPU/context/runner、类型、环境依赖、时序；对manifest/启动/runtime/environment/凭证使用字段白名单，源码/来源类型严格检查 |
| D7-05 凭证链 | 通用重放遗漏版本、配置、数据版本和准备时序；无授权可能先报其他错误 | 完整绑定版本/配置/锁/代码/开发结果和验证凭证，检查开发→准备→测试时序及检查项数量/producer SHA；无授权优先拒绝 |
| D7-06 异常记录 | 启动文件写入在保护块之外；清理报错可覆盖原异常 | 启动/生成/记录归入受保护生命周期；失败文件与FAILED事件分别尽力保存，清理错误保留原异常，已记录失败的目录禁止作为COMPLETE复算 |
| D7-07 重验门禁 | 239个文件和整个台账恰好2条被写死 | 快照按其Git基线的文件覆盖及SHA核验；按run_id核对该次开始/完成，其他合法完成/失败记录可保留。原273文件快照与增加合法条目的快照均通过 |

本轮没有修改指标公式、模型/Embedding/索引参数。原来2题未进Top10等漏召回继续作为真实基线错误报告，后续按开发集开展检索优化；不能为关闭交付缺陷把95%改写为100%。

## 2. 最终证据

以下文件相对于reports/rechecks/task7-audit-20261112。

| 核验 | 结果 | 文件 |
| --- | --- | --- |
| 任务七完整交付与原资产保全 | 43/43 | acceptance/task7-delivery-final.json |
| 新缺陷、模拟生命周期/凭证、历史与可扩展快照回归 | 61/61 | acceptance/supplement-final-v2.json |
| 原合同检查（合成来源行号夹具已符合真实结构） | 110/110 | acceptance/contract-final.json |
| 原开发副本复算和CLI拒绝路径 | 113/113 | acceptance/replay-final.json |
| 原指标算术 | 54/54 | arithmetic.json；retrieval_metrics.py未改 |
| 原dev/test独立复算 | 与原始汇总一致 | dev-recomputed.json、test-recomputed.json |
| 修复后真实开发入口 | 40题/120次，Recall@5/10=96.875%、MRR@10=0.890625 | ../retrieval/task7-audit-20261112/dev；acceptance/live-dev-recomputed.json |
| 公开独立副本复算 | 原dev、原test、新dev三组一致，0模型请求 | acceptance/public-only-replay.json |
| 原授权依赖的补充来源 | 原两个提交的依赖SHA与当前一致；新执行来源13项 | source-coverage.json |

真实开发运行的代码提交为dd4ff10，完整SHA见新dev/run_manifest.json的source_commit；最终核心验证合同源版本为4937f6c，后续维护文档及验证报告字段。新开发延迟仅作为本次入口运行记录，不替换原性能基线或宣称优化收益。

中间55项、59项和首轮113中112项的回归文件均保留。首轮无授权路径未到达预期门禁，随后前移无授权拒绝并在稳定源码下完整113/113；原测试从未因此重新检索。最终依据acceptance下的最终文件。61项v2回执明确“底层门禁重放了原测试记录、只暴露聚合、0新测量”，修正早期回执read字段可能混淆直接读取与底层重放的表达，检查内容和原数据不变。

失败持久化采用独立两通道。如果操作系统同时禁止写失败文件和使用台账，程序保留原异常并以非零退出报告，不声称已成功落盘。模拟双文件写入失败、FAILED事件仍可落盘及清理二次失败都已检查；强制结束进程的未完成STARTED不冒充成功。

## 3. 复验命令

本轮路径已经存在，重验需使用新的报告路径；不覆盖旧数据和报告。

```powershell
.\.venv\Scripts\python.exe scripts/verify_task7_supplement.py --report reports/rechecks/my-task7-audit/supplement.json
.\.venv\Scripts\python.exe scripts/verify_task7_delivery.py --preservation-snapshot .runtime/task7-audit/before.json --report reports/rechecks/my-task7-audit/delivery.json
.\.venv\Scripts\python.exe scripts/recompute_dense_retrieval.py --run-dir reports/retrieval/dense_b0/test --output reports/rechecks/my-task7-audit/test-recomputed.json
# 公开完整Git克隆，无私有模型/语料/索引也可复算：
python -S scripts/recompute_dense_retrieval.py --run-dir reports/retrieval/dense_b0/test --output reports/my-public-recheck.json
```

`verify_task7_supplement.py`是本机工程回归，使用已保存开发记录和私有保全快照；内部对原测试只重放/核验聚合，绝不发起新的测试Embedding请求。公开recompute工具只证明来源、已保存记录和算术一致性；不能独立证明私人阅读、专家规则认证或抵御本地完全重造执行证据。

## 4. 保全与重新交付

原TECHNICAL_DESIGN、DEVELOPMENT_PLAN_AND_REPORT、任务七原范围及原交付报告保留；原Corpus B0、10冻结/4历史前缀、61语料、原评测与真实人审、正式索引全部文件、原工程178静态文件维持原哈希。原任务七预测/逐请求记录/manifest/凭证/使用台账及其95%结果维持原字节。

维护当前README、DENSE_RETRIEVAL、DELIVERY_STATUS和实验/报告索引，任务14只追加本阶段记录；旧9个实验对象及其历史SHA保留。公开仅新增代码、无正文/向量/账号的排名元数据、复验报告与哈希。发布前核对当前完整清单和凭据排除，发布后只读核对整个GitHub树及新旧标签。

仅yangyanbeen/football-rules-rag-lab允许写入，desktop-tutorial/main仍应为8e7bafebe26caa0dbcb64d729766513d485c73bb。按小提交、独立PR、普通merge和新版本标签归档。任务8–13不在本轮执行，任务14同步补交付归档。
