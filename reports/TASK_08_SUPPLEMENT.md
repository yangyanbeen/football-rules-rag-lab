# 任务八缺陷复查与补交付

日期：2026-11-12。基线 `93687ce5a73853a63782d2204225b046697c7028`，原交付 PR #16、标签 `v0.8.0-bm25-b0`。本轮分支 `fix/task-08-delivery-audit`。

**结论：已修复四组交付缺陷，原任务八完整门禁在三个等价重建索引上通过 35/35；专项 74/74、新增回归 32/32、恢复流程 8/8、公开副本 13/13 通过。** 原技术设计、任务交付标准及原报告不修改；本报告补充原 [TASK_08_DELIVERY](TASK_08_DELIVERY.md)。

## 1. 发现、复现与修复

| 组 | 缺陷及影响 | 修复 | 证据 |
| --- | --- | --- | --- |
| 来源与授权 | 复算会接受晚于原运行的源码/索引构建提交；历史授权读取时未复核选择和验收文件已进入授权提交 | 校验生产提交早于运行/授权时间；从授权 Git 对象逐字节核对选择与验收文件；提前校验 split/template/run_id | 修复前隔离复现、32项回归中的时间和未提交凭证反例 |
| 分词对照 | 可删空 artifacts/sources/inputs 清单，或改错 comparison 指标并更新其哈希，旧复算仍通过；忽略分词模式、HMM、预热和整轮计时；固定索引目录使第二次开发运行失败 | 严格字段与覆盖范围、来源/资源/索引身份、时间和预热检查；从原预测重新计算两路指标及延迟；每次开发创建独立索引目录 | 缺失清单、重签错误对照、模式/布尔类型/计时反例；两次真实开发运行成功 |
| 运行生命周期 | 单次测试用“检查存在后追加”预约，两个进程可能同时启动；创建输出目录失败缺少失败记录 | STARTED 使用文件独占创建，只有预约的 run_id 与完整身份可结束一次；失败保留阶段/重复序号和原异常；未取得目录所有权时写私有诊断目录 | 两线程预约只有一个成功；非拥有者/重复结束被拒；合成目录、索引加载、查询失败测试 |
| 恢复与门禁 | 完整门禁仍要求新旧索引 manifest 完全相同，误拒绝构建提交变化但载荷一致的恢复索引；部分验收只看 PASS 和计数 | 门禁复用语义身份校验，支持独立索引根目录；核对回执每项为真、源码 Git 哈希及最后代码变更时间；核对测试账本全身份与时间顺序 | 三个实际重建的旧相等判断均为 false，新语义检查均通过；完整门禁 35/35；假回执及错误账本反例 |

修复前 `before-fixes.json` 的 **14/14 GAPS_REPRODUCED** 表示在隔离副本和合成操作上成功复现缺口；不表示原始实验文件曾被篡改。新回归数量与原标准分别报告，不相加冒充验收标准。

## 2. 原标准复验与新检查

证据统一位于 [rechecks/task8-audit-20261112](rechecks/task8-audit-20261112)。

| 检查 | 结果 | 文件 |
| --- | --- | --- |
| 原任务八完整交付门禁，三个新恢复索引 | 35/35 PASS | delivery-restored-current.json |
| 原算术、分词、索引及开发结果专项 | 74/74 PASS | contract.json |
| 新增反例、来源/预约/失败/回执回归 | 32/32 PASS | regressions-current.json |
| 原恢复专项及一次真实开发集运行 | 8/8 PASS | portability.json |
| 三个恢复载荷与原载荷逐字节一致，旧门禁误拒绝复现 | 3/3 | restored-index-proof.json 的 cases |
| 无全文/索引/jieba 的公开检出复算 | 13/13 PASS，8组结果 | public-only-replay.json |
| 前序任务四、六、七原门禁 | 分别 26/26、62/62、43/43 PASS | previous-task4/6/7.json |
| 历史成果、本地索引与数据保全 | 18/18 PASS | preservation.json |

原任务八要求的构建脚本、运行脚本、三个本机索引、`bm25_baseline.json`、逐题排名/分数/计时、典型开发案例和 BM25 文档均保留。原三模板选择、固定参数、版本、来源与数据锁继续由原报告及新门禁复验。

## 3. 新的真实开发运行

仅验证实现与恢复路径，没有新增锁定测试检索，也没有调参数。

- 准确模式恢复索引：40开发题、120次测量，Recall@5/10 均 96.875%、MRR@10=0.8932291667，与原 title_body 开发质量一致。路径见 portability.json 的 actual_development_directory。
- 搜索分词模式：`retrieval/task8-audit-20261112/segmentation-dev-1` 与 `segmentation-dev-2`，各40题、120次测量；两次 Recall@5/10 均96.875%、MRR@10=0.9010416667，与原补充开发实验一致。两个私有索引路径不同，未覆盖原索引。
- 合计3次新开发运行、360次测量。各轮延迟为独立实测，保存在其 summary；不替换原测试延迟，不宣称速度优化。

公开副本使用 detached Git worktree，确认 `.runtime`、语料、索引、`.venv` 均缺失，`python -S` 下 jieba 不可导入。复算原3组dev、原test、原分词dev、新恢复dev、新2组分词dev，共8组。复算读取已保存预测，不调用检索器或答案模型。

## 4. 保留的真实失败与修正

- regressions-v1.json：17/18，未提交凭证被 Git 拒绝，但测试器未归一异常；修正后 v2 为18/18。
- regressions-final.json：扩展后30/32，暴露历史回执文件名格式及发布提交晚于历史测试时间的处理问题；按真实历史源码及最后代码变更时间校验后，current 为32/32。
- delivery-restored.json：33/35，CLI 短 SHA 未解析为完整提交；入口修正后 delivery-restored-current 为35/35。

这些中间文件按原字节保留，最终依据使用带 current 的报告。原 Task8 初始失败目录和所有旧报告同样保留。

## 5. 复验入口

本机已有冻结语料、原人工账本、隔离 jieba 和索引时，使用新的输出文件名：

```powershell
.venv/Scripts/python.exe -B scripts/verify_task8_audit.py --report reports/rechecks/my-task8-audit.json
.venv/Scripts/python.exe -B scripts/verify_bm25_contract.py --development-root reports/retrieval/bm25_b0/development --report reports/rechecks/my-task8-contract.json
.venv/Scripts/python.exe -B scripts/verify_bm25_portability.py --report reports/rechecks/my-task8-portability.json
.venv/Scripts/python.exe -B scripts/verify_bm25_delivery.py --report reports/rechecks/my-task8-delivery.json
.venv/Scripts/python.exe -B scripts/compare_bm25_segmentation.py --output-dir reports/retrieval/my-task8-segmentation-dev
```

`verify_bm25_delivery.py` 默认复核原历史专项回执对应的源码；检查新专项回执时一起传 `--contract-report`、`--portability-report` 和这些回执对应的 `--reference-commit`。`--index-root` 可指向三个等价重建索引的父目录。独立复算仍使用 BM25_RETRIEVAL 中的 `python -S` 入口。

`verify_task8_preservation.py` 使用本机复查前快照检查原446个文件保留、20个原私有索引文件、61份语料、原13个实验对象和原人工账本。快照不上传，公开仓库的历史版本和报告保留可审计哈希；公开检出不能替代本机保全验收。

## 6. 结果与版本边界

原唯一正式 BM25 测试仍为 Recall@5=97.5%（39/40）、Recall@10=100%（40/40）、MRR@10=.95；原150次 P50/P95=.265350/.377535ms。源码65e7516、授权、两条使用事件、原始预测及汇总均保持原字节。本次只复算这些旧预测，没有新的测试成绩。

历史回执绑定的代码可以存在于较晚发布提交中；核对的是实际文件 Git 哈希及其变更时间，不回填历史运行源码。Git 时间和本地证据用于项目追溯，不冒充独立第三方测量。

新补交付版本为 `v0.8.1-task8-audit`，通过独立 PR 留下小步提交；旧标签、原本地工程、其他已有仓库保持不变。完整语料、倒排索引、第三方依赖、账号与运行数据库不公开。原 jieba 的 pkg_resources 弃用警告继续记录，不改核心依赖隐藏警告。任务九及后续优化继续原计划，本轮没有答案准确率、QPS或线上性能结论。
