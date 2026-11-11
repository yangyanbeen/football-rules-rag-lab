# 运行环境层

- 固定上游：Kotaemon v0.12.0 / `9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9`，Apache-2.0。
- Python：已验收环境 3.10.22；依赖使用固定上游的 uv.lock。
- 本地模型：Ollama qwen2.5:3b、bge-m3；模型与账号数据库不进 Git。
- 配置示例：根目录 `.env.example`；原启动器不会自动加载它，须按文档设置环境或页面配置。
- 资源准备和兼容：`scripts/prepare_kotaemon_assets.py`、`kotaemon_runtime_env.py`。
- 安装入口：[PUBLIC_SETUP](../docs/PUBLIC_SETUP.md)；历史已执行记录：[LOCAL_SETUP](../docs/LOCAL_SETUP.md)。
- 当前核心安装：`scripts/install_local_runtime.ps1`，本目录独立 Python/虚拟环境；从原锁导出核心依赖，260 + 两个源码包。可选高级/图/开发 extras 不包含。
- 当前复核：[FRESH_ACCEPTANCE](../docs/FRESH_ACCEPTANCE.md)，新实例 7861；未复用旧虚拟环境或索引数据库，显式复用本机 Ollama 模型服务。

本轮不增加 Docker、远程部署或 CI 模型任务；这些尚未在原任务中完成。
