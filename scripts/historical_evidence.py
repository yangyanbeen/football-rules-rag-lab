"""Read immutable Git evidence without taking source identities from today's workspace."""
import re
import subprocess
from pathlib import PurePosixPath

from answer_eval_core import ROOT, digest


def git_bytes(commit, name):
    if not isinstance(commit, str) or not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('Expected a full producer commit')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or str(path) != name or '\\' in name:
        raise ValueError('Expected a checkout-relative Git path')
    result = subprocess.run(['git', 'show', f'{commit}:{name}'], cwd=ROOT, capture_output=True)
    if result.returncode:
        raise ValueError(f'File is missing from the recorded commit: {name}')
    return result.stdout


def git_record(commit, name):
    raw = git_bytes(commit, name)
    return {'path': name, 'size_bytes': len(raw), 'sha256': digest(raw)}


def frozen_bytes(path, commit):
    path = path.resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Frozen input is outside this checkout')
    name = path.relative_to(ROOT).as_posix()
    original = git_bytes(commit, name)
    if path.read_bytes() != original:
        raise ValueError(f'Frozen input differs from its original bytes: {name}')
    return original
