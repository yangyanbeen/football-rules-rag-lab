"""Prepare process-local networking for the documented local Kotaemon setup."""

from __future__ import annotations

import importlib.util
import hashlib
import os
from pathlib import Path
from urllib.parse import urlsplit

CL100K_URL = "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
CL100K_CACHE_KEY = "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
CL100K_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"


def configure_local_runtime() -> dict:
    root = Path(__file__).resolve().parents[1]
    cache_key = CL100K_CACHE_KEY
    expected_hash = CL100K_SHA256
    candidates = []
    if os.environ.get("TIKTOKEN_CACHE_DIR"):
        candidates.append(Path(os.environ["TIKTOKEN_CACHE_DIR"]))
    candidates.extend((root / ".cache/tiktoken", root / ".venv/Lib/site-packages/llama_index/core/_static/tiktoken_cache"))
    cache = next((path for path in candidates if (path / cache_key).is_file() and hashlib.sha256((path / cache_key).read_bytes()).hexdigest() == expected_hash), None)
    if cache is None:
        raise FileNotFoundError("The verified cl100k_base tokenizer cache is missing; prepare the runtime assets described in docs/LOCAL_SETUP.md before startup.")
    os.environ["TIKTOKEN_CACHE_DIR"] = str(cache)
    nltk_candidates = [root / '.cache/nltk_data', root / '.venv/Lib/site-packages/llama_index/core/_static/nltk_cache']
    nltk_cache = next((p for p in nltk_candidates if all((p / item).is_file() for item in (
        'corpora/stopwords/english', 'tokenizers/punkt/english.pickle',
        'tokenizers/punkt_tab/english/abbrev_types.txt', 'tokenizers/punkt_tab/english/ortho_context.tab'))), None)
    if nltk_cache:
        os.environ['NLTK_DATA'] = str(nltk_cache)
    bypass = [item.strip() for item in os.environ.get("NO_PROXY", "").split(",") if item.strip()]
    for address in ("127.0.0.1", "localhost", "::1"):
        if address not in bypass:
            bypass.append(address)
    os.environ["NO_PROXY"] = ",".join(bypass)
    ignored = []
    if importlib.util.find_spec("socksio") is None:
        for name in ("ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "all_proxy", "https_proxy", "http_proxy"):
            value = os.environ.get(name)
            if value and urlsplit(value).scheme.lower().startswith("socks"):
                del os.environ[name]
                ignored.append(name)
    if ignored:
        print("Local runtime: skipped SOCKS proxy variables unsupported by this locked environment: " + ", ".join(ignored))
    print(f"Local runtime: verified tokenizer cache at {cache}")
    return {"loopback_bypass": ["127.0.0.1", "localhost", "::1"], "unsupported_proxy_variables_skipped": ignored, "tiktoken_cache": str(cache), "cl100k_base_sha256": expected_hash, "nltk_data": os.environ.get("NLTK_DATA")}
