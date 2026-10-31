#!/usr/bin/env bash
# Install the reviewed first-stage application bundle only after isolated live API acceptance.
set -euo pipefail
umask 077
APP_ROOT=/data/solexai/yongjun/select-chip-agent
WK_ROOT=/data/solexai/yongjun/weknora
RELEASE=${1:-$APP_ROOT/releases/weknora-v030}
case "$RELEASE" in "$APP_ROOT"/releases/*) ;; *) echo 'Unexpected release directory' >&2; exit 2;; esac
export DOCKER_CONFIG="$APP_ROOT/docker-client"
COMPOSE="$APP_ROOT/deploy/compose"
cd "$RELEASE"
exec 9>"$APP_ROOT/deploy/reframing.lock"
flock -n 9 || { echo 'Another release is running'; exit 1; }
sha256sum -c SHA256SUMS
curl -fsS http://127.0.0.1:18081/health >/dev/null
test -s "$WK_ROOT/bootstrap.json"
gzip -dc images.tar.gz | docker load

# Dedicated synthetic acceptance tenant and KB, never the enterprise corpus.
python3 knowledge/bootstrap.py --state "$WK_ROOT/acceptance-bootstrap.json" --scope acceptance
python3 - <<'PY'
import json,secrets
from pathlib import Path
d=json.loads(Path('/data/solexai/yongjun/weknora/acceptance-bootstrap.json').read_text())
p=Path('probe.env')
p.write_text('DJANGO_SECRET_KEY='+secrets.token_hex(32)+'\nWEKNORA_BASE_URL=http://weknora:8080\nWEKNORA_READ_KEY='+d['read_key']+'\nWEKNORA_WRITE_KEY='+d['write_key']+'\n')
p.chmod(0o600)
Path('probe-kb').write_text(d['collections']['acceptance'])
PY
trap 'rm -f probe.env probe-kb' EXIT
docker run --rm --network select-chip-knowledge --env-file probe.env \
  select-chip-agent-yongjun/backend:weknora-v030 python manage.py weknora_probe \
  --kb-id "$(cat probe-kb)" --timeout 240 | tee live-api-acceptance.json
rm -f probe.env probe-kb

# Save a consistent database snapshot and the previous deployable configuration.
BACKUP="$APP_ROOT/backups/weknora-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
cp -p "$APP_ROOT/.env" "$BACKUP/env"
cp "$APP_ROOT/deploy/compose.yaml" "$BACKUP/compose.yaml"
tar -czf "$BACKUP/source.tar.gz" -C "$APP_ROOT" src
"$COMPOSE" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BACKUP/database.dump"
test -s "$BACKUP/database.dump"

rollback() {
  status=$?
  trap - ERR
  "$COMPOSE" stop knowledge-sync || true
  cp "$BACKUP/compose.yaml" "$APP_ROOT/deploy/compose.yaml"
  cp -p "$BACKUP/env" "$APP_ROOT/.env"
  mv "$APP_ROOT/src" "$BACKUP/failed-src"
  tar -xzf "$BACKUP/source.tar.gz" -C "$APP_ROOT"
  "$COMPOSE" up -d --no-build backend worker agent-worker web || true
  echo "Application rollout failed; prior services restored. Additive schema retained. Backup: $BACKUP"
  exit "$status"
}
trap rollback ERR
tar -xzf source.tar.gz -C "$APP_ROOT/src"
cp compose.yaml "$APP_ROOT/deploy/compose.yaml"
python3 - <<'PY'
import json
from pathlib import Path
root=Path('/data/solexai/yongjun/select-chip-agent')
d=json.loads(Path('/data/solexai/yongjun/weknora/bootstrap.json').read_text())
values={'KNOWLEDGE_BACKEND':'weknora','WEKNORA_SYNC_ENABLED':'1','WEKNORA_BASE_URL':'http://weknora:8080',
        'WEKNORA_READ_KEY':d['read_key'],'WEKNORA_WRITE_KEY':d['write_key']}
p=root/'.env'
lines=[line for line in p.read_text().splitlines() if line.split('=',1)[0] not in values]
p.write_text('\n'.join(lines)+'\n'+''.join(f'{k}={v}\n' for k,v in values.items()))
p.chmod(0o600)
PY
"$COMPOSE" up -d --no-build --wait --wait-timeout 180 backend worker agent-worker web
python3 - <<'PY'
import json,time
from urllib import request
opener=request.build_opener(request.ProxyHandler({}))
for attempt in range(30):
    try:
        with opener.open('http://127.0.0.1:8080/api/health/',timeout=5) as response:
            if json.load(response).get('version') == '0.3.0': break
    except (OSError,ValueError):
        pass
    time.sleep(2)
else:
    raise SystemExit('Application frontend health did not reach v0.3.0')
PY

# Scope provisioning is explicit; do not silently fold project Wiki boundaries into common.
"$COMPOSE" exec -T backend python manage.py shell -v 0 -c \
 'from assistant.models import KnowledgeDocument; print("\n".join("project:"+str(x) for x in KnowledgeDocument.objects.filter(versions__state="published",project_id__isnull=False).values_list("project_id",flat=True).distinct()))' > scopes.txt
while IFS= read -r scope; do
  [ -z "$scope" ] && continue
  [[ "$scope" =~ ^project:[0-9]+$ ]] || { echo 'Invalid scope output'; false; }
  python3 knowledge/bootstrap.py --state "$WK_ROOT/bootstrap.json" --scope "$scope"
done < scopes.txt
python3 - <<'PY' > bindings.tsv
import json
from pathlib import Path
d=json.loads(Path('/data/solexai/yongjun/weknora/bootstrap.json').read_text())
for scope,kb in d['collections'].items(): print(scope+'\t'+kb)
PY
while IFS=$'\t' read -r scope kb; do
  "$COMPOSE" exec -T backend python manage.py weknora_sync bind --scope "$scope" --kb-id "$kb"
done < bindings.tsv
"$COMPOSE" exec -T backend python manage.py weknora_sync backfill
"$COMPOSE" up -d --no-build knowledge-sync
"$COMPOSE" exec -T backend python manage.py weknora_sync status
trap - ERR
"$COMPOSE" ps
echo "Application v0.3.0 active in weknora mode. Wiki remains disabled. Backup: $BACKUP"
