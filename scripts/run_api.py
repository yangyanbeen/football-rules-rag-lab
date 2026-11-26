"""Run the persistent Task13 HTTP API."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402


if __name__ == "__main__":
    uvicorn.run(
        "backend.api_app:app",
        host=os.environ.get("FOOTBALL_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("FOOTBALL_API_PORT", "8080")),
        workers=1,
    )
