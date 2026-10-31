"""Shared records, private proposals, optimistic edits and source-aware retrieval."""
import hashlib
from datetime import date
from django.db import transaction
from django.db.models import Q
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Value
from django.utils import timezone
from rest_framework import serializers
from core.domain import split_blocks
from core.knowledge import extract, tokenize
from core.models import AuditEvent
from .models import EnterpriseProject, ProjectVersion, Proposal, KnowledgeDocument, KnowledgeVersion, Passage


class PersonSchema(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    department = serializers.CharField(max_length=150, allow_blank=True, default='')
    work = serializers.CharField(max_length=500, allow_blank=True, default='')


class ModuleSchema(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    chips = serializers.ListField(child=serializers.CharField(max_length=120), max_length=30, default=list)
    responsible = PersonSchema(many=True, default=list)
    participants = PersonSchema(many=True, default=list)
    notes = serializers.CharField(max_length=3000, allow_blank=True, default='')


class ProjectSchema(serializers.Serializer):
    code = serializers.CharField(max_length=100)
    name = serializers.CharField(max_length=200)
    aliases = serializers.ListField(child=serializers.CharField(max_length=100), max_length=30, default=list)
    summary = serializers.CharField(max_length=6000, allow_blank=True, default='')
    modules = ModuleSchema(many=True, default=list)
    document_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=100, default=list)
    evidence_note = serializers.CharField(max_length=3000, allow_blank=True, default='')
    effective_from = serializers.DateField()

    def validate_modules(self, value):
        if len(value) > 100 or any(len(m['responsible']) + len(m['participants']) > 100 for m in value):
            raise serializers.ValidationError('模块或人员过多，请拆分记录')
        return value

    def validate_document_ids(self, value):
        if KnowledgeDocument.objects.filter(pk__in=value, versions__state='published').distinct().count() != len(set(value)):
            raise serializers.ValidationError('依据必须是已确认共享的文档')
        return value


def validate_project(data):
    schema = ProjectSchema(data=data)
    schema.is_valid(raise_exception=True)
    result = dict(schema.validated_data)
    result['effective_from'] = result['effective_from'].isoformat()
    return result


def propose(actor, data, project_id=None, base_revision=0, conversation=None):
    if not isinstance(base_revision, int) or isinstance(base_revision, bool) or base_revision < 0:
        raise ValueError('版本号必须为非负整数')
    if project_id is not None and (not isinstance(project_id, int) or isinstance(project_id, bool) or project_id <= 0):
        raise ValueError('项目编号无效')
    data = validate_project(data)
    project = EnterpriseProject.objects.filter(pk=project_id).first() if project_id else None
    if project_id and not project:
        raise ValueError('项目不存在')
    if project and data['code'] != project.code:
        raise ValueError('更新不能修改项目代号')
    if not project and EnterpriseProject.objects.filter(code=data['code']).exists():
        raise ValueError('项目代号已存在，请选择原项目修改')
    return Proposal.objects.create(owner=actor, conversation=conversation, project=project,
                                   base_revision=base_revision, data=data)


def confirm_proposal(proposal_id, actor):
    with transaction.atomic():
        p = Proposal.objects.select_for_update().get(pk=proposal_id)
        if p.owner_id != actor.pk and not actor.is_staff:
            raise PermissionError('不能确认他人的待保存内容')
        if p.state == 'accepted':
            return p
        if p.state not in ['pending', 'needs_admin']:
            raise ValueError('此建议已处理，请重新提出修改')
        # Validate again in case a cited document was withdrawn after preview.
        data = validate_project(p.data)
        if p.project_id:
            project = EnterpriseProject.objects.select_for_update().get(pk=p.project_id)
            if project.owner_id != actor.pk and not actor.is_staff:
                p.state = 'needs_admin'
                p.save(update_fields=['state'])
                return p
            if project.revision != p.base_revision:
                raise ValueError('项目已被修改，请查看最新内容并重新生成建议；不会覆盖他人修改')
            project.revision += 1
            project.name, project.aliases = data['name'], data['aliases']
            project.save()
        else:
            project = EnterpriseProject.objects.create(code=data['code'], name=data['name'],
                aliases=data['aliases'], owner=p.owner)
        ProjectVersion.objects.create(project=project, revision=project.revision,
            effective_from=data['effective_from'], data=data, actor=actor)
        p.project, p.state, p.confirmed_at = project, 'accepted', timezone.now()
        p.save()
        AuditEvent.objects.create(actor=actor, action='confirm_project', target=str(project.pk),
                                  detail={'revision': project.revision, 'proposal': p.pk})
        return p


def project_record(project, as_of=None):
    day = date.fromisoformat(as_of) if as_of else timezone.localdate()
    v = project.versions.filter(effective_from__lte=day).order_by('-effective_from', '-revision').first()
    return {'id': project.pk, 'code': project.code, 'name': project.name,
            'revision': project.revision, 'owner_id': project.owner_id,
            'as_of': day.isoformat(), 'data': v.data if v else None,
            'effective_revision': v.revision if v else None,
            'url': f'/api/assistant/projects/{project.pk}/?as_of={day.isoformat()}'}


def find_projects(query, as_of=None):
    query = query.strip()[:300]
    exact = EnterpriseProject.objects.filter(Q(code__iexact=query) | Q(name__iexact=query) | Q(aliases__contains=[query]))
    qs = exact if exact.exists() else EnterpriseProject.objects.filter(Q(code__icontains=query) | Q(name__icontains=query))
    return [project_record(p, as_of) for p in qs.order_by('name')[:12]]


def retrieve(query, project_id=None):
    from .knowledge_backends.retrieval import retrieve as backend_retrieve
    return backend_retrieve(query, project_id)


def retrieve_legacy(query, project_id=None):
    from .knowledge_backends.retrieval import published_versions
    terms = list(dict.fromkeys(tokenize(query[:1000]).split()))[:30]
    sq = None
    for term in terms:
        item = SearchQuery(term, config='simple')
        sq = item if sq is None else sq | item
    if sq is None:
        return []
    qs = Passage.objects.filter(version__in=published_versions(project_id)).select_related('version__document')
    # @@ uses the GIN index; filtering only on the computed rank scans every passage.
    qs = qs.filter(search_vector=sq).annotate(rank=SearchRank('search_vector', sq)).order_by('-rank', 'id')[:8]
    return [{'document_id': p.version.document_id, 'version_id': p.version_id, 'title': p.version.document.title,
             'text': p.text, 'locator': p.locator, 'url': f'/api/assistant/documents/{p.version.document_id}/file/?version={p.version_id}'} for p in qs]


def index_document(version_id):
    v = KnowledgeVersion.objects.get(pk=version_id)
    try:
        pieces = [(loc, part) for loc, text in extract(v) for part in split_blocks(text)]
        if not pieces or len(pieces) > 5000 or sum(len(t) for _, t in pieces) > 2_000_000:
            raise ValueError('文字为空或超过解析上限，请拆分文档')
        canonical = '\n\n'.join(text for _, text in pieces)
        with transaction.atomic():
            locked = KnowledgeVersion.objects.select_for_update().get(pk=v.pk)
            if locked.state != 'indexing':
                return
            locked.passages.all().delete()
            Passage.objects.bulk_create([Passage(version=locked, locator=loc, text=text,
                search_vector=SearchVector(Value(tokenize(text)), config='simple')) for loc, text in pieces])
            locked.text, locked.digest = canonical, hashlib.sha256(canonical.encode()).hexdigest()
            locked.state = 'ready'
            locked.save()
    except Exception as exc:
        message = str(exc)[:250] if isinstance(exc, ValueError) else '资料解析失败，请检查文件格式'
        KnowledgeVersion.objects.filter(pk=v.pk, state='indexing').update(state='failed', error=message, updated_at=timezone.now())


def confirm_document(version_id, actor):
    with transaction.atomic():
        v = KnowledgeVersion.objects.select_related('document').get(pk=version_id)
        doc = KnowledgeDocument.objects.select_for_update().get(pk=v.document_id)
        v = KnowledgeVersion.objects.select_for_update().get(pk=v.pk)
        if doc.owner_id != actor.pk and not actor.is_staff:
            raise PermissionError('只能维护自己提交的资料')
        if v.state == 'published':
            from .knowledge_sync import publication_changed
            publication_changed(doc)
            return
        if v.state != 'ready':
            raise ValueError('请先等待解析成功并查看预览')
        if doc.versions.filter(revision__gt=v.revision, state='published').exists():
            raise ValueError('较新版本已经发布，不能用旧版本覆盖')
        doc.versions.filter(state='published').update(state='archived')
        v.state = 'published'
        v.save()
        from .knowledge_sync import publication_changed
        publication_changed(doc)
        AuditEvent.objects.create(actor=actor, action='share_enterprise_document', target=str(doc.pk), detail={'version': v.pk})


def withdraw_document(version_id, actor):
    with transaction.atomic():
        v = KnowledgeVersion.objects.get(pk=version_id)
        doc = KnowledgeDocument.objects.select_for_update().get(pk=v.document_id)
        if doc.owner_id != actor.pk and not actor.is_staff:
            raise PermissionError('只能维护自己提交的资料')
        v = KnowledgeVersion.objects.select_for_update().get(pk=v.pk)
        v.state = 'withdrawn'
        v.save()
        from .knowledge_sync import publication_changed
        publication_changed(doc)
        AuditEvent.objects.create(actor=actor, action='withdraw_enterprise_document', target=str(doc.pk), detail={'version': v.pk})
