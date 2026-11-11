# Git 与 PR 工作流

本说明适用于新建的 `yangyanbeen/football-rules-rag-lab`。原技术/任务文档和原本地工程保持不变。此次用户授权在新仓库启用 Git，旧文档中“本机根目录未初始化 Git”的描述是当时的事实。

## 权威文档

- 需求、边界和原验收标准：`TECHNICAL_DESIGN.md`、`DEVELOPMENT_PLAN_AND_REPORT.md`，保持原件。
- 当前进度：`DELIVERY_STATUS.md`，完成一项后更新。
- 字段定义与版本：`RAG_DATA_SCHEMA.md`。
- 新技术决策：向 `DECISIONS.md` 追加。
- 每次实验：向 `EXPERIMENT_LOG.md` 追加命令、版本、结果及失败。
- 公共分发范围：`PUBLICATION_POLICY.md`。

## 一项任务的顺序

```powershell
git switch main
git pull --ff-only
git switch -c feat/task-04-evaluation
# 先写清本次范围、输入、交付物和原任务验收条件，再改动。
git status --short
git diff
git add <本次明确改动的文件>
git diff --cached
git commit -m "feat(eval): add initial annotation format"
git push -u origin feat/task-04-evaluation
gh pr create --base main --head feat/task-04-evaluation
```

PR 描述按模板填写：原任务编号、基线 commit/数据版本、交付物、实际验证、失败或限制、需维护文档。不把未执行的检查写成通过；测试和模型运行按当前任务授权及验收要求执行。先完成一个可审核的小目标，再做下一个。

## 合并与恢复

功能通过对应验收并复核公开文件范围后，通过 PR 合并。需要保留小提交时使用 merge commit，避免把多个不同目的的提交揉成一个大提交。

撤销一个普通提交：

```powershell
git switch main
git pull --ff-only
git switch -c fix/revert-change
git revert <要撤销的commit>
git push -u origin fix/revert-change
gh pr create --base main --head fix/revert-change
```

撤销一个 merge commit 时，确认其第一父提交是 main，再用 `git revert -m 1 <merge_commit>`。不要对公开 main 做 `reset --hard` 或强制推送。

`git restore --source <commit> -- <path>` 可以在新分支取回指定文件；检查后提交并发 PR。Git 只管理已跟踪的源码、文档和清单，不保存本地全文数据、账号、索引、模型；它们要单独保留本地备份，不能依靠 Git 回滚恢复。

## 本次导入的分支

| 分支 | 职责 |
| --- | --- |
| `import/task-01-corpus-audit` | 原技术/执行文档、语料审计、来源和冻结清单 |
| `import/task-02-kotaemon` | Kotaemon 运行入口、环境兼容层、回答引用修复 |
| `import/task-03-data-schema` | Schema、转换校验脚本、任务三交付报告及数据版本清单 |

这些分支用于整理已有成果，按任务 1 → 2 → 3 顺序 PR 合并。以后从最新 main 建分支，不复用这些导入分支追加新需求。
