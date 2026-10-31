"""Durable publication outbox. Each step is restartable, bounded and independently leased."""
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.db.models import F
from django.utils import timezone

from .models import KnowledgeCollection, KnowledgeReplica, KnowledgeVersion, KnowledgeDocument
from .knowledge_backends.weknora import WeKnora, RemoteError, KnowledgeUnavailable, upload_filename


def publication_changed(document):
    """Called while the document row is locked by the business transaction."""
    collection = None
    current = document.versions.filter(state='published').first()
    if current and settings.WEKNORA_SYNC_ENABLED:
        scope = f'project:{document.project_id}' if document.project_id else 'common'
        collection, _ = KnowledgeCollection.objects.get_or_create(scope=scope)
        KnowledgeReplica.objects.get_or_create(version=current, defaults={'collection': collection,
            'wiki_state': 'pending' if settings.WEKNORA_WIKI_ENABLED else 'disabled'})
    old = KnowledgeReplica.objects.filter(version__document=document).exclude(version__state='published')
    affected = set(old.values_list('collection_id', flat=True))
    if collection:
        affected.add(collection.pk)
    old.update(source_ready=False, next_attempt_at=timezone.now())
    old.exclude(state='running').exclude(state='deleted').update(state='queued', error='')
    KnowledgeCollection.objects.filter(pk__in=affected).update(generation=F('generation') + 1)
    KnowledgeCollection.objects.filter(pk__in=affected).exclude(wiki_state='disabled').update(wiki_state='dirty')
    if settings.WEKNORA_WIKI_ENABLED:
        KnowledgeCollection.objects.filter(pk__in=affected).update(wiki_state='pending', wiki_error='', wiki_next_check=timezone.now())


def claim():
    now = timezone.now()
    with transaction.atomic():
        job = (KnowledgeReplica.objects.select_for_update(skip_locked=True)
               .filter(state__in=['queued', 'retry', 'polling', 'deleting', 'uncertain', 'running'], next_attempt_at__lte=now)
               .order_by('next_attempt_at', 'created_at').first())
        if job:
            job.state = 'running'
            job.attempts += 1
            job.next_attempt_at = now + timedelta(minutes=10)
            job.save()
            return job.pk


def finish(job_id, state, error='', delay=0, ready=False):
    with transaction.atomic():
        doc_id = KnowledgeReplica.objects.values_list('version__document_id', flat=True).get(pk=job_id)
        KnowledgeDocument.objects.select_for_update().get(pk=doc_id)
        job = KnowledgeReplica.objects.select_for_update(of=('self',)).select_related('version').get(pk=job_id)
        if job.version.state != 'published':
            ready = False
            if state in {'ready', 'polling'}:
                state, delay = 'queued', 0
        job.state, job.error, job.source_ready = state, error[:300], ready
        if not error:
            job.failures = 0
        job.next_attempt_at = timezone.now() + timedelta(seconds=delay)
        job.save()


def step(job_id):
    # A session advisory lock prevents an expired lease from starting a second
    # upload while the first process still holds its HTTP connection.
    lock_id = job_id.int & ((1 << 63) - 1)
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(%s)', [lock_id])
        if not cursor.fetchone()[0]:
            return
    try:
        _step(job_id)
    except KnowledgeUnavailable as exc:
        KnowledgeReplica.objects.filter(pk=job_id).update(failures=F('failures') + 1)
        job = KnowledgeReplica.objects.get(pk=job_id)
        uncertain = job.upload_started_at and not job.remote_id
        status = getattr(exc, 'status', None)
        terminal = status in {400, 401, 403, 409, 413, 422} or job.failures >= 12
        finish(job_id, 'blocked' if terminal else ('uncertain' if uncertain else 'retry'),
               str(exc), delay=min(300, 10 * 2 ** min(job.failures, 5)))
    except Exception:
        # Do not log file text, headers, provider response bodies or credentials.
        KnowledgeReplica.objects.filter(pk=job_id).update(failures=F('failures') + 1)
        job = KnowledgeReplica.objects.get(pk=job_id)
        finish(job_id, 'blocked' if job.failures >= 12 else 'retry', '知识同步异常，请管理员检查任务', delay=60)
    finally:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_unlock(%s)', [lock_id])


def _step(job_id):
    job = KnowledgeReplica.objects.select_related('version__document', 'collection').get(pk=job_id)
    if not job.collection.remote_id:
        # No network call can have been made until a KB is bound.
        if job.version.state != 'published':
            finish(job_id, 'deleted')
        else:
            finish(job_id, 'blocked', '尚未绑定项目知识库，请联系管理员')
        return
    client = WeKnora(write=True)
    if job.version.state != 'published':
        if not job.remote_id and job.upload_started_at:
            found = client.find_upload(job)
            if not found:
                # An upload may still be completing upstream. Never forget it.
                raise RemoteError('等待确认先前上传结果，旧版本已停止检索')
            bind_remote(job, found)
        if job.remote_id:
            try:
                client.document(job.remote_id)
            except RemoteError as exc:
                if exc.status != 404:
                    raise
                finish(job_id, 'deleted')
                return
            if job.delete_requested_at:
                if job.delete_requested_at < timezone.now() - timedelta(minutes=30):
                    finish(job_id, 'blocked', '远端删除长时间未完成，请管理员检查后重试')
                    return
            else:
                from .wiki import capture_retraction
                capture_retraction(job, client)
                client.delete(job.remote_id)
                KnowledgeReplica.objects.filter(pk=job.pk).update(delete_requested_at=timezone.now())
            finish(job_id, 'deleting', delay=15)
            return
        finish(job_id, 'deleted')
        return
    if not job.remote_id:
        kb = client.collection(job.collection.remote_id)
        strategy = kb.get('indexing_strategy', {})
        if strategy.get('graph_enabled') or (strategy.get('wiki_enabled') and not settings.WEKNORA_WIKI_ENABLED):
            raise RemoteError('知识库自动整理设置与应用配置不一致', 400)
        found = client.find_upload(job)
        if found:
            bind_remote(job, found)
        elif job.upload_started_at:
            # No blind POST retry after an ambiguous result: fail closed and
            # reconcile later, including after process crash immediately after POST.
            raise RemoteError('上传结果尚未确认，正在对账；不会重复上传')
        else:
            KnowledgeReplica.objects.filter(pk=job.pk).update(upload_started_at=timezone.now())
            try:
                found = client.upload(job)
            except RemoteError as exc:
                if exc.status in {400, 401, 403, 413, 422}:
                    KnowledgeReplica.objects.filter(pk=job.pk).update(upload_started_at=None)
                raise
            bind_remote(job, found)
        # Persist the external identity before any subsequent API call.
        client.label(job)
    if job.reparse_requested:
        # Explicit owner/admin retry only. The remote identity never changes.
        client.reparse(job.remote_id)
        KnowledgeReplica.objects.filter(pk=job.pk).update(reparse_requested=False)
        finish(job_id, 'polling', delay=15)
        return
    # A withdrawal racing with upload is handled by finish(), which queues cleanup.
    remote = client.document(job.remote_id)
    if remote.get('knowledge_base_id') != job.collection.remote_id:
        raise RemoteError('同步文档的知识库与绑定不一致', 400)
    parse_state = remote.get('parse_status')
    if parse_state in {'completed', 'finalizing'}:
        finish(job_id, 'ready', ready=True)
    elif parse_state == 'failed':
        finish(job_id, 'blocked', '原文索引失败，请管理员在知识服务检查后重试')
    elif job.attempts >= 120:
        finish(job_id, 'blocked', '原文索引长时间未完成，请管理员检查处理状态')
    else:
        finish(job_id, 'polling', delay=15)


def bind_remote(job, data):
    remote_id = data.get('id')
    if not isinstance(remote_id, str) or not remote_id or len(remote_id) > 100 or data.get('knowledge_base_id') != job.collection.remote_id:
        raise RemoteError('知识服务返回的文档标识无效')
    if data.get('file_name') != upload_filename(job):
        raise RemoteError('知识服务返回了其他资料的记录，请管理员核对重复文件', 409)
    KnowledgeReplica.objects.filter(pk=job.pk).update(remote_id=remote_id)
    job.remote_id = remote_id


def retry(version_id):
    with transaction.atomic():
        job = KnowledgeReplica.objects.select_for_update().get(version_id=version_id)
        if job.state == 'running':
            raise ValueError('同步任务仍在运行')
        if job.remote_id and job.state == 'blocked' and job.error.startswith('原文索引失败'):
            job.reparse_requested = True
        if job.state == 'blocked' and job.error.startswith('远端删除长时间未完成'):
            job.delete_requested_at = None
        # upload_started_at is deliberately retained: retries reconcile uncertain POSTs.
        job.state, job.error, job.attempts, job.failures = 'queued', '', 0, 0
        job.next_attempt_at = timezone.now()
        job.save()


def status_for(version):
    try:
        r = version.replica
    except KnowledgeReplica.DoesNotExist:
        return None
    return {'state': r.state, 'source_ready': r.source_ready and version.state == 'published',
            'wiki_state': r.wiki_state, 'wiki_error': r.wiki_error, 'error': r.error, 'updated_at': r.updated_at}
