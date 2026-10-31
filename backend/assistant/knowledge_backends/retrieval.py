import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from assistant.models import KnowledgeVersion, KnowledgeReplica, ProjectVersion, KnowledgeDocument
from .weknora import WeKnora, KnowledgeUnavailable

logger = logging.getLogger(__name__)


def published_versions(project_id=None):
    if project_id not in (None, 0):
        if isinstance(project_id, bool) or not isinstance(project_id, int) or project_id < 1:
            raise ValueError('项目编号无效')
    qs = KnowledgeVersion.objects.filter(state='published')
    if project_id:
        data = (ProjectVersion.objects.filter(project_id=project_id, effective_from__lte=timezone.localdate())
                .order_by('-effective_from', '-revision').values_list('data', flat=True).first()) or {}
        qs = qs.filter(Q(document__project_id=project_id) | Q(document_id__in=data.get('document_ids', [])))
    return qs


def locator(item):
    labels = []
    locs = item.get('source_locators', [])
    for loc in (locs if isinstance(locs, list) else [])[:6]:
        if not isinstance(loc, dict):
            continue
        if loc.get('type') == 'pdf' and isinstance(loc.get('page'), int) and loc['page'] > 0:
            labels.append(f"第 {loc['page']} 页")
        elif loc.get('type') == 'sheet' and isinstance(loc.get('row_start'), int) and loc['row_start'] > 0:
            labels.append(f"{str(loc.get('sheet', '工作表'))[:80]} 第 {loc['row_start']} 行")
        elif loc.get('type') == 'docx' and isinstance(loc.get('block'), int) and loc['block'] > 0:
            labels.append(f"第 {loc['block']} 段/表")
    return '；'.join(dict.fromkeys(labels))[:200] or '原文片段（未提供精确位置）'


def retrieve_weknora(query, project_id=None):
    versions = list(published_versions(project_id).select_related('document').order_by('id')[:settings.WEKNORA_MAX_DOCUMENTS + 1])
    if not versions:
        return []
    if len(versions) > settings.WEKNORA_MAX_DOCUMENTS:
        raise KnowledgeUnavailable('当前资料范围过大，请限定项目查询')
    replicas = list(KnowledgeReplica.objects.filter(version_id__in=[v.pk for v in versions],
        source_ready=True, remote_id__isnull=False).select_related('collection'))
    if len(replicas) != len(versions):
        # A partial migration must not silently masquerade as a complete search.
        raise KnowledgeUnavailable('部分已共享资料仍在建立索引，请稍后查询或联系管理员')
    by_id = {r.remote_id: r for r in replicas}
    by_version = {v.pk: v for v in versions}
    response = WeKnora().search(query, list(by_id))
    items = response.get('data')
    if not isinstance(items, list):
        raise KnowledgeUnavailable('企业知识服务返回格式异常')
    # Recheck after I/O; withdrawal or version replacement may have happened in flight.
    allowed = set(published_versions(project_id).values_list('pk', flat=True))
    result, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            continue
        r = by_id.get(item.get('knowledge_id'))
        if not r or r.version_id not in allowed or item.get('knowledge_base_id') != r.collection.remote_id:
            continue
        text = item.get('content')
        if not isinstance(text, str) or not text.strip():
            continue
        key = (r.remote_id, item.get('id'))
        if key in seen:
            continue
        seen.add(key)
        v = by_version[r.version_id]
        result.append({'document_id': v.document_id, 'version_id': v.pk, 'title': v.document.title,
            'text': text[:12000], 'locator': locator(item), 'kind': 'enterprise_document',
            'url': f'/api/assistant/documents/{v.document_id}/file/?version={v.pk}'})
        if len(result) == 8:
            break
    return result


def retrieve(query, project_id=None):
    from assistant.knowledge import retrieve_legacy
    if not isinstance(query, str) or not query.strip():
        return []
    mode = settings.KNOWLEDGE_BACKEND
    if mode == 'legacy':
        return retrieve_legacy(query, project_id)
    if mode == 'weknora':
        return retrieve_weknora(query, project_id)
    if mode == 'shadow':
        result = retrieve_legacy(query, project_id)
        try:
            other = retrieve_weknora(query, project_id)
            # No queries, filenames, snippets or provider response bodies in logs.
            logger.info('knowledge_shadow legacy_count=%d remote_count=%d overlap=%d', len(result), len(other),
                len({x['version_id'] for x in result} & {x['version_id'] for x in other}))
        except KnowledgeUnavailable:
            logger.warning('knowledge_shadow remote_unavailable')
        return result
    raise KnowledgeUnavailable('企业知识检索配置无效，请联系管理员')


def validate_answer_sources(sources):
    """Call inside the final message transaction; serialize with confirm/withdraw."""
    ids = {s['version_id'] for s in sources if s.get('version_id')}
    if not ids:
        return
    docs = KnowledgeVersion.objects.filter(pk__in=ids).values_list('document_id', flat=True)
    list(KnowledgeDocument.objects.select_for_update().filter(pk__in=docs).order_by('pk'))
    if KnowledgeVersion.objects.filter(pk__in=ids, state='published').count() != len(ids):
        raise KnowledgeUnavailable('回答引用的资料刚刚更新或撤回，请重新提问以获取最新依据')
