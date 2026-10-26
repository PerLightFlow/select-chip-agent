import hashlib
import re
import uuid
import jieba
from bs4 import BeautifulSoup
from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.utils import timezone
from pgvector.django import CosineDistance
from pypdf import PdfReader
from .models import Document, DocumentVersion, Chunk, AuditEvent
from .domain import split_blocks, reciprocal_rank_fusion
from .providers import embed, embedding_profile, ProviderUnavailable


def tokenize(text):
    return ' '.join(t.lower() for t in jieba.lcut(text) if re.search(r'\w', t))


def visible_chunks(demo=False):
    return Chunk.objects.filter(version__state='published',
        version__document__active_version_id=F('version_id'), version__document__is_demo=demo)


def evidence_valid(chunk, demo=False, chip='', sdk=''):
    if not chunk:
        return False
    if chip and chip not in chunk.version.chip_models:
        return False
    if sdk and chunk.version.sdk_version != sdk:
        return False
    return visible_chunks(demo).filter(pk=chunk.pk).exists()


def extract(version):
    if not version.file:
        return [('正文', version.text)]
    if version.file.size > 10 * 1024 * 1024:
        raise ValueError('文件超过 10 MiB，请拆分后上传')
    suffix = version.file.name.rsplit('.', 1)[-1].lower()
    with version.file.open('rb') as f:
        if suffix == 'pdf':
            reader = PdfReader(f)
            if reader.is_encrypted or len(reader.pages) > 500:
                raise ValueError('加密文件或超过 500 页，需要人工整理')
            pages = [(f'第 {i + 1} 页', page.extract_text() or '') for i, page in enumerate(reader.pages)]
            if any(len(text.strip()) < 10 for _, text in pages):
                raise ValueError('存在无法可靠提取的页面，请先 OCR 或人工整理')
            return pages
        if suffix not in {'txt', 'md', 'html', 'htm'}:
            raise ValueError('只支持 PDF、TXT、Markdown 或 HTML')
        raw = f.read()
    if suffix in {'html', 'htm'}:
        soup = BeautifulSoup(raw, 'html.parser')
        for node in soup(['script', 'style', 'nav', 'header', 'footer', 'noscript', 'form']):
            node.decompose()
        for table in soup.find_all('table'):
            if table.select('[rowspan], [colspan]'):
                raise ValueError('合并单元格需要人工核对并整理为 Markdown')
            rows = [' | '.join(c.get_text(' ', strip=True) for c in row.find_all(['td', 'th']))
                    for row in table.find_all('tr')]
            table.replace_with('\n\n' + '\n'.join(rows) + '\n\n')
        text = soup.get_text('\n')
    else:
        text = raw.decode('utf-8-sig')
    return [('正文', text)]


def queue_index(version_id, actor):
    with transaction.atomic():
        v = DocumentVersion.objects.select_for_update().get(pk=version_id)
        if v.state not in {'draft', 'failed'}:
            raise ValueError('仅草稿或失败版本可以建立索引')
        if not isinstance(v.chip_models, list) or any(not isinstance(x, str) for x in v.chip_models):
            raise ValueError('适用型号必须是字符串数组')
        v.state, v.error = 'queued', ''
        v.save()
        AuditEvent.objects.create(actor=actor, action='queue_index', target=str(v.pk))


def build_index(version_id):
    v = DocumentVersion.objects.get(pk=version_id)
    if v.state != 'indexing':
        raise ValueError('版本尚未被 Worker 领取')
    try:
        pages = extract(v)
        pieces = [(loc, part) for loc, text in pages for part in split_blocks(text)]
        if not pieces or len(pieces) > 5000 or sum(len(t) for _, t in pieces) > 2_000_000:
            raise ValueError('文本为空或超过处理上限，请拆分并人工核验')
        profile = embedding_profile()
        if not profile and not (settings.ALLOW_KEYWORD_ONLY or v.document.is_demo):
            raise ValueError('尚未配置 Embedding；正式语义索引不能发布')
        vectors = embed([p[1] for p in pieces]) if profile else [None] * len(pieces)
        canonical = '\n\n'.join(f'[{loc}]\n{text}' for loc, text in pieces)
        chunks = [Chunk(version=v, ordinal=i, text=text, locator=f'{loc} · 段落 {i+1}',
                    terms=tokenize(text), embedding=vectors[i]) for i, (loc, text) in enumerate(pieces)]
        with transaction.atomic():
            locked = DocumentVersion.objects.select_for_update().get(pk=v.pk)
            if locked.state != 'indexing' or locked.index_generation != v.index_generation:
                return
            locked.chunks.all().delete()
            Chunk.objects.bulk_create(chunks)
            locked.text, locked.digest = canonical, hashlib.sha256(canonical.encode()).hexdigest()
            locked.embedding_profile, locked.index_generation = profile, uuid.uuid4()
            locked.state, locked.error = 'ready', ''
            locked.save()
    except Exception as exc:
        # Provider payloads/credentials must not enter logs or persisted errors.
        message = str(exc) if isinstance(exc, (ValueError, ProviderUnavailable)) else '解析或索引失败，请检查资料格式'
        DocumentVersion.objects.filter(pk=v.pk, state='indexing', index_generation=v.index_generation).update(state='failed', error=message[:250], updated_at=timezone.now())


def publish_version(version_id, actor):
    with transaction.atomic():
        v = DocumentVersion.objects.select_for_update().select_related('document').get(pk=version_id)
        doc = Document.objects.select_for_update().get(pk=v.document_id)
        if v.state != 'ready' or not v.chunks.exists():
            raise ValueError('只有索引完成的待审核版本可以发布')
        if not v.embedding_profile and not (settings.ALLOW_KEYWORD_ONLY or doc.is_demo):
            raise ValueError('正式语义索引尚未完成')
        if v.embedding_profile and v.embedding_profile != embedding_profile():
            raise ValueError('向量模型配置已变化，请以新文档版本重建索引')
        v.state, v.reviewed_by, v.published_at = 'published', actor, timezone.now()
        v.save()
        doc.active_version = v
        doc.save(update_fields=['active_version'])
        AuditEvent.objects.create(actor=actor, action='publish_document', target=str(v.pk), detail={'digest': v.digest})


def withdraw_version(version_id, actor):
    with transaction.atomic():
        v = DocumentVersion.objects.select_for_update().get(pk=version_id)
        v.state = 'withdrawn'
        v.save()
        Document.objects.filter(pk=v.document_id, active_version=v).update(active_version=None)
        AuditEvent.objects.create(actor=actor, action='withdraw_document', target=str(v.pk))


def serialize_chunk(c):
    return {'id': c.pk, 'text': c.text, 'locator': c.locator, 'title': c.version.document.title,
        'document_id': c.version.document_id, 'version_id': c.version_id,
        'revision': c.version.revision, 'index_generation': str(c.version.index_generation),
        'chip_models': c.version.chip_models, 'sdk_version': c.version.sdk_version,
        'source_url': c.version.document.source_url, 'is_demo': c.version.document.is_demo}


def search_documents(query, chip='', sdk='', task='', demo=False, limit=8):
    query = query.strip()[:2000]
    if not query:
        return {'items': [], 'mode': 'keyword', 'notice': '请输入检索内容'}
    base = visible_chunks(demo).select_related('version__document')
    if chip:
        base = base.filter(version__chip_models__contains=[chip])
    if sdk:
        base = base.filter(version__sdk_version=sdk)
    if task:
        base = base.filter(version__task=task)
    words = list(dict.fromkeys(tokenize(query).split()))[:40]
    sq = None
    for word in words:
        item = SearchQuery(word, config='simple')
        sq = item if sq is None else sq | item
    lexical = []
    if sq is not None:
        lexical = list(base.annotate(rank=SearchRank(SearchVector('terms', config='simple'), sq))
            .filter(rank__gt=0).order_by('-rank','id').values_list('id', flat=True)[:40])
    semantic, mode, notice = [], 'keyword', '未配置向量服务，当前仅使用关键词检索'
    profile = embedding_profile()
    if profile:
        try:
            vector = embed([query])[0]
            semantic = list(base.filter(version__embedding_profile=profile, embedding__isnull=False)
                .annotate(distance=CosineDistance('embedding', vector))
                .filter(distance__lte=settings.EMBEDDING_MAX_DISTANCE).order_by('distance','id')
                .values_list('id', flat=True)[:40])
            mode, notice = 'hybrid', ''
            if base.exclude(version__embedding_profile=profile).exists():
                notice = '部分文档索引配置不同，仅参与关键词检索；请重建匹配的索引'
        except ProviderUnavailable as exc:
            notice = str(exc) + '；已降级为关键词检索'
    ranked, scores = reciprocal_rank_fusion(lexical, semantic)
    # Recheck publication status after external call; withdrawn evidence is excluded.
    found = {c.pk: c for c in base.filter(pk__in=ranked[:limit])}
    return {'items': [{**serialize_chunk(found[i]), 'rank_score': scores[i]} for i in ranked[:limit] if i in found],
        'mode': mode, 'notice': notice, 'embedding_profile': profile,
        'config': {'fusion': 'rrf', 'k': 60, 'limit': limit, 'max_distance': settings.EMBEDDING_MAX_DISTANCE}}
