# 前端层

当前 UI 是固定版本 Kotaemon 的 Gradio 页面，位于本地 `third_party/kotaemon-v0.12.0/libs/ktem/ktem/pages/`，不重复上传上游源码，也没有伪造独立前端工程。

- 入口：`frontend/start.ps1`，转调原 `scripts/run_baseline_check.ps1`。
- 来源面板：由 `scripts/football_quality_pipeline.py` 接入并调用 `football_evidence.py` 渲染。
- 后续界面改动：另建 `feat/ui-...` 分支，追加验收条件；不能顺便改变原语料或评测口径。
- 新环境步骤：见 [PUBLIC_SETUP](../docs/PUBLIC_SETUP.md)。
