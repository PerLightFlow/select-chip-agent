#!/usr/bin/env bash
set -euo pipefail
umask 077
SOURCE=$(cd -- "$(dirname -- "$0")" && pwd)
ROOT=/data/solexai/yongjun/weknora-native
if [[ $(id -u) != 0 ]]; then
  echo 'Use sudo -n /usr/local/sbin/chipagent-release apply RELEASE_NAME.' >&2
  exit 2
fi
cd "$SOURCE"
sha256sum --check --status SHA256SUMS
test -f "$ROOT/active.json"
test ! -L "$ROOT"
exec 9>"$ROOT/deploy.lock"
flock -n 9 || { echo 'Another native deployment is running.' >&2; exit 2; }
python3 "$SOURCE/deploy.py" apply
