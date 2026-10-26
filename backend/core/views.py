import json
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse, FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_protect
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.db.models import F
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import serializers, viewsets
from rest_framework.throttling import AnonRateThrottle
from .models import Project, SelectionRun, Chip, Document, DocumentVersion, SearchRun
from .domain import validate_requirements
from .knowledge import search_documents, visible_chunks, serialize_chunk
from .providers import embedding_profile
from .workflow import parse_requirements, selection_graph


class LoginThrottle(AnonRateThrottle):
    scope = 'login'


@ensure_csrf_cookie
@require_http_methods(['GET'])
def session(request):
    user = request.user
    return JsonResponse({'authenticated': user.is_authenticated, 'username': user.get_username() if user.is_authenticated else '',
        'is_staff': user.is_staff if user.is_authenticated else False})


@csrf_protect
@require_http_methods(['POST'])
def sign_in(request):
    if not LoginThrottle().allow_request(request, None):
        return JsonResponse({'error':'登录尝试过于频繁，请稍后重试'}, status=429)
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError()
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error':'登录信息格式错误'},status=400)
    username, password = data.get('username',''), data.get('password','')
    if not isinstance(username, str) or not isinstance(password, str) or len(username)>150 or len(password)>1000:
        return JsonResponse({'error':'登录信息格式错误'}, status=400)
    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({'error':'用户名或密码错误'}, status=400)
    login(request, user)
    return JsonResponse({'username':user.get_username(), 'is_staff':user.is_staff})


@api_view(['POST'])
def sign_out(request):
    logout(request)
    return Response({'ok':True})


@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    return Response({'status':'ok','version':'0.1.0'})


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['id','title','description','requirements','task','revision','updated_at']
        read_only_fields = ['id','revision','updated_at']

    def validate_requirements(self, value):
        try:
            return validate_requirements(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

    def validate_description(self, value):
        if len(value)>10000:
            raise serializers.ValidationError('需求描述最多 10000 字符')
        return value


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    http_method_names = ['get','post','patch','delete','head','options']

    def get_queryset(self):
        return Project.objects.filter(owner=self.request.user).order_by('-updated_at')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_update(self, serializer):
        serializer.save(revision=serializer.instance.revision+1)


@api_view(['POST'])
def analyze(request):
    text = request.data.get('text','')
    if not isinstance(text,str) or not 1 <= len(text) <= 10000:
        return Response({'error':'请提供 1 至 10000 字符的需求描述'},status=400)
    return Response(parse_requirements(text))


@api_view(['POST','GET'])
def project_runs(request, project_id):
    project = get_object_or_404(Project, pk=project_id, owner=request.user)
    if request.method == 'GET':
        return Response([{'id':r.pk,'created_at':r.created_at,'snapshot':r.snapshot,'result':r.result}
            for r in project.runs.order_by('-id')[:30]])
    demo = request.data.get('demo',False) is True
    snapshot = {'title': project.title,'description':project.description,'requirements':project.requirements,
        'task':project.task,'revision':project.revision,'demo':demo}
    state = selection_graph.invoke({'requirements':project.requirements,'description':project.description,
        'task':project.task,'demo':demo})
    run = SelectionRun.objects.create(project=project,snapshot=snapshot,result=state['result'])
    return Response({'id':run.pk,'result':run.result,'snapshot':snapshot,'created_at':run.created_at},status=201)


@api_view(['GET'])
def export_run(request, run_id):
    run = get_object_or_404(SelectionRun, pk=run_id, project__owner=request.user)
    result = {'id':run.pk,'created_at':run.created_at.isoformat(),'snapshot':run.snapshot,
        'result':run.result,'rules_version':run.rules_version,
        'notice':'历史快照；资料可能已更新或撤回，请对新决策重新运行选型。'}
    response = HttpResponse(json.dumps(result,ensure_ascii=False,indent=2),content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="selection-{run.pk}.json"'
    return response


@api_view(['GET'])
def chips(request):
    demo = request.query_params.get('demo') == 'true'
    qs = Chip.objects.filter(published=True,is_demo=demo).order_by('manufacturer','model')
    q = request.query_params.get('q','')[:150]
    if q:
        qs = qs.filter(model__icontains=q)
    return Response({'items':list(qs.values('id','model','family','manufacturer','sku','role','lifecycle','sale_status','is_demo')),
        'coverage':{'catalog_complete':False,'notice':'全量在售目录尚未核验。演示数据不计入正式覆盖率。'}})


@api_view(['GET'])
def stats(request):
    return Response({'chips':Chip.objects.filter(published=True,is_demo=False).count(),
        'documents':Document.objects.filter(is_demo=False,active_version__state='published').count(),
        'demo_chips':Chip.objects.filter(published=True,is_demo=True).count(),
        'semantic_configured':bool(embedding_profile()),'coverage_complete':False})


@api_view(['POST'])
def search(request):
    query = request.data.get('query','')
    if not isinstance(query,str) or not 1 <= len(query.strip()) <= 2000:
        return Response({'error':'查询需要 1 至 2000 字符'},status=400)
    filters = {k:request.data.get(k,'') for k in ['chip','sdk','task']}
    if any(not isinstance(v,str) or len(v)>150 for v in filters.values()):
        return Response({'error':'过滤条件格式错误'},status=400)
    filters['demo'] = request.data.get('demo',False) is True
    result = search_documents(query,**filters)
    run = SearchRun.objects.create(owner=request.user,query=query,filters=filters,result=result)
    return Response({**result,'search_id':run.pk})


@api_view(['GET'])
def evidence(request, chunk_id):
    demo = request.query_params.get('demo') == 'true'
    c = get_object_or_404(visible_chunks(demo).select_related('version__document'),pk=chunk_id)
    return Response(serialize_chunk(c))


@api_view(['GET'])
def document_file(request, version_id):
    v = get_object_or_404(DocumentVersion,pk=version_id,state='published',document__active_version_id=F('id'))
    if v.file:
        return FileResponse(v.file.open('rb'),as_attachment=True,filename=f'document-{v.pk}.'+v.file.name.rsplit('.',1)[-1])
    response = HttpResponse(v.text,content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="document-{v.pk}.txt"'
    return response
