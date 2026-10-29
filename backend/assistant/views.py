from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Conversation, Message, Turn, EnterpriseProject, Proposal, KnowledgeDocument, KnowledgeVersion
from .knowledge import propose, confirm_proposal, project_record, find_projects, retrieve, confirm_document


def proposal_data(p):
    return {'id': p.pk, 'data': p.data, 'project_id': p.project_id, 'base_revision': p.base_revision, 'state': p.state}


def conversation_data(c, detail=False):
    result = {'id': str(c.pk), 'title': c.title, 'updated_at': c.updated_at}
    if detail:
        result['brief'] = c.brief
        result['messages'] = list(c.messages.order_by('id').values('id', 'role', 'content', 'sources', 'created_at'))
        result['turn'] = c.turns.order_by('-created_at').values('id', 'state', 'events', 'error', 'usage').first()
        result['proposals'] = [proposal_data(p) for p in c.proposals.order_by('-id')[:30]]
    return result


@api_view(['GET', 'POST'])
def conversations(request):
    if request.method == 'POST':
        return Response(conversation_data(Conversation.objects.create(owner=request.user)), status=201)
    return Response([conversation_data(c) for c in Conversation.objects.filter(owner=request.user).order_by('-updated_at')[:100]])


@api_view(['GET', 'DELETE'])
def conversation(request, conversation_id):
    c = get_object_or_404(Conversation, pk=conversation_id, owner=request.user)
    if request.method == 'DELETE':
        with transaction.atomic():
            c = Conversation.objects.select_for_update().get(pk=c.pk)
            if c.turns.filter(state__in=['queued', 'running']).exists():
                return Response({'error': '请先停止当前调研'}, status=409)
            c.delete()
        return Response(status=204)
    return Response(conversation_data(c, True))


@api_view(['POST'])
def send_message(request, conversation_id):
    text = request.data.get('text')
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 10000:
        return Response({'error': '请输入 1–10000 字符'}, status=400)
    try:
        with transaction.atomic():
            c = get_object_or_404(Conversation.objects.select_for_update(), pk=conversation_id, owner=request.user)
            if c.turns.filter(state__in=['queued', 'running']).exists():
                return Response({'error': '本轮仍在进行，请等待或停止后再发送'}, status=409)
            if Turn.objects.filter(conversation__owner=request.user, state__in=['queued', 'running']).count() >= 2:
                return Response({'error': '每个用户最多同时运行两项调研'}, status=429)
            Message.objects.create(conversation=c, role='user', content=text.strip())
            if c.title == '新对话':
                c.title = text.strip()[:80]
            c.save()
            turn = Turn.objects.create(conversation=c)
        return Response({'id': str(turn.pk), 'state': turn.state}, status=202)
    except IntegrityError:
        return Response({'error': '本轮已提交，请刷新查看'}, status=409)


@api_view(['POST'])
def stop_turn(request, turn_id):
    with transaction.atomic():
        t = get_object_or_404(Turn.objects.select_for_update(), pk=turn_id, conversation__owner=request.user)
        if t.state in ['queued', 'running']:
            t.state = 'cancelled'
            t.save()
            # Unconfirmed suggestions from a cancelled run must not appear as saved facts.
    return Response({'state': t.state})


@api_view(['GET'])
def projects(request):
    query, as_of = request.query_params.get('q', ''), request.query_params.get('as_of')
    try:
        items = find_projects(query, as_of) if query else [project_record(p, as_of) for p in EnterpriseProject.objects.order_by('-id')[:100]]
    except ValueError:
        return Response({'error': '历史日期应为 YYYY-MM-DD'}, status=400)
    return Response({'items': items})


@api_view(['GET'])
def project_detail(request, project_id):
    p = get_object_or_404(EnterpriseProject, pk=project_id)
    try:
        data = project_record(p, request.query_params.get('as_of'))
    except ValueError:
        return Response({'error': '日期格式错误'}, status=400)
    data['versions'] = list(p.versions.order_by('-revision').values('revision', 'effective_from', 'data', 'created_at')[:100])
    return Response(data)


@api_view(['GET', 'POST'])
def proposals(request):
    if request.method == 'GET':
        qs = Proposal.objects.filter(Q(owner=request.user) | (Q(state='needs_admin') if request.user.is_staff else Q(pk__in=[])))
        return Response([proposal_data(p) for p in qs.order_by('-id')[:100]])
    try:
        p = propose(request.user, request.data.get('data'), request.data.get('project_id'), request.data.get('base_revision', 0))
        return Response(proposal_data(p), status=201)
    except (ValueError, IntegrityError):
        return Response({'error': '项目或版本不正确，请刷新后重试'}, status=400)


@api_view(['POST'])
def proposal_action(request, proposal_id):
    qs = Proposal.objects.filter(Q(owner=request.user) | (Q(state='needs_admin') if request.user.is_staff else Q(pk__in=[])))
    p = get_object_or_404(qs, pk=proposal_id)
    if request.data.get('action') == 'reject':
        with transaction.atomic():
            p = Proposal.objects.select_for_update().get(pk=p.pk)
            if p.state not in ['pending', 'needs_admin']:
                return Response({'error': '建议已经处理'}, status=409)
            p.state = 'rejected'
            p.save()
        return Response(proposal_data(p))
    if request.data.get('action') != 'confirm':
        return Response({'error': '需要明确确认待保存内容'}, status=400)
    try:
        return Response(proposal_data(confirm_proposal(p.pk, request.user)))
    except PermissionError as exc:
        return Response({'error': str(exc)}, status=403)
    except (ValueError, IntegrityError) as exc:
        return Response({'error': str(exc) if isinstance(exc, ValueError) else '项目代号冲突，请刷新后重新整理'}, status=409)


def document_data(doc, user):
    versions = doc.versions.all()
    if doc.owner_id != user.pk and not user.is_staff:
        versions = versions.filter(state__in=['published', 'archived'])
    return {'id': doc.pk, 'title': doc.title, 'project_id': doc.project_id,
            'can_edit': doc.owner_id == user.pk or user.is_staff,
            'versions': list(versions.order_by('-revision').values('id', 'revision', 'state', 'error', 'digest', 'created_at')[:20])}


@api_view(['GET', 'POST'])
def documents(request):
    if request.method == 'GET':
        qs = KnowledgeDocument.objects.filter(Q(versions__state='published') | Q(owner=request.user)).distinct().order_by('-id')
        if request.user.is_staff:
            qs = KnowledgeDocument.objects.all().order_by('-id')
        query = request.query_params.get('q', '')[:200]
        if query:
            qs = qs.filter(title__icontains=query)
        try:
            offset = max(0, int(request.query_params.get('offset', 0)))
        except ValueError:
            return Response({'error': '分页参数错误'}, status=400)
        return Response({'count': qs.count(), 'items': [document_data(d, request.user) for d in qs[offset:offset+30]]})
    title, text, upload = request.data.get('title', ''), request.data.get('text', ''), request.FILES.get('file')
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 250 or not isinstance(text, str) or len(text) > 1_000_000:
        return Response({'error': '标题或正文格式不正确'}, status=400)
    if not upload and not text.strip():
        return Response({'error': '请选择文件或填写正文'}, status=400)
    if upload and (upload.size > 10 * 1024 * 1024 or upload.name.rsplit('.', 1)[-1].lower() not in {'pdf', 'docx', 'xlsx', 'csv', 'txt', 'md'}):
        return Response({'error': '支持不超过 10 MiB 的 PDF、DOCX、XLSX、CSV、TXT、MD'}, status=400)
    project = None
    if request.data.get('project_id'):
        project = get_object_or_404(EnterpriseProject, pk=request.data['project_id'])
    with transaction.atomic():
        if request.data.get('document_id'):
            doc = get_object_or_404(KnowledgeDocument.objects.select_for_update(), pk=request.data['document_id'])
            if doc.owner_id != request.user.pk and not request.user.is_staff:
                return Response({'error': '只能维护自己的资料'}, status=403)
            revision = (doc.versions.order_by('-revision').first().revision if doc.versions.exists() else 0) + 1
        else:
            doc = KnowledgeDocument.objects.create(owner=request.user, title=title.strip(), project=project)
            revision = 1
        KnowledgeVersion.objects.create(document=doc, revision=revision, text=text, file=upload or '')
    return Response(document_data(doc, request.user), status=202)


@api_view(['GET', 'POST'])
def document_detail(request, document_id):
    doc = get_object_or_404(KnowledgeDocument, pk=document_id)
    if request.method == 'GET':
        allowed = doc.versions.all()
        if doc.owner_id != request.user.pk and not request.user.is_staff:
            allowed = allowed.filter(state__in=['published', 'archived'])
        v = get_object_or_404(allowed, pk=request.query_params.get('version')) if request.query_params.get('version') else allowed.order_by('-revision').first()
        if v is None:
            return Response({'error': '资料不存在'}, status=404)
        return Response({**document_data(doc, request.user), 'preview': v.text[:20000], 'version_id': v.pk})
    if doc.owner_id != request.user.pk and not request.user.is_staff:
        return Response({'error': '只能维护自己的资料'}, status=403)
    v = get_object_or_404(doc.versions, pk=request.data.get('version_id'))
    try:
        if request.data.get('action') == 'confirm':
            confirm_document(v.pk, request.user)
        elif request.data.get('action') == 'withdraw':
            with transaction.atomic():
                KnowledgeDocument.objects.select_for_update().get(pk=doc.pk)
                v = KnowledgeVersion.objects.select_for_update().get(pk=v.pk)
                v.state = 'withdrawn'
                v.save()
        else:
            raise ValueError('请选择确认共享或撤回')
    except (ValueError, PermissionError) as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(document_data(doc, request.user))


@api_view(['GET'])
def document_file(request, document_id):
    doc = get_object_or_404(KnowledgeDocument, pk=document_id)
    qs = doc.versions.filter(state__in=['published', 'archived'])
    if doc.owner_id == request.user.pk or request.user.is_staff:
        qs = doc.versions.all()
    v = get_object_or_404(qs, pk=request.query_params.get('version')) if request.query_params.get('version') else qs.order_by('-revision').first()
    if not v:
        return Response({'error': '资料不存在'}, status=404)
    if v.file:
        return FileResponse(v.file.open('rb'), as_attachment=True)
    return HttpResponse(v.text, content_type='text/plain; charset=utf-8')


@api_view(['POST'])
def search(request):
    query = request.data.get('query', '')
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 1000:
        return Response({'error': '请输入查询内容'}, status=400)
    return Response({'items': retrieve(query, request.data.get('project_id'))})
