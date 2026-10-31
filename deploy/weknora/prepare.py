#!/usr/bin/env python3
"""Prepare a new isolated deployment without overwriting existing secrets or data."""
import argparse
from pathlib import Path
import secrets
import shutil

parser = argparse.ArgumentParser()
parser.add_argument('--root', required=True, type=Path)
parser.add_argument('--port', default=18081, type=int)
parser.add_argument('--network', default='select-chip-knowledge')
args = parser.parse_args()
root = args.root.resolve()
root.mkdir(parents=True, exist_ok=True)
env = root / '.env'
if not env.exists():
    fields = {'WEKNORA_DATA_ROOT': str(root / 'data'), 'WEKNORA_ADMIN_PORT': str(args.port),
              'WEKNORA_NETWORK': args.network, 'DB_USER': 'weknora', 'DB_NAME': 'weknora',
              'DB_PASSWORD': secrets.token_hex(24), 'REDIS_PASSWORD': secrets.token_hex(24),
              'JWT_SECRET': secrets.token_hex(32), 'SYSTEM_AES_KEY': secrets.token_hex(16),
              'SYSTEM_SIGNING_KEY': secrets.token_hex(32)}
    # All values are generated or validated local paths; never print secrets.
    if any('\n' in v or '\r' in v or '$' in v for v in fields.values()):
        raise SystemExit('Unsupported characters in deployment arguments')
    with env.open('x') as stream:
        env.chmod(0o600)
        stream.write(''.join(f'{k}={v}\n' for k, v in fields.items()))
for name in ('files', 'docreader', 'postgres', 'redis', 'models'):
    (root / 'data' / name).mkdir(parents=True, exist_ok=True)
compose = root / 'compose.yaml'
if not compose.exists():
    shutil.copyfile(Path(__file__).with_name('compose.yaml'), compose)
elif compose.read_bytes() != Path(__file__).with_name('compose.yaml').read_bytes():
    raise SystemExit('Existing Compose differs; review and update explicitly')
print(f'Prepared {root}; existing credentials retained. No containers started.')
