#!/usr/bin/env bash
# Promote the installed v0.3 integration to the sole document retrieval backend.
set -euo pipefail
umask 077
ROOT=/data/solexai/yongjun/select-chip-agent
export DOCKER_CONFIG="$ROOT/docker-client"
COMPOSE="$ROOT/deploy/compose"
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [ -f SHA256SUMS ]; then sha256sum -c SHA256SUMS; fi
exec 9>"$ROOT/deploy/reframing.lock"
flock -n 9 || { echo 'Another release is running'; exit 1; }
"$COMPOSE" config --quiet
"$COMPOSE" exec -T backend python manage.py weknora_sync backfill
"$COMPOSE" exec -T backend python manage.py shell -v 0 <<'PY'
import json
from django.conf import settings
from assistant.models import KnowledgeCollection, KnowledgeVersion, Turn
from assistant.knowledge_backends.weknora import WeKnora
assert settings.WEKNORA_SYNC_ENABLED, 'Knowledge synchronization must be enabled'
assert not Turn.objects.filter(state__in=['queued', 'running']).exists(), 'Wait for active research tasks before restarting'
published = KnowledgeVersion.objects.filter(state='published')
assert not published.exclude(replica__source_ready=True, replica__remote_id__isnull=False,
                             replica__state='ready').exists(), 'Published documents still need indexing'
collections = list(KnowledgeCollection.objects.exclude(remote_id=''))
assert any(c.scope == 'common' for c in collections), 'Shared knowledge base must be bound'
for collection in collections:
    for write in (False, True):
        data = WeKnora(write=write).collection(collection.remote_id)
        strategy = data.get('indexing_strategy', {})
        assert strategy.get('vector_enabled') and strategy.get('keyword_enabled'), 'Retrieval indexes must be enabled'
        assert not strategy.get('wiki_enabled') and not strategy.get('graph_enabled'), 'Use the validated document-only configuration'
print(json.dumps({'preflight':'passed','previous_mode':settings.KNOWLEDGE_BACKEND,
                  'published_versions':published.count(),'bound_collections':len(collections)}))
PY

BACKUP="$ROOT/backups/cutover-weknora-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
cp -p "$ROOT/.env" "$BACKUP/env"
cp -p "$ROOT/deploy/compose.yaml" "$BACKUP/compose.yaml"
SERVICES=(backend worker agent-worker knowledge-sync web)
rollback() {
  status=$?
  trap - ERR
  cp -p "$BACKUP/env" "$ROOT/.env"
  if "$COMPOSE" up -d --no-build --force-recreate --wait --wait-timeout 180 "${SERVICES[@]}"; then
    echo "Cutover failed; previous configuration and services restored. Backup: $BACKUP" >&2
  else
    echo "Cutover failed; configuration restored but service recovery needs attention. Backup: $BACKUP" >&2
  fi
  exit "$status"
}
trap rollback ERR
python3 - <<'PY'
from pathlib import Path
path = Path('/data/solexai/yongjun/select-chip-agent/.env')
values = {'KNOWLEDGE_BACKEND':'weknora', 'WEKNORA_SYNC_ENABLED':'1'}
lines = [line for line in path.read_text().splitlines() if line.split('=', 1)[0].strip() not in values]
temporary = path.with_name('.env.cutover-pending')
temporary.touch(mode=0o600, exist_ok=True)
temporary.chmod(0o600)
temporary.write_text('\n'.join(lines) + '\n' + ''.join(f'{k}={v}\n' for k,v in values.items()))
temporary.replace(path)
PY
"$COMPOSE" up -d --no-build --force-recreate --wait --wait-timeout 180 "${SERVICES[@]}"
for service in backend worker agent-worker knowledge-sync; do
  "$COMPOSE" exec -T "$service" python -c 'import os,json; os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings"); from django.conf import settings; assert settings.KNOWLEDGE_BACKEND=="weknora" and settings.WEKNORA_SYNC_ENABLED; print(json.dumps({"mode":settings.KNOWLEDGE_BACKEND,"sync_enabled":settings.WEKNORA_SYNC_ENABLED}))'
done
"$COMPOSE" exec -T backend python manage.py shell -v 0 <<'PY'
import json
from unittest.mock import patch
from assistant.knowledge import retrieve
from assistant.knowledge_backends.weknora import KnowledgeUnavailable
with patch('assistant.knowledge.retrieve_legacy', side_effect=AssertionError('Legacy retrieval must not execute')):
    result = retrieve('芯片和模块负责人')
    with patch('assistant.knowledge_backends.retrieval.retrieve_weknora', side_effect=KnowledgeUnavailable('synthetic outage')):
        try:
            retrieve('检索服务故障验证')
        except KnowledgeUnavailable:
            pass
        else:
            raise AssertionError('Knowledge service errors must not silently fall back')
print(json.dumps({'production_retrieval_mode':'weknora','legacy_calls':0,'silent_fallback':False,
                  'result_count':len(result)}))
PY
python3 - <<'PY'
import json,re,time
from urllib import request
opener = request.build_opener(request.ProxyHandler({}))
base = 'http://127.0.0.1:8080'
for attempt in range(30):
    try:
        with opener.open(base + '/api/health/', timeout=5) as response:
            health = json.load(response)
        assert health.get('version') == '0.3.0'
        with opener.open(base + '/', timeout=5) as response:
            page = response.read().decode()
        assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', page)
        assert assets
        for path in assets:
            with opener.open(base + path, timeout=5) as response:
                assert response.status == 200
        break
    except (OSError, ValueError, AssertionError):
        time.sleep(2)
else:
    raise SystemExit('Frontend/health verification failed')
print(json.dumps({'health':health,'frontend':'passed','asset_count':len(assets)}))
PY
"$COMPOSE" exec -T backend python manage.py weknora_sync status
trap - ERR
echo "WeKnora is the active production document retrieval backend. Backup: $BACKUP"
