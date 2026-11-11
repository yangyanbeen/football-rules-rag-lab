# 本机安装与启动说明

本文包括 2026-11-10 在本机已执行的步骤和从新环境复现的方法。项目目录假设为 `C:\Users\HP\Documents\Codex\football-rules-rag-project`。

## 已通过的本机配置

| 组件 | 本机值 |
| --- | --- |
| OS / Python | Windows / 项目隔离 Python 3.10.22 (`.venv`) |
| Kotaemon | v0.12.0，commit `9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9` |
| 依赖 | 固定 checkout 的 `uv.lock` |
| Ollama | 0.40.16 |
| 聊天模型 | Ollama `qwen2.5:3b` |
| Embedding | Ollama `bge-m3` |
| 向量存储 | Chroma |
| 文档存储 | 运行时使用上游 `SimpleFileDocumentStore` 的 Windows 兼容覆盖层 |
| 应用地址 | `http://127.0.0.1:7860/` |
| 文档索引 | 5/5 Markdown 文件，50 个 Kotaemon 临时 chunk |

任务二的三条原始问题、回答和回答/引用问题见 `docs/KOTAEMON_BASELINE.md`。没有正式检索或答案准确率指标。

## 从新环境准备

1. 安装 Git、Python 3.10.22 和 Astral `uv`。确认 `git --version`、`python --version`、`uv --version` 可用。
2. 在项目根目录取得固定上游并核对 commit：

   ```powershell
   git clone --branch v0.12.0 --depth 1 https://github.com/Cinnamon/kotaemon.git third_party/kotaemon-v0.12.0
   git -C third_party/kotaemon-v0.12.0 rev-parse HEAD
   ```

   输出必须是 `9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9`。

3. 从项目根目录让 `uv` 使用固定 checkout 的锁文件，并把隔离环境放在项目根目录：

   ```powershell
   $env:UV_PROJECT_ENVIRONMENT = (Join-Path (Get-Location) '.venv')
   uv sync --locked --project .\third_party\kotaemon-v0.12.0
   .\.venv\Scripts\python.exe --version
   ```

   Python 应为 3.10.x。`uv sync` 需要访问依赖源；如失败，保留完整终端错误，不要改用未锁定依赖。

4. 安装并启动 Ollama 服务，然后确保 `qwen2.5:3b` 和 `bge-m3` 两个模型已下载。首次下载需要可用网络和足够磁盘空间。模型名、服务地址等设置在 Kotaemon 的本机 Settings 中；不要把密钥或个人 API token 写入项目文档、日志或截图。

## 启动应用

在项目根目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_baseline_check.ps1
```

脚本会核对固定 commit 和项目 `.venv`，然后调用 `scripts/run_kotaemon_local.py`。它不直接运行上游默认入口，因为该 Windows 环境下默认 LanceDB 文档存储初始化失败。兼容层只替换文档存储实现为上游 `SimpleFileDocumentStore`；Chroma 向量存储保持不变。新机器应先重新验证该存储行为。

如只想检查固定 commit、Python 和运行依赖而不启动第二个服务，可运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_baseline_check.ps1 -CheckOnly
```

本次该检查通过，日志为 `reports/kotaemon-baseline-20261110-222605.log`。

第一次配置时登录应用并在模型/Embedding 设置中选择 Ollama、`qwen2.5:3b` 与 `bge-m3`，按本机页面确认保存。此次环境使用的模型配置及检索参数记录在 `docs/KOTAEMON_BASELINE.md`。不要将本地模型配置数据库、文档索引或用户数据提交到公共仓库。

## 复跑 UI 冒烟

应用打开后，以 Search All 搜索范围上传以下五份已有 Markdown：

```text
data/processed/wikipedia_zh_2026-11-10/01_场地器材与队员.md
data/processed/wikipedia_zh_2026-11-10/02_裁判比赛流程与结果.md
data/processed/wikipedia_zh_2026-11-10/03_越位犯规与纪律.md
data/processed/wikipedia_zh_2026-11-10/04_任意球与罚球点球.md
data/processed/wikipedia_zh_2026-11-10/05_界外球球门球与角球.md
```

等待索引结束，再依次提交 `docs/KOTAEMON_BASELINE.md` 中 Q1–Q3。将应用回答和来源面板逐字记录；不要润色失败答案。回答显示但没有证据、来源与答案不匹配，都应如实标失败。应用自动生成的 50 个 chunk 是 UI 冒烟数据，不是任务三要求的 99 条稳定 ID 导入。

## 停止服务和检查日志

- 在启动应用的 PowerShell 窗口按 `Ctrl+C` 停止 Kotaemon。
- 如果 Ollama 是本次单独启动的服务，再在其终端停止服务。
- 启动记录写入 `reports/kotaemon-baseline-<时间戳>.log`；模型和索引相关的本轮历史记录见 `reports/` 下以 `task2-`、`kotaemon-app-` 开头的文件。
- 忽略规则排除了 `.venv/`、模型缓存、上游 checkout、应用数据库和索引数据；清理这些本地状态会导致重装或重新索引。

## 已知问题

- 本机默认 LanceDB 文档存储初始化遇到 Windows OS error 5；使用本项目兼容启动器后成功索引。错误与解决路径见 `docs/KOTAEMON_BASELINE.md`。
- 三条冒烟回答都出现引用错位或内容质量问题，不能当作正确规则解释。接下来的稳定 chunk 导入、评测集、检索链路和引用校验任务仍需完成。
- Ollama 首次拉取模型与依赖安装需要网络。若 GitHub/模型源不可达，按错误日志排查网络，不要切换到浮动上游版本。
- 早期环境检查日志反映的是安装前状态，不能代表当前 `.venv` 和模型已经存在；当前运行结果以任务二索引日志、版本核验和本基线记录为准。


## 任务二交付补充：本机工具与模型配置命令（2026-11-10）

本机隔离工具已位于 `.runtime/uv/uv.exe` 和 `.runtime/ollama/ollama.exe`，模型缓存为 `.models/ollama`。以下是本机复现/维护命令；已有服务时复用现有服务。补验阶段执行的是版本查询、`-CheckOnly`、只读数据库查询和浏览器 HTTP 检查，没有重新安装依赖或重新下载模型。

在项目根目录，隔离环境已存在时可直接启动。重建环境时使用固定源码锁文件并指定 Python：

```powershell
$taskProjectRoot = (Get-Location).Path
$env:UV_PROJECT_ENVIRONMENT = Join-Path $taskProjectRoot '.venv'
& .\.runtime\uv\uv.exe sync --locked --python 3.10.22 --project .\third_party\kotaemon-v0.12.0
```

需要单独启动 Ollama 时，在一个终端运行：

```powershell
$taskProjectRoot = (Get-Location).Path
$env:OLLAMA_MODELS = Join-Path $taskProjectRoot '.models\ollama'
$env:OLLAMA_HOST = '127.0.0.1:11434'
& .\.runtime\ollama\ollama.exe serve
```

在另一个终端检查/准备本地模型（已有两模型时只运行 list）：

```powershell
$env:OLLAMA_HOST = '127.0.0.1:11434'
& .\.runtime\ollama\ollama.exe list
& .\.runtime\ollama\ollama.exe pull qwen2.5:3b
& .\.runtime\ollama\ollama.exe pull bge-m3
```

当前模型名称和 digest 见 `reports/task2-model-runtime-2026-11-10.json`；重新 pull 可变标签前应核对 digest 是否发生变化。保留当前 `.models/ollama` 可复用本次模型文件。

应用模型管理中名为 `ollama` 的实际配置为：

| 项目 | 聊天模型 | Embedding |
| --- | --- | --- |
| 适配类 | `kotaemon.llms.ChatOpenAI` | `kotaemon.embeddings.OpenAIEmbeddings` |
| base_url | `http://127.0.0.1:11434/v1/` | `http://127.0.0.1:11434/v1/` |
| model | `qwen2.5:3b` | `bge-m3` |
| 设为默认 | 是 | 是 |

如页面要求 api_key 字段，本地 Ollama 兼容接口可使用本地占位文本；不要填入付费服务密钥。配置保存在被忽略的本机应用数据库中，公开文档只保留上述非敏感字段。

随后运行原启动命令；只核对环境时加 `-CheckOnly`。本轮检查通过，退出码 0，日志 `reports/kotaemon-baseline-20261110-232421.log`。原始三问和浏览器在线证据见 `reports/task2-ui-evidence-2026-11-10.json`；完整补验命令为 `.\.venv\Scripts\python.exe scripts/audit_task1_task2.py`。


## 任务一二再次交付：实际重启修复与完整步骤（2026-11-11）

本节补充今日按启动脚本重启时实际发现并修复的条件；前文保留为历史记录。原技术设计、任务交付标准、五份 Markdown 和两份 JSONL 保持原字节。

### 今日启动失败与修复

| 实际问题 | 修复及证据 |
| --- | --- |
| 环境继承 `ALL_PROXY` 的 SOCKS 配置，锁定依赖未包含 socksio，Gradio/httpx 实际导入失败 | `scripts/kotaemon_runtime_env.py` 在当前 Python 进程中跳过依赖不支持的 SOCKS 代理变量，并为本机地址补充 NO_PROXY；保留可用的 HTTP 代理。只记录变量名，不记录代理值，不修改系统设置。失败日志 `reports/kotaemon-startup-2026-11-11.log`。 |
| 之前的 tokenizer 缓存环境变量未持久化，新进程尝试远程下载 cl100k_base，网络失败 | 启动器定位并验证项目或锁定依赖附带的缓存，再设置当前进程的 TIKTOKEN_CACHE_DIR。固定 SHA-256 为 `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`。失败日志 `reports/kotaemon-startup-fixed-2026-11-11.log`。 |
| 仅检查模块是否存在，不能证明实际可导入 | `scripts/check_kotaemon_runtime.py` 改为真实导入 kotaemon、ktem、chromadb、gradio，失败则退出非零；随后再由同一套环境规则运行应用。 |

`scripts/run_baseline_check.ps1 -InstallDependencies` 现可使用 PATH 中的 uv 或本机 `.runtime/uv/uv.exe`，指定 Python 3.10.22，仍只使用固定源码的 `uv.lock`。已安装的当前环境不需要重复安装。

### 启动前资源准备

在项目根目录执行；第一次准备缺失资源时需要网络，已有有效文件会复用：

```powershell
.\.venv\Scripts\python.exe scripts/prepare_kotaemon_assets.py
.\.venv\Scripts\python.exe scripts/prepare_kotaemon_assets.py --verify-only
```

资源包括 tiktoken 的 cl100k_base 文件，以及 NLTK stopwords、punkt_tab 的英文处理文件。脚本优先复用并校验本地 tiktoken 缓存；仅缺失时访问其原始下载源，下载内容必须符合固定哈希。NLTK 文件保存在项目隔离环境下的依赖缓存中。`--verify-only` 不下载、不写入；今日实测 PASS。缓存和模型不纳入公开交付目录。

### 今日实际启动命令

先按前文命令在一个终端启动本地 Ollama，并用本机 list 命令确认两模型存在。在另一个项目终端启动应用：

```powershell
$env:PYTHONUNBUFFERED = '1'
$env:GRADIO_ANALYTICS_ENABLED = 'false'
$env:GRADIO_SERVER_NAME = '127.0.0.1'
$env:GRADIO_SERVER_PORT = '7860'
$env:KH_GRADIO_SHARE = 'false'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_baseline_check.ps1
```

今天实际使用上述环境和启动脚本，应用进入 `Running on local URL: http://127.0.0.1:7860`。成功日志为 `reports/kotaemon-startup-cached-2026-11-11.log`，同次 PowerShell transcript 为 `reports/kotaemon-baseline-20261111-124053.log`。Ollama 日志为 `reports/ollama-server-2026-11-11.log`。本机首次服务启动如因沙箱不能创建用户配置失败，需要在允许访问本机用户配置的普通终端启动；不要导出 Ollama 私钥。

根目录 `.env.example` 是非敏感配置示例，启动器不会自动加载它；上面 PowerShell 变量才是本次实际传入的值。本地 Ollama 调用不需要真实付费 API 密钥。停止方法仍是两个服务所在终端分别 `Ctrl+C`。

### 页面中必须确认的选项

1. 进入 Chat，显式点击一次 Search All，使当前用户的已导入五份文档成为检索范围。当前索引已存在，不要重复上传；新环境才需要按前文上传。
2. 打开 Chat settings，在当前会话把 Language 选为 Chinese、LLM 选为 ollama，分别确认选择。全局语言设置不一定覆盖已打开会话，本次曾发现会话仍为 English，因此重新选择后才采集最终三问。
3. Citation 选 highlight，Reasoning 选 simple。提交原 Q1—Q3，等待生成结束；核对每题有回答和 Information panel。
4. 原始回答、逐题来源面板和会话选项均保存于 `reports/task2-ui-evidence-2026-11-11.json`。该 JSON 同时保留早期探测页面原文，最终 qa 数组明确只选中文设置后的三条回答。

### 尚存在但未阻止本次运行的警告

上游仍可能输出 NLTK 旧 punkt 检查、可选 HuggingFace/Mistral tokenizer 下载失败后使用 dummy tokenizer、GraphRAG/LightRAG 未安装、远程 changelog 请求失败等警告。实际使用的 cl100k_base、stopwords、punkt_tab 已校验，应用、三问和来源面板均完成。本次不声称所有可选功能可用；若另一个环境不能启动，应保存当次错误重新定位，不能以本次历史 PASS 替代实际检查。


## 回答与引用质量修复启动配置（2026-11-11）

当前启动器默认启用 `evidence-guard-v1`，替换 simple 的问答行为；上游源码不变。仍按前文启动 Ollama 和 run_baseline_check.ps1，页面选 Search All、ollama、Chinese，关闭 Mindmap。配置为 `config/answer_quality.json`；聊天经 native Ollama /api/chat 显式传入 num_ctx=16384，模型只选稳定 ID，原文和 URL 由程序输出。引用面板与答案使用同一批 metadata，不再依赖独立 CitationPipeline 工具调用。

具体流程、逐题结果和限制见 `docs/ANSWER_QUALITY_FIX.md`。新回归命令 `.\.venv\Scripts\python.exe scripts/run_answer_quality_regression.py --output reports/answer-quality-regression-rerun.json`；只读契约复核 `.\.venv\Scripts\python.exe scripts/verify_answer_quality.py`。

可选环境变量 `FOOTBALL_QUALITY_GUARD=1` 默认启用；仅作历史对照时在重启前设为 0，重启前恢复 1 则重新启用。`.env.example` 是示例，不自动加载。已运行的进程不会随环境变量修改自动切换，需按 Ctrl+C 后重启。

实际启动日志 `reports/kotaemon-quality-fix-2026-11-11.log`，transcript `reports/kotaemon-baseline-20261111-134128.log`。原五份文档、50 个临时应用块和 99 稳定单元都保留；本轮的稳定单元向量保存在被忽略的 `.cache/football-quality/`，不是任务五的正式索引交付。前文混合检索/Top-K10 是上游粗文件检索的历史与当前基础配置，新证据层另有候选预算；不得混淆为同一阶段参数。


本轮最终签收启动日志为 `reports/kotaemon-quality-fix-final-2026-11-11.log`，transcript `reports/kotaemon-baseline-20261111-135518.log`；最后一版代码启动后重新完成原三问。原任务一二在线复核32/32通过，详见 `reports/task1_task2_after-quality-fix-2026-11-11.json`。


## 本机账号与任务三数据入口（2026-11-11）

本机普通账号yanyanbeen已创建并验证登录。登录地址不变 http://127.0.0.1:7860/，密码在被忽略的 `.runtime/kotaemon-account.json` 中查看；操作见 `docs/LOCAL_ACCOUNT.md`。原admin及其文档、模型配置和索引未移动、未重设权限。

任务三已将原99稳定知识段适配为新JSONL：`data/processed/rag_chunks_zh.jsonl` 和 `rag_chunks_parallel.jsonl`。构建命令 `.\.venv\Scripts\python.exe scripts/build_rag_dataset.py`，校验命令 `.\.venv\Scripts\python.exe scripts/validate_rag_dataset.py`，交付复核 `.\.venv\Scripts\python.exe scripts/verify_task3_delivery.py`。这是本地数据适配，不上传或重切分应用文件；正式索引导入留在原后续任务。完整字段与版本规则见 RAG_DATA_SCHEMA。
