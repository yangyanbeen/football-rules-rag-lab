"""Check whether the pinned Kotaemon runtime packages are importable."""

from __future__ import annotations

import importlib
import sys

from kotaemon_runtime_env import configure_local_runtime


configure_local_runtime()
REQUIRED_MODULES = ("kotaemon", "ktem", "chromadb", "gradio")
failed = []
print(f"Python: {sys.version.split()[0]}")
for name in REQUIRED_MODULES:
    try:
        importlib.import_module(name)
        print(f"{name}: import OK")
    except Exception as exc:
        failed.append(name)
        print(f"{name}: import FAILED ({type(exc).__name__}: {exc})")
raise SystemExit(1 if failed else 0)
