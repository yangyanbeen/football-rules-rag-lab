# 从公开仓库恢复运行环境

这是新公开仓库的操作入口。历史 LOCAL_SETUP 保留原文；下列命令均在新仓库根目录执行。

## 1. 取得代码与已有本地数据

```powershell
git clone https://github.com/yangyanbeen/football-rules-rag-lab.git
cd football-rules-rag-lab
python scripts/import_local_corpus.py --source <你的原football-rules-rag-project目录>
```

本机使用新目录时已有代码，无需再次 clone。导入器按公开清单只复制已锁定的 data/raw 和 data/processed 文件，逐文件核对 SHA-256；目标若有不同内容则拒绝覆盖。它不复制数据库、账号、索引、缓存、模型或依赖，不改写来源目录。导入后的全文继续由 `.gitignore` 排除。

没有原语料副本的使用者可以阅读代码、Schema 和来源清单，但不能直接复现这一批固定快照；从今天的网页重抓会得到不同数据版本，必须另建任务和版本，不能冒充原 Corpus B0。

## 2. 准备固定上游与依赖

安装 Git、uv，以及本地 Ollama。按原已验收环境使用 Python 3.10.22：

```powershell
git clone --branch v0.12.0 --depth 1 https://github.com/Cinnamon/kotaemon.git third_party/kotaemon-v0.12.0
git -C third_party/kotaemon-v0.12.0 rev-parse HEAD
$env:UV_PROJECT_ENVIRONMENT = Join-Path (Get-Location) '.venv'
uv sync --locked --python 3.10.22 --project third_party/kotaemon-v0.12.0
.\.venv\Scripts\python.exe scripts/prepare_kotaemon_assets.py
```

HEAD 必须等于 `9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9`。不得改用浮动 main。新环境需要网络与磁盘空间；当前发布操作不安装依赖或重新下载模型。

## 3. 模型和应用

启动 Ollama，准备 `qwen2.5:3b` 和 `bge-m3`。原模型 digest 记录在历史文档；可变模型标签重新拉取后须核对差异。

```powershell
ollama serve
# 另一个终端：
ollama pull qwen2.5:3b
ollama pull bge-m3
powershell -NoProfile -ExecutionPolicy Bypass -File frontend/start.ps1
```

访问 `http://127.0.0.1:7860/`，按 LOCAL_SETUP 在应用设置中配置 Ollama、上传原五份 Markdown。用户账号、会话和上传索引由新环境创建，不从旧数据库迁移。仅在可信本机使用；环境示例绑定 127.0.0.1，不开启 Gradio 分享。模型设置和安全配置以实际固定版本页面为准。

界面冒烟的 50 个临时 chunk 不替代任务三的 99 条统一格式数据；后者需要按后续任务继续接入正式索引。

## 4. 数据工具

已有全文、公开清单及原文档到位后，任务三原命令为：

```powershell
python scripts/build_rag_dataset.py
python scripts/validate_rag_dataset.py
python scripts/verify_task3_delivery.py
```

这些是复现操作说明，此次发布没有执行它们。任务一二的完整在线验收依赖原本机日志、截图和数据库等状态，不能只靠公开副本声称重新通过；原通过结果参见 reports 中的历史证据。

## 5. 补交付后的统一复核入口

首次导入时没有重跑测试；后续补交付已实际重新执行。当前结果与历史记录分开，见 `reports/TASK_01_03_REDELIVERY.md`。

复用原已安装环境、语料到位且两项本地服务启动后，在新 checkout 根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/recheck_tasks_01_03.ps1 -RuntimeRoot "<已有原工程目录>"
```

该入口明确复用原 Python/模型，不表示公开目录已装完整依赖。任务三在隔离副本执行，不覆盖原报告。16 条开发题已补入 `data/quality_regression/`，完整模型回答写忽略的 `.runtime/`，公开摘要在 `reports/acceptance/`。

单独检查引用契约时可指定本轮输出，不必改名或覆盖旧报告：

```powershell
python scripts/verify_answer_quality.py --regression-report <本次本地回归JSON路径> --output reports/acceptance/answer_quality_contract.json
```

完整参数、公开文件清单维护及范围说明见 `docs/TASK_01_03_SUPPLEMENT.md`。
