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
LOCAL_PROFILE = os.environ.get('FOOTBALL_LOCAL_PROFILE', '1') != '0'
if LOCAL_PROFILE:
    # These upstream feature switches are read while flowsettings is loaded.
    for name in ('USE_MS_GRAPHRAG', 'USE_LIGHTRAG', 'USE_NANO_GRAPHRAG', 'USE_GLOBAL_GRAPHRAG'):
        os.environ[name] = 'false'
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
    os.environ.setdefault('GRADIO_ANALYTICS_ENABLED', 'false')
    os.environ.setdefault('GRADIO_SERVER_NAME', '127.0.0.1')
    # A new database gets an actual random admin password, stored locally only.
    if not (UPSTREAM / 'ktem_app_data/user_data/sql.db').exists() and not os.environ.get('KH_FEATURE_USER_MANAGEMENT_PASSWORD'):
        import json
        import secrets
        account_path = PROJECT_ROOT / '.runtime/kotaemon-admin.json'
        account_path.parent.mkdir(parents=True, exist_ok=True)
        if account_path.exists():
            account = json.loads(account_path.read_text('utf-8'))
        else:
            account = {'username': 'admin', 'password': 'Aa1!' + secrets.token_urlsafe(24)}
            with account_path.open('x', encoding='utf-8') as handle:
                json.dump(account, handle)
        os.environ['KH_FEATURE_USER_MANAGEMENT_PASSWORD'] = account['password']
configure_local_runtime()

if not (UPSTREAM / "app.py").is_file():
    raise FileNotFoundError(f"Pinned Kotaemon app.py is missing: {UPSTREAM / 'app.py'}")

# Resolve this script and app imports from the exact pinned checkout.
os.chdir(UPSTREAM)
for path in (UPSTREAM, UPSTREAM / "libs" / "ktem", UPSTREAM / "libs" / "kotaemon"):
    sys.path.insert(0, str(path))

from theflow.settings import settings as flowsettings  # noqa: E402

if LOCAL_PROFILE:
    flowsettings.KH_ENABLE_FIRST_SETUP = False
    flowsettings.KH_GRADIO_SHARE = False
    flowsettings.SETTINGS_REASONING['lang']['value'] = 'zh'
    flowsettings.KH_LLMS = {'ollama': {'spec': {
        '__type__': 'kotaemon.llms.ChatOpenAI', 'base_url': 'http://127.0.0.1:11434/v1/',
        'model': 'qwen2.5:3b', 'api_key': 'ollama', 'temperature': 0,
    }, 'default': True}}
    flowsettings.KH_EMBEDDINGS = {'ollama': {'spec': {
        '__type__': 'kotaemon.embeddings.OpenAIEmbeddings', 'base_url': 'http://127.0.0.1:11434/v1/',
        'model': 'bge-m3', 'api_key': 'ollama',
    }, 'default': True}}
    flowsettings.KH_RERANKINGS = {}
    flowsettings.FILE_INDEX_RETRIEVER_PIPELINES = [
        'kotaemon_local_retrieval.LocalDocumentRetrievalPipeline'
    ]
    flowsettings.KH_REASONINGS = ['ktem.reasoning.simple.FullQAPipeline']
    print('Football local profile: Ollama defaults; optional graph indexes disabled')

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
