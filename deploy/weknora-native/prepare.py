#!/usr/bin/env python3
"""Create a separate deployment; retain generated identity and encryption keys."""
import argparse
import json
from pathlib import Path
import secrets
import shutil
import subprocess

from common import ROOT, IMAGES, read_env, save_env, save_json


def prepare(root=ROOT):
    root = Path(root)
    if root.resolve() != root.absolute():
        raise ValueError('Deployment root must not contain symbolic links')
    root.mkdir(parents=True, exist_ok=True)
    env_path = root / '.env'
    if env_path.exists():
        env = read_env(env_path)
        if env.get('NATIVE_ROOT') != str(root):
            raise ValueError('Existing environment belongs to a different deployment')
    else:
        # A lost env must not silently replace the keys of an existing database.
        if any((root / 'data').glob('postgres/*')):
            raise ValueError('Existing data without .env: restore keys before proceeding')
        env = dict(IMAGES, NATIVE_ROOT=str(root), UI_BIND='127.0.0.1', UI_PORT='18082',
                   DB_USER='weknora', DB_NAME='weknora', DB_PASSWORD=secrets.token_hex(24),
                   REDIS_PASSWORD=secrets.token_hex(24), JWT_SECRET=secrets.token_hex(32),
                   SYSTEM_AES_KEY=secrets.token_hex(16), SYSTEM_SIGNING_KEY=secrets.token_hex(32),
                   SEARXNG_SECRET=secrets.token_hex(32),
                   WEKNORA_BOOTSTRAP_SYSTEM_ADMIN_EMAIL='admin@weknora.local',
                   FRONTEND_BASE_URL='http://192.168.85.199:8080')
        save_env(env_path, env)
    identity_path = root / 'admin.json'
    if not identity_path.exists():
        if any((root / 'data').glob('postgres/*')):
            raise ValueError('Existing database without admin.json: recover the login first')
        save_json(identity_path, {'email': env['WEKNORA_BOOTSTRAP_SYSTEM_ADMIN_EMAIL'],
                  'username': 'weknora-admin', 'password': 'Aa1!' + secrets.token_urlsafe(16)})
    source = Path(__file__).parent
    target = root / 'compose.yaml'
    if target.exists() and target.read_bytes() != (source / 'compose.yaml').read_bytes():
        raise ValueError('Existing Compose differs; review it before changing deployment')
    shutil.copyfile(source / 'compose.yaml', target)
    for name in ('files', 'docreader', 'postgres', 'redis', 'models', 'searxng'):
        folder = root / 'data' / name
        if folder.resolve() != folder.absolute():
            raise ValueError('Data directory must not contain symbolic links')
        folder.mkdir(parents=True, exist_ok=True)
    searx_config = root / 'data/searxng/settings.yml'
    if not searx_config.exists():
        shutil.copyfile(source / 'searxng.yml', searx_config)
    print('Prepared isolated native deployment; credentials kept on server.')


def pin(root):
    env = read_env(root / '.env')
    pins = {}
    for key in IMAGES:
        ref = env[key]
        info = json.loads(subprocess.check_output(['docker', 'image', 'inspect', ref]))[0]
        repo = ref.split('@', 1)[0].rsplit(':', 1)[0]
        digests = [d for d in info.get('RepoDigests', []) if d.startswith(repo + '@sha256:')]
        if not digests:
            raise ValueError(f'No matching registry digest for {key}')
        env[key] = digests[0]
        pins[key] = {'source': ref, 'digest': digests[0]}
    save_env(root / '.env', env)
    save_json(root / 'images.lock.json', pins)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'pin'))
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
    else:
        pin(ROOT)
