# 任务 14–17 缺陷审查与补交付

本轮复现并关闭 **19 项可验证缺口**。18 项是同一套边界检查在旧版和修订版的对照，另有 1 项通过真实归档 CLI 在两个隔离工作树验证。原任务的技术与验收规则、正式测试及人工账本按原版本保留。 [操作和复验](../docs/TASK_14_17_AUDIT.md) · [旧版复现](rechecks/task14-17/before.json) · [修订回归](rechecks/task14-17/regressions-first.json)

| 范围 | 缺口及修复证据 |
| --- | --- |
| 任务 14 | 负数或非标准下标、非法转义都会被拒绝。旧版会输出被改过的数字，修订版校验冻结归档后才显示。 [真实 CLI 对照](rechecks/task14-17/archive-cli.json) · [归档 43/43](rechecks/task14-17/archive-replay.json) |
| 任务 15 | 参数被替换、向量与 ID 对调、开发题被改写或用布尔值冒充构建次数都会被拒绝。原测量复算及本机二进制文件验证通过。 [历史复算 17/17](rechecks/task14-17/faiss-replay.json) · [原私有制品](rechecks/task14-17/native-prior.json) |
| 任务 16 | 候选回答和引用一起校验。版本或索引变化隔离，异常封包回源，同键并发在同一进程内去重。真实重复问答 hit 时调用为0。 [复算 34/34](rechecks/task14-17/cache-replay.json) · [真实 Redis 客户端断线](rechecks/task14-17/redis-fallback.json) |
| 任务 17 | 原段进入提示前校验，异常仍正确计数，共享引擎的请求独立记录。正常、版本拒答和受控引用拦截完成真实复验。 [历史复算 18/18](rechecks/task14-17/graph-replay.json) · [实际图受控检查 15/15](rechecks/task14-17/graph-controls.json) |

现场冒烟 **5/5**。精确缓存一次 miss 后命中同一安全回答与引用，独立图正常成功，未核实版本在检索前拒答，故意更改的引用被拦截。新请求是本机集成冒烟，原正式测试重跑和新增人工判断均为0。 [真实证据](rechecks/task14-17/live-smoke.json)

原 29 条实验登记和旧标签仍可追溯。日志、CSV 与简历证据追加本轮修订。原始实验结论适用原测量条件。Redis 服务端、生产量级延迟和总体准确率仍待测。
