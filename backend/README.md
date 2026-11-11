# 后端层

当前后端是同一 Kotaemon/Gradio Python 进程的推理覆盖层，尚未新增 FastAPI 或独立 REST 服务。

| 文件 | 职责 |
| --- | --- |
| `scripts/run_kotaemon_local.py` | 加载固定上游、Windows 文档存储兼容层与本地推理实现 |
| `scripts/football_quality_pipeline.py` | 复用用户所选文件检索边界，将完整答案和引用输出到 Gradio |
| `scripts/football_evidence.py` | 原知识段检索、模型选 ID、完整证据恢复和引用校验 |
| `config/answer_quality.json` | 模型、上下文和候选数量配置 |
| `scripts/run_answer_quality_regression.py` | 原已交付开发回归入口，非锁定评测集 |

为保留原数据 manifest 的实现哈希与相对路径，这些脚本本轮仍位于 scripts/。未来迁移为 Python 包时单独增加任务、兼容入口和验收记录。
