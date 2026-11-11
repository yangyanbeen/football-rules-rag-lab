# 后端层

任务二后端是同一 Kotaemon/Gradio Python 进程的推理覆盖层，尚未新增 FastAPI 或独立 REST 服务。

| 文件 | 职责 |
| --- | --- |
| `scripts/run_kotaemon_local.py` | 加载固定上游、Windows 文档存储兼容层与本地推理实现 |
| `scripts/football_quality_pipeline.py` | 复用用户所选文件检索边界，将完整答案和引用输出到 Gradio |
| `scripts/football_evidence.py` | 原知识段检索、模型选 ID、完整证据恢复和引用校验 |
| `config/answer_quality.json` | 模型、上下文和候选数量配置 |
| `scripts/run_answer_quality_regression.py` | 原已交付开发回归入口，非锁定评测集 |

为保留原数据 manifest 的实现哈希与相对路径，这些脚本本轮仍位于 scripts/。未来迁移为 Python 包时单独增加任务、兼容入口和验收记录。

任务五另交付scripts/dense_index.py、build_dense_index.py与query_dense_index.py，提供固定99段独立索引和可重复读取/查询的适配层。该模块尚未接管现有应用问答；任务六再接入，避免将现有50块临时索引当作新正式索引。固定配置为config/dense_index.json，原环境/模型池与用户数据库不改。


## 任务六：生成式RAG B0

新入口使用rag_b0.py接通任务五DenseIndex和本机Qwen中文生成；rag_b0_worker_client.py提供进程边界，避免本机完整UI导入后的HNSW原生异常。每条UI请求启动独立Python问答进程，串行调度；没有新增REST服务。原证据摘录链路和旧应用未改。

当前配置固定Top5召回、最多1个完整生成证据块、最多1次无效输出重试。回答来源由程序绑定已提供块；数值/格式/重复/残句不通过则拒绝，不能当作完整语义验证。详情及故障记录见docs/RAG_B0.md、reports/TASK_06_DELIVERY.md。
