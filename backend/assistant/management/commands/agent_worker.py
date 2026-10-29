import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction, close_old_connections, connections
from django.utils import timezone
from assistant.models import Turn, KnowledgeVersion
from assistant.runtime import run_turn
from assistant.knowledge import index_document


def perform(fn, pk):
    close_old_connections()
    try:
        fn(pk)
    finally:
        connections.close_all()


def claim():
    with transaction.atomic():
        t = Turn.objects.select_for_update(skip_locked=True).filter(state='queued').order_by('created_at').first()
        if t:
            t.state = 'running'
            t.save()
            return run_turn, t.pk
        v = KnowledgeVersion.objects.select_for_update(skip_locked=True).filter(state='queued').order_by('id').first()
        if v:
            v.state = 'indexing'
            v.save()
            return index_document, v.pk
    return None


class Command(BaseCommand):
    help = '运行持久化对话和企业文档任务，支持并发与停止'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        workers = max(1, min(settings.AGENT_WORKERS, 50))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pending = set()
            while True:
                close_old_connections()
                cutoff = timezone.now() - timedelta(seconds=settings.AGENT_TURN_SECONDS + 180)
                Turn.objects.filter(state='running', updated_at__lt=cutoff).update(state='failed', error='任务中断，请继续提问', updated_at=timezone.now())
                KnowledgeVersion.objects.filter(state='indexing', updated_at__lt=cutoff).update(state='failed', error='解析任务中断，请重新上传', updated_at=timezone.now())
                for f in list(pending):
                    if f.done():
                        pending.remove(f)
                        try:
                            f.result()
                        except Exception:
                            self.stderr.write('任务异常退出，超时回收将标记失败')
                while len(pending) < workers:
                    job = claim()
                    if not job:
                        break
                    pending.add(pool.submit(perform, *job))
                    if options['once']:
                        for f in pending:
                            f.result()
                        return
                if options['once']:
                    return
                time.sleep(0.5)
