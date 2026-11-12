# 独立环境与新 UI 三问复核

初次独立安装日期：2026-11-11。此补充流程不改变原任务一至三要求。初次结果是 reports/acceptance/fresh_delivery.json，旧环境和历史 UI 回执保留原日期。2026-11-12综合复审见 [TASK_01_07_AUDIT_DELIVERY](../reports/TASK_01_07_AUDIT_DELIVERY.md)。

## 已实际完成

1. 新目录重新建立 Python/虚拟环境，原锁导出 260 核心依赖、两项固定源码包，262 项位置均在新目录。固定上游源码未修改。
2. 新空数据库创建 admin，再从浏览器创建普通账号 yanyanbeen，退出 admin 后上传五份 MD；所有权和字节哈希通过，50 个临时块，不是正式 RAG B0。
3. 普通账号在 7861 页面实际提交 Q1–Q3；回答、信息面板完整证据段和链接与同次管线记录逐项一致。
4. 统一新复核入口实际退出 0：综合 33/33（含原工程保全两项），开发回归 16/16、引用契约 19/19；任务三原校验 18/18、suite 8/8、坏数据拒绝 16/16。

## 如何重新采集浏览器证据

按 PUBLIC_SETUP 启动服务，普通账号登录并已有五份资料。在 Chat 新建空会话，选 Search All、关闭 Mindmap。不要通过后端 API 代替点击/输入。

打开浏览器开发者工具 Console，粘贴 scripts/capture_fresh_ui.js 的完整代码一次。脚本只读取问答和来源面板，不读取账号、密码或存储，也不提交问题。

按顺序在聊天框输入问题。每问等待完整回答和来源面板出现后，分别在 Console 执行采集命令，十分钟内采集以关联本次管线时间。

| ID | 界面实际输入的问题 | 完成后采集 |
| --- | --- | --- |
| Q1 | 越位位置本身是否就是越位犯规？裁判还需要判断哪些参与比赛的行为？请给出规则来源。 | `captureFootballQuestion('Q1')` |
| Q2 | 哪些行为可以判直接任意球？请从规则资料中列举三项，并分别给出引用。 | `captureFootballQuestion('Q2')` |
| Q3 | 球门球开出后，球在什么条件下才算进入比赛？请说明触球或进球相关条件，并给出引用。 | `captureFootballQuestion('Q3')` |

执行 `saveFootballCapture()`，将下载的 ui-three-dom.json 放到本仓库 .runtime/，全文不提交 Git。每次重新粘贴会清空本次采集数组；重新验收需新建空会话并从 Q1 开始。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/recheck_fresh_delivery.ps1 -UiCapture .runtime/ui-three-dom.json -AppUrl http://127.0.0.1:7861/ -StderrLog .runtime/my-run/app.stderr.log
```

本机本轮原始采集是 .runtime/fresh-runtime-20261111/ui-three-dom.json，不是公开下载文件。可直接用这个路径重验已有证据。重验不会冒充“又提交了一次三问”。可另加 `-OriginalRoot <原工程目录> -OriginalSnapshot <变更前静态哈希JSON>` 复查原工程保全；须是变更前真实记录，不能临时补造。

## 机器检查与证据

检查解释器/包位置、260 个锁定版本、干净上游、真实 tokenizer 资源、10 个冻结文件、4 个历史前缀、61 个本地语料、普通角色/所有权/上传哈希/50 块、私有集合、仅 Ollama 模型池、新 UI/同次事件/来源段/URL、16 开发题/19 契约、原任务三 suite、HTTP 和模型 digest。公开回执只含结果、时间、摘要和哈希；完整 DOM/回答留本机。

初次 UI 发现空重排模型池错误；本地检索工厂现不实例化未使用的重排器，仍复用上游检索和所选文件范围，不宣称实现重排优化。初次检查器误读 relation.user；现按 Source 所有权关联计数，失败回执留本机。

本轮启动仍有 Chroma 候选容量提示（请求 100，实际 50，自动收敛）；没有远程 tokenizer 重试、未安装图依赖错误或应用 traceback。首次安装的网络/缓存失败也保留本机，不删除失败历史。

任务一至七已交付，任务八至十四继续按原计划。专家审校、历史正文独立回取及正式答案质量评测仍未完成，不用开发题通过数代替这些工作。

## 重验保护

每次创建新的报告目录；可用 -ReportDir 指定，已有目录直接拒绝。子工具的 --report/--output 也拒绝覆盖旧回执。UI按问题、十分钟时窗和完整可见回答匹配唯一日志；后续同题交互不会使历史回执失效，附加或删减回答会被拒绝。当前只规范化本项目渲染器实际输出的链接、粗体、引用前缀、HTML实体和排版空白。

19项引用检查绑定实际开发回归文件SHA；任务三回执须包含18项校验、8项suite及16个坏例全部通过。日志、依赖报告、原始采集的SHA随新回执保存；HTTP检查只证明检查时服务响应，不冒充新UI三问。
