# Kotaemon 上游版本固定记录

状态：**上游固定与本机运行验收通过。**  
核验日期：2026-11-10（Asia/Shanghai）

## 固定来源

- 仓库：[Cinnamon/kotaemon](https://github.com/Cinnamon/kotaemon)
- tag：`v0.12.0`
- 完整 commit：`9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9`
- 本地 checkout：`third_party/kotaemon-v0.12.0/`
- 本地 HEAD：与固定 commit 完全一致；工作树中的运行配置和索引数据被 `.gitignore` 排除在项目文件追踪之外。
- 上游许可证：Apache License 2.0；固定提交许可证：[LICENSE.txt](https://github.com/Cinnamon/kotaemon/blob/9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9/LICENSE.txt)
- 依赖锁文件：固定 checkout 的 `uv.lock`，Python 要求 `>=3.10`；本机运行环境为 Python 3.10.22。
- 官方依据：[release v0.12.0](https://github.com/Cinnamon/kotaemon/releases/tag/v0.12.0)、[固定 commit](https://github.com/Cinnamon/kotaemon/commit/9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9)、[固定提交 README](https://github.com/Cinnamon/kotaemon/blob/9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9/README.md)

此前选择该版本时，它是核验当天官方 Releases 页面列出的最新 release。此记录固定了项目上游基线，不代表以后仍是最新版本。

## 本机执行结果

- 已从上游取得源码并核对本地 HEAD。
- 项目隔离 Python 环境已建在项目根目录 `.venv/`；该目录被忽略，不公开提交。
- 按固定 checkout 的 `uv.lock` 安装依赖；`docs/KOTAEMON_BASELINE.md` 记录了实际模型、索引配置、原始回答和验收结论。
- 上游 `app.py` 默认 LanceDB 文档存储在本机 Windows 初始化时遇到 OS error 5。没有修改上游源文件；项目使用 `scripts/run_kotaemon_local.py` 在运行时切换到上游自带的 `SimpleFileDocumentStore`，向量库仍为 Chroma。
- 首次启动尝试及兼容运行日志见 `reports/kotaemon-app-2026-11-10-final.log` 和 `reports/kotaemon-app-windows-overlay-2026-11-10.log`；成功导入日志见 `reports/task2-indexing-windows-overlay-final-2026-11-10.log`。
- 当前 checkout 用作固定实验依赖；项目自己的业务/实验代码放在仓库根目录 `scripts/`，不直接改上游实现。

## 在新环境重新取得固定版本

在项目根目录运行：

```powershell
git clone --branch v0.12.0 --depth 1 https://github.com/Cinnamon/kotaemon.git third_party/kotaemon-v0.12.0
git -C third_party/kotaemon-v0.12.0 rev-parse HEAD
```

第二条命令必须输出 `9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9`。随后按 `docs/LOCAL_SETUP.md` 建立 Python 3.10.22 环境并安装锁定依赖。不要用 `main` 或浮动 `latest` 代替此版本。

## 官方参考

- [Releases](https://github.com/Cinnamon/kotaemon/releases)
- [固定提交及源码树](https://github.com/Cinnamon/kotaemon/tree/9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9)
- [固定提交许可证](https://github.com/Cinnamon/kotaemon/blob/9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9/LICENSE.txt)
- [Windows ZIP 安装问题 #866](https://github.com/Cinnamon/kotaemon/issues/866)：曾报告 v0.12.0 的 Windows ZIP 安装故障。本机采用源码 checkout 加运行时存储覆盖层，未使用 ZIP 安装器。
