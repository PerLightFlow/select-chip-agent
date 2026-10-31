import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count
from assistant.models import KnowledgeCollection, KnowledgeDocument, KnowledgeReplica
from assistant.knowledge_sync import publication_changed, retry
from assistant.knowledge_backends.weknora import WeKnora, KnowledgeUnavailable


class Command(BaseCommand):
    help = '绑定 WeKnora 知识库、补录已发布资料、查看或重试同步任务'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['bind', 'backfill', 'status', 'retry'])
        parser.add_argument('--scope', default='common')
        parser.add_argument('--kb-id')
        parser.add_argument('--version-id', type=int)

    def handle(self, *args, **options):
        action = options['action']
        if action == 'status':
            counts = list(KnowledgeReplica.objects.values('state', 'source_ready').annotate(count=Count('pk')))
            self.stdout.write(json.dumps({'mode': settings.KNOWLEDGE_BACKEND, 'sync_enabled': settings.WEKNORA_SYNC_ENABLED,
                'collections': list(KnowledgeCollection.objects.values('scope', 'remote_id', 'wiki_state')), 'tasks': counts}, ensure_ascii=False))
            return
        if not settings.WEKNORA_SYNC_ENABLED:
            raise CommandError('请先配置 WEKNORA_SYNC_ENABLED=1')
        if action == 'bind':
            scope, remote_id = options['scope'], options['kb_id']
            if not remote_id or (scope != 'common' and not (scope.startswith('project:') and scope[8:].isdigit())):
                raise CommandError('需要 --kb-id；scope 为 common 或 project:<id>')
            try:
                data = WeKnora(write=True).collection(remote_id)
            except KnowledgeUnavailable as exc:
                raise CommandError(str(exc)) from None
            strategy = data.get('indexing_strategy', {})
            if strategy.get('graph_enabled') or bool(strategy.get('wiki_enabled')) != settings.WEKNORA_WIKI_ENABLED or not strategy.get('vector_enabled') or not strategy.get('keyword_enabled'):
                raise CommandError('请启用向量和关键词索引、关闭图谱，并让 Wiki 开关与应用配置一致')
            with transaction.atomic():
                c, _ = KnowledgeCollection.objects.get_or_create(scope=scope)
                c = KnowledgeCollection.objects.select_for_update().get(pk=c.pk)
                if c.remote_id and c.remote_id != remote_id:
                    raise CommandError('已有绑定不可直接改指向；请使用独立迁移流程')
                if KnowledgeCollection.objects.exclude(pk=c.pk).filter(remote_id=remote_id).exists():
                    raise CommandError('这个知识库已经绑定其他范围')
                c.remote_id = remote_id
                if settings.WEKNORA_WIKI_ENABLED:
                    c.wiki_state = 'pending'
                c.save()
                c.replicas.filter(state='blocked', upload_started_at__isnull=True).update(state='queued', error='')
            self.stdout.write('知识库已绑定')
        elif action == 'backfill':
            count = 0
            for doc_id in KnowledgeDocument.objects.filter(versions__state='published').values_list('pk', flat=True).iterator():
                with transaction.atomic():
                    doc = KnowledgeDocument.objects.select_for_update().get(pk=doc_id)
                    publication_changed(doc)
                count += 1
            self.stdout.write(f'已对账 {count} 份已发布资料；重复运行不会重复创建任务')
        elif action == 'retry':
            if not options['version_id']:
                raise CommandError('需要 --version-id')
            try:
                retry(options['version_id'])
            except (ValueError, KnowledgeReplica.DoesNotExist) as exc:
                raise CommandError(str(exc)) from None
            self.stdout.write('同步重试已排队；不确定的上传会先对账')
