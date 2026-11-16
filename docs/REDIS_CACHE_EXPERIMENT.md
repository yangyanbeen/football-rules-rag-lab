# 精确查询与语义缓存实验

精确缓存通过独立本机入口复用经过校验的答案和引用。24 次留出请求中，精确匹配 6 次，无错误复用。语义阈值 0.90 在开发集选出，留出集命中 12 次，其中 4 次匹配到错误意图。本项目保留精确缓存入口，语义匹配限于离线实验。 [交付报告](../reports/TASK_16_DELIVERY.md) · [原任务标准](DEVELOPMENT_PLAN_AND_REPORT.md)

## 缓存键与失效

原问答仅去掉首尾空白，精确键沿用该规则。键包含前缀、手动 epoch、身份 SHA256、TTL 和问题 SHA256。身份覆盖语料版本与正文哈希、Embedding 和生成模型的清单、检索和重排配置、回答提示、引文清单、索引清单、实现和缓存策略。每次请求读取当前标识。不同业务会话若不宜共享同一结果，使用不同 epoch。 [配置](../config/query_cache.json) · [实现](../scripts/query_cache.py)

内存后端容量 128，按访问顺序淘汰，TTL 为 300 秒。Redis 后端用一次 `SET ... PX` 写入键与过期。读取不续期。改变 epoch 即切换命名空间，旧键按原 TTL 自然清理。拒答、失败、损坏、引用不符和过大的结果均不会从缓存返回。缓存读取或写入无法完成时，入口返回真实问答结果及旁路状态。Redis 值含回答与引用，本机示例绑定 loopback，独立实例关闭持久化。 [Redis SET](https://redis.io/docs/latest/commands/set/) · [应用入口](../scripts/run_cached_query.py)

本机 Docker Linux 引擎未运行，默认 Redis TCP 端口拒绝连接。本次延迟使用内存后端。独立 redis-py 客户端验证了真实连接拒绝后回源，Redis 写入过期命令由接口测试覆盖。Redis 服务端命中、实际 TTL 和网络延迟待测。 [本机连通性证据](../reports/task16/redis-availability.json) · [Redis Windows 安装说明](https://redis.io/docs/latest/operate/oss_and_stack/install/install-redis/install-redis-on-windows/)

## 测量与取舍

使用独立编写的两组问题，每组 6 条已预热的锚点和 24 个探针。每组有 6 个原句、12 个同意图改写、6 个只改关键条件的难负例。标签判定同一答案能否复用，样本由本实验编写，未经裁判独立复核。各阈值在开发集选定前就已列出。本机 BGE-M3 编码，使用余弦排名。留出集的主题与开发锚点分开。 [问题与依据](../data/eval/cache_query_workload_v1.json) · [冻结记录](../reports/task16/holdout-freeze.json)

| 留出方法 | 命中/24 | 正确命中 | 错误命中/命中 | 查找命中 P50/P95 ms | 查找未命中 P50/P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| 精确 | 6 | 6 | 0/6 | 0.00890/0.02965 | 0.00340/0.01513 |
| 语义 0.85 | 19 | 13 | 6/19 | 0.45235/0.69438 | 0.46825/0.63888 |
| 语义 0.90（开发首选） | 12 | 8 | 4/12 | 0.24260/0.65198 | 0.47165/0.66724 |
| 语义 0.95 | 8 | 6 | 2/8 | 0.00935/0.52405 | 0.48125/0.70375 |
| 语义 0.98 | 7 | 6 | 1/7 | 0.00910/0.44920 | 0.48125/0.70285 |

每个探针有 16 次计时。查找包含内存读取、封包校验与语义候选排序。语义组先查精确缓存，命中延迟会混合两类实际命中路径。上表使用预计算向量，单列两组各 24 个去重文本的实际 Embedding 批次耗时 3.58 s 与 3.79 s。实际线上语义匹配每次精确未命中都需先得出查询向量。所有 P50/P95 都从原始纳秒读数插值得到。 [开发结果](../reports/task16/dev/summary.json) · [留出结果和逐题错误](../reports/task16/holdout/summary.json) · [留出向量与计时清单](../reports/task16/holdout/run_manifest.json)

按每个未命中一次下游请求的预算，精确缓存将 24 次降为 18 次。0.90 的表面下游次数为 12，实际只有 8 次安全复用，新增的 6 次语义命中里有 4 次错误。0.98 仍将角球直接入本方球门匹配到入对方球门，相似度 0.99269。不同条款、动作对象或前提可以共享词汇，单看相似度不足以安全复用。原 RAG 答案准确率是另一项指标。 [原始相似度](../reports/task16/holdout/observations.json)

真实重复问答另测。未启用缓存两次均调用原工作进程。精确缓存一次 miss 后一次 hit，输出相同回答哈希和引用 ID，该 hit 少 1 次 Embedding、40 个重排对和 1 次生成。该单个 miss 约 15.57 s，hit 约 15.96 ms。序列含模型预热变化，因此这里只报告实际单次耗时与调用计数。 [真实问答回执](../reports/task16/live-exact.json)

## 试运行与复算

使用原任务十三的本机环境和已就绪的 Ollama。同一进程读入两行以复用内存缓存。

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$question = '标准成人足球比赛的球门宽度是多少？'
@($question, $question) | & .runtime/task13/venv-final/Scripts/python.exe -B scripts/run_cached_query.py --backend memory --epoch local
```

已有独立 Redis 时，可用单独 Python 环境安装 redis-py 5.2.1，用 `--backend redis --redis-port 6379 --epoch local` 运行同一入口。换 epoch 可立即停用旧缓存。原 worker 仍从任务十三固定的环境执行。

```powershell
python -S -B scripts/verify_query_cache.py --report .tmp/task16-replay-new.json
python -S -B scripts/verify_task16_delivery.py --public-only --report .tmp/task16-delivery-new.json
```

完整公开验收在干净克隆中使用完整 Git 历史。真实语义复跑用新克隆从开发清单的生成提交开始，准备固定 BGE-M3 和 NumPy 1.26.4，运行 `run_cache_experiment.py dev`，提交开发结果，运行并提交 `freeze`，然后运行 `holdout`。默认报告目录为新的 `reports/task16/dev` 与 `reports/task16/holdout`，原结果受排他写入保护。 [开发清单](../reports/task16/dev/run_manifest.json)
