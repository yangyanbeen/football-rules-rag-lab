# 任务一至三补交付与复核说明

日期：2026-11-11。依据仍为原 `TECHNICAL_DESIGN.md` 与 `DEVELOPMENT_PLAN_AND_REPORT.md`，不修改其内容、任务范围或通过条件。

## 审核发现与补齐

| 发现 | 补齐方式 | 交付证据 |
| --- | --- | --- |
| 公开 checkout 缺任务一要求路径的 project_file_manifest | 新增该路径的当前文件清单与生成/只读验证工具；记录路径、字节、SHA-256、用途和公开/仅本地属性 | `data/manifests/project_file_manifest.json`、`scripts/manage_delivery_manifest.py` |
| 部分任务二证据仅在原工程，公开仓库链接不能直接查看 | 导出当前服务/启动记录、运行代码对应关系与明确标注日期的历史 UI 三问摘要 | `reports/evidence/` |
| 开发回归脚本缺少公开输入文件 | 补回原有 16 条开发问题与标签，不新增或伪造测试集 | `data/quality_regression/development_cases.jsonl` |
| 引用契约检查写死旧报告路径，不方便保留历史 | 增加 `--regression-report`、`--output`；保留旧默认参数 | `scripts/verify_answer_quality.py` |
| 原任务三验收入口会重写固定名称的报告 | 增加隔离副本执行入口，原 suite 不改，原输入与历史报告保持不变 | `scripts/verify_task3_isolated.py` |
| 当前应用和 Ollama 均已停止，历史 PASS 不能代表服务在线 | 按原本机配置恢复两服务，再执行原在线验收及开发回归 | `reports/evidence/task1_task2_before_service_restart.json`、`reports/acceptance/` |

这次补的是前三项任务的交付完整性和复核入口，没有提前替代任务四至十四。

## 当前独立环境入口

上一轮依赖原环境的缺项已关闭：新实例 http://127.0.0.1:7861/，普通账号拥有五份原资料，浏览器三问重新完成。原锁文件、原标准和 Corpus B0 不变。核心依赖 260 个、固定本地包两个；不包含可选高级/图/开发 extras。

按 [PUBLIC_SETUP](PUBLIC_SETUP.md) 安装，按 [FRESH_ACCEPTANCE](FRESH_ACCEPTANCE.md) 采集新 UI 证据并执行 `scripts/recheck_fresh_delivery.ps1`。当前回执 `reports/acceptance/fresh_delivery.json` 为 33/33，旧回执不覆盖。

## 上一轮复用原环境的完整入口（历史）

先按原 LOCAL_SETUP 启动既有 Ollama 与 Kotaemon。对已有固定环境执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/recheck_tasks_01_03.ps1 -RuntimeRoot "<已有原工程目录>"
```

该命令依次运行原任务一二在线验收、任务三隔离 suite、16 条开发回归、19 项引用契约，并导出有明确范围的摘要。命令实际执行通过；细节见 `reports/TASK_01_03_REDELIVERY.md`。

- 原运行环境的 `.venv`、上游源码、模型和索引继续复用，没有把它们假装安装到公开 checkout。
- 完整模型回答只写入新 checkout 的忽略目录 `.runtime/task123-recheck-*/`。
- 原任务一二新验收报告写入原工程忽略的 `.tmp/`，原静态文件不变。
- 数据 suite 在新 checkout 的 `.tmp/task3-isolated-*/` 副本中执行，损坏数据只在副本中注入。
- 公布的历史 UI 三问保留原日期；本轮新跑的 16 问是后端开发回归，二者不混称“新 UI 三问”。

## 文件清单的区别

1. 原工程 `project_file_manifest.json`：原本机完整静态交付，177 项及 10 个日志快照，保留原字节。
2. `reports/PUBLICATION_MANIFEST.json`：首次导入 Git 的历史快照，记录当时的原件哈希；不是后续提交的实时覆盖清单。
3. 新 checkout `data/manifests/project_file_manifest.json`：本次补交付的当前清单；包括 Git 跟踪文件和仅本地语料的哈希元数据，排除自身以避免递归哈希。

每次提交新文件前，先暂存明确的文件，再更新清单、只读校验，最后提交清单：

```powershell
python scripts/manage_delivery_manifest.py
python scripts/manage_delivery_manifest.py --verify
git add data/manifests/project_file_manifest.json
```

该清单不会上传全文。`data/raw/`、`data/processed/`、账号、数据库、模型和会话缓存继续按原规则留在本地。修改已跟踪文件后，也要重新生成清单。

## 仍需保留的边界

- 任务二通过运行标准，不代表已完成正式 RAG B0 或正式答案评测。
- 开发问题已经用于调试，16/16 不等于独立测试集准确率。
- 任务三数据中 parent 全部为 null；没有虚构父子关系或规则专家审校。
- Wikipedia 是二手来源；可见修订号与历史正文独立核验是不同事项。原翻译、28 条复核提示及版本边界继续保留。
