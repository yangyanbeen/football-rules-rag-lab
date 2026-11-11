# 任务六交付报告：端到端 RAG B0

完成日期：2026-11-12（2026-11-11开始）。**原任务六已完成：交付检查62/62通过，后端smoke与真实浏览器分别完成3条可回答+1条资料外拒答。** 这证明运行与可追溯链路，不是正式答案准确率或整个14项项目全部完成。

## 1. 原交付标准逐项核对

依据未改动的DEVELOPMENT_PLAN_AND_REPORT.md任务六与TECHNICAL_DESIGN.md。

| 原要求/通过条件 | 当前交付 | 实际依据 |
| --- | --- | --- |
| 固定上游、统一语料、正式Dense索引和LLM配置 | 固定Kotaemon v0.12.0、99段任务五正式索引、精确本机模型digest | config/rag_b0.json、docs/RAG_B0.md；原索引/语料哈希检查 |
| 查询规范化、Top-K及证据组装 | NFKC/空白规范化，Dense Top5；B0生成最多用1个预算内完整块 | 实际Top5与context分开记录，精确messages及字节预算可复核 |
| LLM生成、提示词、来源引用 | Qwen2.5:3b生成中文；程序绑定唯一提供的完整块并恢复原URL/chunk/规则号/行号 | 三条实际LLM原响应及原引用metadata |
| 证据不足时拒答 | 资料外问题实际检索/生成后拒答；官方版本未核验、服务失败或无效响应也拒答 | 实际资料外smoke、版本边界及故障契约检查 |
| 能启动的完整RAG链路 | 独立Kotaemon App/ChatPage，127.0.0.1:7863；前端适配器调用独立问答进程 | 真实页面填入问题并提交，DOM/最后回答/证据面板与trace ID一致 |
| docs/RAG_B0.md | 模型、Top-K、提示词、上下文、存储、引用、运行和限制均已说明 | 文档及frontend/start_rag_b0.ps1、CLI检查/查询入口 |
| reports/rag_b0_smoke.jsonl至少3+1 | 规定本机路径共4条完整输入/Top5/context/模型原响应/答案/引用/耗时 | 原始SHA见rag_b0_smoke_manifest.json，完整记录依原忽略规则留本机 |
| 检索证据与生成答案可区分，每个回答可回溯 | 检索、实际证据、生成、程序恢复引用各自记录 | 62项检查核对正文、完整metadata、配置/提示词/索引SHA与实际输出 |
| 校核和资料边界可见 | 回答/面板显示非官方、AI整理、非专家审校；来源有校核标记、历史版本未独立核验、许可链接 | 四次真实页面采集及引用元数据 |

## 2. 版本、运行与实际样例

- 起点main：0f6abdcc2b5ef8f35b9add68e0a1c15ee56f7fff；独立分支feat/task-06-rag-b0，小步提交记录实际修复过程。
- 固定上游9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9；Python3.10.22、原锁定依赖未变。
- Embedding复用原BGE-M3制品digest及任务五索引，未重新切分、替换或覆盖正式索引。
- 生成模型qwen2.5:3b，digest357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b；Ollama0.40.16，CPU8线程、temperature0、seed42、窗口8192、输出上限1024。
- 最终提示词grounded-text-v7；模型输出ANSWER:或REFUSE:文本，应用解析并检查，不再使用早期复杂JSON生成约束。
- 查询后端无付费Key；源码配置没有个人密码或Token。

| 临时问题 | 后端/实际页面结果 | 程序恢复引用 |
| --- | --- | --- |
| 足球场的边界线属于场内还是场外？ | 可回答/可回答 | L01-01，Wikipedia Football pitch，第1条 |
| 球门两根门柱之间的距离和横梁高度各是多少？ | 可回答/可回答 | L01-03，同来源，第1条 |
| 队员掷界外球时双脚和双手应满足什么要求？ | 可回答/可回答 | L15-02，Wikipedia Throw-in，第15条 |
| 火星明天的天气怎么样？ | 拒答/拒答 | 不给确定答案或引用 |

以上是临时链路检查，不读取冻结评测题用于调参/计分。固定seed不保证每次输出逐字相同；之前已实际观察到不同回复，因此没有宣称生成结果位级复现。单次耗时/token见机器回执，只作运行记录，不当作P95、QPS或优化收益。

## 3. 真实失败、修复及保留范围

本轮没有用第一次后端通过直接签收。多轮原型和真实页面发现并保留了以下问题：

1. 有直接证据仍误拒答；澄清一般资料问答与“已核验官方规则”要求的区别。
2. 复杂JSON响应混合拒答与断言、误用段落ID、重复续写、超长或残句。最终改为简短文本生成，来源由程序绑定唯一提供的完整块；校验前缀、长度、句子完整性、重复及数值。
3. 页面曾混用其他块数值/引用并发生生成截断。保留原始事件；最终限定生成上下文为一个完整块，数值须存在于该引用块；被拒绝的中间输出不显示。
4. 完整Kotaemon导入后同进程读取Chroma/HNSW触发Windows native access violation。最终隔离问答子进程，保留固定依赖、上游、索引和旧实例。
5. 空索引UI不满足固定ChatPage的选择器事件约定。新增只读BaseIndex/选择器，实际检索仍只有任务五索引，不另建临时向量集合。

完整失败在.runtime/rag-b0/，公开10份文件的哈希和具体观察见reports/evidence/rag_b0_failures.json。前六轮smoke，包括一轮后端通过而后续页面仍发现问题的记录，均保留；最终规定路径仅对应最终配置的新一轮。没有把早期通过、失败或重试删掉后冒充一次成功。

校验失败最多额外重试一次，正常证据不足拒答不重试；每次保存原响应/消息/错误/token及耗时，最终仍无效则拒答。完整块引用和数字检查不等于语义蕴含证明；一般语义错误、条件遗漏和误拒答仍需原任务十二正式评测。单块上下文对跨块问题能力有限，不声称这是最优检索/上下文参数。

## 4. 验收与保全

**新任务六门禁62/62：**实际LLM、真实页面3+1、原证据/metadata完全一致、预算可复核、引用绑定、拒答不附断言、15类以上坏输出/错误输入、模型截断/版本、服务和子进程故障、有限重试，以及所有冻结数据保全。详细检查逐条见task6_delivery_gate.json；检查数量是本次验证项，不替换原任务条件或变成准确率。

**原任务四、五独立重验：**

| 检查 | 本次结果 |
| --- | --- |
| 原逐题人工交付门禁 | 26/26，原真实人工90/90 |
| 公开人工凭证一致性 | 13/13 |
| 工作流/封存专项 | 27/27、15/15 |
| 原任务五完整验收 | 24/24，18种错误拒绝 |
| 任务五空目录真实重建 | 重新编码99段，最大向量差0.0；正式索引不覆盖 |
| 前轮补缺回归 | 39/39 |

所有新回执位于reports/rechecks/task6-20261111/，原报告未覆盖。原10个冻结文件、4个历史前缀、61份本机语料、178份原工程静态文件、任务四评测及人工日志、任务五索引/公开清单均保持原内容。原应用启动代码未改；7860/7861/7862实例未停止或接管，原工程无根Git。

文档更新后再次62/62通过，回执为rechecks/task6-20261111/acceptance/task6_final_gate.json；只读检查7860/7861/7862/7863均HTTP200，固定模型和99段索引READY，见evidence/task6_live_runtime.json。

## 5. 交付文件和运行

- 使用说明：docs/RAG_B0.md；执行范围与原标准映射：docs/TASK_06_SCOPE.md。
- 代码/配置：scripts/rag_b0*.py、query_rag_b0.py、run_rag_b0.py、smoke_rag_b0.py、verify_rag_b0.py；config/rag_b0.json及rag_b0_system.txt。
- 后端完整smoke：本机reports/rag_b0_smoke.jsonl；公开reports/evidence/rag_b0_smoke_manifest.json。
- 真实页面：本机ui-events.jsonl、ui-captures.jsonl；公开reports/evidence/rag_b0_ui_manifest.json。
- 机器验收：reports/acceptance/task6_delivery_gate.json；失败摘要：rag_b0_failures.json。
- Git交付：feat/task-06-rag-b0分支、PR合并、v0.6.0-rag-b0标签；只向新的yangyanbeen/football-rules-rag-lab写入，既有其他仓库保持不变。合并后使用audit_remote_delivery.py --require-supplement --require-task6再次逐文件核对，回执留本机以避免自指哈希循环。

```powershell
.\.venv\Scripts\python.exe scripts/query_rag_b0.py --check
powershell -NoProfile -ExecutionPolicy Bypass -File frontend/start_rag_b0.ps1
# 已在运行则直接打开 http://127.0.0.1:7863/
```

完整语料/向量、完整模型答案、数据库和日志按既有规则保留本机；公开回执仅有状态、来源元数据、计数和哈希，不能替代阅读私有原始记录。后续任务七建立正式检索指标；任务7–14未在本轮冒充完成。无BM25/RRF/Reranker/缓存、正式Recall/MRR/nDCG、答案准确率、QPS或延迟提升数字。
