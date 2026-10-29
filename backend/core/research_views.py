from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.http import FileResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import ResearchJob, DocumentVersion
from .research import enqueue
from .official_http import REGISTRY


def jobs_for(user):
    qs = ResearchJob.objects.filter(owner=user)
    if user.is_staff:
        qs = ResearchJob.objects.filter(Q(owner=user) | Q(owner__isnull=True))
    return qs


def serialize_job(job):
    result = dict(job.result)
    items = [dict(item) for item in result.get('items', [])]
    states = {v.pk:v for v in DocumentVersion.objects.filter(pk__in=[i['version_id'] for i in items])}
    for item in items:
        v = states.get(item['version_id'])
        item['state'] = v.state if v else 'unavailable'
        item['index_error'] = v.error if v else ''
    result['items'] = items
    return {'id':job.pk,'kind':job.kind,'query':job.query,'url':job.url,'chip':job.chip,'sdk':job.sdk,
        'state':job.state,'result':result,'error':job.error,'created_at':job.created_at,'updated_at':job.updated_at}


@api_view(['GET','POST'])
def jobs(request):
    if request.method == 'GET':
        return Response({'items':[serialize_job(j) for j in jobs_for(request.user).order_by('-id')[:30]]})
    kind = request.data.get('kind','search')
    if kind == 'import' and not request.user.is_staff:
        return Response({'error':'官网链接导入由管理员操作；普通用户可查询官方资料'},status=403)
    try:
        job = enqueue(request.user,kind=kind,**{k:request.data.get(k,'') for k in ('query','url','chip','sdk')})
    except ValueError as exc:
        return Response({'error':str(exc)},status=400)
    return Response(serialize_job(job),status=202)


@api_view(['GET'])
def job_detail(request, job_id):
    return Response(serialize_job(get_object_or_404(jobs_for(request.user),pk=job_id)))


@api_view(['GET'])
def source_list(request):
    from django.conf import settings
    return Response({'enabled':settings.OFFICIAL_ONLINE_ENABLED,'seeds':REGISTRY['seeds'],
        'hosts':list(REGISTRY['hosts']),'notice':'仅遍历配置的官方目录与相关链接；不保证全量覆盖。'})


@api_view(['GET'])
def snapshot_file(request, job_id, version_id):
    job = get_object_or_404(jobs_for(request.user),pk=job_id)
    if version_id not in [i['version_id'] for i in job.result.get('items',[])]:
        return Response({'error':'该任务没有此资料'},status=404)
    version = get_object_or_404(DocumentVersion,pk=version_id)
    if not version.file:
        return Response({'error':'没有可下载的原始文件'},status=404)
    return FileResponse(version.file.open('rb'),as_attachment=True,
        filename=f'official-snapshot-{version.pk}.'+version.file.name.rsplit('.',1)[-1])
