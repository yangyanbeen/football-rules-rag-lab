# 任务十三修订版：当前操作与复验

原技术/执行规则和旧交付保持原字节。当前修订入口7867，原7866仍是v0.13.0。完整补交付见[报告](../reports/TASK_13_SUPPLEMENT.md)，证据在reports/rechecks/task13-audit-20261114。

## 已在本机准备好的环境

在仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File frontend/start_integrated_rag_audit.ps1
```

打开 http://127.0.0.1:7867/ 。若已经启动，不再重复运行。Ctrl+C只关闭该启动终端的修订UI。它复用已验收的262包环境、固定模型和99段重建索引，新数据库为.runtime/task13/audit/kotaemon，工作回执/日志为.runtime/task13-audit；原7866数据库、正式账本和原索引不合并。

## 从另一份公开代码恢复

1. 获取完整Git历史，检出发布tag `v0.13.1-task13-audit`，用于核对源码生产提交。
2. 使用原[TASK_13_REPRODUCTION](TASK_13_REPRODUCTION.md)第2–6节准备固定上游、Python3.10.22、语料存档、模型、BM25/辅助资源并重建空目录索引。固定语料/模型和参数不变。公开仓库不包含规则全文和模型；必须自行准备有权使用的本机存档。
3. 安装时使用下面修订包装器，预先拒绝越界/已存在/环境内部回执路径，核对editable上游HEAD和工作树干净后才允许安装。参数沿用原安装器；默认新环境目录必须不存在，已安装环境无需重复安装。

```powershell
python -B scripts/prepare_task13_environment_checked.py --uv C:/tools/uv.exe --python C:/tools/python31022/python.exe --report reports/task13/environment-new.json
```

4. 本机固定资源齐全后，可只读运行修订工作进程预检查，再启动7867：

```powershell
.runtime/task13/venv-final/Scripts/python.exe -B scripts/query_task13_audit.py --check
powershell -ExecutionPolicy Bypass -File frontend/start_integrated_rag_audit.ps1
```

READY只在固定上游/262项实际包版本、新修订源码已提交、原模型与新索引初始化及清理检查完成后返回，不生成答案。若目录或旧索引已存在，构建器会拒绝覆盖；重建测试应使用另一个checkout和空目录，不修改当前固定config来伪造旧运行包匹配。原文档中“修改目录后重建”的做法须作为独立新版本开发，再生成对应的新证据；当前验收使用固定版本。

安装/下载命令依赖本机可信工具、实际缓存或网络，实测环境为Windows+现有已核验模型/缓存。修订包装器的非法参数与上游预检查经过回归，原新环境成功安装证据保留；本轮没有再声称重新安装一次262包或重新下载模型。

## 错误、引用和版本如何核对

- 超时、进程失败、异常输出和运行故障统一显示“本次请求未能完成”，私有failure.json保留错误和部分输出；运行故障不作为普通资料不足拒答。超时由subprocess.run结束子进程后处理。
- 模型身份等明确不可重试错误立即停止；格式错误仍允许最多一次修复，成功后的第二次响应可通过公私回执检查，不会因第一条格式失败而被误拒。
- 每份修订回答绑定实际工作进程生产commit、新修订文件SHA、固定原运行包，以及原config/语料/新索引/模型。公开回执只允许固定字段，完整回答/上下文/DOM不公开。
- 新99条引用元数据表从原固定语料导出，不包含规则正文。引用URL/行号/修订号/本地编目/署名/许可和正文hash须逐字段一致；不能只因来自同一个Wikipedia域名就通过。
- 原运行包的全部成员按生产提交的Git树独立列举，漏文件、重复、越界、错误数据/模型/upstream版本都拒绝；不改写原manifest掩盖旧缺口。

## 重验命令与证据范围

```powershell
# 私有完整证据回归，无新模型请求，报告必须用新文件名
python -S -B scripts/verify_task13_audit.py --private --report reports/rechecks/task13-audit-20261114/recheck-new.json
# 当前完整补交付验收，公开副本使用--public-only
python -S -B scripts/verify_task13_audit_delivery.py --public-only --report reports/rechecks/task13-audit-20261114/public-new.json
# 新一轮真实功能演示，会产生模型请求；不要当作正式test
.runtime/task13/venv-final/Scripts/python.exe -B scripts/run_task13_audit_demo.py backend --report reports/rechecks/task13-audit-20261114/demo-new.json
```

旧verify_task13_delivery的24项登记数绑定其历史阶段；本轮25项登记后，使用上面的当前补交付验收，旧原完整39/39的实际复验另保存在prior-full。正式dev40/test50只读复算，不删除封存目录重跑。

真正无私有语料/模型的公开worktree使用Python -S执行新增对抗回归和当前公开完整验收。它只能复算脱敏元数据/生产提交/已保存回执；原始生成和浏览器DOM一致性由本机私有模式核对。合成故障测试不冒充真实模型样例或人工语义判断。

当前仍是非官方Wikipedia快照的AI中文整理，规则正确性/专家审校边界及原人工引用9/20等限制保留，详见[TASK_13_LICENSES](TASK_13_LICENSES.md)。修复工程缺口没有新增总体答案准确率、QPS、跨平台或Docker结论。回滚可在独立checkout检出旧tag；不删除正式账本或移动24个旧标签。
