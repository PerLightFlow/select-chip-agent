import time
import uuid
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction, close_old_connections
from django.utils import timezone
from core.models import DocumentVersion
from core.knowledge import build_index


class Command(BaseCommand):
    help = '处理持久化文档索引队列；单次任务使用数据库行锁领取'

    def add_arguments(self, parser):
        parser.add_argument('--once',action='store_true')

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            DocumentVersion.objects.filter(state='indexing',updated_at__lt=timezone.now()-timedelta(hours=2)).update(
                state='failed',error='任务中断或超时，请在后台重新排队',updated_at=timezone.now())
            with transaction.atomic():
                v = DocumentVersion.objects.select_for_update(skip_locked=True).filter(state='queued').order_by('id').first()
                if v:
                    v.state, v.index_generation = 'indexing', uuid.uuid4()
                    v.attempts += 1
                    v.save()
                    version_id = v.pk
                else:
                    version_id = None
            if version_id:
                build_index(version_id)
            if options['once']:
                return
            if not version_id:
                time.sleep(2)
