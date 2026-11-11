"""Rebuild the local project file manifest with SHA-256 hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "manifests" / "project_file_manifest.json"
RUNTIME_SNAPSHOTS = ROOT / "data" / "manifests" / "runtime_log_snapshots.json"
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".cache",
    ".models",
    ".runtime",
    ".tmp",
    ".theflow",
    "downloads",
    "third_party",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".pem", ".key", ".p12", ".pfx"}
EXCLUDED_NAMES = {".env"}
EXCLUDED_PARTS = {"secret", "credential"}


def category_and_purpose(relative: str) -> tuple[str, str]:
    path = Path(relative)
    if path.parts[:2] == ("data", "raw"):
        return "raw_source_snapshot", "本地来源文本快照；清单用于本机审计，不代表可公开分发"
    if path.parts[:2] == ("data", "processed"):
        return "processed_corpus", "清洗、翻译、HTML、JSONL、manifest 或校验产物"
    if path.parts[:2] == ("data", "manifests"):
        return "data_manifest", "来源版本、许可或项目文件清单"
    if path.parts[0] == "docs":
        return "project_documentation", "项目方案、执行记录或技术说明"
    if path.parts[0] == "scripts":
        return "project_script", "项目构建、验证或运行脚本"
    if path.parts[0] == "reports":
        return "run_evidence", "本机执行日志或阶段验收证据"
    if path.name == ".gitignore":
        return "repository_config", "忽略规则；当前项目根目录不含 Git 元数据"
    if path.name.lower().endswith((".md", ".txt")):
        return "project_documentation", "项目入口或说明文件"
    return "project_file", "项目文件"


def should_exclude(path: Path, live_paths: set[str]) -> bool:
    relative = path.relative_to(ROOT)
    if relative.as_posix() in live_paths:
        return True
    if any(part in EXCLUDED_DIRS for part in relative.parts[:-1]):
        return True
    name = path.name.lower()
    if name in EXCLUDED_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    if any(part in name for part in EXCLUDED_PARTS):
        return True
    if name.startswith(".env.") and name != ".env.example":
        return True
    return False


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def runtime_snapshots() -> list[dict]:
    if not RUNTIME_SNAPSHOTS.is_file():
        return []
    records = json.loads(RUNTIME_SNAPSHOTS.read_text(encoding="utf-8"))["snapshots"]
    for item in records:
        source = (ROOT / item["source_path"]).resolve()
        archive = (ROOT / item["archive_path"]).resolve()
        if not source.is_relative_to(ROOT) or not archive.is_relative_to(ROOT):
            raise ValueError("Runtime log paths must remain inside this project")
        if source == archive or not source.is_file() or not archive.is_file():
            raise ValueError(f"Missing source or distinct archived runtime log: {item['source_path']}")
        if sha256(archive) != item["sha256"] or archive.stat().st_size != item["size_bytes"]:
            raise ValueError(f"Archived runtime log was changed: {item['archive_path']}")
    return records


def entries(live_paths: set[str]) -> list[dict]:
    files = []
    for current, directories, names in os.walk(ROOT, topdown=True, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(name for name in directories if name not in EXCLUDED_DIRS)
        for name in sorted(names):
            path = current_path / name
            if path == OUTPUT or should_exclude(path, live_paths):
                continue
            relative = path.relative_to(ROOT).as_posix()
            category, purpose = category_and_purpose(relative)
            files.append(
                {
                    "path": relative,
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                    "category": category,
                    "purpose": purpose,
                }
            )
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Read-only check of all frozen hashes and manifest coverage")
    args = parser.parse_args()
    snapshots = runtime_snapshots()
    live_paths = {item["source_path"] for item in snapshots}
    files = entries(live_paths)

    if args.verify:
        current = json.loads(OUTPUT.read_text(encoding="utf-8"))
        expected_by_path = {item["path"]: item for item in current["files"]}
        actual_by_path = {item["path"]: item for item in files}
        errors = []
        for path in sorted(set(expected_by_path) | set(actual_by_path)):
            if path not in expected_by_path:
                errors.append(f"unlisted: {path}")
            elif path not in actual_by_path:
                errors.append(f"missing or excluded unexpectedly: {path}")
            elif expected_by_path[path] != actual_by_path[path]:
                errors.append(f"changed: {path}")
        if current.get("file_count") != len(current["files"]):
            errors.append("file_count mismatch")
        if current.get("live_runtime_logs") != snapshots:
            errors.append("runtime log snapshot policy changed")
        print(f"Frozen manifest: {len(files)} files; runtime log snapshots: {len(snapshots)}; errors: {len(errors)}")
        for error in errors:
            print(error)
        return 1 if errors else 0

    manifest = {
        "manifest_version": "1.2",
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "scope": "本项目目录中的静态审计文件及运行日志归档快照；包括 raw/processed 语料，但不表示可公开分发。活动日志的原路径单独列示，归档快照参与文件哈希验收。",
        "self_hash_policy": "本文件不列入自身文件数组，避免递归 hash。",
        "excluded_directory_patterns": sorted(EXCLUDED_DIRS),
        "excluded_file_patterns": [
            ".env and local secret/credential files",
            "*.pyc, *.pyo, *.pem, *.key, *.p12, *.pfx",
            "data/manifests/project_file_manifest.json (self-reference)",
            "Exact live runtime log paths listed in live_runtime_logs; their immutable archive snapshots remain included",
        ],
        "live_runtime_logs": snapshots,
        "file_count": len(files),
        "files": files,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}: {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
