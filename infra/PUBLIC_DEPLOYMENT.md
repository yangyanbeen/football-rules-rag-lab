# 公网部署清单（未发布）

当前仓库已经有可用的本机 HTTP 边界，但没有云账号、域名或部署凭据，因此不能凭空生成一个公网地址。
公网运行必须保留下面的边界：

```text
HTTPS reverse proxy + auth/rate limit
             |
       FastAPI /chat /sessions /health
             |
  persistent Python worker + SQLite/managed DB
             |
  private Ollama 0.40.16 (qwen2.5:3b + bge-m3)
             |
  frozen corpus + Dense/BM25 indexes + BGE reranker
```

## 需要的云端资源

1. 一台能稳定驻留 3B、BGE-M3 和 FAISS/BGE 依赖的 Linux VM/容器主机；当前本机实测是 CPU
   串行 Worker，4 个 D036 并发请求会排队约 39.5 秒，不能直接承诺高并发。
2. 持久卷：模型目录、索引、SQLite（或 PostgreSQL/Redis），并将运行日志与问答 trace 分开。
3. HTTPS 域名、反向代理鉴权和限流。公网环境必须设置 `FOOTBALL_API_TOKEN`（当前本机开发入口
   默认不要求 token），并关闭调试文档或放到受保护网络。
4. 私有模型服务只允许 API 主机访问；不要把 Ollama 11434 直接暴露到公网。

## 入口与环境变量

```powershell
$env:FOOTBALL_API_HOST='127.0.0.1'
$env:FOOTBALL_API_PORT='8080'
$env:FOOTBALL_OLLAMA_BASE_URL='http://127.0.0.1:11434'
$env:FOOTBALL_API_DB='.runtime/task13-api/sessions.sqlite3'
.\\.venv\\Scripts\\python.exe scripts\\run_api.py
```

部署前必须在云主机重新执行：Ollama `/api/version` 与 `/api/tags`、E39 17 题专项、D022/T036、
固定 90 题和未见 40 题。当前固定 90 题的 `T007/T022` 原正确题退化仍未通过，公网发布应保持
E39 候选关闭。

## 当前未完成项

- 未绑定云厂商/账号/域名，故没有可宣称的公网 URL。
- 增量文档还没有在线 ingestion/re-index 端点；冻结索引不能由 `/chat` 请求隐式修改。
- 长期 Session 目前是 SQLite + 最近三轮有界历史，不是无限记忆；历史压缩需单独验收。
- 并发 4 仅做了 D036 门禁 smoke，正常回答的吞吐和 P95 尚未通过生产门禁。
