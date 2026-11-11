"""Prepare the auxiliary tokenizer resources used by the pinned local app.

Reuse validated local files first. Missing resources require network access to
the original tiktoken/NLTK sources. --verify-only performs no download or write.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

from kotaemon_runtime_env import CL100K_CACHE_KEY, CL100K_SHA256, CL100K_URL, configure_local_runtime


ROOT = Path(__file__).resolve().parents[1]


def valid(path: Path) -> bool:
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == CL100K_SHA256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    target = ROOT / ".cache/tiktoken" / CL100K_CACHE_KEY
    bundled = ROOT / ".venv/Lib/site-packages/llama_index/core/_static/tiktoken_cache" / CL100K_CACHE_KEY
    if not valid(target):
        if args.verify_only and not valid(bundled):
            raise FileNotFoundError("No valid local cl100k_base cache exists")
        if not args.verify_only:
            target.parent.mkdir(parents=True, exist_ok=True)
            if valid(bundled):
                shutil.copyfile(bundled, target)
            else:
                with urllib.request.urlopen(CL100K_URL, timeout=30) as response:
                    data = response.read()
                if hashlib.sha256(data).hexdigest() != CL100K_SHA256:
                    raise ValueError("Downloaded cl100k_base file does not match the pinned dependency's SHA-256")
                target.write_bytes(data)
    nltk_root = ROOT / ".venv/Lib/site-packages/llama_index/core/_static/nltk_cache"
    required = {
        "stopwords": ["corpora/stopwords/english"],
        "punkt_tab": ["tokenizers/punkt_tab/english/abbrev_types.txt", "tokenizers/punkt_tab/english/collocations.tab", "tokenizers/punkt_tab/english/ortho_context.tab", "tokenizers/punkt_tab/english/sent_starters.txt"],
    }
    for package, names in required.items():
        if not all((nltk_root / name).is_file() and (nltk_root / name).stat().st_size > 0 for name in names):
            if args.verify_only:
                raise FileNotFoundError(f"NLTK resource is incomplete: {package}")
            import nltk
            if not nltk.download(package, download_dir=str(nltk_root), raise_on_error=True):
                raise RuntimeError(f"Failed to prepare NLTK resource: {package}")
        if not all((nltk_root / name).is_file() and (nltk_root / name).stat().st_size > 0 for name in names):
            raise FileNotFoundError(f"Downloaded NLTK resource remains incomplete: {package}")
    result = configure_local_runtime()
    result["nltk_required_packages"] = list(required)
    result["verification"] = "PASS"
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
