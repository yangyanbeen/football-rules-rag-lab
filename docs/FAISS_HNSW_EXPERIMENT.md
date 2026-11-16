# FAISS HNSW 检索实验

在原 Corpus B0 的 99 条 1024 维向量上，按开发集规则选择 Flat。锁定测试中，达到精确 Top10 重合门槛的 HNSW 配置维持了标注质量，查询 P50/P95 为 12.2/16.5 µs，Flat 为 9.1/11.2 µs。部署决策为保留当前应用。 [原任务十五标准](DEVELOPMENT_PLAN_AND_REPORT.md) · [交付验收](../reports/TASK_15_DELIVERY.md)

## 配置和测量

所有配置使用同一组 L2 归一化的 BGE-M3 float32 文档向量及其稳定 ID。原始 NPY 与原向量指纹均通过 SHA256 核对。每题由 Ollama 0.40.16 上的固定 BGE-M3 模型编码一次，各方法复用该查询向量。内积与单位向量余弦相同，FlatIP 对全部向量做精确搜索。基准运行于同一台 Windows x64 CPU 机器，FAISS 1.11.0 AVX2，FAISS 单线程。 [原向量清单](../data/manifests/dense_index_manifest.json) · [固定配置](../config/faiss_hnsw_experiment.json) · [FAISS 官方索引说明](https://github.com/facebookresearch/faiss/wiki/Faiss-indexes)

| 方法 | M | efConstruction | efSearch | 对照关系 |
| --- | ---: | ---: | ---: | --- |
| FlatIP | — | — | — | 精确排序 |
| HNSW 参考 | 16 | 100 | 16 | 三组参数对照的参照 |
| HNSW M8 | 8 | 100 | 16 | 减少图连接数 |
| HNSW C40 | 16 | 40 | 16 | 减少构建搜索深度 |
| HNSW S64 | 16 | 100 | 64 | 同一参考图，提高查询搜索深度 |

质量指标使用原计划的 Recall@K 和 MRR@10。Recall@K 以可回答问题为分母，命中一个人工核对的支持段即可计入。Top10 重合率衡量与精确 Flat 的结果集合共有多少项，每题分母为10，纳入全部问题。40 道开发题中的32题可回答，50 道测试题中的40题可回答。

查询计时覆盖所有题，每种方法每题搜索32次。预热后按固定种子轮转方法顺序。测量包含 Python 调用 FAISS 的开销，起止点为 `index.search`，与 Embedding、索引装载和评分分开。P50/P95 使用线性插值。微秒级结果受系统调度影响，32次重复用于测延迟，质量分母依然是问题数。

每个物理索引由三个独立进程各构建一次，三次序列化文件的 SHA256 一致。构建时间包括创建索引和加入向量，文件写入另行记录大小。RSS 取加入向量前后的进程驻留内存，用中位差描述变化，包含分配器和进程内其他内存变化。Windows 进程峰值及三次原读数均保留。 [构建逐次证据](../reports/task15/dev/builds.json) · [测试运行环境](../reports/task15/test/run_manifest.json)

## 结果与保留方案

开发集按 Flat 的 Recall@5、Recall@10、MRR@10 以上及 Top10 重合率至少99%筛选，再比较搜索 P50。Flat 与 S64 通过筛选，Flat 的开发 P50 为 8.75 µs，S64 为 11.70 µs。选择在测试前提交，五组全部按冻结配置报告。 [开发汇总](../reports/task15/dev/summary.json) · [测试冻结记录](../reports/task15/test-freeze.json)

| 锁定测试方法 | Recall@5 / @10 | MRR@10 | 精确 Top10 重合 | 搜索 P50/P95 µs |
| --- | ---: | ---: | ---: | ---: |
| FlatIP | 97.5% / 97.5% | 0.868750 | 100% | 9.1 / 11.2 |
| HNSW 参考 | 97.5% / 97.5% | 0.868750 | 98.2% | 7.7 / 10.3 |
| HNSW M8 | 97.5% / 97.5% | 0.872917 | 97.4% | 9.4 / 12.8 |
| HNSW C40 | 97.5% / 97.5% | 0.868750 | 98.0% | 8.5 / 11.5 |
| HNSW S64 | 97.5% / 97.5% | 0.868750 | 100% | 12.2 / 16.5 |

| 物理索引 | 构建 P50/P95 ms | 文件字节 | 构建 RSS 中位增量 KiB |
| --- | ---: | ---: | ---: |
| FlatIP | 0.065 / 0.079 | 405549 | 52 |
| HNSW 参考与 S64 共享 | 13.198 / 23.475 | 419998 | 240 |
| HNSW M8 | 3.889 / 4.085 | 413846 | 236 |
| HNSW C40 | 4.361 / 17.663 | 419998 | 236 |

参考组测试 P50 少 1.4 µs，有7题的 Top10 成员发生变化。M8 的标注 MRR 略高，精确 Top10 重合率为四个 HNSW 组最低。S64 在该样本上精确 Top10 重合率为100%，但比 Flat 耗时更长。开发期预选结论为保留 Flat 作为实验对照。现有库仍按原应用配置运行。报告适用范围是99条向量的单线程本机微基准，规模扩展、端到端延迟和吞吐为待测。 [测试汇总及逐题差异](../reports/task15/test/summary.json) · [逐题排名和计时](../reports/task15/test/predictions.jsonl)

## 复算和本机复跑

在发布版本的仓库根目录复算。完整公开验收在无本地数据和环境目录的干净克隆内执行。报告路径须为仓库内的新文件。公开复算读取原标签、逐题排名、原始纳秒计时和构建读数。用 Python 3.10 或更高版本执行，完整 Git 历史用于校验生成提交。

```powershell
python -S -B scripts/verify_faiss_hnsw.py --report .tmp/task15-replay-new.json
python -S -B scripts/verify_task15_delivery.py --public-only --report .tmp/task15-delivery-new.json
```

正式结果已归档。复跑可在独立完整克隆中从开发运行的生成提交开始，按 [原向量准备说明](EMBEDDING_AND_INDEX.md) 恢复原任务五的 `embeddings.npy`，启动已安装固定 BGE-M3 的本机 Ollama。如果使用非默认端口，设置 `FOOTBALL_DENSE_OLLAMA_URL` 指向该 loopback 地址。FAISS 运行环境单独安装。 [开发运行生成提交和命令](../reports/task15/dev/run_manifest.json) · [FAISS CPU 发行包](https://pypi.org/project/faiss-cpu/1.11.0/)

```powershell
uv venv --python 3.10.22 .runtime/task15/venv
uv pip install --python .runtime/task15/venv/Scripts/python.exe --only-binary :all: faiss-cpu==1.11.0 numpy==1.26.4 packaging==24.2 psutil==6.1.1
$python = '.runtime/task15/venv/Scripts/python.exe'
& $python -B scripts/run_faiss_hnsw.py dev
git add reports/task15/dev
git commit -m "Record reproduction development measurements"
& $python -B scripts/run_faiss_hnsw.py freeze
git add reports/task15/test-freeze.json
git commit -m "Freeze the reproduction test configuration"
& $python -B scripts/run_faiss_hnsw.py test
```

`dev` 和 `test` 使用新的固定目录。开发运行创建的查询向量和二进制索引保存在本机 `.runtime/task15`。新环境会产生新的计时、内存读数和选择记录，应按独立复跑保存。
