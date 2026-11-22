# 低内存运行模式

2026-11-22，Windows 本地 CPU、Qwen2.5:3b、原 BGE-M3 与 BGE-Reranker，提交 `566b9cf`。

此前的6.5GiB是旧实验的启动安全余量，不是单个模型大小或经验证的最低硬件要求。原链路在向量检索后仍让 BGE-M3 驻留，随后构造重排器；回答模型也会在请求结束后继续驻留10分钟。低内存模式将这些组件分阶段使用。

在按原说明启动固定本地 Ollama 服务后，从项目目录启动网页：

```powershell
powershell -ExecutionPolicy Bypass -File frontend/start_integrated_rag_audit.ps1 -LowMemory
```

直接调用默认 Worker 时，在该进程中设置：

```powershell
$env:FOOTBALL_LOW_MEMORY = '1'
.runtime/task13/venv-final/Scripts/python.exe -B scripts/query_task13_audit.py --check
```

`-LowMemory` 自动启用门禁后的延迟构造、重排前按需加载及重排后释放，无需分别设置三个旧实验开关。E13事实补答仍由原有 `FOOTBALL_SOURCE_FACTS=1` 单独控制。常规启动不加本开关时保留原行为；环境变量显式设为0可关闭本模式。

运行顺序：

1. 缺赛事/赛季的累计黄牌处罚查询直接拒答，不加载检索或回答模型。
2. 普通问题检索前，卸载上次驻留的固定回答模型。
3. 完成原向量检索、BM25与RRF后，卸载固定BGE-M3，确认 `/api/ps` 已无该模型，再构造同一重排器。
4. 排序与原Prompt装配完成后，释放重排器并核验对象回收，再调用原3B回答模型。
5. 回答流程结束后卸载3B，避免空闲驻留。

卸载使用 [Ollama 官方 API 的空请求及 keep_alive=0](https://github.com/ollama/ollama/blob/main/docs/api.md#unload-a-model)，不产生额外推理。只处理配置中的模型名称及匹配digest，不枚举卸载其他模型；卸载失败时停止进入下一重型阶段，保留运行错误。正文、重排批量、Top-K、Prompt、Schema、上下文上限、模型、线程、采样参数和引用校验保持原配置。适用于串行请求与专用本地模型服务；并发仍须单独验收。

## 本机实测

正常Worker五次、正常网页五次，共10次请求；包含D036、D001、D004、T026及重复D001。保留了用户Chrome与Codex。完整数据见 `optimization/reports/E15_low_memory_pilot.json`，原始轨迹见 `.runtime/phase2/e15-lowmemory01/`。

| 指标 | 结果 |
| --- | --- |
| 入口运行完成 | 10/10 |
| 全部请求最低可用内存 | 2.992GiB |
| 最长可见回复/Worker耗时 | 35.49秒 |
| 普通请求耗时中位数 | 34.22秒 |
| Worker请求期间任务进程树工作集峰值 | 最高约3.00GiB，含驻留网页服务及观察器 |
| 网页请求期间任务进程树工作集峰值 | 最高约3.68GiB，另含专用测试Chrome |
| 卸载BGE时可用内存回升中位数 | 1.165GiB，8次观测 |
| 回答后卸载3B时回升中位数 | 2.287GiB，8次观测 |
| 请求结束后的模型列表 | 10/10为空 |
| D036 | 两入口均零检索、零回答调用 |
| 与E14归档的输入、候选顺序及实际Prompt | 10/10一致 |
| 原文审核对应的选段及答案等级 | 10/10保持；T026仍为部分正确 |
| 引用支持 | 8/12，与同题归档选段一致 |

这是候选单组实测及历史输入核对，不是同期A/B，也不是90题的新准确率。没有降低1GiB最低可用内存和60秒响应门槛。新测试脚本采用5.0GiB启动预检，实际这次启动时为6.391GiB，故尚不能声称已验证5.0GiB就是足够的启动余量，更不能推广为所有小内存机器均适用。

工作集峰值按同一时点的任务进程树求和；共享页可能重复计入。不要相加各角色各自的峰值，也不要把“可用内存回升”全部等同于模型独占物理内存。外部周期采样的间隔中位数约0.311秒，最大约0.951秒，并同时采用阶段即时Windows快照；采样间隙仍存在。

低内存模式的代价是连续请求需要重新加载模型。本次耗时达标，但尚未验收90题连续运行、长期运行、并发与40题留出集。原E15的中断、资源失败记录及E14的54/72历史质量基线均保留，不能用本专项替代全量验收。

离线机制检查及入口专项复跑：

```powershell
.runtime/task13/venv-final/Scripts/python.exe -B optimization/verify_low_memory.py
pwsh -NoProfile -ExecutionPolicy Bypass -File optimization/run_low_memory_probe.ps1 -RunName e15-lowmemory02
.runtime/task13/venv-final/Scripts/python.exe -B optimization/score_low_memory_probe.py --run .runtime/phase2/e15-lowmemory02
```

复跑须使用新的输出目录。脚本只管理其创建的服务与专用无头浏览器，结束后关闭这些进程，不关闭用户Chrome或Codex。
