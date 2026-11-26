# Task13 HTTP API

The API is a transport boundary around the existing `task13_audit_client`.
It does not change dense/BM25, RRF, reranking, context budgets, prompts, or
refusal policy. SQLite stores session metadata and completed turns; only the
last three turns (the same bounded history contract used by the worker) are
passed to a new request.

```powershell
$env:FOOTBALL_API_HOST = '127.0.0.1'
$env:FOOTBALL_API_PORT = '8080'
$env:FOOTBALL_OLLAMA_BASE_URL = 'http://127.0.0.1:11434'
.\\.venv\\Scripts\\python.exe scripts\\run_api.py
```

Endpoints:

- `GET /health` — API, SQLite and model inventory; never generates text.
- `POST /sessions` — create an isolated session.
- `GET /sessions/{id}` / `GET /sessions` — inspect persisted session state.
- `DELETE /sessions/{id}` — remove a session and its turns.
- `POST /chat` — run the existing worker and persist the turn.

The default bind is loopback. A public deployment requires an authenticated
Python service (or a managed VM/container) plus a reachable private model
service; a static frontend or a Cloudflare Worker alone cannot run this
Python/FAISS/BGE/Ollama process.

For a public reverse-proxy deployment set `FOOTBALL_API_TOKEN`; all endpoints
except `/health` then require `Authorization: Bearer <token>`. Leave it unset
only for local development.
