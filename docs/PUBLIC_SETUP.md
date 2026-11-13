# 从公开仓库恢复运行环境

这是当前安装入口。原 LOCAL_SETUP 与技术/执行文档保留历史字节。命令在本仓库根目录执行；本机新目录已安装，无需再次克隆。

## 1. 取得代码与冻结语料

```powershell
git clone https://github.com/yangyanbeen/football-rules-rag-lab.git
cd football-rules-rag-lab
python scripts/import_local_corpus.py --source <你的原football-rules-rag-project目录>
```

导入器只复制清单允许的 61 个原始/处理文件，逐个核对 SHA-256；不覆盖不同内容的目标文件，不复制数据库、账号、索引或旧虚拟环境。全文继续由 .gitignore 排除。

没有原快照的使用者可以阅读代码、Schema 和来源清单，但仅克隆不能获得全文；从今日网页重抓属于新数据版本，不能冒充原 Corpus B0。

## 2. 固定上游并安装当前核心配置

安装 Git、uv、Ollama，预留依赖/缓存及模型空间。

```powershell
git clone --branch v0.12.0 --depth 1 https://github.com/Cinnamon/kotaemon.git third_party/kotaemon-v0.12.0
git -C third_party/kotaemon-v0.12.0 rev-parse HEAD
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_local_runtime.ps1
.\.venv\Scripts\python.exe scripts/prepare_kotaemon_assets.py
```

HEAD 必须是 `9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9`，不用浮动 main。安装脚本在本项目 .runtime/python 安装/选择独立 Python 3.10.22，在 .venv 安装两项 workspace 的核心运行依赖。从**原未改动 uv.lock** 导出 260 个当前平台依赖并用哈希校验安装，再安装两个固定源码包；不包含高级 torch、图和开发 extras。

首次安装需要网络；资源准备下载真实 NLTK 数据和 tokenizer 并核对发布者哈希，缓存留在本目录。若 raw.githubusercontent.com 不可达，NLTK 下载会尝试官方 GitHub 仓库 API，仍须通过相同 SHA-256。后续启动只验证资源，不自动联网下载它们。

已有完整项目缓存可加 `-Offline`。`-RecreateEnvironment` 会清理且仅清理本目录 .venv，通常无需使用；不要在服务运行时使用。`-UvExe <uv.exe路径>` 可选择未加入 PATH 的 uv。

## 3. 本地模型与应用

已有 Ollama 服务无需再次 serve。新机器先启动服务，再在另一终端准备模型与应用：

```powershell
ollama serve
# 另一个终端：
ollama pull qwen2.5:3b
ollama pull bge-m3
$env:GRADIO_SERVER_NAME = '127.0.0.1'
$env:GRADIO_SERVER_PORT = '7861'
powershell -NoProfile -ExecutionPolicy Bypass -File frontend/start.ps1
```

访问 [本机应用](http://127.0.0.1:7861/)。默认配置 FOOTBALL_LOCAL_PROFILE=1 已选用 Ollama qwen2.5:3b/bge-m3、私有文件集合和证据问答；未安装的图索引不显示，也不创建外部服务的默认模型。已有数据库的模型设置不会被启动器强行覆盖。模型可变标签重新拉取后须核对 digest；本轮回执核对原两个 digest。

首次建库生成随机 admin 密码，**仅存本机 .runtime/kotaemon-admin.json**。在本机查看文件后登录，进入 Resources → Users 创建普通账号，再退出 admin 并登录普通账号。本机已有普通账号 yanyanbeen，凭据在忽略的 .runtime/kotaemon-account.json；不要上传或粘贴这些文件到公开内容。

普通账号进入 File Collection → Upload Files，上传 data/processed/wikipedia_zh_2026-11-10 中 **01 至 05** 的五份 MD，点 Upload and Index；不要上传 00 阅读说明。全部完成后回到 Chat，选 Search All、关闭 Mindmap，开始提问。原账号私有文件不自动共享给新账号。

停止前台服务按 Ctrl+C。端口冲突时改 GRADIO_SERVER_PORT；本轮用 7861，旧 7860 实例保留。仅绑定本机，不开启 Gradio 分享。50 个 UI 临时块不替代任务三 99 条统一数据，正式索引仍按后续任务执行。

## 4. 当前验收入口

按 [FRESH_ACCEPTANCE](FRESH_ACCEPTANCE.md) 实际提交三问并采集本机 DOM，再执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/recheck_fresh_delivery.ps1 -UiCapture .runtime/ui-three-dom.json
```

使用本仓库 Python 验证资源与真实导入、隔离执行任务三原 suite、重跑 16 条开发题和 19 项引用契约，并核对已采集的新 UI 与同次管线记录。完整输出留本机，公开摘要到 reports/acceptance。这不会自动代替浏览器提问。

33/33 是本机本轮包含旧工程保全两项的数量；不提供旧工程保全参数时数量相应减少。当前结果见 [逐项交付报告](../reports/TASK_01_03_REDELIVERY.md)。旧的 recheck_tasks_01_03.ps1 -RuntimeRoot 入口用于重现上一轮外部环境验收，保留为历史入口。

## 5. 文件清单与边界

提交前暂存明确文件，运行 `python scripts/manage_delivery_manifest.py` 和 `--verify`，再暂存清单。原规范与冻结语料不改；完整回答、凭据、数据库、依赖、缓存不公开。

任务一至九已按原标准交付，当前状态见 [DELIVERY_STATUS](DELIVERY_STATUS.md)。16 条开发题已经用于调试，通过数不代表独立测试集准确率或 Recall/MRR/nDCG；检索基线来自任务七/八，任务九在原双路排名上完成冻结的融合对照。

重复验收会写入新的 reports/rechecks/fresh-时间戳目录，拒绝覆盖旧报告。指定本次应用的私有错误日志，避免拿旧日志证明当前启动：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/recheck_fresh_delivery.ps1 -UiCapture .runtime/ui-three-dom.json -StderrLog .runtime/my-run/app.stderr.log -ReportDir reports/rechecks/my-new-review
```

UiCapture 必须来自已完成的真实浏览器操作；也可传历史采集重验历史记录，报告明确标记重放。历史 recheck_tasks_01_03.ps1 用于阅读旧环境流程，当前复验使用本节入口。完整七项复验及证据映射见 [综合复审报告](../reports/TASK_01_07_AUDIT_DELIVERY.md)。


## 任务六RAG B0

先按EMBEDDING_AND_INDEX.md恢复本机原语料并准备任务五正式99段索引、两个固定Ollama模型和独立.venv。执行`.venv/Scripts/python.exe scripts/query_rag_b0.py --check`后，用`powershell -NoProfile -ExecutionPolicy Bypass -File frontend/start_rag_b0.ps1`启动7863。若已在运行直接访问，不重复占用端口。

当前代码不需要新增包或付费Key；公开仓库不包含完整语料、模型和索引，不能仅克隆就假定这些本机输入存在。完整运行、日志、拒答/重试和验收说明见RAG_B0.md。

## 任务八BM25离线实验

任务八最新补充见 [TASK_08_SUPPLEMENT](../reports/TASK_08_SUPPLEMENT.md)。来源时间与授权、分词对照复算、测试预约、失败证据和完整索引恢复门禁已修复；原测试成绩和所有历史结果保留。分词开发可使用不同输出目录重复执行，会创建独立的私有索引；原索引不会被覆盖。

原语料恢复后执行 `.venv/Scripts/python.exe scripts/install_bm25_runtime.py`，再按 [BM25_RETRIEVAL](BM25_RETRIEVAL.md) 构建三个本地索引。jieba从固定官方包隔离安装到.runtime/bm25，原应用262包保持不变，BM25实验不需要Ollama。已有目录/原正式测试拒绝覆盖或重复运行；使用新dev路径。公开结果复算可用python -S，无需语料、jieba或实际索引。现有UI仍沿用原Dense入口，任务九混合检索使用独立脚本。

## 任务九混合召回与RRF

任务九修复补充在[TASK_09_SUPPLEMENT](../reports/TASK_09_SUPPLEMENT.md)。新真实查询检查生成绑定生产提交与索引前后哈希的1.1回执；完整门禁可传`--live-report`，原回执保留并按历史源码验证。无效输出和空问题会在初始化模型前拒绝。

见[RRF_EXPERIMENT](RRF_EXPERIMENT.md)。公开克隆无需模型和语料即可执行`python -S scripts/run_hybrid_retrieval.py replay --run-dir reports/retrieval/hybrid_rrf_b0/test --output reports/rechecks/my-rrf-replay.json`核验已有结果。运行新的dev仍要求原人工审核账本；实际query须恢复原Dense/BM25索引、固定依赖与本机Ollama/BGE-M3，不调用答案模型。四方法保持相同Top10输出上限，完整并集覆盖另列；RRF在本集MRR低于BM25，不能称全面提升。


## 任务十：官方BGE-Reranker实验

复用现有262项核心依赖与原Dense/BM25索引，执行`.venv/Scripts/python.exe -B scripts/install_reranker_model.py --download`将固定约1.1GB官方ONNX与分词配置写入被忽略的.models，再用`run_reranker_experiment.py query --question "请查找球场球门的规定尺寸资料。" --method top40`。参数、CPU耗时、完整命令和公开无模型复算见[RERANKER_EXPERIMENT](RERANKER_EXPERIMENT.md)。公开仓库没有全文和权重；原测试账本已消耗，不能直接重复正式test或删除旧证据。


## 任务十缺陷补交付的复验入口

当前版本另用 `scripts/verify_task10_audit_delivery.py --complete --public-only --report reports/rechecks/task10-recheck/delivery.json`，可由系统Python以 `-S -B` 执行，无须模型或全文；保留Git历史以校验生产提交。原 `verify_reranker_delivery.py` 在原标签 `v0.10.0-bge-reranker` 使用，不能要求它把后续代码当作当时交付源码。见 [TASK_10_AUDIT](TASK_10_AUDIT.md)。新运行输出1.1诊断，旧1.0结果不改写，不重跑锁定test。
