# 任务四至六仓库审计与补交付（2026-11-12）

## 当前结论

原main f97c0df32566a62f9a2106367a048a5cd77da1f5上的205个公开文件齐全，GitHub对象/清单大小和哈希全部匹配，14/14通过。本轮发现并补齐8组代码/重验边界问题；最终任务四原门禁26/26、任务五24/24、任务六62/62及新增边界回归58/58通过。以下交付范围内的已发现缺陷已关闭。

分支fix/task-04-06-delivery-audit；原技术/执行规则保持字节不变。代码基线477784420a1f27b8e2a4b688dae548b35c22cf96，补交付通过独立PR、普通merge与新标签v0.6.1-task456-audit归档。旧v0.6.0-rag-b0保持f97c0df；仅yangyanbeen/football-rules-rag-lab允许写入。GitHub的实际合并SHA及时间以PR/标签为准。

## 1. 发现了什么、怎样补齐

修复前记录为[task456_before_fixes.json](acceptance/task456_before_fixes.json)：18个检查，前16个在模拟服务/子进程及隔离副本中实际复现，后2个来自源码依赖/判断式核对，不冒充真实线上事故。详细补交付基线见[范围文档](../docs/TASK_04_06_SUPPLEMENT_SCOPE.md)。

| 缺陷 | 修复及交付结果 |
| --- | --- |
| D456-01 索引接受重新计算哈希的无效人工回执 | DenseIndex构建/加载前要求公开回执语义一致；decision需实际批准。公开检查不代替私人原人工门禁 |
| D456-02 配置类型/范围不严 | 拒绝bool冒充整数、负预测/超时/端口、未知配置与未支持策略，核对预算；原B0配置字节未变 |
| D456-03 模型响应身份/计数不全 | 固定模型名、assistant正文、完成原因及实际正整数token计数；缺失/错误/超预算原包被拒绝 |
| D456-04 拒答夹带无引用结论 | 用户只看到固定拒答文案，模型原理由留私有trace，不直接呈现自由文本 |
| D456-05 失败trace丢失/混用 | 保留请求后模型变化的原响应，记录attempt阶段/错误/耗时；第二次失败清空本次generation，网络失败不无限重试 |
| D456-06 worker伪来源/畸形结果 | UI独立核对包结构、原文/metadata/messages/哈希、模型原响应与派生摘要、答案及引用；无效包拒答，UI不创建Chroma索引 |
| D456-07 重验绑定旧私有记录 | smoke/UI路径与授权代码基线可指定；旧trace回归改自足夹具；新UI摘要可独立生成快照，不依赖历史原型失败文件；增加公开/私有回执验证工具 |
| D456-08 合法后续版本被误报 | 原标签保持不变，验证其为新main祖先；继续核对当前全量文件树和公开清单 |

D456-06复查再补齐原响应与摘要逐字段绑定，增加3个隔离坏包样例。首轮55项结果按原字节保留，最终58项覆盖最终源代码。

## 2. 原验收与新增检查分开列示

本轮证据根目录为[rechecks/task456-20261112](rechecks/task456-20261112)。所有命令实际执行，新报告使用新路径；旧任务报告和数据未覆盖。

| 验收项 | 结果 | 机器证据（均相对于本轮根目录） |
| --- | --- | --- |
| 任务四原完整门禁/实际逐题人工状态 | 26/26；90/90 | original/acceptance/task4_delivery_gate.json |
| 公开凭证/工作流/封存 | 13/13；27/27；15/15 | original/acceptance/task4_public_receipt.json、task4_workflow_verification.json、task4_human_release_verification.json |
| 任务五原完整门禁 | 24/24；18种错误拒绝 | original/acceptance/task5_delivery_gate.json |
| 新空目录真实重编码 | 99段，55.836秒；最大向量差0.0 | 同上rebuild_timing与rebuild_directory；公开重建metadata见original/manifests |
| 前轮任务四五补缺回归 | 39/39 | original/acceptance/task45_regressions.json |
| 本轮边界回归 | 58/58 | final/acceptance/regressions.json |
| 重验工具可移植回归 | 62/62 | final/acceptance/task6_portability_regression.json；仅重放旧真实记录的夹具，不是新页面 |
| 最终任务六完整验收 | 62/62 | final/acceptance/task6_delivery_gate.json；使用本轮新smoke、真实UI与不可变journal快照 |
| 新真实后端/真实UI | 各3条可回答＋1条资料外拒答，无处理错误 | final/evidence/rag_b0_smoke.json、rag_b0_ui.json |
| 公开回执一致性 | 15/15 | final/acceptance/public_receipts.json |
| 私有完整记录/DOM/来源核对 | 20/20 | final/acceptance/private_receipts.json |

真实页面分别提交界线、球门尺寸、掷界外球及火星天气四问，核对最后回答、chunk/原URL、面板数和唯一trace ID。可回答来源分别为L01-01、L01-03、L15-02；资料外问题仅显示固定拒答。没有使用锁定评测问题选参数或计分。

58项回归使用模拟包/隔离副本，脚本自身调用真实模型0次；其可移植检查重放旧smoke/UI。新的真实模型与网页运行另列，不能把自动检查数当作准确率样本数。

## 3. 已执行的复验命令

以下在仓库根目录执行。路径已存在，复验时换新目录。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/recheck_task45.ps1 -ReportDir reports/rechecks/task456-20261112/original -OriginalRoot C:/Users/HP/Documents/Codex/football-rules-rag-project -OriginalSnapshot C:/Users/HP/Documents/Codex/2026-11-06/new-chat/.tmp/github-publication/original-project-before.json
.\.venv\Scripts\python.exe scripts/verify_task456_regressions.py --report reports/rechecks/task456-20261112/final/acceptance/regressions.json --reference-commit 477784420a1f27b8e2a4b688dae548b35c22cf96
.\.venv\Scripts\python.exe scripts/smoke_rag_b0.py --output .runtime/rag-b0/task456/final/smoke.jsonl --summary reports/rechecks/task456-20261112/final/evidence/rag_b0_smoke.json
# 浏览器在加载最终代码的7863新页面真实填入/提交四问，DOM采集到本机ui-captures.jsonl后：
.\.venv\Scripts\python.exe scripts/summarize_rag_b0_ui.py --captures .runtime/rag-b0/task456/final/ui-captures.jsonl --journal .runtime/rag-b0/ui-events.jsonl --output reports/rechecks/task456-20261112/final/evidence/rag_b0_ui.json
.\.venv\Scripts\python.exe scripts/verify_rag_b0.py --report reports/rechecks/task456-20261112/final/acceptance/task6_delivery_gate.json --smoke-file .runtime/rag-b0/task456/final/smoke.jsonl --smoke-manifest reports/rechecks/task456-20261112/final/evidence/rag_b0_smoke.json --ui-captures .runtime/rag-b0/task456/final/ui-captures.jsonl --ui-journal .runtime/rag-b0/task456/final/ui-journal-2c770abd2bfd697ca904.jsonl --reference-commit 477784420a1f27b8e2a4b688dae548b35c22cf96
.\.venv\Scripts\python.exe scripts/validate_rag_b0_receipts.py --smoke-manifest reports/rechecks/task456-20261112/final/evidence/rag_b0_smoke.json --ui-manifest reports/rechecks/task456-20261112/final/evidence/rag_b0_ui.json --report reports/rechecks/task456-20261112/final/acceptance/public_receipts.json
.\.venv\Scripts\python.exe scripts/validate_rag_b0_receipts.py --smoke-manifest reports/rechecks/task456-20261112/final/evidence/rag_b0_smoke.json --ui-manifest reports/rechecks/task456-20261112/final/evidence/rag_b0_ui.json --private --report reports/rechecks/task456-20261112/final/acceptance/private_receipts.json
```

verify_rag_b0原默认代码基线为任务六起点0f6abdcc，本轮显式使用获授权的4777844，原因是DenseIndex入口已修复。原冻结10文件/4前缀、61语料、原索引固定哈希、真实人工日志与原工程178静态文件仍分别检查；该参数不能把数据改动“重签”为通过。原validate_eval_dataset.py未改。

## 4. 交付保全与公开复核范围

- 原任务四评测问题/标签、90题真实人工日志、锁定时间，任务五正式索引全部文件及原公开producer manifest不变；本轮只做验证，不新建人工审批。
- 原五份中文文档及61个本地数据文件不变；原工程178静态文件不变且未初始化根Git。原技术/执行文档逐字节保留，四份历史文档只追加允许内容。
- 完整问答、DOM、worker响应、向量/数据库和账号继续留忽略目录；公开回执只含哈希、ID、计数、来源等元数据。原reports/rag_b0_smoke.jsonl和旧UI快照不覆盖；新的journal snapshot固定本轮字节，live journal以后可追加。
- 当前维护的README、RAG_B0、EMBEDDING_AND_INDEX、状态/实验索引按本轮事实更新。旧任务四五六交付报告保留，不把维护文档的更新当作冻结数据变更。
- 发布前运行manage_delivery_manifest.py及--verify、原文件/凭证排除检查；合并后使用audit_remote_delivery.py --expected-commit <实际合并SHA> --require-supplement --require-task6逐文件核对。该远程检查只读，不写仓库。
- 其他已有仓库仅只读核对；desktop-tutorial/main应保持8e7bafebe26caa0dbcb64d729766513d485c73bb。真实发布结果由GitHub PR和标签查证。

## 5. 能力边界

以上证明本轮运行、输入/输出合同、来源和版本保全，不证明自然语言结论都被证据蕴含。当前仍为固定Dense Top5、最多1个完整生成证据块，跨块问题和误拒答需后续正式评测；Wikipedia AI整理、非官方版本/未专家审校的边界不变。

本轮没有正式Recall、MRR、nDCG、答案准确率、P95/QPS或性能提升数字。原任务七至十四继续按冻结计划推进，不能把本次修复当作它们完成。
