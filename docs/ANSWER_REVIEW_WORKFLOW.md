# 任务十二补充：真实人工复核与当前复验入口

本说明补充原 ANSWER_EVALUATION.md，不改原方法、模型、标签或正式测试结果。

## 人工审核

在仓库目录运行：

```powershell
.venv/Scripts/python.exe -B scripts/serve_answer_review_v2.py --port 7865
```

打开 http://127.0.0.1:7865/ 。固定12题采用原错误优先抽样，不是全50题的随机代表。逐题查看实际回答、标签支持段和当时提供给模型的全文，核对条件/例外、否定、单位、规则编号以及引用能否回答所问。

- “是”：该项正确；“否”：该项错误或遗漏；“无法判定”：仍需查证。
- 错误拒答没有覆盖任何答案要点，其要点和条件应判“否”。不能因拒答语句流畅判覆盖。
- 填写真实审阅者与理由，点击“提交本题人工判断”。没有默认选项，也没有全部通过按钮。
- 原始记录仅保留本机 `.runtime/task12/human_answer_reviews.jsonl`；修订只追加，按题取最后一份有效记录，提交次数不算样本数。
- 新入口验证样本、标签、答案SHA、原响应SHA及语料文件；材料改变或旧表单失效会拒收。未知字段、缺失判断、重复字段及破损账本均拒收。

审核完成是12题均有明确判断；可以全部或部分判错。`uncertain` 不会被算成通过，也不会移出指标分母。完成审核不代表12个答案都正确，更不代表裁判专家认证或整体50题准确率。

## 导出和验收

```powershell
.venv/Scripts/python.exe -B scripts/answer_review_v2.py --report reports/answer_evaluation_audit/human-review-status-next.json --require-complete
```

输出路径必须未存在，保留每次快照。未完成时状态 `PENDING`，要求完整审核时返回非零退出码；不会把 AI 判定、旧90题标签批准或负责人笼统同意当作本次逐题判断。脱敏导出包含逐项决定、分子分母、未定项和原私有账本哈希，不含审阅者姓名、备注或规则全文。

本轮保存的快照是 `human-review-status.json`。之后若完成真实审核，新增带后缀的快照，并以新PR追加当前状态和证据；历史快照保持原字节。审阅样本的分数只能描述该12题，不能扩写为全测试集成绩。

## 工程复验

```powershell
.venv/Scripts/python.exe -B scripts/verify_answer_audit.py --private --report .runtime/task12-audit/recheck-new.json
.venv/Scripts/python.exe -B scripts/verify_answer_audit_public.py --report .runtime/task12-audit/public-new.json
.venv/Scripts/python.exe -B scripts/verify_answer_audit_delivery.py --report .runtime/task12-audit/delivery-new.json --require-complete
```

路径同样不能重复使用。公开副本仅使用标准库和Git，以 Python `-S` 运行，不需要本机语料、模型、索引或评分服务。补充交付门禁分别输出工程状态和 `task12_fully_accepted`；人工尚未完成时，即使工程 `PASS`，完整验收仍为false，严格模式返回非零。

原脚本为冻结实验的生产代码，保留以供历史复算。旧 `verify_answer_release.py` 是创建第21个标签前的门禁；原完整门禁规定累计21项实验。补丁阶段用新增补交付入口，不通过篡改历史数量和历史PASS回执维持表面通过。

本轮没有修改回答算法、用测试题调参或重新跑测试。原AI引用22/71、要点40/100等低分仍然有效；本轮修复提升证据与审核可靠性，不声称提高了模型答案质量。
