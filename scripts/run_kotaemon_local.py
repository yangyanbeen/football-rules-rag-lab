"""Launch the pinned Kotaemon app with the Windows-friendly local docstore.

Kotaemon v0.12.0's default LanceDB document store fails on this Windows
workspace while copying its initial manifest. This launcher keeps the upstream
checkout unchanged and uses the upstream SimpleFileDocumentStore plus the local
football evidence reasoning overlay. The vector store remains Chroma.
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

from kotaemon_runtime_env import configure_local_runtime


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = PROJECT_ROOT / "third_party" / "kotaemon-v0.12.0"
configure_local_runtime()

if not (UPSTREAM / "app.py").is_file():
    raise FileNotFoundError(f"Pinned Kotaemon app.py is missing: {UPSTREAM / 'app.py'}")

# Resolve this script and app imports from the exact pinned checkout.
os.chdir(UPSTREAM)
for path in (UPSTREAM, UPSTREAM / "libs" / "ktem", UPSTREAM / "libs" / "kotaemon"):
    sys.path.insert(0, str(path))

from theflow.settings import settings as flowsettings  # noqa: E402

docstore_path = UPSTREAM / "ktem_app_data" / "user_data" / "docstore-simple"
docstore_path.mkdir(parents=True, exist_ok=True)
flowsettings.KH_DOCSTORE = {
    "__type__": "kotaemon.storages.SimpleFileDocumentStore",
    "path": str(docstore_path),
}

if os.environ.get("FOOTBALL_QUALITY_GUARD", "1") != "0":
    flowsettings.KH_REASONINGS = [
        "football_quality_pipeline.FootballEvidenceQAPipeline"
        if path == "ktem.reasoning.simple.FullQAPipeline" else path
        for path in flowsettings.KH_REASONINGS
    ]
    print("Football answer profile: evidence-guard-v1 (config/answer_quality.json)")
else:
    print("Football answer profile: original upstream Simple QA (historical comparison)")

print(f"Pinned upstream: {UPSTREAM}")
print("Document store: upstream SimpleFileDocumentStore (Windows compatibility overlay)")
print("Vector store: configured upstream ChromaVectorStore")

runpy.run_path(str(UPSTREAM / "app.py"), run_name="__main__")
