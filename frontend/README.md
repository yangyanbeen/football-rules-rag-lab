# 前端层

当前 UI 是固定版本 Kotaemon 的 Gradio 页面，位于本地 `third_party/kotaemon-v0.12.0/libs/ktem/ktem/pages/`，不重复上传上游源码，也没有伪造独立前端工程。

- 入口：`frontend/start.ps1`，转调原 `scripts/run_baseline_check.ps1`。
- 来源面板：由 `scripts/football_quality_pipeline.py` 接入并调用 `football_evidence.py` 渲染。
- 后续界面改动：另建 `feat/ui-...` 分支，追加验收条件；不能顺便改变原语料或评测口径。
- 新环境步骤：见 [PUBLIC_SETUP](../docs/PUBLIC_SETUP.md)。


## 任务六：正式RAG B0入口

`frontend/start_rag_b0.ps1`启动固定Kotaemon App/ChatPage，访问http://127.0.0.1:7863/。新增只读足球知识库选择器，不上传文件或网页；完整答案与证据面板由rag_b0_pipeline.py接入。原7861入口保持原样。

本机真实页面已提交三条规则问答及一条资料外问题，DOM、最后回答、原文面板/链接和trace ID逐条核对；见reports/evidence/rag_b0_ui_manifest.json。运行和复现见docs/RAG_B0.md。
