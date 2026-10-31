"""Publish immutable Wiki snapshots only after source and retraction checks."""
import hashlib
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.db.models import F
from django.utils import timezone

from .models import KnowledgeCollection, KnowledgeReplica, WikiSnapshot
from .knowledge_backends.weknora import WeKnora, KnowledgeUnavailable


def source_ids(page):
    refs = page.get('source_refs')
    if not isinstance(refs, list) or not all(isinstance(x, str) for x in refs):
        return set()
    return {x.split('|', 1)[0] for x in refs if x}


def fingerprint(page):
    return {'id': page.get('id'), 'version': page.get('version', 0),
            'digest': hashlib.sha256(page.get('content', '').encode()).hexdigest()}


def capture_retraction(replica, client):
    """Persist pre-delete content; metadata-only source removal is not a completed rewrite."""
    if not settings.WEKNORA_WIKI_ENABLED or replica.wiki_retraction is not None:
        return
    pages = client.wiki_pages(replica.collection.remote_id)
    baseline = {p['slug']: fingerprint(p) for p in pages
                if replica.remote_id in source_ids(p) and p.get('page_type') != 'index'}
    KnowledgeReplica.objects.filter(pk=replica.pk).update(wiki_retraction=baseline, wiki_state='withdrawing')
    replica.wiki_retraction = baseline


def wiki_span_state(data):
    nodes = data.get('trace', [])
    if isinstance(nodes, dict):
        nodes = [nodes]
    found = []
    def walk(items):
        for node in items:
            if not isinstance(node, dict):
                continue
            if node.get('name') == 'postprocess.wiki':
                found.append(node.get('status'))
            walk(node.get('children', []))
    walk(nodes if isinstance(nodes, list) else [])
    if any(s in {'failed', 'cancelled'} for s in found):
        return 'failed'
    if found and all(s == 'done' for s in found):
        return 'ready'
    return 'pending'


def retractions_complete(replicas, pages):
    by_slug = {p['slug']: p for p in pages}
    for replica in replicas:
        if replica.remote_id and replica.wiki_state != 'disabled' and replica.wiki_retraction is None:
            return False
        for slug, before in (replica.wiki_retraction or {}).items():
            page = by_slug.get(slug)
            if page is None:
                continue
            after = fingerprint(page)
            if after['digest'] == before['digest']:
                return False
            if after['id'] == before['id'] and after['version'] <= before['version']:
                return False
    return True


def refresh_collection(collection):
    generation = collection.generation
    replicas = list(collection.replicas.select_related('version__document'))
    current = [r for r in replicas if r.version.state == 'published']
    retired = [r for r in replicas if r.version.state != 'published']
    if any(not r.source_ready or r.state != 'ready' for r in current) or any(r.state != 'deleted' for r in retired):
        return 'pending', ''
    client = WeKnora()
    for replica in current:
        state = wiki_span_state(client.spans(replica.remote_id))
        error = 'Wiki 整理失败，原文检索仍可用；可重试整理' if state == 'failed' else ''
        KnowledgeReplica.objects.filter(pk=replica.pk).update(wiki_state=state, wiki_error=error)
        if state != 'ready':
            return state, error
    stats = client.wiki_stats(collection.remote_id)
    if stats.get('is_active') is not False or stats.get('pending_tasks') != 0:
        return 'pending', ''
    pages = client.wiki_pages(collection.remote_id)
    if not retractions_complete(retired, pages):
        return 'pending', 'Wiki 正在清理撤回资料，旧页面暂不展示'
    by_remote = {r.remote_id: r for r in current}
    snapshots = []
    covered = set()
    for page in pages:
        if page.get('page_type') == 'index' or page.get('status') != 'published':
            continue
        ids = source_ids(page)
        if not ids or not ids.issubset(by_remote):
            # A stale or unbound source invalidates the whole collection, not just one citation.
            return 'pending', 'Wiki 来源仍在更新，原文检索可继续使用'
        if not isinstance(page.get('version'), int) or page['version'] < 1:
            raise KnowledgeUnavailable('Wiki 页面版本无效')
        sources = []
        for remote_id in sorted(ids):
            r = by_remote[remote_id]
            sources.append({'document_id': r.version.document_id, 'version_id': r.version_id,
                'title': r.version.document.title, 'url': f'/api/assistant/documents/{r.version.document_id}/file/?version={r.version_id}'})
        if page.get('page_type') == 'summary':
            covered.update(ids)
        snapshots.append(WikiSnapshot(collection=collection, generation=generation, slug=page['slug'],
            title=page['title'], page_type=page['page_type'], version=page['version'],
            content=page.get('content', ''), sources=sources))
    if set(by_remote) != covered:
        return 'pending', '等待生成带来源的资料摘要页'
    # A Wiki failure can be dead-lettered after total parse_status becomes completed.
    # Only explicit successful Wiki spans plus complete, checked pages reach here.
    with transaction.atomic():
        locked = KnowledgeCollection.objects.select_for_update().get(pk=collection.pk)
        if locked.generation != generation:
            return 'pending', ''
        WikiSnapshot.objects.filter(collection=collection, generation=generation).delete()
        WikiSnapshot.objects.bulk_create(snapshots)
        locked.wiki_state, locked.wiki_error = 'ready', ''
        locked.save(update_fields=['wiki_state', 'wiki_error'])
    return 'ready', ''


def refresh_one():
    if not settings.WEKNORA_WIKI_ENABLED:
        return False
    collection = (KnowledgeCollection.objects.exclude(remote_id='').exclude(wiki_state='ready')
                  .filter(wiki_next_check__lte=timezone.now()).order_by('wiki_next_check').first())
    if not collection:
        return False
    lock = -collection.pk  # Separate lock domain from replica UUID locks.
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(%s)', [lock])
        if not cursor.fetchone()[0]:
            return False
    try:
        KnowledgeCollection.objects.filter(pk=collection.pk).update(wiki_next_check=timezone.now()+timedelta(seconds=20))
        try:
            state, error = refresh_collection(collection)
        except KnowledgeUnavailable as exc:
            state, error = 'failed', str(exc)
        except Exception:
            state, error = 'failed', 'Wiki 状态检查失败，请管理员检查后重试'
        KnowledgeCollection.objects.filter(pk=collection.pk, generation=collection.generation).update(
            wiki_state=state, wiki_error=error[:300],
            wiki_next_check=timezone.now()+timedelta(seconds=60 if state == 'failed' else 20))
        return True
    finally:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_unlock(%s)', [lock])


def retry_wiki(version):
    if not settings.WEKNORA_WIKI_ENABLED or version.state != 'published':
        raise ValueError('只有已共享资料可以重试 Wiki 整理')
    replica = KnowledgeReplica.objects.select_for_update().get(version=version)
    if not replica.remote_id or replica.state == 'running':
        raise ValueError('请等待原文同步完成')
    replica.reparse_requested = True
    replica.state, replica.source_ready, replica.wiki_state = 'queued', False, 'pending'
    replica.wiki_error, replica.error = '', ''
    replica.attempts, replica.failures = 0, 0
    replica.next_attempt_at = timezone.now()
    replica.save()
    KnowledgeCollection.objects.filter(pk=replica.collection_id).update(generation=F('generation')+1,
        wiki_state='pending', wiki_error='', wiki_next_check=timezone.now())


def visible_pages():
    if not settings.WEKNORA_WIKI_ENABLED:
        return WikiSnapshot.objects.none()
    return WikiSnapshot.objects.filter(collection__wiki_state='ready', generation=F('collection__generation'))
