#!/usr/bin/env bash
# Starts only the isolated knowledge stack; never changes the existing application.
set -euo pipefail
# The server keeps the Compose plugin in its approved project directory.
if ! docker compose version >/dev/null 2>&1 && [ -d /data/solexai/yongjun/select-chip-agent/docker-client ]; then
  export DOCKER_CONFIG=/data/solexai/yongjun/select-chip-agent/docker-client
fi
root=${1:-/data/solexai/yongjun/weknora}
case "$root" in /data/solexai/yongjun/*) ;; *) echo 'Deployment root must stay under /data/solexai/yongjun' >&2; exit 2;; esac
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
python3 "$source_dir/prepare.py" --root "$root"
cd "$root"
docker compose config --quiet
while IFS= read -r image; do
  pulled=0
  for attempt in 1 2 3; do
    if docker pull "$image"; then pulled=1; break; fi
  done
  if [ "$pulled" != 1 ]; then echo "Image unavailable: $image" >&2; exit 3; fi
done < <(docker compose config --images)
# Pin exactly the images which passed the registry pull, before starting them.
python3 - <<'PY'
import json, subprocess
from pathlib import Path
env=Path('.env')
data=dict(line.split('=',1) for line in env.read_text().splitlines() if '=' in line and not line.startswith('#'))
images={'WEKNORA_APP_IMAGE':'wechatopenai/weknora-app:v0.9.0',
        'WEKNORA_DOCREADER_IMAGE':'wechatopenai/weknora-docreader:v0.9.0',
        'WEKNORA_DB_IMAGE':'paradedb/paradedb:v0.25.11-pg17',
        'WEKNORA_REDIS_IMAGE':'redis:7.0-alpine', 'EMBEDDING_IMAGE':'ollama/ollama:0.40.13'}
for key, default in images.items():
    ref=data.get(key,default)
    result=json.loads(subprocess.check_output(['docker','image','inspect',ref]))[0]
    digests=result.get('RepoDigests',[])
    if not digests: raise SystemExit('Image has no registry digest: '+ref)
    data[key]=digests[0]
temporary=Path('.env.pending')
temporary.touch(mode=0o600, exist_ok=True)
temporary.chmod(0o600)
temporary.write_text(''.join(f'{k}={v}\n' for k,v in data.items()))
temporary.replace(env)
PY
docker compose up -d --wait --wait-timeout 300
docker compose exec -T embedding ollama pull qwen3-embedding:0.6b
python3 "$source_dir/bootstrap.py" --state "$root/bootstrap.json"
docker compose ps
echo 'Isolated knowledge stack prepared. Application retrieval has not been switched.'
