"""Small persistent HTTP API around the Task13 worker.

The existing worker remains the source of truth for retrieval, answer policy,
citations and refusal gates. This module only supplies a stable transport and
SQLite-backed session history; it does not introduce a second RAG pipeline.
"""
from __future__ import annotations

import json
import hmac
import os
import sqlite3
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from task13_audit_client import call_worker  # noqa: E402


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _db_path() -> Path:
    configured = os.environ.get("FOOTBALL_API_DB")
    path = Path(configured) if configured else ROOT / ".runtime" / "task13-api" / "sessions.sqlite3"
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


DB_PATH = _db_path()
DB_LOCK = threading.RLock()


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
        finally:
            conn.close()


def _init_db() -> None:
    with _db() as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS turns (
                turn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                status TEXT NOT NULL,
                trace_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS turns_session_created
                ON turns(session_id, turn_id);
            """
        )


def _new_session() -> dict[str, str]:
    session_id = str(uuid.uuid4())
    now = _utc_now()
    with _db() as conn:
        conn.execute(
            "INSERT INTO sessions(session_id, created_at, updated_at) VALUES (?, ?, ?)",
            (session_id, now, now),
        )
    return {"session_id": session_id, "created_at": now, "updated_at": now}


def _session_row(session_id: str) -> sqlite3.Row | None:
    with _db() as conn:
        return conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()


def _ensure_session(session_id: str | None) -> dict[str, str]:
    if session_id is None:
        return _new_session()
    try:
        uuid.UUID(session_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="session_id must be a UUID")
    row = _session_row(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return dict(row)


def _history(session_id: str, limit: int = 3) -> list[list[str]]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT question, answer FROM turns WHERE session_id=? ORDER BY turn_id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [[row["question"], row["answer"]] for row in reversed(rows)]


def _save_turn(session_id: str, question: str, result: dict[str, Any]) -> None:
    now = _utc_now()
    with _db() as conn:
        conn.execute(
            "INSERT INTO turns(session_id, question, answer, status, trace_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                question,
                str(result.get("answer", "")),
                str(result.get("status", "error")),
                result.get("trace_id"),
                now,
            ),
        )
        conn.execute("UPDATE sessions SET updated_at=? WHERE session_id=?", (now, session_id))


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    """Do not expose prompts, raw model output, or private trace paths."""
    fields = (
        "trace_id", "status", "answer", "citations", "selected_ids",
        "offered_ids", "retrieved_ids", "refusal_reason", "error",
        "timing", "query_resolution",
    )
    return {key: result[key] for key in fields if key in result}


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1200)
    session_id: str | None = None


class SessionCreate(BaseModel):
    session_id: str | None = None


app = FastAPI(title="Football Rules RAG API", version="task13-api-1.0")


@app.middleware("http")
async def optional_bearer_auth(request: Request, call_next):
    """Require a bearer token when the deployment opts into public mode."""
    expected = os.environ.get("FOOTBALL_API_TOKEN")
    if expected and request.url.path != "/health":
        supplied = request.headers.get("authorization", "")
        if not supplied.startswith("Bearer ") or not hmac.compare_digest(supplied[7:], expected):
            return Response(status_code=401, content="unauthorized")
    return await call_next(request)


@app.on_event("startup")
def startup() -> None:
    _init_db()


@app.get("/health")
def health() -> dict[str, Any]:
    """Report API/session health and model availability without generating."""
    model_url = os.environ.get("FOOTBALL_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model_version = None
    models: list[str] = []
    model_error = None
    try:
        import urllib.request
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(model_url + "/api/version", timeout=3) as response:
            model_version = json.load(response).get("version")
        with opener.open(model_url + "/api/tags", timeout=3) as response:
            models = [row.get("name") for row in json.load(response).get("models", []) if isinstance(row, dict)]
    except Exception as exc:
        model_error = type(exc).__name__
    try:
        _init_db()
        session_store = "ok"
    except Exception as exc:
        session_store = "error"
        model_error = model_error or type(exc).__name__
    required = os.environ.get("FOOTBALL_API_MODEL", "qwen2.5:3b")
    status = "ok" if session_store == "ok" and required in models else "degraded"
    return {
        "status": status, "service": "football-rules-rag", "model_url": model_url,
        "model_version": model_version, "required_model": required, "models": models,
        "model_error": model_error, "session_store": session_store, "db_path": str(DB_PATH),
    }


@app.post("/sessions", status_code=201)
def create_session(_: SessionCreate | None = None) -> dict[str, str]:
    return _new_session()


@app.get("/sessions")
def list_sessions(limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    with _db() as conn:
        rows = conn.execute(
            "SELECT session_id, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"sessions": [dict(row) for row in rows]}


@app.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    row = _session_row(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    with _db() as conn:
        turns = conn.execute(
            "SELECT turn_id, question, answer, status, trace_id, created_at FROM turns WHERE session_id=? ORDER BY turn_id",
            (session_id,),
        ).fetchall()
    return {"session": dict(row), "turns": [dict(turn) for turn in turns]}


@app.delete("/sessions/{session_id}", status_code=204, response_class=Response)
def delete_session(session_id: str) -> Response:
    with _db() as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        cursor = conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="session not found")
    return Response(status_code=204)


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    session = _ensure_session(request.session_id)
    history = _history(session["session_id"])
    try:
        result, private_trace, elapsed = call_worker(request.question, history=history)
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"error": type(exc).__name__, "message": str(exc)}) from exc
    _save_turn(session["session_id"], request.question, result)
    return {
        "session_id": session["session_id"], "question": request.question,
        "result": _public_result(result), "elapsed_seconds": elapsed,
        "history_turns_used": len(history),
    }
