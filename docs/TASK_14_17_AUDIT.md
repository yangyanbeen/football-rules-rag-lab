# 任务 14–17 修订与复验

以 `v0.17.0-langgraph-flow` 的完整提交为审查基线。原技术设计、执行规则、旧报告、指标和正式评测记录继续留在原路径。本轮用隔离输入在旧版复现 18 项边界缺口，另在两个临时 Git 工作树对照归档查询。 [交付报告](../reports/TASK_14_17_SUPPLEMENT.md)

| 任务 | 修订行为 |
| --- | --- |
| 14 归档 | 按 JSON Pointer 语法校验转义和数组下标。查询数字、实验或证据分组之前复验冻结归档。历史生成脚本按原 Git 提交核对。 |
| 15 FAISS | 固定实验配置、语料映射、原向量清单和开发/测试输入。拒绝布尔值冒充构建次数。冻结前复验完整开发回执。旧测量按原提交读。 |
| 16 缓存 | 缓存身份覆盖实际语料、索引正文和实现。通过规范渲染重新核对缓存中的回答及引文。同一进程同键未命中合并回源，版本变化中止，坏封包触发回源。 |
| 17 LangGraph | 在发给模型前重算完整证据段的正文和记录哈希。共享引擎的请求串行计量，部分失败仍保留已完成的查询编码。显式请求 ID 严格校验。 |

同进程并发去重由进程内锁实现。多个进程连接同一 Redis 实例仍各自发起回源。Redis 客户端真实断线回源已经复验，Redis 服务端 TTL 与网络性能仍待测。语义缓存继续作为实验记录。图的请求耗时包含等待同引擎的时间，修订后的生产吞吐未测。

## 本机检查

在仓库根目录使用前序任务的独立环境。第一个命令运行原生图和合成输入，第二个命令运行本机固定模型。始终使用新的报告路径。

```powershell
.runtime/task17/venv/Scripts/python.exe -B scripts/verify_task14_17_regressions.py --report .tmp/task14-17-regressions-new.json
.runtime/task17/venv/Scripts/python.exe -B scripts/run_task14_17_smoke.py --report reports/rechecks/task14-17/live-new.json
.runtime/task15/venv/Scripts/python.exe -B scripts/verify_task14_17_delivery.py --report .tmp/task14-17-local-new.json
```

公开验收用完整 Git 历史和没有模型、私有语料的干净克隆。当前脚本直接复验任务 14–17 的历史归档和专项证据。

```powershell
python -S -B scripts/verify_task14_17_delivery.py --public-only --report .tmp/task14-17-public-new.json
python -S -B scripts/task14_archive.py show --claim reranker_top40_r5
```

历史完整门禁绑定对应任务原标签的代码、登记条目和报告。复验历史完整门禁时，可在 Git 工作树检出对应旧标签。当前补交付用上面的任务 14–17 门禁。 [旧版标签](https://github.com/yangyanbeen/football-rules-rag-lab/tree/v0.17.0-langgraph-flow)
