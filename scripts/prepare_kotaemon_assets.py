"""Prepare the auxiliary tokenizer resources used by the pinned local app.

Reuse validated local files first. Missing resources require network access to
the original tiktoken/NLTK sources. --verify-only performs no download or write.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

from kotaemon_runtime_env import CL100K_CACHE_KEY, CL100K_SHA256, CL100K_URL, configure_local_runtime


ROOT = Path(__file__).resolve().parents[1]
NLTK_PACKAGES = {
    'punkt': ('tokenizers', '51c3078994aeaf650bfc8e028be4fb42b4a0d177d41c012b6a983979653660ec'),
    'punkt_tab': ('tokenizers', 'e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106'),
    'stopwords': ('corpora', '48c0e52d8b52546e827f53761fb30300c0ab94f70660d28bd65ba0a86270946b'),
}


def prepare_nltk_package(package: str, root: Path) -> None:
    """Fetch actual NLTK data; validate publisher SHA-256 before extracting."""
    folder, expected = NLTK_PACKAGES[package]
    path = f'packages/{folder}/{package}.zip'
    headers = {'User-Agent': 'football-rules-rag-lab/0.3 (local resource setup)'}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def get(url, timeout=120):
        with opener.open(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
            return response.read()
    try:
        data = get('https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/' + path, 12)
    except OSError:
        info = json.loads(get('https://api.github.com/repos/nltk/nltk_data/contents/' + path + '?ref=gh-pages'))
        blob = json.loads(get('https://api.github.com/repos/nltk/nltk_data/git/blobs/' + info['sha']))
        data = base64.b64decode(blob['content'])
        if hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != info['sha']:
            raise ValueError('GitHub resource blob hash mismatch')
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f'NLTK {package} does not match the pinned publisher checksum')
    destination = (root / folder).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.infolist():
            if not (destination / member.filename).resolve().is_relative_to(destination):
                raise ValueError('Unsafe NLTK archive entry')
        archive.extractall(destination)
    print(f'NLTK {package}: verified SHA-256 {expected}')


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
    nltk_root = ROOT / '.cache/nltk_data'
    bundled_nltk = ROOT / '.venv/Lib/site-packages/llama_index/core/_static/nltk_cache'
    required = {
        "stopwords": ["corpora/stopwords/english"],
        "punkt": ["tokenizers/punkt/english.pickle"],
        "punkt_tab": ["tokenizers/punkt_tab/english/abbrev_types.txt", "tokenizers/punkt_tab/english/collocations.tab", "tokenizers/punkt_tab/english/ortho_context.tab", "tokenizers/punkt_tab/english/sent_starters.txt"],
    }
    for package, names in required.items():
        if not all((nltk_root / name).is_file() and (nltk_root / name).stat().st_size > 0 for name in names):
            if args.verify_only:
                raise FileNotFoundError(f"NLTK resource is incomplete: {package}")
            if all((bundled_nltk / name).is_file() and (bundled_nltk / name).stat().st_size > 0 for name in names):
                folder = NLTK_PACKAGES[package][0]
                shutil.copytree(bundled_nltk / folder / package, nltk_root / folder / package, dirs_exist_ok=True)
            else:
                prepare_nltk_package(package, nltk_root)
        if not all((nltk_root / name).is_file() and (nltk_root / name).stat().st_size > 0 for name in names):
            raise FileNotFoundError(f"Downloaded NLTK resource remains incomplete: {package}")
    result = configure_local_runtime()
    result["nltk_required_packages"] = list(required)
    result["verification"] = "PASS"
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
