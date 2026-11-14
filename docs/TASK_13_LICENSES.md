# 来源、署名与许可

本页区分代码、模型和语料；仓库代码许可证不会自动覆盖它们。核对日期：2026-11-14。这里记录来源和运行边界，不重新发布规则全文或模型权重。

| 内容 | 来源与许可记录 | 本仓库交付方式 |
| --- | --- | --- |
| 项目集成/实验代码 | 根目录Apache-2.0，保留LICENSE/NOTICE | 源码与配置公开 |
| Kotaemon v0.12.0 | 固定commit9ad3e4e…fdf9，Apache-2.0；见UPSTREAM_VERSION | 使用者单独取得原上游，不把依赖源码混作个人成果 |
| Wikipedia来源和AI中文整理 | 每段保留Wikipedia contributors、URL/行号、CC BY-SA4.0元数据、来源修订核验状态和翻译/审校标志 | 完整资料只在本机；公开来源清单、稳定ID、元数据和hash |
| BGE-M3 | [BAAI原模型卡](https://huggingface.co/BAAI/bge-m3/blob/main/README.md)标MIT；本机Ollama artifact以config/dense_index.json完整digest核对 | 不上传权重；固定模型身份与使用配置公开 |
| BGE-reranker-base | [固定revision原模型卡](https://huggingface.co/BAAI/bge-reranker-base/blob/2cfc18c9415c912f9d8155881c133215df768a70/README.md)标MIT | 不上传约1.1GB ONNX；5文件hash和取得/核验入口公开 |
| Qwen2.5-3B-Instruct | [Qwen原LICENSE](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/LICENSE)为Qwen Research；本地qwen2.5:3b另以完整digest核对 | 不将其写成Apache-2.0模型，不上传权重；使用者按对应模型原条款核对用途 |

当前语料来自固定Wikipedia页面的整理，并不是IFAB官方某赛季规则授权全文。来源历史修订正文未独立核验、译文未获裁判专家审校的状态继续显示，不能把本地第N组编目当官方第N条依据。IFAB页面在本项目仅用于特定主题/编号核对，不据此声称已取得官方规则全文的再发布许可。

界面和完整答案展示署名、来源与许可链接，并保留整段条件、否定、单位、例外和校核提示。语料导入保持原字节；代码Apache与语料的署名/相同方式共享要求分开。模型、语料、UI数据库、用户姓名/审核备注、原始长回答和真实凭据不进入公开Git。

本机完整演示截图/DOM快照也按本地证据保留，仅公开其SHA和关联请求；不借截图把原本不公开的整段正文重新发布。公开文件清单和发布检查再次核对禁止目录及凭据模式。
