#!/usr/bin/env python3
"""Package a local completed frontend build; no networking or Docker writes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from deploy import PageAssets, dist_digest

RUNTIME = 'wechatopenai/weknora-ui@sha256:df26705d866997db07f3da78dabedc4f594b383566a3996810c166a5c6bee393'
SOURCE = Path(__file__).resolve().parent


def prepare(dist, destination, revision):
    dist = Path(dist).resolve()
    destination = Path(destination).absolute()
    if destination.exists():
        raise ValueError('Choose a new release destination; existing files are never overwritten')
    if not re.fullmatch('[a-f0-9]{40,64}', revision):
        raise ValueError('Use the full Git revision containing the frontend source')
    parser = PageAssets()
    parser.feed((dist / 'index.html').read_text())
    if not parser.title.startswith('SOLEX') or not parser.assets:
        raise ValueError('A completed SOLEX frontend build is required')
    checksum = dist_digest(dist)
    release_id = 'solex-ui-' + checksum[:16]
    destination.mkdir(parents=True)
    for name in ['apply.sh', 'deploy.py', 'Dockerfile', '50x.html', '.dockerignore', 'README.md']:
        shutil.copy2(SOURCE / name, destination / name)
    shutil.copytree(dist, destination / 'dist')
    metadata = {'release_id': release_id, 'image': 'solex/solex-ui:' + checksum[:16],
                'source_revision': revision, 'runtime_image': RUNTIME, 'dist_sha256': checksum}
    (destination / 'release.json').write_text(json.dumps(metadata, indent=2) + '\n')
    files = sorted(path for path in destination.rglob('*') if path.is_file())
    manifest = ''.join(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.relative_to(destination).as_posix() + '\n' for path in files)
    (destination / 'SHA256SUMS').write_text(manifest)
    print(json.dumps({'release_id': release_id, 'directory': str(destination), 'dist_sha256': checksum}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dist', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--source-revision', required=True)
    args = parser.parse_args()
    prepare(args.dist, args.output, args.source_revision)
