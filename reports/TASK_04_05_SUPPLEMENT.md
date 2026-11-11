# 任务四、五仓库审计与缺陷补交付

日期：2026-11-11。审计起点为已发布main：`3e41191c145da963fb24057bb1b39354287ebc5a`，分支`fix/task-04-05-delivery-audit`。**6组问题均已在隔离环境复现、修复并回归通过。原任务四/五交付数据和旧证据不覆盖，原技术/任务标准不变。**

## 1. GitHub上传核对

原任务四PR #8与任务五PR #9均已合并，原版本标签v0.4.1-human-reviewed和v0.5.0-dense有效。GitHub仓库ID为1453703558、所有者ID为328912604，公开仓库yangyanbeen/football-rules-rag-lab。

修复前读取GitHub完整文件树，157份公开文件与本地对应Git提交逐文件匹配，公开清单列出的字节数/SHA-256全部吻合；任务四、五规定交付物无缺失，未上传索引、模型、全文或账号目录。远程检查12/12通过，见`rechecks/task45-20261111/evidence/github_before.json`。这证明原上传完整，不代表代码没有边界问题。

新增可重复的只读工具`audit_remote_delivery.py`，只调用GET和本地Git读取。补交付合并后再次核对远程main全树及新增文件，运行结果留本机，避免为更新检查时间循环改写已发布报告。

## 2. 发现与关闭的6组问题

| 编号 | 修复前真实复现 | 修复及交付 | 回归 |
| --- | --- | --- | --- |
| D45-01 | 隔离副本缺human_review_receipt.json时，原人工日志门禁仍26/26；重复冻结返回Already locked，没有发现公开凭证缺失 | 保持原人工验证器不变，新增公开凭证13项独立校验；冻结工具在幂等及新封存路径都要求凭证有效；增加公开克隆可运行入口 | 缺凭证拒绝且不写数据；11种重签哈希后语义错误被拒绝；无语料/日志/模型的公开副本13/13通过 |
| D45-02 | 同一路径打开两个DenseIndex，关闭第二个后，首个仍可查询，但再关闭首个抛KeyError | 按路径引用计数、锁定引用管理，最后一个实例才停止系统；关闭幂等，关闭后查询明确拒绝 | 交错关闭、重复关闭、存活实例查询、已关闭实例拒绝通过 |
| D45-03 | get_collection失败后，创建的Chroma系统仍留缓存 | 创建/打开集合失败时释放本次引用；不停止该路径的其他存活实例 | 独占失败无缓存泄漏、共享失败不影响已有实例通过 |
| D45-04 | 模拟的TopK不足、重复ID及错误有限距离可被当作正常结果返回 | 校验查询批次数、TopK长度、字段对齐、唯一ID及原metadata；用保存的归一化向量复核余弦距离；外部Embedding实例须同配置 | 残缺、重复、错位、缺字段、错误距离、未固定Embedding均被拒绝 |
| D45-05 | 配置声明了未支持的api/query_template，加载器仍接受，而实现忽略它们 | 明确拒绝不支持的API/查询模板；num_gpu与expected_records要求严格整数 | 4类配置错误拒绝通过 |
| D45-06 | safe_output允许把新索引放进已有索引内部，实际构建可能使父索引制品清单失效 | 在任何写入前拒绝祖先目录已含索引manifest或embeddings.npy的嵌套路径 | 无写入的嵌套路径拒绝、原索引全部文件哈希不变通过 |

修复前6/6复现证据：`acceptance/task45_before_fixes.json`。其中共享客户端问题的实际表现是关闭清理报错，未把当时仍能工作的查询描述为失败。所有破坏性测试仅在忽略的.tmp副本；没有改真实人工日志或原知识库数据。

## 3. 完整重验结果

新报告统一位于`reports/rechecks/task45-20261111/`。

| 检查 | 实际结果 | 文件 |
| --- | --- | --- |
| 任务四原人工交付门禁 | PASS26/26，人工90/90 | acceptance/task4_delivery_gate.json |
| 公开人工凭证一致性 | PASS_PUBLIC_RECEIPT13/13 | acceptance/task4_public_receipt.json |
| 任务四自动工作流 | PASS27/27，16种坏数据拒绝 | acceptance/task4_workflow_verification.json |
| 任务四封存检查 | PASS15/15 | acceptance/task4_human_release_verification.json |
| 任务五完整验收 | PASS24/24，18种错误拒绝；再次真实编码99段并从空目录重建，最大向量差0.0 | acceptance/task5_delivery_gate.json |
| 6组缺陷回归 | PASS39/39 | acceptance/task45_regressions_final.json；首轮结果另保留 |
| 原GitHub交付快照 | PASS12/12，157份公开文件无缺失/哈希错误 | evidence/github_before.json |

最终保全核对的61份旧评测/交付证据、任务四数据及公开索引元数据逐字节不变；reports/README、实验汇总CSV和简历证据索引是随交付维护的入口，不计入此不可变集合。首轮回归在更新入口文档前另记录64份一致，保留当时结果。原任务四验证器源码不变；原正式索引全部文件和完整私有人工日志不增不删。原10个冻结文件、4个历史前缀、61份本机语料和178份原工程静态文件通过任务五保全检查，原工程仍无根Git。

任务五旧manifest记录的是当时的构建代码；本次更新读取/生命周期检查，新目录重建记录新代码哈希。旧制品的producer哈希与当前reader哈希不必相同，两者在各自带日期的证据中明确保留，不能拿旧生成时间冒充新代码构建。

## 4. 公开可核验与本机完整验收的区别

只克隆公开仓库，可执行以下命令校验公开问题、凭证、版本、数量、哈希、逐题绑定、时间和隐私字段，不需要模型、原规则全文或人工日志：

```powershell
python scripts/validate_eval_receipt.py
```

PASS_PUBLIC_RECEIPT仅证明公开元数据相互一致，不能独立证明私人真实阅读，也不是官方或裁判专家认证。原完整验收仍要求真实私有日志四项核对、当前题目哈希和封存日志哈希；不以公开凭证替代原人工要求，不生成任何真实人工通过。

## 5. 重验与GitHub复核

本机已有语料、固定模型服务与虚拟环境时：

```powershell
# 默认创建带时间的新报告目录，不覆盖旧交付证据；包含一轮真实99段重新编码：
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/recheck_task45.ps1
# 需要同时复核原工程时，补上已有真实快照路径：
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/recheck_task45.ps1 -OriginalRoot <原工程目录> -OriginalSnapshot <变更前快照JSON>
# 只读检查GitHub当前main，包括本次新增交付：
.\.venv\Scripts\python.exe scripts/audit_remote_delivery.py --require-supplement --report .runtime/task45/github-current.json
```

不带原工程补充参数时，任务五核心22项；本次实际带参数为24项。所有原报告继续作为当时记录；当前补缺结论以本报告和新目录证据为准。无锁定测试调参、正式检索/LLM计分或新性能收益；任务六未在本次执行。
