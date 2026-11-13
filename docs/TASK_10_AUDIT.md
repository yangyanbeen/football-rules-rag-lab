# 任务十缺陷复审与兼容说明

基线为 `e24e5c1b37585fe91047a6c6f64c6bdaf7273291`，原技术设计、执行计划及任务十要求保持原字节。本次为缺陷补交付，未执行任务十一，未重新检索锁定测试问题。

## 修复范围

| 问题 | 修复与验证方式 |
| --- | --- |
| Token 长度记录可在不足 512 时声称被截短 | 固定 `used_tokens=min(original_tokens,max_length)`，超长才标记截断；合成错误记录拒绝 |
| JSON 的 `true` 可冒充排名或并发数 1 | 排名与冻结配置按规范 JSON 比较，保留类型差异 |
| 只固定模型权重，其他分词器文件可替换 | 原五份文件的大小和 SHA256 全部精确绑定官方固定 revision；配置文件不变 |
| 双路原始结果顺序未核验 | Dense 距离升序、BM25 分数降序及稳定 ID 排序；拒绝非有限数，允许余弦距离微小负舍入误差 |
| 清理异常覆盖初始化主异常 | 保留主异常并记录次级清理异常；模拟失败路径验证 |
| 返回的 Embedding 观测可回写内部状态 | 返回独立字典，原内部观测不随调用方修改 |
| replay 的错误输出路径到重放后才检查 | 读取实验结果前完成路径与覆写预检查 |
| 测试授权的开发摘要可指向其他实验 | 摘要必须属于同一开发 manifest 的目录，且为 dev 摘要 |
| 部分支持段丢失未被错误分析完整列出 | 新增部分截断丢失及 Top5/10 支持不完整字段，保留旧定义重放 |
| 单独 replay 可接受未来完成时间或矛盾时钟 | 核验开始/完成/当前时间与单调计时一致性；原完整门禁已包含部分时间校验 |
| 不同预算对同一 query/chunk 的输入身份可矛盾 | 交叉校验 query/passage/input IDs 哈希及 token 长度；不要求不同 batch 的浮点分数逐位一致 |
| 新旧错误分析格式容易混淆 | 新运行使用 `reranker-run-1.1` / `reranker-errors-1.1`；重放从冻结生产源码识别格式，不能给旧生产记录改贴新版本 |

上表按原因归组。18 项原版复现检查包含 **14 项接口缺口及 4 项有效输入对照**；27 项修复回归还包括跨预算、浮点边界和旧格式兼容。检查数量不是独立线上故障数或质量样本数。

## 历史兼容与交付门禁

- 原 dev/test、授权、测试两条账本、原结果、原交付报告、原说明保持原字节，1.0 错误分析照原定义复算。
- 原 `verify_reranker_delivery.py` 会要求当时交付代码和 17 个注册对象，故应在原标签 `v0.10.0-bge-reranker` 运行。本轮用独立历史公开副本确认 35/35；没有降低原门禁以迎合新代码。
- 当前补交付使用 `verify_task10_audit_delivery.py`。`--public-only` 禁用私有文件检查；完整模式同时核验本机索引、语料、人审账本和模型身份。
- `regressions-first`、`contract-current`、`lifecycle-current` 为开发过程证据；当前生产代码依据名称含 `final` 的回执。原始失败/复现文件不覆盖。
- 实际功能回执的生产提交早于生成时间，源码 SHA 与当前版本一致。四预算真实调用和冷启动分别为 8/8，不能替代锁定集质量或稳定性压测。

## 支持段诊断与真实限制

新诊断仅从保存排名计算，不发起模型请求，不改原 Recall/MRR。原测试 Top40 的 Recall@5/10=100%、MRR@10=.975 是“至少命中一条支持段”和首条命中的指标，不能证明每题证据完整。

Top20/40/80 各有两题 Top5 未覆盖全部标注支持段：T022 为 75%，T034 为 50%；其中一题 Top10 仍不完整。Top40 的平均支持段覆盖率为 .98125。这些情况在新 `test_support_diagnostics.json` 全部列出。未通过调整标签、重跑 test 或扩大召回来消除它们；后续结构切分与答案质量任务需继续处理。

部分支持段被 Top20 截断、但仍至少命中一条的合成案例用于验证新增字段。它不冒充本轮新增实测案例。开发 D001 的原真实 Top20 丢失及 D011 的排名下降仍保留。

原 CPU 秒级延迟、每题每方法一次测量、小语料和旧测试复用限制继续适用。本轮不产生新加速比、Recall 提升、答案准确率或生产吞吐结论。

## 复核命令

```powershell
.venv/Scripts/python.exe -B scripts/verify_task10_audit.py --report reports/rechecks/task10-recheck/regressions.json
.venv/Scripts/python.exe -B scripts/verify_task10_live_audit.py --replay reports/rechecks/task10-audit-20261113/live-current.json
.venv/Scripts/python.exe -B scripts/verify_reranker_cold_start.py --replay reports/rechecks/task10-audit-20261113/cold-current.json
.venv/Scripts/python.exe -B scripts/verify_task10_audit_delivery.py --complete --report reports/rechecks/task10-recheck/delivery.json
```

公开副本可用系统 Python `-S -B` 执行最后一条，并加 `--public-only`；需保留 Git 历史用于校验生产提交。它不需要模型、语料、索引或第三方 Python 包。输出使用新路径，禁止覆盖既有回执。不要重跑原 `test` 命令。
