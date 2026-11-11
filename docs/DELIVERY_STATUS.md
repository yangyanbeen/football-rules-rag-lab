# 当前进度与交付索引

日期：2026-11-11。原设计/执行文档是冻结的历史基线，其中的历史进度、未初始化 Git 等描述不改写；当前事实由本页及对应交付报告补充。

| 任务 | 状态 | 原交付要求与已交付文件 | 证据 |
| --- | --- | --- | --- |
| 1 审计与冻结 | 已交付 | PROJECT_AUDIT、EXPERIMENT_LOG、原本机 project_file_manifest、基线锁 | TASK_01_02_DELIVERY、TASK_01_02_RECHECK、task1_task2_after-task3.json；32/32 为任务一二联合结果 |
| 2 固定应用与本机运行 | 已交付 | UPSTREAM_VERSION、LOCAL_SETUP、启动脚本、KOTAEMON_BASELINE | 同上；质量修复见 ANSWER_QUALITY_FIX_2026-11-11.md；UI/引用检查 5/5 |
| 3 统一数据结构 | 已交付 | RAG_DATA_SCHEMA、build/validate 脚本、两份派生 JSONL、数据 manifest | TASK_03_DELIVERY；主校验 18/18、交付 8/8、坏数据拒绝 16/16 |
| 4 人工检索/答案评测集 | 进行中，未交付 | 40开发/50测试候选、90答案标签和90负例；标注/验证/冻结工具 | 结构22/22、自动工作流27/27；真实人工0/90，正式门禁未通过，测试未冻结 |
| 5–14 | 按原计划继续 | 正式索引、RAG B0、检索优化、打包与实验归档 | 尚未完成，不填虚构性能数字 |

任务 3 的两份完整 JSONL 和任务 1 的原始/处理语料保留本地、不纳入公开 Git；来源清单、稳定 ID 映射、输出哈希和代码已纳入。原本机 project_file_manifest 包含不可公开的运行归档，本仓库提供独立 `reports/PUBLICATION_MANIFEST.json`；二者范围不同，不相互替换。

## 首次导入做了什么（历史）

1. 创建独立的新仓库目录；原工程未初始化 Git、未搬移、未改写。
2. 原技术设计、执行文档、原脚本和选定报告按字节复制；映射见 PUBLICATION_MANIFEST。
3. 增加分层说明、公开复现入口、PR 模板与 Git 回滚说明。
4. 既有成果分任务导入，建立可追踪的小提交。没有重跑模型、重建索引或变更任务验收条件。

本仓库 Git 历史从整理日开始；此前的开发过程由原报告和 SHA-256 记录。公开仓库的导入提交不能用来推断此前实验的运行时间。

## 补交付复核（2026-11-11）

原要求保持不变，按 [逐项补交付报告](../reports/TASK_01_03_REDELIVERY.md) 重新检查并补齐：任务一规定路径的当前文件清单、任务二运行证据和开发题输入，以及不覆盖历史报告的复核入口。

原任务一二重新在线验收 32/32；任务三主校验 18/18、交付 8/8、坏数据拒绝 16/16；新开发回归 16/16、引用契约 19/19。原工程 178 个静态文件未变。机器汇总见 `reports/acceptance/task123_recheck_summary.json`。

上段为上一轮补交付结果。后续缺陷关闭已在新目录真实安装独立环境（260 个核心依赖 + 两个固定本地包），新建空数据库与普通账号并从浏览器上传五份资料，重新提交三问。综合检查 33/33、UI 三问 3/3、开发回归 16/16、引用契约 19/19；任务三原 suite 继续通过。证据为 `reports/acceptance/fresh_delivery.json` 和 `reports/evidence/fresh_ui_three_questions.json`。

运行入口见 [PUBLIC_SETUP](PUBLIC_SETUP.md)，验收与重新采集方法见 [FRESH_ACCEPTANCE](FRESH_ACCEPTANCE.md)。旧的外部环境复核结果保留为历史。任务四至十四状态不变。

## 任务四候选准备（当前进行中）

范围见 [TASK_04_SCOPE](TASK_04_SCOPE.md)，标注/复核规则见 [EVAL_DATASET](EVAL_DATASET.md)，当前逐项检查见 [TASK_04_DELIVERY](../reports/TASK_04_DELIVERY.md)。候选数据与自动工具已备齐，人工核对仍需真实复核人完成；不会将程序检查计作人工签收。仅候选分支/草稿PR，未合并成完成版本，也未进入任务五。
