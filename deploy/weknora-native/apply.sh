#!/usr/bin/env bash
set -euo pipefail
umask 077
ROOT=/data/solexai/yongjun/weknora-native
SOURCE=$(cd -- "$(dirname -- "$0")" && pwd)
if [[ $(id -u) != 0 ]]; then
  echo 'Use sudo -n /usr/local/sbin/chipagent-release apply RELEASE_NAME.' >&2
  exit 2
fi
if ! docker compose version >/dev/null 2>&1; then
  export DOCKER_CONFIG=/data/solexai/yongjun/select-chip-agent/docker-client
fi
docker compose version >/dev/null
docker info >/dev/null
python3 - <<'PY'
from pathlib import Path
p = Path('/data/solexai/yongjun/weknora-native')
if p.resolve() != p.absolute():
    raise SystemExit('Refusing symbolic links in deployment root')
PY
mkdir -p "$ROOT"
exec 9>"$ROOT/deploy.lock"
flock -n 9 || { echo 'Another native deployment is running.' >&2; exit 2; }
cd "$SOURCE"
sha256sum --check SHA256SUMS
if [[ -f "$ROOT/active.json" ]]; then
  python3 "$SOURCE/export_operator.py"
  echo 'Native deployment is already active; use its Compose for later updates.'
  exit 0
fi
printf '%s\n' '1/6 Preparing a separate native deployment.'
python3 prepare.py prepare
cd "$ROOT"
docker compose config --quiet
printf '%s\n' '2/6 Pulling fixed upstream images and recording registry digests.'
while IFS= read -r image; do
  docker pull "$image"
done < <(docker compose config --images)
python3 "$SOURCE/prepare.py" pin
# Copy reusable model files into the new instance, never share a mutable DB.
EXISTING_MODELS=/data/solexai/yongjun/weknora/data/models/models
if [[ ! -d "$ROOT/data/models/models" && -d "$EXISTING_MODELS" ]]; then
  cp -a -- "$EXISTING_MODELS" "$ROOT/data/models/"
fi
printf '%s\n' '3/6 Starting native services on server loopback ports.'
docker compose up -d --wait --wait-timeout 600
docker compose exec -T embedding ollama show qwen3-embedding:0.6b >/dev/null 2>&1 || \
  docker compose exec -T embedding ollama pull qwen3-embedding:0.6b
printf '%s\n' '4/6 Configuring the native admin, model, search and Wiki.'
python3 "$SOURCE/bootstrap.py" identity
# Startup bootstrap promotes the account that was just created; no direct SQL.
docker compose restart app
python3 "$SOURCE/bootstrap.py" configure
printf '%s\n' '5/6 Checking native upload, independent search modes and generated Wiki.'
python3 "$SOURCE/acceptance.py"
python3 "$SOURCE/bootstrap.py" team
printf '%s\n' '6/6 Switching port 8080; failures restore the old containers.'
python3 "$SOURCE/cutover.py" switch
python3 "$SOURCE/export_operator.py"
docker compose ps
printf '%s\n' 'Login details are ready for the operator; they are not included in this log.'
printf '%s\n' "Smoke results: $ROOT/acceptance.json; 50-user/10k-document capacity is not yet verified."
