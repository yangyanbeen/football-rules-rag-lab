# 任务十六交付报告

按原标准交付独立精确缓存入口、过期和跨版本隔离、Redis 后端适配，以及开发与留出两期语义评估。实际运行使用内存后端。 [原任务标准](../docs/DEVELOPMENT_PLAN_AND_REPORT.md) · [配置、结果与复跑](../docs/REDIS_CACHE_EXPERIMENT.md)

| 交付项 | 验收证据 |
| --- | --- |
| 先做精确 Query Cache | 真实同一问题启用缓存后一次 miss、一次 hit，回答哈希和引用 ID 相同。[本机实测](task16/live-exact.json) |
| 版本键、过期及失效 | 查询哈希、语料、模型、检索设置、TTL 和 epoch 均进入键。内存固定过期、容量淘汰、Redis 原子 PX 和断线回源分别验证。[专项复验](task16/replay-local.json) · [redis-py 真实连接拒绝](task16/redis-availability.json) |
| 语义匹配和错误率 | 开发 24 个探针先选 0.90，提交冻结后运行留出 24 个。实际编码和逐题相似度可复算。[开发](task16/dev/summary.json) · [冻结](task16/holdout-freeze.json) · [留出](task16/holdout/summary.json) |
| 命中、未命中延迟及调用节省 | 查找 P50/P95 以逐次原始读数计算。另保存真实问答调用次数和独立工作负载的预算估算。[计时](task16/holdout/observations.json) · [问答调用](task16/live-exact.json) |

留出精确缓存 6/24 命中，0/6 错误。开发冻结的 0.90 在留出中有 12/24 命中，其中 4/12 错误。0.98 仍有一次错误匹配。交付采用精确缓存作为可用入口，语义匹配作为保留的对照实验。Redis 服务端性能、生产请求分布和总体答案质量待测。 [逐题结果与错误](task16/holdout/summary.json)

两组语义探针实测 48 个去重 Embedding 输入、12 个批次。真实重复问答实际运行工作进程 3 次，缓存命中额外触发的请求为 0。原锁定测试没有重跑，原人工评测账本保持原样。 [开发模型清单](task16/dev/run_manifest.json) · [留出模型清单](task16/holdout/run_manifest.json)

本机与独立公开副本各 34/34 专项检查通过，涵盖版本隔离、过期、错误回源、真实性回链和独立复算。 [本机复验](task16/replay-local.json) · [公开复验](task16/replay-public.json)
