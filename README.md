# 足球规则 RAG Lab

基于 [Cinnamon/kotaemon](https://github.com/Cinnamon/kotaemon) 的足球规则中文问答与可追溯语料工程。面向逐项实现、真实评测和可回滚开发。

**当前已交付任务 1–3。** 本仓库于 2026-11-11 将既有交付按小提交导入 Git；提交时间是整理发布时间，不冒充原来的开发历史。

## 先看什么

1. [当前进度与交付基线](docs/DELIVERY_STATUS.md)：哪些已完成，哪些未做。
2. [技术文档](docs/TECHNICAL_DESIGN.md) 和 [原执行文档](docs/DEVELOPMENT_PLAN_AND_REPORT.md)：原件逐字节保留。
3. [架构与分层](docs/ARCHITECTURE.md)：前端、后端、数据和运行环境的边界。
4. [Git 与 PR 工作流](docs/GIT_WORKFLOW.md)：建分支、小提交、PR、合并及回滚。
5. [公开仓库复现说明](docs/PUBLIC_SETUP.md)：恢复本地语料并准备依赖。

## 目录

| 层 | 目录/入口 | 现状 |
| --- | --- | --- |
| 前端 | [frontend/](frontend/README.md) | 复用固定版本 Kotaemon 的 Gradio UI；启动入口 `frontend/start.ps1` |
| 后端 | [backend/](backend/README.md)、`scripts/football_*.py` | 本地证据选择、引用恢复及运行时兼容层；与 UI 同进程 |
| 数据 | [data/](data/README.md)、`scripts/build_rag_dataset.py` | 冻结语料、稳定 ID、统一 Schema、独立校验与来源清单 |
| 环境 | [infra/](infra/README.md)、`config/` | 上游 commit、锁定依赖、本地模型配置 |
| 设计与执行 | `docs/` | 原技术设计、14 项任务计划及新增 Git 治理说明 |
| 交付证据 | [reports/](reports/README.md) | 已有报告、历史验收结果、原文件与公开副本哈希映射 |

已有脚本依赖项目根目录的相对路径。首次导入保留原字节，后续修复由 PR 记录；位置继续保留，后续模块迁移须单独建任务与 PR。当前没有独立 Vue/React 前端或 REST API 服务。

## 当前交付

- 任务 1：5 份中文分卷、99 个稳定知识段、18 页来源的审计和冻结。
- 任务 2：Kotaemon v0.12.0 本机运行；Windows 兼容启动器；证据回答与引用修复。
- 任务 3：Schema 1.0.0，99 条中文及 99 条英中对照的统一格式适配；原 ID、正文与来源边界不变。
- 历史验收：任务 1/2 共 32/32；任务 3 主校验 18/18、交付检查 8/8，16 类坏数据被拒绝。首次整理未重跑模型或应用；后续实测结果见下方补交付章节。

任务 4 的人工评测集、正式 RAG B0、BM25/RRF/Reranker、检索性能优化等继续按原计划实施。16 条已调试问题的通过情况不等于锁定测试集准确率；本项目尚无正式 Recall、MRR、nDCG 或延迟优化成绩。

## 数据与运行

原文档约定 `data/raw/`、`data/processed/` 默认不进 Git，此公开仓库保持该规则。源码、Schema、来源与版本清单公开，**五份规则全文及两份任务三 JSONL 留在本地**。仅克隆仓库不能直接得到完整问答语料。

在已有语料的机器上，可按 [PUBLIC_SETUP](docs/PUBLIC_SETUP.md) 导入原项目资料；导入命令只复制已知数据文件，不复制账号、数据库、模型或缓存。需要安装 Git、uv、固定 Kotaemon/Python 依赖和本地 Ollama 模型。

资料来自 Wikipedia 社区概述，中文为 AI 翻译且未经过裁判专家审校，不是 IFAB 官方赛季规则书。许可、可见 revision 与尚未独立核验历史正文的边界均保留，见 [数据说明](data/README.md)。

## 版本管理

`main` 用于已交付版本，任务分支采用 `feat/task-XX-name`，修复用 `fix/name`。每次改动通过 PR 留下目标、基线、提交与实际验证记录。回滚用 `git revert` 新增撤销提交，不改写公开历史。

本仓库独立新建；未向原有仓库写入、推送、发 PR 或修改设置。原本地工程也保持原状。

## 任务一至三补交付复核

已按原标准重新检查并补齐交付缺项，详见 [逐项交付报告](reports/TASK_01_03_REDELIVERY.md) 和 [补交付操作说明](docs/TASK_01_03_SUPPLEMENT.md)。本次实际重跑结果：任务一二 32/32，任务三主校验 18/18、交付 8/8、坏数据拒绝 16/16，开发回归 16/16、引用契约 19/19。

首次导入报告继续作为历史证据；各轮实测结果在 `reports/acceptance/`，原技术/执行文档和 Corpus B0 不变。

后续已关闭新目录未安装、普通账号无资料和 UI 仅有历史证据的缺项：独立环境 262 个包，普通账号五份原文/50 个临时块，真实新 UI 三问 3/3，综合检查 33/33。新实例访问 [127.0.0.1:7861](http://127.0.0.1:7861/)。当前复核入口与证据采集见 [FRESH_ACCEPTANCE](docs/FRESH_ACCEPTANCE.md)。

## 任务四负责人批量签收

40开发题、50测试题、90条答案标签和90对难负例已按用户最新授权批量批准并冻结。结构22/22、工作流27/27、负责人签收检查全部通过；保留2条真实逐题人工记录，**没有把批量批准当成90题人工gold**。说明见 [负责人签收](docs/TASK_04_OWNER_ACCEPTANCE.md)，完整状态见 [任务四报告](reports/TASK_04_DELIVERY.md)。本机记录页：[127.0.0.1:7862](http://127.0.0.1:7862/)。
