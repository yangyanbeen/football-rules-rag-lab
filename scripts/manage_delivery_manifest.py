"""Build/verify the public checkout's file manifest, with local corpus hashes."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data/manifests/project_file_manifest.json'


def entries():
    output = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT)
    names = {p.decode('utf-8') for p in output.split(b'\0') if p}
    public = names - {OUTPUT.relative_to(ROOT).as_posix()}
    inventory = json.loads((ROOT / 'data/manifests/local_data_files.json').read_text('utf-8'))
    local = {x['path'] for x in inventory['files']}
    if public & local:
        raise ValueError('Full corpus unexpectedly tracked by Git')
    result = []
    for name in sorted(public | local):
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError(f'Missing or unsafe path: {name}')
        data = path.read_bytes()
        layer = Path(name).parts[0]
        purpose = {'docs': '技术、执行或当前交付文档', 'scripts': '构建、运行或验收工具',
                   'reports': '历史证据或本次补交付验收结果', 'frontend': '界面入口与职责说明',
                   'backend': '后端职责说明', 'infra': '运行环境说明', 'config': '非敏感应用配置',
                   'data': '数据格式、来源或版本清单', '.github': 'PR 工作流模板'}.get(layer, '仓库入口、许可证或 Git 配置')
        result.append({'path': name, 'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                       'purpose': '原本地冻结语料；只公开此元数据，不上传全文' if name in local else purpose,
                       'distribution': 'local-only' if name in local else 'public-git'})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    current = entries()
    if args.verify:
        stored = json.loads(OUTPUT.read_text('utf-8'))
        expected = {i['path']: i for i in stored['files']}
        actual = {i['path']: i for i in current}
        errors = [p for p in sorted(set(expected) | set(actual)) if expected.get(p) != actual.get(p)]
        if stored['file_count'] != len(current):
            errors.append('file_count')
        print(json.dumps({'status': 'FAIL' if errors else 'PASS', 'files': len(current), 'errors': errors}))
        return 1 if errors else 0
    payload = {'manifest_version': 'public-checkout-1.0',
               'scope': 'New public checkout: tracked files plus hash-only local corpus inventory; original local project manifest is preserved separately.',
               'self_hash_policy': 'This manifest excludes itself to avoid recursion.',
               'runtime_policy': 'External runtime, credentials, databases, caches, live logs and temporary fixtures are excluded.',
               'file_count': len(current), 'files': current}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(f'Wrote {len(current)} file entries')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
